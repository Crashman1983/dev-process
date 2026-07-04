# Journal, State & Plans

Working memory lives under a repo-local `.process-work/` directory. Git records *what*
changed; these files record *why* and *what is in flight*.

## Journal

The journal captures the reasoning behind decisions — root-cause findings, why an
approach was chosen over alternatives, non-obvious constraints. Write it as decisions
are made, not at the end. Convert relative dates ("yesterday") to absolute ones.

**Path — shard it per branch when efforts run in parallel.** A single
`.process-work/journal/YYYY-MM-DD.md` is fine for solo, single-effort work; but a
shared daily file is the one piece of working memory that two parallel efforts both
append to, so they conflict on merge. When more than one effort is in flight, write to
`.process-work/journal/<branch-slug>/YYYY-MM-DD.md` — per-branch, exactly as state and
plans are already sharded, so parallel efforts never touch the same file. The
cross-project daily view is recovered by globbing the shards; tooling that reads
journals does so recursively.

Journal duty scales with the tier: entries are expected from Tier 2 upward, or
whenever a non-obvious decision was made. Tier 0-1 changes need none — the
commit message carries them.

## Branch-scoped state

`.process-work/state/<branch-slug>.md` is per-branch working memory: active work,
open risks, the next concrete action. It is the primary signal when restoring context
after a break. One file per branch. Wherever other efforts' state files are visible
(shared checkout, worktrees, or after a merge), treat them as read-only.

## Plans

`.process-work/plans/YYYY-MM-DD-<feature>.md` holds the current implementation plan
(from the plan phase). Archived to `.process-work/plans/archive/` on merge. Designs
from the brainstorm phase live beside plans as `design-<topic>.md`.

## Parallel efforts

The process runs several efforts at once cleanly, and the split between what is
parallel and what is serialized is deliberate:

- **Execution is parallel and contention-free.** One feature branch or worktree per
  effort (the isolation invariant in `commits.md`), and all working memory is sharded
  per effort — state per branch, plans per feature, journal per branch. Two efforts in
  flight never write the same file, so nothing conflicts *while they run*.
- **Integration is serialized, by design.** Merging is fast-forward-only
  (fetch → rebase → gate → merge → push), one branch at a time. When another effort
  merges first, rebase onto the moved main and re-run the gates before merging. That
  rebase-and-re-gate is the friction — and it is the price of a linear history in which
  **every merge passed the gates against the actual latest main, not merely in
  isolation**. It is not a defect to remove; it is the guarantee.
- **Never two efforts on one owner.** Two efforts on the same behavior must declare
  *phase-of* or *supersede* (mandatory rule 4), never race — that is the one kind of
  parallelism the process forbids, because it produces conflicting accretion no merge
  can reconcile.
