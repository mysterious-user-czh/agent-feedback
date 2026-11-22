"""Read-only Hermes import with versioned three-field message-segment provenance."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ..segment_rules import CORRECTION_RULES_VERSION, build_segments
from ..service import FeedbackService

RULES_VERSION = "hermes-message-segments-v2.2-three-fields"


def _json(value: Any) -> Any:
    try:
        return json.loads(value or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}


def classify_tool_result(data: Any) -> str | None:
    """Return failure/cancelled for structured abnormal results; normalize numeric exit codes."""
    if not isinstance(data, dict):
        return None
    raw_code = data.get("exit_code")
    code = None
    if not isinstance(raw_code, bool) and isinstance(raw_code, (int, str)):
        try:
            code = int(raw_code)
        except ValueError:
            code = None
    failed = data.get("success") is False or bool(data.get("error")) or (code is not None and code != 0)
    if not failed:
        return None
    return "cancelled" if code == 130 else "failure"


def import_hermes(db_path: str, service: FeedbackService, hours: int | None = None,
                  include_subagents: bool = False) -> dict[str, int]:
    """Incrementally import v2 segments; reject unsafe session-level or v1 stores."""
    path = Path(db_path).expanduser().resolve()
    con = sqlite3.connect("file:" + path.as_posix() + "?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours) if hours else None
    sessions = con.execute("SELECT id,started_at,parent_session_id FROM sessions ORDER BY started_at").fetchall()
    stats = {"total_sessions": len(sessions), "excluded_subagents": 0, "matched": 0,
             "imported": 0, "already_present": 0, "skipped_unchanged": 0,
             "segments_touched": 0, "segment_messages": 0,
             "selection_events": 0, "tool_errors": 0, "tool_failures": 0,
             "tool_cancellations": 0, "tool_error_or_cancel_events": 0,
             "correction_candidates": 0, "human_labels_preserved": 0, "parse_failures": 0}
    rules = service.store.one("SELECT value FROM schema_metadata WHERE key='hermes_segment_rules'")
    segmented = service.store.one("SELECT task_id FROM tasks WHERE agent='hermes' AND external_id LIKE 'hermes:%:segment:%' LIMIT 1")
    if (rules and rules["value"] != RULES_VERSION) or (segmented and not rules):
        con.close()
        raise ValueError("Incompatible Hermes segment rules; import into a fresh database")
    service.store.execute(
        "INSERT INTO schema_metadata VALUES('hermes_segment_rules',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (RULES_VERSION,),
    )
    service.store.execute(
        "INSERT INTO schema_metadata VALUES('hermes_correction_rules',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (CORRECTION_RULES_VERSION,),
    )
    for session in sessions:
        sid = session["id"]
        if session["parent_session_id"] and not include_subagents:
            stats["excluded_subagents"] += 1
            continue
        legacy = service.store.one("SELECT task_id FROM tasks WHERE agent='hermes' AND external_id=?", (sid,))
        if legacy:
            con.close()
            raise ValueError(
                f"Legacy session-level Hermes task detected for {sid}; "
                "import into a fresh database or run an explicit migration"
            )
        try:
            all_messages = con.execute("SELECT id,role,content,tool_calls,tool_name,timestamp FROM messages WHERE session_id=? ORDER BY id", (sid,)).fetchall()
            if not all_messages:
                continue
            latest = max((float(m["timestamp"] or 0) for m in all_messages), default=float(session["started_at"]))
            if cutoff and datetime.fromtimestamp(latest, timezone.utc) < cutoff:
                continue
            stats["matched"] += 1
            # Backfill source time even when no new messages need importing.
            timestamps = {int(message["id"]): float(message["timestamp"] or session["started_at"] or 0)
                          for message in all_messages}
            imported_messages = service.store.all(
                "SELECT task_id,message_id FROM segment_messages WHERE agent='hermes' AND session_id=?", (sid,),
            )
            source_times: dict[str, float] = {}
            for row in imported_messages:
                timestamp = timestamps.get(int(row["message_id"]))
                if timestamp is not None:
                    source_times[row["task_id"]] = min(timestamp, source_times.get(row["task_id"], timestamp))
            for task_id, timestamp in source_times.items():
                source_started_at = datetime.fromtimestamp(timestamp, timezone.utc).isoformat()
                service.store.execute(
                    "UPDATE tasks SET source_started_at=? WHERE task_id=? AND source_started_at IS NULL",
                    (source_started_at, task_id),
                )
            cursor = service.store.one("SELECT last_message_id FROM ingestion_cursors WHERE agent='hermes' AND external_id=?", (sid,))
            last_id = cursor["last_message_id"] if cursor else 0
            max_id = max(m["id"] for m in all_messages)
            if last_id >= max_id:
                stats["skipped_unchanged"] += 1
                continue
            for segment in build_segments(sid, all_messages):
                new_messages = [entry for entry in segment["messages"] if entry[0]["id"] > last_id]
                if not new_messages:
                    continue
                started = service.start("hermes", segment["goal"], sid, external_id=segment["external_id"])
                tid = started["task_id"]
                first_source_time = float(new_messages[0][0]["timestamp"] or session["started_at"] or 0)
                service.store.execute(
                    "UPDATE tasks SET source_started_at=? WHERE task_id=? AND source_started_at IS NULL",
                    (datetime.fromtimestamp(first_source_time, timezone.utc).isoformat(), tid),
                )
                stats["imported" if started["created"] else "already_present"] += 1
                stats["segments_touched"] += 1
                if started["created"]:
                    service.store.execute(
                        "INSERT INTO task_segments(task_id,segment_type,ambiguous_reason) VALUES(?,?,?)",
                        (tid, segment["segment_type"], segment["ambiguous_reason"]),
                    )
                else:
                    service.store.execute("UPDATE tasks SET goal=? WHERE task_id=?", (segment["goal"], tid))
                    service.store.execute(
                        "UPDATE task_segments SET segment_type=?,ambiguous_reason=? WHERE task_id=?",
                        (segment["segment_type"], segment["ambiguous_reason"], tid),
                    )
                for message, event_source, relation, automated in new_messages:
                    service.store.execute(
                        "INSERT INTO segment_messages(task_id,agent,session_id,message_id,role,is_automated,event_source,relation) VALUES(?,?,?,?,?,?,?,?)",
                        (tid, "hermes", sid, message["id"], message["role"], int(automated), event_source, relation),
                    )
                    stats["segment_messages"] += 1
                    decoded = _json(message["tool_calls"])
                    for index, call in enumerate(decoded if isinstance(decoded, list) else []):
                        fn = call.get("function") or {}
                        if fn.get("name") != "skill_view":
                            continue
                        name = _json(fn.get("arguments")).get("name")
                        if name:
                            result = service.event(
                                tid, "selection", {"kind": "skill", "name": name, "source": "observed"},
                                f"hermes:{sid}:selection:{message['id']}:{index}",
                            )
                            stats["selection_events"] += int(result["created"])
                    content = message["content"] or ""
                    if message["role"] == "tool":
                        start = content.find("{")
                        data = _json(content[start:]) if start >= 0 else {}
                        tool_status = classify_tool_result(data)
                        if tool_status:
                            result = service.event(
                                tid, "tool_result",
                                {"name": message["tool_name"] or "hermes_tool", "status": tool_status,
                                 "error_class": "cancelled" if tool_status == "cancelled" else "structured_error",
                                 "source": "observed"},
                                f"hermes:{sid}:error:{message['id']}",
                            )
                            created = int(result["created"])
                            stats["tool_error_or_cancel_events"] += created
                            stats["tool_cancellations" if tool_status == "cancelled" else "tool_failures"] += created
                            stats["tool_errors"] += created if tool_status == "failure" else 0
                    if relation == "correction":
                        result = service.label(
                            tid, comment="疑似用户纠正：" + content[:500], source="observed",
                        )
                        stats["correction_candidates"] += int(result.get("saved", False))
                        stats["human_labels_preserved"] += int(result.get("preserved", False))
            service.store.execute("INSERT INTO ingestion_cursors VALUES('hermes',?,?) ON CONFLICT(agent,external_id) DO UPDATE SET last_message_id=excluded.last_message_id", (sid, max_id))
        except (ValueError, TypeError, sqlite3.Error, json.JSONDecodeError):
            stats["parse_failures"] += 1
    con.close()
    return stats
