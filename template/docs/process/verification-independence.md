# Verification Independence

A check is worth only as much as its context is independent of the work it
checks. An agent that grades or reviews its own output, in the same context
that produced it, inherits that context's framing and blind spots — it tends to
confirm rather than catch. Preventing that is the whole reason a review gate
exists, so the gate's value is bounded by how independent it actually is.

The process spends independence like a budget: production needs none,
verification runs independent, and the degree of independence scales with the
tier.

## Production needs no independence

Brainstorm, plan, and execute are production. They live on coherence — the plan
follows from the design, the code from the plan. Independence is not
manufactured here, but where the coherence lives depends on who drives:

- **An interactive session** that plans may continue into execute in the
  same session — warm, no re-priming. This is the one place "warm" applies.
- **The dispatch chain** (`dispatch.py chain`, `tower.md`) hands plan →
  execute over in a fresh session: the committed plan with its `##
  Decisions` ledger is the hand-over artifact, so a plan the next session
  cannot execute without the conversation is an incomplete plan.

Review is never warm, whoever drives (below). This section owns the
statement; the workflow and tier docs point here.

## Verification runs independent

Grading and review are verification. Their entire job is to see what production
could not, so independence is not overhead — it is the property that makes the
check mean anything. Scale it to the tier (`risk-tiers.md`):

- **Tier 0–1** — an in-context self-check is enough; the change is small and
  self-contained enough that a blind spot is cheap. Tier 1's Quick flow reviews
  its own work (a light pass over the checklist), it does not dispatch a fresh
  reviewer — the tier that first requires independence is Tier 2.
- **Tier 2** — a fresh, independent process reviews from a read-only bundle
  (the diff plus the plan and the rules), not from the producing context. The
  implementing agent does not certify its own work. A single model is
  acceptable.
- **Tier 3** — independence should cross the model family **where a second
  family is available**: two families' blind spots are uncorrelated, and a
  same-family check, however fresh its context, can still miss what its family
  systematically misses. Where only one family is available, do not fake it —
  declare the `single-family` limitation in the attestation (below); the
  recorded flag is the honest degradation the process uses for every other
  environment-dependent gate, and the gate accepts it as the explicit
  alternative to `cross-model`. Add adversarial verification (`refute.md`)
  and, where configured, a second-opinion review: independent reviewers try
  to *refute* the change rather than confirm it, and a majority refutation
  blocks the merge.

## The review bundle — the portable interface to any reviewer

The read-only bundle is the seam that makes independence *and* model diversity
practical: one self-contained markdown document that is the reviewer's complete
input. `scripts/process/make_review_bundle.py` assembles it — reviewer preamble,
the kernel block, the review checklist, the product frame, the plan(s) under
review — the plans the branch touches, active or archived (`--plan <slug>`
names them instead, archive included) — the diff against a base ref with the
list of its files (a binary shows as path and size; the digest still covers
its bytes), and the output grammar: the `REVIEW` line is
imported from `check_review.py` itself (that half cannot drift from the gate),
the `FINDING` line's owner is the github-issues report gate and its tokens are
pinned to that gate by a template test. Sources it cannot read are named in
place.

Dispatching is harness-plumbing around that artifact — pick what exists:

    python scripts/process/make_review_bundle.py -o /tmp/bundle.md

- **Claude Code:** `claude -p "$(cat /tmp/bundle.md)"` (a fresh process — not
  the implementing session).
- **Codex CLI:** `codex exec "$(cat /tmp/bundle.md)"` — this is the cross-model
  path when the implementer was a Claude, and vice versa.
- **Any chat model:** paste the bundle as the whole prompt.

The reviewer's independence flags follow from the dispatch, not from wishful
attestation: a fresh process over the bundle is `bundle,non-implementing`; add
`cross-model` only when the reviewing family really differs, else declare
`single-family` (the honest degradation above).

**Delta rounds.** After a failed round, `--since <head the last round
reviewed>` builds a bundle whose diff is only the fixes since that head, plus
the prior round's report from `.process-work/reviews/` (the newest one of
this work: a header `work:` equal to one of its issues — same repository — or
plan slugs; without a `work:` header, a file name or `review:` value naming
it as a whole word; issues first; never another item's) and the full-branch
stat — the reviewer re-reads what changed and what it was told, not the whole
branch again. The full-branch digest fields stay in the bundle, so the
attestation still binds the verdict to the complete artifact. Tier 3 is the
exception: the tool refuses a delta-only bundle there — the highest tier
re-reads in full every round. A delta needs a declared tier: a plan's, or
`--tier N` for a branch without one (a floor, never a discount — the bundle
names where the tier came from). Pair this with batching: one fix pass and one
push per round, never a drip of per-finding commits that each re-pay the
push-time gates and tests.

**What each round judges.** This paragraph owns the rule; `/review` and the
bundle preamble carry it. Round 1 names every blocker, not the first — a
blocker held back is a round. A delta round judges the fix diff and the open
findings, and re-checks the fixed failure class everywhere it can recur, not
only at the fixed spot (downstream, a fifth of the blockers were introduced
by the previous fix). An older defect found outside that is its own issue —
unless it is a BLOCKER for this change; then it goes into the verdict marked
"pre-existing, found in round N". If the fix changed a contract, the
architecture or the risk scope, the reviewer says so and asks for a full
bundle instead of judging the delta.

## Bind the verdict to the reviewed artifact

Independence is incomplete if the branch can change after review without
invalidating the verdict. The bundle therefore prints one fingerprint over
the raw binary diff from the resolved merge base to the reviewed head:

    REVIEW_ARTIFACT base=<git-sha> head=<git-sha> diff=<sha256>

`attest.py --bundle` writes those three fields onto the `REVIEW` line,
recomputing the digest itself — never typed, never invented. The gate then
recomputes the digest from git and hard-fails a mismatch or an unresolvable commit: the verdict is bound to the exact diff
that was reviewed. Perform the final rebase *before* the review — a rebase
after it changes the diff, and the recorded digest honestly stops matching
the merged content; loop back to a fresh bundle and review instead.

(Lean pass: the former `review-binding: artifact-v1` mode — tree-empty
certificate commits and CI candidate binding — is retired; the per-line
digest keeps the diff-exact guarantee without the ritual.)

## Independence is attested, not assumed

The one step that is supposed to be independent is easy to run in the wrong
context by accident. So the review records how it ran — bundle-only, by a
non-implementing process, and (at Tier 3) cross-model — as part of its result.
A `pass` that cannot make those claims does not clear the tier — the gate
blocks it. This makes the independence claim explicit and reviewable rather
than assumed.

The record is a structured `REVIEW` line in the journal, one per review:

```
REVIEW work=42 tier=2 reviewer=fresh-agent model=same independence=bundle,non-implementing verdict=pass round=1
```

A digest-bound record additionally carries `base`, `head`, and `diff` (written
by `scripts/process/attest.py`, which recomputes the digest from base/head with
the gate's own formula — a digest typed by hand, or
from the bundle's `REVIEW_ARTIFACT` line); the exact grammar is in
`journal-state-plans.md`.

`independence` is a comma set drawn from `bundle,non-implementing,cross-model,
single-family`; `single-family` is the explicit honesty flag for "only one
model family was available — I did not fake cross-model". Grammar and fields
are documented with the other working-memory records in
`journal-state-plans.md`.

The `REVIEW` line is the attestation; it is deliberately one line. Tier 3
reviews and audit campaigns additionally write a **report file**
(`.process-work/reviews/`) carrying the full record — the prompt the reviewer
ran with, the verdict, and each finding with its disposition; a Tier 2 report
is encouraged where findings are worth tracking. When the `github-issues`
module is on, reports are published as issues (campaigns bundled under a
parent) and the gate binds them: unpublished-without-waiver and untracked
follow-up findings fail (see the module doc).

## Enforcement

The `review` gate (`scripts/process/check_review.py`, core and always-on)
enforces what a language-agnostic gate honestly can, and no more:

- **Arithmetic.** A `verdict=pass` may not claim to clear a tier its flags do
  not support: a self-review (`non-implementing` absent) or a warm review
  (`bundle` absent) cannot clear Tier 2+, and a Tier 3 pass must carry
  `cross-model` or the explicit `single-family` acknowledgment. This is the
  independence expectation above, turned from prose into a check.
- **Presence.** Archived plans declaring `tier: N` with N ≥ 2 need a clearing
  `verdict=pass` `REVIEW` matching their work and tier, or an explicit
  `review-waived: <reason>` line. The gate also checks active Tier 2+ plans
  touched by the pushed range and plans whose issues its commits claim:
  review is due before the integration push, not only after archival. Missing
  review is a hard failure on an integration push and a note on other branch
  pushes; archived-plan failures remain hard. An active Tier 3 plan whose
  issue is already claimed on the integration branch also fails without a
  clearing review or waiver.
- **Verified template updates.** A plan marked `template-update: true` may
  replace a new REVIEW with computed provenance only for a pure,
  owner/steward-acknowledged update. Both pinned releases are re-rendered;
  local project delta still needs a fresh, digest-bound Tier 2 REVIEW, and
  enforcement migrations retain Tier 3. Failed provenance or a saved report
  cannot grant an exemption (`risk-tiers.md`, `releases.md`).
- **Artifact identity.** A `REVIEW` carrying `base`/`head`/`diff` is verified:
  the gate recomputes the raw binary-diff digest from git and fails a mismatch
  or unresolvable commits — a claimed digest that cannot be checked is treated
  as false, never skipped.

What the gate **cannot** do is verify the reviewer was *truthfully* a different
agent or model — it never sees the review runtime. That claim stays attested.
The gate makes a weak, absent, or over-claiming attestation *block the merge*
instead of being weighed by a human; it does not pretend to check identity.
The gate also checks review coverage for later changes and standing block
verdicts in the pushed range. The `review-waived:` escape records an explicit,
auditable exception; it does not prove independent review.

## Sampling audit — the human reviews by exception

The human owner does not out-review the model reviewers, and should not try:
their comparative advantage is intent, product taste, and the running
surface, not diff-reading. The owner's standing verification duty is a
**sampling audit**: one merged work item per week, chosen *deterministically*
(the owner digest picks it by ISO week — no re-rolling until a convenient
one comes up), read deep and post-merge from the full bundle. The point is
not to catch what the gates missed on that one item — it is that no agent
ever knows which item will be drawn, and that the owner's trust in the gates
stays calibrated by contact instead of by dashboard. Findings route through
the normal channel (issues, FINDING grammar); a sampling audit that keeps
finding real defects is the signal to tighten the gates, not to sample more.

## Why this is efficient, not just safe

Independence costs tokens and wall-clock, so the process buys it only where it
pays: at verification, scaled by risk. Production stays fast; the
expensive fresh, cross-model, adversarial pass fires only at the tier where an
escaped defect is most expensive. The saving is real where a team currently
re-primes between production steps or runs several correlated checks; for a
lean setup it is mostly a reallocation — the same budget spent where it catches
more.

One distinction matters here: an in-context self-grade is fine as an
*advisory* signal for measurement (it costs little and its trace is useful),
but it must not be *trusted as the gate* — read as assurance, a self-grade in
the producing context is the worst of both, a model call that returns false
comfort. Prefer one trustworthy independent check over several correlated ones.

**Refute before review.** How hard a change is attacked before and during its review scales
with the tier — `refute.md` owns the table and the brief; the edge cases that broke downstream
are in `docs/process/failure-catalog.md`.

### Delta after an integration merge

A delta bundle uses the branch's first-parent commits since the reviewed head,
plus each two-parent merge's remerge-diff (the conflict resolution). It omits
changes merely imported from main. Its `REVIEW_ARTIFACT` and attestation carry
`mode=delta`; the writer and gate recompute the same reduced digest. Tier 3
still requires a full bundle. Octopus merges or a base outside the first-parent
chain require a full review. Delta records do not pool coverage for other work,
because their reduced diff did not review every commit on the imported side.
