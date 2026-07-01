# git_hooks Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Ship an opt-in `git_hooks` module: a brownfield-safe `install-hooks.sh` that wires three hooks (pre-commit main-guard, pre-push gate mirror, post-commit warn) delegating to the manifest-aware `gate_runner.py`.

**Architecture:** Hooks call `gate_runner.py` (no hard-coded gate list — Rule 5). The installer writes hooks into `.git/hooks` (host-local; the script is the source of truth), skips any foreign hook (sentinel marker `# dev-process-managed-hook`), and is idempotent. `gate_runner` gains a `--warn` mode for the non-blocking post-commit hook.

**Tech Stack:** Python 3.11+ stdlib + pyyaml (gate_runner, pre-existing), bash (installer + hooks), copier templating, pytest.

**Design source:** `docs/design/2026-07-01-sp4-git-hooks-design.md`. **Branch:** `design/sp4-git-hooks` (spec already committed). **Target tag:** v0.6.0.

## Global Constraints

- Shell files ship **without** a `.jinja` suffix (verbatim, like `new_issue.sh`); the path-conditional in the filename is always evaluated regardless of suffix.
- Sentinel marker string is exactly `# dev-process-managed-hook` (installer detects ownership by grepping for it).
- Bypass envs: `ALLOW_MAIN_COMMIT=1` (pre-commit), `SKIP_PUSH_GATE=1` or `git push --no-verify` (pre-push).
- Hooks call `python3 scripts/process/gate_runner.py`; never a hard-coded gate name.
- No Kenni-specific term may leak into any shipped file. Neutrality list: `Kenni`, `KenniNext`, `Seb`, `Signal`, `SvelteKit`, `user_id=1`, `surface:ios`.
- Commit trailers on every commit:
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
  `Claude-Session: https://claude.ai/code/session_01MS9nrQC9f9WGhipvJ9NFpk`
- Run tests with `.venv/bin/python -m pytest`; lint with `.venv/bin/ruff`. Prefix every shell command with `cd /home/claude/Projekte/dev-process`.

## File Structure

| File | Task | Responsibility |
|---|---|---|
| `template/scripts/process/gate_runner.py.jinja` | 1 | add `--warn` mode |
| `copier.yml` | 1 | `git_hooks: false` default |
| `tests/conftest.py` | 1 | `git_hooks: False` default |
| `tests/test_git_hooks.py` | 1,2,3 | all tests (created T1, extended T2/T3) |
| `template/scripts/process/{% raw %}{% if modules.git_hooks %}install-hooks.sh{% endif %}{% endraw %}` | 2 | the installer + three hook bodies |
| `template/docs/process/{% raw %}{% if modules.git_hooks %}modules{% endif %}{% endraw %}/git-hooks.md` | 3 | module doc |
| `template/docs/process/commits.md` | 3 | reconcile the hook promise |
| `BOOTSTRAP.md` | 3 | document the install step |
| `README.md` | 3 | catalog + status → v0.6.0 |

---

### Task 1: `gate_runner --warn` + module wiring

**Files:**
- Modify: `template/scripts/process/gate_runner.py.jinja`
- Modify: `copier.yml`
- Modify: `tests/conftest.py`
- Create: `tests/test_git_hooks.py`

**Interfaces:**
- Produces: `gate_runner.py` supports `--warn` (runs active gates, reports failures as a non-blocking warning, always exit 0); the `git_hooks` module key exists so later tasks can render `git_hooks: True`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_git_hooks.py`:
```python
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

KENNI = ["Kenni", "KenniNext", "Seb", "Signal", "SvelteKit", "user_id=1", "surface:ios"]


def _render(render, tmp_path, **mods):
    m = {"git_hooks": True}
    m.update(mods)
    return render(tmp_path, {"project_name": "d", "modules": m})


def _runner(out: Path, *args):
    return subprocess.run(
        [sys.executable, str(out / "scripts/process/gate_runner.py"), *args],
        cwd=out, capture_output=True, text=True,
    )


def _failing_contract(out: Path):
    """Enable a hard-failing active gate: a contracts-drift pin/artifact mismatch."""
    (out / "contracts").mkdir(parents=True, exist_ok=True)
    (out / "contracts/api.json").write_bytes(b"NEW-bytes-edited")
    reg = out / "docs/process/contracts"
    reg.mkdir(parents=True, exist_ok=True)
    (reg / "orders-api.json").write_text(json.dumps({
        "id": "orders-api", "kind": "rest",
        "artifact": "contracts/api.json",
        "pin": "sha256:" + hashlib.sha256(b"OLD-bytes").hexdigest(),
    }))


def test_warn_mode_reports_but_exits_zero(render, tmp_path):
    out = _render(render, tmp_path, contracts_drift=True)
    _failing_contract(out)
    r = _runner(out, "--warn")
    assert r.returncode == 0, r.stdout
    assert "not blocking" in r.stdout
    assert "contracts-drift" in r.stdout


def test_without_warn_hard_fails(render, tmp_path):
    out = _render(render, tmp_path, contracts_drift=True)
    _failing_contract(out)
    r = _runner(out)
    assert r.returncode == 1
    assert "FAILED gates" in r.stdout


def test_list_unaffected(render, tmp_path):
    out = _render(render, tmp_path, contracts_drift=True)
    r = _runner(out, "--list")
    assert r.returncode == 0, r.stderr
    assert "contracts-drift" in r.stdout
    assert "not blocking" not in r.stdout


def test_answers_records_git_hooks(render, tmp_path):
    out = _render(render, tmp_path)
    assert "git_hooks: true" in (out / ".copier-answers.yml").read_text()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/claude/Projekte/dev-process && .venv/bin/python -m pytest tests/test_git_hooks.py -q`
Expected: `test_warn_mode_reports_but_exits_zero` FAILS (no `--warn` handling → exit 1, no "not blocking"); `test_answers_records_git_hooks` FAILS (key not in copier.yml/conftest yet). Others may pass incidentally.

- [ ] **Step 3: Add `--warn` to gate_runner**

In `template/scripts/process/gate_runner.py.jinja`, replace the `main()` body's post-`--list` section. Current:
```python
    failed = []
    for name in active:
        _key, cmd = GATES[name]
        print(f"== running {name} ==")
        if subprocess.run(cmd, cwd=root).returncode != 0:
            failed.append(name)
    if failed:
        print(f"FAILED gates: {', '.join(failed)}")
        return 1
    print(f"all {len(active)} active gate(s) passed")
    return 0
```
Replace with:
```python
    warn = "--warn" in sys.argv
    failed = []
    for name in active:
        _key, cmd = GATES[name]
        print(f"== running {name} ==")
        if subprocess.run(cmd, cwd=root).returncode != 0:
            failed.append(name)
    if failed:
        if warn:
            print(f"⚠ gate warnings (not blocking): {', '.join(failed)}")
            return 0
        print(f"FAILED gates: {', '.join(failed)}")
        return 1
    print(f"all {len(active)} active gate(s) passed")
    return 0
```

- [ ] **Step 4: Wire the module key**

In `copier.yml`, in the `modules.default` block, add after `contracts_drift: false`:
```yaml
    git_hooks: false
```

In `tests/conftest.py`, line 26, add `"git_hooks": False` to the modules dict:
```python
        "modules": {"doc_drift_gate": False, "arch_onboarding": False, "feature_registry": False, "github_issues": False, "contracts_drift": False, "git_hooks": False},
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /home/claude/Projekte/dev-process && .venv/bin/python -m pytest tests/test_git_hooks.py -q && .venv/bin/ruff check tests/test_git_hooks.py`
Expected: 4 passed; ruff clean.

- [ ] **Step 6: Commit**

```bash
cd /home/claude/Projekte/dev-process
git add template/scripts/process/gate_runner.py.jinja copier.yml tests/conftest.py tests/test_git_hooks.py
git commit -F - <<'EOF'
feat: add gate_runner --warn mode and git_hooks module key

--warn runs the active gates but reports failures as a non-blocking
warning (exit 0) — the mode the post-commit hook uses. Register the
git_hooks module key in copier defaults and conftest so the module renders.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01MS9nrQC9f9WGhipvJ9NFpk
EOF
```

---

### Task 2: `install-hooks.sh` + the three hooks

**Files:**
- Create: `template/scripts/process/{% raw %}{% if modules.git_hooks %}install-hooks.sh{% endif %}{% endraw %}`
- Modify: `tests/test_git_hooks.py` (append git-integration helpers + tests)

**Interfaces:**
- Consumes: `gate_runner.py` (+ `--warn` from Task 1).
- Produces: `scripts/process/install-hooks.sh` — writes `.git/hooks/{pre-commit,pre-push,post-commit}`, each carrying the sentinel marker; foreign hooks skipped.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_git_hooks.py`:
```python
def _hook_env(**extra):
    # Ensure `python3` inside the hooks resolves to the venv python (has pyyaml).
    env = dict(os.environ)
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env["PATH"]
    env.update(extra)
    return env


def _git(out: Path, *args, **kw):
    return subprocess.run(["git", *args], cwd=out, capture_output=True, text=True, **kw)


def _init_repo(out: Path, install=True):
    _git(out, "init", "-q", "-b", "main", check=True)
    _git(out, "config", "user.email", "t@example.com", check=True)
    _git(out, "config", "user.name", "Test", check=True)
    (out / "seed.txt").write_text("x")
    _git(out, "add", "seed.txt", check=True)
    _git(out, "commit", "-q", "-m", "init", check=True)  # no hooks yet
    if install:
        r = subprocess.run(["bash", "scripts/process/install-hooks.sh"],
                           cwd=out, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        return r
    return None


def test_main_guard_blocks_and_escapes(render, tmp_path):
    out = _render(render, tmp_path)
    _init_repo(out)
    blocked = _git(out, "commit", "--allow-empty", "-m", "x", env=_hook_env())
    assert blocked.returncode != 0
    assert "blocked" in blocked.stderr
    ok = _git(out, "commit", "--allow-empty", "-m", "x", env=_hook_env(ALLOW_MAIN_COMMIT="1"))
    assert ok.returncode == 0, ok.stderr


def test_feature_branch_commit_allowed(render, tmp_path):
    out = _render(render, tmp_path)
    _init_repo(out)
    _git(out, "checkout", "-q", "-b", "feat", check=True)
    r = _git(out, "commit", "--allow-empty", "-m", "x", env=_hook_env())
    assert r.returncode == 0, r.stderr


def test_pre_push_runs_gate_and_bypass(render, tmp_path):
    out = _render(render, tmp_path, contracts_drift=True)
    _init_repo(out)
    _failing_contract(out)
    blocked = subprocess.run(["bash", ".git/hooks/pre-push"], cwd=out,
                             stdin=subprocess.DEVNULL, capture_output=True, text=True, env=_hook_env())
    assert blocked.returncode == 1, blocked.stdout
    bypass = subprocess.run(["bash", ".git/hooks/pre-push"], cwd=out,
                            stdin=subprocess.DEVNULL, capture_output=True, text=True,
                            env=_hook_env(SKIP_PUSH_GATE="1"))
    assert bypass.returncode == 0


def test_post_commit_warns_never_blocks(render, tmp_path):
    out = _render(render, tmp_path, contracts_drift=True)
    _init_repo(out)
    _failing_contract(out)
    r = subprocess.run(["bash", ".git/hooks/post-commit"], cwd=out,
                       capture_output=True, text=True, env=_hook_env())
    assert r.returncode == 0, r.stdout
    assert "not blocking" in r.stdout


def test_brownfield_foreign_hook_untouched(render, tmp_path):
    out = _render(render, tmp_path)
    _init_repo(out, install=False)
    foreign = out / ".git/hooks/pre-commit"
    foreign.parent.mkdir(parents=True, exist_ok=True)
    foreign.write_text("#!/bin/sh\necho FOREIGN\n")
    foreign.chmod(0o755)
    r = subprocess.run(["bash", "scripts/process/install-hooks.sh"],
                       cwd=out, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert foreign.read_text() == "#!/bin/sh\necho FOREIGN\n"
    assert "not dev-process-managed" in r.stderr
    assert (out / ".git/hooks/pre-push").exists()  # non-conflicting hooks still installed


def test_installer_idempotent(render, tmp_path):
    out = _render(render, tmp_path)
    _init_repo(out)  # installs once
    r = subprocess.run(["bash", "scripts/process/install-hooks.sh"],
                       cwd=out, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "dev-process-managed-hook" in (out / ".git/hooks/pre-commit").read_text()


def test_installer_absent_when_module_off(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    assert not (out / "scripts/process/install-hooks.sh").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/claude/Projekte/dev-process && .venv/bin/python -m pytest tests/test_git_hooks.py -q -k "guard or branch or pre_push or post_commit or brownfield or idempotent or module_off"`
Expected: the install-dependent tests FAIL (install-hooks.sh does not exist → `_init_repo`'s install assert / bash errors). `test_installer_absent_when_module_off` PASSES already.

- [ ] **Step 3: Create the installer**

Create `template/scripts/process/{% raw %}{% if modules.git_hooks %}install-hooks.sh{% endif %}{% endraw %}` (no `.jinja` suffix) with exactly:
```bash
#!/usr/bin/env bash
# Installs dev-process git hooks into .git/hooks (host-local, not versioned;
# THIS script is the source of truth). Brownfield-safe: a pre-existing hook not
# managed by dev-process is left untouched. Idempotent — re-run any time.
set -e
MARKER="# dev-process-managed-hook"
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || {
  echo "✗ not a git repository — run this from inside your repo." >&2
  exit 1
}
HOOK_DIR="$(git -C "$REPO_ROOT" rev-parse --git-path hooks)"
mkdir -p "$HOOK_DIR"

# 0 = safe to (over)write our hook; 1 = a foreign hook is present, skip it.
can_write() {
  target="$HOOK_DIR/$1"
  if [ -e "$target" ] && ! grep -q "$MARKER" "$target" 2>/dev/null; then
    echo "⚠ $1 exists and is not dev-process-managed — leaving it untouched." >&2
    echo "  Merge the dev-process $1 manually if you want its checks." >&2
    return 1
  fi
  return 0
}

if can_write pre-commit; then
cat > "$HOOK_DIR/pre-commit" << 'EOF'
#!/usr/bin/env bash
# dev-process-managed-hook
# Blocks direct commits to main/master. Feature branch + ff-only merge to main.
# Automation escape: ALLOW_MAIN_COMMIT=1.
branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null)"
if { [ "$branch" = "main" ] || [ "$branch" = "master" ]; } && [ "${ALLOW_MAIN_COMMIT:-0}" != "1" ]; then
  echo "✗ Direct commit to '$branch' blocked. Use a feature branch; ff-only merge to main." >&2
  echo "  Automation: ALLOW_MAIN_COMMIT=1 git commit ..." >&2
  exit 1
fi
exit 0
EOF
chmod +x "$HOOK_DIR/pre-commit"
echo "✓ installed pre-commit"
fi

if can_write pre-push; then
cat > "$HOOK_DIR/pre-push" << 'EOF'
#!/usr/bin/env bash
# dev-process-managed-hook
# Local mirror of the CI merge gates: runs the manifest-aware gate runner over
# all active modules. Bypass: git push --no-verify, or SKIP_PUSH_GATE=1.
[ "${SKIP_PUSH_GATE:-0}" = "1" ] && { echo "⚠ pre-push gate skipped (SKIP_PUSH_GATE=1)." >&2; exit 0; }
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0
cd "$REPO_ROOT" || exit 0
[ -f scripts/process/gate_runner.py ] || exit 0
python3 scripts/process/gate_runner.py
EOF
chmod +x "$HOOK_DIR/pre-push"
echo "✓ installed pre-push"
fi

if can_write post-commit; then
cat > "$HOOK_DIR/post-commit" << 'EOF'
#!/usr/bin/env bash
# dev-process-managed-hook
# Warn-only drift feedback after each commit (never blocks).
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0
cd "$REPO_ROOT" || exit 0
[ -f scripts/process/gate_runner.py ] || exit 0
python3 scripts/process/gate_runner.py --warn || true
EOF
chmod +x "$HOOK_DIR/post-commit"
echo "✓ installed post-commit"
fi

echo "Done. Bypass: ALLOW_MAIN_COMMIT=1 (pre-commit); SKIP_PUSH_GATE=1 or --no-verify (pre-push)."
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/claude/Projekte/dev-process && .venv/bin/python -m pytest tests/test_git_hooks.py -q`
Expected: all tests pass (11 total).

- [ ] **Step 5: Commit**

```bash
cd /home/claude/Projekte/dev-process
git add "template/scripts/process/{% raw %}{% if modules.git_hooks %}install-hooks.sh{% endif %}{% endraw %}" tests/test_git_hooks.py
git commit -F - <<'EOF'
feat: add brownfield-safe install-hooks.sh with three hooks

install-hooks.sh writes pre-commit (main-guard), pre-push (gate_runner
mirror, blocking), and post-commit (gate_runner --warn) into .git/hooks,
each marked "# dev-process-managed-hook". A pre-existing foreign hook is
left untouched; re-running is idempotent.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01MS9nrQC9f9WGhipvJ9NFpk
EOF
```

---

### Task 3: Module doc, `commits.md` reconciliation, BOOTSTRAP, README

**Files:**
- Create: `template/docs/process/{% raw %}{% if modules.git_hooks %}modules{% endif %}{% endraw %}/git-hooks.md`
- Modify: `template/docs/process/commits.md`
- Modify: `BOOTSTRAP.md`
- Modify: `README.md`
- Modify: `tests/test_git_hooks.py` (append doc tests)

**Interfaces:**
- Consumes: the installer + hooks from Task 2.
- Produces: `git-hooks.md` module doc; a reconciled `commits.md`; adopter-facing install docs.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_git_hooks.py`:
```python
def test_module_doc_present_and_neutral(render, tmp_path):
    out = _render(render, tmp_path)
    doc = out / "docs/process/modules/git-hooks.md"
    assert doc.is_file()
    text = doc.read_text()
    for k in KENNI:
        assert k not in text, f"{k} leaked in git-hooks.md"


def test_module_doc_absent_when_off(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    assert not (out / "docs/process/modules/git-hooks.md").exists()


def test_docdrift_green_with_module_doc(render, tmp_path):
    out = render(tmp_path, {"project_name": "d",
                            "modules": {"doc_drift_gate": True, "git_hooks": True}})
    r = subprocess.run(
        [sys.executable, str(out / "scripts/process/check_doc_drift.py"), str(out)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stdout


def test_commits_md_no_unconditional_hook_promise(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})  # module OFF
    commits = (out / "docs/process/commits.md").read_text()
    # must reference the optional module, not promise a hook unconditionally,
    # and must not hard-link the module-conditional doc file
    assert "git-hooks" in commits
    assert "modules/git-hooks.md" not in commits
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/claude/Projekte/dev-process && .venv/bin/python -m pytest tests/test_git_hooks.py -q -k "module_doc or docdrift or commits_md"`
Expected: FAIL (git-hooks.md missing; commits.md lacks "git-hooks").

- [ ] **Step 3: Create the module doc**

Create `template/docs/process/{% raw %}{% if modules.git_hooks %}modules{% endif %}{% endraw %}/git-hooks.md`:
```markdown
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
```

- [ ] **Step 4: Reconcile `commits.md`**

In `template/docs/process/commits.md`, replace the last sentence (line 20–21):
```
review gate has passed: fetch → rebase → gate → `merge --ff-only` → push. A git
`pre-commit` hook guards the main branch and is bypassable for automation.
```
with:
```
review gate has passed: fetch → rebase → gate → `merge --ff-only` → push. When
the optional `git-hooks` module is installed, a `pre-commit` hook enforces this
locally (bypassable for automation via `ALLOW_MAIN_COMMIT=1`).
```

- [ ] **Step 5: Document the install step in BOOTSTRAP.md**

In `BOOTSTRAP.md`, in the `## Later` section, append after the existing paragraph:
```markdown

If you enabled the `git-hooks` module, install the hooks once per clone (they
live in host-local `.git/hooks`, not version control):

    bash scripts/process/install-hooks.sh
```

- [ ] **Step 6: Update README.md**

In `README.md`, update the status block (lines 10–11) — change the SP3 module list to add git-hooks and bump the tag:
```
> **Status:** SP1 (Foundation) + SP2 (Architektur-Onboarding) + SP3
> (feature-registry, github-issues, contracts-drift) + SP4 (git-hooks)
> ausgeliefert, Tag `v0.6.0`.
```
In the module catalog paragraph (the `Zuschaltbare Module heute:` sentence), append before the closing period:
```
 und `git-hooks` (lokale pre-commit/pre-push/post-commit-Durchsetzung, an den gate_runner delegiert)
```
In the Roadmap table, add a row after the SP3 row:
```
| **SP4** Prozess-Vervollständigung II | git-hooks (lokale Enforcement-Säule) | ✅ ausgeliefert |
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd /home/claude/Projekte/dev-process && .venv/bin/python -m pytest tests/test_git_hooks.py -q`
Expected: all pass (15 total).

- [ ] **Step 8: Full suite + ruff**

Run: `cd /home/claude/Projekte/dev-process && .venv/bin/python -m pytest -q && .venv/bin/ruff check tests/`
Expected: full suite green; ruff clean.

- [ ] **Step 9: Commit**

```bash
cd /home/claude/Projekte/dev-process
git add "template/docs/process/{% raw %}{% if modules.git_hooks %}modules{% endif %}{% endraw %}/git-hooks.md" template/docs/process/commits.md BOOTSTRAP.md README.md tests/test_git_hooks.py
git commit -F - <<'EOF'
docs: add git-hooks module doc, reconcile commits.md, README v0.6.0

Module doc covers install/hooks/bypass/brownfield. Reconcile commits.md so
the core methodology attributes the pre-commit guard to the optional
git-hooks module (no unconditional promise). Document the one-time install
in BOOTSTRAP; add git-hooks to the README catalog and SP4 roadmap row.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01MS9nrQC9f9WGhipvJ9NFpk
EOF
```

---

## Self-Review

**Spec coverage:** §3 files → Tasks 1–3 all mapped. §4 hooks → Task 2. §5 `--warn` → Task 1. §6 installer brownfield/idempotent → Task 2 tests. §7 commits.md → Task 3 Step 4. §8 BOOTSTRAP/doc → Task 3 Steps 3,5. §9 honest ceiling → covered by main-guard-blocks + warn-never-blocks tests. §10 testing → Tasks 1–3 tests. §11 wiring → Task 1 Step 4. No gaps.

**Placeholder scan:** none — every step has concrete code/edits/commands.

**Type/name consistency:** `_render`, `_runner`, `_failing_contract`, `_git`, `_init_repo`, `_hook_env` defined once (Tasks 1–2) and reused; marker string `# dev-process-managed-hook` identical in installer, hooks, and tests; `--warn` output string `"not blocking"` matches between gate_runner and the T1/T2 assertions.

**Risk note:** hooks call `python3`; tests prepend the venv bin to PATH via `_hook_env` so `python3` has pyyaml. Real adopters need pyyaml on their `python3` (pre-existing gate_runner dependency, unchanged by this slice).

## Post-plan: merge gate

After Task 3: verify `origin/main` unchanged and ff-clean; build a review bundle of `main..HEAD`; dispatch an independent Opus merge-gate reviewer with load-bearing lenses (main-guard actually blocks + escape works; pre-push propagates gate exit; post-commit never blocks; brownfield foreign hook untouched; hooks delegate to gate_runner not a fixed list; `--warn` only softens on failure; commits.md makes no unconditional promise + no dead link; neutrality + doc-drift green; module-off leak-free). Fix any Critical/Important, re-review. Then bump `pyproject.toml` to `0.6.0` in the same slice (version tracks tags now — bump before the tag), `git checkout main && git merge --ff-only design/sp4-git-hooks`, annotated tag `v0.6.0`, push main + tag, delete branch. Update memory (`project_dev_process_meta_repo.md` SP4-① bullet → SHIPPED; MEMORY.md index).
