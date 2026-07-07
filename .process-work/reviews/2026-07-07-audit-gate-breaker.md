audit: gate-breaker-red-team
work: PR #13 (v1.19.0 branch state)
campaign: 2026-07-07-hard-audit
issue: #18
campaign-issue: #14

## Prompt

```
Adversarial red-team auditor. Mission: BREAK the gates of the dev-process
copier template. Only deliverable: defects proven by execution — a finding
without a reproduced command/output is worthless. Attack every gate with
false-green constructions (quoting tricks, markdown variants, CRLF/BOM/
homoglyphs, path tricks, state tricks), false-reds, crashes, gate-vs-gate
disagreements. The suite is green — your value is what it does NOT cover.
(Model: Opus. Full prompt archived in session; core mission quoted.)
```

## Result

5 MAJOR, 3 MINOR — all reproduced by execution. Gates that resisted
completely: gate_runner, security-floor, contracts, parity, doc-drift,
product-frame (the SP31 fixes held), feature-registry cycles. Most
productive targets: check_review (SP19/29) and check_issues report handling
(SP32) — the newest enforcement surfaces.

## Findings

FINDING sev=major action=follow-up issue=#15 tier over-declaration (tier=4) bypasses cross-model check and still clears Tier-3 presence
FINDING sev=major action=follow-up issue=#15 report header split only on level-2 headings — h3-first report treats whole file as header, quoted issue: counts as publication
FINDING sev=major action=follow-up issue=#15 decisions gate reads next heading as value of an empty section — documented soft path unreachable
FINDING sev=major action=follow-up issue=#15 github-master tracebacks on mixed-type blocked_by in committed snapshot
FINDING sev=major action=follow-up issue=#15 tilde fences not stripped by review+telemetry gates — fenced verdict=pass really clears a Tier-3 plan
FINDING sev=minor action=follow-up issue=#15 campaign parent refs compared as raw strings — same issue in two forms reads as split campaign
FINDING sev=minor action=follow-up issue=#15 capability contract symbols matched as bare substrings — declared-first satisfiable by coincidence
FINDING sev=minor action=follow-up issue=#15 scalar code_roots iterated character-wise by architecture gate
