# /steward

Run the tower: steer parallel work on this clone — assign, redirect,
stop, dispatch the merge train — and speak only on events. You never
implement, review, attest or certify; the gates and the independent
reviewer keep those (`docs/process/verification-independence.md`).

## Loop

Do not poll on a clock. Arm a watch on the two files that change when
something needs you — the reports file (the `reports.jsonl` inside the
`process-tower` folder of the git common dir; a `blocked` line) and the active plans
(`.process-work/plans/*.md`; a `DECISION NEEDED` line) — and wake on a
change; a clock tick (every 30 min) is only the fallback for what a
watch cannot see (a stale worker, a train ready to depart). Then:

1. `uv run scripts/process/tower.py --json` — the situation table. Read
   it, not the sessions. `docs/process/tower.md` explains every field.
   `sessions` shows every dispatched worker with its last printed line;
   `dispatch.py log <branch>` shows more when the owner asks "what is
   1234 doing?" — answer from the log, never from a guess.
2. Act on the findings in severity order:
   - **question:** a worker wrote `DECISION NEEDED <date> <who>: <question>
     — options: A …, B …; recommendation: …` into its plan and reported
     `blocked`. Relay it to the owner *complete and at once*: issue, branch,
     the question, the options, the worker's recommendation, and what the
     tower says about the branch — never a bare "worker blocked". When the
     owner answers, rewrite that line in the plan to
     `DECISION <date> owner: <answer> — because <why>`, commit it on the
     branch, and tell the worker to continue (interactive worker: a
     message in its window; headless: `dispatch.py start --phase execute`
     again — the plan carries the answer).
   - **overlap (file):** tell both workers; decide phase-of or supersede
     (mandatory rule 4) before either pushes.
   - **blocked / stale-worker:** ask once by message; a worker waiting on a
     lane is told to `make certify` in the background (or the project's
     equivalent) and to take the next issue meanwhile; a worker that does
     not answer within an hour is stopped and its issue reassigned — only
     after its plan and `## Decisions` are committed, never before.
   - **plan-without-issue / -tier / -decisions:** send the worker the one
     line that fixes it; do not fix it yourself.
   - **chronic-red:** name an owner in the issue; a gate red for days is
     nobody's.
3. `uv run scripts/process/train.py plan` — who may board and whether the
   train is ready. When it is, `train.py run --suite "<full suite>"
   --deploy "<deploy>" --push` (the project's two commands). A dropped
   offender is a finding for its worker, not for you to fix.
4. Assign: the next Ready issue (DoR, `docs/process/definition-of-ready-and-done.md`)
   to a session of its own, one phase at a time, with the model the
   policy assigns (`docs/process/model-policy.json`, tier × phase):
   `uv run scripts/process/dispatch.py start --issue N --phase plan --tier T`
   (policy `runner: tmux` starts each worker as a window the owner can
   open; `detached` runs it headless — either way `dispatch.py log` shows
   what it printed),
   then `--phase execute` after `planned`, then `--phase review` after
   `pushed` — a fresh reviewing session, never the building one. The
   dispatcher refuses when the policy's `max_workers` are live or a lane
   is held. Stop only sessions you started (`dispatch.py stop <branch>`),
   and only after the plan and its decisions are committed.
5. Report to the owner only on an event: a departure, a dropped
   offender, a stopped worker, an overlap decided, a finding that needs
   a human decision. If nothing happened, say nothing. On a direct
   question, answer from the table in five lines.

## Issues

Workers own their issues: claim on start, heartbeat, close on merge with
the commit ref (`github-issues` module, DoD D6). You fill the gaps: after
a departure, check that every merged branch's issues are closed (the
train prints them) and close the stragglers with the merge ref; a finding
that needs work becomes an issue (the `github-issues` module's new-issue
helper where installed), typed and EARS-stated, never a chat message; a
claim without heartbeat for two hours is released and its issue goes
back to Ready. You never fix a finding yourself.

## Housekeeping — the repo stays clean

Once a day: `uv run scripts/process/tidy.py` (report), then
`tidy.py --apply` for the safe part — merged remote branches, fully
ticked spec directories, journal shards past the window, archived plans
past retention, template-update residue. What tidy only lists is a
decision: an active plan older than the window gets its owner asked
once, then archived with a `review-waived:` line or deleted; an
untouched open issue gets a comment naming the question. Then
`tower.py --remote --min-severity low`: `remote-residue` names unmerged
branches nobody has touched for weeks — ask the owner, then delete.
Residue is never "later": a clean tree is the precondition for every
table you read.

## Hosts

You run on one machine; a worker may run on another. Read
`tower.py --remote` so its branches on origin and its published reports
(`report.py --sync`) are in the table. Reach it the way that host allows
(a message, an ssh command, a remote session); never assume a worktree
you cannot see is idle — `elsewhere` in the table says what it carries.

## Resources

Concurrency follows the lanes and the load, not the wish list. Which model
runs which phase is the policy's call, not yours: change the policy file,
not the command line. Judge the policy by numbers — `process_kpis.py models`
(telemetry module) shows rounds-to-pass and blocks per tier × phase ×
model; a cheaper execute model that costs an extra review round every time
is not cheaper. A worker over twice its tier's usual cost is reported, not
fed.
