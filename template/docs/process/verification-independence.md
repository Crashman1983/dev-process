# Verification Independence

A check is worth only as much as its context is independent of the work it
checks. An agent that grades or reviews its own output, in the same context
that produced it, inherits that context's framing and blind spots — it tends to
confirm rather than catch. Preventing that is the whole reason a review gate
exists, so the gate's value is bounded by how independent it actually is.

The process spends independence like a budget: production runs warm,
verification runs independent, and the degree of independence scales with the
tier.

## Production runs warm

Brainstorm, plan, and execute are production. They live on coherence — the plan
follows from the design, the code from the plan. Running them in one continuous
context is correct and efficient; forcing a fresh session between them discards
that coherence and pays a re-priming cost for nothing. Do not manufacture
independence here.

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
  alternative to `cross-model`. Add adversarial verification:
  independent reviewers try to *refute* the change rather than confirm it, and
  a majority refutation blocks the merge.

## The review bundle — the portable interface to any reviewer

The read-only bundle is the seam that makes independence *and* model diversity
practical: one self-contained markdown document that is the reviewer's complete
input. `scripts/process/make_review_bundle.py` assembles it — reviewer preamble,
the kernel block, the review checklist, the product frame, the active plan(s),
the diff against a base ref, and the output grammar: the `REVIEW` line is
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

## Bind the verdict to the reviewed artifact

Independence is incomplete if the branch can change after review without
invalidating the verdict. A Tier 2+ plan can opt into exact artifact binding
with this machine-readable line:

    review-binding: artifact-v1

For a bound review, perform the final rebase before review, finalize and
archive the plan, and only then build the bundle. The bundle prints one
fingerprint over the raw binary diff from the resolved merge base to the
reviewed head:

    REVIEW_ARTIFACT base=<git-sha> head=<git-sha> diff=<sha256>

The clearing `REVIEW` record repeats those three fields. It must be recorded in
a **tree-empty certificate commit** whose sole parent is the reviewed head and
whose tree is identical to that parent. The commit body is the durable review
certificate; an optional copy in the journal is useful to humans but does not
clear an `artifact-v1` plan. This avoids changing the reviewed tree merely to
record that it was reviewed.

On a protected-target push or pull request, the gate recomputes the exact
candidate diff and requires the certificate digest to match it. Any content
change after review — including a rebase that changes the reviewed diff —
invalidates the certificate and requires a fresh bundle and review. A bound
integration slice may carry only one newly archived bound plan, keeping the
certificate-to-change relationship unambiguous.

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

For `review-binding: artifact-v1`, the same record is placed in the certificate
commit body and additionally carries `base`, `head`, and `diff`; the exact
grammar is in `journal-state-plans.md`.

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
- **Presence.** A plan is archived on merge; an **archived** plan that declares
  `tier: N` with N ≥ 2 must carry a clearing `verdict=pass` `REVIEW` (matching
  `work`, `tier ≥ N`) or an explicit `review-waived: <reason>` line. So a
  Tier 2+ change cannot merge with no independent review — or it merges as a
  named, auditable exception.
- **Artifact identity.** For a plan declaring `review-binding: artifact-v1`, a
  journal attestation alone is insufficient. The clearing record must live in
  the tree-empty certificate commit and its base, head, and raw binary-diff
  digest must match both the commit relationship and the protected integration
  candidate.

What the gate **cannot** do is verify the reviewer was *truthfully* a different
agent or model — it never sees the review runtime. That claim stays attested.
The gate makes a weak, absent, or over-claiming attestation *block the merge*
instead of being weighed by a human; it does not pretend to check identity.
Presence keys on archived plans (not in-flight ones), so it never reds CI
mid-development, and the `review-waived:` escape keeps honest single-agent
setups unblocked.

## Why this is efficient, not just safe

Independence costs tokens and wall-clock, so the process buys it only where it
pays: at verification, scaled by risk. Production stays warm and fast; the
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
