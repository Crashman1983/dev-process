# Module: arch-docs

Opt-in. Ships a stakeholder-facing architecture overview
(`ARCHITECTURE-OVERVIEW.md`), shaped after arc42 and the C4 model but kept
thin, plus a gate that keeps it honest without pretending its prose is
verified. It is the *narrative* layer of architecture — the part the code and
the ADRs cannot say for themselves.

## When required

Enable when someone who will not read the code needs to understand the system:
onboarding a new team member, a security or architecture review, a stakeholder
conversation. If the only audience is the implementers and the machine-checked
`arch` block plus ADRs already suffice, you do not need this.

## One owner per behavior — what this does NOT duplicate

Architecture lives in three places, one owner each (mandatory rule 4):

- **Structure** — layers, boundaries, interface symbols — is the machine-checked
  `arch` block in `ARCHITECTURE.md` *when the `arch-onboarding` module is
  active* (it ships that file and verifies it against real code; without it,
  name where your structure is defined). The overview's "building blocks"
  section **links** there and adds only a stakeholder gloss; it never restates
  the structure.
- **Decisions** are ADRs under `docs/process/adr/` (`Status` + `Intent` axes).
  The overview's "decisions" section **references** load-bearing ADRs by id; it
  never restates them.
- **Narrative** — context, quality goals, runtime scenarios, deployment, risks,
  glossary — is this overview. It is the only owner of that.

Enable `arch-docs` together with `arch-onboarding` (and ADRs, always present)
for full arc42-style coverage with no duplicated owner.

## The verify tags

Every section of the overview is tagged so no reader mistakes prose for a
verified fact:

- `[verified elsewhere]` — building blocks and decisions; the real source is
  named and linked, not restated. This gate checks that the **ADR** references
  resolve; the building-blocks link points to the structure's owner
  (`ARCHITECTURE.md` when `arch-onboarding` is active), which that module —
  not this gate — verifies against real code.
- `[review-checked]` — context, quality goals, runtime, deployment, risks,
  glossary; prose, not machine-checkable, kept honest by the review gate and its
  `review-checklist.md`.

## What the gate checks (and deliberately does not)

`scripts/process/check_arch_docs.py`:

- **Hard (CI fails):** an `ADR-NNNN` reference in the overview with no matching
  `docs/process/adr/adr-NNNN-*.md` — a dead decision link is silent doc-rot.
  Non-UTF-8 file → hard fail.
- **Soft (advisory note, never blocks):** sections still holding the shipped
  `> _Placeholder…_` marker are listed, so an unfilled overview is visible
  instead of passing as "documented". An absent file is a pre-adoption note.
- **Not checked:** whether the quality goals are the right ones, whether the
  risks are complete, whether the prose is any good — that is judgment, owned by
  the review gate, never grep-able. A green `arch-docs` gate means "references
  resolve and placeholders are visible", not "the architecture is well
  documented".

## The C4 / arc42 mapping

The sections map onto the familiar frameworks so a reader who knows either is
oriented: context & scope = C4 system context / arc42 §3; quality goals =
arc42 §1.2 + §10; building blocks = C4 containers/components / arc42 §5 (owned
by `arch-onboarding`); runtime scenarios = arc42 §6; deployment = arc42 §7;
decisions = arc42 §9 (owned by ADRs); risks & technical debt = arc42 §11;
glossary = arc42 §12.

## Diagrams as code (convention, not gated)

When a section wants a picture, write it as a **fenced Mermaid block in the
markdown itself** — GitHub, GitLab and most doc tools render it natively, and
a text diagram diffs in the PR alongside the change that moved a boundary
(the whole point: a diagram that cannot drift invisibly). Mermaid covers the
C4-style context/container view plus sequence and state diagrams; that is
enough here. Prose remains the primary carrier — a diagram *illustrates* a
section, it never becomes a second owner of structure (the `arch` block and
the ADRs own that). Binary diagram exports (draw.io PNGs, screenshots) are
the anti-pattern this convention replaces: not diffable, not reviewable,
stale on arrival. The gate deliberately does not parse diagrams — placeholder
and ADR-reference honesty stay its whole job.
