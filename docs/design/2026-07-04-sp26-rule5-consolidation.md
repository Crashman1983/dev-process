# SP26 — Rule-5 consolidation (increment vs. rewrite, surfaced)

## Why

The process's own **Rule 5 (patch-count gate)** says: once an element carries ≥2
prior patches, the plan must make an explicit *increment vs. rewrite-the-owner-
layer* decision **before** more patching, and surface it. The holistic arc review
flagged that two gates crossed that line without the decision being stated. This
slice states it — with evidence — and does the one refactor it warrants. This is
consolidation, not a feature: no new behavior, tests unchanged.

## Gate 1 — `check_feature_registry.py` (extended by SP21 blocked_by, SP23 parent)

**Evidence:** 266 lines, already decomposed by concern:
`_story_files`, `_adr_exists`, `_check_story` (per-file), `_cycles` (shared
helper), `_dependency_checks` (SP21), `_hierarchy_checks` (SP23), `check`
(orchestrates). Each extension landed as its *own* named function; the shared
cycle detection has one owner (`_cycles`, reused by both graphs).

**Decision: INCREMENT.** The owner layer is already well-factored — a third
extension (e.g. traceability-closure) slots in as a new `_*_checks` function
called from `check()`, exactly as the last two did. No rewrite, no refactor. The
structure is legible and the pattern is established; rewriting would be churn
without benefit.

## Gate 2 — `check_github_master.py` (SP22 spine, SP23 parent-drift, SP24 board)

**Evidence:** 201 lines, but `check()` is a ~70-line **monolith** — it inlines
three distinct concerns in one body: the per-story *invariants* (issue +
snapshot-entry), *completeness* (snapshot entry ⇒ story), and an 8-branch *drift*
loop (title/status/state/parent/board/blocked_by). `_stories` and `_load_snapshot`
are already separate; `check()` is where the accretion sits.

**Decision: INCREMENT, with a legibility refactor.** Keep one gate (rewriting into
multiple gates would fragment the "registry ↔ snapshot consistency" owner). But
decompose `check()`'s body into named, single-concern helpers — `_invariant_hard`,
`_completeness_hard`, `_drift_hard` — so the next extension has an obvious home and
the drift loop stops growing unbounded. **Behavior-identical**: the same hard
messages in the same order; the 34 github-master tests pass unchanged. This is the
increment done *cleanly* rather than piling a 9th branch into a wall of code.

## Scope / non-goals

- No behavior change to either gate — a pure refactor + the recorded decisions.
- No new gate, no new module, no schema change.
- Not touching the shared `_cycles` or `_load_snapshot` (already single-owner).

## The standing rule going forward

The next extension of **either** gate re-checks this decision. For
`check_feature_registry` a fourth `_*_checks` function is still fine; past that,
reconsider. For `check_github_master`, once the decomposed helpers themselves grow
a third concern each, revisit whether the board/sub-issue drift wants its own
module. Documented here so the clock is visible, not implicit.

## Anchor Delta

No anchor/rule change. This slice *applies* Rule 5; it does not modify it. The
github-master gate's internal structure changes (behavior-identical); the
feature-registry gate is unchanged by explicit decision.

## Feature Registry Trace

Template self-change; the existing github-master tests (unchanged) are the
behavior-identical acceptance — if any assertion moves, the refactor was not
behavior-preserving.
