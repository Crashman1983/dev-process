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


def test_valid_story_ok(render, tmp_path):
    out = _render(render, tmp_path)
    _write_story(out, "STORY-0007.json", VALID)
    (out / "tests/billing").mkdir(parents=True, exist_ok=True)
    (out / "tests/billing/test_post.py").write_text("def test_x():\n    pass\n")
    r = _run(out)
    assert r.returncode == 0, r.stdout
    assert "registry-gate: OK" in r.stdout


def test_missing_required_field_is_hard(render, tmp_path):
    out = _render(render, tmp_path)
    broken = {k: v for k, v in VALID.items() if k != "title"}
    _write_story(out, "STORY-0008.json", broken)
    r = _run(out)
    assert r.returncode == 1
    assert "missing 'title'" in r.stdout


def test_bad_id_format_is_hard(render, tmp_path):
    out = _render(render, tmp_path)
    _write_story(out, "story7.json", {**VALID, "id": "STORY-7"})
    r = _run(out)
    assert r.returncode == 1
    assert "STORY-NNNN" in r.stdout


def test_duplicate_id_is_hard(render, tmp_path):
    out = _render(render, tmp_path)
    _write_story(out, "a.json", {**VALID, "id": "STORY-0009"})
    _write_story(out, "b.json", {**VALID, "id": "STORY-0009"})
    r = _run(out)
    assert r.returncode == 1
    assert "duplicate id" in r.stdout


def test_bad_status_is_hard(render, tmp_path):
    out = _render(render, tmp_path)
    _write_story(out, "STORY-0010.json", {**VALID, "status": "shipped"})
    r = _run(out)
    assert r.returncode == 1
    assert "status" in r.stdout


def test_empty_acceptance_text_is_hard(render, tmp_path):
    out = _render(render, tmp_path)
    bad = {**VALID, "acceptance": [{"id": "AC1", "text": "   "}]}
    _write_story(out, "STORY-0011.json", bad)
    r = _run(out)
    assert r.returncode == 1
    assert "acceptance[0]" in r.stdout


def test_missing_test_path_is_hard(render, tmp_path):
    out = _render(render, tmp_path)
    _write_story(out, "STORY-0012.json", {**VALID, "tests": ["tests/nope/test_absent.py"]})
    r = _run(out)
    assert r.returncode == 1
    assert "test path does not exist" in r.stdout


def test_done_without_tests_is_hard(render, tmp_path):
    out = _render(render, tmp_path)
    story = {**VALID, "status": "done"}
    story.pop("tests")
    _write_story(out, "STORY-0013.json", story)
    r = _run(out)
    assert r.returncode == 1
    assert "requires at least one test" in r.stdout


def test_test_path_with_node_selector_resolves(render, tmp_path):
    out = _render(render, tmp_path)
    (out / "tests/billing").mkdir(parents=True, exist_ok=True)
    (out / "tests/billing/test_post.py").write_text("def test_x():\n    pass\n")
    story = {**VALID, "tests": ["tests/billing/test_post.py::test_x"]}
    _write_story(out, "STORY-0014.json", story)
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_missing_adr_is_hard(render, tmp_path):
    out = _render(render, tmp_path)
    (out / "tests/billing").mkdir(parents=True, exist_ok=True)
    (out / "tests/billing/test_post.py").write_text("def test_x():\n    pass\n")
    _write_story(out, "STORY-0015.json", {**VALID, "adr": "ADR-0099"})
    r = _run(out)
    assert r.returncode == 1
    assert "adr link" in r.stdout


def test_present_adr_passes(render, tmp_path):
    out = _render(render, tmp_path)
    (out / "tests/billing").mkdir(parents=True, exist_ok=True)
    (out / "tests/billing/test_post.py").write_text("def test_x():\n    pass\n")
    (out / "docs/process/adr").mkdir(parents=True, exist_ok=True)
    (out / "docs/process/adr/adr-0005-billing.md").write_text("# ADR 5\n")
    _write_story(out, "STORY-0016.json", {**VALID, "adr": "ADR-0005"})
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_acceptance_without_test_is_soft(render, tmp_path):
    out = _render(render, tmp_path)
    (out / "tests/billing").mkdir(parents=True, exist_ok=True)
    (out / "tests/billing/test_post.py").write_text("def test_x():\n    pass\n")
    story = {
        **VALID,
        "status": "in-progress",
        "acceptance": [
            {"id": "AC1", "text": "one"},
            {"id": "AC2", "text": "two"},
        ],
        "tests": ["tests/billing/test_post.py"],
    }
    _write_story(out, "STORY-0017.json", story)
    r = _run(out)
    assert r.returncode == 0, r.stdout          # soft: does not fail the build
    assert "coverage unverified" in r.stdout


def test_unknown_field_ignored(render, tmp_path):
    out = _render(render, tmp_path)
    (out / "tests/billing").mkdir(parents=True, exist_ok=True)
    (out / "tests/billing/test_post.py").write_text("def test_x():\n    pass\n")
    story = {**VALID, "surface": "web", "owner": "team-a", "links": ["x"]}
    _write_story(out, "STORY-0018.json", story)
    r = _run(out)
    assert r.returncode == 0, r.stdout
    assert "registry-gate: OK" in r.stdout


def test_example_file_not_validated(render, tmp_path):
    out = _render(render, tmp_path)
    # a broken *.example.json must be ignored even though it is malformed
    (out / REG).mkdir(parents=True, exist_ok=True)
    (out / REG / "STORY-9999.example.json").write_text("{ not json", encoding="utf-8")
    r = _run(out)
    assert r.returncode == 0, r.stdout
    assert "no stories yet" in r.stdout
