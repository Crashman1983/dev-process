#!/usr/bin/env python3
"""red_evidence — the red-before/green-after proof of a fix, measured instead of typed.

    red_evidence.py --work W --round R --before <ref> [--cause TEXT] [--copy PATH …]
                    [--journal-dir DIR] [--dry-run] [root] -- <pytest command>

Every fix round writes, by hand, the command it ran, its exit code before and
after, and the tests that went from red to green — and, after a block, a
ROOT-CAUSE line that names those tests. Mostly mechanical text, written from
memory: a test named as red that never was, a count that does not add up, an
exit code read through a pipe (downstream: 200+ words per round, the same
mistakes each time). This tool runs the command twice and writes what it saw:

1. at `--before` (a temporary worktree of that ref, with the command's test
   files — and every `--copy` path — taken from the working tree, so the new
   tests run against the old code);
2. in the working tree.

It refuses when no test went from red to green (the proof proves nothing) or
when a test is still red after. The journal gets the block; with `--cause`
also the `ROOT-CAUSE work=W round=R: <cause> — <tests>` line attest.py asks
for, the test names filled in from the run. The why is the only free text.

The command after `--` is pytest's (`python3 -m pytest …`, `uv run pytest …`); a
small probe plugin (`-p red_evidence_probe`, on PYTHONPATH) records pytest's own node
ids and what each test's setup and call did. Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling import
from attest import ROOT_CAUSE, _journal_target  # noqa: E402  (one grammar, one journal home)
from check_review import JOURNAL_DIR, readable  # noqa: E402


# pytest exit codes that mean "the tests did not run as asked": interrupted
# (a collection error), internal error, usage error
NOT_RUN = {2: "collection was interrupted (a collection error)", 3: "pytest hit an internal error",
           4: "pytest was called wrongly"}
# options whose next argument is a value, not a test path
_VALUED = {"-c", "-k", "-m", "-p", "-o", "-W", "--rootdir", "--confcutdir", "--basetemp",
           "--junitxml", "--deselect", "--ignore", "--ignore-glob", "--timeout"}
TIMEOUT = 1800


PASSED, FAILED, ERROR = "passed", "failed", "error"

# asked of pytest itself, not guessed from a report: its own node id (relative to its own
# rootdir, a doctest's id, a dot in a directory name all as pytest has them) and what each
# phase did. Refute of #124, three rounds of guessing — the junit report's `classname` is
# rootdir-relative and dotted, its `file` names where a test is defined, its `<error>` mixes
# a setup error with a run — so the probe below records the facts where pytest decides them.
_PROBE = """
import json, os

_seen = {}


def pytest_runtest_logreport(report):
    if report.when == "call":
        if report.passed:
            _seen.setdefault(report.nodeid, "passed")
        elif report.failed:
            _seen[report.nodeid] = "failed"
        else:
            _seen[report.nodeid] = "skipped"
    elif report.failed:
        # setup or teardown failed: the test's own code did not prove anything
        if _seen.get(report.nodeid) != "failed":
            _seen[report.nodeid] = "error"
    elif report.skipped:
        _seen[report.nodeid] = "skipped"


def pytest_sessionfinish(session):
    with open(os.environ["RED_EVIDENCE_OUT"], "w", encoding="utf-8") as fh:
        json.dump({k: v for k, v in _seen.items() if v != "skipped"}, fh)
"""


def _run(command: list[str], cwd: Path, probe_dir: Path, out: Path,
         timeout: int) -> tuple[int, dict[str, str] | None]:
    """(exit code, node id -> passed/failed/error) of one pytest run, reported by the probe."""
    env = dict(os.environ, RED_EVIDENCE_OUT=str(out),
               PYTHONPATH=os.pathsep.join(p for p in (str(probe_dir), os.environ.get("PYTHONPATH", "")) if p))
    try:
        proc = subprocess.run([*command, "-p", "no:cacheprovider", "-p", "red_evidence_probe"],
                              cwd=cwd, capture_output=True, text=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        raise SystemExit(f"red_evidence: the run in {cwd} took longer than {timeout} s") from None
    # no report is no outcome: the probe did not load (a command that ignores PYTHONPATH,
    # `python -I`) or pytest died — never "no test ran red" (refute of #124)
    seen = json.loads(out.read_text(encoding="utf-8")) if out.is_file() else None
    return proc.returncode, seen


def _portable(command: list[str], root: Path) -> list[str]:
    """The command as both trees can run it. A relative interpreter (`backend/.venv/bin/python`)
    points into the working tree — the temporary worktree has no virtualenv — so it is made
    absolute. An absolute test path inside the root is made relative, or the old tree would
    run the working tree's file."""
    first = root / command[0]
    head = str(first) if "/" in command[0] and first.exists() else command[0]
    rest = []
    for arg in command[1:]:
        path, sep, node = arg.partition("::")
        if Path(path).is_absolute():
            try:
                arg = str(Path(path).resolve().relative_to(root.resolve())) + sep + node
            except ValueError:
                pass
        rest.append(arg)
    return [head, *rest]


def test_paths(root: Path, command: list[str], copy: list[str]) -> list[str]:
    """The files and directories the command names, relative to the root — what the old
    tree needs from the working tree. An option's value is no path; an absolute path inside
    the root is made relative (it crashed the copy); one outside is not the repo's."""
    found: set[str] = set()
    skip = False
    for arg in [*command[1:], *copy]:
        if skip:
            skip = False
            continue
        if arg in _VALUED:
            skip = True
            continue
        if arg.startswith("-"):
            continue
        path = Path(arg.split("::", 1)[0])
        full = path if path.is_absolute() else root / path
        try:
            rel = full.resolve().relative_to(root.resolve())
        except ValueError:
            continue
        if full.exists() and str(rel) != ".":
            found.add(str(rel))
    return sorted(found)


def _is_test_file(rel: str) -> bool:
    name = Path(rel).name
    return name == "conftest.py" or (name.endswith(".py") and (name.startswith("test_") or name.endswith("_test.py")))


_TEST_DIRS = {"tests", "test", "testing"}


def _not_test_content(folder: str, names: list[str]) -> set[str]:
    """What a carried directory leaves behind: caches, and source files. Inside a `tests`
    folder every .py is test code (helpers, base classes, `__init__`); outside one only test
    files and conftest.py are."""
    in_tests = bool(_TEST_DIRS & set(Path(folder).parts))
    return {n for n in names if n == "__pycache__"
            or (n.endswith(".py") and not in_tests and not _is_test_file(n)
                and not (Path(folder) / n).is_dir())}


def _take_along(root: Path, tree: Path, rels: list[str]) -> None:
    """Directories and test files travel into the old tree; a source file named on the command
    (`--doctest-modules calc.py`) does not — carried along, the old run exercised the new code."""
    for rel in rels:
        src, dst = root / rel, tree / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            # by what it holds, not where it is: a named `backend/` carried the fixed source
            # along, and the old run tested the new code (refute of #124)
            shutil.copytree(src, dst, dirs_exist_ok=True, ignore=_not_test_content)
        elif _is_test_file(rel) or not rel.endswith(".py"):
            shutil.copy2(src, dst)


def measure(root: Path, before: str, command: list[str], copy: list[str], timeout: int = TIMEOUT) -> dict:
    command = _portable(command, root)
    carried = [r for r in test_paths(root, command, copy)
               if (root / r).is_dir() or _is_test_file(r) or not r.endswith(".py")]
    # a worktree a killed run left behind is registered but gone: prune it first
    subprocess.run(["git", "-C", str(root), "worktree", "prune"], capture_output=True)
    with tempfile.TemporaryDirectory(prefix="red-evidence-") as tmp:
        probe = Path(tmp) / "probe"
        probe.mkdir()
        (probe / "red_evidence_probe.py").write_text(_PROBE, encoding="utf-8")
        tree = Path(tmp) / "before"
        add = subprocess.run(["git", "-C", str(root), "worktree", "add", "--detach", "-q", str(tree), before],
                             capture_output=True, text=True)
        if add.returncode != 0:
            raise SystemExit(f"red_evidence: cannot check out {before}: {add.stderr.strip()}")
        try:
            _take_along(root, tree, carried)
            exit_before, was = _run(command, tree, probe, Path(tmp) / "before.json", timeout)
        finally:
            subprocess.run(["git", "-C", str(root), "worktree", "remove", "--force", str(tree)],
                           capture_output=True)
        exit_after, now = _run(command, root, probe, Path(tmp) / "after.json", timeout)
    missing = [side for side, seen in ((f"at {before}", was), ("now", now)) if seen is None]
    was, now = was or {}, now or {}
    return {"command": command, "before": before, "exit_before": exit_before, "exit_after": exit_after,
            "red_to_green": sorted(t for t, s in now.items() if s == PASSED and was.get(t) == FAILED),
            "still_red": sorted(t for t, s in now.items() if s != PASSED), "carried": carried,
            "no_report": missing}


def refusals(m: dict) -> list[str]:
    if m["no_report"]:
        return [f"the probe wrote no report {' and '.join(m['no_report'])} — pytest died, or the "
                f"command ignores PYTHONPATH (`python -I`) and the probe never loaded; cannot tell"]
    out = []
    if m["exit_before"] in NOT_RUN:
        out.append(f"at {m['before']} {NOT_RUN[m['exit_before']]} (exit {m['exit_before']}) — the "
                   f"tests never ran against the old code; select tests that collect there (a new "
                   f"module belongs in its own test run)")
    elif not m["red_to_green"]:
        out.append(f"no test went from red at {m['before']} to green now — the run proves no fix "
                   f"(exit before {m['exit_before']}, after {m['exit_after']})")
    if m["still_red"] or m["exit_after"] != 0:
        out.append(f"still red after the fix (exit {m['exit_after']}): "
                   + (", ".join(m["still_red"]) or "the run failed without a test report"))
    return out


def block(m: dict, work: str, round_: int, cause: str | None) -> str:
    tests = m["red_to_green"]
    lines = [f"Red evidence work={work} round={round_} (red_evidence.py):", "", "```",
             " ".join(m["command"]),
             f"at {m['before']}: exit={m['exit_before']}   now: exit={m['exit_after']}",
             f"red before, green after ({len(tests)}): " + ", ".join(tests), "```"]
    if m["carried"]:
        lines.insert(-1, "test files taken into the old tree: " + ", ".join(m["carried"]))
    if cause:
        lines += ["", f"ROOT-CAUSE work={work} round={round_}: {cause.strip()} — " + ", ".join(tests)]
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    if "--" not in argv:
        print("red_evidence: the pytest command follows `--`", file=sys.stderr)
        return 2
    split = argv.index("--")
    ap = argparse.ArgumentParser(description="measure and record the red-before/green-after proof")
    ap.add_argument("--work", required=True)
    ap.add_argument("--round", type=int, required=True, dest="round_")
    ap.add_argument("--before", required=True, help="the ref before the fix")
    ap.add_argument("--cause", help="the root cause, one sentence; writes the ROOT-CAUSE line")
    ap.add_argument("--copy", action="append", default=[], help="another file for the old tree")
    ap.add_argument("--timeout", type=int, default=TIMEOUT, help="seconds per run")
    ap.add_argument("--journal-dir", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("root", nargs="?", default=str(ROOT))
    args = ap.parse_args(argv[:split])
    command = argv[split + 1:]
    if not command:
        print("red_evidence: no command after `--`", file=sys.stderr)
        return 2
    root = Path(args.root).resolve()
    # a kill runs the cleanup too: the temporary worktree is removed in `measure`'s finally
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(128 + signal.SIGTERM))
    m = measure(root, args.before, command, args.copy, args.timeout)
    problems = refusals(m)
    if problems:
        for p in problems:
            print(f"red_evidence: {p}", file=sys.stderr)
        return 1
    text = block(m, args.work, args.round_, args.cause)
    if args.cause and not ROOT_CAUSE.search(readable(text)):
        print("red_evidence: the cause does not read as a ROOT-CAUSE line — write a real sentence",
              file=sys.stderr)
        return 1
    journal_dir = Path(args.journal_dir) if args.journal_dir else root / JOURNAL_DIR
    target = _journal_target(root, journal_dir)
    print(text, end="")
    if args.dry_run:
        print(f"red_evidence: dry run — would append to {target}")
        return 0
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as fh:
        fh.write(("\n" if target.stat().st_size else "") + text)
    print(f"red_evidence: appended to {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
