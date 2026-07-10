# /review

Run the gate before merging to the main branch. Re-read the kernel
(`docs/process/kernel.md`) and `docs/process/mandatory-rules.md` first — the
review judges the change against those rules, and a long session may have
compacted them out of context. Then read
`docs/process/workflow.md` (Review); depth scales with
`docs/process/risk-tiers.md`. Judge functional completeness, correctness, and
rule adherence against the plan or spec, working through
`docs/process/review-checklist.md` (what a review actually checks —
completeness, correctness, security, design, decisions, product frame, tests).
Fixes loop back through `/execute` and then `/review` again until the branch is
clean.

Record the result in the exact grammar (`journal-state-plans.md`): a
`REVIEW work=… tier=… reviewer=… model=… independence=… verdict=… round=…`
line in the journal (the core `review` gate parses it), and — for a
findings-producing or Tier 3 review — `FINDING sev=… action=… issue=…` lines
in a `.process-work/reviews/` report (gate-linted where the `github-issues`
module is installed; the report grammar either way).

To dispatch a fresh (or cross-model) reviewer, do not hand-craft its input:
`python scripts/process/make_review_bundle.py -o /tmp/bundle.md` assembles the
complete read-only bundle — rules, checklist, product frame, plan, diff, and
the exact output grammar — ready to feed any model
(`docs/process/verification-independence.md`, "The review bundle").
