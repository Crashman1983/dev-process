#!/usr/bin/env python3
"""release_notes — the CHANGELOG entry of one version, as release notes.

    python3 tools/release_notes.py v2.33.0 [CHANGELOG.md]

Prints `<title>` on the first line and the entry's body after it. An entry is
the section that starts with `## vX.Y.Z — <title> · <date>` (the date optional)
and runs until the next `## ` or `# ` heading; the grammar, the older bold form
included, is owned by `template/scripts/process/changelog.py`, read from this
tool's own tree. Exits 1 when the version has no entry: a release without notes
is not published.
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]


def _changelog() -> ModuleType:
    """The core entry grammar from this tool's tree — never from a `root` argument, which
    may be a test root without the template — and without a `__pycache__` in it."""
    spec = importlib.util.spec_from_file_location("release_changelog", ROOT / "template/scripts/process/changelog.py")
    mod = importlib.util.module_from_spec(spec)
    keep, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.dont_write_bytecode = keep
    return mod


changelog = _changelog()
ENTRY, OLD_ENTRY = changelog.ENTRY, changelog.OLD_ENTRY
# NEWS.md, the plain-language log: one `## vX.Y.Z — <title>` section per release
NEWS_ENTRY = re.compile(r"^##\s+(v\d+\.\d+\.\d+)\s+—\s+(\S.*)$")


def notes(text: str, tag: str) -> tuple[str, str] | None:
    """The CHANGELOG entry of `tag` as (title, body), None without one (changelog.notes)."""
    return changelog.notes(text, tag)


def news(news_md: str, tag: str) -> tuple[str, str] | None:
    """The NEWS.md section of `tag` as (title, body), None without one — or with
    an empty body: a heading alone tells a reader nothing."""
    lines = news_md.splitlines()
    for i, line in enumerate(lines):
        m = NEWS_ENTRY.match(line)
        if not m or m.group(1) != tag:
            continue
        body = []
        for nxt in lines[i + 1:]:
            if nxt.startswith("## ") or nxt.startswith("# "):
                break
            body.append(nxt)
        text = "\n".join(body).strip()
        return (m.group(2).strip(), text + "\n") if text else None
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
