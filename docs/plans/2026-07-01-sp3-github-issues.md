# GitHub-Issues Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship an opt-in `github_issues` copier module: EARS issue templates, a seed helper, a documented backlog workflow, and a gate that hard-validates each feature-registry story's `issue`-ref format and best-effort-checks its existence on GitHub.

**Architecture:** A new manifest module (default off) rendered by copier path-conditionals. A new gate `check_issues.py` re-globs feature-registry stories, hard-fails (exit 1) on malformed `issue` refs, and best-effort-confirms existence via `gh` (entirely advisory, never exit 1). GitHub config (`github_repo`) is an optional, `when`-gated copier question read at runtime from `.copier-answers.yml`. The shipped v0.3.0 feature-registry gate stays frozen.

**Tech Stack:** Python 3 (stdlib + PyYAML), copier, pytest, ruff. Env: `.venv/bin/python`, `.venv/bin/ruff` at repo root `/home/claude/Projekte/dev-process`.

## Global Constraints

- **Honest ceiling:** issue-ref **format** is hard (exit 1); issue **existence** is best-effort and **entirely advisory — never exit 1**, a 404 stays a note.
- **Accepted `issue` forms** (validated only when present + non-empty; absent/empty allowed): bare `#N`, cross-repo `owner/repo#N`, URL `https://github.com/owner/repo/issues/N`.
- **Owner:** issue-format validation lives ONLY in `check_issues.py`. Do NOT modify `check_feature_registry.py.jinja` (frozen v0.3.0). `check_issues.py` re-globs stories itself (deliberate ~5-line duplication — the modules are independently installable and must not import each other).
- **`github_repo`** is read from the top-level key of `.copier-answers.yml`; blank/absent → skip existence with a note.
- **Subprocess `gh` call carries `timeout=GH_TIMEOUT_S` (= 10)**; a named constant, no magic number.
- **Neutrality:** no rendered artifact may contain any of: `Kenni`, `KenniNext`, `Seb`, `Signal`, `SvelteKit`, `user_id=1`, `surface:ios`. `test_core_docs` does NOT scan `.github/`, so this plan adds its own neutrality test.
- **copier path-conditional** per segment: `{% if modules.github_issues %}…{% endif %}`; a segment that renders empty skips the file (proven by sibling modules).
- **doc-drift** resolves references repo-root-relative (`root / ref`). In `github-issues.md`, every non-placeholder slash-path must resolve when only `github_issues` is on — reference ONLY this module's own artifacts as real paths; reference registry paths illustratively with `NNNN` (a doc-drift placeholder).
- Python: full type hints, ruff-clean. Tests mirror `tests/test_arch_onboarding.py`; the fake-binary never hits the network.
- **Every commit** ends with the two trailers:
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
  `Claude-Session: https://claude.ai/code/session_01MS9nrQC9f9WGhipvJ9NFpk`

---

### Task 1: `check_issues.py` — copier wiring + issue-ref format (hard)

**Files:**
- Modify: `copier.yml` (add `github_issues: false`; add `github_repo` question)
- Modify: `tests/conftest.py` (add `github_issues: False` to `_copy` full defaults)
- Create: `template/scripts/process/{% if modules.github_issues %}check_issues.py{% endif %}.jinja`
- Create: `tests/test_github_issues.py`

**Interfaces:**
- Produces: `check_issues.py` exposes `parse_issue_ref(ref) -> tuple[str|None, int] | None`, `_story_files(root)`, `check(root) -> (hard, soft)`, `main()`. Task 2 extends `check()` with existence and adds `_default_repo`, `_issue_exists`.
- Consumes: renders only when `modules.github_issues` is true; reads stories from `docs/process/feature-registry/*.json`.

- [ ] **Step 1: Write the failing format tests**

Create `tests/test_github_issues.py`:

```python
import json
import os
import subprocess
import sys
from pathlib import Path

KENNI = ["Kenni", "KenniNext", "Seb", "Signal", "SvelteKit", "user_id=1", "surface:ios"]


def _render(render, tmp_path, repo="", **mods):
    m = {"github_issues": True, "feature_registry": True}
    m.update(mods)
    data = {"project_name": "d", "modules": m}
    if repo:
        data["github_repo"] = repo
    return render(tmp_path, data)


def _run(out: Path, path=None, prepend=None):
    env = dict(os.environ)
    if path is not None:
        env["PATH"] = path
    elif prepend:
        env["PATH"] = f"{prepend}{os.pathsep}" + env["PATH"]
    return subprocess.run(
        [sys.executable, str(out / "scripts/process/check_issues.py"), str(out)],
        capture_output=True, text=True, env=env,
    )


def _story(out: Path, issue=None, status="proposed", sid="STORY-0001"):
    d = {"id": sid, "title": "t", "story": "s", "status": status,
         "acceptance": [{"text": "a"}], "tests": []}
    if issue is not None:
        d["issue"] = issue
    reg = out / "docs/process/feature-registry"
    reg.mkdir(parents=True, exist_ok=True)
    (reg / f"{sid}.json").write_text(json.dumps(d))


def test_valid_bare(render, tmp_path):
    out = _render(render, tmp_path)
    _story(out, issue="#412")
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_valid_crossrepo(render, tmp_path):
    out = _render(render, tmp_path)
    _story(out, issue="octo/billing#77")
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_valid_url(render, tmp_path):
    out = _render(render, tmp_path)
    _story(out, issue="https://github.com/octo/api/issues/412")
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_malformed_number_only(render, tmp_path):
    out = _render(render, tmp_path)
    _story(out, issue="412")
    r = _run(out)
    assert r.returncode == 1
    assert "malformed" in r.stdout


def test_malformed_hash_only(render, tmp_path):
    out = _render(render, tmp_path)
    _story(out, issue="#")
    r = _run(out)
    assert r.returncode == 1


def test_malformed_crossrepo_no_number(render, tmp_path):
    out = _render(render, tmp_path)
    _story(out, issue="octo/billing#")
    r = _run(out)
    assert r.returncode == 1


def test_malformed_non_github_url(render, tmp_path):
    out = _render(render, tmp_path)
    _story(out, issue="https://example.com/octo/api/issues/1")
    r = _run(out)
    assert r.returncode == 1


def test_issue_non_string_is_hard(render, tmp_path):
    out = _render(render, tmp_path)
    _story(out, issue=412)
    r = _run(out)
    assert r.returncode == 1
    assert "string" in r.stdout


def test_no_issue_ok(render, tmp_path):
    out = _render(render, tmp_path)
    _story(out, status="proposed")  # no issue field
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_tracked_without_issue_notes(render, tmp_path):
    out = _render(render, tmp_path)
    _story(out, status="in-progress")  # no issue field
    r = _run(out)
    assert r.returncode == 0, r.stdout
    assert "no issue link" in r.stdout


def test_bad_json_skipped(render, tmp_path):
    out = _render(render, tmp_path)
    reg = out / "docs/process/feature-registry"
    reg.mkdir(parents=True, exist_ok=True)
    (reg / "STORY-0002.json").write_text("{not json")
    r = _run(out)
    assert r.returncode == 0, r.stdout  # registry gate owns JSON validity


def test_no_stories_note(render, tmp_path):
    out = _render(render, tmp_path, feature_registry=False)  # no registry dir
    r = _run(out)
    assert r.returncode == 0, r.stdout
    assert "no stories" in r.stdout
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_github_issues.py -q`
Expected: FAIL — copier errors / `check_issues.py` does not render (module unknown).

- [ ] **Step 3: Add the copier question + module flag**

Edit `copier.yml` — add `github_issues: false` to the `modules.default` block so it reads:

```yaml
modules:
  type: yaml
  help: "Which opt-in process modules to install"
  default:
    doc_drift_gate: false
    arch_onboarding: false
    feature_registry: false
    github_issues: false
```

Then append the new question at the end of `copier.yml`:

```yaml
github_repo:
  type: str
  help: >-
    GitHub repo as OWNER/REPO for issue tracking (optional — leave blank to skip
    the best-effort issue-existence check; issue-ref format is still enforced).
  default: ""
  when: "{{ modules.github_issues }}"
```

- [ ] **Step 4: Add the conftest default**

Edit `tests/conftest.py` `_copy`, extending the `modules` dict:

```python
        "modules": {"doc_drift_gate": False, "arch_onboarding": False, "feature_registry": False, "github_issues": False},
```

- [ ] **Step 5: Write the gate (format half)**

Create `template/scripts/process/{% if modules.github_issues %}check_issues.py{% endif %}.jinja`:

```python
#!/usr/bin/env python3
"""github-issues gate: validate the `issue` field on feature-registry stories.

Issue-ref FORMAT is hard-guaranteed (CI exit 1). Issue EXISTENCE on GitHub is
best-effort and entirely advisory (never exit 1). Stdlib only in this half;
existence (added by the github-issues module) reads the copier answers."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REGISTRY_DIR = "docs/process/feature-registry"
TRACKED = ("in-progress", "done")  # statuses that ought to carry an issue link

_BARE = re.compile(r"^#(\d+)$")
_CROSS = re.compile(r"^([\w.-]+/[\w.-]+)#(\d+)$")
_URL = re.compile(r"^https://github\.com/([\w.-]+/[\w.-]+)/issues/(\d+)$")


def _story_files(root: Path) -> list[Path]:
    reg = root / REGISTRY_DIR
    if not reg.is_dir():
        return []
    return sorted(p for p in reg.glob("*.json") if not p.name.endswith(".example.json"))


def parse_issue_ref(ref: str) -> tuple[str | None, int] | None:
    """(repo_or_None, number) for a well-formed ref, else None. repo is None
    only for the bare `#N` form, which resolves against the configured repo."""
    for pat, has_repo in ((_BARE, False), (_CROSS, True), (_URL, True)):
        m = pat.match(ref)
        if m:
            return (m.group(1), int(m.group(2))) if has_repo else (None, int(m.group(1)))
    return None


def check(root: Path) -> tuple[list[str], list[str]]:
    stories = _story_files(root)
    if not stories:
        return [], ["no stories to check (feature-registry empty or absent)"]
    hard: list[str] = []
    soft: list[str] = []
    for path in stories:
        rel = path.relative_to(root)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue  # the feature-registry gate owns JSON validity
        if not isinstance(data, dict):
            continue
        issue = data.get("issue")
        status = data.get("status")
        if not issue:
            if status in TRACKED:
                soft.append(f"{rel}: status {status!r} but no issue link — unverified")
            continue
        if not isinstance(issue, str):
            hard.append(f"{rel}: 'issue' must be a string, got {type(issue).__name__}")
            continue
        if parse_issue_ref(issue.strip()) is None:
            hard.append(
                f"{rel}: malformed issue ref {issue!r} "
                "(want '#N', 'owner/repo#N', or a github issue URL)"
            )
    return hard, soft


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    hard, soft = check(root)
    for note in soft:
        print(f"issues-gate: note: {note}")
    if hard:
        print("issues-gate: FAILED:")
        for h in hard:
            print(f"  - {h}")
        return 1
    print("issues-gate: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_github_issues.py -q && .venv/bin/ruff check tests/test_github_issues.py`
Expected: PASS (12 tests). ruff clean.

- [ ] **Step 7: Commit**

```bash
git add copier.yml tests/conftest.py "template/scripts/process/{% if modules.github_issues %}check_issues.py{% endif %}.jinja" tests/test_github_issues.py
git commit -F - <<'EOF'
feat: add github_issues module with issue-ref format gate

check_issues.py hard-validates the issue-ref format (#N, owner/repo#N, or a
github URL) on feature-registry stories. github_issues is an opt-in module
(default off); github_repo is a when-gated, blank-allowed copier question.
The v0.3.0 feature-registry gate is untouched — issue-format is owned here.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01MS9nrQC9f9WGhipvJ9NFpk
EOF
```

---

### Task 2: best-effort existence check via `gh`

**Files:**
- Modify: `template/scripts/process/{% if modules.github_issues %}check_issues.py{% endif %}.jinja`
- Modify: `tests/test_github_issues.py`

**Interfaces:**
- Produces: `check()` now performs advisory existence; adds `_default_repo(root) -> str|None`, `_issue_exists(gh, repo, number) -> bool`, constant `GH_TIMEOUT_S = 10`.
- Consumes: `parse_issue_ref` (Task 1), `github_repo` from `.copier-answers.yml`, `gh` on PATH.

- [ ] **Step 1: Write the failing existence tests**

Append to `tests/test_github_issues.py`:

```python
def _stub_gh(bindir: Path, code: int, stdout: str = ""):
    bindir.mkdir(parents=True, exist_ok=True)
    p = bindir / "gh"
    p.write_text(f'#!/bin/sh\nprintf "%s" "{stdout}"\nexit {code}\n')
    p.chmod(0o755)


def _stub_gh_capture(bindir: Path, argfile: Path, code: int = 0):
    bindir.mkdir(parents=True, exist_ok=True)
    p = bindir / "gh"
    p.write_text(f'#!/bin/sh\nprintf "%s" "$*" > "{argfile}"\nexit {code}\n')
    p.chmod(0o755)


def test_existence_gh_absent_is_soft(render, tmp_path):
    # must-not-hard-fail guard: gh not on PATH -> note, exit 0
    out = _render(render, tmp_path, repo="octo/api")
    _story(out, issue="#412")
    empty = tmp_path / "empty"
    empty.mkdir()
    r = _run(out, path=str(empty))
    assert r.returncode == 0, r.stdout
    assert "gh not on PATH" in r.stdout


def test_existence_ok_no_note(render, tmp_path):
    out = _render(render, tmp_path, repo="octo/api")
    _story(out, issue="#412")
    bindir = tmp_path / "bin"
    _stub_gh(bindir, 0)
    r = _run(out, prepend=str(bindir))
    assert r.returncode == 0, r.stdout
    assert "could not confirm" not in r.stdout


def test_existence_404_is_soft(render, tmp_path):
    # must-not-hard-fail guard: a non-zero gh (404 / not visible) -> note, exit 0
    out = _render(render, tmp_path, repo="octo/api")
    _story(out, issue="#412")
    bindir = tmp_path / "bin"
    _stub_gh(bindir, 1)
    r = _run(out, prepend=str(bindir))
    assert r.returncode == 0, r.stdout
    assert "could not confirm" in r.stdout


def test_existence_forwards_configured_repo(render, tmp_path):
    out = _render(render, tmp_path, repo="octo/api")
    _story(out, issue="#412")
    bindir = tmp_path / "bin"
    argfile = out / "gh-args.txt"
    _stub_gh_capture(bindir, argfile, code=0)
    r = _run(out, prepend=str(bindir))
    assert r.returncode == 0, r.stdout
    args = argfile.read_text()
    assert "--repo octo/api" in args
    assert "412" in args


def test_existence_bare_without_repo_notes(render, tmp_path):
    out = _render(render, tmp_path)  # no github_repo configured
    _story(out, issue="#412")
    bindir = tmp_path / "bin"
    _stub_gh(bindir, 0)
    r = _run(out, prepend=str(bindir))
    assert r.returncode == 0, r.stdout
    assert "no github_repo configured" in r.stdout


def test_existence_crossrepo_uses_own_repo(render, tmp_path):
    out = _render(render, tmp_path)  # no default repo, ref carries its own
    _story(out, issue="octo/billing#77")
    bindir = tmp_path / "bin"
    argfile = out / "gh-args.txt"
    _stub_gh_capture(bindir, argfile, code=0)
    r = _run(out, prepend=str(bindir))
    assert r.returncode == 0, r.stdout
    assert "--repo octo/billing" in argfile.read_text()
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_github_issues.py -q`
Expected: FAIL — existence not implemented (no `gh` invocation, notes absent).

- [ ] **Step 3: Extend the gate with existence**

Replace the whole `template/scripts/process/{% if modules.github_issues %}check_issues.py{% endif %}.jinja` with:

```python
#!/usr/bin/env python3
"""github-issues gate: validate the `issue` field on feature-registry stories.

Issue-ref FORMAT is hard-guaranteed (CI exit 1). Issue EXISTENCE on GitHub is
best-effort and entirely advisory (never exit 1): a definitive 404 stays a
note, because this cannot distinguish a deleted issue from one an
unauthenticated or cross-repo token cannot see. Stdlib + PyYAML (a gate dep,
used to read the copier answers)."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

REGISTRY_DIR = "docs/process/feature-registry"
ANSWERS_FILE = ".copier-answers.yml"
GH_TIMEOUT_S = 10  # cap a hung `gh` so it cannot wedge CI
TRACKED = ("in-progress", "done")  # statuses that ought to carry an issue link

_BARE = re.compile(r"^#(\d+)$")
_CROSS = re.compile(r"^([\w.-]+/[\w.-]+)#(\d+)$")
_URL = re.compile(r"^https://github\.com/([\w.-]+/[\w.-]+)/issues/(\d+)$")


def _story_files(root: Path) -> list[Path]:
    reg = root / REGISTRY_DIR
    if not reg.is_dir():
        return []
    return sorted(p for p in reg.glob("*.json") if not p.name.endswith(".example.json"))


def _default_repo(root: Path) -> str | None:
    f = root / ANSWERS_FILE
    if not f.is_file():
        return None
    data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
    repo = data.get("github_repo")
    return repo.strip() if isinstance(repo, str) and repo.strip() else None


def parse_issue_ref(ref: str) -> tuple[str | None, int] | None:
    """(repo_or_None, number) for a well-formed ref, else None. repo is None
    only for the bare `#N` form, which resolves against the configured repo."""
    for pat, has_repo in ((_BARE, False), (_CROSS, True), (_URL, True)):
        m = pat.match(ref)
        if m:
            return (m.group(1), int(m.group(2))) if has_repo else (None, int(m.group(1)))
    return None


def _issue_exists(gh: str, repo: str, number: int) -> bool:
    """Best-effort. False also means 'could not determine' — the caller treats
    any False as an advisory note, never a hard failure."""
    try:
        r = subprocess.run(
            [gh, "issue", "view", str(number), "--repo", repo, "--json", "number"],
            capture_output=True, text=True, timeout=GH_TIMEOUT_S,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    return r.returncode == 0


def check(root: Path) -> tuple[list[str], list[str]]:
    stories = _story_files(root)
    if not stories:
        return [], ["no stories to check (feature-registry empty or absent)"]
    default_repo = _default_repo(root)
    gh = shutil.which("gh")
    hard: list[str] = []
    soft: list[str] = []
    gh_absent_noted = False
    for path in stories:
        rel = path.relative_to(root)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue  # the feature-registry gate owns JSON validity
        if not isinstance(data, dict):
            continue
        issue = data.get("issue")
        status = data.get("status")
        if not issue:
            if status in TRACKED:
                soft.append(f"{rel}: status {status!r} but no issue link — unverified")
            continue
        if not isinstance(issue, str):
            hard.append(f"{rel}: 'issue' must be a string, got {type(issue).__name__}")
            continue
        parsed = parse_issue_ref(issue.strip())
        if parsed is None:
            hard.append(
                f"{rel}: malformed issue ref {issue!r} "
                "(want '#N', 'owner/repo#N', or a github issue URL)"
            )
            continue
        repo, number = parsed
        target = repo or default_repo
        if not gh:
            if not gh_absent_noted:
                soft.append("gh not on PATH — skipping issue-existence checks")
                gh_absent_noted = True
            continue
        if not target:
            soft.append(f"{rel}: {issue} — no github_repo configured, cannot check existence")
            continue
        if not _issue_exists(gh, target, number):
            soft.append(f"{rel}: could not confirm {target}#{number} exists")
    return hard, soft


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    hard, soft = check(root)
    for note in soft:
        print(f"issues-gate: note: {note}")
    if hard:
        print("issues-gate: FAILED:")
        for h in hard:
            print(f"  - {h}")
        return 1
    print("issues-gate: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run to verify all pass**

Run: `.venv/bin/python -m pytest tests/test_github_issues.py -q`
Expected: PASS (all Task 1 + Task 2 tests).

- [ ] **Step 5: Commit**

```bash
git add "template/scripts/process/{% if modules.github_issues %}check_issues.py{% endif %}.jinja" tests/test_github_issues.py
git commit -F - <<'EOF'
feat: add best-effort gh issue-existence check

Existence is entirely advisory: absent gh, blank github_repo, or any non-zero
gh (404 / not-visible / network) become notes, never exit 1. The subprocess
call carries a timeout so a hung gh cannot wedge CI. Bare #N resolves against
the configured repo; cross-repo and URL refs carry their own.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01MS9nrQC9f9WGhipvJ9NFpk
EOF
```

---

### Task 3: register the gate in `gate_runner`

**Files:**
- Modify: `template/scripts/process/gate_runner.py.jinja`
- Modify: `tests/test_github_issues.py`

**Interfaces:**
- Consumes: `gate_runner` `GATES` dict + manifest mechanism (unchanged shape).
- Produces: `--list` emits `github-issues` iff the module is active.

- [ ] **Step 1: Write the failing wiring tests**

Append to `tests/test_github_issues.py`:

```python
def _runner_list(out: Path):
    return subprocess.run(
        [sys.executable, str(out / "scripts/process/gate_runner.py"), "--list"],
        cwd=out, capture_output=True, text=True,
    )


def test_runner_lists_issues_when_on(render, tmp_path):
    out = _render(render, tmp_path)
    r = _runner_list(out)
    assert r.returncode == 0, r.stderr
    assert "github-issues" in r.stdout


def test_runner_skips_issues_when_off(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    r = _runner_list(out)
    assert r.returncode == 0, r.stderr
    assert "github-issues" not in r.stdout
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_github_issues.py -q -k runner`
Expected: FAIL — `github-issues` not in the manifest.

- [ ] **Step 3: Add the GATES entry**

Edit `template/scripts/process/gate_runner.py.jinja`, adding one line to the `GATES` dict after the `feature-registry` entry:

```python
    "github-issues": ("github_issues", [sys.executable, "scripts/process/check_issues.py", "."]),
```

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_github_issues.py -q -k runner`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add "template/scripts/process/gate_runner.py.jinja" tests/test_github_issues.py
git commit -F - <<'EOF'
feat: register github-issues gate in the manifest runner

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01MS9nrQC9f9WGhipvJ9NFpk
EOF
```

---

### Task 4: static artifacts — templates, seed helper, module doc

**Files:**
- Create: `template/.github/{% if modules.github_issues %}ISSUE_TEMPLATE{% endif %}/feature.md`
- Create: `template/.github/{% if modules.github_issues %}ISSUE_TEMPLATE{% endif %}/bug.md`
- Create: `template/scripts/process/{% if modules.github_issues %}new_issue.sh{% endif %}`
- Create: `template/docs/process/{% if modules.github_issues %}modules{% endif %}/github-issues.md`
- Modify: `tests/test_github_issues.py`

**Interfaces:**
- Consumes: nothing new; all rendered only when the module is on.
- Produces: neutral EARS templates, a POSIX seed helper (`new_issue.sh <name>` prints a frontmatter-stripped body path), and the module doc whose only real slash-paths are this module's own artifacts.

- [ ] **Step 1: Write the failing artifact tests**

Append to `tests/test_github_issues.py`:

```python
def test_artifacts_present_when_on(render, tmp_path):
    out = _render(render, tmp_path)
    assert (out / ".github/ISSUE_TEMPLATE/feature.md").is_file()
    assert (out / ".github/ISSUE_TEMPLATE/bug.md").is_file()
    assert (out / "scripts/process/new_issue.sh").is_file()
    assert (out / "docs/process/modules/github-issues.md").is_file()


def test_artifacts_absent_when_off(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    assert not (out / ".github/ISSUE_TEMPLATE/feature.md").exists()
    assert not (out / "scripts/process/new_issue.sh").exists()
    assert not (out / "docs/process/modules/github-issues.md").exists()


def test_artifacts_neutral(render, tmp_path):
    out = _render(render, tmp_path)
    for rel in [
        ".github/ISSUE_TEMPLATE/feature.md",
        ".github/ISSUE_TEMPLATE/bug.md",
        "docs/process/modules/github-issues.md",
        "scripts/process/new_issue.sh",
    ]:
        text = (out / rel).read_text()
        for k in KENNI:
            assert k not in text, f"{k} leaked in {rel}"


def test_feature_template_has_ears_and_story(render, tmp_path):
    out = _render(render, tmp_path)
    t = (out / ".github/ISSUE_TEMPLATE/feature.md").read_text()
    assert "User story" in t
    assert "shall" in t  # EARS phrasing
    assert "<role>" in t


def test_seed_script_strips_frontmatter(render, tmp_path):
    out = _render(render, tmp_path)
    r = subprocess.run(
        ["bash", str(out / "scripts/process/new_issue.sh"), "feature"],
        cwd=out, capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    body_path = Path(r.stdout.strip())
    assert body_path.is_file()
    body = body_path.read_text()
    assert "User story" in body
    assert "labels:" not in body  # YAML frontmatter removed
    assert not body.lstrip().startswith("---")


def test_docdrift_resolves_module_doc_refs(render, tmp_path):
    out = render(
        tmp_path,
        {"project_name": "d", "modules": {"doc_drift_gate": True, "github_issues": True}},
    )
    r = subprocess.run(
        [sys.executable, str(out / "scripts/process/check_doc_drift.py"), str(out)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stdout  # module-doc refs resolve; feature_registry off
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_github_issues.py -q -k "artifacts or template or seed or docdrift"`
Expected: FAIL — artifacts do not exist.

- [ ] **Step 3: Create `feature.md`**

Create `template/.github/{% if modules.github_issues %}ISSUE_TEMPLATE{% endif %}/feature.md`:

```markdown
---
name: Feature
about: A new capability, framed as a user story with EARS acceptance criteria
labels: type:feature
---

## User story

As a <role>, I want <capability> so that <benefit>.

## Context

<Why now — the problem, the trigger, links to related work.>

## Acceptance criteria (EARS)

Write each criterion in one of the EARS patterns so it is gradeable:

- When <trigger>, the system shall <response>.
- While <state>, the system shall <response>.
- Where <feature is present>, the system shall <response>.
- If <unwanted condition>, then the system shall <response>.
- The system shall <ubiquitous requirement>.

## Scope

<In scope / explicitly out of scope.>

## Dependencies

<Blocking issues, contracts, or interfaces this needs first.>
```

- [ ] **Step 4: Create `bug.md`**

Create `template/.github/{% if modules.github_issues %}ISSUE_TEMPLATE{% endif %}/bug.md`:

```markdown
---
name: Bug
about: A defect — observed vs. expected, with a gradeable fix criterion
labels: type:bug
---

## Summary

<One sentence: what is wrong.>

## Steps to reproduce

1. <step>
2. <step>

## Expected vs. actual

- Expected: <what should happen>
- Actual: <what happens>

## Acceptance criteria (EARS)

- When <the reproduction steps run>, the system shall <expected behaviour>.

## Scope / notes

<Root-cause hypothesis, affected area, out-of-scope follow-ups.>
```

- [ ] **Step 5: Create `new_issue.sh`**

Create `template/scripts/process/{% if modules.github_issues %}new_issue.sh{% endif %}`:

```bash
#!/usr/bin/env bash
# Seed an issue body from a .github/ISSUE_TEMPLATE, because `gh issue create`
# ignores ISSUE_TEMPLATE/. Prints the path to a temp file with the YAML
# frontmatter stripped; feed it to `gh issue create --body-file <path>`.
set -euo pipefail

kind="${1:?usage: new_issue.sh <template, e.g. feature|bug>}"
tpl=".github/ISSUE_TEMPLATE/${kind}.md"
[ -f "$tpl" ] || { echo "no such template: $tpl" >&2; exit 1; }

out="$(mktemp -t issue-body.XXXXXX.md)"
# Drop the leading YAML frontmatter block (--- ... ---), keep the rest.
awk 'NR==1 && $0=="---"{f=1; next} f && $0=="---"{f=0; next} !f' "$tpl" > "$out"
echo "$out"
```

- [ ] **Step 6: Create the module doc**

Create `template/docs/process/{% if modules.github_issues %}modules{% endif %}/github-issues.md`. (Only real slash-paths are this module's own artifacts; the registry path is written with `NNNN` so doc-drift treats it as illustrative.)

```markdown
# Module: github-issues

Opt-in. Runs the backlog on GitHub Issues: EARS-framed templates, a seed
helper, a documented claim workflow, and a gate over the `issue` link on
feature-registry stories.

## When required

Enable when GitHub Issues is the operative backlog. Tracked work (a story at
status `in-progress` or `done`) should carry an `issue` link; the gate emits a
note when it does not.

## Prerequisites (optional)

- A GitHub repository. Set it at setup via the `github_repo` answer
  (`OWNER/REPO`) — optional; leave blank to skip existence checks.
- The `gh` CLI, authenticated (`gh auth login`). Absent → existence checks are
  skipped with a note; format is still enforced.

## The `issue` field

A story's `issue` field (illustrative story path `docs/process/feature-registry/STORY-NNNN.json`)
accepts three forms:

- bare `#412` — resolves against the configured `github_repo`
- cross-repo `owner/repo#412`
- URL `https://github.com/owner/repo/issues/412`

**Hard (CI fails):** a malformed ref. **Best-effort (advisory note only):**
whether the issue exists — a 404 stays a note, because the gate cannot tell a
deleted issue from one the token cannot see, and cross-repo refs are allowed.

## Templates and the seed helper

Two templates: `.github/ISSUE_TEMPLATE/feature.md` and
`.github/ISSUE_TEMPLATE/bug.md`. Because `gh issue create` ignores
`ISSUE_TEMPLATE/`, seed a body with `scripts/process/new_issue.sh`:

    body="$(bash scripts/process/new_issue.sh feature)"
    gh issue create --title "..." --body-file "$body"

## Example label schema (adapt freely)

A starting point, not enforced by any gate:

- `surface:<area>` — which part of the system
- `priority:{low,med,high}`
- `type:{feature,bug,chore}`
- `status:in-progress` — claimed and being worked

## Claim workflow

1. Comment to claim: agent/branch/scope/next-update.
2. Set `status:in-progress`.
3. Post a heartbeat comment on long-running work.
4. On merge: remove `status:in-progress`, close the issue with the commit ref.
```

- [ ] **Step 7: Run to verify all pass**

Run: `.venv/bin/python -m pytest tests/test_github_issues.py -q && .venv/bin/ruff check tests/test_github_issues.py`
Expected: PASS (full file). ruff clean.

- [ ] **Step 8: Commit**

```bash
git add "template/.github/{% if modules.github_issues %}ISSUE_TEMPLATE{% endif %}/feature.md" \
        "template/.github/{% if modules.github_issues %}ISSUE_TEMPLATE{% endif %}/bug.md" \
        "template/scripts/process/{% if modules.github_issues %}new_issue.sh{% endif %}" \
        "template/docs/process/{% if modules.github_issues %}modules{% endif %}/github-issues.md" \
        tests/test_github_issues.py
git commit -F - <<'EOF'
feat: add neutral EARS issue templates, seed helper, module doc

feature.md/bug.md are EARS-framed and Kenni-free; new_issue.sh strips the YAML
frontmatter (gh issue create ignores ISSUE_TEMPLATE/); github-issues.md
documents the format/existence split, prerequisites, an example label schema,
and the claim workflow. The doc references only this module's own artifacts as
real paths so doc-drift stays green when feature_registry is off.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01MS9nrQC9f9WGhipvJ9NFpk
EOF
```

---

### Task 5: full-suite + real-render verification (pre-merge gate)

**Files:** none (verification only).

- [ ] **Step 1: Full suite + lint**

Run: `.venv/bin/python -m pytest -q && .venv/bin/ruff check .`
Expected: all tests pass (Slice-1 count + the new github-issues tests), ruff clean.

- [ ] **Step 2: Real copier render, all relevant modules on**

```bash
D=$(mktemp -d)
uvx copier copy . "$D" --vcs-ref HEAD --trust --defaults \
  --data project_name=demo \
  --data-file /dev/stdin <<'YAML'
modules: {doc_drift_gate: true, feature_registry: true, github_issues: true}
github_repo: "octo/demo"
YAML
ls "$D/.github/ISSUE_TEMPLATE" "$D/scripts/process/check_issues.py" "$D/docs/process/modules/github-issues.md"
```
Expected: artifacts present.
(If `--data-file /dev/stdin` is awkward in the runner, pass the same values with repeated `--data 'modules={...}'` `--data github_repo=octo/demo`.)

- [ ] **Step 3: Gates green on the render**

```bash
cd "$D" && /home/claude/Projekte/dev-process/.venv/bin/python scripts/process/gate_runner.py; cd -
```
Expected: doc-drift OK (module-doc template refs resolve), feature-registry OK (only the inert `.example` seed), github-issues OK/notes (no stories → "no stories" note); overall exit 0.

- [ ] **Step 4: Seed helper on the render**

```bash
cd "$D" && bash scripts/process/new_issue.sh feature && cd -
```
Expected: prints a temp path; the file has no `---` frontmatter.

- [ ] **Step 5: Module off renders nothing**

```bash
D2=$(mktemp -d)
uvx copier copy . "$D2" --vcs-ref HEAD --trust --defaults --data project_name=demo
test ! -e "$D2/scripts/process/check_issues.py" && test ! -e "$D2/.github/ISSUE_TEMPLATE" && echo "off: clean"
```
Expected: `off: clean`.

---

## Self-Review

**1. Spec coverage.** §3 setup question → Task 1 (copier `github_repo` + flag). §4 format-hard + owner → Task 1 (`check_issues.py`, registry gate untouched). §5 existence best-effort → Task 2. §6 artifacts → Tasks 1–4 (gate, gate_runner, templates, seed, doc). §7 wiring/degradation → Tasks 3/4 + no-stories note (Task 1). §8 testing → tests across all tasks, real render Task 5. §9 dogfooding → render tests (module not self-installed). No gap.

**2. Placeholder scan.** No TBD/TODO; every code step carries full file content; commands have expected output. The `<role>`/`<trigger>` tokens are literal EARS template content (asserted by `test_feature_template_has_ears_and_story`), not plan placeholders.

**3. Type/name consistency.** `parse_issue_ref`, `_story_files`, `_default_repo`, `_issue_exists`, `check`, `GH_TIMEOUT_S`, `TRACKED` consistent across Tasks 1–2. `_render`/`_run`/`_story`/`_stub_gh`/`_stub_gh_capture`/`_runner_list` consistent across the test file. Gate name `github-issues` and module key `github_issues` consistent across gate_runner, copier, and tests.
