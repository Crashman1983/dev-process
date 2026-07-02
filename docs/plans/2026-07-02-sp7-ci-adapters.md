# Plan: ci-adapters (SP7) + install fallbacks

Design: `docs/design/2026-07-02-sp7-ci-adapters-design.md`. TDD per task.

## Task 1 — `ci` question + GitHub workflow behind `ci.github`

- `copier.yml`: add `ci` yaml question, default `{github: true, gitlab: false}`.
- Move `template/.github/workflows/process-gates.yml.jinja` to
  `template/.github/{% if ci.github %}workflows{% endif %}/process-gates.yml.jinja`.
- `tests/conftest.py`: add explicit `ci` defaults to `_copy`.
- Tests: default render still has `.github/workflows/process-gates.yml`
  (existing `test_workflow_rendered` keeps passing); `ci.github: false`
  renders no `workflows/` directory anywhere.

## Task 2 — GitLab adapter files

- `template/{% if ci.gitlab %}.gitlab-ci.yml{% endif %}`: `include: local:` shim.
- `template/.gitlab/{% if ci.gitlab %}ci{% endif %}/process-gates.gitlab-ci.yml`:
  job mirroring the GitHub workflow (`pip install pyyaml`,
  `python scripts/process/gate_runner.py`).
- Tests: gitlab off (default) → no `.gitlab-ci.yml`, no `.gitlab/` anywhere;
  gitlab on → both files, shim includes the job file path, job calls the
  gate_runner; both CI providers can be on at once.

## Task 3 — docs: degradation + BOOTSTRAP ci answer

- README: enforcement paragraph names both transports and the no-CI
  degradation (git-hooks only); usage section mentions the `ci` question;
  roadmap row SP7.
- BOOTSTRAP: `ci` in the prompt list, `--data 'ci={…}'` in the headless
  recipe, gitlab-brownfield note (`--skip '.gitlab-ci.yml'` + include merge).
- SYSTEM-REQUIREMENTS: CI section covers both providers.
- Tests: BOOTSTRAP documents `--data 'ci={` and the degradation note exists.

## Task 4 — install fallback ladder in BOOTSTRAP

- BOOTSTRAP "Installation": fallback ladder pipx → venv/pip → git clone with
  `--vcs-ref` note, each command verified once against this repo.
- SYSTEM-REQUIREMENTS: `uv` row notes the fallbacks.
- Tests: BOOTSTRAP names `pipx run copier`, `pip install copier`, and the
  clone fallback.

## Task 5 — version bump

- `pyproject.toml` → 1.1.0; README status line mentions SP7.
