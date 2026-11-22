# P1 独立验证启动基线

## 已冻结

- 开发集：原 20 个会话、40 点，版本 `p1-r3-independent-review-adjusted`。
- 验证 cohort A：剩余 14/14 个会话、29 点；候选池 3,326 条消息。
- 会话交集：0；固定种子 20261116；规则仍冻结为 `hermes-message-segments-v2.2-three-fields`。
- 分层：new_task 10、assistant continuation 8、tool continuation 8、other continuation 3。
- 冻结清单元数据 SHA-256：`66ed507c824c5c52c9401b76f083aeb920d632656a184461688cee4455d660f1`。

## 尚未完成，不得写成验收通过

1. 29 点尚未标注、复核和评分；cohort A 当前是冻结盲标输入，不是测试结果。
2. 剩余历史会话没有 correction、child_event 或 cron 候选。 cohort B 必须来自后续新会话，补齐这些难例；不得从开发集借样。
3. 标注时必须展示完整消息与相邻上下文，长文包含结尾；记录 unknown 和理由。
4. 标签冻结后才运行评分，报告 P/R/F1、关系、任务根归属、无法判定、区间和覆盖差集。
5. 若修改规则，必须升级版本并另建验证集；不能在 cohort A 上边看结果边调参。
