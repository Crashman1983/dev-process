"""The standard setup (lean pass): one opinionated module set instead of
profiles and thirteen toggles; `regulated` is the single switch."""
import subprocess
import sys

STANDARD_ON = [
    "scripts/process/check_doc_drift.py",
    ".pre-commit-config.yaml",
    "scripts/process/check_feature_registry.py",
    "scripts/process/check_issues.py",
    "scripts/process/check_github_master.py",
    "scripts/process/check_contracts.py",
    "scripts/process/check_capability_contracts.py",
    "scripts/process/check_architecture.py",
    "scripts/process/check_arch_docs.py",
    "scripts/process/check_telemetry.py",
]
REGULATED_ONLY = [
    "scripts/process/check_sbom.py",
    "scripts/process/check_security_floor.py",
]


def test_default_render_is_the_standard_set(render_raw, tmp_path):
    out = render_raw(tmp_path, {"project_name": "d"})
    for rel in STANDARD_ON:
        assert (out / rel).is_file(), rel
    for rel in REGULATED_ONLY:
        assert not (out / rel).exists(), rel
    answers = (out / ".copier-answers.yml").read_text()
    assert "doc_drift_gate: true" in answers  # manifest stays load-bearing
    assert "sbom: false" in answers


def test_regulated_adds_the_compliance_pack(render_raw, tmp_path):
    out = render_raw(tmp_path, {"project_name": "d", "regulated": True})
    for rel in STANDARD_ON + REGULATED_ONLY:
        assert (out / rel).is_file(), rel
    answers = (out / ".copier-answers.yml").read_text()
    assert "sbom: true" in answers and "security_floor: true" in answers


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
    for rel in STANDARD_ON + REGULATED_ONLY:
        assert not (out / rel).exists(), rel


def test_standard_setup_documented(render_raw, tmp_path):
    out = render_raw(tmp_path, {"project_name": "d"})
    text = (out / "docs/process/start-here.md").read_text(encoding="utf-8")
    assert "## The standard setup" in text
    assert "`regulated`" in text
    assert "decision record" in text  # switching off is a recorded decision
