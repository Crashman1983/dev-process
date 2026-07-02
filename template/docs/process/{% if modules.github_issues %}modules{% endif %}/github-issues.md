# Module: github-issues

Opt-in. Runs the backlog on GitHub Issues: EARS-framed templates, a seed
helper, a documented claim workflow, and a gate over the `issue` link on
feature-registry stories.

## When required

Enable when GitHub Issues is the operative backlog. Tracked work (a story at
status `in-progress` or `done`) should carry an `issue` link; the gate emits a
note when it does not.

The gate operates on feature-registry story files: without the
`feature-registry` module (or before the first real story exists) it is
intentionally inert — enable both modules to get enforcement.

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

**Hard (CI fails):** a malformed ref. **Best-effort (advisory note only):**
whether the issue exists — a 404 stays a note, because the gate cannot tell a
deleted issue from one the token cannot see, and cross-repo refs are allowed.

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

1. Comment to claim: agent/branch/scope/next-update.
2. Set `status:in-progress`.
3. Post a heartbeat comment on long-running work.
4. On merge: remove `status:in-progress`, close the issue with the commit ref.
