# Releases & versioning

How a change that merged becomes a version someone can depend on. Small on
purpose: a solo project needs a predictable ritual, not a release train.

## Semantic versioning

Version `MAJOR.MINOR.PATCH`:

- **MAJOR** — a breaking change: something a consumer depended on (API,
  contract, file format, CLI flag, default) no longer holds.
- **MINOR** — new behavior, nothing existing breaks.
- **PATCH** — a fix or internal change, observable behavior otherwise equal.

Before `1.0.0` the contract is explicitly unstable — by convention here,
breaking changes land in MINOR; say so in the README. Cutting `1.0.0` *is* the promise of
stability, so make it deliberately, not by drift.

## The changelog

One `CHANGELOG.md`, newest first, written for the *consumer*, not the
committer: what changed for them, what breaks, what they must do. The
Conventional-Commit types (`commits.md`) make the raw material greppable
(`feat:` → Added, `fix:` → Fixed, breaking notes → the migration section),
but a changelog entry is curated prose, not a commit dump.

## The release ritual

One commit, then one tag — in this order, so the tag points at a state whose
files already claim that version:

1. Bump the version in its single source (the manifest your stack uses —
   `pyproject.toml`, `package.json`, …) and write the `CHANGELOG.md` entry
   in the same commit (`chore: release vX.Y.Z`).
2. Merge through the normal gate path — a release commit is not a bypass.
3. Tag the commit that lands on the main branch `vX.Y.Z` and push the tag. Where the platform builds
   releases from tags (GitHub Releases, package publish), that automation
   hangs off this tag — never off a branch tip.

Two invariants: the version named in the tag, the manifest and the changelog
**agree** (a drifted trio is the release equivalent of a false green), and
tags are **immutable** — a bad release gets a new PATCH, never a moved tag.

## What this is not

No release branches, no train, no cadence promise — merge when green, release
when there is something worth depending on. If the project later needs
parallel maintained majors, that is a process decision worth a decision
record, not an accident.

## Updating the process template

1. Fetch the integration branch and record its SHA before updating. Keep
   that baseline through the update, review and acknowledgment.
2. Run `uv run scripts/process/template_update.py --ref <release>` on a clean
   branch. Resolve conflicts and port owned-file deltas deliberately.
3. Run `uv run --script scripts/process/template_verify.py --base <baseline-sha>`.
   Include its computed file listing and `release_notes` in the update PR.
   The two pinned renders identify template provenance; no saved report
   can exempt a file from review. Verification needs Copier and Git access
   to the recorded template source; unavailable provenance fails closed.
4. Read those behavior notes and acknowledge them with the same command plus
   `--ack <owner-or-steward>`. Commit the generated acknowledgment under
   `.process-work/`, along with the update. Its baseline and resolved release
   SHA must match the verifier's result.
5. Apply the template-update tier rules in `risk-tiers.md`: pure updates need
   gates and project tests, project deltas need one Tier 2 review, enforcement
   migrations retain Tier 3. Use `template-update: true` on the update's plan.
   Archive it before merging; finish and the merge train use the same proof.

Verification also catches a release-pin bump that leaves a changed template
file at the old version. Template deletions qualify only when the old project
file matched the old render; deleting a project test always needs review.
