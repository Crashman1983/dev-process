"""test_select.py (#206): one selection rule for the hook, certify and a manual run."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

PROC = Path(__file__).resolve().parents[1] / "template/scripts/process"
SEL = PROC / "test_select.py"


def _git(root, *args):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True).stdout.strip()


def _write(root, rel, text=""):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


BACKEND = {
    "paths": ["backend/"], "cwd": "backend",
    "runner": [sys.executable, "-c", "import sys, pathlib; pathlib.Path('ran-backend').write_text(' '.join(sys.argv[1:]))", "{paths}"],
    "full": [sys.executable, "-c", "import pathlib; pathlib.Path('ran-backend-full').write_text('x')"],
    "tests": ["backend/tests/**/test_*.py"],
    "map": [{"from": "backend/src/app/{pkg}/{sub}/**", "to": ["backend/tests/{pkg}/{sub}", "backend/tests/{pkg}"]},
            {"from": "backend/src/app/{pkg}/*.py", "to": ["backend/tests/{pkg}"]}],
    "pins": {"Makefile": ["backend/tests/audit/test_make.py"], "e2e/": ["backend/tests/audit/test_e2e.py"]},
    "unmapped": "skip",
}


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "r"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@t")
    _git(root, "config", "user.name", "t")
    _git(root, "config", "commit.gpgsign", "false")
    for rel in ("backend/src/app/api/users/views.py", "backend/src/app/api/util.py",
                "backend/src/app/core/db.py", "backend/tests/api/test_api.py",
                "backend/tests/audit/test_make.py", "backend/tests/audit/test_e2e.py",
                "backend/tests/_schema_template.py", "Makefile", "e2e/spec.ts", "README.md"):
        _write(root, rel, "x = 1\n")
    _write(root, "docs/process/testing.local.json", json.dumps({"stacks": {"backend": BACKEND}}))
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    _git(root, "checkout", "-q", "-b", "feature")
    return root


def _change(root, *rels, delete=()):
    for rel in rels:
        _write(root, rel, "x = 2\n")
    for rel in delete:
        _git(root, "rm", "-q", rel)
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "change")


def _sel(root, *args, env=None):
    return subprocess.run([sys.executable, str(SEL), *args], cwd=root, capture_output=True, text=True,
                          env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", **(env or {})})


def _plan(root, *args):
    r = _sel(root, "plan", "--json", *args)
    assert r.returncode == 0, r.stderr
    return {s["name"]: s for s in json.loads(r.stdout)["stacks"]}


def _config(root, **backend):
    _write(root, "docs/process/testing.local.json", json.dumps({"stacks": {"backend": {**BACKEND, **backend}}}))
    _git(root, "commit", "-qam", "config")


def test_a_source_file_selects_its_closest_test_package_and_names_the_fallback(repo):
    _change(repo, "backend/src/app/api/users/views.py")
    s = _plan(repo)["backend"]
    assert s["action"] == "run" and s["targets"] == ["backend/tests/api"]
    assert any("no tests in backend/tests/api/users" in f for f in s["fallbacks"]), s


def test_a_helper_no_map_reaches_follows_the_unmapped_rule(repo):
    """Downstream: tests/_schema_template.py reached no map and a scoped certification ran everything."""
    _change(repo, "backend/tests/_schema_template.py")
    s = _plan(repo)["backend"]
    assert s["unmapped"] == ["backend/tests/_schema_template.py"] and s["action"] == "none", s
    _config(repo, unmapped="full")
    assert _plan(repo)["backend"]["action"] == "full"


def test_a_test_file_selects_itself_and_pins_fire_for_deleted_subjects(repo):
    _change(repo, "backend/tests/api/test_api.py", delete=["e2e/spec.ts"])
    s = _plan(repo)["backend"]
    assert s["targets"] == ["backend/tests/api/test_api.py", "backend/tests/audit/test_e2e.py"], s


def test_a_path_in_no_stack_counts_only_for_pins(repo):
    _change(repo, "README.md", "Makefile")
    s = _plan(repo)["backend"]
    assert s["targets"] == ["backend/tests/audit/test_make.py"] and not s["unmapped"], s


def test_a_branch_an_integration_ref_contains_changes_nothing(repo):
    s = _plan(repo)["backend"]
    assert s["action"] == "none" and not s["targets"]


def test_no_fork_point_is_no_answer(repo):
    _git(repo, "branch", "-D", "main")
    r = _sel(repo, "plan")
    assert r.returncode == 2 and "no fork point" in r.stderr, r.stderr


def test_a_local_selector_adds_targets_and_its_failure_is_no_empty_answer(repo):
    _write(repo, "sel.py", "import sys\nraw = sys.stdin.buffer.read().split(b'\\0')\n"
                          "assert b'backend/src/app/core/db.py' in raw\nprint('backend/tests/api')\n")
    _config(repo, select=[sys.executable, "sel.py"])
    _change(repo, "backend/src/app/core/db.py")
    s = _plan(repo)["backend"]
    assert s["targets"] == ["backend/tests/api"], s
    _write(repo, "sel.py", "import sys\nsys.exit(3)\n")
    _git(repo, "commit", "-qam", "broken selector")
    r = _sel(repo, "plan")
    assert r.returncode == 2 and "selector failed (3)" in r.stderr, r.stderr


def test_check_names_stale_pins_and_map_targets(repo):
    assert _sel(repo, "check").returncode == 0
    _config(repo, pins={"gone/": ["backend/tests/audit/test_missing.py"]},
            map=[{"from": "backend/src/{a}/**", "to": ["backend/nope/{a}"]}])
    r = _sel(repo, "check")
    assert r.returncode == 1
    assert "pin subject gone/" in r.stderr and "test_missing.py" in r.stderr and "map[0]" in r.stderr


def test_a_path_beginning_with_a_dash_reaches_the_runner_as_a_path(repo):
    _config(repo, tests=["backend/**/test_*.py"])
    _change(repo, "backend/-odd/test_x.py")
    r = _sel(repo, "run")
    assert r.returncode == 0, r.stderr
    assert (repo / "backend/ran-backend").read_text() == "./-odd/test_x.py"


def _lane_repo(repo, tmp_path):
    (repo / "scripts/process").mkdir(parents=True, exist_ok=True)
    for name in ("lane.py", "testing_config.py"):
        shutil.copy(PROC / name, repo / "scripts/process" / name)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "lane")
    return {"PROCESS_LANE_DIR": str(tmp_path / "lanes")}


def test_all_stacks_run_under_one_lane_hold(repo, tmp_path):
    env = _lane_repo(repo, tmp_path)
    # `started` names one hold: a hold per stack would write a new one (same pid or not)
    probe = ("import json, pathlib, sys; rec = json.loads(pathlib.Path(sys.argv[1]).read_text()); "
             "pathlib.Path(sys.argv[2]).write_text(f\"{rec['pid']} {rec['started']}\")")
    status = str(tmp_path / "lanes/test-lane-scoped.status")
    cfg = {"stacks": {
        "backend": {**BACKEND, "runner": [sys.executable, "-c", probe, status, str(tmp_path / "pid-a"), "{paths}"]},
        "web": {"paths": ["web/"], "cwd": ".", "tests": ["web/**/*.test.ts"], "unmapped": "skip",
                "runner": [sys.executable, "-c", probe, status, str(tmp_path / "pid-b"), "{paths}"]}}}
    _write(repo, "docs/process/testing.local.json", json.dumps(cfg))
    _change(repo, "backend/tests/api/test_api.py", "web/a.test.ts")
    r = _sel(repo, "run", env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert (tmp_path / "pid-a").read_text() == (tmp_path / "pid-b").read_text()  # one holder for both


def test_a_busy_lane_runs_nothing_and_exits_75(repo, tmp_path):
    env = _lane_repo(repo, tmp_path)
    _write(repo, "docs/process/testing.local.json",
           json.dumps({"lanes": {"scoped": {"wait": 0.3}, "full": {"wait": 1}}, "stacks": {"backend": BACKEND}}))
    _change(repo, "backend/tests/api/test_api.py")
    holder = subprocess.Popen([sys.executable, str(repo / "scripts/process/lane.py"), "run", "--lane", "scoped",
                               "--", sys.executable, "-c", "import time; time.sleep(20)"],
                              cwd=repo, env={**os.environ, **env, "PYTHONDONTWRITEBYTECODE": "1"})
    try:
        import time
        for _ in range(100):
            if (tmp_path / "lanes/test-lane-scoped.status").exists():
                break
            time.sleep(0.05)
        r = _sel(repo, "run", env=env)
        assert r.returncode == 75 and "nothing ran" in r.stderr, r.stderr
        assert not (repo / "backend/ran-backend").exists()
    finally:
        holder.kill()
        holder.wait()


def test_red_stops_and_a_runner_past_its_time_is_red_and_frees_the_lane(repo, tmp_path):
    env = _lane_repo(repo, tmp_path)
    _config(repo, runner=[sys.executable, "-c", "import time; time.sleep(5)", "{paths}"], timeout=0.5)
    _change(repo, "backend/tests/api/test_api.py")
    r = _sel(repo, "run", env=env)
    assert r.returncode == 1 and "exceeded" in r.stderr, r.stderr
    status = subprocess.run([sys.executable, "scripts/process/lane.py", "status"], cwd=repo, capture_output=True,
                            text=True, env={**os.environ, **env, "PYTHONDONTWRITEBYTECODE": "1"}).stdout
    assert "scoped: free" in status, status


def test_a_deleted_source_still_selects_the_tests_it_maps_to(repo):
    """Refute #206: the deleted module's test package ran nothing, even with unmapped=full."""
    _change(repo, delete=["backend/src/app/api/util.py"])
    s = _plan(repo)["backend"]
    assert s["action"] == "run" and s["targets"] == ["backend/tests/api"], s


def test_the_merge_class_asks_no_selector(repo):
    """A merge push runs its whole suite; a selector that fails cannot refuse it."""
    _write(repo, "sel.py", "import sys\nsys.exit(3)\n")
    _write(repo, "docs/process/testing.local.json", json.dumps(
        {"merge_suite": f"{sys.executable} -c \"open('ran-merge','w')\"",
         "stacks": {"backend": {**BACKEND, "select": [sys.executable, "sel.py"]}}}))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "selector")
    r = _sel(repo, "run", "--class", "merge")
    assert r.returncode == 0 and (repo / "ran-merge").exists(), r.stdout + r.stderr


def test_certify_writes_after_green_on_a_clean_tree_and_the_next_run_reads_it(repo):
    _change(repo, "backend/tests/api/test_api.py")
    (repo / ".gitignore").write_text("backend/ran-*\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "ignore output")
    r = _sel(repo, "run", "--certify")
    assert r.returncode == 0 and "push certificate written" in r.stdout, r.stdout + r.stderr
    (repo / "backend/ran-backend").unlink()
    r = _sel(repo, "run")
    assert "push certificate of tree" in r.stdout and not (repo / "backend/ran-backend").exists()


def test_certify_on_a_dirty_tree_tests_but_certifies_nothing(repo):
    _change(repo, "backend/tests/api/test_api.py")
    (repo / "stray.txt").write_text("x")
    r = _sel(repo, "run", "--certify")
    assert r.returncode == 0 and "no certificate will be written" in r.stdout, r.stdout


def test_the_merge_class_runs_the_merge_suite_without_a_certificate(repo):
    _write(repo, "docs/process/testing.local.json",
           json.dumps({"merge_suite": f"{sys.executable} -c \"open('ran-merge','w')\"", "stacks": {"backend": BACKEND}}))
    _git(repo, "commit", "-qam", "merge suite")
    r = _sel(repo, "run", "--class", "merge")
    assert r.returncode == 0 and (repo / "ran-merge").exists(), r.stdout + r.stderr


def test_the_merge_class_without_suite_or_full_is_refused(repo):
    _config(repo, full=None)
    r = _sel(repo, "run", "--class", "merge")
    assert r.returncode == 2 and "cannot be tested" in r.stderr, r.stderr


def test_no_configuration_selects_nothing(repo):
    _git(repo, "rm", "-q", "docs/process/testing.local.json")
    _git(repo, "commit", "-qm", "no config")
    r = _sel(repo, "run")
    assert r.returncode == 0 and "no test configuration" in r.stdout


# --- #209: the environment preflight -------------------------------------------------

def _preflight_cfg(repo, preflight, **more):
    _write(repo, "docs/process/testing.local.json",
           json.dumps({"preflight": preflight, **more, "stacks": {"backend": BACKEND}}))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "preflight")


@pytest.mark.parametrize("bad", [[], "make doctor", [""], {"run": ["x"]}])
def test_a_malformed_preflight_is_a_broken_configuration(repo, bad):
    _preflight_cfg(repo, bad)
    r = _sel(repo, "plan")
    assert r.returncode == 2 and "preflight" in r.stderr, r.stderr


def test_a_red_preflight_runs_no_test_and_cannot_judge(repo):
    _preflight_cfg(repo, [sys.executable, "-c", "raise SystemExit(4)"])
    _change(repo, "backend/tests/api/test_api.py")
    r = _sel(repo, "run")
    assert r.returncode == 2 and "environment — the preflight exited 4; no test ran" in r.stderr, r.stderr
    assert not (repo / "backend/ran-backend").exists()


def test_a_green_preflight_runs_once_before_the_tests(repo):
    probe = "import pathlib; p = pathlib.Path('preflight.log'); p.write_text(p.read_text() + 'x' if p.exists() else 'x')"
    _preflight_cfg(repo, [sys.executable, "-c", probe])
    (repo / ".gitignore").write_text("preflight.log\nbackend/ran-*\n")
    _change(repo, "backend/tests/api/test_api.py", "backend/src/app/core/db.py")
    r = _sel(repo, "run")
    assert r.returncode == 0, r.stderr
    assert (repo / "preflight.log").read_text() == "x" and (repo / "backend/ran-backend").exists()


def test_a_preflight_past_its_time_cannot_judge(repo):
    _preflight_cfg(repo, [sys.executable, "-c", "import time; time.sleep(5)"], preflight_timeout=0.5)
    _change(repo, "backend/tests/api/test_api.py")
    r = _sel(repo, "run")
    assert r.returncode == 2 and "did not finish in 0 s" in r.stderr, r.stderr


def test_no_preflight_without_work_or_behind_a_certificate(repo):
    marker = "import pathlib; pathlib.Path('preflight.log').write_text('ran')"
    _preflight_cfg(repo, [sys.executable, "-c", marker])
    (repo / ".gitignore").write_text("preflight.log\nbackend/ran-*\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "ignore")
    r = _sel(repo, "run")  # nothing changed on the branch: nothing to test
    assert r.returncode == 0 and not (repo / "preflight.log").exists(), r.stdout + r.stderr
    _change(repo, "backend/tests/api/test_api.py")
    assert _sel(repo, "run", "--certify").returncode == 0
    (repo / "preflight.log").unlink()
    r = _sel(repo, "run")  # the certificate covers the tree
    assert "push certificate of tree" in r.stdout and not (repo / "preflight.log").exists(), r.stdout


def test_a_red_preflight_certifies_nothing(repo):
    _preflight_cfg(repo, [sys.executable, "-c", "raise SystemExit(1)"])
    _change(repo, "backend/tests/api/test_api.py")
    assert _sel(repo, "run", "--certify").returncode == 2
    # same tree: a certificate would be read before the preflight runs again
    r = _sel(repo, "run")
    assert r.returncode == 2 and "certificate of tree" not in r.stdout, r.stdout
