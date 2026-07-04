# SP18 — Typed Decision Records + integrity gate

## Problem

Two gaps surfaced in use:

1. **Significant product/process decisions that are not features have no home.**
   The template has `feature-registry` (features: story + acceptance) and
   `adr/` (architecture decisions). A scope boundary, a deliberate "we will not
   build X", a positioning principle, a process choice — none is a feature, and
   the ADR is *named and signposted* for architecture (README trigger: "shapes
   structure, crosses a boundary"). The ADR body already asks about "product,
   organizational" forces, so the artifact fits; the framing keeps it from
   being used.

2. **The ADR/decision machinery is weakly anchored and only optionally gated.**
   - No mandatory rule requires recording a significant decision or reading the
     relevant ones before planning.
   - No patch-count discipline (Kenni Rule 5: ≥2 prior patches ⇒ explicit
     increment-vs-rewrite call) is generalized.
   - The README states "every new ADR must be in the index" but no gate checks
     it.
   - The Intent axis (`keep | change-planned | tolerated`) can express
     contradictory / unclear states across records, and incoherent
     Status×Intent pairs (e.g. `Superseded` + `keep`) are never caught.
   - The only ADR gate (`check_arch_docs.py`) lives in the opt-in `arch_docs`
     module and checks only that `ADR-NNNN` refs in the overview resolve — it
     never inspects the ADR files themselves. A project that ships `adr/`
     (core) without `arch_docs` gets zero decision-integrity checking.

## Decision

**Generalize the ADR into a typed Decision Record** (the MADR "any decision
record" convention) and **add a core, always-on integrity gate** for the
decision-record files.

### 1. Typed Decision Record (docs, core)

- Rename the log framing: "Decision Records" — one significant, hard-to-reverse
  decision, **architectural, product, or process**. Keep the `adr-NNNN-*.md`
  filename and `ADR-NNNN` reference token unchanged (the whole gate/ref
  ecosystem and every existing link depend on it — renaming the token would be
  a breaking, low-value churn). The word "ADR" stays as the *reference token*;
  the *concept* is a Decision Record.
- Add a `## Type` axis to `template.md`: `architecture | product | process`.
- Add one sentence making **Intent atomicity** explicit: Intent is one value
  per record; a decision that cannot take a single Intent is more than one
  decision — split it. The single-value rule is the forcing function for
  atomicity, and answers the "keep and change mixed" worry: mixed intent is the
  signal to split, not a state to encode.

### 2. Core integrity gate (`check_decisions.py`, always-on)

`docs/process/adr/` is core, so its integrity gate must be core too. The gate
runner has no always-on concept today (every gate is module-keyed). Introduce
one: a `None` module key means "core gate, always runs". `check_decisions.py`
is the first core gate and ships unconditionally (no `{% if %}` filename
wrapper).

Ownership split (no duplication): `check_decisions.py` owns **decision-record
file integrity**; `check_arch_docs.py` keeps owning **overview→ADR ref
resolution**. Different artifacts, different owners.

**Hard (CI fails, with file:line):**
- A decision file (`adr-NNNN-*.md`, excluding `template.md`) whose number is
  not listed in `README.md`'s index — a decision missing from the index is
  silently unfindable.
- A `Status` value that is a real choice but outside the enum
  (`Proposed|Accepted|Superseded[...]`), or an `Intent` outside
  (`keep|change-planned|tolerated`) — a typo makes the axis unreadable.
- An **incoherent Status×Intent** pair: `Superseded` with `keep` or
  `change-planned` (a superseded decision is historical; endorsing it or
  planning its migration contradicts the supersession).
- Non-UTF-8 decision file.

**Best-effort (advisory note, never fails CI):**
- `Status`/`Intent` still the unedited template menu (contains `|`) in a real
  `adr-NNNN` file — "not yet chosen", the same pre-adoption honesty telemetry
  uses. (The seed and `template.md` are excluded / carry real values.)
- Missing `## Type` — advisory; brownfield-adopted records predate the field,
  and absence reads as `architecture` by default. Not hard, to avoid a
  retroactive false-red.
- `Intent: change-planned` with no `ADR-NNNN` ref and no URL in the body — the
  follow-up should be linked, but it may legitimately be an issue, so soft.

The gate parses only the presence and enum-membership of `Status`/`Intent`/
`Type` fields. It never judges whether a decision is *correct* — that is the
review gate's job. Documented boundary, no false-green.

### 3. Anchoring (docs, core)

- `mandatory-rules.md` Rule 4 extended (principle, not mechanics): a
  significant, hard-to-reverse decision (architecture, product, or process) is
  recorded as a Decision Record before the code that assumes it; when an
  element already carries ≥2 prior decision records/patches, the plan makes an
  explicit increment-vs-rewrite call before more patching.
- `start-here.md` definition-of-ready: read the relevant Decision Records
  before planning; a new significant decision gets a record first.

## Alternatives considered

- **Separate PDR log** (`decisions/product/`): rejected — violates one-owner,
  doubles drift surface, and the "is this product or architecture?" boundary
  becomes its own friction. A typed single log is lighter and honest for the
  solo/small-team target.
- **Second Intent vocabulary for product decisions**: rejected — the three
  values map cleanly (keep≈committed, change-planned≈deprecated-with-migration,
  tolerated≈debt); a parallel scale is exactly the "unclear state" to avoid.
- **Fold integrity into `arch_docs`**: rejected — leaves core `adr/` unguarded
  when `arch_docs` is off.

## Scope / non-goals

- No rename of the `adr/` directory or the `ADR-NNNN` token (breaking, no
  value).
- No semantic judgment of decisions in the gate (review's job).
- Patch-count is a *plan discipline* surfaced in the rule, not a machine gate
  (patch count per code element is not reliably countable in a language-
  agnostic gate).

## Anchor Delta

`mandatory-rules.md` Rule 4 gains the decision-record + patch-count principle.
No kernel change. New core-gate concept documented where the gate runner is
described.

## Feature Registry Trace

Process-template self-change; the template's own tests are the acceptance.
New tests: decision-record generalization (Type field, Intent atomicity
sentence, neutral), and the core gate (listing-drift hard, Status×Intent
coherence hard, menu/Type/change-planned soft, always-on wiring).
