"""The standard setup (lean pass, KISS pass v2.27.0): one opinionated module
set, no switch; retired modules are gone from every render."""
import subprocess
import sys

STANDARD_ON = [
    "scripts/process/check_doc_drift.py",
    ".pre-commit-config.yaml",
    "scripts/process/check_feature_registry.py",
    "scripts/process/check_issues.py",
    "scripts/process/check_architecture.py",
    "scripts/process/check_sbom.py",
    "scripts/process/check_telemetry.py",
    "scripts/process/check_design_contracts.py",
]
RETIRED = [
    "scripts/process/check_github_master.py",
    "scripts/process/check_contracts.py",
    "scripts/process/check_capability_contracts.py",
    "scripts/process/check_arch_docs.py",
    "scripts/process/check_security_floor.py",
    "scripts/process/trace.py",
    "ARCHITECTURE-OVERVIEW.md",
]


def test_default_render_is_the_standard_set(render_raw, tmp_path):
    out = render_raw(tmp_path, {"project_name": "d"})
    for rel in STANDARD_ON:
        assert (out / rel).is_file(), rel
    for rel in RETIRED:
        assert not (out / rel).exists(), rel
    answers = (out / ".copier-answers.yml").read_text()
    assert "doc_drift_gate: true" in answers  # manifest stays load-bearing
    assert "sbom: true" in answers and "regulated" not in answers


def test_old_manifest_with_retired_modules_still_runs(render_raw, tmp_path):
    # a project installed before the KISS pass still names the retired
    # modules in its manifest: accepted, never run, never an error
    out = render_raw(tmp_path, {"project_name": "d"})
    ans = out / ".copier-answers.yml"
    text = ans.read_text()
    ans.write_text(text.replace("sbom: true", "sbom: true, contracts: true, security_floor: true, "
                                "arch_docs: true, github_master: true"))
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=out, check=True)
    r = subprocess.run([sys.executable, str(out / "scripts/process/gate_runner.py")],
                       cwd=out, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "contracts-drift" not in r.stdout and "github-master" not in r.stdout

def test_standard_render_gates_green(render_raw, tmp_path):
    # content-driven gates must be honestly inert on an empty project — the
    # standard set never blocks a fresh install
    out = render_raw(tmp_path, {"project_name": "d"})
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=out, check=True)
    r = subprocess.run([sys.executable, str(out / "scripts/process/gate_runner.py")],
                       cwd=out, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_harness_single_choice(render_raw, tmp_path):
    out = render_raw(tmp_path, {"project_name": "d", "harness": "copilot"})
    assert (out / ".github/prompts/brainstorm.prompt.md").is_file()
    assert not (out / ".claude").exists()
    assert not (out / "AGENTS.md").exists()


def test_explicit_modules_still_override(render_raw, tmp_path):
    # the expert opt-out: a passed complete modules dict replaces the standard
    out = render_raw(tmp_path, {"project_name": "d", "modules": {
        "doc_drift_gate": False, "arch_onboarding": False,
        "feature_registry": False, "github_issues": False, "contracts": False,
        "git_hooks": False, "security_floor": False, "sbom": False,
        "telemetry": False, "arch_docs": False, "github_master": False}})
    for rel in STANDARD_ON:
        assert not (out / rel).exists(), rel


def test_standard_setup_documented(render_raw, tmp_path):
    out = render_raw(tmp_path, {"project_name": "d"})
    text = (out / "docs/process/start-here.md").read_text(encoding="utf-8")
    assert "## The standard setup" in text
    assert "no module switch" in text
    assert "decision record" in text  # switching off is a recorded decision


def test_a_push_of_another_commit_than_the_checked_tree_fails(render_raw, tmp_path):
    # pre-commit names the pushed commit; the gates check the working tree —
    # the two must be the same commit, or the verdict is about the wrong tree
    import os
    out = render_raw(tmp_path, {"project_name": "d"})
    for args in (["init", "-q", "-b", "main"], ["config", "user.email", "t@t"],
                 ["config", "user.name", "t"], ["add", "-A"], ["commit", "-q", "-m", "base"]):
        subprocess.run(["git", *args], cwd=out, check=True, capture_output=True)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=out, capture_output=True,
                          text=True).stdout.strip()
    runner = [sys.executable, str(out / "scripts/process/gate_runner.py")]
    same = subprocess.run(runner, cwd=out, capture_output=True, text=True,
                          env={**os.environ, "PRE_COMMIT_TO_REF": head})
    assert same.returncode == 0, same.stdout + same.stderr
    other = subprocess.run(runner, cwd=out, capture_output=True, text=True,
                           env={**os.environ, "PRE_COMMIT_TO_REF": "0" * 40})
    assert other.returncode != 0 and "not being pushed" in other.stderr


def test_render_without_ci_is_green(render_raw, tmp_path):
    # without the CI adapter no rendered doc may point at a CI-only file
    out = render_raw(tmp_path, {"project_name": "d", "ci": {"github": False}})
    assert not (out / "scripts/process/setup_branch_protection.sh").exists()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=out, check=True)
    r = subprocess.run([sys.executable, str(out / "scripts/process/gate_runner.py")],
                       cwd=out, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
