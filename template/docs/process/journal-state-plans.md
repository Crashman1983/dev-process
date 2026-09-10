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
tracked issue (via the `github-issues` module's `new_issue.py`, when installed)
or is deliberately dropped. A triaged issue gets the
**normal form** — the bug/finding templates with EARS acceptance criteria, an
`Origin` naming the item being worked when it surfaced, and a comment on that
origin issue so the trail runs both ways (module doc, "Discovered work keeps
the form and the trail"). This is discipline, not a gate — "did you capture
everything you noticed" is not mechanically decidable, so nothing checks it;
the value is that scope stays clean and nothing is silently lost.

## Plans

`.process-work/plans/YYYY-MM-DD-<feature>.md` holds the current implementation plan
(from the plan phase). Archived to `.process-work/plans/archive/` on merge. Designs
from the brainstorm phase live beside plans as `design-<topic>.md` — scaffold and
section prompts in `docs/process/design-template.md`.

An in-progress design may carry `[NEEDS CLARIFICATION: …]` markers for its open
questions (`design-template.md`); a **plan** may not — a plan is built from an
approved, clarification-free design. The core `clarification` gate enforces
exactly that line: a marker in an active plan is a hard failure, markers in an
active design are a visible note, and archived files are history.

**Plans have exactly one home.** Every presence guarantee downstream (review
attestation, archive ritual, issue-before-code) keys on `.process-work/plans/`
— a plan written anywhere else silently escapes all of them. This matters with
topic-triggered third-party skills (brainstorming/planning assistants with
their own file conventions): a skill may help *inside* a phase, but the
artifact lands in the plan home (or `specs/` on the Spec Kit path), nowhere
else. The `review` gate enforces the loud half of this: a `tier: 2+`
declaration outside the sanctioned homes is a hard failure.

**Decisions made in dialogue live in the plan, not in the conversation.**
Every plan (and every `specs/<feature>/plan.md`) carries a `## Decisions`
section — the ledger of choices the owner or the agent made while working,
one line each, written *before the next step starts*, never at the end:

```
## Decisions
- DECISION 2026-09-10 owner: variant B (single table), not A — because the
  export path stays one owner
- DECISION 2026-09-10 agent: skip the CSV export in this slice — because the
  owner deferred it to the follow-up issue
```

A conversation is the one artifact a compaction summarizes, and the
sentence carrying a decision is the first to go; the plan is re-read at
every re-hydration (`process_context.py` prints the ledger for `/prime`,
`/execute` and `/review`, and the kernel's compaction directive names it).
A Tier 2+ plan without the section gets a note from the review gate: the
gate cannot know a decision is missing, but a reviewer who sees an empty
ledger asks.

A plan carries one machine-readable line, `tier: N`, recording the derived risk
tier (`risk-tiers.md`). It is the single tier source the `review` gate keys on:
once the plan is archived (i.e. the work merged), a declared `tier: 2` or higher
must have a clearing review attestation (below) or a named `review-waived:`
exception. An **active** plan (and a `specs/<feature>/plan.md`) without a
`tier:` line is a hard failure of the review gate: every tier-keyed duty
keys on that line, so omitting it switched them all off silently — off by
omission was the escape (observed downstream: two plans without the line
were invisible to every gate until it was added, and two duties armed at
once). Archived plans without the line are a note: history is not
re-litigated.

**Tier 3 is anchored to the push, not the archive.** Waiting for the archive
step means the proof arrives after the merge it was meant to gate. So for an
*active* `tier: 3` plan **this push carries** — its file is in the pushed
range, or a pushed commit claims its issue (a closing trailer such as
`closes #N`, or a `… (#N)` subject; a bare mention claims nothing) — the
review gate demands the clearing pass **on the push to main/master** and
reports the same finding as a note on every other push. The gate learns where
a push lands from the environment: the pre-commit framework's
`PRE_COMMIT_REMOTE_BRANCH`, or `PROCESS_PUSH_TARGETS` exported by a custom
hook from git's stdin. Somebody else's Tier 3 plan sitting in the tree is not
this push's proof to produce. Known limitation: a pull request merged
server-side never pushes main from a clone, so this arm never fires on that
route — there `finish.py` (run before the PR is opened) is the stop, and the
archive arm catches the residue on main.

Digest binding is opt-in per REVIEW line (below), not per plan — the former
`review-binding: artifact-v1` plan field is retired; the gate reports a
leftover as a note.

With the `speckit` module on, an active Tier 2+ plan also either references
its `specs/NNN-…` directory or carries a `spec-waived: <reason>` line — the
spec interrogation comes before planning, and skipping it is a recorded
decision, never a silent one (the `speckit` gate enforces this).

A waiver is an honest degradation — and a degradation without an owner
becomes the new normal. `review-waived:` and `spec-waived:` lines should name
their debt owner on the line itself (an issue ref `#N` or a URL); the gates
report a waiver without one as a note, never a failure.

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

## Review reports

`.process-work/reviews/YYYY-MM-DD-<slug>.md` holds the full record of a
findings-producing review or audit — the prompt, the verdict, and one
structured `FINDING` line per finding — beside the one-line `REVIEW`
attestation below, which stays the journal's record. A UI story's
**before/after evidence pair** lives beside it in
`.process-work/reviews/<slug>/` (DoD D8): screenshots per viewport, theme
and state, which the review bundle lists and the owner digest points at. Format, publication to
GitHub Issues, and the gate binding are in the `github-issues` module doc;
without that module the reports are simply working memory.

## Review attestations

The `review` gate reads `REVIEW` lines from the journal — one per review, the
structured record of how independent the review actually was (see
`verification-independence.md`). Fields, space-separated `key=value` in any
order, values without spaces:

```
REVIEW work=42 tier=2 reviewer=fresh-agent model=same independence=bundle,non-implementing verdict=pass round=1
```

A REVIEW may bind itself to the exact reviewed diff by carrying the three
integrity fields. **Write the line with `scripts/process/attest.py`**
(`--bundle <bundle file>` or `--base/--head`): it recomputes the digest with
the gate's own formula, refuses a stale bundle, validates the grammar and
appends to today's shard. Never type a digest. The gate names a digest that
matches no formula for its base/head as what it is — a fabricated
attestation — and counts the review as absent (observed on one deployment:
15 of 16 recorded digests were never computed, and the gate said so on every
run until nobody read it). The digest formula is pinned against git config
(`check_review.CANONICAL_DIFF`), so a value computed on one clone verifies
on every other:

```
REVIEW work=42 tier=2 reviewer=fresh-agent model=same independence=bundle,non-implementing verdict=pass round=1 base=<git-sha> head=<git-sha> diff=<sha256>
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
| `base` | optional: merge-base commit the bundle diffed from |
| `head` | optional: reviewed branch head |
| `diff` | optional: SHA-256 of the raw `git diff --binary base...head` bytes — the gate recomputes and verifies it |

A `REVIEW` inside a ```-fenced block is a quotation and is ignored (quote
literal examples only there). Grammar and the independence arithmetic the gate
enforces on a `pass` are in `verification-independence.md`.

A record carries none of `base`/`head`/`diff`, or all three; partial
artifact metadata is malformed.

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

**What is *not* gate-protected across parallel efforts — know these.** The
sharding above prevents file conflicts; it does not prevent semantic collisions
on shared single-source-of-truth artifacts. These serialize only through
ordinary git merge + the ff-only re-gate, and a gate catches each only *after*
both efforts land:
- **Story-ID space.** Two efforts can both claim `STORY-0042` off the same base;
  the duplicate-id check fails at the *second* merge, forcing a manual renumber.
  Reserve ids up front, or let the second effort renumber on rebase.
- **`PRODUCT.md` coherence.** Git auto-merges edits to different lines, so one
  effort adding a Goal and another adding a contradicting Non-goal merge clean
  with no gate noticing the incoherence — only the review's product-frame
  questions can. Coordinate frame edits, or review the merged frame.
- **Campaign parent issues.** Two agents publishing a report near-simultaneously
  both see "no parent yet" and each create one (`publish_review.sh` is
  best-effort, network, not race-safe); the offline gate flags the split only
  after both reports coexist. Create the campaign parent first, then publish.

## Retention — growth is unbounded by design

Nothing here expires automatically: journals, archived plans, review reports
and branch state files accumulate, and the gates stay fast well past a
thousand files — history is cheap, and `trace.py` is the reader. When the
volume itself starts to bother you (searching, cloning), prune by age as an
ordinary change: delete or move journal shards and archived plans older than
what you still reference, in a commit that says so. `scripts/process/compact_journal.py`
does the routine form of it: shards older than N weeks (default 8) are folded
into a monthly `journal/archive/YYYY-MM.md` that keeps exactly the machine-read
records (`REVIEW`, `GRADE`) verbatim — the gates and `trace.py` glob the archive
like any shard — and drops the prose, which git still holds. Dry run by
default, `--apply` writes. Two things should NOT be
pruned casually: review reports (the audit trail the review gate's waivers
point at) and the decision records (which are not working memory at all).

Residue accrues where removal depends on remembering, so the pruning has
one owner: `scripts/process/tidy.py` reports every kind of residue with the
command that removes it — merged remote branches, finished spec
directories, old archived plans, old journal shards (folded, records kept),
a leftover template-delta directory — and `--apply` executes the safe part.
Active plans past the window and quiet open issues are only listed: they
are the owner's call. The weekly digest carries the same report, so the
numbers are seen before they are felt.
