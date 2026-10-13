#!/usr/bin/env python3
"""The one writer of the gate event log: one JSON line per check run, kept in
the common git directory (`process-gate-events.jsonl`), shared by every
worktree and never committed. The gate runner and dispatch's plan-drift check
write here; `process_kpis.py nodes` reads it. The log observes: an unwritable
log loses an observation, never a verdict."""
from __future__ import annotations

import datetime as _dt
import json
import os
import subprocess
from pathlib import Path

EVENTS_NAME = "process-gate-events.jsonl"
MAX_BYTES = 5_000_000  # then the log rolls over to .1 (one generation kept)


def git_out(root: Path, *args: str) -> str | None:
    try:
        proc = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return proc.stdout.strip() if proc.returncode == 0 else None


def events_path(root: Path) -> Path | None:
    common = git_out(root, "rev-parse", "--git-common-dir")
    if not common:
        return None
    path = Path(common)
    return (path if path.is_absolute() else root / path) / EVENTS_NAME


def append(path: Path | None, row: dict) -> None:
    """Append `row` with a millisecond UTC timestamp in front."""
    if path is None:
        return
    line = {"ts": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="milliseconds"), **row}
    try:
        if path.is_file() and path.stat().st_size > MAX_BYTES:
            os.replace(path, path.with_name(path.name + ".1"))
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(line) + "\n")
    except Exception:  # noqa: BLE001 — an unwritable log loses an observation, never a verdict
        pass
