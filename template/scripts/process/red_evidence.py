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

The command after `--` is pytest's (`python3 -m pytest …`, `uv run pytest …`);
`--junitxml` is added to read the outcome per test. Stdlib only.
"""
from __future__ import annotations

import argparse
import shutil
import signal
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
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


PASSED, FAILED, NOT_RUN_CASE = "passed", "failed", "error"


def _module_file(classname: str, tree: Path) -> tuple[str, list[str]] | None:
    """(the collecting module's path, the class chain) for a junit classname, found by the
    longest dotted prefix that is a file in `tree` — the module that ran the test, not the one
    that defines it (an inherited test's `file` names its base class's module)."""
    parts = classname.split(".")
    for i in range(len(parts), 0, -1):
        rel = "/".join(parts[:i]) + ".py"
        if (tree / rel).is_file():
            return rel, parts[i:]
    return None


def outcomes(xml_path: Path, tree: Path) -> dict[str, str]:
    """pytest node id (`path::Class::test[param]`) -> passed / failed / error, from a junit
    XML report. Skipped tests and collection errors are left out; a missing report is no
    outcome.

    One table, and it reads the facts, not a proxy (refute of #124): the node id comes from
    the module that collected the test (`classname` in `tree`), and only a `<failure>` is a
    failed run — an `<error>` in setup means the test's own code never ran, so it proves
    nothing about the old code. A test absent from the before-run was never red there."""
    if not xml_path.is_file():
        return {}
    result: dict[str, str] = {}
    for case in ET.parse(xml_path).getroot().iter("testcase"):
        if any(child.tag == "skipped" for child in case):
            continue
        located = _module_file(case.get("classname") or "", tree)
        if located is None:
            continue  # a collection error, or a test outside the tree
        path, klass = located
        node = "::".join([path, *klass, case.get("name", "")])
        tags = {child.tag for child in case}
        result[node] = FAILED if "failure" in tags else NOT_RUN_CASE if "error" in tags else PASSED
    return result


def _run(command: list[str], cwd: Path, report: Path, timeout: int) -> tuple[int, dict[str, str]]:
    try:
        proc = subprocess.run([*command, "-p", "no:cacheprovider",
                               f"--junitxml={report}"], cwd=cwd, capture_output=True, text=True,
                              timeout=timeout)
    except subprocess.TimeoutExpired:
        raise SystemExit(f"red_evidence: the run in {cwd} took longer than {timeout} s") from None
    return proc.returncode, outcomes(report, cwd)


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


def _take_along(root: Path, tree: Path, rels: list[str]) -> None:
    for rel in rels:
        src, dst = root / rel, tree / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__"))
        else:
            shutil.copy2(src, dst)


def measure(root: Path, before: str, command: list[str], copy: list[str], timeout: int = TIMEOUT) -> dict:
    command = _portable(command, root)
    carried = test_paths(root, command, copy)
    # a worktree a killed run left behind is registered but gone: prune it first
    subprocess.run(["git", "-C", str(root), "worktree", "prune"], capture_output=True)
    with tempfile.TemporaryDirectory(prefix="red-evidence-") as tmp:
        tree = Path(tmp) / "before"
        add = subprocess.run(["git", "-C", str(root), "worktree", "add", "--detach", "-q", str(tree), before],
                             capture_output=True, text=True)
        if add.returncode != 0:
            raise SystemExit(f"red_evidence: cannot check out {before}: {add.stderr.strip()}")
        try:
            _take_along(root, tree, carried)
            exit_before, was = _run(command, tree, Path(tmp) / "before.xml", timeout)
        finally:
            subprocess.run(["git", "-C", str(root), "worktree", "remove", "--force", str(tree)],
                           capture_output=True)
        exit_after, now = _run(command, root, Path(tmp) / "after.xml", timeout)
    return {"command": command, "before": before, "exit_before": exit_before, "exit_after": exit_after,
            "red_to_green": sorted(t for t, s in now.items() if s == PASSED and was.get(t) == FAILED),
            "still_red": sorted(t for t, s in now.items() if s != PASSED), "carried": carried}


def refusals(m: dict) -> list[str]:
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
