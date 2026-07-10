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

import json
import re
import sys
from pathlib import Path

FRAME = "PRODUCT.md"
REGISTRY_DIR = "docs/process/feature-registry"

# the decision-records gate (core, co-rendered) owns ADR file identity —
# import, don't copy (one owner per behavior)
sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling import
from check_decisions import ADR_DIR, adr_exists  # noqa: E402

STATUS = re.compile(r"^\s*(?:[-*+]\s+)?[*_]*status[*_]*:\s*(.+?)\s*$", re.MULTILINE)
STATES = {"not-onboarded", "onboarded"}
ADR_REF = re.compile(r"\bADR-(\d+)\b")
STORY_REF = re.compile(r"\bSTORY-(\d+)\b")  # any width; normalized like ADR refs
PLACEHOLDER = re.compile(r"^\s*>\s*_Placeholder", re.MULTILINE)
HEADING = re.compile(r"^##\s+(.*)$", re.MULTILINE)
HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)


def _unfenced(text: str) -> str:
    """Drop fenced code blocks (``` and ~~~, closed by their own marker) and
    HTML comments — a quoted or commented example is not a claim. The seed
    itself uses an HTML comment for the status-flip instruction."""
    text = HTML_COMMENT.sub("", text)
    out: list[str] = []
    fence: str | None = None
    for line in text.splitlines(keepends=True):
        stripped = line.lstrip()
        marker = next((m for m in ("```", "~~~") if stripped.startswith(m)), None)
        if marker and fence is None:
            fence = marker
            continue
        if marker and fence == marker:
            fence = None
            continue
        if fence is None:
            out.append(line)
    return "".join(out)


def _story_ids(root: Path) -> set[str]:
    """Registered story ids — resolved by the `id` field like the registry
    gate does, falling back to the filename stem, so a story living in a
    non-canonical filename still resolves."""
    reg = root / REGISTRY_DIR
    ids: set[str] = set()
    for p in reg.glob("*.json"):
        if p.name.endswith(".example.json"):
            continue
        ids.add(p.stem)
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            continue
        if isinstance(d, dict) and isinstance(d.get("id"), str):
            ids.add(d["id"])
    return ids


def _leftover_placeholders(text: str) -> list[str]:
    """Where placeholder lines survive: section headings when a heading
    encloses the hit, '(before the first section)' otherwise. Scans the WHOLE
    text — a placeholder above the first heading must not pass green."""
    out: list[str] = []
    heads = list(HEADING.finditer(text))
    first = heads[0].start() if heads else len(text)
    if PLACEHOLDER.search(text[:first]):
        out.append("(before the first section)")
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
                    f"{sorted(STATES)} (one bare value, no annotation)")
    elif m.group(1) == "not-onboarded":
        soft.append("product frame not onboarded yet — fill it in the start-here "
                    "onboarding dialogue and flip 'status:' to 'onboarded'")
    else:  # onboarded — placeholders now claim direction that is not there
        left = _leftover_placeholders(text)
        if left:
            hard.append(f"{FRAME}: status is 'onboarded' but "
                        f"{len(left)} place(s) still hold a placeholder: "
                        f"{', '.join(left)}")

    for ref in ADR_REF.finditer(text):
        if not adr_exists(root, ref.group(1)):
            hard.append(f"{FRAME}: ADR-{ref.group(1)} referenced but no "
                        f"{ADR_DIR}/adr-{ref.group(1)}-*.md exists")

    stories = sorted({s.group(1) for s in STORY_REF.finditer(text)})
    if stories:
        reg = root / REGISTRY_DIR
        if not reg.is_dir():
            soft.append(f"STORY reference(s) in {FRAME} not checkable — "
                        f"no {REGISTRY_DIR}/ (feature-registry off)")
        else:
            ids = _story_ids(root)
            for num in stories:
                # width-normalized like ADR refs: STORY-7 resolves to STORY-0007
                if f"STORY-{num.zfill(4)}" not in ids and f"STORY-{num}" not in ids:
                    hard.append(f"{FRAME}: STORY-{num} referenced but no such "
                                f"story is registered in {REGISTRY_DIR}/")
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
