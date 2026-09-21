#!/usr/bin/env python3
"""dispatch — start, list and stop worker sessions per phase, with the model
the policy assigns.

    uv run scripts/process/dispatch.py start --issue N --phase plan|execute|review [--tier T] [--branch B] [--title "..."]
    uv run scripts/process/dispatch.py list
    uv run scripts/process/dispatch.py stop <branch> [--force]
    uv run scripts/process/dispatch.py policy [--tier T]        # what would run

A phase is a session: `plan` opens a worktree on a fresh branch (or reuses
the branch's worktree) and starts the planning session; `execute` starts
the build session in that worktree; `review` starts a fresh reviewing
session there. Between phases the artifacts carry the state (the plan and
its `## Decisions` ledger, the bundle) — the model may change, the
worktree stays. Which model runs which phase comes from
`docs/process/model-policy.json` (tier × phase); the project's own start
command is the `command` template there, `{model}` and `{prompt}`
substituted, the prompt passed as ONE argument (never through a shell).

The child runs detached (own session, stdout+stderr to a log), so it
survives the steward's own tool timeouts. `<git common dir>/process-
dispatch/<branch>.json` records pid, phase, model, log, start time; `list`
shows them with liveness, `stop` sends SIGTERM to a child this tool
started — and refuses while the branch has uncommitted work unless
`--force`, because a plan and its decisions that are not committed are
lost with the process. `max_workers` (policy) caps concurrent live
children on this host; a busy lane counts as no free CPU.

The dispatcher decides nothing about the work: it passes the issue, the
tier and the phase command to the session, and reports `idle` when it
stops one. Stdlib only."""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling imports
import report as _report  # noqa: E402

POLICY = "docs/process/model-policy.json"
DISPATCH_DIR = "process-dispatch"
PHASES = ("plan", "execute", "review")
PHASE_COMMAND = {"plan": "/plan", "execute": "/execute", "review": "/review"}


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=120)


def _out(root: Path, *args: str) -> str:
    r = _git(root, *args)
    return r.stdout.strip() if r.returncode == 0 else ""


def common_dir(root: Path) -> Path:
    c = Path(_out(root, "rev-parse", "--git-common-dir") or ".git")
    return c if c.is_absolute() else root / c


def load_policy(root: Path) -> dict:
    p = root / POLICY
    if not p.is_file():
        raise SystemExit(f"dispatch: {POLICY} missing — the policy is the one place that names models")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise SystemExit(f"dispatch: {POLICY} is not valid JSON: {exc}")
    if not isinstance(data.get("command"), str) or "{prompt}" not in data["command"]:
        raise SystemExit(f"dispatch: {POLICY} needs a `command` template containing {{prompt}}")
    return data


def model_for(policy: dict, tier: int | None, phase: str) -> str:
    tiers = policy.get("tiers") or {}
    table = tiers.get(str(tier)) if tier is not None else None
    table = table or policy.get("default") or {}
    model = table.get(phase)
    if not model:
        raise SystemExit(f"dispatch: policy names no model for tier {tier} phase {phase}")
    return str(model)


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:40] or "work"


def default_branch(issue: int, title: str | None) -> str:
    return f"{issue}-{_slug(title)}" if title else f"issue-{issue}"


def find_branch(root: Path, issue: int) -> str | None:
    """The branch an issue already lives on: a dispatch record first, then a
    local branch named `<issue>-…` or `issue-<issue>` — so `--phase execute`
    after `--phase plan` lands in the same worktree without repeating the name."""
    for rec in records(root):
        if rec.get("issue") == issue:
            return rec["branch"]
    for b in _out(root, "branch", "--list", "--format=%(refname:short)").splitlines():
        b = b.strip()
        if b == f"issue-{issue}" or b.startswith(f"{issue}-"):
            return b
    return None


def worktree_for(root: Path, branch: str) -> Path:
    for line in (_out(root, "worktree", "list", "--porcelain")).splitlines():
        if line.startswith("worktree "):
            cur = Path(line[len("worktree "):])
        elif line == f"branch refs/heads/{branch}":
            return cur
    return root.parent / f"{root.name}-{branch.replace('/', '-')}"


def ensure_worktree(root: Path, branch: str) -> Path:
    wt = worktree_for(root, branch)
    if wt.is_dir():
        return wt
    base = "origin/main" if _git(root, "rev-parse", "--verify", "--quiet", "origin/main").returncode == 0 else "main"
    exists = _git(root, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}").returncode == 0
    args = ["worktree", "add", "-q", str(wt), branch] if exists else ["worktree", "add", "-q", "-b", branch, str(wt), base]
    r = _git(root, *args)
    if r.returncode != 0:
        raise SystemExit(f"dispatch: cannot add worktree for {branch}:\n{r.stderr.strip()}")
    return wt


def prompt_for(phase: str, issue: int, tier: int | None, branch: str, model: str) -> str:
    tier_s = f"tier {tier}" if tier is not None else "tier: derive it from the scope (risk-tiers.md)"
    common = (f"You are the {phase} session for issue #{issue} on branch `{branch}` ({tier_s}), "
              f"running as {model}. Work only in this worktree. Report every state transition with "
              f"`uv run scripts/process/report.py <state> --issue {issue} --model {model}` (/report). ")
    if phase == "plan":
        return common + (f"Run {PHASE_COMMAND['plan']} for issue #{issue}: read the issue, derive the tier, "
                         "write the plan with its `## Decisions` ledger, commit it, report `planned`, then stop. "
                         "Do not implement.")
    if phase == "execute":
        return common + (f"Run {PHASE_COMMAND['execute']}: build the committed plan task by task, test-driven, "
                         "report `pushed` at the first push and `blocked` the moment you cannot proceed. "
                         "A decision the plan does not cover goes back to the planner (mandatory rule 4) — "
                         "do not decide it yourself. Stop after the last task is committed and pushed.")
    return common + (f"Run {PHASE_COMMAND['review']} as an independent reviewer of this branch: build the "
                     "bundle, judge it against the checklist, attest the REVIEW line with attest.py, report "
                     "`review-pass` or `blocked` with the findings, then stop. Never fix the code yourself.")


def _records_dir(root: Path) -> Path:
    d = common_dir(root) / DISPATCH_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def _record_path(root: Path, branch: str) -> Path:
    return _records_dir(root) / (branch.replace("/", "__") + ".json")


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def records(root: Path) -> list[dict]:
    out = []
    for p in sorted(_records_dir(root).glob("*.json")):
        try:
            rec = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            continue
        rec["alive"] = _alive(int(rec.get("pid") or 0))
        out.append(rec)
    return out


def live_children(root: Path) -> list[dict]:
    return [r for r in records(root) if r["alive"]]


def lanes_busy(root: Path) -> bool:
    lane = root / "scripts" / "lane.py"
    if not lane.is_file():
        return False
    try:
        r = subprocess.run([sys.executable, str(lane), "status"], cwd=root, capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return "held by" in r.stdout


def start(root: Path, *, issue: int, phase: str, tier: int | None, branch: str | None, title: str | None,
          dry_run: bool) -> int:
    policy = load_policy(root)
    model = model_for(policy, tier, phase)
    branch = branch or find_branch(root, issue) or default_branch(issue, title)
    live = live_children(root)
    cap = int(policy.get("max_workers") or 4)
    if any(r["branch"] == branch for r in live):
        print(f"dispatch: {branch} already has a live session (pid {[r['pid'] for r in live if r['branch'] == branch][0]}) — stop it first", file=sys.stderr)
        return 3
    if len(live) >= cap:
        print(f"dispatch: {len(live)} live sessions, policy max_workers={cap} — not starting", file=sys.stderr)
        return 3
    if lanes_busy(root):
        print("dispatch: a test lane is held — no free CPU for a new session; retry when lane-status says free",
              file=sys.stderr)
        return 3
    prompt = prompt_for(phase, issue, tier, branch, model)
    argv = [prompt if a == "{prompt}" else a.replace("{model}", model) for a in shlex.split(policy["command"])]
    if dry_run:
        shown = [a if a != prompt else f"<prompt {len(prompt)} chars>" for a in argv]
        print(f"dispatch: would start {phase} for #{issue} on {branch} with {model}:\n  {shown}")
        return 0
    wt = ensure_worktree(root, branch)
    log = _records_dir(root) / f"{branch.replace('/', '__')}-{phase}-{_dt.datetime.now():%Y%m%d-%H%M%S}.log"
    env = dict(os.environ, PROCESS_WORKER=branch, PROCESS_PHASE=phase, PROCESS_MODEL=model,
               PROCESS_ISSUE=str(issue))
    with log.open("ab") as fh:
        try:
            proc = subprocess.Popen(argv, cwd=wt, stdin=subprocess.DEVNULL, stdout=fh, stderr=subprocess.STDOUT,
                                    env=env, start_new_session=True)
        except OSError as exc:
            print(f"dispatch: cannot start {argv[0]!r}: {exc} — fix `command` in {POLICY}", file=sys.stderr)
            return 1
    rec = {"branch": branch, "issue": issue, "phase": phase, "tier": tier, "model": model, "pid": proc.pid,
           "worktree": str(wt), "log": str(log), "started": int(time.time()),
           "ts": _dt.datetime.now().isoformat(timespec="seconds")}
    _record_path(root, branch).write_text(json.dumps(rec, indent=2), encoding="utf-8")
    print(f"dispatch: started {phase} for #{issue} on {branch} with {model} (pid {proc.pid}, log {log.name})")
    return 0


def list_sessions(root: Path) -> int:
    recs = records(root)
    if not recs:
        print("dispatch: no sessions started from this clone")
        return 0
    now = time.time()
    for r in recs:
        mins = int((now - int(r.get("started") or now)) // 60)
        print(f"- {r['branch']}: {r['phase']} #{r.get('issue')} {r.get('model')} pid {r.get('pid')} "
              f"{'LIVE' if r['alive'] else 'ended'} ({mins} min) — {Path(r.get('log', '')).name}")
    return 0


def stop(root: Path, branch: str, *, force: bool) -> int:
    p = _record_path(root, branch)
    if not p.is_file():
        print(f"dispatch: {branch} was not started by this tool — stop only what you started", file=sys.stderr)
        return 2
    rec = json.loads(p.read_text(encoding="utf-8"))
    pid = int(rec.get("pid") or 0)
    if not _alive(pid):
        print(f"dispatch: {branch} (pid {pid}) is not running")
        p.unlink()
        return 0
    wt = Path(rec.get("worktree") or "")
    dirty = _out(wt, "status", "--porcelain", "--untracked-files=no") if wt.is_dir() else ""
    if dirty and not force:
        print(f"dispatch: {branch} has uncommitted work ({len(dirty.splitlines())} file(s)) — a plan or decisions "
              "not committed die with the process; ask the worker to commit, or --force", file=sys.stderr)
        return 3
    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        os.kill(pid, signal.SIGTERM)
    for _ in range(50):
        if not _alive(pid):
            break
        time.sleep(0.2)
    else:
        os.kill(pid, signal.SIGKILL)
    try:
        _report.write_report(root, "idle", issue=rec.get("issue"), note=f"stopped by dispatch ({rec.get('phase')})",
                             worker=branch)
    except SystemExit:
        pass
    p.unlink()
    print(f"dispatch: stopped {branch} (pid {pid})")
    return 0


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="dispatch.py", description=__doc__.split("\n\n")[0])
    p.add_argument("--root", default=".")
    sub = p.add_subparsers(dest="command", required=True)
    s = sub.add_parser("start")
    s.add_argument("--issue", type=int, required=True)
    s.add_argument("--phase", choices=PHASES, required=True)
    s.add_argument("--tier", type=int)
    s.add_argument("--branch")
    s.add_argument("--title", help="slug source for a new branch name")
    s.add_argument("--dry-run", action="store_true")
    sub.add_parser("list")
    st = sub.add_parser("stop")
    st.add_argument("branch")
    st.add_argument("--force", action="store_true")
    po = sub.add_parser("policy")
    po.add_argument("--tier", type=int)
    a = p.parse_args(argv)
    root = Path(_out(Path(a.root).resolve(), "rev-parse", "--show-toplevel") or a.root).resolve()
    if a.command == "start":
        return start(root, issue=a.issue, phase=a.phase, tier=a.tier, branch=a.branch, title=a.title,
                     dry_run=a.dry_run)
    if a.command == "list":
        return list_sessions(root)
    if a.command == "stop":
        return stop(root, a.branch, force=a.force)
    policy = load_policy(root)
    for ph in PHASES:
        print(f"{ph}: {model_for(policy, a.tier, ph)}")
    print(f"command: {policy['command']}  (max_workers {policy.get('max_workers', 4)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
