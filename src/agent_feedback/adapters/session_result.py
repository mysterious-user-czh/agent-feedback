"""Import the engine-neutral skill-up SessionResult contract into the event store."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from ..service import FeedbackService


def _object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def import_session_result(result_path: str | Path, service: FeedbackService, *,
                          verification: dict[str, Any] | None = None,
                          goal: str | None = None, external_id: str | None = None) -> dict[str, Any]:
    path = Path(result_path).resolve()
    raw = path.read_bytes()
    result = json.loads(raw)
    engine = result.get("engine")
    code = result.get("exit_code")
    if not isinstance(engine, str) or not engine or isinstance(code, bool) or not isinstance(code, int):
        raise ValueError("SessionResult requires engine and integer exit_code")
    transcript = result.get("transcript") or []
    if not isinstance(transcript, list):
        raise ValueError("SessionResult.transcript must be a list")
    if goal is None:
        goal = next((m.get("content") for m in transcript if m.get("role") == "user" and m.get("content")), None)
    if not goal:
        raise ValueError("A goal or user transcript message is required")
    identity = external_id or "session-result:" + hashlib.sha256(raw).hexdigest()
    started = service.start(engine, goal, result.get("session_id") or None, external_id=identity)
    task_id = started["task_id"]
    stats = {"created": started["created"], "selection_events": 0, "tool_events": 0,
             "artifact_events": 0, "verification_events": 0, "process_events": 0}
    for index, selection in enumerate(result.get("selections") or []):
        name = selection.get("name") if isinstance(selection, dict) else str(selection)
        made = service.event(task_id, "selection", {"kind": "skill", "name": name, "source": "observed"},
                             f"{identity}:selection:{index}")
        stats["selection_events"] += int(made["created"])
    for index, message in enumerate(transcript):
        if message.get("role") != "tool":
            continue
        content = _object(message.get("content"))
        output = _object(content.get("output"))
        tool_code = output.get("exit_code")
        cancelled = tool_code == 130 or content.get("status") == "cancelled"
        failed = bool(content.get("is_error")) or content.get("status") == "failure" or (
            isinstance(tool_code, int) and not isinstance(tool_code, bool) and tool_code != 0)
        status = "cancelled" if cancelled else "failure" if failed else "success"
        made = service.event(task_id, "tool_result", {
            "name": str(content.get("name") or "engine_tool"), "status": status,
            "error_class": "cancelled" if cancelled else "structured_error" if failed else None,
            "recovered": False, "source": "observed"}, f"{identity}:tool:{index}")
        stats["tool_events"] += int(made["created"])
    for index, artifact in enumerate((result.get("artifacts") or {}).get("files") or []):
        made = service.event(task_id, "artifact", {
            "name": str(artifact.get("name") or artifact.get("path") or f"artifact-{index}"),
            "reference": artifact.get("path"), "sha256": artifact.get("sha256"), "source": "observed"},
            f"{identity}:artifact:{index}")
        stats["artifact_events"] += int(made["created"])
    if verification is not None:
        made = service.event(task_id, "verification", verification, f"{identity}:verification")
        stats["verification_events"] += int(made["created"])
    made = service.event(task_id, "process_result", {"exit_code": code, "source": "observed"},
                         f"{identity}:process")
    stats["process_events"] += int(made["created"])
    stats["task_id"] = task_id
    return stats
