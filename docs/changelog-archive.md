# Changelog archive — dev-process up to v2.28.1

The releases before v2.28.2, newest first, in the form of the
[CHANGELOG](../CHANGELOG.md): **Why**, **What changes**, **Effect**,
**Update** and **Details** where the history names them. The history was
written as a narrative by sub-project (SP1 to SP79); the Details line names
the sub-project where the history gives one. Versions without a tag carry no date.
Deutsche Fassung: [changelog-archive-DE.md](changelog-archive-DE.md).

## v2.28.1 — Urgent fix: every push with history was rejected · 2026-09-24

**Why.** The annotated-tag resolution introduced in v2.27.1 wrote `^{{commit}}` in the gate runner. In a Jinja template that is Jinja syntax and renders to `^`, which is the parent commit. With the `git-hooks` module, the check of the pushed state therefore rejected every push whose commit has a predecessor. The test ran with a repo of a single commit and did not see it.

**What changes.**
- The gate runner now writes `^0` (no braces).
- A test with real history and an annotated tag.
- A guard test against double braces without a space in Python templates.

**Update.** Anyone who installed v2.27.1 or v2.28.0 and fails at push: update to v2.28.1.

## v2.28.0 — Review enforcement without CI sharpened · 2026-09-24

**Why.** An audit of the reference project showed three gaps, all undetected without CI:
- A Tier 2 plan could be merged to main without review (the obligation only applied on archiving).
- Code after the review note stayed green.
- A skipped hook or a merge via the platform button went unnoticed.

**What changes.**
- The push to main now requires the clearing pass from Tier 2.
- A pass is valid only for the `head` it names. Code changed later in the paths of the push invalidates it at the merge push and in `finish.py` (journal and plans excepted).
- A Tier 3 plan that is still active while commits on main claim its issue turns the gate red on every run, unless there is a pass or `review-waived:`.
- Active plans are recognized, like archived ones, by their short name without date.
- The recipe for cloud sessions installs the git hooks, because pushes happen there too.

## v2.27.1 — Findings of an independent functional audit of v2.27.0 fixed · 2026-09-24

**Why.** An independent functional audit of v2.27.0 found three bugs that broke documented paths.

**What changes.**
- `no-commit-to-branch` also ran at pre-push and blocked the merge push of `finish` and the train. It now runs only at commit.
- For an annotated tag, the check of the pushed state compared the tag object instead of the commit.
- With `ci.github=false`, doc-drift was red from the first run, because start-here named a script that is only rendered with CI.
- `template_update.py` raises an older standard installation to `sbom: true` (there, `sbom: false` was only derived from `regulated: false`).
- `check_issues` reads an empty response multiplied by old update helpers as empty.
- BOOTSTRAP names all files that need a `--skip` and then a merge in brownfield, and the path for installations under v2.24.0.
- The status table reads plans from all worktrees. A worker plan without an issue is now found.
- The review gate no longer reports a claimed issue as planless when a plan under Tier 2 names it.
- Outdated texts about removed modules are cleaned up, `fix-streak` reports OK, `make_review_bundle.py` and `tidy.py` know `--help`.
- From the audit of the reference project: in CI, the hook wiring reports nothing (there the job is the enforcement; it does not need local hooks). A review digest that cannot be computed in a shallow clone (the default of a cloud session) is a note instead of red.

## v2.27.0 — KISS pass by measurement, new logo, working documents removed · 2026-09-24

**Why.** An independent audit measured on the reference project what carries weight: which gates ever found something, which modules have artifacts, which scripts are used.

**What changes.**
- Removed is what was empty or unused in the reference project: the modules `contracts` (`contract-first`, `contracts-drift`), `arch_docs`, `github_master` (with `gh_sync`/`gh_board`) and `security_floor`, plus `trace.py`, `new_issue.*` and the workflow `cleanup-branches` (replaced by `tidy`).
- The `regulated` question is dropped. `sbom` stays and is now part of the standard setup, because an SBOM counts for productive use.
- An older manifest that names removed modules keeps working. `template_update.py` removes their files.
- Brought back from the reference project, where it proved itself:
  - the gate `fix-streak`: the third fix to a file in the branch is named (rule 6).
  - the gate `ac-text-drift`: an acceptance criterion reads the same in spec and inventory.
  - the check that a pre-push pushes the checked state (`PRE_COMMIT_TO_REF` against HEAD).
  - the attest always goes into the branch's journal folder, so parallel reviews no longer collide in one daily file.
  - in the train, the gate start via `gate_invoke`.
  - a second run when the base state is red, and the push from the staging worktree.
  - in the delta bundle only the findings of THIS operation, and never a stale bundle after a failed run.
  - a guide for the setup hook of cloud sessions (`tower.md`).
- There are now 15 gates instead of 16/18.
- Logo: `docs/assets/` holds the mark (`mark.svg`), the wordmark for light and dark surfaces and a social preview image (1280×640). Three agents run on their own lanes into a gate of four tiers each, whose opening is only one line wide, and leave it as one checked line: a check mark that ends in a merge point.
- Cleaned up: the working documents since July are removed from the tree. These are `docs/design/` and `docs/plans/` (67 drafts and plans, most from before the lean pass), `docs/pilots/`, the audit reports under `.process-work/reviews/` and `docs/CAPABILITIES.md`, which the overview replaces. They stay in git history; this CHANGELOG tells the development.
- The current Spec Kit draft now sits with the analysis under `docs/analysis/`.

## v2.26.0 — The session on the other host has a name · 2026-09-24

**Why.** In the reference project's pilot, the cloud start in the terminal printed only text, no JSON. The session ID appeared only in it, and the steward could not see which session to check.

**What changes.**
- `dispatch.py` now reads the session ID from the output of the hand-over (stdout or log of the tmux window).
- It is recognized via `phases.<phase>.handover_id` (regex, group 1) or as the first URL.
- `list`, `log` and the tower show it.

## v2.25.0 — Remote hand-over from a terminal · 2026-09-24

**Why.** In the reference project, handing a review over to a cloud session failed: the start command did not run without a terminal, and `dispatch.py` started it without one.

**What changes.**
- A remote phase with `"runner": "tmux"` now starts the hand-over command in a tmux window.
- `log` and `say` reach this window.
- `list` shows `HAND-OVER FAILED (exit N)` when the hand-over ended with an error, instead of reporting the phase as running.

## v2.24.0 — `pushed` is checked, findings of the greenfield audit fixed · 2026-09-24

**Why.** In the reference project, workers reported `pushed` three times in one day before the work was on origin. The steward then started the next phase on a branch without that work.

**What changes.**
- `report.py pushed` now refuses as long as the branch is not on origin with the worktree's HEAD, or origin has no new commit since the phase started.
- `dispatch.py` passes the start point along as `PROCESS_PHASE_BASE`.
- `--force` remains for an unreachable origin and marks the report as unverified.
- A greenfield audit by an independent agent (empty repo, all harnesses, `regulated`, hooks, Spec Kit, one Tier 2 run) found no blocker. Fixed:
  - `template_update.py` doubled the quotes of empty string answers (`github_repo: ''`) on every run. It now detects a HEAD installation before the run instead of via copier's downgrade error.
  - `scripts/process/.gitignore` and `.process-work/.gitignore` keep `__pycache__/` and the update deltas out of the worktree.
  - The Spec Kit setup also removes the three skills under `.github/skills` (Copilot).
  - `start-here.md` names `speckit` and `design-contracts` in the standard setup.
  - `workflow.md` says that `/report`, `/steward` and `/finish` are Claude Code commands and other harnesses call the scripts directly.
  - `rehydrate.py --check` confirms success, `train.py plan` without commits stops instead of failing, `finish.py` names `publish_and_prune` only for changes with a spec.
- The README is new and slim, with a pointer to the overview, which is now also available in English (`docs/OVERVIEW.md`).

*Documentation as entry point, no template change.*
- `docs/UEBERBLICK.md` (and identical as PDF) explains the process in eleven chapters and is the new entry point from the README.
- BOOTSTRAP names the five actual questions, recommends `template_update.py` for updates instead of an example dictionary that would have switched off modules, and explains parallel agents (model policy, `rehydrate.py --install`, steward, dispatch, train). Both were re-checked against a fresh headless render.
- SYSTEM-REQUIREMENTS drops GitLab and `parity` and adds tmux and the coordination scripts.
- The public repo names the origin project only as reference project and contains no operating details, client references or first names any more. The neutrality lists of the tests stay.

*License text in the rendered repo, SBOM generated instead of maintained.*
- Why: the template did not ship the license text, although Apache 2.0 requires it on redistribution. The repo SBOM was maintained by hand and stood at v1.37.0.
- Every set-up repository gets `docs/process/LICENSE` (Apache 2.0, identical to the repo `LICENSE`; a test keeps both equal) and `docs/process/NOTICE.md`. The license applies to the rendered process files, not to the code and content of the project. Changed process files carry a change notice.
- `tools/gen_sbom.py` now generates `docs/SBOM.md` and `docs/sbom.cdx.json` (CycloneDX 1.5, with hashes and dependency graph, deterministic) from `pyproject.toml` and `uv.lock`.
- `test_sbom.py` turns CI red as soon as either file is stale.

## Sub-project table (SP1–SP24)

The table was maintained up to SP24; from SP25 on, the narrative above carries the history alone.

| Sub-project | Content | Status |
|---|---|---|
| **SP1** Foundation | Core + adapters + copier init + additive brownfield drop-in | ✅ shipped |
| **SP2** Architecture onboarding | Architecture interview + verification against real code | ✅ shipped |
| **SP3** Process completion (multi-repo/multi-human) | feature-registry · github-issues · contracts-drift | ✅ slices 1–3 |
| **SP4** Process completion II | git-hooks (local enforcement pillar) · contract-first (interface-declared-first gate) · parity (capability×surface matrix, gap→issue) · security-floor (pattern floor over git-tracked files) | ✅ shipped |
| **Capstone** command-adapters | Harness-native slash commands (Claude / Copilot / AGENTS.md), pointing thinly to `docs/process/`, also checked by the doc-drift gate — closes the "as complete as the reference project" programme at `v1.0.0` | ✅ shipped |
| **SP7** ci-adapters | GitLab CI as second enforcement transport (`ci` namespace, includable job + root shim) · documented no-CI degradation · install fallbacks without `uv` (pipx / venv+pip / local clone) | ✅ shipped |
| **SP8** english-canon | All artifacts in English (halves the doc tokens per session) · kernel rule "dialogue in the user's language" · "when it is not worth it" honesty · journal duty only from Tier 2 | ✅ shipped |
| **SP9** audit-fixes | Three-axis audit: all confirmed false-greens closed (manifest load-bearing, arch fence, unborn-main hook, hooksPath guard) · failure modes with diagnosis instead of traceback · doc-drift understands document-relative links · doc drift cleaned up | ✅ shipped |
| **SP10** telemetry | Efficiency made measurable (audit finding, generalized from the reference project): `GRADE` trace convention in the journal · gate lints the trace format (no silent telemetry loss) · read-only KPI cockpit (`process_kpis.py`: effectiveness/convergence/suite/tempo/cost/cfr) · grader calibration suite with the three trust thresholds (≥20/≥5 · 0 false-PASS · ≥90 % ≤2 rounds) | ✅ shipped |
| **SP11** reaudit + public | Adversarial re-audit of the telemetry slice: false-greens closed (suite-shape alignment in the danger direction, filter=grammar, Unicode-round, typo-root) · failure modes speak instead of tracebacks · personal data out of the tree, English README entry, `uv.lock` committed, CI least-privilege | ✅ shipped |
| **SP12** verification-independence | Context independence of verification as core methodology (the gap after the telemetry slice): production warm (coherence), verification independent, tier-graded (0–1 self-check · 2 fresh bundle review · 3 cross-model + adversarial-refute) · review attests its independence, otherwise it counts one tier weaker | ✅ shipped |
| **SP13** anchor-guidance | Two portable gaps closed (from comparison with a mature adopter): the "anchor carries pointers, not drifting detail" discriminator is now spelled out in `start-here.md` (*does it drift on refactor? → not in the anchor*), plus how to scale anchors for large multi-stack repos (nested per-subtree anchors) — keeps the thin kernel thin | ✅ shipped |
| **SP14** junior-legibility | Three gaps closed from a junior simulation: a stack-neutral `review-checklist.md` (what a review really checks — completeness, correctness, **security** untrusted-input→sink, design/one owner, tests), a "How do I recognize my tier?" heuristic in `risk-tiers.md`, and an honest "pattern floor, not your security review" sentence in the security-floor module | ✅ shipped |
| **SP15** arch-docs | New opt-in module: stakeholder-facing architecture docs (arc42/C4-lite) as an `ARCHITECTURE-OVERVIEW.md` scaffold — context, quality goals, runtime, deployment, risks/tech debt, glossary; building blocks→arch block and decisions→ADRs *linked* instead of duplicated (one owner); the gate checks only what is mechanically honest (dead ADR refs hard, placeholders as note), never pretends "documented" | ✅ shipped |
| **SP16** review-breadth | `review-checklist.md` freed from its web bias: two stack-neutral dimensions added — **performance & efficiency** (N+1, unbounded fan-out, hot paths) and **observability & operability** (fail-fast instead of silent degradation, deploy-dependent questions phrased conditionally); untrusted-input→sink framed more broadly | ✅ shipped |
| **SP17** parallel-friction | Friction for parallel agents on one repo reduced: the one shared daily journal can be sharded per branch (`.process-work/journal/<branch-slug>/YYYY-MM-DD.md` — gate and cockpit read recursively, both layouts work); new "## Parallel efforts" section names the trade-off honestly (execution parallel+sharded, integration serialized by ff-only, never two efforts on one owner) | ✅ shipped |
| **SP18** decision-records | ADR generalized to the typed **decision record** (`Type: architecture \| product \| process`) — significant product/process decisions finally have a home; intent stays *one* value per record (atomicity forcing function). First **core gate** (`check_decisions.py`, always active since `adr/` is core): listing drift + invalid enums + incoherent status×intent pairs (`Superseded`+`keep`) hard, unfilled menus/missing type soft. Rule 4 anchors "significant decision → decision record" + patch-count gate (third patch wrong by default) | ✅ shipped |
| **SP19** review-enforcement | Review independence from prose to gated artifact: structured `REVIEW` attestation in the journal, second **core gate** (`check_review.py`). **Arithmetic** hard — a `pass` may not clear a tier that its independence flags do not support (self-review/warm clears no Tier 2+; Tier 3 needs `cross-model` or honest `single-family`). **Presence** hard — a merged (archived) Tier 3+ plan without clearing attestation fails, unless a named `review-waived:` exception. Identity/model truth stays attested (the gate cannot see the review runtime) — honest limit, no false-green | ✅ shipped |
| **SP20** issue-centricity | GitHub issues pulled more strongly into the flow: **issue-before-code** as a gate in the `github-issues` module — an *active* Tier 3+ plan without an `issue:` link (or a named `issue-waived:`) fails. Mirror image of the review gate: issues for active plans (start), reviews for archived ones (end), no overlap. Claim/heartbeat discipline sharpened (claim fields + cadence) — deliberately *not* gated (social/wall-clock not machine-checkable), honestly named as such. All opt-in under the module (portability) | ✅ shipped |
| **SP21** dependency-sequencing | Stories can declare dependencies (`blocked_by: [STORY-NNNN]`, sequencing, not decomposition). Feature-registry gate (owner extended, no parallel gate) checks hard: dangling ref, self-reference, **dependency cycle** (DFS, with path); soft: `done` story with unfinished blocker. Read-only `story_order.py` computes the ready-to-start set + topological order. "Blocked by #N" rendering into the issue stays an optional projection (registry = SSOT) | ✅ shipped |
| **SP22** github-master | Opt-in adapter that flips the direction of truth: **GitHub Issues = SSOT**, the file registry becomes a mirror — without network in CI. Two layers strictly separated: **sync** (`gh_sync.py`, pulls issues → committed `.process-work/github-snapshot.json`, network) vs. **gate** (`check_github_master.py`, hermetic offline over the snapshot). Hard master invariants: every living story has an issue ref + snapshot entry (complete on both sides), drift on title/status↔state; `null` slots for blocked_by/parent/board (later slices). The portable registry-master default stays untouched | ✅ shipped |
| **SP23** sub-issues | Decomposition: `parent: STORY-NNNN` (tree, orthogonal to `blocked_by`). Feature-registry gate extended (shared cycle DFS, one owner): parent dangling/self/**cycle** hard; soft: parent-done-before-child, literal child↔parent duplication. Epic test rule resolved: a parent may be `done` without its own test only if **all children are done** (the children's tests cover it), a leaf never. github-master drift-checks `parent` (sub-issues = master); `story_order.py` shows the epic→children hierarchy. Anti-dup honestly checkable only for literal equality | ✅ shipped |
| **SP24** project-board | GitHub project board (Backlog→Ready→In-progress→Review→Done) — **automated *and* gated**, without breaking hermeticity: `gh_board.py` (network) fills the `board_status` slot in the snapshot, the **gate checks offline** the consistency column↔story status↔issue state (unknown column / contradiction hard; `deprecated` exempt). Card movement (`--push`) is an explicit extension point (GitHub write, best-effort, never a gate). One canonical mapping table | ✅ shipped |

## v2.23.0 — Lane lock by lane and phase · 2026-09-24

**What changes.**
- `dispatch.py` now evaluates the lane lock by lane and phase instead of blanket.
- `lane.py status` is read line by line. A held `full` blocks only `execute` (plan and review run under the train). A held `scoped` or an unknown lane blocks everything.
- A remote phase sees neither `max_workers` nor the lane, because its load sits on the other host.
- `--dry-run` names the rule that allowed or refused, and keeps exit 3 on refusal.
- `tower.md` and the docstring say the same.

## v2.22.0 — Phases on another host · 2026-09-24

**Why.** The steward in the reference project found that the bottleneck is the CPU of the control host, not the number of slots. Reviews bind much of it and need only git.

**What changes.**
- The policy knows `phases.<phase>` with `command`, `runner` and `remote: true`.
- A remote phase start creates no worktree. The command is the handover (cloud session, ssh). The branch must be on origin. The prompt tells the worker to report with `--sync` under its own `PROCESS_HOST`.
- `list` shows REMOTE, `stop` forgets only the record, `tower.py --remote` sees the reports.
- `tower.md` says why reviews move first (git-only, CPU-heavy, and a fresh clone on another host is independence) and that a push from there passes no local pre-push hook.
- `rehydrate.py` prints only the last twelve decisions of a plan. A plan with 113 DECISION lines is a log, and every compaction paid for it.

## v2.21.0 — From the first steward day · 2026-09-23

**Why.** Two findings of the owner, both from operation.
1. The steward let a worker wait an hour on `planned`, because it ticked only every 30 minutes and was just passing a question through. The guide knew no watch.
2. A gate was red in the train and not reproducible in the root. The staging worktree lay under `.git/process-train/`, and a file lister that skips every path with a `.git` segment saw an empty tree.

**What changes.**
- Claude Code has a watch: `Monitor` on `tail -f` of the reports file wakes the steward at the next `planned`/`pushed`/`blocked`/`review-pass`/`done` immediately. It lives at most 30 minutes and is set again at each wake. The `/loop` tick remains the fallback (a `DECISION NEEDED` without `blocked` is seen only by the tower).
- Phase changes wait for nobody: after `planned` immediately `execute`, after `pushed` immediately `review`. The owner is informed, not asked.
- The staging worktree now lies as a sibling next to the root (`<root>-train`, like the dispatch worktrees). Only logs stay in the git common dir.

## v2.20.1 — Subagents in the worker: offload reading, never the change · 2026-09-23

**What changes.**
- `/execute` now says what a worker uses subagents for: search across the codebase, diagnosis from long test runs, doc comparison. Read much, return little.
- It also says what they are not for: the change itself. The subagent knows neither kernel nor ledger, and the worker would sign a commit it has not seen (rule 1). The exception remains the `[P]` protocol.
- `rehydrate.py --install` keeps the escapes of the settings file.

## v2.20.0 — Re-hydration as a mechanism, not a sentence · 2026-09-23

**Why.** So far only the kernel said "after a compaction, re-read kernel, rules and ledger". That is a sentence that has to survive the compaction it warns about. The owner noticed that workers do not do it.

**What changes.**
- New `scripts/process/rehydrate.py` prints what `/prime` reads and nothing more: kernel block, mandatory rules, active plans with tier/issue, DECISION ledger, open DECISION-NEEDED questions with the hint "do not decide yourself", next task, state file, journal shard. It runs as a Claude Code `SessionStart` hook for `compact|resume`.
- `rehydrate.py --install` writes the hook idempotently into `.claude/settings.json` without touching the rest of the file (it stays project-owned). `--check` says whether the hook is there.
- `/prime` stays for the cases the hook does not cover. `start-here.md` describes the mechanism.
- `dispatch.py` also replaces `{branch}` and `{issue}` in the policy `command`, so a harness can name the session. In Claude Code, `--remote-control={branch}` makes every worker visible in the Claude app (the `=` form; otherwise the optional name of the flag eats the prompt).

## v2.19.2 — Questions as a menu · 2026-09-23

**What changes.**
- The steward no longer passes a worker question on as a paragraph but as a selection.
- Where the harness has a question tool (Claude Code: `AskUserQuestion`): one question per worker, with the worker's options as clickable answers. The recommendation comes first and is marked "(Recommended)". Issue, branch and situation are in the question text.
- Without such a tool: a numbered list.
- Up to four open questions in one call, oldest first.

**Effect.** Works in the app and via Remote Control.

## v2.19.1 — Second independent review (v2.18/v2.19): 19 findings addressed · 2026-09-22

**Why.** A fresh reviewer read dispatch, tower, train, steward and model policy without prior knowledge. The hard findings:
- tmux workers counted as alive forever (the shell PID was not the worker).
- `stop` could hit foreign processes (recycled PID, PID 0 = own group).
- A foreign directory at the worktree path was accepted as a worktree.
- The tower did not see questions in a worker's worktree (it read only its own).
- The model KPIs counted rounds per report instead of per issue.
- The prompt ran through an interactive shell despite the docs.
- The steward had instructions without a mechanism ("file watch", "message into the window").

**What changes.**
- `dispatch.py` rewritten:
  - Liveness is the pane state (`pane_dead`, `remain-on-exit`), never a shell PID.
  - Records carry PID plus start time; `stop` ends only the recorded process.
  - The window runs a non-interactive `sh` with exact POSIX quoting and `exec`.
  - `{model}`/`{prompt}` are replaced also inside a token.
  - `CLAUDECODE`/`CLAUDE_CODE_*` are removed for both runners.
  - `issues.json` finds the branch of an issue even after a stop.
  - The prompt starts with the slash command and carries the question protocol.
  - New `dispatch.py say <branch> "<text>"` types a line into a tmux worker.
  - `log` shows the screen for tmux (a TUI log is escape codes), otherwise the log tail without ANSI.
  - The dirty check counts untracked files.
- Tower:
  - `questions` reads every worktree of this clone and, via `git show`, the branches of other hosts (`--remote`).
  - The question line tolerates bold text and a missing "who".
  - `sessions` shows the state (live/dead/gone/unknown).
- Train: an open `DECISION NEEDED` keeps the branch off the train.
- `process_context.py` carries `open_questions` per plan (`/prime` sees what is being waited for).
- KPI `models`: an issue is one unit, the model last reported per phase owns it, rounds count once per issue.
- Steward guide without inventions: tick via `/loop`, no file watch in the process; answers via `say` to the asking worker, never two writers on one plan.
- Trust boundary of the policy (`command` runs on the steward host, to be reviewed like CI configuration) stated in `tower.md` and in the policy itself.
- Note on permissions (`-p` needs a grant, interactive possibly a trust dialog).

## v2.19.0 — Visible workers and a question protocol · 2026-09-22

**Why.** Owner experience with the first steward: "I see too little, questions come late and without context". Two design gaps, now closed.

**What changes.**
- **Workers as tmux windows.**
  - Policy `runner: tmux`, `tmux_session`. `dispatch.py` opens one window of a tmux session per worker, interactive and to be opened by the human.
  - Output goes into the log via pipe-pane. The start runs shell, pipe, send-keys, so the first second is not lost and the TUI keeps its tty.
  - `dispatch.py log <branch>`.
  - The tower carries `sessions` with last output line and age per worker.
- **Question protocol.**
  - A question to the owner is a line in the plan: `DECISION NEEDED <date> <worker>: <question> — options: …; recommendation: …` plus `blocked`.
  - The tower carries `questions` and reports them as a high finding.
  - The answer is written back as a `DECISION` line; the worker reads the plan. Notes up to 1000 characters.
- **The steward watches instead of ticking.** File watch on reports and plans, the tick only as fallback. Questions are passed through completely and immediately: issue, branch, question, options, recommendation, situation.

Details: SP75

## v2.18.0 — Dispatch and model policy · 2026-09-21

**Why.** Two maintainer questions: "does the system start the sessions itself?" (no, until now) and "a different LLM per phase?" (yes, because the phases are separated by artifacts: plan and decisions ledger, then the bundle).

**What changes.**
- `docs/process/model-policy.json` is the one place to turn. It holds tier × phase → model, the project's own start command as template (`{model}`, `{prompt}`; the prompt is ONE argument, never passed through a shell) and `max_workers`. It is project-owned and belongs in `.process-owned`.
- `dispatch.py` starts a detached session per phase in the branch's worktree (`start --issue N --phase plan|execute|review`, finds the branch of the issue again). It keeps books in `.git/process-dispatch/`, shows liveness (`list`), and stops only its own children and only with a committed tree (`stop`, `--force`). It refuses when `max_workers` is reached or the lane is held.
- Measure instead of gut feeling: `report.py --model` (or `PROCESS_MODEL`/`PROCESS_PHASE` from dispatch) records which model ran which phase. `process_kpis.py models` (telemetry) slices review rounds to pass and blocks by tier × phase × model. It is honestly a proxy with confidence, the number by which the policy is measured.
- `/steward` assigns via dispatch and changes models only via the policy file.

Details: SP74

## v2.17.3 — Independent review of tower, train, report, design contract and ledger · 2026-09-21

**Why.** Maintainer: "check everything again, without bias". A fresh reviewer without context found 26 findings, six of them high, all with repro.

**What changes.**
- Train:
  - The tier from the raw text read fenced examples as a declaration (now `_unfenced`, as in the review gate).
  - A de-dated slug let a January pass clear a September plan of the same name (now the uniqueness rule of the gate).
  - A push to origin without an ancestor check could publish a main without local commits (now abort).
  - A failed local `branch -d` deleted on origin anyway (now coupled and reported).
  - The bisection blamed the first candidate when main was red (now a base check: a red main blames nobody).
  - Conflict dropouts stayed silent (now a `blocked` report).
- Tower:
  - main and `.process-work/` produced overlap findings.
  - A README counted as a plan.
  - A branch named differently locally overlapped with itself on origin.
  - A failed fetch was invisible (now finding `remote-unreachable`, no `--prune`).
- Report:
  - Hostnames were cut at the first dot (`build.eu`/`build.us` shared a ref).
  - Timeouts were uncaught.
- Design contract:
  - `Decision: GO/NO-GO meeting` counted as GO.
  - Fenced examples counted.
  - Any 64-hex number in the review counted as seal (now only a named `manifest.sha256:` line).
  - A subheading with an ID counted as a second definition.
- Seal: a nested `manifest.json` was exempt from the seal.
- Ledger: `--full` rechecked but did not write back, so a poisoned entry survived (now `--full` rebuilds the ledger).
- Docs aligned with the code; the threat model of the tower is named honestly.

## v2.17.2 — Guide wired in; the steward keeps the repo clean and the issues closed · 2026-09-20

**Why.** Maintainer question "is the guide adapted?": no, it was not. Tower, report, train and steward stood only in their own docs.

**What changes.**
- workflow.md "Parallel agents" explains the four and says explicitly that without a steward every session stays autonomous: gates and /finish still carry, the tower only makes things visible, the train only cheaper.
- /plan, /execute, /review and /finish name their `/report` state change. The train names the way past the /finish merge.
- README commands list.
- Steward, housekeeping section: daily `tidy.py --apply` for the safe part, an owner question for what tidy only lists, `remote-residue` from the tower.
- Steward, issues section: workers own their claims and closes. The steward closes stragglers with the merge ref, turns findings into typed issues, and releases dead claims after two hours.
- The train prints the referenced issues per merged branch.

## v2.17.1 — Backlog is not flight · 2026-09-20

**Why.** First remote run in the reference project: July branches, thousands of commits behind main, appeared as "in flight elsewhere".

**What changes.** A branch with no commit for 14 days is counted instead of listed and reported as one finding `remote-residue`.

## v2.17.0 — Tower across hosts · 2026-09-20

**Why.** Maintainer requirement: the process stays host-agnostic. In the reference project the control runs on one host and a detached worker on a second. The only channel every host already has is git, so git is the transport.

**What changes.**
- `report.py --sync` (or `PROCESS_REPORT_SYNC=1`) publishes a host's reports as a blob under `refs/process/reports/<host>` on origin. No ssh, nothing committed on a branch.
- `tower.py --remote` (or `PROCESS_TOWER_REMOTE=1`) fetches origin and these refs.
- Branches of other hosts appear as `elsewhere` with lead, paths in flight and age. They take part in the overlap check and can be stale like a local worker.
- The reports of all hosts are merged; per worker the most recent wins.
- Starting and stopping on the other host stays its own mechanism; the steward rule does not change.

## v2.16.1 — Train plan without leftovers · 2026-09-20

**Why.** First run in the reference project: 350 already merged branches appeared as "nothing ahead".

**What changes.** Backlog is the business of `tidy.py`, not a candidate. The plan shows only branches with a lead.

## v2.16.0 — Merge train and steward role · 2026-09-20

**Why.** Maintainer request: collect jobs and merge and deploy them efficiently at a good moment, instead of thirteen agents paying for thirteen full runs and deploys.

**What changes.**
- New merge train `train.py`. `plan` shows who may board and why not; the result is computed, never asserted.
- A branch boards only with an archived plan on the branch and a clearing REVIEW pass or waiver. A worker report counts only as a pointer, never as a substitute for a missing pass.
- A branch also boards only with no file overlap with a branch already aboard and no red gate.
- Departure at `--min-candidates` or `--max-wait-hours`, only when lanes are free; `--force` departs immediately.
- `run` creates a staging branch from main in its own worktree and merges the candidates in waiting order (conflict = drop out). Process gates and the full suite run ONCE on the combined tree.
- On red, a prefix bisection finds the first culprit; it drops out and is reported `blocked`.
- On green follow a fast-forward of main, `--push`, deletion of the branches, `done` per worker and `--deploy` once.
- New steward role (`/steward`): read the tower instead of asking sessions, work through findings by severity, assign, redirect. Stop only its own children, and only after a committed plan and decisions. Dispatch the train and write to the owner only on an event.
- The steward never implements, reviews or certifies. Model choice follows the tier, budget applies per issue.
- Docs: `docs/process/train.md`.

Details: SP73

## v2.15.0 — Tower: a computed picture of parallel work · 2026-09-20

**Why.** The maintainer's idea: an agent that coordinates many workers, talks to the maintainer, finds problems and steers resources. Before an agent judges, it needs a picture that is computed, not narrated. This deterministic core of a steward provides it.

**What changes.**
- New `tower.py`: a table built from state the process already keeps. It holds all worktrees of the clone with ahead/behind, paths in flight, dirty count and minutes since the last commit.
- It also holds overlaps of two worktrees on the same file (high) or the same directory (low), active plans with tier, issue, decisions count and design-contract binding, the day's reviews, red gates with age, lanes where they exist, and worker reports.
- Deterministic findings with reasons: overlap, Tier-2+ plan without issue, plan without decisions ledger, plan without tier, chronically red gate, silent worker with no commit and no report for an hour, blocked worker, branch far behind main. Options: `--json`, `--min-severity`, `--stale-minutes`.
- Worker protocol (`/report`, `report.py`): planned/pushed/review-pass/blocked/done/idle, one line per state change into the clone's shared git common dir, never committed.
- Docs: `docs/process/tower.md`.

**Effect.** The tower decides nothing and talks to no one. It is the steward's input, so that the steward's tokens go into judgement (assign, redirect, end) and not into asking thirteen workers.

Details: SP72

## v2.14.4 — No push waits blind · 2026-09-18

**Why.** Finding of 2026-09-18 in the reference project: the pre-push hook sat behind a full run, and the agent's tool call died after 40 minutes at 96 % of the scoped tests, five times in a row.

**What changes.**
- New rule in git-hooks.md and `/finish`: a hook that can run for minutes waits for a bounded time and aborts with the holder and a way out.
- The evidence is produced decoupled in the background (certify step, tree certificate); the push reads it.
- The tooling stays project-specific. In the reference project it is a lane script with two lanes and a certify target.

## v2.14.3 — Integrity ledger in the review gate · 2026-09-15

**Why.** Finding in the reference project: 628 digest-bound REVIEW lines, several git diffs per line, one canonical diff of large ranges ~3 s. The pre-push gate never finished. The inputs of a verification are immutable in the clone, and so is its result.

**What changes.**
- A record checked once is remembered in `.git/process-review-integrity`, "ok" as well as mismatch. A fabricated digest stays red on every run without being recomputed.
- Shards that the push itself changes are always checked fresh. Missing commits are searched for again every time.
- `--full` or `PROCESS_REVIEW_INTEGRITY=all` checks everything; `PROCESS_REVIEW_INTEGRITY=in-flight` checks only the changed shards (CI switch for huge journals).

## v2.14.2 — Plan binding to the named contract · 2026-09-15

**Why.** First run in the reference project: ID families span surfaces (E1 is a layer on web as in the app). An app plan was checked against the web contract, and `C8` did not count as `C08`.

**What changes.**
- A plan is checked only against the contract it names (path or `design-contract: <surface>` line).
- A plan with family IDs and no naming gets exactly one note.
- Zeros are not identity.

## v2.14.1 — Seal interop with render-kit freezers · 2026-09-15

**Why.** Trigger: three rounds already sealed in the reference project.

**What changes.**
- `seal.py --verify` and the design-contracts gate also read the manifest of a project's own render-kit freezer.
- The format is: `files` as a list `{path, sha256}`, dependencies as `externalDependencies` with folder-relative `../..` paths, `manifest.sha256` in sha256sum form `<hex>  manifest.json`.
- The formula stays the same, with one verifier.

## v2.14.0 — Design contracts as a module · 2026-09-15

**Why.** Generalized from practice in the reference project for web and app: UI work repeatedly failed because every agent renders something plausible and nobody can say which picture was *right*. In the reference project this was cured by one design contract per surface with stable IDs, sealed render rounds as reference, independent review with GO, and amend-before-code.

**What changes.** The template turns this into a module in the standard set, inert until the first registry entry:
- **Registry** (`docs/process/design-contracts/<surface>.json`): contract, status draft/accepted, sha256 pin, ID families, ADR, review, sealed reference, code paths.
- **Gate** `check_design_contracts.py`. Hard on: pin drift without re-pin, doubly defined ID, accepted without ADR or without a review with `Decision: GO`, review with a different seal than the reference, reference with a broken seal, active plan citing an ID the contract does not know. Note on: opaque pin, draft, boards from an older contract, surface push without cited ID.
- **`seal.py`**: manifest and sha256 over round folder and declared dependencies. `--verify` fails on edited, missing and undeclared files; drift of a dependency is exit 2.
- **Templates**: contract skeleton with § blocks and amendment log, review template with rubric/GO/seal hash, round README with procedure.
- **Binding without new chain links**: R5 now also names the contract IDs. D8 judges the AFTER image against the sealed board of the cited IDs. Review checklist "Surfaces" and rule 3 follow. The review bundle names the governing contract and the cited IDs.

**Effect.** The design itself stays a human and reviewer judgement against the boards. Render kit, export QA and token lints stay project-specific; the module describes only the pattern.

Details: SP71

## v2.13.0 — Evidence is computed, permanent red gets an age · 2026-09-10

**Why.** Maintainer finding from a second deployment: 15 of 16 review digests were never computed. It was plausible hex that no byte stream of any commit produces. The gate reported it on every run until nobody read it any more as permanent red. Third maintainer finding: two plans without a `tier:` line were invisible to every gate until they got one and two duties immediately became active.

**What changes.**
- **Evidence is computed, never typed.** `attest.py` writes the REVIEW line: the digest is recomputed from base/head with the gate's formula, a stale bundle is refused, the grammar is checked, the line is appended to the day's shard.
- The formula is ONE owner in check_review. `CANONICAL_DIFF` pins every git-config knob (algorithm, renames, prefix, abbrev, ext-diff, textconv) so a digest verifies the same on every clone. Legacy digests stay valid.
- A value that no formula produces is now called FABRICATED in the gate and counts as a missing review.
- **Permanent red gets an age.** gate_runner remembers each gate's first red day in `.git/` and prints the age with every failure. Digest section 8 shows it to the owner.
- **Switching off by omission closed.** An active plan and a specs/*/plan.md without a tier are now hard; archived ones stay a note.

Details: SP70

## v2.12.0 — Securing decisions in the plan · 2026-09-10

**Why.** Maintainer finding from a second process deployment: decisions made in dialogue do not land in the plan and are lost on compaction. The kernel protects itself, decisions not.

**What changes.**
- **`## Decisions` ledger in the plan**: one line `DECISION <date> <who>: <what> — because <why>` per decision, written before the next step. The plan, execute and prime commands and workflow.md carry the duty.
- **Re-hydration reads it**: process_context.py prints the ledger per active plan, so /prime, /execute and /review see it again after every compaction. The kernel directive names the section, byte-identical in all four copies.
- **Visible gap**: review-gate note for Tier-2+ plans without the section, also specs/*/plan.md.

**Effect.** The gate does not know a missing decision, but a reviewer asks when the ledger is empty.

Details: SP69

## v2.11.0 — tidy.py cleans up leftovers · 2026-09-08

**Why.** On the maintainer question "does the process clean up enough?". Measured on the reference project: 353 of 457 remote branches already merged, 9 of 35 spec directories finished, 5 active plans older than two weeks, all without a rhythm. Only plan-archive retention worked, because it sits hard in the hook and the fix is one command.

**What changes.**
- **`tidy.py`**: one report per leftover with the command. `--apply` does the safe part: merged remote branches, finished spec directories via publish_and_prune, folding the journal, old archives, template-delta.
- Old active plans and silent issues are only listed (owner decision).
- **Digest section 7**: the same numbers in front of the owner every week.

Details: SP68

## v2.10.1 — Evidence directory for Spec Kit plans · 2026-09-08

**What changes.** The evidence directory of a Spec Kit plan (`specs/NNN-x/plan.md`) is found via the directory, not via the file name `plan`.

## v2.10.0 — UI evidence: before/after pairs · 2026-09-08

**Why.** On the maintainer question "are screenshots stored for comparison and success control?". They were proof at the lower bound, but no comparison with the intent and invisible to the owner.

**What changes.**
- **DoD D8**: a before/after pair per viewport, theme and state under `.process-work/reviews/<slug>/`, linked from the review report. The after image is judged against the intent, not only against the lower bound.
- **Review bundle "UI evidence"**: lists the pair and every image the diff touches. A missing pair is a finding, not a skip. /review and the checklist require the verdict "matches the intent".
- **Digest section 6**: what changed on screen, with evidence pairs and changed pixel baselines as paths to open.
- **`check_baseline_duplicates.py`**: byte-identical screenshots under different names are proof of nothing. Ratchet with baseline pin.

**Effect.** First run on the reference project: 16 groups, among them "error" identical to "partially loaded".

Details: SP67

## v2.9.4 — Test lanes as a shared resource · 2026-09-07

**Why.** Finding in the reference project: four agents in four worktrees ran their scoped suites at the same time, load 6, everything crawled. A crawling gate gets bypassed.

**What changes.** testing.md: certificate transfer at the push and one flock track per host. Queue instead of throttle, no bypass.

## v2.9.3 — Three findings from a worker session closed generically · 2026-09-07

**Why.** Three findings from a worker session. On a worker host, a June copy of pre-push from `.git/hooks` ran for months, and a leaked GIT_DIR switched the real repo to `core.bare=true` through it. `gh issue comment` runs over GraphQL, whose secondary limit blocked for hours while the REST budget was untouched. Trigger for the deny list: project-internal identifiers in a spec snapshot.

**What changes.**
- **Hook doctor for `.githooks/`**: it also checks the other manager model. A tracked, populated hook directory without a matching `core.hooksPath` is never read by git and is hard, in gate_runner and in finish.
- **REST fallback when posting**: `publish_and_prune` falls back to `gh api …/comments` when `gh issue comment` fails at the GraphQL secondary limit. Verification reads via REST first.
- **Deny list before publishing**: `.publish-denylist` with project-owned regexes that both publish scripts (publish_and_prune and publish_review.sh) check before anything leaves the repo. A hit refuses the post and names the line.

## v2.9.2 — Certificates keyed by what they attest · 2026-09-07

**Why.** Finding in the reference project: parallel worktrees destroyed each other's certification with a slot file "the certified tree".

**What changes.** Certificates are keyed by what they attest: one entry per tree hash, never a single slot. Intermediate files are created per run via mktemp, never at a fixed shared path (testing.md).

## v2.9.1 — template_update.py re-sets recorded answers · 2026-09-07

**Why.** The first real run of `template_update.py` on the reference project uncovered a Copier pitfall: `modules` and `harnesses` are derived (`when: false`) answers that copier recomputes from the default on every update. The recorded answer does NOT win, and a disabled module silently comes back (observed: git-hooks including an anchor conflict).

**What changes.**
- The helper now re-sets every recorded answer as `--data`.
- BOOTSTRAP corrects the earlier claim "recorded modules dict wins".

## v2.9.0 — Token savers: context cost, journal compaction, template update · 2026-09-07

**Why.** The remaining three candidates from the maintainer question "what else can be automated by script". The hour of manual conflict resolution per release, measured on the reference project with five scripts, one doc and one command, becomes a mechanical port.

**What changes.**
- **Measure context cost** (`process_context.py --cost`): what a session start loads, grouped by anchor, commands, process docs, product frame, active plans, state/journal, all journal shards, spec directories. Plus the session-start estimate and the ten largest files. It counts chars/4, so figures are comparable with each other, not with the bill. Measure first, then trim.
- **Journal compaction** (`compact_journal.py`): shards older than N weeks are folded into a monthly archive. It keeps exactly the machine-read records (REVIEW, GRADE) verbatim and hands the prose to git. Gates and trace glob the archive like any shard; fenced quotes drop out with the prose. Dry run by default.
- **Template update with owner list** (`template_update.py` + `.process-owned`): copier update as before, the owner files stay as committed. The template's own delta per owner file (old release render against new) lands as a diff under `.process-work/template-delta/<ref>/`.

Details: SP66

## v2.8.1 — Note ledger in gate_runner and finish.py --apply · 2026-09-07

**Why.** Two token and time savers on the maintainer question "what else can be automated by script". Every gate note lands in the agent's context, and the notes are stable by construction (pre-adoption states, placeholders, freshness hints). So every push cost the same lines and buried the one that had changed. The tail checker printed the deterministic part to be typed in by hand.

**What changes.**
- **Note ledger in gate_runner**: the runner remembers the notes of the last run in `.git/`, prints only what is new and counts what was suppressed. `--all-notes` shows everything. A fresh checkout has no ledger and prints everything; CI inherits no local silence.
- **`finish.py --apply`**: the tail checker runs the deterministic part itself. Archive commit and rebase always run; merge, push and branch deletion only behind the package's full suite. `--tests CMD` runs it, `--tests-passed` asserts it.
- Every step prints its command, the first error stops in a state that git explains.

## v2.8.0 — Four process inventions from the reference project in the core · 2026-09-07

**Why.** Reference upstreaming: four process inventions from the reference project that carry generically are lifted into the core. A runner that does not start is a launch problem with a different owner than a regression. In the reference project, registration was silent and unnoticed for 25 days. There, a foreign decision paper in the tree blocked an uninvolved branch.

**What changes.**
- **Launch owner** (`gate_invoke.py`, pure stdlib): the one place that decides how a script declaring PEP 723 is launched. Children of the runner, `finish.py` and the review bundle run through it. "Not startable" is reported separately from "red".
- **Hook doctor** (same module): `.pre-commit-config.yaml` next to a set `core.hooksPath` means every registration is silent. gate_runner and finish block hard. A never-installed hook is a note or a finish blocker, respectively: a missing check is a blocker, never a skip.
- **Push-anchored presence** (check_review): an active Tier-3 plan that THIS push carries needs the clearing pass hard on the push to main/master, as a note otherwise. "Carries" means: file in the pushed range, or issue claimed via closing trailer/`(#N)` subject. The gate reads the target from `PRE_COMMIT_REMOTE_BRANCH` of the pre-commit framework or `PROCESS_PUSH_TARGETS` of a custom hook. Known limit: a server-side merged PR never pushes main locally; there finish.py remains the stop.
- **finish scoped to branch ownership**: only plans that the branch carries or claims are its review debt and archiving duty.
- **UI reuse duty**: DoR R5 / DoD D7 require a reuse map before implementation and a consumer proof after. Review checklist "Surfaces": nothing clipped, 24 px targets per WCAG 2.5.8, accessible name on every button/link, nothing obscured, four states, both themes. Stack guides sharpen, never lower.
- **Ratchet pattern** (testing.md): the baseline pins legacy, new findings and orphaned exceptions fail, the baseline can only shrink.
- **"Unmeasurable is not red"**: measuring gates refuse on a loaded host with their own exit code (EX_TEMPFAIL) instead of failing.

Details: SP65

## v2.7.8 — Records are guardrails, not concrete · 2026-08-29

**Why.** Recorded at the maintainer's request.

**What changes.**
- ADRs and contracts MAY be changed when the solution becomes more durable, technically better or clearer as a result. That alone is a sufficient reason.
- The two honesty duties are the whole bar. Name what gets better and why it holds in the long term (not merely "more convenient right now"). Make the change in the same effort as the code that requires it (Rule 4): supersession or a versioned contract change with all consumers, never silent drift.
- `adr/README` and `contract-first.md` carry the principle.

## v2.7.7 — Four-state rule for UI stories · 2026-08-28

**Why.** The hardening-wave analysis showed that about a quarter of the fixes in the reference project were cold, empty or offline states ("unknown stock rendered as empty", scope fallback while loading). "Unknown" is the state that ships broken when nobody names it: not-yet-resolved is neither empty nor an error.

**What changes.** The spec template now requires a table per touched surface with the states loading / empty / error / **unknown**, each with one expected behavior. These are the DoR-R2 twins, made concrete for UI.

## v2.7.6 — The test suite as a managed asset · 2026-08-27

**Why.** The maintainer's finding "still an extreme amount of time for tests". Measured: the Vitest suite grew by 43 % in two weeks, there were 69 E2E specs × 2 platforms, and stability proofs ran as 5× the full suite.

**What changes.**
- **E2E budget per feature = 1, floor AND ceiling.** A growing feature replaces its E2E proof. Platform variants only where behavior differs. Consolidation passes are maintenance. Every retired test needs a named cheaper replacement.
- **Stability proofs scoped × N, full × 1** (`testing.md`).
- **Test-estate trend in the owner digest.** Unit and E2E file counts now vs. 14 days ago, git-based, read-only.

**Effect.** Growth becomes visible before it feels like today again.

## v2.7.5 — Certificate transfer downhill too · 2026-08-21

**Why.** A live finding by the maintainer: the push gate pulls the full suite, and right after it the boundary run runs again, with no change in between.

**What changes.**
- **Stronger evidence replaces weaker.** A full-run trigger at push may memoize on a certificate that covers the same tree in a superset configuration (coverage run ⊇ plain run).
- The order at the coherence point is now boundary run → push → review → merge. One full run per batch; all later gates read the certificate instead of earning it again.
- Clarification: the review preflight runs only the process gates, never the suite.

## v2.7.4 — Push and certificate economy · 2026-08-20

**Why.** The maintainer's finding "deploy 20 min, push gate similar".

**What changes.**
- **Push at coherence points, not per commit.** The push gates price the pushed span; five related commits in one push cost one gate run. Limits: before building the bundle, before the session ends, often enough for parallel visibility (`commits.md`).
- **Paid completeness is transferable.** The boundary full run writes the certificates that later gates memoize on (coverage-tree cert). They are earned in the certifying configuration, never claimed. A deploy gate on the same tree becomes a memo hit instead of a double payment (`testing.md`).

## v2.7.3 — Test economy as a generic pattern · 2026-08-18

**Why.** The maintainer's question "full test run on every change?".

**What changes.**
- **Selection close to the edit, completeness close to the merge.** `testing.md` carries the ladder.
- Per task and per push, run the scoped set (module graph / `vitest related`, or an auditable module map). Honest full-run triggers cover everything that does not act via imports (config, tokens, global styles, schema, DI, fixtures).
- At the merge boundary, run the FULL suite exactly once for the whole batch. Several changes share one full run; selection is never the last safety net.
- `finish.py` prints the full-suite step before the merge.

## v2.7.2 — Two gate defects from a fresh clone · 2026-08-17

**Why.** Two defects from a fresh clone of the reference project, the first cold test bench after weeks of warm sessions.

**What changes.**
- **Digest binding degrades honestly.** After a rebase merge and branch deletion, the pre-merge SHAs exist in no fresh clone. Unresolvable artifact commits are now a Note ("unverifiable here") instead of a hard red, which would retroactively redden every clone for every correctly bound historical review. A digest MISMATCH stays hard.
- **Tier cap in the presence arithmetic.** The REVIEW grammar caps tier at 3. A plan on the extended downstream scale (`tier: 4/5`) clears at the gated ceiling (min(tier,3)) instead of an unmeetable bar, on the archive and the speckit path alike.

## v2.7.1 — Speckit presence and gate hygiene · 2026-08-17

**Why.** The finding in the reference project that "slices 009–016 ran past the strongest gate". Spec Kit plans live in `specs/<dir>/plan.md` and are never archived. The review-presence gate scanned only `.process-work/plans/archive/` and could not see the standard path.

**What changes.**
- **Speckit presence** (`speckit_unreviewed` in check_review): a fully ticked tasks.md plus a Tier-2+ plan without a waiver needs the clearing pass. `finish.py` blocks hard at the merge ritual. The review gate reports a Note only: a hard block at push would redden every push between the last tick and the review. `commits.md` names the speckit variant of the archive step: publish_and_prune instead of an archive move; finish prints the finished directories one by one.
- **Owner-brief note** (speckit gate): a spec.md without an Owner-brief section gets a Note. 2 of 6 new specs in the reference project had forgotten the brief.
- **Waiver honesty:** a plan with an `issue:` anchor owns its waivers there. Only trackerless waivers are flagged. The digest is aligned.
- **ADR noise:** the intent Note no longer applies to rejected/superseded records; historical records have no endorsement axis.

Details: SP64

## v2.7.0 — Owner loop: the human as a real node · 2026-08-13

**Why.** The maintainer's finding "I hardly review the slices, and often don't understand the specs". The human becomes a real node of the loop graph, with defined inbound edges instead of polling.

**What changes.**
- **Owner brief.** Mandatory preface of every spec: five plain sentences without jargon or file names (what / why / visible change / risk / "Your call"). It leads the staged issue comment and makes the influence window usable.
- **`human_digest.py`.** The inbound edges as ONE page: waiting specs with their brief and open questions, merges of the last N days, standing waiver debts, fix clusters. Read-only; missing sources are named instead of silently left empty.
- **Sampling audit.** One merged package per week, chosen deterministically by ISO week (no re-rolling). Review by exception instead of diff competition with the model reviewer (`verification-independence.md`).
- **owner-digest workflow.** Weekly on Monday plus dispatch; the digest goes into the step summary.

Details: SP63

## v2.6.2 — Using [P] groups for real · 2026-08-13

**What changes.** "Parallel edit, serial commit":
- [P] tasks run as concurrent subagents in the same worktree. Subagents edit their disjoint file package and deliver test evidence; they never commit.
- The orchestrator serializes the tail of each task (atomic commit, checkbox, gate) in dependency order.
- `/plan` sharpens [P] to "no shared touchpoint", including barrel exports, manifests and generated indexes. A wrong marker would be a working-tree collision.

## v2.6.1 — Slice economy sharpened · 2026-08-13

**Why.** The #688 finding "50 tasks, extremely long".

**What changes.**
- **Task grain.** One task = one behavior, test AND implementation. The TDD order lives IN the task, never as a task pair. The task is the unit of planning, checkbox, gate run and report: 50 tasks that could be 30 pay the ritual twenty times for nothing.
- **Tier per stage.** With stage merges, each stage carries its own tier. A behavior-neutral extraction stage with mechanical proof is Tier 2, even if the behavior-changing stage is Tier 3 (`risk-tiers.md`).
- **Mechanics before judgment.** All mechanical detectors run BEFORE the review bundle and their results go into it. The model reviewer verifies the mechanics layer instead of discovering it. A grep-able finding costs cents mechanically and a round via review.

Details: #688

## v2.6.0 — Longitudinal view: patterns between packages · 2026-08-13

**Why.** The finding in the reference project: "53 fix commits in 5 days, one scope cluster with 13 fixes, each one through all gates individually". The process governed the single package but had no organ for patterns BETWEEN packages.

**What changes.**
- **Fix-cluster advisory** (`process_kpis clusters`): Rule 6 across sessions; the counter lives in git. The debug command, `workflow.md` and the review checklist carry the stop rule "third fix on the same behavior = missing specification".
- **Invariants home.** Decision-record type `invariant` for cross-feature behavior rules. A `## Test` section is mandatory as the enforcement twin from Accepted; the decisions gate checks it.
- **Degradation debts.** `review-waived:`/`spec-waived:` without an issue ref gives a Note, "a debt with an owner".
- **KPI trigger.** Monthly process-kpis workflow: a KPI without a trigger does not exist.
- **`/finish`** (`finish.py`): the merge tail as ONE verdict. Clearing pass, green gates, clean tree, then the remaining ritual in order. Read-only; built against the observed tail failures #652/#653/#660.

Details: SP62, #652, #653, #660

## v2.5.2 — Round economy of the review loop documented · 2026-08-12

**Why.** The maintainer's finding "on every deviation the whole chain runs". The `--since` delta bundle had existed since v2.3.0, but no document and no command taught it.

**What changes.** `/review`, `workflow.md` (Review) and `verification-independence.md` now describe three price rules:
- Bundle the findings of a round: one fix pass, one push. Every additional head commit pays the push gates and tests again.
- Round 2+ as a delta bundle via `--since`. The full diff stays digest-bound; Tier 3 always reads in full.
- Rebase once, before the first round. Any later rebase invalidates the digests.

## v2.5.1 — Model routing as harness default · 2026-08-11

**What changes.**
- `model:` frontmatter on the phase commands: `/brainstorm` and `/plan` on the strongest model (judgment density: a spec or plan error costs a multiple downstream), `/review` on `opus`. Execution inherits the session working model.
- The `/speckit-*` commands stay untouched, since a Spec Kit update overwrites them. Routing lives in the wrapper commands.
- Docs in the speckit module updated.
- No new gate and no config axis: routing stays engine/harness behavior.

## v2.5.0 — Visibility package: issue at the idea, stage publishing, review economy · 2026-08-08

**Why.** From the maintainer's lifecycle review. The human's window of influence is the spec/design phase.

**What changes.**
- **Issue at the idea instead of the plan.** The tracking issue is created on brainstorm entry. An active `specs/*/spec.md` without an `issue:` line is a hard failure (issue-before-spec in the issues gate).
- **Stage publishing.** `publish_and_prune --stage` posts the finished spec (and design) as a dated read-only snapshot comment on the issue and prunes nothing. New issue comments are clarify input before `/plan`.
- **Review economy for subagent engines.** Task reviews only for owner/integration tasks (mechanics in the collective checkpoint). Round 2+ as a `--since` delta. The engine's final whole-branch review IS the attested merge review: one deep review on the strongest model instead of two (~5 instead of ~9 runs per #651-sized package).

Details: SP61, #651

## v2.4.0 — Engine freedom and hygiene · 2026-08-08

**Why.** From live operation of the SpecKit/Superpowers combination in the reference project.

**What changes.**
- "The execute engine is free, the artifacts are not": subagent-per-task engines are sanctioned in execute as long as the artifact invariants hold and the merge review remains the attested one.
- The **prose-tier detector** in the review gate makes the third-party-skill failure mode loud: a plan mentions "Tier N" but declares no `tier:` line, so all tier-keyed gates are unarmed (found live on #651).
- **"Merge leaves no residue"** in `commits.md`: delete the branch, `git worktree remove`/`prune`.
- The dispatchable **cleanup-branches workflow** (patch-identity-based, dry-run default, open-PR protection), in the repo and in the template.

Details: SP60, #651

## v2.3.0 — Downstream backflow from the DATEV fork · 2026-08-07

**Why.** The four generalizable contributions from the private DATEV fork, taken over by patch handoff (the fork may not open PRs).

**What changes.**
- **Copier render cache in the tests.** Each answer set renders once per session; each test gets its copy. The full suite drops from ~4.5 min to ~1.5 min.
- **Gate preflight before the review bundle.** Red gates do not produce a review-ready bundle; `--skip-preflight` is the deliberate way out.
- **Bounded delta re-reviews.** `--since` with full-artifact binding, carried-over prior findings and Tier-3 rejection.
- **Advisory finding ratchet.** `gate=judgement|possible|<rule>` on FINDING lines; `possible` marks automation candidates as a Note, never blocking.

Deliberately NOT taken over: model routing, CODEOWNERS hardening, mandatory SBOM, platform pinning (fork-local, congruent with the Lean pass) and the decision-adoption module (parked until usage evidence exists; the intent axis already carries the light version).

Details: SP59

## v2.2.0 — Plans have one home; license changes to Apache-2.0 · 2026-08-07

**Why.** An observation in the reference project: topic-triggered third-party skills (Superpowers brainstorming/planning) with their own file conventions can silently bypass duties that depend on artifact presence. A plan that never lands in `.process-work/plans/` triggers neither clarification nor review presence.

**What changes.**
- `journal-state-plans.md` fixes "Plans have exactly one home": skills help *within* phases, the artifact has exactly one home.
- The review gate gets the **unhomed-plan detector**. A `tier: 2+` declaration outside the sanctioned homes (`.process-work/`, `specs/`, `docs/process/`, harness directories) is a hard failure. Archives count as history; Tier 0/1 and fenced quotes stay out.
- **Spec-before-plan** in the speckit gate: an active Tier-2+ plan references its `specs/` directory or carries a reasoned `spec-waived:` line. Skipping the Spec Kit interrogation is a documented decision, never a silent behavior.
- License change (2026-08-07, after v2.1.0): from the Prosperity Public License 3.0.0 (non-commercial) to **Apache-2.0**. The core is deliberately open (open-core strategy: future commercial add-on components remain separate works).
- The MIT attribution for the two templates derived from GitHub Spec Kit is caught up (`THIRD-PARTY-NOTICES.md`, also rendered in adopter repos; provenance comments in the files).

Details: SP58

## v2.1.0 — Reference backflow: four process lessons and two ADR-gate fixes · 2026-08-07

**Why.** Four process lessons from live operation of the reference project that the generic core demonstrably still lacked after adoption. Two brownfield defects in the decision-records gate, uncovered by the ADR-corpus adoption in the reference project.

**What changes.**
- **Rule 1 sharpened.** Subagent summaries are `[assumption]` until spot-checked. The stop word "source?" means tool proof or retraction.
- **Review-round cap in the workflow.** After two unsuccessful review→fix rounds, back to planning. This is the review counterpart to the two-attempts Rule 6.
- **Bookkeeping discipline in `commits.md`.** Journal, plan and state travel in the work commit, no `record` chains. Evidence without an SSOT goes into the issue comment.
- **Anchor-budget check in the doc-drift gate.** Anchor > 200 lines gives a Note, never a Fail. It is the mechanical guard for the "does it drift on a refactor?" discriminator.
- **Status enum extended** by `Rejected` (a proposal that never applied) and `Deprecated` (applied once, now discouraged). Otherwise a dead proposal would stay `proposed` forever.
- **Seed record renumbered** from `adr-0001` to `adr-0000`, so an existing corpus that starts at 0001 can move in without collision.

Details: SP57

## v2.0.0 — Lean standard: refactoring onto GitHub + Spec Kit + pre-commit + dev-process kernel · 2026-08-06

**What changes.**
- The large refactoring (SP56, lean-standard) moves the process onto the standard stack GitHub + Spec Kit + pre-commit + dev-process kernel, after an independent design review (report: `.process-work/reviews/2026-08-06-speckit-hybrid-design-review.md`).
- Removed: the GitLab CI adapter, parity, `attention.py`/`who_is_working.py` (the GitHub UI takes over), `story_order` and the work-log axis of the registry, the custom hook installer, the artifact-v1 certificate ritual. Telemetry now runs on the three target KPIs only (convergence, cost, CFR). Profiles and toggles give way to the standard setup with a single `regulated` switch. contract-first and contracts-drift are merged into `contracts`.
- Rebuilt: feature-registry is now the feature inventory (capability → acceptance → test, hermetic). The hooks run on the pre-commit framework. github-master is registry-free (snapshot by issue number, DoR-at-rest, board consistency). Review is reduced to one attestation with an opt-in diff digest (verified instead of ritual).
- Built: the `speckit` module as the standard specification path — constitution pointer with gate guard, EARS/test-obligation overrides, command wrapper with kernel duties, clarification gate over `specs/`, `publish_and_prune` merge ritual with verified publish + SC accounting and flow-forward degradation.
- The change of product frame is documented in the README, and the exit scenario (freeze the pin) is recorded.
- Also the token-lean pass (`process_context.py`, prime diet, analyze/converge only for Tier 3).
- Also the Windows path fix: no more `|` in template paths, the OS smoke matrix is green again.
- **Breaking**: module keys and the install dialog have changed.
- SP55 (spec-deepening) deepens the specification phase with borrowings from GitHub Spec Kit, schema-preserving (analysis: `docs/analysis/2026-08-06-speckit-comparison.md`):
  - `[NEEDS CLARIFICATION: …]` marker convention in brainstorm instead of silent assumptions.
  - `design-template.md` as a core doc scaffold (intent, constraints, touchpoints, numbered EARS ACs, alternatives, open questions, Tier 3 threat question).
  - The review checklist gains "Specification quality" (testable criteria, honestly resolved questions, what/how separation, DoR-R2 twins).
  - Fifth **core gate** (`check_clarification.py`): an unresolved marker in an *active plan* is a hard failure (the plan presupposes an approved design), in the active design only a note (mid-flight stays green), the archive is history. A fenced block counts as a quotation, as in the review gate.

**Update.** Existing adopters migrate via `copier update` with an explicit `modules` dict (BOOTSTRAP, "Later").

Details: SP55, SP56

## v1.37.0 — Cross-platform hardening: `git` + `uv` as runtime contract · 2026-07-10

**What changes.**
- `git` + `uv` are the uniform runtime contract on Linux, macOS and Windows.
- The PEP-723 gate runner needs no system-wide Python and no PyYAML.
- Hook installation, hook logic and issue body generation exist as portable Python implementations behind compatible shell launchers.
- Claude, Copilot and AGENTS.md can be combined independently.
- New: OS smoke matrix.
- Manifest values are validated fail-closed.
- The release tag must match the project version.

Details: SP54

## v1.36.0 — Methodology fitness check: EARS pattern catalog and spike path · 2026-07-10

**Why.** The principles check of the chain brainstorm→EARS→plan showed two gaps.

**What changes.**
- The **EARS pattern catalog** is in the DoR doc: all five forms (ubiquitous/event/state/unwanted/optional), with unwanted behaviour as the natural form of the negative cases that R2 demands.
- The **spike path** in `workflow.md` covers open-ended work: timeboxed, the output is knowledge (journal/design/decision record), never product code. A follow-up feature runs through the normal cycle, the prototype is not promoted. Stopping at the timebox is a success.

Details: SP53

## v1.35.1 — Diverse audit of v1.35.0: four new angles, fixes · 2026-07-10

**What changes.** SP52 is a diverse audit of v1.35.0 from four deliberately new angles:
- Pragmatist/economics: verdict "process with unusually little theater", about 5.4k tokens of reading tax per session, gates 0.2–0.8 s, over-engineering candidates acquitted.
- Multi-harness degradation: 9 render combinations.
- Lifecycle: upgrades v1.13.0→HEAD conflict-free and byte-identical, 10x growth under 0.9 s.
- Technical writer over the SP48–51 prose.

Fixed:
- The Copilot anchor gets the route to workflow/commits.
- BOOTSTRAP "Later" without `--skip` (stale kernel after upgrade reproduced) and a hook reinstall note.
- `trace` without bare-digit noise (#7 matched 68/68 plans).
- The bundle has a `--plan` filter and a hard unknown-flag error.
- Soft note for non-archived Tier 2+ plans.
- doc-drift scans the Copilot instructions file.
- `gate_runner` names the hand-edit cause.
- No-CI DoR is satisfiable (hooks as authority).
- Quick questions with a single owner in `workflow.md`.
- Retention honesty.
- R2 owns the four acceptance cases.
- About 15 writer precision fixes.

Report: `.process-work/reviews/2026-07-10-sp52-diverse-audit.md`.

Details: SP52

## v1.35.0 — State-of-the-art comparison: six gaps closed

**Why.** The research (DORA, Diátaxis/arc42, supply chain, diagrams-as-code, AI guardrails) showed six gaps.

**What changes.**
- `testing.md` as a core doc: suite shape as a pyramid heuristic, property-based testing, regression pins, mutation testing on critical logic, honest coverage ceiling (trend instead of threshold gate). Wired in via rule 5 and the review checklist.
- `releases.md` as a core doc: SemVer, curated changelog, tag ritual with the version-triad invariant. Wired in via `commits.md`.
- Threat question for Tier 3 in brainstorm and review checklist ("What could an attacker do with this change?" — assets/inputs/trust boundaries).
- Diagrams-as-code convention (Mermaid in Markdown, diffable in the PR; the gate still parses no diagrams) in the arch-docs module doc and the overview scaffold.
- Platform hygiene in the onboarding DoR (secret scanning + push protection, Dependabot/Renovate), honestly framed as network services, not a hermetic gate.
- Branch lifetime "days, not weeks" in `commits.md` (small-batch finding behind trunk-based).

Details: SP51

## v1.34.1 — Deep audit: one blocker closed, SP49 regression fixed · 2026-07-10

**What changes.** SP50 is a deep audit of the cleaned-up state, from four independent angles with an execution mandate: adversarial, coherence, fresh adopter, robustness.
- 1 blocker closed: fence tracking is length-aware (quoted waivers in nested fences cleared the review/issue gate).
- SP49 regression fixed: only real issue refs count as clearing work-ids; the ref grammar moved to `check_review` (one owner).
- OSError diagnostics instead of tracebacks.
- security-floor with a regex backtracking budget and a zero-in-scope note.
- `gate_runner` with a gate timeout and bytecode-free.
- The last `adr_exists`/`_unfenced` copies are consolidated.
- `gh_board` argument hygiene.
- BOOTSTRAP update recipe for HEAD installs.
- `start-here` order and `git init -b main`.
- Commit traceability convention.

**Effect.** Adopter verdict: a solo dev reaches a green gate run and the first reviewed change without help.

Report: `.process-work/reviews/2026-07-10-sp50-deep-audit.md`.

Details: SP50

## v1.34.0 — KISS cleanup: one owner per behavior

**What changes.** SP49 cleans up on the basis of three parallel deep sweeps (dead code, duplicates, docs vs. code).

One owner per behavior:
- `check_review` owns the plan-field grammar and `_unfenced` (`check_issues`/`trace` import them). The issue regex is unified, cross-repo refs now also clear the review gate.
- `check_decisions` owns `adr_exists` (replaces 3 divergent copies).
- The review bundle imports the kernel block extraction (second block → honestly unavailable instead of silently the first).
- `gh_json` has one owner in the github-issues module.
- Non-importable twins (sbom/security-floor git helpers, EARS/epic heuristic) are pinned by a template test.

Functional:
- The sbom example policy no-opped on root manifests (bare+`**/` pairs).
- Dead manifest globs without a parser removed.
- `sbom` was missing from all three adapter module lists (test pins against `copier.yml`).
- `gh_board --push` no-op stub removed.
- github-master reports an empty mirror as advisory instead of silently OK.
- The `trace` FINDING matcher requires `key=value`.

Plus 12 doc coherence fixes ("one tier weaker" struck, DoR/DoD deviation channels separated, Copilot review prompt carries the grammar, among others).

Details: SP49

## v1.33.0 — Telemetry honesty: project individuality as a binding ceiling

**What changes.** SP48 documents the individuality of projects as a binding ceiling:
- Numbers apply only within a project against its own baseline (trends, ratios, catch/escape events as the most robust class).
- No cross-project benchmarking.
- Cockpit thresholds are starting values for recalibration.
- Goodhart/self-grading caveat.
- The module doc section "honest ceiling", the cockpit docstring and the README carry this.
- Module doc and cockpit are pinned by a template test.

Details: SP48

## v1.32.1 — Arc review of the depth arc: four defects in the bundle tool closed · 2026-07-10

**What changes.** An arc review of the depth arc with two independent reviewers.
- Four executable defects in the bundle tool closed: fence corruption on Markdown diffs, non-UTF-8 crash, IndexError on a missing option value, subdir invocation lost root sources.
- The grammar claim is honestly limited to the REVIEW half; the FINDING tokens are pinned to `check_issues` by a template test.
- The adr resolution sees raw rules, deviation counts only as a real heading, the dor slot has an exact key set.
- Doc coherence: conditional arch-onboarding reference, hard-path clause in github-issues.

## v1.32.0 — Depth II and III: architecture boundaries as floor rules, review bundle

**What changes.**
- SP46 (depth II — architecture boundaries as floor rules): there is no 14th module, the existing owner is used. security-floor can already do rules scoped by `applies_to`. New: optional `adr` field per rule (dangling links are a hard failure), example architecture rule, module doc section with an honest ceiling (regex floor, not an architecture review), ratchet trigger and arch-onboarding cross-reference.
- SP47 (depth III — review bundle as a portable reviewer interface): `make_review_bundle.py` (core) builds the one self-contained document from kernel, checklist, product frame, plans, diff and REVIEW grammar, which is imported directly from `check_review`. The FINDING tokens are pinned to `check_issues` by a template test. Dispatch recipes per harness are in verification-independence, `/review` points to the tool.

Details: SP46, SP47

## v1.31.0 — Depth I: DoR as a gate

**What changes.** SP45 makes the Definition of Ready a gate.
- `gh_sync` derives the ready facts from the live issue (typed/EARS/`## Deviations` body note as the named escape) and stores them as the `dor` slot in the snapshot.
- The hermetic github-master gate fails hard when an in-progress story links a non-ready issue without a deviation. Proposed has not started yet, done is the review gate's matter.
- An old snapshot degrades honestly to the re-sync note.

Details: SP45

## v1.30.1 — Merge-gate review of the v1.26–v1.30 arc · 2026-07-10

**What changes.** Merge-gate review of the v1.26–v1.30 arc, two independent reviewers.
- Blocker in the branch-protection script closed: an existing rule is never overwritten again (GET-404 ambiguity).
- The kernel gate enforces exactly one block and rejects an empty canon.
- `trace` precision: no bare-number grep, empty query refused.
- The ratchet is the single owner with all 13 modules.
- README/update-semantics coherence.

## v1.30.0 — Traceability as a tool: `trace.py`

**What changes.** SP44 delivers `trace.py`: the whole story of a unit of work in one command.
- Sources: story, issue (snapshot offline first, then `gh`, otherwise only the ref), active/archived plans, commits, parsed `REVIEW work=` attestations, reports including FINDINGs.
- Read-only, core.
- Unreachable sources are named instead of silently skipped.

Details: SP44

## v1.29.0 — Quick wins "reliable + readable": `setup_branch_protection.sh`

**What changes.** SP43:
- `setup_branch_protection.sh` is the one step that turns "gate runs" into "gate blocks", as an idempotent one-liner (non-destructive, honest failure modes for private repo/free plan).
- The Actions job id is aligned from `gates` to `process-gates`, so that the documented required-check context can be met at all.
- The SP history is moved from the README into this CHANGELOG.

Details: SP43

## v1.28.0 — Profiles instead of 13 module booleans, hardening ratchet

**What changes.** SP42 (meta-review "reach before depth" for solo devs/small teams):
- **Profiles** instead of 13 module booleans: one `profile` question (minimal/solo/team/custom) derives the module default; explicit `modules` still overrides.
- The **hardening ratchet** in start-here: switch a module on when its trigger occurs — first persistence → security_floor, second surface → parity, and so on. Loosening is a documented process decision.

Details: SP42

## v1.27.0 — Kernel survives compaction

**What changes.** SP41:
- A self-healing directive *inside* the kernel block: on resume/compaction, re-read kernel and rules. It is byte-identical in all four copies and therefore cannot be removed past the kernel gate.
- Phase re-hydration in `/execute`, `/review`, `/prime`.
- Honest limit and per-harness reality documented in start-here — a gate does not see the live context.

Details: SP41

## v1.26.0 — Kernel integrity as the fourth core gate: `check_kernel.py`

**Why.** A derived process made visible the gap "rules forgotten because ungated".

**What changes.** The always-loaded rule block must be byte-identical to `kernel.md` in every present anchor.

**Effect.** A silently deleted or changed rule blocks the merge.

Details: SP40

## v1.25.0 — 4-perspective functional audit: sbom gate hardened

**What changes.** SP39 (4-perspective functional audit):
- sbom gate hardened: SPDX `OR`/`AND` evaluation, only the root component is exempt, multi-license conjunction, exact coverage names, no doc-drift red run on a fresh render.
- `attention` counts only existing tests.
- DoR/DoD and tier route coherence.
- `ARCHITECTURE-OVERVIEW.md` is `.jinja`.
- BOOTSTRAP `github_master` key.
- Internal sprint refs removed from adopter code.

Details: SP39

## v1.24.0 — Binding Definition of Ready & Done

**What changes.** SP38:
- The binding **Definition of Ready & Done** as the core doc `definition-of-ready-and-done.md`: per unit of work, enforcement delegated to existing mechanisms, living checklists.
- The name collision with the project onboarding maturity in `start-here.md` is resolved.
- Hooked into brainstorm/review, rule 7 and the review checklist.
- Consolidation of backport patch 0013.

Details: SP38

## v1.23.0 — Backport batch 2: coordination dashboards

**What changes.** SP37 (backport batch 2):
- Read-only coordination dashboards under `github-issues`: `who_is_working.py` (concurrency preflight) and `attention.py` (where a human should look, including issue hygiene).
- Parallel-agents workflow section.
- The label-mutating lifecycle tools and the `status:hold`/`awaiting-ack` overlays are deliberately left out.

Details: SP37, #22

## v1.22.0 — Backport batch 1: pre-push checks pushed commits, `sbom` module

**What changes.** SP36 (backport batch 1 from the parallel process branch):
- pre-push checks the **pushed commits** instead of the working tree (throwaway worktree).
- New opt-in **`sbom`** module with CycloneDX license attestation.
- feature-registry advisory for under-granular acceptance.

Details: SP36

## v0.1.0 – v1.21.0 — Sub-projects SP1 to SP35 · 2026-07-01 – 2026-07-07

**What changes.** SP1 to SP35 shipped by `v1.21.0`:
- SP1 (Foundation).
- SP2 (architecture onboarding).
- SP3 (feature-registry, github-issues, contracts-drift).
- SP4 (git-hooks, contract-first, parity, security-floor).
- Capstone (command-adapters, `v1.0.0`): the full command set of the reference project, harness-native.
- SP7 (ci-adapters): GitLab CI and install fallbacks.
- SP8 (english-canon): English canon and honest economics.
- SP9 (audit-fixes): false greens closed, failure modes speak.
- SP10 (telemetry): GRADE trace and KPI cockpit, efficiency measurable.
- SP11: re-audit and public readiness.
- SP12 (verification-independence): verification independent, tier-graded.
- SP13 (anchor-guidance).
- SP14 (junior-legibility): review checklist, tier recognition.
- SP15 (arch-docs): arc42/C4-lite architecture documentation module.
- SP16 (review-breadth): performance/observability dimensions.
- SP17 (parallel-friction): journal sharding, parallel-efforts docs.
- SP18 (decision-records): typed decision record and core integrity gate.
- SP19 (review-enforcement): review independence as a gated attestation.
- SP20 (issue-centricity): issue-before-code for Tier 3+, sharpened claim discipline.
- SP21 (dependency-sequencing): `blocked_by`, cycle gate and ready-order tool.
- SP22 (github-master): issues as SSOT via a hermetic snapshot gate and sync.
- SP23 (sub-issues): `parent` decomposition, cycle/drift gate, hierarchy view.
- SP24 (project-board): hermetic column consistency gate and board automation.
- SP25 (github-master honesty pass): freshness disclosure and honest doc fixes.
- SP26: rule-5 consolidation — increment-vs-rewrite decision and gate refactor.
- SP27 (story-lifecycle-closure): done hard-requires an issue, DoR/DoD view, discovered-work inbox.
- SP28 (audit-hardening): six persona audits across two models — two live bugs fixed, consensus findings cleared, verified branches regression-secured.
- SP29 (tier-model): the scale collapsed from 0–4 to zero-based **0–3**. Tier 0 "direct commit", which was effectively fictitious under PR/merge duty, is folded into Tier 1; every remaining boundary carries weight; gate thresholds and anchor/docs are remapped.
- SP30 (decision-flow-wiring): decision records are hooked into the phases — brainstorm reads them as constraints, plan names its decision context, execute stops on a discovered fundamental decision, the review checklist asks about a missing, contradicted or silently obsolete record.
- SP31 (product-frame): `PRODUCT.md` as a **core** artifact — product frame with goals/non-goals/constraints, created in the init dialog, read by all phases as a direction constraint, always-active gate: missing is hard, not-onboarded an honest note, placeholder-after-onboarding and dead refs hard.
- SP32 (review-visibility): audits/reviews including prompt, verdict and findings as a report artifact and GitHub issue — `FINDING` grammar, `publish_review.sh` with campaign bundling under a parent issue, hermetic binding (unpublished without waiver hard, follow-up finding without issue hard, split campaign hard). Discovered work in the correct form: `finding`/`bug` templates with EARS ACs and an origin section, back-link and comment on the originating item as a convention.
- SP33 (gate-hardening from a 4-session audit): 8 reproduced gate defects closed — tier range validation, report header split at every level, shared fence/bullet discipline for REVIEW/GRADE, decisions section parser, github-master fail-clean, campaign ref normalization, symbol word boundary, code_roots scalar. Plus the patch `v1.20.1` from the SP33 review: Unicode digit crash in the tier check, header split on every heading style, honest symbol boundary.
- SP34 (flow-closure): plan archiving as a named merge step, baseline commit bypass, tracker-less waiver for done story and follow-up finding, neutral `kernel.md`, reviewer grammar in `/review`, sharpened Tier 1/2 boundary and Tier 0-1 as a self-check band.
- SP35 (economics/discoverability): the anchor lists active module docs, `/quick` carries its own steps, `/prime` reads inbox, which-artifact-when router, multi-agent SSOT honesty, mid-size trap named.

Details: SP1–SP35
