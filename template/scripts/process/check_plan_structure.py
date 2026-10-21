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
  - a criterion without its planned test once execution started (a ticked
    task) or at the merge push: `AC-<id>: <path>::<test>` or `AC-<id>: struck —
    <reason>` — the report line's own grammar (attest knows no other proof),
    so plan and report cannot drift apart;
  - a section the project requires (`sections`) missing;
  - a story id the plan names that the registry does not hold (`story_id`
    and `registry`, both set);
  - at the merge push, an open `- [ ]` task without `struck: <reason>` or
    `moved: #<issue>`;
  - a `## Transitions` section (`check_review.TRANSITIONS_HEADING`, any depth)
    without a pipe table below it, before the next heading of the same or a
    higher level; a table without a `Test` column and two others; a row with
    an empty cell; once execution started or at the merge push, a test cell
    that is neither `<path>::<test>` nor `struck — <reason>` (#293). Rows of
    one equivalence class may name the same test.
  NOTE: an `[assumption]` left in a DECISION line.

Bound are only plans the branch ADDS — absent at the integration ref, or below
Tier 2 there (a stub raised here) — so a plan merged before this gate is
history, not a new duty. A Spec Kit plan (`specs/<name>/plan.md`) is bound when
it is absent at the integration ref and Tier 2+; it answers for its Transitions
table only, its ticks stand in `tasks.md` beside it. Project data,
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

sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling import
from attest_evidence import AC_LINE, STRUCK_LINE, _NAMES_A_TEST, _STRUCK_MARK, ac_key  # noqa: E402
from check_review import (  # noqa: E402  (one owner for plan grammar and fences)
    DECISION_LINE,
    OPEN_TASK,
    SPEC_PLAN,
    SPECS_DIR,
    TRANSITIONS_HEADING,
    GitReadError,
    fenced_lines,
    integration_push,
    integration_ref,
    plan_tier,
)
from process_git import git_environment  # noqa: E402  (one owner for how git is read)

PLANS_ACTIVE = ".process-work/plans"
DATA = "docs/process/plan-structure.local.json"
_TICKED = re.compile(r"^[ \t]*[-*+][ \t]+\[[xX]\][ \t]", re.MULTILINE)
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


_HEADING = re.compile(r"^(#{1,6})(?:[ \t]|$)")
_TABLE_ROW = re.compile(r"^[ \t]{0,3}\|")
_DELIMITER_CELL = re.compile(r"^:?-+:?$")
_PIPE = re.compile(r"(?<!\\)\|")
_UNFILLED = {"", "…", "..."}
# a row's test cell struck on purpose: the criterion strike's own mark and reason rule
_STRUCK_CELL = re.compile(r"^" + _STRUCK_MARK + r"[ \t]*(?!<|(?i:todo)\b|…|\.\.\.)\S*\w")


def _cells(row: str) -> list[str]:
    """The cells of a pipe-table row: outer pipes dropped, an escaped `\\|` kept."""
    body = row.strip()
    body = body[1:] if body.startswith("|") else body
    body = body[:-1] if body.endswith("|") and not body.endswith("\\|") else body
    return [c.strip() for c in _PIPE.split(body)]


def _bare(cell: str) -> str:
    return cell.strip().strip("`*_").strip()


def _sections(lines: list[str]) -> list[tuple[int, str, list[tuple[int, str]]]]:
    """(line, heading, body lines) of every Transitions section: from its heading to the
    next heading of the same or a higher level."""
    out: list[tuple[int, str, list[tuple[int, str]]]] = []
    for i, line in enumerate(lines):
        if not TRANSITIONS_HEADING.match(line):
            continue
        level = len(line) - len(line.lstrip("#"))
        body: list[tuple[int, str]] = []
        for j in range(i + 1, len(lines)):
            h = _HEADING.match(lines[j])
            if h and len(h.group(1)) <= level:
                break
            body.append((j + 1, lines[j]))
        out.append((i + 1, line.strip(), body))
    return out


def _tables(body: list[tuple[int, str]]) -> list[list[tuple[int, str]]]:
    """The pipe tables of a section: a run of `|` rows whose second row is a delimiter."""
    runs: list[list[tuple[int, str]]] = []
    for n, line in body:
        if _TABLE_ROW.match(line):
            if runs and runs[-1][-1][0] == n - 1:
                runs[-1].append((n, line))
            else:
                runs.append([(n, line)])
    return [r for r in runs if len(r) >= 2 and all(_DELIMITER_CELL.match(c) for c in _cells(r[1][1]))]


def transitions_findings(rel: str, text: str, *, need_tests: bool) -> list[str]:
    """The findings on a plan's Transitions sections (unfenced text, the file's own line
    numbers): a pipe table below each, with a `Test` column and two others, every cell of
    every row filled; once tests are due, each test cell `<path>::<test>` or `struck —
    <reason>`. Every table of the section is read: a second one is no way around the first."""
    out: list[str] = []
    for line, heading, body in _sections(text.splitlines()):
        tables = _tables(body)
        if not tables:
            out.append(f"{rel}:{line}: `{heading}` has no table below it — state × event → result with a "
                       f"`Test` column (docs/process/design-template.md, Transitions)")
            continue
        for table in tables:
            (hline, hrow), *_delim = table[:2]
            header = [_bare(c) for c in _cells(hrow)]
            tests = [k for k, name in enumerate(header) if name.lower() == "test"]
            if not tests:
                out.append(f"{rel}:{hline}: the transitions table has no `Test` column — one test per row; "
                           f"rows of one equivalence class may name the same test")
                continue
            if len(header) < 3:
                out.append(f"{rel}:{hline}: the transitions table needs a `Test` column and at least two "
                           f"others (state × event → result)")
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
                if need_tests and not (_is_proof(cell) or _STRUCK_CELL.match(_bare(cell))):
                    out.append(f"{rel}:{n}: transitions row names no test — `<path>::<test>` (it may not "
                               f"exist yet) or `struck — <reason>`")
    return out


def _bound(root: Path, ref: str, rel: str) -> bool:
    """Is this plan the branch's to answer for? Added on the branch, or below Tier 2 at
    the integration ref (a stub raised to Tier 2 here is written here). An archived plan
    is judged where it lived before `/finish` moved it, too: an old plan archived here is
    history. Unreadable at the ref: bound (fail closed)."""
    homes = [rel]
    if rel.startswith(f"{PLANS_ACTIVE}/archive/"):
        homes.append(f"{PLANS_ACTIVE}/{rel.rsplit('/', 1)[1]}")
    try:
        before = next((t for t in (_at_ref(root, ref, h) for h in homes) if t is not None), None)
    except _Unreadable:
        return True
    return before is None or (plan_tier(_quoted_blank(before)) or 0) < 2


def _spec_plan_findings(root: Path, ref: str, plans: list[Path], *, merge: bool) -> list[str]:
    """Spec Kit plans (`specs/<name>/plan.md`) answer for their Transitions table only —
    the plan folder's other rules stay with the plan folder. Bound when absent at the
    integration ref and Tier 2+ (unreadable there: bound); their ticks stand in
    `tasks.md` beside them."""
    out: list[str] = []
    for p in plans:
        rel = p.relative_to(root).as_posix()
        try:
            text = _quoted_blank(p.read_text(encoding="utf-8", errors="replace"))
        except OSError as exc:
            out.append(f"{rel}: could not read: {exc}")
            continue
        if (plan_tier(text) or 0) < 2:
            continue
        try:
            if _at_ref(root, ref, rel) is not None:
                continue  # stood at the ref: history, not a new duty
        except _Unreadable:
            pass
        tasks = p.parent / "tasks.md"
        try:
            ticked = bool(_TICKED.search(text)) or (
                tasks.is_file() and bool(_TICKED.search(_quoted_blank(tasks.read_text(encoding="utf-8",
                                                                                      errors="replace")))))
        except OSError as exc:
            out.append(f"{tasks.relative_to(root).as_posix()}: could not read: {exc}")
            continue
        out += transitions_findings(rel, text, need_tests=merge or ticked)
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
    hard += _spec_plan_findings(root, ref, spec_plans, merge=merge)
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
        need_tests = merge or bool(_TICKED.search(text))
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
