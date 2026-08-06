# /execute

Build the plan task by task, test-driven. Re-read the kernel
(`docs/process/kernel.md`) and `docs/process/mandatory-rules.md` first — a long
build compacts, and the rules bind every task, not just the first. Run
`uv run scripts/process/process_context.py` for the next unchecked task and
load only `tasks.md` plus the files that task names — never `specs/`
recursively. Then read
`docs/process/workflow.md` (Execute) and `docs/process/commits.md`. Per task:
write the failing test, see it fail, implement the minimum, see it pass, then
make one atomic conventional commit, and tick the task's checkbox in
`tasks.md` in the same commit (the checkboxes are the canonical progress
state). Keep tasks isolated so each is independently reviewable.

Next: `/review`.
