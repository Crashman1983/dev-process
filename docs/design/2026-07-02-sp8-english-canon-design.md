# Design: english-canon (SP8) + honest-economics

**Date:** 2026-07-02
**Status:** approved (scope agreed with Seb: efficiency review items 1 + 3;
item 2 — graders/telemetry — waits on access to the Kenni grader spec)
**Slice:** all rendered artifacts become English-only; the user-facing dialogue
language becomes an explicit kernel rule; the process states when it is *not*
worth installing and exempts Tier 0-1 from journal duty.

## Gap

Every rendered adapter, command, and the start-here dialogue carries every
sentence twice (German + English). That doubles the token cost of every prime,
every command invocation, and every onboarding read — recurring, in every
rendered repo, forever — and it is the template's single largest recurring
cost with the least value per token: an LLM needs one language, and it
performs most reliably in English. Separately, the process never says when it
is a net loss (throwaway prototypes), and the journal duty applies uniformly
even where nothing will ever be resumed.

## Decision 1 — artifacts are English; dialogue follows the user

There is no `language` copier question. Two concerns, split cleanly:

- **Artifacts** (process docs, adapters, commands, ADRs, journal, commits,
  code comments) are written in English — the canon LLMs handle best, and one
  language to maintain instead of two.
- **Dialogue** follows the user: a new kernel line instructs every harness to
  converse in the user's language (detected from their messages) while keeping
  artifacts English. The distinction costs one sentence, not a render axis.

Rejected: a `language: de/en/both` copier question. It would jinja-fork every
doc, keep double maintenance for `both`, and solve the wrong problem — the
user reads the *dialogue*, not the process docs.

## Decision 2 — scope of the de-bilingualization

English-only: all template adapters (`CLAUDE.md`, `AGENTS.md`, copilot
instructions), all command files (both harness variants), `start-here.md`,
`.process-work/README.md`, and upstream `BOOTSTRAP.md` (agent entry point) —
the latter keeps a two-line German pointer at the top. The upstream `README.md`
stays German: it is the project's face for its (German) audience, read once,
not rendered into targets. Core docs under `docs/process/` are already
English-only.

## Decision 3 — honest economics

`README.md` and `start-here.md` gain a short "when NOT to use this" statement:
for throwaway prototypes, one-off scripts, and single-session work the process
is net negative — install nothing, or the minimal profile. The same honesty the
gates apply to conformance applies to the process itself.

## Decision 4 — journal duty scales with tier

`journal-state-plans.md`: journal entries are expected from Tier 2 upward, or
whenever a non-obvious decision was made; Tier 0-1 changes need none. State
files remain per-branch (they are what makes any resumption cheap); plans
remain a Tier 3+ artifact as before.

## Out of scope

Graders/telemetry (efficiency item 2) — blocked on the Kenni grader spec;
gets its own slice once accessible.
