<!-- Derived from GitHub Spec Kit's spec-template.md (MIT, Copyright GitHub, Inc.) — see THIRD-PARTY-NOTICES.md -->
# Feature Specification: [FEATURE NAME]

**Created**: [DATE] · **Status**: Draft · **Input**: User description: "$ARGUMENTS"

*(dev-process override: acceptance is authored in EARS — the grammar the
issue gates read — and every story carries the DoR-R2 twins. Constraints
first: read `PRODUCT.md` and the decision records for the touched area; a
spec that violates a non-goal or an Accepted decision says so and does not
proceed silently. Mark anything underspecified as
`[NEEDS CLARIFICATION: question]` instead of guessing — the clarification
gate blocks unresolved markers from reaching plan.md/tasks.md.)*

## Owner brief — plain language *(mandatory, first)*

<!-- Five sentences, no jargon, no file names, no process vocabulary.
     Written for the product owner, who must be able to steer HERE without
     reading further. This block leads the staged issue comment — it is the
     owner's influence window. -->

1. **What**: [what will exist that does not exist today — one sentence]
2. **Why**: [whose problem it solves, and what it costs to leave unsolved]
3. **Visible change**: [what the user will see or do differently]
4. **Risk**: [the one thing most likely to be wrong or regretted later]
5. **Your call**: [the decision(s) only the owner can make — or "none"]

## User Scenarios & Testing *(mandatory)*

<!-- Stories are PRIORITIZED, independently testable slices: implementing
     only US1 must yield a viable MVP. -->

### User Story 1 — [title] (Priority: P1)

[User journey in plain language]

**Why this priority**: [value]

**Independent test**: [how this slice is validated on its own]

**Acceptance criteria (EARS)** — including the negative, edge,
authorization, and invalidation/cleanup twins (DoR R2,
`docs/process/definition-of-ready-and-done.md`):

- AC-1: When [trigger], the system shall [response].
- AC-2: When [invalid input / unauthorized caller / cleanup case], the
  system shall [safe response].

### User Story 2 — [title] (Priority: P2)

(same shape)

### Surface states *(mandatory for any story with a UI surface)*

Every surface the story touches names its **four states**, one expected
behaviour each — the DoR-R2 edge twins, concretized for UI. "Unknown" is
the one that ships broken when unnamed: not-yet-resolved is neither empty
nor error, and a surface that reads it as "empty" invents data loss.

| state | expected behaviour |
|---|---|
| loading | [what the user sees while nothing is known yet] |
| empty | [a true empty stock — and the way out of it] |
| error | [failure named, retry offered] |
| unknown / not yet resolved | [never rendered as empty; what instead] |

### Edge cases

- What happens when [boundary condition]?

## Requirements *(mandatory)*

- **FR-001**: The system MUST …
- **FR-002**: The system MUST … [NEEDS CLARIFICATION: …]

### Key entities *(if the feature involves data)*

- **[Entity]**: [what it represents — no implementation]

## Success Criteria *(mandatory — measurable, technology-agnostic)*

<!-- SCs answer "was the RIGHT problem solved?" — ACs only prove the
     solution behaves as designed. Every SC-ID survives the merge: evidenced
     at review, converted into a tracked measurement follow-up, or
     explicitly waived (the publish-and-prune ritual accounts for them). -->

- **SC-001**: [measurable outcome, e.g. "users complete X in under N minutes"]
- **SC-002**: [business/user metric]

## Constraints read

Decision records and `PRODUCT.md` entries read as constraints — or "none
apply"; a design overturning an endorsed decision names the supersession
(mandatory rule 4).

## Assumptions

- [Named assumption chosen where the description was silent]
