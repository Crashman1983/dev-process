import json
import math
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


def _fake_lane(out: Path, status: str) -> None:
    # the project's own lane tool: one status line per lane (scripts/lane.py)
    lane = out / "scripts" / "lane.py"
    lane.write_text(f"import sys\nprint({status!r})\n")


FULL_HELD = "scoped: free\nfull: held by pid 1 — test-boundary (train/x) since 09:28 (0 min)"


def _load_dispatch(out: Path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("dispatch_under_test", out / "scripts/process/dispatch.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


LANE_TABLE = [
    (set(), {"plan": True, "execute": True, "review": True}),
    ({"full"}, {"plan": True, "execute": False, "review": True}),
    ({"scoped"}, {"plan": False, "execute": False, "review": False}),
    ({"scoped", "full"}, {"plan": False, "execute": False, "review": False}),
    ({"gpu"}, {"plan": False, "execute": False, "review": False}),
]


@pytest.mark.parametrize("held,allowed", LANE_TABLE)
@pytest.mark.parametrize("phase", ["plan", "execute", "review"])
def test_lane_rule_by_lane_and_phase(render, tmp_path, held, allowed, phase):
    d = _load_dispatch(render(tmp_path, {"project_name": "d", "modules": {}}))
    verdict = d.lane_verdict(held, phase)
    assert (verdict is None) == allowed[phase], verdict
    if verdict:
        assert phase in verdict and any(name in verdict for name in held)


def test_lane_status_is_parsed_line_by_line(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    d = _load_dispatch(out)
    _fake_lane(out, FULL_HELD)
    assert d.held_lanes(out) == {"full"}
    _fake_lane(out, "scoped: free\nfull: free — last held by nobody")  # a label is not a holder
    assert d.held_lanes(out) == set()


def test_full_lane_held_lets_plan_start_but_not_execute(render, tmp_path):
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    _repo(out)
    _fake_command(out, "sleep 30\n")
    _fake_lane(out, FULL_HELD)
    r = _dispatch(out, "start", "--issue", "8", "--phase", "execute", "--branch", "b8")
    assert r.returncode == 3 and "full" in r.stderr and "execute" in r.stderr
    r = _dispatch(out, "start", "--issue", "8", "--phase", "plan", "--branch", "b8")
    assert r.returncode == 0, r.stderr
    _dispatch(out, "stop", "b8", "--force")


def test_policy_resolves_by_tier_and_phase(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    r = _dispatch(out, "policy", "--tier", "3")
    assert r.returncode == 0, r.stderr
    assert "plan: claude-opus-5" in r.stdout and "review: claude-opus-5 (xhigh)" in r.stdout
    assert "execute: claude-opus-5\n" in r.stdout  # a plain cell prints no effort
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
    assert r.returncode == 3 and "uncommitted or untracked work" in r.stderr
    _git(wt, "reset", "-q", "draft.md")
    r = _dispatch(out, "stop", "7-login-flow")  # untracked counts too
    assert r.returncode == 3 and "untracked" in r.stderr
    r = _dispatch(out, "stop", "7-login-flow", "--force")
    assert r.returncode == 0 and "stopped 7-login-flow" in r.stdout
    r = _dispatch(out, "list")
    assert "7-login-flow" not in r.stdout and "b8" in r.stdout
    # the next phase for #7 finds its branch again although the record is gone
    r = _dispatch(out, "start", "--issue", "7", "--phase", "execute", "--dry-run")
    assert r.returncode == 0 and "on 7-login-flow" in r.stdout
    # a record whose pid was recycled by another process is not "ours": stop refuses to kill
    rec_dir = Path(_git(out, "rev-parse", "--git-common-dir").stdout.strip())
    rec_dir = (rec_dir if rec_dir.is_absolute() else out / rec_dir) / "process-dispatch"
    rec = json.loads((rec_dir / "b8.json").read_text())
    rec["pid_start"] = "not-the-real-start"
    (rec_dir / "b8.json").write_text(json.dumps(rec))
    r = _dispatch(out, "stop", "b8", "--force")
    assert r.returncode == 0 and "gone" in r.stdout
    assert subprocess.run(["kill", "-0", str(rec["pid"])]).returncode == 0  # still running: not ours to kill
    os.killpg(os.getpgid(rec["pid"]), 15)
    # the forced stop reported idle for the worker
    t = json.loads(subprocess.run([sys.executable, str(out / "scripts/process/tower.py"), "--json"],
                                  cwd=out, capture_output=True, text=True).stdout)
    states = {x["worker"]: x["state"] for x in t["reports"]}
    assert states["7-login-flow"] == "idle"
    # stopping something dispatch did not start is refused
    assert _dispatch(out, "stop", "foreign").returncode == 2


def test_remote_phase_hands_over_without_a_worktree(render, tmp_path):
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    _repo(out)
    bare = tmp_path / "origin.git"
    _git(out, "clone", "-q", "--bare", str(out), str(bare))
    _git(out, "remote", "add", "origin", str(bare))
    marker = tmp_path / "handover"
    pol = out / "docs/process/model-policy.json"
    data = json.loads(pol.read_text())
    cloud = out.parent / "start-cloud.sh"
    cloud.write_text(f'#!/bin/sh\nprintf "%s|%s|%s|%s|%s|%s" "$1" "$2" "$3" "$PROCESS_PHASE" "$4" "$PROCESS_EFFORT" > {marker}\necho session-abc\n')
    cloud.chmod(0o755)
    local = out.parent / "local.sh"
    local.write_text("#!/bin/sh\nsleep 30\n")
    local.chmod(0o755)
    data["command"] = f"{local} {{prompt}}"
    data["phases"] = {"review": {"command": f"{cloud} {{branch}} {{model}} {{prompt}} {{effort}}", "remote": True}}
    pol.write_text(json.dumps(data))
    # the branch must be on origin first — a review of unpushed work is nothing
    r = _dispatch(out, "start", "--issue", "4", "--phase", "review", "--branch", "b4")
    assert r.returncode == 3 and "not on origin" in r.stderr
    _git(out, "branch", "b4")
    _git(out, "push", "-q", "origin", "b4")
    r = _dispatch(out, "start", "--issue", "4", "--phase", "review", "--tier", "3", "--branch", "b4")
    assert r.returncode == 0, r.stderr
    assert "handed review for #4" in r.stdout and "session-abc" in r.stdout
    seen = marker.read_text().split("|")
    assert seen[0] == "b4" and seen[1] == "claude-opus-5" and seen[3] == "review"
    assert seen[4:] == ["xhigh", "xhigh"]  # the Tier 3 review cell's effort: argv and env
    assert "--sync" in seen[2] and "PROCESS_REPORT_SYNC=1" in seen[2] and "/review" in seen[2]
    assert not (out.parent / "repo-b4").exists()  # no local worktree for a remote phase
    r = _dispatch(out, "list")
    assert "b4: review #4" in r.stdout and "another host" in r.stdout and "REMOTE" in r.stdout
    # a remote record does not count against this host's cap; local phases keep the local command
    r = _dispatch(out, "start", "--issue", "5", "--phase", "plan", "--branch", "b5", "--dry-run")
    assert r.returncode == 0 and "local.sh" in r.stdout and "(remote, " not in r.stdout
    r = _dispatch(out, "stop", "b4")
    assert r.returncode == 0 and "another host" in r.stdout
    assert "b4" not in _dispatch(out, "list").stdout
    # a bad per-phase command is refused up front
    data["phases"] = {"review": {"command": "cloud-start only"}}
    pol.write_text(json.dumps(data))
    assert "{prompt}" in _dispatch(out, "policy").stderr


def test_remote_phase_skips_local_cap_and_lanes(render, tmp_path):
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    _repo(out)
    bare = tmp_path / "origin.git"
    _git(out, "clone", "-q", "--bare", str(out), str(bare))
    _git(out, "remote", "add", "origin", str(bare))
    marker = tmp_path / "handover"
    pol = out / "docs/process/model-policy.json"
    data = json.loads(pol.read_text())
    cloud = out.parent / "start-cloud.sh"
    cloud.write_text(f'#!/bin/sh\necho "$PROCESS_PHASE" > {marker}\necho session-xyz\n')
    cloud.chmod(0o755)
    local = out.parent / "local.sh"
    local.write_text("#!/bin/sh\nsleep 30\n")
    local.chmod(0o755)
    data["command"] = f"{local} {{prompt}}"
    data["max_workers"] = 1
    data["phases"] = {"review": {"command": f"{cloud} {{prompt}}", "remote": True}}
    pol.write_text(json.dumps(data))
    assert _dispatch(out, "start", "--issue", "6", "--phase", "plan", "--branch", "b6").returncode == 0
    _git(out, "branch", "b7")
    _git(out, "push", "-q", "origin", "b7")
    _fake_lane(out, "scoped: held by pid 1 — x (y) since 09:00 (1 min)\nfull: free")
    # cap and lane refuse a local phase ...
    r = _dispatch(out, "start", "--issue", "7", "--phase", "plan", "--branch", "b7")
    assert r.returncode == 3 and "max_workers=1" in r.stderr
    # ... but not a remote one: its load lies on the other host
    r = _dispatch(out, "start", "--issue", "7", "--phase", "review", "--branch", "b7")
    assert r.returncode == 0, r.stderr
    assert marker.read_text().strip() == "review"
    _dispatch(out, "stop", "b6", "--force")


def test_a_session_whose_phase_is_over_holds_no_slot(render, tmp_path):
    """Kenni #2414: a plan session that reported `planned` still counted
    against max_workers until somebody stopped it."""
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    _repo(out)
    _fake_command(out, "sleep 30\n")  # max_workers=2
    try:
        for b in ("b1", "b2"):
            assert _dispatch(out, "start", "--issue", b[1:], "--phase", "plan", "--branch", b).returncode == 0
        r = _dispatch(out, "start", "--issue", "3", "--phase", "plan", "--branch", "b3", "--dry-run")
        assert r.returncode == 3 and "max_workers=2" in r.stderr
        env = dict(os.environ, PROCESS_PHASE="plan")
        r = subprocess.run([sys.executable, str(out / "scripts/process/report.py"), "planned", "--issue", "1",
                            "--worker", "b1", "--model", "m", "--force"], cwd=out, capture_output=True,
                           text=True, env=env)
        assert r.returncode == 0, r.stderr
        r = _dispatch(out, "start", "--issue", "3", "--phase", "plan", "--branch", "b3", "--dry-run")
        assert r.returncode == 0, r.stderr
        # the same branch's live session still refuses, phase over or not
        r = _dispatch(out, "start", "--issue", "1", "--phase", "execute", "--branch", "b1", "--dry-run")
        assert r.returncode == 3 and "already has a live session" in r.stderr
    finally:
        for b in ("b1", "b2"):
            _dispatch(out, "stop", b, "--force")


def test_worktree_path_taken_by_a_foreign_directory_is_refused(render, tmp_path):
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    _repo(out)
    _fake_command(out, "sleep 30\n")
    (out.parent / "repo-b1").mkdir()
    (out.parent / "repo-b1" / "secret.txt").write_text("not a worktree")
    r = _dispatch(out, "start", "--issue", "1", "--phase", "plan", "--branch", "b1")
    assert r.returncode != 0 and "not a worktree" in r.stderr
    assert (out.parent / "repo-b1" / "secret.txt").read_text() == "not a worktree"


def test_prompt_inside_a_token_and_env_stripped(render, tmp_path):
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    _repo(out)
    marker = tmp_path / "seen"
    pol = out / "docs/process/model-policy.json"
    data = json.loads(pol.read_text())
    fake = out.parent / "fake.sh"
    fake.write_text(f'#!/bin/sh\nprintf "%s\\n" "$2" > {marker}\necho "CC=${{CLAUDECODE:-unset}} CCE=${{CLAUDE_CODE_ENTRY:-unset}} $1" >> {marker}\nsleep 30\n')
    fake.chmod(0o755)
    data["command"] = f"{fake} --name={{branch}}-{{issue}} --prompt={{prompt}}"  # placeholders inside tokens
    pol.write_text(json.dumps(data))
    env = dict(os.environ, CLAUDECODE="1", CLAUDE_CODE_ENTRY="steward")
    r = _dispatch(out, "start", "--issue", "2", "--phase", "plan", "--branch", "b2", env=env)
    assert r.returncode == 0, r.stderr
    deadline = time.time() + 10
    while time.time() < deadline and not marker.exists():
        time.sleep(0.1)
    time.sleep(0.3)
    seen = marker.read_text()
    assert seen.startswith("--prompt=/plan issue #2") and "CC=unset CCE=unset --name=b2-2" in seen
    _dispatch(out, "stop", "b2", "--force")


@pytest.mark.parametrize("runner", ["detached", "tmux"])
def test_policy_env_reaches_the_worker_only(render, tmp_path, runner):
    # worker sessions run built-in subagents on a cheaper model; the
    # steward's own CLAUDE_CODE_* is still stripped, the policy's value wins
    if runner == "tmux" and shutil.which("tmux") is None:
        pytest.skip("tmux not installed")
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    _repo(out)
    marker = tmp_path / "seen"
    pol = out / "docs/process/model-policy.json"
    data = json.loads(pol.read_text())
    fake = out.parent / "fake.sh"
    fake.write_text(f'#!/bin/sh\necho "SUB=${{CLAUDE_CODE_SUBAGENT_MODEL:-unset}} '
                    f'X=${{X_TOP:-unset}} CCE=${{CLAUDE_CODE_ENTRY:-unset}}" > {marker}\nsleep 30\n')
    fake.chmod(0o755)
    session = f"envtest{os.getpid()}"
    data.update({"command": f"{fake} {{prompt}}", "runner": runner, "tmux_session": session,
                 "env": {"CLAUDE_CODE_SUBAGENT_MODEL": "haiku", "X_TOP": "top"},
                 "phases": {"plan": {"env": {"CLAUDE_CODE_SUBAGENT_MODEL": "sonnet"}}}})
    pol.write_text(json.dumps(data))
    env = dict(os.environ, CLAUDE_CODE_SUBAGENT_MODEL="opus", CLAUDE_CODE_ENTRY="steward")
    try:
        r = _dispatch(out, "start", "--issue", "4", "--phase", "plan", "--branch", "b4", env=env)
        assert r.returncode == 0, r.stderr
        deadline = time.time() + 15
        while time.time() < deadline and not (marker.exists() and marker.read_text()):
            time.sleep(0.1)
        assert marker.read_text().strip() == "SUB=sonnet X=top CCE=unset"
    finally:
        _dispatch(out, "stop", "b4", "--force")
        subprocess.run(["tmux", "kill-session", "-t", session], capture_output=True)


def test_policy_env_must_not_set_process_vars(render, tmp_path):
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    pol = out / "docs/process/model-policy.json"
    data = json.loads(pol.read_text())
    data["phases"] = {"review": {"env": {"PROCESS_PHASE": "x"}}}
    pol.write_text(json.dumps(data))
    r = _dispatch(out, "policy")
    assert r.returncode != 0 and "PROCESS_*" in r.stderr
    data["phases"] = {}
    data["env"] = {"A": 1}
    pol.write_text(json.dumps(data))
    r = _dispatch(out, "policy")
    assert r.returncode != 0 and "must map names to strings" in r.stderr

def test_dry_run_and_bad_policy(render, tmp_path):
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    _repo(out)
    r = _dispatch(out, "start", "--issue", "3", "--phase", "review", "--tier", "3", "--dry-run")
    assert r.returncode == 0 and "would start review for #3" in r.stdout and "claude-opus-5 (xhigh)" in r.stdout
    assert "--effort=xhigh" in r.stdout  # the default command carries the cell's effort
    assert not (out.parent / "repo-issue-3").exists()
    pol = out / "docs/process/model-policy.json"
    pol.write_text('{"command": "claude -p"}')
    r = _dispatch(out, "policy")
    assert r.returncode != 0 and "{prompt}" in r.stderr


def test_dry_run_names_the_lane_rule(render, tmp_path):
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    _repo(out)
    _fake_lane(out, FULL_HELD)
    r = _dispatch(out, "start", "--issue", "9", "--phase", "plan", "--dry-run")
    assert r.returncode == 0, r.stderr
    assert "lane rule" in r.stdout and "allowed" in r.stdout and "full" in r.stdout
    r = _dispatch(out, "start", "--issue", "9", "--phase", "execute", "--dry-run")
    assert r.returncode == 3  # a refusal is never a green dry run
    assert "lane rule" in r.stderr and "refused" in r.stderr


def test_report_carries_model_and_kpis_cut_by_it(render, tmp_path):
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {"telemetry": True}})
    _repo(out)
    env = dict(os.environ, PROCESS_PHASE="execute")
    r = subprocess.run([sys.executable, str(out / "scripts/process/report.py"), "pushed", "--issue", "5",
                        "--worker", "w5", "--model", "claude-sonnet-5", "--force"], cwd=out, capture_output=True, text=True, env=env)
    assert r.returncode == 0
    j = out / ".process-work/journal"
    j.mkdir(parents=True, exist_ok=True)
    (j / "2026-09-21.md").write_text(
        "REVIEW work=5 tier=2 reviewer=fresh model=cross independence=bundle,non-implementing verdict=block round=1\n"
        "REVIEW work=5 tier=2 reviewer=fresh model=cross independence=bundle,non-implementing verdict=pass round=2\n")
    # a second report of the same phase does not count the rounds twice
    subprocess.run([sys.executable, str(out / "scripts/process/report.py"), "done", "--issue", "5",
                    "--worker", "w5", "--model", "claude-sonnet-5"], cwd=out, capture_output=True, text=True, env=env)
    r = subprocess.run([sys.executable, str(out / "scripts/process/process_kpis.py"), "models"],
                       cwd=out, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "execute" in r.stdout and "claude-sonnet-5" in r.stdout and "2.0 (1/1 pass)" in r.stdout
    assert "confidence: low" in r.stdout
    # a re-dispatch with another model supersedes: the last execute model owns the issue
    subprocess.run([sys.executable, str(out / "scripts/process/report.py"), "pushed", "--issue", "5",
                    "--worker", "w5", "--model", "claude-opus-5", "--force"], cwd=out, capture_output=True, text=True, env=env)
    r = subprocess.run([sys.executable, str(out / "scripts/process/process_kpis.py"), "models"],
                       cwd=out, capture_output=True, text=True)
    assert "claude-opus-5" in r.stdout and "claude-sonnet-5" not in r.stdout
    # the effort is part of the cell: the same model at another effort is another row
    subprocess.run([sys.executable, str(out / "scripts/process/report.py"), "pushed", "--issue", "5",
                    "--worker", "w5", "--model", "claude-opus-5", "--force"], cwd=out, capture_output=True, text=True,
                   env={**env, "PROCESS_EFFORT": "xhigh"})
    recs = [json.loads(x) for x in (out / ".git/process-tower/reports.jsonl").read_text().splitlines()]
    assert recs[-1]["effort"] == "xhigh" and "effort" not in recs[0]  # absent when unset: records unchanged
    r = subprocess.run([sys.executable, str(out / "scripts/process/process_kpis.py"), "models"],
                       cwd=out, capture_output=True, text=True)
    assert "claude-opus-5 (xhigh)" in r.stdout, r.stdout


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
        assert "hello from w11 phase=execute" in text and "issue #11" in text and "LIVE" not in text
        assert "— live" in text
        t = json.loads(subprocess.run([sys.executable, str(out / "scripts/process/tower.py"), "--json"],
                                      cwd=out, capture_output=True, text=True).stdout)
        s = next(x for x in t["sessions"] if x["branch"] == "w11")
        assert s["alive"] and s["state"] == "live" and s["where"] == f"tmux {session}:w11" and s["last_output"]
        # a line typed into the worker reaches its stdin
        r = _dispatch(out, "say", "w11", "DECISION 2026-09-22 owner: B — because cheaper")
        assert r.returncode == 0, r.stderr
        r = _dispatch(out, "stop", "w11")
        assert r.returncode == 0 and "stopped w11" in r.stdout
        assert subprocess.run(["tmux", "list-panes", "-t", f"{session}:w11"], capture_output=True).returncode != 0
        # a worker that exits by itself is DEAD, not live: the shell pid is not the worker
        fake.write_text('#!/bin/sh\necho "done quickly"\n')
        r = _dispatch(out, "start", "--issue", "12", "--phase", "execute", "--branch", "w12")
        assert r.returncode == 0, r.stderr
        deadline = time.time() + 10
        text = ""
        while time.time() < deadline and "dead" not in text:
            time.sleep(0.2)
            text = _dispatch(out, "list").stdout
        assert "w12" in text and "DEAD" in text and "done quickly" in text
        assert _dispatch(out, "say", "w12", "hello").returncode == 3
        r = _dispatch(out, "stop", "w12")
        assert r.returncode == 0 and "dead" in r.stdout
    finally:
        subprocess.run(["tmux", "kill-session", "-t", session], capture_output=True)


@pytest.mark.skipif(shutil.which("tmux") is None, reason="tmux not installed")
def test_remote_phase_with_tmux_runner_hands_over_from_a_terminal(render, tmp_path):
    # a hand-over CLI that refuses to start without a terminal: the tmux runner
    # gives it one; a failed hand-over shows as FAILED, never as a running review
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    _repo(out)
    bare = tmp_path / "origin.git"
    _git(out, "clone", "-q", "--bare", str(out), str(bare))
    _git(out, "remote", "add", "origin", str(bare))
    _git(out, "branch", "b6")
    _git(out, "push", "-q", "origin", "b6")
    cloud = out.parent / "cloud.sh"
    cloud.write_text('#!/bin/sh\nif [ -t 0 ]; then echo "cloud session started for $1"; sleep 30; '
                     'else echo "needs a terminal" >&2; exit 1; fi\n')
    cloud.chmod(0o755)
    pol = out / "docs/process/model-policy.json"
    data = json.loads(pol.read_text())
    session = f"t-{os.getpid()}"
    data["tmux_session"] = session
    data["phases"] = {"review": {"command": f"{cloud} {{branch}} {{prompt}}", "remote": True, "runner": "tmux"}}
    pol.write_text(json.dumps(data))
    try:
        r = _dispatch(out, "start", "--issue", "6", "--phase", "review", "--branch", "b6")
        assert r.returncode == 0, r.stderr
        assert "from tmux" in r.stdout
        for _ in range(160):  # generous: a loaded CI host starts tmux panes slowly
            if "cloud session started for b6" in _dispatch(out, "log", "b6").stdout:
                break
            time.sleep(0.25)
        assert "cloud session started for b6" in _dispatch(out, "log", "b6").stdout
        assert "REMOTE (hand-over window live)" in _dispatch(out, "list").stdout
        # a hand-over that fails shows as such
        _dispatch(out, "stop", "b6")
        cloud.write_text('#!/bin/sh\necho "login required"; exit 4\n')
        r = _dispatch(out, "start", "--issue", "6", "--phase", "review", "--branch", "b6")
        assert r.returncode == 0, r.stderr
        for _ in range(160):  # generous: a loaded CI host starts tmux panes slowly
            if "HAND-OVER FAILED (exit 4)" in _dispatch(out, "list").stdout:
                break
            time.sleep(0.25)
        assert "HAND-OVER FAILED (exit 4)" in _dispatch(out, "list").stdout
    finally:
        subprocess.run(["tmux", "kill-session", "-t", session], capture_output=True)


def test_remote_hand_over_names_the_session_it_started(render, tmp_path):
    # a starter that prints text, not JSON: the session id is read from that
    # text — by the policy's handover_id regex, else the first URL
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    _repo(out)
    bare = tmp_path / "origin.git"
    _git(out, "clone", "-q", "--bare", str(out), str(bare))
    _git(out, "remote", "add", "origin", str(bare))
    for b in ("b7", "b8"):
        _git(out, "branch", b)
        _git(out, "push", "-q", "origin", b)
    cloud = out.parent / "cloud.sh"
    cloud.write_text('#!/bin/sh\necho "Starting cloud session..."\n'
                     'echo "Session session_01AbC started: https://claude.ai/code/session_01AbC"\n')
    cloud.chmod(0o755)
    pol = out / "docs/process/model-policy.json"
    data = json.loads(pol.read_text())
    data["phases"] = {"review": {"command": f"{cloud} {{prompt}}", "remote": True}}
    pol.write_text(json.dumps(data))
    assert _dispatch(out, "start", "--issue", "7", "--phase", "review", "--branch", "b7").returncode == 0
    assert "session: https://claude.ai/code/session_01AbC" in _dispatch(out, "list").stdout
    data["phases"]["review"]["handover_id"] = r"Session (session_\w+) started"
    pol.write_text(json.dumps(data))
    assert _dispatch(out, "start", "--issue", "8", "--phase", "review", "--branch", "b8").returncode == 0
    listing = _dispatch(out, "list").stdout
    assert "b8" in listing and "session: session_01AbC" in listing
    assert "session session_01AbC" in _dispatch(out, "log", "b8").stdout
    data["phases"]["review"]["handover_id"] = "(unclosed"
    pol.write_text(json.dumps(data))
    assert "not a regex" in _dispatch(out, "policy").stderr


# --- say checks delivery; phases chain; the queue skips; workers run niced ---

class _Pane:
    """A fake tmux pane: send-keys are recorded, capture-pane shows `screens`
    one after the other (the last one repeats)."""

    def __init__(self, screens):
        self.screens, self.keys = list(screens), []

    def __call__(self, *args):
        if args[0] == "send-keys":
            self.keys.append(args[-1])
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[0] == "capture-pane":
            screen = self.screens.pop(0) if len(self.screens) > 1 else self.screens[0]
            return subprocess.CompletedProcess(args, 0, screen, "")
        return subprocess.CompletedProcess(args, 0, "", "")


def _say_setup(render, tmp_path, monkeypatch, screens):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    mod = _load_dispatch(out)
    pane = _Pane(screens)
    monkeypatch.setattr(mod, "_tmux", pane)
    monkeypatch.setattr(mod, "_sleep", lambda _s: None)
    monkeypatch.setattr(mod, "_load_record", lambda root, b: (tmp_path / "r.json",
                                                              {"tmux_window": "@1", "state": "live"}))
    return out, mod, pane


BOX = "╭──────╮\n│ > {} │\n╰──────╯\n"


def test_say_presses_enter_again_until_the_text_left_the_input_line(render, tmp_path, monkeypatch):
    stuck, empty = BOX.format("Lane a is free for you"), BOX.format("")
    out, mod, pane = _say_setup(render, tmp_path, monkeypatch, [empty, stuck, stuck, empty])  # first: before typing
    assert mod.say(out, "w1", "Lane a is free for you") == 0
    assert pane.keys == ["Lane a is free for you", "Enter", "Enter", "Enter"]


def test_say_fails_naming_the_branch_when_the_text_never_leaves(render, tmp_path, monkeypatch, capsys):
    out, mod, pane = _say_setup(render, tmp_path, monkeypatch, [BOX.format("the train is through")])
    assert mod.say(out, "w1", "the train is through") == 4
    assert pane.keys.count("Enter") == 1 + mod.SAY_RETRIES
    assert "w1" in capsys.readouterr().err


def test_say_counts_a_queued_message_as_delivered(render, tmp_path, monkeypatch):
    # mid-turn: the harness shows the message above an empty input line
    screen = "> decision text\n  (queued)\n" + BOX.format("")
    out, mod, pane = _say_setup(render, tmp_path, monkeypatch, [screen])
    assert mod.say(out, "w1", "decision text") == 0
    assert pane.keys == ["decision text", "Enter"]


def test_say_fails_naming_the_branch_when_the_input_line_is_unreadable(render, tmp_path, monkeypatch, capsys):
    """Kenni #2405: a screen without a prompt line was "said" (exit 0)."""
    out, mod, pane = _say_setup(render, tmp_path, monkeypatch, ["some output\nno prompt here\n"])
    assert mod.say(out, "w1", "decision text") == 6
    err = capsys.readouterr().err
    assert "w1" in err and "input line unreadable" in err and "say_prompt" in err, err
    assert pane.keys == ["decision text", "Enter"]


def test_drain_skips_a_refused_line_instead_of_waiting_on_it(render, tmp_path, monkeypatch):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    mod = _load_dispatch(out)
    for issue, phase in ((1, "execute"), (2, "plan"), (3, "review")):
        mod.queue_add(out, issue=issue, phase=phase, tier=2, branch=None)
    started = []

    def fake_start(root, *, issue, phase, **_kw):
        if phase == "execute":
            return 3  # a held lane refuses execute
        started.append((issue, phase))
        return 0

    monkeypatch.setattr(mod, "start", fake_start)
    mod.drain(out)
    assert started == [(2, "plan"), (3, "review")]
    assert [e["issue"] for e in mod.queue_load(out)] == [1]


def test_chain_moves_each_report_to_its_next_phase(render, tmp_path, monkeypatch):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    mod = _load_dispatch(out)
    recs = [
        {"branch": "a", "issue": 1, "tier": 2, "phase": "plan", "started": 1},
        {"branch": "b", "issue": 2, "tier": 2, "phase": "execute", "started": 1},
        {"branch": "c", "issue": 3, "tier": 2, "phase": "execute", "started": 1},
        {"branch": "d", "issue": 4, "tier": 2, "phase": "review", "started": 1},
        {"branch": "e", "issue": 5, "tier": 2, "phase": "review", "started": 1},
        {"branch": "f", "issue": 6, "tier": 2, "phase": "execute", "started": 1},
    ]
    reports = [{"worker": "a", "state": "planned", "epoch": 1}, {"worker": "b", "state": "pushed", "epoch": 1},
               {"worker": "c", "state": "pushed", "epoch": 1}, {"worker": "d", "state": "review-pass", "epoch": 1},
               {"worker": "e", "state": "review-pass", "epoch": 1}, {"worker": "f", "state": "blocked", "epoch": 1}]
    stopped, started = [], []
    monkeypatch.setattr(mod, "records", lambda root: recs)
    monkeypatch.setattr(mod, "_load_record", lambda root, b: (None, next(r for r in recs if r["branch"] == b)))
    monkeypatch.setattr(mod, "plan_tier_on_origin", lambda root, b: None)
    monkeypatch.setattr(mod._report, "read_reports", lambda root, **_kw: reports)
    monkeypatch.setattr(mod, "new_code_on_origin", lambda root, b, **_kw: b == "b")  # c: an attestation only
    monkeypatch.setattr(mod, "work_complete_on_origin", lambda root, b: True)
    monkeypatch.setattr(mod, "attest_on_origin", lambda root, b: b == "d")    # e's attestation is not pushed
    monkeypatch.setattr(mod, "stop", lambda root, b, **kw: stopped.append((b, kw.get("keep_report"))) or 0)
    monkeypatch.setattr(mod, "start", lambda root, *, issue, phase, **_kw: started.append((issue, phase)) or 0)
    mod.chain(out)
    assert stopped == [("a", True), ("b", True), ("d", True)]
    assert started == [(1, "execute"), (2, "review")]


def _origin_pair(tmp_path):
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    work = tmp_path / "work"
    work.mkdir()
    _git(work, "init", "-q", "-b", "main")
    _git(work, "config", "user.email", "t@t")
    _git(work, "config", "user.name", "t")
    (work / "a.py").write_text("a = 0\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-q", "-m", "base")
    _git(work, "remote", "add", "origin", str(origin))
    _git(work, "push", "-q", "origin", "main")
    _git(work, "fetch", "-q", "origin")
    _git(work, "checkout", "-q", "-b", "w")
    return work


def _commit_file(root, rel, text, msg):
    (root / rel).parent.mkdir(parents=True, exist_ok=True)
    (root / rel).write_text(text)
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", msg)


def test_new_code_on_origin_sees_past_bookkeeping_and_stops_at_the_attestation(render, tmp_path):
    out = render(tmp_path / "p", {"project_name": "d", "modules": {}})
    mod = _load_dispatch(out)
    work = _origin_pair(tmp_path)
    _commit_file(work, "a.py", "a = 1\n", "code")
    _git(work, "push", "-q", "origin", "w")
    assert mod.new_code_on_origin(work, "w")
    _commit_file(work, ".process-work/journal/j.md", "REVIEW …\n", "docs: attest")
    _git(work, "push", "-q", "origin", "w")
    assert not mod.new_code_on_origin(work, "w")  # an attestation-only push is no work for a review
    assert mod.attest_on_origin(work, "w")
    _commit_file(work, ".process-work/plans/p.md", "# plan\n", "plan note")
    _commit_file(work, "a.py", "a = 2\n", "more code")
    assert not mod.attest_on_origin(work, "w")  # local head moved past what origin holds
    _git(work, "push", "-q", "origin", "w")
    assert mod.new_code_on_origin(work, "w")


def test_local_workers_start_niced(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    mod = _load_dispatch(out)
    if shutil.which("nice"):
        assert mod.niced({}, ["claude", "x"]) == ["nice", "-n", "10", "env", "claude", "x"]
        assert mod.niced({"worker_nice": 5}, ["claude"]) == ["nice", "-n", "5", "env", "claude"]
        assert mod.niced({"worker_nice": None}, ["c"]) == ["nice", "-n", "10", "env", "c"]
    assert mod.niced({"worker_nice": 0}, ["claude"]) == ["claude"]
    for bad in ("high", 5.9, True):
        with pytest.raises(SystemExit):
            mod.niced({"worker_nice": bad}, ["claude"])


# --- refute of the chain: each case a downstream way it went wrong ---


def test_a_queue_file_does_not_break_the_records(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    mod = _load_dispatch(out)
    mod.queue_add(out, issue=1, phase="plan", tier=1, branch=None)
    assert mod.records(out) == []
    assert _dispatch(out, "list").returncode == 0


def test_chain_waits_for_open_tasks_and_ignores_old_reports(render, tmp_path, monkeypatch):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    mod = _load_dispatch(out)
    recs = [{"branch": "x", "issue": 1, "tier": 2, "phase": "execute", "started": 100},
            {"branch": "y", "issue": 2, "tier": 2, "phase": "plan", "started": 100},
            {"branch": "z", "issue": 3, "tier": 2, "phase": "plan", "started": 100, "state": "unknown"}]
    reports = [{"worker": "x", "state": "pushed", "epoch": 200},
               {"worker": "y", "state": "planned", "epoch": 50},    # from before this session
               {"worker": "z", "state": "planned", "epoch": 200}]   # tmux cannot be asked
    stopped = []
    monkeypatch.setattr(mod, "records", lambda root: recs)
    monkeypatch.setattr(mod._report, "read_reports", lambda root, **_kw: reports)
    monkeypatch.setattr(mod, "new_code_on_origin", lambda root, b, **_kw: True)
    monkeypatch.setattr(mod, "work_complete_on_origin", lambda root, b: False)  # first push, tasks open
    monkeypatch.setattr(mod, "stop", lambda root, b, **kw: stopped.append(b) or 0)
    monkeypatch.setattr(mod, "start", lambda root, **_kw: 0)
    mod.chain(out)
    assert stopped == [] and mod.queue_load(out) == []


def test_an_unknown_pane_is_not_stopped(render, tmp_path, monkeypatch):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    mod = _load_dispatch(out)
    rec = tmp_path / "rec.json"
    rec.write_text("{}")
    monkeypatch.setattr(mod, "_load_record", lambda root, b: (rec, {"state": "unknown", "branch": b}))
    assert mod.stop(out, "w", force=False) == 3 and rec.exists()


def test_the_queue_keeps_one_line_per_issue_and_phase(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    mod = _load_dispatch(out)
    mod.queue_add(out, issue=4, phase="execute", tier=None, branch=None)
    mod.queue_add(out, issue=4, phase="execute", tier=2, branch="issue-4")
    assert len(mod.queue_load(out)) == 1


def test_a_start_that_exits_does_not_wedge_the_queue(render, tmp_path, monkeypatch):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    mod = _load_dispatch(out)
    for issue in (10, 11, 12):
        mod.queue_add(out, issue=issue, phase="plan", tier=1, branch=None)

    def fake_start(root, *, issue, **_kw):
        if issue == 11:
            raise SystemExit("worktree path taken")
        return 0

    monkeypatch.setattr(mod, "start", fake_start)
    mod.drain(out)
    assert [e["issue"] for e in mod.queue_load(out)] == [11]


def test_two_drains_start_each_line_once_and_adds_are_not_lost(render, tmp_path, monkeypatch):
    import threading
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    mod = _load_dispatch(out)
    for issue in range(5):
        mod.queue_add(out, issue=issue + 1, phase="plan", tier=1, branch=None)
    started, lock = [], threading.Lock()

    def slow_start(root, *, issue, **_kw):
        time.sleep(0.05)
        with lock:
            started.append(issue)
        return 0

    monkeypatch.setattr(mod, "start", slow_start)
    threads = [threading.Thread(target=mod.drain, args=(out,)) for _ in range(2)]
    threads += [threading.Thread(target=mod.queue_add, args=(out,),
                                 kwargs={"issue": 100 + i, "phase": "review", "tier": 2, "branch": None})
                for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(started) == sorted(set(started))  # nothing started twice
    left = {e["issue"] for e in mod.queue_load(out)}
    assert all(i in set(started) | left for i in range(100, 120))  # no add lost


def test_a_corrupt_queue_is_kept_aside_not_dropped(render, tmp_path, capsys):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    mod = _load_dispatch(out)
    q = mod._queue_path(out)
    q.write_text("{not json")
    assert mod.queue_load(out) == []
    assert list(q.parent.glob("queue.corrupt-*.json")) and "kept as" in capsys.readouterr().err
    q.write_text(json.dumps([{"issue": "abc", "phase": "plan"}, {"issue": 2, "phase": "plan", "tier": "zz"},
                             {"issue": 3, "phase": "plan", "branch": 5}, {"issue": 4, "phase": "plan"}]))
    assert [e["issue"] for e in mod.queue_load(out)] == [4]


def test_a_journal_note_is_no_attestation_and_a_merge_counts_its_own_code(render, tmp_path):
    out = render(tmp_path / "p", {"project_name": "d", "modules": {}})
    mod = _load_dispatch(out)
    work = _origin_pair(tmp_path)
    _commit_file(work, "a.py", "a = 1\n", "code")
    _commit_file(work, ".process-work/journal/j.md", "why I chose X\n", "journal note mid-work")
    _git(work, "push", "-q", "origin", "w")
    assert mod.new_code_on_origin(work, "w")
    _commit_file(work, ".process-work/journal/j.md", "why I chose X\nREVIEW work=w verdict=pass\n", "attest")
    _git(work, "push", "-q", "origin", "w")
    assert mod.new_code_on_origin(work, "w") is False
    # a merge whose conflict resolution writes code after the attestation
    _git(work, "checkout", "-q", "-b", "side", "main")
    _commit_file(work, "a.py", "a = 'side'\n", "side")
    _git(work, "checkout", "-q", "w")
    subprocess.run(["git", "merge", "-q", "--no-edit", "side"], cwd=work, capture_output=True)
    (work / "a.py").write_text("a = 'resolved'\n")
    _git(work, "commit", "-q", "-am", "merge side")
    _git(work, "push", "-q", "origin", "w")
    assert mod.new_code_on_origin(work, "w")
    assert mod.new_code_on_origin(work, "nosuch") is None


def test_open_tasks_on_origin_mean_the_work_is_not_done(render, tmp_path):
    out = render(tmp_path / "p", {"project_name": "d", "modules": {}})
    mod = _load_dispatch(out)
    work = _origin_pair(tmp_path)
    _commit_file(work, ".process-work/plans/2026-01-01-w.md", "# w\n\n- [x] one\n- [ ] two\n", "plan")
    _git(work, "push", "-q", "origin", "w")
    assert mod.work_complete_on_origin(work, "w") is False
    _commit_file(work, ".process-work/plans/2026-01-01-w.md", "# w\n\n- [x] one\n- [x] two\n", "done")
    _git(work, "push", "-q", "origin", "w")
    assert mod.work_complete_on_origin(work, "w") is True


def test_origin_is_asked_for_exactly_this_branch(render, tmp_path):
    out = render(tmp_path / "p", {"project_name": "d", "modules": {}})
    mod = _load_dispatch(out)
    work = _origin_pair(tmp_path)
    _git(work, "push", "-q", "origin", "HEAD:refs/heads/feat/w")
    assert mod._remote_head(work, "w") == ""
    _git(work, "push", "-q", "origin", "w")
    assert mod._remote_head(work, "w") == _git(work, "rev-parse", "w").stdout.strip()


def test_say_finds_a_long_wrapped_input_and_a_pasted_placeholder(render, tmp_path, monkeypatch):
    long = "x" * 900
    wrapped = "> earlier message\n" + "│ > " + long[:70] + " │\n" + "".join(f"│ {long[i:i + 70]} │\n"
                                                                     for i in range(70, 900, 70))
    out, mod, pane = _say_setup(render, tmp_path, monkeypatch, [wrapped])
    assert mod.say(out, "w1", long) == 4
    out2, mod2, _pane = _say_setup(render, tmp_path / "b", monkeypatch, [BOX.format("[Pasted text #1 +3 lines]")])
    assert mod2.say(out2, "w1", "a\nb\nc") == 4


def test_a_say_prompt_without_a_group_falls_back(render, tmp_path, monkeypatch):
    out, mod, _pane = _say_setup(render, tmp_path, monkeypatch, ["> \n"])
    monkeypatch.setattr(mod, "load_policy", lambda root: {"say_prompt": "^>"})
    assert mod.say(out, "w1", "hello") == 0


def test_a_missing_harness_is_a_refusal_and_assignments_survive_nice(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    mod = _load_dispatch(out)
    assert mod.runnable(["no-such-harness-xyz", "p"]) is not None
    assert mod.runnable(["FOO=bar", "sh", "-c", "true"]) is None
    assert mod.runnable(["/nonexistent/claude"]) is not None
    if shutil.which("nice"):
        argv = mod.niced({}, ["FOO=bar", "sh", "-c", 'test "$FOO" = bar'])
        assert subprocess.run(argv).returncode == 0


# --- second refute of the chain ---


def test_say_never_types_or_presses_enter_into_a_dialog(render, tmp_path, monkeypatch):
    dialog = "> earlier\nDo you want to proceed?\n❯ 1. Yes\n  2. No\n"
    out, mod, pane = _say_setup(render, tmp_path, monkeypatch, [dialog])
    assert mod.say(out, "w1", "1 more thing: stop") == 5 and pane.keys == []  # open before: nothing typed
    typed_then_dialog = BOX.format("run it") + "Do you want to proceed?\n❯ 1. Yes\n"
    out2, mod2, pane2 = _say_setup(render, tmp_path / "b", monkeypatch, [BOX.format(""), typed_then_dialog])
    assert mod2.say(out2, "w1", "run it") == 5 and pane2.keys == ["run it", "Enter"]  # no extra Enter
    delivered = "> Do you want to know more?\n" + BOX.format("")
    out3, mod3, _p3 = _say_setup(render, tmp_path / "c", monkeypatch, [BOX.format(""), delivered])
    assert mod3.say(out3, "w1", "Do you want to know more?") == 0  # delivered text is no dialog


def test_work_complete_reads_only_the_branchs_own_plan_and_skips_fenced_examples(render, tmp_path):
    out = render(tmp_path / "p", {"project_name": "d", "modules": {}})
    mod = _load_dispatch(out)
    work = _origin_pair(tmp_path)
    _git(work, "checkout", "-q", "main")
    _commit_file(work, ".process-work/plans/2026-01-01-other.md", "# other\n\n- [ ] not mine\n", "other plan")
    _git(work, "push", "-q", "origin", "main")
    _git(work, "fetch", "-q", "origin")
    _git(work, "checkout", "-q", "w")
    _git(work, "merge", "-q", "--no-edit", "main")
    _commit_file(work, ".process-work/plans/2026-01-01-other.md", "# other\n\n- [ ] not mine\n- note\n", "touch")
    _commit_file(work, ".process-work/plans/2026-01-02-w.md",
                 "# w\n\ntier: 3\n\n- [x] done\n\n```\n- [ ] an example\n```\n", "own plan")
    _git(work, "push", "-q", "origin", "w")
    assert mod.work_complete_on_origin(work, "w") is True
    assert mod.plan_tier_on_origin(work, "w") == 3


def test_chain_does_not_stop_a_session_that_changed_since_it_was_judged(render, tmp_path, monkeypatch):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    mod = _load_dispatch(out)
    judged = [{"branch": "a", "issue": 1, "tier": 2, "phase": "plan", "started": 1}]
    now = {"branch": "a", "issue": 1, "tier": 2, "phase": "execute", "started": 5}  # restarted meanwhile
    stopped = []
    monkeypatch.setattr(mod, "records", lambda root: judged)
    monkeypatch.setattr(mod, "_load_record", lambda root, b: (None, now))
    monkeypatch.setattr(mod._report, "read_reports",
                        lambda root, **_kw: [{"worker": "a", "state": "planned", "epoch": 3}])
    monkeypatch.setattr(mod, "stop", lambda root, b, **kw: stopped.append(b) or 0)
    monkeypatch.setattr(mod, "start", lambda root, **_kw: 0)
    mod.chain(out)
    assert stopped == []


def test_queue_lines_are_strict_and_a_branch_named_queue_does_not_collide(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    mod = _load_dispatch(out)
    q = mod._queue_path(out)
    q.write_text(json.dumps([{"issue": True, "phase": "plan"}, {"issue": 7.9, "phase": "plan"},
                             {"issue": "8", "phase": "plan"}]))
    assert [e["issue"] for e in mod.queue_load(out)] == [8]
    q.write_text(json.dumps({"not": "a list"}))
    assert mod.queue_load(out) == [] and list(q.parent.glob("queue.corrupt-*.json"))
    assert mod._record_path(out, "queue") != q
    rec = mod._record_path(out, "queue")
    rec.write_text(json.dumps({"branch": "queue", "issue": 1, "phase": "plan", "pid": 0}))
    assert [r["branch"] for r in mod.records(out)] == ["queue"]  # a branch named queue is a record


def test_a_bulleted_review_line_is_an_attestation(render, tmp_path):
    out = render(tmp_path / "p", {"project_name": "d", "modules": {}})
    mod = _load_dispatch(out)
    work = _origin_pair(tmp_path)
    _commit_file(work, "a.py", "a = 1\n", "code")
    _commit_file(work, ".process-work/journal/j.md", "- REVIEW work=w verdict=pass\n", "attest")
    _git(work, "push", "-q", "origin", "w")
    assert mod.new_code_on_origin(work, "w") is False and mod.attest_on_origin(work, "w")


def test_say_answers_a_question_asked_in_prose(render, tmp_path, monkeypatch):
    question = "● Do you want to keep the old API or drop it?\n" + BOX.format("")
    out, mod, pane = _say_setup(render, tmp_path, monkeypatch, [question, question])
    assert mod.say(out, "w1", "keep it") == 0 and pane.keys == ["keep it", "Enter"]


def test_an_archived_foreign_plan_is_not_the_branchs_own(render, tmp_path):
    out = render(tmp_path / "p", {"project_name": "d", "modules": {}})
    mod = _load_dispatch(out)
    work = _origin_pair(tmp_path)
    _git(work, "checkout", "-q", "main")
    _commit_file(work, ".process-work/plans/2026-01-01-other.md", "# other\n\ntier: 3\nissue: #5\n\n- [ ] open\n", "x")
    _git(work, "push", "-q", "origin", "main")
    _git(work, "fetch", "-q", "origin")
    _git(work, "checkout", "-q", "w")
    _git(work, "merge", "-q", "--no-edit", "main")
    (work / ".process-work/plans/archive").mkdir(parents=True, exist_ok=True)
    _git(work, "mv", ".process-work/plans/2026-01-01-other.md", ".process-work/plans/archive/2026-01-01-other.md")
    _commit_file(work, ".process-work/plans/2026-01-02-w.md", "# w\n\ntier: 1\nissue: #6\n\n- [x] done\n", "own")
    _git(work, "push", "-q", "origin", "w")
    assert mod.work_complete_on_origin(work, "w") is True and mod.plan_tier_on_origin(work, "w") == 1


# --- the start prompt names the steward as decision partner ---

def test_the_start_prompt_names_the_steward_and_the_execute_duties(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    mod = _load_dispatch(out)
    for phase in ("plan", "execute", "review"):
        text = mod.prompt_for(phase, 7, 2, "7-work", "m")
        assert "Your decision partner is the steward, not the owner" in text, phase
        assert "DECISION NEEDED" in text and "report.py blocked" in text and "never a question in chat" in text
        assert "reach the steward live" not in text
    execute = mod.prompt_for("execute", 7, 2, "7-work", "m")
    assert "ROOT-CAUSE work=<id> round=<r>: <cause> — <test that failed before the fix>" in execute
    assert "attest.py --dry-run" in execute and "The duties before `pushed` are in /execute" in execute
    live = mod.prompt_for("plan", 7, 2, "7-work", "m", channel="SendMessage to 'steward'")
    assert "reach the steward live via SendMessage to 'steward'" in live


def test_the_policy_decision_channel_reaches_the_prompt(render, tmp_path, monkeypatch):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    mod = _load_dispatch(out)
    seen = []
    monkeypatch.setattr(mod, "prompt_for", lambda *a, **k: seen.append(k.get("channel")) or "p")
    for channel, expected in (("SendMessage to 'steward'", "SendMessage to 'steward'"), ("  ", None), (7, None)):
        policy = json.loads((out / "docs/process/model-policy.json").read_text())
        policy["decision_channel"] = channel
        monkeypatch.setattr(mod, "load_policy", lambda _root, p=policy: p)
        mod.start(out, issue=7, phase="plan", tier=2, branch="7-work", title=None, dry_run=True)
        assert seen[-1] == expected, channel


# --- the session's own report, and whether its phase is over: one answer for chain and tower ---

def test_a_report_from_before_the_session_is_not_its_word(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    mod = _load_dispatch(out)
    rec = {"branch": "7-work", "started": 100}
    reports = [{"worker": "7-work", "state": "planned", "epoch": 50},
               {"worker": "other", "state": "blocked", "epoch": 200}]
    assert mod.session_report(rec, reports) is None
    reports.append({"worker": "7-work", "state": "pushed", "epoch": 120})
    reports.append({"worker": "7-work", "state": "blocked", "epoch": 110})
    assert mod.session_report(rec, reports)["state"] == "pushed"


def test_phase_over_follows_each_phase_and_the_tasks_on_origin(render, tmp_path, monkeypatch):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    mod = _load_dispatch(out)

    def over(phase, state):
        return mod.phase_over(out, {"branch": "7-work", "phase": phase}, {"state": state} if state else None)

    assert over("plan", "planned") and over("review", "review-pass") and over("review", "blocked")
    assert over("execute", "done") and over("plan", "idle")
    assert not over("plan", None) and not over("execute", "blocked") and not over("plan", "pushed")
    for done, expected in ((True, True), (False, False), (None, None)):
        monkeypatch.setattr(mod, "work_complete_on_origin", lambda _root, _b, _local=False, d=done: d)
        assert over("execute", "pushed") is expected, done


def test_of_two_reports_in_one_second_the_later_line_wins(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    mod = _load_dispatch(out)
    reports = [{"worker": "7-work", "state": "pushed", "epoch": 150}, {"worker": "7-work", "state": "done", "epoch": 150}]
    assert mod.session_report({"branch": "7-work", "started": 100}, reports)["state"] == "done"


def test_phase_over_reads_the_local_branch_without_origin_and_says_unknown_when_it_cannot_tell(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=out, check=True)
    for k, v in (("user.email", "t@t"), ("user.name", "t")):
        subprocess.run(["git", "config", k, v], cwd=out, check=True)
    subprocess.run(["git", "add", "-A"], cwd=out, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=out, check=True)
    subprocess.run(["git", "update-ref", "refs/remotes/origin/main", "HEAD"], cwd=out, check=True)
    subprocess.run(["git", "checkout", "-q", "-b", "7-work"], cwd=out, check=True)
    plan = out / ".process-work/plans/2026-09-29-work.md"
    plan.parent.mkdir(parents=True, exist_ok=True)
    plan.write_text("# Work\n\ntier: 2\nissue: #7\n\n- [x] one\n- [ ] two\n")
    subprocess.run(["git", "add", "-A"], cwd=out, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "plan"], cwd=out, check=True)
    mod = _load_dispatch(out)
    rec, rep = {"branch": "7-work", "phase": "execute"}, {"state": "pushed"}

    def fetched():  # what `git push` / `git fetch` leave: origin's tip as last seen
        subprocess.run(["git", "update-ref", "refs/remotes/origin/7-work", "HEAD"], cwd=out, check=True)

    assert mod.phase_over(out, rec, rep, local=True) is None  # never pushed: cannot be told
    fetched()
    assert mod.phase_over(out, rec, rep, local=True) is False  # an open task on origin
    plan.write_text(plan.read_text().replace("- [ ] two", "- [x] two"))
    subprocess.run(["git", "commit", "-q", "-am", "done"], cwd=out, check=True)
    # ticked but not pushed: origin still has the open task, as chain sees it
    assert mod.phase_over(out, rec, rep, local=True) is False
    fetched()
    assert mod.phase_over(out, rec, rep, local=True) is True
    assert mod.phase_over(out, rec, rep) is None  # live origin cannot be asked here: unknown


# --- the merge guard's side of dispatch (merge_route.py) ------------------------------

@pytest.mark.parametrize("phase", ["plan", "review"])
@pytest.mark.parametrize("remote", [False, True])
def test_plan_and_review_prompts_forbid_the_push_to_main(render, tmp_path, phase, remote):
    # a supplement, not the enforcement (the pre-push hook is): observed downstream, a
    # review prompt that only said "never fix code" ended with its branch pushed to main
    mod = _load_dispatch(render(tmp_path, {"project_name": "d", "modules": {}}))
    text = mod.prompt_for(phase, 7, 2, "7-work", "m", remote=remote)
    assert "never push to main" in text and "Push only branch `7-work`" in text


def test_the_execute_prompt_keeps_the_merge_tail_open(render, tmp_path):
    mod = _load_dispatch(render(tmp_path, {"project_name": "d", "modules": {}}))
    assert "never push to main" not in mod.prompt_for("execute", 7, 2, "7-work", "m")


def test_a_record_is_replaced_in_one_step(render, tmp_path, monkeypatch):
    # the guard reads the records while a dispatch may be writing one: a half file
    # must never be what it sees, and a failed write leaves the old record whole
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    mod = _load_dispatch(out)
    mod._write_record(out, "7-work", {"branch": "7-work", "phase": "review", "pid": 1})
    folder = out / ".git" / "process-dispatch"
    assert [p.name for p in folder.iterdir()] == ["7-work.json"]

    def broken(*_a, **_k):
        raise OSError("disk full")

    monkeypatch.setattr(mod.os, "replace", broken)
    with pytest.raises(OSError):
        mod._write_record(out, "7-work", {"branch": "7-work", "phase": "execute", "pid": 2})
    assert [p.name for p in folder.iterdir()] == ["7-work.json"]
    assert json.loads((folder / "7-work.json").read_text())["phase"] == "review"


def test_session_pid_is_the_worker_or_the_pane(render, tmp_path, monkeypatch):
    mod = _load_dispatch(render(tmp_path, {"project_name": "d", "modules": {}}))
    assert mod.session_pid({"pid": 4242}) == 4242
    assert mod.session_pid({"remote": True}) == 0
    assert mod.session_pid({"pid": "junk"}) == 0
    monkeypatch.setattr(mod, "_tmux", lambda *a: subprocess.CompletedProcess(a, 0, "777\n", ""))
    assert mod.session_pid({"tmux_window": "@3", "pid": 1}) == 777
    monkeypatch.setattr(mod, "_tmux", lambda *a: subprocess.CompletedProcess(a, 1, "", "gone"))
    assert mod.session_pid({"tmux_window": "@3"}) == 0



@pytest.mark.parametrize("branch, issue, found", [
    ("feat/7-login", 7, True), ("7-login", 7, True), ("issue-7", 7, True),
    ("2026-09-30-login", 2026, False), ("70s-look", 70, False),
])
def test_find_branch_reads_the_issue_as_its_owner_does(render, tmp_path, branch, issue, found):
    """Refute round 2, F3: dispatch read issue numbers from branch names its own way —
    `feat/7-login` was no branch of #7, a dated branch one of #2026."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _git(out, "branch", branch)
    sys.path.insert(0, str(out / "scripts/process"))
    try:
        import importlib

        import dispatch
        importlib.reload(dispatch)
        got = dispatch.find_branch(out, issue)
    finally:
        sys.path.pop(0)
        for m in ("dispatch", "report", "check_review"):
            sys.modules.pop(m, None)

    assert (got == branch) if found else got is None, got


def _usage(pct):
    import collections
    usage = collections.namedtuple("usage", "total used free")
    return usage(100 * 2**30, pct * 2**30, (100 - pct) * 2**30)


@pytest.mark.parametrize("pct,refused", [(95, True), (90, True), (89, False), (40, False)])
def test_a_full_disk_refuses_a_local_start_and_names_the_cleanup(render, tmp_path, monkeypatch, capsys, pct, refused):
    # #136: 111 merged worktrees, each with its own venv, filled the disk and stalled every session
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    _repo(out)
    _fake_command(out, "sleep 30\n")
    d = _load_dispatch(out)
    monkeypatch.delenv(d.DISK_LIMIT_ENV, raising=False)
    seen = []
    monkeypatch.setattr(d.shutil, "disk_usage", lambda p: seen.append(Path(p)) or _usage(pct))
    rc = d.start(out, issue=4, phase="plan", tier=None, branch="b4", title=None, dry_run=True)
    err = capsys.readouterr().err
    assert seen and seen[0] == out.parent  # the filesystem the worktrees go to
    if refused:
        assert rc == 3 and f"{pct}% full" in err and "python3 scripts/process/tidy.py --apply" in err
    else:
        assert rc == 0 and "full" not in err


@pytest.mark.parametrize("value", ["abc", "0", "-5", "150", "nan", "inf"])
def test_a_misconfigured_disk_limit_refuses_naming_it(render, tmp_path, monkeypatch, value):
    d = _load_dispatch(render(tmp_path, {"project_name": "d", "modules": {}}))
    monkeypatch.setattr(d.shutil, "disk_usage", lambda p: _usage(10))
    monkeypatch.setenv(d.DISK_LIMIT_ENV, value)
    why = d.disk_refusal(tmp_path)
    assert why and d.DISK_LIMIT_ENV in why and repr(value) in why


def test_an_unreadable_disk_use_lets_the_start_through_with_a_note(render, tmp_path, monkeypatch, capsys):
    d = _load_dispatch(render(tmp_path, {"project_name": "d", "modules": {}}))
    monkeypatch.delenv(d.DISK_LIMIT_ENV, raising=False)

    def broken(_p):
        raise OSError(5, "I/O error")

    monkeypatch.setattr(d.shutil, "disk_usage", broken)
    assert d.disk_refusal(tmp_path) is None
    err = capsys.readouterr().err
    assert "not checked" in err and "I/O error" in err


def test_the_disk_limit_reaches_the_command_line(render, tmp_path):
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    _repo(out)
    _fake_command(out, "sleep 30\n")
    r = _dispatch(out, "start", "--issue", "4", "--phase", "plan", "--branch", "b4",
                  env={**os.environ, "PROCESS_DISK_LIMIT_PCT": "0.001"})
    assert r.returncode == 3 and "% full (limit 0.001%" in r.stderr and "tidy.py --apply" in r.stderr
    assert not (tmp_path / "repo-b4").exists()  # no worktree, no session


def test_a_task_class_row_wins_over_the_tier_and_the_default(render, tmp_path):
    """A spawn names its model from the class row; the tier and the default
    only fill what the class leaves open (one precedence, one owner)."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    pol = out / "docs/process/model-policy.json"
    data = json.loads(pol.read_text())
    data["classes"] = {"mechanical": {"execute": "small-x"}}
    pol.write_text(json.dumps(data))
    sys.path.insert(0, str(out / "scripts/process"))
    try:
        import importlib
        d = importlib.import_module("dispatch")
        policy = d.load_policy(out)
        assert d.model_for(policy, 3, "execute", "mechanical") == "small-x"
        assert d.cell_for(policy, 3, "review", "mechanical") == ("claude-opus-5", "xhigh", None)
        assert d.model_for(policy, 3, "execute", "standard") == data["tiers"]["3"]["execute"]
        assert d.model_for(policy, 9, "execute") == data["default"]["execute"]
    finally:
        sys.path.remove(str(out / "scripts/process"))
        sys.modules.pop("dispatch", None)
    r = _dispatch(out, "policy", "--tier", "3", "--class", "mechanical")
    assert r.returncode == 0 and "execute: small-x" in r.stdout, r.stdout + r.stderr


def test_an_unknown_task_class_refuses_naming_it(render, tmp_path):
    """A typo in a class must not silently fall back to the tier's model."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    r = _dispatch(out, "policy", "--class", "mechanicl")
    assert r.returncode != 0 and "mechanicl" in r.stdout + r.stderr


def test_a_malformed_classes_block_refuses(render, tmp_path):
    """`classes` is validated like the rest of the policy: phase keys, string models."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    pol = out / "docs/process/model-policy.json"
    data = json.loads(pol.read_text())
    data["classes"] = {"mechanical": {"deploy": "x"}}
    pol.write_text(json.dumps(data))
    r = _dispatch(out, "policy")
    assert r.returncode != 0 and "classes" in r.stdout + r.stderr


# --- effort per cell ------------------------------------------------------------------

def test_an_effort_cell_follows_the_one_precedence_and_wins_whole(render, tmp_path):
    """Class over tier over default, as for models; the winning cell is taken
    whole — a class cell without an effort must not borrow the tier's."""
    d = _load_dispatch(render(tmp_path, {"project_name": "d", "modules": {}}))
    policy = {"default": {"execute": {"model": "dm", "effort": "low"}},
              "tiers": {"3": {"execute": {"model": "tm", "effort": "high"}}},
              "classes": {"mechanical": {"execute": "cm"}}}
    assert d.cell_for(policy, 3, "execute", "mechanical") == ("cm", None, None)
    assert d.cell_for(policy, 3, "execute") == ("tm", "high", None)
    assert d.cell_for(policy, 9, "execute") == ("dm", "low", None)
    assert d.model_for(policy, 3, "execute") == "tm"  # the thin wrapper keeps its callers


@pytest.mark.parametrize("cell", [{"model": "x", "effort": "ultra"}, {"effort": "low"},
                                  {"model": "x", "effort": "low", "speed": 1}, 7],
                         ids=["unknown-level", "no-model", "unknown-key", "not-a-cell"])
def test_a_malformed_cell_refuses_naming_it(render, tmp_path, cell):
    """A typo in an effort must not fall back to the harness default unseen."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    pol = out / "docs/process/model-policy.json"
    data = json.loads(pol.read_text())
    data["tiers"]["2"]["review"] = cell
    pol.write_text(json.dumps(data))
    r = _dispatch(out, "policy")
    assert r.returncode != 0 and "tiers.2.review" in r.stderr, r.stdout + r.stderr


def test_the_effort_element_is_dropped_without_an_effort(render, tmp_path):
    """A cell without an effort leaves the harness default: neither an empty
    `--effort=` nor a dangling flag that would eat the next argument."""
    d = _load_dispatch(render(tmp_path, {"project_name": "d", "modules": {}}))
    policy = {"command": "h --model {model} --effort={effort} -c reason={effort} --x {effort} {prompt}"}
    assert d.build_argv(policy, "m", "P") == ["h", "--model", "m", "P"]
    assert d.build_argv(policy, "m", "P", effort="max") == [
        "h", "--model", "m", "--effort=max", "-c", "reason=max", "--x", "max", "P"]
    # an element that merely contains the effort goes alone; the flag before it stays
    assert d.build_argv({"command": "c --flag {effort}x {prompt}"}, "m", "P") == ["c", "--flag", "P"]
    assert d.build_argv({"command": "c -p --effort={effort} {prompt}"}, "m", "P") == ["c", "-p", "P"]
    assert d.build_argv({"command": "c --a=b {effort} {prompt}"}, "m", "P") == ["c", "--a=b", "P"]


def test_an_effort_the_command_cannot_carry_refuses_the_start(render, tmp_path):
    """An effort set in the policy but never passed would be silently ignored:
    the start refuses and `policy` flags the cell."""
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    _repo(out)
    _fake_command(out, "exit 0\n")  # `--model {model} {prompt}`: no {effort}
    r = _dispatch(out, "start", "--issue", "3", "--phase", "review", "--tier", "3", "--dry-run")
    assert r.returncode == 3 and "{effort}" in r.stderr, r.stdout + r.stderr
    r = _dispatch(out, "start", "--issue", "3", "--phase", "plan", "--tier", "3", "--dry-run")
    assert r.returncode == 0, r.stderr  # a cell without effort still starts
    r = _dispatch(out, "policy", "--tier", "3")
    assert r.returncode == 0 and "review: claude-opus-5 (xhigh)  WARNING" in r.stdout, r.stdout


def test_a_worker_gets_its_cells_effort(render, tmp_path):
    """PROCESS_EFFORT lets report.py record the effort; a cell without one sets
    it empty, so a value from the steward's own environment cannot leak in."""
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    _repo(out)
    marker = tmp_path / "seen"
    _fake_command(out, f'echo "$* effort=$PROCESS_EFFORT" >> {marker}\n')
    pol = out / "docs/process/model-policy.json"
    data = json.loads(pol.read_text())
    data["command"] = data["command"].replace("{prompt}", "--effort={effort} {prompt}")
    data["tiers"]["2"]["plan"] = {"model": "m2", "effort": "high"}
    pol.write_text(json.dumps(data))
    env = {**os.environ, "PROCESS_EFFORT": "stale"}
    r = _dispatch(out, "start", "--issue", "7", "--phase", "plan", "--tier", "2", env=env)
    assert r.returncode == 0 and "with m2 (high)" in r.stdout, r.stdout + r.stderr
    r = _dispatch(out, "start", "--issue", "8", "--phase", "plan", "--tier", "1", env=env)
    assert r.returncode == 0, r.stderr
    deadline = time.time() + 10
    while time.time() < deadline and (not marker.exists() or len(marker.read_text().splitlines()) < 2):
        time.sleep(0.1)
    lines = sorted(marker.read_text().splitlines(), key=lambda s: "m2" not in s)
    assert "--model m2 --effort=high" in lines[0] and lines[0].endswith("effort=high")
    assert "--effort" not in lines[1] and lines[1].endswith("effort=")


def test_a_cell_command_wins_over_the_phase_and_the_top_level_command(render, tmp_path):
    """A second family is one cell: its own CLI, while the phase keeps its
    runner and host — and {effort} is substituted in it like anywhere."""
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    _repo(out)
    pol = out / "docs/process/model-policy.json"
    data = json.loads(pol.read_text())
    data["phases"] = {"review": {"command": "phase-cli --model {model} {prompt}"}}
    data["tiers"]["3"]["review"] = {"model": "other-1", "effort": "minimal",
                                    "command": "sh -c true --model {model} -c reasoning={effort} {prompt}"}
    pol.write_text(json.dumps(data))
    r = _dispatch(out, "start", "--issue", "3", "--phase", "review", "--tier", "3", "--dry-run")
    assert r.returncode == 0, r.stderr
    assert "with other-1 (minimal)" in r.stdout and "'reasoning=minimal'" in r.stdout and "phase-cli" not in r.stdout
    r = _dispatch(out, "start", "--issue", "3", "--phase", "review", "--tier", "2", "--dry-run")
    assert "phase-cli" in r.stdout  # a plain cell keeps the phase's command
    r = _dispatch(out, "policy", "--tier", "3")
    assert "review: other-1 (minimal)  via `sh -c true" in r.stdout and "WARNING" not in r.stdout, r.stdout


@pytest.mark.parametrize("command", ["cli {prompt}", "cli --model {model}", 7], ids=["no-model", "no-prompt", "not-a-string"])
def test_a_cell_command_without_model_or_prompt_refuses_naming_the_cell(render, tmp_path, command):
    """A cell command that cannot carry the model or the prompt would start
    the wrong session or none — refused like the top-level command."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    pol = out / "docs/process/model-policy.json"
    data = json.loads(pol.read_text())
    data["tiers"]["3"]["review"] = {"model": "x", "command": command}
    pol.write_text(json.dumps(data))
    r = _dispatch(out, "policy")
    assert r.returncode != 0 and "tiers.3.review.command" in r.stderr, r.stdout + r.stderr


@pytest.mark.parametrize("key", ["model", "effort"])
def test_a_phase_command_file_that_overrides_the_model_refuses_the_start(render, tmp_path, key):
    """Kenni #2317: `model:` frontmatter on a command silently replaced the
    dispatched model; `effort:` would do the same to the cell's effort."""
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    _repo(out)
    cmd = out / ".claude/commands/plan.md"
    cmd.write_text(f"---\ndescription: plan\n{key}: haiku\n---\n" + cmd.read_text())
    _git(out, "commit", "-qam", "override")  # the worker sees the committed file
    r = _dispatch(out, "start", "--issue", "3", "--phase", "plan", "--tier", "2", "--dry-run")
    assert r.returncode == 3 and "one owner for the model" in r.stderr and f"{key}:" in r.stderr, r.stderr
    r = _dispatch(out, "start", "--issue", "3", "--phase", "execute", "--tier", "2", "--dry-run")
    assert r.returncode == 0, r.stderr  # only the phase's own file counts


@pytest.mark.parametrize("harness", ["claude", "copilot", "agents_md"])
def test_no_rendered_command_or_skill_declares_model_or_effort(render_raw, tmp_path, harness):
    """The policy is the one owner of model and effort: a rendered command,
    prompt or skill file with such frontmatter would override every dispatch."""
    out = render_raw(tmp_path, {"project_name": "d", "harness": harness})
    d = _load_dispatch(out)
    files = [p for p in out.rglob("*.md") if {"commands", "prompts", "skills"} & set(p.relative_to(out).parts)]
    assert files or harness == "agents_md"
    assert not [(str(p.relative_to(out)), d.frontmatter_overrides(p.read_text())) for p in files
                if d.frontmatter_overrides(p.read_text()) != []]


def _transcript(path: Path, *models: str, started: float = 0, sidechain: str = "") -> None:
    import datetime
    ts = datetime.datetime.fromtimestamp(started + 5, datetime.timezone.utc).isoformat()
    lines = [json.dumps({"type": "assistant", "timestamp": ts, "message": {"model": m}}) for m in models]
    if sidechain:
        lines.append(json.dumps({"type": "assistant", "isSidechain": True, "timestamp": ts,
                                 "message": {"model": sidechain}}))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")


def test_model_drift_reads_the_sessions_own_assistant_messages(render, tmp_path):
    """A dated id is the dispatched alias; a subagent (sidechain) on another
    model is a choice, not drift; without `transcripts` nothing is read."""
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    d = _load_dispatch(out)
    wt = tmp_path / "wt"
    rec = {"model": "claude-opus-5", "worktree": str(wt), "started": time.time() - 60}
    _transcript(tmp_path / "t" / "wt" / "a.jsonl", "claude-opus-5-20261001", "<synthetic>",
                started=rec["started"], sidechain="claude-sonnet-5")
    pattern = str(tmp_path / "t" / "*" / "*.jsonl")
    assert d.model_drift(out, rec) == []  # no transcripts glob in the policy
    assert d.model_drift(out, rec, pattern) == []
    _transcript(tmp_path / "t" / "wt" / "b.jsonl", "claude-haiku-5", started=rec["started"])
    assert d.model_drift(out, rec, pattern) == ["claude-haiku-5"]
    # an earlier phase's transcript in the same worktree is not this session's
    assert d.model_drift(out, {**rec, "started": time.time() + 3600}, pattern) == []


def test_the_tower_reports_model_drift_only_with_transcripts(render, tmp_path):
    """Visible drift where the harness's transcripts are configured; no new
    noise where they are not."""
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    _repo(out)
    _fake_command(out, "sleep 30\n")
    r = _dispatch(out, "start", "--issue", "7", "--phase", "plan", "--tier", "2", "--branch", "b7")
    assert r.returncode == 0, r.stderr
    rec = next(x for x in _load_dispatch(out).records(out) if x["branch"] == "b7")
    # the harness keeps transcripts per working directory: `{worktree}` names it
    _transcript(Path(str(tmp_path / "t") + rec["worktree"]) / "s.jsonl", "claude-haiku-5", started=rec["started"])

    def tower():
        r = subprocess.run([sys.executable, str(out / "scripts/process/tower.py"), "--json", "--section", "findings"],
                           cwd=out, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        return [f for f in json.loads(r.stdout)["findings"] if f["kind"] == "model-drift"]

    try:
        assert tower() == []
        pol = out / "docs/process/model-policy.json"
        data = json.loads(pol.read_text())
        data["transcripts"] = str(tmp_path / "t") + "{worktree}/*.jsonl"
        pol.write_text(json.dumps(data))
        drift = tower()
        assert len(drift) == 1 and "claude-opus-5" in drift[0]["what"] and "claude-haiku-5" in drift[0]["what"], drift
        assert drift[0]["severity"] == "high"
    finally:
        _dispatch(out, "stop", "b7", "--force")


@pytest.mark.parametrize(("text", "keys"), [
    ("---\nmodel: inherit\neffort: 'inherit'\n---\nbody", []),
    ("# Title\n\n---\nmodel: haiku\n---\n", []),
    ("---\nmodel: haiku\n", []),
    ("\ufeff---\n\"model\": x\n---\n", ["model"]),
    ("---\r\neffort: low\r\n---\r\n", ["effort"]),
    ("---\nModel: x\ndescription: plan\n---\n", []),
    ("---\nmodel: inherit # the policy owns it\n---\n", []),
    ("---\r\n# owner: policy\r\nmodel: inherit  # c\r\n---\r\n", []),
    ("---\n\"model\": \"inherit\"\n---\n", []),
    ("---\nmodel: 'haiku' # c\n---\n", ["model"]),
    # #173/#174: what a strict reader cannot decide is no "no override"
    ("---\ndescription: x\n  model: nested\n---\n", None),
    ("---\n{model: haiku}\n---\n", None),
    ("---\nmodel:inherit\n---\n", None),
    ("---\n[model, haiku]\n---\n", None),
    ("---\n\tmodel: haiku\n---\n", None),
    ("---\ndescription: x\n...\nmodel: haiku\n---\n", None),
    ("---\ndescription: model: haiku\n---\n", None),
    ("---\nmodel: \"haiku\n---\n", None),
], ids=["inherit", "horizontal-rule", "unclosed", "bom-quoted-key", "crlf", "other-case",
        "inherit-comment", "crlf-comment", "quoted-inherit", "quoted-comment", "nested", "flow-mapping",
        "no-space", "flow-sequence", "tab-indent", "document-marker", "in-a-value", "unclosed-quote"])
def test_only_a_real_frontmatter_override_counts(render, tmp_path, text, keys):
    """`inherit` defers to the dispatched model, and a `---` rule in a body
    is no header — refusing those would block a correct start; a header the
    strict reader cannot decide that mentions model/effort is None (refused)."""
    d = _load_dispatch(render(tmp_path, {"project_name": "d", "modules": {}}))
    assert d.frontmatter_overrides(text) == keys


def test_the_override_check_reads_the_workers_branch_and_harness(render, tmp_path):
    """The worker runs the branch tip, not the steward's checkout; a Codex
    command never reads Claude's command file."""
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    _repo(out)
    cmd = out / ".claude/commands/plan.md"
    clean = cmd.read_text()
    cmd.write_text("---\nmodel: haiku\n---\n" + clean)
    _git(out, "commit", "-qam", "override on main")
    _git(out, "checkout", "-qb", "b5")
    cmd.write_text(clean)
    _git(out, "commit", "-qam", "clean on the branch")
    _git(out, "checkout", "-q", "main")
    start = ("start", "--issue", "5", "--phase", "plan", "--tier", "2", "--dry-run")
    r = _dispatch(out, *start, "--branch", "b5")
    assert r.returncode == 0, r.stderr  # the branch decides
    r = _dispatch(out, *start, "--branch", "b6")
    assert r.returncode == 3 and "one owner" in r.stderr  # a new branch starts from main
    pol = out / "docs/process/model-policy.json"
    data = json.loads(pol.read_text())
    data["command"] = "codex exec --model {model} {prompt}"
    pol.write_text(json.dumps(data))
    r = _dispatch(out, *start, "--branch", "b6")
    assert r.returncode == 0, r.stderr


def test_a_header_that_cannot_be_decided_refuses_the_start(render, tmp_path):
    """#173: `{model: haiku}` slipped past the line pattern as no override."""
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    _repo(out)
    cmd = out / ".claude/commands/plan.md"
    cmd.write_text("---\n{model: haiku}\n---\n" + cmd.read_text())
    _git(out, "commit", "-qam", "flow")
    r = _dispatch(out, "start", "--issue", "3", "--phase", "plan", "--tier", "2", "--dry-run")
    assert r.returncode == 3 and "cannot be parsed strictly" in r.stderr, r.stderr


def test_an_existing_worktree_is_checked_on_disk(render, tmp_path):
    """#174: the worker runs the worktree's working copy, not the committed file."""
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    _repo(out)
    cmd = out / ".claude/commands/plan.md"
    cmd.write_text("---\nmodel: inherit\n---\n" + cmd.read_text())
    _git(out, "commit", "-qam", "inherit")
    wt = tmp_path / "wt-b8"
    _git(out, "worktree", "add", "-q", "-b", "b8", str(wt))
    start = ("start", "--issue", "8", "--phase", "plan", "--tier", "2", "--branch", "b8", "--dry-run")
    assert _dispatch(out, *start).returncode == 0
    local = wt / ".claude/commands/plan.md"
    local.write_text(local.read_text().replace("model: inherit", "model: haiku"))
    r = _dispatch(out, *start)
    assert r.returncode == 3 and "declares model:" in r.stderr, r.stderr
    local.unlink()
    assert _dispatch(out, *start).returncode == 0  # absent: nothing overrides


def test_an_unreadable_command_blob_refuses_the_start(render, tmp_path):
    """#174: a blob git cannot show was read as "no override"."""
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    _repo(out)
    cmd = out / ".claude/commands/plan.md"
    cmd.write_text("---\nmodel: inherit\n---\nunique body 7f3a\n")
    _git(out, "commit", "-qam", "inherit")
    blob = _git(out, "rev-parse", "HEAD:.claude/commands/plan.md").stdout.strip()
    obj = out / ".git/objects" / blob[:2] / blob[2:]
    obj.chmod(0o644)
    obj.write_bytes(b"corrupt")
    r = _dispatch(out, "start", "--issue", "3", "--phase", "plan", "--tier", "2", "--dry-run")
    assert r.returncode == 3 and "unreadable" in r.stderr, r.stderr


@pytest.mark.parametrize(("seen", "dispatched", "same"), [
    ("claude-opus-5-20261001", "claude-opus-5", True),
    ("claude-opus-5[1m]", "claude-opus-5", True),
    ("claude-opus-5", "claude-opus-5[1m]", True),
    ("claude-opus-5-5", "claude-opus-5", False),
    ("claude-opus-5-5", "opus", True),
    ("claude-sonnet-5", "opus", False),
    ("anthropic.claude-haiku-5-v1", "haiku", True),
])
def test_same_model_normalises_suffixes_and_aliases(render, tmp_path, seen, dispatched, same):
    """A context suffix, a date, or a family alias is the same dispatch, not drift."""
    d = _load_dispatch(render(tmp_path, {"project_name": "d", "modules": {}}))
    assert d._same_model(seen, dispatched) is same


def test_model_drift_reads_each_transcript_once(render, tmp_path):
    """The tower asks per session; a large transcript is parsed once per version."""
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    d = _load_dispatch(out)
    rec = {"model": "claude-opus-5", "worktree": str(tmp_path / "wt"), "started": time.time() - 60}
    f = tmp_path / "t" / "wt" / "a.jsonl"
    _transcript(f, "claude-opus-5", started=rec["started"])
    pattern = str(tmp_path / "t" / "*" / "*.jsonl")
    assert d.model_drift(out, rec, pattern) == []
    (key,) = [k for k in d._TRANSCRIPTS if k[0] == str(f)]
    d._TRANSCRIPTS[key] = [(math.inf, "from-the-cache")]
    assert d.model_drift(out, rec, pattern) == ["from-the-cache"]


def test_report_validates_the_effort_against_dispatchs_levels(render, tmp_path):
    """A typo must not become a KPI cell: the flag refuses, the env is noted and dropped."""
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    _repo(out)
    cli = [sys.executable, str(out / "scripts/process/report.py"), "idle", "--model", "m"]
    r = subprocess.run([*cli, "--effort", "turbo"], cwd=out, capture_output=True, text=True)
    assert r.returncode == 2 and "turbo" in r.stderr
    r = subprocess.run(cli, cwd=out, capture_output=True, text=True, env={**os.environ, "PROCESS_EFFORT": "turbo"})
    assert r.returncode == 0 and "PROCESS_EFFORT" in r.stderr, r.stderr
    r = subprocess.run([*cli, "--effort", "minimal"], cwd=out, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    recs = [json.loads(x) for x in (out / ".git/process-tower/reports.jsonl").read_text().splitlines()]
    assert "effort" not in recs[0] and recs[1]["effort"] == "minimal"


def test_drift_from_an_unversioned_alias_is_low(render, tmp_path):
    """An alias lets the harness pick the version: another member of the family
    is no drift, another family is worth a look but no alarm."""
    import importlib.util
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    sys.path.insert(0, str(out / "scripts/process"))
    try:
        spec = importlib.util.spec_from_file_location("tower_under_test", out / "scripts/process/tower.py")
        tower = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tower)
    finally:
        sys.path.remove(str(out / "scripts/process"))
    table = {"overlaps": [], "plans": [], "gates": [], "worktrees": [], "reports": [],
             "sessions": [{"branch": "b", "phase": "plan", "model": m, "model_drift": ["claude-sonnet-5"],
                           "model_alias": alias, "alive": False, "state": "dead", "report_state": "done"}
                          for m, alias in (("opus", True), ("claude-opus-5", False))]}
    drift = [f["severity"] for f in tower.findings(table, 60) if f["kind"] == "model-drift"]
    assert sorted(drift) == ["high", "low"]
