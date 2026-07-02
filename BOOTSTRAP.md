# BOOTSTRAP — Entwicklungsprozess einrichten / set up the dev-process

**Deutsch:** Diese Datei ist eigenstaendig. Ein LLM oder Coding-Agent kann ihr
in jedem Harness folgen; ein vorinstallierter Adapter ist nicht noetig.

**English:** This file is self-contained. Any LLM or coding agent, in any
harness, can follow it; no pre-installed adapter is required.

## Was installiert wird / What this does

**Deutsch:** Installiert einen portablen Entwicklungsprozess: eine neutrale
Methodik-SSOT unter `docs/process/`, CI-Gates und duenne Adapter fuer Claude
Code, GitHub Copilot und AGENTS.md. Funktioniert in neuen Repositories
(Greenfield) und bestehenden Repositories (Brownfield, additiv; keine
stillschweigenden Ueberschreibungen).

**English:** Installs a portable development process: a neutral methodology SSOT under
`docs/process/`, CI gates, and thin adapters for Claude Code / GitHub Copilot /
AGENTS.md. Works in an empty repo (greenfield) or an existing one (brownfield —
additive; it will not overwrite your files without asking).

## Installation

1. Ensure `uv` is available (https://docs.astral.sh/uv/). The copy step needs
   no other tool. Runtime requirements for rendered gates and hooks are listed
   in [`docs/SYSTEM-REQUIREMENTS.md`](docs/SYSTEM-REQUIREMENTS.md).
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
4. Commit the result. Then let the LLM guide the Greenfield or Brownfield setup
   through `docs/process/start-here.md` before further work.

**Deutsch:** Nach dem Kopieren ist der Prozess installiert, aber das Projekt ist
noch nicht fachlich eingerichtet. Das LLM soll mit `docs/process/start-here.md`
brainstorming-artig Greenfield oder Brownfield klaeren, Annahmen bestaetigen
lassen und erst danach echte Projektartefakte schreiben.

**English:** After copying, the process is installed, but the project is not yet
onboarded as a product project. The LLM should use `docs/process/start-here.md`
to clarify Greenfield or Brownfield in a brainstorming-style dialogue, confirm
assumptions, and only then write real project artifacts.

## Brownfield-Hinweise / Brownfield notes

- copier never silently overwrites an existing file. On a content conflict it
  prompts you per file (interactive) or requires `--overwrite` (non-interactive/CI).
- If you already have a `CLAUDE.md` / `AGENTS.md`, copier will flag the conflict —
  merge the process kernel into yours, or accept the template's version.

## Spaeter / Later

Add a module or pull an updated process version: re-answer (or edit
`.copier-answers.yml`) and run `uvx copier update`. `update` checks out the
latest **tagged** template release by default and preserves your local edits,
flagging conflicts inline.

If you enabled the `git-hooks` module, install the hooks once per clone (they
live in host-local `.git/hooks`, not version control):

    bash scripts/process/install-hooks.sh
