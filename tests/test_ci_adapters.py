# CI providers are the transport of enforcement (design: sp7-ci-adapters):
# `ci.*` decides which pipeline file invokes gate_runner.py, never which gates
# run — that stays with `modules.*`.


def test_github_workflow_rendered_by_default(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    assert (out / ".github/workflows/process-gates.yml").is_file()


def test_github_off_renders_no_workflow_anywhere(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "ci": {"github": False, "gitlab": False}})
    assert not (out / ".github/workflows").exists()
    assert not list(out.rglob("process-gates.yml"))


def test_gitlab_off_by_default_no_gitlab_files(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    assert not (out / ".gitlab-ci.yml").exists()
    assert not (out / ".gitlab").exists()


def test_gitlab_on_renders_shim_and_includable_job(render, tmp_path):
    # the job lives in an includable file that never collides with a
    # brownfield root .gitlab-ci.yml; the root shim is greenfield convenience
    out = render(tmp_path, {"project_name": "d", "ci": {"github": False, "gitlab": True}})
    shim = out / ".gitlab-ci.yml"
    job = out / ".gitlab/ci/process-gates.gitlab-ci.yml"
    assert shim.is_file()
    assert job.is_file()
    assert ".gitlab/ci/process-gates.gitlab-ci.yml" in shim.read_text()
    job_text = job.read_text()
    assert "uv run scripts/process/gate_runner.py" in job_text
    assert "ghcr.io/astral-sh/uv" in job_text


def test_both_ci_providers_can_coexist(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "ci": {"github": True, "gitlab": True}})
    assert (out / ".github/workflows/process-gates.yml").is_file()
    assert (out / ".gitlab-ci.yml").is_file()
