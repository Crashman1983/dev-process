#!/usr/bin/env python3
"""attest: write the REVIEW line — computed, validated, never typed.

Why a writer exists: the REVIEW attestation is the artifact the review gate
enforces, and every field of it was typed by hand — malformed lines, and
values written to look right (downstream, 15 of 16 recorded digests matched
no commit). Evidence that can be typed will be typed.

This tool closes the typing path. It takes the review's fields as flags,
takes base/head from the bundle's `REVIEW_ARTIFACT` line (or `--base`/
`--head`), checks that both commits exist here and that a full round's base
is the fork point of its head, validates the finished line through the
gate's parser, and appends it to the journal shard. Two SHAs name the
reviewed change exactly; the diff digest older lines carry is no longer
written. What this cannot do — and does not claim — is prove the review
happened; it proves the line names a range that exists.

The round is counted, not claimed: round = 1 + the blocking REVIEW lines
already recorded for this work. A re-check after a pass, a rebase or a
"short look" keeps the round — only a block starts a new one (observed
downstream: rounds numbered 6 with one line in the journal, re-checks counted
as rounds, plan and code rounds on one counter). Plan reviews count apart
(`--plan-review` records work=<id>-plan). A claimed `--round` above the count
is corrected to the count, with a note; one below the last blocked round is
refused — a late pass of an old round must not outrank the blocks since.

Before any round after a block, each block's fix names its cause: a line
`ROOT-CAUSE work=<id> round=<r>: <cause> — <the test that failed before the fix>`
in the journal or the plan (a Spec Kit plan too). A fix that names no cause is a patch, and
patches on patches were the largest source of extra rounds downstream. A
missing cause is a note here, not a refusal: by the time a verdict is
attested the review has run, and refusing its record bought no cause — only a
mechanical round (downstream: a pass of two families refused over a cause
labelled round=6 instead of 5). The duty sits where the fix is made: the
execute session's `--dry-run` must name no missing cause before it reports.
`--exception TEXT` records an owner's override as `REVIEW-EXCEPTION`, where it
can be counted.

Usage:
  attest.py --work ID --tier N --reviewer R --model M --independence a,b
            --verdict pass|block [--round N] [--plan-review]
            [--bundle FILE | --base SHA --head SHA] [--note TEXT]
            [--exception TEXT] [--journal-dir DIR] [--dry-run]
            [--archive PLAN] [--commit] [--with PATH ...]

`--archive PLAN` (a pass only) moves the plan into the archive with the line;
`--with PATH` adds the round's other records — its review report, plan lines —
so the round is one commit and one push (each bookkeeping push paid the
push-time gates downstream; half the commits of two weeks were bookkeeping);
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
from check_fix_streak import notes as fix_streak_notes  # noqa: E402
from check_review import (  # noqa: E402  (one owner for grammar, digest, record homes)
    BOOKKEEPING,
    JOURNAL_DIR,
    full_round_base_problem,
    integration_targets,
    PLAN_KINDS,
    PLANS_ARCHIVE,
    ROOT_CAUSE_LINE,
    _known_work,
    _plan_work_ids,
    _unfenced,
    branch_issue,
    plan_stem,
    PLANS_ACTIVE,
    SPEC_PLAN,
    SPECS_DIR,
    DATE_PREFIX,
    _slug_in_name,
    work_key,
    parse_review_lines,
    readable,
    record_kind,
    record_texts,
)

# a ROOT-CAUSE line — the review gate owns its shape (`check_review.ROOT_CAUSE_LINE`),
# read through `readable`: a fenced, commented or placeholder line is no cause
ROOT_CAUSE = ROOT_CAUSE_LINE

# an older bundle's line also carries `diff=` and `mode=` — read past, never used
ARTIFACT_LINE = re.compile(
    r"^REVIEW_ARTIFACT\s+base=(?P<base>\S+)\s+head=(?P<head>\S+)(?:\s+diff=\S+)?(?:\s+mode=(?P<mode>full|delta))?\s*$",
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


def with_problems(args, root: Path) -> list[str]:
    """`--with` carries records only: a source file riding an attestation commit
    would be code no review saw, under a commit the tools read as bookkeeping."""
    out = []
    for rel in args.with_ or []:
        p = (root / rel).resolve()
        if not p.is_relative_to(root.resolve()) or not p.is_file():
            out.append(f"--with: {rel} is no file in this repository")
            continue
        r = p.relative_to(root.resolve()).as_posix()
        if not (r.startswith(BOOKKEEPING) or record_kind(r) is not None):
            out.append(f"--with: {rel} is not a process record (under {BOOKKEEPING} or a plan) — "
                       f"commit code with its own message")
    return out


def work_problems(args, root: Path) -> list[str]:
    """A `--work` no plan names clears nothing. A number no plan declares and the
    branch does not lead with is most likely the PR's number (observed: rounds
    attested as work=<PR>, which no gate ever matched) — refused; any other
    unknown id is a note, since a plan may still be written."""
    work = args.work[:-len("-plan")] if args.work.endswith("-plan") else args.work
    if work in _known_work(root):
        return []
    branch = _git(root, "symbolic-ref", "--short", "HEAD") or ""
    if work.isascii() and work.isdigit() and branch_issue(branch) != work:
        active = sorted({i for rel, text in record_texts(root, PLAN_KINDS) or []
                         for i in _plan_work_ids(plan_stem(rel), _unfenced(text), include_dedated=True)})
        return [f"work={work} names no plan or issue — it looks like a PR number; the work id "
                f"is the plan slug or its issue: line. Active plans: "
                f"{', '.join(active) if active else 'none'}. Issue work without a plan: "
                f"attest with --exception \"<reason>\""]
    print(f"attest: note — work={work} names no plan (active, archived or Spec Kit) yet; "
          f"no plan's review is cleared by it until one does", file=sys.stderr)
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


def round_ids(args, root: Path) -> set[str]:
    """The work ids whose rounds and root causes are this round's: a plan's slug
    and its issue are one work — switching `--work 9` to `--work widget`
    restarted the count at round 1 and skipped the root cause (refutation). But
    only within ONE plan: an issue shared by several plans would lend plan A's
    rounds to plan B (refutation). A slug names its plan (an active one first);
    an issue names the active plans declaring it, narrowed to the one whose slug
    the branch carries when several do. No single plan: the literal id alone."""
    work = args.work
    if work.endswith("-plan"):  # plan reviews count apart, literally
        return {work}
    key = work_key(work)
    plans = [(rel, _plan_work_ids(plan_stem(rel), _unfenced(text), include_dedated=True))
             for rel, text in record_texts(root, PLAN_KINDS + ("plan-archive",)) or []]
    hits = [(rel, ids) for rel, ids in plans if key in {work_key(i) for i in ids}]
    active = [(rel, ids) for rel, ids in hits if record_kind(rel) != "plan-archive"]
    cands = active if (isinstance(key, tuple) or active) else hits
    if len(cands) > 1:
        leaf = (_git(root, "symbolic-ref", "--short", "HEAD") or "").rsplit("/", 1)[-1]
        cands = [(rel, ids) for rel, ids in cands
                 if _slug_in_name(DATE_PREFIX.sub("", plan_stem(rel)), leaf)]
    return {work} | cands[0][1] if len(cands) == 1 else {work}


def round_problems(args, root: Path, journal_dir: Path) -> tuple[int, list[str], list[str]]:
    """(the round to write, notes, refusals). A claim above the count and a
    missing cause are bookkeeping about a review that already ran — notes, since
    a refusal there cost a whole mechanical round downstream and caught nothing.
    A claim below the last blocked round is refused: written as the count, a late
    pass of an old round would outrank the blocks recorded since (refutation)."""
    texts = _texts(root, journal_dir)
    mine = {work_key(w) for w in round_ids(args, root)}
    # distinct rounds, not lines: several reviewers (lenses) of one round each
    # write their block line — that is one round (observed downstream: 21
    # duplicated block lines would have over-counted)
    blocks = sorted({int(f["round"]) for t in texts for _ln, f in parse_review_lines(t)[0]
                     if work_key(f["work"]) in mine and f["verdict"] == "block"})
    counted = 1 + len(blocks)
    last = blocks[-1] if blocks else None
    notes: list[str] = []
    refusals: list[str] = []
    claimed = str(args.round_) if args.round_ is not None else str(counted)
    # the next round, or another reviewer (lens) of the round that just blocked
    allowed = {str(counted)} | ({str(last)} if last is not None else set())
    written = int(claimed) if claimed in allowed else counted
    if claimed not in allowed and not (claimed.isdigit() and int(claimed) > counted):
        refusals.append(
            f"round {args.round_} claimed, but {len(blocks)} blocking round(s) are recorded for "
            f"work={args.work} — this is round {counted}"
            + (f" (or {last}, for another reviewer of that round)" if last is not None else "")
            + "; a verdict on an older round no longer stands against the blocks since — "
            "review the current head")
    elif claimed not in allowed:
        notes.append(
            f"round {args.round_} claimed, but {len(blocks)} blocking round(s) are recorded for "
            f"work={args.work} — written as round {counted}"
            + (f" (pass --round {last} for another reviewer of that round)" if last is not None else "")
            + "; a re-check after a pass or a rebase keeps the round")
    # a cause is read as rendered: a quoted example or a commented line is no cause
    causes = {int(m.group("round")) for t in texts for m in ROOT_CAUSE.finditer(readable(t))
              if work_key(m.group("work")) in mine}
    missing = [r for r in blocks if r < written and r not in causes]
    if missing:
        notes.append(
            "no root cause for the fix of blocking round(s) " + ", ".join(map(str, missing))
            + f" — record `ROOT-CAUSE work={args.work} round=<r>: <cause> — <the test "
            "that failed before the fix>` in the journal or the plan (docs/process/review-checklist.md, "
            "round economy)")
    return written, notes, refusals


def build_line(args, root: Path, journal_dir: Path | None = None) -> tuple[str, list[str]]:
    """(REVIEW line, problems). Base and head come from the bundle or the flags."""
    problems: list[str] = []
    fields = [f"work={args.work}", f"tier={args.tier}", f"reviewer={args.reviewer}",
              f"model={args.model}", f"independence={args.independence}",
              f"verdict={args.verdict}", f"round={args.round_}"]
    base = head = None
    if args.bundle:
        text = Path(args.bundle).read_text(encoding="utf-8", errors="replace")
        m = ARTIFACT_LINE.search(text)
        if not m:
            problems.append(f"no REVIEW_ARTIFACT line in {args.bundle}")
        elif m.group("mode") == "delta":
            problems.append(f"{args.bundle} is an older delta bundle (its base is the last round's "
                            f"head) — rebuild it: a REVIEW binds the whole branch")
        else:
            base, head = m.group("base"), m.group("head")
    if args.base or args.head:
        if not (args.base and args.head):
            problems.append("--base and --head go together")
        base, head = args.base, args.head
    if base and head and not problems:
        missing = [sha for sha in (base, head) if _git(root, "cat-file", "-e", f"{sha}^{{commit}}") is None]
        if missing:
            problems.append(f"commit {missing[0][:12]} does not exist in this clone — fetch it, "
                            f"or rebuild the bundle here")
        else:
            why = full_round_base_problem(root, base, head)
            if why:
                problems.append(why)
            fields += [f"base={base}", f"head={head}"]
    line = "REVIEW " + " ".join(fields)
    for _ln, msg in parse_review_lines(line)[1]:
        problems.append(f"malformed: {msg}")
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
                    help="optional: another reviewer of the last blocked round; a round above the count "
                         "of recorded blocks is written as the counted one, one below the last block "
                         "is refused")
    ap.add_argument("--plan-review", action="store_true",
                    help="a review of the plan, not the code: counted apart as work=<id>-plan")
    ap.add_argument("--exception", help="an owner's override, recorded as REVIEW-EXCEPTION with what it overrides")
    ap.add_argument("--bundle")
    ap.add_argument("--base")
    ap.add_argument("--head")
    ap.add_argument("--note", help="prose paragraph written above the line")
    ap.add_argument("--archive", help="with a pass: git-mv this plan into the archive")
    ap.add_argument("--commit", action="store_true",
                    help="one commit of the line (and the archived plan); default with "
                         "--archive: staged, the commit named")
    ap.add_argument("--with", dest="with_", action="append", metavar="PATH",
                    help="another record of this round (its review report, the plan) — staged and "
                         "committed with the line")
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
    counted, round_notes, round_issues = round_problems(args, root, journal_dir)
    round_issues += work_problems(args, root)  # an owner exception overrides it too
    exception_note = ""
    if args.exception:
        # always written: an owner exception that trips no rule here (a round
        # beyond the cap) must be countable too, never lost in silence
        named = round_issues + round_notes
        overrides = "; ".join(named) if named else "no attest rule tripped"
        exception_note = (f"REVIEW-EXCEPTION work={args.work} round={counted}: "
                          f"{args.exception} (overrides: {overrides})")
        round_issues = round_notes = []
    for note in round_notes:
        print(f"attest: note — {note}", file=sys.stderr)
    args.round_ = counted
    line, problems = build_line(args, root, journal_dir)
    problems = round_issues + problems + archive_problems(args, root) + with_problems(args, root)
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
        _fix_streak_notes(root, args.verdict)
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
    _fix_streak_notes(root, args.verdict)
    if not (args.archive or args.commit or args.with_):
        return 0
    staged = ([str(target)] if target.is_relative_to(root) else []) + [
        str((root / rel).resolve()) for rel in args.with_ or []]
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


def _fix_streak_notes(root: Path, verdict: str) -> None:
    """A block is where the next patch gets stacked: rules 4/6 ask their
    structural question there (check_fix_streak owns the note; never blocks)."""
    if verdict != "block":
        return
    try:
        found = fix_streak_notes(root) or []
    except (OSError, ValueError):
        return
    for note in found:
        print(note, file=sys.stderr)


def _git_ok(root: Path, *args: str) -> bool:
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, env=git_environment())
    if r.returncode != 0:
        print(f"attest: git {' '.join(args)} failed: {r.stderr.strip()} — the line is "
              f"written; finish the step by hand", file=sys.stderr)
    return r.returncode == 0


if __name__ == "__main__":
    raise SystemExit(main())
