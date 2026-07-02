# SP4 Slice 1 — `git_hooks` module design

**Status:** approved (maintainer, 2026-07-01), ready for `writing-plans`.

## 1. Context & goal

`dev-process` names local **git-hook enforcement** as one of its three durability
pillars (README: "Durchsetzung: CI-Gates, git-Hooks"; `commits.md`: "a `pre-commit`
hook guards the main branch"). But the template ships **no hook and no installer** —
only the CI runner (`process-gates.yml`) exists. The methodology promises something
the template does not deliver. This slice closes that gap with an opt-in `git_hooks`
module: a rendered installer that wires three hooks which **delegate to the existing
manifest-aware `gate_runner.py`** (no hard-coded gate list — Rule 5, one owner) and
are **brownfield-safe** (never clobber a foreign hook).

First slice of the SP4–SP6 "complete like Kenni" program. Each module ships its own
`spec → plan → build → review → tag` cycle. This slice targets tag **v0.6.0**.

## 2. Scope

**In:** opt-in `git_hooks` module; `install-hooks.sh` installer; three hooks
(pre-commit main-guard, pre-push gate mirror, post-commit warn); a `--warn` mode on
`gate_runner.py`; module doc; `commits.md` reconciliation; BOOTSTRAP install step;
copier/conftest wiring; tests.

**Out (deliberately):** path-aware push gates (Kenni optimizes for a heavy test
suite; dev-process gates are all fast — run them all), staged-diff gates in
pre-commit (enforcement lives in pre-push), and any Kenni-specific hook content
(security-floor, e2e-wait-ratchet — those arrive with their own later slices).

## 3. Files

| File | Kind | Purpose |
|---|---|---|
| `template/scripts/process/{% raw %}{% if modules.git_hooks %}install-hooks.sh{% endif %}{% endraw %}` | verbatim shell (no `.jinja`) | idempotent, brownfield-safe installer |
| `template/scripts/process/gate_runner.py.jinja` | modify | add `--warn` mode |
| `template/docs/process/{% raw %}{% if modules.git_hooks %}modules{% endif %}{% endraw %}/git-hooks.md` | verbatim md | module doc |
| `template/docs/process/commits.md` | modify | reconcile the unconditional hook promise |
| `copier.yml` | modify | `git_hooks: false` in `modules.default` |
| `tests/conftest.py` | modify | `git_hooks: False` in the defaults dict |
| `BOOTSTRAP.md` | modify | document the one-time install step |
| `tests/test_git_hooks.py` | create | integration + unit tests |
| `README.md` | modify | module catalog + status → v0.6.0 |

Shell files ship **without** a `.jinja` suffix (verbatim, like `new_issue.sh`): the
hook bodies contain `${VAR:-0}` which is not a Jinja delimiter (`{{`/`{%`/`{#`), and
no project-specific value needs rendering. The path-conditional in the filename is
always evaluated regardless of suffix (copier `_render_parts`).

## 4. The hook set

All three hooks carry a sentinel first comment line `# dev-process-managed-hook`
(the installer's ownership marker) and `cd` to the repo root before doing work.

**pre-commit** — the universal no-direct-main rule, fast, no gates:
```bash
#!/usr/bin/env bash
# dev-process-managed-hook
branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null)"
if { [ "$branch" = "main" ] || [ "$branch" = "master" ]; } && [ "${ALLOW_MAIN_COMMIT:-0}" != "1" ]; then
  echo "✗ Direct commit to '$branch' blocked. Use a feature branch; ff-only merge to main." >&2
  echo "  Automation: ALLOW_MAIN_COMMIT=1 git commit ..." >&2
  exit 1
fi
exit 0
```

**pre-push** — local mirror of the CI merge gates; runs the manifest-aware runner
(all active gates), propagates its exit code so a failing gate blocks the push:
```bash
#!/usr/bin/env bash
# dev-process-managed-hook
[ "${SKIP_PUSH_GATE:-0}" = "1" ] && { echo "⚠ pre-push gate skipped (SKIP_PUSH_GATE=1)." >&2; exit 0; }
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0
cd "$REPO_ROOT" || exit 0
[ -f scripts/process/gate_runner.py ] || exit 0
python3 scripts/process/gate_runner.py
```
Bypass: `git push --no-verify` or `SKIP_PUSH_GATE=1`. No path-awareness — the runner
already skips inactive modules, and active gates are fast. stdin (pushed refs) is
ignored intentionally.

**post-commit** — warn-only drift feedback, never blocks:
```bash
#!/usr/bin/env bash
# dev-process-managed-hook
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0
cd "$REPO_ROOT" || exit 0
[ -f scripts/process/gate_runner.py ] || exit 0
python3 scripts/process/gate_runner.py --warn || true
```

## 5. `gate_runner.py --warn`

Minimal addition: run every active gate as today, but in `--warn` mode report
failures as a non-blocking warning and **always exit 0**. `--list` behaviour is
unchanged. Sketch:
```python
warn = "--warn" in sys.argv
...
if failed:
    if warn:
        print(f"⚠ gate warnings (not blocking): {', '.join(failed)}")
        return 0
    print(f"FAILED gates: {', '.join(failed)}")
    return 1
```

## 6. `install-hooks.sh` — brownfield-safe & idempotent

For each of the three hooks the installer resolves `.git/hooks/<name>` and:

- **absent** → write our hook, `chmod +x`.
- **exists, contains `# dev-process-managed-hook`** → overwrite (idempotent update of
  our own hook).
- **exists, foreign** (no marker) → print a warning naming the file and **skip it**
  (never clobber; the adopter merges manually or uses a hook manager like husky).

It resolves the repo root via `git rev-parse --show-toplevel` (errors out clearly if
not a git repo), `mkdir -p` the hooks dir, and prints a one-line summary of what was
installed vs. skipped. Re-running is safe on every host.

## 7. `commits.md` reconciliation

`commits.md` is core (always shipped, module-agnostic) yet currently promises the
pre-commit hook unconditionally. Reword to attribute the guard to the **optional
`git-hooks` module** so an adopter with the module off reads no false promise. The
reference is by name in prose only — **no markdown link to the module-conditional
file** (a hard link to `modules/git-hooks.md` would break the doc-drift gate when the
module is off).

## 8. BOOTSTRAP & module doc

BOOTSTRAP gains a short "Later / hooks" note: when `git_hooks` is enabled, run
`bash scripts/process/install-hooks.sh` once per clone (hooks live in `.git/hooks`,
which is host-local and unversioned — the installer is the source of truth). The
module doc (`git-hooks.md`) covers: what each hook does, the bypass envs
(`ALLOW_MAIN_COMMIT`, `SKIP_PUSH_GATE`, `--no-verify`), brownfield behaviour, and the
delegate-to-`gate_runner` design. Its only real slash-path backtick ref is
`scripts/process/gate_runner.py` (always present) — every other path stays a
placeholder or slash-less, keeping doc-drift green.

## 9. Honest ceiling

**Hard (deterministic, local):** the pre-commit main-guard actually blocks (exit 1
without the escape); pre-push runs the active gates and propagates their exit code.
No external system is involved, so there is no best-effort tier to fake. The one
intentionally soft behaviour is **post-commit warn-only**, by design (commit = inform,
push = enforce). No false-green: an inactive module contributes no gate, and the
installer never silently clobbers a foreign hook.

## 10. Testing

Integration tests render the template, `git init` the output, set a throwaway git
identity, run the installer, then exercise real behaviour:

- **main-guard:** on `main`, `git commit --allow-empty` → blocked (exit 1);
  `ALLOW_MAIN_COMMIT=1` → succeeds; on a feature branch → succeeds.
- **pre-push:** invoke `.git/hooks/pre-push </dev/null` directly (no remote needed —
  the hook runs the runner unconditionally). With an active failing gate → exit 1;
  `SKIP_PUSH_GATE=1` → exit 0.
- **post-commit:** a commit on a feature branch succeeds even when an active gate
  would fail (warn-only never blocks the commit).
- **brownfield:** pre-seed a foreign `.git/hooks/pre-commit` (no marker) → installer
  warns and leaves it byte-for-byte untouched.
- **idempotency:** running the installer twice leaves our managed hooks intact.

Unit test for `--warn`: render with `git_hooks` + a module whose gate fails (e.g.
`contracts_drift` with a sha256 pin that mismatches its artifact) →
`gate_runner.py --warn` exits 0 and prints the warning; the same without `--warn`
exits 1.

Module-off tests: no `install-hooks.sh` and no `git-hooks.md` when the module is off;
`gate_runner` without `--warn` is unchanged; neutrality (no Kenni-specific term leaks
into the shipped files); doc-drift stays green with the module doc present.

## 11. copier / conftest wiring

Add `git_hooks: false` to `copier.yml`'s `modules.default` and `git_hooks: False` to
the conftest defaults dict. No new copier question — the hooks need no project value.

## 12. Decisions resolved

- **Install mechanism:** rendered `install-hooks.sh` + documented one-time run (not
  `core.hooksPath`, not copier `_tasks`) — brownfield-safe, no task-trust, mirrors
  Kenni's proven model. (maintainer, 2026-07-01)
- **post-commit:** included in v1 as warn-only (like Kenni), not deferred. (maintainer)
- **git_hooks is opt-in**, not core-always — respects brownfield adopters who use a
  hook manager; `commits.md` is reconciled so the core methodology makes no
  unconditional hook promise.
- **Generic delegation:** hooks call `gate_runner.py`, never a hard-coded gate list,
  so the module composes with whatever other modules are active.
