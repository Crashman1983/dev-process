#!/usr/bin/env python3
"""make_review_bundle: assemble the read-only bundle an independent reviewer
consumes — the process's portable interface to ANY reviewing model.

Verification independence (verification-independence.md) says a Tier 2+ review
runs in a fresh process over a read-only bundle, not in the producing context —
and a Tier 3 review preferably on another model family. What makes that
portable is the *artifact*: one self-contained markdown document any model can
take as its whole input. This tool assembles it:

  1. the reviewer preamble (role, independence expectations, read-only rule);
  2. the kernel block (the binding rules, from docs/process/kernel.md);
  3. the review checklist (what a review actually checks);
  4. the product frame (PRODUCT.md — direction to judge the change against);
  5. the plan(s) under review — the plans the branch touches;
  6. the diff (BASE...HEAD, three-dot: what the branch adds) and the list of
     its files;
  7. the output grammar: the REVIEW line imported from check_review.py (the
     gate that parses it — that half cannot drift), plus the FINDING line whose
     owner is the github-issues module's report gate (journal-state-plans.md);
     a template test pins the FINDING tokens to that gate's enums.

Plus the fix-streak note (check_fix_streak.py, rules 4 and 6) when the branch
has one — its only call site, once per review round.

Sources that cannot be read are named in place, never silently skipped.

Usage:
    make_review_bundle.py [--skip-preflight] [--base REF] [--plan SLUG]
        [--tier N] [--since REF] [-o FILE]

The plans under review are the plans the branch touches (`BASE...HEAD`):
active, archived or `specs/<dir>/plan.md` — never every plan in the repo.
--plan names them explicitly instead: every plan whose file name (a Spec Kit
plan: its path) contains SLUG, archived ones included; no match is an error.

--tier asserts the caller's tier — a floor, never a discount: where a bundled
plan declares a higher one, that one wins. --since limits the diff to the
changes since REF (a delta re-review); it demands a declared tier (a plan's,
or --tier for a branch without one); at Tier 3 a full round at REF and no
scope growth (verification-independence.md, "What each round judges").

--base defaults to the first of origin/main, main, origin/master, master that
git can resolve. Output goes to stdout unless -o is given. The repo root is
resolved via git (works from a subdirectory); read-only; never a gate, never in
CI. Stdlib only.
"""
from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

# check_review.py owns the REVIEW grammar; check_kernel.py owns kernel-block
# extraction — importing both keeps this tool byte-honest with the gates
sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling import
from process_git import git_environment  # noqa: E402
import check_kernel as _kernel_gate  # noqa: E402
import check_review as _review_gate  # noqa: E402
import gate_invoke as _launch  # noqa: E402  (one owner for "how to start the runner")

CHECKLIST = "docs/process/review-checklist.md"
# the project's own review dimensions (stack, domain) — owned by the project, carried here
LOCAL_CHECKLIST = "docs/process/review.local.md"
PRODUCT = "PRODUCT.md"
PLANS = _review_gate.PLANS_ACTIVE
# where a plan under review may live: active, archived (the plan is archived
# before the bundle is built — workflow.md), or a Spec Kit plan
PLAN_HOMES = (*_review_gate.PLAN_KINDS, "plan-archive")
REVIEWS = ".process-work/reviews"
DEFAULT_BASES = _review_gate.INTEGRATION_REFS
PREFLIGHT_TIMEOUT_S = 600
DELTA_MAX_TIER = 3


def _read(root: Path, rel: str) -> str | None:
    p = root / rel
    try:
        return p.read_text(encoding="utf-8") if p.is_file() else None
    except (UnicodeDecodeError, OSError):
        return None


def _kernel_block(root: Path) -> str | None:
    text = _read(root, _kernel_gate.KERNEL_DOC)
    if text is None:
        return None
    # >1 START marker is ambiguous (the kernel gate hard-fails it) — refusing
    # here beats silently bundling whichever block happens to come first
    if text.count(_kernel_gate._START) > 1:
        return None
    return _kernel_gate._block(text)


def _git(root: Path, *args: str) -> str | None:
    try:
        # errors="replace": a non-UTF-8 tracked text file must degrade to
        # replacement chars in the diff, not crash the whole bundle
        r = subprocess.run(["git", "-C", str(root), *args],
                           capture_output=True, text=True, timeout=60,
                           encoding="utf-8", errors="replace", env=git_environment())
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout if r.returncode == 0 else None


def _git_bytes(root: Path, *args: str) -> bytes | None:
    """Raw Git stdout for artifact hashing; decoding must not change bytes."""
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            timeout=60,
            env=git_environment(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout if result.returncode == 0 else None


def _repo_root(cwd: Path) -> Path:
    """The git toplevel when available — running from a subdirectory must not
    silently lose the root-level plan/kernel/PRODUCT sources."""
    top = _git(cwd, "rev-parse", "--show-toplevel")
    return Path(top.strip()) if top and top.strip() else cwd


def _resolve_base(root: Path, base: str | None) -> str | None:
    candidates = (base,) if base else _review_gate.integration_refs(root)
    for c in candidates:
        if c and _git(root, "rev-parse", "--verify", "--quiet", f"{c}^{{commit}}") is not None:
            return c
    return None


def _preflight(root: Path) -> tuple[bool, int, str]:
    """Run the authoritative gate runner before dispatching a review."""
    argv = _launch.gate_runner_argv(root)
    if argv is None:
        # exit 2 = unavailable, distinct from 1 = gates red: a runner that
        # cannot start is a launch problem, not a finding about the branch
        return False, 2, (f"review bundle unavailable: preflight runner not "
                          f"runnable — {_launch.not_runnable_reason(root)}")
    try:
        result = subprocess.run(
            argv, cwd=root, capture_output=True, text=True,
            timeout=PREFLIGHT_TIMEOUT_S, encoding="utf-8", errors="replace",
            env=git_environment(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, 2, (
            f"review bundle unavailable: preflight runner could not run "
            f"({type(exc).__name__})"
        )
    if result.returncode:
        detail = (result.stdout + result.stderr).strip()
        return False, 1, (
            "review bundle blocked: preflight gates failed"
            + (f"\n{detail}" if detail else "")
        )
    return True, 0, ""


FIX_STREAK = Path(__file__).resolve().parent / "check_fix_streak.py"


def _fix_streak(root: Path) -> str:
    """Rules 4/6 as a note in the bundle — once per review round, never blocking. Not a
    gate: the runner's output stays hidden unless it fails, and the note never fails."""
    try:
        r = subprocess.run([sys.executable, str(FIX_STREAK), "."], cwd=root,
                           capture_output=True, text=True, timeout=60,
                           encoding="utf-8", errors="replace", env=git_environment())
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"## Fix streak\nfix-streak: not evaluated ({type(exc).__name__})\n"
    if r.returncode:
        why = (r.stderr.strip().splitlines() or [f"exit {r.returncode}"])[-1]
        return f"## Fix streak\nfix-streak: not evaluated ({why})\n"
    notes = [ln for ln in r.stdout.splitlines() if ln.startswith("fix-streak: note:")]
    return "## Fix streak\n" + "\n".join(notes) + "\n" if notes else ""


def _read_plan(plan: Path) -> str:
    """A plan's text; a byte that is not UTF-8 becomes a replacement char —
    the rest of the plan (its tier, its REFUTE lines) must not vanish with
    it (downstream refute: one bad byte read the whole plan as empty)."""
    try:
        return plan.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _rel(root: Path, plan: Path) -> str:
    return plan.relative_to(root).as_posix()


def _label(root: Path, plan: Path) -> str:
    """How the bundle names a plan: its file name, or `specs/<dir>/plan.md`
    for a Spec Kit plan (every one of them is called plan.md)."""
    rel = _rel(root, plan)
    # `_shown`: a name with a control character (a newline) or a byte that is
    # no UTF-8 is printed escaped — raw, it broke the heading or the write
    return _shown(rel if _review_gate.record_kind(rel) == "spec-plan" else plan.name)


def _plans_from_filter(root: Path, plan_filter: str) -> list[Path]:
    """`--plan`: every plan whose file name contains the filter — active or
    archived — or a Spec Kit plan whose path does (its directory or its
    printed label `specs/<dir>/plan.md`). A filter matching nothing is an
    error: a bundle without the plan asked for would be reviewed as if the
    work had none."""
    hits = [f for rel, f in _review_gate.record_files(root, PLAN_HOMES)
            if plan_filter in (rel if _review_gate.record_kind(rel) == "spec-plan" else f.name)]
    if not hits:
        raise SystemExit(
            f"make_review_bundle: --plan {plan_filter!r} matches no plan. Searched:\n"
            f"  {PLANS}/*{plan_filter}*.md\n"
            f"  {_review_gate.PLANS_ARCHIVE}/**/*{plan_filter}*.md\n"
            f"  {_review_gate.SPECS_DIR}/*{plan_filter}*/{_review_gate.SPEC_PLAN}")
    return hits


def _plans_under_review(root: Path, base_ref: str | None, plan_filter: str | None) -> list[Path]:
    """The plans this review is about: with `--plan`, the ones it names;
    otherwise the plans the branch touches (`base_ref...HEAD`) — active,
    archived or Spec Kit — plus every plan whose issue a commit of the range
    claims (the review gate's own join), and nothing else.

    Bundling every active plan buried the reviewed one downstream (29 active
    plans, some 12,000 lines of other work's text) and let a foreign plan's
    `tier:` refuse a delta. A plan the branch never touched is not the plan
    under review. No base: nothing can be listed, so no plan is bundled."""
    if plan_filter:
        return _plans_from_filter(root, plan_filter)
    if base_ref is None:
        return []
    # -z through the owner of the names: a quoted non-ASCII plan name would
    # match no file and the plan the branch carries would be missing
    names = _review_gate._names(_review_gate._git_bytes(
        root, "diff", "--name-only", "--no-renames", "-z", f"{base_ref}...HEAD"))
    if names is None:
        # a list git cannot give is no "no plan under review": the bundle would
        # carry no plan, no tier and no refute warning, and say nothing
        raise SystemExit(f"make_review_bundle: git cannot list the files of {base_ref}...HEAD "
                         "— repair the clone (`git fsck`, fetch) and build again")
    plans = {rel for rel in names
             if _review_gate.record_kind(rel) in PLAN_HOMES and (root / rel).is_file()}
    # a feature is touched when any file of its spec directory changes: a branch that
    # only ticks tasks.md implements that plan (it had no plan, tier or refute warning)
    specs = _review_gate.SPECS_DIR + "/"
    for rel in names:
        parts = rel[len(specs):].split("/") if rel.startswith(specs) else []
        spec_plan = f"{specs}{parts[0]}/{_review_gate.SPEC_PLAN}" if len(parts) > 1 else ""
        if spec_plan and (root / spec_plan).is_file():
            plans.add(spec_plan)
    # the gate's second join: a plan is this work's when a commit of the range
    # CLAIMS its issue (`check_review.issue_refs_in_range`), touched or not —
    # otherwise the gate enforced a Tier 3 plan the bundle never showed, and a
    # delta was accepted on a caller's --tier 2 (refutation)
    fork = _git(root, "merge-base", base_ref, "HEAD")
    try:
        claimed = _review_gate.issue_refs_in_range(root, "HEAD", base=fork.strip(), strict=True) \
            if fork and fork.strip() else set()
    except _review_gate.GitReadError:
        raise SystemExit(f"make_review_bundle: git cannot read the commits of {base_ref}..HEAD "
                         "— repair the clone and build again") from None
    if claimed:
        for rel, f in _review_gate.record_files(root, PLAN_HOMES):
            text = _review_gate._unfenced(_read_plan(f))
            if claimed & _review_gate._plan_issue_numbers(text):
                plans.add(rel)
    return [root / rel for rel in sorted(plans)]


def _declared_tier(texts: list[str]) -> int | None:
    """The highest tier the plans declare, each read as the review gate reads
    it (`check_review.plan_tier`) — a fenced example or a second `tier:` line
    is no declaration (refutation: the bundle warned and refused on tiers the
    gate never saw)."""
    tiers = [t for t in (_review_gate.plan_tier(text) for text in texts) if t is not None]
    return max(tiers) if tiers else None


_DATED = re.compile(r"^\d{4}-\d{2}-\d{2}-")


class _ReviewedDiff(NamedTuple):
    """What the digest is computed from, apart from what the reviewer reads.

    `digest` is the SHA-256 of the canonical `--binary` bytes
    (`check_review.artifact_diff`) — the identity of the reviewed change,
    which the gate recomputes and every REVIEW record binds to. `text` is the
    same diff without `--binary`: a binary file reads as one `Binary files …
    differ` line instead of its base85 payload, which no reviewer can read
    and which alone once pushed a bundle past a model's prompt limit
    (downstream: 24 PNG baselines)."""

    base: str
    head: str
    digest: str
    text: str
    range_spec: str
    binaries: bool


# the canonical formula minus the payload: every other knob stays pinned, so
# the text read is the text hashed, binaries aside
READABLE_DIFF = tuple(a for a in _review_gate.CANONICAL_DIFF if a not in ("--binary", "--full-index"))
_BINARY_LINE = re.compile(r"^Binary files .* differ$", re.MULTILINE)


def _review_artifact(root: Path, base_ref: str, *, delta: bool = False) -> _ReviewedDiff | None:
    """Resolved endpoints, SHA-256 of the reviewed diff, and its readable text."""
    base = _git(root, "rev-parse", base_ref) if delta else _git(root, "merge-base", base_ref, "HEAD")
    head = _git(root, "rev-parse", "HEAD")
    if not base or not head:
        return None
    base_sha = base.strip()
    head_sha = head.strip()
    # ONE formula, owned by the gate that verifies it (check_review.artifact_diff):
    # canonical three-dot diff with every git-config knob pinned. A delta bundle
    # uses own first-parent changes and integration merge resolutions.
    range_spec = f"{base_sha}...{head_sha}"
    raw = _review_gate.artifact_diff(root, base_sha, head_sha, mode="delta" if delta else "full")
    shown = (_review_gate.delta_diff(root, base_sha, head_sha, binary=False) if delta
             else _git_bytes(root, *READABLE_DIFF, range_spec))
    if raw is None or shown is None:
        return None
    text = shown.decode("utf-8", errors="replace")
    return _ReviewedDiff(base_sha, head_sha, hashlib.sha256(raw).hexdigest(), text,
                         range_spec, _BINARY_LINE.search(text) is not None)


def _fenced(body: str, info: str = "") -> str:
    """`body` in a fence longer than any backtick run inside it (min 4): a
    diff of a markdown file, or a file name, carries its own ``` runs, which
    would close a plain fence early and corrupt everything after it."""
    longest = max((len(m) for m in re.findall(r"`+", body)), default=0)
    fence = "`" * max(4, longest + 1)
    return f"{fence}{info}\n" + body + ("" if body.endswith("\n") else "\n") + fence + "\n"


def _grammar_section() -> str:
    # REVIEW fields/enums come from the gate that parses them (import above).
    # The FINDING line's owner is check_issues.py (github-issues module — not
    # importable here, it renders conditionally); its sev/action tokens are
    # duplicated below and pinned to that gate's enums by a template test.
    fields = " ".join(f"{k}=…" for k in sorted(_review_gate.REQUIRED))
    return f"""Record your verdict EXACTLY in this grammar — the gates parse it verbatim,
free-form prose is invisible to them:

    REVIEW {fields}

Bind your verdict to the exact artifact: do NOT type `base=… head=… diff=…`
yourself — run `python scripts/process/attest.py --bundle <this file> …`,
which recomputes the digest from base/head (a typed digest is a fabricated
attestation the gate names as such). The `REVIEW_ARTIFACT` line binds to the exact
reviewed diff (the gate recomputes and verifies the digest). Never invent
these values.

- `verdict`: one of {sorted(_review_gate.VERDICTS)}.
- `independence`: comma-joined tokens from {sorted(_review_gate.INDEP_TOKENS)} —
  attest honestly what you are: reading this bundle in a fresh context is
  `bundle,non-implementing`; add `cross-model` only if you are a different
  model family than the implementer, else declare `single-family`.
- `tier`/`round`: integers; `work`: the issue number or plan slug under review.
- `model`: your own model's id, verbatim — the *relation* to the implementer is
  what `independence` records, so `same`/`cross` there says nothing new.

For each finding, one line:

    FINDING sev=<blocker|major|minor|nit> action=<fix|accept|follow-up> issue=<ref|-> gate=<judgement|possible|name> [origin=<draft|fix|late>] <title>

- `gate`: could a linter, type checker or gate rule have produced this finding?
  `judgement` = no, it needed a reader; `possible` = yes, but no rule exists
  yet; otherwise the name of the rule that now catches it. `possible` is the
  one that matters: it marks a finding every future change will pay a reader
  to rediscover until somebody writes the rule.
- `origin` (optional): `draft` = in the change as first reviewed, `fix` =
  introduced by a fix round, `late` = in the draft but found only now.

Judge against the checklist and the rules above; cite file:line evidence; a
`pass` with unfixed blockers is a false green — verdict `block` instead."""


def _tier_provenance(root: Path, tier: int | None, plan_tier: int | None,
                     declared_tier: int | None, plans: list[Path]) -> str:
    """Where the deciding tier came from. A tier the caller asserted with
    `--tier` and no plan corroborates is legible as an assertion — otherwise
    a delta's scope would rest on something the reviewer never sees."""
    if tier is None:
        return "no declared tier"
    if plan_tier is not None and (declared_tier is None or plan_tier >= declared_tier):
        return f"tier {tier} read from " + ", ".join(_shown(_rel(root, p)) for p in plans)
    if plan_tier is not None:
        return (f"tier {tier} asserted by the caller via --tier, above the tier "
                f"{plan_tier} the bundled plan declares")
    if plans:
        return (f"tier {tier} asserted by the caller via --tier — the bundled plan "
                "declares none")
    return (f"tier {tier} asserted by the caller via --tier — no plan is under "
            "review, so nothing in this repository corroborates it")


# the tier from which a plan without a REFUTE line is warned about; gate code
# warns at any tier (`docs/process/refute.md`, the table)
REFUTE_RUN_TIER = 3
# at Tier 2 the review itself answers the refuter's brief (`docs/process/refute.md`)
TIER_TWO_BRIEF = (
    "**Tier 2: the review is also the attack.** Answer each in your report, with evidence: "
    "OWNER — does the diff re-implement a fact or rule existing code already owns (a second "
    "reader)? Prove it with an input on which both judge differently. FAIL-OPEN — what does a "
    "missing, failing or unresolved input read as? It must not read as the OK state. EDGE "
    "CASES — the classes of `docs/process/failure-catalog.md` the change touches. EVIDENCE — "
    "would a test go red if one branch of the new code were removed?")

# what each round judges — owned by verification-independence.md ("What each
# round judges"); a template test pins these to that paragraph
FIRST_ROUND_RULE = ("Name every blocker you find, not the first — a blocker held back is "
                    "a round.")
DELTA_ROUND_RULE = ("Judge the fix diff and the open findings, and re-check the fixed failure "
                    "class everywhere it can recur, not only at the fixed spot. If the fix "
                    "changed a contract, the architecture or the risk scope, say so and ask "
                    "for a full bundle instead of judging the delta.")


# above this a review stops being one review: downstream, the works that ran
# five to seven rounds were 3,000–5,500 changed lines or a batch of issues
REVIEW_MAX_FILES = int(os.environ.get("PROCESS_REVIEW_MAX_FILES", "30"))
REVIEW_MAX_LINES = int(os.environ.get("PROCESS_REVIEW_MAX_LINES", "1500"))
SIZE_IGNORED = re.compile(r"^\.process-work/|(^|/)(package-lock\.json|uv\.lock|poetry\.lock|yarn\.lock|"
                          r"pnpm-lock\.yaml|Cargo\.lock|go\.sum)$")


# gate code as `docs/process/refute.md` defines it — the review gate owns the paths
GATE_PATHS, GATE_FILES = _review_gate.GATE_PATHS, _review_gate.GATE_FILES
# a real REFUTE line: at most three spaces of indent (four is a code block),
# any list marker, a work id that is not the brief's placeholder, a round and
# what was found. A bare `REFUTE work=x` or a line in backticks is a mention,
# not a record (downstream review: both switched the warning off)
REFUTE_LINE = re.compile(
    r"^ {0,3}(?:(?:[-*+]|\d+[.)])[ \t]+(?:\[[xX]\][ \t]+)?)?REFUTE[ \t]+work=(?P<work>(?!<)(?!TODO\b)[\w#./-]+)"
    r"[ \t]+round=(?P<round>\d+):[ \t]*(?P<text>(?!<|TODO\b|…|\.\.\.)\S.*)$",
    re.MULTILINE)
# Known limit: an item nested four spaces deep reads as a code block and does
# not count (a false warning, never a silent pass). Fenced blocks and HTML
# comments are removed first, as check_review.readable renders them (its
# known limits apply here too).


def _gate_files(root: Path, base_ref: str) -> list[str] | None:
    """Gate code the branch changes (`docs/process/refute.md`) — None when git
    cannot tell. `--no-renames`: a gate file moved out of the gate paths is a
    deletion there, not a silent new name elsewhere; `-z`: non-ASCII names
    arrive unquoted."""
    out = _git(root, "diff", "--name-only", "--no-renames", "-z", f"{base_ref}...HEAD")
    if out is None:
        return None
    return sorted(n for n in out.split("\0")
                  if n and _review_gate.is_gate_path(n))


def _refute_entries(text: str) -> set[tuple[str, int, str]]:
    """(work, round, what was found — whitespace-normalized) of the REFUTE
    lines a reader sees: outside fenced blocks and HTML comments — an example
    quoted from the brief does not count; an unchecked `- [ ]` item is a
    to-do, not a record."""
    return {(m.group("work"), int(m.group("round")), " ".join(m.group("text").split()))
            for m in REFUTE_LINE.finditer(_review_gate.readable(text or ""))}


def _plan_ids(rel: str, text: str) -> set[str]:
    return _review_gate._plan_work_ids(_review_gate.plan_stem(rel), text, include_dedated=True)


def _plans_at(root: Path, ref: str) -> dict[str, str] | None:
    """Every plan at `ref` — active, archived and Spec Kit, as check_review
    lists them (path -> text). None when git cannot tell."""
    texts = _review_gate.record_texts(
        root, (*_review_gate.PLAN_KINDS, "plan-archive"), ref=ref)
    return None if texts is None else dict(texts)


def _unrefuted(root: Path, plans: dict[Path, str], before: dict[str, str] | None = None) -> list[str]:
    """Plans without a REFUTE line of their OWN work — a line of one stacked
    plan does not cover another (downstream review).

    With `before` (every plan at the delta's start, archived ones included),
    the plan needs a NEW record of its own work. A record is old when
      - the plan's own path at the start already had that round for one of
        the plan's CURRENT work ids (a reformatted or edited old line; a line
        that only starts to count because the plan gained an id), or
      - a plan at the start carried the same record — same round, same text
        after the colon (whitespace aside) — for this plan's work, or in a
        plan that is gone from its path since (moved, archived or merged,
        its id maybe changed along). A plan still in place keeps its lines:
        another work's identical line is not this plan's (refutation).
    No similarity score decides it (git's rename detection flipped with the
    edit size, downstream refute), and a second plan of one issue neither
    lends nor takes a round: its own new line differs in what it found.
    Known limit: an old line whose text is edited AND that moved to another
    path reads as new."""
    missing: list[str] = []
    earlier = {old: _refute_entries(t) for old, t in (before or {}).items()}
    for plan, text in plans.items():
        rel = _rel(root, plan)
        ids = _plan_ids(rel, text)
        records = {(r, t) for w, r, t in _refute_entries(text) if w in ids}
        if before is not None:
            old_rounds = {r for w, r, _t in earlier.get(rel, ()) if w in ids}
            # a line of this work anywhere; any line of a plan that is gone
            # from its path since (moved, archived, merged — its id may have
            # changed along); a plan still in place keeps its lines to itself
            pool = {(r, t) for old, entries in earlier.items() for w, r, t in entries
                    if w in ids or not (root / old).exists()}
            records = {(r, t) for r, t in records if r not in old_rounds and (r, t) not in pool}
        if not records:
            missing.append(_label(root, plan))
    return missing


def _tier_warning(by_tier: list[str], tiers: dict[str, int | None]) -> str:
    named = ", ".join(f"{label} (tier: {tiers[label]})" for label in by_tier[:3])
    return (f"**REFUTE WARNING:** {named}{' …' if len(by_tier) > 3 else ''} carries no "
            "`REFUTE work=<its id> round=<r>: …` line — from Tier 3 on, a fresh agent attacks "
            "the change before its first review round and each delta round "
            "(`docs/process/refute.md`). Say in the verdict that it was not.\n")


def _shown(path: str) -> str:
    """A path as a Markdown line can carry it: a control character (a newline
    in a file name) is escaped, so the bullet stays one line."""
    return "".join(c if c.isprintable() else repr(c)[1:-1] for c in path)


def review_size(root: Path, base_ref: str) -> tuple[int, int]:
    """(files, changed lines) of the whole branch — process bookkeeping,
    lock files and binaries left out."""
    files = lines = 0
    # -z: a quoted non-ASCII lock file escaped the filter. Each entry is
    # "added\tdeleted\tpath"; a rename leaves the path empty and names the old
    # and the new path in the next two fields.
    out = _review_gate._git_bytes(root, "diff", "--numstat", "-z", f"{base_ref}...HEAD") or b""
    fields = iter(out.decode(errors="surrogateescape").split("\0"))
    for field in fields:
        parts = field.split("\t", 2)
        if len(parts) < 3:
            continue
        path = parts[2]
        if not path:
            next(fields, None)
            path = next(fields, "")
        if SIZE_IGNORED.search(path):
            continue
        files += 1
        if parts[0].isdigit() and parts[1].isdigit():
            lines += int(parts[0]) + int(parts[1])
    return files, lines


def _report_keys(root: Path, plan_filter: str | None, plan_texts: dict[Path, str]):
    """(slugs, issues) that name this work's report (`check_review.report_of`)."""
    slugs = [_DATED.sub("", plan_filter)] if plan_filter else []
    issues: list = []
    for p, text in plan_texts.items():
        s, i = _review_gate.plan_report_keys(_rel(root, p), text, root)
        slugs += s
        issues += i
    return tuple(dict.fromkeys(s for s in slugs if s)), tuple(dict.fromkeys(issues))


def _since_head(root: Path, since: str) -> tuple[str, str]:
    sha = (_git(root, "rev-parse", "--verify", "--quiet", f"{since}^{{commit}}") or "").strip()
    return sha, (_git(root, "rev-parse", "HEAD") or "").strip()


def _tier_at(root: Path, ref: str, plans: list[Path]) -> int:
    """The highest tier these plans declared at `ref` (0 when none did), read
    as `build` reads it: no design doc, no plan that waives its review."""
    texts = [_git(root, "show", f"{ref}:{_rel(root, p)}") for p in plans
             if not p.name.startswith(_review_gate.DESIGN_DOC_PREFIX)]
    return _declared_tier([t for t in texts if t and not _review_gate.review_waived(t)]) or 0


def _delta_files(root: Path, since: str) -> list[str] | None:
    sha = _git(root, "rev-parse", "--verify", "--quiet", f"{since}^{{commit}}")
    head = _git(root, "rev-parse", "HEAD")
    if not sha or not head:
        return None
    entries = _review_gate.name_status(
        _review_gate.delta_diff(root, sha.strip(), head.strip(), names=True))
    return None if entries is None else list(dict.fromkeys(path for _l, _s, path in entries))


def _tier3_delta_refusal(root: Path, since: str, plan_filter: str | None,
                         plan_texts: dict[Path, str]) -> str | None:
    """Why this Tier 3 delta needs a full bundle — None when it may run. The
    gate's owner decides (`check_review.tier3_delta_problem`), never the worker."""
    sha, head = _since_head(root, since)
    ids = {i for p, t in plan_texts.items() if t for i in _plan_ids(_rel(root, p), t)}
    records = [f for _r, t in _review_gate.record_texts(root, ("journal",)) or []
               for _l, f in _review_gate.parse_review_lines(t)[0]]
    if not sha or not head:
        return _review_gate.tier3_delta_refusal(sha or since)
    return _review_gate.tier3_delta_problem(root, records, ids, sha, head,
                                            _report_keys(root, plan_filter, plan_texts))


def build(root: Path, base: str | None, plan_filter: str | None = None,
          since: str | None = None, plans: list[Path] | None = None,
          declared_tier: int | None = None) -> str:
    out: list[str] = []
    add = out.append
    resolved = _resolve_base(root, base)
    # main() passes the selection in, so the summary it prints cannot
    # disagree with what the bundle carries
    if plans is None:
        plans = _plans_under_review(root, resolved, plan_filter)
    plan_texts = {plan: _read_plan(plan) for plan in plans}
    plan_tier = _declared_tier([text for plan, text in plan_texts.items()
                                  if not plan.name.startswith(_review_gate.DESIGN_DOC_PREFIX)
                                  and not _review_gate.review_waived(text)])
    # a caller's --tier is a floor, never a discount: the higher one decides
    tier = plan_tier if declared_tier is None else max(plan_tier or 0, declared_tier)
    # the plans a refute is asked of by tier: not a design doc, not a plan
    # that waives its review — as the review gate judges both
    tiers = {_label(root, plan): _review_gate.plan_tier(text) for plan, text in plan_texts.items()
             if not plan.name.startswith(_review_gate.DESIGN_DOC_PREFIX) and not _review_gate.review_waived(text)}
    if since and tier is None:
        # no plan under review, no --tier: an undeclared tier is no licence
        # for a delta — scoping the plans to the branch would otherwise hand
        # every planless branch the delta review Tier 3 forbids
        raise SystemExit(
            "make_review_bundle: --since refused — no tier is declared. Name the plan "
            f"with --plan <slug> (in {PLANS}/, its archive, or "
            f"{_review_gate.SPECS_DIR}/<dir>/{_review_gate.SPEC_PLAN}), declare the tier with "
            "--tier N for a branch without a plan, or build the full bundle without --since")
    if since and tier is not None and tier > DELTA_MAX_TIER:
        raise SystemExit(f"make_review_bundle: --since refused — tier {tier} is above the "
                         f"Tier {DELTA_MAX_TIER} scale; build the full bundle")
    touches = _delta_files(root, since) if since else None
    # a fix round that lowers the tier is judged at the tier it started from
    if since and tier is not None and (tier >= 3 or _tier_at(root, since, plans) >= 3):
        # Tier 3: anchored on a full round, and no scope growth (verification-independence.md)
        refusal = _tier3_delta_refusal(root, since, plan_filter, plan_texts)
        if refusal:
            who = (f"bundled plan {next(_label(root, p) for p, t in plan_texts.items() if _declared_tier([t]) == tier)}"
                   if plan_tier == tier else f"--tier {declared_tier}")
            raise SystemExit(f"make_review_bundle: --since refused — {who} declares tier: {tier}; "
                             f"{refusal}. If that plan is not the work under review, name the one "
                             "that is with --plan <name>")

    add("# Review bundle — read-only\n")
    add("You are an INDEPENDENT reviewer. This bundle is your complete input: "
        "do not consult the implementing agent's context, do not edit anything, "
        "and do not trust claims you can check in the diff. Your deliverable is "
        "a verdict plus findings in the exact grammar at the end. The edge cases to try are "
        "the classes of `docs/process/failure-catalog.md` the change touches.\n")
    if since:
        add("**Delta re-review.** The diff below is limited to changes since "
            f"`{since}`. Previous findings and the full branch file surface are "
            "included so fixes are judged in their original scope. " + DELTA_ROUND_RULE + "\n")
        add(f"**Scope rests on {_tier_provenance(root, tier, plan_tier, declared_tier, plans)}.** "
            "A Tier 3 delta needs a full round at its start and no scope growth; if that tier is "
            "wrong, this bundle is too narrow — say so instead of reviewing it.\n")
        add("DELTA_TOUCHES files=" + (",".join(_shown(p) for p in touches)
                                      if touches is not None else "(unknown)") + "\n")
    else:
        add(FIRST_ROUND_RULE + "\n")
    if tier == 2:
        add(TIER_TWO_BRIEF + "\n")

    if resolved is not None:
        files, lines = review_size(root, resolved)
        if files > REVIEW_MAX_FILES or lines > REVIEW_MAX_LINES:
            add(f"**SIZE WARNING:** this branch changes {files} files / {lines} lines (limit "
                f"{REVIEW_MAX_FILES} / {REVIEW_MAX_LINES}, `PROCESS_REVIEW_MAX_FILES`/`_LINES`). "
                "Reviews this large ran five to seven rounds downstream. Split it before the "
                "first round if the plan allows; otherwise say so in the verdict and review "
                "it slice by slice.\n")

    if resolved is None and not since and plan_texts:
        # no base, so no gate-code check — the tier needs no git (refutation:
        # the tier warning vanished silently without a base)
        missing = _unrefuted(root, plan_texts)
        by_tier = [label for label in missing if (tiers.get(label) or 0) >= REFUTE_RUN_TIER]
        if by_tier:
            add(_tier_warning(by_tier, tiers))
        elif missing and any((tiers.get(label) or 0) == 2 for label in missing):
            # refute v2.47: Tier 2 needs no refute run — unless the diff is gate
            # code, which nobody can tell without a base; say so instead of nothing
            add("*(REFUTE check unavailable: no base ref, so gate code cannot be detected — "
                "if this Tier 2 change touches gate code, it needs a `REFUTE` line)*\n")
    if resolved is not None or since:
        # a delta re-review: the fix round's own gate code, refuted anew
        gate_files = _gate_files(root, since or resolved)
        before = _plans_at(root, since) if since else None
        if since and before is None:
            gate_files = None
        missing = _unrefuted(root, plan_texts, before) if plan_texts else ["(no plan under review)"]
        # by tier (`docs/process/refute.md`): from Tier 3 on, a refute before the
        # first review round and again before each delta round (Tier 2 answers
        # the brief inside the review)
        by_tier = [label for label in missing if (tiers.get(label) or 0) >= REFUTE_RUN_TIER]
        if gate_files is None:
            add("*(REFUTE check unavailable: git could not list the branch's files — a shallow clone "
                "or no merge base; check by hand whether gate code changed)*\n")
        elif gate_files and missing:
            add(f"**REFUTE WARNING:** this {'delta' if since else 'diff'} changes gate code "
                f"({', '.join(gate_files[:3])}{', …' if len(gate_files) > 3 else ''}) and "
                f"{', '.join(missing[:3])}{' …' if len(missing) > 3 else ''} carries no "
                f"{'new ' if since else ''}`REFUTE work=<its id> round=<r>: …` line — gate code is "
                "attacked by a fresh agent before its first review round, and a fix round's gate "
                "code again (`docs/process/refute.md`). Say in the verdict that it was not.\n")
            by_tier = []
        if by_tier:
            add(_tier_warning(by_tier, tiers))

    streak = _fix_streak(root)
    if streak:
        add(streak)

    kernel = _kernel_block(root)
    add("## The binding rules (kernel)\n")
    add(kernel + "\n" if kernel else "*(unavailable: docs/process/kernel.md has no readable kernel block)*\n")

    checklist = _read(root, CHECKLIST)
    add("## What a review checks\n")
    add(checklist + "\n" if checklist else "*(unavailable: docs/process/review-checklist.md missing)*\n")
    local = _read(root, LOCAL_CHECKLIST)
    if local:
        add(f"## This project's review dimensions ({LOCAL_CHECKLIST})\n")
        add("They sharpen the list above, never weaken it: a line here cannot waive a rule, a "
            "gate or a checklist category.\n\n")
        add(local + "\n")

    product = _read(root, PRODUCT)
    add("## Product frame (judge direction against this)\n")
    add(product + "\n" if product else "*(unavailable: PRODUCT.md missing)*\n")

    add("## Plan(s) under review\n")
    if plans:
        for p in plans:
            add(f"### {_label(root, p)}\n")
            add((plan_texts[p] or "*(unreadable)*") + "\n")
    else:
        why = ("the branch touches no plan" if resolved is not None else
               "without a base ref the plans the branch touches cannot be listed")
        add(f"*(no plan under review: {why} in `{PLANS}/` (active or archived) or "
            f"`{_review_gate.SPECS_DIR}/<dir>/{_review_gate.SPEC_PLAN}` — name one with `--plan <slug>` "
            "if it lives elsewhere; otherwise review the diff against the checklist and rules "
            "alone, and say so in your verdict)*\n")

    if since:
        add("## Findings from the previous round\n")
        # the gate's rule: the report as committed, never one the fix brought
        slugs, issues = _report_keys(root, plan_filter, plan_texts)
        sha, head = _since_head(root, since)
        found = _review_gate.prior_report(root, slugs, issues, sha, head) if sha and head else None
        if found:
            add(f"### {_shown(found[0])}\n{found[1]}\n")
        else:
            named = ", ".join([*dict.fromkeys(s for s in slugs if s),
                               *(f"{repo or ''}#{n}" for repo, n in issues)]) or "no plan or issue"
            add(f"*(no review report for this work item ({named}) under {REVIEWS}; prior "
                f"findings unavailable — deliberately not another item's report)*\n")

    add("## Diff under review\n")
    if resolved is None:
        add("*(unavailable: no usable base ref — pass --base explicitly; "
            "git may be absent or the repo unborn)*\n")
    else:
        artifact = _review_artifact(root, since or resolved, delta=bool(since))
        if artifact is None and since:
            raise SystemExit("make_review_bundle: cannot bound this delta — use a full review "
                             "for non-first-parent, feature merge or octopus histories")
        if artifact is None:
            add(f"*(unavailable: `git diff {resolved}...HEAD` failed)*\n")
        else:
            add(f"REVIEW_ARTIFACT base={artifact.base} head={artifact.head} diff={artifact.digest}{' mode=delta' if since else ''}\n")
            if since:
                add(f"REVIEW_SCOPE mode=delta since={artifact.base} head={artifact.head}\n")
            diff = artifact.text
            if not diff.strip():
                add(f"*(empty: HEAD adds nothing over {resolved})*\n")
            else:
                lines = diff.count("\n")
                label = (f"Delta: `{since}..HEAD`" if since else
                         f"Base: `{resolved}` resolved to `{artifact.base}` (three-dot: what the branch adds)")
                add(f"{label}. "
                    f"{lines} diff lines.\n")
                # the reviewer checks completeness against this list instead of
                # hunting `diff --git` lines (downstream: two reviewers spent a
                # full round on an artifact that lacked five files); -z through
                # the owner, so a name arrives unquoted
                entries = _review_gate.name_status(
                    _review_gate.delta_diff(root, artifact.base, artifact.head, names=True) if since
                    else _review_gate._git_bytes(root, "diff", "--name-status", "--no-renames", "-z", artifact.range_spec))
                if entries is not None:
                    entries = list(dict.fromkeys(entries))
                if entries is None:
                    raise SystemExit(f"make_review_bundle: git cannot list the files of "
                                     f"{artifact.range_spec} — repair the clone and build again")
                if entries:
                    add(f"Files in this diff ({len(entries)}):\n" + _fenced(
                        "\n".join(f"{letter}\t{_shown(path)}" for letter, _source, path in entries)))
                if since:
                    stat = _git(root, "diff", "--stat", f"{resolved}...HEAD")
                    if stat and stat.strip():
                        add("Full branch surface:\n```\n" + stat.rstrip() + "\n```\n")
                if artifact.binaries:
                    # a binary reads as `Binary files … differ`, without a size:
                    # the stat block names path and bytes, so the gap is not
                    # mistaken for completeness. The digest still covers them.
                    stat = ("\n".join(artifact.text.splitlines()) if since
                            else _git(root, "diff", "--stat=200", "--no-renames", artifact.range_spec))
                    add("*(binary files carry no content in this bundle — their encoded payload "
                        "is unreadable to you, and the digest above still covers it. Judge them "
                        "by path, status and size:)*\n")
                    if stat and stat.strip():
                        add(_fenced(stat.rstrip()))
                if lines > 4000:
                    truncated = "no text was truncated" if artifact.binaries else "nothing was truncated"
                    add(f"*(large diff — consider a per-area pass; {truncated})*\n")
                status = _git(root, "status", "--porcelain")
                if status and status.strip():
                    add("*(working tree dirty — uncommitted changes are NOT in this "
                        "diff; only committed work is under review)*\n")
                add(_fenced(diff, "diff"))

    add("## UI evidence (open the files — a bundle cannot carry pixels)\n")
    add(_ui_evidence(root, resolved, plans) + "\n")

    add("## Required output grammar\n")
    add(_grammar_section() + "\n")
    return "\n".join(out)


IMAGE_RE = re.compile(r"\.(png|jpe?g|webp|gif)$", re.IGNORECASE)
EVIDENCE_DIR = ".process-work/reviews"
# screenshots of states that are no evidence (a loading placeholder, an empty
# shell): an evidence image byte-identical to one of them is void
VOID_DIR = "docs/process/void-evidence"
PAIR_SIDE = re.compile(r"^(before|after)-(.+)$")


def _void_evidence(root: Path, imgs: list[Path]) -> list[str]:
    """Evidence that proves nothing, named: a before/after pair whose two
    images are byte-identical (nothing changed on screen — or both show the
    same loading state), other images identical under different names (the
    harness rendered the wrong thing), and images identical to a known void
    state under `docs/process/void-evidence/`."""
    def digest(f: Path) -> str:
        return hashlib.sha256(f.read_bytes()).hexdigest()
    void_dir = root / VOID_DIR
    known = {digest(f): f.name for f in sorted(void_dir.glob("*")) if f.is_file() and IMAGE_RE.search(f.name)} \
        if void_dir.is_dir() else {}
    by_hash: dict[str, list[Path]] = {}
    out: list[str] = []
    for f in imgs:
        h = digest(f)
        by_hash.setdefault(h, []).append(f)
        if h in known:
            out.append(f"- VOID: `{f.relative_to(root)}` is the known void state `{known[h]}` ({VOID_DIR}/)")
    for same in by_hash.values():
        if len(same) < 2:
            continue
        sides: dict[str, dict[str, Path]] = {}
        for f in same:
            m = PAIR_SIDE.match(f.stem)
            if m:
                sides.setdefault(m.group(2), {})[m.group(1)] = f
        paired = {f for pair in sides.values() if len(pair) == 2 for f in pair.values()}
        for rest, pair in sorted(sides.items()):
            if len(pair) == 2:
                out.append(f"- VOID: pair `{rest}` — `{pair['before'].relative_to(root)}` and "
                           f"`{pair['after'].relative_to(root)}` are byte-identical")
        others = [f for f in same if f not in paired]
        if len(others) > 1:
            out.append("- VOID: byte-identical under different names: "
                       + ", ".join(f"`{f.relative_to(root)}`" for f in others))
    return out


def _ui_evidence(root: Path, base_ref: str | None, plans: list[Path]) -> str:
    """The screenshots this change carries: the before/after evidence pair the
    DoD asks for (D8: `.process-work/reviews/<slug>/`) and every image the
    diff adds or changes (pixel baselines). A reviewer judges a UI story
    against the rendered state, and "matches the intent" needs the after
    picture beside the spec — listing the paths is what makes that judgment
    possible instead of skipped."""
    lines: list[str] = []
    pairs = 0
    for plan in plans:
        stem = plan.parent.name if plan.name == "plan.md" else plan.stem
        slug = re.sub(r"^\d{4}-\d{2}-\d{2}-", "", stem)
        for cand in (root / EVIDENCE_DIR / slug, root / EVIDENCE_DIR / stem):
            if cand.is_dir():
                imgs = sorted(p for p in cand.rglob("*") if p.is_file() and IMAGE_RE.search(p.name))
                if imgs:
                    lines.append(f"Evidence for `{_shown(plan.name)}` in `{cand.relative_to(root)}/`:")
                    lines += [f"- {p.relative_to(root)}" for p in imgs]
                    pairs += len(imgs)
                    void = _void_evidence(root, imgs)
                    if void:
                        lines.append("**Void evidence — these prove nothing; a UI story resting on "
                                     "them is not done (DoD D8), a pass on them is a finding:**")
                        lines += void
                break
    changed: list[str] = []
    if base_ref:
        # -z through the owner: a quoted non-ASCII name sends the reviewer
        # to a path that does not exist
        entries = _review_gate.name_status(_review_gate._git_bytes(root, "diff", "--name-status", "-z",
                                                                   f"{base_ref}...HEAD")) or []
        changed += [f"- {letter} {_shown(path)}" for letter, _source, path in entries if IMAGE_RE.search(path)]
    if changed:
        lines.append(f"Images added/modified/deleted by the diff ({len(changed)}):")
        lines += changed[:60]
        if len(changed) > 60:
            lines.append(f"- … {len(changed) - 60} more")
    contracts = _design_contracts(root, plans)
    if not lines and not contracts:
        return ("*(no screenshots: no evidence directory for the plan and no image "
                "in the diff — for a change with a UI surface this is a finding, "
                "not a pass; DoD D8)*")
    if contracts:
        lines.append("Design contracts governing this change (judge the AFTER picture "
                     "against the sealed reference board of each cited ID; a plan "
                     "citing no ID for a surface change is a finding):")
        lines += contracts
    if lines and not lines[-1].startswith("*(no screenshots"):
        lines.append("")
    lines.append("Judge the AFTER picture against the spec's intent and the four "
                 "states, not only against the acceptance floor; a baseline that "
                 "is byte-identical to another name proves nothing.")
    return "\n".join(lines)


def _design_contracts(root: Path, plans: list[Path]) -> list[str]:
    """The surface contracts and the IDs the plans cite — from the optional
    design-contracts module's gate, when installed; nothing otherwise."""
    gate = Path(__file__).resolve().parent / "check_design_contracts.py"
    if not gate.is_file():
        return []
    try:
        import check_design_contracts as _dc  # sibling; sys.path set at import
        texts = {str(p.relative_to(root)): p.read_text(encoding="utf-8", errors="replace")
                 for p in plans}
        return _dc.bundle_lines(root, texts)
    except Exception as exc:  # the bundle must not die on a module's oddity
        return [f"- (design-contracts unreadable: {exc})"]


USAGE = ("usage: make_review_bundle.py [--skip-preflight] [--base REF] [--plan SLUG] "
         "[--tier N] [--since REF] [-o FILE]")


def _opt(argv: list[str], flag: str) -> str | None:
    if flag not in argv:
        return None
    i = argv.index(flag)
    if i + 1 >= len(argv):
        raise SystemExit(f"{USAGE} — {flag} needs a value")
    return argv[i + 1]


def main(argv: list[str]) -> int:
    if "-h" in argv or "--help" in argv:
        print(USAGE)
        return 0
    skip_preflight = "--skip-preflight" in argv
    argv = [arg for arg in argv if arg != "--skip-preflight"]
    out_file = _opt(argv, "-o")
    # a stale output is unsafe whatever fails next (a bad flag, a red preflight):
    # the caller could hand the previous bundle — old head, old digest — to a
    # reviewer. Remove it before anything is validated (observed downstream).
    target = Path(out_file) if out_file else None
    partial = target.with_name(target.name + ".partial") if target else None
    if target is not None and partial is not None:
        target.unlink(missing_ok=True)
        partial.unlink(missing_ok=True)
    base = _opt(argv, "--base")
    plan_filter = _opt(argv, "--plan")
    since = _opt(argv, "--since")
    tier_opt = _opt(argv, "--tier")
    if tier_opt is not None and not (tier_opt.isascii() and tier_opt.isdigit()):
        raise SystemExit(f"{USAGE} — --tier needs an integer, got {tier_opt!r}")
    declared_tier = int(tier_opt) if tier_opt is not None else None
    # an unknown flag must be a hard error, not silently ignored — a typo'd
    # --base would hand the reviewer a bundle diffed against the wrong ref
    known = {"--base", "-o", "--plan", "--since", "--tier"}
    consumed = {i for f in known if f in argv
                for i in (argv.index(f), argv.index(f) + 1)}
    extra = [a for i, a in enumerate(argv) if i not in consumed]
    if extra:
        raise SystemExit(f"{USAGE} — unknown argument(s): {' '.join(extra)}")
    root = _repo_root(Path.cwd())
    if not skip_preflight:
        ok, status, detail = _preflight(root)
        if not ok:
            print(detail, file=sys.stderr)
            return status
    included = _plans_under_review(root, _resolve_base(root, base), plan_filter)
    text = build(root, base, plan_filter, since, included, declared_tier)
    for warn in (ln for ln in text.splitlines() if ln.startswith(("**SIZE WARNING:**", "**REFUTE WARNING:**", "DELTA_TOUCHES "))):
        print("make_review_bundle: " + warn.replace("**", ""), file=sys.stderr)
    # an over-wide bundle was invisible until a reviewer read it (downstream:
    # 14,103 lines, mostly other work's plans) — say size and plans at build time
    summary = (f"{text.count(chr(10)) + 1} lines; plans included: "
               + (", ".join(_shown(_rel(root, p)) for p in included) if included else "none")
               + (f"; tier asserted via --tier {declared_tier}" if declared_tier is not None else ""))
    if target is not None and partial is not None:
        try:  # atomic: a reader never sees half a bundle
            partial.write_text(text, encoding="utf-8")
            os.replace(partial, target)
        finally:
            partial.unlink(missing_ok=True)
        print(f"review bundle written to {out_file} — {summary}")
    else:
        print(text)
        # stderr: stdout is the bundle itself (attest.py --bundle reads it)
        print(f"review bundle: {summary}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
