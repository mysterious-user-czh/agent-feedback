"""End-to-end MCP stdio smoke test using the official SDK client."""
import asyncio
import os
import sys
import tempfile
from pathlib import Path

from mcp import Client, StdioServerParameters


async def main():
    with tempfile.TemporaryDirectory() as tmp:
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "agent_feedback.mcp_server"],
            env={**os.environ, "AGENT_FEEDBACK_DB": str(Path(tmp) / "mcp.db")},
        )
        async with Client(params, raise_exceptions=True) as client:
            tools = await client.list_tools()
            names = {t.name for t in tools.tools}
            assert names == {"feedback_start", "feedback_event", "feedback_label", "feedback_report"}, names
            started = await client.call_tool("feedback_start", {"agent": "mcp-test", "goal": "Verify MCP workflow"})
            task_id = started.structured_content["task_id"]
            await client.call_tool("feedback_event", {"task_id": task_id, "type": "selection", "payload": {"kind": "skill", "name": "demo", "source": "observed"}})
            await client.call_tool("feedback_event", {"task_id": task_id, "type": "verification", "payload": {"outcome": "success", "evidence": ["stdio integration test passed"], "source": "observed", "artifact_source": "live"}})
            labelled = await client.call_tool("feedback_label", {"task_id": task_id, "outcome": "success"})
            assert labelled.structured_content["saved"] is True
            observed = await client.call_tool("feedback_label", {"task_id": task_id, "outcome": "failure", "source": "observed"})
            assert observed.structured_content["preserved"] is True
            report = await client.call_tool("feedback_report", {"agent": "mcp-test", "response_format": "json"})
            data = report.structured_content
            if "result" in data:
                import json
                data = json.loads(data["result"])
            assert data["total"] == 1
            assert data["items"][0]["outcome"] == "success"
            print("MCP stdio OK: 4 tools; start → event → label → report passed")


if __name__ == "__main__":
    asyncio.run(main())
