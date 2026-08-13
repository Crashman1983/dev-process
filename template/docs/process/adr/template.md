# ADR-NNNN: <title>

## Status

Proposed | Accepted | Superseded by ADR-MMMM | Deprecated | Rejected

## Type

architecture | product | process | invariant

Which kind of decision this is. `architecture` = structure, boundaries,
technology; `product` = scope, positioning, a deliberate non-goal; `process` =
how the team works; `invariant` = a cross-cutting behavioural rule that spans
features and so has no single spec to live in (e.g. "which scope does a turn
inherit?"). One type per record. An `invariant` record additionally carries a
`## Test` section naming its enforcement twin — the table/property test that
pins the whole rule, not one path; the decision-records gate requires it once
the record is Accepted. The third fix on the same behaviour is the signal to
write one (`workflow.md`, Debug).

## Intent

keep | change-planned | tolerated

Endorsement, independent of lifecycle status. `keep` = deliberately endorsed;
`change-planned` = current reality, migration intended (link the follow-up);
`tolerated` = accepted debt, not endorsed, no active migration.

Exactly one Intent per record. A decision that cannot take a single Intent —
part `keep`, part `change-planned` — is more than one decision: split it. The
single value is the forcing function for one-decision-per-record; it is not a
state to blend.

## Context

What forces are at play — technical, product, organizational? What makes this decision
necessary now? State the constraints, not the solution.

## Decision

The choice, in the active voice: "We will …". One decision per ADR.

## Consequences

What becomes easier and what becomes harder as a result. Include follow-up work and
the trade-offs accepted.
