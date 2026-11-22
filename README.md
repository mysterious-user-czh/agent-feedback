# agent-feedback

本地优先、跨 Agent 的反馈采集、确定性规则检测与证据复核工具。它记录 Skill 选择、工具执行、客观验证和人工复核结论，不会自动修改技能或路由。

当前版本：**0.11.1**（P4 最小产品闭环、Hermes 默认自动采集与可选 MLflow 集成）。

> Hermes v2.2 修复自动前导的增量身份稳定，并新增 P1 分层黄金集。静态归属完整不等于语义边界正确；本批人工复核的边界 F1 为 70%，不能把当前硬切段称为语义问题已解决。

## 组成

- Python 核心与 SQLite 存储，运行时依赖 `jsonschema`；
- 4 个 MCP stdio 工具：`feedback_start`、`feedback_event`、`feedback_label`、`feedback_report`；
- Hermes `state.db` 只读、增量、版本化消息段导入器，以及带双向覆盖审计的一次采集和持续 watcher；
- 实际参与加载的 JSON Schema、10 个示例合约与 34 条旧黄金案例；
- P0/P1/P2 候选报告，工具失败和取消独立统计；
- 20 会话、40 观测点的 P1 分层标签及完整指标；
- 可复制的 `skill/agent-feedback/SKILL.md`。

## 安装

需要 Python 3.10+。

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[mcp]"
```

Linux/macOS 使用 `.venv/bin/python`。默认数据库为 `~/.agent-feedback/feedback.db`，通过 `AGENT_FEEDBACK_DB` 指定其他位置；`AGENT_FEEDBACK_CONTRACTS` 指定合约 JSON。

## MCP 配置

```json
{
  "mcpServers": {
    "agent-feedback": {
      "command": "D:/path/agent-feedback/.venv/Scripts/python.exe",
      "args": ["-m", "agent_feedback.mcp_server"],
      "env": {
        "AGENT_FEEDBACK_DB": "D:/path/agent-feedback/data/feedback.db",
        "AGENT_FEEDBACK_CONTRACTS": "D:/path/agent-feedback/examples/contracts.json"
      }
    }
  }
}
```

将路径替换为实际绝对路径。

## 最小工作流

1. `feedback_start` 创建任务并保存 `task_id`。
2. `feedback_event` 记录 `selection`、`tool_result`、`artifact`、`verification` 或 `process_result`；后者必须带整数 `exit_code`。
3. `feedback_label` 保存人工反馈或复核结论。
4. `feedback_report` 生成 Markdown 或 JSON 报告。

`success` 必须先有非空客观证据、`source=observed/human` 且 `artifact_source=live/imported` 的成功验证事件；`self_reported` 或来源不明一律不能通过，证据不足时使用 `unknown`。工具失败不能单独证明路由错误或任务失败。

事件采用 append-only 存储，SQLite 触发器拒绝 UPDATE 和 DELETE。`observed` 和 `self_reported` 不能覆盖人工标签；修改人工标签必须提供 `reason`；相同标签不会重复写修订；旧标签自动迁移到 `label_revisions`。

## P3 三态评估

报告对 routing、execution、artifact、exit、outcome 分别输出 `pass / fail / unknown` 和机器可读原因。旧事件没有 `process_result` 时，exit 保持 unknown；没有客观 verification 时，artifact 和 outcome 保持 unknown。当前 execution 只表示是否观察到工具失败，恢复状态尚未完整识别，因此不是任务失败率，也不自动判 routing。

汇总包含各维度拒判率、unknown 原因覆盖率和按类型划分的 actual × predicted 混淆矩阵。unknown 不计入“判定后准确率”的分子或分母，但计入覆盖率分母；只有人工 outcome 或明确 expected_selection 等可靠标签才进入矩阵。unknown 原因覆盖率只表示拒判有类别，不是根因识别准确率。

运行 `.venv/Scripts/python evaluation/p3/replay.py` 可复算 34 条公开黄金案例。实测 34/34 覆盖，33 条判定全部正确、1 条 unknown；不计算 Top-1，因为该集合没有唯一最佳选择标签。结果位于 `evaluation/p3/`。

隔离 Hermes 批次可自动导入真实运行记录和独立 oracle：

```bash
agent-feedback --db validation/BATCH/p3-feedback.db --contracts examples/contracts.json import-isolated validation/BATCH evaluation/p2/real-tasks-02.json
agent-feedback --db validation/BATCH/p3-feedback.db --contracts examples/contracts.json report --format markdown
```

适配器核对 raw／result 的 run_id、case 和退出码，稳定事件 ID 保证重复导入零新增；stream-json 工具结果也全部入库，取消与普通失败分开。最终十项实测已覆盖 10/10，artifact／exit／outcome 均为 10/10 pass；execution 为 3 pass／7 fail（仅表示观察到工具失败，不等于任务失败），routing 为 1 pass／9 unknown，不把高拒判率隐藏为成功。

## Hermes v2.2 切段模型

| 字段 | 合法值 | 含义 |
|---|---|---|
| `segment_type` | `task / ambiguous` | 当前段是任务本体还是有明确原因的结构歧义 |
| `event_source` | `user / background / delegation / cron` | 消息来自哪里 |
| `relation` | `new_task / continuation / correction / child_event` | 消息与当前任务是什么关系 |

冻结规则：

1. 非自动真实用户消息通常以 `new_task` 开启任务；会话首条人类消息即使含纠正关键词，也开启 `task`。
2. 已有人类任务时，命中纠正规则且不是重复初始消息的消息以 `correction` 归入当前任务，纠正候选也标注当前任务。
3. assistant/tool 和普通后台消息为 `continuation`；委派通知为 `child_event`。
4. 自动前导并入随后第一个人类任务；整个会话没有人类消息时，自动内容独立形成 `task`。
5. 自动开头的段固定使用首条消息 ID。第一次只有自动 envelope、之后才出现人类消息时，任务身份不变，只把目标更新为真实请求。
6. 每段首条消息只能是 `new_task` 或 `child_event`。`ambiguous` 必须有 `ambiguous_reason`；完全无法识别消息角色的会话有显式 fallback。已知会话中的 `session_meta` 等元数据继续归入当前段，不误判整段歧义。
7. cron 识别先于通用 `[IMPORTANT:` 后台 envelope。
8. 不使用语义模型猜测 continuation。普通用户消息仍硬切段，黄金集已实测出过度切段与纠正误判。
9. `schema_metadata` 记录 `hermes-message-segments-v2.2-three-fields`。

规则集中在 `src/agent_feedback/segment_rules.py`，导入器和基线共同引用。结构断言与人工内容标签是两类不同证据：前者检查字段不变量，后者才能发现规则本身的语义问题。

### 导入与升级

```bash
agent-feedback --db data/feedback-v062.db --contracts examples/contracts.json import-hermes "C:/Users/name/AppData/Local/hermes/state.db" --hours 24
agent-feedback --db data/feedback-v062.db --contracts examples/contracts.json report --format markdown
```

**v0.4／v0.5／v0.6.0／v0.6.1 数据库都不能直接沿用。** 旧规则标签不能与新规则混用，导入器会明确拒绝，必须使用新数据库。

导入器只读打开 Hermes 数据库，默认排除子会话，支持老会话增量补扫。结构化 `success=true` 不算失败；`exit_code=130` 记录为取消。

### Hermes 默认自动采集

```bash
agent-feedback --db data/feedback.db --contracts examples/contracts.json collect-hermes "C:/Users/name/AppData/Local/hermes/state.db"
agent-feedback --db data/feedback.db --contracts examples/contracts.json watch-hermes "C:/Users/name/AppData/Local/hermes/state.db" --interval 60
```

`collect-hermes` 导入一次并独立枚举源库基线；只有会话、消息、Skill 选择、结构化工具错误的缺失与额外差集均为 0，且解析失败为 0，才返回成功，否则退出码为 2。`watch-hermes` 顺序执行同样的采集与审计，最短间隔 5 秒，异常落盘并等待下一轮，不紧循环重试。状态写入 `collector-status.json`，历史追加到 `collector-history.jsonl`。

一键 Hermes 包默认每 60 秒运行该 watcher；它是周期性只读增量采集，不是 Hermes 内部实时 hook。自动采集只覆盖选择、工具结果和结构证据，不自动推断 routing 真值或产物成功。

## 合约与报告

当前只有 10 个示例合约，具体名称以 `examples/contracts.json` 为准。

- 强制场景未选、禁用场景误选：P1；
- 同段选择次数超过明确上限：P2 候选；
- 同段多个不同 Skill：P1 复核信号；
- 人工确认失败：P0；
- 疑似用户纠正：当前任务的 P1 候选；
- 工具失败和取消：只统计，不自动生成 finding。

“无发现”不代表成功。JSON Schema 使用正确的 Draft 2020-12 地址并实际参与加载；另拒绝重复 Skill 和非法正则。输出规则尚未启用自动产物检查。

## 测试与全量验收

```bash
.venv/Scripts/python -m unittest discover -s tests -v
.venv/Scripts/python tests/test_mcp_stdio.py
```

本版实际结果：

- **81 项 unittest 全部通过**（含 P3、隔离采集、SessionResult、脱敏跟踪与最新验证冲突测试）；另有 **1 项独立手工 MCP stdio 脚本通过**，不计入 unittest；
- 旧黄金案例 **34/34**，与 v0.6.0 逐字节相同；示例合约 **10/10**；
- 最新真实库副本完整枚举 250 会话、12,122 消息；默认范围排除 199 个子会话和 6 个空主会话；
- **已覆盖 45/45 非空主会话、7,864/7,864 消息、71/71 选择、266/266 工具失败、14/14 取消，合计 280/280 异常结果；差集 0，parse_failures=0**；
- 创建 423 个任务段，source_started_at 回填 423/423；完整合约下为 21 个 P1 任务、22 条 P1 finding；
- 第二次导入新增消息、选择、失败、取消、纠正候选均为 0；watcher 2/2 轮通过；
- 7 个纠正候选与工具失败数前 10 个任务已人工复核 17/17：6 个确认真问题任务（聚合为 5 个底层问题）、4 个误报、7 个需更多证据。

报告仍有 9 条多技能和 6 条纠正正则候选，只供人工复核，不能自动归因。1275／1382 虽为重复内容，在消息关系上仍是对前序任务的纠正；6937／6986 是粘贴评审，8835 是复述，不应仅凭正则判为 correction。

## P1 分层黄金集

交付目录：`evaluation/p1/`。

- 先完整枚举 34 个非空主会话、6,793 条消息；
- 固定种子 20261115 选取 20 个会话，每个会话至少 1 点；
- 共 40 点：新任务 10、纠正 6、委派子事件 8、assistant 延续 8、tool 延续 8；
- 会话覆盖 20/20，标注覆盖 40/40，差集为 0。

| 指标 | 实测 | 95% 置信区间 |
|---|---:|---:|
| 边界 TP／FP／FN／TN | 7／3／3／27 | — |
| Precision | 7/10（70%） | 39.7%–89.2% |
| Recall | 7/10（70%） | 39.7%–89.2% |
| F1 | 70% | 37.5%–100% |
| 关系准确率 | 34/40（85%） | 70.9%–92.9% |
| 任务归属准确率 | 32/40（80%） | 65.2%–89.5% |
| 无法判定比例 | 实测 0/40 | 本批没有歧义黄金例 |

黄金正边界为 10 个（TP+FN），预测正边界也是 10 个（TP+FP）；40 是全部观测点数。Precision／Recall／准确率使用 Wilson score 区间；F1 使用按会话整组 bootstrap（10,000 次，种子 20261115）。区间不覆盖标注或会话选择偏差。

在交付根目录运行 `python evaluation/p1/score.py`，仅用 Python 标准库即可从 `golden.json` 与脱敏的 `predictions.json` 重建 `metrics.json` 和 `metrics.md`。无法判定由预测中的 unknown／ambiguous／无归属段逐条实算，不是硬编码。

全部 8 条差异见 `evaluation/p1/metrics.md`。主要问题是：“第一个方向”等延续被切成新任务；粘贴评审被正则误判为纠正；部分纠正虽关系判对，但前序任务已经切错。

标注由同一 Agent 逐条阅读内容和相邻轮次完成，**不是人类标注**。随后由未参与此前标注的只读复核者独立检查 40 条标签及原 7 条差异：原差异全部认可，全部标签同意 39/40；新增消息 8846 的归属修正，使差异总数由 7 增至 8。详见 `evaluation/p1/independent-review.md`。这**不是隔周盲标、人际一致性或独立测试集**，最早有效隔周复标日期为 2026-11-22。

这 40 点冻结为**开发／诊断集**，会话分布集中，不能外推为全库总体性能，也不能同时用于调参和泛化声明。本批没有歧义黄金例，0% 不能证明歧义检测有效。后续语义改进和防过拟合约束见 `evaluation/p1/segmentation-improvement-freeze.md`。

## P1 会话隔离验证 cohort A

剩余 14/14 个历史会话、29/29 点已完成主 Agent 标注，与开发集会话交集为 0。v2.2 实测边界 TP／FP／FN／TN 为 4／6／0／19，Precision 40%、Recall 100%、F1 57.1%，关系与任务归属准确率均为 23/29（79.3%）。6 条差异全是把延续或纠正切成新任务。

这说明开发集 70% F1 不能外推。验证集仅有 4 个正边界，且没有 correction、child_event、cron 候选；区间很宽，缺类仍需后续 cohort B。标签尚无独立人员复核，本轮未根据验证结果修改算法。详见 `evaluation/p1-validation/`。

## P2 首批同 harness 用例

首批 5 条用例各运行 3 次，**已覆盖 15/15，缺失 0**。隔离 HOME、冻结技能副本、fixture 哈希、原始轨迹和导出记录保存在验证区，公开包只放脱敏结果。路由通过 6/15，产物／失败证据通过 4/12 个适用运行，退出码为 0 仅 3/15，路由、执行、产物和退出码全部满足为 **0/15**。本批完成证据闭环，但功能验收未通过；详见 `evaluation/p2/`。

## 已验证的隔离接口

此前已验证 `chat --oneshot --format stream-json` 与 `sessions export --format jsonl` 能取得完整工具轨迹，隔离 spike 未留下进程。`-z` 在当前安装会触发 gateway 冲突，不能声称直接可用。该 spike 不证明自动路由质量，也不等于持续实时接入完成。

## 实验性能力禁则

`agent_feedback.routing_policy.denied_skills(query)` 只根据明确能力边界输出需要排除的技能，不推断 Top1，也不读取 case ID。传入 `base_dir` 时，它还会对查询中显式引用、但实际不存在的 fixture 文件执行 Office／DOCX 技能前置禁则；未显式引用文件时不猜测缺失。它用于隔离 HOME 的物理禁则实验，尚未接入真实 Hermes，不能替代完整语义路由。规则见 `src/agent_feedback/routing-policy.json`。

`validation/` 可能包含凭据副本、原始查询、会话 ID 和绝对路径，已加入 `.gitignore`；不得打包、提交或公开。对外只提供脱敏汇总。运行沙箱位于项目仓库外，只复制 fixtures 和空 artifacts，并检查是否读取评测清单。

## 当前边界

P1 会话隔离验证 F1 57.1% 仍未达到语义边界目标。candidate-10 的最终本地 fixture 批次已实测 10/10 严格通过，route／artifact／exit 均为 10/10，且输入、来源、污染、临时文件和进程检查通过；详见 `evaluation/p2/candidate-10-final-review.md`。该结果只适用于隔离副本，真实 Hermes 尚未接入自动禁则，每项最终仅一次，不能外推长期稳定性。

P3.1 最小闭环已修正：当前 0.11.1 回归为 **81 项 unittest 全部通过**，独立 MCP stdio 全链路、34/34 黄金回放及真实隔离运行 10/10 逐项核对均已通过。选择、66 条结构化工具结果和退出码可自动采集；最终十项产物已由独立 oracle 现场重新打开验证，标记为 live。五维分别输出 pass／fail／unknown，但 outcome 只是人工标签或 artifact＋exit 的确定性 completion rollup，不是完整语义质量判断。真实批次中 routing 为 1 pass／9 unknown，execution 为 3 pass／7 fail，artifact／exit／outcome 均为 10 pass。7 次 execution fail 只表示存在中间工具失败，不能抵消最终任务成功；routing 标签覆盖仍有限。

## P4 最小产品闭环

已实测完成单任务事后采集、统一事件契约、可分发 Skill 引导包、skill-up 0.16.0 custom local engine、真实失败转回归用例和可选本地 MLflow 脱敏存证。真实图片压缩失败新鲜复现 **2/2**，修复后同例 **3/3 PASS**，正常正文编辑对照 **1/1 PASS**；MLflow 3.18.0 可按来源哈希和版本字段找回 before=`ERROR`、after=`PASS` 两条脱敏结果。干净通用 Host 已从 wheel 非 editable 安装并完成 Skill、MCP 与 SessionResult 全链路验收，受控 TEMP 残留 0。通用 `SessionResult` 导入及确定性参考 engine 也已验证，但参考程序不是第二真实 LLM Agent。详见 `evaluation/p4/`。

0.11.1 将三者接成同一证据链：真实队列人工复核 **17/17**；T03 教学示例误报在冻结 before 中复现 **2/2**，修复后 **0/3**，正常纠正对照 **1/1** 保留；原始 SessionResult 与独立 oracle 回导 **6/6**，二次导入零新增。MLflow 实测 **1 个父 run＋6 个嵌套子 run**，仅保存脱敏状态、计数和来源／配置／源码／fixture／oracle 哈希。该闭环只证明一个确定性纠正识别缺陷被修复，不外推为全 Skill 路由或模型质量结论。

仍未完成：隔周盲标、cohort B、真实 Hermes 持续实时 hook、第二真实 LLM Agent、通用语义输出／安全检测、全 Skill Top1 和完整工作流状态机。skill-up 当前只声明 local／batch／单轮；具体模型身份、token 与金额信息不足，保持 unknown。failproofai 本版不采用，不影响事后证据与回归主闭环。
