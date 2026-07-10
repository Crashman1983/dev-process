audit: cold-start-coherence
work: PR #23 (v1.24.0 branch state)
campaign: 2026-07-08-functional-audit
campaign-issue: #24
issue: publish-waived: fixed in PR #23, bundled into campaign #24

## Prompt

```
Cold-start adopter & coherence reviewer. Follow the documented path against the
rendered output — BOOTSTRAP -> start-here -> mandatory-rules -> risk-tiers ->
workflow -> DoR/DoD -> review-checklist — and flag every contradiction, dead
end, or dishonest degradation, grounded in execution where checkable. (Model:
Opus. Full prompt archived in session.)
```

## Result

1 major (the sbom doc-drift fresh-render failure, independently confirming the
rendering audit), several coherence findings. Coherent negative space: the two
"Definition of Ready" concepts are disambiguated; 0–3 tier scale consistent in
the render; degradation honest for 13 of 14 gates.

## Findings

FINDING sev=major action=fix issue=- fresh sbom+doc_drift render fails gate_runner (exit 1) before product work — CI red from first commit; consensus with the rendering audit
FINDING sev=minor action=fix issue=- DoD D4 names `adr-/pdr-adoption gates` that do not exist here — decision adoption is the core `decision-records` gate; corrected
FINDING sev=minor action=fix issue=- risk-tiers Tier-2 route (plan->review) disagrees with workflow "Tier 2+ full cycle" and DoR R2 pinning decomposition to brainstorm; reconciled to per-tier design step
FINDING sev=minor action=fix issue=- README changelog (SP12/SP19) still shows the superseded "Tier 4" scale though the process is 0–3; front page self-contradicted; corrected
FINDING sev=nit action=fix issue=- DoR mis-cites mandatory rule 2 for issue-tracking (rule 2 is tier-derivation + plan); reworded
FINDING sev=nit action=fix issue=- shipped gate code carries internal sprint labels (SP19/20/32); scrubbed
FINDING sev=nit action=fix issue=- .process-work/README omits inbox.md and reviews/ that the start-here router documents; added
