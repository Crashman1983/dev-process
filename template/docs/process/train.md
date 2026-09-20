# The merge train — one full suite per batch

Every finished branch paying its own full run and its own deploy is the
most expensive shape parallel work can take: thirteen agents, thirteen
suites, thirteen deploys. The train collects finished branches and merges
them as one batch behind **one** full suite at a good moment
(`scripts/process/train.py`; `testing.md`, "one full run per batch").

    uv run scripts/process/train.py plan                       # who may board, why not, ready?
    uv run scripts/process/train.py run --suite "<full suite>" --deploy "<deploy>" --push

## Boarding — computed, never claimed

A local branch boards when it is ahead of the integration branch and

- carries an **archived plan** added on the branch (the `/finish` archive
  step) whose Tier 2+ plan is **cleared by a REVIEW pass** on the branch's
  journal, or is waived; a worker report `review-pass`/`done`
  (`report.py`) is accepted as the pointer when no archived plan exists,
  never as a substitute for a missing pass;
- has **no file overlap** with a branch already aboard — the earlier
  candidate keeps its seat, the later one is told why;
- the clone's red ledger names **no red gate**.

`train.py plan` prints every candidate with its reasons; `--json` gives an
orchestrator the same.

## Departure — a number, not a judgment

The train departs when at least `--min-candidates` (default 3) are aboard,
or the oldest has waited longer than `--max-wait-hours` (default 4), and
the test lanes are free where the project has a lane script (see `tower.md`, lanes).
`--force` departs with whatever boarded. Environment:
`PROCESS_TRAIN_MIN`, `PROCESS_TRAIN_MAX_WAIT_H`.

## The run

1. A staging branch `train/<stamp>` from the integration branch, in its own
   worktree under the clone's git common dir — the root worktree is not
   touched until the end.
2. Candidates merged in order (`--no-ff`); a conflict drops that candidate
   and continues.
3. The process gates, then the full suite, run **once** on the combined
   tree. Red: the last-boarded candidate is dropped and the train rebuilt
   — linear back-off, the offender is named and gets a `blocked` report.
4. Green: the integration branch fast-forwards to the train; `--push`
   pushes it; merged branches are deleted (`--keep-branches` keeps them);
   every merged worker gets a `done` report; `--deploy` runs once. A failed
   deploy leaves the merge standing and says so.

Run from the root worktree on the integration branch with a clean tree.
The log lives next to the staging worktree (`<stamp>.log`).

## What the train does not do

It does not review, attest or certify. It merges what the process already
cleared, and it earns the one thing a batch must earn: the full suite on
the *combination*, which no branch could have run alone. The coverage
certificate, where the project keeps one, comes from that same run.
