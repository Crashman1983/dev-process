# /review

Run the gate before merging to the main branch. Read
`docs/process/workflow.md` (Review); depth scales with
`docs/process/risk-tiers.md`. Judge functional completeness, correctness, and
rule adherence against the plan or spec, working through
`docs/process/review-checklist.md` (what a review actually checks —
completeness, correctness, security, design, decisions, tests). Fixes loop back
through `/execute` and then `/review` again until the branch is clean.
