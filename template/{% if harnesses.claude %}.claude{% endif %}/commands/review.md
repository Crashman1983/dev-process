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

Record the result with the writer, never by hand:

    python scripts/process/attest.py --work <id> --tier <n> --reviewer <id> \
      --model <family> --independence bundle,non-implementing[,cross-model] \
      --verdict pass|block --bundle /tmp/bundle.md   # [--plan-review]

It recomputes the digest from the bundle's base/head with the gate's formula,
refuses a stale bundle, validates the grammar and appends the `REVIEW` line to
today's journal shard of the branch (`journal-state-plans.md`). A typed digest is a
fabricated attestation; the gate names it as such and counts the review as
absent. For a
findings-producing or Tier 3 review — `FINDING sev=… action=… issue=…` lines
in a `.process-work/reviews/` report (gate-linted where the `github-issues`
module is installed; the report grammar either way).

After a clearing pass is attested, `uv run scripts/process/report.py review-pass --issue N` — the branch may now board the merge train (`docs/process/train.md`).

To dispatch a fresh (or cross-model) reviewer, do not hand-craft its input:
`python scripts/process/make_review_bundle.py -o /tmp/bundle.md` assembles the
complete read-only bundle — rules, checklist, product frame, plan, diff, and
the exact output grammar — ready to feed any model
(`docs/process/verification-independence.md`, "The review bundle").

UI stories: the bundle ends with a **UI evidence** section — the story's
before/after pair (DoD D8) and every image the diff touches. Open them. The
verdict on a UI story names whether the AFTER picture matches the intent
(spec, four-state table); "passes the floor" alone is not a pass, and a
missing pair is a finding, not a skip.

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
- **The round is counted, not claimed.** `attest.py` numbers it: 1 + the
  distinct blocked rounds recorded for the work. Every blocking round gets
  its REVIEW line (`--verdict block`); several reviewers (lenses) of one
  round each attest it with `--round <that round>`; a re-check after a
  pass, a rebase or a short look is no new round. Plan reviews count apart
  (`--plan-review`).
- **Cause before fix.** Before the next round, the fixer writes
  `ROOT-CAUSE work=<id> round=<r>: <cause> — <the test that failed before
  the fix>` into the journal or the plan; `attest.py` refuses the next round
  without it. The test comes first and fails on the old code. Downstream,
  the largest source of extra rounds was a fix that created the next
  blocker — the same rule patched three times.
- **One reviewer set per work.** Round 1 runs the full set the tier
  requires (including any full-tool refuter lenses); later rounds use the
  same set — no new lenses, no swapped model family. A reviewer that
  becomes unavailable is replaced with a journal note, and its first round
  counts as round 1 for that lens. Downstream, a new reviewer in a later
  round found older defects the first set never looked at, and each became
  a round.
- **Later rounds judge the fix, not the whole branch again.** A round ≥2
  checks the fix diff and its surroundings (callers, tests, the rule it
  touches). An older defect found outside that is its own issue — unless it
  is a BLOCKER for this change; then it goes into the verdict marked
  "pre-existing, found in round N".
- **The same spot blocks twice → a fresh session fixes it.** The
  implementing session has twice missed what is wrong there; it is not the
  one to try a third time.
- **Size.** The bundle warns above 30 files / 1,500 lines
  (`PROCESS_REVIEW_MAX_FILES`/`_LINES`). Split before round 1 where the plan
  allows; works of 3,000+ lines ran five to seven rounds downstream.
- **Exceptions are recorded.** Where the owner overrides a rule above,
  `attest.py --exception "<reason>"` writes a `REVIEW-EXCEPTION` line —
  also when no attest rule trips (a round beyond the cap) — countable,
  never silent.
