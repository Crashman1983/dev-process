"""The merge guard on real pushes: git's pre-push ref lines, not the environment.

A refutation of the first port pushed through real pre-commit to a bare
remote: pre-commit hands its hooks only the FIRST ref line with something to
push (`git push origin HEAD:main feature` moved main), runs no hook at all for
a published commit pushed onto main (`git push -f origin feature:main`), a
forged `PROCESS_PUSH_TARGETS` hid main, a remote not named `origin` let a
block through, and `PROCESS_PHASE=Review` was no review. The guard now reads
git's lines as `pre-push.legacy` (install_hooks.py) — these tests push for
real, through the guard alone and through pre-commit where it is available.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

BLOCK = ("REVIEW work=2168 tier=1 reviewer=fresh-agent model=same "
         "independence=bundle,non-implementing,single-family verdict=block round=2\n")


def _env(extra: dict | None = None) -> dict:
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("PROCESS_", "PRE_COMMIT", "SKIP", "GIT_"))}
    return {**env, **(extra or {})}


def _git(root: Path, *args: str, env: dict | None = None, check: bool = True):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                          env=_env(env), check=check)


def _push(root: Path, *args: str, env: dict | None = None):
    return _git(root, "push", *args, env=env, check=False)


def _remote_head(bare: Path, ref: str = "main") -> str:
    r = subprocess.run(["git", "--git-dir", str(bare), "rev-parse", "--verify", "-q", ref],
                       capture_output=True, text=True)
    return r.stdout.strip()


def _project(render, tmp_path: Path, *, remote: str = "origin", empty_remote: bool = False,
             drop_gates: bool = False) -> tuple[Path, Path]:
    out = render(tmp_path / "work", {"project_name": "d", "modules": {"git_hooks": True}})
    if drop_gates:
        # these tests are about the guard; the gate runner has its own
        cfg_path = out / ".pre-commit-config.yaml"
        cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
        cfg["repos"] = [r for r in cfg["repos"] if r["repo"] == "local"]
        for r in cfg["repos"]:
            r["hooks"] = [h for h in r["hooks"] if h["id"] != "process-gates"]
        cfg_path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    bare = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True)
    _git(out, "init", "-q", "-b", "main")
    _git(out, "config", "user.email", "t@t")
    _git(out, "config", "user.name", "t")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "base")
    _git(out, "remote", "add", remote, str(bare))
    if not empty_remote:
        _git(out, "push", "-q", "--no-verify", remote, "main")
    _git(out, "checkout", "-q", "-b", "feature")
    (out / "code.py").write_text("x = 1\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "feat: code")
    return out, bare


def _install_guard(out: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "scripts/process/install_hooks.py"], cwd=out,
                          capture_output=True, text=True, env=_env())


# --- the guard alone (a project without pre-commit, or before it) -----------------------

@pytest.fixture
def guarded(render, tmp_path):
    out, bare = _project(render, tmp_path)
    r = _install_guard(out)
    assert r.returncode == 0, r.stderr
    assert (out / ".git/hooks/pre-push").is_file()
    return out, bare


def test_a_main_line_behind_a_branch_line_is_seen(guarded):
    # finding 1: the second ref line is main; pre-commit only named the first
    out, bare = guarded
    assert _push(out, "-q", "origin", "feature").returncode == 0
    (out / "code.py").write_text("x = 2\n")
    _git(out, "commit", "-qam", "feat: more")
    before = _remote_head(bare)
    r = _push(out, "origin", "feature", "HEAD:main")
    assert r.returncode != 0 and "merge_route" in r.stderr, r.stderr
    assert _remote_head(bare) == before


def test_a_published_branch_force_pushed_onto_main_is_refused(guarded):
    # finding 3: the commit is already on the remote — pre-commit ran no hook at all
    out, bare = guarded
    assert _push(out, "-q", "origin", "feature").returncode == 0
    before = _remote_head(bare)
    r = _push(out, "-f", "origin", "feature:main")
    assert r.returncode != 0 and "merge_route" in r.stderr, r.stderr
    assert _remote_head(bare) == before


def test_a_forged_target_variable_does_not_hide_main(guarded):
    # finding 5: the variable can add a target, never replace git's lines
    out, bare = guarded
    before = _remote_head(bare)
    r = _push(out, "origin", "HEAD:main", env={"PROCESS_PUSH_TARGETS": "refs/heads/feature"})
    assert r.returncode != 0 and "merge_route" in r.stderr, r.stderr
    assert _remote_head(bare) == before


@pytest.mark.parametrize("phase", ["Review", "PLAN", "bogus"])
def test_an_unvalidated_phase_is_refused(guarded, phase):
    # finding 11: `Review` is a review; a value that names no phase cannot be told
    out, bare = guarded
    before = _remote_head(bare)
    r = _push(out, "origin", "HEAD:main",
              env={"PROCESS_PHASE": phase, "PROCESS_MERGE_ROUTE": "train"})
    assert r.returncode != 0 and "merge_route" in r.stderr, r.stderr
    assert _remote_head(bare) == before


def test_the_named_route_moves_main(guarded):
    out, bare = guarded
    r = _push(out, "origin", "HEAD:main",
              env={"PROCESS_MERGE_ROUTE": "finish", "PROCESS_PHASE": "Execute"})
    assert r.returncode == 0, r.stderr
    assert _remote_head(bare) == _git(out, "rev-parse", "HEAD").stdout.strip()


def _block_on_feature(out: Path) -> None:
    (out / ".process-work/journal").mkdir(parents=True, exist_ok=True)
    (out / ".process-work/journal/2026-09-28.md").write_text(BLOCK)
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "docs: attest (#2168)")


@pytest.mark.parametrize("remote", ["origin", "upstream"])
def test_a_block_does_not_ride_a_finish_push_whatever_the_remote_is_called(
        render, tmp_path, remote):
    # finding 4: the base is the remote's SHA on the ref line, not a local main
    # already fast-forwarded onto the pushed commit
    out, bare = _project(render, tmp_path, remote=remote)
    assert _install_guard(out).returncode == 0
    _block_on_feature(out)
    _git(out, "checkout", "-q", "main")
    _git(out, "merge", "-q", "--ff-only", "feature")
    before = _remote_head(bare)
    r = _push(out, remote, "main", env={"PROCESS_MERGE_ROUTE": "finish"})
    assert r.returncode != 0 and "verdict=block" in r.stderr, r.stderr
    assert _remote_head(bare) == before


@pytest.mark.parametrize("block", [True, False])
def test_a_push_that_creates_main_carries_every_block_at_its_tip(render, tmp_path, block):
    out, bare = _project(render, tmp_path, empty_remote=True)
    assert _install_guard(out).returncode == 0
    if block:
        _block_on_feature(out)
    r = _push(out, "origin", "HEAD:main", env={"PROCESS_MERGE_ROUTE": "finish"})
    assert (r.returncode != 0) is block, r.stderr
    assert bool(_remote_head(bare)) is not block


def test_a_skipped_gate_is_logged_and_skips_the_block_check(render, tmp_path):
    # the owner's emergency exit keeps its old shape: logged, not a route for agents
    out, bare = _project(render, tmp_path)
    assert _install_guard(out).returncode == 0
    _block_on_feature(out)
    r = _push(out, "origin", "HEAD:main", env={"SKIP": "process-gates"})
    assert r.returncode == 0, r.stderr
    assert "SKIP=process-gates" in (out / ".git/process-owner-overrides.log").read_text()


def test_a_missing_guard_script_refuses_only_main(guarded):
    out, bare = guarded
    (out / "scripts/process/merge_route.py").unlink()
    assert _push(out, "-q", "origin", "feature").returncode == 0
    r = _push(out, "origin", "HEAD:main", env={"PROCESS_MERGE_ROUTE": "finish"})
    assert r.returncode != 0 and "push to main refused" in r.stderr


def test_the_installer_is_idempotent_and_leaves_a_foreign_hook_alone(render, tmp_path):
    out, _bare = _project(render, tmp_path)
    assert _install_guard(out).returncode == 0
    assert _install_guard(out).returncode == 0
    hook = out / ".git/hooks/pre-push"
    hook.write_text("#!/bin/sh\nexit 0\n")
    r = _install_guard(out)
    assert r.returncode == 1 and "another hook" in r.stderr
    assert hook.read_text() == "#!/bin/sh\nexit 0\n"


# --- through the real pre-commit framework --------------------------------------------

def _pre_commit_available() -> bool:
    return shutil.which("uvx") is not None


@pytest.fixture
def framework(render, tmp_path):
    if not _pre_commit_available():
        pytest.skip("uvx (pre-commit) not available")
    out, bare = _project(render, tmp_path, drop_gates=True)
    r = subprocess.run(["uvx", "pre-commit", "install", "--hook-type", "pre-push"], cwd=out,
                       capture_output=True, text=True, env=_env())
    if r.returncode != 0:
        pytest.skip(f"pre-commit install failed here: {r.stderr[-300:]}")
    return out, bare


@pytest.mark.parametrize("order", ["guard-after", "guard-before"])
def test_through_pre_commit_the_guard_sees_every_line(render, tmp_path, order):
    if not _pre_commit_available():
        pytest.skip("uvx (pre-commit) not available")
    out, bare = _project(render, tmp_path, drop_gates=True)
    if order == "guard-before":
        assert _install_guard(out).returncode == 0
    r = subprocess.run(["uvx", "pre-commit", "install", "--hook-type", "pre-push"], cwd=out,
                       capture_output=True, text=True, env=_env())
    if r.returncode != 0:
        pytest.skip(f"pre-commit install failed here: {r.stderr[-300:]}")
    if order == "guard-after":
        assert _install_guard(out).returncode == 0
    assert (out / ".git/hooks/pre-push.legacy").is_file()
    before = _remote_head(bare)
    assert _push(out, "-q", "origin", "feature").returncode == 0
    forced = _push(out, "-f", "origin", "feature:main")          # finding 3
    assert forced.returncode != 0 and "merge_route" in forced.stderr, forced.stderr
    (out / "code.py").write_text("x = 3\n")
    _git(out, "commit", "-qam", "feat: more")
    second = _push(out, "origin", "feature", "HEAD:main")       # finding 1
    assert second.returncode != 0 and "merge_route" in second.stderr, second.stderr
    assert _remote_head(bare) == before
    ok = _push(out, "origin", "HEAD:main", env={"PROCESS_MERGE_ROUTE": "train"})
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert not list((out / ".git/process-merge-guard").iterdir())  # the stamp was consumed


def test_through_pre_commit_without_the_guard_main_is_refused(framework):
    out, bare = framework
    before = _remote_head(bare)
    r = _push(out, "origin", "HEAD:main", env={"PROCESS_MERGE_ROUTE": "train"})
    assert r.returncode != 0 and "install_hooks.py" in (r.stdout + r.stderr)
    assert _remote_head(bare) == before
    assert _push(out, "-q", "origin", "feature").returncode == 0  # a branch push: a note
