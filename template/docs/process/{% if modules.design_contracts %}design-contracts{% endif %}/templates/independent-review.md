# <Surface> design — independent review, round N[.M]

**Reviewer:** <agent / person> — **Independence:** <"independent of the authoring agent: different model family" | "same family — NOT model-independent">
**Date:** YYYY-MM-DD
**Reviewed commit:** <sha>
**Seal reviewed:** manifest.sha256 = `<64-hex>` (`scripts/process/seal.py --verify <round dir>` passed)
**Decision:** GO | GO with conditions | NO GO

The gate reads two things from this file: the `Decision:` line, and the
seal hash. A contract becomes `accepted` only on a GO, and only for the
boards this hash names; a re-sealed round needs a new review file (or a
new round section with its own hash).

## Verified scope

What was actually done — and what was not:
- seal verified; export QA report read (n cases, n failures)
- boards opened: …
- files read: contract §…, tokens, …
- not done: <e.g. no device test, no screen reader pass>

## Rubric (weights sum to 100)

| Criterion | Weight | Score | Rationale |
| --------- | ------ | ----- | --------- |
| Visual hierarchy and readability | 20 | | |
| Interaction and hit areas | 20 | | |
| State completeness (loading / empty / error / unknown, both themes, AX3) | 20 | | |
| Consistency with the contract (every board traceable to IDs) | 20 | | |
| Accessibility (contrast, names, focus order, reflow) | 20 | | |
| **Total** | 100 | | |

Adjust the criteria and weights per surface, but keep them written down
before scoring: a rubric decided after the fact measures nothing.

## Findings

### Blockers (F*) — must be resolved before GO
- F1 …

### Major (M*)
- M1 …

### Minor (m*)
- m1 …

## Conditions attached to the GO
1. …

## Open decisions for the owner
- D… (contract §9)

## Evidence limits

What this review could not see and therefore does not claim.
