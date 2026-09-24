"""ac-text-drift: one wording per acceptance criterion across spec and inventory."""
import json
import subprocess
import sys


def _gate(out):
    return subprocess.run([sys.executable, str(out / "scripts/process/check_ac_text_drift.py"), "."],
                          cwd=out, capture_output=True, text=True)


def _seed(out, registry_text):
    (out / "specs/004-export").mkdir(parents=True)
    (out / "specs/004-export/spec.md").write_text(
        "# Spec\n\n- AC-1: When the owner exports, the system shall write a CSV.\n"
        "- AC-2: When the export is empty, the system shall say so.\n")
    plans = out / ".process-work/plans"
    plans.mkdir(parents=True, exist_ok=True)
    (plans / "2026-09-24-export.md").write_text("# Plan\n\ntier: 2\nissue: #42\nspec: specs/004-export\n")
    reg = out / "docs/process/feature-registry"
    reg.mkdir(parents=True, exist_ok=True)
    (reg / "STORY-0042.json").write_text(json.dumps({
        "id": "STORY-0042", "issue": "https://github.com/o/r/issues/42",
        "acceptance": [{"id": "AC1", "text": registry_text},
                       {"id": "AC2", "text": "When the export is empty, the system shall say so."}]}))


def test_same_wording_is_green_and_rendered_only_with_the_module(render, tmp_path):
    out = render(tmp_path / "on", {"project_name": "d", "modules": {"feature_registry": True}})
    _seed(out, "When the owner exports,  the system shall write a CSV.")  # whitespace is not drift
    r = _gate(out)
    assert r.returncode == 0 and "OK" in r.stdout, r.stdout
    off = render(tmp_path / "off", {"project_name": "d", "modules": {}})
    assert not (off / "scripts/process/check_ac_text_drift.py").exists()


def test_diverging_wording_fails_and_names_both_places(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {"feature_registry": True}})
    _seed(out, "When the owner exports, the system shall write an XLSX.")
    r = _gate(out)
    assert r.returncode == 1
    assert "AC-1 of #42 differs" in r.stdout and "specs/004-export/spec.md" in r.stdout
    assert "STORY-0042.json" in r.stdout and "AC-2" not in r.stdout
