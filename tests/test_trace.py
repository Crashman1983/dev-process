import json
import subprocess
import sys
from pathlib import Path


def _run(out: Path, *args):
    return subprocess.run([sys.executable, str(out / "scripts/process/trace.py"), *args],
                          cwd=out, capture_output=True, text=True)


def _git(out: Path, *args):
    return subprocess.run(["git", *args], cwd=out, capture_output=True, text=True)


def _seed(out: Path):
    """A synthetic worked item: story + issue-linked plan + commit + review."""
    reg = out / "docs/process/feature-registry"
    reg.mkdir(parents=True, exist_ok=True)
    (out / "tests").mkdir(exist_ok=True)
    (out / "tests/test_x.py").write_text("def test_x():\n    pass\n")
    (reg / "STORY-0007.json").write_text(json.dumps(
        {"id": "STORY-0007", "title": "Billing hook", "story": "s",
         "acceptance": [{"id": "AC1", "text": "a"}],
         "tests": ["tests/test_x.py"], "status": "done", "issue": "#42"}))
    plans = out / ".process-work/plans/archive"
    plans.mkdir(parents=True, exist_ok=True)
    (plans / "2026-07-01-billing-hook.md").write_text(
        "# Plan\n\ntier: 2\nissue: #42\n\nImplements STORY-0007.\n")
    j = out / ".process-work/journal"
    j.mkdir(parents=True, exist_ok=True)
    (j / "2026-07-02.md").write_text(
        "- REVIEW work=42 tier=2 reviewer=fresh model=x independence=fresh-context "
        "verdict=pass round=1\n")
    r = out / ".process-work/reviews"
    r.mkdir(parents=True, exist_ok=True)
    (r / "2026-07-02-billing.md").write_text(
        "review: billing-hook\nwork: #42\nissue: #57\n\n## Prompt\n\nx\n\n"
        "## Findings\nFINDING sev=minor action=fix issue=- edge case\n")
    _git(out, "init", "-q")
    _git(out, "config", "user.email", "t@t")
    _git(out, "config", "user.name", "t")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "feat: billing hook (STORY-0007, #42)")


def test_present_on_every_profile(render, tmp_path):
    # trace is a core tool: its spine (plans/journal/reviews/git) is core
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    assert (out / "scripts/process/trace.py").is_file()


def test_selftest(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    r = _run(out, "--selftest")
    assert r.returncode == 0, r.stderr + r.stdout


def test_traces_story_end_to_end(render, tmp_path):
    out = render(tmp_path, {"project_name": "d",
                            "modules": {"feature_registry": True}})
    _seed(out)
    r = _run(out, "STORY-0007")
    assert r.returncode == 0, r.stderr
    t = r.stdout
    assert "story STORY-0007: Billing hook" in t and "status: done" in t
    assert "2026-07-01-billing-hook.md [archived (merged)]" in t and "tier: 2" in t
    assert "billing hook (STORY-0007, #42)" in t          # the commit
    assert "REVIEW work=42" in t                          # the attestation
    assert "review: billing-hook" in t or "billing" in t  # the report
    assert "FINDING sev=minor" in t


def test_traces_by_issue_ref(render, tmp_path):
    out = render(tmp_path, {"project_name": "d",
                            "modules": {"feature_registry": True}})
    _seed(out)
    r = _run(out, "#42")
    t = r.stdout
    assert "story STORY-0007" in t          # issue resolved back to its story
    assert "REVIEW work=42" in t


def test_commit_grep_skips_bare_number(render, tmp_path):
    # '#42' must not surface unrelated commits that merely contain "42"
    out = render(tmp_path, {"project_name": "d",
                            "modules": {"feature_registry": True}})
    _seed(out)
    _git(out, "commit", "-q", "--allow-empty", "-m", "chore: bump to v0.42.1")
    _git(out, "commit", "-q", "--allow-empty", "-m", "feat: PR-142 follow-up")
    t = _run(out, "#42").stdout
    assert "billing hook (STORY-0007, #42)" in t
    assert "v0.42.1" not in t and "PR-142" not in t


def test_review_line_renders_single_bullet(render, tmp_path):
    out = render(tmp_path, {"project_name": "d",
                            "modules": {"feature_registry": True}})
    _seed(out)
    t = _run(out, "#42").stdout
    assert "- REVIEW work=42" in t
    assert "- - REVIEW" not in t


def test_blank_query_refused(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    r = _run(out, "")
    assert r.returncode != 0  # usage, not a match-everything trace


def test_empty_repo_is_not_git_unavailable(render, tmp_path):
    # unborn branch: an empty commit trail, honestly not "git unavailable"
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _git(out, "init", "-q")
    t = _run(out, "#7").stdout
    assert "git unavailable" not in t


def test_honest_about_missing_sources(render, tmp_path):
    # minimal profile, no git, nothing seeded: every gap is named, exit 0
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    r = _run(out, "#99")
    assert r.returncode == 0, r.stderr
    t = r.stdout
    assert "gh unavailable" in t or "ref only" in t
    assert "none found" in t                              # plans
    assert "no REVIEW attestation" in t


def test_bare_digit_key_does_not_match_every_plan(render, tmp_path):
    # SP52: issue #7's bare "7" must not substring-match dates/step numbers —
    # and "#7" must not match "#70"
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    plans = out / ".process-work/plans"
    plans.mkdir(parents=True, exist_ok=True)
    (plans / "2026-07-11-unrelated.md").write_text(
        "# Unrelated\n\ntier: 2\nissue: #70\nstep 7 of the plan\n")
    (plans / "2026-01-01-target.md").write_text(
        "# Target\n\ntier: 2\nissue: #7\n")
    r = subprocess.run(
        [sys.executable, str(out / "scripts/process/trace.py"), "#7"],
        cwd=out, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "target.md" in r.stdout
    assert "unrelated.md" not in r.stdout
