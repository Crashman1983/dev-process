# Weekly improvement session

A brief for whoever runs the week's improvement pass: the steward, or a
session it starts. Any harness can run it (Claude Code, Codex, another); it
needs the repository, `uv` and, for `outcomes`, `gh`. The contract behind it
is `optimization.md`; this page says what to do in one sitting.

**Your freedom.** Diagnose, propose and design freely: a gate to weaken or
add, an order to change, a model per phase, a product signal instead of a
process change. Nothing here asks for a statistical study. **Your limits.**
You weaken nothing yourself (every weakening is the owner's line), you set
no guardrail and no protected gate, and new executable checks come in
through normal code review.

## Inputs

Read, do not change:

- `uv run scripts/process/process_kpis.py losses` — occupancy, delay, owner
  effort and tokens, each against its own past.
- `uv run scripts/process/process_kpis.py nodes` — each gate's cost against
  its blocks; flips; triage so far.
- `uv run scripts/process/process_kpis.py outcomes` — epics to usable,
  disruptive bugs to fixed, bug-origin coverage (needs `gh`).
- `uv run scripts/process/process_kpis.py flow`, `rounds`, `clusters` where a
  number needs its issues behind it.
- `uv run scripts/process/gate_modes.py status` and `optimize.py status` —
  what is weakened, locked or on trial.
- `uv run scripts/process/process_kpis.py rounds` — blockers by `kind`,
  plan review and code review apart: a growing `knowledge-gap` share in code
  review means facts exist that plans do not reach (`inventories.md`).
- Last week's report (`.process-work/improvement/`), for its prognosis.

Not installed (telemetry module off, no `gh`) is a finding, not a zero:
say what you could not see.

## Steps

0. **Run the sentinel** (`uv run scripts/process/gate_modes.py sentinel`).
   A restore it writes is committed and merged first; it is the one step
   that makes things stricter on its own.
1. **Check last week's prognosis.** What did the chosen action promise, what
   happened? One line, honest, including "not measurable yet".
2. **Triage a few gate blocks.** Pick 3–5 untriaged blocks from `nodes`
   (prefer gates that cost much). For each, read the run and the commits
   after it, and append a line to `.process-work/gate-triage.jsonl`:
   `confirmed-defect`, `accepted-risk`, `infra-or-flake` or `unknown`, with
   the failure class and the fix. A later fix commit proves nothing on its
   own; when unsure, write `unknown`.
3. **Look for blind spots.** Read a handful of this week's new issues,
   commits and journal lines. A recurring piece of free text that carries a
   dimension no field holds ("follow-up of #N", "after the deploy of #N",
   "review residuals") becomes a provisional question, with the evidence and
   the decision that needs the answer. "No new question" is a valid result.
   A low bug-origin coverage in `outcomes` is a blind spot already named:
   say where the labels get lost.
4. **Rank one action.** Weigh what the numbers show against what an action
   would cost to build, run and maintain. Choose **one**:
   - a graph change proposal (weaken, add, reorder a node) — weakening goes
     to the owner as a proposal with its triage evidence;
   - an improvement record (`optimize.py new …`) for a mechanism;
   - a product signal (an issue for delivery work) when value suffers and no
     process loss explains it — missing data means "unknown", then the
     action is to close the gap;
   - nothing, when nothing pays back within about four weeks.
5. **Write the report** (below) and commit it with the triage lines.
6. **Render the news** (`git fetch`, then `uv run scripts/process/news.py render`, where the
   project keeps `news/` fragments) and let `NEWS.md` ride the same branch
   and merge as the report (`news.md`).

## Report

`.process-work/improvement/YYYY-Www.md` (ISO week), in the project's
working language:

```
# Improvement YYYY-Www
- Ran by: <harness>/<model family> · role: steward | session for the steward
- Last prognosis: <what it said> → <what happened | not measurable yet>
- Seen: losses <one line> · nodes <one line> · outcomes <one line> · not visible: <…>
- Triage: <n> blocks (<gate>: <category>, …)
- Blind spots: <question + evidence + who needs it | none>
- Action: <the one action> · cost: <agent h / owner min> · prognosis: <what should change, by when>
- For the owner: <decisions only the owner can take, with evidence | none>
```

Stop after the report. One action a week that holds beats five that
interfere.
