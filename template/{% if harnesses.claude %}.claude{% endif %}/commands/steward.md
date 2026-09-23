# /steward

Run the tower: steer parallel work on this clone — assign, redirect,
stop, dispatch the merge train — and speak only on events. You never
implement, review, attest or certify; the gates and the independent
reviewer keep those (`docs/process/verification-independence.md`).

## Loop

Wake on a tick the owner sets (`/loop 30m /steward` in the steward's
session) or on the owner's message; there is no file watch in this
process — nothing wakes you when a worker writes `blocked` or a
`DECISION NEEDED` line, so the tick is the only guarantee a question is
seen within the interval. If your harness offers a watch on the reports
file (the `reports.jsonl` inside the `process-tower` folder of the git
common dir) or on the workers' plans, use it as an extra wake, never as
the only one. On each wake:

1. `uv run scripts/process/tower.py --json` — the situation table. Read
   it, not the sessions. `docs/process/tower.md` explains every field.
   `sessions` shows every dispatched worker with its last printed line;
   `dispatch.py log <branch>` shows more when the owner asks "what is
   1234 doing?" — answer from the log, never from a guess.
2. Act on the findings in severity order:
   - **question:** a worker wrote `DECISION NEEDED <date> <who>: <question>
     — options: A …, B …; recommendation: …` into its plan (in ITS
     worktree — the tower reads every worktree and every branch on origin)
     and reported `blocked`. Relay it to the owner *complete and at once*
     — and as a choice, not as prose: where the harness offers a
     question tool (Claude Code: `AskUserQuestion`), ask one question per
     worker with the worker's options as the selectable answers, the
     worker's recommendation first and marked "(Recommended)", and the
     context in the question text: issue, branch, the question, and what
     the tower says about the branch. Without such a tool, the same as a
     numbered list the owner answers by number. Never a bare "worker
     blocked", never options buried in a paragraph. Several open
     questions: one call with up to four of them, oldest first. When the
     owner answers, give the answer to the worker that
     asked: `dispatch.py say <branch> "DECISION <date> owner: <answer> —
     because <why>"` for a tmux worker (it rewrites the line in its plan and
     continues); for a headless worker rewrite the line yourself in that
     worker's worktree, commit it there on the worker's branch, and
     `dispatch.py start --phase execute` again — the plan carries the
     answer. Never edit a plan in a worktree whose worker is live without
     telling it: two writers on one file lose one of them.
   - **overlap (file):** tell both workers; decide phase-of or supersede
     (mandatory rule 4) before either pushes.
   - **blocked / stale-worker:** ask once by message (`dispatch.py say
     <branch> "…"` reaches a tmux worker; a headless one only reads its
     plan — write the question there); a worker waiting on a
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
   open and `dispatch.py say` can type into; `detached` runs it headless —
   either way `dispatch.py log` shows what it shows; the policy's
   `command` runs on this machine, so a change to it is reviewed like CI
   configuration),
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
