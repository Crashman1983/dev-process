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


def outcomes(xml_path: Path) -> dict[str, bool]:
    """test id -> passed, from a junit XML report. A missing report is no outcome."""
    if not xml_path.is_file():
        return {}
    result: dict[str, bool] = {}
    for case in ET.parse(xml_path).getroot().iter("testcase"):
        name = f"{case.get('classname', '')}::{case.get('name', '')}".lstrip(":")
        bad = any(child.tag in ("failure", "error") for child in case)
        skipped = any(child.tag == "skipped" for child in case)
        if not skipped:
            result[name] = not bad
    return result


def _run(command: list[str], cwd: Path, report: Path) -> tuple[int, dict[str, bool]]:
    proc = subprocess.run([*command, "-p", "no:cacheprovider", f"--junitxml={report}"],
                          cwd=cwd, capture_output=True, text=True)
    return proc.returncode, outcomes(report)


def _absolute_interpreter(command: list[str], root: Path) -> list[str]:
    """A relative interpreter (`backend/.venv/bin/python`) points into the working tree;
    the temporary worktree has no virtualenv."""
    first = root / command[0]
    return [str(first), *command[1:]] if "/" in command[0] and first.exists() else command


def measure(root: Path, before: str, command: list[str], copy: list[str]) -> dict:
    command = _absolute_interpreter(command, root)
    paths = [a.split("::", 1)[0] for a in command[1:] if not a.startswith("-")]
    carried = sorted({p for p in [*paths, *copy] if (root / p).is_file()})
    with tempfile.TemporaryDirectory(prefix="red-evidence-") as tmp:
        tree = Path(tmp) / "before"
        add = subprocess.run(["git", "-C", str(root), "worktree", "add", "--detach", "-q", str(tree), before],
                             capture_output=True, text=True)
        if add.returncode != 0:
            raise SystemExit(f"red_evidence: cannot check out {before}: {add.stderr.strip()}")
        try:
            for rel in carried:
                (tree / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(root / rel, tree / rel)
            exit_before, was = _run(command, tree, Path(tmp) / "before.xml")
        finally:
            subprocess.run(["git", "-C", str(root), "worktree", "remove", "--force", str(tree)],
                           capture_output=True)
        exit_after, now = _run(command, root, Path(tmp) / "after.xml")
    return {"command": command, "before": before, "exit_before": exit_before, "exit_after": exit_after,
            "red_to_green": sorted(t for t, ok in now.items() if ok and not was.get(t, False)),
            "still_red": sorted(t for t, ok in now.items() if not ok), "carried": carried}


def refusals(m: dict) -> list[str]:
    out = []
    if not m["red_to_green"]:
        out.append(f"no test went from red at {m['before']} to green now — the run proves no fix "
                   f"(exit before {m['exit_before']}, after {m['exit_after']})")
    if m["still_red"] or m["exit_after"] != 0:
        out.append(f"still red after the fix (exit {m['exit_after']}): "
                   + (", ".join(m["still_red"]) or "the run failed without a test report"))
    return out


def block(m: dict, work: str, round_: int, cause: str | None) -> str:
    tests = [t.rsplit("::", 1)[-1] for t in m["red_to_green"]]
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
    ap.add_argument("--journal-dir", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("root", nargs="?", default=str(ROOT))
    args = ap.parse_args(argv[:split])
    command = argv[split + 1:]
    if not command:
        print("red_evidence: no command after `--`", file=sys.stderr)
        return 2
    root = Path(args.root).resolve()
    m = measure(root, args.before, command, args.copy)
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
