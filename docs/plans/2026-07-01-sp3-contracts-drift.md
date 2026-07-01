# contracts-drift Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship an opt-in `contracts_drift` copier module: a gate that hard-catches contract drift on committed artifacts via a content-hash pin ratchet, and best-effort-checks live conformance via an optional project-supplied verify command — universal, REST + Kafka shipped as inert examples.

**Architecture:** A new manifest module (default off) rendered by copier path-conditionals. A contract is declared one-per-file under `docs/process/contracts/<id>.json` (id = filename stem) as a committed `artifact` plus a `pin`. Gate `check_contracts.py` hard-fails (exit 1) on structural defects, a missing/escaping artifact, and a content-hash pin that no longer matches its artifact; it degrades everything that touches an external system (opaque non-hash pin, live conformance) to an advisory note (exit 0). REST + Kafka ship as inert `*.example.json` seeds. No adapter code.

**Tech Stack:** Python 3 stdlib only (`hashlib`, `subprocess`, `shlex`, `json`, `re`, `pathlib`); copier + Jinja path-conditionals; pytest via the repo's `render` fixture.

## Global Constraints

- **Stdlib only.** `check_contracts.py` imports `hashlib`, `json`, `re`, `shlex`, `subprocess`, `sys`, `pathlib` — no third-party dependency.
- **Honest ceiling, no false-green.** HARD (exit 1): valid JSON/dict; the four required fields non-empty; `id` == filename stem; `artifact` exists and is inside the repo; a **content-hash** `pin` (`sha256:`/`sha512:`/`sha1:`) that no longer matches the artifact bytes. BEST-EFFORT (note, exit 0): an opaque (non-hash) pin; live conformance via `verify`. **A `verify` command NEVER causes a non-zero exit** — nonconformance, an unlaunchable command, and a timeout are all notes.
- **Module default off.** `contracts_drift: false` in `copier.yml` `modules.default`.
- **`.example.json` files are skipped** by the gate (inert seeds), matching feature-registry.
- **Neutral template.** No project-specific term in any rendered artifact. Neutrality guard list: `Kenni`, `KenniNext`, `Seb`, `Signal`, `SvelteKit`, `user_id=1`, `surface:ios`.
- **`id` == filename stem** (hard). This gives id-uniqueness for free (filenames are unique in a dir) — there is deliberately no separate uniqueness check.
- **`artifact` is required and committed.** A contract in dev-process is a committed snapshot + a pin; a registry-only contract still commits a snapshot file.
- **`kind` is an open free string** (`rest`/`kafka`/…), never enum-enforced — universality over a closed list.
- **`verify` runs via `shlex.split` (argv, no shell).** Shell features (env vars, pipes) go through an explicit `sh -c '...'` wrapper written by the project.
- **Naming:** module answer key `contracts_drift`; gate name `contracts-drift`; gate output prefix `contracts-gate:`; deposit dir `docs/process/contracts/`.
- **Commit trailers on every commit:**
  ```
  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01MS9nrQC9f9WGhipvJ9NFpk
  ```
- **Environment:** repo `/home/claude/Projekte/dev-process`; Python `.venv/bin/python`; linter `.venv/bin/ruff`. Shell cwd resets between calls — prefix each with `cd /home/claude/Projekte/dev-process`.

---

## File Structure

- **Create** `template/scripts/process/{% raw %}{% if modules.contracts_drift %}check_contracts.py{% endif %}{% endraw %}.jinja` — the gate (Tasks 1–3).
- **Modify** `template/scripts/process/gate_runner.py.jinja` — register `contracts-drift` (Task 4).
- **Create** `template/docs/process/{% raw %}{% if modules.contracts_drift %}contracts{% endif %}{% endraw %}/rest-orders.example.json` — inert REST seed (Task 5).
- **Create** `template/docs/process/{% raw %}{% if modules.contracts_drift %}contracts{% endif %}{% endraw %}/kafka-order-events.example.json` — inert Kafka seed (Task 5).
- **Create** `template/docs/process/{% raw %}{% if modules.contracts_drift %}modules{% endif %}{% endraw %}/contracts-drift.md` — module doc (Task 5).
- **Modify** `copier.yml` — `contracts_drift: false` in `modules.default` (Task 1).
- **Modify** `tests/conftest.py` — add `contracts_drift: False` to the full defaults dict (Task 1).
- **Create** `tests/test_contracts_drift.py` — all tests (Tasks 1–5).

> **copier note:** the `.jinja` suffix Jinja-renders file *content*; `{% if modules.contracts_drift %}…{% endif %}` path segments gate whether a file renders at all. `check_contracts.py` uses only single-brace f-strings and brace-free regexes — no `{{`/`{%`/`{#`. The `.example.json` seeds and the module `.md` are non-`.jinja` (copied verbatim), so their content is never templated.

---

### Task 1: copier wiring + structural hard core

**Files:**
- Modify: `copier.yml` (add to `modules.default`)
- Modify: `tests/conftest.py` (add to full defaults dict)
- Create: `template/scripts/process/{% raw %}{% if modules.contracts_drift %}check_contracts.py{% endif %}{% endraw %}.jinja`
- Test: `tests/test_contracts_drift.py`

**Interfaces:**
- Produces: `check_contracts.py` with `check(root: Path) -> tuple[list[str], list[str]]` (hard, soft) and a `__main__` that prints `contracts-gate:` lines and exits 1 iff hard is non-empty. Consumed by Tasks 2–4.
- Produces: helper `_contract_files(root) -> list[Path]` (globs `docs/process/contracts/*.json` minus `*.example.json`, sorted).

- [ ] **Step 1: Add the module flag to `copier.yml`**

Modify `copier.yml` `modules.default` (currently ends with `github_issues: false`):

```yaml
modules:
  type: yaml
  help: "Which opt-in process modules to install"
  default:
    doc_drift_gate: false
    arch_onboarding: false
    feature_registry: false
    github_issues: false
    contracts_drift: false
```

- [ ] **Step 2: Add the flag to the test defaults dict**

Modify the `full` dict in `tests/conftest.py::_copy` (the `modules` line) to:

```python
        "modules": {"doc_drift_gate": False, "arch_onboarding": False, "feature_registry": False, "github_issues": False, "contracts_drift": False},
```

- [ ] **Step 3: Write the failing tests (render + structural hard core)**

Create `tests/test_contracts_drift.py`:

```python
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

KENNI = ["Kenni", "KenniNext", "Seb", "Signal", "SvelteKit", "user_id=1", "surface:ios"]


def _render(render, tmp_path, **mods):
    m = {"contracts_drift": True}
    m.update(mods)
    return render(tmp_path, {"project_name": "d", "modules": m})


def _run(out: Path, path=None, prepend=None):
    env = dict(os.environ)
    if path is not None:
        env["PATH"] = path
    elif prepend:
        env["PATH"] = f"{prepend}{os.pathsep}" + env["PATH"]
    return subprocess.run(
        [sys.executable, str(out / "scripts/process/check_contracts.py"), str(out)],
        capture_output=True, text=True, env=env,
    )


def _sha256(b: bytes) -> str:
    return "sha256:" + hashlib.sha256(b).hexdigest()


def _contract(out: Path, cid="orders-api", kind="rest", artifact="contracts/api.json",
              pin="registry:v1", verify=None, artifact_bytes=b"{}", fname=None, drop=None):
    """Write a contract declaration (+ its artifact file) into a render."""
    if artifact is not None and artifact_bytes is not None:
        ap = out / artifact
        ap.parent.mkdir(parents=True, exist_ok=True)
        ap.write_bytes(artifact_bytes)
    d = {"id": cid, "kind": kind, "artifact": artifact, "pin": pin}
    if verify is not None:
        d["verify"] = verify
    for k in (drop or []):
        d.pop(k, None)
    reg = out / "docs/process/contracts"
    reg.mkdir(parents=True, exist_ok=True)
    (reg / f"{fname or cid}.json").write_text(json.dumps(d))
    return d


def test_no_contracts_note(render, tmp_path):
    out = _render(render, tmp_path)
    r = _run(out)
    assert r.returncode == 0, r.stdout
    assert "no contracts yet" in r.stdout


def test_valid_opaque_pin_ok(render, tmp_path):
    out = _render(render, tmp_path)
    _contract(out, pin="registry:v1")
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_missing_required_field_is_hard(render, tmp_path):
    out = _render(render, tmp_path)
    _contract(out, drop=["kind"])
    r = _run(out)
    assert r.returncode == 1
    assert "'kind'" in r.stdout


def test_malformed_json_is_hard(render, tmp_path):
    out = _render(render, tmp_path)
    reg = out / "docs/process/contracts"
    reg.mkdir(parents=True, exist_ok=True)
    (reg / "broken.json").write_text("{not json")
    r = _run(out)
    assert r.returncode == 1
    assert "invalid JSON" in r.stdout


def test_id_must_equal_filename_stem(render, tmp_path):
    out = _render(render, tmp_path)
    _contract(out, cid="not-the-stem", fname="orders-api")
    r = _run(out)
    assert r.returncode == 1
    assert "filename stem" in r.stdout


def test_missing_artifact_is_hard(render, tmp_path):
    out = _render(render, tmp_path)
    _contract(out, artifact="contracts/gone.json", artifact_bytes=None)  # declaration but no file
    r = _run(out)
    assert r.returncode == 1
    assert "artifact" in r.stdout


def test_artifact_escaping_repo_is_hard(render, tmp_path):
    out = _render(render, tmp_path)
    _contract(out, artifact="../escape.json", artifact_bytes=None)
    r = _run(out)
    assert r.returncode == 1
    assert "escapes" in r.stdout
```

- [ ] **Step 4: Run the tests — verify they fail**

Run: `cd /home/claude/Projekte/dev-process && .venv/bin/python -m pytest tests/test_contracts_drift.py -q`
Expected: FAIL (the gate file does not render yet → `check_contracts.py` missing → non-zero exit / FileNotFoundError).

- [ ] **Step 5: Write the gate (structural core)**

Create `template/scripts/process/{% raw %}{% if modules.contracts_drift %}check_contracts.py{% endif %}{% endraw %}.jinja`:

```python
#!/usr/bin/env python3
"""contracts-drift gate: detect drift in declared external contracts.

A contract is declared one-per-file under docs/process/contracts/<id>.json as a
committed artifact plus a pin. Structure, a committed artifact, and a
content-hash pin are hard-guaranteed (CI exit 1): if the artifact changes
without its pin being updated, the build fails — a deliberate re-pin ratchet.
Everything that depends on an external system is best-effort and advisory,
never faked as verified: an opaque (non-hash) pin and live conformance via an
optional project-supplied verify command yield notes, never a failure.
Language-agnostic; Python stdlib only."""
from __future__ import annotations

import hashlib
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

CONTRACTS_DIR = "docs/process/contracts"
VERIFY_TIMEOUT_S = 30  # cap a hung verify command so it cannot wedge CI
REQUIRED = ("id", "kind", "artifact", "pin")
_HASH_RE = re.compile(r"^(sha256|sha512|sha1):([0-9a-fA-F]+)$")


def _contract_files(root: Path) -> list[Path]:
    d = root / CONTRACTS_DIR
    if not d.is_dir():
        return []
    return sorted(p for p in d.glob("*.json") if not p.name.endswith(".example.json"))


def _artifact_path(root: Path, artifact: str) -> Path | None:
    """Resolve an artifact path strictly inside root; None if it escapes."""
    resolved = (root / artifact).resolve()
    root_resolved = root.resolve()
    if root_resolved not in resolved.parents:
        return None
    return resolved


def _check_contract(root: Path, path: Path) -> tuple[list[str], list[str]]:
    hard: list[str] = []
    soft: list[str] = []
    rel = path.relative_to(root)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"{rel}: invalid JSON: {exc}"], []
    if not isinstance(data, dict):
        return [f"{rel}: contract must be a JSON object, got {type(data).__name__}"], []

    for field in REQUIRED:
        val = data.get(field)
        if not isinstance(val, str) or not val.strip():
            hard.append(f"{rel}: '{field}' must be a non-empty string")
    if hard:
        return hard, soft

    if data["id"].strip() != path.stem:
        hard.append(f"{rel}: 'id' {data['id'].strip()!r} must equal the filename stem {path.stem!r}")

    artifact = data["artifact"].strip()
    apath = _artifact_path(root, artifact)
    if apath is None:
        hard.append(f"{rel}: artifact path {artifact!r} escapes the repo root")
        return hard, soft
    if not apath.is_file():
        hard.append(f"{rel}: artifact not committed / does not exist: {artifact}")
        return hard, soft

    return hard, soft


def check(root: Path) -> tuple[list[str], list[str]]:
    files = _contract_files(root)
    if not files:
        return [], ["no contracts yet (contracts dir empty or absent)"]
    hard: list[str] = []
    soft: list[str] = []
    for path in files:
        h, s = _check_contract(root, path)
        hard += h
        soft += s
    return hard, soft


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    hard, soft = check(root)
    for note in soft:
        print(f"contracts-gate: note: {note}")
    if hard:
        print("contracts-gate: FAILED:")
        for h in hard:
            print(f"  - {h}")
        return 1
    print("contracts-gate: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 6: Run the tests — verify they pass**

Run: `cd /home/claude/Projekte/dev-process && .venv/bin/python -m pytest tests/test_contracts_drift.py -q`
Expected: PASS (7 tests). Then `.venv/bin/ruff check .` → clean.

- [ ] **Step 7: Commit**

```bash
cd /home/claude/Projekte/dev-process
git add copier.yml tests/conftest.py tests/test_contracts_drift.py \
  "template/scripts/process/{% raw %}{% if modules.contracts_drift %}check_contracts.py{% endif %}{% endraw %}.jinja"
git commit -F - <<'MSG'
feat: add contracts_drift module with structural gate

<trailers>
MSG
```
(Replace `<trailers>` with the two Global-Constraints trailer lines.)

---

### Task 2: content-hash pin drift ratchet

**Files:**
- Modify: `template/scripts/process/{% raw %}{% if modules.contracts_drift %}check_contracts.py{% endif %}{% endraw %}.jinja`
- Test: `tests/test_contracts_drift.py`

**Interfaces:**
- Consumes: `_check_contract`, `_artifact_path`, `_HASH_RE` from Task 1.
- Produces: `_pin_hash(pin: str) -> tuple[str, str] | None` (algo, lowercased-hex) and, inside `_check_contract`, a hard "artifact changed but pin not updated" on hash mismatch + a soft "opaque pin" note otherwise.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_contracts_drift.py`:

```python
def test_sha256_pin_match_is_clean(render, tmp_path):
    out = _render(render, tmp_path)
    body = b'{"openapi": "3.1.0"}'
    _contract(out, pin=_sha256(body), artifact_bytes=body)
    r = _run(out)
    assert r.returncode == 0, r.stdout
    assert "opaque pin" not in r.stdout
    assert "changed but pin" not in r.stdout


def test_sha256_pin_mismatch_is_hard(render, tmp_path):
    out = _render(render, tmp_path)
    _contract(out, pin=_sha256(b"OLD"), artifact_bytes=b"NEW-the-artifact-was-edited")
    r = _run(out)
    assert r.returncode == 1
    assert "changed but pin not updated" in r.stdout


def test_opaque_pin_is_soft(render, tmp_path):
    out = _render(render, tmp_path)
    _contract(out, pin="registry:v3")
    r = _run(out)
    assert r.returncode == 0, r.stdout
    assert "opaque pin" in r.stdout


def test_sha512_pin_match_is_clean(render, tmp_path):
    out = _render(render, tmp_path)
    body = b"schema-bytes"
    pin = "sha512:" + hashlib.sha512(body).hexdigest()
    _contract(out, pin=pin, artifact_bytes=body)
    r = _run(out)
    assert r.returncode == 0, r.stdout
    assert "opaque pin" not in r.stdout
```

- [ ] **Step 2: Run — verify the two new pin tests fail**

Run: `cd /home/claude/Projekte/dev-process && .venv/bin/python -m pytest tests/test_contracts_drift.py -q -k "pin"`
Expected: `test_sha256_pin_mismatch_is_hard` FAILS (no hash check yet → exit 0, not 1); `test_opaque_pin_is_soft` FAILS (no "opaque pin" note yet). The two "match_is_clean" tests may already pass (no note is emitted yet).

- [ ] **Step 3: Add the pin ratchet to `check_contracts.py`**

Add the `_pin_hash` helper after `_artifact_path`:

```python
def _pin_hash(pin: str) -> tuple[str, str] | None:
    m = _HASH_RE.match(pin)
    return (m.group(1), m.group(2).lower()) if m else None
```

In `_check_contract`, replace the final `return hard, soft` with the pin logic:

```python
    pin = data["pin"].strip()
    parsed = _pin_hash(pin)
    if parsed is None:
        soft.append(
            f"{rel}: opaque pin {pin!r} — integrity not machine-checkable; "
            "use a sha256: pin or a verify command"
        )
    else:
        algo, expected = parsed
        actual = hashlib.new(algo, apath.read_bytes()).hexdigest()
        if actual != expected:
            hard.append(
                f"{rel}: artifact changed but pin not updated "
                f"({algo} {actual} != {expected}) — re-pin deliberately"
            )

    return hard, soft
```

- [ ] **Step 4: Run — verify pass**

Run: `cd /home/claude/Projekte/dev-process && .venv/bin/python -m pytest tests/test_contracts_drift.py -q`
Expected: PASS (11 tests). `.venv/bin/ruff check .` → clean.

- [ ] **Step 5: Commit**

```bash
cd /home/claude/Projekte/dev-process
git add tests/test_contracts_drift.py \
  "template/scripts/process/{% raw %}{% if modules.contracts_drift %}check_contracts.py{% endif %}{% endraw %}.jinja"
git commit -F - <<'MSG'
feat: add content-hash pin drift ratchet

<trailers>
MSG
```

---

### Task 3: best-effort conformance via verify

**Files:**
- Modify: `template/scripts/process/{% raw %}{% if modules.contracts_drift %}check_contracts.py{% endif %}{% endraw %}.jinja`
- Test: `tests/test_contracts_drift.py`

**Interfaces:**
- Consumes: `_check_contract`, `VERIFY_TIMEOUT_S` from Task 1.
- Produces: `_run_verify(command: str) -> str | None` (None = conformed; else a note string). NEVER raises, NEVER hard-fails. A launched non-zero verify, an unlaunchable command, and a timeout are all soft notes.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_contracts_drift.py`:

```python
def _stub_cmd(bindir: Path, name: str, code: int):
    bindir.mkdir(parents=True, exist_ok=True)
    p = bindir / name
    p.write_text(f"#!/bin/sh\nexit {code}\n")
    p.chmod(0o755)


def test_verify_absent_notes(render, tmp_path):
    out = _render(render, tmp_path)
    _contract(out, pin=_sha256(b"{}"), artifact_bytes=b"{}")  # clean pin, no verify
    r = _run(out)
    assert r.returncode == 0, r.stdout
    assert "no verify command" in r.stdout


def test_verify_zero_no_note(render, tmp_path):
    out = _render(render, tmp_path)
    _contract(out, pin=_sha256(b"{}"), artifact_bytes=b"{}", verify="okcheck")
    bindir = tmp_path / "bin"
    _stub_cmd(bindir, "okcheck", 0)
    r = _run(out, prepend=str(bindir))
    assert r.returncode == 0, r.stdout
    assert "no verify command" not in r.stdout
    assert "nonconformance" not in r.stdout


def test_verify_nonzero_is_soft(render, tmp_path):
    # load-bearing must-not-hard-fail guard: a verify that reports drift -> note, exit 0
    out = _render(render, tmp_path)
    _contract(out, pin=_sha256(b"{}"), artifact_bytes=b"{}", verify="failcheck")
    bindir = tmp_path / "bin"
    _stub_cmd(bindir, "failcheck", 1)
    r = _run(out, prepend=str(bindir))
    assert r.returncode == 0, r.stdout
    assert "nonconformance" in r.stdout


def test_verify_unlaunchable_is_soft(render, tmp_path):
    # load-bearing must-not-hard-fail guard: a command not on PATH -> note, exit 0
    out = _render(render, tmp_path)
    _contract(out, pin=_sha256(b"{}"), artifact_bytes=b"{}", verify="definitely-not-a-real-cmd-xyz")
    r = _run(out)
    assert r.returncode == 0, r.stdout
    assert "could not run verify" in r.stdout
```

- [ ] **Step 2: Run — verify the verify tests fail**

Run: `cd /home/claude/Projekte/dev-process && .venv/bin/python -m pytest tests/test_contracts_drift.py -q -k "verify"`
Expected: FAIL (no verify handling yet — no "no verify command" / "nonconformance" / "could not run" notes are emitted).

- [ ] **Step 3: Add the verify handling to `check_contracts.py`**

Add the `_run_verify` helper after `_pin_hash`:

```python
def _run_verify(command: str) -> str | None:
    """Run a project-supplied verify command as argv (no shell). Returns None
    on conformance (exit 0), else an advisory note. Never raises, never
    hard-fails — a verify reaching an external system must not gate CI."""
    try:
        r = subprocess.run(
            shlex.split(command),
            capture_output=True, text=True, timeout=VERIFY_TIMEOUT_S,
        )
    except (subprocess.TimeoutExpired, OSError):
        return "could not run verify command"
    if r.returncode != 0:
        return "verify reported possible nonconformance"
    return None
```

In `_check_contract`, insert the verify block just before the final `return hard, soft` (after the pin block):

```python
    verify = data.get("verify")
    if isinstance(verify, str) and verify.strip():
        note = _run_verify(verify.strip())
        if note:
            soft.append(f"{rel}: {note}")
    else:
        soft.append(f"{rel}: conformance not machine-verified — no verify command")

    return hard, soft
```

- [ ] **Step 4: Run — verify pass**

Run: `cd /home/claude/Projekte/dev-process && .venv/bin/python -m pytest tests/test_contracts_drift.py -q`
Expected: PASS (15 tests). `.venv/bin/ruff check .` → clean.

- [ ] **Step 5: Commit**

```bash
cd /home/claude/Projekte/dev-process
git add tests/test_contracts_drift.py \
  "template/scripts/process/{% raw %}{% if modules.contracts_drift %}check_contracts.py{% endif %}{% endraw %}.jinja"
git commit -F - <<'MSG'
feat: add best-effort conformance via optional verify command

<trailers>
MSG
```

---

### Task 4: register the gate in the manifest runner

**Files:**
- Modify: `template/scripts/process/gate_runner.py.jinja` (the `GATES` dict)
- Test: `tests/test_contracts_drift.py`

**Interfaces:**
- Consumes: the `GATES` dict shape `name -> (module_key, [argv])` from the existing runner.
- Produces: a `contracts-drift` entry listed by `gate_runner.py --list` iff `contracts_drift` is active.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_contracts_drift.py`:

```python
def _runner_list(out: Path):
    return subprocess.run(
        [sys.executable, str(out / "scripts/process/gate_runner.py"), "--list"],
        cwd=out, capture_output=True, text=True,
    )


def test_runner_lists_contracts_when_on(render, tmp_path):
    out = _render(render, tmp_path)
    r = _runner_list(out)
    assert r.returncode == 0, r.stderr
    assert "contracts-drift" in r.stdout


def test_runner_skips_contracts_when_off(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    r = _runner_list(out)
    assert r.returncode == 0, r.stderr
    assert "contracts-drift" not in r.stdout
```

- [ ] **Step 2: Run — verify fail**

Run: `cd /home/claude/Projekte/dev-process && .venv/bin/python -m pytest tests/test_contracts_drift.py -q -k "runner"`
Expected: `test_runner_lists_contracts_when_on` FAILS (gate not registered).

- [ ] **Step 3: Register the gate**

In `template/scripts/process/gate_runner.py.jinja`, add one line to the `GATES` dict after the `github-issues` entry:

```python
    "contracts-drift": ("contracts_drift", [sys.executable, "scripts/process/check_contracts.py", "."]),
```

- [ ] **Step 4: Run — verify pass**

Run: `cd /home/claude/Projekte/dev-process && .venv/bin/python -m pytest tests/test_contracts_drift.py -q`
Expected: PASS (17 tests). `.venv/bin/ruff check .` → clean.

- [ ] **Step 5: Commit**

```bash
cd /home/claude/Projekte/dev-process
git add tests/test_contracts_drift.py template/scripts/process/gate_runner.py.jinja
git commit -F - <<'MSG'
feat: register contracts-drift gate in the manifest runner

<trailers>
MSG
```

---

### Task 5: static artifacts (REST + Kafka seeds, module doc) + verification

**Files:**
- Create: `template/docs/process/{% raw %}{% if modules.contracts_drift %}contracts{% endif %}{% endraw %}/rest-orders.example.json`
- Create: `template/docs/process/{% raw %}{% if modules.contracts_drift %}contracts{% endif %}{% endraw %}/kafka-order-events.example.json`
- Create: `template/docs/process/{% raw %}{% if modules.contracts_drift %}modules{% endif %}{% endraw %}/contracts-drift.md`
- Modify: `README.md` (module catalog)
- Test: `tests/test_contracts_drift.py`

**Interfaces:**
- Consumes: the `.example.json`-skip rule from Task 1 (`_contract_files`).
- Produces: three rendered files present only when the module is on; leak-free when off; the module doc's path refs resolve under doc-drift.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_contracts_drift.py`:

```python
def test_artifacts_present_when_on(render, tmp_path):
    out = _render(render, tmp_path)
    assert (out / "docs/process/contracts/rest-orders.example.json").is_file()
    assert (out / "docs/process/contracts/kafka-order-events.example.json").is_file()
    assert (out / "docs/process/modules/contracts-drift.md").is_file()


def test_artifacts_absent_when_off(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    assert not (out / "docs/process/contracts/rest-orders.example.json").exists()
    assert not (out / "docs/process/modules/contracts-drift.md").exists()


def test_seeds_are_skipped_by_gate(render, tmp_path):
    # only the inert *.example.json seeds are present -> gate sees no real contracts
    out = _render(render, tmp_path)
    r = _run(out)
    assert r.returncode == 0, r.stdout
    assert "no contracts yet" in r.stdout


def test_example_seeds_are_valid_json(render, tmp_path):
    out = _render(render, tmp_path)
    for name in ("rest-orders.example.json", "kafka-order-events.example.json"):
        data = json.loads((out / "docs/process/contracts" / name).read_text())
        assert set(("id", "kind", "artifact", "pin")) <= set(data)


def test_artifacts_neutral(render, tmp_path):
    out = _render(render, tmp_path)
    for rel in [
        "docs/process/contracts/rest-orders.example.json",
        "docs/process/contracts/kafka-order-events.example.json",
        "docs/process/modules/contracts-drift.md",
    ]:
        text = (out / rel).read_text()
        for k in KENNI:
            assert k not in text, f"{k} leaked in {rel}"


def test_docdrift_resolves_module_doc_refs(render, tmp_path):
    out = render(
        tmp_path,
        {"project_name": "d", "modules": {"doc_drift_gate": True, "contracts_drift": True}},
    )
    r = subprocess.run(
        [sys.executable, str(out / "scripts/process/check_doc_drift.py"), str(out)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stdout  # module-doc refs resolve
```

- [ ] **Step 2: Run — verify fail**

Run: `cd /home/claude/Projekte/dev-process && .venv/bin/python -m pytest tests/test_contracts_drift.py -q -k "artifacts or seeds or example or docdrift"`
Expected: FAIL (seed + doc files do not render yet).

- [ ] **Step 3: Create the REST seed**

Create `template/docs/process/{% raw %}{% if modules.contracts_drift %}contracts{% endif %}{% endraw %}/rest-orders.example.json` (non-`.jinja`, verbatim; inert — the `.example.json` suffix makes the gate skip it):

```json
{
  "id": "rest-orders",
  "kind": "rest",
  "artifact": "contracts/orders.openapi.json",
  "pin": "sha256:REPLACE_WITH_THE_ARTIFACT_SHA256",
  "verify": "sh -c 'npx --yes openapi-diff contracts/orders.openapi.json \"$ORDERS_LIVE_URL\"'",
  "consumers": ["billing", "shipping"],
  "notes": "A committed OpenAPI snapshot pinned by content hash. Editing the spec without re-pinning fails CI (the drift ratchet). Re-pin deliberately when the contract changes."
}
```

- [ ] **Step 4: Create the Kafka seed**

Create `template/docs/process/{% raw %}{% if modules.contracts_drift %}contracts{% endif %}{% endraw %}/kafka-order-events.example.json` (verbatim; inert):

```json
{
  "id": "kafka-order-events",
  "kind": "kafka",
  "artifact": "contracts/order-created.avsc",
  "pin": "registry:v3",
  "verify": "sh -c 'python scripts/schema_compat.py order-created contracts/order-created.avsc'",
  "consumers": ["fulfilment"],
  "notes": "A committed Avro snapshot whose pin is an opaque schema-registry version (integrity degrades to a note). Backward/forward compatibility is delegated to the project verify command against the registry."
}
```

- [ ] **Step 5: Create the module doc**

Create `template/docs/process/{% raw %}{% if modules.contracts_drift %}modules{% endif %}{% endraw %}/contracts-drift.md`. All illustrative artifact/command paths use `<…>` placeholders so the doc-drift gate skips them; the only real path referenced is the module's own gate:

```markdown
# Module: contracts-drift

Opt-in. Detects **contract drift** — when a service's agreed external interface
(a REST API, a Kafka event schema, …) changes without a deliberate re-pin.
Universal: REST and Kafka ship only as inert examples; you wire your own kinds
and tools.

## When required

Enable when the project depends on, or exposes, an external contract you want
git to guard. A contract is declared one-per-file under
`docs/process/contracts/<id>.json` (the `id` equals the filename stem).

## The contract file

| field | required | meaning |
|---|---|---|
| `id` | yes | slug, equals the filename stem |
| `kind` | yes | free string: `rest`, `kafka`, `graphql`, … (not a fixed list) |
| `artifact` | yes | repo-relative path to a **committed** snapshot of the contract |
| `pin` | yes | the agreed version marker (see below) |
| `verify` | no | a project command that checks live conformance |
| `consumers`, `notes` | no | prose, ignored by the gate |

## Hard vs. best-effort (no false-green)

**Hard (CI fails):** invalid JSON; a missing required field; `id` not equal to
the filename stem; a missing or repo-escaping `artifact`; a **content-hash**
`pin` that no longer matches its artifact.

**Best-effort (advisory note, never fails CI):** an opaque (non-hash) `pin`;
live conformance via `verify`. A `verify` command that reports nonconformance,
cannot be launched, or times out yields a note — never a failed build. External
systems (a live API, a schema registry) must not gate CI; the hard teeth are
the offline integrity check.

## The pin — the drift ratchet

Prefer a content hash for artifacts you control. Compute it and paste it:

    sha256sum contracts/<your-openapi>.json     # -> sha256:<hex>

Now any edit to the artifact that is not accompanied by a re-pin fails CI — a
deliberate acknowledgement that the contract moved. For a schema owned
elsewhere (a registry), use an opaque pin like `registry:<version>`; integrity
then degrades to a note and you lean on `verify`.

## verify — live conformance

`verify` runs as argv (no shell). For env vars or pipes, wrap it yourself:

    sh -c '<your-openapi-diff-or-schema-compat-command>'

Its exit code is advisory: non-zero surfaces a note, it never fails the build.

## Examples

Two inert seeds ship under `docs/process/contracts/`:
`rest-orders.example.json` (REST, hash pin) and `kafka-order-events.example.json`
(Kafka, opaque registry pin). Copy one, drop the `.example`, and point it at a
real committed artifact. The gate itself is `scripts/process/check_contracts.py`.
```

- [ ] **Step 6: Refresh the README module catalog**

In `README.md`, extend the module catalog line (currently ends `… und \`github-issues\` (EARS-Templates + Issue-Ref-Gate).`) to add contracts-drift:

```
Module heute: `doc-drift-gate` (tote Pfad-Referenzen in Docs), `arch-onboarding`
(Architektur gegen echten Code), `feature-registry` (User-Story-/Akzeptanz-/
Test-Traceability), `github-issues` (EARS-Templates + Issue-Ref-Gate) und
`contracts-drift` (Kopplung-als-Contract, Pin-Drift-Ratchet + best-effort-Konformität).
```

And update the roadmap SP3 row to mark slice 3 shipped:

```
| **SP3** Prozess-Vervollständigung (Multi-Repo/-Mensch) | feature-registry · github-issues · contracts-drift | ✅ Slices 1–3 |
```

- [ ] **Step 7: Run the full suite + ruff**

Run: `cd /home/claude/Projekte/dev-process && .venv/bin/python -m pytest -q && .venv/bin/ruff check .`
Expected: all green (97 prior + 23 new = 120 passed), ruff clean.

- [ ] **Step 8: Real render verification (module on + off), via `vcs_ref="HEAD"`**

`copier.run_copy` against the git repo renders from the last **tag**, hiding files committed after it — always verify a real render with `vcs_ref="HEAD"`. Run this script (writes to scratch, cleans up):

```bash
cd /home/claude/Projekte/dev-process && .venv/bin/python - <<'PY'
import copier, json, subprocess, sys, tempfile, hashlib
from pathlib import Path
REPO = "/home/claude/Projekte/dev-process"
with tempfile.TemporaryDirectory() as td:
    out = Path(td) / "proj"
    copier.run_copy(REPO, str(out), data={
        "project_name": "demo",
        "harnesses": {"copilot": False, "agents_md": False},
        "modules": {"doc_drift_gate": True, "contracts_drift": True},
    }, defaults=True, unsafe=True, quiet=True, vcs_ref="HEAD")
    # seed a real contract with a matching sha256 pin
    art = out / "contracts/orders.openapi.json"; art.parent.mkdir(parents=True)
    body = b'{"openapi":"3.1.0"}'; art.write_bytes(body)
    (out / "docs/process/contracts").mkdir(parents=True, exist_ok=True)
    (out / "docs/process/contracts/orders-api.json").write_text(json.dumps({
        "id": "orders-api", "kind": "rest", "artifact": "contracts/orders.openapi.json",
        "pin": "sha256:" + hashlib.sha256(body).hexdigest(),
    }))
    for name, cmd in [("doc-drift", "check_doc_drift.py"), ("contracts", "check_contracts.py")]:
        r = subprocess.run([sys.executable, f"scripts/process/{cmd}", "."], cwd=out, capture_output=True, text=True)
        print(f"{name}: exit {r.returncode} :: {r.stdout.strip().splitlines()[-1] if r.stdout else ''}")
        assert r.returncode == 0, r.stdout
    # now edit the artifact WITHOUT re-pinning -> must hard-fail
    art.write_bytes(b'{"openapi":"3.1.0","changed":true}')
    r = subprocess.run([sys.executable, "scripts/process/check_contracts.py", "."], cwd=out, capture_output=True, text=True)
    print("after edit:", "exit", r.returncode, "::", r.stdout.strip().splitlines()[-1])
    assert r.returncode == 1 and "pin not updated" in r.stdout
    # module OFF -> no leak
    out2 = Path(td) / "off"
    copier.run_copy(REPO, str(out2), data={"project_name": "demo",
        "harnesses": {"copilot": False, "agents_md": False}, "modules": {}},
        defaults=True, unsafe=True, quiet=True, vcs_ref="HEAD")
    assert not (out2 / "scripts/process/check_contracts.py").exists()
    assert not (out2 / "docs/process/contracts").exists()
    print("MODULE OFF: leak-free")
    print("ALL GREEN")
PY
```
Expected: doc-drift + contracts exit 0 on the clean render; after editing the artifact the gate exits 1 with "pin not updated"; module-off is leak-free; `ALL GREEN`.

- [ ] **Step 9: Commit**

```bash
cd /home/claude/Projekte/dev-process
git add README.md tests/test_contracts_drift.py \
  "template/docs/process/{% raw %}{% if modules.contracts_drift %}contracts{% endif %}{% endraw %}/rest-orders.example.json" \
  "template/docs/process/{% raw %}{% if modules.contracts_drift %}contracts{% endif %}{% endraw %}/kafka-order-events.example.json" \
  "template/docs/process/{% raw %}{% if modules.contracts_drift %}modules{% endif %}{% endraw %}/contracts-drift.md"
git commit -F - <<'MSG'
feat: add REST/Kafka example contracts, module doc, README catalog

<trailers>
MSG
```

---

## Post-plan: merge gate

After Task 5, mirror Slice 2:
1. Full suite green + ruff clean; re-verify ff-only against `origin/main` (fetch → merge-base == main tip).
2. Build a read-only review bundle (`git diff -U8 main..HEAD`) and dispatch an independent Opus merge-gate reviewer with these explicit lenses: **verify never exits non-zero**; **hash mismatch is the only pin hard-fail**; **no Kenni leakage**; **`contracts_drift` registered in copier.yml + gate_runner + README**; **doc-drift stays green (module-doc refs are placeholders or real)**.
3. On a clean review: `git checkout main && git merge --ff-only design/sp3-contracts-drift`; annotated tag `v0.5.0`; push main + tag; delete the branch.
4. Update memory (`project_dev_process_meta_repo.md` slice-3 bullet → SHIPPED; MEMORY.md index line).

---

## Self-Review

**1. Spec coverage** (against `docs/design/2026-07-01-sp3-contracts-drift-design.md`):
- §3 module shape / deposit dir / default off / gate_runner + copier.yml + README registration → Tasks 1, 4, 5. ✓
- §4 schema (id/kind/artifact/pin required; verify/consumers/notes optional; id==stem; artifact committed; kind open) → Tasks 1–3. ✓
- §5 hard list (JSON/dict, required, id==stem, artifact exists+within-root, hash mismatch) → Tasks 1–2. ✓
- §5 best-effort (opaque pin, no verify, unlaunchable verify, non-zero verify all soft) → Tasks 2–3, with the two must-not-hard-fail guards as load-bearing tests. ✓
- §6 artifacts (gate, 2 seeds, module doc) + modifications → Tasks 1, 4, 5. ✓
- §8 REST + Kafka inert exemplars → Task 5. ✓
- §9 test plan (render on/off, all hard, all soft, seeds skipped, neutrality, doc-drift, gate_runner list) → Tasks 1–5. ✓
- §10 dogfooding deferred → no task needed (test suite is the proof). ✓

**2. Placeholder scan:** no TBD/TODO; every code + test step carries full content; the `<trailers>` token in commit steps is an explicit instruction to paste the two Global-Constraints trailer lines, not a code placeholder.

**3. Type consistency:** `check(root) -> (hard, soft)`, `_check_contract(root, path) -> (hard, soft)`, `_contract_files(root) -> list[Path]`, `_artifact_path(root, artifact) -> Path | None`, `_pin_hash(pin) -> tuple[str,str] | None`, `_run_verify(command) -> str | None` are used identically across tasks. Gate name `contracts-drift`, module key `contracts_drift`, output prefix `contracts-gate:`, dir `docs/process/contracts/` consistent throughout. Test helper `_contract(...)` signature stable across Tasks 1–5.
