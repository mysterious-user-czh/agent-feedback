# 2026-11-18 复核清单完成汇总

## 执行覆盖

复核要求的流程已全部执行，未增加 cohort、P3／P4 或跨 engine。完成功能验收不等于所有任务通过：最终 10 项为 **8/10**，剩余差集 2 项。

| 复核项 | 执行结果 |
|---|---|
| P0-1 整包大小 | 已加每张图、媒体总量、整包及正文 XML 检查；多图整包 38,567 → 38,188，最终通过 |
| P0-2 真阻断 pywin32 | 已加 stub、实际解释器探针、渲染器记录；P0 复验走 PowerShell 通过，最终轮改走 cscript，按规定口径失败 |
| P0-3 oracle 泄漏 | 工作目录移出项目仓库，只复制 fixtures；最终 10/10 无污染，Markdown 最终通过 |
| P0-4 provenance | 显式来源、文件数、树哈希、逐 run 来源及 16 turns；正式批次同一 candidate-09 树，前后哈希不变 |
| P1-1 自动 deny | 核心规则模块完成；原用例与正文对照 15/15，改写 8/8；正常退出分别 13/15、8/8 |
| P1-2 隔离 A/B | 30/30；on 15/15、off 14/15；路由两臂均 15/15，不声称相对路由改善 |
| P2-1 max_turns | runner 显式 16，raw 与 manifest 均为 16 |
| P2-2 报告措辞 | 旧 10/10 撤回；真实用户工作流改为本地 fixture 回归；p2-03 标为无文件探针；数据库措辞加限制 |
| P2-3 批注样式 | CommentText 已直接生成验证，最终批注产物也存在 |
| P2-4 敏感证据 | validation 已加入 .gitignore；不打包、不提交、不公开原始证据，只交付脱敏汇总 |

## 最终 10 项

- 严格任务通过：**8/10**。
- 路由：9/10；产物／边界证据：9/10；输入未改：10/10；无污染：10/10；来源一致：10/10。
- 正常退出：7/10，单独保留。
- 差集：real-04 PDF 未走规定的 PowerShell 回退分支；real-08 缺失输入多选技能。
- 临时文件清理：9/9，剩余 0；相关 Hermes／Python／Node 与所有 WINWORD 进程为 0。

## 核心回归与边界

核心 unittest **43/43**，MCP stdio **1/1**。真实 Hermes 未接入自动禁则；所有技能修复仅在 candidate-09 隔离副本。未主动写入真实配置、技能、cron 或数据库，Hermes 自身仍可能写 live DB／cron。

详细报告：`p0-correction-review.md`、`automatic-policy-review.md`、`policy-ab-review.md`、`real-tasks-05-final.md`。
