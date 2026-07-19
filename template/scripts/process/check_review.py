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
    Tier 2+; a Tier 3 pass must carry `cross-model` or the explicit
    `single-family` honesty flag.
  - HARD (presence, post-merge, opt-in by tier declaration): an archived plan
    declaring `tier: N` with N >= 2 that carries neither a clearing
    `verdict=pass` REVIEW nor an explicit `review-waived:` line.

It does NOT verify that the reviewer was truthfully a different agent or model —
the gate never sees the review runtime. That claim stays *attested*; the gate
only makes a weak, absent, or over-claiming attestation *block the merge* rather
than be weighed by a human. Presence is checked against archived plans (a plan is
archived on merge), so the gate never reds CI mid-development and offers a
named-exception escape (`review-waived:`) so it enforces without a footgun.

Pure stdlib. Owns the `REVIEW` grammar; shares nothing with telemetry's `GRADE`.
"""
from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

JOURNAL_DIR = ".process-work/journal"
PLANS_ACTIVE = ".process-work/plans"
PLANS_ARCHIVE = ".process-work/plans/archive"

LEGACY_REQUIRED = {"work", "tier", "reviewer", "model", "independence", "verdict", "round"}
ARTIFACT_REQUIRED = LEGACY_REQUIRED | {"base", "head", "diff"}
# The bundle imports REQUIRED, so every new review prompt emits artifact-v1.
REQUIRED = ARTIFACT_REQUIRED
INDEP_TOKENS = {"bundle", "non-implementing", "cross-model", "single-family"}
VERDICTS = {"pass", "block"}
# tolerant of a leading list bullet and **bold**/_emphasis_ on the key, and of
# a trailing annotation — a bulleted `- tier: 3` must not escape the presence
# check (a false-green). This gate OWNS the plan-field grammar; the issue gate
# and trace.py import these matchers instead of keeping copies in sync.
_LEAD = r"^\s*(?:[-*+]\s+)?[*_]*"
TIER_DECL = re.compile(_LEAD + r"tier[*_]*\s*:\s*[*_]*\s*(\d+)\b", re.IGNORECASE | re.MULTILINE)
ISSUE_DECL = re.compile(_LEAD + r"issue[*_]*\s*:\s*(\S+)", re.IGNORECASE | re.MULTILINE)
WAIVED = re.compile(_LEAD + r"review-waived[*_]*\s*:\s*\S", re.IGNORECASE | re.MULTILINE)
REVIEW_BINDING_DECL = re.compile(
    _LEAD + r"review-binding[*_]*\s*:\s*[*_]*\s*(\S+)",
    re.IGNORECASE | re.MULTILINE,
)
DATE_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2}-")
GIT_SHA = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")

# issue-ref grammar — owned here (core) so both this gate and the issue gate
# read the same shapes; only these count as issue declarations
_BARE = re.compile(r"^#(\d+)$")
_CROSS = re.compile(r"^([\w.-]+/[\w.-]+)#(\d+)$")
_URL = re.compile(r"^https://github\.com/([\w.-]+/[\w.-]+)/issues/(\d+)$")


def parse_issue_ref(ref: str) -> tuple[str | None, int] | None:
    """(repo_or_None, number) for a well-formed ref, else None. repo is None
    only for the bare `#N` form, which resolves against the configured repo."""
    for pat, has_repo in ((_BARE, False), (_CROSS, True), (_URL, True)):
        m = pat.match(ref)
        if m:
            return (m.group(1), int(m.group(2))) if has_repo else (None, int(m.group(1)))
    return None


# a REVIEW record may be written as a Markdown bullet — `- REVIEW ...` must
# not silently vanish (audit: the natural journal form was invisible to both
# the parse and the malformed check)
_REVIEW_LINE = re.compile(r"^\s*(?:[-*+]\s+)?[*_]*REVIEW(\s+.*|)$")


_FENCE_RUN = re.compile(r"^(`{3,}|~{3,})")


def _fence_marker(line: str) -> str | None:
    """The fence run (``` or ~~~, any length >= 3) opening this line, if any."""
    m = _FENCE_RUN.match(line.strip())
    return m.group(1) if m else None


def _fence_closes(fence: str, marker: str) -> bool:
    """CommonMark: a fence closes only on a run of the SAME character at least
    as long as the opener — a ``` inside a ````-fenced example must not close
    it early, or quoted `review-waived:`/`tier:` lines leak out (false-green)."""
    return marker[0] == fence[0] and len(marker) >= len(fence)


def _unfenced(text: str) -> str:
    """Text with fenced blocks (``` and ~~~, each closed by its own,
    length-aware marker) removed. A `tier:`/`issue:`/`review-waived:` line
    inside a fenced example is a quotation, not a declaration — the same
    discipline the journal parser applies to REVIEW lines."""
    out: list[str] = []
    fence: str | None = None
    for line in text.splitlines():
        marker = _fence_marker(line)
        if marker and fence is None:
            fence = marker
            continue
        if marker and fence is not None and _fence_closes(fence, marker):
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
        marker = _fence_marker(raw)
        if marker and fence is None:
            fence = marker
            continue
        if marker and fence is not None and _fence_closes(fence, marker):
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
        shape = set(fields)
        shape_key = frozenset(shape)
        if shape_key not in {frozenset(LEGACY_REQUIRED), frozenset(ARTIFACT_REQUIRED)}:
            expected = ARTIFACT_REQUIRED if shape & {"base", "head", "diff"} else LEGACY_REQUIRED
            missing = expected - shape
            extra = shape - expected
            bits = []
            if missing:
                bits.append("missing " + ",".join(sorted(missing)))
            if extra:
                bits.append("unexpected " + ",".join(sorted(extra)))
            errors.append((i, "; ".join(bits)))
            continue
        if shape == ARTIFACT_REQUIRED:
            for key in ("base", "head"):
                if not GIT_SHA.fullmatch(fields[key]):
                    errors.append((i, f"{key} must be a 40- or 64-character lowercase Git SHA"))
                    malformed = key
                    break
            if malformed:
                continue
            if not SHA256.fullmatch(fields["diff"]):
                errors.append((i, "diff must be a 64-character lowercase SHA-256"))
                continue
        # isascii guards unicode digits ("²"): isdigit() is True but int() raises
        # — the same trap telemetry's GRADE round check already names
        if not (fields["tier"].isascii() and fields["tier"].isdigit()) or \
                not (fields["round"].isascii() and fields["round"].isdigit()):
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
        # bundle/non-implementing is the Tier-2 floor: Tier 0-1 is a self-check
        # (Quick flow reviews itself), Tier 2 is the first tier with a fresh
        # read-only-bundle review — verification-independence.md
        if tier >= 2 and "non-implementing" not in indep:
            hard.append(f"{rel}:{lineno}: pass at tier {tier} without 'non-implementing' "
                        f"— the implementer cannot certify its own work at Tier 2+")
        if tier >= 2 and "bundle" not in indep:
            hard.append(f"{rel}:{lineno}: pass at tier {tier} without 'bundle' "
                        f"— Tier 2+ is reviewed from a read-only bundle, not the warm context")
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
        # only a real issue ref may act as a clearing work-id — `issue: v2.0`
        # or `issue: none` must not let an unrelated REVIEW clear this plan
        # (and `none` twice would let ONE review clear two plans)
        tok = m.group(1)
        if tok.isascii() and tok.isdigit():
            ids.add(tok)  # bare number, the historical form
            continue
        parsed = parse_issue_ref(tok)
        if parsed is not None:
            ids.add(tok)
            ids.add(str(parsed[1]))  # `work=42` matches `issue: owner/repo#42`
    return ids


@dataclass(frozen=True)
class ReviewCertificate:
    commit: str
    parents: tuple[str, ...]
    tree: str
    lineno: int
    fields: dict[str, str]


def _git_text(root: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout if result.returncode == 0 else None


def _git_bytes(root: Path, *args: str) -> bytes | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout if result.returncode == 0 else None


def _commit_review_records(
    root: Path,
) -> tuple[list[tuple[str, list[tuple[int, dict]]]], list[ReviewCertificate], list[str]]:
    """Read REVIEW records from commit bodies in one bounded Git invocation."""
    raw = _git_text(root, "log", "--format=%x1e%H%x00%P%x00%T%x00%B")
    if raw is None:
        return [], [], []  # pre-adoption/non-Git renders keep the legacy path
    groups: list[tuple[str, list[tuple[int, dict]]]] = []
    certificates: list[ReviewCertificate] = []
    hard: list[str] = []
    for chunk in raw.split("\x1e"):
        chunk = chunk.lstrip("\n")
        if not chunk.strip():
            continue
        parts = chunk.split("\x00", 3)
        if len(parts) != 4:
            hard.append("git history: could not parse commit metadata for REVIEW records")
            continue
        commit, parent_text, tree, body = parts
        records, errors = parse_review_lines(body)
        source = f"commit {commit}"
        for lineno, message in errors:
            hard.append(f"{source}:{lineno}: malformed REVIEW line — {message}")
        if records:
            groups.append((source, records))
        parents = tuple(parent_text.split())
        for lineno, fields in records:
            if set(fields) == ARTIFACT_REQUIRED:
                certificates.append(
                    ReviewCertificate(commit, parents, tree, lineno, fields)
                )
    return groups, certificates, hard


def _commit_exists(root: Path, sha: str) -> bool:
    return _git_bytes(root, "cat-file", "-e", f"{sha}^{{commit}}") == b""


def _diff_digest(root: Path, base: str, head: str) -> str | None:
    diff = _git_bytes(root, "diff", "--binary", f"{base}...{head}")
    return hashlib.sha256(diff).hexdigest() if diff is not None else None


def _validated_certificates(
    root: Path, certificates: list[ReviewCertificate]
) -> tuple[list[ReviewCertificate], list[str]]:
    valid: list[ReviewCertificate] = []
    hard: list[str] = []
    for certificate in certificates:
        fields = certificate.fields
        source = f"commit {certificate.commit}:{certificate.lineno}"
        missing = [sha for sha in (fields["base"], fields["head"])
                   if not _commit_exists(root, sha)]
        if missing:
            hard.append(f"{source}: review artifact commit(s) do not resolve: {', '.join(missing)}")
            continue
        if len(certificate.parents) != 1 or certificate.parents[0] != fields["head"]:
            hard.append(f"{source}: certificate parent must equal reviewed head {fields['head']}")
            continue
        head_tree = _git_text(root, "rev-parse", f"{fields['head']}^{{tree}}")
        if head_tree is None or certificate.tree != head_tree.strip():
            hard.append(f"{source}: certificate commit must be tree-empty relative to reviewed head")
            continue
        actual = _diff_digest(root, fields["base"], fields["head"])
        if actual is None:
            hard.append(f"{source}: review artifact diff could not be computed")
            continue
        if actual != fields["diff"]:
            hard.append(
                f"{source}: review artifact digest mismatch: "
                f"expected {fields['diff']}, actual {actual}"
            )
            continue
        valid.append(certificate)
    return valid, hard


def _protected_target(target: str | None) -> bool:
    return target in {"main", "master", "refs/heads/main", "refs/heads/master"}


def _candidate_bound_plans(root: Path, base: str) -> tuple[list[Path], str | None]:
    names = _git_text(
        root,
        "diff",
        "--name-only",
        "--diff-filter=AMR",
        f"{base}...HEAD",
        "--",
        PLANS_ARCHIVE,
    )
    if names is None:
        return [], f"candidate base {base} does not resolve or diff could not be computed"
    plans: list[Path] = []
    for name in names.splitlines():
        path = root / name
        if not path.is_file() or path.name.startswith("design-"):
            continue
        text = _unfenced(path.read_text(encoding="utf-8", errors="replace"))
        match = REVIEW_BINDING_DECL.search(text)
        if match and match.group(1) == "artifact-v1":
            plans.append(path)
    return plans, None


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
            except OSError as exc:  # broken symlink, directory named *.md, …
                hard.append(f"{rel}: could not read: {exc}")
                continue
            records, errors = parse_review_lines(text)
            for lineno, msg in errors:
                hard.append(f"{rel}:{lineno}: malformed REVIEW line — {msg}")
            hard.extend(_arithmetic_violations(rel, records))
            all_records.extend(records)

    commit_groups, certificates, commit_hard = _commit_review_records(root)
    hard.extend(commit_hard)
    for source, records in commit_groups:
        hard.extend(_arithmetic_violations(source, records))
        all_records.extend(records)
    valid_certificates, certificate_hard = _validated_certificates(root, certificates)
    hard.extend(certificate_hard)

    passes = [f for _ln, f in all_records if f["verdict"] == "pass"]
    bound_passes = [certificate.fields for certificate in valid_certificates
                    if certificate.fields["verdict"] == "pass"]

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
            try:
                text = _unfenced(p.read_text(encoding="utf-8", errors="replace"))
            except OSError as exc:  # broken symlink, directory named *.md, …
                hard.append(f"{PLANS_ARCHIVE}/{p.name}: could not read: {exc}")
                continue
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
            binding_match = REVIEW_BINDING_DECL.search(text)
            binding = binding_match.group(1) if binding_match else None
            if binding and binding != "artifact-v1":
                hard.append(f"{PLANS_ARCHIVE}/{p.name}: unknown review-binding {binding!r}")
                continue
            unique = dedated_counts[DATE_PREFIX.sub("", p.stem)] == 1
            ids = _plan_work_ids(p.stem, text, include_dedated=unique)
            eligible = bound_passes if binding == "artifact-v1" else passes
            cleared = any(f["work"] in ids and int(f["tier"]) >= tier for f in eligible)
            if not cleared:
                if binding == "artifact-v1":
                    hard.append(
                        f"{PLANS_ARCHIVE}/{p.name}: review-binding artifact-v1 requires "
                        f"a valid tree-empty certificate commit (verdict=pass, "
                        f"work in {sorted(ids)}, tier>={tier}); journal records do not clear it"
                    )
                else:
                    hard.append(f"{PLANS_ARCHIVE}/{p.name}: archived plan declares tier {tier} "
                                f"but has no clearing REVIEW (verdict=pass, work in {sorted(ids)}, "
                                f"tier>={tier}) and no 'review-waived:' line")

    candidate_target = os.environ.get("DEV_PROCESS_CANDIDATE_TARGET")
    candidate_base = os.environ.get("DEV_PROCESS_CANDIDATE_BASE")
    if _protected_target(candidate_target):
        if not candidate_base:
            hard.append("protected candidate target has no DEV_PROCESS_CANDIDATE_BASE")
        else:
            candidate_plans, candidate_error = _candidate_bound_plans(root, candidate_base)
            if candidate_error:
                hard.append(candidate_error)
            elif len(candidate_plans) > 1:
                rels = sorted(str(path.relative_to(root)) for path in candidate_plans)
                hard.append(
                    "candidate contains multiple newly archived artifact-v1 plans; "
                    f"integrate and push one reviewed slice at a time: {rels}"
                )
            elif candidate_plans:
                plan = candidate_plans[0]
                text = _unfenced(plan.read_text(encoding="utf-8", errors="replace"))
                tier_match = TIER_DECL.search(text)
                tier = int(tier_match.group(1)) if tier_match else 0
                ids = _plan_work_ids(plan.stem, text, include_dedated=True)
                matching = [f for f in bound_passes
                            if f["work"] in ids and int(f["tier"]) >= tier]
                actual = _diff_digest(root, candidate_base, "HEAD")
                if actual is None:
                    hard.append(
                        f"candidate diff {candidate_base}...HEAD could not be computed"
                    )
                elif not any(fields["diff"] == actual for fields in matching):
                    expected = sorted({fields["diff"] for fields in matching})
                    hard.append(
                        f"candidate digest {actual} does not match certified digest(s) "
                        f"for {plan.relative_to(root)}: {expected or ['none']}"
                    )

    # active Tier 2+ plans are not presence-checked (by design: no red CI
    # mid-development) — but "forgot to archive on merge" and that design are
    # indistinguishable and silent, so the gap is at least made visible
    pdir = root / PLANS_ACTIVE
    if pdir.is_dir():
        active = 0
        for p in sorted(pdir.glob("*.md")):
            if p.name.startswith("design-"):
                continue
            try:
                text = _unfenced(p.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue  # active plans are not enforced; the archive path diagnoses
            m = TIER_DECL.search(text)
            if m and int(m.group(1)) >= 2:
                active += 1
        if active:
            soft.append(f"{active} active Tier 2+ plan(s) in {PLANS_ACTIVE} — "
                        f"review presence is only enforced once a plan is "
                        f"archived (the merge step); archive on merge")

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
