# Design: arch-docs module (SP15)

**Date:** 2026-07-03
**Status:** approved (scope: the stakeholder-facing architecture-documentation
gap — the template verifies structure and records decisions, but has no home
for context, quality goals, runtime/deployment views, or a risk register; an
arc42/C4-lite scaffold closes it without betraying the "prose rots, verify
against code" ethos)
**Slice:** a new opt-in `arch_docs` module: a thin arc42/C4-shaped overview
whose verifiable parts point at what already checks them, whose prose parts are
honestly tagged unverified, and a minimal gate that catches only the
mechanical rot (dead decision links, hidden placeholders).

## Gap

`arch-onboarding` verifies *structure* (layers, dependency rules, interface
symbols against real code) and ADRs record *decisions*. Neither gives a
stakeholder-facing narrative: system context, quality goals + scenarios,
runtime views, deployment, a risk/technical-debt register, a glossary — the
arc42 sections a team needs to explain the system to someone who will not read
the code. The template deliberately avoids prose that rots, so the answer is
not "ship arc42's twelve prose sections" — it is a thin scaffold that hooks
reality where it can and is honest where it cannot.

## Decision 1 — a scaffold that complements, never duplicates

`ARCHITECTURE-OVERVIEW.md` (root, stakeholder-discoverable) ships arc42/C4-lite
sections, each with a one-line "what goes here", a placeholder marker, and a
**verifiability tag**:

- **Context & scope**, **quality goals + scenarios**, **runtime scenarios**,
  **deployment**, **risks & technical debt**, **glossary** — prose, tagged
  `review-checked` (kept honest by the review gate, not machine-checked).
- **Building blocks** → points to the `arch` block in `ARCHITECTURE.md`
  (`arch-onboarding`); **decisions** → points to `docs/process/adr/`. These are
  *not restated* here — one owner per behavior (mandatory rule 4). The overview
  links to them.

A legend at the top explains the tags so no reader mistakes prose for verified.

## Decision 2 — a minimal gate that never fakes verification

`check_arch_docs.py` does only what is genuinely mechanical, so a green gate
never implies the prose is good:

- **Hard fail:** an `ADR-NNNN` reference in the overview that does not resolve
  to a `docs/process/adr/adr-NNNN-*.md` file — a dead decision link is silent
  doc-rot, exactly the class the template exists to catch. Non-UTF-8 → hard
  fail.
- **Soft note:** sections still carrying the placeholder marker — "N sections
  still placeholder; overview not fully onboarded". Never blocks (documentation
  takes time), but the emptiness is visible instead of passing as "documented".
- **Soft note:** file absent (a project deleted it) — pre-adoption, not a
  failure.
- Pure stdlib; no PyYAML (it reads markdown, not the manifest).

The gate deliberately does **not** check that quality goals are good or risks
complete — that is judgment, caught by the review gate and its
`review-checklist.md`, never grepped.

## Decision 3 — honest integration, not a fourth architecture surface

The module doc states the split plainly: **structure** = `arch-onboarding`,
**decisions** = ADRs, **narrative** = this overview. Enabling all three (plus
ADRs, always present) yields full arc42 coverage with one owner per part. A
`risks & technical debt` entry may reference an ADR whose `Intent: tolerated`
records accepted debt — the register points at the decision, it does not copy
it.

## Out of scope

Verifying prose quality (not grep-able — the review gate's job); C4 diagram
rendering (a project's tooling choice; the scaffold names the C4 levels but
ships no diagram generator); auto-syncing the overview's building-block section
from the arch block (they are linked by reference, not generated — generation
would be a second owner of the same structure).
