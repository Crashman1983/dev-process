#!/usr/bin/env python3
"""dispatch — start, list, watch, message and stop worker sessions per
phase, with the model the policy assigns.

    uv run scripts/process/dispatch.py start --issue N --phase plan|execute|review [--tier T] [--branch B] [--title "..."]
    uv run scripts/process/dispatch.py list
    uv run scripts/process/dispatch.py log <branch> [--lines N]   # what the worker shows right now
    uv run scripts/process/dispatch.py say <branch> "<text>"      # a line into an interactive worker
    uv run scripts/process/dispatch.py stop <branch> [--force]
    uv run scripts/process/dispatch.py chain [--dry-run]           # next phase from the reports, then drain
    uv run scripts/process/dispatch.py queue add --issue N --phase P [--tier T] [--branch B] | list
    uv run scripts/process/dispatch.py drain                       # start what the queue may start now
    uv run scripts/process/dispatch.py policy [--tier T]          # what would run

A phase is a session: `plan` opens a worktree on a fresh branch (or reuses
the issue's branch) and starts the planning session; `execute` starts the
build session in that worktree; `review` a fresh reviewing session there.
Between phases the artifacts carry the state (the plan and its `##
Decisions` ledger, the bundle) — the model may change, the worktree stays.
Which model runs which phase comes from `docs/process/model-policy.json`
(tier × phase), with `model-policy.local.json` laid over it when the project
has one; the project's own start command is the `command` template
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
line into a tmux worker and checks it left the input line: a busy worker
leaves typed text sitting there (downstream: sessions idled up to 90
minutes on an unsent line), so `say` presses Enter again, and exits
non-zero naming the branch when the text still has not gone.

Phases chain themselves (`chain`, run it from the steward's tick): a
`planned` plan session is stopped and `execute` queued; a `pushed` execute
session with new code on origin beyond the last attestation is stopped and
`review` queued; a `review-pass` review session whose attestation is on
origin is stopped — its report is the train's ticket. `blocked` queues
nothing: that decision is the steward's. A chained stop keeps the worker's
report (a plain `stop` writes `idle`). The queue (`queue.json` beside the
records) is drained in order, and a line the caps or lanes refuse is
skipped, not waited on: a plan or review behind a refused execute still
starts. Local workers start under `nice` (policy `worker_nice`, default
10; 0 = off): the merge train's suite, run at normal priority, keeps its
CPU while workers test (downstream: timeouts under load dropped innocent
passengers).

Records live in `<git common dir>/process-dispatch/`: one JSON per
branch (pid + process start time, tmux window id, phase, model, log) and
`issues.json` (issue → branch, so the next phase finds the branch after
a stop; an empty branch marks an issue the train merged). `stop` acts only on what this tool started, only when the
recorded process is the recorded one (pid + start time; never pid 0), and
refuses while the worktree has uncommitted or untracked work unless
`--force` — a plan not committed dies with the process. `max_workers`
caps live children on this host; a held lane counts as no free CPU —
a held full lane blocks only execute, a held scoped (or unknown) lane
blocks every phase, and a remote phase sees neither cap nor lane. A
local start also refuses while the filesystem holding the worktrees is
at or above 90% use (`PROCESS_DISK_LIMIT_PCT`) and names `tidy.py
--apply`: each worktree carries its own venv/node_modules (downstream:
111 merged worktrees filled the disk). Whether a merged worktree may be
removed has one owner here (`merged_worktrees`); the train and tidy ask it.

Trust boundary, plainly: the policy's `command` is executed on the
machine that runs dispatch. It is a repository file — whoever can merge
to it can run code here. Treat it like CI configuration.

The dispatcher decides nothing about the work. Stdlib only."""
from __future__ import annotations

import argparse
import datetime as _dt
import fnmatch
import json
import math
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling imports
import report as _report  # noqa: E402

POLICY = "docs/process/model-policy.json"
# the project's own choices over the template's policy, mapping by mapping — so a
# release that edits model-policy.json reaches the project and its own ids stay
LOCAL_POLICY = "docs/process/model-policy.local.json"
DISPATCH_DIR = "process-dispatch"
ISSUES_FILE = "issues.json"
QUEUE_FILE = "queue.json"
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
    local = root / LOCAL_POLICY
    if local.is_file():
        try:
            over = json.loads(local.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise SystemExit(f"dispatch: {LOCAL_POLICY} is not valid JSON: {exc}")
        if not isinstance(over, dict):
            raise SystemExit(f"dispatch: {LOCAL_POLICY} must be an object laid over {POLICY}")
        data = _merged(data, over)
    if not isinstance(data.get("command"), str) or "{prompt}" not in data["command"]:
        raise SystemExit(f"dispatch: {POLICY} needs a `command` template containing {{prompt}}")
    _check_env(data.get("env"), "env")
    for ph, row in (data.get("phases") or {}).items():
        if isinstance(row, dict):
            _check_env(row.get("env"), f"phases.{ph}.env")
        if ph not in PHASES or not isinstance(row, dict):
            raise SystemExit(f"dispatch: {POLICY} `phases` keys must be plan|execute|review with an object each")
        if "command" in row and (not isinstance(row["command"], str) or "{prompt}" not in row["command"]):
            raise SystemExit(f"dispatch: {POLICY} phases.{ph}.command must contain {{prompt}}")
        if "handover_id" in row:
            try:
                re.compile(str(row["handover_id"]))
            except re.error as exc:
                raise SystemExit(f"dispatch: {POLICY} phases.{ph}.handover_id is not a regex: {exc}")
    return data


def _merged(base: dict, over: dict) -> dict:
    """`over` laid on `base`: mappings merge key by key, anything else replaces whole."""
    out = dict(base)
    for key, value in over.items():
        out[key] = (_merged(out[key], value)
                    if isinstance(value, dict) and isinstance(out.get(key), dict) else value)
    return out


def _check_env(env: object, where: str) -> None:
    if env is None:
        return
    if not isinstance(env, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in env.items()):
        raise SystemExit(f"dispatch: {POLICY} `{where}` must map names to strings")
    if any(k.startswith("PROCESS_") for k in env):
        raise SystemExit(f"dispatch: {POLICY} `{where}` must not set PROCESS_* — dispatch owns those")
    # a worker's environment must not switch the local guards off: pre-commit's SKIP,
    # git's own configuration (GIT_CONFIG_* can set core.hooksPath), pre-commit's knobs
    # HOME and XDG_* carry a git config (core.hooksPath), PATH another git, LD_*/DYLD_*
    # code into every process; names compared case-insensitively (`skip` is SKIP on a
    # case-insensitive system). The policy is trusted configuration all the same —
    # `command` can run anything — so this closes the easy path, and a change to the
    # policy files is gate code to the review bundle
    hooks = sorted(k for k in env if k.upper() in ("SKIP", "HOME", "PATH")
                   or k.upper().startswith(("GIT_", "PRE_COMMIT", "XDG_", "LD_", "DYLD_")))
    if hooks:
        raise SystemExit(f"dispatch: {POLICY} `{where}` must not set {', '.join(hooks)} — "
                         f"it would switch the hooks off or redirect git for every worker")


def phase_base(root: Path, branch: str) -> str:
    """The branch's commit on origin when a phase starts ('' when not on origin yet):
    report.py refuses `pushed` until origin has moved past it."""
    return _remote_head(root, branch)


def _remote_head(root: Path, branch: str) -> str:
    """origin's commit of exactly this branch ('' if none) — `ls-remote --heads
    origin x` also lists `feat/x`."""
    for line in _out(root, "ls-remote", "origin", f"refs/heads/{branch}").splitlines():
        sha, _, ref = line.partition("\t")
        if ref.strip() == f"refs/heads/{branch}":
            return sha.strip()
    return ""


def phase_policy(policy: dict, phase: str) -> dict:
    """The command, runner and host for ONE phase: `phases.<phase>` overrides
    the top-level `command`/`runner`; `remote: true` says the session runs on
    another host (a cloud session, another machine) — no local worktree, no
    local liveness, reports come back through origin (`report.py --sync`)."""
    row = (policy.get("phases") or {}).get(phase) or {}
    return {"command": row.get("command") or policy["command"],
            "runner": str(row.get("runner") or policy.get("runner") or "detached"),
            "remote": bool(row.get("remote", False)),
            "handover_id": str(row.get("handover_id") or ""),
            # worker-only environment (e.g. a cheaper subagent model): the
            # phase's entries over the top-level ones; the owner's own
            # sessions never see it
            "env": {**(policy.get("env") or {}), **(row.get("env") or {})}}


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


def niced(policy: dict, argv: list[str]) -> list[str]:
    """A local worker's argv under `nice` (policy `worker_nice`, default 10).
    `env` carries the argv: a command that starts with `VAR=value` keeps
    working as it did through the runner's own `env`."""
    level = policy.get("worker_nice", 10)
    if level is None:
        level = 10
    if isinstance(level, bool) or not isinstance(level, int):
        raise SystemExit(f"dispatch: worker_nice in {POLICY} must be an integer, got {level!r}")
    if level <= 0 or not shutil.which("nice"):
        return argv
    return ["nice", "-n", str(min(level, 19)), "env", *argv]


def _command_word(argv: list[str]) -> str:
    return next((a for a in argv if "=" not in a or a.startswith(("/", "."))), "")


def runnable(argv: list[str]) -> str | None:
    """None when the command can start here, else why not — checked before
    starting, so a missing harness is a refusal, not a worker that dies."""
    word = _command_word(argv)
    if not word:
        return "the policy command is empty"
    if "/" in word:
        return None if os.access(word, os.X_OK) else f"{word!r} is not an executable file"
    return None if shutil.which(word) else f"{word!r} is not on PATH"


# --- branches and worktrees --------------------------------------------------------

def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:40] or "work"


def default_branch(issue: int, title: str | None) -> str:
    return f"{issue}-{_slug(title)}" if title else f"issue-{issue}"


def _issues_path(root: Path) -> Path:
    return _records_dir(root) / ISSUES_FILE


def _issue_map(root: Path) -> dict[str, str]:
    p = common_dir(root) / DISPATCH_DIR / ISSUES_FILE  # a read creates nothing
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _remember_issue(root: Path, issue: int, branch: str) -> None:
    m = _issue_map(root)
    m[str(issue)] = branch
    _issues_path(root).write_text(json.dumps(m, indent=2), encoding="utf-8")


def _record_issue(rec: dict) -> int | None:
    """The issue a record names — a positive int, nothing else (a boolean,
    a float, a list are no issue)."""
    issue = rec.get("issue")
    return issue if type(issue) is int and issue > 0 else None


def _placed(root: Path) -> dict[int, str]:
    """issue -> the branch dispatch placed it on: the issue map first (it
    outlives stop, and a re-dispatch re-points it), then the first dispatch
    record naming the issue. An issue the map marks merged (an empty branch,
    written by forget_branch) is placed nowhere, whatever a record left on
    another host still says. One answer for find_branch and issues_of."""
    placed: dict[int, str] = {}
    for rec in _record_files(root):
        issue = _record_issue(rec)
        if issue is not None:
            placed.setdefault(issue, rec["branch"])
    for k, v in _issue_map(root).items():
        if k.isdigit() and int(k) > 0:
            if v:
                placed[int(k)] = v
            else:
                placed.pop(int(k), None)
    return placed


def find_branch(root: Path, issue: int) -> str | None:
    """The branch an issue lives on: the issue map (outlives stop), a
    dispatch record, then a local branch named `<issue>-…` or `issue-<issue>`."""
    known = _placed(root).get(issue)
    if known:
        return known
    from check_review import branch_issue  # noqa: PLC0415  (the one owner of a branch's issue)

    for b in _out(root, "branch", "--list", "--format=%(refname:short)").splitlines():
        b = b.strip()
        if branch_issue(b) == str(issue):
            return b
    return None


def issues_of(root: Path, branch: str) -> set[int]:
    """The issues dispatch placed on `branch` — exactly those find_branch
    resolves to it (refutation: a record left from before a re-dispatch kept
    an issue on its old branch). A branch can carry another issue than the
    number its name leads with: a package of a larger issue is dispatched
    onto `<epic>-<package>-…`. Reading creates nothing and asks no worker."""
    return {issue for issue, b in _placed(root).items() if b == branch}


def forget_branch(root: Path, branch: str) -> None:
    """The branch's work is merged: its issues are placed on it no more, and
    on no other branch either — a later branch of the same name starts clean
    (refutation: a reused name inherited old issues, and its merge closed
    them), and a dead record from before a re-dispatch does not bring the
    merged issue back to its abandoned branch (refutation). A live worker's
    record stays, and so does one whose liveness cannot be asked here (tmux
    unknown, a worker on another host); `stop` owns them. Known limits: a
    branch merged outside the train keeps its entries until its issue is
    dispatched again — the map outlives `stop` on purpose, so the next phase
    finds the branch; and a second attempt still running on another branch
    for the merged issue is placed nowhere once the issue is marked done —
    reading the map asks no worker's liveness."""
    done = issues_of(root, branch)
    m = _issue_map(root)
    # merged: an empty branch marks the issue done, so a record kept for a
    # worker on another host cannot place it again (refutation); a later
    # dispatch of the issue overwrites the mark
    kept = {**{k: v for k, v in m.items() if v != branch}, **{str(i): "" for i in done}}
    if kept != m:
        _issues_path(root).write_text(json.dumps(kept, indent=2), encoding="utf-8")
    for rec in records(root):
        if rec["alive"] or rec.get("state") == "unknown":
            continue
        own = rec["branch"] == branch
        if own or (rec.get("state") != "remote" and _record_issue(rec) in done):
            try:
                _record_path(root, rec["branch"]).unlink()
            except OSError:
                pass

def worktree_entries(root: Path) -> list[dict]:
    """Every worktree git knows, in its order: path, branch (None when detached),
    locked, main (git lists the main worktree first)."""
    out: list[dict] = []
    cur: dict | None = None
    for line in _out(root, "worktree", "list", "--porcelain").splitlines():
        if line.startswith("worktree "):
            cur = {"path": Path(line[len("worktree "):]), "branch": None, "locked": False, "main": not out}
            out.append(cur)
        elif cur is None:
            continue
        elif line.startswith("branch refs/heads/"):
            cur["branch"] = line[len("branch refs/heads/"):]
        elif line == "locked" or line.startswith("locked "):
            cur["locked"] = True
    return out


def _worktrees(root: Path) -> dict[str, Path]:
    """branch → worktree path, from git itself."""
    return {e["branch"]: e["path"] for e in worktree_entries(root) if e["branch"]}


# --- removing merged worktrees (#136) ---------------------------------------------------
# Every dispatched issue gets a worktree with its own venv/node_modules; nothing
# removed them after the merge (downstream: 111 worktrees, ~57G, a full disk and
# every session stalled). The train (after its merge) and tidy (`--apply`) remove
# them — and both ask this one owner whether a worktree may go, and if not, why.

DISK_LIMIT_PCT = 90  # `start` refuses while the worktrees' filesystem is this full
DISK_LIMIT_ENV = "PROCESS_DISK_LIMIT_PCT"
CLEANUP_CMD = "python3 scripts/process/tidy.py --apply"


def _toplevel(path: Path) -> Path | None:
    top = _out(path, "rev-parse", "--show-toplevel")
    return Path(top).resolve() if top else None


# What may be destroyed with a merged worktree: environments and caches a command
# regenerates — matched against the name of each ignored entry git lists (the
# entry itself, not a parent: `build/notes.md` listed alone is a file somebody kept).
# Anything else ignored (`.env`, notes excluded via .git/info/exclude) keeps it.
DISPOSABLE_IGNORED = (
    ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".hypothesis", ".tox", ".nox", ".coverage", ".coverage.*", "htmlcov", "dist", "build", "*.egg-info",
    ".next", ".turbo", ".parcel-cache", ".cache", "*.pyc", "*.pyo", ".DS_Store",
)


def _disposable(entry: str) -> bool:
    name = entry.rstrip("/").rsplit("/", 1)[-1]
    return any(fnmatch.fnmatchcase(name, pat) for pat in DISPOSABLE_IGNORED)


def _has_own_commits(root: Path, branch: str) -> bool:
    """False when the branch's reflog shows nothing but its creation — a fresh branch
    sits at its base's tip and so reads as "contained", but no work of it was merged
    (a dispatched worker that died before its first commit). An empty or expired
    reflog proves nothing either way: the branch is older than the reflog — True."""
    r = _git(root, "reflog", "show", "--format=%gs", f"refs/heads/{branch}", "--")
    entries = [ln for ln in r.stdout.splitlines() if ln.strip()] if r.returncode == 0 else []
    return not entries or not all(ln.startswith("branch: Created from") for ln in entries)


def worktree_keep_reason(root: Path, wt: dict, base: str, recs: list[dict],
                         others: list[Path] | None = None) -> str | None:
    """None when the worktree `wt` (a `worktree_entries` item) may be removed;
    otherwise why it stays. What may go is named, not inferred: a branch's
    worktree (not the main one, not the one we run in, not detached, not
    locked) holding no other registered worktree (`others`, default: all git
    lists), its branch contained in `base` AND with commits of its own (its
    reflog shows more than its creation, or has expired — see
    `_has_own_commits`), no live dispatch session on it, no uncommitted
    change, no untracked file git does not ignore (an uncommitted journal
    shard is work), and every ignored entry a regenerable environment or cache
    (`DISPOSABLE_IGNORED`; `.env` or a note excluded by .git/info/exclude is not)."""
    path, branch = wt["path"], wt["branch"]
    if wt["main"]:
        return "the main worktree"
    here = {p for p in (_toplevel(root), _toplevel(Path.cwd())) if p}
    real = path.resolve()
    if real in here:
        return "the current worktree"
    if wt["locked"]:
        return "locked (`git worktree lock`)"
    if others is None:
        others = [e["path"] for e in worktree_entries(root)]
    for other in others:
        o = other.resolve()
        if o != real and o.is_relative_to(real):
            return f"holds worktree {other}"
    if not branch:
        return "detached HEAD — not a branch's worktree"
    if _git(root, "merge-base", "--is-ancestor", f"refs/heads/{branch}", base).returncode != 0:
        return f"{branch} is not contained in {base}"
    if not _has_own_commits(root, branch):
        return f"no commits of its own — {branch} was only created, never worked on"
    for rec in recs:
        same = rec["branch"] == branch or (rec.get("worktree") and Path(rec["worktree"]).resolve() == path.resolve())
        if same and (rec.get("alive") or rec.get("state") == "unknown"):
            return f"a dispatch session is {'live' if rec.get('alive') else 'not askable (tmux)'} on it " \
                   f"({rec.get('phase') or '?'})"
    if not path.is_dir():
        return None  # gone already: `git worktree prune` forgets it
    # one status: `??` untracked, `!!` ignored — `matching`: the path the ignore rule
    # names (`src/__pycache__/`), not a parent holding only ignored files (`src/`) —
    # anything else a change; -z keeps paths unquoted
    st = _git(path, "status", "--porcelain", "-z", "--ignored=matching", "--untracked-files=normal")
    if st.returncode != 0:
        return f"git status failed there: {st.stderr.strip()[-200:]}"
    entries = [e for e in st.stdout.split("\0") if e]
    changed = [e for e in entries if not e.startswith(("?? ", "!! "))]
    if changed:
        return f"uncommitted changes ({len(changed)} path(s))"
    untracked = [e[3:] for e in entries if e.startswith("?? ")]
    if untracked:
        return f"untracked files not ignored ({', '.join(untracked[:3])}{', …' if len(untracked) > 3 else ''})"
    kept = [e[3:] for e in entries if e.startswith("!! ") and not _disposable(e[3:])]
    if kept:
        return f"ignored files that are not a regenerable environment or cache ({kept[0]}" \
               f"{f', +{len(kept) - 1} more' if len(kept) > 1 else ''})"
    return None


def merged_worktrees(root: Path, base: str, branches: list[str] | None = None) -> list[tuple[dict, str | None]]:
    """(worktree, keep reason or None) for the worktree of each of `branches`, or —
    without `branches` — of every branch contained in `base`. The main worktree is
    never a candidate; detached worktrees are no branch's and are not listed."""
    recs = records(root)
    entries = worktree_entries(root)
    others = [e["path"] for e in entries]
    out = []
    for wt in entries:
        if wt["main"] or not wt["branch"]:
            continue
        if branches is not None:
            if wt["branch"] not in branches:
                continue
        elif _git(root, "merge-base", "--is-ancestor", f"refs/heads/{wt['branch']}", base).returncode != 0:
            continue
        out.append((wt, worktree_keep_reason(root, wt, base, recs, others)))
    return out


def remove_worktree(root: Path, path: Path) -> str | None:
    """Remove one worktree that `worktree_keep_reason` cleared; None or why it failed.
    No `--force`: plain `git worktree remove` deletes ignored files (venv,
    node_modules, caches) with the tree but refuses a change, an untracked file or a
    lock — git checks those again, so such a file written after the keep check is
    not lost (an ignored one written in that window is not re-checked)."""
    r = _git(root, "worktree", "remove", str(path)) if path.is_dir() else None
    _git(root, "worktree", "prune")
    if r is not None and r.returncode != 0:
        return r.stderr.strip() or f"git worktree remove exited {r.returncode}"
    return None


def disk_refusal(path: Path) -> str | None:
    """Why no session may start while the filesystem holding `path` is too full
    (use = used / (used + available), as `df` counts it), or None. A limit that is no
    percentage in (0, 100] refuses too: a misconfigured guard is neither silently off
    nor silently the default. A usage that cannot be read lets the start through,
    with a note."""
    raw = os.environ.get(DISK_LIMIT_ENV, "").strip()
    try:
        limit = float(raw) if raw else float(DISK_LIMIT_PCT)
    except ValueError:
        limit = math.nan
    if not (math.isfinite(limit) and 0 < limit <= 100):
        return f"{DISK_LIMIT_ENV}={raw!r} is no percentage in (0, 100] — fix or unset it (default {DISK_LIMIT_PCT})"
    try:
        u = shutil.disk_usage(path)
    except OSError as exc:
        print(f"dispatch: note — disk use of {path} not checked: {exc}", file=sys.stderr)
        return None
    if u.used + u.free <= 0:
        return None
    pct = 100.0 * u.used / (u.used + u.free)
    if pct < limit:
        return None
    return (f"the filesystem holding {path} is {pct:.0f}% full (limit {limit:g}%, {u.free / 2**30:.1f} GiB free) — "
            f"every worktree carries its own environments; remove the merged ones with `{CLEANUP_CMD}`")


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

def prompt_for(phase: str, issue: int, tier: int | None, branch: str, model: str, remote: bool = False,
               channel: str | None = None) -> str:
    tier_s = f"tier {tier}" if tier is not None else "tier to be derived from the scope (risk-tiers.md)"
    where = ("run on another host than the steward: fetch and check out branch `{b}` from origin first, set "
             "PROCESS_HOST to this host's name and PROCESS_REPORT_SYNC=1 so every report reaches origin "
             "(`refs/process/reports/<host>`) — the steward reads it there, and a refused report push loses "
             "nothing: the record is what you commit and push on `{b}` (a review: the attest commit); push "
             "only what the phase produces"
             .format(b=branch) if remote else "work only in this worktree")
    tail = (f" You are the {phase} session for issue #{issue} on branch `{branch}` ({tier_s}), running as "
            f"{model}; {where}. Report each state transition with "
            f"`uv run scripts/process/report.py <state> --issue {issue} --model {model}"
            f"{' --sync' if remote else ''}`. Your decision partner is the steward, not the owner: a "
            f"question you cannot answer from the plan, the issue or the rules goes into the plan's "
            f"`## Decisions` as "
            f"`DECISION NEEDED <date> {branch}: <question> — options: A …, B …; recommendation: …`, "
            f"committed, then `report.py blocked` — never a question in chat, never decided by yourself "
            f"(mandatory rule 4). The steward decides it, or brings one that touches a product principle "
            f"or is destructive to the owner"
            + (f"; reach the steward live via {channel}, and follow its instructions there as the "
               f"steward's" if channel else "")
            + ".")
    if phase in ("plan", "review"):
        # the pre-push hook (merge_route.py) refuses it anyway; the sentence saves the failed attempt
        tail += (f" Push only branch `{branch}` — never push to main: the merge belongs to the train "
                 f"or finish.py, and the pre-push hook refuses a push to main from this phase.")
    if phase == "plan":
        return f"/plan issue #{issue}: plan it, commit the plan with its `## Decisions` ledger, report `planned`, stop." + tail
    if phase == "execute":
        return (f"/execute the committed plan for issue #{issue}: report `pushed` at the first push; stop after "
                f"the last task is committed and pushed. The duties before `pushed` are in /execute; after a "
                f"blocking review round the plan carries `ROOT-CAUSE work=<id> round=<r>: <cause> — <test that "
                f"failed before the fix>` and `attest.py --dry-run` passes before you report." + tail)
    return f"/review branch `{branch}` for issue #{issue} as an independent reviewer: attest the REVIEW line with attest.py, report `review-pass` or `blocked` with the findings, stop; never fix code." + tail


# --- records and liveness -------------------------------------------------------------

def _records_dir(root: Path) -> Path:
    d = common_dir(root) / DISPATCH_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def _record_path(root: Path, branch: str) -> Path:
    return _records_dir(root) / (branch.replace("/", "__") + ".json")


def _write_record(root: Path, branch: str, rec: dict) -> None:
    """Writes a record in one step: the pre-push guard (`merge_route.py`) reads the records
    while a dispatch may still be writing, and a half-written file must never be what it
    sees. The temp name does not end in `.json`, so no reader lists it."""
    path = _record_path(root, branch)
    staging = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        staging.write_text(json.dumps(rec, indent=2), encoding="utf-8")
        os.replace(staging, path)
    except OSError:
        staging.unlink(missing_ok=True)
        raise


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


def _tmux_start(session: str, window: str, cwd: Path, argv: list[str], extra: dict[str, str],
                log: Path) -> tuple[str | None, str]:
    """Start argv in a new window of tmux `session` (a real terminal); returns
    (window_id, "") or (None, why). The pane keeps its process until it exits
    (remain-on-exit), and its output is piped to `log`."""
    _tmux_ensure_session(session)
    # a non-interactive sh: exact quoting, no aliases/rc/history; the sleep
    # lets the log pipe attach before the first line; exec keeps the pane
    # process = the worker, so pane_dead is the truth about liveness
    unset = [f"-u {shlex.quote(k)}" for k in os.environ if k.startswith(STRIP_ENV_PREFIXES) and k not in extra]
    inner = "sleep 1; exec env " + " ".join(unset) + " \"$@\""
    shell_cmd = shlex.join(["sh", "-c", inner, "_", *argv])
    env_args = [x for k, v in extra.items() for x in ("-e", f"{k}={v}")]
    r = _tmux("new-window", "-d", "-P", "-F", "#{window_id}", "-t", session, "-n", window, "-c", str(cwd),
              *env_args, shell_cmd)
    if r.returncode != 0:
        return None, f"tmux new-window failed: {r.stderr.strip()}"
    window_id = r.stdout.strip()
    _tmux("set-option", "-t", window_id, "remain-on-exit", "on")
    if _tmux("pipe-pane", "-t", window_id, "-o", f"cat >> {shlex.quote(str(log))}").returncode != 0:
        print("dispatch: warning — log pipe could not be attached; `log` will read the live screen only",
              file=sys.stderr)
    return window_id, ""


def _pane_exit(window_id: str) -> str:
    """The exit status of a dead pane ('' while it runs or when unknown)."""
    r = _tmux("display-message", "-p", "-t", window_id, "#{pane_dead}:#{pane_dead_status}")
    dead, _, status = r.stdout.strip().partition(":")
    return status if r.returncode == 0 and dead == "1" else ""


def _pane_state(window_id: str) -> str:
    """'live' | 'dead' (pane exited, remain-on-exit) | 'gone' | 'unknown'."""
    r = _tmux("display-message", "-p", "-t", window_id, "#{pane_dead}")
    if r.returncode != 0:
        return "unknown" if "unavailable" in r.stderr else "gone"
    return "dead" if r.stdout.strip() == "1" else "live"


def session_pid(rec: dict) -> int:
    """The process a record's session runs as: the recorded worker, or the pane's process
    for a tmux window. 0 = unknown (a remote hand-over, a pane already gone). The pre-push
    guard compares it with its own ancestors to tell this session's record from another's."""
    if rec.get("tmux_window"):
        r = _tmux("display-message", "-p", "-t", rec["tmux_window"], "#{pane_pid}")
        text = r.stdout.strip()
        return int(text) if r.returncode == 0 and text.isdigit() else 0
    try:
        return int(rec.get("pid") or 0)
    except (TypeError, ValueError):
        return 0


def _record_files(root: Path) -> list[dict]:
    """The dispatch records as written — no liveness asked, nothing created;
    an unreadable entry (bad JSON, a directory named *.json) is skipped."""
    d = common_dir(root) / DISPATCH_DIR
    out = []
    for p in sorted(d.glob("*.json")) if d.is_dir() else []:
        if p.name == ISSUES_FILE:
            continue
        try:
            rec = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(rec, dict) and isinstance(rec.get("branch"), str) and rec["branch"]:
            out.append(rec)
    return out


def records(root: Path) -> list[dict]:
    out = []
    for rec in _record_files(root):
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


_URL = re.compile(r"https?://[^\s'\"<>)\]]+")


def handover_session(rec: dict) -> str:
    """The other host's session id or URL, read from what the hand-over
    printed (its stdout, or the tmux window's log): the policy's
    `phases.<phase>.handover_id` regex (group 1 if it has one), else the
    first URL. A starter that prints text instead of JSON still names its
    session somewhere in that text — this is where the steward finds it."""
    if not rec.get("remote"):
        return ""
    text = rec.get("handover") or ""
    log = Path(rec.get("log") or "")
    if log.is_file():
        try:
            text += "\n" + _ANSI.sub("", log.read_bytes()[:65536].decode("utf-8", "replace"))
        except OSError:
            pass
    pattern = rec.get("handover_id") or ""
    m = re.search(pattern, text) if pattern else _URL.search(text)
    if not m:
        return ""
    return (m.group(1) if m.groups() else m.group(0)).strip()


def last_output(rec: dict, lines: int = 1) -> tuple[str, int | None]:
    """What the worker shows: the live tmux screen for a tmux worker (escape
    codes are not words), else the log tail; and minutes since it wrote."""
    log = Path(rec.get("log") or "")
    mins = int((time.time() - log.stat().st_mtime) // 60) if log.is_file() else None
    if rec.get("tmux_window") and rec.get("state") in (None, "live", "dead", "remote"):
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
    full = None if remote else disk_refusal(root.parent)  # where ensure_worktree puts the worktree
    if full:
        print(f"dispatch: not starting — {full}", file=sys.stderr)
        return 3
    channel = policy.get("decision_channel")
    prompt = prompt_for(phase, issue, tier, branch, model, remote=remote,
                        channel=channel if isinstance(channel, str) and channel.strip() else None)
    argv = build_argv(policy, model, prompt, branch, issue, phase)
    if not remote:
        why = runnable(argv)
        if why and not dry_run:
            print(f"dispatch: cannot start: {why} — fix `command` in {POLICY}", file=sys.stderr)
            return 1
        argv = niced(policy, argv)
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
        if not _remote_head(root, branch):
            print(f"dispatch: {branch} is not on origin — a remote {phase} session needs the branch pushed first",
                  file=sys.stderr)
            return 3
        extra = {**pp["env"], "PROCESS_WORKER": branch, "PROCESS_PHASE": phase, "PROCESS_MODEL": model, "PROCESS_ISSUE": str(issue),
             "PROCESS_PHASE_BASE": phase_base(root, branch)}
        rec = {"branch": branch, "issue": issue, "phase": phase, "tier": tier, "model": model, "remote": True,
               "started": int(time.time()), "ts": _dt.datetime.now().isoformat(timespec="seconds"),
               "runner": runner, "handover_id": pp["handover_id"]}
        if runner == "tmux":
            # some hand-over CLIs refuse to start without a terminal (observed
            # downstream: a cloud-session start exited at once when detached) —
            # the tmux window is that terminal, and stays inspectable with log/say
            session = str(policy.get("tmux_session") or "workers")
            window = ("remote-" + branch.replace("/", "-").replace(".", "-"))[:40]
            log = _records_dir(root) / f"{branch.replace('/', '__')}-{phase}-{_dt.datetime.now():%Y%m%d-%H%M%S}.log"
            window_id, why = _tmux_start(session, window, root, argv, extra, log)
            if window_id is None:
                print(f"dispatch: remote start failed: {why}", file=sys.stderr)
                return 1
            rec.update({"tmux_window": window_id, "tmux_session": session, "tmux_name": window,
                        "log": str(log)})
            _write_record(root, branch, rec)
            _remember_issue(root, issue, branch)
            print(f"dispatch: handing {phase} for #{issue} on {branch} to another host with {model} from "
                  f"tmux {session}:{window} ({window_id}) — watch it with `dispatch.py log {branch}`; "
                  f"reports via origin (`tower.py --remote`)")
            return 0
        try:
            r = subprocess.run(argv, cwd=root, capture_output=True, text=True, timeout=300, env=_worker_env(extra))
        except (OSError, subprocess.TimeoutExpired) as exc:
            print(f"dispatch: remote start failed: {exc}", file=sys.stderr)
            return 1
        if r.returncode != 0:
            print(f"dispatch: remote start command exited {r.returncode}: {(r.stderr or r.stdout).strip()[-400:]}",
                  file=sys.stderr)
            return 1
        rec["handover"] = r.stdout.strip()[-400:]
        _write_record(root, branch, rec)
        _remember_issue(root, issue, branch)
        print(f"dispatch: handed {phase} for #{issue} on {branch} to another host with {model} — "
              f"reports via origin (`tower.py --remote`)" + (f"\n  {rec['handover']}" if rec["handover"] else ""))
        return 0
    wt = ensure_worktree(root, branch)
    log = _records_dir(root) / f"{branch.replace('/', '__')}-{phase}-{_dt.datetime.now():%Y%m%d-%H%M%S}.log"
    extra = {**pp["env"], "PROCESS_WORKER": branch, "PROCESS_PHASE": phase, "PROCESS_MODEL": model, "PROCESS_ISSUE": str(issue),
             "PROCESS_PHASE_BASE": phase_base(root, branch)}
    rec = {"branch": branch, "issue": issue, "phase": phase, "tier": tier, "model": model,
           "worktree": str(wt), "log": str(log), "started": int(time.time()),
           "ts": _dt.datetime.now().isoformat(timespec="seconds"), "runner": runner}
    if runner == "tmux":
        session = str(policy.get("tmux_session") or "workers")
        window = branch.replace("/", "-").replace(".", "-")[:40]
        window_id, why = _tmux_start(session, window, wt, argv, extra, log)
        if window_id is None:
            print(f"dispatch: {why}", file=sys.stderr)
            return 1
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
    _write_record(root, branch, rec)
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
        if r.get("remote") and r.get("tmux_window"):
            # the hand-over ran in a terminal: a dead window with a non-zero exit
            # means the other host never got the work — say so, never "remote"
            pane, code = _pane_state(r["tmux_window"]), _pane_exit(r["tmux_window"])
            failed = pane == "dead" and code not in ("", "0")
            print(f"- {r['branch']}: {r['phase']} #{r.get('issue')} {r.get('model')} another host, hand-over in "
                  f"{r.get('tmux_session')}:{r.get('tmux_name')} "
                  + (f"HAND-OVER FAILED (exit {code})" if failed else f"REMOTE (hand-over window {pane})")
                  + (f" · session: {sid}" if (sid := handover_session(r)) else "")
                  + (f" · {since} min ago: {last[-120:]}" if last else ""))
            continue
        where = ("another host" if r.get("remote") else
                 f"{r.get('tmux_session')}:{r.get('tmux_name')}" if r.get("tmux_window") else f"pid {r.get('pid')}")
        sid = handover_session(r)
        print(f"- {r['branch']}: {r['phase']} #{r.get('issue')} {r.get('model')} {where} "
              f"{r['state'].upper()} ({mins} min)" + (f" · session: {sid}" if sid else "")
              + (f" · {since} min ago: {last[-120:]}" if last else ""))
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
    if sid := handover_session(rec):
        head += f" — session {sid}"
    print(head + (f" — last write {mins} min ago" if mins is not None else ""))
    print(text or "(nothing yet)")
    return 0


SAY_RETRIES = 3
SAY_WAIT_S = 1.5
# the input line of an interactive harness: a `>` prompt, maybe inside a box
_PROMPT_LINE = re.compile(r"^[\s│|╭╰─]*>\s?(.*?)[\s│|]*$")
_sleep = time.sleep


def _screen(window_id: str) -> list[str] | None:
    r = _tmux("capture-pane", "-p", "-t", window_id)
    return [ln for ln in r.stdout.splitlines() if ln.strip()] if r.returncode == 0 else None


def _input_line(lines: list[str] | None, pattern: re.Pattern[str]) -> str | None:
    """What the worker's input line holds now — None when it cannot be read."""
    if lines is None:
        return None
    for ln in reversed(lines):  # the bottom-most prompt line; a long input wraps below it
        m = pattern.match(ln)
        if m:
            return m.group(1)
    return None


_PASTED = re.compile(r"^\[Pasted text")


_DIALOG = re.compile(r"^\s*[❯>]?\s*\d+\.\s+(Yes|No)\b|Do you want to|\(y/n\)|\[y/N\]", re.IGNORECASE | re.MULTILINE)


def _dialog_open(lines: list[str] | None, pattern: re.Pattern[str] = _PROMPT_LINE) -> bool:
    """A dialog replaces or sits below the input line; the same words in the
    transcript above it are the worker's text (a question asked in prose, an
    earlier message) — answering those is what `say` is for (refutation)."""
    if not lines:
        return False
    last_prompt = max((k for k, ln in enumerate(lines) if pattern.match(ln)), default=-1)
    below = lines[last_prompt + 1:] if last_prompt >= 0 else lines[-12:]
    return bool(_DIALOG.search("\n".join(below)))


def _still_typed(line: str, text: str) -> bool:
    shown = " ".join(line.split())
    if _PASTED.match(shown):
        return True  # the harness folded the typed text into a placeholder
    parts = [" ".join(p.split())[:20] for p in (text, text.splitlines()[-1] if text.splitlines() else "")]
    return any(head and shown.startswith(head) for head in parts)


def say(root: Path, branch: str, text: str) -> int:
    found = _load_record(root, branch)
    if found is None or not found[1].get("tmux_window"):
        print(f"dispatch: {branch} is not a tmux worker started here — nothing to type into", file=sys.stderr)
        return 2
    _p, rec = found
    state = _pane_state(rec["tmux_window"]) if rec["state"] == "remote" else rec["state"]
    if state != "live":
        print(f"dispatch: {branch} is {state} — nobody is listening", file=sys.stderr)
        return 3
    pattern = _PROMPT_LINE
    try:
        custom = load_policy(root).get("say_prompt")
        if isinstance(custom, str) and custom:
            compiled = re.compile(custom)
            if compiled.groups >= 1:
                pattern = compiled
            else:
                print("dispatch: say_prompt needs a group (what is still typed) — using the default",
                      file=sys.stderr)
    except (re.error, SystemExit):
        pass
    window = rec["tmux_window"]
    if _dialog_open(_screen(window), pattern):
        # typing now would answer the dialog, not reach the worker (refutation)
        print(f"dispatch: {branch} shows a dialog — nothing typed; answer it first: {text[:80]}",
              file=sys.stderr)
        return 5
    r = _tmux("send-keys", "-t", window, "-l", text)
    r2 = _tmux("send-keys", "-t", window, "Enter")
    if r.returncode != 0 or r2.returncode != 0:
        print(f"dispatch: send-keys failed: {(r.stderr or r2.stderr).strip()}", file=sys.stderr)
        return 1
    for attempt in range(SAY_RETRIES + 1):
        _sleep(SAY_WAIT_S * (attempt + 1))
        screen = _screen(window)
        line = _input_line(screen, pattern)
        if line is None:
            print(f"dispatch: said to {branch}: {text[:80]} (not verified — the input line could not be read)")
            return 0
        if not _still_typed(line, text):
            print(f"dispatch: said to {branch}: {text[:80]}")  # delivered, whatever the output says
            return 0
        if _dialog_open(screen, pattern):
            # still typed and a dialog opened: an Enter would answer it (refutation)
            print(f"dispatch: {branch} shows a dialog — not pressing Enter; the text is unsent: {text[:80]}",
                  file=sys.stderr)
            return 5
        if attempt < SAY_RETRIES:
            _tmux("send-keys", "-t", window, "Enter")  # a busy worker queues it now
    print(f"dispatch: {branch} — the text is still in the input line after {SAY_RETRIES} more Enter; "
          f"not delivered: {text[:80]}", file=sys.stderr)
    return 4


def stop(root: Path, branch: str, *, force: bool, keep_report: bool = False) -> int:
    found = _load_record(root, branch)
    if found is None:
        print(f"dispatch: {branch} was not started by this tool — stop only what you started", file=sys.stderr)
        return 2
    p, rec = found
    if rec["state"] == "remote":
        print(f"dispatch: {branch} runs on another host — stop it there; record removed here")
        p.unlink()
        return 0
    if rec["state"] == "unknown":
        print(f"dispatch: {branch} — tmux cannot be asked (is it on PATH?); the worker may still run — "
              "not stopped, record kept", file=sys.stderr)
        return 3
    if rec["state"] != "live":
        print(f"dispatch: {branch} is {rec['state']} — record removed")
        p.unlink()
        return 0
    wt = Path(rec["worktree"]) if rec.get("worktree") else None  # Path("") would be the cwd
    dirty = _out(wt, "status", "--porcelain") if wt is not None and wt.is_dir() else ""
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
    if not keep_report:
        try:
            _report.write_report(root, "idle", issue=rec.get("issue"),
                                 note=f"stopped by dispatch ({rec.get('phase')})", worker=branch)
        except SystemExit:
            pass
    p.unlink()
    print(f"dispatch: stopped {branch}")
    return 0


# --- the phase chain and its queue -----------------------------------------------------

BOOKKEEPING = ".process-work/"
JOURNAL = ".process-work/journal/"


def _queue_dir(root: Path) -> Path:
    d = _records_dir(root) / "queue"  # not beside the records: a branch named `queue` would collide
    d.mkdir(parents=True, exist_ok=True)
    return d


def _migrate_queue(root: Path) -> None:
    """The queue of an older dispatch (beside the records): carried over, not
    dropped — under the queue lock, so two processes do not race on it."""
    old, new = _records_dir(root) / QUEUE_FILE, _queue_path(root)
    if new.exists() or not old.exists():
        return
    try:
        data = json.loads(old.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if isinstance(data, list):
        new.write_text(json.dumps(data, indent=2), encoding="utf-8")
        old.unlink(missing_ok=True)


def _queue_path(root: Path) -> Path:
    return _queue_dir(root) / QUEUE_FILE


class _QueueLock:
    """One writer at a time for the queue — a steward tick, a manual `queue
    add` and a second drain would otherwise lose lines or start one twice."""

    def __init__(self, root: Path):
        self.root = root
        self.path = _queue_dir(root) / "queue.lock"
        self.fh = None

    def __enter__(self):
        import fcntl
        self.fh = open(self.path, "a+")
        fcntl.flock(self.fh.fileno(), fcntl.LOCK_EX)
        _migrate_queue(self.root)
        return self

    def __exit__(self, *_exc):
        import fcntl
        fcntl.flock(self.fh.fileno(), fcntl.LOCK_UN)
        self.fh.close()


def _valid_entry(e: object) -> dict | None:
    if not isinstance(e, dict) or e.get("phase") not in PHASES:
        return None
    def as_int(v: object) -> int | None:
        if isinstance(v, bool):
            return None
        if isinstance(v, int):
            return v
        return int(v) if isinstance(v, str) and v.isdigit() else None
    issue = as_int(e.get("issue"))
    tier = None if e.get("tier") is None else as_int(e.get("tier"))
    if issue is None or (e.get("tier") is not None and tier is None):
        return None
    branch = e.get("branch")
    if branch is not None and not isinstance(branch, str):
        return None
    return {"issue": issue, "phase": e["phase"], "tier": tier, "branch": branch}


def queue_load(root: Path) -> list[dict]:
    path = _queue_path(root)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError:
        return []
    except ValueError:
        data = None
    if not isinstance(data, list):
        aside = path.with_name(f"queue.corrupt-{time.time_ns()}-{os.getpid()}.json")
        path.replace(aside)
        print(f"dispatch: the queue was unreadable — kept as {aside.name}, starting empty", file=sys.stderr)
        return []
    out = []
    for e in data:
        v = _valid_entry(e)
        if v is None:
            print(f"dispatch: dropping an invalid queue line: {e!r}", file=sys.stderr)
        else:
            out.append(v)
    return out


def _queue_save(root: Path, entries: list[dict]) -> None:
    path = _queue_path(root)
    tmp = path.with_name(f"queue.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(entries, indent=2), encoding="utf-8")
    tmp.replace(path)


def _same_line(a: dict, b: dict) -> bool:
    return a["issue"] == b["issue"] and a["phase"] == b["phase"]


def queue_add(root: Path, *, issue: int, phase: str, tier: int | None, branch: str | None) -> None:
    with _QueueLock(root):
        entries = queue_load(root)
        entry = {"issue": int(issue), "phase": phase, "tier": tier, "branch": branch}
        if not any(_same_line(entry, e) for e in entries):  # one line per issue and phase
            entries.append(entry)
            _queue_save(root, entries)


def drain(root: Path) -> int:
    """Start every queued line the caps and lanes allow now, in order; a
    refused line stays queued and does not hold the ones behind it. Each
    start is saved at once, under the queue lock."""
    with _QueueLock(root):
        entries = queue_load(root)
        started = 0
        for e in list(entries):
            try:
                rc = start(root, issue=e["issue"], phase=e["phase"], tier=e.get("tier"),
                           branch=e.get("branch"), title=None, dry_run=False)
            except SystemExit as exc:
                print(f"dispatch: queued #{e['issue']} {e['phase']} could not start: {exc}", file=sys.stderr)
                rc = 1
            if rc == 0:
                entries.remove(e)
                started += 1
                _queue_save(root, entries)
        _queue_save(root, entries)
    print(f"dispatch: queue drained — {started} started, {len(entries)} waiting")
    return 0


def _commit_touches(root: Path, commit: str) -> list[str] | None:
    """The files a commit changes — a merge by what it adds of its own (`--cc`).
    `-z` through the owner of names (`check_review._names`): git quotes a
    non-ASCII name otherwise, and the file matches nothing it is compared to.
    None when git cannot tell — never "touches nothing"."""
    import check_review as _review  # noqa: PLC0415  (lazily, as tower imports dispatch)
    names = _review._names(_review._git_bytes(
        root, "diff-tree", "-z", "--no-commit-id", "--name-only", "-r", "--root", "--cc", commit))
    return sorted(names) if names is not None else None


_REVIEW_ADDED = re.compile(r"^\+\s*(?:[-*+]\s+)?REVIEW\s", re.MULTILINE)


def _is_attestation(root: Path, commit: str) -> bool:
    """A commit that records a REVIEW line in the journal — a journal note
    written mid-work is not one."""
    return bool(_REVIEW_ADDED.search(_out(root, "show", "--format=", commit, "--", JOURNAL)))


def _tip_on_origin(root: Path, branch: str, *, fetch: bool) -> str:
    sha = _remote_head(root, branch)
    if not sha:
        return ""
    if fetch and _git(root, "fetch", "-q", "origin", f"refs/heads/{branch}").returncode != 0:
        return ""
    return sha if _git(root, "cat-file", "-e", f"{sha}^{{commit}}").returncode == 0 else ""


def _integration_base(root: Path, tip: str) -> str:
    for ref in ("origin/main", "origin/master", "main", "master"):
        base = _out(root, "merge-base", tip, ref)
        if base:
            return base
    return ""


def new_code_on_origin(root: Path, branch: str, *, fetch: bool = True) -> bool | None:
    """Does origin carry code on `branch` beyond its last attestation? None
    when origin cannot be asked. A `pushed` report over an attestation-only
    push is premature (downstream: two such reports sent workers to review
    nothing)."""
    tip = _tip_on_origin(root, branch, fetch=fetch)
    if not tip:
        return None
    base = _integration_base(root, tip)
    listed = _git(root, "rev-list", tip, *([f"^{base}"] if base else []))
    if listed.returncode != 0:
        return None  # a commit list git cannot give is no "nothing beyond the attestation"
    for c in listed.stdout.split():  # newest first
        touched = _commit_touches(root, c)
        if touched is None:
            return None  # a commit git cannot read is no "attestation only"
        if any(not f.startswith(BOOKKEEPING) for f in touched):
            return True
        if _is_attestation(root, c):
            return False
    return False


_OPEN_TASK = re.compile(r"^\s*[-*] \[ \]", re.MULTILINE)


_FENCE = re.compile(r"^(```|~~~).*?^\1[^\n]*$", re.MULTILINE | re.DOTALL)


def _own_plans_on_origin(root: Path, branch: str, local: bool = False) -> tuple[str, list[str]]:
    """(origin's tip — or, with `local`, origin's tip as last fetched, no
    network — and the plans this branch added: active, archived or Spec Kit
    tasks); another work's plan the branch only touched is not its own. A
    task ticked but not pushed is open for both: what counts is what origin
    holds (refutation: the local branch read a worker finished that chain
    never advanced)."""
    tip = (_out(root, "rev-parse", "--verify", "-q", f"refs/remotes/origin/{branch}") if local
           else _remote_head(root, branch))
    if not tip:
        return "", []
    base = _integration_base(root, tip)
    if not base:
        return tip, []
    # added by the branch, git's rename detection on: another work's plan the
    # branch archived or moved is not its own (refutation); a rename pairing
    # an old plan with a new one for other issues is a new plan
    # -z through the owner (`check_review.name_status`): a plan with a
    # non-ASCII name came back quoted and was never the branch's
    import check_review as _review  # noqa: PLC0415
    status = _review.name_status(_review._git_bytes(root, "diff", "--name-status", "-M", "-z",
                                                    f"{base}...{tip}")) or []
    added = []
    for letter, source, path in status:
        if letter == "A":
            added.append(path)
        elif letter == "R":
            before, after = _out(root, "show", f"{base}:{source}"), _out(root, "show", f"{tip}:{path}")
            if set(_ISSUE.findall(before)) != set(_ISSUE.findall(after)):
                added.append(path)
    plans = [f for f in added if (f.startswith(".process-work/plans/") and "/archive/" not in f
                                  and f.endswith(".md")) or re.fullmatch(r"specs/[^/]+/tasks\.md", f)]
    return tip, plans


_ISSUE = re.compile(r"^\s*(?:[-*+]\s+)?[*_]*issue[*_]*\s*:\s*(\S+)", re.IGNORECASE | re.MULTILINE)


def work_complete_on_origin(root: Path, branch: str, local: bool = False) -> bool | None:
    """Are the tasks of the branch's own plans all ticked at origin's tip
    (with `local`: origin's tip as last fetched — no network)? `pushed` is reported at the FIRST push — the tasks tell when
    the work is done. A task inside a fenced example does not count. None
    when the branch added no plan to read, or git cannot tell."""
    tip, plans = _own_plans_on_origin(root, branch, local)
    if not plans:
        return None
    return not any(_OPEN_TASK.search(_FENCE.sub("", _out(root, "show", f"{tip}:{f}"))) for f in plans)


_TIER = re.compile(r"^\s*(?:[-*+]\s+)?[*_]*tier[*_]*\s*:\s*[*_]*\s*(\d+)\b", re.IGNORECASE | re.MULTILINE)


def plan_tier_on_origin(root: Path, branch: str) -> int | None:
    """The tier the branch's own plan declares — the next phase runs on the
    model for that tier, not the plan session's (often unset) one."""
    tip, plans = _own_plans_on_origin(root, branch)
    tiers = [int(m.group(1)) for f in plans if f.endswith(".md") and not f.endswith("tasks.md")
             for m in [_TIER.search(_FENCE.sub("", _out(root, "show", f"{tip}:{f}")))] if m]
    return max(tiers) if tiers else None


def attest_on_origin(root: Path, branch: str) -> bool:
    """Is the branch's local head — its attestation — what origin holds?"""
    local = _out(root, "rev-parse", "--verify", "-q", f"refs/heads/{branch}")
    if not local or _remote_head(root, branch) != local:
        return False
    return _is_attestation(root, local)


def session_report(rec: dict, reports: list[dict]) -> dict | None:
    """The latest report of a session's branch written since the session
    started — an older one is the previous phase's word (a plan session's
    `planned` is not what its execute session said)."""
    started = int(rec.get("started") or 0)
    best = None
    for r in reports:  # file order: of two reports in one second, the later line wins
        if r.get("worker") == rec.get("branch") and int(r.get("epoch") or 0) >= started \
                and (best is None or int(r.get("epoch") or 0) >= int(best.get("epoch") or 0)):
            best = r
    return best


def phase_over(root: Path, rec: dict, rep: dict | None, *, local: bool = False) -> bool | None:
    """Has this session's phase ended? Its own final report says so — a plan
    `planned`, a review `review-pass` or `blocked` (it stops either way), any
    phase `done` or `idle` — or, for an execute session, `pushed` with every
    task of the branch's own plans ticked on origin (with `local`: as last
    fetched — no network). None when that cannot be told."""
    state, phase = (rep or {}).get("state"), rec.get("phase")
    if state in ("done", "idle"):
        return True
    if (phase, state) in (("plan", "planned"), ("review", "review-pass"), ("review", "blocked")):
        return True
    if phase == "execute" and state == "pushed":
        return work_complete_on_origin(root, rec["branch"], local)
    return False


class _ChainLock(_QueueLock):
    def __init__(self, root: Path):
        super().__init__(root)
        self.path = _queue_dir(root) / "chain.lock"


def chain(root: Path, *, dry_run: bool = False) -> int:
    """One chain run at a time (two overlapping runs judged stale snapshots
    and stopped a fresh session — refutation)."""
    with _ChainLock(root):
        return _chain(root, dry_run=dry_run)


def _chain(root: Path, *, dry_run: bool = False) -> int:
    reports = _report.read_reports(root)
    for rec in records(root):
        if rec.get("remote") or rec.get("state") == "unknown":
            continue  # liveness lives elsewhere, or cannot be asked: act on nothing
        branch, phase = rec["branch"], rec.get("phase")
        rep = session_report(rec, reports)
        if rep is None:
            continue  # a report from before this session started is not this session's word
        try:
            issue = int(rec["issue"])
        except (KeyError, TypeError, ValueError):
            print(f"dispatch: {branch} — record without an issue, chain skips it", file=sys.stderr)
            continue
        state, nxt = rep.get("state"), None
        if state == "planned" and phase == "plan":
            nxt = "execute"
        elif state == "pushed" and phase == "execute":
            if dry_run:
                print(f"dispatch: would check {branch} on origin (tasks done, code beyond the attestation)")
                continue
            done, code = work_complete_on_origin(root, branch), new_code_on_origin(root, branch)
            if code is None or done is None:
                print(f"dispatch: {branch} reported pushed — cannot read its plan or code on origin; "
                      "not queuing a review", file=sys.stderr)
                continue
            if not done:
                print(f"dispatch: {branch} reported pushed — its plan still has open tasks; the worker is at it")
                continue  # `pushed` comes at the first push
            if not code:
                print(f"dispatch: {branch} reported pushed, but origin has no code beyond its last "
                      "attestation — not queuing a review")
                continue
            nxt = "review"
        elif state == "review-pass" and phase == "review":
            if not attest_on_origin(root, branch):
                print(f"dispatch: {branch} passed review — waiting for its attestation on origin")
                continue
            print(f"dispatch: {branch} passed review, attestation on origin — a train candidate")
        else:
            continue  # blocked and everything else: the steward decides
        wt = Path(rec["worktree"]) if rec.get("worktree") else None  # Path("") would be the cwd
        if wt is not None and wt.is_dir() and _out(wt, "status", "--porcelain"):
            print(f"dispatch: {branch} has uncommitted work — the worker commits first; chain waits",
                  file=sys.stderr)
            continue
        if dry_run:
            print(f"dispatch: would stop {branch} ({phase})" + (f" and queue {nxt}" if nxt else ""))
            continue
        current = _load_record(root, branch)
        if current is None or current[1].get("started") != rec.get("started") or current[1].get("phase") != phase:
            continue  # the session changed since it was judged
        if stop(root, branch, force=False, keep_report=True) != 0:
            continue
        if nxt:
            tier = rec.get("tier") if rec.get("tier") is not None else plan_tier_on_origin(root, branch)
            try:
                queue_add(root, issue=issue, phase=nxt, tier=tier, branch=branch)
            except OSError as exc:
                print(f"dispatch: {branch} stopped, but {nxt} could not be queued ({exc}) — queue it by hand: "
                      f"dispatch.py queue add --issue {issue} --phase {nxt}"
                      + (f" --tier {tier}" if tier is not None else "") + f" --branch {branch}", file=sys.stderr)
    return 0 if dry_run else drain(root)


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
    ch = sub.add_parser("chain")
    ch.add_argument("--dry-run", action="store_true")
    qu = sub.add_parser("queue")
    qsub = qu.add_subparsers(dest="queue_command", required=True)
    qa = qsub.add_parser("add")
    qa.add_argument("--issue", type=int, required=True)
    qa.add_argument("--phase", choices=PHASES, required=True)
    qa.add_argument("--tier", type=int)
    qa.add_argument("--branch")
    qsub.add_parser("list")
    sub.add_parser("drain")
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
    if a.command == "chain":
        return chain(root, dry_run=a.dry_run)
    if a.command == "queue":
        if a.queue_command == "add":
            queue_add(root, issue=a.issue, phase=a.phase, tier=a.tier, branch=a.branch)
        for e in queue_load(root):
            print(f"#{e['issue']} {e['phase']}" + (f" tier {e['tier']}" if e.get("tier") is not None else "")
                  + (f" on {e['branch']}" if e.get("branch") else ""))
        return 0
    if a.command == "drain":
        return drain(root)
    policy = load_policy(root)
    for ph in PHASES:
        print(f"{ph}: {model_for(policy, a.tier, ph)}")
    print(f"command: {policy['command']}  (runner {policy.get('runner', 'detached')}, "
          f"max_workers {max_workers(policy)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
