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

import os
import re
import subprocess
import sys
from pathlib import Path

# the checker must not dirty the tree it is judging clean: the sibling import
# below would otherwise drop a __pycache__ into scripts/process
sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling import
from process_git import git_environment  # noqa: E402
from check_review import (  # noqa: E402  (one owner for grammar + arithmetic)
    JOURNAL_DIR,
    PLANS_ACTIVE,
    integration_targets,
    PLANS_ARCHIVE,
    SPECS_DIR,
    plan_tier,
    review_waived,
    IN_FLIGHT_UNKNOWN,
    _cleared,
    _plan_issue_numbers,
    _plan_work_ids,
    _unfenced,
    GitReadError,
    branch_issue,
    integration_ref,
    issue_refs_in_range,
    merge_base,
    no_clearing_review,
    paths_in_flight,
    review_passes,
    speckit_unreviewed,
    stale_review,
    verified_template_plan,
    template_review_findings,
)
from gate_invoke import (  # noqa: E402  (one owner for "how to launch")
    gate_runner_argv,
    hook_wiring_findings,
    not_runnable_reason,
)


def _git(*args: str) -> str | None:
    proc = subprocess.run(["git", *args], capture_output=True, text=True,
                          cwd=str(ROOT), env=git_environment())
    return proc.stdout.strip() if proc.returncode == 0 else None


def _branches_to_finish(root: Path, default: str, limit: int = 8) -> str:
    """Where the work to finish is, when finish runs on the integration branch:
    each branch not merged into it — in the worktree that holds it, or to check
    out (observed: finish run from the main checkout while the work sat in a
    dispatched worktree)."""
    out = _git("branch", "--no-merged", default, "--format=%(refname:short)")
    if out is None:
        return f"git cannot list the branches not merged into {default} — check out the branch first"
    unmerged = [b for b in out.splitlines() if b.strip()]
    if not unmerged:
        return f"no branch is left unmerged into {default}"
    try:
        import dispatch as _dispatch  # lazy, as `usage`: a listing never blocks the message
        held = {e["branch"]: e["path"] for e in _dispatch.worktree_entries(root) if e["branch"]}
    except Exception:  # noqa: BLE001
        held = {}
    ways = [f"cd {held[b]} (holds {b})" if b in held else f"git checkout {b}"
            for b in unmerged[:limit]]
    more = f" | … {len(unmerged) - limit} more (git branch --no-merged {default})" \
        if len(unmerged) > limit else ""
    return "check out the branch first: " + " | ".join(ways) + more


def _journal_passes(root: Path) -> list[dict]:
    texts: list[str] = []
    jdir = root / JOURNAL_DIR
    if not jdir.is_dir():
        return []
    for f in sorted(jdir.glob("**/*.md")):
        try:
            texts.append(f.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
    return review_passes(root, texts)


def check(root: Path) -> tuple[list[str], list[str]]:
    """(blockers, tail) — tail is the printable remaining ritual."""
    blockers: list[str] = []
    tail: list[str] = []

    global ROOT
    ROOT = root
    branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    if branch is None:
        return ["not a git repository (or git missing)"], []
    if f"refs/heads/{branch}" in integration_targets(root):
        return [f"on {branch} — there is no feature branch to finish; "
                + _branches_to_finish(root, branch)], []

    dirty = _git("status", "--porcelain")
    if dirty:
        blockers.append(f"worktree not clean ({len(dirty.splitlines())} "
                        f"entr(y/ies)) — commit or stash before finishing")

    # --- clearing pass per active tier-2+ plan (review-gate arithmetic) ---
    passes = _journal_passes(root)
    # the same scope as the review gate's push-anchored arm: a plan is this
    # branch's business when the branch carries its file or claims its issue
    # a base whose diff git cannot list leaves in_flight None: every active
    # plan counts as this branch's (fail closed), and the broken read is named
    # an ambiguous fork point is a blocker, never "no base" (downstream #2381)
    try:
        has_base = merge_base(root) is not None
        base_error = None
    except GitReadError as exc:
        has_base, base_error = False, exc
        blockers.append(f"cannot bound this branch's range: {exc}")
    in_flight = paths_in_flight(root) if has_base else None
    if has_base:
        from template_verify import verify
        try:
            # the ref, not the fork SHA: verify demands one fork point itself
            ref = integration_ref(root)
            if ref is None:
                raise ValueError('the integration ref behind the merge base disappeared')
            update = verify(root, ref)
            blockers.extend(template_review_findings(root, update, passes))
        except (GitReadError, ValueError, OSError, subprocess.TimeoutExpired) as exc:
            blockers.append(f'template verification failed: {exc}')
    if has_base and in_flight is None:
        blockers.append(f"{IN_FLIGHT_UNKNOWN} — every active plan counts as this branch's; "
                        f"repair the clone (`git fsck`, fetch) and run finish again")
    claimed_issues = issue_refs_in_range(root) if base_error is None else set()
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
            tier = plan_tier(text)
            if tier is None:
                continue
            if tier < 2:
                to_archive.append(p.name)
                continue
            if verified_template_plan(root, f"{PLANS_ACTIVE}/{p.name}", text):
                to_archive.append(p.name)
                continue
            if review_waived(text):
                to_archive.append(p.name)
                continue
            ids = _plan_work_ids(p.stem, text, include_dedated=True)
            if _cleared(passes, ids, tier):
                stale = stale_review(root, passes, ids, tier, in_flight or set())
                if stale:
                    blockers.append(f"{PLANS_ACTIVE}/{p.name}: {stale}")
                else:
                    to_archive.append(p.name)
            else:
                blockers.append(no_clearing_review(f"{PLANS_ACTIVE}/{p.name}", tier, ids)
                                + " — run /review before /finish")

    # --- speckit-path plans: same presence question, different home — the
    # spec dir's plan never enters the archive, its completion signal is the
    # fully-ticked tasks.md (the review gate's blind spot; this IS the stop)
    done_spec_dirs: list[str] = []
    sdir = root / SPECS_DIR
    if sdir.is_dir():
        for name, tier, ids in speckit_unreviewed(root, passes):
            blockers.append(no_clearing_review(f"{SPECS_DIR}/{name}", tier, ids)
                            + " — its tasks are all ticked; run /review before /finish")
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
        gr = subprocess.run(argv, cwd=str(root), capture_output=True, text=True, env=git_environment())
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
                    f"commit before merge); attesting the clearing pass with "
                    f"`attest.py … --archive {PLANS_ACTIVE}/{name} --commit` does both in one")
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
                f"auto-delete / `tidy.py --apply`")
    tail.append("git worktree remove <path> && git worktree prune  # if this "
                "branch rode a worktree")
    if (root / "scripts/process/publish_and_prune.py").is_file():
        if done_spec_dirs:
            for name in done_spec_dirs:
                tail.append(f"python3 scripts/process/publish_and_prune.py "
                            f"{SPECS_DIR}/{name}  # publish the outcome, "
                            f"prune the finished working set")
        else:
            tail.append("only if this change ran through a spec (not spec-waived): "
                        "python3 scripts/process/publish_and_prune.py "
                        "<feature-dir>  # publish the outcome, prune the spec "
                        "working set")
    tail.append("close the tracking issue with the merge commit ref (DoD)")
    return [], tail


# The route marker the pre-push guard reads to tell finish's push to main
# from any other (owner of the name: merge_route.py). Set for that one push only.
MERGE_ROUTE_ENV = "PROCESS_MERGE_ROUTE"
MERGE_ROUTE = "finish"


def _sh(root: Path, argv: list[str], env: dict[str, str] | None = None) -> bool:
    """Run one tail command visibly; False on failure (the caller stops)."""
    print(f"finish: $ {' '.join(argv)}")
    # a marker inherited from an enclosing push (gates running under the hook)
    # must not mark a step that never asked for it
    inherited = {k: v for k, v in os.environ.items() if k != MERGE_ROUTE_ENV}
    return subprocess.run(argv, cwd=str(root), env=git_environment({**inherited, **(env or {})})).returncode == 0


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
        # Validate the whole batch before staging the first rename.
        for name in to_archive:
            source, target = root / PLANS_ACTIVE / name, root / PLANS_ARCHIVE / name
            if not source.is_file() or target.exists():
                print(f"finish: cannot archive {name}: source missing or target exists; nothing moved", file=sys.stderr)
                return 1
        (root / PLANS_ARCHIVE).mkdir(parents=True, exist_ok=True)
        moved = []
        for name in to_archive:
            if not _sh(root, ["git", "mv", f"{PLANS_ACTIVE}/{name}", f"{PLANS_ARCHIVE}/{name}"]):
                print(f"finish: cannot archive {name}: git mv failed; rolling back earlier moves", file=sys.stderr)
                for previous in reversed(moved):
                    if not _sh(root, ["git", "mv", f"{PLANS_ARCHIVE}/{previous}", f"{PLANS_ACTIVE}/{previous}"]):
                        print(f"finish: rollback failed for {previous}; restore that plan before retrying", file=sys.stderr)
                return 1
            moved.append(name)
        if not _sh(root, ["git", "commit", "-q", "-m", f"docs: archive plan(s) on merge — {', '.join(to_archive)}"]):
            print(f"finish: archive commit failed for {to_archive}; rolling back moves", file=sys.stderr)
            for name in reversed(moved):
                if not _sh(root, ["git", "mv", f"{PLANS_ARCHIVE}/{name}", f"{PLANS_ACTIVE}/{name}"]):
                    print(f"finish: rollback failed for {name}; restore it before retrying", file=sys.stderr)
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
        if subprocess.run(tests, shell=True, cwd=str(root), env=git_environment()).returncode != 0:
            print("finish: full suite red — not merging")
            return 1
    elif not tests_passed:
        print("finish: applied archive + rebase; stopped before the merge — "
              "run the FULL test suite now, then re-run with "
              "`--apply --tests-passed` (or pass `--tests CMD` to run it here)")
        return 0
    # 4. A worktree must not check out main while another checkout owns it.
    route = {MERGE_ROUTE_ENV: MERGE_ROUTE}
    raw_worktrees = _git("worktree", "list", "--porcelain", "-z") or ""
    integration_checkout = None
    path = None
    for field in raw_worktrees.split("\0"):
        if field.startswith("worktree "):
            path = Path(field.removeprefix("worktree "))
        elif field == f"branch refs/heads/{default}" and path is not None:
            integration_checkout = path
    elsewhere = integration_checkout is not None and integration_checkout.resolve() != root.resolve()
    if elsewhere:
        if _git("merge-base", "--is-ancestor", f"origin/{default}", "HEAD") is None:
            print(f"finish: origin/{default} is not an ancestor of HEAD — rebase onto origin/{default}, re-review and retry", file=sys.stderr)
            return 1
        if not _sh(root, ["git", "push", "-q", "origin", f"HEAD:{default}"], route):
            return 1
        # Keep the other checkout's files and ref together; never move a ref under it.
        other_status = subprocess.run(["git", "-C", str(integration_checkout), "status", "--porcelain"],
                                      capture_output=True, text=True, env=git_environment())
        other_branch = subprocess.run(
            ["git", "-C", str(integration_checkout), "symbolic-ref", "--quiet", "--short", "HEAD"],
            capture_output=True, text=True, env=git_environment())
        if (other_status.returncode == 0 and not other_status.stdout.strip()
                and other_branch.returncode == 0 and other_branch.stdout.strip() == default):
            if not _sh(integration_checkout, ["git", "merge", "--ff-only", f"origin/{default}"]):
                print(f"finish: push succeeded; refresh {integration_checkout} manually", file=sys.stderr)
        else:
            print(f"finish: push succeeded; {integration_checkout} was kept unchanged; refresh it manually")
    else:
        for argv, env in ((["git", "checkout", "-q", default], None),
                          (["git", "merge", "--ff-only", branch], None),
                          (["git", "push", "-q", "origin", default], route)):
            if not _sh(root, argv, env):
                return 1
    _done(root, branch)  # the merge is pushed: whatever fails next, it is done
    remote_branch = _git("ls-remote", "--heads", "origin", f"refs/heads/{branch}")
    if remote_branch:
        if not _sh(root, ["git", "push", "-q", "origin", "--delete", branch]):
            return 1
    else:
        print(f"finish: remote branch {branch} absent or unreadable — no remote delete")
    print(f"finish: merged {branch} into {default} and pushed. Remaining by "
          f"hand: remove the worktree if one carried the branch "
          f"(`git worktree remove <path> && git worktree prune`), "
          f"publish/prune finished spec dirs, close the tracking issue with "
          f"the merge commit ref (DoD)")
    return 0


def _done(root: Path, branch: str) -> None:
    """The worker's `done`, with the usage line as its note. A pushed merge
    never ends in a traceback over bookkeeping."""
    issue, tokens = usage(root, branch)
    print(f"finish: {tokens}")
    try:
        import report as _report
        _report.write_report(root, "done", issue=issue, note=tokens,
                             worker=os.environ.get("PROCESS_WORKER") or branch)
    except (Exception, SystemExit) as exc:  # noqa: BLE001
        print(f"finish: merged, but the `done` report was not written ({exc}) — "
              f"`report.py done --issue N` by hand", file=sys.stderr)


def usage(root: Path, branch: str | None) -> tuple[int | None, str]:
    """(issue, `tokens: …` line) — the issue the branch name leads with; the
    count is dispatch's (`issue_tokens`), `not measured` when it cannot tell."""
    number = branch_issue(branch) if branch else None
    issue = int(number) if number else None
    try:
        import dispatch as _dispatch
        return issue, _dispatch.tokens_line(root, issue)
    except Exception:  # noqa: BLE001 — a usage line never blocks the merge
        return issue, "tokens: not measured"


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
    print(f"finish: {usage(root, _git('rev-parse', '--abbrev-ref', 'HEAD'))[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
