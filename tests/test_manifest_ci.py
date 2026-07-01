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


def test_workflow_rendered(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    assert (out / ".github/workflows/process-gates.yml").is_file()
