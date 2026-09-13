# 自测指南

目的：15 分钟内从零跑完一遍 coordinator → worker → 回流的闭环，确认每一层都按 Cursor Project 的方式工作。每一步都有"应该看到什么"，没看到就是 bug。

前提：Python 3.12+、git、just。Herdr 和 `gh` 可选，没有也能跑完 A–D。

## A. 冷启动（2 分钟）

```bash
git clone git@github.com:oldwinter/project-herdr.git
cd project-herdr
just check
just start
just doctor
just context
```

应该看到：

- `just check`：全部 OK。
- `just start`：一句规则 + 下一步命令列表，最后一行是 `project-herdr notes`。
- `just doctor`：`harnesses  claude codex droid grok hermes pi`；`herdr` 一行是路径或 `missing (optional)`。
- `just context`：`context/docs` `context/internal` `context/media` 三个目录都存在。

## B. 登记一个真实工作区（3 分钟）

在 `control/workspaces.local.toml`（不提交）加一个你自己的仓：

```toml
[[workspaces]]
id = "skills"
name = "Skills"
kind = "product"
remote = "git@github.com:oldwinter/skills.git"
default_harness = "codex"
entry = "just test"
```

再告诉它本机路径（任选其一）：

```bash
export PROJECT_HERDR_PATH_SKILLS=~/code/skills
# 或写 control/overlays/<hostname>/paths.toml：
#   device = "<hostname>"
#   [paths]
#   skills = "/Users/you/code/skills"
```

```bash
just workspaces
just status
```

应该看到：`skills` 出现在列表里，`status` 的 PATH 是真实路径，GIT 是 `ok`，DIRTY 反映真实状态。

## C. 不用 Herdr 的手动闭环（5 分钟）

这是核心。coordinator 只写合同，你自己扮演 worker。

```bash
just dispatch create \
  --workspace skills \
  --objective "在 README 顶部加一行一句话简介" \
  --harness codex \
  --accept "just test" \
  --ready
just notes
```

应该看到：

- 输出 `d-<日期>-<slug>  ready  skills`。
- `control/notes.md` 里有 `- [ ] [d-...](dispatches/d-....toml) ... — ready, waiting for a worker`。
- `control/runtime/d-.../prompt.md` 存在，里面有 `## Output` 段，指向 `context/internal/d-.../report.md`，还有 `dispatch attach ... --pr` 的用法。

现在把 prompt 贴给任意一个 harness（Codex app、Claude Code、Pi 都行），在 `skills` 仓里干活。干完回到本仓：

```bash
mkdir -p context/internal/d-.../
echo "改了 README 第一行；just test 通过" > context/internal/d-.../report.md
just receipt record --dispatch d-... --verdict needs_review \
  --summary "README 加了简介，等你看一眼" \
  --evidence context/internal/d-.../report.md
just inbox
just notes
```

应该看到：

- `inbox` 有一行 `review  d-...  skills  needs_review  README 加了简介…`。
- `notes.md` 那一行变成 `— README 加了简介，等你看一眼`。

你看完满意：

```bash
just receipt record --dispatch d-... --verdict passed --summary "合入"
just inbox      # 应为 Inbox empty.
just notes      # 那一行变成 - [x]
```

再造 3 个以上 `passed` 的 dispatch，`notes.md` 只留最新 3 条 `[x]`，多的进 `control/archived.md`。

## D. PR 回流（3 分钟，需要 `gh auth login`）

对一个真的开了 PR 的 dispatch：

```bash
just dispatch attach d-... --pr https://github.com/oldwinter/skills/pull/12
just notes                 # 行尾出现 [PR](...)
just sync --dry-run        # 看 lifecycle / checks / action，不写
just sync                  # merged → done；CI 红 → needs_review
```

没登录 `gh` 时应该看到 `probe_failed` 和 `gh auth login` 提示，且合同、收据一个字节都没变。

## E. Herdr 派发（可选，2 分钟）

在 Herdr pane 里，`HERDR_ENV=1` 自动有：

```bash
just dispatch create --workspace skills --objective "跑一遍 just test 并汇报" --enqueue
```

应该看到：右侧新开一个 pane，cwd 是 skills 仓，harness 是 `codex`，prompt 已提交；本仓命令立即返回，合同状态 `dispatched`。不在 Herdr pane 里跑同一条，应该报 `not_in_herdr_pane`，合同留在 `ready`。

## F. 记教训（1 分钟）

```bash
just lesson add "skills 仓 just test 前要先 just seed" --workspace skills
cat context/docs/lessons.md
```

## 判定

| 层 | 通过标准 |
| --- | --- |
| coordinator 不写代码 | 全程本仓只多了 `control/` `context/` 下的文件；产品仓 diff 全在产品仓 |
| notes | 每次 create / attach / receipt / sync 后 `control/notes.md` 立刻反映当前状态，且没有历史流水 |
| shared context | worker 报告落在 `context/internal/<id>/report.md`，教训在 `context/docs/lessons.md` |
| PR 回流 | `sync` 能把 merged 变 done、CI 红变 needs_review，没 `gh` 不乱动 |
| harness 可换 | `--harness pi` / `codex` / `claude` 各派一次，prompt 一致，只有 `--kind` 不同 |

哪一条不过，把 `just --json <命令>` 的输出贴回 coordinator 会话。
