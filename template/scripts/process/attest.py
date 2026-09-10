#!/usr/bin/env python3
"""attest: write the REVIEW line — computed, validated, never typed.

Why a writer exists: the REVIEW attestation is the artifact the review gate
enforces, and every field of it was typed by hand. Two failure classes grew
there. Malformed lines (the gate catches those). And digests that were never
computed: on one deployment, 15 of 16 recorded `diff=` values matched no
byte stream of any commit within five days of the record — plausible hex,
written to look right. The gate reported the mismatch every run; because it
stayed red for months, nobody read it any more. Evidence that can be typed
will be typed.

This tool closes the typing path. It takes the review's fields as flags,
takes base/head from the bundle's `REVIEW_ARTIFACT` line (or `--base`/
`--head`), RECOMPUTES the digest with the gate's own formula
(`check_review.artifact_digest` — one owner for producer, writer and
verifier), refuses when the bundle's digest does not match (the tree moved
since the bundle: rebuild it), validates the finished line through the
gate's parser, and appends it to the journal shard. What this cannot do —
and does not claim — is prove the review happened; it proves the line was
produced from the artifact it names.

Usage:
  attest.py --work ID --tier N --reviewer R --model M --independence a,b
            --verdict pass|block --round N
            [--bundle FILE | --base SHA --head SHA] [--note TEXT]
            [--journal-dir DIR] [--dry-run]
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling import
from check_review import (  # noqa: E402  (one owner for grammar + digest)
    JOURNAL_DIR,
    artifact_digest,
    parse_review_lines,
)

ARTIFACT_LINE = re.compile(
    r"^REVIEW_ARTIFACT\s+base=(?P<base>\S+)\s+head=(?P<head>\S+)\s+diff=(?P<diff>\S+)\s*$",
    re.MULTILINE)


def _git(root: Path, *args: str) -> str | None:
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def _journal_target(root: Path, journal_dir: Path) -> Path:
    """Today's shard: per-branch when that shard directory exists (parallel
    efforts), the flat daily file otherwise (journal-state-plans.md)."""
    today = dt.date.today().isoformat()
    branch = _git(root, "symbolic-ref", "--short", "HEAD") or ""
    slug = branch.replace("/", "-")
    if slug and (journal_dir / slug).is_dir():
        return journal_dir / slug / f"{today}.md"
    return journal_dir / f"{today}.md"


def build_line(args, root: Path) -> tuple[str, list[str]]:
    """(REVIEW line, problems). The digest is computed here, never copied."""
    problems: list[str] = []
    fields = [f"work={args.work}", f"tier={args.tier}", f"reviewer={args.reviewer}",
              f"model={args.model}", f"independence={args.independence}",
              f"verdict={args.verdict}", f"round={args.round_}"]
    base = head = None
    bundle_digest = None
    if args.bundle:
        text = Path(args.bundle).read_text(encoding="utf-8", errors="replace")
        m = ARTIFACT_LINE.search(text)
        if not m:
            problems.append(f"no REVIEW_ARTIFACT line in {args.bundle}")
        else:
            base, head, bundle_digest = m.group("base"), m.group("head"), m.group("diff")
    if args.base or args.head:
        if not (args.base and args.head):
            problems.append("--base and --head go together")
        base, head = args.base, args.head
    if base and head and not problems:
        digest = artifact_digest(root, base, head)
        if digest is None:
            problems.append(f"cannot compute the diff {base[:9]}...{head[:9]} in this "
                            f"clone — the commits must exist here")
        else:
            if bundle_digest and bundle_digest != digest:
                problems.append(f"the bundle's digest {bundle_digest[:12]}… differs from "
                                f"the recomputed {digest[:12]}… for the same base/head — "
                                f"the bundle is stale or its line was edited; rebuild "
                                f"the bundle and review again")
            fields += [f"base={base}", f"head={head}", f"diff={digest}"]
    line = "REVIEW " + " ".join(fields)
    records, errors = parse_review_lines(line)
    for _ln, msg in errors:
        problems.append(f"malformed: {msg}")
    return line, problems


def main() -> int:
    ap = argparse.ArgumentParser(description="write a computed, validated REVIEW line")
    ap.add_argument("--work", required=True)
    ap.add_argument("--tier", required=True)
    ap.add_argument("--reviewer", default="fresh-agent")
    ap.add_argument("--model", required=True)
    ap.add_argument("--independence", required=True)
    ap.add_argument("--verdict", required=True)
    ap.add_argument("--round", required=True, dest="round_")
    ap.add_argument("--bundle")
    ap.add_argument("--base")
    ap.add_argument("--head")
    ap.add_argument("--note", help="prose paragraph written above the line")
    ap.add_argument("--journal-dir", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("root", nargs="?", default=str(ROOT))
    args = ap.parse_args()
    root = Path(args.root).resolve()
    line, problems = build_line(args, root)
    if problems:
        print("attest: REFUSED — nothing written:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1
    journal_dir = Path(args.journal_dir) if args.journal_dir else root / JOURNAL_DIR
    target = _journal_target(root, journal_dir)
    print(line)
    if args.dry_run:
        print(f"attest: dry run — would append to {target.relative_to(root) if target.is_relative_to(root) else target}")
        return 0
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as fh:
        if target.stat().st_size == 0:
            fh.write(f"# {dt.date.today().isoformat()}\n\n")
        if args.note:
            fh.write(args.note.rstrip() + "\n\n")
        fh.write(line + "\n")
    print(f"attest: appended to {target.relative_to(root) if target.is_relative_to(root) else target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
