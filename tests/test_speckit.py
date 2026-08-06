"""speckit module (standard, default-on): Spec Kit as the Tier 2+
specification path — rendered overrides, constitution pointer with gate
guard, deterministic test-task floor, clarification on specs/, publish-and-
prune merge ritual."""
import subprocess
import sys

CONST = ".specify/memory/constitution.md"
OVR = ".specify/templates/overrides"


def _render(render, tmp_path, on=True):
    return render(tmp_path, {"project_name": "d", "modules": {"speckit": on}})


def _gate(out):
    return subprocess.run(
        [sys.executable, str(out / "scripts/process/check_speckit.py"), "."],
        cwd=out, capture_output=True, text=True)


def _clar(out):
    return subprocess.run(
        [sys.executable, str(out / "scripts/process/check_clarification.py"), "."],
        cwd=out, capture_output=True, text=True)


def test_module_renders_overrides_and_pointer(render, tmp_path):
    out = _render(render, tmp_path)
    spec_ovr = (out / OVR / "spec-template.md").read_text()
    tasks_ovr = (out / OVR / "tasks-template.md").read_text()
    const = (out / CONST).read_text()
    # EARS + DoR twins in the spec override (one acceptance grammar)
    assert "EARS" in spec_ovr and "shall" in spec_ovr
    assert "invalidation/cleanup" in spec_ovr
    assert "Success Criteria" in spec_ovr and "SC-001" in spec_ovr
    # the upstream "tests optional" stance is inverted
    assert "Tests are MANDATORY" in tasks_ovr
    assert "Checkpoint" in tasks_ovr
    # constitution is a pointer, never authored principles
    assert "DEV-PROCESS-CONSTITUTION-POINTER" in const
    assert "mandatory-rules.md" in const
    assert "Do NOT run `/speckit-constitution`" in const


def test_module_off_renders_nothing(render, tmp_path):
    out = _render(render, tmp_path, on=False)
    assert not (out / ".specify").exists()
    assert not (out / "scripts/process/check_speckit.py").exists()
    assert not (out / "scripts/process/publish_and_prune.py").exists()


def test_gate_soft_before_init_is_impossible_here(render, tmp_path):
    # the module renders .specify/ itself (pointer + overrides), so the gate
    # always has the pointer to verify on a fresh render — and passes
    out = _render(render, tmp_path)
    r = _gate(out)
    assert r.returncode == 0, r.stdout + r.stderr


def test_gate_fails_when_pointer_replaced(render, tmp_path):
    # someone ran /speckit-constitution: generated principles replace the
    # pointer — a second truth beside the gated one
    out = _render(render, tmp_path)
    (out / CONST).write_text("# My Constitution\n\n## Principles\nI. Be nice.\n")
    r = _gate(out)
    assert r.returncode == 1
    assert "pointer marker missing" in r.stdout


def test_gate_fails_story_phase_without_test_task(render, tmp_path):
    out = _render(render, tmp_path)
    d = out / "specs/001-widget"
    d.mkdir(parents=True)
    (d / "tasks.md").write_text(
        "# Tasks\n\n## Phase 3: User Story 1 — widget (P1)\n\n"
        "- [ ] T001 [US1] Implement widget in src/widget.py\n")
    r = _gate(out)
    assert r.returncode == 1
    assert "no test task" in r.stdout and "rule 5" in r.stdout


def test_gate_passes_story_phase_with_test_task(render, tmp_path):
    out = _render(render, tmp_path)
    d = out / "specs/001-widget"
    d.mkdir(parents=True)
    (d / "tasks.md").write_text(
        "# Tasks\n\n## Phase 3: User Story 1 — widget (P1)\n\n"
        "- [ ] T001 [US1] Test: failing test for AC-1 in tests/test_widget.py\n"
        "- [ ] T002 [US1] Implement widget in src/widget.py\n"
        "\n## Final phase: Polish\n\n- [ ] T003 Update docs\n")
    r = _gate(out)
    assert r.returncode == 0, r.stdout
    # unchecked tasks are the deterministic completeness signal (converge diet)
    assert "unchecked task(s)" in r.stdout


def test_clarification_marker_in_spec_is_note_in_plan_is_hard(render, tmp_path):
    out = _render(render, tmp_path)
    d = out / "specs/001-widget"
    d.mkdir(parents=True)
    (d / "spec.md").write_text("# Spec\n\n[NEEDS CLARIFICATION: which auth?]\n")
    r = _clar(out)
    assert r.returncode == 0, r.stdout
    assert "speckit-clarify" in r.stdout  # visible note
    (d / "plan.md").write_text("# Plan\n\n[NEEDS CLARIFICATION: which auth?]\n")
    r = _clar(out)
    assert r.returncode == 1
    assert "unclarified spec" in r.stdout


def test_commands_repointed_when_module_on(render, tmp_path):
    out = _render(render, tmp_path)
    brainstorm = (out / ".claude/commands/brainstorm.md").read_text()
    plan = (out / ".claude/commands/plan.md").read_text()
    assert "speckit-specify" in brainstorm and "speckit-clarify" in brainstorm
    assert "tier first" in brainstorm  # kernel duty travels into the wrapper
    assert "speckit-plan" in plan and "speckit-tasks" in plan
    assert "tier: N" in plan and "issue: <ref>" in plan
    # replacement, not parallel operation: the old design-template path is gone
    assert "design-template.md" not in brainstorm


def test_commands_keep_fallback_when_module_off(render, tmp_path):
    out = _render(render, tmp_path, on=False)
    brainstorm = (out / ".claude/commands/brainstorm.md").read_text()
    assert "design-template.md" in brainstorm
    assert "speckit" not in brainstorm


def test_module_doc_pins_version_and_exit_scenario(render, tmp_path):
    out = _render(render, tmp_path)
    doc = (out / "docs/process/modules/speckit.md").read_text()
    assert "specify-cli==" in doc  # pinned, vendored dependency
    assert "speckit-implement" in doc  # excluded skills named
    assert "Exit scenario" in doc and "freeze the pin" in doc
    assert "Tier 3" in doc  # analyze/converge reserved for Tier 3 (token economy)
    assert "publish_and_prune.py" in doc
    assert "feature.json" in doc  # gitignored per-checkout state


def test_publish_and_prune_refuses_without_issue_or_sc_accounting(render, tmp_path):
    out = _render(render, tmp_path)
    d = out / "specs/001-widget"
    d.mkdir(parents=True)
    (d / "spec.md").write_text("# Spec\n\n- SC-001: users finish in 2 min\n")
    (d / "plan.md").write_text("# Plan\n\ntier: 2\n")
    r = subprocess.run(
        [sys.executable, str(out / "scripts/process/publish_and_prune.py"), "001-widget"],
        cwd=out, capture_output=True, text=True)
    assert r.returncode == 1
    assert "no issue: ref" in r.stderr
    assert (d / "spec.md").is_file()  # nothing pruned on refusal
    (d / "plan.md").write_text("# Plan\n\ntier: 2\nissue: #7\n")
    r = subprocess.run(
        [sys.executable, str(out / "scripts/process/publish_and_prune.py"), "001-widget"],
        cwd=out, capture_output=True, text=True)
    assert r.returncode == 1
    assert "SC-001" in r.stderr  # unaccounted SC blocks the prune
    assert (d / "spec.md").is_file()


def test_gate_runner_lists_speckit(render, tmp_path):
    out = _render(render, tmp_path)
    r = subprocess.run(
        [sys.executable, str(out / "scripts/process/gate_runner.py"), "--list"],
        cwd=out, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "speckit" in r.stdout.splitlines()


def test_workflow_phases_point_to_speckit(render, tmp_path):
    out = _render(render, tmp_path)
    text = (out / "docs/process/workflow.md").read_text()
    assert "speckit-specify" in text and "speckit-tasks" in text
    out2 = _render(render, tmp_path / "off", on=False)
    assert "speckit" not in (out2 / "docs/process/workflow.md").read_text()
