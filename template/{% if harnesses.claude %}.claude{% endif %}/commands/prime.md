# /prime

Restore working context after a break — cheaply. Re-read the kernel
(`docs/process/kernel.md`) and `docs/process/mandatory-rules.md` first — a break
or compaction may have dropped the always-on rules from context. Then run
`uv run scripts/process/process_context.py` — one JSON with branch, state
file, active plans (tier/issue), the next unchecked task, unresolved
markers, and the inbox size — and read ONLY what it names: the branch state
file, the latest journal shard of THIS branch (never the whole journal
history), the active plan. Read `PRODUCT.md` only when the next action is
product-shaped. Answer: what is in flight? What is the next concrete action?
Any inbox item to triage?
