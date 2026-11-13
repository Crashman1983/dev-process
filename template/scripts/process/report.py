#!/usr/bin/env python3
"""report — a worker's state transition, one line, to the tower.

    uv run scripts/process/report.py <state> [--issue N] [--note TEXT] [--worker NAME]

States: planned | pushed | review-pass | blocked | done | idle. Five or six
lines per issue, sent only when the state actually changes — never a
running commentary. The tower (`tower.py`) reads them, shows the latest
state per worker, and treats a worker with no report and no commit for an
hour as stale.

Where it lands: `<git common dir>/process-tower/reports.jsonl` — shared by
every worktree of this clone on this machine, never committed, one line
per report: {"ts","host","worker","branch","issue","state","note","cwd"} and,
where the issue has one, its "track" (PROCESS_TRACK).

More than one host (the steward on one machine, a detached worker on
another): `--sync` (or PROCESS_REPORT_SYNC=1) publishes this host's file
as a blob under `refs/process/reports/<host>` on origin — git is the one
channel every host already has; no ssh, nothing committed to a branch.
The tower fetches those refs (`tower.py --remote`) and merges every
host's reports. Host name: PROCESS_HOST or the machine's hostname.

`pushed` is checked, not believed: the branch must be on origin with this
worktree's HEAD, and — when dispatch recorded where the phase began
(PROCESS_PHASE_BASE, the branch's origin commit at phase start) — origin
must have moved past that point. A premature `pushed` let the steward
start the next phase on a branch that held none of this phase's work
(observed downstream three times in one day). `--force` records it anyway,
marked unverified in the note — for an origin that is unreachable.

The worker is checked too: the train, the tower and dispatch find reports
by `worker == branch`, so `--worker`, PROCESS_WORKER and the current-branch
fallback must name a local or remote-tracking branch (a detached `HEAD`
names none) — else exit 2. `done` and `idle` also take a deleted branch
that `phases/branches.json` or a former report knows: the merge may have
removed it before the worker said so.
Stdlib only."""
from __future__ import annotations

import argparse
import json
import os
import socket
import re
import subprocess
import sys
import time
from pathlib import Path

# `failed`: the run itself broke (crash, timeout, signal) — not `blocked`, which is a
# question or a red gate the worker hands over (#270)
STATES = ("planned", "pushed", "review-pass", "blocked", "failed", "done", "idle")
REPORTS_DIR = "process-tower"
REPORTS_FILE = "reports.jsonl"
REPORT_REFS = "refs/process/reports"


def _git(root: Path, *args: str) -> str:
    try:
        r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return r.stdout.strip() if r.returncode == 0 else ""


def reports_path(root: Path) -> Path | None:
    common = _git(root, "rev-parse", "--git-common-dir")
    if not common:
        return None
    p = Path(common)
    if not p.is_absolute():
        p = root / p
    d = p / REPORTS_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d / REPORTS_FILE


def host_name() -> str:
    raw = os.environ.get("PROCESS_HOST") or socket.gethostname() or "host"
    # the whole name, sanitised — `build.eu` and `build.us` must not share a ref
    return "".join(ch if ch.isalnum() or ch in "-_." else "-" for ch in raw)[:64]


def default_worker(root: Path) -> str:
    return (os.environ.get("PROCESS_WORKER") or _git(root, "rev-parse", "--abbrev-ref", "HEAD")
            or root.name)


UNMEASURED = "not measured"


def efforts() -> tuple[str, ...]:
    """The effort levels — dispatch owns them (imported late: dispatch imports this module)."""
    from dispatch import EFFORTS
    return EFFORTS


def _env_effort() -> str:
    """PROCESS_EFFORT when it names a level; another value is noted and left out."""
    e = os.environ.get("PROCESS_EFFORT", "").strip()
    if e and e not in efforts():
        print(f"report: PROCESS_EFFORT={e!r} is not one of {', '.join(efforts())} — not recorded", file=sys.stderr)
        return ""
    return e


EXECUTION = ("delegate", "retain-context")  # a packet's mode (`/plan`, `/execute`); process_kpis.py cuts by it


USAGE_KEYS = ("input", "cached", "output", "cost_usd")


_COUNT = re.compile(r"[0-9]+")
_DECIMAL = re.compile(r"[0-9]+(?:\.[0-9]+)?")


def parse_usage(text: str) -> dict:
    """`input=<n>,cached=<n>,output=<n>[,cost_usd=<x>]` → a dict; ValueError names what
    is wrong. A harness without transcripts the dispatch reader knows (a remote host,
    another CLI) states its usage this way (#270)."""
    out: dict = {}
    for part in (p.strip() for p in text.split(",") if p.strip()):
        key, eq, value = part.partition("=")
        if not eq or key not in USAGE_KEYS:
            raise ValueError(f"{part!r} is not one of {', '.join(f'{k}=' for k in USAGE_KEYS)}")
        if key in out:
            raise ValueError(f"{key} twice")
        # plain ASCII digits only: float() takes nan, inf and `1_0`, int() takes `١٢`
        if not (_DECIMAL if key == "cost_usd" else _COUNT).fullmatch(value):
            raise ValueError(f"{key}={value!r} is no non-negative number")
        out[key] = float(value) if key == "cost_usd" else int(value)
    for key in ("input", "output"):
        if key not in out:
            raise ValueError(f"{key}= is missing")
    return out


def write_report(root: Path, state: str, *, issue: int | None, note: str, worker: str | None,
                 model: str | None = None, effort: str | None = None, execution: str | None = None,
                 usage: dict | None = None, track: str | None = None) -> dict:
    """One report line into this host's file. `track` (or PROCESS_TRACK, which dispatch sets from the
    issue's phase history) names the issue's track of the mandate's `steering` block; absent when
    neither says one (v2.97)."""
    # never empty: an empty model was indistinguishable from a lost field downstream
    model = (model or os.environ.get("PROCESS_MODEL") or "").strip()
    if not model:
        model = UNMEASURED
        print(f"report: model {UNMEASURED} — pass --model <id> (or set PROCESS_MODEL)", file=sys.stderr)
    record = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "epoch": int(time.time()),
        "host": host_name(),
        "worker": worker or default_worker(root),
        "branch": _git(root, "rev-parse", "--abbrev-ref", "HEAD"),
        "issue": issue,
        "state": state,
        "model": model,
        # the cell's reasoning effort when dispatch set one; absent: the harness default
        **({"effort": e} if (e := effort or _env_effort()) else {}),
        "phase": os.environ.get("PROCESS_PHASE") or "",
        "note": note.strip()[:1000],
        "cwd": str(root),
        **({"execution": execution} if execution else {}),
        **({"usage": usage} if usage else {}),
        **({"track": tr} if (tr := (track or os.environ.get("PROCESS_TRACK") or "").strip()) else {}),
    }
    p = reports_path(root)
    if p is None:
        raise SystemExit("report: not a git clone — nowhere shared to write")
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def _parse(text: str, host: str | None) -> list[dict]:
    """The records of one file or published ref. A record its readers cannot key or
    order — no non-empty `worker` string, an `epoch` that is no number (a bool is
    none) — is skipped like an unparsable line: another host's ref is data. A record
    without `epoch` stays: its readers order it first (`get("epoch", 0)`) and read
    `ts`, as older ledgers carry it."""
    out: list[dict] = []
    for line in text.splitlines():
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if not isinstance(rec, dict):
            continue
        worker, epoch = rec.get("worker"), rec.get("epoch", 0)
        if not (isinstance(worker, str) and worker
                and isinstance(epoch, (int, float)) and not isinstance(epoch, bool)):
            continue
        if rec.get("state") in STATES:
            rec.setdefault("host", host or "?")
            out.append(rec)
    return out


def read_reports(root: Path, *, remote: bool = False) -> list[dict]:
    """This host's file, plus — with `remote` — every other host's published
    ref (fetch them first: `fetch_reports`). Own host: the file wins."""
    p = reports_path(root)
    out: list[dict] = []
    if p is not None and p.is_file():
        out += _parse(p.read_text(encoding="utf-8", errors="replace"), host_name())
    if remote:
        refs = _git(root, "for-each-ref", "--format=%(refname)", REPORT_REFS + "/")
        for ref in refs.splitlines():
            host = ref.rsplit("/", 1)[-1]
            if host == host_name():
                continue
            out += _parse(_git(root, "cat-file", "-p", ref), host)
    return out


_GIT_ENV = dict(os.environ, GIT_TERMINAL_PROMPT="0")


def _run(argv: list[str], timeout: float = 60) -> bool:
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                              env=_GIT_ENV).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def fetch_reports(root: Path, remote: str = "origin", timeout: float = 60) -> bool:
    """Fetch every host's published reports; `timeout` bounds the call in seconds (dispatch asks
    with 15 before it counts the work in progress)."""
    return _run(["git", "-C", str(root), "fetch", "--quiet", remote, f"+{REPORT_REFS}/*:{REPORT_REFS}/*"],
                timeout)


def sync_reports(root: Path, remote: str = "origin", timeout: float = 60) -> bool:
    """Publish this host's reports file as a blob ref on the remote — the whole file, which only
    grows, so a later sync carries every earlier line. `timeout` bounds each git call."""
    p = reports_path(root)
    if p is None or not p.is_file():
        return False
    blob = _git(root, "hash-object", "-w", str(p))
    if not blob:
        return False
    ref = f"{REPORT_REFS}/{host_name()}"
    if not _run(["git", "-C", str(root), "update-ref", ref, blob], timeout):
        return False
    return _run(["git", "-C", str(root), "push", "--quiet", "--force", remote, f"{ref}:{ref}"], timeout)


def publish_if_steered(root: Path, timeout: float = 15) -> bool | None:
    """Publish this host's reports when the mandate sets `steering`: the WIP count of the
    other host (`tower.in_progress`) sees a `done` only once it is published. None when
    there is no steering block (nothing to publish for); else whether the sync went through."""
    try:
        from optimize import steering  # noqa: PLC0415 — the block's one reader
        conf, _problems = steering(root)
    except Exception:  # noqa: BLE001 — bookkeeping: an unreadable mandate publishes nothing
        return None
    if not conf:
        return None
    return sync_reports(root, timeout=timeout)


def pushed_refusal(root: Path, remote: str = "origin") -> str | None:
    """Why a `pushed` report would be false right now — None when it is true."""
    branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
    if not branch or branch == "HEAD":
        return "HEAD is detached — `pushed` names a branch"
    head = _git(root, "rev-parse", "HEAD")
    line = _git(root, "ls-remote", "--heads", remote, branch)
    on_origin = line.split()[0] if line else ""
    if not on_origin:
        return f"{branch} is not on {remote} (or {remote} is unreachable) — push first"
    if on_origin != head and subprocess.run(
            ["git", "-C", str(root), "merge-base", "--is-ancestor", head, on_origin],
            capture_output=True).returncode != 0:
        return f"{branch} has commits that are not on {remote} — push first"
    base = os.environ.get("PROCESS_PHASE_BASE", "").strip()
    if base and on_origin == base:
        return (f"no new commit on {remote}/{branch} since this phase started ({base[:10]}) — "
                f"commit and push the phase's work first")
    return None


# `done` and `idle` may name a branch that is gone: the merge deleted it before the worker
# said so (`finish`, `commands/report.md`) — for a name dispatch or a former report knows
_AFTER_THE_BRANCH = ("done", "idle")


def _is_branch(root: Path, name: str) -> bool:
    """A local branch `name`, or a remote-tracking `<remote>/name`. `HEAD` is none:
    a detached checkout names no branch, and `<remote>/HEAD` is a pointer."""
    if not name or name == "HEAD":
        return False
    if _git(root, "rev-parse", "--verify", "--quiet", f"refs/heads/{name}^{{commit}}"):
        return True
    tracking = _git(root, "for-each-ref", "--format=%(refname)", "refs/remotes/")
    return any(ref.removeprefix("refs/remotes/").partition("/")[2] == name for ref in tracking.splitlines())


def _known_worker(root: Path, name: str) -> bool:
    """A name dispatch placed issues on (`phases/branches.json`) or a former report carries
    — this host's or a fetched one."""
    if any(rec.get("worker") == name for rec in read_reports(root, remote=True)):
        return True
    from dispatch import BRANCH_INDEX, DISPATCH_DIR, common_dir  # late: dispatch imports this module
    try:
        index = json.loads((common_dir(root) / DISPATCH_DIR / "phases" / BRANCH_INDEX).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(index, dict) and name in index


def worker_refusal(root: Path, state: str, worker: str) -> str | None:
    """Why `worker` cannot carry this report — None when it may. The train, the tower and
    dispatch find a worker's reports by `worker == branch`; a report under another name is
    never read."""
    if _is_branch(root, worker) or (state in _AFTER_THE_BRANCH and worker != "HEAD"
                                    and _known_worker(root, worker)):
        return None
    return f"worker {worker} is no branch — the train and the tower match reports by branch"


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="report.py", description=__doc__.split("\n\n")[0])
    p.add_argument("state", choices=STATES)
    p.add_argument("--issue", type=int)
    p.add_argument("--note", default="")
    p.add_argument("--worker", help="the branch (default: PROCESS_WORKER or the current branch); it must "
                                     "be a local or remote-tracking branch — `done` and `idle` also take a "
                                     "deleted one that dispatch or a former report knows")
    p.add_argument("--model", help="the model doing this phase (default: PROCESS_MODEL) — what the KPIs cut by")
    p.add_argument("--effort", help="the reasoning effort of this phase's cell (default: PROCESS_EFFORT)")
    p.add_argument("--execution", choices=EXECUTION,
                   help="the packet's mode — delegated to a subagent or kept in this session (`/execute`)")
    p.add_argument("--usage", help="this phase's tokens where no transcript records them: "
                                    "input=<n>,cached=<n>,output=<n>[,cost_usd=<x>]")
    p.add_argument("--root", default=".")
    p.add_argument("--force", action="store_true",
                   help="record `pushed` without the origin check (marked unverified)")
    p.add_argument("--sync", action="store_true",
                   help="publish this host's reports to origin (refs/process/reports/<host>)")
    a = p.parse_args(argv)
    root = Path(a.root).resolve()
    if a.effort is not None and a.effort not in efforts():
        print(f"report: --effort {a.effort!r} is not one of {', '.join(efforts())}", file=sys.stderr)
        return 2
    usage = None
    if a.usage:
        try:
            usage = parse_usage(a.usage)
        except ValueError as exc:
            print(f"report: --usage {exc}", file=sys.stderr)
            return 2
    if _git(root, "rev-parse", "--git-dir"):  # outside a clone, write_report names that
        worker = a.worker or default_worker(root)
        refused = worker_refusal(root, a.state, worker)
        if refused:
            print(f"report: {refused}", file=sys.stderr)
            return 2
    note = a.note
    if a.state == "pushed":
        why = pushed_refusal(root)
        if why and not a.force:
            print(f"report: refusing `pushed` — {why}", file=sys.stderr)
            return 2
        if why:
            note = f"[unverified: {why}] {note}".strip()
    rec = write_report(root, a.state, issue=a.issue, note=note, worker=a.worker, model=a.model, effort=a.effort,
                       execution=a.execution, usage=usage)
    print(f"report: {rec['worker']}@{rec['host']} → {rec['state']}"
          + (f" #{rec['issue']}" if rec["issue"] else "") + (f" — {rec['note']}" if rec["note"] else ""))
    if a.sync or os.environ.get("PROCESS_REPORT_SYNC") == "1":
        print("report: published to origin" if sync_reports(root)
              else "report: publish to origin failed (kept locally; the tower reads it on this host)",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
