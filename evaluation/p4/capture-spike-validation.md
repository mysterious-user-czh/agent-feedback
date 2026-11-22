# P4.0 真实采集 spike

## 选定路径

采用现有 `hermes chat --cli --oneshot --format stream-json` 加 `sessions export --format jsonl`。它能同时提供结构化工具结果、会话导出、技能选择和退出码，因此本轮不启动 ACP 对照。

## 通过批次

`p4-capture-spike-02`：一个文本复制任务，预算 8 turns、300 秒。

- 运行 1/1；stream 事件 80；导出非空。
- 未选择 Skill，符合本任务冻结预期；P3 routing 仍按通用规则保持 unknown，不用单个预期冒充全 Skill Top1。
- 工具结果 2 条，失败 0、取消 0，execution pass；这里只表示未观察到工具失败，不声称完整识别恢复状态。
- 独立现场打开 output.txt 并逐字验证，artifact live pass。
- 退出码 0，exit pass；outcome 为 artifact＋exit rollup pass。
- 真实 config、技能树、cron、state.db 及 WAL／SHM 前后哈希全部一致。
- candidate-10 来源技能树不变，隔离进程残留 0。

## 首次不确定对照

首次 `p4-capture-spike` 的功能采集通过，但真实 state.db WAL／SHM 哈希变化，主数据库、配置、cron 和技能未变。随后 10 秒无任务对照无变化，第二次独立采集全部不变。首次变化无法归因，故不把它算作零写入通过，也不掩盖；最终只采用第二批次的通过证据。

## 边界

这证明单任务事后自动采集链路，不等于真实 Hermes 持续实时接入。原始轨迹和数据库仅保留在本地 validation，公开报告不包含会话 ID、原始消息或绝对路径。
