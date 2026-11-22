# P4.2 插件封装与 skill-up 最小链路

## skill-up

- 使用 alibaba/skill-up 0.16.0 Windows amd64，官方发布 SHA-256 校验一致。
- `engine.custom transport=local`、`conversation_mode=batch`、标准 SessionInput／SessionResult。
- 适配器在 skill-up workspace 内复制隔离 Hermes Home，只读过滤现有凭据，不改真实配置。
- 显式返回 artifacts，transcript 包含工具调用／结果；退出码保留。

最终批次 `skillup-minimal05`：1/1 PASS，expect 退出码、文件存在及 PowerShell script judge 三项全过。judge 实测 input unchanged、output exact、exit zero 均为 true。此前 127、缺凭据、脚本解释器及 sibling 脚本复制问题分别修正，失败批次保留不作为通过证据。

边界：当前只声明 local／batch／单轮最小链路。http、stateful 多轮、OTLP、token／成本映射和持续实时 hook 尚未完成；model 显示 unknown，不伪造实际模型观测。

## Skill 产品封装

- 统一 MCP server 名 `agent-feedback`，四个工具为 feedback_start／event／label／report。
- SKILL.md 明确 live／imported、outcome rollup、unknown 和禁止自动改路由。
- 新增宿主配置参考及 `docs/installation.md`，包含版本、依赖、环境变量和卸载边界。
- 历史 P4.2 批次的 `dist/agent-feedback.skill` 含 SKILL.md 与 MCP 配置参考，ZIP CRC 校验通过；当时 SHA-256 为 `b6fbf57823474e868a13354725cf78f6eba55175327d3eb7a7807fc56fb5441c`。这不是 0.11.1／0.11.2 当前附件的校验值；当前值以对应 Release 为准。

这只是可分发的 Skill 引导包；Python 核心和 MCP 仍需按安装文档安装，不能把复制 SKILL.md 当作完整产品安装。
