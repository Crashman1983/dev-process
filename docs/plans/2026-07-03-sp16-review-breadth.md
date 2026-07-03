# Plan: review breadth (SP16)

Design: `docs/design/2026-07-03-sp16-review-breadth-design.md`.

## Task 1 — two new dimensions + framing

- `template/docs/process/review-checklist.md`: add "## Performance & efficiency"
  (after Correctness) and "## Observability & operability" (after Security);
  broaden the security intro with non-web untrusted-input examples. Stack-neutral
  questions only.
- Test: extend `tests/test_core_docs.py` to assert both new sections and a
  load-bearing token each (e.g. "N+1", "roll back").

## Task 2 — release

- `pyproject.toml` → 1.5.1; `docs/SBOM.md`; README status.
- Independent adversarial review; attest single-family; merge + tag `v1.5.1`.
