#!/usr/bin/env python3
"""Test lanes: one visible, bounded queue per host — instead of agents in
parallel worktrees thrashing one CPU, or one agent sitting blind in an hour's
wait (`docs/process/testing.md`, "Test lanes are a shared resource").

    lane.py run [--lane NAME] [--wait SECONDS] [--label TEXT] [--no-nice] -- CMD...
    lane.py wait [--lane NAME] [--wait SECONDS] [--quiet]   # until free, run nothing
    lane.py status                                          # who holds which lane

Lanes come from `docs/process/testing.local.json` (`lanes`; default `scoped`
for short runs, `full` for the train's suite, which yields CPU with `nice`).
Runs within one lane are serialised by an exclusive `fcntl.flock` on
`<dir>/test-lane-<lane>.lock`; the holder is named in `<lane>.status` next to
it. The lock is the truth — a killed holder frees the lane with its process.
The directory is `PROCESS_LANE_DIR`, else the config's `lane_dir`, else
`$XDG_STATE_HOME/process-lanes` (`~/.local/state/process-lanes`): one queue per
host, across clones. A project that kept its own lane script uses the same
file names and status record, so both share one lock on a host.

The wait is bounded: past it, nothing runs and the exit is 75 (EX_TEMPFAIL)
with the holder named — a hook inside an agent's tool call must not sit out
its own timeout (downstream: a hook queued 40 minutes behind a full run, the
tool call died at 96 %, the retry started from zero, five times). A hold
inside a hold of the same lane is a pass-through (`PROCESS_LANE_HELD`): a
hook run from a lane-held command would otherwise wait for itself.

Without `fcntl` (Windows) there is no lock: the run goes ahead unqueued and
says so once — lanes are a Unix host's queue.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as _dt
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

import testing_config  # noqa: E402

EX_TEMPFAIL = 75
HELD_ENV = "PROCESS_LANE_HELD"
DIR_ENV = "PROCESS_LANE_DIR"
POLL_S = 2.0
NOTE_EVERY_S = 60.0


class LaneBusy(RuntimeError):
    """The wait budget ran out; nothing ran. `str()` names the holder."""


def _git(root: Path | None, *args: str) -> str:
    try:
        r = subprocess.run(["git", *(["-C", str(root)] if root else []), *args],
                           capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return r.stdout.strip() if r.returncode == 0 else ""


def _root() -> Path | None:
    top = _git(None, "rev-parse", "--show-toplevel")
    return Path(top) if top else None


def config(root: Path | None = None) -> dict:
    """The lane settings: {"dir": Path, "lanes": {name: {wait, nice}}}.
    ConfigError propagates — a malformed configuration queues nothing."""
    root = root if root is not None else _root()
    cfg = testing_config.load(root) if root else None
    lanes = cfg["lanes"] if cfg else testing_config._lanes(None)
    if os.environ.get(DIR_ENV):
        where = Path(os.environ[DIR_ENV]).expanduser()
    elif cfg and cfg.get("lane_dir"):
        where = Path(cfg["lane_dir"]).expanduser()
    else:
        state = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
        where = Path(state).expanduser() / "process-lanes"
    return {"dir": where, "lanes": lanes}


def _fcntl():
    try:
        import fcntl  # noqa: PLC0415 — absent on Windows; only a lock needs it
    except ImportError:
        return None
    return fcntl


def _paths(where: Path, lane: str) -> tuple[Path, Path]:
    return where / f"test-lane-{lane}.lock", where / f"test-lane-{lane}.status"


def _lock_free(where: Path, lane: str) -> bool | None:
    """True when nobody holds the lane (the kernel's lock says so), None when
    it cannot be told (no fcntl, unreadable lock file)."""
    fcntl = _fcntl()
    lock, _status = _paths(where, lane)
    if fcntl is None or not lock.exists():
        return None if fcntl is None else True
    try:
        with open(lock, "a+") as fh:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            return True
    except BlockingIOError:
        return False
    except OSError:
        return None


def holder(where: Path, lane: str) -> dict | None:
    """The holder's status record, None when the lane is free."""
    _lock, status = _paths(where, lane)
    free = _lock_free(where, lane)
    if free:
        with contextlib.suppress(OSError):
            status.unlink()  # a crashed holder's leftover; the lock says free
        return None
    try:
        return json.loads(status.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        if free is None:
            return None
        return {"lane": lane, "label": "unknown holder (status file unreadable)", "pid": 0, "started": 0}


def describe(where: Path, lane: str) -> str:
    """`<lane>: free` or `<lane>: held by pid <p> — <label> (<branch>) since HH:MM (<n> min)`
    — the line the train, the tower and dispatch read."""
    h = holder(where, lane)
    if h is None:
        return f"{lane}: free"
    started = float(h.get("started") or 0)
    mins = int((time.time() - started) // 60) if started else 0
    since = _dt.datetime.fromtimestamp(started).strftime("%H:%M") if started else "?"
    return (f"{lane}: held by pid {h.get('pid') or '?'} — {h.get('label') or 'unlabelled'} "
            f"({h.get('branch') or h.get('cwd') or '?'}) since {since} ({mins} min)")


def _held_marks() -> list[str]:
    try:
        marks = json.loads(os.environ.get(HELD_ENV, "[]"))
    except ValueError:
        return []
    return [m for m in marks if isinstance(m, str)] if isinstance(marks, list) else []


def _mark(where: Path, lane: str) -> str:
    return f"{where.resolve()}\n{lane}"


def _write_status(where: Path, lane: str, label: str) -> None:
    _lock, status = _paths(where, lane)
    record = {"lane": lane, "label": label, "pid": os.getpid(), "started": time.time(),
              "cwd": os.getcwd(), "branch": _git(None, "rev-parse", "--abbrev-ref", "HEAD")}
    tmp = status.with_name(f"{status.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(record), encoding="utf-8")
    os.replace(tmp, status)


@contextlib.contextmanager
def hold(lane: str, *, wait: float | None = None, label: str = "", quiet: bool = False,
         settings: dict | None = None):
    """Hold `lane` for the body: wait up to `wait` seconds (the lane's own
    budget by default), raise LaneBusy past it. A hold of a lane this process
    tree already holds passes through. Children inherit the mark."""
    settings = settings or config()
    if lane not in settings["lanes"]:
        raise ValueError(f"no lane {lane!r} (configured: {', '.join(settings['lanes'])})")
    where = settings["dir"]
    budget = settings["lanes"][lane]["wait"] if wait is None else wait
    mark = _mark(where, lane) if where.exists() else f"{where}\n{lane}"
    if mark in _held_marks():
        yield
        return
    fcntl = _fcntl()
    if fcntl is None:
        if not quiet:
            print(f"lane: no fcntl on this platform — {lane} runs unqueued", file=sys.stderr)
        yield
        return
    where.mkdir(parents=True, exist_ok=True)
    mark = _mark(where, lane)
    lock, status = _paths(where, lane)
    fh = open(lock, "a+")
    deadline = time.monotonic() + budget
    last_note = time.monotonic() - NOTE_EVERY_S
    try:
        while True:
            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                pass
            now = time.monotonic()
            if now >= deadline:
                raise LaneBusy(describe(where, lane))
            if not quiet and now - last_note >= NOTE_EVERY_S:
                print(f"… lane {describe(where, lane)} — waiting, "
                      f"{int(deadline - now) // 60} min budget left", file=sys.stderr, flush=True)
                last_note = now
            time.sleep(min(POLL_S, max(0.05, deadline - now)))
        _write_status(where, lane, label or "lane hold")
        previous = os.environ.get(HELD_ENV)
        os.environ[HELD_ENV] = json.dumps([*_held_marks(), mark])
        try:
            yield
        finally:
            if previous is None:
                os.environ.pop(HELD_ENV, None)
            else:
                os.environ[HELD_ENV] = previous
            with contextlib.suppress(OSError):
                status.unlink()
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    finally:
        fh.close()


def niced(settings: dict, lane: str, argv: list[str]) -> list[str]:
    """`argv` under the lane's `nice`, where the lane asks for one and `nice` exists."""
    level = settings["lanes"].get(lane, {}).get("nice", 0)
    if level and os.name == "posix":
        return ["nice", "-n", str(level), *argv]
    return argv


def tempfail_message(busy: LaneBusy, wait: float) -> str:
    return (f"✗ lane {busy} — wait budget of {int(wait) // 60} min exhausted; nothing ran.\n"
            f"  Not a gate failure: `scripts/process/lane.py status` names the holder; push again "
            f"once it is free, or let a certificate carry the evidence (`test_select.py run --certify`).")


def cmd_run(args, settings: dict) -> int:
    cmd = args.cmd[1:] if args.cmd[:1] == ["--"] else args.cmd
    if not cmd:
        print("lane: nothing to run (give the command after --)", file=sys.stderr)
        return 2
    wait = settings["lanes"][args.lane]["wait"] if args.wait is None else args.wait
    argv = cmd if args.no_nice else niced(settings, args.lane, cmd)
    proc = None

    def _forward(signum, _frame):
        if proc is not None:
            proc.send_signal(signum)

    try:
        with hold(args.lane, wait=wait, label=args.label or " ".join(cmd)[:80], settings=settings):
            for sig in (signal.SIGINT, signal.SIGTERM, getattr(signal, "SIGHUP", None)):
                if sig is not None:
                    signal.signal(sig, _forward)
            proc = subprocess.Popen(argv)
            return proc.wait()
    except LaneBusy as busy:
        print(tempfail_message(busy, wait), file=sys.stderr)
        return EX_TEMPFAIL


def cmd_wait(args, settings: dict) -> int:
    wait = settings["lanes"][args.lane]["wait"] if args.wait is None else args.wait
    try:
        with hold(args.lane, wait=wait, label="lane wait", quiet=args.quiet, settings=settings):
            return 0
    except LaneBusy as busy:
        print(tempfail_message(busy, wait), file=sys.stderr)
        return EX_TEMPFAIL


def cmd_status(_args, settings: dict) -> int:
    for lane in settings["lanes"]:
        print(describe(settings["dir"], lane))
    return 0


def main(argv: list[str]) -> int:
    try:
        settings = config()
    except testing_config.ConfigError as exc:
        print(f"lane: {exc}", file=sys.stderr)
        return 2
    names = list(settings["lanes"])
    p = argparse.ArgumentParser(prog="lane.py", description=(__doc__ or "").split("\n\n")[0])
    sub = p.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="hold a lane while CMD runs")
    run.add_argument("--lane", choices=names, default=names[0])
    run.add_argument("--wait", type=float, default=None, help="seconds to queue (default: the lane's)")
    run.add_argument("--label", default="")
    run.add_argument("--no-nice", action="store_true", help="do not nice the command")
    run.add_argument("cmd", nargs=argparse.REMAINDER)
    run.set_defaults(func=cmd_run)
    wait = sub.add_parser("wait", help="block until the lane is free, run nothing")
    wait.add_argument("--lane", choices=names, default=names[0])
    wait.add_argument("--wait", type=float, default=None)
    wait.add_argument("--quiet", action="store_true")
    wait.set_defaults(func=cmd_wait)
    status = sub.add_parser("status", help="who holds which lane")
    status.set_defaults(func=cmd_status)
    args = p.parse_args(argv)
    return args.func(args, settings)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
