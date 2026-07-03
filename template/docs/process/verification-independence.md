# Verification Independence

A check is worth only as much as its context is independent of the work it
checks. An agent that grades or reviews its own output, in the same context
that produced it, inherits that context's framing and blind spots — it tends to
confirm rather than catch. Preventing that is the whole reason a review gate
exists, so the gate's value is bounded by how independent it actually is.

The process spends independence like a budget: production runs warm,
verification runs independent, and the degree of independence scales with the
tier.

## Production runs warm

Brainstorm, plan, and execute are production. They live on coherence — the plan
follows from the design, the code from the plan. Running them in one continuous
context is correct and efficient; forcing a fresh session between them discards
that coherence and pays a re-priming cost for nothing. Do not manufacture
independence here.

## Verification runs independent

Grading and review are verification. Their entire job is to see what production
could not, so independence is not overhead — it is the property that makes the
check mean anything. Scale it to the tier (`risk-tiers.md`):

- **Tier 0–1** — an in-context self-check is enough; the change is small and
  reversible enough that a blind spot is cheap.
- **Tier 2–3** — a fresh, independent process reviews from a read-only bundle
  (the diff plus the plan and the rules), not from the producing context. The
  implementing agent does not certify its own work. A single model is
  acceptable.
- **Tier 4** — independence must cross the model family. Two families' blind
  spots are uncorrelated; a same-family check, however fresh its context, can
  still miss what its family systematically misses. Add adversarial
  verification: independent reviewers try to *refute* the change rather than
  confirm it, and a majority refutation blocks the merge.

## Independence is attested, not assumed

The one step that is supposed to be independent is easy to run in the wrong
context by accident. So the review records how it ran — bundle-only, by a
non-implementing process, and (at Tier 4) cross-model — as part of its result.
An unattested review is treated as a warm self-check: one tier weaker than it
claims. This keeps the independent step auditable instead of taken on faith.

## Why this is efficient, not just safe

Independence costs tokens and wall-clock, so the process buys it only where it
pays: at verification, scaled by risk. Production stays warm and fast; the
expensive fresh, cross-model, adversarial pass fires only at the tier where an
escaped defect is most expensive. A self-grading step that runs in the
producing context is the worst of both — it costs a model call and returns
false comfort. Prefer one trustworthy independent check over several correlated
ones.
