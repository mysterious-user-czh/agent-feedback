"""Import isolated Hermes run records, tool traces and independent oracle results into P3."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..service import FeedbackService


def _decode(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
            return decoded if isinstance(decoded, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def tool_results(stream_path: Path) -> list[dict[str, Any]]:
    """Read actual stream-json tool results; cancellation is never an ordinary error."""
    results = []
    for index, line in enumerate(stream_path.read_text(encoding="utf-8", errors="replace").splitlines()):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") != "tool_result":
            continue
        output = _decode(event.get("output"))
        code = output.get("exit_code")
        cancelled = code == 130
        failed = bool(event.get("is_error")) or output.get("success") is False or bool(output.get("error")) or (
            isinstance(code, int) and not isinstance(code, bool) and code != 0
        )
        status = "cancelled" if cancelled else "failure" if failed else "success"
        results.append({
            "event_key": str(event.get("tool_call_id") or index),
            "payload": {"name": str(event.get("name") or "hermes_tool"), "status": status,
                        "error_class": "cancelled" if cancelled else "structured_error" if failed else None,
                        "recovered": False, "source": "observed"},
        })
    return results


def _artifact_source(row: dict[str, Any]) -> tuple[str, bool]:
    """Keep live only with frozen harness provenance; otherwise downgrade to imported."""
    source = row.get("artifact_source", "imported")
    if source != "live":
        return source, False
    provenance = row.get("provenance") or {}
    required = ("harness_version", "config_sha256", "skill_tree_sha256")
    if all(provenance.get(key) for key in required):
        return "live", False
    return "imported", True


def import_isolated_batch(batch_dir: str | Path, spec_path: str | Path,
                          service: FeedbackService) -> dict[str, Any]:
    """Import actual runs idempotently; never treat final text as objective verification."""
    batch = Path(batch_dir).resolve()
    data = json.loads((batch / "results.json").read_text(encoding="utf-8"))
    specs = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    goals = {t.get("task_id", t.get("case_id")): t["query"] for t in specs["tasks"]}
    stats = {"runs_seen": len(data["results"]), "imported": 0, "already_present": 0,
             "selection_events": 0, "tool_events": 0, "tool_failures": 0,
             "tool_cancellations": 0, "verification_events": 0, "process_events": 0,
             "live_downgraded": 0}
    seen = set()
    for row in data["results"]:
        run_id = row["run_id"]
        if run_id in seen:
            raise ValueError(f"Duplicate run_id in results: {run_id}")
        seen.add(run_id)
        raw_path = batch / "raw" / f"{run_id}.json"
        raw = json.loads(raw_path.read_text(encoding="utf-8"))
        if raw["run_id"] != run_id or raw.get("case_id") != row["task_id"]:
            raise ValueError(f"Raw/result identity mismatch: {run_id}")
        if raw["exit_code"] != row["exit_code"]:
            raise ValueError(f"Raw/result exit mismatch: {run_id}")
        stream_path = batch / "raw" / f"{run_id}.stream.jsonl"
        tools = tool_results(stream_path)
        goal = goals[row["task_id"]]
        started = service.start("isolated-hermes", goal, raw.get("session_id"),
                                raw.get("config_sha256"), f"isolated:{run_id}")
        task_id = started["task_id"]
        stats["imported" if started["created"] else "already_present"] += 1
        for index, name in enumerate(row["selected_skills"]):
            result = service.event(task_id, "selection",
                                   {"kind": "skill", "name": name, "source": "observed"},
                                   f"isolated:{run_id}:selection:{index}")
            stats["selection_events"] += int(result["created"])
        for tool in tools:
            result = service.event(task_id, "tool_result", tool["payload"],
                                   f"isolated:{run_id}:tool:{tool['event_key']}")
            stats["tool_events"] += int(result["created"])
            if result["created"] and tool["payload"]["status"] == "failure":
                stats["tool_failures"] += 1
            if result["created"] and tool["payload"]["status"] == "cancelled":
                stats["tool_cancellations"] += 1
        artifact_source, downgraded = _artifact_source(row)
        stats["live_downgraded"] += int(downgraded)
        outcome = ("success" if row["artifact_pass"] else "failure") if artifact_source in {"live", "imported"} else "unknown"
        verified = service.event(
            task_id, "verification",
            {"outcome": outcome,
             "evidence": [f"{artifact_source.capitalize()} independent oracle: {row['artifact_evidence']}"],
             "source": "observed", "artifact_source": artifact_source},
            f"isolated:{run_id}:verification",
        )
        stats["verification_events"] += int(verified["created"])
        process = service.event(task_id, "process_result",
                                {"exit_code": row["exit_code"], "source": "observed"},
                                f"isolated:{run_id}:process")
        stats["process_events"] += int(process["created"])
    expected_runs = data["summary"].get("runs", data["summary"].get("tasks", len(data["results"])))
    stats["missing_runs"] = int(expected_runs - len(data["results"]))
    return stats
