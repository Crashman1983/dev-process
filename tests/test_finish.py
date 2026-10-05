"""SP62: the /finish tail checker — blocked without a clearing pass, ready
with one, and the printed tail carries the ritual order."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

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


def test_on_main_names_the_unmerged_branches_and_their_worktrees(render, tmp_path):
    out = render(tmp_path / "main", {"project_name": "demo"})
    _git(out, "init", "-q", "-b", "main")
    _git(out, "config", "user.email", "t@example.com")
    _git(out, "config", "user.name", "Test")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "base")
    r = _run(out)
    assert "no branch is left unmerged into main" in r.stdout, r.stdout
    wt = tmp_path / "wt-7"
    _git(out, "worktree", "add", "-q", "-b", "7-widget", str(wt), "main")
    (wt / "w.txt").write_text("w\n")
    _git(wt, "add", "-A")
    _git(wt, "commit", "-q", "-m", "feat: w")
    _git(out, "branch", "8-gizmo", "7-widget")
    _git(out, "branch", "merged-one", "main")  # merged: not offered
    r = _run(out)
    assert r.returncode == 1
    assert (f"check out the branch first: cd {wt.resolve()} (holds 7-widget) | "
            f"git checkout 8-gizmo") in r.stdout, r.stdout
    assert "merged-one" not in r.stdout


def test_blocked_without_clearing_pass(render, tmp_path):
    out = _repo_on_feature(render, tmp_path)
    _active_plan(out, "2026-07-04-widget.md", "# Plan\n\ntier: 2\nissue: none\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "feat: widget plan")
    r = _run(out)
    assert r.returncode == 1
    assert "no clearing REVIEW" in r.stdout and "/review before /finish" in r.stdout


@pytest.mark.parametrize("name", ["2026-07-04-größe.md", "2026-07-04-new\nline.md"])
def test_a_plan_whose_name_git_quotes_is_still_this_branchs(render, tmp_path, name):
    # without -z git prints such a name quoted; the plan read as another
    # work's and finished without its review (downstream refutation)
    out = _repo_on_feature(render, tmp_path)
    _active_plan(out, name, "# Plan\n\ntier: 2\nissue: none\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "feat: plan with a quoted name")
    r = _run(out)
    assert r.returncode == 1, r.stdout
    assert "no clearing REVIEW" in r.stdout


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
    # deleting the base of a stacked PR closes it on GitHub — the tail says so
    assert "retarget a PR stacked on it first" in r.stdout[di:].split("\n", 1)[0]


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


def test_foreign_active_plan_does_not_block_this_branch(render, tmp_path):
    # SP65: a tier-3 decision paper committed on main by someone else is
    # neither this branch's review debt nor its archiving duty
    out = render(tmp_path, {"project_name": "demo"})
    _git(out, "init", "-q", "-b", "main")
    _git(out, "config", "user.email", "t@example.com")
    _git(out, "config", "user.name", "Test")
    _active_plan(out, "2026-09-01-foreign.md", "# Plan\n\ntier: 3\nissue: #5\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "base")
    _git(out, "checkout", "-q", "-b", "feature")
    (out / "payload.txt").write_text("mine\n", encoding="utf-8")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "feat: unrelated")
    r = _run(out)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "foreign" not in r.stdout
    # but a commit that CLAIMS the plan's issue pulls it in
    _git(out, "commit", "-q", "--allow-empty", "-m", "feat: do it (#5)")
    r = _run(out)
    assert r.returncode == 1
    assert "foreign" in r.stdout and "/review before /finish" in r.stdout


def test_not_runnable_gates_are_named_apart_from_red(render, tmp_path, monkeypatch):
    out = _repo_on_feature(render, tmp_path)
    (out / "scripts/process/gate_runner.py").unlink()
    r = _run(out)
    assert r.returncode == 1
    assert "NOT RUNNABLE (not red)" in r.stdout and "missing" in r.stdout


# --- v2.8.1: --apply executes the deterministic tail ------------------------

def _run_args(root, *args):
    return subprocess.run(
        [sys.executable, str(root / "scripts/process/finish.py"), *args, "."],
        cwd=root, capture_output=True, text=True,
    )


def _repo_with_origin(render, tmp_path):
    out = render(tmp_path / "work", {"project_name": "demo"})
    bare = tmp_path / "origin.git"
    _git(out, "init", "-q", "-b", "main")
    _git(out, "config", "user.email", "t@example.com")
    _git(out, "config", "user.name", "Test")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "base")
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    _git(out, "remote", "add", "origin", str(bare))
    _git(out, "push", "-q", "-u", "origin", "main")
    _git(out, "checkout", "-q", "-b", "feature")
    _active_plan(out, "2026-09-07-tiny.md", "# Plan\n\ntier: 1\n")
    (out / "payload.txt").write_text("done\n", encoding="utf-8")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "feat: tiny")
    _git(out, "push", "-q", "-u", "origin", "feature")
    return out, bare


def test_apply_archives_and_stops_before_the_merge(render, tmp_path):
    out, _bare = _repo_with_origin(render, tmp_path)
    r = _run_args(out, "--apply")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "stopped before the merge" in r.stdout
    assert (out / PLANS / "archive" / "2026-09-07-tiny.md").is_file()
    assert not (out / PLANS / "2026-09-07-tiny.md").exists()
    assert "archive plan(s) on merge" in _git(out, "log", "-1", "--format=%s").stdout
    assert _git(out, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == "feature"


def test_apply_with_asserted_suite_merges_pushes_and_deletes_branch(render, tmp_path):
    out, bare = _repo_with_origin(render, tmp_path)
    r = _run_args(out, "--apply", "--tests-passed")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "merged feature into main and pushed" in r.stdout
    assert _git(out, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == "main"
    remote_heads = subprocess.run(["git", "--git-dir", str(bare), "branch"],
                                  capture_output=True, text=True).stdout
    assert "feature" not in remote_heads and "main" in remote_heads
    remote_log = subprocess.run(["git", "--git-dir", str(bare), "log", "-1",
                                 "--format=%s", "main"],
                                capture_output=True, text=True).stdout
    assert "archive plan(s)" in remote_log


def test_finish_names_tokens_and_apply_writes_them_into_done(render, tmp_path):
    """No tokens per issue were recorded downstream; finish says the count or `not measured`
    and its `done` report carries the same line — no new form."""
    import json
    out, _bare = _repo_with_origin(render, tmp_path)
    r = _run(out)
    assert r.returncode == 0 and "finish: tokens: not measured" in r.stdout, r.stdout
    r = _run_args(out, "--apply", "--tests-passed")
    assert r.returncode == 0 and "finish: tokens: not measured" in r.stdout, r.stdout + r.stderr
    ledger = out / ".git/process-tower/reports.jsonl"
    done = [json.loads(line) for line in ledger.read_text().splitlines()]
    assert done[-1]["state"] == "done" and done[-1]["note"] == "tokens: not measured"
    assert done[-1]["worker"] == "feature"


def test_done_is_written_once_the_merge_is_pushed_even_if_the_branch_delete_fails(render, tmp_path):
    """Refute: `done` came only after the remote branch delete; a refused delete left a
    pushed merge without it."""
    import json
    out, bare = _repo_with_origin(render, tmp_path)
    hook = bare / "hooks/pre-receive"
    hook.write_text("#!/bin/sh\nwhile read old new ref; do\n"
                    "  [ \"$new\" = 0000000000000000000000000000000000000000 ] && exit 1\n"
                    "done\nexit 0\n")
    hook.chmod(0o755)
    r = _run_args(out, "--apply", "--tests-passed")
    assert r.returncode == 1 and "Traceback" not in r.stderr, r.stdout + r.stderr
    remote_log = subprocess.run(["git", "--git-dir", str(bare), "log", "-1", "--format=%s", "main"],
                                capture_output=True, text=True).stdout
    assert "archive plan(s)" in remote_log  # the merge is pushed
    done = [json.loads(line) for line in (out / ".git/process-tower/reports.jsonl").read_text().splitlines()]
    assert done[-1]["state"] == "done" and done[-1]["note"] == "tokens: not measured"


def test_a_failing_done_report_does_not_end_a_pushed_merge_in_a_traceback(render, tmp_path, monkeypatch):
    """A merged change must not end in a traceback over bookkeeping."""
    import importlib.util
    out = _repo_on_feature(render, tmp_path)
    sys.path.insert(0, str(out / "scripts/process"))
    spec = importlib.util.spec_from_file_location("finish_done", out / "scripts/process/finish.py")
    finish = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(finish)
    import report

    def boom(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(report, "write_report", boom)
    finish._done(out, "feature")  # no exception


def test_issue_tokens_sum_the_policy_transcripts_of_its_worktrees(render, tmp_path):
    """The count is read, never estimated: the policy's `transcripts` glob per dispatched worktree."""
    import importlib.util
    import json
    out = _repo_on_feature(render, tmp_path)
    sys.path.insert(0, str(out / "scripts/process"))
    spec = importlib.util.spec_from_file_location("finish_t", out / "scripts/process/finish.py")
    finish = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(finish)
    assert finish.usage(out, "7-widget") == (7, "tokens: not measured")
    wt = tmp_path / "wt [7]"  # glob characters in a worktree path are literal
    (wt / "t").mkdir(parents=True)
    (wt / "t" / "a.jsonl").write_text('{"usage": {"output_tokens": 40}}\n{"output_tokens": 2}\n')
    (wt / "t" / "b.jsonl").write_text('{"output_tokens": 100}\n')
    records = out / ".git/process-dispatch"
    records.mkdir(parents=True, exist_ok=True)
    (records / "7-widget.json").write_text(json.dumps({"issue": 7, "worktree": str(wt), "phase": "review"}))
    (records / "8-other.json").write_text(json.dumps({"issue": 8, "worktree": str(tmp_path), "phase": "plan"}))
    (out / "docs/process/model-policy.local.json").write_text(json.dumps({"transcripts": "{worktree}/t/*.jsonl"}))
    assert finish.usage(out, "7-widget") == (7, "tokens: 142 output over 2 sessions")
    assert finish.usage(out, "feature") == (None, "tokens: not measured")


def test_apply_red_suite_does_not_merge(render, tmp_path):
    out, _bare = _repo_with_origin(render, tmp_path)
    r = _run_args(out, "--apply", "--tests", "false")
    assert r.returncode == 1
    assert "full suite red" in r.stdout
    assert _git(out, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == "feature"


def test_apply_refuses_when_blocked(render, tmp_path):
    out = _repo_on_feature(render, tmp_path)
    _active_plan(out, "2026-07-04-widget.md", "# Plan\n\ntier: 2\nissue: none\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "feat: widget plan")
    r = _run_args(out, "--apply", "--tests-passed")
    assert r.returncode == 1 and "nothing applied" in r.stdout


def test_tail_names_the_full_suite_before_merge(render, tmp_path):
    out = _repo_on_feature(render, tmp_path)
    r = _run(out)
    assert r.returncode == 0, r.stdout + r.stderr
    fi = r.stdout.index("FULL test suite")
    mi = r.stdout.index("merge:")
    assert fi < mi  # the batch pays completeness before it merges


def _route_hooks(out: Path, seen: Path) -> None:
    """Hooks that log the route marker each git step sees; the pre-push one is the
    merge guard itself, fed the remote refs from stdin as a hook wrapper does."""
    hooks = out / ".git/hooks"
    for name in ("post-checkout", "post-merge"):
        (hooks / name).write_text(
            f'#!/bin/sh\necho "{name} ${{PROCESS_MERGE_ROUTE:-unset}}" >> "{seen}"\n')
        (hooks / name).chmod(0o755)
    (hooks / "pre-push").write_text(
        "#!/bin/sh\ntargets=''\n"
        "while read lref lsha rref rsha; do targets=\"$targets $rref\"; "
        f'echo "push $rref ${{PROCESS_MERGE_ROUTE:-unset}}" >> "{seen}"; done\n'
        f'exec "{sys.executable}" scripts/process/merge_route.py $targets\n')
    (hooks / "pre-push").chmod(0o755)


def test_apply_marks_only_its_own_push_to_main(render, tmp_path):
    # the pre-push guard (merge_route.py) refuses a push to main without a route;
    # finish names it for that one push and strips a marker it inherited
    out, bare = _repo_with_origin(render, tmp_path)
    seen = tmp_path / "seen.log"
    _route_hooks(out, seen)
    env = {k: v for k, v in os.environ.items() if not k.startswith(("PROCESS_", "SKIP"))}
    r = subprocess.run([sys.executable, str(out / "scripts/process/finish.py"), "--apply",
                        "--tests-passed", "."], cwd=out, capture_output=True, text=True,
                       env={**env, "PROCESS_MERGE_ROUTE": "inherited"})
    assert r.returncode == 0, r.stdout + r.stderr
    lines = seen.read_text().splitlines()
    assert "push refs/heads/main finish" in lines
    assert "push refs/heads/feature unset" in lines  # the branch deletion is no merge
    assert not [ln for ln in lines if ln.endswith("inherited")], lines
    assert "post-checkout unset" in lines and "post-merge unset" in lines
    # without finish, the same guard refuses a hand push to main
    _git(out, "commit", "-q", "--allow-empty", "-m", "by hand")
    hand = subprocess.run(["git", "push", "-q", "origin", "main"], cwd=out, capture_output=True,
                          text=True, env=env)
    assert hand.returncode != 0 and "merge_route" in hand.stderr
