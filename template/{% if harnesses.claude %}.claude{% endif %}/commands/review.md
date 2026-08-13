---
model: opus
---

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

Mechanics before judgment — the model reviewer is the most expensive
detector you have, so it goes last: before building the bundle, run every
*mechanical* check the plan, spec, or contracts name (ownership/layering
detectors, grep-able invariants, token/schema checks — the gate suite
already runs as the bundle's preflight) and fix or file what they find.
Append their results to the bundle: the reviewer then *verifies* the
mechanical layer and spends its judgment on what only judgment can find. A
finding a grep could have made costs cents mechanically and a review round
otherwise.

Round economy — a failed round must not re-pay the whole chain:

- **Batch, don't drip.** Collect ALL must-fix findings of a round, fix them in
  one pass, push once — every extra head commit re-pays the push-time test
  suite for nothing.
- **Round 2+ reviews the delta.** Rebuild with
  `make_review_bundle.py --since <head the last round reviewed>`: the reviewer
  reads the fix diff plus the prior round's findings, while the bundle still
  binds the full-branch digest (Tier 3 gets a full bundle every round — the
  tool refuses delta-only there).
- **Rebase once**, before the first review round — every later rebase changes
  the tree and voids the bundle digests, forcing a fresh full round.
