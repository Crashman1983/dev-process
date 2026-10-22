"""red_evidence: the red-before/green-after proof, measured instead of typed (#124)."""
import subprocess
import sys
from pathlib import Path


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True).stdout.strip()


def _repo(render, tmp_path) -> tuple[Path, str]:
    """A repo with a bug committed (the ref before the fix), then the fix and its test."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _git(out, "init", "-q", "-b", "main")
    _git(out, "config", "user.email", "t@t")
    _git(out, "config", "user.name", "t")
    (out / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "base")
    before = _git(out, "rev-parse", "HEAD")
    _git(out, "checkout", "-q", "-b", "7-fix")
    (out / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (out / "test_calc.py").write_text(
        "from calc import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n\n\n"
        "def test_zero():\n    assert add(0, 0) == 0\n", encoding="utf-8")
    return out, before


def _tool(out: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(out / "scripts/process/red_evidence.py"), *args],
                          cwd=out, capture_output=True, text=True)


def _journal(out: Path) -> str:
    return "".join(p.read_text(encoding="utf-8") for p in (out / ".process-work/journal").rglob("*.md"))


def test_writes_the_measured_block_and_the_root_cause_line(render, tmp_path):
    out, before = _repo(render, tmp_path)

    r = _tool(out, "--work", "7", "--round", "1", "--before", before,
              "--cause", "add subtracted instead of adding", "--",
              sys.executable, "-m", "pytest", "test_calc.py")

    assert r.returncode == 0, r.stdout + r.stderr
    text = _journal(out)
    assert "exit=1" in text and "now: exit=0" in text
    assert "red before, green after (1): test_calc.py::test_add" in text  # test_zero: green both
    assert "ROOT-CAUSE work=7 round=1: add subtracted instead of adding — test_calc.py::test_add" in text


def test_the_root_cause_line_satisfies_attest(render, tmp_path):
    """The line it writes is the one attest.py asks for before the next round."""
    out, before = _repo(render, tmp_path)
    _tool(out, "--work", "7", "--round", "1", "--before", before, "--cause", "add subtracted",
          "--", sys.executable, "-m", "pytest", "test_calc.py")
    sys.path.insert(0, str(out / "scripts/process"))
    import importlib.util
    spec = importlib.util.spec_from_file_location("attest_re", out / "scripts/process/attest.py")
    attest = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(attest)

    assert attest.ROOT_CAUSE.search(_journal(out))


def _grammar(out: Path):
    """check_review's ROOT-CAUSE grammar and attest_evidence's test reader of this render."""
    import importlib
    names = ("check_review", "attest_evidence", "required_records", "process_git")
    sys.path.insert(0, str(out / "scripts/process"))
    try:
        for name in names:
            sys.modules.pop(name, None)
        return importlib.import_module("check_review"), importlib.import_module("attest_evidence")
    finally:
        sys.path.remove(str(out / "scripts/process"))
        for name in names:
            sys.modules.pop(name, None)


def _class_test(out: Path) -> tuple[str, str | None, list]:
    cr, ev = _grammar(out)
    m = cr.ROOT_CAUSE_LINE.search(_journal(out))
    cause, sites, tests = cr.root_cause_parts(m.group("text"))
    return cause, sites, ev.claimed_tests(tests)


def test_sites_write_the_class_test_form_and_read_back_pytest(render, tmp_path):
    """v2.77 B5: `--sites` writes `<cause> — sites: <sites> — <tests>`, and the reader
    attest uses gets the measured node ids back."""
    out, before = _repo(render, tmp_path)
    r = _tool(out, "--work", "7", "--round", "1", "--before", before, "--cause", "add subtracted",
              "--sites", "calc.py:2, calc.py:sub", "--", sys.executable, "-m", "pytest", "test_calc.py")
    assert r.returncode == 0, r.stdout + r.stderr
    assert ("ROOT-CAUSE work=7 round=1: add subtracted — sites: calc.py:2, calc.py:sub — "
            "test_calc.py::test_add") in _journal(out)
    assert _class_test(out) == ("add subtracted", "calc.py:2, calc.py:sub", [("test_calc.py", "test_add")])


def test_without_sites_the_old_line_stays_and_a_note_says_so(render, tmp_path):
    out, before = _repo(render, tmp_path)
    r = _tool(out, "--work", "7", "--round", "1", "--before", before, "--cause", "add subtracted",
              "--", sys.executable, "-m", "pytest", "test_calc.py")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "ROOT-CAUSE work=7 round=1: add subtracted — test_calc.py::test_add" in _journal(out)
    assert "--sites" in r.stderr and "class-test" in r.stderr, r.stderr


def test_sites_read_back_a_junit_test_by_its_file_attribute(render, tmp_path):
    """A runner writing `file=` on its test case (vitest, jest-junit with the option) names
    the test file itself; its `classname` is no path (a `describe` title)."""
    out, before = _repo(render, tmp_path)
    runner = RUNNER.replace("<testcase classname='calc.spec' name=",
                            "<testcase classname='Calc adds' file='tests/calc.test.ts' name=")
    (out / "calc.spec.py").write_text(runner, encoding="utf-8")
    r = _tool(out, "--work", "7", "--round", "1", "--before", before, "--junit", "report.xml",
              "--copy", "calc.spec.py", "--cause", "add subtracted", "--sites", "calc.py:2", "--",
              sys.executable, "calc.spec.py")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "red before, green after (1): tests/calc.test.ts::adds" in _journal(out)
    assert _class_test(out) == ("add subtracted", "calc.py:2", [("tests/calc.test.ts", "adds")])


def test_refuses_when_no_test_was_red_before(render, tmp_path):
    out, before = _repo(render, tmp_path)

    r = _tool(out, "--work", "7", "--round", "1", "--before", before, "--",
              sys.executable, "-m", "pytest", "test_calc.py::test_zero")

    assert r.returncode == 1 and "proves no fix" in r.stderr, r.stderr
    assert not (out / ".process-work/journal").exists() or "Red evidence" not in _journal(out)


def test_refuses_when_a_test_is_still_red(render, tmp_path):
    out, before = _repo(render, tmp_path)
    (out / "test_calc.py").write_text(
        (out / "test_calc.py").read_text() + "\n\ndef test_broken():\n    assert add(2, 2) == 5\n",
        encoding="utf-8")

    r = _tool(out, "--work", "7", "--round", "1", "--before", before, "--",
              sys.executable, "-m", "pytest", "test_calc.py")

    assert r.returncode == 1 and "still red" in r.stderr and "test_broken" in r.stderr, r.stderr


def test_refuses_a_placeholder_cause(render, tmp_path):
    out, before = _repo(render, tmp_path)

    r = _tool(out, "--work", "7", "--round", "1", "--before", before, "--cause", "<cause>", "--",
              sys.executable, "-m", "pytest", "test_calc.py")

    assert r.returncode == 1 and "real sentence" in r.stderr, r.stderr


def test_leaves_no_worktree_behind(render, tmp_path):
    out, before = _repo(render, tmp_path)
    _tool(out, "--work", "7", "--round", "1", "--before", before, "--dry-run", "--",
          sys.executable, "-m", "pytest", "test_calc.py")

    assert len(_git(out, "worktree", "list").splitlines()) == 1


# --- refute: a proof that proves nothing must not pass (one owner: a table by node id) ---


def test_a_test_that_did_not_run_before_is_no_red(render, tmp_path):
    """F1: a directory argument; the new file never ran at the old ref, so it proves nothing."""
    out, before = _repo(render, tmp_path)
    (out / "tests").mkdir()
    (out / "tests/test_new.py").write_text("def test_trivial():\n    assert True\n", encoding="utf-8")

    r = _tool(out, "--work", "7", "--round", "1", "--before", before, "--",
              sys.executable, "-m", "pytest", "tests")

    assert r.returncode == 1 and "proves no fix" in r.stderr, r.stdout + r.stderr


def test_a_directory_argument_is_taken_into_the_old_tree(render, tmp_path):
    """Twin: the directory's tests do run at the old ref, and the real regression is measured."""
    out, before = _repo(render, tmp_path)
    (out / "tests").mkdir()
    (out / "test_calc.py").rename(out / "tests/test_calc.py")
    (out / "tests/conftest.py").write_text(
        "import sys, pathlib\nsys.path.insert(0, str(pathlib.Path(__file__).parents[1]))\n", encoding="utf-8")

    r = _tool(out, "--work", "7", "--round", "1", "--before", before, "--dry-run", "--",
              sys.executable, "-m", "pytest", "tests")

    assert r.returncode == 0, r.stdout + r.stderr
    assert "test_calc.py::test_add" in r.stdout and "test_zero" not in r.stdout.split("green after")[1]


def test_a_collection_error_before_is_refused(render, tmp_path):
    """F2: pytest stopped collecting; the other tests never ran against the old code."""
    out, before = _repo(render, tmp_path)
    (out / "helper.py").write_text("X = 1\n", encoding="utf-8")
    (out / "test_helper.py").write_text("from helper import X\n\n\ndef test_x():\n    assert X == 1\n",
                                        encoding="utf-8")

    r = _tool(out, "--work", "7", "--round", "1", "--before", before, "--",
              sys.executable, "-m", "pytest", "test_calc.py", "test_helper.py")

    assert r.returncode == 1 and "collect" in r.stderr, r.stdout + r.stderr


def test_the_record_names_tests_by_node_id(render, tmp_path):
    """F5: two tests of one name in two files stay two, a parametrized id stays whole."""
    out, before = _repo(render, tmp_path)
    (out / "test_other.py").write_text(
        "import pytest\nfrom calc import add\n\n\ndef test_add():\n    assert add(2, 2) == 4\n\n\n"
        "@pytest.mark.parametrize('p', ['a::b'])\ndef test_p(p):\n    assert add(1, 1) == 2\n",
        encoding="utf-8")

    r = _tool(out, "--work", "7", "--round", "1", "--before", before, "--dry-run", "--",
              sys.executable, "-m", "pytest", "test_calc.py", "test_other.py")

    assert r.returncode == 0, r.stderr
    assert "test_calc.py::test_add" in r.stdout and "test_other.py::test_add" in r.stdout
    assert "test_other.py::test_p[a::b]" in r.stdout, r.stdout


def test_an_absolute_test_path_is_taken_into_the_old_tree(render, tmp_path):
    """F4: an absolute path crashed the copy (`SameFileError`)."""
    out, before = _repo(render, tmp_path)

    r = _tool(out, "--work", "7", "--round", "1", "--before", before, "--dry-run", "--",
              sys.executable, "-m", "pytest", str(out / "test_calc.py"))

    assert r.returncode == 0 and "Traceback" not in r.stderr, r.stdout + r.stderr


def test_a_stale_worktree_of_an_earlier_run_is_pruned(render, tmp_path):
    """F3: a killed run left its worktree registered; the next run prunes it."""
    out, before = _repo(render, tmp_path)
    stale = tmp_path / "gone"
    _git(out, "worktree", "add", "--detach", "-q", str(stale), before)
    import shutil
    shutil.rmtree(stale)

    _tool(out, "--work", "7", "--round", "1", "--before", before, "--dry-run", "--",
          sys.executable, "-m", "pytest", "test_calc.py")

    assert len(_git(out, "worktree", "list").splitlines()) == 1


# --- refute of the fix round: read the fact, not a proxy ---


def test_a_setup_error_before_is_no_red(render, tmp_path):
    """G1: an error in setup (a fixture the old tree lacks) is no run of the test's code."""
    out, before = _repo(render, tmp_path)
    (out / "tests/pkg").mkdir(parents=True)
    (out / "tests/pkg/conftest.py").write_text(
        "import pytest\n\n\n@pytest.fixture\ndef newfix():\n    return 1\n", encoding="utf-8")
    (out / "tests/pkg/test_t.py").write_text("def test_trivial(newfix):\n    assert True\n",
                                             encoding="utf-8")

    r = _tool(out, "--work", "7", "--round", "1", "--before", before, "--",
              sys.executable, "-m", "pytest", "tests/pkg/test_t.py")

    assert r.returncode == 1 and "proves no fix" in r.stderr, r.stdout + r.stderr


def test_an_inherited_test_is_named_by_its_collecting_module(render, tmp_path):
    """G3: xunit1's `file` names where the function is defined, not the module that runs it."""
    out, before = _repo(render, tmp_path)
    (out / "tests/pkg").mkdir(parents=True)
    (out / "tests/__init__.py").write_text("", encoding="utf-8")
    (out / "tests/pkg/__init__.py").write_text("", encoding="utf-8")
    (out / "tests/base.py").write_text(
        "from calc import add\n\n\nclass Base:\n    def test_shared(self):\n        assert add(1, 2) == 3\n",
        encoding="utf-8")
    (out / "tests/pkg/test_a.py").write_text(
        "from tests.base import Base\n\n\nclass TestImpl(Base):\n    pass\n", encoding="utf-8")

    r = _tool(out, "--work", "7", "--round", "1", "--before", before, "--dry-run", "--copy", "tests",
              "--", sys.executable, "-m", "pytest", "tests/pkg/test_a.py")

    assert r.returncode == 0, r.stdout + r.stderr
    assert "tests/pkg/test_a.py::TestImpl::test_shared" in r.stdout, r.stdout


# --- third look: ask pytest for its own facts (node ids, rootdir, what is a test) ---


def test_a_test_under_its_own_rootdir_is_measured(render, tmp_path):
    """H1: `backend/pytest.ini` makes backend/ the rootdir; the test is not dropped."""
    out, before = _repo(render, tmp_path)
    (out / "backend/tests").mkdir(parents=True)
    (out / "backend/pytest.ini").write_text("[pytest]\npythonpath = ..\n", encoding="utf-8")
    (out / "test_calc.py").rename(out / "backend/tests/test_b.py")

    r = _tool(out, "--work", "7", "--round", "1", "--before", before, "--dry-run", "--copy",
              "backend/pytest.ini", "--", sys.executable, "-m", "pytest", "backend/tests/test_b.py")

    assert r.returncode == 0, r.stdout + r.stderr
    assert "test_b.py::test_add" in r.stdout, r.stdout


def test_a_dot_in_a_directory_name_is_no_package_separator(render, tmp_path):
    """H1: `tests/v1.2/` was split on its dot and the test vanished."""
    out, before = _repo(render, tmp_path)
    (out / "tests/v1.2").mkdir(parents=True)
    (out / "test_calc.py").rename(out / "tests/v1.2/test_d.py")
    (out / "conftest.py").write_text("", encoding="utf-8")

    r = _tool(out, "--work", "7", "--round", "1", "--before", before, "--dry-run", "--copy",
              "conftest.py", "--", sys.executable, "-m", "pytest", "tests/v1.2/test_d.py")

    assert r.returncode == 0, r.stdout + r.stderr
    assert "tests/v1.2/test_d.py::test_add" in r.stdout, r.stdout


def test_a_named_source_file_is_not_taken_into_the_old_tree(render, tmp_path):
    """H2: `--doctest-modules calc.py` carried the fixed source along, and the old run
    exercised the new code. Only test files travel; the doctest runs against the old code."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _git(out, "init", "-q", "-b", "main")
    _git(out, "config", "user.email", "t@t")
    _git(out, "config", "user.name", "t")
    doc = 'def add(a, b):\n    """\n    >>> add(1, 2)\n    3\n    """\n'
    (out / "calc.py").write_text(doc + "    return a - b\n", encoding="utf-8")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "base")
    before = _git(out, "rev-parse", "HEAD")
    (out / "calc.py").write_text(doc + "    return a + b\n", encoding="utf-8")

    r = _tool(out, "--work", "7", "--round", "1", "--before", before, "--dry-run", "--",
              sys.executable, "-m", "pytest", "--doctest-modules", "calc.py")

    assert r.returncode == 0, r.stdout + r.stderr
    assert "calc.py::calc.add" in r.stdout, r.stdout


def test_a_named_directory_carries_only_its_tests(render, tmp_path):
    """J1: `pytest backend` copied the fixed backend/calc.py into the old tree."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _git(out, "init", "-q", "-b", "main")
    _git(out, "config", "user.email", "t@t")
    _git(out, "config", "user.name", "t")
    (out / "backend").mkdir()
    (out / "backend/pytest.ini").write_text("[pytest]\npythonpath = .\n", encoding="utf-8")
    (out / "backend/calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "base")
    before = _git(out, "rev-parse", "HEAD")
    (out / "backend/calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (out / "backend/tests").mkdir()
    (out / "backend/tests/test_b.py").write_text(
        "from calc import add\n\n\ndef test_b():\n    assert add(1, 2) == 3\n", encoding="utf-8")

    r = _tool(out, "--work", "7", "--round", "1", "--before", before, "--dry-run", "--",
              sys.executable, "-m", "pytest", "backend")

    assert r.returncode == 0, r.stdout + r.stderr
    assert "tests/test_b.py::test_b" in r.stdout, r.stdout


def test_a_missing_probe_report_is_named(render, tmp_path):
    """J2: `python -I` ignores PYTHONPATH, the probe never loads — say so."""
    out, before = _repo(render, tmp_path)

    r = _tool(out, "--work", "7", "--round", "1", "--before", before, "--",
              sys.executable, "-I", "-m", "pytest", "test_calc.py")

    assert r.returncode == 1 and "probe" in r.stderr, r.stderr


RUNNER = '''import sys
from xml.sax.saxutils import quoteattr
sys.path.insert(0, ".")
from calc import add
cases = []
for name, ok in (("adds", add(1, 2) == 3), ("zero", add(0, 0) == 0)):
    body = "" if ok else "<failure message='wrong'/>"
    cases.append(f"<testcase classname='calc.spec' name={quoteattr(name)}>{body}</testcase>")
open("report.xml", "w").write("<testsuites><testsuite name='calc'>" + "".join(cases) + "</testsuite></testsuites>")
sys.exit(0 if all(ok for _n, ok in ((1, add(1, 2) == 3), (2, add(0, 0) == 0))) else 1)
'''


def test_a_junit_runner_is_measured_by_its_report(render, tmp_path):
    """#256: a runner other than pytest reports through JUnit XML; the tool reads each
    side's fresh report and names tests `<classname>::<name>`."""
    out, before = _repo(render, tmp_path)
    (out / "calc.spec.py").write_text(RUNNER, encoding="utf-8")
    r = _tool(out, "--work", "7", "--round", "1", "--before", before, "--junit", "report.xml",
              "--copy", "calc.spec.py", "--cause", "add subtracted instead of adding", "--",
              sys.executable, "calc.spec.py")
    assert r.returncode == 0, r.stdout + r.stderr
    text = _journal(out)
    assert "JUnit report.xml" in text
    assert "red before, green after (1): calc.spec::adds" in text
    assert "ROOT-CAUSE work=7 round=1: add subtracted instead of adding — calc.spec::adds" in text


def test_a_missing_junit_report_proves_nothing(render, tmp_path):
    """#256 AC-2: no file, an empty one or a stale one is "did not run as asked"."""
    out, before = _repo(render, tmp_path)
    (out / "report.xml").write_text("<testsuites><testsuite><testcase classname='x' name='y'/>"
                                    "</testsuite></testsuites>", encoding="utf-8")  # stale, from earlier
    r = _tool(out, "--work", "7", "--round", "1", "--before", before, "--junit", "report.xml", "--",
              sys.executable, "-c", "pass")
    assert r.returncode == 1 and "no JUnit report report.xml" in r.stderr, r.stdout + r.stderr


def test_junit_mode_carries_no_directory_of_source(render, tmp_path):
    """A named directory of a non-Python project holds its fixed source — only files travel."""
    out, before = _repo(render, tmp_path)
    (out / "web").mkdir()
    (out / "web/app.js").write_text("fixed\n", encoding="utf-8")
    sys.path.insert(0, str(out / "scripts/process"))
    import importlib.util
    spec = importlib.util.spec_from_file_location("red_ev_junit", out / "scripts/process/red_evidence.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    m = mod.measure(out, before, [sys.executable, "-c", "pass", "web"], [], junit="r.xml")
    assert "web" not in m["carried"]
    sys.path.remove(str(out / "scripts/process"))


def _red_evidence_module(out):
    import importlib.util
    spec = importlib.util.spec_from_file_location("red_ev_r2", out / "scripts/process/red_evidence.py")
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(out / "scripts/process"))
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.path.remove(str(out / "scripts/process"))
    return mod


def test_junit_names_only_a_report_it_may_delete(render, tmp_path):
    # refute v2.75 r2: `--junit calc.mjs` deleted the working tree's uncommitted fix
    out, before = _repo(render, tmp_path)
    for name, why in (("calc.py", "an .xml file"), ("tracked.xml", "git tracks that file")):
        if name == "tracked.xml":
            (out / name).write_text("<testsuites/>", encoding="utf-8")
            _git(out, "add", name)
        r = _tool(out, "--work", "7", "--round", "1", "--before", before, "--junit", name, "--",
                  sys.executable, "-c", "pass")
        assert r.returncode == 2 and why in r.stderr, r.stderr
        assert (out / name).is_file()


def test_a_junit_error_is_no_red_and_the_worst_outcome_stands_in_any_order(render, tmp_path):
    out, _before = _repo(render, tmp_path)
    mod = _red_evidence_module(out)
    report = tmp_path / "r.xml"
    for first, second in (("<error/>", "<failure/>"), ("<failure/>", "<error/>"), ("", "<failure/>")):
        report.write_text(f"<testsuites><testsuite><testcase classname='c' name='t'>{first}</testcase>"
                          f"<testcase classname='c' name='t'>{second}</testcase>"
                          "<testcase classname='c' name='s'><skipped/></testcase></testsuite></testsuites>")
        got = mod.junit_outcomes(report)
        assert got == {"c::t": "error" if "error" in first + second else "failed"}, (first, second, got)
    report.write_text("<testsuites><testsuite><testcase classname='c' name='t'>")  # cut off mid-run
    assert mod.junit_outcomes(report) is None


def test_a_stale_report_on_the_fixed_side_proves_nothing(render, tmp_path):
    out, before = _repo(render, tmp_path)
    # the old code writes its failing report; the fixed one writes none
    (out / "calc.spec.py").write_text(
        "import sys\nsys.path.insert(0, '.')\nfrom calc import add\nif add(1, 2) != 3:\n"
        "    open('report.xml', 'w').write(\"<testsuites><testsuite><testcase classname='calc.spec' "
        "name='adds'><failure/></testcase></testsuite></testsuites>\")\n    sys.exit(1)\n", encoding="utf-8")
    (out / "report.xml").write_text("<testsuites><testsuite><testcase classname='calc.spec' name='adds'/>"
                                    "</testsuite></testsuites>", encoding="utf-8")  # passing, from earlier
    r = _tool(out, "--work", "7", "--round", "1", "--before", before, "--junit", "report.xml",
              "--copy", "calc.spec.py", "--", sys.executable, "calc.spec.py")
    assert r.returncode == 1 and "no JUnit report report.xml now" in r.stderr, r.stdout + r.stderr


def test_the_old_tree_borrows_the_installed_node_modules(render, tmp_path):
    # refute v2.75 r2: a JS test importing a dependency failed in the old tree for that alone
    out, before = _repo(render, tmp_path)
    _git(out, "checkout", "-q", before)
    (out / "package.json").write_text("{}\n", encoding="utf-8")
    _git(out, "add", "package.json")
    _git(out, "commit", "-q", "-m", "package")
    before = _git(out, "rev-parse", "HEAD")
    _git(out, "checkout", "-q", "-B", "7-fix")
    (out / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (out / "node_modules/dep").mkdir(parents=True)
    (out / "node_modules/dep/index.txt").write_text("installed\n", encoding="utf-8")
    (out / "calc.spec.py").write_text(
        "import os, sys\nsys.path.insert(0, '.')\nfrom calc import add\n"
        "dep = os.path.exists('node_modules/dep/index.txt')\n"
        "body = '<error/>' if not dep else ('' if add(1, 2) == 3 else '<failure/>')\n"
        "open('report.xml', 'w').write(f\"<testsuites><testsuite><testcase classname='calc.spec' "
        "name='adds'>{body}</testcase></testsuite></testsuites>\")\n"
        "sys.exit(0 if dep and add(1, 2) == 3 else 1)\n", encoding="utf-8")
    r = _tool(out, "--work", "7", "--round", "1", "--before", before, "--junit", "report.xml",
              "--copy", "calc.spec.py", "--dry-run", "--", sys.executable, "calc.spec.py")
    assert r.returncode == 0 and "red before, green after (1): calc.spec::adds" in r.stdout, r.stdout + r.stderr


def test_a_dash_inside_the_sites_reads_back_as_written(render, tmp_path):
    """` — ` trennt die Segmente der Zeile; in `--sites` wird er zum Komma, sonst endeten
    die Sites früher und die Tests läsen nicht zurück."""
    out, _before = _repo(render, tmp_path)
    mod = _red_evidence_module(out)
    m = {"command": ["pytest"], "before": "abc", "exit_before": 1, "exit_after": 0,
         "red_to_green": ["test_calc.py::test_add"], "carried": [], "junit": None}
    text = mod.block(m, "7", 1, "add subtracted", "a.py:1 — b.py:2")
    cr, ev = _grammar(out)
    found = cr.ROOT_CAUSE_LINE.search(text)
    cause, sites, tests = cr.root_cause_parts(found.group("text"))
    assert (cause, sites, ev.claimed_tests(tests)) == ("add subtracted", "a.py:1, b.py:2",
                                                       [("test_calc.py", "test_add")])


def test_sites_is_read_in_any_case(render, tmp_path):
    out, _before = _repo(render, tmp_path)
    cr, _ev = _grammar(out)
    assert cr.root_cause_parts("x — Sites: none — refuted") == ("x", "none", "refuted")
