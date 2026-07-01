# SP3 Slice 1 — Feature-Registry Module (Design)

**Status:** Draft (for review) · **Date:** 2026-07-01 · **Supersedes/extends:** none (new opt-in module; extends the SP1 module mechanism, references SP2 ADRs)

## 1. Purpose

SP3 = *„complete the proven Kenni process for a multi-repo environment"* — a small
program of portable opt-in modules, not a cross-repo-contracts special case. This
slice ships the **feature-registry**: the requirements / acceptance-criteria /
test-traceability SSOT that every user-visible behaviour traces to.

It is the **deposit target** the earlier design conversation converged on: when a
scenario is sharpened at onboarding, the concrete requirements — including cross-repo
coupling — land here (a coupling becomes a story with acceptance „consumes billing-api
via OpenAPI, drift-checked"). It is what mandatory-rule *„tests prove acceptance"*
checks against, and the substrate the later slices build on (GitHub-Issues links,
contracts-drift). It mirrors Kenni's `docs/feature-registry/` deliberately — Seb keeps
working the way he does today.

## 2. Scope

**In:** a per-story registry format, a validation gate, an interview/how-to doc,
module wiring, an inert seed. Portable (JSON + a Python check, no network), and
**dogfoodable in dev-process itself** (its own slices become stories).

**Out (later slices / separate modules):**
- Parity / `feature-inventory` (coverage-across-surfaces) → separate module.
- GitHub-Issues binding (backlog, claim/heartbeat, EARS issue templates) → Slice 2;
  here only an **optional `issue` link field** is reserved (forward-compat).
- Generic contracts-drift gate → Slice 3; here only the **coupling-as-story** deposit
  pattern is enabled, no drift mechanics.

### Honest ceiling (carried from SP1/SP2)

Structural well-formedness and reference existence are **hard** (CI exit 1). Whether a
test *semantically* proves its acceptance criterion is **not** mechanically decidable —
the gate verifies that a mapping exists and its targets resolve, and flags missing
mappings; it never claims a criterion is genuinely covered. No false-green.

## 3. The registry format

One story per file — `docs/process/feature-registry/<story-id>.json` — so stories
diff and merge independently (low conflict in multi-repo / multi-author work).

```json
{
  "id": "STORY-0007",
  "title": "Consume billing API",
  "story": "As an order service, when a checkout completes, the system shall post the invoice to billing.",
  "acceptance": [
    {"id": "AC1", "text": "A completed checkout produces exactly one billing POST."},
    {"id": "AC2", "text": "A 4xx from billing marks the order invoice-failed, not lost."}
  ],
  "tests": ["tests/billing/test_post.py::test_one_post_per_checkout"],
  "status": "done",
  "adr": "ADR-0005",
  "issue": "https://github.com/owner/repo/issues/42",
  "links": ["consumes billing-api (OpenAPI), pinned gh:owner/billing@v1.2.0"]
}
```

- **Required:** `id`, `title`, `story`, `acceptance[]` (each with non-empty `text`),
  `status`.
- **Optional:** `tests[]`, `adr`, `issue`, `links[]`.
- **`status` ∈** `proposed | in-progress | done | deprecated`.
- **Unknown fields ignored** (Slice 2/3 forward-compat).

`story` is written in EARS form by convention (role / trigger / „the system shall …"),
**encouraged in the interview, not regex-enforced** — story prose is an open domain
(CLAUDE.md regex-vs-LLM rule: no keyword authority over open text). The gate grades
*structure*, humans/agents grade *wording*.

## 4. Two artifacts (SP1 pattern)

### 4a. Interview / how-to — neutral SSOT + thin adapters

`docs/process/modules/feature-registry.md`: when a story is required (ties to
mandatory-rules „plan before work" + „tests prove acceptance"), how to write a
gradeable EARS acceptance criterion, how to map tests, how a sharpened coupling is
deposited as a story. Placeholder-form example paths only (doc-drift-safe).

### 4b. Registry gate — `scripts/process/check_feature_registry.py`

Reads every `docs/process/feature-registry/*.json`. **Hard (CI exit 1):**

| Check | Rationale |
|---|---|
| valid JSON, required fields present | manifest well-formed |
| `id` matches `STORY-NNNN`, unique across registry | stable, collision-free trace anchor |
| `status` ∈ enum | no silent typo states |
| each `acceptance[].text` non-empty (+ `id`) | acceptance is gradeable, not blank |
| each `tests[]` path resolves to an existing file | a mapped test truly exists |
| `status: done` has ≥1 `tests[]` entry | „done" needs proof (Rule 6) |
| optional `adr` resolves to `docs/process/adr/adr-NNNN-*.md` | reuse SP2's adr-glob; live decision link |

**Best-effort (exit 0, note):**
- a `in-progress`/`done` story whose acceptance count exceeds its mapped test count →
  soft „N acceptance criteria have no mapped test" (missing *mapping* is visible;
  semantic coverage stays a human judgement).

**Empty registry** (module on, no story files) → soft „no stories yet", exit 0 — never
a false-fail before the first story (mirrors SP2's not-onboarded branch).

Registered in `gate_runner` under module key `feature_registry`.

### 4c. Relationship to the mandatory rules

Mandatory-rule „tests prove acceptance" gains a thin pointer: *when the feature-registry
module is installed, acceptance lives in `docs/process/feature-registry/`.* No rule text
duplicated — the anchor points, the module owns the mechanics (same as Rule 3 →
contract-first).

## 5. Wiring, degradation, files

- `copier.yml`: add `feature_registry: false` to `modules.default`.
- New (all gated by `{% if modules.feature_registry %}`):
  - `template/scripts/process/{% if … %}check_feature_registry.py{% endif %}.jinja`
  - `template/docs/process/{% if … %}modules{% endif %}/feature-registry.md.jinja` (…nested under the existing modules dir pattern)
  - a seed story `template/docs/process/{% if … %}feature-registry{% endif %}/STORY-0001.example.json.jinja` — **inert** (`.example.json`, not read by the gate, which globs `*.json` minus `*.example.json`) so the shipped seed never fails.
- `gate_runner.py`: register `feature-registry`.
- Module off → none of the above rendered.
- Tests + conftest: reuse the SP1/SP2 snapshot fixture; add `feature_registry: False` to the conftest module defaults for parity with copier.yml.

## 6. Testing (fixtures + stubs, like SP1/SP2)

module-files present-when-on / absent-when-off · empty-registry soft-OK ·
valid-story OK · missing-required-field hard · duplicate-id hard · bad-status hard ·
test-path-missing hard · done-without-tests hard · adr-missing hard / adr-present pass ·
unknown-field ignored · acceptance-without-test soft-note · gate_runner lists/omits by flag.

## 7. Dogfooding

dev-process adopts its own registry: SP1/SP2/SP3-slices become `STORY-0001…`, their
acceptance = each design's check table, their `tests[]` = the module test files, `adr`
= the relevant decision. Closes the loop — the process proves itself.

## 8. Extension points (later slices)

- **`issue` field → GitHub-Issues module (Slice 2):** populates the link, verifies it
  resolves, generalises Kenni's surface-labels + claim/heartbeat + EARS templates.
  GitHub concrete **by example**; adopters adapt their copy (copier ownership model),
  GitHub listed under README prerequisites.
- **`links` coupling → contracts-drift (Slice 3):** a coupling story gains a generic,
  project-configured `verify`/`fetch` drift check; committed + pinned + integrity-checked
  hard, conformance best-effort.
- **parity / feature-inventory:** separate module.

## Open decisions (resolve in the plan)

1. **JSON vs YAML** for entries — proposed **JSON**, mirrors Kenni; adopters may switch.
2. **one-file-per-story vs single file** — proposed **one file per story** (merge-friendly).
3. **EARS enforcement depth** — proposed: acceptance `text` required + non-empty (hard),
   EARS wording encouraged in the doc, **not** regex-graded (open domain).
4. **`id` scheme** — proposed `STORY-NNNN`; per-repo namespace deferred to Slice 2/SP3
   multi-repo (an optional prefix, forward-compat via ignored fields).
