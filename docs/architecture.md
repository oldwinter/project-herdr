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

## Notes

`control/notes.md` 对应 Cursor Project 里 coordinator 维护的 `notes.md`：一行一个 checkbox，只有当前状态，没有历史。它是派生物，`dispatch create` / `dispatch attach` / `receipt record` / `notes` 都会用临时文件原子重写它。

- 未完成的 dispatch 是 `- [ ]`；多个工作区时按 `## <workspace>` 分组。
- `done` 的 dispatch 是 `- [x]`，只保留最新 3 条；更旧的追加进 `control/archived.md`（append-only，按 id 去重）。
- 进行中的 dispatch 优先显示最新 session step；否则有收据时显示收据 summary，再否则显示状态短语。`pr_url` 存在时追加 `[PR](url)`。

## Shared context

`context/` 对应 Cursor Project 的 Agent Store。分三层，worker prompt 会直接写明目标路径：

| 目录 | 放什么 |
| --- | --- |
| `context/docs/` | 人会打开的交付物；跨仓教训在 `lessons.md` |
| `context/internal/<dispatch>/` | worker 的 `report.md` 和其它 agent 侧证据 |
| `context/media/` | 截图、录屏 |

产品仓自己的知识仍然留在产品仓的 AGENTS.md。

## Session

`session` 对应 Cursor Project 里 coordinator 对仍在跑的 worker 的增量读数。它不写收据、不改合同状态。

| 命令 | 做什么 |
| --- | --- |
| `session update --dispatch <id> --step "..."` | worker 追加一条短步骤到 `context/internal/<id>/session.jsonl` |
| `session show [id]` | 读日志；省略 id 时列出未完成 dispatch 的最新步骤 |
| `session pull <id>` | 调 `herdr agent read`，只把相对上次 cursor 的新增文本写入同一 JSONL |

`pull` 的 cursor 在 `control/runtime/<id>/session.cursor`（上次完整快照）。新文本是旧快照的前缀延长、滑动窗口重叠，或整段重置。没有 Herdr 会话、不在 Herdr pane、或没有 `herdr` 时 fail closed，不写文件。`--dry-run` 只报告。

进行中的 dispatch（`drafted` / `ready` / `dispatched`）在 `notes.md` 里显示最新 step，而不是泛化的状态短语。

## Sync

`sync` 是 Cursor Project "follow all your PRs" 的轮询版。对每个 `pr_url` 非空且未 `done` 的 dispatch 调一次 `gh pr view --json state,mergedAt,statusCheckRollup`，然后：

| 观察到 | 收据 | 状态 |
| --- | --- | --- |
| merged | passed "PR merged" | done |
| closed 未合并 | blocked "PR closed without merge" | blocked |
| open 且任一 check 失败 | needs_review "CI failing on PR" | needs_review（只记一次） |
| open 且 pending / 全绿 | 不写 | 不变 |
| `gh` 出错 | 不写 | 不变，结果里给出 `probe_failed` 和原因 |

没有 `gh` 且存在待同步的 dispatch 时报 `AdapterError`（exit 3），不写任何文件。`--dry-run` 只报告。

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
