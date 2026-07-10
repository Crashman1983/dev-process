# Start Here

## Purpose

This repository has the development process installed. That is the process
baseline, not an automatically onboarded product project. Setup is meant to be
guided by an LLM: the LLM asks step by step, documents the answers, and only
then creates the project-specific artifacts.

Converse with the user in the user's language; write all artifacts (docs,
code, commits, ADRs, journal) in English.

**When this process is not worth it:** for throwaway prototypes, one-off
scripts, and single-session work the overhead is a net loss — install nothing,
or pick the `minimal` profile and skip the onboarding dialogue. The process
pays off for anything multi-session, multi-agent, or touching contracts,
persistence, or auth.

## Profiles and the hardening ratchet

Module choice at install time is one question, not thirteen: the **profile**
preset derives the module set, and the modules question then shows that set for
adjustment — a starting point, not a lock.

| Profile | Modules on top of the core gates | Who it fits |
|---|---|---|
| `minimal` | none | prototypes; the smallest footprint |
| `solo` (default) | doc-drift, git-hooks | one developer — local enforcement carries the process even without CI review culture |
| `team` | solo + feature-registry, github-issues | a small team — shared backlog and acceptance traceability |
| `custom` | none preselected | you know exactly what you want |

**Harden as the project earns it — the ratchet.** Start light and switch a
module on when its trigger appears; each step is a `copier update` with the new
module set (see BOOTSTRAP.md, "Later"). The triggers:

- first **persistence, auth, or secrets** → `security_floor`
- a **second surface** (web + cli, web + mobile) → `parity`
- a **shared or external interface** another component builds on →
  `contract_first`, `contracts_drift`
- **user-visible behavior worth tracing** to acceptance and tests →
  `feature_registry`
- the backlog outgrows one head, or a **second person/agent** joins →
  `github_issues` (and `github_master` once issues become the source of truth)
- **architecture claims worth checking** against real code → `arch_onboarding`;
  stakeholders who want to *read* it → `arch_docs`
- you want to **measure what the process catches and costs** → `telemetry`
- **license/compliance** obligations → `sbom`

The ratchet only tightens: switching a module *off* again is a process decision
— record why (decision record), do not just drop the gate that started failing.

**The mid-size caveat:** four gates are *core* and always run regardless of the
module profile — `kernel` (the always-on rule block is intact in the anchor),
`decision-records`, `review`, and `product-frame`. So even on
the minimal profile, the first Tier 2+ change (one that touches a contract,
persistence, auth, or something another component depends on) carries the full
plan → review → attestation ceremony, without the optional modules
(feature-registry, github-issues) that would house its acceptance and issue
link. A project too small to want that ceremony but that will inevitably make
one cross-component change sits in an awkward middle: keep such changes rare, or
accept the core-gate floor as the price of the guarantee it buys (no unreviewed
Tier 2+ merge).

## First run

1. Confirm that the process files exist: `CLAUDE.md`, `PRODUCT.md`,
   `docs/process/`, `.copier-answers.yml`, and `scripts/process/gate_runner.py`.
2. Initialize Git if this is a new repository.
3. Install local hooks if the `git-hooks` module is active:
   `bash scripts/process/install-hooks.sh`.
4. Run the gates: `python scripts/process/gate_runner.py` (use `python3` if
   `python` is not on PATH; needs `PyYAML>=6`).
5. Read `docs/process/mandatory-rules.md` and `docs/process/risk-tiers.md`.
6. Create a process-baseline commit before product work starts. If you already
   installed the `git-hooks` module (step 3) and you are on the main branch, the
   no-direct-main pre-commit will block this one-time commit — run it with
   `ALLOW_MAIN_COMMIT=1 git commit …` (the sanctioned bypass for onboarding), or
   make the baseline commit before installing the hooks.

Green gates at this stage mean: "the process is installed." They do not yet
mean that architecture, requirements, contracts, parity, or security rules
have been onboarded as project facts.

## LLM-guided onboarding

The LLM guides setup like a brainstorming session. It asks only a few
questions at a time, summarizes the answers, labels assumptions explicitly,
and writes files only after the answers are clear.

### Starting questions

1. Question: Is this project Greenfield or Brownfield?
2. Question: What is the project goal in one paragraph?
3. Question: Who uses the project and what is the first useful outcome?
4. Question: Which technology or stack constraints exist?
5. Question: Which risks are already known: auth, persistence, external
   interfaces, security, multiple surfaces?

### Question compass

Use these categories as a compass, not as a form. Ask only the questions
relevant to the current mode. If an answer is unknown, document it as an open
question or assumption; do not invent it.

- Purpose: Which problem does the project solve, and how is value recognized?
- Users: Who uses the system, and which role has priority?
- First slice: What is the smallest useful end-to-end outcome?
- Stack — ask per layer; open layers go through proposal mode (see dialogue
  rules):
  - Frontend: Which technology carries each surface (framework, rendering,
    build), or is the project deliberately frontend-free?
  - Backend: Which language, framework, and runtime are fixed or preferred?
  - Storage: What kind of persistence (relational, document, files, none),
    which concrete system, and how do migrations run?
  - API/communication: How do the project's own components and surfaces talk
    to each other (REST, GraphQL, gRPC, events, queues), and how is that
    versioned? The answer informs the module choice (`contract-first`,
    `contracts-drift`, `parity`).
  - Deployment: Which runtime environment and deployment targets are set?
- Codebase: Is there existing code, tests, CI, docs, or data model?
- Architecture: Which code roots, layers, interfaces, and boundaries actually
  exist or are planned?
- Data/Auth/Security: Is there persistence, personal data, authorization,
  secrets, or forbidden patterns?
- Integrations: Which external APIs, events, files, jobs, or systems are
  involved?
- Surfaces: Is this web, mobile, CLI, API-only, or multiple target surfaces?
- Quality: Which tests, gates, performance, or operations requirements matter
  from the beginning? Should the process measure what its gates catch and
  cost (`telemetry`)?
- Organization: Are there issues, labels, release rules, review duties, or
  multiple agents/humans?

### Dialogue rules

- Always name the mode: Greenfield or Brownfield.
- Converse in the user's language; write artifacts in English.
- Ask at most three questions at a time.
- After each answer, briefly summarize what was understood.
- Mark assumptions and get confirmation before writing files.
- Proposal mode: if a stack layer has no given preference, derive 1-3 options
  from the goal, the first slice, and the known constraints, name the
  trade-offs, mark one recommendation, and get it confirmed. Proposals are
  always clearly labeled as proposals — facts are still never invented.
- Do not write real architecture, story, contract, parity, or security
  artifacts until the facts are defensible.
- End with the next three concrete steps.

### Dialogue output

**The dialogue's primary artifact is the product frame:** fill `PRODUCT.md`
(purpose, users, goals, non-goals, constraints, scope now) from the confirmed
answers and flip its `status:` to `onboarded` — the frame is created *in* this
init dialogue, not as a separate chore afterwards. Every later phase reads it
as the direction development is checked against (`workflow.md`,
`review-checklist.md`).

Beyond the frame, the LLM records at least:

- Greenfield or Brownfield;
- project goal and first useful slice;
- initial stack per layer (frontend, backend, storage, API/communication,
  deployment) and source layout — each layer decided,
  proposed-and-confirmed, or a documented open question;
- whether `ARCHITECTURE.md` (if `arch-onboarding` is active) can already
  receive a real `arch` block, and whether the stakeholder-facing
  `ARCHITECTURE-OVERVIEW.md` (if `arch-docs` is active) has an audience yet;
- whether real entries under docs/process/feature-registry/ are needed;
- whether contracts, parity, or security floor need real artifacts now or stay
  intentionally inert.

## Greenfield start

Use this path when no product code exists yet.

1. Fill `PRODUCT.md` from the onboarding dialogue (purpose, users, goals,
   non-goals, constraints, scope now) and flip its `status:` to `onboarded`.
2. Settle the stack per layer (frontend, backend, storage, API/communication,
   deployment); where no preference is given, use proposal mode. Choose the
   confirmed result and the source layout small enough that the first
   architecture can be described truthfully, and record fundamental stack
   decisions as ADRs.
3. Create source directories and interface files only then.
4. If `arch-onboarding` is active, replace the inert `arch-example` in
   `ARCHITECTURE.md` with a real `arch` block only when the referenced paths
   exist.
5. If `feature-registry` is active, copy the seed under
   docs/process/feature-registry/ and remove `.example` from the filename once
   the first real user story is known.
6. If `security-floor` is active, copy the file security-floor.example.json to
   a policy file named security-floor.json once real forbidden patterns are
   known.
7. Keep optional examples for `parity`, `contract-first`, `contracts-drift`,
   and the `telemetry` calibration seed inert until real capabilities,
   interfaces, external contracts, or graded work exist.
8. Start new work through tier routing: Tier 0-1 uses Quick; Tier 2+ uses
   Brainstorm -> Plan -> Execute -> Review.

## Brownfield start

Use this path when product code already exists.

1. Do not rewrite the project just to fit the process.
2. Inventory real code roots, tests, architecture boundaries, features,
   external contracts, security invariants, and surfaces first.
   Fill `PRODUCT.md` from the *real* product — what it actually does and for
   whom, plus the deliberate non-goals — and flip its `status:` to `onboarded`;
   aspirations that are not yet true belong in Goals, not in Scope now.
3. Fill `ARCHITECTURE.md` from real code. If a rule is only aspirational,
   document it in an ADR as `change-planned` or `tolerated`, not as already
   satisfied.
4. Create registry entries only for facts you can defend: real stories, real
   tests, real contracts, real parity gaps, real security rules.
5. Run `python scripts/process/gate_runner.py` after each onboarding slice.
6. Commit onboarding in small steps: architecture baseline, feature registry,
   contracts, parity, security floor.
7. Start product work only after the relevant baseline for that area exists.

## Which artifact when

A quick router for the "where does this go?" question — the single most common
onboarding confusion. Match your thing to its home:

| You have… | It goes in… | Gated? |
|---|---|---|
| A significant, hard-to-reverse decision (architecture, product, or process) | a decision record `docs/process/adr/adr-NNNN-*.md` | decision-records (core) |
| An approved design/spec before building | a `design-*.md` beside the plan (`.process-work/plans/`) | no (review reads it) |
| The product's purpose, goals, non-goals, scope | `PRODUCT.md` (edit it in the same change that shifts scope) | product-frame (core) |
| A unit of user-visible behavior + its acceptance + tests | a registry story `docs/process/feature-registry/STORY-NNNN.json` | feature-registry |
| A Tier 2+ change's task breakdown | a plan `.process-work/plans/YYYY-MM-DD-*.md` | review presence (core) |
| The reasoning behind a choice made mid-work | the journal `.process-work/journal/…` | no |
| Work you noticed but won't do now | one line in `.process-work/inbox.md` | no (triage later) |
| A review/audit's prompt, verdict, findings | a report `.process-work/reviews/*.md` | github-issues |

Rule of thumb: a *decision* → record; a *design* → design doc; the *product's
shape* → PRODUCT.md; a *behavior* → story; *how to build it* → plan; *why you
did it* → journal; *something for later* → inbox.

## Anchors: what goes where, and how to scale them

The anchor files (`CLAUDE.md`, `AGENTS.md`, and any harness equivalent) are thin
by design: the authoritative process lives in `docs/process/`. Keep them thin as
the project grows.

**What the anchor carries:** role and mission, the always-on kernel, pointers to
where things live, and project facts that do not drift. **What it must not
carry:** any detail that changes on a refactor — commands, ports, versions,
file or symbol names, mechanics. Those have canonical sources (build files, the
code itself, `docs/process/`), and the anchor **points at them, it never copies
them** — a copy drifts out of date and becomes a lie the reader trusts.
Discriminator: *does it drift on a refactor?* If yes, it does not belong in the
anchor.

**Scaling to a large or multi-stack repo:** do not let the root anchor become a
dumping ground for stack-specific facts. Keep the root about cross-cutting
process, and put stack-specific facts in per-area anchors. The mechanism is
harness-specific: Claude Code loads a nested anchor file per subtree
automatically when work touches that subtree; AGENTS.md-style harnesses use a
per-directory file or an explicit pointer from the root anchor. Either way the
root stays small and each area owns its own detail.

## Keeping the kernel loaded across compaction

The `kernel` gate guarantees the rule block is intact *in the anchor file*. It
cannot guarantee the block is in the model's *live context* — a long session
compacts (summarizes) its history, and the anchor can be summarized away even
though the file is untouched. No offline gate can see the live context, so this
is a behavioral invariant, not a checkable one. Four things keep the kernel
loaded:

- **The kernel is thin by design** — small enough to survive a summary intact.
- **It is self-restoring.** Its first line instructs: if you are resuming or the
  block was compacted, re-read `kernel.md` and `mandatory-rules.md` before
  acting. That directive rides along with any surviving fragment, and the
  `kernel` gate's byte-identity check makes it un-droppable from the file.
- **Phases re-hydrate.** `execute` and `review` re-read the kernel and the plan
  at phase entry (`workflow.md`) — the long phases are exactly where compaction
  strikes, so they do not trust warm memory.
- **The harness helps, unevenly.** Claude Code re-injects the root anchor after
  compaction automatically; a `PreCompact`/`SessionStart` hook can re-read the
  kernel explicitly. AGENTS.md-style harnesses vary — there, the self-restoring
  directive and `/prime` on resume are the safety net. Configure a
  compaction/session hook where your harness supports one.

## Definition of ready (project onboarding)

This is the one-time *project*-readiness bar — the process is installed and
onboarded. It is distinct from the per-work-item **Definition of Ready /
Definition of Done** (`definition-of-ready-and-done.md`), which gates starting
and finishing each issue or story once development is under way.

The project is ready for normal process-driven development when:

- the process baseline is committed;
- Greenfield or Brownfield is recorded in `.process-work/`;
- `PRODUCT.md` is either honestly `not-onboarded` (the gate notes it) or
  onboarded with real purpose, users, goals and non-goals from the dialogue;
- if `arch-onboarding` is active: `ARCHITECTURE.md` either honestly remains
  "not onboarded yet" or contains a real `arch` block with existing paths;
- each active optional module either intentionally stays inert or has at least
  one real project artifact;
- `scripts/process/gate_runner.py` runs and all notes are understood as known
  onboarding state;
- **the CI gate is wired as a *required* check.** The `process-gates` job failing
  only blocks a merge if your host is configured to require it — CI cannot set
  this itself. On GitHub, the GitHub CI adapter ships a one-command setup:
  `setup_branch_protection.sh` (under scripts/process/) idempotently adds
  `process-gates` as a required status check on the default branch — or do it
  manually via Settings → Branches. On GitLab: a merge-request approval rule /
  pipeline-must-succeed setting. Without this, a red gate is advisory, not
  enforced — the single step that turns "the gate runs" into "the gate blocks".

Once developing: before planning any change, read the Decision Records
(`docs/process/adr/`) relevant to the area you are about to touch — a decision
already made and endorsed is a constraint, not an open question. A new
significant, hard-to-reverse decision (architecture, product, or process) gets
its own record *before* the code that assumes it (mandatory rule 4).
