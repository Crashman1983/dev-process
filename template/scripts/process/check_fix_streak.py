#!/usr/bin/env python3
"""check_fix_streak — the mechanical arm of mandatory rule 6 (root cause
before symptom): the third `fix` commit on the same file in a branch asks the
structural question before the next patch is stacked.

The rule stood as a convention and did not fire on its own: downstream, one
branch collected six fix commits on the same owner before anyone asked
whether the design was wrong. This gate counts conventional `fix:`/`fix(…)`
commits per touched file on the current branch against the integration
branch and prints a note from three on. Note-only (exit 0 always): it makes
the pattern visible, it does not block. A no-op on the integration branch and
in clones without a merge base.

Usage: check_fix_streak.py [root]      Stdlib only.
"""
from __future__ import annotations

import subprocess
import sys
from collections import defaultdict
from pathlib import Path

THRESHOLD = 3
INTEGRATION = ("main", "master")
BASES = ("origin/main", "main", "origin/master", "master")


def _git(root: Path, *args: str) -> str | None:
    proc = subprocess.run(["git", "-C", str(root), *args], capture_output=True)
    # surrogateescape, as check_review._names reads names: a non-UTF-8 name
    # stays one name instead of a replacement-character guess
    return proc.stdout.decode(errors="surrogateescape") if proc.returncode == 0 else None


def fix_streaks(log: str, threshold: int = THRESHOLD) -> dict[str, int]:
    """file -> number of fix commits touching it, only entries >= threshold.
    `log` is `git log -z --pretty=%x01%s --name-only` output: NUL-separated
    fields, a subject marked with \x01, the first name after it led by the
    newline git puts between header and names. `-z`: without it git quotes a
    non-ASCII name, and the same file under a quoted and a plain name counted
    as two (downstream refutation)."""
    counts: defaultdict[str, int] = defaultdict(int)
    is_fix = False
    seen: set[str] = set()
    after_subject = False
    for field in log.split("\0"):
        if field.startswith("\x01"):
            subject = field[1:]
            # the conventional prefix, not any "fix…": `fixup!` and `fixture:`
            # are not behaviour fixes
            is_fix = subject.startswith(("fix:", "fix("))
            seen = set()
            after_subject = True
            continue
        path = field[1:] if after_subject and field.startswith("\n") else field
        after_subject = False
        if not is_fix or not path or path in seen:
            continue
        # process bookkeeping (journal, plans) rides along with fixes but owns
        # no behaviour — noise for this rule
        if path.startswith(".process-work/"):
            continue
        seen.add(path)
        counts[path] += 1
    return {p: n for p, n in counts.items() if n >= threshold}


def main(argv: list[str]) -> int:
    root = Path(argv[0] if argv else ".").resolve()
    branch = (_git(root, "rev-parse", "--abbrev-ref", "HEAD") or "").strip()
    if branch in ("", "HEAD", *INTEGRATION):
        return 0
    base = ""
    # origin first: a local main lags in work clones and would count merged history
    for ref in BASES:
        base = (_git(root, "merge-base", ref, "HEAD") or "").strip()
        if base:
            break
    if not base:
        return 0
    log = _git(root, "log", "-z", "--no-merges", "--pretty=%x01%s", "--name-only", f"{base}..HEAD")
    if log is None:
        return 0
    streaks = fix_streaks(log)
    for path, n in sorted(streaks.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"fix-streak: note: {n} fix commits on {path} in this branch — mandatory rule 6: "
              f"find the root cause (or record the structural decision) before the next patch")
    if not streaks:
        print("fix-streak: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
