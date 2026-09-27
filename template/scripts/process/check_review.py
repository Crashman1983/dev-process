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
import time
from typing import NamedTuple
from pathlib import Path

JOURNAL_DIR = ".process-work/journal"
PLANS_ACTIVE = ".process-work/plans"
PLANS_ARCHIVE = ".process-work/plans/archive"
SPECS_DIR = "specs"
SPEC_PLAN = "plan.md"

# --- where the process records live: ONE owner ------------------------------
# REVIEW, ROOT-CAUSE and REFUTE lines are written into journal shards, into
# plans and into Spec Kit plans (`specs/<dir>/plan.md`, which never archive).
# Every tool that reads those records — this gate, attest.py (rounds, root
# causes), make_review_bundle.py (the REFUTE check and its delta pre-state) —
# asks here, so no tool can forget a home (observed downstream: the delta
# pre-state read only the plan folder, and an old REFUTE line in a Spec Kit
# plan passed as new).
RECORD_KINDS = ("journal", "plan", "plan-archive", "spec-plan")
PLAN_KINDS = ("plan", "spec-plan")  # plans under work: not archived


def record_kind(rel: str) -> str | None:
    """The record kind of a repo-relative posix path, None for any other file:
    `journal` (any shard under the journal), `plan` (an active plan, directly
    in the plan folder), `plan-archive` (a plan in a subfolder of it — the
    archive), `spec-plan` (`specs/<dir>/plan.md`)."""
    if not rel.endswith(".md"):
        return None
    if rel.startswith(JOURNAL_DIR + "/"):
        return "journal"
    if rel.startswith(PLANS_ACTIVE + "/"):
        return "plan" if "/" not in rel[len(PLANS_ACTIVE) + 1:] else "plan-archive"
    parts = rel.split("/")
    if len(parts) == 3 and parts[0] == SPECS_DIR and parts[2] == SPEC_PLAN:
        return "spec-plan"
    return None


def plan_stem(rel: str) -> str:
    """A plan's name for work ids: the file stem, or the spec directory's name
    for a Spec Kit plan (every one of them is called plan.md)."""
    parts = rel.split("/")
    if record_kind(rel) == "spec-plan":
        return parts[1]
    return parts[-1][:-3] if parts[-1].endswith(".md") else parts[-1]


def record_files(root: Path, kinds: tuple[str, ...] = RECORD_KINDS, *,
                 journal_dir: Path | None = None) -> list[tuple[str, Path]]:
    """(repo-relative path, file) of every record file of `kinds` in the
    worktree, sorted per home. `journal_dir` overrides the journal's place
    (attest --journal-dir); its files keep their path relative to the root
    where they sit under it, else their absolute path."""
    out: list[tuple[str, Path]] = []

    def rel_of(f: Path) -> str:
        try:
            return f.relative_to(root).as_posix()
        except ValueError:
            return f.as_posix()

    if "journal" in kinds:
        jdir = journal_dir if journal_dir is not None else root / JOURNAL_DIR
        if jdir.is_dir():
            out += [(rel_of(f), f) for f in sorted(jdir.glob("**/*.md"))]
    pdir = root / PLANS_ACTIVE
    if pdir.is_dir() and ("plan" in kinds or "plan-archive" in kinds):
        for f in sorted(pdir.glob("**/*.md")):
            rel = f"{PLANS_ACTIVE}/{f.relative_to(pdir).as_posix()}"
            if record_kind(rel) in kinds:
                out.append((rel, f))
    sdir = root / SPECS_DIR
    if "spec-plan" in kinds and sdir.is_dir():
        out += [(f"{SPECS_DIR}/{f.parent.name}/{SPEC_PLAN}", f)
                for f in sorted(sdir.glob(f"*/{SPEC_PLAN}")) if f.is_file()]
    return out


def record_texts(root: Path, kinds: tuple[str, ...] = RECORD_KINDS, *,
                 ref: str | None = None,
                 journal_dir: Path | None = None) -> list[tuple[str, str]] | None:
    """(repo-relative path, text) of every record file of `kinds` — in the
    worktree, or at the git `ref`. None when git cannot tell (a missing ref,
    an unreadable blob): the caller must not read "no records" into that.
    Unreadable worktree files are skipped (the gate diagnoses them)."""
    if ref is None:
        out: list[tuple[str, str]] = []
        for rel, f in record_files(root, kinds, journal_dir=journal_dir):
            try:
                out.append((rel, f.read_text(encoding="utf-8", errors="replace")))
            except OSError:
                continue
        return out
    names = _git_bytes(root, "ls-tree", "-r", "-z", "--name-only", ref, "--",
                       JOURNAL_DIR, PLANS_ACTIVE, SPECS_DIR)
    if names is None:
        return None
    out = []
    for raw in names.split(b"\0"):
        rel = raw.decode("utf-8", errors="surrogateescape")
        if not raw or record_kind(rel) not in kinds:
            continue
        blob = _git_bytes(root, "cat-file", "blob", f"{ref}:{rel}")
        if blob is None:
            return None
        out.append((rel, blob.decode("utf-8", errors="replace")))
    return out

REQUIRED = {"work", "tier", "reviewer", "model", "independence", "verdict", "round"}
# optional integrity fields — all three or none (a partial claim is malformed)
ARTIFACT_FIELDS = {"base", "head", "diff"}
INDEP_TOKENS = {"bundle", "non-implementing", "cross-model", "single-family"}
VERDICTS = {"pass", "block"}
# tolerant of a leading list bullet and **bold**/_emphasis_ on the key, and of
# a trailing annotation — a bulleted `- tier: 3` must not escape the presence
# check (a false-green). This gate OWNS the plan-field grammar; the issue gate
# imports these matchers instead of keeping a copy in sync.
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


# HTML comments as CommonMark renders them. A line starting with `<!--` (at
# most three spaces in) opens an HTML block that ends at the line carrying
# `-->`; unclosed, it hides the rest of the file. In running text a comment is
# hidden only when it closes within its paragraph — an unclosed `<!--` there
# is literal text (downstream: "write `<!--` to start a comment" in prose
# swallowed a real record below it). Scanned left to right, the way the
# renderer does: a code span (`<!--` in backticks) is code, a comment opened
# first hides the backticks inside it, `\`` and `\<` are escaped characters.
# Linear time: once no `-->` (or no closing backtick run of a length) follows,
# none is searched again.
# Known limits (a record may be read where a renderer hides it, or the other
# way round): the `<!-->` / `<!--->` forms, comments inside container blocks
# (block quotes, list items indented past three spaces), HTML blocks of other
# kinds (`<div>`, `<pre>`, `<script>`), indented code blocks, entity-escaped
# markers, and setext/table edge cases are not modelled.
_BLOCK_COMMENT = re.compile(r"^ {0,3}<!--")
_ASCII_PUNCT = set("!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~")


def _closing_run(para: str, run: int, pos: int) -> int:
    """Start of the next backtick run of exactly `run` from `pos`, or -1."""
    ticks = "`" * run
    while True:
        k = para.find(ticks, pos)
        if k < 0:
            return -1
        end = k + run
        while end < len(para) and para[end] == "`":
            end += 1
        if end - k == run:
            return k
        pos = end


def _inline_uncommented(para: str) -> str:
    out: list[str] = []
    start = i = 0
    n = len(para)
    no_comment_close = False
    no_tick_close: set[int] = set()
    while i < n:
        c = para[i]
        if c == "\\" and i + 1 < n and para[i + 1] in _ASCII_PUNCT:
            i += 2
            continue
        if c == "`":
            j = i
            while j < n and para[j] == "`":
                j += 1
            run = j - i
            if run not in no_tick_close:
                k = _closing_run(para, run, j)
                if k >= 0:
                    i = k + run
                    continue
                no_tick_close.add(run)
            i = j
            continue
        if c == "<" and not no_comment_close and para.startswith("<!--", i):
            k = para.find("-->", i + 4)
            if k < 0:
                no_comment_close = True
                i += 4
                continue
            out.append(para[start:i])
            start = i = k + 3
            continue
        i += 1
    out.append(para[start:])
    return "".join(out)


def uncommented(text: str) -> str:
    """`text` without what an HTML comment hides when rendered."""
    out: list[str] = []
    para: list[str] = []

    def flush() -> None:
        if para:
            out.append(_inline_uncommented("\n".join(para)))
            para.clear()

    in_block = False
    for line in text.splitlines():
        if in_block:
            in_block = "-->" not in line
            continue
        if _BLOCK_COMMENT.match(line):
            flush()
            in_block = "-->" not in line[line.index("<!--") + 4:]
            continue
        if not line.strip():
            flush()
            out.append("")
            continue
        para.append(line)
    flush()
    return "\n".join(out)


def readable(text: str) -> str:
    """What a reader of the rendered Markdown sees of a record file: fenced
    blocks and HTML comments removed — REFUTE and ROOT-CAUSE lines (and a
    tool's view of REVIEW lines in plans) are read through this."""
    return uncommented(_unfenced(text))


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
            shallow = (_git_bytes(root, "rev-parse", "--is-shallow-repository") or b"").strip() == b"true"
            if shallow:
                # a shallow clone (a cloud session's default) cuts the history the
                # three-dot diff needs — unverifiable here, not a fabrication
                soft.append(f"{rel}:{lineno}: review artifact diff not computable in this "
                            f"shallow clone — digest unverifiable here (`git fetch --unshallow`)")
            else:
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



# --- integrity scope: verify what this push carries, remember the rest -------
# Every digest-bound REVIEW record costs git diffs (canonical, then the
# legacy forms). Re-verifying the whole journal on every push grows without
# bound — measured downstream: 628 bound records, one canonical diff of a
# large range ~3 s, a pre-push gate that no longer finished. The inputs of a
# verification are immutable in a clone (commit objects, the recorded
# digest), so its result is too: a record verified once in this clone is
# taken from a ledger in .git/ afterwards — an "ok" as well as a mismatch,
# so a fabricated digest stays red on every run without being recomputed.
# Shards the push itself changes are always verified fresh; a record whose
# commits are missing here is re-checked each run (a fetch may bring them).
# PROCESS_REVIEW_INTEGRITY=all (or --full) re-verifies everything;
# =in-flight verifies only the changed shards (a CI knob for huge journals).
INTEGRITY_LEDGER = "process-review-integrity"
INTEGRITY_ENV = "PROCESS_REVIEW_INTEGRITY"


def _integrity_ledger_path(root: Path) -> Path | None:
    out = _git_bytes(root, "rev-parse", "--git-dir")
    if out is None:
        return None
    gitdir = Path(out.decode(errors="replace").strip())
    if not gitdir.is_absolute():
        gitdir = root / gitdir
    return gitdir / INTEGRITY_LEDGER if gitdir.is_dir() else None


def _load_integrity_ledger(path: Path | None) -> dict[str, str]:
    if path is None or not path.is_file():
        return {}
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        key, sep, verdict = line.partition("\t")
        if sep and key.count(" ") == 2:
            out[key] = verdict
    return out


def _fetch_stamp(root: Path) -> float:
    """When this clone last fetched — the only event that can bring a missing
    artifact commit. Worktrees share FETCH_HEAD via the common dir."""
    out = _git_bytes(root, "rev-parse", "--git-common-dir")
    if out is None:
        return 0.0
    common = Path(out.decode(errors="replace").strip())
    if not common.is_absolute():
        common = root / common
    try:
        return (common / "FETCH_HEAD").stat().st_mtime
    except OSError:
        return 0.0


def _integrity_scoped(rel: str, root: Path, records: list[tuple[int, dict]], *,
                      fresh: bool, mode: str, ledger: dict[str, str] | None,
                      fetched_at: float = 0.0) -> tuple[list[str], list[str], int]:
    """(hard, soft, reused): integrity findings for one shard; `reused` counts
    records answered from the ledger instead of recomputed. A record whose
    commits are missing is remembered with the time of the check and looked
    up again only after a later fetch — on a partial clone a miss costs
    seconds (measured: ~8 s per lookup, 196 such records, ten minutes a run)."""
    bound = [(ln, f) for ln, f in records if "diff" in f]
    if not bound:
        return [], [], 0
    if mode == "in-flight" and not fresh:
        return [], [], len(bound)
    if fresh or ledger is None:
        h, s = _integrity_violations(rel, root, records)
        if mode == "all" and ledger is not None:
            _remember(rel, root, bound, ledger)
        return h, s, 0
    if mode == "all":  # recompute everything, rewrite the ledger from scratch
        h, s = _integrity_violations(rel, root, records)
        _remember(rel, root, bound, ledger)
        return h, s, 0
    hard: list[str] = []
    soft: list[str] = []
    reused = 0
    for ln, f in bound:
        key = f"{f['base']} {f['head']} {f['diff']}"
        cached = ledger.get(key)
        if cached is not None and cached.startswith("missing:"):
            checked_at = float(cached.split(":", 2)[1] or 0)
            if fetched_at > checked_at:
                cached = None  # a fetch happened since: the commits may be here now
        if cached is not None:
            reused += 1
            if cached.startswith("hard:"):
                hard.append(f"{rel}:{ln}: {cached[5:]}")
            elif cached.startswith("missing:"):
                soft.append(f"{rel}:{ln}: {cached.split(':', 2)[2]}")
            continue
        h, s = _integrity_violations(rel, root, [(ln, f)])
        hard += h
        soft += s
        prefix = f"{rel}:{ln}: "
        if h:
            ledger[key] = "hard:" + h[0].removeprefix(prefix)
        elif s:
            ledger[key] = f"missing:{int(time.time())}:" + s[0].removeprefix(prefix)
        else:
            ledger[key] = "ok"
    return hard, soft, reused


def _remember(rel: str, root: Path, bound: list[tuple[int, dict]], ledger: dict[str, str]) -> None:
    """Store the recomputed verdict of every bound record (used by --full)."""
    for ln, f in bound:
        key = f"{f['base']} {f['head']} {f['diff']}"
        h, s = _integrity_violations(rel, root, [(ln, f)])
        prefix = f"{rel}:{ln}: "
        if h:
            ledger[key] = "hard:" + h[0].removeprefix(prefix)
        elif s:
            ledger[key] = f"missing:{int(time.time())}:" + s[0].removeprefix(prefix)
        else:
            ledger[key] = "ok"


def _save_integrity_ledger(path: Path | None, ledger: dict[str, str]) -> None:
    if path is None:
        return
    try:
        path.write_text("".join(f"{k}\t{v}\n" for k, v in sorted(ledger.items())),
                        encoding="utf-8")
    except OSError:
        pass  # a read-only .git/ costs a recompute next run, never a finding


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
# ("see #12", "Merge pull request #34") claims nothing — read as a claim it
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


BOOKKEEPING = ".process-work/"


REMOTE_INTEGRATION_REFS = ("origin/main", "origin/master")


def _integration_ref(root: Path, tip: str = "HEAD") -> str | None:
    """The integration branch as it stands BEFORE this push. A ref that already
    contains HEAD cannot be that — pushing local `main` without an
    `origin/main` would otherwise exclude everything (downstream refutation);
    then there is no base, and the check stays conservative.

    The remote ref is the authority. A local main ahead of it counts only
    when all it adds are merges on its first-parent chain — a train that
    merged but has not pushed yet; measured against the stale origin, those
    passengers would read as unreviewed. Anything else a local main carries
    (a commit made on main by mistake, a `master` pointed at unreviewed work)
    is not integrated, and does not hide code (downstream refutation)."""
    def usable(ref: str) -> bool:
        out = _git_bytes(root, "rev-parse", "--verify", "-q", f"{ref}^{{commit}}")
        return bool(out and out.strip()) and \
            _git_bytes(root, "merge-base", "--is-ancestor", tip, ref) is None
    remote = next((r for r in REMOTE_INTEGRATION_REFS if usable(r)), None)
    for local in (r for r in INTEGRATION_REFS if r not in REMOTE_INTEGRATION_REFS and usable(r)):
        if remote is None:
            return local
        if _git_bytes(root, "merge-base", "--is-ancestor", remote, local) is None:
            continue
        extra = _git_bytes(root, "rev-list", "--first-parent", "--no-merges", local, f"^{remote}")
        if extra is not None and not extra.strip():
            return local
    return remote


def _names(out: bytes | None) -> set[str] | None:
    """NUL-separated path names (`-z`): non-ASCII names arrive unquoted."""
    if out is None:
        return None
    # surrogateescape: a name that is not UTF-8 goes back to git byte for
    # byte; nothing but the empty field is dropped (a name of whitespace is a
    # name) — downstream refutation
    return {n for n in out.decode(errors="surrogateescape").split("\0") if n}


class History(NamedTuple):
    """What git says about one reviewed head and what is pushed — the facts
    `decide` judges. Gathered by `_history`, one field per case the review
    gate has met downstream (each one a patch before this table existed)."""
    git_error: bool = False           # git could not answer: fail closed
    shallow_missing: bool = False     # the head is not in a shallow clone
    in_history: bool = True           # False: amend or rebase replaced it
    late: frozenset = frozenset()     # this work's code after the head
    dropped: frozenset = frozenset()  # a merge threw the reviewed change away
    fellow: tuple = ()                # (merge, paths): a train merge of another
    #                                   passenger that adds code of its own


def decide(h: History, head: str) -> tuple[str, str]:
    """`("fresh", "")` or `("stale", reason)` — the whole staleness rule."""
    if h.git_error:
        return "stale", (f"cannot determine what changed after the reviewed head {head[:9]} "
                         f"(git did not answer) — not taken as reviewed")
    if h.shallow_missing:
        return "stale", (f"the reviewed head {head[:9]} is not in this shallow clone — cannot check "
                         f"the review; fetch the history (`git fetch --unshallow`)")
    if not h.in_history:
        return "stale", (f"the reviewed head {head[:9]} is not in the history of what is pushed "
                         f"(commit --amend or a rebase replaced the reviewed commits) — the review "
                         f"covers none of it; review again and attest the new head")
    if h.dropped:
        shown = sorted(h.dropped)
        return "stale", (f"a merge threw the reviewed change away ({', '.join(shown[:4])}"
                         f"{', …' if len(shown) > 4 else ''}) — review the merge and attest again")
    if h.late:
        shown = sorted(h.late)
        return "stale", (f"code changed after the reviewed head ({', '.join(shown[:4])}"
                         f"{', …' if len(shown) > 4 else ''}) — the review does not cover it; "
                         f"re-review the delta (`make_review_bundle.py --since <head>`) and attest again")
    if h.fellow:
        merge, paths = h.fellow[0]
        shown = sorted(paths)
        return "stale", (f"train merge {merge[:9]} of another passenger adds code of its own "
                         f"({', '.join(shown[:4])}{', …' if len(shown) > 4 else ''}) — not this "
                         f"work's code, but no merge may carry code outside every review; rebuild the train")
    return "fresh", ""


def _parents(root: Path, commit: str) -> list[str] | None:
    line = _git_bytes(root, "rev-list", "--parents", "-n", "1", commit)
    return None if line is None else line.decode(errors="replace").split()[1:]


def _merge_own(root: Path, merge: str) -> set[str] | None:
    """The code a merge commit adds of its own: paths where its result is
    not what git merges on its own. A clean merge adds nothing — also when
    both sides changed different hunks of one file (downstream: `--cc
    --name-only` named such a file, and every train whose passenger touched a
    file main had changed since the review was refused). A conflicted path
    counts when the resolution equals neither parent; resolving to one side
    is `_dropped_by_merge`'s case. Octopus merges, or a git without
    `merge-tree --write-tree`, fall back to the combined diff — more, never
    less."""
    parents = _parents(root, merge)
    if parents is None:
        return None
    auto = _auto_merge(root, parents[0], parents[1]) if len(parents) == 2 else None
    if auto is None:
        return _names(_git_bytes(root, "show", "--cc", "--format=", "--name-only",
                                 "--ignore-submodules=none", "-z", merge))
    tree, conflicted = auto
    differs = _names(_git_bytes(root, "diff", "--name-only", "--no-renames", "--ignore-submodules=none",
                                "-z", tree, merge))
    if differs is None:
        return None
    own = set()
    for path in differs:
        result = _blob(root, merge, path)
        sides = [_blob(root, p, path) for p in parents]
        if result is None or None in sides:
            return None
        if path in conflicted and result in sides:
            continue
        own.add(path)
    return own


def _history(root: Path, head: str, tip: str = "HEAD",
             reviewed: tuple[tuple[str, str], ...] = (), base: str | None = None) -> History:
    """Gather the facts `decide` judges for one reviewed head.

    `tip` is what is judged — HEAD for a push, a branch for the merge train's
    boarding. Everything reachable from it but not from the reviewed head or
    from main is code of this push that the review never saw: later commits,
    a side branch merged in, an amended commit merged back next to the
    reviewed one, the content an `-s ours` merge kept (downstream refutation:
    each of these passed a "descends from the reviewed head" rule). Merges
    count by what they add of their own (`_merge_own`).

    A merge train is the one exception: its staging commits are a chain of
    merges on top of main, one per passenger. Fellow passengers' commits are
    not this work's code (they carry their own reviews, or need none at
    Tier 0-1), so on such a chain only the merged-in tip that carries the
    reviewed head counts. What a chain merge adds of its own is code nobody
    reviewed: the carrier's merge counts as this work's, another passenger's
    merge is named as such (`fellow`) — it blocks, but is not blamed on this
    work. By design, a passenger without a plan or below Tier 2 is not this
    work's concern: the train's boarding rules and the per-plan gate own
    what may ride."""
    if _git_bytes(root, "merge-base", "--is-ancestor", head, tip) is None:
        shallow = (_git_bytes(root, "rev-parse", "--is-shallow-repository") or b"").strip() == b"true"
        if shallow and _git_bytes(root, "cat-file", "-e", f"{head}^{{commit}}") is None:
            return History(shallow_missing=True)
        return History(in_history=False)
    error = History(git_error=True)
    integ = _integration_ref(root, tip)
    not_integ = [f"^{integ}"] if integ else []
    # code another clearing review has seen is not unreviewed code of this
    # push — a later, separately reviewed change to files of a merged plan
    # is covered by its own review (downstream: a merged plan left active
    # blamed it). A review covers the commits of ITS range, base..head — not
    # the history below its base; code no review has seen stays unreviewed,
    # whatever plan it lands under
    covered: set[str] = set()
    for other_base, other_head in reviewed:
        if other_head == head or _git_bytes(root, "merge-base", "--is-ancestor", other_head, tip) is None:
            continue
        seen = _git_bytes(root, "rev-list", other_head, f"^{other_base}")
        if seen is None:
            continue  # its base is unknown here: it covers nothing
        covered |= {ln.strip() for ln in seen.decode(errors="replace").splitlines() if ln.strip()}
    walk = _git_bytes(root, "rev-list", "--first-parent", "--parents", tip, *not_integ)
    if walk is None:
        return error
    chain = [ln.split() for ln in walk.decode(errors="replace").splitlines() if ln.strip()]
    tips, carriers = [tip], []
    # only the merge train's own staging branch (`train/<stamp>`, pushed from its
    # worktree) gets the passenger exemption — a work branch made of merges
    # only is not a train, and treating it as one hid a side branch merged
    # into it (downstream refutation)
    staging = tip == "HEAD" and (_git_bytes(root, "symbolic-ref", "--short", "-q", "HEAD") or b"") \
        .decode(errors="replace").strip().startswith("train/")
    if staging and chain and all(len(c) >= 3 for c in chain):  # merges only: the train's chain
        for c in chain:
            for parent in c[2:]:
                if _git_bytes(root, "merge-base", "--is-ancestor", head, parent) is not None:
                    carriers.append(c[0])
                    tips.append(parent)
        if carriers:
            tips = tips[1:]
    commits_out = _git_bytes(root, "rev-list", "--no-merges", *tips, f"^{head}", *not_integ)
    merges_out = _git_bytes(root, "rev-list", "--merges", *tips, f"^{head}", *not_integ)
    if commits_out is None or merges_out is None:
        return error
    own_commits = [c for c in (ln.strip() for ln in commits_out.decode(errors="replace").splitlines())
                   if c and c not in covered]
    late: set[str] | None = set()
    if own_commits:
        late = _names(_git_bytes(root, "--no-optional-locks", "-c", "log.showRoot=true", "log", "--no-walk=unsorted",
                                 "--format=", "--name-only", "--no-renames", "--ignore-submodules=none", "-z",
                                 *own_commits))
        if late is None:
            return error
    all_merges = [c for c in (ln.strip() for ln in merges_out.decode(errors="replace").splitlines()) if c]
    in_range = [c for c in all_merges if c not in covered]
    chain_merges = [c[0] for c in chain] if carriers else []
    fellow = []
    for merge in dict.fromkeys(in_range + chain_merges):
        own = _merge_own(root, merge)
        if own is None:
            return error
        if merge in chain_merges and merge not in carriers:
            if own := {p for p in own if not p.startswith(BOOKKEEPING)}:
                fellow.append((merge, frozenset(own)))
        else:
            late |= own
    # merges that resolved to the other side: every merge in the range —
    # also one another review covered: that review saw its code, not that
    # it threw THIS work's reviewed change away (downstream review) — and
    # the train chain's merges
    dropped: set[str] = set()
    for merge in dict.fromkeys(all_merges + chain_merges):
        d = _dropped_by_merge(root, merge, head, base)
        if d is None:
            return error
        dropped |= d
    keep = lambda paths: frozenset(p for p in paths if not p.startswith(BOOKKEEPING))  # noqa: E731
    return History(late=keep(late), dropped=keep(dropped), fellow=tuple(fellow))


def _unreviewed_paths(root: Path, head: str, tip: str = "HEAD", base: str | None = None) -> set[str] | None:
    """Paths of code in `tip` that no review covers — None when git cannot
    tell (the merge train's boarding judges a branch by this)."""
    h = _history(root, head, tip, base=base)
    if h.git_error or h.shallow_missing or not h.in_history:
        return None  # not "nothing unreviewed": the review covers none of it
    return set(h.late | h.dropped).union(*(paths for _m, paths in h.fellow))


_ABSENT = ""


def _blob(root: Path, commit: str, path: str) -> str | None:
    """The object at `path` in `commit`: its mode and id, `_ABSENT` when the
    path does not exist there, None when git cannot tell — a failure must
    never read as "both sides lack the file" (downstream refutation: a
    non-UTF-8 name made every lookup fail, and any resolution passed as
    unchanged). The mode counts: a merge that takes the executable bit away
    changed the file (refutation: a dropped `+x` read as unchanged)."""
    out = _git_bytes(root, "--literal-pathspecs", "ls-tree", "-z", commit, "--", path)
    if out is None:
        return None
    entry = out.split(b"\0", 1)[0]
    if not entry:
        return _ABSENT
    mode, _kind, oid = entry.split(b"\t", 1)[0].split()
    return f"{mode.decode()} {oid.decode()}"


def _auto_merge(root: Path, ours: str, other: str) -> tuple[str, set[str]] | None:
    """What git would have merged on its own: (tree, conflicted paths) — None
    when git cannot tell (an old git without `merge-tree --write-tree`)."""
    try:
        r = subprocess.run(["git", "-C", str(root), "merge-tree", "--write-tree", "--allow-unrelated-histories", "--name-only", "-z",
                            "--no-messages", ours, other], capture_output=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode not in (0, 1):
        return None
    fields = [f for f in r.stdout.decode(errors="surrogateescape").split("\0") if f]
    if not fields:
        return None
    return fields[0].strip(), set(fields[1:])


_EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"  # no common history: all of it is the work's


def _renames(out: bytes | None) -> dict[str, str] | None:
    """`diff --name-status -M -z` read as {old name: new name}."""
    if out is None:
        return None
    fields, i, moved = out.decode(errors="surrogateescape").split("\0"), 0, {}
    while i < len(fields) and fields[i]:
        if fields[i][:1] in ("R", "C") and i + 2 < len(fields):
            if fields[i][:1] == "R":
                moved[fields[i + 1]] = fields[i + 2]
            i += 3
        else:
            i += 2
    return moved


def _dropped_by_merge(root: Path, merge: str, head: str, base: str | None = None) -> set[str] | None:
    """Paths where a merge threw the reviewed work's change away in favour of
    another parent's version. `--cc` is blind to this — the result equals one
    parent, so the combined diff is empty (downstream review residual).

    Judged against what git would have merged on its own: a conflicted path
    resolved wholesale to the other side, or a clean path whose result was
    turned back to the other side against the automatic merge. A clean merge
    that keeps git's own result is never a drop — also not when main already
    carries the reviewed change plus later edits (a squash or cherry-pick
    before a stacked branch merges main; downstream refutation).
    Only this work's own paths can be dropped: what its review saw change
    (`base..head`; without a known base, what it changed since it forked from
    the other side), followed through renames on both sides — a file this
    work renamed is compared with the other side's file under its old name,
    and a file the other side renamed is this work's under its new name. A
    file of this work that git's own merge kept, even moved into a renamed
    directory, and that the merge deleted, is dropped. A side that already
    carries the reviewed head drops nothing. Known limit: inside another
    review's range, a conflict on this work's line resolved to a third value
    is that review's judgement — textually it is indistinguishable from a
    sensible resolution.
    `--no-renames`: a file main renamed is compared under both names; `-z`:
    a non-ASCII name arrives unquoted, or its blobs are never found and the
    drop passes (downstream review)."""
    parents = _parents(root, merge)
    if parents is None:
        return None
    ours = [p for p in parents
            if _git_bytes(root, "merge-base", "--is-ancestor", head, p) is not None]
    if not ours:
        return set()
    our = ours[0]
    paths = _names(_git_bytes(root, "diff", "--name-only", "--no-renames", "--ignore-submodules=none",
                              "-z", our, merge))
    if paths is None:
        return None
    # the review's own range: a stacked branch's review does not own the
    # branch below it, and an unrelated import brings no work of its own
    # (refutation: both read a merge taking main's side of such a file as a drop)
    known_base = base if base and _git_bytes(root, "cat-file", "-e", f"{base}^{{commit}}") is not None else None
    dropped: set[str] = set()
    for other in (p for p in parents if p != our):
        if _git_bytes(root, "merge-base", "--is-ancestor", head, other) is not None:
            continue  # the other side carries the reviewed change itself: nothing of it to drop
        # only what THIS work changed can be thrown away: a file another
        # branch edited and the merge took main's side of is not this work's
        # (refutation: a stacked branch's "take main's version" read as a drop)
        fork = (_git_bytes(root, "merge-base", head, other) or b"").decode().strip() or _EMPTY_TREE
        start = known_base or fork
        work = _names(_git_bytes(root, "diff", "--name-only", "--no-renames", "--ignore-submodules=none",
                                 "-z", start, head))
        mine_moved = _renames(_git_bytes(root, "diff", "--name-status", "-M", "-z", start, head))
        theirs_moved = _renames(_git_bytes(root, "diff", "--name-status", "-M", "-z", fork, other))
        if work is None or mine_moved is None or theirs_moved is None:
            return None
        # a file of this work the other side renamed is this work's under its new name
        work |= {new for old, new in theirs_moved.items() if old in work}
        old_name = {new: old for old, new in mine_moved.items()}
        auto = _auto_merge(root, our, other)
        if auto is None:
            return None
        tree, conflicted = auto
        auto_moved = _renames(_git_bytes(root, "diff", "--name-status", "-M", "-z", our, tree))
        if auto_moved is None:
            return None
        for path in paths & work:
            result, mine, theirs = _blob(root, merge, path), _blob(root, our, path), _blob(root, other, path)
            if None in (result, mine, theirs):
                return None
            if theirs == _ABSENT and path in old_name:
                theirs = _blob(root, other, old_name[path])  # this work renamed it: the other side's is the old name
                if theirs is None:
                    return None
            auto_blob = _blob(root, tree, path)
            if auto_blob is None:
                return None
            if result == _ABSENT and mine != _ABSENT and auto_blob == _ABSENT and path in auto_moved:
                # git's own merge moved the file (a directory the other side renamed): judged where it went
                kept = _blob(root, merge, auto_moved[path])
                if kept is None:
                    return None
                if kept == _ABSENT:
                    dropped.add(path)
                continue
            if result != theirs or mine == theirs:
                continue
            if path in conflicted or result != auto_blob:
                dropped.add(path)
    return dropped


def merged_work(root: Path, rel: str, passes: list[dict], ids: set[str], tier: int) -> bool:
    """Does this plan belong to work the integration branch already carries?
    The plan file is on the integration ref and every clearing review's head
    is in it. Only a note: its stale check still runs — later code no review
    has seen is unreviewed whatever plan it lands under (a refutation showed
    a skip let unreviewed follow-up work through); later code another review
    saw is covered by that review (`reviewed` in `_history`)."""
    integ = _integration_ref(root)
    if integ is None or _git_bytes(root, "cat-file", "-e", f"{integ}:{rel}") is None:
        return False
    heads = [r["head"] for r in passes if r["work"] in ids and int(r["tier"]) >= min(tier, 3) and r.get("head")]
    return bool(heads) and all(
        _git_bytes(root, "merge-base", "--is-ancestor", h, integ) is not None for h in heads)


def _reviewed_heads(passes: list[dict], tier: int, known: set[str]) -> tuple[tuple[str, str], ...]:
    """(base, head) of every clearing CODE review at this plan's tier or
    above that records both, for work a plan names (`known`) — the commits of
    each range count as reviewed for any plan's stale check. A plan review
    (`work=<id>-plan`) saw no code, and a pass for work no plan names is
    nobody's review (refutation: both whitewashed unreviewed code)."""
    return tuple(dict.fromkeys((r["base"], r["head"]) for r in passes
                               if r.get("head") and r.get("base") and int(r["tier"]) >= min(tier, 3)
                               and r["work"] in known and not r["work"].endswith("-plan")))


def _known_work(root: Path) -> set[str]:
    """Every work id any plan names — active, archived or Spec Kit."""
    known: set[str] = set()
    for rel, text in record_texts(root, PLAN_KINDS + ("plan-archive",)) or []:
        stem = Path(rel).parent.name if rel.startswith(SPECS_DIR + "/") else Path(rel).stem
        known |= _plan_work_ids(stem, _unfenced(text), include_dedated=True)  # an example is no id
    return known


def _residue(rel: str) -> str:
    return (f"{rel}: belongs to work already merged (its reviewed head is on the integration "
            f"branch) — later changes are not its code; archive the plan (a merge that "
            f"carries a cleared plan archives it)")


def stale_review(root: Path, passes: list[dict], ids: set[str], tier: int,
                 in_flight: set[str] | None = None,
                 reviewed: tuple[tuple[str, str], ...] = ()) -> str | None:
    """Why the clearing reviews of a plan no longer cover the code — None when
    one of them still does.

    A pass records the `head` it reviewed; `_history` gathers what git says
    about it and `decide` judges — one table, pinned row by row. Bookkeeping
    (journal, plans) is exempt: the attestation commit itself lands after the
    reviewed head. Fails closed: git errors and a head missing from a shallow
    clone are stale, not current.

    A pass without `head` (older records) counts as current only when no
    pass for the work has one. `in_flight` is kept for callers and no longer
    narrows the check: the range above is the push's own code, and an empty
    set must never mean "nothing to check"."""
    req = min(tier, 3)
    clearing = [r for r in passes if r["work"] in ids and int(r["tier"]) >= req]
    if not clearing:
        return None
    with_head = [r for r in clearing if r.get("head")]
    if not with_head:
        # a headless (older) pass counts only while no pass for the work —
        # of any tier — records a head
        if any(r.get("head") for r in passes if r["work"] in ids):
            return "no clearing REVIEW pass records the reviewed head, and a pass that does exists — attest the current head"
        return None
    reason = None
    for r in with_head:
        verdict, why = decide(_history(root, r["head"], reviewed=reviewed, base=r.get("base")), r["head"])
        if verdict == "fresh":
            return None
        reason = why
    return reason


def issues_on_integration(root: Path, limit: int = 2000) -> set[int]:
    """Issue numbers claimed (closing trailer or `(#N)` subject) by commits
    already on the integration branch — the record of what was merged."""
    for ref in INTEGRATION_REFS:
        out = _git_bytes(root, "log", "--format=%B%x00", f"-{limit}", ref)
        if out is not None:
            refs: set[int] = set()
            for message in out.decode(errors="replace").split("\0"):
                body = message.strip()
                if not body:
                    continue
                refs |= {int(n) for n in _ISSUE_CLOSING.findall(body)}
                refs |= {int(n) for n in _ISSUE_SUBJECT.findall(body.splitlines()[0])}
            return refs
    return set()


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
    for _rel, plan in record_files(root, ("spec-plan",)):
        d = plan.parent
        tasks = d / "tasks.md"
        if not tasks.is_file():
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
    integrity_mode = "all" if "--full" in sys.argv else os.environ.get(INTEGRITY_ENV, "ledger")
    scope_base = merge_base(root)
    changed_shards = paths_in_flight(root) if scope_base is not None else set()
    ledger_path = _integrity_ledger_path(root) if integrity_mode in ("ledger", "all") else None
    # `all` recomputes every record AND rewrites the ledger from that — a
    # poisoned or stale entry does not survive a --full run
    ledger = ({} if integrity_mode == "all" else _load_integrity_ledger(ledger_path)) \
        if ledger_path is not None else None
    fetched_at = _fetch_stamp(root) if ledger is not None else 0.0
    reused_total = 0
    # the journal's shards — record_files owns where records live
    for rel, f in record_files(root, ("journal",)):
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
        ih, isoft, reused = _integrity_scoped(
            rel, root, records, ledger=ledger, mode=integrity_mode,
            fetched_at=fetched_at,
            fresh=(scope_base is None or rel in changed_shards))
        reused_total += reused
        hard.extend(ih)
        soft.extend(isoft)
        all_records.extend(records)
    if ledger is not None:
        _save_integrity_ledger(ledger_path, ledger)
    if reused_total:
        what = ("not re-verified (only the shards this push changes are)" if integrity_mode == "in-flight"
                else "answered from this clone's ledger (verified here before; a mismatch stays red)")
        soft.append(f"integrity: {reused_total} digest-bound record(s) in unchanged shards {what} — "
                    f"`--full` or {INTEGRITY_ENV}=all re-verifies everything")

    passes = [f for _ln, f in all_records if f["verdict"] == "pass"]
    known_work = _known_work(root)

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
    for rel, plan in record_files(root, ("spec-plan",)):
        ptext = _unfenced(plan.read_text(encoding="utf-8", errors="replace"))
        tm = TIER_DECL.search(ptext)
        if not tm:
            hard.append(f"{rel}: no 'tier: N' declaration — "
                        f"the review, speckit and issue gates all key on it; a "
                        f"plan without a tier is off by omission (add the line, "
                        f"`/plan` puts it there)")
            continue
        if int(tm.group(1)) >= 2 and not DECISIONS_HEADING.search(ptext):
            soft.append(f"{rel}: no '## Decisions' section "
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
    active = [p for _rel, p in record_files(root, ("plan",))]
    in_flight = paths_in_flight(root)
    merged_issues = issues_on_integration(root)
    if (root / PLANS_ACTIVE).is_dir():
        active_tier2 = 0
        active_dedated: dict[str, int] = {}
        for p in active:
            key = DATE_PREFIX.sub("", p.stem)
            active_dedated[key] = active_dedated.get(key, 0) + 1
        for p in active:
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
            # the slug without its date names the plan too, when unambiguous —
            # as for archived plans (attest's `--work <slug>`)
            ids = _plan_work_ids(p.stem, text,
                                 include_dedated=active_dedated.get(DATE_PREFIX.sub("", p.stem), 0) == 1)
            tiered_plans.append((rel, text, tier, ids))
            if WAIVED.search(text):
                soft += waiver_debt_notes(rel, text, WAIVED, "review-waived")
                continue
            # after the fact: a Tier 3 plan still active while commits claiming
            # its issue already sit on the integration branch was merged past
            # the process (a bypassed hook, a platform merge button) — hard,
            # whatever this push carries: nothing else would ever see it
            if (tier >= 3 and not _cleared(passes, ids, tier)
                    and _plan_issue_numbers(text) & merged_issues):
                hard.append(f"{rel}: tier {tier} work already merged — commits on the "
                            f"integration branch claim #{sorted(_plan_issue_numbers(text) & merged_issues)[0]}"
                            f" — without a clearing REVIEW; review it now and attest, or record "
                            f"the exception with a 'review-waived:' line")
                continue
            if rel not in in_flight:
                # somebody else's plan, sitting in the tree untouched by this
                # push — not this push's proof to produce
                continue
            if not _cleared(passes, ids, tier):
                presence(f"{rel}: active plan declares tier {tier} but has no "
                         f"clearing REVIEW (verdict=pass, work in {sorted(ids)}, "
                         f"tier>={min(tier, 3)}) and no 'review-waived:' line — from "
                         f"Tier 2 on the proof is due before the merge")
                continue
            if merged_work(root, rel, passes, ids, tier):
                soft.append(_residue(rel))
            stale = stale_review(root, passes, ids, tier, in_flight, _reviewed_heads(passes, tier, known_work))
            if stale:
                presence(f"{rel}: {stale}")
        if active_tier2:
            soft.append(f"{active_tier2} active Tier 2 plan(s) in {PLANS_ACTIVE} — "
                        f"their review is due at the merge push; archive on merge")

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
            if number not in _declared_anywhere(root):
                soft.append(f"a commit in the pushed range claims #{number}, but no "
                            f"plan declares that issue — no tier to key on, so review "
                            f"presence is not enforced for it")
            # a plan below Tier 2 or a waived one declares it: nothing to enforce
            continue
        for rel, text, tier, ids in matching:
            if tier < 2 or WAIVED.search(text):
                continue
            if not _cleared(passes, ids, tier):
                presence(f"a commit in the pushed range claims #{number}, whose "
                         f"plan {rel} declares tier {tier}, but no clearing REVIEW "
                         f"(verdict=pass, work in {sorted(ids)}, tier>={min(tier, 3)}) and "
                         f"no 'review-waived:' line")
                continue
            stale = stale_review(root, passes, ids, tier, in_flight, _reviewed_heads(passes, tier, known_work))
            if stale:
                presence(f"#{number} ({rel}): {stale}")

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


def _declared_anywhere(root: Path) -> set[int]:
    """Issue numbers any plan declares — active or archived, whatever its tier."""
    found: set[int] = set()
    for d in (root / PLANS_ACTIVE, root / PLANS_ARCHIVE):
        for p in sorted(d.glob("*.md")) if d.is_dir() else []:
            try:
                found |= _plan_issue_numbers(_unfenced(p.read_text(encoding="utf-8", errors="replace")))
            except OSError:
                continue
    return found


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
    args = [a for a in sys.argv[1:] if a != "--full"]
    root = Path(args[0] if args else ".").resolve()
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
