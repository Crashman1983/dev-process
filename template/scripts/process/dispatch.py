#!/usr/bin/env python3
"""dispatch — start, list, watch, message and stop worker sessions per
phase, with the model the policy assigns.

    uv run scripts/process/dispatch.py start --issue N --phase plan|execute|review [--tier T] [--branch B] [--title "..."]
    uv run scripts/process/dispatch.py list
    uv run scripts/process/dispatch.py log <branch> [--lines N]   # what the worker shows right now
    uv run scripts/process/dispatch.py say <branch> "<text>"      # a line into an interactive worker
    uv run scripts/process/dispatch.py stop <branch> [--force]
    uv run scripts/process/dispatch.py policy [--tier T]          # what would run

A phase is a session: `plan` opens a worktree on a fresh branch (or reuses
the issue's branch) and starts the planning session; `execute` starts the
build session in that worktree; `review` a fresh reviewing session there.
Between phases the artifacts carry the state (the plan and its `##
Decisions` ledger, the bundle) — the model may change, the worktree stays.
Which model runs which phase comes from `docs/process/model-policy.json`
(tier × phase); the project's own start command is the `command` template
there. `{model}` and `{prompt}` are substituted inside the argv the
template splits into; the prompt is one argv element.

Two runners (policy `runner`): `detached` starts the argv headless (own
session, output to a log). `tmux` starts it as a window of one tmux
session (policy `tmux_session`) so a human can open it: the window runs
a non-interactive `sh` that waits a second (the log pipe attaches
meanwhile) and `exec`s the argv with exact POSIX quoting — no aliases, no
rc files, no history; `remain-on-exit` keeps a finished worker's last
screen. Liveness is the pane's own state (`pane_dead`), never a shell
pid. `log` shows the live screen of a tmux worker (escape codes are not
the worker's words) and the log tail of a detached one; `say` types a
line into a tmux worker.

Records live in `<git common dir>/process-dispatch/`: one JSON per
branch (pid + process start time, tmux window id, phase, model, log) and
`issues.json` (issue → branch, so the next phase finds the branch after
a stop). `stop` acts only on what this tool started, only when the
recorded process is the recorded one (pid + start time; never pid 0), and
refuses while the worktree has uncommitted or untracked work unless
`--force` — a plan not committed dies with the process. `max_workers`
caps live children on this host; a held lane counts as no free CPU —
a held full lane blocks only execute, a held scoped (or unknown) lane
blocks every phase, and a remote phase sees neither cap nor lane.

Trust boundary, plainly: the policy's `command` is executed on the
machine that runs dispatch. It is a repository file — whoever can merge
to it can run code here. Treat it like CI configuration.

The dispatcher decides nothing about the work. Stdlib only."""
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
ISSUES_FILE = "issues.json"
PHASES = ("plan", "execute", "review")
STRIP_ENV_PREFIXES = ("CLAUDECODE", "CLAUDE_CODE_")  # a nested session must not inherit the steward's identity
_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b[()][A-Z0-9]|\x1b[=>]|\r")


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(args, 127, "", str(exc))


def _out(root: Path, *args: str) -> str:
    r = _git(root, *args)
    return r.stdout.strip() if r.returncode == 0 else ""


def common_dir(root: Path) -> Path:
    c = Path(_out(root, "rev-parse", "--git-common-dir") or ".git")
    return c if c.is_absolute() else root / c


# --- policy -------------------------------------------------------------------------

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
    for ph, row in (data.get("phases") or {}).items():
        if ph not in PHASES or not isinstance(row, dict):
            raise SystemExit(f"dispatch: {POLICY} `phases` keys must be plan|execute|review with an object each")
        if "command" in row and (not isinstance(row["command"], str) or "{prompt}" not in row["command"]):
            raise SystemExit(f"dispatch: {POLICY} phases.{ph}.command must contain {{prompt}}")
    return data


def phase_policy(policy: dict, phase: str) -> dict:
    """The command, runner and host for ONE phase: `phases.<phase>` overrides
    the top-level `command`/`runner`; `remote: true` says the session runs on
    another host (a cloud session, another machine) — no local worktree, no
    local liveness, reports come back through origin (`report.py --sync`)."""
    row = (policy.get("phases") or {}).get(phase) or {}
    return {"command": row.get("command") or policy["command"],
            "runner": str(row.get("runner") or policy.get("runner") or "detached"),
            "remote": bool(row.get("remote", False))}


def model_for(policy: dict, tier: int | None, phase: str) -> str:
    tiers = policy.get("tiers") or {}
    row = (tiers.get(str(tier)) if tier is not None else None) or {}
    model = row.get(phase) or (policy.get("default") or {}).get(phase)  # per-phase fallback
    if not model:
        raise SystemExit(f"dispatch: policy names no model for tier {tier} phase {phase}")
    return str(model)


def max_workers(policy: dict) -> int:
    try:
        n = int(policy.get("max_workers", 4))
    except (TypeError, ValueError):
        raise SystemExit(f"dispatch: max_workers must be an integer, got {policy.get('max_workers')!r}")
    return n if n > 0 else 4


def build_argv(policy: dict, model: str, prompt: str, branch: str = "", issue: int | None = None,
               phase: str | None = None) -> list[str]:
    # {branch}/{issue} name the session for a harness that labels sessions
    # (e.g. `--remote-control={branch}` — the `=` form, or the flag eats the prompt)
    subs = {"{model}": model, "{prompt}": prompt, "{branch}": branch, "{issue}": str(issue or "")}
    command = phase_policy(policy, phase)["command"] if phase else policy["command"]
    out = []
    for a in shlex.split(command):
        for k, v in subs.items():
            a = a.replace(k, v)
        out.append(a)
    return out


# --- branches and worktrees --------------------------------------------------------

def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:40] or "work"


def default_branch(issue: int, title: str | None) -> str:
    return f"{issue}-{_slug(title)}" if title else f"issue-{issue}"


def _issues_path(root: Path) -> Path:
    return _records_dir(root) / ISSUES_FILE


def _issue_map(root: Path) -> dict[str, str]:
    p = _issues_path(root)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _remember_issue(root: Path, issue: int, branch: str) -> None:
    m = _issue_map(root)
    m[str(issue)] = branch
    _issues_path(root).write_text(json.dumps(m, indent=2), encoding="utf-8")


def find_branch(root: Path, issue: int) -> str | None:
    """The branch an issue lives on: the issue map (outlives stop), a
    dispatch record, then a local branch named `<issue>-…` or `issue-<issue>`."""
    known = _issue_map(root).get(str(issue))
    if known:
        return known
    for rec in records(root):
        if rec.get("issue") == issue:
            return rec["branch"]
    for b in _out(root, "branch", "--list", "--format=%(refname:short)").splitlines():
        b = b.strip()
        if b == f"issue-{issue}" or b.startswith(f"{issue}-"):
            return b
    return None


def _worktrees(root: Path) -> dict[str, Path]:
    """branch → worktree path, from git itself."""
    out: dict[str, Path] = {}
    cur: Path | None = None
    for line in _out(root, "worktree", "list", "--porcelain").splitlines():
        if line.startswith("worktree "):
            cur = Path(line[len("worktree "):])
        elif line.startswith("branch refs/heads/") and cur is not None:
            out[line[len("branch refs/heads/"):]] = cur
    return out


def ensure_worktree(root: Path, branch: str) -> Path:
    listed = _worktrees(root)
    if branch in listed:
        return listed[branch]
    wt = root.parent / f"{root.name}-{branch.replace('/', '-')}"
    if wt.exists():
        raise SystemExit(f"dispatch: {wt} exists but is not a worktree of {branch} (git worktree list does not "
                         "know it) — refusing to start a worker in a directory that is not the project")
    base = "origin/main" if _git(root, "rev-parse", "--verify", "--quiet", "origin/main").returncode == 0 else "main"
    exists = _git(root, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}").returncode == 0
    args = ["worktree", "add", "-q", str(wt), branch] if exists else ["worktree", "add", "-q", "-b", branch, str(wt), base]
    r = _git(root, *args)
    if r.returncode != 0:
        raise SystemExit(f"dispatch: cannot add worktree for {branch}:\n{r.stderr.strip()}")
    return wt


# --- the prompt: the slash command leads, the command file owns the steps -----------

def prompt_for(phase: str, issue: int, tier: int | None, branch: str, model: str, remote: bool = False) -> str:
    tier_s = f"tier {tier}" if tier is not None else "tier to be derived from the scope (risk-tiers.md)"
    where = ("run on another host than the steward: fetch and check out branch `{b}` from origin first, set "
             "PROCESS_HOST to this host's name and PROCESS_REPORT_SYNC=1 so every report reaches origin "
             "(`refs/process/reports/<host>`) — the steward reads it there; push only what the phase produces"
             .format(b=branch) if remote else "work only in this worktree")
    tail = (f" You are the {phase} session for issue #{issue} on branch `{branch}` ({tier_s}), running as "
            f"{model}; {where}. Report each state transition with "
            f"`uv run scripts/process/report.py <state> --issue {issue} --model {model}"
            f"{' --sync' if remote else ''}`. A question only "
            f"the owner can answer goes into the plan's `## Decisions` as "
            f"`DECISION NEEDED <date> {branch}: <question> — options: A …, B …; recommendation: …`, "
            f"then `report.py blocked` — never decide it yourself (mandatory rule 4).")
    if phase == "plan":
        return f"/plan issue #{issue}: plan it, commit the plan with its `## Decisions` ledger, report `planned`, stop." + tail
    if phase == "execute":
        return f"/execute the committed plan for issue #{issue}: report `pushed` at the first push; stop after the last task is committed and pushed." + tail
    return f"/review branch `{branch}` for issue #{issue} as an independent reviewer: attest the REVIEW line with attest.py, report `review-pass` or `blocked` with the findings, stop; never fix code." + tail


# --- records and liveness -------------------------------------------------------------

def _records_dir(root: Path) -> Path:
    d = common_dir(root) / DISPATCH_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def _record_path(root: Path, branch: str) -> Path:
    return _records_dir(root) / (branch.replace("/", "__") + ".json")


def _proc_start(pid: int) -> str:
    """A process's start time as a string — pid + start time identify the
    process; a recycled pid does not match."""
    if pid <= 1:
        return ""
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8", errors="replace") as fh:
            fields = fh.read().rsplit(")", 1)[-1].split()
        return fields[19]  # starttime in clock ticks since boot
    except (OSError, IndexError):
        pass
    try:
        r = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True, text=True, timeout=10)
        return r.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _same_process(rec: dict) -> bool:
    pid = int(rec.get("pid") or 0)
    if pid <= 1:
        return False
    start = _proc_start(pid)
    return bool(start) and start == rec.get("pid_start")


def _tmux(*args: str) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["tmux", *args], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(args, 127, "", f"tmux unavailable: {exc}")


def _tmux_ensure_session(name: str) -> None:
    if _tmux("has-session", "-t", f"={name}").returncode != 0:
        r = _tmux("new-session", "-d", "-s", name, "-n", "steward")
        if r.returncode != 0:
            raise SystemExit(f"dispatch: cannot create tmux session {name!r}: {r.stderr.strip()}")


def _pane_state(window_id: str) -> str:
    """'live' | 'dead' (pane exited, remain-on-exit) | 'gone' | 'unknown'."""
    r = _tmux("display-message", "-p", "-t", window_id, "#{pane_dead}")
    if r.returncode != 0:
        return "unknown" if "unavailable" in r.stderr else "gone"
    return "dead" if r.stdout.strip() == "1" else "live"


def records(root: Path) -> list[dict]:
    out = []
    for p in sorted(_records_dir(root).glob("*.json")):
        if p.name == ISSUES_FILE:
            continue
        try:
            rec = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if rec.get("remote"):
            rec["state"] = "remote"  # liveness lives on the other host; its reports say
        elif rec.get("tmux_window"):
            rec["state"] = _pane_state(rec["tmux_window"])
        else:
            rec["state"] = "live" if _same_process(rec) else "gone"
        rec["alive"] = rec["state"] == "live"
        out.append(rec)
    return out


def live_children(root: Path) -> list[dict]:
    return [r for r in records(root) if r["alive"]]


def last_output(rec: dict, lines: int = 1) -> tuple[str, int | None]:
    """What the worker shows: the live tmux screen for a tmux worker (escape
    codes are not words), else the log tail; and minutes since it wrote."""
    log = Path(rec.get("log") or "")
    mins = int((time.time() - log.stat().st_mtime) // 60) if log.is_file() else None
    if rec.get("tmux_window") and rec.get("state") in (None, "live", "dead"):
        r = _tmux("capture-pane", "-p", "-t", rec["tmux_window"], "-S", f"-{max(lines, 1) + 5}")
        if r.returncode == 0:
            text = [ln.rstrip() for ln in r.stdout.splitlines()
                    if ln.strip() and not ln.startswith("Pane is dead")]  # tmux's epitaph is not the worker's
            return "\n".join(text[-lines:]), mins
    if not log.is_file():
        return "", None
    try:
        data = _ANSI.sub("", log.read_bytes()[-16384:].decode("utf-8", "replace"))
    except OSError:
        return "", None
    text = [ln for ln in data.splitlines() if ln.strip()][-lines:]
    return "\n".join(text), mins


_LANE_HELD = re.compile(r"^(\S+): held by", re.MULTILINE)


def held_lanes(root: Path) -> set[str]:
    """Names of the lanes `scripts/lane.py status` reports as held (one line per lane)."""
    lane = root / "scripts" / "lane.py"
    if not lane.is_file():
        return set()
    try:
        r = subprocess.run([sys.executable, str(lane), "status"], cwd=root, capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return set()
    return set(_LANE_HELD.findall(r.stdout))


def lane_verdict(held: set[str], phase: str) -> str | None:
    """None = start allowed, else why not. Only `full` held, for a plan or review, is
    allowed (those run under the train); any other held lane fails closed."""
    if not held:
        return None
    names = ", ".join(sorted(held))
    if held == {"full"} and phase != "execute":
        return None
    if held == {"full"}:
        return f"lane {names} is held — no free CPU for an execute session (phase {phase}); retry when lane-status says free"
    return f"lane {names} is held — no free CPU for a new session (phase {phase}); retry when lane-status says free"


def _worker_env(extra: dict[str, str]) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(STRIP_ENV_PREFIXES)}
    env.update(extra)
    return env


# --- commands ---------------------------------------------------------------------------

def start(root: Path, *, issue: int, phase: str, tier: int | None, branch: str | None, title: str | None,
          dry_run: bool) -> int:
    policy = load_policy(root)
    model = model_for(policy, tier, phase)
    branch = branch or find_branch(root, issue) or default_branch(issue, title)
    live = live_children(root)
    cap = max_workers(policy)
    pp = phase_policy(policy, phase)
    runner, remote = pp["runner"], pp["remote"]
    if any(r["branch"] == branch for r in live):
        print(f"dispatch: {branch} already has a live session — stop it first", file=sys.stderr)
        return 3
    # a remote phase puts its load on another host: neither this host's cap nor its lanes apply
    if not remote and len(live) >= cap:
        print(f"dispatch: {len(live)} live sessions, policy max_workers={cap} — not starting", file=sys.stderr)
        return 3
    refusal = None if remote else lane_verdict(held_lanes(root), phase)
    if refusal:
        print(f"dispatch: lane rule refused — {refusal}", file=sys.stderr)
        return 3
    prompt = prompt_for(phase, issue, tier, branch, model, remote=remote)
    argv = build_argv(policy, model, prompt, branch, issue, phase)
    if dry_run:
        held = sorted(held_lanes(root)) if not remote else []
        print(f"dispatch: lane rule allowed — held: {', '.join(held) or 'none'}, phase {phase}"
              + (" (remote: local lanes do not apply)" if remote else ""))
        shown = [a if a != prompt else f"<prompt {len(prompt)} chars>" for a in argv]
        print(f"dispatch: would start {phase} for #{issue} on {branch} with {model} "
              f"({'remote, ' if remote else ''}{runner}):\n  {shown}")
        return 0
    if remote:
        # another host: no worktree here, the start command hands the work over
        # (a cloud session, an ssh command); its exit is the hand-over, not the
        # worker's end — the worker's reports arrive through origin
        if not _out(root, "ls-remote", "--heads", "origin", branch):
            print(f"dispatch: {branch} is not on origin — a remote {phase} session needs the branch pushed first",
                  file=sys.stderr)
            return 3
        extra = {"PROCESS_WORKER": branch, "PROCESS_PHASE": phase, "PROCESS_MODEL": model, "PROCESS_ISSUE": str(issue)}
        try:
            r = subprocess.run(argv, cwd=root, capture_output=True, text=True, timeout=300, env=_worker_env(extra))
        except (OSError, subprocess.TimeoutExpired) as exc:
            print(f"dispatch: remote start failed: {exc}", file=sys.stderr)
            return 1
        if r.returncode != 0:
            print(f"dispatch: remote start command exited {r.returncode}: {(r.stderr or r.stdout).strip()[-400:]}",
                  file=sys.stderr)
            return 1
        rec = {"branch": branch, "issue": issue, "phase": phase, "tier": tier, "model": model, "remote": True,
               "started": int(time.time()), "ts": _dt.datetime.now().isoformat(timespec="seconds"),
               "runner": runner, "handover": r.stdout.strip()[-400:]}
        _record_path(root, branch).write_text(json.dumps(rec, indent=2), encoding="utf-8")
        _remember_issue(root, issue, branch)
        print(f"dispatch: handed {phase} for #{issue} on {branch} to another host with {model} — "
              f"reports via origin (`tower.py --remote`)" + (f"\n  {rec['handover']}" if rec["handover"] else ""))
        return 0
    wt = ensure_worktree(root, branch)
    log = _records_dir(root) / f"{branch.replace('/', '__')}-{phase}-{_dt.datetime.now():%Y%m%d-%H%M%S}.log"
    extra = {"PROCESS_WORKER": branch, "PROCESS_PHASE": phase, "PROCESS_MODEL": model, "PROCESS_ISSUE": str(issue)}
    rec = {"branch": branch, "issue": issue, "phase": phase, "tier": tier, "model": model,
           "worktree": str(wt), "log": str(log), "started": int(time.time()),
           "ts": _dt.datetime.now().isoformat(timespec="seconds"), "runner": runner}
    if runner == "tmux":
        session = str(policy.get("tmux_session") or "workers")
        _tmux_ensure_session(session)
        window = branch.replace("/", "-").replace(".", "-")[:40]
        # a non-interactive sh: exact quoting, no aliases/rc/history; the sleep
        # lets the log pipe attach before the first line; exec keeps the pane
        # process = the worker, so pane_dead is the truth about liveness
        unset = [f"-u {shlex.quote(k)}" for k in os.environ if k.startswith(STRIP_ENV_PREFIXES)]
        inner = "sleep 1; exec env " + " ".join(unset) + " \"$@\""
        shell_cmd = shlex.join(["sh", "-c", inner, "_", *argv])
        env_args = [x for k, v in extra.items() for x in ("-e", f"{k}={v}")]
        r = _tmux("new-window", "-d", "-P", "-F", "#{window_id}", "-t", session, "-n", window, "-c", str(wt),
                  *env_args, shell_cmd)
        if r.returncode != 0:
            print(f"dispatch: tmux new-window failed: {r.stderr.strip()}", file=sys.stderr)
            return 1
        window_id = r.stdout.strip()
        _tmux("set-option", "-t", window_id, "remain-on-exit", "on")
        if _tmux("pipe-pane", "-t", window_id, "-o", f"cat >> {shlex.quote(str(log))}").returncode != 0:
            print("dispatch: warning — log pipe could not be attached; `log` will read the live screen only",
                  file=sys.stderr)
        rec.update({"tmux_window": window_id, "tmux_session": session, "tmux_name": window})
        where = f"tmux {session}:{window} ({window_id})"
    else:
        with log.open("ab") as fh:
            try:
                proc = subprocess.Popen(argv, cwd=wt, stdin=subprocess.DEVNULL, stdout=fh,
                                        stderr=subprocess.STDOUT, env=_worker_env(extra), start_new_session=True)
            except OSError as exc:
                print(f"dispatch: cannot start {argv[0]!r}: {exc} — fix `command` in {POLICY}", file=sys.stderr)
                return 1
        rec.update({"pid": proc.pid, "pid_start": _proc_start(proc.pid)})
        where = f"pid {proc.pid}"
    _record_path(root, branch).write_text(json.dumps(rec, indent=2), encoding="utf-8")
    _remember_issue(root, issue, branch)
    print(f"dispatch: started {phase} for #{issue} on {branch} with {model} ({where}, log {log.name})")
    return 0


def list_sessions(root: Path) -> int:
    recs = records(root)
    if not recs:
        print("dispatch: no sessions started from this clone")
        return 0
    now = time.time()
    for r in recs:
        mins = int((now - int(r.get("started") or now)) // 60)
        last, since = last_output(r)
        where = ("another host" if r.get("remote") else
                 f"{r.get('tmux_session')}:{r.get('tmux_name')}" if r.get("tmux_window") else f"pid {r.get('pid')}")
        print(f"- {r['branch']}: {r['phase']} #{r.get('issue')} {r.get('model')} {where} "
              f"{r['state'].upper()} ({mins} min)" + (f" · {since} min ago: {last[-120:]}" if last else ""))
    return 0


def _load_record(root: Path, branch: str) -> tuple[Path, dict] | None:
    p = _record_path(root, branch)
    if not p.is_file():
        return None
    rec = json.loads(p.read_text(encoding="utf-8"))
    rec["state"] = ("remote" if rec.get("remote") else
                    _pane_state(rec["tmux_window"]) if rec.get("tmux_window") else
                    "live" if _same_process(rec) else "gone")
    return p, rec


def show_log(root: Path, branch: str, lines: int) -> int:
    found = _load_record(root, branch)
    if found is None:
        print(f"dispatch: no record for {branch}", file=sys.stderr)
        return 2
    _p, rec = found
    text, mins = last_output(rec, lines)
    head = f"{branch} — {rec.get('phase')} #{rec.get('issue')} {rec.get('model')} — {rec['state']}"
    print(head + (f" — last write {mins} min ago" if mins is not None else ""))
    print(text or "(nothing yet)")
    return 0


def say(root: Path, branch: str, text: str) -> int:
    found = _load_record(root, branch)
    if found is None or not found[1].get("tmux_window"):
        print(f"dispatch: {branch} is not a tmux worker started here — nothing to type into", file=sys.stderr)
        return 2
    _p, rec = found
    if rec["state"] != "live":
        print(f"dispatch: {branch} is {rec['state']} — nobody is listening", file=sys.stderr)
        return 3
    r = _tmux("send-keys", "-t", rec["tmux_window"], "-l", text)
    r2 = _tmux("send-keys", "-t", rec["tmux_window"], "Enter")
    if r.returncode != 0 or r2.returncode != 0:
        print(f"dispatch: send-keys failed: {(r.stderr or r2.stderr).strip()}", file=sys.stderr)
        return 1
    print(f"dispatch: said to {branch}: {text[:80]}")
    return 0


def stop(root: Path, branch: str, *, force: bool) -> int:
    found = _load_record(root, branch)
    if found is None:
        print(f"dispatch: {branch} was not started by this tool — stop only what you started", file=sys.stderr)
        return 2
    p, rec = found
    if rec["state"] == "remote":
        print(f"dispatch: {branch} runs on another host — stop it there; record removed here")
        p.unlink()
        return 0
    if rec["state"] != "live":
        print(f"dispatch: {branch} is {rec['state']} — record removed")
        p.unlink()
        return 0
    wt = Path(rec.get("worktree") or "")
    dirty = _out(wt, "status", "--porcelain") if wt.is_dir() else ""
    if dirty and not force:
        print(f"dispatch: {branch} has uncommitted or untracked work ({len(dirty.splitlines())} file(s)) — a "
              "plan or decisions not committed die with the process; ask the worker to commit, or --force",
              file=sys.stderr)
        return 3
    if rec.get("tmux_window"):
        _tmux("kill-window", "-t", rec["tmux_window"])
    else:
        pid = int(rec.get("pid") or 0)
        try:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass
        for _ in range(50):
            if not _same_process(rec):
                break
            time.sleep(0.2)
        else:
            try:
                os.kill(pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
    try:
        _report.write_report(root, "idle", issue=rec.get("issue"), note=f"stopped by dispatch ({rec.get('phase')})",
                             worker=branch)
    except SystemExit:
        pass
    p.unlink()
    print(f"dispatch: stopped {branch}")
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
    lg = sub.add_parser("log")
    lg.add_argument("branch")
    lg.add_argument("--lines", type=int, default=30)
    sy = sub.add_parser("say")
    sy.add_argument("branch")
    sy.add_argument("text")
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
    if a.command == "log":
        return show_log(root, a.branch, a.lines)
    if a.command == "say":
        return say(root, a.branch, a.text)
    if a.command == "stop":
        return stop(root, a.branch, force=a.force)
    policy = load_policy(root)
    for ph in PHASES:
        print(f"{ph}: {model_for(policy, a.tier, ph)}")
    print(f"command: {policy['command']}  (runner {policy.get('runner', 'detached')}, "
          f"max_workers {max_workers(policy)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
