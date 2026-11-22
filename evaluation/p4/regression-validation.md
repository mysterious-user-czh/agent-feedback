# P4.3 真实失败到既有修复及 candidate-11 的回归验证

## 验收结论

- 历史来源：`p2-clean / p2-04-confusable-image-compression`，原始 **3/3** 次缺目标 DOCX。
- 修复前新鲜复现：**2/2** 次具有相同 `artifact_missing` 签名，均为非零退出；judge 运行 **0/2**，不把执行错误伪装成 judge FAIL。
- candidate-11 同例回归：**3/3 PASS**。
- 正常正文编辑对照：**1/1 PASS**。
- candidate-10 是既有修复；candidate-11 额外统一 quality=85、保留透明图 alpha，并在替换前重新解码、核对尺寸。
- 修复后每次均通过：DOCX 可打开、输入未改、`document.xml` 逐字节不变、媒体缩小、整包缩小、图片可解码、尺寸保持或等比缩放、alpha 保留、零退出。
- 正常对照通过：新正文存在、旧正文消失、表格保留、输入未改、零退出。

## 分流与纠正

最初检查过 candidate-05，但其第三次已经生成有效产物，故未冒充稳定失败；最终使用原始 p2-clean 三次均缺产物的冻结版本。两次新鲜 before 运行签名一致才准入；本轮满足。三次 after 是同一冻结任务的重复回归，确定性脚本也重复执行，不是三个独立模型行为样本。

## 预算与边界

- 实际收到并传给 Hermes CLI 的预算：回归 12 turns／240 秒，正常对照 16 turns／240 秒；controls sidecar 核验 **6/6**。
- skill-up 的 turns 字段单独记录，不假定等于 CLI Agent 回合，也不作为预算执行证据。
- token 字段返回 0 表示未采集，不解释为实际零消耗；token 与金额均为 unknown。
- custom engine 未暴露具体模型身份，因此本结果不做跨模型或模型固定声明。
- 只证明一个真实图片压缩失败及一个正常 Word 编辑对照，不外推全 Skill、全任务或长期稳定性。
- before、candidate-11 技能树及冻结 candidate-10 均核对未变；脱敏结果不含原始回复、轨迹、session_id、凭据或数据库。

机器可读汇总：`evaluation/p4/regression-results.json`。原始证据仅保留在本地 `validation/`。
