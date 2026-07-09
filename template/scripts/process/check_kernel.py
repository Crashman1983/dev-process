#!/usr/bin/env python3
"""kernel gate (core, always on): the always-on kernel block must be present and
intact in every anchor file that exists.

The kernel is the one part of the process that is *always in context* — it
carries the mandatory-rule summary, tier routing, and the language rule into
every session. Most mandatory rules are not individually machine-checkable
(verify-before-asserting, root-cause-before-symptom, readable code); they are
binding only because the kernel keeps them in front of the agent. So the kernel
itself is the load-bearing artifact — and this gate protects it: if the block is
edited, truncated, or a rule silently dropped from an anchor, the merge blocks.

Canonical source: docs/process/kernel.md, the text between the
`<!-- KERNEL:START -->` and `<!-- KERNEL:END -->` markers. Every rendered anchor
carries a byte-identical copy of that block; adopters extend their anchor
*outside* the markers, never inside (the "extend, never remove" rule). This gate
compares each present anchor's marked block to the canonical one.

Honest boundary: it verifies the block is present in the file, not that the
harness actually loaded it — that is not observable from a file. Stdlib only,
offline.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

KERNEL_DOC = "docs/process/kernel.md"
# Anchor files that carry the kernel when their adapter is installed. The gate
# checks only the ones that exist — a skipped adapter leaves no file to drift.
ANCHORS = ["CLAUDE.md", "AGENTS.md", ".github/copilot-instructions.md"]
_BLOCK = re.compile(r"<!-- KERNEL:START -->(.*?)<!-- KERNEL:END -->", re.S)


def _block(text: str) -> str | None:
    m = _BLOCK.search(text)
    return m.group(1).strip() if m else None


def check(root: Path) -> tuple[list[str], list[str]]:
    doc = root / KERNEL_DOC
    if not doc.is_file():
        return [f"{KERNEL_DOC} is missing — the canonical kernel source is gone"], []
    try:
        canonical = _block(doc.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, OSError) as exc:
        return [f"{KERNEL_DOC}: could not read: {exc}"], []
    if canonical is None:
        return [f"{KERNEL_DOC} has no KERNEL:START/END block — the canonical "
                "kernel is unreadable"], []

    hard: list[str] = []
    present = []
    for rel in ANCHORS:
        p = root / rel
        if not p.is_file():
            continue
        present.append(rel)
        try:
            block = _block(p.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, OSError) as exc:
            hard.append(f"{rel}: could not read: {exc}")
            continue
        if block is None:
            hard.append(f"{rel}: the KERNEL:START/END block is missing — the "
                        "always-on rules are not carried into the session")
        elif block != canonical:
            hard.append(f"{rel}: the kernel block has drifted from {KERNEL_DOC} "
                        "— a rule may have been dropped, changed, or truncated; "
                        "restore it (extend your anchor outside the markers)")

    if not present:
        return hard, [f"no anchor carries the kernel yet ({', '.join(ANCHORS)} "
                      f"absent) — merge the block from {KERNEL_DOC} into your anchor"]
    return hard, []


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    hard, soft = check(root)
    for note in soft:
        print(f"kernel: note: {note}")
    if hard:
        print("kernel: FAILED:")
        for h in hard:
            print(f"  - {h}")
        return 1
    print("kernel: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
