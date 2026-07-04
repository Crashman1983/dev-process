# SP18 Plan — Typed Decision Records + integrity gate

Design: `docs/design/2026-07-04-sp18-decision-records.md`. Tier 3 (changes a
mandatory rule, adds a core gate concept, cross-cutting to how decisions are
recorded). Route: design → plan → execute → independent review → merge → tag.

## Anchor Delta

Rule 4 in `mandatory-rules.md` gains the decision-record + patch-count
principle. New "core gate" concept in the gate runner. No kernel change.

## Steps (atomic commits)

### Commit 1 — generalize ADR → typed Decision Record (docs, core)
- `adr/README.md`: reframe title/intro to "Decision Records — architectural,
  product, or process"; keep filename + `ADR-NNNN` token; keep the
  "must be in the index" line.
- `adr/template.md`: add `## Type` (`architecture | product | process`) after
  Status; add Intent-atomicity sentence ("one value per record; a decision that
  cannot take a single Intent is more than one decision — split it").
- `adr/adr-0001-*.md`: add `## Type\n\nprocess` (recording decisions is a
  process decision) so the seed models the field and stays gate-clean.

### Commit 2 — core integrity gate (`check_decisions.py`) + runner wiring + tests
- New `template/scripts/process/check_decisions.py` (no `{% if %}` wrapper —
  always rendered). Hard: index-listing, enum validity, Status×Intent
  coherence, non-UTF-8. Soft: unfilled menu, missing Type, change-planned
  without a linked follow-up. Prints `file:line`; exit 1 only on hard.
- `gate_runner.py.jinja`: allow `None` module key = core/always-on; add
  `"decision-records": (None, [...check_decisions.py...])`; update `active`
  filter to `key is None or mods.get(key)`.
- Tests:
  - `tests/test_decisions.py` (new): clean seed passes; unlisted file → hard;
    bad enum → hard; `Superseded`+`keep` → hard; `Superseded`+`change-planned`
    → hard; unfilled menu → soft (exit 0 + note); missing Type → soft;
    change-planned without link → soft; non-UTF-8 → hard.
  - `tests/test_manifest_ci.py`: core gate `decision-records` always listed
    even with all modules off; still runs on a clean tree.
  - `tests/conftest.py`: no new module key needed (core gate is keyless); keep
    dict as-is.

### Commit 3 — anchoring (docs, core)
- `mandatory-rules.md` Rule 4: append decision-record + patch-count principle.
- `start-here.md` definition-of-ready: read relevant Decision Records before
  planning; new significant decision → record first.
- `tests/test_core_docs.py`: assert Rule 4 names decision record + the
  increment-vs-rewrite call; assert start-here names reading decision records
  at plan time.

### Commit 4 — version + docs
- `pyproject.toml` 1.5.2 → 1.6.0 (new core gate = minor, additive capability).
- `docs/SBOM.md` component version; `README.md` status blockquote + roadmap row
  SP18; module/gate list mentions the core decision-records gate.

## Verification
- Full suite green + ruff clean before each commit.
- Render a demo project; run `gate_runner.py` and confirm `decision-records`
  runs with all modules off; confirm seed tree is gate-clean.
- Build a diff bundle; independent adversarial review (fresh agent) over it —
  focus: core-gate wiring correctness, no false-green in the coherence gate,
  parser robustness (headings/menus), one-owner split vs `check_arch_docs.py`,
  neutrality, version correctness.
- Fix findings, draft PR, ff-merge, dispatch release-tag v1.6.0.

## Feature Registry Trace
Template self-change; template tests are acceptance. New: `test_decisions.py`,
extended `test_manifest_ci.py` + `test_core_docs.py`.
