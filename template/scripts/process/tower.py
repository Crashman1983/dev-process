#!/usr/bin/env python3
"""tower — the situation table for parallel work on one clone, computed,
never narrated.

    uv run scripts/process/tower.py            # short text: worktrees, findings
    uv run scripts/process/tower.py --json     # the full table for an agent
    uv run scripts/process/tower.py --stale-minutes 60
    uv run scripts/process/tower.py --remote   # other hosts: their branches on origin, their published reports

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
  lanes      — `scripts/lane.py status` where the project has it
  reports    — the latest state each worker reported (`report.py`)
  findings   — deterministic, each with a because: overlaps, a Tier 2+ plan
               without an issue, a plan without a Decisions ledger, a gate
               red for days, a worker with no report and no commit for an
               hour, a branch far behind the integration branch

The tower decides nothing. It is the input an orchestrating agent reads
instead of the sessions themselves — compact, testable, and the same on
every run. Sibling imports; stdlib only."""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling imports
import check_review as _review  # noqa: E402
import report as _report  # noqa: E402

INTEGRATION = ("origin/main", "origin/master", "main", "master")
PLANS_ACTIVE = ".process-work/plans"
SPECS_DIR = "specs"
DESIGN_CONTRACT = re.compile(r"^\s*(?:[-*+]\s+)?[*_]*design-contract[*_]*\s*:\s*(\S+)",
                             re.IGNORECASE | re.MULTILINE)
DECISION_LINE = re.compile(r"^\s*(?:[-*+]\s+)?DECISION\s+\d{4}-\d{2}-\d{2}\s", re.MULTILINE)
# a worker's question to the owner — lives in the plan, not in a chat
QUESTION_LINE = re.compile(r"^\s*(?:[-*+]\s+)?[*_]*DECISION NEEDED[*_]*\s+(\d{4}-\d{2}-\d{2})(?:\s+([^:\n]+?))?\s*:\s*(.+?)\s*$",
                           re.MULTILINE)  # bold markers and a missing `who` are still a question
BEHIND_LIMIT = 50
PLAN_NAME = re.compile(r"^(\d{4}-\d{2}-\d{2}-|design-)")
RED_AGE_DAYS = 2


def _git(root: Path, *args: str) -> str | None:
    try:
        r = subprocess.run(["git", "-C", str(root), "--no-optional-locks", *args],
                           capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout if r.returncode == 0 else None


def integration_ref(root: Path) -> str | None:
    for ref in INTEGRATION:
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
    d["in_flight"] = sorted(_review.paths_in_flight(path))
    status = _git(path, "status", "--porcelain")
    d["dirty"] = len([ln for ln in (status or "").splitlines() if ln.strip()])
    last = _git(path, "log", "-1", "--format=%ct")
    if last and last.strip().isdigit():
        d["minutes_since_commit"] = int((time.time() - int(last.strip())) // 60)
    return d


BOOKKEEPING = (".process-work/",)  # every branch writes here; sharing it is not a collision
INTEGRATION_NAMES = ("main", "master")


def overlaps(wts: list[dict]) -> list[dict]:
    out: list[dict] = []
    wts = [w for w in wts if w.get("branch") not in INTEGRATION_NAMES and not w.get("missing")]
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
        tier = _review.TIER_DECL.search(text)
        issues = sorted(_review._plan_issue_numbers(text))
        dc = DESIGN_CONTRACT.search(text)
        out.append({
            "path": str(p.relative_to(root)),
            "kind": "design" if p.stem.startswith("design-") else "plan",
            "tier": int(tier.group(1)) if tier else None,
            "issue": f"#{issues[0]}" if issues else None,
            "decisions": len(DECISION_LINE.findall(text)),
            "has_decisions_section": bool(_review.DECISIONS_HEADING.search(text)),
            "design_contract": dc.group(1).strip("`'\"") if dc else None,
            "waived": bool(_review.WAIVED.search(text)),
            "age_days": int((time.time() - p.stat().st_mtime) // 86400),
        })
    return out


def _questions_in(text: str, plan: str, branch: str | None, issue: str | None) -> list[dict]:
    out = []
    for m in QUESTION_LINE.finditer(_review._unfenced(text)):
        out.append({"plan": plan, "branch": branch, "issue": issue, "date": m.group(1),
                    "who": (m.group(2) or "worker").strip(), "question": m.group(3).strip()[:600]})
    return out


def _plan_paths_in_ref(root: Path, ref: str) -> list[str]:
    names = (_git(root, "ls-tree", "-r", "--name-only", ref, "--", PLANS_ACTIVE, SPECS_DIR) or "").splitlines()
    return [n for n in names if (n.startswith(PLANS_ACTIVE + "/") and PLAN_NAME.match(Path(n).name))
            or (n.startswith(SPECS_DIR + "/") and Path(n).name == "plan.md")]


def questions(root: Path, wts: list[dict], elsewhere: list[dict] | None = None) -> list[dict]:
    """Open `DECISION NEEDED <date> <who>: <question — options … recommendation …>`
    lines in active plans — in every worktree of this clone (a worker's plan
    lives in ITS worktree, not the steward's) and in the branches other hosts
    pushed. Answered = the line was rewritten to DECISION. Uncommitted text
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
    for rec in _dispatch.records(root):
        last, since = _dispatch.last_output(rec)
        where = (f"tmux {rec.get('tmux_session')}:{rec.get('tmux_name')}" if rec.get("tmux_window")
                 else f"pid {rec.get('pid')}")
        out.append({"branch": rec["branch"], "phase": rec.get("phase"), "issue": rec.get("issue"),
                    "model": rec.get("model"), "alive": rec["alive"], "state": rec["state"], "where": where,
                    "minutes_since_start": int((time.time() - int(rec.get("started") or time.time())) // 60),
                    "last_output": last[-200:], "minutes_since_output": since})
    return out


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
        gate, day = ln.split(" ", 1)
        try:
            age = (today - _dt.date.fromisoformat(day.strip())).days
        except ValueError:
            age = 0
        out.append({"gate": gate, "since": day.strip(), "age_days": age})
    return out


def lanes(root: Path) -> list[str]:
    lane = root / "scripts" / "lane.py"
    if not lane.is_file():
        return []
    try:
        r = subprocess.run([sys.executable, str(lane), "status"], cwd=root,
                           capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return []
    return [ln for ln in r.stdout.splitlines() if ln.strip()]


def latest_reports(root: Path, *, remote: bool = False) -> list[dict]:
    latest: dict[str, dict] = {}
    for rec in sorted(_report.read_reports(root, remote=remote), key=lambda r: r.get("epoch", 0)):
        latest[rec["worker"]] = rec
    now = time.time()
    out = []
    for rec in sorted(latest.values(), key=lambda r: r.get("epoch", 0), reverse=True):
        rec = dict(rec)
        rec["minutes_ago"] = int((now - rec.get("epoch", now)) // 60)
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
        if not b or b in ("HEAD", "main", "master") or b.startswith("train/") or b in local_branches:
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
        files = (_git(root, "diff", "--name-only", f"{ref}...{full}") or "").splitlines()
        out.append({"branch": b, "remote": True, "ahead": int(ahead), "behind": int(behind),
                    "in_flight": sorted(f for f in files if f.strip()), "dirty": 0,
                    "minutes_since_commit": minutes})
    return out, old


# --- findings -----------------------------------------------------------------------

def findings(table: dict, stale_minutes: int) -> list[dict]:
    out: list[dict] = []
    for q in table.get("questions", []):
        out.append({"kind": "question", "severity": "high",
                    "what": f"{q['who']} asks on {q['plan']}"
                            f"{' [' + q['branch'] + (', another host' if q.get('remote') else '') + ']' if q.get('branch') else ''}"
                            f"{' (' + q['issue'] + ')' if q.get('issue') else ''}: {q['question']}",
                    "because": "a worker is waiting for a decision only the owner can take — relay it with its "
                               "options now, write the answer back as a DECISION line"})
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
                        "what": f"{p['path']} declares tier {p['tier']} but no issue:",
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
                        "what": f"gate {g['gate']} red since {g['since']} ({g['age_days']} days)",
                        "because": "a gate red for days is read by nobody; fix it or waive it with a named owner"})
    reported = {r["worker"]: r for r in table["reports"]}
    for wt in table["worktrees"] + table.get("elsewhere", []):
        if wt.get("missing") or wt["branch"] in ("main", "master", "detached"):
            continue
        rep = reported.get(wt["branch"])
        quiet_commit = wt.get("minutes_since_commit", 0) >= stale_minutes
        quiet_report = rep is None or rep["minutes_ago"] >= stale_minutes
        parked = rep is not None and rep["state"] in ("review-pass", "done", "idle")  # waiting, not working
        if quiet_commit and quiet_report and not parked and (wt.get("ahead", 0) or wt.get("dirty", 0)):
            out.append({"kind": "stale-worker", "severity": "medium",
                        "what": f"{wt['branch']}{' (another host)' if wt.get('remote') else ''}: no commit for {wt.get('minutes_since_commit', '?')} min and "
                                f"{'no report' if rep is None else 'last report ' + str(rep['minutes_ago']) + ' min ago (' + rep['state'] + ')'}",
                        "because": "a worker that neither commits nor reports is idle, waiting on a lane, "
                                   "or looping — ask, reassign, or stop it"})
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
    for rep in table["reports"]:
        if rep["state"] == "blocked" and rep["minutes_ago"] >= stale_minutes:
            out.append({"kind": "blocked", "severity": "high",
                        "what": f"{rep['worker']} blocked for {rep['minutes_ago']} min: {rep.get('note') or 'no reason given'}",
                        "because": "a blocked worker burns nothing but delivers nothing — unblock or reassign"})
    order = {"high": 0, "medium": 1, "low": 2}
    return sorted(out, key=lambda f: order[f["severity"]])


# --- assembly -------------------------------------------------------------------------

def build(root: Path, stale_minutes: int = 60, *, remote: bool = False) -> dict:
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
        "overlaps": overlaps(wts + elsewhere),
        "plans": plans(root),
        "questions": questions(root, wts, elsewhere),
        "sessions": sessions(root),
        "reviews": reviews_today(root),
        "gates": red_gates(root),
        "lanes": lanes(root),
        "reports": latest_reports(root, remote=remote),
        "remote_fetched": fetch_ok if remote else None,
    }
    table["findings"] = findings(table, stale_minutes)
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
                     f"{len(wt.get('in_flight', []))} file(s) in flight, {wt.get('dirty', 0)} dirty, "
                     f"last commit {wt.get('minutes_since_commit', '?')} min ago")
    for wt in table.get("elsewhere", []):
        lines.append(f"  - {wt['branch']} (another host): +{wt['ahead']}/-{wt['behind']}, "
                     f"{len(wt['in_flight'])} file(s) in flight, last commit {wt['minutes_since_commit']} min ago")
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
    if table["reports"]:
        lines.append("reports: " + "; ".join(
            f"{r['worker']}@{r.get('host', '?')} {r['state']}{' #' + str(r['issue']) if r.get('issue') else ''} ({r['minutes_ago']} min)"
            for r in table["reports"][:12]))
    if table["findings"]:
        lines.append(f"findings ({len(table['findings'])}):")
        for f in table["findings"]:
            lines.append(f"  [{f['severity']}] {f['kind']}: {f['what']} — because {f['because']}")
    else:
        lines.append("findings: none")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="tower.py", description=__doc__.split("\n\n")[0])
    p.add_argument("--json", action="store_true")
    p.add_argument("--stale-minutes", type=int, default=int(os.environ.get("PROCESS_STALE_MINUTES", "60")))
    p.add_argument("--min-severity", choices=("high", "medium", "low"), default="low",
                   help="drop findings below this severity")
    p.add_argument("--remote", action="store_true", default=os.environ.get("PROCESS_TOWER_REMOTE") == "1",
                   help="fetch origin: branches and reports of other hosts join the table")
    p.add_argument("root", nargs="?", default=".")
    a = p.parse_args(argv)
    root = Path(a.root).resolve()
    top = _git(root, "rev-parse", "--show-toplevel")
    if top:
        root = Path(top.strip())
    table = build(root, a.stale_minutes, remote=a.remote)
    keep = {"high": ("high",), "medium": ("high", "medium"), "low": ("high", "medium", "low")}[a.min_severity]
    table["findings"] = [f for f in table["findings"] if f["severity"] in keep]
    print(json.dumps(table, indent=2, ensure_ascii=False) if a.json else render(table))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
