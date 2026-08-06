# CI is the transport of enforcement (design: sp7-ci-adapters, lean pass):
# `ci.github` decides whether the Actions workflow invokes gate_runner.py,
# never which gates run — that stays with `modules.*`.


def test_github_workflow_rendered_by_default(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    workflow = out / ".github/workflows/process-gates.yml"
    assert workflow.is_file()
    text = workflow.read_text()
    assert "fetch-depth: 0" in text
    assert "DEV_PROCESS_CANDIDATE_BASE" in text
    assert "github.event.pull_request.base.sha" in text
    assert "github.event.before" in text
    assert "DEV_PROCESS_CANDIDATE_TARGET" in text


def test_github_off_renders_no_workflow_anywhere(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "ci": {"github": False}})
    assert not (out / ".github/workflows").exists()
    assert not list(out.rglob("process-gates.yml"))


def test_no_gitlab_files_ever(render, tmp_path):
    # the GitLab adapter was removed in the lean pass — nothing may render it
    out = render(tmp_path, {"project_name": "d"})
    assert not (out / ".gitlab-ci.yml").exists()
    assert not (out / ".gitlab").exists()
