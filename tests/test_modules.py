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
