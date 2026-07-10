#!/usr/bin/env python3
"""trace: the full story of one piece of work, in one read-only view.

The process leaves a trace by construction — issue, plan, commits, REVIEW
attestation, review reports — but it is scattered across `.process-work/`, the
journal, git, and GitHub. This tool reassembles it, so "how did this change
happen and who checked it?" is one command instead of archaeology:

    trace.py STORY-0007      # by feature-registry story id
    trace.py '#42'           # by issue ref
    trace.py 2026-07-08-foo  # by plan slug (or any part of it)

It correlates, best-effort and read-only:

  - the feature-registry story (when that module is installed);
  - the issue — offline from the github-master snapshot when present, else via
    `gh` when available, else just the ref;
  - plans (active and archived) whose filename or text mentions a correlation
    key (deliberately broad — a plan that merely discusses the issue is shown);
  - commits mentioning a distinctive key (`git log --grep`; the bare issue
    number is not grepped — it substring-matches unrelated shas/versions);
  - `REVIEW` attestations in the journal whose `work=` matches;
  - review/audit reports in `.process-work/reviews/` (header + FINDING lines).

Sources it cannot reach are named, never silently skipped. Stdlib only; git and
`gh` are optional. Never a gate, never in CI — it reports, it does not fail.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REGISTRY = Path("docs/process/feature-registry")
PLANS = Path(".process-work/plans")
JOURNAL = Path(".process-work/journal")
REVIEWS = Path(".process-work/reviews")
SNAPSHOT = Path(".process-work/github-snapshot.json")

_STORY = re.compile(r"^STORY-\d{4}$")
_ISSUE = re.compile(r"^#?(\d+)$")
_LEAD = r"^\s*(?:[-*+]\s+)?[*_]*"
_PLAN_TIER = re.compile(_LEAD + r"tier[*_]*\s*:\s*[*_]*\s*(\d+)\b", re.I | re.M)
_PLAN_ISSUE = re.compile(_LEAD + r"issue[*_]*\s*:\s*(\S+)", re.I | re.M)
_REVIEW = re.compile(r"^\s*(?:[-*+]\s+)?[*_]*REVIEW\s+(.*)$")
_FINDING = re.compile(r"^\s*(?:[-*+]\s+)?FINDING\s+(.*)$")
_RPT_HEAD = re.compile(_LEAD + r"(review|audit|work|issue|campaign)[*_]*\s*:\s*(.+)$", re.I)


# ---------------------------------------------------------------- correlation

def keys_for(query: str, root: Path) -> tuple[dict, list[str]]:
    """Resolve the query into the work item and its correlation keys."""
    item: dict = {"story": None, "issue": None, "slug": None}
    keys: list[str] = []
    q = query.strip()
    if _STORY.match(q):
        item["story"] = q
        keys.append(q)
        story = load_story(root, q)
        if story and story.get("issue"):
            item["issue"] = digits(story["issue"])
    elif _ISSUE.match(q):
        item["issue"] = _ISSUE.match(q).group(1)
        for p in sorted(REGISTRY_DIR(root).glob("STORY-*.json")) if REGISTRY_DIR(root).is_dir() else []:
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            if digits(d.get("issue")) == item["issue"]:
                item["story"] = d.get("id")
                keys.append(str(d.get("id")))
                break
    else:
        item["slug"] = q
        keys.append(q)
    if item["issue"]:
        keys += [f"#{item['issue']}", item["issue"]]
    return item, keys


def digits(ref) -> str | None:
    d = "".join(c for c in str(ref or "") if c.isdigit())
    return d or None


def REGISTRY_DIR(root: Path) -> Path:
    return root / REGISTRY


def load_story(root: Path, sid: str) -> dict | None:
    p = REGISTRY_DIR(root) / f"{sid}.json"
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


# ------------------------------------------------------------------- sources

def issue_details(root: Path, num: str) -> tuple[dict | None, str | None]:
    """(details, source): the snapshot offline first, then gh, else nothing."""
    snap = root / SNAPSHOT
    if snap.is_file():
        try:
            data = json.loads(snap.read_text(encoding="utf-8"))
            for e in data.get("issues", []):
                if str(e.get("number")) == num:
                    return e, "github-snapshot (offline)"
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass
    try:
        out = subprocess.run(["gh", "issue", "view", num, "--json", "number,title,state"],
                             capture_output=True, text=True, check=True, cwd=root).stdout
        return json.loads(out), "gh (live)"
    except (subprocess.CalledProcessError, FileNotFoundError, json.JSONDecodeError):
        return None, None


def matching_plans(root: Path, keys: list[str]) -> list[dict]:
    out = []
    base = root / PLANS
    if not base.is_dir():
        return out
    for p in sorted(base.rglob("*.md")):
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        hit = any(k in p.name for k in keys) or any(k in text for k in keys)
        if not hit:
            continue
        tier = _PLAN_TIER.search(text)
        issue = _PLAN_ISSUE.search(text)
        out.append({"path": p.relative_to(root), "archived": "archive" in p.parts,
                    "tier": tier.group(1) if tier else None,
                    "issue": issue.group(1) if issue else None})
    return out


def matching_reviews(root: Path, keys: list[str]) -> tuple[list[str], list[dict]]:
    """(journal REVIEW lines, report summaries) that reference a key."""
    lines: list[str] = []
    bare = {k.lstrip("#") for k in keys}
    jdir = root / JOURNAL
    if jdir.is_dir():
        for p in sorted(jdir.rglob("*.md")):
            try:
                text = p.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for raw in text.splitlines():
                m = _REVIEW.match(raw)
                if not m:
                    continue
                wm = re.search(r"\bwork=(\S+)", m.group(1))
                if wm and wm.group(1).lstrip("#") in bare:
                    lines.append("REVIEW " + m.group(1).strip())
    reports: list[dict] = []
    rdir = root / REVIEWS
    if rdir.is_dir():
        for p in sorted(rdir.glob("*.md")):
            try:
                text = p.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if not any(k in text for k in keys):
                continue
            head = {m.group(1).lower(): m.group(2).strip()
                    for m in (_RPT_HEAD.match(ln) for ln in text.splitlines()[:12]) if m}
            findings = [f.group(0).strip() for f in
                        (_FINDING.match(ln) for ln in text.splitlines()) if f]
            reports.append({"path": p.relative_to(root), "head": head, "findings": findings})
    return lines, reports


def matching_commits(root: Path, keys: list[str]) -> list[str] | None:
    """Commits mentioning a distinctive key, newest first; None if git is
    unavailable, [] for a repo with no commits yet. Bare digit keys are skipped
    — `--grep=42` substring-matches unrelated shas and version strings."""
    seen: dict[str, str] = {}
    for k in (k for k in keys if not k.isdigit()):
        try:
            out = subprocess.run(
                ["git", "-C", str(root), "log", "--oneline", "--fixed-strings",
                 f"--grep={k}"], capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.TimeoutExpired):
            return None
        if out.returncode != 0:
            try:
                probe = subprocess.run(["git", "-C", str(root), "rev-parse",
                                        "--git-dir"], capture_output=True, timeout=30)
            except (OSError, subprocess.TimeoutExpired):
                return None
            # a git repo with an unborn branch has no commits — that is an
            # empty trail, not "git unavailable"
            return [] if probe.returncode == 0 else None
        for ln in out.stdout.splitlines():
            sha = ln.split(" ", 1)[0]
            seen.setdefault(sha, ln)
    return list(seen.values())


# -------------------------------------------------------------------- report

def render(query: str, root: Path) -> str:
    item, keys = keys_for(query, root)
    L = [f"# trace — {query}", ""]
    notes: list[str] = []

    L.append("## Work item")
    story = load_story(root, item["story"]) if item["story"] else None
    if story:
        L.append(f"- story {story.get('id')}: {story.get('title', '')} "
                 f"[status: {story.get('status')}]")
        if story.get("tests"):
            L.append(f"- mapped tests: {len(story['tests'])}")
    elif item["story"]:
        L.append(f"- story {item['story']} (registry entry unreadable)")
    elif not REGISTRY_DIR(root).is_dir():
        notes.append("no feature-registry (module off or empty) — story enrichment skipped")
    if item["issue"]:
        det, src = issue_details(root, item["issue"])
        if det:
            L.append(f"- issue #{item['issue']}: {det.get('title', '')} "
                     f"[{str(det.get('state', '')).lower()}] — via {src}")
        else:
            L.append(f"- issue #{item['issue']} (no snapshot, gh unavailable — ref only)")
    if item["slug"]:
        L.append(f"- plan slug query: {item['slug']}")
    if not (story or item["issue"] or item["slug"]):
        L.append("- nothing resolvable from the query")

    L += ["", "## Plans"]
    plans = matching_plans(root, keys)
    for p in plans:
        state = "archived (merged)" if p["archived"] else "active"
        extra = "".join(f"  {k}: {v}" for k, v in (("tier", p["tier"]), ("issue", p["issue"])) if v)
        L.append(f"- {p['path']} [{state}]{extra}")
    if not plans:
        L.append("- none found")

    L += ["", "## Commits"]
    commits = matching_commits(root, keys)
    if commits is None:
        notes.append("git unavailable — commit trail skipped")
        L.append("- (git unavailable)")
    elif commits:
        L += [f"- {c}" for c in commits[:30]]
        if len(commits) > 30:
            L.append(f"- (+{len(commits) - 30} more)")
    else:
        L.append("- none mention " + ", ".join(keys))

    L += ["", "## Reviews"]
    if not (root / REVIEWS).is_dir():
        notes.append("no reviews directory yet (.process-work/reviews absent) — reports skipped")
    rev_lines, reports = matching_reviews(root, keys)
    L += [f"- {ln}" for ln in rev_lines] or ["- no REVIEW attestation references this work"]
    for r in reports:
        kind = "audit" if "audit" in r["head"] else "review"
        name = r["head"].get("audit") or r["head"].get("review") or "?"
        pub = r["head"].get("issue", "unpublished")
        L.append(f"- report {r['path']} ({kind}: {name}, issue: {pub})")
        L += [f"  - {f}" for f in r["findings"][:10]]

    if notes:
        L += ["", "## Notes"] + [f"- {n}" for n in notes]
    return "\n".join(L)


# ------------------------------------------------------------------- selftest

def _selftest() -> int:
    item, keys = keys_for("#42", Path("/nonexistent"))
    assert item["issue"] == "42" and "#42" in keys and "42" in keys
    item, _ = keys_for("STORY-0007", Path("/nonexistent"))
    assert item["story"] == "STORY-0007"
    item, keys = keys_for("2026-07-08-foo", Path("/nonexistent"))
    assert item["slug"] == "2026-07-08-foo" and keys == ["2026-07-08-foo"]
    assert digits("#412") == "412" and digits(None) is None
    assert _REVIEW.match("- REVIEW work=42 tier=2 verdict=pass")
    # the tolerated emphasis form closes before the colon: **issue**: #42
    m = _PLAN_ISSUE.search("- **issue**: #42\n")
    assert m and m.group(1) == "#42", m
    print("trace selftest: OK")
    return 0


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return _selftest()
    if not argv or not argv[0].strip():
        # a blank query would match every plan, commit, and report — refuse
        raise SystemExit(__doc__)
    print(render(argv[0], Path.cwd()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
