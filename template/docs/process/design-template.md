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
answer needs investigation). An assumption about an external tool's behaviour
names the probe that confirmed it. The `clarification` gate (core) enforces the floor
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
copies: name the owning contract/spec files instead of restating them. New shared behavior gets its contract declared first
(mandatory rule 3).

## Acceptance criteria
Numbered EARS criteria (`When <trigger>, the system shall <response>` — DoR R2,
`definition-of-ready-and-done.md`), including the negative, edge,
authorization, and invalidation/cleanup cases:

- AC-1: When …, the system shall …
- AC-2: …
- AC-3: struck — <why it was cut> (a cut criterion keeps its id and its reason; a bare strike-through cuts nothing)

## Alternatives considered
The paths not taken, one line each, with the reason — enough that the next
reader does not re-litigate them. An alternative whose rejection is a
significant, hard-to-reverse decision becomes a decision record instead
(mandatory rule 4).

## Open questions
The [NEEDS CLARIFICATION: …] markers still unresolved, gathered here so the
approval conversation sees them in one place. Empty at approval.

## Threat and failure question (Tier 3; Tier 2 for gate code, data loss, authorization, migration, concurrency)
What could an attacker do with this change? Assets touched, new inputs, trust
boundaries crossed (`workflow.md`, Brainstorm; `review-checklist.md`,
Security). How can it lose data, be bypassed, fail open — what does a
missing or unresolved input read as? Walk the classes of
`docs/process/failure-catalog.md` the change touches; name the ones that apply.

## Transitions (state machines and event-driven work only)
A table instead of prose invariants: state × event → result, including the
forbidden transitions and when a derived assignment expires (its basis gone
or changed). Concurrency, a lifecycle, a guard and a parser count as state
work too. Name the invariant, its one owner, and every writer and reader of
the state. The `Test` column holds one test per row;
rows of one equivalence class may name the same test,
and a forbidden transition has a negative test. A test cell is `<path>::<test>` (it may not exist yet) or
`struck — <reason>`. In a Tier 2+ plan the `plan-structure` gate reads the
table: every cell filled, and a test in every test cell once the first task
is ticked. Other work omits this section. The review bundle notes a likely
missing table when a plan speaks of states, events or expiry and has no such
section.

| State | Event | Result | Test |
|---|---|---|---|
| draft | submit | in review | `tests/test_order.py::test_submit_starts_review` |
| in review | approve | approved | `tests/test_order.py::test_decision_ends_review` |
| in review | reject | draft | `tests/test_order.py::test_decision_ends_review` |
| approved | submit | forbidden | `tests/test_order.py::test_submit_after_approval_is_refused` |
| approved | price list changed | approval expires → draft | struck — prices are frozen at approval in this release |

## Fresh-worktree dry run (migrations; deleted or replaced gate, hook or lane scripts)
Required before the first plan review when the plan migrates (a template
update with `migration: true` from `template_verify`) or deletes or replaces
a gate, hook or lane script. Two parts, as evidence, not intent:
1. The plan's steps — or the checks that prove them — run once in a fresh
   `git worktree` without `.venv`, `node_modules` or other caches: each
   command with its exit code.
2. For every path the plan deletes or replaces, a search for its consumers,
   including existence probes (`is_file()`, `exists()`, `test -f`) that would
   go quiet instead of failing: the command and its hits.
Other work omits this section.
```

## Why a template and not a gate

Whether a section's *content* is good is exactly the judgment the review
supplies (`review-checklist.md`, Specification quality) — a machine could only
check that headings exist, which invites ritual compliance. The one mechanical
floor worth enforcing is the marker rule above, and the `clarification` gate
owns precisely that and nothing more.
