import hashlib
import re
import subprocess
import sys
from pathlib import Path


def _run(out: Path, *args):
    return subprocess.run(
        [sys.executable, str(out / "scripts/process/make_review_bundle.py"), *args],
        cwd=out, capture_output=True, text=True)


def _git(out: Path, *args, **kwargs):
    return subprocess.run(
        ["git", *args], cwd=out, capture_output=True, text=True, **kwargs
    )


def _artifact(text: str) -> dict[str, str]:
    match = re.search(
        r"^REVIEW_ARTIFACT base=(?P<base>[0-9a-f]{40,64}) "
        r"head=(?P<head>[0-9a-f]{40,64}) diff=(?P<diff>[0-9a-f]{64})$",
        text,
        re.MULTILINE,
    )
    assert match, text
    return match.groupdict()


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


def test_bundle_fingerprint_matches_binary_diff(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    text = _run(out, "--base", "main").stdout
    artifact = _artifact(text)
    merge_base = _git(out, "merge-base", "main", "HEAD").stdout.strip()
    head = _git(out, "rev-parse", "HEAD").stdout.strip()
    diff = subprocess.run(
        ["git", "diff", "--binary", f"{merge_base}...{head}"],
        cwd=out,
        capture_output=True,
        check=True,
    ).stdout
    assert artifact == {
        "base": merge_base,
        "head": head,
        "diff": hashlib.sha256(diff).hexdigest(),
    }


def test_bundle_fingerprint_changes_with_committed_content(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    first = _artifact(_run(out, "--base", "main").stdout)["diff"]
    (out / "widget.py").write_text("def widget():\n    return 43\n")
    _git(out, "add", "widget.py", check=True)
    _git(out, "commit", "-q", "-m", "fix: change widget", check=True)
    second = _artifact(_run(out, "--base", "main").stdout)["diff"]
    assert first != second


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


def test_finding_tokens_pinned_to_their_owning_gate(render, tmp_path):
    # the FINDING line is hand-written in the bundle (its owner, check_issues,
    # renders only with github_issues) — this pins the duplicate to the enums
    import importlib.util
    out = render(tmp_path, {"project_name": "d",
                            "modules": {"github_issues": True}})
    spec = importlib.util.spec_from_file_location(
        "ci_gate", out / "scripts/process/check_issues.py")
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    bundle_src = (out / "scripts/process/make_review_bundle.py").read_text()
    sev_line = "sev=<" + "|".join(sorted(gate.FINDING_SEVS, key="blocker major minor nit".split().index)) + ">"
    act_line = "action=<" + "|".join(sorted(gate.FINDING_ACTIONS, key="fix accept follow-up".split().index)) + ">"
    assert sev_line in bundle_src, sev_line
    assert act_line in bundle_src, act_line


def test_option_missing_value_is_usage_not_traceback(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    for args in (["--base"], ["-o"]):
        r = _run(out, *args)
        assert r.returncode != 0
        assert "usage" in (r.stdout + r.stderr)
        assert "Traceback" not in r.stderr


def test_nested_fences_do_not_corrupt_bundle(render, tmp_path):
    # a diff of a markdown file carries its own ``` — the bundle's fence must
    # outrun it, or everything after the diff sits inside an open code block
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    (out / "notes.md").write_text("intro\n```python\nx = 1\n```\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "docs: notes with fence")
    t = _run(out, "--base", "main").stdout
    lines = t.splitlines()
    # the fence must outrun the diff's own ``` runs: 4 backticks here
    opens = [i for i, ln in enumerate(lines) if ln.startswith("````diff")]
    assert len(opens) == 1, "exactly one diff fence expected"
    closes = [i for i, ln in enumerate(lines[opens[0] + 1:], opens[0] + 1)
              if ln.rstrip() == "````"]
    assert closes, "the 4-backtick fence is never closed"
    inner = "\n".join(lines[opens[0] + 1:closes[0]])
    assert "```python" in inner   # the md file's own fence rides INSIDE the diff
    # the grammar section lives after the closed fence, not swallowed by it
    grammar_at = next(i for i, ln in enumerate(lines)
                      if ln.startswith("## Required output grammar"))
    assert grammar_at > closes[0]
    assert t.rstrip().endswith("verdict `block` instead.")


def test_subdirectory_invocation_finds_root(render, tmp_path):
    import subprocess as sp
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    r = sp.run([sys.executable, str(out / "scripts/process/make_review_bundle.py"),
                "--base", "main"],
               cwd=out / "docs", capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    # root-level sources found despite subdir cwd
    assert "2026-07-09-widget.md" in r.stdout
    assert "Mandatory rules" in r.stdout
    assert "no active plan" not in r.stdout


def test_non_utf8_tracked_file_does_not_crash(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    (out / "latin.txt").write_bytes("café résumé\n".encode("latin-1"))
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "feat: latin file")
    r = _run(out, "--base", "main")
    assert r.returncode == 0, r.stderr
    assert "Traceback" not in r.stderr


def test_dirty_tree_is_disclosed(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    (out / "uncommitted.py").write_text("x = 1\n")
    t = _run(out, "--base", "main").stdout
    assert "working tree dirty" in t and "NOT in this diff" in t


def test_bundle_survives_safe_path_python(render, tmp_path):
    # PYTHONSAFEPATH removes the implicit script-dir sys.path entry — the
    # explicit sibling-import shim must keep the tool working (SP50 audit)
    import os
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    env = {**os.environ, "PYTHONSAFEPATH": "1"}
    r = subprocess.run(
        [sys.executable, str(out / "scripts/process/make_review_bundle.py"),
         "--base", "main"],
        cwd=out, capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
    assert "Mandatory rules" in r.stdout


def test_unknown_flag_is_usage_error(render, tmp_path):
    # a typo'd --base must not silently produce a bundle against the wrong ref
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    for args in (["--bases", "main"], ["--help"], ["--base", "main", "extra"]):
        r = _run(out, *args)
        assert r.returncode != 0, args
        assert "usage" in (r.stdout + r.stderr)
        assert "Traceback" not in r.stderr


def test_plan_filter_narrows_bundle(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    plans = out / ".process-work/plans"
    (plans / "2026-07-11-other.md").write_text("# Other\n\ntier: 2\n")
    r = _run(out, "--base", "main", "--plan", "widget")
    assert r.returncode == 0, r.stderr
    assert "2026-07-09-widget.md" in r.stdout
    assert "2026-07-11-other.md" not in r.stdout
    # a filter matching nothing says so instead of silently bundling all
    r2 = _run(out, "--base", "main", "--plan", "nope")
    assert "no active plan matches" in r2.stdout
