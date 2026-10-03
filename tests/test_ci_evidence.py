"""tools/ci_evidence.py — a release needs a green push run of ci.yml on main for its SHA."""
import importlib.util
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
SHA = "a" * 40
OTHER = "b" * 40
SLUG = "owner/dev-process"


def _load():
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("ci_evidence", REPO / "tools/ci_evidence.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ev = _load()


def _run(id=1, number=1, sha=SHA, event="push", branch="main", repo=SLUG,
         status="completed", conclusion="success"):
    return {"id": id, "run_number": number, "head_sha": sha, "event": event,
            "head_branch": branch, "repository": {"full_name": repo}, "status": status,
            "conclusion": conclusion, "created_at": f"2026-01-0{number}T00:00:00Z",
            "html_url": f"https://github.com/{repo}/actions/runs/{id}"}


def _jobs(**override):
    jobs = {name: ("completed", "success") for name in ev.REQUIRED_JOBS}
    jobs.update(override)
    return [{"name": n, "status": s, "conclusion": c} for n, (s, c) in jobs.items() if s]


def _verdict(runs, jobs=None, sha=SHA):
    return ev.verdict(sha, runs, {1: _jobs() if jobs is None else jobs}, SLUG)


def test_a_green_push_run_on_main_is_proof():
    ok, reason = _verdict([_run()])
    assert ok and reason.endswith("/actions/runs/1"), reason


@pytest.mark.parametrize("runs", [
    pytest.param([_run(sha=OTHER)], id="other-sha"),
    pytest.param([], id="no-evidence"),
    pytest.param([_run(event="pull_request")], id="pull-request-same-sha"),
    pytest.param([_run(branch="feature")], id="other-branch"),
    pytest.param([_run(repo="fork/dev-process")], id="other-repo"),
])
def test_no_matching_run_is_refused(runs):
    """Only a push run on main in this repository tests the commit that landed there."""
    ok, reason = _verdict(runs)
    assert not ok and "wait for CI after merge" in reason, reason


@pytest.mark.parametrize(("status", "conclusion"), [
    ("in_progress", None), ("queued", None), ("completed", "failure"),
    ("completed", "cancelled"),
])
def test_an_unfinished_or_red_run_is_refused(status, conclusion):
    ok, reason = _verdict([_run(status=status, conclusion=conclusion)])
    assert not ok and (conclusion or status) in reason, reason


@pytest.mark.parametrize("state", [("completed", "skipped"), ("completed", "neutral"),
                                   ("completed", "timed_out"), ("in_progress", None)])
def test_a_required_job_not_green_is_refused(state):
    """A run can conclude success with a matrix leg skipped."""
    ok, reason = _verdict([_run()], _jobs(**{"portable-smoke (windows-latest)": state}))
    assert not ok and "windows-latest" in reason, reason


def test_a_missing_required_job_is_refused():
    ok, reason = _verdict([_run()], _jobs(test=(None, None)))
    assert not ok and "'test' missing" in reason, reason


def test_the_newest_run_decides_over_an_older_green_one():
    """A red re-run is not covered by the green run before it."""
    runs = [_run(id=1, number=1), _run(id=2, number=2, conclusion="failure")]
    ok, reason = ev.verdict(SHA, runs, {1: _jobs(), 2: _jobs()}, SLUG)
    assert not ok and "failure" in reason, reason


@pytest.mark.parametrize("sha", ["a" * 7, "A" * 40, "g" * 40, "", "--delete", "a" * 41])
def test_a_malformed_sha_is_refused(sha):
    ok, reason = ev.verdict(sha, [_run(sha=sha)], {1: _jobs()}, SLUG)
    assert not ok and "40-hex" in reason, reason
    assert ev.main([sha]) == 1


def test_required_jobs_match_ci_yml():
    """Drift: a renamed job or matrix leg would refuse every release (or prove nothing)."""
    wf = yaml.safe_load((REPO / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    names = set()
    for job_id, job in wf["jobs"].items():
        name = job.get("name", job_id)
        oses = job.get("strategy", {}).get("matrix", {}).get("os")
        names |= {f"{name} ({os})" for os in oses} if oses else {name}
    assert names == set(ev.REQUIRED_JOBS)


@pytest.mark.parametrize("workflow", ["release-tag.yml", "release-publish.yml"])
def test_release_workflows_check_ci_evidence_before_they_act(workflow):
    text = (REPO / ".github/workflows" / workflow).read_text(encoding="utf-8")
    assert "actions: read" in text
    check = text.index("python3 tools/ci_evidence.py")
    acts = [text.find(word) for word in ("git tag", "gh release", "git push origin")]
    assert check < min(i for i in acts if i >= 0), workflow
