audit: rendering-module-integrity
work: PR #23 (v1.24.0 branch state)
campaign: 2026-07-08-functional-audit
campaign-issue: #24
issue: publish-waived: fixed in PR #23, bundled into campaign #24

## Prompt

```
Rendering & module-integrity auditor. Prove or break clean rendering across
many module combinations by execution: render 20 combinations, run gate_runner
on each, scan the whole tree for jinja leaks and empty-path-segment collisions,
and check the four SSOTs (copier.yml, conftest, BOOTSTRAP, gate_runner) for
mutual consistency. (Model: Opus. Full prompt archived in session.)
```

## Result

3 confirmed defects; all other combinations rendered leak-free and gated exit 0.
Verified present-when-on / absent-when-off / not-misplaced for all module docs
and gate scripts, plus all four CI variants.

## Findings

FINDING sev=major action=fix issue=- sbom.md names concrete `docs/process/sbom-policy.json` in backticks — doc-drift gate reads it as a broken reference, failing a fresh sbom+doc_drift render (exit 1) before any work; now points at the shipped example
FINDING sev=minor action=fix issue=- ARCHITECTURE-OVERVIEW.md lacked the .jinja suffix — copier ships it byte-for-byte, so a raw `{{ project_name }}` token lands in the delivered title; renamed to add .jinja
FINDING sev=minor action=fix issue=- BOOTSTRAP headless module dicts omit `github_master` — the documented command cannot enable it (silently unselectable); added to both dicts and the heuristic
