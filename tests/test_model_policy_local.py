"""A project's model choice without owning the policy (#130, P2):
`docs/process/model-policy.local.json` is merged over `model-policy.json`, mapping by
mapping (`default`, `tiers.N`, `phases.P`, `env`), so a release that edits the template
policy reaches the project and the project's own ids stay."""
import json
import subprocess
import sys
from pathlib import Path

import pytest


def _dispatch(out: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(out / "scripts/process/dispatch.py"), *args],
                          cwd=out, capture_output=True, text=True)


def _local(out: Path, data: object) -> None:
    text = data if isinstance(data, str) else json.dumps(data)
    (out / "docs/process/model-policy.local.json").write_text(text, encoding="utf-8")


def test_the_local_file_overrides_one_cell_and_keeps_the_rest(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _local(out, {"tiers": {"3": {"execute": "my-sonnet"}}, "default": {"plan": "my-opus"}})

    t3 = _dispatch(out, "policy", "--tier", "3")
    dflt = _dispatch(out, "policy")

    assert t3.returncode == 0, t3.stderr
    assert "execute: my-sonnet" in t3.stdout and "review: claude-fable-5-1" in t3.stdout, t3.stdout
    assert "plan: my-opus" in dflt.stdout and "execute: claude-sonnet-5" in dflt.stdout, dflt.stdout


def test_the_merged_policy_is_validated(render, tmp_path):
    """The local file cannot slip past the checks the template file gets."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _local(out, {"env": {"PROCESS_PHASE": "x"}})

    r = _dispatch(out, "policy")

    assert r.returncode != 0 and "PROCESS_" in r.stdout + r.stderr, r.stdout + r.stderr


@pytest.mark.parametrize("bad", ["{nope", "[]"], ids=["unparseable", "not-a-mapping"])
def test_a_malformed_local_file_refuses(render, tmp_path, bad):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _local(out, bad)

    r = _dispatch(out, "policy")

    assert r.returncode != 0 and "model-policy.local.json" in r.stdout + r.stderr, r.stdout + r.stderr


def test_a_local_value_replaces_a_scalar_and_a_list_whole(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _local(out, {"command": "mine --model {model} {prompt}", "max_workers": 2})
    sys.path.insert(0, str(out / "scripts/process"))
    try:
        import importlib

        import dispatch
        importlib.reload(dispatch)
        policy = dispatch.load_policy(out)
    finally:
        sys.path.pop(0)
        sys.modules.pop("dispatch", None)

    assert policy["command"] == "mine --model {model} {prompt}" and policy["max_workers"] == 2
    assert policy["tiers"]["3"]["review"] == "claude-fable-5-1"


@pytest.mark.parametrize("key", ["SKIP", "GIT_CONFIG_COUNT", "GIT_DIR", "PRE_COMMIT_ALLOW_NO_CONFIG"])
def test_worker_env_cannot_switch_hooks_off(render, tmp_path, key):
    """Refute of #130 (older than it): `env: {"SKIP": "merge-route,process-gates"}` or a
    GIT_CONFIG_* that sets core.hooksPath let a worker push past every local guard."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _local(out, {"phases": {"execute": {"env": {key: "x"}}}})

    r = _dispatch(out, "policy")

    assert r.returncode != 0 and key in r.stdout + r.stderr, r.stdout + r.stderr


@pytest.mark.parametrize("key", ["skip", "HOME", "XDG_CONFIG_HOME", "PATH", "LD_PRELOAD"])
def test_worker_env_cannot_redirect_git_config_or_executables(render, tmp_path, key):
    """Refute round 2, F2: HOME / XDG_CONFIG_HOME carry a git config with core.hooksPath,
    PATH another git, and `skip` is SKIP on case-insensitive systems."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _local(out, {"env": {key: "x"}})

    r = _dispatch(out, "policy")

    assert r.returncode != 0 and key in r.stdout + r.stderr, r.stdout + r.stderr


def test_the_local_file_changes_one_class_cell(render, tmp_path):
    """A project re-points one class without copying the template's classes."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _local(out, {"classes": {"design": {"execute": "my-large"}}})

    design = _dispatch(out, "policy", "--class", "design")
    mech = _dispatch(out, "policy", "--class", "mechanical")

    assert design.returncode == 0 and "execute: my-large" in design.stdout, design.stdout + design.stderr
    assert mech.returncode == 0 and "execute: claude-sonnet-5" in mech.stdout, mech.stdout + mech.stderr
