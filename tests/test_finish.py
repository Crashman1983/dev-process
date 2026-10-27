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
    _git(out, "remote", "add", "origin", str(tmp_path / "origin.git"))  # the push tail (#330)
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


def test_speckit_plan_in_flight_without_review_blocks(render, tmp_path):
    """#266: a Spec Kit plan this branch carries owes its review at the merge, like an
    active plan — unticked tasks no longer let it through."""
    out = _repo_on_feature(render, tmp_path)
    _spec_dir(out, "009-widget", tier=3, ticked=False)
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "feat: widget in flight")
    r = _run(out)
    assert r.returncode == 1 and "specs/009-widget/plan.md" in r.stdout, r.stdout + r.stderr


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
    # the same reader gives input and cache shares apart; a field the harness never
    # wrote stays absent (not measured), never a zero
    (wt / "t" / "a.jsonl").write_text('{"usage": {"input_tokens": 5, "cache_read_input_tokens": 900, '
                                      '"cache_creation": {"ephemeral_5m_input_tokens": 77}, '
                                      '"output_tokens": 40}}\n')
    import dispatch
    totals, sessions = dispatch.issue_token_usage(out, 7)
    assert sessions == 2
    assert totals == {"input_tokens": 5, "cache_read_input_tokens": 900, "output_tokens": 140}
    assert dispatch.issue_token_usage(out, 9) is None


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


def _finish_module(out):
    import importlib.util
    sys.path.insert(0, str(out / "scripts/process"))
    spec = importlib.util.spec_from_file_location("finish_argv", out / "scripts/process/finish.py")
    finish = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(finish)
    return finish


def test_tests_run_without_a_shell(render, tmp_path):
    """#199: `--tests CMD` is argv, split once — no `shell=True` on argv text."""
    finish = _finish_module(_repo_on_feature(render, tmp_path))
    assert finish.tests_argv("make test") == (["make", "test"], {})
    assert finish.tests_argv("uv run pytest -k 'a or b|c'") == (["uv", "run", "pytest", "-k", "a or b|c"], {})
    assert finish.tests_argv("make test # note") == (["make", "test", "#", "note"], {})
    assert "shell=True" not in (Path(finish.__file__)).read_text()


@pytest.mark.parametrize("cmd", ["make a && make b", "make test | tee log", "make test > log",
                                 "make a; make b", "pytest 'unclosed", "   ", "CI=1", "A=1 B=2"])
def test_a_tests_command_that_needs_a_shell_is_refused(render, tmp_path, cmd):
    finish = _finish_module(_repo_on_feature(render, tmp_path))
    assert isinstance(finish.tests_argv(cmd), str)


def test_apply_refuses_a_shell_chain_before_merging(render, tmp_path):
    out, _bare = _repo_with_origin(render, tmp_path)
    r = _run_args(out, "--apply", "--tests", "true && true")
    assert r.returncode == 1 and "shell operator '&&'" in r.stdout, r.stdout


def test_tests_keep_an_env_prefix_and_refuse_a_newline(render, tmp_path):
    finish = _finish_module(_repo_on_feature(render, tmp_path))
    assert finish.tests_argv("FOO=1 make test") == (["make", "test"], {"FOO": "1"})
    assert "newline" in finish.tests_argv("make test\nmake deploy")
    assert "shell operator" in finish.tests_argv("make test # && make deploy")  # `#` hides nothing


@pytest.mark.parametrize("cmd", ["no-such-command-199", "FOO=1 no-such-command-199"])
def test_apply_with_a_missing_tests_command_does_not_merge(render, tmp_path, cmd):
    out, _bare = _repo_with_origin(render, tmp_path)
    r = _run_args(out, "--apply", "--tests", cmd)
    assert r.returncode == 1 and "cannot run" in r.stdout and "Traceback" not in r.stderr, (r.stdout, r.stderr)


def test_apply_with_an_assignment_alone_applies_nothing(render, tmp_path):
    """Refute #199: `CI=1` alone ran `env`, exit 0, and merged."""
    out, _bare = _repo_with_origin(render, tmp_path)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=out, capture_output=True, text=True).stdout
    r = _run_args(out, "--apply", "--tests", "CI=1")
    assert r.returncode == 1 and "names no command" in r.stdout and "nothing applied" in r.stdout, r.stdout
    assert subprocess.run(["git", "rev-parse", "HEAD"], cwd=out, capture_output=True, text=True).stdout == head


def test_apply_runs_the_tests_with_their_assignments(render, tmp_path):
    out, _bare = _repo_with_origin(render, tmp_path)
    check = f"FOO=199 {sys.executable} -c 'import os, sys; sys.exit(os.environ.get(\"FOO\") != \"199\")'"
    r = _run_args(out, "--apply", "--tests", check)
    assert r.returncode == 0 and "full suite red" not in r.stdout, r.stdout


def _merge_certificate(out: Path, evidence: str):
    import json
    code = ("import sys, json; sys.path.insert(0, 'scripts/process'); import certificate; "
            "from pathlib import Path; "
            f"print(json.dumps(certificate.find(Path('.'), ('merge',), {{'merge': {evidence!r}}})))")
    r = subprocess.run([sys.executable, "-c", code], cwd=out, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


@pytest.mark.parametrize("configured", [True, False])
def test_apply_with_the_merge_suite_certifies_the_merged_tree(render, tmp_path, configured):
    """#206: the push to main then runs no suite again; any other command certifies nothing."""
    import json
    out, _bare = _repo_with_origin(render, tmp_path)
    (out / "docs/process/testing.local.json").write_text(
        json.dumps({"merge_suite": "true" if configured else "make suite"}))
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "test config")
    r = _run_args(out, "--apply", "--tests", "true")
    assert r.returncode == 0, r.stdout + r.stderr
    hit = _merge_certificate(out, "true")
    if configured:
        assert "merge certificate written" in r.stdout and hit and hit["writer"] == "finish --tests"
    else:
        assert hit is None and "merge certificate" not in r.stdout


def test_tests_passed_is_refused_while_a_merge_suite_is_set(render, tmp_path):
    """#255: with a configured merge_suite the claim certifies nothing and the push would
    run the suite again — `--tests` is the route, so the claim is refused before anything
    is applied."""
    import json
    out, _bare = _repo_with_origin(render, tmp_path)
    (out / "docs/process/testing.local.json").write_text(json.dumps({"merge_suite": "true"}))
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "test config")
    head = _git(out, "rev-parse", "HEAD").stdout
    r = _run_args(out, "--apply", "--tests-passed")
    assert r.returncode == 2 and "--apply --tests" in r.stderr, r.stdout + r.stderr
    assert _git(out, "rev-parse", "HEAD").stdout == head
    assert _merge_certificate(out, "true") is None


def test_tests_passed_without_a_merge_suite_stays_a_claim(render, tmp_path):
    out, _bare = _repo_with_origin(render, tmp_path)
    r = _run_args(out, "--apply", "--tests-passed")
    assert r.returncode == 0, r.stdout + r.stderr
    assert _merge_certificate(out, "true") is None


def test_bare_tests_runs_the_merge_suite_and_certifies(render, tmp_path):
    """#255: `--tests` alone is the project's merge_suite."""
    import json
    out, _bare = _repo_with_origin(render, tmp_path)
    (out / "docs/process/testing.local.json").write_text(json.dumps({"merge_suite": "true"}))
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "test config")
    r = _run_args(out, "--apply", "--tests")
    assert r.returncode == 0, r.stdout + r.stderr
    hit = _merge_certificate(out, "true")
    assert hit and hit["writer"] == "finish --tests", r.stdout


def test_bare_tests_without_a_merge_suite_names_the_way_out(render, tmp_path):
    out, _bare = _repo_with_origin(render, tmp_path)
    r = _run_args(out, "--apply", "--tests")
    assert r.returncode == 2 and "--tests CMD" in r.stderr, r.stdout + r.stderr


def _finish(root, *args):
    """finish.py with exactly these arguments — no root appended."""
    return subprocess.run([sys.executable, str(root / "scripts/process/finish.py"), *args],
                          cwd=root, capture_output=True, text=True)


def test_tests_write_no_certificate_without_a_remote(render, tmp_path):
    """#330: the merge certificate serves the pre-push only, and a local merge pushes nothing."""
    import json
    out = _repo_without_remote(render, tmp_path)
    (out / "docs/process/testing.local.json").write_text(json.dumps({"merge_suite": "true"}))
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "test config")
    r = _run_args(out, "--apply", "--tests")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "merge certificate" not in r.stdout and _merge_certificate(out, "true") is None, r.stdout
    assert "locally (the repository has no remote)" in r.stdout


def test_bare_tests_is_read_in_every_argument_order(render, tmp_path):
    # refute v2.75 r2: only `--tests .` was tested; a bare `--tests`, `--tests --apply` and
    # `--tests ''` take other branches, and a bare name is a command even beside a folder
    import json
    out, _bare = _repo_with_origin(render, tmp_path)
    (out / "docs/process/testing.local.json").write_text(json.dumps({"merge_suite": "true"}))
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "test config")
    r = _finish(out, "--tests", "")
    assert r.returncode == 2 and "names no command" in r.stderr, r.stderr
    r = _finish(out, "--tests", "--apply")
    assert r.returncode == 0 and "merge certificate written" in r.stdout, r.stdout + r.stderr


def test_a_command_named_like_a_folder_is_the_command(render, tmp_path):
    import json
    out, _bare = _repo_with_origin(render, tmp_path)
    (out / "docs/process/testing.local.json").write_text(json.dumps({"merge_suite": "false"}))
    (out / "true").mkdir()
    (out / "true/.keep").write_text("")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "test config and a folder named true")
    r = _finish(out, "--apply", "--tests", "true")  # runs `true`, not the red merge_suite
    assert r.returncode == 0 and "full suite red" not in r.stdout, r.stdout + r.stderr


def test_a_broken_testing_file_is_named_not_mistaken_for_no_suite(render, tmp_path):
    out, _bare = _repo_with_origin(render, tmp_path)
    (out / "docs/process/testing.local.json").write_text('{"merge_suite": "true", "bogus": 1}')
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "broken test config")
    for flag in ("--tests", "--tests-passed"):
        r = _run_args(out, "--apply", flag)
        assert r.returncode == 2 and "testing.local.json cannot be read" in r.stderr, (flag, r.stderr)


def test_the_stop_names_the_route_the_merge_suite_takes(render, tmp_path):
    import json
    out, _bare = _repo_with_origin(render, tmp_path)
    (out / "docs/process/testing.local.json").write_text(json.dumps({"merge_suite": "true"}))
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "test config")
    r = _run_args(out, "--apply")
    assert r.returncode == 0 and "re-run with `--apply --tests`" in r.stdout, r.stdout
    assert "--tests-passed" not in r.stdout


# --- #330: finish in a repository without any remote --------------------------

def _repo_without_remote(render, tmp_path):
    """`_repo_with_origin` without the origin: a tier-1 plan and a payload on `feature`."""
    out = _repo_on_feature(render, tmp_path)
    _active_plan(out, "2026-09-07-tiny.md", "# Plan\n\ntier: 1\n")
    (out / "payload.txt").write_text("done\n", encoding="utf-8")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "feat: tiny")
    return out


def _main_checkout_with_feature_worktree(render, tmp_path):
    """main stays checked out in the main checkout; `feature` rides a worktree."""
    out = render(tmp_path / "main", {"project_name": "demo"})
    _git(out, "init", "-q", "-b", "main")
    _git(out, "config", "user.email", "t@example.com")
    _git(out, "config", "user.name", "Test")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "base")
    wt = tmp_path / "wt-feature"
    _git(out, "worktree", "add", "-q", "-b", "feature", str(wt), "main")
    return out, wt


def _common_dir(out: Path) -> Path:
    common = Path(_git(out, "rev-parse", "--git-common-dir").stdout.strip())
    return common if common.is_absolute() else out / common


def _failing_pre_push(out: Path, seen: Path) -> None:
    hook = _common_dir(out) / "hooks/pre-push"
    hook.write_text(f'#!/bin/sh\necho ran >> "{seen}"\nexit 1\n')
    hook.chmod(0o755)


def _reports(out: Path) -> list[dict]:
    import json
    ledger = _common_dir(out) / "process-tower/reports.jsonl"
    return [json.loads(line) for line in ledger.read_text().splitlines()] if ledger.is_file() else []


def _has_branch(out: Path, name: str) -> bool:
    return subprocess.run(["git", "rev-parse", "--verify", "-q", f"refs/heads/{name}"],
                          cwd=out, capture_output=True).returncode == 0


def test_apply_without_a_remote_merges_locally_and_deletes_the_branch(render, tmp_path):
    out = _repo_without_remote(render, tmp_path)
    seen = tmp_path / "pre-push.log"
    _failing_pre_push(out, seen)
    # a leftover tracking ref the gates never anchor on blocks nothing
    _git(out, "update-ref", "refs/remotes/old/feature", "HEAD")
    r = _run_args(out, "--apply", "--tests", "true")  # without a remote a claim is refused
    assert r.returncode == 0, r.stdout + r.stderr
    assert "merged feature into main locally (the repository has no remote)" in r.stdout, r.stdout
    assert _git(out, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == "main"
    assert "archive plan(s)" in _git(out, "log", "-1", "--format=%s", "main").stdout
    assert not _has_branch(out, "feature")  # the merged branch is deleted
    assert not seen.exists()  # nothing pushed: the pre-push never ran
    assert "merge certificate" not in r.stdout and _merge_certificate(out, "true") is None
    assert _reports(out)[-1]["state"] == "done"


def test_check_without_a_remote_prints_the_local_tail(render, tmp_path):
    out = _repo_without_remote(render, tmp_path)
    _git(out, "checkout", "-q", "main")
    (out / "other.txt").write_text("main moved\n", encoding="utf-8")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "feat: main moved")
    _git(out, "checkout", "-q", "feature")
    r = _run(out)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "git push" not in r.stdout and "git fetch" not in r.stdout, r.stdout
    assert "git rebase main" in r.stdout
    assert "git checkout main && git merge --ff-only feature && git branch -d feature" in r.stdout


def test_a_local_main_ahead_of_the_branch_is_rebased_in(render, tmp_path):
    out = _repo_without_remote(render, tmp_path)
    _git(out, "checkout", "-q", "main")
    (out / "other.txt").write_text("main moved\n", encoding="utf-8")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "feat: main moved")
    moved = _git(out, "rev-parse", "HEAD").stdout.strip()
    _git(out, "checkout", "-q", "feature")
    r = _run_args(out, "--apply", "--tests", "true")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "finish: rebased" in r.stdout
    assert subprocess.run(["git", "merge-base", "--is-ancestor", moved, "main"], cwd=out).returncode == 0
    assert (out / "payload.txt").is_file() and (out / "other.txt").is_file()


@pytest.mark.parametrize("elsewhere", [False, True])
def test_a_red_merge_gate_stops_the_local_merge(render, tmp_path, elsewhere):
    """The gates run as the push to main would run them — here no push runs them."""
    if elsewhere:
        _main_checkout, out = _main_checkout_with_feature_worktree(render, tmp_path)
    else:
        out = _repo_on_feature(render, tmp_path)
    _active_plan(out, "2026-07-04-widget.md",
                 "# Plan\n\ntier: 2\nissue: none\n\n- [ ] T1 the task still open\n")
    _journal(out, "REVIEW work=widget tier=2 reviewer=fresh model=same "
                  "independence=bundle,non-implementing verdict=pass round=1")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "feat: widget with pass")
    main_before = _git(out, "rev-parse", "main").stdout
    r = _run_args(out, "--apply", "--tests", "true")
    assert r.returncode == 1, r.stdout + r.stderr
    assert "open task at the merge" in r.stdout, r.stdout
    assert _git(out, "rev-parse", "main").stdout == main_before  # nothing merged
    assert _git(out, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == "feature"
    assert not [e for e in _reports(out) if e["state"] == "done"]


def test_without_a_remote_the_checkout_holding_main_is_advanced(render, tmp_path):
    main_checkout, wt = _main_checkout_with_feature_worktree(render, tmp_path)
    (wt / "payload.txt").write_text("done\n", encoding="utf-8")
    _git(wt, "add", "-A")
    _git(wt, "commit", "-q", "-m", "feat: payload")
    r = _run_args(wt, "--apply", "--tests", "true")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "locally (the repository has no remote)" in r.stdout
    assert _git(main_checkout, "rev-parse", "HEAD").stdout == _git(wt, "rev-parse", "HEAD").stdout
    assert (main_checkout / "payload.txt").is_file()  # files and ref moved together
    assert _git(wt, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == "feature"  # kept
    assert "git branch -d feature" in r.stdout, r.stdout
    assert _reports(wt)[-1]["state"] == "done"


def test_a_refused_fast_forward_in_the_checkout_holding_main_merges_nothing(render, tmp_path):
    main_checkout, wt = _main_checkout_with_feature_worktree(render, tmp_path)
    (wt / "payload.txt").write_text("done\n", encoding="utf-8")
    _git(wt, "add", "-A")
    _git(wt, "commit", "-q", "-m", "feat: payload")
    (main_checkout / "payload.txt").write_text("in the way\n", encoding="utf-8")  # untracked there
    main_before = _git(main_checkout, "rev-parse", "HEAD").stdout
    r = _run_args(wt, "--apply", "--tests", "true")
    assert r.returncode == 1, r.stdout + r.stderr
    assert _git(main_checkout, "rev-parse", "HEAD").stdout == main_before
    assert "merged feature" not in r.stdout
    assert not [e for e in _reports(wt) if e["state"] == "done"]


def test_a_stale_tracking_ref_without_a_remote_is_refused(render, tmp_path):
    """Without a remote a left-over `origin/main` would anchor the gates on a stale base."""
    out = _repo_without_remote(render, tmp_path)
    _git(out, "update-ref", "refs/remotes/origin/main", "main")
    main_before = _git(out, "rev-parse", "main").stdout
    r = _run(out)
    assert r.returncode == 1 and "git branch -r -d origin/main" in r.stdout, r.stdout
    r = _run_args(out, "--apply", "--tests-passed")
    assert r.returncode == 1 and "nothing applied" in r.stdout, r.stdout
    assert "git branch -r -d origin/main" in r.stdout
    assert _git(out, "rev-parse", "main").stdout == main_before
    assert _git(out, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == "feature"


def test_a_refused_push_with_a_remote_keeps_the_branch(render, tmp_path):
    out, bare = _repo_with_origin(render, tmp_path)
    hook = bare / "hooks/pre-receive"
    hook.write_text("#!/bin/sh\nwhile read old new ref; do\n"
                    "  [ \"$ref\" = refs/heads/main ] && exit 1\n"
                    "done\nexit 0\n")
    hook.chmod(0o755)
    r = _run_args(out, "--apply", "--tests-passed")
    assert r.returncode == 1, r.stdout + r.stderr
    assert _has_branch(out, "feature")
    assert "no remote" not in r.stdout


def test_a_repository_with_another_remote_stays_on_the_push_path(render, tmp_path):
    """Only `upstream`: no silent local merge — the push to origin fails as today."""
    out = _repo_without_remote(render, tmp_path)
    bare = tmp_path / "upstream.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    _git(out, "remote", "add", "upstream", str(bare))
    r = _run_args(out, "--apply", "--tests-passed")
    assert r.returncode == 1, r.stdout + r.stderr
    assert "no remote" not in r.stdout
    assert _has_branch(out, "feature")


def test_tests_passed_without_a_remote_is_refused_before_anything_merges(render, tmp_path):
    """Fix round 1: without a remote no pre-push runs the suite, so the claim is never checked
    — a stack whose full suite is red merged on `--tests-passed`. `--tests <command>` runs it."""
    out = _repo_without_remote(render, tmp_path)
    (out / "suite.sh").write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")  # the red full suite
    (out / "suite.sh").chmod(0o755)
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "test: a red suite")
    head, main_before = _git(out, "rev-parse", "HEAD").stdout, _git(out, "rev-parse", "main").stdout
    r = _run_args(out, "--apply", "--tests-passed")
    assert r.returncode == 1, r.stdout + r.stderr
    assert "without a remote no pre-push runs the suite: pass --tests <command>" in r.stdout, r.stdout
    assert "nothing applied" in r.stdout
    assert _git(out, "rev-parse", "HEAD").stdout == head  # not even the archive commit
    assert _git(out, "rev-parse", "main").stdout == main_before
    assert _git(out, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == "feature"
    assert not [e for e in _reports(out) if e["state"] == "done"]
    r = _run_args(out, "--apply", "--tests", "./suite.sh")
    assert r.returncode == 1 and "full suite red — not merging" in r.stdout, r.stdout + r.stderr
    assert _git(out, "rev-parse", "main").stdout == main_before


def test_an_unreadable_tracking_ref_list_without_a_remote_is_a_blocker(render, tmp_path):
    """Fix round 1: a failing `git for-each-ref` read as "no tracking refs" — never "none"."""
    import shutil
    out = _repo_without_remote(render, tmp_path / "work")
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "git").write_text(
        "#!/bin/sh\ncase \"$*\" in *for-each-ref*refs/remotes/*) "
        "echo 'fatal: bad ref store' >&2; exit 128;; esac\n"
        f'exec "{shutil.which("git")}" "$@"\n', encoding="utf-8")
    (bindir / "git").chmod(0o755)
    env = {**os.environ, "PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}"}
    main_before = _git(out, "rev-parse", "main").stdout
    for args in ((), ("--apply", "--tests", "true")):
        r = subprocess.run([sys.executable, str(out / "scripts/process/finish.py"), *args, "."],
                           cwd=out, capture_output=True, text=True, env=env)
        assert r.returncode == 1, (args, r.stdout + r.stderr)
        assert "could not list remote-tracking refs" in r.stdout, (args, r.stdout)
    assert _git(out, "rev-parse", "main").stdout == main_before
