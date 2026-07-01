import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

KENNI = ["Kenni", "KenniNext", "Seb", "Signal", "SvelteKit", "user_id=1", "surface:ios"]


def _render(render, tmp_path, **mods):
    m = {"git_hooks": True}
    m.update(mods)
    return render(tmp_path, {"project_name": "d", "modules": m})


def _runner(out: Path, *args):
    return subprocess.run(
        [sys.executable, str(out / "scripts/process/gate_runner.py"), *args],
        cwd=out, capture_output=True, text=True,
    )


def _failing_contract(out: Path):
    """Enable a hard-failing active gate: a contracts-drift pin/artifact mismatch."""
    (out / "contracts").mkdir(parents=True, exist_ok=True)
    (out / "contracts/api.json").write_bytes(b"NEW-bytes-edited")
    reg = out / "docs/process/contracts"
    reg.mkdir(parents=True, exist_ok=True)
    (reg / "orders-api.json").write_text(json.dumps({
        "id": "orders-api", "kind": "rest",
        "artifact": "contracts/api.json",
        "pin": "sha256:" + hashlib.sha256(b"OLD-bytes").hexdigest(),
    }))


def test_warn_mode_reports_but_exits_zero(render, tmp_path):
    out = _render(render, tmp_path, contracts_drift=True)
    _failing_contract(out)
    r = _runner(out, "--warn")
    assert r.returncode == 0, r.stdout
    assert "not blocking" in r.stdout
    assert "contracts-drift" in r.stdout


def test_without_warn_hard_fails(render, tmp_path):
    out = _render(render, tmp_path, contracts_drift=True)
    _failing_contract(out)
    r = _runner(out)
    assert r.returncode == 1
    assert "FAILED gates" in r.stdout


def test_list_unaffected(render, tmp_path):
    out = _render(render, tmp_path, contracts_drift=True)
    r = _runner(out, "--list")
    assert r.returncode == 0, r.stderr
    assert "contracts-drift" in r.stdout
    assert "not blocking" not in r.stdout


def test_answers_records_git_hooks(render, tmp_path):
    out = _render(render, tmp_path)
    assert "git_hooks: true" in (out / ".copier-answers.yml").read_text()


def _hook_env(**extra):
    # Ensure `python3` inside the hooks resolves to the venv python (has pyyaml).
    env = dict(os.environ)
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env["PATH"]
    env.update(extra)
    return env


def _git(out: Path, *args, **kw):
    return subprocess.run(["git", *args], cwd=out, capture_output=True, text=True, **kw)


def _init_repo(out: Path, install=True):
    _git(out, "init", "-q", "-b", "main", check=True)
    _git(out, "config", "user.email", "t@example.com", check=True)
    _git(out, "config", "user.name", "Test", check=True)
    (out / "seed.txt").write_text("x")
    _git(out, "add", "seed.txt", check=True)
    _git(out, "commit", "-q", "-m", "init", check=True)  # no hooks yet
    if install:
        r = subprocess.run(["bash", "scripts/process/install-hooks.sh"],
                           cwd=out, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        return r
    return None


def test_main_guard_blocks_and_escapes(render, tmp_path):
    out = _render(render, tmp_path)
    _init_repo(out)
    blocked = _git(out, "commit", "--allow-empty", "-m", "x", env=_hook_env())
    assert blocked.returncode != 0
    assert "blocked" in blocked.stderr
    ok = _git(out, "commit", "--allow-empty", "-m", "x", env=_hook_env(ALLOW_MAIN_COMMIT="1"))
    assert ok.returncode == 0, ok.stderr


def test_feature_branch_commit_allowed(render, tmp_path):
    out = _render(render, tmp_path)
    _init_repo(out)
    _git(out, "checkout", "-q", "-b", "feat", check=True)
    r = _git(out, "commit", "--allow-empty", "-m", "x", env=_hook_env())
    assert r.returncode == 0, r.stderr


def test_pre_push_runs_gate_and_bypass(render, tmp_path):
    out = _render(render, tmp_path, contracts_drift=True)
    _init_repo(out)
    _failing_contract(out)
    blocked = subprocess.run(["bash", ".git/hooks/pre-push"], cwd=out,
                             stdin=subprocess.DEVNULL, capture_output=True, text=True, env=_hook_env())
    assert blocked.returncode == 1, blocked.stdout
    bypass = subprocess.run(["bash", ".git/hooks/pre-push"], cwd=out,
                            stdin=subprocess.DEVNULL, capture_output=True, text=True,
                            env=_hook_env(SKIP_PUSH_GATE="1"))
    assert bypass.returncode == 0


def test_post_commit_warns_never_blocks(render, tmp_path):
    out = _render(render, tmp_path, contracts_drift=True)
    _init_repo(out)
    _failing_contract(out)
    r = subprocess.run(["bash", ".git/hooks/post-commit"], cwd=out,
                       capture_output=True, text=True, env=_hook_env())
    assert r.returncode == 0, r.stdout
    assert "not blocking" in r.stdout


def test_brownfield_foreign_hook_untouched(render, tmp_path):
    out = _render(render, tmp_path)
    _init_repo(out, install=False)
    foreign = out / ".git/hooks/pre-commit"
    foreign.parent.mkdir(parents=True, exist_ok=True)
    foreign.write_text("#!/bin/sh\necho FOREIGN\n")
    foreign.chmod(0o755)
    r = subprocess.run(["bash", "scripts/process/install-hooks.sh"],
                       cwd=out, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert foreign.read_text() == "#!/bin/sh\necho FOREIGN\n"
    assert "not dev-process-managed" in r.stderr
    assert (out / ".git/hooks/pre-push").exists()  # non-conflicting hooks still installed


def test_installer_idempotent(render, tmp_path):
    out = _render(render, tmp_path)
    _init_repo(out)  # installs once
    r = subprocess.run(["bash", "scripts/process/install-hooks.sh"],
                       cwd=out, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "dev-process-managed-hook" in (out / ".git/hooks/pre-commit").read_text()


def test_installer_absent_when_module_off(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    assert not (out / "scripts/process/install-hooks.sh").exists()
