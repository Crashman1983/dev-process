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
