# Hermes agent-feedback 一键安装包（0.11.2）

## 安装

解压后在包目录打开 PowerShell：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
```

默认位置：

- Hermes Home：现有 `HERMES_HOME`，否则 `%LOCALAPPDATA%\hermes`；
- 独立运行环境和数据库：`D:\KimiData\agent-feedback`；
- MCP 名称：`agent-feedback`。

首次安装需要 Python 3.10+，并需要联网获取 wheel 的依赖。脚本不覆盖已有同名 Skill 或 MCP；注册前备份 `config.yaml`，注册通过 Hermes 官方 `mcp add` 完成，不直接改写 YAML。

如 Hermes CLI 不在 PATH：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -HermesBin "C:\path\to\hermes.exe"
```

其他可选参数：`-HermesHome <目录>`、`-InstallRoot <目录>`、`-Python <python路径>`。只需 MCP 手动采集时，可加 `-NoAutoCollector`。

## 默认自动采集

安装成功后默认启动一个隐藏的本机 PowerShell 采集进程，每 60 秒完成一轮增量导入和独立覆盖审计。首次启动必须首轮覆盖通过，否则安装报错并回滚 MCP／Skill；不会把“进程存在”冒充“采集成功”。

- 只读打开 Hermes `state.db`，默认排除子会话；反馈数据写入本包自己的数据库。
- 审计独立枚举源库基线，缺失或范围外的会话、消息、Skill 选择、工具错误都会使当轮失败；解析失败也会使当轮失败。
- 老会话后续新增消息会补扫；重复导入不会重复计数。
- 这是周期性增量采集，不是 Hermes 内部实时 hook；Hermes 未运行或源库暂时不可读时会记录失败并等待下一轮。
- 重启电脑后需要重新运行下面的 `start-auto-collector.ps1`；本包不创建开机启动项或 cron。
- 不自动修改其他技能、路由、配置或 cron；routing 没有可靠真值时仍为 `unknown`，最终产物仍需独立验证。

查看状态：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\status-auto-collector.ps1 -InstallRoot "D:\KimiData\agent-feedback"
```

停止或重新启动：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\stop-auto-collector.ps1 -InstallRoot "D:\KimiData\agent-feedback"
powershell -NoProfile -ExecutionPolicy Bypass -File .\start-auto-collector.ps1 -InstallRoot "D:\KimiData\agent-feedback" -HermesHome "%LOCALAPPDATA%\hermes"
```

PowerShell 不会自动展开双引号里的 `%LOCALAPPDATA%`；重新启动时请把 `-HermesHome` 替换为实际绝对路径。

## 验证

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\verify.ps1
```

验证包版本、contracts、Skill、MCP；启用自动采集时，还验证进程身份和最近一次完整覆盖状态。

## 升级与卸载

从旧版升级时，先用旧包的 `uninstall.ps1` 卸载且**不要加 `-Purge`**，再用同一 `InstallRoot` 安装本版，以保留 `data\feedback.db`。操作前备份需要保留的数据。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\uninstall.ps1
```

卸载先停止本包采集进程，再移除自身 MCP 和 Skill。默认保留数据库、运行环境和配置备份；`-Purge` 会连反馈数据和运行环境一起删除。

安装后重启 Hermes 会话以加载 Skill 和 4 个 MCP 工具。MLflow 和 skill-up 不属于基础安装。
