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
    SPEC_PLAN,
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
    "ranks": {"claude-haiku": 0, "claude-sonnet": 1, "claude-opus": 2, "claude-fable": 3},
    "families": ["gpt-"],
}
# an acceptance criterion's id: `AC-1`, `AC-2.1`, `AC-B1`, `AC1` — a digit in it, so
# prose (`AC-Zeile`, `AC-<id>`) names none; a sentence's final dot is no part of it
_AC = r"AC-?(?P<id>[A-Za-z]{0,3}\d(?:[\w.]*\w)?)"
AC_ID = re.compile(r"\b" + _AC + r"(?![\w-])")
# a report's line for one: `AC-1: <path>::<test>`, listed, boxed, bold or as a heading
AC_LINE = re.compile(
    r"^[ \t]*(?:[-*+][ \t]+)?(?:\[[ xX]\][ \t]+)?(?:#{1,6}[ \t]+)?(?:\*\*)?" + _AC
    + r"(?:\*\*)?[ \t]*:(?:\*\*)?[ \t]*(?P<body>.*?)[ \t]*$",
    re.MULTILINE)
PLAN_SESSION = re.compile(
    r"^[ \t]*(?:[-*+][ \t]+)?[*_]*plan-session[ \t]+model[*_]*:[*_]*[ \t]*`?(?P<model>[^\s`*]+)`?",
    re.MULTILINE | re.IGNORECASE)
_SKIP_WORD = re.compile(r"\b(?:skip|skipif|xfail|importorskip)\b")
_OTHER_SKIP = re.compile(r"\b(?:skip|xit|xtest|xdescribe|todo)\b")
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
    tier, ranks, fams = got.get("cross_model_from_tier"), got.get("ranks"), got.get("families")
    if isinstance(tier, bool) or not isinstance(tier, int) or not 0 <= tier <= 4:
        return {}, f"{POLICY_KEY}.cross_model_from_tier must be an integer 0-4 (4: never), got {tier!r}"
    if not (isinstance(ranks, dict) and all(isinstance(k, str) and k and isinstance(v, int)
                                            and not isinstance(v, bool) for k, v in ranks.items())):
        return {}, f"{POLICY_KEY}.ranks must map model-id prefixes to integer ranks"
    if not (isinstance(fams, list) and all(isinstance(f, str) and f for f in fams)):
        return {}, f"{POLICY_KEY}.families must be a list of model-id prefixes"
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
    for now in (_worktree_text(root, rel), _index_text(root, rel)):
        if now is None or now == text:
            continue
        if not records_only(text, now):
            return "differs", rel, text, ""
        added += now[len(text):] if now.startswith(text) else "\n".join(
            ln for ln in now.splitlines() if ln not in set(text.splitlines()))
    return "ok", rel, text, added


def _worktree_text(root: Path, rel: str) -> str | None:
    try:
        return (root / rel).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""  # deleted or unreadable: not the plan at head


def _index_text(root: Path, rel: str) -> str | None:
    r = _git(root, "show", f":{rel}")
    return r.stdout if r.returncode == 0 else ""


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


_OFF_CALLS = ("skip", "xfail", "importorskip")


def _call_name(call: ast.Call) -> str:
    f = call.func
    return f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else ""


def _is_mark(call: ast.Call) -> bool:
    f = call.func
    return isinstance(f, ast.Attribute) and (
        (isinstance(f.value, ast.Attribute) and f.value.attr == "mark")
        or (isinstance(f.value, ast.Name) and f.value.id == "mark"))


def _skip_bound(tree: ast.Module) -> set[str]:
    """Names the module binds to a skip/xfail expression — an alias decorator
    (`off = pytest.mark.skip`, `@off`) is a skip too."""
    out = set()
    for node in tree.body:
        value = node.value if isinstance(node, (ast.Assign, ast.AnnAssign)) else None
        targets = node.targets if isinstance(node, ast.Assign) else [getattr(node, "target", None)]
        if value is not None and _SKIP_WORD.search(ast.unparse(value)):
            out |= {t.id for t in targets if isinstance(t, ast.Name)}
        if isinstance(node, ast.ImportFrom):
            out |= {a.asname or a.name for a in node.names if _SKIP_WORD.search(a.name)}
    return out


def _names(expr: ast.expr) -> set[str]:
    return {n.id for n in ast.walk(expr) if isinstance(n, ast.Name)}


def _marks_off(expr: ast.expr | None, aliases: set[str]) -> bool:
    return expr is not None and bool(_SKIP_WORD.search(ast.unparse(expr)) or _names(expr) & aliases)


def _pytestmark_off(body: list[ast.stmt], aliases: set[str]) -> bool:
    for node in body:
        targets = (node.targets if isinstance(node, ast.Assign)
                   else [node.target] if isinstance(node, ast.AnnAssign) else [])
        if any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in targets) \
                and _marks_off(node.value, aliases):
            return True
    return False


def _python_status(text: str, file: str, name: str) -> str | None:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return f"{file} does not parse at head"
    aliases = _skip_bound(tree)
    if _pytestmark_off(tree.body, aliases):
        return f"{file} carries a module pytestmark with skip/xfail"
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        # `pytest.skip(..., allow_module_level=True)`, `importorskip` — a mark built here
        # (`pytest.mark.skip(...)`) skips nothing by itself; its alias is caught where used
        if any(isinstance(c, ast.Call) and _call_name(c) in ("skip", "importorskip") and not _is_mark(c)
               for c in ast.walk(node)):
            return f"{file} skips at module level"
    parts = name.split("::")
    scope: list[ast.stmt] = tree.body
    decorators: list[ast.expr] = []
    for cls in parts[:-1]:
        hits = [n for n in scope if isinstance(n, ast.ClassDef) and n.name == cls]
        if not hits:
            return f"{file} has no class {cls} at head"
        if _pytestmark_off(hits[-1].body, aliases):
            return f"{file}::{cls} carries a pytestmark with skip/xfail"
        decorators += hits[-1].decorator_list
        scope = hits[-1].body
    fn = parts[-1]
    if not fn.startswith("test"):
        return f"{file}::{name} is no test function (a helper proves no criterion)"
    # Python binds the name to its last definition — the one pytest collects
    defs = [n for n in scope if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == fn]
    if not defs:
        return f"{file} has no test {name} at head"
    if any(_marks_off(d, aliases) for d in decorators + defs[-1].decorator_list):
        return f"{file}::{name} is marked skip/xfail"
    for call in ast.walk(defs[-1]):
        if isinstance(call, ast.Call) and _call_name(call) in _OFF_CALLS:
            return f"{file}::{name} calls {_call_name(call)} in its body"
    return None


# a named test anywhere in a line — what is left is the line's own words (`unproven`)
_ITEM_ANY = re.compile(r"`[^`]*::[^`]*`|[\w./-]*::[\w:\[\].-]+")
_ITEM = re.compile(r"^`?(?P<file>[\w./-]+\.\w+)?::(?P<name>[^`]+?)`?(?:[ \t]+\(.*\))?$")
_SPLIT = re.compile(r"[ \t]*[,;][ \t]*|[ \t]+(?:und|and)[ \t]+(?=`?[\w./-]*::)")


def claimed_tests(body: str) -> list[tuple[str, str]]:
    """(file, test) pairs an AC line names: `a.py::test_x`, `a.py::Cls::test_x`,
    `a.spec.ts::shows the banner`; an item `::test_y` takes the file before it.
    A parametrized id (`test_x[case]`) names its function."""
    out: list[tuple[str, str]] = []
    last = ""
    for item in _SPLIT.split(body.strip()):
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




def test_status(root: Path, head: str, file: str, name: str) -> str | None:
    """None: the named test stands at head and is not switched off; else why not.
    Python by its syntax tree; any other language by the name and its line."""
    text = _show(root, head, file)
    if text is None:
        return f"{file} does not exist at head"
    if file.endswith(".py"):
        return _python_status(text, file, name)
    lines = [ln for ln in text.splitlines() if name in ln]
    if not lines:
        return f"{file} does not name {name!r} at head"
    if all(_OTHER_SKIP.search(ln) for ln in lines):
        return f"{file}: {name!r} is marked skip/todo at head"
    return None


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
                    status[key] = test_status(root, head, *key)
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
        plan_acs=frozenset(ac_key(m) for m in AC_ID.finditer(plan_read + "\n" + readable(spec)))
        - held_open(plan_read),
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
    if not ev.plan_acs:
        out.append(f"{ev.plan_rel} names no acceptance criterion (`AC-<id>`) — nothing to trace a "
                   f"test to; name them in the plan, or commit {_skip('ac-trace', ev)}")
    for n in sorted(ev.plan_acs):
        bodies = ev.claims.get(n, [])
        if not bodies:
            out.append(f"AC-{n} has no line in the report — name the test that goes red when it "
                       f"breaks (`AC-{n}: <path>::<test>`) or `AC-{n}: unproven`")
        for body in bodies:
            named = claimed_tests(body)
            rest = _ITEM_ANY.sub(" ", body)
            if re.search(r"\bunproven\b", rest, re.IGNORECASE):
                out.append(f"AC-{n} is unproven — no test goes red when it breaks")
                continue
            if not named:
                out.append(f"AC-{n}: `{body}` names no `<path>::<test>`")
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
