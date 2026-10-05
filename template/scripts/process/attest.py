#!/usr/bin/env python3
"""attest: write the REVIEW line — computed, validated, never typed.

Why a writer exists: the REVIEW attestation is the artifact the review gate
enforces, and every field of it was typed by hand. Two failure classes grew
there. Malformed lines (the gate catches those). And digests that were never
computed: on one deployment, 15 of 16 recorded `diff=` values matched no
byte stream of any commit within five days of the record — plausible hex,
written to look right. The gate reported the mismatch every run; because it
stayed red for months, nobody read it any more. Evidence that can be typed
will be typed.

This tool closes the typing path. It takes the review's fields as flags,
takes base/head from the bundle's `REVIEW_ARTIFACT` line (or `--base`/
`--head`), RECOMPUTES the digest with the gate's own formula
(`check_review.artifact_digest` — one owner for producer, writer and
verifier), refuses when the bundle's digest does not match (the tree moved
since the bundle: rebuild it), validates the finished line through the
gate's parser, and appends it to the journal shard. What this cannot do —
and does not claim — is prove the review happened; it proves the line was
produced from the artifact it names.

The round is counted, not claimed: round = 1 + the blocking REVIEW lines
already recorded for this work. A re-check after a pass, a rebase or a
"short look" keeps the round — only a block starts a new one — and a block
that was never attested cannot be skipped over (observed downstream: rounds
numbered 6 with one line in the journal, re-checks counted as rounds, plan
and code rounds on one counter). Plan reviews count apart (`--plan-review`
records work=<id>-plan).

Before any round after a block, each block's fix names its cause: a line
`ROOT-CAUSE work=<id> round=<r>: <cause> — <the test that failed before the fix>`
in the journal or the plan (a Spec Kit plan too). A fix that names no cause is a patch, and
patches on patches were the largest source of extra rounds downstream.
`--exception TEXT` overrides either rule; the reason is written above the
line as `REVIEW-EXCEPTION`, where it can be counted.

Usage:
  attest.py --work ID --tier N --reviewer R --model M --independence a,b
            --verdict pass|block [--round N] [--plan-review]
            [--bundle FILE | --base SHA --head SHA] [--note TEXT]
            [--exception TEXT] [--journal-dir DIR] [--dry-run]
            [--archive PLAN] [--commit]

`--archive PLAN` (a pass only) moves the plan into the archive with the line;
`--commit` makes that one commit. Every refusal comes before the first write.
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling import
from process_git import git_environment  # noqa: E402
from check_review import (  # noqa: E402  (one owner for grammar, digest, record homes)
    JOURNAL_DIR,
    integration_targets,
    PLANS_ARCHIVE,
    _plan_work_ids,
    branch_issue,
    plan_stem,
    PLANS_ACTIVE,
    SPEC_PLAN,
    SPECS_DIR,
    artifact_digest,
    parse_review_lines,
    readable,
    record_kind,
    record_texts,
    tier3_delta_problem,
)

# read like a REFUTE line (make_review_bundle.REFUTE_LINE): at most three
# spaces in (four is a code block), an optional list marker, a real work id
# and real content — the brief's `<cause>` placeholder, a TODO or an ellipsis
# is a template, not a cause. Fenced blocks and HTML comments are removed
# before (check_review.readable): a quoted example is no record (downstream
# refute: a fenced, a commented and a placeholder line each passed round 2).
ROOT_CAUSE = re.compile(
    r"^ {0,3}(?:(?:[-*+]|\d+[.)])[ \t]+(?:\[[xX]\][ \t]+)?)?ROOT-CAUSE[ \t]+"
    r"work=(?P<work>(?!<)(?!TODO\b)\S+)[ \t]+round=(?P<round>\d+):[ \t]*(?!<|TODO\b|…|\.\.\.)\S",
    re.MULTILINE)

ARTIFACT_LINE = re.compile(
    r"^REVIEW_ARTIFACT\s+base=(?P<base>\S+)\s+head=(?P<head>\S+)\s+diff=(?P<diff>\S+)(?:\s+mode=(?P<mode>full|delta))?\s*$",
    re.MULTILINE)


def _git(root: Path, *args: str) -> str | None:
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, env=git_environment())
    return r.stdout.strip() if r.returncode == 0 else None


def _journal_target(root: Path, journal_dir: Path) -> Path:
    """Today's shard: on a work branch always its own directory
    (journal-state-plans.md) — two parallel branches appending one shared daily
    file collide at merge (observed downstream: attestations of parallel
    reviews conflicting in the same file). A numbered branch writes
    `issue-<N>/`: one issue, one shard, found without knowing the slug (two
    branches of one issue wrote two shards downstream). Any other branch writes
    its slug; the integration branch or a detached HEAD, the flat daily file."""
    today = dt.date.today().isoformat()
    branch = _git(root, "symbolic-ref", "--short", "HEAD") or ""
    issue = branch_issue(branch)
    if issue:
        return journal_dir / f"issue-{issue}" / f"{today}.md"
    slug = branch.replace("/", "-")
    if slug and f"refs/heads/{branch}" not in integration_targets(root):
        return journal_dir / slug / f"{today}.md"
    return journal_dir / f"{today}.md"


def _archive_target(root: Path, plan: Path) -> Path:
    """Where `--archive` moves a plan. A Spec Kit plan is always `plan.md`: it takes
    its feature directory's name, or every Spec Kit plan would collide in the archive."""
    resolved = plan.resolve()
    if resolved.name == SPEC_PLAN and resolved.parent.parent == (root / SPECS_DIR).resolve():
        return root / PLANS_ARCHIVE / f"{resolved.parent.name}.md"
    return root / PLANS_ARCHIVE / plan.name


def _shown(root: Path, p: Path) -> str:
    return str(p.relative_to(root)) if p.is_relative_to(root) else str(p)


def archive_problems(args, root: Path) -> list[str]:
    """Checked before anything is written: a late failure left a written line, and the
    corrected rerun doubled it (downstream)."""
    if not args.archive:
        return []
    plan = root / args.archive
    if not plan.is_file():
        return [f"--archive: plan not found: {args.archive}"]
    rel = plan.resolve().relative_to(root.resolve()).as_posix() \
        if plan.resolve().is_relative_to(root.resolve()) else ""
    if record_kind(rel) not in ("plan", "spec-plan"):
        return [f"--archive: {args.archive} is no active plan (a file in {PLANS_ACTIVE}/ or "
                f"{SPECS_DIR}/<feature>/{SPEC_PLAN}) — only a plan is archived"]
    if args.plan_review:
        return ["--archive goes with the code review's pass, not the plan review's"]
    ids = _plan_work_ids(plan_stem(rel), plan.read_text(encoding="utf-8", errors="replace"),
                         include_dedated=True)
    if args.work not in ids:
        return [f"--archive: {args.archive} is not the plan of work={args.work} (its ids: "
                f"{', '.join(sorted(ids))}) — archive a plan with its own work's pass"]
    if _git(root, "ls-files", "--error-unmatch", "--", rel) is None:
        return [f"--archive: {args.archive} is not tracked — commit it first; `git mv` would "
                f"fail after the line is written"]
    if args.verdict != "pass":
        return [f"--archive only with verdict=pass — a plan is archived when its work "
                f"merges, not during a review round (verdict={args.verdict})"]
    target = _archive_target(root, plan)
    if target.exists():
        return [f"--archive: {_shown(root, target)} exists already — the move would "
                f"overwrite another plan"]
    return []


def _texts(root: Path, journal_dir: Path) -> list[str]:
    """Every file where REVIEW and ROOT-CAUSE lines live — journal shards,
    plans (active and archived), Spec Kit plans; check_review owns the list.
    The journal raw, as the gate reads REVIEW lines there: a block the gate
    counts is a block here too, or a round slips through without its root
    cause (refutation). Plans, which the gate does not read for REVIEW
    lines, as rendered: a commented example there is no round.
    `--journal-dir` replaces the repository's journal (it does not add to
    it) — a known limit of the override, meant for tests and dry runs."""
    return [text if record_kind(rel) == "journal" or rel.startswith(str(journal_dir)) else readable(text)
            for rel, text in record_texts(root, journal_dir=journal_dir) or []]


def round_problems(args, root: Path, journal_dir: Path) -> tuple[int, list[str]]:
    """(the counted round, what is wrong with the claimed one)."""
    texts = _texts(root, journal_dir)
    # distinct rounds, not lines: several reviewers (lenses) of one round each
    # write their block line — that is one round (observed downstream: 21
    # duplicated block lines would have over-counted)
    blocks = sorted({int(f["round"]) for t in texts for _ln, f in parse_review_lines(t)[0]
                     if f["work"] == args.work and f["verdict"] == "block"})
    counted = 1 + len(blocks)
    last = blocks[-1] if blocks else None
    problems: list[str] = []
    claimed = str(args.round_) if args.round_ is not None else str(counted)
    # the next round, or another reviewer (lens) of the round that just blocked
    allowed = {str(counted)} | ({str(last)} if last is not None else set())
    if claimed not in allowed:
        problems.append(
            f"round {args.round_} claimed, but {len(blocks)} blocking round(s) are recorded for "
            f"work={args.work} — this is round {counted}"
            + (f" (or {last}, for another reviewer of that round)" if last is not None else "")
            + ". A re-check after a pass or a rebase keeps the round; a block that was never "
            "attested is attested first (its own --base/--head); omit --round to use the count")
    target = int(claimed) if claimed.isdigit() else counted
    # a cause is read as rendered: a quoted example or a commented line is no cause
    causes = {(m.group("work"), int(m.group("round"))) for t in texts for m in ROOT_CAUSE.finditer(readable(t))}
    missing = [r for r in blocks if r < target and (args.work, r) not in causes]
    if missing:
        problems.append(
            "no root cause for the fix of blocking round(s) " + ", ".join(map(str, missing))
            + f" — before the next round write `ROOT-CAUSE work={args.work} round=<r>: <cause> — <the test "
            "that failed before the fix>` into the journal or the plan (docs/process/review-checklist.md, "
            "round economy)")
    return counted, problems


def build_line(args, root: Path, journal_dir: Path | None = None) -> tuple[str, list[str]]:
    """(REVIEW line, problems). The digest is computed here, never copied."""
    problems: list[str] = []
    fields = [f"work={args.work}", f"tier={args.tier}", f"reviewer={args.reviewer}",
              f"model={args.model}", f"independence={args.independence}",
              f"verdict={args.verdict}", f"round={args.round_}"]
    base = head = None
    bundle_digest = None
    mode = "full"
    if args.bundle:
        text = Path(args.bundle).read_text(encoding="utf-8", errors="replace")
        m = ARTIFACT_LINE.search(text)
        if not m:
            problems.append(f"no REVIEW_ARTIFACT line in {args.bundle}")
        else:
            base, head, bundle_digest = m.group("base"), m.group("head"), m.group("diff")
            mode = m.group("mode") or "full"
    if args.base or args.head:
        if not (args.base and args.head):
            problems.append("--base and --head go together")
        base, head = args.base, args.head
    if base and head and not problems:
        digest = artifact_digest(root, base, head, mode=mode)
        if digest is None:
            problems.append(f"cannot compute the diff {base[:9]}...{head[:9]} in this "
                            f"clone — the commits must exist here")
        else:
            if bundle_digest and bundle_digest != digest:
                problems.append(f"the bundle's digest {bundle_digest[:12]}… differs from "
                                f"the recomputed {digest[:12]}… for the same base/head — "
                                f"the bundle is stale or its line was edited; rebuild "
                                f"the bundle and review again")
            fields += [f"base={base}", f"head={head}", f"diff={digest}"]
            if mode == "delta":
                fields.append("mode=delta")
    line = "REVIEW " + " ".join(fields)
    records, errors = parse_review_lines(line)
    for _ln, msg in errors:
        problems.append(f"malformed: {msg}")
    for _ln, f in records:
        if f.get("mode") == "delta" and int(f["tier"]) >= 3:
            known = [r for t in _texts(root, journal_dir or (root / JOURNAL_DIR).resolve())
                     for _l, r in parse_review_lines(t)[0]]
            why = tier3_delta_problem(root, known, {f["work"]}, f["base"], f["head"])
            if why:
                problems.append(f"malformed: {why}")
    return line, problems


def main() -> int:
    ap = argparse.ArgumentParser(description="write a computed, validated REVIEW line")
    ap.add_argument("--work", required=True)
    ap.add_argument("--tier", required=True)
    ap.add_argument("--reviewer", default="fresh-agent")
    ap.add_argument("--model", required=True)
    ap.add_argument("--independence", required=True)
    ap.add_argument("--verdict", required=True)
    ap.add_argument("--round", default=None, dest="round_",
                    help="optional: checked against the count of recorded blocks for this work")
    ap.add_argument("--plan-review", action="store_true",
                    help="a review of the plan, not the code: counted apart as work=<id>-plan")
    ap.add_argument("--exception", help="override the round/root-cause rules; the reason is recorded")
    ap.add_argument("--bundle")
    ap.add_argument("--base")
    ap.add_argument("--head")
    ap.add_argument("--note", help="prose paragraph written above the line")
    ap.add_argument("--archive", help="with a pass: git-mv this plan into the archive")
    ap.add_argument("--commit", action="store_true",
                    help="one commit of the line (and the archived plan); default with "
                         "--archive: staged, the commit named")
    ap.add_argument("--journal-dir", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("root", nargs="?", default=str(ROOT))
    args = ap.parse_args()
    root = Path(args.root).resolve()
    journal_dir = Path(args.journal_dir) if args.journal_dir else Path(JOURNAL_DIR)
    if not journal_dir.is_absolute():
        journal_dir = root / journal_dir
    journal_dir = journal_dir.resolve()
    if args.plan_review:
        # always: a plan whose own id ends in `-plan` would otherwise have its
        # plan review clear its code (refutation)
        args.work += "-plan"
    counted, round_issues = round_problems(args, root, journal_dir)
    exception_note = ""
    if args.exception:
        # always written: an owner exception that trips no rule here (a round
        # beyond the cap) must be countable too, never lost in silence
        overrides = "; ".join(round_issues) if round_issues else "no attest rule tripped"
        exception_note = (f"REVIEW-EXCEPTION work={args.work} round={args.round_ or counted}: "
                          f"{args.exception} (overrides: {overrides})")
        round_issues = []
    args.round_ = counted if args.round_ is None else args.round_
    line, problems = build_line(args, root, journal_dir)
    problems = round_issues + problems + archive_problems(args, root)
    if args.note and any(ln.lstrip().startswith("REVIEW") for ln in args.note.splitlines()):
        problems.append("the note carries REVIEW-looking lines — the validated line is the "
                        "only REVIEW writer")
    if problems:
        print("attest: REFUSED — nothing written:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1
    target = _journal_target(root, journal_dir)
    print(line)
    if args.dry_run:
        print(f"attest: dry run — would append to {target.relative_to(root) if target.is_relative_to(root) else target}")
        return 0
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as fh:
        if target.stat().st_size == 0:
            fh.write(f"# {dt.date.today().isoformat()}\n\n")
        if exception_note:
            fh.write(exception_note + "\n\n")
        if args.note:
            fh.write(args.note.rstrip() + "\n\n")
        fh.write(line + "\n")
    print(f"attest: appended to {_shown(root, target)}")
    if not (args.archive or args.commit):
        return 0
    staged = [str(target)] if target.is_relative_to(root) else []
    if args.archive:
        dest = _archive_target(root, root / args.archive)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not _git_ok(root, "mv", args.archive, str(dest)):
            return 1
        print(f"attest: archived {args.archive} as {_shown(root, dest)}")
    if staged and not _git_ok(root, "add", "--", *staged):
        return 1
    if args.archive:
        staged += [str(root / args.archive), str(dest)]  # the rename, staged by git mv
    message = f"docs: attest {args.work} round {args.round_}" + (
        " and archive the plan" if args.archive else "")
    if args.commit:
        # only the attestation's own paths: anything else staged stays staged
        # (refutation: a staged source file rode along into this commit)
        if not _git_ok(root, "commit", "-q", "-m", message, "--", *staged):
            return 1
        print(f"attest: committed: {message}")
    else:
        print(f'attest: staged — commit with: git commit -m "{message}"')
    return 0


def _git_ok(root: Path, *args: str) -> bool:
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, env=git_environment())
    if r.returncode != 0:
        print(f"attest: git {' '.join(args)} failed: {r.stderr.strip()} — the line is "
              f"written; finish the step by hand", file=sys.stderr)
    return r.returncode == 0


if __name__ == "__main__":
    raise SystemExit(main())
