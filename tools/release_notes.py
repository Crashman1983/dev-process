#!/usr/bin/env python3
"""release_notes — the CHANGELOG entry of one version, as release notes.

    python3 tools/release_notes.py v2.33.0 [CHANGELOG.md]

Prints `<title>` on the first line and the entry's body after it. An entry is
the block that starts with `**vX.Y.Z — <title>.**` and runs until the next
`**v…` entry or heading. Exits 1 when the version has no entry: a release
without notes is not published.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ENTRY = re.compile(r"^\*\*(v\d+\.\d+\.\d+)\s+—\s+(.+?)\*\*\s*(.*)$")


def notes(changelog: str, tag: str) -> tuple[str, str] | None:
    lines = changelog.splitlines()
    for i, line in enumerate(lines):
        m = ENTRY.match(line)
        if not m or m.group(1) != tag:
            continue
        title = m.group(2).rstrip(".")
        body = [m.group(3)] if m.group(3) else []
        for nxt in lines[i + 1:]:
            if ENTRY.match(nxt) or nxt.startswith("#"):
                break
            body.append(nxt)
        return title, "\n".join(body).strip() + "\n"
    return None


def main(argv: list[str]) -> int:
    if not argv or not argv[0].startswith("v"):
        print(__doc__.strip().splitlines()[2].strip(), file=sys.stderr)
        return 2
    path = Path(argv[1]) if len(argv) > 1 else Path(__file__).resolve().parents[1] / "CHANGELOG.md"
    found = notes(path.read_text(encoding="utf-8"), argv[0])
    if found is None:
        print(f"release_notes: no CHANGELOG entry for {argv[0]}", file=sys.stderr)
        return 1
    title, body = found
    print(title)
    print(body, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
