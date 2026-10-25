---
---

# /review

**Project overlay:** if `docs/process/commands/review.local.md` exists, read it
before you start — the project's own rules for this command, binding over
this file where it says so; a template doc this command sends you to may
have one beside it (`<doc>.local.md`), read with the doc
(`docs/process/overlays.md`).

Run the gate before merging to the main branch. Re-read the kernel
(`docs/process/kernel.md`) and `docs/process/mandatory-rules.md` first — the
review judges the change against those rules, and a long session may have
compacted them out of context. Then read
`docs/process/workflow.md` (Review); depth scales with
`docs/process/risk-tiers.md`. Judge functional completeness, correctness, and
rule adherence against the plan or spec, working through
`docs/process/review-checklist.md` (what a review actually checks —
completeness, correctness, security, design, decisions, product frame, tests).
If `review.local.md` in `docs/process/` exists, read it next: the project's own
review dimensions. They sharpen the checklist and never weaken it.
Fixes loop back through `/execute` and then `/review` again until the branch is
clean.

**Verify every block before you attest it.** Each finding that would block
names its failure scenario (input or state, path through the change, wrong
outcome). Hand each one to a fresh subagent that did not write it — a cheap
model is enough — with the bundle and the scale in
`docs/process/verification-independence.md` ("What blocks"); below 80 the
finding is a residual or a follow-up issue, and a verdict left with none is
a `pass`. The report ends with **Merge danger** in two lines: one-way or
two-way door (can a revert undo it? a migration, deleted data or a published
contract cannot) and the blast radius if it is wrong.

Record the result with the writer, never by hand:

    python scripts/process/attest.py --work <id> --tier <n> --reviewer <id> \
      --model <family> --independence bundle,non-implementing[,cross-model] \
      --verdict pass|block --bundle /tmp/bundle.md \
      --commit --with .process-work/reviews/<report>.md   # [--plan-review]

It takes the reviewed range (base, head) from the bundle, checks that a full
round's base is the head's fork point, validates the grammar and appends the
`REVIEW` line to today's journal shard of the branch (`journal-state-plans.md`).
Every Tier 2+ review writes a `.process-work/reviews/` report — findings as
`FINDING sev=… action=… issue=…` lines, each blocker and major with its `class=`
and its place `at=<path>:<line>` (gate-linted where the `github-issues`
module is installed; the report grammar either way). A `block` verdict always
has findings, so it always writes the report: the next delta bundle reads the
open findings from it. Report
and line are one commit — `attest.py … --commit --with
.process-work/reviews/<report>.md` — and one push.

**One line per acceptance criterion** (Tier 2+ code review): for each
`AC-<n>` of the plan, the test that goes red when that behaviour breaks —
`AC-3: tests/test_x.py::test_refuses_y` — or `AC-3: unproven`. Ask of each
named test: would it fail if the behaviour were deleted, or does it pass on
a stub, a mocked-away call, real state outside its temp dir? A criterion no
test can turn red is a finding (`kind=test-gap`), and `unproven` refuses the
pass. `attest.py` refuses a pass whose report misses a criterion, or names a
test that does not stand at the reviewed head or is skipped there
(`docs/process/verification-independence.md`, "Evidence at the writer", for
this and the other evidence rules: cross-model from the project's tier,
the gate-code refute, the plan's lines before the head).

**Gate code at Tier 2, one run:** where the review runs on a second model
family (`cross-model`) and the range touches gate code, give that reviewer
the refuter's brief (`docs/process/refute.md`) instead of a plain review
prompt; its report carries the `REFUTE work=<id> round=<r>: …` line next to
its findings, and that line counts as the refute. A single-family review of
gate code needs the refute line in the work's plan (`refute_line.py` counts
it from the refuter's `SCENARIO` lines), or `skipped refute
work=<id>: <reason>` there — committed before the bundle, or appended after
the plan's last line and attested with `--with` the plan.

After a clearing pass is attested, `uv run scripts/process/report.py review-pass --issue N` — the branch may now board the merge train (`docs/process/train.md`).

**Push only your own branch, never main.** The review pushes the attest
commit to its branch; the merge belongs to the train or `finish.py`, and the
pre-push hook (`merge_route.py`) refuses a push to main from a review
session — no route marker and no override applies to it
(`docs/process/train.md`, "Who pushes to main").

To dispatch a fresh (or cross-model) reviewer, do not hand-craft its input:
`python scripts/process/make_review_bundle.py -o /tmp/bundle.md` assembles the
complete read-only bundle — rules, checklist, product frame, plan, diff, and
the exact output grammar — ready to feed any model
(`docs/process/verification-independence.md`, "The review bundle"). Inside
the tree, write it as `.process-work/reviews/<slug>.bundle.md` — git ignores
`*.bundle.md` there; anywhere else in the tree it is an untracked file that
`finish.py` reports dirty and the review gate reads as an unhomed plan.

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
  reads the fix diff plus the prior round's findings, while the verdict
  still binds the whole branch, at every tier
  (`docs/process/verification-independence.md`, "What each round judges").
  A delta round over gate or security code needs a reviewer with tools: it
  runs the changed code and its tests, not only reads the bundle. A
  `FIX-PASS WARNING` in the bundle (a fix pass above 300 changed production
  lines — downstream, such passes were followed by a fix-induced blocker
  in two of three next rounds or more) asks the reviewer to attack the
  sibling paths of every change.
- **Rebase or merge main before the first review round.** A later rebase or
  merge of main that applies cleanly keeps the review (the gate judges
  content, not history); one that resolves a conflict is a new round.
- **The round is counted, not claimed.** `attest.py` numbers it: 1 + the
  distinct blocked rounds recorded for the work. Every blocking round gets
  its REVIEW line (`--verdict block`); several reviewers (lenses) of one
  round each attest it with `--round <that round>`; a re-check after a
  pass, a rebase or a short look is no new round. Plan reviews count apart
  (`--plan-review`).
- **Cause before fix.** Before the next round, the fixer writes
  `ROOT-CAUSE work=<id> round=<r>: <cause> — sites: <sites> — <tests>` into
  the journal or the plan — the sibling sites of the cause and the class test
  that failed before the fix, or `sites: none — <reason>` for a block without
  a code defect — and checks it with `attest.py --dry-run`, which refuses a
  pass while a blocked round lacks one (`docs/process/workflow.md`, Execute,
  "Fixing a review round"). The test comes first and fails on the old code. Downstream, the largest source of extra rounds was
  a fix that created the next blocker — the same rule patched three times.
- **Attack before or within round 1, by tier.** Owner check, fail-open, edge cases, evidence —
  at Tier 2 inside the review, a separate refute run where the table asks for one
  (`docs/process/refute.md`: the table by tier, the brief, the `REFUTE` line). Downstream, a
  refute pass found more in two runs than three review rounds had.
- **A second owner blocks.** A rule the change re-implements although existing code owns it,
  proven by a differential test, is a blocking finding at every tier — unless the plan's
  `DECISION` names why the rule has two owners.
- **The plan's decisions first.** Each section of `review-checklist.md`
  opens with what the plan decides; check that the code does what the plan
  decided — a deviation is a finding — then the section's code questions. A
  plan review (`--plan-review`, a `-plan` bundle) reads only those Plan
  halves: is a dimension the change touches left undecided, is a cited
  signature wrong against the code? Its pass (`work=<id>-plan`) clears the
  plan for execute and boards nothing on the train.
- **Short lenses.** Each lens reports in at most ~400 words, worst first, and
  every finding cites the rule, the plan or spec line, or the failure
  scenario it rests on — a finding that cites none is not one.
- **One reviewer set per work.** Round 1 runs the full lens set the tier
  requires (including any full-tool refuter lenses); a delta round re-runs
  the lenses whose prior report has an open finding or names a file in the
  bundle's `DELTA_TOUCHES` line, plus the attesting reviewer — no new
  lenses, no swapped model family. Lens sets stay project-owned. A reviewer that
  becomes unavailable is replaced with a journal note, and its first round
  counts as round 1 for that lens. Downstream, a new reviewer in a later
  round found older defects the first set never looked at, and each became
  a round.
- **Round 1 names every blocker; later rounds judge the fix and its class.**
  A delta round re-checks the fixed failure class everywhere it can recur and
  asks for a full bundle when the fix changed a contract, the architecture or
  the risk scope (`docs/process/verification-independence.md`, "What each
  round judges").
- **The work blocks twice → a fresh session fixes it** and records the
  increment-vs-rebuild call in the plan before the next round as
  `REPLAN work=<id> round=<r>: increment|rebuild — <reason>`, one per blocked
  round after the first; a `rebuild` gets a new plan review before the code
  changes. The implementing session has twice missed what is wrong there; it
  is not the one to try a third time.
- **Only what someone would hit blocks; three blocks reach the owner
  once.** Plan text, report wording and tallies are nits; an all-minor
  verdict is a pass with residuals. After the third blocking round the
  owner decides once for the rest of the work
  (`docs/process/verification-independence.md`, "What blocks, and when the
  rounds stop").
- **Size.** The bundle warns above 30 files / 1,500 lines
  (`PROCESS_REVIEW_MAX_FILES`/`_LINES`). Split before round 1 where the plan
  allows; works of 3,000+ lines ran five to seven rounds downstream.
- **Exceptions are recorded.** Where the owner overrides a rule above,
  `attest.py --exception "<reason>"` writes a `REVIEW-EXCEPTION` line —
  also when no attest rule trips (a round beyond the cap) — countable,
  never silent.

  Example: the second lens of round 2 reports after the fix for that round
  has already landed. It still attests round 2, from the round-2 bundle, and
  says why: `attest.py --work 42 --round 2 --bundle <round-2 bundle> …
  --verdict block --exception "second lens attested after the fix landed"`
  writes `REVIEW-EXCEPTION work=42 round=2: second lens attested after the
  fix landed (overrides: …)` above its `REVIEW` line — the
  overridden rule is named, or "no attest rule tripped".
