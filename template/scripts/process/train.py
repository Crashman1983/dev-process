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

Departure: at least `--min-candidates` aboard, or the oldest candidate
has waited longer than `--max-wait-hours`; the test lanes are free where
the project has lanes; and the runner's red ledger names no red gate on
this clone. `--force` departs with whatever boarded.

The run: a staging branch `train/<stamp>` from the integration branch in
its own worktree; candidates merged in order (a conflict drops that
candidate and continues); the process gates and then the full suite run
ONCE on the combined tree. If they fail, the base itself is checked once
(a red main blames nobody), then a bisection over boarding-order prefixes
names the first offender, drops it, and the rest is rebuilt.
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
import re
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling imports
import check_review as _review  # noqa: E402
from gate_invoke import gate_runner_argv, not_runnable_reason  # noqa: E402
import report as _report  # noqa: E402
import tower as _tower  # noqa: E402

ARCHIVE = ".process-work/plans/archive"
JOURNAL = ".process-work/journal"
TRAIN_DIR = "process-train"


_GIT_ENV = dict(os.environ, GIT_TERMINAL_PROMPT="0")


def _git(root: Path, *args: str, check: bool = False) -> subprocess.CompletedProcess:
    try:
        r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                           timeout=300, env=_GIT_ENV)
    except subprocess.TimeoutExpired:
        r = subprocess.CompletedProcess(args, 124, "", f"git {' '.join(args)}: timed out after 300 s")
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
    # the review gate's rule: a de-dated slug may act as a work id only when it
    # is unique across the archive — count them over main's archive and every
    # candidate's additions, so one old pass cannot clear a same-named new plan
    dedated: dict[str, int] = {}
    archived_stems = [Path(r).stem for r in _out(root, "ls-tree", "-r", "--name-only", local, "--", ARCHIVE).splitlines()]
    for b in branches:
        archived_stems += [Path(r).stem for r in _out(root, "diff", "--name-only", "--diff-filter=A",
                                                        f"{base}...{b}", "--", ARCHIVE).splitlines()]
    for st in archived_stems:
        key = _review.DATE_PREFIX.sub("", st)
        dedated[key] = dedated.get(key, 0) + 1
    boarded_files: set[str] = set()
    out: list[dict] = []
    for b in sorted(branches):
        counts = _out(root, "rev-list", "--left-right", "--count", f"{base}...{b}")
        behind, ahead = (counts.split() + ["0", "0"])[:2] if counts else ("0", "0")
        c: dict = {"branch": b, "ahead": int(ahead), "behind": int(behind), "eligible": False,
                   "reasons": [], "plans": [], "by": None}
        if int(ahead) == 0:
            continue  # already merged (or empty) — residue for tidy.py, not a candidate
        files = set(_out(root, "diff", "--name-only", f"{base}...{b}").splitlines())
        c["files"] = len(files)
        last = _out(root, "log", "-1", "--format=%ct", b)
        c["hours_waiting"] = round((time.time() - int(last)) / 3600, 1) if last.isdigit() else None
        archived = [p for p in _out(root, "diff", "--name-only", "--diff-filter=A", f"{base}...{b}",
                                     "--", ARCHIVE).splitlines() if p.endswith(".md")]
        passes = passes_root + _journal_passes_branch(root, base, b)
        cleared_all = bool(archived)
        for rel in archived:
            text = _review._unfenced(_show(root, b, rel))  # a fenced example is not a declaration
            stem = Path(rel).stem
            tier_m = _review.TIER_DECL.search(text)
            tier = int(tier_m.group(1)) if tier_m else 0
            unique = dedated.get(_review.DATE_PREFIX.sub("", stem), 0) <= 1
            ids = _review._plan_work_ids(stem, text, include_dedated=unique)
            waived = bool(_review.WAIVED.search(text))
            ok = tier < 2 or waived or _review._cleared(passes, ids, tier)
            c["plans"].append({"path": rel, "tier": tier, "cleared": ok, "waived": waived})
            cleared_all = cleared_all and ok
        # a question the owner never answered rides no train: the branch
        # was built on an assumption — answer it (DECISION line) first
        open_q = [rel for rel in _out(root, "diff", "--name-only", f"{base}...{b}", "--", _tower.PLANS_ACTIVE, _tower.SPECS_DIR).splitlines()
                  if rel.endswith(".md") and _tower.QUESTION_LINE.search(_review._unfenced(_show(root, b, rel)))]
        if open_q:
            c["reasons"].append(f"open DECISION NEEDED in {open_q[0]} — answer it as a DECISION line before merging")
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
        if c["by"] and not overlap and not open_q:
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


GATE_RUNNER_REL = "scripts/process/gate_runner.py"


def _run_gates(wt: Path, log) -> bool:
    """Process gates on the tree in `wt`. No runner in the checkout means no
    gates; the start path is gate_invoke's decision, as in finish.py — a bare
    `sys.executable` cannot resolve the runner's PEP-723 dependencies, and the
    crash read as a red main (observed downstream)."""
    if not (wt / GATE_RUNNER_REL).is_file():
        return True
    argv = gate_runner_argv(wt)
    return argv is not None and _sh(wt, shlex.join(argv), log)


def _train_dir(root: Path) -> Path:
    """Logs and bookkeeping: inside the git common dir, never committed."""
    common = Path(_out(root, "rev-parse", "--git-common-dir"))
    if not common.is_absolute():
        common = root / common
    d = common / TRAIN_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def _train_worktree(root: Path) -> Path:
    """The staging worktree is a sibling of the root (`<root>-train`), like
    dispatch's worktrees — NOT under `.git/`: a suite run there met tools
    that skip every path with a `.git` segment and saw an empty tree
    (observed downstream: a file lister that filters `.git`, a gate red
    for a reason nobody could reproduce in the root)."""
    return root.parent / f"{root.name}-train"


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
    if (root / GATE_RUNNER_REL).is_file() and gate_runner_argv(root) is None:
        # "not runnable" is a tooling finding, not "main is red" — surface it
        # before any worktree or base check is paid for
        print(f"train: gate runner not runnable — {not_runnable_reason(root)}", file=sys.stderr)
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
    logfile = _train_dir(root) / f"{stamp}.log"
    print(f"train {stamp}: departing with {', '.join(aboard)} ({p['why']})")
    if dry_run:
        print("train: dry run — no merge, no suite")
        return 0
    try:
        return _run_batch(root, local, p, aboard, stamp, logfile, suite=suite, deploy=deploy, push=push,
                          keep_branches=keep_branches)
    except BaseException:
        wt = _train_worktree(root)
        if wt.exists():
            _git(root, "worktree", "remove", "--force", str(wt))
            print(f"train: aborted — staging worktree removed, branch train/{stamp} kept; log: {logfile}",
                  file=sys.stderr)
        raise


def _run_batch(root: Path, local: str, p: dict, aboard: list[str], stamp: str, logfile: Path, *,
               suite: str | None, deploy: str | None, push: bool, keep_branches: bool) -> int:
    def log(line: str) -> None:
        with logfile.open("a", encoding="utf-8") as fh:
            fh.write(f"{_dt.datetime.now().isoformat(timespec='seconds')} {line}\n")

    base = p["base"]
    # oldest first: boarding order is waiting order, and the bisection below
    # blames by position, so the order must mean something
    waiting = {c["branch"]: c.get("hours_waiting") or 0 for c in p["candidates"]}
    aboard.sort(key=lambda b: -waiting[b])
    blamed: list[str] = []
    conflicted: list[str] = []
    branch = ""

    def attempt(subset: list[str]) -> tuple[bool, list[str], str]:
        wt, br, merged, dropped = build_train(root, base, subset, stamp, log)
        for d in dropped:
            if d not in conflicted:
                conflicted.append(d)
        if not merged:
            return len(subset) == 0 and _base_green(wt), merged, br
        return _run_gates(wt, log) and (_sh(wt, suite, log) if suite else True), merged, br

    def _base_green(wt: Path) -> bool:
        return _run_gates(wt, log) and (_sh(wt, suite, log) if suite else True)

    base_checked = False
    while aboard:
        ok, merged, branch = attempt(aboard)
        aboard = merged
        if ok or not aboard:
            break
        if not base_checked:
            # before blaming anybody: is the base itself red (a broken main,
            # a flaky suite)? Then no candidate is the offender.
            base_checked = True
            if not attempt([])[0]:
                # a red base does not clear the combination either: one more run
                # of the combined tree tells a flaky suite from a broken main
                log("base red — retry of the combined tree")
                ok, merged, branch = attempt(aboard)
                aboard = merged
                if ok:
                    break
                print("train: the combined tree is red twice and the base is red too — the "
                      "integration branch itself is red (gates or suite fail with nobody aboard); "
                      "no candidate blamed, "
                      "nothing merged — fix main first", file=sys.stderr)
                log("base red and combined red on retry — aborted without blame")
                _cleanup(root, stamp)
                return 1
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
    def _report_dropped() -> None:
        for b in conflicted:
            print(f"train: {b} did not board — merge conflict with the batch; its worker rebases (report: blocked)")
            _write(root, "blocked", f"dropped from train {stamp}: merge conflict — rebase onto {local}", b)
        for b in blamed:
            print(f"train: {b} was dropped as the offender — its worker owes a fix (report: blocked)")
            _write(root, "blocked", f"dropped from train {stamp}: red with it aboard", b)

    if not aboard:
        print("train: nothing survived — see " + str(logfile), file=sys.stderr)
        _report_dropped()
        _cleanup(root, stamp)
        return 1
    if _git(root, "merge-base", "--is-ancestor", local, base).returncode != 0:
        print(f"train: local {local} carries commits that are not on {base} — push or drop them first; "
              f"a fast-forward is impossible and the train would publish a {local} without them",
              file=sys.stderr)
        _cleanup(root, stamp)
        return 2
    if push:
        # origin first, local second: a rejected push (branch protection, a
        # race with another push) must leave local main untouched and the
        # train branch in place — never a local main ahead of origin
        # from the staging worktree: a pre-push hook checks the pushed commit
        # against HEAD of the checkout it runs in — from the root that is main
        r = _git(_train_worktree(root), "push", "origin", f"HEAD:{local}")
        if r.returncode != 0:
            log(f"push of {branch} to origin/{local} rejected: {r.stderr.strip()}")
            _git(root, "worktree", "remove", "--force", str(_train_worktree(root)))
            print(f"train: origin rejected the push to {local} — nothing merged locally; the train "
                  f"branch {branch} stays for inspection (branch protection? then open a PR from it):\n"
                  f"{r.stderr.strip()}", file=sys.stderr)
            return 1
        log(f"pushed {branch} as origin/{local}")
    _git(root, "merge", "--ff-only", branch, check=True)
    log(f"{local} fast-forwarded to {branch} ({_out(root, 'rev-parse', '--short', 'HEAD')})")
    print(f"train: {local} → {_out(root, 'rev-parse', '--short', 'HEAD')} with {', '.join(aboard)}"
          + (" (pushed)" if push else ""))
    for b in aboard:
        refs = sorted({int(n) for n in re.findall(r"(?<![\w/])#(\d+)\b",
                                                  _out(root, "log", "--format=%B", f"{base}..{b}"))})
        if refs:
            print(f"train: {b} references issue(s) {', '.join('#' + str(n) for n in refs)} — "
                  "closed by GitHub where a commit says Closes; the steward closes the rest with the merge ref")
            log(f"{b} issues: {refs}")
        try:
            _report.write_report(root, "done", issue=refs[0] if refs else None,
                                 note=f"merged by train {stamp}" + (f"; issues {refs}" if refs else ""), worker=b)
        except SystemExit:
            pass
        if not keep_branches:
            d = _git(root, "branch", "-d", b)
            if d.returncode != 0:
                print(f"train: local branch {b} kept — {d.stderr.strip().splitlines()[-1] if d.stderr.strip() else 'delete refused'} "
                      "(checked out in a worktree?); origin copy kept too", file=sys.stderr)
            elif push:
                _git(root, "push", "origin", "--delete", b)
    _cleanup(root, stamp)
    _report_dropped()
    if deploy:
        if not _sh(root, deploy, log):
            print("train: deploy failed — the merge stands, the deploy does not; see " + str(logfile), file=sys.stderr)
            return 1
    return 0


def _write(root: Path, state: str, note: str, worker: str) -> None:
    try:
        _report.write_report(root, state, issue=None, note=note, worker=worker)
    except SystemExit:
        pass


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
        if local_integration(root) is None:
            # a fresh repo without commits: nothing can board yet — a state, not an error
            print("train plan: hold — no local main/master branch yet (no commits)")
            return 0
        result = plan(root, min_candidates=a.min_candidates, max_wait_hours=a.max_wait_hours)
        print(json.dumps(result, indent=2) if a.json else render_plan(result))
        return 0
    return run(root, suite=a.suite, deploy=a.deploy, push=a.push, min_candidates=a.min_candidates,
               max_wait_hours=a.max_wait_hours, force=a.force, keep_branches=a.keep_branches,
               dry_run=a.dry_run)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
