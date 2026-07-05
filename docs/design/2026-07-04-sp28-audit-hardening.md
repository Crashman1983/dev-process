# SP28 — Audit hardening (6-audit synthesis)

## Provenance

Six independent adversarial audits (3 personas — architect / CI-CD / QA — × 2
models — Opus 4.8 + Sonnet 5), read-only over v1.14.0. Five verdicts positive
(SOUND/SOUND/PROVEN/SOUND/SOUND); **Sonnet/QA dissented (NOT-PROVEN)** and, by
direct probing, found two live bugs the green suite hid — the value of model
diversity: Opus/QA rated PROVEN and missed both. Both bugs were re-verified here
by execution before fixing.

## P0 — verified live bugs (fixed)

1. **Telemetry false-positive.** `_intended_grade` linted any line starting
   `GRADE ` that contained *any* `word=` anywhere, so prose like
   `GRADE totals for Q3 revenue=120k` hard-failed the gate (verified: exit 1).
   Fix: require the **first token** after `GRADE` to be `key=value`
   (`GRADE\s+\S+=`) — real GRADE lines (and typo'd-key ones) still lint; prose
   with a later `=` does not. Tests added both directions.
2. **Security-floor silent skip.** A non-UTF-8 / unreadable file was skipped
   with **no note** (unlike the git-absent path), and `test_binary_file_skipped`
   enshrined the silent `OK`. A grep gate silently passing an unscannable file is
   false confidence. Fix: disclose skipped files as an advisory note (stays
   non-hard — can't grep binary — but is now visible). Test updated to assert the
   disclosure.

## P1 — consensus / real findings

3. **Status-vocabulary fail-open** (both architects; Sonnet MAJOR).
   `check_github_master.STATUS_STATE.get(status)` silently skips the state-drift
   check for a status not in its map — so a status added only to
   `check_feature_registry.STATUSES` stops being drift-checked, no test catches
   it. The gates can't import each other (module isolation), so the guard is a
   **cross-gate consistency test**: assert `STATUSES ⊆ STATUS_STATE` (and the
   board map's implied statuses) at CI time.
4. **Rendered `process-gates` workflow ships no `permissions:`** (both CI-CD).
   Add `permissions: contents: read` to the GitHub workflow.
5. **`release-tag.yml` `sha` unvalidated** (both CI-CD) — git option-injection
   (`sha=--delete`). Add a `^[0-9a-f]{7,40}$` guard.
6. **`github_master` doc overclaim** (Opus/architect). The design says `gh_sync`
   "materializes/updates the registry mirror"; it writes only the snapshot. No
   registry write-back ships. Correct the docs to the truth (materialization is
   manual / an extension point), so the gate isn't clearing-by-hand-edit against
   a doc that forbids hand edits.
7. **`gh_sync` clobbers `gh_board`** (Opus/architect). `gh_sync` rewrites every
   entry's `board_status`/`parent`/`blocked_by` to `null`, wiping `gh_board`'s
   merged values. Fix: preserve existing non-null slots for entries already in
   the committed snapshot.
8. **Branch protection undocumented** (Sonnet/CI-CD MAJOR). A red gate blocks a
   merge only if the adopter sets it as a required status check — copier can't
   set it, and nothing documents it. Add the operational note to BOOTSTRAP /
   SYSTEM-REQUIREMENTS.
9. **`pip install pyyaml` unpinned** in the rendered gate workflow (Sonnet/CI-CD).
   Pin it (`'pyyaml>=6,<7'`).

## P2 — coverage (add tests, code verified-correct today)

~15–20 of ~90 HARD branches untested, concentrated in defensive/shape guards
(the traceback-guard class the project's own discipline targets). Highest value:
`gate_runner` PyYAML-less diagnostic; telemetry `out_of_scope` verdict; the two
`design-*` bypass exemptions (review + issues); `check_decisions` missing
`## Status`; feature-registry / arch-onboarding / github-master schema-shape and
non-UTF-8 fail-clean branches; a few exit-code-only assertions gain a message.

## Non-goals

- Not building registry write-back for github_master (documented as an extension
  point; correcting the overclaim is the honest fix here).
- Not exhaustively covering every one of the ~90 branches — the highest-value
  fail-clean/bypass/danger-direction ones.

## Anchor Delta

Gate behaviour: telemetry predicate tightened; security-floor discloses skips;
`gh_sync` preserves slots. CI: permissions + sha-guard + pyyaml pin. Docs:
github_master honesty + branch-protection note. New cross-gate status-vocab test.
No core rule change.

## Feature Registry Trace

Template self-change; template tests are acceptance. New/updated tests across
telemetry, security-floor, github-master, the CI/manifest tests, and the P2
coverage additions.
