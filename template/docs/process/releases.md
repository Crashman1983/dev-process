# Releases & versioning

How a change that merged becomes a version someone can depend on. Small on
purpose: a solo project needs a predictable ritual, not a release train.

## Semantic versioning

Version `MAJOR.MINOR.PATCH`:

- **MAJOR** — a breaking change: something a consumer depended on (API,
  contract, file format, CLI flag, default) no longer holds. With the
  `contract-first`/`contracts-drift` modules, the changed spec/pin is the
  evidence.
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
