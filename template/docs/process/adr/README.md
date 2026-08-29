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
`adr-0000-record-architecture-decisions.md`) — the gates resolve `ADR-NNNN`
references against exactly this pattern.

**Records are constraints, not concrete.** A decision record binds until it
is deliberately changed — and changing it is a first-class, *welcome* move,
not a defeat: when a different choice makes the solution **durably more
sustainable, technically better, or clearer**, that is by itself sufficient
reason to supersede the record (or sharpen its wording, where only clarity
improves). Two duties keep this honest, and they are the whole bar: name in
the superseding record *what* becomes better and *why that holds long-term*
(not merely "more convenient right now"), and make the change in the same
effort as the code that assumes it (mandatory rule 4) — never as silent
drift the record no longer describes. The same principle applies to
capability contracts: a contract may change for the same reasons, versioned,
with every consumer updated in the same change (`modules/contract-first.md`).
A record nobody may ever touch does not protect the architecture; it dares
people to route around it.

Every new ADR file must be added to the index below in the same change.

The seed record is numbered `0000` so an existing decision corpus that starts
at `0001` can move in without a number collision.

| ADR | Title | Status |
|---|---|---|
| 0000 | Record architecture decisions | Accepted |
