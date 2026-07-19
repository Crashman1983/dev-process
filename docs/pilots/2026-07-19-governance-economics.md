# Governance-Economics Pilot

Status: 1/3 observed; no template routing change authorised.

This meta-repository pilot asks whether documentation-only governance changes
need a lighter execution route than ordinary Tier 2 product work. It records
evidence before changing the generated process. Until all three cases are
observed and reviewed, this file has **no template or gate effect**.

## Decision rule

After three real cases, choose `adopt | revise | reject` for a distinct route.
Adoption requires evidence that the proposed classification is unambiguous,
reduces meaningful process cost, and does not weaken review of high semantic
impact. A smaller diff or the absence of runtime code is not sufficient.

## Case 1 — Kenni product realignment documentation

Observed on 2026-07-18/19 from the completed Kenni documentation realignment
that motivated this pilot.

| Field | Observation |
|---|---|
| `intent_mode` | `documentation` |
| `semantic_impact` | `high` — changed the declared product direction and interpretation of future scope |
| `mutation_class` | `governance-only` — product/process owners changed; no runtime implementation |
| `owner` | PRD and product-direction anchors |
| `non_goals` | no runtime behavior, API contract, persistence, or feature-registry implementation change |
| `terminal_state` | review complete; merge was not authorised at observation time |
| `claim_delta` | corrected a stale meeting-capability claim against the current inventory owner |
| `process_cost` | 363 plan lines, 15 acceptance criteria, 10 commits, and 3 review rounds |
| `repeated_decision_question` | `yes` — the documentation-only scope and intended terminal state were reconfirmed repeatedly |
| `tool_stalls` | no material tool stall observed; elapsed cost came primarily from process breadth and review iteration |
| `outcome` | evidence retained; no routing decision before cases 2 and 3 |

## Case 2 — not observed

| Field | Observation |
|---|---|
| `intent_mode` | not observed |
| `semantic_impact` | not observed |
| `mutation_class` | not observed |
| `owner` | not observed |
| `non_goals` | not observed |
| `terminal_state` | not observed |
| `claim_delta` | not observed |
| `process_cost` | not observed |
| `repeated_decision_question` | not observed |
| `tool_stalls` | not observed |
| `outcome` | not observed |

## Case 3 — not observed

| Field | Observation |
|---|---|
| `intent_mode` | not observed |
| `semantic_impact` | not observed |
| `mutation_class` | not observed |
| `owner` | not observed |
| `non_goals` | not observed |
| `terminal_state` | not observed |
| `claim_delta` | not observed |
| `process_cost` | not observed |
| `repeated_decision_question` | not observed |
| `tool_stalls` | not observed |
| `outcome` | not observed |

## Final assessment — deferred

Decision: `adopt | revise | reject` after case 3. Until then, existing tier
routing remains authoritative and `governance-only` is an observation label,
not an active route.
