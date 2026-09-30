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
    assert "red before, green after (1): test_add" in text  # test_zero passes on both sides
    assert "ROOT-CAUSE work=7 round=1: add subtracted instead of adding — test_add" in text


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
