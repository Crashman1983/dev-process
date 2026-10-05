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
  - remove review reports of closed work older than the window — the rule
    is `old_review_reports` (newest per work, open work, campaign reports,
    reports a record names and evidence directories stay)
  - remove .process-work/template-delta/ (working memory of an update)
  - remove the worktrees of branches contained in origin/<default> (each
    carries its own venv/node_modules) — only where dispatch.py says so: no
    uncommitted change, no untracked file git does not ignore, no ignored
    file but regenerable environments and caches, no worktree nested inside,
    commits of its own on the branch, no live dispatch session, not locked,
    not the main or current worktree; the report names each one kept and why
Two things it only LISTS, because they are the owner's decision: active
plans older than the window (abandoned, or just slow?) and open issues
untouched for a while (needs `gh`; skipped without it).

Usage: tidy.py [root] [--apply] [--days N] [--keep GLOB ...]
"""
from __future__ import annotations

import datetime as dt
import fnmatch
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling imports

PLANS_ACTIVE = ".process-work/plans"
PLANS_ARCHIVE = ".process-work/plans/archive"
SPECS = "specs"
DELTA_DIR = ".process-work/template-delta"
DATE_PREFIX = re.compile(r"^(\d{4}-\d{2}-\d{2})")
SIZE_CAP = 200_000  # directory entries counted per worktree before the size reads "≥"
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


def worktree_base(root: Path) -> str:
    default = _default_branch(root)
    return f"origin/{default}" if _git(root, "rev-parse", "--verify", "--quiet", f"origin/{default}") else default


def merged_worktrees(root: Path) -> list[tuple[dict, str | None]]:
    """(worktree, keep reason or None) per worktree whose branch is contained in
    origin/<default> (local <default> without origin) — dispatch.py owns the verdict."""
    base = worktree_base(root)
    try:
        import dispatch as _dispatch  # noqa: E402  (sibling; one owner for the worktrees)
    except ImportError:
        return []
    return _dispatch.merged_worktrees(root, base)


def tree_size(path: Path, cap: int = SIZE_CAP) -> tuple[int, bool]:
    """(bytes, complete) under `path`, symlinks not followed; stops after `cap` entries."""
    total, seen, stack = 0, 0, [str(path)]
    while stack:
        try:
            with os.scandir(stack.pop()) as it:
                for e in it:
                    seen += 1
                    if seen > cap:
                        return total, False
                    try:
                        if e.is_dir(follow_symlinks=False):
                            stack.append(e.path)
                        else:
                            total += e.stat(follow_symlinks=False).st_size
                    except OSError:
                        continue
        except OSError:
            continue
    return total, True


def _human(n: float) -> str:
    for unit in ("B", "KiB", "MiB"):
        if n < 1024:
            return f"{n:.0f} B" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GiB"


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


def spec_blocker(root: Path, name: str) -> str | None:
    """Why publish_and_prune would refuse this finished directory — None when
    it would accept it. The same preconditions, asked before `--apply`: a
    "safe" bucket that the pruner then refuses lists the same residue forever
    (observed downstream: 8 of 9 selected directories had no plan.md)."""
    d = root / SPECS / name
    missing = [f for f in ("plan.md", "spec.md") if not (d / f).is_file()]
    if missing:
        return "no " + " and no ".join(missing)
    pp = root / "scripts/process/publish_and_prune.py"
    if not pp.is_file():
        return None
    import importlib.util
    spec = importlib.util.spec_from_file_location("_tidy_publish_and_prune", pp)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except (Exception, SystemExit):  # noqa: BLE001 — a broken pruner is its own finding at --apply
        return None
    try:
        plan_text = (d / "plan.md").read_text(encoding="utf-8", errors="replace")
        spec_text = (d / "spec.md").read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return f"plan.md/spec.md unreadable ({exc.strerror or exc})"
    try:
        issue = mod._issue_number(plan_text)
        unaccounted = mod._unaccounted_scs(spec_text, plan_text)
    except (Exception, SystemExit):  # noqa: BLE001 — a pruner without these helpers is its own finding at --apply
        return None
    if not issue:
        return "plan.md has no issue: ref"
    if unaccounted:
        return "unaccounted Success Criteria " + ", ".join(unaccounted)
    return None


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


_CAMPAIGN = re.compile(r"^\s*(?:[-*+]\s+)?[*_]*campaign[*_]*\s*:", re.IGNORECASE | re.MULTILINE)


def _report_date(root: Path, rel: str) -> dt.date | None:
    """The date in the report's name, else its last commit's date; None: keep."""
    d = _dated(Path(rel))
    if d:
        return d
    out = (_git(root, "log", "-1", "--format=%cs", "--", rel) or "").strip()
    try:
        return dt.date.fromisoformat(out) if out else None
    except ValueError:
        return None


def old_review_reports(root: Path, days: int) -> list[str]:
    """Top-level review reports that are residue — the one owner of that rule.

    Decided per report, through `check_review.report_of` (the rule the
    review bundle uses to find a work's prior report): it goes only when
    EVERY way of reaching it leads to closed work and ALL hold: older than
    `days`; no `campaign:` header; reached by a journal work whose latest
    REVIEW verdict is pass, which no active plan names (in its REVIEW lines
    or text), and of which it is not the newest report; reached by no
    active plan or `specs/*/plan.md` (`check_review.plan_report_keys`); and
    no plan, archived plan or journal shard names its file. Evidence
    directories (`reviews/<slug>/`) are never candidates. Anything unknown
    keeps it. `unremovable` then keeps what git could not give back."""
    rdir = root / _review_mod().REVIEW_REPORTS
    if not rdir.is_dir():
        return []
    cr = _review_mod()
    cutoff = dt.date.today() - dt.timedelta(days=days)
    reports: list[tuple[str, str]] = []
    for f in sorted(p for p in rdir.glob("*.md") if p.is_file()):
        try:
            reports.append((f"{cr.REVIEW_REPORTS}/{f.name}", f.read_text(encoding="utf-8", errors="replace")))
        except OSError:
            continue
    if not reports:
        return []
    journal = cr.record_texts(root, ("journal",)) or []
    plans = cr.record_texts(root, cr.PLAN_KINDS) or []
    archive = cr.record_texts(root, ("plan-archive",)) or []
    records = [fields for _rel, text in journal for _n, fields in cr.parse_review_lines(text)[0]]
    standing = cr.latest_verdicts(records)

    def reached(slugs, issues) -> list[str]:
        """Every report `report_of` reaches by these keys, newest first."""
        remaining, members = list(reports), []
        while (hit := cr.report_of(remaining, slugs, issues)) is not None:
            members.append(hit[0])
            remaining.remove(hit)
        return members

    # decided per report: kept when ANY way of reaching it is open work
    keep: set[str] = set()
    open_works: set[str] = set()
    plan_text = "\n".join(text for _rel, text in plans)
    for rel, text in plans:  # an active plan reaches its reports by the bundle's keys
        keep.update(reached(*cr.plan_report_keys(rel, text)))
        open_works.update(fields["work"] for _n, fields in cr.parse_review_lines(text)[0])
    drop: set[str] = set()
    for work, fields in standing.items():
        slugs, issues = cr.work_keys([work])
        members = reached(slugs, issues)
        if not members:
            continue
        keep.add(members[0])  # the newest of this work: the next delta reads it
        named_in_plan = re.search(rf"(?<![\w#/.-]){re.escape(work)}(?![\w-])", plan_text)
        closed = fields["verdict"] == "pass" and work not in open_works and not named_in_plan
        (drop if closed else keep).update(members[1:])
    named = "\n".join(text for _rel, text in journal + plans + archive)
    out: list[str] = []
    for rel, text in reports:
        name = rel.rsplit("/", 1)[-1]
        if rel not in drop or rel in keep or _CAMPAIGN.search(text) or name in named:
            continue
        d = _report_date(root, rel)
        if d is not None and d < cutoff:
            out.append(rel)
    return out


def unremovable(root: Path, rels: list[str]) -> dict[str, str]:
    """Why each of `rels` must not be removed — untracked, or changed against
    HEAD: deleting it would destroy what git cannot give back."""
    out: dict[str, str] = {}
    for rel in rels:
        if _git(root, "ls-files", "--error-unmatch", "--", rel) is None:
            out[rel] = "not tracked by git"
        elif subprocess.run(["git", "-C", str(root), "diff", "--quiet", "HEAD", "--", rel],
                            capture_output=True).returncode != 0:
            out[rel] = "changed against HEAD"
    return out


def review_sizes(root: Path, rels: list[str]) -> tuple[int, int, int]:
    """(bytes of `rels`, markdown bytes under the reviews folder, other bytes —
    evidence images and the like, which tidy never removes)."""
    rdir = root / _review_mod().REVIEW_REPORTS
    gone = sum((root / r).stat().st_size for r in rels if (root / r).is_file())
    md = other = 0
    if rdir.is_dir():
        for f in rdir.rglob("*"):
            if f.is_file() and not f.is_symlink():
                if f.suffix == ".md":
                    md += f.stat().st_size
                else:
                    other += f.stat().st_size
    return gone, md, other


def _review_mod():
    import check_review  # noqa: E402  (sibling; one owner for reports and REVIEW lines)
    return check_review


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
           *, with_remote: bool = True, sizes: bool | None = None) -> tuple[list[str], dict]:
    """(lines, items) — the digest section and the raw findings. `sizes` (default:
    `with_remote`) walks each merged worktree for its size — the offline digest skips it."""
    items: dict = {}
    lines: list[str] = []
    if with_remote and _git(root, "remote", "get-url", "origin"):
        items["branches"] = merged_remote_branches(root, keep)
    else:
        items["branches"] = []
    finished = finished_spec_dirs(root)
    blockers = {d: spec_blocker(root, d) for d in finished}
    items["specs"] = [d for d in finished if blockers[d] is None]
    items["specs_blocked"] = {d: why for d, why in blockers.items() if why}
    items["stale_plans"] = stale_active_plans(root, days)
    items["old_archive"] = old_archived_plans(root, days)
    items["journal"] = old_journal_shards(root, days)
    old_reports = old_review_reports(root, days)
    items["reviews_skipped"] = unremovable(root, old_reports)
    items["reviews"] = [r for r in old_reports if r not in items["reviews_skipped"]]
    items["delta"] = (root / DELTA_DIR).is_dir()
    items["issues"] = quiet_open_issues(root, days)
    wts = merged_worktrees(root)
    items["worktrees"] = [wt["path"] for wt, why in wts if why is None]
    items["worktrees_kept"] = {str(wt["path"]): why for wt, why in wts if why}

    b = items["branches"]
    lines.append(f"- remote branches already merged into the default branch: {len(b)}"
                 + (f" (e.g. {', '.join(b[:3])}{', …' if len(b) > 3 else ''})" if b else "")
                 + (" — `tidy.py --apply` deletes them (nothing unmerged is lost)" if b else ""))
    s = items["specs"]
    lines.append(f"- spec directories fully ticked but not published/pruned: {len(s)}"
                 + (f" ({', '.join(s[:4])}{', …' if len(s) > 4 else ''}) — `tidy.py --apply` "
                    f"runs publish_and_prune per directory" if s else ""))
    sb = items["specs_blocked"]
    if sb:
        shown = "; ".join(f"{d}: {why}" for d, why in list(sb.items())[:4])
        lines.append(f"- spec directories fully ticked that publish_and_prune would refuse: {len(sb)} "
                     f"({shown}{'; …' if len(sb) > 4 else ''}) — YOUR call: add the missing piece, "
                     f"or delete the directory (git history keeps it); `--apply` leaves them")
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
    rv = items["reviews"]
    gone, md, other = review_sizes(root, rv)
    lines.append(f"- review reports of closed work older than {days} days: {len(rv)} ({_human(gone)})"
                 + (" — `tidy.py --apply` removes them with `git rm` (tracked and unchanged, so "
                    "git history keeps them)" if rv else "")
                 + f"; the reviews folder holds {_human(md)} markdown, {_human(other)} other "
                   f"(evidence, never removed)")
    lines.extend(f"    {x}" for x in rv[:10])
    if len(rv) > 10:
        lines.append("    …")
    for rel, why in items["reviews_skipped"].items():
        lines.append(f"    kept: {rel} — {why}; YOUR call (commit or discard the change first)")
    if items["delta"]:
        lines.append(f"- {DELTA_DIR}/ left over from a template update — `tidy.py --apply` removes it")
    w = items["worktrees"]
    if sizes if sizes is not None else with_remote:
        measured = [(p, tree_size(p)) for p in w]
        partial = not all(complete for _p, (_n, complete) in measured)
        held = f", {'≥ ' if partial else ''}{_human(sum(n for _p, (n, _c) in measured))}" if w else ""
        shown = [f"{p} ({'' if c else '≥ '}{_human(n)})" for p, (n, c) in measured]
    else:
        shown, held = [str(p) for p in w], ""
    lines.append(f"- worktrees of merged branches: {len(w)}{held}"
                 + (" — `tidy.py --apply` removes them" if w else ""))
    lines.extend(f"    {x}" for x in shown)
    for path, why in items["worktrees_kept"].items():
        lines.append(f"    kept: {path} — {why}")
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
    for rel, why in items.get("reviews_skipped", {}).items():
        print(f"tidy: kept {rel} — {why}")
        rc = 1
    for rel in items.get("reviews", []):
        print(f"tidy: $ git rm -q {rel}")
        # never a plain unlink: git rm refuses an untracked or locally changed file,
        # and that refusal is what keeps the only copy
        r = subprocess.run(["git", "-C", str(root), "rm", "-q", "--", rel], capture_output=True, text=True)
        if r.returncode != 0:
            print(f"tidy: could not remove {rel}: {r.stderr.strip()}")
            rc = 1
    if items["worktrees"]:
        import dispatch as _dispatch  # noqa: E402  (sibling; one owner for the worktrees)
        for path in items["worktrees"]:
            print(f"tidy: $ git worktree remove {path}")
            failed = _dispatch.remove_worktree(root, path, worktree_base(root))
            if failed:
                print(f"tidy: could not remove {path}: {failed}")
                rc = 1
    if items["delta"]:
        print(f"tidy: rm -r {DELTA_DIR}")
        shutil.rmtree(root / DELTA_DIR, ignore_errors=True)
    print("tidy: done — commit the tree changes as an ordinary change "
          "(\"history is pruned in a commit that says so\")")
    return rc


def main() -> int:
    args = sys.argv[1:]
    if "-h" in args or "--help" in args:
        print(__doc__)
        return 0
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
              "(branches, finished specs, journal, old archive, old review reports, delta dir, "
              "merged worktrees)")
        return 0
    return apply(root, items, days)


if __name__ == "__main__":
    raise SystemExit(main())
