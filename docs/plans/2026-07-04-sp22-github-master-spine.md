# SP22 Plan — github-master spine

Design: `docs/design/2026-07-04-sp22-github-master-spine.md`. Tier 4 (inverts the
SSOT direction as an opt-in adapter; new module). Route: design → plan → execute
→ independent review → merge → tag. Own attestation: `single-family`.

tier: 4
issue-waived: dev-process is the process template itself; its backlog is not run on GitHub Issues.

## Anchor Delta

New opt-in `github_master` module: gate + sync tool + doc + snapshot schema +
gate-runner wiring + copier answer. Registry-master default untouched.

## Steps (atomic commits)

### Commit 1 — module wiring + gate skeleton + snapshot schema
- `copier.yml`: add `github_master: false` to modules default.
- `tests/conftest.py`: add `github_master` key to the full modules dict.
- `gate_runner.py.jinja`: register `"github-master": ("github_master", [... check_github_master.py ...])`.
- New `template/scripts/process/{% if modules.github_master %}check_github_master.py{% endif %}.jinja`
  (module-gated). Implements the hermetic checks (snapshot schema, missing-issue
  invariant, both-direction join, drift on title/status/blocked_by, status↔state
  map). Pure stdlib (+ read of copier answers for mode is not needed — the gate
  only runs when the module is on, which the runner already decides).
- `tests/test_github_master.py`: on/off wiring (`--list`); snapshot-missing soft;
  malformed snapshot hard; missing-issue invariant hard; story-without-snapshot
  hard; snapshot-without-story hard; drift (title/status/blocked_by) hard;
  status↔state mapping (done↔closed etc.); clean case OK.

### Commit 2 — sync tool + module doc + example snapshot
- New `template/scripts/process/{% if modules.github_master %}gh_sync.py{% endif %}`
  (best-effort, `gh`-based; writes the snapshot + updates the registry mirror
  marker). Not gate-wired; thin; documents its network posture.
- New `template/docs/process/{% if modules.github_master %}modules{% endif %}/github-master.md`:
  the two-layer model (sync vs gate), the snapshot schema, the master invariants,
  the status↔state map, and that the registry-master default is the alternative.
- `.process-work` seed: ship a `github-snapshot.example.json` (inert, skipped by
  the gate) as a shape reference.
- Tests: module doc present when on / absent when off; neutrality; example
  snapshot inert.

### Commit 3 — release
- `pyproject.toml`/`uv.lock`/`docs/SBOM.md` 1.9.0 → 1.10.0 (new module = minor).
  README status + roadmap row SP22 + module list.

## Verification
- Full suite green + ruff clean before each commit.
- Render a demo with `github_master` on; craft a snapshot + matching stories →
  gate OK; introduce a title drift → hard; drop an issue ref → hard; module off →
  gate absent from `--list`, no new enforcement.
- Diff bundle; independent adversarial review (fresh agent, single-family) —
  focus: hermeticity (no network in the gate), the missing-issue invariant is
  sound, drift detection has no false-green, status↔state map correct,
  default-untouched, one-owner vs check_issues/check_feature_registry,
  neutrality, version.
- Fix findings, ff-merge, release-tag v1.10.0.

## Feature Registry Trace
Template self-change; template tests are acceptance. New `test_github_master.py`.
