# Commits & Branching

## Message format

Conventional Commits: `type: imperative subject` where `type` is one of
`feat | fix | docs | refactor | test | chore | perf`. Subject under 72 characters,
imperative mood, no trailing period. Body (optional) explains *why*, wraps at ~72.

## Atomicity

One logical change per commit. No multi-feature commits. A commit that touches tests
and implementation for the same behavior is atomic; a commit that mixes two unrelated
behaviors is not. A skipped gate or deliberately dropped scope is named in the body
(e.g. `skipped review: <reason>`).

## Branching

No direct commits to the main branch. Light work goes on a feature branch; heavy or
parallel work goes in an isolated worktree. Merge fast-forward-only after the tier's
review gate has passed: fetch → rebase → gate → `merge --ff-only` → push. A git
`pre-commit` hook guards the main branch and is bypassable for automation.
