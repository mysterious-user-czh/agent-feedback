"""Continuous read-only Hermes collection with independent coverage accounting."""
from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .adapters.hermes import classify_tool_result, import_hermes
from .service import FeedbackService


def _json(value: Any) -> Any:
    try:
        return json.loads(value or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}


def _source_messages(db_path: str, hours: int | None, include_subagents: bool):
    path = Path(db_path).expanduser().resolve()
    con = sqlite3.connect("file:" + path.as_posix() + "?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours) if hours else None
    expected = {}
    excluded_subagents = 0
    for session in con.execute("SELECT id,started_at,parent_session_id FROM sessions ORDER BY started_at"):
        sid = session["id"]
        if session["parent_session_id"] and not include_subagents:
            excluded_subagents += 1
            continue
        rows = con.execute(
            "SELECT id,role,content,tool_calls,tool_name,timestamp FROM messages WHERE session_id=? ORDER BY id",
            (sid,),
        ).fetchall()
        if not rows:
            continue
        latest = max((float(row["timestamp"] or 0) for row in rows), default=float(session["started_at"]))
        if cutoff and datetime.fromtimestamp(latest, timezone.utc) < cutoff:
            continue
        expected[sid] = [dict(row) for row in rows]
    con.close()
    return expected, excluded_subagents


def audit_hermes_import(db_path: str, service: FeedbackService, hours: int | None = None,
                        include_subagents: bool = False) -> dict[str, Any]:
    """Enumerate the source baseline and compare stable identities, not importer self-reports."""
    expected, excluded_subagents = _source_messages(db_path, hours, include_subagents)
    actual_rows = service.store.all(
        "SELECT session_id,message_id FROM segment_messages WHERE agent='hermes' ORDER BY session_id,message_id")
    actual = {}
    for row in actual_rows:
        actual.setdefault(row["session_id"], set()).add(int(row["message_id"]))

    missing_sessions = []
    unexpected_sessions = sorted(set(actual) - set(expected)) if not hours else []
    missing_messages = []
    unexpected_messages = []
    covered_sessions = 0
    expected_message_count = 0
    expected_selections = set()
    expected_failures = set()
    expected_cancellations = set()
    for sid, rows in expected.items():
        expected_ids = {int(row["id"]) for row in rows}
        actual_ids = actual.get(sid, set())
        expected_message_count += len(expected_ids)
        if not actual_ids:
            missing_sessions.append(sid)
        missing = sorted(expected_ids - actual_ids)
        unexpected = sorted(actual_ids - expected_ids)
        missing_messages.extend({"session_id": sid, "message_id": mid} for mid in missing)
        unexpected_messages.extend({"session_id": sid, "message_id": mid} for mid in unexpected)
        if not missing and not unexpected:
            covered_sessions += 1
        for row in rows:
            calls = _json(row["tool_calls"])
            for index, call in enumerate(calls if isinstance(calls, list) else []):
                fn = call.get("function") or {}
                if fn.get("name") == "skill_view" and _json(fn.get("arguments")).get("name"):
                    expected_selections.add(f"hermes:{sid}:selection:{row['id']}:{index}")
            content = row["content"] or ""
            start = content.find("{")
            data = _json(content[start:]) if start >= 0 else {}
            tool_status = classify_tool_result(data) if row["role"] == "tool" else None
            if tool_status:
                target = expected_cancellations if tool_status == "cancelled" else expected_failures
                target.add(f"hermes:{sid}:error:{row['id']}")

    event_rows = service.store.all("SELECT event_id,type,payload FROM events")
    actual_selections = {row["event_id"] for row in event_rows
                         if row["type"] == "selection" and row["event_id"].startswith("hermes:")}
    actual_failures = {row["event_id"] for row in event_rows if row["type"] == "tool_result"
                       and row["event_id"].startswith("hermes:") and _json(row["payload"]).get("status") == "failure"}
    actual_cancellations = {row["event_id"] for row in event_rows if row["type"] == "tool_result"
                            and row["event_id"].startswith("hermes:") and _json(row["payload"]).get("status") == "cancelled"}
    result = {
        "source_sessions": len(expected),
        "covered_sessions": covered_sessions,
        "missing_sessions": missing_sessions,
        "unexpected_sessions": unexpected_sessions,
        "excluded_subagents": excluded_subagents,
        "source_messages": expected_message_count,
        "covered_messages": expected_message_count - len(missing_messages),
        "missing_messages": missing_messages,
        "unexpected_messages": unexpected_messages,
        "source_skill_selections": len(expected_selections),
        "covered_skill_selections": len(expected_selections & actual_selections),
        "missing_skill_selections": sorted(expected_selections - actual_selections),
        "unexpected_skill_selections": sorted(actual_selections - expected_selections) if not hours else [],
        "source_tool_failures": len(expected_failures),
        "covered_tool_failures": len(expected_failures & actual_failures),
        "missing_tool_failures": sorted(expected_failures - actual_failures),
        "unexpected_tool_failures": sorted(actual_failures - expected_failures) if not hours else [],
        "source_tool_cancellations": len(expected_cancellations),
        "covered_tool_cancellations": len(expected_cancellations & actual_cancellations),
        "missing_tool_cancellations": sorted(expected_cancellations - actual_cancellations),
        "unexpected_tool_cancellations": sorted(actual_cancellations - expected_cancellations) if not hours else [],
    }
    result["source_tool_error_or_cancel_events"] = len(expected_failures) + len(expected_cancellations)
    result["covered_tool_error_or_cancel_events"] = (len(expected_failures & actual_failures) +
                                                       len(expected_cancellations & actual_cancellations))
    # Backward-compatible field names now mean failures only, never failure+cancellation totals.
    result["source_tool_errors"] = result["source_tool_failures"]
    result["covered_tool_errors"] = result["covered_tool_failures"]
    result["missing_tool_errors"] = result["missing_tool_failures"]
    result["unexpected_tool_errors"] = result["unexpected_tool_failures"]
    result["coverage_complete"] = all((
        not missing_sessions, not unexpected_sessions, not missing_messages, not unexpected_messages,
        not result["missing_skill_selections"], not result["unexpected_skill_selections"],
        not result["missing_tool_failures"], not result["unexpected_tool_failures"],
        not result["missing_tool_cancellations"], not result["unexpected_tool_cancellations"],
    ))
    return result


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def collect_once(state_db: str, feedback_db: str, contracts: str | None = None,
                 hours: int | None = None, include_subagents: bool = False,
                 status_path: str | None = None) -> dict[str, Any]:
    started = datetime.now(timezone.utc)
    service = FeedbackService(feedback_db, contracts)
    try:
        stats = import_hermes(state_db, service, hours, include_subagents)
        coverage = audit_hermes_import(state_db, service, hours, include_subagents)
    finally:
        service.close()
    complete = coverage["coverage_complete"] and stats["parse_failures"] == 0
    status = {
        "schema_version": 2,
        "last_run_utc": datetime.now(timezone.utc).isoformat(),
        "heartbeat_utc": datetime.now(timezone.utc).isoformat(),
        "phase": "complete",
        "duration_seconds": (datetime.now(timezone.utc) - started).total_seconds(),
        "success": complete,
        "import": stats,
        "coverage": coverage,
    }
    destination = Path(status_path).expanduser().resolve() if status_path else (
        Path(feedback_db).expanduser().resolve().parent / "collector-status.json")
    _atomic_json(destination, status)
    history = destination.parent / "collector-history.jsonl"
    history_row = {key: value for key, value in status.items() if key != "coverage"}
    history_row["coverage"] = {key: value for key, value in coverage.items()
                               if not isinstance(value, list)}
    with history.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(history_row, ensure_ascii=False) + "\n")
    return status


def watch_hermes(state_db: str, feedback_db: str, contracts: str | None = None,
                 hours: int | None = None, include_subagents: bool = False,
                 interval_seconds: int = 60, cycles: int = 0,
                 status_path: str | None = None) -> None:
    if interval_seconds < 5:
        raise ValueError("interval_seconds must be at least 5")
    completed = 0
    destination = Path(status_path).expanduser().resolve() if status_path else (
        Path(feedback_db).expanduser().resolve().parent / "collector-status.json")
    while True:
        heartbeat = datetime.now(timezone.utc).isoformat()
        _atomic_json(destination, {"schema_version": 2, "last_run_utc": heartbeat,
                                   "heartbeat_utc": heartbeat, "phase": "collecting",
                                   "success": False})
        try:
            status = collect_once(state_db, feedback_db, contracts, hours,
                                  include_subagents, status_path)
            print(json.dumps({"last_run_utc": status["last_run_utc"], "success": status["success"],
                              "coverage": {k: v for k, v in status["coverage"].items()
                                           if k in {"source_sessions", "covered_sessions", "source_messages",
                                                    "covered_messages", "coverage_complete"}}}),
                  flush=True)
        except Exception as exc:
            destination = Path(status_path).expanduser().resolve() if status_path else (
                Path(feedback_db).expanduser().resolve().parent / "collector-status.json")
            _atomic_json(destination, {"schema_version": 2,
                                       "last_run_utc": datetime.now(timezone.utc).isoformat(),
                                       "heartbeat_utc": datetime.now(timezone.utc).isoformat(),
                                       "phase": "error",
                                       "success": False,
                                       "error": f"{type(exc).__name__}: {exc}"})
            print(f"collection failed: {type(exc).__name__}: {exc}", flush=True)
        completed += 1
        if cycles and completed >= cycles:
            return
        time.sleep(interval_seconds)
