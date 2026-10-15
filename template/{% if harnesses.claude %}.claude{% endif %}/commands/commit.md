# /commit

**Project overlay:** if `docs/process/commands/commit.local.md` exists, read it
before you start — the project's own rules for this command, binding over
this file where it says so; a template doc this command sends you to may
have one beside it (`<doc>.local.md`), read with the doc
(`docs/process/overlays.md`).

Record one atomic conventional commit. Read
`docs/process/commits.md`. Use `type: imperative subject` under 72 characters,
one logical change per commit, and document skipped gates or dropped scope in
the body. No direct commits to `main`; work on a feature branch and merge only
after the review gate has passed — locally or via PR/MR (merge routes:
`docs/process/commits.md`).
