# Design: anchor guidance (SP13)

**Date:** 2026-07-03
**Status:** approved (scope: the two portable gaps a comparison against a mature
adopter surfaced — the anchor-vs-process-docs principle is embodied but never
stated, and nested per-subtree anchors are undocumented)
**Slice:** state the "keep the anchor thin" discriminator as onboarding
guidance, and document how to scale anchors for a large multi-stack repo —
so the thin kernel stays thin over time instead of drifting fat.

## Gap

The template's `CLAUDE.md`/`AGENTS.md` are thin by design (methodology lives in
`docs/process/`), but two things a mature adopter carries in its own anchor
have no home here:

1. **The discriminator itself is unstated.** The template *embodies* "anchors
   carry pointers and role, not drifting detail" (the adapter says "thin
   adapter"), but never says it. A maintainer deciding "does this go in the
   anchor or in `docs/process/`?" has no rule to apply — so the anchor fattens
   over time, exactly the drift the thin design exists to prevent.
2. **Scaling anchors is undocumented.** A large multi-stack repo needs
   stack-specific facts somewhere; without guidance the root anchor becomes the
   dumping ground. The per-subtree-anchor technique (harness-specific in
   mechanism) is a known answer but absent from the template.

## Decision — put both in `start-here.md`, guard from the adapter

Both are onboarding/structure concerns, so they belong in `start-here.md` (read
at onboarding, referenced by every adapter), not in the always-loaded kernel —
adding always-on lines to teach "keep the always-on part small" would be
self-defeating on the very token economy the thin kernel buys.

- New `start-here.md` section **"Anchors: what goes where, and how to scale
  them"**:
  - The anchor carries role, mission, pointers, and project facts that do not
    drift. It must **not** carry detail that drifts on a refactor — commands,
    ports, versions, file/symbol names, mechanics. Those have canonical sources
    (build files, the code, `docs/process/`); the anchor **points, it never
    copies** (a copy drifts and becomes a lie the reader trusts). Discriminator:
    *does it drift on a refactor?* → then not the anchor.
  - Scaling: for a large multi-stack repo, do not fatten the root anchor — put
    stack-specific facts in per-area anchors and keep the root about
    cross-cutting process. Mechanism is harness-specific: Claude Code loads a
    nested anchor per subtree automatically; AGENTS.md-style harnesses use a
    per-directory file or an explicit pointer from the root.
- The `CLAUDE.md` adapter's existing "thin adapter" line gains a pointer to the
  section (one word of always-on cost, at the exact spot the fattening starts).
  The kernel block is untouched (byte-identity across adapters holds).

## Out of scope

Any machine gate for anchor bloat (there is a `check_claude_md_budget`-style
idea in a mature adopter, but that is a module-sized effort and this slice is
guidance); harness-specific nested-anchor *rendering* (the template ships one
root adapter; splitting is the project's choice at onboarding, described, not
scaffolded).
