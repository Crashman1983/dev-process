# Independent review: template verification and cleanup

Date: 2026-10-02. Scope: the three downstream MAJOR findings reported during
Kenni's template upgrade. Baseline commit:
`b528c7c6ea3e644762c7d31c608b4536a7f0e744`.

## Corrections

- Migration classification includes actual project differences in enforcement
  paths, not only differences between pinned release renders.
- Automatic provenance rendering skips tasks, omits trust and uses an existing
  empty settings file in an isolated temporary directory. Operator-driven
  updates retain their explicit trusted execution contract.
- Worktree removal reloads worktree/session records and rechecks the full keep
  policy immediately before calling Git. Tidy and train supply their
  integration bases.

## Independent examination

A separate Codex review session (`/root/independent_review`) examined the
implementation without editing it. No remaining confirmed finding was
reported. Its additional real experiments verified:

- deletion and executable-mode changes to local process scripts during a
  documentation-only upgrade remain migrations;
- local Copier trust cannot permit extension import during automatic
  verification, while an explicit trusted update can import the same fixture;
- an ignored `.env` created after initial clearance prevents removal and
  retains its contents.

This records the independent Codex review, not a Claude review. Claude is not
available in this environment; a required downstream Claude review remains
outstanding.

## Regression evidence and limits

Nine new real Git/Copier regression cases cover classification, tasks,
settings trust, ignored files, live sessions and branch containment. Six
critical cases were also run against the baseline: three migration cases,
task execution, extension trust and stale tidy clearance all failed as
expected. The stale-clearance reproduction removed the disposable fixture
worktree with its newly created ignored `.env`; the corrected path preserves it.

The final keep-policy check and Git deletion are not atomic against external
writers. Writes during or after that check remain a boundary; stop external
writers before cleanup when this matters. The older `finish --tests`
`shell=True` finding is separate and is not changed by these corrections.

Final local validation: 43 focused tests passed; full suite 1,397 passed and
3 skipped. Ruff and whitespace checks passed. Two initial artifact-hygiene
failures came from generated template bytecode; after removing that local
cache, both checks and the complete suite passed.
