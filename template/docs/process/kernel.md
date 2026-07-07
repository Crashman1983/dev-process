# Always-on kernel

This file always renders, regardless of which harness adapters were installed
or skipped. It is the canonical source of the anchor kernel: when an existing
`CLAUDE.md` / `AGENTS.md` was skipped at install, copy the block between the
`KERNEL:START` / `KERNEL:END` markers below into your existing anchor and add a
pointer to `docs/process/start-here.md`. The rendered adapters carry an
identical copy; this neutral file exists so the kernel is obtainable even when
none of them were rendered.

<!-- KERNEL:START -->
## Always-on kernel

**Mandatory rules (full text: `docs/process/mandatory-rules.md`):**
1. Verify before asserting. 2. Plan before substantive work. 3. Contract/interface first.
4. One owner per behavior. 5. Tests prove acceptance. 6. Root cause before symptom.
7. Review gate before merge. 8. Atomic commits. 9. Readable, intention-revealing code.

**Tier routing (full matrix: `docs/process/risk-tiers.md`):**
Tier 0 -> direct commit if no behavior change, else quick flow (no review; branching rules still apply). Tier 1 -> quick flow + a test.
Tier 2+ -> plan -> execute -> review.
Scope, not diff size, sets the tier.

**Language:** converse with the user in the user's language; write all artifacts
(docs, code, commits, ADRs, journal) in English.
<!-- KERNEL:END -->
