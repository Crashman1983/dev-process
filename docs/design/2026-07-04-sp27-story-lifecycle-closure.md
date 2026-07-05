# SP27 — Story-lifecycle closure (C traceability, E DoR/DoD, F discovered-work)

## Why

Three small backlog items that close gaps in the story lifecycle, so nothing
falls through the cracks between "a story exists" and "a story is done and
traceable". All three are cheap; only one adds enforcement.

## C — Traceability closure (the one gate change)

Today the `github-issues` gate emits a **soft** note when a tracked
(`in-progress`/`done`) story has no `issue` link. A **done** story with no issue
is a real closure hole — completed work that traces to nothing. Harden it:

- **Hard:** a `done` story with no `issue` — a finished story must be traceable.
- **Soft (unchanged):** an `in-progress` story with no `issue` — still active,
  the issue may be forthcoming (SP20 already enforces issue-before-code on the
  *plan*, so active work is covered there).

The other half of "closure" the backlog imagined — *issue state matches story
status* (issue closed ⇔ story done) — is already the **github-master** gate's
job, offline against the snapshot (`done` ⇒ issue `closed`). For non-github-master
users it stays best-effort via `gh` (existence check). We do **not** duplicate it
here. This is the **2nd** extension of `check_issues` (after SP20's plan-issue
check) — still increment per Rule 5; the 3rd will need the explicit decision.

## E — DoR / DoD checklist (doc-only, aggregation)

A "Definition of Ready / Done" section in the feature-registry module doc. It is
a **legibility view**, not new enforcement — each item points at the owner that
already enforces it, so a contributor sees the whole bar in one place:

- **Ready:** a real user story (`story`), gradeable acceptance (`acceptance`),
  an approach recorded (the plan), and — Tier 3+ — an issue (SP20).
- **Done:** every AC maps a test (`tests` + mandatory-rules "tests prove
  acceptance"); the independent review ran and attested (SP19); a `done` story
  carries a test (registry gate) and an issue (C, above); docs/registry updated.

Stated honestly as an aggregation of existing gates, not a new checkbox nobody
checks.

## F — Discovered-work inbox (doc/convention)

Work discovered mid-flow (a bug you spot while building something else) must be
*captured, not scope-crept into the current change*. A lightweight
`.process-work/inbox.md` holds one line per discovery; triage turns each into a
tracked issue (`new_issue.sh`) or discards it. Documented in
`journal-state-plans.md`. No gate — it is discipline, and a gate on "did you
capture everything" is not mechanically decidable (stated so).

## Non-goals

- No network state-match check in `check_issues` (github-master owns it offline;
  gh-state is best-effort and out of scope here).
- No gate for E or F — they are a view and a convention, honestly labelled.

## Anchor Delta

`check_issues.py`: done-without-issue soft → hard. `feature-registry.md`:
DoR/DoD section. `journal-state-plans.md`: discovered-work inbox section. No core
rule change.

## Feature Registry Trace

Template self-change; template tests are acceptance. New tests:
`test_github_issues.py` (done-without-issue hard; in-progress-without-issue still
soft); doc-content tests for the DoR/DoD and inbox sections.
