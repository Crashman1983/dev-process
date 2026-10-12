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
  implementer. It writes `FROZEN <date> <who>: terms=<hash>` — from then on
  Trial, Limits, Criteria, `select`, `until`, the budgets, `flag` and
  `mechanism` must not change: an experiment does not ease its own
  criteria. With git history, `check` also compares against the version the
  FROZEN line was committed with, so a rewritten hash does not help.
- `adopted` is the owner's, or the steward's where the mandate's
  `steward_may` names `adopt`; never the implementer's.

`active` is how a mechanism under trial asks whether to behave the new
way: exactly one `piloting` record carries the flag, its terms are intact,
today is not past `until`, and the work matches `select`
(`issues=12,15 tiers=1,2 classes=mechanical parity=odd`, or `all`; a
constraint the caller cannot answer does not match). Stopping an
experiment is a state change; every doubt reads as inactive.

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
PLACEMENTS = ("core", "module", "config", "project")
SECTIONS = ("Observation", "Hypothesis", "Placement", "Trial", "Limits", "Criteria",
            "Generality", "Rollback", "Result", "Decision", "Log")
# what each state needs filled, cumulative along the path
NEEDS = {
    "designed": ("Observation", "Hypothesis", "Placement"),
    "piloting": ("Trial", "Limits", "Criteria", "Generality", "Rollback"),
    "adopted": ("Result", "Decision"),
    "rejected": ("Decision",),
    "rolled-back": ("Decision",),
    "superseded": ("Decision",),
}
# the frozen terms: what an experiment must not change once it runs
TERM_SECTIONS = ("Trial", "Limits", "Criteria")
TERM_FIELDS = ("mechanism", "flag", "select", "until", "budget-tokens", "budget-hours")
SELECT_KEYS = ("issues", "tiers", "classes", "parity")
# stopping is nobody's right to withhold (the safe direction): not in steward_may
MANDATE_DEFAULTS = {"max_pilot_days": 30, "steward_may": ["start", "roll-back"]}

FIELD = re.compile(r"^\s*(?:[-*+]\s+)?([a-z][a-z-]*)\s*:\s*(.*?)\s*$")
HEADING = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
LOG_LINE = re.compile(r"^\s*[-*+]\s+(\d{4}-\d{2}-\d{2})\s+([^:\s][^:]*?):\s*([a-z-]+)\b(.*)$")
REVIEWED = re.compile(r"^\s*[-*+]\s+REVIEWED\s+(\d{4}-\d{2}-\d{2})\s+([^:]+?):\s*(pass|block)\s+"
                      r"terms=([0-9a-f]{12})\b(.*)$", re.MULTILINE)
FROZEN = re.compile(r"^\s*[-*+]\s+FROZEN\s+(\d{4}-\d{2}-\d{2})\s+([^:]+?):\s*terms=([0-9a-f]{12})\s*$",
                    re.MULTILINE)
PLACEHOLDER = re.compile(r"^(?:todo|tbd|…|\.\.\.|<[^>]*>|-|n/a)?$", re.IGNORECASE)
COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
NAME = re.compile(r"^OPT-(\d{4})-[a-z0-9-]+\.md$")


# --- reading -------------------------------------------------------------
def records_dir(root: Path) -> Path:
    return root / RECORDS


def record_files(root: Path) -> list[Path]:
    d = records_dir(root)
    return sorted(p for p in d.glob("OPT-*.md") if p.is_file()) if d.is_dir() else []


def parse(text: str) -> dict:
    """{"title", "fields": {key: value}, "sections": {name: body}, "log": [...],
    "reviews": [...], "frozen": [...]} — the header is every `key: value` line
    before the first `##` heading."""
    head, _sep, _rest = text.partition("\n## ")
    title = ""
    fields: dict[str, str] = {}
    for line in head.splitlines():
        if line.startswith("# ") and not title:
            title = line[2:].strip()
            continue
        m = FIELD.match(line)
        if m and m.group(1) not in fields:
            fields[m.group(1)] = m.group(2)
    sections: dict[str, str] = {}
    marks = list(HEADING.finditer(text))
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        sections[m.group(1)] = text[m.end():end].strip("\n")
    log_text = sections.get("Log", "")
    log = []
    for line in log_text.splitlines():
        m = LOG_LINE.match(line)
        if m and m.group(3) in STATES:
            log.append({"date": m.group(1), "who": m.group(2).strip(), "state": m.group(3),
                        "rest": m.group(4).strip()})
    reviews = [{"date": m.group(1), "who": m.group(2).strip(), "verdict": m.group(3),
                "terms": m.group(4)} for m in REVIEWED.finditer(log_text)]
    frozen = [{"date": m.group(1), "who": m.group(2).strip(), "terms": m.group(3)}
              for m in FROZEN.finditer(log_text)]
    return {"title": title, "fields": fields, "sections": sections, "log": log,
            "reviews": reviews, "frozen": frozen}


def filled(body: str | None) -> bool:
    """A section counts once it says something: not empty, not only comments,
    not only placeholders (TODO, …, <fill in>)."""
    if not body:
        return False
    for line in COMMENT.sub("", body).splitlines():
        s = line.strip().lstrip("-*+ ").strip()
        if s and not PLACEHOLDER.match(s):
            return True
    return False


def terms_hash(rec: dict) -> str:
    parts = [f"{k}={rec['fields'].get(k, '').strip()}" for k in TERM_FIELDS]
    for name in TERM_SECTIONS:
        body = rec["sections"].get(name, "")
        parts.append(f"## {name}\n" + "\n".join(line.rstrip() for line in body.strip().splitlines()))
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()[:12]


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
    if "parity" in select:
        if issue is None or ("odd" if issue % 2 else "even") not in select["parity"]:
            return False
    return True


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
    unknown = sorted(set(may) - {"start", "roll-back", "adopt", "reject"})
    if unknown:
        return None, f"{MANDATE}: steward_may names unknown right(s) {', '.join(unknown)}"
    return out, None


def may_move(who: str, state: str, rec: dict, mandate: dict | None, from_state: str) -> str | None:
    """Why `who` may not move the record to `state` (concept: decision rights);
    None when allowed. Roles are the literal tokens `owner` and `steward`."""
    who = who.strip()
    implementer = rec["fields"].get("implementer", "").strip()
    if state in ("piloting", "adopted") and implementer and who == implementer:
        return f"{who} implements this change and cannot {'start' if state == 'piloting' else 'adopt'} it"
    if state in ("proposed", "designed", "stopped", "evaluating"):
        return None
    may = (mandate or MANDATE_DEFAULTS)["steward_may"]
    right = {"piloting": "start", "adopted": "adopt", "rejected": "reject",
             "rolled-back": "roll-back", "superseded": "reject"}[state]
    if who == "owner":
        return None
    if state == "rejected" and from_state in ("proposed", "designed"):
        return None  # declining a proposal is anyone's
    if who == "steward" and right in may:
        return None
    return (f"{state} needs the owner, or the steward where the mandate's steward_may names "
            f"{right!r} (it names: {', '.join(may) or 'nothing'})")


# --- judging -------------------------------------------------------------
def _git(root: Path, *args: str) -> str | None:
    try:
        r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout.decode("utf-8", "surrogateescape") if r.returncode == 0 else None


def frozen_in_history(root: Path, path: Path) -> tuple[str, str] | None:
    """(commit, terms hash of the record as that commit had it) for the first
    commit whose version of `path` carries a FROZEN line; None when git cannot
    say (untracked, no repository, shallow history)."""
    try:
        rel = path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return None
    out = _git(root, "log", "--follow", "--reverse", "--format=%H", "-G", r"FROZEN", "--", rel)
    if not out:
        return None
    for sha in out.split():
        names = _git(root, "log", "-1", "--follow", "--format=", "--name-only", "-z", sha, "--", rel)
        old = (names or "").split("\0")[0] or rel
        text = _git(root, "show", f"{sha}:{old}")
        if text is not None and FROZEN.search(text):
            return sha, terms_hash(parse(text))
    return None


def problems(root: Path, path: Path, rec: dict, mandate: dict | None, *,
             history: bool = True) -> list[str]:
    """Everything wrong with one record, in the order a reader fixes it."""
    out: list[str] = []
    f = rec["fields"]
    if not NAME.match(path.name):
        out.append("file name must be OPT-NNNN-<slug>.md")
    state = f.get("state", "")
    if state not in STATES:
        return out + [f"state {state!r} is not one of {', '.join(STATES)}"]
    for key in ("responsible", "mechanism"):
        if not f.get(key):
            out.append(f"{key}: missing")
    if rec["log"] and rec["log"][-1]["state"] != state:
        out.append(f"state is {state} but the log's last transition is {rec['log'][-1]['state']}")
    path_states = _reached(state, rec)
    for need_state in path_states:
        for name in NEEDS.get(need_state, ()):
            if not filled(rec["sections"].get(name)):
                out.append(f"{state} needs a filled ## {name}")
    if "designed" in path_states:
        placement = f.get("placement", "").strip()
        if placement not in PLACEMENTS:
            out.append(f"placement must be one of {', '.join(PLACEMENTS)}")
    if "piloting" in path_states:
        out += _pilot_terms(rec)
        h = terms_hash(rec)
        if len(rec["frozen"]) != 1:
            out.append(f"a record that ran needs exactly one FROZEN line (found {len(rec['frozen'])})")
        elif rec["frozen"][0]["terms"] != h:
            out.append(f"terms changed after they were frozen (frozen {rec['frozen'][0]['terms']}, now {h}) "
                       f"— an experiment does not change its own criteria; start a new record")
        elif history:
            hist = frozen_in_history(root, path)
            if hist is not None and hist[1] != h:
                out.append(f"terms differ from the version frozen in commit {hist[0][:10]} "
                           f"(then {hist[1]}, now {h}) — an experiment does not change its own criteria")
        if not any(r["verdict"] == "pass" and r["terms"] == (rec["frozen"][0]["terms"] if rec["frozen"] else h)
                   and r["who"] != f.get("implementer", "").strip() for r in rec["reviews"]):
            out.append("no REVIEWED pass on the frozen terms by someone other than the implementer")
    if state in TERMINAL and rec["log"]:
        last = rec["log"][-1]
        before = rec["log"][-2]["state"] if len(rec["log"]) > 1 else "proposed"
        why = may_move(last["who"], state, rec, mandate, before)
        if why:
            out.append(f"{state} by {last['who']}: {why}")
    if state == "superseded" and not f.get("superseded-by"):
        out.append("superseded needs superseded-by: OPT-NNNN")
    return out


def _reached(state: str, rec: dict) -> list[str]:
    """The states a record in `state` has passed through (for what it must carry):
    a rejected proposal never ran; a rejected trial did, and keeps its terms."""
    if state == "proposed":
        return ["proposed"]
    if state == "designed":
        return ["proposed", "designed"]
    ran = state not in ("rejected",) or rec["frozen"] or any(e["state"] == "piloting" for e in rec["log"])
    if not ran:
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


def check_all(root: Path, *, history: bool = True) -> tuple[dict[str, list[str]], list[str]]:
    """({record: problems}, repository-wide problems)."""
    mandate, mproblem = load_mandate(root)
    per: dict[str, list[str]] = {}
    general = [mproblem] if mproblem else []
    numbers: dict[str, str] = {}
    running: dict[tuple[str, str], str] = {}
    names = set()
    parsed = {}
    for p in record_files(root):
        rec = parse(p.read_text(encoding="utf-8", errors="replace"))
        parsed[p] = rec
        names.add(p.name[:8])
    for p, rec in parsed.items():
        probs = problems(root, p, rec, mandate, history=history)
        num = p.name[:8]
        if num in numbers:
            probs.append(f"{num} is also {numbers[num]}")
        numbers.setdefault(num, p.name)
        if rec["fields"].get("state") == "piloting":
            if mandate is None:
                probs.append(f"piloting without a mandate ({MANDATE})")
            for key in ("mechanism", "flag"):
                value = rec["fields"].get(key, "").strip()
                if value:
                    other = running.setdefault((key, value), p.name)
                    if other != p.name:
                        probs.append(f"{other} pilots the same {key} {value!r} — one experiment per "
                                     f"{key} at a time, or the results confound each other")
        for key in ("supersedes", "superseded-by"):
            ref = rec["fields"].get(key, "").strip()
            if ref and ref[:8] not in names:
                probs.append(f"{key}: {ref} names no record")
        if probs:
            per[p.name] = probs
    return per, general


def active(root: Path, flag: str, *, issue: int | None = None, tier: int | None = None,
           klass: str | None = None, today: _dt.date | None = None) -> tuple[str | None, str]:
    """(record name, why) — the record that switches `flag` on for this work,
    or None and the reason it is off. Every doubt is off."""
    today = today or _dt.date.today()
    mandate, mproblem = load_mandate(root)
    if mproblem or mandate is None:
        return None, mproblem or f"no mandate ({MANDATE})"
    hits = []
    for p in record_files(root):
        rec = parse(p.read_text(encoding="utf-8", errors="replace"))
        if rec["fields"].get("flag", "").strip() == flag and rec["fields"].get("state") == "piloting":
            hits.append((p, rec))
    if not hits:
        return None, f"no piloting record carries flag {flag!r}"
    if len(hits) > 1:
        return None, f"{len(hits)} piloting records carry flag {flag!r} — ambiguous, off"
    p, rec = hits[0]
    probs = problems(root, p, rec, mandate)
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
- placement: <core | module | config | project>
- flag: <the experiment flag the mechanism asks `optimize.py active` for, if any>
- select: <issues=… tiers=… classes=… parity=odd|even, or all>
- until: <YYYY-MM-DD>
- budget-tokens: <tokens the experiment may spend>
- budget-hours: <execution hours the experiment may spend>
- issues: {issues}
- upstream: <owner/repo#N of the process change, if any>

## Observation
<!-- affected issues, what was observed, evidence and its data quality
(measured / estimated / missing) -->

## Hypothesis
<!-- the suspected cause and the mechanism by which the change should help -->

## Placement
<!-- core | module | config | project, and why there (docs/process/optimization.md,
"Placement") — a change good for this project can be wrong for the process core -->

## Trial
<!-- baseline (issues, window), process version, which work is in, exclusions -->

## Limits
<!-- budget, duration, quality floors that must hold, stop conditions -->

## Criteria
<!-- success criteria fixed before the trial: metric, minimum n, minimum effect;
below minimum n the result is inconclusive -->

## Generality
<!-- supported variants affected outside this project and the checks that prove them -->

## Rollback
<!-- 1. stop use (state → stopped turns the flag off); 2. the safe way back for
code or data the trial already changed -->

## Result
<!-- measured against the criteria: time, tokens, interventions, escapes, upkeep;
measured, estimated and missing values apart -->

## Decision
<!-- adopt, reject, roll back, or supersede with a new record — and why -->

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
    num = f"OPT-{(max(taken) + 1) if taken else 1:04d}"
    path = d / f"{num}-{_slug(title)}.md"
    path.write_text(SKELETON.format(num=num, title=title, responsible=responsible,
                                    implementer=implementer or "<who builds the change>",
                                    mechanism=mechanism, issues=issues or "<#N, …>",
                                    date=_dt.date.today().isoformat(), who=who,
                                    because=because), encoding="utf-8")
    return path


def _set_state(text: str, state: str) -> str:
    lines = text.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if line.startswith("## "):
            break
        m = FIELD.match(line)
        if m and m.group(1) == "state":
            prefix = line[:line.index("state")]
            lines[i] = f"{prefix}state: {state}\n"
            return "".join(lines)
    raise ValueError("no state: line in the header")


def _append_log(text: str, *lines: str) -> str:
    body = "\n".join(lines) + "\n"
    if "\n## Log" not in text:
        return text.rstrip("\n") + "\n\n## Log\n" + body
    return text.rstrip("\n") + "\n" + body


def move(root: Path, path: Path, state: str, who: str, because: str,
         today: _dt.date | None = None) -> str | None:
    """Write the transition, or return why it is refused (nothing written)."""
    today = today or _dt.date.today()
    text = path.read_text(encoding="utf-8")
    rec = parse(text)
    current = rec["fields"].get("state", "")
    if state not in MOVES.get(current, ()):
        return f"{current} → {state} is not a transition ({current} moves to " \
               f"{', '.join(MOVES.get(current, ())) or 'nothing — it is final'})"
    if not because.strip():
        return "--because is required: a transition without its reason is lost on the next restart"
    mandate, mproblem = load_mandate(root)
    if mproblem:
        return mproblem
    why = may_move(who, state, rec, mandate, current)
    if why:
        return why
    target = {**rec, "fields": {**rec["fields"], "state": state}}
    if state == "piloting":
        if mandate is None:
            return f"no mandate ({MANDATE}) — analysis needs none, a pilot does"
        h = terms_hash(rec)
        target["frozen"] = [{"date": today.isoformat(), "who": who, "terms": h}]
        until = _date(rec["fields"].get("until", ""))
        if until is not None and (until - today).days > mandate["max_pilot_days"]:
            return f"until {until} is beyond the mandate's max_pilot_days ({mandate['max_pilot_days']})"
        if until is not None and until < today:
            return f"until {until} is already past"
    if state == "superseded" and not rec["fields"].get("superseded-by"):
        return "add superseded-by: OPT-NNNN (the record that continues this one) first"
    probs = [p for p in problems(root, path, target, mandate, history=False)
             if not p.startswith("state is ") and not p.startswith(f"{state} by ")]
    if probs:
        return "; ".join(probs)
    lines = [f"- {today.isoformat()} {who}: {state} — because {because.strip()}"]
    if state == "piloting":
        lines.append(f"- FROZEN {today.isoformat()} {who}: terms={terms_hash(rec)}")
    path.write_text(_append_log(_set_state(text, state), *lines), encoding="utf-8")
    return None


def review(path: Path, who: str, verdict: str, because: str,
           today: _dt.date | None = None) -> str | None:
    today = today or _dt.date.today()
    text = path.read_text(encoding="utf-8")
    rec = parse(text)
    if rec["fields"].get("state") not in ("proposed", "designed"):
        return "a review covers the terms before the pilot; once frozen they do not change"
    if who.strip() == rec["fields"].get("implementer", "").strip():
        return f"{who} implements this change — the review is someone else's"
    if not because.strip():
        return "--because is required"
    line = f"- REVIEWED {today.isoformat()} {who}: {verdict} terms={terms_hash(rec)} — {because.strip()}"
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
