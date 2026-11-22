# 第二 engine 契约复用验证

## 实测

- 确定性参考 engine 通过同一 skill-up 文本复制用例：**1/1 PASS**。
- 同一 `SessionResult` 导入器成功建立工具、产物、独立验证和退出事件；二次导入新增 **0**。
- 五维状态：routing=`unknown`，execution／artifact／exit／outcome=`pass`。没有技能选择证据时不虚构路由成功。
- CLI `import-session` 已实际运行成功。

## 必须保留的边界

本机 PATH 未发现 Claude、Codex 或 Kimi CLI。本次使用的是**确定性参考程序，不是第二个真实 LLM Agent**。它证明输入输出契约、judges 和核心映射可以复用，不证明第二真实 Agent 的路由、技能加载或语义行为。

证据：`reference-engine-validation.json`、`validation/skillup-reference-contract01/` 和 `validation/reference-session/`。公开结果不包含原始提示词、回复、轨迹或数据库。
