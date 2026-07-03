# Plan: verification-independence (SP12)

Design: `docs/design/2026-07-02-sp12-verification-independence-design.md`.

## Task 1 — core methodology doc

- Add `template/docs/process/verification-independence.md`: production-warm /
  verification-independent split, the tier ladder (0–1 self, 2–3 fresh
  bundle-only single-family, 4 cross-family + adversarial refute), attestation,
  the efficiency argument. Methodology only — no harness mechanics, no
  project-specific terms.
- Tests: add it to `tests/test_core_docs.py` CORE list (present, no jinja leak,
  no project-specific terms); it renders unconditionally (core, not a module).

## Task 2 — wire into the existing methodology

- `risk-tiers.md`: a compact paragraph after the floor note summarizing the
  independence ladder and pointing to the new doc.
- `workflow.md.jinja`: Execute names that it runs in the warm production
  context; Review names that independence scales with the tier
  (`verification-independence.md`).
- `mandatory-rules.md`: rule 7 points to the new doc for how the gate earns
  its trust (no new rule — count stays nine).
- Tests: existing core-docs + workflow tests stay green; doc-drift green (any
  path ref resolves; keep bare filenames in prose).

## Task 3 — release

- `pyproject.toml` → 1.4.3; `docs/SBOM.md` project row; README status line +
  roadmap row SP12.
- Adversarial self-review of the diff (dogfood the Tier-4 rule this slice adds)
  before merge; then merge + tag `v1.4.3`.
