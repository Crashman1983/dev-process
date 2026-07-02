# Design: telemetry (SP10)

**Date:** 2026-07-02
**Status:** approved (scope: efficiency review item 2 — graders/telemetry —
deferred in SP8 pending the Kenni grader spec, which is now accessible)
**Slice:** make process efficiency measurable — a graded-acceptance trace
convention, a gate that keeps the trace parseable, and a read-only KPI cockpit
where every number carries confidence and an action.

## Gap

The 2026-07-02 audit confirmed what SP8 had already deferred: the process
enforces discipline but never measures whether that discipline pays off. No
artifact records what the review/execute phases actually catch, how often work
kicks back, whether defects slip through despite the gates, or where the cycle
stalls. A process whose pitch is "enforcement, not prose" must also be able to
say *what the enforcement buys* — otherwise gate-trimming decisions (which
check earns its churn?) are vibes, exactly the failure mode the mandatory
rules exist to prevent.

Kenni solved this in three parts, all now readable: a `GRADE` trace line the
execute/review kickback loops append to journals, `grade_metrics.py` (grader
calibration: convergence + a labeled case suite with hard thresholds), and
`process_kpis.py` (a read-only cockpit over four decision families, every
number framed with confidence and a gated action). This slice generalizes that
system; the Kenni-specific parts are named and left behind.

## Decision 1 — the trace is the instrument; no new pipeline

Kenni's §7 explicitly rejected a dedicated measurement pipeline as
superstructure; measurement rides on artifacts the workflow already produces.
Ported: whenever a phase grades acceptance criteria (execute checkpoints, the
review gate, quick's lightweight check), it appends **one line per criterion
per round** to the day's journal (`.process-work/journal/`):

```
GRADE work=<id> checkpoint=<n|final> criterion=<id> round=<n> \
      verdict=<satisfied|partial|not_satisfied|out_of_scope> \
      action=<satisfied|fixed|disputed|surfaced> source=<plan|execute|review|quick|debug>
```

Keys are English (SP8 canon), generalized from Kenni's `issue=`/`ak=`:
`work=` carries the issue number where the github-issues module supplies one,
else the plan slug — the field is an attribution key, not a tracker coupling.
Verdict/action semantics are ported unchanged: they survived six calibration
spike rounds and two parser bugfixes (#317, #318) in production.

## Decision 2 — the gate lints the trace; the cockpit never gates

The one thing worth *enforcing* is that the trace stays machine-readable:
Kenni's #318 showed a GRADE line with an empty `checkpoint=` silently falling
through the parser — the most important grade, unparsed, reported nothing.
`check_telemetry.py` (registered in the gate_runner) hard-fails any journal
line that starts with `GRADE` but does not match the grammar, or that carries
an out-of-enum verdict/action/source, with file:line diagnostics. Non-UTF-8
journals fail per the shared guard convention. Zero GRADE lines repo-wide is a
**soft note** ("no telemetry yet — expected pre-adoption"), never a failure:
blocking every commit on a practice that only pays off over weeks would be
dishonest friction.

The cockpit itself (`process_kpis.py`) reads and reports only — never blocks,
never mutates, never runs in CI. That split is load-bearing: Kenni's design
warns that a grader hardened into a gate artifact grows accretions.

## Decision 3 — every number carries confidence and an action

The cockpit ports Kenni's bias-class framing wholesale, because it is the part
that makes a KPI page more than vanity: each family prints the number, a
confidence tag (`high` — direct measure, enough n / `medium` — sample-biased /
`low` — proxy or thin n; proxies never reach `high`), and a
confidence-gated action — at `low` the only action is "collect more data",
never acting on a thin or confounded number. n before percent.

Families (subcommands, plus `report` for all):

- **effectiveness** — per-source catch precision from GRADE episodes:
  `catch` (action=fixed) / `false-alarm` (disputed) / `surfaced` / `idle`
  (first-try satisfied). Action at confidence: trim a gate with 0 catch and
  high idle; keep a gate that demonstrably catches.
- **convergence** + **suite** — the grader-trust instruments: kickback
  convergence (≥90% resolved ≤2 rounds, first-try episodes excluded from the
  denominator) and the labeled calibration suite (≥20 graded cases, ≥5
  danger-direction, 0 false-pass in the danger direction — non-negotiable).
  Only cases an actual grader run has labeled count; unlabeled fixtures are
  not evidence (Kenni #318 vacuity guard).
- **tempo** — issue cycle time p50/p90 over the last closed issues via `gh`;
  degrades honestly when `gh` or an issue tracker is absent ("tempo skipped"),
  flags its sample cap and the un-calibrated p90 threshold as provisional.
- **cost** — rework episodes (kickback round>1 → fixed) from GRADE lines;
  optional `--transcripts DIR` scans harness transcript JSONL for
  `output_tokens` (harness-specific, marked `~approx`, median per session —
  the cumulative sum is context, not a decision number).
- **cfr** — DORA change failure rate as a proxy: share of `feat:` commits with
  a near-term corrective `fix:` (≤7 days, code-file overlap only — process
  artifacts would fabricate failures). Trend-only reading, DORA bands printed
  for framing, never a single-value action.
- **friction** — deliberately a stub: the bypass-event log is the only piece
  needing real new instrumentation and stays gated until the other families
  prove friction matters (Kenni iteration-2 discipline).

## Decision 4 — one parser owner, two scripts, one module

Kenni splits `grade_metrics.py` / `process_kpis.py` for phase-history reasons
and bridges them with a sibling import. Greenfield port: the grammar, parser,
and enums live in `check_telemetry.py` (the gate needs them anyway); the
cockpit imports them from its sibling. The no-cross-import rule applies
*between* modules; these are two files of one module. Cockpit episode
classification, confidence framing, and family logic live in the cockpit.

## Decision 5 — emission is anchored in the workflow, not the adapters

Command adapters stay module-agnostic (SP6 invariant). `workflow.md` becomes
`workflow.md.jinja`: with the module active, the Execute and Review sections
gain one sentence each pointing to `docs/process/modules/telemetry.md` for the
trace duty. The phase description is the owner of phase duties; the module doc
carries the grammar, the episode semantics, and the calibration practice
(piggyback growth: when work merges, diff + criteria already exist — label a
case; danger-direction cases, pre-fix states of real bugs, are the mandatory
share, because a clean-feature-only suite measures the wrong regime).

## Not ported (Kenni-specific, named honestly)

The §7 layer-removal decision itself (which redundant review layer a
calibrated grader may replace is a project decision, not template mechanics);
grader model/worker choices (Sonnet floor, Codex shellout); the transcript
default path; FLOOR-WARN anti-skip nudges and issue heartbeats (coupled to
Kenni's multi-host issue workflow). The thresholds (20/5, 0 false-pass, 90%,
≤2 rounds, 7-day CFR window) port as documented defaults with their honest
labels: DORA bands are externally published, the flagged-episode floor is
reasoned, the tempo p90 threshold is an uncalibrated heuristic and says so.

## Out of scope

Bypass-event log (friction iteration 2, gated); KPI time series / trend
storage; per-issue token attribution; any hook/daemon instrumentation; a
copier answer for telemetry config (zero-config module — thresholds are
constants with documented rationale, overridable per project by editing the
rendered script it owns).
