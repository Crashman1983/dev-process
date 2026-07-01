# SP4-② `contract_first` module — design

**Status:** Accepted · **Target tag:** v0.7.0 · **Date:** 2026-07-01

## 1. Problem / motivation

Mandatory Rule 3 (contract-first) says a cross-surface capability must have its
shared interface declared *before* any surface (web/mobile/CLI) builds on it.
Kenni enforces the two halves of Rule 3 separately:

- **Artifact drift** (`make openapi-diff`, hard/pre-push): the committed API spec
  must match the freshly generated one.
- **Coverage drift** (`_contract_coverage_drifts`, warn): a capability marked
  *built* in the inventory whose contract section is still provisional/missing.
- **story-first** (the other half of Rule 3) — already owned by the
  `feature_registry` module.

## 2. Scope decision (Rule 5 — one owner per behavior)

The **artifact-drift** half is *mechanically identical* to what the shipped
`contracts_drift` module already owns: a committed spec artifact + a
regenerate-`verify` command + a content-hash pin. Re-shipping a second drift
mechanism here would be two owners for one behavior. **So `contract_first` does
NOT check artifact drift** — a project that wants "committed spec == generated"
declares its spec as a `contracts_drift` contract (artifact + `verify: "<regen
cmd>"`).

`contract_first` owns the **distinct, still-hard** assertion that artifact-drift
does not make: **a declared capability's interface symbols must already exist in
the committed shared spec** — the "declared first" in contract-first. A contract
that references a DTO not yet in the spec is a Rule-3 violation and fails CI.

Kenni's coverage-drift bridges `feature-inventory.md` ↔ `contracts.md`. That
cross-references the *parity* surface (SP4-③). Modules must not import each
other (Rule 5), so `contract_first` is **self-contained** and does not read the
inventory; the inventory↔contract status bridge, if wanted, belongs to whichever
module owns the inventory. This is a deliberate, documented divergence from
Kenni's exact mechanism — the portable, hard core is symbol-presence.

Distinct from siblings: `feature_registry` = story→acceptance→tests (behavior
traceability); `contracts_drift` = external-system coupling by artifact+pin
(byte-drift ratchet); `contract_first` = internal cross-surface capability →
shared interface declared-first (symbol presence). Three axes, no overlap.

## 3. Artifact

One capability contract per file under
`docs/process/capability-contracts/<capability>.json`:

```json
{
  "capability": "chat",
  "surfaces": ["web", "mobile"],
  "spec": "docs/api/openapi.json",
  "symbols": ["ChatMessage", "ChatSession"],
  "notes": "optional free text"
}
```

- `capability` (string, == filename stem → uniqueness by construction)
- `surfaces` (non-empty list of strings — the surfaces that must follow the spec)
- `spec` (string — path to the committed shared interface artifact, in-repo)
- `symbols` (non-empty list of strings — interface/DTO names that must appear in
  the committed spec before surfaces build on them)
- `notes` (optional string; unknown fields ignored = forward-compat)

Inert seed `*.example.json` (gate skips `.example.json`, like the sibling gates).

## 4. Honest ceiling

**HARD (CI exit 1):**
- valid JSON object; unreadable/non-UTF-8/non-object → fail (mirror the
  `contracts_drift` hardening class).
- required fields present + correctly typed: `capability` non-empty string ==
  filename stem; `surfaces` non-empty list of non-empty strings; `spec` non-empty
  string; `symbols` non-empty list of non-empty strings.
- `spec` resolves to a committed file strictly inside the repo root (escape-guard
  via `resolve()` + `root in resolved.parents`, reused from `contracts_drift`).
- **every symbol string occurs in the committed spec's text** — the declared
  interface exists. A missing symbol → fail: "declared before the interface
  exists" is the Rule-3 violation.

**BEST-EFFORT (note, exit 0 — never faked as verified):**
- whether the named `surfaces` actually consume the capability is not verifiable
  across arbitrary codebases → informational note only.
- empty/absent registry → "no capability contracts yet".

Symbol presence is a substring search over the committed spec text: language- and
format-agnostic (JSON/YAML/proto/…), honest as a floor ("the name is present"),
and CI-failable. We do not parse the spec structure — that would assume a format.

## 5. Wiring (identical to prior slices)

- `copier.yml` → `modules.default` gains `contract_first: false`.
- `gate_runner.py` `GATES` gains
  `"contract-first": ("contract_first", [sys.executable, "scripts/process/check_capability_contracts.py", "."])`.
- `tests/conftest.py` modules-defaults dict gains `"contract_first": False`.
- Module doc `docs/process/{% if modules.contract_first %}modules{% endif %}/contract-first.md`.
- README module catalog + roadmap + status/tag → v0.7.0.
- Path-conditional gate file
  `template/scripts/process/{% if modules.contract_first %}check_capability_contracts.py{% endif %}.jinja`.

## 6. Neutrality & verification

No Kenni terms in any shipped file (neutrality test list). Real `vcs_ref=HEAD`
copier render verified on + off. doc-drift green with the module doc present.

## 7. Risks

- **Contrived-gate risk:** mitigated — symbol-presence is a genuinely distinct,
  useful hard assertion (catches a contract that references a DTO the spec does
  not yet declare), not a re-skin of artifact-drift.
- **Substring false-positive:** a symbol name that is a common substring could
  match spuriously. Accepted: the gate is a floor that enforces *declaration
  order*; precise structural matching would require assuming the spec format.
  Documented in the module doc.
