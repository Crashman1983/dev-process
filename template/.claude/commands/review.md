# /review

**Deutsch:** Fuehre das Gate vor dem Merge auf den Main-Branch aus. Lies
`docs/process/workflow.md` (Review); die Tiefe richtet sich nach
`docs/process/risk-tiers.md`. Pruefe funktionale Vollstaendigkeit, Korrektheit
und Regelkonformitaet gegen Plan oder Spec. Fixes gehen zurueck durch
`/execute` und erneut `/review`, bis der Branch sauber ist.

**English:** Run the gate before merging to the main branch. Read
`docs/process/workflow.md` (Review); depth scales with
`docs/process/risk-tiers.md`. Judge functional completeness, correctness, and
rule adherence against the plan or spec. Fixes loop back through `/execute` and
then `/review` again until the branch is clean.
