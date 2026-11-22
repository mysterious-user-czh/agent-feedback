"""MCP stdio server exposing the four agent-feedback workflow tools."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .service import FeedbackService

try:
    from mcp.server import MCPServer
except ImportError as exc:
    raise SystemExit("MCP support is not installed. Run: pip install -e '.[mcp]'") from exc

DB_PATH = os.environ.get("AGENT_FEEDBACK_DB", str(Path.home() / ".agent-feedback" / "feedback.db"))
CONTRACTS_PATH = os.environ.get("AGENT_FEEDBACK_CONTRACTS")
mcp = MCPServer("agent-feedback")
service = FeedbackService(DB_PATH, CONTRACTS_PATH)

WRITE = {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False}
READ = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}


@mcp.tool(name="feedback_start", annotations=WRITE)
def feedback_start(agent: str, goal: str, session_id: str | None = None,
                   config_hash: str | None = None, external_id: str | None = None) -> dict[str, Any]:
    """Start tracking one agent task. Returns a task_id required by later events and labels.
    external_id may be a stable platform task ID to make repeated imports idempotent."""
    return service.start(agent, goal, session_id, config_hash, external_id)


@mcp.tool(name="feedback_event", annotations=WRITE)
def feedback_event(task_id: str, type: str, payload: dict[str, Any], event_id: str | None = None) -> dict[str, Any]:
    """Record selection, tool_result, artifact, verification, or process_result. selection needs kind/name/source;
    tool_result needs name/status; process_result needs integer exit_code; verification success requires objective evidence.
    Events never modify agent configuration."""
    return service.event(task_id, type, payload, event_id)


@mcp.tool(name="feedback_label", annotations=WRITE)
def feedback_label(task_id: str, outcome: str = "unknown", failure_stage: str = "unknown",
                   expected_selection: str | None = None, comment: str | None = None,
                   source: str = "human", actor: str | None = None, reason: str | None = None) -> dict[str, Any]:
    """Save an auditable label revision. Success requires verification evidence. Observed feedback cannot
    overwrite human labels; a human revision requires a reason. Tool errors alone do not prove routing failure."""
    return service.label(task_id, outcome, failure_stage, expected_selection, comment, source, actor, reason)


@mcp.tool(name="feedback_report", annotations=READ)
def feedback_report(agent: str | None = None, selection: str | None = None,
                    review_status: str = "all", limit: int = 20, offset: int = 0,
                    response_format: str = "markdown", priority: str | None = None,
                    execution: str | None = None, has_tool_errors: bool | None = None,
                    has_observed_label: bool | None = None, sort: str = "priority") -> dict[str, Any] | str:
    """Read a paginated triage report. Filter by priority P0/P1/P2/none, execution pass/fail/unknown,
    tool-failure presence, observed-label presence, agent, selection, and review status. Sort by priority,
    source_time, or tool_errors. Candidate signals require review and are not automatic verdicts."""
    return service.report(agent=agent, selection=selection, review_status=review_status,
                          limit=limit, offset=offset, response_format=response_format,
                          priority=priority, execution=execution, has_tool_errors=has_tool_errors,
                          has_observed_label=has_observed_label, sort=sort)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
