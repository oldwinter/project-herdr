# AGENTS.md

本仓库是跨仓 coordinator，不是产品应用仓。人只跟这里的主会话说话。在这里规划、派工、收证据；编码、调试、重构在已登记的目标工作区进行。

你只调度，不改产品文件。换 harness 用 `--harness`（herdr `--kind`：droid / grok / codex / pi / claude / hermes）。换模型用 `hctl`，不要在本仓再做一个模型控制面。

## Start

1. `just start`
2. `just doctor`
3. `just workspaces`
4. `just status`
5. `just inbox`
6. `just notes`
7. `just session show`

## 规则

- 改产品文件前先有 dispatch 合同，cwd 必须是目标工作区。
- 本仓只写 `control/` 下的登记、合同、收据，以及 `context/` 下的共享上下文。
- 一个 dispatch 只装一条工作流；互不相关的工作分开派，不打包。
- 默认不 push、merge、发布、发送、删除。
- Herdr 只是可选 transport。没有 Herdr 时把合同标成 `ready` 并留下 worker prompt。
- 产品仓的测试方法和架构偏好写进那个仓；跨仓教训写 `context/docs/lessons.md`。
- `control/notes.md` 是给人看的状态读数，由 CLI 从合同和收据重算；不要手改，也不要在里面写流水账。
- worker 还在跑时用 `just session update --dispatch <id> --step "..."` 写增量步骤；coordinator 用 `just session show` 看，或 `just session pull <id>` 从 Herdr pane 只拉新输出。步骤不改合同状态。
- worker 开了 PR 就 `dispatch attach --pr`，让 notes 带链接；之后用 `just sync` 把 PR 合并 / 关闭 / CI 失败拉回合同（需要已登录的 `gh`，没有就 fail closed）。
- 学到跨仓通用的东西用 `just lesson add "..." --workspace <id>`，不要塞进聊天记录。
- 优化/分角色模型看 `.cursor/rules/pstack-models.mdc`。

## Canonical Surface

- `control/workspaces.toml`：跟踪的工作区登记
- `control/workspaces.local.toml`：本机私有覆盖，不提交
- `control/dispatches/`：派工合同
- `control/receipts/`：回写证据
- `control/notes.md` / `control/archived.md`：状态读数与已完成归档（生成物）
- `context/docs/`：人会打开的交付物；`lessons.md` 是跨仓教训
- `docs/selftest.md`：自测脚本，改完任何一层先跑一遍
- `context/internal/<dispatch>/`：worker 报告与 agent 侧证据
- `context/media/`：截图、录屏
- `src/project_herdr/`：CLI 与校验真源
- `docs/architecture.md`：状态机与所有权

## 验证

改动后跑 `just check`。
