# BOOTSTRAP — set up the dev-process in this repository

This file is self-contained. Any coding agent, in any harness, can follow it —
you do not need a pre-installed adapter.

## What this does

Installs a portable development process: a neutral methodology SSOT under
`docs/process/`, CI gates, and thin adapters for Claude Code / GitHub Copilot /
AGENTS.md. Works in an empty repo (greenfield) or an existing one (brownfield —
additive; it will not overwrite your files without asking).

## Do this

1. Ensure `uv` is available (https://docs.astral.sh/uv/). No other dependency.
   If the template repo is **private**, git needs a credential once —
   `gh auth setup-git` (GitHub CLI) or any git credential helper. Public repos
   need nothing.
2. From the target repository root, run:

       uvx copier copy gh:Crashman1983/dev-process .

3. Answer the prompts:
   - `project_name` — human-readable name.
   - `harnesses` — which adapters to install (`copilot`, `agents_md`); Claude Code
     is always installed.
   - `modules` — which opt-in process modules to enable (e.g. `doc_drift_gate`).
4. Commit the result. Read `docs/process/mandatory-rules.md` and
   `docs/process/risk-tiers.md` before further work.

## Brownfield notes

- copier never silently overwrites an existing file. On a content conflict it
  prompts you per file (interactive) or requires `--overwrite` (non-interactive/CI).
- If you already have a `CLAUDE.md` / `AGENTS.md`, copier will flag the conflict —
  merge the process kernel into yours, or accept the template's version.

## Later

Add a module or pull an updated process version: re-answer (or edit
`.copier-answers.yml`) and run `uvx copier update`. `update` checks out the
latest **tagged** template release by default and preserves your local edits,
flagging conflicts inline.

If you enabled the `git-hooks` module, install the hooks once per clone (they
live in host-local `.git/hooks`, not version control):

    bash scripts/process/install-hooks.sh
