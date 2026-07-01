# SP3 Slice 3 — contracts-drift module — Design

Status: proposed · Date: 2026-07-01 · Supersedes: — · Depends on: SP3 Slice 1
(feature-registry, v0.3.0), Slice 2 (github-issues, v0.4.0)

## 1. Purpose

A generic, opt-in gate that detects **contract drift** — when a service's
agreed external interface (a REST API, a Kafka event schema, …) changes without
a deliberate re-pin. The design is **universal**: no target environment is
assumed. REST and Kafka are the two exemplar contract *kinds* that prove the
generic model works; adopters adapt their copier copy to their own kinds and
tools.

The gate answers one question mechanically and honestly: *has a committed
contract artifact changed since it was last pinned?* — and, where the project
supplies the means, surfaces whether the live interface still conforms.

## 2. Scope & the honest ceiling

| Concern | Guarantee | Mechanism |
|---|---|---|
| Contract file is valid + well-formed | **Hard** (exit 1) | JSON parse, required fields non-empty, `id` unique + = filename stem |
| The pinned artifact is committed | **Hard** (exit 1) | `artifact` path exists under repo root |
| Artifact changed without re-pin (drift) | **Hard** (exit 1) | if `pin` is a content hash → recompute over artifact bytes, fail on mismatch |
| Pin is a non-hash opaque marker | Best-effort (note) | cannot recompute → note, integrity not machine-checkable |
| Live conformance (API/schema matches) | Best-effort (note) | project-supplied `verify` command; absent or unlaunchable → note |
| Empty / absent contracts dir | Best-effort (note) | "no contracts yet" — exit 0 |

**No false-green.** The gate never claims a contract conforms unless the project
gave it the means to check, and never fails on something it cannot mechanically
prove.

## 3. Module shape & deposit point

- Module key **`contracts_drift`**, default `false` (like the other three
  opt-in modules).
- One contract per file: **`docs/process/contracts/<id>.json`** (mirrors the
  one-file-per-story shape of feature-registry).
- Inert seeds **`<id>.example.json`** are skipped by the gate (same convention
  as feature-registry's `*.example.json` and arch-onboarding's `arch-example`
  fence) — the module renders green before a real contract is authored.
- Gate **`check_contracts.py`**, registered in the manifest `gate_runner`
  GATES dict, in `copier.yml` `modules.default`, and in the README module
  catalog.
- **Independent module.** No dependency on feature-registry or arch-onboarding
  being enabled. The feature-registry `links` field *may* name a contract `id`
  as a soft prose pointer ("consumes orders-api"), but neither gate validates
  that cross-reference — no hard coupling, no module import (Rule 4).

## 4. Contract schema

One JSON object per file:

```json
{
  "id": "orders-api",
  "kind": "rest",
  "artifact": "contracts/orders.openapi.json",
  "pin": "sha256:ab12…",
  "verify": "npx openapi-diff contracts/orders.openapi.json $LIVE_URL",
  "consumers": ["billing", "shipping"],
  "notes": "Owned by the orders team; breaking changes need a new /v2 path."
}
```

- **`id`** (required, string, non-empty) — unique across all contract files and
  equal to the filename stem (`orders-api.json` → `"orders-api"`). Hard.
- **`kind`** (required, string, non-empty) — free string (`rest`, `kafka`,
  `graphql`, …). **Open domain, not enum-enforced** — universality over a
  closed list (consistent with EARS not being regex-enforced in Slice 1).
- **`artifact`** (required, string) — repo-relative path to a **committed**
  representation of the contract. *Opinionated stance:* a contract in
  dev-process is a committed snapshot plus a pin. The live source (a running
  API, a schema registry) is authoritative at runtime; the committed artifact
  is the diffable, review-able, git-versioned pinned state. This is what makes
  drift visible in git at all. Hard: the path must exist.
- **`pin`** (required, string, non-empty) — the agreed version marker. If it
  matches a content-hash form (`sha256:<hex>`, `sha512:<hex>`, `sha1:<hex>`)
  the gate recomputes it over the artifact bytes (hard drift check). Any other
  value (`registry:v3`, a git ref, a semver) is treated as opaque → best-effort
  note.
- **`verify`** (optional, string) — a project-supplied shell command that
  checks live conformance. Advisory (see §5).
- **`consumers`**, **`notes`** (optional) — prose, forward-compat; ignored by
  the gate.

Unknown fields are ignored (forward-compat), matching Slice 1.

## 5. The honest ceiling — hard vs best-effort (the crux)

**Hard (exit 1) — mechanically guaranteed, no external tool:**

1. File is valid JSON and a dict (malformed → hard).
2. `id`, `kind`, `artifact`, `pin` present and non-empty strings.
3. `id` unique across contract files and equal to the filename stem.
4. `artifact` resolves to an existing file under the repo root (committed).
5. **Drift ratchet:** if `pin` is a recognised content hash, recompute the hash
   over the artifact bytes; a mismatch is hard — "artifact changed but pin not
   updated; re-pin deliberately." This forces every contract change to be a
   conscious act (updating the pin acknowledges the interface moved). It is
   deterministic, self-contained, and works for **any** committed artifact
   regardless of kind — the universal core of the gate.

**Best-effort (note, exit 0) — never fakes a green:**

- `pin` is opaque (not a content hash) → "integrity of `<id>` not
  machine-checkable from an opaque pin; supply a `sha256:` pin or a `verify`
  command."
- `verify` absent → "conformance of `<id>` not machine-verified — no verify
  command."
- `verify` present but the command **cannot be launched** (command-not-found /
  `OSError` / timeout) → "could not run verify for `<id>`."
- `verify` present, **launches, and reports non-zero** → **note, exit 0**
  ("verify for `<id>` reported possible nonconformance").

**Resolved decision (the §3 open question):** a launched `verify` that reports
non-zero is **advisory (soft)**, not a hard failure. Rationale: a contract
`verify` command inherently reaches an **external** system — a live API, a
schema registry — whose flakiness (network, auth, transient 5xx) must not gate
CI. The hard teeth live in the **integrity/pin** check, which is deterministic
and offline. This is a principled divergence from arch-onboarding, where the
conformance tool is a *local static* linter (import-linter / dependency-cruiser)
that is deterministic, so there a present-tool violation is hard. Here
conformance is inherently external, so it is honest to keep it advisory. A
`verify` command is a timeout-capped subprocess (like the Slice 2 `gh` call).

## 6. Artifacts (rendered files)

All gated by `{% if modules.contracts_drift %}`:

- `template/scripts/process/{% if modules.contracts_drift %}check_contracts.py{% endif %}.jinja`
  — the gate. Stdlib + hashlib only; no third-party dependency.
- `template/docs/process/{% if modules.contracts_drift %}contracts{% endif %}/rest-orders.example.json`
  — inert REST exemplar (sha256 pin, OpenAPI artifact, optional openapi-diff verify).
- `template/docs/process/{% if modules.contracts_drift %}contracts{% endif %}/kafka-order-events.example.json`
  — inert Kafka exemplar (committed `.avsc`, pin, optional schema-compat verify).
- `template/docs/process/{% if modules.contracts_drift %}modules{% endif %}/contracts-drift.md`
  — module doc: schema, hard/best-effort split, REST + Kafka wiring, the
  committed-copy-vs-registry pattern, how to compute a `sha256:` pin.

Modified: `copier.yml` (`contracts_drift: false` in `modules.default`),
`template/scripts/process/gate_runner.py.jinja` (register `contracts-drift`),
`README.md` (module catalog), `tests/conftest.py` (defaults dict).

## 7. Wiring & degradation

- `gate_runner` GATES entry:
  `"contracts-drift": ("contracts_drift", [sys.executable, "scripts/process/check_contracts.py", "."])`.
- Manifest-aware: runs only when `contracts_drift` is active in
  `.copier-answers.yml`.
- Degradation ladder, all exit 0 with a note: no contracts dir / empty dir →
  "no contracts yet"; opaque pin → integrity note; no verify → conformance
  note; unlaunchable verify → could-not-run note.
- Only structural/integrity defects (§5 hard list) ever exit 1.

## 8. REST + Kafka exemplars (inert)

Two `.example.json` seeds render into `docs/process/contracts/` and are skipped
by the gate (the `.example.json` suffix, same rule as Slice 1). They exist to
show the model spans both kinds without any adapter code:

- **rest-orders.example.json** — `kind: "rest"`, `pin: "sha256:…"`,
  `artifact: "contracts/orders.openapi.json"`,
  `verify: "npx openapi-diff …"`. Demonstrates the hard hash ratchet on a
  committed OpenAPI file.
- **kafka-order-events.example.json** — `kind: "kafka"`,
  `artifact: "contracts/order-created.avsc"`, `pin: "registry:v3"` (opaque →
  integrity note), `verify: "… schema-registry compatibility check …"`.
  Demonstrates the registry case: the committed `.avsc` is the pinned snapshot,
  the opaque `pin` degrades integrity to a note, and conformance is delegated to
  the project's registry-compat `verify`.

The module doc explains both, plus how to produce a `sha256:` pin
(`sha256sum`/`shasum`) and when to prefer a committed hash pin (files you
control) over an opaque registry pin (schemas owned elsewhere).

## 9. Testing

`tests/test_contracts_drift.py`, PATH-stub pattern for `verify` (as Slice 2
stubbed `gh`). Cases:

- **Render on/off:** artifacts present when on; absent + leak-free when off;
  neutrality (no project-specific term leaks); `gate_runner --list` includes /
  excludes `contracts-drift`.
- **Hard:** missing required field; missing `artifact` file; `id` ≠ filename
  stem; duplicate `id` across files; malformed JSON; sha256 pin **mismatch**
  after editing the artifact.
- **Best-effort (exit 0 + note):** valid sha256 pin **match** (no note);
  opaque pin → integrity note; no `verify` → conformance note; `verify` that
  cannot launch (empty PATH / nonexistent command) → could-not-run note;
  `verify` that launches and returns non-zero → soft note, **exit 0** (the
  must-not-hard-fail guard for conformance); `verify` returns zero → no note.
- **Seeds:** `.example.json` files are skipped (no false failure from the
  inert exemplars).
- **doc-drift:** with both modules on, the module doc's path refs resolve.

Tests map to the §5 hard/best-effort contract; the two must-not-hard-fail
guards (unlaunchable verify, non-zero verify) are the load-bearing assertions.

## 10. Dogfooding

Deferred, consistent with SP1/SP2/Slice1/Slice2: dev-process does not render
itself; the test suite is the proof. (Adding a real `docs/process/contracts/`
to dev-process would be a separate, later choice.)

## 11. Extension points

- **More kinds** — `kind` is a free string; a project adds `graphql`, `grpc`,
  `asyncapi` with no gate change. The hard hash ratchet is kind-agnostic.
- **Verify adapters** — intentionally *not* shipped (universality over
  batteries). A project wires its own `verify` command; a future slice or an
  adopter could add reference adapters (openapi-diff, schema-registry-compat)
  as a separate opt-in without touching this gate.
- **Kafka is no longer deferred** — it is a first-class exemplar here. What
  stays open is only the *adapter* choice, which is correctly a per-project
  `verify` command, not a template concern.

## 12. Open decisions (resolved)

- **Conformance verify hard-vs-soft** → **soft/advisory** (§5). External
  systems must not gate CI; integrity/pin carries the hard teeth. (Seb, "ok".)
- **`artifact` required** → yes; a contract is a committed snapshot + pin
  (§4). A registry-only contract still commits a snapshot `.avsc`/spec.
- **`kind` enum** → no; open domain for universality (§4).
- **Contract home** → standalone `contracts_drift` module, not feature-registry
  `links` nor an arch `external:` slot (§3). (Seb, chosen.)
