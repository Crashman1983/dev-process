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
left untouched (you merge it yourself). Re-running is idempotent.

## The three hooks

| Hook | When | What | Bypass |
|---|---|---|---|
| pre-commit | each commit | blocks a direct commit to `main`/`master` | `ALLOW_MAIN_COMMIT=1` |
| pre-push | each push | runs the gate runner over all active modules; a failing gate blocks the push | `git push --no-verify` or `SKIP_PUSH_GATE=1` |
| post-commit | after each commit | runs the gate runner in `--warn` mode (reports drift, never blocks) | — |

The commit hook is fast (a branch check only); enforcement of the module gates
happens at push time, mirroring CI. The post-commit warning is advisory.

## Why delegate

The hooks call `scripts/process/gate_runner.py`, never a fixed gate list. Enable
or disable a module and the hooks adjust automatically — one owner for "which
gates run", shared with CI.
