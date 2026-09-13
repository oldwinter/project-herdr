# PR #5 CLI 自测报告

范围：A–D、F，以及 E 的非 Herdr 负向路径和三种 harness 的 ready prompt 对比。隔离 checkout 为 `/tmp/project-herdr-selftest-dfrb_g65/coordinator`，commit `92c27cf`；产品 fixture 为 `/tmp/project-herdr-selftest-dfrb_g65/product-fixture`。不包含真实 Herdr pane 派发（由主会话单独验证）。

结论：`just check` 37/37 通过，基本闭环、真实 GitHub PR 回流通过；额外发现 2 个同秒收据/归档问题和 1 个指南命令错误。未修源代码。

## 已验证

- A：Python 3.14.4，`just check` 37 tests OK；start 最后一行为 project-herdr notes；doctor 列出六种 harness；context 三目录存在。
- B：本地不提交登记、环境变量路径、hostname overlay 路径均解析到 fixture；GIT ok，初始 clean，worker 改 README 后 dirty。
- C：先有 dispatch 合同，再在产品 fixture cwd 添加 README 简介并运行真实 `just test`；create 自动刷新 ready notes；needs_review receipt 自动刷新摘要和 review inbox；passed 自动标记 checkbox，inbox empty。报告保存在 clone 的 context/internal/<id>/report.md。5 条 passed 只留 3 条 checkbox，但同秒时保留的身份不是最新 3 条（见问题）。
- D（真实 gh，仅只读）：将测试合同分别 attach 到 oldwinter/project-herdr #4/#5。#4 返回 merged/passing，dry-run action done，sync 后合同 done、notes PR merged；#5 返回 open/passing/unchanged。attach 自动显示 PR 链接。
- D（明确模拟）：PATH 本地 gh stub 返回未认证错误，输出 probe_failed 和 gh auth login；完全无 gh 的 PATH 返回 exit 3 与 gh is not on PATH；两者合同/收据/notes/archived SHA256 均不变。另一个 stub 返回 OPEN+FAILURE，dry-run needs_review 且零写入，sync 后合同 needs_review、notes CI failing on PR、inbox review。
- E（负向）：HERDR_ENV 移除后 enqueue 非零退出、not_in_herdr_pane、合同保留 ready。pi/codex/claude 三份 ready prompt 仅规范化 dispatch ID 后逐字一致，合同 harness 各自正确。未调用真实 Herdr 或启动 harness。
- F：lesson add 写入 context/docs/lessons.md，包含 workspace。
- 范围：coordinator 的 git 变更仅 control/、context/；产品 fixture diff 仅 README.md；src/tests/docs/justfile/AGENTS.md 无 diff。

## 问题

1. **同一秒的后续 receipt 不会成为 latest，notes 显示旧摘要。** 本次实际 CLI 在同秒先记 needs_review「README 加了简介，等你看一眼」，再记 passed「合入」。合同 done，notes checkbox 已勾选，但摘要仍是旧 needs_review 文本。`receipts.py` 按 filename 排序取最后一项；首次文件名 `...162535Z.json`，后续文件名 `...162535343296Z.json`，微秒文件字典序反而在前。证据：commands.jsonl seq 77–79、receipt-collision/、notes-after-passed.md。快速连续执行两次 `just receipt record` 可复现；要使两次落在同一秒。
2. **同秒完成多条 dispatch，notes 留下的并非最新 3 条。** 本次依次完成 readme、archive-fixture-0、1、2、3，notes 最终保留 2、3、0，较新的 1 先被归档。`recorded_at` 仅秒精度，`notes._finished_at` 无更细顺序；ties 沿合同原排序。证据：commands.jsonl seq 86–105、notes-after-five-completed.md、archive-after-five-completed.md。
3. **指南末尾 JSON 复现命令错误。** `just --json doctor` exit 1：`error: --dump used with unexpected argument: doctor`；`just doctor --json` exit 0 并返回 JSON。证据 commands.jsonl seq 25–29。通用写法应为 `just <命令> --json`。

## 证据与边界

- `commands.jsonl`：每条 CLI 命令的 argv、cwd、env override、stdout/stderr、exit code，以及 fixture 写入和读出的实际产物。
- `*-before.json` / `*-after.json`：真实 dry-run、模拟未认证、模拟 gh 缺失、模拟 CI 红 dry-run 的 SHA256 全量快照。
- `assertions-final.json`：最终 104 条检查，102 通过、2 个产品行为失败。`assertions.json` 保留初始记录，其中两条 B 断言曾误用 `git` 字段；原始 CLI 实际输出是正确的 `git_state=ok`，更正依据在 `qa-assertion-corrections.json`，未改原日志。
- `run_cli_qa.py`：本次一次性 QA 驱动；仅能对干净 fixture 重跑。所有 CLI 行为走 just，不替代应用逻辑。
- 此处产品 fixture 的 just test 仅检验其 README 非空；它验证流程，不代表真实 skills 仓测试。README「合入」仅测试 receipt 文本，未执行 git merge/push。两条真实 PR 只用于读取状态，未更改 GitHub。
