# Design template

The scaffold for the Brainstorm phase's output (`workflow.md`, Brainstorm): a
design/spec written to `.process-work/plans/design-<topic>.md`
(`journal-state-plans.md`, Plans). Sections are prompts, not bureaucracy — a
Tier 2 design fills them in a page; a Tier 3 design goes deeper. Delete a
section only when it truly does not apply, and say so in one line rather than
silently dropping it: the reader cannot tell "not applicable" from "forgotten".

## The clarification marker

While drafting, never guess at an underspecified point — mark it:

```
[NEEDS CLARIFICATION: <the concrete question>]
```

A marker is a first-class part of the draft: it makes the open question visible
instead of burying a silent assumption in prose. Brainstorm ends only when every
marker is **resolved** — answered by the user, or converted into a written,
named assumption in the design (or into a spike, `workflow.md`, Spike, when the
answer needs investigation). The `clarification` gate (core) enforces the floor
mechanically: an unresolved marker in an **active plan** fails CI — a plan is
built from an *approved* design, so open questions must not survive into it.
Markers in an in-progress design are legitimate and only reported, never
blocking.

## Sections

```markdown
# Design: <topic>

## Intent
What problem this solves and why now — the *what/why*, no implementation. Name
the product goal (`PRODUCT.md`) it serves, or that it is product-neutral.

## Constraints read
The decision records (`docs/process/adr/`) and product-frame entries read as
constraints — or "none apply". A design that overturns an endorsed decision
names the supersession (mandatory rule 4).

## Touchpoints
What existing behavior, contracts, and data this touches — pointers, not
copies: name the owning contract/spec files (e.g. the contract-first capability
spec or contracts-drift pins, where those modules are installed) instead of
restating them. New shared behavior gets its contract declared first
(mandatory rule 3).

## Acceptance criteria
Numbered EARS criteria (`When <trigger>, the system shall <response>` — DoR R2,
`definition-of-ready-and-done.md`), including the negative, edge,
authorization, and invalidation/cleanup cases:

- AC-1: When …, the system shall …
- AC-2: …

## Alternatives considered
The paths not taken, one line each, with the reason — enough that the next
reader does not re-litigate them. An alternative whose rejection is a
significant, hard-to-reverse decision becomes a decision record instead
(mandatory rule 4).

## Open questions
The [NEEDS CLARIFICATION: …] markers still unresolved, gathered here so the
approval conversation sees them in one place. Empty at approval.

## Threat question (Tier 3)
What could an attacker do with this change? Assets touched, new inputs, trust
boundaries crossed (`workflow.md`, Brainstorm; `review-checklist.md`,
Security).
```

## Why a template and not a gate

Whether a section's *content* is good is exactly the judgment the review
supplies (`review-checklist.md`, Specification quality) — a machine could only
check that headings exist, which invites ritual compliance. The one mechanical
floor worth enforcing is the marker rule above, and the `clarification` gate
owns precisely that and nothing more.
