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
  plan rides `--with`; anything else must be at head.
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
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from check_review import (
    PLAN_KINDS,
    REFUTE_LINE,
    REVIEW_REPORTS,
    SKIP_LINE,
    _plan_work_ids,
    _unfenced,
    is_gate_path,
    plan_stem,
    readable,
    record_kind,
    record_texts,
    records_only,
    work_key,
)
from process_git import git_environment

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
    "families": ["gpt-"],
    # pytest's own defaults; a project with other `python_files`/`python_classes` names them
    "python_files": ["test_*.py", "*_test.py"],
    "python_classes": ["Test"],
    # test files of other languages (fnmatch on the repository path, `*` spans folders)
    "test_files": ["*tests/*", "*Tests/*", "*__tests__/*", "spec/*", "*/spec/*", "*Test.*", "*Tests.*",
                   "*Spec.*", "*.test.*", "*.spec.*", "*_test.*", "*_spec.*", "*/test_*", "test_*"],
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
    report_refute: bool = False  # a REFUTE line of the work in this attest's review report
    plan_state: str = "ok"  # ok | missing | ambiguous | differs | unreadable
    plan_rel: str = ""
    plan_gate_code: bool = False
    plan_acs: frozenset = frozenset()
    plan_struck: frozenset = frozenset()  # struck with a reason: the report confirms each
    plan_session: str | None = None  # None: no source names it
    plan_session_source: str = "none"  # report | plan-line | none
    has_reports: bool = False
    claims: dict = field(default_factory=dict)  # AC id -> [line bodies]
    test_status: dict = field(default_factory=dict)  # (file, name) -> None (ok) | why not


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

def review_policy(root: Path, ref: str) -> tuple[dict, str]:
    """(`review_evidence` over the defaults, problem) as the policy reads at `ref` — the
    reviewed base. The overlay is dispatch's (`_merged`), one rule for how the local
    file lays over."""
    from dispatch import _merged  # late: dispatch is large
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
        data = _merged(data, layer)
    rules = data.get(POLICY_KEY, {})
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


def _skips(texts: list[str], ids: set) -> frozenset:
    return frozenset("cross-model" if m.group("kind") == "codex-review" else m.group("kind")
                     for t in texts for m in SKIP_LINE.finditer(t) if _binds(m.group("work"), ids))


def _refuted(texts: list[str], ids: set) -> bool:
    return any(_binds(m.group("work"), ids) for t in texts for m in REFUTE_LINE.finditer(t))


def _plan(root: Path, ids: set, head: str) -> tuple[str, str, str, str]:
    """(state, path, text at head, records appended since) of the work's plan —
    active or Spec Kit, else archived (a late lens attests after `--archive`).
    `differs`: the worktree or index holds more than records appended after the
    plan's last line (E1, the gate's `records_only`)."""
    records = record_texts(root, PLAN_KINDS + ("plan-archive",), ref=head)
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
    added = ""
    # a plan the first lens of this round already archived (`--archive`) is read where it went
    moved = _archived_as(root, rel)
    for now in (_worktree_text(root, rel) or _worktree_text(root, moved),
                _index_text(root, rel) or _index_text(root, moved)):
        if now == text:
            continue
        if not records_only(text, now):
            return "differs", rel, text, ""
        added += now[len(text):] if now.startswith(text) else "\n".join(
            ln for ln in now.splitlines() if ln not in set(text.splitlines()))
    return "ok", rel, text, added


def _archived_as(root: Path, rel: str) -> str:
    """Where `attest.py --archive` moves this plan — attest owns the target."""
    from attest import _archive_target  # late: attest imports this module
    target = _archive_target(root, root / rel)
    return target.relative_to(root).as_posix() if target.is_relative_to(root) else ""


def _worktree_text(root: Path, rel: str) -> str:
    """The file in the worktree; "" when it is not there (deleted or unreadable)."""
    try:
        return (root / rel).read_text(encoding="utf-8", errors="replace") if rel else ""
    except OSError:
        return ""


def _index_text(root: Path, rel: str) -> str:
    r = _git(root, "show", f":{rel}") if rel else None
    return r.stdout if r is not None and r.returncode == 0 else ""


def _planned_model(root: Path, issues: set[int]) -> str | None:
    """The plan session's model from the newest `planned` report of the work's
    issues (report.py); None when there is none or it measured none."""
    if not issues:
        return None
    from report import UNMEASURED, read_reports  # late: report imports dispatch lazily
    rows = [r for r in read_reports(root) if r.get("issue") in issues and r.get("state") == "planned"]
    if not rows:
        return None
    newest = max(rows, key=lambda r: r.get("epoch") if isinstance(r.get("epoch"), int) else 0)
    model = str(newest.get("model") or "")
    return None if model in ("", UNMEASURED) else model


# a criterion struck on purpose, with its reason (#234): `AC-3: struck — <reason>`
# or `dropped`; listed, boxed or bold like a criterion line; a bare strike-through
# (`~~AC-3~~`) names no reason and strikes nothing. The mark is lower case and a
# hyphen separates only with spaces around it: `AC-3: Dropped: When the socket
# drops …` and `AC-3: Dropped-connection retry` are criteria (plan review, refute)
_STRUCK_MARK = r"(?:struck|dropped)(?:[ \t]*[—–:]|[ \t]+--?[ \t])"
STRUCK_LINE = re.compile(
    r"^[ \t]*(?:[-*+][ \t]+)?(?:\[[ xX]\][ \t]+)?(?:\*\*)?" + _AC
    + r"(?:\*\*)?[ \t]*:(?:\*\*)?[ \t]*" + _STRUCK_MARK + r"[ \t]*"
    r"(?!<|(?i:todo)\b|…|\.\.\.)\S*\w",
    re.MULTILINE)
# a test a line names: a file with its extension, then `::` (prose like `std::vector` is none)
_NAMES_A_TEST = re.compile(r"[\w./-]+\.\w+::\w")
# the report's confirmation of a strike: the same mark, the reason optional
_STRUCK_CONFIRMED = re.compile(r"(?:struck|dropped)(?:[ \t]*[—–:]|[ \t]+--?[ \t]|[ \t]*$)")


def struck(text: str) -> set[str]:
    """The criteria a text strikes, each with a reason."""
    return {ac_key(m) for m in STRUCK_LINE.finditer(text)}


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


def _criteria(plan: str, spec: str) -> tuple[frozenset[str], frozenset[str]]:
    plan, spec = _EXAMPLE_SPAN.sub(" ", plan), _EXAMPLE_SPAN.sub(" ", spec)
    in_spec = {ac_key(m) for m in AC_ID.finditer(spec)}
    named = {ac_key(m) for m in AC_ID.finditer(plan)} | in_spec
    open_ = held_open(plan)
    gone = (struck(spec) | (struck(plan) - in_spec)) - open_
    return frozenset(named - open_ - gone), frozenset(gone & named)


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


def claimed_tests(body: str) -> list[tuple[str, str]]:
    """(file, test) pairs an AC line names: `a.py::test_x`, `a.py::Cls::test_x`,
    `a.spec.ts::shows the banner`; an item `::test_y` takes the file before it.
    A parametrized id (`test_x[case]`) names its function."""
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
        name = m.group("name").strip()
        if file.endswith(".py"):
            name = re.sub(r"\[.*\]$", "", name)
        out.append((file, name))
    return out




def test_status(root: Path, head: str, file: str, name: str, rules: dict) -> str | None:
    """None: the named test stands at head where the runner collects it and is not
    switched off; else why not. Which files are tests is the project's declaration
    (`review_evidence`: `python_files`, `python_classes`, `test_files`) — never a
    guess from names (#225 refute: Xcode's `FooTests/…Tests.swift` read as no test).
    Python as pytest collects it; any other language by the declaring line and its
    body (a named residual: a runner's own rules beyond these are not modelled)."""
    text = _show(root, head, file)
    if text is None:
        return f"{file} does not exist at head"
    if file.endswith(".py"):
        return _python_status(text, file, name, rules)
    return _other_status(text, file, name, rules)


def gather(root: Path, *, work: str, ids: set[str], tier: int, verdict: str, independence: str,
           base: str | None, head: str | None, plan_review: bool, model: str,
           reports: list[Path]) -> Evidence:
    """`ids`: the work's ids (`attest.round_ids` of the plain work, no `-plan`)."""
    if not (_resolvable(root, head) and _resolvable(root, base)):
        return Evidence(work, tier, verdict, plan_review, model, head_ok=False)
    policy, problem = review_policy(root, base)
    if problem:
        return Evidence(work, tier, verdict, plan_review, model, policy_problem=problem)
    keys = {work_key(i) for i in ids}
    state, rel, plan_text, appended = _plan(root, keys, head)
    # the plan's own lines, as the bundle's refute check reads them; records appended
    # after it count only when they ride this attestation (`--with` the plan)
    riding = {p.resolve() for p in reports}
    own = readable(plan_text) + ("\n" + readable(appended) if rel and (root / rel).resolve() in riding else "")
    plan_ids = _plan_work_ids(plan_stem(rel), _unfenced(plan_text), include_dedated=True) if rel else set()
    plan_read = readable(plan_text)
    spec = (_show(root, head, rel.rsplit("/", 1)[0] + "/spec.md") or "") \
        if record_kind(rel) == "spec-plan" else ""
    # the review reports among the round's records: a plan riding `--with` is no report
    reports = [p for p in reports if p.resolve().is_relative_to((root / REVIEW_REPORTS).resolve())]
    report_texts = [readable(p.read_text(encoding="utf-8", errors="replace")) for p in reports]
    issues = {int(i) for i in plan_ids | set(ids) if i.isascii() and i.isdigit()}
    session = _planned_model(root, issues) if plan_review else None
    source = "report" if session is not None else "none"
    if plan_review and session is None and (m := PLAN_SESSION.search(plan_read)):
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
    return Evidence(
        work=work, tier=tier, verdict=verdict, plan_review=plan_review, model=model,
        cross_model_from=policy["cross_model_from_tier"], ranks=dict(policy["ranks"]),
        families=tuple(policy["families"]),
        gate_code=None if changed is None else any(is_gate_path(p) for p in changed),
        cross_model="cross-model" in tokens, single_family="single-family" in tokens,
        skips=_skips([own], skip_ids), refute=_refuted([own], plan_ids),
        report_refute=_refuted(report_texts, plan_ids),
        plan_state=state, plan_rel=rel, plan_gate_code=plan_names_gate_code(plan_read),
        plan_acs=required_criteria(plan_read, readable(spec)),
        plan_struck=struck_criteria(plan_read, readable(spec)),
        plan_session=session, plan_session_source=source,
        has_reports=bool(reports), claims=claims, test_status=status)


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
            f"new head (record lines — REFUTE, ROOT-CAUSE, DECISION, skips — may ride the "
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
    elif mine[1] is not None:  # another family is never smaller — nothing to compare
        theirs = model_class(ev.plan_session, ev.ranks, ev.families) if ev.plan_session else None
        if ev.plan_session is None:
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


def _decide_code(ev: Evidence) -> list[str]:
    out: list[str] = []
    if ev.tier >= ev.cross_model_from:
        out += _cross_model(ev, f"a pass at tier {ev.tier}")
    if ev.gate_code is None:
        out.append("git could not list the reviewed diff — whether it touches gate code is "
                   "unknown; rebuild the bundle here")
    elif ev.gate_code and not (ev.refute or "refute" in ev.skips
                               or (ev.report_refute and ev.cross_model and ev.tier < 3)):
        out.append(f"the diff changes gate code and work {ev.work} has no REFUTE line at head — "
                   f"refute it (`docs/process/refute.md`) and commit `REFUTE work={ev.work} "
                   f"round=<r>: <finding or survives: …>`, or commit {_skip('refute', ev)}")
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
        if not bodies:
            out.append(f"AC-{n} has no line in the report — name the test that goes red when it "
                       f"breaks (`AC-{n}: <path>::<test>`) or `AC-{n}: unproven`")
        # a heading or a prose line of the criterion is no claim; one naming a test is
        unproven = [b for b in bodies if re.search(r"\bunproven\b", _ITEM_ANY.sub(" ", b), re.IGNORECASE)]
        if unproven:
            out.append(f"AC-{n} is unproven — no test goes red when it breaks")
            continue
        named = [key for b in bodies for key in claimed_tests(b)]
        if bodies and not named:
            out.append(f"AC-{n}: `{bodies[0]}` names no `<path>::<test>`")
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
                      model: str, reports: list[Path]) -> list[str]:
    """attest.py's one entry: gather at head, then decide — only for a Tier 2+ pass."""
    if verdict != "pass" or tier < 2:
        return []
    return decide(gather(root, work=work, ids=ids, tier=tier, verdict=verdict,
                         independence=independence, base=base, head=head, plan_review=plan_review,
                         model=model, reports=reports))
