# /report

Tell the tower where this worker stands — one line, only when the state
changes. Never a running commentary: five or six reports per issue is the
whole budget.

    uv run scripts/process/report.py planned      --issue N --model <id> --note "plan committed, tier 2"
    uv run scripts/process/report.py pushed       --issue N --model <id>
    uv run scripts/process/report.py review-pass  --issue N --model <id>
    uv run scripts/process/report.py blocked      --issue N --model <id> --note "lane held by full run; waiting"
    uv run scripts/process/report.py idle                   --model <id> --note "ready for the next issue"

`--model` is your own model id, verbatim (a dispatched session has it in
`PROCESS_MODEL`); without either the report records `not measured`.
Send `planned` when the plan is committed, `pushed` after the phase's work
is committed AND pushed (the script checks origin and refuses otherwise —
push, then report; never `--force` to get past it while origin is reachable),
`review-pass` when the clearing REVIEW is attested, `blocked` the moment
you cannot proceed (with the reason — that line is what unblocks you),
`idle` when you have nothing assigned. `done` is written for you after the
merge — by `finish.py --apply` (with the issue's token line) or the train;
without either, `report.py done --issue N --model <id>`. Reports land
in the clone's git common dir (a `process-tower` folder inside `.git`), shared by
every worktree on this machine and never committed; the tower
(`scripts/process/tower.py`) shows the latest state per worker and marks
a worker stale after an hour without report or commit (`docs/process/tower.md`).
