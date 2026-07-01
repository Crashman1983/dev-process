# SP2 — Architecture Onboarding Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an opt-in `arch-onboarding` module that captures a repo's architecture in a fenced `arch` block inside `ARCHITECTURE.md` and verifies its machine-checkable claims against real code on every CI run.

**Architecture:** One new gate script (`check_architecture.py`) parses only an exact ` ```arch ` block, hard-checks existence/location of paths + interface symbols, best-effort-checks layering conformance (present arch-linter, else a manual checklist), and hard-checks that any linked ADR file exists. Wired into the SP1 manifest-aware `gate_runner`. The interview is a neutral questionnaire under `docs/process/modules/`; a seed `ARCHITECTURE.md` ships an inert ` ```arch-example ` block. The core ADR template gains an `Intent` axis.

**Tech Stack:** Python 3, `pyyaml`, copier Jinja templating, pytest. Mirrors SP1 patterns exactly (`scripts/process/check_doc_drift.py`, `gate_runner.py`, `tests/conftest.py` fixtures).

## Global Constraints

- **Existence/location is hard** (CI exit 1); **layering conformance is best-effort** (present arch-linter → hard; no linter → manual-review checklist, exit 0). Never pretend conformance was verified when it was not.
- **Only an exact ` ```arch ` fence is read.** An inert ` ```arch-example ` fence (the seed) is ignored → repo reads as "not onboarded", exit 0. No false-fail before onboarding.
- **No `external:` / cross-repo anything in SP2** (that is SP3). The checker **ignores unknown top-level manifest keys** (SP3 forward-compat).
- **Module default off.** All new template files gated by `{% if modules.arch_onboarding %}`; the seed `ARCHITECTURE.md` and module doc appear only when the module is on.
- **ADR filename convention:** `docs/process/adr/adr-NNNN-<slug>.md`; `rules[].adr: ADR-NNNN` resolves by the zero-padded number.
- **ADR record has two axes:** `Status` (Proposed|Accepted|Superseded) + `Intent` (keep|change-planned|tolerated). `Intent` lives in the **core** `docs/process/adr/template.md` (one convention, ungated).
- **Example paths inside `docs/process/**/*.md` must be placeholder-form** (`src/<layer>/x.py`, angle brackets) so the doc-drift-gate ignores them — it only flags slash-containing, non-placeholder, `.ext` references.
- Follow `docs/process/commits.md`: atomic conventional commits, feature branch, ff-only merge. Commit trailers as in existing history.

---

### Task 1: Module wiring + inert checker + seed + interview doc

**Files:**
- Modify: `copier.yml` (add `arch_onboarding: false` to `modules.default`)
- Modify: `tests/conftest.py` (add `arch_onboarding: False` to `_copy` full defaults)
- Create: `template/scripts/process/{% if modules.arch_onboarding %}check_architecture.py{% endif %}.jinja`
- Create: `template/docs/process/{% if modules.arch_onboarding %}modules{% endif %}/arch-onboarding.md.jinja`
- Create: `template/{% if modules.arch_onboarding %}ARCHITECTURE.md{% endif %}.jinja`
- Test: `tests/test_arch_onboarding.py`

**Interfaces:**
- Produces: `check_architecture.py` with `extract_block(md: str) -> str | None`, `check(root: Path) -> tuple[list[str], list[str]]` (returns `(hard_problems, soft_notes)`), `main() -> int`. In this task `check()` only handles the not-onboarded branches; existence/conformance/adr checks are added in Tasks 2–4.

- [ ] **Step 1: Add the copier answer**

In `copier.yml`, change the `modules.default` block to:

```yaml
modules:
  type: yaml
  help: "Which opt-in process modules to install"
  default:
    doc_drift_gate: false
    arch_onboarding: false
```

- [ ] **Step 2: Add the conftest default**

In `tests/conftest.py`, change the `full` dict inside `_copy` to:

```python
    full = {
        "harnesses": {"copilot": False, "agents_md": False},
        "modules": {"doc_drift_gate": False, "arch_onboarding": False},
    }
```

- [ ] **Step 3: Write the failing test**

Create `tests/test_arch_onboarding.py`:

```python
import os
import subprocess
import sys
from pathlib import Path


def _render(render, tmp_path, **mods):
    m = {"arch_onboarding": True}
    m.update(mods)
    return render(tmp_path, {"project_name": "d", "modules": m})


def _run(out: Path, extra_path: str | None = None):
    env = dict(os.environ)
    if extra_path:
        env["PATH"] = f"{extra_path}{os.pathsep}" + env["PATH"]
    return subprocess.run(
        [sys.executable, str(out / "scripts/process/check_architecture.py"), str(out)],
        capture_output=True, text=True, env=env,
    )


def _write_arch(out: Path, block: str, fence: str = "arch"):
    (out / "ARCHITECTURE.md").write_text(
        f"# Architecture\n\nnarrative\n\n```{fence}\n{block}\n```\n"
    )


def test_module_files_present_when_on(render, tmp_path):
    out = _render(render, tmp_path)
    assert (out / "scripts/process/check_architecture.py").is_file()
    assert (out / "docs/process/modules/arch-onboarding.md").is_file()
    assert (out / "ARCHITECTURE.md").is_file()


def test_module_files_absent_when_off(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    assert not (out / "scripts/process/check_architecture.py").exists()
    assert not (out / "docs/process/modules/arch-onboarding.md").exists()
    assert not (out / "ARCHITECTURE.md").exists()


def test_seed_is_inert(render, tmp_path):
    out = _render(render, tmp_path)  # ships ARCHITECTURE.md with ```arch-example
    r = _run(out)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "not onboarded" in r.stdout


def test_no_architecture_md(render, tmp_path):
    out = _render(render, tmp_path)
    (out / "ARCHITECTURE.md").unlink()
    r = _run(out)
    assert r.returncode == 0
    assert "not onboarded" in r.stdout


def test_no_arch_block(render, tmp_path):
    out = _render(render, tmp_path)
    (out / "ARCHITECTURE.md").write_text("# Architecture\n\njust prose, no block\n")
    r = _run(out)
    assert r.returncode == 0
    assert "not onboarded" in r.stdout
```

- [ ] **Step 4: Run the test to verify it fails**

Run: `uv run pytest tests/test_arch_onboarding.py -q`
Expected: FAIL — the template files do not exist yet.

- [ ] **Step 5: Create the inert checker**

Create `template/scripts/process/{% if modules.arch_onboarding %}check_architecture.py{% endif %}.jinja`:

```python
#!/usr/bin/env python3
"""arch-onboarding gate: verify the machine-checkable claims in the fenced
```arch block of ARCHITECTURE.md against the real code.

Existence/location is hard-guaranteed; layering conformance is best-effort
(a present arch-linter, else a manual-review checklist). Language-agnostic.
Only an exact ```arch fence is read — an inert ```arch-example seed is ignored."""
from __future__ import annotations

import sys
from pathlib import Path

ADR_DIR = "docs/process/adr"


def extract_block(md: str) -> str | None:
    inside, out = False, []
    for line in md.splitlines():
        s = line.strip()
        if not inside:
            if s == "```arch":
                inside = True
            continue
        if s == "```":
            return "\n".join(out)
        out.append(line)
    return None


def check(root: Path) -> tuple[list[str], list[str]]:
    arch = root / "ARCHITECTURE.md"
    if not arch.is_file():
        return [], ["architecture not onboarded yet (no ARCHITECTURE.md)"]
    block = extract_block(arch.read_text(encoding="utf-8"))
    if block is None:
        return [], ["architecture not onboarded yet (no ```arch block)"]
    return [], []  # existence/conformance/adr checks added in Tasks 2-4


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    hard, soft = check(root)
    for note in soft:
        print(f"arch-gate: note: {note}")
    if hard:
        print("arch-gate: FAILED:")
        for h in hard:
            print(f"  - {h}")
        return 1
    print("arch-gate: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 6: Create the seed ARCHITECTURE.md (inert)**

Create `template/{% if modules.arch_onboarding %}ARCHITECTURE.md{% endif %}.jinja`:

````markdown
# Architecture — {{ project_name }}

Run the onboarding interview (`docs/process/modules/arch-onboarding.md`), then
replace the inert `arch-example` block below with a real `arch` block. The
arch-gate reads only an exact ` ```arch ` fence, so this seed never fails CI.

<Describe the layers, the boundaries, and the key invariants here.>

```arch-example
code_roots: [src]
layers:
  domain: {path: src/<domain>}
  infra:  {path: src/<infra>}
rules:
  - {forbid: domain -> infra, adr: ADR-0002}
interfaces:
  - {name: ExamplePort, path: src/<domain>/ports.py}
```
````

- [ ] **Step 7: Create the interview questionnaire**

Create `template/docs/process/{% if modules.arch_onboarding %}modules{% endif %}/arch-onboarding.md.jinja`:

````markdown
# Module: arch-onboarding

Captures the architecture of **{{ project_name }}** and verifies it against the
real code. Runs in CI via `process-gates` and locally via
`uv run scripts/process/check_architecture.py`.

## Interview (run this with a human)

Fill an ` ```arch ` block in `ARCHITECTURE.md` by answering, one at a time:

1. **code_roots** — which directories hold this repo's own code?
2. **layers** — name each architectural layer and its path (e.g. `domain`,
   `app`, `infra`). Example path form: `src/<layer>`.
3. **invariants (rules)** — which dependencies are forbidden? Express as
   `forbid: A -> B` using layer names. Each rule the human confirms as a real
   decision earns an ADR (below) and links it via `adr:`.
4. **interfaces** — the key contract symbols in this repo and the file each
   lives in (e.g. `<PortName>` in `src/<domain>/ports.py`).

Then write the block into `ARCHITECTURE.md`:

```
code_roots: [src]
layers:
  domain: {path: src/<domain>}
  infra:  {path: src/<infra>}
rules:
  - {forbid: domain -> infra, adr: ADR-NNNN}
interfaces:
  - {name: <PortName>, path: src/<domain>/ports.py}
```

## What the gate verifies

- **Hard (CI fails):** every `code_roots` / `layers.*.path` exists; every
  `interfaces[].path` file exists and contains its `name`; a `rules[].adr`
  link resolves to a file; rule layer names are known; manifest is well-formed.
- **Best-effort:** layering conformance runs a present arch-linter
  (import-linter via `lint-imports`, dependency-cruiser via `depcruise`) and
  fails on violations; with no linter it prints a manual-review checklist and
  stays green. Conformance is **delegated to the linter's own contracts**
  (`.importlinter`, `.dependency-cruiser.*`) — keep those in sync with the
  `rules` here, or a green linter can silently pass a rule it never enforces.
- **Ignored:** unknown top-level keys (reserved for later cross-repo work).

## Decisions → ADRs

Each confirmed invariant becomes an ADR under `docs/process/adr/` named
`adr-NNNN-<slug>.md` (see `docs/process/adr/template.md`). Record two axes:

- **Status:** Proposed | Accepted | Superseded.
- **Intent:** keep | change-planned | tolerated — endorsed vs. documented-but-
  migrating vs. accepted-debt. Link the rule to the ADR via `rules[].adr`.
````

- [ ] **Step 8: Run the tests to verify they pass**

Run: `uv run pytest tests/test_arch_onboarding.py -q`
Expected: PASS (6 tests).

- [ ] **Step 9: Verify no jinja leak / doc-drift stays clean with both modules on**

Run:
```bash
uv run pytest tests/ -q
```
Expected: PASS — existing SP1 tests still green (the module-doc examples are placeholder-form, so doc-drift-gate does not flag them).

- [ ] **Step 10: Commit**

```bash
git add copier.yml tests/conftest.py tests/test_arch_onboarding.py \
  "template/scripts/process/{% if modules.arch_onboarding %}check_architecture.py{% endif %}.jinja" \
  "template/docs/process/{% if modules.arch_onboarding %}modules{% endif %}/arch-onboarding.md.jinja" \
  "template/{% if modules.arch_onboarding %}ARCHITECTURE.md{% endif %}.jinja"
git commit -m "feat: arch-onboarding module scaffold + inert arch-gate"
```

---

### Task 2: Existence + manifest-consistency checks

**Files:**
- Modify: `template/scripts/process/{% if modules.arch_onboarding %}check_architecture.py{% endif %}.jinja` (fill `check()`)
- Test: `tests/test_arch_onboarding.py` (add cases)

**Interfaces:**
- Consumes: `check(root)`, `extract_block`, `_run`, `_write_arch` from Task 1.
- Produces: `check()` now hard-fails on missing `code_roots`/`layers` paths, missing interface files, interface symbols absent from their file, rules naming unknown layers, and malformed `forbid`. Unknown top-level keys stay ignored.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_arch_onboarding.py`:

```python
CLEAN_BLOCK = """\
code_roots: [src]
layers:
  domain: {path: src/domain}
  infra:  {path: src/infra}
interfaces:
  - {name: OrderPort, path: src/domain/ports.py}
"""


def _seed_code(out: Path):
    (out / "src/domain").mkdir(parents=True, exist_ok=True)
    (out / "src/infra").mkdir(parents=True, exist_ok=True)
    (out / "src/domain/ports.py").write_text("class OrderPort:\n    ...\n")


def test_existence_pass(render, tmp_path):
    out = _render(render, tmp_path)
    _seed_code(out)
    _write_arch(out, CLEAN_BLOCK)
    r = _run(out)
    assert r.returncode == 0, r.stdout
    assert "OK" in r.stdout


def test_layer_path_missing(render, tmp_path):
    out = _render(render, tmp_path)
    _seed_code(out)
    (out / "src/infra").rmdir()
    _write_arch(out, CLEAN_BLOCK)
    r = _run(out)
    assert r.returncode == 1
    assert "infra" in r.stdout


def test_interface_symbol_missing(render, tmp_path):
    out = _render(render, tmp_path)
    _seed_code(out)
    (out / "src/domain/ports.py").write_text("class Something:\n    ...\n")
    _write_arch(out, CLEAN_BLOCK)
    r = _run(out)
    assert r.returncode == 1
    assert "OrderPort" in r.stdout


def test_rule_unknown_layer(render, tmp_path):
    out = _render(render, tmp_path)
    _seed_code(out)
    block = CLEAN_BLOCK + "rules:\n  - {forbid: domain -> nope}\n"
    _write_arch(out, block)
    r = _run(out)
    assert r.returncode == 1
    assert "nope" in r.stdout


def test_forward_compat_unknown_key_ignored(render, tmp_path):
    out = _render(render, tmp_path)
    _seed_code(out)
    block = CLEAN_BLOCK + "external:\n  repos: [{name: billing, url: 'gh:o/billing'}]\n"
    _write_arch(out, block)
    r = _run(out)
    assert r.returncode == 0, r.stdout
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_arch_onboarding.py -q`
Expected: FAIL — `check()` currently returns `[], []` for a valid block, so the missing/symbol/unknown-layer cases do not fail as expected.

- [ ] **Step 3: Fill in `check()`**

In `check_architecture.py`, add two imports — `import re` (after `from __future__`) and `import yaml` (in the third-party group, matching SP1's `check_doc_drift.py` import layout). Then replace the placeholder line `return [], []  # existence/conformance/adr checks added in Tasks 2-4` with:

```python
    data = yaml.safe_load(block) or {}
    hard: list[str] = []

    for r in data.get("code_roots", []) or []:
        if not (root / r).exists():
            hard.append(f"code_root missing: {r}")

    layers = data.get("layers", {}) or {}
    for name, spec in layers.items():
        path = (spec or {}).get("path")
        if not path:
            hard.append(f"layer '{name}' has no path")
        elif not (root / path).exists():
            hard.append(f"layer '{name}' path missing: {path}")

    for iface in data.get("interfaces", []) or []:
        name, path = iface.get("name"), iface.get("path")
        target = root / path if path else None
        if not target or not target.is_file():
            hard.append(f"interface '{name}' file missing: {path}")
        elif name and not re.search(rf"\b{re.escape(name)}\b", target.read_text(encoding="utf-8")):
            hard.append(f"interface symbol '{name}' not found in {path}")

    for rule in data.get("rules", []) or []:
        forbid = rule.get("forbid", "")
        m = re.match(r"\s*([\w-]+)\s*->\s*([\w-]+)\s*$", str(forbid))
        if not m:
            hard.append(f"malformed rule forbid: {forbid!r}")
        else:
            for layer in (m.group(1), m.group(2)):
                if layer not in layers:
                    hard.append(f"rule references unknown layer '{layer}' in {forbid!r}")

    return hard, []
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_arch_onboarding.py -q`
Expected: PASS (all Task 1 + Task 2 cases).

- [ ] **Step 5: Commit**

```bash
git add "template/scripts/process/{% if modules.arch_onboarding %}check_architecture.py{% endif %}.jinja" tests/test_arch_onboarding.py
git commit -m "feat: arch-gate existence + manifest-consistency checks"
```

---

### Task 3: Best-effort layering conformance

**Files:**
- Modify: `template/scripts/process/{% if modules.arch_onboarding %}check_architecture.py{% endif %}.jinja`
- Test: `tests/test_arch_onboarding.py`

**Interfaces:**
- Consumes: `check()` from Task 2.
- Produces: `check()` now appends conformance results — a present arch-linter (import-linter/`lint-imports`, dependency-cruiser/`depcruise`) runs and hard-fails on non-zero; a configured-but-uninstalled linter is a soft note; no linter at all yields a per-rule manual-review checklist (soft). Helpers `_has_importlinter`, `_has_depcruise`, `_conformance`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_arch_onboarding.py`:

```python
def _stub(bindir: Path, name: str, code: int):
    bindir.mkdir(parents=True, exist_ok=True)
    p = bindir / name
    p.write_text(f"#!/bin/sh\nexit {code}\n")
    p.chmod(0o755)


RULE_BLOCK = CLEAN_BLOCK + "rules:\n  - {forbid: domain -> infra}\n"


def test_conformance_no_linter_checklist(render, tmp_path):
    out = _render(render, tmp_path)
    _seed_code(out)
    _write_arch(out, RULE_BLOCK)
    r = _run(out)
    assert r.returncode == 0, r.stdout
    assert "review" in r.stdout.lower()


def test_conformance_linter_fail(render, tmp_path):
    out = _render(render, tmp_path)
    _seed_code(out)
    (out / ".importlinter").write_text("[importlinter]\n")
    _write_arch(out, RULE_BLOCK)
    bindir = tmp_path / "bin"
    _stub(bindir, "lint-imports", 1)
    r = _run(out, extra_path=str(bindir))
    assert r.returncode == 1
    assert "lint-imports" in r.stdout


def test_conformance_linter_pass(render, tmp_path):
    out = _render(render, tmp_path)
    _seed_code(out)
    (out / ".importlinter").write_text("[importlinter]\n")
    _write_arch(out, RULE_BLOCK)
    bindir = tmp_path / "bin"
    _stub(bindir, "lint-imports", 0)
    r = _run(out, extra_path=str(bindir))
    assert r.returncode == 0, r.stdout
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_arch_onboarding.py -k conformance -q`
Expected: FAIL — no conformance logic yet (no checklist note; linter never run).

- [ ] **Step 3: Add conformance helpers and wire them in**

In `check_architecture.py`, add these imports at the top: `import shutil` and `import subprocess`. Add the helpers above `check()`:

```python
def _has_importlinter(root: Path) -> bool:
    if (root / ".importlinter").is_file():
        return True
    cfg = root / "setup.cfg"
    return cfg.is_file() and "[importlinter]" in cfg.read_text(encoding="utf-8")


def _has_depcruise(root: Path) -> bool:
    return any(
        (root / f).is_file()
        for f in (".dependency-cruiser.js", ".dependency-cruiser.json", ".dependency-cruiser.cjs")
    )


def _conformance(root: Path, rules: list) -> tuple[list[str], list[str]]:
    hard: list[str] = []
    soft: list[str] = []
    ran = False
    linters = []
    if _has_importlinter(root):
        linters.append(("lint-imports", ["lint-imports"]))
    if _has_depcruise(root):
        linters.append(("depcruise", ["depcruise", "--validate"]))
    for label, cmd in linters:
        binary = shutil.which(cmd[0])
        if binary is None:
            soft.append(f"arch-linter '{label}' configured but not installed — conformance unverified")
            continue
        ran = True
        if subprocess.run([binary, *cmd[1:]], cwd=root).returncode != 0:
            hard.append(f"arch-linter '{label}' reported layering violations")
    if not ran and not hard:
        for rule in rules:
            soft.append(f"conformance not machine-verified (no arch-linter): review 'forbid {rule.get('forbid')}' manually")
    return hard, soft
```

Then change the final line of `check()` from `return hard, []` to:

```python
    rules = data.get("rules", []) or []
    hard_c, soft = _conformance(root, rules) if rules else ([], [])
    return hard + hard_c, soft
```

(The `rules` list is already iterated above for layer-consistency; this re-reads the same key to run conformance — leave the earlier loop as is.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_arch_onboarding.py -q`
Expected: PASS (all cases so far).

- [ ] **Step 5: Commit**

```bash
git add "template/scripts/process/{% if modules.arch_onboarding %}check_architecture.py{% endif %}.jinja" tests/test_arch_onboarding.py
git commit -m "feat: arch-gate best-effort layering conformance"
```

---

### Task 4: ADR link existence

**Files:**
- Modify: `template/scripts/process/{% if modules.arch_onboarding %}check_architecture.py{% endif %}.jinja`
- Test: `tests/test_arch_onboarding.py`

**Interfaces:**
- Consumes: `check()` from Task 3.
- Produces: a `rules[].adr: ADR-NNNN` link hard-fails unless a file `docs/process/adr/adr-NNNN-*.md` exists. Helper `_adr_exists(root, adr) -> bool`. Rules without `adr` are unaffected.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_arch_onboarding.py`:

```python
ADR_RULE_BLOCK = CLEAN_BLOCK + "rules:\n  - {forbid: domain -> infra, adr: ADR-0007}\n"


def test_adr_link_missing(render, tmp_path):
    out = _render(render, tmp_path)
    _seed_code(out)
    _write_arch(out, ADR_RULE_BLOCK)
    r = _run(out)
    assert r.returncode == 1
    assert "ADR-0007" in r.stdout


def test_adr_link_present(render, tmp_path):
    out = _render(render, tmp_path)
    _seed_code(out)
    (out / "docs/process/adr/adr-0007-layering.md").write_text("# ADR-0007\n")
    _write_arch(out, ADR_RULE_BLOCK)
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_rule_without_adr_not_checked(render, tmp_path):
    out = _render(render, tmp_path)
    _seed_code(out)
    _write_arch(out, RULE_BLOCK)  # no adr key
    r = _run(out)
    assert r.returncode == 0, r.stdout
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_arch_onboarding.py -k adr -q`
Expected: FAIL — `test_adr_link_missing` returns 0 (no adr check yet).

- [ ] **Step 3: Add `_adr_exists` and the adr check**

In `check_architecture.py`, add the helper above `check()`:

```python
def _adr_exists(root: Path, adr: str) -> bool:
    m = re.search(r"\d+", adr)
    if not m:
        return False
    return bool(list((root / ADR_DIR).glob(f"adr-{int(m.group()):04d}-*.md")))
```

Inside `check()`, in the existing `for rule in data.get("rules", []) or []:` loop (the layer-consistency loop from Task 2), add after the `forbid` handling:

```python
        adr = rule.get("adr")
        if adr and not _adr_exists(root, adr):
            hard.append(f"rule adr link '{adr}' has no file under {ADR_DIR}/")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_arch_onboarding.py -q`
Expected: PASS (all cases).

- [ ] **Step 5: Commit**

```bash
git add "template/scripts/process/{% if modules.arch_onboarding %}check_architecture.py{% endif %}.jinja" tests/test_arch_onboarding.py
git commit -m "feat: arch-gate hard-checks linked ADR file existence"
```

---

### Task 5: Gate-runner registration + doc-drift watches ARCHITECTURE.md

**Files:**
- Modify: `template/scripts/process/gate_runner.py.jinja` (add `arch-onboarding` to `GATES`)
- Modify: `template/scripts/process/{% if modules.doc_drift_gate %}check_doc_drift.py{% endif %}.jinja` (add `ARCHITECTURE.md` to `SCAN_FILES`)
- Test: `tests/test_arch_onboarding.py`

**Interfaces:**
- Consumes: SP1 `gate_runner.py` (`GATES`, `active_gates`, `--list`); SP1 `check_doc_drift.py` (`SCAN_FILES`).
- Produces: `gate_runner --list` prints `arch-onboarding` when the module is on; doc-drift-gate flags dead path references in `ARCHITECTURE.md` prose when both modules are on.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_arch_onboarding.py`:

```python
def _runner_list(out: Path):
    return subprocess.run(
        [sys.executable, str(out / "scripts/process/gate_runner.py"), "--list"],
        cwd=out, capture_output=True, text=True,
    )


def test_runner_lists_arch_when_on(render, tmp_path):
    out = _render(render, tmp_path)
    r = _runner_list(out)
    assert r.returncode == 0, r.stderr
    assert "arch-onboarding" in r.stdout


def test_runner_skips_arch_when_off(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    r = _runner_list(out)
    assert r.returncode == 0, r.stderr
    assert "arch-onboarding" not in r.stdout


def test_docdrift_scans_architecture_md(render, tmp_path):
    out = render(
        tmp_path,
        {"project_name": "d", "modules": {"doc_drift_gate": True, "arch_onboarding": True}},
    )
    (out / "ARCHITECTURE.md").write_text("# Architecture\n\nSee [x](does/not/exist.py).\n")
    r = subprocess.run(
        [sys.executable, str(out / "scripts/process/check_doc_drift.py"), str(out)],
        capture_output=True, text=True,
    )
    assert r.returncode == 1
    assert "ARCHITECTURE.md" in r.stdout
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_arch_onboarding.py -k "runner or docdrift" -q`
Expected: FAIL — `arch-onboarding` not in `GATES`; doc-drift does not scan `ARCHITECTURE.md`.

- [ ] **Step 3: Register the gate**

In `template/scripts/process/gate_runner.py.jinja`, change the `GATES` dict to:

```python
GATES = {
    "doc-drift-gate": ("doc_drift_gate", [sys.executable, "scripts/process/check_doc_drift.py", "."]),
    "arch-onboarding": ("arch_onboarding", [sys.executable, "scripts/process/check_architecture.py", "."]),
}
```

- [ ] **Step 4: Add ARCHITECTURE.md to doc-drift scan set**

In `template/scripts/process/{% if modules.doc_drift_gate %}check_doc_drift.py{% endif %}.jinja`, change the `SCAN_FILES` line to:

```python
SCAN_FILES = ["CLAUDE.md", "AGENTS.md", ".github/copilot-instructions.md", "ARCHITECTURE.md"]
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_arch_onboarding.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add "template/scripts/process/gate_runner.py.jinja" \
  "template/scripts/process/{% if modules.doc_drift_gate %}check_doc_drift.py{% endif %}.jinja" \
  tests/test_arch_onboarding.py
git commit -m "feat: register arch-onboarding gate + doc-drift watches ARCHITECTURE.md"
```

---

### Task 6: Core ADR template gains the Intent axis

**Files:**
- Modify: `template/docs/process/adr/template.md`
- Test: `tests/test_core_docs.py` (add one case)

**Interfaces:**
- Consumes: the SP1 core ADR template.
- Produces: every rendered project's `docs/process/adr/template.md` carries a `## Intent` section listing `keep | change-planned | tolerated`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_core_docs.py`:

```python
def test_adr_template_has_intent_axis(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    text = (out / "docs/process/adr/template.md").read_text()
    assert "## Intent" in text
    for v in ["keep", "change-planned", "tolerated"]:
        assert v in text, v
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_core_docs.py::test_adr_template_has_intent_axis -q`
Expected: FAIL — the template has no `## Intent` section.

- [ ] **Step 3: Add the Intent axis to the ADR template**

In `template/docs/process/adr/template.md`, insert this section between `## Status` and `## Context`:

```markdown
## Intent

keep | change-planned | tolerated

Endorsement, independent of lifecycle status. `keep` = deliberately endorsed;
`change-planned` = current reality, migration intended (link the follow-up);
`tolerated` = accepted debt, not endorsed, no active migration.
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/test_core_docs.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add template/docs/process/adr/template.md tests/test_core_docs.py
git commit -m "feat: add Intent axis (keep|change-planned|tolerated) to ADR template"
```

---

## Final verification (after all tasks)

- [ ] **Full suite green:** `uv run pytest tests/ -q` — all SP1 + SP2 tests pass.
- [ ] **Lint clean:** `uv run ruff check .`
- [ ] **Real copier render, module on:**
  ```bash
  printf 'modules:\n  arch_onboarding: true\n' > /tmp/sp2-data.yml
  rm -rf /tmp/sp2-check
  uvx copier copy --defaults --data project_name=Demo --data-file /tmp/sp2-data.yml . /tmp/sp2-check
  cd /tmp/sp2-check && python scripts/process/check_architecture.py .
  ```
  Expected: `arch-gate: note: architecture not onboarded yet ...` then `arch-gate: OK`, exit 0 (the seed is inert).
- [ ] **Module off leaves no arch files:** render with defaults → no `ARCHITECTURE.md`, no `check_architecture.py`.

## Self-Review (run by plan author)

**Spec coverage** — every spec section maps to a task:
- §2 own-repo scope / no `external:` → Task 2 (`test_forward_compat_unknown_key_ignored`).
- §3 manifest schema (code_roots/layers/rules/interfaces) → Tasks 2–4.
- §4a interview + seed → Task 1.
- §4b gate check table (existence hard, symbol, conformance, adr, consistency, degradation) → Tasks 1–4.
- §4c ADRs from onboarding + two axes + `rules[].adr` link → Tasks 4 (link) + 6 (Intent axis) + Task 1 interview doc.
- §5 wiring / degradation / doc-drift interplay / files → Tasks 1, 5.
- §6 tests → each task's test steps.
- Honest ceiling → Task 3.

**Placeholder scan:** none — every code step shows complete code.

**Type consistency:** `check()` returns `(hard, soft)` in every task; `extract_block`, `_conformance`, `_adr_exists`, `_has_importlinter`, `_has_depcruise` signatures are stable across tasks; test helpers `_render`/`_run`/`_write_arch`/`_seed_code`/`_stub` defined before first use.
