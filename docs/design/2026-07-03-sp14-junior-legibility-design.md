# Design: junior legibility (SP14)

**Date:** 2026-07-03
**Status:** approved (scope: the three gaps a junior-developer simulation
surfaced — the process guides a junior to the review door but does not teach
them what to look for once inside, and gives no help recognizing a task's tier
or the ceiling of the security-floor gate)
**Slice:** close the legibility gaps so a junior driving the process without a
senior beside them still catches the dangerous class, without inflating the
thin kernel.

## Gap

A rendered example project (a URL shortener) driven from a junior's shoes
exposed a consistent shape: the process is **self-explanatory for the
workflow** (onboarding, tier routing, machine gates) but **thin on domain
judgment**. Concretely, planting five classic junior pitfalls:

- The machine gates caught only the grep-able one (`shell=True`). An **open
  redirect**, an **unhandled short-code collision (500)**, and a **duplicated
  generator** passed every gate — they live only at the review gate.
- The template's review guidance is a few neutral sentences ("judge functional
  completeness, correctness, rule adherence") with **no checklist** of what
  those mean — so a junior reviewer has nothing telling them to validate a
  redirect target or check for dead data. A senior or AI reviewer supplies that
  judgment; a junior does not have it.
- The tier matrix names the risk *categories* (persistence, security, …) but
  gives no help *recognizing* that a specific task falls in one. The redirect
  was tiered correctly only because it also touched persistence — the security
  angle would have been missed.
- After fixing `shell=True`, all gates read green — a junior can feel "security
  checked" while shipping an open redirect. The `security-floor` module is
  honest that it is a "grep-able subset", but that is too quiet for a junior.

## Decision 1 — a neutral review checklist as a core doc

New `review-checklist.md`: the distilled, stack-neutral version of what a
competent reviewer checks — completeness (every field/side-effect reaches its
terminal state; no dead data; all paths), correctness (boundaries, empties,
duplicates, concurrency, error/retry), **security** (untrusted input reaching a
sink without validation — redirect target, rendered markup, query, subprocess,
file path, deserialization; authz fail-closed; secrets), design/one-owner
(does this duplicate an existing owner?), and tests-prove-acceptance. Framed as
questions, not stack specifics, so it stays methodology, not implementation.
Depth scales with the tier; `workflow.md` Review and the `/review` command
point at it. This is the piece the simulation proved missing — and it is
generic security-review methodology, not a project fact, so it belongs in the
neutral SSOT.

## Decision 2 — a tier-recognition heuristic in risk-tiers

`risk-tiers.md` gains a short "Recognizing your tier" block: a handful of
trigger questions that turn the risk *categories* into a recognition test —
does it read or write persistence? does untrusted input leave the process
(redirect, render, query, shell, file path)? does it touch auth, a contract, or
multiple surfaces? A yes to any lifts it to Tier 3+ regardless of diff size.
This helps a junior map their concrete task onto the matrix instead of assuming
the category list is self-applying.

## Decision 3 — one honest sentence in security-floor

`security-floor.md` gains a sentence naming its ceiling explicitly: it is a
pattern floor, not the security review — runtime vulnerabilities (open
redirect, injection, authorization) are the review gate's job, caught by the
`review-checklist.md` security questions, not by this gate. Removes the false
"security checked" signal a green floor can give.

## Out of scope

Any machine gate for the checklist (it is judgment, not grep — the whole point
is that these defects are not mechanically detectable; a gate would be the
false-green the process forbids); stack-specific checklists (the neutral
question form is deliberate — a project may extend it in its own anchor);
turning the checklist into per-language linters (that is the project's tooling
choice, not template methodology).
