# Plan: audit-fixes (SP9)

Design: `docs/design/2026-07-02-sp9-audit-fixes-design.md`. TDD per task.

## Task 1 — gate_runner: load-bearing manifest + friendly PyYAML error

- Walk up from cwd to find `.copier-answers.yml` (repo root); missing,
  unparseable, or `modules` not a mapping → diagnostic + exit 1.
- Wrap the `yaml` import: ImportError → one-line install hint, exit 1.
- Tests: subdir run passes (finds root); deleted manifest → red; manifest
  without `modules` → red; all-modules-false manifest → green.

## Task 2 — gate robustness

- check_architecture: unclosed ```arch fence → hard fail; `str()` casts on
  YAML-sourced paths.
- UTF-8/YAML guards: check_doc_drift, check_feature_registry, check_issues
  (`_default_repo`), check_parity (non-mapping answers).
- check_contracts: verify commands run with `cwd=root`.
- check_security_floor: note when 0 files scanned.
- Tests per fix (plant the malformed input, assert clean red or note).

## Task 3 — hooks

- pre-commit: `git symbolic-ref --short HEAD` (unborn-branch safe).
- installer: refuse under a configured `core.hooksPath` with guidance.
- pre-push + git-hooks module doc: state the working-tree limitation, CI is
  authority.
- Tests: unborn-main commit blocked; hooksPath refusal.

## Task 4 — doc-drift: document-relative links

- Refs starting with `./`/`../` resolve against the containing doc; bare
  paths stay repo-root-relative.
- Tests: valid `../workflow.md` link passes; dead relative link fails.

## Task 5 — drift fixes (docs + template)

- README: nine rules, drop stray "und". SBOM: current versions.
- SYSTEM-REQUIREMENTS: github-issues needs PyYAML; hook/venv PATH note.
- Tier-0 wording across kernel (3 adapters, byte-identical), risk-tiers,
  workflow. start-here: condition ARCHITECTURE.md refs. Module docs:
  `python` instead of `uv run`. ADR-0001 file shipped. Story example title.
  BOOTSTRAP: conditional questions, module disable, PyYAML note.
  github-issues doc: feature-registry dependency. copier.yml:
  `_min_copier_version`. GitHub workflow: no double-run.
- Tests: adjusted/added string anchors where cheap.

## Task 6 — version bump

- `pyproject.toml` → 1.3.0; README status line; SBOM row matches.
