# SP21 — Dependency & sequencing (blocked_by + cycle gate + ready order)

## Problem

The template has no way to express that one story depends on another. With a
backlog of any size you cannot answer "what is safe to start now?", and nothing
stops a plan building things in the wrong order or a `done` story that secretly
depends on unfinished work. The mature adopter renders "Blocked by #N" into
issues and computes a ready-to-start order; the template has neither.

## Decision

Extend the **feature-registry** owner (no new module, no parallel gate): stories
gain a machine-readable `blocked_by` list, the registry gate validates it, and a
read-only tool computes the ready-to-start order.

### 1. `blocked_by` field (feature-registry schema)

A story may carry `"blocked_by": ["STORY-0002", ...]` — the stories that must
land first. Absent or `[]` means no dependency. Added to the example story as
`[]` (gate-clean).

### 2. Gate checks in `check_feature_registry.py` (the owner)

**Hard (CI fails):**
- `blocked_by` present but not a list of `STORY-NNNN` strings (malformed).
- A `blocked_by` ref that resolves to no existing story id (dangling — the
  dependency points at nothing, so ordering is a lie).
- A story listing **itself** in `blocked_by`.
- A **dependency cycle** (A blocked_by B blocked_by … blocked_by A) — an
  unbuildable order, reported with the cycle path.

**Best-effort (advisory note):**
- A `done` story with a `blocked_by` that is not itself `done` — a likely
  integrity slip ("finished, but its prerequisite is not"), noted not blocked,
  because status can legitimately move out of order during a migration.

Dangling and cycle detection need the whole story set, so they run in the
cross-story `check()` pass (per-story validation stays in `_check_story`).

### 3. `story_order.py` — read-only ready-to-start tool

A read-only tool (never a gate, not in CI — same posture as the KPI cockpit)
that prints, from the current registry:
- **Ready now:** not-`done` stories whose every `blocked_by` is `done` (or which
  have none) — the safe-to-start set.
- **Blocked:** not-`done` stories still waiting, each with the unfinished
  blockers it waits on.
- A topological order of the not-`done` stories.
It reports a cycle plainly if one exists (the gate is what *fails* on cycles;
the tool just refuses to order them).

### 4. Optional GitHub rendering (documented, not built)

"Blocked by #N" in the issue body is a GitHub-specific convenience that needs a
write token; documented as an optional recipe in the `github-issues` module doc,
not built into a gate (portability + no faked capability).

## Alternatives considered

- **A separate dependency gate/module**: rejected — the feature-registry gate
  already owns story structure and reference resolution (ADR, tests); dependency
  refs are the same class. One owner.
- **Store deps in issues, not the registry**: rejected — that couples the core
  sequencing concept to GitHub. The registry is the portable SSOT; the issue
  render is the optional projection.
- **Status-consistency as hard**: rejected for this slice — a `done`-with-
  unfinished-blocker is a *soft* note here; hard status↔status enforcement is
  the traceability-closure slice's concern (kept separate, one behavior per
  slice).

## Non-goals

- No GitHub write / "Blocked by #N" rendering (optional recipe only).
- No hard status-consistency enforcement (soft note only; that is a later
  slice).

## Anchor Delta

Feature-registry schema gains `blocked_by`; its gate gains dependency
validation; a new read-only `story_order.py` ships with the module. No core rule
change, no kernel change.

## Feature Registry Trace

Process-template self-change; template tests are acceptance. New/extended
`test_feature_registry.py`: malformed blocked_by → hard; dangling ref → hard;
self-ref → hard; cycle → hard; valid deps → clean; done-with-unfinished-blocker
→ soft. New `test_story_order.py`: ready/blocked/order output; cycle handled.
