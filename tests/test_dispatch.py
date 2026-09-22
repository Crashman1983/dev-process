import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest


def _git(root: Path, *args: str):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True)


def _dispatch(out: Path, *args: str, env=None):
    return subprocess.run([sys.executable, str(out / "scripts/process/dispatch.py"), *args],
                          cwd=out, capture_output=True, text=True, env=env)


def _repo(out: Path) -> None:
    _git(out, "init", "-q", "-b", "main")
    _git(out, "config", "user.email", "t@t")
    _git(out, "config", "user.name", "t")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "base")


def _fake_command(out: Path, script: str) -> None:
    # the policy's command template points at a fake session: it records its
    # argv and env and sleeps, so start/list/stop can be observed
    pol = out / "docs/process/model-policy.json"
    data = json.loads(pol.read_text())
    fake = out.parent / "fake-session.sh"
    fake.write_text("#!/bin/sh\n" + script)
    fake.chmod(0o755)
    data["command"] = f"{fake} --model {{model}} {{prompt}}"
    data["max_workers"] = 2
    pol.write_text(json.dumps(data))


def test_policy_resolves_by_tier_and_phase(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    r = _dispatch(out, "policy", "--tier", "3")
    assert r.returncode == 0, r.stderr
    assert "plan: claude-opus-5" in r.stdout and "review: claude-fable-5-1" in r.stdout
    r = _dispatch(out, "policy", "--tier", "1")
    assert "execute: claude-sonnet-5" in r.stdout
    r = _dispatch(out, "policy")  # no tier: default row
    assert "execute: claude-sonnet-5" in r.stdout and "plan: claude-opus-5" in r.stdout


def test_start_list_stop_lifecycle(render, tmp_path):
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    _repo(out)
    marker = tmp_path / "seen"
    _fake_command(out, f'echo "$1 $2 phase=$PROCESS_PHASE worker=$PROCESS_WORKER model=$PROCESS_MODEL issue=$PROCESS_ISSUE" > {marker}\n'
                       f'printf "%s" "$3" > {marker}.prompt\nsleep 30\n')
    r = _dispatch(out, "start", "--issue", "7", "--phase", "plan", "--tier", "2", "--title", "Login Flow!")
    assert r.returncode == 0, r.stderr
    assert "started plan for #7 on 7-login-flow with claude-opus-5" in r.stdout
    deadline = time.time() + 10
    while time.time() < deadline and not marker.exists():
        time.sleep(0.1)
    seen = marker.read_text()
    assert "--model claude-opus-5" in seen and "phase=plan" in seen and "worker=7-login-flow" in seen
    prompt = (marker.with_suffix(".prompt")).read_text()
    assert "/plan" in prompt and "issue #7" in prompt and "report.py <state> --issue 7 --model claude-opus-5" in prompt
    wt = out.parent / "repo-7-login-flow"
    assert wt.is_dir() and _git(wt, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == "7-login-flow"
    r = _dispatch(out, "list")
    assert "7-login-flow: plan #7 claude-opus-5" in r.stdout and "LIVE" in r.stdout
    # a second start on the same branch is refused; the cap holds
    assert _dispatch(out, "start", "--issue", "7", "--phase", "execute").returncode == 3
    assert _dispatch(out, "start", "--issue", "8", "--phase", "plan", "--branch", "b8").returncode == 0
    r = _dispatch(out, "start", "--issue", "9", "--phase", "plan", "--branch", "b9")
    assert r.returncode == 3 and "max_workers=2" in r.stderr
    # uncommitted work in the worktree: stop refuses without --force
    (wt / "draft.md").write_text("plan in progress")
    _git(wt, "add", "draft.md")
    r = _dispatch(out, "stop", "7-login-flow")
    assert r.returncode == 3 and "uncommitted work" in r.stderr
    r = _dispatch(out, "stop", "7-login-flow", "--force")
    assert r.returncode == 0 and "stopped 7-login-flow" in r.stdout
    r = _dispatch(out, "list")
    assert "7-login-flow" not in r.stdout and "b8" in r.stdout
    _dispatch(out, "stop", "b8", "--force")
    # the stop reported idle for the worker
    t = json.loads(subprocess.run([sys.executable, str(out / "scripts/process/tower.py"), "--json"],
                                  cwd=out, capture_output=True, text=True).stdout)
    states = {x["worker"]: x["state"] for x in t["reports"]}
    assert states["7-login-flow"] == "idle"
    # stopping something dispatch did not start is refused
    assert _dispatch(out, "stop", "foreign").returncode == 2


def test_dry_run_and_bad_policy(render, tmp_path):
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    _repo(out)
    r = _dispatch(out, "start", "--issue", "3", "--phase", "review", "--tier", "3", "--dry-run")
    assert r.returncode == 0 and "would start review for #3" in r.stdout and "claude-fable-5-1" in r.stdout
    assert not (out.parent / "repo-issue-3").exists()
    pol = out / "docs/process/model-policy.json"
    pol.write_text('{"command": "claude -p"}')
    r = _dispatch(out, "policy")
    assert r.returncode != 0 and "{prompt}" in r.stderr


def test_report_carries_model_and_kpis_cut_by_it(render, tmp_path):
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {"telemetry": True}})
    _repo(out)
    env = dict(os.environ, PROCESS_PHASE="execute")
    r = subprocess.run([sys.executable, str(out / "scripts/process/report.py"), "pushed", "--issue", "5",
                        "--worker", "w5", "--model", "claude-sonnet-5"], cwd=out, capture_output=True, text=True, env=env)
    assert r.returncode == 0
    j = out / ".process-work/journal"
    j.mkdir(parents=True, exist_ok=True)
    (j / "2026-09-21.md").write_text(
        "REVIEW work=5 tier=2 reviewer=fresh model=cross independence=bundle,non-implementing verdict=block round=1\n"
        "REVIEW work=5 tier=2 reviewer=fresh model=cross independence=bundle,non-implementing verdict=pass round=2\n")
    r = subprocess.run([sys.executable, str(out / "scripts/process/process_kpis.py"), "models"],
                       cwd=out, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "execute" in r.stdout and "claude-sonnet-5" in r.stdout and "2.0 (1/1 pass)" in r.stdout
    assert "confidence: low" in r.stdout


@pytest.mark.skipif(shutil.which("tmux") is None, reason="tmux not installed")
def test_tmux_runner_starts_a_window_with_log_and_stops_it(render, tmp_path):
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    _repo(out)
    pol = out / "docs/process/model-policy.json"
    data = json.loads(pol.read_text())
    fake = out.parent / "fake-interactive.sh"
    fake.write_text('#!/bin/sh\necho "hello from $PROCESS_WORKER phase=$PROCESS_PHASE"\necho "prompt-has-issue: $3"\nsleep 60\n')
    fake.chmod(0o755)
    session = f"t{os.getpid()}"
    data.update({"command": f"{fake} --model {{model}} {{prompt}}", "runner": "tmux", "tmux_session": session})
    pol.write_text(json.dumps(data))
    try:
        r = _dispatch(out, "start", "--issue", "11", "--phase", "execute", "--tier", "2", "--branch", "w11")
        assert r.returncode == 0, r.stderr
        assert f"tmux {session}:w11" in r.stdout
        deadline = time.time() + 10
        text = ""
        while time.time() < deadline and "prompt-has-issue" not in text:
            time.sleep(0.2)
            text = _dispatch(out, "log", "w11").stdout
        assert "hello from w11 phase=execute" in text and "issue #11" in text
        t = json.loads(subprocess.run([sys.executable, str(out / "scripts/process/tower.py"), "--json"],
                                      cwd=out, capture_output=True, text=True).stdout)
        s = next(x for x in t["sessions"] if x["branch"] == "w11")
        assert s["alive"] and s["where"] == f"{session}:w11" and s["last_output"]
        r = _dispatch(out, "stop", "w11")
        assert r.returncode == 0 and "stopped w11" in r.stdout
        assert subprocess.run(["tmux", "list-panes", "-t", f"{session}:w11"], capture_output=True).returncode != 0
    finally:
        subprocess.run(["tmux", "kill-session", "-t", session], capture_output=True)
