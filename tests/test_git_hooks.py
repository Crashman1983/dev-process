"""git-hooks module: local enforcement delegated to the standard pre-commit
framework (lean pass) — the module renders a .pre-commit-config.yaml instead
of a custom installer/launcher pair."""
import yaml


def _render(render, tmp_path, **mods):
    modules = {"git_hooks": True}
    modules.update(mods)
    return render(tmp_path, {"project_name": "d", "modules": modules})


def test_module_on_renders_pre_commit_config(render, tmp_path):
    out = _render(render, tmp_path)
    cfg_file = out / ".pre-commit-config.yaml"
    assert cfg_file.is_file()
    cfg = yaml.safe_load(cfg_file.read_text(encoding="utf-8"))
    hooks = {h["id"]: h for repo in cfg["repos"] for h in repo["hooks"]}
    # branch discipline via the upstream standard hook
    assert "no-commit-to-branch" in hooks
    assert "--branch" in hooks["no-commit-to-branch"]["args"]
    # the gates run at pre-push through the manifest-aware runner
    gates = hooks["process-gates"]
    assert "gate_runner.py" in gates["entry"]
    assert gates["stages"] == ["pre-push"]
    assert gates["always_run"] is True
    assert gates["pass_filenames"] is False


def test_module_off_renders_nothing(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    assert not (out / ".pre-commit-config.yaml").exists()
    assert not (out / "scripts/process/install_hooks.py").exists()
    assert not (out / "scripts/process/run_hook.py").exists()


def test_config_documents_sanctioned_bypass(render, tmp_path):
    # the onboarding baseline commit on main is the one sanctioned bypass —
    # it must be named in the config header, not tribal knowledge
    out = _render(render, tmp_path)
    text = (out / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    assert "SKIP=no-commit-to-branch" in text
    assert "mandatory rule 8" in text


def test_module_doc_names_install_command(render, tmp_path):
    out = _render(render, tmp_path)
    doc = (out / "docs/process/modules/git-hooks.md").read_text(encoding="utf-8")
    assert "pre-commit install --hook-type pre-commit --hook-type pre-push" in doc
    assert "pre-commit.com" in doc
