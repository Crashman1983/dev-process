# Plan: telemetry (SP10)

Design: `docs/design/2026-07-02-sp10-telemetry-design.md`. TDD per task.

## Task 1 — module wiring

- `copier.yml`: add `telemetry: false` to the `modules` default map.
- `gate_runner.py.jinja` `GATES`: add
  `"telemetry": ("telemetry", [sys.executable, "scripts/process/check_telemetry.py", "."])`.
- `tests/conftest.py`: add `telemetry: False` to the full modules dict.
- Tests: module off ships nothing (script, cockpit, doc, calibration dir all
  absent); module on ships all four; `gate_runner.py --list` includes
  `telemetry`; `.copier-answers.yml` records `telemetry: true`.

## Task 2 — gate: `check_telemetry.py`

- `template/scripts/process/{% if modules.telemetry %}check_telemetry.py{% endif %}`
  (no render-time data → no `.jinja`). Owns the GRADE grammar: regex, verdict/
  action/source enums, `parse_grade_lines()`.
- Scans `.process-work/journal/**/*.md`: a line whose first token is `GRADE`
  but does not match the grammar, or whose verdict/action/source is outside
  the enums, is a hard failure with `file:line`. Non-UTF-8 journal → hard
  failure. No journals / zero GRADE lines → soft note, exit 0.
- Validates calibration cases under `docs/process/telemetry/calibration/`
  (skipping `*.example.json`): invalid JSON / non-UTF-8 / non-object /
  missing `id` or `ground_truth` / verdict values outside the enum → hard.
- Output convention: `telemetry: OK` / `telemetry: note: ...` /
  `telemetry: FAILED:` + bullets.
- Tests: valid lines pass; malformed GRADE line fails with file:line; bad
  verdict/action/source fail; non-UTF-8 fails; prose containing the word
  GRADE mid-sentence is ignored; empty repo soft-notes; broken calibration
  case fails; `.example.json` ignored.

## Task 3 — cockpit: `process_kpis.py`

- `template/scripts/process/{% if modules.telemetry %}process_kpis.py{% endif %}`.
  Imports parser/enums from sibling `check_telemetry`. Read-only; never
  blocks; not registered in the gate_runner.
- Subcommands: `effectiveness`, `convergence`, `suite`, `tempo`, `cost`,
  `cfr`, `friction`, `report` (default). Port from Kenni with English output,
  `work=`/`criterion=` keys, confidence()/action() framing, thresholds as
  documented constants; tempo degrades without `gh`; cfr detects the default
  branch (`main`/`master`, `--branch` override) and uses a broad code-extension
  set; cost takes optional `--transcripts DIR`; convergence excludes first-try
  episodes from the denominator; suite counts only graded cases.
- Tests (subprocess, seeded journals/cases under a rendered repo):
  effectiveness buckets catch/false-alarm/surfaced/idle correctly and prints a
  low-confidence "collect more" action under the floor; convergence classifies
  converged/thrash/unresolved/first_try; suite reports thresholds and flags a
  danger-direction false-pass; cfr flags a feat+fix code overlap inside the
  window and ignores doc-only overlap; tempo skips gracefully without gh
  (exit 0); report runs end-to-end exit 0.

## Task 4 — docs: module doc, workflow anchor, seed

- `template/docs/process/{% if modules.telemetry %}modules{% endif %}/telemetry.md`:
  grammar + field table, episode/verdict semantics, hard-vs-soft split of the
  gate, cockpit families with their confidence-gated actions, calibration
  practice (piggyback growth, danger-direction duty, thresholds with honesty
  labels), one-owner boundary note.
- `template/docs/process/{% if modules.telemetry %}telemetry{% endif %}/calibration/case.example.json`
  — inert seed mirroring the Kenni case format (id, source, danger_direction,
  ground_truth, grader_verdict=null, note).
- `workflow.md` → `workflow.md.jinja`: Execute and Review sections gain one
  `{% if modules.telemetry %}` sentence pointing at the module doc.
- Tests: rendered workflow.md mentions GRADE only with the module on;
  doc-drift gate green with `doc_drift_gate + telemetry` both on; neutrality
  (no Kenni terms in rendered module files); core-docs suite stays green.

## Task 5 — upstream docs

- `README.md`: module list + roadmap row SP10 + status line.
- `BOOTSTRAP.md`: add `telemetry` to both complete `--data` module dicts.
- `docs/SYSTEM-REQUIREMENTS.md`: module table row (`telemetry` — stdlib;
  optional `gh` for tempo) and PyYAML consumer note unchanged.
- `docs/SBOM.md`: version row; `gh` optional-tools row gains the tempo use.
- `template/docs/process/start-here.md`: module-choice heuristic + inert-seed
  list mention calibration cases.

## Task 6 — version bump

- `pyproject.toml` → 1.4.0; `docs/SBOM.md` project row; README status line.
