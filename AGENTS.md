# AGENTS.md

本仓库是跨仓 coordinator，不是产品应用仓。人只跟这里的主会话说话。在这里规划、派工、收证据；编码、调试、重构在已登记的目标工作区进行。

你只调度，不改产品文件。换 harness 用 `--harness`（herdr `--kind`：droid / grok / codex / pi / claude / hermes）。换模型用 `hctl`，不要在本仓再做一个模型控制面。

## Start

1. `just start`
2. `just doctor`
3. `just workspaces`
4. `just status`
5. `just inbox`

## 规则

- 改产品文件前先有 dispatch 合同，cwd 必须是目标工作区。
- 本仓只写 `control/` 下的登记、合同、收据。
- 默认不 push、merge、发布、发送、删除。
- Herdr 只是可选 transport。没有 Herdr 时把合同标成 `ready` 并留下 worker prompt。
- 产品仓的测试方法和架构偏好写进那个仓；这里只保留指针和跨仓教训。
- 优化/分角色模型看 `.cursor/rules/pstack-models.mdc`。

## Canonical Surface

- `control/workspaces.toml`：跟踪的工作区登记
- `control/workspaces.local.toml`：本机私有覆盖，不提交
- `control/dispatches/`：派工合同
- `control/receipts/`：回写证据
- `src/project_herdr/`：CLI 与校验真源
- `docs/architecture.md`：状态机与所有权

## 验证

改动后跑 `just check`。
