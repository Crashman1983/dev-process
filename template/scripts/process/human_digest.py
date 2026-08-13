#!/usr/bin/env python3
"""human_digest: the owner's inbound edges, as one readable page.

The process produces everything a human owner needs — staged specs, merged
plans, waiver debts, fix clusters — but scattered across issues, journals
and directories, which in practice means the owner polls nothing and reads
nothing. This aggregator turns the owner into a real node of the loop graph:
defined inputs, one page, plain language first.

Sections, in reading order:
  1. WAITING FOR YOU — specs in the influence window (no tasks.md yet, or
     unresolved [NEEDS CLARIFICATION]); each led by its Owner brief, the
     five plain-language sentences the spec template mandates.
  2. MERGED — archived plans of the last N days (slug, tier, issue), the
     pool the sampling audit draws from, with a deterministic weekly pick.
  3. OPEN DEBTS — review-waived:/spec-waived: lines still standing; a
     degradation is a debt with an owner (journal-state-plans.md).
  4. FIX CLUSTERS — the rule-6-across-sessions advisory, inlined from
     process_kpis.py where the telemetry module is installed.

Read-only; never blocks; missing sources are named, never silently empty.
Pure stdlib. Usage:
    human_digest.py [--days N] [-o FILE]
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import re
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # the reader must not dirty the tree

ROOT = Path(__file__).resolve().parents[2]
SPECS = "specs"
PLANS_ARCHIVE = ".process-work/plans/archive"
PLANS_ACTIVE = ".process-work/plans"
DATE_PREFIX = re.compile(r"^(\d{4}-\d{2}-\d{2})-")
TIER = re.compile(r"^\s*(?:[-*+]\s+)?[*_]*tier[*_]*\s*:\s*[*_]*\s*(\d+)\b",
                  re.IGNORECASE | re.MULTILINE)
ISSUE = re.compile(r"^\s*(?:[-*+]\s+)?[*_]*issue[*_]*\s*:\s*(\S+)",
                   re.IGNORECASE | re.MULTILINE)
MARKER = re.compile(r"\[NEEDS CLARIFICATION[^\]]*\]")
WAIVER = re.compile(r"^\s*(?:[-*+]\s+)?[*_]*(review-waived|spec-waived)"
                    r"[*_]*\s*:\s*(.+)$", re.IGNORECASE | re.MULTILINE)
BRIEF_HEADING = re.compile(r"^#{1,6}\s+Owner brief\b.*$", re.IGNORECASE)


def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def owner_brief(text: str) -> str | None:
    """The Owner-brief section body, if the spec carries one."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if BRIEF_HEADING.match(line.strip()):
            body: list[str] = []
            for j in range(i + 1, len(lines)):
                s = lines[j]
                if re.match(r"^#{1,6}\s", s):
                    break
                if s.strip().startswith("<!--") or s.strip().endswith("-->"):
                    continue
                body.append(s.rstrip())
            b = "\n".join(body).strip()
            return b or None
    return None


def section_waiting(root: Path) -> list[str]:
    out: list[str] = []
    sdir = root / SPECS
    if not sdir.is_dir():
        return ["(no specs/ directory — nothing staged for you)"]
    for d in sorted(p for p in sdir.iterdir() if p.is_dir()):
        spec = d / "spec.md"
        if not spec.is_file():
            continue
        text = _read(spec)
        planned = (d / "tasks.md").is_file()
        markers = MARKER.findall(text)
        if planned and not markers:
            continue  # past the influence window, no open question
        im = ISSUE.search(text)
        head = f"**{d.name}**" + (f" ({im.group(1)})" if im else " (no issue ref)")
        state = "not yet planned" if not planned else "planned, but"
        if markers:
            state += f" {len(markers)} open question(s)"
        out.append(f"{head} — {state}")
        brief = owner_brief(text)
        if brief:
            out.append(brief)
        else:
            out.append("(no Owner brief in this spec — ask for one; the "
                       "template mandates it)")
        for m in markers[:5]:
            out.append(f"  - open: {m}")
        out.append("")
    return out or ["(nothing waiting — every active spec is planned and "
                   "question-free)"]


def section_merged(root: Path, days: int) -> tuple[list[str], list[str]]:
    """(lines, candidate slugs) — archived plans dated within the window."""
    out: list[str] = []
    candidates: list[str] = []
    adir = root / PLANS_ARCHIVE
    if not adir.is_dir():
        return ["(no plan archive yet)"], []
    cutoff = _dt.date.today() - _dt.timedelta(days=days)
    for p in sorted(adir.glob("*.md")):
        m = DATE_PREFIX.match(p.name)
        if not m:
            continue
        try:
            d = _dt.date.fromisoformat(m.group(1))
        except ValueError:
            continue
        if d < cutoff:
            continue
        text = _read(p)
        tm, im = TIER.search(text), ISSUE.search(text)
        tier = tm.group(1) if tm else "?"
        issue = im.group(1) if im else "-"
        out.append(f"- {p.name} · tier {tier} · issue {issue}")
        candidates.append(p.name)
    if not out:
        out = [f"(nothing merged in the last {days} days)"]
    return out, candidates


def sampling_pick(candidates: list[str]) -> str | None:
    """Deterministic weekly pick: same ISO week, same choice — so the pick
    cannot be quietly re-rolled until a convenient slice comes up."""
    if not candidates:
        return None
    week = _dt.date.today().isocalendar()
    seed = f"{week.year}-{week.week}"
    idx = int(hashlib.sha256(seed.encode()).hexdigest(), 16) % len(candidates)
    return sorted(candidates)[idx]


def section_debts(root: Path) -> list[str]:
    out: list[str] = []
    for rel_dir in (PLANS_ACTIVE, PLANS_ARCHIVE):
        d = root / rel_dir
        if not d.is_dir():
            continue
        for p in sorted(d.glob("*.md")):
            for kind, reason in WAIVER.findall(_read(p)):
                owned = bool(re.search(r"#\d+|https?://", reason))
                tag = "" if owned else "  ← NO OWNER (link an issue)"
                out.append(f"- {rel_dir}/{p.name}: {kind.lower()}: "
                           f"{reason.strip()[:100]}{tag}")
    return out or ["(no standing waivers)"]


def section_clusters(root: Path) -> list[str]:
    kpis = root / "scripts/process/process_kpis.py"
    if not kpis.is_file():
        return ["(telemetry module not installed — no cluster advisory)"]
    proc = subprocess.run([sys.executable, str(kpis), "clusters"],
                          capture_output=True, text=True, cwd=str(root))
    body = (proc.stdout or "").strip()
    return body.splitlines() if body else ["(cluster reader returned nothing)"]


def build(root: Path, days: int) -> str:
    lines: list[str] = []
    lines.append(f"# Owner digest — {_dt.date.today().isoformat()}")
    lines.append("")
    lines.append("One page: what waits for your judgment, what merged, what "
                 "debts stand, what patterns repeat. Everything else is "
                 "deliberately absent.")
    lines.append("")
    lines.append("## 1 · Waiting for you (influence window)")
    lines.append("")
    lines += section_waiting(root)
    lines.append("")
    lines.append(f"## 2 · Merged (last {days} days)")
    lines.append("")
    merged, candidates = section_merged(root, days)
    lines += merged
    pick = sampling_pick(candidates)
    if pick:
        lines.append("")
        lines.append(f"**Sampling audit pick (this ISO week): `{pick}`** — one "
                     f"deep, post-merge look per week keeps the gates honest "
                     f"(`verification-independence.md`, Sampling audit). The "
                     f"pick is deterministic per week: no re-rolling.")
    lines.append("")
    lines.append("## 3 · Open debts (waivers)")
    lines.append("")
    lines += section_debts(root)
    lines.append("")
    lines.append("## 4 · Repeating patterns (fix clusters)")
    lines.append("")
    lines += section_clusters(root)
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="owner digest (read-only)")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("-o", dest="out")
    ap.add_argument("root", nargs="?", default=str(ROOT))
    args = ap.parse_args()
    digest = build(Path(args.root).resolve(), args.days)
    if args.out:
        Path(args.out).write_text(digest, encoding="utf-8")
        print(f"digest written to {args.out}")
    else:
        print(digest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
