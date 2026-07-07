# /quick

Use the Tier 0/1 shortcut for small, isolated changes without a separate plan
file. This command carries the operative steps — you need not read the whole
`docs/process/workflow.md` or `review-checklist.md` for a quick change (open
them only if a point below is unclear). Before editing: state goal, touched
files, and risk; add a test for Tier 1. Before finishing, take a light pass over
the two checklist questions most likely to bite a small change — untrusted input
reaching a sink, and duplicating an existing behavior instead of changing its
owner. Escalate to `/plan` the moment persistence, auth, contracts, external
integrations, or anything another component depends on come into scope.
