# P4 最小产品闭环验收与内容修正

## 0.11.2 内容修正

本版不宣称新的路由或语义质量提升，只修正公开交付内容：

- 基础示例补齐 `process_result`、成功工具结果和 `artifact_source=live`，实际运行通过；新增独立回归测试防止示例再次失效。
- `examples/report.md` 由当前代码重新生成，包含筛选统计、工具失败／取消统计和五维状态。
- 补齐 0.11.1 的公开发布审计与 manifest 副本；历史 Skill 哈希明确标注为早期 P4.2 批次，不再与当前附件混淆。
- README 重组为用途、边界、下载安装、最小工作流和证据索引；“跨 Agent”和 Hermes 切段规则版本的适用范围就近说明。
- 82/82 unittest、独立 MCP stdio 4 工具全链路和 34 条 P3 黄金回放通过。0.11.1 已发布附件保持不变。

---

## 0.11.1 结论口径

**本轮 A1–A5、B1/B2、B3 真实 triage、skill-up＋MLflow 回归联接和 C 隔离发布验收通过。** 覆盖只适用于下文逐项证据；不把测试数、进程存在或安装成功冒充路由与语义质量。真实安装升级结果单独记录，不改写本隔离验收的适用范围。

| 验收项 | 实测结果 | 公开证据 |
|---|---|---|
| 最新验证信任门 | success→failure 后拒绝成功标签；failure→最新合格 success 才允许；人工 success 与最新验证冲突生成 P1 | `integration-review-check.json` 仅私有；81 项回归 |
| 真实采集覆盖 | 45/45 非空主会话、7,864/7,864 消息、71/71 选择、266/266 失败、14/14 取消，合计 280/280；差集 0，parse_failures=0 | `auto-collection-validation.json` |
| 报告 triage | priority／execution／has_tool_errors／has_observed_label／sort 与 filtered_total 可用；21 个 P1 任务、22 条 P1 finding；源时间回填 423/423 | `auto-collection-validation.json` |
| B3 人工复核 | 7 个纠正候选＋工具失败前 10，已覆盖 17/17；6 个真问题任务、4 个误报、7 个需更多证据；T06/T07 合并为同一底层问题 | `real-triage-v0111.json` |
| T03 冻结回归 | before 误报 2/2；after 误报 0/3；正常纠正对照 1/1；skill-up 6/6 PASS | `t03-closed-loop-v0111.json` |
| 独立 oracle 与回导 | 独立复算 6/6 原始字节一致；SessionResult 回导 6/6；二次导入新增事件 0；routing 保持 unknown | `t03-closed-loop-v0111.json` |
| MLflow 父子关联 | 本地 1 父＋6 子 run；case、来源、配置、源码、fixture、oracle 哈希齐全；脱敏产物 6/6 可回读，远端上传 0 | `t03-closed-loop-v0111.json` |
| 完整回归与接口 | 81/81 unittest；独立 MCP stdio 4 工具全链路；PowerShell 语法 7/7；旧 MLflow API 2/2 run 可找回 | 本报告与任务日志 |
| 一键包生命周期 | 隔离安装、首轮完整覆盖、status／verify、重复安装拒绝、进程树清理和保留数据卸载通过 | `oneclick-plugin-v0111-validation.json` |
| 失败路径 | MCP test 失败回滚、异常 status、陈旧 start、verify 过期、stop 已退出进程，已覆盖 5/5 | `release-failure-paths-v0111.json` |
| 干净通用 Host | 0.11.1 wheel 非 editable 安装；Skill 2 文件、MCP、SessionResult 导入通过；受控 TEMP 残留 0 | `clean-delivery-validation.json` |
| 发布完整性 | 核心 ZIP、wheel、Skill、Hermes 一键包 CRC／唯一条目／隐私扫描通过；不含 validation、数据库、凭据或缓存 | `final-audit-v0111.json` |

### 0.11.1 边界

- T03 是一个确定性的 agent-feedback 纠正识别缺陷，不是技能路由 benchmark，不证明模型质量或全库改善。
- 自动采集为安装后的 60 秒周期性只读 watcher，不是实时 hook，也不是重启后自恢复服务。
- routing 没有可靠真值时继续 unknown；产物必须独立 oracle；工具失败不自动等于任务失败。
- MLflow 仅本地 file store；模型身份、token 和成本信息不足时保持 unknown。
- 原始提示、响应、轨迹、session_id、数据库和 `runtime-private.env` 不进入公开包或 MLflow。

---

# P4 最小产品闭环最终验收（0.10.1 历史基线）

## 结论口径

**结论：P4 最小产品闭环的返工验收通过。** 表内 15/15 个验收项均有实测或冻结证据。安装成功、测试数量和参考 engine 不冒充真实检测效果；route／execution／artifact／exit／outcome 分账，证据不足保持 unknown。execution 只表示是否观察到工具失败，恢复状态尚未完整识别，不是任务失败率。

## 验收矩阵

| 验收项 | 实测结果 | 公开证据 |
|---|---|---|
| 真实任务事后采集 | 通过批次 1/1；80 条 stream 事件、2 条工具结果；未选择 Skill、routing=unknown；live artifact／exit／outcome 通过；真实配置、技能、cron、数据库及 WAL／SHM 前后不变 | `capture-spike-validation.md` |
| 统一事件契约与信任门 | v1 已冻结；成功验证必须 observed／human＋live／imported＋非空证据；self_reported、来源不明及旧数据绕过均不能通过 | `event-contract-v1.md` |
| Skill 与 MCP 封装 | `.skill` 2 文件、CRC 通过；独立 MCP stdio 4 工具 start→event→label→report 通过；服务器内部名统一为 `agent-feedback` | `skillup-minimal-validation.md` |
| skill-up custom engine | 0.16.0 local／batch／单轮最小链路 1/1 PASS；输入未改、输出精确、零退出 | `skillup-minimal-validation.md` |
| 真实失败复现 | 原始失败历史 3/3；新鲜复现 2/2 均为 `artifact_missing`、ERROR、非零退出；judge 运行 0/2，没有伪装成 judge FAIL | `regression-validation.md` |
| candidate-11 同例回归 | 3/3 PASS；DOCX 可打开、输入与正文 XML 不变、媒体和整包缩小、图片可解码、尺寸保持或等比缩放、alpha 保留、零退出 | `regression-results.json` |
| 正常任务防退化对照 | 1/1 PASS；正文替换正确、表格保留、输入未改、零退出 | `regression-results.json` |
| 确定性图片脚本与 oracle | 两份脚本 RGB 各 1/1、alpha 各 1/1；quality=85；正例通过，坏图片和错误尺寸均被拒绝 | `image-oracle-validation.json` |
| 通用事件导入 | SessionResult 导入 1/1，二次导入零新增；routing unknown，其余四维 pass | `reference-engine-validation.md` |
| 参考 engine 契约复用 | 确定性参考程序 1/1 PASS；不是第二真实 LLM Agent | `reference-engine-validation.md` |
| MLflow 脱敏存证与找回 | 3.18.0 本地 file store；2/2 run 按来源和版本字段找回；before ERROR、after PASS；code_version=0.10.1；敏感键 0 | `mlflow-validation.json` |
| 最终代码回归 | 69/69 unittest OK；独立 MCP stdio 全链路通过；P3 黄金回放 34/34 覆盖、33 判定正确、1 unknown | 本报告与任务日志 |
| 干净通用 Host 交付验收 | wheel 非 editable 安装 0.10.1；Skill 2 文件与 CRC、MCP 全链路、SessionResult 导入均通过；受控 TEMP 残留 0；不含 skill-up 或真实 Hermes 任务 | `clean-delivery-validation.json` |
| 原始阻塞问题复验 | self_reported＋live、observed＋unknown 两种输入均被拒；旧数据绕过时成功 label 仍被拒，artifact／outcome=unknown | 本报告与任务日志 |
| 发布内容隐私与完整性 | 发布 ZIP 和 Skill 扫描真实会话 ID、Windows 绝对路径、密钥、敏感文件名均为 0；无数据库、validation、重复条目或缓存 | `release-manifest-v0111.json` |

## 回归预算与重复性

- 6/6 个有效回归运行均有 controls sidecar：实际收到并传给 Hermes CLI 的预算为回归 12 turns／240 秒、正常对照 16 turns／240 秒。
- skill-up 的 turns 字段单独记录，不假定等于 CLI Agent 回合，也不作为预算执行证据。
- 三次 after 是同一冻结任务的重复回归，确定性脚本也重复执行；产物 SHA-256 相同，不构成三个独立模型行为样本。
- 启动路径错误的无效批次已在本地清理，不计入 2＋3＋1 的验收分母。

## 关键哈希

- 回归 fixture：`e088a0b113a61d991ac33aae4b1bde9dcf46669b951a9dbe7313e8d9043d9fa9`。
- 修复前技能树：`91ceb996f4f6e3c50e40ce188403cf638add0230d4bb27e44fd9e2dc456b92c3`。
- candidate-11 技能树：`8bc00cf238a5c734e7eca901a73795e6423a3ba86be99d9e289f5253c51db1e7`。
- 冻结 candidate-10 技能树：`b88230146e2e06bc2e19d0230f25cba615f847960711b40b1afe4be02018bd94`，终验保持不变。
- 三次 candidate-11 产物：`8c75bfcb2c21b61adbe66e5bee1f32238ed0abc02aa30b6bdd4269a708fa29ea`。
- Skill 包：`b4b0dd6cd7244d77a40e28f08291396ee62abcf71a084edc913405e475f4b186`。

## 清理与隐私

原始轨迹、凭据、数据库和 `validation/` 不进入公开发布包。初版公开评估的会话标识与项目路径已脱敏；发布扫描补充发现 P2 旧结果中的 4 条本机路径，也已清理并重新扫描。显式隔离工作区作为本地证据保留，不宣称系统 Temp 零遗留。真实 Hermes 配置、技能、cron 和数据库未被本轮返工修改。

## 仍未解决

- 真实 Hermes 持续实时 hook 未接入；当前是单任务事后自动采集。
- 通用语义质量、安全红线、全 Skill Top1 和完整工作流状态机未解决。
- 第二真实 LLM Agent 未验证；确定性参考程序只证明契约复用。
- skill-up 的具体模型身份、token 和金额信息不足，保持 unknown；返回 0 不解释为零消耗。
- 当前真实失败闭环只覆盖一个图片压缩失败及一个正常 Word 编辑对照，不能外推全 Skill 或长期稳定性。
- failproofai 本版不采用；这不影响事后证据与回归主闭环。
