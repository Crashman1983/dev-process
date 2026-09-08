#!/usr/bin/env python3
"""tidy: the residue the process leaves behind, in one report and one command.

Every stage of the process produces something that is meant to disappear
later — a feature branch after its merge, a spec directory after its
publish, an archived plan after its retention window, a journal shard after
its reasoning went stale. Each has an owner in the docs (`commits.md`
"Merge leaves no residue", `journal-state-plans.md` Retention, the speckit
publish ritual), and each was measured downstream to pile up anyway:
353 of 457 remote branches already merged, 9 of 35 spec directories fully
ticked, active plans a month old that no gate looks at. Residue accrues
where removal depends on remembering; this tool makes it one look and one
command.

Dry run by default: a report with counts and the exact command per item.
`--apply` executes the safe part:
  - delete remote branches whose tip is already contained in the default
    branch (nothing unmerged can be lost; `--keep GLOB` protects patterns)
  - publish and prune spec directories whose tasks.md is fully ticked
    (via publish_and_prune.py, where the speckit module is installed)
  - fold journal shards older than the window (compact_journal.py)
  - remove archived plans older than the retention window (git history
    keeps them; the review gate reads the journal's REVIEW lines, which
    compaction preserves)
  - remove .process-work/template-delta/ (working memory of an update)
Two things it only LISTS, because they are the owner's decision: active
plans older than the window (abandoned, or just slow?) and open issues
untouched for a while (needs `gh`; skipped without it).

Usage: tidy.py [root] [--apply] [--days N] [--keep GLOB ...]
"""
from __future__ import annotations

import datetime as dt
import fnmatch
import re
import shutil
import subprocess
import sys
from pathlib import Path

PLANS_ACTIVE = ".process-work/plans"
PLANS_ARCHIVE = ".process-work/plans/archive"
SPECS = "specs"
DELTA_DIR = ".process-work/template-delta"
DATE_PREFIX = re.compile(r"^(\d{4}-\d{2}-\d{2})")
DEFAULT_KEEP = ("main", "master", "HEAD", "release/*", "gh-pages")


def _git(root: Path, *args: str, timeout: int = 120) -> str | None:
    try:
        r = subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                           text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout if r.returncode == 0 else None


def _default_branch(root: Path) -> str:
    for cand in ("main", "master"):
        if _git(root, "rev-parse", "--verify", "--quiet", f"origin/{cand}") is not None:
            return cand
    return "main"


def _dated(p: Path) -> dt.date | None:
    m = DATE_PREFIX.match(p.name)
    if not m:
        return None
    try:
        return dt.date.fromisoformat(m.group(1))
    except ValueError:
        return None


# --- the items -----------------------------------------------------------------

def merged_remote_branches(root: Path, keep: tuple[str, ...]) -> list[str]:
    """Remote branches whose tip is contained in origin/<default>."""
    default = _default_branch(root)
    _git(root, "fetch", "--prune", "--quiet", "origin", timeout=600)
    out = _git(root, "branch", "-r", "--merged", f"origin/{default}") or ""
    names: list[str] = []
    for line in out.splitlines():
        ref = line.strip()
        if "->" in ref or not ref.startswith("origin/"):
            continue
        name = ref[len("origin/"):]
        if any(fnmatch.fnmatch(name, pat) for pat in keep):
            continue
        names.append(name)
    return names


def finished_spec_dirs(root: Path) -> list[str]:
    out: list[str] = []
    sdir = root / SPECS
    if not sdir.is_dir():
        return out
    for d in sorted(p for p in sdir.iterdir() if p.is_dir()):
        tasks = d / "tasks.md"
        if not tasks.is_file():
            continue
        text = tasks.read_text(encoding="utf-8", errors="replace")
        if not re.search(r"^\s*- \[ \] ", text, re.M) and re.search(r"^\s*- \[[xX]\] ", text, re.M):
            out.append(d.name)
    return out


def stale_active_plans(root: Path, days: int) -> list[str]:
    cutoff = dt.date.today() - dt.timedelta(days=days)
    pdir = root / PLANS_ACTIVE
    if not pdir.is_dir():
        return []
    return [p.name for p in sorted(pdir.glob("*.md"))
            if not p.name.startswith("design-") and (d := _dated(p)) and d < cutoff]


def old_archived_plans(root: Path, days: int) -> list[str]:
    cutoff = dt.date.today() - dt.timedelta(days=days)
    adir = root / PLANS_ARCHIVE
    if not adir.is_dir():
        return []
    return [p.name for p in sorted(adir.glob("*.md")) if (d := _dated(p)) and d < cutoff]


def old_journal_shards(root: Path, days: int) -> int:
    """Count only — compact_journal.py owns the folding."""
    cutoff = dt.date.today() - dt.timedelta(days=days)
    jdir = root / ".process-work/journal"
    if not jdir.is_dir():
        return 0
    n = 0
    for p in jdir.rglob("*.md"):
        if "archive" in p.relative_to(jdir).parts:
            continue
        m = re.search(r"(\d{4}-\d{2}-\d{2})", p.name)
        if not m:
            continue
        try:
            if dt.date.fromisoformat(m.group(1)) < cutoff:
                n += 1
        except ValueError:
            pass
    return n


def quiet_open_issues(root: Path, days: int) -> list[str] | None:
    """Open issues untouched for `days` — needs gh; None when unavailable."""
    gh = shutil.which("gh")
    if not gh:
        return None
    since = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    try:
        r = subprocess.run([gh, "issue", "list", "--state", "open", "--limit", "200",
                            "--search", f"updated:<{since}", "--json", "number,title"],
                           capture_output=True, text=True, timeout=60, cwd=str(root))
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0:
        return None
    import json
    try:
        return [f"#{i['number']} {i['title']}" for i in json.loads(r.stdout)]
    except (json.JSONDecodeError, KeyError, TypeError):
        return None


# --- report and apply -----------------------------------------------------------

def report(root: Path, days: int, keep: tuple[str, ...] = DEFAULT_KEEP,
           *, with_remote: bool = True) -> tuple[list[str], dict]:
    """(lines, items) — the digest section and the raw findings."""
    items: dict = {}
    lines: list[str] = []
    if with_remote and _git(root, "remote", "get-url", "origin"):
        items["branches"] = merged_remote_branches(root, keep)
    else:
        items["branches"] = []
    items["specs"] = finished_spec_dirs(root)
    items["stale_plans"] = stale_active_plans(root, days)
    items["old_archive"] = old_archived_plans(root, days)
    items["journal"] = old_journal_shards(root, days)
    items["delta"] = (root / DELTA_DIR).is_dir()
    items["issues"] = quiet_open_issues(root, days)

    b = items["branches"]
    lines.append(f"- remote branches already merged into the default branch: {len(b)}"
                 + (f" (e.g. {', '.join(b[:3])}{', …' if len(b) > 3 else ''})" if b else "")
                 + (" — `tidy.py --apply` deletes them (nothing unmerged is lost)" if b else ""))
    s = items["specs"]
    lines.append(f"- spec directories fully ticked but not published/pruned: {len(s)}"
                 + (f" ({', '.join(s[:4])}{', …' if len(s) > 4 else ''}) — `tidy.py --apply` "
                    f"runs publish_and_prune per directory" if s else ""))
    p = items["stale_plans"]
    lines.append(f"- active plans older than {days} days: {len(p)}"
                 + (f" ({', '.join(p[:4])}{', …' if len(p) > 4 else ''}) — YOUR call: "
                    f"archive with a review-waived: line, or delete; nothing gates them" if p else ""))
    a = items["old_archive"]
    lines.append(f"- archived plans older than {days} days: {len(a)}"
                 + (" — `tidy.py --apply` removes them (git history keeps them)" if a else ""))
    j = items["journal"]
    lines.append(f"- journal shards older than {days} days: {j}"
                 + (" — `tidy.py --apply` folds them (REVIEW/GRADE lines kept)" if j else ""))
    if items["delta"]:
        lines.append(f"- {DELTA_DIR}/ left over from a template update — `tidy.py --apply` removes it")
    iss = items["issues"]
    if iss is None:
        lines.append(f"- open issues untouched for {days} days: (needs `gh` on PATH — not checked)")
    else:
        lines.append(f"- open issues untouched for {days} days: {len(iss)}"
                     + (f" ({'; '.join(iss[:5])}{'; …' if len(iss) > 5 else ''}) — YOUR call: "
                        f"close with a reason, or re-prioritise" if iss else ""))
    return lines, items


def apply(root: Path, items: dict, days: int) -> int:
    rc = 0
    for name in items["branches"]:
        print(f"tidy: $ git push origin --delete {name}")
        r = subprocess.run(["git", "-C", str(root), "push", "--quiet", "origin",
                            "--delete", name], capture_output=True, text=True)
        if r.returncode != 0:
            print(f"tidy: could not delete {name}: {r.stderr.strip()}")
            rc = 1
    pp = root / "scripts/process/publish_and_prune.py"
    for d in items["specs"]:
        if not pp.is_file():
            print(f"tidy: {SPECS}/{d} is finished but publish_and_prune.py is not installed — "
                  f"prune by hand")
            continue
        print(f"tidy: $ python scripts/process/publish_and_prune.py {d}")
        r = subprocess.run([sys.executable, str(pp), d], cwd=str(root),
                           capture_output=True, text=True)
        print((r.stdout + r.stderr).strip())
        if r.returncode != 0:
            rc = 1
    cj = root / "scripts/process/compact_journal.py"
    if items["journal"] and cj.is_file():
        print(f"tidy: $ python scripts/process/compact_journal.py --weeks {max(1, days // 7)} --apply")
        r = subprocess.run([sys.executable, str(cj), "--weeks", str(max(1, days // 7)),
                            "--apply", "."], cwd=str(root), capture_output=True, text=True)
        print(r.stdout.strip())
        if r.returncode != 0:
            rc = 1
    for name in items["old_archive"]:
        print(f"tidy: $ git rm -q {PLANS_ARCHIVE}/{name}")
        r = subprocess.run(["git", "-C", str(root), "rm", "-q", f"{PLANS_ARCHIVE}/{name}"],
                           capture_output=True, text=True)
        if r.returncode != 0:
            (root / PLANS_ARCHIVE / name).unlink(missing_ok=True)
    if items["delta"]:
        print(f"tidy: rm -r {DELTA_DIR}")
        shutil.rmtree(root / DELTA_DIR, ignore_errors=True)
    print("tidy: done — commit the tree changes as an ordinary change "
          "(\"history is pruned in a commit that says so\")")
    return rc


def main() -> int:
    args = sys.argv[1:]
    days = 30
    keep = list(DEFAULT_KEEP)
    if "--days" in args:
        i = args.index("--days")
        days = int(args[i + 1])
        del args[i:i + 2]
    while "--keep" in args:
        i = args.index("--keep")
        keep.append(args[i + 1])
        del args[i:i + 2]
    do_apply = "--apply" in args
    positional = [a for a in args if not a.startswith("--")]
    root = Path(positional[0] if positional else ".").resolve()
    lines, items = report(root, days, tuple(keep))
    print(f"tidy: residue report (window {days} days)")
    for ln in lines:
        print(ln)
    if not do_apply:
        print("tidy: dry run — re-run with --apply to execute the safe part "
              "(branches, finished specs, journal, old archive, delta dir)")
        return 0
    return apply(root, items, days)


if __name__ == "__main__":
    raise SystemExit(main())
