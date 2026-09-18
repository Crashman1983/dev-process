# Module: git-hooks — local enforcement via pre-commit

The local enforcement pillar. Without CI (or before it runs), git hooks are
what stands between a rule and a silent violation. This module delegates to
the standard [pre-commit](https://pre-commit.com) framework instead of a
custom installer — one less thing to maintain, and a tool contributors
already know.

## What it ships

A rendered `.pre-commit-config.yaml` with two hooks:

- **`no-commit-to-branch`** (pre-commit stage, upstream standard hook):
  blocks direct commits to `main`/`master` — branch discipline
  (`commits.md`).
- **`process-gates`** (pre-push stage, local hook): runs
  `uv run scripts/process/gate_runner.py` — the same manifest-aware gates CI
  runs, so a push that would fail CI fails at your machine first.

## Install (once per clone)

```
uvx pre-commit install --hook-type pre-commit --hook-type pre-push
```

`pre-commit` manages `.git/hooks` itself and composes with hooks a project
already uses via its own config — the brownfield-additive property the old
custom installer provided, now owned by the standard tool. Re-run the same
command after a `copier update`; it is idempotent.

## Bypass — sanctioned and otherwise

- The **onboarding baseline commit** on main is the one sanctioned bypass:
  `SKIP=no-commit-to-branch git commit …`.
- Anything else (`--no-verify`, `SKIP=process-gates`) is a skipped gate:
  allowed in an emergency, documented in the commit body (mandatory rule 8),
  and caught by CI on push anyway.

## One hook manager — and a doctor for it

The pre-commit framework installs into `.git/hooks`. If `core.hooksPath` is
set (a second hook manager, a `.githooks/` directory, a global git config),
git reads hooks from *there* and every pre-commit registration is silently
inert — measured downstream: 25 days without a single local gate run,
discovered by accident. So: exactly one hook manager per repository. The
gate runner and `finish.py` run a **hook doctor** (`gate_invoke.py`) that
fails hard when this config coexists with a `core.hooksPath`, and notes a
clone that never installed the hooks. A registered check that cannot run is
a missing check, and a missing check is reported as a blocker, never as a
pass.

The pre-push stage also hands the review gate the push target
(`PRE_COMMIT_REMOTE_BRANCH`, set by the framework), which is what makes the
Tier 3 presence arm hard on a push to main and a note elsewhere
(`journal-state-plans.md`). A custom hook that replaces the framework must
export `PROCESS_PUSH_TARGETS` from git's stdin to keep that arm armed.

The doctor also covers the *other* manager: a tracked `.githooks/`
directory is only read when `core.hooksPath` points at it. Unset, git runs
whatever stale copy sits in `.git/hooks` — observed downstream: a months-old
copy of `pre-push` ran while the tracked one evolved, and a leaked
`GIT_DIR` from a test then flipped the real repository to `core.bare=true`
through it. The doctor fails hard on a populated `.githooks/` without the
matching `core.hooksPath`.

## Long-running hooks and agent tool calls

A hook that can run for minutes (a scoped test arm queued behind another
worktree's full run) must never be waited out inside an agent's tool call:
the call has its own timeout, it kills the push at the last percent, and
the retry starts from zero — observed downstream five times in a row. Two
rules: the hook waits **bounded** (minutes, not an hour) and then aborts
with who holds the resource and the way out; and the evidence is produced
**decoupled** from the push — a certify step run in the background that
records the tree, which the hook then reads instead of re-earning. An
agent that hits the bounded abort does other work and pushes again when
the lane is free or the certificate exists; it does not loop on the push.

## Honest ceiling

Hooks are client-side: a clone that never installs them enforces nothing
locally. CI (the `ci.github` adapter plus branch protection) remains the
enforcement authority; this module is the fast local mirror of it, and — in
a no-CI setup — the only pillar (`start-here.md`, enforcement wiring).
