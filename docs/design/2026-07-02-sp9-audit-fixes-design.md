# Design: audit-fixes (SP9)

**Date:** 2026-07-02
**Status:** approved (scope: the confirmed findings of the 2026-07-02 audit —
three adversarial audit passes over gates, docs, and end-to-end flows)
**Slice:** close every confirmed false-green/bypass, make failure modes speak,
and fix the documentation drift the audit surfaced.

## Gap

The audit found the worst class of defect an enforcement system can have:
paths where enforcement silently disappears while reporting green — plus a
set of raw-traceback failure modes and doc/claim drift. For a process whose
core promise is "holds even when nobody is looking", false-greens are not
negotiable.

## Decision 1 — the manifest is load-bearing; treat its absence as red

`gate_runner` derived "no active gates" equally from "all modules off" (fine)
and "manifest missing / unparseable / no `modules` mapping" (enforcement
silently off). Now: the runner resolves the repo root by walking up to the
directory containing `.copier-answers.yml`; a missing or malformed manifest is
a hard failure with a diagnostic, not an empty gate list. Running from a
subdirectory therefore works instead of false-greening.

## Decision 2 — failure modes speak

- Missing PyYAML: a friendly one-line diagnostic (`pip install pyyaml`) and
  exit 1 instead of a raw ImportError traceback — this also fixes the hooks'
  worst UX (push blocked by a traceback).
- Unclosed ```arch fence: hard fail ("unclosed arch fence") instead of
  "not onboarded yet".
- Malformed YAML / non-UTF-8 inputs: the guard pattern that three gates
  already had is applied to the gates that lacked it (doc-drift,
  feature-registry, github-issues, parity non-mapping, architecture str
  casts). Contract verify commands run with `cwd=root`.
- security-floor notes when zero files were scanned instead of an
  unqualified OK.

## Decision 3 — hooks: correct where cheap, honest where not

- Unborn-branch bypass: `git symbolic-ref --short HEAD` (works before the
  first commit) replaces `rev-parse --abbrev-ref`.
- `core.hooksPath`: the installer now refuses when a custom hooks path is
  configured (machine-wide blast radius, foreign-hook detection would check
  the wrong directory) and tells the user to integrate manually.
- Working-tree gap: the pre-push hook checks the checkout, not the pushed
  commits. A correct fix (temp worktree per push) is disproportionate for a
  local convenience layer; instead the hook and the module doc now state the
  limitation plainly and name CI as the authority. Honest ceiling over
  implied guarantee.

## Decision 4 — doc-drift resolves document-relative links

Refs starting with `./` or `../` resolve against the containing document
(standard markdown behavior, renders fine on GitHub); bare paths keep the
repo-root convention. Correct links stop failing the gate.

## Decision 5 — drift fixes are part of the slice, not follow-ups

Nine rules (not eight) in the README plus the stray "und"; SBOM version rows;
SYSTEM-REQUIREMENTS: github-issues needs PyYAML, venv/PATH hook recipe
corrected; Tier-0 wording ("direct commit" means no plan/review cycle — the
branching rules of commits.md still apply) aligned across kernel, risk-tiers,
workflow; start-here conditions its ARCHITECTURE.md references on the
arch-onboarding module; module docs say `python`, not `uv run`; ADR-0001 ships
as a real file matching the seed index; story example title no longer implies
copy-verbatim-passes; BOOTSTRAP documents the conditional questions
(`github_repo`, `parity_surfaces`), module disabling, and the PyYAML
requirement at the verification step; github-issues doc names its
feature-registry dependency; `_min_copier_version: 9.4.0`; the GitHub workflow
no longer double-runs on PR branches (`push: branches: [main]` +
`pull_request`).

## Out of scope

Windows console encodings, mktemp/BSD portability, case-insensitive branch
names, UTF-16 security-floor evasion (documented in code), github-issues gh
latency — cosmetic tier, tracked in the audit report, not worth their churn
now.
