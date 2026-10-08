# The merge train — one full suite per batch

Every finished branch paying its own full run and its own deploy is the
most expensive shape parallel work can take: thirteen agents, thirteen
suites, thirteen deploys. The train collects finished branches and merges
them as one batch behind **one** full suite at a good moment
(`scripts/process/train.py`; `testing.md`, "one full run per batch").

    uv run scripts/process/train.py plan                       # who may board, why not, ready?
    uv run scripts/process/train.py run --suite "<full suite>" --deploy "<deploy>" --push

**`--suite` is the full suite of every stack**: backend, frontend, whatever
the repository ships. A stack the command leaves out is untested at the
merge, and nothing downstream catches it when there is no CI. Put one make
target behind it (e.g. `make test-merge` = frontend + backend) rather than a
single stack's runner. Without `--suite` the train runs the process gates
only and says so.

## Boarding — computed, never claimed

A local branch boards when it is ahead of the integration branch and

- carries an **archived plan** added on the branch (the `/finish` archive
  step) whose Tier 2+ plan is **cleared by a REVIEW pass** on the branch's
  journal, or is waived; a worker report `review-pass`/`done`
  (`report.py`) is accepted as the pointer when no archived plan exists,
  never as a substitute for a missing pass. Only the branch's **own** plan
  counts: one whose issue number or slug the branch name carries, or one
  the base did not have. Archiving another work's cleared plan is
  housekeeping — it clears nothing (a template-update branch once boarded
  on seven such plans while its own review still ran);
- changes the gates' code (`scripts/process/`, `.githooks/`) only with a
  **REVIEW pass for its own work**, whatever its tier — no Tier 0-1 plan,
  waiver or report lets unreviewed gate code onto main;
- has **no file overlap** with a branch already aboard — the earlier
  candidate keeps its seat, the later one is told why;

(The clone's red ledger naming no red gate is a *departure* condition for
the whole train, not a per-candidate reason.)

`train.py plan` prints every candidate with its reasons; `--json` gives an
orchestrator the same.

## Departure — a number, not a judgment

The train departs when at least `--min-candidates` (default 3) are aboard,
or the oldest has waited longer than `--max-wait-hours` (default 4), and
no lane but `scoped` is held where the project has a lane script (see
`tower.md`, lanes). The suite runs on `full`, niced beside the short
`scoped` runs; a train that waited for every pre-push to finish left once
a day downstream, with five reviewed candidates waiting.
`--force` departs with whatever boarded. Environment:
`PROCESS_TRAIN_MIN`, `PROCESS_TRAIN_MAX_WAIT_H`.

## The run

1. A staging branch `train/<stamp>` from the integration branch, in its own
   worktree next to the root (`<root>-train`, a sibling like dispatch's
   worktrees, never under `.git/` — tools that skip every path with a
   `.git` segment would see an empty tree there) — the root worktree is
   not touched until the end.
2. Candidates merged in order (`--no-ff`); a conflict drops that candidate
   and continues. The merge finishes the passenger's work: its own active
   plans with a clearing review (or none required) move to the archive
   inside the merge commit — the chain stays merges only — and the merge
   message says `Closes #N` for the issues of its own plans, so the forge
   closes them when the merge lands. A plan left active after its merge
   kept claiming its files, and the review gate blamed later, separately
   reviewed changes on it; it now names such a plan as residue instead. A
   plan that must outlive the merge says `plan-stays-active: <why>`; it
   stays, and its issue stays open. Another work's plan the passenger only
   touched is left alone.
3. The process gates, then the full suite, run **once** on the combined
   tree. Red: the **same tree runs once more** — red then green on
   identical code is a flaky test, reported as FLAKY and merged, never
   bisected (bisecting a flake blames whoever sits in the prefix). Red
   twice: the base itself is checked once (a red main blames nobody and
   aborts; its gates always run, its suite only when no earlier train saw
   it green on that very tree, `green-suites` in the train's directory),
   then a bisection over boarding-order prefixes names the first
   offender; it is dropped, gets a `blocked` report, and the rest is
   rebuilt. A suite that does not exist on a tree — a passenger introduces
   it — makes that tree *not comparable*, never red: the base is not called
   red, a prefix is not blamed. A combined tree that reads undefined has the
   base checked: a base that HAS the suite makes it a passenger's removal
   (a deleted make target, a broken script) — red, and the search blames
   whoever loses it; a base without it aborts ("fix --suite"). One rule
   decides (`decide()` in `train.py`, one table row per case), first row
   that applies: exit 0 is green; any make call of the suite failing on a
   defined target (`*** [file:N: target] Error n`, also run into output
   without a final newline, or make's "Waiting for unfinished jobs") is
   red, even when a later call finds no rule; a missing prerequisite
   (`…, needed by …`) or a missing include is red; the suite's own entry
   file missing from the tree is undefined — the script it starts with
   (run by its path, or by `sh`, `bash`, `python3`, `uv run`, also
   behind `timeout`, `nice`, `env`, `exec`, `command`), make's `-C dir` or
   `-f file`, or a `cd dir &&` in front — when the command is one `&&`
   chain; every `No rule to make target` stop naming a target the suite
   command itself names (exit 2) is undefined; exit 127 is undefined only
   when the train's shell did not find a command of the suite's own `&&`
   chain that is no file in the tree (a script that is there but broken —
   CRLF line ends, a missing interpreter — is red); a tool missing inside
   the suite is red; anything else is red. Only the suite's own make level
   counts (`make:` run bare, `make[1]:` under `make train`). Read red on
   purpose: a translated make (run the train with `LC_ALL=C`), output
   redirected away from the train (`make test > log`), a target spelled
   through the shell (`make test-${X}`), a missing file behind `;` or `||`
   (an earlier failure may hide there), `python -m pytest tests/new` (the
   path is the tool's argument, not the suite's file). `make nope test`
   stops before `test` runs and reads undefined; a pipe hides the exit
   code (`make test | tee log` is green when `tee` is). Every red verdict logs the load average — a timeout under
   load 10 on 6 CPUs is a different finding from a broken test. A
   candidate dropped for a merge conflict is reported `blocked` too, with
   "rebase" as the reason.
4. Green: with `--push` the train is pushed as the integration branch
   *first* (a rejected push — branch protection, a race, the local
   pre-push hook — leaves local main untouched and keeps the train branch;
   the message says which of them refused and quotes its reasons); then local main
   fast-forwards. Local main carrying commits that are not on origin
   refuses to depart. The worktree of each merged branch is removed
   (each carries its own venv/node_modules; downstream, 111 left behind
   filled the disk) unless it holds an uncommitted change, an untracked
   file git does not ignore (an uncommitted journal shard), an ignored
   file that is no regenerable environment or cache (`.env`, a note in
   `.git/info/exclude`), another worktree nested inside it, a live
   dispatch session or a lock, or its branch has no commits of its own —
   the train names each one it kept and why,
   and a failed removal is a note, never a failed train; `dispatch.py`
   owns that verdict, `tidy.py` asks the same. Immediately before removal,
   dispatch rechecks the full keep policy against the caller's integration
   base, with fresh worktree and session records. External writes during
   Git's deletion remain a non-atomic boundary; stop external writers before
   cleanup when that matters. Merged branches are deleted (`--keep-branches`
   keeps them; a branch checked out elsewhere is kept, locally and on
   origin, and said so); every merged worker gets a `done` report;
   `--deploy` runs once. A failed deploy leaves the merge standing and
   says so.

Run from the root worktree on the integration branch with a clean tree.
The log lives in the clone's git common dir (`process-train/<stamp>.log`).

## Who pushes to main — the merge route

A push to main is the merge, and the pre-push guard
(`scripts/process/merge_route.py`, installed by `install_hooks.py` where it
reads git's own pre-push ref lines — every ref of the push, and the SHA
the remote holds) decides it before any gate. Observed downstream: a review
session reset its branch onto main and published 16 commits past a `block`.

- **Plan and review sessions never push to main.** The phase is the
  strictest of `PROCESS_PHASE` and every live dispatch record of this
  session (same worktree, same branch, or an ancestor process). A record the
  guard cannot read — or a phase it cannot determine — refuses the push;
  `dispatch.py stop <branch>` clears a record whose session has ended.
- **The route is named.** The train and `finish.py --apply` set
  `PROCESS_MERGE_ROUTE=train|finish` for their own push to main and for
  nothing else. Any other push to main is refused.
- **The owner override** — `PROCESS_OWNER_OVERRIDE="<reason>" git push …` —
  passes a push past the train. It needs a reason, is refused from a
  dispatched session, and appends one line (time, user, host, branch, head,
  kind, reason, targets) to `<git-common-dir>/process-owner-overrides.log`.
- **Skipped gates** (`SKIP=process-gates`, or `--bypass NAME` from a
  project's own hook switch) on a push to main keep the phase bar, need no
  route, skip the standing-block check with the gates, are refused from a
  dispatched session, and land in the same ledger.

The review gate adds the verdict: on the merge push, a work whose latest
REVIEW (highest round; a tie goes to the block) is `verdict=block` stops the
push, whatever its tier, read from the commits of the pushed range
(`check_review.py`; `--standing-block <sha>[:<remote_sha>]` for a custom
hook that reads git's ref lines). The markers are environment variables and
can be forged; the guard makes the intent explicit and the bypasses
visible. `--no-verify`, `SKIP=merge-route` and a clone without hooks stay
out of its reach.

## What the train does not do

It does not review, attest or certify. It merges what the process already
cleared, and it earns the one thing a batch must earn: the full suite on
the *combination*, which no branch could have run alone. The coverage
certificate, where the project keeps one, comes from that same run.

## Push timeout

Git pushes get 1800 seconds by default so full pre-push hooks can finish.
Set `PROCESS_TRAIN_PUSH_TIMEOUT_SECONDS` to a positive integer to change it,
for example `PROCESS_TRAIN_PUSH_TIMEOUT_SECONDS=2400 uv run scripts/process/train.py run --push`.
An invalid value refuses the push; other Git operations keep their 300-second timeout.
