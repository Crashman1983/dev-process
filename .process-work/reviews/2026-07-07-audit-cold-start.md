audit: cold-start-adopter
work: PR #13 (v1.19.0 branch state)
campaign: 2026-07-07-hard-audit
issue: #20
campaign-issue: #14

## Prompt

```
Simulate a competent but completely cold adopter who has NEVER seen the
template. LIVE the process end-to-end twice (greenfield + brownfield),
strictly by the rendered docs, no development history. Record every point of
ambiguity, disagreement, unhelpful failure, or forced guess.
(Model: Fable. Core mission quoted.)
```

## Result

1 BLOCKER, 4 MAJOR, 7 MINOR — from two full lived simulations (greenfield
"SnipShelf" with a real two-round independent review; brownfield "wordbag").
What genuinely worked: honest degradation is real, failure messages mostly
name the fix, the fresh-agent bundle review caught real defects, brownfield
render perfectly additive.

## Findings

FINDING sev=blocker action=follow-up issue=#16 default install renders the last tag (v1.14.0) while docs describe v1.19.0 — PRODUCT.md missing from what adopters get; resolved operationally by tagging after merge, BOOTSTRAP skew warning tracked in #16
FINDING sev=major action=follow-up issue=#16 github_issues dead-ends tracker-less projects — done-stories unsatisfiable (no story-level waiver), follow-up findings force dishonest accept-downgrades
FINDING sev=major action=follow-up issue=#16 first-run checklist walks into the repo's own pre-commit hook at the baseline commit
FINDING sev=major action=follow-up issue=#16 kernel-merge instruction unfollowable in the standard brownfield skip-CLAUDE.md configuration — no rendered adapter exists
FINDING sev=major action=follow-up issue=#16 Tier-1/2 boundary self-destructs — read literally, user-visible swallows nearly every small feature
FINDING sev=minor action=follow-up issue=#16 REVIEW work= matching semantics undocumented outside the gate source
FINDING sev=minor action=follow-up issue=#16 greenfield/brownfield record location and dialogue-output target file never named
FINDING sev=minor action=follow-up issue=#16 plan-archive choreography vs ff-only + no-main-commits must be derived by the adopter
FINDING sev=minor action=follow-up issue=#16 reviewer output grammar not pushed into the review instruction — fresh reviewers emit unparseable records
FINDING sev=minor action=follow-up issue=#16 BOOTSTRAP verification uses python where start-here already knows python3
FINDING sev=minor action=follow-up issue=#16 ADR granularity for stack decisions is a guess
FINDING sev=minor action=follow-up issue=#17 no single which-artifact-when routing table — learnable only via ~1100 lines across 9 files
