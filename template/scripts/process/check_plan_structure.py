#!/usr/bin/env python3
"""plan-structure gate (core): the structure of an active Tier 2+ plan, checked
when the plan is written instead of by a plan-review round (#278).

Seven of twenty findings where a check never took effect (dev-process #277,
step 0 on Kenni's history) were rules about a plan's structure that existed
only as prose: required sections, criteria nobody could test, tasks left open
at the merge. A plan reviewer re-found them by reading. This gate reads them:

  HARD (an active Tier 2+ plan this branch adds):
  - a criterion line `AC-<id>: <EARS statement>` with no or several `shall`
    (an EARS requirement has exactly one; `shall_words` adds others, e.g.
    German `soll`), or an id twice;
  - a criterion without its planned test, from the first push on (#327: a
    branch that owed it only at the merge passed branch push and review and
    failed at main): `AC-<id>: <path>::<test>` or `AC-<id>: struck —
    <reason>` — the report line's own grammar (attest knows no other proof),
    so plan and report cannot drift apart;
  - a section the project requires (`sections`) missing;
  - a story id the plan names that the registry does not hold (`story_id`
    and `registry`, both set);
  - at the merge push, an open `- [ ]` task without `struck: <reason>` or
    `moved: #<issue>`;
  - a `## Transitions` section (`check_review.TRANSITIONS_HEADING`: an ATX heading
    of level 2 or deeper; `# Transitions` is the plan's title level and not read;
    a setext heading ends a section but opens none)
    without a pipe table below it, before the next heading (ATX or setext) of
    the same or a higher level; no table there with a `Test` column (`Tests`,
    `Test(s)`) and two others — a table without one beside it, the writer
    and reader inventory, is no finding; a test table without a row; a row
    with an empty cell; a test cell that is neither `<path>::<test>` nor
    `struck — <reason>` (#293). Rows of one equivalence class may name the
    same test. No `Invariant:` line in the section outside its tables and
    indented code, or one
    that is neither `Invariant: <statement> — owner: <owner> — <test>` (the
    test as in a test cell) nor `Invariant: none — <reason>` (#312). Read as
    rendered: what an HTML comment hides is neither section nor table.
  NOTE: an `[assumption]` left in a DECISION line.

Bound are only plans the branch ADDS — absent at the integration ref, or below
Tier 2 there (a stub raised here) — so a plan merged before this gate is
history, not a new duty. A Spec Kit plan (`specs/<name>/plan.md`) is bound by
the same rule when it is Tier 2+; it answers for its Transitions
section only. Project data,
`docs/process/plan-structure.local.json`, is read at the integration ref like
every evidence rule (a branch cannot lift its own duty):
  {"sections": ["Anchor Delta"], "shall_words": ["shall"],
   "story_id": "[A-Z]+-US-\\\\d+", "registry": "docs/feature-registry/*/*.json"}

Fenced text is quotation and is not read. Stdlib only.
"""
from __future__ import annotations

import fnmatch
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling import
from attest_evidence import AC_LINE, STRUCK_LINE, _NAMES_A_TEST, _STRUCK_MARK, ac_key  # noqa: E402
from check_review import (  # noqa: E402  (one owner for plan grammar and fences)
    DECISION_LINE,
    OPEN_TASK,
    PLACEHOLDER,
    SPEC_PLAN,
    SPECS_DIR,
    TRANSITIONS_HEADING,
    GitReadError,
    fenced_lines,
    integration_push,
    integration_ref,
    plan_tier,
    uncommented,
)
from process_git import git_environment  # noqa: E402  (one owner for how git is read)

PLANS_ACTIVE = ".process-work/plans"
DATA = "docs/process/plan-structure.local.json"
_SETTLED = re.compile(r"\b(?:struck:[ \t]*\S|moved:[ \t]*#\d+)", re.IGNORECASE)
_ASSUMPTION = re.compile(r"\[assumption\]", re.IGNORECASE)


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=git_environment())


class _Unreadable(Exception):
    """git could not tell whether, or what, a file is at a ref."""


def _at_ref(root: Path, ref: str, rel: str) -> str | None:
    """The file at `ref`; None: not there. A failed read is no absence: it raises."""
    listed = _git(root, "ls-tree", "--name-only", ref, "--", rel)
    if listed.returncode != 0:
        raise _Unreadable(listed.stderr.strip() or f"git ls-tree exit {listed.returncode}")
    if not listed.stdout.strip():
        return None
    shown = _git(root, "show", f"{ref}:{rel}")
    if shown.returncode != 0:
        raise _Unreadable(shown.stderr.strip() or f"git show exit {shown.returncode}")
    return shown.stdout


def _quoted_blank(text: str) -> str:
    """The text with fenced lines blanked, not dropped: a finding's line number is the
    file's own (`_unfenced` compacts the text)."""
    kept = dict(fenced_lines(text)[0])
    return "\n".join(kept.get(i, "") for i in range(1, len(text.splitlines()) + 1))


def load_data(root: Path, ref: str) -> tuple[dict, str]:
    """(project data, problem) — read at the integration ref."""
    try:
        text = _at_ref(root, ref, DATA)
    except _Unreadable as exc:
        return {}, f"{DATA} at the integration ref cannot be read ({exc}) — the plan rules are unknown"
    if text is None:
        return {}, ""
    try:
        data = json.loads(text)
    except ValueError as exc:
        return {}, f"{DATA} is not valid JSON ({exc})"
    if not isinstance(data, dict):
        return {}, f"{DATA} must be a JSON object"
    for key in ("sections", "shall_words"):
        if key in data and not (isinstance(data[key], list) and all(isinstance(x, str) and x for x in data[key])):
            return {}, f"{DATA}: {key} must be a list of strings"
    for key in ("story_id", "registry"):
        if key in data and not (isinstance(data[key], str) and data[key]):
            return {}, f"{DATA}: {key} must be a string"
    if "story_id" in data:
        try:
            re.compile(data["story_id"])
        except re.error as exc:
            return {}, f"{DATA}: story_id is no regular expression ({exc})"
    return data, ""


def _is_proof(body: str) -> bool:
    return bool(_NAMES_A_TEST.search(body))


def criteria_findings(rel: str, text: str, shall_words: list[str], *, need_tests: bool) -> list[str]:
    """The criterion and planned-test findings of one plan (unfenced text)."""
    out: list[str] = []
    shall = re.compile(r"\b(?:" + "|".join(re.escape(w) for w in shall_words) + r")\b", re.IGNORECASE)
    struck = {ac_key(m) for m in STRUCK_LINE.finditer(text)}
    criteria: dict[str, int] = {}
    proven: set[str] = set()
    for m in AC_LINE.finditer(text):
        key, body = ac_key(m), m.group("body").strip()
        if key in struck and not _is_proof(body):
            continue
        if _is_proof(body):
            proven.add(key)
            continue
        if not body:
            continue
        line = text.count("\n", 0, m.start()) + 1
        if key in criteria:
            out.append(f"{rel}:{line}: AC-{key} is named twice as a criterion — one id, one requirement")
            continue
        criteria[key] = line
        n = len(shall.findall(body))
        if n != 1:
            words = "/".join(shall_words)
            out.append(f"{rel}:{line}: AC-{key} has {n} × `{words}` — an EARS requirement states exactly "
                       f"one (`When <trigger>, <system> shall <response>`); split it or name the response")
    if need_tests:
        for key, line in sorted(criteria.items(), key=lambda kv: kv[1]):
            if key not in proven and key not in struck:
                out.append(f"{rel}:{line}: AC-{key} names no planned test — add `AC-{key}: <path>::<test>` "
                           f"(it may not exist yet) or `AC-{key}: struck — <reason>`")
    return out


_HEADING = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]|$)")
_SETEXT = re.compile(r"^ {0,3}(=+|-+)[ \t]*$")
_LIST_ITEM = re.compile(r"^ {0,3}(?:[-*+]|\d{1,9}[.)])(?:[ \t]|$)")
_INDENTED = re.compile(r"^(?: {4}| {0,3}\t)")  # indented code: no heading, no table
_DELIMITER_CELL = re.compile(r"^:?-+:?$")
_PIPE = re.compile(r"(?<!\\)\|")
_TEST_HEADER = re.compile(r"^tests?(?:\(s\))?$", re.IGNORECASE)
_UNFILLED = {"", "…", "..."}
_LINE_MARK = re.compile(r"\x00(\d+)\x00$")
# a row's test cell struck on purpose: the criterion strike's own mark and reason rule
_STRUCK_CELL = re.compile(r"^" + _STRUCK_MARK + r"[ \t]*" + PLACEHOLDER + r"\S*\w")
# the invariant beside the table (#312), read from the right: the test after the owner,
# `owner: <owner>` after the last separator before it, the rest the statement — which may
# hold a separator itself. Separators as for a strike, an owner in backticks or bare.
_SEP = r"(?:[ \t]*[—–][ \t]*|[ \t]+--[ \t]+)"
_INVARIANT = re.compile(r"^[ \t]*(?:[-*+][ \t]+)?Invariant:[ \t]*(?P<body>.*?)[ \t]*$")
_INVARIANT_NONE = re.compile(r"^(?i:none)(?:" + _SEP + r"(?P<reason>.*))?$")
_INVARIANT_OWNED = re.compile(r"^(?P<statement>.*)" + _SEP + r"owner:[ \t]*(?P<owner>`[^`]*`|[^\s`—–]*)"
                              r"(?:" + _SEP + r"(?P<test>.*))?$")
_OWNER = re.compile(r"^[\w./:-]*\w[\w./:-]*$")  # `module.function`, `path/file.py:function`
_FILLED = re.compile(PLACEHOLDER + r"\S*\w")  # the strike's reason rule


def _cells(row: str) -> list[str]:
    """The cells of a pipe-table row: outer pipes dropped, an escaped `\\|` kept."""
    body = row.strip()
    body = body[1:] if body.startswith("|") else body
    body = body[:-1] if body.endswith("|") and not body.endswith("\\|") else body
    return [c.strip() for c in _PIPE.split(body)]


def _bare(cell: str) -> str:
    return cell.strip().strip("`*_").strip()


def _comments_blank(text: str) -> str:
    """The text without what an HTML comment hides when rendered (`check_review.uncommented`,
    the one reader of comments), each kept line at its own line number: a finding names
    the file's line. Every non-blank line carries its number through the reader; a line a
    comment ran into keeps its rest at the line the comment closed on."""
    lines = text.replace("\x00", "").splitlines()
    marked = "\n".join(f"{line}\x00{n}\x00" if line.strip() else line for n, line in enumerate(lines, 1))
    kept = [""] * len(lines)
    for piece in uncommented(marked).splitlines():
        m = _LINE_MARK.search(piece)
        if m:
            kept[int(m.group(1)) - 1] = piece[:m.start()]
    return "\n".join(kept)


def _is_row(line: str) -> bool:
    """A line a pipe table may hold: an unescaped `|`, not indented code."""
    return bool(_PIPE.search(line)) and not _INDENTED.match(line) and not _HEADING.match(line)


def _is_delimiter(line: str) -> bool:
    return _is_row(line) and all(_DELIMITER_CELL.match(c) for c in _cells(line))


def _tables(lines: list[str]) -> list[list[tuple[int, str]]]:
    """The pipe tables of the text as GFM reads them, outer pipes optional: a header row,
    a delimiter row below it, then every row up to a line without an unescaped `|`."""
    out: list[list[tuple[int, str]]] = []
    k = 0
    while k + 1 < len(lines):
        if not (_is_row(lines[k]) and _is_delimiter(lines[k + 1])):
            k += 1
            continue
        table = [(k + 1, lines[k]), (k + 2, lines[k + 1])]
        k += 2
        while k < len(lines) and _is_row(lines[k]):
            table.append((k + 1, lines[k]))
            k += 1
        out.append(table)
    return out


def _heading_level(lines: list[str], j: int, table_rows: set[int]) -> int | None:
    """The level of a heading at line index `j`: ATX (`## x`, up to three spaces in) or a
    setext underline (`===` level 1, `---` level 2) below a paragraph line — below a
    blank, a heading, a list item or a table row `---` is a thematic break."""
    h = _HEADING.match(lines[j])
    if h:
        return len(h.group(1))
    s = _SETEXT.match(lines[j])
    if not s or j == 0:
        return None
    above = lines[j - 1]
    if (not above.strip() or _INDENTED.match(above) or _HEADING.match(above) or _LIST_ITEM.match(above)
            or _SETEXT.match(above) or j - 1 in table_rows):
        return None
    return 1 if s.group(1)[0] == "=" else 2


def _sections(lines: list[str], table_rows: set[int]) -> list[tuple[int, str, list[tuple[int, str]]]]:
    """(line, heading, body lines) of every Transitions section: from its heading to the
    next heading of the same or a higher level, ATX or setext."""
    out: list[tuple[int, str, list[tuple[int, str]]]] = []
    for i, line in enumerate(lines):
        if not TRANSITIONS_HEADING.match(line):
            continue
        marks = line.lstrip(" ")
        level = len(marks) - len(marks.lstrip("#"))
        body: list[tuple[int, str]] = []
        for j in range(i + 1, len(lines)):
            found = _heading_level(lines, j, table_rows)
            if found is not None and found <= level:
                if not _HEADING.match(lines[j]):
                    body.pop()  # the setext heading's own text line
                break
            body.append((j + 1, lines[j]))
        out.append((i + 1, line.strip(), body))
    return out


def _names_test(cell: str) -> bool:
    """A test cell's grammar, the invariant's test too: `<path>::<test>` or `struck — <reason>`."""
    return _is_proof(cell) or bool(_STRUCK_CELL.match(_bare(cell)))


def _invariant_line(rel: str, n: int, body: str) -> list[str]:
    """The findings on one `Invariant:` line, `body` the text after the colon."""
    where = f"{rel}:{n}: the `Invariant:` line"
    none = _INVARIANT_NONE.match(body)
    if none:
        if not _FILLED.match(none.group("reason") or ""):
            return [f"{where} leaves its reason a placeholder — `Invariant: none — <why the section has none>`"]
        return []
    owned = _INVARIANT_OWNED.match(body)
    owner = owned.group("owner").strip("`").strip() if owned else ""
    if not owned or (_FILLED.match(owner) and not _OWNER.match(owner)):
        return [f"{where} follows neither form — `Invariant: <statement> — owner: <owner> — "
                f"<path>::<test>` (the owner `module.function` or `path/file.py:function`) or "
                f"`Invariant: none — <reason>`"]
    out: list[str] = []
    for part, value in (("statement", owned.group("statement")), ("owner", owner)):
        if not _FILLED.match(value.strip()):
            out.append(f"{where} leaves its {part} a placeholder — name the invariant and the one "
                       f"function that keeps it")
    if not _names_test(owned.group("test") or ""):
        out.append(f"{where} names no test — end it with `<path>::<test>` (it may not exist yet) or "
                   f"`struck — <reason>`")
    return out


def invariant_findings(rel: str, line: int, heading: str, body: list[tuple[int, str]],
                       table_rows: set[int]) -> list[str]:
    """The findings on one Transitions section's invariant (#312): at least one `Invariant:`
    line in its body outside its tables and indented code, each read on its own. The plans
    that converged after six code rounds named their invariant; the table alone did not."""
    out: list[str] = []
    found = False
    for n, text in body:
        m = _INVARIANT.match(text)
        if m and n - 1 not in table_rows and not _INDENTED.match(text):
            found = True
            out += _invariant_line(rel, n, m.group("body"))
    if not found:
        out.append(f"{rel}:{line}: `{heading}` has no `Invariant:` line — name the invariant, its owner "
                   f"and its test, or `Invariant: none — <reason>`")
    return out


def transitions_findings(rel: str, text: str, *, need_tests: bool) -> list[str]:
    """The findings on a plan's Transitions sections (unfenced text, the file's own line
    numbers), read as rendered — an HTML comment hides a heading and a table alike: a
    pipe table below each whose header and delimiter row name the same number of cells,
    with a `Test` column (`Tests`, `Test(s)`) and two others, at
    least one row, every cell of every row filled; once tests are due, each test cell
    `<path>::<test>` or `struck — <reason>`. The section's first table is its transitions
    table: without a `Test` column it is refused, whatever follows — a `Test` column in a
    later table lends it none. A later table without one (the writer and reader inventory) is
    free; a later table with one is read like the first, so a first table with a `Test`
    column answers for itself, not for a state table below it (v2.77 cross-model review,
    rounds 1 and 2)."""
    out: list[str] = []
    lines = _comments_blank(text).splitlines()
    tables = _tables(lines)
    table_rows = {n - 1 for table in tables for n, _row in table}
    for line, heading, body in _sections(lines, table_rows):
        out += invariant_findings(rel, line, heading, body, table_rows)
        span = {n for n, _line in body}
        mine = [t for t in tables if t[0][0] in span]
        if not mine:
            out.append(f"{rel}:{line}: `{heading}` has no table below it — state × event → result with a "
                       f"`Test` column (docs/process/design-template.md, Transitions)")
            continue
        table = mine[0]
        header = [_bare(c) for c in _cells(table[0][1])]
        tests = [k for k, name in enumerate(header) if _TEST_HEADER.match(name)]
        if not tests:
            out.append(f"{rel}:{table[0][0]}: the transitions table has no `Test` column — one test per "
                       f"row; rows of one equivalence class may name the same test (the section's first "
                       f"table is its transitions table; an inventory table goes after it)")
            continue
        read = [(table, header, tests)]
        for later in mine[1:]:
            names = [_bare(c) for c in _cells(later[0][1])]
            cols = [k for k, name in enumerate(names) if _TEST_HEADER.match(name)]
            if cols:
                read.append((later, names, cols))
        for table, header, tests in read:
            hline = table[0][0]
            delimiter = _cells(table[1][1])
            if len(delimiter) != len(header):
                out.append(f"{rel}:{hline}: the transitions table has {len(header)} header cells and "
                           f"{len(delimiter)} delimiter cells — a GFM table's delimiter row names one "
                           f"cell per column")
                continue
            if len(header) < 3:
                out.append(f"{rel}:{hline}: the transitions table needs a `Test` column and at least two "
                           f"others (state × event → result)")
                continue
            if len(table) == 2:
                out.append(f"{rel}:{hline}: the transitions table has no row — one row per transition, "
                           f"forbidden ones included")
                continue
            for n, row in table[2:]:
                cells = _cells(row)
                if len(cells) != len(header):
                    out.append(f"{rel}:{n}: transitions row has {len(cells)} cells, the header {len(header)}")
                    continue
                empty = [header[k] or f"column {k + 1}" for k, c in enumerate(cells) if _bare(c) in _UNFILLED]
                if empty:
                    out.append(f"{rel}:{n}: transitions row leaves {', '.join(f'`{e}`' for e in empty)} "
                               f"empty — fill every cell")
                    continue
                cell = cells[tests[0]]
                if need_tests and not _names_test(cell):
                    out.append(f"{rel}:{n}: transitions row names no test — `<path>::<test>` (it may not "
                               f"exist yet) or `struck — <reason>`")
    return out


def _bound(root: Path, ref: str, rel: str) -> bool:
    """Is this plan the branch's to answer for? Added on the branch, or below Tier 2 at
    the integration ref (a stub raised to Tier 2 here is written here). An archived plan
    is judged where it lived before `/finish` moved it, or before `publish_and_prune` copied
    a spec's plan there (`specs/<slug>/plan.md`, #343), too: an old plan archived here is
    history. Unreadable at the ref: bound (fail closed)."""
    homes = [rel]
    if rel.startswith(f"{PLANS_ACTIVE}/archive/"):
        name = rel.rsplit("/", 1)[1]
        homes += [f"{PLANS_ACTIVE}/{name}", f"{SPECS_DIR}/{name.removesuffix('.md')}/plan.md"]
    try:
        before = next((t for t in (_at_ref(root, ref, h) for h in homes) if t is not None), None)
    except _Unreadable:
        return True
    return before is None or (plan_tier(_quoted_blank(before)) or 0) < 2


def _spec_plan_findings(root: Path, ref: str, plans: list[Path]) -> list[str]:
    """Spec Kit plans (`specs/<name>/plan.md`) answer for their Transitions section only,
    its test cells from the first push like a plan folder's (#327) — the plan folder's
    other rules stay with the plan folder. Bound by the plan folder's rule (`_bound`):
    Tier 2+ and absent at the integration ref or below Tier 2 there (unreadable there:
    bound)."""
    out: list[str] = []
    for p in plans:
        rel = p.relative_to(root).as_posix()
        try:
            text = _quoted_blank(p.read_text(encoding="utf-8", errors="replace"))
        except OSError as exc:
            out.append(f"{rel}: could not read: {exc}")
            continue
        if (plan_tier(text) or 0) < 2 or not _bound(root, ref, rel):
            continue  # stood at the ref at Tier 2+: history, not a new duty
        out += transitions_findings(rel, text, need_tests=True)
    return out


def _registry_ids(root: Path, pattern: str, glob: str) -> set[str]:
    rx = re.compile(pattern)
    ids: set[str] = set()
    head = glob.split("*", 1)[0]  # the folder the pattern starts in: `a/b.json` walks `a`
    for dirpath, _dirs, files in os.walk(root / head.rsplit("/", 1)[0] if "/" in head else root):
        for name in files:
            rel = os.path.relpath(os.path.join(dirpath, name), root).replace(os.sep, "/")
            if fnmatch.fnmatch(rel, glob):
                try:
                    ids |= set(rx.findall(Path(dirpath, name).read_text(encoding="utf-8", errors="replace")))
                except OSError:
                    continue
    return ids


def check(root: Path, env: dict[str, str] | None = None) -> tuple[list[str], list[str]]:
    hard: list[str] = []
    soft: list[str] = []
    pdir = root / PLANS_ACTIVE
    sdir = root / SPECS_DIR
    spec_plans = sorted(sdir.glob(f"*/{SPEC_PLAN}")) if sdir.is_dir() else []
    if not pdir.is_dir() and not spec_plans:
        return hard, soft
    try:
        ref = integration_ref(root)
    except GitReadError as exc:
        return [f"cannot read the integration ref: {exc}"], soft
    if ref is None:
        # on the integration branch itself, or no integration ref at all: there is no
        # branch range, so no plan is new here — old plans are history, not a new duty
        return hard, ["no branch range against an integration ref — no plan is checked"]
    data, problem = load_data(root, ref)
    if problem:
        return [problem], soft
    merge, _why = integration_push(env if env is not None else dict(os.environ), root)
    shall_words = ["shall", *data.get("shall_words", [])]  # a project's words add to `shall`
    sections = data.get("sections", [])
    registry: set[str] | None = None
    hard += _spec_plan_findings(root, ref, spec_plans)
    # an archived plan the branch adds is its plan too: /finish archives before the merge push
    archive = pdir / "archive"
    plans = [*sorted(pdir.glob("*.md")), *(sorted(archive.glob("*.md")) if archive.is_dir() else [])] \
        if pdir.is_dir() else []
    for p in plans:
        rel = p.relative_to(root).as_posix()
        if p.name.startswith("design-"):
            continue
        try:
            text = _quoted_blank(p.read_text(encoding="utf-8", errors="replace"))
        except OSError as exc:
            hard.append(f"{rel}: could not read: {exc}")
            continue
        tier = plan_tier(text)
        if tier is None or tier < 2 or not _bound(root, ref, rel):
            continue  # untiered plans are the review gate's finding; old plans are history
        # #327: owed from the first push, not from the first tick or the merge — a branch
        # whose plan owed them only at the merge passed branch push and review and failed at main
        need_tests = True
        hard += criteria_findings(rel, text, shall_words, need_tests=need_tests)
        hard += transitions_findings(rel, text, need_tests=need_tests)
        for name in sections:
            if not re.search(r"^#{2,3}[ \t]+" + re.escape(name) + r"\b", text, re.MULTILINE | re.IGNORECASE):
                hard.append(f"{rel}: no `## {name}` section — {DATA} requires it in every Tier 2+ plan")
        if data.get("story_id") and data.get("registry"):
            if registry is None:
                registry = _registry_ids(root, data["story_id"], data["registry"])
            for sid in sorted(set(re.findall(data["story_id"], text)) - registry):
                hard.append(f"{rel}: story {sid} is not in the registry ({data['registry']})")
        if merge:
            for m in OPEN_TASK.finditer(text):
                if not _SETTLED.search(m.group("task")):
                    line = text.count("\n", 0, m.start()) + 1
                    hard.append(f"{rel}:{line}: open task at the merge — finish it, or mark it "
                                f"`struck: <reason>` or `moved: #<issue>`")
        for line, row in enumerate(text.splitlines(), 1):
            if DECISION_LINE.match(row) and _ASSUMPTION.search(row):
                soft.append(f"{rel}:{line}: a DECISION still rests on an `[assumption]` — verify it or say so")
    return hard, soft


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    hard, soft = check(root)
    for note in soft:
        print(f"plan-structure: note: {note}")
    if hard:
        print("plan-structure: FAILED:")
        for h in hard:
            print(f"  - {h}")
        return 1
    print("plan-structure: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
