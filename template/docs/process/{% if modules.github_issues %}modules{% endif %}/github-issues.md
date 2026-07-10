# Module: github-issues

Opt-in. Runs the backlog on GitHub Issues: EARS-framed templates, a seed
helper, a documented claim workflow, and a gate over the `issue` link on
feature-registry stories.

## When required

Enable when GitHub Issues is the operative backlog. Tracked work (a story at
status `in-progress` or `done`) should carry an `issue` link; the gate emits a
note when it does not.

The gate has two independent parts. The **story** part operates on
feature-registry story files: without the `feature-registry` module (or before
the first real story exists) it is inert. The **issue-before-code** part
operates on active plans and runs whenever this module is on, independent of
the feature registry (see below).

## Prerequisites (optional)

- A GitHub repository. Set it at setup via the `github_repo` answer
  (`OWNER/REPO`) — optional; leave blank to skip existence checks.
- The `gh` CLI, authenticated (`gh auth login`). Absent → existence checks are
  skipped with a note; format is still enforced.

## The `issue` field

A story's `issue` field (illustrative story path
`docs/process/feature-registry/STORY-NNNN.json`) accepts three forms:

- bare `#412` — resolves against the configured `github_repo`
- cross-repo `owner/repo#412`
- URL `https://github.com/owner/repo/issues/412`

**Hard (CI fails):** a malformed ref; **a `done` story with no `issue` link at
all** — a finished story must trace to an issue (this applies to *every* done
story, epic or leaf: an epic's children can cover its tests, but the epic's own
tracking issue is its own). **Tracker-less escape:** a done story may instead
carry an `issue_waived: <reason>` string field (soft note, not hard) — for a
project running this module without a reachable issue tracker, so `done` is not
permanently unreachable. **Soft (advisory note):** an `in-progress` story
without an issue — still active, the issue may be forthcoming (issue-before-code
is enforced on the *plan*, below); and whether the issue exists — a 404 stays a
note, because the gate cannot tell a deleted issue from one the token cannot see.

> **Migration:** enabling this module (or upgrading to it) makes done-without-
> issue hard. An existing registry with legacy `done` stories that lack `issue`
> links will fail on the first run — add the links, or move those stories off
> `done`, before turning the gate on in CI.

## Issue before code

Tier 2+ work is tracked by an issue *before* the code is written. The gate
enforces this at the active plan (`.process-work/plans/`), which already
declares its risk tier (`journal-state-plans.md`):

- **Hard (CI fails):** an active plan declaring `tier: 2` or higher that carries
  neither a valid `issue:` line (same three forms as above) nor an explicit
  `issue-waived: <reason>`. A `tier:` inside a fenced example is a quotation and
  is ignored.
- **Not enforced:** a plan without a `tier:` line (opt-in by declaration), a
  Tier 0–1 plan, or an archived plan — archived (merged) plans are the review
  gate's business, not this one's.

`issue-waived:` is the named, auditable escape for legitimately untracked work
(a throwaway spike, an offline setting). The rule is the mature-adopter
discipline "Tier 2+ needs an issue before any code", made a gate — but only
where the project has chosen to run its backlog on GitHub Issues.

## Templates and the seed helper

Three templates: `.github/ISSUE_TEMPLATE/feature.md`,
`.github/ISSUE_TEMPLATE/bug.md` and `.github/ISSUE_TEMPLATE/finding.md` (a
review/audit finding that needs work — see the report binding below). Because
`gh issue create` ignores `ISSUE_TEMPLATE/`, seed a body with
`scripts/process/new_issue.sh`:

    body="$(bash scripts/process/new_issue.sh feature)"
    gh issue create --title "..." --body-file "$body"

## Example label schema (adapt freely)

A starting point, not enforced by any gate:

- `surface:<area>` — which part of the system
- `priority:{low,med,high}`
- `type:{feature,bug,chore,finding}` (the finding template sets `type:finding`)
- `status:in-progress` — claimed and being worked. `who_is_working.py` also
  treats `status:{review,handoff,blocked}` as active if you use finer states.

## Claim workflow

Convention, not gated — a CI gate cannot see cross-repo comments or wall-clock
cadence, so this is discipline the agents keep, not a check. Keeping it is what
makes a shared backlog legible when several efforts run at once.

1. Comment to claim, naming: **agent · branch/worktree · scope · next-update
   time**. One claimant per issue at a time.
2. Set `status:in-progress`.
3. Post a heartbeat comment on long-running work (a cadence the team agrees —
   e.g. every ~90 min of active work), so a stalled claim is visible.
4. On merge: remove `status:in-progress`, close the issue with the commit ref.

## Coordination views (read-only)

Two read-only tools surface, on the command line, what the offline gates and the
issue labels only show separately — neither edits anything, and a missing or
unauthenticated `gh` degrades to a note rather than an error:

- `scripts/process/who_is_working.py` — a concurrent-activity preflight before
  claiming: active claims (with branch and staleness), open PRs, remote work
  branches with no PR, and local worktrees. Read it *before* starting so two
  efforts do not collide on one issue.
- `scripts/process/attention.py` — where a human should look and steer:
  under-granular acceptance (tests far outnumber criteria), done-without-issue,
  active claims and PRs, and **issue hygiene** — open issues that are not
  gradeable (missing a `type:` label, or, unless an epic, missing an EARS
  acceptance section). That last is the pattern review findings and follow-ups
  fall into when filed outside the story flow: a finding or follow-up that needs
  work is a typed issue (`type:bug`/`chore`/`feature`/`finding`) with EARS acceptance, the
  same gradeable discipline as a story; a purely informational record is exempt.
  Advisory only as a view — a triage hint, this tool never gates. (With the
  `github-master` module installed, the same two conditions DO fail the gate
  hard once a story is in-progress — `definition-of-ready-and-done.md`.)

## Optional: render story dependencies

A story's `blocked_by` (feature-registry) is the portable source of truth for
sequencing. If you want it visible on GitHub, render it into the issue body as a
`Blocked by #N` line (or use GitHub's native issue relationships). This is a
one-way projection *from* the registry — a convenience, never the source of
truth, and not gated (it needs a write token). The feature-registry module's
`story_order.py` tool prints the ready-to-start order from the same data without
touching GitHub.

## Review and audit visibility

Independent reviews and audits produce the process's most valuable negative
knowledge — findings — and that knowledge belongs where the team works: in
issues, not in chat history. Three pieces:

**The report file** — `.process-work/reviews/YYYY-MM-DD-<slug>.md`, beside the
plans. Machine-readable header plus free sections:

~~~
review: sp31-product-frame        (or: audit: qa-persona)
work: #42
campaign: 2026-07-round-1         (optional — bundles reports of one campaign)
issue: #57                        (once published; or: publish-waived: <reason>)
campaign-issue: #50               (required when campaign: is set and published)

## Prompt      — the verbatim prompt the reviewer/auditor ran with
## Result      — verdict and summary
## Findings
FINDING sev=major action=fix issue=- placeholder scan missed the intro
FINDING sev=minor action=follow-up issue=#61 story refs resolve by filename
~~~

`FINDING sev=<blocker|major|minor|nit> action=<fix|accept|follow-up>
issue=<ref|-> <title>` — `fix` was resolved within the reviewed change,
`accept` is a conscious acceptance (reason in prose), `follow-up` becomes
tracked work and **must** carry an issue ref. Fenced examples are quotations
and are ignored, as everywhere — **fence the Prompt section** when it quotes
the grammar or header-like lines (`issue:`, `campaign:`), or the gate lints
the quotes as claims. A title may contain `=` (`USER_ID=1 hardcoded` is fine);
only leading `sev=`/`action=`/`issue=` tokens are parsed as fields.

**The publish tool** — `bash scripts/process/publish_review.sh <report.md>
[--campaign <title>]` creates the issue with the full report as body (prompt,
result, findings — full visibility); with a campaign it creates or reuses the
campaign parent issue and links the report to it (natively as a sub-issue
where the installed `gh` supports it, else as a body reference). Best-effort,
network, never a gate. Write the printed refs back into the report and commit.

**The gate binding (offline, hard):** a report with neither an `issue:` ref
nor a named `publish-waived:` reason fails — an unpublished review is
invisible review. A `follow-up` finding without an issue fails — a follow-up
nobody tracks will be forgotten (the parity gap→issue rule, applied to
findings). Reports sharing a `campaign:` must agree on the `campaign-issue:`
parent. A `blocker` finding that is merely `accept`ed is a visible note. The
gate reads files, not GitHub: whether the issue body still matches the report
stays attested, like every truthfulness claim.

## Discovered work keeps the form and the trail

A follow-up from a finding, or a bug discovered while working on something
else, is **normal work and gets the normal form** — filed through the
templates (`new_issue.sh finding` / `new_issue.sh bug`), with a user story
where one applies and gradeable EARS acceptance criteria. A prose dump titled
"fix stuff from review" is not a tracked follow-up.

Both templates carry an **Origin** section: the report or issue that surfaced
the item (`Discovered during: #N`). When an origin issue exists, **comment on
it** referencing the new issue, so the trail runs both ways — from the origin
to the follow-up and back. Like the claim workflow, the linking and the
comment are convention, not gated (a CI gate cannot see issue bodies or
comments); the *templates* provide the form, and the report gate already
enforces that a `follow-up` finding carries *some* issue ref.
