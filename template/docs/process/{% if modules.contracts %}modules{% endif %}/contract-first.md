# Module: contract-first

Opt-in. Enforces the *declared-first* half of Rule 3: a cross-surface capability
(one that several surfaces — web, mobile, CLI — build on) must have its shared
interface **declared in a committed spec before** any surface consumes it. The
gate fails CI when a capability references an interface symbol the spec does not
yet contain.

## When required

Enable when more than one surface depends on the same internal capability and you
want git to guarantee the shared interface exists *before* a surface is wired to
it. A capability is declared one-per-file under
`docs/process/capability-contracts/<capability>.json` (the `capability` value
equals the filename stem, so identity is unique by construction).

## The capability contract

```json
{
  "capability": "chat",
  "surfaces": ["web", "mobile"],
  "spec": "docs/api/openapi.json",
  "symbols": ["ChatMessage", "ChatSession"],
  "notes": "optional free text"
}
```

| field | required | meaning |
|---|---|---|
| `capability` | yes | slug, equals the filename stem |
| `surfaces` | yes | non-empty list of the surfaces that must follow the spec |
| `spec` | yes | repo-relative path to the **committed** shared interface artifact |
| `symbols` | yes | non-empty list of interface / DTO names that must appear in the spec |
| `notes` | no | prose, ignored by the gate; unknown fields are ignored (forward-compat) |

## Hard vs. best-effort (no false-green)

**Hard (CI fails):** invalid JSON; not valid UTF-8; not a JSON object; a missing
or wrongly-typed required field; `capability` not equal to the filename stem; a
`spec` that escapes the repo root or is not a committed file; **any `symbols`
entry that does not occur in the committed spec's text** — the Rule-3 violation
of building on an interface before it is declared.

**Best-effort (advisory note, never fails CI):** whether the named `surfaces`
actually consume the capability is not machine-checkable across arbitrary
codebases, so it is surfaced as a note, never faked as verified. An empty or
absent registry yields "no capability contracts yet".

## The symbol floor — what it does and does not prove

Symbol presence is a word-boundary text search over the committed spec text:
language- and format-agnostic (JSON / YAML / proto / …), honest as a floor — it
proves the name is *present*, and can fail CI when it is not. It deliberately
does not parse the spec structure, which would assume a format. Word boundaries
stop a short name (`get`, `p`) from matching inside another word; a dotted
symbol can still match inside a longer dotted run (`3.0` in `3.0.0`). The gate
enforces *declaration order*, not precise structural conformance.

## One owner per behavior (Rule 4)

This module owns only symbol-presence. It does **not** check artifact drift (a
committed spec matching a freshly generated one) — that is the job of the
`contracts-drift` module; declare your spec there with a hash pin or a verify
command if you want the byte-drift ratchet. It also does not read any
inventory or other module's artifacts, so the two compose without coupling.

## The seed

An inert `capability.example.json` ships under the capability-contracts
directory; the gate skips every `*.example.json`. Copy it, drop the `.example`,
rename the stem to your capability, and point `spec`/`symbols` at your committed
shared interface. The gate itself is
`scripts/process/check_capability_contracts.py`.
