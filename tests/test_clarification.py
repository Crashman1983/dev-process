"""clarification gate (core): the [NEEDS CLARIFICATION] marker floor — a
marker in an active plan is hard, in an active design a note, in the archive
history (design: spec-deepening, borrowed from Spec Kit's clarify step)."""
import subprocess
import sys

PLANS = ".process-work/plans"
MARKER = "[NEEDS CLARIFICATION: which auth provider?]"


def _run(root):
    return subprocess.run(
        [sys.executable, str(root / "scripts/process/check_clarification.py"), "."],
        cwd=root,
        capture_output=True,
        text=True,
    )


def _write(root, rel, body):
    p = root / PLANS / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")


def test_clean_render_passes(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    r = _run(out)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "clarification: OK" in r.stdout


def test_marker_in_active_plan_is_hard(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    _write(out, "2026-08-06-widget.md", f"# Plan\n\ntier: 2\n\n{MARKER}\n")
    r = _run(out)
    assert r.returncode == 1
    assert "2026-08-06-widget.md:5" in r.stdout  # file:line, clickable
    assert "active plan" in r.stdout


def test_marker_in_active_design_is_note_only(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    _write(out, "design-widget.md", f"# Design\n\n{MARKER}\n{MARKER}\n")
    r = _run(out)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "note" in r.stdout and "2 unresolved" in r.stdout


def test_archived_marker_is_history(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    _write(out, "archive/2026-01-01-old.md", f"# Plan\n\ntier: 2\n{MARKER}\n")
    _write(out, "archive/design-old.md", f"# Design\n{MARKER}\n")
    r = _run(out)
    assert r.returncode == 0, r.stdout + r.stderr


def test_fenced_marker_is_quotation(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    _write(out, "2026-08-06-doc.md",
           f"# Plan\n\ntier: 2\n\n```\n{MARKER}\n```\n")
    r = _run(out)
    assert r.returncode == 0, r.stdout + r.stderr


def test_case_and_bare_form_do_not_escape(render, tmp_path):
    # [needs clarification] without colon/question must still be caught —
    # a spelling nuance must not produce a false-green
    out = render(tmp_path, {"project_name": "demo"})
    _write(out, "2026-08-06-case.md", "# Plan\n\n[needs clarification]\n")
    r = _run(out)
    assert r.returncode == 1


def test_gate_runner_registers_clarification_as_core(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    r = subprocess.run(
        [sys.executable, str(out / "scripts/process/gate_runner.py"), "--list"],
        cwd=out, capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "clarification" in r.stdout.splitlines()
