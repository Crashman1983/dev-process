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
  - HARD on the merge push only (presence, push-anchored): an ACTIVE plan
    declaring `tier: 3` that this push carries (its file is in the pushed
    range, or a pushed commit claims its issue via a closing trailer or a
    `(#N)` subject) without a clearing pass or waiver. Waiting for the
    archive step means the proof arrives after the merge it was meant to
    gate. "Merge push" is read from the environment (`PROCESS_PUSH_TARGETS`,
    or the pre-commit framework's `PRE_COMMIT_REMOTE_BRANCH`): hard when a
    target ref is main/master, the same findings as notes anywhere else —
    a gate that reds the wrong push gets bypassed, and a bypassed gate
    proves nothing.
  - HARD (integrity, opt-in by carrying the fields): a REVIEW that names
    `base`/`head`/`diff` binds itself to an exact reviewed diff — the gate
    recomputes the digest and fails on mismatch or unresolvable commits. The
    review bundle prints the three values (`REVIEW_ARTIFACT` line) so the
    reviewer copies, never invents, them.

Lean pass: the former artifact-v1 mode (tree-empty certificate commits,
candidate-target binding, two attestation modes) is retired — the optional
digest above keeps the diff-exact guarantee at a fraction of the ritual. A
plan's `review-binding:` line is reported as retired, never silently ignored.

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
from pathlib import Path

JOURNAL_DIR = ".process-work/journal"
PLANS_ACTIVE = ".process-work/plans"
PLANS_ARCHIVE = ".process-work/plans/archive"

REQUIRED = {"work", "tier", "reviewer", "model", "independence", "verdict", "round"}
# optional integrity fields — all three or none (a partial claim is malformed)
ARTIFACT_FIELDS = {"base", "head", "diff"}
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
RETIRED_BINDING = re.compile(_LEAD + r"review-binding[*_]*\s*:", re.IGNORECASE | re.MULTILINE)
DATE_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2}-")
# a waiver is an honest degradation — but a degradation without an owner
# becomes the new normal. The debt marker is an issue ref (#N) or a URL on
# the waiver line itself. Soft everywhere: the waiver stays valid, the
# missing owner is named. One owner for the notion; the speckit and issues
# gates import this instead of keeping copies.
_WAIVER_DEBT = re.compile(r"#\d+|https?://")


def waiver_debt_notes(rel: str, text: str, pattern: re.Pattern[str],
                      label: str) -> list[str]:
    """One note per waiver line that names no issue/URL owner. A plan that
    declares its tracking issue (`issue: #N`) already has an owner — the
    waiver is recorded where the work is tracked — so only waivers in
    plans without ANY issue anchor are flagged."""
    if any(parse_issue_ref(m.group(1)) or m.group(1).isdigit()
           for m in ISSUE_DECL.finditer(text)):
        return []
    notes = []
    for line in text.splitlines():
        if pattern.search(line) and not _WAIVER_DEBT.search(line):
            notes.append(f"{rel}: '{label}:' without an issue ref — a "
                         f"degradation is a debt with an owner; link #N (or a "
                         f"URL) on the waiver line, or declare the plan's "
                         f"'issue:' link")
    return notes
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
        artifact = shape & ARTIFACT_FIELDS
        expected = REQUIRED | (ARTIFACT_FIELDS if artifact else set())
        if shape != expected:
            missing = expected - shape
            extra = shape - expected
            bits = []
            if missing:
                bits.append("missing " + ",".join(sorted(missing)))
            if extra:
                bits.append("unexpected " + ",".join(sorted(extra)))
            errors.append((i, "; ".join(bits)))
            continue
        if artifact:
            bad = None
            for key in ("base", "head"):
                if not GIT_SHA.fullmatch(fields[key]):
                    errors.append((i, f"{key} must be a 40- or 64-character lowercase Git SHA"))
                    bad = key
                    break
            if bad:
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
            bad_tok = ",".join(sorted(indep - INDEP_TOKENS))
            errors.append((i, f"independence has unknown token(s): {bad_tok}"))
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


# --- the review artifact digest: ONE formula, pinned against git config -----
# Producer (make_review_bundle), writer (attest.py) and verifier (this gate)
# must compute the same bytes on every clone. `git diff` output depends on
# user/repo config — diff.algorithm, diff.renames, diff.noprefix,
# diff.mnemonicPrefix, core.abbrev (index lines), external diff drivers,
# textconv — so a digest computed on one machine can honestly fail on another
# (observed downstream: an attest at core.abbrev=9 red-ed a fresh clone at 7).
# The canonical form pins every knob on the command line. Legacy digests
# (plain `git diff --binary`, produced before the pin) stay verifiable.
CANONICAL_DIFF = (
    "-c", "diff.algorithm=myers", "-c", "diff.renames=false",
    "-c", "diff.noprefix=false", "-c", "diff.mnemonicPrefix=false",
    "-c", "diff.context=3", "-c", "diff.suppressBlankEmpty=false",
    "-c", "core.quotePath=true",
    "diff", "--binary", "--full-index", "--no-color", "--no-ext-diff",
    "--no-textconv", "--no-renames",
)


def artifact_diff(root: Path, base: str, head: str) -> bytes | None:
    """The exact bytes the digest is computed from: the canonical three-dot
    diff `base...head` (what the branch adds over the merge base)."""
    return _git_bytes(root, *CANONICAL_DIFF, f"{base}...{head}")


def artifact_digest(root: Path, base: str, head: str) -> str | None:
    diff = artifact_diff(root, base, head)
    return hashlib.sha256(diff).hexdigest() if diff is not None else None


def _legacy_digests(root: Path, base: str, head: str) -> set[str]:
    """Digests older records may carry: the unpinned `git diff --binary` in
    both range forms, as this clone's config renders them today."""
    out: set[str] = set()
    for rng in (f"{base}...{head}", f"{base}..{head}"):
        diff = _git_bytes(root, "diff", "--binary", rng)
        if diff is not None:
            out.add(hashlib.sha256(diff).hexdigest())
    return out


def _integrity_violations(rel: str, root: Path,
                          records: list[tuple[int, dict]]) -> tuple[list[str], list[str]]:
    """A REVIEW carrying base/head/diff binds itself to an exact diff — verify
    the claim where it CAN be verified. A mismatched digest is hard: the
    bound artifact provably differs from what was reviewed. Commits that do
    not resolve in THIS clone are a note, not a failure: after a rebase-merge
    plus branch deletion the pre-merge SHAs legitimately exist in no fresh
    clone, and hard-failing there would red every clone retroactively for
    every properly bound historical review (observed in production). The
    binding did its job at merge time; a later clone that cannot re-check it
    says so honestly instead of crying wolf."""
    hard: list[str] = []
    soft: list[str] = []
    for lineno, f in records:
        if "diff" not in f:
            continue
        missing = [sha for sha in (f["base"], f["head"])
                   if _git_bytes(root, "cat-file", "-e", f"{sha}^{{commit}}") is None]
        if missing:
            soft.append(f"{rel}:{lineno}: review artifact commit(s) not present "
                        f"in this clone ({', '.join(missing)}) — digest "
                        f"unverifiable here (pre-merge SHAs gone after "
                        f"rebase-merge + branch delete); verified at merge "
                        f"time or not at all")
            continue
        actual = artifact_digest(root, f["base"], f["head"])
        if actual is None:
            hard.append(f"{rel}:{lineno}: review artifact diff could not be computed")
            continue
        if f["diff"] == actual or f["diff"] in _legacy_digests(root, f["base"], f["head"]):
            continue
        # neither the canonical nor any legacy formula produces this value:
        # no byte stream of this diff hashes to it. Observed downstream: 15
        # of 16 recorded digests matched no commit within five days — they
        # were typed to look right, never computed. Name it as what it is.
        hard.append(f"{rel}:{lineno}: review artifact digest {f['diff'][:12]}… "
                    f"matches no formula for {f['base'][:9]}...{f['head'][:9]} "
                    f"(canonical {actual[:12]}…) — no byte stream of this diff "
                    f"produces it; a digest that was typed rather than computed "
                    f"is a FABRICATED attestation, and this review counts as "
                    f"absent. Write REVIEW lines with scripts/process/attest.py, "
                    f"which computes the digest itself")
    return hard, soft


def _cleared(passes: list[dict], ids: set[str], tier: int) -> bool:
    """Does any pass clear a plan of this tier? The REVIEW grammar caps tier
    at 3 — a plan on an extended downstream scale (tier 4/5) clears at the
    gated ceiling, not an unmeetable bar."""
    req = min(tier, 3)
    return any(r["work"] in ids and int(r["tier"]) >= req for r in passes)


# --- push anchoring: what THIS push carries ---------------------------------
INTEGRATION_REFS = ("origin/main", "origin/master", "main", "master")
INTEGRATION_TARGET_REFS = ("refs/heads/main", "refs/heads/master")
# the remote refs a push lands on. A hook exports PROCESS_PUSH_TARGETS from
# what git hands it on stdin (`<local_ref> <local_sha> <remote_ref>
# <remote_sha>`); the pre-commit framework sets PRE_COMMIT_REMOTE_BRANCH for
# its pre-push stage without any wiring — both are read, the explicit one first
PUSH_TARGETS_ENV = "PROCESS_PUSH_TARGETS"
PRE_COMMIT_TARGET_ENV = "PRE_COMMIT_REMOTE_BRANCH"
# The issue numbers a push CLAIMS, not every `#N` it mentions. A cross-reference
# ("see #1288", "Merge pull request #1589") claims nothing — read as a claim it
# makes a foreign Tier 3 plan this push's proof to produce and reds a branch that
# has nothing to do with it. Two forms count: a GitHub closing trailer anywhere
# in the message, and the `… (#N)` subject convention.
_ISSUE_CLOSING = re.compile(
    r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s*:?\s+#(\d+)\b", re.IGNORECASE)
_ISSUE_SUBJECT = re.compile(r"\(#(\d+)\)\s*$")


def integration_push(env: dict[str, str] | None = None) -> tuple[bool, str]:
    """(is this push a merge?, why not) — the switch between hard and note.

    The push-anchored arms promise something that hangs on the MERGE, not on
    every push: a worker pushes its feature branch while the review is still
    ahead of it (the attestation is written later, from the bundle). Blocking
    that push is a chicken-and-egg. So: hard only when a target ref is an
    integration branch, otherwise the same findings as notes.

    No variable at all (a manual run, CI) is deliberately the soft side: the
    gate cannot know where the work would land, and guessing "merge" would
    red every local run. The known limitation: a PR merged server-side never
    pushes main from a clone, so this switch never fires for that route —
    there, finish.py (run before the PR) is the stop, and the archive arm
    above catches the residue on main."""
    source = os.environ if env is None else env
    raw = source.get(PUSH_TARGETS_ENV, "") or source.get(PRE_COMMIT_TARGET_ENV, "")
    targets = raw.split()
    if not targets:
        return False, (f"no push target known ({PUSH_TARGETS_ENV} unset) — hard "
                       f"only on a push to main/master")
    if any(t in INTEGRATION_TARGET_REFS for t in targets):
        return True, ""
    return False, (f"push targets {' '.join(targets)}, no integration branch — "
                   f"the proof is due on the merge push")


def merge_base(root: Path) -> str | None:
    """The commit the pushed range starts at, resolved offline. Tries the
    integration branches in order, then falls back to HEAD~1. None means
    "cannot tell", never "nothing to check": callers degrade to the
    plan-anchored arms rather than reddening a clone without an integration
    ref (a fresh shallow checkout, a differently named default branch)."""
    for ref in INTEGRATION_REFS:
        out = _git_bytes(root, "merge-base", "HEAD", ref)
        if out is not None and out.strip():
            return out.decode(errors="replace").strip()
    out = _git_bytes(root, "rev-parse", "HEAD~1")
    if out is not None and out.strip():
        return out.decode(errors="replace").strip()
    return None


def issue_refs_in_range(root: Path) -> set[int]:
    """The issue numbers the commits since the merge-base CLAIM as their own
    (`_ISSUE_CLOSING`, `_ISSUE_SUBJECT`) — read from the local repo only, so
    the gate stays offline like its neighbours. A plan is this push's
    business when the push carries its file (`paths_in_flight`) or claims
    its issue here; both arms mean the same thing by "this push's proof"."""
    base = merge_base(root)
    if base is None:
        return set()
    out = _git_bytes(root, "log", "--format=%B%x00", f"{base}..HEAD")
    if out is None:
        return set()
    refs: set[int] = set()
    for message in out.decode(errors="replace").split("\0"):
        body = message.strip()
        if not body:
            continue
        refs |= {int(n) for n in _ISSUE_CLOSING.findall(body)}
        refs |= {int(n) for n in _ISSUE_SUBJECT.findall(body.splitlines()[0])}
    return refs


def paths_in_flight(root: Path) -> set[str]:
    """Repo-relative paths this push carries: the committed range
    `{base}...HEAD`, nothing else. An unscoped "every active Tier 3 plan"
    reds every push in the repo for a plan the pusher does not own (measured
    downstream: a committed decision paper, tier 3, deliberately unimplemented,
    blocked an unrelated branch). Untracked, staged and modified files are
    deliberately NOT in flight: a push transports commits, and an uncommitted
    plan draft travels with nothing. `--no-optional-locks`: a gate must never
    take `index.lock` out from under a concurrent commit."""
    base = merge_base(root)
    if base is None:
        return set()
    out = _git_bytes(root, "--no-optional-locks", "diff", "--name-only",
                     f"{base}...HEAD")
    if out is None:
        return set()
    return {line.strip() for line in out.decode(errors="replace").splitlines()
            if line.strip()}


def _plan_issue_numbers(text: str) -> set[int]:
    """The issue numbers a plan declares — the join between a pushed commit
    and the tier only the plan knows."""
    numbers: set[int] = set()
    for m in ISSUE_DECL.finditer(text):
        tok = m.group(1)
        if tok.isascii() and tok.isdigit():
            numbers.add(int(tok))
            continue
        parsed = parse_issue_ref(tok)
        if parsed is not None:
            numbers.add(parsed[1])
    return numbers


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


SPECS_DIR = "specs"
UNCHECKED = re.compile(r"^\s*- \[ \] ", re.MULTILINE)
DECISIONS_HEADING = re.compile(r"^#{2,4}\s+Decisions\b", re.IGNORECASE | re.MULTILINE)


def speckit_unreviewed(root: Path, passes: list[dict]) -> list[tuple[str, int, set[str]]]:
    """Spec-dir plans past the review-presence gate's blind spot: the speckit
    path keeps its plan in specs/<dir>/plan.md and never archives it, so the
    archived-plan scan cannot see it. The completion signal there is the
    fully-ticked tasks.md. Returns (dir name, tier, matching work ids) for
    every spec dir whose tasks are all ticked, whose plan declares tier >= 2
    without a review-waived line, and which no clearing pass covers. One
    owner: finish.py blocks on this at the merge ritual; the review gate
    reports it as a note (a hard gate would red every push between the last
    tick and the review that must follow it)."""
    out: list[tuple[str, int, set[str]]] = []
    sdir = root / SPECS_DIR
    if not sdir.is_dir():
        return out
    for d in sorted(p for p in sdir.iterdir() if p.is_dir()):
        plan, tasks = d / "plan.md", d / "tasks.md"
        if not plan.is_file() or not tasks.is_file():
            continue
        ttext = tasks.read_text(encoding="utf-8", errors="replace")
        if UNCHECKED.search(ttext) or not re.search(r"^\s*- \[[xX]\] ", ttext,
                                                    re.MULTILINE):
            continue  # in flight, or no checkbox grammar at all
        ptext = _unfenced(plan.read_text(encoding="utf-8", errors="replace"))
        m = TIER_DECL.search(ptext)
        if not m or int(m.group(1)) < 2 or WAIVED.search(ptext):
            continue
        tier = int(m.group(1))
        # the REVIEW grammar caps tier at 3 — a plan on an extended downstream
        # scale (tier 4/5) clears at the gated ceiling, not an unmeetable bar
        req = min(tier, 3)
        ids = _plan_work_ids(d.name, ptext, include_dedated=False)
        if not any(r["work"] in ids and int(r["tier"]) >= req for r in passes):
            out.append((d.name, tier, ids))
    return out


def check(root: Path) -> tuple[list[str], list[str]]:
    hard: list[str] = []
    soft: list[str] = []

    # the push-anchored arms below are the merge's condition, not every
    # push's — see integration_push()
    to_integration, not_a_merge = integration_push()

    def presence(finding: str) -> None:
        """A push-anchored presence finding: hard on the merge push, a
        visible note anywhere else."""
        if to_integration:
            hard.append(finding)
        else:
            soft.append(f"{finding} [note only: {not_a_merge}]")

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
            ih, isoft = _integrity_violations(rel, root, records)
            hard.extend(ih)
            soft.extend(isoft)
            all_records.extend(records)

    passes = [f for _ln, f in all_records if f["verdict"] == "pass"]

    # --- presence: archived (merged) plans that declare Tier 2+ ---
    adir = root / PLANS_ARCHIVE
    enforced_any = False
    # a de-dated slug shared by two archived plans is ambiguous — one review
    # must not clear both, so such slugs are excluded from matching
    dedated_counts: dict[str, int] = {}
    # (rel, text, tier, work ids) of every tiered plan — the join the
    # commit-anchored arm below needs
    tiered_plans: list[tuple[str, str, int, set[str]]] = []
    if adir.is_dir():
        plans = [p for p in sorted(adir.glob("*.md")) if not p.name.startswith("design-")]
        for p in plans:
            key = DATE_PREFIX.sub("", p.stem)
            dedated_counts[key] = dedated_counts.get(key, 0) + 1
        for p in plans:
            try:
                text = _unfenced(p.read_text(encoding="utf-8", errors="replace"))
            except OSError as exc:  # broken symlink, directory named *.md, …
                hard.append(f"{PLANS_ARCHIVE}/{p.name}: could not read: {exc}")
                continue
            if RETIRED_BINDING.search(text):
                soft.append(f"{PLANS_ARCHIVE}/{p.name}: 'review-binding:' is retired "
                            f"(lean pass) — a single attestation mode remains; "
                            f"digest binding is opt-in per REVIEW line")
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
                soft += waiver_debt_notes(f"{PLANS_ARCHIVE}/{p.name}", text,
                                          WAIVED, "review-waived")
                continue
            unique = dedated_counts[DATE_PREFIX.sub("", p.stem)] == 1
            ids = _plan_work_ids(p.stem, text, include_dedated=unique)
            tiered_plans.append((f"{PLANS_ARCHIVE}/{p.name}", text, tier, ids))
            if not _cleared(passes, ids, tier):
                hard.append(f"{PLANS_ARCHIVE}/{p.name}: archived plan declares tier {tier} "
                            f"but has no clearing REVIEW (verdict=pass, work in {sorted(ids)}, "
                            f"tier>={tier}) and no 'review-waived:' line")

    # the speckit path's plans: the decisions ledger is a note there too
    sdir = root / SPECS_DIR
    if sdir.is_dir():
        for d in sorted(p for p in sdir.iterdir() if p.is_dir()):
            plan = d / "plan.md"
            if not plan.is_file():
                continue
            ptext = _unfenced(plan.read_text(encoding="utf-8", errors="replace"))
            tm = TIER_DECL.search(ptext)
            if not tm:
                hard.append(f"{SPECS_DIR}/{d.name}/plan.md: no 'tier: N' declaration — "
                            f"the review, speckit and issue gates all key on it; a "
                            f"plan without a tier is off by omission (add the line, "
                            f"`/plan` puts it there)")
                continue
            if int(tm.group(1)) >= 2 and not DECISIONS_HEADING.search(ptext):
                soft.append(f"{SPECS_DIR}/{d.name}/plan.md: no '## Decisions' section "
                            f"— decisions made in dialogue have no home here and do "
                            f"not survive a compaction (journal-state-plans.md, Plans)")

    # the speckit path's plans never enter the archive — surface the same
    # presence question there as a note (finish.py is the hard stop)
    for name, tier, ids in speckit_unreviewed(root, passes):
        soft.append(f"{SPECS_DIR}/{name}: tasks all ticked and plan declares "
                    f"tier {tier}, but no clearing REVIEW (verdict=pass, work "
                    f"in {sorted(ids)}, tier>={tier}) and no 'review-waived:' "
                    f"— run /review before merging; finish.py blocks on this")

    # ACTIVE plans this push carries. Waiting for the archive step means the
    # proof arrives after the merge it was supposed to gate — so Tier 3 is
    # enforced here, at the push, scoped to the plans this push actually
    # touches (paths_in_flight). Tier 2 keeps the archive-time threshold:
    # "forgot to archive on merge" and that design are indistinguishable and
    # silent, so the gap is at least made visible.
    pdir = root / PLANS_ACTIVE
    in_flight = paths_in_flight(root)
    if pdir.is_dir():
        active_tier2 = 0
        for p in sorted(pdir.glob("*.md")):
            if p.name.startswith("design-"):
                continue
            try:
                text = _unfenced(p.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue  # unreadable active plan; the archive path diagnoses
            m = TIER_DECL.search(text)
            # a plan that TALKS about its tier but never declares it sits outside
            # every tier-keyed gate (presence, spec-before-plan, issue-before-code)
            # — the third-party-plan-writer failure mode: the engine knows tiers,
            # not this grammar. Loud note, not hard: prose mentions are heuristic.
            if not m:
                # Off by omission was the escape: every tier-keyed duty (review
                # presence, spec-before-plan, issue-before-code) is silent for a
                # plan that declares no tier — observed downstream, two plans
                # without the line were invisible to every gate until someone
                # added it and two duties armed at once. An ACTIVE plan is a
                # plan by location; declaring its tier is not optional. Archived
                # plans stay a note (history is not re-litigated).
                hard.append(f"{PLANS_ACTIVE}/{p.name}: no 'tier: N' declaration — "
                            f"every tier-keyed gate (review presence, spec-before-"
                            f"plan, issue-before-code) is unarmed for this plan; a "
                            f"plan without a tier is off by omission. Declare it "
                            f"(risk-tiers.md), or move a non-plan out of the plan home")
                continue
            tier = int(m.group(1))
            if tier < 2:
                continue
            if tier == 2:
                active_tier2 += 1
            rel = f"{PLANS_ACTIVE}/{p.name}"
            if not DECISIONS_HEADING.search(text):
                soft.append(f"{rel}: no '## Decisions' section — decisions made in "
                            f"dialogue have no home in this plan and do not survive a "
                            f"compaction (journal-state-plans.md, Plans); add the "
                            f"ledger, even if it is empty for now")
            ids = _plan_work_ids(p.stem, text, include_dedated=False)
            tiered_plans.append((rel, text, tier, ids))
            if tier < 3:
                continue
            if WAIVED.search(text):
                soft += waiver_debt_notes(rel, text, WAIVED, "review-waived")
                continue
            if rel not in in_flight:
                # somebody else's plan, sitting in the tree untouched by this
                # push — not this push's proof to produce
                continue
            if not _cleared(passes, ids, tier):
                presence(f"{rel}: active plan declares tier {tier} but has no "
                         f"clearing REVIEW (verdict=pass, work in {sorted(ids)}, "
                         f"tier>={tier}) and no 'review-waived:' line — at Tier 3 "
                         f"the proof is due before the merge, not at archival")
        if active_tier2:
            soft.append(f"{active_tier2} active Tier 2 plan(s) in {PLANS_ACTIVE} — "
                        f"at Tier 2 review presence is enforced once the plan is "
                        f"archived (the merge step); archive on merge")

    # the commit-anchored arm: what exists at every merge is the issue plus
    # the commits that CLAIM it (a closing trailer or the `… (#N)` subject —
    # a bare mention is somebody else's business, see issue_refs_in_range).
    # The tier still comes from the plan — a gate that invents its own tier
    # would be worse than the gap it closes — so a claimed issue without a
    # findable plan is a note, not a failure.
    for number in sorted(issue_refs_in_range(root)):
        matching = [(rel, text, tier, ids) for rel, text, tier, ids in tiered_plans
                    if number in _plan_issue_numbers(text)]
        if not matching:
            soft.append(f"a commit in the pushed range claims #{number}, but no "
                        f"plan declares that issue — no tier to key on, so review "
                        f"presence is not enforced for it")
            continue
        for rel, text, tier, ids in matching:
            if tier < 3 or WAIVED.search(text):
                continue
            if not _cleared(passes, ids, tier):
                presence(f"a commit in the pushed range claims #{number}, whose "
                         f"plan {rel} declares tier {tier}, but no clearing REVIEW "
                         f"(verdict=pass, work in {sorted(ids)}, tier>={tier}) and "
                         f"no 'review-waived:' line")

    hard.extend(_unhomed_plans(root))

    if not all_records and not enforced_any and not hard:
        soft.append("no REVIEW attestations yet — expected pre-adoption")
    return hard, soft


# The presence check above keys on .process-work/plans — a plan written
# anywhere else (a topic-triggered third-party skill with its own conventions,
# a stray docs/plans/) silently escapes it, and everything downstream (review
# attestation, archive ritual) never fires. This detector makes that bypass
# loud: a Tier 2+ declaration is the very opt-in the presence gate keys on, so
# one living outside the plan home is hard. Tier 0/1 documents are not plans
# in the gated sense and stay out of scope.
_UNHOMED_PRUNE = {".git", "node_modules", ".venv", "venv", "archive",
                  "__pycache__"}
_UNHOMED_SANCTIONED = (".process-work", "specs", "docs/process", ".github",
                       ".specify", ".claude")


def _unhomed_plans(root: Path) -> list[str]:
    hard: list[str] = []
    for p in sorted(root.rglob("*.md")):
        rel = p.relative_to(root)
        parts = rel.parts
        if any(part in _UNHOMED_PRUNE for part in parts):
            continue
        rel_s = str(rel).replace("\\", "/")
        if any(rel_s == s or rel_s.startswith(s + "/")
               for s in _UNHOMED_SANCTIONED):
            continue
        try:
            text = _unfenced(p.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        m = TIER_DECL.search(text)
        if m and int(m.group(1)) >= 2:
            hard.append(
                f"{rel_s}: declares 'tier: {m.group(1)}' outside the plan home "
                f"— the review-presence gate only sees {PLANS_ACTIVE}; move the "
                f"plan there (or the spec to specs/), or fence the line if it "
                f"is a quotation")
    return hard


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
