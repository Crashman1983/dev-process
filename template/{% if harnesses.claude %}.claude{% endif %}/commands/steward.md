# /steward

Run the tower: steer parallel work on this clone — assign, redirect,
stop, dispatch the merge train — and speak only on events. You never
implement, review, attest or certify; the gates and the independent
reviewer keep those (`docs/process/verification-independence.md`).

## Loop

1. `uv run scripts/process/tower.py --json` — the situation table. Read
   it, not the sessions. `docs/process/tower.md` explains every field.
2. Act on the findings in severity order:
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
   to an idle worker, in a worktree of its own, with the issue, the tier
   and the contract it binds to. Start a worker only when a lane and CPU
   are free; stop only workers you started.
5. Report to the owner only on an event: a departure, a dropped
   offender, a stopped worker, an overlap decided, a finding that needs
   a human decision. If nothing happened, say nothing. On a direct
   question, answer from the table in five lines.

## Hosts

You run on one machine; a worker may run on another. Read
`tower.py --remote` so its branches on origin and its published reports
(`report.py --sync`) are in the table. Reach it the way that host allows
(a message, an ssh command, a remote session); never assume a worktree
you cannot see is idle — `elsewhere` in the table says what it carries.

## Resources

Concurrency follows the lanes and the load, not the wish list. Mechanical
work (tidy, digest, ports, regression pins) goes to a small model; design
and Tier 3 to the large one. A worker over twice its tier's usual cost is
reported, not fed.
