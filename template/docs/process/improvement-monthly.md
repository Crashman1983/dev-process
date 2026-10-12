# Monthly improvement review

A brief for a fresh session, once a month: it advises, it decides nothing.
Any harness can run it (Claude Code, Codex, another). It must not be the
session that ran the weekly passes it judges, and it starts without their
conversation — it reads the reports, the records and the numbers.

**Independence, the minimum:** you did not implement what you judge; you
read evidence at an exact revision without changing it; you run the checks
yourself where they can be run. Record your harness and model family in
the report. Where the project's tier rules ask for a reviewer of another
model family and one is available, the framework proposals below go to it
before the owner; where none is available, say so.

## What you review

1. **The graph as a whole.** `process_kpis.py nodes --days 90`,
   `gate_modes.py status`: which gates carry the catches, which cost without
   catching, which flip. Are weakened gates still justified by their triage?
   Does a locked gate wait for a triage nobody does?
2. **The decisions of the month.** Each weekly report's prognosis against
   what happened. A pattern of hits, misses or "not measurable" says more
   than one week.
3. **The signals.** Do `losses`, `nodes` and `outcomes` still measure what
   matters here? Coverage, missing values, numbers that could be moved
   without anything getting better (reclassifying, splitting issues,
   skipping triage). Has the model, the harness or the project phase
   changed so that an adopted measure no longer fits?
4. **The guardrails and the protected gates** (`guardrails` in the mandate).
   Too loose to catch a loss, too tight to let anything improve, a class of
   failure no guardrail watches?
5. **The loops themselves.** Did the weekly pass produce decisions that held,
   at a cost below what they saved? A loop that only produces reports is a
   cost.

## What you produce

`.process-work/improvement/YYYY-MM-review.md`:

```
# Improvement review YYYY-MM
- Ran by: <harness>/<model family> · independent of: <the weekly sessions>
- Graph: <what carries, what costs, what to look at>
- Decisions: <n> weekly actions · held <n> · missed <n> · not measurable <n>
- Signals: <still fit | what drifted and why>
- Proposals to the owner: <guardrail / protected gate / budget / signal change, each with evidence and the expected effect | none>
- Second opinion: <reviewer family and verdict | not available>
```

Proposals change nothing until the owner decides. Changing a guardrail, the
protected gates, the budget or what a signal means is the owner's line in
the mandate, never yours.
