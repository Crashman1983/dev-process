import importlib.util
import subprocess
import sys
from pathlib import Path


def _render(render, tmp_path, issues=True):
    return render(tmp_path, {"project_name": "d",
                             "modules": {"github_issues": issues, "feature_registry": True}})


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_present_when_github_issues_on(render, tmp_path):
    out = _render(render, tmp_path)
    assert (out / "scripts/process/who_is_working.py").is_file()
    assert (out / "scripts/process/attention.py").is_file()


def test_absent_when_github_issues_off(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {"github_issues": False}})
    assert not (out / "scripts/process/who_is_working.py").exists()
    assert not (out / "scripts/process/attention.py").exists()


def test_who_is_working_selftest(render, tmp_path):
    out = _render(render, tmp_path)
    r = subprocess.run([sys.executable, str(out / "scripts/process/who_is_working.py"),
                        "--selftest"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr + r.stdout
    assert "OK" in r.stdout


def test_attention_selftest(render, tmp_path):
    out = _render(render, tmp_path)
    r = subprocess.run([sys.executable, str(out / "scripts/process/attention.py"),
                        "--selftest"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr + r.stdout
    assert "OK" in r.stdout


def test_attention_reads_flat_registry_tests(render, tmp_path):
    # the registry maps tests at the story root (flat list), not per-acceptance;
    # the dashboard must count those, else every story looks 0-test.
    out = _render(render, tmp_path)
    reg = out / "docs/process/feature-registry"
    reg.mkdir(parents=True, exist_ok=True)
    # n_tests counts only tests that exist on disk (consistency with the gate)
    paths = [f"tests/test_flat_{i}.py" for i in range(6)]
    for p in paths:
        (out / p).parent.mkdir(parents=True, exist_ok=True)
        (out / p).write_text("def test_x():\n    pass\n")
    import json as _json
    (reg / "STORY-0009.json").write_text(_json.dumps(
        {"id": "STORY-0009", "status": "done", "issue": "#5",
         "acceptance": [{"id": "AC1", "text": "z"}], "tests": paths}))
    mod = _load(out / "scripts/process/attention.py", "att_flat")
    rows = mod.load_stories(reg)
    assert rows[0]["n_ak"] == 1 and rows[0]["n_tests"] == 6
    assert [r["id"] for r in mod.under_granular(rows, 5)] == ["STORY-0009"]


def test_attention_n_tests_ignores_missing_files(render, tmp_path):
    # a story listing tests that do not exist must count 0 — matching the
    # feature-registry gate, which only counts existing test paths.
    out = _render(render, tmp_path)
    reg = out / "docs/process/feature-registry"
    reg.mkdir(parents=True, exist_ok=True)
    import json as _json
    (reg / "STORY-0010.json").write_text(_json.dumps(
        {"id": "STORY-0010", "status": "proposed", "issue": "#6",
         "acceptance": [{"id": "AC1", "text": "z"}],
         "tests": ["tests/nope_a.py", "tests/nope_b.py"]}))
    mod = _load(out / "scripts/process/attention.py", "att_missing")
    rows = mod.load_stories(reg)
    assert rows[0]["n_tests"] == 0


def test_workflow_parallel_agents_section_gated(render, tmp_path):
    on = _render(render, tmp_path, issues=True)
    text = (on / "docs/process/workflow.md").read_text(encoding="utf-8")
    assert "## Parallel agents" in text
    for ref in ("who_is_working.py", "story_order.py", "attention.py"):
        assert ref in text, ref
    # the label-mutating ambient-HITL overlays were not adopted
    assert "status:hold" not in text and "awaiting-ack" not in text
    off = render(tmp_path / "off", {"project_name": "d", "modules": {"github_issues": False}})
    assert "## Parallel agents" not in (off / "docs/process/workflow.md").read_text(encoding="utf-8")


def test_workflow_no_story_order_ref_without_feature_registry(render, tmp_path):
    # story_order.py is a feature_registry tool; the parallel-agents section must
    # not hard-reference it when that module is off (else doc-drift breaks).
    out = render(tmp_path, {"project_name": "d",
                            "modules": {"github_issues": True, "feature_registry": False}})
    text = (out / "docs/process/workflow.md").read_text(encoding="utf-8")
    assert "## Parallel agents" in text
    assert "story_order.py" not in text


def test_github_issues_doc_has_coordination_views(render, tmp_path):
    out = _render(render, tmp_path)
    text = (out / "docs/process/modules/github-issues.md").read_text(encoding="utf-8")
    assert "Coordination views" in text
    assert "who_is_working.py" in text and "attention.py" in text
    assert "issue hygiene" in text.lower()


def test_attention_issue_hygiene_and_ears(render, tmp_path):
    out = _render(render, tmp_path)
    mod = _load(out / "scripts/process/attention.py", "att_hy")
    hy = mod.issue_hygiene([
        {"number": 1, "title": "STORY-A", "labels": [{"name": "type:feature"}],
         "body": "the system SHALL x", "state": "OPEN"},
        {"number": 2, "title": "[Finding] z", "labels": [], "body": "prose", "state": "OPEN"},
        {"number": 3, "title": "EPIC: e", "labels": [{"name": "type:epic"}],
         "body": "scope", "state": "OPEN"},
        {"number": 4, "title": "old", "labels": [], "body": "", "state": "CLOSED"},
    ])
    assert [h["issue"] for h in hy] == ["#2"]
    assert hy[0]["missing"] == ["type", "EARS acceptance"]
    # uppercase SHALL + German EARS heading both count as gradeable
    assert mod._has_ears("Akzeptanzkriterien (EARS)") and mod._has_ears("it SHALL do")
