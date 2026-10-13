#!/usr/bin/env python3
"""news: the change log a reader without technical knowledge can follow.

One fragment per user-visible change, `news/<slug>.md`, written in the branch
that makes the change:

    type: new | improved | fixed
    issue: #123            (optional)

    One to three plain sentences: what is new, better or fixed — no file
    names, no jargon.

Fragments stay where they are; `render` rebuilds `NEWS.md` from all of them
every time. Parallel branches never touch the same file, and every merge route
works the same (the train and `finish.py` alike).

A fragment's date is the day it reached the integration branch (the first
commit there that added the file, following first parents, so a merge counts
as the day it was merged) — not the day it was written. A fragment not yet on
the integration branch is "Unreleased".

  news.py new --type new|improved|fixed --slug S [--issue N] "text"
  news.py check                 form of every fragment (advisory, never a gate)
  news.py render                write NEWS.md at the repo root
  news.py show [--since DATE]   entries newest first, for the digest

Optional `docs/process/news.local.json`:
  {"title": "News", "labels": {"new": "New", "improved": "Improved",
   "fixed": "Fixed"}, "unreleased": "Unreleased"}
Absent: English defaults. Present but malformed: an error naming the file.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling imports
import gate_modes  # noqa: E402
from process_git import git_environment  # noqa: E402

NEWS_DIR = "news"
OUTPUT = "NEWS.md"
CONFIG = "docs/process/news.local.json"
TYPES = ("new", "improved", "fixed")  # the order inside a month
MAX_TEXT = 600
SLUG = re.compile(r"^[a-z0-9-]+$")
TYPE_LINE = re.compile(r"^type:[ \t]*(\S+)[ \t]*$")
ISSUE_LINE = re.compile(r"^issue:[ \t]*#(\d+)[ \t]*$")
DEFAULTS = {"title": "News", "labels": {"new": "New", "improved": "Improved", "fixed": "Fixed"},
            "unreleased": "Unreleased"}


class NewsError(Exception):
    """Something the reader must be told by name; the CLI prints it and exits 1."""


@dataclass(frozen=True)
class Entry:
    name: str  # file name inside news/
    type: str
    issue: str | None  # "#123"
    text: str  # whitespace-collapsed, one line
    date: str | None  # YYYY-MM-DD on the integration branch; None: unreleased


# --- configuration -----------------------------------------------------------

def load_config(root: Path) -> dict:
    """The effective configuration: the defaults, overridden by the optional file."""
    cfg = {"title": DEFAULTS["title"], "labels": dict(DEFAULTS["labels"]), "unreleased": DEFAULTS["unreleased"]}
    path = root / CONFIG
    if not path.is_file():
        return cfg
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise NewsError(f"{CONFIG}: unreadable or not JSON ({exc})") from exc
    if not isinstance(data, dict):
        raise NewsError(f"{CONFIG}: must be a JSON object")
    unknown = sorted(set(data) - set(DEFAULTS))
    if unknown:
        raise NewsError(f"{CONFIG}: unknown key(s) {', '.join(unknown)} (allowed: title, labels, unreleased)")
    for key in ("title", "unreleased"):
        if key in data:
            if not (isinstance(data[key], str) and data[key].strip()):
                raise NewsError(f"{CONFIG}: '{key}' must be a non-empty string")
            cfg[key] = data[key].strip()
    if "labels" in data:
        labels = data["labels"]
        if not isinstance(labels, dict):
            raise NewsError(f"{CONFIG}: 'labels' must be an object with the keys {', '.join(TYPES)}")
        for key, value in labels.items():
            if key not in TYPES:
                raise NewsError(f"{CONFIG}: unknown label '{key}' (allowed: {', '.join(TYPES)})")
            if not (isinstance(value, str) and value.strip()):
                raise NewsError(f"{CONFIG}: label '{key}' must be a non-empty string")
            cfg["labels"][key] = value.strip()
    return cfg


# --- fragments ---------------------------------------------------------------

def parse_fragment(content: str) -> tuple[str, str | None, str]:
    """(type, issue, text) of one fragment's content; ValueError says what is wrong."""
    lines = content.lstrip("﻿").splitlines()
    first = TYPE_LINE.match(lines[0]) if lines else None
    if not first:
        raise ValueError("first line must be `type: new|improved|fixed`")
    kind = first.group(1)
    if kind not in TYPES:
        raise ValueError(f"unknown type '{kind}' (allowed: {', '.join(TYPES)})")
    rest = lines[1:]
    issue = None
    if rest and rest[0].lower().startswith("issue:"):
        m = ISSUE_LINE.match(rest[0])
        if not m:
            raise ValueError("the issue line must read `issue: #N`")
        issue = f"#{m.group(1)}"
        rest = rest[1:]
    text = " ".join(" ".join(rest).split())
    if not text:
        raise ValueError("no text after the header")
    if len(text) > MAX_TEXT:
        raise ValueError(f"text is {len(text)} characters (at most {MAX_TEXT})")
    return kind, issue, text


def has_base(root: Path) -> bool:
    return gate_modes.base_ref(root) is not None


def _first_added(root: Path) -> dict[str, str]:
    """file name -> date (YYYY-MM-DD) of the first commit on the integration
    branch that added news/<file>. First parents only: a merge adds the file on
    the day it is merged, however old the branch's own commits are."""
    base = gate_modes.base_ref(root)
    if base is None:
        return {}
    proc = subprocess.run(
        ["git", "-C", str(root), "-c", "core.quotepath=off", "log", "--first-parent", "--no-renames",
         "--diff-filter=A", "--reverse", "--format=%x01%cs", "--name-only", base, "--", f"{NEWS_DIR}/"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", env=git_environment())
    if proc.returncode != 0:
        return {}
    prefix = f"{NEWS_DIR}/"
    found: dict[str, str] = {}
    for chunk in proc.stdout.split("\x01")[1:]:
        date, *names = chunk.splitlines()
        for name in names:
            if name.startswith(prefix) and "/" not in name[len(prefix):]:
                found.setdefault(name[len(prefix):], date.strip())
    return found


def collect(root: Path) -> tuple[list[Entry], list[str]]:
    """(entries, problems) of every fragment under news/, by file name. A
    problem reads `news/<file>: <what is wrong>`."""
    ndir = root / NEWS_DIR
    if not ndir.is_dir():
        return [], []
    names = sorted(p.name for p in ndir.iterdir() if not p.name.startswith("."))
    dates = _first_added(root) if names else {}
    entries: list[Entry] = []
    problems: list[str] = []
    for name in names:
        path = ndir / name
        rel = f"{NEWS_DIR}/{name}"
        stem = name[:-3] if name.endswith(".md") else ""
        if not path.is_file() or not SLUG.match(stem):
            problems.append(f"{rel}: must be a file named <slug>.md with a slug of a-z, 0-9 and '-'")
            continue
        try:
            kind, issue, text = parse_fragment(path.read_text(encoding="utf-8"))
        except UnicodeDecodeError:
            problems.append(f"{rel}: not UTF-8")
        except OSError as exc:
            problems.append(f"{rel}: unreadable ({exc})")
        except ValueError as exc:
            problems.append(f"{rel}: {exc}")
        else:
            entries.append(Entry(name, kind, issue, text, dates.get(name)))
    return entries, problems


# --- output ------------------------------------------------------------------

def _suffix(entry: Entry) -> str:
    return f" ({entry.issue})" if entry.issue else ""


def render_text(entries: list[Entry], cfg: dict) -> str:
    """NEWS.md: Unreleased first, then months newest first; inside a section by
    type (new, improved, fixed), then date, then file name."""
    out = [f"# {cfg['title']}", ""]
    sections = [(cfg["unreleased"], [e for e in entries if e.date is None])]
    for month in sorted({e.date[:7] for e in entries if e.date}, reverse=True):
        sections.append((month, [e for e in entries if e.date and e.date[:7] == month]))
    for heading, group in sections:
        if not group:
            continue
        out += [f"## {heading}", ""]
        for kind in TYPES:
            rows = sorted((e for e in group if e.type == kind), key=lambda e: (e.date or "", e.name))
            if rows:
                out += [f"### {cfg['labels'][kind]}", ""]
                out += [f"- {e.date + ' — ' if e.date else ''}{e.text}{_suffix(e)}" for e in rows]
                out.append("")
    return "\n".join(out).rstrip("\n") + "\n"


def show_lines(entries: list[Entry], cfg: dict, since: str | None = None) -> list[str]:
    """Entries newest first: unreleased on top, then by day descending; inside
    a day by type, then file name. With `since`, only entries dated on or after
    it — every unreleased one stays, it is newer than any date."""
    keep = sorted((e for e in entries if e.date is None or since is None or e.date >= since),
                  key=lambda e: (TYPES.index(e.type), e.name))
    keep.sort(key=lambda e: e.date or "9999-99-99", reverse=True)  # stable: ties keep type/name order
    return [f"{e.date or cfg['unreleased']}  {cfg['labels'][e.type]}  {e.text}{_suffix(e)}" for e in keep]


# --- commands ----------------------------------------------------------------

def _root() -> Path:
    proc = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True,
                          env=git_environment())
    if proc.returncode != 0:
        raise NewsError("not inside a git repository")
    return Path(proc.stdout.strip())


def cmd_new(root: Path, args: argparse.Namespace) -> int:
    if not SLUG.match(args.slug):
        raise NewsError(f"slug '{args.slug}' must consist of a-z, 0-9 and '-'")
    issue = None
    if args.issue:
        m = re.fullmatch(r"#?(\d+)", args.issue.strip())
        if not m:
            raise NewsError(f"--issue '{args.issue}' must be a number")
        issue = m.group(1)
    body = args.text.strip()
    content = f"type: {args.type}\n" + (f"issue: #{issue}\n" if issue else "") + f"\n{body}\n"
    try:
        parse_fragment(content)  # the one definition of a valid fragment
    except ValueError as exc:
        raise NewsError(str(exc)) from exc
    path = root / NEWS_DIR / f"{args.slug}.md"
    if path.exists():
        raise NewsError(f"{NEWS_DIR}/{args.slug}.md exists already — pick another slug")
    path.parent.mkdir(exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    print(f"{NEWS_DIR}/{args.slug}.md written")
    return 0


def cmd_check(root: Path, _args: argparse.Namespace) -> int:
    load_config(root)
    entries, problems = collect(root)
    for p in problems:
        print(p)
    if problems:
        print(f"{len(problems)} fragment(s) need a fix (advisory)")
        return 1
    print(f"{len(entries)} fragment(s) ok")
    return 0


def _entries_or_abort(root: Path) -> list[Entry]:
    entries, problems = collect(root)
    if problems:
        raise NewsError("malformed fragment(s):\n" + "\n".join(f"  {p}" for p in problems))
    return entries


def cmd_render(root: Path, _args: argparse.Namespace) -> int:
    cfg = load_config(root)
    entries = _entries_or_abort(root)
    if entries and not has_base(root):
        print("news: no integration branch found (origin/HEAD, origin/main, origin/master) — "
              f"every fragment counts as {cfg['unreleased']}", file=sys.stderr)
    (root / OUTPUT).write_text(render_text(entries, cfg), encoding="utf-8", newline="\n")
    print(f"{OUTPUT} written ({len(entries)} entr{'y' if len(entries) == 1 else 'ies'})")
    return 0


def cmd_show(root: Path, args: argparse.Namespace) -> int:
    if args.since is not None:
        try:
            _dt.date.fromisoformat(args.since)
        except ValueError as exc:
            raise NewsError(f"--since '{args.since}' must be a date YYYY-MM-DD") from exc
    cfg = load_config(root)
    for line in show_lines(_entries_or_abort(root), cfg, args.since):
        print(line)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="user-readable change log from news/ fragments")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_new = sub.add_parser("new", help="create news/<slug>.md")
    p_new.add_argument("--type", required=True, choices=TYPES)
    p_new.add_argument("--slug", required=True)
    p_new.add_argument("--issue")
    p_new.add_argument("text")
    sub.add_parser("check", help="validate all fragments (advisory)")
    sub.add_parser("render", help=f"write {OUTPUT}")
    p_show = sub.add_parser("show", help="print entries, newest first")
    p_show.add_argument("--since", metavar="YYYY-MM-DD")
    args = ap.parse_args(argv)
    try:
        return {"new": cmd_new, "check": cmd_check, "render": cmd_render, "show": cmd_show}[args.cmd](
            _root(), args)
    except NewsError as exc:
        print(f"news: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
