"""certificate.py (#206): evidence paid once, only for a tree it describes."""
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

PROC = Path(__file__).resolve().parents[1] / "template/scripts/process"


def _cert():
    before = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(PROC))
    try:
        spec = importlib.util.spec_from_file_location("certificate_t", PROC / "certificate.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        sys.path.remove(str(PROC))
        sys.dont_write_bytecode = before
    return mod


def _git(root, *args):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "r"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@t")
    _git(root, "config", "user.name", "t")
    _git(root, "config", "commit.gpgsign", "false")
    (root / "a.py").write_text("a = 1\n")
    (root / ".gitignore").write_text("build/\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    return root


def _write(c, root, kind="push", evidence="pytest -q", **kw):
    return c.write(root, kind, evidence, before_tree=c.evidence_tree(root), writer="test", **kw)


def test_a_green_run_on_a_clean_tree_is_found_with_its_record(repo, capsys):
    c = _cert()
    ok, _path = _write(c, repo)
    assert ok
    rec = c.find(repo, ("push",), {"push": "pytest -q"})
    assert rec and rec["kind"] == "push" and rec["writer"] == "test"
    assert "push certificate of tree" in c.describe(rec)
    assert c.find(repo, ("push",), {"push": "pytest -q -x"}) is None  # another command: no evidence


def test_a_bookkeeping_commit_keeps_the_certificate(repo):
    c = _cert()
    assert _write(c, repo)[0]
    (repo / ".process-work/journal").mkdir(parents=True)
    (repo / ".process-work/journal/d.md").write_text("REVIEW …\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "attest")
    assert c.find(repo, ("push",), {"push": "pytest -q"})
    (repo / "a.py").write_text("a = 2\n")
    _git(repo, "commit", "-qam", "code")
    assert c.find(repo, ("push",), {"push": "pytest -q"}) is None


@pytest.mark.parametrize("dirt", ["tracked", "untracked", "changed-tree", "makeflags", "listed-env"])
def test_no_certificate_for_a_run_that_proves_nothing(repo, monkeypatch, dirt):
    """Downstream #2474: an untracked conftest or a MAKEFLAGS override changed what ran."""
    c = _cert()
    before = c.evidence_tree(repo)
    if dirt == "tracked":
        (repo / "a.py").write_text("a = 3\n")
    elif dirt == "untracked":
        (repo / "conftest.py").write_text("import pytest\n")
    elif dirt == "changed-tree":
        (repo / "a.py").write_text("a = 4\n")
        _git(repo, "commit", "-qam", "during the run")
    elif dirt == "makeflags":
        monkeypatch.setenv("MAKEFLAGS", "-j4 MERGE_SUITE_STEPS=")
    else:
        monkeypatch.setenv("PYTEST_ADDOPTS", "-k nothing")
    ok, why = c.write(repo, "push", "pytest -q", before_tree=before, writer="t", env_names=["PYTEST_ADDOPTS"])
    assert not ok and why, why
    assert c.find(repo, ("push",), {"push": "pytest -q"}) is None


@pytest.mark.parametrize("flags,named", [
    ("is", "-i"), ("k -j4", "-k"), ("s -- PIN=x", "assignment"), ("-n", "-n"), ("-wt", "-t"),
    ("--eval=override\\ PIN:=evil", "--eval"), ("-E override\\ PIN:=evil", "-E"),
    ("-o stale.o", "-o"), ("--assume-old=x", "--assume-old"), ("--keep-going", "--keep-going"),
    ("e", "-e"), ("--ignore-err", "--ignore-err"), ("--keep-go", "--keep-go"), ("--env", "--env"),
    ("--dry", "--dry"), ("--tou", "--tou"),
])
def test_makeflags_that_change_what_ran_certify_nothing(repo, monkeypatch, flags, named):
    """Downstream #2149: `make -i` (MAKEFLAGS=is) or `--eval` certified a run the suite never did."""
    c = _cert()
    monkeypatch.setenv("MAKEFLAGS", flags)
    ok, why = _write(c, repo)
    assert not ok and named in why, why


@pytest.mark.parametrize("flags", ["s", "w -j4 --no-print-directory", "-j4", "-Otarget", "--jobs=4",
                                   "-l2 -j4", "-C sub", " -j4 --jobserver-auth=fifo:/tmp/x",
                                   "--output-sync=target"])
def test_makeflags_that_only_shape_the_run_still_certify(repo, monkeypatch, flags):
    c = _cert()
    monkeypatch.setenv("MAKEFLAGS", flags)
    assert _write(c, repo)[0], flags


def test_ignored_files_and_makeflags_without_assignment_do_not_block(repo, monkeypatch):
    c = _cert()
    (repo / "build").mkdir()
    (repo / "build/out.txt").write_text("x")
    monkeypatch.setenv("MAKEFLAGS", "-j4 --no-print-directory")
    assert _write(c, repo)[0]


def test_a_failing_git_status_writes_nothing(repo, monkeypatch):
    c = _cert()
    before = c.evidence_tree(repo)
    real = c._git
    monkeypatch.setattr(c, "_git", lambda root, *a, **kw: subprocess.CompletedProcess(a, 128, b"", b"boom")
                        if a[:1] == ("status",) else real(root, *a, **kw))
    ok, why = c.write(repo, "push", "pytest -q", before_tree=before, writer="t")
    assert not ok and "git status failed" in why


def test_the_store_keeps_the_newest(repo, monkeypatch):
    c = _cert()
    monkeypatch.setattr(c, "KEPT", 3)
    for i in range(5):
        assert _write(c, repo, evidence=f"cmd {i}")[0]
        os.utime(c._store(repo, "push") / f"{c.evidence_tree(repo)}-{c.evidence_hash(f'cmd {i}')}", (i, i))
    _write(c, repo, evidence="cmd 5")
    assert len([p for p in c._store(repo, "push").iterdir() if not p.name.startswith(".")]) == 3


def test_a_merge_certificate_serves_a_branch_push(repo):
    c = _cert()
    assert _write(c, repo, kind="merge", evidence="make test-merge")[0]
    rec = c.find(repo, ("push", "merge"), {"push": "stacks", "merge": "make test-merge"})
    assert rec and rec["kind"] == "merge"
    assert c.find(repo, ("merge",), {"merge": "make other"}) is None
