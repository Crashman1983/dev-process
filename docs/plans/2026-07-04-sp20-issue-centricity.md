# SP20 Plan — Issue-centricity (issue-before-code + claim discipline)

Design: `docs/design/2026-07-04-sp20-issue-centricity.md`. Tier 3 (module gate
behavior change + core-doc convention; opt-in, no core rule change). Route:
design → plan → execute → independent review → merge → tag. Own attestation
will carry `single-family`.

tier: 3
issue-waived: dev-process is the process template itself; its backlog is not run on GitHub Issues, so the issue-before-code rule it ships is not self-applied.

## Anchor Delta

`github-issues.md` gains issue-before-code + tightened claim discipline;
`journal-state-plans.md` documents the plan `issue:` field. No new gate, no core
rule change.

## Steps (atomic commits)

### Commit 1 — issue-before-code enforcement in `check_issues.py` + tests
- Extend `check_issues.py`:
  - Add a fenced-block stripper (a plan's `tier:`/`issue:` inside ``` is a
    quotation) — mirror the review gate.
  - New scan of active plans (`.process-work/plans/*.md`, not `archive/`, not
    `design-*.md`): for `tier: N` (N≥3), require a valid `issue:` line (reuse
    `parse_issue_ref`) or `issue-waived: <reason>`; else hard. Malformed
    `issue:` ref → hard. No `tier:` → skip (not enforced).
  - Keep the existing story checks; adjust the "inert without registry" early
    return so plan enforcement still runs.
- `tests/test_issues.py`: active tier-3 plan without issue → hard; with `#12` →
  clean; malformed plan issue → hard; `issue-waived:` clears; tier-2 plan not
  enforced; no-tier plan not enforced; fenced `tier:` ignored; archived plan
  NOT issue-checked; module-off → gate not run (manifest).

### Commit 2 — docs (module + core convention)
- `github-issues.md`: add "## Issue before code" (the gate rule + waiver);
  tighten "## Claim workflow" (claim fields + heartbeat cadence, explicitly not
  gated); fix the "inert without feature-registry" sentence.
- `journal-state-plans.md`: plan may carry `issue:`; under `github-issues`, a
  Tier 3+ plan needs it before code (or `issue-waived:`).
- `tests/test_modules.py` (or the module's doc test): assert the module doc
  names issue-before-code + waiver. If no such test exists, add a focused one.

### Commit 3 — release
- `pyproject.toml`/`uv.lock`/`docs/SBOM.md` 1.7.0 → 1.8.0 (new enforced module
  capability = minor). README status blockquote + roadmap row SP20.

## Verification
- Full suite green + ruff clean before each commit.
- Render a demo with `github_issues` on; craft an active tier-3 plan without an
  issue → gate hard; add `issue: #7` → green; move plan to `archive/` → not
  issue-checked. With module off → gate absent from `--list`.
- Diff bundle; independent adversarial review (fresh agent, single-family) —
  focus: false-red (active vs archived timing; fenced tier), false-green (does a
  malformed/absent issue slip?), one-owner (no dup of parse_issue_ref/plan
  scan vs the review gate), portability (module-off inert), neutrality, version.
- Fix findings, ff-merge, release-tag v1.8.0.

## Feature Registry Trace
Template self-change; template tests are acceptance. Extended `test_issues.py`,
module doc test, `test_core_docs.py` (journal-state-plans issue field).
