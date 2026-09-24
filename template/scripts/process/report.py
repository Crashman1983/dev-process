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
per report: {"ts","host","worker","branch","issue","state","note","cwd"}.

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
Stdlib only."""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

STATES = ("planned", "pushed", "review-pass", "blocked", "done", "idle")
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


def write_report(root: Path, state: str, *, issue: int | None, note: str, worker: str | None,
                 model: str | None = None) -> dict:
    record = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "epoch": int(time.time()),
        "host": host_name(),
        "worker": worker or default_worker(root),
        "branch": _git(root, "rev-parse", "--abbrev-ref", "HEAD"),
        "issue": issue,
        "state": state,
        "model": model or os.environ.get("PROCESS_MODEL") or "",
        "phase": os.environ.get("PROCESS_PHASE") or "",
        "note": note.strip()[:1000],
        "cwd": str(root),
    }
    p = reports_path(root)
    if p is None:
        raise SystemExit("report: not a git clone — nowhere shared to write")
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def _parse(text: str, host: str | None) -> list[dict]:
    out: list[dict] = []
    for line in text.splitlines():
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if isinstance(rec, dict) and rec.get("state") in STATES:
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


def fetch_reports(root: Path, remote: str = "origin") -> bool:
    return _run(["git", "-C", str(root), "fetch", "--quiet", remote, f"+{REPORT_REFS}/*:{REPORT_REFS}/*"])


def sync_reports(root: Path, remote: str = "origin") -> bool:
    """Publish this host's reports file as a blob ref on the remote."""
    p = reports_path(root)
    if p is None or not p.is_file():
        return False
    blob = _git(root, "hash-object", "-w", str(p))
    if not blob:
        return False
    ref = f"{REPORT_REFS}/{host_name()}"
    if not _run(["git", "-C", str(root), "update-ref", ref, blob]):
        return False
    return _run(["git", "-C", str(root), "push", "--quiet", "--force", remote, f"{ref}:{ref}"])


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


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="report.py", description=__doc__.split("\n\n")[0])
    p.add_argument("state", choices=STATES)
    p.add_argument("--issue", type=int)
    p.add_argument("--note", default="")
    p.add_argument("--worker", help="name (default: PROCESS_WORKER or the branch)")
    p.add_argument("--model", help="the model doing this phase (default: PROCESS_MODEL) — what the KPIs cut by")
    p.add_argument("--root", default=".")
    p.add_argument("--force", action="store_true",
                   help="record `pushed` without the origin check (marked unverified)")
    p.add_argument("--sync", action="store_true",
                   help="publish this host's reports to origin (refs/process/reports/<host>)")
    a = p.parse_args(argv)
    root = Path(a.root).resolve()
    note = a.note
    if a.state == "pushed":
        why = pushed_refusal(root)
        if why and not a.force:
            print(f"report: refusing `pushed` — {why}", file=sys.stderr)
            return 2
        if why:
            note = f"[unverified: {why}] {note}".strip()
    rec = write_report(root, a.state, issue=a.issue, note=note, worker=a.worker, model=a.model)
    print(f"report: {rec['worker']}@{rec['host']} → {rec['state']}"
          + (f" #{rec['issue']}" if rec["issue"] else "") + (f" — {rec['note']}" if rec["note"] else ""))
    if a.sync or os.environ.get("PROCESS_REPORT_SYNC") == "1":
        print("report: published to origin" if sync_reports(root)
              else "report: publish to origin failed (kept locally; the tower reads it on this host)",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
