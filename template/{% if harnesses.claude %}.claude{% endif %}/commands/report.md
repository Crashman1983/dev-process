# /report

Tell the tower where this worker stands — one line, only when the state
changes. Never a running commentary: five or six reports per issue is the
whole budget.

    uv run scripts/process/report.py planned      --issue N --note "plan committed, tier 2"
    uv run scripts/process/report.py pushed       --issue N
    uv run scripts/process/report.py review-pass  --issue N
    uv run scripts/process/report.py blocked      --issue N --note "lane held by full run; waiting"
    uv run scripts/process/report.py done         --issue N
    uv run scripts/process/report.py idle                   --note "ready for the next issue"

Send `planned` when the plan is committed, `pushed` after the phase's work
is committed AND pushed (the script checks origin and refuses otherwise —
push, then report; never `--force` to get past it while origin is reachable),
`review-pass` when the clearing REVIEW is attested, `blocked` the moment
you cannot proceed (with the reason — that line is what unblocks you),
`done` after the merge, `idle` when you have nothing assigned. Reports land
in the clone's git common dir (a `process-tower` folder inside `.git`), shared by
every worktree on this machine and never committed; the tower
(`scripts/process/tower.py`) shows the latest state per worker and marks
a worker stale after an hour without report or commit (`docs/process/tower.md`).
