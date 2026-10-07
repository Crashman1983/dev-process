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
| `rounds` | per work item: tier, rounds to the first pass and blocked rounds (journal `REVIEW` lines); blockers per `FINDING`, by `origin=draft\|fix\|late` where the reports carry it — read through `check_issues.py` when the `github-issues` module is installed, else "not read"; a reader that is installed but cannot import (PyYAML missing — `uv run` resolves the script's header) is named as such | proxy; within one tier over time: `fix` blockers dominate → regression tests and a re-check of the fixed class (`verification-independence.md`, "What each round judges"); `late` dominates → a more complete round 1 |
| `share` | week by week on the integration branch: commits touching only process records, mixed and product only, and the landed changes that carried product code (`tower.py` owns the classification and shows the current week as `balance`) | proxy — paths, not effort; process-only above 40% for two weeks while product changes fall → look where the rounds go (`rounds`) and batch bookkeeping one commit per round (`testing.md`) |

A KPI without a trigger does not exist — the cockpit only helps if something
runs it. With GitHub CI the `process-kpis` workflow runs `report` monthly
(and on dispatch) into the run's step summary; read it.

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
