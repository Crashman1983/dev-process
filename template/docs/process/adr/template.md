# ADR-NNNN: <title>

## Status

Proposed | Accepted | Superseded by ADR-MMMM

## Type

architecture | product | process

Which kind of decision this is. `architecture` = structure, boundaries,
technology; `product` = scope, positioning, a deliberate non-goal; `process` =
how the team works. One type per record.

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
