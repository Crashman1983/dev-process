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
  5. the active plan(s) under review;
  6. the diff (BASE...HEAD, three-dot: what the branch adds);
  7. the output grammar: the REVIEW line imported from check_review.py (the
     gate that parses it — that half cannot drift), plus the FINDING line whose
     owner is the github-issues module's report gate (journal-state-plans.md);
     a template test pins the FINDING tokens to that gate's enums.

Sources that cannot be read are named in place, never silently skipped.

Usage:
    make_review_bundle.py [--base REF] [--plan SLUG] [-o FILE]

--plan narrows the bundled plans to filenames containing SLUG — for parallel
efforts, so the reviewer sees the one plan under review, not all of them.

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

# check_review.py owns the REVIEW grammar; check_kernel.py owns kernel-block
# extraction — importing both keeps this tool byte-honest with the gates
sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling import
import check_kernel as _kernel_gate  # noqa: E402
import check_review as _review_gate  # noqa: E402
import gate_invoke as _launch  # noqa: E402  (one owner for "how to start the runner")

CHECKLIST = "docs/process/review-checklist.md"
PRODUCT = "PRODUCT.md"
PLANS = _review_gate.PLANS_ACTIVE
REVIEWS = ".process-work/reviews"
DEFAULT_BASES = ("origin/main", "main", "origin/master", "master")
PREFLIGHT_TIMEOUT_S = 600
DELTA_MAX_TIER = 2


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
                           encoding="utf-8", errors="replace")
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
    candidates = (base,) if base else DEFAULT_BASES
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
    return rel if _review_gate.record_kind(rel) == "spec-plan" else plan.name


def _spec_dirs_touched(root: Path, base_ref: str | None) -> set[str]:
    """Spec directories the branch changes (`base_ref...HEAD`); empty when
    there is no base or git cannot tell (the in-flight rule still holds)."""
    if not base_ref:
        return set()
    out = _git_bytes(root, "diff", "--name-only", "--no-renames", "-z", f"{base_ref}...HEAD",
                     "--", _review_gate.SPECS_DIR)
    names = (n.decode("utf-8", errors="surrogateescape") for n in (out or b"").split(b"\0"))
    return {n.split("/")[1] for n in names if n.count("/") >= 2}


def _spec_in_flight(plan: Path) -> bool:
    """Its tasks.md still has an unticked task."""
    try:
        tasks = (plan.parent / "tasks.md").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return bool(_review_gate.UNCHECKED.search(_review_gate._unfenced(tasks)))


def _active_plans(root: Path, plan_filter: str | None, base_ref: str | None = None) -> list[Path]:
    """The plans under review — as check_review lists the homes:
      - every active plan in `.process-work/plans/` (archive/ is finished
        work — the archive step is what ends a plan's review life);
      - a Spec Kit plan `specs/<dir>/plan.md` only when this branch touches
        `specs/<dir>/` (`base...HEAD`) or its tasks.md has an unticked task.
        Spec Kit plans are never archived, so a finished one — or a product
        document that happens to live at specs/<x>/plan.md — would otherwise
        be bundled, refuted and tier-checked forever (downstream refute);
      - with `--plan`, whatever matches it, under review or not: asked for
        by name (a plan's file name; a Spec Kit plan's directory or its
        printed label `specs/<dir>/plan.md`)."""
    touched = _spec_dirs_touched(root, base_ref)
    plans: list[Path] = []
    for rel, f in _review_gate.record_files(root, _review_gate.PLAN_KINDS):
        spec = _review_gate.record_kind(rel) == "spec-plan"
        if plan_filter:
            # parallel efforts: 8 active plans would bury the reviewer in 7
            # irrelevant ones — --plan narrows to the effort under review
            if plan_filter in (rel if spec else f.name):
                plans.append(f)
        elif not spec or f.parent.name in touched or _spec_in_flight(f):
            plans.append(f)
    return plans


_TIER_RE = _review_gate.TIER_DECL


def _declared_tier(texts: list[str]) -> int | None:
    tiers = [int(match.group(1)) for text in texts for match in _TIER_RE.finditer(text)]
    return max(tiers) if tiers else None


_DATED = re.compile(r"^\d{4}-\d{2}-\d{2}-")


IssueKey = tuple[str | None, int]  # (owner/repo lowercased, or None for this repo's `#N`; number)


def _issue_key(ref: str) -> IssueKey | None:
    """An issue ref as a comparable key: `#9` and `9` are this repository's
    issue 9; `owner/repo#9` and the issue URL name that repository's."""
    parsed = _review_gate.parse_issue_ref(ref)
    if parsed is not None:
        return (parsed[0].lower() if parsed[0] else None, parsed[1])
    return (None, int(ref)) if ref.isascii() and ref.isdigit() else None


def _plan_issue_keys(text: str) -> list[IssueKey]:
    keys = (_issue_key(m.group(1)) for m in _review_gate.ISSUE_DECL.finditer(_review_gate._unfenced(text or "")))
    return list(dict.fromkeys(k for k in keys if k is not None))


def _slug_in_name(slug: str, stem: str) -> bool:
    """`slug` is the file stem or a whole dash-separated part run of it —
    `api` names `api-round-2`, not `rapid-fix`."""
    return stem == slug or re.search(rf"(?:^|-){re.escape(slug)}(?:-|$)", stem) is not None


def _review_report_for(root: Path, slugs: list[str], issues: list[IssueKey]) -> Path | None:
    """The previous round's report of THIS work item — never another one's.

    Reports are `YYYY-MM-DD-<slug>.md` with a header block (`review: <slug>`,
    `work: <issue or plan slug>`). A report whose header names its `work:`
    belongs to that work alone: it is this item's when a value is one of this
    item's issues (the same repository: `other/repo#9` is not this repo's #9)
    or plan slugs, exactly, and never otherwise, whatever its name says.
    Without a `work:` header the file name decides: `<N>-…`, `issue-<N>` or a
    whole slug part; or the `review:` value equals a plan slug. Issues are
    tried before slugs; the newest match wins. Taking simply the newest
    report put an unrelated item's findings into a delta bundle (observed
    downstream), and so did a slug matched inside another word. No match
    means no report, said so — not a stranger's."""
    if not (root / REVIEWS).is_dir():
        return None
    reports = sorted(p for p in (root / REVIEWS).rglob("*.md") if p.is_file())
    slugs = [s for s in dict.fromkeys(slugs) if s]
    bare = {n for repo, n in issues if repo is None}

    def stem(p: Path) -> str:
        return _DATED.sub("", p.stem)

    by_issue: list[Path] = []
    by_slug: list[Path] = []
    for p in reports:
        head = _report_header(p)
        works = head.get("work", [])
        if works:
            if any(_issue_key(w) in issues for w in works):
                by_issue.append(p)
            elif any(w in slugs for w in works):
                by_slug.append(p)
            continue  # another work's report, whatever its file name says
        s = stem(p)
        if any(s == str(n) or s.startswith(f"{n}-") or _slug_in_name(f"issue-{n}", s) for n in bare):
            by_issue.append(p)
        elif any(_slug_in_name(slug, s) for slug in slugs) or \
                any(v in slugs for v in head.get("review", [])):
            by_slug.append(p)
    hits = by_issue or by_slug
    return hits[-1] if hits else None


_HEADER_KEY = re.compile(r"^\s*(?:[-*+]\s+)?[*_]*(review|audit|work)[*_]*\s*:\s*(\S+)", re.IGNORECASE)


_MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")


def _report_header(path: Path) -> dict[str, list[str]]:
    """The `review:`/`audit:`/`work:` values of a report's header block — the
    lines from the top to the first blank one (the documented report format,
    journal-state-plans.md; the report gate reads the same block). The report
    names its work there, not necessarily in its file name (downstream: a
    round-1 report named after the review, `work: #N` in the header, was not
    found by the delta bundle)."""
    try:
        text = _review_gate._unfenced(path.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return {}
    out: dict[str, list[str]] = {}
    for line in text.splitlines():
        if not line.strip():
            break
        m = _HEADER_KEY.match(line)
        if m:
            key = "review" if m.group(1).lower() == "audit" else m.group(1).lower()
            # `[#9](url)` names #9, and `#9,` too — a link or a trailing
            # comma must not unbind the report from its work (refutation)
            value = _MD_LINK.sub(r"\1", m.group(2)).strip().rstrip(".,;:")
            out.setdefault(key, []).append(_DATED.sub("", value))
    return out


def _review_artifact(root: Path, base_ref: str, *, delta: bool = False) -> tuple[str, str, str, bytes] | None:
    """Resolved endpoints, SHA-256, and exact bytes of the reviewed diff."""
    base = _git(root, "rev-parse", base_ref) if delta else _git(root, "merge-base", base_ref, "HEAD")
    head = _git(root, "rev-parse", "HEAD")
    if not base or not head:
        return None
    base_sha = base.strip()
    head_sha = head.strip()
    # ONE formula, owned by the gate that verifies it (check_review.artifact_diff):
    # canonical three-dot diff with every git-config knob pinned. A delta bundle
    # (`since` is an ancestor of HEAD) yields the same bytes as `since..HEAD`.
    diff = _review_gate.artifact_diff(root, base_sha, head_sha)
    if diff is None:
        return None
    return base_sha, head_sha, hashlib.sha256(diff).hexdigest(), diff


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

    FINDING sev=<blocker|major|minor|nit> action=<fix|accept|follow-up> issue=<ref|-> gate=<judgement|possible|name> <title>

- `gate`: could a linter, type checker or gate rule have produced this finding?
  `judgement` = no, it needed a reader; `possible` = yes, but no rule exists
  yet; otherwise the name of the rule that now catches it. `possible` is the
  one that matters: it marks a finding every future change will pay a reader
  to rediscover until somebody writes the rule.

Judge against the checklist and the rules above; cite file:line evidence; a
`pass` with unfixed blockers is a false green — verdict `block` instead."""


# above this a review stops being one review: downstream, the works that ran
# five to seven rounds were 3,000–5,500 changed lines or a batch of issues
REVIEW_MAX_FILES = int(os.environ.get("PROCESS_REVIEW_MAX_FILES", "30"))
REVIEW_MAX_LINES = int(os.environ.get("PROCESS_REVIEW_MAX_LINES", "1500"))
SIZE_IGNORED = re.compile(r"^\.process-work/|(^|/)(package-lock\.json|uv\.lock|poetry\.lock|yarn\.lock|"
                          r"pnpm-lock\.yaml|Cargo\.lock|go\.sum)$")


# gate code as `docs/process/refute.md` defines it, approximated by path: the
# gates, the hooks, and what starts them (make targets, CI, pre-commit)
GATE_PATHS = ("scripts/process/", ".githooks/", ".github/workflows/")
GATE_FILES = ("Makefile", ".pre-commit-config.yaml")
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
                  if n and (n.startswith(GATE_PATHS) or n in GATE_FILES))


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


def review_size(root: Path, base_ref: str) -> tuple[int, int]:
    """(files, changed lines) of the whole branch — process bookkeeping,
    lock files and binaries left out."""
    files = lines = 0
    for ln in (_git(root, "diff", "--numstat", f"{base_ref}...HEAD") or "").splitlines():
        parts = ln.split("\t")
        if len(parts) < 3 or SIZE_IGNORED.search(parts[2]):
            continue
        files += 1
        if parts[0].isdigit() and parts[1].isdigit():
            lines += int(parts[0]) + int(parts[1])
    return files, lines


def build(root: Path, base: str | None, plan_filter: str | None = None,
          since: str | None = None) -> str:
    out: list[str] = []
    add = out.append
    sized = _resolve_base(root, base)
    plans = _active_plans(root, plan_filter, sized or since)
    plan_texts = {plan: _read_plan(plan) for plan in plans}
    tier = _declared_tier(list(plan_texts.values()))
    tiers = {_label(root, plan): _declared_tier([text]) for plan, text in plan_texts.items()}
    if since and tier is not None and tier > DELTA_MAX_TIER:
        top = next(_label(root, p) for p, t in plan_texts.items() if _declared_tier([t]) == tier)
        raise SystemExit(
            f"make_review_bundle: --since refused — bundled plan {top} declares tier: {tier}; "
            "Tier 3 reviews require a full diff. If that plan is not the work under review, "
            "name the one that is with --plan <name>"
        )

    add("# Review bundle — read-only\n")
    add("You are an INDEPENDENT reviewer. This bundle is your complete input: "
        "do not consult the implementing agent's context, do not edit anything, "
        "and do not trust claims you can check in the diff. Your deliverable is "
        "a verdict plus findings in the exact grammar at the end.\n")
    if since:
        add("**Delta re-review.** The diff below is limited to changes since "
            f"`{since}`. Previous findings and the full branch file surface are "
            "included so fixes are judged in their original scope.\n")

    if sized is not None:
        files, lines = review_size(root, sized)
        if files > REVIEW_MAX_FILES or lines > REVIEW_MAX_LINES:
            add(f"**SIZE WARNING:** this branch changes {files} files / {lines} lines (limit "
                f"{REVIEW_MAX_FILES} / {REVIEW_MAX_LINES}, `PROCESS_REVIEW_MAX_FILES`/`_LINES`). "
                "Reviews this large ran five to seven rounds downstream. Split it before the "
                "first round if the plan allows; otherwise say so in the verdict and review "
                "it slice by slice.\n")

    if sized is not None or since:
        # a delta re-review: the fix round's own gate code, refuted anew
        gate_files = _gate_files(root, since or sized)
        before = _plans_at(root, since) if since else None
        if since and before is None:
            gate_files = None
        missing = _unrefuted(root, plan_texts, before) if plan_texts else ["(no active plan)"]
        # by tier (`docs/process/refute.md`): from Tier 2 on, one refute before
        # the first review round. A delta asks no new one — below Tier 3 there
        # is one run, and a Tier 3 review never takes a delta (DELTA_MAX_TIER)
        by_tier = [] if since else [label for label in missing if (tiers.get(label) or 0) >= 2]
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
            named = ", ".join(f"{label} (tier: {tiers[label]})" for label in by_tier[:3])
            add(f"**REFUTE WARNING:** {named}{' …' if len(by_tier) > 3 else ''} carries no "
                "`REFUTE work=<its id> round=<r>: …` line — from Tier 2 on, a fresh agent attacks "
                "the change before its first review round (`docs/process/refute.md`). Say in the "
                "verdict that it was not.\n")

    kernel = _kernel_block(root)
    add("## The binding rules (kernel)\n")
    add(kernel + "\n" if kernel else "*(unavailable: docs/process/kernel.md has no readable kernel block)*\n")

    checklist = _read(root, CHECKLIST)
    add("## What a review checks\n")
    add(checklist + "\n" if checklist else "*(unavailable: docs/process/review-checklist.md missing)*\n")

    product = _read(root, PRODUCT)
    add("## Product frame (judge direction against this)\n")
    add(product + "\n" if product else "*(unavailable: PRODUCT.md missing)*\n")

    add("## Plan(s) under review\n")
    if plans:
        for p in plans:
            add(f"### {_label(root, p)}\n")
            add((plan_texts[p] or "*(unreadable)*") + "\n")
    elif plan_filter:
        add(f"*(no active plan matches --plan {plan_filter!r} — check the "
            f"filter, or drop it to bundle every active plan)*\n")
    else:
        add(f"*(no active plan in {PLANS} or {_review_gate.SPECS_DIR}/*/plan.md — review the diff against "
            "the checklist and rules alone, and say so in your verdict)*\n")

    if since:
        add("## Findings from the previous round\n")
        slugs = [_DATED.sub("", plan_filter)] if plan_filter else []
        slugs += [_DATED.sub("", _review_gate.plan_stem(_rel(root, p))) for p in plan_texts]
        issues = list(dict.fromkeys(k for text in plan_texts.values() for k in _plan_issue_keys(text)))
        report = _review_report_for(root, slugs, issues)
        report_text = _read(root, str(report.relative_to(root))) if report else None
        if report_text:
            add(f"### {report.relative_to(root)}\n{report_text}\n")
        else:
            named = ", ".join([*dict.fromkeys(s for s in slugs if s),
                               *(f"{repo or ''}#{n}" for repo, n in issues)]) or "no plan or issue"
            add(f"*(no review report for this work item ({named}) under {REVIEWS}; prior "
                f"findings unavailable — deliberately not another item's report)*\n")

    resolved = _resolve_base(root, base)
    add("## Diff under review\n")
    if resolved is None:
        add("*(unavailable: no usable base ref — pass --base explicitly; "
            "git may be absent or the repo unborn)*\n")
    else:
        artifact = _review_artifact(root, since or resolved, delta=bool(since))
        if artifact is None:
            add(f"*(unavailable: `git diff {resolved}...HEAD` failed)*\n")
        else:
            base_sha, head_sha, digest, diff_bytes = artifact
            add(f"REVIEW_ARTIFACT base={base_sha} head={head_sha} diff={digest}\n")
            if since:
                add(f"REVIEW_SCOPE mode=delta since={base_sha} head={head_sha}\n")
            diff = diff_bytes.decode("utf-8", errors="replace")
            if not diff.strip():
                add(f"*(empty: HEAD adds nothing over {resolved})*\n")
            else:
                lines = diff.count("\n")
                label = (f"Delta: `{since}..HEAD`" if since else
                         f"Base: `{resolved}` resolved to `{base_sha}` (three-dot: what the branch adds)")
                add(f"{label}. "
                    f"{lines} diff lines.\n")
                if since:
                    stat = _git(root, "diff", "--stat", f"{resolved}...HEAD")
                    if stat and stat.strip():
                        add("Full branch surface:\n```\n" + stat.rstrip() + "\n```\n")
                if lines > 4000:
                    add("*(large diff — consider a per-area pass; nothing was truncated)*\n")
                status = _git(root, "status", "--porcelain")
                if status and status.strip():
                    add("*(working tree dirty — uncommitted changes are NOT in this "
                        "diff; only committed work is under review)*\n")
                # a diff of a markdown file carries its own ``` runs, which would
                # close a plain fence early and corrupt everything after it — fence
                # with more backticks than the longest run inside (min 4)
                longest = max((len(m) for m in re.findall(r"`+", diff)), default=0)
                fence = "`" * max(4, longest + 1)
                add(f"{fence}diff\n" + diff + ("\n" if not diff.endswith("\n") else "") + fence + "\n")

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
                    lines.append(f"Evidence for `{plan.name}` in `{cand.relative_to(root)}/`:")
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
        names = _git(root, "diff", "--name-status", f"{base_ref}...HEAD") or ""
        for ln in names.splitlines():
            parts = ln.split("\t")
            if len(parts) >= 2 and IMAGE_RE.search(parts[-1]):
                changed.append(f"- {parts[0][0]} {parts[-1]}")
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


USAGE = "usage: make_review_bundle.py [--skip-preflight] [--base REF] [--plan SLUG] [--since REF] [-o FILE]"


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
    # an unknown flag must be a hard error, not silently ignored — a typo'd
    # --base would hand the reviewer a bundle diffed against the wrong ref
    known = {"--base", "-o", "--plan", "--since"}
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
    text = build(root, base, plan_filter, since)
    for warn in (ln for ln in text.splitlines() if ln.startswith(("**SIZE WARNING:**", "**REFUTE WARNING:**"))):
        print("make_review_bundle: " + warn.replace("**", ""), file=sys.stderr)
    if target is not None and partial is not None:
        try:  # atomic: a reader never sees half a bundle
            partial.write_text(text, encoding="utf-8")
            os.replace(partial, target)
        finally:
            partial.unlink(missing_ok=True)
        print(f"review bundle written to {out_file}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
