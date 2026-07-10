import subprocess
import sys
from pathlib import Path


def _run(out: Path, *args):
    return subprocess.run(
        [sys.executable, str(out / "scripts/process/make_review_bundle.py"), *args],
        cwd=out, capture_output=True, text=True)


def _git(out: Path, *args):
    return subprocess.run(["git", *args], cwd=out, capture_output=True, text=True)


def _seed_repo(out: Path):
    """main with a base commit, a feature branch with a change and a plan."""
    _git(out, "init", "-q", "-b", "main")
    _git(out, "config", "user.email", "t@t")
    _git(out, "config", "user.name", "t")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "base")
    _git(out, "checkout", "-q", "-b", "feat")
    plans = out / ".process-work/plans"
    plans.mkdir(parents=True, exist_ok=True)
    (plans / "2026-07-09-widget.md").write_text(
        "# Plan\n\ntier: 2\nissue: #9\n\nBuild the widget.\n")
    (out / "widget.py").write_text("def widget():\n    return 42\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "feat: widget")


def test_core_tool_present_on_minimal(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    assert (out / "scripts/process/make_review_bundle.py").is_file()


def test_bundle_assembles_all_sections(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    r = _run(out, "--base", "main")
    assert r.returncode == 0, r.stderr
    t = r.stdout
    # the seven sections, each carrying real content
    assert "INDEPENDENT reviewer" in t
    assert "Mandatory rules" in t                       # kernel block content
    assert "# Review Checklist" in t                    # checklist inlined
    assert "Product frame" in t
    assert "2026-07-09-widget.md" in t and "Build the widget." in t
    assert "def widget():" in t                         # the diff itself
    assert "```diff" in t
    # grammar imported from the gate — fields, verdicts, independence tokens
    assert "REVIEW independence=… model=… reviewer=… round=… tier=… verdict=… work=…" in t
    assert "['block', 'pass']" in t
    assert "'cross-model'" in t and "'single-family'" in t
    assert "FINDING sev=<blocker|major|minor|nit>" in t


def test_output_file_option(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    r = _run(out, "--base", "main", "-o", "bundle.md")
    assert r.returncode == 0, r.stderr
    assert "written to bundle.md" in r.stdout
    assert "INDEPENDENT reviewer" in (out / "bundle.md").read_text()


def test_missing_sources_named_not_skipped(render, tmp_path):
    # no git repo, no plan: every gap is named in place, exit still 0
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    (out / "PRODUCT.md").unlink()
    r = _run(out)
    assert r.returncode == 0, r.stderr
    t = r.stdout
    assert "no active plan" in t
    assert "no usable base ref" in t
    assert "PRODUCT.md missing" in t
    # kernel + checklist still real
    assert "Mandatory rules" in t and "# Review Checklist" in t


def test_empty_diff_stated(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _git(out, "init", "-q", "-b", "main")
    _git(out, "config", "user.email", "t@t")
    _git(out, "config", "user.name", "t")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "base")
    r = _run(out, "--base", "main")
    assert "HEAD adds nothing over main" in r.stdout
