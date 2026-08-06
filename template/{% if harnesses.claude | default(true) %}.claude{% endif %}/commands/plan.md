# /plan

Turn an approved design into a testable task breakdown that an
agent can execute without more context. Read `docs/process/workflow.md` (Plan)
and `docs/process/journal-state-plans.md` for where plans live. The input design
must be clarification-free — no unresolved `[NEEDS CLARIFICATION]` marker may
survive into the plan (the `clarification` gate blocks it). Write small
tasks with concrete files, code, and test commands. Required for every Tier 2+
change.

Next: `/execute`.
