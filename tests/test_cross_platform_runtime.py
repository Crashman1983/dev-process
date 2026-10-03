import itertools
import subprocess
import sys
import tomllib
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
    assert (out / ".pre-commit-config.yaml").is_file()
    cfg = (out / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    assert "no-commit-to-branch" in cfg
    assert "gate_runner.py" in cfg and "pre-push" in cfg
    text = (out / "scripts/process/gate_runner.py").read_text(encoding="utf-8")
    assert '# requires-python = ">=3.11"' in text

    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=out, check=True)
    gates = subprocess.run(
        ["uv", "run", "scripts/process/gate_runner.py"],
        cwd=out,
        capture_output=True,
        text=True,
    )
    assert gates.returncode == 0, gates.stdout + gates.stderr


def test_ci_smoke_runs_macos_windows_and_linux_via_full_suite():
    """Linux smoke left the matrix: job `test` must still run this file there, unfiltered."""
    root = Path(__file__).parents[1]
    workflow = yaml.load(
        (root / ".github/workflows/ci.yml").read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )
    smoke = workflow["jobs"]["portable-smoke"]
    assert set(smoke["strategy"]["matrix"]["os"]) == {"macos-latest", "windows-latest"}
    test = workflow["jobs"]["test"]
    assert test["runs-on"] == "ubuntu-latest"
    [cmd] = [s["run"] for s in test["steps"] if "pytest" in s.get("run", "")]
    words = cmd.split()
    args = words[words.index("pytest") + 1:]
    for flag in ("-k", "-m", "--deselect", "--ignore"):
        assert not any(a == flag or a.startswith(flag + "=") for a in args), cmd
    valued = {"-n", "--dist"}  # options whose value is the next word
    positional = [a for prev, a in zip(["", *args], args)
                  if not a.startswith("-") and prev not in valued]
    assert positional == [], cmd
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["tool"]["pytest"]["ini_options"]["testpaths"] == ["tests"]


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
    assert "--data harness=agents_md" in text and "--data harness=claude" in text


def test_release_notes_come_from_the_changelog_entry_of_the_tag(tmp_path):
    import subprocess
    import sys
    root = Path(__file__).parents[1]
    log = tmp_path / "CHANGELOG.md"
    log.write_text("# Changelog\n\n**v1.2.0 — neu.** Text eins.\n- Punkt\n\n**v1.1.0 — alt.** Alt.\n", encoding="utf-8")
    tool = [sys.executable, str(root / "tools/release_notes.py")]
    r = subprocess.run([*tool, "v1.2.0", str(log)], capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.splitlines()[0] == "neu" and "Punkt" in r.stdout and "Alt" not in r.stdout
    assert subprocess.run([*tool, "v9.9.9", str(log)], capture_output=True, text=True).returncode == 1
    wf = (root / ".github/workflows/release-publish.yml").read_text(encoding="utf-8")
    assert "tools/release_notes.py" in wf and "--verify-tag" in wf


@pytest.mark.parametrize("module, script", [
    ("arch_onboarding", "check_architecture.py"), ("github_issues", "check_issues.py")])
def test_a_gate_that_imports_yaml_declares_it(render, tmp_path, module, script):
    """A gate run alone (`uv run scripts/process/<gate>.py`) resolves what it imports;
    without the declaration it worked only where PyYAML happened to be installed."""
    out = render(tmp_path, {"project_name": "d", "modules": {module: True}})
    text = (out / "scripts/process" / script).read_text(encoding="utf-8")
    assert "import yaml" in text and "# /// script" in text and "pyyaml" in text
