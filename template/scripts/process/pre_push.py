#!/usr/bin/env python3
"""The pre-push frame: the one sequence every push runs (`docs/process/testing.md`,
"One test path").

    pre_push.py [remote url]          # git's pre-push hook: the ref lines on stdin

Every installed guard reaches it (`merge_route.py --stdin` hands the push
over); a project with its own hook calls it the same way
(`exec python3 scripts/process/pre_push.py "$@"`). In order:

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
configuration), 75 a lane stayed busy — not a gate failure. Whatever the
exit, the frame stamps that it ran (pre-commit's hooks ask, `merge_route`).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

import certificate  # noqa: E402
import merge_route  # noqa: E402
import testing_config  # noqa: E402
from check_review import BOOKKEEPING, integration_targets  # noqa: E402
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


def _changed(root: Path):
    import test_select  # noqa: PLC0415

    return test_select.changed_paths(root, None)


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
    try:
        cfg = testing_config.load(root)
    except testing_config.ConfigError as exc:
        _say(f"{exc} — the push is refused until it parses")
        return 2
    import test_select  # noqa: PLC0415

    changed = None
    try:
        changed = _changed(root)
    except test_select.Unjudgeable as exc:
        # a merge push runs its whole suite whatever changed; a branch push
        # whose change git cannot list is no "nothing to test"
        if cfg and cfg["stacks"] and "tests" not in skips and klass == "branch":
            _say(f"cannot select tests: {exc}")
            return 2
    scope = "process-only" if changed is not None and changed and all(
        p.startswith(BOOKKEEPING) for p in changed) else "code"
    head = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True,
                          text=True, env=git_environment()).stdout.strip()
    tree = certificate.evidence_tree(root)
    sha_key, tree_key = f"sha {head} {klass} {scope}", (f"tree {tree} {klass} {scope}" if tree else "")
    stamps = _stamps(root) if not skips else set()
    if head and sha_key in stamps:
        _say(f"{head[:10]} passed this push before ({klass}, {scope}) — nothing to run")
        ran["gates"] = True
        return 0
    tree_hit = bool(tree_key) and tree_key in stamps
    if "gates" not in skips:
        gate_runner = root / "scripts" / "process" / "gate_runner.py"
        if not gate_runner.is_file():
            _say("scripts/process/gate_runner.py is missing — the push is refused")
            return 1
        try:
            r = subprocess.run([sys.executable, str(gate_runner)], cwd=root, timeout=GATES_TIMEOUT_S,
                               env={**env, "PYTHONDONTWRITEBYTECODE": "1"})
        except subprocess.TimeoutExpired:
            _say(f"the process gates did not finish in {GATES_TIMEOUT_S} s — refused")
            return 1
        ran["gates"] = True
        if r.returncode != 0:
            return 1
    if tree_hit:
        _say(f"tree {tree[:12]} passed this push before ({klass}, {scope}) — gates only")
    elif cfg and cfg["stacks"] and scope == "code" and "tests" not in skips:
        rc = test_select.run(root, cfg, changed or set(), klass, certify=False)
        if rc:
            return rc
    if not skips:
        problem = certificate.clean_tree_problem(root)
        if problem:
            _say(f"no stamp — {problem}")
        else:
            _write_stamps(root, [k for k in (sha_key, tree_key) if k])
    return 0


def run(root: Path, lines: list, env: dict[str, str]) -> int:
    """The frame for git's ref lines. Stamps that it ran, whatever the exit."""
    ran = {"gates": False}
    try:
        return _run(root, lines, env, ran)
    except Exception as exc:  # noqa: BLE001 — a crash is a refusal, never a pass
        _say(f"the frame failed ({type(exc).__name__}: {exc}) — the push is refused")
        return 1
    finally:
        merge_route.stamp_guard_run(root, lines)
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
