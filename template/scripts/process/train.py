#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6,<7"]
# ///
"""train — collect finished branches and merge them as one batch behind ONE
full suite, at a good moment, instead of every branch paying its own
full run and deploy.

    uv run scripts/process/train.py plan [--json]        # who may board, why not, ready to depart?
    uv run scripts/process/train.py run [--suite "<full suite cmd>" [--suite-differs-ok]] [--retry "<cmd>"]
                                       [--deploy "<cmd>"] [--push] [--preflight "<cmd>"]
                                       [--min-candidates N] [--max-wait-hours H]
                                       [--force] [--keep-branches] [--dry-run]

`--suite` defaults to `merge_suite` of `docs/process/testing.local.json` —
with `merge_suite` set, another command (after `strip`) is refused before
boarding, as the push would never match its certificate; `--suite-differs-ok`
runs it anyway and logs it. `plan` also names pairwise conflicts among the
candidates that may board (`run` does not compute them).
`--preflight` defaults to its `preflight`; every stack's own `preflight` follows either
way — a merge runs every stack, so any of them red is the host's.
`--preflight` checks the environment (tools, logins, disk) on the first
combined tree before any gate: red there is the host's, not a passenger's —
the run stops, nobody is blamed, nothing is retried or bisected.

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
  * its own Spec Kit plans (`specs/<slug>/plan.md`) name its work (slug and
    issues), and each one at Tier 2+ is cleared by a REVIEW pass for that
    plan's work covering the head — one plan's pass never clears another
    plan of the same issue (#218);
  * its latest report among `blocked`, `pushed` and `review-pass` — this
    host's and the ones other hosts published — is not `blocked`: a newer
    `pushed` or `review-pass` releases it, `idle` and `planned` do not (#326);
    the train's own `blocked` (a conflict, red with it aboard) describes a
    run and holds nothing — the tower's rule (`tower.train_holds`), the one
    the tower shows (#336);

Departure: at least `--min-candidates` aboard, or the oldest candidate
has waited longer than `--max-wait-hours`; no lane but `scoped` is held
where the project has lanes (the suite runs on `full`, beside the short
runs); and the runner's red ledger names no red gate on
this clone. `--force` departs with whatever boarded.

The run: a staging branch `train/<stamp>` from the integration branch in
its own worktree; candidates merged in order (a conflict drops that
candidate and continues); the process gates and then the full suite run
ONCE on the combined tree. If they fail, the base itself is checked once
(a red main blames nobody; the suite is skipped on a tree an earlier train
saw green), then a bisection over boarding-order prefixes
names the first offender, drops it, and the rest is rebuilt.
A suite run that marks itself aborted (a line in `$PROCESS_SUITE_ABORT`, or
exit 75 of the command) measured nothing: it is repeated once after the load
falls, and an abort alone never blames a passenger (v2.95, train.md).
The train holds the lane `full` once, from after the preboard check to
before the push (v2.97 B7), where the template's lane script is the
project's: another heavy run of the host waits for the whole loop, the
suite's own `lane.py run --lane full` passes through, and the push's hook
takes the lane itself. A lane still held after at most 60 s ends the run
in a round `lane-held`: nothing ran, nobody is blamed.
Every tree of a run — first, retry, base, probe, rebuild, preboard — is
the SHAs boarding judged on the base's SHA, from one snapshot (#391): a
commit after boarding rides a later train, a fetch moves no run. After
the last green verdict and before the push the holds are read again
(#335): a passenger held now, or reported `blocked` since boarding, leaves
with everyone stacked on it, and the smaller board runs as a new round.
On green: a suite run that left the tree as it found it writes the
`merge` certificate of that tree (`certificate.py`) — the push to main then
runs no suite again; the integration branch fast-forwards to the train, `--push`
pushes it, merged branches are deleted (unless `--keep-branches`), each
worker gets a `done` report, and `--deploy` runs once. A branch that moved
since boarding merged at its boarded SHA and stays: no delete, no `done`,
its dispatch records kept — its new commits need their own review. The combination
is new — that is why the batch, not the branch, earns the full run
(`docs/process/testing.md`). Each run logs its phase times (plan, preflight,
gates, suite, retry, bisect, push, deploy, abort_wait) and appends them, with the
branches that landed, whether the deploy ran green and when the run ended,
to `<git-common-dir>/process-train/phases.jsonl` (`process_kpis.py
train-phases`, `flow`). Every run names who stays behind and why, as `plan`
does (#399); the departing one in its log, a holding one or one with nothing
to do over `<git-common-dir>/process-train/last-hold.txt`.

Run from the root worktree on the integration branch with a clean tree.
The train never reviews, never certifies by itself: it merges what the
process already cleared. Sibling imports; stdlib only."""
from __future__ import annotations

import argparse
from collections import Counter
import contextlib
import datetime as _dt
import itertools
import json
import os
import posixpath
import re
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable, NamedTuple

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling imports
import certificate  # noqa: E402
import check_review as _review  # noqa: E402
from gate_invoke import gate_runner_argv, not_runnable_reason  # noqa: E402
import report as _report  # noqa: E402
import tower as _tower  # noqa: E402

from process_git import REGRESSION_LINE, git_environment  # noqa: E402

ARCHIVE = ".process-work/plans/archive"
PLANS = ".process-work/plans"
# the gates' own code: a branch that changes it boards only on a REVIEW pass
# for its own work — never on a Tier 0-1 plan, a waiver or a worker report
PROCESS_PATHS = ("scripts/process/", ".githooks/")
JOURNAL = ".process-work/journal"
TRAIN_DIR = "process-train"
# the hold rule (#326) has one owner, the tower (#336): `HOLD_STATES`, the train's own
# `blocked` it reads past (`_train_written`) and the note that marks it
# (`TRAIN_DROP_NOTE`, which the train writes) live there


# The route marker the pre-push guard reads to tell the train's push to main
# from any other (owner of the name: merge_route.py). Set for that one push
# only, never in _GIT_ENV — and never inherited: the train's own push runs the
# gates under this marker, so a train started there would otherwise carry it
# into every git call.
MERGE_ROUTE_ENV = "PROCESS_MERGE_ROUTE"
MERGE_ROUTE = "train"
# The abort marker of one suite run (v2.95, `docs/process/train.md`): the path of a fresh,
# empty file the train makes for that run alone. A project's tool that stops the run for a
# reason outside the tree (a held lane, a watchdog under load) appends one line to it. Set
# for suite runs only (`_sh`), never inherited — not by git, the push or its hook either.
SUITE_ABORT_ENV = "PROCESS_SUITE_ABORT"
_GIT_ENV = {**{k: v for k, v in os.environ.items() if k not in (MERGE_ROUTE_ENV, SUITE_ABORT_ENV)},
            "GIT_TERMINAL_PROMPT": "0"}


def _git(root: Path, *args: str, check: bool = False,
         env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    timeout = 300
    if args and args[0] == "push":
        try:
            timeout = int(os.environ.get("PROCESS_TRAIN_PUSH_TIMEOUT_SECONDS", "1800"))
            if timeout <= 0:
                raise ValueError
        except ValueError:
            return subprocess.CompletedProcess(args, 2, "", "PROCESS_TRAIN_PUSH_TIMEOUT_SECONDS must be a positive integer")
    try:
        r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                           timeout=timeout, env=git_environment(_GIT_ENV if env is None else {**_GIT_ENV, **env}))
    except subprocess.TimeoutExpired:
        r = subprocess.CompletedProcess(args, 124, "", f"git {' '.join(args)}: timed out after {timeout} s")
    if check and r.returncode != 0:
        raise SystemExit(f"train: git {' '.join(args)} failed:\n{r.stderr.strip()}")
    return r


def _out(root: Path, *args: str) -> str:
    r = _git(root, *args)
    return r.stdout.strip() if r.returncode == 0 else ""


def _git_bytes(root: Path, *args: str) -> bytes | None:
    """git's raw stdout (for `-z` output), None when git failed."""
    try:
        r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, timeout=300, env=git_environment(_GIT_ENV))
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
    for target in _review.integration_targets(root):
        name = target.removeprefix("refs/heads/")
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


def _branch_issues(root: Path, branch: str, placed: dict[int, str] | None = None) -> set[str]:
    """`dispatch.branch_issues` — the one owner (#204). `placed`: `_placed_issues`,
    read once per planning (#398); without it, dispatch reads its records."""
    import dispatch as _dispatch  # lazily, as tower does
    return _dispatch.branch_issues(root, branch, placed)


def _placed_issues(root: Path) -> dict[int, str]:
    """Where dispatch placed each issue (`dispatch._placed`), for one planning."""
    import dispatch as _dispatch
    return _dispatch._placed(root)


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


def _stacked_renames(root: Path, base: str, branches: list[str], new_by: dict[str, set[str]],
                     unreadable: list[str], tips: dict[str, str] | None = None) -> dict[str, str]:
    """One plan under two names (#201): a candidate stacked on another renames a
    plan the other adds — measured from their own fork, as git's merge of the
    two pairs them. As {path: representative}; only renames (R) from a path
    one candidate brings to a path another brings, each measured against the
    base. Two candidates that share no commit beyond the base are no stack
    and cost no diff. A rewrite git no longer calls a rename stays two plans
    (fail closed). `tips` names each branch's SHA as boarded (#391); without
    one, the branch's name."""
    parent: dict[str, str] = {}
    tip = (tips or {}).get

    def find(p: str) -> str:
        while parent.get(p, p) != p:
            p = parent[p]
        return p

    forks = {b: _out(root, "merge-base", base, tip(b, b)) for b in branches if new_by.get(b)}
    # their commits beyond the base (#398: a `merge-base` per ordered pair was 16 % of a plan);
    # None where git could not list them — unknown is no "disjoint"
    beyond = {b: _commits_beyond(root, base, tip(b, b)) for b in forks}
    shared_forks: dict[tuple[str, str], str] = {}

    def stack_fork(o: str, b: str) -> str:
        """Their own fork, "" for none. Disjoint commits share no commit beyond the base:
        no stack, no `merge-base`. Shared ones ask git once per pair, in one order
        (`merge-base` is not symmetric on criss-cross histories)."""
        if beyond[o] is None or beyond[b] is None:
            return _out(root, "merge-base", tip(o, o), tip(b, b))
        if beyond[o].isdisjoint(beyond[b]):
            return ""
        pair = tuple(sorted((tip(o, o), tip(b, b))))
        if pair not in shared_forks:
            shared_forks[pair] = _out(root, "merge-base", *pair)
        return shared_forks[pair]

    for o in branches:
        for b in branches:
            if o == b or not new_by.get(o) or not new_by.get(b):
                continue
            fork = stack_fork(o, b)
            if not fork or fork in (forks.get(o), forks.get(b)):
                continue  # no commit of o's below b (or the other way round): no stack
            pairs = _review.name_status(_git_bytes(root, "diff", "--name-status", "-M", "-z",
                                                   f"{fork}..{tip(b, b)}", "--", PLANS))
            if pairs is None:
                unreadable.append(f"the plan renames between {o} and {b}")
                continue
            for letter, source, rel in pairs:
                if letter == "R" and source in new_by[o] and rel in new_by[b]:
                    parent[find(source)] = find(rel)
    return {p: find(p) for p in parent}


def _commits_beyond(root: Path, base: str, tip: str) -> set[str] | None:
    """The commits `tip` has beyond `base` (`rev-list base..tip`); None when git failed."""
    listed = _git_bytes(root, "rev-list", f"{base}..{tip}")
    return None if listed is None else set(listed.decode().split())


def _identity_slugs(paths: set[str], same_plan: dict[str, str]) -> Counter:
    """`check_review.slug_counts` over plans, not paths: the names of one
    plan (`_stacked_renames`) count each of their slugs once."""
    groups: dict[str, set[str]] = {}
    for p in paths:
        if p.endswith(".md"):
            groups.setdefault(same_plan.get(p, p), set()).add(p)
    counts: Counter = Counter()
    for members in groups.values():
        counts.update(_review.slug_counts(Path(m).stem for m in members).keys())
    return counts


def _snapshot(root: Path, base: str) -> tuple[dict[str, str], str]:
    """Every local branch's SHA, and the base's, from ONE `for-each-ref` (#391): what
    boarding judges is what the train merges — a commit after it, a fetch that moves
    the base, rides no run of this train. As ({branch: sha}, base sha); the base by
    `rev-parse` only where the listing does not name it."""
    refs = _listed_refs(root, "refs/heads/", "refs/remotes/")
    heads = {name.removeprefix("refs/heads/"): sha for name, sha in refs.items() if name.startswith("refs/heads/")}
    base_sha = (refs.get(f"refs/heads/{base}") or refs.get(f"refs/remotes/{base}")
                or _out(root, "rev-parse", "--verify", "--quiet", f"{base}^{{commit}}") or base)
    return heads, base_sha


def _listed_refs(root: Path, *args: str) -> dict[str, str]:
    """{full refname: sha} of one `for-each-ref`; {} when git failed."""
    refs: dict[str, str] = {}
    for line in _out(root, "for-each-ref", "--format=%(refname) %(objectname)", *args).splitlines():
        name, _, sha = line.rpartition(" ")
        if name and sha:
            refs[name] = sha
    return refs


def _without_lead(root: Path, base_sha: str, tips: dict[str, str]) -> set[str]:
    """The local branches the base already contains, from ONE `for-each-ref --merged`
    (#398: two diffs and a `rev-list` each, for hundreds of merged branches) — only
    where the listed SHA is the snapshot's: a branch moved since is read the normal
    way. An unreadable listing sorts nothing out."""
    merged = {name.removeprefix("refs/heads/"): sha
              for name, sha in _listed_refs(root, f"--merged={base_sha}", "refs/heads/").items()
              if name.startswith("refs/heads/")}
    return {branch for branch, sha in merged.items() if tips.get(branch) == sha}


def candidates(root: Path, local: str, base: str, snapshot: dict | None = None) -> list[dict]:
    """Who may board, and why not. Content is read at each branch's SHA of one
    snapshot and the base at its SHA (#391) — each candidate carries its `sha`;
    identity (the branch's issues, its work ids, its reports) is read by name.
    `snapshot`, when given, receives `base_sha` and `reports_seen` — the report
    identities at boarding, which the run compares before its push (#335) — and
    `no_lead`, how many branches the base already contains (no candidates)."""
    tips, base_sha = _snapshot(root, base)
    # the reports first: a hold written after this read is new to the run's check,
    # one written before it is in the hold read below
    seen = _tower.report_ids(root)
    if snapshot is not None:
        snapshot.update(base_sha=base_sha, reports_seen=seen)
    branches = [b for b in tips if b and b not in (local,) and not b.startswith("train/")]
    # already merged (or empty) — residue for tidy.py, not a candidate: read no further
    merged = _without_lead(root, base_sha, tips)
    no_lead = len([b for b in branches if b in merged])
    branches = [b for b in branches if b not in merged]
    # the train's own `blocked` (TRAIN_DROP_NOTE) describes a run: it neither holds nor hides
    # the report before it from the arms (review round 2: it shadowed a `review-pass`)
    reports = {r["worker"]: r for r in _tower.latest_reports(root, skip=_tower._train_written)}
    # the hold (#326): the tower's rule, the one the tower shows (#336)
    holds = _tower.train_holds(root)
    placed = _placed_issues(root)  # dispatch's records, once for every branch (#398)
    local_sha = tips.get(local, local)
    passes_root = _journal_passes_tree(root, local_sha)
    # the review gate's rule: a de-dated slug may act as a work id only when it
    # is unique across the archive — count them over main's archive and every
    # candidate's additions, so one old pass cannot clear a same-named new plan
    dedated: dict[str, int] = {}
    # a name list git could not produce is no empty list: without it the
    # uniqueness count and the base's plans are unknown, and nothing boards
    unreadable: list[str] = []
    listed = _paths(root, "ls-tree", "-r", "-z", "--name-only", local_sha, "--", ARCHIVE)
    if listed is None:
        unreadable.append(f"the archive on {local}")
    archived_stems = [Path(r).stem for r in listed or ()]
    added_by: dict[str, list[str] | None] = {}
    for b in branches:
        added_by[b] = _paths(root, "diff", "--name-only", "-z", "--diff-filter=A", f"{base_sha}...{tips[b]}",
                             "--", ARCHIVE)
        archived_stems += [Path(r).stem for r in added_by[b] or ()]
    for st in archived_stems:
        key = _review.DATE_PREFIX.sub("", st)
        dedated[key] = dedated.get(key, 0) + 1
    # a plan the base already carries (active or archived) is another work's —
    # archiving it on a branch is housekeeping, not this branch's clearance
    listed = _paths(root, "ls-tree", "-r", "-z", "--name-only", base_sha, "--", PLANS)
    if listed is None:
        unreadable.append(f"the plans on {base}")
    base_plan_stems = {Path(r).stem for r in listed or ()}
    # an active plan's slug is its work id where the gate takes it now and
    # after the merge archives it: unique over what the merged tree may hold —
    # the base's plans, active and archived, and every candidate's new ones
    # (refute and review #199: a namesake on the base or on another car
    # boarded the branch, then the gate refused its plan after the merge)
    # By path (refute: the same plan on stacked branches counted twice): the
    # base's plans and every candidate's new names — and only the branch's own
    # deletions and renames taken out (a plan it only renamed counts once); a
    # car that deletes a namesake may not board, so its deletion counts for
    # nobody else (review: that read a slug as unique the gate then refused)
    gone_by: dict[str, set[str]] = {}
    new_by: dict[str, set[str]] = {}
    merged_paths = set(listed or ())
    for b in branches:
        changes = _review.name_status(_git_bytes(root, "diff", "--name-status", "-M", "-z",
                                                 f"{base_sha}...{tips[b]}", "--", PLANS))
        if changes is None:
            unreadable.append(f"the plan changes of {b}")
        gone_by[b] = {source or rel for letter, source, rel in changes or () if letter in ("D", "R")}
        new_by[b] = {rel for letter, _source, rel in changes or () if letter != "D"}
        merged_paths |= new_by[b]
    same_plan = _stacked_renames(root, base_sha, branches, new_by, unreadable, tips)
    out: list[dict] = []
    for b in sorted(branches):
        tip = tips[b]  # its content, as boarded; `b` stays its identity
        counts = _out(root, "rev-list", "--left-right", "--count", f"{base_sha}...{tip}")
        behind, ahead = (counts.split() + ["0", "0"])[:2] if counts else ("0", "0")
        c: dict = {"branch": b, "sha": tip, "ahead": int(ahead), "behind": int(behind), "eligible": False,
                   "reasons": [], "plans": [], "by": None}
        if int(ahead) == 0:
            if counts:  # git read it: contained after all (an unreadable listing, a branch moved since the snapshot)
                no_lead += 1
            continue  # an unreadable count stays unboarded as before, but is no "merged or empty"
        listed = _paths(root, "diff", "--name-only", "-z", f"{base_sha}...{tip}")
        files = set(listed or ())
        c["files"] = len(files)
        last = _out(root, "log", "-1", "--format=%ct", tip)
        c["hours_waiting"] = round((time.time() - int(last)) / 3600, 1) if last.isdigit() else None
        archived = [p for p in added_by[b] or () if p.endswith(".md")]
        branch_unreadable = unreadable + [what for what, names in (
            (f"the files of {b}", listed), (f"the plans {b} archives", added_by[b])) if names is None]
        branch_passes = _journal_passes_branch(root, base_sha, tip)
        passes = passes_root + branch_passes
        touches_process = sorted(f for f in files if f.startswith(PROCESS_PATHS))
        # the branch's name and its issues: a REVIEW line of any other work
        # is not this branch's
        issues = _branch_issues(root, b, placed)
        own_ids = _branch_work_ids(b) | issues
        housekeeping: list[str] = []
        own_archived: list[str] = []
        for rel in archived:
            shown = _git(root, "show", f"{tip}:{rel}")
            if shown.returncode != 0:
                branch_unreadable.append(f"{rel} on {b}")  # an unread plan is no Tier 0 plan
                continue
            text = _review._unfenced(shown.stdout)  # a fenced example is not a declaration
            stem = Path(rel).stem
            tier = _review.plan_tier(text) or 0
            unique = dedated.get(_review.DATE_PREFIX.sub("", stem), 0) <= 1
            ids = _review._plan_work_ids(stem, text, include_dedated=unique)
            if not (_names_branch(b, ids, issues) or stem not in base_plan_stems):
                housekeeping.append(rel)  # another work's plan, only moved to the archive here
                continue
            own_archived.append(rel)
            own_ids |= ids
            waived = _review.review_waived(text)
            pure_template = _review.verified_template_plan(root, rel, text, tip=tip)
            ok = tier < 2 or waived or pure_template or _covers(root, passes, ids, tier, tip, branch_passes, base_sha)
            if touches_process and not _covers(root, passes, ids, 2, tip, branch_passes, base_sha):
                ok = False
            c["plans"].append({"path": rel, "tier": tier, "cleared": ok, "waived": waived,
                               **({"verified_template": True} if pure_template else {})})
        archived = own_archived
        # its own active plans name its work too: the merge archives them
        # (`_settle_plans`), and their REVIEW says `work=<stem>` or `<slug>`
        def read(rel: str, b: str = b, tip: str = tip) -> str | None:
            shown = _git(root, "show", f"{tip}:{rel}")
            if shown.returncode != 0:
                branch_unreadable.append(f"{rel} on {b}")
                return None
            return shown.stdout
        own_active = _own_plans(root, base_sha, b, read, specs=True, tip=tip, placed=placed)
        if own_active is None:
            branch_unreadable.append(f"the plans of {b}")
        merged_slugs = _identity_slugs(merged_paths - gone_by.get(b, set()), same_plan)
        # a Spec Kit plan's slug and issues are its work too (#218), and each
        # one at Tier 2+ needs a clearing REVIEW of its own: one issue split
        # into two spec plans on one branch is two works — a pass for the one
        # does not clear the other, even where its range saw both
        spec_uncleared: list[tuple[str, set[str]]] = []
        for rel, plain in own_active or ():
            kind = _review.record_kind(rel)
            if kind == "plan":
                stem = Path(rel).stem
                unique = merged_slugs[_review.DATE_PREFIX.sub("", stem)] == 1
                own_ids |= _review._plan_work_ids(stem, plain, include_dedated=unique)
            elif kind == "spec-plan":
                ids = _review._plan_work_ids(_review.plan_stem(rel), plain, include_dedated=False)
                own_ids |= ids
                tier = _review.plan_tier(plain) or 0
                if tier >= 2 and not _review.review_waived(plain) \
                        and not _covers(root, passes, ids, tier, tip, branch_passes, base_sha):
                    spec_uncleared.append((rel, ids))
        found = _deviations(root, base_sha, b, tip=tip, placed=placed)  # what rides into its merge commit
        if found is None:
            branch_unreadable.append(f"the DoD deviations of {b}")  # an unread hold would close the issue
        deviations, held = found or ([], set())
        c["deviations"] = len(deviations)
        c["keeps_open"] = sorted(held)
        cleared_all = bool(archived) and all(p["cleared"] for p in c["plans"])
        if housekeeping:
            c["housekeeping"] = housekeeping
        # a question the owner never answered rides no train: the branch
        # was built on an assumption — answer it (DECISION line) first
        # a plan the branch deletes holds no question and cannot be read at its
        # tip (#201: it refused the branch as unreadable)
        active = _paths(root, "diff", "--name-only", "-z", "--diff-filter=d", f"{base_sha}...{tip}", "--",
                        _tower.PLANS_ACTIVE, _tower.SPECS_DIR)
        if active is None:
            branch_unreadable.append(f"the active plans of {b}")
        open_q = []
        for rel in (r for r in active or () if r.endswith(".md")):
            shown = _git(root, "show", f"{tip}:{rel}")
            if shown.returncode != 0:
                branch_unreadable.append(f"{rel} on {b}")  # an unread plan hides its open question
            elif questions := _review.open_questions(shown.stdout):
                open_q.append((rel, " ".join(questions[0].group(0).split())[:160]))
        if open_q:
            # the line and the answer forms (downstream: questions answered in content but
            # left unmarked held branches for a day, ten marking commits after the fact)
            rel, line = open_q[0]
            c["reasons"].append(
                f"open DECISION NEEDED in {rel}: `{line}` — answer it before merging: a dated "
                f"`DECISION <date> <who>: …` line in place of it, or mark the question "
                f"`(answered <date>)` before its colon")
        if branch_unreadable:
            c["reasons"].append(f"git could not read {', '.join(branch_unreadable)} — an unread name or plan "
                                f"is no Tier 0 plan; repair the clone (`git fsck`, fetch) and run the train again")
        from template_verify import verify
        template_blocked = False
        try:
            update = verify(root, base_sha, tip)
            template_findings = _review.template_review_findings(root, update, passes, tip=tip)
            template_blocked = bool(template_findings)
            c["reasons"].extend(template_findings)
        except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
            template_blocked = True
            c["reasons"].append(f'template verification failed: {exc}')
        hold = holds.get(b)
        report_blocked = bool(hold)
        if report_blocked:
            note = f": {hold['note']}" if hold.get("note") else ""
            c["reasons"].append(f"latest report `blocked` ({hold['minutes_ago']} min ago{note}) — "
                                f"`report.py pushed` after the fix, or `review-pass`, releases it")
        rep = reports.get(b)
        process_unreviewed = bool(touches_process) and not _covers(root, passes, own_ids, 2, tip, branch_passes, base_sha)
        if process_unreviewed:
            more = f" and {len(touches_process) - 1} more" if len(touches_process) > 1 else ""
            c["reasons"].append(f"changes the gates' code ({touches_process[0]}{more}) without a REVIEW pass "
                                f"at tier 2 or higher for its own work (work= one of {', '.join(sorted(own_ids))}) "
                                f"— gate code needs it whatever the plan's tier")
        elif spec_uncleared:
            rel, ids = spec_uncleared[0]
            more = f" (and {len(spec_uncleared) - 1} more spec plan(s))" if len(spec_uncleared) > 1 else ""
            c["reasons"].append(f"{rel}{more}: Tier 2+ spec plan without a clearing REVIEW pass of its own "
                                f"covering the branch head (work= one of {', '.join(sorted(ids))}) — "
                                f"another plan's review does not clear it (review it, then attest)")
        elif archived and cleared_all:
            needs_review = [p for p in c["plans"] if p["tier"] is not None and p["tier"] >= 2 and not p["waived"]]
            c["by"] = ("archived plan + verified template render"
                       if any(p.get("verified_template") for p in c["plans"])
                       else "archived plan + REVIEW pass" if needs_review
                       else "archived plan (Tier 0-1 or waived: no review required)")
        elif rep and rep["state"] == "review-pass":
            if archived and not cleared_all:
                c["reasons"].append("archived Tier 2+ plan without a REVIEW pass covering the branch head "
                                    "— the report is not the record")
            elif (_covers(root, passes, own_ids, 0, tip, branch_passes, base_sha)
                  and any(r["work"] in own_ids for r in passes)):
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
        # a file shared with a branch aboard is no reason to wait: git merges
        # the batch, a conflict drops the later candidate (`build_train`), and
        # the gates read reviewed content as git's merge of the reviewed works
        # (v2.55) — downstream three reviewed branches waited a train for a
        # shared test, contract doc or registry file
        if c["by"] and not open_q and not branch_unreadable and not template_blocked and not report_blocked:
            c["eligible"] = True
        out.append(c)
    if snapshot is not None:
        snapshot["no_lead"] = no_lead
    return out


def _journal_passes_tree(root: Path, ref: str) -> list[dict]:
    return _review.review_passes(root, (
        _show(root, ref, rel) for rel in _paths(root, "ls-tree", "-r", "-z", "--name-only", ref,
                                                 "--", JOURNAL) or () if rel.endswith(".md")), ref)


def _covers(root: Path, passes: list[dict], ids: set[str], tier: int, tip: str,
            own: list[dict] | None = None, base: str | None = None) -> bool:
    """Does a clearing REVIEW pass cover the branch as it stands NOW? A pass
    whose reviewed content the branch no longer is — code nobody reviewed
    came after it, or a merge changed it — clears the plan but not these commits —
    downstream, a branch merged by one train got new commits and boarded the
    next on its old clearance. The same rule as the review gate's stale check
    (`check_review._unreviewed_paths`), judged at the branch tip. Passes
    without a head (older records) count only when no pass for the work has
    one, and only from the branch's OWN journal (`own`): a headless pass on
    main was written for earlier work and cannot vouch for new commits
    (downstream refutation). The own-family rule is read at `base` — boarding's
    base SHA (#391) — else at the checkout's integration ref."""
    req = min(tier, 3)
    deciding = _review.clearing_passes(root, passes, tier, base)  # the gate's answer which passes count (#241)
    clearing = [r for r in deciding if r["work"] in ids and int(r["tier"]) >= req]
    with_head = [r for r in clearing if r.get("head")]
    if not with_head:
        if any(r.get("head") for r in passes if r["work"] in ids):
            return False
        own_ids = {id(r) for r in (own or [])}
        return any(id(r) in own_ids for r in clearing)
    reviewed = _review._reviewed_heads(deciding, tier, _review._known_work(root, ref=tip))
    for r in with_head:
        late = _review._unreviewed_paths(root, r["head"], tip, reviewed, r.get("base") or "")
        if late is not None and not late:
            return True
    return False


def _journal_passes_branch(root: Path, base: str, branch: str) -> list[dict]:
    return _review.review_passes(root, (
        _show(root, branch, rel) for rel in _paths(root, "diff", "--name-only", "-z",
                                                    f"{base}...{branch}", "--", JOURNAL) or ()
        if rel.endswith(".md")), branch)


def departure(cands: list[dict], root: Path, *, min_candidates: int, max_wait_hours: float) -> tuple[bool, str]:
    aboard = [c for c in cands if c["eligible"]]
    if not aboard:
        return False, "nobody aboard"
    # a held `scoped` lane does not hold the train: the suite runs on `full`,
    # niced beside the short runs (downstream: serial pre-pushes held `scoped`
    # all morning and one train left in a day, five reviewed candidates
    # waiting). A held `full` or unknown lane does: the suite would queue
    # behind it and a lane timeout reads red.
    lanes = _tower.lanes(root)
    busy = [ln for ln in lanes if "held by" in ln and not ln.startswith("scoped:")]
    if busy:
        return False, f"lane busy: {busy[0]}"
    reds = [g for g in _tower.red_gates(root) if g["age_days"] >= 0]
    if reds:
        return False, "gate red on this clone: " + ", ".join(
            g["gate"] + (f" ({g['reason']})" if g.get("reason") else "") for g in reds)
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
    # other hosts' published reports: a steward's `blocked --sync` holds a branch
    # here too (#326). Best effort like the fetch above — a note, never a hold
    if not _report.fetch_reports(root):
        print("train: could not fetch the published reports from origin (offline, or no origin) — "
              "boarding reads the reports this clone has; another host's unfetched `blocked` holds nothing",
              file=sys.stderr)
    base = base_ref(root, local)
    # what boarding saw (#391, #335): the base's SHA and every report's identity —
    # each candidate carries its own `sha`
    snapshot: dict = {}
    cands = candidates(root, local, base, snapshot)
    ready, why = departure(cands, root, min_candidates=min_candidates, max_wait_hours=max_wait_hours)
    return {"integration": local, "base": base, **snapshot, "candidates": cands, "ready": ready, "why": why}


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
# "aborted" (v2.95) — the run said itself it measured nothing: a line in its
# abort marker (`SUITE_ABORT_ENV`) with a non-zero exit, or exit 75 (EX_TEMPFAIL)
# of the command itself. It is no verdict on the tree: the train's rule
# (`run_judged`) turns it into green, red or a stop that blames nobody, and the
# preboard check boards it unchecked. It is not "undefined", which can blame (a
# passenger removed the suite).
EXIT_75_REASON = "exit 75 (EX_TEMPFAIL), the suite refused to run"

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
    abort: tuple[str, ...] = ()                # the lines of the run's abort marker, first line first


def decide(f: SuiteFacts) -> tuple[str, str]:
    """`(state, reason)`, state "green", "red", "undefined" or "aborted" — the
    whole rule; the first row that applies decides."""
    if f.rc == 0:
        return "green", "exit 0"
    # the run marked itself aborted (a held lane, a watchdog): no finding about the tree,
    # whatever make made of the exit (`make -k` turns a recipe's 75 into 2)
    if f.abort:
        return "aborted", f"a run aborted: {f.abort[0]}"
    # the suite itself refused to run (a lane called without make): not measured
    if f.rc == 75:
        return "aborted", f"a run aborted: {EXIT_75_REASON}"
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
               exists: Callable[[str], bool] | None = None, abort: tuple[str, ...] = ()) -> SuiteFacts:
    """The facts of one run from the command, its exit code, its output lines,
    the MAKELEVEL the train runs at, the tree (`exists` answers for a path
    relative to it; None: the tree is not asked) and the lines of its abort
    marker (`_abort_lines`)."""
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
        abort=tuple(abort),
    )


def _one_minute_load() -> float | None:
    """The host's one-minute load average; None where it cannot be read (no
    `os.getloadavg`, as on Windows, or an OSError)."""
    getloadavg = getattr(os, "getloadavg", None)
    if getloadavg is None:
        return None
    try:
        return float(getloadavg()[0])
    except (OSError, TypeError, ValueError, IndexError):
        return None


def _cpus() -> int | None:
    """The CPUs this process may run on (`sched_getaffinity`, else `cpu_count`); None
    when neither says."""
    affinity = getattr(os, "sched_getaffinity", None)
    if affinity is not None:
        try:
            n = len(affinity(0))
            if n > 0:
                return n
        except OSError:
            pass
    n = os.cpu_count()
    return n if n else None


def _load() -> str:
    one = _one_minute_load()
    if one is None:
        return "load unknown"
    return f"load {one:.1f} on {_cpus() or '?'} CPUs"


# --- a suite run that aborted (v2.95) ------------------------------------------------
# The train repeats a run that aborted once, after the host's load fell below its CPUs
# or ABORT_WAIT_S passed (constants, no configuration: nobody asked to tune them).
ABORT_RETRIES = 1
ABORT_WAIT_S = 600.0
ABORT_POLL_S = 10.0
ABORT_DIR = "suite-abort"     # under the train's directory: `<stamp>-<pid>.<n>`, one file per run
ABORT_BYTES = 64 * 1024       # what the train reads of a marker at most
ABORT_LINES = 50
ABORT_LINE_CHARS = 500        # of one line, the rest is cut
ABORT_STALE_S = 86400.0       # a marker this old is a killed train's: any cleanup removes it
# C0 and C1 controls and DEL: a terminal escape in a reason prints nowhere
_ABORT_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")
# what `wait_for_load` waits with; the tests replace them
_abort_clock = time.monotonic
_abort_sleep = time.sleep
# `n` of the marker path: every suite run of this process counts, the preboard probes too
_ABORT_RUNS = itertools.count(1)


def wait_for_load(log, *, budget: float | None = None, clock: Callable[[], float] | None = None,
                  sleep: Callable[[float], None] | None = None) -> tuple[float, str]:
    """Wait until the one-minute load is below the CPUs, at most `budget` seconds
    (ABORT_WAIT_S) — `(seconds waited, how it ended)`: "load", "budget", or "unread"
    when the load or the CPU count cannot be read (then nothing waits; the log says so)."""
    budget = ABORT_WAIT_S if budget is None else budget
    clock = clock or _abort_clock
    sleep = sleep or _abort_sleep
    cpus = _cpus()
    if cpus is None:
        log("abort: no CPU count on this host — no wait for the load before the repeat")
        return 0.0, "unread"
    started = clock()
    while True:
        load = _one_minute_load()
        waited = clock() - started
        if load is None:
            log("abort: no load average on this host — no wait for the load before the repeat")
            return waited, "unread"
        if load < cpus:
            return waited, "load"
        if waited >= budget:
            return waited, "budget"
        sleep(min(ABORT_POLL_S, budget - waited))


def _abort_lines(path: Path) -> tuple[str, ...]:
    """The non-empty lines of a run's abort marker, at most ABORT_LINES of its first
    ABORT_BYTES — a regular file opened without following a link (`_lastfailed_ids`).
    () when it cannot be read: an unreadable marker marks nothing."""
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    except (OSError, ValueError):
        return ()
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            return ()
        raw = os.read(fd, ABORT_BYTES)
    except OSError:
        return ()
    finally:
        os.close(fd)
    # a line becomes a reason (the log, `aborts`, a stop's message): no control
    # characters, at most ABORT_LINE_CHARS
    lines = (_ABORT_CONTROL.sub(" ", ln).strip()[:ABORT_LINE_CHARS]
             for ln in raw.decode("utf-8", "replace").splitlines())
    return tuple(ln for ln in lines if ln)[:ABORT_LINES]


def _abort_marker(root: Path, stamp: str) -> Path | None:
    """A fresh, empty marker for the next suite run of this train: its own path, so a
    late writer of an earlier run marks nothing here. None when it cannot be made."""
    try:
        folder = _train_dir(root) / ABORT_DIR
        folder.mkdir(exist_ok=True)
        path = folder / f"{stamp}-{os.getpid()}.{next(_ABORT_RUNS)}"
        with contextlib.suppress(FileNotFoundError):
            path.unlink()
        os.close(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600))
    except OSError:
        return None
    return path


def _clear_aborts(root: Path, stamp: str) -> None:
    """Remove this train's markers (`<stamp>-<pid>.*`): what a run left behind — and
    every marker older than ABORT_STALE_S, whoever made it: a killed train cleans up
    nothing, and a live run's marker is as young as the run."""
    try:
        folder = _train_dir(root) / ABORT_DIR
        own = set(folder.glob(f"{stamp}-{os.getpid()}.*"))
        stale = time.time() - ABORT_STALE_S
        for f in folder.iterdir() if folder.is_dir() else ():
            with contextlib.suppress(OSError):
                if f in own or f.lstat().st_mtime < stale:
                    f.unlink()
    except OSError:
        pass


def _marked_sh(root: Path, stamp: str, cwd: Path, cmd: str, log, *args, **kw) -> tuple[str, str]:
    """One suite run with its own abort marker: `_sh` with the marker, then
    `(state, reason)` — the reason of an "aborted" run is the marker's first line
    (or exit 75), "" otherwise. The marker is removed afterwards: a writer that keeps
    the contract (append, never create) cannot bring it back. A marker that cannot be
    made runs the suite without one, and says so."""
    path = _abort_marker(root, stamp)
    lines: tuple[str, ...] = ()
    if path is None:
        log(f"abort marker not made in {TRAIN_DIR}/{ABORT_DIR} — `{cmd}` runs without {SUITE_ABORT_ENV}")
        state = _sh(cwd, cmd, log, *args, **kw)
    else:
        try:
            state = _sh(cwd, cmd, log, *args, abort=path, **kw)
            lines = _abort_lines(path) if state == "aborted" else ()
        finally:
            with contextlib.suppress(OSError):
                path.unlink()
    if state != "aborted":
        return state, ""
    # no marker line: only an exit 75 at the top aborts a run
    return state, lines[0] if lines else EXIT_75_REASON


def _echo(text: str, end: str = "\n") -> None:
    """Print what the suite prints, also where stdout cannot encode it (an
    ASCII terminal and a `€` in a test name): replaced, never a traceback."""
    try:
        print(text, end=end, flush=True)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "ascii"
        print(text.encode(enc, "replace").decode(enc), end=end, flush=True)


def _sh(cwd: Path, cmd: str, log, timeout: float | None = None, *, timeout_state: str = "red",
        env: dict[str, str] | None = None, abort: Path | None = None) -> str:
    """Run cmd, streaming its output; "green", "red", "undefined" (the
    command or make target does not exist on this tree) or "aborted" (only
    with `abort`, or on exit 75) — `decide`'s verdict.
    Past `timeout` seconds its whole process group is killed: `timeout_state` —
    red for the preflight, the suite and the deploy; the preboard check asks
    for "undefined" (a slow check says nothing about the candidate, #386).
    `env` extends the inherited environment, never replaces it — except for
    SUITE_ABORT_ENV, which no command inherits: it is `abort`, the marker of a
    suite run (`_marked_sh`), and only there."""
    _echo(f"train: $ {cmd}")
    # the lines that can carry a fact, over the whole run: those that make a
    # run red whatever follows without a cap, the others the last 400
    red: dict[str, None] = {}
    kept: list[str] = []
    child = {**{k: v for k, v in os.environ.items() if k != SUITE_ABORT_ENV}, **(env or {})}
    if abort is not None:
        child[SUITE_ABORT_ENV] = str(abort)
    proc = subprocess.Popen(["sh", "-c", cmd], cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, errors="replace", env=git_environment(child),
                            start_new_session=timeout is not None)
    assert proc.stdout is not None
    expired = threading.Event()

    def _expire() -> None:
        # the group: a child of `sh` holding stdout open would outlive `sh` alone
        expired.set()
        with contextlib.suppress(OSError):
            if hasattr(os, "killpg"):
                os.killpg(proc.pid, signal.SIGKILL)
            else:
                proc.kill()

    timer = threading.Timer(timeout, _expire) if timeout is not None else None
    if timer:
        timer.start()
    for line in proc.stdout:
        _echo(line, end="")
        line = line.rstrip("\n")
        if _RED_LINE.search(line):
            red[line] = None
        elif _FACT_LINE.search(line):
            kept = (kept + [line])[-400:]
    rc = proc.wait()
    if timer:
        timer.cancel()
    if expired.is_set():
        log(f"$ {cmd} → killed after {timeout:g} s ({timeout_state})")
        _echo(f"train: `{cmd}` did not finish in {timeout:g} s — killed")
        return timeout_state
    state, why = decide(read_facts(cmd, rc, [*red, *kept], os.environ.get("MAKELEVEL", "0"),
                                   lambda p: (cwd / p).exists(),
                                   abort=_abort_lines(abort) if abort is not None else ()))
    log(f"$ {cmd} → exit {rc} ({state}{'' if rc == 0 else ' — ' + why + ', ' + _load()})")
    return state


GATE_RUNNER_REL = "scripts/process/gate_runner.py"


def _run_gates(wt: Path, log, target: str | None = None) -> bool:
    """Process gates on the tree in `wt`. No runner in the checkout means no
    gates; the start path is gate_invoke's decision, as in finish.py — a bare
    `sys.executable` cannot resolve the runner's PEP-723 dependencies, and the
    crash read as a red main (observed downstream). `target` (a full ref name)
    tells the gates where the merge goes, as the push hook does: the merge-only
    checks are hard here, before the push (v2.94)."""
    if not (wt / GATE_RUNNER_REL).is_file():
        return True
    argv = gate_runner_argv(wt)
    env = {_review.PUSH_TARGETS_ENV: target} if target else None
    return argv is not None and _sh(wt, shlex.join(argv), log, env=env) == "green"



# trees whose suite this train saw green: the base it checks after a red batch
# is the tree an earlier train fast-forwarded to, so the suite need not run on
# it again (downstream a full suite took ~26 min). The gates still run: some
# read state beyond the tree (the issue tracker, the red ledger).
GREEN_SUITES = "green-suites"
GREEN_SUITES_KEPT = 200


def _suite_key(wt: Path, suite: str, scope_argv: list[str] | None = None) -> str:
    """`<tree> <evidence digest>`, or "" when the tree or the scope cannot be read (no
    memo). The digest is the merge certificate's evidence, scope included: a green that
    covered a narrowed run is never the memo of the full one."""
    tree = _out(wt, "rev-parse", "HEAD^{tree}")
    evidence = certificate.merge_evidence(wt, suite, scope_argv)
    # the digest is certificate's: memo and merge certificate name a suite alike (S6)
    return f"{tree} {certificate.evidence_hash(evidence)}" if tree and evidence else ""


def _suite_seen_green(root: Path, key: str) -> bool:
    if not key:
        return False
    try:
        lines = (_train_dir(root) / GREEN_SUITES).read_text(encoding="utf-8").splitlines()
    except OSError:
        return False
    return key in lines


def _remember_green_suite(root: Path, key: str) -> None:
    f = _train_dir(root) / GREEN_SUITES
    try:
        lines = f.read_text(encoding="utf-8").splitlines() if f.is_file() else []
        lines = [ln for ln in lines if ln != key][-(GREEN_SUITES_KEPT - 1):] + [key]
        tmp = f.with_name(f"{f.name}.{os.getpid()}.tmp")
        tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
        os.replace(tmp, f)
    except OSError:
        pass  # a memo that cannot be written only costs a later run

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


def build_train(root: Path, base: str, aboard: list[str], stamp: str, log, *,
                worktree: Path | None = None,
                shas: dict[str, str] | None = None) -> tuple[Path, str, list[str], list[str]]:
    """Merge candidates onto a fresh staging branch in its own worktree
    (`worktree`, default the staging worktree `<root>-train`; the preboard
    check builds its probe trees here too — one owner of the merge, #386).
    `shas` names the SHA each candidate boarded with: that is what merges, on
    `base` as the caller pinned it (#391) — a branch that moves after boarding
    changes no run; without one, its name. Names stay the identity (messages,
    issues, the merged list). Returns (worktree, branch, merged,
    dropped_for_conflict)."""
    wt = worktree if worktree is not None else _train_worktree(root)
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
        tip = (shas or {}).get(b) or b
        r = _git(wt, "merge", "--no-ff", "--no-commit", tip)
        if r.returncode == 0 and _git(wt, "rev-parse", "-q", "--verify", "MERGE_HEAD").returncode != 0:
            merged.append(b)  # already contained (a stacked passenger merged before it)
            log(f"merged {b} — already contained")
            continue
        if r.returncode == 0:
            # read before settling: settling moves plans the deviations live in
            found = _deviations(wt, base, b, tip=tip)
            if found is None:
                # an unread hold would close an issue the plan keeps open
                _git(wt, "merge", "--abort")
                dropped.append(b)
                log(f"{b} dropped (git could not read its plans' DoD deviations)")
                continue
            deviations, held = found
            archived, issues = _settle_plans(wt, base, b, log, tip=tip)
            kept = issues & held
            issues -= held
            message = f"train: merge {b}"
            if deviations:
                message += "\n\n" + "\n".join(deviations)
            refs = [f"Closes #{n}" for n in sorted(issues)] + [f"Refs #{n}" for n in sorted(kept)]
            if refs:
                message += "\n\n" + "\n".join(refs)
            for n in sorted(kept):
                log(f"{b}: issue #{n} stays open — a DoD-deviation leaves an AC open or the work continuing")
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


_local_issues = _review.local_issue_numbers  # one owner (#204)


STAYS_ACTIVE = re.compile(_review._LEAD + r"plan-stays-active[*_]*\s*:\s*[*_]*\s*\S",
                          re.IGNORECASE | re.MULTILINE)
_OPEN_TASK = _review.OPEN_TASK  # the one open-task grammar


def _own_plans(root: Path, base: str, branch: str, read, *, specs: bool = False, tip: str | None = None,
               placed: dict[int, str] | None = None) -> list[tuple[str, str]] | None:
    """The plans under PLANS — with `specs`, also the Spec Kit plans
    (`specs/<slug>/plan.md`, #218) — that are `branch`'s own, as (path, unfenced text):
    added by the branch (git's rename detection: a plan the branch only
    renamed or moved is not new), or already on the base with one of the
    branch's issues among its issues — another work's plan the branch
    touched, renamed or archived is never its own (a refutation closed issues
    through a slug in a branch name). Boarding and the merge's settling ask
    this one rule (#199: an active plan's ids counted only once archived, and
    a `work=<slug>` pass did not board). `read(rel)` gives the text, None when
    there is none; None when git cannot list the plans. `tip` is the content to
    read (the SHA the branch boarded with, #391), `branch` the identity — its
    issues decide what is its own; without `tip`, the branch's name. `placed`: as
    `_branch_issues`."""
    pathspec = (PLANS, _review.SPECS_DIR) if specs else (PLANS,)
    own = _review.own_plans(root, base, tip or branch, _branch_issues(root, branch, placed), read, pathspec,
                            lambda rel: rel.endswith(".md") and (rel.startswith(PLANS + "/")
                                                                 or _review.record_kind(rel) == "spec-plan"))
    return None if own is None else [(rel, plain) for rel, plain, _added in own]


# Mandatory rule 7: a DoD deviation belongs in the merge-commit body. The train
# writes that body, so it carries the branch's own deviation lines
# (`definition-of-ready-and-done.md`, Bindingness, owns the grammar).
DOD_DEVIATION = re.compile(_review._LEAD + r"DoD-deviation[*_]*\s*:(.*)$", re.IGNORECASE | re.MULTILINE)
# `open AC-3 [of #N]` or `continues [#N]` right after the marker: the issue stays open
# a closing keyword in a copied line would let GitHub close what `Refs` keeps open
_CLOSING = re.compile(r"\b(close[sd]?|fix(?:e[sd])?|resolve[sd]?)(\s*:?\s+)([\w.-]+/[\w.-]+)?#(\d+)",
                      re.IGNORECASE)
_HOLDS = re.compile(r"\s*[*_]*\s*(?:open\s+AC-[\w.]+(?:\s*,\s*AC-[\w.]+)*(?:\s+of)?|continues)"
                    r"(?P<refs>(?:[\s,]*#\d+)*)(?![\w-])", re.IGNORECASE)


def _deviations(root: Path, base: str, branch: str, *, tip: str | None = None,
                placed: dict[int, str] | None = None) -> tuple[list[str], set[int]] | None:
    """The `DoD-deviation:` lines of `branch`'s own plans and spec plans
    (`check_review.own_plans`, the one rule), each stripped but otherwise
    verbatim, in order and without repeats — and the issues they keep open:
    a line that names an open AC (`open AC-3`) or continuing work
    (`continues`) holds the issues it names after that (`of #N`, `#N`), else
    its plan's own issues. A fenced example is no declaration. A closing
    keyword before an issue (`fixes #12`) is copied as `fixes issue 12`, so
    GitHub closes nothing the train did not close. None when git cannot
    list the plans. Content at `tip` (the boarded SHA, #391), identity by
    `branch`; without `tip`, the branch's name. `placed`: as `_branch_issues`."""
    tip = tip or branch

    def read(rel: str) -> str | None:
        shown = _git(root, "show", f"{tip}:{rel}")
        return shown.stdout if shown.returncode == 0 else None

    own = _review.own_plans(root, base, tip, _branch_issues(root, branch, placed), read,
                            (PLANS, _review.SPECS_DIR),
                            lambda rel: _review.record_kind(rel) in ("plan", "plan-archive", "spec-plan"))
    if own is None:
        return None
    lines: list[str] = []
    held: set[int] = set()
    for _rel, plain, _added in own:
        for m in DOD_DEVIATION.finditer(plain):
            line = _CLOSING.sub(r"\1\2\3issue \4", m.group(0).strip())
            if line not in lines:
                lines.append(line)
            hold = _HOLDS.match(m.group(1))
            if hold:
                named = {int(n) for n in re.findall(r"#(\d+)", hold.group("refs"))}
                held |= named or _local_issues(plain)
    return lines, held


def _settle_plans(wt: Path, base: str, branch: str, log, *,
                  tip: str | None = None) -> tuple[list[str], set[int]]:
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
    refutation closed issues through a slug in a branch name). `tip` is the
    merged SHA (#391): which plans changed is read there, whose they are by
    `branch`. The own-family rule is read at `base`, never at the train's HEAD:
    a wagon that lifts it lifts it for no later wagon."""
    records = _review.record_texts(wt, ("journal",)) or []
    passes = _review.review_passes(wt, (text for _rel, text in records), tip or branch)
    listed = _paths(wt, "ls-files", "-z", "--", PLANS)
    stems = [Path(n).stem for n in listed or () if n.endswith(".md")]
    dedated: dict[str, int] = {}
    for stem in stems:
        key = _review.DATE_PREFIX.sub("", stem)
        dedated[key] = dedated.get(key, 0) + 1

    def read(rel: str) -> str | None:
        f = wt / rel
        return f.read_text(encoding="utf-8", errors="replace") if f.is_file() else None

    archived: list[str] = []
    issues: set[int] = set()
    for rel, plain in _own_plans(wt, base, branch, read, tip=tip) or []:
        stem = Path(rel).stem
        # without the listing no de-dated slug is known to be unique
        unique = listed is not None and dedated.get(_review.DATE_PREFIX.sub("", stem), 0) <= 1
        ids = _review._plan_work_ids(stem, plain, include_dedated=unique)
        if STAYS_ACTIVE.search(plain):
            continue
        tier = _review.plan_tier(plain)
        if tier is None or _OPEN_TASK.search(plain):
            continue  # no tier (the gate's finding) or tasks still open: not finished
        if _review.record_kind(rel) == "plan":
            if not (tier < 2 or _review.review_waived(plain)
                    or _review._cleared(_review.clearing_passes(wt, passes, tier, base), ids, tier)):
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


def _changed_by_run(wt: Path) -> bool:
    """Did a run leave anything git would see — a modified file or a new one
    not ignored? Unreadable counts as changed."""
    r = _git(wt, "status", "--porcelain")
    return r.returncode != 0 or bool(r.stdout.strip())


PHASES = ("plan", "preboard", "preflight", "gates", "suite", "retry", "bisect", "push", "deploy",
          "abort_wait")
PHASES_FILE = "phases.jsonl"
LAST_HOLD_FILE = "last-hold.txt"  # the last run that did not depart: when, why, who stayed behind


class EnvironmentRed(Exception):
    """`--preflight` failed: the host cannot run the suite — nobody aboard is to blame."""


class SuiteAborted(EnvironmentRed):
    """A suite run aborted, its repeat too, and the base could not tell load from a
    hang (it aborted as well, is the one that aborted, or has no suite): nobody is
    blamed, nothing merges (`red_path` "suite-aborted")."""


class BaseRed(Exception):
    """A run aborted twice and the fresh base ran red: main is red — `_red_base`, not
    an environment stop."""


class LaneHeld(EnvironmentRed):
    """The lane `full` stayed held past the train's wait: nothing ran, nobody is blamed,
    nothing merges (`red_path` "lane-held"; "lane-busy" is a kind of abort-marker line)."""


TRAIN_LANE = "full"
# the train's own wait for `full`: at most this, never the lane's `wait` (3600 s by
# default) — a train that cannot start says so and departs later (v2.97 B7, r3 n8)
TRAIN_LANE_WAIT_S = 60.0


def _restore_env(name: str, value: str | None) -> None:
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value


def _hold_full(root: Path, stamp: str, log) -> contextlib.ExitStack:
    """The train's hold of `full` (v2.97 B7), taken once after the preboard and let go
    before the push (`.close()`): no other holder comes and goes between two suite runs,
    the abort rule (v2.95) never sees the train's own lane, and the push's pre-push hook,
    which takes `full` itself, does not wait for the train. The rule of `test_select.run`:
    held where the template's lane script is the project's — a project that kept its own
    `scripts/lane.py` holds its lanes in its commands; a configuration without `full`
    has nothing to hold. Every child inherits the hold (`PROCESS_LANE_HELD`, so `lane.py run
    --lane full` in the suite passes through) and this lane directory (`PROCESS_LANE_DIR`,
    so a passenger that moves `lane_dir` meets the same lock). Raises LaneHeld past
    `TRAIN_LANE_WAIT_S` (or the lane's shorter wait)."""
    import lane as _lane  # noqa: PLC0415
    import testing_config  # noqa: PLC0415

    held = contextlib.ExitStack()
    if testing_config.lane_script(root) != root / "scripts/process/lane.py":
        return held
    try:
        settings = _lane.config(root)
    except testing_config.ConfigError as exc:  # main() refused it already; a caller from outside
        log(f"lane {TRAIN_LANE} not held — {exc}")
        return held
    if TRAIN_LANE not in settings["lanes"]:
        return held
    wait = min(TRAIN_LANE_WAIT_S, settings["lanes"][TRAIN_LANE]["wait"])
    try:
        held.enter_context(_lane.hold(TRAIN_LANE, wait=wait, label=f"train {stamp}", settings=settings))
    except _lane.LaneBusy as busy:
        log(f"lane {busy} — the train waited {wait:g} s; nothing ran")
        raise LaneHeld(f"the lane {busy} — waited {wait:g} s") from None
    where = str(settings["dir"])
    held.callback(_restore_env, _lane.DIR_ENV, os.environ.get(_lane.DIR_ENV))
    os.environ[_lane.DIR_ENV] = where
    log(f"lane {TRAIN_LANE} held by this train ({where}) until before the push")
    return held


def stage_markers(wt: Path) -> dict[str, tuple[int, int, int] | None] | None:
    """The `<stage>.time` markers the merge suite left in the merge-suite folder of
    `wt`, for each stage its `stages` file names, in that order: `(start, end, exit)`,
    or None for a missing or unreadable marker. None when the `stages` file or the
    git dir cannot be read. The one marker reader: the stage times, the retry's
    certificate and the red stages of the measure all ask here."""
    gitdir = _out(wt, "rev-parse", "--absolute-git-dir")
    names = certificate.run_stages(wt)
    if not gitdir or names is None:
        return None
    folder = Path(gitdir) / "merge-suite"
    markers: dict[str, tuple[int, int, int] | None] = {}
    for name in names:
        try:
            t0, t1, verdict = (int(x) for x in (folder / f"{name}.time").read_text(encoding="utf-8").split())
        except (OSError, ValueError):
            markers[name] = None
            continue
        markers[name] = (t0, t1, verdict)
    return markers


def _collect_stage_times(wt: Path, stages: dict[str, dict], seen: set[tuple[str, int, int]],
                         log) -> None:
    """Folds the `<stage>.time` markers the merge suite left in the merge-suite
    folder of `wt` into `stages` (`docs/process/testing.md`, "Stages"). A stage without a readable marker is
    `skipped`, and a skip never overwrites what an earlier run of that stage said.
    `seen` keeps a run that is collected twice (suite, then retry) from counting twice;
    the state is the one of the last run, the seconds add up over all of them."""
    markers = stage_markers(wt)
    if markers is None:
        return
    for name, marker in markers.items():
        try:
            if marker is None:
                raise ValueError("no readable marker")
            t0, t1, verdict = marker
            if t1 < t0:
                raise ValueError("ends before it starts")
            start = _dt.datetime.fromtimestamp(t0).isoformat(timespec="seconds")
            end = _dt.datetime.fromtimestamp(t1).isoformat(timespec="seconds")
        except (OSError, ValueError, OverflowError):  # a bad marker costs a KPI, never the train
            if name not in stages:
                stages[name] = {"seconds": 0, "runs": 0, "state": "skipped", "start": None, "end": None}
                log(f"stage {name}: skipped")
            continue
        if (name, t0, t1) in seen:
            continue
        seen.add((name, t0, t1))
        entry = stages.setdefault(name, {"seconds": 0, "runs": 0})
        state = "green" if verdict == 0 else "red"
        entry.update(seconds=entry["seconds"] + t1 - t0, runs=entry["runs"] + 1, state=state,
                     start=start, end=end)
        log(f"stage {name}: {state} {t1 - t0} s ({start} → {end})")


def _every_stage_green(wt: Path) -> bool:
    """Does every stage the run's `stages` file names carry a green `<stage>.time`
    marker in `wt`'s merge-suite folder? No stage list (a suite without stages) is no:
    then nothing tells which part a retry covered."""
    markers = stage_markers(wt)
    if not markers:
        return False
    return all(marker is not None and marker[2] == 0 for marker in markers.values())


# The red tests of a suite-red run, read only from pytest's own `lastfailed` files
# (`red_ids` in testing.local.json, v2.88 #378): what a later partial re-run would pick,
# measured first. A measuring error costs a field, never the train.
RED_IDS_MAX = 200
RED_IDS_BYTES = 1 << 20
IMPLICIT_STAGE = "suite"  # a suite without stages is one stage


class _Unread(Exception):
    """A `lastfailed` file the measure cannot use — the message is the field's reason."""


def _lastfailed_ids(path: Path) -> list[str]:
    """The node ids of a pytest `lastfailed` file: a regular file (no symlink), at most
    1 MiB, a UTF-8 JSON object whose keys are the ids."""
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        raise _Unread("missing") from None
    if not stat.S_ISREG(st.st_mode):
        raise _Unread("not a regular file")
    if st.st_size > RED_IDS_BYTES:
        raise _Unread("larger than 1 MiB")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as fh:
        raw = fh.read(RED_IDS_BYTES + 1)
    if len(raw) > RED_IDS_BYTES:
        raise _Unread("larger than 1 MiB")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise _Unread("not UTF-8") from None
    try:
        data = json.loads(text)
    except ValueError:
        raise _Unread("not JSON") from None
    if not isinstance(data, dict):
        raise _Unread("not a JSON object")
    return list(data)


def _tree_blobs(wt: Path, ref: str) -> dict[str, str] | None:
    """{path: blob sha} of the tree at `ref` — one `git ls-tree -r` per tree; None when
    git cannot read it."""
    raw = _git_bytes(wt, "ls-tree", "-r", "-z", ref)
    if raw is None:
        return None
    blobs: dict[str, str] = {}
    for entry in raw.split(b"\0"):
        meta, sep, name = entry.partition(b"\t")
        parts = meta.split()
        if sep and len(parts) == 3 and parts[1] == b"blob":
            blobs[name.decode("utf-8", "surrogateescape")] = parts[2].decode("ascii")
    return blobs


def _defines(text: str, name: str) -> bool:
    return re.search(rf"^[ \t]*(?:async[ \t]+)?def[ \t]+{re.escape(name)}[ \t]*\(", text, re.MULTILINE) is not None


def _on_base(node_id: str, rootdir: str, board: dict[str, str], base: dict[str, str], wt: Path,
             blobs: dict[str, str | None]) -> bool | str:
    """Was the red test `node_id` on the base already? True, False or "unknown". A
    parameter case `[...]` goes first, then the id splits at its first `::`: the file is
    `rootdir/<part before>`, the function the last part. False only for a file the base
    lacks or a `def` the board tree adds; True only for an unchanged file that defines the
    function itself; anything else is unknown — a later partial run picks functions, never
    single parameter cases."""
    if node_id.endswith("]") and "[" in node_id:
        node_id = node_id[:node_id.index("[")]
    part, sep, rest = node_id.partition("::")
    name = rest.rsplit("::", 1)[-1]
    if not sep or not part or not name:
        return "unknown"
    rel = posixpath.normpath(posixpath.join(rootdir, part))
    if rel.startswith(("/", "../")) or rel in ("..", "."):
        return "unknown"
    if rel not in board:
        return "unknown"
    if rel not in base:
        return False

    def text(sha: str) -> str | None:
        if sha not in blobs:
            raw = _git_bytes(wt, "cat-file", "blob", sha)
            blobs[sha] = None if raw is None else raw.decode("utf-8", "replace")
        return blobs[sha]
    if board[rel] == base[rel]:
        # an unchanged file holds the test only where it defines it: an inherited mixin
        # method or a star import may be new elsewhere (refute v2.88) — then unknown
        same = text(board[rel])
        return True if same is not None and _defines(same, name) else "unknown"
    new, old = text(board[rel]), text(base[rel])
    if new is None or old is None:
        return "unknown"
    return False if _defines(new, name) and not _defines(old, name) else "unknown"


def red_tests(wt: Path, base: str, entries: list[dict], cache: dict) -> dict:
    """The red tests of the suite-red run just finished in `wt`: its red stages (from the
    markers; without a `stages` file the stage `suite`), and per `red_ids` entry the ids
    of its `lastfailed` file, each with `on_base` against `base` — or a `reason`. The
    board tree is `wt`'s HEAD. `cache` keeps the base's blobs across rounds. Never raises."""
    try:
        markers = stage_markers(wt)
        names = list(markers) if markers else [IMPLICIT_STAGE]
        red = [n for n, m in (markers or {}).items() if m is not None and m[2] != 0]
        if not markers or not red:
            red = [IMPLICIT_STAGE]  # red, but no marker says where: the whole suite
        board = base_blobs = None
        sources: list[dict] = []
        for e in entries:
            stage = e.get("stage") or IMPLICIT_STAGE
            src: dict = {"lastfailed": e["lastfailed"], "rootdir": e.get("rootdir") or ".", "stage": stage}
            sources.append(src)
            if stage not in names:
                src["reason"] = "unknown stage"
                continue
            if stage not in red:
                src["reason"] = "stage not red"
                continue
            try:
                ids = _lastfailed_ids(wt / e["lastfailed"])
                if len(ids) > RED_IDS_MAX:
                    src.update(reason="too_many", n=len(ids))
                    continue
                if board is None:
                    board = _tree_blobs(wt, "HEAD")
                    if "base" not in cache:
                        cache["base"] = _tree_blobs(wt, base)
                    base_blobs = cache["base"]
                if board is None or base_blobs is None:
                    src["reason"] = "trees unreadable"
                    continue
                blobs = cache.setdefault("blobs", {})
                src["ids"] = {i: _on_base(i, src["rootdir"], board, base_blobs, wt, blobs) for i in ids}
            except _Unread as exc:
                src["reason"] = str(exc)
            except Exception as exc:  # noqa: BLE001 — a measuring error costs a field, never the train
                src["reason"] = f"unreadable: {type(exc).__name__}"
        return {"stages": red, "sources": sources}
    except Exception as exc:  # noqa: BLE001 — a measuring error costs a field, never the train
        return {"reason": f"unreadable: {type(exc).__name__}"}


def _rounded_rounds(rounds: list[dict]) -> list[dict]:
    """The measure's rounds for the phases row, the seconds to a tenth."""
    out = []
    for r in rounds:
        runs = {kind: {"n": v["n"], "build_gates_s": round(v["build_gates_s"], 1),
                       "suite_s": round(v["suite_s"], 1)} for kind, v in r.get("runs", {}).items()}
        out.append({**r, "runs": runs})
    return out


def _end_round(measure: dict | None, red_path: str) -> None:
    """How the last round's red path ended — set where the run ends it."""
    rounds = (measure or {}).get("rounds")
    if rounds:
        rounds[-1]["red_path"] = red_path


def _record_phases(root: Path, stamp: str, phases: dict[str, float], result: str, aboard: list[str],
                   log, outcome: dict | None = None, stages: dict | None = None,
                   measure: dict | None = None) -> None:
    """One log line and one JSON line per run: where the train's time went.
    `result`: green, red, environment (a red preflight, a suite run that aborted
    with nobody to blame, or the lane `full` held by another run — the last round's
    `red_path` tells them apart; no red
    train) or preboard (the preboard check dropped every candidate — nothing was built).
    `branches` are the ones that landed, `deployed` whether the deploy ran
    green (null: no deploy ran), `ended` when the run finished (UTC) — what
    ties a deploy to an issue for `process_kpis.py flow`. `stages`: the merge-suite
    stage times (`_collect_stage_times`), `{}` when none were collected. `rounds`: the
    red path's runs per kind and round (`docs/process/train.md`), `[]` when none ran.
    `preboard_checks`: what the preboard check decided (`pre_board`) — only when it was
    configured, so a row without it reads as before. `held`: who left before the push
    on a hold set during the run (#335), `[]` when nobody did."""
    spent = {k: round(phases.get(k, 0.0), 1) for k in PHASES}
    log(f"phases ({result}): " + ", ".join(f"{k} {v:.0f} s" for k, v in spent.items() if v))
    outcome = outcome or {}
    row = {"stamp": stamp, "result": result, "aboard": len(aboard), **spent,
           "stages": stages or {},
           "branches": list(outcome.get("branches") or []), "held": list(outcome.get("held") or []),
           "deployed": outcome.get("deployed"),
           "ended": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
           "rounds": _rounded_rounds((measure or {}).get("rounds") or [])}
    if "preboard_checks" in outcome:
        row["preboard_checks"] = outcome["preboard_checks"]
    try:
        with (_train_dir(root) / PHASES_FILE).open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
    except OSError:
        pass  # a lost timing line costs a KPI, never the merge


def _certify_merge(wt: Path, suite: str, before: str | None, env_names: list[str], log,
                   scope_argv: list[str] | None = None) -> None:
    """The `merge` certificate of the tree the suite just ran green on — only
    when the run left the worktree as it found it (S6)."""
    if not before:
        return
    if _changed_by_run(wt):
        # name what the run left, so it can be ignored or cleaned (downstream #2542)
        log(f"suite green, but the run changed the worktree — no merge certificate"
            f" ({certificate.clean_tree_problem(wt) or 'the tree differs from before the run'})")
        return
    # the hook builds the same evidence (`certificate.merge_evidence`): the same string, or no
    # hit. The scope is the run's `stages` file; missing with `merge_scope` configured = unknown,
    # never recomputed
    evidence = certificate.run_evidence(wt, suite, scope_argv)
    if evidence is None:
        log("suite green, but the scope of the run is unknown — no merge certificate")
        return
    ok, why = certificate.write(wt, "merge", evidence, before_tree=before, writer="train",
                                env_names=env_names)
    log(f"merge certificate {'written' if ok else 'not written — ' + why}")


def retry_plan(red_in: str, retry: str | None) -> tuple[str, str]:
    """How a red combined tree is run once more before anybody is blamed —
    `(how, why)`, the whole rule: "gates" re-runs the process gates on the
    same worktree (minutes; a gate can read the network), "failed" runs the
    project's `--retry` command there (what failed and what did not run),
    "full" rebuilds the tree and runs the whole suite again. Downstream a
    deterministic red cost a second 24-minute suite before the drop; a
    flake under load stays a flake either way (#193)."""
    if red_in == "gates":
        return "gates", "the process gates are red — re-run them on the same tree"
    if retry:
        return "failed", "the suite is red — re-run what failed and what did not run (--retry)"
    return "full", "the suite is red — no --retry: rebuild and run the whole suite again"


PREBOARD_SUFFIX = "-preboard"


def _preboard_worktree(root: Path) -> Path:
    """The probe worktree of the preboard check, a sibling like `<root>-train`."""
    return root.parent / f"{root.name}-train{PREBOARD_SUFFIX}"


def _worktree_branch(root: Path, wt: Path) -> str | None:
    """The branch ref checked out at `wt` if git has a worktree registered there
    ("" for a detached one), else None."""
    out = _out(root, "worktree", "list", "--porcelain") or ""
    current = None
    for line in out.splitlines() + [""]:
        if line.startswith("worktree "):
            current = Path(line[len("worktree "):])
        elif line.startswith("branch ") and current is not None and current.resolve() == wt.resolve():
            return line[len("branch "):]
        elif line == "detached" and current is not None and current.resolve() == wt.resolve():
            return ""
    return None


def _clear_worktree(root: Path, wt: Path) -> None:
    """Remove `wt` and its registration: what an earlier build or a killed run left."""
    if wt.exists():
        _git(root, "worktree", "remove", "--force", str(wt))
        shutil.rmtree(wt, ignore_errors=True)
    _git(root, "worktree", "prune")


def pre_board(root: Path, base: str, aboard: list[str], stamp: str, cmd: str, timeout: float | None,
              log, preflight: str | None = None, preflight_timeout: float | None = None,
              checks: dict | None = None, shas: dict[str, str] | None = None) -> tuple[list[str], dict]:
    """The preboard check (#386): `cmd`, a check of seconds, on base+candidate before the
    candidate boards — `(still aboard, checks)`, a new list in boarding order. The probe
    trees are `build_train`'s, in `<root>-train-preboard` on `train/<stamp>-preboard`: the
    train's own merge, plans settled. The base first: red or not judgeable there, nobody
    is checked (a broken host, a red main — never a candidate's fault). A candidate red on
    base+it runs once more on a rebuilt tree; red twice, it is reported blocked and stays
    off this train. Not judgeable (undefined, past `timeout`, a conflict, a tree that
    cannot be built, a run that aborted — v2.95) boards, and says so: the full suite
    still judges it (AC-2).
    Before anybody is reported, the base is checked once more and the host by `preflight`
    on the base's tree (refute v2.89: a broken part of the host the base never exercised,
    or a host that broke mid-check, blocked candidates before the preflight ran) — the
    base no longer green: nobody dropped; the preflight red: `EnvironmentRed`, nobody
    blamed. `shas`: the SHAs the candidates boarded with, merged as `build_train`
    merges them (#391)."""
    wt = _preboard_worktree(root)
    probe_stamp = f"{stamp}{PREBOARD_SUFFIX}"
    checks = {} if checks is None else checks  # the caller's: it reaches the row on any exit
    checks.update(checked=0, dropped=[], unchecked=0, reason=None)
    owner = _worktree_branch(root, wt)
    if owner is not None and not owner.startswith("refs/heads/train/"):
        # dispatch names a worktree `<root>-<branch>`: a branch `train-preboard` owns this
        # path — never removed for a probe (refute v2.89: it lost uncommitted work)
        checks.update(unchecked=len(aboard), reason=f"probe path {wt} is the worktree of {owner}")
        log(f"preboard: {checks['reason']} — not pre-checked")
        print(f"train: preboard: {checks['reason']} — not pre-checked", file=sys.stderr)
        return list(aboard), checks
    _clear_worktree(root, wt)  # a killed run's probe tree first: its branch is checked out there
    # probe branches a killed run left (its `finally` never ran)
    stale = (_out(root, "for-each-ref", "--format=%(refname:short)", "refs/heads/train/") or "").split()
    for old_branch in stale:
        if old_branch.endswith(PREBOARD_SUFFIX):
            _git(root, "branch", "-D", old_branch)

    def probe(subset: list[str]) -> str:
        """green, red, undefined — or "conflict", "not built", "aborted": not judged. A
        probe that aborted (its marker, v2.95) is not repeated: it boards unchecked."""
        _clear_worktree(root, wt)  # a fresh tree per check: no residue of the run before counts
        try:
            built, _br, merged, _dropped = build_train(root, base, subset, probe_stamp, log, worktree=wt,
                                                       shas=shas)
        except (Exception, SystemExit) as exc:  # noqa: BLE001 — `_git(check=True)` exits
            # a probe that cannot be built checks nothing, and never aborts the train
            log(f"preboard: probe tree not built — {type(exc).__name__}: {exc}")
            return "not built"
        if any(b not in merged for b in subset):
            return "conflict"  # boards: the train's own build drops it as before
        return _marked_sh(root, stamp, built, cmd, log, timeout, timeout_state="undefined")[0]

    try:
        log(f"preboard `{cmd}` on the base")
        state = probe([])
        if state != "green":
            checks.update(unchecked=len(aboard), reason=f"preboard on the base: {state}")
            log(f"{checks['reason']} — not pre-checked")
            print(f"train: {checks['reason']} — not pre-checked", file=sys.stderr)
            return list(aboard), checks
        kept: list[str] = []
        unjudged: list[str] = []
        for b in aboard:
            log(f"preboard `{cmd}` on base+{b}")
            state = probe([b])
            if state == "red":
                log(f"preboard red with {b} — once more on a rebuilt tree")
                state = probe([b])
            if state == "red":
                checks["dropped"].append(b)
                log(f"preboard red twice with {b} — held back, reported once base and host are confirmed")
                continue
            kept.append(b)
            if state == "green":
                checks["checked"] += 1
                continue
            checks["unchecked"] += 1
            unjudged.append(f"{b}: {state}")
            log(f"preboard {b}: not pre-checked — {state}")
            print(f"train: {b}: not pre-checked — {state}", file=sys.stderr)
        checks["reason"] = "; ".join(unjudged) or None
        if checks["dropped"]:
            again = probe([])  # the base once more: a host or a check that turned red mid-way
            if again != "green":
                checks["reason"] = f"preboard on the base turned {again} — not pre-checked"
                log(checks["reason"])
                print(f"train: {checks['reason']}; nobody held back", file=sys.stderr)
                checks["unchecked"] += len(checks["dropped"])
                checks["dropped"] = []
                return list(aboard), checks
            if preflight:
                started = time.monotonic()
                state = _sh(wt, preflight, log, preflight_timeout)
                checks["preflight_s"] = time.monotonic() - started  # the caller books it as preflight
                if state != "green":
                    # the host cannot run what the candidates' check needs: nobody's fault
                    raise EnvironmentRed(f"the preflight `{preflight}` is red")
            for b in checks["dropped"]:
                print(f"train: {b} did not board — the preboard check `{cmd}` is red on {base}+{b} twice; "
                      "its worker owes a fix (report: blocked)", file=sys.stderr)
                _write(root, "blocked", f"{_tower.TRAIN_DROP_NOTE} {stamp}: preboard red — {cmd}", b)
        return kept, checks
    finally:
        _clear_worktree(root, wt)
        _git(root, "branch", "-D", f"train/{probe_stamp}")


def _stay(root: Path, said: str, behind: list[str]) -> None:
    """A run that does not depart (#399): what it says and who stays behind, and why —
    printed, and written over `last-hold.txt`, never appended: a polled `run` floods
    no log. A lost file costs the record, never the run."""
    print(said)
    for line in behind:
        print(line)
    now = _dt.datetime.now().isoformat(timespec="seconds")
    try:
        (_train_dir(root) / LAST_HOLD_FILE).write_text(
            "".join(f"{line}\n" for line in [f"{now} {said}", *behind]), encoding="utf-8")
    except OSError:
        pass


def run(root: Path, *, suite: str | None, deploy: str | None, push: bool, min_candidates: int,
        max_wait_hours: float, force: bool, keep_branches: bool, dry_run: bool,
        retry: str | None = None, preflight: str | None = None,
        certificate_env: list[str] | None = None, preflight_timeout: float | None = None,
        merge_scope: list[str] | None = None, suite_note: str | None = None,
        red_ids: list[dict] | None = None, preboard: str | None = None,
        preboard_timeout: float | None = None) -> int:
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
    started = time.monotonic()
    p = plan(root, min_candidates=min_candidates, max_wait_hours=max_wait_hours)
    planned = time.monotonic() - started  # a departing run logs it as `plan`, the others print it
    aboard = [c["branch"] for c in p["candidates"] if c["eligible"]]
    behind = left_behind(p)
    if not aboard:
        _stay(root, f"train: {p['why']} — nothing to do (planning took {planned:.1f} s)", behind)
        return 0
    if not p["ready"] and not force:
        _stay(root, f"train: holding — {p['why']} (--force departs now; planning took {planned:.1f} s)", behind)
        return 0
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M")
    logfile = _train_dir(root) / f"{stamp}.log"
    print(f"train {stamp}: departing with {', '.join(aboard)} ({p['why']})")
    for line in behind:
        print(line)
    if not suite:
        print("train: no --suite — only the process gates run; the batch merges without "
              "its full suite (docs/process/train.md)", file=sys.stderr)
    if suite_note:
        print(f"train: {suite_note}", file=sys.stderr)
    if dry_run:
        print("train: dry run — no merge, no suite")
        return 0
    # the deliberate exception stays on the run's record, beside what it ran; and who
    # stays behind, and why (#399), before the first build
    if record := ([suite_note] if suite_note else []) + behind:
        now = _dt.datetime.now().isoformat(timespec="seconds")
        with logfile.open("a", encoding="utf-8") as fh:
            fh.writelines(f"{now} {line}\n" for line in record)
    phases: dict[str, float] = {"plan": planned}
    outcome: dict = {}
    stages: dict[str, dict] = {}
    measure: dict = {}  # the red path's rounds (v2.88): filled by _run_batch, ended here too
    rc = 1
    result = "red"
    try:
        rc = _run_batch(root, local, p, aboard, stamp, logfile, suite=suite, deploy=deploy, push=push,
                        keep_branches=keep_branches, retry=retry, preflight=preflight, phases=phases,
                        certificate_env=certificate_env or [], preflight_timeout=preflight_timeout,
                        outcome=outcome, stages=stages, merge_scope=merge_scope, measure=measure,
                        red_ids=red_ids, preboard=preboard, preboard_timeout=preboard_timeout)
        # a result the batch names itself (preboard: nobody left to build) stands
        result = outcome.get("result") or ("green" if rc == 0 else "red")
        return rc
    except LaneHeld as busy:
        # before the general branch: its own red path, as a suite abort's
        result = "environment"
        _end_round(measure, "lane-held")
        print(f"train: {busy} — another run holds it; nothing ran, nobody is blamed, nothing merged "
              f"(see {logfile})", file=sys.stderr)
        _cleanup(root, stamp)
        return rc
    except SuiteAborted as aborted:
        # before the general branch: its own red path, never overwritten as "environment"
        result = "environment"
        _end_round(measure, "suite-aborted")
        print(f"train: {aborted} — no finding about a passenger; nobody is blamed, nothing merged "
              f"(see {logfile})", file=sys.stderr)
        _cleanup(root, stamp)
        return rc
    except EnvironmentRed as env_red:
        result = "environment"
        _end_round(measure, "environment")
        print(f"train: {env_red} — the environment cannot run the suite; "
              f"nobody is blamed, nothing merged, no retry (see {logfile})", file=sys.stderr)
        _cleanup(root, stamp)
        return rc
    except BaseException:
        _end_round(measure, "aborted")
        wt = _train_worktree(root)
        if wt.exists():
            _git(root, "worktree", "remove", "--force", str(wt))
            print(f"train: aborted — staging worktree removed, branch train/{stamp} kept; log: {logfile}",
                  file=sys.stderr)
        raise
    finally:
        def _log(line: str) -> None:
            with logfile.open("a", encoding="utf-8") as fh:
                fh.write(f"{_dt.datetime.now().isoformat(timespec='seconds')} {line}\n")
        _clear_aborts(root, stamp)
        _record_phases(root, stamp, phases, result, aboard, _log, outcome, stages, measure)


def _run_batch(root: Path, local: str, p: dict, aboard: list[str], stamp: str, logfile: Path, *,
               suite: str | None, deploy: str | None, push: bool, keep_branches: bool,
               retry: str | None = None, preflight: str | None = None,
               phases: dict[str, float] | None = None, certificate_env: list[str] | None = None,
               preflight_timeout: float | None = None, outcome: dict | None = None,
               stages: dict | None = None, merge_scope: list[str] | None = None,
               measure: dict | None = None, red_ids: list[dict] | None = None,
               preboard: str | None = None, preboard_timeout: float | None = None) -> int:
    def log(line: str) -> None:
        with logfile.open("a", encoding="utf-8") as fh:
            fh.write(f"{_dt.datetime.now().isoformat(timespec='seconds')} {line}\n")

    phases = {} if phases is None else phases
    stages = {} if stages is None else stages
    stage_seen: set[tuple[str, int, int]] = set()
    searching = ""  # "retry" or "bisect": a judged tree's time counts there
    # the red path's runs per kind and round (v2.88, #378) — counted, never steering
    measure = {} if measure is None else measure
    rounds: list[dict] = measure.setdefault("rounds", [])
    run_now: dict[str, float] | None = None  # the run being counted: its suite and preflight seconds
    red_cache: dict = {}  # the base's blobs, read once across rounds

    def timed(phase: str, fn, *args):
        started = time.monotonic()
        try:
            return fn(*args)
        finally:
            spent = time.monotonic() - started
            name = searching if searching and phase in ("gates", "suite") else phase
            phases[name] = phases.get(name, 0.0) + spent
            if run_now is not None and phase in ("suite", "retry", "preflight"):
                key = "preflight" if phase == "preflight" else "suite"
                run_now[key] += spent

    @contextlib.contextmanager
    def counted(kind: str):
        """One run of the red path of the current round: build and gates apart from the
        suite (a partial run saves only the suite); the preflight counts in neither."""
        nonlocal run_now
        run_now = {"suite": 0.0, "preflight": 0.0}
        started = time.monotonic()
        try:
            yield
        finally:
            wall = time.monotonic() - started
            if rounds:
                entry = rounds[-1]["runs"].setdefault(kind, {"n": 0, "build_gates_s": 0.0, "suite_s": 0.0})
                entry["n"] += 1
                entry["suite_s"] += run_now["suite"]
                entry["build_gates_s"] += max(0.0, wall - run_now["suite"] - run_now["preflight"])
            run_now = None

    preflight_done = not preflight

    suite_before: dict[Path, str | None] = {}  # the tree each suite run started from
    last_abort = ""  # the reason of the last suite run that aborted (its marker's first line)

    def _suite_run(wt: Path, cmd: str, kind: str) -> str:
        """The lower layer (v2.95): one suite run with its own abort marker. It only
        reports — "aborted" decides nothing here; `run_judged` applies the rule."""
        nonlocal last_abort
        state, reason = _marked_sh(root, stamp, wt, cmd, log)
        if state == "aborted":
            last_abort = reason
            log(f"{kind}: the suite run aborted ({reason}) — not measured, nothing judged on it")
        return state

    def full_suite(wt: Path, key: str, kind: str) -> str:
        """The suite on `wt`, remembered and — on a tree it left as found — certified.
        An aborted run is passed through untouched: no memo, no certificate, no stage times."""
        dirty = certificate.clean_tree_problem(wt)
        if dirty:
            log(f"no merge certificate for this run: {dirty} before the suite")
        before = certificate.evidence_tree(wt) if dirty is None else None
        suite_before[wt] = before
        certificate.clear_run(wt)  # the `stages` file the certificate reads is this run's
        state = timed("suite", _suite_run, wt, suite, kind)
        if state == "aborted":
            return state
        _collect_stage_times(wt, stages, stage_seen, log)
        if state == "green" and (noop := certificate.noop_problem()):
            # `make -n` exits 0 having run nothing: no green to merge on (#265)
            raise EnvironmentRed(f"the suite ran under an environment that runs no recipe ({noop})")
        # the memo names what ran: a run whose scope differs from the predicted one
        # (the key's) is no green of that key (plan review)
        ran = certificate.run_evidence(wt, suite, merge_scope) if state == "green" else None
        if state == "green" and key and ran is not None \
                and key.rsplit(" ", 1)[-1] == certificate.evidence_hash(ran):
            _remember_green_suite(root, key)
            green_here.add(key)
        if state == "green":
            _certify_merge(wt, suite, before, certificate_env or [], log, merge_scope)
        return state

    # what boarding judged (#391): every run builds the SHAs on the base's SHA, so a
    # commit or a fetch after it changes no tree of this train. Without them (a caller
    # from outside, an old plan), the names, as before
    base = p.get("base_sha") or p["base"]
    shas = {c["branch"]: c["sha"] for c in p["candidates"] if c.get("sha")}
    # oldest first: boarding order is waiting order, and the bisection below
    # blames by position, so the order must mean something
    waiting = {c["branch"]: c.get("hours_waiting") or 0 for c in p["candidates"]}
    aboard.sort(key=lambda b: -waiting[b])
    if preboard:
        # before the first round, in boarding order; the preflight stays where it is, in
        # the first combined tree's judge — pre_board runs it on the base only before it
        # reports a candidate
        checks: dict = {}
        try:
            kept, _c = timed("preboard", lambda *a: pre_board(*a, shas=shas), root, base, aboard, stamp,
                             preboard, preboard_timeout, log, preflight, preflight_timeout, checks)
        except EnvironmentRed:
            # the preflight on the base's tree stopped it: an environment round, counts kept
            rounds.append({"red_path": "environment", "runs": {}})
            raise
        finally:
            moved = checks.pop("preflight_s", 0.0) or 0.0
            if moved:  # the preflight's seconds are the preflight's, not the check's
                phases["preboard"] = max(0.0, phases.get("preboard", 0.0) - moved)
                phases["preflight"] = phases.get("preflight", 0.0) + moved
            if outcome is not None:
                outcome["preboard_checks"] = checks
        if len(kept) != len(aboard):
            aboard = kept  # rebound, never changed in place: run() keeps the start count
        if not aboard:
            if outcome is not None:
                outcome["result"] = "preboard"
            log("preboard red for every candidate — nothing built")
            print(f"train: every candidate is red on the preboard check `{preboard}` — nothing built, "
                  f"nothing merged (see {logfile})", file=sys.stderr)
            return 1
    blamed: list[str] = []
    conflicted: list[str] = []
    branch = ""

    base_from_memo = False  # the base's green is the memo's, not a run's
    red_in = ""             # where the last judged tree went red: "gates" or "suite"
    last_wt: Path | None = None
    green_here: set[str] = set()  # trees whose suite this run saw green

    def merge_target(wt: Path) -> str | None:
        """Where this tree's merge goes, for the gates (v2.94 C2) — only when the
        tree differs from the base: with every passenger already contained the
        tree IS the base, never pushed, and a target there would red the arms
        that need a branch range ("no proper integration base"). Unreadable: none,
        the push hook still judges with one."""
        head = _out(wt, "rev-parse", "HEAD")
        at = _out(wt, "rev-parse", f"{base}^{{commit}}")
        return f"refs/heads/{local}" if head and at and head != at else None

    def judge(wt: Path, *, kind: str, bare_base: bool = False, memo: bool = True, fresh: bool = False) -> str:
        """"green", "red", "undefined" (the suite does not exist on this tree) or
        "aborted" (passed through from the suite run). The bare base skips the suite
        when this train saw it green on that tree — provisionally: before the first
        passenger is blamed it runs for real. `fresh` runs the suite whatever this
        train or an earlier one saw on the tree (the abort rule's base, v2.95)."""
        nonlocal base_from_memo, red_in, preflight_done
        if not preflight_done:
            if timed("preflight", _sh, wt, preflight, log, preflight_timeout) != "green":
                raise EnvironmentRed(f"the preflight `{preflight}` is red")
            preflight_done = True
        red_in = "gates"
        # the bare base runs without a target: it is never pushed (v2.94 C2)
        if not timed("gates", _run_gates, wt, log, None if bare_base else merge_target(wt)):
            return "red"
        red_in = "suite"
        if not suite:
            return "green"
        key = _suite_key(wt, suite, merge_scope)
        if key and key in green_here and not fresh:
            # a bisection probe went green on this very tree minutes ago; the
            # rebuild after the drop is the same tree (downstream: ~25 minutes
            # paid twice for one tree). Only this run's verdicts: an earlier
            # train's green on a passenger's tree is not trusted for a merge
            log(f"tree {key.split()[0][:12]}: suite green earlier in this train — not run again")
            return "green"
        if bare_base and memo and not fresh and _suite_seen_green(root, key):
            log(f"base tree {key.split()[0][:12]}: suite green on an earlier train — not run again")
            base_from_memo = True
            return "green"
        return full_suite(wt, key, kind)

    def attempt(subset: list[str], *, memo: bool = True, fresh: bool = False,
                kind: str) -> tuple[str, list[str], str]:
        """One build and judge of `subset` — the state as `judge` reads it, "aborted"
        included. Callers that evaluate a run use `run_judged`."""
        nonlocal last_wt
        with counted(kind):
            wt, br, merged, dropped = build_train(root, base, subset, stamp, log, shas=shas)
            last_wt = wt
            for d in dropped:
                if d not in conflicted:
                    conflicted.append(d)
            if not merged and subset:
                return "red", merged, br  # everybody conflicted: nothing to judge
            return judge(wt, kind=kind, bare_base=not subset, memo=memo, fresh=fresh), merged, br

    def _note_abort(waited: float = 0.0, ended: str | None = None) -> dict:
        """One aborted run in the round's `aborts`: its reason, the seconds waited before
        its repeat and how the wait ended (None: nothing was repeated after it). Returns
        the entry, for a repeat that comes later (after the fresh base)."""
        entry = {"reason": last_abort, "wait_s": round(waited, 1), "ended": ended}
        if rounds:
            rounds[-1].setdefault("aborts", []).append(entry)
        return entry

    def _repeat(subset: list[str], *, memo: bool, fresh: bool,
                entry: dict | None = None) -> tuple[str, list[str], str]:
        """The repeat of an aborted run, after the load: a bare `attempt` with the
        aborted run's own features (never `run_judged`: an aborted fresh base must not
        come back green from this train's memory, nor the guard from the memo). `entry`:
        the aborted run's `aborts` entry when it is noted already — its wait is filled in."""
        reason = last_abort if entry is None else entry["reason"]
        log(f"a suite run aborted ({reason}) — waiting for the load, then once more ({_load()})")
        waited, ended = wait_for_load(log)
        phases["abort_wait"] = phases.get("abort_wait", 0.0) + waited
        if entry is None:
            _note_abort(waited, ended)
        else:
            entry.update(wait_s=round(waited, 1), ended=ended)
        log(f"waited {waited:.0f} s for the load ({ended}) — repeating the run")
        return attempt(subset, kind="retry_abort", memo=memo, fresh=fresh)

    def abort_rule(subset: list[str], state: str, merged: list[str], br: str, *, kind: str,
                   memo: bool = True, fresh: bool = False) -> tuple[str, list[str], str]:
        """The upper layer (v2.95): what a run of `subset` that aborted counts as —
        `(state, merged, br)` of the subset's last run, never "aborted". Repeated
        ABORT_RETRIES times; aborted still, the fresh base decides: green — the subset
        runs once more, and only if that run aborts too it is red (a test that hangs on
        every run; a load that passed meanwhile blames nobody); red — `BaseRed`;
        aborted, or no base to ask (`subset` is the base, the base has no suite) —
        `SuiteAborted`."""
        nonlocal base_state, base_from_memo, retried
        if state != "aborted":
            return state, merged, br
        for _ in range(ABORT_RETRIES):
            state, merged, br = _repeat(subset, memo=memo, fresh=fresh)
            if state != "aborted":
                return state, merged, br
        repeated = _note_abort()
        if not subset:
            raise SuiteAborted(f"the base's suite run aborted, and so did its repeat ({last_abort})")
        if base_state == "undefined":
            # a passenger brings the suite: nothing tells a hang from the load — nobody is blamed
            raise SuiteAborted(f"a suite run aborted, and so did its repeat ({last_abort}); the base has "
                               "no suite to tell a hang from the load")
        log(f"a suite run aborted twice ({last_abort}) — the base runs fresh to tell a hang from the load")
        bstate, _m, _b = attempt([], kind="base", fresh=True)
        if bstate == "aborted":
            for _ in range(ABORT_RETRIES):
                bstate, _m, _b = _repeat([], memo=True, fresh=True)
                if bstate != "aborted":
                    break
            else:
                _note_abort()
                raise SuiteAborted(f"a suite run aborted, its repeat and the fresh base too ({last_abort})")
        if bstate == "red":
            base_state = "red"
            raise BaseRed(last_abort)
        if bstate != "green":
            base_state = bstate
            raise SuiteAborted(f"a suite run aborted, and so did its repeat ({last_abort}); the base reads "
                               f"{bstate} — nothing tells a hang from the load")
        # green on the base, aborted twice with the passengers: the subset once more — a
        # load or a held lane that ended between its repeat and the base blames nobody
        # (refute). Green or red, that run stands as a run of this site
        base_state, base_from_memo = "green", False
        log(f"aborted twice with {', '.join(subset)} aboard, green on the base — once more with them")
        state, merged, br = _repeat(subset, memo=memo, fresh=fresh, entry=repeated)
        if state != "aborted":
            return state, merged, br
        # aborted again on a green base: the run is red (a test of theirs hangs every
        # time); its repeat was the flake run, and no red tests are read from an abort
        _note_abort()
        if kind == "first":
            retried = True
            if red_ids:
                rounds[-1]["red_tests"] = "suite-aborted"
        log(f"aborted three times with {', '.join(subset)} aboard, green on the base — counted red")
        return "red", merged, br

    def run_judged(subset: list[str], *, kind: str, memo: bool = True,
                   fresh: bool = False) -> tuple[str, list[str], str]:
        """`attempt` plus the abort rule: every caller that evaluates a run, and none of
        them ever sees "aborted"."""
        state, merged, br = attempt(subset, kind=kind, memo=memo, fresh=fresh)
        return abort_rule(subset, state, merged, br, kind=kind, memo=memo, fresh=fresh)

    def _report_dropped(*, conflicts: bool = True) -> None:
        """`blocked` for the passengers this train dropped. `conflicts=False` (a stop that
        judged nobody: the environment, a red base): only those dropped for a real red —
        a conflict with a batch that never merged is no news its worker owes a fix for."""
        for b in conflicted if conflicts else []:
            print(f"train: {b} did not board — merge conflict with the batch; its worker rebases (report: blocked)")
            _write(root, "blocked", f"{_tower.TRAIN_DROP_NOTE} {stamp}: merge conflict — rebase onto {local}", b)
        for b in blamed:
            print(f"train: {b} was dropped as the offender — its worker owes a fix (report: blocked)")
            _write(root, "blocked", f"{_tower.TRAIN_DROP_NOTE} {stamp}: red with it aboard", b)

    base_state = ""  # the base's verdict, checked once ("": not yet)
    retried = told = False
    # who left before the push: a hold set during the run (#335) — on the row as `held`
    held: list[str] = outcome.setdefault("held", []) if outcome is not None else []
    seen = p.get("reports_seen")  # the report identities at boarding; None: no check

    def held_during_run() -> bool:
        """After the last green verdict, before the push (#335): a passenger whose
        worker holds it now, or reported a `blocked` since boarding — released or
        not, the release is for its new tip —, leaves, and so does a passenger
        stacked on it (its SHA contains the held one's). The worker's own report
        is the record: the train writes no `blocked`. True when somebody left: the
        smaller board is a new combination and runs as a new round. Known rest: a
        hold that arrives while the push's own pre-push gates run."""
        nonlocal aboard, retried
        if seen is None:
            return False
        if not _report.fetch_reports(root):
            log("hold check: could not fetch the published reports — reading the ones this clone has")
        found = _tower.held_since(root, seen)
        direct = [b for b in aboard if b in found]
        if not direct:
            return False
        why = {b: f"`{found[b]['state']}` ({found[b].get('note') or 'no reason given'})" for b in direct}
        for b in aboard:
            if b in why:
                continue
            under = next((h for h in direct if _git(root, "merge-base", "--is-ancestor", shas.get(h, h),
                                                    shas.get(b, b)).returncode == 0), None)
            if under:
                why[b] = f"it contains {under}"
        for b in (b for b in aboard if b in why):
            held.append(b)
            log(f"{b} held during the run — {why[b]}; the rest is rebuilt without it")
            print(f"train: {b} held during the run — {why[b]}; rebuilding without it", file=sys.stderr)
        aboard = [b for b in aboard if b not in why]
        retried = False  # a new combination earns its own flake re-run
        return True

    def check_base() -> str:
        nonlocal base_state
        if not base_state:
            base_state = run_judged([], kind="base")[0]
        return base_state

    def _red_base(aborted: str | None = None) -> int:
        """Main is red: nobody blamed in this round, nothing merged. A passenger dropped
        for a real red in an earlier round of this train is still reported. `aborted`:
        the reason, when a run that aborted twice made the train ask the base."""
        _end_round(measure, "base-red")
        if aborted is None:
            print("train: the combined tree is red and the base is red too — the "
                  "integration branch itself is red (gates or suite fail with nobody aboard); "
                  "no candidate blamed, "
                  "nothing merged — fix main first", file=sys.stderr)
            log("base red and combined red — aborted without blame")
        else:
            print(f"train: a suite run aborted twice ({aborted}), and the base, run fresh, is red — the "
                  "integration branch itself is red (gates or suite fail with nobody aboard); "
                  "no candidate blamed, nothing merged — fix main first", file=sys.stderr)
            log(f"a run aborted twice ({aborted}), the fresh base red — aborted without blame")
        _report_dropped(conflicts=False)
        _cleanup(root, stamp)
        return 1

    # `full` from here to before the push (v2.97 B7): after the preboard, whose probes are
    # seconds; a train that cannot take it ends in a round of its own, nothing built
    try:
        full_lane = _hold_full(root, stamp, log)
    except LaneHeld:
        rounds.append({"red_path": "lane-held", "runs": {}})
        raise
    # the abort rule's two exits (v2.95): a red fresh base is main's, a stop that blames
    # nobody still reports who was dropped for a real red in an earlier round — on every
    # environment stop of a round, the preflight's and a no-op suite's included; a passenger
    # that only conflicted is not reported there
    try:
        while aboard:
            # a round: the first run, and each one after a drop
            rounds.append({"red_path": None, "runs": {}})
            state, merged, branch = run_judged(aboard, kind="first")
            aboard = merged
            if state == "green" or not aboard:
                _end_round(measure, "green" if state == "green" else "conflicts")
                if state == "green" and held_during_run():
                    continue
                break
            if red_ids and state == "red" and "red_tests" not in rounds[-1]:
                # read only, before any other run rebuilds the worktree: the board tree is this
                # one (after an abort, the last run's with the passengers; "suite-aborted" when
                # that run aborted too)
                rounds[-1]["red_tests"] = "gates-red" if red_in == "gates" else \
                    red_tests(last_wt, base, red_ids, red_cache)
            if state == "undefined":
                if check_base() == "undefined":
                    _end_round(measure, "undefined")
                    print(f"train: the suite `{suite}` does not exist on the combined tree — fix the suite "
                          "command (merge_suite in docs/process/testing.local.json, or --suite where none "
                          "is set); nothing merged", file=sys.stderr)
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
            searching = "retry"
            if not retried:
                # one more run of the SAME tree before anybody is blamed: red then
                # green on identical code is a flaky test (observed downstream: a
                # 5 s lock wait and a 5.1 s UI test under load 10 on 6 CPUs), not
                # an offender — bisecting a flake blames whoever sits in the prefix
                retried = True
                how, why = retry_plan(red_in, retry)
                if how != "full" and (last_wt is None or _changed_by_run(last_wt)):
                    # the first run wrote into the tree (a snapshot baseline it
                    # generated, a lockfile): the worktree is no longer the judged
                    # tree, and a retry there could pass on that residue (refutation)
                    how, why = "full", "the first run changed the worktree — rebuild and run the whole suite"
                log(f"red — retry of the same combined tree: {how} — {why} ({_load()})")
                # what the retry really ran decides what a green may claim (#263): only the
                # same suite on the same tree is a flake; a narrower command is a subset
                ran = "full"
                if how == "gates" and last_wt is not None:
                    ran = "gates"
                    with counted("retry_gates"):
                        state = "green" if timed("gates", _run_gates, last_wt, log, merge_target(last_wt)) else "red"
                    if state == "green" and suite:
                        red_in = "suite"
                        # the suite never ran behind the red gates
                        with counted("retry_full"):
                            state = full_suite(last_wt, _suite_key(last_wt, suite, merge_scope), "retry_full")
                        # the rule outside the `counted` block: its repeat counts as a run of its own.
                        # A green repeat stays a gate flake, the suite ran green for the first time
                        if state == "aborted":
                            state, merged, branch = abort_rule(aboard, state, aboard, branch, kind="retry_full")
                            aboard = merged
                            if state != "green":
                                ran = "full"
                elif how == "failed" and last_wt is not None:
                    ran = "retry"
                    with counted("retry_failed"):
                        state = timed("retry", _suite_run, last_wt, retry, "retry_failed")
                        if state != "aborted":
                            _collect_stage_times(last_wt, stages, stage_seen, log)
                        noop = certificate.noop_problem()
                        if noop and state == "green":
                            # `make -n` exits 0 having run nothing: no green to merge on (#265)
                            raise EnvironmentRed(f"the retry ran under an environment that runs no recipe ({noop})")
                    if state == "aborted":
                        # the repeat rebuilds the tree and runs the whole suite: `--retry` does not
                        # run again, and a green is the full suite's
                        ran = "full"
                        state, merged, branch = abort_rule(aboard, state, aboard, branch, kind="retry_failed")
                        aboard = merged
                    if state == "undefined" and ran == "retry":  # no such command on this tree: the whole suite
                        log("the --retry command does not exist on this tree — rebuilding for the whole suite")
                        ran = "full"
                        state, merged, branch = run_judged(aboard, kind="retry_full")
                        aboard = merged
                else:
                    state, merged, branch = run_judged(aboard, kind="retry_full")
                    aboard = merged
                searching = ""
                if state == "green":
                    _end_round(measure, "gate-flaky" if ran == "gates" else "flaky")
                    if ran == "retry":
                        # the suite ran whole on this tree and the retry re-ran what failed, green:
                        # certified only when every stage of the scope has a green marker now — a
                        # stage the first run never reached is no pass the retry made (#265, refute)
                        if _every_stage_green(last_wt):
                            _certify_merge(last_wt, suite, suite_before.get(last_wt), certificate_env or [], log,
                                           merge_scope)
                        else:
                            log("retry green, but not every stage of the scope ran green on this tree — "
                                "no merge certificate; the push runs the suite")
                        print(f"train: green under the retry command `{retry}` (it re-ran only what failed), "
                              f"red under the suite `{suite}` — flaky, or the two runs differ (flags, "
                              f"environment); merging "
                              f"(see {logfile}; {_load()})", file=sys.stderr)
                        log(f"red under `{suite}`, then green under the retry command `{retry}` — flaky or "
                            "the commands differ, merging")
                    elif ran == "gates":
                        print("train: the gates were red, then green on the identical tree — a gate flake"
                              + ("; the suite then ran green for the first time" if suite else "")
                              + f"; merging (see {logfile}; {_load()})", file=sys.stderr)
                        log("gates red then green on the identical tree — gate flake, merging")
                    else:
                        print("train: FLAKY — the combined tree was red, then green on the identical tree; "
                              f"merging, but the suite has a flaky test (see {logfile}; {_load()})", file=sys.stderr)
                        log("red then green on the identical tree — flaky suite, merging")
                    if held_during_run():
                        continue
                    break
            # before blaming anybody: is the base itself red (a broken main)?
            # Then no candidate is the offender.
            searching = "bisect"
            if check_base() == "red":
                return _red_base()
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
                pstate, pmerged, _br = run_judged(aboard[:mid], kind="probe")
                # a prefix without the passenger that defines the suite cannot be
                # judged by it — it is not the offender; where the base has the
                # suite, a prefix without it lost it: red
                if (pstate == "green" or (pstate == "undefined" and base_state == "undefined")) \
                        and len(pmerged) == mid:
                    lo = mid + 1
                else:
                    hi = mid
            if lo == 1 and base_from_memo:
                # every prefix red and the base green only by the memo: main may
                # have turned red outside the tree (a host or dependency upgrade,
                # a date) — run the base for real before the first passenger is
                # blamed (refutation: otherwise each one is dropped in turn)
                base_from_memo = False
                log("first passenger about to be blamed on a remembered base — running the base")
                base_state = run_judged([], kind="base", memo=False)[0]
                if base_state == "red":
                    return _red_base()
            offender = aboard[lo - 1]
            blamed.append(offender)
            # the rest is a new combination: it earns its own flake re-run (the
            # base does not change — its verdict is kept)
            retried = False
            searching = ""
            log(f"red with {offender} aboard — dropped, rebuilding")
            print(f"train: red with {offender} aboard — dropping it and rebuilding")
            aboard = [b for b in aboard if b != offender]
            _end_round(measure, f"dropped:{offender}")
    except BaseRed as red_base:
        return _red_base(aborted=str(red_base))
    except EnvironmentRed:
        _report_dropped(conflicts=False)
        raise
    finally:
        full_lane.close()  # before the push: its hook takes `full` itself
    if not aboard:
        if rounds and str(rounds[-1]["red_path"]).startswith("dropped:"):
            _end_round(measure, "none-survived")  # the last drop left nobody aboard
        print("train: nothing survived" + (f" — held during the run: {', '.join(held)}" if held else "")
              + " — see " + str(logfile), file=sys.stderr)
        _report_dropped()
        _cleanup(root, stamp)
        return 1
    if _git(root, "merge-base", "--is-ancestor", local, base).returncode != 0:
        print(f"train: local {local} carries commits that are not on {p['base']} — push or drop them first; "
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
        r = timed("push", lambda: _git(_train_worktree(root), "push", "origin", f"HEAD:{local}",
                                       env={MERGE_ROUTE_ENV: MERGE_ROUTE}))
        if r.returncode != 0:
            _end_round(measure, "push-rejected")
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
    if outcome is not None:
        outcome["branches"] = list(aboard)
    log(f"{local} fast-forwarded to {branch} ({_out(root, 'rev-parse', '--short', 'HEAD')})")
    print(f"train: {local} → {_out(root, 'rev-parse', '--short', 'HEAD')} with {', '.join(aboard)}"
          + (" (pushed)" if push else ""))
    import dispatch as _dispatch  # lazily, as tower does
    # a branch that moved since boarding merged at its boarded SHA (#391): its new
    # commits are unreviewed and unmerged — it stays, with its records and worktree
    moved = {b: shas[b] for b in aboard
             if b in shas and _out(root, "rev-parse", "--verify", "--quiet", f"refs/heads/{b}") != shas[b]}
    try:
        # merged now: their worktrees (each with its own venv/node_modules) are
        # residue — dispatch says which may go; asked before forget_branch drops records
        worktrees = {wt["branch"]: (wt, why) for wt, why in
                     _dispatch.merged_worktrees(root, local, [b for b in aboard if b not in moved])}
    except Exception as exc:  # noqa: BLE001 — cleanup after the merge: say so, never abort a landed train
        print(f"train: merged worktrees not checked — {exc}", file=sys.stderr)
        worktrees = {}
    for b in aboard:
        tip = shas.get(b) or b
        if b in shas and b not in moved \
                and _out(root, "rev-parse", "--verify", "--quiet", f"refs/heads/{b}") != shas[b]:
            # it moved while the merged ones were reported: re-read right before its own
            # report and cleanup (DeepSeek v2.90)
            moved[b] = shas[b]
        # a `Regression-of: #N` trailer names the issue a fix repairs, not one this
        # branch works on — it must neither file the merge under #N nor ask to close it.
        # What merged, against the base it merged on: after the push `origin/main`
        # contains the branch, and `origin/main..b` read nothing
        bodies = REGRESSION_LINE.sub("", _out(root, "log", "--format=%B", f"{base}..{tip}"))
        refs = sorted({int(n) for n in re.findall(r"(?<![\w/])#(\d+)\b", bodies)})
        if refs:
            print(f"train: {b} references issue(s) {', '.join('#' + str(n) for n in refs)} — "
                  "closed by GitHub where a commit says Closes; the steward closes the rest with the merge ref")
            log(f"{b} issues: {refs}")
        if b in moved:
            # no `done`, no forget: its worker is still at it, and its issues with it.
            # Known rest: a `Closes #N` of the boarded commits closes N all the same
            said = (f"{b} moved since boarding — merged at {moved[b][:12]}; its new commits need their own "
                    "review and train")
            print(f"train: {said}")
            log(said)
            continue
        try:
            _report.write_report(root, "done", issue=refs[0] if refs else None,
                                 note=f"merged by train {stamp}" + (f"; issues {refs}" if refs else ""), worker=b)
        except SystemExit:
            pass
        try:
            _dispatch.forget_branch(root, b)  # merged: its issues are placed on it no more
        except Exception as exc:  # noqa: BLE001 — bookkeeping after the merge: say so, never abort a landed train
            print(f"train: dispatch still places {b}'s issues on it — could not forget it: {exc}",
                  file=sys.stderr)
        if b in worktrees:
            wt, why = worktrees[b]
            if why:
                print(f"train: worktree {wt['path']} of {b} kept — {why}")
            else:
                try:
                    failed = _dispatch.remove_worktree(root, wt["path"], local)
                except Exception as exc:  # noqa: BLE001 — a note, never a train failure
                    failed = str(exc)
                print(f"train: worktree {wt['path']} of {b} " + (f"not removed — {failed}" if failed else "removed"))
                log(f"worktree {wt['path']} of {b}: {failed or 'removed'}")
        if not keep_branches:
            _delete_branch(root, b, shas.get(b), push=push, log=log)
    _cleanup(root, stamp)
    _report_dropped()
    if deploy:
        deployed = timed("deploy", _sh, root, deploy, log) == "green"
        if outcome is not None:
            outcome["deployed"] = deployed
        if not deployed:
            print("train: deploy failed — the merge stands, the deploy does not; see " + str(logfile), file=sys.stderr)
            return 1
    return 0


def _delete_branch(root: Path, b: str, sha: str | None, *, push: bool, log) -> None:
    """A merged passenger's branch goes — only as it boarded (#391): locally
    `update-ref -d` with the boarded SHA (a commit in the meantime keeps it), on
    origin a delete under `--force-with-lease` of that SHA (a worker's push from
    elsewhere keeps the copy). Without a SHA, `branch -d` as before. A branch
    checked out in a worktree stays, and so does its origin copy."""
    if sha is None:
        d = _git(root, "branch", "-d", b)
    elif _checked_out(root, b):
        d = subprocess.CompletedProcess([], 1, "", "checked out in a worktree")
    else:
        d = _git(root, "update-ref", "-d", f"refs/heads/{b}", sha)
    if d.returncode != 0:
        print(f"train: local branch {b} kept — {d.stderr.strip().splitlines()[-1] if d.stderr.strip() else 'delete refused'} "
              "(checked out in a worktree, or moved?); origin copy kept too", file=sys.stderr)
        return
    if not push:
        return
    if sha is None:
        _git(root, "push", "origin", "--delete", b)
        return
    r = _git(root, "push", f"--force-with-lease=refs/heads/{b}:{sha}", "origin", f":refs/heads/{b}")
    if r.returncode != 0 and ("stale info" in r.stderr or "rejected" in r.stderr):
        # origin's copy may only lag: the worker never pushed its last commits — an
        # ancestor of what merged loses nothing (refute v2.90)
        theirs = (_out(root, "ls-remote", "origin", f"refs/heads/{b}") or "").split()
        if not theirs:
            return  # origin never had it, or it is gone already: nothing moved, nothing to delete
        older = _git(root, "merge-base", "--is-ancestor", theirs[0], sha).returncode == 0
        if older:
            r = _git(root, "push", f"--force-with-lease=refs/heads/{b}:{theirs[0]}", "origin", f":refs/heads/{b}")
    if r.returncode != 0 and ("stale info" in r.stderr or "rejected" in r.stderr):
        print(f"train: origin's {b} kept — it moved since boarding (a push from elsewhere); "
              f"its new commits need their own review and train", file=sys.stderr)
        log(f"origin's {b} kept — moved since boarding")


def _checked_out(root: Path, b: str) -> bool:
    """Is `b` the branch of a worktree of this clone? None readable counts as yes."""
    r = _git(root, "worktree", "list", "--porcelain")
    return r.returncode != 0 or f"branch refs/heads/{b}" in r.stdout.splitlines()


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


def conflict_hints(root: Path, cands: list[dict]) -> list[dict]:
    """Pairwise conflicts among the candidates that may board, as git's own merge
    of the two tips sees them (`check_review._auto_merge`): {"branches": [a, b],
    "paths": [...]}, `paths` None where git could not tell — never read as clean.
    A note for `plan` only: `run` calls `plan()` and must not pay for it (#379);
    the run itself drops the later of a conflicting pair (`build_train`). Pairs
    come in boarding order — oldest first, the order `_run_batch` sorts by — so
    "the later" is the one the run drops (refute v2.87: listing order named the
    wrong branch)."""
    aboard = [c["branch"] for c in sorted((c for c in cands if c["eligible"]),
                                          key=lambda c: -(c.get("hours_waiting") or 0))]
    tip = {c["branch"]: c.get("sha") or c["branch"] for c in cands}  # as boarding judged them (#391)
    pairs = [(first, second) for i, first in enumerate(aboard) for second in aboard[i + 1:]]
    _review._auto_merges(root, [(tip[first], tip[second]) for first, second in pairs])  # one git for all (#398)
    hints: list[dict] = []
    for first, second in pairs:
        merged = _review._auto_merge(root, tip[first], tip[second])
        if merged is None or merged[1]:
            hints.append({"branches": [first, second],
                          "paths": sorted(merged[1]) if merged is not None else None})
    return hints


def _candidate_lines(c: dict) -> list[str]:
    """One candidate as `plan` shows it: its line, then its reasons."""
    mark = "✓" if c["eligible"] else "·"
    extra = f" — {c['by']}" if c.get("by") and c["eligible"] else ""
    held = c.get("keeps_open") or []
    keeps = f", keeps {', '.join(f'#{n}' for n in held)} open" if held else ""
    line = (f"  {mark} {c['branch']} (+{c['ahead']}/-{c['behind']}, {c.get('files', 0)} file(s), "
            f"{c.get('hours_waiting', '?')} h, {c.get('deviations', 0)} DoD deviation(s){keeps}){extra}")
    return [line] + [f"      - {r}" for r in c["reasons"]]


def _no_lead_lines(p: dict) -> list[str]:
    n = p.get("no_lead") or 0
    return [f"  {n} branch(es) without a lead on {p['base']} — merged or empty, not candidates"] if n else []


def left_behind(p: dict) -> list[str]:
    """Who does not board, and why (#399): every candidate that is not eligible, as
    `render_plan` shows it, and the branches without a lead."""
    return [line for c in p["candidates"] if not c["eligible"] for line in _candidate_lines(c)] + _no_lead_lines(p)


def render_plan(p: dict) -> str:
    lines = [f"train plan — base {p['base']}: {'READY' if p['ready'] else 'hold'} ({p['why']})"]
    for c in p["candidates"]:
        lines += _candidate_lines(c)
    lines += _no_lead_lines(p)
    for h in p.get("conflicts") or []:
        first, second = h["branches"]
        if h["paths"] is None:
            lines.append(f"  note: {first} × {second}: could not check for a conflict (git merge-tree)")
        else:
            lines.append(f"  note: {first} × {second} conflict ({', '.join(h['paths'])}) — merged in "
                         f"this order, the train drops {second} unless {first} is dropped first")
    return "\n".join(lines)


def resolve_suite(cli: str | None, merge_suite: str | None, *,
                  differs_ok: bool) -> tuple[str | None, str | None, str | None]:
    """(suite to run, refusal, note to log) for `run --suite`. With `merge_suite`
    configured, the push to main looks the merge certificate up under that
    command, so `--suite` must be it — finish.py's rule, equal after `strip` —
    and the run uses `merge_suite` itself: the certificate's evidence is then the
    hook's string exactly (#381). `--suite-differs-ok` lets a deliberate
    difference through and names it for the train log. Without `merge_suite`
    the caller's command runs as before."""
    if not cli or not merge_suite:
        return cli or merge_suite, None, None
    if cli.strip() == merge_suite:
        return merge_suite, None, None
    if differs_ok:
        return cli, None, (f"--suite-differs-ok: running `{cli}`, not merge_suite `{merge_suite}` — "
                           "its merge certificate will not match the push, which runs merge_suite again")
    return None, (f"train: --suite `{cli}` is not merge_suite `{merge_suite}` of "
                  "docs/process/testing.local.json — the push to main looks the merge certificate up "
                  "under merge_suite, so a certificate of this run would never match and the push "
                  "runs the suite again. Drop --suite (it defaults to merge_suite) or make it equal; "
                  "--suite-differs-ok only when the difference is deliberate — a passenger changes "
                  "merge_suite itself; nothing boarded"), None


def main(argv: list[str]) -> int:
    # a parent's marker is no run of this train: no selector, check or other child of
    # the train inherits it — the suite runs get their own (`_marked_sh`)
    os.environ.pop(SUITE_ABORT_ENV, None)
    p = argparse.ArgumentParser(prog="train.py", description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="command", required=True)
    for name in ("plan", "run"):
        s = sub.add_parser(name)
        s.add_argument("--min-candidates", type=int, default=int(os.environ.get("PROCESS_TRAIN_MIN", "3")))
        s.add_argument("--max-wait-hours", type=float, default=float(os.environ.get("PROCESS_TRAIN_MAX_WAIT_H", "4")))
        s.add_argument("--root", default=".")
    sub.choices["plan"].add_argument("--json", action="store_true")
    r = sub.choices["run"]
    r.add_argument("--suite", help="the full suite command, run once on the combined tree "
                                   "(default: merge_suite of docs/process/testing.local.json; with "
                                   "merge_suite set, another command is refused)")
    r.add_argument("--suite-differs-ok", action="store_true",
                   help="run a --suite other than merge_suite on purpose (a passenger changes "
                        "merge_suite itself); logged in the train log")
    r.add_argument("--preflight", help="an environment check run once before the gates; red stops the "
                                       "run without blaming anybody (default: preflight of "
                                       "docs/process/testing.local.json)")
    r.add_argument("--preboard", help="a check of seconds run on base+candidate before each candidate "
                                      "boards; red twice keeps it off the train (default: preboard of "
                                      "docs/process/testing.local.json; \"\" runs none)")
    r.add_argument("--retry", help="after a red suite: re-run what failed and what did not run, on the same "
                                   "tree (default: the whole suite again)")
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
        # computed here, not in plan(): `run` calls plan() and must not pay for the hint (#379)
        result["conflicts"] = conflict_hints(root, result["candidates"])
        result.pop("reports_seen", None)  # the run's comparison set, not the plan's word
        print(json.dumps(result, indent=2) if a.json else render_plan(result))
        return 0
    import testing_config  # noqa: PLC0415

    try:
        cfg = testing_config.load(root)
    except testing_config.ConfigError as exc:
        print(f"train: {exc} — fix it first; the suite and the certificates read it", file=sys.stderr)
        return 2
    suite, refusal, suite_note = resolve_suite(a.suite, cfg["merge_suite"] if cfg else None,
                                               differs_ok=a.suite_differs_ok)
    if refusal:
        print(refusal, file=sys.stderr)
        return 2
    # the configured environment check is the train's too; an explicit one wins,
    # `--preflight ""` included (none for this run)
    # and every stack's own after it (#373) — always, `--preflight` replaces only the
    # global one: a merge runs every stack, so any non-zero exit, 3 ("this host cannot
    # run it") included, is the environment, never a red train
    first = a.preflight if a.preflight is not None else (
        shlex.join(cfg["preflight"]) if cfg and cfg["preflight"] else "")
    checks = [first] if first.strip() else []
    checks += [shlex.join(s["preflight"]) for s in (cfg["stacks"] if cfg else []) if s.get("preflight")]
    preflight = " && ".join(checks) if checks else None
    # the configured preboard check likewise; `--preboard ""` runs none for this run (#386)
    preboard = a.preboard if a.preboard is not None else (
        shlex.join(cfg["preboard"]) if cfg and cfg["preboard"] else "")
    return run(root, suite=suite, deploy=a.deploy, push=a.push, min_candidates=a.min_candidates,
               max_wait_hours=a.max_wait_hours, force=a.force, keep_branches=a.keep_branches,
               dry_run=a.dry_run, retry=a.retry, preflight=preflight,
               certificate_env=cfg["certificate_env"] if cfg else [],
               merge_scope=cfg["merge_scope"] if cfg else None, suite_note=suite_note,
               red_ids=cfg["red_ids"] if cfg else None,
               preflight_timeout=cfg["preflight_timeout"] if cfg else testing_config.DEFAULT_PREFLIGHT_TIMEOUT,
               preboard=preboard if preboard.strip() else None,
               preboard_timeout=cfg["preboard_timeout"] if cfg else testing_config.DEFAULT_PREBOARD_TIMEOUT)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
