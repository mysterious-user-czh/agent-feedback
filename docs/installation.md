# 安装、集成与卸载

## 核心与 MCP

要求 Windows／Linux／macOS、Python 3.10+。在交付目录执行：

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[mcp]"
.venv/Scripts/python -m unittest discover -s tests
.venv/Scripts/python tests/test_mcp_stdio.py
```

Linux／macOS 使用 `.venv/bin/python`。将 `skill/agent-feedback` 复制到宿主 Agent 的 Skills 目录，并按该目录中的 `references/mcp-config.md` 注册同名 MCP server：`agent-feedback`。不要写成 `agent_feedback_mcp`。

支持版本：当前包 0.11.1 的事件协议，Python ≥3.10，`mcp>=1.12,<3`。数据库默认 `~/.agent-feedback/feedback.db`，生产使用显式 `AGENT_FEEDBACK_DB`。旧版切段数据库不能直接复用。

## Hermes 自动采集

```bash
agent-feedback --db <FEEDBACK_DB> --contracts <CONTRACTS_JSON> collect-hermes <HERMES_STATE_DB>
agent-feedback --db <FEEDBACK_DB> --contracts <CONTRACTS_JSON> watch-hermes <HERMES_STATE_DB> --interval 60
```

默认排除子会话；重复运行零重复，老会话新增消息会补扫。每轮独立枚举源库并核对会话、消息、Skill 选择和结构化工具错误的双向差集；缺漏、额外记录或解析失败均不能报告成功。这是周期性只读采集，不是实时 hook，也不自动判断 routing 真值或最终产物质量。Windows 一键包的安装、状态、停止和保留数据升级见 `packaging/hermes-plugin/README.md`。

## 可选本地 MLflow

MLflow 不是核心或 MCP 的运行依赖。只在项目虚拟环境中按需安装：

```bash
.venv/Scripts/python -m pip install -e ".[mlflow]"
agent-feedback track-skillup <RESULT_JSON> --tracking-uri file:///<LOCAL_TRACKING_DIR> --artifact-root <LOCAL_ARTIFACT_DIR> --experiment agent-feedback --code-version 0.11.1 --metadata '{"candidate":"after","config_hash":"<HASH>","skill_tree_hash":"<HASH>","model_version":"unknown"}'
```

只允许 `file:` 跟踪地址，拒绝 http／https 和远程 `file://host/...`，避免误上传。保存内容为脱敏状态、指标、版本字段和布尔 judge 检查，不保存 prompt、response、transcript、session_id、原始错误或凭据。token 未采集时保持 unknown，不把 0 当成零消耗。

MLflow 3.18+ 默认限制文件存储；`track-skillup` 只在自身进程内临时启用并在结束后恢复原环境变量。若用其他脚本直接读取该 file store，需要在该读取进程设置 `MLFLOW_ALLOW_FILE_STORE=true`，不要写入系统级环境配置。

## Hermes 与 skill-up custom engine

项目内已验证 skill-up 0.16.0 Windows amd64。运行前设置：

- `AGENT_FEEDBACK_ROOT`：项目根目录；Windows Git Bash 下用 `/d/...` 形式。
- `AGENT_FEEDBACK_PYTHON=python`。
- `AGENT_FEEDBACK_HERMES_TEMPLATE`：隔离 Hermes Home 模板。
- `AGENT_FEEDBACK_HERMES_BIN`：Hermes CLI 绝对路径。
- `AGENT_FEEDBACK_HERMES_ENV_FILE`：现有 Hermes `.env`，只读复制并过滤消息平台凭据。

然后执行：

```bash
skill-up validate integrations/skillup/evals/eval.yaml
skill-up run integrations/skillup/evals/eval.yaml --output-dir <LOCAL_VALIDATION_DIR> --no-delete
```

当前只声明 local／batch／单轮最小链路。http、stateful 多轮、OTLP 和自动实时 hook 尚未验收。产物由适配器显式列出，PowerShell script judge 现场检查。

## 卸载

1. 从宿主 Agent 移除 `agent-feedback` MCP 配置和复制的 Skill 目录。
2. 停止该宿主中正在运行的 MCP 会话。
3. 删除项目自己的 `.venv`、数据目录和验证目录；保留需要审计的报告。
4. 不删除或修改 Hermes 原有配置、技能、cron 和数据库。

安装和卸载均不需要暂停真实 Hermes，也不会自动改技能或路由。
