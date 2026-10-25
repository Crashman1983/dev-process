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
`ROOT-CAUSE work=<id> round=<r>: <cause> — sites: <sites> — <path>::<test>` (the
test that failed before the fix; `sites: none — <reason>` for a round without a code
defect; the older `<cause> — <test>` still names a cause, but is no class test)
in the journal or the plan (a Spec Kit plan too). A fix that names no cause is a patch, and
patches on patches were the largest source of extra rounds downstream. A
missing cause is a note here, not a refusal: by the time a verdict is
attested the review has run, and refusing its record bought no cause — only a
mechanical round (downstream: a pass of two families refused over a cause
labelled round=6 instead of 5). The duty sits where the fix is made: the
execute session's `--dry-run` must name no missing cause before it reports.
v2.77 turns that around for a Tier 2+ pass, on purpose (the owner's class test,
#297): per blocked code round the branch adds, a cause in the class-test form
(`… — sites: … — <path>::<test>`), and from the second such round a `REPLAN`
line per follow-up block in the plan (`attest_evidence`, required_records).
`--exception TEXT` records an owner's override as `REVIEW-EXCEPTION`, where it
can be counted.

Usage:
  attest.py --work ID --tier N --reviewer R --model M --independence a,b
            --verdict pass|block [--round N] [--plan-review]
            [--bundle FILE | --base SHA --head SHA] [--note TEXT]
            [--exception TEXT] [--journal-dir DIR] [--dry-run]
            [--archive PLAN] [--commit] [--with PATH ...]

A Tier 2+ pass shows its evidence first (`attest_evidence.py`, #225): its
review report with one test per acceptance criterion, a refute for gate code,
cross-model or a reasoned single-family from the project's tier, a plan
reviewer of no lower class than the plan session. Plan lines (REFUTE,
ROOT-CAUSE, DECISION, skips) are committed before the bundle is built, or
appended after the plan's last line and ridden here with `--with` the plan.

`--archive PLAN` is refused before anything is read: attest moves no plan (#308); the
archive is a commit of its own after the attestation, `git mv <plan> <archive>`, whose
target the refusal names. `--with PATH` adds the round's other records — its review report, plan lines —
so the round is one commit and one push (each bookkeeping push paid the
push-time gates downstream; half the commits of two weeks were bookkeeping);
`--commit` makes that one commit. Every refusal comes before the first write.

What counts is read once, as git objects (#308): the snapshot fixes `old` (HEAD), the
bytes of today's shard and every `--with` record through checked descriptors, and two
trees — `E` (the reviewed head plus them: the evidence) and `T0` (`old` plus them: the
round counter). The worktree and the index are read after it only to refuse. The write
phase is a compare-and-swap against the snapshot: attest holds the index's own
`index.lock`, appends today's shard through a descriptor checked for identity and
content, runs git commit's hooks (pre-commit, prepare-commit-msg, commit-msg) on the
commit's own index, and moves HEAD by `update-ref HEAD new old`; a refusal drops the lock
and leaves HEAD and the index as they were. A hook that refuses stops the commit as a
failed `update-ref` does: the line written and staged, HEAD unmoved. There is no
`--no-verify`.
- R-1: without `--commit` the staging is the product — `--with` stages the blobs of `T1`
  under the lock, no flags only appends the line (no index).
- R-6: where the platform has no `dir_fd`/`O_NOFOLLOW` (Windows) the descriptor's
  identity check stands in for the link-free walk.
- R-7: a split index (`core.splitIndex`, or an index whose link extension git reports by
  `rev-parse --shared-index-path`) is refused; attest writes only a whole index. A
  `sharedindex.*` left beside a whole index is not a split.
- The archive: attest moves no plan. After the attestation, `git mv <plan> <archive>` and
  `git commit` — a commit of its own, which the round counter walks through.
"""
from __future__ import annotations

import argparse
from collections import Counter
import dataclasses
import datetime as dt
import os
import re
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling import
from process_git import git_environment  # noqa: E402
from check_fix_streak import notes as fix_streak_notes  # noqa: E402
from attest_evidence import (  # noqa: E402  (one file-set owner)
    _create_in_repo,
    _entries,
    _hash_blob,
    _lexical_rel,
    _open_in_repo,
    _read_at_start,
    _rev,
    _tree_with,
    evidence_problems,
    snapshot,
)
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
    SPEC_PLAN,
    SPECS_DIR,
    DATE_PREFIX,
    _slug_in_name,
    work_key,
    parse_review_lines,
    readable,
    record_kind,
    record_texts,
    records_only,
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



def _git_out(root: Path, *args: str) -> bytes:
    """git's stdout, or ValueError when it fails — the moved round rule keeps its
    `except ValueError` branches word for word."""
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, check=False, timeout=60,
                       env=git_environment())
    if r.returncode:
        raise ValueError(f"git {' '.join(args[:2])} failed: {r.stderr.decode(errors='replace').strip()[-200:]}")
    return r.stdout


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


def archive_rel(rel: str) -> str:
    """Where the archive takes the plan at the repository path `rel`. A Spec Kit plan is
    always `plan.md`: it takes its feature directory's name, or every Spec Kit plan would
    collide in the archive. `_attest_commit` pairs an archive move by it."""
    parts = rel.split("/")
    if len(parts) == 3 and parts[0] == SPECS_DIR and parts[2] == SPEC_PLAN:
        return f"{PLANS_ARCHIVE}/{parts[1]}.md"
    return f"{PLANS_ARCHIVE}/{parts[-1]}"


def _shown(root: Path, p: Path) -> str:
    return str(p.relative_to(root)) if p.is_relative_to(root) else str(p)


def archive_refusal(args, root: Path) -> str:
    """Why `--archive` is refused, or "" without it. attest moves no plan (#308, design
    §10): every way it had to move one opened a window in which the worktree could lose
    bytes. The archive is a commit of its own after the attestation, named here with its
    target; the gate and a second lens read the moved plan by its content. Checked before
    anything is read, from the strings alone."""
    if not args.archive:
        return ""
    rel, _why = _lexical_rel(root, Path(args.archive))
    plan = rel or args.archive
    return (f"--archive: attest no longer archives the plan — attest without --archive, then "
            f"archive the plan in a commit of its own: git mv {plan} {archive_rel(plan)} && "
            f"git commit -m \"docs: archive the plan\"")


def with_problems(args, root: Path, snap) -> list[str]:
    """`--with` carries records only: a source file riding an attestation commit
    would be code no review saw, under a commit the tools read as bookkeeping. The
    path itself is checked by `snapshot` (one owner); here only the record home of the
    `--with` paths the snapshot carries is read — lexically, on its paths, no file
    system call (design §9: a path swapped after the snapshot is still checked)."""
    out = []
    held = {f.rel for f in snap.files if f.data is not None}
    root = Path(os.path.realpath(root))  # the root as `snapshot` holds it
    for rel in args.with_ or []:
        r, _why = _lexical_rel(root, Path(rel))
        if r is None or r not in held:
            continue  # the snapshot names the path, the symlink or the missing file
        if not (r.startswith(BOOKKEEPING) or record_kind(r) is not None):
            out.append(f"--with: {rel} is not a process record (under {BOOKKEEPING} or a plan) — "
                       f"commit code with its own message")
    return out


def _plan_records(root: Path, kinds: tuple[str, ...], records: list | None) -> list[tuple[str, str]]:
    """The plans of `kinds`: from `records` (a tree's record set, `Snapshot.records_T0`),
    or — `records` None, the preview callers (D-7) — from the worktree."""
    if records is None:
        return record_texts(root, kinds) or []
    return [(rel, text) for rel, text in records if record_kind(rel) in kinds]


def work_problems(args, root: Path, records: list | None = None) -> list[str]:
    """A `--work` no plan names clears nothing. A number no plan declares and the
    branch does not lead with is most likely the PR's number (observed: rounds
    attested as work=<PR>, which no gate ever matched) — refused; any other
    unknown id is a note, since a plan may still be written. The plans are those of
    `records` (T0, I12), else the worktree's."""
    work = args.work[:-len("-plan")] if args.work.endswith("-plan") else args.work
    known = _known_work(root) if records is None else {
        i for rel, text in _plan_records(root, PLAN_KINDS + ("plan-archive",), records)
        for i in _plan_work_ids(plan_stem(rel), _unfenced(text), include_dedated=True)}
    if work in known:
        return []
    branch = _git(root, "symbolic-ref", "--short", "HEAD") or ""
    if work.isascii() and work.isdigit() and branch_issue(branch) != work:
        active = sorted({i for rel, text in _plan_records(root, PLAN_KINDS, records)
                         for i in _plan_work_ids(plan_stem(rel), _unfenced(text), include_dedated=True)})
        return [f"work={work} names no plan or issue — it looks like a PR number; the work id "
                f"is the plan slug or its issue: line. Active plans: "
                f"{', '.join(active) if active else 'none'}. Issue work without a plan: "
                f"attest with --exception \"<reason>\""]
    print(f"attest: note — work={work} names no plan (active, archived or Spec Kit) yet; "
          f"no plan's review is cleared by it until one does", file=sys.stderr)
    return []


def _texts(root: Path, journal_dir: Path, records: list | None = None) -> list[str]:
    """Every file where REVIEW and ROOT-CAUSE lines live — journal shards,
    plans (active and archived), Spec Kit plans; check_review owns the list.
    The journal raw, as the gate reads REVIEW lines there: a block the gate
    counts is a block here too, or a round slips through without its root
    cause (refutation). Plans, which the gate does not read for REVIEW
    lines, as rendered: a commented example there is no round.
    `records` is a tree's record set (`Snapshot.records_T0`: the repository's
    journal and the `--journal-dir` shards, which carry no record kind of their
    own); None reads the worktree for the preview callers (D-7), where
    `--journal-dir` replaces the repository's journal (it does not add to it) —
    a known limit of the override, meant for tests and dry runs."""
    if records is not None:
        return [text if record_kind(rel) in ("journal", None) else readable(text) for rel, text in records]
    return [text if record_kind(rel) == "journal" or rel.startswith(str(journal_dir)) else readable(text)
            for rel, text in record_texts(root, journal_dir=journal_dir) or []]


def round_ids(args, root: Path, records: list | None = None) -> set[str]:
    """The work ids whose rounds and root causes are this round's: a plan's slug
    and its issue are one work — switching `--work 9` to `--work widget`
    restarted the count at round 1 and skipped the root cause (refutation). But
    only within ONE plan: an issue shared by several plans would lend plan A's
    rounds to plan B (refutation). A slug names its plan (an active one first);
    an issue names the active plans declaring it, narrowed to the one whose slug
    the branch carries when several do. No single plan: the literal id alone. The
    plans are those of `records` (T0: a plan only in the worktree is no alias, D-3),
    else the worktree's (D-7)."""
    work = args.work
    if work.endswith("-plan"):  # plan reviews count apart, literally
        return {work}
    key = work_key(work)
    plans = [(rel, _plan_work_ids(plan_stem(rel), _unfenced(text), include_dedated=True))
             for rel, text in _plan_records(root, PLAN_KINDS + ("plan-archive",), records)]
    hits = [(rel, ids) for rel, ids in plans if key in {work_key(i) for i in ids}]
    active = [(rel, ids) for rel, ids in hits if record_kind(rel) != "plan-archive"]
    cands = active if (isinstance(key, tuple) or active) else hits
    if len(cands) > 1:
        leaf = (_git(root, "symbolic-ref", "--short", "HEAD") or "").rsplit("/", 1)[-1]
        cands = [(rel, ids) for rel, ids in cands
                 if _slug_in_name(DATE_PREFIX.sub("", plan_stem(rel)), leaf)]
    return {work} | cands[0][1] if len(cands) == 1 else {work}


def _block_lines(texts: list[str], mine: set) -> list[tuple[int, str]]:
    """(round, line) of every blocking REVIEW line of the work `mine` in `texts`."""
    out: list[tuple[int, str]] = []
    for t in texts:
        lines = t.splitlines()
        out += [(int(f["round"]), lines[ln - 1]) for ln, f in parse_review_lines(t)[0]
                if work_key(f["work"]) in mine and f["verdict"] == "block"]
    return out


def block_lines(args, root: Path, journal_dir: Path, records: list | None = None) -> list[tuple[int, str]]:
    """The blocks `round_problems` counts, line by line — what attest_evidence reads for
    the blocked code rounds a branch adds (v2.77 `replan`, `class-test`): the duty and
    the round number read one set (`records`, T0). Apart from `round_problems`, whose
    return value its other caller (`_dispatch_codex`) reads as it is."""
    return _block_lines(_texts(root, journal_dir, records),
                        {work_key(w) for w in round_ids(args, root, records)})


def uncommitted_blocks(args, root: Path, journal_dir: Path, records: list) -> list[str]:
    """D-2: a blocking REVIEW line of the work in the worktree that T0 (`records`: the
    committed records plus this attestation's) does not hold is refused by name — it
    was counted silently before, from a file neither committed nor carried. A refusal
    reader (I5): the worktree is read here, never counted."""
    mine = {work_key(w) for w in round_ids(args, root, records)}
    fixed = {line.strip() for _r, line in _block_lines(_texts(root, journal_dir, records), mine)}
    out = []
    for rel, text in record_texts(root, journal_dir=journal_dir) or []:
        view = text if record_kind(rel) in ("journal", None) else readable(text)
        for _r, line in _block_lines([view], mine):
            if line.strip() not in fixed:
                out.append(f"{rel}: `{line.strip()}` is a block of work={args.work} that is neither "
                           f"committed nor carried by this attestation — commit it, or pass {rel} "
                           f"with --with")
    return out


def round_problems(args, root: Path, journal_dir: Path, records: list | None = None
                   ) -> tuple[int, list[str], list[str]]:
    """(the round to write, notes, refusals). A claim above the count and a
    missing cause are bookkeeping about a review that already ran — notes, since
    a refusal there cost a whole mechanical round downstream and caught nothing.
    A claim below the last blocked round is refused: written as the count, a late
    pass of an old round would outrank the blocks recorded since (refutation).
    The blocks are those of `records` (T0, D-1), else the worktree's (D-7)."""
    texts = _texts(root, journal_dir, records)
    mine = {work_key(w) for w in round_ids(args, root, records)}
    # distinct rounds, not lines: several reviewers (lenses) of one round each
    # write their block line — that is one round (observed downstream: 21
    # duplicated block lines would have over-counted)
    blocks = sorted({r for r, _line in _block_lines(texts, mine)})
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
            + f" — record `ROOT-CAUSE work={args.work} round=<r>: <cause> — sites: <sibling sites> — "
            "<path>::<the test that failed before the fix>` (or `… — sites: none — <reason>`) in the "
            "journal or the plan (docs/process/review-checklist.md, round economy)")
    return written, notes, refusals


def artifact_range(args) -> tuple[str | None, str | None, list[str]]:
    """(base, head, problems) from the bundle's `REVIEW_ARTIFACT` line or the flags — an
    input read once, before the snapshot (D-6)."""
    problems: list[str] = []
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
    return base, head, problems


def build_line(args, root: Path, journal_dir: Path | None = None,
               rng: tuple[str | None, str | None, list[str]] | None = None) -> tuple[str, list[str]]:
    """(REVIEW line, problems). Base and head come from the bundle or the flags
    (`artifact_range`, or `rng` as main read it before the snapshot)."""
    base, head, problems = rng if rng is not None else artifact_range(args)
    problems = list(problems)
    fields = [f"work={args.work}", f"tier={args.tier}", f"reviewer={args.reviewer}",
              f"model={args.model}", f"independence={args.independence}",
              f"verdict={args.verdict}", f"round={args.round_}"]
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




def blocked_round_at(root: Path, args: argparse.Namespace, head: str) -> int | None:
    """The round of a blocking REVIEW line of the work (`round_ids`) on this head —
    another lens already blocked the round this review is a lens of — or None. "This head"
    is the line's own head, or one only attest commits and pure archive commits lie above
    (`_attest_commit`, `_archive_only`), as a lens built after the first lens's attest
    commit — or after the plan's own archive commit (#308) — sees it. Rebuilt in the v2.77
    cross-model review (round 3): a rule over paths read the reviewed plan as bookkeeping,
    or the records an attest commit carries as content."""
    mine = {work_key(w) for w in round_ids(args, root)}
    attests: list[str] = []  # head, then each first parent while the commit is an attest commit
    at = head
    while len(attests) < 100:
        attests.append(at)
        try:
            parents = _git_out(root, "rev-list", "--parents", "-n", "1", at).decode().split()[1:]
        except ValueError:
            break  # git cannot tell: this head alone
        if len(parents) != 1 or not (_attest_commit(root, parents[0], at, mine)
                                     or _archive_only(root, parents[0], at)):
            break
        at = parents[0]
    rounds = [int(f["round"]) for t in _texts(root, root / JOURNAL_DIR) for _ln, f in parse_review_lines(t)[0]
              if f["verdict"] == "block" and f.get("head") in attests and work_key(f["work"]) in mine]
    return max(rounds) if rounds else None


def _attest_commit(root: Path, parent: str, commit: str, mine: set) -> bool:
    """Is `commit` over `parent` an attest commit of the work `mine`: it adds a REVIEW line
    of the work and changes nothing else than reports and journal (`.process-work/`, plans
    aside) and records appended to a plan (`check_review.records_only`, as attest `--with`
    lets them ride), the plan moved to the archive by `--archive` included? A plan changed
    in its content, added or deleted is a fix, and so is a commit without a REVIEW line — a
    decision answering a block included. Unreadable is no."""

    def plan(rel: str) -> bool:
        return record_kind(rel) in (*PLAN_KINDS, "plan-archive")

    try:
        status = _git_out(root, "diff", "--name-status", "-z", "--no-renames", parent, commit).decode().split("\0")
        changes = dict(zip(status[1::2], status[0::2]))  # path -> A|D|M|T
        pairs = [(rel, rel) for rel, kind in changes.items() if kind == "M" and plan(rel)]
        # an older `attest --archive` (v2.77, still in history) moved the plan it appended
        # to: the deleted plan and its archived copy pair by the archive rule, never by
        # git's rename guess (round 5)
        pairs += [(rel, archive_rel(rel)) for rel, kind in changes.items() if kind == "D" and plan(rel)]
        paired = {p for pair in pairs for p in pair}
        for rel in changes:
            if rel in paired:
                continue
            if plan(rel) or not rel.startswith(".process-work/"):
                return False  # a plan added or deleted unpaired, or a path outside bookkeeping
        for old, new in pairs:
            if changes.get(new) != ("M" if new == old else "A") or not plan(new):
                return False
            before = _git_out(root, "show", f"{parent}:{old}").decode("utf-8")
            after = _git_out(root, "show", f"{commit}:{new}").decode("utf-8")
            if not records_only(before, after):
                return False

        def lines(rev: str, rel: str) -> Counter[str]:
            try:
                return Counter(_git_out(root, "show", f"{rev}:{rel}").decode("utf-8", errors="replace").splitlines())
            except ValueError:
                return Counter()  # not there at that side
        # the lines the commit adds, counted per path and per archive pair: a moved plan adds
        # none of its old lines, a lens line equal to one already there still counts (round 6)
        sides = pairs + [(rel, rel) for rel in changes if rel not in paired]
        added = "\n".join((sum((lines(commit, new) - lines(parent, old) for old, new in sides), Counter()))
                          .elements())
    except (ValueError, UnicodeDecodeError):
        return False
    return any(work_key(f["work"]) in mine for _ln, f in parse_review_lines(added)[0])


def _archive_only(root: Path, parent: str, commit: str) -> bool:
    """Is `commit` over `parent` a pure archive commit (#308, design §10): every change a
    pair `D rel` + `A archive_rel(rel)` of a plan with the same blob, nothing else? The
    archive is a commit of its own after the attestation; it adds no line and changes no
    plan, so the round another lens blocked stays this head's. A plan changed on the way
    is a fix. Unreadable is no."""
    try:
        status = _git_out(root, "diff", "--name-status", "-z", "--no-renames", parent, commit).decode().split("\0")
        changes = dict(zip(status[1::2], status[0::2]))  # path -> A|D|M|T
        moved = [rel for rel, kind in changes.items()
                 if kind == "D" and record_kind(rel) in PLAN_KINDS and archive_rel(rel) != rel]
        if not moved or len(changes) != 2 * len(moved):
            return False
        for rel in moved:
            dest = archive_rel(rel)
            if changes.get(dest) != "A":
                return False
            if _git_out(root, "rev-parse", f"{parent}:{rel}") != _git_out(root, "rev-parse", f"{commit}:{dest}"):
                return False
    except ValueError:
        return False
    return True


def _write_seam(stage: str) -> None:
    """S2, the test seam of the write phase (design §8): a named no-op the phase calls at
    `before-lock`, `index-checked` and `worktree-checked`; a test patches it to mutate there."""


class _Refused(Exception):
    """A refusal inside the write phase: the lock is dropped, HEAD and the index unchanged."""


def _git_run(root: Path, *args: str, env: dict | None = None, data: bytes | None = None
             ) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args], input=data, capture_output=True,
                          env=env or git_environment(), check=False)


def _write_phase(root: Path, snap, target_rel: str, target_bytes: bytes, message: str,
                 commit: bool, index_too: bool = True) -> bool:
    """The transactional write phase (design §8): every write is a compare-and-swap
    against the snapshot, on the object the check saw. Objects first — the target's blob,
    `T1` (`T0` plus it), with `commit`. Then W1: attest takes
    the real index's `index.lock` itself (`O_CREAT|O_EXCL`; held → refused), checks
    `HEAD == old` and that every snapshot path's index entry is the one recorded, `old`'s or
    the snapshot's blob (I6, I11), and writes the new index — built on a copy in `tempfile`
    — into the lock. W2: each file opened without following a link, `fstat` identity and
    content (through that descriptor) equal to the snapshot; the line appended through the
    target's descriptor (`O_APPEND`, never `O_TRUNC`), a new shard made by `O_CREAT|O_EXCL`;
    then every path's `lstat` equal to its descriptor's `fstat`. Only then the lock renamed
    onto the index, git commit's hooks (`_commit_hooks`), `commit-tree T1 -p old` with the
    message they leave, and `update-ref HEAD new old`. A refusal before the rename removes the
    lock — the only name attest removes in the worktree (I13′) — HEAD stays `old`. Without
    `commit` the phase ends with the index rename (R-1); without `index_too` (no flags) it
    is W2 alone: the line appended, no index, no commit. A split index is refused (R-7)."""
    try:
        return _write_phase_steps(root, snap, target_rel, target_bytes, message, commit, index_too)
    except _Refused as why:
        print(f"attest: REFUSED — {why}", file=sys.stderr)
        return False


def _w2_append(root: Path, snap, target_rel: str, target_bytes: bytes, fds: dict[str, int]) -> None:
    """W2: today's shard checked through its descriptor (`_w2_check`), the seam, a new shard
    made only now, the line appended through the descriptor, then the after-identity."""
    target = next(f for f in snap.files if f.rel == target_rel)
    _w2_check(root, snap, target_rel, fds)
    _write_seam("worktree-checked")
    if target.data is None:  # today's shard, new: created only now, beside nothing
        try:
            fds[target_rel] = _create_in_repo(os.fspath(root), target_rel, os.O_RDWR | os.O_APPEND)
        except FileExistsError:
            raise _Refused(f"{target_rel} appeared after the snapshot — nothing written; rerun "
                           f"attest") from None
        except OSError as exc:
            raise _Refused(f"{target_rel} cannot be made without following a link ({exc}) — "
                           f"nothing written") from None
    view = memoryview(target_bytes[len(target.data or b""):])
    while view:
        view = view[os.write(fds[target_rel], view):]
    for rel, fd in fds.items():
        st = os.fstat(fd)
        try:
            now = os.lstat(os.path.join(root, *rel.split("/")))
        except OSError:
            now = None
        if now is None or (now.st_dev, now.st_ino) != (st.st_dev, st.st_ino):
            raise _Refused(f"{rel} was replaced while attest wrote it — nothing committed, the "
                           f"index unchanged; the file at the path is untouched")


def _write_phase_steps(root: Path, snap, target_rel: str, target_bytes: bytes, message: str,
                       commit: bool, index_too: bool) -> bool:
    if not index_too:  # no flags: the line only, appended by W2 — no index, no commit (R-1)
        fds: dict[str, int] = {}
        try:
            _w2_append(root, snap, target_rel, target_bytes, fds)
        finally:
            for fd in fds.values():
                os.close(fd)
        return True
    if not snap.old:
        raise _Refused("no HEAD to attest onto — nothing written")
    target = next(f for f in snap.files if f.rel == target_rel)
    blob = _hash_blob(root, target_bytes)
    if blob is None:
        raise _Refused("git hash-object failed — nothing written")
    written = dataclasses.replace(target, blob=blob)
    staged = [written if f.rel == target_rel else f for f in snap.files if f.blob or f.rel == target_rel]
    t1 = None
    if commit:
        t1 = _tree_with(root, snap.T0, [written])
        if not t1:
            raise _Refused("git cannot build the attestation's commit — nothing written")
    unsplit = "git config core.splitIndex false && git update-index --no-split-index"
    if (_git(root, "config", "--type=bool", "core.splitIndex") or "") == "true":
        raise _Refused(f"the index is split (core.splitIndex) — attest writes only a whole index "
                       f"(R-7); {unsplit}, then rerun")
    # Split or not is the index's own word (its link extension), not a sharedindex.* left
    # beside it; git that cannot say is a refusal.
    shared = _git(root, "rev-parse", "--shared-index-path")
    if shared is None:
        raise _Refused("git cannot say whether the index is split — nothing written")
    if shared:
        raise _Refused(f"the index is split (it links {shared}) — attest writes only a whole "
                       f"index (R-7); {unsplit}, then rerun")
    where = _git(root, "rev-parse", "--git-path", "index")
    if not where:
        raise _Refused("git cannot name the index — nothing written")
    index = os.path.normpath(os.path.join(root, where))
    lock = index + ".lock"
    _write_seam("before-lock")
    try:
        lock_fd: int | None = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0),
                                      0o666)
    except FileExistsError:
        raise _Refused(f"{lock} is held by another git process — nothing written; rerun when it "
                       f"is free") from None
    except OSError as exc:
        raise _Refused(f"cannot take {lock} ({exc}) — nothing written") from None
    fds = {}
    done = False
    try:
        _w1_check(root, snap)
        _write_seam("index-checked")
        data = _new_index(root, index, staged)
        view = memoryview(data)
        while view:
            view = view[os.write(lock_fd, view):]
        os.fsync(lock_fd)
        os.close(lock_fd)
        lock_fd = None
        _w2_append(root, snap, target_rel, target_bytes, fds)
        os.replace(lock, index)
        done = True
    finally:
        for fd in fds.values():
            os.close(fd)
        if lock_fd is not None:
            os.close(lock_fd)
        if not done:
            try:
                os.unlink(lock)
            except FileNotFoundError:
                pass
    if t1 is None:
        return True
    paths = " ".join(f.rel for f in staged)
    final, why = _commit_hooks(root, t1, message)
    made = _git_run(root, "commit-tree", t1, "-p", snap.old, data=final.encode("utf-8", "surrogateescape")) if final else None
    if made is not None and made.returncode:
        why = f"git commit-tree failed: {made.stderr.decode(errors='replace').strip()}"
    moved = None
    if made is not None and not made.returncode:
        moved = _git_run(root, "update-ref", "-m", final.splitlines()[0], "HEAD",
                         made.stdout.decode().strip(), snap.old)
        if moved.returncode:
            why = f"git update-ref failed: {moved.stderr.decode(errors='replace').strip()}"
    if moved is None or moved.returncode:
        print(f"attest: {why} — the attestation is written and staged, nothing committed; finish "
              f"with: git commit -m \"{message}\" -- {paths}", file=sys.stderr)
        return False
    return True


COMMIT_HOOKS = ("pre-commit", "prepare-commit-msg", "commit-msg")


def _commit_hooks(root: Path, t1: str, message: str) -> tuple[str | None, str]:
    """git commit's hooks for the attest commit (design §11): `commit-tree` runs none, so
    attest runs them itself by `git hook run`, as `git commit -m <message> -- <paths>` would
    — `GIT_INDEX_FILE` is a private index of `T1` in `tempfile` (the commit's own index, no
    foreign staging), the message a file beside it. They run after the write phase, so the
    worktree already holds the target's line and a hook that stashes and checks out the
    worktree (the pre-commit framework) rewrites no checked file. A hook that fails, or
    changes the commit's index (the commit is `T1`, I2), stops the commit; the message a
    hook leaves is the commit's. (final message, why) — the message None when stopped."""
    with tempfile.TemporaryDirectory(prefix="attest-hooks-") as tmp:
        index, msg = os.path.join(tmp, "index"), os.path.join(tmp, "COMMIT_EDITMSG")
        env = {**git_environment(), "GIT_INDEX_FILE": index, "GIT_EDITOR": ":"}
        if _git_run(root, "read-tree", t1, env=env).returncode:
            return None, "git cannot build the commit's index for its hooks"
        with open(msg, "w", encoding="utf-8") as fh:
            fh.write(message + "\n")
        args = {"pre-commit": (), "prepare-commit-msg": (msg, "message"), "commit-msg": (msg,)}
        for hook in COMMIT_HOOKS:
            ran = _git_run(root, "hook", "run", "--ignore-missing", hook, "--", *args[hook], env=env, data=b"")
            said = (ran.stdout + ran.stderr).decode(errors="replace").strip()
            if said:
                print(said, file=sys.stderr)
            if ran.returncode:
                return None, f"the {hook} hook refused the commit (exit {ran.returncode}: {said[-500:]})"
            if _git_run(root, "write-tree", env=env).stdout.decode().strip() != t1:
                return None, (f"the {hook} hook changed the commit's index — the attest commit carries "
                              f"only the checked snapshot (I2)")
        with open(msg, "rb") as fh:
            final = _git_run(root, "stripspace", data=fh.read()).stdout.decode("utf-8", "surrogateescape")
    if not final.strip():
        return None, "the commit hooks left an empty commit message"
    return final, ""


def _w1_check(root: Path, snap) -> None:
    """W1 steps 1–2 under the lock: HEAD is still `old`, and every snapshot path's index
    entry is the one recorded at the snapshot, `old`'s or the snapshot's blob — foreign
    staged bytes are refused, never replaced (I6, I11)."""
    if _rev(root, "HEAD^{commit}") != snap.old:
        raise _Refused("HEAD moved since the snapshot (another commit) — nothing written; rerun attest")
    rels = [f.rel for f in snap.files]
    now = _entries(_git_run(root, "--literal-pathspecs", "ls-files", "-s", "-z", "--", *rels)
                   .stdout.decode("utf-8", "surrogateescape"))
    at_old = _entries(_git_run(root, "--literal-pathspecs", "ls-tree", "-z", snap.old, "--", *rels)
                      .stdout.decode("utf-8", "surrogateescape"))
    for f in snap.files:
        entry = now.get(f.rel)
        if entry is None:
            if f.index is not None:
                raise _Refused(f"{f.rel} was unstaged after the snapshot — foreign work in the index; "
                               f"nothing written")
            continue
        allowed = {f.index, f.blob, at_old.get(f.rel, ("", None))[1]} - {None, ""}
        if entry == ("", "") or entry[1] not in allowed:
            raise _Refused(f"{f.rel} was staged with other bytes after the snapshot ({entry[1][:12] or 'a conflict'})"
                           f" — foreign work in the index; nothing written, the staged bytes kept")


def _new_index(root: Path, index: str, staged) -> bytes:
    """W1 step 3: the real index with exactly the attestation's blobs laid over it, built on
    a copy in `tempfile` (never in the worktree), returned as bytes for the lock."""
    with tempfile.TemporaryDirectory(prefix="attest-index-") as tmp:
        copy = os.path.join(tmp, "index")
        try:
            with open(index, "rb") as src:
                current = src.read()
        except FileNotFoundError:
            current = b""
        if current:
            with open(copy, "wb") as dst:
                dst.write(current)
        env = {**git_environment(), "GIT_INDEX_FILE": copy}
        info = b"".join(f"{f.mode} {f.blob}\t{f.rel}\0".encode("utf-8", "surrogateescape") for f in staged)
        if _git_run(root, "update-index", "--add", "--replace", "-z", "--index-info", env=env, data=info).returncode:
            raise _Refused("git cannot build the new index — nothing written")
        with open(copy, "rb") as built:
            return built.read()


def _w2_check(root: Path, snap, target_rel: str, fds: dict[str, int]) -> None:
    """W2 steps 1–2 for the one file the phase writes in the worktree, today's shard:
    opened for appending without following a link (no `O_CREAT`, no `O_TRUNC`), the
    descriptor's identity and its bytes equal to the snapshot's. The descriptor stays open
    in `fds`. A `--with` record is not written in the worktree — the index and the commit
    take its snapshot blob — so a later change there loses nothing and is not refused."""
    for f in snap.files:
        if f.data is None or f.rel != target_rel:
            continue
        try:
            fds[f.rel] = fd = _open_in_repo(os.fspath(root), f.rel, os.O_RDWR | os.O_APPEND)
        except OSError as exc:
            raise _Refused(f"{f.rel} cannot be opened without following a link ({exc}) — nothing "
                           f"written") from None
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or (st.st_dev, st.st_ino) != f.ident:
            raise _Refused(f"{f.rel} is another file than the snapshot read — nothing written; rerun attest")
        if _read_at_start(fd) != f.data:
            raise _Refused(f"{f.rel} changed after the snapshot — nothing written, its bytes kept; "
                           f"rerun attest")


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
    ap.add_argument("--archive", help="refused: attest archives no plan; it names the archive "
                                      "commit to make after the attestation")
    ap.add_argument("--commit", action="store_true",
                    help="one commit of the line and the --with records; without it they are "
                         "staged, the commit named")
    ap.add_argument("--with", dest="with_", action="append", metavar="PATH",
                    help="another record of this round (its review report, the plan) — staged and "
                         "committed with the line")
    ap.add_argument("--journal-dir", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("root", nargs="?", default=str(ROOT))
    args = ap.parse_args()
    root = Path(args.root).resolve()
    refused = archive_refusal(args, root)
    if refused:  # before anything is read: attest moves no plan (design §10)
        print(f"attest: REFUSED — nothing written:\n  - {refused}", file=sys.stderr)
        return 1
    journal_dir = Path(args.journal_dir) if args.journal_dir else Path(JOURNAL_DIR)
    if not journal_dir.is_absolute():
        journal_dir = root / journal_dir
    # lexical on purpose: `snapshot` checks every component before any read, so a
    # symlink in `--journal-dir` (or the default) cannot be hidden by dereferencing
    target = _journal_target(root, journal_dir)
    if args.plan_review:
        # always: a plan whose own id ends in `-plan` would otherwise have its
        # plan review clear its code (refutation)
        args.work += "-plan"
    # D-6: the range (an input), then the one snapshot this attestation fixes — `old`
    # first, the file set read through checked descriptors, E and T0 (design §4) — and
    # only then the count, the line, the evidence and the refusals, all from it
    rng = artifact_range(args)
    head = rng[1] if rng[1] and _git(root, "cat-file", "-e", f"{rng[1]}^{{commit}}") is not None else None
    with_files = [root / rel for rel in args.with_ or []]
    snap = snapshot(root, target, with_files, journal_dir, head=head)
    records = snap.records_T0
    if records is None or snap.records_E is None:
        # unknown is no "no records" (design §7): a symlink or submodule as a record or
        # as a directory records lie under, or a tree git cannot read
        print("attest: REFUSED — nothing written:", file=sys.stderr)
        for p in [*snap.problems, "the records of the snapshot cannot be read — a symlink or submodule "
                  "is committed as a record or as a directory records lie under (or git cannot read "
                  "the tree); replace it by the file or directory itself"]:
            print(f"  - {p}", file=sys.stderr)
        return 1
    counted, round_notes, round_issues = round_problems(args, root, journal_dir, records)
    round_issues += work_problems(args, root, records)  # an owner exception overrides it too
    args.round_ = counted
    line, problems = build_line(args, root, journal_dir, rng)
    # the evidence a Tier 2+ pass must show (attest_evidence.py), read at the
    # range the line names — known only once build_line has it
    record = next((f for _ln, f in parse_review_lines(line)[0]), {})
    plain = args.work.removesuffix("-plan") if args.plan_review else args.work
    carried, carried_problems = snap.carried, list(snap.problems)
    evidence = evidence_problems(
        root, work=args.work, ids=round_ids(argparse.Namespace(work=plain), root, records),
        tier=int(args.tier) if args.tier.isascii() and args.tier.isdigit() else 0,
        verdict=args.verdict, independence=args.independence, base=record.get("base"),
        head=record.get("head"), plan_review=args.plan_review, model=args.model,
        reports=[],  # the snapshot's files under the reports' home (gather, lexical)
        # a plan review asks no code round's records
        blocks=None if args.plan_review else block_lines(args, root, journal_dir, records),
        journal_dir=journal_dir, snapshot=snap)
    round_issues += uncommitted_blocks(args, root, journal_dir, records)
    exception_note = ""
    if args.exception:
        # always written: an owner exception that trips no rule here (a round
        # beyond the cap) must be countable too, never lost in silence
        named = round_issues + round_notes + evidence
        overrides = "; ".join(named) if named else "no attest rule tripped"
        exception_note = (f"REVIEW-EXCEPTION work={args.work} round={counted}: "
                          f"{args.exception} (overrides: {overrides})")
        round_issues = round_notes = evidence = []
    for note in round_notes:
        print(f"attest: note — {note}", file=sys.stderr)
    problems = round_issues + problems + evidence + carried_problems + with_problems(args, root, snap)
    if args.note and any(ln.lstrip().startswith("REVIEW") for ln in args.note.splitlines()):
        problems.append("the note carries REVIEW-looking lines — the validated line is the "
                        "only REVIEW writer")
    if problems:
        print("attest: REFUSED — nothing written:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1
    print(line)
    if args.dry_run:
        print(f"attest: dry run — would append to {target.relative_to(root) if target.is_relative_to(root) else target}")
        _fix_streak_notes(root, args.verdict)
        return 0
    # what the evidence check read is what this attestation writes: the checked bytes,
    # never a fresh read after the validation (R4 TOCTOU)
    target_rel, target_old = carried[0]
    appended = ""
    if not target_old:
        appended += f"# {dt.date.today().isoformat()}\n\n"
    if exception_note:
        appended += exception_note + "\n\n"
    if args.note:
        appended += args.note.rstrip() + "\n\n"
    appended += line + "\n"
    target_bytes = (target_old or b"") + appended.encode("utf-8")
    message = f"docs: attest {args.work} round {args.round_}"
    # one write phase (design §8): only the attestation's own paths — anything else staged
    # stays staged (refutation: a staged source file rode along into this commit); without
    # flags the line alone, through the checked descriptor (R-1)
    staged = bool(args.commit or args.with_)
    if not _write_phase(root, snap, target_rel, target_bytes, message, commit=args.commit,
                        index_too=staged):
        return 1
    print(f"attest: appended to {_shown(root, target)}")
    _fix_streak_notes(root, args.verdict)
    if args.commit:
        print(f"attest: committed: {message}")
    elif staged:
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


if __name__ == "__main__":
    raise SystemExit(main())
