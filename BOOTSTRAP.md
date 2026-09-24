# BOOTSTRAP — set up the dev-process

**Deutsch:** Diese Datei ist die eigenstaendige Setup-Anleitung fuer LLM-Agenten
und Menschen. Artefakte und Prozessdoku sind englisch; der Dialog mit dir laeuft
in deiner Sprache. Was der Prozess ist und warum, erklaert der Ueberblick
[`docs/UEBERBLICK.md`](docs/UEBERBLICK.md).

This file is self-contained. Any LLM or coding agent, in any harness, can
follow it; no pre-installed adapter is required.

## What this does

Installs a portable development process: a neutral methodology SSOT under
`docs/process/`, CI gates, and thin adapters for Claude Code / GitHub Copilot /
AGENTS.md. Works in an empty repo (greenfield) or an existing one (brownfield —
additive; it will not overwrite your files without asking).

All rendered artifacts are English; agents converse with the user in the
user's language. Not worth installing for throwaway prototypes or one-off
scripts — the process pays off for multi-session, multi-agent, or
contract/persistence/auth-touching work.

## Installation

1. Ensure `uv` is available (https://docs.astral.sh/uv/). The copy step needs
   no other tool. Runtime requirements for rendered gates and hooks are listed
   in [`docs/SYSTEM-REQUIREMENTS.md`](docs/SYSTEM-REQUIREMENTS.md).
   If the template repo is **private**, git needs a credential once —
   `gh auth setup-git` (GitHub CLI) or any git credential helper. Public repos
   need nothing.
2. From the target repository root, run:

       uvx copier copy gh:Crashman1983/dev-process .

   **Without `uv`** — same command tail, different runner (fallback ladder,
   each rung tested):

       # pipx (isolated, like uvx)
       pipx run copier copy gh:Crashman1983/dev-process .

       # bare python: one-off venv
       python3 -m venv .copier-venv
       .copier-venv/bin/pip install 'copier>=9.4'
       .copier-venv/bin/copier copy gh:Crashman1983/dev-process .
       # remove .copier-venv afterwards; do not commit it

   **If the `gh:` shorthand cannot resolve** (restricted network): clone
   first, copy from the local path. Note: a local clone renders the latest
   **tag**; pass `--vcs-ref=HEAD` for the branch tip.

       git clone https://github.com/Crashman1983/dev-process /tmp/dev-process
       uvx copier copy /tmp/dev-process .

3. Answer the prompts (four; the last one only matters for the issue gate):
   - `project_name` — human-readable name.
   - `harness` — one of `claude` | `copilot` | `agents_md` for the command
     adapters; the methodology and gates are harness-neutral either way.
   - `ci` — whether the `github` Actions workflow renders the `process-gates`
     job (default on). **With it off, nothing enforces the gates remotely** —
     local git hooks (`git_hooks` module) become the only enforcement pillar.
   - `github_repo` (OWNER/REPO, optional) for the issue gate. Headless: pass
     it via `--data` like the others.

   Everything else renders as the fixed standard set
   (`docs/process/start-here.md`, "The standard setup").
4. Commit the result. Then run the Spec Kit setup (pinned, one command
   sequence — see the rendered `docs/process/modules/speckit.md`, "Setup"),
   and let the LLM guide the Greenfield or Brownfield setup through
   `docs/process/start-here.md` before further work.

After copying, the process is installed, but the project is not yet onboarded
as a product project. The LLM should use `docs/process/start-here.md` to
clarify Greenfield or Brownfield in a brainstorming-style dialogue, confirm
assumptions, and only then write real project artifacts.

## Headless agent setup

copier asks its questions interactively; agent harnesses (Claude Code, Codex,
Copilot, and friends) have no TTY for that. Pass all answers on the command
line instead:

    # standard setup
    uvx copier copy --defaults \
      --data project_name="<project name>" \
      --data harness=agents_md \
      --data 'ci={"github": true}' \
      --skip 'CLAUDE.md' --skip 'AGENTS.md' \
      gh:Crashman1983/dev-process .

    # expert opt-out only: override the fixed standard module set
    uvx copier copy --defaults \
      --data project_name="<project name>" \
      --data harness=claude \
      --data 'modules={"speckit": true, "doc_drift_gate": true, "arch_onboarding": false, "feature_registry": true, "github_issues": true, "git_hooks": true, "sbom": true, "telemetry": true, "design_contracts": false}' \
      --data 'ci={"github": true}' \
      --skip 'CLAUDE.md' --skip 'AGENTS.md' \
      gh:Crashman1983/dev-process .

- `--defaults` answers everything not passed explicitly; no interactive prompt
  may remain.
- When you pass a dictionary (`modules`, `ci`), pass it **complete**, not
  just the changed keys — a passed `modules` overrides the standard set
  entirely; omit it to get the standard setup.
- `--skip 'CLAUDE.md' --skip 'AGENTS.md'` protects brownfield repos: without a
  TTY, a content conflict otherwise aborts mid-render and leaves a
  half-installed state, while `--skip` keeps the existing file untouched and
  lets the run complete. **Never** use `--overwrite` in a repo you do not own.
- The same holds for every other file the template renders at a path your
  repo already uses. Check first and add a `--skip` for each that exists:
  `.pre-commit-config.yaml`, `PRODUCT.md`, `ARCHITECTURE.md`,
  `THIRD-PARTY-NOTICES.md`, `.github/copilot-instructions.md`. Then merge
  them as below.

**Merge skipped adapters:** if an existing `CLAUDE.md`/`AGENTS.md` was
skipped, copy the block between `<!-- KERNEL:START -->` and
`<!-- KERNEL:END -->` from `docs/process/kernel.md` (always rendered — the
canonical kernel source, present even when every adapter was skipped) into your
existing file and add a pointer to `docs/process/start-here.md`.

**Merge the other skipped files** (render the template once into an empty
scratch directory to have the originals at hand):
- `.pre-commit-config.yaml` — pre-commit reads one config: add the template's
  two hooks (`no-commit-to-branch` at the pre-commit stage, the local
  `process-gates` hook at pre-push) to yours.
- `PRODUCT.md` — the product-frame gate reads the template's layout
  (`status:` line and sections); move your content into it.
- `ARCHITECTURE.md` — add the template's `arch` block (inert example first)
  to your file; the arch-onboarding gate reads only that block.
- `THIRD-PARTY-NOTICES.md` — append the template's Spec Kit section.

**Verification (mandatory):** claim "installed" only after these checks
(use `python3` if `python` is not on PATH):

    uv run scripts/process/gate_runner.py   # must exit 0
    git status --porcelain                   # brownfield: added files only

**Version check:** confirm the render matches the docs you are following. The
rendered project records its template version in `.copier-answers.yml` (the
`_commit:` line — a tag, or `<tag>.post…` for a HEAD install); compare it to
the version the template README advertises. The default `copier copy gh:…`
renders the latest **tag** — if that lags the README, pass `--vcs-ref=HEAD`
(or `git clone` + `--vcs-ref=HEAD`) to get the branch tip, or the tag is
simply behind and the maintainer needs to cut a release.

The gate runner carries PEP 723 metadata; `uv run` supplies Python and
`PyYAML>=6` without a system Python installation.

## Recommended order

1. Install the standard setup (the prompts above).
2. Run the start-here dialogue (greenfield/brownfield, goal, stack, risks) —
   content-driven gates stay honestly inert until their artifacts exist, so
   the standard set never blocks an empty project.
3. Onboard area by area as `docs/process/start-here.md` describes.

## Brownfield notes

- copier never silently overwrites an existing file. On a content conflict it
  prompts you per file (interactive); non-interactive runs abort mid-render
  unless the conflicting files are excluded via `--skip` (safe, see the
  headless setup above) or forced with `--overwrite` (destructive — avoid).
- If you already have a `CLAUDE.md` / `AGENTS.md`, copier will flag the conflict —
  merge the process kernel (the `KERNEL:START`/`KERNEL:END` block) into yours,
  or accept the template's version.

## Parallel agents (optional)

The process runs fine with one agent at a time. To let several agents work
in parallel — one worktree and branch per issue, a steward that assigns work
and merges finished branches as a batch — the rendered repo already carries
the scripts; three steps switch it on:

1. **Set the model policy.** `docs/process/model-policy.json` names the model
   per phase and tier, the command that starts a worker session, the runner
   (`detached` headless, or `tmux` for visible windows a human can open) and
   `max_workers`. Its `_comment` explains every key. It is executable
   configuration: review changes to it like CI configuration.
2. **Keep the kernel loaded across compaction** (Claude Code): run
   `python3 scripts/process/rehydrate.py --install` once and commit the
   resulting `.claude/settings.json`. After every compaction or resume, the
   hook re-injects the kernel, the mandatory rules and the active plan's
   decisions; `--check` reports whether it is installed.
3. **Start the steward.** In a session on the main clone, run the `steward`
   command (Claude Code; with another harness, the same scripts work by hand). It reads the situation table (`python3 scripts/process/tower.py`),
   starts workers (`python3 scripts/process/dispatch.py start --issue N --phase
   plan|execute|review`), relays questions, and merges finished branches as a
   train (`python3 scripts/process/train.py plan`, then `run`).

Useful by hand: `dispatch.py list` shows every worker and its last line,
`dispatch.py log <branch>` more of it, `dispatch.py say <branch> "…"` types an
answer into a tmux worker, `dispatch.py stop <branch>` stops it. A phase can
run on another host (a cloud session, a second machine) via
`phases.<phase>.remote` in the policy; workers there report through git and
`tower.py --remote` shows them. Details: `docs/process/tower.md` and
`docs/process/train.md` in the rendered repo.

## Later: updating the process

Pull a newer process version with a clean working tree
(`git status --porcelain` empty). **Use the helper** — it re-asserts every
recorded answer, so no module silently changes:

    uv run scripts/process/template_update.py            # add --ref <tag> to pick a release

A project that **owns** some rendered files (a gate it extended, a command it
rewrote) lists them in a `.process-owned` file at the repo root (one path or
glob per line). The helper keeps every owned file as committed and writes the
template's own change to each of them (old release render → new release
render) to `.process-work/template-delta/<ref>/<path>.diff` — the exact delta
to port by hand, without the noise of the local divergence. Delete that
directory once ported; it is working memory, not a commit.

After any update, re-run
`uvx pre-commit install --hook-type pre-commit --hook-type pre-push` (the
`git-hooks` module is part of the standard set), then the gate runner.

**Plain copier, if you must.** `modules` is a derived answer (`when: false`):
copier recomputes it from the template default on every update, so a module
you switched off comes back unless you pass the **complete** dictionary on
every update. The standard set is:

    uvx copier update --defaults \
      --data 'modules={"speckit": true, "doc_drift_gate": true, "arch_onboarding": true, "feature_registry": true, "github_issues": true, "git_hooks": true, "sbom": true, "telemetry": true, "design_contracts": true}'

Setting a module to `false` makes `copier update` **remove** its rendered
files (gate script, module doc), and the gate stops running — check the diff
before committing. Do NOT `--skip` the anchor files on an update: copier's
three-way merge preserves your local anchor extensions anyway, while a
skipped anchor keeps the OLD kernel block and turns the kernel gate red.
`update` checks out the latest **tagged** release by default. **If the
project was installed with `--vcs-ref=HEAD`** (a `.post…` version in
`.copier-answers.yml`), a default update refuses with "Downgrades are not
supported" — pass `--vcs-ref=HEAD` here too.

**A project on a release older than v2.24.0** carries an update helper that
wraps empty answers in extra quotes on every run: copy this repository's
`template/scripts/process/template_update.py` over the project's copy first,
then update.

**Important:** Do not hand-edit `.copier-answers.yml` to enable a module.
`copier update` reads that file as the *old* state: after a hand edit, the old
and new renders are identical, the missing module files count as intentional
local deletions, and the module is never rendered. Always pass new answers via
`--data`; copier rewrites the answers file itself afterwards.

Install the git hooks once per clone (they live in host-local `.git/hooks`,
not version control):

    uvx pre-commit install --hook-type pre-commit --hook-type pre-push
