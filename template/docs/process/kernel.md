# Always-on kernel

This file always renders, regardless of which harness adapters were installed
or skipped. It is the canonical source of the anchor kernel: when an existing
`CLAUDE.md` / `AGENTS.md` was skipped at install, copy the block between the
`KERNEL:START` / `KERNEL:END` markers below into your existing anchor and add a
pointer to `docs/process/start-here.md`. The rendered adapters carry an
identical copy; this neutral file exists so the kernel is obtainable even when
none of them were rendered.

**This block is gated.** The core `kernel` gate (`scripts/process/check_kernel.py`,
always on) verifies that every root anchor present in the repo carries the block
below byte-identical to this file — so a rule cannot be silently dropped, edited,
or truncated out of the anchor file (keeping it in the *live context* across
compaction is the behavioral mechanism in `start-here.md`, which no file gate can
verify). Adopt and extend your anchor *outside* the `KERNEL:START`/`KERNEL:END`
markers; the text inside them is canonical here, and exactly one block per file.

<!-- KERNEL:START -->
## Always-on kernel

**Load-bearing — these rules bind every turn, not just the first.** If you are resuming a session, or this block was summarized or compacted out of context, re-read `docs/process/kernel.md` and `docs/process/mandatory-rules.md` in full before continuing.

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
