# review

Run the merge gate. Re-read the kernel (`docs/process/kernel.md`) and
`docs/process/mandatory-rules.md` first — the review judges the change against
those rules, and a long session may have compacted them out. Then read
`docs/process/workflow.md` (Review) and
`docs/process/risk-tiers.md`. Check completeness, correctness, and rule
adherence against the plan or spec, working through
`docs/process/review-checklist.md`. To dispatch a fresh or cross-model
reviewer, assemble its complete input with
`python scripts/process/make_review_bundle.py -o /tmp/bundle.md`
(`docs/process/verification-independence.md`).
