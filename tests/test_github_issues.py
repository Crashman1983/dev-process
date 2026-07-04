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


def _plan(out: Path, name: str, body: str, archived: bool = False):
    d = out / ".process-work" / "plans"
    if archived:
        d = d / "archive"
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(body)


def test_active_tier3_plan_without_issue_hard(render, tmp_path):
    out = _render(render, tmp_path)
    _plan(out, "2026-07-04-feature.md", "# Plan\n\ntier: 3\n")
    r = _run(out)
    assert r.returncode == 1
    assert "issue-before-code" in r.stdout


def test_active_tier3_plan_with_issue_clean(render, tmp_path):
    out = _render(render, tmp_path)
    _plan(out, "2026-07-04-feature.md", "# Plan\n\ntier: 3\nissue: #7\n")
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_active_tier3_plan_malformed_issue_hard(render, tmp_path):
    out = _render(render, tmp_path)
    _plan(out, "2026-07-04-feature.md", "tier: 3\nissue: 7\n")  # bare number, invalid
    r = _run(out)
    assert r.returncode == 1
    assert "malformed issue ref" in r.stdout


def test_active_plan_issue_waived_clears(render, tmp_path):
    out = _render(render, tmp_path)
    _plan(out, "2026-07-04-feature.md",
          "tier: 3\nissue-waived: spike, will file the issue if it graduates\n")
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_active_tier2_plan_not_enforced(render, tmp_path):
    out = _render(render, tmp_path)
    _plan(out, "2026-07-04-feature.md", "tier: 2\n")  # below the threshold
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_plan_without_tier_not_enforced(render, tmp_path):
    out = _render(render, tmp_path)
    _plan(out, "2026-07-04-feature.md", "# Plan\n\nNo tier declared.\n")
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_fenced_tier_in_plan_ignored(render, tmp_path):
    # a tier: inside a fenced example is a quotation, not a declaration
    out = _render(render, tmp_path)
    _plan(out, "2026-07-04-feature.md", "# Plan\n\n```\ntier: 3\n```\n")
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_archived_tier3_plan_not_issue_checked(render, tmp_path):
    # issue-before-code is a start-of-work rule: archived (merged) plans are the
    # review gate's business, not this one's
    out = _render(render, tmp_path)
    _plan(out, "2026-07-04-feature.md", "tier: 3\n", archived=True)
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_plan_enforced_even_without_feature_registry(render, tmp_path):
    out = _render(render, tmp_path, feature_registry=False)
    _plan(out, "2026-07-04-feature.md", "tier: 4\n")
    r = _run(out)
    assert r.returncode == 1
    assert "issue-before-code" in r.stdout


def test_module_doc_names_issue_before_code(render, tmp_path):
    out = _render(render, tmp_path)
    t = (out / "docs/process/modules/github-issues.md").read_text()
    assert "## Issue before code" in t
    assert "issue-waived" in t
    assert "not gated" in t  # the claim workflow is convention, honestly labeled


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


def _runner_list(out: Path):
    return subprocess.run(
        [sys.executable, str(out / "scripts/process/gate_runner.py"), "--list"],
        cwd=out, capture_output=True, text=True,
    )


def test_runner_lists_issues_when_on(render, tmp_path):
    out = _render(render, tmp_path)
    r = _runner_list(out)
    assert r.returncode == 0, r.stderr
    assert "github-issues" in r.stdout


def test_runner_skips_issues_when_off(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    r = _runner_list(out)
    assert r.returncode == 0, r.stderr
    assert "github-issues" not in r.stdout


def test_artifacts_present_when_on(render, tmp_path):
    out = _render(render, tmp_path)
    assert (out / ".github/ISSUE_TEMPLATE/feature.md").is_file()
    assert (out / ".github/ISSUE_TEMPLATE/bug.md").is_file()
    assert (out / "scripts/process/new_issue.sh").is_file()
    assert (out / "docs/process/modules/github-issues.md").is_file()


def test_artifacts_absent_when_off(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    assert not (out / ".github/ISSUE_TEMPLATE/feature.md").exists()
    assert not (out / "scripts/process/new_issue.sh").exists()
    assert not (out / "docs/process/modules/github-issues.md").exists()


def test_artifacts_neutral(render, tmp_path):
    out = _render(render, tmp_path)
    for rel in [
        ".github/ISSUE_TEMPLATE/feature.md",
        ".github/ISSUE_TEMPLATE/bug.md",
        "docs/process/modules/github-issues.md",
        "scripts/process/new_issue.sh",
    ]:
        text = (out / rel).read_text()
        for k in KENNI:
            assert k not in text, f"{k} leaked in {rel}"


def test_feature_template_has_ears_and_story(render, tmp_path):
    out = _render(render, tmp_path)
    t = (out / ".github/ISSUE_TEMPLATE/feature.md").read_text()
    assert "User story" in t
    assert "shall" in t  # EARS phrasing
    assert "<role>" in t


def test_seed_script_strips_frontmatter(render, tmp_path):
    out = _render(render, tmp_path)
    r = subprocess.run(
        ["bash", str(out / "scripts/process/new_issue.sh"), "feature"],
        cwd=out, capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    body_path = Path(r.stdout.strip())
    assert body_path.is_file()
    body = body_path.read_text()
    assert "User story" in body
    assert "labels:" not in body  # YAML frontmatter removed
    assert not body.lstrip().startswith("---")


def test_docdrift_resolves_module_doc_refs(render, tmp_path):
    out = render(
        tmp_path,
        {"project_name": "d", "modules": {"doc_drift_gate": True, "github_issues": True}},
    )
    r = subprocess.run(
        [sys.executable, str(out / "scripts/process/check_doc_drift.py"), str(out)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stdout  # module-doc refs resolve; feature_registry off
