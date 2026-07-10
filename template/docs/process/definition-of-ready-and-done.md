# Definition of Ready & Definition of Done

Two **binding** checklists, each tied to a transition of a single unit of work
(an issue or a story):

- the **Definition of Ready (DoR)** gates *starting* work on it (the
  `Proposed → Ready` step);
- the **Definition of Done (DoD)** gates *finishing* it (the review/merge gate —
  closing the issue is the record).

This is per-work-item readiness and doneness. It is **not** the one-time
project-onboarding readiness (baseline committed, CI wired, `PRODUCT.md`
onboarded) — that lives in `start-here.md` under "Definition of ready (project
onboarding)".

This document is the single visible **owner of the work-item checklists**.
Enforcement is delegated to the mechanisms named in each row — it does not add a
second gate. The tools that evaluate a row differ per harness and per installed
module; the checklist items do not. Where a named mechanism's module is not
installed, the item is carried by review judgment instead.

## Bindingness

Both are **always evaluated** at their gate, and **followed by default**. Every
item is either **met** or carries a **documented, justified deviation** a
reviewer can trace:

- a **DoR** deviation is recorded on the issue (a `## Deviations` note or comment);
- a **DoD** deviation is named in the merging commit body / PR, per mandatory
  rule 8 (a skipped gate or dropped scope is documented there).

Silent skipping is not allowed. This mirrors how the process already treats a
plan's `Applicable constraints` (satisfied or explicitly not-applicable) and
decision obligations (adopted or a recorded follow-up).

## Definition of Ready — gate: `Proposed → Ready`

A unit of work is ready to be started when:

| # | Item | Evaluated by (owner) |
| - | ---- | -------------------- |
| R1 | Typed (bug / chore / feature / epic) | the issue-hygiene view (`attention.py`) where `github-issues` is active; else review |
| R2 | Acceptance stated in **EARS** (`When <trigger>, the system shall <response>`); an epic carries scope + invariants instead | the issue-hygiene view; decomposed at the tier's design step — an upfront brainstorm (Tier 3) or the plan (Tier 2) (`workflow.md`) |
| R3 | Linked to its epic/story and the applicable design / decision records / product frame | brainstorm & plan review (`workflow.md`, mandatory rule 4) |
| R4 | Dependencies (`blocked_by`) known, and no open blocker remains | the backlog-ordering view (`story_order.py`) where `feature-registry` is active; else review |

Recognizing the tier (`risk-tiers.md`) is part of getting to Ready: it decides
how much of the cycle runs (mandatory rule 2), and a Tier 2+ item is not ready
until it is tracked by an issue (enforced by the `github-issues`
issue-before-code gate where installed).

## Definition of Done — gate: review / merge

A change is done when:

| # | Item | Evaluated by (owner) |
| - | ---- | -------------------- |
| D1 | Every acceptance criterion has a passing test | feature-registry coverage + **review** (`review-checklist.md`) |
| D2 | All **active** process gates are green | the gate runner (pre-push / CI) |
| D3 | **Affected docs updated** — module docs, decision records, API/contract, README; no stale references | **review** judgment; path validity by the doc-drift gate |
| D4 | Decision obligations reconciled (adopted, or deferred with a follow-up); a new significant decision is recorded before the code that assumes it | the core `decision-records` gate + review (mandatory rule 4) |
| D5 | Atomic, conventional commit(s); any skipped gate or dropped scope named in the commit | `commits.md` + review (mandatory rule 8) |
| D6 | Issue status set at each phase transition, and the issue closed with the commit ref on merge | the claim/lifecycle convention + review (`github-issues` module) |

The **Review** phase (`workflow.md`, `review-checklist.md`) owns the DoD gate: it
does not pass unless each applicable item is met or a documented deviation is
present.

## Amending these checklists

The DoR and DoD are **living**. When a human expresses a new readiness or
completion expectation — even in passing, e.g. "before we start, X must be true"
or "at the end, Y must have happened" — treat it as an instruction to **update
the relevant checklist here** (add or change a DoR/DoD item), not as a one-off
for the current task. Propose the edit as part of the work, so the expectation is
enforced from then on for every unit of work. Removing or weakening an item is
itself a change that needs a stated reason.
