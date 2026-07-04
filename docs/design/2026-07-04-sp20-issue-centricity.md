# SP20 — Issue-centricity (issue-before-code + claim discipline)

## Problem

GitHub Issues are used far less intensively than in the mature adopter (Kenni),
where "Tier 2+ requires a GitHub issue before any code" plus a claim/heartbeat
protocol keeps the backlog operative. The template's `github-issues` module
ships EARS templates, a seed helper, a prose claim workflow, and a gate — but
the gate only validates the `issue` *format* on feature-registry stories and
notes a missing link. Nothing enforces that Tier 3+ work is *tracked by an
issue before code is written*. The discipline is documented, not driven.

## What is enforceable, honestly

- **Can:** require that an **active** plan declaring Tier 3+ carries a valid
  `issue:` link (or a named waiver) — issue-before-code, checked at the plan
  artifact that SP19 already gave a machine-readable `tier:` field.
- **Cannot / should not:** enforce claim comments or a 90-minute heartbeat —
  those are cross-repo, wall-clock, social conventions a language-agnostic CI
  gate cannot see. They stay documented discipline (tightened to match the
  mature adopter), not a faked gate.
- **Portability:** all of this lives under the opt-in `github-issues` module.
  A project that does not run its backlog on GitHub is unaffected.

## Decision

### 1. `check_issues.py` gains issue-before-code enforcement (module gate)

The `github-issues` gate already owns issue-ref parsing (`parse_issue_ref`) and
runs only when the module is enabled. Extend the *same owner* (no new gate, no
duplication):

- For each **active** plan (`.process-work/plans/*.md`, excluding `archive/`
  and `design-*.md`) that declares `tier: N` with **N ≥ 3**:
  - **Hard:** neither a valid `issue:` line nor an `issue-waived: <reason>`
    line → fail (issue-before-code). A `tier: N` inside a fenced example is a
    quotation, ignored (same fence-skip discipline as the review gate).
  - **Hard:** an `issue:` line whose ref is malformed (reuse `parse_issue_ref`).
  - **Soft / not enforced:** a plan without a `tier:` line — opt-in by tier
    declaration, never a retroactive false-red.
- Timing is deliberately the mirror of the review gate: issues are checked on
  **active** plans (work is starting — the issue should already exist), reviews
  on **archived** plans (work is finishing). No overlap.

The existing story-`issue` checks are unchanged. The gate is no longer inert
without `feature-registry`: plan enforcement runs whenever the module is on.

### 2. Claim / heartbeat discipline tightened (module doc)

`github-issues.md` claim workflow gains the fields a claim comment must carry
(agent · branch/worktree · scope · next-update) and a heartbeat cadence for
long-running work, matching the mature adopter — as convention, explicitly not
gated (and said so, so no one mistakes it for enforcement).

### 3. `issue:` on plans documented (core doc)

`journal-state-plans.md` already documents `tier:` and is where the review gate
reads `issue:`. Add that a plan may carry an `issue:` link, and that under the
`github-issues` module a Tier 3+ plan needs it before code (or a named
`issue-waived:`).

## Why the active-plan artifact is the right hook

Issue-before-code is a *start-of-work* rule, so it is checked where work starts:
the active plan. That plan already declares its tier (SP19), so the check is a
few lines on an artifact that exists, with the same opt-in-by-tier and
named-waiver honesty as the review gate — one consistent mechanism, not a
second bespoke one.

## Alternatives considered

- **A separate `issue-before-code` gate**: rejected — the `github-issues`
  module already owns issue refs; a second gate splits ownership and doubles
  wiring.
- **Enforce in core (mandatory-rules / risk-tiers)**: rejected — issue-tracking
  is a module choice, not a universal rule; core must not hard-depend on a
  tracker. The rule lives in the module doc and the module gate.
- **Gate the claim/heartbeat**: rejected — not machine-checkable; a faked gate
  would be false comfort. Kept as tightened convention.

## Non-goals

- No enforcement of claim comments or heartbeat cadence (social, not gate-able).
- No change to the story-`issue` format checks or existence best-effort.

## Anchor Delta

`github-issues.md` gains issue-before-code + tightened claim discipline;
`journal-state-plans.md` documents the plan `issue:` field. No new gate, no core
rule change, no kernel change.

## Feature Registry Trace

Process-template self-change; template tests are acceptance. New/extended
`test_issues.py`: active Tier-3+ plan without issue → hard; with valid issue →
clean; malformed plan issue → hard; `issue-waived:` clears; no-tier plan → not
enforced; fenced `tier:`/`issue:` ignored; archived plan not issue-checked;
module-off → gate inert.
