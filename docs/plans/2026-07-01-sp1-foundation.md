# SP1 Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the SP1 foundation of `dev-process` — a copier template that installs a portable, harness-agnostic development process (neutral Markdown SSOT + CI enforcement + thin adapters for Claude Code / Copilot / AGENTS.md) with opt-in modules, working for greenfield and additive brownfield.

**Architecture:** The repo *is* a copier template. `copier.yml` asks which modules and harnesses to install; conditional Jinja filenames render only the chosen parts; `.copier-answers.yml` is the manifest. The methodology lives as neutral Markdown in `docs/process/` (the SSOT); each harness adapter carries a short inlined "kernel" digest plus a pointer to the SSOT. A manifest-aware CI job runs only the active modules' gates. TDD via copier's Python API driving renders into temp dirs and asserting on the output.

**Tech Stack:** copier (template engine + Python API), Python 3.11+, pytest, `uv`/`uvx` as runner, GitHub Actions, Jinja2 (via copier), YAML.

## Global Constraints

- Delivery is a **copier template only** — no second (bash) installer path. One owner (spec §2, decision "copier als kanonischer Weg").
- Neutral SSOT is **`docs/process/`** (rendered into the target repo), never `CLAUDE.md`. Adapters are thin pointers + inlined kernel (spec §4.2, §4.4).
- Conditional inclusion uses copier's **empty-rendered-filename** rule: the `.jinja` suffix stays OUTSIDE the `{% if %}`; when the condition is false the stem renders empty and the file is skipped (spec §7; verified pattern `{% if x %}name{% endif %}.jinja`).
- copier Python API (verified 2026-07-01): `copier.run_copy(src_path, dst_path, data=..., defaults=True, unsafe=True, quiet=True)`; `copier.run_update(dst_path, overwrite=True, ...)`.
- `_subdirectory: template` in `copier.yml` — only `template/` is rendered into targets; `docs/`, `tests/`, `README.md` of *this* repo are never shipped.
- Rendered target files must contain **no leftover Jinja** (`{{`, `{%`, `{#`) and **no Kenni-specifics** (`KenniNext`, `Kenni`, `user_id=1`, `Seb`, `Signal`).
- Answer namespaces: harnesses under `harnesses.*` (bool), modules under `modules.*` (bool). Claude Code adapter is always rendered (no question).
- Commits: Conventional Commits, atomic, imperative, `< 72` char subject. Every code-changing step ends with a commit.
- Every process/gate script is Python run via `uv run` (spec §10 decision #3); no bash-only gates.

---

## File Structure (after SP1)

```
dev-process/
├─ copier.yml                                   # questions: modules.* + harnesses.* + project vars
├─ pyproject.toml                               # dev deps: copier, pytest; ruff config
├─ BOOTSTRAP.md                                 # self-contained, harness-agnostic pull-mode entry
├─ README.md                                    # (exists) front-door
├─ docs/design/2026-07-01-foundation-design.md  # (exists) spec
├─ docs/plans/2026-07-01-sp1-foundation.md      # this plan
├─ .github/workflows/ci.yml                     # dogfood CI: pytest render matrix + ruff
├─ tests/
│  ├─ conftest.py                               # render()/update() helpers via copier API
│  ├─ fixtures/                                 # pre-populated + drift fixtures
│  ├─ test_spine.py                             # copier runs, answers file, subdirectory scope
│  ├─ test_core_docs.py                         # core SSOT present, headings, no jinja/kenni leak
│  ├─ test_adapters.py                          # claude always; conditional copilot/agents; kernel consistency
│  ├─ test_modules.py                           # doc-drift-gate on/off inclusion
│  ├─ test_manifest_ci.py                       # gate_runner reads manifest, activates gates
│  └─ test_brownfield.py                        # additive no-clobber + idempotent re-copy
└─ template/                                    # ← rendered into target repos
   ├─ .copier-answers.yml.jinja
   ├─ docs/process/
   │  ├─ mandatory-rules.md
   │  ├─ risk-tiers.md
   │  ├─ workflow.md
   │  ├─ commits.md
   │  ├─ journal-state-plans.md
   │  └─ adr/{README.md, template.md}
   ├─ CLAUDE.md.jinja
   ├─ {% if harnesses.copilot %}.github/copilot-instructions.md{% endif %}.jinja
   ├─ {% if harnesses.copilot %}.github/instructions/process.instructions.md{% endif %}.jinja
   ├─ {% if harnesses.agents_md %}AGENTS.md{% endif %}.jinja
   ├─ {% if modules.doc_drift_gate %}docs/process/modules/doc-drift-gate.md{% endif %}.jinja
   ├─ {% if modules.doc_drift_gate %}scripts/process/check_doc_drift.py{% endif %}.jinja
   ├─ scripts/process/gate_runner.py.jinja
   └─ .github/workflows/process-gates.yml.jinja
```

**Decision locks (from spec §10, resolved here):**
- **#2 Digest mechanism:** inline a short kernel block in each adapter, delimited by `<!-- KERNEL:START -->` / `<!-- KERNEL:END -->`; a consistency test asserts the three rendered blocks are byte-identical. Chosen over Jinja `{% include %}` to avoid loader-path risk; DRY is enforced by the test, not by sharing.
- **#3 Gate language:** Python, run via `uv run`.
- **#4 `doc-drift-gate` granularity:** opt-in module (not core), but it is the exemplar built in this plan.
- **#5 Slash-commands:** SP1 ships **no** `.claude/commands/`; the Claude adapter points at `docs/process/workflow.md`. Command portering is post-SP1.
- **Module scope:** this plan builds the *mechanism* end-to-end plus **one** exemplar opt-in module (`doc-drift-gate`). The other 7 modules (contract-first, feature-registry, parity-inventory, security-floor, kpis, audit, e2e-discipline) are follow-on plans that repeat the Task 5/6 pattern — explicitly out of SP1 scope.

---

## Task 1: copier spine + test harness

**Files:**
- Create: `pyproject.toml`
- Create: `copier.yml`
- Create: `tests/conftest.py`
- Create: `tests/test_spine.py`
- Create: `template/docs/process/mandatory-rules.md` (minimal stub, filled in Task 2)
- Create: `template/.copier-answers.yml.jinja`

**Interfaces:**
- Produces: `render(tmp_path, data: dict) -> Path` and `SRC` (repo root) in `conftest.py`, consumed by all later test tasks.
- Produces: `copier.yml` question keys `harnesses.copilot`, `harnesses.agents_md`, `modules.doc_drift_gate` (all bool, default false), `project_name` (str), consumed by all later tasks.

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "dev-process"
version = "0.1.0"
description = "Portable, harness-agnostic AI-assisted development process (copier template)"
requires-python = ">=3.11"

[dependency-groups]
dev = ["copier>=9.4", "pytest>=8", "ruff>=0.6"]

[tool.ruff]
line-length = 100

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Write the failing spine test**

```python
# tests/test_spine.py
def test_render_produces_core_and_answers(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    assert (out / "docs/process/mandatory-rules.md").is_file()
    answers = (out / ".copier-answers.yml").read_text()
    assert "_src_path" in answers            # copier stamps provenance
    assert "harnesses" in answers            # our namespaces recorded

def test_subdirectory_scope_excludes_repo_meta(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    assert not (out / "copier.yml").exists()   # template-only via _subdirectory
    assert not (out / "tests").exists()
    assert not (out / "docs/design").exists()
```

- [ ] **Step 3: Write `tests/conftest.py`**

```python
# tests/conftest.py
from pathlib import Path
import copier
import pytest

SRC = Path(__file__).resolve().parent.parent  # repo root (holds copier.yml)

def _copy(dst: Path, data: dict) -> Path:
    full = {"harnesses": {"copilot": False, "agents_md": False},
            "modules": {"doc_drift_gate": False}}
    full.update(data)
    copier.run_copy(str(SRC), str(dst), data=full, defaults=True, unsafe=True, quiet=True)
    return dst

@pytest.fixture
def render():
    return _copy
```

- [ ] **Step 4: Write `copier.yml`**

```yaml
_subdirectory: template
_answers_file: .copier-answers.yml

project_name:
  type: str
  help: "Human-readable project name"

harnesses:
  type: yaml
  help: "Which harness adapters to install (Claude Code is always installed)"
  default:
    copilot: false
    agents_md: false

modules:
  type: yaml
  help: "Which opt-in process modules to install"
  default:
    doc_drift_gate: false
```

- [ ] **Step 5: Write `template/.copier-answers.yml.jinja`**

```jinja
# Managed by copier — do not edit by hand. Records the installed process version.
{% raw %}{{ _copier_answers|to_nice_yaml }}{% endraw %}
```

- [ ] **Step 6: Write minimal `template/docs/process/mandatory-rules.md`**

```markdown
# Mandatory Rules

(placeholder — authored in Task 2)
```

- [ ] **Step 7: Run tests — expect PASS**

Run: `uv run pytest tests/test_spine.py -v`
Expected: 2 passed. If `run_copy` errors on `unsafe`, confirm copier>=9.4 installed via `uv sync`.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml copier.yml tests/ template/
git commit -m "feat: copier spine + render test harness"
```

---

## Task 2: Core SSOT process docs

**Files:**
- Modify: `template/docs/process/mandatory-rules.md`
- Create: `template/docs/process/risk-tiers.md`
- Create: `template/docs/process/workflow.md`
- Create: `template/docs/process/commits.md`
- Create: `template/docs/process/journal-state-plans.md`
- Create: `template/docs/process/adr/README.md`
- Create: `template/docs/process/adr/template.md`
- Create: `tests/test_core_docs.py`

**Interfaces:**
- Produces: the neutral SSOT files that adapters (Task 3/4) point to and the digest kernel (Task 3) is derived from. Required H2 anchors listed per file below are the contract the adapter kernel and doc-drift gate rely on.

- [ ] **Step 1: Write the failing structural test**

```python
# tests/test_core_docs.py
import re
CORE = ["mandatory-rules.md","risk-tiers.md","workflow.md","commits.md",
        "journal-state-plans.md","adr/README.md","adr/template.md"]
KENNI = ["KenniNext","Kenni","user_id=1","Seb","Signal","SvelteKit"]

def test_core_docs_present_and_clean(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    for rel in CORE:
        p = out / "docs/process" / rel
        assert p.is_file(), rel
        text = p.read_text()
        assert not re.search(r"{{|{%|{#", text), f"jinja leak in {rel}"
        for k in KENNI:
            assert k not in text, f"kenni-specific '{k}' leaked in {rel}"

def test_mandatory_rules_required_headings(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    text = (out / "docs/process/mandatory-rules.md").read_text()
    for h in ["Verification before assertion","Plan before substantive work",
              "One owner per behavior","Root cause before symptom","Atomic commits"]:
        assert h in text, h

def test_risk_tiers_matrix(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    text = (out / "docs/process/risk-tiers.md").read_text()
    for t in ["Tier 0","Tier 1","Tier 2","Tier 3","Tier 4"]:
        assert t in text, t
```

- [ ] **Step 2: Run test — expect FAIL** (`Tier 0` etc. absent)

Run: `uv run pytest tests/test_core_docs.py -v` → FAIL.

- [ ] **Step 3: Author `mandatory-rules.md`** (universal distillation; no Kenni-specifics)

```markdown
# Mandatory Rules

Binding. Earlier rules outrank later ones; check them in order.

1. **Verification before assertion.** Every claim about existing code (file, function, flag, behavior) needs a same-turn tool-call (read/search) or an explicit confidence tag: `[verified]` / `[assumption]`. On conflict, `[verified]` wins.
2. **Plan before substantive work.** Derive the risk tier (`risk-tiers.md`) from the real scope, not the diff size, and route accordingly. Tier 3+ needs a written plan before code.
3. **Contract/interface first for shared behavior.** Behavior that crosses a component or repo boundary needs its interface/contract defined before any consumer implements against it. (Enforced by the `contract-first` module when installed.)
4. **One owner per behavior; structural over additive.** Check existing code first. New overrides/wrappers/flags that duplicate an existing responsibility add accretion — find the owning layer and change it there. Two efforts on the same problem must declare *phase-of* or *supersede*, never run parallel.
5. **Tests prove acceptance.** Every feature/behavior change maps a test to the acceptance it claims. Exception: pure copy/formatting/doc-typo with no behavior change.
6. **Root cause before symptom.** Max two diagnostic attempts at a symptom, then stop and do a root-cause analysis. Ask "why does this happen?", not "how do I suppress it?".
7. **Review gate before merge to the main branch.** Merge only after the review required by the tier (`risk-tiers.md`) has run.
8. **Atomic commits, documented exceptions.** One logical change per commit, imperative Conventional-Commit subject. A skipped gate or dropped scope is named in the commit body.
```

- [ ] **Step 4: Author `risk-tiers.md`**

```markdown
# Risk Tiers

Scope — not code volume — sets the tier. User-visible, cross-component, API/interface, auth, or persistence changes are Tier 3+ even with a tiny diff.

| Tier | Scope | Route |
|---|---|---|
| **Tier 0** | No behavior change (docs, formatting, comments) | Direct commit |
| **Tier 1** | Local, isolated, reversible; single file/function | Quick flow: state goal + touched files + risk, then edit |
| **Tier 2** | Small feature/fix, no contract/persistence/auth impact | Quick flow + a test |
| **Tier 3** | User-visible, cross-component, or touches an interface/contract | Plan → execute → review before merge |
| **Tier 4** | Auth, persistence/migrations, security surface, or multi-repo contract | Plan + upfront design + review + (where configured) second-opinion review |

**Floor, not ceiling:** a label or convention may raise a tier; it never lowers the derived tier. Below the derived tier only with a one-line written justification.
```

- [ ] **Step 5: Author the remaining core docs** (each concise; content contract below)

`workflow.md` — required H2s: `## The cycle`, `## Brainstorm`, `## Plan`, `## Execute`, `## Review`, `## Quick`, `## Debug`. Each section: 2–4 sentences describing the phase as harness-neutral process (what enters, what it produces, when to use). The cycle: brainstorm (design + approval) → plan (zero-context task breakdown) → execute (task-by-task, TDD, commit per task) → review (gate before merge); quick = Tier 1–2 shortcut; debug = root-cause entry (Rule 6).

`commits.md` — required H2s: `## Message format`, `## Atomicity`, `## Branching`. Content: Conventional Commits (`feat|fix|docs|refactor|test|chore|perf`), imperative < 72-char subject; one logical change per commit; no direct commits to the main branch — feature branch, fast-forward-only merge after the tier's review gate; a git `pre-commit` hook guards the main branch (bypassable for automation).

`journal-state-plans.md` — required H2s: `## Journal`, `## Branch-scoped state`, `## Plans`. Content: `journal/YYYY-MM-DD.md` records *why* decisions were made (git shows *what*); `state/<branch-slug>.md` is per-branch working memory (active work, open risks, next action); `plans/YYYY-MM-DD-<feature>.md` holds the current plan, archived on merge. All under a repo-local `.process-work/` directory.

`adr/README.md` — one-paragraph explanation of ADRs + an index table (`| ADR | Title | Status |`) with a single seed row `| 0001 | Record architecture decisions | Accepted |`. Note: every new ADR file must be added to this index.

`adr/template.md` — headings `# ADR-NNNN: <title>`, `## Status`, `## Context`, `## Decision`, `## Consequences`.

- [ ] **Step 6: Run test — expect PASS**

Run: `uv run pytest tests/test_core_docs.py -v` → all pass.

- [ ] **Step 7: Commit**

```bash
git add template/docs/process tests/test_core_docs.py
git commit -m "feat: neutral SSOT process docs (rules, tiers, workflow, commits, journal, adr)"
```

---

## Task 3: Claude Code adapter + kernel digest

**Files:**
- Create: `template/CLAUDE.md.jinja`
- Create: `tests/test_adapters.py`

**Interfaces:**
- Produces: the kernel block delimited by `<!-- KERNEL:START -->` / `<!-- KERNEL:END -->` and the SSOT pointer, both reused verbatim by Task 4's adapters. The kernel text is the contract for the consistency test.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_adapters.py
import re
def _kernel(text):
    m = re.search(r"<!-- KERNEL:START -->(.*?)<!-- KERNEL:END -->", text, re.S)
    return m.group(1).strip() if m else None

def test_claude_adapter_always_present(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    p = out / "CLAUDE.md"
    assert p.is_file()
    text = p.read_text()
    assert "docs/process/" in text                 # pointer to SSOT
    assert _kernel(text) is not None               # inlined kernel
    assert "demo" in text                          # project_name interpolated
    assert not re.search(r"{{|{%|{#", text)        # no jinja leak
```

- [ ] **Step 2: Run test — expect FAIL** (`CLAUDE.md` absent)

Run: `uv run pytest tests/test_adapters.py::test_claude_adapter_always_present -v` → FAIL.

- [ ] **Step 3: Write `template/CLAUDE.md.jinja`**

```jinja
# {{ project_name }} — Claude Code anchor

This file is a thin adapter. The **authoritative** development process lives in
`docs/process/` (the neutral SSOT). Read it before substantive work:
`docs/process/mandatory-rules.md`, `risk-tiers.md`, `workflow.md`, `commits.md`.

<!-- KERNEL:START -->
## Always-on kernel

**Mandatory rules (full text: `docs/process/mandatory-rules.md`):**
1. Verify before asserting. 2. Plan before substantive work. 3. Contract/interface first.
4. One owner per behavior. 5. Tests prove acceptance. 6. Root cause before symptom.
7. Review gate before merge. 8. Atomic commits.

**Tier routing (full matrix: `docs/process/risk-tiers.md`):**
Tier 0 → direct commit · Tier 1–2 → quick flow · Tier 3+ → plan → execute → review.
Scope, not diff size, sets the tier.
<!-- KERNEL:END -->

For Claude Code specifics (skills, subagents), see `docs/process/workflow.md`.
```

- [ ] **Step 4: Run test — expect PASS**

Run: `uv run pytest tests/test_adapters.py::test_claude_adapter_always_present -v` → PASS.

- [ ] **Step 5: Commit**

```bash
git add template/CLAUDE.md.jinja tests/test_adapters.py
git commit -m "feat: Claude Code adapter with inlined kernel + SSOT pointer"
```

---

## Task 4: Conditional harness adapters (Copilot + AGENTS.md) + kernel consistency

**Files:**
- Create: `template/{% raw %}{% if harnesses.copilot %}.github/copilot-instructions.md{% endif %}{% endraw %}.jinja`
- Create: `template/{% raw %}{% if harnesses.copilot %}.github/instructions/process.instructions.md{% endif %}{% endraw %}.jinja`
- Create: `template/{% raw %}{% if harnesses.agents_md %}AGENTS.md{% endif %}{% endraw %}.jinja`
- Modify: `tests/test_adapters.py`

**Interfaces:**
- Consumes: the kernel block + SSOT pointer from Task 3 (same delimited text, verbatim).
- Produces: proof that conditional inclusion works via `harnesses.*` answers — the pattern Task 5 reuses for modules.

- [ ] **Step 1: Add the failing conditional + consistency tests**

```python
# tests/test_adapters.py  (append)
def test_copilot_conditional(render, tmp_path):
    off = render(tmp_path / "off", {"project_name": "d"})
    assert not (off / ".github/copilot-instructions.md").exists()
    on = render(tmp_path / "on", {"project_name": "d", "harnesses": {"copilot": True, "agents_md": False}})
    assert (on / ".github/copilot-instructions.md").is_file()
    assert (on / ".github/instructions/process.instructions.md").is_file()

def test_agents_md_conditional(render, tmp_path):
    on = render(tmp_path / "on", {"project_name": "d", "harnesses": {"copilot": False, "agents_md": True}})
    assert (on / "AGENTS.md").is_file()

def test_kernel_identical_across_adapters(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "harnesses": {"copilot": True, "agents_md": True}})
    blocks = [_kernel((out / f).read_text()) for f in
              ["CLAUDE.md", ".github/copilot-instructions.md", "AGENTS.md"]]
    assert blocks[0] and blocks.count(blocks[0]) == 3, "kernel must be byte-identical across adapters"
```

- [ ] **Step 2: Run test — expect FAIL** (files absent)

Run: `uv run pytest tests/test_adapters.py -v` → the 3 new tests FAIL.

- [ ] **Step 3: Create the Copilot global adapter**

File name (literal, on disk): `template/{% if harnesses.copilot %}.github/copilot-instructions.md{% endif %}.jinja`
Content — identical kernel block to Task 3 Step 3 (verbatim between the KERNEL markers), with this head/tail:

```jinja
# {{ project_name }} — GitHub Copilot instructions

Authoritative process: `docs/process/` (neutral SSOT). This file is an adapter.

<!-- KERNEL:START -->
## Always-on kernel

**Mandatory rules (full text: `docs/process/mandatory-rules.md`):**
1. Verify before asserting. 2. Plan before substantive work. 3. Contract/interface first.
4. One owner per behavior. 5. Tests prove acceptance. 6. Root cause before symptom.
7. Review gate before merge. 8. Atomic commits.

**Tier routing (full matrix: `docs/process/risk-tiers.md`):**
Tier 0 → direct commit · Tier 1–2 → quick flow · Tier 3+ → plan → execute → review.
Scope, not diff size, sets the tier.
<!-- KERNEL:END -->
```

- [ ] **Step 4: Create the Copilot path-scoped instructions**

File name: `template/{% if harnesses.copilot %}.github/instructions/process.instructions.md{% endif %}.jinja`

```jinja
---
applyTo: "**"
---
Follow the development process in `docs/process/`. Before substantive work, read
`mandatory-rules.md` and derive the tier from `risk-tiers.md`. Tier 3+ requires a
written plan under `.process-work/plans/` before code.
```

- [ ] **Step 5: Create the AGENTS.md adapter**

File name: `template/{% if harnesses.agents_md %}AGENTS.md{% endif %}.jinja` — same head + verbatim KERNEL block as Step 3, with an AGENTS.md-appropriate title (`# {{ project_name }} — agent instructions`) and a closing note: `Unlike Claude Code, most AGENTS.md readers do not auto-load nested files — read docs/process/ explicitly.`

- [ ] **Step 6: Run tests — expect PASS**

Run: `uv run pytest tests/test_adapters.py -v` → all pass (kernel byte-identical across the 3).

- [ ] **Step 7: Commit**

```bash
git add template tests/test_adapters.py
git commit -m "feat: conditional Copilot + AGENTS.md adapters with shared kernel"
```

---

## Task 5: Opt-in module mechanism + `doc-drift-gate` exemplar

**Files:**
- Create: `template/{% raw %}{% if modules.doc_drift_gate %}docs/process/modules/doc-drift-gate.md{% endif %}{% endraw %}.jinja`
- Create: `template/{% raw %}{% if modules.doc_drift_gate %}scripts/process/check_doc_drift.py{% endif %}{% endraw %}.jinja`
- Create: `tests/test_modules.py`
- Create: `tests/fixtures/drift/good.md`, `tests/fixtures/drift/bad.md`

**Interfaces:**
- Consumes: the conditional-filename pattern proven in Task 4.
- Produces: `check_doc_drift.py` exposing `find_drift(root: Path) -> list[str]` (returns human-readable drift messages; empty = clean) and a `__main__` that exits non-zero on drift. Consumed by Task 6's `gate_runner`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_modules.py
import subprocess, sys
def test_module_off_absent(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    assert not (out / "scripts/process/check_doc_drift.py").exists()
    assert not (out / "docs/process/modules/doc-drift-gate.md").exists()

def test_module_on_present(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {"doc_drift_gate": True}})
    assert (out / "scripts/process/check_doc_drift.py").is_file()
    assert (out / "docs/process/modules/doc-drift-gate.md").is_file()

def test_gate_detects_broken_reference(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {"doc_drift_gate": True}})
    script = out / "scripts/process/check_doc_drift.py"
    # clean tree: gate passes
    assert subprocess.run([sys.executable, str(script), str(out)]).returncode == 0
    # inject a doc that references a non-existent file → gate fails
    (out / "docs/process/broken.md").write_text("See [x](does/not/exist.py).")
    assert subprocess.run([sys.executable, str(script), str(out)]).returncode != 0
```

- [ ] **Step 2: Run test — expect FAIL**

Run: `uv run pytest tests/test_modules.py -v` → FAIL (files absent).

- [ ] **Step 3: Write the gate script** (no `{{`/`{%` so Jinja passes it through unchanged)

File name: `template/{% if modules.doc_drift_gate %}scripts/process/check_doc_drift.py{% endif %}.jinja`

```python
#!/usr/bin/env python3
"""doc-drift-gate: verify that repo-relative path references in docs/process/
and the harness adapters actually resolve. Portable, language-agnostic."""
from __future__ import annotations
import re, sys
from pathlib import Path

LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")          # markdown links
BACKTICK = re.compile(r"`([^`]+\.[a-z]{1,5})`")      # `path/to/file.ext`
SCAN_DIRS = ["docs/process"]
SCAN_FILES = ["CLAUDE.md", "AGENTS.md", ".github/copilot-instructions.md"]

def _candidates(text: str):
    for m in LINK.finditer(text):
        yield m.group(1)
    for m in BACKTICK.finditer(text):
        yield m.group(1)

def _is_local_path(ref: str) -> bool:
    return not ref.startswith(("http://", "https://", "#", "mailto:")) and "/" in ref

def find_drift(root: Path) -> list[str]:
    targets: list[Path] = []
    for d in SCAN_DIRS:
        targets += (root / d).rglob("*.md")
    for f in SCAN_FILES:
        if (root / f).is_file():
            targets.append(root / f)
    problems: list[str] = []
    for doc in targets:
        for ref in _candidates(doc.read_text(encoding="utf-8")):
            ref_clean = ref.split("#", 1)[0].strip()
            if not _is_local_path(ref_clean):
                continue
            if not (root / ref_clean).exists():
                problems.append(f"{doc.relative_to(root)} -> missing '{ref_clean}'")
    return problems

def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    problems = find_drift(root)
    if problems:
        print("doc-drift-gate: broken references:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("doc-drift-gate: OK")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Write the module doc**

File name: `template/{% if modules.doc_drift_gate %}docs/process/modules/doc-drift-gate.md{% endif %}.jinja`

```jinja
# Module: doc-drift-gate

Verifies that repo-relative path references in `docs/process/` and the harness
adapters resolve to real files. Runs in CI via `process-gates` and locally via
`uv run scripts/process/check_doc_drift.py`.

Installed for **{{ project_name }}**. Rationale: anchors that name files/paths must
stay true as code moves (mandatory rule 1). Non-resolving references fail the gate.
```

- [ ] **Step 5: Run tests — expect PASS**

Run: `uv run pytest tests/test_modules.py -v` → all pass.

- [ ] **Step 6: Commit**

```bash
git add template tests/test_modules.py tests/fixtures
git commit -m "feat: opt-in module mechanism + doc-drift-gate exemplar"
```

---

## Task 6: Manifest-aware CI (`gate_runner` + `process-gates` workflow)

**Files:**
- Create: `template/scripts/process/gate_runner.py.jinja`
- Create: `template/.github/workflows/process-gates.yml.jinja`
- Create: `tests/test_manifest_ci.py`

**Interfaces:**
- Consumes: `.copier-answers.yml` (the manifest) and `check_doc_drift.py`'s `__main__` (Task 5).
- Produces: `gate_runner.py` exposing `active_gates(answers: dict) -> list[str]` and a `__main__` that runs each active gate as a subprocess, exiting non-zero if any fails.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_manifest_ci.py
import subprocess, sys
def test_runner_lists_gate_when_module_on(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {"doc_drift_gate": True}})
    r = subprocess.run([sys.executable, str(out/"scripts/process/gate_runner.py"), "--list"],
                       cwd=out, capture_output=True, text=True)
    assert "doc-drift-gate" in r.stdout

def test_runner_skips_gate_when_module_off(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    r = subprocess.run([sys.executable, str(out/"scripts/process/gate_runner.py"), "--list"],
                       cwd=out, capture_output=True, text=True)
    assert "doc-drift-gate" not in r.stdout

def test_runner_runs_and_passes_clean_tree(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {"doc_drift_gate": True}})
    r = subprocess.run([sys.executable, str(out/"scripts/process/gate_runner.py")], cwd=out)
    assert r.returncode == 0

def test_workflow_rendered(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    assert (out / ".github/workflows/process-gates.yml").is_file()
```

- [ ] **Step 2: Run test — expect FAIL**

Run: `uv run pytest tests/test_manifest_ci.py -v` → FAIL.

- [ ] **Step 3: Write `gate_runner.py.jinja`** (contains no `{{`/`{%`)

File name: `template/scripts/process/gate_runner.py.jinja`

```python
#!/usr/bin/env python3
"""Manifest-aware gate runner. Reads .copier-answers.yml and runs only the
gates whose module is active. Language-agnostic; each gate is a subprocess."""
from __future__ import annotations
import subprocess, sys
from pathlib import Path
import yaml

# gate-name -> (module answer key, command relative to repo root)
GATES = {
    "doc-drift-gate": ("doc_drift_gate", [sys.executable, "scripts/process/check_doc_drift.py", "."]),
}

def _answers(root: Path) -> dict:
    f = root / ".copier-answers.yml"
    return yaml.safe_load(f.read_text()) if f.is_file() else {}

def active_gates(answers: dict) -> list[str]:
    mods = (answers or {}).get("modules", {}) or {}
    return [name for name, (key, _cmd) in GATES.items() if mods.get(key)]

def main() -> int:
    root = Path(".").resolve()
    answers = _answers(root)
    active = active_gates(answers)
    if "--list" in sys.argv:
        for g in active:
            print(g)
        return 0
    failed = []
    for name in active:
        _key, cmd = GATES[name]
        print(f"== running {name} ==")
        if subprocess.run(cmd, cwd=root).returncode != 0:
            failed.append(name)
    if failed:
        print(f"FAILED gates: {', '.join(failed)}")
        return 1
    print(f"all {len(active)} active gate(s) passed")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
```

Note: add `pyyaml` to the *target* project's expectations — the workflow (Step 4) installs it. (`.copier-answers.yml` is YAML; stdlib has no YAML reader.)

- [ ] **Step 4: Write `process-gates.yml.jinja`**

File name: `template/.github/workflows/process-gates.yml.jinja`

```yaml
name: process-gates
on: [push, pull_request]
jobs:
  gates:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install pyyaml
      - run: python scripts/process/gate_runner.py
```

- [ ] **Step 5: Run tests — expect PASS**

Run: `uv run pytest tests/test_manifest_ci.py -v` → all pass. (`gate_runner` import of `yaml` requires `pyyaml` in the dev env — add via `uv add --group dev pyyaml` if the subprocess fails on import.)

- [ ] **Step 6: Commit**

```bash
git add template/scripts/process/gate_runner.py.jinja template/.github/workflows/process-gates.yml.jinja tests/test_manifest_ci.py
git commit -m "feat: manifest-aware gate runner + process-gates CI workflow"
```

---

## Task 7: Brownfield additivity + idempotency guarantees

**Files:**
- Create: `tests/fixtures/existing/README.md`, `tests/fixtures/existing/AGENTS.md`
- Create: `tests/test_brownfield.py`
- Modify: `tests/conftest.py` (add `render_into` helper that copies a fixture tree first)

**Interfaces:**
- Consumes: `render()` and `SRC` from Task 1.
- Produces: `render_into(dst, seed_dir, data)` — seeds `dst` from a fixture, then runs copier into it.

- [ ] **Step 1: Add `render_into` to `conftest.py`**

```python
# tests/conftest.py  (append)
import shutil
@pytest.fixture
def render_into():
    def _f(dst: Path, seed: Path, data: dict) -> Path:
        shutil.copytree(seed, dst, dirs_exist_ok=True)
        return _copy(dst, data)
    return _f
```

- [ ] **Step 2: Create fixtures + failing tests**

`tests/fixtures/existing/README.md` content: `# my existing project` (sentinel line).
`tests/fixtures/existing/AGENTS.md` content: `# pre-existing agents file — keep me`.

```python
# tests/test_brownfield.py
from pathlib import Path
FIX = Path(__file__).parent / "fixtures/existing"

def test_existing_readme_not_clobbered(render_into, tmp_path):
    out = render_into(tmp_path, FIX, {"project_name": "d"})
    assert "my existing project" in (out / "README.md").read_text()

def test_existing_agents_md_preserved(render_into, tmp_path):
    # request the agents_md adapter, but a user AGENTS.md already exists
    out = render_into(tmp_path, FIX, {"project_name": "d",
                                      "harnesses": {"copilot": False, "agents_md": True}})
    assert "keep me" in (out / "AGENTS.md").read_text()

def test_idempotent_second_copy(render_into, tmp_path):
    out = render_into(tmp_path, FIX, {"project_name": "d"})
    before = {p: p.read_bytes() for p in out.rglob("*") if p.is_file()}
    _ = render_into(out, FIX, {"project_name": "d"})  # copy again in place
    after = {p: p.read_bytes() for p in out.rglob("*") if p.is_file()}
    assert before.keys() == after.keys() and all(before[k] == after[k] for k in before)
```

- [ ] **Step 3: Run tests — expect PASS or documented conflict behavior**

Run: `uv run pytest tests/test_brownfield.py -v`
Expected: `test_existing_readme_not_clobbered` PASS (copier does not ship a `README.md` into targets, so no collision). `test_existing_agents_md_preserved`: copier prompts/skips on conflict — with `defaults=True` it does NOT overwrite existing files unless `overwrite=True`; assert it kept the user's content. If copier's default in this version overwrites, set the conftest `_copy` to pass `overwrite=False` explicitly and re-run. `test_idempotent_second_copy` PASS.

- [ ] **Step 4: If needed, pin non-destructive default**

If Step 3 shows overwrite, edit `tests/conftest.py` `_copy` to add `overwrite=False` to `run_copy`, and add a one-line note to `README.md` that brownfield installs are non-destructive by default. Re-run.

- [ ] **Step 5: Commit**

```bash
git add tests/conftest.py tests/test_brownfield.py tests/fixtures/existing
git commit -m "test: guarantee additive brownfield drop-in + idempotency"
```

---

## Task 8: BOOTSTRAP.md, README finalization, dogfood CI

**Files:**
- Create: `BOOTSTRAP.md`
- Modify: `README.md`
- Create: `.github/workflows/ci.yml`
- Create: `tests/test_bootstrap.py`

**Interfaces:**
- Consumes: everything above (this task ships the human/agent front-door and the repo's own CI).

- [ ] **Step 1: Write the failing bootstrap test**

```python
# tests/test_bootstrap.py
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
def test_bootstrap_has_exact_copier_command():
    text = (ROOT / "BOOTSTRAP.md").read_text()
    assert "uvx copier copy gh:Crashman1983/dev-process ." in text
    assert "BOOTSTRAP" in (ROOT / "README.md").read_text()
```

- [ ] **Step 2: Run test — expect FAIL**

Run: `uv run pytest tests/test_bootstrap.py -v` → FAIL.

- [ ] **Step 3: Write `BOOTSTRAP.md`** (self-contained, harness-agnostic — the pull-mode entry)

```markdown
# BOOTSTRAP — set up the dev-process in this repository

This file is self-contained. Any coding agent, in any harness, can follow it —
you do not need a pre-installed adapter.

## What this does
Installs a portable development process: a neutral methodology SSOT under
`docs/process/`, CI gates, and thin adapters for Claude Code / GitHub Copilot /
AGENTS.md. Works in an empty repo (greenfield) or an existing one (brownfield,
additive — it will not overwrite your files).

## Do this
1. Ensure `uv` is available (`https://docs.astral.sh/uv/`). No other dependency.
2. From the target repository root, run:

       uvx copier copy gh:Crashman1983/dev-process .

3. Answer the prompts: `project_name`, which **harnesses** to install
   (`copilot`, `agents_md`; Claude Code is always installed), and which **modules**
   to enable (e.g. `doc_drift_gate`).
4. Commit the result. Read `docs/process/mandatory-rules.md` and `risk-tiers.md`
   before further work.

## Later
Add a module or pull an updated process version: edit `.copier-answers.yml`
(or re-answer) and run `uvx copier update`.
```

- [ ] **Step 4: Update `README.md`** — replace the "Geplante Nutzung (SP1)" status note: change status line to "SP1 implemented" and add a one-line link to `BOOTSTRAP.md`. Keep the rest.

- [ ] **Step 5: Write dogfood CI `.github/workflows/ci.yml`**

```yaml
name: ci
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv sync
      - run: uv run ruff check .
      - run: uv run pytest -v
```

- [ ] **Step 6: Run the full suite — expect PASS**

Run: `uv run pytest -v` → all tasks' tests green. `uv run ruff check .` → clean.

- [ ] **Step 7: Commit**

```bash
git add BOOTSTRAP.md README.md .github/workflows/ci.yml tests/test_bootstrap.py
git commit -m "feat: BOOTSTRAP entry, dogfood CI, README finalization"
```

---

## Manual verification (after Task 8)

Prove the real end-to-end install once, by hand (copier CLI, not the test API):

```bash
# greenfield
mkdir /tmp/gf && cd /tmp/gf && git init -q
uvx copier copy --defaults --data project_name=Green gh:Crashman1983/dev-process .
test -f docs/process/mandatory-rules.md && test -f CLAUDE.md && echo OK

# with a module + copilot
uvx copier copy --defaults \
  --data project_name=Green --data 'modules={"doc_drift_gate": true}' \
  --data 'harnesses={"copilot": true, "agents_md": false}' \
  gh:Crashman1983/dev-process /tmp/gf2
python /tmp/gf2/scripts/process/gate_runner.py --list   # → doc-drift-gate
```

Record the outcome in `.process-work/journal/` once the process is self-installed (dogfooding).

---

## Self-Review (completed)

- **Spec coverage:** §4.2 core SSOT → Task 2; §4.4 adapters (Claude/Copilot/AGENTS.md) + digest → Tasks 3–4; §4.3 module mechanism + exemplar → Task 5; §4.5 manifest + §4.6 manifest-aware CI → Task 6; §5.2 additive brownfield + §7 idempotency → Task 7; §4.7 BOOTSTRAP + §6 dogfood testing → Tasks 1/8. §4.3's other 7 modules are explicitly out of SP1 scope (follow-on plans). SP2/SP3 remain extension points (not implemented) — correct per spec §2.
- **Placeholder scan:** the only intentionally-deferred content is the prose of `workflow.md`/`commits.md`/`journal-state-plans.md`/`adr/*` (Task 2 Step 5), given as exact required-heading + required-substance contracts with a structural test — not "add appropriate content". `mandatory-rules.md` and `risk-tiers.md` are inlined in full as the pattern exemplars.
- **Type/name consistency:** `find_drift(root)` (Task 5) and `active_gates(answers)`/`GATES` (Task 6) are used consistently; answer keys `harnesses.copilot`, `harnesses.agents_md`, `modules.doc_drift_gate` match across `copier.yml` (Task 1), conditional filenames (Tasks 4–5), and `gate_runner` (Task 6); the KERNEL-marker contract is shared by Tasks 3–4.
```
