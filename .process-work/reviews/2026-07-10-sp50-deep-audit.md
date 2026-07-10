review: SP50 deep audit (post-KISS-cleanup state, v1.33.0-v1.34.0 span)
work: PR #26
issue: publish-waived: all findings fixed in-PR before merge (this report is the record)

## Prompt

```
Four independent auditors with execution mandates over the cleaned state
(443c509..HEAD = SP48 telemetry honest ceiling + SP49 KISS cleanup):
1. adversarial-by-execution (attack the new import wiring, changed regexes,
   sbom/gh_board fixes; defects proven by reproduced command+output);
2. process-coherence (full-span diff vs rendered output; stale-token sweep);
3. fresh-eyes adopter (follow README -> BOOTSTRAP -> start-here verbatim as a
   solo dev to the first reviewed change; judge every gate message);
4. robustness/input-attack (gates as attack surface: hostile JSON/markdown/
   filesystem shapes, regex DoS, shellcheck).
(Model: Fable. Full prompts archived in session.)
```

## Result

1 blocker, 4 major, 8 minor, 3 nit — all fixed in the same PR (v1.34.1)
except three accepted (tag lag: resolved by the merge+tag procedure itself;
binary PRODUCT.md labeled "missing" in the read-only bundle; hooks-order
ceremony kept with reordered steps). The adopter verdict was positive: a solo
dev reaches a green gate run and a first fully reviewed Tier 2 change without
outside help, and the negative-path messages teach the process. The new
sibling-import wiring held under attack (decoys, PYTHONPATH pollution, every
legal module combination, subdir cwd) with one shim gap (bundle) fixed.

## Findings

FINDING sev=blocker action=fix issue=- fence tracking was length-insensitive: a ``` run inside a ````-fence closed it early, so a QUOTED review-waived:/issue-waived:/tier: example leaked out and cleared the review and issue gates (false-green, reproduced both); also flagged a quoted REVIEW line as malformed (false-red). Fixed CommonMark-style (closing run of the same char, >= opening length) in check_review's shared _unfenced/parse_review_lines; check_issues and check_product_frame inherit via import
FINDING sev=major action=fix issue=- SP49 regression: ISSUE_DECL's \S+ capture let ANY token after issue: act as a clearing work-id — issue: v2.0 was cleared by REVIEW work=0 (digit-tail), and issue: none twice let ONE review clear TWO plans. Work-ids now require a bare number or a parseable ref; the ref grammar (parse_issue_ref, _BARE/_CROSS/_URL) moved to check_review (core owner), check_issues imports it
FINDING sev=major action=fix issue=- check_review and check_issues tracebacked on repo-controlled filesystem shapes (broken symlink, directory named *.md/.json) — OSError guards added at every read site, matching trace.py's existing pattern; diagnosed as "could not read", never a stack trace
FINDING sev=major action=fix issue=- security-floor had no defense against catastrophic-backtracking patterns — (a+)+$ against a long line wedged CI indefinitely (measured exponential). Per-rule wall-clock budget (hard, named failure; env-overridable for tests) plus a 600s per-gate timeout in gate_runner as the backstop
FINDING sev=major action=fix issue=- BOOTSTRAP "Later" update recipe hard-failed for HEAD-installed projects ("Downgrades are not supported") — the --vcs-ref=HEAD requirement is now stated where the update is documented
FINDING sev=minor action=fix issue=- security-floor: exclude:["*"] neutered the whole floor silently — now an advisory "0 files in scope" note, mirroring the existing zero-tracked-files disclosure
FINDING sev=minor action=fix issue=- make_review_bundle was the only sibling-importer without the sys.path shim — crashed under PYTHONSAFEPATH=1; shim added
FINDING sev=minor action=fix issue=- gh_board silently swallowed the removed --push flag (and passed a leading flag to gh as the project number) — exactly one positional, unknown flags get the usage line
FINDING sev=minor action=fix issue=- gate runs littered adopter repos with untracked __pycache__ (new with the sibling imports) — gate_runner sets PYTHONDONTWRITEBYTECODE for its subprocesses
FINDING sev=minor action=fix issue=- two _adr_exists copies survived the SP49 consolidation in check_architecture (zero-padded only) and check_arch_docs (two widths) — both now import check_decisions.adr_exists; check_product_frame's _unfenced twin now wraps check_review's
FINDING sev=minor action=fix issue=- three "every number carries confidence" claims survived the SP48 scoping (cockpit docstring, README module line) and gh_sync's docstring still claimed the gate flags orphan issues — all reconciled
FINDING sev=minor action=fix issue=- BOOTSTRAP's version check named a pyproject.toml that does not exist in the rendered project — now points at .copier-answers.yml's _commit; start-here now says git init -b main (the CI push trigger assumes main) and orders the baseline commit before hook installation
FINDING sev=minor action=fix issue=- trace.py's commit correlation depended on an undocumented convention — commits.md now asks for the plan slug/issue ref in the message; plans/archive/ ships seeded
FINDING sev=nit action=fix issue=- DoR R1 type enum omitted finding; CHANGELOG SP48 entry overclaimed the README as template-test-pinned; trace/check_issues FINDING regex twin now pinned by test
FINDING sev=nit action=accept issue=- release tag lags the docs until the next merge+tag — inherent to the tag-on-merge procedure, resolved by merging this PR
FINDING sev=nit action=accept issue=- make_review_bundle labels a binary PRODUCT.md "missing" instead of "unreadable" — read-only tool, message slightly imprecise
