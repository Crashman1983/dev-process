# Review Checklist

What a competent review actually checks — the judgment the review gate supplies
that no machine gate can. These defects are not grep-able (that is why they need
a review, not a linter), so this is a checklist of *questions to ask*, not a
pattern to match. Framed neutrally: apply each to your stack.

Depth scales with the tier (`risk-tiers.md`): a Tier 0–1 change gets a light
pass over the relevant questions; Tier 2+ gets all of them; how *independent*
the reviewer must be also scales (`verification-independence.md`) — the
implementing agent does not self-certify.

## Completeness

- Does every new field, value, or side-effect reach its **terminal state**
  (persisted, emitted, displayed, or deliberately dropped)? Trace it from where
  it is created to where it is used — a value that is produced and never read is
  dead data.
- Are **all execution paths** handled: the happy path, the error path, the retry
  path, and any async/deferred path?
- Is there **one end-to-end proof** (a test or a manual trace) that input
  becomes the intended durable state or visible outcome — not just a unit test
  of one piece in isolation?

## Correctness

- What happens at the **boundaries**: empty input, a duplicate, a value at the
  limit, a concurrent caller, a collision? Each is a common source of a silent
  wrong answer or an unhandled crash.
- Is **error handling** deliberate — does a failure surface, retry, or roll
  back, rather than being swallowed or crashing on the next line?
- If the operation can be retried, is it **idempotent**?

## Performance & efficiency

- Does the change add work that grows with the input — an **N+1** query, a loop
  that re-fetches or re-computes per item, an **unbounded** collection, a full
  scan where a keyed lookup exists?
- Are expensive calls (I/O, network, database, subprocess) made **once and
  reused**, not repeated inside a loop?
- Is anything **unbounded loaded into memory** — a whole file, an unpaginated
  result set, a growing cache with no eviction?
- Both directions: catch the accidental blow-up on a hot path, but do not
  gold-plate a cold one — flag premature optimization too.

## Security — untrusted input reaching a sink

The dangerous class a junior most often misses. Untrusted input is not only a
web form — a request body, a CLI argument, a config value, a file, a queue
message are all external. For every place such input flows, ask: does it reach a
**sink** without validation?

- A **redirect** target (open redirect — validate the scheme and destination).
- **Rendered markup** or a template (injection / XSS).
- A **query** or command string (injection).
- A **subprocess** invocation (argv list, never a shell string).
- A **file path** (path traversal — resolve and confine to a root).
- **Deserialization** of external data.

Also: is **authorization fail-closed** (deny by default, not allow on error)?
Are **secrets** kept out of logs, responses, and the repository?

## Observability & operability

- When this **fails in production, will anyone know**? Is there a log, metric,
  or trace at the failure point carrying enough context to diagnose it — the
  ids, not the secrets?
- Are messages at the **right level** — an expected condition is not an error, a
  real failure is not swallowed at debug?
- Does a new **dependency or config fail fast** at startup, rather than only
  when the code path that needs it first runs (in a server, at 3am on the first
  request; in a batch job, halfway through the run)?
- Is the change **safe to release and reverse**? Where it is deployed
  incrementally, is a migration backward-compatible for any window in which the
  old and new versions run together; and can the change be reverted without a
  data fix?

## Design — one owner per behavior

- Does this change **duplicate** an existing behavior instead of changing its
  owner? A second function, flag, wrapper, or fallback that overlaps something
  already there adds accretion — find the owning layer and change it there
  (mandatory rule 4).
- Is the code **readable** — intention-revealing names, small single-purpose
  units, no magic values (mandatory rule 9, `code-craft.md`)?

## Decisions — recorded, not embodied silently

The non-mechanical counterpart of the `decision-records` gate: the gate checks
the integrity of records that *exist*; only a review can notice one that is
*missing*. Ask of the change as a whole (mandatory rule 4):

- Does it **embody a significant, hard-to-reverse decision** — architectural,
  product, or process — that has **no decision record**? A choice of storage
  model, protocol, dependency, or irreversible data shape hidden inside a diff
  is a decision made silently.
- Does it **contradict an `Accepted` record**? Then either the change or the
  record is wrong — resolve the conflict, do not merge the contradiction.
- Does it make an existing record **obsolete in practice** while leaving the
  file untouched? A record the code no longer honors is a lie to the next
  reader — supersede it in the same change.

## Product frame — direction, not drift

The frame (`PRODUCT.md`) is what development is checked against; the
product-frame gate keeps it present and reference-clean, but only a review can
judge the change against its content:

- Does the change **serve a stated goal** — or is it product-neutral
  infrastructure? Work that serves no goal and is not infrastructure is scope
  arriving uninvited.
- Does it **violate a non-goal**? Then either the change is wrong or the frame
  is — change `PRODUCT.md` deliberately in the same change, or do not merge.
- Does it **shift scope while `PRODUCT.md` stays untouched**? A scope change
  that only lives in code is silent drift; the frame must move with it.

## Tests prove acceptance

- Does a **test map to each acceptance criterion** the change claims? A feature
  without a test proving its acceptance is not done (mandatory rule 5).

## Extending this list

This is the neutral floor. A project with a specific stack or risk surface
should extend it in its own anchor — add the framework's known footguns, the
domain's invariants — but never *remove* a category to make a review pass.
