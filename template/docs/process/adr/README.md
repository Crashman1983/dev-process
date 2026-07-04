# Decision Records

A decision record captures one significant, hard-to-reverse decision — the
context, the choice, and its consequences. The decision may be **architectural,
product, or process** (the `Type` axis says which): a structural choice, a scope
boundary, a deliberate "we will not build X", a positioning principle, a
workflow rule. Write one whenever a decision shapes structure, crosses a
boundary, sets product direction, or future contributors would otherwise ask
"why is it done this way?". Use `template.md`.

Records keep the historical filename and reference token `adr-NNNN` / `ADR-NNNN`
(stories, architecture rules, and gates all resolve that token) — the *token*
stays "ADR", the *concept* is a decision record of any type.

Filename convention: `adr-NNNN-<slug>.md` (zero-padded, e.g.
`adr-0001-record-architecture-decisions.md`) — the gates resolve `ADR-NNNN`
references against exactly this pattern.

Every new ADR file must be added to the index below in the same change.

| ADR | Title | Status |
|---|---|---|
| 0001 | Record architecture decisions | Accepted |
