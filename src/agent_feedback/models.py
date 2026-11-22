"""Validation and safe serialization for the agent-feedback event protocol."""
from __future__ import annotations

import re
from typing import Any

OUTCOMES = {"success", "failure", "unknown", "abandoned"}
FAILURE_STAGES = {"routing", "execution", "environment", "requirements", "unknown"}
SOURCES = {"observed", "self_reported", "human"}
EVENT_TYPES = {"selection", "tool_result", "artifact", "verification", "process_result"}
SELECTION_KINDS = {"skill", "tool", "agent", "workflow"}
TOOL_STATUSES = {"success", "failure", "cancelled"}
ARTIFACT_SOURCES = {"live", "imported", "unknown"}

_SECRET = re.compile(r"(?i)\b(sk-[A-Za-z0-9_-]{12,}|bearer\s+[A-Za-z0-9._-]{12,})")


def clean_text(value: Any, field: str, *, required: bool = False, limit: int = 2000) -> str:
    if value is None:
        if required:
            raise ValueError(f"{field} is required")
        return ""
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    value = _SECRET.sub("[REDACTED]", value.strip())
    if required and not value:
        raise ValueError(f"{field} cannot be empty")
    if len(value) > limit:
        raise ValueError(f"{field} exceeds {limit} characters")
    return value


def choice(value: Any, allowed: set[str], field: str) -> str:
    value = clean_text(value, field, required=True, limit=50)
    if value not in allowed:
        raise ValueError(f"{field} must be one of: {', '.join(sorted(allowed))}")
    return value


def validate_event(event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    event_type = choice(event_type, EVENT_TYPES, "type")
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")
    p = dict(payload)
    if event_type == "selection":
        return {
            "kind": choice(p.get("kind"), SELECTION_KINDS, "payload.kind"),
            "name": clean_text(p.get("name"), "payload.name", required=True, limit=200),
            "source": choice(p.get("source", "self_reported"), SOURCES, "payload.source"),
        }
    if event_type == "tool_result":
        return {
            "name": clean_text(p.get("name"), "payload.name", required=True, limit=200),
            "status": choice(p.get("status"), TOOL_STATUSES, "payload.status"),
            "error_class": clean_text(p.get("error_class"), "payload.error_class", limit=100) or None,
            "recovered": bool(p.get("recovered", False)),
            "source": choice(p.get("source", "observed"), SOURCES, "payload.source"),
        }
    if event_type == "artifact":
        return {
            "name": clean_text(p.get("name"), "payload.name", required=True, limit=200),
            "reference": clean_text(p.get("reference"), "payload.reference", limit=1000) or None,
            "sha256": clean_text(p.get("sha256"), "payload.sha256", limit=64) or None,
            "source": choice(p.get("source", "observed"), SOURCES, "payload.source"),
        }
    if event_type == "process_result":
        code = p.get("exit_code")
        if isinstance(code, bool) or not isinstance(code, int):
            raise ValueError("payload.exit_code must be an integer")
        return {"exit_code": code, "source": choice(p.get("source", "observed"), SOURCES, "payload.source")}
    evidence = p.get("evidence") or []
    if not isinstance(evidence, list) or len(evidence) > 20:
        raise ValueError("payload.evidence must be a list with at most 20 items")
    outcome = choice(p.get("outcome"), OUTCOMES, "payload.outcome")
    if outcome == "success" and not evidence:
        raise ValueError("success verification requires objective evidence")
    source = choice(p.get("source", "observed"), SOURCES, "payload.source")
    artifact_source = choice(p.get("artifact_source", "unknown"), ARTIFACT_SOURCES,
                             "payload.artifact_source")
    if outcome == "success":
        if source == "self_reported":
            raise ValueError("success verification cannot be self_reported")
        if artifact_source not in {"live", "imported"}:
            raise ValueError("success verification requires artifact_source=live or imported")
    return {
        "outcome": outcome,
        "evidence": [clean_text(x, "payload.evidence", required=True, limit=500) for x in evidence],
        "source": source,
        "artifact_source": artifact_source,
    }
