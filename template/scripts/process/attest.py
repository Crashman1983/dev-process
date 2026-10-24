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
"""
from __future__ import annotations

import argparse
from collections import Counter
import datetime as dt
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling import
from process_git import git_environment  # noqa: E402
from check_fix_streak import notes as fix_streak_notes  # noqa: E402
from attest_evidence import _lexical_rel, evidence_problems, snapshot  # noqa: E402  (one file-set owner)
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
    is the line's own head, or one only attest commits lie above (`_attest_commit`), as a
    lens built after the first lens's attest commit sees it. Rebuilt in the v2.77
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
        if len(parents) != 1 or not _attest_commit(root, parents[0], at, mine):
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
        # `attest --archive` moves the plan it appends to: the deleted plan and its archived
        # copy pair by the archive rule, never by git's rename guess (round 5)
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


def _blob(root: Path, data: bytes) -> str | None:
    """The blob id of exactly `data` — no path, no clean filter, no second read."""
    r = subprocess.run(["git", "-C", str(root), "hash-object", "-w", "--stdin"],
                       input=data, capture_output=True, env=git_environment())
    if r.returncode:
        print(f"attest: git hash-object failed: {r.stderr.decode(errors='replace').strip()}",
              file=sys.stderr)
        return None
    return r.stdout.decode().strip()


def _index_entry(root: Path, env: dict, rel: str, data: bytes, mode: str) -> bool:
    blob = _blob(root, data)
    if blob is None:
        return False
    r = subprocess.run(["git", "-C", str(root), "update-index", "--add", "--cacheinfo",
                        mode, blob, rel],
                       capture_output=True, text=True, env=env)
    if r.returncode:
        print(f"attest: git update-index {rel} failed: {r.stderr.strip()}", file=sys.stderr)
        return False
    return True


def _stage_bytes(root: Path, files: list[tuple[str, bytes | None]], modes: dict[str, str]) -> bool:
    """The index gets exactly the checked bytes, never a fresh read of the worktree, in
    the snapshot's mode (I4: 100755 only where `old` holds the path so)."""
    env = git_environment()
    return all(data is None or _index_entry(root, env, rel, data, modes.get(rel, "100644"))
               for rel, data in files)


def _commit_bytes(root: Path, files: list[tuple[str, bytes | None]], removals: list[str],
                  message: str, old: str | None, modes: dict[str, str]) -> bool:
    """One commit whose tree is `old` plus exactly these blobs (and removals), via a private
    index and a compare-and-swap update of HEAD from `old`, the HEAD the snapshot read
    (I3): a commit of another process since then fails the swap. Foreign staged changes
    stay in the real index and out of the commit. The real index gets the attestation's
    bytes first: when that fails (a held `index.lock`) HEAD has not moved; after HEAD moved
    no step is left that can fail, so HEAD never names a commit the index contradicts
    (#308 R5)."""
    if not old:
        print("attest: no HEAD to commit onto", file=sys.stderr)
        return False
    if not _stage_bytes(root, files, modes):
        print("attest: the index could not take the attestation — nothing committed; the "
              "line is written, rerun the commit when the index is free", file=sys.stderr)
        return False
    paths = list(dict.fromkeys([rel for rel, _data in files] + removals))
    tmp_root = root / ".process-work" / "tmp"
    try:
        tmp_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="attest-index-", dir=tmp_root) as tmp:
            env = {**git_environment(), "GIT_INDEX_FILE": str(Path(tmp) / "index")}
            if subprocess.run(["git", "-C", str(root), "read-tree", old],
                              capture_output=True, env=env).returncode:
                print("attest: git read-tree failed", file=sys.stderr)
                return False
            for rel in removals:
                subprocess.run(["git", "-C", str(root), "update-index", "--force-remove", "--", rel],
                               capture_output=True, env=env)
            for rel, data in files:
                if data is not None and not _index_entry(root, env, rel, data, modes.get(rel, "100644")):
                    return False
            tree = subprocess.run(["git", "-C", str(root), "write-tree"],
                                  capture_output=True, text=True, env=env)
            if tree.returncode:
                print(f"attest: git write-tree failed: {tree.stderr.strip()}", file=sys.stderr)
                return False
            commit = subprocess.run(["git", "-C", str(root), "commit-tree", tree.stdout.strip(),
                                     "-p", old, "-m", message],
                                    capture_output=True, text=True, env=env)
            if commit.returncode:
                print(f"attest: git commit-tree failed: {commit.stderr.strip()}", file=sys.stderr)
                return False
            new = commit.stdout.strip()
            moved = subprocess.run(["git", "-C", str(root), "update-ref", "-m", message,
                                    "HEAD", new, old], capture_output=True, text=True, env=env)
            if moved.returncode:
                print(f"attest: git update-ref failed: {moved.stderr.strip()} — the attestation "
                      f"is written and staged, nothing committed; finish with: git commit "
                      f"-m \"{message}\" -- {' '.join(paths)}", file=sys.stderr)
                return False
    except OSError as exc:
        print(f"attest: cannot use the worktree index ({exc}) — the attestation is written "
              f"and staged, nothing committed", file=sys.stderr)
        return False
    return True


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
    modes = {f.rel: f.mode for f in snap.files}
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
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(target_bytes)
    files = [(target_rel, target_bytes), *carried[1:]]
    print(f"attest: appended to {_shown(root, target)}")
    _fix_streak_notes(root, args.verdict)
    if not (args.commit or args.with_):
        return 0
    message = f"docs: attest {args.work} round {args.round_}"
    changes = list(files)
    removals: list[str] = []
    if args.commit:
        # only the attestation's own paths: anything else staged stays staged
        # (refutation: a staged source file rode along into this commit)
        if not _commit_bytes(root, changes, removals, message, snap.old, modes):
            return 1
        print(f"attest: committed: {message}")
    else:
        if not _stage_bytes(root, changes, modes):
            return 1
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
