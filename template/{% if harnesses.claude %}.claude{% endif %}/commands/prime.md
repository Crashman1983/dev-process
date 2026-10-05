# /prime

Restore working context after a break — cheaply. (After a compaction or a
resume the `SessionStart` hook `scripts/process/rehydrate.py` already
printed the kernel, the rules and the ledger into this session —
`rehydrate.py --check` says whether it is installed; `--install` adds it.
/prime is for the cases the hook does not cover.) Re-read the kernel
(`docs/process/kernel.md`) and `docs/process/mandatory-rules.md` first — a break
or compaction may have dropped the always-on rules from context. Then run
`uv run scripts/process/process_context.py` — pass `--issue N` when you know
the issue; without it the branch name decides, and on `main` you get only the
index of all plans and specs (`other_plans`/`other_specs`) — pick one and run
again with `--issue N`. Add `--cost` when the question is
what a session start costs in tokens — measure before cutting. One JSON with branch, state
file, the current work's plans (tier/issue and their `DECISION` ledger — the choices
made in dialogue that a compaction would have dropped), the next unchecked task, unresolved
markers, and the inbox size — and read ONLY what it names: the branch state
file, the latest journal shard of THIS branch (never the whole journal
history), the active plan. Read `PRODUCT.md` only when the next action is
product-shaped. Answer: what is in flight? What is the next concrete action?
When the inbox size is nonzero, read `.process-work/inbox.md` and name any item
to triage.
