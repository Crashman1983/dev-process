---

description: "Task list template for feature implementation (dev-process override)"
---
<!-- Derived from GitHub Spec Kit's tasks-template.md (MIT, Copyright GitHub, Inc.) — see THIRD-PARTY-NOTICES.md -->

# Tasks: [FEATURE NAME]

**Input**: Design documents from `/specs/[###-feature-name]/`

**Prerequisites**: plan.md (required), spec.md (required for user stories)

**Tests are MANDATORY**: every user story phase carries the tests that
prove its acceptance criteria (mandatory rule 5, `docs/process/testing.md`).
**One task = one behaviour, test AND implementation** (the `/plan` rule):
inside the same task, write the test, watch it fail (red), implement, watch
it pass (green), then tick the box — never a "write tests" task followed by
an "implement" task. Each behaviour task names its test file. A story phase
with no task that references a test fails the `speckit` gate.

**Organization**: tasks are grouped by user story so each story is an
independently implementable, testable, deliverable slice — P1 first (MVP).

## Format: `[ID] [P?] [Story] [class?] Description`

- **[P]**: can run in parallel — disjoint files and a fixed shared contract,
  no shared resource (see `/plan`)
- **[Story]**: which user story this task belongs to (e.g. US1, US2)
- **[class]**: `[mechanical]` or `[design]`; omitted is standard — picks the
  model (`docs/process/tower.md`, "Model by task class")
- Include exact file paths in descriptions; a task cites the AC-IDs it serves.

## Phase 1: Setup (shared infrastructure — only if genuinely needed)

- [ ] T001 …

## Phase 2: Foundational (blocking prerequisites all stories need)

- [ ] T002 …

## Phase 3: User Story 1 — [title] (P1)

- [ ] T003 [US1] AC-1 <behaviour>: test in tests/… (red) → implement in src/… (green)
- [ ] T004 [US1] AC-2 <behaviour>: test in tests/… (red) → implement in src/… (green)
- [ ] T005 [US1] AC-3 an expired invite is refused with `InviteExpired`, nothing is created: test `test_expired_invite_is_refused` in tests/test_invites.py asserts the error and the unchanged member list (red) → implement the expiry check in src/invites.py (green)

**Checkpoint**: US1 is independently functional — validate the slice against
its acceptance criteria and Success Criteria before starting US2; where the
telemetry module is installed, record one GRADE line per criterion in the
journal (`docs/process/modules/telemetry.md`). A wrong direction dies here,
at slice cost, not at review after 100% of the work.

## Phase N: User Story N — [title] (PN)

(same shape: one task per behaviour, each red → green inside the task, then the checkpoint)

## Final phase: Polish & cross-cutting concerns

- [ ] T0NN Docs affected by this feature updated (DoD)

## Execution rules

- Mark a task `[X]` in THIS file the moment it completes — the checkboxes
  are the canonical progress state (session re-entry: next task = first
  unchecked box).
- A task closes when its behaviour is green; its test and implementation land
  in one or two commits (`docs/process/commits.md`, Atomicity).
- Execution runs through the dev-process execute flow — `/speckit-implement`
  is not installed (it would bypass the commit and TDD discipline).
