# P3 隔离 Hermes 真实运行采集验证

## 结论

P3.1 最小闭环已修正并完成现场复验：选择、工具结果、独立产物 oracle 和进程退出码均可从隔离 Hermes 实际运行自动采集，并生成五维度三态报告。outcome 是人工标签或 artifact＋exit 的确定性 completion rollup，不再复制 artifact。

使用 `real-tasks-07-final` 的 10 条实际运行，已覆盖 **10/10**，缺失 0、额外 0、artifact／execution／exit 状态不一致 0；第二次导入所有事件新增 0。

## 采集内容

- 每条运行生成稳定任务 ID，并核对 raw／result 的 run_id、case 和退出码。
- 技能选择转为 observed selection。
- stream-json 的 66 条实际 tool_result 全部入库；14 条失败、0 条取消。exit_code=130 单列取消，不算普通失败。
- 独立 oracle 转为 verification；不采用 Agent 自我宣称。
- 实际退出码转为 process_result。

## 实际 P3 汇总

| 维度 | pass | fail | unknown | 拒判率 |
|---|---:|---:|---:|---:|
| routing | 1 | 0 | 9 | 90% |
| execution | 3 | 7 | 0 | 0% |
| artifact | 10 | 0 | 0 | 0% |
| exit | 10 | 0 | 0 | 0% |
| outcome | 10 | 0 | 0 | 0% |

execution 的 7 次 fail 表示观察到工具失败，不等于任务失败或路由错误；这些运行最终产物和进程退出仍全部通过。routing 高拒判是因为多数任务没有可靠唯一选择标签或命中合约，不能用结果成功倒推路由正确。

## 完成边界

本轮完成的是确定性 P3：三态、拒判、分类型矩阵、五维独立判断、幂等采集和真实运行回放。Top-1 仍只在可靠标签存在时评分；本批没有人工标签，因此混淆矩阵为空，不虚构准确率。

真实 Hermes 持续实时接入、通用语义输出／安全检测和完整工作流状态机不属于本次已完成范围。原始数据库及含会话标识的报告只留在本地 validation，不打包、不公开；真实配置、技能、cron、数据库原件未修改。
