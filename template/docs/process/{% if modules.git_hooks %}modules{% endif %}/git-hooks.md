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

## Honest ceiling

Hooks are client-side: a clone that never installs them enforces nothing
locally. CI (the `ci.github` adapter plus branch protection) remains the
enforcement authority; this module is the fast local mirror of it, and — in
a no-CI setup — the only pillar (`start-here.md`, enforcement wiring).
