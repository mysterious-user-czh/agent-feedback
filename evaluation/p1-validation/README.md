# P1 会话隔离验证 cohort A

## 覆盖与标注

- 与 40 点开发集会话交集为 0；覆盖剩余 14/14 个历史会话。
- 29/29 点已标注，黄金正边界 4 个，预测正边界 10 个。
- 主 Agent 阅读完整消息与相邻上下文完成标注，尚无独立人员复核；不是人际一致性证据。
- 剩余历史会话无 correction、child_event、cron 候选，缺类仍需 cohort B。

## v2.2 实测

| 指标 | 结果 | 95% 区间 |
|---|---:|---:|
| 边界 TP／FP／FN／TN | 4／6／0／19 | — |
| Precision | 40% | 16.8%–68.7% |
| Recall | 100% | 51.0%–100% |
| F1 | 57.1% | 0%–100% |
| 关系准确率 | 23/29（79.3%） | 61.6%–90.2% |
| 任务归属准确率 | 23/29（79.3%） | 61.6%–90.2% |
| 无法判定 | 实测 0/29 | 无歧义黄金例 |

六条差异全部为把延续／纠正切成新任务，包括选项确认、压缩摘要、重跑纠正、方案接受和同图追问。开发集 F1 70% 不能外推；独立集只有 4 个正边界，区间很宽，不能反过来宣称精确总体性能。

按冻结纪律，本轮不根据这 29 点修改算法。后续语义规则需升级版本，并用新的会话验证。

运行复现：

```bash
python evaluation/p1/score.py --golden evaluation/p1-validation/golden.json --predictions evaluation/p1-validation/predictions.json --output-dir evaluation/p1-validation
```
