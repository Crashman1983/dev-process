#!/usr/bin/env python3
"""review gate (core, always-on): make the review-independence attestation a
gated artifact instead of prose.

Review-before-merge is mandatory rule 7 — core, not an optional module — so this
gate always runs. It reads `REVIEW` attestation lines from the journal and
enforces what a language-agnostic CI gate honestly can:

  - HARD: a malformed `REVIEW ` line (grammar, enums, numeric fields) — a
    malformed attestation is silent loss, exactly as for telemetry `GRADE`.
  - HARD (independence arithmetic on a `verdict=pass`): a self-review
    (`non-implementing` absent) or a warm review (`bundle` absent) cannot clear
    Tier 1+; a Tier 3 pass must carry `cross-model` or the explicit
    `single-family` honesty flag.
  - HARD (presence, post-merge, opt-in by tier declaration): an archived plan
    declaring `tier: N` with N >= 2 that carries neither a clearing
    `verdict=pass` REVIEW nor an explicit `review-waived:` line.

It does NOT verify that the reviewer was truthfully a different agent or model —
the gate never sees the review runtime. That claim stays *attested*; SP19 only
makes a weak, absent, or over-claiming attestation *block the merge* rather than
be weighed by a human. Presence is checked against archived plans (a plan is
archived on merge), so the gate never reds CI mid-development and offers a
named-exception escape (`review-waived:`) so it enforces without a footgun.

Pure stdlib. Owns the `REVIEW` grammar; shares nothing with telemetry's `GRADE`.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

JOURNAL_DIR = ".process-work/journal"
PLANS_ARCHIVE = ".process-work/plans/archive"

REQUIRED = {"work", "tier", "reviewer", "model", "independence", "verdict", "round"}
INDEP_TOKENS = {"bundle", "non-implementing", "cross-model", "single-family"}
VERDICTS = {"pass", "block"}
# tolerant of a leading list bullet and **bold**/_emphasis_ on the key, and of
# a trailing annotation — a bulleted `- tier: 3` must not escape the presence
# check (a false-green). Kept identical to the issue gate's plan-field matchers.
_LEAD = r"^\s*(?:[-*+]\s+)?[*_]*"
TIER_DECL = re.compile(_LEAD + r"tier[*_]*\s*:\s*[*_]*\s*(\d+)\b", re.IGNORECASE | re.MULTILINE)
ISSUE_DECL = re.compile(_LEAD + r"issue[*_]*\s*:\s*#?(\d+)\b", re.IGNORECASE | re.MULTILINE)
WAIVED = re.compile(_LEAD + r"review-waived[*_]*\s*:\s*\S", re.IGNORECASE | re.MULTILINE)
DATE_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2}-")


# a REVIEW record may be written as a Markdown bullet — `- REVIEW ...` must
# not silently vanish (audit: the natural journal form was invisible to both
# the parse and the malformed check)
_REVIEW_LINE = re.compile(r"^\s*(?:[-*+]\s+)?[*_]*REVIEW(\s+.*|)$")


def _unfenced(text: str) -> str:
    """Text with fenced blocks (``` and ~~~, each closed by its own marker)
    removed. A `tier:`/`issue:`/`review-waived:` line inside a fenced example
    is a quotation, not a declaration — the same discipline the journal parser
    applies to REVIEW lines."""
    out: list[str] = []
    fence: str | None = None
    for line in text.splitlines():
        stripped = line.strip()
        marker = next((m for m in ("```", "~~~") if stripped.startswith(m)), None)
        if marker and fence is None:
            fence = marker
            continue
        if marker and fence == marker:
            fence = None
            continue
        if fence is None:
            out.append(line)
    return "\n".join(out)


def parse_review_lines(text: str) -> tuple[list[tuple[int, dict]], list[tuple[int, str]]]:
    """Return (records, errors). A record is (lineno, field-dict) for a
    well-formed REVIEW line (optionally bulleted); an error is (lineno,
    message) for a malformed one. Lines inside fenced blocks (``` or ~~~) are
    quotations and are ignored."""
    records: list[tuple[int, dict]] = []
    errors: list[tuple[int, str]] = []
    fence: str | None = None
    for i, raw in enumerate(text.splitlines(), start=1):
        s = raw.strip()
        marker = next((m for m in ("```", "~~~") if s.startswith(m)), None)
        if marker and fence is None:
            fence = marker
            continue
        if marker and fence == marker:
            fence = None
            continue
        if fence is not None:
            continue
        rm = _REVIEW_LINE.match(raw)
        if not rm:
            continue
        toks = rm.group(1).split()
        fields: dict[str, str] = {}
        malformed = None
        for t in toks:
            if "=" not in t:
                malformed = f"token {t!r} is not key=value"
                break
            k, v = t.split("=", 1)
            if not v:
                malformed = f"empty value for {k!r}"
                break
            if k in fields:
                malformed = f"duplicate key {k!r}"
                break
            fields[k] = v
        if malformed:
            errors.append((i, malformed))
            continue
        if set(fields) != REQUIRED:
            missing = REQUIRED - set(fields)
            extra = set(fields) - REQUIRED
            bits = []
            if missing:
                bits.append("missing " + ",".join(sorted(missing)))
            if extra:
                bits.append("unexpected " + ",".join(sorted(extra)))
            errors.append((i, "; ".join(bits)))
            continue
        if not fields["tier"].isdigit() or not fields["round"].isdigit():
            errors.append((i, "tier and round must be integers"))
            continue
        # audit: an out-of-range tier (e.g. tier=4 on the 0-3 scale) both
        # skipped the cross-model check and still cleared a lower plan via
        # `>= tier` — over-declaring must be malformed, not a bypass
        if not 0 <= int(fields["tier"]) <= 3:
            errors.append((i, f"tier {fields['tier']} outside the 0-3 scale"))
            continue
        if fields["verdict"] not in VERDICTS:
            errors.append((i, f"verdict {fields['verdict']!r} not in {sorted(VERDICTS)}"))
            continue
        indep = set(fields["independence"].split(","))
        if not indep <= INDEP_TOKENS:
            bad = ",".join(sorted(indep - INDEP_TOKENS))
            errors.append((i, f"independence has unknown token(s): {bad}"))
            continue
        records.append((i, fields))
    return records, errors


def _arithmetic_violations(rel: str, records: list[tuple[int, dict]]) -> list[str]:
    """The independence arithmetic: a pass verdict may not claim to clear a tier
    its flags do not support."""
    hard: list[str] = []
    for lineno, f in records:
        if f["verdict"] != "pass":
            continue
        tier = int(f["tier"])
        indep = set(f["independence"].split(","))
        if tier >= 1 and "non-implementing" not in indep:
            hard.append(f"{rel}:{lineno}: pass at tier {tier} without 'non-implementing' "
                        f"— the implementer cannot certify its own work at Tier 1+")
        if tier >= 1 and "bundle" not in indep:
            hard.append(f"{rel}:{lineno}: pass at tier {tier} without 'bundle' "
                        f"— Tier 1+ is reviewed from a read-only bundle, not the warm context")
        if tier >= 3 and not (indep & {"cross-model", "single-family"}):
            hard.append(f"{rel}:{lineno}: pass at tier 3 without 'cross-model' or "
                        f"'single-family' — Tier 3 must cross the model family or declare it could not")
    return hard


def _plan_work_ids(stem: str, text: str, *, include_dedated: bool) -> set[str]:
    """The identifiers a REVIEW's `work=` may use to match this plan: the file
    stem, any `issue:` it declares, and — only when it is unique across the
    archive — the stem without its leading date. A de-dated slug shared by two
    archived plans (a feature re-planned on another day) is dropped, so one
    review cannot silently clear both."""
    ids = {stem}
    if include_dedated:
        ids.add(DATE_PREFIX.sub("", stem))
    for m in ISSUE_DECL.finditer(text):
        ids.add(m.group(1))
    return ids


def check(root: Path) -> tuple[list[str], list[str]]:
    hard: list[str] = []
    soft: list[str] = []

    # --- parse all REVIEW attestations from the (recursive) journal ---
    all_records: list[tuple[int, dict]] = []
    jdir = root / JOURNAL_DIR
    if jdir.is_dir():
        for f in sorted(jdir.glob("**/*.md")):
            rel = f"{JOURNAL_DIR}/{f.relative_to(jdir)}"
            try:
                text = f.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                hard.append(f"{rel}: not valid UTF-8")
                continue
            records, errors = parse_review_lines(text)
            for lineno, msg in errors:
                hard.append(f"{rel}:{lineno}: malformed REVIEW line — {msg}")
            hard.extend(_arithmetic_violations(rel, records))
            all_records.extend(records)

    passes = [f for _ln, f in all_records if f["verdict"] == "pass"]

    # --- presence: archived (merged) plans that declare Tier 2+ ---
    adir = root / PLANS_ARCHIVE
    enforced_any = False
    if adir.is_dir():
        plans = [p for p in sorted(adir.glob("*.md")) if not p.name.startswith("design-")]
        # a de-dated slug shared by two archived plans is ambiguous — one review
        # must not clear both, so such slugs are excluded from matching
        dedated_counts: dict[str, int] = {}
        for p in plans:
            key = DATE_PREFIX.sub("", p.stem)
            dedated_counts[key] = dedated_counts.get(key, 0) + 1
        for p in plans:
            text = _unfenced(p.read_text(encoding="utf-8", errors="replace"))
            m = TIER_DECL.search(text)
            if not m:
                soft.append(f"{PLANS_ARCHIVE}/{p.name}: no 'tier:' declaration "
                            f"— review presence not enforced for this plan")
                continue
            tier = int(m.group(1))
            if tier < 2:
                continue
            enforced_any = True
            if WAIVED.search(text):
                continue
            unique = dedated_counts[DATE_PREFIX.sub("", p.stem)] == 1
            ids = _plan_work_ids(p.stem, text, include_dedated=unique)
            cleared = any(f["work"] in ids and int(f["tier"]) >= tier for f in passes)
            if not cleared:
                hard.append(f"{PLANS_ARCHIVE}/{p.name}: archived plan declares tier {tier} "
                            f"but has no clearing REVIEW (verdict=pass, work in {sorted(ids)}, "
                            f"tier>={tier}) and no 'review-waived:' line")

    if not all_records and not enforced_any and not hard:
        soft.append("no REVIEW attestations yet — expected pre-adoption")
    return hard, soft


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    if not root.is_dir():
        print(f"review: FAILED:\n  - root {root} is not a directory")
        return 1
    hard, soft = check(root)
    for note in soft:
        print(f"review: note: {note}")
    if hard:
        print("review: FAILED:")
        for h in sorted(set(hard)):
            print(f"  - {h}")
        return 1
    print("review: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
