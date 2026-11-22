# P3.1 判定语义修正与现场复验

## 修正内容

- outcome 不再复制 artifact。人工 outcome 标签优先；否则由 artifact＋exit 形成确定性 completion rollup。任一失败则失败，两者均通过才通过，其余保持 unknown。
- execution 仍单独报告中间工具失败，不被最终 completion 抵消。
- verification 新增 `artifact_source=live/imported/unknown`。隔离适配器默认把历史 P2 结果标为 imported；现场运行独立 oracle 后标为 live。
- PDF 禁则覆盖“导出 artifacts/output.pdf”等输出路径写法。
- real-08 必须明确提到 `not-present.docx`、承认缺失且不生成目标 PDF。
- real-03 明确验证要求的 CommentText 标记和 trackChanges。
- 结果分为 `route_artifact_input_pass` 与包含零退出的 `strict_task_pass`，不再使用含义模糊的 task_pass。
- 每条结果增加 provenance；污染扫描已包含 real-tasks-02.json。

## 实测

- 60/60 unittest 通过；独立 MCP stdio 4 工具链路通过。
- 黄金回放 34/34，33 条判定正确、1 条 unknown，覆盖率 97.0588%。
- 最终十项的隔离工作产物已复制回验证区，独立 oracle 现场重新打开并检查，不是读取旧 artifact_pass。
- 现场 artifact 10/10、route 10/10、输入未改 10/10、无污染 10/10、零退出 10/10、临时文件 0。
- P3 覆盖 10/10，缺失 0、额外 0、状态不一致 0，二次导入零新增。
- 所有 artifact 判定原因均为 `objective_verification_live`；所有 outcome 均为 `deterministic_artifact_exit_rollup`。

## 分布与边界

routing 为 1 pass／9 unknown；execution 为 3 pass／7 fail；artifact、exit、outcome 均为 10 pass。outcome 的通过只表示确定性产物＋退出组合通过，不声称完整语义质量、安全合规或全 Skill 路由正确。

真实 Hermes 持续接入、skill-up、MLflow 与插件产品化仍属于后续 P4 工作。
