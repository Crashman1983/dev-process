# /commit

Record one atomic conventional commit. Read
`docs/process/commits.md`. Use `type: imperative subject` under 72 characters,
one logical change per commit, and document skipped gates or dropped scope in
the body. No direct commits to `main`; work on a feature branch and merge only
after the review gate has passed — locally or via PR/MR (merge routes:
`docs/process/commits.md`).
