# P4 事件契约 v1（冻结）

## 身份与不可变性

- `task_id`：一次可独立验收的任务；同一 run 重导保持稳定。
- `external_id`：来源类型＋run_id；不得使用“最新会话”猜测归属。
- `event_id`：来源＋run＋事件类型＋来源事件键；重复导入不得新增。
- 原始事件只追加；标签修订另存历史，observed 不覆盖 human。
- run、case、session、退出码冲突时拒绝导入，不自动修补。

## 事件与字段

| 事件 | 必填字段 | 状态／来源 |
|---|---|---|
| selection | kind、name、source | kind=skill/tool/agent/workflow |
| tool_result | name、status、recovered、source | success/failure/cancelled；exit 130=cancelled |
| artifact | name、reference/sha256、source | 只声明产物，不证明合格 |
| verification | outcome、evidence、source、artifact_source | artifact_source=live/imported/unknown |
| process_result | exit_code、source | 整数；124=timeout，非零不隐藏 |
| label | outcome、failure_stage、expected_selection、source、comment | human 需保留修订原因和历史 |

verification success 必须有非空客观证据、`source=observed/human`，且 `artifact_source=live/imported`；`self_reported` 或来源不明不能通过。最终文本自我宣称不是 live verification。历史 P2 `artifact_pass` 只能标 imported；现场重新打开并检查产物才标 live。

## 五维判定

- routing：可靠合约或人工选择真值；否则 unknown。
- execution：当前采集器尚未完整识别恢复状态，因此只表示“观察到工具失败／未观察到工具失败”，不是任务失败率；无证据或仅取消为 unknown。
- artifact：最近一次有效 verification；保留 artifact_source。
- exit：最近 process_result；0 pass，其余 fail，缺失 unknown。
- outcome：人工 outcome 优先；否则 artifact＋exit 的确定性 completion rollup。它不是完整语义质量或安全结论。

五维独立报告。execution fail 不自动导致 routing fail，也不抹去最终 artifact／exit 证据。

## skill-up 映射

| skill-up | agent-feedback |
|---|---|
| SessionInput.case_id＋variant＋调用序号 | external run identity |
| SessionResult.session_id | 来源会话标识，仅本地保存 |
| transcript 中 skill_view | observed selection |
| transcript tool 结果 | tool_result；按结构化状态分类 |
| artifacts.files／generated_files | artifact 声明，仍需 judge |
| script judge 现场检查结果 | verification，artifact_source=live |
| SessionResult.exit_code | process_result；timeout=124 |
| 人工复核 | label，source=human |

新 skill-up 用例以 `judge: script` 为权威判定。旧 contracts 和 34 条黄金案例只作 legacy 回归，不与新 judge 合并成第二套并行结论。缺失映射保持 unknown。

local 为当前唯一必需 transport；http、多轮 stateful 和 OTLP 都是后续可选映射，未完成前不得宣称支持。
