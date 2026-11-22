# P2 首批实测

- 覆盖：15/15；缺失 0。
- 路由通过：6/15；执行轨迹：15/15；总体：0/15。
- 进程退出码为 0：3/15；非零：12/15。非零运行即使产物成立，也不计为完整 harness 成功。

| 用例 | 路由 | 总体 |
|---|---:|---:|
| p2-01-success-word-pdf | 2/3 | 0/3 |
| p2-02-failure-missing-input | 0/3 | 0/3 |
| p2-03-reject-legacy-doc | 0/3 | 0/3 |
| p2-04-confusable-image-compression | 3/3 | 0/3 |
| p2-05-confusable-word-review | 1/3 | 0/3 |

## 逐次证据

- p2-p2-01-success-word-pdf-a1-0dba41d0d5：技能 ['docx']；route=False；artifact=True；PDF pages=1, required text=True。
- p2-p2-01-success-word-pdf-a2-21b3f97c76：技能 ['microsoft-office', 'docx']；route=True；artifact=False；PDF invalid/missing: [Errno 2] No such file or directory: '<PROJECT>\\validation\\p2-clean\\work\\p2-p2-01-success-word-pdf-a2-21b3f97c76\\artifacts\\p2-p2-01-success-word-pdf-a2-21b3f97c76.pdf'。
- p2-p2-01-success-word-pdf-a3-63c6cf09ac：技能 ['microsoft-office', 'docx']；route=True；artifact=False；PDF invalid/missing: [Errno 2] No such file or directory: '<PROJECT>\\validation\\p2-clean\\work\\p2-p2-01-success-word-pdf-a3-63c6cf09ac\\artifacts\\p2-p2-01-success-word-pdf-a3-63c6cf09ac.pdf'。
- p2-p2-02-failure-missing-input-a1-8997f12a57：技能 无；route=False；artifact=True；Missing input acknowledged and no fabricated artifact。
- p2-p2-02-failure-missing-input-a2-b95fa64a95：技能 无；route=False；artifact=True；Missing input acknowledged and no fabricated artifact。
- p2-p2-02-failure-missing-input-a3-f1aac9899b：技能 无；route=False；artifact=True；Missing input acknowledged and no fabricated artifact。
- p2-p2-03-reject-legacy-doc-a1-f71e6550a3：技能 ['docx']；route=False；artifact=None；No artifact required。
- p2-p2-03-reject-legacy-doc-a2-a872066bc0：技能 ['docx', 'microsoft-office']；route=False；artifact=None；No artifact required。
- p2-p2-03-reject-legacy-doc-a3-534d132fa5：技能 ['docx']；route=False；artifact=None；No artifact required。
- p2-p2-04-confusable-image-compression-a1-5ca2bd3418：技能 ['docx', 'microsoft-office']；route=True；artifact=False；DOCX invalid/missing: Package not found at '<PROJECT>\validation\p2-clean\work\p2-p2-04-confusable-image-compression-a1-5ca2bd3418\artifacts\p2-p2-04-confusable-image-compression-a1-5ca2bd3418.docx'。
- p2-p2-04-confusable-image-compression-a2-e61593fa4e：技能 ['docx']；route=True；artifact=False；DOCX invalid/missing: Package not found at '<PROJECT>\validation\p2-clean\work\p2-p2-04-confusable-image-compression-a2-e61593fa4e\artifacts\p2-p2-04-confusable-image-compression-a2-e61593fa4e.docx'。
- p2-p2-04-confusable-image-compression-a3-2977113c96：技能 ['docx']；route=True；artifact=False；DOCX invalid/missing: Package not found at '<PROJECT>\validation\p2-clean\work\p2-p2-04-confusable-image-compression-a3-2977113c96\artifacts\p2-p2-04-confusable-image-compression-a3-2977113c96.docx'。
- p2-p2-05-confusable-word-review-a1-0870e11443：技能 ['microsoft-office', 'microsoft-office', 'microsoft-office']；route=False；artifact=False；DOCX invalid/missing: [Errno 2] No such file or directory: '<PROJECT>\\validation\\p2-clean\\work\\p2-p2-05-confusable-word-review-a1-0870e11443\\artifacts\\p2-p2-05-confusable-word-review-a1-0870e11443.docx'。
- p2-p2-05-confusable-word-review-a2-51c3650eac：技能 ['docx', 'docx']；route=True；artifact=False；DOCX invalid/missing: [Errno 2] No such file or directory: '<PROJECT>\\validation\\p2-clean\\work\\p2-p2-05-confusable-word-review-a2-51c3650eac\\artifacts\\p2-p2-05-confusable-word-review-a2-51c3650eac.docx'。
- p2-p2-05-confusable-word-review-a3-a57bc4e1c5：技能 ['microsoft-office', 'microsoft-office', 'microsoft-office']；route=False；artifact=False；comment=True, trackChanges=False。
