# SP19 — Enforce review independence (gated attestation)

## Problem

`verification-independence.md` defines tier-scaled independent review and
*attestation* (bundle-only, non-implementing, cross-model), but ends with:
"a judgment applied at the gate, not a machine-checked gate itself." So nothing
stops:

- a Tier 3+ change merging with **no** independent review at all;
- the **implementer self-certifying** (the exact failure the gate exists to
  prevent);
- a Tier 4 change silently skipping the **cross-model** pass.

The attestation is prose in a review result; its consequence ("the merge
decision weighs it accordingly") is human judgment. The crown-jewel quality
mechanism of the process is unenforced.

## What a language-agnostic CI gate can and cannot enforce

- **Can:** the *presence and shape* of a structured attestation; the
  *arithmetic* that a pass verdict does not claim more independence-clearance
  than its declared flags justify; the presence of a clearing attestation for
  work that **declares** itself Tier 3+ and **has merged**.
- **Cannot:** whether the reviewer was *truthfully* a different agent or model
  — the gate never sees the review runtime. That claim stays *attested*, as in
  SP12. SP19 turns the *consequence* of a weak/absent/over-claiming attestation
  from "weighed by a human" into "blocks the merge", without pretending to
  verify identity.

## Decision

### 1. The attestation is a structured `REVIEW` record (core)

One line per review, appended to the journal (core artifact; the same place
telemetry writes `GRADE`, but an independent grammar and owner):

```
REVIEW work=42 tier=3 reviewer=fresh-agent model=same independence=bundle,non-implementing verdict=pass round=1
```

| field | meaning |
|---|---|
| `work` | attribution: issue number or the plan slug it reviews |
| `tier` | the reviewed change's tier (0–4) |
| `reviewer` | an id for the reviewing process (presence gated; truthfulness attested) |
| `model` | reviewing model-family slug, or `same` if same family as the producer |
| `independence` | comma set ⊆ `bundle,non-implementing,cross-model,single-family` |
| `verdict` | `pass` \| `block` |
| `round` | 1, 2, … |

`single-family` is the explicit honest acknowledgment that only one model
family was available (SP12's "do not fake it — state the limitation").

### 2. `check_review.py` — a core, always-on gate

Core because it guards a mandatory rule (rule 7, review before merge), not an
optional module. It is the second core gate (module key `None`).

**Hard (CI fails, file:line):**
- A journal line starting `REVIEW ` that does not match the grammar, or whose
  `verdict`/`independence` tokens are out of enum, or `tier`/`round` non-numeric
  — a malformed attestation is silent loss (same discipline as telemetry).
- **Independence arithmetic** on a `verdict=pass`:
  - `tier ≥ 2` without `non-implementing` → hard. A self-review cannot clear
    Tier 2+ (the implementer does not certify its own work).
  - `tier ≥ 2` without `bundle` → hard. Tier 2+ is reviewed from a read-only
    bundle, not the warm producing context.
  - `tier = 4` with neither `cross-model` nor `single-family` → hard. Tier 4
    must either cross the model family or explicitly declare it could not.
- **Presence** (post-merge, opt-in by tier declaration): an **archived** plan
  (`.process-work/plans/archive/…`) that declares `tier: N` with N ≥ 3 and
  carries neither a matching `verdict=pass` `REVIEW` (`work` = plan slug or its
  issue, `tier ≥ N`) **nor** an explicit `review-waived: <reason>` line → hard.

**Best-effort (advisory note, never fails CI):**
- Zero `REVIEW` lines repo-wide — expected pre-adoption.
- A plan with **no** `tier:` declaration — presence cannot be enforced, noted,
  never a retroactive false-red for brownfield plans that predate the field.
- A non-archived (in-flight) plan declaring tier ≥ 3 without a review yet —
  advisory; the review is expected at merge, and CI runs mid-development.

Fenced ```-blocks are quotations, invisible to the gate (as in telemetry).
The gate checks shape and arithmetic only; whether the reviewer was truthfully
independent is not machine-checkable and stays attested.

### 3. Machine-readable tier on plans (core convention)

Plans gain one line: `tier: N`. It is the single machine-readable tier source
the presence check keys on, and it is opt-in — a plan without it is simply not
presence-enforced (honest degradation). Documented in `journal-state-plans.md`.

### 4. Anchoring

- `verification-independence.md`: replace the "not a machine-checked gate"
  close with an "## Enforcement" section — the arithmetic and presence are now
  gated (`check_review.py`); identity/model truthfulness stays attested.
- `mandatory-rules.md` rule 7: the review attestation is recorded and gated;
  a merge without a clearing attestation for a declared Tier 3+ change fails
  the gate (or is an explicitly waived, named exception — rule 10).

## Why the plan-archival lifecycle is the right enforcement point

A plan is archived on merge. Checking presence against **archived** plans fires
exactly once, at the moment work lands — after which both the archived plan and
the journal `REVIEW` line are in the tree for the gate to see. It never reds CI
during development (the plan is still in `plans/`, only advisory then), and it
has a named-exception escape (`review-waived:`) so it enforces without becoming
a footgun that blocks every later merge.

## Alternatives considered

- **Infer tier from the diff**: rejected — not reliable language-agnostically;
  scope (not volume) sets the tier, which code cannot read.
- **Verify reviewer identity/model**: impossible — the gate cannot see the
  review runtime. Enforcing the *arithmetic* of the self-declared flags is the
  honest maximum.
- **REVIEW lines as a telemetry-module concern**: rejected — review-before-merge
  is mandatory rule 7 (core), not an optional-module feature; the gate must run
  even when telemetry is off. Separate grammar, separate owner from `GRADE`.

## Non-goals

- No claim to verify that a different model *actually* ran.
- No effective-tier lattice beyond the three arithmetic rules above (keeps the
  gate legible and non-brittle).

## Anchor Delta

`verification-independence.md` gains "## Enforcement"; `mandatory-rules.md`
rule 7 references the gated attestation; `journal-state-plans.md` documents the
`tier:` plan field and the `REVIEW` record. Second core gate registered. No
kernel change.

## Feature Registry Trace

Process-template self-change; template tests are acceptance. New:
`test_review.py` (grammar hard, arithmetic hard, presence hard + waiver,
pre-adoption soft, no-tier soft, fenced-ignored), extended `test_manifest_ci.py`
(second core gate lists/runs), `test_core_docs.py` (enforcement section, rule 7,
plan tier field).
