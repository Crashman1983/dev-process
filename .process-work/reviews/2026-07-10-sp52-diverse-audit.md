review: SP52 diverse audit (four fresh lenses over v1.35.0)
work: PR #26
issue: publish-waived: all findings fixed in-PR before merge (this report is the record)

## Prompt

```
Four auditors with lenses deliberately DIFFERENT from SP50's
(adversarial/coherence/adopter/robustness):
1. skeptical-senior pragmatics/economics (token tax, ceremony-vs-value,
   over-engineering hunt, gaming paths, failure UX — with numbers);
2. multi-harness degradation (copilot-only, agents-only, gitlab-only, no-CI,
   all-on: second-class-citizen hunt across 9 render combos);
3. lifecycle simulation (v1.13.0->HEAD upgrades, module retrofit round-trip,
   6-months growth at 1x/10x, retention, answers-file drift);
4. critical technical writer on the SP48-51 prose (fact-checks, internal
   consistency, scope, English quality).
(Model: Fable. Full prompts archived in session.)
```

## Result

3 major, ~14 minor, several nit — all fixed in-PR except the accepted items
below. The pragmatist's overall verdict: "process with unusually little
theater" — session reading tax ~5.4k tokens (<3% of a window), gates
0.2–0.8s, every over-engineering suspect acquitted (profiles collapse the
choice, github-master/telemetry correctly opt-in). Lifecycle: upgrades from
v1.13.0 are conflict-free and byte-identical to fresh renders; growth to 10x
(600 plans, 2000 journal files) keeps gates under 0.9s. Multi-harness: the
shared docs layer genuinely carries the process; the Copilot anchor was the
one second-class citizen.

## Findings

FINDING sev=major action=fix issue=- Copilot anchor had no route to the workflow: zero pointers to workflow.md/commits.md and no phase map — branching/merge rules unreachable from auto-loaded Copilot context; reading list + prompts pointer added before the kernel block
FINDING sev=major action=fix issue=- BOOTSTRAP "Later" recipe's --skip CLAUDE.md/AGENTS.md left a stale kernel block after upgrade and turned the kernel gate red (reproduced v1.13.0->HEAD); flags dropped (3-way merge preserves local edits), plus re-run-install-hooks note (installed hooks are copies and do not update themselves — also added to git-hooks.md)
FINDING sev=major action=fix issue=- trace.py matched plans/reports on bare-digit keys: issue #7 listed 68/68 plans (608/608 at 10x); bare digits excluded and '#N' anchored so '#7' no longer matches '#70' (same guard matching_commits already had)
FINDING sev=major action=fix issue=- testing.md cited DoR R2 for the four acceptance cases R2 never named, and implied the git-hooks module runs the test suite pre-push; R2 now owns the four-case list (workflow/testing point at it), hook claim reworded
FINDING sev=major action=accept issue=- the SP51 release bundled version bump + changelog into the feat commit, violating the releases.md it shipped; accepted for d518968 (the ritual landed in that same commit), binding from now on — v1.35.1 follows it
FINDING sev=minor action=fix issue=- make_review_bundle silently ignored unknown flags (a typo'd --base reviews the wrong diff) and bundled all active plans unfiltered (8 parallel plans bury the reviewer); unknown argv is now a hard usage error, --plan SLUG narrows the bundle
FINDING sev=minor action=fix issue=- "forgot to archive the plan" was perfectly silent — the one gaming path with no runtime signal; the review gate now notes active Tier 2+ plans (soft, exit 0)
FINDING sev=minor action=fix issue=- doc-drift never scanned .github/instructions/process.instructions.md (proved live: dead ref stayed green) though its docstring claimed coverage; added to SCAN_FILES
FINDING sev=minor action=fix issue=- no-CI renders read an unsatisfiable project-DoR item ("CI gate wired as required check"); the item now names the hooks-as-enforcement-authority branch, and four module docs no longer claim "Runs in CI" unconditionally
FINDING sev=minor action=fix issue=- gate_runner reported a hand-edited-manifest phantom module as a bare "can't open file"; it now names the likely cause and the copier-update fix
FINDING sev=minor action=fix issue=- /quick (Claude) carried two checklist questions that existed in no shared doc; workflow.md Quick now owns them, the command points there; AGENTS.md review entry now surfaces the gate-parsed REVIEW grammar + bundle tool
FINDING sev=minor action=fix issue=- no retention story existed (unbounded growth silent); journal-state-plans.md now states it honestly: unbounded by design, prune by age as an ordinary change, reports/ADRs excepted
FINDING sev=minor action=fix issue=- writer precision pass: E2E-proof wording aligned with the checklist (manual trace may stand in), invalidation case restored in two enforcement enumerations, telemetry-cockpit reference guarded, "tag the merge commit" -> the commit that lands on main, pre-1.0 marked as convention, Mermaid "most doc tools natively" softened, scaffold Germanism fixed, "event ledger" -> raw event counts, comma splices fixed, one sentence on reviewing AI-generated tests for assertion substance
FINDING sev=nit action=fix issue=- copier.yml modules help now warns github_issues/github_master assume a GitHub-hosted repo + gh; archive/.gitkeep normalized to 1 byte; CHANGELOG "Trophy" claim corrected
FINDING sev=nit action=accept issue=- tags lag main until PR merge (tag-on-merge policy; remote carries v1.32.1) — resolved by merging this PR; naive copier update leaves new module keys absent from the recorded dict (harmless, gate_runner uses .get); copilot prime prompt omits inbox triage (reachable via journal-state-plans.md)
