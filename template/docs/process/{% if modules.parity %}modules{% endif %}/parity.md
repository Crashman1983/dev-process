# Module: parity

Opt-in. Enforces surface parity: a living
capability×surface matrix that prevents **silent capability loss** — the failure
mode where a UI shell is rewritten and features quietly disappear because no
artifact tracked which surface was supposed to have them. The gate fails CI when
a deliberate gap is not linked to a tracking issue, when a status is invalid, or
(when you declare your surfaces) when a capability omits one of them.

## When required

Enable when the same capability is meant to reach more than one surface (web,
mobile, CLI, …) and you want git to record which surface can do what — and to
fail CI on any deliberate gap that is not issue-linked. A capability is declared
one-per-file under `docs/process/parity/<capability>.json` (the `capability`
value equals the filename stem, so identity is unique by construction).

## The parity entry

```json
{
  "capability": "chat",
  "surfaces": { "web": "complete", "mobile": "gap", "cli": "na" },
  "issues": { "mobile": "#42" },
  "notes": "optional free text"
}
```

| field | required | meaning |
|---|---|---|
| `capability` | yes | slug, equals the filename stem |
| `surfaces` | yes | non-empty object mapping surface name → status |
| `issues` | for each `gap` | maps a gapped surface → its tracking issue ref |
| `notes` | no | prose, ignored by the gate; unknown fields are ignored (forward-compat) |

### Status enum

Each surface carries exactly one status: `complete` (implemented and visible),
`view` (renders but the actions are incomplete), `code` (backend/logic exists,
no surface yet), `gap` (a deliberate, tracked absence) or `na` (not applicable to
this surface). A `gap` — and only a `gap` — needs a matching entry in `issues`
whose value is a valid issue reference: one of `#N`, `owner/repo#N`, or a GitHub
issue URL. This mechanizes the discipline that every deliberate gap links to a
tracking issue.

## Declared surfaces (exact coverage)

The optional `parity_surfaces` answer (a copier question, e.g. `[web, mobile,
cli]`) is the project's canonical surface list. When it is a non-empty list, every
capability file's `surfaces` keys must cover **exactly** that set: a missing
surface is a silent omission (the precise failure this module prevents), an
unknown surface is a typo. When `parity_surfaces` is empty (the default) — or
malformed (not a list of strings), which degrades the same way rather than
crash — coverage is not enforced: surfaces are free-form and only status/gap
validity applies. The gate reads the answer from `.copier-answers.yml` at
runtime.

## Hard vs. best-effort (no false-green)

**Hard (CI fails):** invalid JSON; not valid UTF-8; not a JSON object; a missing
or wrongly-typed `capability`/`surfaces`; `capability` not equal to the filename
stem; a status outside the enum; a `gap` surface without a valid issue ref; and,
when `parity_surfaces` is declared, a missing or unknown surface.

**Best-effort (advisory note, never fails CI):** a `complete` status carries no
machine-checkable code proof, so it is surfaced as a note ("code proof is
review-enforced, not machine-checked") and never faked as verified — deciding
whether a capability is truly implemented, visible and complete across an
arbitrary codebase is not mechanizable. Issue *existence* is not checked (format
only). An empty or absent registry yields "no parity entries yet".

## One owner per behavior (Rule 4)

This module owns only the capability×surface matrix and its gap-linking. It is
distinct from `feature-registry` (story → acceptance → tests) and `contract-first`
(capability → interface symbols in a spec), and it reads no other module's
artifacts. The issue-reference formats it accepts are a deliberate small
duplication of the `github-issues` gate's — modules must not import each other, so
the three short regexes are copied rather than shared.

## The seed

An inert `capability.example.json` ships under the parity directory; the gate
skips every `*.example.json`. Copy it, drop the `.example`, rename the stem to your
capability, and fill in the real surfaces. The gate itself is
`scripts/process/check_parity.py`.
