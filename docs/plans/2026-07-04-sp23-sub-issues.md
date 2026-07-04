# SP23 Plan — Parent/child decomposition (sub-issues)

Design: `docs/design/2026-07-04-sp23-sub-issues.md`. Tier 3 (registry schema +
gate behavior, opt-in surfaces). Route: design → plan → execute → independent
review → merge → tag. Own attestation: `single-family`.

tier: 3
issue-waived: dev-process is the process template itself; its backlog is not run on GitHub Issues.

## Anchor Delta

feature-registry schema gains `parent`; its gate gains parent validation +
parent-aware done-test + dup/consistency notes (shared cycle DFS extracted, one
owner); github-master drift-checks `parent`; story_order gains a hierarchy view.
No core rule change.

## Steps (atomic commits)

### Commit 1 — parent field + gate + tool + github-master drift + tests
- `check_feature_registry.py`: extract `_cycles(adj, label)` (shared by
  blocked_by and parent); add `parent` validation + `_hierarchy_checks`
  (dangling/self/cycle hard; parent-done-before-child + verbatim-dup soft);
  move the done-test rule into the parent-aware pass (epic soft, leaf hard).
- `STORY-0001.example.json`: add `"parent": null`.
- `check_github_master.py`: add `parent` to the mirror + a drift check
  (symmetric with blocked_by; null-skip).
- `story_order.py`: add an epic→children hierarchy section (sequencing
  unchanged).
- Tests across `test_feature_registry.py`, `test_github_master.py`,
  `test_story_order.py`.

### Commit 2 — docs
- feature-registry module doc: `parent` field + the decomposition rules.
- github-master doc: `parent` drift + the slot note.

### Commit 3 — release
- `pyproject.toml`/`uv.lock`/`docs/SBOM.md` 1.10.0 → 1.11.0. README status +
  roadmap row SP23.

## Verification
- Full suite green + ruff clean (402 passed).
- Independent adversarial review (fresh agent, single-family) — focus: parent
  cycle detection (shared `_cycles` correctness for the single-edge parent
  graph), the moved done-test rule doesn't regress leaf enforcement, epic
  exemption is sound, no false-green, github-master parent drift, neutrality,
  version.
- Fix findings, ff-merge, release-tag v1.11.0.

## Feature Registry Trace
Template self-change; template tests are acceptance. Extended
`test_feature_registry.py`, `test_github_master.py`, `test_story_order.py`.
