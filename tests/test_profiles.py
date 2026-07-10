import subprocess
import sys

SOLO_ON = ["scripts/process/check_doc_drift.py", "scripts/process/install-hooks.sh"]
TEAM_EXTRA = ["scripts/process/check_feature_registry.py", "scripts/process/check_issues.py"]
HEAVY_OFF = ["scripts/process/check_sbom.py", "scripts/process/check_security_floor.py",
             "scripts/process/check_parity.py", "scripts/process/check_github_master.py"]


def test_default_profile_is_solo(render_raw, tmp_path):
    out = render_raw(tmp_path, {"project_name": "d"})
    for rel in SOLO_ON:
        assert (out / rel).is_file(), rel
    for rel in TEAM_EXTRA + HEAVY_OFF:
        assert not (out / rel).exists(), rel
    assert "profile: solo" in (out / ".copier-answers.yml").read_text()


def test_minimal_profile_core_only(render_raw, tmp_path):
    out = render_raw(tmp_path, {"project_name": "d", "profile": "minimal"})
    for rel in SOLO_ON + TEAM_EXTRA + HEAVY_OFF:
        assert not (out / rel).exists(), rel
    # core gates still there
    for rel in ["scripts/process/check_kernel.py", "scripts/process/check_decisions.py",
                "scripts/process/check_review.py", "scripts/process/check_product_frame.py"]:
        assert (out / rel).is_file(), rel


def test_team_profile_adds_backlog_modules(render_raw, tmp_path):
    out = render_raw(tmp_path, {"project_name": "d", "profile": "team"})
    for rel in SOLO_ON + TEAM_EXTRA:
        assert (out / rel).is_file(), rel
    for rel in HEAVY_OFF:
        assert not (out / rel).exists(), rel
    # derived set is recorded concretely, so `copier update` keeps it
    ans = (out / ".copier-answers.yml").read_text()
    assert "profile: team" in ans
    assert "feature_registry: true" in ans and "sbom: false" in ans


def test_custom_profile_starts_all_off(render_raw, tmp_path):
    out = render_raw(tmp_path, {"project_name": "d", "profile": "custom"})
    for rel in SOLO_ON + TEAM_EXTRA + HEAVY_OFF:
        assert not (out / rel).exists(), rel


def test_explicit_modules_override_profile(render_raw, tmp_path):
    # a passed modules dict wins over the profile-derived default entirely
    out = render_raw(tmp_path, {"project_name": "d", "profile": "solo",
                                "modules": {"sbom": True}})
    assert (out / "scripts/process/check_sbom.py").is_file()
    for rel in SOLO_ON:
        assert not (out / rel).exists(), rel


def test_profile_renders_gate_green(render_raw, tmp_path):
    # each profile's fresh render must pass its own gate runner
    for prof in ("minimal", "solo", "team"):
        out = render_raw(tmp_path / prof, {"project_name": "d", "profile": prof})
        r = subprocess.run([sys.executable, str(out / "scripts/process/gate_runner.py")],
                           cwd=out, capture_output=True, text=True)
        assert r.returncode == 0, f"{prof}: {r.stdout}"


def test_ratchet_documented(render_raw, tmp_path):
    out = render_raw(tmp_path, {"project_name": "d", "profile": "minimal"})
    text = (out / "docs/process/start-here.md").read_text(encoding="utf-8")
    assert "hardening ratchet" in text
    for prof in ("`minimal`", "`solo`", "`team`", "`custom`"):
        assert prof in text, prof
    # every optional module (all 13 copier.yml keys) has a ratchet trigger
    for mod in ("doc_drift_gate", "git_hooks",
                "security_floor", "parity", "contract_first", "contracts_drift",
                "feature_registry", "github_issues", "github_master",
                "arch_onboarding", "arch_docs", "telemetry", "sbom"):
        assert f"`{mod}`" in text, mod
