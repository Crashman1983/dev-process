#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6,<7"]
# ///
"""finish: the merge-tail checker — is this branch actually done?

The failures this exists for are all tail failures observed in production:
a plan merged without its clearing pass, a pass recorded but the plan never
archived, a merge that left branch and worktree behind. `/finish` runs the
tail as ONE readable verdict instead of a ritual scattered over four docs.

Read-only by default: it verifies and then PRINTS the exact remaining
commands. With `--apply` it executes the deterministic part itself
(archive commit, rebase; then merge, push and branch delete only behind the
batch's full suite, `--tests CMD` or `--tests-passed`) — every step prints
its command and the first failure stops in a state git explains. A green
`--tests` that is the project's `merge_suite` (`testing.local.json`) on a
clean tree writes the `merge` certificate, so the push to main runs no suite
again; `--tests` alone runs that `merge_suite`. `--tests-passed` is a claim
and certifies nothing — it is refused while `merge_suite` is set (#255), and
without one the push runs the suite itself.

A repository without any remote (`git remote` prints nothing, #330) merges
locally: no fetch (a local `<default>` ahead of the branch is rebased in), the
gates run with the merge target as the push to main would run them, then the
fast-forward — no push, no route marker, no certificate — and the merged
branch is deleted. `--tests-passed` is refused there: no pre-push runs the
suite behind the claim, so `--tests CMD` runs it. A remote-tracking ref the
gates anchor on is stale there by construction; it blocks until removed, and
one git cannot list blocks too.

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
import shlex
import subprocess
import sys
from pathlib import Path

# the checker must not dirty the tree it is judging clean: the sibling import
# below would otherwise drop a __pycache__ into scripts/process
sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling import
from process_git import git_environment  # noqa: E402
import certificate  # noqa: E402
import testing_config  # noqa: E402
from check_review import (  # noqa: E402  (one owner for grammar + arithmetic)
    JOURNAL_DIR,
    PLANS_ACTIVE,
    PUSH_TARGETS_ENV,
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
    clearing_passes,
    own_family_missing,
    own_family_rule,
    integration_ref,
    issue_refs_in_range,
    merge_base,
    no_clearing_review,
    paths_in_flight,
    review_passes,
    spec_plan_findings,
    speckit_unreviewed,
    stale_review,
    verified_template_plan,
    template_review_findings,
    waiver_owner_findings,
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


def _default_branch() -> str:
    return "main" if _git("rev-parse", "--verify", "--quiet", "main") else "master"


def _local_only() -> bool:
    """The repository has no remote at all (#330): `git remote` prints nothing.
    Not "no origin" — a repository with only `upstream` keeps the push path and
    fails at the push as before — and not "no origin/<default>": a tracking ref
    can outlive its remote. A git failure reads as "has a remote" (fail closed)."""
    return _git("remote") == ""


def _upstream(default: str, local_only: bool) -> str:
    """What the branch rebases onto and is merged into: the local default without a remote."""
    return default if local_only else f"origin/{default}"


def _anchoring_tracking_refs(default: str) -> list[str] | None:
    """The remote-tracking refs the gates anchor on (`check_review._integration_base`:
    `<remote>/main`, `/master`, the default and `/HEAD`). Without a remote each is
    stale by construction, and the gates would judge against it. A left-over
    `old/feature` anchors nothing and is not named. None when git cannot list
    them — unknown, never "none"."""
    names = dict.fromkeys(("main", "master", default, "HEAD"))
    out = _git("for-each-ref", "--format=%(refname)", *(f"refs/remotes/*/{n}" for n in names))
    if out is None:
        return None
    return [ref.removeprefix("refs/remotes/") for ref in out.splitlines() if ref.strip()]


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
    default = _default_branch()
    local_only = _local_only()
    stale_refs = _anchoring_tracking_refs(default) if local_only else []
    if stale_refs is None:
        blockers.append("the repository has no remote, and git could not list remote-tracking "
                        "refs (`git for-each-ref refs/remotes`) — a stale one would anchor the "
                        "gates; repair the ref store (`git fsck`) and run finish again")
    elif stale_refs:
        blockers.append(f"the repository has no remote, but the gates anchor on the stale "
                        f"tracking ref(s) {', '.join(stale_refs)} — remove them: "
                        + " && ".join(f"git branch -r -d {ref}" for ref in stale_refs))

    # --- clearing pass per active tier-2+ plan (review-gate arithmetic) ---
    passes = _journal_passes(root)
    # the same scope as the review gate's push-anchored arm: a plan is this
    # branch's business when the branch carries its file or claims its issue
    # a base whose diff git cannot list leaves in_flight None: every active
    # plan counts as this branch's (fail closed), and the broken read is named
    # an ambiguous fork point is a blocker, never "no base" (downstream #2381)
    try:
        fork = merge_base(root)  # the reviewed base: where the gate and attest read the policy
        has_base = fork is not None
        base_error = None
    except GitReadError as exc:
        fork, has_base, base_error = None, False, exc
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
                # the owner's word is due before the archive, not first at the merge push (#282)
                owed = waiver_owner_findings(f"{PLANS_ACTIVE}/{p.name}", text, tier,
                                             own_family_rule(root, fork)[1])
                if owed:
                    blockers.extend(owed)
                else:
                    to_archive.append(p.name)
                continue
            ids = _plan_work_ids(p.stem, text, include_dedated=True)
            own = clearing_passes(root, passes, tier, fork)  # the gate's answer, at its base (#241)
            if _cleared(own, ids, tier):
                stale = stale_review(root, own, ids, tier, in_flight or set())
                if stale:
                    blockers.append(f"{PLANS_ACTIVE}/{p.name}: {stale}")
                else:
                    to_archive.append(p.name)
            elif _cleared(passes, ids, tier):  # cleared, but only by another model family (#241)
                blockers.append(own_family_missing(f"{PLANS_ACTIVE}/{p.name}", tier,
                                                   own_family_rule(root, fork)[0]))
            else:
                blockers.append(no_clearing_review(f"{PLANS_ACTIVE}/{p.name}", tier, ids)
                                + " — run /review before /finish")

    # --- speckit-path plans: same presence question, different home — the
    # spec dir's plan never enters the archive, its completion signal is the
    # fully-ticked tasks.md (the review gate's blind spot; this IS the stop)
    done_spec_dirs: list[str] = []
    sdir = root / SPECS_DIR
    if sdir.is_dir():
        in_flight_specs = spec_plan_findings(root, passes, in_flight, fork)  # the gate's duty (#266), at its base
        blockers.extend(f"{f}; run /review before /finish" for f in in_flight_specs)
        for name, tier, ids in speckit_unreviewed(root, passes):
            if any(f.startswith(f"{SPECS_DIR}/{name}/") for f in in_flight_specs):
                continue  # already named above
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
    for name in to_archive:
        tail.append(f"git mv {PLANS_ACTIVE}/{name} {PLANS_ARCHIVE}/{name} "
                    f"&& git commit  # archive the plan ON the branch (last "
                    f"commit before merge), after the clearing pass is attested — "
                    f"attest itself moves no plan")
    behind = _git("rev-list", "--count", f"{branch}..{_upstream(default, local_only)}")
    if behind and behind != "0":
        tail.append((f"git rebase {default}" if local_only else
                     f"git fetch origin {default} && git rebase origin/{default}")
                    + f"  # {behind} commit(s) behind — NOTE: a rebase voids "
                    f"review-bundle digests; re-review if a bundle was built")
    tail.append("run the FULL test suite now — the whole batch pays it once "
                "here; scoped runs during the loop were evidence, not the "
                "verdict (docs/process/testing.md, test economy)")
    if local_only:
        tail.append(f"merge: locally, the repository has no remote — `finish.py --apply`, "
                    f"or `git checkout {default} && git merge --ff-only {branch} "
                    f"&& git branch -d {branch}` after the gates ran with the merge target "
                    f"(`{PUSH_TARGETS_ENV}=refs/heads/{default}`)")
    else:
        tail.append(f"merge: PR with linear-history merge, or locally "
                    f"`git checkout {default} && git merge --ff-only {branch} "
                    f"&& git push`")
        tail.append(f"git push origin --delete {branch}  # or let the platform "
                    f"auto-delete / `tidy.py --apply` (retarget a PR stacked on it "
                    f"first — GitHub closes a PR whose base vanishes)")
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
    print(f"finish: $ {' '.join(argv)}", flush=True)  # before the step's own output
    # a marker inherited from an enclosing push (gates running under the hook)
    # must not mark a step that never asked for it
    inherited = {k: v for k, v in os.environ.items() if k != MERGE_ROUTE_ENV}
    return subprocess.run(argv, cwd=str(root), env=git_environment({**inherited, **(env or {})})).returncode == 0


_ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")


def tests_argv(cmd: str) -> tuple[list[str], dict[str, str]] | str:
    """`--tests CMD` as (argv, leading variable assignments) it runs, without
    a shell (#199: consumers' security floors flagged a shell run of argv
    text) — or why it cannot run: unbalanced quotes, no command after the
    assignments (refute: `CI=1` alone ran `env` and merged), or a shell
    operator (`&&`, `|`, `;`, a redirection, a newline) a command without a
    shell would pass on as a word. `#` is no comment here: it is an argument,
    as `shlex.split` reads it. Several stages belong in one make target or
    script (`make test-merge`)."""
    try:
        lex = shlex.shlex(cmd, posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        lex.commenters = ""
        tokens = list(lex)
        argv = shlex.split(cmd)
    except ValueError as exc:
        return f"cannot be read ({exc})"
    operators = [t for t in tokens if t and set(t) <= set("();<>|&")]
    if "\n" in cmd or "\r" in cmd:
        operators.insert(0, "newline")
    if operators:
        return (f"carries the shell operator {operators[0]!r}; it runs without a shell — "
                f"put the stages in one make target or script")
    assigned: dict[str, str] = {}
    while argv and _ASSIGNMENT.match(argv[0]):
        name, _eq, value = argv.pop(0).partition("=")
        assigned[name] = value  # `FOO=1 make test`, as the shell ran it
    if not argv:
        return "names no command"
    return argv, assigned


def _certifiable_tree(root: Path, tests: str) -> tuple[str, str, list[str], list[str] | None] | None:
    """(evidence tree, merge_suite, certificate_env, merge_scope) when a green `--tests`
    run may certify this tree for the merge push: the command is the
    project's `merge_suite` and the worktree is clean. `--tests-passed` is a
    claim, not evidence — it never certifies; the push then runs the suite."""
    try:
        cfg = testing_config.load(root)
    except testing_config.ConfigError:
        return None  # the push names the broken file
    if not cfg or cfg["merge_suite"] != tests.strip():
        return None
    if certificate.clean_tree_problem(root) or certificate.env_problem(cfg["certificate_env"]):
        return None
    tree = certificate.evidence_tree(root)
    return (tree, cfg["merge_suite"], cfg["certificate_env"], cfg["merge_scope"]) if tree else None


def apply(root: Path, *, tests: str | None, tests_passed: bool) -> int:
    """--apply: execute the deterministic part of the tail instead of
    printing it for an agent to retype. Archive commit and rebase always;
    the merge only behind the batch's full suite — run here via --tests
    CMD, or asserted with --tests-passed. Every step prints its command and
    the first failure stops the run: the tree is then in a state git
    explains (a rebase conflict, a rejected push), never half-merged."""
    run_tests = tests_argv(tests) if tests else ([], {})
    if isinstance(run_tests, str):
        # judged before step 1: a command that cannot run leaves no archive commit behind
        print(f"finish: --tests {run_tests} — nothing applied")
        return 1
    blockers, _tail = check(root)
    if blockers:
        print("finish: BLOCKED — nothing applied:")
        for b in blockers:
            print(f"  - {b}")
        return 1
    branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    default = _default_branch()
    local_only = _local_only()
    if local_only and tests_passed and not tests:
        # the claim is checked by the push's pre-push only; a local merge pushes nothing
        print("finish: `--tests-passed` is refused — without a remote no pre-push runs the "
              "suite: pass --tests <command> (nothing applied)")
        return 1
    upstream = _upstream(default, local_only)
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
    # 2. rebase onto the moved integration branch (gates re-run below);
    # without a remote there is nothing to fetch — the local default is the one that moved
    if local_only or _git("rev-parse", "--verify", "--quiet", upstream) is not None:
        if not local_only and not _sh(root, ["git", "fetch", "-q", "origin", default]):
            return 1
        behind = _git("rev-list", "--count", f"{branch}..{upstream}")
        if behind and behind != "0":
            if not _sh(root, ["git", "rebase", "-q", upstream]):
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
        argv, assigned = run_tests
        shown = shlex.join([*(f"{k}={v}" for k, v in assigned.items()), *argv])
        # the certificate serves the pre-push only; a local merge pushes nothing
        before = None if local_only else _certifiable_tree(root, tests)
        certificate.clear_run(root)  # the `stages` file the certificate reads is this run's
        print(f"finish: $ {shown}   # the FULL suite, once per batch")
        try:
            green = subprocess.run(argv, cwd=str(root),
                                   env={**git_environment(), **assigned}).returncode == 0
        except OSError as exc:  # no such command, not executable
            print(f"finish: --tests cannot run ({exc}) — not merging")
            return 1
        if not green:
            print("finish: full suite red — not merging")
            return 1
        if before:
            # a configured scope with no `stages` file is an unknown scope — never recomputed here
            evidence = certificate.run_evidence(root, before[1], before[3])
            if evidence is None:
                ok, why = False, "the scope of the run is unknown"
            else:
                ok, why = certificate.write(root, "merge", evidence, before_tree=before[0],
                                            writer="finish --tests", env_names=before[2])
            print(f"finish: merge certificate {'written — the push runs no suite again' if ok else 'not written — ' + why}")
    elif not tests_passed:
        suite, _broken = _configured_merge_suite(root)
        certifies = "" if local_only else " and writes the merge certificate"
        print("finish: applied archive + rebase; stopped before the merge — "
              + (f"re-run with `--apply --tests` (it runs `{suite}`{certifies})"
                 if suite else "re-run with `--apply --tests CMD` (it runs the FULL test "
                 "suite here; without a remote a claim has no pre-push to check it)"
                 if local_only else "run the FULL test suite now, then re-run with "
                 "`--apply --tests-passed` (or pass `--tests CMD` to run it here)"))
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
    if local_only:
        return _merge_locally(root, branch, default, integration_checkout if elsewhere else None)
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
    print(f"finish: merged {branch} into {default} and pushed. {_BY_HAND}")
    return 0


_BY_HAND = ("Remaining by hand: remove the worktree if one carried the branch "
            "(`git worktree remove <path> && git worktree prune`), publish/prune finished "
            "spec dirs, close the tracking issue with the merge commit ref (DoD)")


def _merge_locally(root: Path, branch: str, default: str, other: Path | None) -> int:
    """The merge of a repository without a remote (#330). Nothing is pushed, so no
    pre-push runs the gates: they run here first, with the merge target, as the
    push to main would run them — red merges nothing. No route marker and no
    certificate: both have the pre-push as their only reader. `other` is the
    checkout that holds `default` when it is not this one: the fast-forward
    happens there, and this branch stays (it is checked out here)."""
    argv = gate_runner_argv(root)
    if argv is None:
        print(f"finish: gate suite NOT RUNNABLE (not red): {not_runnable_reason(root)} — nothing merged")
        return 1
    if not _sh(root, argv, {PUSH_TARGETS_ENV: f"refs/heads/{default}"}):
        print(f"finish: the gates are red for the merge into {default} — nothing merged")
        return 1
    if other is not None:
        if _git("merge-base", "--is-ancestor", default, "HEAD") is None:
            print(f"finish: {default} is not an ancestor of HEAD — rebase onto {default}, "
                  f"re-review and retry", file=sys.stderr)
            return 1
        if not _sh(other, ["git", "merge", "--ff-only", branch]):
            print(f"finish: the fast-forward in {other} failed — nothing merged", file=sys.stderr)
            return 1
        _done(root, branch)
        kept = (f" {branch} stays, it is checked out here — to delete it: "
                f"`cd {other} && git worktree remove {root} && git branch -d {branch}`.")
    else:
        for step in (["git", "checkout", "-q", default], ["git", "merge", "--ff-only", branch]):
            if not _sh(root, step):
                return 1
        _done(root, branch)  # merged is merged: a branch that cannot be deleted changes nothing
        kept = "" if _sh(root, ["git", "branch", "-d", branch]) else (
            f" `git branch -d {branch}` failed — it is checked out in another worktree; "
            f"delete it there.")
    print(f"finish: merged {branch} into {default} locally (the repository has no remote).{kept} {_BY_HAND}")
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


def _configured_merge_suite(root: Path) -> tuple[str | None, str | None]:
    """(the project's `merge_suite` or None, why testing.local.json cannot be read)."""
    try:
        cfg = testing_config.load(root)
    except testing_config.ConfigError as exc:
        return None, str(exc)
    return (cfg or {}).get("merge_suite") or None, None


def main() -> int:
    args = [a for a in sys.argv[1:]]
    tests: str | None = None
    bare_tests = False
    if "--tests" in args:
        i = args.index("--tests")
        value = args[i + 1] if i + 1 < len(args) else None
        if value is not None and not value.strip():
            print("finish: `--tests ''` names no command", file=sys.stderr)
            return 2
        # a path is the root argument, never a test command (`--tests .`); a bare name is a
        # command even where a folder shares it (`--tests make`, refute v2.75 r2)
        if value is None or value.startswith("--") or (
                Path(value).is_dir() and (value in (".", "..") or "/" in value or os.sep in value)):
            bare_tests = True  # `--tests` alone: the project's merge_suite (#255)
            del args[i]
        else:
            tests = value
            del args[i:i + 2]
    tests_passed = "--tests-passed" in args
    do_apply = "--apply" in args
    positional = [a for a in args if not a.startswith("--")]
    root = Path(positional[0] if positional else ROOT).resolve()
    suite, broken = _configured_merge_suite(root)
    if broken and (bare_tests or tests_passed):
        # whether a merge_suite is set cannot be told — the push refuses the file anyway
        print(f"finish: testing.local.json cannot be read — {broken}", file=sys.stderr)
        return 2
    if bare_tests:
        if not suite:
            print("finish: `--tests` without a command needs `merge_suite` in testing.local.json "
                  "— name the command: `--tests CMD`", file=sys.stderr)
            return 2
        tests = suite
    if tests_passed and suite:
        # a claim where evidence is configured: the push would run the suite again anyway
        print(f"finish: `--tests-passed` certifies nothing while `merge_suite` is set — run "
              f"`--apply --tests` (it runs `{suite}` and writes the merge certificate)", file=sys.stderr)
        return 2
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
    if _local_only():
        print("finish: `--apply` executes archive + rebase (+ local merge and branch delete "
              "once --tests CMD ran the full suite; without a remote --tests-passed is refused)")
    else:
        print("finish: `--apply` executes archive + rebase (+ merge, push, branch delete once "
              "the full suite is asserted via --tests CMD or --tests-passed)")
    print(f"finish: {usage(root, _git('rev-parse', '--abbrev-ref', 'HEAD'))[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
