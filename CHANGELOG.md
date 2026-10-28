# Changelog — dev-process

What changed in each release, why, and what it leads to — newest first. Each entry
has the same parts: **Why** (the problem that was observed), **What changes** (as a
project using the template sees it), **Effect**, **Update** (steps for existing
projects), and **Details** (the plan with the technical particulars, the issues);
a small fix release may leave out Effect, and an entry without a plan or issue has
no Details line.
A few plain sentences per release: [NEWS.md](NEWS.md). Deutsche Fassung:
[CHANGELOG-DE.md](CHANGELOG-DE.md). Releases before v2.28.2:
[docs/changelog-archive.md](docs/changelog-archive.md).

## v2.80.0 — Measure where the process grows, and cut it where it costs · 2026-10-28

**Why.** Projects slow down as they grow: Kenni clearly, spkiam beginning. An eight-week analysis of Kenni (9,111 commits, 281 train merges) found the share of pure process commits rising from about a third to two thirds, and the review rounds rising with a work's size and with the number of stacks it spans. The analysis ran by hand, because the KPI cockpit counted `works 0` on every clone: it took its merged works only from host-local data (#341). Cost per work (#314), value per round (#318) and escapes per tier (#320) were open questions without numbers.

**What changes.**
- The cockpit reads merged works from git: every train merge (`train: merge <branch>`) and every `finish` archive commit on the integration branch is a merge event; its issues come from `Closes`/`Refs` lines, else from the plans it carries. A work is an issue with its events (stacked phases sum up); start is the earliest author time, end the last event. The header of each report names the source of its population, mixed ranges, works joined to no plan or REVIEW line, commits outside any merge range and a shallow clone. Escapes, the integration branch and the process version come from `tower.integration_ref`; a failed git read is unknown, never zero.
- `works` (new, #314): one row per merged work — tier, kind (`fix`, `change`, `template-update`), plan and code rounds, lead time, session time and sessions per model family where the host has them, product lines; median and p90 per tier and kind.
- `rounds` adds a table per round number (1, 2, 3, ≥4), code and plan reviews apart: median blockers, share of works still blocked, share of blocks on lines unchanged since round 1, median cost where the host has it (#318).
- `baseline` adds per tier: merged works, escapes over closed windows (open ones beside), median rounds and tokens; under about 20 works marked `thin` (#320).
- `load` (new): week by week over merge events — process and product lines and their ratio, median process files per merge, merges without a product file, the lines committed outside any merge range (a steward's records straight on the integration branch), the trend.
- `size` (new): review rounds by a work's product lines (<200, 200–500, 500–1500, >1500) with rounds per 100 product lines and process lines per product line per band; one stack against several (stacks from `testing.local.json`); the code files most works touched; the share of product lines on files that no longer exist.
- `report` runs `baseline`, `works`, `load` and `size` too. `load` and `size` classify paths with `tower.is_process_path` and say they are a proxy.
- `/plan` advises, without a field or gate: a plan expecting well over about 500 product lines checks a split into stacked plans along the contracts, work across stacks checks cutting the contract first; every split costs a fixed set of process, and `size` shows in the project whether it pays. An open approach starts with a throwaway spike (no review, no merge; its result is a plan). `/review`'s size warning and `/brainstorm` point there.
- `.process-work/.gitignore` ignores generated files under `reviews/` (`*.log`, `*.jsonl`, `*.json`, `*.txt`, `*.gz`, `*.patch`, `*.diff`); reports (`*.md`) and images stay versioned.
- A rule budget: a new check names its expected yield; one that over eight triaged weeks never blocked alone and found no confirmed defect is a candidate for removal — without eight covered, triaged weeks the answer is unknown. The monthly review asks for it.

**Effect.** The cockpit answers on any clone where the process load goes, how size and stacks drive rounds, and what a work costs per tier; the relief rules are advice the project can check against its own numbers instead of new gates.

**Update.** A pure update. A project that already versions generated files under `.process-work/reviews/` removes them from the index once (`git rm -r --cached` on the new patterns); reports and images stay.

**Changed sections.** `improvement-monthly.md` (What you review), `journal-state-plans.md` (Review reports), `optimization.md` (The process as a check graph), `telemetry.md` (The KPI cockpit), commands `/brainstorm`, `/plan`, `/review`

Details: [Plan](docs/analysis/2026-10-28-v2.80.md) #341 #314 #318 #320

## v2.79.0 — Gates that hold in daily work, and the invariant in the plan · 2026-10-27

**Why.** Since v2.78 the consuming projects reported gates that decided wrongly in daily work. The merge train boarded a branch the steward had held with `report.py blocked` (#326). Two branches passed their branch push and review and failed only at the push to main, because a Transitions test cell named no path (#327). attest did not know test titles from `it.each` tables (#328) nor `*.vitest.*` files (#300). Interactive workers stalled for hours on a permission prompt for a shell form the allowlist cannot match (#323). The first project on a fresh install (spkiam) added `finish.py` without a remote (#330), attest messages that left the next step to guesswork (#332), and plan rounds that blocked on a wrong count (#329). Separately, three works needed about six code rounds each and converged only once their design named an explicit invariant (#312).

**What changes.**
- A branch whose latest holding report is a steward's or worker's `blocked` does not board the train, whatever its archived plan or REVIEW records say; the reason names the report. Only a newer `pushed` or `review-pass` releases it — `idle` from `dispatch stop`, `planned` and `done` do not. The train's own `blocked` (a conflict, red with it aboard) describes a run and holds nothing. A published report without a worker or with a non-numeric epoch is skipped instead of stopping the train. The train reads the reports of this host and the published ones of other hosts (`report.py blocked --sync`); it fetches them best effort.
- `plan-structure` owes test evidence from the first push of a bound Tier 2+ plan, not only once a task is ticked or at the merge push: every `AC-<id>` line and every Transitions test cell names `<path>::<test>` (the file may not exist yet) or `struck — <reason>`.
- A Transitions section carries an invariant line: `Invariant: <statement> — owner: <owner> — <path>::<test>`, or `Invariant: none — <reason>`. The gate reads it from the right, so the statement may contain ` — `; the owner may stand in backticks. The plan review's state-space step asks whether it holds for every transition.
- attest reads a test title as the literal that directly follows the test keyword — `it("x"`, `it.only("x"`, `test.skipIf(c)("x"`, RSpec `it "x" do`, Rails and ExUnit `test "x" do`, a call split after `it(` — so a table cell that mentions `should` declares nothing. An `it.each`/`test.each` title declares the names its template covers (`%d`, `%i`, `%$` only numbers, `%s`, `$name`, `${…}` any text); `describe.each` declares no test. Whether a table row produces exactly that name is not checked, and a string whose text is a whole test call still declares.
- `*.vitest.*` counts as a test file in attest's defaults, the review bundle and the human digest.
- attest refuses a `--journal-dir` that is the shard it adds itself (`issue-<N>`), names the full SHA when a short one resolves uniquely, and on a code-review block prints the round for ROOT-CAUSE and REPLAN and what the pass will need (`AC-<id>` lines, the `red_evidence.py` call). `red_evidence.py` refuses the same shard.
- Every worker prompt of the Claude policy ends with a shell-form block: one simple command per Bash call, no shell variables, expansions, brace groups, subshells or `eval`, files written with Write/Edit, reading with Read/Grep/Glob. The policy key `worker_shell_form` replaces it (`""` turns it off); the Codex variant ignores it. The remote hand-over names `report.py … --sync` instead of environment variables.
- `finish.py` in a repository without any remote merges locally: it runs the gates as the push to main would, runs the suite given with `--tests` (a bare `--tests-passed` is refused: no pre-push runs it), rebases onto a moved local main, fast-forwards, deletes the merged branch, and writes no certificate. Remote-tracking refs the gates anchor on, left without a remote, are refused with the command that removes them; a failing ref listing is a blocker too. A repository with another remote than `origin` keeps today's path.
- A wrong number or list in a plan that the work acts on (a count a test will check, the files a task changes) is `minor` with `action=fix`, never blocking unless it hides an undecided behaviour; a tally nothing acts on stays a `nit`.

**Effect.** A held branch stays held until someone says it is fixed; a plan's test evidence is complete before the first review instead of at the merge; table-driven Vitest and Jest tests can be traced; workers no longer wait on prompts the allowlist cannot answer; a local-only project finishes without a failing push.

**Update.**
1. Tier 2+ plans in flight on a branch: from the first push after the update every AC line and Transitions test cell needs `<path>::<test>` or `struck — <reason>`, and every Transitions section an `Invariant:` line. Plans on main and plans archived on main are not affected.
2. After a steward's or worker's `blocked` report, release the branch with `report.py pushed` after the fix, or `review-pass`; pushing alone no longer releases it.
3. A project that overrides `review_evidence.test_files` in its policy adds `*.vitest.*` itself.
4. A project that appends its own shell-form text to worker prompts sets `worker_shell_form`, or drops its own copy.

**Changed sections.** `commits.md` (Merging), `design-template.md` (Sections), `journal-state-plans.md` (Plans), `refute.md` (Refuting a plan), `review-checklist.md` (Completeness), `tower.md` (Dispatch and the model policy), `train.md` (Boarding — computed, never claimed; The run), `verification-independence.md` (The review bundle — the portable interface to any reviewer), commands `/execute`, `/finish`, `/plan`, `/review`

Details: [Plan](docs/analysis/2026-10-27-v2.79.md) #326 #327 #312 #328 #300 #332 #323 #330 #329

## v2.78.1 — A pass rests only on evidence that reaches the repository · 2026-10-25

**Why.** `attest` read ROOT-CAUSE and skip lines from every journal shard in the worktree, also uncommitted ones, while its commit carried only today's shard and explicit `--with` paths. Evidence in another day's uncommitted shard could authorize a committed pass without ever landing in the repository. Separately, `plan-structure` accepted a `## Transitions` table whose delimiter row named fewer cells than its header.

**What changes.**
- The evidence owner counts a journal line only when it is committed at the reviewed head or lies in a file the same attestation commits (today's shard, `--with`). Only this work's counted evidence — its ROOT-CAUSE and the skip kinds the journal may carry — can refuse a pass; foreign work and kinds read from the plan alone stay invisible. Such a line only in another uncommitted shard is refused with its file and line, never counted silently.
- Evidence appended to today's shard lands with the REVIEW line as before; no new record list sits beside the evidence owner.
- `attest` reads every record once and commits exactly the bytes it checked — each path once. A failing index or ref update exits non-zero and loses nothing.
- A blocking REVIEW line of the work that is neither committed nor carried by the attestation is refused by name instead of counted.
- A record staged with other bytes than the worktree and HEAD hold is refused instead of overwritten; the foreign staging stays.
- While it writes, `attest` holds the index's own `index.lock`, so a parallel `git add` fails instead of being overwritten; today's shard is appended through a descriptor checked for identity and content. A split index is refused.
- The attest commit runs `git commit`'s hooks as before (pre-commit, prepare-commit-msg, commit-msg) on the commit's own index; a hook that refuses stops the commit with the line written and staged. A hook that stages more into that commit is refused instead of committed, and `post-commit` does not run for it.
- A symlink or submodule committed as a record, or as a directory records lie under, is refused instead of read as an empty home.
- `attest --archive` no longer moves the plan: it refuses before reading anything and names the way to archive. Every way of moving a file after the check could lose another process's bytes; the gate recognizes a plan archived by a later `git mv` commit by its content, as it does after `/finish`.
- `plan-structure` compares the cell counts of a table's header and delimiter row (GFM) and reports a mismatch as a finding.

**Update.** No steps for the template's own commands. A script or habit that runs `attest … --archive <plan>` drops the flag: attest first (with `--with <plan>` when records are appended to it), then `git mv <plan> <archive path> && git commit` — the refusal names the path.

**Changed sections.** `verification-independence.md` (Bind the verdict to the reviewed range)

Details: [Plan](docs/analysis/2026-10-24-v2.77.3.md) #308

## v2.78.0 — A finding names its place; blocks on old code are counted · 2026-10-24

**Why.** The Claude Code team found by git blame that 59 % of repeatedly flagged code had been there since round 1 (#311). We wanted the same number for our review rounds and could not get it: in Kenni's 571 review reports only 24 % of the FINDING lines named a `file:line` at all, free in the title, and of 37 blockers in round 2 or later two could be measured.

**What changes.**
- A FINDING line has a place field, `at=<path>:<line>`, `<path>:<first>-<last>`, `<path>` or `-` (no single place). The github-issues report gate requires it on every blocker and major a branch adds, like `class=`; findings that stood at the fork point stay valid, and classifying or placing an old finding does not make it new. The review bundle and the Codex result schema ask for it; a Codex run started before the update is handed off with `at=-`.
- `process_kpis.py rounds` and `baseline` report old-code blocks (#311): the `sev=blocker` findings of code reviews in round 2 or later whose lines stand as they did at a head of round 1, as a share of the measured ones, per round and per work, with what could not be measured named by reason. The comparison is by tree content, so a rebase between rounds changes nothing while round 1's head exists.

**Effect.** From the first review after the update on, the cockpit shows how many late blocks fall on code round 1 already saw — the measure for #310 (stable finding ids, next) and for any change to the review rounds.

**Update.**
1. New blocker and major findings a branch adds carry `at=`; project-owned review prompts (briefs for other reviewers) add it to their FINDING form.
2. Reports on main stay valid.

**Changed sections.** `verification-independence.md` (The review bundle — the portable interface to any reviewer), module `github-issues` (Review and audit visibility), module `telemetry` (The KPI cockpit), command `/review`

Details: [Plan](docs/analysis/2026-10-24-v2.78.md) #311

## v2.77.2 — A pytest parameter with brackets keeps the whole id · 2026-10-23

**Why.** `red_evidence` cut a pytest parameter suffix at the last `[`, so a valid id such as `test_x[a[b]]` was read as `test_x[a` while `attest_evidence` reads `test_x`; a valid red-to-green proof was refused on the pytest and JUnit paths.

**What changes.**
- `attest_evidence` owns the test-name normalization as the public `attest_name`; `red_evidence` calls it on both paths and carries no own `[` rule.
- A parameter value may contain brackets, `]`, commas, Unicode or be empty; the identity is the function attest resolves.
- The written reference form is unchanged.

**Update.** No steps.

Details: [Plan](docs/analysis/2026-10-23-v2.77.2.md) #306

## v2.77.1 — Fixes from the v2.77.0 uptake · 2026-10-23

**Why.** v2.77.0 could report a fix as proven while no single test went from red to green: two JUnit cases with the same file and name but different classes were folded into one, so a red-then-skipped case beside an always-green one looked green. Separately, `process_kpis.py findings` crashed on any FINDING line, the review bundle named the next round for a second lens on a blocked head, and the plan-structure docstring described a looser Transitions heading than the gate enforces.

**What changes.**
- `red_evidence` keeps JUnit cases apart by file, class and name and refuses a written test reference the gate reads as another case of the run, or — with `--sites` — does not read as this test; nested Python classes keep their whole chain. The reference form for other languages is unchanged.
- `process_kpis.py findings` exits zero and counts distinct works; the bundle names the blocked round and the `--round` attest accepts; the docstring states the level-2-or-deeper Transitions rule.
- The lens-round rule now lives in `attest.py`; the bundle and the Codex handoff share it.

**Update.** No steps.

Details: [Plan](docs/analysis/2026-10-23-v2.77.1.md) #303

## v2.77.0 — Plans that decide the state space, review-fix rounds that fix the class · 2026-10-22

**Why.** In Kenni's review history (510 issues, 808 rounds), 39 % of the blocking findings in the longest works were plan gaps and 35 % came from the previous round's fix; review noise was none. Fix-induced defects grew with the size of a fix pass (6–9 findings: 46 % of next rounds blocked again, 10 or more: 86 %), and a red test first did not lower them (41 % against 40 %). Mandatory rule 4's "increment or rebuild" after the second block was prose, attest read a ROOT-CAUSE only in the plan while `red_evidence` writes it to the journal, and a required-records fact git could not tell fell away in silence for every fact but two.

**What changes.**
- Two required records (#293, #297): from the second blocked code round of a work, each follow-up block owes `REPLAN work=<id> round=<r>: increment|rebuild — <why>` in the plan; every blocked round owes a class test — `ROOT-CAUSE … — sites: <sibling sites> — <path>::<test>` with a test that stands at head (`red_evidence.py --sites` writes the form), or `sites: none — <reason>` for a round without a code defect. Only rounds and records the branch adds count, compared with its fork point by content; a reasoned `skipped replan|class-test` is the way out.
- attest refuses every pass a fact it cannot tell would leave undecided, and reads ROOT-CAUSE lines and the new skips in the journal too.
- `plan-structure` checks a plan's `## Transitions` table (also in a Spec Kit plan the branch adds): a `Test` column, at least one row, every cell filled, and once tests are due a `<path>::<test>` or `struck — <reason>` per row.
- The github-issues report gate requires `class=` on every blocker and major finding a branch adds.
- The plan review gains a STATE SPACE step and calibration (an undecided failure class is at least `major`); Execute gains "Fixing a review round" (sibling sites, differential test, passes above about 300 lines or six findings in steps, REPLAN first); a measured old/new differential counts as score 100; the failure catalog gains "Decision after an await on a stale snapshot"; the delta bundle warns on a large fix pass.
- Reports carry `round:`; `process_kpis.py baseline` counts blockers by origin, rounds with and without a plan review, fix findings against the fix-induced blockers of the next round, and skips by kind.

**Effect.** A second block can no longer be patched over without the rebuild question, a fix names the class it closes and the sites it checked, and the baseline shows whether fix-induced blockers and fix rounds go down.

**Update.**
1. Works already in flight: a pass after two or more blocked rounds the branch added owes the REPLAN lines and the class-test causes — or `skipped replan|class-test work=<id>: blocked before v2.77`; a new blocker or major finding of your own without `class=` gets one; a plan in flight with `## Transitions` gets a `Test` column.
2. Reports on main and plans already merged stay valid.

**Changed sections.** `design-template.md` (Sections), `failure-catalog.md` (Facts and state), `improvement-monthly.md` (What you review, What you produce), `journal-state-plans.md` (Review attestations), `mandatory-rules.md`, `refute.md` (Refuting a plan), `review-checklist.md` (Decisions — recorded, not embodied silently), `tower.md` (Dispatch and the model policy), `verification-independence.md` (The review bundle — the portable interface to any reviewer, Bind the verdict to the reviewed range, Enforcement), `workflow.md` (Execute, Review), module `github-issues` (Review and audit visibility), module `telemetry` (The KPI cockpit), commands `/execute`, `/plan`, `/review`

Details: [Plan](docs/analysis/2026-10-21-v2.77.md) #293 #297

## v2.76.1 — A dispatched Codex report is readable; another issue's criterion is not required · 2026-10-21

**Why.** Two template defects reached Kenni. The Codex dispatch wrote the report's title above its header block. The header is the block up to the first blank line, so the github-issues report gate read no `review:` and refused the push: twice on one day (Kenni #2683, #2691), each fixed by hand. `check_review.report_header` read no `work:` from such a report either. And attest counted every `AC-<id>` in a plan as a criterion of the work, including one the plan only cited from another issue ("up to the AC-11 measurement (#2659)"). It then refused a pass for a test that criterion never owed. A third came from Kenni #2338: the Codex handoff attested the issue number, and an issue split into several plans made attest refuse it, with no way to name the plan.

**What changes.**
- The Codex dispatch writes the header block first and the title after it (#286).
- A plan cites another issue's criterion qualified, `#2659/AC-11`: attest does not require it and names it in a note (#287). A bare `AC-<id>` stays the plan's own — prose cannot tell a citation from an own criterion with its origin — and its refusal now names the qualified form as the way out.
- A dispatched Codex review records its work: the issue number, or — when that number names several plans at the reviewed head — the slug of the plan it reviews. The handoff attests with it, and the fallback hint names it (#290).
- `verification-independence.md`: a read-only reviewer through opencode also needs redirects, pipes and chains denied — an allowed `git show*` let a review write `git show … > <file>`.

**Update.** A plan that names another issue's criterion writes it `#<issue>/AC-<id>`; a bare id stays required, and attest says so. A dispatched Codex report written before the update keeps its title on top: move it below the header block if the gate refuses it.

**Changed sections.** `journal-state-plans.md` (Plans), `verification-independence.md` (The review bundle — the portable interface to any reviewer)

Details: #286 #287 #290

## v2.76.0 — Deterministic checks before review, the measure of their effect · 2026-10-21

**Why.** Kenni's review history (315 reports, 1,694 findings, dev-process #277 step 0) showed that of the 423 blocking or major findings only 85 needed a reader's judgment; the rest a rule or a test could have caught. Seven of twenty findings where a check never took effect were rules that only printed a warning, seven more were rules that existed only as prose. A template update could not clear its own review, a train carrying one was refused, and a test run under `MAKEFLAGS=-n` passed the push hook.

**What changes.**
- Required records (#282): one table, `review_evidence.required_records` in `model-policy.json`, says what a work owes — a REFUTE for gate code and from Tier 3, a ROOT-CAUSE line after three fix commits on one file, the owner's `DECISION <date> owner:` behind a `review-waived:` line, wherever the plan lives (active, archive, Spec Kit) and already at `/finish`. attest refuses without the record or a reasoned `skipped <kind> work=<id>: <reason>` (the owner's word cannot be skipped); a project appends rows under `required_records_extra`. The bundle reads its refute warning from the same table.
- New core gate `plan-structure` (#278): in a Tier 2+ plan the branch adds — active or already archived, or raised here from Tier 1 — each `AC-<id>:` criterion has exactly one `shall`, an id used once, and — once a task is ticked and at the merge push — its planned test (`AC-<id>: <path>::<test>` or `struck — <reason>`, the grammar attest accepts); at the merge push no task is left `- [ ]` without `struck:` or `moved: #N`. Project sections, further `shall` words and a story registry come from `plan-structure.local.json`, read at the integration ref.
- The review checklist can be scoped to the diff (#281): `review-sections.local.json` maps sections to path classes; the bundle leaves out sections no touched class reaches and names them, and keeps every section when a path falls into no class.
- FINDING lines carry `class=mechanical|testable|judgment` and `rule=<check>` (#276); `process_kpis.py findings` counts them and names a check that repeats across works. The Codex reviewer writes both.
- `process_kpis.py baseline` (#277): per merged work in one or two date windows, the medians of tokens, review and fix rounds, findings and lead time, the tokens stated per phase, escaped works and the change-failure proxy. `testing.md` gains "Classes, not cases"; the github-issues module ships a verification-change template with "Replaces" and "Measure".
- Dispatch (#270): `start` and `queue add` take `--class`, the class travels through the chain; `report.py` takes the state `failed` (crash, timeout — listed high by the tower) and `--usage input=…,cached=…,output=…[,cost_usd=…]`, shown by `models`; a policy cell's `status_file` is a liveness signal. `deepseek-` is a model family of its own.
- `verification-independence.md` adds a reviewer through opencode (an OpenAI-compatible model such as DeepSeek): the model declared with `reasoning` and `tool_call`, read-only repository access, and a brief with `verified=` and a scope per lens — measured on this release's cross-model review, nine in ten findings held with read access, one in six from the diff alone.
- Fixes: a template update's own review report no longer counts as unseen project delta (#272); the gate judges a template update in a train on its own branch (#271); a test run under `MAKEFLAGS=-n` or a variable from `certificate_env` refuses the push, and a green stage retry writes the merge certificate (#265); an in-flight Spec Kit plan owes presence and own family in the gate and in `finish.py` (#266); `due_measurements.py` names a missing milestone file (#259).

**Effect.** Defects a rule or a test can catch are caught before the review, warnings that nobody had to follow became duties with an explicit way out, and the baseline shows whether fewer fix rounds and tokens per work follow — with escaped works as the guard.

**Update.**
1. Nothing is required for existing plans: `plan-structure` binds only plans a branch adds.
2. Stricter than before:
   - every Tier 3 code-review pass needs a REFUTE line of the work or `skipped refute work=<id>: <reason>`;
   - three fix commits on one file need a ROOT-CAUSE line or a skip;
   - a `review-waived:` plan in flight needs `DECISION <date> owner: …`; `/finish` asks for it before archiving;
   - a new Tier 2+ plan's criteria follow the EARS line form with one `shall` (a project writing in another language adds its word in `shall_words`);
   - a push under `MAKEFLAGS=-n` or a `certificate_env` variable is refused;
   - an in-flight Spec Kit plan blocks `finish.py` without its review.
3. Optional:
   - `plan-structure.local.json` for project sections and a story registry;
   - `review-sections.local.json` to scope the checklist;
   - `class=`/`rule=` on findings;
   - `--usage` and `status_file` for harnesses without transcripts.

**Changed sections.** `journal-state-plans.md` (Plans, Review attestations), `mandatory-rules.md`, `refute.md` (What happens with the findings), `start-here.md` (The standard setup), `testing.md` (Classes, not cases — new), `train.md` (The run), `tower.md` (The worker protocol), `verification-independence.md` (The review bundle — the portable interface to any reviewer), module `telemetry` (The KPI cockpit)

Details: [Plan](docs/analysis/2026-10-21-v2.76.md) #259 #265 #266 #270 #271 #272 #276 #277 #278 #281 #282

## v2.75.0 — Template updates survive a moving main, one fence reading, bookkeeping counted from the runs · 2026-10-19

**Why.** Kenni's v2.74 update needed its ack and its full Tier 3 review again after every train that moved main, although nothing in the update had changed; the train's retry message also named the wrong retry. The three readers of fenced blocks disagreed on what closes a fence, so a quoted `REVIEW … verdict=pass` or `review-waived:` could count as real. Refute and red-evidence lines were still typed by hand, a deleted plan escaped its review, and the v2.74 reviews left smaller residues in attest, finish, the design-contract gate and the review bundle.

**What changes.**
- Template update: the ack and the update's REVIEW carry over to a new main when the old base is an ancestor of the new one and the commits in between touch none of the update's paths; the gate names an expired ack (`ack_expired`), and an update REVIEW counts only when its head saw the update's answers, owned list and project delta.
- The train's retry message says what ran: green under the retry command, a gate flake, or the classic FLAKY.
- Fences: one walk (`check_review.fenced_lines`) for the REVIEW parser, the declaration reader and the clarification gate. They read fences as before. Where CommonMark's closing rule (nothing else on the line, so ` ```python ` inside a ` ```md ` example closes nothing) would read any line of a journal shard, plan or spec document differently, that is a hard finding — a quoted REVIEW or waiver that used to count is now refused. A fence still open at the end of a plan or journal shard that hides `tier:`, `issue:`, `review-waived:`, a REVIEW line, `DECISION NEEDED` or a clarification marker is a hard finding too (a note in the archive).
- A Tier 2+ plan deleted by a push, or moved where no arm reads a plan (`notes.txt`, a subfolder, `archive/<dir>/`), still owes its review; the dispatch chain queues no execute while a branch has no single fork point.
- `refute_line.py` writes the REFUTE line from the refuter's report: the brief now ends with `SCENARIO` and `PATTERN` lines, the tool counts them and takes the next round; the summary is the only free text.
- `red_evidence.py --junit PATH` measures red-before/green-after for any runner that writes JUnit XML (vitest, jest, XCTest); `PATH` is an untracked `.xml` file, and the old tree borrows the installed `node_modules`.
- `process_kpis.py models` shows each model's share of the dispatched sessions' tokens, subagents included.
- `finish.py --tests` without a command runs the configured `merge_suite`; `--tests-passed` is refused while one is set.
- attest: the lowest ranked model class reviews no plan, an unmeasured model report is refused with a hint, and a base without `review_evidence` takes HEAD's stricter tier floors.
- Design contracts: a shallow clone no longer dates old plans by its boundary (a note names `git fetch --unshallow`); status `legacy` registers a pre-registry norm with one note.
- The review bundle carries the `CLAUDE.md`/`AGENTS.md` of the folders a diff touches; `dispatch.py` uses the gate's fork point, and `--plan` finds a plan by the issue it declares.
- `testing.md`: a project whose `merge_scope` skips stages schedules a full run with an alert as the net under its selection.
- The changelog archive before v2.28.2 is now one entry per release, in English and German.

**Effect.** A template update is acknowledged and reviewed once, even when trains merge in between. A quoted example can no longer clear or waive a review, and a broken fence can no longer switch a gate off. Refute and red-evidence records come from the runs, and the token report shows whether mechanical steps really moved to the smaller model.

**Update.**
1. Nothing is required.
2. Stricter than before: a line like ` ```python ` inside a fence no longer closes it; a fence left open that hides `tier:`, `issue:`, `review-waived:` or a REVIEW line is now hard — close the fence. `finish.py --tests-passed` is refused where `merge_suite` is set (use `--tests`). Deleting a Tier 2+ plan without its review is refused on the merge push.
3. Optional: write refute reports in the `SCENARIO`/`PATTERN` form and append with `refute_line.py`; use `--junit` for suites other than pytest; with `merge_scope`, schedule the full run (`testing.md`).

**Changed sections.** `commits.md` (Merging), `journal-state-plans.md` (Review attestations), `refute.md` (The brief, What happens with the findings), `releases.md` (Updating the process template), `review-checklist.md` (Extending this list), `risk-tiers.md` (Template updates), `testing.md` (Test economy — scoped inner loop, full merge boundary), `tower.md` (Dispatch and the model policy), `verification-independence.md` (The review bundle — the portable interface to any reviewer, Enforcement), module `design-contracts` (The registry entry, Hard vs. best-effort (no false-green), Declaring the contract), `/execute`, `/finish`, `/review`

Details: [Plan](docs/analysis/2026-10-15-v2.75.md) #124 #125 #207 #228 #229 #230 #232 #250 #251 #252 #253 #254 #255 #256 #257 #262 #263

## v2.74.2 — `make -k` certifies again · 2026-10-16

**Why.** v2.74.0 refused certificates under MAKEFLAGS flags that change what runs, and it listed `-k` among them. Keep-going hides nothing: make runs the remaining targets after a failure and still exits non-zero. The template's own advice runs the suite as `make -k test-merge`. Kenni's merge suite does exactly that. Two trains failed: the tests that write certificates went red under the inherited `MAKEFLAGS=k`, and the main push was refused.

**What changes.**
- `-k` and `--keep-going` no longer block a certificate.
- `-i`, `-n`, `-t`, `--eval` and abbreviated long options still do.

**Update.** Nothing to do.

**Changed sections.** `testing.md` (Test economy — scoped inner loop, full merge boundary)

Details: #263

## v2.74.1 — The family name /review records clears again from own_family_from_tier · 2026-10-15

**Why.** `/review` records a pass with `--model <family>`, for example `claude`. From `own_family_from_tier` on, v2.74.0 counted only models whose class the ranks know (`claude-opus`), so a pass recorded the documented way cleared nothing in the gate, in `finish.py` and in the train. Kenni found it in the review of its v2.74 update, where it would have refused current Tier 3 passes.

**What changes.**
- A bare family name counts as the project's own family when a ranked class belongs to it (`claude` for `claude-*`). Another family's name (`codex`, `gpt`), a partial prefix (`claude-op`) or a non-name (`opus`) does not.
- The bare name stays classless: a plan review still needs the concrete model id.

**Update.** Nothing to do; only projects that set `own_family_from_tier` notice it.

**Changed sections.** `verification-independence.md` (Enforcement)

Details: #260

## v2.74.0 — Fewer project deviations, Codex handoff fixed, readable CHANGELOG · 2026-10-15

**Why.** After v2.73 Kenni still kept its own kernel text, two gate scripts of its own in the template directory and several overlays, only because the template lacked an option. The new Codex handoff left a failed push behind and asked the catalog in the wrong directory. The CHANGELOG was a commit log without structure.

**What changes.**
- The language of artifacts is a copier answer: `artifact_language: english` (as before) or `conversation` (code, commits, issues and contract docs in English, the operator's prose in the conversation language).
- `review_evidence.own_family_from_tier` lets only passes of the project's own model family clear a plan from that tier on; the gate, `finish.py` and the train ask the same owner.
- The `design_contracts` module has an opt-in duty: with `design-contract-declaration.local.json` every Tier 2+ plan declares its contract or `n/a — <reason>`.
- `due_measurements.py` reports due measurement milestones from `milestones.local.json` until a report carries `milestone: <id>`.
- `/execute` requires every handoff to carry forbidden paths, its ACs and the narrow proving command, and to return red before and green after the change; a larger model needs a named reason.
- Further fixes: a failed attest push is retried, the Codex catalog is asked in the worktree, test titles may hold commas, FINDING lines name their reviewer with `by=`, and MAKEFLAGS that change what runs (`-i`, `--eval`, abbreviations) certify nothing.

**Effect.** A project expresses its specifics through answers and local files instead of its own versions of template files; updates run without kernel conflicts and without gate scripts of its own. The CHANGELOG says per release why something changed and what it leads to, in English and German.

**Update.**
1. A project that writes its prose in the conversation language sets `artifact_language: conversation` in `.copier-answers.yml` before the update; a hand-kept language line in the kernel then goes away.
2. To use the new options: `own_family_from_tier` in `model-policy.local.json`, `milestones.local.json`, `design-contract-declaration.local.json`. Without them nothing changes.
3. Stricter than before: an AC line with a comma in its text that names no second reference is now one reference; MAKEFLAGS with an unknown long option certifies nothing.
4. For Kenni: the steps are in the Migration section of the [plan](docs/analysis/2026-10-15-v2.74.md); the old gate `check_tier3_claude_pass.py` goes only in a follow-up commit after the merge.

**Changed sections.** `kernel.md` (Always-on kernel, only with `conversation`), `start-here.md` (Purpose, Dialogue rules, only with `conversation`), `improvement-weekly.md` (Inputs, Steps), `optimization.md` (The record), `tower.md` (Dispatch and the model policy), `train.md` (The run), `verification-independence.md` (Enforcement), module `github-issues` (Review and audit visibility), module `design-contracts`, `/execute` and its Copilot prompt

Details: [Plan](docs/analysis/2026-10-15-v2.74.md) #231 #237 #239 #240 #241 #242 #243 #244 #245 #246 #247 #248

## v2.73.0 — Codex review attested, overlays for project notes, manual CI · 2026-10-15

**Why.** Kenni ran Codex workers, the per-package handoff rule and the opt-out of hosted CI as its own variants; the template adopts them so Kenni does not drift away. Project notes in template docs had no check for whether a template change breaks them.

**What changes.**
- `--harness codex` for `start`, `queue add` and `policy` starts a Codex worker under a supervisor with a time limit; it requires a logged-in Codex CLI.
- `dispatch.py handoff <branch>` checks evidence, attests and pushes; if Codex is unavailable, a trace remains, with the way out `--harness claude` or `skipped cross-model`.
- `/plan` requires `Execution: delegate | retain-context` with a rationale per larger package; `report.py --execution` and `process_kpis.py execution` show whether delegating costs review rounds.
- `ci.github: manual` renders workflows only via `workflow_dispatch` and without a guard script; it is enforced in the pre-push hook, allowed values are `true`, `false`, `manual`.
- Project notes on template docs and commands live in `docs/process/<doc>.local.md` or `docs/process/commands/<name>.local.md`, anchored with `extends`/`replaces: "<heading>" @<hash>`.
- The `overlays` gate turns red when an anchored section changes, until it is re-stamped with `--stamp`; `template_update.py` lists affected overlays.

**Effect.** Codex becomes a full reviewer and leaves a trace when it fails. Own rules no longer break unnoticed on template changes, but every change to an anchored section costs a review; Kenni no longer needs gate code in `.process-owned`.

**Update.**
1. Anyone who wants `ci.github: manual` sets the answer in `.copier-answers.yml` before the update. Allowed are `true`, `false` and `manual`; the string `"true"` is refused.
2. After the update, move your own notes in template docs and commands into overlays, anchor them and stamp them with `--stamp`. The kernel takes no overlay.
3. For Kenni, before the update: set `ci: {github: manual}` and move `legacy_preflight` out of `scripts/process/_dispatch_codex.py` into a file of its own outside `scripts/process/` — the template replaces that file.
4. For Kenni, afterwards: Codex values into `model-policy.codex.local.json`, own rules into overlays, empty `.process-owned`, adapt or drop the tests of the advisory Codex handoff.

**Changed sections.** `commits.md` (Merging), `start-here.md` (The standard setup, Anchors: what goes where…, Definition of ready), `tower.md` (Dispatch and the model policy), `verification-independence.md` (The review bundle…), `workflow.md` (Plan), modules `arch-onboarding`, `doc-drift-gate`, `feature-registry`, `git-hooks` (Honest ceiling), `sbom` (The gate), all commands and Copilot prompts (new overlay line under the title)

Details: [Plan](docs/analysis/2026-10-15-kenni-backport-2.md)

## v2.72.0 — Merge scope in the certificate, stage timings, struck ACs · 2026-10-15

**Why.** Kenni's changes should live in the template as far as possible. A render with Kenni's answers found 27 differing template files, seven of which Kenni carried as its own gate code in `.process-owned`; that made every template update there a migration.

**What changes.**
- `testing.local.json` knows `merge_scope`, an argv that names the stages of `merge_suite`; a narrower run never certifies a fuller push.
- The train and `finish --tests` delete old stage and timing files before the suite, and the train's memo applies only at the same scope.
- A staged merge suite leaves `stages` and one `<stage>.time` per stage in `<git-dir>/merge-suite/`; `process_kpis.py train-phases` shows median, maximum and skips per stage.
- `AC-<id>: struck — <reason>` or `dropped` removes an own AC from the test requirement; the review report must confirm every strike, otherwise attest refuses.
- Smaller changes: invalid `stale_minutes` and a wrong policy shape are reported, design-contract notes and `.process-work/inbox.md` merge with `merge=union`, CI cancels older runs on branches, never on `main`.
- Docs and commands from Kenni: two test lanes with bounded push waiting, coherent packages in `/plan` (median 53 instead of 183 turns), `/finish --tests` with the `merge_suite` string.

**Effect.** A narrower run can no longer release a fuller push, and the train shows which stage costs time. The first push after the update runs once more, because the configuration now carries `merge_scope`.

**Update.** No steps. Optional for Kenni, in this order:
1. Update to v2.72.0 with the entries in `.process-owned`.
2. Replace `certificate.py`, `testing_config.py`, `test_select.py`, `train.py` and `finish.py` with the new render.
3. Remove the five lines from `.process-owned`.

Details: [Plan](docs/analysis/2026-10-15-kenni-backport.md) #226 #234 #235 #221

## v2.71.0 — Evidence before the pass: cross-model, refute, one test per AC · 2026-10-14

**Why.** In one night Kenni merged six tier-2 branches, each with a pass in review round 1; an audit then found six major defects, four of them tests that cannot turn red. 4 of 4 gate-code branches skipped the refute, and the cross-model run was missing without notice, since both had only warned so far.

**What changes.**
- A code-review pass from tier 2 needs a report (`--with`) with one line `AC-<id>: <path>::<test>` per AC; `unproven` refuses the pass.
- The project declares its test files in `review_evidence` (`python_files`, `python_classes`, `test_files`); the test must really run, not be disabled.
- If the scope touches gate code, a pass from tier 2 needs a REFUTE line in its own plan or `skipped refute work=<id>: <reason>`.
- From `review_evidence.cross_model_from_tier` (default 3), the pass carries `cross-model` or `single-family` with `skipped cross-model`.
- A plan-review pass from tier 2 names, via `--model`, the model ID whose rank is not below the plan session's; plans carry `plan-session model: <id>`.
- Every rule has a committed way out `skipped <kind> work=<id>: <reason>` (`cross-model`, `refute`, `plan-review`, `ac-trace`).

**Effect.** A pass proves what it claims, and missing evidence is countable instead of silent. This costs more mandatory lines; a hand-written REVIEW line still bypasses the check, and whether a test actually checks its AC is for the reviewer to judge.

**Update.**
1. Tier 2+ reviews: write a report with one AC line per AC and attest with `--with`; plan reviews pass `--model`.
2. Plans carry `plan-session model: <id>`; a single-family pass on tier 3 needs `skipped cross-model work=<id>: <reason>`.
3. Spec Kit projects give the plan or `spec.md` AC IDs or put `skipped ac-trace work=<id>: <reason>` in the plan, otherwise every tier 2+ pass is refused.
4. For Kenni: the steps are in the Migration section of the [plan](docs/analysis/2026-10-14-review-evidence.md).

Details: [Plan](docs/analysis/2026-10-14-review-evidence.md) #225

## v2.70.0 — Generated inventories, reader search in the plan, news · 2026-10-13

**Why.** Around 200 blocking review findings from one project, sorted by cause, showed ~47% implementation errors and 10–16% missing knowledge of existing code. The knowledge gaps arose when reading code and from unknown readers, not from a missing overall specification.

**What changes.**
- `inventory.py update` generates inventories (environment variables, jobs, tables, tools) into `docs/inventory/<name>.md` from extractors in `docs/process/inventories.local.json`.
- `inventory.py check` compares byte for byte and is inactive without configuration; the project registers the check in `gates.local.json`.
- `inventory.py for-plan <plan>` lists the inventory lines of the files touched, and `/plan` carries them into the tasks.
- A plan that changes a constant, a default, a timeout, a format or an environment variable documents the search for readers and writers in `## Consumers`.
- FINDING lines optionally carry `kind=` (`knowledge-gap`, `requirement`, `implementation`, `test-gap`, `process`, `environment`), and `process_kpis.py rounds` counts blockers by it.
- Every user-visible change brings a fragment `news/<slug>.md` (`news.py new`); the steward renders `NEWS.md` weekly, with title and labels from `news.local.json`.

**Effect.** Planners and reviewers see inventory and readers before changing anything, and blockers can be analyzed by cause; non-technical readers see what is new. Each project has to write its extractors itself.

**Update.** No steps.

Details: [Plan](docs/analysis/2026-10-13-knowledge-anchors-plan.md) #223

## v2.69.0 — Plan drift measurement, fresh-worktree dry run, two release kinds · 2026-10-13

**Why.** A plan was over 1000 commits old when its execute started, and migrations that delete or replace scripts had no prescribed dry run in a fresh worktree. A test that committed in its own temp repo hit the pushing repo on push.

**What changes.**
- `dispatch.py start --phase execute` measures plan drift; mandate `plan_drift`: `mode` `shadow` (default, log only), `warn` or `block` (overridable with `--stale-plan-ok`).
- A migrating plan, or one that deletes or replaces a gate, hook or lane script, carries a `## Fresh-worktree dry run` with exit codes from a fresh `git worktree`.
- A release is either a plain update or a migration release with its own `Migration` section (`releases.md`).
- `tower.py --wait` wakes on silent workers with no report and no commit since the threshold (`--stale-minutes`, `PROCESS_STALE_MINUTES`, policy `stale_minutes`, otherwise 60), once per silence.
- pre-push removes the repo's git variables (`GIT_DIR`, `GIT_INDEX_FILE`, …) from child processes of gates, test runners and the merge suite.
- `DoD-deviation: …` lines of own plans go into the merge commit; `open AC-3 — …` or `continues #42 — …` keeps the issue open (`Refs #N`).

**Effect.** Stale plans are noticed before work builds on them, silent workers wake the steward, and tests can no longer modify the pushing repo. An issue does not close early when the plan names a deviation from the definition of done.

**Update.** No steps. Plan drift initially only logs; after two to four weeks `nodes` and `flow` show whether the thresholds fit, then the owner decides on `warn` or `block`.

Details: #213 #214 #217 #218 #219 #220

## v2.68.0 — Process as a verification graph: node measurement, gate modes, weekly loop · 2026-10-13

**Why.** The process should deliver more output at the same quality and therefore be able to weaken or remove gates. What was missing was a measurement of what a gate costs and catches, and a safe way to weaken it.

**What changes.**
- The gate runner writes one line per gate run (result, duration, commit, mode) to `process-gate-events.jsonl` in the shared git directory.
- `process_kpis.py nodes` shows cost, blocks and flips per gate, `losses` four loss measures, `outcomes` epics and bugs through to the delivered result.
- `gate_modes.py` sets a gate's mode (`block`, `shadow`, `sampled`, `off`) in the log `docs/process/gate-changes.local.jsonl`; weakening needs an owner line, core gates are exempt.
- The steward calls `gate_modes.py sentinel` daily (rollback when a guardrail breaks); `improvement-weekly.md` and `improvement-monthly.md` describe the loops.
- Token totals count an API message once instead of per line (previously inflated); `flow` ends at deploy, otherwise at merge, and says which.
- Behavior change: `optimize.py` `active()` returns an `Activation` whose truth value is on/off (in v2.67 `if active(...)` was always true), and two running trials switch each other off.

**Effect.** A project sees per gate what it costs and whether it catches anything, can observe a new gate in shadow before it blocks, and roll back automatically when a guardrail breaks. Price: every gate run writes a line, and every weakening costs an owner line.

**Update.** No steps. Optional: label bugs with `cause:*` and `channel:*` and set `outcomes.usable` in the mandate for epics (e.g. `label:acceptance`) so `outcomes` shows coverage.

Details: [Plan](docs/analysis/2026-10-12-closed-loop-plan.md)

## v2.67.0 — Optimization contract with frozen criteria and flow measurement · 2026-10-12

**Why.** The owner wanted a process that improves itself: observe, find the cause, review the improvement independently, deploy it in a bounded way, assess the effect. This lacked a contract that fixes criteria before the trial, and a measurement from the first phase to deploy.

**What changes.**
- `docs/process/optimization.md` describes the control loop; `optimize.py` keeps one record per improvement under `.process-work/optimizations/`.
- Before `piloting` it needs a mandate (`docs/process/optimization.local.json`), budgets and an independent `REVIEWED` line; afterwards criteria, limits, duration and budget are frozen byte for byte.
- A mechanism under trial asks `optimize.py active <flag>` (doubt means off); the owner may adopt, the steward only with `adopt` in the mandate, never the implementer.
- `process_kpis.py flow [--issue N]` follows an issue to deploy or merge: work and wait time, tokens, owner decisions and follow-up defects via the commit trailer `Regression-of: #N`.
- `graph.py build|context|missed` derives edges from plans, test map, git co-change and REVIEW lines and only recommends, never narrowing a gate.
- The steward gets the section "Improvement loop" (daily, not per tick).

**Effect.** A project can run process changes as a bounded trial without anyone loosening the criteria afterwards, and sees where an issue loses time and tokens. Without a mandate and records, nothing changes.

**Update.** No steps.

Details: [Concept and review](docs/analysis/2026-10-12-self-improving-process.md)

## v2.66.0 — One rule for own plans, plan review fail-closed · 2026-10-12

**Why.** Dispatch counted only added plans: a branch that changed the main plan of its issue went straight to execute without a plan review. In addition, `plan_review_due` misjudged or crashed on an unreachable origin or non-UTF-8 git output.

**What changes.**
- Own means a plan added by the branch or a base plan that declares an issue of the branch; dispatch and the train use the same rule.
- If a branch changes the main plan of an issue it was dispatched for, a plan review starts, and its pass releases the chain.
- A package for #72 on `70-pkg-…` does not review the plan of its epic #70.
- The prompt and wait message of a plan review name the due plans with their path and require one pass per plan.
- When in doubt, dispatch chooses the code review: on an unreachable origin, in a remote session, with `--dry-run` and with non-UTF-8 git output.
- In the train, a branch that deletes an active plan no longer counts as "unreadable", and a renamed plan counts only once.

**Effect.** A changed plan no longer bypasses the plan review, and an unclear situation resolves in the safe direction. A branch that changes a main plan needs a `-plan` pass beforehand, and `start --phase review` becomes a plan review for it.

**Update.** No steps.

Details: #207 #204 #201

## v2.65.0 — Environment preflight before every test run · 2026-10-10

**Why.** In Kenni a broken worktree venv showed up three times in one day as red certify and operator tests; in v2.64 only the train had a `--preflight`.

**What changes.**
- `testing.local.json` knows `preflight` (argv without shell) and `preflight_timeout` (default 600 s).
- It runs once before the first test command, in the pre-push frame, on `run --certify` and on manual runs; a certificate hit does not need it.
- If it is red, no test runs, no stamp and no certificate is produced, and the run ends with exit 2.
- The train uses it as the default for `--preflight` with the same time limit; a hanging preflight is killed along with its process group, `--preflight ""` runs without.
- On push, the process gates run before the preflight.

**Effect.** A broken host shows up as an environment error instead of a red test and uses up no test runs.

**Update.** No steps.

Details: #209

## v2.64.0 — One test path: selection, lanes and certificates from data · 2026-10-10

**Why.** `testing.md` described four rules for test selection and lanes that every project had to build itself. Kenni built `lane.py`, pre-push and selectors on its own, and `certify` ran the full suite there for a one-file change.

**What changes.**
- `docs/process/testing.local.json` describes per stack the runner, test globs, map, `select`, `merge_suite`, lanes and `certificate_env`; if it is missing only gates run, if it is broken the push is refused.
- `test_select.py plan|run|check` is the single selection rule for hook, `certify` and manual runs; `check` reports stale pins and map targets.
- `lane.py` holds the lanes `scoped` and `full` jointly for all stacks of a push; if the lane stays busy, no test runs.
- Certificates `push` and `merge` apply to an unchanged tree; a merge push without a certificate runs `merge_suite`, otherwise `full` per stack.
- `pre_push.py` is the single sequence of every push; `PROCESS_SKIP=gates|tests` is the logged owner escape hatch, and `gates.local.json` knows `exec` and `paths`.
- The train gains `--preflight CMD` and writes the merge certificate after a green suite; `finish.py --tests CMD` with `merge_suite` does the same. **Contract change:** `--tests-passed` writes none.

**Effect.** A project supplies data instead of its own scripts, a one-file change selects only its tests, and a green merge suite is not run again in the push.

**Update.** For Kenni:
1. Write `testing.local.json` with the stacks, set `unmapped: "skip"` and `merge_suite` to the merge target; reduce `.githooks/pre-push` to `exec uv run scripts/process/pre_push.py "$@"`.
2. Replace `finish --tests-passed` with `finish --tests <merge_suite>`, otherwise the suite runs in the push.

**Changed sections.** `testing.md` ("One test path"), `train.md`, `failure-catalog.md`, BOOTSTRAP

Details: #206

## v2.63.0 — Plan review is detected, Codex block counts only from score 80 · 2026-10-10

**Why.** In Kenni (#2480, #2483) a plan was changed after its plan pass, the review session started without `--plan-review` and aborted with "no code". Also, a project rule prevented the plan pass as soon as Codex blocked, although the independent score was 75 and only a residual remained.

**What changes.**
- `dispatch.py start --phase review` starts a plan review itself when the branch changes only plans and bookkeeping and an own tier 2+ plan has no pass for its current text.
- The state the session reviews is authoritative; if git cannot answer the question, it stays a code review.
- `--plan-review` still forces the plan review and is needed when a plan already on main is changed on the branch (#204).
- A block from a second model family counts only from score 80, as with plan reviews (`verification-independence.md`).
- A `review.local.md` may tighten the round count, not the threshold.

**Effect.** A changed plan is reviewed as a plan instead of aborting as a code review, and a residual below the threshold no longer prevents the plan pass.

**Update.** For Kenni: adjust the own rule that tightens the score threshold.

Details: #203

## v2.62.1 — A valid round with the same number supersedes the old line · 2026-10-10

**Why.** `attest.py` counts round = 1 + blocking rounds, so the round after a pass keeps its number; v2.62.0 nevertheless required a higher one for the superseding full round. In Kenni #2396 an old malformed delta line therefore stayed in place and every push remained refused.

**What changes.** A full round supersedes the old line even with the same number, provided it is a pass and its head descends from the old one.

**Update.** No steps.

Details: #199

## v2.62.0 — Four gate gaps from Kenni operations closed · 2026-10-10

**Why.** The Kenni steward reported four gaps on v2.61: stuck branches after merging main (#2240, #2396), a branch with an active plan rejected by the train, a Spec Kit plan made stale by `attest --with`, and `finish.py --tests` with `shell=True`. The last one triggered the consumers' security scanners.

**What changes.**
- A superseded REVIEW line no longer blocks when a valid full round of the same work follows with a higher round and a descending head; it becomes a note.
- The train counts a branch's active plan as its work when the branch adds it or it carries an issue of the branch.
- A Spec Kit plan no longer goes stale through appended records (REFUTE, ROOT-CAUSE, REVIEW, dated DECISION), an answered `DECISION NEEDED` or archiving.
- `finish.py --tests` runs without a shell: leading assignments (`FOO=1 make test`) count as environment, and shell operators are rejected before the first step.

**Effect.** Branches no longer get stuck after the merge, the own attestation no longer invalidates a review, and the scanners no longer fire. Multiple test stages therefore belong in a make target or script.

**Update.**
1. `finish.py --tests` with multiple stages or shell operators: move them into a make target or script.
2. For Kenni: Kenni maintains the scanner for merge commits in its own `.githooks/pre-commit` itself; the template ships none.

Details: #199

## v2.61.0 — Tier is recomputed, changed values are searched · 2026-10-09

**Why.** In Kenni #2454 a tier 2 plan rewrote the redirect path on which the only SSRF guard depended, without the tier being recomputed; in #2456 plan and review saw only the package list for an image tag, not Makefile, tests and docs, and the train ran red. Also, `template_update.py --help` started a `copier update` in the current checkout, presumably the cause of Kenni #2463.

**What changes.**
- From tier 2 the plan names the touched boundary and its independent guard (`file:line`); if the changed code is the only enforcement, it is tier 3.
- `review-checklist.md`, `/plan` and the plan brief in `refute.md` ask this question; if the tier does not hold, the review stops and the work is re-tiered.
- `/plan` inventories changed versions, paths and constants like a rename and cites the search; the code review searches for the old value itself once more.
- `template_update.py` reads arguments with argparse: `--help` changes nothing, unknown arguments and a directory without `.copier-answers.yml` are rejected before copier runs.

**Effect.** A change to the only enforcement of a guard is reviewed as tier 3, a value that appears in several places is found before the train, and `--help` is harmless again.

**Update.** No steps.

Details: #197

## v2.60.0 — Mechanical tasks run on Haiku · 2026-10-09

**Why.** Since v2.58.0 `/plan` cuts tasks so that a small model can execute them without a decision of its own; the `mechanical` class nevertheless ran on Sonnet.

**What changes.** In `model-policy.json`, `classes.mechanical.execute` now points to `claude-haiku-5`; `[design]` tasks stay on Opus, review and refute still follow the tier.

**Effect.** `[mechanical]` tasks run on the smaller model with the update.

**Update.** To stay on Sonnet, set in `model-policy.local.json`: `{"classes": {"mechanical": {"execute": "claude-sonnet-5"}}}`.

## v2.59.1 — The train does not retest an already green tree · 2026-10-09

**Why.** In Kenni train 20261009-0935 the bisection saw main+#2445 green; after #2456 was dropped, the rebuild, i.e. the same tree, ran through the suite for another 25 min. A docs-only branch thus held the lane for almost two hours.

**What changes.** `judge` skips the suite for trees that were already green in the same train; the gates still run.

**Update.** No steps.

## v2.59.0 — The train retries a red run cheaply · 2026-10-09

**Why.** The train used to always rebuild a red combined tree and run the whole suite again, even for a deterministic red. In Kenni this cost a second 24-minute run before the drop on a 25-minute `test-merge`.

**What changes.**
- Red gates run once more on the same worktree, and on green the suite follows; the log states decision and reason.
- On a red suite, `--retry` runs the project command on the same worktree; without `--retry` it rebuilds as before.
- `--retry` repeats what failed and what did not run, so stages behind the first red one are not merged untested.
- If the first run left something git sees, it rebuilds; the suite's own output therefore belongs in the gitignore.

**Effect.** A deterministic red now costs only the retry run of the failures, and the flake protection remains.

**Update.** For Kenni:
1. Run the suite as `make -k test-merge` so every stage runs once.
2. Pass `--retry "make test-merge-retry"` via `TRAIN_ARGS` or the `train` target; each stage runs only its failed tests.

Details: #193

## v2.58.0 — A plan is independently reviewed before code is written · 2026-10-09

**Why.** Between plan and execute nobody read the plan independently; the first independent look came with the code review. In Kenni #2454 a tier 2 plan covered all eight ACs and still had two gaps that would only have surfaced after a full execute round.

**What changes.**
- `review-checklist.md` begins every section with "Plan decides:"; the plan decides there for the touched dimensions, and the code review checks the code against it.
- Tier 2: A fresh subagent reviews the plan with the plan brief in `refute.md`, and the planner attests with `attest.py --plan-review --commit`.
- Tier 3: A dedicated plan-review session with a second model family reviews the plan.
- `dispatch.py chain` queues execute only once every own tier 2+ plan carries a passing plan review for its current text.
- `/plan` cuts tasks as `[mechanical]` where possible (exact files, contract, test, command); what needs judgment becomes `[design]`.
- Checks that read `.process-work/` are gates rather than tests behind the tree stamp.

**Effect.** Gaps in the plan surface before the code, and more tasks run on the smallest model. Limit: `chain` acts only on local sessions; after a plan review on another host the steward queues execute itself.

**Update.** For Kenni: Running tier 2+ plans need a plan pass before execute; work whose execute is already running is not affected. The mechanical cell in Kenni's `model-policy.json` can point to a smaller model.

**Changed sections.** `/plan`, `/review`, `workflow.md` (Plan), DoR R3, `tower.md`, `refute.md`, Copilot prompts

Details: #192

## v2.57.1 — Shared files no longer hold up reviewed branches · 2026-10-08

**Why.** A candidate did not board the train if it shared a file with a branch already on board. In Kenni, a whole train run waited on three reviewed branches just because of a shared test, contract document or registry file.

**What changes.** Git merges the batch in boarding order and the full suite runs on the combined tree; only on a real conflict is the later candidate kicked off with `blocked` and rebases.

**Effect.** Branches that change different parts of the same file now ride together. Known limit: if B is removed as the culprit after colliding with C, C still misses the train; candidates that certainly collide still count toward `--min-candidates`.

**Update.** No steps.

## v2.57.0 — Train and sessions no longer wait for pre-pushes · 2026-10-08

**Why.** On 08.10., serial pre-pushes in Kenni held the `scoped` lane all morning. An execute start was rejected for hours, and only one train ran while five candidates with a passed review waited.

**What changes.**
- The train (`departure`) no longer waits for a busy `scoped` lane; it runs the suite with `nice` on `full`, alongside the short runs.
- A session start, including execute, is no longer rejected when the `full` or `scoped` lane is busy; only the session's test runs wait at the lane.
- The gates already run before `planned` in the plan prompt and in `/plan`; `chain` starts no execute while the plan worktree is red and names the reason.
- A session starts at the origin state: lagging worktrees are fast-forwarded, diverging ones rejected; a review rejects a worktree ahead of origin.
- After a red batch, the suite on bare main is skipped if the train already saw that tree green (`green-suites`), except before blaming a passenger.

**Effect.** The train runs alongside the pre-pushes, execute starts no longer wait, and plan errors surface before execute. In Kenni, the push failed thirty times per branch on a missing `design-contract:` line.

**Update.** No steps. For Kenni: remove the local steps in `run_issue.sh` (`gate_runner`, pulling up to origin); the train runs without `--force`.

Details: Kenni #2441, #2446

## v2.56.1 — Review bundle no longer breaks the issues gate · 2026-10-08

**Why.** The issues gate read every `.md` in `.process-work/reviews/` as a report, including the gitignored review bundle (`*.bundle.md`), and the push failed because it lacks the `review:` header. In Kenni this happened twice in one day.

**What changes.** Files ignored by git no longer count as reports, and `testing.md` describes what test selection and the lane script should look like.

**Update.** No steps. For Kenni: selection (`Makefile`) and `scripts/lane.py` remain Kenni's code, with test subpackages and one lane hold per push; record the hold time before and after in #184.

Details: #186, #184

## v2.56.0 — Debug method, brainstorming in rounds, verified review blocks · 2026-10-08

**Why.** An unbiased comparison with Matt Pocock's `skills` v1.3.1 and Claude Code's `code-review` plugin showed methods the process lacked. Only those were adopted; no new gates, no new artifacts.

**What changes.**
- Debugging follows a fixed order (`workflow.md`): red loop, reproduce, falsifiable hypotheses, regression test at the seam, commit naming the confirmed hypothesis.
- Brainstorm asks questions bundled in rounds, each with a recommendation; with Spec Kit, `/speckit-clarify` records the answers.
- A blocking finding names its failure scenario; a defect whose path does not run through the change is pre-existing and becomes an issue instead of a block.
- A fresh process scores every block (0/25/50/75/100); below 80 it becomes a residual finding, and anything linters, type checkers or tests catch never blocks.
- Each review lens reports in at most about 400 words, most severe first, and ends with "Merge danger".
- `review-checklist.md` gains "Silent failures", `testing.md` names tautological and internals-bound tests, and `THIRD-PARTY-NOTICES.md` lists the adopted sources.

**Effect.** Debug sessions and reviews follow a fixed method; a block is evidenced rather than assumed, and weak findings no longer hold up the merge.

**Update.** No steps. For Kenni: the review session has a fresh subagent score every block before attesting it (a cheap model suffices); Kenni's own refute panel can become narrower (steward brief, point 2).

## v2.55.0 — Review gate checks content instead of history · 2026-10-08

**Why.** The gate inferred from commit history whether a review still applies, and left reviewed work looking unreviewed after an integration; in Kenni, three works changing the registry sat on one branch. Also, a conflict resolution passed on its own side even when it discarded `main`'s change.

**What changes.**
- A file at the pushed tip counts as reviewed if its content matches git's merge of the integration branch and the reviewed heads; colliding paths never count as reviewed.
- A conflict-free rebase or merge of `main` keeps a review with a fork-point base valid (#158), and reviewed works that merge cleanly count as reviewed together.
- Stricter: every conflict resolution needs a new round, and a commit that resets a reviewed file to `main`'s state is unreviewed.
- Any git error means "stale" (fail closed); the weaker `--cc` fallback after a failed `merge-tree` is gone.
- `/review` now says: rebase or merge `main` before round 1; a later conflict-free integration keeps the review.

**Effect.** Only real conflicts now cost a new review round. A verdict takes a median of 0.05 s instead of 25 s, and about 400 lines of gate code plus 28 tests are gone.

**Update.** Requires git 2.38 or newer (`merge-tree --write-tree`). For Kenni: branches with a conflict resolution need a new round; a conflict-free rebase no longer does.

Details: [Plan](docs/analysis/2026-10-07-review-gate-teardown.md) #158, Kenni #2439

## v2.54.2 — Review gate without timeout on large history · 2026-10-08

**Why.** In Kenni, the review gate ran 936 s and was aborted by the gate runner after 600 s; the train stood for hours with four finished candidates.

**What changes.** The stale check asks git each fact only once per run, and an aborted gate names the running and the longest finished phase.

**Effect.** In Kenni, the run on a pushed range of 900 commits dropped from 172 s to 92 s, the stale check from 39 s to 7.5 s. A timeout now reads as a performance problem with a named phase instead of a verdict.

**Update.** No steps. For Kenni: drop the local patch from #2436 to `check_review.py` and `gate_runner.py` with the update (own gate-code changes would otherwise be a tier-3 migration).

Details: #182, Kenni #2436

## v2.54.1 — Commands and prompts state the inventory and REVIEW rule · 2026-10-07

**Why.** The rule "one owner per acceptance criterion" was only in the module docs and the review checklist, so review found violations a round later. The Copilot review prompt and `AGENTS.md` had the `REVIEW` line written by hand, without `base` and `head` from the bundle.

**What changes.** `/execute` and the Copilot execute prompt state the owner rule, and the Copilot review prompt and `AGENTS.md` write the `REVIEW` line with `attest.py`.

**Update.** No steps.

## v2.54.0 — Two fewer gates, one owner per acceptance criterion · 2026-10-07

**Why.** In Kenni, one month had 12 `GRADE` lines against 126 `REVIEW` lines, and what they were meant to measure is already read from the review records by `rounds` and `models`. The `ac-text-drift` gate compared a criterion's text in spec and inventory because both carried it.

**What changes.**
- The GRADE gate is removed along with `process_kpis.py convergence` and the rework count in `cost`; `workflow.md`, the tasks template and `speckit.md` no longer require `GRADE` lines.
- The `telemetry` module stays as a cockpit, old lines stay as history, and a manifest with `telemetry: true` stays valid.
- An acceptance criterion's text has one place: spec or issue until merge, the inventory afterwards; everywhere else only the ID appears.
- The delivering change writes the inventory entry from the final `AC-n` lines as the last step before the review bundle.
- `ac-text-drift` is removed; the review checks whether entry and spec match (new question in `review-checklist.md`).

**Effect.** Two fewer gates, and no text lives in two places that can drift apart.

**Update.** No steps. For Kenni: `test_process_kpis_process.py` and `test_human_digest_process.py` expect `check_telemetry.py` and the `convergence` output and must be adjusted; Kenni's own `ac-text-drift` script in `gates.local.json` is untouched.

## v2.53.0 — Leaner review gate: digest and anchor chain removed · 2026-10-07

**Why.** `diff=<sha256>` was `sha256(git diff base head)`, a function of the two SHAs already in the line, and required recomputation, an integrity ledger, a cache and a fetch stamp. The delta anchor chain at tier 3 also gave the gate more code than checking value.

**What changes.**
- The diff digest, integrity ledger and `PROCESS_REVIEW_INTEGRITY`/`--full` are removed; `attest.py` writes only `base` and `head` and checks the fork point.
- Delta bundles (`--since`) are a reading aid on every tier, and the verdict always binds the whole branch; `mode=delta` and the tier-3 anchor chain are removed.
- An empty delta is named as such, a `--since` pointing at no commit and an older delta bundle are refused.
- A standing block is read at the tip; a block entry that the range deletes no longer stands.
- Legacy data stays valid: lines with `diff=` and `mode=` are read and the fields ignored, and any line with `base`/`head` counts as a full round.

**Effect.** `check_review.py` shrinks from 3,080 to 2,683 lines; with bundle, `attest` and tests, about 1,450 lines are gone. With an empty delta, the reviewer no longer sees no code while still vouching for the branch.

**Update.**
1. A branch that is mid review rounds at update time needs a review from the fork point; merged lines stay valid.

Details: [Plan](docs/analysis/2026-10-07-review-gate-teardown.md)

## v2.52.0 — Less process mechanics: only real errors block · 2026-10-07

**Why.** Measured in Kenni, completed works with review fell from 70 (26.08.–08.09.) to 18 (23.09.–07.10.), and the share of blocking reviews rose from 5% to 33%. On 07.10. the process blocked itself at least six times, for instance when `attest` refused two `pass` entries because the line said `round=6` instead of `round=5` (Kenni #2396).

**What changes.**
- Template updates with release-identical gate code are no longer a tier-3 migration (own changes stay tier 3); `releases.md` recommends updating every two to four weeks.
- `attest.py` no longer refuses bookkeeping: a too-high `--round` and wrongly numbered `ROOT-CAUSE` lines are only hints, and `--with <report>` commits report and plan lines together with the REVIEW line.
- Only an error someone will hit may block; wording issues are `nit`, and minor or nit findings yield a `pass` with residual points.
- From the second block on the same element, the fix session decides between increment and rebuild; after the third, the owner decides once and for good.
- Answered or struck-through `DECISION NEEDED` lines no longer stop the train, and plan, review and brainstorm sessions also start with a busy `scoped` lane (#177).
- A push with only process records runs the process gates without a suite; the tower shows `balance` and reports `process-heavy` above 40% process share.

**Effect.** Fewer self-blocks from bookkeeping and wording, and a template update no longer costs tier-3 rounds (v2.51.1 needed three). Cross-model review at tier 3, refute before the first round and the train with the full suite remain.

**Update.** No steps. For Kenni: `review.local.md` §11 currently sends every round after the second to the owner and should instead adopt the single owner decision per cap.

Details: #177, Kenni #2396, #2397, #2416

## v2.51.1 — Strict override guard and worktree fixes · 2026-10-07

**Why.** The guard against `model:`/`effort:` overrides in phase files had to read frontmatter the way Claude Code itself does (#173/#174), and several bugs appeared in Kenni in worktrees, with `say`, in slot counting and with spec plans.

**What changes.** `dispatch` reads phase frontmatter strictly without PyYAML and refuses ambiguous overrides; fixes for worktrees, `say`, slot counting and spec plans come with it.

**Update.** No steps. For Kenni: drop the local deviation from #2393 with the update.

Details: #170, #173, #174, #175, Kenni #2399, #2405, #2411, #2412, #2414

## v2.51.0 — Effort per policy cell, tier-3 review on Opus xhigh · 2026-10-05

**Why.** A cell in `model-policy.json` was just a model name, with no effort and no start command of its own. Also, in Kenni a `model:` override in a command file's frontmatter silently put plans on another model for weeks (#2317, #2299).

**What changes.**
- A cell in `model-policy.json` is a model name or `{"model": …, "effort": …, "command": …}`; `model-policy.local.json` replaces it entirely.
- Effort levels are `minimal`, `low`, `medium`, `high`, `xhigh`, `max`.
- The start command knows `{effort}` and can be set per cell (cell > `phases.<phase>.command` > `command`), for example to run only the tier-3 review on Codex.
- The tier-3 review runs on `{"model": "claude-opus-5", "effort": "xhigh"}` instead of `claude-fable-5-1`, so the attestation is `single-family`.
- `dispatch start` refuses if the command file sets `model:` or `effort:` in its frontmatter (`inherit` excepted); a template test keeps all files free of them.
- Workers get `PROCESS_EFFORT`, reports show the effort, and with `transcripts` in the policy the tower reports model drift.

**Effect.** Model, effort and start command are selectable per task class, tier or phase, a silent model override is no longer possible, and model drift becomes visible.

**Update.**
1. Projects with their own `command` in the local policy add `--effort={effort}` or set the tier-3 review cell locally; otherwise `dispatch start` refuses.
2. Clean up command files that set `model:` or `effort:` in the frontmatter.

Details: Kenni #2317, #2299, #2244, #2247

## v2.50.1 — Safe template source, spec tidy without data loss · 2026-10-05

**Why.** `template_update` passed an unchecked source on to Copier (executable with `GIT_ALLOW_PROTOCOL=ext`), and the spec tidy could delete spec folders that code still references (Kenni #2382). The process's rejections also did not say what to do.

**What changes.** `template_update` checks the source against the allowlist, the spec tidy no longer deletes spec folders that are still referenced, and rejections name the way out.

**Update.** No steps.

Details: #166, #167, #168, #169, Kenni #2382

## v2.50.0 — Gate checks the base of a full review round · 2026-10-05

**Why.** Since v2.49.1, `attest.py` and the bundle write a full round only against the fork point, but the gate did not check the base of existing entries (#160). It also checked the template in the working tree instead of the committed state (#161).

**What changes.**
- A `mode=full` REVIEW entry counts only if its base is the fork point of head and integration branch; a wrong entry is a malformed line.
- A locally fast-forwarded or forged `main`/`master` does not bypass the check; without an integration ref there is a single message (hard on the integration push).
- The gate always checks the template at the committed state; `template_verify --ack` works on the working tree, and an ack counts only after it is committed.
- On macOS, git commands of the template check name the shared bare clone via `--git-dir`, so `safe.bareRepository=explicit` no longer blocks them.
- The bundle gives an advisory warning "transition table missing": a plan uses state vocabulary without a `## Transitions` section; add own words via `transitions-vocabulary: …` in `review.local.md`.
- A second hint, "regression pin missing", appears when a delta bundle changes code but no test file.

**Effect.** A forged base no longer counts as a full round; against Kenni's journal (1079 entries), no new hard error arises on main. The effect of the two hints is not yet measured.

**Update.** No steps. Merged legacy entries are not checked; entries outside the pushed range are named in a single summary note.

Details: #160, #161, #163

## v2.49.1 — One merge base or none, template source hardened · 2026-10-05

**Why.** With several merge bases, one was silently chosen (Kenni #2381), and a template source like `--upload-pack=…` reached a git call. Kenni had made local fixes for this in #2352, which are now ported to the current code.

**What changes.** No merge base or several merge bases is now an error, and the template check rejects invalid paths and disallowed sources.

**Update.** No steps. For Kenni: replace the local delta from #2352 with the update (#2383).

Details: #160, #161, Kenni #2352, #2381, #2383

## v2.49.0 — Waiting without polling, tidying reports, model per class · 2026-10-05

**Why.** Kenni holds 58 MB in 983 report files under `.process-work/reviews/`, which the gate reads on every run. `/steward` waited for new reports through a harness-owned monitor, and mechanical subtasks could not be put on a cheaper model selectively (#157).

**What changes.**
- `tower.py --wait` blocks without model turns until a report with one of the `--states` arrives and prints it as JSON; `/steward` uses it.
- `--json --section NAME` prints only the named parts of the situation picture.
- `tidy.py` removes only reports of completed work (last verdict `pass`) that are older than `--days`, not the newest, and not named by any plan or journal.
- `tidy.py` deletes only via `git rm` reports that are tracked and identical to HEAD; without `--apply` it only lists them with sizes.
- After its ID, a task carries a class token (`[mechanical]`, `[design]`, or your own from `classes`) that applies before tier and phase; `dispatch.py policy --class C` names the model.
- Every subagent call names its model, the harness default is not a choice (`tower.md`); review and refute still follow the tier.

**Effect.** Waiting costs no model turns, report folders do not grow without bound, and mechanical subtasks run on the cheaper model. The effect of classes is not yet measurable per class; the per-issue token sum from v2.48 shows only the overall effect.

**Update.** No steps.

Details: #157

## v2.48.0 — Tier-3 follow-up rounds as delta, usage visible · 2026-10-05

**Why.** A tier-3 package downstream needed 5 rounds with 3 review lenses each on full bundles of 10,400–13,100 lines, because tier 3 had no delta (#155). The template check also cloned anew on every run (Kenni #2375).

**What changes.**
- A tier-3 follow-up round may use a delta bundle if it builds on a full round for exactly this state or a gapless delta chain; otherwise it never counts as a pass.
- A full bundle is enforced if the delta changes gate code, contract paths, decisions or the tier, or touches a file the anchor report does not name.
- A review lens reruns in the follow-up round only if it has open findings or names a touched file.
- `/execute` also checks host capabilities, credentials and integration fixtures named in the plan before the push; whatever cannot be checked is `DECISION NEEDED`.
- Every report carries a model; `/finish` names the issue's output tokens (policy key `transcripts`) and writes the `done` report itself, and `process_kpis.py cost --issue N` shows them too.
- The template check uses one filtered clone per process instead of two `ls-remote` calls plus a full clone; offline it still fails hard.

**Effect.** Tier-3 follow-up rounds review the fix instead of over 10,000 lines, per-issue usage is visible, and the template check clones less often. The effect is not yet measured; compare via `process_kpis.py rounds` and the new token numbers on the next tier-3 work.

**Update.** No steps.

Details: #155, Kenni #2375

## v2.47.0 — Fewer review rounds: failure catalog and upfront questions · 2026-10-05

**Why.** Kenni had 386 review entries in three weeks, 38% of them blocks, and tier-3 features needed 3–7 rounds. A second project had 10 blockers: 6 from the first draft, 2 introduced by a fix and 2 found late.

**What changes.**
- `docs/process/failure-catalog.md` is the single place for failure classes: the six previous ones from `refute.md` plus eleven new ones, each with input shape, test and helper.
- The design template's threat question applies at tier 3 and at high-risk tier 2 (gate code, data loss, authorization, migration, concurrency).
- New is the "Transitions" section for state machines, with tests per row class and negative tests (`/execute`); when a fact's computation changes, `/plan` inventories every reader.
- Round 1 names all blockers; a follow-up round checks the fix, open findings and the fixed failure class everywhere, and requires a full bundle if contract or risk scope changes.
- At tier 2, the review answers the refuter's questions itself, with a separate refute run only for data loss or concurrency; from tier 3 and for gate code it remains.
- `process_kpis.py rounds` shows tier, rounds and blockers by origin per work; FINDING lines have the optional field `origin=draft|fix|late`.

**Effect.** Failure classes are asked about in the plan instead of found in the third round, and tier 2 saves its own refute run. The effect is not yet measured; compare via `rounds` on the next comparable deliveries.

**Update.** No steps.

## v2.46.0 — Session context limited to current work · 2026-10-05

**Why.** At startup `process_context.py` read in all plans and specs, including unrelated ones; in the reference project (43 active plans, 91 spec folders) that was most of the context, and the same applied to `rehydrate.py` after compaction.

**What changes.**
- `process_context.py` shows only the current work in full (via `--issue N`, branch name or issue in the branch) and all other plans and specs as an index; without a match it shows only the index with a hint to `--issue N`.
- `--all` gives the previous output; `--cost` still measures everything and separates `mandatory` from `available`.
- After compaction `rehydrate.py` likewise shows only the current work in full, with the rest as at most 10 index lines.
- `publish_and_prune --stage` refuses forms like `GH-12` instead of guessing the issue.
- `tools/release.py` runs the full suite in parallel when pytest-xdist is installed (measured 465 s); otherwise it runs serially.
- doc-drift no longer reports a reference to a missing optional `*.local.*` file as drift.

**Effect.** In the reference project `process_context` drops from 428,644 to about 19,000 characters (−96 %) and `rehydrate` from 84,359 to 6,973 (−92 %). Nothing is silently dropped; the rest stays in the index.

**Update.** No steps.

Details: #140

## v2.45.0 — Tag and release only after green CI, fewer duplicate checks · 2026-10-03

**Why.** Tag and release ran without any suite and could bypass CI. The process also checked some things twice: Linux ran as `portable-smoke` next to the `test` job, and `fix-streak` was recomputed on every gate run.

**What changes.**
- `portable-smoke` now runs only on macOS and Windows; the `test` job covers Linux.
- Before tag and release, `tools/ci_evidence.py` requires a successful `push` run of `ci.yml` on `main` for exactly the target commit.
- `release-tag.yml` (also on `replace`) and `release-publish.yml` check this and now run only from `main`.
- A non-hexadecimal `sha` aborts instead of silently tagging HEAD.
- `fix-streak` is no longer a gate; the review bundle carries the hint once per round as a "Fix streak" section, and rules 4 and 6 remain.
- `tools/release.py` keeps its local run, `--no-suite` stays opt-in, and the remote steps name waiting for CI on `main`.

**Effect.** Tag and release can no longer bypass CI. Dropping the Linux smoke saves about 16 s of runner time plus setup per CI run; only the `::error::` annotation for Linux failures is lost.

**Update.**
1. If `portable-smoke (ubuntu-latest)` is a required check, remove it from branch protection.

## v2.44.1 — One owner for task sizing and `[P]` · 2026-10-03

**Why.** The docs contradicted each other: `/execute`, `workflow.md`, the tasks template and the Speckit module docs required "one atomic commit per task", while `/plan` and `commits.md` allowed two commits.

**What changes.** Everywhere the rule is now: a task is done when its behavior is green (one or two commits), and `/plan` is the sole owner of `[P]`.

**Effect.** The commit contradiction and the scattered `[P]` rules are gone; there is no new gate and no new phase.

**Update.** No steps.

## v2.44.0 — Avoid errors earlier, without new mandatory steps · 2026-10-03

**Why.** Existing process steps contradicted each other: `/execute` forbade what "Check existing code first" required, the tasks template conflicted with `/plan`, `testing.md` contradicted itself, and the Speckit docs conflicted with a gate that hard-failed on any companion file.

**What changes.**
- Spec Kit has one task per behavior (test, red, implementation, green); template, gate message, docs and constitution say the same.
- Existing plans with separate test and implementation tasks still pass the gate, and a story without a test reference still fails.
- The inventory for rename, remove and move belongs in the plan's tasks; `/execute` only compares the diff against the plan before the push.
- Before creating or changing a rule, parser or helper, `/execute` reads the existing owner with its callers and tests.
- The clarification gate blocks only on open markers in `plan.md` and `tasks.md` and on read errors; markers in companion files such as `research.md` are only hints with file and line.
- E2E by risk instead of count: "One per feature — floor AND ceiling" is removed, and changed critical contracts need a matching proof.

**Effect.** Errors surface in the plan instead of shortly before the push, and companion files no longer block; no mandatory sections, gates or review rounds are added. The savings are expected, not measured.

**Update.** No steps.

## v2.43.2 — Safe automatic template check, verified cleanup · 2026-10-02

**Why.** During automatic provenance rendering, Jinja extensions marked as trusted locally could run before review, and worktree cleanup could remove ignored work created only after the first approval.

**What changes.** Automatic rendering skips tasks and runs without trust, and before a worktree is removed the keep policy is re-checked with fresh records.

**Effect.** Locally trusted extensions no longer run before review, and ignored work created later is preserved. External writes during the check and the git deletion remain non-atomic.

**Update.** No steps.

## v2.43.1 — Docs on verified template updates refreshed · 2026-10-02

**Why.** Overviews and review hints no longer matched the current template.

**What changes.** The English and German overviews (including the German PDF) and the review and tier hints now describe owner confirmation, update provenance, review of the project delta and enforcement migrations.

**Effect.** Docs only, no change to runtime behavior.

**Update.** No steps.

## v2.43.0 — Verified template updates, faster CI · 2026-10-02

**Why.** A template update would otherwise have had to go through review again, including approved template files, although only the project delta is new. CI tests also took 322 seconds.

**What changes.**
- Both pinned template releases are re-rendered against the trusted source and compared with the project files; lost local customizations remain project delta.
- A pure, owner-confirmed template update passes without re-reviewing the template files.
- The project delta needs a fresh, digest-bound Tier 2 review; gate scripts, helpers and configuration remain Tier 3.
- Own and local files, hooks, Makefiles and changed or deleted tests stay in the project review; forged provenance grants no exception.
- CI tests run with two workers, grouped by test file.
- Audit leftovers: `prime` reads inbox content in all three harness adapters, the language checks cover every module, and the gate workflow names its required check.

**Effect.** The review effort of an update is limited to the project delta; CI time drops from a measured 322 to 183 seconds.

**Update.**
1. Enter baseline and target as release tags or full git SHAs; unpinned values are refused.
2. Follow the update order from `docs/process/releases.md` and attach the computed delta and behavior notes.
3. Commit the owner confirmation.

## v2.42.0 — Downstream fixes in the integration path, worker channels · 2026-10-02

**Why.** After earlier releases, residual defects remained in integration and review in the reference project (#142). On Windows, the output encoding of gate subprocesses could also differ from the runner's.

**What changes.**
- Integration and review are hardened: integration ranges fail closed, review coverage is pooled, and non-fast-forward pushes are protected.
- New: an owner-approved transition from brainstorm to plan, diagnosis of conflicting or dead workers, and additive project-local tower findings.
- `finish` works safely across worktrees and archive batches, and the model policy determines phase selection.
- The train's push timeout is configurable (default 30 minutes), so long pre-push gates are possible (#83).
- Worker channel events and the steward restart feedback are documented (#139).
- Gate subprocesses emit UTF-8.

**Effect.** Integration aborts on an unreadable state instead of guessing, and long gates no longer fail on the push timeout.

**Update.**
1. Update bundle producer, attestation writer and review gate together; new delta attestations carry `mode=delta`, existing full-review records stay valid.
2. Fetch the remote default branch before a protected push; non-fast-forward integration pushes need a named owner exception.

Details: #142, #83, #139

## v2.41.0 — Merged worktrees are removed, never work · 2026-10-01

**Why.** In the reference project, 111 dispatch worktrees stayed behind after merge, each with its own venv and `node_modules`, about 57 GB in total. The disk filled up and all sessions stalled.

**What changes.**
- The train removes the worktrees of branches it merged after a successful push and names every worktree it keeps, with the reason.
- `tidy.py` lists merged worktrees with their size, and `tidy.py --apply` removes them.
- A worktree is kept if it might carry work, for example through uncommitted, untracked or non-regenerable ignored files, or a running session.
- `dispatch.py start` refuses at 90 % disk usage and names the cleanup command (`PROCESS_DISK_LIMIT_PCT`).

**Effect.** Leftovers no longer fill the disk, and no unsaved work is lost.

**Update.** No steps.

Details: #136

## v2.40.1 — Hints name the project's hook installer · 2026-10-01

**Why.** The reference project manages its hooks in `.githooks/` without the git-hooks module, yet the hook doctor and docs sent it to `scripts/process/install_hooks.py`; `tower.md` also still advised putting `model-policy.json` in `.process-owned`, which has been obsolete since v2.39.0.

**What changes.** The repair hint names the project's own installer (`scripts/install_hooks.sh`, a `make hooks` target, otherwise `git config core.hooksPath .githooks`), and `tower.md` points to `model-policy.local.json`.

**Update.** No steps.

Details: #134

## v2.40.0 — Last project deviations reviewed and adopted into the template · 2026-10-01

**Why.** After porting to v2.39.0 the reference project had no owned files left, but four non-owned files still carried local changes that a future update would have overwritten.

**What changes.**
- doc-drift now checks the path in `` `path/file.py::symbol` `` pointers, so stale pointers show up.
- The owner digest lists every `<gate>-waived:` line, including the waiver of a project-own gate (`gates.local.json`).
- `check_architecture` and `check_issues` declare PyYAML (PEP 723).
- The reference project's `doc-drift-base` marker was not adopted because it is unused there and was already removed once in review as a bypass.

**Effect.** The reference project no longer has to carry local changes to these files. Both scripts also run standalone without PyYAML installed.

**Update.** No steps. If you have symbol pointers in checked documents, you may find dead ones after the update.

## v2.39.0 — Local extension points and a guard before main · 2026-09-30

**Why.** In the reference project 14 files sat in `.process-owned`, each one a manual port on every release. An inventory sorted every deviation.

**What changes.**
- `docs/process/gates.local.json` holds own gates (`{name: {module, command}}`); a module gate may be replaced by one of the same name, a core gate may not.
- `docs/process/model-policy.local.json` is layered over `model-policy.json` mapping by mapping.
- `docs/process/review.local.md` carries own review dimensions that only sharpen the review, never weaken it.
- A push to `main` needs the route of the train or `finish.py` (`PROCESS_MERGE_ROUTE`) or a named, logged owner exception.
- A `block` in the pushed range holds up the merge push until a later `pass` for the same work exists (standing block).
- `attest.py --archive` moves the own plan to the archive together with the `pass`, and `--commit` turns that into a commit of only those paths.

**Effect.** The template adopts the upstream candidates and offers three local files for the rest; afterwards `.process-owned` can be empty. A push to `main` now only works via a named route.

**Update.** No steps.

## v2.38.0 — Earlier rebuild question, measured evidence, release as a script · 2026-09-30

**Why.** A retrospective in the reference project showed: a guard needed four review rounds although all findings from round 2 on shared one cause. Red evidence and ROOT-CAUSE lines were written by hand, with errors, and the release consisted of a dozen manual steps.

**What changes.**
- The fix-streak check flags the second `fix` commit on the same file and requires a DECISION "increment or rebuild" before the next patch.
- After the findings, the refuter writes a PATTERN line with the common cause and the one owner that closes all findings, or "no common cause".
- `red_evidence.py` runs a pytest selection against the old state and the working tree; only a test that failed in the run counts as "red before".
- `red_evidence.py` writes the journal block and, with `--cause`, the ROOT-CAUSE line, and refuses if no test was red before or anything is red afterwards.
- `tools/release.py` does the local part of a template release in one run; `--check` reports every place not on the version.
- Known, not implemented: the REFUTE line is not yet generated from the refute report (#124).

**Effect.** The rebuild question comes after the second hit instead of the fourth, evidence is measured instead of typed, and a release is one script call.

**Update.** No steps.

Details: #124

## v2.37.0 — Path names read with `-z`, "unreadable" is not "empty" · 2026-09-29

**Why.** Without `-z`, git quotes names containing umlauts, newlines or tabs, and the quoted name matches no file. In the reference project the train read an archived Tier 2 plan this way as Tier 0, and the branch entered without review.

**What changes.**
- All process tools (train, tower, review bundle, `dispatch`, `template_update` and others) read path names with `-z`.
- `template_update` now sets own files and searches conflict markers name-safely; before, an update overwrote own files with an umlaut in the name.
- If git cannot deliver a list, it no longer counts as empty.
- The review gate then counts every active plan, `finish` blocks, and the train does not let the branch enter.
- tower reports a branch with an unreadable file list as `paths-unknown`, and `dispatch` then answers "cannot say".
- Known, not fixed: some places still read a git error as "no plans" or size 0, but none decides a merge.

**Effect.** No branch enters without review because a plan under a special-character name was unreadable. An update no longer overwrites own files with an umlaut in the name.

**Update.** No steps.

## v2.36.0 — Workers ask the steward, tower sees unanswered questions · 2026-09-29

**Why.** In the reference project a worker's question to the owner sat unanswered in chat for six hours. Also, git quotes plan names with umlauts, so `finish` reported a Tier 2 plan as done without review and the review gate let the merge push of a Tier 3 plan through without evidence.

**What changes.**
- The steward is the decision partner; the worker asks the owner only about product principles or destructive steps.
- A question goes into the plan as `DECISION NEEDED` with `blocked`, never into chat; the policy names the live channel (`decision_channel`).
- Before `pushed`, `/execute` has four new duties, including a `ROOT-CAUSE` line checked with `attest.py --dry-run` after a blocked round.
- tower reports a live worker that has printed nothing for 30 minutes as `waiting-for-input` (question routed) or `question-unrouted`.
- tower reads paths NUL-separated and prints names that are not UTF-8 masked.
- Known, not fixed: other tools still read paths without `-z` (follow-up in v2.37.0), and a worker on another host shows no screen here.

**Effect.** Questions land where someone reads them, and tower shows an unanswered one immediately. Plans with umlauts in the name no longer bypass review.

**Update.** No steps.

## v2.35.0 — The train knows the issue of a package branch · 2026-09-29

**Why.** A branch named after a larger issue (`<epic>-<package>-…`) but reviewed under its package's issue never entered the train, because its name carries only the epic's number.

**What changes.**
- One place answers "which issue does the branch belong to", and the train asks it on entry, for the branch's plans and for the merge's `Closes #N`.
- An issue reported in the worker report itself does not count.
- After the merge, the train removes the entries and dead records of the branch's issues; a reused branch name inherits no old issues.
- Code that reads the issue map and records creates no directory, queries no worker and skips broken entries.
- Known, not fixed: a branch merged outside the train keeps its entries until its issue is reassigned.
- Known, not fixed: a second, still running attempt on another branch loses its assignment once the issue is merged.

**Effect.** Package branches enter the train and their merge closes the right issue; before, such a branch entered but closed nothing.

**Update.** No steps.

## v2.34.0 — One refuter from Tier 2: owner check first, then edge cases · 2026-09-28

**Why.** Refute was mandatory only for gate code but has proven itself beyond that: in the stale check every round found real errors, about half of them from the previous fix round. The costliest blockers in the reference project came from a second owner of a rule.

**What changes.**
- Refute is graded by tier: Tier 0 none, Tier 1 optional, Tier 2 one run before the first review round (fix round: regression tests), Tier 3 and gate code again after every fix round.
- The refuter checks in fixed order: owner check, error read as success, edge cases and a sample of the evidence; pre-existing findings become issues.
- A second owner blocks on every tier unless a `DECISION` in the plan gives the reason.
- The review bundle warns when a plan at Tier 2 or higher carries no REFUTE line of its own.
- Only one owner now reads a plan's tier and waiver, the same for bundle and gate.

**Effect.** Errors surface before rather than in the fix round, and duplicate owners are looked for first; the price is one extra refute run at Tier 2. Known, not fixed: the delta refusal still counts design documents and plans with a review waiver, and `dispatch` still reads the tier with its own logic.

**Update.** No steps.

## v2.33.1 — Discard detection in the stale check, also within other reviews' range · 2026-09-27

**Why.** A review in the reference project showed that another review's `base..head` range excused more than the content this review had seen, so a merge there could discard reviewed code unnoticed.

**What changes.** The stale check again tests merges within another review's range for discards; if base or head is missing, everything since the branch point counts.

**Effect.** Discarded reviewed code is caught even within another review's range; five edge cases remain open and are documented.

**Update.** No steps.

## v2.33.0 — Evidence, train verdict and dispatch hardened · 2026-09-27

**Why.** Five process gaps came from reference-project findings: evidence lines were read inconsistently, the train's suite verdict and stale check had gaps, a train merge did not close out the work, and `dispatch` was weakly guarded.

**What changes.**
- One place defines where REVIEW, ROOT-CAUSE and REFUTE lines live; examples, comments and placeholders do not count.
- A red make call stays red, and "not present" applies only to the suite's own file or target.
- If the suite is missing only in the combined tree, that is blamed on the passenger who removed it.
- A train merge archives its own finished plans and closes this repository's issues via `Closes #N`; `plan-stays-active:` keeps a plan open.
- In the stale check, code counts as reviewed if another code review saw it within its `base..head` range; plan reviews cover no code.
- `dispatch`: `say` checks delivery, `chain` advances phases from reports, the queue is locked and deduplicated, and workers run under `nice` (`worker_nice`).

**Effect.** attest, bundle and gate evaluate evidence consistently, and a train merge leaves no finished plans or open issues behind. Every finding is backed by a test that fails against the previous version, or documented as a known limit.

**Update.** No steps.

## v2.32.5 — Stale check judges by a pinned table · 2026-09-26

**Why.** After the third patch to the stale check, trains were rejected daily in the reference project; the check now gathers facts from git and judges by a pinned table.

**What changes.** For clean merges, the stale check counts only what goes beyond git's own merge, and stays fail-closed on missing data or hidden changes.

**Effect.** Clean merges no longer reject the train, and malicious resolutions and discarded reviews do not slip through.

**Update.** No steps.

## v2.32.4 — REFUTE line as evidence, more precise suite detection · 2026-09-25

**Why.** A review of the refute port in the reference project blocked, and a fresh agent then found three majors with about 165 scenarios.

**What changes.** A REFUTE line needs `round=<n>:`, content and its plan's work id, and the train's "suite not present" detection is narrower.

**Effect.** Only genuine REFUTE evidence counts, and a stacked plan's line covers no other plan.

**Update.** No steps.

## v2.32.3 — The train takes only branches reviewed at their head · 2026-09-25

**Why.** A branch a train had already merged showed up as ready to board the next train after new commits, because the old `done` report and the old REVIEW pass still applied.

**What changes.** A branch boards the train only if its REVIEW pass covers the branch head and no unreviewed code follows it.

**Effect.** New commits after a train merge do not reach the next train without a new review.

**Update.** No steps.

## v2.32.2 — Refute of the residual-finding fixes from v2.31.6/7 · 2026-09-25

**Why.** A fresh agent tested the fixes from v2.31.6/7 with 27 scenarios; 8 failed.

**What changes.** The train's stale check and suite detection are corrected for renames, clean merges, missing prerequisites and further make variants.

**Effect.** False alarms on clean merges disappear, and the train report stays complete.

**Update.** No steps.

## v2.32.1 — The REFUTE warning withstands its own refute · 2026-09-25

**Why.** The rule from v2.32.0 was applied to its own implementation right away: a fresh agent found three majors and three minors in the REFUTE warning.

**What changes.** The REFUTE warning now also detects files moved away, more gate paths (incl. `Makefile`, `.github/workflows/`) and non-ASCII names, and ignores example lines.

**Effect.** The warning can be bypassed neither by renames nor by example lines.

**Update.** No steps.

## v2.32.0 — Refute before the first review for gate code · 2026-09-25

**Why.** Gate changes needed four or more review rounds in the reference project; a refute pass found more in two runs than three review rounds before.

**What changes.**
- If a diff changes `scripts/process/`, `.githooks/` or the gate configuration, a fresh agent attacks it before the review sees it.
- `docs/process/refute.md` (new) describes timing, role, a copyable brief and how to handle findings.
- The result is recorded as a line `REFUTE work=<id> round=<r>: …` in the plan.
- The review bundle warns on gate code without a REFUTE line, but does not block.
- `review.md` and `verification-independence.md` point to the new rule.

**Effect.** Gate code is attacked before review; every finding becomes a regression test or a DECISION. For now the warning is only a hint.

**Update.** No steps.

## v2.31.7 — "Suite not present" under `make train` too · 2026-09-25

**Why.** v2.31.6 detected "suite not present" only under `make:`; under `make train` the suite's make reports as `make[1]:`, and the case would have been red again.

**What changes.** The make level directly below the train's now counts; deeper levels stay red.

**Update.** No steps.

## v2.31.6 — Four residual findings in the train, tidy and the stale check · 2026-09-25

**Why.** The review of v2.31.5 left four residual findings open.

**What changes.** The train detects "suite not present" more narrowly and retries flakes after a drop, `tidy` survives unreadable files, and the stale check detects discarded conflict resolutions.

**Effect.** A failing test no longer looks like a missing suite, and a discarded review does not slip through.

**Update.** No steps.

## v2.31.5 — `stale_review` checks the rule instead of the symptom · 2026-09-25

**Why.** Round 3 of the review in the reference project showed: after `commit --amend` or a rebase, the reviewed state is no longer in the history, and the check let that through.

**What changes.** The stale check verifies the rule instead of the symptom: a reviewed state outside the history is invalid, everything unreviewed counts, and git errors lead to rejection.

**Effect.** A merged-in side branch, an amend next to the reviewed state and a merge with `-s ours` are now caught. The findings of an independent refute agent are in place as regression tests.

**Update.** No steps.

## v2.31.4 — Journal lines from two branches merge without conflict · 2026-09-25

**Why.** In the reference project, two reviewed branches blocked each other in the train over REVIEW lines appended to the same daily file.

**What changes.** `.process-work/journal/.gitattributes` sets `*.md merge=union`, so the merge keeps both lines; a project's own root `.gitattributes` is untouched.

**Update.** No steps.

## v2.31.3 — One reviewer set across all review rounds · 2026-09-25

**Why.** A new reviewer in a later round found old findings, and each of them became its own round.

**What changes.** `review.md` requires a fixed reviewer set per piece of work and lets follow-up rounds check only the fix and its surroundings; older findings become their own issues.

**Update.** No steps.

## v2.31.2 — Conflict resolutions in merge commits count as unreviewed · 2026-09-25

**Why.** Round 2 of the review in the reference project: the fix from v2.31.0 (`--no-merges`) missed a conflict hunk resolved by hand in a merge commit after the review.

**What changes.** The stale check reads merges via their combined diff (`--cc`): a conflict resolution counts as the work's code, a clean merge does not.

**Update.** No steps.

## v2.31.1 — Round counter counts rounds instead of block lines · 2026-09-25

**Why.** The first review of the round counter showed: several reviewer lenses of one round were counted multiple times.

**What changes.** `attest` counts unique blocked rounds instead of block lines, and `--exception` writes the `REVIEW-EXCEPTION` line even when no rule applies.

**Effect.** Several lenses of one round no longer count as several rounds, and exceptions always remain countable.

**Update.** No steps.

## v2.31.0 — Train distinguishes flake, missing suite and foreign passengers · 2026-09-25

**Why.** Findings from the reference project (trains 31 and 34): a bisection over a flake blames an uninvolved party, a passenger bringing a new make target turned the tree red, and the merge push rejected every train with several passengers.

**What changes.**
- If the combined tree is red, it runs a second time; if it is then green, the train reports FLAKY and merges.
- If the suite is missing on a tree, that tree is not comparable instead of red: main does not count as red, no prefix is blamed.
- Every red verdict logs the system load, and a rejected push says whether origin or the local pre-push hook rejected it.
- The review gate counts only non-merge commits descending from the reviewed state as "code after the review".
- `tidy` lists spec directories the pruner would reject, with the missing part as an owner decision; `--apply` no longer hands them over.

**Effect.** A flake no longer blocks the train, fellow passengers no longer cause rejection, and `tidy --apply` hands over nothing the pruner rejects.

**Update.** No steps.

## v2.30.0 — Fewer review rounds: count, cause first, then fix · 2026-09-24

**Why.** The analysis in the reference project showed that work with three or more rounds rose from 11 % to 23 %, mainly through fixes that created the next blocker themselves and an inflated round counter. Work of 3,000–5,500 lines added to this.

**What changes.**
- `attest` counts the round itself (1 plus recorded blocks) and rejects a deviating claim; plan reviews count separately (`--plan-review`).
- Before every round after a block, `attest` requires one line `ROOT-CAUSE work=<id> round=<r>: …` per block in the journal or plan.
- `--exception` lifts both rules and writes a countable `REVIEW-EXCEPTION` line.
- The review bundle warns from 30 files or 1,500 lines (`PROCESS_REVIEW_MAX_FILES`/`_LINES`).
- Per `review.md`, a fresh session takes over the fix when the same spot blocks twice.

**Effect.** A fix round starts only with a documented cause, the counter shows real rounds, and oversized work stands out early.

**Update.** No steps.

## v2.29.0 — Only a branch's own work releases it · 2026-09-24

**Why.** In the reference project, a template-update branch boarded the train while its own review was still running, because it only archived other people's long-approved plans.

**What changes.**
- In the train, an archived plan releases a branch only if it is the branch's own.
- A branch that changes `scripts/process/` or `.githooks/` boards, regardless of tier, only with a REVIEW pass for its own work.
- The review bundle marks invalid evidence as VOID: identical before/after pairs, identical images and known empty states under `docs/process/void-evidence/`.
- `model-policy.json` knows `env` globally and per phase (e.g. `CLAUDE_CODE_SUBAGENT_MODEL`), valid only for worker sessions.
- The tmux runner no longer removes policy variables together with the steward's `CLAUDE_CODE_*` variables.
- `tower.md` names the attest commit on the work branch as the way to deliver a verdict from the cloud.

**Effect.** Tidying up other people's plans no longer releases a branch, empty evidence does not count, and policy variables reach the workers.

**Update.** No steps.

## v2.28.2 — The merge suite is each stack's full suite · 2026-09-24

**Why.** In the reference project, the train ran only the backend suite; a CSS change broke a frontend pin, and nothing before the merge ran it.

**What changes.** `--suite` is now the full suite of every stack (`train.md`, `testing.md`), and `train.py run` without `--suite` warns on stderr that only the process gates run.

**Update.** No steps.
