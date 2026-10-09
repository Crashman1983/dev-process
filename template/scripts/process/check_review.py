#!/usr/bin/env python3
"""review gate (core, always-on): make the review-independence attestation a
gated artifact instead of prose.

Review-before-merge is mandatory rule 7 — core, not an optional module — so this
gate always runs. It reads `REVIEW` attestation lines from the journal and
enforces what a language-agnostic CI gate honestly can:

  - HARD: a malformed `REVIEW ` line (grammar, enums, numeric fields) — a
    malformed attestation is silent loss.
  - HARD (independence arithmetic on a `verdict=pass`): a self-review
    (`non-implementing` absent) or a warm review (`bundle` absent) cannot clear
    Tier 2+; a Tier 3 pass must carry `cross-model` or the explicit
    `single-family` honesty flag.
  - HARD (presence, post-merge, opt-in by tier declaration): an archived plan
    declaring `tier: N` with N >= 2 that carries neither a clearing
    `verdict=pass` REVIEW nor an explicit `review-waived:` line.
  - HARD on the merge push only (presence, push-anchored): an ACTIVE plan
    declaring `tier: 3` that this push carries (its file is in the pushed
    range, or a pushed commit claims its issue via a closing trailer or a
    `(#N)` subject) without a clearing pass or waiver. Waiting for the
    archive step means the proof arrives after the merge it was meant to
    gate. "Merge push" is read from the environment (`PROCESS_PUSH_TARGETS`,
    or the pre-commit framework's `PRE_COMMIT_REMOTE_BRANCH`): hard when a
    target ref is main/master, the same findings as notes anywhere else —
    a gate that reds the wrong push gets bypassed, and a bypassed gate
    proves nothing.
  - HARD on the merge push only (standing block, any tier): the latest
    REVIEW of a work this push carries (highest round; an equal round goes
    to the block) is `verdict=block` — read from the commits of the pushed
    range, never the worktree. `--standing-block <sha>[:<remote_sha>]` runs
    this arm alone for a pre-push hook.
  - The reviewed range: a REVIEW names `base` and `head` (the bundle prints
    them in its `REVIEW_ARTIFACT` line, `attest.py` writes them). A full
    round's `base` is the fork point of its `head`; code after the reviewed
    head is unreviewed. Two SHAs name the reviewed change exactly — the
    diff digest older records carry (`diff=`) is read and ignored (template
    v2.53: it was a function of base and head, and its verification
    machinery was a source of defects of its own).

Lean pass: the former artifact-v1 mode (tree-empty certificate commits,
candidate-target binding, two attestation modes) is retired. A plan's
`review-binding:` line is reported as retired, never silently ignored.

It does NOT verify that the reviewer was truthfully a different agent or model —
the gate never sees the review runtime. That claim stays *attested*; the gate
only makes a weak, absent, or over-claiming attestation *block the merge* rather
than be weighed by a human. Presence is checked against archived plans (a plan is
archived on merge), so the gate never reds CI mid-development and offers a
named-exception escape (`review-waived:`) so it enforces without a footgun.

Pure stdlib. Owns the `REVIEW` grammar.
"""
from __future__ import annotations

import functools
import os
import re
import subprocess
import sys
import time
from collections import Counter
from typing import NamedTuple
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from process_git import NoForkPoint, fork_point, git_environment  # noqa: E402
from template_verify import verify  # noqa: E402

JOURNAL_DIR = ".process-work/journal"
PLANS_ACTIVE = ".process-work/plans"
PLANS_ARCHIVE = ".process-work/plans/archive"
SPECS_DIR = "specs"
SPEC_PLAN = "plan.md"

# --- where the process records live: ONE owner ------------------------------
# REVIEW, ROOT-CAUSE and REFUTE lines are written into journal shards, into
# plans and into Spec Kit plans (`specs/<dir>/plan.md`, which never archive).
# Every tool that reads those records — this gate, attest.py (rounds, root
# causes), make_review_bundle.py (the REFUTE check and its delta pre-state) —
# asks here, so no tool can forget a home (observed downstream: the delta
# pre-state read only the plan folder, and an old REFUTE line in a Spec Kit
# plan passed as new).
RECORD_KINDS = ("journal", "plan", "plan-archive", "spec-plan")
PLAN_KINDS = ("plan", "spec-plan")  # plans under work: not archived


def record_kind(rel: str) -> str | None:
    """The record kind of a repo-relative posix path, None for any other file:
    `journal` (any shard under the journal), `plan` (an active plan, directly
    in the plan folder), `plan-archive` (a plan in a subfolder of it — the
    archive), `spec-plan` (`specs/<dir>/plan.md`)."""
    if not rel.endswith(".md"):
        return None
    if rel.startswith(JOURNAL_DIR + "/"):
        return "journal"
    if rel.startswith(PLANS_ACTIVE + "/"):
        return "plan" if "/" not in rel[len(PLANS_ACTIVE) + 1:] else "plan-archive"
    parts = rel.split("/")
    if len(parts) == 3 and parts[0] == SPECS_DIR and parts[2] == SPEC_PLAN:
        return "spec-plan"
    return None


# a branch named after its issue: `7`, `7-login`, `issue-7`, `feat/7-login` (the last
# segment decides) — never a date (`2026-09-30-login` is no issue 2026)
_BRANCH_ISSUE = re.compile(r"^(?:issue-)?([0-9]+)(?:-|$)")
_DATED_BRANCH = re.compile(r"^\d{4}-\d{2}-\d{2}(?:-|$)")


def branch_issue(branch: str) -> str | None:
    """The issue number a branch name leads with, or None — the one owner; the train,
    attest's journal shard and the merge guard ask it (refutation: two rules read
    `feat/7-login` and `7/x` differently)."""
    leaf = branch.rsplit("/", 1)[-1]
    if _DATED_BRANCH.match(leaf):
        return None
    m = _BRANCH_ISSUE.match(leaf)
    return m.group(1) if m else None


def plan_stem(rel: str) -> str:
    """A plan's name for work ids: the file stem, or the spec directory's name
    for a Spec Kit plan (every one of them is called plan.md)."""
    parts = rel.split("/")
    if record_kind(rel) == "spec-plan":
        return parts[1]
    return parts[-1][:-3] if parts[-1].endswith(".md") else parts[-1]


def record_files(root: Path, kinds: tuple[str, ...] = RECORD_KINDS, *,
                 journal_dir: Path | None = None) -> list[tuple[str, Path]]:
    """(repo-relative path, file) of every record file of `kinds` in the
    worktree, sorted per home. `journal_dir` overrides the journal's place
    (attest --journal-dir); its files keep their path relative to the root
    where they sit under it, else their absolute path."""
    out: list[tuple[str, Path]] = []

    def rel_of(f: Path) -> str:
        try:
            return f.relative_to(root).as_posix()
        except ValueError:
            return f.as_posix()

    if "journal" in kinds:
        jdir = journal_dir if journal_dir is not None else root / JOURNAL_DIR
        if jdir.is_dir():
            out += [(rel_of(f), f) for f in sorted(jdir.glob("**/*.md"))]
    pdir = root / PLANS_ACTIVE
    if pdir.is_dir() and ("plan" in kinds or "plan-archive" in kinds):
        for f in sorted(pdir.glob("**/*.md")):
            rel = f"{PLANS_ACTIVE}/{f.relative_to(pdir).as_posix()}"
            if record_kind(rel) in kinds:
                out.append((rel, f))
    sdir = root / SPECS_DIR
    if "spec-plan" in kinds and sdir.is_dir():
        out += [(f"{SPECS_DIR}/{f.parent.name}/{SPEC_PLAN}", f)
                for f in sorted(sdir.glob(f"*/{SPEC_PLAN}")) if f.is_file()]
    return out


def record_texts(root: Path, kinds: tuple[str, ...] = RECORD_KINDS, *,
                 ref: str | None = None,
                 journal_dir: Path | None = None) -> list[tuple[str, str]] | None:
    """(repo-relative path, text) of every record file of `kinds` — in the
    worktree, or at the git `ref`. None when git cannot tell (a missing ref,
    an unreadable blob): the caller must not read "no records" into that.
    Unreadable worktree files are skipped (the gate diagnoses them)."""
    if ref is None:
        out: list[tuple[str, str]] = []
        for rel, f in record_files(root, kinds, journal_dir=journal_dir):
            try:
                out.append((rel, f.read_text(encoding="utf-8", errors="replace")))
            except OSError:
                continue
        return out
    names = _git_bytes(root, "ls-tree", "-r", "-z", "--name-only", ref, "--",
                       JOURNAL_DIR, PLANS_ACTIVE, SPECS_DIR)
    if names is None:
        return None
    out = []
    for raw in names.split(b"\0"):
        rel = raw.decode("utf-8", errors="surrogateescape")
        if not raw or record_kind(rel) not in kinds:
            continue
        blob = _git_bytes(root, "cat-file", "blob", f"{ref}:{rel}")
        if blob is None:
            return None
        out.append((rel, blob.decode("utf-8", errors="replace")))
    return out

REQUIRED = {"work", "tier", "reviewer", "model", "independence", "verdict", "round"}
# the reviewed range — both or none (a partial claim is malformed)
ARTIFACT_FIELDS = {"base", "head"}
# legacy fields older records carry next to base/head: read, never required,
# never written (v2.52: a diff digest is a function of base and head — the
# SHAs already name the reviewed change; `mode=delta` marked a delta bundle)
LEGACY_FIELDS = {"diff", "mode"}
INDEP_TOKENS = {"bundle", "non-implementing", "cross-model", "single-family"}
VERDICTS = {"pass", "block"}
# tolerant of a leading list bullet and **bold**/_emphasis_ on the key, and of
# a trailing annotation — a bulleted `- tier: 3` must not escape the presence
# check (a false-green). This gate OWNS the plan-field grammar; the issue gate
# imports these matchers instead of keeping a copy in sync.
_LEAD = r"^\s*(?:[-*+]\s+)?[*_]*"
TIER_DECL = re.compile(_LEAD + r"tier[*_]*\s*:\s*[*_]*\s*(\d+)\b", re.IGNORECASE | re.MULTILINE)
ISSUE_DECL = re.compile(_LEAD + r"issue[*_]*\s*:\s*(\S+)", re.IGNORECASE | re.MULTILINE)
WAIVED = re.compile(_LEAD + r"review-waived[*_]*\s*:\s*\S", re.IGNORECASE | re.MULTILINE)
RETIRED_BINDING = re.compile(_LEAD + r"review-binding[*_]*\s*:", re.IGNORECASE | re.MULTILINE)
DATE_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2}-")
# a waiver is an honest degradation — but a degradation without an owner
# becomes the new normal. The debt marker is an issue ref (#N) or a URL on
# the waiver line itself. Soft everywhere: the waiver stays valid, the
# missing owner is named. One owner for the notion; the speckit and issues
# gates import this instead of keeping copies.
_WAIVER_DEBT = re.compile(r"#\d+|https?://")


def waiver_debt_notes(rel: str, text: str, pattern: re.Pattern[str],
                      label: str) -> list[str]:
    """One note per waiver line that names no issue/URL owner. A plan that
    declares its tracking issue (`issue: #N`) already has an owner — the
    waiver is recorded where the work is tracked — so only waivers in
    plans without ANY issue anchor are flagged."""
    if any(parse_issue_ref(m.group(1)) or m.group(1).isdigit()
           for m in ISSUE_DECL.finditer(text)):
        return []
    notes = []
    for line in text.splitlines():
        if pattern.search(line) and not _WAIVER_DEBT.search(line):
            notes.append(f"{rel}: '{label}:' without an issue ref — a "
                         f"degradation is a debt with an owner; link #N (or a "
                         f"URL) on the waiver line, or declare the plan's "
                         f"'issue:' link")
    return notes
GIT_SHA = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")

# issue-ref grammar — owned here (core) so both this gate and the issue gate
# read the same shapes; only these count as issue declarations
_BARE = re.compile(r"^#(\d+)$")
_CROSS = re.compile(r"^([\w.-]+/[\w.-]+)#(\d+)$")
_URL = re.compile(r"^https://github\.com/([\w.-]+/[\w.-]+)/issues/(\d+)$")


def parse_issue_ref(ref: str) -> tuple[str | None, int] | None:
    """(repo_or_None, number) for a well-formed ref, else None. repo is None
    only for the bare `#N` form, which resolves against the configured repo."""
    for pat, has_repo in ((_BARE, False), (_CROSS, True), (_URL, True)):
        m = pat.match(ref)
        if m:
            return (m.group(1), int(m.group(2))) if has_repo else (None, int(m.group(1)))
    return None


# a REVIEW record may be written as a Markdown bullet — `- REVIEW ...` must
# not silently vanish (audit: the natural journal form was invisible to both
# the parse and the malformed check)
_REVIEW_LINE = re.compile(r"^\s*(?:[-*+]\s+)?[*_]*REVIEW(\s+.*|)$")


_FENCE_RUN = re.compile(r"^(`{3,}|~{3,})")


def _fence_marker(line: str) -> str | None:
    """The fence run (``` or ~~~, any length >= 3) opening this line, if any."""
    m = _FENCE_RUN.match(line.strip())
    return m.group(1) if m else None


def _fence_closes(fence: str, marker: str) -> bool:
    """CommonMark: a fence closes only on a run of the SAME character at least
    as long as the opener — a ``` inside a ````-fenced example must not close
    it early, or quoted `review-waived:`/`tier:` lines leak out (false-green)."""
    return marker[0] == fence[0] and len(marker) >= len(fence)


def _unfenced(text: str) -> str:
    """Text with fenced blocks (``` and ~~~, each closed by its own,
    length-aware marker) removed. A `tier:`/`issue:`/`review-waived:` line
    inside a fenced example is a quotation, not a declaration — the same
    discipline the journal parser applies to REVIEW lines."""
    out: list[str] = []
    fence: str | None = None
    for line in text.splitlines():
        marker = _fence_marker(line)
        if marker and fence is None:
            fence = marker
            continue
        if marker and fence is not None and _fence_closes(fence, marker):
            fence = None
            continue
        if fence is None:
            out.append(line)
    return "\n".join(out)


# A worker's open question to the owner: `DECISION NEEDED <date> <who>: …`
# (bold markers and a missing `who` are still a question). Answered is the line
# rewritten to `DECISION`, struck through, or marked `(answered …)` anywhere
# before its colon — downstream, workers marked answered questions in place,
# and a marker after the date read as still open: three finished branches
# would have dropped out of the train over its position.
DECISION_NEEDED = re.compile(
    r"^\s*(?:[-*+]\s+)?[*_]*DECISION NEEDED[*_]*\s+(\d{4}-\d{2}-\d{2})(?:\s+([^:\n]+?))?\s*:\s*(.+?)\s*$",
    re.MULTILINE)
# the marker is a status, not a phrase: `(decided by owner)` still asks (refutation)
ANSWERED_MARK = re.compile(
    r"\((?:answered|resolved|decided|beantwortet|entschieden|erledigt)"
    r"(?=\s*[),;]|\s+(?:below|above|unten|oben|see|siehe|s\.\s*u\.|→|->|\d{4}-\d{2}-\d{2}))",
    re.IGNORECASE)


# The record lines a plan carries — one owner, read through `readable`:
# at most three spaces of indent (four is a code block), any list marker, a
# work id that is not the brief's placeholder, a round and what was found. A
# bare `REFUTE work=x` or a line in backticks is a mention, not a record
# (downstream review: both switched the refute warning off); the brief's
# `<cause>` placeholder, a TODO or an ellipsis is a template, not a cause
# (downstream refute: a fenced, a commented and a placeholder line each
# passed). make_review_bundle reads REFUTE lines and attest ROOT-CAUSE lines
# through these.
_RECORD_LEAD = r"^ {0,3}(?:(?:[-*+]|\d+[.)])[ \t]+(?:\[[xX]\][ \t]+)?)?"
REFUTE_LINE = re.compile(
    _RECORD_LEAD + r"REFUTE[ \t]+work=(?P<work>(?!<)(?!TODO\b)[\w#./-]+)"
    r"[ \t]+round=(?P<round>\d+):[ \t]*(?P<text>(?!<|TODO\b|…|\.\.\.)\S.*)$",
    re.MULTILINE)
ROOT_CAUSE_LINE = re.compile(
    _RECORD_LEAD + r"ROOT-CAUSE[ \t]+"
    r"work=(?P<work>(?!<)(?!TODO\b)\S+)[ \t]+round=(?P<round>\d+):[ \t]*(?!<|TODO\b|…|\.\.\.)\S",
    re.MULTILINE)
# a dated answer to the owner's question (an open `DECISION NEEDED` is none)
DECISION_LINE = re.compile(_RECORD_LEAD + r"[*_]*DECISION[*_]*[ \t]+\d{4}-\d{2}-\d{2}\b\S*[ \t]*\S")


def _record_line(line: str) -> bool:
    """Is this one line a record — REFUTE, ROOT-CAUSE, a well-formed REVIEW
    line or a dated DECISION — at most three spaces in (more, or a tab, is a
    code block, refute #199)?"""
    if REFUTE_LINE.match(line) or ROOT_CAUSE_LINE.match(line) or DECISION_LINE.match(line):
        return True
    if not re.match(r" {0,3}\S", line):
        return False
    records, errors = parse_review_lines(line)
    return bool(records) and not errors


_ATX_HEADING = re.compile(r" {0,3}#{1,6}(?:[ \t]|$)")
_LIST_MARKER = re.compile(r"( {0,3})(?:[-*+]|\d{1,9}[.)])[ \t]")


def _list_item(line: str) -> str | None:
    """The indent of a list item line, None for any other line."""
    m = _LIST_MARKER.match(line)
    return m.group(1) if m else None


# what `splitlines` reads as a line end and Markdown does not (refute #199:
# U+0085 kept a closed fence open in the render)
_ODD_LINE_ENDS = re.compile("[\x0b\x0c\x1c\x1d\x1e\x85\u2028\u2029]")


def records_only(before: str, after: str) -> bool:
    """Is `after` the plan `before` plus records — REFUTE, ROOT-CAUSE, REVIEW
    and DECISION lines added, an open `DECISION NEEDED` replaced by a
    DECISION line — with every other line kept as it was? Such lines ride
    the attestation commit after the reviewed head (`attest --with`,
    `--archive`); a Spec Kit plan is no bookkeeping, and they made its own
    pass stale (#199). Prose, an edited or a deleted line is plan content:
    not records only. So is a record line a reader does not see as one
    (`readable`: inside a fence, an HTML comment, indented as code), and an
    addition that joins or splits the paragraphs around it (refute #199: a
    setext underline, a lazy continuation, a blank line that turned prose
    into an invisible link definition): records go between blank lines,
    next to other records, an open question or a heading, as a sibling list
    item, or at the end of a list. The rendered plan, records aside, must
    read exactly as before. Known limits: a record line's own inline markup
    (a backtick closing a code span its record paragraph opened) is not
    rendered here, and neither is list containment — a record list item
    can turn an indented code block below it into list content (refute:
    an indented `<!--` then hid a reviewed line)."""
    import difflib
    if _ODD_LINE_ENDS.findall(before) != _ODD_LINE_ENDS.findall(after):
        return False
    a, b = before.splitlines(), after.splitlines()

    def blank(line: str | None) -> bool:
        return line is None or not line.strip(" \t")  # U+00A0 is text to a renderer

    def edge(line: str | None) -> bool:
        # what a record may stand next to without regrouping it: a blank line,
        # another record, the open question it answers, an ATX heading
        return (blank(line) or _record_line(line) or bool(DECISION_NEEDED.match(line))
                or bool(_ATX_HEADING.match(line)))

    def sibling(line: str | None, record: str) -> bool:
        # a record list item next to an item of the same list level
        return line is not None and _list_item(line) is not None and _list_item(line) == _list_item(record)

    added: list[str] = []
    answered: list[str] = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        for line in a[i1:i2]:
            if not DECISION_NEEDED.match(line):
                return False
            answered.append(line)
        block = b[j1:j2]
        records = [line for line in block if not blank(line)]
        if not records or not all(_record_line(line) for line in records):
            return False  # prose, or blank lines alone (they regroup paragraphs)
        prev = b[j1 - 1] if j1 > 0 else None
        nxt = b[j2] if j2 < len(b) else None
        left = (edge(prev) or (blank(block[0]) and blank(nxt)) or sibling(prev, block[0])
                # the end of a list: the record continues its last item, visibly
                or (_list_item(prev) is not None and not any(blank(x) for x in block) and blank(nxt)))
        right = edge(nxt) or (blank(block[-1]) and blank(prev)) or sibling(nxt, block[-1])
        if not (left and right):
            return False  # it would join or split the paragraph next to it
        added += records
    if len(answered) > sum(1 for line in added if DECISION_LINE.match(line)):
        return False  # a question dropped, not answered

    def content(text: str, drop: list[str]) -> tuple[list[str], Counter]:
        lines = [line for line in readable(text).splitlines() if not blank(line)]
        records = Counter(line for line in lines if _record_line(line))
        rest = Counter(lines) - records - Counter(drop)
        return sorted(rest.elements()), records
    rest_before, records_before = content(before, answered)
    rest_after, records_after = content(after, [])
    # every added record visible as written, nothing else read differently
    return rest_before == rest_after and records_after - records_before == Counter(added)


def open_questions(text: str) -> list[re.Match]:
    """The still-open `DECISION NEEDED` lines of a plan, fenced examples left out."""
    return [m for m in DECISION_NEEDED.finditer(_unfenced(text))
            if not ANSWERED_MARK.search(m.group(2) or "")
            and not ANSWERED_MARK.match(m.group(3))]


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
# markers, and setext/table edge cases are not modelled.
_BLOCK_COMMENT = re.compile(r"^ {0,3}<!--")
_ASCII_PUNCT = set("!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~")



# a design doc next to the plans (`design-<x>.md`) is not a plan: no tier, no review
DESIGN_DOC_PREFIX = "design-"


def plan_tier(text: str) -> int | None:
    """The tier a plan declares, as the tier-keyed gates read it: the first
    `tier:` line a reader sees — not one in a fenced block (an example), not
    a second one further down (a note on a tier considered)."""
    m = TIER_DECL.search(_unfenced(text or ""))
    return int(m.group(1)) if m else None


def review_waived(text: str) -> bool:
    """Does the plan waive its review (`review-waived: <reason>`) — read as
    the presence gate reads it."""
    return WAIVED.search(_unfenced(text or "")) is not None

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


def _inline_uncommented(para: str) -> str:
    out: list[str] = []
    start = i = 0
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
            out.append(para[start:i])
            start = i = k + 3
            continue
        i += 1
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


def readable(text: str) -> str:
    """What a reader of the rendered Markdown sees of a record file: fenced
    blocks and HTML comments removed — REFUTE and ROOT-CAUSE lines (and a
    tool's view of REVIEW lines in plans) are read through this."""
    return uncommented(_unfenced(text))


def parse_review_lines(text: str) -> tuple[list[tuple[int, dict]], list[tuple[int, str]]]:
    """Return (records, errors). A record is (lineno, field-dict) for a
    well-formed REVIEW line (optionally bulleted); an error is (lineno,
    message) for a malformed one. Lines inside fenced blocks (``` or ~~~) are
    quotations and are ignored."""
    records: list[tuple[int, dict]] = []
    errors: list[tuple[int, str]] = []
    fence: str | None = None
    for i, raw in enumerate(text.splitlines(), start=1):
        marker = _fence_marker(raw)
        if marker and fence is None:
            fence = marker
            continue
        if marker and fence is not None and _fence_closes(fence, marker):
            fence = None
            continue
        if fence is not None:
            continue
        rm = _REVIEW_LINE.match(raw)
        if not rm:
            continue
        toks = rm.group(1).split()
        fields: dict[str, str] = {}
        malformed = None
        for t in toks:
            if "=" not in t:
                malformed = f"token {t!r} is not key=value"
                break
            k, v = t.split("=", 1)
            if not v:
                malformed = f"empty value for {k!r}"
                break
            if k in fields:
                malformed = f"duplicate key {k!r}"
                break
            fields[k] = v
        if malformed:
            errors.append((i, malformed))
            continue
        shape = set(fields)
        artifact = shape & ARTIFACT_FIELDS
        expected = REQUIRED | (ARTIFACT_FIELDS if artifact else set())
        if artifact:
            expected |= shape & LEGACY_FIELDS
        if "mode" in shape and fields["mode"] not in ("full", "delta"):
            errors.append((i, "mode must be full or delta"))
            continue
        if shape != expected:
            missing = expected - shape
            extra = shape - expected
            bits = []
            if missing:
                bits.append("missing " + ",".join(sorted(missing)))
            if extra:
                bits.append("unexpected " + ",".join(sorted(extra)))
            errors.append((i, "; ".join(bits)))
            continue
        if artifact:
            bad = None
            for key in ("base", "head"):
                if not GIT_SHA.fullmatch(fields[key]):
                    errors.append((i, f"{key} must be a 40- or 64-character lowercase Git SHA"))
                    bad = key
                    break
            if bad:
                continue
        # isascii guards unicode digits ("²"): isdigit() is True but int() raises
        if not (fields["tier"].isascii() and fields["tier"].isdigit()) or \
                not (fields["round"].isascii() and fields["round"].isdigit()):
            errors.append((i, "tier and round must be integers"))
            continue
        # audit: an out-of-range tier (e.g. tier=4 on the 0-3 scale) both
        # skipped the cross-model check and still cleared a lower plan via
        # `>= tier` — over-declaring must be malformed, not a bypass
        if not 0 <= int(fields["tier"]) <= 3:
            errors.append((i, f"tier {fields['tier']} outside the 0-3 scale"))
            continue
        if fields["verdict"] not in VERDICTS:
            errors.append((i, f"verdict {fields['verdict']!r} not in {sorted(VERDICTS)}"))
            continue
        indep = set(fields["independence"].split(","))
        if not indep <= INDEP_TOKENS:
            bad_tok = ",".join(sorted(indep - INDEP_TOKENS))
            errors.append((i, f"independence has unknown token(s): {bad_tok}"))
            continue
        records.append((i, fields))
    return records, errors


def _arithmetic_violations(rel: str, records: list[tuple[int, dict]]) -> list[str]:
    """The independence arithmetic: a pass verdict may not claim to clear a tier
    its flags do not support."""
    hard: list[str] = []
    for lineno, f in records:
        if f["verdict"] != "pass":
            continue
        tier = int(f["tier"])
        indep = set(f["independence"].split(","))
        # bundle/non-implementing is the Tier-2 floor: Tier 0-1 is a self-check
        # (Quick flow reviews itself), Tier 2 is the first tier with a fresh
        # read-only-bundle review — verification-independence.md
        if tier >= 2 and "non-implementing" not in indep:
            hard.append(f"{rel}:{lineno}: pass at tier {tier} without 'non-implementing' "
                        f"— the implementer cannot certify its own work at Tier 2+")
        if tier >= 2 and "bundle" not in indep:
            hard.append(f"{rel}:{lineno}: pass at tier {tier} without 'bundle' "
                        f"— Tier 2+ is reviewed from a read-only bundle, not the warm context")
        if tier >= 3 and not (indep & {"cross-model", "single-family"}):
            hard.append(f"{rel}:{lineno}: pass at tier 3 without 'cross-model' or "
                        f"'single-family' — Tier 3 must cross the model family or declare it could not")
    return hard


# gate code as `docs/process/refute.md` defines it, approximated by path: the
# gates, the hooks, and what starts them (make targets, CI, pre-commit) —
# and the local gate configuration: which gates run, which models review
GATE_PATHS = ("scripts/process/", ".githooks/", ".github/workflows/")
GATE_FILES = ("Makefile", ".pre-commit-config.yaml",
              "docs/process/gates.local.json", "docs/process/model-policy.local.json")
REVIEW_REPORTS = ".process-work/reviews"
_REPORT_KEY = re.compile(r"^\s*(?:[-*+]\s+)?[*_]*(review|audit|work)[*_]*\s*:\s*(\S+)", re.IGNORECASE)


def is_gate_path(rel: str) -> bool:
    return rel.startswith(GATE_PATHS) or rel in GATE_FILES


def _show(root: Path, ref: str, rel: str) -> str | None:
    out = _git_bytes(root, "show", f"{ref}:{rel}")
    return None if out is None else out.decode("utf-8", errors="replace")


IssueKey = tuple  # (owner/repo lowercased, or None for this repo's `#N`; number)
_MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")


def issue_key(ref: str) -> IssueKey | None:
    """An issue ref as a comparable key: `#9` and `9` are this repository's
    issue 9; `owner/repo#9` and the issue URL name that repository's."""
    parsed = parse_issue_ref(ref)
    if parsed is not None:
        return (parsed[0].lower() if parsed[0] else None, parsed[1])
    return (None, int(ref)) if ref.isascii() and ref.isdigit() else None


def work_keys(works) -> tuple[tuple[str, ...], tuple[IssueKey, ...]]:
    """(slugs, issues) of REVIEW work ids, for `report_of`."""
    slugs, issues = [], []
    for w in sorted(works):
        k = issue_key(w)
        if k is not None:
            issues.append(k)
        else:
            slugs.append(DATE_PREFIX.sub("", w))
    return tuple(slugs), tuple(issues)


def work_key(work: str):
    """A REVIEW work id as compared across records: an issue ref by its number
    (`#26`, `26`, `owner/repo#26` and the issue URL are one — as `_plan_work_ids`
    lets `work=26` match `issue: owner/repo#26`), any other id as itself."""
    k = issue_key(work)
    return ("#", k[1]) if k is not None else work


@functools.lru_cache(maxsize=64)
def _plans_at_ref(root_s: str, ref: str) -> tuple[tuple[str, str], ...] | None:
    texts = record_texts(Path(root_s), PLAN_KINDS + ("plan-archive",), ref=ref)
    return None if texts is None else tuple(texts)


def expand_work(root: Path, works, ref: str | None = None
                ) -> tuple[set[str], tuple[tuple[str, ...], tuple[IssueKey, ...]]]:
    """(ids, (slugs, issues)) of the work the REVIEW ids `works` name — the one
    owner of "which records are this work's" for a Tier 3 delta: every plan
    (active, archived, Spec Kit; at `ref`, else the worktree) one of whose ids
    (`_plan_work_ids`) is one of `works` lends all its ids and its report keys
    (`plan_report_keys`); `work_keys(works)` always counts. A plan's slug and
    its `issue:` name one work: the bundle, attest and the gate read a round
    attested as `work=widget` and one as `work=26` of the plan `widget` with
    `issue: #26` alike (refutation: they disagreed, so a delta the bundle built
    could not be attested). When git cannot list the plans, `works` alone."""
    works = {w for w in works if w}
    want = {work_key(w) for w in works}
    ids = set(works)
    slugs, issues = (list(k) for k in work_keys(works))
    plans = (record_texts(root, PLAN_KINDS + ("plan-archive",)) if ref is None
             else _plans_at_ref(str(root), ref)) or ()
    for rel, text in plans:
        pids = _plan_work_ids(plan_stem(rel), _unfenced(text), include_dedated=True)
        if want & {work_key(p) for p in pids}:
            ids |= pids
            s, i = plan_report_keys(rel, text)
            slugs += s
            issues += i
    return ids, (tuple(dict.fromkeys(s for s in slugs if s)), tuple(dict.fromkeys(issues)))


def ref_token(value: str) -> str:
    """A header or `issue:` value as the ref it names: `[#9](url)` is `#9`, and
    so are `#9,`, `#9.`, `**#9**` and `<#9>` (refutation) — the one owner;
    report headers and plan keys read through it."""
    value = _MD_LINK.sub(r"\1", value)
    prev = None
    while prev != value:
        prev = value
        value = value.strip().strip("*_<>").rstrip(".,;:")
    return value


def plan_report_keys(rel: str, text: str) -> tuple[tuple[str, ...], tuple[IssueKey, ...]]:
    """(slugs, issues) by which a plan reaches its review reports through
    `report_of`: the plan's stem without its date, and the issues it declares
    — the one owner; the review bundle and tidy ask it."""
    issues = [issue_key(ref_token(m.group(1))) for m in ISSUE_DECL.finditer(_unfenced(text or ""))]
    slug = DATE_PREFIX.sub("", plan_stem(rel))
    return ((slug,) if slug else ()), tuple(dict.fromkeys(k for k in issues if k is not None))


def _slug_in_name(slug: str, stem: str) -> bool:
    """`slug` is the file stem or a whole dash-separated part run of it —
    `api` names `api-round-2`, not `rapid-fix`."""
    return stem == slug or re.search(rf"(?:^|-){re.escape(slug)}(?:-|$)", stem) is not None


def report_header(text: str) -> dict[str, list[str]]:
    """The `review:`/`audit:`/`work:` values of a report's header block — the
    lines from the top to the first blank one (journal-state-plans.md). The
    report names its work there, not necessarily in its file name."""
    out: dict[str, list[str]] = {}
    for line in _unfenced(text).splitlines():
        if not line.strip():
            break
        m = _REPORT_KEY.match(line)
        if m:
            key = "review" if m.group(1).lower() == "audit" else m.group(1).lower()
            value = ref_token(m.group(2))
            out.setdefault(key, []).append(DATE_PREFIX.sub("", value))
    return out


def report_of(candidates: list[tuple[str, str]], slugs, issues) -> tuple[str, str] | None:
    """The previous round's report of THIS work item among (path, text)
    candidates — never another one's; the one owner of that rule.

    A report whose header names its `work:` belongs to that work alone: it is
    this item's when a value is one of this item's issues (the same
    repository: `other/repo#9` is not this repo's #9) or plan slugs, exactly.
    Without a `work:` header the file name decides: `<N>-…`, `issue-<N>` or a
    whole slug part; or the `review:` value equals a plan slug. Issues are
    tried before slugs; the newest by name wins. Taking simply the newest
    report put an unrelated item's findings into a delta bundle (observed
    downstream), and so did a slug matched inside another word."""
    slugs = [s for s in dict.fromkeys(slugs) if s]
    issues = list(issues)
    bare = {n for repo, n in issues if repo is None}
    by_issue: list[tuple[str, str]] = []
    by_slug: list[tuple[str, str]] = []
    for rel, text in sorted(candidates):
        head = report_header(text)
        works = head.get("work", [])
        if works:
            if any(issue_key(w) in issues for w in works):
                by_issue.append((rel, text))
            elif any(w in slugs for w in works):
                by_slug.append((rel, text))
            continue  # another work's report, whatever its file name says
        s = DATE_PREFIX.sub("", Path(rel).stem)
        if any(s == str(n) or s.startswith(f"{n}-") or _slug_in_name(f"issue-{n}", s) for n in bare):
            by_issue.append((rel, text))
        elif any(_slug_in_name(slug, s) for slug in slugs) or \
                any(v in slugs for v in head.get("review", [])):
            by_slug.append((rel, text))
    hits = by_issue or by_slug
    return hits[-1] if hits else None


def prior_report(root: Path, slugs, issues, since: str, head: str) -> tuple[str, str] | None:
    """(path, text) of the previous round's report of this work, as committed.

    Candidates: the reports present at `since` (that version), and a report
    the delta adds only while everything from `since` up to the commit
    adding it touches `.process-work/` alone — the report lands before any
    fix code, so a fix cannot bring its own report. `report_of` picks among
    them; None when none is this work's (callers treat that as doubt)."""
    listed = _git_bytes(root, "ls-tree", "-r", "-z", "--name-only", head, "--", REVIEW_REPORTS)
    if listed is None:
        return None
    candidates: list[tuple[str, str]] = []
    for rel in sorted(p for p in listed.decode(errors="surrogateescape").split("\0") if p.endswith(".md")):
        text = _show(root, since, rel)
        if text is None:  # added by the delta: only ahead of any fix code
            added = _git_bytes(root, "log", "--reverse", "--format=%H", "--diff-filter=A",
                               f"{since}..{head}", "--", rel)
            first = (added or b"").decode().split()
            before = _git_bytes(root, "diff", "--name-only", "-z", "--no-renames",
                                since, first[0]) if first else None
            if before is None or any(not p.startswith(BOOKKEEPING)
                                     for p in before.decode(errors="surrogateescape").split("\0") if p):
                continue
            text = _show(root, first[0], rel)
        if text is not None:
            candidates.append((rel, text))
    return report_of(candidates, slugs, issues)


def _commit_sha(root: Path, ref: str) -> str | None:
    out = _git_bytes(root, "rev-parse", "--verify", "-q", f"{ref}^{{commit}}")
    return out.decode().strip() if out else None


@functools.lru_cache(maxsize=64)
def _unmerged_history(root_s: str, tip_sha: str, merged: tuple[str, ...]) -> frozenset[str] | None:
    """The commits of tip's history no integration ref holds (`merged`: their
    SHAs) — the range a push vouches for. None: git cannot list them."""
    out = _git_bytes(Path(root_s), "rev-list", tip_sha, "--not", *merged, "--")
    return None if out is None else frozenset(out.decode().split())


@functools.lru_cache(maxsize=1024)
def _base_problem(root_s: str, base: str, head: str, merged: tuple[str, ...]) -> str | None:
    """`full_round_base_problem`, once per (base, head) and integration state."""
    return full_round_base_problem(Path(root_s), base, head)


NO_INTEGRATION_REF = (
    "full-round REVIEW records not checked against the fork point: no integration ref "
    "resolves — fetch origin/main (or the remote default branch; `git remote set-head "
    "origin -a` names it)")


def _integration_bounds(root: Path, tip_sha: str) -> tuple[str, ...] | None:
    """The SHAs that bound what a push of `tip_sha` vouches for: the
    remote-tracking integration refs that do not contain it; only when no
    remote-tracking integration ref resolves at all, the local names that do
    not. A ref containing the tip bounds nothing (`_integration_base`'s
    principle): a local main fast-forwarded to the tip (finish.py) or a
    forged `master` at HEAD would otherwise hide the whole range. () when
    the deciding refs all contain the tip — it is integrated, nothing is
    vouched for (a stale local main behind origin/main does not reopen
    main's history); None when no integration ref resolves."""
    listed = _git_bytes(root, "for-each-ref", "--format=%(refname:short)",
                        "refs/remotes/*/main", "refs/remotes/*/master")
    remote_names = {*_remote_defaults(root), *(f"origin/{n}" for n in INTEGRATION_NAMES),
                    *(listed or b"").decode(errors="replace").split()}
    refs = [*integration_refs(root), *sorted(remote_names)]
    resolved = {ref: sha for ref in dict.fromkeys(refs) for sha in [_commit_sha(root, ref)] if sha}
    if not resolved:
        return None
    outside = {ref: sha for ref, sha in resolved.items()
               if _git_bytes(root, "merge-base", "--is-ancestor", tip_sha, sha) is None}
    if any(ref in remote_names for ref in resolved):
        # a remote ref decides alone: all of them containing the tip means it is
        # integrated — a stale local main behind it bounds nothing
        return tuple(sorted({sha for ref, sha in outside.items() if ref in remote_names}))
    return tuple(sorted(set(outside.values())))


def _full_rounds_split(root: Path, records: list[dict], tip: str
                       ) -> tuple[dict[int, str], list[dict], tuple[str, ...], bool]:
    """(invalid, outside, merged, unbounded): the full rounds whose head the
    push of `tip` carries unmerged, judged against the fork point; the full
    rounds whose head it does not carry, unjudged; the bounding integration
    SHAs; whether full rounds went unjudged because no integration ref resolves.
    Every record with a range is a full round since v2.53, `mode=delta` or not:
    a REVIEW binds the whole branch, and a delta line the push carries would
    otherwise clear a plan on a slice (refutation). Merged ones stand as main
    judged them."""
    full = [r for r in records if r.get("base") and r.get("head")]
    tip_sha = _commit_sha(root, tip) if full else None
    if tip_sha is None:
        return {}, [], (), False
    merged = _integration_bounds(root, tip_sha)
    if merged is None:
        return {}, [], (), True  # one finding (`check`), never one per record
    pushed = (_unmerged_history(str(root), tip_sha, merged) if merged else frozenset())
    invalid: dict[int, str] = {}
    outside: list[dict] = []
    for r in full:
        if pushed is not None and r["head"] not in pushed:
            outside.append(r)  # merged, missing or another branch's: not this push's range
            continue
        why = _base_problem(str(root), r["base"], r["head"], merged)
        if why:
            invalid[id(r)] = why
    return invalid, outside, merged, False


def invalid_full_rounds(root: Path, records: list[dict], tip: str = "HEAD") -> dict[int, str]:
    """id(record) → why, for every full-round REVIEW whose base is not the
    fork point of its head (`full_round_base_problem`, #160) — it clears
    nothing and anchors no delta. Judged are the records that vouch for the
    pushed range: head in `tip`'s history and in no integration ref (git
    unable to list that range: every record). A merged record stands as main
    judged it; a missing head or another branch's is not this push's
    (`unchecked_full_rounds` counts the latter). Without any integration ref
    nothing is judged (`unbounded_full_rounds`)."""
    return _full_rounds_split(root, records, tip)[0]


def unbounded_full_rounds(root: Path, records: list[dict], tip: str = "HEAD") -> bool:
    """Did full rounds go unjudged because no integration ref resolves?"""
    return _full_rounds_split(root, records, tip)[3]


def unchecked_full_rounds(root: Path, records: list[dict], tip: str = "HEAD") -> int:
    """How many full rounds off their fork point stay unjudged: head present
    and unmerged, but outside `tip`'s history (a stale branch's record)."""
    _invalid, outside, merged, _unbounded = _full_rounds_split(root, records, tip)
    if not outside or not merged:  # no bound: the tip is integrated, nothing is this push's
        return 0
    listed = _git_bytes(root, "rev-list", "--all", "--not", *merged, "--")
    unmerged = set((listed or b"").decode().split())
    return sum(1 for r in outside if r["head"] in unmerged
               and _base_problem(str(root), r["base"], r["head"], merged))


def invalid_records(root: Path, records: list[dict], tip: str = "HEAD") -> dict[int, str]:
    """id(record) → why, for every REVIEW record that clears nothing: full
    rounds off their fork point (`invalid_full_rounds`) — the gate, the
    standing-block arm and the train read passes through here."""
    return invalid_full_rounds(root, records, tip)


def superseded_records(root: Path, records: list[dict], invalid: dict[int, str]) -> dict[int, str]:
    """id(record) → the later round that supersedes it, for invalid records a
    valid full round of the same work with a higher round covers: its base is
    the fork point of its head (`full_round_base_problem`) and its head
    descends from the invalid record's head. Such a round reviewed everything
    from the fork point on, the off-fork line included, so the line hides no
    unreviewed code — it stays invalid and clears nothing (a block stays a
    block), but no longer stops every push (downstream: a pre-v2.53 delta
    line held two branches after their merge of main)."""
    later = [r for r in records if id(r) not in invalid and r.get("base") and r.get("head")]
    out: dict[int, str] = {}
    for r in records:
        if id(r) not in invalid or not r.get("head"):
            continue
        for v in sorted(later, key=lambda v: -int(v["round"])):
            if (work_key(v["work"]) == work_key(r["work"]) and int(v["round"]) > int(r["round"])
                    and _git_bytes(root, "merge-base", "--is-ancestor", r["head"], v["head"]) is not None
                    and full_round_base_problem(root, v["base"], v["head"]) is None):
                out[id(r)] = f"round={v['round']} head={v['head'][:12]}"
                break
    return out


def valid_passes(root: Path, records: list[dict], tip: str = "HEAD") -> list[dict]:
    """The passes among these records, invalid ones (`invalid_records`) left out."""
    bad = invalid_records(root, records, tip)
    return [r for r in records if r.get("verdict") == "pass" and id(r) not in bad]


def review_passes(root: Path, texts, tip: str = "HEAD") -> list[dict]:
    """The valid passes of these journal texts, judged for the push of `tip`."""
    return valid_passes(root, [f for text in texts for _ln, f in parse_review_lines(text)[0]], tip)


def _git_bytes(root: Path, *args: str) -> bytes | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            timeout=60,
            env=git_environment(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout if result.returncode == 0 else None


# --- per-run memo of git facts fixed by object ids (#182) -------------------
# `_history` asks the same questions again for every clearing pass and every
# plan: the parents of a merge, what git merges on its own, a blob at a path.
# A fact addressed by full object ids cannot change, so git answers it once
# per run. A failed read (None) is never kept: "git could not tell" stays
# "stale, fail closed" on the next ask.
_PURE: dict[tuple, object] = {}


def clear_memo() -> None:
    """Forget every memoized git fact (a long-lived caller after a fetch)."""
    _PURE.clear()


def _addressed(root: Path, revs: tuple[str, ...]) -> tuple | None:
    """The memo key part for a question about `revs`; None when one of them is
    not a full object id (a ref can move, so its answer is never kept)."""
    if all(GIT_SHA.fullmatch(r) for r in revs):
        return (str(root), revs)
    return None


def _git_pure(root: Path, revs: tuple[str, ...], *args: str) -> bytes | None:
    """`_git_bytes(root, *args)` for a question fully determined by the object
    ids in `revs` (every id the arguments name): answered once per run."""
    where = _addressed(root, revs)
    if where is None:
        return _git_bytes(root, *args)
    key = ("git", where, args)
    if key in _PURE:
        return _PURE[key]  # type: ignore[return-value]
    out = _git_bytes(root, *args)
    if out is not None:
        _PURE[key] = out
    return out


def _is_ancestor(root: Path, ancestor: str, descendant: str) -> bool:
    """Is `ancestor` reachable from `descendant`? A git failure reads as no,
    as `_git_bytes(... --is-ancestor ...) is not None` always did; only a
    definite answer about full ids is kept."""
    where = _addressed(root, (ancestor, descendant))
    if where is not None and ("anc", where) in _PURE:
        return _PURE[("anc", where)]  # type: ignore[return-value]
    try:
        result = subprocess.run(["git", "-C", str(root), "merge-base", "--is-ancestor", ancestor, descendant],
                                capture_output=True, timeout=60, env=git_environment())
    except (OSError, subprocess.TimeoutExpired):
        return False
    if result.returncode not in (0, 1):
        return False
    if where is not None:
        _PURE[("anc", where)] = result.returncode == 0
    return result.returncode == 0


def _commit_id(root: Path, rev: str) -> str:
    """The full commit id `rev` names; "" when it names none (or an option)."""
    if not rev or rev.startswith("-"):
        return ""
    return (_git_pure(root, (rev,), "rev-parse", "--verify", "-q", f"{rev}^{{commit}}") or b"").decode().strip()


class GitReadError(RuntimeError):
    """A git read the standing-block arm cannot do without failed."""


def _git_read(root: Path, *args: str, strict: bool) -> bytes | None:
    """`_git_bytes`, but a strict caller gets an error instead of None. The
    anchor readers answer "which work does this push carry?"; None read as
    "none" turned a failing `git log` into a push that carries nothing — and
    a block passed (downstream refutation)."""
    out = _git_bytes(root, *args)
    if out is None and strict:
        raise GitReadError(f"git {args[0]} failed")
    return out


# --- the review artifact digest: ONE formula, pinned against git config -----
# Producer (make_review_bundle), writer (attest.py) and verifier (this gate)
# must compute the same bytes on every clone. `git diff` output depends on
# user/repo config — diff.algorithm, diff.renames, diff.noprefix,
# diff.mnemonicPrefix, core.abbrev (index lines), external diff drivers,
# textconv — so a digest computed on one machine can honestly fail on another
# (observed downstream: an attest at core.abbrev=9 red-ed a fresh clone at 7).
# The canonical form pins every knob on the command line. Legacy digests
# (plain `git diff --binary`, the `--full-index` form, and the index lines at
# every core.abbrev from 4 to 16 — produced before the pin) stay verifiable.
CANONICAL_DIFF = (
    "-c", "diff.algorithm=myers", "-c", "diff.renames=false",
    "-c", "diff.noprefix=false", "-c", "diff.mnemonicPrefix=false",
    "-c", "diff.context=3", "-c", "diff.suppressBlankEmpty=false",
    "-c", "core.quotePath=true",
    "diff", "--binary", "--full-index", "--no-color", "--no-ext-diff",
    "--no-textconv", "--no-renames",
)


def delta_commands(root: Path, base: str, head: str, *, binary: bool = True,
                   names: bool = False) -> list[tuple[str, ...]] | None:
    """Own first-parent commits plus merge resolutions, never the imported side."""
    ancestors = _git_bytes(root, "rev-list", "--first-parent", head)
    if ancestors is None or base.encode() not in ancestors.splitlines():
        return None
    commits = _git_bytes(root, "rev-list", "--first-parent", "--reverse", f"{base}..{head}")
    if commits is None:
        return None
    flags = [a for a in CANONICAL_DIFF if binary or a not in ("--binary", "--full-index")]
    index = flags.index("diff")
    config, options = flags[:index], flags[index + 1:]
    if names:
        options = ["--name-status", "-z", "--no-renames", "--no-ext-diff", "--no-textconv"]
    commands = []
    for commit in commits.decode().splitlines():
        parents = _git_bytes(root, "rev-list", "--parents", "-n", "1", commit)
        if parents is None:
            return None
        parents = parents.decode().split()[1:]
        if len(parents) == 1:
            commands.append(tuple([*config, "diff", *options, parents[0], commit]))
        elif len(parents) == 2:
            # Only integration-side changes may be omitted. A feature-side
            # merge could otherwise hide entirely unreviewed implementation.
            if not any(_git_bytes(root, "merge-base", "--is-ancestor", parents[1], ref) is not None
                       for ref in integration_refs(root)):
                return None
            commands.append(tuple([*config, "-c", "merge.conflictStyle=merge", "show", "--format=",
                                   "--remerge-diff", *options, commit]))
        else:
            return None  # octopus/rewrite shapes need a full review
    return commands


def delta_diff(root: Path, base: str, head: str, *, binary: bool = True,
               names: bool = False) -> bytes | None:
    commands = delta_commands(root, base, head, binary=binary, names=names)
    if commands is None:
        return None
    parts = []
    for command in commands:
        out = _git_bytes(root, *command)
        if out is None:
            return None
        parts.append(out)
    return b"".join(parts)


def _cleared(passes: list[dict], ids: set[str], tier: int) -> bool:
    """Does any pass clear a plan of this tier? The REVIEW grammar caps tier
    at 3 — a plan on an extended downstream scale (tier 4/5) clears at the
    gated ceiling, not an unmeetable bar."""
    req = min(tier, 3)
    return any(r["work"] in ids and int(r["tier"]) >= req for r in passes)


# --- push anchoring: what THIS push carries ---------------------------------
INTEGRATION_NAMES = ("main", "master")
INTEGRATION_REFS = tuple(f"origin/{name}" for name in INTEGRATION_NAMES) + INTEGRATION_NAMES
INTEGRATION_TARGET_REFS = tuple(f"refs/heads/{name}" for name in INTEGRATION_NAMES)


def _remote_defaults(root: Path) -> list[str]:
    heads = (_git_bytes(root, "for-each-ref", "--format=%(symref)", "refs/remotes") or b"").decode().splitlines()
    return [ref.removeprefix("refs/remotes/") for ref in heads if ref.startswith("refs/remotes/")]


def integration_refs(root: Path) -> tuple[str, ...]:
    """Configured remote default branches first, with the legacy names as fallbacks."""
    defaults = _remote_defaults(root)
    names = [ref.split("/", 1)[1] for ref in defaults if "/" in ref]
    return tuple(dict.fromkeys([*defaults, *names, *INTEGRATION_REFS]))


def integration_targets(root: Path) -> tuple[str, ...]:
    names = [ref.split("/", 1)[1] for ref in _remote_defaults(root) if "/" in ref]
    return tuple(dict.fromkeys(f"refs/heads/{name}" for name in [*names, *INTEGRATION_NAMES]))

# the remote refs a push lands on. A hook exports PROCESS_PUSH_TARGETS from
# what git hands it on stdin (`<local_ref> <local_sha> <remote_ref>
# <remote_sha>`); the pre-commit framework sets PRE_COMMIT_REMOTE_BRANCH for
# its pre-push stage without any wiring — both are read, the explicit one first
PUSH_TARGETS_ENV = "PROCESS_PUSH_TARGETS"
PRE_COMMIT_TARGET_ENV = "PRE_COMMIT_REMOTE_BRANCH"
# The issue numbers a push CLAIMS, not every `#N` it mentions. A cross-reference
# ("see #12", "Merge pull request #34") claims nothing — read as a claim it
# makes a foreign Tier 3 plan this push's proof to produce and reds a branch that
# has nothing to do with it. Two forms count: a GitHub closing trailer anywhere
# in the message, and the `… (#N)` subject convention.
_ISSUE_CLOSING = re.compile(
    r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s*:?\s+#(\d+)\b", re.IGNORECASE)
_ISSUE_SUBJECT = re.compile(r"\(#(\d+)\)\s*$")


def push_targets(env: dict[str, str], *sources: list[str]) -> list[str]:
    """Every remote ref any source names: the arguments, git's ref lines and BOTH
    environment variables — the one owner of "where does this push go". A union, so a
    forged `PROCESS_PUSH_TARGETS` can add a target but never hide main, and pre-commit's
    `PRE_COMMIT_REMOTE_BRANCH` (the first ref line with something to push, nothing
    else) can never be all there is (refutation: the gate read the first one set)."""
    seen: list[str] = []
    for target in [*(t for source in sources for t in source),
                   *env.get(PUSH_TARGETS_ENV, "").split(),
                   *env.get(PRE_COMMIT_TARGET_ENV, "").split()]:
        if target not in seen:
            seen.append(target)
    return seen


def integration_push(env: dict[str, str] | None = None, root: Path | None = None) -> tuple[bool, str]:
    """(is this push a merge?, why not) — the switch between hard and note.

    The push-anchored arms promise something that hangs on the MERGE, not on
    every push: a worker pushes its feature branch while the review is still
    ahead of it (the attestation is written later, from the bundle). Blocking
    that push is a chicken-and-egg. So: hard only when a target ref is an
    integration branch, otherwise the same findings as notes.

    No variable at all (a manual run, CI) is deliberately the soft side: the
    gate cannot know where the work would land, and guessing "merge" would
    red every local run. The known limitation: a PR merged server-side never
    pushes main from a clone, so this switch never fires for that route —
    there, finish.py (run before the PR) is the stop, and the archive arm
    above catches the residue on main."""
    targets = push_targets(dict(os.environ) if env is None else env)
    if not targets:
        return False, (f"no push target known ({PUSH_TARGETS_ENV} unset) — hard "
                       f"only on a push to main/master")
    if any(t in integration_targets(root or Path.cwd()) for t in targets):
        return True, ""
    return False, (f"push targets {' '.join(targets)}, no integration branch — "
                   f"the proof is due on the merge push")


def merge_base(root: Path, tip: str = "HEAD", *, strict: bool = False) -> str | None:
    """A proper integration ancestor of tip, resolved offline: the fork point's SHA.

    Refuse a missing base or a ref already containing tip: neither bounds
    the incoming range. Never guess tip~1. An ambiguous fork point (a
    criss-cross merge) raises GitReadError instead of answering None or one
    silently picked base (`_integration_base`). `strict` remains accepted for
    compatibility with existing integrations.
    """
    found = _integration_base(root, tip)
    return found[1] if found else None


def integration_ref(root: Path, tip: str = "HEAD") -> str | None:
    """The integration ref whose fork point `merge_base` reports.

    Template verification takes this ref, not the fork SHA: a SHA already in
    tip's history has exactly one merge base with it, so a criss-cross would
    stay invisible to `git merge-base --all`."""
    found = _integration_base(root, tip)
    return found[0] if found else None


def _integration_base(root: Path, tip: str) -> tuple[str, str] | None:
    """(integration ref, fork point SHA) of tip — `process_git.fork_point`
    owns the fork. Every candidate is scanned in order (primary remotes,
    other remotes, local names); a ref that already contains tip is skipped,
    never terminal: a forged or stale `origin/main` at HEAD must not switch
    the base-scoped arms off. None only when no other ref yields a fork.

    An ambiguous fork point is no None either: read as "no base" it turned
    the gate's arms off (downstream #2381). On a primary ref that does not
    contain tip it raises GitReadError (the gate, finish and the train name
    it). On a fallback it is skipped when another ref answers — a later
    unique fork, or a ref containing tip (on main, a criss-crossed upstream
    must not red main) — and raises when nothing does."""
    tip_sha = (_git_bytes(root, "rev-parse", "--verify", "-q", f"{tip}^{{commit}}") or b"").strip()
    if not tip_sha:
        return None
    tip_hex = tip_sha.decode()
    listed = _git_bytes(root, "for-each-ref", "--format=%(refname:short)",
                        "refs/remotes/*/main", "refs/remotes/*/master")
    others = [r for r in (listed or b"").decode(errors="replace").split()
              if r not in integration_refs(root)]
    remote_names = set(_remote_defaults(root)) | {f"origin/{n}" for n in INTEGRATION_NAMES}
    remotes = [r for r in integration_refs(root) if r in remote_names]
    local = [r for r in integration_refs(root) if r not in remote_names]
    contained = False
    ambiguous: GitReadError | None = None
    for ref in [*remotes, *sorted(others), *local]:
        if _git_bytes(root, "rev-parse", "--verify", "-q", f"{ref}^{{commit}}") is None:
            continue
        if _git_bytes(root, "merge-base", "--is-ancestor", tip_hex, ref) is not None:
            contained = True  # integrated here: bounds nothing, decides nothing
            continue
        try:
            return ref, fork_point(root, ref, tip_hex)
        except NoForkPoint:
            continue
        except ValueError as exc:
            error = GitReadError(f"integration base of {tip} on {ref}: {exc}")
            if ref in remotes:
                raise error from None  # the primary ref is the one chosen
            ambiguous = ambiguous or error
    if ambiguous is not None and not contained:
        raise ambiguous
    return None


def full_round_base_problem(root: Path, base: str, head: str) -> str | None:
    """Why `base` cannot carry a FULL review round of `head` — None when it can.

    A full round reviews the whole branch: its base is the fork point of
    `head` from the integration branch (`_integration_base`). Any other base
    reviews a slice and records it as the whole (#160). The writers (attest,
    the review bundle) refuse it; a fork that cannot be told is refused with
    the reason. A head no integration ref forks and one contains is an audit
    of a merged range: no fork bounds it, and any base stands (a forged ref
    at the head does not count while another ref still forks it). The gate
    judges existing records through `invalid_full_rounds`."""
    try:
        found = _integration_base(root, head)
    except GitReadError as exc:
        return (f"a full round's base must be the one fork point of the head: {exc}")
    if found is None and any(
            _git_bytes(root, "rev-parse", "--verify", "-q", f"{ref}^{{commit}}") is not None
            and _git_bytes(root, "merge-base", "--is-ancestor", head, ref) is not None
            for ref in integration_refs(root)):
        return None  # no ref forks it, one contains it: an audit of a merged range
    if found is None:
        return (f"a full round's base must be the fork point of {head[:12]} from the "
                f"integration branch, and no integration ref resolves — fetch it; if the "
                f"remote's default branch is not main/master, run `git remote set-head "
                f"origin -a` so origin/HEAD names it")
    ref, fork = found
    resolved = (_git_bytes(root, "rev-parse", "--verify", "-q", f"{base}^{{commit}}") or b"").strip()
    if resolved.decode(errors="replace") != fork:
        return (f"base {base[:12]} is not the fork point {fork[:12]} of {head[:12]} from {ref} "
                f"— a full round reviews the whole branch from the integration branch (Tier 3 "
                f"needs one); a stacked branch rebases onto {ref} first — a review always "
                f"covers the whole branch from its fork point")
    return None


def push_base(root: Path, tip: str, remote_sha: str) -> str | None:
    """The commit a push of `tip` starts at, from what the push itself knows.

    A pre-push hook gets the remote's current SHA per ref line; the
    merge-base with it is the range the remote does not have yet. Nothing
    else stands in for it: not the LOCAL `main`, which a session can advance
    onto `tip`, and not `origin/main` either — a remote-tracking ref equal to
    `tip` empties the range just as the local one does, and a block rides
    through (downstream refutation, reproduced with a shallow clone). So a
    new ref (all-zero SHA), a value that is no git SHA, a SHA this clone
    lacks and a history without a common ancestor all answer None = cannot
    tell; the caller refuses, and the way out is to fetch first — the train
    and `finish.py` do."""
    if not GIT_SHA.fullmatch(remote_sha) or not remote_sha.strip("0"):
        return None
    if _git_bytes(root, "merge-base", "--is-ancestor", remote_sha, tip) is None:
        return None
    out = _git_bytes(root, "merge-base", tip, remote_sha)
    return out.decode(errors="replace").strip() if out is not None and out.strip() else None


def issue_refs_in_range(root: Path, tip: str = "HEAD", *, base: str | None = None,
                        strict: bool = False) -> set[int]:
    """The issue numbers the commits since the merge-base CLAIM as their own
    (`_ISSUE_CLOSING`, `_ISSUE_SUBJECT`) — read from the local repo only, so
    the gate stays offline like its neighbours. A plan is this push's
    business when the push carries its file (`paths_in_flight`) or claims
    its issue here; both arms mean the same thing by "this push's proof".
    `strict`: a failing `git log` raises GitReadError instead of reading as
    "claims nothing"."""
    base = base or merge_base(root, tip)
    if base is None:
        return set()
    out = _git_read(root, "log", "--format=%B%x00", f"{base}..{tip}", strict=strict)
    if out is None:
        return set()
    refs: set[int] = set()
    for message in out.decode(errors="replace").split("\0"):
        body = message.strip()
        if not body:
            continue
        refs |= {int(n) for n in _ISSUE_CLOSING.findall(body)}
        refs |= {int(n) for n in _ISSUE_SUBJECT.findall(body.splitlines()[0])}
    return refs


def paths_in_flight(root: Path, tip: str = "HEAD", *, base: str | None = None,
                    strict: bool = False) -> set[str] | None:
    """Repo-relative paths this push carries: the committed range
    `{base}...HEAD`, nothing else. An unscoped "every active Tier 3 plan"
    reds every push in the repo for a plan the pusher does not own (measured
    downstream: a committed decision paper, tier 3, deliberately unimplemented,
    blocked an unrelated branch). Untracked, staged and modified files are
    deliberately NOT in flight: a push transports commits, and an uncommitted
    plan draft travels with nothing. `--no-optional-locks`: a gate must never
    take `index.lock` out from under a concurrent commit. `-z`, read by
    `_names`: git quotes a non-ASCII name without it, the quoted name matches
    no plan, and the plan read as somebody else's — a Tier 2 plan finished
    without a review (downstream refutation).

    No base is "nothing in flight" (the plan-anchored arms still run); a base
    whose diff git cannot list is None = cannot tell. Read as empty, a failing
    `git diff` (a missing tree object) made every plan somebody else's: finish
    called a Tier 2 plan without review ready, and a Tier 3 merge push went
    through without proof (downstream refutation). Callers treat None as
    "every active plan is in flight" and say so (a `strict` caller gets
    GitReadError instead)."""
    base = base or merge_base(root, tip)
    if base is None:
        if _git_bytes(root, "rev-parse", "--verify", f"{tip}^{{commit}}") is not None:
            if strict:
                raise GitReadError("no proper integration base; fetch the remote default branch")
            return None
        return set()  # unborn repositories carry no pushed commits
    return _names(_git_read(root, "--no-optional-locks", "diff", "--no-ext-diff",
                            "--no-textconv", "--no-color", "--name-only", "-z",
                            f"{base}...{tip}", strict=strict))


IN_FLIGHT_UNKNOWN = ("git could not list the paths this push carries (`git diff "
                     "<base>...HEAD` failed)")


# --- the standing block: the latest verdict of a pushed work is `block` -----
# Observed downstream: round 2 of a Tier 1 work stood at `verdict=block`, and
# the push to main went through — the gate collected passes only, and every
# tier-keyed arm says "skip" below Tier 2. This arm is tier-blind: the
# latest verdict per work id counts (highest round; an equal round goes to
# the block), read from the commits of the pushed range, never the worktree.

def latest_verdicts(records: list[dict]) -> dict[str, dict]:
    """The REVIEW record that stands per work id: the highest round; on
    equal rounds a block wins. `round` is the only order a line carries
    (shards have no global sequence), and an equal-round pair only exists
    where two reviews ran in parallel — there failing closed is right."""
    standing: dict[str, dict] = {}
    for fields in records:
        current = standing.get(fields["work"])
        if current is None or _verdict_rank(fields) > _verdict_rank(current):
            standing[fields["work"]] = fields
    return standing


def _verdict_rank(fields: dict) -> tuple[int, bool]:
    return int(fields["round"]), fields["verdict"] == "block"


# a journal folder `issue-<W>/` belongs to work W — it travels with a rebase,
# where a `head=` SHA does not
_ISSUE_SHARD = re.compile(re.escape(JOURNAL_DIR) + r"/issue-([^/]+)/")


def _record_identity(fields: dict) -> tuple[tuple[str, str], ...]:
    """What makes a REVIEW record the same record wherever it stands: all its fields."""
    return tuple(sorted(fields.items()))


class RangeRecords(NamedTuple):
    """The REVIEW records of a pushed range, read from `base` and `tip`."""

    seen: list[tuple[str, dict]]
    """(location, fields) of every record that stands at `base` or at `tip`."""
    at_base: list[dict]
    """The records at `base` — what the remote already holds."""
    added: list[dict]
    """The records `tip` holds more often than `base` does."""


def _journal_blobs(root: Path, commit: str, *, strict: bool) -> list[tuple[str, str]]:
    """(path, blob SHA) of the journal shards at `commit` — `ls-tree -z`, no diff involved."""
    out = _git_read(root, "ls-tree", "-r", "-z", commit, "--", JOURNAL_DIR, strict=strict)
    if out is None:
        raise GitReadError(f"git ls-tree {commit} failed")
    blobs = []
    for raw in out.split(b"\0"):
        meta, tab, name = raw.partition(b"\t")
        parts = meta.split()
        rel = name.decode("utf-8", errors="surrogateescape")
        if not tab or len(parts) != 3:
            continue
        # a symlink's blob is the link text, a submodule is no blob: the records
        # they point at would not be read, and a block there would ride along.
        # Checked for EVERY entry under the journal, before the `.md` filter — a
        # symlinked folder, or the journal itself as a symlink, has no `.md` name
        if parts[0] != b"100644" and parts[0] != b"100755":
            raise GitReadError(f"{rel} at {commit[:12]} is a symlink or submodule in the journal "
                               f"(mode {parts[0].decode()}) — a shard must be a plain file")
        if record_kind(rel) == "journal":
            blobs.append((rel, parts[2].decode()))
    return blobs


def _blob_texts(root: Path, shas: list[str]) -> dict[str, str]:
    """The text of each blob, read in ONE `cat-file --batch` (a base holds hundreds of shards)."""
    if not shas:
        return {}
    try:
        result = subprocess.run(["git", "-C", str(root), "cat-file", "--batch"],
                                input="".join(f"{sha}\n" for sha in shas).encode(),
                                capture_output=True, timeout=60, check=False, env=git_environment())
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GitReadError(f"git cat-file failed ({type(exc).__name__})") from exc
    if result.returncode != 0:
        raise GitReadError("git cat-file failed")
    texts, data = {}, result.stdout
    for sha in shas:
        header, _nl, data = data.partition(b"\n")
        parts = header.split()
        if len(parts) != 3 or parts[1] != b"blob":
            raise GitReadError(f"git cat-file cannot read the blob {sha}")
        size = int(parts[2])
        texts[sha] = data[:size].decode("utf-8", errors="replace")
        data = data[size + 1:]
    return texts


def range_records(root: Path, base: str, tip: str) -> RangeRecords:
    """ONE comparison of `base` and `tip` — the owner of "which REVIEW
    records does this push add, and which did it hold at all?".

    `added`: an identity (all fields) `tip` holds more often than `base` — a
    record that only moved to another shard keeps its count and adds nothing
    (a set difference lost a second identical `block` line downstream).
    `seen`: every record that stands at `base` or `tip`; a block among them
    stands until a pass AT `tip` clears it (`standing_block_findings`).

    Until v2.53 every commit of the range was read as well, so that a block
    the range deleted, or brought in and dropped again, still stood. Deleting
    a journal line is a visible diff, not a gap an agent slips through
    unnoticed; reading the whole range cost a walk per push and its own
    defects. Every git failure is a GitReadError, never an empty answer."""
    tip_sha = (_git_read(root, "rev-parse", "--verify", f"{tip}^{{commit}}", strict=True)
               or b"").decode().strip()
    order = [base, *([tip_sha] if tip_sha != base else [])]
    trees = {commit: _journal_blobs(root, commit, strict=True) for commit in order}
    texts = _blob_texts(root, sorted({sha for blobs in trees.values() for _rel, sha in blobs}))
    parsed = {sha: parse_review_lines(text)[0] for sha, text in texts.items()}
    counts: dict[str, Counter] = {}
    seen: dict[tuple[tuple[str, str], ...], tuple[str, dict]] = {}
    for commit in order:
        count: Counter = Counter()
        for rel, sha in trees[commit]:
            for lineno, fields in parsed[sha]:
                identity = _record_identity(fields)
                count[identity] += 1
                seen.setdefault(identity, (f"{commit[:12]}:{rel}:{lineno}", fields))
        counts[commit] = count
    peak: Counter = Counter()
    for commit in order[1:]:
        peak |= counts[commit]
    added = [dict(identity) for identity, n in peak.items() if n > counts[base][identity]]
    at_base = [fields for _rel, sha in trees[base] for _lineno, fields in parsed[sha]]
    return RangeRecords(seen=list(seen.values()), added=added, at_base=at_base)


def pushed_work_ids(root: Path, records: list[dict], in_flight: set[str] | None, *,
                    tip: str = "HEAD", base: str | None = None, strict: bool = False,
                    added: list[dict] | None = None) -> set[str]:
    """The work ids this push carries, from three anchors that survive each
    other's failure: a commit of the range claims the issue, the range adds
    a REVIEW record for the work (or a shard of the range sits in the work's
    own `issue-<W>/` folder), or a REVIEW line's `head=` lies in the range.

    A rebase breaks the third (the SHA changes) and the record anchor
    carries on — in the downstream incident the attest commit sat in the
    range. Only ADDED records anchor (`range_records`): a daily shard holds
    the lines of many works, and a touched shard must not pull every block
    in it into an unrelated push. `added` is `range_records(...).added` when
    the caller already compared the range."""
    base = base or merge_base(root, tip)
    carried = {str(number) for number in issue_refs_in_range(root, tip, base=base, strict=strict)}
    if base is None:
        return carried
    for rel in sorted(in_flight or ()):
        folder = _ISSUE_SHARD.match(rel) if record_kind(rel) == "journal" else None
        if folder:
            carried.add(folder.group(1))
    if added is None:
        try:
            added = range_records(root, base, tip).added
        except GitReadError:
            if strict:
                raise
            added = []
    carried |= {f["work"] for f in added}
    range_commits = _git_read(root, "rev-list", f"{base}..{tip}", strict=strict)
    if range_commits is not None:
        in_range = set(range_commits.decode(errors="replace").split())
        carried |= {f["work"] for f in records if f.get("head") in in_range}
    return carried


def _blocks(located: list[tuple[str, dict]]) -> dict[str, tuple[str, dict]]:
    """(location, record) of the block that stands per work — `latest_verdicts` over the list."""
    where = {id(fields): loc for loc, fields in located}
    return {work: (where[id(rec)], rec)
            for work, rec in latest_verdicts([fields for _loc, fields in located]).items()
            if rec["verdict"] == "block"}


def _history_blocks(compared: RangeRecords, root: Path, tip: str = "HEAD") -> list[tuple[str, dict]]:
    """The records the history adds to the verdict at `tip`: the blocks it
    held, and the passes the remote already holds.

    Blocks count wherever they stood, passes only where they are pushed or
    already merged: a pass only the history holds (reverted, lost in a
    conflict, deleted from main) would otherwise clear a block. The passes
    at `base` join as they are: main already judged them, and a journal
    pruned after the merge does not reopen the work. The order is
    `latest_verdicts`' own, so a block of the range is cleared only by a
    LATER round. Changing a verdict in place (block → pass, same round) is
    refused: by its lines it cannot be told from two parallel reviews of one
    round whose block a merge dropped; whoever changes a verdict counts the
    round up."""
    blocks = [(loc, f) for loc, f in compared.seen if f["verdict"] == "block"]
    merged = [("base", f) for f in valid_passes(root, compared.at_base, tip)]
    return blocks + merged


def standing_block_findings(root: Path, tip: str = "HEAD", *, remote_sha: str | None = None,
                            refuse_unreadable: bool = True, allow_non_fast_forward: bool = False) -> list[str]:
    """The findings of a standing block: the latest verdict of a work the
    push of `tip` carries is `block`.

    Tier-blind and plan-blind on purpose — the tier-keyed arms of `check` all
    say "skip" below Tier 2. Four rules keep it honest about WHAT is pushed:

    - the records are read from commits, not the worktree: a `pass` that no
      commit carries clears nothing, an uncommitted `block` blocks nothing;
    - `tip` is the pushed commit, not whatever HEAD says;
    - the base comes first. With `remote_sha` (a hook's ref line) it is what
      the remote lacks (`push_base`), and a push whose base cannot be told
      is refused whether or not a block is in sight — the block may be
      exactly what the missing range would show. Without it, the
      integration-ref ladder of `merge_base` (strict); there a missing base
      only matters when `tip` shows a block;
    - the verdicts are those of `base` and of `tip` (`range_records`): a
      block that stands at either is cleared only by a pass at `tip` or at
      `base` (`_history_blocks`).

    Plans join issue and work id at every tier (`issue: #42` in a Tier 1
    plan lets `work=my-feature` follow a commit that says `(#42)`)."""
    texts = record_texts(root, RECORD_KINDS, ref=tip)
    if texts is None:
        return [f"cannot read the review records at {tip} — a push whose records cannot "
                f"be read is refused"] if refuse_unreadable else []
    at_tip: list[tuple[str, dict]] = []
    malformed: list[str] = []
    for rel, text in texts:
        if record_kind(rel) == "journal":
            parsed, errors = parse_review_lines(text)
            at_tip += [(f"{rel}:{lineno}", fields) for lineno, fields in parsed]
            # a line the parser cannot read is no `pass` and no `block`
            malformed += [f"{rel}:{lineno}: malformed REVIEW line — {message} — a push whose "
                          f"review records cannot be read is refused" for lineno, message in errors]
    if malformed:
        return malformed
    # an invalid pass clears no block (`invalid_records`)
    bad = invalid_records(root, [f for _loc, f in at_tip], tip)
    at_tip = [(loc, f) for loc, f in at_tip if id(f) not in bad or f["verdict"] != "pass"]
    if remote_sha is not None and GIT_SHA.fullmatch(remote_sha) and not remote_sha.strip("0"):
        # the remote has no such ref: this push creates main and carries its
        # whole history, so every work standing blocked at the tip is carried
        return [f"work {work}: the latest REVIEW is verdict=block (round {rec['round']}, "
                f"{loc}) and this push creates the integration branch with that work — a "
                f"later round with verdict=pass has to clear it before the merge"
                for work, (loc, rec) in sorted(_blocks(at_tip).items())]
    if remote_sha is None:
        try:
            base, bases = merge_base(root, tip, strict=True), integration_refs(root)
        except GitReadError as exc:
            # an ambiguous fork point bounds no range: refused, blocks or not
            return [f"cannot determine the pushed range of {tip}: {exc}"]
    else:
        base = push_base(root, tip, remote_sha)
        if base is None and allow_non_fast_forward:
            common = _git_bytes(root, "merge-base", tip, remote_sha)
            base = common.decode().strip() if common else None
        bases = (f"the remote SHA {remote_sha or '(empty)'}",)
    if base is None:
        if remote_sha is None and not _blocks(at_tip):
            return []
        return [f"cannot determine the pushed range of {tip}: none of {', '.join(bases)} "
                f"resolves, and without the range neither the blocks it held nor the commit "
                f"that claims a work can be read — fetch the remote, then push again"]
    try:
        compared = range_records(root, base, tip)
        standing = _blocks(at_tip + _history_blocks(compared, root, tip))
        if not standing:
            return []
        in_flight = paths_in_flight(root, tip, base=base, strict=True)
        carried = pushed_work_ids(root, [f for _loc, f in at_tip + compared.seen], in_flight,
                                  tip=tip, base=base, strict=True, added=compared.added)
        claimed = issue_refs_in_range(root, tip, base=base, strict=True)
    except GitReadError as exc:
        return [f"cannot read the pushed range of {tip}: {exc} — a push whose range cannot be "
                f"read is refused (a standing block could ride along)"]
    plans = [(rel, text) for rel, text in texts
             if record_kind(rel) in ("plan", "plan-archive", "spec-plan")]
    dedated: dict[str, int] = {}
    for rel, _text in plans:
        key = DATE_PREFIX.sub("", plan_stem(rel))
        dedated[key] = dedated.get(key, 0) + 1
    for rel, text in plans:
        text = _unfenced(text)
        if claimed & _plan_issue_numbers(text):
            unique = dedated[DATE_PREFIX.sub("", plan_stem(rel))] == 1
            carried |= _plan_work_ids(plan_stem(rel), text, include_dedated=unique)
    return [f"work {work}: the latest REVIEW is verdict=block (round {rec['round']}, "
            f"{loc}) and this push carries that work — a later round with "
            f"verdict=pass has to clear it before the merge"
            for work, (loc, rec) in sorted(standing.items()) if work in carried]


BOOKKEEPING = ".process-work/"


REMOTE_INTEGRATION_REFS = tuple(ref for ref in INTEGRATION_REFS if "/" in ref)


def _integration_ref(root: Path, tip: str = "HEAD") -> str | None:
    """The integration branch as it stands BEFORE this push. A ref that already
    contains HEAD cannot be that — pushing local `main` without an
    `origin/main` would otherwise exclude everything (downstream refutation);
    then there is no base, and the check stays conservative.

    The remote ref is the authority. A local main ahead of it counts only
    when all it adds are merges on its first-parent chain — a train that
    merged but has not pushed yet; measured against the stale origin, those
    passengers would read as unreviewed. Anything else a local main carries
    (a commit made on main by mistake, a `master` pointed at unreviewed work)
    is not integrated, and does not hide code (downstream refutation)."""
    def usable(ref: str) -> bool:
        out = _git_bytes(root, "rev-parse", "--verify", "-q", f"{ref}^{{commit}}")
        return bool(out and out.strip()) and \
            _git_bytes(root, "merge-base", "--is-ancestor", tip, ref) is None
    remote_names = set(_remote_defaults(root)) | {f"origin/{n}" for n in INTEGRATION_NAMES}
    remote = next((r for r in integration_refs(root) if r in remote_names and usable(r)), None)
    for local in (r for r in integration_refs(root) if r not in remote_names and usable(r)):
        if remote is None:
            return local
        if _git_bytes(root, "merge-base", "--is-ancestor", remote, local) is None:
            continue
        extra = _git_bytes(root, "rev-list", "--first-parent", "--no-merges", local, f"^{remote}")
        if extra is not None and not extra.strip():
            return local
    return remote


def _names(out: bytes | None) -> set[str] | None:
    """NUL-separated path names (`-z`): non-ASCII names arrive unquoted."""
    if out is None:
        return None
    # surrogateescape: a name that is not UTF-8 goes back to git byte for
    # byte; nothing but the empty field is dropped (a name of whitespace is a
    # name) — downstream refutation
    return {n for n in out.decode(errors="surrogateescape").split("\0") if n}


class History(NamedTuple):
    """What git says about one reviewed head and what is pushed — the facts
    `decide` judges. Gathered by `_history`, one field per case the review
    gate has met downstream (each one a patch before this table existed)."""
    git_error: bool = False           # git could not answer: fail closed
    shallow_missing: bool = False     # the head is not in a shallow clone
    in_history: bool = True           # False: the head is in no history here
    late: frozenset = frozenset()     # content at the tip that is no reviewed state
    fellow: tuple = ()                # (merge, paths): a train merge of another
    #                                   passenger that adds code of its own


def decide(h: History, head: str) -> tuple[str, str]:
    """`("fresh", "")` or `("stale", reason)` — the whole staleness rule."""
    if h.git_error:
        return "stale", (f"cannot determine what changed after the reviewed head {head[:9]} "
                         f"(git did not answer) — not taken as reviewed")
    if h.shallow_missing:
        return "stale", (f"the reviewed head {head[:9]} is not in this shallow clone — cannot check "
                         f"the review; fetch the history (`git fetch --unshallow`)")
    if not h.in_history:
        return "stale", (f"the reviewed head {head[:9]} is not in this repository — the review "
                         f"covers nothing here; review again and attest the new head")
    if h.late:
        shown = sorted(h.late)
        return "stale", (f"code changed after the reviewed head ({', '.join(shown[:4])}"
                         f"{', …' if len(shown) > 4 else ''}) — the review does not cover it; "
                         f"re-review (`make_review_bundle.py --since <head>` shows the reviewer "
                         f"the delta) and attest the new head")
    if h.fellow:
        merge, paths = h.fellow[0]
        shown = sorted(paths)
        return "stale", (f"{'train merge ' + merge[:9] if merge else 'a train merge'} of another passenger adds code of its own "
                         f"({', '.join(shown[:4])}{', …' if len(shown) > 4 else ''}) — not this "
                         f"work's code, but no merge may carry code outside every review; rebuild the train")
    return "fresh", ""


def _entries(root: Path, tree: str, paths) -> dict[str, str] | None:
    """`path -> "<mode> <object>"` for each of `paths` present in `tree` (a
    commit or tree id); a path absent there is absent here. None when git
    cannot tell."""
    out: dict[str, str] = {}
    names = sorted(paths)
    for i in range(0, len(names), 200):
        raw = _git_pure(root, (tree,), "--literal-pathspecs", "ls-tree", "-z", tree, "--", *names[i:i + 200])
        if raw is None:
            return None
        for entry in raw.split(b"\0"):
            meta, _tab, name = entry.partition(b"\t")
            fields = meta.split()
            if len(fields) == 3:
                out[name.decode(errors="surrogateescape")] = f"{fields[0].decode()} {fields[2].decode()}"
    return out


def _reviewed_merge(root: Path, base: str, heads: list[str]) -> tuple[str, frozenset[str]] | None:
    """(tree, conflicted paths) git makes of `base` merged with each of
    `heads` in turn — the state these reviews saw their change land in. A
    path that conflicted in any step is no reviewed state at all: git writes
    markers there, or one side's file where no marker fits (modify/delete,
    rename/delete, a file turned symlink — refutation of step B). A head
    that already contains the state fast-forwards, without `merge-tree`.
    Intermediate merges are written as unreferenced commits (`merge-tree`
    needs commits); gc takes them. None when git cannot tell."""
    key = ("merged", _addressed(root, (base, *heads)))
    if key[1] is not None and key in _PURE:
        return _PURE[key]  # type: ignore[return-value]
    current, conflicted = base, set()
    heads = list(dict.fromkeys(heads))
    # a head another reviewed head contains adds nothing — merging it first
    # would fix its conflicts with main in place before the later review
    # that resolved them (Kenni shadow run: a later round reviewed the merge
    # of main, the first round's head conflicted with main)
    latest = [h for h in heads if not any(o != h and _is_ancestor(root, h, o) for o in heads)]
    for head in latest:
        if _is_ancestor(root, head, current):
            continue
        if _is_ancestor(root, current, head):
            current = head  # the head already carries this state: nothing to merge
            continue
        auto = _auto_merge(root, current, head)
        if auto is None:
            return None
        conflicted |= auto[1]
        made = _git_bytes(root, "-c", "user.name=review-gate", "-c", "user.email=review-gate@localhost",
                          "commit-tree", "--no-gpg-sign", auto[0], "-p", current, "-p", head,
                          "-m", "review gate: reviewed state")
        if made is None:
            return None
        current = made.decode().strip()
    out = _git_pure(root, (current,), "rev-parse", f"{current}^{{tree}}")
    if out is None:
        return None
    result = (out.decode().strip(), frozenset(conflicted))
    if key[1] is not None:
        _PURE[key] = result
    return result


def _unreviewed_at(root: Path, head: str, head_base: str, judged: str, integ: str | None,
                   reviewed: tuple[tuple[str, str], ...]) -> set[str] | None:
    """The paths of `judged` whose content is no reviewed state (see
    `_history`), bookkeeping aside; None when git cannot tell."""
    met: list[str] = []
    if integ:
        bases_out = _git_bytes(root, "merge-base", "--all", judged, integ)
        if bases_out is None:
            return None
        met = bases_out.decode(errors="replace").split()
    states: list[tuple[str, frozenset[str]]] = []
    partial: set[tuple[str, str]] = set()  # reviews that vouch for their own range only
    for base in met:
        # the commits the judged tip adds over this base: one walk, not one
        # question per review (Kenni: hundreds of reviews per run)
        above = _git_pure(root, (judged, base), "rev-list", judged, f"^{base}")
        if above is None:
            return None
        above_ids = set(above.decode(errors="replace").split())
        whole: list[str] = []
        # this work's head counts whole where the tip carries it, or where its
        # review saw everything it adds over main; a head rebased away with a
        # base above main saw a slice only (refutation of step B)
        if head in above_ids or _is_ancestor(root, head, base) or \
                (head_base and _is_ancestor(root, head_base, base)):
            whole.append(head)
        elif head_base:
            partial.add((head_base, head))
        for other_base, other_head in reviewed:
            other = other_head if GIT_SHA.fullmatch(other_head or "") else _commit_id(root, other_head)
            if not other or other == head or other not in above_ids:
                continue  # not in what the tip adds: on main already, or elsewhere
            other_base = other_base if GIT_SHA.fullmatch(other_base or "") else _commit_id(root, other_base)
            if other_base and _is_ancestor(root, other_base, base):
                whole.append(other)  # it saw everything it adds over main
            else:
                partial.add((other_base, other))
        # a review whose base lies above main counts whole when that base is
        # itself reviewed content: what the whole reviews below it merge to,
        # bookkeeping aside (Kenni shadow run: a work that reviewed its merge
        # of main recorded the previous work's attest commit as its base)
        promoted = True
        while promoted:
            promoted = False
            for other_base, other in sorted(partial):
                if not other_base:
                    continue  # a range nobody can name is no reviewed base
                inside = [w for w in whole if _is_ancestor(root, w, other_base)]
                # main as that base knew it: the tip may have met a newer one
                known = (_git_pure(root, (other_base, base), "merge-base", other_base, base) or b"").decode().strip()
                if not known:
                    continue  # no common history with main: it proves nothing
                below = _reviewed_merge(root, known, inside)
                if below is None:
                    return None
                differs = _names(_git_pure(root, (below[0], other_base), "diff", "--name-only", "--no-renames",
                                           "--ignore-submodules=none", "-z", below[0], other_base))
                if differs is None:
                    return None
                if not {p for p in differs | below[1] if not p.startswith(BOOKKEEPING)}:
                    partial.discard((other_base, other))
                    whole.append(other)
                    promoted = True
        merged = _reviewed_merge(root, base, whole)
        if merged is None:
            return None
        if head not in whole:
            # without this head the state is main's for the paths it
            # changed: those must not pass as main's version (a revert)
            own = _names(_git_pure(root, (head_base, head), "diff", "--name-only", "--no-renames",
                                   "--ignore-submodules=none", "-z", head_base, head)) if head_base else set()
            if own is None:
                return None
            merged = (merged[0], merged[1] | frozenset(own))
        states.append(merged)
    if not met:
        states = [(head, frozenset())]  # no integration branch to meet: the head is all there is
    first, first_conflicted = states[0]
    changed = _names(_git_pure(root, (first, judged), "diff", "--name-only", "--no-renames",
                               "--ignore-submodules=none", "-z", first, judged))
    if changed is None:
        return None
    left = {p for p in changed | first_conflicted if not p.startswith(BOOKKEEPING)}
    if not left:
        return left
    at_tip = _entries(root, judged, left)
    if at_tip is None:
        return None

    def matched(paths: set[str], state: tuple[str, frozenset[str]]) -> set[str] | None:
        here = _entries(root, state[0], paths)
        if here is None:
            return None
        return {p for p in paths if p not in state[1] and at_tip.get(p) == here.get(p)}

    for state in states:
        hit = matched(left, state)
        if hit is None:
            return None
        left -= hit
        if not left:
            return left
    # a review that saw a range above main vouches for the paths that range
    # changed, merged with main as git merges it
    for other_base, other in sorted(partial):
        if not left:
            break
        saw = _names(_git_pure(root, (other_base, other), "diff", "--name-only", "--no-renames",
                               "--ignore-submodules=none", "-z", other_base, other))
        mine = left & saw if saw is not None else set()
        for base in met if mine else []:
            merged = _reviewed_merge(root, base, [other])
            hit = matched(mine, merged) if merged is not None else None
            if hit:
                left -= hit
    for p in sorted(p for p in left if record_kind(p) == "spec-plan"):
        if _records_since_review(root, p, judged, states):
            left.discard(p)
    return left


def _records_since_review(root: Path, rel: str, judged: str,
                          states: list[tuple[str, frozenset[str]]]) -> bool:
    """Is the Spec Kit plan `rel` at `judged` — or, gone from there, its
    archived copy (`attest --archive`) — a reviewed state's version plus
    records only (`records_only`)? Unreadable is no."""
    def text(rev: str, path: str) -> str | None:
        raw = _git_bytes(root, "show", f"{rev}:{path}")
        # surrogateescape: a changed byte that is no UTF-8 stays a change
        return raw.decode("utf-8", errors="surrogateescape") if raw is not None else None
    after = text(judged, rel)
    if after is None:
        after = text(judged, f"{PLANS_ARCHIVE}/{rel.split('/')[1]}.md")
    if after is None:
        return False
    for commit, conflicted in states:
        before = text(commit, rel) if rel not in conflicted else None
        if before is not None and records_only(before, after):
            return True
    return False


def _history(root: Path, head: str, tip: str = "HEAD",
             reviewed: tuple[tuple[str, str], ...] = (), base: str = "") -> History:
    """Step B of the review-gate teardown: what is pushed counts as reviewed
    where its content is a reviewed state, not where its history reads right.

    A path is reviewed when its content at the tip (mode and object) equals
    git's own merge of the integration branch where the tip last met it
    (every merge base of tip and integration ref) with the reviewed head and
    with every other clearing review's head the tip adds over it — a path
    that conflicted in that merge matches nothing, so every resolution is
    unreviewed. A review counts whole when the tip carries its head or its
    base lies on main; one whose base lies above main vouches only for the
    paths its range changed. Without an integration branch the head is the
    one reviewed state.

    So a rebase or a merge of main that applies cleanly keeps the review
    (#158), and several reviewed works git merges cleanly are reviewed
    together (Kenni: three works on one branch, each editing the feature
    registry). Everything else is unreviewed: later commits — also one that
    sets a file back to main's version (refutation of step B: a partial
    revert of the reviewed change), any conflict resolution, a merge that
    keeps the branch's file where main had changed it or that throws the
    reviewed change away, evil merges.

    On the merge train's staging branch every carrier of this work is judged
    at its own branch tip, and every train merge must be git's own merge:
    what a train merge adds is the carrier's code (`late`) or another
    passenger's (`fellow`). Any git failure is stale (fail closed), never a
    weaker answer (Kenni #2439)."""
    error = History(git_error=True)
    head_id = _commit_id(root, head)
    if not head_id:
        shallow = (_git_bytes(root, "rev-parse", "--is-shallow-repository") or b"").strip() == b"true"
        return History(shallow_missing=True) if shallow else History(in_history=False)
    tip_id = _commit_id(root, tip)
    if not tip_id:
        return error
    head_base = base if GIT_SHA.fullmatch(base or "") else _commit_id(root, base) if base else ""
    integ = _integration_ref(root, tip_id)
    judged, fellow, carrier_own = [tip_id], [], set()
    staging = tip == "HEAD" and (_git_bytes(root, "symbolic-ref", "--short", "-q", "HEAD") or b"") \
        .decode(errors="replace").strip().startswith("train/")
    if staging and integ:
        walk = _git_bytes(root, "rev-list", "--first-parent", "--parents", tip_id, f"^{integ}")
        if walk is None:
            return error
        chain = [ln.split() for ln in walk.decode(errors="replace").splitlines() if ln.strip()]
        if chain and all(len(c) == 3 for c in chain):  # the train's chain: two-parent merges only
            carriers = [c for c in chain if _is_ancestor(root, head_id, c[2])]
            if carriers:
                # every passenger tip that carries this work, as it boarded
                # (refutation: judging only the newest hid an older carrier's code)
                judged = [c[2] for c in carriers]
                for merge, first, second in chain:
                    auto = _auto_merge(root, first, second)
                    if auto is None:
                        return error
                    added = _names(_git_pure(root, (auto[0], merge), "diff", "--name-only", "--no-renames",
                                             "--ignore-submodules=none", "-z", auto[0], merge))
                    if added is None:
                        return error
                    added = {p for p in added | auto[1] if not p.startswith(BOOKKEEPING)}
                    if any(c[0] == merge for c in carriers):
                        carrier_own |= added
                    elif added:
                        fellow.append((merge, frozenset(added)))
    left: set[str] = set()
    for one in judged:
        found = _unreviewed_at(root, head_id, head_base, one, integ, reviewed)
        if found is None:
            return error
        left |= found
    left |= carrier_own
    try:
        ref = integration_ref(root, tip)
        if ref and left:
            update = verify(root, ref, tip)
            if update['update'] and not update['errors'] and not update['migration']:
                left -= set(update['identical'])
    except (GitReadError, ValueError, OSError, subprocess.TimeoutExpired):
        pass  # unverifiable provenance never grants coverage
    return History(late=frozenset(left), fellow=tuple(fellow))


def _unreviewed_paths(root: Path, head: str, tip: str = "HEAD",
                      reviewed: tuple[tuple[str, str], ...] = (), base: str = "") -> set[str] | None:
    """Paths of code in `tip` that no review covers — None when git cannot
    tell (the merge train's boarding judges a branch by this)."""
    h = _history(root, head, tip, reviewed=reviewed, base=base)
    if h.git_error or h.shallow_missing or not h.in_history:
        return None  # not "nothing unreviewed": the review covers none of it
    return set(h.late).union(*(paths for _m, paths in h.fellow))


def _auto_merge(root: Path, ours: str, other: str) -> tuple[str, set[str]] | None:
    """What git would have merged on its own: (tree, conflicted paths) — None
    when git cannot tell (an old git without `merge-tree --write-tree`). Once
    per pair and run."""
    where = _addressed(root, (ours, other))
    if where is not None and ("auto", where) in _PURE:
        tree, conflicted = _PURE[("auto", where)]  # type: ignore[misc]
        return tree, set(conflicted)
    merged = _auto_merge_uncached(root, ours, other)
    if merged is not None and where is not None:
        _PURE[("auto", where)] = (merged[0], frozenset(merged[1]))
    return merged


def _auto_merge_uncached(root: Path, ours: str, other: str) -> tuple[str, set[str]] | None:
    try:
        r = subprocess.run(["git", "-C", str(root), "merge-tree", "--write-tree", "--allow-unrelated-histories", "--name-only", "-z",
                            "--no-messages", ours, other], capture_output=True, timeout=60, env=git_environment())
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode not in (0, 1):
        return None
    fields = [f for f in r.stdout.decode(errors="surrogateescape").split("\0") if f]
    if not fields:
        return None
    return fields[0].strip(), set(fields[1:])


def name_status(out: bytes | None) -> list[tuple[str, str, str]] | None:
    """`--name-status -z` read as (status letter, source, path): the source is
    the old name of a rename or copy, else "". The one reader of that format —
    every tool that needs the status of a path asks here, with `-z`, decoded as
    `_names` decodes (without `-z` git quotes a non-ASCII name, and the quoted
    name matches no plan; downstream refutation). None when git failed."""
    if out is None:
        return None
    fields, i = out.decode(errors="surrogateescape").split("\0"), 0
    entries: list[tuple[str, str, str]] = []
    while i + 1 < len(fields) and fields[i]:
        letter = fields[i][:1]
        if letter in ("R", "C") and i + 2 < len(fields):
            entries.append((letter, fields[i + 1], fields[i + 2]))
            i += 3
        else:
            entries.append((letter, "", fields[i + 1]))
            i += 2
    return entries


def merged_work(root: Path, rel: str, passes: list[dict], ids: set[str], tier: int) -> bool:
    """Does this plan belong to work the integration branch already carries?
    The plan file is on the integration ref and every clearing review's head
    is in it. Only a note: its stale check still runs — later code no review
    has seen is unreviewed whatever plan it lands under (a refutation showed
    a skip let unreviewed follow-up work through); later code another review
    saw is covered by that review (`reviewed` in `_history`)."""
    integ = _integration_ref(root)
    if integ is None or _git_bytes(root, "cat-file", "-e", f"{integ}:{rel}") is None:
        return False
    heads = [r["head"] for r in passes if r["work"] in ids and int(r["tier"]) >= min(tier, 3) and r.get("head")]
    return bool(heads) and all(
        _git_bytes(root, "merge-base", "--is-ancestor", h, integ) is not None for h in heads)


def _reviewed_heads(passes: list[dict], tier: int, known: set[str]) -> tuple[tuple[str, str], ...]:
    """(base, head) of every clearing CODE review at this plan's tier or
    above that records both, for work a plan names (`known`) — the commits of
    each range count as reviewed for any plan's stale check. A plan review
    (`work=<id>-plan`) saw no code, and a pass for work no plan names is
    nobody's review (refutation: both whitewashed unreviewed code)."""
    return tuple(dict.fromkeys((r["base"], r["head"]) for r in passes
                               if r.get("head") and r.get("base") and int(r["tier"]) >= min(tier, 3)
                               and r["work"] in known and not r["work"].endswith("-plan")
                               and r.get("mode", "full") == "full"))


def _known_work(root: Path, *, ref: str | None = None) -> set[str]:
    """Every work id any plan names — active, archived or Spec Kit."""
    known: set[str] = set()
    for rel, text in record_texts(root, PLAN_KINDS + ("plan-archive",), ref=ref) or []:
        stem = Path(rel).parent.name if rel.startswith(SPECS_DIR + "/") else Path(rel).stem
        known |= _plan_work_ids(stem, _unfenced(text), include_dedated=True)  # an example is no id
    return known


def no_clearing_review(rel: str, tier: int, ids) -> str:
    """The one wording of "this plan's review is missing" — with both ways out,
    so no site names only one (the gate and finish.py ask here)."""
    work = sorted(ids)
    pick = min(work, key=lambda i: (len(i), i)) if work else "<id>"
    return (f"{rel}: tier {tier} plan has no clearing REVIEW (verdict=pass, work in {work}, "
            f"tier>={min(tier, 3)}). Two ways out: review it and attest (attest.py --work {pick} "
            f"--tier {min(tier, 3)} … --verdict pass), or record the exception in the plan: "
            f"'review-waived: <reason> #<issue>' (journal-state-plans.md)")


def _residue(rel: str) -> str:
    return (f"{rel}: belongs to work already merged (its reviewed head is on the integration "
            f"branch) — later changes are not its code; archive the plan (a merge that "
            f"carries a cleared plan archives it)")


def stale_review(root: Path, passes: list[dict], ids: set[str], tier: int,
                 in_flight: set[str] | None = None,
                 reviewed: tuple[tuple[str, str], ...] = ()) -> str | None:
    """Why the clearing reviews of a plan no longer cover the code — None when
    one of them still does.

    A pass records the `head` it reviewed; `_history` compares what is
    pushed with the states that head makes reviewed, and `decide` words the
    verdict. Bookkeeping
    (journal, plans) is exempt: the attestation commit itself lands after the
    reviewed head. Fails closed: git errors and a head missing from a shallow
    clone are stale, not current.

    A pass without `head` (older records) counts as current only when no
    pass for the work has one. `in_flight` is kept for callers and no longer
    narrows the check: the range above is the push's own code, and an empty
    set must never mean "nothing to check"."""
    req = min(tier, 3)
    clearing = [r for r in passes if r["work"] in ids and int(r["tier"]) >= req]
    if not clearing:
        return None
    with_head = [r for r in clearing if r.get("head")]
    if not with_head:
        # a headless (older) pass counts only while no pass for the work —
        # of any tier — records a head
        if any(r.get("head") for r in passes if r["work"] in ids):
            return "no clearing REVIEW pass records the reviewed head, and a pass that does exists — attest the current head"
        return None
    reason = None
    for r in with_head:
        verdict, why = decide(_history(root, r["head"], reviewed=reviewed, base=r.get("base") or ""), r["head"])
        if verdict == "fresh":
            return None
        reason = why
    return reason


def issues_on_integration(root: Path, limit: int = 2000) -> set[int]:
    """Issue numbers claimed (closing trailer or `(#N)` subject) by commits
    already on the integration branch — the record of what was merged."""
    for ref in integration_refs(root):
        out = _git_bytes(root, "log", "--format=%B%x00", f"-{limit}", ref)
        if out is not None:
            refs: set[int] = set()
            for message in out.decode(errors="replace").split("\0"):
                body = message.strip()
                if not body:
                    continue
                refs |= {int(n) for n in _ISSUE_CLOSING.findall(body)}
                refs |= {int(n) for n in _ISSUE_SUBJECT.findall(body.splitlines()[0])}
            return refs
    return set()


def declared_issue_numbers(text: str) -> list[int]:
    """The issue numbers a plan or spec declares, in file order — bare `7`,
    `#7`, `owner/repo#7` or an issue URL; `issue: none` declares nothing."""
    numbers: list[int] = []
    for m in ISSUE_DECL.finditer(text):
        tok = m.group(1)
        if tok.isascii() and tok.isdigit():
            numbers.append(int(tok))
            continue
        parsed = parse_issue_ref(tok)
        if parsed is not None:
            numbers.append(parsed[1])
    return numbers


def _plan_issue_numbers(text: str) -> set[int]:
    """The issue numbers a plan declares — the join between a pushed commit
    and the tier only the plan knows."""
    return set(declared_issue_numbers(text))


def spec_dir_issue(fdir: Path) -> int | None:
    """A spec directory's issue: spec.md's `issue:` first (issue-before-spec),
    plan.md's as fallback — the one owner (publish_and_prune --stage and
    process_context ask it). A file's FIRST `issue:` line decides: unparseable
    there (`GH-12`, `none`) is None, never a later line or plan.md — refute: a
    spec snapshot went to the plan's issue instead of being refused."""
    for name in ("spec.md", "plan.md"):
        p = fdir / name
        m = ISSUE_DECL.search(p.read_text(encoding="utf-8", errors="replace")) \
            if p.is_file() else None
        if m:
            numbers = declared_issue_numbers(m.group(0))
            return numbers[0] if numbers else None
    return None


def slug_counts(stems) -> Counter:
    """How many of these plan stems share each de-dated slug — an active
    plan's slug is its work id only where it is unique among the active plans
    (the gate's rule; the train asks the same of a branch's active plans)."""
    return Counter(DATE_PREFIX.sub("", stem) for stem in stems)


def _plan_work_ids(stem: str, text: str, *, include_dedated: bool) -> set[str]:
    """The identifiers a REVIEW's `work=` may use to match this plan: the file
    stem, any `issue:` it declares, and — only when it is unique across the
    archive — the stem without its leading date. A de-dated slug shared by two
    archived plans (a feature re-planned on another day) is dropped, so one
    review cannot silently clear both."""
    ids = {stem}
    if include_dedated:
        ids.add(DATE_PREFIX.sub("", stem))
    for m in ISSUE_DECL.finditer(text):
        # only a real issue ref may act as a clearing work-id — `issue: v2.0`
        # or `issue: none` must not let an unrelated REVIEW clear this plan
        # (and `none` twice would let ONE review clear two plans). Read through
        # `ref_token`, as report headers and plan keys are: `**#42**`, `[#42](url)`
        # and `#42,` name issue 42
        tok = ref_token(m.group(1))
        if tok.isascii() and tok.isdigit():
            ids.add(tok)  # bare number, the historical form
            continue
        parsed = parse_issue_ref(tok)
        if parsed is not None:
            ids.add(tok)
            ids.add(str(parsed[1]))  # `work=42` matches `issue: owner/repo#42`
    return ids


UNCHECKED = re.compile(r"^\s*- \[ \] ", re.MULTILINE)
DECISIONS_HEADING = re.compile(r"^#{2,4}\s+Decisions\b", re.IGNORECASE | re.MULTILINE)


def speckit_unreviewed(root: Path, passes: list[dict]) -> list[tuple[str, int, set[str]]]:
    """Spec-dir plans past the review-presence gate's blind spot: the speckit
    path keeps its plan in specs/<dir>/plan.md and never archives it, so the
    archived-plan scan cannot see it. The completion signal there is the
    fully-ticked tasks.md. Returns (dir name, tier, matching work ids) for
    every spec dir whose tasks are all ticked, whose plan declares tier >= 2
    without a review-waived line, and which no clearing pass covers. One
    owner: finish.py blocks on this at the merge ritual; the review gate
    reports it as a note (a hard gate would red every push between the last
    tick and the review that must follow it)."""
    out: list[tuple[str, int, set[str]]] = []
    for _rel, plan in record_files(root, ("spec-plan",)):
        d = plan.parent
        tasks = d / "tasks.md"
        if not tasks.is_file():
            continue
        ttext = tasks.read_text(encoding="utf-8", errors="replace")
        if UNCHECKED.search(ttext) or not re.search(r"^\s*- \[[xX]\] ", ttext,
                                                    re.MULTILINE):
            continue  # in flight, or no checkbox grammar at all
        ptext = _unfenced(plan.read_text(encoding="utf-8", errors="replace"))
        tier = plan_tier(ptext)
        if tier is None or tier < 2 or review_waived(ptext):
            continue
        # the REVIEW grammar caps tier at 3 — a plan on an extended downstream
        # scale (tier 4/5) clears at the gated ceiling, not an unmeetable bar
        req = min(tier, 3)
        ids = _plan_work_ids(d.name, ptext, include_dedated=False)
        if not any(r["work"] in ids and int(r["tier"]) >= req for r in passes):
            out.append((d.name, tier, ids))
    return out


def verified_template_plan(root: Path, rel: str, text: str, *, tip: str = "HEAD",
                           update: dict | None = None) -> bool:
    """Shared exemption for a marked plan of a computed, acknowledged pure update."""
    if not re.search(r'^template-update:\s*true\s*$', text, re.M):
        return False
    try:
        found = _integration_base(root, tip)
    except GitReadError:
        return False  # an ambiguous fork point exempts nothing; the gate names it
    if not found:
        return False
    ref, base = found
    if update is None:
        try:
            update = verify(root, ref, tip)
        except (ValueError, OSError, subprocess.TimeoutExpired):
            return False
    pure = (update['update'] and not update['errors'] and not update['project_delta']
            and not update['migration'] and update.get('acknowledged'))
    return bool(pure and rel in (paths_in_flight(root, tip, base=base) or set()))


def template_review_findings(root: Path, update: dict, passes: list[dict],
                             *, tip: str = "HEAD") -> list[str]:
    """One owner for the update's review duty, used by gate, finish and train."""
    findings = [f'template verification failed: {e}' for e in update['errors']]
    # a failure withdraws everything: the errors are the finding, and an
    # unverified update has nothing to acknowledge or review yet (#170)
    if findings or not update['update']:
        return findings
    if not update.get('acknowledged'):
        findings.append('template update: owner/steward must acknowledge the behavior notes '
                        '(template_update.py --verify --base <integration-base> --ack <owner>)')
    if update['project_delta'] or update['migration']:
        tier = 3 if update['migration'] else 2
        known = _known_work(root, ref=tip)
        covering = [r for r in passes if int(r['tier']) >= tier
                    and r.get('base') == update['base'] and r.get('head')
                    and r.get('mode', 'full') == 'full' and r['work'] in known]
        if not any(_unreviewed_paths(root, r['head'], tip, _reviewed_heads(passes, tier, known),
                                     r.get('base') or '') == set()
                   for r in covering):
            findings.append(f'template update: tier {tier} REVIEW of the update range required for '
                            + ('the enforcement migration' if update['migration'] else
                               'project delta: ' + ', '.join(update['project_delta'])))
    return findings


class _Phases:
    """Marks which phase of `check` is running: one `gate-phase: <name>
    start|done <monotonic seconds>` line each on stderr. `gate_runner` reads
    them when it kills a gate that ran too long, so the red ledger names a slow
    phase instead of a review finding (#182). Silent unless the CLI turned it on."""

    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled
        self.current: str | None = None

    def _mark(self, name: str, kind: str) -> None:
        if self.enabled:
            print(f"gate-phase: {name} {kind} {time.monotonic():.3f}", file=sys.stderr, flush=True)

    def enter(self, name: str) -> None:
        self.leave()
        self.current = name
        self._mark(name, "start")

    def leave(self) -> None:
        if self.current is not None:
            self._mark(self.current, "done")
            self.current = None


REPORT_PHASES = False  # `main` turns the phase lines on; library callers stay quiet


def check(root: Path) -> tuple[list[str], list[str]]:
    hard: list[str] = []
    soft: list[str] = []
    phases = _Phases(REPORT_PHASES)

    # the push-anchored arms below are the merge's condition, not every
    # push's — see integration_push()
    to_integration, not_a_merge = integration_push(root=root)

    def presence(finding: str) -> None:
        """A push-anchored presence finding: hard on the merge push, a
        visible note anywhere else."""
        if to_integration:
            hard.append(finding)
        else:
            soft.append(f"{finding} [note only: {not_a_merge}]")

    # --- parse all REVIEW attestations from the (recursive) journal ---
    phases.enter("records")
    all_records: list[tuple[int, dict]] = []
    located: list[tuple[str, int, dict]] = []
    # an ambiguous fork point is a finding, never "no base": every arm keyed
    # on the pushed range would otherwise read nothing (downstream #2381)
    base_error = None
    try:
        scope_base = merge_base(root)
    except GitReadError as exc:
        base_error = exc
        scope_base = None
        hard.append(f"cannot bound the pushed range: {exc}")
    # no ref bounds HEAD at all (not: its shards could not be listed below)
    no_base = scope_base is None and base_error is None
    # the journal's shards — record_files owns where records live
    for rel, f in record_files(root, ("journal",)):
        try:
            text = f.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            hard.append(f"{rel}: not valid UTF-8")
            continue
        except OSError as exc:  # broken symlink, directory named *.md, …
            hard.append(f"{rel}: could not read: {exc}")
            continue
        records, errors = parse_review_lines(text)
        for lineno, msg in errors:
            hard.append(f"{rel}:{lineno}: malformed REVIEW line — {msg}")
        hard.extend(_arithmetic_violations(rel, records))
        all_records.extend(records)
        located += [(rel, lineno, f) for lineno, f in records]
    invalid = invalid_records(root, [f for _ln, f in all_records])
    superseded = superseded_records(root, [f for _ln, f in all_records], invalid) if invalid else {}
    for rel, lineno, f in located:
        if id(f) in superseded:
            soft.append(f"{rel}:{lineno}: REVIEW line clears nothing — {invalid[id(f)]}; "
                        f"superseded by the valid {superseded[id(f)]}")
        elif id(f) in invalid:
            hard.append(f"{rel}:{lineno}: malformed REVIEW line — {invalid[id(f)]}")
    unchecked = unchecked_full_rounds(root, [f for _ln, f in all_records])
    if unbounded_full_rounds(root, [f for _ln, f in all_records]):
        presence(NO_INTEGRATION_REF)
    if unchecked:
        soft.append(f"{unchecked} legacy full-round record(s) not checked against the fork "
                    f"point: head not in this push's history")
    # a full round off its fork point clears nothing; its block still stands
    all_records = [(ln, f) for ln, f in all_records
                   if id(f) not in invalid or f["verdict"] != "pass"]

    passes = [f for _ln, f in all_records if f["verdict"] == "pass"]
    known_work = _known_work(root)

    # A report is presentation, never authority. Recompute from the trusted
    # integration baseline and release renders; template loss is project delta.
    update = None
    if scope_base:
        try:
            # the ref, not scope_base: verify demands one fork point itself
            ref = integration_ref(root)
            if ref is None:
                raise ValueError('the integration ref behind the merge base disappeared')
            # the gate judges what is pushed: the committed tip, never the
            # worktree (template_update refuses a dirty tree before updating)
            update = verify(root, ref)
        except (GitReadError, ValueError, OSError, subprocess.TimeoutExpired) as exc:
            hard.append(f'template verification failed: {exc}')
    if update and (update['update'] or update['errors']):
        for finding in template_review_findings(root, update, passes):
            if finding.startswith('template verification failed:'):
                hard.append(finding)
            else:
                presence(finding)
        soft.append('template verification: ' + str(len(update['identical']))
                    + ' release-identical path(s), ' + str(len(update['project_delta']))
                    + ' project delta path(s)')

    # --- presence: archived (merged) plans that declare Tier 2+ ---
    phases.enter("plans-archive")
    adir = root / PLANS_ARCHIVE
    enforced_any = False
    # a de-dated slug shared by two archived plans is ambiguous — one review
    # must not clear both, so such slugs are excluded from matching
    dedated_counts: dict[str, int] = {}
    # (rel, text, tier, work ids) of every tiered plan — the join the
    # commit-anchored arm below needs
    tiered_plans: list[tuple[str, str, int, set[str]]] = []
    if adir.is_dir():
        plans = [p for p in sorted(adir.glob("*.md")) if not p.name.startswith("design-")]
        for p in plans:
            key = DATE_PREFIX.sub("", p.stem)
            dedated_counts[key] = dedated_counts.get(key, 0) + 1
        for p in plans:
            try:
                text = _unfenced(p.read_text(encoding="utf-8", errors="replace"))
            except OSError as exc:  # broken symlink, directory named *.md, …
                hard.append(f"{PLANS_ARCHIVE}/{p.name}: could not read: {exc}")
                continue
            if RETIRED_BINDING.search(text):
                soft.append(f"{PLANS_ARCHIVE}/{p.name}: 'review-binding:' is retired "
                            f"(lean pass) — a single attestation mode remains; "
                            f"digest binding is opt-in per REVIEW line")
            tier = plan_tier(text)
            if tier is None:
                soft.append(f"{PLANS_ARCHIVE}/{p.name}: no 'tier:' declaration "
                            f"— review presence not enforced for this plan")
                continue
            if tier < 2:
                continue
            if verified_template_plan(root, f'{PLANS_ARCHIVE}/{p.name}', text, update=update):
                soft.append(f'{PLANS_ARCHIVE}/{p.name}: pure template update verified by re-render')
                continue
            enforced_any = True
            if review_waived(text):
                soft += waiver_debt_notes(f"{PLANS_ARCHIVE}/{p.name}", text,
                                          WAIVED, "review-waived")
                continue
            unique = dedated_counts[DATE_PREFIX.sub("", p.stem)] == 1
            ids = _plan_work_ids(p.stem, text, include_dedated=unique)
            tiered_plans.append((f"{PLANS_ARCHIVE}/{p.name}", text, tier, ids))
            if not _cleared(passes, ids, tier):
                hard.append(no_clearing_review(f"{PLANS_ARCHIVE}/{p.name}", tier, ids))

    # the speckit path's plans: the decisions ledger is a note there too
    for rel, plan in record_files(root, ("spec-plan",)):
        ptext = _unfenced(plan.read_text(encoding="utf-8", errors="replace"))
        tier = plan_tier(ptext)
        if tier is None:
            hard.append(f"{rel}: no 'tier: N' declaration — "
                        f"the review, speckit and issue gates all key on it; a "
                        f"plan without a tier is off by omission (add the line, "
                        f"`/plan` puts it there)")
            continue
        if tier >= 2 and not DECISIONS_HEADING.search(ptext):
            soft.append(f"{rel}: no '## Decisions' section "
                        f"— decisions made in dialogue have no home here and do "
                        f"not survive a compaction (journal-state-plans.md, Plans)")
        if tier >= 2:  # the commit-anchored arm below joins on it too
            tiered_plans.append((rel, ptext, tier,
                                 _plan_work_ids(plan_stem(rel), ptext, include_dedated=False)))

    # the speckit path's plans never enter the archive — surface the same
    # presence question there as a note (finish.py is the hard stop)
    for name, tier, ids in speckit_unreviewed(root, passes):
        soft.append(no_clearing_review(f"{SPECS_DIR}/{name}", tier, ids)
                    + " — its tasks are all ticked; finish.py blocks on this")

    # ACTIVE plans this push carries. Waiting for the archive step means the
    # proof arrives after the merge it was supposed to gate — so Tier 3 is
    # enforced here, at the push, scoped to the plans this push actually
    # touches (paths_in_flight). Tier 2 keeps the archive-time threshold:
    # "forgot to archive on merge" and that design are indistinguishable and
    # silent, so the gap is at least made visible.
    active = [p for _rel, p in record_files(root, ("plan",))]
    in_flight = paths_in_flight(root) if base_error is None else None
    if in_flight is None:
        review_required = any(
            not rel.startswith(f"{PLANS_ACTIVE}/design-")
            and (plan_tier(text) or 0) >= 2 and not review_waived(text)
            for rel, text in record_texts(root, PLAN_KINDS) or [])
        if no_base and review_required:
            # a presence finding like the arms it disarms: hard on the merge
            # push, a note on a branch push (verification-independence.md)
            presence("no proper integration base — fetch origin/main (or the remote default branch); cannot bound the pushed range")
        soft.append(f"{IN_FLIGHT_UNKNOWN} — every active plan is treated as in flight")
        in_flight = {f"{PLANS_ACTIVE}/{p.name}" for p in active}
    phases.enter("stale_review")
    merged_issues = issues_on_integration(root)
    if (root / PLANS_ACTIVE).is_dir():
        active_tier2 = 0
        active_dedated = slug_counts(p.stem for p in active)
        for p in active:
            if p.name.startswith("design-"):
                continue
            try:
                text = _unfenced(p.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue  # unreadable active plan; the archive path diagnoses
            tier = plan_tier(text)
            # a plan that TALKS about its tier but never declares it sits outside
            # every tier-keyed gate (presence, spec-before-plan, issue-before-code)
            # — the third-party-plan-writer failure mode: the engine knows tiers,
            # not this grammar. Loud note, not hard: prose mentions are heuristic.
            if tier is None:
                # Off by omission was the escape: every tier-keyed duty (review
                # presence, spec-before-plan, issue-before-code) is silent for a
                # plan that declares no tier — observed downstream, two plans
                # without the line were invisible to every gate until someone
                # added it and two duties armed at once. An ACTIVE plan is a
                # plan by location; declaring its tier is not optional. Archived
                # plans stay a note (history is not re-litigated).
                hard.append(f"{PLANS_ACTIVE}/{p.name}: no 'tier: N' declaration — "
                            f"every tier-keyed gate (review presence, spec-before-"
                            f"plan, issue-before-code) is unarmed for this plan; a "
                            f"plan without a tier is off by omission. Declare it "
                            f"(risk-tiers.md), or move a non-plan out of the plan home")
                continue
            if tier < 2:
                continue
            if verified_template_plan(root, f'{PLANS_ACTIVE}/{p.name}', text, update=update):
                soft.append(f'{PLANS_ACTIVE}/{p.name}: pure template update verified by re-render')
                continue
            if tier == 2:
                active_tier2 += 1
            rel = f"{PLANS_ACTIVE}/{p.name}"
            if not DECISIONS_HEADING.search(text):
                soft.append(f"{rel}: no '## Decisions' section — decisions made in "
                            f"dialogue have no home in this plan and do not survive a "
                            f"compaction (journal-state-plans.md, Plans); add the "
                            f"ledger, even if it is empty for now")
            # the slug without its date names the plan too, when unambiguous —
            # as for archived plans (attest's `--work <slug>`)
            ids = _plan_work_ids(p.stem, text,
                                 include_dedated=active_dedated.get(DATE_PREFIX.sub("", p.stem), 0) == 1)
            tiered_plans.append((rel, text, tier, ids))
            if review_waived(text):
                soft += waiver_debt_notes(rel, text, WAIVED, "review-waived")
                continue
            # after the fact: a Tier 3 plan still active while commits claiming
            # its issue already sit on the integration branch was merged past
            # the process (a bypassed hook, a platform merge button) — hard,
            # whatever this push carries: nothing else would ever see it
            if (tier >= 3 and not _cleared(passes, ids, tier)
                    and _plan_issue_numbers(text) & merged_issues):
                hard.append(f"{rel}: tier {tier} work already merged — commits on the "
                            f"integration branch claim #{sorted(_plan_issue_numbers(text) & merged_issues)[0]}"
                            f" — without a clearing REVIEW; review it now and attest, or record "
                            f"the exception with a 'review-waived:' line")
                continue
            if rel not in in_flight:
                # somebody else's plan, sitting in the tree untouched by this
                # push — not this push's proof to produce
                continue
            if not _cleared(passes, ids, tier):
                presence(no_clearing_review(rel, min(tier, 3), ids)
                         + " — from Tier 2 on the proof is due before the merge")
                continue
            if merged_work(root, rel, passes, ids, tier):
                soft.append(_residue(rel))
            stale = stale_review(root, passes, ids, tier, in_flight, _reviewed_heads(passes, tier, known_work))
            if stale:
                presence(f"{rel}: {stale}")
        if active_tier2:
            soft.append(f"{active_tier2} active Tier 2 plan(s) in {PLANS_ACTIVE} — "
                        f"their review is due at the merge push; archive on merge")

    # the commit-anchored arm: what exists at every merge is the issue plus
    # the commits that CLAIM it (a closing trailer or the `… (#N)` subject —
    # a bare mention is somebody else's business, see issue_refs_in_range).
    # The tier still comes from the plan — a gate that invents its own tier
    # would be worse than the gap it closes — so a claimed issue without a
    # findable plan is a note, not a failure.
    phases.enter("stale_review-by-issue")
    for number in sorted(issue_refs_in_range(root) if base_error is None else ()):
        matching = [(rel, text, tier, ids) for rel, text, tier, ids in tiered_plans
                    if number in _plan_issue_numbers(text)]
        if not matching:
            if number not in _declared_anywhere(root):
                soft.append(f"a commit in the pushed range claims #{number}, but no "
                            f"plan declares that issue (neither in {PLANS_ACTIVE} nor in "
                            f"{SPECS_DIR}/*/{SPEC_PLAN}) — no tier to key on, so review "
                            f"presence is not enforced for it")
            # a plan below Tier 2 or a waived one declares it: nothing to enforce
            continue
        for rel, text, tier, ids in matching:
            if tier < 2 or review_waived(text):
                continue
            if not _cleared(passes, ids, tier):
                presence(f"a commit in the pushed range claims #{number} — "
                         + no_clearing_review(rel, min(tier, 3), ids))
                continue
            stale = stale_review(root, passes, ids, tier, in_flight, _reviewed_heads(passes, tier, known_work))
            if stale:
                presence(f"#{number} ({rel}): {stale}")

    # a standing block: the committed records of the pushed range, whatever
    # the tier (see standing_block_findings). `check` may read a directory
    # that is no repository at all — no records, no finding; the hook-side
    # `--standing-block` call is the one that refuses unreadable ones
    phases.enter("standing_block")
    for finding in standing_block_findings(root, refuse_unreadable=False):
        presence(finding)

    phases.enter("unhomed")
    hard.extend(_unhomed_plans(root))
    phases.leave()

    if not all_records and not enforced_any and not hard:
        soft.append("no REVIEW attestations yet — expected pre-adoption")
    return hard, soft


# The presence check above keys on .process-work/plans — a plan written
# anywhere else (a topic-triggered third-party skill with its own conventions,
# a stray docs/plans/) silently escapes it, and everything downstream (review
# attestation, archive ritual) never fires. This detector makes that bypass
# loud: a Tier 2+ declaration is the very opt-in the presence gate keys on, so
# one living outside the plan home is hard. Tier 0/1 documents are not plans
# in the gated sense and stay out of scope.
_UNHOMED_PRUNE = {".git", "node_modules", ".venv", "venv", "archive",
                  "__pycache__"}
_UNHOMED_SANCTIONED = (".process-work", "specs", "docs/process", ".github",
                       ".specify", ".claude")


def _declared_anywhere(root: Path) -> set[int]:
    """Issue numbers any plan declares — active, archived or a spec dir's,
    whatever its tier."""
    found: set[int] = set()
    for _rel, text in record_texts(root, ("plan", "plan-archive", "spec-plan")) or []:
        found |= _plan_issue_numbers(_unfenced(text))
    return found


def _gitignored(root: Path, rels: list[str]) -> set[str]:
    """The subset of `rels` git ignores. An ignored path is not part of the
    repository — most often another agent's worktree nested under the
    checkout, whose plans are in no commit yet failed the push of whoever
    pushed next (observed downstream). `.gitignore` stays the one owner of
    what belongs to the repo; an untracked plan that is NOT ignored stays in
    scope on purpose — a plan just written to the wrong place is what the
    scan exists for. Fails open: git absent or erroring ignores nothing."""
    if not rels:
        return set()
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "check-ignore", "-z", "--stdin"],
            input="\0".join(rels).encode(errors="surrogateescape"),
            capture_output=True, timeout=60, env=git_environment())
    except (OSError, subprocess.TimeoutExpired):
        return set()
    # 0 = some path ignored, 1 = none ignored, >1 = an error (fail open)
    if result.returncode > 1:
        return set()
    return {n for n in result.stdout.decode(errors="surrogateescape").split("\0") if n}


def _unhomed_plans(root: Path) -> list[str]:
    candidates: list[tuple[Path, str]] = []
    for p in sorted(root.rglob("*.md")):
        rel = p.relative_to(root)
        parts = rel.parts
        if any(part in _UNHOMED_PRUNE for part in parts):
            continue
        rel_s = str(rel).replace("\\", "/")
        if any(rel_s == s or rel_s.startswith(s + "/")
               for s in _UNHOMED_SANCTIONED):
            continue
        candidates.append((p, rel_s))
    ignored = _gitignored(root, [rel_s for _, rel_s in candidates])
    hard: list[str] = []
    for p, rel_s in candidates:
        if rel_s in ignored:
            continue
        try:
            text = _unfenced(p.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        tier = plan_tier(text)
        if tier is not None and tier >= 2:
            hard.append(
                f"{rel_s}: declares 'tier: {tier}' outside the plan home "
                f"— the review-presence gate only sees {PLANS_ACTIVE}; move the "
                f"plan there (or the spec to specs/), or fence the line if it "
                f"is a quotation")
    return hard


def standing_block_main(tips: list[str]) -> int:
    """`--standing-block <sha>[:<remote_sha>]…`: a pre-push hook's own check of
    the commits it sends to main, for a hook that reads git's ref lines
    (`<local_ref> <local_sha> <remote_ref> <remote_sha>`) and may end before
    the gate runner. exit 1 = a pushed commit carries a standing block."""
    root = Path(".").resolve()
    findings: list[str] = []
    for token in tips:
        tip, has_remote, remote_sha = token.partition(":")
        findings += standing_block_findings(root, tip, remote_sha=remote_sha if has_remote else None)
    for finding in sorted(set(findings)):
        print(f"review: {finding}", file=sys.stderr)
    return 1 if findings else 0


def main() -> int:
    if sys.argv[1:2] == ["--standing-block"]:
        return standing_block_main(sys.argv[2:])
    args = [a for a in sys.argv[1:] if a != "--full"]
    root = Path(args[0] if args else ".").resolve()
    if not root.is_dir():
        print(f"review: FAILED:\n  - root {root} is not a directory")
        return 1
    global REPORT_PHASES
    REPORT_PHASES = True
    hard, soft = check(root)
    for note in soft:
        print(f"review: note: {note}")
    if hard:
        print("review: FAILED:")
        for h in sorted(set(hard)):
            print(f"  - {h}")
        return 1
    print("review: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
