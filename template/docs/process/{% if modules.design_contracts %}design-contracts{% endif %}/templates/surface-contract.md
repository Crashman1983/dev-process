# <Surface> design contract

**Status:** draft | accepted — the norm for every presentation change on this surface
**Issue:** #NNNN
**Decision:** ADR-NNNN (the record that made this contract normative)
**Scope:** <exactly which surface, form factors, platforms — and what is excluded>
**Reference size:** <the viewport / device the boards are rendered at>
**Registry:** `docs/process/design-contracts/<surface>.json` (pin, reference boards, review)

Every normative element carries a stable ID. IDs are never renumbered or
reused; a retired element keeps its ID with a `retired:` line. Plans, commits,
tests and snapshots cite these IDs (DoR R5, DoD D8).

## 0. Precedence

When two norms disagree, the higher one wins and the lower one is corrected
in the same piece of work:

1. the functional contract (API / capability / behaviour spec)
2. this design contract
3. the sealed reference boards named in the registry
4. the render kit's stylesheet and renderer
5. fine-tuning during implementation — every deviation recorded in §10

## 1. Idea and non-goals

- What this surface is for, in one paragraph.
- Non-goals: what this contract deliberately does not cover.

## 2. Information architecture and screens (S*)

| ID | Screen | Purpose | Reference board |
| -- | ------ | ------- | --------------- |
| S01 | … | … | `<reference>/boards/S01-….png` |

## 3. Visual foundation

### 3.1 Token roles
Which token owns which role (surface, text, accent, state). Raw literals in
surface code are forbidden; the token owner file is `<path>`.

### 3.2 Typography
Scale, roles, minimum sizes, how the largest accessibility size (AX*) reflows.

### 3.3 Grid, radii, elevation (E*)

| ID | Level | Use | Value |
| -- | ----- | --- | ----- |
| E0 | content | no shadow | — |
| E1 | docked | … | … |
| E2 | floating | … | … |
| E3 | overlay | … | … |

### 3.4 Material and motion tokens
Durations, curves, reduced-motion behaviour (a shared motion doc where one exists).

## 4. Recurring components — binding briefs (C*)

One brief per shared component. A brief is the smallest complete answer to
"what does an implementer need to build this without asking":

### C01 <Component name>
- **Purpose / where used:** S01, S03
- **Anatomy:** parts, order, spacing
- **Geometry:** sizes, minimum hit area (≥ 24 × 24 CSS px; ≥ 44 pt on touch)
- **States:** default, hover/pressed, focused, disabled, loading, empty, error
- **Tokens:** which roles from §3.1
- **Accessibility:** name, role, focus order, AX* reflow
- **Provenance:** (operator, date, issue) for every value that was decided, not derived

## 5. Surface rules

Layout rules that hold across screens: chrome budget, width cascade,
safe areas, the four states (loading / empty / error / unknown) and that *not
yet resolved* is never shown as *empty*.

## 6. Motion and accessibility (AX*)

| ID | Rule |
| -- | ---- |
| AX1 | contrast floors: text 4.5:1, glyph 3:1, focus ring 3:1 |
| AX2 | every control has an accessible name; nothing interactive is covered |
| AX3 | layout at the largest accessibility text size: what reflows, what truncates |

## 7. Implementation and acceptance contract

The checklist an implementing agent works through, in order:

1. Before code: read this contract and the reference boards; confirm the
   route / data / action owner; record the UI reuse map (DoR R5) and the IDs
   this change implements or amends (also R5) in the plan.
2. Tokens first: new values enter the token owner, never a view.
3. Shared components before screens: a C* brief becomes one shared
   presentation unit with its states; screens compose it.
4. For every S*/C* touched: behaviour tests, snapshot in both themes and at
   AX3, before/after evidence pair (DoD D8).
5. Review asks explicitly: does the AFTER picture match the reference board
   for that ID? Is every deviation recorded in §10 with provenance?

## 8. Acceptance matrix (machine-readable)

The normative implementation manifest. `implemented: true` requires the
named test, fixture and versioned baseline to exist; until then the case is
planned, never passed.

```json
{
  "cases": [
    {"id": "S01", "test": "<test id>", "fixture": "<fixture>", "baseline": "<path>", "implemented": false}
  ]
}
```

## 9. Decisions

Open questions for the owner, numbered D1…, each with the options, the
recommendation, and — once taken — the decision, date and consequence.

## 10. Amendments

Append-only. An amendment is written **before** the code that relies on it:

| Date | IDs | Change | Provenance (who, issue) | Re-pinned |
| ---- | --- | ------ | ----------------------- | --------- |
