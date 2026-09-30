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
  * carries an archived plan of its OWN (added on the branch — `/finish`
    did its archive step) whose Tier 2+ plan is cleared by a REVIEW pass on
    the branch's journal that COVERS the branch head (or is waived), OR whose
    worker reported `review-pass` and a REVIEW pass for its own work covers
    the head — the pass is the record, the report only the pointer. A `done`
    report (what a train writes after merging) boards nothing: new commits
    after a merge need their own review. Own = the plan names the branch (its issue
    number or slug is in the branch name) or did not exist on the base; a
    plan of other work the branch merely archives is housekeeping and
    clears nothing;
  * changes the gates' code (`scripts/process/`, `.githooks/`) only with a
    REVIEW pass for its own work, whatever the tier;
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
import posixpath
import re
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, NamedTuple

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling imports
import check_review as _review  # noqa: E402
from gate_invoke import gate_runner_argv, not_runnable_reason  # noqa: E402
import report as _report  # noqa: E402
import tower as _tower  # noqa: E402

ARCHIVE = ".process-work/plans/archive"
PLANS = ".process-work/plans"
# the gates' own code: a branch that changes it boards only on a REVIEW pass
# for its own work — never on a Tier 0-1 plan, a waiver or a worker report
PROCESS_PATHS = ("scripts/process/", ".githooks/")
JOURNAL = ".process-work/journal"
TRAIN_DIR = "process-train"


# The route marker the pre-push guard reads to tell the train's push to main
# from any other (owner of the name: merge_route.py). Set for that one push
# only, never in _GIT_ENV — and never inherited: the train's own push runs the
# gates under this marker, so a train started there would otherwise carry it
# into every git call.
MERGE_ROUTE_ENV = "PROCESS_MERGE_ROUTE"
MERGE_ROUTE = "train"
_GIT_ENV = {**{k: v for k, v in os.environ.items() if k != MERGE_ROUTE_ENV},
            "GIT_TERMINAL_PROMPT": "0"}


def _git(root: Path, *args: str, check: bool = False,
         env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    try:
        r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                           timeout=300, env=_GIT_ENV if env is None else {**_GIT_ENV, **env})
    except subprocess.TimeoutExpired:
        r = subprocess.CompletedProcess(args, 124, "", f"git {' '.join(args)}: timed out after 300 s")
    if check and r.returncode != 0:
        raise SystemExit(f"train: git {' '.join(args)} failed:\n{r.stderr.strip()}")
    return r


def _out(root: Path, *args: str) -> str:
    r = _git(root, *args)
    return r.stdout.strip() if r.returncode == 0 else ""


def _git_bytes(root: Path, *args: str) -> bytes | None:
    """git's raw stdout (for `-z` output), None when git failed."""
    try:
        r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, timeout=300, env=_GIT_ENV)
    except subprocess.TimeoutExpired:
        return None
    return r.stdout if r.returncode == 0 else None


def _paths(root: Path, *args: str) -> list[str] | None:
    """The path names a git command lists, read NUL-separated through the
    owner (`check_review._names`); every caller passes `-z`. Without it git
    quotes a non-ASCII name, `_show` reads nothing under the quoted name, the
    tier reads 0 and a Tier 2 branch boards unreviewed (downstream
    refutation). None when git failed — the caller refuses, it does not read
    "no files"."""
    names = _review._names(_git_bytes(root, *args))
    return sorted(names) if names is not None else None


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

def _branch_work_ids(branch: str) -> set[str]:
    """The work ids a branch name carries: the name, its last segment and the
    issue number dispatch puts in front (`42-fix-login`, `issue-42`) — not
    every number in it (`process-v2.28.0` names no issue 28)."""
    leaf = branch.rsplit("/", 1)[-1]
    issue = _review.branch_issue(branch)
    return {branch, leaf} | ({issue} if issue else set())


def _branch_issues(root: Path, branch: str) -> set[str]:
    """The issues a branch belongs to: the number its name leads with, and
    every issue dispatch placed on it (`dispatch.issues_of`, the owner of
    that map). Boarding, the plans counted as the branch's own and the
    issues its merge closes all ask this one question (refutation: the
    train boarded a package branch on its issue, then closed the epic's)."""
    import dispatch as _dispatch  # lazily, as tower does
    issue = _review.branch_issue(branch)
    return ({issue} if issue else set()) | {str(i) for i in _dispatch.issues_of(root, branch)}


def _names_branch(branch: str, ids: set[str], issues: set[str]) -> bool:
    """Does a plan with these work ids belong to this branch? Its issue number
    is one of the branch's (`_branch_issues`), or its slug is in the branch
    name (or, long enough to mean something, the other way round)."""
    leaf = branch.rsplit("/", 1)[-1]
    for i in ids:
        tail = i.rsplit("#", 1)[-1]
        if tail.isdigit():
            if tail in issues:
                return True
        elif len(i) >= 3 and (i in leaf or (len(leaf) >= 8 and leaf in i)):
            return True
    return False


def candidates(root: Path, local: str, base: str) -> list[dict]:
    branches = [b.strip().lstrip("* ").strip() for b in _out(root, "branch", "--list", "--format=%(refname:short)").splitlines()]
    branches = [b for b in branches if b and b not in (local,) and not b.startswith("train/")]
    reports = {r["worker"]: r for r in _tower.latest_reports(root)}
    passes_root = _journal_passes_tree(root, local)
    # the review gate's rule: a de-dated slug may act as a work id only when it
    # is unique across the archive — count them over main's archive and every
    # candidate's additions, so one old pass cannot clear a same-named new plan
    dedated: dict[str, int] = {}
    # a name list git could not produce is no empty list: without it the
    # uniqueness count and the base's plans are unknown, and nothing boards
    unreadable: list[str] = []
    listed = _paths(root, "ls-tree", "-r", "-z", "--name-only", local, "--", ARCHIVE)
    if listed is None:
        unreadable.append(f"the archive on {local}")
    archived_stems = [Path(r).stem for r in listed or ()]
    added_by: dict[str, list[str] | None] = {}
    for b in branches:
        added_by[b] = _paths(root, "diff", "--name-only", "-z", "--diff-filter=A", f"{base}...{b}", "--", ARCHIVE)
        archived_stems += [Path(r).stem for r in added_by[b] or ()]
    for st in archived_stems:
        key = _review.DATE_PREFIX.sub("", st)
        dedated[key] = dedated.get(key, 0) + 1
    # a plan the base already carries (active or archived) is another work's —
    # archiving it on a branch is housekeeping, not this branch's clearance
    listed = _paths(root, "ls-tree", "-r", "-z", "--name-only", base, "--", PLANS)
    if listed is None:
        unreadable.append(f"the plans on {base}")
    base_plan_stems = {Path(r).stem for r in listed or ()}
    boarded_files: set[str] = set()
    out: list[dict] = []
    for b in sorted(branches):
        counts = _out(root, "rev-list", "--left-right", "--count", f"{base}...{b}")
        behind, ahead = (counts.split() + ["0", "0"])[:2] if counts else ("0", "0")
        c: dict = {"branch": b, "ahead": int(ahead), "behind": int(behind), "eligible": False,
                   "reasons": [], "plans": [], "by": None}
        if int(ahead) == 0:
            continue  # already merged (or empty) — residue for tidy.py, not a candidate
        listed = _paths(root, "diff", "--name-only", "-z", f"{base}...{b}")
        files = set(listed or ())
        c["files"] = len(files)
        last = _out(root, "log", "-1", "--format=%ct", b)
        c["hours_waiting"] = round((time.time() - int(last)) / 3600, 1) if last.isdigit() else None
        archived = [p for p in added_by[b] or () if p.endswith(".md")]
        branch_unreadable = unreadable + [what for what, names in (
            (f"the files of {b}", listed), (f"the plans {b} archives", added_by[b])) if names is None]
        branch_passes = _journal_passes_branch(root, base, b)
        passes = passes_root + branch_passes
        touches_process = sorted(f for f in files if f.startswith(PROCESS_PATHS))
        # the branch's name and its issues: a REVIEW line of any other work
        # is not this branch's
        issues = _branch_issues(root, b)
        own_ids = _branch_work_ids(b) | issues
        housekeeping: list[str] = []
        own_archived: list[str] = []
        for rel in archived:
            shown = _git(root, "show", f"{b}:{rel}")
            if shown.returncode != 0:
                branch_unreadable.append(f"{rel} on {b}")  # an unread plan is no Tier 0 plan
                continue
            text = _review._unfenced(shown.stdout)  # a fenced example is not a declaration
            stem = Path(rel).stem
            tier_m = _review.TIER_DECL.search(text)
            tier = int(tier_m.group(1)) if tier_m else 0
            unique = dedated.get(_review.DATE_PREFIX.sub("", stem), 0) <= 1
            ids = _review._plan_work_ids(stem, text, include_dedated=unique)
            if not (_names_branch(b, ids, issues) or stem not in base_plan_stems):
                housekeeping.append(rel)  # another work's plan, only moved to the archive here
                continue
            own_archived.append(rel)
            own_ids |= ids
            waived = bool(_review.WAIVED.search(text))
            ok = tier < 2 or waived or _covers(root, passes, ids, tier, b, branch_passes)
            if touches_process and not _covers(root, passes, ids, 2, b, branch_passes):
                ok = False
            c["plans"].append({"path": rel, "tier": tier, "cleared": ok, "waived": waived})
        archived = own_archived
        cleared_all = bool(archived) and all(p["cleared"] for p in c["plans"])
        if housekeeping:
            c["housekeeping"] = housekeeping
        # a question the owner never answered rides no train: the branch
        # was built on an assumption — answer it (DECISION line) first
        active = _paths(root, "diff", "--name-only", "-z", f"{base}...{b}", "--", _tower.PLANS_ACTIVE, _tower.SPECS_DIR)
        if active is None:
            branch_unreadable.append(f"the active plans of {b}")
        open_q = []
        for rel in (r for r in active or () if r.endswith(".md")):
            shown = _git(root, "show", f"{b}:{rel}")
            if shown.returncode != 0:
                branch_unreadable.append(f"{rel} on {b}")  # an unread plan hides its open question
            elif _tower.QUESTION_LINE.search(_review._unfenced(shown.stdout)):
                open_q.append(rel)
        if open_q:
            c["reasons"].append(f"open DECISION NEEDED in {open_q[0]} — answer it as a DECISION line before merging")
        if branch_unreadable:
            c["reasons"].append(f"git could not read {', '.join(branch_unreadable)} — an unread name or plan "
                                f"is no Tier 0 plan; repair the clone (`git fsck`, fetch) and run the train again")
        rep = reports.get(b)
        process_unreviewed = bool(touches_process) and not _covers(root, passes, own_ids, 2, b, branch_passes)
        if process_unreviewed:
            more = f" and {len(touches_process) - 1} more" if len(touches_process) > 1 else ""
            c["reasons"].append(f"changes the gates' code ({touches_process[0]}{more}) without a REVIEW pass "
                                f"at tier 2 or higher for its own work (work= one of {', '.join(sorted(own_ids))}) "
                                f"— gate code needs it whatever the plan's tier")
        elif archived and cleared_all:
            needs_review = [p for p in c["plans"] if p["tier"] is not None and p["tier"] >= 2 and not p["waived"]]
            c["by"] = ("archived plan + REVIEW pass" if needs_review
                       else "archived plan (Tier 0-1 or waived: no review required)")
        elif rep and rep["state"] == "review-pass":
            if archived and not cleared_all:
                c["reasons"].append("archived Tier 2+ plan without a REVIEW pass covering the branch head "
                                    "— the report is not the record")
            elif _covers(root, passes, own_ids, 0, b, branch_passes) and any(r["work"] in own_ids for r in passes):
                c["by"] = f"worker report review-pass ({rep['minutes_ago']} min ago) + REVIEW pass covering the head"
            else:
                c["reasons"].append("report review-pass, but no REVIEW pass for its own work covers the branch "
                                    "head — code after the reviewed head, or no attestation")
        elif archived:
            c["reasons"].append("archived Tier 2+ plan without a REVIEW pass covering the branch head "
                                "(run /review, then attest)")
        elif rep and rep["state"] == "done":
            # `done` is what a train writes after merging: it clears nothing
            # the branch committed since (downstream: a merged branch got new
            # commits and showed as boardable on the old report)
            c["reasons"].append("report `done` boards nothing — commits after a merge need their own "
                                "REVIEW pass (review the new commits, then attest)")
        elif housekeeping:
            c["reasons"].append(f"archives {len(housekeeping)} plan(s) of other work only — none is this "
                                "branch's own, and another work's clearance does not clear this branch")
        else:
            c["reasons"].append("no archived plan on the branch and no review-pass report (run /finish first)")
        overlap = sorted(files & boarded_files)
        if overlap:
            c["reasons"].append(f"overlaps {len(overlap)} file(s) with a branch already aboard: {', '.join(overlap[:3])}")
        if c["by"] and not overlap and not open_q and not branch_unreadable:
            c["eligible"] = True
            boarded_files |= files
        out.append(c)
    return out


def _journal_passes_tree(root: Path, ref: str) -> list[dict]:
    passes: list[dict] = []
    for rel in _paths(root, "ls-tree", "-r", "-z", "--name-only", ref, "--", JOURNAL) or ():
        if rel.endswith(".md"):
            records, _e = _review.parse_review_lines(_show(root, ref, rel))
            passes += [r for _ln, r in records if r.get("verdict") == "pass"]
    return passes


def _covers(root: Path, passes: list[dict], ids: set[str], tier: int, tip: str,
            own: list[dict] | None = None) -> bool:
    """Does a clearing REVIEW pass cover the branch as it stands NOW? A pass
    whose reviewed head is not in the branch, or behind which the branch
    carries code nobody reviewed, clears the plan but not these commits —
    downstream, a branch merged by one train got new commits and boarded the
    next on its old clearance. The same rule as the review gate's stale check
    (`check_review._unreviewed_paths`), judged at the branch tip. Passes
    without a head (older records) count only when no pass for the work has
    one, and only from the branch's OWN journal (`own`): a headless pass on
    main was written for earlier work and cannot vouch for new commits
    (downstream refutation)."""
    req = min(tier, 3)
    clearing = [r for r in passes if r["work"] in ids and int(r["tier"]) >= req]
    with_head = [r for r in clearing if r.get("head")]
    if not with_head:
        if any(r.get("head") for r in passes if r["work"] in ids):
            return False
        own_ids = {id(r) for r in (own or [])}
        return any(id(r) in own_ids for r in clearing)
    for r in with_head:
        if _git(root, "merge-base", "--is-ancestor", r["head"], tip).returncode != 0:
            continue
        late = _review._unreviewed_paths(root, r["head"], tip, _review.work_bases(passes, ids))
        if late is not None and not late:
            return True
    return False


def _journal_passes_branch(root: Path, base: str, branch: str) -> list[dict]:
    passes: list[dict] = []
    for rel in _paths(root, "diff", "--name-only", "-z", f"{base}...{branch}", "--", JOURNAL) or ():
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

# A suite run is judged by ONE rule, `decide`, over facts `read_facts` takes
# from the command, the run's output and the tree. "undefined" — the suite
# does not exist on this tree (a passenger introduces the make target or the
# script) — makes the tree *not comparable*: never red, nobody blamed. Every
# other failure is red. The rule was patched once per case downstream; each
# case is now a row of `decide` and a row of its table test
# (tests/test_train.py). Only the suite's own signals count: the stop lines of
# the suite's OWN make — the level right below the one the train runs at
# (`make train` puts the train at MAKELEVEL 1, so the suite's make prints
# `make[1]:`; run bare, `make:`) —, the train's own `sh` saying a command of
# the suite is not found, and the suite's own entry file missing from the
# tree. A deeper make, or a "not found" printed by a test that shells out, is
# red. `_run_batch` checks the base when a combined tree reads undefined: a
# base that HAS the suite makes that undefined a passenger's removal — red.
# Known limits, each read red (fail closed) unless said otherwise: a
# translated make (run the train with LC_ALL=C if a passenger introduces the
# suite); output redirected away from the train (`make test > log`); a
# target spelled through the shell (`make test-${X}`); a suite behind `;` or
# `||` (only the start of the command and what follows `&&` is the suite's
# own command); `python -m pytest tests/new` (a missing path is a tool's
# argument, not the suite's file). `make nope test` stops before `test` runs:
# undefined, as the suite as written does not exist. A pipe masks the exit
# code (`make test | tee log` is green if tee is) — the command's business.
# This reads text: a test printing make's exact stop line, or a nested make
# with MAKELEVEL cleared, can read undefined; the train then aborts or excuses
# a prefix, it never merges on it.

# make options that take their value as the next word
_MAKE_VALUE_OPTS = {"-C", "-f", "-I", "-o", "-W", "--directory", "--file", "--makefile", "--include-dir",
                    "--old-file", "--assume-old", "--what-if", "--new-file", "--assume-new",
                    "-l", "--load-average", "-E", "--eval"}
_SHELL_PUNCT = set("();<>|&")
_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
# a line that can carry a fact: make's `***` lines, make's include line, "not found"
_FACT_LINE = re.compile(r"\*\*\* |: No such file or directory$|: (?:command )?not found$")
# a line that makes a run red whatever follows: kept without a cap
_RED_LINE = re.compile(r"\*\*\* \[|\*\*\* Waiting for unfinished jobs|, needed by ")
_INTERPRETERS = re.compile(r"^(?:sh|bash|dash|zsh|ksh|python[0-9.]*|node|ruby|perl)$")


class SuiteFacts(NamedTuple):
    """What one suite run says about itself — the inputs of `decide`, gathered
    by `read_facts`. The make facts are read at the suite's own make level,
    over every make call of the command."""
    rc: int                                    # the command's exit code
    targets: frozenset = frozenset()           # what the command asks make for (empty: no make call it can read)
    words: frozenset = frozenset()             # first words of the suite's own commands, not files in the tree
    recipe_failed: bool = False                # `make: *** [file:N: target] Error n`: a defined target failed
    needed_by: bool = False                    # `No rule to make target 'x', needed by 'y'`: a missing prerequisite
    no_rule: frozenset = frozenset()           # `No rule to make target 'T'.`: names make has no rule for
    missing_includes: frozenset = frozenset()  # `Makefile:N: x: No such file or directory`: make's include line
    not_found: frozenset = frozenset()         # the train's `sh: 1: w: not found`: words the shell did not find
    absent: frozenset = frozenset()            # the suite's entry file or directory, missing from the tree


def decide(f: SuiteFacts) -> tuple[str, str]:
    """`(state, reason)`, state "green", "red" or "undefined" — the whole rule;
    the first row that applies decides."""
    if f.rc == 0:
        return "green", "exit 0"
    # any make call failing on a defined target makes the tree red, even when
    # a later call finds no rule (`make test; make -C examples test`)
    if f.recipe_failed:
        return "red", "a make call failed on a defined target"
    if f.needed_by:
        return "red", "a missing prerequisite (a rule needs a file that is gone)"
    # make names the include it cannot find first — also one named like the target
    if f.no_rule & f.missing_includes:
        return "red", "a missing include"
    # the script, makefile or directory the suite starts with is not on this tree
    if f.absent:
        return "undefined", "the suite's own file is not on this tree"
    # every stop is for a target the suite command names: its make target is not here
    if f.rc == 2 and f.no_rule and f.no_rule <= f.targets:
        return "undefined", "no rule for a target the suite command names"
    # the suite's own command is not found (and is no file in the tree: that one is broken)
    if f.rc == 127 and f.not_found & f.words:
        return "undefined", "the suite command itself is not found"
    if f.rc == 127:
        return "red", "exit 127 from a command inside the suite"
    return "red", f"exit {f.rc}"


def _without_substitutions(cmd: str) -> str:
    """`$(…)`, `$((…))` and backticks become the word `0`: their parentheses
    do not split the command (`make -j$(nproc) test` is one make call)."""
    out: list[str] = []
    i, single, double = 0, False, False
    while i < len(cmd):
        c = cmd[i]
        if single:
            single = c != "'"
        elif c == "\\":
            out.append(cmd[i:i + 2])
            i += 2
            continue
        elif c == "'" and not double:
            single = True
        elif c == '"':
            double = not double
        elif cmd.startswith("$(", i) or c == "`":
            j, depth = i + (2 if c == "$" else 1), 1
            while j < len(cmd) and depth:
                if c == "`":
                    depth = 0 if cmd[j] == "`" else 1
                else:
                    depth += {"(": 1, ")": -1}.get(cmd[j], 0)
                j += 1
            out.append("0")
            i = j
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _simple_commands(cmd: str) -> list[tuple[str, list[str]]]:
    """The command's simple commands as (operator before it, words) —
    `(cd x && make t) > log` is `[("", ["cd", "x"]), ("&&", ["make", "t"])]`;
    a redirection's target is no word. Empty when the words cannot be read."""
    try:
        lex = shlex.shlex(_without_substitutions(cmd), posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        tokens = list(lex)
    except ValueError:
        return []
    out: list[tuple[str, list[str]]] = []
    cur: list[str] = []
    sep = pending = ""
    redirect = False
    for w in tokens:
        if set(w) <= _SHELL_PUNCT:  # an operator, a subshell, a redirection
            op = w.replace("(", "").replace(")", "")
            is_redirect = "<" in op or ">" in op
            if cur and ((op and not is_redirect) or op != w):
                out.append((sep, cur))
                cur = []
            if is_redirect:
                redirect = True
            elif op:
                pending = op
            continue
        if redirect:
            redirect = False
            continue
        if not cur:
            sep, pending = pending, ""
        cur.append(w)
    if cur:
        out.append((sep, cur))
    return out


def _make_targets(words: list[str]) -> set[str]:
    """The targets one simple command asks make for — `make test`, `make -C x
    a b`, `uv run make test`, `gmake …`. Empty when it is no make call (`sh -c
    'make test'` is one word to sh: no make call the train can read)."""
    targets: set[str] = set()
    in_make = skip = False
    for w in words:
        if skip:
            skip = False
            continue
        if not in_make:
            in_make = Path(w).name in ("make", "gmake")
            continue
        if w in _MAKE_VALUE_OPTS:
            skip = True
            continue
        if w.startswith("-") or "=" in w or w.replace(".", "").isdigit():  # options, variables, `-j 4`, `2>&1`
            continue
        targets.add(w)
    return targets


def _entry_files(words: list[str]) -> list[str]:
    """The files one command starts from, as written: the script
    (`./scripts/x.sh`, `sh scripts/x.sh`, `python3 x.py`, `uv run x.py`, behind
    `timeout 600`, `nice`, `env`, `exec`, `command`, `time`, `nohup`), or
    make's `-C dir` and `-f file`. Empty for a bare command (`pytest`)."""
    i = 0
    while i < len(words) and _ASSIGNMENT.match(words[i]):
        i += 1

    def skip_options(i: int, valued: set[str]) -> int:
        while i < len(words) and words[i].startswith("-") and words[i] != "-":
            i += 2 if words[i] in valued else 1
        return i

    while i < len(words):
        w, name = words[i], Path(words[i]).name
        if name == "timeout":
            i = skip_options(i + 1, {"-s", "-k", "--signal", "--kill-after"}) + 1  # and the duration
        elif name == "nice":
            i = skip_options(i + 1, {"-n", "--adjustment"})
        elif name == "env":
            i = skip_options(i + 1, {"-u", "--unset", "-C", "--chdir", "-S", "--split-string"})
            while i < len(words) and _ASSIGNMENT.match(words[i]):
                i += 1
        elif name in ("exec", "command", "time", "nohup"):
            i = skip_options(i + 1, set())
        elif name == "uv" and words[i + 1:i + 2] == ["run"]:
            i = skip_options(i + 2, {"--with", "--python", "-p", "--project", "--directory", "--package",
                                     "--extra", "--group", "--env-file", "--with-requirements"})
        elif name in ("make", "gmake"):
            files, d, j = [], "", i + 1
            while j < len(words):
                opt = words[j]
                val = words[j + 1] if j + 1 < len(words) else ""
                if opt in ("-C", "--directory"):
                    d = posixpath.join(d, val)
                    files.append(d)
                elif opt in ("-f", "--file", "--makefile"):
                    files.append(posixpath.join(d, val))
                elif opt.startswith("-C") and len(opt) > 2:
                    d = posixpath.join(d, opt[2:])
                    files.append(d)
                    val = None
                elif opt.startswith("-f") and len(opt) > 2 and not opt.startswith("--"):
                    files.append(posixpath.join(d, opt[2:]))
                    val = None
                else:
                    val = None
                j += 1 if val is None else 2
            return files
        elif _INTERPRETERS.match(name):
            shell = name in ("sh", "bash", "dash", "zsh", "ksh")
            kind = "sh" if shell else "python" if name.startswith("python") else name
            # letters that run program text, letters that take a value (attached,
            # or the next word when last in the cluster), long options with a value
            text_flags = {"sh": "c", "python": "cm", "node": "ep"}.get(kind, "eE")
            valued = {"sh": "oO", "python": "WX", "node": "r", "perl": "IMmx", "ruby": "Irx"}.get(kind, "")
            long_valued = {"--require", "--import", "--loader", "--experimental-loader", "--rcfile",
                           "--init-file", "-o", "+o", "-O", "+O"}
            long_text = {"--eval", "--print", "--command"}
            j, program = i + 1, False
            while j < len(words) and words[j][:1] in "-+" and words[j] not in ("-", "+", "--"):
                o = words[j]
                j += 1
                if o.startswith("--") or o in long_valued:
                    program = program or o in long_text
                    if o in long_valued or (o.startswith("--") and "=" not in o and o in long_valued):
                        j += 1
                    continue
                for k, letter in enumerate(o[1:], start=1):
                    if letter in text_flags:
                        program = True
                        break
                    if letter in valued:
                        if k == len(o) - 1:
                            j += 1  # its value is the next word
                        break  # the rest of the cluster is the value
            if program:
                return []  # a program text or a module: no file to ask the tree for
            return words[j:j + 1]
        else:
            return [w] if "/" in w else []
    return []


def _in_tree(base: str, path: str) -> str | None:
    """`path` relative to the tree, or None when it is none of the tree's
    (absolute, `~`, `$VAR`, outside)."""
    if not path or path[0] in "/~$":
        return None
    p = posixpath.normpath(posixpath.join(base, path))
    return None if p == ".." or p.startswith("../") else p


def read_facts(cmd: str, rc: int, lines: list[str], makelevel: str = "0",
               exists: Callable[[str], bool] | None = None) -> SuiteFacts:
    """The facts of one run from the command, its exit code, its output lines,
    the MAKELEVEL the train runs at and the tree (`exists` answers for a path
    relative to it; None: the tree is not asked)."""
    commands = _simple_commands(cmd)
    targets: set[str] = set().union(*(_make_targets(c) for _sep, c in commands))
    # the suite's own commands: the start and whatever follows `&&` — behind
    # `;` or `||` an earlier failure is hidden, a missing fallback proves nothing
    own: list[tuple[str, list[str]]] = []
    for sep, c in commands:
        if sep not in ("", "&&"):
            break
        own.append((sep, c))
    is_file = exists or (lambda _p: False)
    words, absent, base = set(), set(), ""
    for _sep, c in own:
        first = next((w for w in c if not _ASSIGNMENT.match(w)), "")
        rel = _in_tree(base, first) if "/" in first else None
        if first and not (rel and is_file(rel)):
            words.add(first)
        if first == "cd" and len(c) > 1:
            d = _in_tree(base, c[c.index("cd") + 1])
            if d is None:
                break
            base = d
    # the file the suite starts from: only where nothing else could have run —
    # a single chain of `&&` (an absent first file stops it)
    if exists is not None and own == commands:
        base = ""
        for _sep, c in own:
            first = next((w for w in c if not _ASSIGNMENT.match(w)), "")
            if first == "cd":
                d = _in_tree(base, c[c.index("cd") + 1]) if len(c) > c.index("cd") + 1 else None
                if d is None:
                    break
                if not exists(d):
                    absent.add(d)
                    break
                base = d
                continue
            for f in _entry_files(c):
                p = _in_tree(base, f)
                if p is not None and not exists(p):
                    absent.add(p)
            break
    level = makelevel if makelevel.isascii() and makelevel.isdigit() else "0"
    # make's marker is found anywhere in a line: a recipe's output without a
    # final newline, or -j progress dots, run into it (`FAILEDmake: *** [...]`)
    mark = "g?make" + ("" if int(level) == 0 else rf"\[{int(level)}\]") + r": \*\*\* "
    text = "\n".join(lines)
    # GNU make 3.81 quotes `x', make under -k omits "Stop."
    no_rule = re.compile(mark + r"No rule to make target [`'](.+)'\.(?:\s+Stop\.)?$", re.MULTILINE)
    needed = re.compile(mark + r"No rule to make target [`'].*', needed by [`'].*'\.(?:\s+Stop\.)?$", re.MULTILINE)
    return SuiteFacts(
        rc=rc,
        targets=frozenset(targets),
        words=frozenset(words),
        # 4.x `[Makefile:2: test] Error 1`, 3.81 `[test] Error 1`, a signal `[…] Killed`;
        # -j prints "Waiting for unfinished jobs" once a job failed
        recipe_failed=bool(re.search(mark + r"(?:\[.+\] \S|Waiting for unfinished jobs)", text)),
        needed_by=bool(needed.search(text)),
        no_rule=frozenset(m.group(1) for m in no_rule.finditer(text) if not needed.match(m.group(0))),
        missing_includes=frozenset(re.findall(r"(?m)^[^\s:]+:\d+: (.+): No such file or directory$", text)),
        not_found=frozenset(re.findall(
            r"(?m)^sh: (?:line )?\d+: (.+): (?:not found|command not found|No such file or directory)$", text)),
        absent=frozenset(absent),
    )


def _load() -> str:
    try:
        one, _five, _fifteen = os.getloadavg()
    except OSError:
        return "load unknown"
    return f"load {one:.1f} on {os.cpu_count() or '?'} CPUs"


def _echo(text: str, end: str = "\n") -> None:
    """Print what the suite prints, also where stdout cannot encode it (an
    ASCII terminal and a `€` in a test name): replaced, never a traceback."""
    try:
        print(text, end=end, flush=True)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "ascii"
        print(text.encode(enc, "replace").decode(enc), end=end, flush=True)


def _sh(cwd: Path, cmd: str, log) -> str:
    """Run cmd, streaming its output; "green", "red" or "undefined" (the
    command or make target does not exist on this tree) — `decide`'s verdict."""
    _echo(f"train: $ {cmd}")
    # the lines that can carry a fact, over the whole run: those that make a
    # run red whatever follows without a cap, the others the last 400
    red: dict[str, None] = {}
    kept: list[str] = []
    proc = subprocess.Popen(["sh", "-c", cmd], cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, errors="replace")
    assert proc.stdout is not None
    for line in proc.stdout:
        _echo(line, end="")
        line = line.rstrip("\n")
        if _RED_LINE.search(line):
            red[line] = None
        elif _FACT_LINE.search(line):
            kept = (kept + [line])[-400:]
    rc = proc.wait()
    state, why = decide(read_facts(cmd, rc, [*red, *kept], os.environ.get("MAKELEVEL", "0"),
                                   lambda p: (cwd / p).exists()))
    log(f"$ {cmd} → exit {rc} ({state}{'' if rc == 0 else ' — ' + why + ', ' + _load()})")
    return state


GATE_RUNNER_REL = "scripts/process/gate_runner.py"


def _run_gates(wt: Path, log) -> bool:
    """Process gates on the tree in `wt`. No runner in the checkout means no
    gates; the start path is gate_invoke's decision, as in finish.py — a bare
    `sys.executable` cannot resolve the runner's PEP-723 dependencies, and the
    crash read as a red main (observed downstream)."""
    if not (wt / GATE_RUNNER_REL).is_file():
        return True
    argv = gate_runner_argv(wt)
    return argv is not None and _sh(wt, shlex.join(argv), log) == "green"


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
        issues: set[int] = set()
        archived: list[str] = []
        r = _git(wt, "merge", "--no-ff", "--no-commit", b)
        if r.returncode == 0 and _git(wt, "rev-parse", "-q", "--verify", "MERGE_HEAD").returncode != 0:
            merged.append(b)  # already contained (a stacked passenger merged before it)
            log(f"merged {b} — already contained")
            continue
        if r.returncode == 0:
            archived, issues = _settle_plans(wt, base, b, log)
            message = f"train: merge {b}"
            if issues:
                message += "\n\n" + "\n".join(f"Closes #{n}" for n in sorted(issues))
            # --no-verify: the old auto-commit of `git merge` ran no pre-commit
            # hook; a broken hook install must not empty the train (refutation)
            r = _git(wt, "commit", "-q", "--no-verify", "-m", message)
        if r.returncode == 0:
            merged.append(b)
            log(f"merged {b}" + (f" — archived {', '.join(archived)}" if archived else "")
                + (f" — closes {', '.join(f'#{n}' for n in sorted(issues))}" if issues else ""))
        else:
            _git(wt, "merge", "--abort")
            dropped.append(b)
            log(f"conflict: {b} dropped ({r.stderr.strip().splitlines()[-1] if r.stderr.strip() else 'merge failed'})")
    return wt, branch, merged, dropped


_LOCAL_ISSUE = re.compile(r"^#?(\d+)[.,;:]?$")


def _local_issues(text: str) -> set[int]:
    """The issues of THIS repository a plan declares (`issue: #7`, `issue: 7`).
    `issue: other/repo#7` is another repository's #7 — a `Closes #7` in this
    repository would close the wrong issue (refutation)."""
    return {int(m.group(1)) for d in _review.ISSUE_DECL.finditer(text)
            for m in [_LOCAL_ISSUE.match(d.group(1))] if m}


STAYS_ACTIVE = re.compile(_review._LEAD + r"plan-stays-active[*_]*\s*:\s*[*_]*\s*\S",
                          re.IGNORECASE | re.MULTILINE)
_OPEN_TASK = re.compile(r"^\s*[-*+] \[ \]", re.MULTILINE)


def _settle_plans(wt: Path, base: str, branch: str, log) -> tuple[list[str], set[int]]:
    """What merging `branch` finishes: its own active plans that are done —
    a declared tier, no open task, a clearing review (or none required) —
    move to the archive in the merge itself, and the issues of its own
    finished plans are closed by the merge message (`Closes #N` — the forge
    closes them when the merge lands on the default branch).

    Downstream, a plan left active after its train merge kept claiming its
    files, and merged issues stayed open, because a train merge carries no
    closing keyword. A plan that must outlive the merge (work in several
    merges) says `plan-stays-active: <why>`: it stays, its issue stays open.

    Own means: added by the branch (git's rename detection: a plan the branch
    only renamed or moved is not new), or already on the base with the
    branch's issue number among its issues — another work's plan the branch
    touched, renamed or archived is never the branch's to finish (a
    refutation closed issues through a slug in a branch name)."""
    records = _review.record_texts(wt, ("journal",)) or []
    passes = [r for _rel, text in records for _ln, r in _review.parse_review_lines(text)[0]
              if r.get("verdict") == "pass"]
    # (status letter, source on base or "", path now) — the owner reads the -z form
    listed = _git_bytes(wt, "diff", "--name-status", "-M", "-z", f"{base}...{branch}", "--", PLANS)
    entries = _review.name_status(listed) or []
    listed = _paths(wt, "ls-files", "-z", "--", PLANS)
    stems = [Path(n).stem for n in listed or () if n.endswith(".md")]
    dedated: dict[str, int] = {}
    for stem in stems:
        key = _review.DATE_PREFIX.sub("", stem)
        dedated[key] = dedated.get(key, 0) + 1
    branch_issue = _branch_issues(wt, branch)
    archived: list[str] = []
    issues: set[int] = set()
    for letter, source, rel in entries:
        f = wt / rel
        if letter == "D" or not rel.endswith(".md") or not f.is_file():
            continue
        text = f.read_text(encoding="utf-8", errors="replace")
        plain = _review._unfenced(text)
        stem = Path(rel).stem
        # without the listing no de-dated slug is known to be unique
        unique = listed is not None and dedated.get(_review.DATE_PREFIX.sub("", stem), 0) <= 1
        ids = _review._plan_work_ids(stem, plain, include_dedated=unique)
        numbers = {str(n) for n in _local_issues(plain)}
        added = letter == "A"
        if letter == "R" and source:
            # git pairs a deleted old plan with a new, similar one as a rename:
            # a plan for other issues is a new plan, not the old one moved
            fork = _out(wt, "merge-base", base, branch) or base
            old = _review._unfenced(_out(wt, "show", f"{fork}:{source}"))
            added = _local_issues(old) != _local_issues(plain)
        if not added and not (numbers & branch_issue):
            continue  # another work's plan: touched, renamed or archived here
        if STAYS_ACTIVE.search(plain):
            continue
        tier_m = _review.TIER_DECL.search(plain)
        if tier_m is None or _OPEN_TASK.search(plain):
            continue  # no tier (the gate's finding) or tasks still open: not finished
        tier = int(tier_m.group(1))
        if _review.record_kind(rel) == "plan":
            if not (tier < 2 or _review.WAIVED.search(plain) or _review._cleared(passes, ids, tier)):
                continue  # not cleared: it stays active, and its issue open
            dest = f"{ARCHIVE}/{Path(rel).name}"
            if (wt / dest).exists():
                log(f"{rel}: not archived — {dest} exists already")
                continue
            (wt / ARCHIVE).mkdir(parents=True, exist_ok=True)
            if _git(wt, "mv", rel, dest).returncode != 0:
                log(f"{rel}: not archived — git mv failed")
                continue
            archived.append(dest)
        issues |= _local_issues(plain)
    return archived, issues


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
    if not suite:
        print("train: no --suite — only the process gates run; the batch merges without "
              "its full suite (docs/process/train.md)", file=sys.stderr)
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

    def judge(wt: Path) -> str:
        """"green", "red" or "undefined" (the suite does not exist on this tree)."""
        if not _run_gates(wt, log):
            return "red"
        return _sh(wt, suite, log) if suite else "green"

    def attempt(subset: list[str]) -> tuple[str, list[str], str]:
        wt, br, merged, dropped = build_train(root, base, subset, stamp, log)
        for d in dropped:
            if d not in conflicted:
                conflicted.append(d)
        if not merged and subset:
            return "red", merged, br  # everybody conflicted: nothing to judge
        return judge(wt), merged, br

    def _report_dropped() -> None:
        for b in conflicted:
            print(f"train: {b} did not board — merge conflict with the batch; its worker rebases (report: blocked)")
            _write(root, "blocked", f"dropped from train {stamp}: merge conflict — rebase onto {local}", b)
        for b in blamed:
            print(f"train: {b} was dropped as the offender — its worker owes a fix (report: blocked)")
            _write(root, "blocked", f"dropped from train {stamp}: red with it aboard", b)

    base_state = ""  # the base's verdict, checked once ("": not yet)
    retried = told = False

    def check_base() -> str:
        nonlocal base_state
        if not base_state:
            base_state = attempt([])[0]
        return base_state

    while aboard:
        state, merged, branch = attempt(aboard)
        aboard = merged
        if state == "green" or not aboard:
            break
        if state == "undefined":
            if check_base() == "undefined":
                print(f"train: the suite `{suite}` does not exist on the combined tree — fix --suite; "
                      "nothing merged", file=sys.stderr)
                log("suite undefined on the combined tree and on the base — aborted without blame")
                # an offender dropped earlier may have been the one that brought
                # the suite in: it still owes its fix, say so (downstream refutation)
                _report_dropped()
                _cleanup(root, stamp)
                return 1
            # the base HAS the suite: a passenger removed or broke it (deleted
            # the make target, a script with CRLF line ends) — red, and no
            # flake re-run: a missing suite is not flaky (downstream refutation)
            log(f"suite undefined on the combined tree but defined on the base ({base_state}) — "
                "a passenger removed or broke it: red")
            print(f"train: `{suite}` exists on the base but not on the combined tree — a passenger "
                  "removed or broke it; searching for it")
            retried = True
        if not retried:
            # one more run of the SAME tree before anybody is blamed: red then
            # green on identical code is a flaky test (observed downstream: a
            # 5 s lock wait and a 5.1 s UI test under load 10 on 6 CPUs), not
            # an offender — bisecting a flake blames whoever sits in the prefix
            retried = True
            log(f"red — retry of the same combined tree ({_load()})")
            state, merged, branch = attempt(aboard)
            aboard = merged
            if state == "green":
                print("train: FLAKY — the combined tree was red, then green on the identical tree; "
                      f"merging, but the suite has a flaky test (see {logfile}; {_load()})", file=sys.stderr)
                log("red then green on the identical tree — flaky suite, merging")
                break
        # before blaming anybody: is the base itself red (a broken main)?
        # Then no candidate is the offender.
        if check_base() == "red":
            print("train: the combined tree is red and the base is red too — the "
                  "integration branch itself is red (gates or suite fail with nobody aboard); "
                  "no candidate blamed, "
                  "nothing merged — fix main first", file=sys.stderr)
            log("base red and combined red — aborted without blame")
            _cleanup(root, stamp)
            return 1
        if base_state == "undefined" and not told:
            # a passenger introduces the suite (its make target): the base
            # cannot be judged by it — that is not a red main
            told = True
            log("suite undefined on the base (a passenger introduces it) — base not comparable")
            print(f"train: `{suite}` does not exist on the base — a passenger introduces it; "
                  "the base is not judged red, the offender search continues")
        # the combination is red: find the first candidate whose prefix turns
        # it red (bisection over prefixes — O(log n) suite runs per offender),
        # drop it, and try the rest. Order is boarding order, so "first red
        # prefix" names the offender, not whoever happened to board last.
        lo, hi = 1, len(aboard)
        while lo < hi:
            mid = (lo + hi) // 2
            pstate, pmerged, _br = attempt(aboard[:mid])
            # a prefix without the passenger that defines the suite cannot be
            # judged by it — it is not the offender; where the base has the
            # suite, a prefix without it lost it: red
            if (pstate == "green" or (pstate == "undefined" and base_state == "undefined")) \
                    and len(pmerged) == mid:
                lo = mid + 1
            else:
                hi = mid
        offender = aboard[lo - 1]
        blamed.append(offender)
        # the rest is a new combination: it earns its own flake re-run (the
        # base does not change — its verdict is kept)
        retried = False
        log(f"red with {offender} aboard — dropped, rebuilding")
        print(f"train: red with {offender} aboard — dropping it and rebuilding")
        aboard = [b for b in aboard if b != offender]
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
        # the route marker rides on this one push: the pre-push guard
        # (merge_route.py) refuses a push to main that does not name its route
        r = _git(_train_worktree(root), "push", "origin", f"HEAD:{local}",
                 env={MERGE_ROUTE_ENV: MERGE_ROUTE})
        if r.returncode != 0:
            log(f"push of {branch} to origin/{local} rejected: {r.stderr.strip()}")
            _git(root, "worktree", "remove", "--force", str(_train_worktree(root)))
            said = "\n".join((r.stdout.strip() + "\n" + r.stderr.strip()).strip().splitlines()[-30:])
            remote = "[remote rejected]" in r.stderr or "protected branch" in r.stderr.lower()
            why = ("origin rejected it (branch protection? then open a PR from it)" if remote else
                   "the local pre-push hook refused it — its reasons are below; they name the gate")
            print(f"train: the push to {local} failed: {why}. Nothing merged locally; the train "
                  f"branch {branch} stays for inspection:\n{said}", file=sys.stderr)
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
        import dispatch as _dispatch  # lazily, as tower does
        try:
            _dispatch.forget_branch(root, b)  # merged: its issues are placed on it no more
        except Exception as exc:  # noqa: BLE001 — bookkeeping after the merge: say so, never abort a landed train
            print(f"train: dispatch still places {b}'s issues on it — could not forget it: {exc}",
                  file=sys.stderr)
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
        if _sh(root, deploy, log) != "green":
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
