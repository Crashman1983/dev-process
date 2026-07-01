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
