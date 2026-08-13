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

**Execution engine is free, artifacts are not.** Driving this phase with a
subagent-per-task engine (e.g. a Superpowers-style skill: fresh implementer
per task, per-task review loop, model routed by task complexity) is a valid —
often better — way to run it, provided the invariants hold: tasks come from
the plan/`tasks.md`, checkboxes are ticked in the artifact per task, the
test-first order stands, commits stay atomic, and the Tier-2+ **merge review
remains the independent, attested review** (`/review`) — a per-task reviewer
loop reduces defects but does not replace the attestation.

**[P] groups run as "parallel edit, serial commit".** When `tasks.md` marks
tasks `[P]`, dispatch them as concurrent subagents in the SAME worktree —
three invariants make that safe:
1. **Subagents edit, they never commit.** Each gets its file packet (its
   tasks' named files, plus explicitly forbidden paths) and returns its
   test-first evidence (failing run seen, green run) as its result —
   disjoint files are race-free, a shared git index is not.
2. **The orchestrator serialises each task's tail** — atomic commit,
   checkbox tick in `tasks.md` in that commit, gate run — in dependency
   order, not wallclock order. Every existing invariant holds verbatim;
   only the thinking and writing runs in parallel.
3. **`[P]` means no shared touchpoint at all** — not "different features":
   two tasks that each add a line to the same barrel export, manifest, or
   generated index are NOT `[P]` (`/plan` sets the markers under that
   definition; trust them, do not re-derive).

**Calibrate the engine's review spend** (review cost is the budget lever):
per-task reviews only for owner/integration tasks — mechanical tasks
(registry updates, pure test tasks) batch at checkpoints; rounds 2+ review
the delta (`make_review_bundle.py --since`); and let the engine's final
whole-branch review BE the attested merge review (fresh process on the
bundle, REVIEW line) — one deep review on the strongest model, not two.

Next: `/review`.
