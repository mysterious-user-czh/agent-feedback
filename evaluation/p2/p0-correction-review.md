# P0 验收漏洞修正记录

## 结论

旧批次“10/10 真实任务通过”已撤回。严格复验后，多图压缩与无 pywin32 PDF 已修复；Markdown 格式任务仍失败。P0 三项最新有效结果为 **2/3 通过**，不是 3/3。

## 验收器与运行条件

- 技能树显式复制，记录来源路径、文件数、复制前后树哈希；每条运行记录 `source_tree_sha256`、`source_kind` 和 `max_turns=16`。
- 工作目录移到项目仓库外、当前工作区内的 `validation-sandbox/`，仅复制 fixtures 和空 artifacts。
- 检查原始轨迹是否读取 `evaluation/p2` 或评测清单；污染、输入改变、来源不一致均不能通过。
- 路由、产物、输入完整性、污染、来源和退出码分别记录。
- 旧批次和旧数字保留，新运行写入新目录，不回改历史证据。

## 三项结果

| 任务 | 初次严格复验 | 修复后复验 | 当前状态 |
|---|---|---|---|
| real-02 多图压缩 | 媒体 27,970 → 23,259，但整包 38,567 → 40,671，失败 | 整包 38,567 → **38,188**，三张图分别缩小，正文 XML 相同，退出 0 | **通过** |
| real-04 无 pywin32 PDF | PDF 存在，但旧脚本未记录实际分支，失败 | 实际解释器导入被 stub 阻断；轨迹记录 `renderer=powershell-com`；PDF 含 `PDF_REAL_OK`，退出 0 | **通过** |
| real-10 Markdown | 将标题作为 H1，缺少 `## 标题`，失败 | 相同查询再次运行，仍不满足三个指定二级章节，退出 0 | **仍未通过** |

没有为了通过 real-10 而放宽标题断言，也没有把正常退出当作任务成功。

## 隔离技能修复

- `docx_compress_images.py`：ZIP_DEFLATED level 9 并记录输入／输出整包大小；直接实测多图和单图整包均缩小。
- `docx_to_pdf.py`：输出实际 `renderer`（`libreoffice`／`win32com`／`powershell-com`）。
- `docx_comments.py`：补充 Comment Text 段落样式，已直接生成 DOCX 并确认 `CommentText` 写入。
- 所有修复仅在 `validation/candidate-09-shared-home` 隔离副本，真实 Hermes 技能未修改。

## 证据

- 首轮严格失败：`validation/real-tasks-02-p0/results.json`。
- 修复后复验：`validation/real-tasks-03-p0/results.json`。
- Markdown 同查询复验：`validation/real-tasks-04-markdown/results.json`。

这些目录含敏感原始证据，不公开、不打包；对外仅提供本汇总。
