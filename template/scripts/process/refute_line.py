#!/usr/bin/env python3
"""refute_line — the plan's REFUTE line, counted from the refuter's report.

    refute_line.py REPORT --plan PATH --summary TEXT [--work W] [--round R]
                   [--dry-run] [root]

A refute run ends in a report; the plan then gets one line saying what was
attacked (`docs/process/refute.md`). Typed by hand, the counts in that line
were the part that went wrong — scenarios miscounted, a MINOR counted as a
finding the fix round never saw (#124). The refute brief therefore reports in
a fixed form, one line per scenario and one for the shared cause:

    SCENARIO <label>: HELD
    SCENARIO <label>: CONFIRMED <BLOCKER|MAJOR|MINOR> <NEW|PRE-EXISTING> — <what broke>
    PATTERN: <the shared cause and its one owner, or "no common cause">

This tool counts that report and appends

    REFUTE work=<id> round=<r>: <n> scenarios, <k> findings (<severities>) — <summary>

to the plan. The summary — what became of the findings (fixed, a DECISION,
an issue) — is the only free text. It refuses a report without a scenario or
without a PATTERN line, a line that starts like a scenario but does not parse,
a label named twice, a work id that is not the plan's own (the line would
count for nothing), and a round the plan already records. The round defaults
to the plan's last REFUTE round for that work plus one. Stdlib only.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling import
# the review gate owns the line's shape, the record reading and the plan's ids
from check_review import REFUTE_LINE, _plan_work_ids, fenced_lines, plan_stem, readable  # noqa: E402
from attest_evidence import _binds  # noqa: E402  (attest's rule for which work id a line binds)

# whatever Markdown a report wraps a line in — a quote, a heading, a numbered or checkbox
# item, emphasis: a scenario must never drop out of the count for its markup (refute v2.75 r2)
_LEAD = r"^[ \t]*(?:>[ \t]*)*(?:#{1,6}[ \t]+)?(?:(?:[-*+]|\d{1,9}[.)])[ \t]+(?:\[[ xX]\][ \t]+)?)?[*_]*"
SCENARIO_START = re.compile(_LEAD + r"SCENARIO\b", re.IGNORECASE)
SCENARIO = re.compile(
    _LEAD + r"SCENARIO[*_]*\s+(?P<label>.+?)\s*:\s*[*_]*(?:(?P<held>HELD)|CONFIRMED\s+"
    r"(?P<severity>BLOCKER|MAJOR|MINOR)\s+(?P<origin>NEW|PRE-EXISTING))(?![\w-]).*$")
PATTERN = re.compile(_LEAD + r"PATTERN[*_]*\s*:\s*\S")
SEVERITIES = ("BLOCKER", "MAJOR", "MINOR")


def parse_report(text: str) -> tuple[list[dict], list[str]]:
    """(scenarios, problems) of a refute report, read as it renders — a
    quoted example of the format (fenced, commented) is no scenario."""
    scenarios: list[dict] = []
    problems: list[str] = []
    seen: set[str] = set()
    for i, line in enumerate(readable(text).splitlines(), start=1):
        if not SCENARIO_START.match(line):
            continue
        m = SCENARIO.match(line)
        if m and m.group("held") and re.search(r"\bCONFIRMED\b", line):
            m = None  # `HELD for X; CONFIRMED … for Y` is two scenarios in one line
        if not m:
            problems.append(f"line {i}: not `SCENARIO <label>: HELD` or `SCENARIO <label>: "
                            f"CONFIRMED <BLOCKER|MAJOR|MINOR> <NEW|PRE-EXISTING> — …`: {line.strip()}")
            continue
        label = " ".join(m.group("label").split()).lower()
        if label in seen:
            problems.append(f"line {i}: scenario {m.group('label')!r} reported twice")
            continue
        seen.add(label)
        scenarios.append({"label": m.group("label"), "held": bool(m.group("held")),
                          "severity": m.group("severity"), "origin": m.group("origin")})
    if not scenarios and not problems:
        problems.append("no SCENARIO line — the report says nothing that can be counted")
    if not any(PATTERN.match(x) for x in readable(text).splitlines()):
        problems.append("no `PATTERN: …` line — the brief asks for the shared cause (or "
                        "\"no common cause\")")
    return scenarios, problems


def counts(scenarios: list[dict]) -> str:
    """`<n> scenarios, <k> findings (<severities>)` of the parsed report."""
    found = [s for s in scenarios if not s["held"]]
    text = f"{len(scenarios)} scenarios, {len(found)} findings"
    if not found:
        return text
    parts = [f"{sum(s['severity'] == sev for s in found)} {sev.lower()}"
             for sev in SEVERITIES if any(s["severity"] == sev for s in found)]
    old = sum(s["origin"] == "PRE-EXISTING" for s in found)
    return text + f" ({', '.join(parts)}" + (f"; {old} pre-existing" if old else "") + ")"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="append the REFUTE line counted from a refute report")
    ap.add_argument("report", help="the refuter's report (`-` reads stdin)")
    ap.add_argument("--plan", required=True, help="the plan the line goes into")
    ap.add_argument("--summary", required=True,
                    help="one sentence: what became of the findings (fixed, DECISION, issue)")
    ap.add_argument("--work", help="the plan's work id (default: its file stem or spec directory)")
    ap.add_argument("--round", type=int, dest="round_",
                    help="default: the plan's last REFUTE round for the work, plus one")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("root", nargs="?", default=str(ROOT))
    args = ap.parse_args(argv)
    root = Path(args.root).resolve()
    plan = Path(args.plan)
    plan = plan if plan.is_absolute() else root / plan
    try:
        report = sys.stdin.read() if args.report == "-" else Path(args.report).read_text(encoding="utf-8")
        text = plan.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"refute_line: cannot read: {exc}", file=sys.stderr)
        return 2
    try:
        rel = plan.resolve().relative_to(root).as_posix()
    except ValueError:
        rel = plan.as_posix()
    ids = _plan_work_ids(plan_stem(rel), readable(text), include_dedated=True)
    work = args.work or plan_stem(rel)
    problems = []
    if not _binds(work, ids):
        problems.append(f"work {work!r} binds no line to this plan — its ids are "
                        f"{', '.join(sorted(i for i in ids if '/' not in i))}")
    if fenced_lines(text)[1] is not None:
        problems.append(f"{rel} ends inside an open code fence — a line appended there is quoted, "
                        "not a record; close the fence first")
    if args.round_ is not None and args.round_ < 1:
        problems.append(f"round {args.round_} — rounds count from 1")
    scenarios, report_problems = parse_report(report)
    problems += report_problems
    summary = " ".join(args.summary.split())
    rounds = {int(m.group("round")) for m in REFUTE_LINE.finditer(readable(text))
              if m.group("work") in ids}
    round_ = args.round_ if args.round_ is not None else max(rounds, default=0) + 1
    if round_ in rounds:
        problems.append(f"round {round_} is already recorded in {rel} — a new round gets a new number")
    line = f"REFUTE work={work} round={round_}: {counts(scenarios)} — {summary}"
    # the summary alone must read as a record's text: a placeholder is no sentence
    if not REFUTE_LINE.search(readable(f"REFUTE work={work} round={round_}: {summary}")):
        problems.append("the summary does not read as a REFUTE record — write the sentence, "
                        "not a placeholder")
    if problems:
        for p in problems:
            print(f"refute_line: {p}", file=sys.stderr)
        return 1
    print(line)
    if args.dry_run:
        print(f"refute_line: dry run — would append to {rel}")
        return 0
    # after the plan's last line and a blank line: an attestation commit adds
    # it without making the plan's own review stale (refute.md)
    with plan.open("a", encoding="utf-8") as fh:
        fh.write(("" if text.endswith("\n") or not text else "\n") + "\n" + line + "\n")
    print(f"refute_line: appended to {rel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
