import importlib.util
import json
import subprocess
import sys
from pathlib import Path


def _git(root: Path, *args: str):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True)


def _commit(root: Path, files: dict[str, str | None], msg: str) -> None:
    for rel, text in files.items():
        p = root / rel
        if text is None:
            p.unlink()
            continue
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", msg)


def _load(out: Path):
    spec = importlib.util.spec_from_file_location("plan_drift_under_test", out / "scripts/process/plan_drift.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


PLAN = ".process-work/plans/2026-10-01-login.md"


def _project(render, tmp_path, mandate: dict | None = None) -> Path:
    """A rendered project with an origin, a plan for #7 naming two files, and
    six later commits on main: three change a named file, one deletes the
    other, two touch something else."""
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    _git(out, "init", "-q", "-b", "main")
    _git(out, "config", "user.email", "t@t")
    _git(out, "config", "user.name", "t")
    if mandate is not None:
        (out / "docs/process/optimization.local.json").write_text(json.dumps(mandate))
    _commit(out, {"src/a.py": "a = 0\n", "src/gone.py": "g = 0\n", "src/other.py": "o = 0\n"}, "base")
    _commit(out, {PLAN: "# Login\n\nissue: #7\ntier: 2\n\n1. Change `src/a.py:3` and drop `src/gone.py`.\n"
                        "2. See `https://example.org/x.py` and `make test`.\n"}, "plan for #7")
    for i in range(3):
        _commit(out, {"src/a.py": f"a = {i + 1}\n"}, f"a {i}")
    _commit(out, {"src/gone.py": None}, "drop gone")
    for i in range(2):
        _commit(out, {"src/other.py": f"o = {i + 1}\n"}, f"o {i}")
    _git(out, "remote", "add", "origin", str(origin))
    _git(out, "push", "-q", "origin", "main")
    _git(out, "fetch", "-q", "origin")
    return out


def _events(out: Path) -> list[dict]:
    common = Path(_git(out, "rev-parse", "--git-common-dir").stdout.strip())
    log = (common if common.is_absolute() else out / common) / "process-gate-events.jsonl"
    if not log.is_file():
        return []
    return [json.loads(line) for line in log.read_text().splitlines() if line.strip()]


def test_drift_counts_commits_behind_and_those_touching_named_files(render, tmp_path):
    out = _project(render, tmp_path)
    mod = _load(out)
    r = mod.measure(out, 7)
    assert r["outcome"] == "pass" and r["mode"] == "shadow"  # defaults: 10 touching, 500 behind
    (plan,) = r["plans"]
    assert plan["path"] == PLAN and plan["behind"] == 6
    assert plan["touching"] == 4  # three edits of a.py, the deletion of gone.py
    assert plan["named"] == 2 and plan["vanished"] == ["src/gone.py"]  # a URL and a command name nothing
    assert mod.measure(out, 8)["outcome"] == "skipped"


def test_a_plan_refreshed_on_the_branch_starts_the_count_again(render, tmp_path):
    out = _project(render, tmp_path, {"plan_drift": {"max_touching": 2}})
    mod = _load(out)
    assert mod.measure(out, 7)["outcome"] == "fail"
    _git(out, "checkout", "-q", "-b", "7-login")
    _commit(out, {PLAN: (out / PLAN).read_text() + "\n3. Re-checked against main.\n"}, "refresh plan")
    _git(out, "checkout", "-q", "main")
    r = mod.measure(out, 7, "7-login")
    assert r["outcome"] == "pass" and r["plans"][0]["behind"] == 0


def test_modes_shadow_records_warn_notes_block_refuses(render, tmp_path):
    out = _project(render, tmp_path, {"plan_drift": {"mode": "shadow", "max_touching": 2}})
    mod = _load(out)
    assert mod.check_execute(out, 7, "7-login", dry_run=False, stale_plan_ok=False) == (None, None)
    ev = _events(out)[-1]
    assert ev["gate"] == "plan-drift" and ev["mode"] == "shadow" and ev["outcome"] == "fail"
    assert ev["issue"] == 7 and ev["branch"] == "7-login" and ev["plans"][0]["touching"] == 4

    (out / "docs/process/optimization.local.json").write_text(json.dumps({"plan_drift": {"mode": "warn", "max_touching": 2}}))
    why, note = mod.check_execute(out, 7, "7-login", dry_run=False, stale_plan_ok=False)
    assert why is None and "Plan drift" in note and "4 touch" in note

    (out / "docs/process/optimization.local.json").write_text(json.dumps({"plan_drift": {"mode": "block", "max_touching": 2}}))
    why, note = mod.check_execute(out, 7, "7-login", dry_run=False, stale_plan_ok=False)
    assert "refresh the plan" in why and note is None
    why, note = mod.check_execute(out, 7, "7-login", dry_run=False, stale_plan_ok=True)
    assert why is None and note and _events(out)[-1]["override"] is True
    n = len(_events(out))
    mod.check_execute(out, 7, "7-login", dry_run=True, stale_plan_ok=False)
    assert len(_events(out)) == n  # a dry run records nothing


def test_a_bad_mandate_value_falls_back_and_says_so(render, tmp_path):
    out = _project(render, tmp_path, {"plan_drift": {"mode": "loud", "max_touching": -1}})
    conf, problems = _load(out).settings(out)
    assert conf == {"mode": "shadow", "max_touching": 10, "max_behind": 500}
    assert len(problems) == 2


def test_without_a_remote_base_nothing_is_told(render, tmp_path):
    out = _project(render, tmp_path)
    _git(out, "remote", "remove", "origin")
    r = _load(out).measure(out, 7)
    assert r["outcome"] == "unknown" and "remote" in r["reason"]


def test_dispatch_refuses_a_blocked_execute_and_starts_with_the_override(render, tmp_path):
    out = _project(render, tmp_path, {"plan_drift": {"mode": "block", "max_touching": 2}})
    run = [sys.executable, str(out / "scripts/process/dispatch.py"), "start", "--issue", "7",
           "--phase", "execute", "--tier", "2", "--branch", "7-login", "--dry-run"]
    r = subprocess.run(run, cwd=out, capture_output=True, text=True)
    assert r.returncode == 3 and "plan drift" in r.stderr and "--stale-plan-ok" in r.stderr
    r = subprocess.run(run + ["--stale-plan-ok"], cwd=out, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "would start execute for #7" in r.stdout
    # the plan phase is not asked: refreshing the plan is the way out
    r = subprocess.run([*run[:6], "plan", *run[7:]], cwd=out, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
