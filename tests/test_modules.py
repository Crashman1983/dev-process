import subprocess
import sys


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
    # inject a doc that references a non-existent file -> gate fails
    (out / "docs/process/broken.md").write_text("See [x](does/not/exist.py).")
    assert subprocess.run([sys.executable, str(script), str(out)]).returncode != 0


def test_gate_skips_runtime_process_work_paths(render, tmp_path):
    # .process-work/ files are runtime working memory, never shipped — a doc
    # referencing one literally (e.g. .process-work/inbox.md) must not be flagged
    out = render(tmp_path, {"project_name": "d", "modules": {"doc_drift_gate": True}})
    script = out / "scripts/process/check_doc_drift.py"
    (out / "docs/process/conv.md").write_text("Capture in `.process-work/inbox.md`.")
    assert subprocess.run([sys.executable, str(script), str(out)]).returncode == 0


def test_gate_runner_leaves_no_pycache(render, tmp_path):
    # the gates' sibling imports must not litter the adopter repo with
    # untracked __pycache__ (gate_runner sets PYTHONDONTWRITEBYTECODE)
    import subprocess
    import sys
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    r = subprocess.run([sys.executable, str(out / "scripts/process/gate_runner.py")],
                       cwd=out, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert not (out / "scripts/process/__pycache__").exists()


def test_gate_runner_names_hand_edited_manifest_cause(render, tmp_path):
    # SP52: module enabled but script missing (the hand-edited-answers trap)
    # must name the likely cause, not just "can't open file"
    import subprocess
    import sys
    out = render(tmp_path, {"project_name": "d",
                            "modules": {"telemetry": True}})
    (out / "scripts/process/check_telemetry.py").unlink()
    r = subprocess.run([sys.executable, str(out / "scripts/process/gate_runner.py")],
                       cwd=out, capture_output=True, text=True)
    assert r.returncode == 1
    assert "hand" in r.stderr and "copier update" in r.stderr
