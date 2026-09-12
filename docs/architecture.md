# Architecture

## Ownership

| 层 | 拥有 | 不拥有 |
| --- | --- | --- |
| Project Herdr | 工作区 identity、派工合同、收据、inbox | 产品代码、产品 AGENTS.md、云电脑 |
| 目标工作区 | 代码、测试、该仓 shared context | 跨仓意图与授权 |
| Herdr | pane / agent 运行时 | queue 语义、工作区真源 |
| herdr-orchestrator | 单仓 durable queue（若目标仓已安装） | 跨仓登记 |

## Dispatch states

```text
drafted -> ready -> dispatched -> needs_review -> done
                               -> blocked
ready -> needs_review | blocked | done
```

`drafted` 只存在于控制面。`ready` 表示工人可以领。`dispatched` 表示 Herdr 已开工人 pane，不等工人结束。`needs_review` 进入 inbox。`done` 离开 inbox。

## Receipts

收据是 append-only JSON。最新一条决定 inbox 分类：

- `needs_review` → review
- `failed` / `blocked` → failed / blocked
- `passed` 且 status `done` → 不在 inbox

收据不复制产品 diff。证据字段只放路径或命令名。

## Path resolution

1. `PROJECT_HERDR_PATH_<ID>`
2. `control/overlays/<device>/paths.toml`
3. 若当前 control-plane checkout 的 `origin` 与该工作区 remote 相同，则用当前 root

路径解析失败时仍可写合同；`--enqueue` 必须能解析到存在的目录。

## Herdr adapter

`--enqueue` 在 `HERDR_ENV=1` 时：

1. 在目标仓 cwd 拆一个不抢焦点的 pane
2. 启动所选 harness
3. 提交 worker prompt
4. 立即返回，不 `--wait`

不在 Herdr pane、没有 `herdr`、或目标路径未解析时 fail closed，合同保持 `ready`。
