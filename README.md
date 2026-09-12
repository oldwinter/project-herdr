# Project Herdr

跨仓库的 agent 总控。人只跟 coordinator 说话；真正改代码的 worker 在已登记的产品仓里跑。Herdr 是可选派发通道，不是真源。

它对应 Cursor Project 的三个能力，但落在文件上，而不是某一种 IDE：

| Cursor Project | Project Herdr |
| --- | --- |
| Coordinator 不写代码 | 本仓只写合同、收据、inbox |
| Shared context 随项目长 | 产品规则留在目标仓；跨仓教训才回到这里 |
| Cloud + subscriptions | 本机 Herdr pane；定时/事件仍由既有 automation 拥有 |

```text
你 ──► project-herdr（coordinator）
          │  workspaces.toml
          │  dispatch contract
          │  receipts / inbox
          ▼
     目标工作区（产品仓 / 知识库）
          │  可选 --enqueue
          ▼
     Herdr pane + worker harness
```

## 要求

- Python 3.12+
- `git`
- `just`（开发入口）
- 可选：Herdr 0.8+，且从 Herdr pane 内 `--enqueue`

## 命令

```bash
just start
just doctor
just workspaces
just status
just inbox
```

登记一个任务，但不改目标仓：

```bash
just dispatch create \
  --workspace project-herdr \
  --objective "Add a second example workspace" \
  --ready
```

在 Herdr pane 里把 worker 派到目标仓（coordinator 不等待）：

```bash
just dispatch create \
  --workspace novel \
  --objective "Draft chapter one" \
  --enqueue
```

worker 结束后回写证据：

```bash
just receipt record \
  --dispatch d-20260913-draft-chapter-one \
  --verdict needs_review \
  --summary "Ending still open"
just inbox
```

CLI 入口是 `project-herdr` / `ph`。在 checkout 里也可以：

```bash
PYTHONPATH=src python3 -m project_herdr --help
```

## 工作区登记

真源是 `control/workspaces.toml`。本机私有仓写到 gitignored 的 `control/workspaces.local.toml`（同 id 覆盖）。本机路径写到 `control/overlays/<device>/paths.toml`，或设 `PROJECT_HERDR_PATH_<ID>`。

不要把产品 git 仓库嵌进本仓。Coordinator 会话留在这里；产品 diff 留在产品仓。

## 安全

- 默认禁止 push / merge / send / delete。要开放必须显式 `--allow-*`。
- secret 不进仓库。
- `--enqueue` 只在 `HERDR_ENV=1` 且 `herdr` 可用时改 Herdr 布局；失败则合同留在 `ready`。

## 验证

```bash
just check
```
