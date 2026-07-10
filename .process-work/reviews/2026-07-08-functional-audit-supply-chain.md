audit: supply-chain-hermeticity
work: PR #23 (v1.24.0 branch state)
campaign: 2026-07-08-functional-audit
campaign-issue: #24
issue: publish-waived: fixed in PR #23, bundled into campaign #24

## Prompt

```
Supply-chain enforcement & hermeticity auditor. Focus: the sbom license gate and
the reworked pre-push worktree hook. Probe sbom SPDX/type/degradation/coverage
and confirm git+stdlib hermeticity; drive the pre-push hook end-to-end for
false-red/green, cleanup, temp leaks, and side-effects. Judge by execution.
(Model: Opus. Full prompt archived in session.)
```

## Result

Confirmed and refined the sbom findings (OR-expression false-red is "fails
closed"; type-application over-skip is real). Found two new advisory-precision
issues. Cleared the pre-push hook entirely.

## Findings

FINDING sev=major action=fix issue=- sbom SPDX OR-expressions string-matched literally — common dual-licensed deps hard-fail; undocumented; now evaluated + documented
FINDING sev=minor action=fix issue=- sbom type==application exemption applies to any component, not just the root — third-party app dodges the check; now root-only
FINDING sev=minor action=fix issue=- sbom coverage substring match yields false "covered" (a short dep name inside an unrelated component); now exact normalized-name compare
FINDING sev=minor action=fix issue=- sbom default manifest_paths (`**/package.json`, …) never match a root-level manifest — coverage no-ops on the common layout; bare entries added
FINDING sev=nit action=accept issue=- sbom git-unavailable is an advisory pass with a note (not a hard fail) — by design, consistent with the other gates

## Negative space (verified correct, no change)

Pre-push hook: false-green defeated (dirty tree ignored), false-red defeated (bad
committed tip blocked), cleanup on every path (gate failure, worktree-add
failure, success, multi-ref, TMPDIR unset), no worktree/temp leak, path-with-
spaces, no stash/HEAD move. sbom hermeticity: git + stdlib only, no network,
honest degradation matrix, SKIP_SBOM bypass.
