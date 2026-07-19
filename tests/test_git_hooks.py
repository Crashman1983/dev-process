import hashlib
import importlib.util
import io
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


def _load_run_hook(out: Path):
    path = out / "scripts/process/run_hook.py"
    spec = importlib.util.spec_from_file_location("rendered_run_hook", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_main_guard_blocks_and_escapes(render, tmp_path):
    out = _render(render, tmp_path)
    _init_repo(out)
    blocked = _git(out, "commit", "--allow-empty", "-m", "x", env=_hook_env())
    assert blocked.returncode != 0
    assert "blocked" in blocked.stderr
    ok = _git(out, "commit", "--allow-empty", "-m", "x", env=_hook_env(ALLOW_MAIN_COMMIT="1"))
    assert ok.returncode == 0, ok.stderr


def test_main_guard_blocks_first_commit_on_unborn_main(render, tmp_path):
    # audit: on an unborn branch, `rev-parse --abbrev-ref HEAD` printed "HEAD",
    # so the very first commit on main slipped past the guard.
    out = _render(render, tmp_path)
    _git(out, "init", "-q", "-b", "main", check=True)
    _git(out, "config", "user.email", "t@example.com", check=True)
    _git(out, "config", "user.name", "Test", check=True)
    r = subprocess.run(["bash", "scripts/process/install-hooks.sh"],
                       cwd=out, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    blocked = _git(out, "commit", "--allow-empty", "-m", "first", env=_hook_env())
    assert blocked.returncode != 0
    assert "blocked" in blocked.stderr


def test_installer_refuses_custom_hooks_path(render, tmp_path):
    # audit: with core.hooksPath set (possibly globally), the installer wrote
    # the hooks there — silently machine-wide for global configs.
    out = _render(render, tmp_path)
    _init_repo(out, install=False)
    elsewhere = tmp_path / "elsewhere-hooks"
    _git(out, "config", "core.hooksPath", str(elsewhere), check=True)
    r = subprocess.run(["bash", "scripts/process/install-hooks.sh"],
                       cwd=out, capture_output=True, text=True)
    assert r.returncode != 0
    assert "hooksPath" in r.stderr
    assert not elsewhere.exists()


def test_feature_branch_commit_allowed(render, tmp_path):
    out = _render(render, tmp_path)
    _init_repo(out)
    _git(out, "checkout", "-q", "-b", "feat", check=True)
    r = _git(out, "commit", "--allow-empty", "-m", "x", env=_hook_env())
    assert r.returncode == 0, r.stderr


def test_pre_push_gates_pushed_commit_and_bypass(render, tmp_path):
    out = _render(render, tmp_path, contracts_drift=True)
    _init_repo(out)
    # Commit a failing state on a feature branch; the hook gates the pushed
    # commits (fed on stdin), not the working tree.
    _git(out, "checkout", "-q", "-b", "feat", check=True)
    _failing_contract(out)
    _git(out, "add", "-A", check=True)
    _git(out, "commit", "-q", "-m", "bad", env=_hook_env(), check=True)
    bad = _git(out, "rev-parse", "HEAD", check=True).stdout.strip()
    refs = f"refs/heads/feat {bad} refs/heads/feat {'0' * 40}\n"
    blocked = subprocess.run(["bash", ".git/hooks/pre-push"], cwd=out,
                             input=refs, capture_output=True, text=True, env=_hook_env())
    assert blocked.returncode == 1, blocked.stdout + blocked.stderr
    bypass = subprocess.run(["bash", ".git/hooks/pre-push"], cwd=out,
                            input=refs, capture_output=True, text=True,
                            env=_hook_env(SKIP_PUSH_GATE="1"))
    assert bypass.returncode == 0


def test_pre_push_ignores_dirty_working_tree(render, tmp_path):
    out = _render(render, tmp_path, contracts_drift=True)
    _init_repo(out)
    _git(out, "checkout", "-q", "-b", "feat", check=True)
    # A clean, gate-passing committed tip ...
    _git(out, "commit", "--allow-empty", "-q", "-m", "ok", env=_hook_env(), check=True)
    good = _git(out, "rev-parse", "HEAD", check=True).stdout.strip()
    # ... with a failing but *uncommitted* working tree must not block the push:
    # the hook gates the pushed tip in an isolated worktree, not this tree.
    _failing_contract(out)
    refs = f"refs/heads/feat {good} refs/heads/feat {'0' * 40}\n"
    r = subprocess.run(["bash", ".git/hooks/pre-push"], cwd=out,
                       input=refs, capture_output=True, text=True, env=_hook_env())
    assert r.returncode == 0, r.stdout + r.stderr


def test_candidate_env_only_for_existing_protected_target(render, tmp_path):
    out = _render(render, tmp_path)
    hook = _load_run_hook(out)
    base = {"KEEP": "yes"}
    sha = "a" * 40

    main = hook._candidate_gate_env(base, "refs/heads/main", sha)
    assert main == {
        "KEEP": "yes",
        "DEV_PROCESS_CANDIDATE_BASE": sha,
        "DEV_PROCESS_CANDIDATE_TARGET": "refs/heads/main",
    }
    assert hook._candidate_gate_env(base, "refs/heads/feature", sha) == base
    assert hook._candidate_gate_env(base, "refs/heads/main", "0" * 40) == base
    assert base == {"KEEP": "yes"}, "helper must not mutate the shared environment"


def test_pre_push_forwards_remote_ref_and_sha(render, tmp_path, monkeypatch):
    out = _render(render, tmp_path)
    hook = _load_run_hook(out)
    local = "b" * 40
    remote = "a" * 40
    seen = []

    monkeypatch.setattr(hook, "_clean_git_env", lambda _root: {"BASE": "1"})
    monkeypatch.setattr(
        hook,
        "_gate_commit",
        lambda root, sha, env, remote_ref, remote_sha: seen.append(
            (root, sha, env, remote_ref, remote_sha)
        ) or 0,
    )
    monkeypatch.setattr(
        sys,
        "stdin",
        io.StringIO(
            f"refs/heads/main {local} refs/heads/main {remote}\n"
        ),
    )

    assert hook.pre_push(out) == 0
    assert seen == [(out, local, {"BASE": "1"}, "refs/heads/main", remote)]


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


def test_installer_from_subdir_lands_in_real_hookdir(render, tmp_path):
    """Run from a subdir of an ordinary checkout: hooks must land in the real
    .git/hooks and actually enforce — not a spurious <subdir>/.git/hooks with a
    false '✓ installed' (git --git-path returns a CWD-relative path)."""
    out = _render(render, tmp_path)
    _init_repo(out, install=False)
    sub = out / "pkg" / "nested"
    sub.mkdir(parents=True)
    script = out / "scripts/process/install-hooks.sh"
    r = subprocess.run(["bash", str(script)], cwd=sub, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert (out / ".git/hooks/pre-commit").exists(), r.stdout
    assert not (sub / ".git").exists(), "hooks written into a spurious subdir .git"
    blocked = _git(out, "commit", "--allow-empty", "-m", "x", env=_hook_env())
    assert blocked.returncode != 0
    assert "blocked" in blocked.stderr


def test_installer_absent_when_module_off(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    assert not (out / "scripts/process/install-hooks.sh").exists()


def test_module_doc_present_and_neutral(render, tmp_path):
    out = _render(render, tmp_path)
    doc = out / "docs/process/modules/git-hooks.md"
    assert doc.is_file()
    text = doc.read_text()
    for k in KENNI:
        assert k not in text, f"{k} leaked in git-hooks.md"


def test_module_doc_absent_when_off(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    assert not (out / "docs/process/modules/git-hooks.md").exists()


def test_docdrift_green_with_module_doc(render, tmp_path):
    out = render(tmp_path, {"project_name": "d",
                            "modules": {"doc_drift_gate": True, "git_hooks": True}})
    r = subprocess.run(
        [sys.executable, str(out / "scripts/process/check_doc_drift.py"), str(out)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stdout


def test_commits_md_no_unconditional_hook_promise(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})  # module OFF
    commits = (out / "docs/process/commits.md").read_text()
    assert "git-hooks" in commits
    assert "modules/git-hooks.md" not in commits
