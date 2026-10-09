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
list of its files (a binary shows as path and size), and the output grammar: the `REVIEW` line is
imported from `check_review.py` itself (that half cannot drift from the gate),
the `FINDING` line's owner is the github-issues report gate and its tokens are
pinned to that gate by a template test. Sources it cannot read are named in
place.

Dispatching is harness-plumbing around that artifact — pick what exists:

    python scripts/process/make_review_bundle.py -o /tmp/bundle.md

- **Claude Code:** `claude -p "$(cat /tmp/bundle.md)"` (a fresh process — not
  the implementing session).
- **Codex CLI:** `codex exec "$(cat /tmp/bundle.md)"` — this is the cross-model
  path when the implementer was a Claude, and vice versa. A dispatched Codex
  cell runs read-only and reports only (no channel, no attest.py — the
  steward attests from its output); the end-to-end path with attestation is
  Codex as a tool inside a Claude review.
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
branch again. The delta is a reading aid, at every tier: the bundle's
`REVIEW_ARTIFACT` line still names the whole branch (fork point and head), so
the verdict vouches for all of it. Pair this with batching: one fix pass and one
push per round, never a drip of per-finding commits that each re-pay the
push-time gates and tests.

**What each round judges.** This paragraph owns the rule; `/review` and the
bundle preamble carry it. Round 1 names every blocker, not the first — a
blocker held back is a round. A delta round judges the fix diff and the open
findings, and re-checks the fixed failure class everywhere it can recur, not
only at the fixed spot (downstream, a fifth of the blockers were introduced
by the previous fix). An older defect found outside that is its own issue —
unless it is a BLOCKER for this change; then it goes into the verdict marked
"pre-existing, found in round N". Its `DELTA_TOUCHES` line lists the files
the delta changes. If the fix changed a contract, the architecture or the
risk scope, the reviewer says so and asks for a full bundle instead of
judging the delta. (Until v2.53 a Tier 3 delta needed an anchoring full
round and a containment check of its files; both are gone — the verdict
binds the whole branch either way, and the machinery that judged a delta's
reach was a source of defects of its own.)

**What blocks, and when the rounds stop.** This paragraph owns the rule;
`/review` and the bundle preamble carry it. Block only for a defect someone
would hit — a user, a caller, the merge or an attacker: in code, tests, a
contract, security or the acceptance the plan claims. Wording in the plan, a
report, a tally or the PR text never blocks: record it as a `nit`. A verdict
whose findings are all minor or nit is a `pass` with residuals — no new
round (downstream, a Tier 3 update's second round blocked on two majors that
were plan text only, its code already accepted). **A block is verified
before it counts** (adapted from Claude Code's `code-review` plugin): a
finding that would block names its failure scenario — the input or state,
the path through the changed code, the wrong outcome; a defect whose path
never runs through the change is pre-existing, an issue rather than this
work's block. Before a `block` is attested, a fresh
process that did not write the finding (a cheap model suffices) checks each
such finding against the bundle and scores it: 0 — does not survive a
look; 25 — unverified; 50 — real but minor or rare; 75 — verified, will be
hit; 100 — confirmed by the evidence. Below 80 the finding is a residual or
a follow-up issue, not a block. Never a block: what a linter, type checker
or the test suite catches, a quality wish no rule or criterion asks for, a
change the plan intends. From the second block on
the same element the fix session — a fresh one, on the model the policy
names for the tier's plan phase — decides *increment vs. rebuild the owning
layer* and records it as a `DECISION` before the next round (mandatory rule
4); that is not an owner question. After the third blocking round the owner
decides once — merge with named residuals, cut scope, or rebuild — and the
decision covers the rest of the work: a later round goes back to the owner
only when the decision's premise no longer holds (downstream: one feature,
eight rounds, six owner decisions, and the rebuild came after round four).
A project's `review.local.md` may tighten the cap; it keeps the one decision
per cap, not one per round.

## Bind the verdict to the reviewed range

Independence is incomplete if the branch can change after review without
invalidating the verdict. The bundle therefore names the reviewed range —
the head's fork point from the integration branch and the head:

    REVIEW_ARTIFACT base=<git-sha> head=<git-sha>

`attest.py --bundle` writes both onto the `REVIEW` line — never typed, never
invented. Two commit SHAs name the reviewed change exactly; no digest is
needed (one was recorded until v2.53 — `diff=<sha256>`, a function of base
and head — and older records keep it; it is read and ignored). A full
round's base is the head's one fork point: the bundle does not build, and
`attest.py` does not write, a round against any other base (a slice
recorded as the whole branch) or against a fork point that is ambiguous or
cannot be resolved.

**What counts as reviewed is content, not history.** The gate compares
every file of the pushed tip with one state: git's own merge of the
integration branch (where the tip last met it) with the reviewed head and
with every other clearing review's head the tip carries. A file that equals
it is reviewed, whatever commits led there; a file that conflicted in that
merge never is. So a rebase or a merge of main that applies cleanly keeps
the review, and several reviewed works that git merges cleanly are reviewed
together. A review counts whole where the tip carries its head, where its
base is the fork point, or where its base is itself reviewed content (what
the whole reviews below it merge to, bookkeeping aside); a head that a
rebase replaced needs such a base, and any other review vouches only for
the files its own range changed.
A Spec Kit plan (`specs/<dir>/plan.md`) is no bookkeeping, but what the
attestation commit adds to it is: REFUTE, ROOT-CAUSE, REVIEW and dated
DECISION lines appended, an open `DECISION NEEDED` replaced by a DECISION,
and its move to the archive with no more than that (`attest --with`,
`--archive`; `check_review.records_only`). Any other line added, edited or
deleted is plan content, and a fenced or indented record line is too.
Everything else is unreviewed: code committed after the reviewed head — also
a commit that sets a reviewed file back to main's version — any conflict
resolution, whichever side it takes, and a merge that adds code of its own.
Any git failure is stale: the gate never falls back to a weaker comparison.
The comparison needs git 2.38 or later (`merge-tree --write-tree`).

The gate reads existing records by the same rule. A full round whose head
the push carries unmerged (in the pushed tip's history, in no integration
ref) and whose base is not that head's one fork point is a malformed
`REVIEW` line: it clears no plan, lifts no block and boards no train. Once
a valid full round of the same work with a higher round follows it — its
head descending from the old one — the line is a note, no longer a refusal:
that round reviewed everything from the fork point on (downstream, a delta
line from before v2.53 refused every push of two branches after their merge
of main, whatever round came after). It still clears nothing. A
merged record stands as main judged it; a record whose head is missing or
lies on another branch is not this push's, and those off their fork point
are counted in one note. The range is bounded by the remote-tracking
integration refs that do not contain the tip (local names only when no
remote-tracking one exists): a local main fast-forwarded to the branch hides
nothing, and a tip every remote ref already contains is integrated — a stale
local main reopens nothing. Without any integration ref nothing is judged,
and the gate says so once.

(Lean pass: the former `review-binding: artifact-v1` mode — tree-empty
certificate commits and CI candidate binding — is retired.)

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

A record written by `scripts/process/attest.py` additionally carries `base`
and `head`, the reviewed range from the bundle's `REVIEW_ARTIFACT` line; the
exact grammar is in `journal-state-plans.md`.

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
  local project delta still needs a fresh Tier 2 REVIEW of the update range, and
  the project's own changes to gate code retain Tier 3 (released gate code
  is template provenance like any other file). Failed provenance or a saved report
  cannot grant an exemption (`risk-tiers.md`, `releases.md`).
- **Reviewed range.** A `REVIEW` carrying `base`/`head` names what was
  reviewed: a full round's base must be its head's fork point, and code
  after the head is unreviewed.

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

A delta bundle shows the branch's first-parent commits since the reviewed head,
plus each two-parent merge's remerge-diff (the conflict resolution). It omits
changes merely imported from main. Its `REVIEW_ARTIFACT` still names the whole
branch. Octopus merges or a base outside the first-parent chain need a full
bundle.
