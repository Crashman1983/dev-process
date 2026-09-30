"""fix-streak: the second fix commit on one file asks increment vs. rewrite
(rule 4), the third names the missing root cause (rule 6)."""
import subprocess
import sys
from pathlib import Path


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def _commit(root: Path, name: str, subject: str) -> None:
    p = root / name
    p.write_text(p.read_text() + "x\n" if p.exists() else "x\n")
    _git(root, "add", name)
    _git(root, "commit", "-q", "-m", subject)


def test_third_fix_on_one_file_is_named_and_never_blocks(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _git(out, "init", "-q", "-b", "main")
    _git(out, "config", "user.email", "t@t")
    _git(out, "config", "user.name", "t")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "base")
    _git(out, "checkout", "-q", "-b", "7-thing")
    for subject in ("fix: a", "fix(core): b", "fixup! not a fix", "fixture: not a fix"):
        _commit(out, "src.py", subject)
    gate = [sys.executable, str(out / "scripts/process/check_fix_streak.py"), "."]
    r = subprocess.run(gate, cwd=out, capture_output=True, text=True)
    # two real fixes: the structural question before the third patch (rule 4)
    assert r.returncode == 0
    assert "fix-streak: note: 2 fix commits on src.py" in r.stdout and "rule 4" in r.stdout
    assert "increment" in r.stdout and "DECISION" in r.stdout
    _commit(out, "src.py", "fix: c")
    r = subprocess.run(gate, cwd=out, capture_output=True, text=True)
    assert r.returncode == 0
    assert "fix-streak: note: 3 fix commits on src.py" in r.stdout and "rule 6" in r.stdout
    # the runner lists it as a core gate
    r = subprocess.run([sys.executable, str(out / "scripts/process/gate_runner.py")],
                       cwd=out, capture_output=True, text=True)
    assert r.returncode == 0 and "fix-streak" in r.stdout


def test_one_fix_each_on_two_files_stays_quiet(render, tmp_path):
    """The note is about the same owner hit twice, not about two fixes anywhere."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _git(out, "init", "-q", "-b", "main")
    _git(out, "config", "user.email", "t@t")
    _git(out, "config", "user.name", "t")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "base")
    _git(out, "checkout", "-q", "-b", "7-thing")
    _commit(out, "a.py", "fix: a")
    _commit(out, "b.py", "fix: b")
    gate = [sys.executable, str(out / "scripts/process/check_fix_streak.py"), "."]
    r = subprocess.run(gate, cwd=out, capture_output=True, text=True)
    assert r.returncode == 0 and "fix-streak: OK" in r.stdout, r.stdout
