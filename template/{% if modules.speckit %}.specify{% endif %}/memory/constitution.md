# Constitution — pointer, not a second truth

<!-- DEV-PROCESS-CONSTITUTION-POINTER -->

This project's principles are NOT authored here. The single source of truth
is the dev-process methodology, and this file only points at it so every
`/speckit-*` phase reads the same rules the gates enforce:

- **Binding rules:** `docs/process/mandatory-rules.md` (the nine rules) and
  the always-on kernel in `docs/process/kernel.md`.
- **Risk routing:** `docs/process/risk-tiers.md` — scope, not diff size,
  sets the tier; the tier decides how much cycle a change runs.
- **Product direction:** `PRODUCT.md` — goals, non-goals, constraints; a
  spec that serves no stated goal or violates a non-goal changes the frame
  in the same effort or does not proceed.
- **Quality bars:** `docs/process/testing.md` (tests prove acceptance —
  test tasks are NEVER optional), `docs/process/review-checklist.md`,
  `docs/process/definition-of-ready-and-done.md`.

Do NOT run `/speckit-constitution` — it would replace this pointer with
generated principles and create a second truth beside the gated one. The
`speckit` gate fails if this pointer marker disappears.
