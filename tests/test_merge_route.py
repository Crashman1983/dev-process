"""merge_route.py — who may push to main: phase bar, route marker, logged
owner override (observed downstream: a review session reset its branch onto
main and published 16 commits past a `block` verdict). Each test runs the
rendered script as the pre-push hook does."""
import json
import os
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest

MAIN = "refs/heads/main"
BRANCH = "7-work"
_OWN_VARS = ("PROCESS_", "PRE_COMMIT_", "SKIP")


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                          check=True).stdout


def _repo(render, tmp_path: Path) -> Path:
    out = render(tmp_path / "p", {"project_name": "d", "modules": {}})
    _git(out, "init", "-q", "-b", "main")
    _git(out, "config", "user.email", "t@t")
    _git(out, "config", "user.name", "t")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "base")
    _git(out, "checkout", "-q", "-b", BRANCH)
    return out


def _env(extra: dict | None = None) -> dict:
    # the suite may itself run inside a dispatched session: its markers must not leak in
    env = {k: v for k, v in os.environ.items() if not k.startswith(_OWN_VARS)}
    return {**env, **(extra or {})}


def _run(root: Path, *args: str, env: dict | None = None, cwd: Path | None = None):
    return subprocess.run([sys.executable, str(root / "scripts/process/merge_route.py"), *args],
                          cwd=cwd or root, capture_output=True, text=True, env=_env(env))


def _folder(root: Path) -> Path:
    common = Path(_git(root, "rev-parse", "--path-format=absolute", "--git-common-dir").strip())
    folder = common / "process-dispatch"
    folder.mkdir(exist_ok=True)
    return folder


def _write(root: Path, content: object, name: str = f"{BRANCH}.json") -> None:
    (_folder(root) / name).write_text(json.dumps(content), encoding="utf-8")


def _start_of(pid: int) -> str:
    """A process start the way dispatch._proc_start reads it (/proc/<pid>/stat, field 22)."""
    return Path(f"/proc/{pid}/stat").read_text(encoding="utf-8").rsplit(")", 1)[-1].split()[19]


def _live(phase: str = "review", branch: str = BRANCH, pid: int | None = None, **more) -> dict:
    pid = os.getpid() if pid is None else pid  # pytest: an ancestor of the guard
    return {"branch": branch, "phase": phase, "pid": pid, "pid_start": _start_of(pid), **more}


@contextmanager
def _foreign_session():
    """A live process that is NOT an ancestor of the guard — somebody else's session."""
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    try:
        yield proc.pid
    finally:
        proc.kill()
        proc.wait()


def _ledger(root: Path) -> list[str]:
    common = Path(_git(root, "rev-parse", "--path-format=absolute", "--git-common-dir").strip())
    f = common / "process-owner-overrides.log"
    return f.read_text(encoding="utf-8").splitlines() if f.is_file() else []


linux_only = pytest.mark.skipif(not Path("/proc/self/stat").exists(), reason="reads /proc")


# --- plan and review never push to main -----------------------------------------------

@pytest.mark.parametrize("phase", ["review", "plan"])
def test_a_barred_phase_is_refused_on_main_and_named(render, tmp_path, phase):
    r = _run(_repo(render, tmp_path), MAIN, env={"PROCESS_PHASE": phase})
    assert r.returncode == 1 and phase in r.stderr


def test_neither_marker_nor_override_rescues_a_barred_phase(render, tmp_path):
    root = _repo(render, tmp_path)
    marked = _run(root, MAIN, env={"PROCESS_PHASE": "review", "PROCESS_MERGE_ROUTE": "train"})
    overridden = _run(root, MAIN, env={"PROCESS_PHASE": "review",
                                       "PROCESS_OWNER_OVERRIDE": "owner said so"})
    assert marked.returncode == 1 and overridden.returncode == 1
    assert _ledger(root) == []


@linux_only
def test_a_live_record_bars_without_the_env_variable(render, tmp_path):
    root = _repo(render, tmp_path)
    _write(root, _live("review"))
    r = _run(root, MAIN, env={"PROCESS_MERGE_ROUTE": "finish"})
    assert r.returncode == 1 and "review" in r.stderr


def test_a_stale_record_does_not_lock_out_finish(render, tmp_path):
    # review is the last phase before the merge: a record whose session is gone
    # must not refuse the branch's finish.py
    root = _repo(render, tmp_path)
    _write(root, {"branch": BRANCH, "phase": "review", "pid": 2**22 + 1, "pid_start": "1"})
    r = _run(root, MAIN, env={"PROCESS_MERGE_ROUTE": "finish"})
    assert r.returncode == 0, r.stderr


@linux_only
def test_a_foreign_sessions_record_does_not_bar(render, tmp_path):
    # otherwise every running review would stop the train
    root = _repo(render, tmp_path)
    _git(root, "checkout", "-q", "-b", "8-other")
    with _foreign_session() as pid:
        _write(root, _live("review", pid=pid, worktree=str(tmp_path / "elsewhere")))
        r = _run(root, MAIN, env={"PROCESS_MERGE_ROUTE": "finish"})
    assert r.returncode == 0, r.stderr


def test_a_barred_phase_may_push_its_own_branch(render, tmp_path):
    r = _run(_repo(render, tmp_path), f"refs/heads/{BRANCH}", env={"PROCESS_PHASE": "review"})
    assert r.returncode == 0, r.stderr


def test_execute_with_a_marker_passes(render, tmp_path):
    r = _run(_repo(render, tmp_path), MAIN,
             env={"PROCESS_PHASE": "execute", "PROCESS_MERGE_ROUTE": "finish"})
    assert r.returncode == 0, r.stderr


# --- route marker or logged override --------------------------------------------------

def test_no_marker_no_override_is_refused_naming_both_ways(render, tmp_path):
    r = _run(_repo(render, tmp_path), MAIN)
    assert r.returncode == 1
    for way in ("train", "finish", "PROCESS_OWNER_OVERRIDE"):
        assert way in r.stderr, r.stderr


def test_train_and_finish_markers_pass_and_log_nothing(render, tmp_path):
    root = _repo(render, tmp_path)
    for route in ("train", "finish"):
        assert _run(root, MAIN, env={"PROCESS_MERGE_ROUTE": route}).returncode == 0
    assert _ledger(root) == []


def test_an_unknown_marker_does_not_count(render, tmp_path):
    assert _run(_repo(render, tmp_path), MAIN, env={"PROCESS_MERGE_ROUTE": "hand"}).returncode == 1


def test_an_override_with_a_reason_passes_and_leaves_exactly_one_line(render, tmp_path):
    root = _repo(render, tmp_path)
    head = _git(root, "rev-parse", "HEAD").strip()
    r = _run(root, MAIN, env={"PROCESS_OWNER_OVERRIDE": "hotfix\tpast the train"})
    assert r.returncode == 0, r.stderr
    lines = _ledger(root)
    assert len(lines) == 1, lines
    stamp, user, host, branch, sha, kind, reason, targets = lines[0].split("\t")
    assert stamp and user and host
    assert (branch, sha, kind) == (BRANCH, head, "override")
    assert reason == "hotfix past the train"
    assert targets == MAIN


def test_an_override_without_a_reason_is_refused(render, tmp_path):
    root = _repo(render, tmp_path)
    for empty in ("", "   "):
        assert _run(root, MAIN, env={"PROCESS_OWNER_OVERRIDE": empty}).returncode == 1
    assert _ledger(root) == []


def test_an_override_from_a_dispatched_session_is_refused(render, tmp_path):
    root = _repo(render, tmp_path)
    r = _run(root, MAIN, env={"PROCESS_PHASE": "execute", "PROCESS_OWNER_OVERRIDE": "hurry"})
    assert r.returncode == 1 and "dispatched" in r.stderr
    assert _ledger(root) == []


@linux_only
def test_an_override_under_a_live_execute_record_is_refused(render, tmp_path):
    root = _repo(render, tmp_path)
    _write(root, _live("execute"))
    assert _run(root, MAIN, env={"PROCESS_OWNER_OVERRIDE": "hurry"}).returncode == 1
    assert _ledger(root) == []


def test_other_targets_need_no_marker(render, tmp_path):
    root = _repo(render, tmp_path)
    r = _run(root, f"refs/heads/{BRANCH}", "refs/tags/v1")
    assert r.returncode == 0, r.stderr
    assert _ledger(root) == []


def test_no_target_at_all_is_the_soft_side(render, tmp_path):
    # a manual run without targets, as check_review.integration_push reads it
    assert _run(_repo(render, tmp_path)).returncode == 0


@pytest.mark.parametrize("var", ["PROCESS_PUSH_TARGETS", "PRE_COMMIT_REMOTE_BRANCH"])
def test_targets_come_from_the_hook_environment(render, tmp_path, var):
    # the pre-commit hook passes no arguments: the framework names the remote ref
    root = _repo(render, tmp_path)
    assert _run(root, env={var: MAIN}).returncode == 1
    assert _run(root, env={var: MAIN, "PROCESS_MERGE_ROUTE": "train"}).returncode == 0
    assert _run(root, env={var: f"refs/heads/{BRANCH}"}).returncode == 0


@pytest.mark.parametrize("args,env", [
    ((), {"PROCESS_PUSH_TARGETS": f"refs/heads/{BRANCH}", "PRE_COMMIT_REMOTE_BRANCH": MAIN}),
    ((f"refs/heads/{BRANCH}",), {"PRE_COMMIT_REMOTE_BRANCH": MAIN}),
    ((MAIN,), {"PROCESS_PUSH_TARGETS": f"refs/heads/{BRANCH}"}),
], ids=["forged-variable", "argument-and-framework", "argument-and-variable"])
def test_the_targets_are_a_union_so_nothing_hides_main(render, tmp_path, args, env):
    # a forged PROCESS_PUSH_TARGETS once won over pre-commit's own variable
    r = _run(_repo(render, tmp_path), *args, env=env)
    assert r.returncode == 1 and "PROCESS_MERGE_ROUTE" in r.stderr, r.stderr


def test_the_guard_knows_the_phases_dispatch_knows(render, tmp_path):
    root = _repo(render, tmp_path)
    sys.path.insert(0, str(root / "scripts/process"))
    try:
        import importlib.util
        mods = {}
        for name in ("dispatch", "merge_route"):
            spec = importlib.util.spec_from_file_location(f"{name}_phases",
                                                          root / f"scripts/process/{name}.py")
            mods[name] = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mods[name])
    finally:
        sys.path.remove(str(root / "scripts/process"))
    assert tuple(mods["merge_route"].KNOWN_PHASES) == tuple(mods["dispatch"].PHASES)


@pytest.mark.parametrize("phase,refused", [("Review", True), ("PLAN", True), ("deploy", True),
                                           ("Execute", False)])
def test_the_env_phase_is_compared_case_insensitively_and_validated(render, tmp_path, phase,
                                                                     refused):
    r = _run(_repo(render, tmp_path), MAIN,
             env={"PROCESS_PHASE": phase, "PROCESS_MERGE_ROUTE": "train"})
    assert (r.returncode == 1) is refused, r.stderr


def test_a_malformed_ref_line_on_stdin_refuses(render, tmp_path):
    root = _repo(render, tmp_path)
    r = subprocess.run([sys.executable, str(root / "scripts/process/merge_route.py"), "--stdin"],
                       cwd=root, input="refs/heads/main deadbeef\n", capture_output=True,
                       text=True, env=_env({"PROCESS_MERGE_ROUTE": "train"}))
    assert r.returncode == 1 and "not a pre-push ref line" in r.stderr


# --- skipped gates: allowed, never silent ---------------------------------------------

def test_a_bypass_on_main_passes_and_is_logged(render, tmp_path):
    root = _repo(render, tmp_path)
    r = _run(root, "--bypass", "SKIP_PUSH_GATE", MAIN)
    assert r.returncode == 0, r.stderr
    lines = _ledger(root)
    assert len(lines) == 1 and lines[0].split("\t")[5] == "SKIP_PUSH_GATE", lines


def test_skipping_the_gate_hook_is_a_logged_bypass(render, tmp_path):
    # pre-commit's own switch: SKIP=process-gates skips the gate runner, not this guard
    root = _repo(render, tmp_path)
    r = _run(root, env={"PRE_COMMIT_REMOTE_BRANCH": MAIN, "SKIP": "foo,process-gates"})
    assert r.returncode == 0, r.stderr
    assert [line.split("\t")[5] for line in _ledger(root)] == ["SKIP=process-gates"]


def test_a_bypass_does_not_lift_the_phase_bar(render, tmp_path):
    root = _repo(render, tmp_path)
    r = _run(root, "--bypass", "SKIP_PUSH_GATE", MAIN, env={"PROCESS_PHASE": "review"})
    assert r.returncode == 1
    assert _ledger(root) == []


@pytest.mark.parametrize("route", [None, "finish"])
def test_a_bypass_from_a_dispatched_session_is_refused(render, tmp_path, route):
    # the owner's emergency exit is not the agent's: a marker does not rescue it either
    root = _repo(render, tmp_path)
    env = {"PROCESS_PHASE": "execute", **({"PROCESS_MERGE_ROUTE": route} if route else {})}
    r = _run(root, "--bypass", "SKIP_PUSH_GATE", MAIN, env=env)
    assert r.returncode == 1 and "SKIP_PUSH_GATE" in r.stderr and "dispatched" in r.stderr
    assert _ledger(root) == []


@linux_only
def test_a_bypass_under_a_live_execute_record_is_refused(render, tmp_path):
    root = _repo(render, tmp_path)
    _write(root, _live("execute"))
    r = _run(root, "--bypass", "SKIP_PROCESS_GATES", MAIN)
    assert r.returncode == 1 and "SKIP_PROCESS_GATES" in r.stderr
    assert _ledger(root) == []


def test_a_bypass_to_a_branch_logs_nothing(render, tmp_path):
    root = _repo(render, tmp_path)
    assert _run(root, "--bypass", "SKIP_PROCESS_GATES", f"refs/heads/{BRANCH}").returncode == 0
    assert _ledger(root) == []


# --- the phase belongs to the session, not to the branch name -------------------------

@linux_only
@pytest.mark.parametrize("move", [["checkout", "-q", "-b", "8-renamed"],
                                  ["checkout", "-q", "--detach", "HEAD"]],
                         ids=["branch-switch", "detached-head"])
def test_leaving_the_branch_does_not_escape_the_bar(render, tmp_path, move):
    root = _repo(render, tmp_path)
    with _foreign_session() as pid:
        _write(root, _live("review", pid=pid, worktree=str(root)))
        _git(root, *move)
        r = _run(root, MAIN, env={"PROCESS_MERGE_ROUTE": "finish"})
    assert r.returncode == 1 and "review" in r.stderr, r.stderr


@linux_only
def test_a_second_worktree_of_the_review_session_does_not_escape(render, tmp_path):
    # other path, other branch, no env — only the process tree gives it away
    root = _repo(render, tmp_path)
    _write(root, _live("review", worktree=str(root)))
    second = tmp_path / "second"
    _git(root, "worktree", "add", "-q", "-b", "8-second", str(second))
    r = _run(root, MAIN, env={"PROCESS_MERGE_ROUTE": "finish"}, cwd=second)
    assert r.returncode == 1 and "review" in r.stderr, r.stderr


@linux_only
def test_a_second_worktree_of_a_foreign_session_is_not_barred(render, tmp_path):
    root = _repo(render, tmp_path)
    second = tmp_path / "second"
    _git(root, "worktree", "add", "-q", "-b", "8-second", str(second))
    with _foreign_session() as pid:
        _write(root, _live("review", pid=pid, worktree=str(root)))
        r = _run(root, MAIN, env={"PROCESS_MERGE_ROUTE": "finish"}, cwd=second)
    assert r.returncode == 0, r.stderr


@linux_only
@pytest.mark.parametrize("declared", ["execute", "anything"])
def test_the_env_does_not_paint_over_a_live_review_record(render, tmp_path, declared):
    root = _repo(render, tmp_path)
    _write(root, _live("review"))
    r = _run(root, MAIN, env={"PROCESS_PHASE": declared, "PROCESS_MERGE_ROUTE": "train"})
    assert r.returncode == 1, r.stderr


# --- "cannot tell" is never "no session" ----------------------------------------------

def test_a_missing_dispatch_import_refuses_main(render, tmp_path):
    root = _repo(render, tmp_path)
    (root / "scripts/process/report.py").unlink()
    r = _run(root, MAIN, env={"PROCESS_MERGE_ROUTE": "finish"})
    assert r.returncode == 1 and "phase" in r.stderr
    assert _run(root, f"refs/heads/{BRANCH}").returncode == 0


def test_a_failing_branch_lookup_refuses_main(render, tmp_path):
    root = _repo(render, tmp_path)
    shim = tmp_path / "shim"
    shim.mkdir()
    real = subprocess.run(["which", "git"], check=True, capture_output=True,
                          text=True).stdout.strip()
    (shim / "git").write_text(f'#!/bin/sh\ncase "$*" in *"rev-parse --abbrev-ref HEAD"*) '
                              f'exit 128 ;; esac\nexec {real} "$@"\n', encoding="utf-8")
    (shim / "git").chmod(0o755)
    path = os.pathsep.join([str(shim), os.environ.get("PATH", os.defpath)])
    r = _run(root, MAIN, env={"PROCESS_MERGE_ROUTE": "finish", "PATH": path})
    assert r.returncode == 1 and "phase" in r.stderr


def test_a_truncated_record_refuses_main_even_with_a_marker_or_a_bypass(render, tmp_path):
    root = _repo(render, tmp_path)
    (_folder(root) / f"{BRANCH}.json").write_text('{"branch": "7-work", "phase": "rev')
    marked = _run(root, MAIN, env={"PROCESS_MERGE_ROUTE": "finish"})
    bypassed = _run(root, "--bypass", "SKIP_PUSH_GATE", MAIN)
    for r in (marked, bypassed):
        assert r.returncode == 1 and f"{BRANCH}.json" in r.stderr, r.stderr
    assert _ledger(root) == []
    assert _run(root, f"refs/heads/{BRANCH}").returncode == 0  # only main is the merge


@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0, reason="root reads any directory")
def test_an_unreadable_dispatch_directory_refuses_main(render, tmp_path):
    root = _repo(render, tmp_path)
    folder = _folder(root)
    folder.chmod(0o100)
    try:
        r = _run(root, MAIN, env={"PROCESS_MERGE_ROUTE": "finish"})
        branch = _run(root, f"refs/heads/{BRANCH}")
    finally:
        folder.chmod(0o755)
    assert r.returncode == 1 and "process-dispatch" in r.stderr, r.stderr
    assert branch.returncode == 0


def test_a_dispatch_directory_that_is_no_directory_refuses_main(render, tmp_path):
    # the same "cannot list" as an unreadable directory, reproducible as root too
    root = _repo(render, tmp_path)
    common = Path(_git(root, "rev-parse", "--path-format=absolute", "--git-common-dir").strip())
    (common / "process-dispatch").write_text("not a directory")
    r = _run(root, MAIN, env={"PROCESS_MERGE_ROUTE": "finish"})
    assert r.returncode == 1 and "process-dispatch" in r.stderr, r.stderr


@pytest.mark.parametrize("missing", ["branch", "phase", "pid", "pid_start"])
def test_a_record_missing_a_field_refuses_instead_of_counting_as_no_session(
        render, tmp_path, missing):
    root = _repo(render, tmp_path)
    record = {"branch": BRANCH, "phase": "review", "pid": os.getpid(), "pid_start": "x"}
    del record[missing]
    _write(root, record)
    r = _run(root, MAIN, env={"PROCESS_MERGE_ROUTE": "finish"})
    assert r.returncode == 1 and f"{BRANCH}.json" in r.stderr, r.stderr


@pytest.mark.parametrize("record", [
    {}, {"branch": BRANCH, "phase": "deploy", "pid": 1, "pid_start": "1"}, {"branch": ""},
    {"branch": BRANCH, "phase": "review", "pid": "12", "pid_start": 7},
    {"branch": BRANCH, "phase": "review", "pid": 0, "pid_start": "1"},
    {"branch": BRANCH, "phase": "review", "pid": -1, "pid_start": "1"},
    {"branch": BRANCH, "phase": "review", "pid": 1, "pid_start": ""},
], ids=["empty", "unknown-phase", "empty-branch", "mistyped-anchor", "pid-zero",
        "pid-negative", "empty-start"])
def test_a_record_with_a_bad_schema_refuses_the_bypass_too(render, tmp_path, record):
    root = _repo(render, tmp_path)
    _write(root, record)
    r = _run(root, "--bypass", "SKIP_PUSH_GATE", MAIN)
    assert r.returncode == 1 and f"{BRANCH}.json" in r.stderr, r.stderr
    assert _ledger(root) == []


def test_the_legacy_queue_list_and_the_issue_map_are_no_records(render, tmp_path):
    root = _repo(render, tmp_path)
    _write(root, [], name="queue.json")
    _write(root, {"7": BRANCH}, name="issues.json")
    r = _run(root, MAIN, env={"PROCESS_MERGE_ROUTE": "finish"})
    assert r.returncode == 0, r.stderr


def test_a_queue_json_object_is_checked_like_a_record(render, tmp_path):
    # a branch named `queue` writes queue.json as its record — the name exempts nothing
    root = _repo(render, tmp_path)
    _write(root, {"branch": "queue"}, name="queue.json")
    r = _run(root, MAIN, env={"PROCESS_MERGE_ROUTE": "finish"})
    assert r.returncode == 1 and "queue.json" in r.stderr, r.stderr


def test_remote_and_stale_records_stay_valid(render, tmp_path):
    root = _repo(render, tmp_path)
    _write(root, {"branch": "8-other", "phase": "review", "remote": True}, "a.json")
    _write(root, {"branch": BRANCH, "phase": "review", "pid": 2**22 + 1, "pid_start": "1"},
           "b.json")
    assert _run(root, MAIN, env={"PROCESS_MERGE_ROUTE": "finish"}).returncode == 0


def test_a_remote_review_record_of_this_branch_bars_and_names_the_way_out(render, tmp_path):
    # liveness on another host cannot be seen here: "unknown" is not "dead"
    root = _repo(render, tmp_path)
    _write(root, {"branch": BRANCH, "phase": "review", "remote": True})
    r = _run(root, MAIN, env={"PROCESS_MERGE_ROUTE": "finish"})
    assert r.returncode == 1 and "review" in r.stderr
    assert "dispatch.py stop" in r.stderr


def test_a_remote_execute_record_lets_finish_through(render, tmp_path):
    root = _repo(render, tmp_path)
    _write(root, {"branch": BRANCH, "phase": "execute", "remote": True})
    assert _run(root, MAIN, env={"PROCESS_MERGE_ROUTE": "finish"}).returncode == 0


# --- the words around it --------------------------------------------------------------

def test_the_review_command_pushes_only_its_own_branch(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "harnesses": {"copilot": True}})
    for rel in (".claude/commands/review.md", ".github/prompts/review.prompt.md"):
        text = " ".join((out / rel).read_text(encoding="utf-8").split())
        assert "Push only your own branch, never main" in text, rel


def test_the_train_doc_owns_the_merge_route(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    text = " ".join((out / "docs/process/train.md").read_text(encoding="utf-8").split())
    for term in ("PROCESS_MERGE_ROUTE=train|finish", 'PROCESS_OWNER_OVERRIDE="<reason>"',
                 "process-owner-overrides.log", "SKIP=process-gates", "--standing-block",
                 "Plan and review sessions never push to main"):
        assert term in text, term
