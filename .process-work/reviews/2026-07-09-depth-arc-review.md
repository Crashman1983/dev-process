review: depth-arc (v1.31.0-v1.32.0 span, SP45-47)
work: PR #25
issue: publish-waived: all findings fixed in-PR before merge (this report is the record)

## Prompt

```
Two independent merge-gate reviewers over 75b0c3f..HEAD (SP45 DoR enforcement,
SP46 architecture floor rules, SP47 make_review_bundle). One adversarial/
execution (defects proven by reproduced command/output; fake gh, crafted
repos), one process-coherence (contradictions and stale references against
rendered output). (Model: Fable. Full prompts archived in session.)
```

## Result

5 major (4 executable defects, all in the new bundle tool; 1 documentation
overclaim), 3 minor, 4 nit — all fixed in the same PR (v1.32.1). The gates
themselves (SP45 DoR, SP46 floor rules) held under attack: DoR matrix, dor
freshness on re-sync, deviation escape, adr resolution edges, example-policy
false-positive hunt, EARS mirror parity — all clean.

## Findings

FINDING sev=major action=fix issue=- bundle: a diff carrying markdown ``` fences closed the ```diff fence early, swallowing the grammar section; fence now outruns the longest backtick run (min 4)
FINDING sev=major action=fix issue=- bundle: non-UTF-8 tracked text file crashed _git with UnicodeDecodeError; subprocess now decodes errors=replace
FINDING sev=major action=fix issue=- bundle: --base/-o as last argv token crashed with IndexError; bounds-checked usage exit
FINDING sev=major action=fix issue=- bundle: run from a subdirectory silently lost root sources and falsely claimed "no active plan"; root now resolved via git rev-parse --show-toplevel
FINDING sev=major action=fix issue=- the "grammar imported from the gate, can never drift" claim was half-false: only REVIEW is imported; FINDING's owner is check_issues (module-gated); claim scoped in tool/doc/CHANGELOG and the FINDING tokens pinned to check_issues enums by a template test
FINDING sev=minor action=fix issue=- security-floor: an invalid regex hid the same rule's dangling adr link; adr resolution now walks raw rules
FINDING sev=minor action=fix issue=- arch-onboarding doc referenced security_floor's doc section unconditionally (renders with the module off); now jinja-guarded with a ratchet pointer in the else-branch
FINDING sev=minor action=fix issue=- github-issues doc said untyped/no-EARS is "never a gate" — incomplete since the github-master hard path; clause added
FINDING sev=nit action=fix issue=- gh_sync deviation regex matched non-headings (##Deviations, heading-in-\s*-newline); tightened to ^#{1,6}[ \t]+
FINDING sev=nit action=fix issue=- dor slot accepted silent extra keys; exact key set enforced
FINDING sev=nit action=fix issue=- bundle: dirty working tree now disclosed in the diff section; BOOTSTRAP "one named trigger" -> "at least one"; doc snippet's ADR-0002 marked illustrative
FINDING sev=nit action=accept issue=- deviation waives the whole DoR by design (a recorded escape is the point); heading-form now enforced, gaming surface accepted
