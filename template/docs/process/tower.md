# The tower — situation table for parallel work

Several agents in several worktrees on one clone fail in ways nobody sees
until merge: two branches on the same owner, a worker looping on a busy
lane, a gate red for days, a plan without an issue that no gate can find.
The tower makes that state one computed table instead of thirteen
conversations.

    uv run scripts/process/tower.py                 # short text
    uv run scripts/process/tower.py --json          # the full table
    uv run scripts/process/tower.py --min-severity high

## What it contains

| Section | Source | What an orchestrator does with it |
| ------- | ------ | --------------------------------- |
| `worktrees` | `git worktree list`; ahead/behind the integration branch; paths in flight (merge-base…HEAD); dirty files; minutes since last commit | who is working where, how far from main |
| `overlaps` | intersection of in-flight paths between worktrees (file: high; same directory: low) | decide phase-of / supersede before both push |
| `plans` | active plans and `specs/*/plan.md`: tier, issue, `DECISION` count, `design-contract:` binding, waiver | what is planned, what lacks a ledger |
| `reviews` | today's `REVIEW` passes and blocks by work id | what cleared today |
| `gates` | the runner's red ledger with age | chronic reds |
| `lanes` | `scripts/lane.py status` where the project has it | who holds the test lanes |
| `reports` | the latest `report.py` line per worker | state each worker claims, and how long ago |
| `sessions` | every worker `dispatch.py` started: phase, model, where (tmux window or pid), alive, last printed line and when | the look at the workers; `dispatch.py log <branch>` for more |
| `questions` | open `DECISION NEEDED` lines in active plans | what only the owner can answer — relayed with options, answered as a `DECISION` line |
| `findings` | deterministic, each with a *because* | the list to act on |

## Findings (deterministic)

- **question** (high) — a worker wrote `DECISION NEEDED … — options: …; recommendation: …` into its plan: relay now, answer in the plan
- **overlap** (high for a shared file, low for a shared directory) — never with the integration branch, and `.process-work/` (which every branch writes) is not a shared directory
- **plan-without-issue** — Tier 2+ plan, no issue, not waived
- **plan-without-decisions** — Tier 2+ plan without a `## Decisions` section
- **plan-without-tier** — an active plan no gate can see
- **chronic-red** — a gate red for two days or more
- **stale-worker** — a branch with work (ahead or dirty) but no commit and no report for an hour (`--stale-minutes`); a worker whose latest report is `review-pass`, `done` or `idle` is parked, not stale
- **remote-unreachable** — `--remote` could not fetch; the table may be stale
- **remote-residue** — unmerged branches on origin untouched for 14 days, counted not listed
- **blocked** — a worker that reported `blocked` an hour ago and nothing since
- **far-behind** — 50+ commits behind the integration branch

Brainstorm papers (`design-*` plans) and waived stale plans are listed but
never findings: they are not work in flight. Only date-prefixed files,
`design-*` papers and `specs/*/plan.md` are plans; a README in the plans
folder is not.

**Threat model, honestly.** The tower and the report ledger are plain
files in `.git/`, and `tower.py` runs the project's lane script from the
checked-out tree. Code that already runs in the repository can falsify them; the tower
is evidence for a steward, not a security boundary.

## The worker protocol

Workers report state transitions with `/report` (`scripts/process/report.py`):
`planned`, `pushed`, `review-pass`, `blocked`, `done`, `idle`. One line per
transition, the reason on `blocked`. Reports live in the clone's git common
dir, shared across worktrees on the machine, never committed. A worker on
another machine reports by message; the orchestrator writes the line for it.

## More than one host

The process stays host-agnostic: the steward may run on one machine and a
detached worker (a platform build that needs its own OS) on another. The
one channel every host already has is git, so that is the transport:

- a worker publishes its reports with `report.py --sync` (or
  `PROCESS_REPORT_SYNC=1`) as a blob under `refs/process/reports/<host>`
  on origin — nothing committed to a branch, no ssh;
- `tower.py --remote` (or `PROCESS_TOWER_REMOTE=1`) fetches origin and
  those refs: branches on origin that no local worktree carries appear
  as `elsewhere` (ahead/behind, paths in flight, minutes since commit),
  join the overlap check, and can be stale like a local worker; every
  host's reports are merged, the latest per worker wins.

Starting or stopping a worker on another host stays that host's own
mechanism (an ssh command, a remote session); the steward's rule does not
change: it stops only what it started, and only after plan and decisions
are committed. Host names come from `PROCESS_HOST` or the hostname.

## Dispatch and the model policy

A phase is a session. `scripts/process/dispatch.py start --issue N --phase
plan|execute|review [--tier T]` opens (or reuses) the branch's worktree and
starts a session with the model `docs/process/model-policy.json` assigns
to that tier and phase; the project's own start command is the policy's
`command` template (`{model}`, `{prompt}` are substituted inside the argv
the template splits into; the prompt is one argv element, and it begins
with the phase's slash command so the command file owns the steps).
Between phases the artifacts carry the state: the plan and its
`## Decisions` ledger from plan to execute, the bundle from execute to
review. Two runners: `detached` starts the argv headless (output to a
log); `tmux` starts it as a window of one tmux session (`tmux_session`)
a human can open — interactive, visible, stoppable. The tmux window runs
a non-interactive `sh` that `exec`s the argv with exact POSIX quoting (no
aliases, no rc files), keeps the last screen when the worker exits, and
pipes the output to the log; liveness is the pane's own state, never a
shell pid. `dispatch.py list` shows state and each worker's last line
(the live screen for a tmux worker — a TUI's log is escape codes),
`dispatch.py log <branch>` more of it, `dispatch.py say <branch> "…"`
types a line into a tmux worker (the owner's answer to a question, a
redirect). `dispatch.py stop <branch>` stops only what dispatch started,
only when the recorded process is still the recorded one (pid and start
time), and refuses while the worktree has uncommitted or untracked work
(a plan not committed dies with the process). `max_workers` caps live
sessions per host; a held lane counts as no free CPU. Both runners strip
the steward's own `CLAUDECODE`/`CLAUDE_CODE_*` variables from the
worker's environment: a worker is a session of its own.

Permissions belong to the command, not to dispatch: a headless `claude
-p` needs its tool permissions granted in the project's settings (an
allowlist for Bash, or `--permission-mode`), else it stops at the first
gate; an interactive worker in a fresh worktree may show a trust dialog
on first start — open the window once, or trust the worktrees' parent
directory beforehand.

Trust boundary: the policy's `command` is executed on the machine that
runs dispatch. It is a repository file — whoever can merge to it can run
code on the steward's host. Review a change to it like CI configuration.
The policy is project-owned (list it in `.process-owned` so a template
update never overwrites it). Sessions report their model
(`report.py … --model`, or `PROCESS_MODEL` set by dispatch), and the
telemetry module's `process_kpis.py models` cuts rounds-to-pass and
blocks by tier × phase × model — one issue is one unit, the last model
reported for a phase owns it — the number the policy is judged by.

## What the tower is not

It decides nothing and speaks to nobody. It is the input an orchestrating
agent reads instead of the sessions themselves — compact, testable, the
same on every run — so that the agent's tokens go into judgment (assign,
redirect, stop) and not into asking thirteen workers how they are doing.
The orchestrator never implements, reviews, or certifies: those stay with
the gates and the independent reviewer (`verification-independence.md`).
