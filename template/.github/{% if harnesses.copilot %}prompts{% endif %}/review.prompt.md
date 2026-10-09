# review

Run the merge gate. Re-read the kernel (`docs/process/kernel.md`) and
`docs/process/mandatory-rules.md` first — the review judges the change against
those rules, and a long session may have compacted them out. Then read
`docs/process/workflow.md` (Review) and
`docs/process/risk-tiers.md`. Check completeness, correctness, and rule
adherence against the plan or spec, working through
`docs/process/review-checklist.md`, plus `review.local.md` in `docs/process/`
where the project has one (it sharpens the checklist, never weakens it); each section's **Plan decides:** line first — does the code do what the plan decided? A plan review (`--plan-review`) reads only those lines. Record the result with the
writer, never by hand: `python scripts/process/attest.py --work <id> --tier <n>
--reviewer <id> --model <family> --independence … --verdict pass|block
--bundle <bundle>` takes the reviewed range (base, head) from the bundle and
appends the `REVIEW` line the core `review` gate parses
(`journal-state-plans.md`). A findings-producing or Tier 3 review also writes
`FINDING sev=… action=… issue=… gate=…` lines in a `.process-work/reviews/`
report; report and line are one commit (`attest.py … --commit --with
<report>`). Block only for a defect someone would
hit — plan or report wording is a nit, an all-minor verdict a pass with
residuals, and each blocking finding names its failure scenario and is
checked by a fresh process before it counts (below 80 of 100, a residual) (`docs/process/verification-independence.md`, "What blocks, and
when the rounds stop"). To dispatch a fresh or cross-model
reviewer, assemble its complete input with
`python scripts/process/make_review_bundle.py -o /tmp/bundle.md`
(`docs/process/verification-independence.md`). Push only your own branch,
never main: the merge belongs to the train or `finish.py`, and the pre-push
hook refuses a push to main from a review session (`docs/process/train.md`).
