#!/usr/bin/env python3
"""attest_evidence: what a Tier 2+ pass must show before attest.py writes it.

Downstream, six Tier 2 branches passed review in round 1 in one night; an
audit found six major defects the review missed — four of them tests that
could not go red — while the gate-code refute had been skipped on 4 of 4
gate-code branches and the cross-model run without a word. Both rules only
warned (#225). This module turns them into refusals at the one place a pass
is written (`attest.py`), each with a committed, countable way out.

Two steps, one owner:

- `gather()` reads the evidence at the git object `head` of the attested
  line — the work's plan with its REFUTE and skip lines (that plan's own
  lines, bound by its own ids, as the bundle's refute check reads them), the
  tests a review report names, the diff `base..head`. The worktree counts
  only as the review gate counts it: records appended after the plan's last
  line ride the attestation (`check_review.records_only`) and count when the
  plan rides `--with`; anything else must be at head. One exception (v2.77):
  the blocked code rounds a branch adds are read in the worktree, as the
  round counter reads them, less what the fork point already holds; its
  journal ROOT-CAUSE and skip lines are read by the same evidence readers
  from one snapshot — head plus the files the attestation commits — less the
  fork (`_branch_records`); a journal skip lifts only the per-round duties
  (`JOURNAL_SKIPS`).
- `decide()` is a pure decision table over what was gathered.

Grammar and rules stay with their owners: `check_review` (REFUTE and skip
lines, records, gate paths, record homes, work ids), `attest.round_ids`
(which ids are one work), `report.py` (worker reports), `dispatch._merged`
(the policy overlay). The thresholds are project choices, `review_evidence`
in `docs/process/model-policy.json`, read at the reviewed base: a branch
does not loosen them for its own pass.

The ways out are lines `skipped <kind> work=<id>: <reason>` (`check_review.
SKIP_LINE`); a plan review's skips name `<id>-plan`. A line naming
`owner/repo#N` counts for no work here. Named residuals: a REVIEW line typed
by hand bypasses attest (the push gate does not re-check evidence); whether
a named test tests its criterion is the reviewer's judgment; the
`cross-model` token and `plan-session model:` line are declarations.
"""
from __future__ import annotations

import ast
import fnmatch
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field, replace
from typing import NamedTuple
from pathlib import Path

sys.dont_write_bytecode = True
from check_review import (  # noqa: E402  (sibling import; the guard above keeps it clean)
    OWNER_DECISION,
    PLACEHOLDER,
    PLAN_KINDS,
    RECORD_KINDS,
    REFUTE_LINE,
    REPLAN_LINE,
    JOURNAL_DIR,
    PLANS_ACTIVE,
    REVIEW_REPORTS,
    ROOT_CAUSE_LINE,
    SKIP_LINE,
    SPEC_PLAN,
    SPECS_DIR,
    GitReadError,
    _plan_work_ids,
    _unfenced,
    integration_refs,
    is_gate_path,
    merge_base,
    plan_stem,
    readable,
    record_files,
    record_kind,
    records_only,
    root_cause_parts,
    work_key,
)
import required_records  # noqa: E402
from process_git import git_environment  # noqa: E402

POLICY = "docs/process/model-policy.json"
LOCAL_POLICY = "docs/process/model-policy.local.json"
POLICY_KEY = "review_evidence"
# the template's values, also in model-policy.json (a test pins them equal): they
# apply where the policy at the reviewed base predates the key
DEFAULTS = {
    "cross_model_from_tier": 3,
    # from this tier on only a pass of the ranked (own) family clears a plan and proves
    # its code current — check_review; 4: never (#241)
    "own_family_from_tier": 4,
    "ranks": {"claude-haiku": 0, "claude-sonnet": 1, "claude-opus": 2, "claude-fable": 3},
    "families": ["gpt-", "deepseek-"],  # deepseek-: a third family, e.g. via Melious (#270)
    # pytest's own defaults; a project with other `python_files`/`python_classes` names them
    "python_files": ["test_*.py", "*_test.py"],
    "python_classes": ["Test"],
    # test files of other languages (fnmatch on the repository path, `*` spans folders)
    "test_files": ["*tests/*", "*Tests/*", "*__tests__/*", "spec/*", "*/spec/*", "*Test.*", "*Tests.*",
                   "*Spec.*", "*.test.*", "*.spec.*", "*_test.*", "*_spec.*", "*/test_*", "test_*"],
    # what a work owes as a record (required_records.py, #282); a project appends rows
    # under `required_records_extra`
    "required_records": [
        {"kind": "refute", "when": {"gate_code": True}},
        {"kind": "refute", "when": {"tier_from": 3}},
        {"kind": "root-cause", "when": {"fix_streak": 3}},
        # v2.77: per blocked code round the branch adds, a class test; per follow-up block
        # (each but the lowest), mandatory rule 4's REPLAN call in the plan
        {"kind": "replan", "when": {"blocked_rounds": 2}},
        {"kind": "class-test", "when": {"blocked_rounds": 1}},
        {"kind": "owner-decision", "when": {"waived": True}},
    ],
}
# an acceptance criterion's id: `AC-1`, `AC-2.1`, `AC-B1`, `AC1` — a digit in it, so
# prose (`AC-Zeile`, `AC-<id>`) names none; a sentence's final dot is no part of it
_AC = r"AC(?:-|[ \t](?=\d))?(?P<id>[A-Za-z]{0,3}\d(?:[\w.]*\w)?)"
# a plan quoting a report line in backticks (`AC-1: <path>::<test>`) gives an example,
# not a criterion; a backticked id alone (`AC-2`: When …) still names one (#225 refute)
_EXAMPLE_SPAN = re.compile(r"`[^`\n]*(?:::|<)[^`\n]*`")
AC_ID = re.compile(r"\b" + _AC + r"(?![\w-])")
# a report's line for one: `AC-1: <path>::<test>`, listed, boxed, bold or as a heading
AC_LINE = re.compile(
    r"^[ \t]*(?:[-*+][ \t]+)?(?:\[[ xX]\][ \t]+)?(?:#{1,6}[ \t]+)?(?:\*\*)?" + _AC
    + r"(?:\*\*)?[ \t]*:(?:\*\*)?[ \t]*(?P<body>.*?)[ \t]*$",
    re.MULTILINE)
PLAN_SESSION = re.compile(
    r"^[ \t]*(?:[-*+][ \t]+)?[*_]*plan-session[ \t]+model[*_]*:[*_]*[ \t]*`?(?P<model>[^\s`*]+)`?",
    re.MULTILINE | re.IGNORECASE)
# a path-like token in plan prose; one cited as `path:line` or run as a command is
# read, not changed (a plan cites the guard's file:line and runs the gates)
_PATH_TOKEN = re.compile(r"(?<![\w./\\-])(?P<path>[\w.\\/-]*[\\/][\w.\\/-]*\w|Makefile|\.pre-commit-config\.yaml)"
                         r"(?![\w/\\-])(?!\.\w)(?!:\d)")
_RUN_BEFORE = re.compile(r"(?:\brun|\bpython3?|\buv run)[ \t]+`?$")

HEAD_MSG = ("a Tier 2+ pass reads its evidence at the reviewed range — name it (--bundle, or "
            "--base/--head) with both commits present in this clone")


def ac_key(m: re.Match) -> str:
    return m.group("id")


@dataclass(frozen=True)
class Evidence:
    """Everything `decide()` needs; `gather()` fills it."""
    work: str
    tier: int
    verdict: str
    plan_review: bool
    model: str
    head_ok: bool = True
    policy_problem: str = ""
    cross_model_from: int = 3
    ranks: dict = field(default_factory=dict)
    families: tuple = ()
    gate_code: bool | None = False  # None: git could not list base..head
    cross_model: bool = False
    single_family: bool = False
    skips: frozenset = frozenset()  # kinds skipped for this work
    refute: bool = False  # a REFUTE line of the work at head (or appended after it)
    root_cause: bool = False  # a ROOT-CAUSE line of the work at head (or appended after it)
    owner_decision: bool = False  # a `DECISION <date> owner:` line in the plan at head
    fix_streak: int | None = 0  # longest fix streak on one file in base..head; None: unknown
    # the blocked code rounds the branch adds (`_blocked_rounds`); None: unknown (the fork
    # point cannot be read), or a plan review, which asks no code round's records
    blocked_rounds: int | None = 0
    replan_open: tuple = ()  # follow-up blocked rounds without a REPLAN line in the plan
    class_test_open: tuple = ()  # "<round> (<why>)" per blocked round without a class test
    # evidence in the worktree that neither head nor this attestation carries (#308)
    evidence_problems: tuple = ()
    # required_records rows in force at the base (gather reads them; the template's by default)
    records: tuple = tuple(DEFAULTS["required_records"])
    report_refute: bool = False  # a REFUTE line of the work in this attest's review report
    plan_state: str = "ok"  # ok | missing | ambiguous | differs | unreadable
    plan_rel: str = ""
    plan_gate_code: bool = False
    plan_acs: frozenset = frozenset()
    plan_struck: frozenset = frozenset()  # struck with a reason: the report confirms each
    plan_foreign: frozenset = frozenset()  # named only beside another issue: not required (#287)
    plan_session: str | None = None  # None: no source names it
    plan_session_source: str = "none"  # report | plan-line | none
    has_reports: bool = False
    claims: dict = field(default_factory=dict)  # AC id -> [line bodies]
    test_status: dict = field(default_factory=dict)  # (file, name) -> None (ok) | why not
    # for the refusal readers after `gather` (`evidence_problems`, I5): the plan's text at
    # head, the ids its evidence binds, and the journal evidence keys read at the fork and in E
    plan_text: str = ""
    plan_ids: frozenset = frozenset()
    skip_ids: frozenset = frozenset()
    journal_keys: frozenset = frozenset()


# --- git -------------------------------------------------------------------------

def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=git_environment(), check=False)


def _resolvable(root: Path, sha: str | None) -> bool:
    return bool(sha) and _git(root, "cat-file", "-e", f"{sha}^{{commit}}").returncode == 0


def _show(root: Path, ref: str, rel: str) -> str | None:
    r = _git(root, "show", f"{ref}:{rel}")
    return r.stdout if r.returncode == 0 else None


def _changed(root: Path, base: str, head: str) -> list[str] | None:
    """None when git cannot list the diff — "no gate code" would be a guess."""
    r = _git(root, "diff", "--name-only", "--no-renames", "-z", base, head)
    return [p for p in r.stdout.split("\0") if p] if r.returncode == 0 else None


def plan_names_gate_code(text: str) -> bool:
    """Does plan prose name a gate path it may change? A token cited as `path:line`
    or run as a command does not count; spellings (`./`, `/abs/…`, backslashes) are
    normalized here, for plan text only — a diff's paths go to `is_gate_path` as is."""
    for line in text.splitlines():
        for m in _PATH_TOKEN.finditer(line):
            if _RUN_BEFORE.search(line[:m.start()]):
                continue
            norm = re.sub(r"^(?:\./|/)+", "", m.group("path").replace("\\", "/"))
            parts = norm.split("/")
            # an absolute or nested spelling of a repository path: try each suffix
            if any(is_gate_path("/".join(parts[i:])) for i in range(len(parts))):
                return True
    return False


# --- policy ----------------------------------------------------------------------

def _policy_layers(root: Path, ref: str, merged) -> tuple[dict, str]:
    """The policy files at `ref`, the local one laid over the template's."""
    data: dict = {}
    for rel in (POLICY, LOCAL_POLICY):
        text = _show(root, ref, rel)
        if text is None:
            continue
        try:
            layer = json.loads(text)
        except ValueError as exc:
            return {}, f"{rel} at {ref[:12]} is not valid JSON ({exc}) — the evidence rules cannot be read"
        if not isinstance(layer, dict):
            return {}, f"{rel} at {ref[:12]} is no JSON object — the evidence rules cannot be read"
        if rel == LOCAL_POLICY and isinstance(layer.get(POLICY_KEY), dict) \
                and "required_records" in layer[POLICY_KEY]:
            # the template's rows are the floor: `[]` here would lift every duty (#282 refute)
            return {}, (f"{rel} at {ref[:12]} sets {POLICY_KEY}.required_records — a project adds rows "
                        f"under required_records_extra and cannot replace the template's")
        data = merged(data, layer)
    return data, ""


def review_policy(root: Path, ref: str) -> tuple[dict, str]:
    """(`review_evidence` over the defaults, problem) as the policy reads at `ref` — the
    reviewed base. The overlay is dispatch's (`_merged`), one rule for how the local
    file lays over."""
    from dispatch import _merged  # late: dispatch is large
    data, problem = _policy_layers(root, ref, _merged)
    if problem:
        return {}, problem
    rules = data.get(POLICY_KEY, {})
    if POLICY_KEY not in data and ref != "HEAD":
        # a base older than the evidence rules: its silence is no rule. The tier floors
        # of the checkout's own policy apply where stricter — they can only tighten (#229)
        head, _ = _policy_layers(root, "HEAD", _merged)
        own = head.get(POLICY_KEY)
        if isinstance(own, dict):
            rules = {k: own[k] for k in ("cross_model_from_tier", "own_family_from_tier")
                     if isinstance(own.get(k), int) and not isinstance(own.get(k), bool)
                     and own[k] < DEFAULTS.get(k, 4)}
    if not isinstance(rules, dict):
        return {}, f"{POLICY_KEY} must be an object"
    got = _merged(dict(DEFAULTS), rules)
    ranks, fams = got.get("ranks"), got.get("families")
    for key in ("cross_model_from_tier", "own_family_from_tier"):
        tier = got.get(key)
        if isinstance(tier, bool) or not isinstance(tier, int) or not 0 <= tier <= 4:
            return {}, f"{POLICY_KEY}.{key} must be an integer 0-4 (4: never), got {tier!r}"
    if not (isinstance(ranks, dict) and all(isinstance(k, str) and k and isinstance(v, int)
                                            and not isinstance(v, bool) for k, v in ranks.items())):
        return {}, f"{POLICY_KEY}.ranks must map model-id prefixes to integer ranks"
    if not (isinstance(fams, list) and all(isinstance(f, str) and f for f in fams)):
        return {}, f"{POLICY_KEY}.families must be a list of model-id prefixes"
    for key in ("python_files", "python_classes", "test_files"):
        if not (isinstance(got.get(key), list) and all(isinstance(g, str) and g for g in got[key])):
            return {}, f"{POLICY_KEY}.{key} must be a list of patterns"
    for key in ("required_records", "required_records_extra"):
        problem = required_records.rows_problem(got.get(key, []))
        if problem:
            return {}, f"{POLICY_KEY}.{key}: {problem}"
    return got, ""


def model_class(model: str, ranks: dict, families) -> tuple[str, int | None] | None:
    """(class, rank) of a concrete model id by its longest matching prefix: a ranked
    class, or another family (rank None). None: unknown."""
    best = max((p for p in [*ranks, *families] if model.startswith(p)), key=len, default=None)
    if best is None:
        return None
    return best, ranks.get(best) if best in ranks else None


# --- reading the evidence --------------------------------------------------------

def _binds(claimed: str, ids: set) -> bool:
    """A line binds by one of its plan's own ids, compared as the bundle's refute
    check compares them (`make_review_bundle._unrefuted`: the string itself) —
    never by an `owner/repo#N`, which names another (or an unprovable) repository."""
    return "/" not in claimed and claimed in ids


def _skip_kind(m) -> str:
    """A skip line's kind as the evidence rows name it (`codex-review` is `cross-model`)."""
    return "cross-model" if m.group("kind") == "codex-review" else m.group("kind")


def _bound_skips(line: str, ids: set) -> frozenset:
    """The skip kinds this one line names for the work `ids`."""
    return frozenset(_skip_kind(m) for m in SKIP_LINE.finditer(line)
                     if _binds(m.group("work"), ids))


def _bound_root_cause(line: str, ids: set) -> bool:
    """Whether this one line names a ROOT-CAUSE of the work `ids`."""
    return any(_binds(m.group("work"), ids) for m in ROOT_CAUSE_LINE.finditer(line))


def _skips(texts: list[str], ids: set) -> frozenset:
    return frozenset().union(*(_bound_skips(t, ids) for t in texts))


def _refuted(texts: list[str], ids: set) -> bool:
    return any(_binds(m.group("work"), ids) for t in texts for m in REFUTE_LINE.finditer(t))


def _root_caused(texts: list[str], ids: set) -> bool:
    return any(_bound_root_cause(t, ids) for t in texts)


def _fix_streak(root: Path, base: str | None, head: str | None) -> int | None:
    import check_fix_streak  # noqa: PLC0415 — only a code pass needs it
    if not (base and head):
        return None
    return check_fix_streak.max_streak(root, base, head)


# --- what the branch adds: blocked code rounds and journal records (v2.77) ---------
# A blocked round is the branch's when its line's content is absent from every record file
# at the fork point — compared by content, wherever the line went: `compact_journal` folding
# a shard into `archive/` makes no old line new, a rebase keeps a line the branch's, and a
# merge of main moves the fork along (plan review rounds 3–4). Journal evidence is read by
# the evidence readers on both sides of that fork, from the snapshot the attestation writes
# (head plus today's shard/--with), never by a second content normalization. An earlier work
# of the same issue, already on main, lends this one neither its blocks nor its skips and
# causes.

# the skips a branch's journal may carry: the per-round duties (`replan`, `class-test`) whose
# ROOT-CAUSE lines the journal holds too; `ac-trace`, `cross-model`, `refute` and every other
# kind count from the plan alone, as before v2.77
JOURNAL_SKIPS = frozenset({"replan", "class-test"})
_LIST_LEAD = re.compile(r"^\s*(?:(?:[-*+]|\d+[.)])\s+(?:\[[ xX]\]\s+)?)?")
# a reason after `sites: none —`, not the brief's placeholder
_REASON = re.compile(r"^" + PLACEHOLDER + r"\S")


def _content(line: str) -> str:
    """A record line as compared across files: no list marker, no surrounding blanks."""
    return _LIST_LEAD.sub("", line).strip()


def _fork(root: Path, head: str) -> str | None:
    """The head's fork point from the integration branch (`check_review.merge_base`);
    "" when the head is on an integration ref itself — no round of its own; None when
    git cannot tell (no integration ref, an ambiguous fork): unknown, never "none"."""
    try:
        fork = merge_base(root, head)
    except GitReadError:
        return None
    if fork:
        return fork
    # merged or missing, told apart as `check_review.full_round_base_problem` does
    contained = any(_git(root, "rev-parse", "--verify", "-q", f"{ref}^{{commit}}").returncode == 0
                    and _git(root, "merge-base", "--is-ancestor", head, ref).returncode == 0
                    for ref in integration_refs(root))
    return "" if contained else None


def _lexical_rel(root: Path, p: Path) -> tuple[str | None, str]:
    """(repo-relative posix path, why) of `p`, from the strings alone: no lstat, no
    resolve — `root` is the resolved root the caller holds."""
    p = Path(os.path.normpath(p if Path(p).is_absolute() else root / p))
    try:
        rel = p.relative_to(root).as_posix()
    except ValueError:
        return None, f"{p} is outside this repository — refused"
    if rel in ("", ".") or rel.startswith("../"):
        return None, f"{p} is outside this repository — refused"
    return rel, ""


def _link_problem(root: Path, rel: str) -> str:
    """Why `rel` is refused by an lstat walk of its components (a symlink as the path or a
    parent, a parent that is no directory), or "". A missing component ends the walk:
    nothing below it can be a link."""
    parts = rel.split("/")
    cur = os.fspath(root)
    for i, part in enumerate(parts):
        cur = os.path.join(cur, part)
        try:
            st = os.lstat(cur)
        except FileNotFoundError:
            return ""
        except OSError as exc:
            return f"{rel} cannot be checked ({exc}) — refused"
        if stat.S_ISLNK(st.st_mode):
            if i == len(parts) - 1:
                return f"{rel} is a symlink — refused, not followed"
            return f"{rel} lies under the symlink {'/'.join(parts[:i + 1])} — refused, not followed"
        if i < len(parts) - 1 and not stat.S_ISDIR(st.st_mode):
            return f"{'/'.join(parts[:i + 1])} is no directory — {rel} refused"
    return ""


def _repo_rel(root: Path, p: Path) -> tuple[str | None, str]:
    """(lexical repo-relative path, why) for one path the attestation may write: the
    strings first (`_lexical_rel`), then every component with lstat (`_link_problem`), so
    a symlink (the path or any parent) is refused by name before anything follows it."""
    root = Path(os.path.realpath(root))
    rel, why = _lexical_rel(root, p)
    if rel is None:
        return None, why
    why = _link_problem(root, rel)
    return (None, why) if why else (rel, "")


def _jrel(root: Path, journal_dir: Path | None) -> str:
    """The attested `--journal-dir` as a repository path, from the strings alone (I12: an
    object reader asks no lstat); "" when it lies outside the repository."""
    if journal_dir is None:
        return ""
    rel, _why = _lexical_rel(root, journal_dir)
    return rel or ""


def _at_fork(root: Path, fork: str, journal_dir: Path | None = None, *, jrel: str | None = None
             ) -> tuple[set[str], list[str]] | None:
    """(the contents of every line at the fork point as the round counter reads blocks, the
    journal texts there for the evidence readers). The blocks are read as `attest._texts`
    reads them — a journal less its fences, a plan as rendered; a line quoted in a fence on
    main is no line of the fork: it hides no real line of the branch. None when git cannot
    read them (`_records_at`, I12). `jrel`: the `--journal-dir` as the snapshot placed it."""
    texts = _records_at(root, fork, RECORD_KINDS, _jrel(root, journal_dir) if jrel is None else jrel)
    if texts is None:
        return None
    journal = [text for rel, text in texts if record_kind(rel) in ("journal", None)]
    plans = [text for rel, text in texts if record_kind(rel) not in ("journal", None)]

    def contents(views: list[str]) -> set[str]:
        return {_content(ln) for text in views for ln in text.splitlines() if ln.strip()}
    return (contents([_unfenced(t) for t in journal] + [readable(t) for t in plans]), journal)


# `dir_fd` and `O_NOFOLLOW` as the platform has them, fixed at import: a later patch of
# `os.open` (a test) must not switch the walk (R-6: Windows has neither)
_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_DIR_FD = bool(_NOFOLLOW) and os.open in os.supports_dir_fd


def _open_in_repo(root: str, rel: str, flags: int, mode: int = 0o644) -> int:
    """A descriptor of `rel` below `root` that follows no symlink. With `dir_fd` and
    `O_NOFOLLOW` each directory is opened from the one above it, the file from the last
    one; elsewhere (R-6) the joined path, the caller's identity check standing in.
    OSError when a component is a link, missing or no directory."""
    parts = rel.split("/")
    if not _DIR_FD:
        return os.open(os.path.join(root, *parts), flags | _NOFOLLOW | getattr(os, "O_BINARY", 0), mode)
    directory = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    dfd = os.open(root, directory)
    try:
        for part in parts[:-1]:
            nfd = os.open(part, directory | _NOFOLLOW, dir_fd=dfd)
            os.close(dfd)
            dfd = nfd
        return os.open(parts[-1], flags | _NOFOLLOW, mode, dir_fd=dfd)
    finally:
        os.close(dfd)


def _create_in_repo(root: str, rel: str, flags: int, mode: int = 0o644) -> int:
    """A descriptor of a new file `rel` below `root` (W2, design §8): the missing
    directories made from the one above (`mkdir(dir_fd=)`), each opened without
    following a link, the file by `O_CREAT|O_EXCL` — an existing name is never opened
    or overwritten (FileExistsError). Elsewhere (R-6) the joined path."""
    parts = rel.split("/")
    create = flags | os.O_CREAT | os.O_EXCL | _NOFOLLOW | getattr(os, "O_BINARY", 0)
    if not _DIR_FD:
        os.makedirs(os.path.join(root, *parts[:-1]), exist_ok=True)
        return os.open(os.path.join(root, *parts), create, mode)
    directory = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    dfd = os.open(root, directory)
    try:
        for part in parts[:-1]:
            try:
                os.mkdir(part, dir_fd=dfd)
            except FileExistsError:
                pass
            nfd = os.open(part, directory | _NOFOLLOW, dir_fd=dfd)
            os.close(dfd)
            dfd = nfd
        return os.open(parts[-1], create, mode, dir_fd=dfd)
    finally:
        os.close(dfd)


def append_checked(root: Path, rel: str, ident: tuple[int, int] | None, data: bytes,
                   separate: bytes = b"") -> str:
    """Append `data` to `rel` through a checked descriptor (W2, design §8, for
    `red_evidence`): opened without following a link and without `O_TRUNC`, its identity
    the one the path check saw at the start (`ident`; None: the file did not exist then and
    is made by `O_CREAT|O_EXCL`), `separate` first when the file is not empty, then the
    path's `lstat` equal to the descriptor's `fstat`. "" when appended, else why not."""
    root_s = os.path.realpath(root)
    try:
        fd = (_open_in_repo(root_s, rel, os.O_WRONLY | os.O_APPEND) if ident is not None
              else _create_in_repo(root_s, rel, os.O_WRONLY | os.O_APPEND))
    except OSError as exc:
        return f"{rel} cannot be opened without following a link ({exc}) — nothing appended"
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or (ident is not None and (st.st_dev, st.st_ino) != ident):
            return f"{rel} is another file than the one checked at the start — nothing appended"
        view = memoryview((separate if st.st_size else b"") + data)
        while view:
            view = view[os.write(fd, view):]
        try:
            now = os.lstat(os.path.join(root_s, *rel.split("/")))
        except OSError:
            now = None
        if now is None or (now.st_dev, now.st_ino) != (st.st_dev, st.st_ino):
            return f"{rel} was replaced while it was appended to — the file at the path is untouched"
        return ""
    finally:
        os.close(fd)


def _read_fd(fd: int) -> bytes:
    chunks = []
    while chunk := os.read(fd, 1 << 16):
        chunks.append(chunk)
    return b"".join(chunks)


def _read_at_start(fd: int) -> bytes:
    """Every byte of the file behind `fd` from offset 0, through that descriptor (W2 step
    2): `os.pread`, looked up at the call; where it is missing (Windows), `lseek` + `read`."""
    pread = getattr(os, "pread", None)
    if pread is None:
        os.lseek(fd, 0, os.SEEK_SET)
        return _read_fd(fd)
    chunks, offset = [], 0
    while chunk := pread(fd, 1 << 16, offset):
        chunks.append(chunk)
        offset += len(chunk)
    return b"".join(chunks)


def _repo_file(root: Path, p: Path, *, may_be_missing: bool
               ) -> tuple[str, bytes | None, tuple[int, int] | None] | tuple[None, str, None]:
    """(repo-relative path, bytes, (st_dev, st_ino)) of one path the attestation may
    write, or (None, why, None). Checked before any read (I4, I10): every component by
    lstat — a symlink, a path below one or no regular file is refused by name, never
    followed — then the file opened without following a link (`_open_in_repo`) and its
    fstat matched against that lstat; the bytes come from that descriptor. A journal
    shard not yet written is (rel, None, None): attest creates it after the check."""
    root = Path(os.path.realpath(root))
    rel, why = _lexical_rel(root, p)
    if rel is None:
        return None, why, None
    why = _link_problem(root, rel)
    if why:
        return None, why, None
    try:
        before = os.lstat(os.path.join(root, *rel.split("/")))
    except FileNotFoundError:
        return (rel, None, None) if may_be_missing else (None, f"{rel} is no file in this repository", None)
    except OSError as exc:
        return None, f"{rel} cannot be checked ({exc}) — refused", None
    if not stat.S_ISREG(before.st_mode):
        return None, f"{rel} is not a regular file — refused", None
    try:
        fd = _open_in_repo(os.fspath(root), rel, os.O_RDONLY)
    except OSError as exc:
        return None, f"{rel} cannot be opened without following a link ({exc}) — refused", None
    try:
        now = os.fstat(fd)
        if not stat.S_ISREG(now.st_mode) or (now.st_dev, now.st_ino) != (before.st_dev, before.st_ino):
            return None, f"{rel} changed while it was checked (another file at the path) — refused", None
        return rel, _read_fd(fd), (now.st_dev, now.st_ino)
    except OSError as exc:
        return None, f"{rel} cannot be read ({exc}) — refused", None
    finally:
        os.close(fd)


def attestation_files(root: Path, target: Path, with_files: list[Path],
                      journal_dir: Path | None = None
                      ) -> tuple[list[tuple[str, bytes | None]], list[str]]:
    """The one file set this attestation fixes: today's journal shard plus every `--with`
    record, as (repo-relative path, bytes). `attest.py` commits exactly these paths and
    the evidence check reads exactly these bytes — neither derives the set itself.
    None bytes: the journal target does not exist yet (attest writes it). Every path is
    checked by `_repo_file` before it is read; a refusal names it and is returned, never
    swallowed. Only the journal target contributes journal evidence; a report or plan
    rides the commit but is no shard. A path is carried once: named twice with the same
    bytes it is one entry, with different bytes it is refused (#308 R5)."""
    reads, problems, _jrel = _attestation_reads(root, target, with_files, journal_dir)
    return [(rel, data) for rel, data, _ident in reads], problems


def _attestation_reads(root: Path, target: Path, with_files: list[Path],
                       journal_dir: Path | None
                       ) -> tuple[list[tuple[str, bytes | None, tuple[int, int] | None]], list[str], str]:
    """`attestation_files` with each file's (st_dev, st_ino), and `jrel`: the attested
    `--journal-dir` as a repository path ("" for none, or a refused one)."""
    root = Path(os.path.realpath(root))
    files: list[tuple[str, bytes | None, tuple[int, int] | None]] = []
    problems: list[str] = []
    jrel = ""
    if journal_dir is not None:
        jrel, why = _repo_rel(root, journal_dir)
        if jrel is None:
            problems.append(why)  # the override itself is checked before any shard below it
            jrel = ""
    for p, may_be_missing in [(target, True), *((p, False) for p in with_files)]:
        rel, got, ident = _repo_file(root, p, may_be_missing=may_be_missing)
        if rel is None:
            problems.append(got)
            continue
        if may_be_missing and record_kind(rel) != "journal" and not (
                jrel and (rel == jrel or rel.startswith(jrel + "/"))):
            problems.append(f"{rel} is no journal shard — the attestation writes only its journal")
            continue
        seen = {r: d for r, d, _i in files}
        if rel in seen:
            if seen[rel] != got:
                problems.append(f"{rel} is named twice and read with different bytes — refused")
            continue
        files.append((rel, got, ident))
    return files, problems, jrel


# --- the snapshot (#308 round 6, design §4) ----------------------------------------

@dataclass(frozen=True)
class SnapFile:
    """One file of the snapshot: the bytes read through the checked descriptor and what
    the write phase compares against."""
    rel: str
    data: bytes | None  # None: today's shard, not yet written
    ident: tuple[int, int] | None  # (st_dev, st_ino) of the descriptor the bytes came from
    mode: str = "100644"  # 100755 only where `old` holds the path so (I4)
    index: str | None = None  # the index entry's oid at the snapshot; None: no entry
    blob: str | None = None  # the oid of `data`


@dataclass(frozen=True)
class Snapshot:
    """What one attestation fixes before it decides (design §4): `old` (HEAD at the
    snapshot), the files it carries, `E` (head plus them: the evidence) and `T0` (`old`
    plus them: the round counter), and the record sets of both trees, read once (§9)."""
    old: str | None
    head: str | None
    files: tuple[SnapFile, ...]
    jrel: str = ""
    E: str | None = None
    T0: str | None = None
    records_E: list[tuple[str, str]] | None = None
    records_T0: list[tuple[str, str]] | None = None
    problems: tuple[str, ...] = ()

    @property
    def carried(self) -> list[tuple[str, bytes | None]]:
        return [(f.rel, f.data) for f in self.files]


def _rev(root: Path, rev: str) -> str | None:
    r = _git(root, "rev-parse", "--verify", "-q", rev)
    return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else None


def _entries(out: str) -> dict[str, tuple[str, str]]:
    """path -> (mode, oid) of `ls-tree -z` (`<mode> <type> <oid>\\t<path>`) or `ls-files
    -s -z` (`<mode> <oid> <stage>\\t<path>`) output; a path in conflict maps to ("", "")."""
    out_map: dict[str, tuple[str, str]] = {}
    for raw in out.split("\0"):
        if not raw:
            continue
        meta, _tab, path = raw.partition("\t")
        fields = meta.split()
        if len(fields) != 3:
            continue
        mode, oid = fields[0], fields[2] if fields[1] in ("blob", "tree", "commit") else fields[1]
        conflict = fields[1] not in ("blob", "tree", "commit") and fields[2] != "0"
        out_map[path] = ("", "") if conflict or path in out_map else (mode, oid)
    return out_map


def _hash_blob(root: Path, data: bytes) -> str | None:
    r = subprocess.run(["git", "-C", str(root), "hash-object", "-w", "--stdin"], input=data,
                       capture_output=True, env=git_environment(), check=False)
    return r.stdout.decode().strip() if r.returncode == 0 else None


def _tree_with(root: Path, base: str | None, files: list[SnapFile]) -> str | None:
    """The tree of `base` (none: empty) with `files`' blobs laid over it, built in a
    private index in a temporary directory outside the worktree (I13′). None on failure."""
    with tempfile.TemporaryDirectory(prefix="attest-index-") as tmp:
        env = {**git_environment(), "GIT_INDEX_FILE": os.path.join(tmp, "index")}

        def run(*args: str, data: bytes | None = None) -> subprocess.CompletedProcess:
            return subprocess.run(["git", "-C", str(root), *args], input=data, capture_output=True,
                                  env=env, check=False)
        if run("read-tree", *([base] if base else ["--empty"])).returncode:
            return None
        info = b"".join(f"{f.mode} {f.blob}\t{f.rel}\0".encode("utf-8", "surrogateescape")
                        for f in files if f.blob)
        if info and run("update-index", "--add", "--replace", "-z", "--index-info", data=info).returncode:
            return None
        tree = run("write-tree")
        return tree.stdout.decode().strip() if tree.returncode == 0 else None


def snapshot(root: Path, target: Path, with_files: list[Path], journal_dir: Path | None,
             head: str | None = None) -> Snapshot:
    """The one snapshot of this attestation (design §4, D-6): `old` first, then the file
    set (`_attestation_reads`: the path check, the bytes through the checked descriptor),
    each file's mode from `old` (I4) and its index entry — one that is neither `old`'s
    nor the snapshot's blob is foreign work and refused (I6) — then the blobs and the two
    trees `E` (head + files) and `T0` (`old` + files), and their record sets, each read
    once (`_records_at`, §9). `head` defaults to `old`. No path-level read of the
    worktree below the root: the bytes come from the descriptors alone."""
    root = Path(os.path.realpath(root))
    old = _rev(root, "HEAD^{commit}")
    head = head or old
    reads, problems, jrel = _attestation_reads(root, target, with_files, journal_dir)
    rels = [rel for rel, _data, _ident in reads]
    at_old = _entries(_git(root, "--literal-pathspecs", "ls-tree", "-z", old, "--", *rels).stdout) \
        if old and rels else {}
    index = _entries(_git(root, "--literal-pathspecs", "ls-files", "-s", "-z", "--", *rels).stdout) \
        if rels else {}
    files: list[SnapFile] = []
    for rel, data, ident in reads:
        blob = _hash_blob(root, data) if data is not None else None
        if data is not None and blob is None:
            problems.append(f"{rel}: git hash-object failed — refused")
            continue
        was = at_old.get(rel)
        staged = index.get(rel)
        if staged == ("", ""):
            problems.append(f"{rel} is in conflict in the index — resolve it first")
        elif data is None and was is not None:
            problems.append(f"{rel} is at HEAD but missing in the worktree — restore it, or "
                            f"commit its removal first")
        elif staged is None and was is not None:
            problems.append(f"{rel} is staged as removed — foreign work in the index; commit or "
                            f"unstage it first")
        elif staged is not None and staged[1] not in {blob, was[1] if was else None}:
            problems.append(f"{rel} is staged with other bytes than the worktree and HEAD hold "
                            f"({staged[1][:12]}) — foreign work in the index; commit or unstage it "
                            f"first")
        files.append(SnapFile(rel, data, ident, "100755" if was and was[0] == "100755" else "100644",
                              staged[1] if staged else None, blob))
    t0 = _tree_with(root, old, files)
    e = t0 if head == old else (_tree_with(root, head, files) if head else None)
    if t0 is None or e is None:
        problems.append("git cannot build the snapshot's trees — refused")
    records_t0 = _records_at(root, t0, RECORD_KINDS, jrel) if t0 else None
    records_e = records_t0 if e == t0 else (_records_at(root, e, RECORD_KINDS, jrel) if e else None)
    return Snapshot(old, head, tuple(files), jrel, e, t0, records_e, records_t0, tuple(problems))


_LINK_MODES = ("120000", "160000")


def _homes(kinds: tuple[str, ...], jrel: str) -> list[str]:
    homes = []
    if "journal" in kinds:
        homes += [JOURNAL_DIR, *([jrel] if jrel and jrel != JOURNAL_DIR else [])]
    if "plan" in kinds or "plan-archive" in kinds:
        homes.append(PLANS_ACTIVE)
    if "spec-plan" in kinds:
        homes.append(SPECS_DIR)
    return homes


def _records_at(root: Path, ref: str, kinds: tuple[str, ...], jrel: str
                ) -> list[tuple[str, str]] | None:
    """(path, text) of every record of `kinds` in the tree `ref` — the journal's shards
    include the `.md` files under `jrel`, the attested `--journal-dir` — or None when the
    tree cannot be read or holds no answer (I12, design §9): every prefix of a home or of
    `jrel` is absent or a directory (040000); a symlink or gitlink that is a record, or on
    the way to one, is unknown — never its link text, never an empty home (§10,
    I12-Minor); any other such entry is no record and passed over. Git objects only: no
    path of the worktree is touched, the pathspecs are literal, a blob is read by oid."""
    homes = _homes(kinds, jrel)
    if not homes:
        return []
    # one non-recursive listing per depth: given `a` and `a/b` at once, ls-tree shows only
    # `a/b`, and an absent `a` would look like an absent `a/b`
    top: dict[str, tuple[str, str]] = {}
    for depth in range(1, max(len(h.split("/")) for h in homes) + 1):
        level = list(dict.fromkeys("/".join(h.split("/")[:depth]) for h in homes
                                   if len(h.split("/")) >= depth))
        r = _git(root, "--literal-pathspecs", "ls-tree", "-z", ref, "--", *level)
        if r.returncode:
            return None
        top |= _entries(r.stdout)
    present = []
    for h in homes:
        parts = h.split("/")
        for i in range(len(parts)):
            entry = top.get("/".join(parts[:i + 1]))
            if entry is None:
                break  # absent: nothing below it
            if entry[0] != "040000":
                return None
        else:
            present.append(h)
    if not present:
        return []
    r = _git(root, "--literal-pathspecs", "ls-tree", "-r", "-z", ref, "--", *present)
    if r.returncode:
        return None

    def journal(rel: str) -> bool:
        return "journal" in kinds and bool(jrel) and rel.startswith(jrel + "/")

    def record(rel: str) -> bool:
        return record_kind(rel) in kinds or (journal(rel) and rel.endswith(".md"))
    out: list[tuple[str, str]] = []
    for rel, (mode, oid) in _entries(r.stdout).items():
        if mode in _LINK_MODES:
            if record(rel) or journal(rel) or record(rel + "/x.md") or record(f"{rel}/{SPEC_PLAN}"):
                return None
            continue
        if not record(rel):
            continue
        blob = subprocess.run(["git", "-C", str(root), "cat-file", "blob", oid], capture_output=True,
                              env=git_environment(), check=False)
        if blob.returncode:
            return None
        out.append((rel, blob.stdout.decode("utf-8", errors="replace")))
    return out


def _evidence_keys(line: str, plan_ids: set, skip_ids: set) -> frozenset:
    """The evidence one rendered line carries, as the readers count it: this work's
    ROOT-CAUSE lines and the skip kinds the journal may lift (`JOURNAL_SKIPS`). The keys
    are the readers' own parsed fields, so a quotation the reader rejects carries none."""
    keys = set()
    for m in ROOT_CAUSE_LINE.finditer(line):
        if _binds(m.group("work"), plan_ids):
            keys.add(("root-cause", m.group("work"), int(m.group("round")),
                      m.group("text").strip()))
    for m in SKIP_LINE.finditer(line):
        if _binds(m.group("work"), skip_ids):
            kind = _skip_kind(m)
            if kind in JOURNAL_SKIPS:
                keys.add(("skip", kind, m.group("work"), m.group("reason").strip()))
    return frozenset(keys)


def _journal_keys(texts: list[str], plan_ids: set, skip_ids: set) -> set:
    """Every evidence key the readers find in `texts`, as rendered (fences and comments
    removed)."""
    return {key for text in texts for line in readable(text).splitlines()
            for key in _evidence_keys(line, plan_ids, skip_ids)}


def _journal_records(root: Path, head: str, journal_dir: Path | None,
                     snapshot: Snapshot | None) -> list[str] | None:
    """The journal texts the evidence reads: those of `E` (head plus the files this
    attestation carries, `Snapshot.records_E`), or at `head` without a snapshot. The
    shards of a `--journal-dir` carry no record kind of their own. None: unknown."""
    if snapshot is not None:
        records = snapshot.records_E
    else:
        records = _records_at(root, head, ("journal",), _jrel(root, journal_dir))
    if records is None:
        return None
    return [text for rel, text in records if record_kind(rel) in ("journal", None)]


def _branch_records(root: Path, head: str, blocks: list[tuple[int, str]] | None,
                    journal_dir: Path | None, plan_ids: set, skip_ids: set,
                    snapshot: Snapshot | None = None
                    ) -> tuple[list[int] | None, str, frozenset]:
    """(the blocked code rounds the branch adds, its journal records, the evidence keys the
    readers saw at the fork and in `E`). The rounds are those of `blocks` —
    `attest.block_lines` at T0, the set the round counter counts — less the lines present
    at the fork point. None: unknown. The journal records are read by the same evidence
    readers from `E` (`_journal_records`) less what the fork already holds; what that run
    yields counts, nothing else. Objects only (I12): a worktree evidence line outside `E`
    is refused by `_foreign_shard_problems`, never counted here."""
    fork = _fork(root, head)
    if fork == "":
        return [], "", frozenset()
    old = (_at_fork(root, fork, journal_dir, jrel=snapshot.jrel if snapshot is not None else None)
           if fork is not None else None)
    journal = _journal_records(root, head, journal_dir, snapshot)
    if old is None or blocks is None or journal is None:
        return None, "", frozenset()
    old_blocks, old_journal = old
    rounds = sorted({r for r, line in blocks if _content(line) not in old_blocks})
    fork_keys = _journal_keys(old_journal, plan_ids, skip_ids)
    rendered = [line for text in journal for line in readable(text).splitlines()]
    seen = {key for line in rendered for key in _evidence_keys(line, plan_ids, skip_ids)}
    new_keys = seen - fork_keys
    new = [line for line in rendered if _evidence_keys(line, plan_ids, skip_ids) & new_keys]
    return rounds, "\n".join(new), frozenset(fork_keys | seen)


def _foreign_shard_problems(root: Path, head: str, journal_dir: Path | None, plan_ids: set,
                            skip_ids: set, known: frozenset) -> list[str]:
    """AC-2, a refusal reader (I5): a worktree journal line whose evidence (this work's
    ROOT-CAUSE, the skip kinds the journal counts) is neither at the fork nor in `E`
    (`known`) is refused by name — committed or carried, it would count; only in the
    worktree it must not count in silence. The set read is that of `_root_caused`/`_skips`,
    so foreign work and kinds read only from the plan stay invisible."""
    problems: list[str] = []
    for rel, f in record_files(root, ("journal",), journal_dir=journal_dir):
        safe_rel, data, _ident = _repo_file(root, f, may_be_missing=False)
        if safe_rel is None:
            problems.append(f"{rel}: {data}")
            continue
        for n, line in enumerate(readable(data.decode("utf-8", errors="replace")).splitlines(), 1):
            if _evidence_keys(line, plan_ids, skip_ids) - known:
                problems.append(
                    f"{rel}:{n}: `{line.strip()}` is neither at {head[:12]} nor carried by this "
                    f"attestation — commit it, or pass {rel} with --with")
    return problems


def _tracked(root: Path, head: str) -> list[str] | None:
    r = _git(root, "ls-tree", "-r", "-z", "--name-only", head)
    return [p for p in r.stdout.split("\0") if p] if r.returncode == 0 else None


def _suffix_hits(file: str, tracked: list[str]) -> list[str]:
    """The tracked paths that end in `file` below a directory (never `file` itself)."""
    return [p for p in tracked if p.endswith("/" + file)]


def _test_file(file: str, tracked: list[str] | None) -> tuple[str | None, str]:
    """(the tracked path a reference names, why none): the path itself, or the one tracked
    path ending in it — a pytest id relative to its rootdir (`backend/`), a JUnit
    `classname` path. Several are none: a guess could pick another test (fail closed)."""
    if tracked is None:
        return None, "git cannot list the files at head"
    file = file.removeprefix("./")
    if file in tracked:
        return file, ""
    hits = _suffix_hits(file, tracked)
    if len(hits) == 1:
        return hits[0], ""
    if hits:
        return None, f"{file} names several tracked files at head ({', '.join(hits[:3])}) — name the path"
    return None, f"{file} is no tracked file at head"


class Resolved(NamedTuple):
    file: str
    name: str
    path: str | None
    why: str | None


class Identity(NamedTuple):
    path: str
    name: str


def identity_of(resolved: Resolved) -> Identity | None:
    """The test identity a `Resolved` names, or None: a `why` means the gate reads no test
    there, so the reference has no identity and collides with nothing. Every reader of an
    identity — the `sites:` check, the collision check, the class-test row — goes through
    this one function."""
    if resolved.why is not None or resolved.path is None:
        return None
    return Identity(resolved.path, resolved.name)


def resolve_tests(tests, files: list[str] | None, read, rules: dict) -> list[Resolved]:
    """The one reading of a test reference — the gate's (`_class_test_problem`) and
    red_evidence's (`_reference_problem`). `files` is the tracked listing (None: git
    could not list it); `read(rel)` returns the text at the reviewed side or None."""
    out: list[Resolved] = []
    for file, name in claimed_tests(tests):
        path, why = _test_file(file, files)
        if path is not None:
            why = text_status(read(path), path, name, rules)
        if why is not None and path == file.removeprefix("./"):
            # the exact path refuses: a pytest id relative to its rootdir (`backend/`) names
            # the one deeper namesake that holds the test; several stay a guess
            other = _suffix_hits(path, files or [])
            if len(other) == 1 and text_status(read(other[0]), other[0], name, rules) is None:
                why = None
                path = other[0]
        out.append(Resolved(file, name, path, why))
    return out


def _class_test_problem(root: Path, head: str, text: str, tracked: list[str] | None,
                        rules: dict) -> str | None:
    """Why one ROOT-CAUSE line's text is no class test, or None: `sites: none — <reason>`,
    or sites and a test after them that `test_status` finds at head (through the one
    resolver, `resolve_tests`)."""
    _cause, sites, tests = root_cause_parts(text)
    if sites is None:
        return "its ROOT-CAUSE line names no `sites:`"
    if not sites:
        return "its `sites:` segment is empty"
    if sites.lower() == "none":
        return None if _REASON.match(tests) else "`sites: none` without a reason after it"
    if not claimed_tests(tests):
        return "its ROOT-CAUSE line names no `<path>::<test>` after `sites:`"
    refs = resolve_tests(tests, tracked, lambda rel: _show(root, head, rel), rules)
    if any(identity_of(r) is not None for r in refs):
        return None
    return "; ".join(r.why for r in refs)


def _class_tests_open(root: Path, head: str, rounds: list[int], texts: list[str], ids: set,
                      rules: dict) -> tuple[str, ...]:
    """`<round> (<why>)` per blocked round without a class test among `texts`' ROOT-CAUSE
    lines of the work (`ids`); one line of the round that is one suffices."""
    causes: dict[int, list[str]] = {}
    for t in texts:
        for m in ROOT_CAUSE_LINE.finditer(t):
            if _binds(m.group("work"), ids):
                causes.setdefault(int(m.group("round")), []).append(m.group("text"))
    tracked = _tracked(root, head) if causes else None
    out = []
    for r in rounds:
        whys = [_class_test_problem(root, head, text, tracked, rules) for text in causes.get(r, [])]
        if None not in whys:
            out.append(f"{r} ({whys[0] if whys else 'no ROOT-CAUSE line'})")
    return tuple(out)


def _plan(root: Path, ids: set, head: str, snapshot: Snapshot | None = None
          ) -> tuple[str, str, str, str]:
    """(state, path, text at head, records appended since) of the work's plan —
    active or Spec Kit, else archived (a late lens attests after the plan's own archive
    commit). Objects only (I12): the plans at head (`_records_at`), the appended records
    from `E` — only when the plan rides this attestation (#308 R5), at its path or its
    archive path. `differs`: the riding plan holds more than records appended after the
    plan's last line (E1, the gate's `records_only`); the worktree and the index are read
    for that refusal apart (`_plan_differs`), never for what counts. Without a snapshot
    (`dispatch`'s preview) nothing rides."""
    records = _records_at(root, head, PLAN_KINDS + ("plan-archive",), "")
    if records is None:
        return "unreadable", "", "", ""
    found = [(rel, text) for rel, text in records
             if ids & {work_key(i) for i in _plan_work_ids(plan_stem(rel), _unfenced(text),
                                                            include_dedated=True)}]
    active = [f for f in found if record_kind(f[0]) != "plan-archive"]
    found = active or found
    if len(found) > 1:
        found = [f for f in found if work_key(plan_stem(f[0])) in ids] or found
    if not found:
        return "missing", "", "", ""
    if len(found) > 1:
        return "ambiguous", ", ".join(rel for rel, _t in found), "", ""
    rel, text = found[0]
    if snapshot is None:
        return "ok", rel, text, ""
    # a plan archived by its own commit after a first lens rides at its archive path
    moved = _archived_as(root, rel)
    riding_rels = {f.rel for f in snapshot.files if f.data is not None}
    at_e = dict(snapshot.records_E or [])
    now = next((at_e[p] for p in (rel, moved) if p in riding_rels and p in at_e), None)
    if now is None or now == text:
        return "ok", rel, text, ""
    if not records_only(text, now):
        return "differs", rel, text, ""
    added = now[len(text):] if now.startswith(text) else "\n".join(
        ln for ln in now.splitlines() if ln not in set(text.splitlines()))
    return "ok", rel, text, added


def _archived_as(root: Path, rel: str) -> str:
    """Where the archive takes this plan (`attest.archive_rel`, lexical) — a plan archived
    by its own commit after a first lens is read where it went."""
    from attest import archive_rel  # late: attest imports this module
    return archive_rel(rel)


def _plan_differs(root: Path, rel: str, text: str) -> bool:
    """A refusal reader (I5): does the worktree or the index hold more of the plan `rel`
    than records appended after its text at head (E1)? Read for the refusal only — what
    counts comes from `E` (`_plan`)."""
    moved = _archived_as(root, rel)
    return any(now and now != text and not records_only(text, now)
               for now in (_worktree_text(root, rel) or _worktree_text(root, moved),
                           _index_text(root, rel) or _index_text(root, moved)))


def _worktree_text(root: Path, rel: str) -> str:
    """The file in the worktree; "" when it is not there (deleted or unreadable)."""
    try:
        return (root / rel).read_text(encoding="utf-8", errors="replace") if rel else ""
    except OSError:
        return ""


def _index_text(root: Path, rel: str) -> str:
    r = _git(root, "show", f":{rel}") if rel else None
    return r.stdout if r is not None and r.returncode == 0 else ""


UNMEASURED_REPORT = "unmeasured-report"  # plan_session_source: a report exists, without a model


def _planned_model(root: Path, issues: set[int]) -> tuple[str | None, bool]:
    """(the plan session's model from the newest `planned` report of the work's
    issues, whether such a report exists) — report.py. A report that measured no
    model still exists: the plan's own `plan-session model:` line, written by the
    session about itself, does not stand in for it (#230)."""
    if not issues:
        return None, False
    from report import UNMEASURED, read_reports  # late: report imports dispatch lazily
    rows = [r for r in read_reports(root) if r.get("issue") in issues and r.get("state") == "planned"]
    if not rows:
        return None, False
    newest = max(rows, key=lambda r: r.get("epoch") if isinstance(r.get("epoch"), int) else 0)
    model = str(newest.get("model") or "")
    return (None if model in ("", UNMEASURED) else model), True


# a criterion struck on purpose, with its reason (#234): `AC-3: struck — <reason>`
# or `dropped`; listed, boxed or bold like a criterion line; a bare strike-through
# (`~~AC-3~~`) names no reason and strikes nothing. The mark is lower case and a
# hyphen separates only with spaces around it: `AC-3: Dropped: When the socket
# drops …` and `AC-3: Dropped-connection retry` are criteria (plan review, refute)
_STRUCK_MARK = r"(?:struck|dropped)(?:[ \t]*[—–:]|[ \t]+--?[ \t])"
STRUCK_LINE = re.compile(
    r"^[ \t]*(?:[-*+][ \t]+)?(?:\[[ xX]\][ \t]+)?(?:\*\*)?" + _AC
    + r"(?:\*\*)?[ \t]*:(?:\*\*)?[ \t]*" + _STRUCK_MARK + r"[ \t]*"
    + PLACEHOLDER + r"\S*\w",
    re.MULTILINE)
# a test a line names: a file with its extension, then `::` (prose like `std::vector` is none)
_NAMES_A_TEST = re.compile(r"[\w./-]+\.\w+::\w")
# the report's confirmation of a strike: the same mark, the reason optional
_STRUCK_CONFIRMED = re.compile(r"(?:struck|dropped)(?:[ \t]*[—–:]|[ \t]+--?[ \t]|[ \t]*$)")


def struck(text: str) -> set[str]:
    """The criteria a text strikes, each with a reason."""
    return {ac_key(m) for m in STRUCK_LINE.finditer(text)}


# another issue's criterion, cited qualified: `#2659/AC-11`, `owner/repo#9/AC-2` (#287).
# Only this form is read as a citation; a bare `AC-<id>` is always the plan's own
_QUALIFIED = re.compile(r"(?<![\w&])(?:[\w.-]+/[\w.-]+)?#(?P<n>\d+)/" + _AC + r"(?![\w])")


def foreign_criteria(plan: str, spec: str) -> frozenset[str]:
    """The criteria the plan cites from another issue, qualified as `#N/AC-<id>` (#287) —
    not required, and named by attest, never dropped in silence. A bare `AC-<id>` stays
    the plan's own: prose cannot tell a citation from an own criterion with its origin."""
    return _criteria(plan, spec)[2]


def required_criteria(plan: str, spec: str) -> frozenset[str]:
    """The criteria a code-review pass traces: every id the plan or its spec names,
    less those a `DoD-deviation: open` keeps open and those struck with a reason.
    A plan strikes only its own criteria: one the spec still names stays required
    unless the spec strikes it (#234 plan review: a plan line must not quietly drop
    a spec criterion)."""
    return _criteria(plan, spec)[0]


def struck_criteria(plan: str, spec: str) -> frozenset[str]:
    """The criteria struck with a reason — no test, but the code review's report
    confirms each (`AC-<id>: struck`), so a strike added after the plan review is
    seen by an independent reviewer (plan review)."""
    return _criteria(plan, spec)[1]


def _cited_elsewhere(plan: str) -> tuple[str, set[str]]:
    """(the plan with its citations of other issues blanked, the ids cited that way). A
    citation naming the number of an issue the plan declares — in any form `check_review`
    reads (`ref_token`), any repository — is no citation: it stays a mention (fail closed)."""
    from check_review import ISSUE_DECL, parse_issue_ref, ref_token  # noqa: PLC0415
    mine: set[int] = set()
    for m in ISSUE_DECL.finditer(plan):
        tok = ref_token(m.group(1))
        ref = parse_issue_ref(tok) or ((None, int(tok)) if tok.isascii() and tok.isdigit() else None)
        if ref:
            mine.add(ref[1])
    cited: set[str] = set()

    def blank(m: re.Match) -> str:
        if int(m.group("n")) in mine:
            return m.group(0)
        cited.add(ac_key(m))
        return " " * len(m.group(0))
    return _QUALIFIED.sub(blank, plan), cited


# any bare mention of an id, hyphen compounds included (`AC-4-Messung`): it keeps a cited id
# the plan's own (#287, fail closed)
_BARE_MENTION = re.compile(r"\b" + _AC + r"(?!\w)")


def _criteria(plan: str, spec: str) -> tuple[frozenset[str], frozenset[str], frozenset[str]]:
    plan, spec = _EXAMPLE_SPAN.sub(" ", plan), _EXAMPLE_SPAN.sub(" ", spec)
    in_spec = {ac_key(m) for m in AC_ID.finditer(spec)}
    plan, cited = _cited_elsewhere(plan)
    bare = {ac_key(m) for m in _BARE_MENTION.finditer(plan)}
    named = {ac_key(m) for m in AC_ID.finditer(plan)} | in_spec | (cited & bare)
    foreign = cited - named  # a bare mention or the spec keeps an id the work's own
    open_ = held_open(plan)
    gone = (struck(spec) | (struck(plan) - in_spec)) - open_
    return frozenset(named - open_ - gone), frozenset(gone & named), frozenset(foreign)


def held_open(plan: str) -> set[str]:
    """Criteria a `DoD-deviation: open AC-<id>` line keeps open on purpose — the
    train's grammar (`train.DOD_DEVIATION`, `_HOLDS`); they have no test to name."""
    from train import _HOLDS, DOD_DEVIATION  # late: the train is large
    out: set[str] = set()
    for m in DOD_DEVIATION.finditer(plan):
        held = _HOLDS.match(m.group(1))
        if held:
            out |= {ac_key(a) for a in AC_ID.finditer(held.group(0))}
    return out


def _claims(texts: list[str]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for t in texts:
        for m in AC_LINE.finditer(t):
            out.setdefault(ac_key(m), []).append(m.group("body"))
    return out


# --- does the named test run? -----------------------------------------------------
# Judged by what pytest collects and which names resolve to a skip — never by
# words in the source (#225 refute: a parametrize value "--skip" refused a test;
# a helper, a Markdown file and an uncollected class proved criteria).

_PYTEST_OFF = {"skip", "skipif", "xfail"}  # pytest.mark.<these>
_PYTEST_CALLS = {"skip", "xfail", "importorskip"}  # pytest.<these>() skip at run time
_UNITTEST_OFF = {"skip", "skipIf", "skipUnless", "expectedFailure"}


class _Names:
    """What the module's top-level imports and assignments make of a name:
    `pytest`, `pytest.mark`, `unittest`, a unittest decorator, `SkipTest` — or a
    value that is a skip mark (an alias decorator)."""

    def __init__(self, tree: ast.Module):
        self.kind: dict[str, str] = {}
        for node in tree.body:
            if isinstance(node, ast.Import):
                for a in node.names:
                    if a.name in ("pytest", "unittest"):
                        self.kind[a.asname or a.name] = a.name
            elif isinstance(node, ast.ImportFrom) and node.module in ("pytest", "unittest", "_pytest.mark"):
                for a in node.names:
                    if node.module == "pytest" and a.name == "mark":
                        self.kind[a.asname or a.name] = "pytest.mark"
                    elif node.module == "pytest" and a.name in _PYTEST_CALLS:
                        self.kind[a.asname or a.name] = f"pytest.{a.name}"
                    elif node.module == "unittest" and a.name in (*_UNITTEST_OFF, "SkipTest"):
                        self.kind[a.asname or a.name] = f"unittest.{a.name}"
        for node in tree.body:  # an alias bound to a mark: `off = pytest.mark.skip(...)`
            value = node.value if isinstance(node, (ast.Assign, ast.AnnAssign)) else None
            targets = node.targets if isinstance(node, ast.Assign) else [getattr(node, "target", None)]
            if value is not None and self.off(value):
                for t in targets:
                    if isinstance(t, ast.Name):
                        self.kind[t.id] = "off"

    def path(self, expr: ast.expr) -> str:
        """`pytest.mark.skip` for `pt.mark.skip`, `mark.skip`, `pytest.mark.skip(...)`."""
        if isinstance(expr, ast.Call):
            return self.path(expr.func)
        if isinstance(expr, ast.Attribute):
            head = self.path(expr.value)
            return f"{head}.{expr.attr}" if head else ""
        if isinstance(expr, ast.Name):
            return self.kind.get(expr.id, "")
        return ""

    def off(self, expr: ast.expr | None) -> bool:
        """A mark (or list of marks) that skips or expects failure."""
        if expr is None:
            return False
        if isinstance(expr, (ast.List, ast.Tuple)):
            return any(self.off(e) for e in expr.elts)
        p = self.path(expr)
        return p == "off" or p in {f"pytest.mark.{m}" for m in _PYTEST_OFF} \
            or p in {f"unittest.{m}" for m in _UNITTEST_OFF}

    def skips(self, node: ast.AST) -> bool:
        """A statement that skips when it runs: `pytest.skip()`, `importorskip`,
        `self.skipTest()`, `raise SkipTest`."""
        for n in ast.walk(node):
            if isinstance(n, ast.Call):
                p = self.path(n)
                if p in {f"pytest.{c}" for c in _PYTEST_CALLS}:
                    return True
                if isinstance(n.func, ast.Attribute) and n.func.attr == "skipTest":
                    return True
            if isinstance(n, ast.Raise) and n.exc is not None:
                p = self.path(n.exc)
                if p in ("unittest.SkipTest", "unittest.case.SkipTest") or p.endswith("skip.Exception"):
                    return True
        return False


def _marked_off(body: list[ast.stmt], names: _Names) -> bool:
    """A `pytestmark` in this scope that skips."""
    for node in body:
        targets = (node.targets if isinstance(node, ast.Assign)
                   else [node.target] if isinstance(node, ast.AnnAssign) else [])
        if any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in targets) and names.off(node.value):
            return True
    return False


def _collected_class(node: ast.ClassDef, classes: list[str]) -> bool:
    """pytest collects classes named by `python_classes` (default `Test*`) without
    `__init__`, and every TestCase subclass."""
    if any(ast.unparse(b).split(".")[-1].endswith("TestCase") for b in node.bases):
        return True
    return any(fnmatch.fnmatchcase(node.name, c if any(ch in c for ch in "*?[") else c + "*")
               for c in classes) and not any(
        isinstance(n, ast.FunctionDef) and n.name == "__init__" for n in node.body)


def _not_collected(body: list[ast.stmt]) -> bool:
    """`__test__ = False` in a module or class."""
    return any(isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "__test__" for t in n.targets)
               and isinstance(n.value, ast.Constant) and n.value.value is False for n in body)


_SETUPS = {"setUp", "setUpClass", "setup_method", "setup_class", "setup_function", "setup_module", "setup"}


def _is_autouse(node: ast.stmt, names: _Names) -> bool:
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return False
    return any(isinstance(d, ast.Call) and names.path(d).endswith("fixture")
               and any(k.arg == "autouse" and isinstance(k.value, ast.Constant) and k.value.value is True
                       for k in d.keywords) for d in node.decorator_list)


def _setup_skips(body: list[ast.stmt], names: _Names) -> bool:
    """An autouse fixture or a setUp/setup_* of this scope that skips — it runs before
    every test there (#225 refute round 2)."""
    return any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
               and (n.name in _SETUPS or _is_autouse(n, names)) and names.skips(n) for n in body)


def _all_params_off(decorator: ast.expr, names: _Names) -> bool:
    """`parametrize(…, [pytest.param(…, marks=skip), …])` with every case switched off."""
    if not (isinstance(decorator, ast.Call) and names.path(decorator).endswith("mark.parametrize")
            and len(decorator.args) >= 2 and isinstance(decorator.args[1], (ast.List, ast.Tuple))):
        return False
    cases = decorator.args[1].elts
    return bool(cases) and all(
        isinstance(c, ast.Call) and names.path(c).endswith("param")
        and any(k.arg == "marks" and names.off(k.value) for k in c.keywords) for c in cases)


def _python_status(text: str, file: str, name: str, rules: dict) -> str | None:
    base = file.rsplit("/", 1)[-1]
    if not any(fnmatch.fnmatchcase(base, g) for g in rules["python_files"]):
        return (f"{file} is no test module pytest collects (python_files: "
                f"{', '.join(rules['python_files'])} — review_evidence in model-policy.json)")
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return f"{file} does not parse at head"
    names = _Names(tree)
    if _not_collected(tree.body):
        return f"{file} sets __test__ = False"
    if _marked_off(tree.body, names):
        return f"{file} carries a module pytestmark that skips"
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and names.skips(node):
            return f"{file} skips at module level"
    if _setup_skips(tree.body, names):
        return f"{file}: a module setup or autouse fixture skips"
    classes = {n.name: n for n in tree.body if isinstance(n, ast.ClassDef)}
    parts = name.split("::")
    scope: list[ast.stmt] = tree.body
    decorators: list[ast.expr] = []
    for cls in parts[:-1]:
        hit = classes.get(cls) if scope is tree.body else next(
            (n for n in reversed(scope) if isinstance(n, ast.ClassDef) and n.name == cls), None)
        if hit is None:
            return f"{file} has no class {cls} at head"
        if not _collected_class(hit, rules["python_classes"]) or _not_collected(hit.body):
            return f"{file}::{cls} is no class pytest collects (python_classes, no __init__, or a TestCase)"
        # the class and the bases this module defines lend their tests, marks and setups
        chain, seen = [hit], {cls}
        for c in chain:
            for b in c.bases:
                if isinstance(b, ast.Name) and b.id in classes and b.id not in seen:
                    seen.add(b.id)
                    chain.append(classes[b.id])
        for c in chain:
            if _marked_off(c.body, names):
                return f"{file}::{cls} carries a pytestmark that skips"
            if _setup_skips(c.body, names):
                return f"{file}::{cls}: its setup or an autouse fixture skips"
            decorators += c.decorator_list
        scope = [n for c in reversed(chain) for n in c.body]  # the subclass's own bindings last
    fn = parts[-1]
    if not fn.startswith("test"):
        return f"{file}::{name} is no test function (a helper proves no criterion)"
    # the last binding of the name is what pytest collects — a later `test_x = mark(test_x)` too
    bound = [n for n in scope if (isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == fn)
             or (isinstance(n, (ast.Assign, ast.AnnAssign)) and any(
                 isinstance(t, ast.Name) and t.id == fn
                 for t in (n.targets if isinstance(n, ast.Assign) else [n.target])))]
    if not bound:
        return f"{file} has no test {name} at head"
    last = bound[-1]
    if not isinstance(last, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return f"{file}::{name} is rebound after its definition — not the function the plan's test names"
    if any(names.off(d) for d in decorators + last.decorator_list):
        return f"{file}::{name} is marked to skip or to fail"
    if any(_all_params_off(d, names) for d in last.decorator_list):
        return f"{file}::{name}: every parametrized case is marked to skip"
    if names.skips(last):
        return f"{file}::{name} skips in its body"
    return None


# any other language: a file the project declares a test file (`review_evidence.test_files`),
# a declaration in the runner's own form naming the test whole, no skip marker on it, on its
# attribute lines, in its body or in a setup of the file
_NOT_CODE = (".md", ".txt", ".rst", ".json", ".yaml", ".yml", ".toml", ".csv", ".lock", ".ini", ".cfg")
_COMMENT = re.compile(r"^\s*(?://|#(?!\[)|--|/\*|\*)")
_DECLARES = re.compile(r"\b(?:it|test|describe|context|func|fn|fun|def|should)\b\s*[\w.]*\s*[(\w`'\"]|@Test\b|#\[test\]")
_ATTRIBUTE = re.compile(r"^\s*(?:@\w+|#\[\w+|\[\w+)")
_TEST_ATTR = re.compile(r"^\s*(?:@Test\b|@ParameterizedTest\b|#\[(?:tokio::)?test\b|\[(?:Test|Fact|Theory)\b)")
_SETUP = re.compile(r"\b(?:setUp\w*|beforeEach|beforeAll|TestMain|setup)\b\s*[(\w]")
_OTHER_SKIP = re.compile(r"\.(?:skip|todo)\b|\b(?:xit|xtest|xdescribe|xcontext)\b|\bt\.Skip(?:Now|f)?\b|"
                         r"\bXCTSkip(?:If|Unless)?\b|@Disabled\b|@Ignore\b|#\[ignore\]|\bthis\.skip\(")


def _declares_test(lines: list[str], i: int, name: str) -> bool:
    """Line `i` declares the test `name` the way its runner collects tests: a JS-style
    `it(`/`test(` with the name as its title, `func test…`/`func Test…` (XCTest, Go),
    `fun`/`fn`/`def test…`, or any function the line above marks `@Test`/`#[test]`."""
    ln = lines[i]
    if any(f"{q}{name}{q}" in ln for q in ('"', "'", "`")) and re.search(r"\b(?:it|test|specify|should)\b", ln):
        return True
    if not (name.isidentifier() and re.search(rf"(?<![\w$]){re.escape(name)}(?![\w$])", ln)):
        return False
    if re.search(rf"\b(?:func|fun|fn|def|void)\s+{re.escape(name)}\b", ln) and re.match(r"(?i)test", name):
        return True
    above = [lines[j] for j in range(i - 1, -1, -1) if lines[j].strip()][:3]
    return any(_TEST_ATTR.match(a) for a in above)


def _other_status(text: str, file: str, name: str, rules: dict) -> str | None:
    if file.lower().endswith(_NOT_CODE) or not any(fnmatch.fnmatchcase(file, g) for g in rules["test_files"]):
        return (f"{file} is no test file this project declares (test_files: review_evidence in "
                f"model-policy.json)")
    lines = text.splitlines()
    code = [i for i, ln in enumerate(lines) if ln.strip() and not _COMMENT.match(ln)]
    decls = [i for i in code if _DECLARES.search(lines[i]) or _SETUP.search(lines[i])]
    mine = [i for i in code if _declares_test(lines, i, name)]
    if not mine:
        return (f"{file} declares no test {name!r} at head (a runner's test form: `it(\"{name}\"`, "
                f"`func test…`, or an `@Test`/`#[test]` function)")

    def span(i: int) -> list[str]:
        # the attribute lines right above, the declaring line, the body up to the next declaration
        top = i
        while top - 1 >= 0 and _ATTRIBUTE.match(lines[top - 1]):
            top -= 1
        nxt = next((d for d in decls if d > i), len(lines))
        return [ln for j, ln in enumerate(lines[top:nxt], top) if j == i or not _COMMENT.match(ln)]

    # a setup of the file (setUp*, beforeEach/All, TestMain) that skips runs before each test
    if any(_OTHER_SKIP.search(ln) for d in decls if _SETUP.search(lines[d]) for ln in span(d)):
        return f"{file}: a setup (setUp/beforeEach/TestMain) skips at head"
    if all(any(_OTHER_SKIP.search(ln) for ln in span(i)) for i in mine):
        return f"{file}: {name!r} is marked or made to skip at head"
    return None


# a named test anywhere in a line — what is left is the line's own words (`unproven`)
_ITEM_ANY = re.compile(r"`[^`]*::[^`]*`|[\w./-]*::[\w:\[\].-]+")
_ITEM = re.compile(r"^`?(?P<file>[\w./-]+\.\w+)?::(?P<name>[^`]+?)`?(?:[ \t]+\(.*\))?$")
# a separator starts a new reference only where one follows (`<path.ext>::` or `::`): a
# test title may hold commas and semicolons of its own (downstream #2607)
_SPLIT = re.compile(r"[ \t]*[,;][ \t]*(?=`?(?:[\w./-]+\.\w+)?::)|[ \t]+(?:und|and)[ \t]+(?=`?[\w./-]*::)")


_PYTEST_PARAM = re.compile(r"\[.*\]$")


def attest_name(file: str, name: str) -> str:
    """The test name attest reads for a runner's case: a pytest parameter suffix
    (`test_x[a[b]]`) names the function `test_x`, so it is dropped whole; any other
    runner's name stands. One owner for the name `red_evidence` compares against the
    resolved test."""
    return _PYTEST_PARAM.sub("", name) if file.endswith(".py") else name


def claimed_tests(body: str) -> list[tuple[str, str]]:
    """(file, test) pairs an AC line names: `a.py::test_x`, `a.py::Cls::test_x`,
    `a.spec.ts::shows the banner`; an item `::test_y` takes the file before it.
    A parametrized id (`test_x[case]`) names its function (`attest_name`)."""
    out: list[tuple[str, str]] = []
    last = ""
    # a parametrized id may hold commas (`test_x[1, 2]`): split outside brackets only
    masked = re.sub(r"\[[^\]]*\]", lambda m: m.group(0).replace(",", "\0").replace(";", "\1"), body.strip())
    for item in (i.replace("\0", ",").replace("\1", ";") for i in _SPLIT.split(masked)):
        m = _ITEM.match(item.strip())
        if not m:
            continue
        file = m.group("file") or last
        if not file:
            continue
        last = file
        name = attest_name(file, m.group("name").strip())
        out.append((file, name))
    return out




def text_status(text: str | None, file: str, name: str, rules: dict) -> str | None:
    """None: the named test stands in `text` where the runner collects it and is not
    switched off; else why not. `None` text is a file that does not exist there."""
    if text is None:
        return f"{file} does not exist at head"
    if file.endswith(".py"):
        return _python_status(text, file, name, rules)
    return _other_status(text, file, name, rules)


def test_status(root: Path, head: str, file: str, name: str, rules: dict) -> str | None:
    """None: the named test stands at head where the runner collects it and is not
    switched off; else why not. Which files are tests is the project's declaration
    (`review_evidence`: `python_files`, `python_classes`, `test_files`) — never a
    guess from names (#225 refute: Xcode's `FooTests/…Tests.swift` read as no test).
    Python as pytest collects it; any other language by the declaring line and its
    body (a named residual: a runner's own rules beyond these are not modelled)."""
    return text_status(_show(root, head, file), file, name, rules)


def gather(root: Path, *, work: str, ids: set[str], tier: int, verdict: str, independence: str,
           base: str | None, head: str | None, plan_review: bool, model: str,
           reports: list[Path], blocks: list[tuple[int, str]] | None = None,
           journal_dir: Path | None = None, snapshot: Snapshot | None = None) -> Evidence:
    """`ids`: the work's ids (`attest.round_ids` of the plain work, no `-plan`); `blocks`:
    the work's blocking REVIEW lines the round counter counts (`attest.block_lines`) —
    None on a code pass is unknown, and refused where a row asks for it. `snapshot`: what
    this attestation fixes (`snapshot()`); the evidence is read at `E` — head plus today's
    shard and `--with` — and nowhere else, git objects only (I1, I12). Without one (a
    preview), at head, and no report is read. `reports` is kept for those callers; with a
    snapshot the reports are its files under the reports' home, chosen by path alone."""
    if not (_resolvable(root, head) and _resolvable(root, base)):
        return Evidence(work, tier, verdict, plan_review, model, head_ok=False)
    policy, problem = review_policy(root, base)
    if problem:
        return Evidence(work, tier, verdict, plan_review, model, policy_problem=problem)
    keys = {work_key(i) for i in ids}
    state, rel, plan_text, appended = _plan(root, keys, head, snapshot)
    # the plan's own lines, as the bundle's refute check reads them; records appended
    # after it count only when they ride this attestation (`--with` the plan)
    own = readable(plan_text) + ("\n" + readable(appended) if appended else "")
    plan_ids = _plan_work_ids(plan_stem(rel), _unfenced(plan_text), include_dedated=True) if rel else set()
    plan_read = readable(plan_text)
    spec = (_show(root, head, rel.rsplit("/", 1)[0] + "/spec.md") or "") \
        if record_kind(rel) == "spec-plan" else ""
    # the review reports among the round's records, chosen lexically on the snapshot's paths
    # (a plan riding `--with` is no report; no resolve, the sweep of design §9), their text
    # the checked bytes — E's blobs — so the evidence and the commit read one snapshot (R4)
    if snapshot is not None:
        report_files = [f for f in snapshot.files
                        if f.rel.startswith(REVIEW_REPORTS + "/") and f.data is not None]
        reports = [root / f.rel for f in report_files]
        report_texts = [readable(f.data.decode("utf-8", errors="replace")) for f in report_files]
    else:
        reports = [p for p in reports
                   if (_lexical_rel(root, p)[0] or "").startswith(REVIEW_REPORTS + "/")]
        report_texts = ["" for _p in reports]
    issues = {int(i) for i in plan_ids | set(ids) if i.isascii() and i.isdigit()}
    session, reported = _planned_model(root, issues) if plan_review else (None, False)
    source = "report" if session is not None else (UNMEASURED_REPORT if reported else "none")
    if plan_review and not reported and (m := PLAN_SESSION.search(plan_read)):
        session, source = m.group("model"), "plan-line"
    changed = _changed(root, base, head)
    claims = _claims(report_texts) if not plan_review else {}
    status: dict = {}
    for bodies in claims.values():
        for body in bodies:
            for key in claimed_tests(body):
                if key not in status:
                    status[key] = test_status(root, head, *key, policy)
    tokens = set(independence.split(","))
    skip_ids = {f"{i}-plan" for i in plan_ids} if plan_review else plan_ids
    # a code pass: the blocked code rounds the branch adds, and its journal records (ROOT-CAUSE,
    # skips) beside the plan's; a plan review asks no code round's records (facts None)
    rounds, journal, journal_keys = (None, "", frozenset()) if plan_review else _branch_records(
        root, head, blocks, journal_dir, plan_ids, skip_ids, snapshot)
    mine = [own, journal]
    # a journal skip lifts only the per-round duties; every other kind counts from the plan
    skips = _skips([own], skip_ids) | (_skips([journal], skip_ids) & JOURNAL_SKIPS)
    replanned = {int(m.group("round")) for m in REPLAN_LINE.finditer(own) if _binds(m.group("work"), plan_ids)}
    return Evidence(
        work=work, tier=tier, verdict=verdict, plan_review=plan_review, model=model,
        cross_model_from=policy["cross_model_from_tier"], ranks=dict(policy["ranks"]),
        families=tuple(policy["families"]),
        gate_code=None if changed is None else any(is_gate_path(p) for p in changed),
        cross_model="cross-model" in tokens, single_family="single-family" in tokens,
        skips=skips, refute=_refuted([own], plan_ids),
        report_refute=_refuted(report_texts, plan_ids),
        root_cause=_root_caused(mine, plan_ids),
        owner_decision=bool(OWNER_DECISION.search(_unfenced(own))),
        fix_streak=None if plan_review else _fix_streak(root, base, head),
        blocked_rounds=None if rounds is None else len(rounds),
        # the follow-up blocks: every blocked round but the lowest
        replan_open=tuple(r for r in (rounds or [])[1:] if r not in replanned),
        class_test_open=_class_tests_open(root, head, rounds, mine, plan_ids, policy) if rounds else (),
        records=tuple(required_records.table(policy)),
        plan_state=state, plan_rel=rel, plan_gate_code=plan_names_gate_code(plan_read),
        plan_acs=required_criteria(plan_read, readable(spec)),
        plan_struck=struck_criteria(plan_read, readable(spec)),
        plan_foreign=foreign_criteria(plan_read, readable(spec)),
        plan_session=session, plan_session_source=source,
        has_reports=bool(reports), claims=claims, test_status=status,
        plan_text=plan_text, plan_ids=frozenset(plan_ids), skip_ids=frozenset(skip_ids),
        journal_keys=journal_keys)


# --- the decision table ----------------------------------------------------------

def _skip(kind: str, ev: Evidence) -> str:
    return f"`skipped {kind} work={ev.work}: <reason>`"


def _plan_problem(ev: Evidence) -> str | None:
    plain = ev.work.removesuffix("-plan") if ev.plan_review else ev.work
    if ev.plan_state == "ok":
        return None
    if ev.plan_state == "unreadable":
        return HEAD_MSG
    if ev.plan_state == "missing":
        return (f"no plan of work {plain} at head — commit the plan, or attest a work "
                f"without one with --exception")
    if ev.plan_state == "ambiguous":
        return f"several plans of work {plain} at head ({ev.plan_rel}) — attest with --work <plan slug>"
    return (f"{ev.plan_rel} holds more than records appended after its last line, compared with "
            f"the attested head — commit the plan first, then rebuild the bundle and attest at the "
            f"new head (record lines — REFUTE, ROOT-CAUSE, REPLAN, DECISION, skips — may ride the "
            f"attestation only appended at the plan's end)")


def _cross_model(ev: Evidence, what: str) -> list[str]:
    if ev.cross_model or (ev.single_family and "cross-model" in ev.skips):
        return []
    if ev.single_family:
        return [f"{what} declares single-family without a reason — commit {_skip('cross-model', ev)}"]
    return [f"{what} without 'cross-model' — run the second family, or declare 'single-family' "
            f"and commit {_skip('cross-model', ev)}"]


def _decide_plan_review(ev: Evidence) -> list[str]:
    out: list[str] = []
    mine = model_class(ev.model, ev.ranks, ev.families)
    if "plan-review" in ev.skips:
        pass
    elif mine is None:
        out.append(f"plan-review pass by an unknown model {ev.model!r} — name the concrete model id "
                   f"(`--model claude-opus-…`; classes: review_evidence in model-policy.json), or "
                   f"commit {_skip('plan-review', ev)}")
    elif mine[1] is not None and ev.ranks and mine[1] == min(ev.ranks.values()):
        # the lowest class reviews no plan, not even one of its own class (#228)
        out.append(f"plan-review pass by {ev.model}, the lowest class — a plan review runs on a "
                   f"larger model, or commit {_skip('plan-review', ev)}")
    elif mine[1] is not None and mine[1] == max(ev.ranks.values()):
        pass  # the top class: no plan session ranks above it (refute v2.75 r2)
    elif mine[1] is not None:  # another family is never smaller — nothing to compare
        theirs = model_class(ev.plan_session, ev.ranks, ev.families) if ev.plan_session else None
        if ev.plan_session is None and ev.plan_session_source == UNMEASURED_REPORT:
            out.append("the newest `planned` report of the work measured no model — the plan "
                       "session's class cannot be compared, and the plan's own `plan-session model:` "
                       f"line does not stand in for a report; commit {_skip('plan-review', ev)}")
        elif ev.plan_session is None:
            out.append("no `planned` report with a measured model and no `plan-session model: <id>` "
                       "line in the plan — the plan session's class cannot be compared; add the "
                       f"line, or commit {_skip('plan-review', ev)}")
        elif theirs is None:
            out.append(f"plan session model {ev.plan_session!r} ({ev.plan_session_source}) is unknown "
                       f"— name its concrete id, or commit {_skip('plan-review', ev)}")
        elif theirs[1] is not None and mine[1] < theirs[1]:
            out.append(f"plan-review pass by {ev.model}, a smaller class than the plan session's "
                       f"{ev.plan_session} ({ev.plan_session_source}) — review with a model of at "
                       f"least its class, or commit {_skip('plan-review', ev)}")
    if ev.plan_gate_code:
        out += _cross_model(ev, "a plan naming gate code, reviewed")
    return out


# what each owed kind asks for, by the record that satisfies it
_RECORD_ASK = {
    "refute": ("work {w} has no REFUTE line at head — refute it (`docs/process/refute.md`) and "
               "commit `REFUTE work={w} round=<r>: <finding or survives: …>`"),
    "root-cause": ("work {w} has no ROOT-CAUSE line (its plan at head, or new in its journal) — "
                   "find the cause the fix commits share "
                   "(mandatory rule 6) and commit `ROOT-CAUSE work={w} round=<r>: <the cause>`"),
    "owner-decision": ("work {w} has no owner's word in its plan — the owner decides, recorded as "
                       "`DECISION <date> owner: <what and why>`"),
    "replan": ("work {w} blocked round(s) {replan} without a REPLAN line in its plan — before each "
               "follow-up block's fix, record mandatory rule 4's call there: `REPLAN work={w} "
               "round=<r>: increment|rebuild — <why>` (a rebuild takes a new plan review)"),
    "class-test": ("work {w} has no class test for blocked round(s) {class_test} — per round "
                   "`ROOT-CAUSE work={w} round=<r>: <cause> — sites: <sibling sites> — <path>::<test>` "
                   "(`red_evidence.py --cause … --sites …`) with a test that stands at head, or "
                   "`… — sites: none — <reason>` for a round without a code defect"),
}
# why a fact is unknown, by the fact
_UNKNOWN = {"gate_code": ("git could not list the reviewed diff — whether it touches gate code is unknown; "
                          "rebuild the bundle here"),
            "fix_streak": "git could not read the fix commits of base..head; rebuild the bundle here",
            "blocked_rounds": ("the fork point of the head cannot be read (no integration ref, or an "
                               "ambiguous fork) — the blocked code rounds this branch adds are unknown; "
                               "fetch the integration branch, or commit `skipped replan|class-test "
                               "work=<id>: <reason>` in the plan (a journal line is read against the "
                               "fork point, which is the unknown)")}


def _owed_records(ev: Evidence) -> list[str]:
    """The records the table says this work owes and does not carry (#282). A fact git
    cannot tell (the diff, the fix streak, the fork point) is no exemption: every row it
    leaves undecided is refused as unknown — any fact, not a listed few (v2.77: a row on a
    new fact fell away in silence)."""
    facts = {"tier_from": ev.tier, "gate_code": ev.gate_code, "fix_streak": ev.fix_streak,
             "blocked_rounds": ev.blocked_rounds,
             "waived": False}  # a waived plan has no pass to attest; the gate asks its owner
    # a REFUTE in the review report counts for gate code below Tier 3 on a cross-model pass
    # (the refute ran inside that review; refute.md)
    refuted = ev.refute or (ev.report_refute and ev.cross_model and ev.tier < 3)
    # per round: present only when every blocked round has its record, and the rounds are known
    rounds_known = ev.blocked_rounds is not None
    present = {k for k, have in (("refute", refuted), ("root-cause", ev.root_cause),
                                 ("replan", rounds_known and not ev.replan_open),
                                 ("class-test", rounds_known and not ev.class_test_open),
                                 ("owner-decision", ev.owner_decision)) if have}
    owed, undecided = required_records.owed(list(ev.records), facts, present, set(ev.skips))
    out: list[str] = []
    for u in undecided:
        why = [_UNKNOWN.get(k, f"the fact {k} is unknown") for k, v in facts.items()
               if v is None and f"{k}=" in u] or [f"{u} — a fact it needs is unknown"]
        out += [w for w in why if w not in out]
    for o in owed:
        ask = _RECORD_ASK.get(o.kind, "work {w} has no `{kind}` record at head").format(
            w=ev.work, kind=o.kind, replan=", ".join(map(str, ev.replan_open)),
            class_test=", ".join(ev.class_test_open))
        skip = f", or commit {_skip(o.kind, ev)}" if o.skippable else ""
        out.append(f"{ask}{skip} (owed: {o.why})")
    return out


def _decide_code(ev: Evidence) -> list[str]:
    out: list[str] = list(ev.evidence_problems)
    if ev.tier >= ev.cross_model_from:
        out += _cross_model(ev, f"a pass at tier {ev.tier}")
    out += _owed_records(ev)
    if "ac-trace" in ev.skips:
        return out
    if not ev.has_reports:
        out.append("a pass without its review report — `--with .process-work/reviews/<report>.md` "
                   "with one line `AC-<id>: <path>::<test>` per acceptance criterion")
        return out
    if ev.plan_state != "ok":
        return out
    for n in sorted(ev.plan_struck):
        bodies = ev.claims.get(n, [])
        if not any(_STRUCK_CONFIRMED.match(b.strip()) for b in bodies):
            out.append(f"AC-{n} is struck in {ev.plan_rel} or its spec — the report confirms the "
                       f"strike with a line `AC-{n}: struck`")
        # struck and proven at once is one claim too many: a criterion misread as
        # struck must not ride on a test nobody checks (refute)
        if any(_NAMES_A_TEST.search(b) for b in bodies):
            out.append(f"AC-{n} is struck, yet its report line names a test — strike it "
                       f"(`AC-{n}: struck`) or prove it (unstrike it in the plan)")
    if not ev.plan_acs and not ev.plan_struck:
        out.append(f"{ev.plan_rel} names no acceptance criterion (`AC-<id>`) — nothing to trace a "
                   f"test to; name them in the plan, or commit {_skip('ac-trace', ev)}")
    for n in sorted(ev.plan_acs):
        bodies = ev.claims.get(n, [])
        cited = f"; if the plan only cites another issue's AC-{n}, write it `#<issue>/AC-{n}` (#287)"
        if not bodies:
            out.append(f"AC-{n} has no line in the report — name the test that goes red when it "
                       f"breaks (`AC-{n}: <path>::<test>`) or `AC-{n}: unproven`{cited}")
        # a heading or a prose line of the criterion is no claim; one naming a test is
        unproven = [b for b in bodies if re.search(r"\bunproven\b", _ITEM_ANY.sub(" ", b), re.IGNORECASE)]
        if unproven:
            out.append(f"AC-{n} is unproven — no test goes red when it breaks{cited}")
            continue
        named = [key for b in bodies for key in claimed_tests(b)]
        if bodies and not named:
            out.append(f"AC-{n}: `{bodies[0]}` names no `<path>::<test>`{cited}")
        for key in named:
            why = ev.test_status.get(key, "not checked at head")
            if why:
                out.append(f"AC-{n}: {why}")
    return out


def decide(ev: Evidence) -> list[str]:
    """The refusals for a verdict (empty: the evidence is there). Pure: `ev` decides."""
    if ev.verdict != "pass" or ev.tier < 2:
        return []
    if not ev.head_ok:
        return [HEAD_MSG]
    if ev.policy_problem:
        return [ev.policy_problem]
    plan = _plan_problem(ev)
    rest = _decide_plan_review(ev) if ev.plan_review else _decide_code(ev)
    return ([plan] if plan else []) + rest


def evidence_problems(root: Path, *, work: str, ids: set[str], tier: int, verdict: str,
                      independence: str, base: str | None, head: str | None, plan_review: bool,
                      model: str, reports: list[Path], blocks: list[tuple[int, str]] | None = None,
                      journal_dir: Path | None = None, snapshot: Snapshot | None = None) -> list[str]:
    """attest.py's one entry: gather at E (objects only), then the refusal readers (I5) —
    a plan the worktree or index holds more of (`_plan_differs`), a journal line only in
    the worktree (`_foreign_shard_problems`) — then decide; only for a Tier 2+ pass."""
    if verdict != "pass" or tier < 2:
        return []
    ev = gather(root, work=work, ids=ids, tier=tier, verdict=verdict, independence=independence,
                base=base, head=head, plan_review=plan_review, model=model, reports=reports,
                blocks=blocks, journal_dir=journal_dir, snapshot=snapshot)
    if ev.plan_state == "ok" and ev.plan_rel and _plan_differs(root, ev.plan_rel, ev.plan_text):
        ev = replace(ev, plan_state="differs")
    if ev.head_ok and not ev.policy_problem and not plan_review and ev.blocked_rounds is not None:
        ev = replace(ev, evidence_problems=tuple(_foreign_shard_problems(
            root, head, journal_dir, ev.plan_ids, ev.skip_ids, ev.journal_keys)))
    for n in sorted(ev.plan_foreign):
        # never dropped in silence (#287): the reader sees which id was left out and why
        print(f"attest: note — AC-{n} not required: {ev.plan_rel} cites it as another issue's "
              f"(`#<issue>/AC-{n}`)", file=sys.stderr)
    return decide(ev)
