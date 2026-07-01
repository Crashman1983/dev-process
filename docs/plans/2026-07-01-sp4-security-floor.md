# SP4-④ security-floor — implementation plan

> Executes `docs/design/2026-07-01-sp4-security-floor-design.md`. TDD, atomic
> conventional commits with the session trailers. Branch `design/sp4-security-floor`
> (design committed). Mirror the sibling modules; apply the Finding-D seed
> discipline (seed ships only when the module is on).

## Global Constraints

- Neutral: no Kenni terms in any shipped `template/…` file. List:
  `Kenni KenniNext Seb Signal SvelteKit user_id=1 surface:ios`.
- Honest ceiling: a present-but-broken config and any pattern match are HARD
  (exit 1); absent config / git-unavailable / binary file / `SKIP_SECURITY_FLOOR=1`
  are soft notes (exit 0), never faked.
- Do NOT cite a mandatory-rule number in the module doc (the neutral rule set has
  no security rule — lesson from the parity review). If the doc references "one
  owner", it is neutral **Rule 4**.
- Gate ships WITH `.jinja`; Python stdlib only (no yaml — this gate reads JSON).
- Real verification renders with `vcs_ref="HEAD"` (commit first).
- Commit trailers on EVERY commit:
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>` /
  `Claude-Session: https://claude.ai/code/session_01MS9nrQC9f9WGhipvJ9NFpk`.

## Files

- Create: `template/scripts/process/{% if modules.security_floor %}check_security_floor.py{% endif %}.jinja`
- Create: `template/docs/process/{% if modules.security_floor %}security-floor.example.json{% endif %}`
- Create: `template/docs/process/{% if modules.security_floor %}modules{% endif %}/security-floor.md`
- Modify: `copier.yml` (modules.default += `security_floor: false`)
- Modify: `template/scripts/process/gate_runner.py.jinja` (GATES += security-floor)
- Modify: `tests/conftest.py` (modules dict += `"security_floor": False`)
- Modify: `README.md` (catalog + roadmap + status/tag v0.9.0)
- Create: `tests/test_security_floor.py`

## Task 1: gate + wiring

**Gate** — `check_security_floor.py` (use verbatim):

```python
#!/usr/bin/env python3
"""security-floor gate: the grep-able subset of a project's security invariants,
enforced as a blocking gate. The project declares forbidden regex patterns in
docs/process/security-floor.json; the gate scans git-tracked files and fails CI
(exit 1) on a match. A present-but-broken config also fails. Enumeration needs
git; if git is unavailable the scan is skipped with an advisory note, never faked
as a pass. Bypass: SKIP_SECURITY_FLOOR=1. Python stdlib only."""
from __future__ import annotations

import fnmatch
import json
import os
import re
import subprocess
import sys
from pathlib import Path

CONFIG = "docs/process/security-floor.json"
# never scan the policy file itself (it holds the patterns) or the gate script.
SELF_EXCLUDE = {CONFIG, "scripts/process/check_security_floor.py"}


def _tracked_files(root: Path) -> list[str] | None:
    try:
        r = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z"],
            capture_output=True, timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0:
        return None
    return [p for p in r.stdout.decode("utf-8", "replace").split("\0") if p]


def _matches_any(rel: str, globs: list[str]) -> bool:
    base = rel.rsplit("/", 1)[-1]
    return any(fnmatch.fnmatch(rel, g) or fnmatch.fnmatch(base, g) for g in globs)


def _load_config(root: Path) -> tuple[dict | None, list[str]]:
    p = root / CONFIG
    if not p.is_file():
        return None, []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return None, [f"{CONFIG}: invalid JSON: {exc}"]
    except UnicodeDecodeError as exc:
        return None, [f"{CONFIG}: not valid UTF-8: {exc}"]
    if not isinstance(data, dict):
        return None, [f"{CONFIG}: must be a JSON object"]
    return data, []


def _validate(cfg: dict) -> tuple[list[dict], list[str], list[str]]:
    hard: list[str] = []
    rules_raw = cfg.get("rules")
    if not isinstance(rules_raw, list):
        return [], [], [f"{CONFIG}: 'rules' must be a list"]
    exclude = cfg.get("exclude") if isinstance(cfg.get("exclude"), list) else []
    exclude = [g for g in exclude if isinstance(g, str)]
    compiled: list[dict] = []
    for i, rule in enumerate(rules_raw):
        if not isinstance(rule, dict):
            hard.append(f"{CONFIG}: rule #{i} must be an object")
            continue
        rid = rule.get("id")
        pattern = rule.get("pattern")
        message = rule.get("message")
        applies = rule.get("applies_to")
        if not isinstance(rid, str) or not rid.strip():
            hard.append(f"{CONFIG}: rule #{i} 'id' must be a non-empty string")
        if not isinstance(message, str) or not message.strip():
            hard.append(f"{CONFIG}: rule {rid!r} 'message' must be a non-empty string")
        if applies is not None and not (isinstance(applies, list) and all(isinstance(g, str) for g in applies)):
            hard.append(f"{CONFIG}: rule {rid!r} 'applies_to' must be a list of glob strings")
            applies = None
        if not isinstance(pattern, str) or not pattern:
            hard.append(f"{CONFIG}: rule {rid!r} 'pattern' must be a non-empty string")
            continue
        try:
            regex = re.compile(pattern)
        except re.error as exc:
            hard.append(f"{CONFIG}: rule {rid!r} pattern is not a valid regex: {exc}")
            continue
        compiled.append({"id": rid, "regex": regex, "applies_to": applies, "message": message})
    return compiled, exclude, hard


def check(root: Path) -> tuple[list[str], list[str]]:
    cfg, errs = _load_config(root)
    if errs:
        return errs, []
    if cfg is None:
        return [], [f"no security-floor config yet ({CONFIG} absent)"]
    rules, exclude, hard = _validate(cfg)
    if hard:
        return hard, []
    if not rules:
        return [], ["security-floor config has no rules"]
    files = _tracked_files(root)
    if files is None:
        return [], ["could not list tracked files (git unavailable); scan skipped"]

    findings: list[str] = []
    for rel in files:
        if rel in SELF_EXCLUDE:
            continue
        if exclude and _matches_any(rel, exclude):
            continue
        applicable = [r for r in rules if r["applies_to"] is None or _matches_any(rel, r["applies_to"])]
        if not applicable:
            continue
        try:
            text = (root / rel).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # binary / unreadable — cannot scan
        for lineno, line in enumerate(text.splitlines(), 1):
            for r in applicable:
                if r["regex"].search(line):
                    findings.append(f"{rel}:{lineno}: {r['message']} [{r['id']}]")
    return findings, []


def main() -> int:
    if os.environ.get("SKIP_SECURITY_FLOOR") == "1":
        print("security-floor: skipped (SKIP_SECURITY_FLOOR=1)")
        return 0
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    hard, soft = check(root)
    for note in soft:
        print(f"security-floor: note: {note}")
    if hard:
        print("security-floor: FAILED:")
        for h in hard:
            print(f"  - {h}")
        print("  → fix, or bypass with SKIP_SECURITY_FLOOR=1 (and say why in the commit).")
        return 1
    print("security-floor: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

**Seed** `security-floor.example.json` (illustrative — a project renames it to
`security-floor.json` to activate; the gate reads only `security-floor.json`):

```json
{
  "rules": [
    { "id": "no-shell-true", "pattern": "shell\\s*=\\s*True",
      "applies_to": ["*.py"], "message": "use a subprocess argv list, not shell=True" },
    { "id": "no-committed-private-key", "pattern": "-----BEGIN [A-Z ]*PRIVATE KEY-----",
      "message": "private key material must not be committed" }
  ],
  "exclude": ["*test_*", "tests/*"]
}
```

**Wiring:** `copier.yml` modules.default (`security_floor: false`),
`gate_runner.py.jinja` GATES (`"security-floor": ("security_floor", [sys.executable, "scripts/process/check_security_floor.py", "."])`),
`tests/conftest.py` modules dict (`"security_floor": False`).

- [ ] Write `tests/test_security_floor.py` (Task 2) → red → implement → green →
  commit `feat: add security-floor pattern gate`.

## Task 2: tests — `tests/test_security_floor.py`

Helpers: `_render` (default `security_floor=True`); `_run(out)` runs the gate with
`out` as root; a `_git_init(out)` that `git init`s + configures identity (mirror
`tests/test_git_hooks.py::_init_repo` — the scan needs tracked files, so
`git add -A && git commit`). Write the config at `docs/process/security-floor.json`.

Required tests:
- `test_module_on_ships_gate_doc_seed` / `test_module_off_ships_nothing` (incl. no seed)
- `test_answers_records_security_floor`
- `test_no_config_is_noop` (no config file → note "no security-floor config yet", exit 0)
- `test_git_unavailable_is_soft` (config with a rule, but the render dir is NOT a git repo → note "could not list tracked files", exit 0)
- `test_pattern_match_hard_fails` (git-init; config `shell=True` rule on `*.py`; a tracked `x.py` containing `subprocess.run(cmd, shell=True)` → exit 1, output has `x.py:<line>` + message)
- `test_clean_tree_passes` (git-init; same rule; a tracked `x.py` with no match → exit 0)
- `test_exclude_glob_skips_file` (the bad file matches an `exclude` glob → exit 0)
- `test_applies_to_scopes` (rule applies_to `*.py`; the pattern text sits only in a `*.md` file → exit 0)
- `test_self_exclude` (a rule whose pattern also matches the config file's own text does NOT flag `security-floor.json` itself)
- `test_invalid_json_config_hard_fails` / `test_config_not_object_hard_fails` / `test_rules_not_list_hard_fails` / `test_rule_missing_pattern_hard_fails` / `test_invalid_regex_hard_fails` (`pattern: "([unclosed"` → exit 1 "not a valid regex")
- `test_skip_env_bypasses` (`SKIP_SECURITY_FLOOR=1` in env → exit 0 "skipped", even with a matching file)
- `test_binary_file_skipped` (a tracked non-UTF-8 file → no crash, exit 0)
- `test_gate_runner_lists_security_floor`
- `test_neutral_no_kenni_terms`
- `test_docdrift_green_with_module_doc`

For git tests, set `env` with the venv bin on PATH is unnecessary (the gate uses
`git` + `python` only); just run `git` via subprocess with `cwd=out`.

## Task 3: module doc + README

- `template/docs/process/{% if modules.security_floor %}modules{% endif %}/security-floor.md`:
  purpose, config shape, glob semantics (fnmatch, matches rel-path OR basename,
  `*` crosses `/`), the whole-tree-scan divergence from added-only + its
  mitigations, HARD vs BEST-EFFORT, the heuristic caveat, `SKIP_SECURITY_FLOOR=1`
  bypass, the git-unavailable note. Do NOT cite a security rule number (there is
  none); if "one owner" is mentioned it is Rule 4. Only real slash-path backtick
  refs: `scripts/process/check_security_floor.py` and `docs/process/security-floor.json`.
- README: append `security-floor` to catalog paragraph + SP4 roadmap row; status/tag → v0.9.0.
- Commit `docs: add security-floor module doc and README catalog entry`.

## Post-plan: merge gate

Full suite + ruff green; real `vcs_ref=HEAD` render on/off (module off ships
nothing) + a live git-repo match→exit-1 check. Independent merge-gate review —
this gate shells out (`git ls-files`), compiles project regexes, and scans files,
so it gets the HEAVIER review tier (subprocess/regex/scan failure surface). Fix
Critical/Important, re-verify. Then bump pyproject to 0.9.0, ff-merge, tag
v0.9.0, delete branch, update memory.
