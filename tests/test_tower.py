import json
import subprocess
import sys
from pathlib import Path


def _git(root: Path, *args: str):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True)


def _tower(out: Path, *args: str):
    return subprocess.run([sys.executable, str(out / "scripts/process/tower.py"), *args],
                          cwd=out, capture_output=True, text=True)


def _report(out: Path, *args: str):
    return subprocess.run([sys.executable, str(out / "scripts/process/report.py"), *args],
                          cwd=out, capture_output=True, text=True)


def _repo(out: Path) -> None:
    _git(out, "init", "-q", "-b", "main")
    _git(out, "config", "user.email", "t@t")
    _git(out, "config", "user.name", "t")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "base")


def _worktree(out: Path, name: str, files: dict[str, str], plan: str | None = None) -> Path:
    wt = out.parent / f"wt-{name}"
    _git(out, "worktree", "add", "-q", "-b", name, str(wt), "main")
    for rel, text in files.items():
        p = wt / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    if plan:
        d = wt / ".process-work/plans"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"2026-09-20-{name}.md").write_text(plan)
    _git(wt, "add", "-A")
    _git(wt, "commit", "-q", "-m", f"feat: {name}")
    return wt


def test_core_tools_present(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    assert (out / "scripts/process/tower.py").is_file()
    assert (out / "scripts/process/report.py").is_file()
    assert (out / ".claude/commands/report.md").is_file()
    assert (out / "docs/process/tower.md").is_file()


def test_tower_sees_worktrees_and_overlaps(render, tmp_path):
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    _repo(out)
    _worktree(out, "alpha", {"src/owner.py": "a = 1\n", "src/other.py": "x\n"})
    _worktree(out, "beta", {"src/owner.py": "a = 2\n"})
    _worktree(out, "gamma", {"src/third.py": "y\n"})
    r = _tower(out, "--json")
    assert r.returncode == 0, r.stderr
    t = json.loads(r.stdout)
    branches = {w["branch"] for w in t["worktrees"]}
    assert {"main", "alpha", "beta", "gamma"} <= branches
    alpha = next(w for w in t["worktrees"] if w["branch"] == "alpha")
    assert alpha["ahead"] == 1 and "src/owner.py" in alpha["in_flight"]
    kinds = {(o["a"], o["b"], o["kind"]) for o in t["overlaps"]}
    assert ("alpha", "beta", "file") in kinds
    assert ("alpha", "gamma", "directory") in kinds
    high = [f for f in t["findings"] if f["kind"] == "overlap" and f["severity"] == "high"]
    assert high and "src/owner.py" in high[0]["what"]
    text = _tower(out).stdout
    assert "worktrees (4)" in text and "[high] overlap" in text
    # --min-severity drops the directory overlap
    t2 = json.loads(_tower(out, "--json", "--min-severity", "high").stdout)
    assert all(f["severity"] == "high" for f in t2["findings"])


def test_plan_findings_and_design_papers_exempt(render, tmp_path):
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    _repo(out)
    plans = out / ".process-work/plans"
    plans.mkdir(parents=True, exist_ok=True)
    (plans / "2026-09-20-noissue.md").write_text("# P\n\ntier: 2\n\n## Decisions\n\nDECISION 2026-09-20 me: x — because y\n")
    (plans / "2026-09-20-notier.md").write_text("# P\n\nissue: #4\n")
    (plans / "2026-09-20-nodecisions.md").write_text("# P\n\ntier: 3\nissue: #5\n")
    (plans / "design-2026-09-20-paper.md").write_text("# Design\n\nno tier here\n")
    t = json.loads(_tower(out, "--json").stdout)
    kinds = {(f["kind"], Path(f["what"].split(" ")[0]).stem) for f in t["findings"]}
    assert ("plan-without-issue", "2026-09-20-noissue") in kinds
    assert ("plan-without-tier", "2026-09-20-notier") in kinds
    assert ("plan-without-decisions", "2026-09-20-nodecisions") in kinds
    assert not any("design-2026-09-20-paper" in f["what"] for f in t["findings"])
    paper = next(p for p in t["plans"] if "paper" in p["path"])
    assert paper["kind"] == "design"
    noissue = next(p for p in t["plans"] if "noissue" in p["path"])
    assert noissue["decisions"] == 1 and noissue["has_decisions_section"]


def test_reports_feed_the_tower_and_stale_workers_are_found(render, tmp_path):
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    _repo(out)
    wt = _worktree(out, "quiet", {"src/q.py": "q\n"})
    r = _report(wt, "planned", "--issue", "7", "--note", "plan committed")
    assert r.returncode == 0 and "quiet → planned #7" in r.stdout
    common = _git(out, "rev-parse", "--git-common-dir").stdout.strip()
    ledger = Path(common if Path(common).is_absolute() else out / common) / "process-tower/reports.jsonl"
    assert ledger.is_file() and '"state": "planned"' in ledger.read_text()
    t = json.loads(_tower(out, "--json").stdout)
    rep = next(x for x in t["reports"] if x["worker"] == "quiet")
    assert rep["state"] == "planned" and rep["issue"] == 7 and rep["minutes_ago"] == 0
    assert not any(f["kind"] == "stale-worker" for f in t["findings"])
    # with a zero stale budget the worker (ahead, no fresh commit) is stale
    t2 = json.loads(_tower(out, "--json", "--stale-minutes", "0").stdout)
    stale = [f for f in t2["findings"] if f["kind"] == "stale-worker"]
    assert stale and "quiet" in stale[0]["what"]
    # a blocked report older than the budget is a high finding
    _report(wt, "blocked", "--issue", "7", "--note", "lane held")
    t3 = json.loads(_tower(out, "--json", "--stale-minutes", "0").stdout)
    blocked = [f for f in t3["findings"] if f["kind"] == "blocked"]
    assert blocked and "lane held" in blocked[0]["what"]
    # reports are never in the tree
    assert not [p for p in out.rglob("reports.jsonl") if ".git" not in p.parts]


def test_red_ledger_age_is_a_finding(render, tmp_path):
    import datetime
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    _repo(out)
    old = (datetime.date.today() - datetime.timedelta(days=4)).isoformat()
    (out / ".git/process-red-ledger").write_text(f"review {old}\n")
    t = json.loads(_tower(out, "--json").stdout)
    assert t["gates"] == [{"gate": "review", "since": old, "age_days": 4}]
    assert any(f["kind"] == "chronic-red" and "review" in f["what"] for f in t["findings"])


def test_report_rejects_unknown_state(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    assert _report(out, "sleeping").returncode != 0
