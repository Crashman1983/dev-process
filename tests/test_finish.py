"""SP62: the /finish tail checker — blocked without a clearing pass, ready
with one, and the printed tail carries the ritual order."""
import subprocess
import sys
from pathlib import Path

JOURNAL = ".process-work/journal"
PLANS = ".process-work/plans"


def _run(root):
    return subprocess.run(
        [sys.executable, str(root / "scripts/process/finish.py"), "."],
        cwd=root, capture_output=True, text=True,
    )


def _git(root: Path, *args: str):
    return subprocess.run(["git", *args], cwd=root, capture_output=True,
                          text=True, check=True)


def _repo_on_feature(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    _git(out, "init", "-q", "-b", "main")
    _git(out, "config", "user.email", "t@example.com")
    _git(out, "config", "user.name", "Test")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "base")
    _git(out, "checkout", "-q", "-b", "feature")
    return out


def _active_plan(root, name, body):
    d = root / PLANS
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(body, encoding="utf-8")


def _journal(root, *lines, name="2026-07-04.md"):
    d = root / JOURNAL
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_blocked_on_main(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    _git(out, "init", "-q", "-b", "main")
    _git(out, "config", "user.email", "t@example.com")
    _git(out, "config", "user.name", "Test")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "base")
    r = _run(out)
    assert r.returncode == 1
    assert "no feature branch to finish" in r.stdout


def test_blocked_without_clearing_pass(render, tmp_path):
    out = _repo_on_feature(render, tmp_path)
    _active_plan(out, "2026-07-04-widget.md", "# Plan\n\ntier: 2\nissue: none\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "feat: widget plan")
    r = _run(out)
    assert r.returncode == 1
    assert "no clearing REVIEW" in r.stdout and "/review before /finish" in r.stdout


def test_ready_with_pass_prints_ordered_tail(render, tmp_path):
    out = _repo_on_feature(render, tmp_path)
    _active_plan(out, "2026-07-04-widget.md", "# Plan\n\ntier: 2\nissue: none\n")
    _journal(out, "REVIEW work=widget tier=2 reviewer=fresh model=same "
                  "independence=bundle,non-implementing verdict=pass round=1")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "feat: widget with pass")
    r = _run(out)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "finish: ready" in r.stdout
    # ritual order: archive before merge, merge before branch delete
    ai = r.stdout.index("archive the plan")
    mi = r.stdout.index("merge:")
    di = r.stdout.index("--delete")
    assert ai < mi < di
    assert "worktree" in r.stdout


def test_blocked_on_dirty_worktree(render, tmp_path):
    out = _repo_on_feature(render, tmp_path)
    (out / "untracked.txt").write_text("wip\n", encoding="utf-8")
    r = _run(out)
    assert r.returncode == 1
    assert "worktree not clean" in r.stdout


# --- SP64: the speckit path's plans reach the presence question ------------

def _spec_dir(root, name, *, tier=2, ticked=True, issue="#42"):
    d = root / "specs" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "plan.md").write_text(f"# Plan\n\ntier: {tier}\nissue: {issue}\n",
                               encoding="utf-8")
    box = "x" if ticked else " "
    (d / "tasks.md").write_text(f"- [{box}] T001 do the thing\n",
                                encoding="utf-8")
    return d


def test_speckit_plan_without_pass_blocks(render, tmp_path):
    out = _repo_on_feature(render, tmp_path)
    _spec_dir(out, "009-widget", tier=3, ticked=True)
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "feat: widget spec work")
    r = _run(out)
    assert r.returncode == 1
    assert "specs/009-widget" in r.stdout and "/review before /finish" in r.stdout


def test_speckit_plan_with_pass_is_ready_and_prunes(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo",
                            "modules": {"speckit": True}})
    _git(out, "init", "-q", "-b", "main")
    _git(out, "config", "user.email", "t@example.com")
    _git(out, "config", "user.name", "Test")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "base")
    _git(out, "checkout", "-q", "-b", "feature")
    _spec_dir(out, "009-widget", tier=2, ticked=True, issue="#9")
    _journal(out, "REVIEW work=9 tier=2 reviewer=fresh model=same "
                  "independence=bundle,non-implementing verdict=pass round=1")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "feat: widget with pass")
    r = _run(out)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "publish_and_prune.py specs/009-widget" in r.stdout


def test_speckit_plan_in_flight_is_not_blocked(render, tmp_path):
    out = _repo_on_feature(render, tmp_path)
    _spec_dir(out, "009-widget", tier=3, ticked=False)
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "feat: widget in flight")
    r = _run(out)
    assert r.returncode == 0, r.stdout + r.stderr


def test_tail_names_the_full_suite_before_merge(render, tmp_path):
    out = _repo_on_feature(render, tmp_path)
    r = _run(out)
    assert r.returncode == 0, r.stdout + r.stderr
    fi = r.stdout.index("FULL test suite")
    mi = r.stdout.index("merge:")
    assert fi < mi  # the batch pays completeness before it merges
