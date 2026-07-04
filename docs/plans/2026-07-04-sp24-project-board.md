# SP24 Plan — Project board

Design: `docs/design/2026-07-04-sp24-project-board.md`. Tier 3 (extends the
github-master gate + a new best-effort tool; opt-in). Route: design → plan →
execute → independent review → merge → tag. Own attestation: `single-family`.

tier: 3
issue-waived: dev-process is the process template itself; its backlog is not run on GitHub Issues.

## Anchor Delta

`check_github_master.py` gains the board-column consistency check (offline);
new `gh_board.py` best-effort tool; github-master doc gains the mapping + the
two-layer note. No core rule change, no snapshot schema reshape (slot exists).

## Steps (atomic commits)

### Commit 1 — board consistency gate + tool + tests
- `check_github_master.py`: `BOARD_STATUS` mapping; in the drift loop, when
  `board_status` is non-null and the story is not deprecated — unknown column
  hard; column-implied status ≠ story status hard.
- New `gh_board.py` (network, best-effort, not gate-wired): reads a project
  board's Status field into the snapshot `board_status`; `--push` is an explicit
  extension point (no guessed destructive write).
- `tests/test_github_master.py`: unknown column hard; each column↔status
  mismatch hard; Backlog/Ready→proposed, In-progress/Review→in-progress,
  Done→done consistent OK; deprecated exempt; tool present/absent; neutrality.

### Commit 2 — docs
- github-master module doc: the project-board section (mapping table, two
  layers, `--push` extension point).

### Commit 3 — release
- `pyproject.toml`/`uv.lock`/`docs/SBOM.md` 1.11.0 → 1.12.0. README status +
  roadmap row SP24.

## Verification
- Full suite green + ruff clean (410 passed).
- Independent adversarial review (fresh agent, single-family) — focus: the board
  check is hermetic (no network in the gate), no false-green on column↔status,
  the mapping is complete/sound, deprecated exemption, gh_board never guesses a
  write, neutrality, version.
- Fix findings, ff-merge, release-tag v1.12.0.
- Then the holistic process-experienced review over the whole SP22–24 arc.

## Feature Registry Trace
Template self-change; template tests are acceptance. Extended
`test_github_master.py`.
