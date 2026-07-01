import json
import os
import subprocess
import sys
from pathlib import Path

KENNI = ["Kenni", "KenniNext", "Seb", "Signal", "SvelteKit", "user_id=1", "surface:ios"]


def _render(render, tmp_path, repo="", **mods):
    m = {"github_issues": True, "feature_registry": True}
    m.update(mods)
    data = {"project_name": "d", "modules": m}
    if repo:
        data["github_repo"] = repo
    return render(tmp_path, data)


def _run(out: Path, path=None, prepend=None):
    env = dict(os.environ)
    if path is not None:
        env["PATH"] = path
    elif prepend:
        env["PATH"] = f"{prepend}{os.pathsep}" + env["PATH"]
    return subprocess.run(
        [sys.executable, str(out / "scripts/process/check_issues.py"), str(out)],
        capture_output=True, text=True, env=env,
    )


def _story(out: Path, issue=None, status="proposed", sid="STORY-0001"):
    d = {"id": sid, "title": "t", "story": "s", "status": status,
         "acceptance": [{"text": "a"}], "tests": []}
    if issue is not None:
        d["issue"] = issue
    reg = out / "docs/process/feature-registry"
    reg.mkdir(parents=True, exist_ok=True)
    (reg / f"{sid}.json").write_text(json.dumps(d))


def test_valid_bare(render, tmp_path):
    out = _render(render, tmp_path)
    _story(out, issue="#412")
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_valid_crossrepo(render, tmp_path):
    out = _render(render, tmp_path)
    _story(out, issue="octo/billing#77")
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_valid_url(render, tmp_path):
    out = _render(render, tmp_path)
    _story(out, issue="https://github.com/octo/api/issues/412")
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_malformed_number_only(render, tmp_path):
    out = _render(render, tmp_path)
    _story(out, issue="412")
    r = _run(out)
    assert r.returncode == 1
    assert "malformed" in r.stdout


def test_malformed_hash_only(render, tmp_path):
    out = _render(render, tmp_path)
    _story(out, issue="#")
    r = _run(out)
    assert r.returncode == 1


def test_malformed_crossrepo_no_number(render, tmp_path):
    out = _render(render, tmp_path)
    _story(out, issue="octo/billing#")
    r = _run(out)
    assert r.returncode == 1


def test_malformed_non_github_url(render, tmp_path):
    out = _render(render, tmp_path)
    _story(out, issue="https://example.com/octo/api/issues/1")
    r = _run(out)
    assert r.returncode == 1


def test_issue_non_string_is_hard(render, tmp_path):
    out = _render(render, tmp_path)
    _story(out, issue=412)
    r = _run(out)
    assert r.returncode == 1
    assert "string" in r.stdout


def test_no_issue_ok(render, tmp_path):
    out = _render(render, tmp_path)
    _story(out, status="proposed")  # no issue field
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_tracked_without_issue_notes(render, tmp_path):
    out = _render(render, tmp_path)
    _story(out, status="in-progress")  # no issue field
    r = _run(out)
    assert r.returncode == 0, r.stdout
    assert "no issue link" in r.stdout


def test_bad_json_skipped(render, tmp_path):
    out = _render(render, tmp_path)
    reg = out / "docs/process/feature-registry"
    reg.mkdir(parents=True, exist_ok=True)
    (reg / "STORY-0002.json").write_text("{not json")
    r = _run(out)
    assert r.returncode == 0, r.stdout  # registry gate owns JSON validity


def test_no_stories_note(render, tmp_path):
    out = _render(render, tmp_path, feature_registry=False)  # no registry dir
    r = _run(out)
    assert r.returncode == 0, r.stdout
    assert "no stories" in r.stdout


def _stub_gh(bindir: Path, code: int, stdout: str = ""):
    bindir.mkdir(parents=True, exist_ok=True)
    p = bindir / "gh"
    p.write_text(f'#!/bin/sh\nprintf "%s" "{stdout}"\nexit {code}\n')
    p.chmod(0o755)


def _stub_gh_capture(bindir: Path, argfile: Path, code: int = 0):
    bindir.mkdir(parents=True, exist_ok=True)
    p = bindir / "gh"
    p.write_text(f'#!/bin/sh\nprintf "%s" "$*" > "{argfile}"\nexit {code}\n')
    p.chmod(0o755)


def test_existence_gh_absent_is_soft(render, tmp_path):
    # must-not-hard-fail guard: gh not on PATH -> note, exit 0
    out = _render(render, tmp_path, repo="octo/api")
    _story(out, issue="#412")
    empty = tmp_path / "empty"
    empty.mkdir()
    r = _run(out, path=str(empty))
    assert r.returncode == 0, r.stdout
    assert "gh not on PATH" in r.stdout


def test_existence_ok_no_note(render, tmp_path):
    out = _render(render, tmp_path, repo="octo/api")
    _story(out, issue="#412")
    bindir = tmp_path / "bin"
    _stub_gh(bindir, 0)
    r = _run(out, prepend=str(bindir))
    assert r.returncode == 0, r.stdout
    assert "could not confirm" not in r.stdout


def test_existence_404_is_soft(render, tmp_path):
    # must-not-hard-fail guard: a non-zero gh (404 / not visible) -> note, exit 0
    out = _render(render, tmp_path, repo="octo/api")
    _story(out, issue="#412")
    bindir = tmp_path / "bin"
    _stub_gh(bindir, 1)
    r = _run(out, prepend=str(bindir))
    assert r.returncode == 0, r.stdout
    assert "could not confirm" in r.stdout


def test_existence_forwards_configured_repo(render, tmp_path):
    out = _render(render, tmp_path, repo="octo/api")
    _story(out, issue="#412")
    bindir = tmp_path / "bin"
    argfile = out / "gh-args.txt"
    _stub_gh_capture(bindir, argfile, code=0)
    r = _run(out, prepend=str(bindir))
    assert r.returncode == 0, r.stdout
    args = argfile.read_text()
    assert "--repo octo/api" in args
    assert "412" in args


def test_existence_bare_without_repo_notes(render, tmp_path):
    out = _render(render, tmp_path)  # no github_repo configured
    _story(out, issue="#412")
    bindir = tmp_path / "bin"
    _stub_gh(bindir, 0)
    r = _run(out, prepend=str(bindir))
    assert r.returncode == 0, r.stdout
    assert "no github_repo configured" in r.stdout


def test_existence_crossrepo_uses_own_repo(render, tmp_path):
    out = _render(render, tmp_path)  # no default repo, ref carries its own
    _story(out, issue="octo/billing#77")
    bindir = tmp_path / "bin"
    argfile = out / "gh-args.txt"
    _stub_gh_capture(bindir, argfile, code=0)
    r = _run(out, prepend=str(bindir))
    assert r.returncode == 0, r.stdout
    assert "--repo octo/billing" in argfile.read_text()
