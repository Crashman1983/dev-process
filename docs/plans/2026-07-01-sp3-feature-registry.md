# SP3 Slice 1 — Feature-Registry Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an opt-in `feature-registry` module that stores each user-visible story as one JSON file under `docs/process/feature-registry/` and verifies its structure, id-uniqueness, and reference existence on every CI run — the requirements / acceptance / test-traceability SSOT.

**Architecture:** One new gate script (`check_feature_registry.py`) globs the registry (excluding inert `*.example.json` seeds), hard-checks each story's structure (JSON well-formed, required fields, `STORY-NNNN` id + uniqueness, status enum, non-empty acceptance), hard-checks reference existence (`tests[]` paths resolve, `status: done` needs ≥1 test, `adr` link resolves via the SP2 adr-glob), and best-effort-flags a missing test *mapping* (never a false-green on semantic coverage). Wired into the SP1 manifest-aware `gate_runner`. The interview is a neutral questionnaire under `docs/process/modules/`; an inert `STORY-0001.example.json` seed ships as a copy-template that the gate ignores.

**Tech Stack:** Python 3 (stdlib only — `json`, `re`, `pathlib`), copier Jinja templating, pytest. Mirrors SP1/SP2 patterns exactly (`scripts/process/check_architecture.py`, `gate_runner.py`, `tests/conftest.py` fixtures, the SP2 adr-glob).

## Global Constraints

- **Structure + reference existence are hard** (CI exit 1). **Semantic test coverage is best-effort** — a missing test *mapping* is a note (exit 0), never claimed as verified. No false-green. (Same honest-ceiling philosophy as SP1/SP2.)
- **Only real story files are validated.** `docs/process/feature-registry/*.json` **minus** `*.example.json`. The shipped seed is `*.example.json` → ignored → an empty registry reads as "no stories yet", exit 0. No false-fail before the first story.
- **`status` enum is exactly** `proposed | in-progress | done | deprecated`.
- **`id` format is exactly** `STORY-NNNN` (four digits), unique across the registry.
- **Required fields:** `id`, `title`, `story`, `acceptance[]` (each item a mapping with non-empty `text`), `status`. **Optional:** `tests[]`, `adr`, `issue`, `links[]`.
- **Unknown fields are ignored** (Slice 2/3 forward-compat: `issue`, `links` are stored but only structurally touched here).
- **EARS is not regex-enforced.** `story` prose is an open domain — the gate grades structure, humans grade wording. Only `acceptance[].text` non-emptiness is hard.
- **`adr` link resolves by zero-padded number** to `docs/process/adr/adr-NNNN-*.md` — reuse the SP2 adr-glob helper verbatim.
- **Module default off.** All new template files gated by `{% if modules.feature_registry %}`; the seed and module doc appear only when the module is on.
- **Example paths inside `docs/process/**/*.md` must be placeholder-form** (`<story-id>`, `NNNN`, angle brackets) so the doc-drift-gate ignores them — it only flags slash-containing, non-placeholder `.ext` references.
- Follow `docs/process/commits.md`: atomic conventional commits, feature branch, ff-only merge. Commit trailers as in existing history (`Co-Authored-By:` + `Claude-Session:`).

---

### Task 1: Module wiring + gate skeleton + seed + interview doc

**Files:**
- Modify: `copier.yml` (add `feature_registry: false` to `modules.default`)
- Modify: `tests/conftest.py` (add `feature_registry: False` to `_copy` full defaults)
- Modify: `template/scripts/process/gate_runner.py.jinja` (register the gate)
- Create: `template/scripts/process/{% if modules.feature_registry %}check_feature_registry.py{% endif %}.jinja`
- Create: `template/docs/process/{% if modules.feature_registry %}modules{% endif %}/feature-registry.md.jinja`
- Create: `template/docs/process/{% if modules.feature_registry %}feature-registry{% endif %}/STORY-0001.example.json.jinja`
- Test: `tests/test_feature_registry.py`

**Interfaces:**
- Produces: `check_feature_registry.py` with `_story_files(root: Path) -> list[Path]`, `_adr_exists(root: Path, adr: object) -> bool`, `_check_story(root: Path, path: Path, seen_ids: dict) -> tuple[list[str], list[str]]`, `check(root: Path) -> tuple[list[str], list[str]]` (returns `(hard_problems, soft_notes)`), `main() -> int`. In this task `_check_story` only parses JSON and type-checks the object; field/reference validation is added in Tasks 2–3. `seen_ids` is threaded through from here so Task 2 can populate it.
- Consumes: nothing (first task).

- [ ] **Step 1: Add the copier answer**

In `copier.yml`, change the `modules.default` block to:

```yaml
modules:
  type: yaml
  help: "Which opt-in process modules to install"
  default:
    doc_drift_gate: false
    arch_onboarding: false
    feature_registry: false
```

- [ ] **Step 2: Add the conftest default**

In `tests/conftest.py`, in `_copy`, update the `full` defaults `modules` dict to include the new key:

```python
    full = {
        "harnesses": {"copilot": False, "agents_md": False},
        "modules": {"doc_drift_gate": False, "arch_onboarding": False, "feature_registry": False},
    }
```

- [ ] **Step 3: Write the failing presence/absence + empty-registry tests**

Create `tests/test_feature_registry.py`:

```python
import json
import subprocess
import sys
from pathlib import Path


def _render(render, tmp_path, **mods):
    m = {"feature_registry": True}
    m.update(mods)
    return render(tmp_path, {"project_name": "d", "modules": m})


def _run(out: Path):
    return subprocess.run(
        [sys.executable, str(out / "scripts/process/check_feature_registry.py"), str(out)],
        capture_output=True, text=True,
    )


REG = "docs/process/feature-registry"


def _write_story(out: Path, name: str, data: dict):
    d = out / REG
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(json.dumps(data), encoding="utf-8")


VALID = {
    "id": "STORY-0007",
    "title": "Consume billing API",
    "story": "As an order service, when a checkout completes, the system shall post the invoice.",
    "acceptance": [{"id": "AC1", "text": "A completed checkout produces exactly one billing POST."}],
    "tests": ["tests/billing/test_post.py"],
    "status": "done",
}


def test_module_files_present_when_on(render, tmp_path):
    out = _render(render, tmp_path)
    assert (out / "scripts/process/check_feature_registry.py").is_file()
    assert (out / "docs/process/modules/feature-registry.md").is_file()
    assert (out / REG / "STORY-0001.example.json").is_file()


def test_module_files_absent_when_off(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    assert not (out / "scripts/process/check_feature_registry.py").exists()
    assert not (out / "docs/process/modules/feature-registry.md").exists()
    assert not (out / REG).exists()


def test_shipped_seed_is_inert(render, tmp_path):
    # only the *.example.json seed ships → registry reads as empty
    out = _render(render, tmp_path)
    r = _run(out)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "no stories yet" in r.stdout


def test_invalid_json_is_hard(render, tmp_path):
    out = _render(render, tmp_path)
    (out / REG).mkdir(parents=True, exist_ok=True)
    (out / REG / "STORY-0002.json").write_text("{ not json", encoding="utf-8")
    r = _run(out)
    assert r.returncode == 1
    assert "invalid JSON" in r.stdout
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `cd /home/claude/Projekte/dev-process && .venv/bin/python -m pytest tests/test_feature_registry.py -q`
Expected: FAIL — the template files do not exist yet (render produces no `check_feature_registry.py`).

- [ ] **Step 5: Create the gate skeleton**

Create `template/scripts/process/{% if modules.feature_registry %}check_feature_registry.py{% endif %}.jinja`:

```python
#!/usr/bin/env python3
"""feature-registry gate: validate the story files under
docs/process/feature-registry/ — the requirements / acceptance / test
traceability SSOT.

Structure and reference existence are hard-guaranteed (CI exit 1). Whether a
test *semantically* proves its acceptance criterion is not mechanically
decidable — a missing test mapping is flagged best-effort, never faked as
verified. Language-agnostic; stdlib only (plus the shared adr glob)."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REGISTRY_DIR = "docs/process/feature-registry"
ADR_DIR = "docs/process/adr"
STATUSES = {"proposed", "in-progress", "done", "deprecated"}
ID_RE = re.compile(r"^STORY-\d{4}$")


def _story_files(root: Path) -> list[Path]:
    reg = root / REGISTRY_DIR
    if not reg.is_dir():
        return []
    return sorted(p for p in reg.glob("*.json") if not p.name.endswith(".example.json"))


def _adr_exists(root: Path, adr: object) -> bool:
    m = re.search(r"\d+", str(adr))
    if not m:
        return False
    return bool(list((root / ADR_DIR).glob(f"adr-{int(m.group()):04d}-*.md")))


def _check_story(root: Path, path: Path, seen_ids: dict) -> tuple[list[str], list[str]]:
    rel = path.relative_to(root)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"{rel}: invalid JSON: {exc}"], []
    if not isinstance(data, dict):
        return [f"{rel}: story must be a JSON object, got {type(data).__name__}"], []
    return [], []


def check(root: Path) -> tuple[list[str], list[str]]:
    files = _story_files(root)
    if not files:
        return [], ["no stories yet (feature-registry empty)"]
    hard: list[str] = []
    soft: list[str] = []
    seen_ids: dict = {}
    for path in files:
        h, s = _check_story(root, path, seen_ids)
        hard += h
        soft += s
    return hard, soft


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    hard, soft = check(root)
    for note in soft:
        print(f"registry-gate: note: {note}")
    if hard:
        print("registry-gate: FAILED:")
        for h in hard:
            print(f"  - {h}")
        return 1
    print("registry-gate: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 6: Create the inert seed story**

Create `template/docs/process/{% if modules.feature_registry %}feature-registry{% endif %}/STORY-0001.example.json.jinja`:

```json
{
  "id": "STORY-0001",
  "title": "Example story for {{ project_name }} — copy this file, drop the .example",
  "story": "As a <role>, when <trigger>, the system shall <response>.",
  "acceptance": [
    {"id": "AC1", "text": "A gradeable, testable statement of one accepted behaviour."}
  ],
  "tests": ["tests/<area>/test_<behaviour>.py"],
  "status": "proposed",
  "adr": "ADR-NNNN",
  "issue": "https://github.com/<owner>/<repo>/issues/<n>",
  "links": ["consumes <other-service> via <contract>, pinned <ref>"]
}
```

- [ ] **Step 7: Create the interview doc**

Create `template/docs/process/{% if modules.feature_registry %}modules{% endif %}/feature-registry.md.jinja`:

```markdown
# Module: feature-registry

Records the user-visible stories of **{{ project_name }}** and traces each to its
acceptance criteria and tests. Runs in CI via `process-gates` and locally via
`uv run scripts/process/check_feature_registry.py`.

## When a story is required

Mandatory rule *"tests prove acceptance"* (`docs/process/mandatory-rules.md`)
routes here: any user-visible behaviour, UI flow, contract, or test-coverage
change needs an affected story **before** implementation. New behaviour gets a
new story first. This is where a scenario sharpened at onboarding — including a
cross-repo coupling — is deposited as a concrete requirement.

## One story per file

Create `docs/process/feature-registry/STORY-NNNN.json` (one file per story so
stories diff and merge independently):

- **id** — `STORY-NNNN` (four digits), unique across the registry.
- **title** — a short label.
- **story** — one sentence in EARS form: *As a `<role>`, when `<trigger>`, the
  system shall `<response>`.* Wording is graded by humans, not the gate.
- **acceptance** — a non-empty list of `{id, text}`; each `text` is a gradeable,
  testable statement.
- **status** — `proposed | in-progress | done | deprecated`.
- **tests** — paths (optionally with a `::node` selector) to the tests that
  prove the acceptance. `status: done` needs at least one.
- **adr** (optional) — `ADR-NNNN` linking a decision under `docs/process/adr/`.
- **issue**, **links** (optional) — forward-compat slots for the GitHub-Issues
  and contracts modules; stored but not yet enforced.

Copy `STORY-0001.example.json` (shipped, inert) as a starting point.

## What the gate verifies

- **Hard (CI fails):** valid JSON object; `id`/`title`/`story`/`status`/
  `acceptance` present; `id` matches `STORY-NNNN` and is unique; `status` in the
  enum; every `acceptance[].text` non-empty; every `tests[]` path exists;
  `status: done` has ≥1 test; an `adr` link resolves to a file.
- **Best-effort:** an `in-progress`/`done` story with more acceptance criteria
  than mapped tests prints a note — the missing *mapping* is visible; semantic
  coverage stays a human judgement.
- **Ignored:** `*.example.json` seeds; unknown fields (cross-module forward-compat).
```

- [ ] **Step 8: Register the gate in the runner**

In `template/scripts/process/gate_runner.py.jinja`, extend the `GATES` dict:

```python
GATES = {
    "doc-drift-gate": ("doc_drift_gate", [sys.executable, "scripts/process/check_doc_drift.py", "."]),
    "arch-onboarding": ("arch_onboarding", [sys.executable, "scripts/process/check_architecture.py", "."]),
    "feature-registry": ("feature_registry", [sys.executable, "scripts/process/check_feature_registry.py", "."]),
}
```

- [ ] **Step 9: Add the gate_runner list test**

Append to `tests/test_feature_registry.py`:

```python
def test_runner_lists_gate_when_module_on(render, tmp_path):
    out = _render(render, tmp_path)
    r = subprocess.run(
        [sys.executable, str(out / "scripts/process/gate_runner.py"), "--list"],
        cwd=out, capture_output=True, text=True,
    )
    assert "feature-registry" in r.stdout


def test_runner_omits_gate_when_module_off(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    r = subprocess.run(
        [sys.executable, str(out / "scripts/process/gate_runner.py"), "--list"],
        cwd=out, capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    assert "feature-registry" not in r.stdout
```

- [ ] **Step 10: Run the tests to verify they pass**

Run: `cd /home/claude/Projekte/dev-process && .venv/bin/python -m pytest tests/test_feature_registry.py -q`
Expected: PASS (6 tests).

- [ ] **Step 11: Commit**

```bash
cd /home/claude/Projekte/dev-process
git add copier.yml tests/conftest.py tests/test_feature_registry.py \
  "template/scripts/process/gate_runner.py.jinja" \
  "template/scripts/process/{% if modules.feature_registry %}check_feature_registry.py{% endif %}.jinja" \
  "template/docs/process/{% if modules.feature_registry %}modules{% endif %}/feature-registry.md.jinja" \
  "template/docs/process/{% if modules.feature_registry %}feature-registry{% endif %}/STORY-0001.example.json.jinja"
git commit -m "$(cat <<'EOF'
feat: add feature-registry module skeleton and wiring

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01MS9nrQC9f9WGhipvJ9NFpk
EOF
)"
```

---

### Task 2: Hard structural checks (fields, id, status, acceptance)

**Files:**
- Modify: `template/scripts/process/{% if modules.feature_registry %}check_feature_registry.py{% endif %}.jinja` (extend `_check_story`)
- Test: `tests/test_feature_registry.py` (add structural cases)

**Interfaces:**
- Consumes: `_check_story(root, path, seen_ids)` from Task 1 (parses JSON, type-checks).
- Produces: the same `_check_story` now also validates required fields, `id` format + uniqueness (populating `seen_ids`), `status` enum, and non-empty `acceptance[].text`. `check()` / `main()` signatures unchanged.

- [ ] **Step 1: Write the failing structural tests**

Append to `tests/test_feature_registry.py`:

```python
def test_valid_story_ok(render, tmp_path):
    out = _render(render, tmp_path)
    _write_story(out, "STORY-0007.json", VALID)
    (out / "tests/billing").mkdir(parents=True, exist_ok=True)
    (out / "tests/billing/test_post.py").write_text("def test_x():\n    pass\n")
    r = _run(out)
    assert r.returncode == 0, r.stdout
    assert "registry-gate: OK" in r.stdout


def test_missing_required_field_is_hard(render, tmp_path):
    out = _render(render, tmp_path)
    broken = {k: v for k, v in VALID.items() if k != "title"}
    _write_story(out, "STORY-0008.json", broken)
    r = _run(out)
    assert r.returncode == 1
    assert "missing 'title'" in r.stdout


def test_bad_id_format_is_hard(render, tmp_path):
    out = _render(render, tmp_path)
    _write_story(out, "story7.json", {**VALID, "id": "STORY-7"})
    r = _run(out)
    assert r.returncode == 1
    assert "STORY-NNNN" in r.stdout


def test_duplicate_id_is_hard(render, tmp_path):
    out = _render(render, tmp_path)
    _write_story(out, "a.json", {**VALID, "id": "STORY-0009"})
    _write_story(out, "b.json", {**VALID, "id": "STORY-0009"})
    r = _run(out)
    assert r.returncode == 1
    assert "duplicate id" in r.stdout


def test_bad_status_is_hard(render, tmp_path):
    out = _render(render, tmp_path)
    _write_story(out, "STORY-0010.json", {**VALID, "status": "shipped"})
    r = _run(out)
    assert r.returncode == 1
    assert "status" in r.stdout


def test_empty_acceptance_text_is_hard(render, tmp_path):
    out = _render(render, tmp_path)
    bad = {**VALID, "acceptance": [{"id": "AC1", "text": "   "}]}
    _write_story(out, "STORY-0011.json", bad)
    r = _run(out)
    assert r.returncode == 1
    assert "acceptance[0]" in r.stdout
```

Note: `test_valid_story_ok` currently fails only on the missing test file / it may pass trivially — it becomes meaningful once the reference checks (Task 3) land; here it guards that structural validation does not false-fail a good story.

- [ ] **Step 2: Run the tests to verify the new ones fail**

Run: `cd /home/claude/Projekte/dev-process && .venv/bin/python -m pytest tests/test_feature_registry.py -q`
Expected: the structural cases FAIL (gate does not yet reject them; `_check_story` returns `[],[]` for any well-formed JSON object).

- [ ] **Step 3: Extend `_check_story` with structural validation**

Replace the `_check_story` function body in `check_feature_registry.py.jinja` with:

```python
def _check_story(root: Path, path: Path, seen_ids: dict) -> tuple[list[str], list[str]]:
    hard: list[str] = []
    soft: list[str] = []
    rel = path.relative_to(root)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"{rel}: invalid JSON: {exc}"], []
    if not isinstance(data, dict):
        return [f"{rel}: story must be a JSON object, got {type(data).__name__}"], []

    sid = data.get("id")
    if not isinstance(sid, str) or not sid:
        hard.append(f"{rel}: missing or non-string 'id'")
    elif not ID_RE.match(sid):
        hard.append(f"{rel}: 'id' must match STORY-NNNN, got {sid!r}")
    elif sid in seen_ids:
        hard.append(f"{rel}: duplicate id {sid!r} (also in {seen_ids[sid]})")
    else:
        seen_ids[sid] = str(rel)

    if not data.get("title"):
        hard.append(f"{rel}: missing 'title'")
    if not data.get("story"):
        hard.append(f"{rel}: missing 'story'")

    if data.get("status") not in STATUSES:
        hard.append(f"{rel}: 'status' must be one of {sorted(STATUSES)}, got {data.get('status')!r}")

    acceptance = data.get("acceptance")
    if not isinstance(acceptance, list) or not acceptance:
        hard.append(f"{rel}: 'acceptance' must be a non-empty list")
    else:
        for i, ac in enumerate(acceptance):
            if not isinstance(ac, dict) or not str(ac.get("text", "")).strip():
                hard.append(f"{rel}: acceptance[{i}] has empty 'text'")

    return hard, soft
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd /home/claude/Projekte/dev-process && .venv/bin/python -m pytest tests/test_feature_registry.py -q`
Expected: PASS (all structural cases green; `test_valid_story_ok` may still not be fully exercised until Task 3 but must not fail).

- [ ] **Step 5: Commit**

```bash
cd /home/claude/Projekte/dev-process
git add tests/test_feature_registry.py \
  "template/scripts/process/{% if modules.feature_registry %}check_feature_registry.py{% endif %}.jinja"
git commit -m "$(cat <<'EOF'
feat: hard-check story structure, id uniqueness, status, acceptance

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01MS9nrQC9f9WGhipvJ9NFpk
EOF
)"
```

---

### Task 3: Hard reference checks (tests paths, done-needs-test, adr)

**Files:**
- Modify: `template/scripts/process/{% if modules.feature_registry %}check_feature_registry.py{% endif %}.jinja` (extend `_check_story`)
- Test: `tests/test_feature_registry.py` (add reference cases)

**Interfaces:**
- Consumes: `_check_story` from Task 2 (structural checks), `_adr_exists` from Task 1.
- Produces: `_check_story` now also verifies `tests[]` path existence, `status: done` needs ≥1 test, and an `adr` link resolves. Counts mapped tests into a local `n_tests` for Task 4's best-effort note.

- [ ] **Step 1: Write the failing reference tests**

Append to `tests/test_feature_registry.py`:

```python
def test_missing_test_path_is_hard(render, tmp_path):
    out = _render(render, tmp_path)
    _write_story(out, "STORY-0012.json", {**VALID, "tests": ["tests/nope/test_absent.py"]})
    r = _run(out)
    assert r.returncode == 1
    assert "test path does not exist" in r.stdout


def test_done_without_tests_is_hard(render, tmp_path):
    out = _render(render, tmp_path)
    story = {**VALID, "status": "done"}
    story.pop("tests")
    _write_story(out, "STORY-0013.json", story)
    r = _run(out)
    assert r.returncode == 1
    assert "requires at least one test" in r.stdout


def test_test_path_with_node_selector_resolves(render, tmp_path):
    out = _render(render, tmp_path)
    (out / "tests/billing").mkdir(parents=True, exist_ok=True)
    (out / "tests/billing/test_post.py").write_text("def test_x():\n    pass\n")
    story = {**VALID, "tests": ["tests/billing/test_post.py::test_x"]}
    _write_story(out, "STORY-0014.json", story)
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_missing_adr_is_hard(render, tmp_path):
    out = _render(render, tmp_path)
    (out / "tests/billing").mkdir(parents=True, exist_ok=True)
    (out / "tests/billing/test_post.py").write_text("def test_x():\n    pass\n")
    _write_story(out, "STORY-0015.json", {**VALID, "adr": "ADR-0099"})
    r = _run(out)
    assert r.returncode == 1
    assert "adr link" in r.stdout


def test_present_adr_passes(render, tmp_path):
    out = _render(render, tmp_path)
    (out / "tests/billing").mkdir(parents=True, exist_ok=True)
    (out / "tests/billing/test_post.py").write_text("def test_x():\n    pass\n")
    (out / "docs/process/adr").mkdir(parents=True, exist_ok=True)
    (out / "docs/process/adr/adr-0005-billing.md").write_text("# ADR 5\n")
    _write_story(out, "STORY-0016.json", {**VALID, "adr": "ADR-0005"})
    r = _run(out)
    assert r.returncode == 0, r.stdout
```

- [ ] **Step 2: Run the tests to verify the new ones fail**

Run: `cd /home/claude/Projekte/dev-process && .venv/bin/python -m pytest tests/test_feature_registry.py -q`
Expected: the reference cases FAIL (gate does not yet check `tests[]`/`adr`).

- [ ] **Step 3: Extend `_check_story` with reference validation**

In `check_feature_registry.py.jinja`, insert the following block into `_check_story` immediately **before** the final `return hard, soft` (after the acceptance block):

```python
    tests = data.get("tests") or []
    if not isinstance(tests, list):
        hard.append(f"{rel}: 'tests' must be a list")
        tests = []
    n_tests = 0
    for t in tests:
        file_part = str(t).split("::", 1)[0]  # strip a pytest ::node selector
        if not (root / file_part).is_file():
            hard.append(f"{rel}: test path does not exist: {t}")
        else:
            n_tests += 1

    if data.get("status") == "done" and not tests:
        hard.append(f"{rel}: status 'done' requires at least one test")

    adr = data.get("adr")
    if adr and not _adr_exists(root, adr):
        hard.append(f"{rel}: adr link {adr!r} has no file under {ADR_DIR}/")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd /home/claude/Projekte/dev-process && .venv/bin/python -m pytest tests/test_feature_registry.py -q`
Expected: PASS (all reference cases green).

- [ ] **Step 5: Commit**

```bash
cd /home/claude/Projekte/dev-process
git add tests/test_feature_registry.py \
  "template/scripts/process/{% if modules.feature_registry %}check_feature_registry.py{% endif %}.jinja"
git commit -m "$(cat <<'EOF'
feat: hard-check test-path existence, done-needs-test, adr link

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01MS9nrQC9f9WGhipvJ9NFpk
EOF
)"
```

---

### Task 4: Best-effort note + forward-compat

**Files:**
- Modify: `template/scripts/process/{% if modules.feature_registry %}check_feature_registry.py{% endif %}.jinja` (add the soft note; count acceptance)
- Test: `tests/test_feature_registry.py` (soft-note + forward-compat cases)

**Interfaces:**
- Consumes: `_check_story` from Task 3 (has `n_tests`).
- Produces: `_check_story` now appends a best-effort `soft` note when `status in {in-progress, done}` and `n_acc > n_tests`. Unknown fields already ignored by construction (never read); this task adds the tests that lock that in.

- [ ] **Step 1: Write the failing soft-note + forward-compat tests**

Append to `tests/test_feature_registry.py`:

```python
def test_acceptance_without_test_is_soft(render, tmp_path):
    out = _render(render, tmp_path)
    (out / "tests/billing").mkdir(parents=True, exist_ok=True)
    (out / "tests/billing/test_post.py").write_text("def test_x():\n    pass\n")
    story = {
        **VALID,
        "status": "in-progress",
        "acceptance": [
            {"id": "AC1", "text": "one"},
            {"id": "AC2", "text": "two"},
        ],
        "tests": ["tests/billing/test_post.py"],
    }
    _write_story(out, "STORY-0017.json", story)
    r = _run(out)
    assert r.returncode == 0, r.stdout          # soft: does not fail the build
    assert "coverage unverified" in r.stdout


def test_unknown_field_ignored(render, tmp_path):
    out = _render(render, tmp_path)
    (out / "tests/billing").mkdir(parents=True, exist_ok=True)
    (out / "tests/billing/test_post.py").write_text("def test_x():\n    pass\n")
    story = {**VALID, "surface": "web", "owner": "team-a", "links": ["x"]}
    _write_story(out, "STORY-0018.json", story)
    r = _run(out)
    assert r.returncode == 0, r.stdout
    assert "registry-gate: OK" in r.stdout


def test_example_file_not_validated(render, tmp_path):
    out = _render(render, tmp_path)
    # a broken *.example.json must be ignored even though it is malformed
    (out / REG).mkdir(parents=True, exist_ok=True)
    (out / REG / "STORY-9999.example.json").write_text("{ not json", encoding="utf-8")
    r = _run(out)
    assert r.returncode == 0, r.stdout
    assert "no stories yet" in r.stdout
```

- [ ] **Step 2: Run the tests to verify the soft-note case fails**

Run: `cd /home/claude/Projekte/dev-process && .venv/bin/python -m pytest tests/test_feature_registry.py -q`
Expected: `test_acceptance_without_test_is_soft` FAILS (no note yet); the forward-compat cases likely already pass (unknown fields never read, example files already excluded) — that is fine, they lock in existing behaviour.

- [ ] **Step 3: Add the best-effort note**

In `_check_story`, the acceptance block computes the count; capture it and append the note before the final `return`. Change the acceptance block to record `n_acc`:

```python
    acceptance = data.get("acceptance")
    n_acc = 0
    if not isinstance(acceptance, list) or not acceptance:
        hard.append(f"{rel}: 'acceptance' must be a non-empty list")
    else:
        n_acc = len(acceptance)
        for i, ac in enumerate(acceptance):
            if not isinstance(ac, dict) or not str(ac.get("text", "")).strip():
                hard.append(f"{rel}: acceptance[{i}] has empty 'text'")
```

Then, immediately before the final `return hard, soft`, add:

```python
    if data.get("status") in ("in-progress", "done") and n_acc > n_tests:
        soft.append(f"{rel}: {n_acc} acceptance criteria but {n_tests} mapped test(s) — coverage unverified")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd /home/claude/Projekte/dev-process && .venv/bin/python -m pytest tests/test_feature_registry.py -q`
Expected: PASS (all cases green).

- [ ] **Step 5: Commit**

```bash
cd /home/claude/Projekte/dev-process
git add tests/test_feature_registry.py \
  "template/scripts/process/{% if modules.feature_registry %}check_feature_registry.py{% endif %}.jinja"
git commit -m "$(cat <<'EOF'
feat: best-effort note for unmapped acceptance; lock forward-compat

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01MS9nrQC9f9WGhipvJ9NFpk
EOF
)"
```

---

### Task 5: Mandatory-rules pointer + real render verification + full suite

**Files:**
- Modify: `template/docs/process/mandatory-rules.md` (thin pointer on Rule 5)
- Verify: real `uvx copier` render, full pytest, ruff

**Interfaces:**
- Consumes: the finished module from Tasks 1–4.
- Produces: nothing new in code — this task wires the rule pointer and proves the whole thing renders and passes end-to-end.

- [ ] **Step 1: Add the thin pointer to Rule 5**

In `template/docs/process/mandatory-rules.md`, change rule 5 to append the parenthetical pointer (mirror the Rule 3 style, no mechanics duplicated):

```markdown
5. **Tests prove acceptance.** Every feature or behavior change maps a test to the acceptance it claims. Exception: pure copy/formatting/doc-typo with no behavior change. (Acceptance lives in `docs/process/feature-registry/` when the `feature-registry` module is installed.)
```

- [ ] **Step 2: Verify the doc-drift-gate stays green with both modules on**

The new pointer references `docs/process/feature-registry/` — a directory path (trailing slash, no `.ext`), which the doc-drift-gate ignores. Confirm by rendering with both modules on and running the drift gate:

Run:
```bash
cd /home/claude/Projekte/dev-process && .venv/bin/python -m pytest tests/ -q
```
Expected: PASS (whole suite — the new module plus all SP1/SP2 tests).

- [ ] **Step 3: Real copier render (module on)**

Render the working tree with `--vcs-ref HEAD` (per the tag-shadowing lesson — a bare local render pins to the last tag and hides files added since):

Run:
```bash
cd /home/claude/Projekte/dev-process
rm -rf /tmp/fr-on && mkdir -p /tmp/fr-on
uvx copier copy --vcs-ref HEAD --trust \
  --data project_name=Demo \
  --data 'modules={"doc_drift_gate": true, "feature_registry": true}' \
  . /tmp/fr-on
ls /tmp/fr-on/scripts/process/check_feature_registry.py
ls /tmp/fr-on/docs/process/feature-registry/STORY-0001.example.json
ls /tmp/fr-on/docs/process/modules/feature-registry.md
cd /tmp/fr-on && python scripts/process/gate_runner.py
```
Expected: all three files exist; `gate_runner.py` prints the feature-registry gate running, reports "no stories yet", and exits 0 with "all N active gate(s) passed".

- [ ] **Step 4: Real copier render (module off)**

Run:
```bash
cd /home/claude/Projekte/dev-process
rm -rf /tmp/fr-off && mkdir -p /tmp/fr-off
uvx copier copy --vcs-ref HEAD --trust --data project_name=Demo . /tmp/fr-off
test ! -e /tmp/fr-off/scripts/process/check_feature_registry.py && echo "absent OK"
test ! -e /tmp/fr-off/docs/process/feature-registry && echo "dir absent OK"
```
Expected: both "absent OK" lines print.

- [ ] **Step 5: Lint**

Run:
```bash
cd /home/claude/Projekte/dev-process && .venv/bin/ruff check tests/ && echo "ruff clean"
```
Expected: "ruff clean". (The gate script itself is a `.jinja` template, not linted directly; its rendered form is exercised by the suite.)

- [ ] **Step 6: Commit**

```bash
cd /home/claude/Projekte/dev-process
git add template/docs/process/mandatory-rules.md
git commit -m "$(cat <<'EOF'
docs: point mandatory-rule 5 at the feature-registry module

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01MS9nrQC9f9WGhipvJ9NFpk
EOF
)"
```

---

## Self-Review

**Spec coverage** (against `docs/design/2026-07-01-sp3-feature-registry-design.md`):
- §3 format (required/optional fields, status enum, id scheme, unknown-ignored) → Tasks 1–4. ✓
- §4a interview doc → Task 1 Step 7. ✓
- §4b gate hard checks (JSON, id unique, status, acceptance text, tests resolve, done-needs-test, adr) → Tasks 1–3. ✓
- §4b best-effort note → Task 4. ✓
- §4b empty-registry soft-OK → Task 1. ✓
- §4c mandatory-rules pointer → Task 5 Step 1. ✓
- §5 wiring (copier flag, conftest, gate_runner, path-conditional files, inert seed) → Task 1. ✓
- §6 testing list → Tasks 1–4 tests. ✓
- §8 forward-compat (`issue`/`links` stored, unknown ignored) → Task 4. ✓
- §7 dogfooding (dev-process adopts its own registry) → **deliberately deferred.** dev-process is the template *source*; it does not render itself, so a root-level registry would need a bespoke run harness. The module's own test suite is the dogfood proof. Adopting a root registry is a follow-up once dev-process renders its process docs; not blocking this slice. (YAGNI.)

**Placeholder scan:** every code step shows complete content; no TBD/TODO. ✓

**Type consistency:** `_story_files`, `_adr_exists`, `_check_story(root, path, seen_ids)`, `check(root)`, `main()` names + signatures identical across Tasks 1–5; `seen_ids` threaded from Task 1; `n_tests`/`n_acc` introduced in Task 3/4 within `_check_story` scope. ✓

**Open-decision resolutions (from spec, user-approved defaults):** JSON, one-file-per-story, EARS-encouraged-not-graded, `STORY-NNNN` — all reflected in the code above.
