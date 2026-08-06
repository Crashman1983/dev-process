"""process_context.py (core): deterministic session orientation — one JSON
call instead of exploratory reads (the token-lean pass)."""
import json
import subprocess
import sys


def _run(out):
    r = subprocess.run(
        [sys.executable, str(out / "scripts/process/process_context.py"), "."],
        cwd=out, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return json.loads(r.stdout)


def _git(out):
    subprocess.run(["git", "init", "-q", "-b", "feat-x"], cwd=out, check=True)


def test_core_tool_renders_always(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    assert (out / "scripts/process/process_context.py").is_file()


def test_empty_project_yields_clean_json(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    ctx = _run(out)
    assert ctx["active_plans"] == []
    assert ctx["spec_features"] == []
    assert ctx["inbox_items"] == 0


def test_context_names_next_task_and_markers(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {"speckit": True}})
    _git(out)
    d = out / "specs/001-widget"
    d.mkdir(parents=True)
    (d / "plan.md").write_text("# Plan\n\ntier: 2\nissue: #7\n")
    (d / "spec.md").write_text("# Spec\n\n[NEEDS CLARIFICATION: auth?]\n")
    (d / "tasks.md").write_text(
        "# Tasks\n\n- [x] T001 Test widget in tests/test_widget.py\n"
        "- [ ] T002 Implement widget in src/widget.py\n"
        "- [ ] T003 Docs\n")
    ctx = _run(out)
    feat = ctx["spec_features"][0]
    assert feat["tier"] == 2 and feat["issue"] == "#7"
    assert feat["tasks_done"] == 1 and feat["tasks_open"] == 2
    assert feat["next_task"].startswith("T002")
    assert feat["unresolved_markers"] == 1
    assert ctx["branch"] == "feat-x"


def test_context_reads_active_plans_and_inbox(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    p = out / ".process-work/plans"
    p.mkdir(parents=True, exist_ok=True)
    (p / "2026-08-06-thing.md").write_text("# Plan\n\ntier: 3\nissue: #9\n")
    (out / ".process-work/inbox.md").write_text("- fix the flaky test\n- docs\n")
    ctx = _run(out)
    assert ctx["active_plans"][0]["tier"] == 3
    assert ctx["inbox_items"] == 2


def test_prime_and_execute_point_to_context_tool(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    prime = (out / ".claude/commands/prime.md").read_text()
    execute = (out / ".claude/commands/execute.md").read_text()
    assert "process_context.py" in prime
    assert "never the whole journal" in prime  # the prime diet
    assert "process_context.py" in execute
    assert "checkbox" in execute  # progress-in-the-artifact
