# Module: git-hooks

Opt-in. Installs local git hooks that enforce the process on every commit and
push — the guarantee that holds when nobody is watching. The hooks delegate to
the manifest-aware gate runner, so they cover whatever modules you enabled
without naming any of them.

## Install

The hooks live in `.git/hooks`, which is host-local and not versioned — so the
installer is the source of truth. Run it once per clone (and after enabling new
modules):

    bash scripts/process/install-hooks.sh

It is brownfield-safe: a pre-existing hook that dev-process did not write is
left untouched (you merge it yourself). Re-running is idempotent. If
`core.hooksPath` is configured (hook managers like husky, or a global
`~/.githooks`), the installer refuses — integrate the hook contents into your
manager manually instead.

**Runtime requirement:** the pre-push and post-commit hooks run
`python3 scripts/process/gate_runner.py`, which needs `PyYAML>=6` importable
by that `python3` **at commit/push time** (a venv only on PATH during
installation does not help). Without it, the runner exits with a one-line
install hint.

## The three hooks

| Hook | When | What | Bypass |
|---|---|---|---|
| pre-commit | each commit | blocks a direct commit to `main`/`master` | `ALLOW_MAIN_COMMIT=1` |
| pre-push | each push | gates the **pushed commits** — each pushed tip is checked out into a throwaway worktree and the gate runner runs there; a failing gate blocks the push | `git push --no-verify` or `SKIP_PUSH_GATE=1` |
| post-commit | after each commit | runs the gate runner in `--warn` mode (reports drift, never blocks) | — |

The commit hook is fast (a branch check only); the push-time gate checks the
**commits being pushed**, not the working tree: each pushed tip is materialized
in a throwaway detached `git worktree` and the gate runner runs against that, so
local uncommitted state can neither mask nor cause a failure, and the check is
parallel-safe (no `stash`, no HEAD move). Where CI runs the gate on the pushed
commits it remains the authority; the post-commit warning is advisory.

## Why delegate

The hooks call `scripts/process/gate_runner.py`, never a fixed gate list. Enable
or disable a module and the hooks adjust automatically — one owner for "which
gates run", shared with CI.
