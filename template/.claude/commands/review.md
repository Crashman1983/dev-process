# /review

Run the gate before merging to the main branch. Read
`docs/process/workflow.md` (Review); depth scales with
`docs/process/risk-tiers.md`. Judge functional completeness, correctness, and
rule adherence against the plan or spec, working through
`docs/process/review-checklist.md` (what a review actually checks —
completeness, correctness, security, design, decisions, product frame, tests).
Fixes loop back through `/execute` and then `/review` again until the branch is
clean.

Record the result in the exact grammar the gates read (`journal-state-plans.md`):
a `REVIEW work=… tier=… reviewer=… model=… independence=… verdict=… round=…`
line in the journal, and — for a findings-producing or Tier 3 review —
`FINDING sev=… action=… issue=…` lines in a `.process-work/reviews/` report. A
dispatched fresh reviewer must be told to emit these verbatim, not free-form
prose, or the gate cannot read them.
