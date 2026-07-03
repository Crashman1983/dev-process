# Plan: anchor guidance (SP13)

Design: `docs/design/2026-07-03-sp13-anchor-guidance-design.md`.

## Task 1 — start-here.md section

- Add "## Anchors: what goes where, and how to scale them" to
  `template/docs/process/start-here.md`: the drift discriminator (anchor points,
  never copies; "does it drift on a refactor?") + the per-subtree scaling note
  (harness-neutral phrasing, Claude Code nested anchor vs AGENTS.md per-dir/
  pointer). No project-specific terms.
- Test: extend `tests/test_core_docs.py` to assert the section is present and
  names the discriminator; existing no-jinja / no-project-term checks still pass.

## Task 2 — adapter pointer

- `template/CLAUDE.md.jinja`: extend the existing "thin adapter" sentence in the
  `## Start` section (outside the kernel block) with a pointer to the new
  section. Kernel block untouched → `test_kernel_identical_across_adapters`
  stays green.
- Test: `test_adapters` suite stays green (kernel identity + start-here pointer).

## Task 3 — release

- `pyproject.toml` → 1.4.4; `docs/SBOM.md` project row; README status + roadmap
  row SP13.
- Independent adversarial review of the diff (Tier-4 rule, dogfood); attest
  single-family honestly; merge + tag `v1.4.4`.
