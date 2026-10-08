# /debug

Find the root cause of a bug before fixing it. Read
`docs/process/workflow.md` (Debug). After two failed symptom attempts: stop,
investigate why it happens, record the analysis, and fix the cause rather than
the symptom.

That counter does not live in your session — it lives in git. Before fixing,
check whether this behaviour is already collecting fixes:
`git log --oneline --since='14 days ago' --grep='^fix' -i -- <area>` (or
`process_kpis.py clusters` where telemetry is installed). **The third fix on
the same behaviour stops the fix**: write the rule as an invariant record
(Type: invariant, `docs/process/adr/template.md`) with a table/property test
that pins the whole rule — then fix your case as one row of that table.

Then follow the method in `docs/process/workflow.md` (Debug): a loop that
goes red on this bug before any theory, reproduce and minimise, three to
five falsifiable hypotheses, one variable per probe, the regression test at
the seam where the bug happens — and the commit names the hypothesis that
held.
