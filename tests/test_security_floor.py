import json
import subprocess
import sys
from pathlib import Path

KENNI = ["Kenni", "KenniNext", "Seb", "Signal", "SvelteKit", "user_id=1", "surface:ios"]

CONFIG = "docs/process/security-floor.json"
SEED = "docs/process/security-floor.example.json"


def _render(render, tmp_path, **mods):
    m = {"security_floor": True}
    m.update(mods)
    return render(tmp_path, {"project_name": "d", "modules": m})


def _run(out: Path, root: Path, env: dict | None = None):
    return subprocess.run(
        [sys.executable, str(out / "scripts/process/check_security_floor.py"), str(root)],
        capture_output=True, text=True, env=env,
    )


def _git(d: Path, *args):
    subprocess.run(["git", *args], cwd=d, check=True, capture_output=True, text=True)


def _git_repo(d: Path):
    """A fresh git repo we fully control — the scan enumerates via git ls-files,
    so isolating it from the rendered tree keeps exactly our planted files in scope
    (mirrors parity's controlled-root pattern)."""
    d.mkdir(parents=True, exist_ok=True)
    _git(d, "init", "-q", "-b", "main")
    _git(d, "config", "user.email", "t@example.com")
    _git(d, "config", "user.name", "Test")


def _write_config(d: Path, cfg: dict):
    p = d / CONFIG
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cfg), encoding="utf-8")


def _write_config_text(d: Path, text: str):
    p = d / CONFIG
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _track(d: Path):
    _git(d, "add", "-A")
    _git(d, "commit", "-q", "-m", "x")


SHELL_RULE = {
    "rules": [
        {"id": "no-shell-true", "pattern": r"shell\s*=\s*True",
         "applies_to": ["*.py"], "message": "use a subprocess argv list, not shell=True"},
    ],
}


# --- ships / wiring -----------------------------------------------------------

def test_module_on_ships_gate_doc_seed(render, tmp_path):
    out = _render(render, tmp_path)
    assert (out / "scripts/process/check_security_floor.py").is_file()
    assert (out / "docs/process/modules/security-floor.md").is_file()
    assert (out / SEED).is_file()


def test_module_off_ships_nothing(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    assert not (out / "scripts/process/check_security_floor.py").exists()
    assert not (out / "docs/process/modules/security-floor.md").exists()
    # the seed is a single conditional-named file — module OFF ships nothing
    assert not (out / SEED).exists()


def test_answers_records_security_floor(render, tmp_path):
    out = _render(render, tmp_path)
    assert "security_floor: true" in (out / ".copier-answers.yml").read_text()


def test_gate_runner_lists_security_floor(render, tmp_path):
    out = _render(render, tmp_path)
    r = subprocess.run(
        [sys.executable, str(out / "scripts/process/gate_runner.py"), "--list"],
        cwd=out, capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    assert "security-floor" in r.stdout


# --- no-op / soft-note (exit 0, never faked) ----------------------------------

def test_no_config_is_noop(render, tmp_path):
    out = _render(render, tmp_path)
    empty = tmp_path / "empty_root"
    empty.mkdir()
    r = _run(out, empty)  # no config file at all
    assert r.returncode == 0, r.stdout
    assert "no security-floor config yet" in r.stdout


def test_git_unavailable_is_soft(render, tmp_path):
    out = _render(render, tmp_path)
    d = tmp_path / "nogit"  # a valid config, but NOT a git repo
    _write_config(d, SHELL_RULE)
    r = _run(out, d)
    assert r.returncode == 0, r.stdout
    assert "could not list tracked files" in r.stdout


# --- pattern scanning (needs a git repo with tracked files) -------------------

def test_pattern_match_hard_fails(render, tmp_path):
    out = _render(render, tmp_path)
    repo = tmp_path / "repo"
    _git_repo(repo)
    _write_config(repo, SHELL_RULE)
    (repo / "x.py").write_text("subprocess.run(cmd, shell=True)\n", encoding="utf-8")
    _track(repo)
    r = _run(out, repo)
    assert r.returncode == 1, r.stdout
    assert "x.py:1" in r.stdout
    assert "shell=True" in r.stdout
    assert "no-shell-true" in r.stdout


def test_clean_tree_passes(render, tmp_path):
    out = _render(render, tmp_path)
    repo = tmp_path / "repo"
    _git_repo(repo)
    _write_config(repo, SHELL_RULE)
    (repo / "x.py").write_text("subprocess.run(cmd)  # argv list, fine\n", encoding="utf-8")
    _track(repo)
    r = _run(out, repo)
    assert r.returncode == 0, r.stdout
    assert "security-floor: OK" in r.stdout


def test_exclude_glob_skips_file(render, tmp_path):
    out = _render(render, tmp_path)
    repo = tmp_path / "repo"
    _git_repo(repo)
    cfg = {**SHELL_RULE, "exclude": ["vendor/*"]}
    _write_config(repo, cfg)
    bad = repo / "vendor" / "x.py"
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_text("subprocess.run(cmd, shell=True)\n", encoding="utf-8")
    _track(repo)
    r = _run(out, repo)
    assert r.returncode == 0, r.stdout
    assert "security-floor: OK" in r.stdout


def test_applies_to_scopes(render, tmp_path):
    out = _render(render, tmp_path)
    repo = tmp_path / "repo"
    _git_repo(repo)
    _write_config(repo, SHELL_RULE)  # rule applies_to *.py
    # the forbidden text sits only in a markdown file, which the rule never scans
    (repo / "notes.md").write_text("example: shell=True in prose\n", encoding="utf-8")
    _track(repo)
    r = _run(out, repo)
    assert r.returncode == 0, r.stdout
    assert "security-floor: OK" in r.stdout


def test_self_exclude(render, tmp_path):
    out = _render(render, tmp_path)
    repo = tmp_path / "repo"
    _git_repo(repo)
    # the rule's pattern text ('PRIVATE KEY') literally appears in the config's own
    # 'pattern' field; without SELF_EXCLUDE the gate would flag the policy file itself.
    cfg = {"rules": [
        {"id": "no-private-key", "pattern": "PRIVATE KEY",
         "message": "committed private key material"},
    ]}
    _write_config(repo, cfg)
    _track(repo)
    r = _run(out, repo)
    assert r.returncode == 0, r.stdout
    assert "security-floor.json" not in r.stdout


def test_binary_file_skipped(render, tmp_path):
    out = _render(render, tmp_path)
    repo = tmp_path / "repo"
    _git_repo(repo)
    _write_config(repo, {"rules": [
        {"id": "x", "pattern": "anything", "message": "m"},
    ]})
    (repo / "data.bin").write_bytes(b"\xff\xfe\x00\x01anything")
    _track(repo)
    r = _run(out, repo)
    assert r.returncode == 0, r.stdout
    assert "security-floor: OK" in r.stdout


def test_skip_env_bypasses(render, tmp_path):
    out = _render(render, tmp_path)
    repo = tmp_path / "repo"
    _git_repo(repo)
    _write_config(repo, SHELL_RULE)
    (repo / "x.py").write_text("subprocess.run(cmd, shell=True)\n", encoding="utf-8")
    _track(repo)
    import os
    env = dict(os.environ)
    env["SKIP_SECURITY_FLOOR"] = "1"
    r = _run(out, repo, env=env)
    assert r.returncode == 0, r.stdout
    assert "skipped" in r.stdout


# --- broken policy is HARD (a broken policy must fail loudly, not no-op) -------

def test_invalid_json_config_hard_fails(render, tmp_path):
    out = _render(render, tmp_path)
    d = tmp_path / "d"
    _write_config_text(d, "{ not json")
    r = _run(out, d)
    assert r.returncode == 1, r.stdout
    assert "invalid JSON" in r.stdout


def test_config_not_object_hard_fails(render, tmp_path):
    out = _render(render, tmp_path)
    d = tmp_path / "d"
    _write_config_text(d, json.dumps(["not", "an", "object"]))
    r = _run(out, d)
    assert r.returncode == 1, r.stdout
    assert "must be a JSON object" in r.stdout


def test_rules_not_list_hard_fails(render, tmp_path):
    out = _render(render, tmp_path)
    d = tmp_path / "d"
    _write_config(d, {"rules": "nope"})
    r = _run(out, d)
    assert r.returncode == 1, r.stdout
    assert "'rules' must be a list" in r.stdout


def test_rule_missing_pattern_hard_fails(render, tmp_path):
    out = _render(render, tmp_path)
    d = tmp_path / "d"
    _write_config(d, {"rules": [{"id": "x", "message": "m"}]})
    r = _run(out, d)
    assert r.returncode == 1, r.stdout
    assert "pattern" in r.stdout


def test_invalid_regex_hard_fails(render, tmp_path):
    out = _render(render, tmp_path)
    d = tmp_path / "d"
    _write_config(d, {"rules": [{"id": "x", "pattern": "([unclosed", "message": "m"}]})
    r = _run(out, d)
    assert r.returncode == 1, r.stdout
    assert "not a valid regex" in r.stdout


# --- degraded-policy hardening: a rule that is structurally accepted but checks
#     nothing, or a broken sub-field silently dropped, is a broken policy — it
#     must fail loudly, not print OK (post-review nits) -------------------------

def test_applies_to_empty_hard_fails(render, tmp_path):
    # applies_to: [] passes an is-list check but scans zero files — the rule looks
    # active while checking nothing. A broken policy must fail loudly, not no-op.
    out = _render(render, tmp_path)
    d = tmp_path / "d"
    _write_config(d, {"rules": [
        {"id": "x", "pattern": "anything", "applies_to": [], "message": "m"},
    ]})
    r = _run(out, d)
    assert r.returncode == 1, r.stdout
    assert "applies_to" in r.stdout
    assert "non-empty" in r.stdout


def test_malformed_exclude_hard_fails(render, tmp_path):
    # 'exclude' as a string is a broken policy: silently coercing it to "no
    # exclusions" drops the author's intent without a word.
    out = _render(render, tmp_path)
    d = tmp_path / "d"
    _write_config(d, {**SHELL_RULE, "exclude": "vendor/*"})
    r = _run(out, d)
    assert r.returncode == 1, r.stdout
    assert "exclude" in r.stdout


def test_absent_exclude_is_fine(render, tmp_path):
    # no 'exclude' key at all stays valid (default: no exclusions).
    out = _render(render, tmp_path)
    repo = tmp_path / "repo"
    _git_repo(repo)
    _write_config(repo, SHELL_RULE)  # no exclude key
    (repo / "x.py").write_text("subprocess.run(cmd)\n", encoding="utf-8")
    _track(repo)
    r = _run(out, repo)
    assert r.returncode == 0, r.stdout
    assert "security-floor: OK" in r.stdout


def test_seed_self_excluded(render, tmp_path):
    # the shipped seed lives at docs/process/security-floor.example.json; a broad
    # user rule must not flag the example file the doc tells them to keep as a copy.
    out = _render(render, tmp_path)
    repo = tmp_path / "repo"
    _git_repo(repo)
    _write_config(repo, {"rules": [
        {"id": "broad", "pattern": "shell", "message": "m"},
    ]})
    seed = repo / SEED
    seed.parent.mkdir(parents=True, exist_ok=True)
    seed.write_text('{"rules": [{"pattern": "shell=True"}]}\n', encoding="utf-8")
    _track(repo)
    r = _run(out, repo)
    assert r.returncode == 0, r.stdout
    assert "security-floor.example.json" not in r.stdout


def test_unreadable_config_is_clean_hard(render, tmp_path):
    # a present-but-unreadable config must fail with a clean message, not a traceback.
    import os
    if os.geteuid() == 0:
        import pytest
        pytest.skip("chmod 000 does not deny root")
    out = _render(render, tmp_path)
    d = tmp_path / "d"
    _write_config(d, SHELL_RULE)
    (d / CONFIG).chmod(0o000)
    try:
        r = _run(out, d)
    finally:
        (d / CONFIG).chmod(0o644)
    assert r.returncode == 1, r.stdout
    assert "could not read" in r.stdout
    assert "Traceback" not in r.stderr


def test_invalid_id_error_uses_index_not_none(render, tmp_path):
    # when a rule's id is itself invalid, downstream field errors must reference
    # the rule index, not print "rule None ...".
    out = _render(render, tmp_path)
    d = tmp_path / "d"
    _write_config(d, {"rules": [{"pattern": "([bad", "message": ""}]})
    r = _run(out, d)
    assert r.returncode == 1, r.stdout
    assert "rule None" not in r.stdout


# --- neutrality + doc-drift ---------------------------------------------------

def test_neutral_no_kenni_terms(render, tmp_path):
    out = _render(render, tmp_path)
    for rel in [
        "scripts/process/check_security_floor.py",
        "docs/process/modules/security-floor.md",
        SEED,
    ]:
        text = (out / rel).read_text()
        for k in KENNI:
            assert k not in text, f"{k} leaked in {rel}"


def test_docdrift_green_with_module_doc(render, tmp_path):
    out = render(tmp_path, {"project_name": "d",
                            "modules": {"doc_drift_gate": True, "security_floor": True}})
    r = subprocess.run(
        [sys.executable, str(out / "scripts/process/check_doc_drift.py"), str(out)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stdout
