---
name: Verification change
about: A new gate, lint, test technique or review rule — named by what it replaces and how its effect is measured
labels: type:process
---

## Defect class

<The class of defect this catches — not a single case. Where did it show up
(review findings, escaped defects, `process_kpis.py findings`)?>

## Check

<The check: a rule in a declarative file, a property, a mutation run, fault
injection at an owner seam, a contract test. One check per class, not one test
per case (`docs/process/testing.md`, classes not cases).>

## Replaces

<What goes away with it — tests deleted, review checklist items or refute scope
dropped, a warn-only text removed. A check that replaces nothing only adds cost.>

## Measure

<Which baseline numbers should move, and which must not
(`process_kpis.py baseline --window … --window …`): tokens per work, fix rounds,
findings per work, lead time; escaped defects as the guard.>

## Acceptance criteria (EARS)

- When <trigger>, the <check> shall <response>.
