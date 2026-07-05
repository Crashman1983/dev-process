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
tracking issue is its own). **Soft (advisory note):** an `in-progress` story
without an issue — still active, the issue may be forthcoming (issue-before-code
is enforced on the *plan*, below); and whether the issue exists — a 404 stays a
note, because the gate cannot tell a deleted issue from one the token cannot see.

> **Migration:** enabling this module (or upgrading to it) makes done-without-
> issue hard. An existing registry with legacy `done` stories that lack `issue`
> links will fail on the first run — add the links, or move those stories off
> `done`, before turning the gate on in CI.

## Issue before code

Tier 3+ work is tracked by an issue *before* the code is written. The gate
enforces this at the active plan (`.process-work/plans/`), which already
declares its risk tier (`journal-state-plans.md`):

- **Hard (CI fails):** an active plan declaring `tier: 3` or higher that carries
  neither a valid `issue:` line (same three forms as above) nor an explicit
  `issue-waived: <reason>`. A `tier:` inside a fenced example is a quotation and
  is ignored.
- **Not enforced:** a plan without a `tier:` line (opt-in by declaration), a
  Tier 0–2 plan, or an archived plan — archived (merged) plans are the review
  gate's business, not this one's.

`issue-waived:` is the named, auditable escape for legitimately untracked work
(a throwaway spike, an offline setting). The rule is the mature-adopter
discipline "Tier 3+ needs an issue before any code", made a gate — but only
where the project has chosen to run its backlog on GitHub Issues.

## Templates and the seed helper

Two templates: `.github/ISSUE_TEMPLATE/feature.md` and
`.github/ISSUE_TEMPLATE/bug.md`. Because `gh issue create` ignores
`ISSUE_TEMPLATE/`, seed a body with `scripts/process/new_issue.sh`:

    body="$(bash scripts/process/new_issue.sh feature)"
    gh issue create --title "..." --body-file "$body"

## Example label schema (adapt freely)

A starting point, not enforced by any gate:

- `surface:<area>` — which part of the system
- `priority:{low,med,high}`
- `type:{feature,bug,chore}`
- `status:in-progress` — claimed and being worked

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

## Optional: render story dependencies

A story's `blocked_by` (feature-registry) is the portable source of truth for
sequencing. If you want it visible on GitHub, render it into the issue body as a
`Blocked by #N` line (or use GitHub's native issue relationships). This is a
one-way projection *from* the registry — a convenience, never the source of
truth, and not gated (it needs a write token). The feature-registry module's
`story_order.py` tool prints the ready-to-start order from the same data without
touching GitHub.
