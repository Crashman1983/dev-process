"""changelog (core): the grammar of a template release's notes, in one place.

An entry is the section that starts with `## vX.Y.Z — <title> · <date>` (the date
optional) and runs until the next `## ` or `# ` heading. Before that form an entry
was a bold paragraph, `**vX.Y.Z — <title>.** body`, running until the next such
paragraph or any heading; an old tag's CHANGELOG still reads that way, and its
notes must stay publishable.

From v2.97 every first-level item under **What changes.** (German: **Was sich
ändert.**) starts with its mark, right after the dash: `- [required] …`,
`- [recommended] …` or `- [optional] …`. `required` means security, a broken
contract, data loss or a defect that blocks work. The template's release tool
refuses an unmarked item in a new entry; `template_update.py --dry-run` lists the
required items of every release a project is about to take.

Readers: `tools/release_notes.py` and `tools/release.py` (the template repository's
own tools), `template_update.py`. Stdlib only.
"""
from __future__ import annotations

import re

# one `## vX.Y.Z — <title> · <date>` section per release (MAINTAINING.md)
ENTRY = re.compile(r"^##\s+(v\d+\.\d+\.\d+)\s+—\s+(.+?)(?:\s+·\s+\d{4}-\d{2}-\d{2})?\s*$")
# the bold paragraph form before it, `**vX.Y.Z — <title>.** body`
OLD_ENTRY = re.compile(r"^\*\*(v\d+\.\d+\.\d+)\s+—\s+(.+?)\*\*\s*(.*)$")
MARKS = ("required", "recommended", "optional")
CHANGES = ("**What changes.**", "**Was sich ändert.**")
# the parts that follow What changes in an entry (CHANGELOG preamble): the part ends at the next
_PART = re.compile(r"^\*\*[^*]+\.\*\*[ \t]*$")  # a part label alone on its line, e.g. **Effect.**
_ITEM = re.compile(r"^(?:[-*+]|\d+[.)])[ \t]+(?P<text>.*)$")
_MARK = re.compile(r"^\[(?P<mark>" + "|".join(MARKS) + r")\][ \t]*(?P<rest>.*)$")


def _scan(text: str) -> list[tuple[str, str, str, bool]]:
    """(version, title, body, old form) per entry: the heading entries in order, then
    the bold ones — a CHANGELOG that has both keeps the heading form first."""
    lines = text.splitlines()
    out: list[tuple[str, str, str, bool]] = []
    for i, line in enumerate(lines):
        m = ENTRY.match(line)
        if not m:
            continue
        body = []
        for nxt in lines[i + 1:]:
            if nxt.startswith("## ") or nxt.startswith("# "):
                break
            body.append(nxt)
        out.append((m.group(1), m.group(2).rstrip("."), "\n".join(body).strip(), False))
    for i, line in enumerate(lines):
        m = OLD_ENTRY.match(line)
        if not m:
            continue
        body = [m.group(3)] if m.group(3) else []
        for nxt in lines[i + 1:]:
            if OLD_ENTRY.match(nxt) or nxt.startswith("#"):
                break
            body.append(nxt)
        out.append((m.group(1), m.group(2).rstrip("."), "\n".join(body).strip(), True))
    return out


def entries(text: str) -> list[tuple[str, str, str]]:
    """(version, title, body) of every entry, body stripped."""
    return [(version, title, body) for version, title, body, _old in _scan(text)]


def notes(text: str, tag: str) -> tuple[str, str] | None:
    """The entry of `tag` as release notes (title, body + newline); None without one —
    or for a heading entry with an empty body: a heading alone tells a reader nothing."""
    for version, title, body, old in _scan(text):
        if version == tag:
            return (title, body + "\n") if body or old else None
    return None


def marks(body: str) -> list[tuple[str | None, str]]:
    """(mark or None, first line) of every first-level item under **What changes.** /
    **Was sich ändert.**, which runs until the next part label alone on its line
    (`**Effect.**`, `**Update.**` …) or a heading — a bold note inside the part does
    not end it. Numbered items count as items. The first line comes without its dash
    and mark. A body without that part has no item."""
    out: list[tuple[str | None, str]] = []
    inside = False
    for line in body.splitlines():
        if line.startswith(CHANGES):
            inside = True
            continue
        if _PART.match(line.strip()) or line.startswith("#"):
            inside = False
        if not inside:
            continue
        item = _ITEM.match(line)
        if item is None:
            continue
        mark = _MARK.match(item.group("text"))
        out.append((mark.group("mark"), mark.group("rest").strip()) if mark
                   else (None, item.group("text").strip()))
    return out
