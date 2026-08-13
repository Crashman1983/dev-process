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

Process bookkeeping (journal entry, plan checkboxes, state file) rides in the
work's commit or one adjacent commit — never a chain of per-step `record`/
`reconcile` commits. Evidence that changes no tracked artifact (logs, screenshots,
verification output) goes to the issue or PR as a comment, not into the history.

## Branching

No direct commits to the main branch. The invariant is *isolation*: one feature
branch per effort, no cross-contamination between parallel efforts. A feature branch
is the default — and it lives **days, not weeks**: the further a branch drifts from
main, the more the merge costs and the later the gates see the work (the small-batch
finding behind trunk-based development). A branch that keeps growing is a scope
signal — split the work, merge what is green. Git worktrees are one isolation technique for when several agents or
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

**Merge leaves no residue.** Delete the remote feature branch once it is
merged (enable GitHub's *Automatically delete head branches*, or run a
cleanup workflow), and remove the worktree that carried it
(`git worktree remove <path>`, then `git worktree prune`) — a landscape of
dead branches and orphaned worktrees is where the next agent picks the wrong
base.

The whole tail — archive, merge, branch delete, worktree removal,
publish/prune — is checkable as one verdict: `scripts/process/finish.py`
(`/finish`) verifies the branch is done (clearing pass, green gates, clean
tree) and prints the remaining steps in order. The tail failures it guards
against (merge without clearing pass, plan never archived, residue left
behind) were all observed in production; prefer the checker over improvising
the ritual from memory.

What a merged state becomes for consumers — version, changelog, tag — is the
release ritual: `docs/process/releases.md`.

When the optional `git-hooks` module is installed, a `pre-commit` hook enforces the
no-direct-main rule locally (bypassable for automation, and for the one-time
onboarding/baseline commit, via `SKIP=no-commit-to-branch`).
