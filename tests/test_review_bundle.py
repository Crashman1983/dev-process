import hashlib
import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import pytest


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
        r"head=(?P<head>[0-9a-f]{40,64}) diff=(?P<diff>[0-9a-f]{64})(?: mode=delta)?$",
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
    assert (
        "REVIEW independence=… model=… reviewer=… "
        "round=… tier=… verdict=… work=…"
    ) in t
    assert "attest.py" in t  # the digest is computed by the writer, never typed
    assert "VERBATIM" not in t  # the retired "copy base=… diff=… verbatim" instruction
    assert "['block', 'pass']" in t
    assert "'cross-model'" in t and "'single-family'" in t
    assert "FINDING sev=<blocker|major|minor|nit>" in t


def test_the_projects_review_dimensions_ride_along(render, tmp_path):
    """#130 P3: a project's own review dimensions reach a dispatched reviewer, who reads
    only the bundle — the project owned review.md for them before."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)  # the file stays out of the diff, so its one occurrence is the section
    (out / "docs/process/review.local.md").write_text("# Ours\n\nLayering: routes never import repos.\n")

    t = _run(out, "--base", "main").stdout

    local = t.index("Layering: routes never import repos.")
    assert t.index("# Review Checklist") < local < t.index("## Product frame (judge direction"), t[:400]
    assert "sharpen" in t[t.index("# Review Checklist"):local] and "never weaken" in t


def test_without_local_dimensions_no_section(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)

    assert "This project's review dimensions" not in _run(out, "--base", "main").stdout


def test_bundle_fingerprint_matches_binary_diff(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    text = _run(out, "--base", "main").stdout
    artifact = _artifact(text)
    merge_base = _git(out, "merge-base", "main", "HEAD").stdout.strip()
    head = _git(out, "rev-parse", "HEAD").stdout.strip()
    diff = subprocess.run(
        ["git", "-c", "diff.algorithm=myers", "-c", "diff.renames=false", "-c", "diff.noprefix=false",
         "-c", "diff.mnemonicPrefix=false", "-c", "diff.context=3", "-c", "diff.suppressBlankEmpty=false",
         "-c", "core.quotePath=true",
         "diff", "--binary", "--full-index", "--no-color", "--no-ext-diff", "--no-textconv", "--no-renames",
         f"{merge_base}...{head}"],
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
    r = _run(out, "--skip-preflight")
    assert r.returncode == 0, r.stderr
    t = r.stdout
    assert "no plan under review" in t
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
    # the optional origin (blockers by draft/fix/late for `process_kpis.py rounds`)
    org_line = "[origin=<" + "|".join(sorted(gate.FINDING_ORIGINS, key="draft fix late".split().index)) + ">]"
    assert org_line in bundle_src, org_line
    assert "origin" in gate.FINDING_KEYS


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
    for args in (["--bases", "main"], ["--base", "main", "extra"]):
        r = _run(out, *args)
        assert r.returncode != 0, args
        assert "usage" in (r.stdout + r.stderr)
        assert "Traceback" not in r.stderr
    r = _run(out, "--help")  # asking for help is not an error
    assert r.returncode == 0 and "usage" in r.stdout


def test_plan_filter_narrows_bundle(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    plans = out / ".process-work/plans"
    (plans / "2026-07-11-other.md").write_text("# Other\n\ntier: 2\n")
    r = _run(out, "--base", "main", "--plan", "widget")
    assert r.returncode == 0, r.stderr
    assert "2026-07-09-widget.md" in r.stdout
    assert "2026-07-11-other.md" not in r.stdout
    # a filter matching nothing is an error, naming where it looked — a bundle
    # without the plan asked for would be reviewed as if the work had none
    r2 = _run(out, "--base", "main", "--plan", "nope")
    assert r2.returncode != 0 and "Review bundle" not in r2.stdout
    assert "--plan 'nope' matches no plan" in r2.stderr and "archive" in r2.stderr


def test_preflight_failure_blocks_bundle(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    runner = out / "scripts/process/gate_runner.py"
    runner.write_text("import sys\nprint('gate failed')\nraise SystemExit(1)\n")
    r = _run(out, "--base", "main")
    assert r.returncode == 1
    assert "review bundle blocked: preflight gates failed" in r.stderr
    assert "Review bundle" not in r.stdout


def test_preflight_runner_failure_is_not_a_successful_bundle(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    (out / "scripts/process/gate_runner.py").unlink()
    r = _run(out, "--base", "main")
    assert r.returncode == 2
    assert "review bundle unavailable: preflight runner not runnable" in r.stderr
    assert "Review bundle" not in r.stdout


def test_skip_preflight_is_a_deliberate_opt_out(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    (out / "scripts/process/gate_runner.py").unlink()
    r = _run(out, "--base", "main", "--skip-preflight")
    assert r.returncode == 0, r.stderr
    assert "Review bundle" in r.stdout

def test_delta_bundle_carries_findings_and_exact_delta_artifact(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    previous = _git(out, "rev-parse", "HEAD").stdout.strip()
    reports = out / ".process-work/reviews"
    reports.mkdir(parents=True)
    (reports / "2026-07-10-widget.md").write_text("FINDING prior finding\n")
    # a newer report of ANOTHER work item must not stand in for this one's
    (reports / "2026-07-11-gadget.md").write_text("FINDING stranger's finding\n")
    (out / "widget.py").write_text("def widget():\n    return 43\n")
    _git(out, "add", "-A", check=True)
    _git(out, "commit", "-q", "-m", "fix: widget", check=True)
    text = _run(out, "--base", "main", "--since", previous).stdout
    artifact = _artifact(text)
    # The digest binds the gate's reduced delta and its mode.
    import importlib.util
    spec = importlib.util.spec_from_file_location("check_review", out / "scripts/process/check_review.py")
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    assert artifact["base"] == previous
    assert artifact["diff"] == gate.artifact_digest(out, previous, "HEAD", mode="delta")
    findings = text.split("## Findings from the previous round", 1)[1].split("## Diff under review", 1)[0]
    assert "FINDING prior finding" in findings
    assert "stranger" not in findings  # the reports are in the diff, not in the findings
    assert "REVIEW_SCOPE mode=delta" in text
    assert "Full branch surface:" in text
    # a fix round re-checks the fixed class, not just the spot (downstream, 2 of 10
    # blockers came from the previous fix), and asks for a full bundle when the fix
    # moved a contract — round 1's "name every blocker" is not repeated here
    preamble = text.split("## The binding rules", 1)[0]
    assert "re-check the fixed failure class everywhere it can recur" in preamble
    assert "ask for a full bundle" in preamble
    assert "Name every blocker you find, not the first" not in preamble
    first = _run(out, "--base", "main").stdout.split("## The binding rules", 1)[0]
    assert "Name every blocker you find, not the first" in first
    assert "re-check the fixed failure class" not in first


def test_delta_bundle_says_so_when_this_item_has_no_report(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    reports = out / ".process-work/reviews"
    reports.mkdir(parents=True)
    (reports / "2026-07-11-gadget.md").write_text("FINDING stranger's finding\n")
    text = _run(out, "--base", "main", "--since", "main").stdout
    assert "stranger" not in text
    assert "no review report for this work item (widget, #9)" in text


def test_delta_bundle_refuses_tier_three(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    r = _run(out, "--base", "main", "--since", "main")
    assert r.returncode == 0, r.stderr
    plan = out / ".process-work/plans/2026-07-09-widget.md"
    plan.write_text("# Plan\n\ntier: 3\nissue: #9\n")
    r = _run(out, "--base", "main", "--since", "main")
    assert r.returncode != 0
    assert "Tier 3 delta needs a full round at" in (r.stdout + r.stderr)


# --- SP67: the bundle names the UI evidence (paths — it cannot carry pixels)

def test_bundle_lists_evidence_pair_and_changed_images(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    plans = out / ".process-work/plans"
    plans.mkdir(parents=True, exist_ok=True)
    (plans / "2026-09-07-panel.md").write_text("# Plan\n\ntier: 2\n")
    ev = out / ".process-work/reviews/panel"
    ev.mkdir(parents=True)
    (ev / "before-panel-375-light.png").write_bytes(b"\x89PNG before")
    (ev / "after-panel-375-light.png").write_bytes(b"\x89PNG after")
    (out / "e2e").mkdir(exist_ok=True)
    (out / "e2e/panel-light.png").write_bytes(b"\x89PNG baseline")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "feat: panel with evidence")
    r = _run(out, "--base", "main")
    assert r.returncode == 0, r.stderr
    assert "## UI evidence" in r.stdout
    assert ".process-work/reviews/panel/after-panel-375-light.png" in r.stdout
    assert "A e2e/panel-light.png" in r.stdout
    assert "against the spec's intent" in r.stdout


def test_bundle_names_identical_and_placeholder_evidence_as_void(render, tmp_path):
    # both images of a pair showed only the loading state
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    plans = out / ".process-work/plans"
    (plans / "2026-09-07-panel.md").write_text("# Plan\n\ntier: 2\n")
    ev = out / ".process-work/reviews/panel"
    ev.mkdir(parents=True)
    (ev / "before-panel-375-light.png").write_bytes(b"\x89PNG loading")      # identical pair
    (ev / "after-panel-375-light.png").write_bytes(b"\x89PNG loading")
    (ev / "before-panel-1280-dark.png").write_bytes(b"\x89PNG old dark")     # distinct pair
    (ev / "after-panel-1280-dark.png").write_bytes(b"\x89PNG spinner")
    void = out / "docs/process/void-evidence"
    void.mkdir(parents=True)
    (void / "loading.png").write_bytes(b"\x89PNG spinner")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "feat: panel with evidence")
    t = _run(out, "--base", "main").stdout
    assert "Void evidence" in t
    assert ("VOID: pair `panel-375-light` — `.process-work/reviews/panel/before-panel-375-light.png` and "
            "`.process-work/reviews/panel/after-panel-375-light.png` are byte-identical") in t
    assert "pair `panel-1280-dark`" not in t
    assert "`.process-work/reviews/panel/after-panel-1280-dark.png` is the known void state `loading.png`" in t


def test_bundle_lists_a_distinct_pair_without_void(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    ev = out / ".process-work/reviews/widget"
    ev.mkdir(parents=True)
    (ev / "before-w-375-light.png").write_bytes(b"\x89PNG a")
    (ev / "after-w-375-light.png").write_bytes(b"\x89PNG b")
    t = _run(out, "--base", "main").stdout
    assert "after-w-375-light.png" in t and "- VOID:" not in t and "Void evidence" not in t

def test_bundle_names_missing_evidence_as_a_finding(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    r = _run(out, "--base", "main")
    assert r.returncode == 0, r.stderr
    assert "no screenshots" in r.stdout and "DoD D8" in r.stdout


def test_a_failed_run_leaves_no_stale_bundle_behind(render, tmp_path):
    # a previous bundle must not survive a run that fails — the next step
    # would hand a reviewer the old head and digest
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    bundle = out / "bundle.md"
    bundle.write_text("OLD BUNDLE head=deadbeef\n")
    r = _run(out, "--base", "main", "-o", str(bundle), "--no-such-flag")
    assert r.returncode != 0
    assert not bundle.exists()
    r = _run(out, "--base", "main", "-o", str(bundle), "--skip-preflight")
    assert r.returncode == 0, r.stderr
    assert "Review bundle" in bundle.read_text() and not (out / "bundle.md.partial").exists()


def test_a_large_branch_gets_a_size_warning(render, tmp_path, monkeypatch):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    r = _run(out, "--base", "main")
    assert "SIZE WARNING" not in r.stdout
    for i in range(4):
        (out / f"m{i}.py").write_text("x = 1\n" * 10)
    (out / "uv.lock").write_text("lock\n" * 5000)  # lock files do not count
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "more")
    env = dict(__import__("os").environ, PROCESS_REVIEW_MAX_FILES="3")
    r = subprocess.run([sys.executable, str(out / "scripts/process/make_review_bundle.py"), "--base", "main"],
                       cwd=out, capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
    assert "**SIZE WARNING:** this branch changes 5 files / 42 lines" in r.stdout
    assert "SIZE WARNING" in r.stderr


def test_gate_code_without_a_refute_line_gets_a_warning(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    gate = out / "scripts/process/new_gate.py"
    gate.write_text("x = 1\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "feat: a new gate")
    r = _run(out, "--base", "main")
    assert r.returncode == 0, r.stderr
    assert "**REFUTE WARNING:** this diff changes gate code (scripts/process/new_gate.py)" in r.stdout
    assert "REFUTE WARNING" in r.stderr
    plan = out / ".process-work/plans/2026-07-09-widget.md"
    plan.write_text(plan.read_text() + "\nREFUTE work=9 round=1: 12 scenarios, 2 findings — fixed\n")
    _git(out, "commit", "-q", "-am", "docs: refute recorded")
    r = _run(out, "--base", "main")
    assert "REFUTE WARNING" not in r.stdout + r.stderr


def test_tier_one_product_code_needs_no_refute(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    plan = out / ".process-work/plans/2026-07-09-widget.md"
    plan.write_text(plan.read_text().replace("tier: 2", "tier: 1"))
    _git(out, "commit", "-q", "-am", "tier 1")
    assert "REFUTE WARNING" not in _bundle(out, "--base", "main").stdout


def test_tier_two_product_code_is_attacked_inside_the_review(render, tmp_path):
    """Review depth by risk class: a separate refute run before every Tier 2 review
    cost a round of its own; the Tier 2 reviewer answers the refuter's brief instead.
    Tier 3 still warns without a REFUTE line, gate code at any tier (test above)."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    r = _bundle(out, "--base", "main")
    assert "REFUTE WARNING" not in r.stdout + r.stderr
    brief = r.stdout.split("## The binding rules", 1)[0]
    assert "**Tier 2: the review is also the attack.**" in brief
    order = [brief.index(k) for k in ("OWNER", "FAIL-OPEN", "EDGE CASES", "EVIDENCE")]
    assert order == sorted(order)
    assert "docs/process/failure-catalog.md" in brief
    reviewed = _git(out, "rev-parse", "HEAD").stdout.strip()
    # a fix round of product code below Tier 3 asks no refute either
    (out / "widget.py").write_text("def widget():\n    return 43\n")
    _git(out, "commit", "-q", "-am", "fix: widget")
    assert "REFUTE WARNING" not in _bundle(out, "--base", "main", "--since", reviewed).stdout
    # Tier 3 runs a separate refute and carries no Tier 2 brief
    _plan_commit(out, "# Plan\n\ntier: 3\nissue: #9\n")
    r = _bundle(out, "--base", "main")
    assert ("**REFUTE WARNING:** 2026-07-09-widget.md (tier: 3) carries no `REFUTE work=<its id> "
            "round=<r>: …` line — from Tier 3 on") in r.stdout
    assert "Tier 2: the review is also the attack" not in r.stdout


def test_a_tier_two_plan_without_a_line_is_named_next_to_a_refuted_one(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    plans = out / ".process-work/plans"
    (plans / "2026-07-09-widget.md").write_text("# Plan\n\ntier: 2\nissue: #9\n\n" + R1_LINE)
    (plans / "2026-07-10-small.md").write_text("# Small\n\ntier: 1\nissue: #11\n")
    (plans / "2026-07-10-other.md").write_text("# Other\n\ntier: 3\nissue: #10\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "three plans")
    t = _bundle(out, "--base", "main").stdout
    assert "**REFUTE WARNING:** 2026-07-10-other.md (tier: 3) carries no" in t
    assert "widget.md (tier" not in t and "small.md (tier" not in t
    # an example line in a code block is no record
    (plans / "2026-07-10-other.md").write_text(
        "# Other\n\ntier: 3\nissue: #10\n\n```\nREFUTE work=10 round=1: 5 scenarios, 0 findings\n```\n")
    _git(out, "commit", "-q", "-am", "example only")
    assert "2026-07-10-other.md (tier: 3) carries no" in _bundle(out, "--base", "main").stdout


def _gate_commit(out, rel, text="x = 1\n", msg="gate change"):
    f = out / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(text)
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", msg)


def test_moving_a_gate_file_out_of_the_gate_paths_warns(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    _git(out, "mv", "scripts/process/tidy.py", "tidy_elsewhere.py")
    _git(out, "commit", "-q", "-m", "move a gate away")
    assert "**REFUTE WARNING:**" in _run(out, "--base", "main").stdout


def test_gate_starters_and_non_ascii_names_warn(render, tmp_path):
    for rel in ("Makefile", ".pre-commit-config.yaml", ".github/workflows/gates.yml",
                "scripts/process/prüfung.py"):
        out = render(tmp_path / rel.replace("/", "_"), {"project_name": "d", "modules": {}})
        _seed_repo(out)
        _gate_commit(out, rel)
        assert "**REFUTE WARNING:**" in _run(out, "--base", "main").stdout, rel


def test_an_example_refute_line_does_not_count(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    _gate_commit(out, "scripts/process/g.py")
    plan = out / ".process-work/plans/2026-07-09-widget.md"
    base = plan.read_text()
    for example in ("\n```\nREFUTE work=9 round=1: done\n```\n",
                    "\n<!-- REFUTE work=9 round=1: done -->\n",
                    "\n    REFUTE work=9 round=1: indented code block\n",
                    "\nREFUTE work=<id> round=<r>: placeholder\n",
                    "\nREFUTE work=TODO round=1: later\n",
                    # a mention is not a record: no round, no content, backticks
                    "\nREFUTE work=9\n",
                    "\nREFUTE work=9 round=1:\n",
                    "\n`REFUTE work=9 round=1: done`\n",
                    "\nSee `REFUTE work=9 round=1: done` in the brief.\n",
                    # refute of the fix: an unclosed comment hides the rest, a lone
                    # marker does not lift a code block, a to-do is not a record
                    "\n<!-- draft\nREFUTE work=9 round=1: done\n",
                    "\n-\n\n    REFUTE work=9 round=1: code block\n",
                    "\n- [ ] REFUTE work=9 round=1: run before review\n",
                    "\nREFUTE work=9 round=1: TODO\n",
                    "\nREFUTE work=9 round=1: …\n"):
        plan.write_text(base + example)
        _git(out, "commit", "-q", "-am", "plan")
        assert "**REFUTE WARNING:**" in _run(out, "--base", "main").stdout, example


def test_list_styles_of_a_real_refute_line_count(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    _gate_commit(out, "scripts/process/g.py")
    plan = out / ".process-work/plans/2026-07-09-widget.md"
    base = plan.read_text()
    for line in ("- [x] REFUTE work=9 round=1: done", "+ REFUTE work=9 round=1: done",
                 "1. REFUTE work=9 round=1: done", "REFUTE work=2026-07-09-widget round=2: `x` held"):
        plan.write_text(base + "\n" + line + "\n")
        _git(out, "commit", "-q", "-am", "plan")
        assert "REFUTE WARNING" not in _bundle(out, "--base", "main").stdout, line


def test_a_refute_line_of_another_plan_does_not_cover_this_one(render, tmp_path):
    # stacked plans: each one records its own refute
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    _gate_commit(out, "scripts/process/g.py")
    plans = out / ".process-work/plans"
    (plans / "2026-07-10-other.md").write_text("# Other\n\ntier: 2\nissue: #10\n\n"
                                               "REFUTE work=10 round=1: 5 scenarios, 0 findings\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "stacked plan")
    t = _run(out, "--base", "main").stdout
    assert "**REFUTE WARNING:**" in t and "2026-07-09-widget.md" in t and "2026-07-10-other.md carries" not in t
    widget = plans / "2026-07-09-widget.md"
    widget.write_text(widget.read_text() + "\nREFUTE work=10 round=1: borrowed\n")
    _git(out, "commit", "-q", "-am", "a line naming the other work")
    assert "**REFUTE WARNING:**" in _run(out, "--base", "main").stdout


def test_a_delta_re_review_of_gate_code_needs_a_new_refute_line(render, tmp_path):
    # the fix round's gate code gets refuted, not the first round's line reused
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    plan = out / ".process-work/plans/2026-07-09-widget.md"
    plan.write_text(plan.read_text() + "\nREFUTE work=9 round=1: 12 scenarios, 2 findings — fixed\n")
    _gate_commit(out, "scripts/process/g.py")
    reviewed = _git(out, "rev-parse", "HEAD").stdout.strip()
    assert "REFUTE WARNING" not in _bundle(out, "--base", "main").stdout
    _gate_commit(out, "scripts/process/g.py", "x = 2\n", "fix round")
    r = _run(out, "--base", "main", "--since", reviewed)
    assert r.returncode == 0, r.stderr
    assert "**REFUTE WARNING:** this delta changes gate code" in r.stdout and "REFUTE WARNING" in r.stderr
    plan.write_text(plan.read_text() + "REFUTE work=9 round=2: 6 scenarios, 0 findings\n")
    _git(out, "commit", "-q", "-am", "docs: refute of the fix")
    assert "REFUTE WARNING" not in _bundle(out, "--base", "main", "--since", reviewed).stdout
    # a delta without gate code needs none
    (out / "widget.py").write_text("def widget():\n    return 43\n")
    _git(out, "commit", "-q", "-am", "product fix")
    head = _git(out, "rev-parse", "HEAD~1").stdout.strip()
    assert "REFUTE WARNING" not in _bundle(out, "--base", "main", "--since", head).stdout


def test_a_comment_across_two_fences_does_not_hide_a_real_line(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    _gate_commit(out, "scripts/process/g.py")
    plan = out / ".process-work/plans/2026-07-09-widget.md"
    plan.write_text(plan.read_text() + "\n```\n<!--\n```\n\nREFUTE work=9 round=1: 4 scenarios, 0 findings\n"
                    "\n```\n-->\n```\n")
    _git(out, "commit", "-q", "-am", "plan")
    assert "REFUTE WARNING" not in _bundle(out, "--base", "main").stdout


def test_a_delta_does_not_take_a_reformatted_or_moved_old_line_as_new(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    plans = out / ".process-work/plans"
    plan = plans / "2026-07-09-widget.md"
    plan.write_text(plan.read_text() + "\nREFUTE work=9 round=1: 12 scenarios, 2 findings — fixed\n")
    _gate_commit(out, "scripts/process/g.py")
    reviewed = _git(out, "rev-parse", "HEAD").stdout.strip()
    _gate_commit(out, "scripts/process/g.py", "x = 2\n", "fix round")
    plan.write_text(plan.read_text().replace("REFUTE work=9", "- REFUTE work=9") + "\n")
    _git(out, "commit", "-q", "-am", "reformat")
    assert "**REFUTE WARNING:** this delta" in _run(out, "--base", "main", "--since", reviewed).stdout
    _git(out, "mv", str(plan), str(plans / "2026-07-11-widget.md"))
    _git(out, "commit", "-q", "-m", "rename the plan")
    assert "**REFUTE WARNING:** this delta" in _run(out, "--base", "main", "--since", reviewed).stdout
    moved = plans / "2026-07-11-widget.md"
    moved.write_text(moved.read_text() + "REFUTE work=9 round=2: 6 scenarios, 0 findings\n")
    _git(out, "commit", "-q", "-am", "refute of the fix")
    assert "REFUTE WARNING" not in _bundle(out, "--base", "main", "--since", reviewed).stdout


def test_a_delta_without_a_base_still_checks_refute(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    reviewed = _git(out, "rev-parse", "HEAD").stdout.strip()
    _gate_commit(out, "scripts/process/g.py", "x = 2\n", "fix round")
    # without a base no plan can be listed, so no tier is declared: refused (D2)
    r = _run(out, "--base", "nosuchbase", "--since", reviewed)
    assert r.returncode != 0 and "no tier is declared" in r.stderr
    r = _run(out, "--base", "nosuchbase", "--since", reviewed, "--tier", "2")
    assert "**REFUTE WARNING:** this delta" in r.stdout, r.stdout[:400] + r.stderr


def test_no_merge_base_says_the_refute_check_did_not_run(render, tmp_path, monkeypatch):
    import importlib.util
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(out / "scripts/process"))
    spec = importlib.util.spec_from_file_location("mrb_under_test", out / "scripts/process/make_review_bundle.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "_gate_files", lambda root, base: None)
    assert "REFUTE check unavailable" in mod.build(out, "main")


# --- one owner for the record homes: Spec Kit plans count, in full and delta


def _spec_kit_repo(out):
    """The widget work planned the Spec Kit way: specs/<dir>/plan.md only."""
    _seed_repo(out)
    _git(out, "rm", "-q", ".process-work/plans/2026-07-09-widget.md")
    spec = out / "specs/001-widget"
    spec.mkdir(parents=True)
    (spec / "plan.md").write_text("# Plan\n\ntier: 2\nissue: #9\n\n"
                                  "REFUTE work=9 round=1: 12 scenarios, 2 findings — fixed\n")
    _gate_commit(out, "scripts/process/g.py", msg="gate change with a spec kit plan")
    return spec / "plan.md"


def test_a_spec_kit_plan_is_under_review_and_carries_its_refute_line(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _spec_kit_repo(out)
    t = _bundle(out, "--base", "main").stdout
    assert "### specs/001-widget/plan.md" in t and "REFUTE WARNING" not in t
    assert "### specs/001-widget/plan.md" in _bundle(out, "--base", "main", "--plan", "001-widget").stdout


def test_a_delta_needs_a_new_refute_line_in_a_spec_kit_plan(render, tmp_path):
    # the delta pre-state read only the plan folder: the old round=1 line of a
    # Spec Kit plan passed as new
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    plan = _spec_kit_repo(out)
    reviewed = _git(out, "rev-parse", "HEAD").stdout.strip()
    _gate_commit(out, "scripts/process/g.py", "x = 2\n", "fix round")
    t = _bundle(out, "--base", "main", "--since", reviewed).stdout
    assert "**REFUTE WARNING:** this delta" in t and "specs/001-widget/plan.md carries no new" in t
    plan.write_text(plan.read_text() + "REFUTE work=9 round=2: 6 scenarios, 0 findings\n")
    _git(out, "commit", "-q", "-am", "refute of the fix")
    assert "REFUTE WARNING" not in _bundle(out, "--base", "main", "--since", reviewed).stdout


def test_stacked_plans_of_one_issue_do_not_cancel_each_others_new_round(render, tmp_path):
    # the earlier self of a plan is found by identity (path or rename), not by
    # a work id another plan shares
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    plans = out / ".process-work/plans"
    widget = plans / "2026-07-09-widget.md"
    widget.write_text(widget.read_text() + "\nREFUTE work=9 round=1: 12 scenarios, 2 findings — fixed\n")
    other = plans / "2026-07-10-other.md"
    other.write_text("# Other\n\ntier: 2\nissue: #9\n\nThe second slice of the same issue.\n")
    _gate_commit(out, "scripts/process/g.py")
    reviewed = _git(out, "rev-parse", "HEAD").stdout.strip()
    _gate_commit(out, "scripts/process/g.py", "x = 2\n", "fix round")
    widget.write_text(widget.read_text() + "REFUTE work=9 round=2: 6 scenarios, 0 findings\n")
    _git(out, "commit", "-q", "-am", "refute of the fix, first plan")
    t = _bundle(out, "--base", "main", "--since", reviewed).stdout
    assert "**REFUTE WARNING:**" in t and "2026-07-10-other.md carries" in t
    other.write_text(other.read_text() + "\nREFUTE work=9 round=1: 5 scenarios, 0 findings\n")
    _git(out, "commit", "-q", "-am", "refute of the fix, second plan")
    assert "REFUTE WARNING" not in _bundle(out, "--base", "main", "--since", reviewed).stdout


def test_a_renamed_and_rewritten_plan_does_not_turn_its_old_line_new(render, tmp_path):
    # past git's rename threshold the old plan is gone, not renamed: its work
    # ids still find it
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    plans = out / ".process-work/plans"
    plan = plans / "2026-07-09-widget.md"
    plan.write_text(plan.read_text() + "\nREFUTE work=9 round=1: 12 scenarios, 2 findings — fixed\n")
    _gate_commit(out, "scripts/process/g.py")
    reviewed = _git(out, "rev-parse", "HEAD").stdout.strip()
    _gate_commit(out, "scripts/process/g.py", "x = 2\n", "fix round")
    _git(out, "rm", "-q", str(plan))
    (plans / "2026-07-12-widget-v2.md").write_text(
        "# A rewritten plan\n\ntier: 2\nissue: #9\n\n" + "".join(f"- step {i}\n" for i in range(40))
        + "\nREFUTE work=9 round=1: 12 scenarios, 2 findings — fixed\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "rewrite the plan")
    assert "**REFUTE WARNING:** this delta" in _bundle(out, "--base", "main", "--since", reviewed).stdout


def test_an_inline_comment_opener_in_prose_does_not_hide_a_real_line(render, tmp_path):
    # CommonMark: an unclosed `<!--` hides the rest only when it starts a line
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    _gate_commit(out, "scripts/process/g.py")
    plan = out / ".process-work/plans/2026-07-09-widget.md"
    base = plan.read_text()
    line = "REFUTE work=9 round=1: 4 scenarios, 0 findings\n"
    for prose in ("\nWrite <!-- to start a comment.\n\n" + line,
                  "\nWrite `<!--` to start a comment.\n\n" + line + "\n<!-- a closed note -->\n",
                  "\nA closed <!-- aside --> comment in running text.\n\n" + line):
        plan.write_text(base + prose)
        _git(out, "commit", "-q", "-am", "plan")
        assert "REFUTE WARNING" not in _bundle(out, "--base", "main").stdout, prose
    # a comment closed later in the same paragraph still hides what it spans
    plan.write_text(base + "\nNote <!-- hidden\n" + line + "--> end.\n")
    _git(out, "commit", "-q", "-am", "plan")
    assert "**REFUTE WARNING:**" in _bundle(out, "--base", "main").stdout


def test_a_delta_finds_the_previous_report_by_its_header(render, tmp_path):
    # the documented report names its work in the header (`work: #N`); its
    # file name carries the review's own slug
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    previous = _git(out, "rev-parse", "HEAD").stdout.strip()
    reports = out / ".process-work/reviews"
    reports.mkdir(parents=True)
    (reports / "2026-07-10-round-one.md").write_text(
        "review: round-one\nwork: #9\npublish-waived: local\n\n## Findings\nFINDING prior finding\n")
    (reports / "2026-07-11-round-one-elsewhere.md").write_text(
        "review: round-one-elsewhere\nwork: #10\n\n## Findings\nFINDING stranger's finding\n")
    (out / "widget.py").write_text("def widget():\n    return 43\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "fix: widget")
    text = _bundle(out, "--base", "main", "--since", previous).stdout
    findings = text.split("## Findings from the previous round", 1)[1].split("## Diff under review", 1)[0]
    assert "FINDING prior finding" in findings and "stranger" not in findings


# --- refute of the record-homes fix


def _bundle(out, *args):
    """A bundle that was really built — a `not in` on an empty stdout proves nothing."""
    r = _run(out, *args, "--skip-preflight")
    assert r.returncode == 0 and "# Review bundle" in r.stdout, r.stdout[-400:] + r.stderr
    return r


R1_LINE = "REFUTE work=9 round=1: 12 scenarios, 2 findings — fixed\n"


def _findings(text):
    return text.split("## Findings from the previous round", 1)[1].split("## Diff under review", 1)[0]


def _spec(out, name, plan, tasks=None):
    d = out / "specs" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "plan.md").write_text(plan)
    if tasks is not None:
        (d / "tasks.md").write_text(tasks)
    return d / "plan.md"


def _spec_only_repo(out, on_main=()):
    """main carries `on_main` (spec dirs written before the base commit); the
    branch works on specs/002-new only."""
    for name, plan, tasks in on_main:
        _spec(out, name, plan, tasks)
    _seed_repo(out)
    _git(out, "rm", "-q", ".process-work/plans/2026-07-09-widget.md")
    plan = _spec(out, "002-new", "# Plan\n\ntier: 2\nissue: #9\n\n" + R1_LINE, "- [ ] T1 build it\n")
    _gate_commit(out, "scripts/process/g.py", msg="gate change")
    return plan


def test_a_finished_spec_kit_plan_is_not_under_review(render, tmp_path):
    # E1: Spec Kit plans never archive — a finished one is not this branch's work
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    plan = _spec_only_repo(out, [("001-old", "# Old\n\ntier: 2\nissue: #3\n\n"
                                  "REFUTE work=3 round=1: 4 scenarios, 0 findings\n", "- [x] T1 done\n")])
    reviewed = _git(out, "rev-parse", "HEAD").stdout.strip()
    _gate_commit(out, "scripts/process/g.py", "x = 2\n", "fix round")
    plan.write_text(plan.read_text() + "REFUTE work=9 round=2: 6 scenarios, 0 findings\n")
    _git(out, "commit", "-q", "-am", "refute of the fix")
    t = _bundle(out, "--base", "main", "--since", reviewed).stdout
    assert "REFUTE WARNING" not in t and "specs/001-old" not in t, t[:600]
    assert "### specs/002-new/plan.md" in t
    # asked for by name, it is bundled
    assert "### specs/001-old/plan.md" in _bundle(out, "--base", "main", "--plan", "001-old").stdout


def test_an_unfinished_spec_kit_plan_elsewhere_is_not_under_review(render, tmp_path):
    # D2: the plans under review are the ones the branch touches — an unticked
    # task in another spec does not make its plan this branch's work
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _spec_only_repo(out, [("003-wip", "# Wip\n\ntier: 2\nissue: #4\n", "- [x] T1\n- [ ] T2\n")])
    t = _bundle(out, "--base", "main").stdout
    assert "specs/003-wip" not in t and "### specs/002-new/plan.md" in t
    assert "### specs/003-wip/plan.md" in _bundle(out, "--base", "main", "--plan", "003-wip").stdout


def test_a_branch_that_only_ticks_tasks_brings_its_spec_plan(render, tmp_path):
    """D2: a feature is touched when any file of its spec directory changes — a branch
    that only ticks tasks.md implements that plan; without it the bundle had no plan,
    no tier and no refute warning."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _spec_only_repo(out, [("003-wip", "# Wip\n\ntier: 2\nissue: #4\n", "- [ ] T1\n- [ ] T2\n")])
    tasks = out / "specs/003-wip/tasks.md"
    tasks.write_text("- [x] T1\n- [ ] T2\n")
    _git(out, "commit", "-q", "-am", "T1")

    t = _bundle(out, "--base", "main").stdout

    assert "### specs/003-wip/plan.md" in t and "### specs/002-new/plan.md" in t, t[:600]


def test_an_unrelated_tier_three_spec_plan_does_not_refuse_a_delta(render, tmp_path):
    # E2: a product document at specs/api/plan.md, no speckit module
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _spec_only_repo(out, [("api", "# API plan\n\ntier: 3\n", None)])
    r = _bundle(out, "--base", "main", "--since", "HEAD~1")
    assert r.returncode == 0, r.stderr
    assert "specs/api" not in r.stdout and "REFUTE WARNING" not in _bundle(out, "--base", "main").stdout
    # a Tier 3 plan under review still refuses — and says how to narrow
    r = _run(out, "--base", "main", "--since", "HEAD~1", "--plan", "api")
    assert r.returncode != 0 and "specs/api/plan.md declares tier: 3" in r.stderr and "--plan" in r.stderr
    assert "Tier 3 delta needs a full round at" in r.stderr


def test_the_printed_label_of_a_spec_kit_plan_works_as_plan_filter(render, tmp_path):
    # D13b
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _spec_only_repo(out)
    assert "### specs/002-new/plan.md" in _bundle(out, "--base", "main", "--plan", "specs/002-new").stdout


def test_a_report_of_another_work_is_never_this_items(render, tmp_path):
    # R1: `review:` matched inside another word, `work:` naming another issue
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    reports = out / ".process-work/reviews"
    reports.mkdir(parents=True)
    (reports / "2026-07-10-r.md").write_text("review: widgets-fix\nwork: #12\n\nFINDING stranger's finding\n")
    (reports / "2026-07-11-widget.md").write_text("review: widget\nwork: #12\n\nFINDING stranger's too\n")
    t = _bundle(out, "--base", "main", "--since", "HEAD").stdout
    assert "stranger" not in _findings(t) and "no review report for this work item" in t
    # issues are tried first: a report of #9 beats a newer one named after the slug
    (reports / "2026-07-12-a.md").write_text("review: a\nwork: #9\n\nFINDING by issue\n")
    (reports / "2026-07-13-widget-notes.md").write_text("FINDING by name\n")
    assert "FINDING by issue" in _findings(_bundle(out, "--base", "main", "--since", "HEAD").stdout)


def test_another_repositorys_issue_is_not_this_repos(render, tmp_path):
    # R2
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    reports = out / ".process-work/reviews"
    reports.mkdir(parents=True)
    (reports / "2026-07-10-r.md").write_text("review: r\nwork: other/repo#9\n\nFINDING stranger's finding\n")
    assert "stranger" not in _findings(_bundle(out, "--base", "main", "--since", "HEAD").stdout)


def _delta_repo(out):
    """widget (#9) with round 1 reviewed at `reviewed`, then a fix round of
    gate code."""
    _seed_repo(out)
    plans = out / ".process-work/plans"
    widget = plans / "2026-07-09-widget.md"
    widget.write_text(widget.read_text() + "\n" + R1_LINE)
    _gate_commit(out, "scripts/process/g.py")
    reviewed = _git(out, "rev-parse", "HEAD").stdout.strip()
    _gate_commit(out, "scripts/process/g.py", "x = 2\n", "fix round")
    return plans, widget, reviewed


def test_an_archived_plan_line_copied_into_a_new_plan_is_not_new(render, tmp_path):
    # D3: a pure move to archive/ is a rename to git; the copied line is old
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    plans, widget, reviewed = _delta_repo(out)
    (plans / "archive").mkdir(exist_ok=True)
    _git(out, "mv", str(widget), str(plans / "archive" / widget.name))
    (plans / "2026-07-11-next.md").write_text("# Next\n\ntier: 2\nissue: #9\n\nA fresh approach.\n\n" + R1_LINE)
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "archive and replan")
    assert "**REFUTE WARNING:** this delta" in _bundle(out, "--base", "main", "--since", reviewed).stdout


def test_a_new_stacked_plan_keeps_its_round_when_the_old_one_is_archived_with_edits(render, tmp_path):
    # D9: no similarity score decides — the new plan's own line is new
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    plans, widget, reviewed = _delta_repo(out)
    (plans / "archive").mkdir(exist_ok=True)
    (plans / "archive" / widget.name).write_text(
        "# Archived\n\ntier: 2\nissue: #9\n\n" + "".join(f"- outcome {i}\n" for i in range(30)) + R1_LINE)
    _git(out, "rm", "-q", str(widget))
    (plans / "2026-07-11-next.md").write_text(
        "# Next\n\ntier: 2\nissue: #9\n\nREFUTE work=9 round=1: 7 scenarios, 1 finding — fixed\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "archive with edits, stacked plan")
    # D2: the archived plan is touched, so it is under review too — its old
    # round is named; the new plan's own round stands
    warning = [ln for ln in _bundle(out, "--base", "main", "--since", reviewed).stdout.splitlines()
               if ln.startswith("**REFUTE WARNING:**")]
    assert len(warning) == 1 and "2026-07-11-next.md" not in warning[0], warning
    assert f"and {widget.name} carries no new" in warning[0], warning


def test_a_line_that_starts_to_count_with_a_new_id_is_not_new(render, tmp_path):
    # D6/D11: old rounds are read with the plan's CURRENT ids
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    widget = out / ".process-work/plans/2026-07-09-widget.md"
    widget.write_text(widget.read_text() + "\nREFUTE work=12 round=1: 5 scenarios, 0 findings\n")
    _gate_commit(out, "scripts/process/g.py")
    reviewed = _git(out, "rev-parse", "HEAD").stdout.strip()
    _gate_commit(out, "scripts/process/g.py", "x = 2\n", "fix round")
    widget.write_text(widget.read_text().replace("issue: #9\n", "issue: #9\nissue: #12\n"))
    _git(out, "commit", "-q", "-am", "the plan takes over #12")
    assert "**REFUTE WARNING:** this delta" in _bundle(out, "--base", "main", "--since", reviewed).stdout


def test_a_copied_plan_brings_no_new_round(render, tmp_path):
    # D1: a copy keeping the old line
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    plans, widget, reviewed = _delta_repo(out)
    widget.write_text(widget.read_text() + "REFUTE work=9 round=2: 6 scenarios, 0 findings\n")
    _git(out, "commit", "-q", "-am", "refute of the fix")
    assert "REFUTE WARNING" not in _bundle(out, "--base", "main", "--since", reviewed).stdout
    (plans / "2026-07-11-copy.md").write_text("# Copy\n\ntier: 2\nissue: #9\n\n" + R1_LINE)
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "a copy of the plan")
    t = _bundle(out, "--base", "main", "--since", reviewed).stdout
    assert "**REFUTE WARNING:**" in t and "2026-07-11-copy.md carries" in t


def test_a_stacked_plans_old_round_merged_into_the_other_is_not_new(render, tmp_path):
    # D2
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    plans, widget, _ = _delta_repo(out)
    other = plans / "2026-07-10-other.md"
    other.write_text("# Other\n\ntier: 2\nissue: #9\n\nREFUTE work=9 round=2: 3 scenarios, 0 findings\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "stacked plan")
    reviewed = _git(out, "rev-parse", "HEAD").stdout.strip()
    _gate_commit(out, "scripts/process/g.py", "x = 3\n", "second fix round")
    widget.write_text(widget.read_text() + "REFUTE work=9 round=2: 3 scenarios, 0 findings\n")
    _git(out, "rm", "-q", str(other))
    _git(out, "commit", "-q", "-am", "merge the stacked plan into the widget")
    assert "**REFUTE WARNING:** this delta" in _bundle(out, "--base", "main", "--since", reviewed).stdout


def test_a_backtick_inside_a_comment_does_not_unhide_it(render, tmp_path):
    # C1/C2: the comment opened first wins; an escaped backtick opens no span
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    _gate_commit(out, "scripts/process/g.py")
    plan = out / ".process-work/plans/2026-07-09-widget.md"
    base = plan.read_text()
    for hidden in ("\nNote <!-- a `tick\n" + R1_LINE + "--> and `more` here.\n",
                   "\nEscaped \\` then <!-- hidden\n" + R1_LINE + "--> and ` here.\n"):
        plan.write_text(base + hidden)
        _git(out, "commit", "-q", "-am", "plan")
        assert "**REFUTE WARNING:**" in _bundle(out, "--base", "main").stdout, hidden


def test_many_unclosed_comment_openers_are_read_in_linear_time(render, tmp_path):
    # F5: 40k unclosed `<!--` in one paragraph took 39 s
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    _gate_commit(out, "scripts/process/g.py")
    plan = out / ".process-work/plans/2026-07-09-widget.md"
    plan.write_text(plan.read_text() + "\nprose " + "x <!-- " * 40000 + "\n\n" + R1_LINE)
    _git(out, "commit", "-q", "-am", "plan")
    r = subprocess.run([sys.executable, str(out / "scripts/process/make_review_bundle.py"), "--base", "main",
                        "--skip-preflight"], cwd=out, capture_output=True, text=True, timeout=15)
    assert r.returncode == 0 and "REFUTE WARNING" not in r.stdout


def test_a_non_utf8_byte_does_not_empty_a_plan(render, tmp_path):
    # F6
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    _gate_commit(out, "scripts/process/g.py")
    plan = out / ".process-work/plans/2026-07-09-widget.md"
    plan.write_bytes(plan.read_bytes() + "caf\xe9\n\n".encode("latin-1") + R1_LINE.encode())
    _git(out, "commit", "-q", "-am", "plan")
    t = _bundle(out, "--base", "main").stdout
    assert "REFUTE WARNING" not in t and "tier: 2" in t


def test_an_old_round_moved_with_a_new_id_is_not_new(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    plans = out / ".process-work/plans"
    plan = plans / "2026-07-09-widget.md"
    plan.write_text(plan.read_text() + "\nREFUTE work=widget round=1: 12 scenarios, 2 findings — fixed\n")
    _gate_commit(out, "scripts/process/g.py")
    reviewed = _git(out, "rev-parse", "HEAD").stdout.strip()
    _gate_commit(out, "scripts/process/g.py", "x = 2\n", "fix round")
    _git(out, "mv", str(plan), str(plans / "2026-07-09-widget-v2.md"))
    moved = plans / "2026-07-09-widget-v2.md"
    moved.write_text(moved.read_text().replace("work=widget round", "work=widget-v2 round"))
    _git(out, "commit", "-q", "-am", "rename, id changed along")
    assert "**REFUTE WARNING:** this delta" in _run(out, "--base", "main", "--since", reviewed).stdout


def test_another_works_identical_line_in_a_plan_in_place_is_not_this_plans_old_round(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    # the other work's plan is archived on main: in place, and not touched by
    # the branch (a touched one would be under review itself — D2)
    archive = out / ".process-work/plans/archive"
    archive.mkdir(parents=True, exist_ok=True)
    (archive / "2026-06-01-a.md").write_text("# a\n\ntier: 2\nissue: #3\n\nREFUTE work=3 round=1: 5 scenarios, 0 findings\n")
    _seed_repo(out)
    _gate_commit(out, "scripts/process/g.py")
    reviewed = _git(out, "rev-parse", "HEAD").stdout.strip()
    _gate_commit(out, "scripts/process/g.py", "x = 2\n", "fix round")
    plan = out / ".process-work/plans/2026-07-09-widget.md"
    plan.write_text(plan.read_text() + "\nREFUTE work=9 round=1: 5 scenarios, 0 findings\n")
    _git(out, "commit", "-q", "-am", "own refute")
    assert "REFUTE WARNING" not in _bundle(out, "--base", "main", "--since", reviewed).stdout


# --- refute of the tier warning: the tier is read by the gate's own owner

_PLANS = ".process-work/plans"
_FENCED_TIER = "# Plan\n\ntier: 1\nissue: #9\n\nExample:\n\n```\ntier: 3\n```\n"
_SECOND_TIER = "# Plan\n\ntier: 1\nissue: #9\n\n## Decisions\n\n- tier: 2 was considered, kept at 1\n"


def _plan_commit(out, text, name="2026-07-09-widget.md"):
    (out / _PLANS / name).write_text(text)
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "plan edit")


def test_the_bundle_reads_a_plans_tier_as_the_review_gate_does(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    sys.path.insert(0, str(out / "scripts/process"))
    try:
        spec = importlib.util.spec_from_file_location("mrb_tier", out / "scripts/process/make_review_bundle.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        sys.path.remove(str(out / "scripts/process"))
    gate = mod._review_gate
    for text in (_FENCED_TIER, _SECOND_TIER, "- tier: 2\n", "**tier:** 2\n", "Tier: 2\n", "tier: 2a\n",
                 "<!--\ntier: 2\n-->\n", "    tier: 2\n", "tier: 2\n\ntier: 1\n"):
        m = gate.TIER_DECL.search(gate._unfenced(text))  # how the presence gate reads it
        assert mod._declared_tier([text]) == (int(m.group(1)) if m else None), text


@pytest.mark.parametrize("text", [_FENCED_TIER, _SECOND_TIER])
def test_an_example_or_a_second_tier_line_asks_no_refute(render, tmp_path, text):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    _plan_commit(out, text)
    assert "REFUTE WARNING" not in _bundle(out, "--base", "main").stdout
    # and a fenced tier 3 no longer refuses a delta
    r = _run(out, "--base", "main", "--since", "HEAD~1", "--skip-preflight")
    assert r.returncode == 0, r.stderr


def test_a_design_doc_or_a_waived_plan_asks_no_refute(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    _plan_commit(out, "# Plan\n\ntier: 2\nissue: #9\n\n" + R1_LINE)
    _plan_commit(out, "# Design\n\ntier: 2\n", "design-widget.md")
    _plan_commit(out, "# Docs\n\ntier: 2\nissue: #12\nreview-waived: docs only, #12\n", "2026-07-10-docs.md")
    t = _bundle(out, "--base", "main").stdout
    assert "REFUTE WARNING" not in t, [ln for ln in t.splitlines() if "REFUTE" in ln]


def test_a_waiver_quoted_in_a_code_block_waives_nothing(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    _plan_commit(out, "# Plan\n\ntier: 3\nissue: #9\n\n```\nreview-waived: docs only, #12\n```\n")
    assert "2026-07-09-widget.md (tier: 3) carries no" in _bundle(out, "--base", "main").stdout


def test_the_tier_warning_needs_no_base(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    # without a base the branch's plans cannot be listed (D2) — named, the
    # plan's tier still asks for its refute
    _plan_commit(out, "# Plan\n\ntier: 3\nissue: #9\n")
    r = _bundle(out, "--base", "nosuchbase", "--plan", "widget")
    assert "**REFUTE WARNING:** 2026-07-09-widget.md (tier: 3) carries no" in r.stdout
    assert "REFUTE WARNING" in r.stderr


def test_a_tier_two_plan_without_a_base_is_told_gate_code_went_unchecked(render, tmp_path):
    """Refute of v2.47: Tier 2 needs no refute run, but without a base nobody can
    see gate code — the bundle said nothing at all."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    _plan_commit(out, "# Plan\n\ntier: 2\nissue: #9\n")
    r = _bundle(out, "--base", "nosuchbase", "--plan", "widget")
    assert "REFUTE check unavailable: no base ref, so gate code cannot be detected" in r.stdout
    assert "**REFUTE WARNING:**" not in r.stdout


def test_gate_code_warns_once_and_a_long_list_is_cut(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    _gate_commit(out, "scripts/process/g.py")
    r = _bundle(out, "--base", "main")
    assert r.stdout.count("**REFUTE WARNING:**") == 1 and "changes gate code" in r.stdout
    assert r.stderr.count("REFUTE WARNING") == 1
    out = render(tmp_path / "many", {"project_name": "d", "modules": {}})
    _seed_repo(out)
    for i in range(4):
        _plan_commit(out, f"# P{i}\n\ntier: 3\nissue: #{20 + i}\n", f"2026-07-1{i}-p{i}.md")
    line = [ln for ln in _bundle(out, "--base", "main").stdout.splitlines()
            if ln.startswith("**REFUTE WARNING:**")]
    assert len(line) == 1 and line[0].count("(tier: 3)") == 3 and " … carries no" in line[0], line


# --- R3 (#130): the plans the branch touches, --tier, what the reviewer reads


def _module(out, name="make_review_bundle"):
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(out / "scripts/process"))
    spec = importlib.util.spec_from_file_location(f"{name}_r3", out / f"scripts/process/{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _plans_section(text):
    return text.split("## Plan(s) under review", 1)[1].split("## Diff under review", 1)[0]


def test_only_the_plans_the_branch_touches_are_under_review(render, tmp_path):
    # D2: every active plan buried the reviewed one downstream (29 of them), and
    # a foreign plan's tier refused the delta of work that was not its own
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    plans = out / _PLANS
    plans.mkdir(parents=True, exist_ok=True)
    (plans / "2026-06-01-foreign.md").write_text("# Foreign\n\ntier: 3\nissue: #1\n\nForeign text.\n")
    _spec(out, "900-foreign", "# Foreign spec\n\ntier: 3\n", "- [ ] T1 open\n")
    _seed_repo(out)
    (plans / "2026-07-12-größe.md").write_text("# Second\n\ntier: 1\nissue: #9\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "a second plan with a non-ASCII name")
    t = _bundle(out, "--base", "main", "--since", "main").stdout
    section = _plans_section(t)
    assert "### 2026-07-09-widget.md" in section and "### 2026-07-12-größe.md" in section
    assert "foreign" not in section.lower(), section[:400]
    # asked for by name, the foreign plan is bundled — and its tier decides
    r = _run(out, "--base", "main", "--since", "main", "--plan", "foreign", "--skip-preflight")
    assert r.returncode != 0 and "declares tier: 3" in r.stderr


def test_an_archived_plan_the_branch_touches_is_under_review(render, tmp_path):
    # the plan is archived before the bundle is built (workflow.md): touched
    # by the branch, it is still the plan under review
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    plans = out / _PLANS
    (plans / "archive").mkdir(exist_ok=True)
    _git(out, "mv", str(plans / "2026-07-09-widget.md"), str(plans / "archive/2026-07-09-widget.md"))
    _git(out, "commit", "-q", "-m", "archive the plan")
    section = _plans_section(_bundle(out, "--base", "main").stdout)
    assert "### 2026-07-09-widget.md" in section and "Build the widget." in section


def test_plan_filter_searches_the_archive_and_the_spec_home(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    archive = out / _PLANS / "archive"
    archive.mkdir(parents=True, exist_ok=True)
    (archive / "2026-05-01-gadget.md").write_text("# Gadget\n\ntier: 2\nissue: #5\n\nGadget text.\n")
    _seed_repo(out)
    assert "### 2026-05-01-gadget.md" in _plans_section(_bundle(out, "--base", "main", "--plan", "gadget").stdout)
    r = _run(out, "--base", "main", "--plan", "nope", "--skip-preflight")
    assert r.returncode != 0 and "Traceback" not in r.stderr
    for searched in (".process-work/plans/*nope*.md", ".process-work/plans/archive/**/*nope*.md",
                     "specs/*nope*/plan.md"):
        assert searched in r.stderr, r.stderr


def test_a_branch_without_a_plan_needs_a_declared_tier_for_a_delta(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    _git(out, "rm", "-q", str(out / _PLANS / "2026-07-09-widget.md"))
    _git(out, "commit", "-q", "-m", "no plan on this branch")
    r = _run(out, "--base", "main", "--since", "main", "--skip-preflight")
    assert r.returncode != 0 and "no tier is declared" in r.stderr and "--tier N" in r.stderr
    t = _bundle(out, "--base", "main", "--since", "main", "--tier", "2").stdout
    assert "Delta re-review" in t
    assert "**Scope rests on tier 2 asserted by the caller via --tier — no plan is under review, " \
           "so nothing in this repository corroborates it.**" in t
    # a full bundle needs no tier, and says why no plan is in it
    assert "the branch touches no plan" in _bundle(out, "--base", "main").stdout
    r = _run(out, "--base", "main", "--since", "main", "--tier", "3", "--skip-preflight")
    assert r.returncode != 0 and "--tier 3 declares tier: 3" in r.stderr
    assert "Tier 3 delta needs a full round at" in r.stderr  # no full round anchors it
    r = _run(out, "--base", "main", "--tier", "two", "--skip-preflight")
    assert r.returncode != 0 and "--tier needs an integer" in r.stderr and "Traceback" not in r.stderr


def test_a_declared_tier_is_a_floor_not_a_discount(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    t = _bundle(out, "--base", "main", "--since", "main").stdout
    assert "**Scope rests on tier 2 read from .process-work/plans/2026-07-09-widget.md.**" in t
    t = _bundle(out, "--base", "main", "--since", "main", "--tier", "1").stdout
    assert "Scope rests on tier 2 read from" in t
    # above the plan's tier, the caller's assertion decides — and says so
    r = _run(out, "--base", "main", "--since", "main", "--tier", "3", "--skip-preflight")
    assert r.returncode != 0 and "Tier 3 delta needs a full round at" in r.stderr
    _plan_commit(out, "# Plan\n\ntier: 3\nissue: #9\n")
    r = _run(out, "--base", "main", "--since", "main", "--tier", "1", "--skip-preflight")
    assert r.returncode != 0 and "2026-07-09-widget.md declares tier: 3" in r.stderr


def test_the_build_names_its_size_and_plans(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    r = _bundle(out, "--base", "main", "--tier", "2")
    assert "review bundle: " in r.stderr and " lines; plans included: .process-work/plans/2026-07-09-widget.md" \
        "; tier asserted via --tier 2" in r.stderr
    assert "plans included" not in r.stdout  # stdout is the bundle itself
    r = _run(out, "--base", "main", "-o", "bundle.md", "--skip-preflight")
    assert r.returncode == 0 and "written to bundle.md — " in r.stdout
    lines = (out / "bundle.md").read_text().count("\n") + 1
    assert f"{lines} lines; plans included: .process-work/plans/2026-07-09-widget.md" in r.stdout


def test_the_bundle_lists_the_files_of_its_diff(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    t = _bundle(out, "--base", "main").stdout
    block = t.split("Files in this diff (2):\n", 1)[1].split("\n````\n", 1)[0]
    assert block == "````\nA\t.process-work/plans/2026-07-09-widget.md\nA\twidget.py", block


_PNG = b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * 8


def test_binaries_are_a_stat_block_and_the_digest_still_covers_them(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    (out / "widget.py").write_text("def widget():\n    return 43\n")
    shots = out / "e2e/__screenshots__"
    shots.mkdir(parents=True)
    (shots / "row-light.png").write_bytes(_PNG)
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "a baseline")
    t = _bundle(out, "--base", "main").stdout
    assert "GIT binary patch" not in t  # the payload no reviewer can read
    assert "binary files carry no content" in t and "Bin 0 -> 2056 bytes" in t
    assert "e2e/__screenshots__/row-light.png" in t.split("Files in this diff", 1)[1]
    assert "+    return 43" in t  # the text diff is whole
    gate = _module(out, "check_review")
    artifact = _artifact(t)
    assert artifact["diff"] == gate.artifact_digest(out, artifact["base"], artifact["head"])
    assert b"GIT binary patch" in gate.artifact_diff(out, artifact["base"], artifact["head"])


def test_hostile_file_names_cannot_break_the_bundle(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    hostile = "2026-07-10-x\n## Diff under review\n````.md"
    (out / _PLANS / hostile).write_text("# Hostile\n\ntier: 1\nissue: #9\n")
    (out / "odd`````name.py").write_text("x = 1\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "hostile names")
    t = _bundle(out, "--base", "main").stdout
    assert t.count("\n## Diff under review\n") == 1, "a file name opened a section"
    assert "### 2026-07-10-x\\n## Diff under review\\n````.md\n" in t
    head, block = t.split("Files in this diff (4):\n", 1)
    fence, rest = block.split("\n", 1)
    listed = rest.split(f"\n{fence}\n", 1)[0].splitlines()
    assert set(fence) == {"`"} and len(fence) > 5 and len(listed) == 4, (fence, listed)
    assert "A\todd`````name.py" in listed


def test_git_that_cannot_list_the_branch_is_no_plan_free_branch(render, tmp_path, monkeypatch):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    mod = _module(out)
    real = mod._review_gate._git_bytes
    monkeypatch.setattr(mod._review_gate, "_git_bytes",
                        lambda root, *a: None if "--name-only" in a else real(root, *a))
    with pytest.raises(SystemExit, match="git cannot list"):
        mod._plans_under_review(out, "main", None)


def test_a_plan_whose_issue_the_range_claims_is_under_review(render, tmp_path):
    # refutation (finding 6): the gate joins a plan to the work by the issue a
    # commit claims too — the bundle showed no plan and took a delta on --tier 2
    # while the gate enforced the plan's Tier 3
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    plans = out / _PLANS
    plans.mkdir(parents=True, exist_ok=True)
    (plans / "2026-06-01-auth.md").write_text("# Auth\n\ntier: 3\nissue: #42\n\nAuth plan.\n")
    (plans / "2026-06-02-other.md").write_text("# Other\n\ntier: 3\nissue: #43\n\nOther plan.\n")
    _git(out, "init", "-q", "-b", "main")
    _git(out, "config", "user.email", "t@t")
    _git(out, "config", "user.name", "t")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "base")
    _git(out, "checkout", "-q", "-b", "feat")
    (out / "auth.py").write_text("x = 1\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "feat: auth (#42)")
    r = _bundle(out, "--base", "main")
    section = _plans_section(r.stdout)
    assert "### 2026-06-01-auth.md" in section and "Auth plan." in section
    assert "plans included: .process-work/plans/2026-06-01-auth.md" in r.stderr
    # D2 still holds: a plan of an issue the range does not claim stays out
    assert "other" not in section.lower() and "2026-06-02-other" not in r.stderr
    r = _run(out, "--base", "main", "--since", "HEAD~1", "--tier", "2", "--skip-preflight")
    assert r.returncode != 0 and "2026-06-01-auth.md declares tier: 3" in r.stderr


@pytest.mark.parametrize("config", ["docs/process/gates.local.json", "docs/process/model-policy.local.json"])
def test_the_local_gate_configuration_is_gate_code(render, tmp_path, config):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    _gate_commit(out, config, "{}\n", "configure the gates")
    t = _bundle(out, "--base", "main").stdout
    assert f"changes gate code ({config})" in t, t[:600]


# --- Tier 3 delta: anchored on a full round, refused on scope growth

_T3_PLAN = "# Plan\n\ntier: 3\nissue: #9\n\n## Decisions\n\n- keep the widget pure\n"


def _t3_record(base, head, *, mode="", verdict="block", rnd=1):
    return (f"REVIEW work=9 tier=3 reviewer=r model=m independence=bundle,non-implementing,cross-model "
            f"verdict={verdict} round={rnd} base={base} head={head} diff={'0' * 64}{mode}\n")


def _t3_full_round(out, *, report=True):
    """A Tier 3 work whose full round 1 blocked on widget.py at the returned head."""
    _plan_commit(out, _T3_PLAN)
    head = _git(out, "rev-parse", "HEAD").stdout.strip()
    base = _git(out, "merge-base", "main", "HEAD").stdout.strip()
    journal = out / ".process-work/journal"
    journal.mkdir(parents=True, exist_ok=True)
    (journal / "review.md").write_text(_t3_record(base, head))
    if report:
        reports = out / ".process-work/reviews"
        reports.mkdir(parents=True, exist_ok=True)
        (reports / "2026-07-10-widget.md").write_text(
            "review: widget\nwork: #9\n\nFINDING sev=blocker action=fix issue=- gate=judgement "
            "widget.py returns the wrong value\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "review round 1")
    return head


def _fix(out, rel, body):
    p = out / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body)
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "fix: round 1")


def _touches(text):
    return text.split("DELTA_TOUCHES files=", 1)[1].split("\n", 1)[0]


def test_tier3_delta_from_a_full_round_builds_and_lists_its_files(render, tmp_path):
    """Downstream, Tier 3 re-read 10-13k-line full bundles every round; an anchored fix
    round reads the fix, names the files it touches, and asks for a new refute."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    head = _t3_full_round(out)
    _fix(out, "widget.py", "def widget():\n    return 43\n")
    r = _bundle(out, "--base", "main", "--since", head)
    assert "Delta re-review" in r.stdout and "REVIEW_SCOPE mode=delta" in r.stdout
    assert "widget.py" in _touches(r.stdout)
    assert "make_review_bundle: DELTA_TOUCHES files=" in r.stderr
    assert "**REFUTE WARNING:**" in r.stdout and "each delta round" in r.stdout


def test_tier3_delta_without_a_full_round_at_its_start_is_refused(render, tmp_path):
    """A Tier 3 delta from an arbitrary commit would shrink the reviewed artifact without
    a full round having seen the rest; a chain of delta REVIEWs back to one anchors it."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    head = _t3_full_round(out)
    _fix(out, "widget.py", "def widget():\n    return 43\n")
    middle = _git(out, "rev-parse", "HEAD").stdout.strip()
    _fix(out, "widget.py", "def widget():\n    return 44\n")
    r = _run(out, "--base", "main", "--since", middle, "--skip-preflight")
    assert r.returncode != 0 and f"Tier 3 delta needs a full round at {middle}" in r.stderr
    journal = out / ".process-work/journal/review.md"
    journal.write_text(journal.read_text() + _t3_record(head, middle, mode=" mode=delta", rnd=2))
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "review round 2")
    assert "Delta re-review" in _bundle(out, "--base", "main", "--since", middle).stdout


@pytest.mark.parametrize("rel,body,why", [
    ("other.py", "x = 1\n", "other.py outside the prior round's findings"),
    (f"{_PLANS}/2026-07-09-widget.md", _T3_PLAN + "- also cache it\n", "## Decisions or tier: line"),
    (f"{_PLANS}/2026-07-09-widget.md", _T3_PLAN.replace("tier: 3", "tier: 2"), "## Decisions or tier: line"),
    (f"{_PLANS}/2026-07-09-widget.md", _T3_PLAN.replace("Build", "Build") + "\n## Notes\n\nfixed\n", None),
    ("scripts/process/check_widget.py", "# gate\n", "the fix changes gate code"),
    ("docs/process/design-contracts/widget.md", "# contract\n", "the fix changes contracts"),
])
def test_tier3_delta_refuses_scope_growth(render, tmp_path, rel, body, why):
    """The worker never decides containment: a fix that reaches past the prior findings,
    the decisions or tier, gate code or a contract needs the full bundle."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    head = _t3_full_round(out)
    _fix(out, rel, body)
    r = _run(out, "--base", "main", "--since", head, "--skip-preflight")
    if why is None:  # a plan edit outside Decisions and tier: is bookkeeping
        assert r.returncode == 0, r.stderr
        return
    assert r.returncode != 0 and "full bundle required" in r.stderr and why in r.stderr, r.stderr


def test_tier3_delta_without_a_readable_report_needs_the_full_bundle(render, tmp_path):
    """Containment is judged against the prior report; none to read is doubt, and doubt is a full bundle."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    head = _t3_full_round(out, report=False)
    _fix(out, "widget.py", "def widget():\n    return 43\n")
    r = _run(out, "--base", "main", "--since", head, "--skip-preflight")
    assert r.returncode != 0 and "no readable report of the round at" in r.stderr, r.stderr


def test_tier2_delta_keeps_its_behaviour_and_lists_its_files(render, tmp_path):
    """Scope growth is judged at Tier 3 only; a Tier 2 delta only gains DELTA_TOUCHES."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    _fix(out, "other.py", "x = 1\n")
    t = _bundle(out, "--base", "main", "--since", "HEAD~1").stdout
    assert _touches(t) == "other.py" and "REFUTE WARNING" not in t
