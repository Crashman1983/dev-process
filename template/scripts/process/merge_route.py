#!/usr/bin/env python3
"""merge_route: may this push land on main? — the pre-push hook's guard.

Observed downstream: a review session reset its branch onto main and
published 16 commits past a `block` verdict. The hook knew neither the
session's phase nor the push's route. Both are properties of the PUSH, not
of the tree — so this guard runs as its own pre-push hook (`merge-route`),
independent of the gate runner and of a skipped gate, and it is its own
owner next to `check_review.py` (which reads the verdict).

Checks, only for a push to main/master (any other target: exit 0, silent):

  1. Phase. `plan` and `review` never push to main — not with a route
     marker, not with an override. The phase belongs to the SESSION, not to
     the branch name: the strictest phase of `PROCESS_PHASE` and of every
     LIVE dispatch record that belongs to this session counts (same
     worktree, same branch, or an ancestor in the process tree — a branch
     switch, a detached HEAD and a second worktree do not escape it).
     Records of other sessions do not bar (every running review would stop
     the train), stale ones do not either (a finished review would lock out
     its branch's `finish.py`). When the phase cannot be determined (an
     import error, git not answering, an unreadable directory, a half
     written file, a record without `branch`, `phase` or a liveness anchor —
     none of them is skipped), the push is refused: a guard that stays
     silent on errors is the gap it stands against. The legacy `queue.json`
     (a list) and `issues.json` are no records.
  2. Route. A push to main carries `PROCESS_MERGE_ROUTE` = `train` or
     `finish` (the train and `finish.py --apply` set it for exactly that
     push) — or a named owner override `PROCESS_OWNER_OVERRIDE="<reason>"`.
     The override needs a reason, never comes from a dispatched session (an
     exception the agent writes for itself is no owner decision) and leaves
     exactly one line in `<git-common-dir>/process-owner-overrides.log`.
  3. Bypass. A skipped gate on a push to main (`--bypass NAME`; the
     pre-commit hook derives it from `SKIP=process-gates`) keeps the phase
     bar, drops the marker duty and leaves a ledger line. Like the override,
     it never comes from a dispatched session: the emergency exit is the
     owner's.

The markers are environment variables because the hook learns nothing else
about its caller. They can be forged; what the guard enforces is that the
intent is stated in the call and that the bypasses it sees (`SKIP`,
`PROCESS_OWNER_OVERRIDE`) land in the ledger. Out of its reach: `git push
--no-verify`, a clone without the hooks installed (or without the guard AND
with `SKIP=merge-route`), and a denied phase in a process without a record.

Targets and base come from git's own pre-push lines (`--stdin`: `<local_ref>
<local_sha> <remote_ref> <remote_sha>` per pushed ref), which only the hook
owning git's stdin sees. Under pre-commit that is `pre-push.legacy`, installed
by `install_hooks.py`: pre-commit runs it with the lines before its own hooks
and before its "nothing to push" shortcut (which otherwise runs no hook at all
for a published commit force-pushed onto main). With the lines, each commit
pushed to main also passes check_review's standing-block arm, based on the
remote's SHA. pre-commit's `merge-route` hook (`--hook-check`) refuses a push
to main the guard did not see. Without stdin (positional targets from a
custom hook, or the environment), the targets are the UNION of the arguments,
`PROCESS_PUSH_TARGETS` and `PRE_COMMIT_REMOTE_BRANCH` — a forged variable can
add a target, never hide main. Exit 0 = may push, exit 1 = refused (one
message on stderr: why, and the next step). Pure stdlib plus sibling imports.
"""
from __future__ import annotations

import getpass
import json
import os
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling imports
from check_review import (  # noqa: E402  (one owner for "what is main" and "where does it go")
    INTEGRATION_TARGET_REFS,
    PRE_COMMIT_TARGET_ENV,
)

PHASE_ENV = "PROCESS_PHASE"
ROUTE_ENV = "PROCESS_MERGE_ROUTE"
OVERRIDE_ENV = "PROCESS_OWNER_OVERRIDE"
BARRED_PHASES = ("plan", "review")
# dispatch.PHASES, repeated so that a broken dispatch import cannot widen what
# the environment may claim (test_merge_route pins the two equal)
KNOWN_PHASES = ("plan", "execute", "review")
ROUTES = ("train", "finish")
LEDGER_NAME = "process-owner-overrides.log"
OVERRIDE_KIND = "override"
# pre-commit's own skip switch: `SKIP=<hook id>,…`. Skipping the gate runner on a
# push to main is a bypass this guard sees and logs.
SKIP_ENV = "SKIP"
GATE_HOOK_IDS = ("process-gates",)


class Verdict(NamedTuple):
    ok: bool
    message: str = ""
    # (kind, reason) of a bypass that must be in the ledger; None = nothing to log
    ledger: tuple[str, str] | None = None


def _git(root: Path, *args: str) -> str:
    try:
        result = subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                                text=True, timeout=60, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def pushes_to_integration(targets: list[str]) -> bool:
    return any(t in INTEGRATION_TARGET_REFS for t in targets)


def _ancestor_pids() -> set[int]:
    """The process ids from us up to the root: /proc, else `ps` (macOS)."""
    pids: set[int] = set()
    pid = os.getpid()
    for _ in range(64):
        if pid <= 1 or pid in pids:
            break
        pids.add(pid)
        try:
            stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8", errors="replace")
            pid = int(stat.rsplit(")", 1)[-1].split()[1])
        except (OSError, ValueError, IndexError):
            try:
                ps = subprocess.run(["ps", "-o", "ppid=", "-p", str(pid)], capture_output=True,
                                    text=True, timeout=10, check=False)
            except (OSError, subprocess.TimeoutExpired):
                break
            pid = int(ps.stdout.strip()) if ps.stdout.strip().isdigit() else 0
    return pids


def _same_directory(recorded: object, root: Path) -> bool:
    return bool(recorded) and os.path.realpath(str(recorded)) == os.path.realpath(root)


def _record_defect(path: Path) -> str:
    """Why this file is no valid dispatch record, else "". A record missing a field is
    "unknown", never "dead" — liveness (`dispatch.records`) needs identity and a liveness
    anchor, and without them the session would drop out of the phase check."""
    import dispatch  # noqa: PLC0415  (needed here only; an import error refuses above)

    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "unreadable (truncated?)"
    if isinstance(record, list) and path.name == dispatch.QUEUE_FILE:
        return ""  # an older dispatch's queue, no session record
    if not isinstance(record, dict):
        return "not a JSON object"
    if not (isinstance(record.get("branch"), str) and record["branch"]):
        return "without `branch`"
    if record.get("phase") not in dispatch.PHASES:
        return f"with unknown phase {record.get('phase')!r}"
    pid, pid_start = record.get("pid"), record.get("pid_start")
    # a pid of 0 or below and an empty pid_start read as `gone` in `dispatch.records()` —
    # such an anchor says nothing about the session and counts as missing
    has_anchor = (record.get("remote") is True
                  or (isinstance(record.get("tmux_window"), str) and bool(record["tmux_window"]))
                  or (isinstance(pid, int) and not isinstance(pid, bool) and pid > 0
                      and isinstance(pid_start, str) and bool(pid_start)))
    return "" if has_anchor else "without a liveness anchor (`tmux_window`, `remote` or `pid` + `pid_start`)"


def record_defects(root: Path) -> list[str]:
    """The files in `process-dispatch/` the guard cannot read as a session, with the
    reason. The directory is read through an interface that reports errors
    (`os.scandir`): `Path.glob` swallows an unreadable directory and answers "no
    records" — the same answer as a world without sessions. A missing directory means
    no session; an unreadable one means the phase cannot be told."""
    import dispatch  # noqa: PLC0415

    directory = dispatch.common_dir(root) / dispatch.DISPATCH_DIR
    try:
        with os.scandir(directory) as entries:
            names = sorted(entry.name for entry in entries)
    except FileNotFoundError:
        return []
    except OSError as exc:
        return [f"{dispatch.DISPATCH_DIR}/ ({exc.strerror or type(exc).__name__})"]
    defects = []
    for name in names:
        if not name.endswith(".json") or name == dispatch.ISSUES_FILE:
            continue
        defect = _record_defect(directory / name)
        if defect:
            defects.append(f"{name} ({defect})")
    return defects


def recorded_phases(root: Path) -> tuple[set[str], str]:
    """(phases of this session's live records, problem). A record belongs to this
    session when worktree, branch or process tree match; `unknown` (tmux not reachable)
    and `remote` (another host) count as live. A problem is not "no phase" but "cannot
    tell"."""
    branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
    if not branch:
        return set(), "the branch of this worktree cannot be read (git rev-parse failed)"
    try:
        import dispatch  # noqa: PLC0415  (needed here only)

        defects = record_defects(root)
        if defects:
            return set(), (f"the dispatch record {', '.join(defects)} cannot be read — check or "
                           f"delete the file under <git-common-dir>/{dispatch.DISPATCH_DIR}/, "
                           f"then push")
        ancestors = _ancestor_pids()
        phases: set[str] = set()
        for record in dispatch.records(root):
            # only `gone` is dead; `unknown` (tmux not reachable) and `remote` (the session
            # runs on another host) mean "liveness cannot be seen"
            if not (record.get("alive") or record.get("state") in ("unknown", "remote")):
                continue
            ours = (_same_directory(record.get("worktree"), root)
                    or (branch != "HEAD" and record.get("branch") == branch)
                    or dispatch.session_pid(record) in ancestors)
            if ours:
                phases.add(str(record.get("phase") or ""))
        return phases, ""
    except (ImportError, OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        return set(), f"the dispatch records cannot be read ({type(exc).__name__}: {exc})"


def session_phases(root: Path, env: dict[str, str]) -> tuple[set[str], str]:
    """Every phase this session claims: the environment AND the records — the
    strictest decides, neither hides the other."""
    recorded, problem = recorded_phases(root)
    # compared case-insensitively (`Review` is a review), and a value that names
    # no phase is "cannot tell", never "no phase" — it would otherwise pass as
    # an undispatched session
    declared = env.get(PHASE_ENV, "").strip().lower()
    if declared and declared not in KNOWN_PHASES:
        return recorded, (f"{PHASE_ENV}={env.get(PHASE_ENV, '').strip()!r} names no phase "
                          f"(one of {', '.join(KNOWN_PHASES)}) — unset it or name the phase")
    return recorded | ({declared} if declared else set()), problem


def check(root: Path, targets: list[str], env: dict[str, str], *, bypass: str = "") -> Verdict:
    if not pushes_to_integration(targets):
        return Verdict(True)
    phases, problem = session_phases(root, env)
    barred = sorted(phases & set(BARRED_PHASES))
    if barred:
        return Verdict(False, f"merge_route: a session in phase `{barred[0]}` never pushes to "
                              f"main — neither a route marker nor an override counts here; push "
                              f"your own branch, the merge belongs to the train or `finish.py`. "
                              f"If the session has ended (on another host too), "
                              f"`dispatch.py stop <branch>` clears its record")
    if problem:
        return Verdict(False, f"merge_route: the session's phase cannot be determined — {problem}; "
                              f"without it a review or plan session cannot be ruled out, so the "
                              f"push to main is refused")
    phase = next(iter(sorted(p for p in phases if p)), "")
    if bypass and phase:
        return Verdict(False, f"merge_route: {bypass} comes from a dispatched session (phase "
                              f"`{phase}`) — skipping the gates is the owner's emergency exit, "
                              f"not a route for the agent; the owner sets it in their own run")
    if bypass:
        return Verdict(True, f"merge_route: WARNING push to main with {bypass} — gates skipped, "
                             f"bypass logged ({LEDGER_NAME})", (bypass, ""))
    if env.get(ROUTE_ENV, "") in ROUTES:
        return Verdict(True)
    override = env.get(OVERRIDE_ENV)
    if override is not None:
        reason = " ".join(override.split())
        if not reason:
            return Verdict(False, f"merge_route: {OVERRIDE_ENV} is set but carries no reason — "
                                  f"the override needs a sentence on why the push skips the train")
        if phase:
            return Verdict(False, f"merge_route: {OVERRIDE_ENV} comes from a dispatched session "
                                  f"(phase `{phase}`) — an exception the agent writes for itself "
                                  f"is no owner decision; the owner sets it in their own run")
        return Verdict(True, f"merge_route: WARNING override logged ({LEDGER_NAME}): {reason}",
                       (OVERRIDE_KIND, reason))
    return Verdict(False, f"merge_route: a push to main goes through the merge train "
                          f"(`train.py run --push`) or `finish.py --apply`; both set "
                          f"{ROUTE_ENV}={'|'.join(ROUTES)}. Deliberately past the train: "
                          f"{OVERRIDE_ENV}=\"<reason>\" — the override is logged")


def _ledger_path(root: Path) -> Path:
    return _common_dir(root) / LEDGER_NAME


def append_ledger(root: Path, kind: str, reason: str, targets: list[str]) -> None:
    """One line per bypass: time, user, host, branch, head, kind, reason, targets.
    A single `O_APPEND` write, so parallel pushes never tear each other's lines."""
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    fields = (stamp, getpass.getuser(), socket.gethostname(),
              _git(root, "rev-parse", "--abbrev-ref", "HEAD"), _git(root, "rev-parse", "HEAD"),
              kind, reason, " ".join(targets))
    line = "\t".join(field.replace("\t", " ").replace("\n", " ") for field in fields) + "\n"
    fd = os.open(_ledger_path(root), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(fd, line.encode("utf-8"))
    finally:
        os.close(fd)


def _skipped_gates(env: dict[str, str]) -> str:
    """The gate hook pre-commit was told to skip (`SKIP=process-gates`), as a bypass name."""
    skipped = {part.strip() for part in env.get(SKIP_ENV, "").split(",")}
    hit = next((hook for hook in GATE_HOOK_IDS if hook in skipped), "")
    return f"{SKIP_ENV}={hit}" if hit else ""


class RefLine(NamedTuple):
    """One line git hands a pre-push hook on stdin."""
    local_ref: str
    local_sha: str
    remote_ref: str
    remote_sha: str


def parse_ref_lines(text: str) -> list[RefLine]:
    """git's pre-push stdin: `<local_ref> <local_sha> <remote_ref> <remote_sha>`
    per pushed ref. A line of another shape is an error, never skipped — the
    skipped line could be the one to main."""
    lines = []
    for raw in text.splitlines():
        if not raw.strip():
            continue
        parts = raw.split()
        if len(parts) != 4:
            raise ValueError(f"not a pre-push ref line: {raw!r}")
        lines.append(RefLine(*parts))
    return lines


def push_targets(env: dict[str, str], *sources: list[str]) -> list[str]:
    """check_review.push_targets — the one owner the review gate asks too."""
    from check_review import push_targets as owner  # noqa: PLC0415

    return owner(env, *sources)


def standing_blocks(root: Path, lines: list[RefLine]) -> list[str]:
    """check_review's standing-block arm for every ref line to main: tip = the
    pushed commit, base = what the remote holds (its SHA on the line; all zeros
    = the push creates main and carries every work at the tip)."""
    from check_review import standing_block_findings  # noqa: PLC0415

    findings: list[str] = []
    for line in lines:
        if line.remote_ref not in INTEGRATION_TARGET_REFS or not line.local_sha.strip("0"):
            continue  # another ref, or the deletion of main (the route check owns that)
        if not _git(root, "rev-parse", "--verify", "--quiet", f"{line.local_sha}^{{commit}}"):
            findings.append(f"{line.local_sha} pushed to {line.remote_ref} is no commit of this "
                            f"clone — its records cannot be read, so the push is refused")
            continue
        findings += standing_block_findings(root, line.local_sha, remote_sha=line.remote_sha)
    return findings


# --- did the stdin guard run for this push? ---------------------------------
# The ref lines reach only a hook that owns git's stdin. Under pre-commit that is
# `pre-push.legacy` (install_hooks.py puts this guard there): pre-commit runs it
# with the lines before its own hooks and before its "nothing to push" shortcut.
# pre-commit's `merge-route` hook then asks here whether that happened for this
# push — a guard that is not installed must be noticed, not assumed.
STAMP_DIR = "process-merge-guard"
STAMP_TTL_S = 600


def _common_dir(root: Path) -> Path:
    common = Path(_git(root, "rev-parse", "--git-common-dir") or ".git")
    return common if common.is_absolute() else root / common


def stamp_guard_run(root: Path, lines: list[RefLine]) -> None:
    folder = _common_dir(root) / STAMP_DIR
    try:
        folder.mkdir(exist_ok=True)
        (folder / f"{os.getpid()}-{time.time_ns()}").write_text(
            "".join(" ".join(line) + "\n" for line in lines), encoding="utf-8")
    except OSError:
        pass  # the hook check then refuses a push to main: loud, not silent


def guard_ran(root: Path, env: dict[str, str]) -> bool:
    """True when the stdin guard stamped the ref line pre-commit names
    (`PRE_COMMIT_REMOTE_BRANCH`, `PRE_COMMIT_TO_REF`) in the last minutes; the
    stamp is consumed. Stale stamps are cleared on the way."""
    remote_ref = env.get(PRE_COMMIT_TARGET_ENV, "").strip()
    to_ref = env.get("PRE_COMMIT_TO_REF", "").strip()
    folder = _common_dir(root) / STAMP_DIR
    try:
        stamps = sorted(folder.iterdir())
    except OSError:
        return False
    now = time.time()
    for stamp in stamps:
        try:
            if now - stamp.stat().st_mtime > STAMP_TTL_S:
                stamp.unlink(missing_ok=True)
                continue
            lines = parse_ref_lines(stamp.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if any(line.remote_ref == remote_ref and (not to_ref or line.local_sha == to_ref)
               for line in lines):
            stamp.unlink(missing_ok=True)
            return True
    return False


INSTALL_HINT = "python3 scripts/process/install_hooks.py"


def hook_check(root: Path, env: dict[str, str]) -> int:
    """pre-commit's `merge-route` hook: the stdin guard must have run for this push."""
    if guard_ran(root, env):
        return 0
    targets = push_targets(env)
    if pushes_to_integration(targets):
        print(f"merge_route: the merge guard did not see this push's ref lines (it runs as "
              f"pre-push.legacy under pre-commit) — install it with `{INSTALL_HINT}` "
              f"after `pre-commit install`; a push to main without it is refused",
              file=sys.stderr)
        return 1
    print(f"merge_route: note — the merge guard is not installed in this clone "
          f"(`{INSTALL_HINT}`); pushes to main are refused until it is", file=sys.stderr)
    return 0


def main(argv: list[str]) -> int:
    env = dict(os.environ)
    root = Path(_git(Path.cwd(), "rev-parse", "--show-toplevel") or ".")
    if argv[:1] == ["--hook-check"]:
        return hook_check(root, env)
    bypass = ""
    if argv[:1] == ["--bypass"]:
        bypass, argv = (argv[1] if len(argv) > 1 else ""), argv[2:]
    bypass = bypass or _skipped_gates(env)
    lines: list[RefLine] = []
    from_stdin = argv[:1] == ["--stdin"]
    if from_stdin:
        # the remaining arguments are git's (remote name, url), no refs
        argv = []
        try:
            lines = parse_ref_lines(sys.stdin.read())
        except ValueError as exc:
            print(f"merge_route: {exc} — the push is refused", file=sys.stderr)
            return 1
        stamp_guard_run(root, lines)
    targets = push_targets(env, " ".join(argv).split(), [line.remote_ref for line in lines])
    verdict = check(root, targets, env, bypass=bypass)
    if verdict.message:
        print(verdict.message, file=sys.stderr)
    if not verdict.ok:
        return 1
    # the verdict of the review records travels with the ref lines; a skipped gate
    # (logged above) skips it too — the owner's emergency exit
    if lines and not bypass:
        findings = standing_blocks(root, lines)
        for finding in sorted(set(findings)):
            print(f"review: {finding}", file=sys.stderr)
        if findings:
            return 1
    if verdict.ledger:
        append_ledger(root, *verdict.ledger, targets)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
