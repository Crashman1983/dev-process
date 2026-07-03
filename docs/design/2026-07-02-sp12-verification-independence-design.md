# Design: verification-independence (SP12)

**Date:** 2026-07-02
**Status:** approved (scope: make context-independence of verification a
first-class, tier-scaled process property — the gap a reader surfaced after
the telemetry slice)
**Slice:** state the one thing the process left to convention — that a check is
only worth its independence from the work it checks — as core methodology, and
scale it to the risk tier so it buys quality without taxing throughput.

## Gap

The process enforces context-independence in exactly one place: the merge
review runs as a fresh process over a read-only bundle, and the implementing
agent does not self-certify. Everywhere else — design, plan, execute, and any
in-loop grading — "fresh context" is convention, and the anchor-reload rule is
a mitigation for the fact that the same context is carried across steps, not a
guarantee that it isn't. The sharpest symptom: an in-loop grader that scores
its own session's work against its own rubric confirms rather than catches (a
no-signal regime), and same-family checks share blind spots even when their
context is fresh — a defect can slip a fresh grader *and* a fresh reviewer of
the same family.

Naively fixing this by making every step fresh would wreck throughput. The
insight is that independence is a *budget*: production wants coherence (warm
context), verification wants distance (independent context), and the amount of
distance should scale with what a missed defect costs.

## Decision 1 — production runs warm, verification runs independent

A new core doc, `verification-independence.md`, states the split as
methodology: brainstorm→plan→execute are production and run in one continuous
context (re-priming between them is waste); grading and review are verification
and must run independent of the producing context, because independence is the
property that makes a check mean anything.

## Decision 2 — independence scales with the tier

- **Tier 0–1:** in-context self-check suffices (a blind spot is cheap).
- **Tier 2–3:** a fresh process reviews from a read-only bundle (diff + plan +
  rules), not the producing context; single model family acceptable.
- **Tier 4:** independence must cross the model family (uncorrelated blind
  spots) and add adversarial verification — reviewers try to refute, majority
  refutation blocks. This is where an escaped defect is most expensive, so this
  is where the expensive independence is spent.

`risk-tiers.md` gains a compact pointer; `workflow.md` names the warm-vs-
independent split on the Execute and Review phases; mandatory rule 7 (review
gate) points to the new doc for *how* the gate earns its trust.

## Decision 3 — independence is attested, not assumed

The step that is supposed to be independent is easy to run warm by accident, so
the review records how it ran (bundle-only, non-implementing process, and at
Tier 4 cross-model). An unattested review counts as a warm self-check, one tier
weaker than it claims — the independent step becomes auditable instead of taken
on faith.

## Why this is efficient, not just safe

Production stays warm and fast; the fresh, cross-model, adversarial pass fires
only at the tier that warrants it. A self-grading step in the producing context
is the worst of both worlds — it costs a model call and returns false comfort —
so the process prefers one trustworthy independent check over several
correlated ones.

## Out of scope

A machine gate that verifies a step *actually* ran in a fresh session (an
environment property, not an artifact fact — the doc makes it a named, attested
expectation instead); harness-specific spawn mechanics (those live in each
harness's command adapters, not the neutral methodology); the concrete
retirement of any project's in-loop grader (a per-project, data-gated call).
