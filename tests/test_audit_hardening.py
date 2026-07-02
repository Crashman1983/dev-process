# Regression tests for the 2026-07-02 audit findings: false-greens must turn
# red, and malformed input must produce diagnostics, not tracebacks.
import subprocess
import sys


def _run(script, cwd):
    return subprocess.run([sys.executable, str(script), "."], cwd=cwd, capture_output=True, text=True)


def test_unclosed_arch_fence_is_hard_fail(render, tmp_path):
    # audit: an unclosed ```arch fence used to read as "not onboarded" — green
    out = render(tmp_path, {"project_name": "d", "modules": {"arch_onboarding": True}})
    arch = out / "ARCHITECTURE.md"
    arch.write_text(arch.read_text() + "\n```arch\ncode_roots: [does-not-exist]\n")
    r = _run(out / "scripts/process/check_architecture.py", out)
    assert r.returncode == 1
    assert "unclosed" in r.stdout


def test_arch_non_string_paths_fail_cleanly(render, tmp_path):
    # audit: an int layer path crashed with a TypeError traceback
    out = render(tmp_path, {"project_name": "d", "modules": {"arch_onboarding": True}})
    (out / "ARCHITECTURE.md").write_text(
        "# a\n```arch\nlayers:\n  api:\n    path: 123\n```\n"
    )
    r = _run(out / "scripts/process/check_architecture.py", out)
    assert r.returncode == 1
    assert "Traceback" not in r.stderr
    assert "path missing" in r.stdout


def test_doc_drift_accepts_document_relative_links(render, tmp_path):
    # audit: valid ../ markdown links (fine on GitHub) were reported missing
    out = render(tmp_path, {"project_name": "d", "modules": {"doc_drift_gate": True}})
    mod = out / "docs/process/modules"
    mod.mkdir(parents=True, exist_ok=True)
    (mod / "x.md").write_text("see [workflow](../workflow.md)\n")
    r = _run(out / "scripts/process/check_doc_drift.py", out)
    assert r.returncode == 0, r.stdout
    (mod / "x.md").write_text("see [nope](../does-not-exist.md)\n")
    r = _run(out / "scripts/process/check_doc_drift.py", out)
    assert r.returncode == 1
    assert "does-not-exist.md" in r.stdout


def test_doc_drift_reports_non_utf8_instead_of_crashing(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {"doc_drift_gate": True}})
    (out / "docs/process/latin1.md").write_bytes("gr\xfc\xdfe".encode("latin-1"))
    r = _run(out / "scripts/process/check_doc_drift.py", out)
    assert r.returncode == 1
    assert "Traceback" not in r.stderr
    assert "not valid UTF-8" in r.stdout


def test_registry_reports_non_utf8_story_cleanly(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {"feature_registry": True}})
    reg = out / "docs/process/feature-registry"
    (reg / "STORY-0001.json").write_bytes(b'{"id": "\xff\xfe"}')
    r = _run(out / "scripts/process/check_feature_registry.py", out)
    assert r.returncode == 1
    assert "Traceback" not in r.stderr
    assert "invalid JSON" in r.stdout


def test_parity_survives_non_mapping_answers(render, tmp_path):
    # audit: a scalar .copier-answers.yml crashed the gate with AttributeError
    out = render(
        tmp_path,
        {"project_name": "d", "modules": {"parity": True}, "parity_surfaces": ["web"]},
    )
    (out / ".copier-answers.yml").write_text("just a string\n")
    r = _run(out / "scripts/process/check_parity.py", out)
    assert "Traceback" not in r.stderr
    assert r.returncode == 0  # no parity files -> honest empty state, no crash