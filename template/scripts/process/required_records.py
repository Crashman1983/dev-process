#!/usr/bin/env python3
"""required_records — one table for "this work owes a record", read by attest
(refuse), the review gate (presence) and the review bundle (list) alike.

A rule that only printed a warning was a rule nobody had to follow: downstream
(Kenni, dev-process #277 step 0), seven of twenty findings where a check never
took effect were rules that existed in prose — refute from Tier 3, a root cause
after a fix streak, an owner's word behind `review-waived:` — while the
mechanics printed text. For gate code attest already had the right shape: the
record, or a reasoned `skipped <kind> work=<id>: <reason>`, and nothing else
passes. This table generalizes that one shape (#282).

A row: {"kind": <record kind>, "when": {<fact>: <value>, ...}, "skippable": bool}.
Facts, all of a row's `when` must hold — an int fact is a threshold (the work's
value is at least the row's), a bool fact is equal; the type comes from FACTS, so
a new int fact cannot fall back to equality and owe its record at one value only:
  tier_from      int   the work's tier
  gate_code      bool  the reviewed diff changes gate code (check_review.is_gate_path)
  fix_streak     int   the fix commits on one file in the range
  blocked_rounds int   the blocked code rounds the branch adds (attest_evidence)
  waived         bool  the plan carries a `review-waived:` line
Kinds and the record that satisfies them:
  refute          `REFUTE work=<id> round=<n>: …`
  root-cause      `ROOT-CAUSE work=<id> round=<n>: …`
  replan          per blocked round after the first, `REPLAN work=<id> round=<r>:
                  increment|rebuild — <why>` in the plan (mandatory rule 4)
  class-test      per blocked round, `ROOT-CAUSE work=<id> round=<r>: <cause> —
                  sites: <sites> — <tests>` naming a test that stands at head, or
                  `sites: none — <reason>` for a round without a code defect
  owner-decision  `DECISION <date> owner: …`  (never skippable: a skip of the
                  owner's word would be the agent's word again)

The template's rows live in `review_evidence.required_records`
(`model-policy.json`); a project appends its own under
`review_evidence.required_records_extra` (`model-policy.local.json`) — read at
the reviewed base like every evidence rule, so a branch cannot lift its own
duty. Stdlib only.
"""
from __future__ import annotations

from dataclasses import dataclass

KINDS = ("refute", "root-cause", "replan", "class-test", "owner-decision")
UNSKIPPABLE = frozenset({"owner-decision"})
FACTS = {"tier_from": int, "gate_code": bool, "fix_streak": int, "blocked_rounds": int, "waived": bool}


@dataclass(frozen=True)
class Owed:
    kind: str
    why: str          # the facts that made it owed, for the message
    skippable: bool


def rows_problem(rows: object) -> str | None:
    """Why `rows` is no valid table, or None."""
    if not isinstance(rows, list):
        return "must be a list of rows"
    for i, row in enumerate(rows):
        if not isinstance(row, dict) or set(row) - {"kind", "when", "skippable", "_comment"}:
            return f"row {i}: an object with kind, when and optionally skippable"
        if row.get("kind") not in KINDS:
            return f"row {i}: kind must be one of {', '.join(KINDS)}, got {row.get('kind')!r}"
        when = row.get("when")
        if not isinstance(when, dict) or not when or set(when) - set(FACTS):
            return f"row {i}: when must name at least one of {', '.join(FACTS)}"
        for key, value in when.items():
            want = FACTS[key]
            if not isinstance(value, want) or (want is int and isinstance(value, bool)):
                return f"row {i}: when.{key} must be {want.__name__}, got {value!r}"
        if "waived" in when and row["kind"] != "owner-decision":
            # only the gate reads a waived plan, and it asks for the owner's word alone: any
            # other kind on `waived` would be owed by nobody
            return f"row {i}: when.waived is read for owner-decision only, not {row['kind']}"
        if "skippable" in row and not isinstance(row["skippable"], bool):
            return f"row {i}: skippable must be true or false"
        if row.get("skippable") and row["kind"] in UNSKIPPABLE:
            return f"row {i}: {row['kind']} cannot be skipped"
    return None


def _holds(when: dict, facts: dict) -> bool | None:
    """Do all of `when` hold? None: a fact it needs is unknown (git could not tell).
    An int fact of FACTS is a threshold, a bool fact equality (True >= False is no rule)."""
    unknown = False
    for key, want in when.items():
        have = facts.get(key)
        if have is None:
            unknown = True
            continue
        if FACTS.get(key) is int:
            if have < want:
                return False
        elif have != want:
            return False
    return None if unknown else True


def owed(rows: list[dict], facts: dict, present: set[str], skipped: set[str]) -> tuple[list[Owed], list[str]]:
    """(the records still owed, the rows a missing fact left undecided).

    `present`: kinds whose record the work carries; `skipped`: kinds with a bound
    `skipped <kind>` line. An undecided row is no pass — the caller refuses on it
    unless the record is there anyway (fail closed)."""
    out: list[Owed] = []
    undecided: list[str] = []
    seen: set[str] = set()
    for row in rows:
        kind = row["kind"]
        holds = _holds(row["when"], facts)
        if holds is False or kind in present or kind in seen:
            continue
        skippable = row.get("skippable", kind not in UNSKIPPABLE)
        if skippable and kind in skipped:
            continue
        why = ", ".join(f"{k}={v}" for k, v in row["when"].items())
        if holds is None:
            undecided.append(f"{kind} ({why}: unknown)")
            continue
        seen.add(kind)
        out.append(Owed(kind, why, skippable))
    return out, undecided


def table(rules: dict) -> list[dict]:
    """The rows in force: the template's, then the project's extra ones."""
    return [*rules.get("required_records", []), *rules.get("required_records_extra", [])]
