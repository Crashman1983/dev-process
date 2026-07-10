# BOOTSTRAP — set up the dev-process

**Deutsch:** Diese Datei ist die eigenstaendige Setup-Anleitung fuer LLM-Agenten
und Menschen. Artefakte und Prozessdoku sind englisch; der Dialog mit dir laeuft
in deiner Sprache.

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

3. Answer the prompts:
   - `project_name` — human-readable name.
   - `harnesses` — which adapters to install (`copilot`, `agents_md`); Claude Code
     is always installed.
   - `profile` — a module preset (`minimal` | `solo` | `team` | `custom`) that
     derives the `modules` default. Pick the closest fit; the next question
     shows the derived set for adjustment. Harden later via `copier update`
     (the ratchet in `docs/process/start-here.md`).
   - `modules` — which opt-in process modules to enable (default derived from
     the profile; adjust freely).
   - `ci` — which CI adapters render the `process-gates` job (`github`: Actions
     workflow, default on; `gitlab`: includable job + root `.gitlab-ci.yml`
     shim). **With both off, nothing enforces the gates remotely** — local git
     hooks (`git_hooks` module) become the only enforcement pillar.
   - Two modules add conditional prompts: `github_issues` asks for
     `github_repo` (OWNER/REPO, optional) and `parity` asks for
     `parity_surfaces` (canonical surface list). Headless: pass them via
     `--data` like the others.
4. Commit the result. Then let the LLM guide the Greenfield or Brownfield setup
   through `docs/process/start-here.md` before further work.

After copying, the process is installed, but the project is not yet onboarded
as a product project. The LLM should use `docs/process/start-here.md` to
clarify Greenfield or Brownfield in a brainstorming-style dialogue, confirm
assumptions, and only then write real project artifacts.

## Headless agent setup

copier asks its questions interactively; agent harnesses (Claude Code, Codex,
Copilot, and friends) have no TTY for that. Pass all answers on the command
line instead:

    # simple: pick a profile, let it derive the module set
    uvx copier copy --defaults \
      --data project_name="<project name>" \
      --data 'harnesses={"copilot": false, "agents_md": true}' \
      --data profile=solo \
      --data 'ci={"github": true, "gitlab": false}' \
      --skip 'CLAUDE.md' --skip 'AGENTS.md' \
      gh:Crashman1983/dev-process .

    # fine-grained: profile=custom plus the complete modules dictionary
    uvx copier copy --defaults \
      --data project_name="<project name>" \
      --data 'harnesses={"copilot": false, "agents_md": true}' \
      --data profile=custom \
      --data 'modules={"doc_drift_gate": false, "arch_onboarding": false, "feature_registry": false, "github_issues": false, "contracts_drift": false, "git_hooks": false, "contract_first": false, "parity": false, "security_floor": false, "sbom": false, "telemetry": false, "arch_docs": false, "github_master": false}' \
      --data 'ci={"github": true, "gitlab": false}' \
      --skip 'CLAUDE.md' --skip 'AGENTS.md' \
      gh:Crashman1983/dev-process .

- `--defaults` answers everything not passed explicitly; no interactive prompt
  may remain.
- When you pass a dictionary (`harnesses`, `modules`, `ci`), pass it
  **complete**, not just the changed keys. Passing `modules` overrides the
  profile-derived set entirely — omit it to let the profile decide.
- `--skip 'CLAUDE.md' --skip 'AGENTS.md'` protects brownfield repos: without a
  TTY, a content conflict otherwise aborts mid-render and leaves a
  half-installed state, while `--skip` keeps the existing file untouched and
  lets the run complete. **Never** use `--overwrite` in a repo you do not own.

**Merge skipped adapters:** if an existing `CLAUDE.md`/`AGENTS.md` was
skipped, copy the block between `<!-- KERNEL:START -->` and
`<!-- KERNEL:END -->` from `docs/process/kernel.md` (always rendered — the
canonical kernel source, present even when every adapter was skipped) into your
existing file and add a pointer to `docs/process/start-here.md`.

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

Module choice happens at install time, but the clarifying questions live in
`docs/process/start-here.md` — after the install. If the module choice is not
yet settled:

1. Install minimally (`--data profile=minimal` — core gates only).
2. Run the start-here dialogue (greenfield/brownfield, goal, stack, risks).
3. Derive the module choice from the answers by applying the **hardening
   ratchet** in `docs/process/start-here.md` — every optional module has at
   least one named trigger there; switch a module on when its trigger appears.
4. Retrofit modules as described under [Later](#later).

If the choice is already known, set it directly at install time.

## Brownfield notes

- copier never silently overwrites an existing file. On a content conflict it
  prompts you per file (interactive); non-interactive runs abort mid-render
  unless the conflicting files are excluded via `--skip` (safe, see the
  headless setup above) or forced with `--overwrite` (destructive — avoid).
- If you already have a `CLAUDE.md` / `AGENTS.md`, copier will flag the conflict —
  merge the process kernel (the `KERNEL:START`/`KERNEL:END` block) into yours,
  or accept the template's version.
- If you enable `ci.gitlab` in a repo that already has a `.gitlab-ci.yml`, add
  `--skip '.gitlab-ci.yml'` and merge the single `include:` line from the
  template shim by hand — the actual job lives collision-free under
  `.gitlab/ci/process-gates.gitlab-ci.yml`.

## Later

Add a module or pull an updated process version — with a clean working tree
(`git status --porcelain` empty), then:

    uvx copier update --defaults \
      --data 'modules={"doc_drift_gate": true, "arch_onboarding": false, "feature_registry": false, "github_issues": false, "contracts_drift": false, "git_hooks": false, "contract_first": false, "parity": false, "security_floor": false, "sbom": false, "telemetry": false, "arch_docs": false, "github_master": false}' 

Do NOT `--skip` the anchor files here: copier's three-way merge preserves your
local anchor extensions anyway, while a skipped anchor keeps the OLD kernel
block and turns the kernel gate red after the update. After any update, re-run
`uv run scripts/process/install_hooks.py` if the `git-hooks` module is active —
the installed hooks are copies and do not update themselves.

The install-time `profile` only seeded the initial modules answer — on update,
the **recorded `modules` dict wins**, so passing a different profile alone is a
silent no-op; always pass the new `modules` set explicitly, as above.
`--data` expects the **complete** `modules` dictionary with the new values,
not just the changed keys. `update` checks out the latest **tagged** template
release by default, preserves your local edits, and flags conflicts inline.
**If the project was installed with `--vcs-ref=HEAD`** (a `.post…` version in
`.copier-answers.yml`), a default update refuses with "Downgrades are not
supported" — pass `--vcs-ref=HEAD` here too.

Disabling works the same way (flag back to `false`): `copier update` then
**removes** that module's rendered files (gate script, module doc) and the
gate stops running — check the diff before committing.

**Important:** Do not hand-edit `.copier-answers.yml` to enable a module.
`copier update` reads that file as the *old* state: after a hand edit, the old
and new renders are identical, the missing module files count as intentional
local deletions, and the module is never rendered. Always pass new answers via
`--data`; copier rewrites the answers file itself afterwards.

If you enabled the `git-hooks` module, install the hooks once per clone (they
live in host-local `.git/hooks`, not version control):

    uv run scripts/process/install_hooks.py
