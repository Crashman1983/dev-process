# Design: reaudit + public-readiness (SP11)

**Date:** 2026-07-02
**Status:** approved (scope: confirmed findings of the 2026-07-02 re-audit —
an adversarial pass over the new telemetry module plus a personal-data and
public-readiness sweep before the repository goes public)
**Slice:** close the telemetry false-greens the re-audit confirmed, make the
remaining failure modes speak, and remove personal data from the tree.

## Gap

SP10 shipped the telemetry module; the re-audit attacked it the way SP9
attacked the earlier gates and found the same defect class again: paths where
the gate reports green while telemetry is silently lost or the one
non-negotiable suite threshold reads PASS vacuously. Separately, going public
requires that no personal data ships and that a stranger can actually use the
repo (license, reproducible SBOM, an English entry point).

## Decision 1 — close the telemetry false-greens

- **Suite shape alignment (danger direction):** a `grader_verdict` whose kind
  or key set differs from `ground_truth` produced zero comparisons yet counted
  as graded — threshold 2 ("0 false-pass in the danger direction", the
  non-negotiable one) printed PASS on exactly the event it exists to catch.
  Now: the gate hard-fails the shape mismatch, and the cockpit independently
  reports threshold 2 as NOT EVALUABLE while any danger-direction entry went
  uncompared. Belt and suspenders, because this threshold gates layer removal.
- **Filter derived from the grammar:** the lint filter required a literal
  `"GRADE "` while grammar and cockpit accept any whitespace — `GRADE\t…`
  bypassed the gate and fed the cockpit out-of-enum values. The intent
  predicate now uses the grammar's own prefix; filter and parser can no longer
  disagree.
- **Unicode digits:** `round=²` passed `str.isdigit()` in the gate and crashed
  every cockpit reader at `int()`. The gate requires ASCII digits; the cockpit
  gets one safe `_round_int` owner used everywhere.
- **Typo'd root:** `check_telemetry.py /nonexistent` globbed nothing and
  reported OK forever; a non-directory root is now a hard failure.

## Decision 2 — failure modes speak, quotations are invisible

Directories named `*.md`/`*.json`, unreadable files, non-object case JSON,
malformed `--issues-json`, bad timestamps, non-UTF-8 journals, and running
`cfr` outside a git repo all produced raw tracebacks in gate or cockpit; each
now yields a one-line diagnostic (gate: hard entry; cockpit: skip note,
exit 0). GRADE lines inside ```-fenced blocks are quotations, not telemetry —
gate and cockpit now share one fence-skipping reader, and the module doc names
the two deliberate non-enforcements (per-round uniqueness, fenced quotes).
Episode source attribution sorts by round instead of file order.

## Decision 3 — personal data out of the tree, history surfaced

Design/plan prose no longer names a person (attributions became "the
maintainer"); the neutrality guard lists in tests/plans stay — they are the
enforcement that keeps such terms out of rendered artifacts, not leaks. The
committer email in the git history and the license choice are maintainer
decisions and are surfaced, not decided here.

## Decision 4 — public readers get a working front door

- `uv.lock` is committed: the SBOM's resolved-package table claimed it as its
  source while `.gitignore` excluded it — an unreproducible SBOM that drifts
  silently on every fresh resolve.
- Upstream CI gets `permissions: contents: read` and stops double-running PR
  pushes (the rendered process-gates workflow already knew this; the upstream
  repo now follows its own pattern). The release-tag workflow validates the
  tag input before passing it to git.
- README opens with an English signpost (what this is, the install command,
  where the English docs live) and an origin note: Kenni is the private
  project this process was generalized from; Kenni-internal references in
  docs/design and docs/plans are history and not publicly resolvable.

## Out of scope

License file (choice is the maintainer's; without it the repo must not go
public), history rewrite for the committer email (destructive, maintainer
decision), SHA-pinning of upstream actions (noted, tag-pinning kept), the
near-miss shapes `grade …`/`GRADE: …` (in-spec silence, documented grammar is
exact), a duplicate-line uniqueness gate (convention, now stated as such).
