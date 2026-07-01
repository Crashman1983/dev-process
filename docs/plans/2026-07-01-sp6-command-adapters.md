# command-adapters Implementation Plan (v1.0.0 capstone)

**Goal:** Ship the neutral process as harness-native slash commands, drift-checked.

**Architecture:** Harness-gated command files (Claude always, Copilot + AGENTS.md
by toggle) that thin-point at `docs/process/*.md` with full slash paths; the
existing `doc_drift_gate` owner is extended to scan the new command directories.

**Tech Stack:** copier template, Python stdlib gate, pytest.

## Global Constraints

- Command bodies reference **only** always-shipping `docs/process/*.md`
  (`workflow.md commits.md journal-state-plans.md risk-tiers.md
  mandatory-rules.md code-craft.md`), always with the **full slash path**
  (`docs/process/workflow.md`, never bare `workflow.md`) — else doc_drift can't
  check them.
- No Jinja delimiters (`{{ {% {#`) in command bodies → ship without `.jinja`.
- No Kenni-isms (word list + structural: no `make …`, `PRD.md`,
  `ARCHITECTURE.md`-as-anchor, product nouns).
- Harness-gated only: no `modules` key, no gate_runner entry, no conftest
  modules change.
- Every commit carries the two trailers; atomic conventional commits.

---

### Task 1: doc_drift scans command dirs (the enforcement hook)

**Files:**
- Modify: `template/scripts/process/{% raw %}{% if modules.doc_drift_gate %}check_doc_drift.py{% endif %}{% endraw %}.jinja` (SCAN_DIRS)
- Test: `tests/test_command_adapters.py` (new)

**TDD:**
- [ ] Negative test `test_doc_drift_scans_claude_commands`: render `doc_drift_gate=True`;
  write `.claude/commands/x.md` containing `` `docs/process/does-not-exist.md` ``;
  run gate → assert `rc == 1` and `"does-not-exist.md"` in output.
- [ ] Negative test `test_doc_drift_scans_copilot_prompts`: render
  `doc_drift_gate=True, copilot=True`; write `.github/prompts/x.prompt.md` with the
  same broken ref; assert `rc == 1` + filename.
- [ ] Run both → FAIL (dirs not yet in SCAN_DIRS; gate exits 0 / file not found).
- [ ] Extend: `SCAN_DIRS = ["docs/process", ".claude/commands", ".github/prompts"]`.
- [ ] Run both → PASS. Run the existing doc_drift test module → still PASS.
- [ ] Commit `feat: doc-drift gate scans command-adapter directories`.

### Task 2: Claude command files (always installed)

**Files:**
- Create: `template/.claude/commands/{brainstorm,plan,execute,review,quick,debug,commit,prime}.md`
- Test: `tests/test_command_adapters.py`

Each file: `# /<name>` title, one-line purpose, "Read `docs/process/<file>.md`
(<Section>)", and the 1–3 contract lines the trigger needs. Full slash paths.

**TDD:**
- [ ] Test `test_claude_commands_always_ship`: render minimal (all off); assert all
  8 `.claude/commands/<name>.md` exist.
- [ ] Test `test_shipped_commands_drift_clean`: render `doc_drift_gate=True` + both
  harnesses; run gate → assert `rc == 0` (every real ref resolves).
- [ ] Run → FAIL (files absent).
- [ ] Create the 8 files.
- [ ] Run → PASS.
- [ ] Commit `feat: add Claude Code slash-command adapters`.

### Task 3: Copilot prompt files (harnesses.copilot)

**Files:**
- Create: `template/.github/{% raw %}{% if harnesses.copilot %}prompts{% endif %}{% endraw %}/<name>.prompt.md` × 8
- Test: `tests/test_command_adapters.py`

Each: frontmatter `--- \n description: … \n ---`, thin body identical in intent to
the Claude file (cross-harness duplication is deliberate).

**TDD:**
- [ ] Test `test_copilot_prompts_gated`: render `copilot=False` → no `.github/prompts`;
  render `copilot=True` → all 8 `.github/prompts/<name>.prompt.md` exist.
- [ ] Run → FAIL.
- [ ] Create the 8 files.
- [ ] Run → PASS. (`test_shipped_commands_drift_clean` from Task 2 covers their refs.)
- [ ] Commit `feat: add Copilot prompt-file command adapters`.

### Task 4: AGENTS.md process-commands section + neutrality

**Files:**
- Modify: `template/{% raw %}{% if harnesses.agents_md %}AGENTS.md{% endif %}{% endraw %}.jinja`
- Test: `tests/test_command_adapters.py`

Append `## Process commands` listing the 8 commands as phase pointers (full slash
paths), noting AGENTS.md readers invoke by reading the phase.

**TDD:**
- [ ] Test `test_agents_md_lists_commands`: render `agents_md=True` → AGENTS.md
  contains `## Process commands` and each command name; render `agents_md=False`
  → AGENTS.md absent.
- [ ] Test `test_commands_are_neutral`: for every shipped command file + the
  AGENTS.md section, assert none of the neutrality word list appears.
- [ ] Run → FAIL (section absent).
- [ ] Add the section.
- [ ] Run → PASS.
- [ ] Commit `feat: list process commands in AGENTS.md adapter`.

### Task 5: README catalog + version bump

**Files:**
- Modify: `README.md` (harness catalog / status / tag row), `pyproject.toml`

**Steps:**
- [ ] Add command-adapters line to the harness/adapters section + mark v1.0.0
  in the status/roadmap.
- [ ] Bump `version = "0.9.0"` → `"1.0.0"`.
- [ ] Run full suite → all green.
- [ ] Commit `docs: document command adapters + bump to 1.0.0` (version bump lands
  before the tag).

---

## Self-review checklist
- [ ] Every command file uses full `docs/process/…` slash paths (drift-checkable).
- [ ] Negative tests exist for BOTH new SCAN_DIRs (not just a positive).
- [ ] No module-gated doc referenced by any command file.
- [ ] Neutrality test covers structural leaks, not only the word list.
- [ ] pyproject == 1.0.0 on the commit that will carry tag v1.0.0.
