import subprocess
import sys


def test_runner_lists_gate_when_module_on(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {"doc_drift_gate": True}})
    r = subprocess.run(
        [sys.executable, str(out / "scripts/process/gate_runner.py"), "--list"],
        cwd=out, capture_output=True, text=True,
    )
    assert "doc-drift-gate" in r.stdout


def test_runner_skips_gate_when_module_off(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    r = subprocess.run(
        [sys.executable, str(out / "scripts/process/gate_runner.py"), "--list"],
        cwd=out, capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr   # runner ran cleanly...
    assert "doc-drift-gate" not in r.stdout  # ...and simply listed no active gate


def test_runner_runs_and_passes_clean_tree(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {"doc_drift_gate": True}})
    r = subprocess.run([sys.executable, str(out / "scripts/process/gate_runner.py")], cwd=out)
    assert r.returncode == 0


def test_runner_finds_root_from_subdirectory(render, tmp_path):
    # audit finding: run from a subdir, the runner used to see no manifest,
    # activate zero gates, and report green — enforcement silently off.
    out = render(tmp_path, {"project_name": "d", "modules": {"doc_drift_gate": True}})
    r = subprocess.run(
        [sys.executable, str(out / "scripts/process/gate_runner.py")],
        cwd=out / "docs", capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    assert "doc-drift-gate" in r.stdout


def test_runner_fails_loud_without_manifest(render, tmp_path):
    # a missing manifest must be red with a diagnostic, not "0 gates passed"
    out = render(tmp_path, {"project_name": "d"})
    (out / ".copier-answers.yml").unlink()
    r = subprocess.run(
        [sys.executable, str(out / "scripts/process/gate_runner.py")],
        cwd=out, capture_output=True, text=True,
    )
    assert r.returncode == 1
    assert "copier-answers" in r.stderr


def test_runner_fails_loud_on_manifest_without_modules(render, tmp_path):
    # a corrupt/hand-pruned manifest must not disable enforcement silently
    out = render(tmp_path, {"project_name": "d"})
    answers = out / ".copier-answers.yml"
    answers.write_text("project_name: d\n")
    r = subprocess.run(
        [sys.executable, str(out / "scripts/process/gate_runner.py")],
        cwd=out, capture_output=True, text=True,
    )
    assert r.returncode == 1
    assert "modules" in r.stderr


def test_runner_all_modules_off_is_still_green(render, tmp_path):
    # legitimate zero-gate state: manifest present, every module false
    out = render(tmp_path, {"project_name": "d"})
    r = subprocess.run(
        [sys.executable, str(out / "scripts/process/gate_runner.py")],
        cwd=out, capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr


def test_workflow_rendered(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    assert (out / ".github/workflows/process-gates.yml").is_file()
