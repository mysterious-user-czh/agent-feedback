---
name: agent-feedback
description: Collect and review Agent Skill selection, tool execution, live artifact verification, process exit, and human labels through the agent-feedback MCP server. Use when tracking why an Agent selected a Skill, auditing whether a task really completed, importing Hermes or skill-up evidence, or generating reproducible regression cases; not for automatically changing Skills or routing.
---

# Agent Feedback

Require the `agent-feedback` MCP server to be installed and configured. If its four `feedback_*` tools are unavailable, stop and report the setup gap; see [mcp-config.md](references/mcp-config.md).

1. If the Hermes automatic collector is enabled, let it import selections and tool results; do not create duplicate manual tasks for the same Hermes history. Use `feedback_report` to find imported task IDs, then add only independent artifact verification or reviewed labels.
2. For manual capture or another host, call `feedback_start` at task start and save `task_id`.
3. In manual capture, call `feedback_event` for observed selections, tool results, artifacts, verification, and integer `process_result.exit_code`.
4. Set `artifact_source=live` only after independently opening and checking the artifact. Use `imported` for historical oracle results.
5. Call `feedback_label` only for explicit user feedback or reviewed diagnosis. Never overwrite human labels with observed events.
6. Use `feedback_report` to inspect routing/execution/artifact/exit/outcome separately. Start triage with `priority="P0"`, then `priority="P1"`, `sort="priority"`, and `limit=100`; use `execution="fail"`, `has_tool_errors=true`, or `has_observed_label=true` for focused queues. `total` is the pre-filter task count and `filtered_total` is the filtered task count; finding counts are separate. Outcome is a human label or deterministic artifact＋exit rollup, not semantic quality assurance.

## Evidence rules

- Default to `unknown`; absence of errors is not success.
- Successful verification requires `source=observed/human`, `artifact_source=live/imported`, and non-empty objective evidence; self-report or unknown provenance is insufficient.
- Do not infer routing failure from tool failure or final task failure.
- Set `expected_selection` only from explicit reviewer truth.
- Never automatically edit descriptions, disable Skills, or alter routing.
- Store hashes and local references instead of secrets, raw sensitive messages, or unnecessary personal data.
