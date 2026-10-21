# Module: telemetry

Opt-in. A read-only KPI cockpit over the traces the workflow already
produces — review records, git history, dispatch reports — where every
number carries confidence and an action. No new pipeline, no gate: the
cockpit never blocks.

The module used to add a graded-acceptance trace (`GRADE` lines) with a gate
of its own. Few projects wrote the lines, and the review records already
carry what they measured (rounds to pass, blockers and their origin), so
both are retired. Old `GRADE` lines stay in the journals as history;
nothing reads them.

## The KPI cockpit

`scripts/process/process_kpis.py` (read-only, never a gate, not in CI) cuts
the existing traces into decision families. Measured numbers print with a
confidence tag — `high` (direct measure, enough n), `medium` (sample-biased),
`low` (proxy or thin n; proxies never reach `high`) — and a confidence-gated
action: at `low` the only action is to collect more data. n before percent.

The error rate at the gate is read from the review records (`rounds`,
`models`), the error rate after merge from git (`cfr`, `clusters`); `cost`
and `share` say what the work and the process cost. `models` and `rounds` file a work item under the highest tier any of its review rounds declared.

| family | measures | action (threshold → act) |
|---|---|---|
| `cost` | `--transcripts DIR` token medians per session (harness-specific, `~approx`); `--issue N` one issue's output tokens from the policy's `transcripts` glob (`finish.py` prints the same line), else `not measured` | a work item far above the median → look at its rounds (`rounds`) before its model |
| `cfr` | DORA change failure rate: `feat:` with a corrective `fix:` ≤7 d sharing a code file (proxy) | trend over ≥3 windows only; rising despite catch>0 → tighten the test/review gate |
| `clusters` | rule 6 across sessions: `fix:` commits (14 d) sharing a subject token — each session sees its fix as a first attempt; git sees the series | a cluster ≥3 → stop path-patching, write the invariant record (Type: invariant) with its table test (`workflow.md`, Debug) |
| `rounds` | per work item: tier, rounds to the first pass and blocked rounds (journal `REVIEW` lines); blockers per `FINDING`, by `origin=draft\|fix\|late` where the reports carry it, and by `kind=` (plan reviews — header `phase: plan` — apart from code reviews; `kind=` is the finding's sort, not the `cause:*` label of `outcomes`) — read through `check_issues.py` when the `github-issues` module is installed, else "not read"; a reader that is installed but cannot import (PyYAML missing — `uv run` resolves the script's header) is named as such | proxy; within one tier over time: `fix` blockers dominate → regression tests and a re-check of the fixed class (`verification-independence.md`, "What each round judges"); `late` dominates → a more complete round 1 |
| `findings` | review findings by what could have caught them — `class=mechanical\|testable\|judgment` (unclassed counted apart), all and blocker/major; mechanical and testable ones by the check that would catch them (`rule=`, else `kind=`), listed where one repeats in `--min-works` works (default 2); the judgment share of classified blocker/major findings; `--json` (#276) | proxy; a repeating check is the next gate or class-level test to write (`testing.md`); the judgment share is the review effort only a reader can carry |
| `flow` | per issue: first dispatched phase (dispatch logs) to deploy (the train's `phases.jsonl`: `branches`, `deployed`, `ended`) or merge (`done` report) — lead time with working time (a phase's start to its end report) and waiting time apart, tokens with input and cache shares (policy `transcripts`), owner `DECISION` lines in the issue's plans, escapes (`Regression-of: #N` within `--follow-up-days`, default 30), the process version at merge (`.copier-answers.yml`); every field `measured`, `estimated` or `missing`, recovery time named as not measured; `--json` for an improvement record | the larger of work and wait is the lever — wait: hand-offs, questions, the train; work: rounds and context; the baseline for `docs/process/optimization.md` |
| `losses` | four loss measures over the `flow` items of a window (`--days`, default 28), **never summed**: occupancy (agent hours, from working time), delay (issue hours waited), owner effort (`DECISION` lines, a proxy) and tokens; each with how many issues carry a value and how many are missing — a missing value is never a zero; regression fixes as a diagnostic proxy | compare each measure with its own past, never with the others: delay → hand-offs and the train; occupancy → rounds and context; tokens → model and context per phase |
| `outcomes` | value (`--days`, default 90), read with `gh` from the 100 most recently updated issues: epics (native sub-issues, the mandate's title prefix or label) to the mandate's *usable* marker — `epic-closed` (a proxy) or an acceptance sub-issue by `label:`/`title:` — measured where the flow shows its deploy; operator-reported disruptive bugs to their delivered fix (a closure as duplicate or `not planned` is no delivery); bug origin on two label axes (`cause:*`, `channel:*`) with coverage against the mandate's target ("blind spot") and the regression share, `estimated` until a triaged sample checks the labels; without `gh`: `unavailable`, never zeros | a blind spot → label where bugs are filed (`github-issues.md`); a worse time to usable with no process loss to explain it → a product signal, not a process change |
| `nodes` | each gate as a node of the check graph (`--days`, default 30), from the gate runner's event log (`process-gate-events.jsonl` in the common git dir): runs and distinct commits, cost (total, median, P90), raw blocks, sole blocks (no other gate failed on the commit — `estimated`, two failures may be two defects), flips (pass and fail on one commit) and triaged blocks from `.process-work/gate-triage.jsonl` (`confirmed-defect`, `accepted-risk`, `infra-or-flake`, `unknown`) | a gate that costs much and never blocks alone is a candidate to weaken — after triage, never on raw blocks; `unknown` is no evidence; a gate that flips is a flake to fix first. Read it where the gates run (a fresh CI checkout has no log) |
| `share` | week by week on the integration branch: commits touching only process records, mixed and product only, and the landed changes that carried product code (`tower.py` owns the classification and shows the current week as `balance`) | proxy — paths, not effort; process-only above 40% for two weeks while product changes fall → look where the rounds go (`rounds`) and batch bookkeeping one commit per round (`testing.md`) |

`report` runs every family except `outcomes` (which needs the network).

**Gate triage** (`.process-work/gate-triage.jsonl`, one JSON object per line,
tracked): `{"gate": "<name>", "commit": "<sha>", "category":
"confirmed-defect|accepted-risk|infra-or-flake|unknown", "class": "<failure
class>", "fix": "<commit or issue>", "note": "…"}`. Whoever reviews a block
records it; the weekly improvement session samples untriaged blocks. A short sha (7+ characters) matches by prefix; a row counts only for a block inside the `--days` window. A
follow-up fix commit proves nothing on its own — it may mend something else.

A KPI without a trigger does not exist — the cockpit only helps if something
runs it. With GitHub CI the `process-kpis` workflow runs `report` monthly
(and on dispatch) into the run's step summary; read it.

## The graph (observation mode)

`scripts/process/graph.py` derives the process's relations from what
already exists — plans (issue → plan → named file), the test map
(`testing.local.json`, file → test, no project selector runs), git history
(files that change together, with support and confidence), journal REVIEW
lines (work → reviewed head) and, optionally, the project's own commands in
`docs/process/graph.local.json` (one JSON edge per line). Every edge carries
its `source`, the commit it was read `at` and its `certainty` (`declared`,
`derived`, `inferred`). No database, no new instrumentation, no gate.

- `graph.py context PATH…` — what else a change to PATH probably touches:
  the context a hand-over should carry, the tests worth running.
- `graph.py missed [--branch B]` — co-change partners and plan-named files
  the branch left alone: candidates for an overlooked relation, to be
  written into an improvement record when they recur.
- `graph.py build [--json]` — every edge but the test map's (those come
  with `context`, for the paths asked), for whoever wants to look.

**A missing edge proves no independence.** git sees what changed together,
a plan what its author named, the test map what it maps. The graph
therefore recommends and makes overlooked dependencies visible; it never
narrows a test selection, a review or a gate. Whether it earns more than
observation is decided by an improvement record, not by this doc.

## What the numbers can say — and what they cannot (honest ceiling)

Every cockpit number is shaped by project-individual choices: how fine the
acceptance criteria are cut, what tier mix the work happens to have, how old
the codebase is, how strictly the grader words verdicts. These confounders do
not cancel out across projects. The consequences are binding:

- **Within-project only.** A number compares a project against its *own*
  baseline over time. Cross-project comparison ("project A needs 1.4 rounds to
  pass, project B 2.1, so A's process is better") is meaningless — the number
  difference is dominated by criterion granularity and domain, not process
  quality. The cockpit deliberately has no export/benchmark format.
- **Trends and ratios, not absolutes.** An absolute value carries no
  information until the project has its own baseline (typically the first
  weeks of traces). Act on direction — rounds to pass rising, fix clusters
  growing, process share climbing — and on within-project ratios, never on the raw
  number against a universal threshold. The thresholds in the cockpit are
  provisional starting points to be recalibrated per project, not standards.
- **Events are the robust class.** Counting discrete events survives
  granularity differences that break rates: a **catch** (a grading source or
  gate stopped a real defect before merge) and an **escape** (a defect reached
  the main branch and needed a corrective fix) are countable facts. When in
  doubt which number to trust, trust the raw event counts over any percentage
  derived from them.
- **Goodhart and self-grading.** Grader and graded are often the same model
  family; a metric that becomes a target stops measuring. The numbers steer
  *attention* — where the rounds go, which behaviour keeps collecting fixes — they
  never grade people, projects, or model choices, and no cockpit value is a
  target to optimize toward.


## One owner per behavior

This module owns no grammar. It reads another module's artifacts only
through that module's own reader (`rounds` asks `check_issues.py` for FINDING
lines, the review records come from `check_review.py`). It measures the
process; it does not define acceptance criteria (`feature-registry`), issues
(`github-issues`), or review depth (`risk-tiers.md`). Thresholds are
documented constants in the rendered scripts — this module owns them, adjust
them there with a journal note.
