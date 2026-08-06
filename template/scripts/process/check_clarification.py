#!/usr/bin/env python3
"""clarification gate (core, always-on): the `[NEEDS CLARIFICATION: …]` marker
convention's mechanical floor.

Brainstorm marks underspecified points instead of guessing
(`docs/process/design-template.md`); markers are resolved before the design is
approved. The plan phase consumes an *approved* design, so this gate enforces
the one line a machine can honestly draw:

  - HARD: an unresolved marker in an ACTIVE plan (`.process-work/plans/*.md`,
    excluding `design-*` and the archive) — a plan carrying an open question
    was built from an unapproved design.
  - SOFT (note only): markers in active `design-*` files — an in-progress
    design legitimately carries them; the note keeps them visible, mid-flight
    CI stays green.
  - Archived plans and designs are history and are not checked: the convention
    postdates them, and the active check already blocked the merge path.

A marker inside a fenced code block is a quotation (this doc convention is the
same one the review gate applies to REVIEW lines) and is ignored. Pure stdlib.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

PLANS_ACTIVE = ".process-work/plans"
PLANS_ARCHIVE_NAME = "archive"

# the review gate owns fence semantics — import, don't copy (one owner)
sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling import
from check_review import _fence_closes, _fence_marker  # noqa: E402

# tolerant of case and of a colon-less bare marker — `[needs clarification]`
# must not escape the gate on a spelling nuance (a false-green)
MARKER = re.compile(r"\[NEEDS CLARIFICATION\b", re.IGNORECASE)


def _marker_lines(text: str) -> list[int]:
    """1-based line numbers of unfenced marker occurrences."""
    hits: list[int] = []
    fence: str | None = None
    for i, line in enumerate(text.splitlines(), start=1):
        marker = _fence_marker(line)
        if marker and fence is None:
            fence = marker
            continue
        if marker and fence is not None and _fence_closes(fence, marker):
            fence = None
            continue
        if fence is None and MARKER.search(line):
            hits.append(i)
    return hits


def check(root: Path) -> tuple[list[str], list[str]]:
    hard: list[str] = []
    soft: list[str] = []
    pdir = root / PLANS_ACTIVE
    if not pdir.is_dir():
        return hard, soft
    for p in sorted(pdir.glob("*.md")):
        rel = f"{PLANS_ACTIVE}/{p.name}"
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:  # broken symlink, directory named *.md, …
            hard.append(f"{rel}: could not read: {exc}")
            continue
        lines = _marker_lines(text)
        if not lines:
            continue
        if p.name.startswith("design-"):
            soft.append(
                f"{rel}: {len(lines)} unresolved [NEEDS CLARIFICATION] marker(s) "
                f"(line(s) {', '.join(map(str, lines))}) — resolve before approval; "
                f"an in-progress design may carry them"
            )
        else:
            for lineno in lines:
                hard.append(
                    f"{rel}:{lineno}: unresolved [NEEDS CLARIFICATION] marker in an "
                    f"active plan — a plan is built from an approved design; resolve "
                    f"the question (or record the named assumption) in the design "
                    f"and re-plan (docs/process/design-template.md)"
                )
    return hard, soft


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    if not root.is_dir():
        print(f"clarification: FAILED:\n  - root {root} is not a directory")
        return 1
    hard, soft = check(root)
    for note in soft:
        print(f"clarification: note: {note}")
    if hard:
        print("clarification: FAILED:")
        for h in hard:
            print(f"  - {h}")
        return 1
    print("clarification: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
