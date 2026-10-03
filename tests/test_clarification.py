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


# --- specs/: only the build input (plan.md, tasks.md) blocks; companions note ---

def _spec(root, rel, body):
    p = root / "specs/001-widget" / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")


def test_marker_in_research_is_note_with_file_and_line(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    _spec(out, "research.md", f"# Research\n\n{MARKER}\n\n[needs clarification]\n")
    _spec(out, "data-model.md", f"# Data model\n{MARKER}\n")
    r = _run(out)
    assert r.returncode == 0, r.stdout + r.stderr
    # one note per marker, clickable file:line; case-insensitive like everywhere
    assert "specs/001-widget/research.md:3:" in r.stdout
    assert "specs/001-widget/research.md:5:" in r.stdout
    assert "specs/001-widget/data-model.md:2:" in r.stdout
    assert "not a permission" in r.stdout  # a note never licenses an open load-bearing decision


def test_marker_in_spec_plan_and_tasks_still_blocks(render, tmp_path):
    for name in ("plan.md", "tasks.md"):
        out = render(tmp_path / name, {"project_name": "demo"})
        _spec(out, "research.md", f"{MARKER}\n")
        _spec(out, name, "# X\n\n[Needs Clarification: which store?]\n")
        r = _run(out)
        assert r.returncode == 1, name
        assert f"specs/001-widget/{name}:3" in r.stdout
        assert "research.md:1:" in r.stdout  # the companion note still prints beside the failure


def test_fenced_marker_in_specs_is_quotation(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    _spec(out, "plan.md", f"# Plan\n\n```\n{MARKER}\n```\n")
    _spec(out, "research.md", f"# Research\n\n~~~\n{MARKER}\n~~~\n")
    r = _run(out)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "research.md" not in r.stdout


def test_unreadable_spec_artifact_fails_not_passes(render, tmp_path):
    # a read error must never count as a passing check — for a companion too
    out = render(tmp_path, {"project_name": "demo"})
    (out / "specs/001-widget/research.md").mkdir(parents=True)  # unreadable as a file
    r = _run(out)
    assert r.returncode == 1
    assert "research.md: could not read" in r.stdout


def test_gate_runner_registers_clarification_as_core(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    r = subprocess.run(
        [sys.executable, str(out / "scripts/process/gate_runner.py"), "--list"],
        cwd=out, capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "clarification" in r.stdout.splitlines()
