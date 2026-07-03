# Plan: junior legibility (SP14)

Design: `docs/design/2026-07-03-sp14-junior-legibility-design.md`.

## Task 1 — review-checklist.md core doc

- Add `template/docs/process/review-checklist.md`: stack-neutral reviewer
  questions across completeness, correctness, security (untrusted-input-to-sink),
  design/one-owner, tests-prove-acceptance; states depth scales with the tier
  and points to `verification-independence.md` for how independent the review
  must be. No project or stack specifics.
- Wire: `workflow.md.jinja` Review sentence + `.claude/commands/review.md` +
  the copilot `review.prompt.md` + the AGENTS.md review line point at it.
- Test: add to `tests/test_core_docs.py` CORE list (present, no jinja, no
  project terms) + assert the security question about untrusted input to a sink
  is present.

## Task 2 — risk-tiers recognition heuristic

- `risk-tiers.md`: "Recognizing your tier" block with the trigger questions.
- Test: `test_risk_tiers_matrix` stays green; add an assert the recognition
  questions are present.

## Task 3 — security-floor ceiling sentence

- `security-floor.md`: one sentence naming the pattern-floor-not-security-review
  ceiling, pointing to `review-checklist.md`.
- Test: existing security-floor tests stay green (module-off ships nothing).

## Task 4 — release

- `pyproject.toml` → 1.4.5; `docs/SBOM.md`; README status + roadmap row SP14.
- Independent adversarial review (Tier-4 rule) over the diff; attest
  single-family; merge + tag `v1.4.5`.
