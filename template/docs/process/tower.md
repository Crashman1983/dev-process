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
| `findings` | deterministic, each with a *because* | the list to act on |

## Findings (deterministic)

- **overlap** (high for a shared file, low for a shared directory)
- **plan-without-issue** — Tier 2+ plan, no issue, not waived
- **plan-without-decisions** — Tier 2+ plan without a `## Decisions` section
- **plan-without-tier** — an active plan no gate can see
- **chronic-red** — a gate red for two days or more
- **stale-worker** — a branch with work (ahead or dirty) but no commit and no report for an hour (`--stale-minutes`)
- **blocked** — a worker that reported `blocked` an hour ago and nothing since
- **far-behind** — 50+ commits behind the integration branch

Brainstorm papers (`design-*` plans) and waived stale plans are listed but
never findings: they are not work in flight.

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

## What the tower is not

It decides nothing and speaks to nobody. It is the input an orchestrating
agent reads instead of the sessions themselves — compact, testable, the
same on every run — so that the agent's tokens go into judgment (assign,
redirect, stop) and not into asking thirteen workers how they are doing.
The orchestrator never implements, reviews, or certifies: those stay with
the gates and the independent reviewer (`verification-independence.md`).
