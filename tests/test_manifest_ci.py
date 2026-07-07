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
    # every module false: only the core gate(s) run, and pass on a clean tree
    out = render(tmp_path, {"project_name": "d"})
    r = subprocess.run(
        [sys.executable, str(out / "scripts/process/gate_runner.py")],
        cwd=out, capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr


def test_core_gate_runs_with_all_modules_off(render, tmp_path):
    # a core gate (module key None) guards a core artifact (docs/process/adr/),
    # so it must run even when every optional module is off — otherwise
    # decision-record integrity could silently go unchecked.
    out = render(tmp_path, {"project_name": "d"})
    r = subprocess.run(
        [sys.executable, str(out / "scripts/process/gate_runner.py"), "--list"],
        cwd=out, capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    assert "decision-records" in r.stdout
    assert "review" in r.stdout  # second core gate also always active
    assert "product-frame" in r.stdout  # third core gate (SP31)


def test_workflow_rendered(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    assert (out / ".github/workflows/process-gates.yml").is_file()


def test_runner_fails_clean_without_pyyaml(render, tmp_path):
    # audit coverage: the friendly "PyYAML is required" diagnostic (a documented
    # SP9 audit fix) had no regression test. Exec the runner with yaml made
    # unimportable -> exit 1 with the diagnostic, never a raw ImportError traceback.
    out = render(tmp_path, {"project_name": "d"})
    runner = out / "scripts/process/gate_runner.py"
    code = ("import sys; sys.modules['yaml'] = None; sys.argv = ['gate_runner', '.']; "
            f"exec(open({str(runner)!r}).read())")
    r = subprocess.run([sys.executable, "-c", code], cwd=out, capture_output=True, text=True)
    assert r.returncode == 1
    assert "PyYAML" in (r.stdout + r.stderr)
    assert "Traceback" not in r.stderr
