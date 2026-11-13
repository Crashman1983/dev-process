#!/usr/bin/env python3
"""tower — the situation table for parallel work on one clone, computed,
never narrated.

    uv run scripts/process/tower.py            # short text: worktrees, findings
    uv run scripts/process/tower.py --json     # the full table for an agent
    uv run scripts/process/tower.py --stale-minutes 60
    uv run scripts/process/tower.py --remote   # other hosts: their branches on origin, their published reports
    uv run scripts/process/tower.py --json --section findings   # only these keys
    uv run scripts/process/tower.py --wait --timeout 1800 --states pushed,blocked,stale,prompt
                                               # block until a report line arrives, or a live
                                               # session goes stale or sits at a permission
                                               # prompt: exit 0, 3 on timeout

What it assembles (all from state the process already keeps):
  worktrees  — every `git worktree` of this clone: branch, ahead/behind the
               integration branch, paths in flight (merge-base…HEAD), dirty
               files, minutes since the last commit
  overlaps   — two worktrees carrying the same file (hard) or files in the
               same directory (soft): the collision nobody sees until merge
  plans      — active plans and spec plans with tier, issue, decisions
               count, design-contract binding
  reviews    — clearing REVIEW passes today, by work id
  gates      — the runner's red ledger with age (a chronic red is wallpaper)
  lanes      — `lane.py status` where the project has lanes (`testing_config.lane_script`)
  reports    — the latest state each worker reported (`report.py`)
  holds      — the branches the train holds (`train_holds`, the train's own
               rule), for live local branches ahead of the integration branch
  wip        — with the mandate's `steering` block: per track its limit, the
               issues in progress on it (`in_progress`, every host as last
               fetched; dormant ones apart) and dispatch's WIP overrides of 7 days
  findings   — deterministic, each with a because: overlaps, a Tier 2+ plan
               without an issue, a plan without a Decisions ledger, a gate
               red for days, a worker with no report and no commit for an
               hour, a tmux worker at a permission prompt, a branch far
               behind the integration branch, a train hold a later report hides

The tower decides nothing. It is the input an orchestrating agent reads
instead of the sessions themselves — compact, testable, and the same on
every run. Sibling imports; stdlib only."""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import shlex
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling imports
import check_review as _review  # noqa: E402
import report as _report  # noqa: E402

from process_git import git_environment  # noqa: E402

INTEGRATION = _review.INTEGRATION_REFS
PLANS_ACTIVE = ".process-work/plans"
SPECS_DIR = "specs"
DESIGN_CONTRACT = re.compile(r"^\s*(?:[-*+]\s+)?[*_]*design-contract[*_]*\s*:\s*(\S+)",
                             re.IGNORECASE | re.MULTILINE)
DECISION_LINE = re.compile(r"^\s*(?:[-*+]\s+)?DECISION\s+\d{4}-\d{2}-\d{2}\s", re.MULTILINE)
BEHIND_LIMIT = 50
PLAN_NAME = re.compile(r"^(\d{4}-\d{2}-\d{2}-|design-)")
RED_AGE_DAYS = 2
# a live worker that printed nothing for this long waits for input
WAIT_MINUTES = 30
# a worker with no commit and no report for this long is stale — unless
# --stale-minutes, PROCESS_STALE_MINUTES or the policy's `stale_minutes` say otherwise
STALE_MINUTES = 60
CLOCK_SKEW_SECONDS = 300  # a status stamp this far ahead is a wrong clock (#270)
# a worker reporting these waits, it does not work; `failed` is over and has its own finding (#270)
PARKED = ("review-pass", "done", "idle", "failed")
# a live tmux worker whose screen shows a dialog this long waits on a human,
# not on the steward (#377) — unless --prompt-minutes, PROCESS_PROMPT_MINUTES
# or the policy's `prompt_minutes` say otherwise
PROMPT_MINUTES = 10
PROMPT_LINES = 15  # the screen tail a dialog is looked for in: it spans several lines
# `prompt` and `stale` are synthetic: never a report line, written by --wait for a
# live session at a permission prompt or a silent one
WAIT_STATES = _report.STATES + ("prompt", "stale")
STALE_POLL_S = 60  # how often --wait looks at the live sessions
STALE_SEEN = "stale-announced.json"  # beside the reports: the stale episodes --wait announced
PROMPT_SEEN = "prompt-announced.json"  # likewise, the permission prompts


def _git(root: Path, *args: str) -> str | None:
    try:
        r = subprocess.run(["git", "-C", str(root), "--no-optional-locks", *args],
                           capture_output=True, text=True, timeout=30, env=git_environment())
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout if r.returncode == 0 else None


def integration_ref(root: Path) -> str | None:
    for ref in _review.integration_refs(root):
        if _git(root, "rev-parse", "--verify", "--quiet", ref) is not None:
            return ref
    return None


# --- worktrees -----------------------------------------------------------------

def worktrees(root: Path) -> list[dict]:
    out = _git(root, "worktree", "list", "--porcelain") or ""
    items: list[dict] = []
    cur: dict = {}
    for line in out.splitlines() + [""]:
        if not line:
            if cur:
                items.append(cur)
            cur = {}
            continue
        key, _, val = line.partition(" ")
        if key == "worktree":
            cur["path"] = val
        elif key == "branch":
            cur["branch"] = val.replace("refs/heads/", "")
        elif key == "HEAD":
            cur["head"] = val
        elif key in ("bare", "detached"):
            cur[key] = True
    return items


def describe_worktree(wt: dict, ref: str | None) -> dict:
    path = Path(wt["path"])
    d = {"path": str(path), "branch": wt.get("branch") or ("detached" if wt.get("detached") else "?"),
         "head": (wt.get("head") or "")[:12]}
    if wt.get("bare") or not path.is_dir():
        d["missing"] = True
        return d
    if ref:
        counts = _git(path, "rev-list", "--left-right", "--count", f"{ref}...HEAD")
        if counts:
            behind, ahead = (counts.split() + ["0", "0"])[:2]
            d["ahead"], d["behind"] = int(ahead), int(behind)
    try:
        in_flight = _review.paths_in_flight(path)
    except _review.GitReadError:
        in_flight = None  # an ambiguous fork point: an overlap cannot be ruled out
    d["in_flight"] = sorted(in_flight or ())
    if in_flight is None:
        d["in_flight_unknown"] = True  # git failed: an overlap here cannot be ruled out
    status = _git(path, "status", "--porcelain")
    d["dirty"] = len([ln for ln in (status or "").splitlines() if ln.strip()])
    last = _git(path, "log", "-1", "--format=%ct")
    if last and last.strip().isdigit():
        d["minutes_since_commit"] = int((time.time() - int(last.strip())) // 60)
    return d


BOOKKEEPING = (".process-work/",)  # every branch writes here; sharing it is not a collision
INTEGRATION_NAMES = _review.INTEGRATION_NAMES


def _in_flight_count(wt: dict) -> str:
    """"3 file(s)", or "files unknown" when git could not list them."""
    return "files unknown" if wt.get("in_flight_unknown") else f"{len(wt.get('in_flight', []))} file(s)"


def overlaps(wts: list[dict], integration_names: tuple[str, ...] = INTEGRATION_NAMES) -> list[dict]:
    out: list[dict] = []
    wts = [w for w in wts if w.get("branch") not in integration_names and not w.get("missing")]
    for i, a in enumerate(wts):
        for b in wts[i + 1:]:
            fa, fb = set(a.get("in_flight", [])), set(b.get("in_flight", []))
            if not fa or not fb:
                continue
            same = sorted(fa & fb)
            if same:
                out.append({"a": a["branch"], "b": b["branch"], "kind": "file", "paths": same[:20]})
                continue
            da = {str(Path(p).parent) for p in fa if not p.startswith(BOOKKEEPING)}
            db = {str(Path(p).parent) for p in fb if not p.startswith(BOOKKEEPING)}
            shared = sorted(x for x in da & db if x not in (".", ""))
            if shared:
                out.append({"a": a["branch"], "b": b["branch"], "kind": "directory", "paths": shared[:20]})
    return out


# --- plans, reviews, gates, lanes ----------------------------------------------

def plans(root: Path) -> list[dict]:
    files: list[Path] = []
    d = root / PLANS_ACTIVE
    if d.is_dir():
        files += sorted(p for p in d.glob("*.md"))
    s = root / SPECS_DIR
    if s.is_dir():
        files += sorted(s.glob("*/plan.md"))
    out: list[dict] = []
    for p in files:
        if p.name != "plan.md" and not PLAN_NAME.match(p.name):
            continue  # a README or a note in the plans folder is not a plan
        try:
            text = _review._unfenced(p.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        tier = _review.plan_tier(text)
        issues = sorted(_review._plan_issue_numbers(text))
        dc = DESIGN_CONTRACT.search(text)
        out.append({
            "path": str(p.relative_to(root)),
            "kind": "design" if p.stem.startswith("design-") else "plan",
            "tier": tier,
            "issue": f"#{issues[0]}" if issues else None,
            "decisions": len(DECISION_LINE.findall(text)),
            "has_decisions_section": bool(_review.DECISIONS_HEADING.search(text)),
            "design_contract": dc.group(1).strip("`'\"") if dc else None,
            "waived": _review.review_waived(text),
            "age_days": int((time.time() - p.stat().st_mtime) // 86400),
        })
    return out


def plans_everywhere(root: Path, wts: list[dict]) -> list[dict]:
    """Active plans of every worktree of this clone — a worker's plan lives in
    ITS worktree, not in the steward's, and a plan there without an issue or a
    tier is exactly what the table must show. Same plan path on several
    worktrees: the first (the root comes first) wins; each entry names its
    worktree's branch."""
    out: list[dict] = []
    seen: set[str] = set()
    for wt in wts or [{"path": str(root)}]:
        wroot = Path(wt["path"])
        if wt.get("missing") or not wroot.is_dir():
            continue
        for p in plans(wroot):
            key = p["path"]
            if key in seen:
                continue
            seen.add(key)
            out.append({**p, "branch": wt.get("branch")})
    return out


def _questions_in(text: str, plan: str, branch: str | None, issue: str | None) -> list[dict]:
    out = []
    for m in _review.open_questions(text):
        out.append({"plan": plan, "branch": branch, "issue": issue, "date": m.group(1),
                    "who": (m.group(2) or "worker").strip(), "question": m.group(3).strip()[:600]})
    return out


def _plan_paths_in_ref(root: Path, ref: str) -> list[str]:
    # -z: a non-ASCII plan name comes back quoted otherwise, and the plan
    # stays unseen (downstream refutation)
    names = sorted(_review._names(_review._git_bytes(
        root, "ls-tree", "-r", "-z", "--name-only", ref, "--", PLANS_ACTIVE, SPECS_DIR)) or ())
    return [n for n in names if (n.startswith(PLANS_ACTIVE + "/") and PLAN_NAME.match(Path(n).name))
            or (n.startswith(SPECS_DIR + "/") and Path(n).name == "plan.md")]


def questions(root: Path, wts: list[dict], elsewhere: list[dict] | None = None) -> list[dict]:
    """Open `DECISION NEEDED <date> <who>: <question — options … recommendation …>`
    lines in active plans — in every worktree of this clone (a worker's plan
    lives in ITS worktree, not the steward's) and in the branches other hosts
    pushed. Answered = the line was rewritten to DECISION or marked answered
    (`check_review.open_questions`). Uncommitted text
    counts on this host: the question is asked the moment it is written."""
    out: list[dict] = []
    seen: set[tuple] = set()
    for wt in wts:
        wroot = Path(wt["path"])
        if wt.get("missing") or not wroot.is_dir():
            continue
        for p in plans(wroot):
            try:
                text = (wroot / p["path"]).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for q in _questions_in(text, p["path"], wt.get("branch"), p.get("issue")):
                key = (q["plan"], q["date"], q["question"])
                if key not in seen:
                    seen.add(key)
                    out.append(q)
    for b in elsewhere or []:
        ref = f"origin/{b['branch']}"
        for rel in _plan_paths_in_ref(root, ref):
            text = _git(root, "show", f"{ref}:{rel}") or ""
            issues = sorted(_review._plan_issue_numbers(_review._unfenced(text)))
            for q in _questions_in(text, rel, b["branch"], f"#{issues[0]}" if issues else None):
                key = (q["plan"], q["date"], q["question"])
                if key not in seen:
                    seen.add(key)
                    q["remote"] = True
                    out.append(q)
    return out


def sessions(root: Path) -> list[dict]:
    """Dispatched worker sessions with their last printed line — the look at
    the workers the steward otherwise lacks."""
    try:
        import dispatch as _dispatch
    except ImportError:
        return []
    out = []
    reports = _report.read_reports(root)
    # model drift is read only where the policy names the harness's transcripts
    pattern = _dispatch.transcripts_pattern(root) if hasattr(_dispatch, "model_drift") else None
    input_line = _dispatch.prompt_pattern(root) if hasattr(_dispatch, "prompt_pattern") else None
    for rec in _dispatch.records(root):
        last, since, prompt = screen(_dispatch, rec, input_line)
        rep = _dispatch.session_report(rec, reports) if hasattr(_dispatch, "session_report") else None
        sid = _dispatch.handover_session(rec) if hasattr(_dispatch, "handover_session") else ""
        where = (f"another host (reports via origin{', session ' + sid if sid else ''})" if rec.get("remote") else
                 f"tmux {rec.get('tmux_session')}:{rec.get('tmux_name')}" if rec.get("tmux_window")
                 else f"pid {rec.get('pid')}")
        out.append({"branch": rec["branch"], "phase": rec.get("phase"), "issue": rec.get("issue"),
                    "model": rec.get("model"), "effort": rec.get("effort"),
                    "model_drift": _dispatch.model_drift(root, rec, pattern) if pattern else [],
                    "model_alias": bool(pattern) and _dispatch.is_alias(str(rec.get("model") or "")),
                    "defect": rec.get("defect"), "alive": rec["alive"], "state": rec["state"], "where": where,
                    "minutes_since_start": int((time.time() - int(rec.get("started") or time.time())) // 60),
                    "last_output": last[-200:], "minutes_since_output": since, "prompt": prompt,
                    # the session's own word and whether its phase is over — dispatch's
                    # answer, the one chain acts on; asked of a quiet live worker and
                    # of one that ended (a finished phase is no dead worker)
                    "report_state": (rep or {}).get("state"),
                    "status_minutes_ago": status_age(rec.get("status_file"), time.time()),
                    "phase_over": (_dispatch.phase_over(root, rec, rep, local=True)
                                   if (not rec["alive"] or (since is not None and since >= WAIT_MINUTES))
                                   and hasattr(_dispatch, "phase_over") else None)})
    return out


def screen(_dispatch, rec: dict, pattern=None) -> tuple[str, int | None, str | None]:
    """A session's last printed line, the minutes since it wrote, and the line
    of a dialog open on its screen (`dispatch.dialog_line`, the one
    recogniser, below the input line `pattern` — `dispatch.prompt_pattern`,
    what `say` reads) — looked for only on a live tmux window: a detached
    `claude -p` run never shows one, a tool it may not use is refused there (#377)."""
    if not (rec.get("tmux_window") and rec.get("alive") and rec.get("runner") != "detached"
            and hasattr(_dispatch, "dialog_line")):
        last, since = _dispatch.last_output(rec)
        return last, since, None
    tail, since = _dispatch.last_output(rec, PROMPT_LINES)
    lines = tail.splitlines()
    found = _dispatch.dialog_line(lines, pattern) if pattern is not None else _dispatch.dialog_line(lines)
    return (lines[-1] if lines else ""), since, found


def reviews_today(root: Path) -> dict:
    today = _dt.date.today().isoformat()
    jdir = root / _review.JOURNAL_DIR
    passes: dict[str, int] = {}
    blocks: dict[str, int] = {}
    if jdir.is_dir():
        for f in jdir.glob("**/*.md"):
            if today not in f.name:
                continue
            records, _errors = _review.parse_review_lines(f.read_text(encoding="utf-8", errors="replace"))
            for _ln, rec in records:
                target = passes if rec.get("verdict") == "pass" else blocks
                target[rec["work"]] = target.get(rec["work"], 0) + 1
    return {"date": today, "pass": passes, "block": blocks}


def red_gates(root: Path) -> list[dict]:
    """The runner's red ledger: one `<gate> <first red day> [<reason>]` line per
    red gate. The one reader of that file besides the runner; the reason is
    there when the runner knew it (a gate killed by its timeout names the slow
    phase)."""
    gitdir = _git(root, "rev-parse", "--git-dir")
    if not gitdir:
        return []
    g = Path(gitdir.strip())
    if not g.is_absolute():
        g = root / g
    ledger = g / "process-red-ledger"
    if not ledger.is_file():
        return []
    out: list[dict] = []
    today = _dt.date.today()
    for ln in ledger.read_text(encoding="utf-8", errors="replace").splitlines():
        if " " not in ln:
            continue
        gate, rest = ln.split(" ", 1)
        day, _sep, reason = rest.strip().partition(" ")
        try:
            age = (today - _dt.date.fromisoformat(day)).days
        except ValueError:
            age = 0
        out.append({"gate": gate, "since": day, "age_days": age, "reason": reason.strip()})
    return out


# --- balance: how much of what lands is process ---------------------------------

# process records and the process itself — what a change to the product does not touch
PROCESS_PATHS = (".process-work/", "docs/process/", "scripts/process/", ".githooks/", ".claude/",
                 ".github/prompts/", ".github/instructions/", ".specify/", "specs/")
PROCESS_FILES = (".copier-answers.yml", ".process-owned", ".pre-commit-config.yaml",
                 "CLAUDE.md", "AGENTS.md")
BALANCE_DAYS = 7
# above this share of process-only commits, with enough of them to judge, the
# process outweighs the product (downstream: 47 % process-only against 19 %
# product in two weeks, and the steward's time over 90 % process)
PROCESS_HEAVY_SHARE = 0.4
PROCESS_SHARE_WEEKS = 4  # the weeks `process_kpis.py share` judges the share over
BALANCE_MIN_COMMITS = 20


def process_share_limit(root: Path) -> tuple[float, int]:
    """(max, weeks): the process-only share of commits above which the process outweighs
    the product, and the weeks `share` judges it over — `steering.process_share_max` (0–1)
    and `steering.process_share_window_weeks` from the mandate, each falling back on its
    own to PROCESS_HEAVY_SHARE and PROCESS_SHARE_WEEKS. A wrong type is ignored, never
    guessed. The one owner of the limit: the tower's finding takes the max, `share` both."""
    from optimize import load_mandate  # noqa: PLC0415 — stdlib-only sibling
    mandate, _problem = load_mandate(root)
    steering = (mandate or {}).get("steering")
    if not isinstance(steering, dict):
        steering = {}
    top = steering.get("process_share_max")
    weeks = steering.get("process_share_window_weeks")
    good_top = isinstance(top, (int, float)) and not isinstance(top, bool) and 0 <= top <= 1
    good_weeks = isinstance(weeks, int) and not isinstance(weeks, bool) and weeks >= 1
    return (top if good_top else PROCESS_HEAVY_SHARE), (weeks if good_weeks else PROCESS_SHARE_WEEKS)


def is_process_path(rel: str) -> bool:
    return rel.startswith(PROCESS_PATHS) or rel in PROCESS_FILES


def classify_commit(files: set[str]) -> str:
    """`process` (only process paths), `product` (none) or `mixed`; no files: `empty`."""
    if not files:
        return "empty"
    proc = sum(is_process_path(f) for f in files)
    return "process" if proc == len(files) else "product" if proc == 0 else "mixed"


def _commits_since(root: Path, ref: str, since: str, until: str | None, *extra: str) -> list[set[str]] | None:
    window = [f"--since={since}"] + ([f"--until={until}"] if until else [])
    out = _git(root, "log", ref, *window, "-z", "--name-only", "--format=%x01%H", *extra)
    if out is None:
        return None
    commits: list[set[str]] = []
    for field in out.split("\0"):
        if field.startswith("\x01"):  # `\x01<sha>`, then its names, the first after a newline
            commits.append(set())
            continue
        field = field.lstrip("\n")
        if field and commits:
            commits[-1].add(field)
    return commits


def balance(root: Path, ref: str | None, days: int = BALANCE_DAYS, offset: int = 0) -> dict | None:
    """What landed on the integration branch in `days` ending `offset` days ago:
    commits by process-only / mixed / product, and the first-parent changes
    (merges included, as their diff to main) that carried product code."""
    if not ref:
        return None
    since, until = f"{days + offset} days ago", (f"{offset} days ago" if offset else None)
    commits = _commits_since(root, ref, since, until, "--no-merges")
    landed = _commits_since(root, ref, since, until, "--first-parent", "-m")
    if commits is None or landed is None:
        return None
    kinds = {"process": 0, "mixed": 0, "product": 0}
    for files in commits:
        kind = classify_commit(files)
        if kind in kinds:
            kinds[kind] += 1
    return {"days": days, "commits": sum(kinds.values()), **kinds,
            "landed": len(landed), "landed_product": sum(classify_commit(f) in ("product", "mixed")
                                                         for f in landed)}


def issue_branch_commits(root: Path, issue: int, since: datetime | None) -> int | None:
    """The commits on the branches that carry `issue` in their name (`check_review.branch_issue`),
    local and remote: per branch `--no-merges <branch> --not <integration>`, authored at or after
    `since` (every one without it). A local branch and its remote copy after a rebase are one
    commit each, told by `git patch-id --stable`; a commit without a diff counts by its SHA.
    None when there is no integration branch or git cannot read a branch. The one count for
    `process_kpis.py intake` (v2.96) and the growth note of dispatch (v2.97)."""
    ref = integration_ref(root)
    if not ref:
        return None
    names = (_git(root, "for-each-ref", "--format=%(refname:short)", "refs/heads/", "refs/remotes/") or "").split()
    shas: set[str] = set()
    for name in names:
        if name == ref or _review.branch_issue(name) != str(issue):
            continue
        out = _git(root, "log", "--no-merges", "--format=%H %at", name, "--not", ref)
        if out is None:
            return None
        for line in out.splitlines():
            sha, _, at = line.partition(" ")
            if at.isdigit() and (since is None or int(at) >= since.timestamp()):
                shas.add(sha)
    if not shas:
        return 0
    try:
        show = subprocess.run(["git", "-C", str(root), "--no-optional-locks", "show", "--no-color", "--no-ext-diff",
                               "--no-textconv", "-p", "--format=commit %H", *sorted(shas)],
                              capture_output=True, timeout=60, env=git_environment())
        ids = subprocess.run(["git", "-C", str(root), "patch-id", "--stable"], input=show.stdout,
                             capture_output=True, timeout=60, env=git_environment())
    except (OSError, subprocess.TimeoutExpired):
        return None
    if show.returncode != 0 or ids.returncode != 0:
        return None
    patches: dict[str, str] = {}
    for line in ids.stdout.decode(errors="replace").splitlines():
        patch, _, sha = line.partition(" ")
        patches[sha.strip()] = patch
    return len(set(patches.values())) + sum(1 for s in shas if s not in patches)


def lanes(root: Path) -> list[str]:
    """The lane status lines (`testing_config.lane_status` owns where they come from)."""
    import testing_config  # noqa: PLC0415

    return testing_config.lane_status(root, env=git_environment())


def latest_reports(root: Path, *, remote: bool = False, states: tuple[str, ...] | None = None,
                   skip=None) -> list[dict]:
    """The latest report per worker, newest first. With `states`, the latest
    among those states only — the train's hold reads `blocked` past a later
    `idle` or `planned` (#326). `skip(rec)` true leaves a record out as if it
    were never written — the hold reads past the train's own `blocked`."""
    latest: dict[str, dict] = {}
    for rec in sorted(_report.read_reports(root, remote=remote), key=lambda r: r.get("epoch", 0)):
        if (states is None or rec.get("state") in states) and not (skip and skip(rec)):
            latest[rec["worker"]] = rec
    now = time.time()
    out = []
    for rec in sorted(latest.values(), key=lambda r: r.get("epoch", 0), reverse=True):
        rec = dict(rec)
        rec["minutes_ago"] = int((now - rec.get("epoch", now)) // 60)
        out.append(rec)
    return out


# --- in progress (v2.97 B2): one rule, for the WIP limit of dispatch and `process_kpis.py intake` ---

# a worker whose last report says this holds no issue; `review-pass` holds one (the work waits for
# the train) — `PARKED` is the rule of a live session's silence, not of this
REPORT_OVER = ("done", "idle", "failed")
# no report and no dispatch record of an issue for this long: dormant — shown, never counted.
# "stale" stays the rule of a silent live session (`quiet_too_long`, STALE_MINUTES)
DORMANT_DAYS = 14
FETCH_TIMEOUT_S = 15  # the deadline of the fetch before the count (dispatch: also of its sync)
UNDERCOUNT_NOTE = "other hosts not read — may undercount"


def _issue_number(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return int(value) if isinstance(value, str) and value.isdigit() else None


def _epoch_of(value: object) -> float:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0.0


def _track_of(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def issue_facts(root: Path, issue: int, *, reports: list[dict] | None = None,
                recs: list[dict] | None = None) -> tuple[str | None, float | None]:
    """(track, claim) of one issue, the one rule for `in_progress` and dispatch. The track: the phase
    history `phases/<issue>.json`, else the newest report or dispatch record of the issue that names
    one, else None (untracked). The claim: the earliest phase start of any branch in the history,
    else the issue's earliest report (every host's, as last fetched), else None; no `gh`.
    `reports` and `recs` are the issue's own, when the caller has read them."""
    import dispatch as _dispatch  # noqa: PLC0415 — the phase histories' owner
    if reports is None:
        reports = [r for r in _report.read_reports(root, remote=True) if _issue_number(r.get("issue")) == issue]
    if recs is None:
        recs = [r for r in _dispatch._record_files(root) if _issue_number(r.get("issue")) == issue]
    history = _dispatch.issue_history(root, issue)
    named = [(_epoch_of(r.get("epoch")), t) for r in reports if (t := _track_of(r.get("track")))] + [
        (_epoch_of(r.get("started")), t) for r in recs if (t := _track_of(r.get("track")))]
    track = _dispatch.history_track(history) or (max(named, key=lambda x: x[0])[1] if named else None)
    starts = _dispatch.history_starts(history)
    claimed = min(starts) if starts else (min(_epoch_of(r.get("epoch")) for r in reports) if reports else None)
    return track, claimed


def in_progress(root: Path, *, fetch: bool = True, now: float | None = None,
                timeout: float = FETCH_TIMEOUT_S) -> dict:
    """The issues in progress over every host, the one rule (v2.97; it replaces the reading of
    v2.96 `intake`): the issue of each worker's last report whose state is not `done`, `idle` or
    `failed`, and the issue of a dispatch record no report of its branch followed since its start
    (a hand-over to another host, `state: remote`, among them). An issue with neither a report nor
    a record for DORMANT_DAYS is `dormant`: listed apart, not counted.

    Per issue: its `track` (the phase history `phases/<issue>.json`, else the newest report or
    record of the issue that names one; None is untracked and counts against no track), its claim
    (`claimed`: the earliest phase start of any branch in the history, else its earliest report),
    the newest word (`state`, `worker`, `host`, `source` report|record, `remote`) and `last`, the
    epoch of its newest report or record. `fetch` first fetches the other hosts' published reports
    (`report.fetch_reports`, `timeout` s); without it they are read as last fetched. `hosts` gives
    the age in minutes of each other host's newest report, `notes` what the count may miss.
    Reads `dispatch.records` and `report.read_reports` directly — never `sessions` — and no `gh`."""
    import dispatch as _dispatch  # noqa: PLC0415 — the records' and phase histories' owner
    now = time.time() if now is None else now
    fetched = _report.fetch_reports(root, timeout=timeout) if fetch else None
    own = _report.host_name()
    reports = sorted(_report.read_reports(root, remote=True), key=lambda r: _epoch_of(r.get("epoch")))
    recs = [r for r in _dispatch.records(root) if _issue_number(r.get("issue")) is not None]
    by_branch = {r["branch"]: r for r in recs}
    latest: dict[str, dict] = {}
    for rec in reports:
        latest[rec["worker"]] = rec
    word: dict[int, dict] = {}

    def take(n: int, seen: dict) -> None:
        if n not in word or seen["last"] >= word[n]["last"]:
            word[n] = seen

    for worker, rec in latest.items():
        n = _issue_number(rec.get("issue"))
        if n is None and worker in by_branch:  # a report without --issue: the session's issue
            n = _issue_number(by_branch[worker].get("issue"))
        if n is None or rec.get("state") in REPORT_OVER:
            continue
        host = str(rec.get("host") or "")
        take(n, {"state": rec.get("state"), "worker": worker, "host": host, "source": "report",
                 "remote": host != own, "last": _epoch_of(rec.get("epoch"))})
    for rec in recs:
        if _dispatch.session_report(rec, reports) is not None:
            continue  # its branch reported since: that word decides
        take(int(_issue_number(rec["issue"]) or 0), {
            "state": rec.get("state"), "worker": rec["branch"], "host": None if rec.get("remote") else own,
            "source": "record", "remote": rec.get("remote") is True, "last": _epoch_of(rec.get("started"))})
    counted: list[dict] = []
    dormant: list[dict] = []
    for n in sorted(word):
        mine = [r for r in reports if _issue_number(r.get("issue")) == n]
        theirs = [r for r in recs if _issue_number(r.get("issue")) == n]
        last = max([_epoch_of(r.get("epoch")) for r in mine] + [_epoch_of(r.get("started")) for r in theirs]
                   + [word[n]["last"]])
        track, claimed = issue_facts(root, n, reports=mine, recs=theirs)
        entry = {"issue": n, "track": track, **word[n], "claimed": claimed, "last": last}
        (dormant if now - last > DORMANT_DAYS * 86400 else counted).append(entry)
    hosts: dict[str, int] = {}
    for rec in reports:
        host = str(rec.get("host") or "")
        if host and host != own:
            hosts[host] = max(0, int((now - _epoch_of(rec.get("epoch"))) // 60))
    notes = [UNDERCOUNT_NOTE] if fetched is False else []
    notes += [f"host {h} as of {m} min ago" for h, m in sorted(hosts.items())]
    return {"in_progress": counted, "dormant": dormant, "fetched": fetched, "hosts": hosts, "notes": notes}


WIP_OVERRIDE_DAYS = 7


def _wip_overrides(root: Path, days: int = WIP_OVERRIDE_DAYS) -> Counter:
    """The WIP overrides dispatch logged (`gate_events`, `gate="wip"`) in the last `days`, per track."""
    import gate_events  # noqa: PLC0415
    path = gate_events.events_path(root)
    since = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=days)
    out: Counter = Counter()
    for name in ((path.name + ".1", path.name) if path else ()):
        try:
            lines = (path.parent / name).read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            try:
                row = json.loads(line)
                when = _dt.datetime.fromisoformat(str(row.get("ts")))
            except (ValueError, AttributeError):
                continue
            if (row.get("gate") == "wip" and row.get("outcome") == "override" and when.tzinfo
                    and when >= since and isinstance(row.get("track"), str)):
                out[row["track"]] += 1
    return out


def wip(root: Path) -> list[dict]:
    """One row per track of the mandate's `steering` block — its limit, the issues in progress on it
    (`in_progress`, as last fetched) and the WIP overrides of the last 7 days — plus `untracked`
    when work carries no track. [] without the block. The tower decides nothing: dispatch refuses."""
    import optimize  # noqa: PLC0415 — the steering block's one reader
    settings, _problems = optimize.steering(root)
    if not settings:
        return []
    work = in_progress(root, fetch=False)["in_progress"]
    overrides = _wip_overrides(root)
    names = list(dict.fromkeys([*(settings.get("tracks") or {}), optimize.PROCESS_TRACK,
                                *sorted(e["track"] for e in work if e["track"])]))
    rows = []
    for name in names:
        key = "process_issues_in_progress" if name == optimize.PROCESS_TRACK else "wip_per_track"
        rows.append({"track": name, "limit": settings.get(key),
                     "in_progress": sorted(e["issue"] for e in work if e["track"] == name),
                     "overrides_7d": overrides.get(name, 0)})
    loose = sorted(e["issue"] for e in work if not e["track"])
    if loose:
        rows.append({"track": "untracked", "limit": None, "in_progress": loose, "overrides_7d": 0})
    return rows


# --- the train's hold (#326): one owner, read by the train and shown here (#336) -----------

# the report states that hold a branch (`blocked`) or release it (#326)
HOLD_STATES = ("blocked", "pushed", "review-pass")
# the note the train's own `blocked` starts with (a conflict, red with it aboard):
# it describes a run, not the branch — a conflict with a passenger that never
# landed would hold for nothing — so the hold reads past it. Writer and reader.
TRAIN_DROP_NOTE = "dropped from train"


def _train_written(rec: dict) -> bool:
    return rec.get("state") == "blocked" and str(rec.get("note") or "").startswith(TRAIN_DROP_NOTE)


def train_holds(root: Path) -> dict[str, dict]:
    """The branches the train holds, as {worker: its `blocked` record}: the latest
    word among `blocked`, `pushed` and `review-pass` is `blocked` — this host's
    reports and the ones other hosts published (`refs/process/reports/*`, local
    refs: no network; `fetch_reports` brings them). `idle` (what `dispatch stop`
    writes) and `planned` neither hold nor release, nor does the train's own
    `blocked` (TRAIN_DROP_NOTE). Always with the published refs: a tower without
    `--remote` showed `idle` where the train held (#336)."""
    return {r["worker"]: r for r in latest_reports(root, remote=True, states=HOLD_STATES, skip=_train_written)
            if r["state"] == "blocked"}


def report_identity(rec: dict) -> tuple:
    """A report as the train remembers it at boarding: who, when (as written, never
    compared with a clock), what, why."""
    # strings only: another host's ref is data, and an unhashable field must not crash the
    # train (refute v2.90)
    return (str(rec.get("worker")), str(rec.get("epoch")), str(rec.get("state")), str(rec.get("note") or ""),
            str(rec.get("host") or ""))


def report_ids(root: Path) -> frozenset:
    """The identities of every report the hold reads (`train_holds`'s sources), plus a
    marker per host whose reports were read — a host first seen later brings its whole
    history, which is no news of this run (refute v2.90)."""
    recs = _report.read_reports(root, remote=True)
    return frozenset([report_identity(r) for r in recs] + [("@host", str(r.get("host") or "")) for r in recs])


def held_since(root: Path, seen: frozenset) -> dict[str, dict]:
    """Who must leave a train before its push (#335), as {worker: the record that
    holds it}: an effective hold now (`train_holds`), or a `blocked` that was not
    among `seen` (`report_ids` at boarding), from a host whose reports boarding read —
    even when a release followed: that release is for the worker's new tip, not for
    the one the train boarded; a host first read now counts by its effective holds
    only. The
    sets are compared, never another host's clock. The train's own `blocked`
    holds nothing."""
    held = dict(train_holds(root))
    for rec in sorted(_report.read_reports(root, remote=True), key=lambda r: r.get("epoch", 0)):
        host = str(rec.get("host") or "")
        # this host's own file is always read: its records are never "first seen"
        known_host = host == _report.host_name() or ("@host", host) in seen
        if (rec.get("state") == "blocked" and not _train_written(rec) and known_host
                and report_identity(rec) not in seen):
            held.setdefault(rec["worker"], rec)
    return held


def live_holds(root: Path, ref: str | None) -> list[dict]:
    """`train_holds` for the branches the train would consider — local, not the
    integration branch, not a train's own, ahead of `ref`. A merged or deleted
    branch's hold is history."""
    if not ref:
        return []
    names = set((_git(root, "for-each-ref", "--format=%(refname)", "refs/heads/") or "").split())
    integration = set(INTEGRATION_NAMES) | {ref.removeprefix("origin/")}
    out = []
    for worker, rec in sorted(train_holds(root).items()):
        if f"refs/heads/{worker}" not in names or worker in integration or worker.startswith("train/"):
            continue
        counts = (_git(root, "rev-list", "--left-right", "--count", f"{ref}...refs/heads/{worker}") or "").split()
        if len(counts) == 2 and counts[1].isdigit() and int(counts[1]) > 0:
            out.append(rec)
    return out


ELSEWHERE_DAYS = 14


def remote_branches(root: Path, ref: str | None, local_branches: set[str],
                    max_age_days: int = ELSEWHERE_DAYS) -> tuple[list[dict], int]:
    """Branches on origin that no local worktree carries: work in flight on
    another host. Same shape as a worktree entry, so overlaps and the stale
    finding treat them alike. A branch whose last commit is older than
    `max_age_days` is not in flight, it is residue (observed downstream:
    July branches thousands of commits behind) — counted, not listed."""
    if not ref or not ref.startswith("origin/"):
        return [], 0
    out: list[dict] = []
    old = 0
    local_heads = set()
    for line in (_git(root, "worktree", "list", "--porcelain") or "").splitlines():
        if line.startswith("HEAD "):
            local_heads.add(line.split(" ", 1)[1].strip())
    upstreams = set((_git(root, "for-each-ref", "--format=%(upstream:short)", "refs/heads/") or "").split())
    names = (_git(root, "for-each-ref", "--format=%(refname:short) %(objectname)", "refs/remotes/origin/") or "").splitlines()
    for entry in names:
        full, _, sha = entry.partition(" ")
        b = full.replace("origin/", "", 1)
        if not b or b == "HEAD" or full in _review.integration_refs(root) or b.startswith("train/") or b in local_branches:
            continue
        if sha in local_heads or full in upstreams:
            continue  # a local worktree carries this tip under another name, or tracks it
        counts = _git(root, "rev-list", "--left-right", "--count", f"{ref}...{full}")
        if not counts:
            continue
        behind, ahead = (counts.split() + ["0", "0"])[:2]
        if int(ahead) == 0:
            continue
        last = _git(root, "log", "-1", "--format=%ct", full)
        minutes = int((time.time() - int(last.strip())) // 60) if last and last.strip().isdigit() else 0
        if minutes > max_age_days * 24 * 60:
            old += 1
            continue
        # -z, as paths_in_flight reads the local worktrees: a quoted remote
        # name never meets its local twin (refutation: the overlap vanished)
        files = _review._names(_review._git_bytes(root, "diff", "--name-only", "-z", f"{ref}...{full}"))
        out.append({"branch": b, "remote": True, "ahead": int(ahead), "behind": int(behind),
                    "in_flight": sorted(files or ()), "dirty": 0,
                    "minutes_since_commit": minutes, **({"in_flight_unknown": True} if files is None else {})})
    return out, old


# --- stale: no commit, no report ------------------------------------------------------

def quiet_too_long(minutes_since_commit: int | None, report_minutes_ago: int | None,
                   report_state: str | None, stale_minutes: int,
                   status_minutes_ago: int | None = None) -> bool:
    """The one owner of "stale": no commit, no report and no status-file update
    (a cell's `status_file`, #270) for `stale_minutes`, and not parked on a
    waiting state (`PARKED`). No report or status file at all is quiet; an
    unknown commit age is not. The `stale-worker` finding asks it of a
    worktree, `--wait` of a live session (`stale_sessions`)."""
    if report_state in PARKED:
        return False
    return ((minutes_since_commit or 0) >= stale_minutes
            and (report_minutes_ago is None or report_minutes_ago >= stale_minutes)
            and (status_minutes_ago is None or status_minutes_ago >= stale_minutes))


def status_age(path: str | None, now: float) -> int | None:
    """Minutes since a worker's status file says it was `updated_at` — a harness
    that writes events but no commits proves it is alive this way (#270). None
    where there is no file or no readable time: no signal, never a fresh one."""
    if not path:
        return None
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        stamp = datetime.fromisoformat(str(data["updated_at"]).replace("Z", "+00:00"))
    except (OSError, ValueError, KeyError, TypeError):
        return None
    # a naive stamp is local time (`timestamp()` reads it so); a stamp from the future
    # beyond clock skew is a wrong clock, not a fresh sign of life
    ago = now - stamp.timestamp()
    if ago < -CLOCK_SKEW_SECONDS:
        return None
    return max(0, int(ago // 60))


def resolve_stale_minutes(root: Path, given: int | None = None) -> int:
    """The quiet budget: `--stale-minutes`, else PROCESS_STALE_MINUTES, else
    the policy's `stale_minutes` (dispatch owns the policy), else 60."""
    return _resolve_minutes(root, given, "PROCESS_STALE_MINUTES", "stale_minutes", STALE_MINUTES)


def resolve_prompt_minutes(root: Path, given: int | None = None) -> int:
    """How long a permission prompt may stand: `--prompt-minutes`, else
    PROCESS_PROMPT_MINUTES, else the policy's `prompt_minutes`, else 10."""
    return _resolve_minutes(root, given, "PROCESS_PROMPT_MINUTES", "prompt_minutes", PROMPT_MINUTES)


def _resolve_minutes(root: Path, given: int | None, env_name: str, policy_key: str, default: int) -> int:
    """A threshold in minutes from whichever source sets it. A negative one is
    refused (refute v2.87: it read as "at once"); 0 is "at once" on purpose, a
    look at every quiet worker now."""
    if given is not None:
        if given < 0:
            raise SystemExit(f"tower: --{policy_key.replace('_', '-')} must be 0 or more, got {given}")
        return given
    env = os.environ.get(env_name, "").strip()
    if env:
        try:
            value = int(env)
        except ValueError:
            raise SystemExit(f"tower: {env_name} must be an integer, got {env!r}")
        if value < 0:
            raise SystemExit(f"tower: {env_name} must be 0 or more, got {value}")
        return value
    try:
        import dispatch as _dispatch
    except ImportError:
        return default
    return (getattr(_dispatch, policy_key)(root) if hasattr(_dispatch, policy_key) else None) or default


def _epoch_iso(epoch: int | None) -> str | None:
    return _dt.datetime.fromtimestamp(epoch).isoformat(timespec="seconds") if epoch else None


def stale_sessions(root: Path, stale_minutes: int) -> list[dict]:
    """Live dispatched sessions on this host that wrote no report of their own
    and made no commit in their worktree for `stale_minutes`
    (`quiet_too_long`) while their phase is not over (`dispatch.phase_over`)
    — each as a synthetic `stale` record naming the last report, the last
    commit and the last printed line. A session's quiet starts no earlier
    than the session: the previous phase's commit is not its silence.
    `episode` changes with every commit or report, so a session that stirs
    and falls silent again is a new stale episode."""
    try:
        import dispatch as _dispatch
    except ImportError:
        return []
    now = time.time()
    reports = _report.read_reports(root)
    out: list[dict] = []
    for rec in _dispatch.records(root):
        if not rec.get("alive") or rec.get("remote"):
            continue  # gone, or on another host: its reports speak for it
        started = int(rec.get("started") or 0)
        wt = Path(rec["worktree"]) if rec.get("worktree") else None  # Path("") would be the cwd
        last = _git(wt, "log", "-1", "--format=%ct") if wt and wt.is_dir() else None
        commit = int(last.strip()) if last and last.strip().isdigit() else None
        own = _dispatch.session_report(rec, reports)
        own_epoch = int(own.get("epoch") or 0) if own else None
        quiet_commit = int((now - max(commit or 0, started)) // 60)
        quiet_report = None if own_epoch is None else int((now - own_epoch) // 60)
        if not quiet_too_long(quiet_commit, quiet_report, (own or {}).get("state"), stale_minutes,
                              status_age(rec.get("status_file"), now)):
            continue
        if _dispatch.phase_over(root, rec, own, local=True) is True:
            continue  # done with its phase, waiting to be stopped — not silent work
        latest = None  # the branch's last word, of this session or of the phase before
        for r in reports:
            if r.get("worker") == rec["branch"] and (
                    latest is None or int(r.get("epoch") or 0) >= int(latest.get("epoch") or 0)):
                latest = r
        line, _since = _dispatch.last_output(rec)
        quiet = quiet_commit if quiet_report is None else min(quiet_commit, quiet_report)
        out.append({
            "state": "stale", "worker": rec["branch"], "issue": rec.get("issue"), "phase": rec.get("phase"),
            "host": _report.host_name(), "epoch": int(now), "minutes_quiet": quiet,
            "last_report": None if latest is None else {
                "state": latest.get("state"), "at": _epoch_iso(int(latest.get("epoch") or 0)),
                "minutes_ago": int((now - int(latest.get("epoch") or 0)) // 60),
                "note": latest.get("note") or "", "this_session": latest is own},
            "last_commit": _epoch_iso(commit),
            "minutes_since_commit": None if commit is None else int((now - commit) // 60),
            "last_output": line[-200:],
            "episode": f"{started}:{max(commit or 0, own_epoch or 0, started)}",
            "note": f"no report and no commit for {quiet} min — read `dispatch.py log {rec['branch']}`, "
                    f"then nudge it (`dispatch.py say`) or stop it",
        })
    return out


# no allowlist entry for a wait loop: the worker runs one simple command per
# Bash call (dispatch.SHELL_FORM), and that command is what the list names
PROMPT_REMEDY = ("approve it in the session (attach to its tmux window), or put that one simple command on "
                 "the permission allowlist so the next run is not stopped")


def prompt_sessions(root: Path, prompt_minutes: int) -> list[dict]:
    """Live tmux sessions on this host whose screen shows a dialog (`screen`)
    and printed nothing for `prompt_minutes`, while their phase is not over —
    each as a synthetic `prompt` record naming the dialog line. The episode is
    the session, its quiet start (the log's mtime) and the line: a prompt
    answered and raised again after new output is a new one."""
    try:
        import dispatch as _dispatch
    except ImportError:
        return []
    now = time.time()
    reports = _report.read_reports(root)
    out: list[dict] = []
    input_line = _dispatch.prompt_pattern(root) if hasattr(_dispatch, "prompt_pattern") else None
    for rec in _dispatch.records(root):
        if not rec.get("alive") or rec.get("remote"):
            continue
        _last, since, line = screen(_dispatch, rec, input_line)
        if line is None or since is None or since < prompt_minutes:
            continue
        if _dispatch.phase_over(root, rec, _dispatch.session_report(rec, reports), local=True) is True:
            continue  # done with its phase, waiting to be stopped
        log = Path(rec.get("log") or "")
        quiet_since = int(log.stat().st_mtime) if rec.get("log") and log.is_file() else ""
        out.append({
            "state": "prompt", "worker": rec["branch"], "issue": rec.get("issue"), "phase": rec.get("phase"),
            "host": _report.host_name(), "epoch": int(now), "minutes_quiet": since, "line": line[-200:],
            "episode": f"{rec.get('started')}:{quiet_since}:{line}",
            "note": f"at a permission prompt for {since} min — {PROMPT_REMEDY}",
        })
    return out


def announce_stale(root: Path, seen_path: Path, stale_minutes: int) -> list[dict]:
    """The stale sessions not yet announced in their current episode. The
    file keeps exactly the episodes stale now: a session that commits or
    reports drops out, and its next silence is announced again — once."""
    return _announce(seen_path, "stale", lambda: stale_sessions(root, stale_minutes))


def announce_prompts(root: Path, seen_path: Path, prompt_minutes: int) -> list[dict]:
    """The permission prompts not yet announced in their episode, as `announce_stale`."""
    return _announce(seen_path, "prompt", lambda: prompt_sessions(root, prompt_minutes))


def _announce(seen_path: Path, what: str, collect) -> list[dict]:
    try:
        seen = json.loads(seen_path.read_text(encoding="utf-8"))
        seen = seen if isinstance(seen, dict) else {}
    except (OSError, ValueError):
        seen = {}
    try:
        stale = collect()
    except Exception as exc:  # noqa: BLE001 — one odd record must not end every watch at once
        print(f"tower: {what} check skipped ({type(exc).__name__}: {exc})", file=sys.stderr)
        return []
    now_seen = {r["worker"]: r["episode"] for r in stale}
    if now_seen != seen:
        staging = seen_path.with_name(f"{seen_path.name}.{os.getpid()}.tmp")
        try:
            staging.write_text(json.dumps(now_seen), encoding="utf-8")
            os.replace(staging, seen_path)
        except OSError:
            staging.unlink(missing_ok=True)
    return [r for r in stale if seen.get(r["worker"]) != r["episode"]]


# --- findings -----------------------------------------------------------------------

def findings(table: dict, stale_minutes: int, prompt_minutes: int = PROMPT_MINUTES, *,
             share_max: float = PROCESS_HEAVY_SHARE) -> list[dict]:
    out: list[dict] = []
    b = table.get("balance")
    if b and b["commits"] >= BALANCE_MIN_COMMITS and b["process"] / b["commits"] > share_max:
        out.append({"kind": "process-heavy", "severity": "low",
                    "what": f"{b['process']} of {b['commits']} commits in {b['days']} days touch only process "
                            f"records; {b['product']} only product code — above the limit of "
                            f"{100 * share_max:g} %",
                    "because": "the process is outweighing the work it guards — look where the rounds go "
                               "(process_kpis.py rounds) and whether bookkeeping is batched one commit per "
                               "round (testing.md, bookkeeping-only push)"})
    for q in table.get("questions", []):
        out.append({"kind": "question", "severity": "high",
                    "what": f"{q['who']} asks on {q['plan']}"
                            f"{' [' + q['branch'] + (', another host' if q.get('remote') else '') + ']' if q.get('branch') else ''}"
                            f"{' (' + q['issue'] + ')' if q.get('issue') else ''}: {q['question']}",
                    "because": "a worker is waiting for a decision — decide it, or relay one that touches a "
                               "product principle or is destructive to the owner with its options; write the "
                               "answer back as a DECISION line"})
    for o in table["overlaps"]:
        out.append({"kind": "overlap", "severity": "high" if o["kind"] == "file" else "low",
                    "what": f"{o['a']} and {o['b']} both carry {o['kind']}(s): {', '.join(o['paths'][:5])}",
                    "because": "two branches changing the same owner merge last-wins; decide phase-of "
                               "or supersede before both push (mandatory rule 4)"})
    for p in table["plans"]:
        if p.get("kind") == "design" or p["waived"]:
            continue  # brainstorm papers and waived stale plans are not work in flight
        if (p["tier"] or 0) >= 2 and not p["issue"]:
            out.append({"kind": "plan-without-issue", "severity": "high",
                        "what": f"{p['path']}{' on ' + p['branch'] if p.get('branch') else ''} "
                                f"declares tier {p['tier']} but no issue:",
                        "because": "a Tier 2+ item is not Ready without an issue (DoR); the issue gate reds the push"})
        if (p["tier"] or 0) >= 2 and not p["has_decisions_section"]:
            out.append({"kind": "plan-without-decisions", "severity": "medium",
                        "what": f"{p['path']} has no `## Decisions` section",
                        "because": "decisions made in dialogue are lost at compaction unless the plan carries them"})
        if p["tier"] is None:
            out.append({"kind": "plan-without-tier", "severity": "medium",
                        "what": f"{p['path']} declares no tier",
                        "because": "a plan without a tier is invisible to every gate (v2.13.0: hard for active plans)"})
    for g in table["gates"]:
        if g["age_days"] >= RED_AGE_DAYS:
            out.append({"kind": "chronic-red", "severity": "high",
                        "what": f"gate {g['gate']} red since {g['since']} ({g['age_days']} days)"
                                + (f" — {g['reason']}" if g.get("reason") else ""),
                        "because": "a gate red for days is read by nobody; fix it or waive it with a named owner"})
    integration_names = set(INTEGRATION_NAMES)
    ref = table.get("integration_ref") or table.get("integration") or ""
    integration_names.add(ref.removeprefix("origin/"))
    reported = {r["worker"]: r for r in table["reports"]}
    status = {s["branch"]: s.get("status_minutes_ago") for s in table.get("sessions", [])}
    for wt in table["worktrees"] + table.get("elsewhere", []):
        if wt.get("missing") or wt["branch"] in integration_names | {"detached"}:
            continue
        rep = reported.get(wt["branch"])
        if quiet_too_long(wt.get("minutes_since_commit", 0), None if rep is None else rep["minutes_ago"],
                          None if rep is None else rep["state"], stale_minutes, status.get(wt["branch"])) \
                and (wt.get("ahead", 0) or wt.get("dirty", 0)):
            out.append({"kind": "stale-worker", "severity": "medium",
                        "what": f"{wt['branch']}{' (another host)' if wt.get('remote') else ''}: no commit for {wt.get('minutes_since_commit', '?')} min and "
                                f"{'no report' if rep is None else 'last report ' + str(rep['minutes_ago']) + ' min ago (' + rep['state'] + ')'}",
                        "because": "a worker that neither commits nor reports is idle, waiting on a lane, "
                                   "or looping — ask, reassign, or stop it"})
        if wt.get("in_flight_unknown"):
            out.append({"kind": "paths-unknown", "severity": "medium",
                        "what": f"{wt['branch']}{' (another host)' if wt.get('remote') else ''}: git could not "
                                f"list the files it carries",
                        "because": "an overlap with this branch cannot be ruled out — repair the clone "
                                   "(`git fsck`, fetch) before it rides a train"})
        if wt.get("behind", 0) >= BEHIND_LIMIT:
            out.append({"kind": "far-behind", "severity": "low",
                        "what": f"{wt['branch']} is {wt['behind']} commits behind the integration branch",
                        "because": "the merge grows harder every day; rebase before it becomes a conflict session"})
    if table.get("elsewhere_residue"):
        out.append({"kind": "remote-residue", "severity": "low",
                    "what": f"{table['elsewhere_residue']} unmerged branch(es) on origin older than "
                            f"{ELSEWHERE_DAYS} days, not shown as in flight",
                    "because": "a branch nobody has touched for weeks is residue, not work — tidy.py "
                               "prunes merged ones; unmerged ones need an owner or a delete"})
    # a live worker quiet for WAIT_MINUTES waits for input — unless its phase
    # is over (`dispatch.phase_over`, on the session's own report). Waiting on
    # a question it routed (DECISION NEEDED, its own blocked report) is the
    # steward's turn; waiting on one it only asked on its screen reaches
    # nobody (downstream: two questions sat six hours unanswered). A worker
    # on another host shows no screen here: its reports speak for it
    asked = {q.get("branch") for q in table.get("questions", [])}
    for s in table.get("sessions", []):
        # a session that ended after its phase was over is done with it, not
        # dead (#161); cannot be told (None) still reports
        if (s.get("state") in ("dead", "gone") and s.get("report_state") != "done"
                and s.get("phase_over") is not True):
            out.append({"kind": "dead-worker", "severity": "high",
                        "what": f"{s['branch']} ({s.get('phase')}): session {s['state']}, work not done",
                        "because": "the worker cannot report or progress — inspect its work and resume or reassign it"})
        if s.get("model_drift"):
            # an unversioned alias dispatched: the harness resolved the family itself — worth a look, no alarm
            out.append({"kind": "model-drift", "severity": "low" if s.get("model_alias") else "high",
                        "what": f"{s['branch']} ({s.get('phase')}): dispatched {s.get('model')}, its transcript "
                                f"shows {', '.join(s['model_drift'])}",
                        "because": "something overrode the policy (a command file's `model:` frontmatter, a "
                                   "harness default) — one owner for the model: remove the override, "
                                   "model-policy*.json decides"})
        if s.get("defect"):
            out.append({"kind": "session-defect", "severity": "high", "what": s["branch"],
                        "because": s["defect"]})
        quiet = s.get("minutes_since_output")
        if s.get("prompt") and s.get("alive") and s.get("phase_over") is not True:
            # a permission dialog waits on a human at the screen, not on the
            # steward's answer: no question-unrouted beside it (#377)
            if quiet is not None and quiet >= prompt_minutes:
                out.append({"kind": "permission-prompt", "severity": "high",
                            "what": f"{s['branch']} ({s.get('phase')}) sits at a permission prompt for "
                                    f"{quiet} min: {s['prompt'][:160]}",
                            "because": f"a tmux worker stops at a tool it may not use until someone answers — "
                                       f"{PROMPT_REMEDY}"})
            continue
        if not s.get("alive") or quiet is None or quiet < WAIT_MINUTES or s.get("phase_over") is True:
            continue
        # its phase end cannot be read (no plan of its own, origin not
        # fetched): still said — a missed waiting worker is the failure this
        # finding exists for — but not as a certainty (refutation both ways)
        unsure = s.get("phase_over") is None
        state = s.get("report_state")
        shown = f": {s['last_output'][-120:]}" if s.get("last_output") else ""
        if s["branch"] in asked or state == "blocked":
            out.append({"kind": "waiting-for-input", "severity": "medium",
                        "what": f"{s['branch']} ({s.get('phase')}) waits for input for {quiet} min on its "
                                f"{'open question' if s['branch'] in asked else 'blocked report'}",
                        "because": "the question is routed — the steward decides and writes the answer back as a "
                                   "DECISION line, or relays it to the owner"})
        else:
            out.append({"kind": "question-unrouted", "severity": "medium" if unsure else "high",
                        "what": f"{s['branch']} ({s.get('phase')}) waits for input for {quiet} min, and its plan "
                                f"carries no DECISION NEEDED"
                                f"{' (whether its phase is over cannot be read)' if unsure else ''}{shown}",
                        "because": "a question on a worker's screen reaches nobody — have it write the question "
                                   "into the plan as DECISION NEEDED and report blocked; the steward decides"})
    for rep in table["reports"]:
        if rep["state"] == "failed":
            # a broken run waits for nobody's answer — every minute is lost (#270)
            out.append({"kind": "failed", "severity": "high",
                        "what": f"{rep['worker']} failed {rep['minutes_ago']} min ago: "
                                f"{rep.get('note') or 'no reason given'}",
                        "because": "the run crashed, timed out or was killed — restart it or hand the work on; "
                                   "a failure is no question to answer"})
        if rep["state"] == "blocked" and rep["minutes_ago"] >= stale_minutes:
            out.append({"kind": "blocked", "severity": "high",
                        "what": f"{rep['worker']} blocked for {rep['minutes_ago']} min: {rep.get('note') or 'no reason given'}",
                        "because": "a blocked worker burns nothing but delivers nothing — unblock or reassign"})
    # a hold the reports above hide (#336): an `idle` or `planned` after the `blocked`, or
    # another host's `blocked` a table without --remote does not list — the train holds the
    # branch all the same. A `blocked` latest report is the finding above, not this one
    shown = {r["worker"]: r["state"] for r in table["reports"]}
    for rec in table.get("holds", []):
        latest = shown.get(rec["worker"])
        if latest == "blocked":
            continue
        out.append({"kind": "train-hold", "severity": "medium",
                    "what": f"{rec['worker']}: the train holds it — `blocked` {rec['minutes_ago']} min ago"
                            f"{' on ' + rec['host'] if rec.get('host') else ''} "
                            f"({rec.get('note') or 'no reason given'}); latest report here: {latest or 'none'}",
                    "because": "`idle` and `planned` release nothing: the branch boards again on a newer "
                               "`pushed` (after the fix) or `review-pass`"})
    order = {"high": 0, "medium": 1, "low": 2}
    return sorted(out, key=lambda f: order[f["severity"]])


def codex_findings(root: Path, wts: list[dict]) -> list[dict]:
    """Two traces of the Codex way out (`tower.md`, "Codex workers"): a `codex
    unavailable <row-id>` skip in an active plan whose row this host never recorded,
    and a block by one model family passed on the same head by another family."""
    import _dispatch_codex as codex_run  # noqa: PLC0415
    from attest_evidence import review_policy  # noqa: PLC0415
    import dispatch as _dispatch  # noqa: PLC0415
    out: list[dict] = []
    known = codex_run.unavailable_ids(_dispatch._records_dir(root))
    rules, _problem = review_policy(root, "HEAD")
    ranks, fams = rules.get("ranks") or {}, rules.get("families") or []
    seen_skips: set[tuple[str, str]] = set()
    lines: dict[tuple[str, str], list[tuple[str, str]]] = {}
    active: set[str] = set()  # work ids of active plans: a block answered and merged is history
    for wt in wts or [{"path": str(root)}]:
        wroot = Path(wt["path"])
        if wt.get("missing") or not wroot.is_dir():
            continue
        for rel, text in _review.record_texts(wroot, _review.PLAN_KINDS) or []:
            active |= {str(w) for w in _review._plan_work_ids(_review.plan_stem(rel), text, include_dedated=True)}
            for m in _review.SKIP_LINE.finditer(text):
                reason = m.group("reason").split()
                if reason[:2] == ["codex", "unavailable"] and len(reason) > 2 and reason[2] not in known:
                    seen_skips.add((rel, reason[2]))
        for f in (wroot / _review.JOURNAL_DIR).glob("**/*.md"):
            for _ln, r in _review.parse_review_lines(f.read_text(encoding="utf-8", errors="replace"))[0]:
                if r.get("head") and r.get("verdict") in ("pass", "block"):
                    entry = (r.get("model") or "", r["verdict"])
                    bucket = lines.setdefault((r["work"], r["head"]), [])
                    if entry not in bucket:
                        bucket.append(entry)
    for rel, row in sorted(seen_skips):
        out.append({"kind": "codex-skip-unmatched", "severity": "low",
                    "what": f"{rel}: `codex unavailable {row}` names no attempt recorded on this host",
                    "because": "a cross-model skip should point at a recorded Codex refusal "
                               "(dispatch records/codex/unavailable.jsonl) — another host may hold it; if none "
                               "does, the skip was never tried"})
    for (work, head), entries in sorted(lines.items()):
        if work.removesuffix("-plan") not in active:
            continue
        fam = {m: codex_run.family(m, ranks, fams) for m, _v in entries}
        blocks = {fam[m] for m, v in entries if v == "block" and fam[m] not in (None, "ranked")}
        passes = [m for m, v in entries if v == "pass" and fam[m] not in blocks]
        if blocks and passes:
            out.append({"kind": "codex-block-overridden", "severity": "high",
                        "what": f"work={work} head {head[:12]}: blocked by {', '.join(sorted(blocks))}, "
                                f"passed by {', '.join(passes)} on the same head",
                        "because": "a second family's block was answered by another family's pass instead of "
                                   "a fix — read the block's findings before the merge"})
    return out


def local_findings(root: Path) -> list[dict]:
    """Additive project checks. Like local gates, these commands are reviewed code."""
    path = root / "docs/process/tower.local.json"
    if not path.exists():
        return []
    out = []
    def error(name, why):
        return {"kind": "local-findings-error", "severity": "high", "what": name,
                "because": why}
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(config, dict):
            raise ValueError("expected an object mapping names to commands")
    except (OSError, ValueError) as exc:
        return [error(str(path.relative_to(root)), str(exc))]
    for name, item in config.items():
        try:
            command = item.get("command") if isinstance(item, dict) else None
            argv = shlex.split(command) if isinstance(command, str) else command
            if not isinstance(argv, list) or not argv or not all(isinstance(a, str) and a for a in argv):
                raise ValueError("command must be a nonempty argv list or quoted command string")
            result = subprocess.run(argv, cwd=root, capture_output=True, text=True, timeout=30,
                                    env=git_environment())
            if result.returncode != 0:
                raise ValueError(f"exit {result.returncode}: {result.stderr[-1000:]}")
            found = json.loads(result.stdout)
            if not isinstance(found, list) or not all(
                    isinstance(f, dict) and f.get("severity") in ("high", "medium", "low")
                    and all(isinstance(f.get(key), str) and f[key].strip() for key in ("kind", "what", "because"))
                    for f in found):
                raise ValueError("output must be a JSON list of kind/severity/what/because findings")
            out.extend({**f, "source": name} for f in found)
        except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
            out.append(error(name, str(exc)))
    return out


# --- assembly -------------------------------------------------------------------------

def build(root: Path, stale_minutes: int = 60, *, remote: bool = False,
          prompt_minutes: int = PROMPT_MINUTES) -> dict:
    fetch_ok = True
    if remote:
        fetch_ok = _git(root, "fetch", "--quiet", "origin") is not None and _report.fetch_reports(root)
    ref = integration_ref(root)
    wts = [describe_worktree(w, ref) for w in worktrees(root)]
    elsewhere, old_remote = remote_branches(root, ref, {w["branch"] for w in wts}) if remote else ([], 0)
    table = {
        "generated": _dt.datetime.now().isoformat(timespec="seconds"),
        "root": str(root),
        "host": _report.host_name(),
        "integration_ref": ref,
        "worktrees": wts,
        "elsewhere": elsewhere,
        "elsewhere_residue": old_remote,
        "overlaps": overlaps(wts + elsewhere, tuple(t.removeprefix("refs/heads/")
                                                    for t in _review.integration_targets(root))),
        "plans": plans_everywhere(root, wts),
        "questions": questions(root, wts, elsewhere),
        "sessions": sessions(root),
        "reviews": reviews_today(root),
        "gates": red_gates(root),
        "lanes": lanes(root),
        "balance": balance(root, ref),
        "reports": latest_reports(root, remote=remote),
        "holds": live_holds(root, ref),
        "wip": wip(root),
        "remote_fetched": fetch_ok if remote else None,
    }
    table["findings"] = (findings(table, stale_minutes, prompt_minutes, share_max=process_share_limit(root)[0])
                         + local_findings(root))
    try:
        table["findings"] += codex_findings(root, wts)
    except Exception as exc:  # noqa: BLE001 — a trace that cannot be read costs a finding, never the table
        table["findings"].append({"kind": "local-findings-error", "severity": "low", "what": "codex traces",
                                  "because": str(exc)})
    if remote and not fetch_ok:
        table["findings"].insert(0, {"kind": "remote-unreachable", "severity": "high",
                                     "what": "fetch from origin failed or timed out — `elsewhere` and "
                                             "other hosts' reports may be stale",
                                     "because": "a table built on an old fetch is confidently wrong; "
                                                "check the network or credentials before acting on it"})
    return table


def render(table: dict) -> str:
    lines = [f"tower — {table['generated']} (integration: {table['integration_ref'] or 'none'})"]
    lines.append(f"worktrees ({len(table['worktrees'])}):")
    for wt in table["worktrees"]:
        if wt.get("missing"):
            lines.append(f"  - {wt['branch']}: (missing)")
            continue
        lines.append(f"  - {wt['branch']}: +{wt.get('ahead', 0)}/-{wt.get('behind', 0)}, "
                     f"{_in_flight_count(wt)} in flight, {wt.get('dirty', 0)} dirty, "
                     f"last commit {wt.get('minutes_since_commit', '?')} min ago")
    for wt in table.get("elsewhere", []):
        lines.append(f"  - {wt['branch']} (another host): +{wt['ahead']}/-{wt['behind']}, "
                     f"{_in_flight_count(wt)} in flight, last commit {wt['minutes_since_commit']} min ago")
    active = [p for p in table["plans"]]
    lines.append(f"plans ({len(active)}): " + ", ".join(
        f"{Path(p['path']).stem}[t{p['tier'] if p['tier'] is not None else '?'}"
        f"{' ' + p['issue'] if p['issue'] else ''}{' d' + str(p['decisions']) if p['decisions'] else ''}]"
        for p in active) if active else "plans: none")
    rv = table["reviews"]
    lines.append(f"reviews today: {sum(rv['pass'].values())} pass, {sum(rv['block'].values())} block")
    if table.get("sessions"):
        lines.append(f"sessions ({len(table['sessions'])}):")
        for s in table["sessions"]:
            lines.append(f"  - {s['branch']}: {s['phase']} #{s['issue']} {s['model']} {s['where']} "
                         f"{s['state'].upper()}"
                         + (f" · {s['minutes_since_output']} min ago: {s['last_output'][-100:]}" if s['last_output'] else ""))
    if table.get("questions"):
        lines.append(f"questions ({len(table['questions'])}):")
        for q in table["questions"]:
            lines.append(f"  - {q['who']} on {Path(q['plan']).stem}"
                         f"{' [' + q['branch'] + ']' if q.get('branch') else ''}: {q['question'][:160]}")
    if table["lanes"]:
        lines.append("lanes: " + "; ".join(table["lanes"]))
    b = table.get("balance")
    if b and b["commits"]:
        pct = lambda n: f"{100 * n // b['commits']}%"  # noqa: E731
        lines.append(f"balance ({b['days']} d on {table['integration_ref']}): {b['commits']} commits — "
                     f"{pct(b['process'])} process only, {pct(b['mixed'])} mixed, {pct(b['product'])} "
                     f"product; {b['landed_product']} of {b['landed']} landed changes carry product code")
    if table["reports"]:
        lines.append("reports: " + "; ".join(
            f"{r['worker']}@{r.get('host', '?')} {r['state']}{' #' + str(r['issue']) if r.get('issue') else ''} ({r['minutes_ago']} min)"
            for r in table["reports"][:12]))
    if table.get("wip"):
        def _wip_row(w: dict) -> str:
            n = len(w["in_progress"])
            said = [", ".join(f"#{i}" for i in w["in_progress"])] if n else []
            if w["overrides_7d"]:
                said.append(f"{w['overrides_7d']} override{'s' if w['overrides_7d'] > 1 else ''} in 7 d")
            return (f"{w['track']} {n}" + (f"/{w['limit']}" if w["limit"] is not None else "")
                    + (f" ({', '.join(said)})" if said else ""))
        lines.append("wip: " + "; ".join(_wip_row(w) for w in table["wip"]))
    if table.get("holds"):
        lines.append("train holds: " + "; ".join(f"{r['worker']} ({r['minutes_ago']} min)" for r in table["holds"]))
    if table["findings"]:
        lines.append(f"findings ({len(table['findings'])}):")
        for f in table["findings"]:
            lines.append(f"  [{f['severity']}] {f['kind']}: {f['what']} — because {f['because']}")
    else:
        lines.append("findings: none")
    return "\n".join(lines)


def wait(root: Path, timeout: float, states: tuple[str, ...], stale_minutes: int = STALE_MINUTES,
         prompt_minutes: int = PROMPT_MINUTES) -> int:
    """Block until this host's reports file gains a line in `states`; print the
    matching records as JSON lines. With `stale` in `states`, a live
    dispatched session silent for `stale_minutes` (`stale_sessions`) ends the
    wait too, as a synthetic `stale` record — once per stale episode, so a
    re-armed watch does not wake on the same silence again; with `prompt`, a
    live tmux session at a permission prompt for `prompt_minutes`
    (`prompt_sessions`), as a synthetic `prompt` record, likewise. Exit 0 on a
    match, 3 on timeout, 2 when `root` is not a git clone. A harness-neutral
    wake: the caller runs it in the background and treats its exit as the
    event. This host only."""
    path = _report.reports_path(root)
    if path is None:
        print("tower: not a git clone — no reports file to wait on", file=sys.stderr)
        return 2
    offset = path.stat().st_size if path.is_file() else 0
    deadline = time.monotonic() + timeout
    # the first look at once
    next_stale = time.monotonic() if "stale" in states or "prompt" in states else None
    while time.monotonic() < deadline:
        time.sleep(1)
        size = path.stat().st_size if path.is_file() else 0
        if size < offset:  # truncated or replaced: start over
            offset = 0
        hits: list[dict] = []
        if size > offset:
            with path.open("rb") as fh:
                fh.seek(offset)
                chunk = fh.read(size - offset)
            complete = chunk.rfind(b"\n") + 1  # a half-written line waits for its newline
            offset += complete
            text = chunk[:complete].decode("utf-8", errors="replace")
            hits = [r for r in _report._parse(text, _report.host_name()) if r["state"] in states]
        if not hits and next_stale is not None and time.monotonic() >= next_stale:
            next_stale = time.monotonic() + STALE_POLL_S
            if "prompt" in states:
                hits += announce_prompts(root, path.parent / PROMPT_SEEN, prompt_minutes)
            if "stale" in states:
                hits += announce_stale(root, path.parent / STALE_SEEN, stale_minutes)
        if hits:
            for rec in hits:
                print(json.dumps(rec, ensure_ascii=False))
            return 0
    return 3


def _states(value: str) -> tuple[str, ...]:
    picked = tuple(s.strip() for s in value.split(",") if s.strip())
    bad = [s for s in picked if s not in WAIT_STATES]
    if bad or not picked:
        raise argparse.ArgumentTypeError(f"unknown state(s) {', '.join(bad) or '(none)'}; "
                                         f"known: {', '.join(WAIT_STATES)}")
    return picked


def main(argv: list[str]) -> int:
    # a path that is not UTF-8 reaches the output as its own bytes
    # (surrogateescape): escaped, never a crash (refutation)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")
    p = argparse.ArgumentParser(prog="tower.py", description=__doc__.split("\n\n")[0])
    p.add_argument("--json", action="store_true")
    p.add_argument("--stale-minutes", type=int, default=None,
                   help="quiet budget for a worker (default: PROCESS_STALE_MINUTES, else the policy's "
                        "`stale_minutes`, else 60)")
    p.add_argument("--prompt-minutes", type=int, default=None,
                   help="how long a tmux worker may sit at a permission prompt (default: "
                        "PROCESS_PROMPT_MINUTES, else the policy's `prompt_minutes`, else 10)")
    p.add_argument("--min-severity", choices=("high", "medium", "low"), default="low",
                   help="drop findings below this severity")
    p.add_argument("--remote", action="store_true", default=os.environ.get("PROCESS_TOWER_REMOTE") == "1",
                   help="fetch origin: branches and reports of other hosts join the table")
    p.add_argument("--section", action="append", default=[], metavar="NAME",
                   help="with --json: print only these top-level keys (repeatable)")
    p.add_argument("--wait", action="store_true",
                   help="block until a report line arrives (or, with `stale` in --states, a live "
                        "session goes stale; with `prompt`, a tmux session sits at a permission "
                        "prompt); exit 0 on a match, 3 on timeout")
    p.add_argument("--timeout", type=float, default=1800, help="--wait: seconds before exit 3")
    p.add_argument("--states", type=_states, default=WAIT_STATES,
                   help="--wait: comma-separated report states that end the wait; `stale` adds "
                        "silent live sessions, `prompt` tmux sessions at a permission prompt")
    p.add_argument("root", nargs="?", default=".")
    a = p.parse_args(argv)
    if a.section and not a.json:
        p.error("--section needs --json")
    if a.wait and (a.json or a.section):
        p.error("--wait prints report lines, never the table: drop --json/--section")
    root = Path(a.root).resolve()
    top = _git(root, "rev-parse", "--show-toplevel")
    if top:
        root = Path(top.strip())
    stale_minutes = resolve_stale_minutes(root, a.stale_minutes)
    prompt_minutes = resolve_prompt_minutes(root, a.prompt_minutes)
    if a.wait:
        return wait(root, a.timeout, a.states, stale_minutes, prompt_minutes)
    table = build(root, stale_minutes, remote=a.remote, prompt_minutes=prompt_minutes)
    keep = {"high": ("high",), "medium": ("high", "medium"), "low": ("high", "medium", "low")}[a.min_severity]
    table["findings"] = [f for f in table["findings"] if f["severity"] in keep]
    if a.section:
        unknown = [k for k in a.section if k not in table]
        if unknown:
            p.error(f"unknown section(s) {', '.join(unknown)}; known: {', '.join(table)}")
        table = {k: table[k] for k in a.section}
    print(json.dumps(table, indent=2, ensure_ascii=False) if a.json else render(table))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
