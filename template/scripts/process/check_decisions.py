#!/usr/bin/env python3
"""decision-records gate (core, always-on): keep the decision-record files
themselves honest and internally coherent.

`docs/process/adr/` ships in core, so its integrity is checked in core — not
gated behind an optional module. This gate owns the *files*; the `arch_docs`
gate owns overview→ADR *reference* resolution. Different artifacts, one owner
each, no overlap.

  - HARD: a decision file not listed in README.md's index (silently unfindable);
    a Status or Type value outside its enum (a typo makes the axis unreadable);
    an incoherent Status×Intent pair — `Superseded` with `keep`/`change-planned`
    (a superseded decision is historical; endorsing it or planning its migration
    contradicts the supersession); a missing `## Status` section (every decision
    has a lifecycle); a non-UTF-8 file.
  - SOFT: a field still holding the unedited template menu (`|`-separated, "not
    yet chosen"); a missing `## Type` or `## Intent` section (the process's own
    newer axes — absence reads as the default, never a retroactive false-red);
    `Intent: change-planned` with no linked follow-up (should link, but it may
    legitimately be an issue).

The gate checks presence and enum-membership only. Whether a decision is
*correct* is the review gate's job, never this one — no false-green.

Pure stdlib.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ADR_DIR = "docs/process/adr"
README = "README.md"
ADR_FILE = re.compile(r"^adr-(\d+)-.*\.md$")

STATUS_OK = {"proposed", "accepted"}  # plus any "superseded..." prefix
INTENT_OK = {"keep", "change-planned", "tolerated"}
TYPE_OK = {"architecture", "product", "process"}


def _section_value(text: str, name: str) -> tuple[str | None, int | None]:
    """The first non-empty line under a `## <name>` heading (any heading level
    is tolerated), and its 1-based line number. (None, heading-line) if the
    section is present but empty; (None, None) if the heading is absent."""
    heading = re.compile(rf"^#{{1,6}}\s+{re.escape(name)}\s*$", re.IGNORECASE)
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if heading.match(line.strip()):
            for j in range(i + 1, len(lines)):
                s = lines[j].strip()
                if s:
                    return s, j + 1
            return None, i + 1
    return None, None


def _is_menu(value: str) -> bool:
    """The shipped template lines are `a | b | c` — a `|` means unfilled."""
    return "|" in value


def _first_token(value: str) -> str:
    """Normalize an axis value to its leading keyword: strip a markdown list
    marker, take the first whitespace-delimited word, drop trailing
    punctuation, lowercase. Lets `- Accepted`, `Accepted.`, `Accepted (2026)`
    all read as `accepted` — cosmetic formatting is not a wrong value."""
    v = value.strip()
    if v.startswith(("- ", "* ")):
        v = v[2:].strip()
    parts = v.split()
    return parts[0].strip(".,;:").lower() if parts else ""


def _listed_numbers(root: Path) -> set[int]:
    """Decision numbers the README index references — as `ADR-NNNN` tokens or as
    leading table cells `| NNNN |`. Zero-pad-insensitive."""
    f = root / ADR_DIR / README
    if not f.is_file():
        return set()
    try:
        text = f.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return set()
    nums: set[int] = set()
    # Only index *table rows* count as "listed". A bare ADR-NNNN mention in
    # prose — most naturally another record's "Superseded by ADR-NNNN" status,
    # the very case that puts a fresh number in the file — must NOT satisfy the
    # index requirement, or a genuinely unindexed decision file passes green.
    for m in re.finditer(r"^\s*\|\s*0*(\d+)\s*\|", text, re.MULTILINE):
        nums.add(int(m.group(1)))
    return nums


def check(root: Path) -> tuple[list[str], list[str]]:
    hard: list[str] = []
    soft: list[str] = []
    d = root / ADR_DIR
    if not d.is_dir():
        return hard, ["no docs/process/adr/ directory — expected pre-adoption"]

    listed = _listed_numbers(root)
    files = sorted(p for p in d.glob("adr-*.md") if ADR_FILE.match(p.name))
    if not files:
        soft.append("no decision records yet — expected pre-adoption")
        return hard, soft

    for p in files:
        rel = f"{ADR_DIR}/{p.name}"
        num = int(ADR_FILE.match(p.name).group(1))
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            hard.append(f"{rel}: not valid UTF-8")
            continue

        if num not in listed:
            hard.append(f"{rel}: ADR-{num} not listed in {ADR_DIR}/{README} index "
                        f"— a decision missing from the index is unfindable")

        status, s_line = _section_value(text, "Status")
        type_, t_line = _section_value(text, "Type")
        intent, i_line = _section_value(text, "Intent")

        # --- Status (universal; every decision has a lifecycle) ---
        status_tok = None
        if status is None:
            if s_line is None:
                hard.append(f"{rel}: no '## Status' section — lifecycle unstated")
            else:
                soft.append(f"{rel}:{s_line}: '## Status' section is empty")
        elif _is_menu(status):
            soft.append(f"{rel}:{s_line}: Status not chosen (still the template menu)")
        else:
            status_tok = _first_token(status)
            if status_tok not in STATUS_OK and status_tok != "superseded":
                hard.append(f"{rel}:{s_line}: Status {status!r} is not a valid "
                            f"lifecycle (Proposed | Accepted | Superseded ...)")

        # --- Type (process's own axis; absence is soft, not a false-red) ---
        if type_ is None:
            soft.append(f"{rel}: no '## Type' section — reads as 'architecture' by "
                        f"default; add architecture | product | process")
        elif _is_menu(type_):
            soft.append(f"{rel}:{t_line}: Type not chosen (still the template menu)")
        elif _first_token(type_) not in TYPE_OK:
            hard.append(f"{rel}:{t_line}: Type {type_!r} is not one of "
                        f"architecture | product | process")

        # --- Intent (endorsement axis; absence is soft) ---
        intent_tok = None
        if intent is None:
            if i_line is None:
                soft.append(f"{rel}: no '## Intent' section — endorsement unstated")
            else:
                soft.append(f"{rel}:{i_line}: '## Intent' section is empty")
        elif _is_menu(intent):
            soft.append(f"{rel}:{i_line}: Intent not chosen (still the template menu)")
        else:
            intent_tok = _first_token(intent)
            if intent_tok not in INTENT_OK:
                hard.append(f"{rel}:{i_line}: Intent {intent!r} is not one of "
                            f"keep | change-planned | tolerated")

        # --- coherence: a superseded decision cannot be kept or migration-planned ---
        if (status_tok == "superseded"
                and intent_tok in {"keep", "change-planned"}):
            hard.append(f"{rel}:{i_line}: Superseded record with Intent={intent_tok!r} "
                        f"— a superseded decision is historical, not kept/change-planned")

        # --- change-planned should link its follow-up (soft) ---
        if intent_tok == "change-planned":
            body_others = re.sub(rf"\bADR-0*{num}\b", "", text)  # ignore self-refs
            if not re.search(r"\bADR-\d+\b", body_others) and "http" not in text:
                soft.append(f"{rel}:{i_line}: Intent=change-planned but no follow-up "
                            f"linked (an ADR-NNNN ref or a URL)")

    return hard, soft


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    if not root.is_dir():
        print(f"decision-records: FAILED:\n  - root {root} is not a directory")
        return 1
    hard, soft = check(root)
    for note in soft:
        print(f"decision-records: note: {note}")
    if hard:
        print("decision-records: FAILED:")
        for h in sorted(set(hard)):
            print(f"  - {h}")
        return 1
    print("decision-records: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
