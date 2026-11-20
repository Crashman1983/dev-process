"""process_git helpers shared by the selector, the gate runner and the pre-push frame (#206)."""
import importlib.util
import sys
from pathlib import Path

import pytest

PROC = Path(__file__).resolve().parents[1] / "template/scripts/process"


def _pg():
    before = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec = importlib.util.spec_from_file_location("process_git_t", PROC / "process_git.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        sys.dont_write_bytecode = before
    return mod


@pytest.mark.parametrize("pattern, path, caps", [
    ("backend/src/app/{pkg}/{sub}/**", "backend/src/app/api/users/views.py", {"pkg": "api", "sub": "users"}),
    ("backend/src/app/{pkg}/{sub}/**", "backend/src/app/api/views.py", None),  # {sub} must be a directory
    ("backend/", "backend", None),                                            # the prefix, not the name
    ("backend/", "backend/tests/x.py", {}),                                   # a trailing / is the prefix
    ("backend/", "backendx/a.py", None),
    ("backend/tests/**/test_*.py", "backend/tests/test_a.py", {}),           # ** may be empty
    ("backend/tests/**/test_*.py", "backend/tests/a/b/test_c.py", {}),
    ("src/*.ts", "src/a/b.ts", None),                                         # * stays in its segment
    ("Makefile", "Makefile", {}),
    ("Makefile", "makefile", None),                                           # case counts everywhere
    ("{a}/{a}", "x/x", {"a": "x"}),
    ("{a}/{a}", "x/y", None),
    ("docs/*.md", "docs/a b.md", {}),
])
def test_one_glob_for_maps_pins_and_triggers(pattern, path, caps):
    assert _pg().path_captures(pattern, path) == caps


def test_a_hooks_repo_local_variables_are_dropped_and_the_rest_kept(monkeypatch):
    """#219: git's own list, its static copy when git cannot answer."""
    pg = _pg()
    env = {"GIT_DIR": "/r/.git", "GIT_INDEX_FILE": "/r/.git/index", "GIT_COMMON_DIR": "/r/.git",
           "GIT_EDITOR": "vi", "PATH": "/bin", "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "a.b",
           "GIT_CONFIG_VALUE_0": "c", "GIT_CONFIG_PARAMETERS": "'x.y'='z'"}
    pg.drop_local_env(env)
    # config passed by environment stays, as git keeps it for another repository
    assert env == {"GIT_EDITOR": "vi", "PATH": "/bin", "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "a.b",
                   "GIT_CONFIG_VALUE_0": "c", "GIT_CONFIG_PARAMETERS": "'x.y'='z'"}
    monkeypatch.setenv("PATH", "")  # no git to ask
    assert pg.local_env_vars() == pg.LOCAL_ENV_VARS


def _usage(used: int, free: int):
    import collections
    return collections.namedtuple("usage", "total used free")(used + free, used, free)


@pytest.mark.parametrize("used, free, limit, full", [
    (95, 5, None, True), (90, 10, None, True), (89, 11, None, False),  # the default: 90 %
    (50, 50, "50", True), (49, 51, "50", False), (99, 1, "100", False), (100, 0, "100", True),
])
def test_disk_use_reads_the_use_and_the_limit(monkeypatch, used, free, limit, full):
    """v2.98 B1: one reader of the disk for dispatch and the train — use = used / (used +
    free), as `df` counts it; full at or over the limit (`PROCESS_DISK_LIMIT_PCT`, 90)."""
    pg = _pg()
    if limit is None:
        monkeypatch.delenv(pg.DISK_LIMIT_ENV, raising=False)
    else:
        monkeypatch.setenv(pg.DISK_LIMIT_ENV, limit)
    monkeypatch.setattr(pg.shutil, "disk_usage", lambda p: _usage(used, free))
    got = pg.disk_use(Path("/x"))
    assert got.use_pct == pytest.approx(used) and got.problem is None and got.full is full
    assert got.free == free and got.limit == float(limit or 90)
    assert pg.disk_full_line(Path("/x"), got.use_pct) == f"disk-full /x {used}%"


@pytest.mark.parametrize("value", ["abc", "0", "-5", "150", "nan", "inf"])
def test_a_misconfigured_disk_limit_is_a_problem_never_full(monkeypatch, value):
    pg = _pg()
    monkeypatch.setenv(pg.DISK_LIMIT_ENV, value)
    monkeypatch.setattr(pg.shutil, "disk_usage", lambda p: _usage(100, 0))
    got = pg.disk_use(Path("/x"))
    assert not got.full and got.use_pct is None and got.limit is None
    assert pg.DISK_LIMIT_ENV in got.problem and repr(value) in got.problem
    # the train's reading (`fallback`): the default limit holds, the problem still named
    fallen = pg.disk_use(Path("/x"), fallback=True)
    assert fallen.full and fallen.use_pct == pytest.approx(100) and fallen.limit == 90
    assert fallen.problem == got.problem


def test_an_unreadable_disk_use_is_a_problem_never_full(monkeypatch):
    pg = _pg()
    monkeypatch.delenv(pg.DISK_LIMIT_ENV, raising=False)

    def broken(_p):
        raise OSError(5, "I/O error")
    monkeypatch.setattr(pg.shutil, "disk_usage", broken)
    got = pg.disk_use(Path("/x"))
    assert not got.full and got.use_pct is None and "I/O error" in got.problem and got.limit == 90


def test_a_disk_full_line_is_known_by_its_first_word():
    pg = _pg()
    assert pg.is_disk_full_line("disk-full /tmp 97%")
    assert not pg.is_disk_full_line("disk-fullish /tmp") and not pg.is_disk_full_line("lane-busy full x")
    assert not pg.is_disk_full_line("")


def _repo(path: Path) -> Path:
    import subprocess
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    (path / ".gitignore").write_text("*.bundle.md\nnested/\n")
    return path


def test_git_ignored_names_what_git_ignores_and_none_when_git_cannot_tell(tmp_path, monkeypatch):
    """#421: one owner of "does git ignore these paths" — the review gate, the issue gate and
    the bundle asked git each in their own way. None is "git cannot tell", never "nothing"."""
    pg = _pg()
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    root = _repo(tmp_path / "r")
    rels = ["a.bundle.md", "plan.md", "nested/x.md", "sub dir/b.bundle.md"]
    assert pg.git_ignored(root, rels) == {"a.bundle.md", "nested/x.md", "sub dir/b.bundle.md"}
    assert pg.git_ignored(root, ["plan.md"]) == set()  # git told: none is ignored
    assert pg.git_ignored(root, []) == set()
    outside = tmp_path / "plain"
    outside.mkdir()
    assert pg.git_ignored(outside, ["a.bundle.md"]) is None  # no repository
    monkeypatch.setenv("PATH", "")
    assert pg.git_ignored(root, ["a.bundle.md"]) is None  # no git


def test_git_ignored_reads_with_the_process_git_environment(tmp_path, monkeypatch):
    pg = _pg()
    seen = {}

    def run(argv, **kw):
        seen.update(argv=argv, **kw)
        raise pg.subprocess.TimeoutExpired(argv, kw["timeout"])
    monkeypatch.setattr(pg.subprocess, "run", run)
    assert pg.git_ignored(tmp_path, ["a"]) is None  # a timeout is "cannot tell"
    assert seen["argv"][-3:] == ["check-ignore", "-z", "--stdin"] and seen["timeout"] == 60
    assert seen["env"]["GIT_NO_REPLACE_OBJECTS"] == "1"


def test_the_ignore_readers_ask_the_one_owner():
    # check_speckit asks another question (which pattern ignores a path, `-v --no-index`)
    for name in ("check_review.py", "make_review_bundle.py",
                 "{% if modules.github_issues %}check_issues.py{% endif %}.jinja"):
        src = (PROC / name).read_text(encoding="utf-8")
        assert "check-ignore" not in src and "git_ignored(" in src, name
