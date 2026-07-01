# SP4-② contract-first — implementation plan

> Executes `docs/design/2026-07-01-sp4-contract-first-design.md`. TDD, atomic
> conventional commits with the session trailers. Branch `design/sp4-contract-first`
> (design already committed). Mirror the sibling modules exactly.

## Global Constraints

- Neutral: no Kenni terms in any shipped (`template/…`) file. Neutrality list:
  `Kenni KenniNext Seb Signal SvelteKit user_id=1 surface:ios`.
- Honest ceiling: structure + spec-committed + symbol-presence are HARD (exit 1);
  everything external/unverifiable is a soft note (exit 0), never faked.
- Rule 5: `contract_first` does not import or read any other module's artifacts
  (no inventory read). Gate file ships WITH `.jinja`; Python stdlib only.
- Real verification renders with `vcs_ref="HEAD"` (files committed first).
- Commit trailers on every commit:
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>` /
  `Claude-Session: https://claude.ai/code/session_01MS9nrQC9f9WGhipvJ9NFpk`.

## Files

- Create: `template/scripts/process/{% if modules.contract_first %}check_capability_contracts.py{% endif %}.jinja`
- Create: `template/docs/process/capability-contracts/capability.example.json` (inert seed, ALWAYS shipped so the dir exists; gate skips `.example.json`)
- Create: `template/docs/process/{% if modules.contract_first %}modules{% endif %}/contract-first.md`
- Modify: `copier.yml` (modules.default += `contract_first: false`)
- Modify: `template/scripts/process/gate_runner.py.jinja` (GATES += contract-first)
- Modify: `tests/conftest.py` (modules-defaults dict += `"contract_first": False`)
- Modify: `README.md` (catalog + roadmap + status/tag v0.7.0)
- Create: `tests/test_contract_first.py`

## Task 1: the gate script + wiring

**Gate** — `check_capability_contracts.py` (mirror `check_contracts.py`'s
hardening: escape-guard, UTF-8/JSON arms, hard/soft split):

```python
#!/usr/bin/env python3
"""contract-first gate: a declared cross-surface capability must reference
interface symbols that already exist in the committed shared spec — the
"declared first" of Rule 3. Structure, an in-repo committed spec, and
symbol presence are hard-guaranteed (CI exit 1). Whether the named surfaces
actually consume the capability is not machine-checkable across arbitrary
codebases and is advisory only, never faked as verified. Python stdlib only."""
from __future__ import annotations

import json
import sys
from pathlib import Path

CONTRACTS_DIR = "docs/process/capability-contracts"


def _contract_files(root: Path) -> list[Path]:
    d = root / CONTRACTS_DIR
    if not d.is_dir():
        return []
    return sorted(p for p in d.glob("*.json") if not p.name.endswith(".example.json"))


def _spec_path(root: Path, spec: str) -> Path | None:
    resolved = (root / spec).resolve()
    if root.resolve() not in resolved.parents:
        return None
    return resolved


def _nonempty_str_list(val) -> bool:
    return (
        isinstance(val, list)
        and len(val) > 0
        and all(isinstance(x, str) and x.strip() for x in val)
    )


def _check(root: Path, path: Path) -> tuple[list[str], list[str]]:
    hard: list[str] = []
    soft: list[str] = []
    rel = path.relative_to(root)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"{rel}: invalid JSON: {exc}"], []
    except UnicodeDecodeError as exc:
        return [f"{rel}: not valid UTF-8: {exc}"], []
    if not isinstance(data, dict):
        return [f"{rel}: contract must be a JSON object, got {type(data).__name__}"], []

    cap = data.get("capability")
    if not isinstance(cap, str) or not cap.strip():
        hard.append(f"{rel}: 'capability' must be a non-empty string")
    spec = data.get("spec")
    if not isinstance(spec, str) or not spec.strip():
        hard.append(f"{rel}: 'spec' must be a non-empty string")
    if not _nonempty_str_list(data.get("surfaces")):
        hard.append(f"{rel}: 'surfaces' must be a non-empty list of non-empty strings")
    if not _nonempty_str_list(data.get("symbols")):
        hard.append(f"{rel}: 'symbols' must be a non-empty list of non-empty strings")
    if hard:
        return hard, soft

    if cap.strip() != path.stem:
        hard.append(f"{rel}: 'capability' {cap.strip()!r} must equal the filename stem {path.stem!r}")

    apath = _spec_path(root, spec.strip())
    if apath is None:
        hard.append(f"{rel}: spec path {spec.strip()!r} escapes the repo root")
        return hard, soft
    if not apath.is_file():
        hard.append(f"{rel}: spec not committed / does not exist: {spec.strip()}")
        return hard, soft

    try:
        spec_text = apath.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        spec_text = apath.read_bytes().decode("utf-8", "replace")
    for sym in data["symbols"]:
        if sym not in spec_text:
            hard.append(
                f"{rel}: symbol {sym!r} not found in spec {spec.strip()} — "
                "declare the interface in the spec before building the surface (Rule 3)"
            )

    soft.append(
        f"{rel}: surface consumption of {cap.strip()!r} by {data['surfaces']} "
        "not machine-verified"
    )
    return hard, soft


def check(root: Path) -> tuple[list[str], list[str]]:
    files = _contract_files(root)
    if not files:
        return [], ["no capability contracts yet (dir empty or absent)"]
    hard: list[str] = []
    soft: list[str] = []
    for path in files:
        h, s = _check(root, path)
        hard += h
        soft += s
    return hard, soft


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    hard, soft = check(root)
    for note in soft:
        print(f"contract-first: note: {note}")
    if hard:
        print("contract-first: FAILED:")
        for h in hard:
            print(f"  - {h}")
        return 1
    print("contract-first: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

**Seed** `capability.example.json` (inert — `.example.json` is skipped):

```json
{
  "capability": "example-capability",
  "surfaces": ["web", "mobile"],
  "spec": "docs/api/openapi.json",
  "symbols": ["ExampleDTO"],
  "notes": "Illustrative only — the gate ignores *.example.json. Copy to <capability>.json (filename stem == capability) and point spec/symbols at your committed shared interface."
}
```

**Wiring:** add to `copier.yml` modules.default (`contract_first: false`),
`gate_runner.py.jinja` GATES (`"contract-first": ("contract_first", [sys.executable, "scripts/process/check_capability_contracts.py", "."])`),
`tests/conftest.py` modules dict (`"contract_first": False`).

- [ ] Write `tests/test_contract_first.py` (Task-2 tests) → run red → implement gate + wiring → green → commit `feat: add contract-first capability-contract gate`.

## Task 2: tests

`tests/test_contract_first.py` — helpers mirror `test_git_hooks.py`/sibling tests.
Required tests:
- `test_module_on_ships_gate_and_doc` / `test_module_off_ships_neither`
- `test_answers_records_contract_first`
- `test_valid_contract_passes` (spec file contains the symbols → exit 0)
- `test_missing_symbol_hard_fails` (symbol absent from spec → exit 1, message names the symbol)
- `test_spec_not_committed_hard_fails`
- `test_spec_escape_hard_fails` (`spec: "../evil"` → exit 1 "escapes")
- `test_capability_stem_mismatch_hard_fails`
- `test_bad_types_hard_fail` (surfaces not a list / symbols empty / non-object / non-UTF-8 / invalid JSON)
- `test_example_seed_ignored` (only `*.example.json` present → "no capability contracts yet", exit 0)
- `test_empty_registry_soft` (dir absent → exit 0 note)
- `test_gate_runner_lists_contract_first` (with module on, `--list` includes `contract-first`)
- `test_neutral_no_kenni_terms` (shipped files carry no neutrality-list term)
- `test_docdrift_green_with_module_doc` (doc_drift_gate + contract_first → check_doc_drift exit 0)

Helper: render a repo dir, write a spec file (e.g. `docs/api/openapi.json` with
the symbol text), write a `<cap>.json`, run
`[sys.executable, out/"scripts/process/check_capability_contracts.py", out]`.

## Task 3: module doc + README

- `template/docs/process/{% if modules.contract_first %}modules{% endif %}/contract-first.md`:
  what it is, the artifact shape, HARD vs BEST-EFFORT, the substring-floor caveat,
  Rule-5 note (artifact drift → contracts_drift; no inventory import). Only real
  slash-path backtick ref is `scripts/process/check_capability_contracts.py`.
- README: append `contract-first` to the module catalog paragraph + roadmap SP4
  row (git-hooks + contract-first), status/tag → v0.7.0.
- Commit `docs: add contract-first module doc and README catalog entry`.

## Post-plan: merge gate

Full suite + ruff green; real `vcs_ref=HEAD` render on/off; then independent
merge-gate review (pure-Python pattern-follow → lighter than the shell git-hooks
review, but still adversarial on the symbol-presence logic + hardening arms).
Fix Critical/Important, re-verify. Then bump pyproject to 0.7.0, ff-merge, tag
v0.7.0, delete branch, update memory.
