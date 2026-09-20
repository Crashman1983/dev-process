import json
import subprocess
import sys
from pathlib import Path


def _git(root: Path, *args: str):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True)


def _train(out: Path, *args: str):
    return subprocess.run([sys.executable, str(out / "scripts/process/train.py"), *args],
                          cwd=out, capture_output=True, text=True)


def _repo(out: Path) -> None:
    _git(out, "init", "-q", "-b", "main")
    _git(out, "config", "user.email", "t@t")
    _git(out, "config", "user.name", "t")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "base")


def _branch(out: Path, name: str, files: dict[str, str], *, tier: int = 2, reviewed: bool = True,
            archive: bool = True) -> None:
    _git(out, "checkout", "-q", "-b", name, "main")
    for rel, text in files.items():
        p = out / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    if archive:
        a = out / ".process-work/plans/archive"
        a.mkdir(parents=True, exist_ok=True)
        (a / f"2026-09-20-{name}.md").write_text(f"# {name}\n\ntier: {tier}\nissue: #1\n\n## Decisions\n")
    if reviewed:
        j = out / ".process-work/journal"
        j.mkdir(parents=True, exist_ok=True)
        (j / f"2026-09-20-{name}.md").write_text(
            f"REVIEW work={name} tier={tier} reviewer=fresh model=cross "
            f"independence=bundle,non-implementing verdict=pass round=1\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", f"feat: {name}")
    _git(out, "checkout", "-q", "main")


def test_plan_boards_cleared_branches_and_explains_the_rest(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    _branch(out, "beta", {"src/b.py": "b\n"}, reviewed=False)                 # no pass
    _branch(out, "gamma", {"src/a.py": "conflict\n", "src/g.py": "g\n"})       # overlaps alpha
    _branch(out, "delta", {"src/d.py": "d\n"}, archive=False, reviewed=False)  # not finished
    _branch(out, "tiny", {"README.md": "tiny\n"}, tier=1, reviewed=False)      # tier 1 needs no pass
    r = _train(out, "plan", "--json")
    assert r.returncode == 0, r.stderr
    p = json.loads(r.stdout)
    by = {c["branch"]: c for c in p["candidates"]}
    assert by["alpha"]["eligible"] and "REVIEW pass" in by["alpha"]["by"]
    assert not by["beta"]["eligible"] and "without a clearing REVIEW pass" in by["beta"]["reasons"][0]
    assert not by["gamma"]["eligible"] and "overlaps" in by["gamma"]["reasons"][0]
    assert not by["delta"]["eligible"] and "run /finish first" in by["delta"]["reasons"][0]
    assert by["tiny"]["eligible"]
    assert p["ready"] is False and "waiting for 3" in p["why"]  # 2 aboard, fresh
    text = _train(out, "plan").stdout
    assert "✓ alpha" in text and "· beta" in text and "hold" in text
    # a worker report is accepted as the pointer when nothing is archived
    subprocess.run([sys.executable, str(out / "scripts/process/report.py"), "review-pass", "--worker", "delta"],
                   cwd=out, check=True, capture_output=True)
    p2 = json.loads(_train(out, "plan", "--json").stdout)
    delta = next(c for c in p2["candidates"] if c["branch"] == "delta")
    assert delta["eligible"] and "worker report review-pass" in delta["by"]
    # but never as a substitute for a missing pass on an archived plan
    subprocess.run([sys.executable, str(out / "scripts/process/report.py"), "done", "--worker", "beta"],
                   cwd=out, check=True, capture_output=True)
    p3 = json.loads(_train(out, "plan", "--json").stdout)
    beta = next(c for c in p3["candidates"] if c["branch"] == "beta")
    assert not beta["eligible"] and "the report is not the record" in beta["reasons"][0]
    assert p3["ready"] is True  # three aboard now


def test_run_merges_the_batch_behind_one_suite_and_drops_the_offender(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    _branch(out, "beta", {"src/b.py": "b\n"})
    _branch(out, "bad", {"src/BROKEN": "x\n"})
    marker = out.parent / "deployed"
    # the suite fails only when the offender's file is present; count the runs
    suite = f"test ! -e src/BROKEN && echo run >> {out.parent}/suite.log"
    r = _train(out, "run", "--force", "--suite", suite, "--deploy", f"touch {marker}")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "dropping it and rebuilding" in r.stdout and "bad" in r.stdout
    assert "main →" in r.stdout and "alpha, beta" in r.stdout
    log = _git(out, "log", "--oneline", "main").stdout
    assert "train: merge alpha" in log and "train: merge beta" in log and "merge bad" not in log
    assert (out / "src/a.py").is_file() and (out / "src/b.py").is_file() and not (out / "src/BROKEN").exists()
    # green runs: one bisection probe ([alpha]) + one for the surviving batch — never one per branch
    assert (out.parent / "suite.log").read_text().count("run") == 2
    assert marker.exists()
    branches = _git(out, "branch", "--list", "--format=%(refname:short)").stdout.split()
    assert "alpha" not in branches and "beta" not in branches and "bad" in branches
    assert not [b for b in branches if b.startswith("train/")]
    reports = subprocess.run([sys.executable, str(out / "scripts/process/tower.py"), "--json"],
                             cwd=out, capture_output=True, text=True).stdout
    t = json.loads(reports)
    states = {x["worker"]: x["state"] for x in t["reports"]}
    assert states["alpha"] == "done" and states["beta"] == "done" and states["bad"] == "blocked"


def test_run_refuses_a_dirty_or_wrong_root(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    (out / "dirty.txt").write_text("x")
    r = _train(out, "run", "--force")
    assert r.returncode == 2 and "not clean" in r.stderr
    (out / "dirty.txt").unlink()
    _git(out, "checkout", "-q", "-b", "elsewhere")
    r = _train(out, "run", "--force")
    assert r.returncode == 2 and "run from the root worktree on main" in r.stderr


def test_run_holds_without_departure_and_dry_run_touches_nothing(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    r = _train(out, "run", "--suite", "true")
    assert r.returncode == 0 and "holding" in r.stdout
    head = _git(out, "rev-parse", "main").stdout
    r = _train(out, "run", "--force", "--dry-run", "--suite", "true")
    assert "dry run" in r.stdout and _git(out, "rev-parse", "main").stdout == head


def test_core_files_present(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    assert (out / "scripts/process/train.py").is_file()
    assert (out / ".claude/commands/steward.md").is_file()
    assert (out / "docs/process/train.md").is_file()
