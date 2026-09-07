#!/usr/bin/env python3
"""compact_journal: fold old journal shards into a monthly archive that keeps
exactly what the gates read.

Journals grow without bound by design (`journal-state-plans.md`, Retention)
and are read by agents and tools alike — trace, the KPI cockpit, the review
and telemetry gates. Reasoning older than a few weeks is history: git has the
full text, and nobody resumes a session from it. What must survive is the
machine-read record: `REVIEW` attestations (the review gate clears archived
plans against them) and `GRADE` lines (telemetry). Everything else in an old
shard is prose that costs tokens on every recursive read.

The archive keeps one section per folded shard (its original path as the
heading) with only its REVIEW/GRADE lines, verbatim and unfenced — so every
gate that globs `.process-work/journal/**/*.md` still finds them, and
`trace.py` still attributes them. Fenced blocks are quotations and are
dropped with the prose.

Dry run by default: prints what would fold and the byte saving. `--apply`
writes the archive and deletes the folded shards; commit the result as an
ordinary change ("history is pruned in a commit that says so").

Usage: compact_journal.py [root] [--weeks N] [--apply]
"""
from __future__ import annotations

import datetime as dt
import re
import sys
from pathlib import Path

JOURNAL = ".process-work/journal"
ARCHIVE = "archive"
DATE_IN_NAME = re.compile(r"(\d{4}-\d{2}-\d{2})")
# the two record grammars the gates own; kept verbatim, matched loosely here
# (a malformed record stays a malformed record — this tool never repairs)
RECORD = re.compile(r"^\s*(?:[-*+]\s+)?[*_]*(?:REVIEW|GRADE)\b")
FENCE = re.compile(r"^\s*(`{3,}|~{3,})")


def _records(text: str) -> list[str]:
    out: list[str] = []
    fence: str | None = None
    for line in text.splitlines():
        m = FENCE.match(line)
        if m:
            marker = m.group(1)
            if fence is None:
                fence = marker
            elif marker[0] == fence[0] and len(marker) >= len(fence):
                fence = None
            continue
        if fence is None and RECORD.match(line):
            out.append(line.rstrip())
    return out


def _shard_date(p: Path) -> dt.date | None:
    m = DATE_IN_NAME.search(p.name)
    if not m:
        return None
    try:
        return dt.date.fromisoformat(m.group(1))
    except ValueError:
        return None


def plan(root: Path, weeks: int, today: dt.date | None = None) -> dict[str, list[Path]]:
    """Month -> shards older than `weeks` (by the date in their file name)."""
    today = today or dt.date.today()
    cutoff = today - dt.timedelta(weeks=weeks)
    jdir = root / JOURNAL
    by_month: dict[str, list[Path]] = {}
    if not jdir.is_dir():
        return by_month
    for p in sorted(jdir.rglob("*.md")):
        if ARCHIVE in p.relative_to(jdir).parts:
            continue
        d = _shard_date(p)
        if d is None or d >= cutoff:
            continue  # undated shards are never touched; recent ones stay
        by_month.setdefault(d.strftime("%Y-%m"), []).append(p)
    return by_month


def compact(root: Path, weeks: int, apply: bool) -> int:
    by_month = plan(root, weeks)
    jdir = root / JOURNAL
    if not by_month:
        print(f"compact-journal: nothing older than {weeks} week(s) to fold")
        return 0
    before = after = 0
    for month, shards in sorted(by_month.items()):
        target = jdir / ARCHIVE / f"{month}.md"
        sections: list[str] = []
        for p in shards:
            text = p.read_text(encoding="utf-8", errors="replace")
            before += len(text.encode("utf-8"))
            recs = _records(text)
            section = f"## {p.relative_to(root).as_posix()}\n\n" + \
                ("\n".join(recs) + "\n" if recs else "(no REVIEW/GRADE records)\n")
            sections.append(section)
            after += len(section.encode("utf-8"))
        print(f"compact-journal: {len(shards)} shard(s) -> {target.relative_to(root)}")
        for p in shards:
            print(f"  fold {p.relative_to(root)} ({len(_records(p.read_text(encoding='utf-8', errors='replace')))} record(s) kept)")
        if apply:
            target.parent.mkdir(parents=True, exist_ok=True)
            head = "" if target.is_file() else \
                f"# Journal archive {month}\n\n<!-- folded by compact_journal.py: " \
                f"only REVIEW/GRADE records kept; full text in git history -->\n\n"
            with target.open("a", encoding="utf-8") as fh:
                fh.write(head + "\n".join(sections) + "\n")
            for p in shards:
                p.unlink()
                parent = p.parent
                if parent != jdir and not any(parent.iterdir()):
                    parent.rmdir()
    saved = before - after
    verb = "saved" if apply else "would save"
    print(f"compact-journal: {verb} {saved} bytes (~{saved // 4} tokens per full "
          f"journal read){'' if apply else ' — re-run with --apply to write'}")
    if apply:
        print("compact-journal: commit the result as an ordinary change (history "
              "is pruned in a commit that says so)")
    return 0


def main() -> int:
    args = sys.argv[1:]
    weeks = 8
    if "--weeks" in args:
        i = args.index("--weeks")
        weeks = int(args[i + 1])
        del args[i:i + 2]
    apply = "--apply" in args
    positional = [a for a in args if not a.startswith("--")]
    root = Path(positional[0] if positional else ".").resolve()
    return compact(root, weeks, apply)


if __name__ == "__main__":
    raise SystemExit(main())
