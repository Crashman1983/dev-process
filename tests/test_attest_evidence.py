"""#225: a Tier 2+ pass shows its evidence before attest.py writes it —
cross-model or a reasoned single-family, a refute for gate code, one test per
acceptance criterion, a plan reviewer not below the plan session's class, and
the plan's own lines committed before the attested head."""
import importlib
import json
import subprocess
import sys

import pytest

sys.dont_write_bytecode = True


@pytest.fixture
def ev_mod(render, tmp_path):
    out = render(tmp_path / "t", {"project_name": "d"})
    sys.path.insert(0, str(out / "scripts/process"))
    try:
        for name in ("attest_evidence", "check_review", "dispatch", "report", "process_git"):
            sys.modules.pop(name, None)
        yield importlib.import_module("attest_evidence"), out
    finally:
        sys.path.remove(str(out / "scripts/process"))
        for name in ("attest_evidence", "check_review", "dispatch", "report", "process_git"):
            sys.modules.pop(name, None)


RANKS = {"claude-haiku": 0, "claude-sonnet": 1, "claude-opus": 2, "claude-fable": 3}
OK_CODE = dict(work="7", tier=2, verdict="pass", plan_review=False, model="claude-opus-5",
               cross_model_from=3, ranks=RANKS, families=("gpt-",), plan_acs=frozenset({"1"}),
               has_reports=True, claims={"1": ["tests/t.py::test_a"]},
               test_status={("tests/t.py", "test_a"): None}, plan_rel="p.md")
OK_PLAN = dict(work="7-plan", tier=2, verdict="pass", plan_review=True, model="claude-opus-5",
               cross_model_from=3, ranks=RANKS, families=("gpt-",), plan_session="claude-opus-5",
               plan_session_source="plan-line", plan_rel="p.md")

# (name, base, changes, expected substring — None: no refusal)
TABLE = [
    ("block is free", OK_CODE, {"verdict": "block", "has_reports": False}, None),
    ("tier 1 is free", OK_CODE, {"tier": 1, "has_reports": False}, None),
    ("complete code pass", OK_CODE, {}, None),
    ("head unreadable", OK_CODE, {"head_ok": False}, "reviewed range"),
    ("policy unreadable", OK_CODE, {"policy_problem": "bad policy"}, "bad policy"),
    ("E1 plan differs", OK_CODE, {"plan_state": "differs"}, "holds more than records appended"),
    ("plan missing", OK_CODE, {"plan_state": "missing"}, "no plan of work 7"),
    ("plans ambiguous", OK_CODE, {"plan_state": "ambiguous"}, "several plans"),
    ("B1 tier 3 without cross-model", OK_CODE, {"tier": 3}, "without 'cross-model'"),
    ("B1 single-family without reason", OK_CODE, {"tier": 3, "single_family": True}, "without a reason"),
    ("B1 single-family with reason", OK_CODE,
     {"tier": 3, "single_family": True, "skips": frozenset({"cross-model"})}, None),
    ("B1 a skip line without the token", OK_CODE, {"tier": 3, "skips": frozenset({"cross-model"})},
     "without 'cross-model'"),
    ("B1 cross-model", OK_CODE, {"tier": 3, "cross_model": True}, None),
    ("B1 floor 2 reaches tier 2", OK_CODE, {"cross_model_from": 2}, "without 'cross-model'"),
    ("B2 diff unknown", OK_CODE, {"gate_code": None}, "could not list"),
    ("B2 gate code unrefuted", OK_CODE, {"gate_code": True}, "has no REFUTE line"),
    ("B2 refuted at head", OK_CODE, {"gate_code": True, "refute": True}, None),
    ("B2 skipped refute", OK_CODE, {"gate_code": True, "skips": frozenset({"refute"})}, None),
    ("A report refute, cross-model, tier 2", OK_CODE,
     {"gate_code": True, "report_refute": True, "cross_model": True}, None),
    ("A report refute without cross-model", OK_CODE, {"gate_code": True, "report_refute": True},
     "has no REFUTE line"),
    ("A report refute at tier 3", OK_CODE,
     {"tier": 3, "gate_code": True, "report_refute": True, "cross_model": True}, "has no REFUTE line"),
    ("C no report", OK_CODE, {"has_reports": False}, "without its review report"),
    ("C skipped trace", OK_CODE, {"has_reports": False, "skips": frozenset({"ac-trace"})}, None),
    ("C plan names no AC", OK_CODE, {"plan_acs": frozenset()}, "names no acceptance criterion"),
    ("C criterion without line", OK_CODE, {"plan_acs": frozenset({"1", "2"})}, "AC-2 has no line"),
    ("C unproven", OK_CODE, {"claims": {"1": ["unproven"]}}, "AC-1 is unproven"),
    ("C unproven after a test", OK_CODE, {"claims": {"1": ["tests/t.py::test_a (unproven: x)"]}},
     "AC-1 is unproven"),
    ("C no path::test", OK_CODE, {"claims": {"1": ["covered by the suite"]}}, "names no"),
    ("C test off at head", OK_CODE, {"test_status": {("tests/t.py", "test_a"): "is marked skip"}},
     "is marked skip"),
    ("complete plan pass", OK_PLAN, {}, None),
    ("D1 unknown reviewer", OK_PLAN, {"model": "claude"}, "unknown model"),
    ("D1 no session source", OK_PLAN, {"plan_session": None}, "no `planned` report"),
    ("D1 unknown session", OK_PLAN, {"plan_session": "same"}, "is unknown"),
    ("D1 smaller reviewer", OK_PLAN, {"model": "claude-haiku-5"}, "smaller class"),
    ("D1 larger reviewer", OK_PLAN, {"model": "claude-fable-5-1"}, None),
    ("D1 other family reviews", OK_PLAN, {"model": "gpt-6.1-sol"}, None),
    ("D1 claude reviews another family's plan", OK_PLAN, {"plan_session": "gpt-6.1-sol"}, None),
    ("D1 other family needs no session", OK_PLAN, {"model": "gpt-6.1-sol", "plan_session": None}, None),
    ("C a test named unproven is a test", OK_CODE,
     {"claims": {"1": ["tests/t.py::test_ac_unproven_blocks"]},
      "test_status": {("tests/t.py", "test_ac_unproven_blocks"): None}}, None),
    ("C a heading plus its test line", OK_CODE,
     {"claims": {"1": ["the widget answers 42", "tests/t.py::test_a"]}}, None),
    ("C ids are text", OK_CODE, {"plan_acs": frozenset({"B1"}), "claims": {"B1": ["tests/t.py::test_a"]}}, None),
    ("D1 skipped", OK_PLAN, {"model": "claude-haiku-5", "skips": frozenset({"plan-review"})}, None),
    ("D2 gate-code plan single model", OK_PLAN, {"plan_gate_code": True}, "without 'cross-model'"),
    ("D2 gate-code plan cross-model", OK_PLAN, {"plan_gate_code": True, "cross_model": True}, None),
    ("D2 gate-code plan reasoned", OK_PLAN,
     {"plan_gate_code": True, "single_family": True, "skips": frozenset({"cross-model"})}, None),
    ("E1 on a plan review", OK_PLAN, {"plan_state": "differs"}, "holds more than records appended"),
]


@pytest.mark.parametrize("name,base,changes,expected", TABLE, ids=[row[0] for row in TABLE])
def test_decide_table(ev_mod, name, base, changes, expected):
    mod, _out = ev_mod
    got = mod.decide(mod.Evidence(**{**base, **changes}))
    if expected is None:
        assert got == [], got
    else:
        assert any(expected in g for g in got), got


def test_every_model_of_the_policy_has_a_class_and_the_defaults_match(ev_mod):
    mod, out = ev_mod
    policy = json.loads((out / "docs/process/model-policy.json").read_text())
    rules = policy["review_evidence"]
    assert {k: rules[k] for k in mod.DEFAULTS} == mod.DEFAULTS

    def cells(row):
        for cell in (row or {}).values():
            yield cell["model"] if isinstance(cell, dict) else cell
    models = {*cells(policy["default"]), *(m for row in policy["tiers"].values() for m in cells(row)),
              *(m for row in policy["classes"].values() for m in cells(row))}
    assert models and all(mod.model_class(m, rules["ranks"], rules["families"]) for m in models), models


def test_gate_code_in_plan_prose_and_criterion_ids(ev_mod):
    mod, _out = ev_mod
    names = mod.plan_names_gate_code
    assert not names("The guard is scripts/process/check_review.py:690; run `uv run scripts/process/gate_runner.py`.")
    assert names("Change ./scripts/process/attest.py.") and names("Edit the Makefile target.")
    assert names("C:\\repo\\.githooks\\pre-push") and not names("src/app/main.py")
    assert [mod.ac_key(m) for m in mod.AC_ID.finditer("AC-1, AC2. AC-B1 AC-2.1. ACCESS")] == ["1", "2", "B1", "2.1"]
    # prose names no criterion (plan review #225 N1): a German compound, a placeholder
    assert not list(mod.AC_ID.finditer("eine AC-Zeile je AC, AC-<id>, AC-N"))
    assert [mod.ac_key(m) for m in mod.AC_ID.finditer("AC 1: x; AC 2026 ok")] == ["1", "2026"]
    assert mod.held_open("DoD-deviation: open AC-3, AC-4 of #12 — next release") == {"3", "4"}


def test_claimed_tests_reads_lists_classes_and_titles(ev_mod):
    mod, _out = ev_mod
    assert mod.claimed_tests("`tests/a.py::test_x` und `::test_y`, tests/b.py::TestK::test_z[1]") == [
        ("tests/a.py", "test_x"), ("tests/a.py", "test_y"), ("tests/b.py", "TestK::test_z")]
    assert mod.claimed_tests("web/a.spec.ts::shows the banner (both states)") == [
        ("web/a.spec.ts", "shows the banner")]


PY_CASES = [
    ("plain", "def test_a():\n    assert 1\n", "test_a", None),
    ("helper", "def helper():\n    pass\n", "helper", "no test function"),
    ("missing", "def test_b():\n    pass\n", "test_a", "has no test"),
    ("decorated skip", "import pytest\n@pytest.mark.skip\ndef test_a():\n    pass\n", "test_a", "marked to skip"),
    ("alias", "import pytest\noff = pytest.mark.skip(reason='x')\n@off\ndef test_a():\n    pass\n",
     "test_a", "marked to skip"),
    ("imported mark", "from pytest import mark as m\n@m.xfail\ndef test_a():\n    pass\n", "test_a", "marked to skip"),
    ("annotated pytestmark", "import pytest\npytestmark: list = [pytest.mark.skip]\ndef test_a():\n    pass\n",
     "test_a", "module pytestmark"),
    ("importorskip", "import pytest\nnp = pytest.importorskip('np')\ndef test_a():\n    pass\n",
     "test_a", "module level"),
    ("module skip", "import pytest\npytest.skip('x', allow_module_level=True)\ndef test_a():\n    pass\n",
     "test_a", "module level"),
    ("docstring says skip", '"""We skip nothing here."""\ndef test_a():\n    pass\n', "test_a", None),
    ("body skip", "import pytest\ndef test_a():\n    pytest.skip('x')\n", "test_a", "skips in its body"),
    ("last def wins", "import pytest\ndef test_a():\n    pass\n@pytest.mark.skip\ndef test_a():\n    pass\n",
     "test_a", "marked to skip"),
    ("custom mark is fine", "import pytest\n@pytest.mark.slow\ndef test_a():\n    pass\n", "test_a", None),
    ("class method", "class TestK:\n    def test_a(self):\n        pass\n", "TestK::test_a", None),
    ("skipped class", "import pytest\n@pytest.mark.skip\nclass TestK:\n    def test_a(self):\n        pass\n",
     "TestK::test_a", "marked to skip"),
    ("class pytestmark", "import pytest\nclass TestK:\n    pytestmark = pytest.mark.xfail\n"
     "    def test_a(self):\n        pass\n", "TestK::test_a", "pytestmark that skips"),
    # refute #225 round 1: data is no mark, a call named skip on data is no skip
    ("data says --skip", "import pytest\n@pytest.mark.parametrize('f', ['--skip', '--run'])\n"
     "def test_a(f):\n    pass\n", "test_a", None),
    ("cases named skip", "import pytest\nCASES = [('skip', 1)]\n@pytest.mark.parametrize('n,v', CASES)\n"
     "def test_a(n, v):\n    R().skip(3)\n", "test_a", None),
    ("skipTest", "import unittest\nclass TestK(unittest.TestCase):\n    def test_a(self):\n"
     "        self.skipTest('later')\n", "TestK::test_a", "skips in its body"),
    ("raise SkipTest", "from unittest import SkipTest\ndef test_a():\n    raise SkipTest('x')\n",
     "test_a", "skips in its body"),
    ("unittest.skip", "import unittest\nclass TestK(unittest.TestCase):\n    @unittest.skip('x')\n"
     "    def test_a(self):\n        pass\n", "TestK::test_a", "marked to skip"),
    ("rebound after def", "import pytest\ndef test_a():\n    pass\ntest_a = pytest.mark.skip(reason='x')(test_a)\n",
     "test_a", "rebound after its definition"),
    ("uncollected class", "class Widget:\n    def test_a(self):\n        pass\n", "Widget::test_a",
     "no class pytest collects"),
    ("TestCase of any name", "import unittest\nclass Widget(unittest.TestCase):\n    def test_a(self):\n"
     "        pass\n", "Widget::test_a", None),
    ("__test__ = False", "__test__ = False\ndef test_a():\n    pass\n", "test_a", "__test__ = False"),
]


@pytest.mark.parametrize("name,text,test,expected", PY_CASES, ids=[c[0] for c in PY_CASES])
def test_python_tests_are_read_as_pytest_collects_them(ev_mod, name, text, test, expected):
    mod, _out = ev_mod
    got = mod._python_status(text, "tests/test_t.py", test)
    assert (got is None) if expected is None else (got and expected in got), got


@pytest.mark.parametrize("file,text,test,expected", [
    ("scripts/process/attest_evidence.py", "def test_status():\n    pass\n", "test_status", "no test module"),
    ("docs/process/refute.md", "refute", "refute", "no test file"),
    ("web/a.spec.ts", 'it("shows the banner", () => {})\n', "shows the banner", None),
    ("web/a.spec.ts", 'it.skip("shows the banner", () => {})\n', "shows the banner", "skip/todo"),
    ("web/a.spec.ts", '// shows the banner\n', "shows the banner", "declares no test"),
    ("src/lib.rs", "#[test]\n#[ignore]\nfn parses_x() {}\n", "parses_x", "no test file"),
    ("tests/parse.rs", "#[test]\n#[ignore]\nfn parses_x() {}\n", "parses_x", "skip/todo"),
], ids=["helper module", "markdown", "ts", "ts skip", "ts comment", "rust src", "rust ignored"])
def test_a_named_test_must_be_one_the_runner_runs(ev_mod, file, text, test, expected):
    mod, _out = ev_mod
    got = mod._python_status(text, file, test) if file.endswith(".py") else mod._other_status(text, file, test)
    assert (got is None) if expected is None else (got and expected in got), got


# --- end to end through attest.py ---------------------------------------------------

def _git(root, *args):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True).stdout.strip()


PLAN = "# Plan\n\nissue: #7\ntier: 2\nplan-session model: claude-opus-5\n\n## Acceptance criteria\n\n- AC-1: When x, the widget shall answer 42.\n"
TEST = "from widget import widget\n\ndef test_widget():\n    assert widget() == 42\n"


@pytest.fixture
def repo(render, tmp_path):
    out = render(tmp_path / "r", {"project_name": "d"})
    _git(out, "init", "-q", "-b", "main")
    _git(out, "config", "user.email", "t@t")
    _git(out, "config", "user.name", "t")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "base")
    _git(out, "checkout", "-q", "-b", "7-widget")
    (out / ".process-work/plans").mkdir(parents=True, exist_ok=True)
    (out / ".process-work/plans/2026-10-14-widget.md").write_text(PLAN)
    (out / "widget.py").write_text("def widget():\n    return 42\n")
    (out / "tests").mkdir(exist_ok=True)
    (out / "tests/test_widget.py").write_text(TEST)
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "feat: widget")
    return out


def _range(out):
    return _git(out, "merge-base", "main", "HEAD"), _git(out, "rev-parse", "HEAD")


def _report(out, body="- AC-1: `tests/test_widget.py::test_widget`\n"):
    rep = out / ".process-work/reviews/widget.md"
    rep.parent.mkdir(parents=True, exist_ok=True)
    rep.write_text("# Review\n\nreview: widget\n\n" + body)
    return ".process-work/reviews/widget.md"


def _attest(out, *extra, tier="2", independence="bundle,non-implementing", plan_review=False,
            work="widget", model="claude-opus-5"):
    base, head = _range(out)
    cmd = [sys.executable, str(out / "scripts/process/attest.py"), "--work", work, "--tier", tier,
           "--model", model, "--independence", independence, "--verdict", "pass",
           "--base", base, "--head", head, *(["--plan-review"] if plan_review else []), *extra, "."]
    return subprocess.run(cmd, cwd=out, capture_output=True, text=True)


def test_a_complete_pass_is_written(repo):
    r = _attest(repo, "--with", _report(repo), "--commit")
    assert r.returncode == 0, r.stderr
    assert "REVIEW work=widget" in r.stdout


def test_a_pass_without_its_report_is_refused_and_nothing_written(repo):
    r = _attest(repo)
    assert r.returncode == 1 and "without its review report" in r.stderr, r.stderr
    assert not any("REVIEW work=widget" in f.read_text()
                   for f in (repo / ".process-work/journal").rglob("*.md"))


def test_a_test_only_in_the_worktree_proves_nothing(repo):
    (repo / "tests/test_late.py").write_text("def test_late():\n    pass\n")
    r = _attest(repo, "--with", _report(repo, "- AC-1: tests/test_late.py::test_late\n"))
    assert r.returncode == 1 and "does not exist at head" in r.stderr, r.stderr


@pytest.mark.parametrize("staged", [False, True])
def test_e1_a_line_inside_the_plan_after_the_head_is_refused(repo, staged):
    """kenni #2407: the attestation's own plan edit left the pass not covering the head."""
    plan = repo / ".process-work/plans/2026-10-14-widget.md"
    plan.write_text(PLAN.replace("## Acceptance", "DECISION 2026-10-14 me: keep 42\n\n## Acceptance"))
    if staged:
        _git(repo, "add", str(plan))
    r = _attest(repo, "--with", _report(repo))
    assert r.returncode == 1 and "holds more than records appended" in r.stderr, r.stderr


def test_e1_records_appended_after_the_plan_ride_and_count(repo):
    """The gate's `records_only`: an appended REFUTE rides the attestation and is the refute."""
    (repo / "scripts/process/extra_gate.py").write_text("X = 1\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "feat: gate")
    plan = repo / ".process-work/plans/2026-10-14-widget.md"
    plan.write_text(PLAN + "\nREFUTE work=widget round=1: survives: one constant, no reader\n")
    r = _attest(repo, "--with", _report(repo), "--with", ".process-work/plans/2026-10-14-widget.md",
                "--commit")
    assert r.returncode == 0, r.stderr


def test_an_appended_refute_not_riding_the_attestation_does_not_count(repo):
    """Plan review #225 N3: without `--with` the plan, the line would never be committed."""
    (repo / "scripts/process/extra_gate.py").write_text("X = 1\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "feat: gate")
    plan = repo / ".process-work/plans/2026-10-14-widget.md"
    plan.write_text(PLAN + "\nREFUTE work=widget round=1: survives: one constant, no reader\n")
    r = _attest(repo, "--with", _report(repo))
    assert r.returncode == 1 and "has no REFUTE line" in r.stderr, r.stderr


def test_another_plans_refute_lends_nothing(repo):
    """Plan review #225 N2: a second plan of the issue neither lends nor takes a refute."""
    (repo / "scripts/process/extra_gate.py").write_text("X = 1\n")
    (repo / ".process-work/plans/archive").mkdir(parents=True, exist_ok=True)
    (repo / ".process-work/plans/archive/2026-01-01-older.md").write_text(
        "# Plan\n\nissue: #7\n\nREFUTE work=7 round=1: survives: older work\n"
        "skipped refute work=7: older work\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "feat: gate")
    r = _attest(repo, "--with", _report(repo))
    assert r.returncode == 1 and "has no REFUTE line" in r.stderr, r.stderr


def test_a_criterion_held_open_by_a_dod_deviation_needs_no_test(repo):
    plan = repo / ".process-work/plans/2026-10-14-widget.md"
    plan.write_text(PLAN + "- AC-2: When y, the widget shall log.\n\n"
                    "DoD-deviation: open AC-2 — logging lands with #8\n")
    _git(repo, "commit", "-qam", "docs: hold AC-2")
    assert _attest(repo, "--with", _report(repo)).returncode == 0


def test_lines_bind_by_any_id_of_the_work(repo):
    """The plan declares issue #7; its REFUTE line names the slug; the pass names the issue."""
    (repo / "Makefile").write_text("all:\n\ttrue\n")
    plan = repo / ".process-work/plans/2026-10-14-widget.md"
    plan.write_text(PLAN + "\nREFUTE work=widget round=1: survives: one target\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "build: target")
    r = _attest(repo, "--with", _report(repo), work="7")
    assert r.returncode == 0, r.stderr


def test_an_archived_plan_still_answers_a_late_lens(repo):
    plan = ".process-work/plans/2026-10-14-widget.md"
    (repo / ".process-work/plans/archive").mkdir(parents=True, exist_ok=True)
    _git(repo, "mv", plan, ".process-work/plans/archive/2026-10-14-widget.md")
    _git(repo, "commit", "-q", "-m", "docs: archive")
    r = _attest(repo, "--with", _report(repo))
    assert r.returncode == 0, r.stderr


def test_a_criterion_quoted_in_backticks_is_an_example(repo):
    plan = repo / ".process-work/plans/2026-10-14-widget.md"
    plan.write_text(PLAN + "\nA report line reads `AC-9: <path>::<test>`.\n")
    _git(repo, "commit", "-qam", "docs: example")
    assert _attest(repo, "--with", _report(repo)).returncode == 0


def test_a_criterion_the_plan_names_anywhere_needs_its_line(repo):
    plan = repo / ".process-work/plans/2026-10-14-widget.md"
    plan.write_text(PLAN + "\n## Tasks\n\n1. Deliver AC-2.1 with test_widget.\n")
    _git(repo, "commit", "-qam", "docs: task")
    r = _attest(repo, "--with", _report(repo))
    assert r.returncode == 1 and "AC-2.1 has no line" in r.stderr, r.stderr


def test_a_plan_review_by_a_smaller_class_is_refused(repo):
    r = _attest(repo, model="claude-sonnet-5", plan_review=True)
    assert r.returncode == 1 and "smaller class" in r.stderr and "(plan-line)" in r.stderr, r.stderr
    assert _attest(repo, model="claude-opus-5-5", plan_review=True).returncode == 0
    r = _attest(repo, model="opus", plan_review=True)
    assert r.returncode == 1 and "unknown model" in r.stderr, r.stderr


def test_b2_gate_code_needs_a_refute_line_at_head(repo):
    (repo / "scripts/process/extra_gate.py").write_text("X = 1\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "feat: gate")
    r = _attest(repo, "--with", _report(repo))
    assert r.returncode == 1 and "has no REFUTE line" in r.stderr, r.stderr
    plan = repo / ".process-work/plans/2026-10-14-widget.md"
    plan.write_text(PLAN + "\nREFUTE work=widget round=1: survives: one gate constant\n")
    _git(repo, "commit", "-qam", "docs: refute")
    r = _attest(repo, "--with", _report(repo))
    assert r.returncode == 0, r.stderr


def test_b2_a_skip_naming_another_repository_does_not_count(repo):
    (repo / "Makefile").write_text("all:\n\ttrue\n")
    plan = repo / ".process-work/plans/2026-10-14-widget.md"
    plan.write_text(PLAN + "\nskipped refute work=other/repo#7: product target only\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "build: target")
    r = _attest(repo, "--with", _report(repo))
    assert r.returncode == 1 and "has no REFUTE line" in r.stderr, r.stderr
    # even the plan's own `issue: owner/repo#7` id: a repository-qualified skip binds nothing here
    plan.write_text(PLAN.replace("issue: #7", "issue: o/r#7") + "\nskipped refute work=o/r#7: product target\n")
    _git(repo, "commit", "-qam", "docs: qualified skip")
    r = _attest(repo, "--with", _report(repo))
    assert r.returncode == 1 and "has no REFUTE line" in r.stderr, r.stderr
    plan.write_text(PLAN + "\nskipped refute work=widget: product target only, no gate reads it\n")
    _git(repo, "commit", "-qam", "docs: skip")
    assert _attest(repo, "--with", _report(repo)).returncode == 0


def test_b1_the_branch_cannot_lower_the_threshold_for_its_own_pass(repo):
    (repo / "docs/process/model-policy.local.json").write_text(
        json.dumps({"review_evidence": {"cross_model_from_tier": 4}}))
    plan = repo / ".process-work/plans/2026-10-14-widget.md"
    plan.write_text(PLAN.replace("tier: 2", "tier: 3")
                    + "\nREFUTE work=widget round=1: survives: policy edit only\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "chore: policy")
    r = _attest(repo, "--with", _report(repo), tier="3",
                independence="bundle,non-implementing")
    assert r.returncode == 1 and "without 'cross-model'" in r.stderr, r.stderr


def test_an_owner_exception_names_the_evidence_it_overrides(repo):
    r = _attest(repo, "--exception", "hotfix without a report")
    assert r.returncode == 0, r.stderr
    shard = next((repo / ".process-work/journal").rglob("*.md")).read_text()
    assert "REVIEW-EXCEPTION" in shard and "without its review report" in shard


def test_d1_the_planned_report_names_the_plan_session(repo):
    """The plan session's own `planned` report outranks the plan's self-declared line."""
    subprocess.run([sys.executable, "scripts/process/report.py", "planned", "--issue", "7",
                    "--model", "claude-fable-5-1"], cwd=repo, capture_output=True, text=True, check=True)
    r = _attest(repo, plan_review=True)
    assert r.returncode == 1 and "smaller class" in r.stderr and "(report)" in r.stderr, r.stderr


def test_a_backticked_criterion_still_counts(repo):
    """Refute #225: only a quoted report line is an example, not every backticked id."""
    plan = repo / ".process-work/plans/2026-10-14-widget.md"
    plan.write_text(PLAN + "- `AC-2`: When y, the widget shall log.\n")
    _git(repo, "commit", "-qam", "docs: AC-2")
    r = _attest(repo, "--with", _report(repo))
    assert r.returncode == 1 and "AC-2 has no line" in r.stderr, r.stderr


def test_a_spec_kit_plan_takes_its_criteria_from_spec_md(repo):
    spec = repo / "specs/007-widget"
    spec.mkdir(parents=True)
    (spec / "plan.md").write_text("# Plan\n\nissue: #9\ntier: 2\n\nDelivers AC-1.\n")
    (spec / "spec.md").write_text("# Spec\n\n- AC-1: answers 42\n- AC-3: logs the answer\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "spec")
    r = _attest(repo, "--with", _report(repo), work="007-widget")
    assert r.returncode == 1 and "AC-3 has no line" in r.stderr, r.stderr


def test_an_unmeasured_planned_report_falls_back_to_the_plan_line(repo):
    env = {k: v for k, v in __import__("os").environ.items() if k != "PROCESS_MODEL"}
    subprocess.run([sys.executable, "scripts/process/report.py", "planned", "--issue", "7"],
                   cwd=repo, capture_output=True, text=True, check=True, env=env)
    r = _attest(repo, model="claude-sonnet-5", plan_review=True)
    assert r.returncode == 1 and "(plan-line)" in r.stderr, r.stderr


def test_two_plans_of_one_issue_narrow_to_the_attested_slug(repo):
    (repo / ".process-work/plans/2026-10-14-gizmo.md").write_text("# Gizmo\n\nissue: #7\ntier: 2\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "second plan of #7")
    assert _attest(repo, "--with", _report(repo)).returncode == 0
    # by issue: the branch's slug picks the plan (`attest.round_ids`) ...
    assert _attest(repo, "--with", _report(repo), work="7").returncode == 0
    # ... and a branch naming neither leaves it open — named, not guessed
    _git(repo, "checkout", "-q", "-b", "7-other")
    r = _attest(repo, "--with", _report(repo), work="7")
    assert r.returncode == 1 and "several plans of work 7" in r.stderr, r.stderr
