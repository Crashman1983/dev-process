#!/usr/bin/env python3
"""overlays gate (core, always on): a project's notes on a template doc still fit
the template they were written against (`docs/process/overlays.md`).

A project does not edit a template-owned doc or command — every edit there turns
the next template update into a merge conflict. It writes an overlay instead: a
`*.local.md` file under `docs/process/` whose head names the template file it
extends (`overlay-of: <path>`) and whose anchor lines name the sections it builds
on, each with the hash of that section as it read when the overlay was checked:

    overlay-of: docs/process/testing.md
    extends: "## Stages" @3f2a9c1b0d4e
    replaces: "### Lanes" @77e01c2a9b10

A template update that removes, renames or changes an anchored section is a
possible breaking change for the project: this gate turns red and names the
overlay and the section, until someone re-read both, adjusted the overlay and
re-stamped it (`check_overlays.py --stamp <overlay>`). `replaces` marks an
overlay that sets a rule of its own in place of the section's — the reason the
check exists. An overlay with no anchor cannot be checked and is refused.

    python3 scripts/process/check_overlays.py [root]              # the gate
    python3 scripts/process/check_overlays.py --stamp <overlay>   # after a re-check

Honest boundary: the gate sees that the anchored text changed, not whether the
change contradicts the overlay — that judgment is the re-check. Stdlib only.
"""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

OVERLAY_GLOB = "docs/process/**/*.local.md"
HEAD = re.compile(r"^overlay-of:[ \t]*(?P<path>\S+)[ \t]*$", re.MULTILINE)
ANCHOR = re.compile(r'^(?P<kind>extends|replaces):[ \t]*"(?P<heading>#{1,6}[ \t]+[^"\n]+?)"[ \t]*'
                    r"@(?P<hash>[0-9a-f]{12}|new)[ \t]*$", re.MULTILINE)
_HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$")
_FENCE = re.compile(r"^[ \t]*(```|~~~)")


def _norm(heading: str) -> str:
    m = _HEADING.match(heading.strip())
    return f"{m.group(1)} {m.group(2).strip()}" if m else heading.strip()


def sections(text: str) -> dict[str, str]:
    """Heading line (normalised) -> the section's text: from the heading to the next
    heading of the same or a higher level, fenced code ignored. A heading that
    occurs twice keeps its first section (an anchor names the first)."""
    lines = text.splitlines()
    heads: list[tuple[int, int, str]] = []
    fenced = False
    for i, line in enumerate(lines):
        if _FENCE.match(line):
            fenced = not fenced
            continue
        m = None if fenced else _HEADING.match(line)
        if m:
            heads.append((i, len(m.group(1)), _norm(line)))
    out: dict[str, str] = {}
    for n, (i, level, name) in enumerate(heads):
        end = next((j for j, lv, _ in heads[n + 1:] if lv <= level), len(lines))
        out.setdefault(name, "\n".join(ln.rstrip() for ln in lines[i:end]).strip())
    return out


def section_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def overlays(root: Path) -> list[Path]:
    """The project's overlays: `*.local.md` under docs/process/ that name their
    template file (`overlay-of:`); other local notes are not overlays."""
    found = []
    for p in sorted(root.glob(OVERLAY_GLOB)):
        try:
            if HEAD.search(p.read_text(encoding="utf-8")):
                found.append(p)
        except (OSError, UnicodeDecodeError):
            found.append(p)  # unreadable: check() names it
    return found


def check_one(root: Path, overlay: Path) -> list[str]:
    rel = overlay.relative_to(root).as_posix()
    try:
        text = overlay.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return [f"{rel}: unreadable ({exc})"]
    head = HEAD.search(text)
    if head is None:
        return [f"{rel}: no `overlay-of: <template path>` line"]
    target = root / head.group("path")
    try:
        doc = sections(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        return [f"{rel}: its template file {head.group('path')} is gone — the template moved or removed it; "
                f"re-home the overlay or delete it (breaking change)"]
    anchors = list(ANCHOR.finditer(text))
    if not anchors:
        return [f"{rel}: no anchor line (`extends:`/`replaces:` \"<heading>\" @<hash>) — an overlay that names no "
                f"section cannot be checked against a template change"]
    problems = []
    for a in anchors:
        name = _norm(a.group("heading"))
        if name not in doc:
            problems.append(f"{rel}: {a.group('kind')} {name!r} — the section is gone from {head.group('path')} "
                            f"(renamed or removed by the template): breaking change, re-home the overlay")
        elif a.group("hash") == "new":
            problems.append(f"{rel}: {a.group('kind')} {name!r} is not stamped yet — check it against the section, "
                            f"then `check_overlays.py --stamp {rel}`")
        elif section_hash(doc[name]) != a.group("hash"):
            problems.append(f"{rel}: {a.group('kind')} {name!r} — the template changed this section since the "
                            f"overlay was checked: possible breaking change; re-read both, adjust the overlay, "
                            f"then `check_overlays.py --stamp {rel}`")
    return problems


def check(root: Path) -> list[str]:
    return [p for o in overlays(root) for p in check_one(root, o)]


def stamp(root: Path, overlay: Path) -> list[str]:
    """Writes the current hash into every anchor line — the record that someone
    checked the overlay against the sections as they read now."""
    text = overlay.read_text(encoding="utf-8")
    head = HEAD.search(text)
    if head is None:
        return [f"{overlay}: no `overlay-of:` line"]
    doc = sections((root / head.group("path")).read_text(encoding="utf-8"))
    missing = [_norm(a.group("heading")) for a in ANCHOR.finditer(text) if _norm(a.group("heading")) not in doc]
    if missing:
        return [f"{overlay}: section {m!r} is not in {head.group('path')} — re-home the anchor first"
                for m in missing]

    def fresh(a: re.Match) -> str:
        return f'{a.group("kind")}: "{a.group("heading")}" @{section_hash(doc[_norm(a.group("heading"))])}'

    overlay.write_text(ANCHOR.sub(fresh, text), encoding="utf-8")
    return []


def main(argv: list[str]) -> int:
    if argv[:1] == ["--stamp"]:
        if len(argv) != 2:
            print("usage: check_overlays.py --stamp <overlay>", file=sys.stderr)
            return 2
        path = Path(argv[1]).resolve()
        root = Path.cwd().resolve()
        problems = stamp(root, path)
        for p in problems:
            print(f"overlays: {p}", file=sys.stderr)
        if not problems:
            print(f"overlays: stamped {path.relative_to(root) if path.is_relative_to(root) else path}")
        return 1 if problems else 0
    root = Path(argv[0] if argv else ".").resolve()
    problems = check(root)
    for p in problems:
        print(f"overlays: {p}")
    if not problems:
        n = len(overlays(root))
        print(f"overlays: OK ({n} overlay{'s' if n != 1 else ''} fit the template)")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
