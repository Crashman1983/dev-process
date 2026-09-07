#!/usr/bin/env python3
"""finish: the merge-tail checker — is this branch actually done?

The failures this exists for are all tail failures observed in production:
a plan merged without its clearing pass, a pass recorded but the plan never
archived, a merge that left branch and worktree behind. `/finish` runs the
tail as ONE readable verdict instead of a ritual scattered over four docs.

Read-only by default: it verifies and then PRINTS the exact remaining
commands. With `--apply` it executes the deterministic part itself
(archive commit, rebase; then merge, push and branch delete only behind the
batch's full suite, `--tests CMD` or `--tests-passed`) — every step prints
its command and the first failure stops in a state git explains.

Checks, in order:
  1. on a feature branch (finishing main is meaningless)
  2. worktree clean (an unfinished tree cannot be finished)
  3. every active tier-2+ plan THIS BRANCH OWNS has its clearing REVIEW pass
     (verdict=pass, matching work id, tier>=plan tier) or a review-waived
     line — the exact arithmetic of the review gate, imported from
     check_review (one owner). Owned = the plan file is in the branch's
     committed range, or a commit in that range claims the plan's issue;
     somebody else's decision paper sitting in the tree is neither this
     branch's review debt nor its archiving duty. Without a determinable
     merge base the check stays conservative (every active plan).
  4. the registered local hooks can actually run (gate_invoke's hook doctor)
     — a check that is missing is a blocker, never a skip
  5. the gate suite is green (gate_runner, launched via gate_invoke); "not
     runnable" is reported distinctly from "red"
Then it prints the tail: archive plan(s) -> merge -> delete branch ->
remove worktree -> publish/prune where those modules are installed.

Exit 0 = ready (tail printed); exit 1 = blocked (blockers printed).
Pure stdlib + sibling imports.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

# the checker must not dirty the tree it is judging clean: the sibling import
# below would otherwise drop a __pycache__ into scripts/process
sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling import
from check_review import (  # noqa: E402  (one owner for grammar + arithmetic)
    JOURNAL_DIR,
    PLANS_ACTIVE,
    PLANS_ARCHIVE,
    SPECS_DIR,
    TIER_DECL,
    WAIVED,
    _cleared,
    _plan_issue_numbers,
    _plan_work_ids,
    _unfenced,
    issue_refs_in_range,
    merge_base,
    parse_review_lines,
    paths_in_flight,
    speckit_unreviewed,
)
from gate_invoke import (  # noqa: E402  (one owner for "how to launch")
    gate_runner_argv,
    hook_wiring_findings,
    not_runnable_reason,
)


def _git(*args: str) -> str | None:
    proc = subprocess.run(["git", *args], capture_output=True, text=True,
                          cwd=str(ROOT))
    return proc.stdout.strip() if proc.returncode == 0 else None


def _journal_passes(root: Path) -> list[dict]:
    passes: list[dict] = []
    jdir = root / JOURNAL_DIR
    if not jdir.is_dir():
        return passes
    for f in sorted(jdir.glob("**/*.md")):
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        records, _ = parse_review_lines(text)
        passes += [r for _ln, r in records if r.get("verdict") == "pass"]
    return passes


def check(root: Path) -> tuple[list[str], list[str]]:
    """(blockers, tail) — tail is the printable remaining ritual."""
    blockers: list[str] = []
    tail: list[str] = []

    branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    if branch is None:
        return ["not a git repository (or git missing)"], []
    if branch in {"main", "master"}:
        return [f"on {branch} — there is no feature branch to finish"], []

    dirty = _git("status", "--porcelain")
    if dirty:
        blockers.append(f"worktree not clean ({len(dirty.splitlines())} "
                        f"entr(y/ies)) — commit or stash before finishing")

    # --- clearing pass per active tier-2+ plan (review-gate arithmetic) ---
    passes = _journal_passes(root)
    # the same scope as the review gate's push-anchored arm: a plan is this
    # branch's business when the branch carries its file or claims its issue
    in_flight = paths_in_flight(root) if merge_base(root) is not None else None
    claimed_issues = issue_refs_in_range(root)
    to_archive: list[str] = []
    pdir = root / PLANS_ACTIVE
    if pdir.is_dir():
        for p in sorted(pdir.glob("*.md")):
            if p.name.startswith("design-") or not p.is_file():
                continue
            text = _unfenced(p.read_text(encoding="utf-8", errors="replace"))
            if (in_flight is not None
                    and f"{PLANS_ACTIVE}/{p.name}" not in in_flight
                    and not (_plan_issue_numbers(text) & claimed_issues)):
                continue  # somebody else's plan — not this branch's tail
            m = TIER_DECL.search(text)
            if not m:
                continue
            tier = int(m.group(1))
            if tier < 2:
                to_archive.append(p.name)
                continue
            if WAIVED.search(text):
                to_archive.append(p.name)
                continue
            ids = _plan_work_ids(p.stem, text, include_dedated=True)
            if _cleared(passes, ids, tier):
                to_archive.append(p.name)
            else:
                blockers.append(
                    f"{PLANS_ACTIVE}/{p.name}: tier {tier} plan has no clearing "
                    f"REVIEW (verdict=pass, work in {sorted(ids)}, tier>={tier}) "
                    f"and no 'review-waived:' line — run /review before /finish")

    # --- speckit-path plans: same presence question, different home — the
    # spec dir's plan never enters the archive, its completion signal is the
    # fully-ticked tasks.md (the review gate's blind spot; this IS the stop)
    done_spec_dirs: list[str] = []
    sdir = root / SPECS_DIR
    if sdir.is_dir():
        for name, tier, ids in speckit_unreviewed(root, passes):
            blockers.append(
                f"{SPECS_DIR}/{name}: tasks all ticked, plan declares tier "
                f"{tier}, but no clearing REVIEW (verdict=pass, work in "
                f"{sorted(ids)}, tier>={tier}) and no 'review-waived:' line — "
                f"run /review before /finish")
        for d in sorted(p for p in sdir.iterdir() if p.is_dir()):
            tasks = d / "tasks.md"
            if tasks.is_file():
                ttext = tasks.read_text(encoding="utf-8", errors="replace")
                if not re.search(r"^\s*- \[ \] ", ttext, re.MULTILINE) \
                        and re.search(r"^\s*- \[[xX]\] ", ttext, re.MULTILINE):
                    done_spec_dirs.append(d.name)

    # --- hook wiring: a registered check that cannot run is a missing check,
    # and a missing check is a blocker, never a skip
    hook_hard, hook_soft = hook_wiring_findings(root)
    for finding in hook_hard + hook_soft:
        blockers.append(f"hooks: {finding}")

    # --- gates --- ("not runnable" and "red" are different failures with
    # different owners; naming them apart is the whole point of the launcher)
    argv = gate_runner_argv(root)
    if argv is None:
        blockers.append(f"gate suite NOT RUNNABLE (not red): "
                        f"{not_runnable_reason(root)}")
    else:
        gr = subprocess.run(argv, cwd=str(root), capture_output=True, text=True)
        if gr.returncode != 0:
            last = [ln for ln in (gr.stdout + gr.stderr).splitlines()
                    if ln.strip()][-3:]
            blockers.append("gate suite red: " + " | ".join(last))

    check.last_archive = list(to_archive)  # apply() reuses the same verdict
    if blockers:
        return blockers, []

    # --- the remaining tail, in execution order ---
    default = "main" if _git("rev-parse", "--verify", "--quiet", "main") \
        else "master"
    for name in to_archive:
        tail.append(f"git mv {PLANS_ACTIVE}/{name} {PLANS_ARCHIVE}/{name} "
                    f"&& git commit  # archive the plan ON the branch (last "
                    f"commit before merge)")
    behind = _git("rev-list", "--count", f"{branch}..origin/{default}")
    if behind and behind != "0":
        tail.append(f"git fetch origin {default} && git rebase origin/{default}"
                    f"  # {behind} commit(s) behind — NOTE: a rebase voids "
                    f"review-bundle digests; re-review if a bundle was built")
    tail.append("run the FULL test suite now — the whole batch pays it once "
                "here; scoped runs during the loop were evidence, not the "
                "verdict (docs/process/testing.md, test economy)")
    tail.append(f"merge: PR with linear-history merge, or locally "
                f"`git checkout {default} && git merge --ff-only {branch} "
                f"&& git push`")
    tail.append(f"git push origin --delete {branch}  # or let the platform "
                f"auto-delete / cleanup-branches workflow")
    tail.append("git worktree remove <path> && git worktree prune  # if this "
                "branch rode a worktree")
    if (root / "scripts/process/publish_and_prune.py").is_file():
        if done_spec_dirs:
            for name in done_spec_dirs:
                tail.append(f"python scripts/process/publish_and_prune.py "
                            f"{SPECS_DIR}/{name}  # publish the outcome, "
                            f"prune the finished working set")
        else:
            tail.append("python scripts/process/publish_and_prune.py "
                        "<feature-dir>  # publish the outcome, prune the spec "
                        "working set")
    tail.append("close the tracking issue with the merge commit ref (DoD)")
    return [], tail


def _sh(root: Path, argv: list[str]) -> bool:
    """Run one tail command visibly; False on failure (the caller stops)."""
    print(f"finish: $ {' '.join(argv)}")
    return subprocess.run(argv, cwd=str(root)).returncode == 0


def apply(root: Path, *, tests: str | None, tests_passed: bool) -> int:
    """--apply: execute the deterministic part of the tail instead of
    printing it for an agent to retype. Archive commit and rebase always;
    the merge only behind the batch's full suite — run here via --tests
    CMD, or asserted with --tests-passed. Every step prints its command and
    the first failure stops the run: the tree is then in a state git
    explains (a rebase conflict, a rejected push), never half-merged."""
    blockers, _tail = check(root)
    if blockers:
        print("finish: BLOCKED — nothing applied:")
        for b in blockers:
            print(f"  - {b}")
        return 1
    branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    default = "main" if _git("rev-parse", "--verify", "--quiet", "main") \
        else "master"
    # 1. archive the branch-owned plans ON the branch
    to_archive = list(getattr(check, "last_archive", []))
    if to_archive:
        (root / PLANS_ARCHIVE).mkdir(parents=True, exist_ok=True)
        for name in to_archive:
            if not _sh(root, ["git", "mv", f"{PLANS_ACTIVE}/{name}",
                              f"{PLANS_ARCHIVE}/{name}"]):
                return 1
        if not _sh(root, ["git", "commit", "-q", "-m",
                          f"docs: archive plan(s) on merge — "
                          f"{', '.join(to_archive)}"]):
            return 1
    # 2. rebase onto the moved integration branch (gates re-run below)
    if _git("rev-parse", "--verify", "--quiet", f"origin/{default}") is not None:
        if not _sh(root, ["git", "fetch", "-q", "origin", default]):
            return 1
        behind = _git("rev-list", "--count", f"{branch}..origin/{default}")
        if behind and behind != "0":
            if not _sh(root, ["git", "rebase", "-q", f"origin/{default}"]):
                print("finish: rebase stopped — resolve, `git rebase "
                      "--continue`, then re-run /finish --apply")
                return 1
            print("finish: rebased — NOTE: a rebase voids review-bundle "
                  "digests; re-review if a bundle was built")
            blockers, _tail = check(root)
            if blockers:
                print("finish: BLOCKED after rebase:")
                for b in blockers:
                    print(f"  - {b}")
                return 1
    # 3. the batch pays completeness once, here
    if tests:
        print(f"finish: $ {tests}   # the FULL suite, once per batch")
        if subprocess.run(tests, shell=True, cwd=str(root)).returncode != 0:
            print("finish: full suite red — not merging")
            return 1
    elif not tests_passed:
        print("finish: applied archive + rebase; stopped before the merge — "
              "run the FULL test suite now, then re-run with "
              "`--apply --tests-passed` (or pass `--tests CMD` to run it here)")
        return 0
    # 4. merge ff-only, push, delete the remote branch
    for argv in (["git", "checkout", "-q", default],
                 ["git", "merge", "--ff-only", branch],
                 ["git", "push", "-q", "origin", default],
                 ["git", "push", "-q", "origin", "--delete", branch]):
        if not _sh(root, argv):
            return 1
    print(f"finish: merged {branch} into {default} and pushed. Remaining by "
          f"hand: remove the worktree if one carried the branch "
          f"(`git worktree remove <path> && git worktree prune`), "
          f"publish/prune finished spec dirs, close the tracking issue with "
          f"the merge commit ref (DoD)")
    return 0


def main() -> int:
    args = [a for a in sys.argv[1:]]
    tests: str | None = None
    if "--tests" in args:
        i = args.index("--tests")
        tests = args[i + 1] if i + 1 < len(args) else None
        del args[i:i + 2]
    tests_passed = "--tests-passed" in args
    do_apply = "--apply" in args
    positional = [a for a in args if not a.startswith("--")]
    root = Path(positional[0] if positional else ROOT).resolve()
    if do_apply:
        return apply(root, tests=tests, tests_passed=tests_passed)
    blockers, tail = check(root)
    if blockers:
        print("finish: BLOCKED:")
        for b in blockers:
            print(f"  - {b}")
        return 1
    print("finish: ready — remaining tail, in order:")
    for i, step in enumerate(tail, 1):
        print(f"  {i}. {step}")
    print("finish: `--apply` executes archive + rebase (+ merge, push, branch "
          "delete once the full suite is asserted via --tests CMD or "
          "--tests-passed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
