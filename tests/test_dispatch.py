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


def _fake_lane(out: Path, status: str) -> None:
    # the project's own lane tool: one status line per lane, like Kenni's scripts/lane.py
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
    cloud.write_text(f'#!/bin/sh\nprintf "%s|%s|%s|%s" "$1" "$2" "$3" "$PROCESS_PHASE" > {marker}\necho session-abc\n')
    cloud.chmod(0o755)
    local = out.parent / "local.sh"
    local.write_text("#!/bin/sh\nsleep 30\n")
    local.chmod(0o755)
    data["command"] = f"{local} {{prompt}}"
    data["phases"] = {"review": {"command": f"{cloud} {{branch}} {{model}} {{prompt}}", "remote": True}}
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
    assert seen[0] == "b4" and seen[1] == "claude-fable-5-1" and seen[3] == "review"
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
    # #2110: worker sessions run built-in subagents on a cheaper model; the
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
    assert r.returncode == 0 and "would start review for #3" in r.stdout and "claude-fable-5-1" in r.stdout
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
