# Agent Skills Feedback

仓库名：`agent-skills-feedback`。本地优先的 Agent Skill 使用反馈与证据复核工具。它记录技能选择、工具执行、产物验证、进程退出和人工复核结论，帮助回答“这次为什么失败、应该检查哪里”。

> 为保持现有安装兼容，Python 包、命令、Skill 目录和 MCP 注册名仍使用 `agent-feedback`；变更的是项目展示名与 GitHub 仓库名。

当前版本：**0.12.0**。新增本机人工审核台、全库搜索、静态文件白名单、Windows 双击启动与桌面快捷方式；项目展示名改为 Agent Skills Feedback，原有技术标识保持兼容。

项目提供面向多 Agent 的开放事件协议和通用 `SessionResult` 导入。**目前完成真实宿主验收的是 Hermes**；确定性参考 engine 只证明接口可复用，不是第二个真实 LLM Agent。

## 能做什么

- 通过 4 个 MCP 工具记录任务、事件、复核标签并生成报告。
- 只读导入 Hermes `state.db`，支持老会话增量补扫和重复导入去重。
- 分别报告 routing、execution、artifact、exit、outcome，证据不足时输出 `unknown`。
- 将已复核失败转成 skill-up 回归用例，并可选写入本地 MLflow。
- 提供本机人工审核台、Windows 双击启动器、Hermes 一键安装包、通用 Skill 引导包和 Python wheel。

## 明确边界

- 不自动修改技能、描述或路由，也不自动选择所谓 Top1 Skill。
- 自动采集是可选的周期性只读 watcher，不是 Hermes 内部实时 hook。
- 工具失败不自动等于路由错误或任务失败；没有可靠路由真值时保持 `unknown`。
- 产物通过必须来自独立验证；`outcome` 不是完整的语义质量或安全审核。
- 0.11.1 的 T03 闭环只证明一个确定性纠正识别缺陷被修复，不能外推到全部 Skill 或模型质量。

## 下载与安装

### Hermes Windows 一键包

从 [v0.12.0 Release](https://github.com/mysterious-user-czh/agent-skills-feedback/releases/tag/v0.12.0) 下载 `hermes-agent-feedback-plugin-v0.12.0.zip`，解压后在包目录运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
```

安装需要 Python 3.10+ 和联网获取依赖。脚本不会覆盖已有同名 Skill 或 MCP；默认启动每 60 秒运行一次的本地采集器，但不创建开机启动项。升级、状态检查、停止和保留数据卸载见 [Hermes 一键包说明](packaging/hermes-plugin/README.md)。

### 从源码安装

```bash
git clone https://github.com/mysterious-user-czh/agent-skills-feedback.git
cd agent-skills-feedback
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[mcp]"
```

Linux／macOS 使用 `.venv/bin/python`。这是面向开发者的 editable 安装；普通宿主集成、MCP 配置、skill-up 和 MLflow 的完整步骤见 [安装、集成与卸载](docs/installation.md)。

默认数据库为 `~/.agent-feedback/feedback.db`。生产使用建议显式设置：

- `AGENT_FEEDBACK_DB`：反馈数据库路径；
- `AGENT_FEEDBACK_CONTRACTS`：合约 JSON，例如 `examples/contracts.json`。

## 本地人工审核台

Windows 完成源码安装后，双击根目录的 `Start Agent Skills Feedback.cmd`。启动器读取 `AGENT_FEEDBACK_DB`，未设置时读取 Hermes 一键包的 `install.json`，最后尝试 `~/.agent-feedback/feedback.db`；不会创建或覆盖真实数据库。服务就绪后自动打开 `http://localhost:7100/`，重复双击会复用已有服务。

也可以在 PowerShell 指定数据库和端口：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-review.ps1 -Database "D:\path\feedback.db" -Port 7100
```

双击 `Stop Agent Skills Feedback.cmd` 停止由启动器管理的服务。审核台只监听本机，提供队列、证据详情、三类人工结论、修订历史和前后对照；不需要 Node.js 或公开部署。`review-ui/` 另保留 `npm run dev` 演示模式，默认使用隔离演示库，不用于真实审核。

## 最小工作流

1. `feedback_start` 创建任务并保存 `task_id`。
2. `feedback_event` 记录 `selection`、`tool_result`、`artifact`、`verification` 和 `process_result`。
3. 独立打开并检查产物后，才能使用 `artifact_source=live`；历史 oracle 结果使用 `imported`。
4. `feedback_label` 保存人工复核结论；自动观察不能覆盖人工标签。
5. `feedback_report` 查看分维结果，先处理 P0，再复核 P1 候选。

可直接运行公开示例：

```bash
.venv/Scripts/python examples/basic_usage.py
```

该示例只演示事件记录和报告生成，**不会真的转换 Word 文档**。生成的事件使用 SQLite append-only 存储；成功标签必须有带客观证据的合格验证，不能仅凭 Agent 自称完成。

## 报告怎么看

| 维度 | 回答的问题 |
|---|---|
| routing | 是否有可靠证据证明选择正确或错误 |
| execution | 是否观察到工具失败；不等同于最终任务失败 |
| artifact | 产物是否经过独立验证 |
| exit | 是否记录进程退出码，以及是否为零 |
| outcome | 人工结论，或 artifact＋exit 的确定性汇总 |

每个维度独立输出 `pass / fail / unknown`。`unknown` 表示证据不足，不计入“判定后准确率”，但计入覆盖率分母。“没有发现”也不代表任务成功。

当前附带的 10 个 JSON 合约只覆盖示例场景；强制场景、禁用场景和选择次数上限必须按实际技能补充。P0 是人工确认失败，P1 是需要复核的触发或证据冲突，P2 是已定义执行规则的候选。

## Hermes 自动采集

```bash
agent-feedback --db data/feedback.db --contracts examples/contracts.json collect-hermes "C:/Users/name/AppData/Local/hermes/state.db"
agent-feedback --db data/feedback.db --contracts examples/contracts.json watch-hermes "C:/Users/name/AppData/Local/hermes/state.db" --interval 60
```

每轮独立枚举源库基线，核对会话、消息、Skill 选择和结构化工具错误；缺漏、额外记录或解析失败都会使当轮失败。默认排除子会话，老会话新增消息会补扫，重复导入不会重复计数。

“Hermes 消息切段规则 v2.2”是本项目导入器的规则版本，不是 Hermes 产品版本。规则能稳定覆盖结构，但语义边界仍有误差；开发集与隔离验证指标详见 [P1 开发集](evaluation/p1/README.md) 和 [P1 隔离验证](evaluation/p1-validation/README.md)。

## skill-up 与 MLflow

项目包含 skill-up 0.16.0 的 custom local engine 示例，当前只声明 local／batch／单轮链路。MLflow 是可选依赖，只允许本地 `file:` 跟踪地址；保存脱敏状态、计数和哈希，不保存提示、回复、原始轨迹或凭据。

配置与命令见 [安装文档](docs/installation.md)，冻结用例见 [skill-up 集成目录](integrations/skillup/evals/eval.yaml)。

## 测试与公开证据

```bash
.venv/Scripts/python -m unittest discover -s tests -v
.venv/Scripts/python tests/test_mcp_stdio.py
```

0.12.0 发布前实测：**90/90 unittest 通过**，独立 MCP stdio 4 工具全链路通过；审核台已在浏览器验证三类写回、全库搜索、前后对照和窄屏布局，Windows 启动器已验证真实库连接、重复启动复用与停止。

历史验收不冒充当前泛化结论：

- [0.11.1 最终验收与适用范围](evaluation/p4/final-validation.md)
- [0.11.1 发布完整性审计](evaluation/p4/final-audit-v0111.json)
- [P3 确定性黄金回放](evaluation/p3/replay-report.md)
- [P2 隔离任务与历史失败](evaluation/p2/README.md)

原始提示、响应、轨迹、会话数据库和 `validation/` 不公开；公开评估只保留脱敏结果。

## 目录

- `src/`：Python 核心、SQLite、MCP 和导入器；
- `skill/`：宿主 Agent 的 Skill 引导；
- `examples/`：可运行示例、示例合约和当前报告样例；
- `integrations/`：skill-up custom engine 与冻结用例；
- `evaluation/`：脱敏评估结果和适用范围；
- `packaging/`：Hermes Windows 一键安装脚本。

## License

[MIT](LICENSE)
