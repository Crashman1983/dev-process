# Plan: english-canon (SP8) + honest-economics

Design: `docs/design/2026-07-02-sp8-english-canon-design.md`. TDD per task.

## Task 1 — kernel rule: dialogue language vs artifact language

- Add one kernel line (byte-identical across the three adapters):
  "Converse with the user in the user's language; write all artifacts
  (docs, code, commits, ADRs, journal) in English."
- Tests: kernel-identity test keeps passing; new assert that the rule is in
  the kernel block.

## Task 2 — de-bilingualize the rendered surface

- English-only (drop the German halves, keep meaning): `CLAUDE.md.jinja`,
  `AGENTS.md.jinja`, copilot instructions + prompts, all `.claude/commands/`,
  `start-here.md`, `.process-work/README.md`.
- Tests: adapt `test_core_docs.py` / `test_command_adapters.py` /
  `test_bootstrap.py` string expectations to English; add a no-German guard
  (e.g. no "**Deutsch:**" marker anywhere in a rendered repo).

## Task 3 — BOOTSTRAP English-only with German pointer

- Rewrite `BOOTSTRAP.md` English-only; keep a two-line German pointer at the
  top. README stays German.
- Tests: existing BOOTSTRAP string tests updated where they asserted German.

## Task 4 — honest economics + tiered journal duty

- README + `start-here.md`: "when NOT to use this process" note.
- `journal-state-plans.md`: journal entries expected from Tier 2 upward;
  Tier 0-1 exempt.
- Tests: rendered `start-here.md` names the exemption and the not-worth-it
  case.

## Task 5 — version bump

- `pyproject.toml` → 1.2.0; README status line.
