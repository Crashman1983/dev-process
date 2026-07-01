# Mandatory Rules

Binding. Earlier rules outrank later ones; check them in order.

1. **Verification before assertion.** Every claim about existing code (file, function, flag, behavior) needs a same-turn tool-call (read/search) or an explicit confidence tag: `[verified]` / `[assumption]`. On conflict, `[verified]` wins.
2. **Plan before substantive work.** Derive the risk tier (`risk-tiers.md`) from the real scope, not the diff size, and route accordingly. Tier 3+ needs a written plan before code.
3. **Contract/interface first for shared behavior.** Behavior that crosses a component or repo boundary needs its interface/contract defined before any consumer implements against it. (Enforced by the `contract-first` module when installed.)
4. **One owner per behavior; structural over additive.** Check existing code first. New overrides, wrappers, or flags that duplicate an existing responsibility add accretion — find the owning layer and change it there. Two efforts on the same problem must declare *phase-of* or *supersede*, never run parallel.
5. **Tests prove acceptance.** Every feature or behavior change maps a test to the acceptance it claims. Exception: pure copy/formatting/doc-typo with no behavior change. (Acceptance lives in `docs/process/feature-registry/` when the `feature-registry` module is installed.)
6. **Root cause before symptom.** Max two diagnostic attempts at a symptom, then stop and do a root-cause analysis. Ask "why does this happen?", not "how do I suppress it?".
7. **Review gate before merge to the main branch.** Merge only after the review required by the tier (`risk-tiers.md`) has run.
8. **Atomic commits, documented exceptions.** One logical change per commit, imperative Conventional-Commit subject. A skipped gate or dropped scope is named in the commit body.
9. **Code is written to be read.** Code is read far more often than it is written — optimize for the next human. Prefer intention-revealing names for variables, functions, and types; keep units small and single-purpose; name constants instead of embedding magic numbers; let comments explain *why*, not *what*. Not mechanically checkable — enforced at the review gate. Concrete practices: `docs/process/code-craft.md`.
