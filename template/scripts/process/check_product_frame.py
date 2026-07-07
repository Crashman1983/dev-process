#!/usr/bin/env python3
"""product-frame gate: keep PRODUCT.md honest — present, state-readable, and
free of dead references. Core and always on: the product frame is the
direction development is checked against, so its enforcement must not hinge
on an optional module.

Mechanical honesty only — prose quality (are the goals good? the non-goals
complete?) is judgment and belongs to the review gate (`review-checklist.md`,
Product frame). What this gate checks:

  - HARD: PRODUCT.md missing. It is a core artifact and ships with the
    template; deleting it removes the frame. (Unlike the *optional* arch-docs
    overview, absence here is a violation, not pre-adoption.)
  - HARD: no recognizable `status:` line, or a value outside
    `not-onboarded | onboarded` — the state axis must stay readable.
  - SOFT: `status: not-onboarded` — expected before the start-here onboarding
    dialogue has filled the frame; placeholders are allowed in this state.
  - HARD once onboarded: leftover placeholder lines. An onboarded frame still
    holding placeholders claims direction it does not have.
  - HARD: an `ADR-NNNN` reference that resolves to no decision record
    (docs/process/adr/ is core).
  - HARD when docs/process/feature-registry/ exists: a `STORY-NNNN` reference
    that resolves to no story file. SOFT note when the registry is absent —
    not checkable, honest degradation.

Fenced code blocks are quotations, not claims — ignored for refs and
placeholders. Pure stdlib.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

FRAME = "PRODUCT.md"
ADR_DIR = "docs/process/adr"
REGISTRY_DIR = "docs/process/feature-registry"

STATUS = re.compile(r"^status:\s*(\S+)\s*$", re.MULTILINE)
STATES = {"not-onboarded", "onboarded"}
ADR_REF = re.compile(r"\bADR-(\d+)\b")
STORY_REF = re.compile(r"\bSTORY-(\d{4})\b")
PLACEHOLDER = re.compile(r"^\s*>\s*_Placeholder", re.MULTILINE)
HEADING = re.compile(r"^##\s+(.*)$", re.MULTILINE)


def _unfenced(text: str) -> str:
    """Drop fenced code blocks — a quoted example is not a claim."""
    out: list[str] = []
    fenced = False
    for line in text.splitlines(keepends=True):
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if not fenced:
            out.append(line)
    return "".join(out)


def _adr_exists(root: Path, num: str) -> bool:
    d = root / ADR_DIR
    for width in {num, num.zfill(4)}:
        if any(d.glob(f"adr-{width}-*.md")):
            return True
    return False


def _placeholder_sections(text: str) -> list[str]:
    """Headings of sections whose body still holds a placeholder line."""
    out = []
    heads = list(HEADING.finditer(text))
    for i, m in enumerate(heads):
        start = m.end()
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        if PLACEHOLDER.search(text[start:end]):
            out.append(m.group(1).strip())
    return out


def check(root: Path) -> tuple[list[str], list[str]]:
    hard: list[str] = []
    soft: list[str] = []
    f = root / FRAME
    if not f.is_file():
        return ([f"{FRAME} missing — the product frame is a core artifact; "
                 f"restore it (the template ships a scaffold)"], [])
    try:
        text = _unfenced(f.read_text(encoding="utf-8"))
    except UnicodeDecodeError:
        return ([f"{FRAME}: not valid UTF-8"], [])

    m = STATUS.search(text)
    if not m:
        hard.append(f"{FRAME}: no 'status:' line — the frame's state is unreadable "
                    f"(want 'status: not-onboarded' or 'status: onboarded')")
    elif m.group(1) not in STATES:
        hard.append(f"{FRAME}: status {m.group(1)!r} is not one of "
                    f"{sorted(STATES)}")
    elif m.group(1) == "not-onboarded":
        soft.append("product frame not onboarded yet — fill it in the start-here "
                    "onboarding dialogue and flip 'status:' to 'onboarded'")
    else:  # onboarded — placeholders now claim direction that is not there
        left = _placeholder_sections(text)
        if left:
            hard.append(f"{FRAME}: status is 'onboarded' but "
                        f"{len(left)} section(s) still hold a placeholder: "
                        f"{', '.join(left)}")

    for ref in ADR_REF.finditer(text):
        if not _adr_exists(root, ref.group(1)):
            hard.append(f"{FRAME}: ADR-{ref.group(1)} referenced but no "
                        f"{ADR_DIR}/adr-{ref.group(1)}-*.md exists")

    stories = sorted({s.group(1) for s in STORY_REF.finditer(text)})
    if stories:
        reg = root / REGISTRY_DIR
        if not reg.is_dir():
            soft.append(f"STORY reference(s) in {FRAME} not checkable — "
                        f"no {REGISTRY_DIR}/ (feature-registry off)")
        else:
            for num in stories:
                if not (reg / f"STORY-{num}.json").is_file():
                    hard.append(f"{FRAME}: STORY-{num} referenced but no "
                                f"{REGISTRY_DIR}/STORY-{num}.json exists")
    return hard, soft


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    if not root.is_dir():
        print(f"product-frame: FAILED:\n  - root {root} is not a directory")
        return 1
    hard, soft = check(root)
    for note in soft:
        print(f"product-frame: note: {note}")
    if hard:
        print("product-frame: FAILED:")
        for h in sorted(set(hard)):
            print(f"  - {h}")
        return 1
    print("product-frame: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
