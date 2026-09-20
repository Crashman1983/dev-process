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
per report: {"ts","worker","branch","issue","state","note","cwd"}. A
worker on another machine reaches the tower by message, not by file.
Stdlib only."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

STATES = ("planned", "pushed", "review-pass", "blocked", "done", "idle")
REPORTS_DIR = "process-tower"
REPORTS_FILE = "reports.jsonl"


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


def default_worker(root: Path) -> str:
    return (os.environ.get("PROCESS_WORKER") or _git(root, "rev-parse", "--abbrev-ref", "HEAD")
            or root.name)


def write_report(root: Path, state: str, *, issue: int | None, note: str, worker: str | None) -> dict:
    record = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "epoch": int(time.time()),
        "worker": worker or default_worker(root),
        "branch": _git(root, "rev-parse", "--abbrev-ref", "HEAD"),
        "issue": issue,
        "state": state,
        "note": note.strip()[:240],
        "cwd": str(root),
    }
    p = reports_path(root)
    if p is None:
        raise SystemExit("report: not a git clone — nowhere shared to write")
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def read_reports(root: Path) -> list[dict]:
    p = reports_path(root)
    if p is None or not p.is_file():
        return []
    out: list[dict] = []
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if isinstance(rec, dict) and rec.get("state") in STATES:
            out.append(rec)
    return out


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="report.py", description=__doc__.split("\n\n")[0])
    p.add_argument("state", choices=STATES)
    p.add_argument("--issue", type=int)
    p.add_argument("--note", default="")
    p.add_argument("--worker", help="name (default: PROCESS_WORKER or the branch)")
    p.add_argument("--root", default=".")
    a = p.parse_args(argv)
    rec = write_report(Path(a.root).resolve(), a.state, issue=a.issue, note=a.note, worker=a.worker)
    print(f"report: {rec['worker']} → {rec['state']}"
          + (f" #{rec['issue']}" if rec["issue"] else "") + (f" — {rec['note']}" if rec["note"] else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
