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
HEAD = re.compile(r"^overlay-of:[ \t]*(?P<path>[^\s#]+)[ \t]*$", re.MULTILINE)
# anything that means to be a head or an anchor: a line that does not parse is red, never skipped
HEAD_INTENT = re.compile(r"^\ufeff?[ \t]*overlay-of[ \t]*:", re.MULTILINE | re.IGNORECASE)
ANCHOR = re.compile(r'^(?P<kind>extends|replaces):[ \t]*"(?P<heading>#{1,6}[ \t]+[^"\n]+?)"[ \t]*'
                    r"@(?P<hash>[0-9a-f]{12}|new)[ \t]*$", re.MULTILINE)
ANCHOR_INTENT = re.compile(r"^[ \t]*(?:extends?|replaces?|replace)[ \t]*:", re.MULTILINE | re.IGNORECASE)
# ATX heading; a closing `#` run counts only after whitespace (`## C#` is the heading "C#")
_HEADING = re.compile(r"^ {0,3}(#{1,6})[ \t]+(.*?)(?:[ \t]+#+)?[ \t]*$")
_FENCE_OPEN = re.compile(r"^ {0,3}(?P<fence>`{3,}|~{3,})(?P<info>.*)$")
# copied byte for byte into the anchors (check_kernel.py): an overlay would never reach them
UNOVERLAYABLE = frozenset({"docs/process/kernel.md"})


def _norm(heading: str) -> str:
    m = _HEADING.match(heading.strip())
    return f"{m.group(1)} {m.group(2).strip()}" if m else heading.strip()


def fenced(lines: list[str]) -> list[bool]:
    """Per line: is it fenced code (the fences included)? CommonMark: a fence closes
    with the same character, at least as long, indented at most three spaces."""
    out, fence = [], ""
    for line in lines:
        if fence:
            stripped = line.strip()
            indent = len(line) - len(line.lstrip(" "))
            if stripped and set(stripped) == {fence[0]} and len(stripped) >= len(fence) and indent <= 3:
                fence = ""
            out.append(True)
            continue
        f = _FENCE_OPEN.match(line)
        if f and not (f.group("fence")[0] == "`" and "`" in f.group("info")):
            fence = f.group("fence")
        out.append(bool(fence))
    return out


def unfenced(text: str) -> str:
    """The overlay's text with fenced lines blanked (line count kept): an example
    head or anchor inside a code block is prose, not a claim."""
    lines = text.splitlines(keepends=True)
    return "".join("\n" if code else ln for ln, code in zip(lines, fenced(lines)))


def sections(text: str) -> dict[str, str]:
    """Heading line (normalised) -> the section's text: from the heading to the next
    heading of the same or a higher level, fenced code ignored. A heading that
    occurs twice keeps its first section (an anchor names the first)."""
    lines = text.splitlines()
    heads: list[tuple[int, int, str]] = []
    for i, (line, code) in enumerate(zip(lines, fenced(lines))):
        m = None if code else _HEADING.match(line)
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
    """The project's overlays: `*.local.md` under docs/process/ that mean to name
    their template file (`overlay-of:` in any spelling — check_one says when it does
    not parse); other local notes are not overlays. rehydrate.py lists these."""
    found = []
    for p in sorted(root.glob(OVERLAY_GLOB)):
        try:
            if HEAD_INTENT.search(unfenced(p.read_text(encoding="utf-8"))):
                found.append(p)
        except (OSError, UnicodeDecodeError):
            found.append(p)  # unreadable: check() names it
    return found


def target_of(root: Path, rel: str) -> Path | None:
    """The template file an overlay names, or None when it is not a regular file inside
    the repository (absolute, `..`, a device): an overlay overlays this project only."""
    p = Path(rel)
    if p.is_absolute() or ".." in p.parts:
        return None
    full = (root / p).resolve()
    return full if full.is_relative_to(root.resolve()) and full.is_file() else None


def check_one(root: Path, overlay: Path) -> list[str]:
    rel = overlay.relative_to(root).as_posix()
    try:
        text = unfenced(overlay.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        return [f"{rel}: unreadable ({exc})"]
    head = HEAD.search(text.lstrip("\ufeff"))
    if head is None:
        return [f"{rel}: its `overlay-of:` line does not parse — write `overlay-of: <template path>` alone on "
                f"its line"]
    if head.group("path") in UNOVERLAYABLE:
        return [f"{rel}: {head.group('path')} takes no overlay — it is copied byte for byte into the anchors; "
                f"a project that must change it keeps its own copy (`.process-owned`)"]
    target = target_of(root, head.group("path"))
    if target is None:
        return [f"{rel}: its template file {head.group('path')} is gone or outside the repository — the template "
                f"moved or removed it; re-home the overlay or delete it (breaking change)"]
    try:
        doc = sections(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        return [f"{rel}: its template file {head.group('path')} is unreadable ({exc})"]
    bad = [m.group(0).strip() for m in ANCHOR_INTENT.finditer(text)
           if not ANCHOR.match(text, m.start())]
    if bad:
        return [f"{rel}: anchor line does not parse: {b!r} — write "
                f"`extends|replaces: \"<heading>\" @<12 hex>|@new`" for b in bad]
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
    checked the overlay against the sections as they read now. Only an overlay the
    gate checks, whose lines all parse, is stamped."""
    if overlay.resolve() not in {p.resolve() for p in overlays(root)}:
        return [f"{overlay}: not an overlay the gate checks (docs/process/**/*.local.md with `overlay-of:`)"]
    problems = [p for p in check_one(root, overlay)
                if "changed this section" not in p and "not stamped yet" not in p]
    if problems:
        return problems
    raw = overlay.read_text(encoding="utf-8")
    text = unfenced(raw)
    head = HEAD.search(text.lstrip("\ufeff"))
    doc = sections(target_of(root, head.group("path")).read_text(encoding="utf-8"))
    missing = [_norm(a.group("heading")) for a in ANCHOR.finditer(text) if _norm(a.group("heading")) not in doc]
    if missing:
        return [f"{overlay}: section {m!r} is not in {head.group('path')} — re-home the anchor first"
                for m in missing]

    def fresh(a: re.Match) -> str:
        return f'{a.group("kind")}: "{a.group("heading")}" @{section_hash(doc[_norm(a.group("heading"))])}'

    lines = raw.splitlines(keepends=True)
    overlay.write_text("".join(ln if code else ANCHOR.sub(fresh, ln)
                               for ln, code in zip(lines, fenced(lines))), encoding="utf-8")
    return []


def main(argv: list[str]) -> int:
    if argv[:1] == ["--stamp"]:
        if len(argv) != 2:
            print("usage: check_overlays.py --stamp <overlay>", file=sys.stderr)
            return 2
        path = Path(argv[1]).resolve()
        import subprocess  # noqa: PLC0415
        top = subprocess.run(["git", "-C", str(path.parent if path.parent.is_dir() else Path.cwd()),
                              "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=False)
        root = Path(top.stdout.strip()).resolve() if top.returncode == 0 and top.stdout.strip() else Path.cwd().resolve()
        try:
            problems = stamp(root, path)
        except (OSError, UnicodeDecodeError) as exc:
            problems = [f"{path}: {exc}"]
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
