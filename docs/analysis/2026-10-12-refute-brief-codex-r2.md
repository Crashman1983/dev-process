# Refute brief, round 2: balance loop and registers (for an independent reviewer)

> **Deutsch, kurz:** Zweite Runde für Codex Astra. Prüft nur den neuen Teil
> des Plans (§4–§8 von `docs/analysis/2026-10-12-closed-loop-plan.md`,
> Revision 2) und die Code-Fixes aus Runde 1. Die Literatur zu Runde 1 steht in
> `docs/analysis/2026-10-12-refute-brief-codex.md`; unten nur, was neu dazukommt.

## Your role

Same as round 1: you are an independent refuter. Find what is wrong, unsafe,
unmeasurable, self-defeating or over-engineered. Do not implement anything. The
repository wins over this brief; check every claim you rely on.

## Scope

1. **Plan revision 2**, sections §4–§8 and §10–§11 of
   `docs/analysis/2026-10-12-closed-loop-plan.md` (PR #216 head):
   - loss ledger and outcome signals;
   - balance rules R1–R6 as reversible register data;
   - weekly and monthly loops, question register, blind-spot loop with
     coverage escalation, regression loop, cost loop, loop saturation;
   - who runs the loops (§6.7, model-agnostic);
   - decision rights (§7);
   - experiment corrections: evidence, evaluator binding, assignment, durable
     adoption (§8).
2. **Your round-1 findings:** §9 maps each to its resolution. Say for each
   whether the resolution holds, is partial or is wrong.
3. **Code fixes in commit `0557b2e`** (findings 2, 3 and 5 of round 1):
   - `Activation` truthiness;
   - one live trial per project;
   - per-field token coverage;
   - the `flow` endpoint (deploy or merge), `deployed=false` reported as failed;
   - the escape window measured from deploy.

   Re-run your reproductions against the PR head.

Out of scope: P5–P7 (offline screen, inert release boundary, upstream channel).
They are deferred, and you already reviewed their round-1 form.

## New owner requirements behind revision 2

- **Continuous detection, no process for its own sake.** A mechanism that
  continuously finds and works on improvement potential, balanced between
  process improvement and real product/delivery improvement.
- **Everything revisable.** Signals, balance rules and measures are themselves
  reviewed, reversible and adapt to changing conditions; an LLM does the
  adapting, not a fixed formula.
- **More loops, to a degree.** More loops where they stabilise, with the limit
  found by the system itself.
- **Missing signals closed by a loop.** Example: no field says whether a bug
  is a regression or newly discovered; a loop must notice, introduce the
  field and use it from then on (acceptance A6).
- **Value at epic level.** Value = a feature is actually usable, or a
  disruptive bug is fixed fast.
- **No fixed models.** Every loop and review must be runnable by Claude or
  Codex.

## Attack questions (minimum)

1. **Self-reference.** Can the monthly loop move its own ruler through
   in-range rule changes (e.g. tune R4 so product signals never fire, or widen
   coverage targets so blind spots disappear)? Are the framework ranges plus
   prognosis-vs-actual enough, or is a fixed outer reference needed?
2. **Goodhart in the loss ledger.** Can loss hours fall through
   reclassification, issue splitting, moving work out of instrumented paths, or
   skipping review rounds, without delivery improving? Does epic-level O1
   bind that? Which variant of Goodhart (regressional, extremal, causal,
   adversarial) applies where?
3. **Free-text pattern discovery (A7).** Is LLM scanning of issue/commit text
   a viable blind-spot detector, or does it produce noise and field
   inflation? Is the three-period retirement enough? What is the minimal
   viable form?
4. **Saturation.** Are "three empty periods" plus a fixed cap a sound
   saturation mechanism? Or must a loop show that it stabilises something
   (variance of its target, oscillation), and how would a small project
   measure that?
5. **Interacting loops.** Weekly, monthly, regression, blind-spot, cost and
   outcome loops act on overlapping budgets and signals. Can they oscillate or
   fight each other (cost loop throttles the loop that would fix the cost
   driver; R4 starves process work exactly when losses cause product delay)?
   Where is hysteresis or a precedence order needed?
6. **Budget rule R1 on small, noisy data.** Is `clamp(5 %, 20 %, k × loss
   share)` robust when weekly data are sparse and missing classes are not
   zero? Smoothing, hysteresis, minimum evidence?
7. **Trust measure.** Is prognosis hit rate per actor a valid basis for
   widening or narrowing the steward's autonomy, or is it gameable through
   timid prognoses?
8. **Model-agnostic independence (§6.7).** Does "another session without the
   proposer's history" give enough independence when proposer and reviewer
   may be the same model? What is the minimum that must hold?
9. **Complexity.** Is P1–P4 still too much for v2.68? What would you cut so
   that the owner gets value in week one?

## Deliverable

A PR review on #216 with a verdict (`approve`, `revise`, `block`). Group
findings by root cause, give severity, a concrete failure scenario and a fix
for each. Mark what you executed versus what is a design scenario. Answer the
nine questions.

## Background material (new in round 2; verify before relying on it)

- **Goodhart variants.** Manheim and Garrabrant, *Categorizing Variants of
  Goodhart's Law* (2018), arXiv:1803.04585. Separates regressional, extremal,
  causal and adversarial Goodhart; useful for question 2.
- **Double-loop learning.** Argyris, *Double Loop Learning in Organizations*,
  Harvard Business Review (1977). First loop corrects actions against fixed
  norms; second loop questions the norms. Revision 2 maps the weekly loop to
  the first and the monthly loop to the second.
- **Requisite variety.** Ashby, *An Introduction to Cybernetics* (1956). A
  regulator needs at least as much variety as the disturbances it must
  absorb; relevant to whether more loops help and where they stop helping.
- **Leverage points.** Meadows, *Leverage Points: Places to Intervene in a
  System* (1999). Ranks interventions from parameters (weak) to rules, goals
  and paradigms (strong); relevant to which layer may change what (§7).
- **Delivery metrics.** DORA, *Accelerate State of DevOps* reports (2024,
  2025); Forsgren et al., *The SPACE of Developer Productivity*, ACM Queue
  (2021). Warn against single productivity metrics; relevant to the loss
  ledger and the outcome signals.
- **Round-1 material** (graph engineering survey, AFlow, Meta-/Self-Harness,
  Anthropic engineering publications, METR) stays in the round-1 brief.

## Known limits the authors already state

- Live A/B evidence for small effects is out of reach per project; revision 2
  relies on event rates and a single final analysis.
- Outcome signal O1 depends on projects using native sub-issues or a
  configured fallback.
- O3 operations data depend on a project-owned host script.
- The registers and loops are not built yet; everything in §4–§8 is design.
