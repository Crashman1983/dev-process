#!/usr/bin/env python3
"""ci_evidence — refuse a release whose commit has no green CI run on main.

    python3 tools/ci_evidence.py <40-hex sha>    (GITHUB_REPOSITORY, GH_TOKEN)

release-tag.yml runs it before it tags, release-publish.yml for the tag's commit
before it publishes. The proof is a `push` run of ci.yml on `main` for exactly
that SHA, in this repository, completed with success, and every REQUIRED_JOBS
entry in it completed with success. If several runs match, the newest decides —
a green older run does not cover a red re-run.

Not per-commit check runs: a pull_request run attaches its checks to the PR head
SHA but tests a synthetic merge commit, so a green check there is no proof for
the commit that lands on main.

Stdlib only: the publish job has no uv.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.parse
import urllib.request

# tests/test_ci_evidence.py derives these from ci.yml (jobs × matrix) — drift fails there
REQUIRED_JOBS = ("test", "portable-smoke (macos-latest)", "portable-smoke (windows-latest)")
SHA = re.compile(r"^[0-9a-f]{40}$")
API = "https://api.github.com"


def decisive(sha: str, runs: list[dict], repo: str) -> dict | None:
    """The newest push run of `sha` on main in `repo`, or None."""
    mine = [r for r in runs
            if r.get("head_sha") == sha and r.get("event") == "push"
            and r.get("head_branch") == "main"
            and (r.get("repository") or {}).get("full_name") == repo]
    return max(mine, key=lambda r: (r.get("run_number") or 0, r.get("created_at") or ""),
               default=None)


def verdict(sha: str, runs: list[dict], jobs_by_run: dict, repo: str) -> tuple[bool, str]:
    """(ok, reason) for `sha` given ci.yml runs and the jobs of each run (by run id)."""
    if not SHA.match(sha or ""):
        return False, f"{sha!r} is no full 40-hex commit SHA"
    run = decisive(sha, runs, repo)
    if run is None:
        return False, f"no CI run for {sha} on main — wait for CI after merge"
    where = run.get("html_url") or f"run {run.get('id')}"
    if run.get("status") != "completed":
        return False, f"CI run for {sha} is {run.get('status')} — wait for it ({where})"
    if run.get("conclusion") != "success":
        return False, f"CI run for {sha} concluded {run.get('conclusion')} ({where})"
    jobs = {j.get("name"): j for j in jobs_by_run.get(run.get("id"), [])}
    for name in REQUIRED_JOBS:
        job = jobs.get(name)
        if job is None:
            return False, f"required job {name!r} missing in {where}"
        if job.get("status") != "completed" or job.get("conclusion") != "success":
            return False, (f"required job {name!r} is {job.get('status')}/"
                           f"{job.get('conclusion')} in {where}")
    return True, where


def _get(url: str, token: str) -> dict:
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def _all(url: str, key: str, token: str, pages: int = 10) -> list[dict]:
    """Every item of a paginated list endpoint (per_page=100; capped — defensive)."""
    out: list[dict] = []
    total = 0
    for page in range(1, pages + 1):
        body = _get(f"{url}&page={page}", token)
        total = body.get("total_count") or 0
        items = body.get(key) or []
        out.extend(items)
        if len(items) < 100:
            break
    if total > len(out):  # truncated: an unseen run or job could be the decisive one
        raise OSError(f"{total} entries, read only {len(out)}")
    return out


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: ci_evidence.py <40-hex sha>", file=sys.stderr)
        return 2
    sha = argv[0]
    repo, token = os.environ.get("GITHUB_REPOSITORY", ""), os.environ.get("GH_TOKEN", "")
    if not SHA.match(sha):
        print(f"ci-evidence: refused — {sha!r} is no full 40-hex commit SHA")
        return 1
    if not repo or not token:
        print("ci-evidence: refused — GITHUB_REPOSITORY and GH_TOKEN are required")
        return 1
    base = f"{API}/repos/{repo}/actions"
    query = urllib.parse.urlencode(
        {"head_sha": sha, "event": "push", "branch": "main", "per_page": 100})
    try:
        runs = _all(f"{base}/workflows/ci.yml/runs?{query}", "workflow_runs", token)
        jobs_by_run = {}
        run = decisive(sha, runs, repo)
        if run is not None:  # jobs only of the run that decides
            jobs_by_run[run["id"]] = _all(
                f"{base}/runs/{run['id']}/jobs?filter=latest&per_page=100", "jobs", token)
    except OSError as exc:  # URLError/HTTPError included
        print(f"ci-evidence: refused — GitHub API: {exc}")
        return 1
    ok, reason = verdict(sha, runs, jobs_by_run, repo)
    print(f"ci-evidence: OK {sha} run {reason}" if ok else f"ci-evidence: refused — {reason}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
