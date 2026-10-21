#!/usr/bin/env python3
"""due_measurements — measurement milestones whose date has passed without a
record that answers them.

A decision taken on a forecast ("measure the gate's cost again in four
weeks") needs someone to come back to it; a date in a plan or a journal line
is read once and forgotten. The project lists its milestones in
`docs/process/milestones.local.json`:

    {"milestones": [{"id": "plan-drift-2026-10-27", "due": "2026-10-27",
                     "command": "uv run scripts/process/process_kpis.py nodes",
                     "record_hint": "thresholds as a proposal to the owner"}]}

A milestone is due once its date is reached and no record carries the line
`milestone: <id>` — an improvement record (`.process-work/optimizations/
OPT-*.md`) or a weekly report (`.process-work/improvement/*.md`). Without
that line the milestone stays due: an answer nobody wrote down is open, not
done.

    due_measurements.py [--today YYYY-MM-DD] [--root PATH]

Prints `DUE <id> (since <date>): <command> → <record_hint>` per due
milestone, sorted by date, and nothing otherwise. A note, not a gate: exit 0.
Without the file it says so in one line — silence there read as "nothing due"
for a project that had milestones and lost the file (#259); a file with an
empty list stays silent. A file that is there
but broken — not JSON, wrong shape, a bad date, an id twice — exits 2 with
the file and the entry named: a broken list must never read as "nothing
due". An invalid `--today` exits 2 as well. Read-only. Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling imports
from optimize import RECORDS  # noqa: E402

MILESTONES_FILE = "docs/process/milestones.local.json"
IMPROVEMENT = ".process-work/improvement"
FIELDS = ("id", "due", "command", "record_hint")
_MILESTONE_LINE = re.compile(r"^milestone:\s*(\S+)\s*$", re.MULTILINE)
# date.fromisoformat also takes `20261027` and week dates; the file says
# YYYY-MM-DD, so that is the one form it accepts
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


@dataclass(frozen=True)
class Milestone:
    id: str
    due: date
    command: str
    record_hint: str


class MilestoneFileError(ValueError):
    """The milestone file exists but cannot be trusted; the message names
    the file and the entry."""


def _entry_error(index: int, entry: object, what: str) -> MilestoneFileError:
    label = f"milestones[{index}]"
    if isinstance(entry, dict) and isinstance(entry.get("id"), str) and entry["id"]:
        label += f" (id {entry['id']!r})"
    return MilestoneFileError(f"{MILESTONES_FILE}: {label}: {what}")


def _milestone(index: int, entry: object) -> Milestone:
    if not isinstance(entry, dict):
        raise _entry_error(index, entry, "not an object")
    for field in FIELDS:
        value = entry.get(field)
        if not isinstance(value, str) or not value.strip():
            raise _entry_error(index, entry, f"{field!r} must be a non-empty string")
    raw = entry["due"]
    try:
        if not _ISO_DATE.fullmatch(raw):
            raise ValueError
        due_on = date.fromisoformat(raw)
    except ValueError:
        raise _entry_error(index, entry, f"due {raw!r} is not a YYYY-MM-DD date") from None
    return Milestone(entry["id"], due_on, entry["command"], entry["record_hint"])


def load_milestones(root: Path) -> tuple[Milestone, ...]:
    """The project's milestones; no file means none. Raises
    MilestoneFileError when the file is there but malformed."""
    path = root / MILESTONES_FILE
    if not path.is_file():
        if path.exists() or path.is_symlink():  # a directory, a dangling link: broken, not absent
            raise MilestoneFileError(f"{MILESTONES_FILE}: not a readable file")
        return ()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise MilestoneFileError(f"{MILESTONES_FILE}: not readable as JSON: {exc}") from None
    if not isinstance(data, dict) or not isinstance(data.get("milestones"), list):
        raise MilestoneFileError(f'{MILESTONES_FILE}: expected {{"milestones": [...]}}')
    milestones: list[Milestone] = []
    seen: set[str] = set()
    for index, entry in enumerate(data["milestones"]):
        m = _milestone(index, entry)
        if m.id in seen:
            raise _entry_error(index, entry, "id appears twice")
        seen.add(m.id)
        milestones.append(m)
    return tuple(milestones)


def recorded_ids(root: Path) -> set[str]:
    """Every `milestone: <id>` line in OPT-*.md and .process-work/improvement/*.md."""
    sources = list((root / RECORDS).glob("OPT-*.md"))
    sources += list((root / IMPROVEMENT).glob("*.md"))
    ids: set[str] = set()
    for path in sources:
        if path.is_file():
            ids.update(_MILESTONE_LINE.findall(path.read_text(encoding="utf-8", errors="replace")))
    return ids


def due(today: date, recorded: set[str], milestones: tuple[Milestone, ...]) -> list[Milestone]:
    """Milestones with due <= today whose id no record carries, by date."""
    open_ = [m for m in milestones if m.due <= today and m.id not in recorded]
    return sorted(open_, key=lambda m: m.due)


def _parse_today(text: str) -> date:
    try:
        if not _ISO_DATE.fullmatch(text):
            raise ValueError
        return date.fromisoformat(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a date (YYYY-MM-DD): {text}") from None


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="report due measurement milestones")
    p.add_argument("--today", type=_parse_today, default=None,
                   help="reference date, default today")
    p.add_argument("--root", type=Path, default=None,
                   help="repository root, default: this repository")
    args = p.parse_args(argv)
    root = args.root or Path(__file__).resolve().parents[2]
    today = args.today or date.today()
    path = root / MILESTONES_FILE
    if not (path.exists() or path.is_symlink()):
        print(f"due_measurements: no {MILESTONES_FILE} — no milestones tracked")
        return 0
    try:
        milestones = load_milestones(root)
    except MilestoneFileError as exc:
        print(f"due_measurements: {exc}", file=sys.stderr)
        return 2
    for m in due(today, recorded_ids(root), milestones):
        print(f"DUE {m.id} (since {m.due.isoformat()}): {m.command} → {m.record_hint}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
