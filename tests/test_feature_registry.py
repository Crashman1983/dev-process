import json
import subprocess
import sys
from pathlib import Path


def _render(render, tmp_path, **mods):
    m = {"feature_registry": True}
    m.update(mods)
    return render(tmp_path, {"project_name": "d", "modules": m})


def _run(out: Path):
    return subprocess.run(
        [sys.executable, str(out / "scripts/process/check_feature_registry.py"), str(out)],
        capture_output=True, text=True,
    )


REG = "docs/process/feature-registry"


def _write_story(out: Path, name: str, data: dict):
    d = out / REG
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(json.dumps(data), encoding="utf-8")


VALID = {
    "id": "STORY-0007",
    "title": "Consume billing API",
    "story": "As an order service, when a checkout completes, the system shall post the invoice.",
    "acceptance": [{"id": "AC1", "text": "A completed checkout produces exactly one billing POST."}],
    "tests": ["tests/billing/test_post.py"],
    "status": "done",
}


def test_module_files_present_when_on(render, tmp_path):
    out = _render(render, tmp_path)
    assert (out / "scripts/process/check_feature_registry.py").is_file()
    assert (out / "docs/process/modules/feature-registry.md").is_file()
    assert (out / REG / "STORY-0001.example.json").is_file()


def test_module_files_absent_when_off(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    assert not (out / "scripts/process/check_feature_registry.py").exists()
    assert not (out / "docs/process/modules/feature-registry.md").exists()
    assert not (out / REG).exists()


def test_shipped_seed_is_inert(render, tmp_path):
    # only the *.example.json seed ships → registry reads as empty
    out = _render(render, tmp_path)
    r = _run(out)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "no stories yet" in r.stdout


def test_invalid_json_is_hard(render, tmp_path):
    out = _render(render, tmp_path)
    (out / REG).mkdir(parents=True, exist_ok=True)
    (out / REG / "STORY-0002.json").write_text("{ not json", encoding="utf-8")
    r = _run(out)
    assert r.returncode == 1
    assert "invalid JSON" in r.stdout


def test_runner_lists_gate_when_module_on(render, tmp_path):
    out = _render(render, tmp_path)
    r = subprocess.run(
        [sys.executable, str(out / "scripts/process/gate_runner.py"), "--list"],
        cwd=out, capture_output=True, text=True,
    )
    assert "feature-registry" in r.stdout


def test_runner_omits_gate_when_module_off(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    r = subprocess.run(
        [sys.executable, str(out / "scripts/process/gate_runner.py"), "--list"],
        cwd=out, capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    assert "feature-registry" not in r.stdout
