#!/usr/bin/env python3
"""optimize — the process-improvement record: one file per experiment.

    optimize.py new --title T --mechanism M [--implementer WHO] [--responsible WHO] [--issues "#1, #2"]
    optimize.py move OPT-0001 <state> --who WHO --because TEXT
    optimize.py review OPT-0001 --who WHO --verdict pass|block --because TEXT
    optimize.py check [--json]          every record and the mandate; exit 1 on a problem
    optimize.py status                  what a running experiment needs now (expiry, budget)
    optimize.py active FLAG [--issue N] [--tier T] [--class C]
                                        exit 0 while an experiment switches FLAG on for this work
    optimize.py list

A record lives in `.process-work/optimizations/OPT-NNNN-<slug>.md` and is
the one durable place of an improvement: observation, hypothesis,
placement, trial, limits, criteria, generality, rollback, result, decision
and a dated log. Sessions restart; the record does not
(`docs/process/optimization.md` is the contract).

States: proposed → designed → piloting → (stopped →) evaluating →
adopted | rejected | rolled-back | superseded; proposed or designed →
rejected. `move` checks what a state needs before it writes it:

- `piloting` needs the mandate (`docs/process/optimization.local.json`),
  filled Trial, Limits, Criteria, Generality and Rollback, `select`,
  `until` within the mandate's `max_pilot_days`, both budgets, and a
  `REVIEWED … pass` line on exactly these terms by someone other than the
  implementer (and no block on them). It writes `FROZEN <date> <who>:
  terms=<hash> max_pilot_days=<n> steward_may=<rights>`.
- `adopted` is the owner's, or the steward's where the mandate (as frozen)
  names `adopt` in `steward_may`; never the implementer's.
- `stopped` and `evaluating` are never refused (the safe direction), and
  `rolled-back` stays open even when the record or the mandate is broken.

**The record is plain Markdown** — no HTML, no comment, no code fence, no
line break but \n — so what this tool reads is what a reader sees, and the
first line `## Result` is a heading wherever it stands.

**The freeze is byte-exact.** The terms are everything above `## Result` —
the header, Observation, Hypothesis, Placement, Trial, Limits, Criteria,
Generality, Rollback — except the header fields that must change (`state`,
`spent-tokens`, `spent-hours`, `superseded-by`, each checked to hold only
its value). Any change above `## Result` breaks the freeze. Below it only
`## Result`, `## Decision` and `## Log` are headings (also inside a quote
or a list), and the Log holds machine-written lines only. An experiment
does not ease its own criteria.

One set of rules: `move` judges the record as it would be written with the
same `problems()` that `check` and `active` apply afterwards — who started
it, who reviewed which terms (only reviews before the freeze count; a block
is not outvoted), the start not dated in the future, `until` within the
frozen mandate and, while it runs, within the current one. Names are
compared without case or spacing.

**History.** With git, one pass over the records directory indexes every
committed version by its OPT number, merges included. The Log is
append-only — every committed version's Log is a prefix of today's, so a
moved block, an edited FROZEN line, a record "un-run" or replaced under its
number is seen — every committed version that ran carries today's terms,
and a record that ran must not vanish. What a file check cannot see:
rewritten history (amend, rebase, force-push) and a shallow clone; and names
are self-declared (the owner's sample is the control for that).

`active` is how a mechanism under trial asks whether to behave the new
way: exactly one `piloting` record carries the flag, nothing above is
wrong with it or with the records' history, today is not past `until`, and
the work matches `select` (`issues=12,15 tiers=1,2 classes=mechanical
parity=odd`, or `all`; a constraint the caller cannot answer does not
match). Every doubt reads as inactive.

Not a gate (yet): the rule is enforced where it is used — `active` turns a
tampered experiment off, `move` refuses. A project may register `check` in
`docs/process/gates.local.json`. Read-only except `new`, `move` and
`review`, which write the record and nothing else (no commit). Stdlib only.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

sys.dont_write_bytecode = True

RECORDS = ".process-work/optimizations"
MANDATE = "docs/process/optimization.local.json"
STATES = ("proposed", "designed", "piloting", "stopped", "evaluating",
          "adopted", "rejected", "rolled-back", "superseded")
TERMINAL = ("adopted", "rejected", "rolled-back", "superseded")
MOVES = {
    "proposed": ("designed", "rejected"),
    "designed": ("piloting", "rejected", "proposed"),
    "piloting": ("stopped", "evaluating"),
    "stopped": ("evaluating", "rolled-back"),
    "evaluating": ("adopted", "rejected", "rolled-back", "superseded"),
}
# turning an experiment off is never blocked — not by a broken record, not by
# a broken mandate, not by a missing right: it is the safe direction
SAFE_MOVES = ("stopped", "evaluating")
PLACEMENTS = ("core", "module", "config", "project")
# what each state needs filled, cumulative along the path
NEEDS = {
    "designed": ("Observation", "Hypothesis", "Placement"),
    "piloting": ("Trial", "Limits", "Criteria", "Generality", "Rollback"),
    "adopted": ("Result", "Decision"),
    "rejected": ("Decision",),
    "rolled-back": ("Decision",),
    "superseded": ("Decision",),
}
# header fields that change while the terms stay frozen
MUTABLE_FIELDS = ("state", "spent-tokens", "spent-hours", "superseded-by")
RESULT_LINE = "## Result"
TAIL_HEADINGS = ("Result", "Decision", "Log")
SELECT_KEYS = ("issues", "tiers", "classes", "parity")
RIGHTS = ("start", "roll-back", "adopt", "reject")
# stopping is nobody's right to withhold (the safe direction): not in steward_may
MANDATE_DEFAULTS = {"max_pilot_days": 30, "steward_may": ["start", "roll-back"]}

FIELD = re.compile(r"^(?:[-*+][ \t]+)?([a-z][a-z-]*)[ \t]*:[ \t]*(.*?)[ \t]*$")
HEADING = re.compile(r"^##[ \t]+(.+?)[ \t]*$", re.MULTILINE)
# a line a Markdown reader may render as a heading, once quote and list
# markers are peeled off: ATX (up to three spaces in) or a setext underline
CONTAINER = re.compile(r"^[ \t]{0,3}(?:>[ \t]?|[-*+][ \t]+|\d{1,9}[.)][ \t]+)")
ATX = re.compile(r"^ {0,3}#{1,6}(?:[ \t]|$)")
SETEXT = re.compile(r"^ {0,3}(?:=+|-+)[ \t]*$")
LOG_LINE = re.compile(r"^- (\d{4}-\d{2}-\d{2}) ([^:\s][^:]*?): ([a-z-]+)\b(.*)$")
REVIEWED = re.compile(r"^- REVIEWED (\d{4}-\d{2}-\d{2}) ([^:]+?): (pass|block) terms=([0-9a-f]{12})\b(.*)$")
FROZEN = re.compile(r"^- FROZEN (\d{4}-\d{2}-\d{2}) ([^:]+?): terms=([0-9a-f]{12})"
                    r"(?: max_pilot_days=(\d+))?(?: steward_may=([a-z,-]*))?[ \t]*$")
PLACEHOLDER = re.compile(r"^(?:todo\b.*|tbd\b.*|…|\.\.\.|-|n/a)?$", re.IGNORECASE)
INLINE_CODE = re.compile(r"`+[^`\n]*`+")
# the record is plain Markdown: no HTML (comments, tags), no code fences —
# nothing a renderer shows differently from the text the tool reads
HTML = re.compile(r"<(?!(?:https?|mailto):)[A-Za-z!/?]")
FENCE = re.compile(r"^[ \t]*(?:`{3,}|~{3,})")
# only \n (and \r\n) break a line; anything else a reader might take for a break is refused
ODD_BREAKS = re.compile("[\v\f\x1c\x1d\x1e\x85  ]|\r(?!\n)")
NAME = re.compile(r"^OPT-(\d{4})-[a-z0-9-]+\.md$")
MUTABLE_VALUE = {
    "state": lambda v: v in STATES,
    "spent-tokens": lambda v: _number(v) is not None or v == "0",
    "spent-hours": lambda v: _number(v) is not None or v == "0",
    "superseded-by": lambda v: re.fullmatch(r"OPT-\d{4}", v) is not None,
}


# --- reading -------------------------------------------------------------
def records_dir(root: Path) -> Path:
    return root / RECORDS


def record_files(root: Path) -> list[Path]:
    d = records_dir(root)
    return sorted(p for p in d.glob("OPT-*.md") if p.is_file()) if d.is_dir() else []


def norm(name: str) -> str:
    """A person or role as compared: case and spacing do not make a second person."""
    return " ".join(str(name).casefold().split())


def _lines(text: str) -> list[str]:
    return text.replace("\r\n", "\n").split("\n")


def _split(text: str) -> tuple[list[str], list[str] | None]:
    """(lines above the first `## Result` line, lines from it) — None for the
    tail when the record has no `## Result` line yet. In a plain record (no
    HTML, no fence, no odd line break) that line is a heading wherever it is."""
    lines = _lines(text)
    for i, line in enumerate(lines):
        if line.rstrip(" \t") == RESULT_LINE:
            return lines[:i], lines[i:]
    return lines, None


def _header_end(lines: list[str]) -> int:
    return next((i for i, line in enumerate(lines) if line.startswith("## ")), len(lines))


def terms_text(text: str) -> str:
    """What the freeze covers, byte for byte: everything above `## Result`
    but the mutable header fields; trailing spaces and tabs and line endings
    normalised, nothing else."""
    above, _tail = _split(text)
    end = _header_end(above)
    kept = []
    for i, line in enumerate(above):
        if i < end:
            m = FIELD.match(line)
            if m and m.group(1) in MUTABLE_FIELDS:
                continue
        kept.append(line.rstrip(" \t"))
    return "\n".join(kept).strip("\n")


def terms_hash(rec_or_text) -> str:
    text = rec_or_text["raw"] if isinstance(rec_or_text, dict) else rec_or_text
    return hashlib.sha256(terms_text(text).encode("utf-8")).hexdigest()[:12]


def _peeled(line: str) -> str:
    while True:
        m = CONTAINER.match(line)
        if not m:
            return line
        line = line[m.end():]


def _plain_problems(text: str) -> list[str]:
    out = []
    if ODD_BREAKS.search(text):
        out.append("only \\n or \\r\\n break a line — a lone \\r, \\v, \\f, U+2028 and kin are refused")
    for line in _lines(text):
        if FENCE.match(line):
            out.append("the record is plain Markdown — no code fence")
            break
    for line in _lines(text):
        if HTML.search(INLINE_CODE.sub("", line)):
            out.append("the record is plain Markdown — no HTML, no comment (inline code is fine)")
            break
    return out


def parse(text: str) -> dict:
    """{"raw", "title", "fields", "sections", "log", "log_lines", "reviews",
    "frozen", "strict"}. A record is plain Markdown — no HTML, no comment, no
    code fence, no odd line break — so what the tool reads is what a reader
    sees. The header and the Log are machine-written lines."""
    strict: list[str] = _plain_problems(text)
    above, tail = _split(text)
    end = _header_end(above)
    title = ""
    fields: dict[str, str] = {}
    for line in above[:end]:
        if line.startswith("# ") and not title:
            title = line[2:].strip()
            continue
        m = FIELD.match(line)
        if m:
            if m.group(1) in fields:
                strict.append(f"header field {m.group(1)}: appears twice")
            else:
                fields[m.group(1)] = m.group(2)
        elif line.strip():
            strict.append(f"the header holds `key: value` lines only (found {line.strip()[:40]!r})")
    for key, ok in MUTABLE_VALUE.items():
        if key in fields and not ok(fields[key].strip()):
            strict.append(f"{key}: {fields[key][:40]!r} is not a valid value — it changes outside the freeze, "
                          f"so it carries nothing else")
    sections: dict[str, str] = {}
    body_text = "\n".join(above)
    for i, m in enumerate(marks := list(HEADING.finditer(body_text))):
        stop = marks[i + 1].start() if i + 1 < len(marks) else len(body_text)
        name = m.group(1).strip()
        if name in sections:
            strict.append(f"## {name} appears twice")
            continue
        sections[name] = body_text[m.end():stop].strip("\n")
    log_lines: list[str] = []
    if tail is not None:
        current = None
        seen: set[str] = set()
        for k, line in enumerate(tail):
            prev = _peeled(tail[k - 1]) if k else ""
            bare = line.rstrip(" \t")
            if bare.startswith("## ") and bare[3:].strip() in TAIL_HEADINGS and bare == f"## {bare[3:].strip()}":
                name = bare[3:].strip()
                if name in seen:
                    strict.append(f"## {name} appears twice")
                seen.add(name)
                current = name
                sections.setdefault(name, "")
                continue
            peeled = _peeled(line)
            prev_is_text = bool(prev.strip()) and not CONTAINER.match(tail[k - 1]) and not SETEXT.match(prev)
            if ATX.match(peeled) or (SETEXT.match(line) and prev_is_text):
                strict.append(f"below {RESULT_LINE} only Result, Decision and Log are headings "
                              f"(found {line.strip()[:40]!r})")
                continue
            if current == "Log":
                if not line.strip():
                    continue
                if FROZEN.match(line) or REVIEWED.match(line) or (
                        (lm := LOG_LINE.match(line)) and lm.group(3) in STATES):
                    log_lines.append(line.rstrip(" \t"))
                else:
                    strict.append(f"the Log holds machine-written lines only (found {line.strip()[:40]!r})")
            elif current:
                sections[current] = (sections[current] + "\n" + line).strip("\n")
    log, reviews, frozen = [], [], []
    for pos, line in enumerate(log_lines):
        if m := FROZEN.match(line):
            frozen.append({"pos": pos, "date": m.group(1), "who": m.group(2).strip(), "terms": m.group(3),
                           "line": line,
                           "max_pilot_days": int(m.group(4)) if m.group(4) else None,
                           "steward_may": m.group(5).split(",") if m.group(5) else
                           ([] if m.group(5) == "" else None)})
        elif m := REVIEWED.match(line):
            reviews.append({"pos": pos, "date": m.group(1), "who": m.group(2).strip(),
                            "verdict": m.group(3), "terms": m.group(4)})
        elif m := LOG_LINE.match(line):
            log.append({"pos": pos, "date": m.group(1), "who": m.group(2).strip(), "state": m.group(3),
                        "rest": m.group(4).strip()})
    return {"raw": text, "title": title, "fields": fields, "sections": sections, "log": log,
            "log_lines": log_lines, "reviews": reviews, "frozen": frozen,
            "strict": list(dict.fromkeys(strict))}


def filled(body: str | None) -> bool:
    """A section counts once it says something: not empty, not only
    placeholders — a paragraph that opens with TODO or TBD is one, however
    many lines it runs."""
    if not body:
        return False
    for para in re.split(r"\n[ \t]*\n", "\n".join(_lines(body))):
        first = para.strip().splitlines()[0].strip().lstrip("-*+ ").strip() if para.strip() else ""
        if first and not PLACEHOLDER.match(first):
            return True
    return False


def parse_select(value: str) -> dict[str, set[str]] | None:
    """`issues=12,15 tiers=1,2 classes=mechanical parity=odd` or `all` → {key:
    values}; None when malformed (an unreadable selection selects nothing)."""
    value = value.strip()
    if value == "all":
        return {}
    if not value:
        return None
    out: dict[str, set[str]] = {}
    for token in value.split():
        key, eq, vals = token.partition("=")
        items = {v.strip().lstrip("#") for v in vals.split(",") if v.strip()}
        if not eq or key not in SELECT_KEYS or key in out or not items:
            return None
        if key == "parity" and not items <= {"odd", "even"}:
            return None
        if key in ("issues", "tiers") and not all(v.isdigit() for v in items):
            return None
        out[key] = items
    return out


def selects(select: dict[str, set[str]], *, issue: int | None, tier: int | None,
            klass: str | None) -> bool:
    if "issues" in select and (issue is None or str(issue) not in select["issues"]):
        return False
    if "tiers" in select and (tier is None or str(tier) not in select["tiers"]):
        return False
    if "classes" in select and (klass is None or klass not in select["classes"]):
        return False
    return not ("parity" in select and (
        issue is None or ("odd" if issue % 2 else "even") not in select["parity"]))


def _date(value: str) -> _dt.date | None:
    try:
        return _dt.date.fromisoformat(value.strip())
    except ValueError:
        return None


def _number(value: str | None) -> float | None:
    try:
        n = float(str(value).replace("_", "").replace(",", ""))
    except (TypeError, ValueError):
        return None
    return n if n > 0 and n == n and n != float("inf") else None


# --- mandate -------------------------------------------------------------
def load_mandate(root: Path) -> tuple[dict | None, str | None]:
    """(mandate with defaults, problem). No file: (None, None) — analysis is
    allowed without a mandate, a pilot is not."""
    f = root / MANDATE
    if not f.is_file():
        return None, None
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return None, f"{MANDATE}: unreadable ({exc})"
    if not isinstance(data, dict):
        return None, f"{MANDATE}: must be a mapping"
    out = {**MANDATE_DEFAULTS, **data}
    days = out.get("max_pilot_days")
    if not isinstance(days, int) or isinstance(days, bool) or days < 1:
        return None, f"{MANDATE}: max_pilot_days must be a positive integer"
    may = out.get("steward_may")
    if not isinstance(may, list) or not all(isinstance(x, str) for x in may):
        return None, f"{MANDATE}: steward_may must be a list of strings"
    unknown = sorted(set(may) - set(RIGHTS))
    if unknown:
        return None, f"{MANDATE}: steward_may names unknown right(s) {', '.join(unknown)}"
    return out, None


def may_move(who: str, state: str, rec: dict, steward_may: list[str], from_state: str) -> str | None:
    """Why `who` may not move the record to `state` under the delegated
    `steward_may` (concept: decision rights); None when allowed. Roles are
    the literal tokens `owner` and `steward`."""
    who = norm(who)
    implementer = norm(rec["fields"].get("implementer", ""))
    if state in ("piloting", "adopted") and implementer and who == implementer:
        return f"{who} implements this change and cannot {'start' if state == 'piloting' else 'adopt'} it"
    if state in ("proposed", "designed", "stopped", "evaluating"):
        return None
    right = {"piloting": "start", "adopted": "adopt", "rejected": "reject",
             "rolled-back": "roll-back", "superseded": "reject"}[state]
    if who == "owner":
        return None
    if state == "rejected" and from_state in ("proposed", "designed"):
        return None  # declining a proposal is anyone's
    if who == "steward" and right in steward_may:
        return None
    return (f"{state} needs the owner, or the steward where the mandate's steward_may names "
            f"{right!r} (it names: {', '.join(steward_may) or 'nothing'})")


# --- history ---------------------------------------------------------------
def _git(root: Path, *args: str) -> str | None:
    try:
        r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout.decode("utf-8", "surrogateescape") if r.returncode == 0 else None


def history_index(root: Path) -> dict[str, dict] | None:
    """{OPT number: {"versions": [(commit, Log lines, terms hash or None if the
    version had not run, FROZEN date, commit date)], "last": (commit, path,
    state)}} over every committed version of every record — one pass over the
    records directory, merges included (-m), so a rename, a renumbering or a
    record added in a merge is seen; None when git cannot say."""
    if _git(root, "rev-parse", "--verify", "-q", "HEAD") is None:
        return None
    out = _git(root, "log", "-m", "--name-status", "-z", "--format=\x01%H\x02%ct", "--", RECORDS)
    if out is None:
        return None
    seen: list[tuple[str, int, str]] = []  # newest first
    tokens = out.split("\0")
    i, sha, ct = 0, "", 0
    while i < len(tokens):
        tok = tokens[i].lstrip("\n")
        if tok.startswith("\x01"):
            sha, _, stamp = tok[1:].partition("\x02")
            ct = int(stamp) if stamp.isdigit() else 0
            i += 1
            continue
        if not tok:
            i += 1
            continue
        status = tok
        if status[:1] in ("R", "C"):
            path = tokens[i + 2] if i + 2 < len(tokens) else ""
            i += 3
        else:
            path = tokens[i + 1] if i + 1 < len(tokens) else ""
            i += 2
        if status[:1] != "D" and path:
            seen.append((sha, ct, path))
    index: dict[str, dict] = {}
    shown: set[tuple[str, str]] = set()
    for sha, ct, path in seen:
        if (sha, path) in shown:
            continue
        shown.add((sha, path))
        m = NAME.match(Path(path).name)
        if not m or not path.startswith(RECORDS + "/"):
            continue
        text = _git(root, "show", f"{sha}:{path}")
        if text is None:
            continue
        rec = parse(text)
        entry = index.setdefault(m.group(1), {"versions": [], "last": None})
        if entry["last"] is None:
            entry["last"] = (sha, path, rec["fields"].get("state", ""))
        entry["versions"].append((sha, rec["log_lines"], terms_hash(rec) if rec["frozen"] else None,
                                  rec["frozen"][0]["date"] if rec["frozen"] else None,
                                  _dt.datetime.fromtimestamp(ct, _dt.timezone.utc).date()))
    return index


def history_problems(index: dict | None, path: Path, rec: dict) -> list[str]:
    """The Log is append-only and the terms stay frozen: every committed
    version's Log is a prefix of today's, and every committed version that
    ran carries today's terms. A moved block, an edited FROZEN line, a record
    "un-run" or replaced under its number — all break the prefix."""
    if not index:
        return []
    m = NAME.match(path.name)
    entry = index.get(m.group(1)) if m else None
    if entry is None:
        return []
    out = []
    current_terms = terms_hash(rec)
    now = rec["log_lines"]
    for sha, lines, terms, fdate, cdate in entry["versions"]:
        if now[:len(lines)] != lines:
            out.append(f"the Log is append-only — commit {sha[:10]} has lines today's Log does not "
                       f"start with")
        if terms is not None and terms != current_terms:
            out.append(f"terms differ from the version frozen in commit {sha[:10]} "
                       f"(then {terms}, now {current_terms}) — an experiment does not change its own criteria")
        frozen_day = _date(fdate) if fdate else None
        if frozen_day and frozen_day > cdate + _dt.timedelta(days=1):
            out.append(f"FROZEN {fdate} was committed on {cdate} — a start is not dated ahead")
    return list(dict.fromkeys(out))


def vanished(index: dict | None, parsed: dict[Path, dict]) -> list[str]:
    """A record that ran (a committed version carried FROZEN) must still exist."""
    if not index:
        return []
    present = {NAME.match(p.name).group(1) for p in parsed if NAME.match(p.name)}
    out = []
    for num, entry in sorted(index.items()):
        ran = [v for v in entry["versions"] if v[2] is not None]
        if ran and num not in present:
            out.append(f"OPT-{num} ran (frozen in commit {ran[-1][0][:10]}) and is gone — "
                       f"records are never deleted; every running experiment is off")
    return out


# --- judging -------------------------------------------------------------
def _reached(state: str, rec: dict) -> list[str]:
    """The states a record in `state` has passed through (for what it must carry):
    a rejected proposal never ran; a rejected trial did, and keeps its terms."""
    if state == "proposed":
        return ["proposed"]
    if state == "designed":
        return ["proposed", "designed"]
    if state == "rejected" and not any(e["state"] == "piloting" for e in rec["log"]):
        return []  # the log line's reason is the decision of a proposal that never ran
    return ["proposed", "designed", "piloting"] + ([state] if state != "piloting" else [])


def _pilot_terms(rec: dict) -> list[str]:
    f = rec["fields"]
    out = []
    if parse_select(f.get("select", "")) is None:
        out.append("select: missing or malformed (issues=… tiers=… classes=… parity=odd|even, or all)")
    if _date(f.get("until", "")) is None:
        out.append("until: missing or not YYYY-MM-DD")
    for key in ("budget-tokens", "budget-hours"):
        if _number(f.get(key)) is None:
            out.append(f"{key}: missing or not a positive number")
    return out


def problems(root: Path, path: Path, rec: dict, mandate: dict | None, *,
             history: dict | None = None, today: _dt.date | None = None) -> list[str]:
    """Everything wrong with one record, re-derived from the record itself —
    every rule `move` checks when it writes a transition is checked again here,
    so a hand-written state, log line or freeze gains nothing."""
    today = today or _dt.date.today()
    out: list[str] = list(rec["strict"])
    f = rec["fields"]
    if not NAME.match(path.name):
        out.append("file name must be OPT-NNNN-<slug>.md")
    state = f.get("state", "")
    if state not in STATES:
        return out + [f"state {state!r} is not one of {', '.join(STATES)}"]
    for key in ("responsible", "mechanism"):
        if not filled(f.get(key)):
            out.append(f"{key}: missing")
    if rec["log"] and rec["log"][-1]["state"] != state:
        out.append(f"state is {state} but the log's last transition is {rec['log'][-1]['state']}")
    path_states = _reached(state, rec)
    for need_state in path_states:
        for name in NEEDS.get(need_state, ()):
            if not filled(rec["sections"].get(name)):
                out.append(f"{state} needs a filled ## {name}")
    implementer = norm(f.get("implementer", ""))
    if "designed" in path_states:
        if f.get("placement", "").strip() not in PLACEMENTS:
            out.append(f"placement must be one of {', '.join(PLACEMENTS)}")
        if not filled(f.get("implementer")):
            out.append("implementer: missing — the review and the decision must know whose change it is")
    if "piloting" not in path_states and rec["frozen"]:
        out.append("a FROZEN line in a record that never ran")
    frozen = rec["frozen"][0] if len(rec["frozen"]) == 1 else None
    if "piloting" in path_states:
        out += _pilot_terms(rec)
        if _split(rec["raw"])[1] is None:
            out.append(f"a record that ran needs its {RESULT_LINE} line — it bounds the frozen terms")
        h = terms_hash(rec)
        if frozen is None:
            out.append(f"a record that ran needs exactly one FROZEN line (found {len(rec['frozen'])})")
        else:
            if frozen["terms"] != h:
                out.append(f"terms changed after they were frozen (frozen {frozen['terms']}, now {h}) "
                           f"— an experiment does not change its own criteria; start a new record")
            if frozen["max_pilot_days"] is None or frozen["steward_may"] is None:
                out.append("the FROZEN line carries no mandate snapshot (max_pilot_days, steward_may)")
            if (_date(frozen["date"]) or today) > today:
                out.append(f"FROZEN {frozen['date']} lies in the future — a start is not dated ahead")
        terms = frozen["terms"] if frozen else h
        before = frozen["pos"] if frozen else len(rec["reviews"]) + len(rec["log"]) + 1
        on_terms = [r for r in rec["reviews"]
                    if r["terms"] == terms and norm(r["who"]) != implementer and r["pos"] < before]
        if not any(r["verdict"] == "pass" for r in on_terms):
            out.append("no REVIEWED pass on the frozen terms, before the freeze, by someone other than "
                       "the implementer")
        if any(r["verdict"] == "block" for r in on_terms):
            out.append("a REVIEWED block stands on the frozen terms — a pass does not outvote it")
        started = [e for e in rec["log"] if e["state"] == "piloting"]
        # the rights a start and a decision are judged by: the mandate as frozen;
        # a running trial is also bound by the mandate as it is now
        snap_may = frozen["steward_may"] if frozen and frozen["steward_may"] is not None \
            else MANDATE_DEFAULTS["steward_may"]
        snap_days = frozen["max_pilot_days"] if frozen and frozen["max_pilot_days"] else \
            MANDATE_DEFAULTS["max_pilot_days"]
        if len(started) != 1:
            out.append(f"the log needs exactly one piloting line (found {len(started)})")
        else:
            mays = [snap_may] + ([mandate["steward_may"]] if state == "piloting" and mandate else [])
            for may in mays:
                why = may_move(started[0]["who"], "piloting", rec, may, "designed")
                if why:
                    out.append(f"started by {started[0]['who']}: {why}")
                    break
            if frozen and frozen["date"] != started[0]["date"]:
                out.append("the FROZEN line is not dated with the start")
        until, start = _date(f.get("until", "")), _date(frozen["date"]) if frozen else None
        limits = [snap_days] + ([mandate["max_pilot_days"]] if state == "piloting" and mandate else [])
        if until and start and (until - start).days > min(limits):
            out.append(f"until {until} lies {(until - start).days} days after the start — "
                       f"beyond the mandate's max_pilot_days ({min(limits)})")
    out += history_problems(history, path, rec)
    if state in TERMINAL and rec["log"]:
        last = rec["log"][-1]
        prior = rec["log"][-2]["state"] if len(rec["log"]) > 1 else "proposed"
        may = (frozen["steward_may"] if frozen and frozen["steward_may"] is not None
               else (mandate or MANDATE_DEFAULTS)["steward_may"])
        why = may_move(last["who"], state, rec, may, prior)
        if why:
            out.append(f"{state} by {last['who']}: {why}")
    if state == "superseded" and not f.get("superseded-by"):
        out.append("superseded needs superseded-by: OPT-NNNN")
    return list(dict.fromkeys(out))


def _conflicts(parsed: dict[Path, dict]) -> dict[Path, list[str]]:
    """Problems between records: a number used twice, two trials on one
    mechanism or flag — named on every record involved, not only the second."""
    out: dict[Path, list[str]] = defaultdict(list)
    by_number: dict[str, list[Path]] = defaultdict(list)
    running: dict[tuple[str, str], list[Path]] = defaultdict(list)
    for p, rec in parsed.items():
        by_number[p.name[:8]].append(p)
        if rec["fields"].get("state") == "piloting":
            for key in ("mechanism", "flag"):
                value = norm(rec["fields"].get(key, ""))
                if filled(value):
                    running[(key, value)].append(p)
    for num, ps in by_number.items():
        if len(ps) > 1:
            for p in ps:
                out[p].append(f"{num} is used by {len(ps)} records — numbers are unique")
    for (key, value), ps in running.items():
        if len(ps) > 1:
            for p in ps:
                others = ", ".join(o.name for o in ps if o != p)
                out[p].append(f"{others} pilots the same {key} {value!r} — one experiment per "
                              f"{key} at a time, or the results confound each other")
    names = {p.name[:8] for p in parsed}
    for p, rec in parsed.items():
        for key in ("supersedes", "superseded-by"):
            ref = rec["fields"].get(key, "").strip()
            if ref and ref[:8] not in names:
                out[p].append(f"{key}: {ref} names no record")
    return out


def _parsed(root: Path) -> dict[Path, dict]:
    return {p: parse(p.read_text(encoding="utf-8", errors="replace")) for p in record_files(root)}


def check_all(root: Path, *, history: bool = True,
              today: _dt.date | None = None) -> tuple[dict[str, list[str]], list[str]]:
    """({record: problems}, repository-wide problems)."""
    mandate, mproblem = load_mandate(root)
    general = [mproblem] if mproblem else []
    parsed = _parsed(root)
    index = history_index(root) if history else None
    general += vanished(index, parsed)
    conflicts = _conflicts(parsed)
    per: dict[str, list[str]] = {}
    for p, rec in parsed.items():
        probs = problems(root, p, rec, mandate, history=index, today=today) + conflicts.get(p, [])
        if rec["fields"].get("state") == "piloting" and mandate is None:
            probs.append(mproblem or f"piloting without a mandate ({MANDATE})")
        if probs:
            per[p.name] = probs
    return per, general


def active(root: Path, flag: str, *, issue: int | None = None, tier: int | None = None,
           klass: str | None = None, today: _dt.date | None = None) -> tuple[str | None, str]:
    """(record name, why) — the record that switches `flag` on for this work,
    or None and the reason it is off. Every doubt is off: whatever `check`
    finds in the record, between it and another, or in the records' history
    turns it off."""
    today = today or _dt.date.today()
    if not filled(norm(flag)):
        return None, "no flag named"
    mandate, mproblem = load_mandate(root)
    if mproblem or mandate is None:
        return None, mproblem or f"no mandate ({MANDATE})"
    parsed = _parsed(root)
    hits = [(p, rec) for p, rec in parsed.items()
            if norm(rec["fields"].get("flag", "")) == norm(flag) and rec["fields"].get("state") == "piloting"]
    if not hits:
        return None, f"no piloting record carries flag {flag!r}"
    if len(hits) > 1:
        return None, f"{len(hits)} piloting records carry flag {flag!r} — ambiguous, off"
    index = history_index(root)
    gone = vanished(index, parsed)
    if gone:
        return None, gone[0]
    p, rec = hits[0]
    probs = problems(root, p, rec, mandate, history=index, today=today) + _conflicts(parsed).get(p, [])
    if probs:
        return None, f"{p.name}: {probs[0]}"
    until = _date(rec["fields"]["until"])
    if until is None or today > until:
        return None, f"{p.name}: past until {rec['fields'].get('until')} — evaluate it"
    select = parse_select(rec["fields"]["select"]) or {}
    if not selects(select, issue=issue, tier=tier, klass=klass):
        return None, f"{p.name}: this work is outside select ({rec['fields']['select']})"
    return p.name, "piloting"


# --- writing -------------------------------------------------------------
SKELETON = """# {num}: {title}

- state: proposed
- responsible: {responsible}
- implementer: {implementer}
- mechanism: {mechanism}
- placement: TODO core, module, config or project
- flag: TODO the experiment flag the mechanism asks `optimize.py active` for, if any
- select: TODO issues=… tiers=… classes=… parity=odd|even, or all
- until: TODO YYYY-MM-DD
- budget-tokens: TODO tokens the experiment may spend
- budget-hours: TODO execution hours the experiment may spend
- issues: {issues}
- upstream: TODO owner/repo#N of the process change, if any

## Observation
TODO: affected issues, what was observed, evidence and its data quality
(measured / estimated / missing).

## Hypothesis
TODO: the suspected cause and the mechanism by which the change should help.

## Placement
TODO: core, module, config or project, and why there (docs/process/optimization.md,
"Placement") — a change good for this project can be wrong for the process core.

## Trial
TODO: baseline (issues, window), process version, which work is in, exclusions.

## Limits
TODO: budget, duration, quality floors that must hold, stop conditions.

## Criteria
TODO: success criteria fixed before the trial — metric, minimum n, minimum effect;
below minimum n the result is inconclusive.

## Generality
TODO: supported variants affected outside this project and the checks that prove them.

## Rollback
TODO: 1. stop use (state → stopped turns the flag off); 2. the safe way back for
code or data the trial already changed. Everything above the next heading is
frozen byte for byte when the trial starts; the record is plain Markdown (no
HTML, no comment, no code fence).

## Result
TODO: measured against the criteria — time, tokens, interventions, escapes,
upkeep; measured, estimated and missing values apart.

## Decision
TODO: adopt, reject, roll back, or supersede with a new record — and why.

## Log
- {date} {who}: proposed — because {because}
"""


def _slug(title: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return s[:48].rstrip("-") or "record"


def find(root: Path, ident: str) -> Path | None:
    ident = ident.strip()
    for p in record_files(root):
        if p.name == ident or p.name.startswith(ident + "-") or p.stem == ident:
            return p
    return None


def new(root: Path, title: str, mechanism: str, *, responsible: str, implementer: str,
        issues: str, who: str, because: str) -> Path:
    d = records_dir(root)
    d.mkdir(parents=True, exist_ok=True)
    taken = [int(m.group(1)) for p in d.glob("OPT-*.md") if (m := NAME.match(p.name))]
    index = history_index(root) or {}
    taken += [int(n) for n in index]  # a number a deleted record used is not reused
    num = f"OPT-{(max(taken) + 1) if taken else 1:04d}"
    path = d / f"{num}-{_slug(title)}.md"
    path.write_text(SKELETON.format(num=num, title=title, responsible=responsible,
                                    implementer=implementer or "TODO who builds the change",
                                    mechanism=mechanism, issues=issues or "TODO #N, …",
                                    date=_dt.date.today().isoformat(), who=who,
                                    because=because), encoding="utf-8")
    return path


def _set_state(text: str, state: str) -> str:
    lines = text.replace("\r\n", "\n").splitlines(keepends=True)
    for i, line in enumerate(lines):
        if line.startswith("## "):
            break
        m = FIELD.match(line.rstrip("\n"))
        if m and m.group(1) == "state":
            prefix = line[:line.index("state")]
            lines[i] = f"{prefix}state: {state}\n"
            return "".join(lines)
    raise ValueError("no state: line in the header")


def _append_log(text: str, *lines: str) -> str:
    text = text.replace("\r\n", "\n")
    body = "\n".join(lines) + "\n"
    if "\n## Log" not in text:
        return text.rstrip("\n") + "\n\n## Log\n" + body
    return text.rstrip("\n") + "\n" + body


def move(root: Path, path: Path, state: str, who: str, because: str,
         today: _dt.date | None = None) -> str | None:
    """Write the transition, or return why it is refused (nothing written).
    The record as it would be written is judged by `problems` — the same rules
    `check` and `active` apply afterwards."""
    today = today or _dt.date.today()
    text = path.read_text(encoding="utf-8")
    rec = parse(text)
    current = rec["fields"].get("state", "")
    if state not in MOVES.get(current, ()):
        return f"{current} → {state} is not a transition ({current} moves to " \
               f"{', '.join(MOVES.get(current, ())) or 'nothing — it is final'})"
    if not because.strip() or "\n" in because:
        return "--because is required, on one line: a transition without its reason is lost on the next restart"
    lines = [f"- {today.isoformat()} {who.strip()}: {state} — because {because.strip()}"]

    def write() -> None:
        path.write_text(_append_log(_set_state(text, state), *lines), encoding="utf-8")

    if state in SAFE_MOVES:
        write()
        return None
    mandate, mproblem = load_mandate(root)
    frozen = rec["frozen"][0] if len(rec["frozen"]) == 1 else None
    if state == "rolled-back":
        # the way back must stay open even when the record or the mandate is broken
        may = (frozen["steward_may"] if frozen and frozen["steward_may"] is not None
               else (mandate if mandate and not mproblem else MANDATE_DEFAULTS)["steward_may"])
        why = may_move(who, state, rec, may, current)
        if why:
            return why
        if not filled(rec["sections"].get("Decision")):
            return "rolled-back needs a filled ## Decision (what is rolled back, and how)"
        write()
        return None
    if mproblem:
        return mproblem
    if state == "piloting":
        if mandate is None:
            return f"no mandate ({MANDATE}) — analysis needs none, a pilot does"
        until = _date(rec["fields"].get("until", ""))
        if until is not None and until < today:
            return f"until {until} is already past"
        lines.append(f"- FROZEN {today.isoformat()} {who.strip()}: terms={terms_hash(rec)} "
                     f"max_pilot_days={mandate['max_pilot_days']} steward_may={','.join(mandate['steward_may'])}")
    else:
        # a decision now is judged by the mandate now, too
        why = may_move(who, state, rec, (mandate or MANDATE_DEFAULTS)["steward_may"], current)
        if why:
            return why
    if state == "superseded" and not rec["fields"].get("superseded-by"):
        return "add superseded-by: OPT-NNNN (the record that continues this one) first"
    new_text = _append_log(_set_state(text, state), *lines)
    after = parse(new_text)
    parsed = _parsed(root)
    parsed[path] = after
    index = history_index(root)
    probs = (problems(root, path, after, mandate, history=index, today=today)
             + _conflicts(parsed).get(path, []))
    if probs:
        return "; ".join(probs)
    path.write_text(new_text, encoding="utf-8")
    return None


def review(path: Path, who: str, verdict: str, because: str,
           today: _dt.date | None = None) -> str | None:
    today = today or _dt.date.today()
    text = path.read_text(encoding="utf-8")
    rec = parse(text)
    if rec["fields"].get("state") not in ("proposed", "designed"):
        return "a review covers the terms before the pilot; once frozen they do not change"
    if not filled(rec["fields"].get("implementer")):
        return "name the implementer first — a review must know whose change it is not"
    if norm(who) == norm(rec["fields"]["implementer"]):
        return f"{who} implements this change — the review is someone else's"
    if not because.strip() or "\n" in because:
        return "--because is required, on one line"
    if _split(text)[1] is None:
        return f"the record needs its {RESULT_LINE} line — it bounds the terms a review covers"
    line = f"- REVIEWED {today.isoformat()} {who.strip()}: {verdict} terms={terms_hash(rec)} — {because.strip()}"
    path.write_text(_append_log(text, line), encoding="utf-8")
    return None


# --- status --------------------------------------------------------------
def status_lines(root: Path, today: _dt.date | None = None) -> list[str]:
    today = today or _dt.date.today()
    out = []
    for p in record_files(root):
        rec = parse(p.read_text(encoding="utf-8", errors="replace"))
        f = rec["fields"]
        state = f.get("state", "")
        if state == "piloting":
            until = _date(f.get("until", ""))
            if until is None:
                out.append(f"{p.name}: piloting without a readable until — fix the record")
            elif today > until:
                out.append(f"{p.name}: past until {until} — the flag is off; move it to evaluating")
            else:
                out.append(f"{p.name}: piloting, {(until - today).days} day(s) left")
            for key in ("tokens", "hours"):
                spent, budget = _number(f.get(f"spent-{key}")), _number(f.get(f"budget-{key}"))
                if spent is None:
                    out.append(f"{p.name}: spent-{key} not recorded — the budget cannot be judged")
                elif budget is not None and spent > budget:
                    out.append(f"{p.name}: spent-{key} {spent:g} over budget-{key} {budget:g} — stop it")
        elif state in ("stopped", "evaluating"):
            out.append(f"{p.name}: {state} — waiting for its result and decision")
    return out


# --- CLI -----------------------------------------------------------------
def _root() -> Path:
    try:
        r = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    except OSError:
        return Path.cwd()
    return Path(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip() else Path.cwd()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="process-improvement records")
    p.add_argument("--root", type=Path)
    sub = p.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("new")
    n.add_argument("--title", required=True)
    n.add_argument("--mechanism", required=True)
    n.add_argument("--responsible", default="steward")
    n.add_argument("--implementer", default="")
    n.add_argument("--issues", default="")
    n.add_argument("--who", default="steward")
    n.add_argument("--because", default="observed in the process measurements")
    m = sub.add_parser("move")
    m.add_argument("record")
    m.add_argument("state", choices=STATES)
    m.add_argument("--who", required=True)
    m.add_argument("--because", required=True)
    r = sub.add_parser("review")
    r.add_argument("record")
    r.add_argument("--who", required=True)
    r.add_argument("--verdict", choices=("pass", "block"), required=True)
    r.add_argument("--because", required=True)
    c = sub.add_parser("check")
    c.add_argument("--json", action="store_true")
    sub.add_parser("status")
    sub.add_parser("list")
    a = sub.add_parser("active")
    a.add_argument("flag")
    a.add_argument("--issue", type=int)
    a.add_argument("--tier", type=int)
    a.add_argument("--class", dest="klass")
    args = p.parse_args(argv)
    root = args.root or _root()

    if args.cmd == "new":
        path = new(root, args.title, args.mechanism, responsible=args.responsible,
                   implementer=args.implementer, issues=args.issues, who=args.who,
                   because=args.because)
        print(f"optimize: wrote {path.relative_to(root)} — fill Observation, Hypothesis and Placement next")
        return 0
    if args.cmd in ("move", "review"):
        path = find(root, args.record)
        if path is None:
            print(f"optimize: no record {args.record} under {RECORDS}", file=sys.stderr)
            return 2
        why = (move(root, path, args.state, args.who, args.because) if args.cmd == "move"
               else review(path, args.who, args.verdict, args.because))
        if why:
            print(f"optimize: refused — {why}", file=sys.stderr)
            return 1
        print(f"optimize: {path.name} {'→ ' + args.state if args.cmd == 'move' else 'reviewed'}")
        return 0
    if args.cmd == "check":
        per, general = check_all(root)
        if args.json:
            print(json.dumps({"records": per, "general": general}, indent=2))
        else:
            for line in general:
                print(f"optimize: {line}")
            for name, probs in per.items():
                for prob in probs:
                    print(f"optimize: {name}: {prob}")
            if not per and not general:
                print(f"optimize: {len(record_files(root))} record(s), no problem")
        return 1 if per or general else 0
    if args.cmd == "status":
        lines = status_lines(root)
        print("\n".join(f"optimize: {line}" for line in lines) if lines else "optimize: nothing running")
        return 0
    if args.cmd == "list":
        for path in record_files(root):
            rec = parse(path.read_text(encoding="utf-8", errors="replace"))
            f = rec["fields"]
            print(f"{path.name[:8]}  {f.get('state', '?'):<11} {f.get('mechanism', '?')}  — {rec['title']}")
        return 0
    name, why = active(root, args.flag, issue=args.issue, tier=args.tier, klass=args.klass)
    print(f"optimize: {args.flag} {'on' if name else 'off'} — {name or why}")
    return 0 if name else 1


if __name__ == "__main__":
    raise SystemExit(main())
