#!/usr/bin/env python3
"""red_evidence — the red-before/green-after proof of a fix, measured instead of typed.

    red_evidence.py --work W --round R --before <ref> [--cause TEXT [--sites TEXT]] [--copy PATH …]
                    [--journal-dir DIR] [--dry-run] [--junit PATH] [root] -- <test command>

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
also the ROOT-CAUSE line attest.py asks for, the test names filled in from the
run. The why is the only free text. With `--sites` (the other places the same
defect can live) it takes the class-test form attest asks for each blocked round
(v2.77, required_records `class-test`): `ROOT-CAUSE work=W round=R: <cause> — sites:
<sites> — <path>::<test>`, a ` — ` inside the sites written as `, ` (it separates the
segments); without `--sites` the older `<cause> — <path>::<test>` names a cause but no
class test. A round without a code defect has no red run: its line is written by hand,
`<cause> — sites: none — <reason>`.

The command after `--` is pytest's (`python3 -m pytest …`, `uv run pytest …`); a
small probe plugin (`-p red_evidence_probe`, on PYTHONPATH) records pytest's own node
ids and what each test's setup and call did. Any other runner (vitest, jest, XCTest
through xcresult conversion) reports through JUnit XML instead: `--junit PATH` names
the file the command writes, relative to where it runs; the probe stays out, each
side's file is removed before its run (a file from earlier proves nothing; so it must
be an .xml file git does not track), a test is `<classname>::<name>` (or by its
`file` attribute, `junit_outcomes`) and the worst of its outcomes stands, and the old tree borrows the working tree's `node_modules` (#256). In that mode only files named on the command
or by `--copy` travel into the old tree — a named directory would carry the fixed
source of a non-Python project along. Stdlib only.
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
         timeout: int, junit: str | None = None) -> tuple[int, dict[str, str] | None]:
    """(exit code, test -> passed/failed/error) of one run — reported by the pytest probe,
    or with `junit` read from the JUnit XML the command writes."""
    if junit:
        report = cwd / junit
        report.unlink(missing_ok=True)  # an earlier file is no outcome of this run
        env = dict(os.environ)
        argv = list(command)
    else:
        env = dict(os.environ, RED_EVIDENCE_OUT=str(out),
                   PYTHONPATH=os.pathsep.join(p for p in (str(probe_dir), os.environ.get("PYTHONPATH", "")) if p))
        argv = [*command, "-p", "no:cacheprovider", "-p", "red_evidence_probe"]
    try:
        proc = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        raise SystemExit(f"red_evidence: the run in {cwd} took longer than {timeout} s") from None
    if junit:
        return proc.returncode, junit_outcomes(cwd / junit, cwd)
    # no report is no outcome: the probe did not load (a command that ignores PYTHONPATH,
    # `python -I`) or pytest died — never "no test ran red" (refute of #124)
    seen = json.loads(out.read_text(encoding="utf-8")) if out.is_file() else None
    return proc.returncode, seen


_RANK = {PASSED: 0, FAILED: 1, ERROR: 2}


def junit_problem(root: Path, junit: str) -> str | None:
    """Why `--junit` cannot name the report: each run deletes it first, so it must be a
    report file of its own, never a file the project keeps (refute v2.75 r2: `--junit
    calc.mjs` deleted the uncommitted fix)."""
    if not junit.lower().endswith(".xml"):
        return f"--junit {junit}: a JUnit report is an .xml file the command writes"
    tracked = subprocess.run(["git", "-C", str(root), "ls-files", "--error-unmatch", "--", junit],
                             capture_output=True, text=True)
    if tracked.returncode == 0:
        return f"--junit {junit}: git tracks that file — each run deletes the report first"
    return None


def _link_dependencies(root: Path, tree: Path) -> list[str]:
    """Link the working tree's installed `node_modules` into the old tree beside each
    `package.json` both have: the old checkout has none installed, and a test importing a
    dependency failed there for that alone — no red a fix turned green (refute v2.75 r2)."""
    listed = subprocess.run(["git", "-C", str(tree), "ls-files", "-z", "--", "package.json", "**/package.json"],
                            capture_output=True, text=True)
    linked = []
    for rel in (p for p in listed.stdout.split("\0") if p) if listed.returncode == 0 else ():
        folder = Path(rel).parent
        src, dst = root / folder / "node_modules", tree / folder / "node_modules"
        if src.is_dir() and not dst.exists():
            dst.symlink_to(src, target_is_directory=True)
            linked.append((folder / "node_modules").as_posix())
    return linked


def _junit_key(case, root: Path | None) -> str:
    """A testcase's id: `<classname>::<name>`, or by its `file` attribute where the runner
    writes one — XCTest's and jest's `classname` is no path (`KenniTests.FooTests`, a
    `describe` title), and attest finds a test by its file (v2.77 class-test). An absolute
    `file` counts relative to `root` (each tree is its own root, so both name one test);
    outside it, the classname form stands. A class the classname ends in (`….TestOne`, not
    the file's own stem) stays in the id: `TestOne::test_x` and `TestTwo::test_x` are two."""
    name, cls, file = case.get("name") or "", case.get("classname") or "", case.get("file") or ""
    if file and Path(file).is_absolute():
        try:
            file = Path(file).resolve().relative_to(root.resolve()).as_posix() if root else ""
        except ValueError:
            file = ""
    if not file:
        return f"{cls}::{name}" if cls else name
    last = cls.rsplit(".", 1)[-1]
    if last.isidentifier() and last[:1].isupper() and last != Path(file).stem:
        return f"{file}::{last}::{name}"
    return f"{file}::{name}"


def junit_outcomes(path: Path, root: Path | None = None) -> dict[str, str] | None:
    """`<test id>` (`_junit_key`) -> passed/failed/error of every testcase in a JUnit XML
    file; None when there is none or it does not parse (no report is no outcome). A skipped
    case is no outcome either — it neither went red nor green. `root`: where the command ran."""
    import xml.etree.ElementTree as ET  # noqa: PLC0415  (stdlib; only this mode needs it)
    if not path.is_file() or not path.stat().st_size:
        return None
    try:
        tree = ET.parse(path)
    except (ET.ParseError, OSError):
        return None
    seen: dict[str, str] = {}
    for case in tree.getroot().iter("testcase"):
        name = case.get("name") or ""
        key = _junit_key(case, root)
        if not name or case.find("skipped") is not None:
            continue
        state = ERROR if case.find("error") is not None else FAILED if case.find("failure") is not None else PASSED
        # one id twice (a parametrized title): the worst outcome stands, whatever the order —
        # an error is worst, it is no red a fix turned green (refute v2.75 r2)
        if _RANK[state] >= _RANK.get(seen.get(key, ""), -1):
            seen[key] = state
    return seen


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


def _take_along(root: Path, tree: Path, rels: list[str], *, files: bool = False) -> None:
    """Directories and test files travel into the old tree; a source file named on the command
    (`--doctest-modules calc.py`) does not — carried along, the old run exercised the new code.
    With `files` (JUnit mode) every named file travels: outside pytest a test file's name
    says nothing (`calc.spec.ts`), and `measure` already left directories behind."""
    for rel in rels:
        if files:
            (tree / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root / rel, tree / rel)
            continue
        src, dst = root / rel, tree / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            # by what it holds, not where it is: a named `backend/` carried the fixed source
            # along, and the old run tested the new code (refute of #124)
            shutil.copytree(src, dst, dirs_exist_ok=True, ignore=_not_test_content)
        elif _is_test_file(rel) or not rel.endswith(".py"):
            shutil.copy2(src, dst)


def measure(root: Path, before: str, command: list[str], copy: list[str], timeout: int = TIMEOUT,
            junit: str | None = None) -> dict:
    command = _portable(command, root)
    carried = [r for r in test_paths(root, command, copy)
               if (not junit and (root / r).is_dir()) or (root / r).is_file() and (
                   _is_test_file(r) or not r.endswith(".py") or junit)]
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
            _take_along(root, tree, carried, files=bool(junit))
            if junit:
                _link_dependencies(root, tree)
            exit_before, was = _run(command, tree, probe, Path(tmp) / "before.json", timeout, junit)
        finally:
            subprocess.run(["git", "-C", str(root), "worktree", "remove", "--force", str(tree)],
                           capture_output=True)
        exit_after, now = _run(command, root, probe, Path(tmp) / "after.json", timeout, junit)
    missing = [side for side, seen in ((f"at {before}", was), ("now", now)) if seen is None]
    was, now = was or {}, now or {}
    return {"command": command, "before": before, "exit_before": exit_before, "exit_after": exit_after,
            "red_to_green": sorted(t for t, s in now.items() if s == PASSED and was.get(t) == FAILED),
            "still_red": sorted(t for t, s in now.items() if s != PASSED), "carried": carried,
            "no_report": missing, "junit": junit}


def refusals(m: dict) -> list[str]:
    if m["no_report"]:
        if m.get("junit"):
            return [f"no JUnit report {m['junit']} {' and '.join(m['no_report'])} (missing, empty or "
                    f"not XML) — the tests did not run as asked; cannot tell"]
        return [f"the probe wrote no report {' and '.join(m['no_report'])} — pytest died, or the "
                f"command ignores PYTHONPATH (`python -I`) and the probe never loaded; cannot tell"]
    out = []
    if not m.get("junit") and m["exit_before"] in NOT_RUN:
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


def block(m: dict, work: str, round_: int, cause: str | None, sites: str | None = None) -> str:
    """The journal block; with `cause` the ROOT-CAUSE line — with `sites` in the class-test
    form `<cause> — sites: <sites> — <tests>` (`check_review.root_cause_parts`)."""
    tests = m["red_to_green"]
    lines = [f"Red evidence work={work} round={round_} (red_evidence.py"
             + (f", JUnit {m['junit']}" if m.get("junit") else "") + "):", "", "```",
             " ".join(m["command"]),
             f"at {m['before']}: exit={m['exit_before']}   now: exit={m['exit_after']}",
             f"red before, green after ({len(tests)}): " + ", ".join(tests), "```"]
    if m["carried"]:
        lines.insert(-1, "test files taken into the old tree: " + ", ".join(m["carried"]))
    if cause:
        # ` — ` separates the line's segments: inside the sites it would end them early, so
        # the line would not read back as written
        where = f"sites: {sites.strip().replace(' — ', ', ')} — " if sites else ""
        lines += ["", f"ROOT-CAUSE work={work} round={round_}: {cause.strip()} — {where}" + ", ".join(tests)]
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
    ap.add_argument("--sites", help="with --cause: the other places the same defect can live "
                    "(`file:line, …`); writes the class-test form attest asks per blocked round")
    ap.add_argument("--copy", action="append", default=[], help="another file for the old tree")
    ap.add_argument("--timeout", type=int, default=TIMEOUT, help="seconds per run")
    ap.add_argument("--journal-dir", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--junit", metavar="PATH", help="read outcomes from the JUnit XML the command "
                    "writes (relative to where it runs) — for runners other than pytest")
    ap.add_argument("root", nargs="?", default=str(ROOT))
    args = ap.parse_args(argv[:split])
    command = argv[split + 1:]
    if not command:
        print("red_evidence: no command after `--`", file=sys.stderr)
        return 2
    root = Path(args.root).resolve()
    problem = junit_problem(root, args.junit) if args.junit else None
    if args.sites and not args.cause:
        problem = "--sites goes with --cause: the sites are part of the ROOT-CAUSE line"
    if problem:
        print(f"red_evidence: {problem}", file=sys.stderr)
        return 2
    # a kill runs the cleanup too: the temporary worktree is removed in `measure`'s finally
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(128 + signal.SIGTERM))
    m = measure(root, args.before, command, args.copy, args.timeout, args.junit)
    problems = refusals(m)
    if problems:
        for p in problems:
            print(f"red_evidence: {p}", file=sys.stderr)
        return 1
    text = block(m, args.work, args.round_, args.cause, args.sites)
    if args.cause and not ROOT_CAUSE.search(readable(text)):
        print("red_evidence: the cause does not read as a ROOT-CAUSE line — write a real sentence",
              file=sys.stderr)
        return 1
    if args.cause and not (args.sites or "").strip():
        print("red_evidence: note — no --sites: the ROOT-CAUSE line names no sibling sites, so it is "
              "no class test for a blocked round (attest's class-test row) — pass --sites \"<file:line, …>\"",
              file=sys.stderr)
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
