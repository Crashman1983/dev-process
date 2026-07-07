import importlib.util
import json
import subprocess
import sys
from pathlib import Path


def _render(render, tmp_path, on=True):
    return render(tmp_path, {"project_name": "d", "modules": {"sbom": on}})


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_files_present_when_on(render, tmp_path):
    out = _render(render, tmp_path, True)
    assert (out / "scripts/process/check_sbom.py").is_file()
    assert (out / "docs/process/sbom-policy.example.json").is_file()
    assert (out / "docs/process/modules/sbom.md").is_file()


def test_files_absent_when_off(render, tmp_path):
    out = _render(render, tmp_path, False)
    assert not (out / "scripts/process/check_sbom.py").exists()
    assert not (out / "docs/process/modules/sbom.md").exists()


def test_registered_in_gate_runner(render, tmp_path):
    out = _render(render, tmp_path, True)
    assert '"sbom": ("sbom"' in (out / "scripts/process/gate_runner.py").read_text()


def _git_init(root: Path):
    for a in (["init"], ["add", "-A"], ["-c", "user.email=a@b.c", "-c", "user.name=t",
                                        "commit", "-m", "x", "--no-gpg-sign"]):
        subprocess.run(["git", "-C", str(root), *a], capture_output=True)


def _run_check(out: Path, work: Path):
    mod = _load(out / "scripts/process/check_sbom.py", "sbomchk")
    return mod.check(work)


def _policy(work: Path, **over):
    pol = {"allowed_licenses": ["MIT", "Apache-2.0"]}
    pol.update(over)
    (work / "docs/process").mkdir(parents=True, exist_ok=True)
    (work / "docs/process/sbom-policy.json").write_text(json.dumps(pol))


def _sbom(work: Path, components):
    (work / "sbom").mkdir(parents=True, exist_ok=True)
    (work / "sbom/bom.json").write_text(json.dumps(
        {"bomFormat": "CycloneDX", "components": components}))


def test_no_policy_is_advisory(render, tmp_path):
    out = _render(render, tmp_path, True)
    work = tmp_path / "w1"
    work.mkdir()
    _git_init(work)
    hard, soft = _run_check(out, work)
    assert hard == [] and any("no SBOM policy" in s for s in soft)


def test_missing_and_disallowed_license_fail(render, tmp_path):
    out = _render(render, tmp_path, True)
    work = tmp_path / "w2"
    work.mkdir()
    _policy(work)
    _sbom(work, [
        {"type": "library", "name": "ok-lib", "licenses": [{"license": {"id": "MIT"}}]},
        {"type": "library", "name": "no-lic", "licenses": []},
        {"type": "library", "name": "bad-lic", "licenses": [{"license": {"id": "GPL-3.0"}}]},
        {"type": "application", "name": "self"},  # exempt
    ])
    _git_init(work)
    hard, _ = _run_check(out, work)
    joined = " ".join(hard)
    assert "no-lic" in joined and "no license attestation" in joined
    assert "bad-lic" in joined and "not in allowed_licenses" in joined
    assert "self" not in joined  # application component skipped


def test_all_attested_and_allowed_passes(render, tmp_path):
    out = _render(render, tmp_path, True)
    work = tmp_path / "w3"
    work.mkdir()
    _policy(work)
    _sbom(work, [
        {"type": "library", "name": "a", "licenses": [{"license": {"id": "MIT"}}]},
        {"type": "library", "name": "b", "licenses": [{"expression": "Apache-2.0"}]},
    ])
    _git_init(work)
    hard, _ = _run_check(out, work)
    assert hard == []
