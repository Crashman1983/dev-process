# Commits & Branching

## Message format

Conventional Commits: `type: imperative subject` where `type` is one of
`feat | fix | docs | refactor | test | chore | perf`. Subject under 72 characters,
imperative mood, no trailing period. Body (optional) explains *why*, wraps at ~72.
Mention the plan slug or issue ref (subject or body) when the commit implements
planned work — that mention is what lets `trace.py` correlate commits with the
story/plan/review chain.

## Atomicity

One logical change per commit. No multi-feature commits. A commit that touches tests
and implementation for the same behavior is atomic; a commit that mixes two unrelated
behaviors is not. A skipped gate or deliberately dropped scope is named in the body
(e.g. `skipped review: <reason>`).

## Branching

No direct commits to the main branch. The invariant is *isolation*: one feature
branch per effort, no cross-contamination between parallel efforts. A feature branch
is the default. Git worktrees are one isolation technique for when several agents or
tasks share a single machine and clone — separate clones, sessions, or sandboxes
satisfy the invariant just as well; the mechanism is the environment's choice. How
parallel efforts stay contention-free during execution and serialize at the merge is
in `journal-state-plans.md` (Parallel efforts).

## Merging

Merge only after the tier's review gate has passed (mandatory rule 7). Two
equivalent routes:

- **Local:** fetch → rebase → gate → **archive the plan** → `merge --ff-only` → push.
- **Hosted (PR/MR):** open a pull/merge request; the review gate runs as the PR
  review plus the `process-gates` CI job, and a linear-history merge ("rebase and
  merge" or a fast-forward-only setting) is the `--ff-only` equivalent. Where the
  platform enforces squash merges, atomicity shifts up one level: one logical
  change per PR. **Archive the plan in the last commit on the branch, before merge.**

**Archiving the plan is a merge step, not an afterthought.** The last commit on
the feature branch (before merge) moves the plan file from `.process-work/plans/`
to `.process-work/plans/archive/` — this is what the review-presence gate keys on
(`journal-state-plans.md`): it scans only the archive, so a Tier 2+ plan left in
the active directory is never presence-checked. Do it before the merge, while you
can still commit on the branch; archiving after the merge would need a direct
commit to the main branch, which the branching rule (and the `git-hooks`
pre-commit) forbid.

When the optional `git-hooks` module is installed, a `pre-commit` hook enforces the
no-direct-main rule locally (bypassable for automation, and for the one-time
onboarding/baseline commit, via `ALLOW_MAIN_COMMIT=1`).
