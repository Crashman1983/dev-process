#!/usr/bin/env python3
"""process_context: deterministic session orientation — one read-only call
instead of exploratory ls/grep/journal-archaeology at session start.

Prints a single JSON object with everything an agent needs to resume:
branch, state file, active plan(s) with their tier:/issue: lines, the active
spec directory with the NEXT unchecked task, unresolved clarification-marker
counts, and the untriaged inbox size. The token saving is the point: /prime
and /execute call this instead of exploring, which is also what makes small
models robust in those phases (no orientation guesswork).

Read-only, never a gate, pure stdlib. Borrowed pattern: Spec Kit's
check-prerequisites --json (deterministic context bootstrap).
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

PLANS = ".process-work/plans"
STATE = ".process-work/state"
INBOX = ".process-work/inbox.md"
SPECS = "specs"

TIER = re.compile(r"^\s*(?:[-*+]\s+)?[*_]*tier[*_]*\s*:\s*[*_]*\s*(\d+)\b",
                  re.IGNORECASE | re.MULTILINE)
ISSUE = re.compile(r"^\s*(?:[-*+]\s+)?issue\s*:\s*(\S+)", re.IGNORECASE | re.MULTILINE)
UNCHECKED = re.compile(r"^\s*- \[ \] (.+)$", re.MULTILINE)
CHECKED = re.compile(r"^\s*- \[[xX]\] ", re.MULTILINE)
MARKER = re.compile(r"\[NEEDS CLARIFICATION", re.IGNORECASE)


def _branch(root: Path) -> str | None:
    r = subprocess.run(["git", "-C", str(root), "symbolic-ref", "--short", "HEAD"],
                       capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _plan_info(p: Path) -> dict:
    text = _read(p)
    tier = TIER.search(text)
    issue = ISSUE.search(text)
    return {"file": str(p), "tier": int(tier.group(1)) if tier else None,
            "issue": issue.group(1) if issue else None}


def main() -> int:
    positional = [a for a in sys.argv[1:] if not a.startswith("--")]
    root = Path(positional[0] if positional else ".").resolve()
    branch = _branch(root)
    out: dict = {"branch": branch}

    slug = (branch or "").replace("/", "-")
    state = root / STATE / f"{slug}.md"
    out["state_file"] = str(state.relative_to(root)) if state.is_file() else None

    journal_shard = root / ".process-work/journal" / slug
    shard_files = sorted(journal_shard.glob("*.md")) if journal_shard.is_dir() else []
    flat = sorted((root / ".process-work/journal").glob("*.md")) \
        if (root / ".process-work/journal").is_dir() else []
    latest = (shard_files or flat)
    out["latest_journal"] = str(latest[-1].relative_to(root)) if latest else None

    pdir = root / PLANS
    out["active_plans"] = [
        {**_plan_info(p), "file": str(p.relative_to(root))}
        for p in sorted(pdir.glob("*.md"))
        if not p.name.startswith("design-")
    ] if pdir.is_dir() else []

    features = []
    sdir = root / SPECS
    if sdir.is_dir():
        for fdir in sorted(d for d in sdir.iterdir() if d.is_dir()):
            tasks = _read(fdir / "tasks.md")
            unchecked = UNCHECKED.findall(tasks)
            info = {
                "dir": str(fdir.relative_to(root)),
                **({k: v for k, v in _plan_info(fdir / "plan.md").items()
                    if k != "file"} if (fdir / "plan.md").is_file() else {}),
                "tasks_done": len(CHECKED.findall(tasks)),
                "tasks_open": len(unchecked),
                "next_task": unchecked[0].strip() if unchecked else None,
                "unresolved_markers": sum(
                    len(MARKER.findall(_read(f))) for f in fdir.glob("*.md")),
            }
            features.append(info)
    out["spec_features"] = features

    inbox = root / INBOX
    out["inbox_items"] = sum(
        1 for line in _read(inbox).splitlines() if line.strip().startswith(("-", "*"))
    ) if inbox.is_file() else 0

    if "--cost" in sys.argv:
        out["context_cost"] = context_cost(root, out)

    print(json.dumps(out, indent=2))
    return 0


# --- context cost: what a session reads, in approximate tokens ------------
# Measure before cutting. "Which doc is too long" is guesswork until the
# sizes are on the table; this puts them there. The estimate is chars/4 — a
# rough average for English prose and code in current tokenizers — so the
# numbers compare against each other, not against a bill.
CHARS_PER_TOKEN = 4
ANCHORS = ("CLAUDE.md", "AGENTS.md", ".github/copilot-instructions.md")
COMMAND_DIRS = (".claude/commands", ".github/prompts")


def _tokens(paths: list[Path]) -> dict:
    sizes = [(p, len(_read(p))) for p in paths if p.is_file()]
    return {"files": len(sizes),
            "tokens": sum(n for _p, n in sizes) // CHARS_PER_TOKEN}


def context_cost(root: Path, ctx: dict) -> dict:
    groups: dict[str, list[Path]] = {}
    groups["anchor"] = [root / a for a in ANCHORS]
    groups["commands"] = [p for d in COMMAND_DIRS
                          for p in sorted((root / d).glob("*.md"))
                          if (root / d).is_dir()]
    groups["process_docs"] = sorted((root / "docs/process").rglob("*.md")) \
        if (root / "docs/process").is_dir() else []
    groups["product_frame"] = [root / "PRODUCT.md"]
    groups["active_plans"] = [root / p["file"] for p in ctx.get("active_plans", [])]
    groups["state_and_latest_journal"] = [root / f for f in
                                          (ctx.get("state_file"), ctx.get("latest_journal"))
                                          if f]
    jdir = root / ".process-work/journal"
    groups["all_journal_shards"] = sorted(jdir.rglob("*.md")) if jdir.is_dir() else []
    groups["spec_dirs"] = [p for f in ctx.get("spec_features", [])
                           for p in sorted((root / f["dir"]).glob("*.md"))]
    report = {name: _tokens(paths) for name, paths in groups.items()}
    # what /prime actually loads: anchor + commands + the branch's own working
    # memory — the process docs are read on demand, the journal never whole
    session = sum(report[k]["tokens"] for k in
                  ("anchor", "commands", "product_frame", "active_plans",
                   "state_and_latest_journal"))
    report["session_start_estimate_tokens"] = session
    everything = sorted({p for ps in groups.values() for p in ps if p.is_file()},
                        key=lambda p: -len(_read(p)))
    report["largest"] = [{"file": str(p.relative_to(root)),
                          "tokens": len(_read(p)) // CHARS_PER_TOKEN}
                         for p in everything[:10]]
    report["unit"] = f"approx tokens = chars / {CHARS_PER_TOKEN}"
    return report


if __name__ == "__main__":
    raise SystemExit(main())
