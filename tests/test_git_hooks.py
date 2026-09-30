"""git-hooks module: local enforcement delegated to the standard pre-commit
framework (lean pass) — the module renders a .pre-commit-config.yaml instead
of a custom installer/launcher pair."""
import os
import shlex
import subprocess
import sys

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


def _hook_run(out, entry, env):
    # the framework runs `entry` from the repository root with no file names
    # (pass_filenames: false); the push target arrives as PRE_COMMIT_REMOTE_BRANCH
    argv = shlex.split(entry)
    assert argv[:2] == ["uv", "run"]
    clean = {k: v for k, v in os.environ.items() if not k.startswith(("PROCESS_", "PRE_COMMIT_", "SKIP"))}
    return subprocess.run([sys.executable, *argv[2:]], cwd=out, capture_output=True, text=True,
                          env={**clean, **env})


def test_the_merge_route_guard_is_its_own_pre_push_hook(render, tmp_path):
    # its own hook: SKIP=process-gates skips the gates, never the guard on main
    out = _render(render, tmp_path)
    cfg = yaml.safe_load((out / ".pre-commit-config.yaml").read_text(encoding="utf-8"))
    local = next(repo["hooks"] for repo in cfg["repos"] if repo["repo"] == "local")
    ids = [h["id"] for h in local]
    assert ids.index("merge-route") < ids.index("process-gates")
    guard = local[ids.index("merge-route")]
    assert guard["entry"].endswith("scripts/process/merge_route.py")
    assert guard["stages"] == ["pre-push"]
    assert guard["always_run"] is True and guard["pass_filenames"] is False
    for k, v in (("init", "-q"), ("config", "user.email t@t"), ("config", "user.name t")):
        subprocess.run(["git", k, *v.split()], cwd=out, check=True)
    subprocess.run(["git", "add", "-A"], cwd=out, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=out, check=True)
    main = {"PRE_COMMIT_REMOTE_BRANCH": "refs/heads/main"}
    refused = _hook_run(out, guard["entry"], main)
    assert refused.returncode == 1 and "PROCESS_MERGE_ROUTE" in refused.stderr
    assert _hook_run(out, guard["entry"], {**main, "PROCESS_MERGE_ROUTE": "train"}).returncode == 0
    assert _hook_run(out, guard["entry"], {"PRE_COMMIT_REMOTE_BRANCH": "refs/heads/7-x"}).returncode == 0
    skipped = _hook_run(out, guard["entry"], {**main, "SKIP": "process-gates"})
    assert skipped.returncode == 0, skipped.stderr
    ledger = (out / ".git/process-owner-overrides.log").read_text(encoding="utf-8")
    assert "\tSKIP=process-gates\t" in ledger
    barred = _hook_run(out, guard["entry"], {**main, "SKIP": "process-gates", "PROCESS_PHASE": "review"})
    assert barred.returncode == 1


def test_the_module_doc_names_the_guard_and_its_bypass(render, tmp_path):
    out = _render(render, tmp_path)
    doc = (out / "docs/process/modules/git-hooks.md").read_text(encoding="utf-8")
    assert "merge-route" in doc and "SKIP=merge-route" in doc
    assert "process-owner-overrides.log" in doc
