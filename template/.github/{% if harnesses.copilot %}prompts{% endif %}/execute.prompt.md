# execute

**Project overlay:** if `docs/process/commands/execute.local.md` exists, read it
before you start — the project's own rules for this command, binding over
this file where it says so; a template doc this command sends you to may
have one beside it (`<doc>.local.md`), read with the doc
(`docs/process/overlays.md`).

Execute the plan task by task, test-driven. Re-read the kernel
(`docs/process/kernel.md`) and `docs/process/mandatory-rules.md` first — a long
build compacts, and the rules bind every task. Run
`uv run scripts/process/process_context.py --issue N` (the issue you execute)
for the next unchecked task. Then read
`docs/process/workflow.md` (Execute). Per task: failing test, see red, implement
the minimum, see green, commit atomically. Name an acceptance criterion by
its id, never restate its text; where the feature inventory is installed,
the last task before review writes its entry from the spec's final `AC-n`
lines (feature-registry module, "One owner per criterion"). A packet handed
to a helper carries its files, the paths it must not touch, its acceptance
criteria and the narrow command that proves them, and comes back with that
command red before and green after; a larger model needs a named reason —
neither the plan's tier nor an infrastructure failure is one.
