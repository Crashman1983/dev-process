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


# --- review and refute of #206: every ref kind, every class, every stamp rule ---------

ROUTE = {"PROCESS_MERGE_ROUTE": "finish"}


def test_a_branch_deletion_is_judged_by_the_guard_alone(project, tmp_path):
    out, bare, git = project
    assert _push(git, "origin", "feature").returncode == 0
    _probe(tmp_path)
    r = _push(git, "origin", ":feature")
    assert r.returncode == 0 and not _remote(bare, "feature"), r.stderr
    assert _probe(tmp_path) == []


def test_a_force_push_to_main_without_a_route_is_refused(project, tmp_path):
    out, bare, git = project
    before = _remote(bare, "main")
    r = _push(git, "-f", "origin", "HEAD:main")
    assert r.returncode != 0 and "merge_route" in r.stderr and _remote(bare, "main") == before, r.stderr


def test_a_branch_and_main_in_one_push_are_a_merge(project, tmp_path):
    out, bare, git = project
    r = _push(git, "origin", "feature", "HEAD:main", env=ROUTE)
    assert r.returncode == 0, r.stderr
    assert _probe(tmp_path) == ["g", "m"]  # the merge suite, not the branch selection


def test_a_merge_push_hands_the_gates_their_target(project, tmp_path):
    """Refute B1: without the target the merge-only checks were notes, and the
    pre-commit entry then skipped its strict run behind the frame's stamp."""
    out, bare, git = project
    _write(out, ".process-work/plans/2026-10-10-x.md", "# x\n\ntier: 3\nissue: #1\n")
    git("add", "-A")
    git("commit", "-qm", "plan")
    before = _remote(bare, "main")
    r = _push(git, "origin", "HEAD:main", env=ROUTE)
    assert r.returncode != 0 and _remote(bare, "main") == before, r.stderr
    assert "tier 3" in (r.stdout + r.stderr).lower()


def test_a_merge_suite_without_stacks_runs_on_a_merge_push(project, tmp_path):
    """Refute B2: the frame asked for stacks before it let the merge suite run."""
    out, bare, git = project
    _write(out, "docs/process/testing.local.json", json.dumps({"merge_suite": "echo m >> \"$PROBE\"; exit 1"}))
    git("commit", "-qam", "suite only")
    before = _remote(bare, "main")
    r = _push(git, "origin", "HEAD:main", env=ROUTE)
    assert r.returncode != 0 and _remote(bare, "main") == before, r.stderr
    assert _probe(tmp_path) == ["g", "m"]


def test_skipping_the_gates_on_main_is_the_guards_bypass_and_holds_for_pre_commit(project, tmp_path):
    """F8: the owner's skip is not undone by pre-commit's gate entry."""
    out, bare, git = project
    r = _push(git, "origin", "HEAD:main", env={**ROUTE, "PROCESS_SKIP": "gates"})
    assert r.returncode == 0, r.stderr
    assert _probe(tmp_path) == ["m"]
    assert "PROCESS_SKIP=gates" in (out / ".git/process-owner-overrides.log").read_text()
    head = git("rev-parse", "HEAD").stdout.strip()
    hook_env = _env(tmp_path, {"PRE_COMMIT_REMOTE_BRANCH": "refs/heads/main", "PRE_COMMIT_TO_REF": head})
    r = subprocess.run([sys.executable, "scripts/process/gate_runner.py", "--unless-frame-ran"], cwd=out,
                       capture_output=True, text=True, env=hook_env)
    assert r.returncode == 0 and "not again" in r.stderr and _probe(tmp_path) == [], r.stdout + r.stderr


def test_a_bookkeeping_only_branch_runs_no_tests(project, tmp_path):
    out, bare, git = project
    git("checkout", "-q", "-b", "notes", "main")
    _write(out, ".process-work/journal/2026-10-10.md", "note\n")
    git("add", "-A")
    git("commit", "-qm", "journal")
    r = _push(git, "origin", "notes")
    assert r.returncode == 0, r.stderr
    assert _probe(tmp_path) == ["g"]


def _drop_integration_refs(out: Path, git) -> None:
    git("update-ref", "-d", "refs/remotes/origin/main")
    git("branch", "-D", "main")


def test_without_any_base_a_branch_push_cannot_be_judged(project, tmp_path):
    out, bare, git = project
    _drop_integration_refs(out, git)
    r = _push(git, "origin", "feature")
    assert r.returncode != 0 and "cannot select tests" in r.stderr and not _remote(bare, "feature"), r.stderr


def test_the_remote_side_of_an_update_bounds_the_change_without_a_base(project, tmp_path):
    """R7: a single-branch clone pushing an existing remote branch."""
    out, bare, git = project
    assert _push(git, "origin", "feature").returncode == 0
    _probe(tmp_path)
    _drop_integration_refs(out, git)
    _write(out, "app/code.py", "x = 4\n")
    git("commit", "-qam", "more")
    r = _push(git, "origin", "feature")
    assert r.returncode == 0, r.stderr
    assert _probe(tmp_path) == ["g", "t app_tests"]


def test_a_failing_selector_cannot_judge_the_push(project, tmp_path):
    """Refute m3: exit 2, not a frame crash."""
    out, bare, git = project
    _write(out, "docs/process/testing.local.json", json.dumps(
        {"stacks": {"app": {**STACK, "select": [sys.executable, "-c", "raise SystemExit(3)"]}}}))
    git("commit", "-qam", "selector")
    head = git("rev-parse", "HEAD").stdout.strip()
    r = subprocess.run([sys.executable, "scripts/process/pre_push.py", "origin", str(bare)], cwd=out,
                       input=f"refs/heads/feature {head} refs/heads/feature {'0' * 40}\n",
                       capture_output=True, text=True, env=_env(tmp_path))
    assert r.returncode == 2 and "selector failed (3)" in r.stderr and "frame failed" not in r.stderr, r.stderr


def test_a_variable_that_narrows_the_tests_writes_no_stamp(project, tmp_path):
    """Refute M1: the stamp follows the certificate's environment rule. A narrowed run
    still ran — only a run under which make runs nothing is refused (#265)."""
    out, bare, git = project
    _write(out, "docs/process/testing.local.json",
           json.dumps({"certificate_env": ["NARROW"], "stacks": {"app": STACK}}))
    git("commit", "-qam", "narrow")
    r = _push(git, "origin", "feature", env={"NARROW": "1"})
    assert r.returncode == 0 and "no stamp — NARROW is set" in r.stderr, r.stderr
    _probe(tmp_path)
    assert _push(git, "origin", "feature:refs/heads/copy").returncode == 0
    assert _probe(tmp_path) == ["g", "t app_tests"]


def test_a_make_variable_on_the_outer_make_still_runs_the_tests(project, tmp_path):
    """Refute of #265: `make finish ISSUE=…` exports `MAKEFLAGS= -- ISSUE=…`; that run
    happens — it is no dry run and must not refuse the push."""
    out, bare, git = project
    r = _push(git, "origin", "feature", env={"MAKEFLAGS": " -- ISSUE=7"})
    assert r.returncode == 0 and "no test ran" not in r.stderr, r.stderr
    assert "t app_tests" in _probe(tmp_path)


def test_gnumakeflags_dry_run_refuses_the_push_too(project, tmp_path):
    """Refute of #265: GNU make reads GNUMAKEFLAGS like MAKEFLAGS."""
    out, bare, git = project
    r = _push(git, "origin", "feature", env={"GNUMAKEFLAGS": "-n"})
    assert r.returncode != 0 and "GNUMAKEFLAGS" in r.stderr and "no test ran" in r.stderr, r.stderr


def test_an_inherited_dry_run_makeflags_refuses_the_push(project, tmp_path):
    """#265: under `MAKEFLAGS=-n` a make recipe exits 0 having run nothing;
    the hook accepted that as a green test run."""
    out, bare, git = project
    r = _push(git, "origin", "feature", env={"MAKEFLAGS": "-n"})
    assert r.returncode != 0 and "no test ran" in r.stderr, r.stderr
    assert "t app_tests" not in _probe(tmp_path)


def test_a_commit_made_during_the_run_writes_no_stamp(project, tmp_path):
    """Refute m1: the stamp names what the tests saw, or nothing."""
    out, bare, git = project
    commit = ("import os, subprocess; open(os.environ['PROBE'], 'a').write('t\\n'); "
              "subprocess.run(['git', 'commit', '-q', '--allow-empty', '-m', 'during'], check=True)")
    _write(out, "docs/process/testing.local.json",
           json.dumps({"stacks": {"app": {**STACK, "runner": [sys.executable, "-c", commit, "{paths}"]}}}))
    git("commit", "-qam", "committing runner")
    head = git("rev-parse", "HEAD").stdout.strip()
    r = subprocess.run([sys.executable, "scripts/process/pre_push.py", "origin", str(bare)], cwd=out,
                       input=f"refs/heads/feature {head} refs/heads/feature {'0' * 40}\n",
                       capture_output=True, text=True, env=_env(tmp_path))
    assert r.returncode == 0 and "no stamp — HEAD or the tree moved" in r.stderr, r.stderr


def test_an_untracked_configuration_change_is_no_stamp_hit(project, tmp_path):
    """Refute m2: the stamp names the configuration it ran under."""
    out, bare, git = project
    git("rm", "-q", "--cached", "docs/process/testing.local.json")
    (out / ".git/info/exclude").write_text("docs/process/testing.local.json\n")
    git("commit", "-qm", "local config")
    assert _push(git, "origin", "feature").returncode == 0
    _write(out, "docs/process/testing.local.json", json.dumps(
        {"stacks": {"app": {**STACK, "runner": [sys.executable, "-c", "raise SystemExit(1)", "{paths}"]}}}))
    r = _push(git, "origin", "feature:refs/heads/copy")
    assert r.returncode != 0 and not _remote(bare, "copy"), r.stderr


def test_pre_commits_route_check_names_the_frames_refusal(project, tmp_path):
    """S3: a refused push reads as refused, not as "guard not installed"."""
    out, bare, git = project
    cfg = {"stacks": {"app": {**STACK, "runner": [sys.executable, "-c", "raise SystemExit(1)", "{paths}"]}}}
    _write(out, "docs/process/testing.local.json", json.dumps(cfg))
    git("commit", "-qam", "red")
    head = git("rev-parse", "HEAD").stdout.strip()
    assert _push(git, "origin", "feature").returncode != 0
    hook_env = _env(tmp_path, {"PRE_COMMIT_REMOTE_BRANCH": "refs/heads/feature", "PRE_COMMIT_TO_REF": head})
    r = subprocess.run([sys.executable, "scripts/process/merge_route.py", "--hook-check"], cwd=out,
                       capture_output=True, text=True, env=hook_env)
    assert r.returncode == 1 and "refused this push (red)" in r.stderr, r.stderr


def test_the_gates_start_from_an_interpreter_without_their_dependencies(project, tmp_path):
    """Review F1: the guard runs as the system python3; the gate runner declares
    PyYAML (PEP 723) — the frame launches it as gate_invoke says, not with its own interpreter."""
    import shutil
    if not shutil.which("uv"):
        pytest.skip("uv resolves the runner's declaration")
    out, bare, git = project
    venv = tmp_path / "bare-python"
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(venv)], check=True)
    python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    assert subprocess.run([str(python), "-c", "import yaml"], capture_output=True).returncode != 0
    head = git("rev-parse", "HEAD").stdout.strip()
    r = subprocess.run([str(python), "scripts/process/pre_push.py", "origin", str(bare)], cwd=out,
                       input=f"refs/heads/feature {head} refs/heads/feature {'0' * 40}\n",
                       capture_output=True, text=True, env=_env(tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr
    assert _probe(tmp_path) == ["g", "t app_tests"]


def test_a_gate_skip_and_a_non_fast_forward_override_are_two_ledger_lines(project, tmp_path):
    """Refute round 2: the override's line replaced the skip's."""
    out, bare, git = project
    assert _push(git, "origin", "HEAD:main", env=ROUTE).returncode == 0
    git("reset", "-q", "--hard", "HEAD~1")
    _write(out, "app/code.py", "x = 5\n")
    git("commit", "-qam", "rewrite")
    r = _push(git, "-f", "origin", "HEAD:main",
              env={"PROCESS_SKIP": "gates", "PROCESS_OWNER_OVERRIDE": "fix main"})
    assert r.returncode == 0, r.stderr
    ledger = (out / ".git/process-owner-overrides.log").read_text()
    assert "PROCESS_SKIP=gates" in ledger and "fix main" in ledger, ledger


def test_a_merge_push_runs_its_suite_even_when_the_selector_fails(project, tmp_path):
    """Review F9: the merge class asks no selector — with the real change set."""
    out, bare, git = project
    _write(out, "docs/process/testing.local.json", json.dumps(
        {"merge_suite": MERGE_SUITE,
         "stacks": {"app": {**STACK, "select": [sys.executable, "-c", "raise SystemExit(3)"]}}}))
    git("commit", "-qam", "failing selector")
    r = _push(git, "origin", "HEAD:main", env=ROUTE)
    assert r.returncode == 0, r.stderr
    assert _probe(tmp_path) == ["g", "m"]


# --- #209: the environment preflight -------------------------------------------------

@pytest.mark.parametrize("target", ["feature", "HEAD:main"])
def test_a_red_preflight_refuses_the_push_without_a_test_or_a_stamp(project, tmp_path, target):
    out, bare, git = project
    cfg = {"preflight": [sys.executable, "-c", "raise SystemExit(5)"], "merge_suite": MERGE_SUITE,
           "stacks": {"app": STACK}}
    _write(out, "docs/process/testing.local.json", json.dumps(cfg))
    git("commit", "-qam", "preflight")
    r = _push(git, "origin", target, env=ROUTE)
    assert r.returncode != 0 and "environment — the preflight exited 5" in r.stderr, r.stderr
    assert _probe(tmp_path) == ["g"]  # gates ran, no test
    assert not (out / ".git/process-push-ok").exists() or not (out / ".git/process-push-ok").read_text().strip()


# --- #219: git's repo-local variables stay out of the children ------------------------

def test_a_runner_that_commits_in_its_own_repo_leaves_the_pushing_repo_alone(project, tmp_path):
    """git hands the hook GIT_DIR and GIT_INDEX_FILE; a test that builds its
    own repo wrote into the pushing one (downstream: commits on the branch)."""
    out, bare, git = project
    own = ("import os, subprocess, tempfile; d = tempfile.mkdtemp(); "
           "open(os.environ['PROBE'], 'a').write('t\\n'); "
           "open(os.path.join(d, 'f'), 'w').write('x'); "
           "g = lambda *a: subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@t', "
           "'-c', 'commit.gpgsign=false', *a], cwd=d, capture_output=True); "
           "g('init', '-q'); g('add', 'f'); g('commit', '-qm', 'runner')")
    _write(out, "docs/process/testing.local.json",
           json.dumps({"stacks": {"app": {**STACK, "runner": [sys.executable, "-c", own, "{paths}"]}}}))
    git("commit", "-qam", "committing runner")
    head = git("rev-parse", "HEAD").stdout.strip()
    index = git("ls-files", "--stage").stdout
    # as git sets them for a hook in a linked worktree: absolute
    r = _push(git, "origin", "feature",
              env={"GIT_DIR": str(out / ".git"), "GIT_INDEX_FILE": str(out / ".git/index")})
    assert r.returncode == 0, r.stderr
    assert _probe(tmp_path) == ["g", "t"]
    assert git("rev-parse", "HEAD").stdout.strip() == head
    assert git("ls-files", "--stage").stdout == index
    assert git("log", "--format=%s", "-1").stdout.strip() == "committing runner"


@pytest.mark.parametrize("name,flags", [("MAKEFLAGS", "-q"), ("MAKEFLAGS", "-t"), ("MAKEFLAGS", "-sn"),
                                         ("MAKEFLAGS", "--dry-run"), ("MAKEFLAGS", "--just-print"),
                                         ("MAKEFLAGS", "--recon"), ("MAKEFLAGS", "--question"),
                                         ("MAKEFLAGS", "--touch"), ("GNUMAKEFLAGS", "--dry-run")])
def test_every_no_op_make_flag_is_refused(render, tmp_path, monkeypatch, name, flags):
    """Cross-model review: only `-n` was exercised; `-q`, `-t` and the long forms were not."""
    import importlib
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    for var in ("MAKEFLAGS", "GNUMAKEFLAGS"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv(name, flags)
    sys.path.insert(0, str(out / "scripts/process"))
    try:
        sys.modules.pop("certificate", None)
        cert = importlib.import_module("certificate")
        assert cert.noop_problem() and name in cert.noop_problem(), flags
        monkeypatch.setenv(name, "-j4 --no-print-directory")
        assert cert.noop_problem() is None
    finally:
        sys.path.remove(str(out / "scripts/process"))
        sys.modules.pop("certificate", None)
