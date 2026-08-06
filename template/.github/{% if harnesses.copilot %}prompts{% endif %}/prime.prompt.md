# prime

Restore context cheaply. Re-read the kernel (`docs/process/kernel.md`) and
`docs/process/mandatory-rules.md` first — a break or compaction may have
dropped the always-on rules. Then run
`uv run scripts/process/process_context.py` and read ONLY what it names
(branch state file, this branch's latest journal shard, the active plan);
read `PRODUCT.md` only when the next action is product-shaped.
Name current state and the next concrete action.
