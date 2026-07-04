# Design: parallel friction (SP17)

**Date:** 2026-07-03
**Status:** approved (scope: the parallel-agent friction a maintainer asked
about — the process enables independent parallelism but has one shared-per-day
file every effort contends on, and the serialized-integration reality is
undocumented)
**Slice:** shard the journal per branch (as state and plans already are) so
parallel *execution* never contends on a file, and name the
serialized-integration trade-off honestly so the friction is understood, not
surprising.

## Gap

The process is built for independent parallel work — the isolation invariant
(`commits.md`: one feature branch/worktree per effort), per-branch state
(`.process-work/state/<branch-slug>.md`), and per-feature plans
(`.process-work/plans/YYYY-MM-DD-<feature>.md`) are all contention-free. **One
working-memory file is not:** the journal at
`.process-work/journal/YYYY-MM-DD.md` is a single file per day that every
parallel effort appends to, so two efforts writing on the same day conflict.
This is the concrete friction — and it was hit in practice (a hand union-merge
of the daily journal during this very process's development).

Separately, the *serialized integration* that ff-only merging imposes
(fetch → rebase → gate → merge → push, one branch at a time) is real and by
design, but undocumented — so its rebase-and-re-gate cost reads as a surprise
rather than the deliberate price of "every merge is green against the real
latest main".

## Decision 1 — shard the journal per branch

The journal convention becomes `.process-work/journal/<branch-slug>/YYYY-MM-DD.md`
for any parallel effort; a top-level `.process-work/journal/YYYY-MM-DD.md` stays
valid for solo/single-effort work. This mirrors what state and plans already
do: working memory is owned per effort, so parallel branches never touch the
same file and merge cleanly (each shard is a distinct path). The cross-project
daily view is recovered by globbing — nothing is lost.

**Compatibility (load-bearing):** the telemetry gate and cockpit already read
journals with a recursive `**/*.md` glob, so a sharded path is picked up
unchanged — proven by a new test. The telemetry module doc's example path is
updated to the sharded form and points at the convention owner.

## Decision 2 — a "Parallel efforts" section that names the trade-off

`journal-state-plans.md` gains a section stating plainly: working memory is
sharded per effort (state per-branch, plans per-feature, journal per-branch) so
parallel *execution* contends on nothing; integration is *serialized* by ff-only
by design, so the friction lives at the merge (rebase onto the moved main,
re-run the gates) — that is the price of a linear history where every merge
passed the gates against the actual latest main, not just in isolation; two
efforts on the same owner declare phase-of or supersede (mandatory rule 4),
never race. `commits.md`'s isolation invariant points at it.

## Out of scope

Any change to ff-only itself (the serialization *is* the correctness guarantee
— the fix is to shard execution memory and document the merge cost, not to
parallelize integration); a merge-train / queue tool (project tooling, not
template methodology); claim/heartbeat mechanics (harness/coordination-specific,
not shipped by the neutral template). Version 1.5.2 (convention refinement +
guidance; no new module or gate).
