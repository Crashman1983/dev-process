#!/usr/bin/env python3
"""The pre-push frame: the one sequence every push runs (`docs/process/testing.md`,
"One test path").

    pre_push.py [remote url]          # git's pre-push hook: the ref lines on stdin

Every installed guard reaches it (`merge_route.py --stdin` hands the push
over); a project with its own hook calls it the same way
(`exec uv run scripts/process/pre_push.py "$@"`). In order:

  1. the merge guard (`merge_route.guard`): route and phase, the ref update,
     the standing block, the ledger — the whole sequence, never a part;
  2. branch updates only (`refs/heads/*` on the remote side, not a deletion):
     tags, report refs and deletions end here;
  3. each pushed commit is this checkout's HEAD (`process_git.pushed_commit_problem`);
  4. the class — `merge` when a branch update lands on an integration
     branch — and the scope — `process-only` when the change touches nothing
     but bookkeeping;
  5. the stamp: the same commit, class and scope passed before → done; the
     same evidence tree (a bookkeeping commit on a green tree) → gates only;
  6. the process gates (`gate_runner.py`, local gates with path triggers);
  7. the tests (`test_select.py run`): one lane hold, certificates honoured;
  8. a stamp, when nothing was skipped and the worktree is clean.

Skipping is the owner's, never an agent's: `PROCESS_SKIP=gates` is the
guard's bypass (logged, and on a push to main the standing block goes with
it, as with `SKIP=process-gates`); `PROCESS_SKIP=tests` keeps the standing
block, is logged, and is refused from a dispatched session. A skip writes no
stamp and no certificate.

Exit: 0 may push, 1 refused, 2 cannot judge (no base, a broken test
configuration, a selector that cannot answer), 75 a lane stayed busy and no
test ran — not a gate failure. Whatever the
exit, the frame stamps that it ran (pre-commit's hooks ask, `merge_route`).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

import certificate  # noqa: E402
import merge_route  # noqa: E402
import testing_config  # noqa: E402
from check_review import BOOKKEEPING, PUSH_TARGETS_ENV, integration_targets  # noqa: E402
from process_git import git_environment, pushed_commit_problem  # noqa: E402

STAMP = "process-push-ok"
STAMPS_KEPT = 400
GATES_TIMEOUT_S = 3600


def _say(message: str) -> None:
    print(f"pre-push: {message}", file=sys.stderr)


def _stamp_path(root: Path) -> Path | None:
    r = subprocess.run(["git", "-C", str(root), "rev-parse", "--git-path", STAMP],
                       capture_output=True, text=True, env=git_environment())
    if r.returncode != 0:
        return None
    p = Path(r.stdout.strip())
    return p if p.is_absolute() else root / p


def _stamps(root: Path) -> set[str]:
    path = _stamp_path(root)
    try:
        return set(path.read_text(encoding="utf-8").splitlines()) if path else set()
    except OSError:
        return set()


def _write_stamps(root: Path, keys: list[str]) -> None:
    path = _stamp_path(root)
    if path is None:
        return
    lines = [k for k in (path.read_text(encoding="utf-8").splitlines() if path.exists() else [])
             if k not in keys] + keys
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text("\n".join(lines[-STAMPS_KEPT:]) + "\n", encoding="utf-8")
        tmp.replace(path)
    except OSError:
        pass  # no stamp only costs the next push its checks


def _owner_only(root: Path, env: dict[str, str], skips: set[str], targets: list[str]) -> str | None:
    """A skip is the owner's emergency exit: refused from a dispatched session
    (or one whose phase cannot be told), else logged."""
    phases, problem = merge_route.session_phases(root, env)
    if phases or problem:
        why = f"phase `{sorted(phases)[0]}`" if phases else problem
        return (f"PROCESS_SKIP={','.join(sorted(skips))} comes from a dispatched session ({why}) — "
                f"skipping checks is the owner's emergency exit, not a route for the agent")
    merge_route.append_ledger(root, "skip", f"PROCESS_SKIP={','.join(sorted(skips))}", targets)
    return None


def _git_out(root: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                       env=git_environment())
    return r.stdout.strip() if r.returncode == 0 else ""


def _changed(root: Path, updates: list) -> set[str]:
    """What the push changes since the fork from the integration branch; with
    no integration ref to fork from, since the remote's side of an update
    (R7). Unjudgeable when neither bounds it."""
    import test_select  # noqa: PLC0415

    try:
        return test_select.changed_paths(root, None)
    except test_select.Unjudgeable:
        for ln in updates:
            base = _git_out(root, "merge-base", "HEAD", ln.remote_sha) if ln.remote_sha.strip("0") else ""
            if base:
                return test_select.changed_paths(root, base)
        raise


def _gates(root: Path, env: dict[str, str], targets: list[str]) -> int:
    """The process gates, launched as every other caller launches them
    (`gate_invoke`: the runner's PEP-723 dependencies resolved), told where
    the push goes — the merge-only checks are hard only on a merge push."""
    from gate_invoke import gate_runner_argv, not_runnable_reason  # noqa: PLC0415

    argv = gate_runner_argv(root)
    if argv is None:
        _say(f"the process gates cannot start — {not_runnable_reason(root)}; the push is refused")
        return 1
    told = " ".join(dict.fromkeys([*env.get(PUSH_TARGETS_ENV, "").split(), *targets]))
    try:
        r = subprocess.run(argv, cwd=root, timeout=GATES_TIMEOUT_S,
                           env={**env, "PYTHONDONTWRITEBYTECODE": "1", PUSH_TARGETS_ENV: told})
    except subprocess.TimeoutExpired:
        _say(f"the process gates did not finish in {GATES_TIMEOUT_S} s — refused")
        return 1
    return 0 if r.returncode == 0 else 1


def _fingerprint(root: Path) -> tuple[str, str | None]:
    return _git_out(root, "rev-parse", "HEAD"), certificate.evidence_tree(root)


def _run(root: Path, lines: list, env: dict[str, str], ran: dict) -> int:
    skips = merge_route.process_skips(env)
    rc = merge_route.guard(root, lines, [], env, merge_route._skipped_gates(env))
    if rc:
        return rc
    updates = [ln for ln in lines if ln.remote_ref.startswith("refs/heads/") and ln.local_sha.strip("0")]
    if not updates:
        return 0  # tags, report refs, deletions: the guard was the check
    for ln in updates:
        problem = pushed_commit_problem(root, ln.local_sha)
        if problem:
            _say(problem)
            return 1
    merge_targets = set(integration_targets(root))
    klass = "merge" if any(ln.remote_ref in merge_targets for ln in updates) else "branch"
    targets = [ln.remote_ref for ln in updates]
    if skips:
        # on main, a gates skip is already the guard's logged bypass
        if klass == "branch" or "tests" in skips:
            refusal = _owner_only(root, env, skips, targets)
            if refusal:
                _say(refusal)
                return 1
        _say(f"WARNING {', '.join(sorted(skips))} skipped by PROCESS_SKIP — logged, no stamp")
        # the owner's skip is the frame's decision about the gates: pre-commit's
        # entry must not run them behind it
        ran["gates"] = "gates" in skips
    try:
        cfg = testing_config.load(root)
    except testing_config.ConfigError as exc:
        _say(f"{exc} — the push is refused until it parses")
        return 2
    import test_select  # noqa: PLC0415

    changed = None
    try:
        changed = _changed(root, updates)
    except test_select.Unjudgeable as exc:
        # a merge push runs its whole suite whatever changed; a branch push
        # whose change git cannot list is no "nothing to test"
        if cfg and cfg["stacks"] and "tests" not in skips and klass == "branch":
            _say(f"cannot select tests: {exc}")
            return 2
    scope = "process-only" if changed and all(p.startswith(BOOKKEEPING) for p in changed) else "code"
    head, tree = _fingerprint(root)
    # the configuration is part of what a stamp proves: an untracked (excluded)
    # testing.local.json changes no tree
    proved = certificate.evidence_hash(json.dumps(cfg, sort_keys=True)) if cfg else "none"
    sha_key = f"sha {head} {klass} {scope} {proved}"
    tree_key = f"tree {tree} {klass} {scope} {proved}" if tree else ""
    stamps = _stamps(root) if not skips else set()
    if head and sha_key in stamps:
        _say(f"{head[:10]} passed this push before ({klass}, {scope}) — nothing to run")
        ran["gates"] = True
        return 0
    tree_hit = bool(tree_key) and tree_key in stamps
    if "gates" not in skips:
        ran["gates"] = True
        if _gates(root, env, [ln.remote_ref for ln in lines]):
            return 1
    testable = bool(cfg) and bool(cfg["stacks"] or (klass == "merge" and cfg["merge_suite"]))
    if tree_hit:
        _say(f"tree {tree[:12]} passed this push before ({klass}, {scope}) — gates only")
    elif testable and scope == "code" and "tests" not in skips:
        try:
            rc = test_select.run(root, cfg, changed or set(), klass, certify=False)
        except test_select.Unjudgeable as exc:
            _say(f"cannot select tests: {exc}")
            return 2
        if rc:
            return rc
    if not skips:
        problem = (certificate.clean_tree_problem(root)
                   or certificate.env_problem(cfg["certificate_env"] if cfg else ())
                   or ("HEAD or the tree moved during the run" if _fingerprint(root) != (head, tree) else None))
        if problem:
            _say(f"no stamp — {problem}")
        else:
            _write_stamps(root, [k for k in (sha_key, tree_key) if k])
    return 0


VERDICTS = {0: "ok", 2: "unjudgeable", 75: "busy"}


def run(root: Path, lines: list, env: dict[str, str]) -> int:
    """The frame for git's ref lines. Stamps that it ran, and its verdict, whatever the exit."""
    ran = {"gates": False}
    rc = 1
    try:
        rc = _run(root, lines, env, ran)
        return rc
    except Exception as exc:  # noqa: BLE001 — a crash is a refusal, never a pass
        _say(f"the frame failed ({type(exc).__name__}: {exc}) — the push is refused")
        return 1
    finally:
        verdict = VERDICTS.get(rc, "red")
        if verdict == "ok" and merge_route.process_skips(env):
            verdict = "skipped"
        merge_route.stamp_guard_run(root, lines, verdict=verdict)
        if ran["gates"]:
            merge_route.stamp_guard_run(root, lines, merge_route.GATES_STAMP_DIR)


def main(argv: list[str]) -> int:
    root_out = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    root = Path(root_out.stdout.strip() or ".")
    try:
        lines = merge_route.parse_ref_lines(sys.stdin.read())
    except ValueError as exc:
        _say(f"{exc} — the push is refused")
        return 1
    return run(root, lines, dict(os.environ))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
