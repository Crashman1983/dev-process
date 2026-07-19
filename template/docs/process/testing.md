# Testing — how to shape a suite

Mandatory rule 5 says *what* a test must do: prove the acceptance it claims.
This document says *how to shape the suite* that does it. It is methodology,
not tooling — pick the runners your stack already uses.

## The shape: many fast, few slow

Order tests by scope, speed and cost — the classic pyramid, read as a
heuristic, not a quota:

- **Unit** (the base): one function/class, milliseconds, no I/O. Most tests
  live here because they run on every edit and localize a failure precisely.
- **Integration** (the middle): components together — a route hitting a real
  (test) database, a parser over real files. Slower, fewer, and the layer
  that catches wiring mistakes units cannot see.
- **End-to-end** (the tip): a handful of whole-workflow proofs. At least
  **one end-to-end proof per feature** that input becomes the intended
  durable state or visible outcome — the review checklist's completeness
  section asks for this (there, a manual trace may stand in); unit tests
  alone do not satisfy it.

Inverting the shape (many E2E, few units) makes the suite slow and flaky and
is the most common failure mode. When an E2E test and a unit test would prove
the same thing, prefer the unit test and keep the E2E count flat.

## What earns a test beyond the happy path

Acceptance decomposition (Definition of Ready, R2) already names them: the
**negative** case, the **edge** case, the **authorization** case, and the
**invalidation/cleanup** case. The missing negative twin is
where a bug most often hides. Two patterns worth reaching for:

- **Property-based testing** where the input space is large (parsers,
  serializers, calculations): state an invariant and let the framework
  search for counterexamples (Hypothesis, fast-check, jqwik, proptest …).
- **Regression pins**: every bug fixed — and every finding whose fix changes
  behavior — gets a test that fails on the old behavior; the suite is the
  ratchet that keeps a caught defect caught.

## Coverage numbers — the honest ceiling

Line coverage measures *execution*, not *verification* — a suite can execute
80% of lines and assert nothing (review AI-generated tests for assertion
substance, not test count). The discipline is the same one the telemetry
module applies to its numbers, where installed: **no universal threshold
gate.** A coverage number is useful
only as a within-project trend (falling coverage on changed code is a review
question) and as a map of what is *untested*, never as a target to optimize.
If you want a stronger signal on critical logic, run **mutation testing**
(Stryker, PIT, mutmut …) there — the mutation score asks the right question
("would the suite notice broken code?") at a compute cost that is only worth
paying on the code that matters most.

## Suite discipline

- A **flaky test is a defect**, not weather: fix it or quarantine it the same
  day with an issue (or an inbox entry, tracker-less) — a suite people retry is a suite people ignore.
- The suite must stay **fast enough to run before every push**, alongside the
  pre-push process gates; split a slow tier behind an explicit marker rather
  than letting the default run grow past patience.
- Test code is code: mandatory rule 9 (written to be read) applies — a test
  nobody understands proves nothing when it fails.

## Gates must survive a fresh checkout

A project-level gate is trustworthy only if a fresh checkout can bootstrap and
run it from tracked inputs. Local caches such as `.venv`, `node_modules`, build
outputs, or a previously prepared agent workspace are conveniences, not part
of the gate contract. The documented gate command must provide a
reproducible bootstrap from lockfiles or an equivalent pinned environment (for example
`uv run`, the project's package-manager install, or a versioned container).

Exercise that contract in CI or a disposable checkout. Report a missing cache
or bootstrap defect separately from a product failure: both block a trustworthy
gate, but they have different owners and fixes. A command that passes only in a
warm development tree is not a reproducible gate.

Review binding: the review checklist's "Tests prove acceptance" section is
where this document is enforced — mapping per criterion, the E2E proof, and the
negative/edge/authorization/invalidation cases are review questions, not
suggestions.
