"""#243: pinning tests for four downstream fixes the template already carries —
the push stamp's scope, finish from a worktree while main is checked out
elsewhere, the train's stage times, and dispatch's dead workers."""
import json
import os
import signal
import subprocess
import sys
from pathlib import Path

from test_dispatch import _fake_command, _load_dispatch
from test_dispatch import _repo as _dispatch_repo
from test_finish import _git as _finish_git
from test_finish import _repo_with_origin, _run_args
from test_pre_push import _probe, _push, _write, project  # noqa: F401 — `project` is a fixture
from test_train import _branch, _repo, _retry_batch, _train

STAGE_SUITE = ('d=$(git rev-parse --absolute-git-dir)/merge-suite; mkdir -p "$d"; '
               'echo a > "$d/stages"; echo "1000 1010 0" > "$d/a.time"')


def _rev(root: Path, ref: str) -> str:
    return subprocess.run(["git", "-C", str(root), "rev-parse", ref],
                          capture_output=True, text=True, check=True).stdout.strip()


# --- pre_push: the stamp names the scope it proved -----------------------------


def test_a_bookkeeping_only_stamp_does_not_clear_the_same_sha_when_code_is_in_scope(project, tmp_path):  # noqa: F811
    """Downstream Kenni #2221: a gates-only stamp let the same SHA skip its tests once code was in scope."""
    out, bare, git = project
    code = git("rev-parse", "HEAD").stdout.strip()
    base = git("rev-parse", "main").stdout.strip()
    _write(out, ".process-work/journal/2026-10-10.md", "note\n")
    git("add", "-A")
    git("commit", "-qm", "journal")
    # the fork point at the code commit: only bookkeeping differs — gates only, stamped
    git("update-ref", "refs/remotes/origin/main", code)
    r = _push(git, "origin", "feature")
    assert r.returncode == 0 and "passed this push before" not in r.stderr, r.stderr
    assert _probe(tmp_path) == ["g"]
    # the same SHA with the fork point back at base: code is in scope, the tests run
    git("update-ref", "refs/remotes/origin/main", base)
    r = _push(git, "origin", "feature:refs/heads/copy")
    assert r.returncode == 0, r.stderr
    assert "passed this push before" not in r.stderr, r.stderr
    assert _probe(tmp_path) == ["g", "t app_tests"]


# --- finish: main checked out in another worktree ------------------------------


def _with_main_elsewhere(render, tmp_path):
    out, bare = _repo_with_origin(render, tmp_path)
    other = tmp_path / "main-wt"
    _finish_git(out, "worktree", "add", "-q", str(other), "main")
    return out, bare, other


def test_finish_pushes_head_to_main_and_fast_forwards_a_clean_checkout_elsewhere(render, tmp_path):
    """Downstream Kenni #2329: finish from a branch checkout must not check out main another worktree holds."""
    out, bare, other = _with_main_elsewhere(render, tmp_path)
    r = _run_args(out, "--apply", "--tests-passed")
    assert r.returncode == 0, r.stdout + r.stderr
    tip = _rev(out, "HEAD")
    assert _rev(bare, "main") == tip
    assert _rev(other, "HEAD") == tip  # the other checkout followed, files and ref together
    assert _finish_git(other, "status", "--porcelain").stdout == ""
    assert _finish_git(out, "symbolic-ref", "--short", "HEAD").stdout.strip() == "feature"


def test_finish_keeps_a_dirty_checkout_of_main_elsewhere_unchanged(render, tmp_path):
    """Downstream Kenni #2329: a dirty checkout of main elsewhere is never moved under the owner's work."""
    out, bare, other = _with_main_elsewhere(render, tmp_path)
    before = _rev(other, "HEAD")
    (other / "owner-note.txt").write_text("local owner work\n")
    r = _run_args(out, "--apply", "--tests-passed")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "kept unchanged" in r.stdout, r.stdout
    assert _rev(bare, "main") == _rev(out, "HEAD")
    assert _rev(other, "HEAD") == before
    assert (other / "owner-note.txt").read_text() == "local owner work\n"


def test_finish_refuses_when_origin_main_moved_past_head_after_the_rebase(render, tmp_path):
    """Downstream Kenni #2329: with main elsewhere, a push over a moved origin/main is refused by name."""
    out, bare, other = _with_main_elsewhere(render, tmp_path)
    racer = tmp_path / "racer"
    # the suite runs after finish's rebase: another clone lands on main meanwhile
    script = tmp_path / "race.sh"
    script.write_text(
        "set -e\n"
        f"git clone -q -b main '{bare}' '{racer}'\n"
        f"git -C '{racer}' -c user.email=t@t -c user.name=t commit -q --allow-empty -m race\n"
        f"git -C '{racer}' push -q origin main\n"
        "git fetch -q origin main\n")
    head_main = _rev(other, "HEAD")
    r = _run_args(out, "--apply", "--tests", f"sh {script}")
    assert r.returncode == 1, r.stdout + r.stderr
    assert "is not an ancestor of HEAD — rebase" in r.stderr, r.stdout + r.stderr
    assert _rev(bare, "main") == _rev(racer, "HEAD") != _rev(out, "HEAD")
    assert _rev(other, "HEAD") == head_main


# --- train: the merge suite's stage times reach the log ------------------------


def test_the_train_logs_the_stage_times_its_merge_suite_left(render, tmp_path):
    """Downstream Kenni #2600: the train never collected the stage markers its merge suite wrote."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    r = _train(out, "run", "--force", "--suite", STAGE_SUITE)
    assert r.returncode == 0, r.stdout + r.stderr
    logs = sorted((out / ".git/process-train").glob("*.log"))
    text = logs[-1].read_text()
    assert "stage a: green 10 s" in text, text


def test_a_retry_logs_the_stage_times_of_its_own_run(render, tmp_path, monkeypatch):
    """Downstream Kenni #2600: the stages a --retry run wrote are collected after the retry too."""
    suite_dir = tmp_path / "repo/.git/merge-suite"

    def sh(cmd, n):
        if n == 1:
            return "red"
        suite_dir.mkdir(parents=True, exist_ok=True)
        (suite_dir / "stages").write_text("a\n")
        (suite_dir / "a.time").write_text("1000 1010 0\n")
        return "green"

    _builds, runs, log = _retry_batch(render, tmp_path, monkeypatch, retry="make retry", sh=sh)
    assert runs[:2] == ["suite", "make retry"], runs
    assert "stage a: green 10 s" in log, log


# --- dispatch: a dead worker's record is no live session -----------------------


def _gone_worker(render, tmp_path, monkeypatch, **extra):
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    _dispatch_repo(out)
    mod = _load_dispatch(out)
    rec = {"branch": "7-work", "issue": 7, "phase": "plan", "tier": 2,
           "tmux_window": "@9", "started": 1, **extra}
    mod._write_record(out, "7-work", rec)
    tmux = []
    monkeypatch.setattr(mod, "_pane_state", lambda w: "gone")
    monkeypatch.setattr(mod, "_tmux", lambda *a: tmux.append(a) or subprocess.CompletedProcess(a, 1, "", "gone"))
    return out, mod, out / ".git/process-dispatch/7-work.json", tmux


def test_start_replaces_the_record_of_a_worker_whose_window_is_gone(render, tmp_path, monkeypatch):
    """Downstream Kenni #2248: a worker whose tmux window is gone blocked its branch until a manual stop."""
    out, mod, path, _tmux = _gone_worker(render, tmp_path, monkeypatch)
    _fake_command(out, "sleep 30\n")
    rc = mod.start(out, issue=7, phase="plan", tier=2, branch="7-work", title=None, dry_run=False)
    rec = json.loads(path.read_text()) if path.is_file() else {}
    try:
        assert rc == 0
        assert "tmux_window" not in rec and rec.get("pid"), rec
    finally:
        if rec.get("pid"):
            try:
                os.killpg(os.getpgid(rec["pid"]), signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass


def test_stop_removes_a_gone_workers_record_although_its_worktree_is_dirty(render, tmp_path, monkeypatch, capsys):
    """Downstream Kenni #2248: stop refused a gone worker over its dirty worktree — nothing left to stop."""
    wt = tmp_path / "wt"
    out, mod, path, tmux = _gone_worker(render, tmp_path, monkeypatch, worktree=str(wt))
    _finish_git(out, "worktree", "add", "-q", "-b", "7-work", str(wt))
    (wt / "draft.md").write_text("plan in progress\n")
    assert mod.stop(out, "7-work", force=False) == 0
    said = capsys.readouterr()
    assert "7-work is gone — record removed" in said.out, said.out + said.err
    assert not path.exists()
    assert (wt / "draft.md").read_text() == "plan in progress\n"  # the work stays for its owner
    assert not [a for a in tmux if a[0] == "kill-window"]
