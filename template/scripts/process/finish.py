#!/usr/bin/env python3
"""finish: the merge-tail checker — is this branch actually done?

The failures this exists for are all tail failures observed in production:
a plan merged without its clearing pass, a pass recorded but the plan never
archived, a merge that left branch and worktree behind. `/finish` runs the
tail as ONE readable verdict instead of a ritual scattered over four docs.

Read-only by design: it verifies and then PRINTS the exact remaining
commands — it never merges, archives, or deletes anything itself. The agent
(or human) executes; the checker cannot wreck a tree.

Checks, in order:
  1. on a feature branch (finishing main is meaningless)
  2. worktree clean (an unfinished tree cannot be finished)
  3. every active tier-2+ plan has its clearing REVIEW pass (verdict=pass,
     matching work id, tier>=plan tier) or a review-waived line — the exact
     arithmetic of the review gate, imported from check_review (one owner)
  4. the gate suite is green (gate_runner)
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
    _plan_work_ids,
    _unfenced,
    parse_review_lines,
    speckit_unreviewed,
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
    to_archive: list[str] = []
    pdir = root / PLANS_ACTIVE
    if pdir.is_dir():
        for p in sorted(pdir.glob("*.md")):
            if p.name.startswith("design-") or not p.is_file():
                continue
            text = _unfenced(p.read_text(encoding="utf-8", errors="replace"))
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
            cleared = any(r["work"] in ids and int(r["tier"]) >= tier
                          for r in passes)
            if cleared:
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

    # --- gates ---
    gr = subprocess.run([sys.executable, "scripts/process/gate_runner.py"],
                        cwd=str(ROOT), capture_output=True, text=True)
    if gr.returncode != 0:
        last = [ln for ln in gr.stdout.splitlines() if ln.strip()][-3:]
        blockers.append("gate suite red: " + " | ".join(last))

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


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT).resolve()
    blockers, tail = check(root)
    if blockers:
        print("finish: BLOCKED:")
        for b in blockers:
            print(f"  - {b}")
        return 1
    print("finish: ready — remaining tail, in order:")
    for i, step in enumerate(tail, 1):
        print(f"  {i}. {step}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
