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
    log.write_text("# Changelog\n\n## v1.2.0 — neu · 2026-10-15\n\n**Warum.** Text eins.\n- Punkt\n\n"
                   "## v1.1.0 — alt · 2026-10-01\n\nAlt.\n", encoding="utf-8")
    tool = [sys.executable, str(root / "tools/release_notes.py")]
    r = subprocess.run([*tool, "v1.2.0", str(log)], capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.splitlines()[0] == "neu" and "Punkt" in r.stdout and "Alt" not in r.stdout
    assert subprocess.run([*tool, "v9.9.9", str(log)], capture_output=True, text=True).returncode == 1
    # an older tag carries the bold form in its own CHANGELOG — still publishable
    old = tmp_path / "OLD.md"
    old.write_text("# Changelog\n\n**v1.0.0 — alt.** Text.\n- Punkt\n\n**v0.9.0 — älter.** X.\n", encoding="utf-8")
    r = subprocess.run([*tool, "v1.0.0", str(old)], capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.splitlines()[0] == "alt" and "Punkt" in r.stdout and "X." not in r.stdout
    # a heading without a body is no entry
    empty = tmp_path / "EMPTY.md"
    empty.write_text("# Changelog\n\n## v1.3.0 — leer · 2026-10-15\n\n## v1.2.0 — x · 2026-10-01\n\nX.\n",
                     encoding="utf-8")
    assert subprocess.run([*tool, "v1.3.0", str(empty)], capture_output=True, text=True).returncode == 1
    wf = (root / ".github/workflows/release-publish.yml").read_text(encoding="utf-8")
    assert "tools/release_notes.py" in wf and "--verify-tag" in wf


@pytest.mark.parametrize("rel", ["../x", "\\x", "C:x", "C:\\x", "C:/x", "/x"])
def test_template_file_reads_never_leave_the_root_on_any_os(tmp_path, rel):
    """template_verify._file: a drive or root component leaves the root on Windows
    even where POSIX sees a name — refused on every OS, here in the portable smoke."""
    import importlib.util
    scripts = Path(__file__).parents[1] / "template/scripts/process"
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(scripts))
    try:
        spec = importlib.util.spec_from_file_location("smoke_template_verify", scripts / "template_verify.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        sys.path.remove(str(scripts))
    root = tmp_path / "render"
    (root / "inner").mkdir(parents=True)
    (root / "inner" / "ok.md").write_text("inside\n", encoding="utf-8")
    assert mod._file(root, "inner/ok.md")[1].replace(b"\r\n", b"\n") == b"inside\n"
    with pytest.raises(ValueError, match="leaves the root"):
        mod._file(root, rel)


_WRITE_SEAM_RUNNER = '''
import json, os, sys
sys.path.insert(0, sys.argv[1])
import attest
spec = json.loads(sys.argv[2])
fired = []
if spec.get("no_pread") and hasattr(os, "pread"):
    del os.pread  # the lseek + read branch, as on Windows
if spec.get("seam") and hasattr(attest, "_write_seam"):
    inner = attest._write_seam

    def seam(stage):
        inner(stage)
        if stage == spec["seam"] and not fired:
            fired.append(stage)
            rel = spec["swap"]
            with open(rel + ".swap", "wb") as fh:
                fh.write(spec["bytes"].encode())
            os.replace(rel + ".swap", rel)  # rename-over: a new file at the path, no symlink
            print("SEAM-FIRED", stage, file=sys.stderr, flush=True)
    attest._write_seam = seam
sys.argv = ["attest.py", *sys.argv[3:]]
raise SystemExit(attest.main())
'''


def _smoke_git(root, *args):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                          check=True).stdout.strip()


_RED = pytest.mark.xfail(strict=True, reason="#308 fix round 6: the write seam is missing before the change")


@pytest.mark.parametrize("case", [pytest.param("swapped", marks=_RED),
                                  pytest.param("swapped without pread", marks=_RED), "plain commit"])
def test_attest_write_primitives_hold_on_this_os(tmp_path, case):
    """#308 fix round 6 (I4, I11, design §8): the write phase checks today's shard through
    the descriptor it appends with — `(st_dev, st_ino)` and the bytes (`os.pread`, else
    `lseek` + `read`). Here in the portable smoke, without symlinks and without a render:
    a shard renamed over at `worktree-checked` is refused and both files keep their bytes;
    a plain `--commit` carries the line and leaves the status clean."""
    import datetime as dt
    import json
    import os
    scripts = Path(__file__).parents[1] / "template/scripts/process"
    root = tmp_path / "repo"
    root.mkdir()
    _smoke_git(root, "init", "-q", "-b", "main")
    _smoke_git(root, "config", "user.email", "t@t")
    _smoke_git(root, "config", "user.name", "t")
    _smoke_git(root, "config", "core.autocrlf", "false")
    (root / "README.md").write_text("smoke\n", encoding="utf-8")
    _smoke_git(root, "add", "-A")
    _smoke_git(root, "commit", "-q", "-m", "base")
    _smoke_git(root, "checkout", "-q", "-b", "7-smoke")
    shard = f".process-work/journal/issue-7/{dt.date.today().isoformat()}.md"
    (root / shard).parent.mkdir(parents=True)
    (root / shard).write_bytes(b"# today\n")
    _smoke_git(root, "add", "-A")
    _smoke_git(root, "commit", "-q", "-m", "docs: today's shard")
    old = _smoke_git(root, "rev-parse", "HEAD")
    swapped = b"# today, renamed over by another process\n"
    spec = {} if case == "plain commit" else {
        "seam": "worktree-checked", "swap": shard, "bytes": swapped.decode(),
        "no_pread": case == "swapped without pread"}
    runner = tmp_path / "write_seam_runner.py"
    runner.write_text(_WRITE_SEAM_RUNNER, encoding="utf-8")
    r = subprocess.run([sys.executable, str(runner), str(scripts), json.dumps(spec),
                        "--work", "smoke", "--tier", "1", "--model", "m", "--independence", "bundle",
                        "--verdict", "pass", "--commit", str(root)],
                       cwd=root, capture_output=True, text=True,
                       env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    if case == "plain commit":
        assert r.returncode == 0, r.stdout + r.stderr
        assert "REVIEW work=smoke" in _smoke_git(root, "show", f"HEAD:{shard}")
        assert _smoke_git(root, "status", "--porcelain") == ""
        return
    assert "SEAM-FIRED worktree-checked" in r.stderr, "seam never ran:\n" + r.stdout + r.stderr
    assert r.returncode == 1, r.stdout + r.stderr
    assert (root / shard).read_bytes() == swapped
    assert _smoke_git(root, "rev-parse", "HEAD") == old
    assert _smoke_git(root, "show", f"HEAD:{shard}") == "# today"


@pytest.mark.parametrize("module, script", [
    ("arch_onboarding", "check_architecture.py"), ("github_issues", "check_issues.py")])
def test_a_gate_that_imports_yaml_declares_it(render, tmp_path, module, script):
    """A gate run alone (`uv run scripts/process/<gate>.py`) resolves what it imports;
    without the declaration it worked only where PyYAML happened to be installed."""
    out = render(tmp_path, {"project_name": "d", "modules": {module: True}})
    text = (out / "scripts/process" / script).read_text(encoding="utf-8")
    assert "import yaml" in text and "# /// script" in text and "pyyaml" in text
