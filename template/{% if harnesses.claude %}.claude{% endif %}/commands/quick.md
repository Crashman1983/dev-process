# /quick

Use the Tier 0/1 shortcut for small, isolated changes without a separate plan
file. This command carries the operative steps — you need not read the whole
`docs/process/workflow.md` or `review-checklist.md` for a quick change (open
them only if a point below is unclear). Before editing: state goal, touched
files, and risk; add a test for Tier 1. Before finishing, take the light pass
`workflow.md` (Quick) names — the two checklist questions most likely to bite
a small change. A change a user notices brings its news fragment
(`scripts/process/news.py new`, `docs/process/news.md`). State the change as one observable sentence ("after this,
<user> can …"); if it does not fit one sentence, it is not quick. Name the
terminal state of any data the change writes or transforms. Escalate to
`/plan` the moment persistence, auth, contracts, external integrations, or
anything another component depends on come into scope — and when the fix needs
a choice between valid designs, or the work needs parallel subagents.
