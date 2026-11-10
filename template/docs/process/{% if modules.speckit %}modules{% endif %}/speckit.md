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
    # drop speckit-constitution, speckit-implement and speckit-taskstoissues
    # (why: below) where the integration put them —
    # Claude Code: .claude/skills, GitHub Copilot: .github/skills,
    # AGENTS.md agents (Codex): .agents/skills
    for d in .claude/skills .github/skills .agents/skills; do
      for s in constitution implement taskstoissues; do
        rm -rf "$d/speckit-$s" "$d/speckit.$s.md"   # skill dir or command file
      done
    done
    echo ".specify/feature.json" >> .gitignore   # per-checkout state, never committed
    # skills directory ignored? fix .gitignore first ("Commit the skills" below) —
    # git add skips ignored paths
    git add .gitignore .specify <your skills dir>/speckit*   # the skills travel with the repo
    git commit -m "chore: Spec Kit <pin> setup"
    uv run scripts/process/gate_runner.py   # the regression net over the init

**Commit the skills.** A clone gets only what is committed: a skills
directory left out of git means every fresh clone, worktree and cloud
session has no `/speckit-*` command and would need the CLI again — which a
sandbox may refuse. The flow uses `speckit-specify`, `-clarify`, `-plan` and
`-tasks`; `-analyze`, `-converge` and `-checklist` are optional, on demand
("The Tier 2+ flow" below). An integration that writes its skills elsewhere
adds its directory to the loop; the gate names any dropped skill still there
and any skill not yet committed.
Keeping them per user breaks "nothing needs the CLI at runtime"; the gate's
note stays until they are committed. If the project ignores its skills
directory, a `!` line alone does not help — git never re-includes a path
whose parent directory is excluded. Turn the directory rule into a
contents rule, one level per ignored parent:

<!-- gitignore-skills -->
```gitignore
# replaces the old directory rule (.claude/ or .claude/skills/) — a `!`
# line below a directory rule never re-includes; if only .claude/skills/ was
# ignored, use the last two lines alone (the first two hide new .claude/ files)
.claude/*
!.claude/skills/
.claude/skills/*
!.claude/skills/speckit*
```

(the same for `.github/skills` or `.agents/skills`).

Three skills are deliberately not kept: `constitution` would overwrite the
rendered pointer (a second truth — the `speckit` gate guards the marker),
`implement` would bypass the execute flow's TDD + atomic-commit discipline,
and `taskstoissues` duplicates the issue path (the issue templates,
issue-before-code). **Upgrades** are a deliberate act: bump the pin, re-run
`specify init --here --force`, drop the three skills again, `git rm` the
skill files the new manifest no longer lists (the gate names them),
diff the core templates against the overrides
(`.specify/templates/overrides/` survives — highest resolution priority),
run the gates, commit as its own `chore:` commit with the new skill files.
**Exit scenario:** if Spec
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
   gates key on them). `/speckit-analyze` is optional, on demand, like
   `-checklist`, at every tier — the templates already enforce structurally
   what analyze would re-derive, and the independent review sees spec +
   plan + tasks in the bundle anyway (token economy: one LLM pass saved per
   feature; LLM judgment is review input, never a gate).
3. Execute through the normal execute flow, consuming `tasks.md`: checkboxes
   in the file are the canonical progress state, story checkpoints validate
   each slice, TDD inside each task, which
   closes when its behaviour is green (test and implementation in one or two
   commits). Completeness at review time is deterministic first: the
   `speckit` gate reports unchecked tasks in an active `tasks.md` as a
   visible note (zero tokens), and the review judges them. `/speckit-converge`
   (a full LLM pass over spec/plan/tasks/codebase) is optional, on demand,
   like `-checklist` — for a suspected semantic divergence (built ≠
   specified despite ticked boxes), at no tier a required step.
4. Review + merge as always (bundle, REVIEW attestation, DoD). The merge
   ritual then runs `python scripts/process/publish_and_prune.py <feature>`:
   SC accounting first (every SC-ID evidenced / tracked as follow-up /
   waived — `sc-evidenced:`/`sc-followup:`/`sc-waived:` lines in plan.md),
   publish to the tracking issue, **verify**, only then prune
   `specs/<feature>/` (no `gh`/no verify ⇒ the directory stays —
   flow-forward degradation). A re-run posts only the parts the issue does
   not hold yet, and the verify reads back every part of this run; issue
   comments it cannot read refuse before anything is posted. The plan's
   archive copy is history for `plan-structure` while it is the text that
   stood at `specs/<feature>/plan.md`. Durable yield is promoted: user stories →
   feature-inventory entries with test refs; shared contracts → the contract
   SSOT.

## Stage publishing — the influence window

The human reads spec and design, not the plan — and influence is only cheap
BEFORE planning. So: create the tracking issue at *idea* time (title +
one-paragraph idea; the spec records `issue: #N`, the issues gate enforces
it), and once clarify is done, publish the spec to the issue:

    python scripts/process/publish_and_prune.py --stage <feature-dir>

A dated, read-only snapshot comment — the file in `specs/` stays the SSOT.
Read new issue comments before `/plan`: they are clarify input. The merge-time
`publish_and_prune <feature-dir>` (publish everything, prune the directory)
is unchanged.

## Outbound guard and the REST route

Everything `publish_and_prune.py` posts leaves the repository for an issue
that may be visible beyond the team. Before any post, each body is matched
against `.publish-denylist` (project-owned, one regex per line, `#`
comments); a hit refuses the whole publish and names the line — observed
downstream: a spec snapshot carried client slugs copied from UI-test stubs
and had to be scrubbed on the issue by hand. The template ships no list;
the project knows its own stubs, secrets and names.

Posting tries `gh issue comment` and falls back to the REST endpoint
(`gh api …/issues/N/comments`) when that fails: the CLI's comment goes
through GraphQL, whose secondary rate limit refused posts for hours while
the REST budget sat untouched. Verification reads back via REST first.

## Branching and parallel agents

`specify init` does not create branches (0.16 — verified); branch creation
stays with this process: name the branch after the spec directory
(`003-chat-system`), one worktree per effort as always. Spec Kit's
feature-state file under .specify is per-checkout — gitignored (see setup),
so worktrees stay independent and merges never conflict on it.

## What the gate enforces (`check_speckit.py`)

- **Hard:** the constitution pointer marker removed/replaced (a second
  truth); a user-story phase in an active `specs/*/tasks.md` with no task
  that references a test (rule 5 must not hang on prompt obedience — upstream
  declares "tests optional", the override plus this gate say otherwise). The
  task grain is one behaviour per task, test and implementation together
  (red → green inside the task, `/plan`); older split-style lists with a
  separate test task still pass.
- **Hard:** an active Tier 2+ plan with neither a `specs/` reference nor a
  `spec-waived: <reason>` line — spec-before-plan is a recorded decision.
- **Soft:** no `.specify/` yet (pre-init), named every run.
- **Soft:** the `/speckit-*` skills each installed integration lists in
  `.specify/integrations/<name>.manifest.json` — never committed (with the
  ignore rule that hides them), committed but missing from this checkout
  (sparse checkouts excepted), one of the three dropped skills back, or a
  committed skill no manifest lists (renamed upstream). No manifest, an
  unreadable one or no git means "unverified", never "all committed".
- The clarification gate additionally treats `specs/*/spec.md` markers as
  notes and `specs/*/plan.md`/`tasks.md` markers as hard (the build input).
  Markers in the other companions (`research.md`, `data-model.md`,
  `quickstart.md`, …) are notes with file and line — research records open
  questions by design. A note is not a permission: an unresolved
  load-bearing implementation decision is resolved (spec, or a plan
  `DECISION`) before the task that depends on it. A file the gate cannot
  read fails it.

## Model routing

Which model runs a phase, a tier and a task class (`[mechanical]`,
`[design]` beside `[P] [US1]` on a tasks.md line) is the model policy's,
read through `dispatch.py policy` — `docs/process/tower.md`, "Dispatch and
the model policy". Any per-command model setting belongs on the wrapper
commands, never on the `/speckit-*` commands themselves: a Spec Kit update
overwrites them.
