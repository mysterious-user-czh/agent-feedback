# MCP configuration

Install Python 3.10+ and the package with MCP support, then register this server in the host Agent. Replace the placeholders with absolute local paths.

```json
{
  "mcpServers": {
    "agent-feedback": {
      "command": "<PYTHON>",
      "args": ["-m", "agent_feedback.mcp_server"],
      "env": {
        "AGENT_FEEDBACK_DB": "<LOCAL_DATA_DIR>/feedback.db",
        "AGENT_FEEDBACK_CONTRACTS": "<PACKAGE_DIR>/examples/contracts.json"
      }
    }
  }
}
```

The server exposes `feedback_start`, `feedback_event`, `feedback_label`, and `feedback_report`. Requires `agent-feedback-local` 0.11.2 with the trusted P3.1 event protocol and `mcp>=1.12,<3`. Keep the database in a host-approved local data directory. Do not reuse pre-0.6 segmented databases.

For skill-up custom engine runs, use the project `integrations/skillup/evals/eval.yaml`; its required environment variables are documented in the project installation guide. The Skill itself does not install Hermes, skill-up, credentials, or host hooks.
