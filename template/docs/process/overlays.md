# Overlays: project notes on template docs

The template owns its docs and commands; a template update replaces them. A
project that edits one owns a merge conflict on every update, and its edit
silently stops matching when the template changes the rule next to it. An
overlay keeps the project's word apart from the template's and makes the
mismatch visible.

## Where an overlay lives

- a doc `docs/process/<name>.md` → `docs/process/<name>.local.md`
- a module doc `docs/process/modules/<name>.md` → `docs/process/modules/<name>.local.md`
- a command `.claude/commands/<name>.md` (or another harness's) →
  `docs/process/commands/<name>.local.md` — never next to the command, where the
  harness would load it as a command of its own

The template never ships, renders or overwrites a `*.local.*` file. Data
overlays (`model-policy.local.json`, `testing.local.json`, `gates.local.json`)
are laid over their file by the scripts that read them; this page is about the
prose ones.

## What an overlay says

Its head names the template file; each anchor line names a section it builds on:

```
overlay-of: docs/process/testing.md
extends: "## Stages" @new
replaces: "### Lanes" @new

## Our stages
…the project's text…
```

- `extends` — the overlay adds to the section; the section still holds.
- `replaces` — the overlay sets a rule of its own in place of the section's;
  say which rule and why, so a reader of both knows which one binds here (the
  overlay does, in this project).
- `@new` until checked; `python3 scripts/process/check_overlays.py --stamp
  <overlay>` writes the hash of each section as it reads now. Stamp only after
  reading the section and the overlay side by side.

Sessions read the overlay with its file: the session context
(`rehydrate.py`) lists every overlay next to its template file.

## The check: does a central change still fit?

The `overlays` gate (core, always on) re-reads every anchor:

- **section gone** (renamed or removed by the template) → red: a breaking
  change; re-home the anchor to the section that now carries the rule, or
  delete the overlay when the template now covers it.
- **section changed** since the stamp → red: a possible breaking change. Read
  the new section and the overlay: still compatible — re-stamp; contradicted —
  adjust the overlay (or drop a `replaces` the template now makes obsolete),
  then re-stamp; the template got it wrong — raise it upstream.
- **template file gone**, **no anchor**, **unstamped** → red, with the way out.

`template_update.py` runs the same check right after an update and lists the
overlays to re-check, so the update commit carries the re-stamped overlays and
the gate stays green. Honest boundary: the gate sees that anchored text
changed, not whether the change contradicts the overlay — that judgment is the
re-check, by someone who reads both.

## On the template side

A release that changes, renames or removes a section projects anchor to names
it in the CHANGELOG, so an adopter knows before the update which overlays will
need a re-check.
