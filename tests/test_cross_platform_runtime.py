import itertools
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


@pytest.mark.parametrize(
    ("claude", "copilot", "agents_md"),
    list(itertools.product([False, True], repeat=3)),
)
def test_harnesses_are_independently_selectable(
    render, tmp_path, claude, copilot, agents_md
):
    out = render(
        tmp_path,
        {
            "project_name": "portable",
            "harnesses": {
                "claude": claude,
                "copilot": copilot,
                "agents_md": agents_md,
            },
        },
    )
    assert (out / "CLAUDE.md").exists() is claude
    assert (out / ".claude/commands").exists() is claude
    assert (out / ".github/copilot-instructions.md").exists() is copilot
    assert (out / "AGENTS.md").exists() is agents_md


def test_runner_anchors_to_rendered_repo_and_declares_uv_dependency(render, tmp_path):
    out = render(tmp_path / "out", {"project_name": "portable"})
    script = out / "scripts/process/gate_runner.py"
    result = subprocess.run(
        [sys.executable, str(script), "--list"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "kernel" in result.stdout
    text = script.read_text(encoding="utf-8")
    assert '# dependencies = ["pyyaml>=6,<7"]' in text


@pytest.mark.parametrize(
    ("manifest", "message"),
    [
        ("modules: {typo_module: true}\nharnesses: {}\n", "unknown module"),
        ("modules: {doc_drift_gate: 0}\nharnesses: {}\n", "booleans"),
        ("modules: {}\nharnesses: []\n", "harnesses"),
        ("modules: {}\nharnesses: {claude: null}\n", "booleans"),
    ],
)
def test_runner_rejects_invalid_manifest_values(render, tmp_path, manifest, message):
    out = render(tmp_path, {"project_name": "portable"})
    (out / ".copier-answers.yml").write_text(manifest, encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(out / "scripts/process/gate_runner.py"), "--list"],
        cwd=out,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert message in result.stderr


def test_portable_python_helpers_render(render, tmp_path):
    out = render(
        tmp_path,
        {
            "project_name": "portable",
            "modules": {"git_hooks": True, "github_issues": True},
        },
    )
    assert (out / "scripts/process/install_hooks.py").is_file()
    assert (out / "scripts/process/run_hook.py").is_file()
    assert (out / "scripts/process/new_issue.py").is_file()
    for name in ["install_hooks.py", "run_hook.py", "new_issue.py"]:
        text = (out / "scripts/process" / name).read_text(encoding="utf-8")
        assert '# requires-python = ">=3.11"' in text

    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=out, check=True)
    gates = subprocess.run(
        ["uv", "run", "scripts/process/gate_runner.py"],
        cwd=out,
        capture_output=True,
        text=True,
    )
    assert gates.returncode == 0, gates.stdout + gates.stderr
    hooks = subprocess.run(
        ["uv", "run", "scripts/process/install_hooks.py"],
        cwd=out,
        capture_output=True,
        text=True,
    )
    assert hooks.returncode == 0, hooks.stderr
    pre_push = subprocess.run(
        ["sh", ".git/hooks/pre-push", "origin", "unused-location"],
        cwd=out,
        input="",
        capture_output=True,
        text=True,
    )
    assert pre_push.returncode == 0, pre_push.stderr
    issue = subprocess.run(
        ["uv", "run", "scripts/process/new_issue.py", "feature"],
        cwd=out,
        capture_output=True,
        text=True,
    )
    assert issue.returncode == 0, issue.stderr


def test_ci_has_linux_macos_windows_smoke_matrix():
    root = Path(__file__).parents[1]
    workflow = yaml.load(
        (root / ".github/workflows/ci.yml").read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )
    job = workflow["jobs"]["portable-smoke"]
    assert job["strategy"]["matrix"]["os"] == [
        "ubuntu-latest",
        "macos-latest",
        "windows-latest",
    ]


def test_release_workflow_requires_tag_to_match_project_version():
    root = Path(__file__).parents[1]
    text = (root / ".github/workflows/release-tag.yml").read_text(encoding="utf-8")
    assert "pyproject.toml" in text
    assert 'expected = f"v{version}"' in text
    assert "tag != expected" in text
    assert "astral-sh/setup-uv@08807647e7069bb48b6ef5acd8ec9567f424441b" in text


def test_bootstrap_documents_complete_optional_harness_mapping():
    root = Path(__file__).parents[1]
    text = (root / "BOOTSTRAP.md").read_text(encoding="utf-8")
    assert "Claude Code is always installed" not in text
    assert 'harnesses={"claude": false, "copilot": false, "agents_md": true}' in text
