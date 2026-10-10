"""The pre-push frame (#206): one sequence for every push — guard, gates,
selected tests, stamp. Real pushes to a bare remote through the installed
guard (`merge_route.py --stdin` hands the push to `pre_push.py`).

A probe gate (`gates.local.json`, `exec`) and a probe test runner append to
the file named by PROBE: `g` per gate run, `t <paths>` per selected run,
`m` per merge suite run.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

PROBE_GATE = {"probe": {"module": None, "exec": [
    sys.executable, "-c", "import os; open(os.environ['PROBE'], 'a').write('g\\n')"]}}
STACK = {
    "paths": ["app/"],
    "runner": [sys.executable, "-c",
               "import os, sys; open(os.environ['PROBE'], 'a').write('t ' + ' '.join(sys.argv[1:]) + '\\n')",
               "{paths}"],
    "tests": ["app_tests/test_*.py"],
    "map": [{"from": "app/*.py", "to": ["app_tests"]}],
    "unmapped": "skip",
}
MERGE_SUITE = "echo m >> \"$PROBE\""


def _env(tmp_path: Path, extra: dict | None = None) -> dict:
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("PROCESS_", "PRE_COMMIT", "SKIP", "GIT_"))}
    return {**env, "PROBE": str(tmp_path / "probe"), "PROCESS_LANE_DIR": str(tmp_path / "lanes"),
            "PYTHONDONTWRITEBYTECODE": "1", "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "commit.gpgsign", "GIT_CONFIG_VALUE_0": "false", **(extra or {})}


def _git(root: Path, tmp_path: Path, *args: str, env: dict | None = None, check: bool = True):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                          env=_env(tmp_path, env), check=check)


def _write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


@pytest.fixture
def project(render, tmp_path):
    out = render(tmp_path / "work", {"project_name": "d", "modules": {"git_hooks": True}})
    bare = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True)
    _write(out, "docs/process/gates.local.json", json.dumps(PROBE_GATE))
    _write(out, "docs/process/testing.local.json",
           json.dumps({"merge_suite": MERGE_SUITE, "stacks": {"app": STACK}}))
    _write(out, "app/code.py", "x = 1\n")
    _write(out, "app_tests/test_code.py", "def test_x(): pass\n")
    git = lambda *a, **k: _git(out, tmp_path, *a, **k)  # noqa: E731
    git("init", "-q", "-b", "main")
    git("config", "user.email", "t@t")
    git("config", "user.name", "t")
    git("add", "-A")
    git("commit", "-q", "-m", "base")
    git("remote", "add", "origin", str(bare))
    git("push", "-q", "--no-verify", "origin", "main")
    git("checkout", "-q", "-b", "feature")
    _write(out, "app/code.py", "x = 2\n")
    git("commit", "-qam", "feat: code")
    r = subprocess.run([sys.executable, "scripts/process/install_hooks.py"], cwd=out,
                       capture_output=True, text=True, env=_env(tmp_path))
    assert r.returncode == 0, r.stderr
    return out, bare, git


def _push(git, *args: str, env: dict | None = None):
    return git("push", *args, env=env, check=False)


def _probe(tmp_path: Path) -> list[str]:
    p = tmp_path / "probe"
    lines = p.read_text().splitlines() if p.exists() else []
    p.unlink(missing_ok=True)
    return lines


def _remote(bare: Path, ref: str) -> str:
    return subprocess.run(["git", "--git-dir", str(bare), "rev-parse", "--verify", "-q", ref],
                          capture_output=True, text=True).stdout.strip()


def test_a_branch_push_runs_gates_and_the_selected_tests_and_a_repeat_runs_nothing(project, tmp_path):
    out, bare, git = project
    r = _push(git, "origin", "feature")
    assert r.returncode == 0, r.stderr
    assert _probe(tmp_path) == ["g", "t app_tests"]
    r = _push(git, "origin", "feature:refs/heads/copy")
    assert r.returncode == 0 and "passed this push before" in r.stderr, r.stderr
    assert _probe(tmp_path) == []


def test_a_bookkeeping_commit_on_a_green_tree_runs_the_gates_only(project, tmp_path):
    out, bare, git = project
    assert _push(git, "origin", "feature").returncode == 0
    _probe(tmp_path)
    _write(out, ".process-work/journal/2026-10-10.md", "note\n")
    git("add", "-A")
    git("commit", "-qm", "journal")
    r = _push(git, "origin", "feature")
    assert r.returncode == 0 and "gates only" in r.stderr, r.stderr
    assert _probe(tmp_path) == ["g"]


def test_a_tag_push_is_judged_by_the_guard_alone(project, tmp_path):
    out, bare, git = project
    git("tag", "v1")
    r = _push(git, "origin", "v1")
    assert r.returncode == 0, r.stderr
    assert _probe(tmp_path) == []


def test_a_pushed_commit_other_than_head_is_refused(project, tmp_path):
    out, bare, git = project
    r = _push(git, "origin", "feature~1:refs/heads/old")
    assert r.returncode != 0 and "this checkout is at" in r.stderr, r.stderr
    assert not _remote(bare, "old") and _probe(tmp_path) == []


def test_a_red_selected_test_refuses_the_push(project, tmp_path):
    out, bare, git = project
    cfg = {"stacks": {"app": {**STACK, "runner": [sys.executable, "-c", "raise SystemExit(1)", "{paths}"]}}}
    _write(out, "docs/process/testing.local.json", json.dumps(cfg))
    git("commit", "-qam", "red runner")
    r = _push(git, "origin", "feature")
    assert r.returncode != 0 and "red" in r.stderr, r.stderr
    assert not _remote(bare, "feature")


def test_a_push_certificate_spares_a_branch_push_its_tests(project, tmp_path):
    out, bare, git = project
    _certify(out, tmp_path, "push", None)
    r = _push(git, "origin", "feature")
    assert r.returncode == 0 and "push certificate of tree" in r.stdout + r.stderr, r.stderr
    assert _probe(tmp_path) == ["g"]


def test_a_dirty_worktree_tests_but_writes_no_stamp(project, tmp_path):
    out, bare, git = project
    (out / "stray.txt").write_text("x")
    r = _push(git, "origin", "feature")
    assert r.returncode == 0 and "no stamp" in r.stderr, r.stderr
    _probe(tmp_path)
    assert _push(git, "origin", "feature:refs/heads/copy").returncode == 0
    assert _probe(tmp_path) == ["g", "t app_tests"]


def test_skipping_the_tests_on_a_branch_is_logged_and_stamps_nothing(project, tmp_path):
    out, bare, git = project
    r = _push(git, "origin", "feature", env={"PROCESS_SKIP": "tests"})
    assert r.returncode == 0 and "skipped by PROCESS_SKIP" in r.stderr, r.stderr
    assert _probe(tmp_path) == ["g"]
    ledger = (out / ".git/process-owner-overrides.log").read_text()
    assert "PROCESS_SKIP=tests" in ledger
    assert _push(git, "origin", "feature:refs/heads/copy").returncode == 0
    assert _probe(tmp_path) == ["g", "t app_tests"]


def test_a_skip_from_a_dispatched_session_is_refused(project, tmp_path):
    out, bare, git = project
    r = _push(git, "origin", "feature", env={"PROCESS_SKIP": "tests", "PROCESS_PHASE": "execute"})
    assert r.returncode != 0 and "dispatched session" in r.stderr, r.stderr
    assert not _remote(bare, "feature")


def test_a_broken_test_configuration_refuses_the_push(project, tmp_path):
    out, bare, git = project
    _write(out, "docs/process/testing.local.json", json.dumps({"stacks": {"app": {"paths": []}}}))
    git("commit", "-qam", "broken")
    r = _push(git, "origin", "feature")
    assert r.returncode != 0 and "refused until it parses" in r.stderr, r.stderr


def test_without_a_test_configuration_only_the_gates_run(project, tmp_path):
    out, bare, git = project
    git("rm", "-q", "docs/process/testing.local.json")
    git("commit", "-qm", "no tests configured")
    assert _push(git, "origin", "feature").returncode == 0
    assert _probe(tmp_path) == ["g"]


def _certify(out: Path, tmp_path: Path, kind: str, evidence: str | None) -> None:
    """`evidence` None: the push evidence of the configuration, as the selector names it."""
    what = repr(evidence) if evidence else "test_select.push_evidence(testing_config.load(Path('.')))"
    code = ("import sys; sys.path.insert(0, 'scripts/process'); import certificate, test_select, "
            "testing_config; from pathlib import Path; "
            f"ok, why = certificate.write(Path('.'), {kind!r}, {what}, "
            "before_tree=certificate.evidence_tree(Path('.')), writer='test'); assert ok, why")
    subprocess.run([sys.executable, "-c", code], cwd=out, check=True, env=_env(tmp_path))


def test_a_merge_push_runs_the_merge_suite_unless_a_merge_certificate_covers_the_tree(project, tmp_path):
    out, bare, git = project
    route = {"PROCESS_MERGE_ROUTE": "finish"}
    _certify(out, tmp_path, "push", None)  # a branch's evidence never carries a merge
    r = _push(git, "origin", "HEAD:main", env=route)
    assert r.returncode == 0, r.stderr
    assert _probe(tmp_path) == ["g", "m"]
    _write(out, "app/code.py", "x = 3\n")
    git("commit", "-qam", "more")
    _certify(out, tmp_path, "merge", MERGE_SUITE)
    r = _push(git, "origin", "HEAD:main", env=route)
    assert r.returncode == 0 and "merge certificate of tree" in r.stdout + r.stderr, r.stderr
    assert _probe(tmp_path) == ["g"]


def test_a_busy_lane_exits_75_and_runs_nothing(project, tmp_path):
    out, bare, git = project
    _write(out, "docs/process/testing.local.json",
           json.dumps({"lanes": {"scoped": {"wait": 0.3}, "full": {"wait": 1}}, "stacks": {"app": STACK}}))
    git("commit", "-qam", "short wait")
    env = _env(tmp_path)
    holder = subprocess.Popen([sys.executable, "scripts/process/lane.py", "run", "--lane", "scoped", "--",
                               sys.executable, "-c", "import time; time.sleep(20)"], cwd=out, env=env)
    try:
        for _ in range(100):
            if (tmp_path / "lanes/test-lane-scoped.status").exists():
                break
            time.sleep(0.05)
        head = git("rev-parse", "HEAD").stdout.strip()
        line = f"refs/heads/feature {head} refs/heads/feature {'0' * 40}\n"
        r = subprocess.run([sys.executable, "scripts/process/pre_push.py", "origin", str(bare)], cwd=out,
                           input=line, capture_output=True, text=True, env=env)
        assert r.returncode == 75 and "nothing ran" in r.stderr, r.stderr
        assert "t app_tests" not in _probe(tmp_path)
    finally:
        holder.kill()
        holder.wait()


def test_the_pre_commit_gate_entry_does_not_run_the_gates_a_second_time(project, tmp_path):
    out, bare, git = project
    assert _push(git, "origin", "feature").returncode == 0
    _probe(tmp_path)
    head = git("rev-parse", "HEAD").stdout.strip()
    hook_env = _env(tmp_path, {"PRE_COMMIT_REMOTE_BRANCH": "refs/heads/feature", "PRE_COMMIT_TO_REF": head})
    runner = [sys.executable, "scripts/process/gate_runner.py", "--unless-frame-ran"]
    r = subprocess.run(runner, cwd=out, capture_output=True, text=True, env=hook_env)
    assert r.returncode == 0 and "not again" in r.stderr, r.stdout + r.stderr
    assert _probe(tmp_path) == []
    # the stamp is consumed: a second run is no push the frame saw
    r = subprocess.run(runner, cwd=out, capture_output=True, text=True, env=hook_env)
    assert r.returncode == 0 and _probe(tmp_path) == ["g"], r.stdout + r.stderr
