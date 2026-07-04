# SP23 — Parent/child decomposition (sub-issues) on the inverted direction

## Problem / decision

Stories can be sequenced (`blocked_by`, SP21) but not **decomposed**: an epic
into its tasks. GitHub models this with **sub-issues**. In `github_master` mode
sub-issues are the master; the registry mirrors them. SP23 adds a single
`parent` field, validates the hierarchy in the registry gate (reusing the SP21
cycle machinery), enforces the mirror via the SP22 `parent` snapshot slot, and
closes the SP22-precheck gaps.

Decomposition is **orthogonal to sequencing**: `parent` is a tree (one parent
per child); `blocked_by` is a DAG. They are validated separately.

## The `parent` field

A story may carry `"parent": "STORY-NNNN"` — the epic/parent it decomposes. A
child body carries only *its own* delta (its title, story, acceptance); it
**references** the parent, it does not copy the parent's context. That
one-owner-of-shared-context discipline is the anti-duplication mechanism — the
registry model makes the right thing the easy thing.

## Feature-registry gate (extends the SP21 owner)

**Hard:**
- `parent` not a `STORY-NNNN` string (malformed).
- `parent` refs a non-existent story (dangling).
- a story that is its own parent.
- a **parent cycle** (A parent B parent A) — a tree may not loop. Reuses the
  SP21 DFS, over the parent edges (a second, independent graph).

**Best-effort (note):**
- a **parent marked `done` while a child is not `done`** — an epic cannot be
  finished before its parts.
- a child whose `title` or `story` is **byte-identical** to its parent's — the
  child should carry its delta, not copy the parent. (Only verbatim duplication
  is mechanically detectable; semantic duplication stays review discipline —
  stated honestly, not overclaimed.)

**Epic ↔ done-test rule (the SP22-precheck gap), resolved:**
The rule "`status: done` requires ≥1 test" moves to a parent-aware pass. A story
that **is a parent** (has ≥1 child) and is `done` without its own test is a
**note**, not a hard fail — its acceptance is proven by its children's tests. A
non-parent `done` story with no test stays **hard**. This exempts pure-container
epics from a false-red without weakening the rule for real leaf stories.

## github-master gate (extends SP22)

The SP22 snapshot already carries a nullable `parent` slot. SP23 adds the drift
check: when the snapshot entry's `parent` is non-null, the registry `parent`
must equal it (GitHub sub-issues are master). `null` ⇒ skip, exactly like
`blocked_by`. Symmetric, hermetic, offline.

`gh_sync.py` populates `parent` **best-effort** where the sub-issues API is
reachable; where it is not, it writes `null` and says so. The registry `parent`
field + the gate are the solid, tested core; actual sub-issue *population* is
best-effort and never faked (same posture as every other network touch).

## story_order.py

Gains a light **Hierarchy** section: each epic (a story that is a parent) with
its children indented. Sequencing output is unchanged — `parent` must **not**
feed the ready/blocked ordering (decomposition ≠ sequencing).

## Optional: sub-issue render

Documented recipe (github-issues / github-master docs): link a child issue to
its parent via GitHub's sub-issue relationship, driven from `parent`. One-way
projection from the master data, best-effort, not a gate, needs a write token.

## Out of scope (stated, not hidden)

- **Mixed parent+`blocked_by` cycles** (e.g. A parent B, B blocked_by A) are not
  detected — pure parent-cycles and pure blocked_by-cycles each are, but a cycle
  spanning both edge types is a rare, subtle case deferred rather than
  half-solved.
- No `type: epic` discriminator — "is a parent" is derived from being referenced
  as someone's `parent`, which needs no new field.

## Anchor Delta

feature-registry schema gains `parent`; its gate gains parent validation +
parent-aware done-test + dup/consistency notes; github-master gains parent
drift; story_order gains a hierarchy view; docs updated. No core rule change.

## Feature Registry Trace

Template self-change; template tests are acceptance. Extended
`test_feature_registry.py` (parent malformed/dangling/self/cycle hard;
parent-done-before-child soft; verbatim-dup soft; epic-done-without-test soft
while leaf stays hard), `test_github_master.py` (parent drift), `test_story_order.py`
(hierarchy view).
