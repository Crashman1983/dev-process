import subprocess

import yaml


def test_script_present_with_github_ci(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "ci": {"github": True, "gitlab": False}})
    p = out / "scripts/process/setup_branch_protection.sh"
    assert p.is_file()
    r = subprocess.run(["bash", "-n", str(p)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    text = p.read_text()
    # non-destructive merge path + honest failure guidance are load-bearing
    assert "required_status_checks/contexts" in text
    assert "paid" in text and "Manual path" in text


def test_script_absent_without_github_ci(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "ci": {"github": False, "gitlab": True}})
    assert not (out / "scripts/process/setup_branch_protection.sh").exists()


def test_job_id_matches_required_check_context(render, tmp_path):
    # the Actions job id IS the status-check context; docs and the setup script
    # both say `process-gates`, so the job must be named exactly that (a job
    # named `gates` would make the documented required check never satisfiable).
    out = render(tmp_path, {"project_name": "d", "ci": {"github": True, "gitlab": False}})
    wf = yaml.safe_load((out / ".github/workflows/process-gates.yml").read_text())
    assert "process-gates" in wf["jobs"], wf["jobs"].keys()
    script = (out / "scripts/process/setup_branch_protection.sh").read_text()
    assert 'CONTEXT="process-gates"' in script
