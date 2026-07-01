# Design: command-adapters (SP6, capstone → v1.0.0)

**Date:** 2026-07-01
**Status:** approved (scope + cadence pre-agreed with Seb)
**Slice:** the final one. Ships the neutral process as harness-native slash
commands, closing the "complete like Kenni" program at v1.0.0.

## Gap

The neutral process lives in `docs/process/` and is pointed at by three thin
adapters (`CLAUDE.md`, `AGENTS.md`, `.github/copilot-instructions.md`). But a
user in a harness has no *native* way to invoke a phase — no `/plan`, no
`/review`. Kenni carries a full command set (`brainstorm plan execute review
quick debug commit prime`); dev-process ships none. This slice extracts that
command surface, harness-native, thin, and drift-checked.

## Decision 1 — harness-gated, not a module

Command adapters are **harness ergonomics**, the same layer as
`CLAUDE.md`/`AGENTS.md`/`process.instructions.md` — not a process capability.
They therefore gate on `harnesses.*`, never on `modules.*`:

- no `modules` toggle, no `.copier-answers` key,
- no `gate_runner.py` entry (a command file is not a gate),
- no `conftest.py` modules-dict addition.

This is also more consistent than a module: every module defaults `false`, but
a command set should ship whenever its harness is active — which is exactly
what `harnesses.*` gating gives. Matches Seb's "Alle aktivierten Harnesses."

## Decision 2 — full thin set, only if thin actually works

Seb: *"Wenn dünn funktioniert nehme ich das. Aber nur dann."* Thin works here
because `workflow.md` already names, per phase, what enters / what it produces /
when to use it. A command file is a ~6-line pointer into the right phase plus
the one contract line the harness needs at the trigger point. It does **not**
re-explain the doc. If a command cannot be carried by a pointer + the doc, that
command is reported back, not padded.

### The set (8 commands)

| Command | Purpose | Points at (full `docs/process/` path) |
|---|---|---|
| `brainstorm` | idea → approved design | `workflow.md` (Brainstorm) |
| `plan` | design → zero-context task plan | `workflow.md` (Plan), `journal-state-plans.md` |
| `execute` | build the plan, TDD, atomic commits | `workflow.md` (Execute), `commits.md` |
| `review` | merge gate, depth by tier | `workflow.md` (Review), `risk-tiers.md` |
| `quick` | Tier 1–2 shortcut | `workflow.md` (Quick), `risk-tiers.md` |
| `debug` | root-cause entry (rule 6) | `workflow.md` (Debug) |
| `commit` | atomic conventional commit | `commits.md` |
| `prime` | restore working context | `journal-state-plans.md` |

`commit` and `prime` have no `workflow.md` phase → they point at
`commits.md` / `journal-state-plans.md` respectively, nothing else. `prime` is
written from `journal-state-plans.md` (restore state file + latest journal +
active plan) — **not** transcribed from Kenni's richer `/prime` (which carries
`make dev-context`, PRD sections, branch-slug specifics that do not exist in the
neutral process).

## Decision 3 — harness-native file layout

- **Claude Code** (always installed): `.claude/commands/<name>.md`, plain
  markdown, unconditional. Claude Code auto-discovers these as `/name`.
- **Copilot** (`harnesses.copilot`): `.github/{% raw %}{% if harnesses.copilot %}prompts{% endif %}{% endraw %}/<name>.prompt.md`,
  verbatim (path-conditional gates the directory; content needs no rendering).
- **AGENTS.md harness** (`harnesses.agents_md`): a `## Process commands`
  section appended to `AGENTS.md.jinja`. AGENTS.md readers have no native
  command menu, so the commands are listed inline as phase pointers.

The Claude and Copilot files for the same command are near-identical thin
pointers differing only in frontmatter. This is **deliberate cross-harness
duplication** (Rule 4): harnesses are separate surfaces; a shared source would
couple them. Small duplication over coupling.

Command files reference **only** always-shipping `docs/process/*.md`
(`workflow.md`, `commits.md`, `journal-state-plans.md`, `risk-tiers.md`,
`mandatory-rules.md`, `code-craft.md`). They never bare-reference a
module-gated doc (e.g. `github-issues.md`), which would 404 when that module is
off. No Jinja conditionals in command bodies — they stay harness-pure and
drift-safe.

## Decision 4 — the enforcement hook (extend doc_drift, Rule 4 owner)

Without a machine check, command-adapters would be the only slice with no
CI-failable property — violating the "Nur echte Enforcement-Module" philosophy.
The check already exists: `doc_drift_gate`'s stated purpose is *"path
references in docs/process/ **and the harness adapters**."* Command files **are**
harness adapters. So the enforcement is a **scan-scope extension of the
existing owner**, not a new checker.

**Rule 4 / patch-count note (binding, surfaced before code):** this is the 3rd
touch of `check_doc_drift.py` (exemplar `5368acf`, ARCHITECTURE.md add
`1c93cae`, this). The patch-count gate demands an explicit *increment vs.
rewrite-the-owner* decision. Decision: **increment.** Adding two entries to
`SCAN_DIRS` makes the code *more* faithful to its own docstring (which already
claims "the harness adapters"); it removes no complexity and adds no parallel
mechanism. This is the textbook "extend the owner layer" case, not accretion.

Extension:
```python
SCAN_DIRS = ["docs/process", ".claude/commands", ".github/prompts"]
```
`rglob("*.md")` catches `.claude/commands/*.md` and `.github/prompts/*.prompt.md`
(both end in `.md`). A non-existent dir (`.github/prompts` when copilot off)
yields an empty rglob — safe, no error.

### Slash-path discipline (why it must be exact)

`doc_drift` only checks references **containing a slash** (`_is_local_path`
requires `/`); bare filenames like `workflow.md` are skipped as illustrative.
`workflow.md` itself uses bare filenames — so a command file that copied that
style would be scanned but have **zero checkable refs**: a silent no-op that
looks enforced. Therefore command files MUST write full paths
(`docs/process/workflow.md`), never bare `workflow.md`. This is the design's
one hard authoring rule and the thing the negative tests below actually prove.

## Testing (no false-green)

A positive test alone does **not** prove the scan extension: it stays green
whether or not the new dirs are scanned (nothing to fail = OK). A typo in one
`SCAN_DIRS` entry (`.claude/command`) would silently scan nothing and every
positive test would still pass. So the wiring is proven by **negative tests,
one per new SCAN_DIR**:

1. `test_doc_drift_scans_claude_commands` — render `doc_drift_gate` on; write a
   `.claude/commands/*.md` file carrying a broken slash-ref
   (`` `docs/process/does-not-exist.md` ``); assert gate exits 1 and names the
   file. Proves `.claude/commands` is in scope.
2. `test_doc_drift_scans_copilot_prompts` — render `doc_drift_gate` + `copilot`
   on; plant the same broken ref in `.github/prompts/*.prompt.md`; assert exit
   1 + filename. Proves `.github/prompts` is in scope.

Plus behaviour tests for the ship-set:

3. Claude command files ship for every harness combination (always).
4. Copilot prompt files ship iff `harnesses.copilot`.
5. AGENTS.md carries `## Process commands` iff `harnesses.agents_md`.
6. **Positive drift-clean:** render everything (`doc_drift` + all harnesses)
   and assert the gate exits 0 — proves every shipped command file's real refs
   resolve (the slash-path discipline holds in the actual content).
7. Neutrality: no shipped command file (and the AGENTS.md section) contains a
   Kenni-ism from the neutrality word list.

## Neutrality beyond the word list

The word-list check catches `Kenni/Seb/Signal/…` but not structural leaks
(`make test`, `ARCHITECTURE.md`-as-anchor, `PRD.md`, surface labels). Command
bodies are authored from the neutral docs only: no build-tool names, no
Kenni-specific file anchors, no product nouns. `prime` and `debug` are the two
most at risk of importing Kenni detail from memory — both authored strictly
from `journal-state-plans.md` / `workflow.md`.

## Out of scope

- No new gate, no gate_runner entry (harness-gated, not a module).
- No CLAUDE.md change (Claude Code discovers `.claude/commands/` natively; a
  pointer would add surface without value).
- No module-gated behaviour inside command bodies (keeps them drift-safe).

## Release

pyproject `0.9.0 → 1.0.0`; tag `v1.0.0`. This is the finish line: with
command-adapters shipped, dev-process carries the full Kenni command surface,
harness-native and drift-checked. Program complete.
