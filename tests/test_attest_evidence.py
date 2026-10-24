"""#225: a Tier 2+ pass shows its evidence before attest.py writes it —
cross-model or a reasoned single-family, a refute for gate code, one test per
acceptance criterion, a plan reviewer not below the plan session's class, and
the plan's own lines committed before the attested head."""
import datetime as dt
import importlib
import inspect
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

sys.dont_write_bytecode = True


@pytest.fixture
def ev_mod(render, tmp_path):
    out = render(tmp_path / "t", {"project_name": "d"})
    sys.path.insert(0, str(out / "scripts/process"))
    try:
        for name in ("attest_evidence", "check_review", "dispatch", "report", "process_git", "required_records"):
            sys.modules.pop(name, None)
        yield importlib.import_module("attest_evidence"), out
    finally:
        sys.path.remove(str(out / "scripts/process"))
        for name in ("attest_evidence", "check_review", "dispatch", "report", "process_git", "required_records"):
            sys.modules.pop(name, None)


RANKS = {"claude-haiku": 0, "claude-sonnet": 1, "claude-opus": 2, "claude-fable": 3}
OK_CODE = dict(work="7", tier=2, verdict="pass", plan_review=False, model="claude-opus-5",
               cross_model_from=3, ranks=RANKS, families=("gpt-",), plan_acs=frozenset({"1"}),
               has_reports=True, claims={"1": ["tests/t.py::test_a"]},
               test_status={("tests/t.py", "test_a"): None}, plan_rel="p.md")
OK_PLAN = dict(work="7-plan", tier=2, verdict="pass", plan_review=True, model="claude-opus-5",
               cross_model_from=3, ranks=RANKS, families=("gpt-",), plan_session="claude-opus-5",
               plan_session_source="plan-line", plan_rel="p.md")

TS = 'it("adds", () => {})\n'
PY_T = "def test_x():\n    assert True\n"
RESOLVE_CASES = [
    ("exact", "tests/c.ts::adds", ["tests/c.ts"], {"tests/c.ts": TS}, [("tests/c.ts", True)], None),
    ("dot-slash", "./tests/c.ts::adds", ["tests/c.ts"], {"tests/c.ts": TS}, [("tests/c.ts", True)], None),
    ("suffix", "c.ts::adds", ["tests/c.ts"], {"tests/c.ts": TS}, [("tests/c.ts", True)], None),
    ("ambiguous-suffix", "tests/c.ts::adds", ["a/tests/c.ts", "b/tests/c.ts"],
     {"a/tests/c.ts": TS, "b/tests/c.ts": TS}, [(None, False)], "several tracked files"),
    ("missing", "tests/gone.ts::adds", ["tests/c.ts"], {"tests/c.ts": TS}, [(None, False)],
     "is no tracked file"),
    ("namesake", "tests/test_w.py::test_a",
     ["tests/test_w.py", "backend/tests/test_w.py"],
     {"tests/test_w.py": "def test_b():\n    assert True\n",
      "backend/tests/test_w.py": "def test_a():\n    assert True\n"},
     [("backend/tests/test_w.py", True)], None),
    ("no-test", "tests/c.ts::nope", ["tests/c.ts"], {"tests/c.ts": TS}, [("tests/c.ts", False)],
     "declares no test 'nope'"),
    ("title", "tests/c.ts::adds (x)", ["tests/c.ts"], {"tests/c.ts": TS}, [("tests/c.ts", True)], None),
    ("params", "tests/test_p.py::test_x[1]", ["tests/test_p.py"], {"tests/test_p.py": PY_T},
     [("tests/test_p.py", True)], None),
    ("no-file", "a::b::c", ["tests/c.ts"], {"tests/c.ts": TS}, [], None),
    ("no-listing", "tests/c.ts::adds", None, {"tests/c.ts": TS}, [(None, False)],
     "git cannot list the files"),
    ("two", "tests/gone.ts::adds, tests/c.ts::adds", ["tests/c.ts"], {"tests/c.ts": TS},
     [(None, False), ("tests/c.ts", True)], None),
]


@pytest.mark.parametrize("name,tests,files,texts,expected,why", RESOLVE_CASES,
                         ids=[c[0] for c in RESOLVE_CASES])
def test_resolve_tests_reads_a_reference_as_the_gate_does(ev_mod, name, tests, files, texts,
                                                          expected, why):
    """#303: one resolver for the gate and red_evidence — exact path, `./`, suffix,
    namesake fallback, and a missing listing all read as `_class_test_problem` reads."""
    ev, out = ev_mod
    rules = ev.review_policy(out, "HEAD")[0]
    got = ev.resolve_tests(tests, files, lambda rel: texts.get(rel), rules)
    assert [(r.path, r.why is None) for r in got] == expected, got
    if why is not None:
        assert why in got[0].why, got[0].why
    if name == "title":
        assert got[0].name == "adds"
    if name == "params":
        assert got[0].name == "test_x"


def test_reference_resolution_has_one_owner(ev_mod):
    """#303: the gate reads references through `resolve_tests`, never a copy; so does
    red_evidence — no second parser or alias rule on the writing side."""
    ev, out = ev_mod
    src = inspect.getsource(ev._class_test_problem)
    assert "resolve_tests(" in src
    assert "_test_file(" not in src and "_suffix_hits(" not in src
    red = (out / "scripts/process/red_evidence.py").read_text(encoding="utf-8")
    assert "resolve_tests(" in red
    # `_is_test_file` is red_evidence's own carry-along helper, not the gate's `_test_file`
    without_helpers = red.replace("_is_test_file(", "")
    for copy in ("claimed_tests(", "_test_file(", "_suffix_hits(", 'removeprefix("./")'):
        assert copy not in without_helpers, copy

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
     {"tier": 3, "single_family": True, "skips": frozenset({"cross-model"}), "refute": True}, None),
    ("B1 a skip line without the token", OK_CODE, {"tier": 3, "skips": frozenset({"cross-model"})},
     "without 'cross-model'"),
    ("B1 cross-model", OK_CODE, {"tier": 3, "cross_model": True, "refute": True}, None),
    # #282: the required-records table — refute from Tier 3, root cause after a fix streak
    ("R tier 3 unrefuted", OK_CODE, {"tier": 3, "cross_model": True}, "has no REFUTE line"),
    ("R tier 3 skipped refute", OK_CODE, {"tier": 3, "cross_model": True, "skips": frozenset({"refute"})},
     None),
    ("R fix streak 3 without root cause", OK_CODE, {"fix_streak": 3}, "has no ROOT-CAUSE line"),
    ("R fix streak 2 owes nothing", OK_CODE, {"fix_streak": 2}, None),
    ("R fix streak 3 with root cause", OK_CODE, {"fix_streak": 3, "root_cause": True}, None),
    ("R fix streak 3 skipped", OK_CODE, {"fix_streak": 3, "skips": frozenset({"root-cause"})}, None),
    ("R fix streak unknown", OK_CODE, {"fix_streak": None}, "fix commits"),
    ("R fix streak unknown, root cause there", OK_CODE, {"fix_streak": None, "root_cause": True}, None),
    ("R a project's extra row", OK_CODE,
     {"records": ({"kind": "refute", "when": {"tier_from": 2}},)}, "has no REFUTE line"),
    # v2.77: per blocked code round the branch adds, a class test; from the second, a REPLAN
    ("R one blocked round, class test there", OK_CODE, {"blocked_rounds": 1}, None),
    ("R one blocked round owes no REPLAN", OK_CODE, {"blocked_rounds": 1, "replan_open": (1,)}, None),
    ("R blocked round without class test", OK_CODE,
     {"blocked_rounds": 1, "class_test_open": ("1 (no ROOT-CAUSE line)",)}, "round(s) 1 (no ROOT-CAUSE line)"),
    ("R class test skipped", OK_CODE,
     {"blocked_rounds": 1, "class_test_open": ("1 (x)",), "skips": frozenset({"class-test"})}, None),
    ("R follow-up block without REPLAN", OK_CODE, {"blocked_rounds": 3, "replan_open": (3,)},
     "blocked round(s) 3 without a REPLAN"),
    ("R REPLAN skipped", OK_CODE, {"blocked_rounds": 3, "replan_open": (3,), "skips": frozenset({"replan"})},
     None),
    ("R blocked rounds unknown", OK_CODE, {"blocked_rounds": None}, "blocked code rounds"),
    ("R blocked rounds unknown, both skipped", OK_CODE,
     {"blocked_rounds": None, "skips": frozenset({"replan", "class-test"})}, None),
    ("R a project's row on blocked rounds, unknown", OK_CODE,
     {"records": ({"kind": "refute", "when": {"blocked_rounds": 1}},), "blocked_rounds": None}, "unknown"),
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
    ("D1 smaller reviewer", OK_PLAN, {"model": "claude-sonnet-5"}, "smaller class"),
    ("D1 lowest class reviews no plan", OK_PLAN, {"model": "claude-haiku-5", "plan_session": "claude-haiku-5"},
     "lowest class"),
    ("D1 unmeasured report", OK_PLAN, {"plan_session": None, "plan_session_source": "unmeasured-report"},
     "measured no model"),
    ("D1 larger reviewer", OK_PLAN, {"model": "claude-fable-5-1"}, None),
    ("D1 top class over an unmeasured report", OK_PLAN,
     {"model": "claude-fable-5-1", "plan_session": None, "plan_session_source": "unmeasured-report"}, None),
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


def test_the_pytest_name_has_one_public_owner(ev_mod):
    """#306: a parameter value may hold brackets (`test_x[a[b]]`); the whole suffix goes,
    not the part after its last `[`. Other runners keep their names."""
    mod, _out = ev_mod
    for raw in ("test_x[a[b]]", "test_x[]]", "test_x[]", "test_x[\\xfc]",
                "test_x[a[b], c]", "test_x[a[b,c]]"):
        assert mod.attest_name("tests/test_x.py", raw) == "test_x", raw
    assert mod.attest_name("tests/test_x.py", "TestK::test_z[a[b]]") == "TestK::test_z"
    assert mod.attest_name("web/a.test.ts", "adds[weird]") == "adds[weird]"
    assert mod.claimed_tests("tests/test_x.py::test_x[a[b]]") == [("tests/test_x.py", "test_x")]


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
    # refute #225 round 2: a setup that skips, every case skipped, an inherited test
    ("autouse fixture skips", "import pytest\n@pytest.fixture(autouse=True)\ndef _off():\n    pytest.skip('x')\n"
     "def test_a():\n    pass\n", "test_a", "autouse fixture skips"),
    ("setUp skips", "import unittest\nclass TestK(unittest.TestCase):\n    def setUp(self):\n"
     "        self.skipTest('x')\n    def test_a(self):\n        pass\n", "TestK::test_a", "setup"),
    ("every case skipped", "import pytest\n@pytest.mark.parametrize('x', [pytest.param(1, marks=pytest.mark.skip)])\n"
     "def test_a(x):\n    pass\n", "test_a", "every parametrized case"),
    ("one case skipped", "import pytest\n@pytest.mark.parametrize('x', [1, pytest.param(2, marks=pytest.mark.skip)])\n"
     "def test_a(x):\n    pass\n", "test_a", None),
    ("inherited test", "class BackendTests:\n    def test_insert(self):\n        pass\n"
     "class TestSqlite(BackendTests):\n    pass\n", "TestSqlite::test_insert", None),
    ("non-autouse fixture may skip", "import pytest\n@pytest.fixture\ndef db():\n    pytest.skip('x')\n"
     "def test_a():\n    pass\n", "test_a", None),
]


@pytest.mark.parametrize("name,text,test,expected", PY_CASES, ids=[c[0] for c in PY_CASES])
def test_python_tests_are_read_as_pytest_collects_them(ev_mod, name, text, test, expected):
    mod, _out = ev_mod
    got = mod._python_status(text, "tests/test_t.py", test, mod.DEFAULTS)
    assert (got is None) if expected is None else (got and expected in got), got


OTHER_CASES = [
    ("helper module", "scripts/process/attest_evidence.py", "def test_status():\n    pass\n", "test_status",
     "no test module"),
    ("markdown", "docs/process/refute.md", "refute", "refute", "no test file"),
    ("readme in tests", "tests/README.md", "Run it with make check.", "make check", "no test file"),
    ("ts", "web/a.spec.ts", 'it("shows the banner", () => {})\n', "shows the banner", None),
    ("ts skip", "web/a.spec.ts", 'it.skip("shows the banner", () => {})\n', "shows the banner", "skip"),
    ("ts comment", "web/a.spec.ts", '// shows the banner\n', "shows the banner", "declares no test"),
    ("ts substring", "web/w.test.ts", 'it("answers 42", () => {})\n', "answers 4", "declares no test"),
    ("rust src", "src/lib.rs", "#[test]\n#[ignore]\nfn parses_x() {}\n", "parses_x", "no test file"),
    ("rust ignored", "tests/parse.rs", "#[test]\n#[ignore]\nfn parses_x() {}\n", "parses_x", "skip"),
    ("xcode target", "ios/KenniTests/ChatTests.swift", "func testSend() {\n  XCTAssert(true)\n}\n",
     "testSend", None),
    ("xcode ui sources", "KenniAppUITests/Sources/AppSnapshotTests.swift", "func testShot() {}\n",
     "testShot", None),
    ("xctskip in body", "KenniTests/ATests.swift", "func testA() throws {\n  throw XCTSkip(\"x\")\n}\n",
     "testA", "skip"),
    ("go t.Skip in body", "pkg/x_test.go", 'func TestX(t *testing.T) {\n\tt.Skip("later")\n}\n', "TestX", "skip"),
    ("the next test's skip", "pkg/x_test.go", 'func TestX(t *testing.T) {}\nfunc TestY(t *testing.T) {\n'
     '\tt.Skip("y")\n}\n', "TestX", None),
    # refute #225 round 3
    ("XCTSkipUnless", "KenniTests/PerfTests.swift", 'func testA() throws {\n  try XCTSkipUnless(false, "perf")\n}\n',
     "testA", "skip"),
    ("swift setUp skips", "KenniTests/MTests.swift",
     'override func setUpWithError() throws { throw XCTSkip("phone") }\nfunc testSend() { XCTFail() }\n',
     "testSend", "a setup"),
    ("a comment does not end the body", "pkg/x_test.go",
     'func TestX(t *testing.T) {\n\t// it is flaky on CI\n\tt.Skip("flaky")\n}\n', "TestX", "skip"),
    ("swift helper", "ios/AppTests/Support/Fixture.swift", "func makeWidget() -> Widget { Widget() }\n",
     "makeWidget", "declares no test"),
    ("ts helper", "web/tests/helpers.ts", "export function renderWidget(): void {}\n", "renderWidget",
     "declares no test"),
    ("a todo above is another test", "web/a.test.ts", "it.todo('logs later')\nit('answers 42', () => {})\n",
     "answers 42", None),
    ("kotlin @Test", "app/src/test/kotlin/WidgetTest.kt", "@Test\nfun answers() {}\n", "answers", None),
    ("rust #[test]", "tests/parse.rs", "#[test]\nfn parses_x() {}\n", "parses_x", None),
]


@pytest.mark.parametrize("name,file,text,test,expected", OTHER_CASES, ids=[c[0] for c in OTHER_CASES])
def test_a_named_test_must_be_one_the_runner_runs(ev_mod, name, file, text, test, expected):
    mod, _out = ev_mod
    rules = mod.DEFAULTS
    got = (mod._python_status(text, file, test, rules) if file.endswith(".py")
           else mod._other_status(text, file, test, rules))
    assert (got is None) if expected is None else (got and expected in got), got


def test_the_project_declares_its_test_files(ev_mod):
    mod, _out = ev_mod
    rules = {**mod.DEFAULTS, "python_files": ["check_*.py"], "test_files": [*mod.DEFAULTS["test_files"], "src/*.rs"]}
    assert mod._python_status("def test_a():\n    pass\n", "tests/check_x.py", "test_a", rules) is None
    assert mod._other_status("#[test]\nfn parses_x() {}\n", "src/lib.rs", "parses_x", rules) is None


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


def test_an_unmeasured_planned_report_does_not_hand_the_class_to_the_plan_line(repo):
    """#230: the plan's own line is the session's word about itself — once a `planned`
    report exists, an unmeasured one cannot be replaced by it; the waiver is named."""
    env = {k: v for k, v in __import__("os").environ.items() if k != "PROCESS_MODEL"}
    subprocess.run([sys.executable, "scripts/process/report.py", "planned", "--issue", "7"],
                   cwd=repo, capture_output=True, text=True, check=True, env=env)
    r = _attest(repo, model="claude-opus-5", plan_review=True)
    assert r.returncode == 1 and "measured no model" in r.stderr, r.stderr
    assert "skipped plan-review work=" in r.stderr and "-plan" in r.stderr, r.stderr


def test_without_a_planned_report_the_plan_line_still_counts(repo):
    """#230 AC-2: slug works without a report keep v2.71's plan line."""
    r = _attest(repo, model="claude-sonnet-5", plan_review=True)
    assert r.returncode == 1 and "(plan-line)" in r.stderr, r.stderr
    assert _attest(repo, model="claude-opus-5", plan_review=True).returncode == 0


def test_the_lowest_class_reviews_no_plan_not_even_its_own(repo):
    """#228: haiku reviewing a haiku plan passed — the lowest class reviews no plan."""
    plan = repo / ".process-work/plans/2026-10-14-widget.md"
    plan.write_text(PLAN.replace("claude-opus-5", "claude-haiku-5-5"))
    _git(repo, "commit", "-qam", "plan by haiku")
    r = _attest(repo, model="claude-haiku-5-5", plan_review=True)
    assert r.returncode == 1 and "lowest class" in r.stderr, r.stderr
    assert _attest(repo, model="claude-sonnet-5", plan_review=True).returncode == 0


def test_a_base_older_than_the_evidence_rules_does_not_lower_the_floor(repo):
    """#229: the base's policy predates `review_evidence`; the checkout's own stricter
    floor applies — it can only tighten, while a base that has the key still decides."""
    _git(repo, "checkout", "-q", "main")
    pol = repo / "docs/process/model-policy.json"
    data = json.loads(pol.read_text())
    data.pop("review_evidence")
    pol.write_text(json.dumps(data))
    _git(repo, "commit", "-qam", "an older policy")
    _git(repo, "checkout", "-q", "7-widget")
    _git(repo, "merge", "-q", "--no-edit", "main")
    (repo / "docs/process/model-policy.local.json").write_text(
        json.dumps({"review_evidence": {"cross_model_from_tier": 2}}))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "chore: stricter local floor")
    r = _attest(repo, "--with", _report(repo), independence="bundle,non-implementing")
    assert r.returncode == 1 and "without 'cross-model'" in r.stderr, r.stderr
    # ... and a looser one never lowers the template's (refute v2.75 r2)
    (repo / "docs/process/model-policy.local.json").write_text(
        json.dumps({"review_evidence": {"cross_model_from_tier": 4}}))
    _git(repo, "commit", "-qam", "chore: a looser local floor")
    r = _attest(repo, "--with", _report(repo), tier="3", independence="bundle,non-implementing")
    assert r.returncode == 1 and "without 'cross-model'" in r.stderr, r.stderr


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


# --- code review #225: rules no test turned red -------------------------------------

def _gate_change(repo):
    (repo / "scripts/process/extra_gate.py").write_text("X = 1\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "feat: gate")


def test_a_placeholder_reason_is_no_skip(repo):
    _gate_change(repo)
    plan = repo / ".process-work/plans/2026-10-14-widget.md"
    plan.write_text(PLAN + "\nskipped refute work=widget: <reason>\n")
    _git(repo, "commit", "-qam", "docs: placeholder")
    r = _attest(repo, "--with", _report(repo))
    assert r.returncode == 1 and "has no REFUTE line" in r.stderr, r.stderr


def test_codex_review_is_the_older_spelling_of_cross_model(repo):
    plan = repo / ".process-work/plans/2026-10-14-widget.md"
    plan.write_text(PLAN.replace("tier: 2", "tier: 3") + "\nREFUTE work=widget round=1: survives: none\n"
                    "skipped codex-review work=widget: no second family on this host\n")
    _git(repo, "commit", "-qam", "docs: reason")
    r = _attest(repo, "--with", _report(repo), tier="3", independence="bundle,non-implementing,single-family")
    assert r.returncode == 0, r.stderr


@pytest.mark.parametrize("layer, says", [("{not json", "not valid JSON"),
                                         ('{"review_evidence": {"cross_model_from_tier": "2"}}', "integer 0-4"),
                                         ('{"review_evidence": {"ranks": ["claude"]}}', "ranks must map"),
                                         ('{"review_evidence": {"test_files": "*"}}', "test_files must be"),
                                         # #282 refute: `[]` would lift every duty; a malformed row is no pass
                                         ('{"review_evidence": {"required_records": []}}',
                                          "cannot replace the template's"),
                                         ('{"review_evidence": {"required_records_extra": '
                                          '[{"kind": "nope", "when": {"tier_from": 1}}]}}', "kind must be one of")])
def test_an_unreadable_policy_at_the_base_refuses(repo, layer, says):
    _git(repo, "checkout", "-q", "main")
    (repo / "docs/process/model-policy.local.json").write_text(layer)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "chore: policy")
    _git(repo, "checkout", "-q", "7-widget")
    _git(repo, "rebase", "-q", "main")
    r = _attest(repo, "--with", _report(repo))
    assert r.returncode == 1 and says in r.stderr, r.stderr


def test_an_owner_decision_row_of_the_project_is_met_by_the_owners_line(repo):
    """Refute of #282: attest never saw an owner's DECISION, so a project row owing one
    refused every attest whatever the plan said."""
    _git(repo, "checkout", "-q", "main")
    (repo / "docs/process/model-policy.local.json").write_text(json.dumps({"review_evidence": {
        "required_records_extra": [{"kind": "owner-decision", "when": {"tier_from": 2}}]}}))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "chore: policy")
    _git(repo, "checkout", "-q", "7-widget")
    _git(repo, "rebase", "-q", "main")
    r = _attest(repo, "--with", _report(repo))
    assert r.returncode == 1 and "no owner's word" in r.stderr, r.stderr
    plan = repo / ".process-work/plans/2026-10-14-widget.md"
    plan.write_text(plan.read_text() + "\n- DECISION 2026-10-21 owner: ship the widget as planned\n")
    _git(repo, "commit", "-qam", "docs: owner decides")
    r = _attest(repo, "--with", _report(repo))
    assert "no owner's word" not in r.stderr, r.stderr


def test_a_plan_review_skip_names_the_plan_work(repo):
    plan = repo / ".process-work/plans/2026-10-14-widget.md"
    plan.write_text(PLAN + "\nskipped plan-review work=widget: the sonnet session wrote it\n")
    _git(repo, "commit", "-qam", "docs: code-review id")
    assert _attest(repo, model="claude-haiku-5", plan_review=True).returncode == 1
    plan.write_text(PLAN + "\nskipped plan-review work=widget-plan: the sonnet session wrote it\n")
    _git(repo, "commit", "-qam", "docs: plan-review id")
    r = _attest(repo, model="claude-haiku-5", plan_review=True)
    assert r.returncode == 0, r.stderr


def test_only_a_review_report_carries_the_trace(repo):
    notes = repo / ".process-work/notes.md"
    notes.write_text("- AC-1: `tests/test_widget.py::test_widget`\n")
    r = _attest(repo, "--with", ".process-work/notes.md")
    assert r.returncode == 1 and "without its review report" in r.stderr, r.stderr


def test_e1_a_plan_changed_only_in_the_index_is_refused(repo):
    plan = repo / ".process-work/plans/2026-10-14-widget.md"
    plan.write_text(PLAN.replace("## Acceptance", "Later prose.\n\n## Acceptance"))
    _git(repo, "add", str(plan))
    plan.write_text(PLAN)  # the worktree is the head again; the index is not
    r = _attest(repo, "--with", _report(repo))
    assert r.returncode == 1 and "holds more than records appended" in r.stderr, r.stderr


def test_a_pass_without_a_range_is_refused(repo):
    r = subprocess.run([sys.executable, str(repo / "scripts/process/attest.py"), "--work", "widget",
                        "--tier", "2", "--model", "claude-opus-5", "--independence", "bundle,non-implementing",
                        "--verdict", "pass", "--with", _report(repo), "."], cwd=repo, capture_output=True, text=True)
    assert r.returncode == 1 and "reads its evidence at the reviewed range" in r.stderr, r.stderr


def test_a_second_lens_after_the_first_archived_the_plan(repo):
    """Code review #225: lens 1 archives with its pass; lens 2 attests the same head."""
    base, head = _range(repo)
    r = _attest(repo, "--with", _report(repo), "--archive", ".process-work/plans/2026-10-14-widget.md",
                "--commit")
    assert r.returncode == 0, r.stderr
    r = subprocess.run([sys.executable, str(repo / "scripts/process/attest.py"), "--work", "widget",
                        "--tier", "2", "--reviewer", "lens-2", "--model", "claude-opus-5",
                        "--independence", "bundle,non-implementing", "--verdict", "pass", "--round", "1",
                        "--base", base, "--head", head, "--with", _report(repo), "."],
                       cwd=repo, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_a_parametrized_id_may_hold_commas(ev_mod):
    mod, _out = ev_mod
    assert mod.claimed_tests("tests/a.py::test_x[1, 2], tests/a.py::test_y") == [
        ("tests/a.py", "test_x"), ("tests/a.py", "test_y")]


def test_a_test_title_may_hold_commas_and_semicolons(ev_mod):
    """#237 (Kenni #2607): a vitest title written as a sentence was cut at its comma."""
    mod, _out = ev_mod
    title = "markiert den Lauf als unvollständig und siegelt nicht, wenn eine Aufzeichnung scheitert"
    assert mod.claimed_tests(f"web/run.test.ts::{title}") == [("web/run.test.ts", title)]
    assert mod.claimed_tests("`web/a.test.ts::a; b`, web/b.test.ts::c; ::d") == [
        ("web/a.test.ts", "a; b"), ("web/b.test.ts", "c"), ("web/b.test.ts", "d")]


def test_a_criterion_struck_with_a_reason_needs_no_test(ev_mod):
    """#234 (Kenni #2606): a struck or prose-only criterion still demanded a test."""
    mod, _out = ev_mod
    req = mod.required_criteria
    assert req("AC-1 AC-2\nAC-2: struck — merged into AC-1\n", "") == {"1"}
    assert req("AC-1 AC-3\n- AC-3: dropped: the owner cut it\n", "") == {"1"}
    # no reason, a placeholder reason, a bare strike-through: still required
    assert req("AC-1\nAC-1: struck\n", "") == {"1"}
    assert req("AC-1\nAC-1: struck — <reason>\n", "") == {"1"}
    assert req("~~AC-1~~ dropped\n", "") == {"1"}
    # a plan line cannot quietly drop a criterion its spec still names; the spec can
    assert req("AC-4: struck — not needed\n", "- AC-4: answers\n") == {"4"}
    assert req("", "- AC-5: logs\nAC-5: struck — owner decided on 2026-10-15\n") == set()
    # a hyphen glued to the word is prose, not a strike (plan review)
    assert req("- AC-3: Dropped-connection retry: When the socket drops, retry.\n", "") == {"3"}
    assert req("- AC-4: Struck-through text renders as deleted.\n", "") == {"4"}
    assert req("AC-1 AC-6\nAC-6: dropped - the owner cut it\n", "") == {"1"}
    assert mod.struck_criteria("AC-1 AC-2\nAC-2: struck — merged into AC-1\n", "") == {"2"}
    # a capitalised title is a criterion, `--` separates like `-` (refute)
    assert req("- AC-3: Dropped: When the socket drops, the client shall retry.\n", "") == {"3"}
    assert req("- AC-3: Struck — When text is struck, it renders as deleted.\n", "") == {"3"}
    assert req("AC-1 AC-7\nAC-7: struck -- the owner cut it\n", "") == {"1"}
    assert req("AC-1 AC-8\nAC-8: struck — todo\n", "") == {"1", "8"}


def test_a_struck_criterion_end_to_end(repo):
    plan = repo / ".process-work/plans/2026-10-14-widget.md"
    plan.write_text(PLAN + "- AC-2: When y, the widget shall log.\n\nAC-2: struck — logging moved to #8\n")
    _git(repo, "commit", "-qam", "docs: strike AC-2")
    # the strike leaves a trace: the code review's report confirms it (plan review)
    r = _attest(repo, "--with", _report(repo))
    assert r.returncode == 1 and "AC-2 is struck" in r.stderr and "`AC-2: struck`" in r.stderr
    confirmed = "- AC-1: `tests/test_widget.py::test_widget`\n- AC-2: struck — seen, logging is #8\n"
    assert _attest(repo, "--with", _report(repo, confirmed)).returncode == 0
    # a confirming line that names a test anyway: the test must stand (refute)
    claimed = confirmed.replace("seen, logging is #8", "`tests/test_widget.py::test_missing`")
    r = _attest(repo, "--with", _report(repo, claimed))
    assert r.returncode == 1 and "AC-2 is struck, yet its report line names a test" in r.stderr
    # a capitalised or glued mark confirms nothing; prose with `::` names no test (code review)
    for line in ("- AC-2: Struck-through text\n", "- AC-2: Struck\n"):
        r = _attest(repo, "--with", _report(repo, confirmed.splitlines(True)[0] + line))
        assert r.returncode == 1 and "the report confirms the strike" in r.stderr, line
    prose = confirmed.replace("seen, logging is #8", "replaced by std::vector use")
    assert _attest(repo, "--with", _report(repo, prose)).returncode == 0


@pytest.mark.parametrize(("rows", "problem"), [
    ([{"kind": "refute", "when": {"tier_from": 3}}], None),
    ({"kind": "refute"}, "list of rows"),
    ([{"kind": "nope", "when": {"tier_from": 3}}], "kind must be one of"),
    ([{"kind": "refute", "when": {}}], "when must name"),
    ([{"kind": "refute", "when": {"tier": 3}}], "when must name"),
    ([{"kind": "refute", "when": {"tier_from": True}}], "when.tier_from must be int"),
    ([{"kind": "owner-decision", "when": {"waived": True}, "skippable": True}], "cannot be skipped"),
    # cross-model review: a refute on `waived` was owed by no reader — refused, not dead
    ([{"kind": "refute", "when": {"waived": True}}], "owner-decision only"),
])
def test_required_records_rows_are_validated(ev_mod, rows, problem):
    """#282: a malformed table is a policy problem, never a silent pass."""
    import required_records
    got = required_records.rows_problem(rows)
    assert (got is None) if problem is None else (problem in got), got


def test_the_owner_decision_cannot_be_skipped(ev_mod):
    import required_records
    rows = [{"kind": "owner-decision", "when": {"waived": True}}]
    owed, _ = required_records.owed(rows, {"waived": True}, set(), {"owner-decision"})
    assert [o.kind for o in owed] == ["owner-decision"]


def test_every_int_fact_is_a_threshold_and_a_bool_stays_equality(ev_mod):
    """v2.77 B1: `blocked_rounds` 3 at a row's 2 is owed — the type comes from FACTS, so a
    new int fact cannot fall back to equality; a bool fact is no number (True >= False)."""
    import required_records
    holds = required_records._holds
    assert required_records.FACTS["blocked_rounds"] is int
    assert {"replan", "class-test"} <= set(required_records.KINDS)
    assert holds({"blocked_rounds": 2}, {"blocked_rounds": 3}) is True
    assert holds({"blocked_rounds": 2}, {"blocked_rounds": 2}) is True
    assert holds({"blocked_rounds": 2}, {"blocked_rounds": 1}) is False
    assert holds({"blocked_rounds": 1}, {"blocked_rounds": None}) is None
    assert holds({"gate_code": False}, {"gate_code": True}) is False
    assert holds({"gate_code": True}, {"gate_code": True}) is True
    assert required_records.rows_problem([{"kind": "replan", "when": {"blocked_rounds": 2}},
                                          {"kind": "class-test", "when": {"blocked_rounds": 1}}]) is None


def test_replan_and_root_cause_grammar(ev_mod):
    """v2.77 B4: `REPLAN work=<id> round=<r>: increment|rebuild — <why>` is a record; a
    ROOT-CAUSE line splits into cause, sites and the tests after them."""
    import check_review as cr
    line = "REPLAN work=v2.77 round=2: rebuild — fix passes over git ranges did not hold"
    m = cr.REPLAN_LINE.search(line)
    assert m and (m.group("work"), m.group("round"), m.group("mode")) == ("v2.77", "2", "rebuild")
    assert cr.REPLAN_LINE.search("- REPLAN work=7 round=3: increment — one owner, one more case")
    for bad in ("REPLAN work=<id> round=2: rebuild — x", "REPLAN work=7 round=2: increment|rebuild — x",
                "REPLAN work=7 round=2: rewrite — x", "REPLAN work=7 round=2: rebuild — <reason>",
                "REPLAN work=7 round=2: rebuild", "    REPLAN work=7 round=2: rebuild — code block"):
        assert not cr.REPLAN_LINE.search(bad), bad
    assert cr._record_line(line)
    assert cr.records_only("# Plan\n\ntier: 2\n", f"# Plan\n\ntier: 2\n\n{line}\n")
    for kind in ("replan", "class-test"):
        m = cr.SKIP_LINE.search(f"skipped {kind} work=7: blocked before v2.77")
        assert m and m.group("kind") == kind
    parts = cr.root_cause_parts
    assert parts("the guard read a stale flag — sites: guard.py:12, sync.py:40 — tests/t.py::test_a") == (
        "the guard read a stale flag", "guard.py:12, sync.py:40", "tests/t.py::test_a")
    assert parts("x — sites: a.ts — web/a.test.ts::adds — and carries") == (
        "x", "a.ts", "web/a.test.ts::adds — and carries")
    assert parts("refuted block — sites: none — the finding misread the guard") == (
        "refuted block", "none", "the finding misread the guard")
    assert parts("add subtracted — test_calc.py::test_add") == ("add subtracted", None, "")
    m = cr.ROOT_CAUSE_LINE.search("ROOT-CAUSE work=7 round=1: cause — sites: a.py — t.py::test_a\n")
    assert m.group("text") == "cause — sites: a.py — t.py::test_a"


def test_another_issues_criterion_is_cited_qualified_and_not_required(ev_mod):
    """#287 (Kenni #2687): a plan citing another issue's criterion made attest ask for it.
    Only the qualified form `#N/AC-<id>` is a citation; prose cannot tell "another issue's
    AC-11" from an own criterion with its origin, so a bare id stays the plan's own."""
    mod, _out = ev_mod
    req, foreign = mod.required_criteria, mod.foreign_criteria
    own = "issue: #7\n\n- AC-1: When x, the widget shall answer 42.\n"
    for line in ("Die Ablehnungsmenge des iOS-Prädikats aus #1918/AC-4.",
                 "dsh läuft nur bis zur #2659/AC-4-Messung.", "As in owner/repo#9/AC-4."):
        assert req(own + line + "\n", "") == {"1"} and foreign(own + line + "\n", "") == {"4"}, line
    # a bare mention keeps the id the plan's own, whatever issue stands beside it (fail closed)
    assert req(own + "dsh runs only up to the AC-4 measurement (#2659).\n", "") == {"1", "4"}
    assert req(own + "#1918/AC-4 and AC-4 here too.\n", "") == {"1", "4"}
    assert foreign(own + "#1918/AC-4 and AC-4 here too.\n", "") == set()  # no note for a required id
    # delta round 5: a bare hyphen compound keeps the id too
    assert req(own + "#2659/AC-4 cited. Die AC-4-Messung bleibt.\n", "") == {"1", "4"}
    # the own issue by its number, in every form check_review reads: any repository, any
    # decoration — the plan's own (fail closed; delta rounds 5–6)
    for decl in ("#7", "me/repo#7", "[#7](https://github.com/me/repo/issues/7)", "<#7>", "**#7**", "#7,"):
        for cite in ("#7/AC-4", "me/repo#7/AC-4", "other/repo#7/AC-4"):
            assert req(f"issue: {decl}\nSee {cite}.\n", "") == {"4"}, (decl, cite)
    # the plan's own issue is no other one; a spec's criterion is the work's own
    assert req(own + "See #7/AC-4.\n", "") == {"1", "4"}
    assert req("issue: #7\nSee #9/AC-2.\n", "- AC-2: When a, b shall c.\n") == {"2"}


def test_attest_names_the_id_it_left_out(repo):
    """#287 AC-3: an id left out as foreign is named, never dropped in silence."""
    plan = repo / ".process-work/plans/2026-10-14-widget.md"
    plan.write_text(PLAN + "\ndsh runs only up to the #2659/AC-11 measurement.\n")
    _git(repo, "commit", "-qam", "docs: cite another issue")
    r = _attest(repo, "--with", _report(repo))
    assert r.returncode == 0, r.stderr
    assert "AC-11 not required" in r.stderr and "#<issue>/AC-11" in r.stderr, r.stderr
    # a bare mention stays required, and the refusal names the way out
    plan.write_text(PLAN + "\ndsh runs only up to the AC-11 measurement (#2659).\n")
    _git(repo, "commit", "-qam", "docs: bare mention")
    r = _attest(repo, "--with", _report(repo))
    assert r.returncode == 1 and "write it `#<issue>/AC-11`" in r.stderr, r.stderr


# --- v2.77: per blocked code round the branch adds, a class test; per follow-up block, a REPLAN

SHARD = f".process-work/journal/issue-7/{dt.date.today().isoformat()}.md"
OLDER_SHARD = f".process-work/journal/issue-7/{(dt.date.today() - dt.timedelta(days=1)).isoformat()}.md"
PLAN_FILE = ".process-work/plans/2026-10-14-widget.md"
CLASS_TEST = "has no class test for blocked round(s) "
REPLAN = " without a REPLAN line"


def _review(work, round_, verdict="block"):
    return (f"REVIEW work={work} tier=2 reviewer=lens model=claude-opus-5 "
            f"independence=bundle,non-implementing verdict={verdict} round={round_}")


def _append(repo, rel, *lines, commit=None):
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    old = p.read_text() if p.is_file() else "# 2026-10-14\n"
    p.write_text(old.rstrip("\n") + "\n\n" + "\n\n".join(lines) + "\n")
    if commit:
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", commit)


def _on_main(repo, rel, *lines):
    """Lines main gained (an earlier work of the issue, or anything); the branch rebases."""
    _git(repo, "checkout", "-q", "main")
    _append(repo, rel, *lines, commit="docs: on main")
    _git(repo, "checkout", "-q", "7-widget")
    _git(repo, "rebase", "-q", "main")


def _pass(repo, *extra, **kw):
    return _attest(repo, "--with", _report(repo), "--dry-run", *extra, **kw)


def test_an_uncommitted_older_shard_is_no_evidence(repo):
    """#308: a record in another day's shard counts only when it is committed — the
    attestation commits today's shard, not every shard the worktree happens to hold."""
    _append(repo, SHARD, _review("widget", 1), commit="docs: block")
    cause = _RC + "sites: none — refuted, the finding misread the guard"
    _append(repo, OLDER_SHARD, cause)
    r = _pass(repo)
    assert r.returncode == 1 and OLDER_SHARD in r.stderr, r.stderr
    assert "neither at" in r.stderr and "carried by this attestation" in r.stderr, r.stderr
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "docs: the cause")
    r = _pass(repo)
    assert r.returncode == 0, r.stderr


JOURNAL_ORIGIN_CASES = [
    # (name, shard, line, committed, refused) — the refusal follows the work-bound readers:
    # this work's ROOT-CAUSE or a skip of a kind the journal counts (class-test, replan)
    ("today's shard, own skip", SHARD,
     "skipped class-test work=widget: blocked before v2.77", "uncommitted", False),
    ("older shard, own skip, committed", OLDER_SHARD,
     "skipped class-test work=widget: blocked before v2.77", "commit", False),
    ("older shard, own skip, uncommitted", OLDER_SHARD,
     "skipped class-test work=widget: blocked before v2.77", "uncommitted", True),
    ("older shard, foreign skip, uncommitted", OLDER_SHARD,
     "skipped class-test work=unrelated: older work", "uncommitted", False),
    ("older shard, foreign root cause, uncommitted", OLDER_SHARD,
     "ROOT-CAUSE work=unrelated round=1: another work — sites: none — refuted", "uncommitted", False),
    ("older shard, own uncounted skip, uncommitted", OLDER_SHARD,
     "skipped ac-trace work=widget: not a journal kind", "uncommitted", False),
]


@pytest.mark.parametrize("name,shard,line,committed,refused", JOURNAL_ORIGIN_CASES,
                         ids=[c[0] for c in JOURNAL_ORIGIN_CASES])
def test_a_journal_refusal_covers_only_this_works_counted_evidence(repo, name, shard, line,
                                                                  committed, refused):
    """#308 review R1: the guard reads the same set as `_root_caused`/`_skips` — this
    work's ROOT-CAUSE and the skips the journal may count. Foreign work and kinds read
    only from the plan stay invisible, at any origin."""
    _append(repo, shard, line, commit="docs: evidence" if committed == "commit" else None)
    r = _pass(repo)
    if refused:
        assert r.returncode == 1 and shard in r.stderr and "neither at" in r.stderr, r.stderr
    else:
        assert r.returncode == 0, r.stderr


def test_todays_journal_evidence_is_committed_with_the_attestation(repo):
    """#308: the one shard the attestation writes is part of its commit — evidence
    appended there before the pass must land in the repository with the REVIEW line."""
    _append(repo, SHARD, _review("widget", 1), commit="docs: block")
    _append(repo, SHARD, _RC + "sites: none — refuted, the finding misread the guard")
    r = _attest(repo, "--with", _report(repo), "--commit")
    assert r.returncode == 0, r.stderr
    assert "ROOT-CAUSE work=widget round=1" in _git(repo, "show", f"HEAD:{SHARD}")


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="needs symlinks")
def test_a_daily_symlink_does_not_carry_its_target(repo):
    """#308 R3: the snapshot dereferenced today's shard while the commit wrote its link
    path. The one file-set owner now refuses the symlink by name, before any read."""
    _append(repo, SHARD, _review("widget", 1), commit="docs: block")
    _append(repo, OLDER_SHARD, _RC + "sites: none — refuted, the finding misread the guard")
    target = repo / OLDER_SHARD
    (repo / SHARD).unlink()
    (repo / SHARD).symlink_to(Path(OLDER_SHARD).name)  # same issue shard directory
    r = _attest(repo, "--with", _report(repo), "--commit")
    assert r.returncode == 1, r.stderr
    assert SHARD in r.stderr and "symlink" in r.stderr, r.stderr
    assert not _git(repo, "diff", "--cached", "--name-only")
    assert target.is_file() and not target.is_symlink()
    assert OLDER_SHARD not in _git(repo, "ls-files")


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="needs symlinks")
def test_a_daily_shard_symlinked_to_a_tracked_file_is_refused(repo):
    """A link to a tracked shard is still a link: the evidence is in that path, not
    behind today's name — refused, never followed."""
    _append(repo, SHARD, _review("widget", 1), commit="docs: block")
    tracked = ".process-work/journal/issue-7/2026-01-01.md"
    _append(repo, tracked, "skipped class-test work=widget: an old shard",
            commit="docs: tracked evidence")
    (repo / SHARD).unlink()
    (repo / SHARD).symlink_to(Path(tracked).name)
    r = _attest(repo, "--with", _report(repo), "--commit")
    assert r.returncode == 1, r.stderr
    assert SHARD in r.stderr and "symlink" in r.stderr, r.stderr
    assert _git(repo, "show", f"HEAD:{tracked}").strip() != ""


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="needs symlinks")
def test_a_symlinked_journal_parent_is_refused(repo, tmp_path):
    """No parent of the path may be a symlink: it could lead outside the shard home."""
    outside = tmp_path / "outside-journal"
    outside.mkdir()
    (outside / f"{dt.date.today().isoformat()}.md").write_text(
        _review("widget", 1) + "\n" + _RC + "sites: none — outside\n")
    (repo / ".process-work/journal").mkdir(parents=True, exist_ok=True)
    (repo / ".process-work/journal/issue-7").symlink_to(outside, target_is_directory=True)
    r = _attest(repo, "--with", _report(repo), "--commit")
    assert r.returncode == 1, r.stderr
    assert SHARD in r.stderr and "symlink" in r.stderr, r.stderr
    assert not _git(repo, "diff", "--cached", "--name-only")


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="needs symlinks")
def test_a_symlinked_with_report_is_refused(repo):
    """`--with` carries a record path the commit names; a symlink there is refused, not
    silently replaced by the file it points at."""
    real = _report(repo)
    linked = ".process-work/reviews/widget-linked.md"
    (repo / linked).symlink_to(Path(real).name)
    r = _attest(repo, "--with", linked, "--commit")
    assert r.returncode == 1, r.stderr
    assert linked in r.stderr and "symlink" in r.stderr, r.stderr
    assert not _git(repo, "diff", "--cached", "--name-only")


def test_a_hardlinked_report_is_carried_by_its_own_path(repo):
    """A hardlink is a plain file at its own path; the bytes at that path are committed
    with the attestation, so the evidence and the commit agree."""
    real = _report(repo)
    linked = ".process-work/reviews/widget-linked.md"
    os.link(repo / real, repo / linked)
    r = _attest(repo, "--with", linked, "--commit")
    assert r.returncode == 0, r.stderr
    assert linked in _git(repo, "show", "--name-only", "--format=", "HEAD")


_AFTER_SNAPSHOT = '''\
import json, os, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import attest
mutations = json.loads(sys.argv[2])
taken = attest.attestation_files


def taken_then_mutated(*args, **kwargs):
    out = taken(*args, **kwargs)
    for rel, op, text in mutations:
        p = Path(rel)
        old = p.read_text(encoding="utf-8") if p.is_file() else ""
        new = {"add": old + text,
               "remove": "".join(ln for ln in old.splitlines(True) if text not in ln),
               "replace": text}[op]
        fresh = p.with_name(p.name + ".new")
        fresh.write_text(new, encoding="utf-8")
        os.replace(fresh, p)  # "replace" is a new file at the path, not an edit
    return out


attest.attestation_files = taken_then_mutated
sys.argv = ["attest.py", *sys.argv[3:]]
raise SystemExit(attest.main())
'''


def _attest_after_snapshot(repo, tmp_path, mutations, *extra):
    """attest.py with the files changed right after `attestation_files` took the snapshot:
    the TOCTOU window between the check and the commit (R4/R5). A hook cannot show it:
    `commit-tree` runs none."""
    runner = tmp_path / "after_snapshot.py"
    runner.write_text(_AFTER_SNAPSHOT, encoding="utf-8")
    base, head = _range(repo)
    cmd = [sys.executable, str(runner), str(repo / "scripts/process"), json.dumps(mutations),
           "--work", "widget", "--tier", "2", "--model", "claude-opus-5",
           "--independence", "bundle,non-implementing", "--verdict", "pass",
           "--base", base, "--head", head, *extra, "."]
    return subprocess.run(cmd, cwd=repo, capture_output=True, text=True)


def test_evidence_removed_after_the_check_is_still_committed(repo, tmp_path):
    """#308 R4: validation read today's shard, then `git add`/`git commit` read the
    worktree again. A line removed after the check made the commit a pass without its
    evidence. The commit now comes from the checked bytes."""
    _append(repo, SHARD, _review("widget", 1), commit="docs: block")
    _append(repo, SHARD, _RC + "sites: none — refuted, the finding misread the guard")
    r = _attest_after_snapshot(repo, tmp_path, [(SHARD, "remove", "ROOT-CAUSE work=widget")],
                               "--with", _report(repo), "--commit")
    assert r.returncode == 0, r.stderr
    assert _RC in _git(repo, "show", f"HEAD:{SHARD}")


def test_with_shard_changed_after_the_check_is_still_committed(repo, tmp_path):
    """#308 R4, the same window for an older `--with` shard: what the evidence check saw
    is what the attestation commits."""
    _append(repo, SHARD, _review("widget", 1), commit="docs: block")
    _append(repo, OLDER_SHARD, _RC + "sites: none — refuted, the finding misread the guard",
            commit="docs: the cause")
    r = _attest_after_snapshot(repo, tmp_path, [(OLDER_SHARD, "remove", "ROOT-CAUSE work=widget")],
                               "--with", _report(repo), "--with", OLDER_SHARD, "--commit")
    assert r.returncode == 0, r.stderr
    assert _RC in _git(repo, "show", f"HEAD:{OLDER_SHARD}")


AC_TRACE_SKIP = "skipped ac-trace work=widget: the widget has no criterion left to trace"


def test_a_plan_record_appended_after_the_snapshot_does_not_count(repo, tmp_path):
    """#308 R5: `_plan` read the plan riding `--with` from the worktree and index again.
    A skip appended after the snapshot authorized a committed pass whose commit held
    neither the skip nor a report. Only the checked bytes count."""
    r = _attest_after_snapshot(repo, tmp_path, [(PLAN_FILE, "add", "\n" + AC_TRACE_SKIP + "\n")],
                               "--with", PLAN_FILE, "--commit")
    assert r.returncode == 1 and "without its review report" in r.stderr, r.stderr
    assert "verdict=pass" not in _git(repo, "log", "-p", "-1")


# (reader, path, the evidence it reads, the extra args) — each reader of the snapshot
_CAUSE = ("ROOT-CAUSE work=widget round=1: the guard read a stale flag — sites: none — "
          "refuted, the finding misread the guard")
SNAPSHOT_READERS = {
    "journal today": (SHARD, _CAUSE, ()),
    "journal older --with": (OLDER_SHARD, _CAUSE, ("--with", OLDER_SHARD)),
    "plan --with": (PLAN_FILE, AC_TRACE_SKIP, ("--with", PLAN_FILE)),
    "report": (".process-work/reviews/widget.md", "- AC-1: `tests/test_widget.py::test_widget`", ()),
}


@pytest.mark.parametrize("mutation", ["add", "remove", "replace"])
@pytest.mark.parametrize("reader", list(SNAPSHOT_READERS))
def test_a_change_after_the_snapshot_never_reaches_the_pass(repo, tmp_path, reader, mutation):
    """#308 R5: one snapshot (path -> bytes) is taken once; every reader reads it and the
    commit writes it. A change after it — a line added, a line removed, the file replaced —
    is either not seen (the commit holds the checked bytes) or refused; it never counts.
    "add": the evidence appears only after the snapshot, so the pass is refused.
    "remove"/"replace": the evidence was checked, so the commit carries it."""
    rel, evidence, extra = SNAPSHOT_READERS[reader]
    reader_is_journal = rel in (SHARD, OLDER_SHARD)
    if reader_is_journal:
        _append(repo, SHARD, _review("widget", 1), commit="docs: block")
    reader_is_report = rel == ".process-work/reviews/widget.md"
    report = _report(repo, "" if reader_is_report and mutation == "add" else
                     "- AC-1: `tests/test_widget.py::test_widget`\n")
    with_report = () if rel == PLAN_FILE else ("--with", report)
    if mutation != "add" and not reader_is_report:
        _append(repo, rel, evidence)
    elif rel == OLDER_SHARD:
        _append(repo, rel, "skipped class-test work=unrelated: another work's shard")
    snapshot = (repo / rel).read_text(encoding="utf-8")
    change = {"add": "\n" + evidence + "\n", "remove": evidence.split(" —")[0].split(": ")[0],
              "replace": "# replaced after the check\n"}[mutation]
    r = _attest_after_snapshot(repo, tmp_path, [(rel, mutation, change)],
                               *with_report, *extra, "--commit")
    if mutation == "add":
        assert r.returncode == 1, r.stdout + r.stderr
        assert "verdict=pass" not in _git(repo, "log", "-p", "-1")
        return
    if rel == PLAN_FILE and mutation == "replace":
        # the plan's own lines changed in the worktree: E1 refuses (`differs`) — a refusal
        # reader only; nothing of the replaced file is counted or committed
        assert r.returncode == 1 and "holds more than records appended" in r.stderr, r.stderr
        assert "verdict=pass" not in _git(repo, "log", "-p", "-1")
        return
    assert r.returncode == 0, r.stderr
    committed = _git(repo, "show", f"HEAD:{rel}")
    if rel == SHARD:
        assert committed.startswith(snapshot.rstrip("\n")) and "verdict=pass" in committed
    else:
        assert committed == snapshot.rstrip("\n")
    assert "replaced after the check" not in committed


@pytest.mark.parametrize("duplicate", ["today's shard", "today's shard as ./path", "report twice",
                                       "plan with --with and --archive"])
def test_a_path_named_twice_is_carried_once(repo, duplicate):
    """#308 R5: `--with <today's shard>` put the path twice in the file set; the second,
    old bytes won and the commit held no new REVIEW line. A path is carried once."""
    _append(repo, SHARD, _review("widget", 1), commit="docs: block")
    _append(repo, SHARD, _RC + "sites: none — refuted, the finding misread the guard")
    report = _report(repo)
    extra = {"today's shard": ("--with", SHARD),
             "today's shard as ./path": ("--with", "./" + SHARD),
             "report twice": ("--with", report),
             "plan with --with and --archive": ("--with", PLAN_FILE, "--archive", PLAN_FILE),
             }[duplicate]
    if duplicate.startswith("plan"):
        _append(repo, PLAN_FILE, "DECISION 2026-10-24 agent: rides the archive")
    r = _attest(repo, "--with", report, *extra, "--commit")
    assert r.returncode == 0, r.stderr
    shard = _git(repo, "show", f"HEAD:{SHARD}")
    assert "verdict=pass" in shard and _RC in shard
    assert report in _git(repo, "show", "--name-only", "--format=", "HEAD")
    if duplicate.startswith("plan"):
        archived = _git(repo, "show", "--name-status", "--no-renames", "--format=", "HEAD")
        assert f"D\t{PLAN_FILE}" in archived, archived
        dest = next(ln.split("\t")[1] for ln in archived.splitlines()
                    if ln.startswith("A\t") and "archive" in ln)
        assert "rides the archive" in _git(repo, "show", f"HEAD:{dest}")


def test_an_archived_plans_records_come_from_the_snapshot(repo, tmp_path):
    """#308 R5: `--archive` read the plan from the worktree after the check and committed
    those bytes. The archived plan is part of the snapshot like any `--with` record."""
    _append(repo, PLAN_FILE, "DECISION 2026-10-24 agent: checked before the move")
    snapshot = (repo / PLAN_FILE).read_text(encoding="utf-8")
    r = _attest_after_snapshot(repo, tmp_path,
                               [(PLAN_FILE, "add", "\nDECISION 2026-10-24 agent: added after\n")],
                               "--with", _report(repo), "--archive", PLAN_FILE, "--commit")
    if r.returncode:
        assert "verdict=pass" not in _git(repo, "log", "-p", "-1")
        return
    archived = _git(repo, "show", "--name-status", "--no-renames", "--format=", "HEAD")
    dest = next(ln.split("\t")[1] for ln in archived.splitlines()
                if ln.startswith("A\t") and "archive" in ln)
    assert _git(repo, "show", f"HEAD:{dest}") == snapshot.rstrip("\n")


def test_a_path_with_two_byte_sets_is_refused(ev_mod, monkeypatch):
    """Two reads of one path that disagree cannot both be the snapshot: refused by name."""
    mod, out = ev_mod
    reads = iter([b"one\n", b"two\n"])
    monkeypatch.setattr(mod, "_repo_file", lambda root, p, may_be_missing: (
        Path(os.path.normpath(p)).relative_to(root.resolve()).as_posix(), next(reads)))
    out = out.resolve()
    files, problems = mod.attestation_files(out, out / SHARD, [out / SHARD])
    assert files == [(SHARD, b"one\n")]
    assert any(SHARD in p and "twice" in p for p in problems), problems


def _git_dir(repo):
    return repo / _git(repo, "rev-parse", "--git-dir")


@pytest.mark.parametrize("lock", ["index.lock", "refs/heads/7-widget.lock"])
def test_a_failed_index_or_ref_update_fails_and_loses_nothing(repo, lock):
    """#308 R5: the index was reset after the ref moved and its failure ignored — exit 0,
    then the journal and report showed as staged deletions. Now a failing step exits
    non-zero, HEAD names a commit only when the index matches it, and nothing is lost."""
    report = _report(repo)
    before = _git(repo, "rev-parse", "HEAD")
    held = _git_dir(repo) / lock
    held.write_text("")
    try:
        r = _attest(repo, "--with", report, "--commit")
    finally:
        held.unlink()
    assert r.returncode != 0, r.stdout + r.stderr
    assert _git(repo, "rev-parse", "HEAD") == before
    assert "verdict=pass" in (repo / SHARD).read_text() and (repo / report).is_file()
    staged = _git(repo, "diff", "--cached", "--name-status")
    assert not any(ln.startswith("D") for ln in staged.splitlines()), staged


def test_after_a_commit_the_index_matches_head(repo):
    """The attestation's paths are staged as committed; nothing shows as a staged change."""
    r = _attest(repo, "--with", _report(repo), "--commit")
    assert r.returncode == 0, r.stderr
    assert _git(repo, "diff", "--cached", "--name-status") == ""


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="needs symlinks")
def test_a_symlinked_override_journal_dir_is_refused(repo):
    """#308 R4: `journal_dir.resolve()` removed a symlink parent before the path owner
    saw it. The lexical path is checked first, so the alias is refused by name."""
    actual = repo / "docs/journal"
    actual.mkdir(parents=True)
    (repo / ".process-work/journal").mkdir(parents=True, exist_ok=True)
    (repo / ".process-work/journal/alias").symlink_to(actual, target_is_directory=True)
    r = _attest(repo, "--with", _report(repo), "--journal-dir",
                ".process-work/journal/alias", "--commit")
    assert r.returncode == 1, r.stderr
    assert "alias" in r.stderr and "symlink" in r.stderr, r.stderr
    assert not _git(repo, "diff", "--cached", "--name-only")


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="needs symlinks")
def test_a_symlinked_default_journal_dir_is_refused(repo):
    """#308 R4: the default journal directory is no exception — a link there is
    checked as a path, not silently replaced by its target."""
    shard_dir = repo / ".process-work/journal"
    actual = repo / "docs/journal"
    actual.parent.mkdir(parents=True, exist_ok=True)
    if shard_dir.exists():
        shard_dir.rename(actual)
    else:
        actual.mkdir(parents=True)
    shard_dir.symlink_to(actual, target_is_directory=True)
    r = _attest(repo, "--with", _report(repo), "--commit")
    assert r.returncode == 1, r.stderr
    assert ".process-work/journal" in r.stderr and "symlink" in r.stderr, r.stderr
    assert not _git(repo, "diff", "--cached", "--name-only")


EVIDENCE_QUOTATIONS = [
    ("four spaces", lambda line: "    " + line),
    ("a tab", lambda line: "\t" + line),
    ("a fence", lambda line: "```\n" + line + "\n```"),
    ("an HTML comment", lambda line: "<!--\n" + line + "\n-->"),
]


@pytest.mark.parametrize("form,quote", EVIDENCE_QUOTATIONS, ids=[c[0] for c in EVIDENCE_QUOTATIONS])
@pytest.mark.parametrize("kind,line", [
    ("a ROOT-CAUSE line",
     "ROOT-CAUSE work=widget round=1: the guard read a stale flag — sites: none — "
     "refuted, the finding misread the guard"),
    ("a class-test skip", "skipped class-test work=widget: blocked before v2.77"),
], ids=["root-cause", "skip"])
def test_a_committed_quotation_is_no_origin_for_an_uncommitted_evidence_line(
        repo, kind, line, form, quote):
    """#308 R2: the origin reader validated nothing — it normalized the committed
    quotation away and matched the real, uncommitted line against it. Both sides now
    run the same evidence reader, so a quotation at head grants no origin."""
    _append(repo, SHARD, _review("widget", 1), commit="docs: block")
    _append(repo, OLDER_SHARD, quote(line), commit="docs: the quoted example")
    _append(repo, OLDER_SHARD, line)  # the real line, never committed
    r = _pass(repo)
    assert r.returncode == 1, r.stderr
    assert OLDER_SHARD in r.stderr and "neither at" in r.stderr, r.stderr


@pytest.mark.parametrize("prefix", ["", "   ", "- ", "* "], ids=["raw", "three-spaces", "bullet", "star"])
def test_a_committed_evidence_line_still_counts_in_the_forms_the_reader_accepts(repo, prefix):
    """The same reader on the attestation's snapshot accepts a real record however it
    is written in the journal (a list marker or up to three spaces); four spaces or a
    tab are a quotation, not a record."""
    _append(repo, SHARD, _review("widget", 1), commit="docs: block")
    _append(repo, SHARD, prefix + "skipped class-test work=widget: annotated in the journal",
            commit="docs: the journal skip")
    r = _pass(repo)
    assert r.returncode == 0, r.stderr


def test_a_block_already_at_the_fork_point_is_no_round_of_this_branch(repo):
    """An earlier work of the same issue blocked round 1 on main: this branch's rounds are 2
    and 3 — round 2 is its first (no REPLAN), and round 1 owes it no class test."""
    _on_main(repo, ".process-work/journal/2026-01-01.md", _review("7", 1))
    _append(repo, SHARD, _review("widget", 2), _review("widget", 3), commit="docs: two blocks")
    r = _pass(repo)
    assert r.returncode == 1, r.stderr
    assert "blocked round(s) 3" + REPLAN in r.stderr, r.stderr
    assert CLASS_TEST + "2 (no ROOT-CAUSE line), 3 (no ROOT-CAUSE line)" in r.stderr, r.stderr


def test_a_block_of_the_branch_still_counts_after_a_rebase(repo):
    _append(repo, SHARD, _review("widget", 1), commit="docs: block")
    _on_main(repo, "README.md", "Moved on.")
    r = _pass(repo)
    assert r.returncode == 1 and CLASS_TEST + "1 (no ROOT-CAUSE line)" in r.stderr, r.stderr


def test_an_uncommitted_block_counts_as_the_round_counter_counts_it(repo):
    _append(repo, SHARD, _review("widget", 1))
    r = _pass(repo)
    assert r.returncode == 1 and CLASS_TEST + "1 (no ROOT-CAUSE line)" in r.stderr, r.stderr


def test_lines_compact_journal_moved_on_the_branch_stay_old(repo):
    """Compared by content, not by path: a folded shard's lines are no new blocks."""
    _on_main(repo, ".process-work/journal/2026-01-01.md", _review("7", 1))
    subprocess.run([sys.executable, "scripts/process/compact_journal.py", ".", "--weeks", "1", "--apply"],
                   cwd=repo, capture_output=True, text=True, check=True)
    assert _review("7", 1) in (repo / ".process-work/journal/archive/2026-01.md").read_text()
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "docs: compact the journal")
    _append(repo, SHARD, _review("widget", 2))
    r = _pass(repo)
    assert r.returncode == 1 and CLASS_TEST + "2 (no ROOT-CAUSE line)" in r.stderr, r.stderr
    assert REPLAN not in r.stderr, r.stderr


def test_an_unreadable_fork_point_refuses(repo):
    """No integration ref at all: the rounds the branch adds are unknown — refused, not 0."""
    base, head = _range(repo)
    _append(repo, SHARD, _review("widget", 1))
    _git(repo, "branch", "-D", "main")
    r = subprocess.run([sys.executable, str(repo / "scripts/process/attest.py"), "--work", "widget", "--tier", "2",
                        "--model", "claude-opus-5", "--independence", "bundle,non-implementing",
                        "--verdict", "pass", "--base", base, "--head", head, "--with", _report(repo),
                        "--dry-run", "."], cwd=repo, capture_output=True, text=True)
    assert r.returncode == 1 and "fork point of the head cannot be read" in r.stderr, r.stderr


def test_the_fork_point_decides_in_gather(repo, monkeypatch):
    """An ambiguous fork (`GitReadError`) is unknown; a head on the integration ref itself
    adds no round of its own."""
    base, head = _range(repo)
    sys.path.insert(0, str(repo / "scripts/process"))
    names = ("attest_evidence", "check_review", "dispatch", "report", "process_git", "required_records")
    try:
        for name in names:
            sys.modules.pop(name, None)
        mod = importlib.import_module("attest_evidence")
        kw = dict(work="widget", ids={"widget"}, tier=2, verdict="pass", independence="bundle,non-implementing",
                  plan_review=False, model="claude-opus-5", reports=[], blocks=[(1, _review("widget", 1))])
        assert mod.gather(repo, base=base, head=head, **kw).blocked_rounds == 1
        assert mod.gather(repo, base=base, head=base, **kw).blocked_rounds == 0  # main's own head

        def ambiguous(*_a, **_k):
            raise mod.GitReadError("criss-cross")
        monkeypatch.setattr(mod, "merge_base", ambiguous)
        ev = mod.gather(repo, base=base, head=head, **kw)
        assert ev.blocked_rounds is None
        assert any("fork point of the head cannot be read" in p for p in mod.decide(ev)), mod.decide(ev)
    finally:
        sys.path.remove(str(repo / "scripts/process"))
        for name in names:
            sys.modules.pop(name, None)


@pytest.mark.parametrize("earlier", ["skipped class-test work=7: an earlier work, blocked before v2.77",
                                     "ROOT-CAUSE work=7 round=1: an earlier cause — sites: none — refuted"])
def test_an_earlier_works_journal_record_on_main_relieves_nothing(repo, earlier):
    _on_main(repo, ".process-work/journal/issue-7/2026-01-01.md", earlier)
    _append(repo, SHARD, _review("widget", 1))
    r = _pass(repo)
    assert r.returncode == 1 and CLASS_TEST + "1 (no ROOT-CAUSE line)" in r.stderr, r.stderr
    # the same kind of line, new on this branch, is this work's record
    _append(repo, SHARD, earlier.replace("earlier", "this"))
    r = _pass(repo)
    assert r.returncode == 0, r.stderr


def test_replan_is_owed_per_follow_up_block_in_the_plan(repo):
    _append(repo, PLAN_FILE, "skipped class-test work=widget: this test pins the REPLAN row", commit="docs: skip")
    _append(repo, SHARD, _review("widget", 1))
    r = _pass(repo)
    assert r.returncode == 0, r.stderr  # one block: no follow-up yet
    _append(repo, SHARD, _review("widget", 2), _review("widget", 3))
    _append(repo, PLAN_FILE, "REPLAN work=widget round=2: increment — one owner, one more case",
            commit="docs: replan round 2")
    r = _pass(repo)
    assert r.returncode == 1 and "blocked round(s) 3" + REPLAN in r.stderr, r.stderr
    # in the journal it is no call of the plan
    _append(repo, SHARD, "REPLAN work=widget round=3: rebuild — the guard is the wrong owner")
    r = _pass(repo)
    assert r.returncode == 1 and "blocked round(s) 3" + REPLAN in r.stderr, r.stderr
    # appended after the plan's last line, riding the attestation
    _append(repo, PLAN_FILE, "REPLAN work=widget round=3: rebuild — the guard is the wrong owner")
    r = _pass(repo, "--with", PLAN_FILE)
    assert r.returncode == 0, r.stderr
    # a reasoned skip instead
    _git(repo, "checkout", "-q", "--", PLAN_FILE)
    _append(repo, PLAN_FILE, "skipped replan work=widget: blocked before v2.77", commit="docs: skip replan")
    r = _pass(repo)
    assert r.returncode == 0, r.stderr


_T = "def test_a():\n    assert True\n"
_RC = "ROOT-CAUSE work=widget round=1: the guard read a stale flag — "
CLASS_CASES = [
    ("only round 1 has one", [2], ("plan", _RC + "sites: none — refuted"), {},
     CLASS_TEST + "2 (no ROOT-CAUSE line)"),
    ("no sites", [], ("plan", _RC + "tests/test_widget.py::test_widget"), {},
     "1 (its ROOT-CAUSE line names no `sites:`"),
    ("no such test file", [], ("plan", _RC + "sites: widget.py:2 — tests/test_gone.py::test_widget"), {},
     "tests/test_gone.py"),
    ("sites none", [], ("plan", _RC + "sites: none — refuted, the finding misread the guard"), {}, None),
    ("the named test", [], ("plan", _RC + "sites: widget.py:2 — tests/test_widget.py::test_widget"), {}, None),
    ("a pytest id relative to backend/", [],
     ("plan", _RC + "sites: backend/calc.py:2 — tests/test_calc.py::test_a"), {"backend/tests/test_calc.py": _T},
     None),
    ("a JUnit reference", [], ("plan", _RC + "sites: web/calc.ts:3 — tests/calc.test.ts::adds two numbers"),
     {"tests/calc.test.ts": 'it("adds two numbers", () => {})\n'}, None),
    ("a title holding a dash", [],
     ("plan", _RC + "sites: web/calc.ts:3 — tests/calc.test.ts::adds — and carries"),
     {"tests/calc.test.ts": 'it("adds — and carries", () => {})\n'}, None),
    ("an ambiguous suffix", [], ("plan", _RC + "sites: a.py:1 — tests/test_x.py::test_a"),
     {"a/tests/test_x.py": _T, "b/tests/test_x.py": _T}, "several tracked files"),
    ("a line in the journal", [], ("journal", _RC + "sites: none — refuted, the finding misread the guard"), {},
     None),
    ("a skip in the journal", [], ("journal", "skipped class-test work=widget: blocked before v2.77"), {}, None),
]


@pytest.mark.parametrize("name,blocks,record,files,expected", CLASS_CASES, ids=[c[0] for c in CLASS_CASES])
def test_a_class_test_per_blocked_round(repo, name, blocks, record, files, expected):
    for rel, text in files.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text)
    _append(repo, SHARD, *(_review("widget", r) for r in [1, *blocks]), commit="feat: tests and blocks")
    r = _pass(repo)
    assert r.returncode == 1 and CLASS_TEST + "1 (no ROOT-CAUSE line)" in r.stderr, r.stderr
    where, line = record
    _append(repo, PLAN_FILE if where == "plan" else SHARD, line, commit="docs: record" if where == "plan" else None)
    r = _pass(repo)
    if expected is None:
        assert r.returncode == 0, r.stderr
    else:
        assert r.returncode == 1 and expected in r.stderr, r.stderr


def test_the_root_cause_row_reads_the_works_journal(repo):
    for i in range(3):
        (repo / "widget.py").write_text(f"def widget():\n    return 42  # {i}\n")
        _git(repo, "commit", "-qam", f"fix: widget {i}")
    r = _pass(repo)
    assert r.returncode == 1 and "has no ROOT-CAUSE line" in r.stderr, r.stderr
    _append(repo, SHARD, "ROOT-CAUSE work=widget round=1: one owner answered for two layers")
    r = _pass(repo)
    assert r.returncode == 0, r.stderr


def test_a_plan_review_pass_asks_no_code_rounds_records(repo):
    _append(repo, SHARD, _review("widget", 1), _review("widget", 2), commit="docs: blocks")
    r = _pass(repo)
    assert r.returncode == 1 and CLASS_TEST in r.stderr, r.stderr  # the code pass owes them
    r = _attest(repo, "--dry-run", plan_review=True)
    assert r.returncode == 0, r.stderr


# --- v2.77 refute round 1 ---------------------------------------------------------------

@pytest.mark.parametrize("kind", ["ac-trace", "cross-model", "refute"])
def test_a_journal_skip_lifts_only_the_round_duties(repo, kind):
    """Eine Skip-Zeile im Journal hebt nur `replan` und `class-test` auf — jede andere Art
    zählt wie vor v2.77 nur aus dem Plan (im Journal auch kommittiert nicht)."""
    tier, independence, report = "2", "bundle,non-implementing", _report(repo)
    if kind == "ac-trace":
        report = _report(repo, body="nothing\n")
    elif kind == "cross-model":
        (repo / PLAN_FILE).write_text(PLAN.replace("tier: 2", "tier: 3") + "\nREFUTE work=widget round=1: survives: x\n")
        tier, independence = "3", "bundle,non-implementing,single-family"
    else:
        (repo / "scripts/process/extra_gate.py").write_text("X = 1\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "feat: the case")
    line = f"skipped {kind} work=widget: a reason of the journal"
    _append(repo, SHARD, line)
    r = _attest(repo, "--with", report, "--dry-run", tier=tier, independence=independence)
    assert r.returncode == 1, r.stderr
    _append(repo, SHARD, line, commit="docs: the journal's skip, committed")
    r = _attest(repo, "--with", report, "--dry-run", tier=tier, independence=independence)
    assert r.returncode == 1, r.stderr
    # the plan's skip still lifts it
    _append(repo, PLAN_FILE, line.replace("journal", "plan"), commit="docs: the plan's skip")
    r = _attest(repo, "--with", report, "--dry-run", tier=tier, independence=independence)
    assert r.returncode == 0, r.stderr


def test_journal_skips_still_lift_replan_and_class_test(repo):
    _append(repo, SHARD, _review("widget", 1), _review("widget", 2), commit="docs: blocks")
    assert _pass(repo).returncode == 1
    _append(repo, SHARD, "skipped replan work=widget: blocked before v2.77",
            "skipped class-test work=widget: blocked before v2.77")
    r = _pass(repo)
    assert r.returncode == 0, r.stderr


def test_a_block_quoted_in_a_fence_on_main_does_not_hide_the_branchs_block(repo):
    """Die Fork-Seite liest wie die Arbeitsbaum-Seite: ein auf main im Fence zitierter
    REVIEW-Block ist kein Block des Forks — der echte Block des Branches zählt."""
    _on_main(repo, ".process-work/journal/2026-01-01.md", "```\n" + _review("widget", 1) + "\n```")
    _append(repo, SHARD, _review("widget", 1), commit="docs: block")
    r = _pass(repo)
    assert r.returncode == 1 and CLASS_TEST + "1 (no ROOT-CAUSE line)" in r.stderr, r.stderr


def test_a_skip_quoted_in_a_fence_on_main_does_not_hide_the_branchs_skip(repo):
    line = "skipped class-test work=widget: blocked before v2.77"
    _on_main(repo, ".process-work/journal/2026-01-01.md", "```\n" + line + "\n```")
    _append(repo, SHARD, _review("widget", 1), line)
    r = _pass(repo)
    assert r.returncode == 0, r.stderr


def test_a_commented_block_on_main_stays_a_block_of_the_fork(repo):
    """Der Rundenzähler liest einen auskommentierten REVIEW-Block im Journal mit; die
    Fork-Seite liest ihn genauso — er ist keine Runde dieses Branches."""
    _on_main(repo, ".process-work/journal/2026-01-01.md", "<!--\n" + _review("7", 1) + "\n-->")
    _append(repo, SHARD, _review("widget", 2), commit="docs: block")
    r = _pass(repo)
    assert r.returncode == 1, r.stderr
    assert CLASS_TEST + "2 (no ROOT-CAUSE line)" in r.stderr and REPLAN not in r.stderr, r.stderr


def test_the_attested_journal_dir_is_read_at_the_fork_too(repo):
    """`--journal-dir docs/journal`: die Skip-Zeile einer früheren Arbeit, schon auf main,
    ist alt — sie hebt die Pflicht dieses Branches nicht auf."""
    _on_main(repo, "docs/journal/2026-01-01.md", "skipped class-test work=7: an earlier work")
    _append(repo, "docs/journal/2026-10-14.md", _review("widget", 1), commit="docs: block")
    r = _pass(repo, "--journal-dir", "docs/journal")
    assert r.returncode == 1 and CLASS_TEST + "1 (no ROOT-CAUSE line)" in r.stderr, r.stderr


def test_sites_is_read_in_any_case(repo):
    _append(repo, SHARD, _review("widget", 1), commit="docs: block")
    _append(repo, PLAN_FILE, _RC + "Sites: none — refuted, the finding misread the guard", commit="docs: cause")
    r = _pass(repo)
    assert r.returncode == 0, r.stderr


def test_an_exact_path_that_refuses_falls_back_to_the_unique_suffix(repo):
    """pytest lief in backend/ (`tests/test_widget.py` dort); das Wurzelverzeichnis hat einen
    Namensvetter ohne diesen Test: der eindeutige Suffix-Treffer zählt."""
    (repo / "backend/tests").mkdir(parents=True)
    (repo / "backend/tests/test_widget.py").write_text("def test_other():\n    assert True\n")
    _append(repo, SHARD, _review("widget", 1), commit="feat: backend test and block")
    _append(repo, PLAN_FILE, _RC + "sites: backend/x.py:1 — tests/test_widget.py::test_other", commit="d")
    r = _pass(repo)
    assert r.returncode == 0, r.stderr
    # a test of that name nowhere: still refused, with the exact path's reason
    _append(repo, SHARD, _review("widget", 2), commit="d")
    _append(repo, PLAN_FILE, "REPLAN work=widget round=2: increment — one more case",
            "ROOT-CAUSE work=widget round=2: y — sites: a:1 — tests/test_widget.py::test_nope", commit="d")
    r = _pass(repo)
    assert r.returncode == 1 and "tests/test_widget.py has no test test_nope" in r.stderr, r.stderr


def test_sites_none_needs_a_reason(repo):
    _append(repo, SHARD, _review("widget", 1), commit="docs: block")
    _append(repo, PLAN_FILE, _RC + "sites: none", commit="docs: cause")
    r = _pass(repo)
    assert r.returncode == 1 and "`sites: none` without a reason" in r.stderr, r.stderr


def test_a_lowercase_todo_is_no_reason(repo, ev_mod):
    """`todo` in any case is a placeholder, after `sites: none —` and in a REPLAN line."""
    _append(repo, SHARD, _review("widget", 1), commit="docs: block")
    _append(repo, PLAN_FILE, _RC + "sites: none — todo", commit="docs: cause")
    r = _pass(repo)
    assert r.returncode == 1 and "`sites: none` without a reason" in r.stderr, r.stderr
    import check_review
    assert not check_review.REPLAN_LINE.search("REPLAN work=7 round=2: rebuild — todo")
    assert check_review.REPLAN_LINE.search("REPLAN work=7 round=2: rebuild — todos left over")
    # the skip, refute and root-cause readers share the guard (v2.77 cross-model review, round 2)
    assert not check_review.SKIP_LINE.search("skipped class-test work=7: todo")
    assert not check_review.SKIP_LINE.search("skipped class-test work=7: Todo")
    assert check_review.SKIP_LINE.search("skipped class-test work=7: todos left over")
    assert not check_review.REFUTE_LINE.search("REFUTE work=7 round=1: todo")
    assert not check_review.ROOT_CAUSE_LINE.search("ROOT-CAUSE work=7 round=1: todo")
    # a word that starts with todo is prose, as before; an uppercase TODO stays a placeholder
    assert check_review.REFUTE_LINE.search("REFUTE work=7 round=1: Todo-list order is lost")
    assert check_review.SKIP_LINE.search("skipped class-test work=7: todo-list only")
    assert not check_review.SKIP_LINE.search("skipped class-test work=7: TODO-later")
    assert not check_review.SKIP_LINE.search("skipped class-test work=7: todo: later")


def test_a_fork_line_with_list_marker_and_trailing_blanks_is_the_same_line(repo):
    """Verglichen wird der Inhalt: `- <Zeile>   ` auf main ist dieselbe Zeile wie die nackte
    Zeile auf dem Branch — die Skip-Zeile einer früheren Arbeit bleibt alt."""
    _on_main(repo, ".process-work/journal/2026-01-01.md", "- skipped class-test work=7: old   ")
    _append(repo, SHARD, _review("widget", 1), "skipped class-test work=7: old")
    r = _pass(repo)
    assert r.returncode == 1 and CLASS_TEST + "1 (no ROOT-CAUSE line)" in r.stderr, r.stderr
