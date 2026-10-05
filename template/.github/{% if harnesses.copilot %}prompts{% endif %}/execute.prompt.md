# execute

Execute the plan task by task, test-driven. Re-read the kernel
(`docs/process/kernel.md`) and `docs/process/mandatory-rules.md` first — a long
build compacts, and the rules bind every task. Run
`uv run scripts/process/process_context.py --issue N` (the issue you execute)
for the next unchecked task. Then read
`docs/process/workflow.md` (Execute). Per task: failing test, see red, implement
the minimum, see green, commit atomically.
