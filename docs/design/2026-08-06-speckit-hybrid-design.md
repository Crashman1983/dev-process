# Design: Spec Kit as the Tier 2+ specification front-end (`speckit-adapter` module)

Date: 2026-08-06 · Status: proposed · Companion analysis:
`docs/analysis/2026-08-06-speckit-comparison.md` (strategic comparison; this
document is the integration design after an *empirical* evaluation).

## Intent

Adopt GitHub Spec Kit's specification workflow (`specify → clarify → plan →
tasks`) as the Tier 2+ path to a plan, while dev-process keeps everything it is
uniquely good at: deterministic enforcement (gates + hooks), risk-tier routing,
review independence, journal/ADR/telemetry, DoR/DoD. Goals, in the user's own
priority: develop faster and more targeted (right solution for the right
problem), and cut cost — including making phases workable by smaller models
instead of a frontier model end to end.

## Empirical findings (verified against specify-cli 0.16.0, not prose)

A real `specify init --integration claude` render was inspected. Facts:

1. **No file collisions.** Spec Kit lives entirely under `.specify/` and
   `.claude/skills/speckit-*`; dev-process under `docs/process/`,
   `scripts/process/`, `.process-work/`, `.claude/commands/`. The two install
   additively into the same repo.
2. **Templates are bundled inside the CLI package** — init needs no network and
   the template set is exactly the pinned CLI version. Pinning
   `specify-cli==X.Y.Z` pins the whole workflow; upgrades are deliberate.
3. **An official, update-safe customization layer exists.**
   `resolve_template()` in `.specify/scripts/bash/common.sh` resolves
   `.specify/templates/overrides/<name>.md` at highest priority (then presets,
   extensions, core). `.specify/extensions.yml` adds `before_*` command hooks.
   Everything we inject lives there — **never** in edited skills or core
   templates, which a re-init regenerates.
4. **The phase logic is genuinely stronger than our thin commands.** The spec
   template forces prioritized, *independently testable* user stories
   (P1/P2/… as MVP slices), Given/When/Then scenarios, numbered FR-IDs,
   **measurable technology-agnostic Success Criteria (SC-IDs)** distinct from
   acceptance, an explicit Assumptions section, and native
   `[NEEDS CLARIFICATION]` markers. `/speckit-clarify` runs a structured
   ambiguity taxonomy with a **maximum-5, impact-ranked question budget**.
   The tasks template groups tasks **per story** with `[P]` parallel markers,
   exact file paths, and a **checkpoint after each story**. This is precisely
   the SP56 backlog we would otherwise hand-build — adopting is cheaper than
   rebuilding, and it tracks upstream improvements.
5. **The enforcement gap is real and verified.** The tasks template declares
   *"Tests are OPTIONAL — only include them if explicitly requested"* — a
   frontal contradiction of mandatory rule 5. The constitution is a
   placeholder scaffold with no enforcement. Spec Kit brings no deterministic,
   merge-blocking checks at all. The gates are not redundant beside Spec Kit;
   they are the missing half.

## Why this pays (the honest cost/benefit)

- **Right problem, right solution:** solution-neutral spec before plan,
  measurable SCs, and the clarify taxonomy attack exactly the "wrong
  solution / missed problem" failure mode — at design time, not at review.
- **Cost:** story-sliced tasks with checkpoints mean a wrong direction dies
  after the P1 slice, not after 100% of implementation. And the phase
  separation concentrates judgment where it is needed, enabling model routing
  (below). The gates stay deterministic — zero tokens.
- **Speed:** `tasks.md` entries are zero-context with exact paths — cheap
  models execute them; parallel `[P]` tasks feed the existing parallel-agent
  discipline.
- **Counterweights, stated plainly:** Spec Kit is 0.x with a history of
  breaking renames (mitigated by the version pin + gates as an upgrade
  regression net); its per-feature artifact volume is real overhead
  (mitigated by tier routing — the pipeline runs for Tier 2+ only; quick flow
  is untouched); skill bodies are not an update-safe customization surface
  (mitigated by putting every injection into overrides / extensions.yml /
  constitution / gates).

## Architecture — ownership split (one owner per behavior)

| Concern | Owner |
|---|---|
| Tier routing, quick/debug/spike flows | dev-process (kernel, `risk-tiers.md`) |
| Tier 2+ path to a plan: specify → clarify → plan → tasks | **Spec Kit** |
| Principles / constitution | dev-process SSOT (`kernel.md`, `mandatory-rules.md`, `PRODUCT.md`); `.specify/memory/constitution.md` rendered as a thin pointer to them — one truth |
| Enforcement (all gates, hooks, CI) | dev-process |
| Review, verification independence, DoD | dev-process (`review-checklist.md`, `verification-independence.md`) |
| Journal, ADRs, telemetry, issues | dev-process |
| Execution vocabulary for Tier 2+ tasks | Spec Kit `tasks.md` (checkpoints double as GRADE/journal points) |

## The `speckit-adapter` module (opt-in)

A new module, so nothing is discarded: without it, the existing thin
brainstorm/plan commands remain the Tier 2+ path (they stay for portability
and for harnesses Spec Kit does not cover). With it:

1. **Bootstrap step:** documented pinned install
   (`uv tool install specify-cli==<pin>` + `specify init --here
   --integration <harness>`), verified by the gate runner afterwards.
2. **Rendered overrides** (`.specify/templates/overrides/`):
   - `plan-template.md`: carries the `tier: N` and `issue: <ref>` lines so the
     existing review/issue gates key on Spec Kit plans unchanged.
   - `tasks-template.md`: deletes the "tests are optional" stance — every
     story slice carries its test tasks (mandatory rule 5); checkpoints
     instruct a journal/GRADE entry where telemetry is installed.
   - `spec-template.md`: adds the DoR-R2 twins (negative, edge, authorization,
     invalidation/cleanup) to the acceptance scenario prompts.
3. **Rendered constitution:** thin pointer file — principles live in
   `docs/process/`; the kernel gate already guards the kernel text itself.
4. **Gate extensions (small, in existing owners):**
   - `check_review.py`: also treat `specs/<feature>/plan.md` as a plan surface
     (active while its branch lives; the archive step stays the merge record).
   - `check_clarification.py`: markers in `specs/*/spec.md` are notes;
     markers in `specs/*/plan.md` or `tasks.md` are hard.
   - `doc-drift-gate`: include `specs/` in reference checking.
   - Command adapters: `/brainstorm` and `/plan` point to the speckit path
     when the module is on (doc-drift keeps the pointers honest).
5. **Update path, both directions independent:**
   - Spec Kit: bump the pin → re-run `specify init --here --force` → the
     regenerated files are core-only (our layer survives in overrides/
     extensions/constitution) → run the gate suite as the regression net →
     commit the upgrade as an ordinary reviewed change.
   - dev-process: `copier update` exactly as today.
6. **Model routing (documented in the module doc, enforced by nothing —
   honestly a recommendation):** specify/clarify = strongest model (judgment
   density); plan = mid; tasks generation, implement, taskstoissues,
   checklist = small model (template- and path-driven); review = per
   `verification-independence.md` (Tier 3 crosses the model family — the one
   place the strong model is non-negotiable).

## File governance — containing the artifact volume

Spec Kit's most-cited criticism is its file volume; the module makes the
containment rules explicit. Two file classes, two treatments:

**Infrastructure (`.specify/`, `.claude/skills/speckit-*` — ~30 files, once
per repo): treated as a vendored, pinned dependency.**

- Never hand-edited — a re-init regenerates them; our layer lives only in
  `overrides/`, `extensions.yml`, and the constitution pointer.
- Marked `linguist-generated` in `.gitattributes` so upgrade diffs collapse
  in PR review.
- Upgraded in a dedicated commit (`chore: bump spec-kit X→Y`), never mixed
  into feature work — diff noise becomes one reviewable moment per upgrade.
- Only the skills the process actually uses are installed; `implement` (the
  execute flow owns execution) and redundant optional skills are skipped.
- Token cost is a non-issue: skills load into context on invocation only.

**Per-feature artifacts (`specs/NNN-feature/`): tier-capped, single-owner,
flow-forward.**

1. **Tier-proportional artifact ceiling.** The core is `spec.md + plan.md +
   tasks.md`. `research.md`, `data-model.md`, `quickstart.md`, `checklists/`
   are created only when content demands them (Tier 3, data-model contact,
   real research questions) — stated in the plan-template override, not left
   to habit. Effort scales with risk, not ritual.
2. **Feature files point, they do not duplicate.** A contract touching more
   than the one feature is promoted to the repo-wide contract SSOT
   (`contract-first`/`contracts-drift`) at merge, the feature copy replaced
   by a reference; durable product/architecture truth moves to
   `PRODUCT.md`/ADRs/registry. `specs/` is the path to the result, never the
   truth afterwards (mandatory rule 4).
3. **Flow-forward persistence, consistent with the archive ritual.** Of Spec
   Kit's three persistence models we choose flow-forward: each feature keeps
   its directory, unchanged after merge, as audit trail — the same role
   `.process-work/plans/archive/` plays today, covered by the same retention
   stance ("growth is unbounded by design; prune by age as an ordinary
   change"). The merge ritual still archives the plan (the review record has
   one owner — the archive); `specs/` remains working history.
4. **Context hygiene enables the small-model routing.** `/prime` and execute
   load, per task, only `tasks.md` plus the files it names exactly — never
   `specs/` recursively; the doc-drift gate keeps those references resolvable
   so targeted loading stays reliable.

## What SP55 becomes

The marker convention and the `clarification` gate carry over unchanged (Spec
Kit uses the identical marker natively — verified in its spec template).
`design-template.md` remains the owner of the design scaffold **without** the
module; with the module active, the Spec Kit spec template owns Tier 2+ specs
and `design-template.md` stays the fallback for quick designs and spikes — the
module doc states this ownership split explicitly.

## Acceptance criteria for the module (EARS)

- AC-1: When the module is enabled and `specify init` has run, the gate runner
  shall pass on a clean render (no collisions, no dead pointers).
- AC-2: When a `specs/<feature>/plan.md` declaring `tier: 2` merges without a
  clearing REVIEW attestation, the review gate shall fail.
- AC-3: When an unresolved `[NEEDS CLARIFICATION]` marker survives into
  `specs/<feature>/plan.md` or `tasks.md`, the clarification gate shall fail.
- AC-4: When the rendered overrides are present, a generated `tasks.md` shall
  contain test tasks for every story slice (judged at review; the override
  text is the mechanism).
- AC-5: When Spec Kit is upgraded to a newer pinned version and re-initialized,
  files under `.specify/templates/overrides/`, `.specify/extensions.yml`, and
  the constitution pointer shall survive unmodified.

## Open questions

- [NEEDS CLARIFICATION: pilot scope — enable the module in one real project
  first, or ship it in dev-process and pilot there? Telemetry baseline needs
  a few Tier 2 cycles either way.]
- [NEEDS CLARIFICATION: should `/speckit-implement` be recommended at all, or
  should execution stay with the dev-process execute flow (TDD + atomic
  commits + GRADE), consuming Spec Kit's tasks.md as input? Default
  recommendation: keep execute — implement bypasses the commit discipline.]

## Measurement

The telemetry module's existing KPIs are the success test: convergence
(review rounds), cost per merged change, and CFR against the project's own
baseline after ≥5 Tier 2 cycles. No new metric machinery.
