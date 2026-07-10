# Module: telemetry

Opt-in. Makes process efficiency measurable: a graded-acceptance trace
(`GRADE` lines in the journal), a gate that keeps that trace machine-readable,
and a read-only KPI cockpit where every number carries confidence and an
action. No new pipeline — measurement rides on artifacts the workflow already
produces. The cockpit never blocks; the gate only fails CI when a written
grade would otherwise be silently unreadable.

## The GRADE line

Whenever a phase grades acceptance criteria — execute checkpoints, the review
gate, quick's lightweight check — it appends **one line per criterion per
round** to the day's journal (`.process-work/journal/YYYY-MM-DD.md`, or the
per-branch shard `.process-work/journal/<branch-slug>/YYYY-MM-DD.md` when efforts
run in parallel — see `journal-state-plans.md`; the gate and cockpit read journals
recursively, so either layout works):

```
GRADE work=42 checkpoint=final criterion=AC-2 round=1 verdict=partial action=fixed source=execute
```

| field | meaning |
|---|---|
| `work` | attribution key: the issue number when one exists, else the plan slug |
| `checkpoint` | which grading pass: a checkpoint number, or `final` for the full-run grade |
| `criterion` | the acceptance-criterion ID exactly as written in the plan/issue |
| `round` | 1 for the first grade of this criterion, 2 after a fix attempt, … |
| `verdict` | `satisfied` \| `partial` \| `not_satisfied` \| `out_of_scope` |
| `action` | what was done about the verdict this round: `satisfied` (nothing to do), `fixed`, `disputed` (verdict rejected with a reason), `surfaced` (unresolved after the round cap, durably flagged) |
| `source` | the phase that graded: `plan` \| `execute` \| `review` \| `quick` \| `debug` |

Fields are space-separated `key=value` tokens in exactly this order; values
contain no spaces. An **episode** is all rounds sharing
(`work`, `checkpoint`, `criterion`). Kickbacks cap at 2 fix rounds per
criterion; still not satisfied after round 2 → `action=surfaced`, move on.
Grading is advisory — it never blocks an autonomous run; disputes and
surfacing must reach a durable place (journal, issue comment), not a prompt.

## Hard vs. best-effort (no false-green)

**Hard (CI fails, `scripts/process/check_telemetry.py`):** a journal line
that starts with `GRADE ` and carries `key=value` tokens but does not match
the grammar, or whose `verdict`/`action`/`source` is outside the enums, or a
non-numeric `round` — each with file:line. A grade that does not parse is
silent telemetry loss: written, never counted. Non-UTF-8 journals fail.
Malformed calibration cases (invalid JSON, `id` ≠ filename stem, missing
`ground_truth`, out-of-enum verdicts, or a `grader_verdict` whose shape or
criteria set does not match `ground_truth`) fail.

**Best-effort (advisory note, never fails CI):** zero GRADE lines repo-wide
("expected pre-adoption") and an empty calibration suite — the trace only
exists once the workflow starts grading. Whether grading *happened* for a
given change is review discipline, not machine-checked. Two conventions the
gate deliberately does not enforce: per-round uniqueness of a
(`work`, `checkpoint`, `criterion`, `round`) line, and GRADE lines inside
```-fenced blocks — fenced regions are treated as quotations and are
invisible to gate and cockpit (quote literal GRADE examples only there).

## The KPI cockpit

`scripts/process/process_kpis.py` (read-only, never a gate, not in CI) cuts
the existing traces into decision families. Measured numbers print with a
confidence tag — `high` (direct measure, enough n), `medium` (sample-biased),
`low` (proxy or thin n; proxies never reach `high`) — and a confidence-gated
action: at `low` the only action is to collect more data. n before percent.
The two threshold families (`convergence`, `suite`) print pass/not-met against
their documented thresholds instead of a confidence tag.

| family | measures | action (threshold → act) |
|---|---|---|
| `effectiveness` | per-source catch precision: `catch` (action=fixed) / `false_alarm` (disputed) / `surfaced` / `idle` (first-try satisfied) | ≥20 flagged episodes and 0 catch + high idle → trim that grading source; catch>0 → keep it |
| `convergence` | do kickbacks resolve ≤2 rounds, or thrash? (first-try episodes excluded from the denominator) | part of the grader-trust thresholds below |
| `suite` | labeled calibration cases: graded count, danger-direction count, false-passes | grader-trust thresholds below |
| `tempo` | issue cycle time p50/p90 via `gh` (skipped without a tracker) | p90 > 7 d (provisional, uncalibrated threshold) → find the blocking phase |
| `cost` | rework episodes (kickback round>1 → fixed); optional `--transcripts DIR` token medians (harness-specific, `~approx`) | rework>0 → find the criterion that kicks back repeatedly |
| `cfr` | DORA change failure rate: `feat:` with a corrective `fix:` ≤7 d sharing a code file (proxy) | trend over ≥3 windows only; rising despite catch>0 → tighten the test/review gate |
| `friction` | bypass rate — deliberately **not instrumented** | build the bypass event log only when the other families prove friction matters |

## What the numbers can say — and what they cannot (honest ceiling)

Every cockpit number is shaped by project-individual choices: how fine the
acceptance criteria are cut, what tier mix the work happens to have, how old
the codebase is, how strictly the grader words verdicts. These confounders do
not cancel out across projects. The consequences are binding:

- **Within-project only.** A number compares a project against its *own*
  baseline over time. Cross-project comparison ("project A has 40% catch rate,
  project B has 25%, so A's process is better") is meaningless — the number
  difference is dominated by criterion granularity and domain, not process
  quality. The cockpit deliberately has no export/benchmark format.
- **Trends and ratios, not absolutes.** An absolute value carries no
  information until the project has its own baseline (typically the first
  weeks of traces). Act on direction — catch rate falling, rework rising,
  convergence degrading — and on within-project ratios, never on the raw
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
  *attention* — which grading source to keep, which criterion thrashes — they
  never grade people, projects, or model choices, and no cockpit value is a
  target to optimize toward.

## Grader trust: the calibration suite

An AI grader's verdict may replace a redundant review layer only when all
three thresholds hold — until then it stays additive-advisory (the safe
default, no time pressure):

1. **≥ 20 graded cases, ≥ 5 in the danger direction** (pre-fix states of real
   bugs — a clean-feature-only suite measures the wrong regime and hides the
   only dangerous direction).
2. **0 false-passes in the danger direction** — non-negotiable.
3. **≥ 90% kickback convergence** to satisfied in ≤ 2 rounds, from real logs.

Cases live one-per-file under `docs/process/telemetry/calibration/` (`id`
equals the filename stem); an inert `case.example.json` ships as the seed and
is skipped by gate and cockpit. `grader_verdict` stays `null` until an actual
grader run against the (regenerated) diff fills it — only graded cases count,
an unlabeled file is a fixture, not evidence. Grow the suite by piggyback:
when work merges, the diff and its criteria already exist — label a case,
danger-direction cases being the mandatory share.

## One owner per behavior

This module owns the GRADE grammar (`check_telemetry.py`; the cockpit imports
the parser from it) and reads no other module's artifacts. It measures the
process; it does not define acceptance criteria (`feature-registry`), issues
(`github-issues`), or review depth (`risk-tiers.md`). Thresholds are
documented constants in the rendered scripts — this module owns them, adjust
them there with a journal note; only "0 false-passes in the danger direction"
is not negotiable.
