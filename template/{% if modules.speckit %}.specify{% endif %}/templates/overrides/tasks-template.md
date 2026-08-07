---

description: "Task list template for feature implementation (dev-process override)"
---
<!-- Derived from GitHub Spec Kit's tasks-template.md (MIT, Copyright GitHub, Inc.) — see THIRD-PARTY-NOTICES.md -->

# Tasks: [FEATURE NAME]

**Input**: Design documents from `/specs/[###-feature-name]/`

**Prerequisites**: plan.md (required), spec.md (required for user stories)

**Tests are MANDATORY**: every user story phase carries the test tasks that
prove its acceptance criteria (mandatory rule 5, `docs/process/testing.md`) —
written first, watched failing, then implemented (the execute flow's TDD
order). A story phase without a test task fails the `speckit` gate.

**Organization**: tasks are grouped by user story so each story is an
independently implementable, testable, deliverable slice — P1 first (MVP).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependencies)
- **[Story]**: which user story this task belongs to (e.g. US1, US2)
- Include exact file paths in descriptions; a task cites the AC-IDs it serves.

## Phase 1: Setup (shared infrastructure — only if genuinely needed)

- [ ] T001 …

## Phase 2: Foundational (blocking prerequisites all stories need)

- [ ] T002 …

## Phase 3: User Story 1 — [title] (P1)

- [ ] T003 [US1] Test: failing test(s) for AC-1 … in tests/…
- [ ] T004 [US1] Implement … in src/…

**Checkpoint**: US1 is independently functional — validate the slice against
its acceptance criteria and Success Criteria before starting US2; where the
telemetry module is installed, record one GRADE line per criterion in the
journal (`docs/process/modules/telemetry.md`). A wrong direction dies here,
at slice cost, not at review after 100% of the work.

## Phase N: User Story N — [title] (PN)

(same shape: test tasks first, then implementation, then the checkpoint)

## Final phase: Polish & cross-cutting concerns

- [ ] T0NN Docs affected by this feature updated (DoD)

## Execution rules

- Mark a task `[X]` in THIS file the moment it completes — the checkboxes
  are the canonical progress state (session re-entry: next task = first
  unchecked box).
- One atomic commit per task (`docs/process/commits.md`).
- Execution runs through the dev-process execute flow — `/speckit-implement`
  is not installed (it would bypass the commit and TDD discipline).
