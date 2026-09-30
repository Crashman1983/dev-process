"""tools/release.py — the local release ritual in one run (#123)."""
import importlib.util
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def _load():
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("release_tool", REPO / "tools/release.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rel = _load()
CURRENT = re.search(r'^version = "(.+)"$', (REPO / "pyproject.toml").read_text(), re.M).group(1)


def test_every_place_the_repository_names_its_version_is_a_location():
    """A new location cannot be forgotten: the current version, anywhere in a tracked
    file outside the history and the generated SBOM, must be one of LOCATIONS."""
    out = subprocess.run(["git", "grep", "-n", "-F", CURRENT, "--", ".",
                          ":!CHANGELOG.md", ":!docs/sbom.cdx.json", ":!docs/SBOM.md", ":!tests/"],
                         cwd=REPO, capture_output=True, text=True).stdout
    files = {line.split(":", 1)[0] for line in out.splitlines()}
    assert files == {path for path, _ in rel.LOCATIONS}, files


def test_check_is_clean_at_the_current_version():
    assert rel.mismatches(REPO, CURRENT) == []


def _copy(tmp_path: Path) -> Path:
    for path, _ in rel.LOCATIONS:
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REPO / path, tmp_path / path)
    return tmp_path


def test_check_names_every_location_off_the_version(tmp_path):
    root = _copy(tmp_path)

    left = rel.mismatches(root, "9.9.9")

    assert [line.split(":", 1)[0] for line in left] == [path for path, _ in rel.LOCATIONS]


def test_bump_moves_every_location_and_nothing_else(tmp_path):
    root = _copy(tmp_path)
    before = {path: (root / path).read_text() for path, _ in rel.LOCATIONS}

    rel.bump(root, "9.9.9")

    assert rel.mismatches(root, "9.9.9") == []
    for path, text in before.items():
        after = (root / path).read_text()
        assert after.replace("9.9.9", CURRENT) == text, path


def test_release_refuses_without_a_changelog_entry(tmp_path):
    root = _copy(tmp_path)
    (root / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")

    with pytest.raises(SystemExit, match="no entry for v9.9.9"):
        rel.release(root, "v9.9.9")
    assert rel.mismatches(root, CURRENT) == []  # nothing bumped


@pytest.mark.parametrize("tag", ["2.38.0", "v2.38", "v2.38.0-rc1"])
def test_release_refuses_what_is_no_version(tmp_path, tag):
    with pytest.raises(SystemExit, match="no version"):
        rel.release(_copy(tmp_path), tag)


def test_a_failing_step_stops_before_the_commit(tmp_path, monkeypatch):
    root = _copy(tmp_path)
    (root / "CHANGELOG.md").write_text("**v9.9.9 — t.** body\n", encoding="utf-8")
    calls = []

    def fake_run(argv, **kw):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 1 if "ruff" in argv else 0, stdout="", stderr="")

    monkeypatch.setattr(rel.subprocess, "run", fake_run)

    with pytest.raises(SystemExit, match="lint failed"):
        rel.release(root, "v9.9.9")
    assert not any("commit" in argv for argv in calls), calls


def test_cli_check_reports_ok_at_the_current_version():
    r = subprocess.run([sys.executable, str(REPO / "tools/release.py"), f"v{CURRENT}", "--check"],
                       capture_output=True, text=True)
    assert r.returncode == 0 and "release: OK" in r.stdout, r.stdout + r.stderr


# --- refute ---


def _git_repo(tmp_path: Path) -> Path:
    root = _copy(tmp_path)
    (root / "CHANGELOG.md").write_text("**v9.9.9 — t.** body\n", encoding="utf-8")
    for args in (["init", "-q", "-b", "main"], ["config", "user.email", "t@t"],
                 ["config", "user.name", "t"], ["add", "-A"], ["commit", "-q", "-m", "base"]):
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)
    return root


def test_release_refuses_a_dirty_tree(tmp_path):
    """F6: a staged file rode along into the release commit."""
    root = _git_repo(tmp_path)
    (root / "WIP.txt").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "add", "WIP.txt"], cwd=root, check=True)

    with pytest.raises(SystemExit, match="not clean"):
        rel.release(root, "v9.9.9", suite=False)
    assert rel.mismatches(root, CURRENT) == []


def test_release_refuses_a_version_not_above_the_current_one(tmp_path):
    root = _git_repo(tmp_path)

    with pytest.raises(SystemExit, match="not above"):
        rel.release(root, "v0.0.1", suite=False)


def test_cli_refuses_an_unknown_flag():
    """F6: `--chek` ran a full release."""
    r = subprocess.run([sys.executable, str(REPO / "tools/release.py"), "v9.9.9", "--chek"],
                       capture_output=True, text=True)
    assert r.returncode == 2 and "unrecognized" in r.stderr, r.stderr


def test_check_reports_a_stale_sbom(monkeypatch):
    """F7: `--check` said OK while the SBOM still named the old version."""
    calls = []
    monkeypatch.setattr(rel.subprocess, "run",
                        lambda argv, **kw: calls.append(argv) or subprocess.CompletedProcess(argv, 1))

    assert "docs/sbom.cdx.json / docs/SBOM.md: stale (tools/gen_sbom.py --check)" in rel.check(REPO, f"v{CURRENT}")
    assert any("gen_sbom.py" in " ".join(map(str, a)) and "--check" in a for a in calls), calls


def test_a_rerun_after_a_failed_step_is_not_refused_as_a_downgrade(tmp_path, monkeypatch):
    """G2: the failed run left the files bumped; the version guard read the bump as current."""
    root = _git_repo(tmp_path)
    real = subprocess.run
    monkeypatch.setattr(rel.subprocess, "run", lambda argv, **kw: real(argv, **kw) if argv[0] == "git"
                        else subprocess.CompletedProcess(argv, 1 if "ruff" in argv else 0, stdout="", stderr=""))
    with pytest.raises(SystemExit, match="lint failed"):
        rel.release(root, "v9.9.9", suite=False)

    with pytest.raises(SystemExit, match="lint failed"):  # the same step fails again — no downgrade refusal
        rel.release(root, "v9.9.9", suite=False)


def test_a_rename_is_named_by_its_new_path(tmp_path):
    """G5: porcelain -z puts the old name in its own field; it was read as a cut path."""
    root = _git_repo(tmp_path)
    subprocess.run(["git", "mv", "README.md", "README-OLD.md"], cwd=root, check=True)

    with pytest.raises(SystemExit) as refused:
        rel.release(root, "v9.9.9", suite=False)
    assert "README-OLD.md" in str(refused.value) and "DME.md" not in str(refused.value), refused.value
