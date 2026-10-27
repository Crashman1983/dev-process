"""red_evidence: the red-before/green-after proof, measured instead of typed (#124)."""
import datetime as dt
import os
import subprocess
import sys
from pathlib import Path

import pytest


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


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="needs symlinks")
def test_a_symlinked_journal_shard_is_refused_before_the_run(render, tmp_path):
    """The journal path is the same one attest fixes: a symlink is refused by name before
    the measurement, so no evidence is written through the link."""
    out, before = _repo(render, tmp_path)
    shard = out / ".process-work/journal/issue-7" / f"{dt.date.today().isoformat()}.md"
    shard.parent.mkdir(parents=True, exist_ok=True)
    shard.symlink_to("../2026-01-01.md")
    r = _tool(out, "--work", "7", "--round", "1", "--before", before,
              "--cause", "add subtracted", "--dry-run", "--", sys.executable, "-c", "pass")
    assert r.returncode == 1, r.stdout + r.stderr
    assert "symlink" in r.stderr and "issue-7" in r.stderr, r.stderr


_SWAP_DURING_MEASURE = '''
import os, sys
sys.path.insert(0, sys.argv[1])
import red_evidence
shard, outside = sys.argv[2], sys.argv[3]
measured = red_evidence.measure


def measure_then_swap(*a, **k):
    out = measured(*a, **k)
    os.symlink(outside, shard + ".lnk")
    os.replace(shard + ".lnk", shard)
    print("SWAPPED", file=sys.stderr, flush=True)
    return out


red_evidence.measure = measure_then_swap
raise SystemExit(red_evidence.main(sys.argv[4:]))
'''


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="needs symlinks")
def test_a_shard_swapped_during_the_measurement_is_not_followed(render, tmp_path, tmp_path_factory):
    """#308 sweep (§9): the path was checked before the measurement and opened by name after
    it — a symlink swapped in meanwhile led the append outside the repository. The append
    goes through the checked descriptor (`append_checked`): refused, the outside file intact."""
    out, before = _repo(render, tmp_path)
    shard = out / ".process-work/journal/issue-7" / f"{dt.date.today().isoformat()}.md"
    shard.parent.mkdir(parents=True, exist_ok=True)
    shard.write_text("# today\n", encoding="utf-8")
    outside = tmp_path_factory.mktemp("outside") / "outside.md"
    outside.write_text("OUTSIDE\n", encoding="utf-8")
    runner = tmp_path_factory.mktemp("runner") / "swap_runner.py"
    runner.write_text(_SWAP_DURING_MEASURE, encoding="utf-8")
    r = subprocess.run([sys.executable, str(runner), str(out / "scripts/process"), str(shard), str(outside),
                        "--work", "7", "--round", "1", "--before", before,
                        "--cause", "add subtracted instead of adding", "--",
                        sys.executable, "-m", "pytest", "test_calc.py"],
                       cwd=out, capture_output=True, text=True,
                       env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    assert "SWAPPED" in r.stderr, r.stdout + r.stderr
    assert r.returncode == 1, r.stdout + r.stderr
    assert outside.read_text(encoding="utf-8") == "OUTSIDE\n"


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
    _files(out, {"tests/calc.test.ts": 'it("adds", () => {})\nit("zero", () => {})\n'})
    runner = RUNNER.replace("<testcase classname='calc.spec' name=",
                            "<testcase classname='Calc adds' file='tests/calc.test.ts' name=")
    (out / "calc.spec.py").write_text(runner, encoding="utf-8")
    r = _tool(out, "--work", "7", "--round", "1", "--before", before, "--junit", "report.xml",
              "--copy", "calc.spec.py", "--cause", "add subtracted", "--sites", "calc.py:2", "--",
              sys.executable, "calc.spec.py")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "red before, green after (1): tests/calc.test.ts::adds" in _journal(out)
    assert _class_test(out) == ("add subtracted", "calc.py:2", [("tests/calc.test.ts", "adds")])


def test_sites_read_back_an_each_test_by_its_expanded_name(render, tmp_path):
    """v2.79 D2 (#328): the JUnit report names an `.each` case by its expanded title; the
    gate's one reader takes it as declared by the template, so the class test resolves."""
    out, before = _repo(render, tmp_path)
    _files(out, {"tests/calc.test.ts": 'it.each([[1, 2, 3]])("adds %i and %i", (a, b, c) => {})\n'})
    (out / "calc.spec.py").write_text(_junit_runner([
        ("Calc", "tests/calc.test.ts", "adds 1 and 2", "fail", "pass")]), encoding="utf-8")
    r = _tool(out, "--work", "7", "--round", "1", "--before", before, "--junit", "report.xml",
              "--copy", "calc.spec.py", "--cause", "add subtracted", "--sites", "calc.py:2", "--",
              sys.executable, "calc.spec.py")
    assert r.returncode == 0, r.stdout + r.stderr
    assert _class_test(out) == ("add subtracted", "calc.py:2", [("tests/calc.test.ts", "adds 1 and 2")])


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


def _files(out: Path, files: dict[str, str]) -> None:
    """Test files in the working tree, never committed (the reference check reads here)."""
    for rel, text in files.items():
        path = out / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def _junit_runner(cases) -> str:
    """A runner after RUNNER's pattern: `(classname, file | None, name, before, after)`,
    states `pass`/`fail`/`skip`/`error`; it writes `after` once the fix is in."""
    source = '''import sys
from xml.sax.saxutils import quoteattr
sys.path.insert(0, ".")
from calc import add
cases = CASES
states = []
out = []
for cls, file, name, before, after in cases:
    state = after if add(1, 2) == 3 else before
    states.append(state)
    body = "<skipped/>" if state == "skip" else "<failure/>" if state == "fail" else (
        "<error/>" if state == "error" else "")
    attrs = "classname=" + quoteattr(cls) + " name=" + quoteattr(name)
    if file is not None:
        attrs += " file=" + quoteattr(file)
    out.append("<testcase " + attrs + ">" + body + "</testcase>")
open("report.xml", "w").write("<testsuites><testsuite name='calc'>" + "".join(out) + "</testsuite></testsuites>")
sys.exit(0 if all(s in ("pass", "skip") for s in states) else 1)
'''
    return source.replace("CASES", repr(cases))


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
        got = mod.junit_cases(report)
        assert {mod._ref(c): s for c, s in got.items()} == {
            "c::t": "error" if "error" in first + second else "failed",
            "c::s": "skipped"}, (first, second, got)
    report.write_text("<testsuites><testsuite><testcase classname='c' name='t'>")  # cut off mid-run
    assert mod.junit_cases(report) is None


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


def test_a_junit_file_attribute_is_made_relative_and_keeps_its_class(render, tmp_path):
    """Ein absolutes `file=` unter der Wurzel wird relativ, eines außerhalb fällt auf die
    classname-Form zurück; eine Klasse im classname bleibt Teil des Namens."""
    out, _before = _repo(render, tmp_path)
    mod = _red_evidence_module(out)
    report = tmp_path / "r.xml"
    inside, outside = out / "tests/test_x.py", tmp_path.parent / f"{tmp_path.name}-other/test_x.py"
    report.write_text(
        "<testsuites><testsuite>"
        f"<testcase classname='tests.test_x.TestOne' file='{inside}' name='test_x'><failure/></testcase>"
        f"<testcase classname='tests.test_x.TestTwo' file='{inside}' name='test_x'/>"
        "<testcase classname='tests.test_x' file='tests/test_x.py' name='test_y'/>"
        "<testcase classname='KenniTests.FooTests' file='KenniTests/FooTests.swift' name='testBar'/>"
        f"<testcase classname='calc.spec' file='{outside}' name='adds'/>"
        "<testcase classname='Calc' file='web/calc.test.ts' name='adds two'/>"
        "</testsuite></testsuites>")
    got = mod.junit_cases(report, out)
    assert {mod._ref(c): s for c, s in got.items()} == {
        "tests/test_x.py::TestOne::test_x": "failed",
        "tests/test_x.py::TestTwo::test_x": "passed",
        "tests/test_x.py::test_y": "passed",
        "KenniTests/FooTests.swift::testBar": "passed",
        "calc.spec::adds": "passed",
        # a one-word `describe` title outside Python is no class: attest finds `adds two` in the file
        "web/calc.test.ts::adds two": "passed",
    }
    # the identity keeps the two different absolute files apart, though both write calc.spec::adds
    assert len([c for c in got if c.file == str(outside)]) == 1


def test_distinct_junit_triples_are_distinct_cases(render, tmp_path):
    """#303 AC-4: identity is the triple (file, classname, name), not a joined key."""
    out, _before = _repo(render, tmp_path)
    mod = _red_evidence_module(out)
    outside1 = tmp_path.parent / f"{tmp_path.name}-one/calc.spec"
    outside2 = tmp_path.parent / f"{tmp_path.name}-two/calc.spec"
    report = tmp_path / "r.xml"
    report.write_text(
        "<testsuites><testsuite>"
        "<testcase classname='suite A' file='tests/c.ts' name='adds'/>"
        "<testcase classname='' file='tests/c.ts' name='adds (suite A)'/>"
        "<testcase classname='a' name='b::c'/>"
        "<testcase classname='a::b' name='c'/>"
        "<testcase classname='x' name='t'><failure/></testcase>"
        "<testcase classname='x' name='t'/>"
        "<testcase classname='' name='solo'/>"
        f"<testcase classname='calc.spec' file='{outside1}' name='adds'/>"
        f"<testcase classname='calc.spec' file='{outside2}' name='adds'/>"
        "<testcase classname='s' name='skip'><skipped/></testcase>"
        "<testcase classname='B' file='./tests/c.ts' name='adds'/>"
        "</testsuite></testsuites>")
    got = mod.junit_cases(report, out)
    expected = {
        mod.Case("tests/c.ts", "suite A", "adds"),
        mod.Case("tests/c.ts", "", "adds (suite A)"),
        mod.Case("", "a", "b::c"),
        mod.Case("", "a::b", "c"),
        mod.Case("", "x", "t"),
        mod.Case("", "", "solo"),
        mod.Case(str(outside1), "calc.spec", "adds"),
        mod.Case(str(outside2), "calc.spec", "adds"),
        mod.Case("", "s", "skip"),
        mod.Case("./tests/c.ts", "B", "adds"),
    }
    assert len(got) == 10 and set(got) == expected, got
    assert got[mod.Case("", "x", "t")] == "failed"
    assert got[mod.Case("", "s", "skip")] == "skipped"
    assert mod.Case("./tests/c.ts", "B", "adds") in got
    assert mod._ref(mod.Case("tests/c.ts", "suite A", "adds")) == "tests/c.ts::adds"
    assert mod._ref(mod.Case("tests/c.ts", "", "adds (suite A)")) == "tests/c.ts::adds (suite A)"
    assert mod._ref(mod.Case("", "a", "b::c")) == "a::b::c"
    assert mod._ref(mod.Case("", "", "solo")) == "solo"
    assert mod._ref(mod.Case(str(outside1), "calc.spec", "adds")) == "calc.spec::adds"
    assert mod._ref(mod.Case("./tests/c.ts", "B", "adds")) == "./tests/c.ts::adds"


@pytest.mark.parametrize("kind,test_file", [
    ("issue-repro", "tests/calc.test.ts"),
    ("bracket", "tests/calc.test.ts"),
    ("concat", None),
    ("outside-root", None),
])
def test_junit_cases_sharing_a_reference_stay_apart_in_the_measurement(render, tmp_path, kind, test_file):
    """No false green though two cases write the same reference: only the case that went
    red may turn green. Runs 1, 3 and 4 were green under v2.77.0; run 2 guards the bracket."""
    out, before = _repo(render, tmp_path)
    outside1 = str(tmp_path.parent / f"{tmp_path.name}-one/calc.spec")
    outside2 = str(tmp_path.parent / f"{tmp_path.name}-two/calc.spec")
    cases = {
        "issue-repro": [("suite A", test_file, "adds", "fail", "skip"),
                        ("suite B", test_file, "adds", "pass", "pass")],
        "bracket": [("suite A", test_file, "adds", "fail", "skip"),
                    ("", test_file, "adds (suite A)", "pass", "pass")],
        "concat": [("a", None, "b::c", "fail", "skip"),
                   ("a::b", None, "c", "pass", "pass")],
        "outside-root": [("calc.spec", outside1, "adds", "fail", "skip"),
                         ("calc.spec", outside2, "adds", "pass", "pass")],
    }[kind]
    if test_file:
        _files(out, {test_file: 'it("adds", () => {})\n'})
    (out / "calc.spec.py").write_text(_junit_runner(cases), encoding="utf-8")
    r = _tool(out, "--work", "7", "--round", "1", "--before", before, "--junit", "report.xml",
              "--copy", "calc.spec.py", "--", sys.executable, "calc.spec.py")
    assert r.returncode == 1 and "proves no fix" in r.stderr, r.stdout + r.stderr
    assert "Red evidence" not in _journal(out)


_TS = 'it("adds", () => {})\n'
_ALIAS_IDS = ["same-name", "title", "skipped", "dot-slash", "suffix", "ambiguous-suffix",
              "namesake", "params", "concat", "concat-sites", "outside-root",
              "outside-root-sites", "empty", "missing-file", "missing-file-sites",
              "title-sites", "resolves"]
_WRITTEN_REF = {"ambiguous-suffix": "a/tests/c.ts::adds", "params": "tests/test_p.py::test_x[1]",
                "concat": "a::b::c", "outside-root": "calc.spec::adds", "empty": "suite A::adds",
                "missing-file": "tests/gone.ts::adds", "resolves": "tests/c.ts::adds"}


@pytest.mark.parametrize("kind", _ALIAS_IDS)
def test_reference_aliases_read_as_the_gate_reads_them(render, tmp_path, kind):
    """#303 AC-4: every alias form the gate reads as one test is refused, or — for a
    `sites:` reference — must resolve to exactly this test. Forms the gate separates stay
    written."""
    out, before = _repo(render, tmp_path)
    one = str(tmp_path.parent / f"{tmp_path.name}-one/calc.spec")
    two = str(tmp_path.parent / f"{tmp_path.name}-two/calc.spec")
    files = {"tests/c.ts": _TS}
    sites = kind.endswith("-sites") or kind == "resolves"
    if kind == "same-name":
        x, y = ("A", "tests/c.ts", "adds", "fail", "pass"), ("B", "tests/c.ts", "adds", "pass", "pass")
    elif kind == "title":
        x, y = ("A", "tests/c.ts", "adds", "fail", "pass"), ("", "tests/c.ts", "adds (x)", "pass", "pass")
    elif kind == "skipped":
        x, y = ("A", "tests/c.ts", "adds", "fail", "pass"), ("B", "tests/c.ts", "adds", "skip", "skip")
    elif kind == "dot-slash":
        x, y = ("A", "tests/c.ts", "adds", "fail", "pass"), ("B", "./tests/c.ts", "adds", "pass", "pass")
    elif kind == "suffix":
        x, y = ("A", "tests/c.ts", "adds", "fail", "pass"), ("B", "c.ts", "adds", "pass", "pass")
    elif kind == "ambiguous-suffix":
        files = {"a/tests/c.ts": _TS, "b/tests/c.ts": _TS}
        x, y = ("A", "a/tests/c.ts", "adds", "fail", "pass"), ("B", "tests/c.ts", "adds", "pass", "pass")
    elif kind == "namesake":
        files = {"tests/test_w.py": "def test_b():\n    assert True\n",
                 "backend/tests/test_w.py": "def test_a():\n    assert True\n"}
        x, y = (("backend.tests.test_w", "backend/tests/test_w.py", "test_a", "fail", "pass"),
                ("tests.test_w", "tests/test_w.py", "test_a", "pass", "pass"))
    elif kind == "params":
        files = {"tests/test_p.py": "def test_x():\n    assert True\n"}
        x, y = (("tests.test_p", "tests/test_p.py", "test_x[1]", "fail", "pass"),
                ("tests.test_p", "tests/test_p.py", "test_x[2]", "pass", "pass"))
    elif kind in ("concat", "concat-sites"):
        x, y = ("a", None, "b::c", "fail", "pass"), ("a::b", None, "c", "pass", "pass")
    elif kind in ("outside-root", "outside-root-sites"):
        x, y = ("calc.spec", one, "adds", "fail", "pass"), ("calc.spec", two, "adds", "pass", "pass")
    elif kind == "empty":
        x, y = ("suite A", None, "adds", "fail", "pass"), ("suite A", None, "zero", "pass", "pass")
    elif kind in ("missing-file", "missing-file-sites"):
        x, y = ("A", "tests/gone.ts", "adds", "fail", "pass"), ("B", "tests/gone.ts", "adds", "pass", "pass")
    elif kind == "title-sites":
        x, y = ("A", "tests/c.ts", "adds (edge)", "fail", "pass"), ("A", "tests/c.ts", "zero", "pass", "pass")
    elif kind == "resolves":
        files = {"tests/c.ts": 'it("adds", () => {})\nit("zero", () => {})\n'}
        x, y = ("A", "tests/c.ts", "adds", "fail", "pass"), ("A", "tests/c.ts", "zero", "pass", "pass")
    _files(out, files)
    (out / "calc.spec.py").write_text(_junit_runner([x, y]), encoding="utf-8")
    args = ["--work", "7", "--round", "1", "--before", before, "--junit", "report.xml",
            "--copy", "calc.spec.py", "--cause", "add subtracted"]
    if sites:
        args += ["--sites", "calc.py:2"]
    r = _tool(out, *args, "--", sys.executable, "calc.spec.py")
    refused = kind not in _WRITTEN_REF
    if refused:
        assert r.returncode == 1, r.stdout + r.stderr
        assert "does not resolve" in r.stderr if sites else "names several test cases" in r.stderr, r.stderr
        assert "Red evidence" not in _journal(out)
        if kind == "same-name":
            assert "A" in r.stderr and "B" in r.stderr and "tests/c.ts::adds" in r.stderr
        if kind == "title":
            assert "(no classname)" in r.stderr
    else:
        assert r.returncode == 0, r.stdout + r.stderr
        assert f"red before, green after (1): {_WRITTEN_REF[kind]}" in _journal(out)
    if kind == "resolves":
        assert _class_test(out) == ("add subtracted", "calc.py:2", [("tests/c.ts", "adds")])


_DYNAMIC_TS = ("const generated = ['adds']\n"
               "for (const name of generated) it(name, () => {})\n")


def test_a_dynamic_test_name_the_gate_cannot_resolve_collides_with_nothing(render, tmp_path):
    """#303 fix r3: two JUnit cases named `adds` whose test the gate cannot find in a
    dynamic test file have no identity, so the one going red -> green is written instead
    of being refused as a collision. v2.77.0 wrote it; fix r2 refused it."""
    out, before = _repo(render, tmp_path)
    _files(out, {"tests/c.ts": _DYNAMIC_TS})
    (out / "calc.spec.py").write_text(_junit_runner([
        ("A", "tests/c.ts", "adds", "fail", "pass"),
        ("B", "tests/c.ts", "adds", "pass", "pass")]), encoding="utf-8")
    r = _tool(out, "--work", "7", "--round", "1", "--before", before, "--junit", "report.xml",
              "--copy", "calc.spec.py", "--", sys.executable, "calc.spec.py")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "red before, green after (1): tests/c.ts::adds" in _journal(out)


_IDENTITY_TABLE = [
    ("resolved-unique", False, True),
    ("resolved-colliding", False, False),
    ("unresolved", False, True),
    ("unresolved-sites", True, False),
]


@pytest.mark.parametrize("kind,sites,written", _IDENTITY_TABLE, ids=[c[0] for c in _IDENTITY_TABLE])
def test_reference_identity_comes_only_from_a_resolved_entry(render, tmp_path, kind, sites, written):
    """#303 fix r3 table: a resolved reference has an identity (unique stays writable,
    colliding is refused); an unresolved one (`why`) has none — without `--sites` it is
    written, with `--sites` the class-test check refuses it."""
    out, before = _repo(render, tmp_path)
    if kind.startswith("unresolved"):
        _files(out, {"tests/c.ts": _DYNAMIC_TS})
        cases = [("A", "tests/c.ts", "adds", "fail", "pass"),
                 ("B", "tests/c.ts", "adds", "pass", "pass")]
    elif kind == "resolved-unique":
        _files(out, {"tests/c.ts": _TS + 'it("zero", () => {})\n'})
        cases = [("A", "tests/c.ts", "adds", "fail", "pass"),
                 ("A", "tests/c.ts", "zero", "pass", "pass")]
    else:
        _files(out, {"tests/c.ts": _TS})
        cases = [("A", "tests/c.ts", "adds", "fail", "pass"),
                 ("B", "tests/c.ts", "adds", "pass", "pass")]
    (out / "calc.spec.py").write_text(_junit_runner(cases), encoding="utf-8")
    args = ["--work", "7", "--round", "1", "--before", before, "--junit", "report.xml",
            "--copy", "calc.spec.py", "--cause", "add subtracted"]
    if sites:
        args += ["--sites", "calc.py:2"]
    r = _tool(out, *args, "--", sys.executable, "calc.spec.py")
    if written:
        assert r.returncode == 0, r.stdout + r.stderr
        assert "red before, green after (1): tests/c.ts::adds" in _journal(out)
    else:
        assert r.returncode == 1, r.stdout + r.stderr
        expected = "does not resolve" if sites else "names several test cases"
        assert expected in r.stderr, r.stderr
        assert "Red evidence" not in _journal(out)


_SITES_WHY_CASES = [
    ("missing-test", {"tests/c.ts": 'it("zero", () => {})\n'}, ("A", "tests/c.ts", "adds"),
     "declares no test 'adds' at head"),
    ("skipped-test", {"tests/c.ts": 'it.skip("adds", () => {})\n'}, ("A", "tests/c.ts", "adds"),
     "is marked or made to skip at head"),
    ("not-a-test-file", {"web/src/c.ts": 'it("adds", () => {})\n'}, ("A", "web/src/c.ts", "adds"),
     "is no test file this project declares"),
    ("python-missing-test", {"tests/test_c.py": "def test_zero():\n    assert True\n"},
     ("tests.test_c", "tests/test_c.py", "test_add"), "has no test test_add at head"),
    ("python-not-a-test-module", {"tests/helper_c.py": "def test_add():\n    assert True\n"},
     ("tests.helper_c", "tests/helper_c.py", "test_add"), "is no test module pytest collects"),
    ("python-marked-skip",
     {"tests/test_c.py": "import pytest\n\n@pytest.mark.skip\ndef test_add():\n    assert True\n"},
     ("tests.test_c", "tests/test_c.py", "test_add"), "is marked to skip or to fail"),
    ("ambiguous-file", {"a/tests/c.ts": _TS, "b/tests/c.ts": _TS}, ("A", "tests/c.ts", "adds"),
     "names several tracked files at head"),
    ("missing-file", {"tests/c.ts": _TS}, ("A", "tests/gone.ts", "adds"),
     "is no tracked file at head"),
]


@pytest.mark.parametrize("kind,files,case,gate", _SITES_WHY_CASES, ids=[c[0] for c in _SITES_WHY_CASES])
def test_a_sites_reference_the_resolver_rejects_is_refused(render, tmp_path, kind, files, case, gate):
    """#303 fix r2: every `--sites` reference whose `resolve_tests` entry carries a `why`
    is refused — the gate's decision and message, not a second rule. The cases cover each
    why class: missing test (the review repro), skipped test, non-test file, Python test
    module/test/skip, ambiguous path and missing file."""
    out, before = _repo(render, tmp_path)
    _files(out, files)
    cls, file, name = case
    (out / "calc.spec.py").write_text(_junit_runner([(cls, file, name, "fail", "pass")]),
                                      encoding="utf-8")
    r = _tool(out, "--work", "7", "--round", "1", "--before", before, "--junit", "report.xml",
              "--copy", "calc.spec.py", "--cause", "add subtracted", "--sites", "calc.py:2", "--",
              sys.executable, "calc.spec.py")
    assert r.returncode == 1, r.stdout + r.stderr
    assert gate in r.stderr, r.stderr
    assert "Red evidence" not in _journal(out)
    assert "ROOT-CAUSE" not in _journal(out)


def test_the_reference_check_fails_closed_without_its_inputs(render, tmp_path, monkeypatch):
    """#303 R5: a missing file list, unreadable text or unreadable policy refuses even
    when no collision was found; the intact setup refuses the collision itself."""
    out, before = _repo(render, tmp_path)
    mod = _red_evidence_module(out)
    _files(out, {"tests/c.ts": _TS})
    (out / "calc.spec.py").write_text(_junit_runner([
        ("A", "tests/c.ts", "adds", "fail", "pass"),
        ("B", "tests/c.ts", "adds", "pass", "pass")]), encoding="utf-8")

    def measure():
        return mod.measure(out, before, [sys.executable, "calc.spec.py"], ["calc.spec.py"],
                           junit="report.xml", class_test=False)

    original_files, original_read = mod._worktree_files, mod._read_worktree
    for kind, expected in (("no-listing", "cannot list the working tree"),
                           ("empty-listing", "cannot list the working tree"),
                           ("unreadable", "cannot read tests/c.ts"),
                           ("policy", "is not valid JSON"),
                           ("listed", "names several test cases")):
        monkeypatch.setattr(mod, "_worktree_files", original_files)
        monkeypatch.setattr(mod, "_read_worktree", original_read)
        policy = out / "docs/process/model-policy.local.json"
        if policy.exists():
            _git(out, "rm", "-q", str(policy.relative_to(out)))
            _git(out, "commit", "-q", "-m", "drop bad policy")
        if kind == "no-listing":
            monkeypatch.setattr(mod, "_worktree_files", lambda root: None)
        elif kind == "empty-listing":
            monkeypatch.setattr(mod, "_worktree_files", lambda root: [])
        elif kind == "unreadable":
            def boom(root, rel):
                if rel == "tests/c.ts":
                    raise OSError("denied")
                return (Path(root) / rel).read_text(encoding="utf-8", errors="replace")
            monkeypatch.setattr(mod, "_read_worktree", boom)
        elif kind == "policy":
            policy = out / "docs/process/model-policy.local.json"
            policy.write_text("{", encoding="utf-8")
            _git(out, "add", str(policy.relative_to(out)))
            _git(out, "commit", "-q", "-m", "bad policy")
        problems = mod.refusals(measure())
        assert any(expected in p for p in problems), (kind, problems)


def test_nested_python_classes_keep_their_whole_chain(render, tmp_path):
    out, _before = _repo(render, tmp_path)
    mod = _red_evidence_module(out)
    report = tmp_path / "r.xml"
    report.write_text(
        "<testsuites><testsuite>"
        "<testcase classname='tests.test_x.TestA.TestInner' file='tests/test_x.py' name='test_y'/>"
        "<testcase classname='tests.test_x.TestB.TestInner' file='tests/test_x.py' name='test_y'/>"
        "<testcase classname='TestOne' file='tests/test_x.py' name='test_y'/>"
        "</testsuite></testsuites>")
    got = mod.junit_cases(report, out)
    assert len(got) == 3, got
    assert mod._ref(mod.Case("tests/test_x.py", "tests.test_x.TestA.TestInner", "test_y")) == \
        "tests/test_x.py::TestA::TestInner::test_y"
    assert mod._ref(mod.Case("tests/test_x.py", "tests.test_x.TestB.TestInner", "test_y")) == \
        "tests/test_x.py::TestB::TestInner::test_y"
    assert mod._ref(mod.Case("tests/test_x.py", "TestOne", "test_y")) == \
        "tests/test_x.py::TestOne::test_y"


def test_a_v2770_root_cause_line_still_reads_back(render, tmp_path):
    """The written reference form does not change for lines v2.77.0 wrote."""
    out, _before = _repo(render, tmp_path)
    cr, ev = _grammar(out)
    line = ("ROOT-CAUSE work=7 round=1: add subtracted — sites: calc.py:2 — "
            "tests/calc.test.ts::adds")
    m = cr.ROOT_CAUSE_LINE.search(line)
    _cause, _sites, tests = cr.root_cause_parts(m.group("text"))
    assert ev.claimed_tests(tests) == [("tests/calc.test.ts", "adds")]


def test_an_absolute_junit_file_names_one_test_in_both_trees(render, tmp_path):
    """Der Runner schreibt `file=` absolut: im alten Baum und im Arbeitsbaum ist es dieselbe
    Datei relativ zur jeweiligen Wurzel — rot vorher, grün nachher wird gemessen."""
    out, before = _repo(render, tmp_path)
    runner = RUNNER.replace(
        "<testcase classname='calc.spec' name=",
        "<testcase classname='calc.spec' file={quoteattr(__import__('os').path.abspath('tests/calc.test.ts'))} name=")
    (out / "calc.spec.py").write_text(runner, encoding="utf-8")
    r = _tool(out, "--work", "7", "--round", "1", "--before", before, "--junit", "report.xml",
              "--copy", "calc.spec.py", "--dry-run", "--", sys.executable, "calc.spec.py")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "red before, green after (1): tests/calc.test.ts::adds" in r.stdout, r.stdout


_PARAM_SOURCE = '''import pytest


@pytest.mark.parametrize("p", ["a[b]", "]", "", "\\xfc", "a[b], c", "a[b,c]"])
def test_param(p):
    assert True


class TestOuter:
    class TestInner:
        @pytest.mark.parametrize("p", ["a[b]"])
        def test_nested(self, p):
            assert True
'''


def test_red_evidence_and_attest_read_one_pytest_id(render, tmp_path):
    """#306 differential: real pytest ids (nested brackets, a `]` in the value, an empty
    value, unicode, a class chain) — the pytest path (with and without `--sites`) and the
    JUnit path derive the same name as the owner, `attest_evidence.claimed_tests`."""
    out, _before = _repo(render, tmp_path)
    _files(out, {"test_param_ids.py": _PARAM_SOURCE})
    collected = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q",
                                "test_param_ids.py"], cwd=out, capture_output=True, text=True)
    node_ids = [line for line in collected.stdout.splitlines() if "::" in line]
    assert collected.returncode == 0 and len(node_ids) == 7, collected.stdout + collected.stderr
    red = _red_evidence_module(out)
    _cr, ev = _grammar(out)
    rules = ev.review_policy(out, "HEAD")[0]
    files = ["test_param_ids.py"]
    resolve = lambda ref: ev.resolve_tests(  # noqa: E731
        ref, files, lambda rel: (out / rel).read_text(encoding="utf-8"), rules)
    for node_id in node_ids:
        pairs = ev.claimed_tests(node_id)
        assert len(pairs) == 1, (node_id, pairs)
        file, owner_name = pairs[0]
        assert red._reference_problem(node_id, [node_id], class_test=False, resolve=resolve) is None
        assert red._reference_problem(node_id, [node_id], class_test=True, resolve=resolve) is None, node_id
        parts = node_id.split("::")
        classes = parts[1:-1]
        classname = ".".join([Path(file).stem, *classes]) if classes else Path(file).stem
        case = red.Case(file, classname, parts[-1])
        assert red._attest_name(case) == owner_name, node_id
        assert red._reference_problem(case, [case], class_test=False, resolve=resolve) is None
        assert red._reference_problem(case, [case], class_test=True, resolve=resolve) is None, node_id


def test_a_nested_parameter_id_is_accepted_as_a_sites_class_test(render, tmp_path):
    """#306 regression: `test_x[a[b]]` is a valid pytest id, not `test_x[a`."""
    out, before = _repo(render, tmp_path)
    (out / "test_param.py").write_text(
        "import pytest\nfrom calc import add\n\n\n"
        "@pytest.mark.parametrize('p', ['a[b]'])\n"
        "def test_param(p):\n    assert add(1, 2) == 3\n", encoding="utf-8")
    r = _tool(out, "--work", "7", "--round", "1", "--before", before, "--cause", "add subtracted",
              "--sites", "calc.py:2", "--", sys.executable, "-m", "pytest", "test_param.py")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "red before, green after (1): test_param.py::test_param[a[b]]" in _journal(out)


def test_a_nested_parameter_id_is_accepted_in_a_junit_reference(render, tmp_path):
    """#306 regression on the JUnit path: the written reference keeps the whole id."""
    out, before = _repo(render, tmp_path)
    _files(out, {"tests/test_p.py": "def test_x(p):\n    assert True\n"})
    (out / "calc.spec.py").write_text(
        _junit_runner([("tests.test_p", "tests/test_p.py", "test_x[a[b]]", "fail", "pass")]),
        encoding="utf-8")
    r = _tool(out, "--work", "7", "--round", "1", "--before", before, "--junit", "report.xml",
              "--copy", "calc.spec.py", "--cause", "add subtracted", "--sites", "calc.py:2", "--",
              sys.executable, "calc.spec.py")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "red before, green after (1): tests/test_p.py::test_x[a[b]]" in _journal(out)
