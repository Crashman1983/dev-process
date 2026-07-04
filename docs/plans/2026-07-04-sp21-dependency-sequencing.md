# SP21 Plan — Dependency & sequencing

Design: `docs/design/2026-07-04-sp21-dependency-sequencing.md`. Tier 3 (module
gate behavior + new tool; opt-in). Route: design → plan → execute → independent
review → merge → tag. Own attestation: `single-family`.

tier: 3
issue-waived: dev-process is the process template itself; its backlog is not run on GitHub Issues.

## Anchor Delta

feature-registry schema gains `blocked_by`; its gate gains dependency
validation; new read-only `story_order.py`. No core rule change.

## Steps (atomic commits)

### Commit 1 — blocked_by validation + dependency gate + example + tests
- `check_feature_registry.py`:
  - `_check_story`: validate `blocked_by` is a list of `STORY-NNNN` (hard on
    malformed); collect into a passed-in `graph` dict when the id is valid.
  - `check()`: after the per-story loop, run dependency checks over the graph —
    dangling ref → hard; self-ref → hard; cycle (DFS, dedup by node-set) → hard;
    `done` story with a non-`done` blocker → soft.
- `STORY-0001.example.json.jinja`: add `"blocked_by": []`.
- `tests/test_feature_registry.py`: malformed → hard; dangling → hard; self →
  hard; 2-cycle and 3-cycle → hard (message names the cycle); valid chain →
  clean; done-with-unfinished-blocker → soft (exit 0 + note).

### Commit 2 — story_order.py read-only tool + tests
- New `template/scripts/process/{% if modules.feature_registry %}story_order.py{% endif %}.jinja`
  (read-only, not wired into gate_runner): prints Ready-now / Blocked-with-
  blockers / topological order; reports a cycle plainly. Reuses the gate's
  parser where practical (import or a small shared read).
- `tests/test_story_order.py`: ready set correct; blocked lists its blockers;
  a done blocker unblocks its dependents; cycle is reported not ordered.

### Commit 3 — docs + release
- feature-registry module doc: document `blocked_by`, the gate rules, and
  `story_order.py`. github-issues doc: optional "Blocked by #N" render recipe
  (documented, not built).
- `pyproject.toml`/`uv.lock`/`docs/SBOM.md` 1.8.0 → 1.9.0 (new field + tool =
  minor). README status + roadmap row SP21.

## Verification
- Full suite green + ruff clean before each commit.
- Render a demo with feature_registry on; craft STORY files with a valid chain →
  gate clean, tool orders them; add a cycle → gate hard, tool reports it; dangle
  a ref → gate hard.
- Diff bundle; independent adversarial review (fresh agent, single-family) —
  focus: cycle-detection correctness (misses/false-positives, self-loops,
  disconnected components), dangling detection, false-red on legit deps, tool
  read-only, one-owner (extends registry gate, no parallel path), neutrality,
  version.
- Fix findings, ff-merge, release-tag v1.9.0.

## Feature Registry Trace
Template self-change; template tests are acceptance. Extended
`test_feature_registry.py`; new `test_story_order.py`; module-doc test.
