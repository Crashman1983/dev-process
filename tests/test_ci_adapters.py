import pytest

# CI is the transport of enforcement (design: sp7-ci-adapters, lean pass):
# `ci.github` decides whether the Actions workflow invokes gate_runner.py,
# never which gates run — that stays with `modules.*`.


def test_github_workflow_rendered_by_default(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    workflow = out / ".github/workflows/process-gates.yml"
    assert workflow.is_file()
    text = workflow.read_text()
    assert "fetch-depth: 0" in text
    assert "gate_runner.py" in text


def test_github_off_renders_no_workflow_anywhere(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "ci": {"github": False}})
    assert not (out / ".github/workflows").exists()
    assert not list(out.rglob("process-gates.yml"))


def test_no_gitlab_files_ever(render, tmp_path):
    # the GitLab adapter was removed in the lean pass — nothing may render it
    out = render(tmp_path, {"project_name": "d"})
    assert not (out / ".gitlab-ci.yml").exists()
    assert not (out / ".gitlab").exists()


def _triggers(out, name):
    import yaml
    wf = yaml.safe_load((out / ".github/workflows" / name).read_text())
    return sorted((wf.get("on") or wf.get(True)).keys())  # YAML 1.1 reads a bare `on` as True


def test_github_manual_renders_the_workflows_for_by_hand_runs_only(render, tmp_path):
    # Kenni ADR-0069: no paid hosted CI — the pre-push hook of a clone is the gate;
    # the workflows stay as a by-hand run, nothing hosted triggers or requires them
    out = render(tmp_path, {"project_name": "d", "ci": {"github": "manual"}, "modules": {"telemetry": True}})
    for name in ("process-gates.yml", "owner-digest.yml", "process-kpis.yml"):
        assert _triggers(out, name) == ["workflow_dispatch"], name
    assert not (out / "scripts/process/setup_branch_protection.sh").exists()
    # and no workflow names the script it does not render (#242)
    assert "setup_branch_protection" not in (out / ".github/workflows/process-gates.yml").read_text()


def test_github_true_keeps_its_hosted_triggers(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {"telemetry": True}})
    assert _triggers(out, "process-gates.yml") == ["pull_request", "push"]
    assert "setup_branch_protection.sh sets" in (out / ".github/workflows/process-gates.yml").read_text()
    for name in ("owner-digest.yml", "process-kpis.yml"):
        assert _triggers(out, name) == ["schedule", "workflow_dispatch"], name


@pytest.mark.parametrize("value", ["yes", "true", 1])
def test_ci_github_takes_true_false_or_manual_only(_template_src, tmp_path, value):
    import copier
    with pytest.raises(ValueError, match="ci.github must be true, false or manual"):
        copier.run_copy(str(_template_src), str(tmp_path / "o"), data={"project_name": "d", "ci": {"github": value}},
                        defaults=True, unsafe=True, quiet=True)
