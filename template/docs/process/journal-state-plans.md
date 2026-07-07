# Journal, State & Plans

Working memory lives under a repo-local `.process-work/` directory. Git records *what*
changed; these files record *why* and *what is in flight*.

## Journal

The journal captures the reasoning behind decisions — root-cause findings, why an
approach was chosen over alternatives, non-obvious constraints. Write it as decisions
are made, not at the end. Convert relative dates ("yesterday") to absolute ones.

**Path — shard it per branch when efforts run in parallel.** A single
`.process-work/journal/YYYY-MM-DD.md` is fine for solo, single-effort work; but a
shared daily file is the one piece of working memory that two parallel efforts both
append to, so they conflict on merge. When more than one effort is in flight, write to
`.process-work/journal/<branch-slug>/YYYY-MM-DD.md` — per-branch, exactly as state and
plans are already sharded, so parallel efforts never touch the same file. The
cross-project daily view is recovered by globbing the shards; tooling that reads
journals does so recursively.

Journal duty scales with the tier: entries are expected from Tier 1 upward, or
whenever a non-obvious decision was made. Tier 0 changes need none — the
commit message carries them.

## Branch-scoped state

`.process-work/state/<branch-slug>.md` is per-branch working memory: active work,
open risks, the next concrete action. It is the primary signal when restoring context
after a break. One file per branch. Wherever other efforts' state files are visible
(shared checkout, worktrees, or after a merge), treat them as read-only.

## Discovered work (inbox)

Work you spot mid-flow — a bug noticed while building something else, a missing
test, a follow-up — is **captured, not scope-crept into the current change**.
One line per item in `.process-work/inbox.md`; keep the current change focused on
its own scope. Triage the inbox when you surface for air: each item becomes a
tracked issue (via the `github-issues` module's `new_issue.sh`, when installed)
or a registry story, or is deliberately dropped. This is discipline,
not a gate — "did you capture everything you noticed" is not mechanically
decidable, so nothing checks it; the value is that scope stays clean and nothing
is silently lost.

## Plans

`.process-work/plans/YYYY-MM-DD-<feature>.md` holds the current implementation plan
(from the plan phase). Archived to `.process-work/plans/archive/` on merge. Designs
from the brainstorm phase live beside plans as `design-<topic>.md`.

A plan carries one machine-readable line, `tier: N`, recording the derived risk
tier (`risk-tiers.md`). It is the single tier source the `review` gate keys on:
once the plan is archived (i.e. the work merged), a declared `tier: 2` or higher
must have a clearing review attestation (below) or a named `review-waived:`
exception. A plan without a `tier:` line is simply not presence-enforced — the
field is opt-in, and its absence is a note, never a failure.

A plan may also carry an `issue: <ref>` line linking its tracking issue (`#N`,
`owner/repo#N`, or a URL). When the `github-issues` module is installed, an
*active* Tier 2+ plan must carry that link before code — issue-before-code — or
a named `issue-waived:` exception; the review gate also uses `issue:` to match a
review attestation to its plan.

A Tier 2+ plan also names its **decision context**: which decision records
(`docs/process/adr/`) it read as constraints, and any new or superseded record
the change entails — or states that none apply. It likewise names the
**product goal** (`PRODUCT.md`) the change serves, or that it is
product-neutral. Both are prose duties judged at the review
(`review-checklist.md`, Decisions and Product frame), deliberately not gated
fields: a machine could only check that *some* text is present, which invites
a ritual "none" — the substance is exactly what the reviewer's questions probe.

## Review attestations

The `review` gate reads `REVIEW` lines from the journal — one per review, the
structured record of how independent the review actually was (see
`verification-independence.md`). Fields, space-separated `key=value` in any
order, values without spaces:

```
REVIEW work=42 tier=2 reviewer=fresh-agent model=same independence=bundle,non-implementing verdict=pass round=1
```

| field | meaning |
|---|---|
| `work` | attribution: the issue number, or the archived plan's slug it reviews |
| `tier` | the reviewed change's tier (0–3) |
| `reviewer` | an id for the reviewing process (presence gated; truthfulness attested) |
| `model` | reviewing model-family slug, or `same` if the producer's family |
| `independence` | comma set ⊆ `bundle,non-implementing,cross-model,single-family` |
| `verdict` | `pass` \| `block` |
| `round` | 1, 2, … |

A `REVIEW` inside a ```-fenced block is a quotation and is ignored (quote
literal examples only there). Grammar and the independence arithmetic the gate
enforces on a `pass` are in `verification-independence.md`.

## Parallel efforts

The process runs several efforts at once cleanly, and the split between what is
parallel and what is serialized is deliberate:

- **Execution is parallel and contention-free.** One feature branch or worktree per
  effort (the isolation invariant in `commits.md`), and all working memory is sharded
  per effort — state per branch, plans per feature, journal per branch. Two efforts in
  flight never write the same file, so nothing conflicts *while they run*.
- **Integration is serialized, by design.** Merging is fast-forward-only
  (fetch → rebase → gate → merge → push), one branch at a time. When another effort
  merges first, rebase onto the moved main and re-run the gates before merging. That
  rebase-and-re-gate is the friction — and it is the price of a linear history in which
  **every merge passed the gates against the actual latest main, not merely in
  isolation**. It is not a defect to remove; it is the guarantee.
- **Never two efforts on one owner.** Two efforts on the same behavior must declare
  *phase-of* or *supersede* (mandatory rule 4), never race — that is the one kind of
  parallelism the process forbids, because it produces conflicting accretion no merge
  can reconcile.
