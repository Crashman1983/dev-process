# Module: speckit — Spec Kit as the Tier 2+ specification path

The standard specification front-end: GitHub Spec Kit's
`specify → clarify → plan → tasks` phases replace the thin brainstorm/plan
prose for Tier 2+ work (one owner — mandatory rule 4), while dev-process
keeps everything Spec Kit does not have: deterministic gates, tier routing,
review independence, journal/ADR/telemetry, DoR/DoD. Design and rationale
live in the template repo (docs/design, speckit-hybrid-design).

## Setup (once per repo, after the copier render)

Spec Kit is a **pinned, vendored dependency** — templates ship inside the
CLI package, so the pin fixes the whole workflow; at runtime nothing needs
the network or the CLI:

    uv tool install specify-cli==0.16.0
    specify init --here --force --integration <your agent>
    rm -rf .claude/skills/speckit-constitution \
           .claude/skills/speckit-implement \
           .claude/skills/speckit-taskstoissues
    echo ".specify/feature.json" >> .gitignore   # per-checkout state, never committed
    uv run scripts/process/gate_runner.py   # the regression net over the init

Three skills are deliberately not kept: `constitution` would overwrite the
rendered pointer (a second truth — the `speckit` gate guards the marker),
`implement` would bypass the execute flow's TDD + atomic-commit discipline,
and `taskstoissues` duplicates the issue path (`new_issue.py`,
issue-before-code). **Upgrades** are a deliberate act: bump the pin, re-run
`specify init --here --force`, diff the core templates against the overrides
(`.specify/templates/overrides/` survives — highest resolution priority),
run the gates, commit as its own `chore:` commit. **Exit scenario:** if Spec
Kit is discontinued or turns, freeze the pin — the vendored state runs
unchanged, forever if needed.

## The Tier 2+ flow

1. `/brainstorm` → runs `/speckit-specify` (+ `/speckit-clarify` until no
   `[NEEDS CLARIFICATION]` marker survives — the clarification gate blocks
   markers from reaching plan/tasks). The wrapper carries the kernel duties
   Spec Kit does not know: derive the tier first (`risk-tiers.md` — Tier 0/1
   takes the quick flow, no specs), read `PRODUCT.md` + decision records as
   constraints.
2. `/plan` → `/speckit-plan` + `/speckit-tasks`; add `tier: N` and
   `issue: <ref>` lines to `specs/<feature>/plan.md` (the review and issue
   gates key on them). Run `/speckit-analyze` at plan exit for **Tier 3, or
   when the spec was substantially iterated** — for a clean, single-pass
   Tier 2 cycle the templates already enforce structurally what analyze
   would re-derive, and the independent review sees spec + plan + tasks in
   the bundle anyway (token economy: one LLM pass saved per normal feature;
   LLM judgment is review input, never a gate).
3. Execute through the normal execute flow, consuming `tasks.md`: checkboxes
   in the file are the canonical progress state, story checkpoints validate
   each slice (GRADE lines where telemetry is on), TDD + one atomic commit
   per task. Completeness at review time is deterministic first: the
   `speckit` gate reports unchecked tasks in an active `tasks.md` as a
   visible note (zero tokens), and the review judges them. `/speckit-converge`
   (a full LLM pass over spec/plan/tasks/codebase) is reserved for **Tier 3**,
   where semantic divergence — built ≠ specified despite ticked boxes —
   justifies the cost.
4. Review + merge as always (bundle, REVIEW attestation, DoD). The merge
   ritual then runs `python scripts/process/publish_and_prune.py <feature>`:
   SC accounting first (every SC-ID evidenced / tracked as follow-up /
   waived — `sc-evidenced:`/`sc-followup:`/`sc-waived:` lines in plan.md),
   publish to the tracking issue, **verify**, only then prune
   `specs/<feature>/` (no `gh`/no verify ⇒ the directory stays —
   flow-forward degradation). Durable yield is promoted: user stories →
   feature-inventory entries with test refs; shared contracts → the contract
   SSOT.

## Branching and parallel agents

`specify init` does not create branches (0.16 — verified); branch creation
stays with this process: name the branch after the spec directory
(`003-chat-system`), one worktree per effort as always. Spec Kit's
feature-state file under .specify is per-checkout — gitignored (see setup),
so worktrees stay independent and merges never conflict on it.

## What the gate enforces (`check_speckit.py`)

- **Hard:** the constitution pointer marker removed/replaced (a second
  truth); a user-story phase in an active `specs/*/tasks.md` without a test
  task (rule 5 must not hang on prompt obedience — upstream declares "tests
  optional", the override plus this gate say otherwise).
- **Soft:** no `.specify/` yet (pre-init), named every run.
- The clarification gate additionally treats `specs/*/spec.md` markers as
  notes and `specs/*/plan.md`/`tasks.md` markers as hard.

## Model routing (recommendation, enforced by nothing)

specify/clarify: strongest model (judgment density) · plan: mid ·
tasks generation + execution against tasks.md: small (zero-context tasks
with exact paths; `process_context.py` hands the next task and the files it
names — no orientation guesswork) · review: per
`verification-independence.md` — Tier 3 crosses the model family,
non-negotiable. Measure the effect against your
own baseline (telemetry: convergence, cost, CFR) instead of trusting this
paragraph.
