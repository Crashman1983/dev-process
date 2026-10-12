# Review brief, round 3: the process as a check graph (for an independent reviewer)

> **Deutsch, kurz:** Dritte Runde für Codex Astra, zu Revision 4 von
> `docs/analysis/2026-10-12-closed-loop-plan.md`. Anders als in Runde 1 und 2
> ist der Maßstab **Verhältnismäßigkeit**: Nicht nur finden, was schiefgehen
> kann, sondern abwägen, ob jede Kontrolle ihren Preis wert ist.

## What changed since round 2

The owner reset the goal and the review standard:

- **Goal:** more output at lower cost, with **no loss of quality or security**.
  The loop may add, change and remove gates to get there.
- **Standard:** proportionality. An LLM system needs latitude when it
  detects, diagnoses, proposes and designs. Hard limits belong where an error
  is expensive or hard to reverse. A control that costs more than it protects
  is itself a defect.

Revision 4 keeps the boundaries rounds 1–2 established (owner-owned
guardrails and protected nodes, an isolated evaluator, separate loss measures,
two-axis bug origin, always-on sentinels). It drops what revision 3 added on top:
typed tunables with deadband and dwell for every rule, preregistered estimands
for every change, six separate loops. Plan §11 lists both groups with reasons.

## Your role

You are an independent reviewer, not only a refuter. For each finding, state:

1. the concrete failure scenario;
2. how likely and how costly it is in a single-operator project;
3. the cheapest control that covers it, and whether that control is worth its
   cost.

A finding whose cheapest control costs more than the expected loss is a
**note**, not a blocker. Say so explicitly. Do not implement anything. The
repository wins over this brief.

## Scope

- Plan revision 4, all sections. Main focus: §3 (review standard), §5 (node
  measurement), §6 (change lifecycle), §8 (rights), §11 (what was relaxed and
  why).
- The relaxations in §11 "Was bewusst anders gelöst wird": for each, say
  whether the reasoning holds or whether the relaxed risk is real and
  under-covered.
- Code on the PR head only as far as the plan relies on it (gate runner,
  `process_kpis.py`, `dispatch.py`, `optimize.py`).

## Questions (minimum)

1. **The asymmetry argument (§3).** Savings are measured directly; only the
   quality side is uncertain, and it is observed per check event, not per
   issue. Does this hold? Where does it break?
2. **Node measurement (§5).** Is "true catch = block followed by a fix commit"
   sound or gameable? Does the overlap sample estimate unique catches well
   enough to decide a removal?
3. **Lifecycle (§6).** Is `block → sampled → off` with automatic restore on a
   sampled catch a sufficient non-inferiority guard? What sample rate and
   probation period would you consider proportionate for a project with
   ~100 merges per month? Where must it not be used?
4. **Guardrails and rollback (§4, §6).** Do window-based rollbacks (newest
   first, one weakening per guardrail) attribute correctly? Can they
   oscillate?
5. **Protected nodes.** Is the default list right — too many (optimization
   blocked) or too few?
6. **Freedom for the LLM (§3, §7).** Is giving the weekly loop free-form
   proposals and free `shadow`/`warn` additions safe within the budget? What
   is the worst realistic outcome?
7. **Proportionality overall.** Which remaining control in revision 4 costs
   more than it protects? What would you remove?

## Deliverable

A PR review on #216 with a verdict (`approve`, `revise`, `block`). Severity per
finding is `blocker`, `major` or `note`, set by expected loss versus the cost of
the cheapest covering control. Mark what you executed and what is a design
scenario. Answer the seven questions.
