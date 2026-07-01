# SP2 — Brownfield Architecture Onboarding + Verification (Design)

**Date:** 2026-07-01
**Status:** approved-for-planning
**Builds on:** `docs/design/2026-07-01-foundation-design.md` (SP1 Foundation, §9 SP2 extension point)

## 1. Purpose

SP1 shipped a portable process (neutral SSOT + CI enforcement + thin harness adapters).
It deliberately does *not* capture or verify a brownfield project's architecture — the
part Seb flagged as the hard, missing piece: "Architekturvorgaben gezielt abgefragt und
gegen echten Code geprüft."

SP2 adds one opt-in module, **`arch-onboarding`**, that:

1. **Elicits** a repo's architecture through a structured interview (an agent walks a
   human through it), producing a machine-readable manifest plus human narrative.
2. **Verifies** the machine-checkable claims of that manifest **against the real code**
   on every CI run, as a gate.

## 2. Scope and the SP2/SP3 boundary

**SP2 covers the *own* repo only.** Layers, paths, invariants, and interfaces of the
repository the module is installed in. That is the focus decision: architecture capture
is per-repo.

Other repositories are attached via interfaces. Capturing and knowing *their* contracts
(cross-repo contract inventory + governance) is **SP3** and lives there. SP2's manifest
therefore has **no `external:` section** — no half-built, unverified cross-repo feature
ships in SP2.

**Forward-compat hook (not a feature):** the arch-gate checker tolerates unknown
top-level manifest keys and ignores them. SP3 can add `external:` / `contracts:` via
`copier update` without breaking the SP2 gate. This is the anchored extension point.

### Honest ceiling (carried from foundation §9, now wired in code)

- **Existence / location** (does `src/domain/` exist? is `OrderPort` present in
  `ports.py`?) is mechanically decidable and **portably guaranteed** — hard CI failure.
- **Layering conformance** ("domain never imports infra") requires a language-specific
  arch-linter or agent judgment. It is **best-effort, not portably guaranteed**: the gate
  runs a present arch-linter and fails on violations; with no linter it degrades to an
  agent-review checklist + report, non-blocking.

SP2 does not attempt portable semantic conformance. It makes the ceiling explicit and
degrades transparently rather than pretending.

## 3. The manifest — a fenced `arch` block in ARCHITECTURE.md

The machine-checkable claims live in a single fenced ` ```arch ` YAML block **inside the
human anchor `ARCHITECTURE.md`**. One file, one anchor (Mandatory Rule 2: Anchor =
CLAUDE.md + PRD + ARCHITECTURE.md), no cross-file drift. The gate parses only the block;
the surrounding prose is human narrative.

````markdown
# Architecture

Domain encapsulates business logic; infra holds adapters and IO. Domain must never
depend on infra.

```arch
code_roots: [src]
layers:
  domain: {path: src/domain}
  app:    {path: src/app}
  infra:  {path: src/infra}
rules:
  - {forbid: domain -> infra, adr: ADR-0007}   # decided → traceable to an ADR
interfaces:
  - {name: OrderPort, path: src/domain/ports.py}
```
````

**Schema (SP2):**

| Key | Meaning | Verified how |
|---|---|---|
| `code_roots: [str]` | directories holding this repo's code | each path must exist (hard) |
| `layers: {name: {path}}` | named architectural layers → location | each `path` must exist (hard) |
| `rules: [{forbid: "A -> B", adr?}]` | layering invariants; `A`/`B` are layer names; optional `adr:` links the decision record (§4c) | conformance best-effort (§4); if `adr` present, referenced ADR file must exist (hard) |
| `interfaces: [{name, path}]` | key interface/contract symbols in this repo | `path` file exists (hard) + `name` present as text in that file (hard) |

Unknown top-level keys are ignored (SP3 forward-compat). `rules` referencing a layer name
not in `layers` is a manifest error (hard) — a claim that cannot be evaluated.

## 4. Two artifacts

### 4a. Interview (elicitation) — neutral SSOT + thin adapters (SP1 pattern)

- **`docs/process/modules/arch-onboarding.md`** — the neutral questionnaire and manifest
  schema reference. Harness-agnostic; any agent follows it. It walks a human through:
  code_roots, layers→paths, invariants (`rules`), local interface symbols. Output = the
  `arch` block + narrative written into `ARCHITECTURE.md`, plus a scaffolded ADR for each
  invariant the human confirms as a real decision (§4c), linked back via `rules[].adr`.
- **Thin harness pointers** — a Claude slash-command pointer and (when `harnesses.copilot`)
  a Copilot prompt-file, each pointing at the neutral questionnaire. Byte-identical intent,
  same kernel discipline as SP1's adapters. No methodology duplicated in the adapters.
- **`ARCHITECTURE.md` seed** — the module ships a seed `ARCHITECTURE.md` with the schema
  shown under an **inert** ` ```arch-example ` fence + a narrative scaffold, so a brownfield
  project has a concrete starting point. The gate matches **only** an exact ` ```arch `
  fence, so the seed example is inert: the repo reads as "not onboarded" (§5, exit 0) until
  the interview replaces the example with a real ` ```arch ` block. This is why the seed
  cannot false-fail against example paths that do not exist in the target repo.

### 4b. Arch-gate (verification) — `scripts/process/check_architecture.py`

Registered in `gate_runner` under the `arch-onboarding` module. Parses **only** the
`arch` block from `ARCHITECTURE.md`, then:

| Claim | Check | On violation |
|---|---|---|
| `code_roots[]`, `layers.*.path` | path exists (dir or file) | **exit 1 (hard)** |
| `interfaces[].path` | file exists | **exit 1 (hard)** |
| `interfaces[].name` | symbol appears as text in the file (language-agnostic substring/word-boundary match) | **exit 1 (hard)** |
| `rules[] forbid: A -> B` | arch-linter present (`.importlinter` / `setup.cfg [importlinter]` / `.dependency-cruiser.{js,json,cjs}`)? run it, fail on violation | linter present: **hard** · **no linter: agent-review checklist + report, exit 0** |
| `rules[].adr` (if present) | referenced ADR file exists under `docs/process/adr/` | **exit 1 (hard)** |
| unknown top-level keys | ignored (SP3) | — |
| `rules` names a layer absent from `layers` | manifest inconsistency | **exit 1 (hard)** |

The honest ceiling is thereby *in code*, not merely asserted: existence guaranteed,
conformance as hard as the environment allows, degrading transparently. Note the gate
checks only that a linked ADR *exists* — never its `Status`/`Intent` content (§4c). ADR
*semantics* stay human-owned; the gate guarantees traceability, not judgment.

**Symbol match** is deliberately language-agnostic — a word-boundary text search for
`name` within the interface file. It proves the symbol is declared somewhere in the named
file without parsing every language's AST. False-negative risk (symbol built dynamically)
is accepted and documented; the interview guides authors to name real, greppable symbols.

**Conformance runner** detects a known arch-linter by config-file presence and invokes it
as a subprocess, surfacing its exit code. It never *generates* linter config (that would
be per-language SP-scope creep and was explicitly rejected — best-effort, not hard). With
no linter, each `rule` becomes a checklist line in the report ("verify manually / via
agent: domain -> infra forbidden") and the gate stays green.

### 4c. Architecture decisions (ADRs) from onboarding

The manifest captures *structure* (what/where). An architecture also embodies
*decisions* (why + status). Onboarding bridges the two — but only for genuine decisions,
not every fact.

- **Derived from decisions, not facts.** Each invariant (`rule`) and each significant
  technology/pattern choice the human confirms as a deliberate decision gets a retroactive
  ("as-built") ADR from the existing `docs/process/adr/template.md`. A layer's *path* is a
  fact and stays manifest-only; "domain must not depend on infra" is a *decision* and earns
  an ADR. Deriving an ADR per path would be noise; per decision it is signal.
- **Human-ratified in the interview.** For each candidate the human chooses: *accept* (a
  real, endorsed decision → ADR), *not a decision* (incidental → no ADR, stays a manifest
  fact), or *change intended* (ADR with `Intent: change-planned`). The agent never
  auto-accepts a decision on the human's behalf.
- **Two-axis ADR record.** Onboarding populates two independent axes:
  - **Status** (lifecycle, canonical): `Proposed | Accepted | Superseded`.
  - **Intent** (endorsement): `keep | change-planned | tolerated`. `keep` = deliberately
    endorsed; `change-planned` = documents current reality, migration intended (link the
    follow-up issue / a Proposed successor ADR); `tolerated` = accepted debt, not endorsed,
    no active migration. This makes the brownfield reality visible at a glance instead of
    hiding change-intent in prose.
- **Core template extension (one convention, not a fork).** The `Intent` axis is added to
  the *core* `docs/process/adr/template.md` — every project gets one ADR convention. It is
  a small, universally-useful distinction (endorsed vs. tolerated); the arch-onboarding
  module simply *populates* it for as-built ADRs. No module-specific ADR variant.
- **Traceability, not judgment.** A `rule` may carry `adr: ADR-NNNN`; the gate checks that
  file exists (§4b, hard). This enforces one owner per enforced invariant. The gate never
  reads the ADR's `Status`/`Intent` — that is human-owned metadata. (A future check —
  "a `Superseded` ADR still enforced by a live rule is drift" — is an explicit extension
  point, §8, deliberately out of SP2's existence-only ceiling.)

## 5. Wiring, degradation, files

- **`copier.yml`**: add `modules.arch_onboarding` (bool, default `false`).
- **`gate_runner`**: add `arch-onboarding` → `check_architecture.py`; active only when the
  answer is on. The manifest-aware CI mechanism from SP1 already carries this — no runner
  redesign.
- **doc-drift-gate interplay**: if `doc_drift_gate` is also on, it watches the
  `ARCHITECTURE.md` *prose* for dead local paths; the `arch` block is additionally
  hard-checked by `check_architecture.py`. Complementary, not duplicate: drift-gate =
  prose path liveness, arch-gate = structural claims vs. code. The two modules are
  independent (either can be on without the other).
- **Degradation (no false green, no false block):**
  - Module on, but no `ARCHITECTURE.md` **or** no exact ` ```arch ` block (e.g. seed still
    carries only the inert ` ```arch-example ` fence / interview not yet run) → gate prints
    "architecture not onboarded yet" and **exit 0**. Not onboarded is a real state, not a
    failure; but it is reported, not silently passed.
  - Module on, `arch` block present → full verification per §4b.
- **New template files** (all gated by `{% if modules.arch_onboarding %}`):
  - `scripts/process/{% if modules.arch_onboarding %}check_architecture.py{% endif %}.jinja`
  - `docs/process/{% if modules.arch_onboarding %}modules{% endif %}/arch-onboarding.md.jinja`
    (shares the conditional `modules` dir-segment with doc-drift-gate — both render into it)
  - `{% if modules.arch_onboarding %}ARCHITECTURE.md{% endif %}.jinja` (the seed)
  - Claude command pointer + conditional Copilot prompt-file pointer.
- **One core file edited (not gated):** `docs/process/adr/template.md` gains the `## Intent`
  axis (§4c). This ships to every project — one ADR convention — independent of whether
  `arch_onboarding` is enabled.

## 6. Testing

pytest, rendered against real fixture trees (SP1 harness: `render` / `render_into`):

- existence fail: a `layers.*.path` that does not exist → gate **exit 1**.
- interface symbol missing: file exists but `name` absent → **exit 1**.
- conformance with linter: seed a fake `.importlinter` + a stub linter that exits non-zero
  → gate **exit 1**; stub that exits zero → gate green.
- conformance without linter: `rules` present, no linter config → report lists each rule,
  **exit 0**.
- manifest inconsistency: `rules` names an unknown layer → **exit 1**.
- forward-compat: manifest carrying an unknown `external:` key → key ignored, existing
  checks still run, **exit 0** on an otherwise-clean tree.
- degradation: module on, no `arch` block → "not onboarded", **exit 0**.
- seed as shipped: the rendered `ARCHITECTURE.md` seed (inert ` ```arch-example ` fence,
  no live ` ```arch ` block) → "not onboarded", **exit 0** — the seed never false-fails.
- adr link existence: a `rule` with `adr: ADR-0007` and no such file → **exit 1**; with
  the file present → gate passes that check.
- adr link ignored when absent: `rules` without `adr:` never trigger an ADR-existence
  check (the field is optional).
- core ADR template: rendered `docs/process/adr/template.md` carries the `## Intent` axis
  with `keep | change-planned | tolerated` (guards §4c; independent of the module answer).
- module off: gate inert, not listed by `gate_runner --list`, runner exits 0.
- brownfield drop-in: applying the module to a repo with an existing `ARCHITECTURE.md`
  is additive / prompts on conflict (SP1 non-destructive guarantee holds).

## 7. Out of scope (SP2)

- Cross-repo contract capture / inventory / governance → **SP3** (the `external:` schema
  extension, cross-repo drift, multi-human coordination).
- Auto-generating arch-linter configuration for any language.
- Portable semantic conformance without a linter (impossible; agent-review is the
  documented fallback).
- Verifying that the narrative prose *matches* the `arch` block semantically (the block is
  authoritative for structure; prose is explained rationale).

## 8. Extension points (beyond SP2)

- **ADR status-consistency check** — a `rule` whose linked ADR is `Superseded` (or `Intent:
  change-planned` long past its follow-up) is drift: a dead decision still enforced. This is
  mechanically checkable (parse the ADR's Status/Intent line) but is deliberately **out of
  SP2** — it crosses the existence-only ceiling into ADR semantics. A future
  `arch-onboarding` increment or a dedicated module can add it.
- Manifest: `external.repos[]`, `external.contracts[]` — captured by an extended interview,
  the checker already tolerates the keys (→ SP3).
- Cross-repo contract SSOT builds on the (future) `contract-first` module (→ SP3).
- `copier update` version-pin remains the governance lever across N repos (→ SP3).
