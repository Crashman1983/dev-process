#!/usr/bin/env python3
"""Tree certificates: evidence paid once, read by every later check of the
same tree (`docs/process/testing.md`, "Pay once, transfer").

A certificate says: on this tree, this evidence ran green. Two kinds:
`push` (the selected tests of a branch, `test_select.py run --certify`) and
`merge` (the train's full suite, or `finish.py --tests` with the configured
`merge_suite`). A branch push accepts either; a merge push only `merge`.

Key: the evidence tree — HEAD's tree without the bookkeeping paths
(`.process-work/`), so an attest or journal commit on a green tree keeps its
certificate — plus a hash of what ran (the suite command, the stack
configuration). Stored in `<git-common-dir>/process-certificates/<kind>/`:
every worktree of a clone sees it, the train's included; another clone pays
its own.

Written only when the run proves something about the tree: clean before and
after (no tracked change, no untracked file git does not ignore — a stray
`conftest.py` would otherwise steer what ran), the tree unchanged, and no
variable from the environment that changes the command (`MAKEFLAGS` with an
assignment overrides a Makefile's `:=` pins; the project lists its own in
`certificate_env`). Threat model as downstream #2474: accidents, not an
attacker — whoever can write the common dir can push code. Known limit: an
ignored file (also via `.git/info/exclude`) is invisible to `git status`.
Every hit is printed with who wrote the certificate, when, and for what.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_review import BOOKKEEPING  # noqa: E402  (one owner of the bookkeeping paths)
from process_git import git_environment  # noqa: E402

KINDS = ("push", "merge")
KEPT = 200
STORE = "process-certificates"


def _git(root: Path, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["git", "-C", str(root), "--no-optional-locks", *args],
                              capture_output=True, timeout=120, env=env or git_environment())
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(args, 127, b"", str(exc).encode())


MERGE_SCOPE_TIMEOUT_S = 60
RUN_STAGES = ("merge-suite", "stages")  # in the git dir: the stages the merge suite ran (testing.md)


def run_stages(root: Path) -> list[str] | None:
    """The stages the last merge-suite run in `root` ran — the `stages` file its
    Makefile wrote — or None when it cannot be read. The one reader: the train's
    stage times and the certificate's scope both ask here, so what ran is one fact."""
    r = _git(root, "rev-parse", "--absolute-git-dir")
    if r.returncode != 0:
        return None
    try:
        return (Path(r.stdout.decode().strip()).joinpath(*RUN_STAGES)).read_text(encoding="utf-8").split()
    except (OSError, ValueError):  # not there, or not text: unknown
        return None


def clear_run(root: Path) -> None:
    """Removes what an earlier merge-suite run in `root` left — the `stages` file and
    the `<stage>.time` markers — before a writer starts the suite, so the `stages` file
    `run_evidence` trusts is this run's: a leftover wider one would otherwise certify a
    narrower run (plan review). Nothing there: nothing to do."""
    r = _git(root, "rev-parse", "--absolute-git-dir")
    if r.returncode != 0:
        return
    folder = Path(r.stdout.decode().strip()).joinpath(*RUN_STAGES[:-1])
    for f in [folder / RUN_STAGES[-1], *folder.glob("*.time")]:
        with contextlib.suppress(OSError):
            f.unlink()


def merge_evidence(root: Path, suite: str, scope_argv: list[str] | None, *,
                   ran_stages: list[str] | None = None) -> str | None:
    """What a `merge` certificate must have run: the suite command, plus — when the
    project configures `merge_scope` — the stages that were selected for it. A narrower
    run is thereby a different evidence string and never satisfies a fuller one.

    The one owner: the writers (`train.py`, `finish.py`) pass `ran_stages`, read from the
    run itself; a reader (the hook) passes none and gets the scope its own selector
    would choose now. None means "scope unknown" — no certificate is written and none
    is looked up, so two sides that both failed to find out can never agree on it."""
    suite = suite.strip()
    if not scope_argv:
        return suite
    if ran_stages is None:
        try:
            done = subprocess.run(scope_argv, cwd=str(root), capture_output=True, text=True,
                                  timeout=MERGE_SCOPE_TIMEOUT_S, env=git_environment())
        except (OSError, ValueError, subprocess.TimeoutExpired):  # ValueError: output not UTF-8
            return None
        if done.returncode != 0:
            return None
        ran_stages = done.stdout.split()
    scope = " ".join(sorted(set(ran_stages)))
    return f"{suite}\nscope={scope}" if scope else None


def run_evidence(root: Path, suite: str, scope_argv: list[str] | None) -> str | None:
    """The evidence a writer certifies: the suite plus the scope the run itself wrote
    (`run_stages`). With `merge_scope` configured and no `stages` file the scope is
    unknown — None, never recomputed (downstream: a recomputed scope
    certified a run the selector had narrowed after it ran). Readers keep `merge_evidence`."""
    ran = run_stages(root)
    if scope_argv and ran is None:
        return None
    return merge_evidence(root, suite, scope_argv, ran_stages=ran)


def evidence_hash(evidence: str) -> str:
    """16 hex digits naming what ran — the train's suite memo uses the same."""
    return hashlib.sha256(evidence.encode("utf-8", "surrogateescape")).hexdigest()[:16]


def evidence_tree(root: Path) -> str | None:
    """HEAD's tree without the bookkeeping paths; None when git cannot tell."""
    with tempfile.TemporaryDirectory() as tmp:
        env = {**git_environment(), "GIT_INDEX_FILE": str(Path(tmp) / "index")}
        if _git(root, "read-tree", "HEAD", env=env).returncode != 0:
            return None
        if _git(root, "rm", "-r", "-q", "--cached", "--ignore-unmatch", "--", BOOKKEEPING,
                env=env).returncode != 0:
            return None
        r = _git(root, "write-tree", env=env)
    out = r.stdout.decode().strip()
    return out if r.returncode == 0 and out else None


def clean_tree_problem(root: Path) -> str | None:
    """Why the worktree is no clean image of HEAD, or None. `git status`
    failing is a problem too — an unread status is no clean one."""
    r = _git(root, "status", "--porcelain", "-z", "--untracked-files=normal")
    if r.returncode != 0:
        return f"git status failed: {r.stderr.decode(errors='replace').strip() or r.returncode}"
    entries = [e for e in r.stdout.decode("utf-8", "surrogateescape").split("\0") if e]
    if entries:
        shown = ", ".join(e[3:] for e in entries[:3]) + (", …" if len(entries) > 3 else "")
        return f"the worktree is not clean ({shown})"
    return None


def env_problem(names: list[str] | tuple[str, ...] = ()) -> str | None:
    """Why the environment may have changed what ran, or None."""
    flags = os.environ.get("MAKEFLAGS", "")
    if any("=" in word and not word.startswith("-") for word in flags.split()):
        return "MAKEFLAGS carries a variable assignment — it overrides the Makefile's pins"
    for name in names:
        if os.environ.get(name):
            return f"{name} is set — it changes what the tests run"
    return None


def _store(root: Path, kind: str) -> Path | None:
    if kind not in KINDS:
        raise ValueError(f"no certificate kind {kind!r}")
    r = _git(root, "rev-parse", "--git-common-dir")
    if r.returncode != 0:
        return None
    common = Path(r.stdout.decode().strip())
    common = common if common.is_absolute() else root / common
    return common / STORE / kind


def find(root: Path, kinds: tuple[str, ...], evidence: dict[str, str], tree: str | None = None) -> dict | None:
    """The first certificate of `kinds` for the evidence tree, as its record
    (kind, writer, time, evidence); None when there is none or git cannot tell.
    `evidence` maps each kind to what it must have run."""
    tree = tree or evidence_tree(root)
    if not tree:
        return None
    for kind in kinds:
        store = _store(root, kind)
        if store is None or kind not in evidence:
            continue
        path = store / f"{tree}-{evidence_hash(evidence[kind])}"
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(record, dict) and record.get("tree") == tree:
            return {**record, "kind": kind}
    return None


def describe(record: dict) -> str:
    when = time.strftime("%Y-%m-%d %H:%M", time.localtime(float(record.get("time") or 0)))
    return (f"{record.get('kind')} certificate of tree {str(record.get('tree'))[:12]} "
            f"(by {record.get('writer') or '?'}, {when}: {record.get('evidence') or '?'})")


def write(root: Path, kind: str, evidence: str, *, before_tree: str | None, writer: str,
          env_names: list[str] | tuple[str, ...] = ()) -> tuple[bool, str]:
    """Certify the evidence tree for `evidence` when the run proved it:
    (True, path) or (False, why not). `before_tree` is the evidence tree the
    caller saw before its run, with a clean worktree."""
    tree = evidence_tree(root)
    if not tree or not before_tree:
        return False, "git cannot name the tree"
    if tree != before_tree:
        return False, f"the tree changed during the run ({before_tree[:12]} → {tree[:12]})"
    problem = clean_tree_problem(root) or env_problem(env_names)
    if problem:
        return False, problem
    store = _store(root, kind)
    if store is None:
        return False, "git cannot name the common dir"
    try:
        store.mkdir(parents=True, exist_ok=True)
        path = store / f"{tree}-{evidence_hash(evidence)}"
        tmp = store / f".{path.name}.{os.getpid()}.tmp"
        tmp.write_text(json.dumps({"tree": tree, "writer": writer, "time": time.time(),
                                   "evidence": evidence, "head": _git(root, "rev-parse", "HEAD")
                                   .stdout.decode().strip()}), encoding="utf-8")
        os.replace(tmp, path)
        _rotate(store)
    except OSError as exc:
        return False, f"cannot write the certificate: {exc}"
    return True, str(path)


def _rotate(store: Path) -> None:
    """The newest KEPT stay; a concurrent rotation removing the same file is fine."""
    files = []
    for p in store.iterdir():
        if p.name.startswith("."):
            continue
        with contextlib.suppress(OSError):
            files.append((p.stat().st_mtime, p))
    for _mtime, p in sorted(files, reverse=True)[KEPT:]:
        with contextlib.suppress(OSError):
            p.unlink()
