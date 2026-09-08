#!/usr/bin/env python3
"""check_baseline_duplicates: byte-identical screenshots under different names
are evidence of nothing.

A screenshot baseline proves a rendering only if it was rendered under the
conditions its name claims. Observed downstream: a catalog harness ignored
per-story viewport parameters and minted desktop renders under mobile
names — two "mobile" baselines byte-identical to their desktop siblings, a
"dark" one identical to "light". The files existed, the review saw green,
and the evidence was for the wrong thing. This check makes that class
mechanical: within the given directories, every group of byte-identical
image files with more than one distinct name is a finding.

Ratchet (testing.md, Ratchets): pass `--baseline FILE` to pin the groups the
tree already carries — one line per group, the sorted paths joined by ` == `.
A pinned group passes; a new group fails; a pinned group that no longer
occurs fails too (stale exception), so the baseline only ever shrinks.
`--write-baseline FILE` writes the current groups as the starting pin.

Usage: check_baseline_duplicates.py [--baseline FILE | --write-baseline FILE] DIR...
Exit 0 = clean (or only pinned groups), 1 = findings, 2 = usage.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


def _groups(dirs: list[Path], root: Path) -> list[list[str]]:
    by_hash: dict[str, set[str]] = {}
    for d in dirs:
        for p in sorted(d.rglob("*")):
            if not p.is_file() or p.suffix.lower() not in IMAGE_SUFFIXES:
                continue
            if "node_modules" in p.parts or ".git" in p.parts:
                continue
            digest = hashlib.sha256(p.read_bytes()).hexdigest()
            rel = p.relative_to(root).as_posix() if p.is_relative_to(root) else str(p)
            by_hash.setdefault(digest, set()).add(rel)
    # a group is a finding only when the NAMES differ — the same file name in
    # two baseline directories (light/dark folders, two browsers) can be
    # legitimately identical; two different names claiming the same pixels
    # cannot both be right
    out = []
    for paths in by_hash.values():
        if len({Path(p).name for p in paths}) > 1:
            out.append(sorted(paths))
    return sorted(out)


def _key(group: list[str]) -> str:
    return " == ".join(group)


def main(argv: list[str]) -> int:
    baseline: Path | None = None
    write: Path | None = None
    args = list(argv)
    for flag in ("--baseline", "--write-baseline"):
        if flag in args:
            i = args.index(flag)
            if i + 1 >= len(args):
                print(__doc__.strip().splitlines()[-2], file=sys.stderr)
                return 2
            if flag == "--baseline":
                baseline = Path(args[i + 1])
            else:
                write = Path(args[i + 1])
            del args[i:i + 2]
    dirs = [Path(a) for a in args if not a.startswith("--")]
    if not dirs:
        print("usage: check_baseline_duplicates.py [--baseline FILE | "
              "--write-baseline FILE] DIR...", file=sys.stderr)
        return 2
    root = Path.cwd()
    missing = [str(d) for d in dirs if not d.is_dir()]
    if missing:
        print(f"baseline-duplicates: no such directory: {', '.join(missing)}",
              file=sys.stderr)
        return 2
    groups = _groups(dirs, root)
    keys = {_key(g) for g in groups}
    if write is not None:
        write.parent.mkdir(parents=True, exist_ok=True)
        write.write_text("".join(f"{k}\n" for k in sorted(keys)), encoding="utf-8")
        print(f"baseline-duplicates: pinned {len(keys)} group(s) to {write} — "
              f"the ratchet starts here; this file only ever shrinks")
        return 0
    pinned: set[str] = set()
    if baseline is not None and baseline.is_file():
        pinned = {ln.strip() for ln in baseline.read_text(encoding="utf-8").splitlines()
                  if ln.strip() and not ln.startswith("#")}
    new = sorted(keys - pinned)
    stale = sorted(pinned - keys)
    for k in new:
        print(f"baseline-duplicates: byte-identical images under different "
              f"names — at most one of these is evidence of what its name "
              f"claims: {k}")
    for k in stale:
        print(f"baseline-duplicates: pinned group no longer occurs — remove it "
              f"from {baseline} (the ratchet only shrinks): {k}")
    if new or stale:
        print(f"baseline-duplicates: FAILED ({len(new)} new, {len(stale)} stale)")
        return 1
    print(f"baseline-duplicates: OK ({len(keys)} pinned group(s), 0 new)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
