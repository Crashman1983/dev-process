# SP19 Plan — Enforce review independence (gated attestation)

Design: `docs/design/2026-07-04-sp19-review-enforcement.md`. Tier 4 (the
crown-jewel quality mechanism; new core gate + new conventions; cross-stack in
spirit). Route: design → plan → execute → independent adversarial review →
merge → tag. Own attestation will honestly carry `single-family` (one model
family available here).

tier: 4

## Anchor Delta

`verification-independence.md` gains "## Enforcement"; rule 7 references the
gated attestation; `journal-state-plans.md` documents `tier:` + `REVIEW`.
Second core gate. No kernel change.

## Steps (atomic commits)

### Commit 1 — REVIEW grammar + `check_review.py` core gate + wiring + tests
- New `template/scripts/process/check_review.py` (no `{% if %}` wrapper — core).
  - Parse `REVIEW ` journal lines (recursive glob; skip ```-fenced regions).
  - HARD: grammar / enum (`verdict`∈{pass,block}, `independence`⊆ set) /
    numeric `tier`,`round`.
  - HARD arithmetic on `verdict=pass`: tier≥2 needs `non-implementing`; tier≥2
    needs `bundle`; tier=4 needs `cross-model` or `single-family`.
  - HARD presence: archived plan with `tier: N` (N≥3) lacking a clearing
    `verdict=pass` REVIEW (work matches slug/issue, tier≥N) AND no
    `review-waived: <reason>` → fail. file:line.
  - SOFT: zero REVIEW lines (pre-adoption); plan without `tier:`; in-flight
    (non-archived) tier≥3 plan without review yet; non-UTF-8 journal is HARD.
- `gate_runner.py.jinja`: register `"review": (None, [...check_review.py...])`
  as the second core gate.
- `tests/test_review.py`: grammar hard; each arithmetic rule hard + its
  passing counterpart; presence hard; waiver clears; no-tier soft; pre-adoption
  soft; fenced REVIEW ignored; archived-plan matching.
- `tests/test_manifest_ci.py`: `review` core gate always listed/runs.

### Commit 2 — conventions + anchoring (docs)
- `journal-state-plans.md`: document the `tier: N` plan field and the `REVIEW`
  record (grammar table + where it is written).
- `verification-independence.md`: replace the closing "not a machine-checked
  gate" paragraph with "## Enforcement" (arithmetic + presence gated; identity
  attested).
- `mandatory-rules.md` rule 7: append the gated-attestation clause.
- `tests/test_core_docs.py`: assert Enforcement section names the gate; rule 7
  names the attestation; journal-state-plans names `tier:` and `REVIEW`.

### Commit 3 — release
- `pyproject.toml`/`uv.lock`/`docs/SBOM.md` 1.6.0 → 1.7.0 (new core gate =
  minor). README status blockquote + roadmap row SP19.

## Verification
- Full suite green + ruff clean before each commit.
- Render a demo; run `gate_runner.py` with all modules off → `review` core gate
  runs; seed tree clean; craft an archived Tier-3 plan without a REVIEW → hard;
  add the REVIEW → green; add a self-review pass at tier=3 → hard.
- Diff bundle; independent adversarial review (fresh agent) — focus: no
  false-green in arithmetic (can a pass wrongly clear a tier?), presence
  false-red risk during development, plan/work matching robustness, fenced-skip
  correctness, one-owner vs telemetry GRADE, neutrality, version.
- Fix findings, ff-merge, release-tag v1.7.0.

## Feature Registry Trace
Template self-change; template tests are acceptance. New `test_review.py`;
extended `test_manifest_ci.py`, `test_core_docs.py`.
