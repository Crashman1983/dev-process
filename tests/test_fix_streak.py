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


def _bundle(out: Path) -> str:
    r = subprocess.run([sys.executable, str(out / "scripts/process/make_review_bundle.py"),
                        "--base", "main", "--skip-preflight"],
                       cwd=out, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout


def test_the_note_lives_in_the_review_bundle_not_the_runner(render, tmp_path):
    """The runner hides a passing gate's output — a note-only gate there said nothing."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _git(out, "init", "-q", "-b", "main")
    _git(out, "config", "user.email", "t@t")
    _git(out, "config", "user.name", "t")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "base")
    _git(out, "checkout", "-q", "-b", "7-thing")
    r = subprocess.run([sys.executable, str(out / "scripts/process/gate_runner.py"), "--list"],
                       cwd=out, capture_output=True, text=True)
    assert r.returncode == 0 and "fix-streak" not in r.stdout, r.stdout
    _commit(out, "src.py", "fix: a")
    assert "Fix streak" not in _bundle(out) and "fix-streak" not in _bundle(out)
    _commit(out, "src.py", "fix: b")
    text = _bundle(out)
    assert "## Fix streak\nfix-streak: note: 2 fix commits on src.py" in text, text[:2000]


def test_a_crashing_streak_check_does_not_block_the_bundle(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _git(out, "init", "-q", "-b", "main")
    _git(out, "config", "user.email", "t@t")
    _git(out, "config", "user.name", "t")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "base")
    (out / "scripts/process/check_fix_streak.py").write_text("raise SystemExit('boom')\n")

    assert "fix-streak: not evaluated (boom)" in _bundle(out)


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


def test_a_shared_changelog_is_no_owner_at_two(render, tmp_path):
    """Refute F8: two unrelated fixes that both touch the CHANGELOG are no pattern."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _git(out, "init", "-q", "-b", "main")
    _git(out, "config", "user.email", "t@t")
    _git(out, "config", "user.name", "t")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "base")
    _git(out, "checkout", "-q", "-b", "7-thing")
    for name in ("b.py", "c.py"):
        (out / name).write_text("x\n")
        p = out / "CHANGELOG.md"
        p.write_text((p.read_text() if p.exists() else "") + name + "\n")
        _git(out, "add", "-A")
        _git(out, "commit", "-q", "-m", f"fix: {name}")
    gate = [sys.executable, str(out / "scripts/process/check_fix_streak.py"), "."]
    r = subprocess.run(gate, cwd=out, capture_output=True, text=True)
    assert "CHANGELOG.md" not in r.stdout, r.stdout


def test_breaking_fix_subjects_count(render, tmp_path):
    """Refute F8 (pre-existing): `fix!:` is a conventional fix too."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _git(out, "init", "-q", "-b", "main")
    _git(out, "config", "user.email", "t@t")
    _git(out, "config", "user.name", "t")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "base")
    _git(out, "checkout", "-q", "-b", "7-thing")
    for subject in ("fix!: a", "fix(core)!: b"):
        _commit(out, "a.py", subject)
    gate = [sys.executable, str(out / "scripts/process/check_fix_streak.py"), "."]
    r = subprocess.run(gate, cwd=out, capture_output=True, text=True)
    assert "2 fix commits on a.py" in r.stdout, r.stdout


def test_a_process_doc_fixed_twice_is_an_owner(render, tmp_path):
    """G4: the process rules live in Markdown — two fixes on one rule file are a pattern."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _git(out, "init", "-q", "-b", "main")
    _git(out, "config", "user.email", "t@t")
    _git(out, "config", "user.name", "t")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "base")
    _git(out, "checkout", "-q", "-b", "7-thing")
    for subject in ("fix(refute): a", "fix(refute): b"):
        _commit(out, "docs/process/refute.md", subject)
    gate = [sys.executable, str(out / "scripts/process/check_fix_streak.py"), "."]
    r = subprocess.run(gate, cwd=out, capture_output=True, text=True)
    assert "2 fix commits on docs/process/refute.md" in r.stdout, r.stdout
