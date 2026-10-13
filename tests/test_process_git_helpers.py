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
           "GIT_EDITOR": "vi", "PATH": "/bin"}
    pg.drop_local_env(env)
    assert env == {"GIT_EDITOR": "vi", "PATH": "/bin"}
    monkeypatch.setenv("PATH", "")  # no git to ask
    assert pg.local_env_vars() == pg.LOCAL_ENV_VARS
