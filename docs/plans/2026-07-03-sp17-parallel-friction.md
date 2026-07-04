# Plan: parallel friction (SP17)

Design: `docs/design/2026-07-03-sp17-parallel-friction-design.md`.

## Task 1 — shard the journal + parallel-efforts guidance

- `journal-state-plans.md`: journal convention becomes
  `.process-work/journal/<branch-slug>/YYYY-MM-DD.md` for parallel work
  (top-level still valid solo); add a "## Parallel efforts" section (sharded
  execution memory + serialized ff-only integration trade-off + one-owner).
- `commits.md`: the isolation invariant points at the new section.
- Test: `tests/test_core_docs.py` asserts journal-state-plans names the
  per-branch journal shard and the "Parallel efforts" section.

## Task 2 — telemetry compatibility

- `telemetry.md` module doc: update the journal path example to the sharded
  form, reference `journal-state-plans.md` as the convention owner.
- Test: `tests/test_telemetry.py` proves a GRADE line in a sharded journal
  (`.process-work/journal/<branch>/YYYY-MM-DD.md`) is read by the gate and the
  cockpit (recursive glob), so sharding does not break measurement.

## Task 3 — release

- `pyproject.toml` → 1.5.2; `docs/SBOM.md`; README status.
- Independent adversarial review; attest single-family; merge + tag `v1.5.2`.
