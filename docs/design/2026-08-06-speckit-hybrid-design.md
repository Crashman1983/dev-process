# Design: Spec Kit as the Tier 2+ specification front-end (`speckit-adapter` module)

Date: 2026-08-06 · Status: **implemented** (SP56; conditions of the independent review folded in — see `.process-work/reviews/2026-08-06-speckit-hybrid-design-review.md`) · Companion analysis:
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

## The `speckit-adapter` module (standard, default-on)

**Decision (2026-08-06): Spec Kit is the standard path, not an option.** The
module renders by default in every profile; disabling it is an explicit
opt-out for setups that cannot run Spec Kit, and that fallback path (thin
original commands + `design-template.md`) is frozen. With the module on:

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
3. **Publish-and-prune at merge (with `github-issues`); flow-forward as the
   fallback.** During work the artifacts must live on the feature branch —
   `tasks.md` is the execution input, clarify edits `spec.md` in place, and
   the review bundle needs spec+plan+tasks beside the diff. At the merge
   ritual, `spec.md`, `tasks.md` (and any research/data-model files) are
   published as comments on the tracking issue (the plan's `issue:` link
   names the target; same mechanism and best-effort character as
   `publish_review.sh` — the GitHub API supports no real file attachments,
   so comments it is, split at the 65k character limit), and `specs/NNN-…/`
   is deleted before merge. `main` carries nothing of the feature directory;
   the full content stays reachable in git history anyway (ff-only merges
   preserve the branch commits), so no traceability is lost. **One file
   stays in the repo:** the compact `plan.md` is archived to
   `.process-work/plans/archive/` exactly as today — it carries `tier:` and
   `issue:` and is the only artifact the review gate keys on. That part is
   non-negotiable: gates are hermetic and offline; issue comments are
   silently editable and deletable — a fine human archive, an unacceptable
   enforcement substrate. Without the `github-issues` module there is
   nowhere to publish, so the honest degradation is flow-forward: the
   feature directory merges and stays, under the existing retention stance
   ("prune by age as an ordinary change").
4. **Success criteria outlive the prune (SC lifecycle).** The spec's
   measurable Success Criteria deliver value at three moments: as a
   design-time forcing function (stating the outcome measurably is what
   steers toward the right problem), at review/checkpoint time (the spec is
   still on the branch — the bundle carries it, the reviewer judges the diff
   and the P1 slice against it; pruning happens only after the review
   passes), and **after release** — where most SCs are first verifiable at
   all, and where publish-and-prune would otherwise let them vanish silently
   into an issue comment. So the merge ritual carries a DoD item: every
   SC-ID is either (a) already evidenced at review (a test or measurement
   exists), (b) converted into a tracked follow-up — a measurement task on
   the issue or a registry story naming metric, threshold, and when to
   measure; a GRADE target where telemetry is installed — or (c) explicitly
   waived with a reason. Silent disappearance is not an option (the same
   deviation discipline DoR/DoD apply everywhere else). This gives SCs the
   post-merge lifecycle Spec Kit itself lacks.
5. **Context hygiene enables the small-model routing.** `/prime` and execute
   load, per task, only `tasks.md` plus the files it names exactly — never
   `specs/` recursively; the doc-drift gate keeps those references resolvable
   so targeted loading stays reliable.

## Downstream phases — what quick/debug/spike/execute/review borrow

The remaining Spec Kit skills were held against the downstream phases. Two
real finds, two format borrowings, two places where dev-process is ahead and
deliberately takes nothing:

1. **Plan exit gains an artifact-consistency step (`/speckit-analyze`) — the
   biggest find.** Our review judges code after implementation; `analyze`
   judges the *artifacts against each other before any code exists*:
   requirements with no covering task, spec↔plan contradictions, terminology
   drift, constitution violations. It is the cheapest point in the cycle to
   catch a wrong solution, and as a pure artifact read it is small-model
   work. Wiring: the `/plan` wrapper runs it at phase exit — mandatory for
   Tier 3, recommended for Tier 2.
2. **Execute adopts progress-in-the-artifact and checkpoints.** Task
   checkboxes are maintained in `tasks.md` itself (next task = first
   unchecked box), making session re-entry trivial and small-model-robust;
   foundational tasks gate story tasks, and each story checkpoint stops for
   slice validation (a GRADE point where telemetry is on). Execute keeps
   what `/speckit-implement` lacks — TDD ordering, atomic commits per task —
   which is exactly why the implement skill itself stays uninstalled: its
   two good ideas move into our execute flow instead of trading away the
   commit discipline.
3. **Review gains a completeness aid (`/speckit-converge`).** Before the
   independent review, converge diffs the codebase against spec/plan/tasks
   and lists what was promised but not built; the reviewer starts from a
   machine-prepared gap list. Both analyze and converge are LLM judgment:
   review *input*, never a gate — attestation and independence stay ours.
4. **Spike adopts the research resolution format.** Unknown → Decision →
   Rationale → Alternatives considered (Spec Kit's `research.md` shape); a
   spike born from a `[NEEDS CLARIFICATION]` marker writes its answer back
   at the marker site in exactly this shape, closing the loop mechanically.
5. **Cross-cutting: deterministic context bootstrap.** Every Spec Kit skill
   opens with `check-prerequisites.sh --json` — phase state as
   machine-readable JSON instead of model memory. `/prime` and execute adopt
   the same pattern; it is the quiet enabler of the small-model routing.
6. **Debug and quick take nothing, deliberately.** Spec Kit has no debugging
   story (a documented criticism) — root-cause-first stays as is. And quick
   is precisely what Spec Kit lacks and gets criticized for; the tier model
   is the answer to that gap, not the other way around.

Priority by the stated goals (cost, error rate): analyze at plan exit →
checkbox progress + checkpoints in execute → converge before review → spike
format → prerequisite JSON.

## Replacement, not parallel operation

Within a project that enables the module, the Spec Kit path **replaces** the
existing specification steps — mandatory rule 4 (one owner per behavior,
structural not additive) forbids a second parallel path:

- `/brainstorm` and `/plan` stay as the entry points but their bodies are
  repointed: `/brainstorm` → `speckit-specify` + `speckit-clarify`,
  `/plan` → `speckit-plan` + `speckit-tasks`. The kernel duties travel into
  the wrapper — deriving the tier and reading `PRODUCT.md`/ADRs as
  constraints are process obligations Spec Kit does not know.
- `design-template.md` is **not rendered** when the module is on — the
  spec-template override is then the sole owner of the Tier 2+ spec scaffold.
- `workflow.md` remains the phase SSOT: it states *what* Brainstorm and Plan
  must achieve; Spec Kit is the *how*. Specification vs. implementation, not
  duplication.
- Everything Spec Kit has no equivalent for stays untouched: quick, debug,
  spike, execute, review, commit, prime, all gates and hooks, tiers, DoR/DoD,
  journal, ADRs, telemetry.

The one honest residual duplication sits at template level: the module-off
path (thin original commands + `design-template.md`) keeps shipping as the
degradation for setups without Spec Kit — **frozen, not developed**. All
future evolution of the specification phase happens in the Spec Kit path only
(overrides, constitution, gate wiring); the fallback is a maintained-at-rest
escape hatch of a few pointer files, not a second product. The marker
convention and the `clarification` gate carry over unchanged in both paths
(Spec Kit uses the identical marker natively — verified in its spec
template).

## Cleanup — consolidations the standard decision forces

Making the Spec Kit path standard creates overlap that rule 4 requires us to
resolve *before* it becomes parallel accretion:

1. **One acceptance grammar.** EARS lives in issue bodies (DoR R2, read by
   the `github-master` gate); Spec Kit's template writes Given/When/Then.
   Resolution: the spec is the authoring site and the override formulates
   acceptance in EARS; the issue carries the EARS criteria as a copy synced
   at spec approval, direction spec → issue, so the existing gate keeps
   working. Two grammars, two locations, no owner — that ends here.
2. **One story concept.** Spec user stories (US1/P1, feature-local working
   form) map to feature-registry stories (STORY-NNNN, the durable
   traceability owner) via the promotion rule at merge; the US→STORY mapping
   is named in the merge commit.
3. **Skill exclusions.** Installed: specify, clarify, plan, tasks, analyze,
   converge, checklist — seven of ten. Excluded: `implement` (decided),
   `taskstoissues` (issue creation already has an owner:
   `new_issue.py` + issue-before-code), and `constitution` — running it
   would replace our rendered pointer with generated principles, recreating
   the second truth. Guard: a small check (kernel-gate mechanic) that the
   constitution file still carries its pointer line.
4. **SP55 partially superseded — honestly.** `design-template.md` renders
   only in the frozen fallback (conditional template); its marker
   documentation moves to a neutral home (`journal-state-plans.md`) since
   the spec template carries the marker natively. The `clarification` gate
   and the Specification-quality review section stay unchanged — both are
   template-agnostic.
5. **Reference hygiene.** `workflow.md`, `start-here.md`, the Copilot
   prompts, and the AGENTS.md section repoint to the Spec Kit path during
   the build; the doc-drift gate fails CI on any pointer missed. Checklist
   ownership stated once: `review-checklist.md` owns the review;
   `speckit-checklist` produces pre-review spec-quality aids.
6. **Outward-facing docs.** The README currently narrates a fully self-built
   specification path; after the build it describes the hybrid honestly
   (Spec Kit for the path to a specification, dev-process for enforcement
   and lifecycle). Analysis doc and CHANGELOG stay as history.

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

- Resolved (2026-08-06): built directly as the standard (owner's decision —
  result over path); the first adopting project delivers the measured
  baseline (convergence, cost, CFR).
- Resolved (2026-08-06): `/speckit-implement` stays uninstalled — execution
  remains with the dev-process execute flow (TDD + atomic commits + GRADE),
  consuming `tasks.md` as input and adopting implement's checkbox-progress
  and checkpoint ideas (see "Downstream phases").

## Measurement

The telemetry module's existing KPIs are the success test: convergence
(review rounds), cost per merged change, and CFR against the project's own
baseline after ≥5 Tier 2 cycles. No new metric machinery.
