# prime

**Project overlay:** if `docs/process/commands/prime.local.md` exists, read it
before you start — the project's own rules for this command, binding over
this file where it says so; a template doc this command sends you to may
have one beside it (`<doc>.local.md`), read with the doc
(`docs/process/overlays.md`).

Restore context cheaply. Re-read the kernel (`docs/process/kernel.md`) and
`docs/process/mandatory-rules.md` first — a break or compaction may have
dropped the always-on rules. Then run
`uv run scripts/process/process_context.py` (`--issue N` when you know the
issue; on `main` without it you get only the index of plans and specs — pick
one, run again with `--issue N`) and read ONLY what it names
(branch state file, this branch's latest journal shard, the active plan);
read `PRODUCT.md` only when the next action is product-shaped.
Name current state and the next concrete action.

When the inbox size is nonzero, read `.process-work/inbox.md` and name any item
to triage.
