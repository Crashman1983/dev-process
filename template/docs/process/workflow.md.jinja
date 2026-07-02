# Workflow

The development cycle, described harness-neutrally. Each phase names what enters it, what it produces, and when to use it. Tools differ per harness; the phases do not.

## The cycle

`brainstorm → plan → execute → review`, with `quick` as the Tier 1–2 shortcut and `debug` as the root-cause entry point. The tier (`risk-tiers.md`) decides how much of the cycle a change runs through: Tier 0 commits directly (no plan/review cycle — the branching rules in `commits.md` still apply), Tier 1–2 take the quick path, Tier 3+ run the full cycle.

## Brainstorm

Turns an idea into an approved design. Enters: a request or problem. Produces: a written design/spec the implementer can follow, plus explicit approval. Use before any non-trivial new behavior — do not start building until the design is agreed. Prefer a few clarifying questions over guessing the intent.

## Plan

Turns an approved design into a zero-context task breakdown. Enters: the design/spec. Produces: a plan file (`journal-state-plans.md`) of bite-sized, independently testable tasks with exact files, code, and test commands. Assume the implementer knows the toolchain but not this codebase. Use for every Tier 3+ change.

## Execute

Implements the plan task by task. Enters: the plan. Produces: committed, tested code — one atomic commit per task (`commits.md`), following test-driven development (write the failing test, watch it fail, implement, watch it pass, commit). Use as the build phase; keep tasks isolated so each is independently reviewable.

## Review

The gate before merge to the main branch. Enters: the branch diff plus the plan/spec. Produces: a pass/fail judgment on functional completeness, correctness, and adherence to these rules. The required depth scales with the tier (`risk-tiers.md`). Use before every merge that the tier gates; fixes loop back through execute + review until clean.

## Quick

The Tier 1–2 shortcut: no separate plan file. Enters: a small, isolated request. Produces: the change plus a test (Tier 2). State goal, touched files, and risk before editing; escalate to plan if persistence, auth, contracts, or external integrations turn out to be in scope.

## Debug

The root-cause entry point (mandatory rule 6). Enters: a bug, test failure, or unexpected behavior. Produces: a root-cause analysis before any fix. After two failed attempts at a symptom, stop patching and investigate why it happens; fix the cause, not the symptom.
