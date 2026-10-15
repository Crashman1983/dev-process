# Process optimization — the improvement contract

The process improves itself from real results, not from opinion. Agents
notice where development takes too long, burns tokens or produces follow-up
defects; they design a change, try it in a bounded way, and keep only what
the evidence carries. This document is the contract: the loop, who owns
which step, what a record must hold, and what nobody may do.

**The loop:** observe → find the cause → design a change → review it
independently → use it in a bounded trial → judge the effect against criteria
fixed beforehand → adopt or roll back.

A change is judged only once its effect in development is known. A merged
change or a published release does not end an experiment.

## Goals and how they are measured

| Goal | Measure | Where it comes from |
|---|---|---|
| Lead time | start of planning to verified deploy; median and P90, working and waiting time apart | `process_kpis.py flow` (telemetry module) |
| Tokens | every dispatched session of planning, execution, review and repair; cache shares apart (sessions started outside dispatch are not counted) | `flow`, `cost --issue N` (policy `transcripts`) |
| Follow-up defects | escapes after deploy, linked to their origin issue (`Regression-of: #N`, `commits.md`) | `flow` (measured), `cfr` (proxy) |
| Owner effort | owner `DECISION` lines per issue | `flow` (proxy — active time and rescue interventions are not measured yet) |
| Recovery time | detection to working again | not measured until the project records incidents |
| Value kept | the original acceptance criteria hold and the work is usable as intended | DoD (`definition-of-ready-and-done.md`) |
| Value delivered | an epic becomes usable; a disruptive bug reported by the owner is fixed fast | `process_kpis.py outcomes` (the mandate's `outcomes` markers) |

The goals are never folded into one score. Security, correctness and
acceptance are the floor; time, tokens and owner effort are optimized above
it. Building, running and maintaining the optimization counts as cost too.

Every number states whether it is **measured**, **estimated** or **missing**,
and the cockpit's honest ceiling applies (telemetry module): within one
project only, trends over absolutes, events over rates.

## The process as a check graph

Every step that checks or holds up work is a node: the gates of the gate
runner, reviews and refutations, test selection, the train, tier routing.
The loop changes the graph — adds, changes or weakens nodes — so the
measurement starts at the node:

- `process_kpis.py nodes` weighs each gate's cost against its blocks, from
  the gate runner's event log. Raw blocks stay raw; what a block was comes
  only from triage (`.process-work/gate-triage.jsonl`), and `unknown` is no
  evidence for weakening anything.
- `process_kpis.py losses` keeps four loss measures apart — occupancy, delay,
  owner effort, tokens — and never sums them.
- `process_kpis.py outcomes` says what the work is for: epics to usable,
  disruptive bugs to fixed, and how well bug origin (cause × channel) is
  labelled.

A node changes through `scripts/process/gate_modes.py`, and only there: the
append-only record `docs/process/gate-changes.local.jsonl` sets each gate's mode
— `block` (default), `shadow` (runs and records, never blocks), `sampled`
(runs on a stable share of commits, never blocks) or `off`.

- **Weakening** needs an owner decision line, every time, in this release.
  Core gates and the mandate's `guardrails.protected` gates cannot be
  weakened at all.
- **A weakening counts once it is on the remote integration branch**
  (`origin`'s default branch, never a local `main`, which at pre-push time
  may be the very commit pushed); a branch cannot weaken a gate for its own
  push, nor un-protect one in its copy of the mandate (the base's
  `protected` list holds too). Without a remote, no weakening counts. A
  restore counts at once — in the working tree that holds it; merge it
  promptly so every other checkout blocks again too.
- **The sentinel** (`gate_modes.py sentinel`, deterministic, run daily by
  the steward) only restores: a shadow or sampled gate that failed on a
  clean commit, and every still-active weakening that touches a breached
  guardrail (`guardrails.limits` in the mandate), newest first. Newest
  first is containment, not a claim about the cause. A restored gate is
  locked until `unlock` records a triage. It reads the gate event log of
  the checkout it runs in: runs on other hosts, in CI (whose log ends with
  the runner) or on a dirty tree are not seen — run it where the gates run.
- **A new gate** can be observed first: `weaken GATE --to shadow --observe`
  (owner line as always) lets its failures stand, so false alarms are
  counted before it blocks. Never for a gate that used to block.
- **The record** lives in `docs/process/gate-changes.local.jsonl`, under review
  like any process configuration; the owner line in it is text, and review
  is what backs it.
- **A new check** is new executable behaviour: it comes in through the
  project's normal code review. Setting a reviewed check's mode is
  configuration. Running a check without blocking does not make it
  harmless — it can still change files or call a service.
- **Evidence for weakening** is triage, not raw blocks (`nodes`; failures in
  shadow or sampled mode count apart, as what the gate would have stopped). Keep a
  residual sample (`sampled`) rather than `off`; `off` wants a replacement
  shown on known failing inputs, or the owner's explicit judgement. Never
  argue a rare, severe class (security, destructive changes) from "no
  catches in the sample".

Not every node is a gate. **Plan drift** (`scripts/process/plan_drift.py`)
is asked by `dispatch.py start --phase execute`: for each active plan the
issue declares, how many commits the integration branch has gained since
the plan was last written, and how many of them change a file the plan
names. A plan hundreds of commits old costs the worker its first hour, or
gets built against code that is gone. The node writes a `plan-drift` line
to the same event log, so `nodes` weighs it like a gate and `flow` shows
each issue's last verdict. Its mode and limits are the mandate's
(`plan_drift`: `mode` shadow | warn | block, `max_touching`, `max_behind`);
it starts in `shadow`, whose events calibrate the limits. `warn` tells the
steward and puts a re-check note into the worker's prompt; `block` refuses
the start until the plan is refreshed (the plan phase), or the steward
passes `--stale-plan-ok`, which the event records. The mandate is the
owner's file, so the owner turns the node up — on the shadow evidence.

Two briefs run the loop, in any harness: `improvement-weekly.md` (the
steward's weekly pass: last prognosis, a few triaged blocks, blind spots,
one ranked action) and `improvement-monthly.md` (a fresh, advisory review
of the graph, the decisions, the signals and the guardrails).

## Roles

Two standing roles carry the loop. Independent reviewers and specialised
workers join for bounded tasks; scripts collect and compute the numbers.

| Responsibility | Steward (this project) | Process maintainer (the process source upstream) |
|---|---|---|
| Coordinate the project's development | owns it | supports with process mechanisms |
| Notice operational problems | records bottlenecks and their impact | analyses recurring causes |
| Prioritise improvements | the project's needs and capacity | technical process work and its generic value |
| Build process changes | commissions and coordinates | owns them in the process repository |
| Project-specific changes | commissions project workers | supplies interfaces and recommendations |
| Generic usability | supplies the project's requirements | owns it |
| Rollout in the project | coordinates update, pilot and rollback | supplies a versioned change and migration notes |
| Judge the effect | owns the project's adoption decision | owns the analysis and the mechanism's improvement |

Both roles are sessions that restart. What makes them standing is the
record: decisions and evidence live in files, messages only coordinate.

- **The steward** stays a coordinator: it never implements, reviews,
  attests or certifies (`verification-independence.md`). Its prioritisation
  concerns this project; it creates no obligation for the process core.
- **The process maintainer** may decline a proposed generalisation and
  recommend a project-local solution, and may start work that keeps the
  process maintainable and portable even when no project reports a defect.
  Its role is described where the process is maintained, not in every
  project that uses it.
- **Nobody signs off their own change.** The record names its
  `implementer`; the review before the trial and the adoption decision are
  someone else's — `optimize.py` refuses both from the implementer.

## Placement

Every proposal gets a reasoned placement before it is built:

| Placement | Where | Example |
|---|---|---|
| `core` | the process core | experiment states, hand-over contract, validity of evidence |
| `module` | an optional process module | a dependency graph, more measurement adapters |
| `config` | the project's configuration | budgets, model policy, quality floors, concurrency limits |
| `project` | the project itself | deployment integration, domain acceptance checks |

For `core` and `module` changes: no project paths, infrastructure or
business rules built in; project values come through existing or clearly
defined configuration (`*.local.json`); optional capabilities stay optional;
the change is proven in a minimal project without the project's extensions
and in every affected supported variant (harnesses, CI adapters, module
sets); existing contracts and migrations are honoured; a new abstraction
needs a demonstrated reuse. A change can be right for this project and wrong
for the core — then it is built locally.

## The record

One file per improvement: `.process-work/optimizations/OPT-NNNN-<slug>.md`,
created by `uv run scripts/process/optimize.py new --title … --mechanism …`.
Its header carries the machine fields, its sections the substance. The
record is **plain Markdown** — no HTML or comment (not even in inline code:
write `a < b`), no code fence, no link reference definition, no line break
but `\n` — so what the tool reads is what a reader sees; placeholders are
`TODO` paragraphs. The header holds `key: value` lines, the Log only
the lines `optimize.py` writes, and the Log is append-only; below
`## Result` only Result, Decision and Log stand as headings; a heading or
header field that appears twice is a problem; names are compared without
case or spacing (`Maintainer` is the `maintainer`).

| Part | Holds |
|---|---|
| header | `state`, `responsible` (who decides the project's trial), `implementer`, `mechanism`, `placement`, `flag`, `select`, `until`, `budget-tokens`, `budget-hours`, `issues`, `upstream`, `supersedes`/`superseded-by`; `spent-tokens`/`spent-hours` as the trial runs |
| Observation | affected issues, what was observed, evidence and its data quality |
| Hypothesis | the suspected cause and why the change should help |
| Placement | core, module, config or project — and why there |
| Trial | baseline, process version, which work is in, exclusions |
| Limits | budget, duration, quality floors, stop conditions |
| Criteria | success criteria: metric, minimum n, minimum effect |
| Generality | affected supported variants and the checks that prove them |
| Rollback | how use stops, and the safe way back for code or data already changed |
| Result | measured against the criteria: time, tokens, interventions, escapes, upkeep |
| Decision | adopt, reject, roll back, or continue in a new record |
| Log | one dated line per transition, `REVIEWED` and `FROZEN` lines |

The record is the one place of an improvement. Implementation issues may
live in different repositories and are linked from it; the steward owns the
project's decision in the record, the process maintainer owns the generic
adoption in the upstream issue and release. Each decision has exactly one
owner.

A record that answers a measurement milestone (`due_measurements.py`)
carries one line `milestone: <id>` in its free text, not in the header —
the header holds `key: value` lines only. Without that line the milestone
stays due: fail-loud, not silently done.

### States

`proposed` → `designed` → `piloting` → (`stopped` →) `evaluating` →
`adopted` | `rejected` | `rolled-back` | `superseded`; a proposal can be
`rejected` before it runs. `optimize.py move <record> <state> --who …
--because …` writes a transition only when the state's needs hold:

- `designed`: Observation, Hypothesis and Placement filled; `placement` set.
- `piloting`: a mandate exists; Trial, Limits, Criteria, Generality and
  Rollback filled; `select`, `until` (within the mandate's
  `max_pilot_days`) and both budgets set; a `REVIEWED … pass` line on exactly
  these terms by someone other than the implementer
  (`optimize.py review`). The move writes the `FROZEN` line.
- `adopted`: Result and Decision filled; by the owner, or by the steward
  where the mandate allows it; never by the implementer.

`check` and `active` re-derive every one of these rules from the record —
who started it, who reviewed which terms before the freeze, the start not
dated ahead, the mandate's limits measured from the `FROZEN` date — so a
state, a log line or a freeze written by hand gains nothing. A
`REVIEWED … block` on the frozen terms is not outvoted by a pass. The
`FROZEN` line carries the mandate as it was (`max_pilot_days`,
`steward_may`): a finished trial is judged by it, a running one also by the
mandate as it is now, so a narrowed mandate binds what runs and leaves what
was decided alone.

**An experiment does not ease its own criteria.** The freeze is
byte-exact: everything above the line `## Result` — header, Observation
to Rollback — stays as it was, except `state`, `spent-tokens`,
`spent-hours` and `superseded-by`. No reading of Markdown decides what is
frozen; the mutable fields hold only their values. With git history,
`optimize.py check` also indexes every committed version of every record by
its number: every committed Log is a prefix of today's (append-only — a
moved block, an edited `FROZEN` line, a record un-run or replaced is seen),
each version that ran carries today's terms, and a record that ran must not
vanish — across renames, renumberings and merges. Rewritten history (amend, rebase,
force-push) and a shallow clone are beyond what a file check sees; names
are self-declared, and the owner's sample is the control for that.
New criteria mean a new record that `supersedes` this one.

### Bounded use and rollback

A process change under trial ships behind a flag, off by default — every
other project keeps today's behaviour. The mechanism asks
`optimize.py active <flag> --issue N --tier T --class C` (or imports
`optimize.active`), and the answer is yes only while exactly one `piloting`
record carries the flag, its terms are intact, today is not past `until`,
and the work matches `select` (`issues=…`, `tiers=…`, `classes=…`,
`parity=odd|even` for a concurrent control group, or `all`). Every doubt
reads as off.

Rollback has two steps. **Stop use:** move the record to `stopped` — the
flag is off at once; anybody may stop an experiment, because stopping is the
safe direction. **Undo effects:** code or data the trial already changed
needs its own safe way back, written in `## Rollback` before the trial
starts.

## Decision rights

A one-time **mandate** (`docs/process/optimization.local.json`, from
`optimization.example.json`) states the project's goals, floors,
budgets and the steward's rights. Without it, analysis is allowed and a
trial is not.

| Decision | Who |
|---|---|
| Reprioritise work within the existing rules | steward |
| Investigate and build improvements | process maintainer (upstream), project workers (local) |
| Start a trial within the mandate | steward, after the independent review |
| Take a change into the process source | process maintainer, through that repository's review and release path |
| Stop a trial whose stop condition is violated | anyone — the steward, the owner, an automatic guard |
| Lower a quality floor, widen the mandate, raise a budget | the owner |
| Change fundamental product or compatibility promises | the owner |

The mandate is a process file: a change to it is the owner's decision and is
reviewed like any change to the process configuration.

## Measuring honestly

- Keep measured values, estimates and missing values apart.
- Compare like with like: comparable issues within this project.
- Count failed and abandoned attempts.
- Name changes in task mix, model, host or test procedure during the window.
- Attribute later defects afterwards (`Regression-of: #N`).
- Report **inconclusive** when the data cannot carry a decision — below the
  minimum n fixed in the Criteria, the result is inconclusive by rule.
- Generalise from one project only with a stated reason why it transfers.

Starting points, set in the mandate and calibrated against the baseline:
about 20–30 issues for a first bottleneck analysis, 30 days of follow-up for
escapes, one live trial per project at a time (`optimize.py check` refuses a
second piloting record, whatever its mechanism or flag), and an optimization
budget of about 10 % of the measured tokens and execution time over 30 days,
setup counted apart. Small samples prove nothing about rare severe defects.

Every loop has a success criterion, a time and token budget and an exit
rule. The existing diagnosis and review round limits stay in force.

## Rhythm

The steward runs `optimize.py status` and `optimize.py check` in its daily
housekeeping, not on every tick: an expired trial is moved to `evaluating`,
a budget overrun stopped, a broken record fixed by its responsible. The
analysis itself is cheap reading (`process_kpis.py flow`, `report`); it must
not cost more than it saves.

## Not a gate yet

The rules above are enforced where they are used: `active` turns a tampered
or expired experiment off, `move` and `review` refuse. A project that runs
experiments may register `optimize.py check` as its own gate in
`docs/process/gates.local.json`. Whether the check becomes a core gate is
decided once real experiments have run.

## Done means

**Effective for the project, placed in the right repository, independently
reviewed, and proven for the affected generic scope.** A positive trial in
one project does not prove portability; a correct release of the process
does not prove value in the project.
