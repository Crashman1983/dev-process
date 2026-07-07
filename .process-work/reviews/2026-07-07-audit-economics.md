audit: engineering-economics
work: PR #13 (v1.19.0 branch state)
campaign: 2026-07-07-hard-audit
issue: #21
campaign-issue: #14

## Prompt

```
Skeptical engineering-economics auditor. Stress the overhead-pays-off claim
quantitatively: context-token economics per tier, ceremony per change (what
feeds a gate vs write-only ritual), multi-agent scaling, gate-suite runtime
on large repos, the honesty of the "when not worth it" story. Numbers for
every claim. (Model: Sonnet. Core mission quoted.)
```

## Result

3 MAJOR, several measured MINORs. Verdict: the economics story is close to
true rather than fundamentally broken — most artifacts are genuinely
machine-consumed; the three overstatements are each one-line fixes.
Measured: Tier-0 read ~800 tok (proportional), Tier-1 ~5,340 tok
(disproportional), Tier-2 ~9,100-13,600 tok; gate suite 0.43s baseline,
security-floor the only repo-size-scaling gate (1.67s at 50k files).

## Findings

FINDING sev=major action=follow-up issue=#17 reading cost not tier-proportional — quick mandates whole workflow.md + review-checklist.md for a three-line fix
FINDING sev=major action=follow-up issue=#17 8 of 12 module docs have no pointer anywhere in the anchor reading chain — ~12.5k tokens of binding rules discoverable only via CI failure
FINDING sev=major action=follow-up issue=#17 multi-agent SSOTs unprotected beyond git — story-ID race caught only at second merge, semantic PRODUCT.md merges invisible to gates, publish_review campaign TOCTOU race
FINDING sev=minor action=follow-up issue=#17 inbox.md is write-only ritual — no command reads it back, not even prime
FINDING sev=minor action=follow-up issue=#17 gate_runner pays 13 interpreter spawns as fixed per-run tax; security-floor scales with repo size not process size
FINDING sev=minor action=follow-up issue=#17 start-here honesty stops short of the mid-size trap — three core gates are not toggleable
