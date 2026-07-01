# Journal, State & Plans

Working memory lives under a repo-local `.process-work/` directory. Git records *what*
changed; these files record *why* and *what is in flight*.

## Journal

`.process-work/journal/YYYY-MM-DD.md` captures the reasoning behind decisions —
root-cause findings, why an approach was chosen over alternatives, non-obvious
constraints. Write it as decisions are made, not at the end. Convert relative dates
("yesterday") to absolute ones.

## Branch-scoped state

`.process-work/state/<branch-slug>.md` is per-branch working memory: active work,
open risks, the next concrete action. It is the primary signal when restoring context
after a break. One file per branch; other agents' state files are read-only to you.

## Plans

`.process-work/plans/YYYY-MM-DD-<feature>.md` holds the current implementation plan
(from the plan phase). Archived to `.process-work/plans/archive/` on merge. Designs
from the brainstorm phase live beside plans as `design-<topic>.md`.
