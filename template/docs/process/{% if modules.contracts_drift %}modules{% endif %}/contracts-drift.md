# Module: contracts-drift

Opt-in. Detects **contract drift** — when a service's agreed external interface
(a REST API, a Kafka event schema, …) changes without a deliberate re-pin.
Universal: REST and Kafka ship only as inert examples; you wire your own kinds
and tools.

## When required

Enable when the project depends on, or exposes, an external contract you want
git to guard. A contract is declared one-per-file under
`docs/process/contracts/<id>.json` (the `id` equals the filename stem).

## The contract file

| field | required | meaning |
|---|---|---|
| `id` | yes | slug, equals the filename stem |
| `kind` | yes | free string: `rest`, `kafka`, `graphql`, … (not a fixed list) |
| `artifact` | yes | repo-relative path to a **committed** snapshot of the contract |
| `pin` | yes | the agreed version marker (see below) |
| `verify` | no | a project command that checks live conformance |
| `consumers`, `notes` | no | prose, ignored by the gate |

## Hard vs. best-effort (no false-green)

**Hard (CI fails):** invalid JSON; a missing required field; `id` not equal to
the filename stem; a missing or repo-escaping `artifact`; a **content-hash**
`pin` that no longer matches its artifact.

**Best-effort (advisory note, never fails CI):** an opaque (non-hash) `pin`;
live conformance via `verify`. A `verify` command that reports nonconformance,
cannot be launched, or times out yields a note — never a failed build. External
systems (a live API, a schema registry) must not gate CI; the hard teeth are
the offline integrity check.

## The pin — the drift ratchet

Prefer a content hash for artifacts you control. Compute it and paste it:

    sha256sum contracts/<your-openapi>.json     # -> sha256:<hex>

Now any edit to the artifact that is not accompanied by a re-pin fails CI — a
deliberate acknowledgement that the contract moved. For a schema owned
elsewhere (a registry), use an opaque pin like `registry:<version>`; integrity
then degrades to a note and you lean on `verify`.

## verify — live conformance

`verify` runs as argv (no shell). For env vars or pipes, wrap it yourself:

    sh -c '<your-openapi-diff-or-schema-compat-command>'

Its exit code is advisory: non-zero surfaces a note, it never fails the build.

## Examples

Two inert seeds ship under the contracts directory: `rest-orders.example.json`
(REST, hash pin) and `kafka-order-events.example.json` (Kafka, opaque registry
pin). Copy one, drop the `.example`, and point it at a real committed artifact.
The gate itself is `scripts/process/check_contracts.py`.
