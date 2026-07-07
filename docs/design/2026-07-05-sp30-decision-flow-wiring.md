# SP30 — Wire decision records into the working flow

## Problem

The ADR/PRD process audit (2026-07-05) found that creating and updating Decision
Records is *mandated* (rule 4, start-here) but *wired into the flow* almost
nowhere. Three verified gaps:

1. `workflow.md` — the phase SSOT every slash command points at — never mentions
   decision records in any phase. An agent following `/plan` reads workflow.md
   and journal-state-plans.md and never meets the duty; it lives only in rule 4.
2. `review-checklist.md` asks no decision question. A *missing* record is
   mechanically undetectable (the gate can only check integrity of records that
   exist), so the review is the one point where a human/LLM can catch "this
   change embodies an undocumented significant decision" or "this change makes
   an Accepted record obsolete" — and the checklist never prompts for it.
3. The plan format carries `tier:` and `issue:` but no decision duty — nothing
   asks a plan to name the records it read or the records it entails (Kenni's
   `## Anchor Delta` has no template counterpart).

Gap 4 from the audit (a change can silently obsolete an untouched record) has no
mechanical fix — it is exactly what the checklist question in (2) exists to
catch.

## Decision

Wire the existing duty into the three places the flow actually reads. No new
gate, no new artifact, no rule change — rule 4 already carries the obligation;
this slice makes it visible at the moments it applies. All three additions are
honest about enforceability: they are review-/discipline-level, not
machine-checked, and say so.

**(a) workflow.md phases.** Brainstorm: read the relevant decision records
before designing — an endorsed decision is a constraint, not an open question;
a design that overturns one names the supersession. Plan: the plan names the
records it read and any new/superseded record the change entails (see plan
format). Execute: a significant decision discovered mid-build stops the task —
record first, then the code that assumes it (rule 4). Review: check the
decision questions on the checklist.

**(b) review-checklist.md — new "Decisions" section** (after Design, before
Tests): does the change embody a significant, hard-to-reverse decision that has
no record? Does it contradict an `Accepted` record (either the change or the
record is wrong — resolve, don't merge the contradiction)? Does it make an
existing record obsolete — if so, the record is superseded in the same change,
not left lying. Framed as judgment questions; explicitly the non-mechanical
counterpart of the `decision-records` gate.

**(c) journal-state-plans.md plan format.** A Tier 2+ plan names the decision
records it read (or `none apply`) and any record the change entails. Prose
duty, deliberately NOT a gated machine-readable field: a `decisions:` line
enforced by a gate would only check presence of text, inviting a ritual
"decisions: none" — the review checklist (b) is where substance is judged.
Honestly labeled as such.

## Non-goals

- No PRD/product-level artifact — deliberately deferred; the product side is
  under separate discussion (audit finding: the template has no PRD concept;
  whether feature-registry + arch-docs suffice is a product decision).
- No new gate and no gate change — `check_decisions.py` already owns record
  integrity; presence-of-judgment cannot be gated without false confidence.
- No change to rule 4 — the duty exists; this is wiring, not legislation.

## Anchor Delta

`workflow.md.jinja` (four phase paragraphs extended), `review-checklist.md`
(one new section), `journal-state-plans.md` (plan-format paragraph). No command
file changes — commands already point at workflow.md. No gate, no schema, no
module change.

## Feature Registry Trace

Template self-change; template tests are acceptance. New assertions in
`test_core_docs.py`: workflow.md mentions decision records in Brainstorm, Plan,
Execute and Review; review-checklist.md carries the Decisions section with the
three questions; journal-state-plans.md names the plan decision duty.

tier: 2
review-waived: template-repo slice; independent fresh-context review runs before push (same session pattern as SP28/SP29)
