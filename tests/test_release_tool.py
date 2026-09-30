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

    def fake_run(argv, cwd):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 1 if "ruff" in argv else 0)

    monkeypatch.setattr(rel.subprocess, "run", fake_run)

    with pytest.raises(SystemExit, match="lint failed"):
        rel.release(root, "v9.9.9")
    assert not any("commit" in argv for argv in calls), calls


def test_cli_check_reports_ok_at_the_current_version():
    r = subprocess.run([sys.executable, str(REPO / "tools/release.py"), f"v{CURRENT}", "--check"],
                       capture_output=True, text=True)
    assert r.returncode == 0 and "release: OK" in r.stdout, r.stdout + r.stderr
