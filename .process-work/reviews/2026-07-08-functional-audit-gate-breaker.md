audit: gate-breaker
work: PR #23 (v1.24.0 branch state)
campaign: 2026-07-08-functional-audit
campaign-issue: #24
issue: publish-waived: fixed in PR #23, bundled into campaign #24

## Prompt

```
Adversarial gate-breaker. Make the process gates lie — false-green (passes
when it should fail) or false-red (fails when it should pass) — by execution,
not inspection. Render the template, drive the rendered gates with crafted
inputs, capture command + output as evidence. Priority targets: check_sbom,
attention/who_is_working, the feature-registry under-granular advisory, the
pre-push hook. (Model: Opus. Full prompt archived in session.)
```

## Result

7 findings reproduced by execution. sbom was the hotspot (4 findings). Cleared
completely: pre-push ref parsing/aggregation, feature-registry cycles/coverage,
who_is_working helpers.

## Findings

FINDING sev=major action=fix issue=- sbom skips every type==application component — a GPL dep typed application passes (false-green); now only the metadata.component root is exempt
FINDING sev=major action=fix issue=- sbom compound SPDX `MIT OR Apache-2.0` string-compared and rejected (false-red); now OR/AND-evaluated
FINDING sev=major action=fix issue=- sbom multiple licenses[] entries pass if any one allowed — GPL co-listed with MIT passes; now a conjunction (all required)
FINDING sev=minor action=fix issue=- sbom license.name `MIT License` not matched against `MIT` (false-red) — documented + policy guidance added
FINDING sev=minor action=fix issue=- attention.py counts non-existent test files while check_feature_registry counts only existing — same story disagrees; attention now counts existing only
FINDING sev=minor action=accept issue=- a pushed commit deleting gate_runner.py escapes pushed-commit gating — best-effort local hook, CI is the backstop (by design)
FINDING sev=nit action=fix issue=- attention `_has_ears` matches bare `shall` in prose — advisory only; left liberal to avoid false-flagging real issues (documented)
