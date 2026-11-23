#!/usr/bin/env python3
"""How the gates read Markdown (core, always rendered): one owner for code fences,
HTML comments and ATX headings (#443).

Every gate that decides on a heading reads it here, on the text the record readers
see (`visible_lines`): fenced blocks out in the gates' old reading (`_legacy_scan`,
#250), HTML comments out as `uncommented` hides them, each line at its own number.
Where that text and a renderer's could differ, `ambiguity_problem` names the line and
the gate asks hard instead of guessing — there is no second reading (#250: every
refinement of the fence reading opened a new silent case, v2.75 review rounds 2–7).

  - `visible_lines(text)`: (1-based line, text) of every line a reader sees, the rest
    of a line after a `-->` at its own number; a leading BOM is dropped.
  - `heading(line)`: one line as a CommonMark ATX heading — 0–3 spaces in, 1–6 `#`,
    then a space, a tab or the line's end; never past the line's end; a bare `##` is
    an empty heading; a closing `#` run after whitespace is dropped (`## C#` stays).
  - `headings(text)`: `heading` over `visible_lines`.
  - `ambiguity_problem(text)`: the first line the two readings could read apart.

Known limits of `headings()` (not reported): headings inside container blocks
(`- ## H`, `> ## H`, indented under a list item) and inside raw HTML blocks (`<div>`)
are not read; setext headings are not read (`check_plan_structure._heading_level`
reads them where a section ends); a closer four or five columns under an opener one
to three columns in closes for both fence readings but not for CommonMark.
Readers outside the gates keep their own patterns on purpose: `human_digest.py`,
`changelog.py`, `tools/release_notes.py`, `tools/build_overview_pdf.py`, `optimize.py`.

Pure stdlib; imports no other gate.
"""
from __future__ import annotations

import bisect
import re
from typing import NamedTuple

_BOM = "﻿"
_FENCE_MARK = re.compile(r"(`{3,}|~{3,})")
# what `splitlines` reads as a line end and Markdown does not (refute #199: U+0085 kept
# a closed fence open in the render)
ODD_LINE_ENDS = re.compile("[\x0b\x0c\x1c\x1d\x1e\x85  ]")
_ODD_NAMES = {"\x0b": "a vertical tab", "\x0c": "a form feed", "\x1c": "a file separator",
              "\x1d": "a group separator", "\x1e": "a record separator", "\x85": "a next-line mark",
              " ": "a line separator", " ": "a paragraph separator"}


def fenced_lines(text: str) -> tuple[list[tuple[int, str]], int | None]:
    """The one fence walk every record reader shares (#250): (unquoted lines as
    (1-based lineno, line), line number of a fence still open at end of file or None).
    Fence lines themselves are not returned. It reads as the gates always read; where
    #250's stricter reading would quote a line differently, `fence_drift_problem` asks."""
    lines = text.splitlines()
    code, opened = _legacy_scan(lines)
    return ([(i, line) for i, (line, quoted) in enumerate(zip(lines, code), start=1) if not quoted],
            None if opened is None else opened + 1)


def _legacy_scan(lines: list[str]) -> tuple[list[bool], int | None]:
    """(per line: quoted?, index of a fence still open at the end) — the reading the
    gates have always used: a fence opens on a line starting with ``` or ~~~ after any
    indentation and closes on the next line starting with a run of its character at
    least as long."""
    out: list[bool] = []
    fence: str | None = None
    opened = None
    for i, line in enumerate(lines):
        m = re.match(r"(`{3,}|~{3,})", line.strip())
        if fence is None:
            if m:
                fence, opened = m.group(1), i
            out.append(fence is not None)
        else:
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence):
                fence = None
            out.append(True)
    return out, (opened if fence is not None else None)


def _strict_scan(lines: list[str]) -> list[bool]:
    """Per line: quoted? — #250's reading (CommonMark's closer): a fence opens on a line
    starting with ``` or ~~~ after any indentation (a backtick fence's info string holds
    no backtick) and closes only on a line holding nothing but its character, at least
    as long, at most three columns deeper than its opener. Only the yardstick of
    `fence_drift_problem`: each attempt to read records this way opened a new silent case
    (v2.75 review rounds 2–7)."""
    out: list[bool] = []
    fence, col = "", 0
    for raw in lines:
        line = raw.rstrip("\r\n").expandtabs(4)
        indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()
        if fence:
            if stripped and set(stripped) == {fence[0]} and len(stripped) >= len(fence) and indent <= col + 3:
                fence = ""
            out.append(True)
            continue
        m = re.match(r"(`{3,}|~{3,})(.*)$", stripped)
        if m and not (m.group(1)[0] == "`" and "`" in m.group(2)):
            fence, col = m.group(1), indent
        out.append(bool(fence))
    return out


def _drift(lines: list[str]) -> tuple[int, str] | None:
    for i, (quoted, was_quoted) in enumerate(zip(_strict_scan(lines), _legacy_scan(lines)[0]), start=1):
        if quoted != was_quoted:
            return i, (f"line {i} reads as {'quoted' if was_quoted else 'text'}, but as "
                       f"{'quoted' if quoted else 'text'} where a closing fence carries nothing "
                       f"else on its line (#250) — a fence line above it (an opener with text after "
                       f"it, or a closer with an info string) reads two ways; make each fence open "
                       f"and close on a line of its own")
    return None


def fence_drift_problem(text: str) -> str | None:
    """The first line #250's reading of fences (`_strict_scan`) quotes differently from the
    gates' reading (`_legacy_scan`), or None. #250: a closing fence carries no info
    string — a ```python line inside a ``` example closes nothing — yet every refinement
    that read records that way opened a new silent case, in both directions (v2.75 review
    rounds 2–7). So the gates keep their reading, and where the stricter one disagrees
    on any line the gate asks instead of guessing."""
    found = _drift(text.splitlines())
    return found[1] if found else None


# HTML comments as CommonMark renders them. A line starting with `<!--` (at
# most three spaces in) opens an HTML block that ends at the line carrying
# `-->`; unclosed, it hides the rest of the file. In running text a comment is
# hidden only when it closes within its paragraph — an unclosed `<!--` there
# is literal text (downstream: "write `<!--` to start a comment" in prose
# swallowed a real record below it). Scanned left to right, the way the
# renderer does: a code span (`<!--` in backticks) is code, a comment opened
# first hides the backticks inside it, `\`` and `\<` are escaped characters.
# Linear time: once no `-->` (or no closing backtick run of a length) follows,
# none is searched again.
# Known limits (a record may be read where a renderer hides it, or the other
# way round): the `<!-->` / `<!--->` forms, comments inside container blocks
# (block quotes, list items indented past three spaces), HTML blocks of other
# kinds (`<div>`, `<pre>`, `<script>`), indented code blocks, entity-escaped
# markers, and setext/table edge cases are not modelled. `ambiguity_problem`
# asks where the first and a comment across a heading or fence line would read
# apart.
_BLOCK_COMMENT = re.compile(r"^ {0,3}<!--")
_ASCII_PUNCT = set("!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~")


def _closing_run(para: str, run: int, pos: int) -> int:
    """Start of the next backtick run of exactly `run` from `pos`, or -1."""
    ticks = "`" * run
    while True:
        k = para.find(ticks, pos)
        if k < 0:
            return -1
        end = k + run
        while end < len(para) and para[end] == "`":
            end += 1
        if end - k == run:
            return k
        pos = end


def _comment_spans(para: str) -> list[tuple[int, int]]:
    """The [start, end) spans of `para` an inline HTML comment hides."""
    spans: list[tuple[int, int]] = []
    i = 0
    n = len(para)
    no_comment_close = False
    no_tick_close: set[int] = set()
    while i < n:
        c = para[i]
        if c == "\\" and i + 1 < n and para[i + 1] in _ASCII_PUNCT:
            i += 2
            continue
        if c == "`":
            j = i
            while j < n and para[j] == "`":
                j += 1
            run = j - i
            if run not in no_tick_close:
                k = _closing_run(para, run, j)
                if k >= 0:
                    i = k + run
                    continue
                no_tick_close.add(run)
            i = j
            continue
        if c == "<" and not no_comment_close and para.startswith("<!--", i):
            k = para.find("-->", i + 4)
            if k < 0:
                no_comment_close = True
                i += 4
                continue
            spans.append((i, k + 3))
            i = k + 3
            continue
        i += 1
    return spans


def _inline_uncommented(para: str) -> str:
    out: list[str] = []
    start = 0
    for a, b in _comment_spans(para):
        out.append(para[start:a])
        start = b
    out.append(para[start:])
    return "".join(out)


def uncommented(text: str) -> str:
    """`text` without what an HTML comment hides when rendered."""
    out: list[str] = []
    para: list[str] = []

    def flush() -> None:
        if para:
            out.append(_inline_uncommented("\n".join(para)))
            para.clear()

    in_block = False
    for line in text.splitlines():
        if in_block:
            in_block = "-->" not in line
            continue
        if _BLOCK_COMMENT.match(line):
            flush()
            in_block = "-->" not in line[line.index("<!--") + 4:]
            continue
        if not line.strip():
            flush()
            out.append("")
            continue
        para.append(line)
    flush()
    return "\n".join(out)


class Line(NamedTuple):
    """A line a reader sees: its own 1-based number, its visible text, and whether a
    comment hid its start — then it continues the paragraph above and opens no block."""
    lineno: int
    text: str
    continued: bool


class _Walk(NamedTuple):
    lines: list[Line]
    spans: list[tuple[int, int]]  # (first, last) line of an inline comment over several lines


def _walk(numbered: list[tuple[int, str]]) -> _Walk:
    """`uncommented` over numbered lines, line for line: the same blocks, paragraphs and
    spans, each piece of text at the line it stands on (r2 M2)."""
    out: list[Line] = []
    multi: list[tuple[int, int]] = []
    para: list[tuple[int, str]] = []

    def flush() -> None:
        if not para:
            return
        joined = "\n".join(line for _n, line in para)
        starts: list[int] = []
        pos = 0
        for _n, line in para:
            starts.append(pos)
            pos += len(line) + 1
        spans = _comment_spans(joined)
        for (n, line), a in zip(para, starts):
            b = a + len(line)
            pieces: list[str] = []
            cur, hidden_start = a, False
            for s, e in spans:
                if e <= a or s >= b:
                    continue
                hidden_start = hidden_start or s <= a
                if s > cur:
                    pieces.append(joined[cur:s])
                cur = max(cur, e)
            if cur < b:
                pieces.append(joined[cur:b])
            if any(pieces):
                out.append(Line(n, "".join(pieces), hidden_start))
        for s, e in spans:
            first = bisect.bisect_right(starts, s) - 1
            last = bisect.bisect_right(starts, e - 1) - 1
            if last > first:
                multi.append((para[first][0], para[last][0]))
        para.clear()

    in_block: int | None = None
    for n, line in numbered:
        if in_block is not None:
            if "-->" in line:
                in_block = None
            continue
        if _BLOCK_COMMENT.match(line):
            flush()
            if "-->" not in line[line.index("<!--") + 4:]:
                in_block = n
            continue
        if not line.strip():
            flush()
            out.append(Line(n, line, False))
            continue
        para.append((n, line))
    flush()
    return _Walk(out, multi)


def visible(text: str) -> list[Line]:
    """Every line a reader of the rendered file sees, as `Line`s (see `visible_lines`)."""
    return _walk(fenced_lines(text.removeprefix(_BOM))[0]).lines


def visible_lines(text: str) -> list[tuple[int, str]]:
    """(1-based line, visible text) of every line outside a code block (the gates'
    reading, `_legacy_scan`) and outside an HTML comment (`uncommented`'s reading). Line
    true: each piece keeps the number of the line it stands on — the rest of a line after
    a `-->` too. A leading BOM is dropped. Blank lines are kept; a line a comment hides
    whole is not returned."""
    return [(line.lineno, line.text) for line in visible(text)]


def blanked(text: str) -> tuple[list[str], frozenset[int]]:
    """(one string per line of the file, hidden text left out and a line holding nothing
    else blank; the 0-based indices of lines whose start a comment hid) — for readers that
    walk a file by line index (tables, setext headings)."""
    body = text.removeprefix(_BOM)
    kept = [""] * len(body.splitlines())
    continued: set[int] = set()
    for line in visible(body):
        kept[line.lineno - 1] = line.text if line.text.strip() else ""
        if line.continued:
            continued.add(line.lineno - 1)
    return kept, frozenset(continued)


def _comments_blank(text: str) -> str:
    """The text without what an HTML comment hides when rendered (`uncommented`, the one
    reader of comments), each kept piece at its own line number: a finding names the
    file's line, and the rest of a line after a `-->` stays on that line."""
    lines = text.replace("\x00", "").splitlines()
    kept = [""] * len(lines)
    for line in _walk(list(enumerate(lines, 1))).lines:
        kept[line.lineno - 1] = line.text if line.text.strip() else ""
    return "\n".join(kept)


_ATX = re.compile(r" {0,3}(#{1,6})(?:[ \t]+(.*?))?[ \t]*")
_CLOSING = re.compile(r"(?:^|[ \t]+)#+$")


def heading(line: str) -> tuple[int, str] | None:
    """(level, text) of `line` read as a CommonMark ATX heading, or None: at most three
    spaces in, one to six `#`, then a space, a tab or the line's end — `#5` and `#hash`
    are text, `####### x` too. Never past the line's end. A bare `##` is an empty
    heading; a closing run of `#` after a space or tab is dropped, `## C#` stays "C#"."""
    m = _ATX.fullmatch(line.removesuffix("\n").removesuffix("\r"))
    if m is None:
        return None
    return len(m.group(1)), _CLOSING.sub("", m.group(2) or "").rstrip(" \t")


class Heading(NamedTuple):
    level: int
    text: str
    lineno: int


def headings(text: str) -> list[Heading]:
    """Every ATX heading a reader of the rendered file sees: `heading` over
    `visible_lines` — none in a code block or an HTML comment, none on a line whose
    start a comment hid; `lineno` is the file's own line. Limits in the module
    docstring (containers, raw HTML blocks, setext)."""
    out: list[Heading] = []
    for line in visible(text):
        found = None if line.continued else heading(line.text)
        if found is not None:
            out.append(Heading(found[0], found[1], line.lineno))
    return out


class HeadingRule:
    """A heading a gate looks for: a level range and a pattern its text starts with —
    one rule for every reader of it (`.search` a file, `.match` one line)."""

    def __init__(self, pattern: str, levels: range, flags: int = 0) -> None:
        self.pattern = re.compile(pattern, flags)
        self.levels = levels

    def fits(self, level: int, text: str) -> bool:
        """Is a heading of `level` and `text` this one?"""
        return level in self.levels and self.pattern.match(text) is not None

    def match(self, line: str) -> tuple[int, str] | None:
        """(level, text) when `line` is such a heading, else None."""
        found = heading(line)
        return found if found is not None and self.fits(*found) else None

    def search(self, text: str) -> Heading | None:
        """The first such heading a reader of `text` sees (`headings`), else None."""
        return next((h for h in headings(text) if self.fits(h.level, h.text)), None)


_EMPTY_COMMENTS = ("<!-->", "<!--->")


def _block_comments(lines: list[str]) -> tuple[int, int, str] | None:
    """Rules 2, 5 and 7 — one walk over the block comments, whichever opens first wins (a
    `<!--` inside a code block is code, r2 M1): (line, rule, message) of the first of a
    fence marker inside a comment opened outside a fence (2), a comment that never closes
    (5), a line holding only `<!-->` or `<!--->` (7)."""
    fence: str | None = None
    comment: int | None = None
    for i, line in enumerate(lines, 1):
        m = _FENCE_MARK.match(line.strip())
        if fence is not None:
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence):
                fence = None
            continue
        if comment is not None:
            if m:
                return i, 2, (f"line {i}: a code fence stands inside the HTML comment opened on line "
                              f"{comment} — the gates read a code block from here and hide what "
                              f"follows the comment, a renderer shows it; take the fence out of the "
                              f"comment")
            if "-->" in line:
                comment = None
            continue
        if m:
            fence = m.group(1)
        elif line.strip() in _EMPTY_COMMENTS:
            return i, 7, (f"line {i}: `{line.strip()}` closes a comment for a renderer but opens one "
                          f"for the gates; write `<!-- … -->` or remove the line")
        elif _BLOCK_COMMENT.match(line) and "-->" not in line[line.index("<!--") + 4:]:
            comment = i
    if comment is not None:
        return comment, 5, (f"line {comment}: an HTML comment opens here and never closes — it hides "
                            f"the rest of the file from every gate; close it with `-->`")
    return None


def _indented_fence(lines: list[str]) -> tuple[int, str] | None:
    """Rule 6: a fence opened four or more columns in whose closer stands more than three
    columns further left, or never comes — outside a list item a renderer reads that
    opener as indented code or paragraph text, the gates as a fence."""
    fence: str | None = None
    col = line_no = 0
    for i, raw in enumerate(lines, 1):
        expanded = raw.expandtabs(4)
        indent = len(expanded) - len(expanded.lstrip(" "))
        m = _FENCE_MARK.match(raw.strip())
        if fence is not None:
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence):
                if col >= 4 and indent < col - 3:
                    break
                fence = None
            continue
        if m:
            fence, col, line_no = m.group(1), indent, i
    else:
        if fence is None or col < 4:
            return None
    return line_no, (f"line {line_no}: a code fence opens {col} columns in and its closer stands "
                     f"further left or never comes — outside a list item a renderer reads indented "
                     f"code or text there, the gates a code block; indent the fence at most three "
                     f"spaces, or align its closer under it")


def ambiguity_problem(text: str) -> str | None:
    """The first line the gates' reading (`visible_lines`) and a renderer's could read
    two ways, with what to do — or None:

      1. the two fence readings differ (`fence_drift_problem`, #250);
      2. a fence marker inside an HTML comment opened outside a fence;
      3. U+2028, U+2029, U+0085, a vertical tab, a form feed or FS/GS/RS — `splitlines`
         ends a line there, a renderer does not;
      4. an inline `<!--` closed on a later line, with a line in between (or on either
         end) that is a heading or carries a fence marker — a renderer ends the
         paragraph there, `uncommented` hides it;
      5. a block `<!--` that never closes — it hides the rest of the file;
      6. a fence opened four or more columns in whose closer stands more than three
         columns further left, or never comes;
      7. a line holding only `<!-->` or `<!--->` — a renderer closes the comment there,
         `uncommented` does not.
    """
    body = text.removeprefix(_BOM)
    lines = body.splitlines()
    found: list[tuple[int, int, str]] = []
    odd = ODD_LINE_ENDS.search(body)
    if odd:
        n = body.count("\n", 0, odd.start()) + 1
        found.append((n, 3, (f"line {n} holds {_ODD_NAMES[odd.group()]} (U+{ord(odd.group()):04X}) — "
                             f"the gates end a line there, a renderer does not; replace it with a "
                             f"newline or a space")))
    for rule, hit in ((1, _drift(lines)), (6, _indented_fence(lines))):
        if hit:
            found.append((hit[0], rule, hit[1]))
    comments = _block_comments(lines)
    if comments:
        found.append(comments)
    for first, last in _walk(fenced_lines(body)[0]).spans:
        for n in range(first, last + 1):
            raw = lines[n - 1]
            if heading(raw) is not None or _FENCE_MARK.match(raw.strip()):
                found.append((n, 4, (f"line {n}: an HTML comment opened on line {first} closes on line "
                                     f"{last} across a heading or code fence — the gates hide it, a "
                                     f"renderer ends the paragraph there and shows it; put the comment "
                                     f"on lines of its own (`<!--` at a line's start)")))
                break
    return min(found)[2] if found else None
