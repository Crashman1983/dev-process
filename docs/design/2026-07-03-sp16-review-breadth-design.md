# Design: review breadth (SP16)

**Date:** 2026-07-03
**Status:** approved (scope: the review-checklist gap a maintainer named — it
covers completeness/correctness/security/design/tests but not the two
dimensions a senior reviewer also checks: performance/efficiency and
observability/operability; and its mental model leans web)
**Slice:** add the two missing review dimensions as stack-neutral questions,
and broaden the untrusted-input framing beyond web, so the checklist covers
what a competent review actually spans.

## Gap

`review-checklist.md` (SP14) closed the junior gap for the dangerous
correctness/security class, but a senior review also asks two things it does
not: *will this perform* (accidental O(n²), N+1 queries, unbounded loads) and
*can this be run and debugged in production* (is a failure observable, is a
deploy/rollback safe). Both are stack-neutral judgment, not grep-able — exactly
the checklist's remit. Separately, the SP15/SP14 review noted the security
examples read web-first; the sinks already span CLI/backend, but the framing
should say so.

## Decision — two new dimensions, one framing touch

- **Performance & efficiency:** questions about work that grows with input
  (N+1, re-fetch loops, unbounded collections, full scans), repeated expensive
  I/O, loading the unbounded into memory — and the honest both-directions note:
  catch the accidental blowup, do not gold-plate a cold path.
- **Observability & operability:** when it fails in production, will someone
  know (a log/metric/trace at the failure point, with ids not secrets, at the
  right level); is a new dependency/config fail-fast at startup; is the change
  safe to deploy incrementally and roll back (a migration backward-compatible
  for the mixed-version window).
- **Framing:** one clause on the security intro naming non-web untrusted
  sources (a request body, a CLI argument, a config value, a queue message) so
  the reader does not read "untrusted input" as "web form only".

Ordered so the flow reads works → works well enough → is safe → can be operated
→ is maintainable → is proven. Version 1.5.1 (additive doc enhancement, no new
module or gate).

## Out of scope

A machine gate (unchanged — these are judgment, not grep-able); per-stack
performance budgets or SLO templates (a project adds those in its own anchor,
as the checklist's "extending this list" section already invites).
