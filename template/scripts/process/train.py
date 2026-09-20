#!/usr/bin/env python3
"""train — collect finished branches and merge them as one batch behind ONE
full suite, at a good moment, instead of every branch paying its own
full run and deploy.

    uv run scripts/process/train.py plan [--json]        # who may board, why not, ready to depart?
    uv run scripts/process/train.py run --suite "<full suite cmd>" [--deploy "<cmd>"] [--push]
                                       [--min-candidates N] [--max-wait-hours H] [--force]
                                       [--keep-branches] [--dry-run]

Boarding (all computed): a local branch that is not the integration
branch, is ahead of it, and
  * carries an archived plan (added on the branch — `/finish` did its
    archive step) whose Tier 2+ plan is cleared by a REVIEW pass on the
    branch's journal (or is waived), OR whose worker reported
    `review-pass`/`done` (`report.py`) — the pass is then the record, the
    report only the pointer;
  * has no file overlap with a branch already boarded (the earlier
    candidate keeps its seat; overlap = the same file in flight);
  * the runner's red ledger names no gate red for the branch's clone.

Departure: at least `--min-candidates` aboard, or the oldest candidate
has waited longer than `--max-wait-hours`; and the test lanes are free
where the project has lanes. `--force` departs with whatever boarded.

The run: a staging branch `train/<stamp>` from the integration branch in
its own worktree; candidates merged in order (a conflict drops that
candidate and continues); the process gates and then the full suite run
ONCE on the combined tree. If they fail, the last-boarded candidate is
dropped and the train rebuilt (linear back-off — the offender is named).
On green: the integration branch fast-forwards to the train, `--push`
pushes it, merged branches are deleted (unless `--keep-branches`), each
worker gets a `done` report, and `--deploy` runs once. The combination
is new — that is why the batch, not the branch, earns the full run
(`docs/process/testing.md`).

Run from the root worktree on the integration branch with a clean tree.
The train never reviews, never certifies by itself: it merges what the
process already cleared. Sibling imports; stdlib only."""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling imports
import check_review as _review  # noqa: E402
import report as _report  # noqa: E402
import tower as _tower  # noqa: E402

ARCHIVE = ".process-work/plans/archive"
JOURNAL = ".process-work/journal"
TRAIN_DIR = "process-train"


def _git(root: Path, *args: str, check: bool = False) -> subprocess.CompletedProcess:
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise SystemExit(f"train: git {' '.join(args)} failed:\n{r.stderr.strip()}")
    return r


def _out(root: Path, *args: str) -> str:
    r = _git(root, *args)
    return r.stdout.strip() if r.returncode == 0 else ""


def local_integration(root: Path) -> str | None:
    for name in ("main", "master"):
        if _git(root, "rev-parse", "--verify", "--quiet", f"refs/heads/{name}").returncode == 0:
            return name
    return None


def base_ref(root: Path, local: str) -> str:
    """origin/<main> when it exists (after a fetch), else the local branch."""
    remote = f"origin/{local}"
    if _git(root, "rev-parse", "--verify", "--quiet", remote).returncode == 0:
        return remote
    return local


def _show(root: Path, branch: str, path: str) -> str:
    return _out(root, "show", f"{branch}:{path}")


# --- boarding ---------------------------------------------------------------------

def candidates(root: Path, local: str, base: str) -> list[dict]:
    branches = [b.strip().lstrip("* ").strip() for b in _out(root, "branch", "--list", "--format=%(refname:short)").splitlines()]
    branches = [b for b in branches if b and b not in (local,) and not b.startswith("train/")]
    reports = {r["worker"]: r for r in _tower.latest_reports(root)}
    passes_root = _journal_passes_tree(root, local)
    boarded_files: set[str] = set()
    out: list[dict] = []
    for b in sorted(branches):
        counts = _out(root, "rev-list", "--left-right", "--count", f"{base}...{b}")
        behind, ahead = (counts.split() + ["0", "0"])[:2] if counts else ("0", "0")
        c: dict = {"branch": b, "ahead": int(ahead), "behind": int(behind), "eligible": False,
                   "reasons": [], "plans": [], "by": None}
        if int(ahead) == 0:
            c["reasons"].append("nothing ahead of the integration branch")
            out.append(c)
            continue
        files = set(_out(root, "diff", "--name-only", f"{base}...{b}").splitlines())
        c["files"] = len(files)
        last = _out(root, "log", "-1", "--format=%ct", b)
        c["hours_waiting"] = round((time.time() - int(last)) / 3600, 1) if last.isdigit() else None
        archived = [p for p in _out(root, "diff", "--name-only", "--diff-filter=A", f"{base}...{b}",
                                     "--", ARCHIVE).splitlines() if p.endswith(".md")]
        passes = passes_root + _journal_passes_branch(root, base, b)
        cleared_all = bool(archived)
        for rel in archived:
            text = _show(root, b, rel)
            stem = Path(rel).stem
            tier_m = _review.TIER_DECL.search(text)
            tier = int(tier_m.group(1)) if tier_m else 0
            ids = _review._plan_work_ids(stem, text, include_dedated=True)
            waived = bool(_review.WAIVED.search(text))
            ok = tier < 2 or waived or _review._cleared(passes, ids, tier)
            c["plans"].append({"path": rel, "tier": tier, "cleared": ok, "waived": waived})
            cleared_all = cleared_all and ok
        rep = reports.get(b)
        if archived and cleared_all:
            c["by"] = "archived plan + REVIEW pass"
        elif rep and rep["state"] in ("review-pass", "done"):
            c["by"] = f"worker report {rep['state']} ({rep['minutes_ago']} min ago)"
            if archived and not cleared_all:
                c["reasons"].append("archived Tier 2+ plan without a clearing REVIEW pass — the report is not the record")
                c["by"] = None
        elif archived:
            c["reasons"].append("archived Tier 2+ plan without a clearing REVIEW pass (run /review, then attest)")
        else:
            c["reasons"].append("no archived plan on the branch and no review-pass report (run /finish first)")
        overlap = sorted(files & boarded_files)
        if overlap:
            c["reasons"].append(f"overlaps {len(overlap)} file(s) with a branch already aboard: {', '.join(overlap[:3])}")
        if c["by"] and not overlap:
            c["eligible"] = True
            boarded_files |= files
        out.append(c)
    return out


def _journal_passes_tree(root: Path, ref: str) -> list[dict]:
    passes: list[dict] = []
    for rel in _out(root, "ls-tree", "-r", "--name-only", ref, "--", JOURNAL).splitlines():
        if rel.endswith(".md"):
            records, _e = _review.parse_review_lines(_show(root, ref, rel))
            passes += [r for _ln, r in records if r.get("verdict") == "pass"]
    return passes


def _journal_passes_branch(root: Path, base: str, branch: str) -> list[dict]:
    passes: list[dict] = []
    for rel in _out(root, "diff", "--name-only", f"{base}...{branch}", "--", JOURNAL).splitlines():
        if rel.endswith(".md"):
            records, _e = _review.parse_review_lines(_show(root, branch, rel))
            passes += [r for _ln, r in records if r.get("verdict") == "pass"]
    return passes


def departure(cands: list[dict], root: Path, *, min_candidates: int, max_wait_hours: float) -> tuple[bool, str]:
    aboard = [c for c in cands if c["eligible"]]
    if not aboard:
        return False, "nobody aboard"
    lanes = _tower.lanes(root)
    busy = [ln for ln in lanes if "held by" in ln]
    if busy:
        return False, f"lane busy: {busy[0]}"
    reds = [g for g in _tower.red_gates(root) if g["age_days"] >= 0]
    if reds:
        return False, f"gate red on this clone: {', '.join(g['gate'] for g in reds)}"
    if len(aboard) >= min_candidates:
        return True, f"{len(aboard)} aboard (min {min_candidates})"
    oldest = max((c.get("hours_waiting") or 0) for c in aboard)
    if oldest >= max_wait_hours:
        return True, f"oldest candidate waited {oldest} h (max {max_wait_hours})"
    return False, f"{len(aboard)} aboard, oldest {oldest} h — waiting for {min_candidates} or {max_wait_hours} h"


def plan(root: Path, *, min_candidates: int, max_wait_hours: float) -> dict:
    local = local_integration(root)
    if local is None:
        raise SystemExit("train: no local main/master branch")
    _git(root, "fetch", "--quiet", "origin", local)  # best effort; offline is fine
    base = base_ref(root, local)
    cands = candidates(root, local, base)
    ready, why = departure(cands, root, min_candidates=min_candidates, max_wait_hours=max_wait_hours)
    return {"integration": local, "base": base, "candidates": cands, "ready": ready, "why": why}


# --- the run -------------------------------------------------------------------------------

def _sh(cwd: Path, cmd: str, log) -> bool:
    print(f"train: $ {cmd}", flush=True)
    r = subprocess.run(["sh", "-c", cmd], cwd=cwd)
    log(f"$ {cmd} → exit {r.returncode}")
    return r.returncode == 0


def _train_worktree(root: Path) -> Path:
    common = Path(_out(root, "rev-parse", "--git-common-dir"))
    if not common.is_absolute():
        common = root / common
    d = common / TRAIN_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d / "worktree"


def build_train(root: Path, base: str, aboard: list[str], stamp: str, log) -> tuple[Path, str, list[str], list[str]]:
    """Merge candidates onto a fresh staging branch in its own worktree.
    Returns (worktree, branch, merged, dropped_for_conflict)."""
    wt = _train_worktree(root)
    branch = f"train/{stamp}"
    if wt.exists():
        _git(root, "worktree", "remove", "--force", str(wt))
        shutil.rmtree(wt, ignore_errors=True)
    _git(root, "branch", "-D", branch)
    _git(root, "worktree", "add", "-q", "-b", branch, str(wt), base, check=True)
    merged: list[str] = []
    dropped: list[str] = []
    for b in aboard:
        r = _git(wt, "merge", "--no-ff", "--no-edit", "-m", f"train: merge {b}", b)
        if r.returncode == 0:
            merged.append(b)
            log(f"merged {b}")
        else:
            _git(wt, "merge", "--abort")
            dropped.append(b)
            log(f"conflict: {b} dropped ({r.stderr.strip().splitlines()[-1] if r.stderr.strip() else 'merge failed'})")
    return wt, branch, merged, dropped


def run(root: Path, *, suite: str | None, deploy: str | None, push: bool, min_candidates: int,
        max_wait_hours: float, force: bool, keep_branches: bool, dry_run: bool) -> int:
    local = local_integration(root)
    if local is None:
        print("train: no local main/master branch", file=sys.stderr)
        return 2
    head = _out(root, "rev-parse", "--abbrev-ref", "HEAD")
    if head != local:
        print(f"train: run from the root worktree on {local} (currently {head})", file=sys.stderr)
        return 2
    if _out(root, "status", "--porcelain"):
        print("train: the root worktree is not clean — commit or stash first", file=sys.stderr)
        return 2
    p = plan(root, min_candidates=min_candidates, max_wait_hours=max_wait_hours)
    aboard = [c["branch"] for c in p["candidates"] if c["eligible"]]
    if not aboard:
        print(f"train: {p['why']} — nothing to do")
        return 0
    if not p["ready"] and not force:
        print(f"train: holding — {p['why']} (--force departs now)")
        return 0
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M")
    logfile = _train_worktree(root).parent / f"{stamp}.log"
    logfile.parent.mkdir(parents=True, exist_ok=True)

    def log(line: str) -> None:
        with logfile.open("a", encoding="utf-8") as fh:
            fh.write(f"{_dt.datetime.now().isoformat(timespec='seconds')} {line}\n")

    print(f"train {stamp}: departing with {', '.join(aboard)} ({p['why']})")
    if dry_run:
        print("train: dry run — no merge, no suite")
        return 0
    base = p["base"]
    # oldest first: boarding order is waiting order, and the bisection below
    # blames by position, so the order must mean something
    waiting = {c["branch"]: c.get("hours_waiting") or 0 for c in p["candidates"]}
    aboard.sort(key=lambda b: -waiting[b])
    blamed: list[str] = []
    branch = ""

    def attempt(subset: list[str]) -> tuple[bool, list[str], str]:
        wt, br, merged, _conflicted = build_train(root, base, subset, stamp, log)
        if not merged:
            return False, merged, br
        gates_ok = _sh(wt, f"{sys.executable} scripts/process/gate_runner.py", log) \
            if (wt / "scripts/process/gate_runner.py").is_file() else True
        ok = gates_ok and (_sh(wt, suite, log) if suite else True)
        return ok, merged, br

    while aboard:
        ok, merged, branch = attempt(aboard)
        aboard = merged
        if ok or not aboard:
            break
        # the combination is red: find the first candidate whose prefix turns
        # it red (bisection over prefixes — O(log n) suite runs per offender),
        # drop it, and try the rest. Order is boarding order, so "first red
        # prefix" names the offender, not whoever happened to board last.
        lo, hi = 1, len(aboard)
        while lo < hi:
            mid = (lo + hi) // 2
            pok, pmerged, _br = attempt(aboard[:mid])
            if pok and len(pmerged) == mid:
                lo = mid + 1
            else:
                hi = mid
        offender = aboard[lo - 1]
        blamed.append(offender)
        log(f"red with {offender} aboard — dropped, rebuilding")
        print(f"train: red with {offender} aboard — dropping it and rebuilding")
        aboard = [b for b in aboard if b != offender]
    if not aboard:
        print("train: nothing survived — see " + str(logfile), file=sys.stderr)
        _cleanup(root, stamp)
        return 1
    _git(root, "merge", "--ff-only", branch, check=True)
    log(f"{local} fast-forwarded to {branch} ({_out(root, 'rev-parse', '--short', 'HEAD')})")
    print(f"train: {local} → {_out(root, 'rev-parse', '--short', 'HEAD')} with {', '.join(aboard)}")
    if push:
        _git(root, "push", "origin", local, check=True)
        log(f"pushed {local}")
    for b in aboard:
        try:
            _report.write_report(root, "done", issue=None, note=f"merged by train {stamp}", worker=b)
        except SystemExit:
            pass
        if not keep_branches:
            _git(root, "branch", "-d", b)
            if push:
                _git(root, "push", "origin", "--delete", b)
    _cleanup(root, stamp)
    if deploy:
        if not _sh(root, deploy, log):
            print("train: deploy failed — the merge stands, the deploy does not; see " + str(logfile), file=sys.stderr)
            return 1
    for b in blamed:
        print(f"train: {b} was dropped as the offender — its worker owes a fix (report: blocked)")
        try:
            _report.write_report(root, "blocked", issue=None,
                                 note=f"dropped from train {stamp}: red with it aboard", worker=b)
        except SystemExit:
            pass
    return 0


def _cleanup(root: Path, stamp: str) -> None:
    wt = _train_worktree(root)
    _git(root, "worktree", "remove", "--force", str(wt))
    shutil.rmtree(wt, ignore_errors=True)
    _git(root, "branch", "-D", f"train/{stamp}")


def render_plan(p: dict) -> str:
    lines = [f"train plan — base {p['base']}: {'READY' if p['ready'] else 'hold'} ({p['why']})"]
    for c in p["candidates"]:
        mark = "✓" if c["eligible"] else "·"
        extra = f" — {c['by']}" if c.get("by") and c["eligible"] else ""
        lines.append(f"  {mark} {c['branch']} (+{c['ahead']}/-{c['behind']}, {c.get('files', 0)} file(s), "
                     f"{c.get('hours_waiting', '?')} h){extra}")
        for r in c["reasons"]:
            lines.append(f"      - {r}")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="train.py", description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="command", required=True)
    for name in ("plan", "run"):
        s = sub.add_parser(name)
        s.add_argument("--min-candidates", type=int, default=int(os.environ.get("PROCESS_TRAIN_MIN", "3")))
        s.add_argument("--max-wait-hours", type=float, default=float(os.environ.get("PROCESS_TRAIN_MAX_WAIT_H", "4")))
        s.add_argument("--root", default=".")
    sub.choices["plan"].add_argument("--json", action="store_true")
    r = sub.choices["run"]
    r.add_argument("--suite", help="the full suite command, run once on the combined tree")
    r.add_argument("--deploy", help="run once after the fast-forward (and push)")
    r.add_argument("--push", action="store_true")
    r.add_argument("--force", action="store_true", help="depart regardless of min/max-wait")
    r.add_argument("--keep-branches", action="store_true")
    r.add_argument("--dry-run", action="store_true")
    a = p.parse_args(argv)
    root = Path(_out(Path(a.root).resolve(), "rev-parse", "--show-toplevel") or a.root).resolve()
    if a.command == "plan":
        result = plan(root, min_candidates=a.min_candidates, max_wait_hours=a.max_wait_hours)
        print(json.dumps(result, indent=2) if a.json else render_plan(result))
        return 0
    return run(root, suite=a.suite, deploy=a.deploy, push=a.push, min_candidates=a.min_candidates,
               max_wait_hours=a.max_wait_hours, force=a.force, keep_branches=a.keep_branches,
               dry_run=a.dry_run)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
