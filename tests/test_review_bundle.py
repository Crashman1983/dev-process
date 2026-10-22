import importlib.util
import json
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
        r"head=(?P<head>[0-9a-f]{40,64})$",
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


def test_a_bundle_under_process_work_is_ignored_and_one_elsewhere_in_the_tree_is_named(render, tmp_path):
    """Downstream: a bundle written into the tree was an untracked file — finish.py
    reported the tree dirty and the review gate read its tier: line as an unhomed plan."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    gate = [sys.executable, str(out / "scripts/process/check_review.py"), "."]
    rel = ".process-work/reviews/w/r1.bundle.md"
    r = _run(out, "--base", "main", "-o", rel, "--skip-preflight")
    assert r.returncode == 0 and (out / rel).is_file(), r.stderr
    assert "untracked in the worktree" not in r.stderr
    assert _git(out, "status", "--porcelain").stdout == ""
    assert "r1.bundle.md" not in subprocess.run(gate, cwd=out, capture_output=True, text=True).stdout
    r = _run(out, "--base", "main", "-o", "bundle.md", "--skip-preflight")
    assert r.returncode == 0
    assert "bundle.md is untracked in the worktree" in r.stderr and ".process-work/reviews/" in r.stderr
    assert "bundle.md" in subprocess.run(gate, cwd=out, capture_output=True, text=True).stdout


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


def test_the_artifact_names_the_fork_point_and_the_head(render, tmp_path):
    """v2.53: two SHAs name the reviewed change; the digest is gone."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    first = _artifact(_run(out, "--base", "main").stdout)
    assert first == {"base": _git(out, "merge-base", "main", "HEAD").stdout.strip(),
                     "head": _git(out, "rev-parse", "HEAD").stdout.strip()}
    (out / "widget.py").write_text("def widget():\n    return 43\n")
    _git(out, "add", "widget.py", check=True)
    _git(out, "commit", "-q", "-m", "fix: change widget", check=True)
    second = _artifact(_run(out, "--base", "main").stdout)
    assert second["base"] == first["base"] and second["head"] != first["head"]


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


def test_bundle_refuses_an_ambiguous_fork_point(render, tmp_path):
    """A criss-cross has two merge bases; the bundle must not pick one silently."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    feature = _git(out, "rev-parse", "HEAD").stdout.strip()
    _git(out, "checkout", "-q", "main")
    (out / "main.md").write_text("b1\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "main moves")
    main_tip = _git(out, "rev-parse", "HEAD").stdout.strip()
    _git(out, "merge", "-q", "--no-ff", "-m", "main takes feat", feature)
    _git(out, "checkout", "-q", "feat")
    _git(out, "merge", "-q", "--no-ff", "-m", "feat takes main", main_tip)
    r = _run(out, "--skip-preflight", "--base", "main")
    assert r.returncode != 0
    assert "merge bases" in r.stderr and "REVIEW_ARTIFACT" not in r.stdout, r.stderr


def test_empty_diff_stated(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _git(out, "init", "-q", "-b", "main")
    _git(out, "config", "user.email", "t@t")
    _git(out, "config", "user.name", "t")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "base")
    r = _run(out, "--base", "main")
    assert "HEAD adds nothing over main" in r.stdout


def test_a_full_bundle_against_a_slice_base_is_refused(render, tmp_path):
    """#160: --base HEAD^ bound a full round to a slice of the branch."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    (out / "widget.py").write_text("def widget():\n    return 43\n")
    _git(out, "commit", "-qam", "fix: widget")
    r = _run(out, "--skip-preflight", "--base", "HEAD^")
    assert r.returncode != 0 and "REVIEW_ARTIFACT" not in r.stdout
    assert "is not the fork point" in r.stderr, r.stderr
    r = _run(out, "--skip-preflight", "--base", "main")
    assert r.returncode == 0, r.stderr
    assert _artifact(r.stdout)["base"] == _git(out, "merge-base", "main", "HEAD").stdout.strip()


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
    # the optional kind (what sort of defect; `rounds` counts blockers by it)
    kind_line = "[kind=<" + "|".join(sorted(gate.FINDING_KINDS, key="knowledge-gap requirement implementation test-gap process environment".split().index)) + ">]"
    assert kind_line in bundle_src, kind_line
    assert "kind" in gate.FINDING_KEYS
    # the optional reviewer family (#247): a merged pass keeps each finding's origin
    assert "[by=<" in bundle_src and "by" in gate.FINDING_KEYS
    # what could have caught it (#276)
    cls_line = "[class=<" + "|".join(sorted(gate.FINDING_CLASSES, key="mechanical testable judgment".split().index)) + ">]"
    assert cls_line in bundle_src and "[rule=<check-name>]" in bundle_src, cls_line
    assert {"class", "rule"} <= set(gate.FINDING_KEYS)


def test_bundle_asks_for_kind_and_a_plan_bundle_for_the_phase_header(render, tmp_path):
    """The reviewer sees `kind=` in the FINDING format; only a `--plan-review` bundle asks for
    the `phase: plan` header line that `rounds` uses to count plan reviews apart — `--plan`
    alone also names the plans of a code review, which must not count as a plan review."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    code = _bundle(out, "--base", "main").stdout
    assert "[kind=<knowledge-gap|requirement|implementation|test-gap|process|environment>]" in code
    assert "knowledge-gap` = the author did not know something that already existed" in " ".join(code.split())
    assert "phase: plan" not in code
    named = _bundle(out, "--base", "main", "--plan", "widget").stdout
    assert "kind=<knowledge-gap" in named and "phase: plan" not in named
    plan = _bundle(out, "--base", "main", "--plan", "widget", "--plan-review").stdout
    assert "put the header line `phase: plan`" in plan
    # #225: a code review traces each criterion to the test that goes red; a plan review has none
    asked = "One line per acceptance criterion the plan names"
    assert asked in code and asked not in plan


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
    _git(out, "add", "-A", check=True)  # the report lands before the fix (the gate's rule)
    _git(out, "commit", "-q", "-m", "review round 1", check=True)
    (out / "widget.py").write_text("def widget():\n    return 43\n")
    _git(out, "add", "-A", check=True)
    _git(out, "commit", "-q", "-m", "fix: widget", check=True)
    text = _run(out, "--base", "main", "--since", previous).stdout
    artifact = _artifact(text)
    # v2.53: the delta is what the reviewer reads; the verdict binds the whole branch
    assert artifact["base"] == _git(out, "merge-base", "main", "HEAD").stdout.strip()
    assert artifact["head"] == _git(out, "rev-parse", "HEAD").stdout.strip()
    shown = text.split("## Diff under review", 1)[1]
    assert "+    return 43" in shown and "+    return 42" not in shown  # the fix, not round 1's code
    findings = text.split("## Findings from the previous round", 1)[1].split("## Diff under review", 1)[0]
    assert "FINDING prior finding" in findings
    assert "stranger" not in findings  # the reports are in the diff, not in the findings
    assert "REVIEW_SCOPE" not in text and "binds the whole branch" in text
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


def test_a_project_row_of_several_facts_warns_like_attest_enforces(render, tmp_path):
    """Refute of #282: the bundle read only one-fact refute rows; a project row naming
    tier and gate code together owed a refute attest enforced and the bundle never named."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    (out / "docs/process/model-policy.local.json").write_text(json.dumps({"review_evidence": {
        "required_records_extra": [{"kind": "refute", "when": {"tier_from": 2, "gate_code": False}}]}}))
    _seed_repo(out)
    t = _bundle(out, "--base", "main").stdout
    assert "**REFUTE WARNING:** 2026-07-09-widget.md (tier: 2) carries no" in t, t[:2000]


def test_the_bundle_reads_the_table_where_attest_does(render, tmp_path):
    """Cross-model review: the bundle read the required-records table at main's tip, attest
    at the fork point; a row main added after the fork is no duty of this review."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    _git(out, "checkout", "-q", "main")
    (out / "docs/process/model-policy.local.json").write_text(json.dumps({"review_evidence": {
        "required_records_extra": [{"kind": "refute", "when": {"tier_from": 2, "gate_code": False}}]}}))
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "policy after the fork")
    _git(out, "checkout", "-q", "feat")
    t = _bundle(out, "--base", "main").stdout
    assert "2026-07-09-widget.md (tier: 2) carries no" not in t, t[:1500]


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
    # v2.53: a delta needs no declared tier — it is a reading aid, not a review kind
    r = _run(out, "--base", "nosuchbase", "--since", reviewed)
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
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "review round 1")
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
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "reports")  # only committed reports count
    t = _bundle(out, "--base", "main", "--since", "HEAD").stdout
    assert "stranger" not in _findings(t) and "no review report for this work item" in t
    # issues are tried first: a report of #9 beats a newer one named after the slug
    (reports / "2026-07-12-a.md").write_text("review: a\nwork: #9\n\nFINDING by issue\n")
    (reports / "2026-07-13-widget-notes.md").write_text("FINDING by name\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "more reports")
    assert "FINDING by issue" in _findings(_bundle(out, "--base", "main", "--since", "HEAD").stdout)


def test_another_repositorys_issue_is_not_this_repos(render, tmp_path):
    # R2
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    reports = out / ".process-work/reviews"
    reports.mkdir(parents=True)
    (reports / "2026-07-10-r.md").write_text("review: r\nwork: other/repo#9\n\nFINDING stranger's finding\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "report")
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
    # asked for by name, the foreign plan is bundled (its tier refuses no delta since v2.53)
    r = _run(out, "--base", "main", "--since", "main", "--plan", "foreign", "--skip-preflight")
    assert r.returncode == 0 and "### 2026-06-01-foreign.md" in _plans_section(r.stdout), r.stderr


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


def test_binaries_are_a_stat_block(render, tmp_path):
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


def test_an_empty_delta_still_shows_the_branch_it_vouches_for(render, tmp_path):
    """Refutation of v2.53: `--since HEAD` showed no code at all, and the bundle still
    named the whole branch for the verdict. The branch surface is always shown; a
    `--since` that names no commit says so."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    t = _bundle(out, "--base", "main", "--since", "HEAD").stdout
    assert "Full branch surface:" in t and "widget.py" in t.split("Full branch surface:", 1)[1]
    assert "nothing was committed since `HEAD`" in t and "HEAD adds nothing over" not in t
    r = _run(out, "--base", "main", "--since", "no-such-ref", "--skip-preflight")
    assert r.returncode != 0 and "--since no-such-ref names no commit" in r.stderr, r.stderr


def test_tier3_delta_from_a_full_round_builds_and_lists_its_files(render, tmp_path):
    """Downstream, Tier 3 re-read 10-13k-line full bundles every round; a fix round
    reads the fix and names the files it touches. A fix outside gate code asks no new
    refute: regression tests and the delta review (a refute after every fix round
    turned each Tier 3 round into two). The verdict binds the whole branch."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    head = _t3_full_round(out)
    _fix(out, "widget.py", "def widget():\n    return 43\n")
    r = _bundle(out, "--base", "main", "--since", head)
    assert "Delta re-review" in r.stdout and "REVIEW_SCOPE" not in r.stdout
    assert _artifact(r.stdout)["base"] == _git(out, "merge-base", "main", "HEAD").stdout.strip()
    assert "widget.py" in _touches(r.stdout)
    assert "make_review_bundle: DELTA_TOUCHES files=" in r.stderr
    assert "REFUTE WARNING" not in r.stdout, r.stdout


def test_tier2_delta_keeps_its_behaviour_and_lists_its_files(render, tmp_path):
    """Scope growth is judged at Tier 3 only; a Tier 2 delta only gains DELTA_TOUCHES."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    _fix(out, "other.py", "x = 1\n")
    t = _bundle(out, "--base", "main", "--since", "HEAD~1").stdout
    assert _touches(t) == "other.py" and "REFUTE WARNING" not in t


def _t3_round_of(out, work):
    """A Tier 3 full round 1 attested as `work=<work>` (the plan is `widget`, issue #9),
    its report headed `work: #9`, and a fix of widget.py after it; returns the round's head."""
    _plan_commit(out, _T3_PLAN)
    head = _git(out, "rev-parse", "HEAD").stdout.strip()
    base = _git(out, "merge-base", "main", "HEAD").stdout.strip()
    journal = out / ".process-work/journal"
    journal.mkdir(parents=True, exist_ok=True)
    (journal / "review.md").write_text(_t3_record(base, head).replace("work=9", f"work={work}"))
    (out / ".process-work/reviews").mkdir(parents=True, exist_ok=True)
    (out / ".process-work/reviews/2026-07-10-round-1.md").write_text(
        "work: #9\n\nFINDING sev=blocker action=fix issue=- gate=judgement widget.py is wrong\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "review round 1")
    _fix(out, "widget.py", "def widget():\n    return 43\n")
    return head


def test_plan_report_keys_read_decorated_issue_tokens_but_not_spec_md(render, tmp_path):
    """`issue: **#9**,` and `[#9](url)` name #9 (one normaliser with report
    headers); spec.md's issue is NOT a bundle key — adding it changed which
    prior report the Tier-3 anchor picks (refute round 3)."""
    out = render(tmp_path, {"project_name": "d", "modules": {"speckit": True}})
    d = out / "specs/001-x"
    d.mkdir(parents=True)
    (d / "plan.md").write_text("# Plan\n\ntier: 2\n")
    (d / "spec.md").write_text("# Spec\n\nissue: #9\n")
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(out / "scripts/process"))
    try:
        spec = importlib.util.spec_from_file_location("bundle_keys", out / "scripts/process/make_review_bundle.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        work = mod._bundled_work(out, None, {d / "plan.md": (d / "plan.md").read_text()})
        slugs, issues = mod._review_gate.expand_work(out, work)[1]
        assert slugs == ("001-x",) and issues == ()
        for token in ("**#9**,", "[#9](https://x/9)", "#9.", "<#9>"):
            _s, got = mod._review_gate.plan_report_keys(".process-work/plans/p.md", f"issue: {token}\n")
            assert got == ((None, 9),), token
    finally:
        sys.path.remove(str(out / "scripts/process"))


# --- advisory: a fix round's regression pin (testing.md) ---

def _fix_round(out: Path, files: dict[str, str], subject: str = "fix: widget") -> str:
    """The seeded branch, reviewed at its head, then a fix commit: the round's `since`."""
    _seed_repo(out)
    reviewed = _git(out, "rev-parse", "HEAD").stdout.strip()
    for rel, body in files.items():
        (out / rel).parent.mkdir(parents=True, exist_ok=True)
        (out / rel).write_text(body)
    _git(out, "add", "-A", check=True)
    _git(out, "commit", "-q", "-m", subject, check=True)
    return reviewed


PIN_NOTE = "regression pin missing for the fixed findings (testing.md)"


def test_a_code_only_fix_round_notes_the_missing_regression_pin(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    reviewed = _fix_round(out, {"widget.py": "def widget():\n    return 43\n",
                                "docs/widget.md": "fixed\n", "pyproject.toml": "[x]\n"})
    r = _run(out, "--base", "main", "--since", reviewed, "--skip-preflight")
    assert r.returncode == 0, r.stderr
    assert f"{PIN_NOTE}: 1 code file(s) changed, no test file" in r.stdout


@pytest.mark.parametrize("test_file", ["tests/test_widget.py", "src/widget.spec.ts",
                                       "pkg/__tests__/w.js", "conftest.py", "widget_test.go"])
def test_a_fix_round_with_a_test_carries_no_pin_note(render, tmp_path, test_file):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    reviewed = _fix_round(out, {"widget.py": "def widget():\n    return 43\n", test_file: "pin\n"})
    r = _run(out, "--base", "main", "--since", reviewed, "--skip-preflight")
    assert r.returncode == 0, r.stderr
    assert PIN_NOTE not in r.stdout


def test_a_delta_bundle_carries_the_fix_streak(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    reviewed = _fix_round(out, {"widget.py": "def widget():\n    return 43\n"})
    (out / "widget.py").write_text("def widget():\n    return 44\n")
    _git(out, "commit", "-q", "-am", "fix: widget again", check=True)
    r = _run(out, "--base", "main", "--since", reviewed, "--skip-preflight")
    assert r.returncode == 0, r.stderr
    assert "## Fix streak\nfix-streak: note: 2 fix commits on widget.py" in r.stdout


# --- advisory: a state-machine plan without a transitions table (design-template.md) ---

TRANSITIONS_NOTE = "transitions table likely missing"


def _plan_bundle(out: Path, body: str, local: str | None = None) -> str:
    _seed_repo(out)
    plan = out / ".process-work/plans/2026-07-09-widget.md"
    plan.write_text("# Plan\n\ntier: 2\nissue: #9\n\n" + body)
    if local is not None:
        (out / "docs/process/review.local.md").write_text(local)
    _git(out, "add", "-A", check=True)
    _git(out, "commit", "-q", "-m", "plan", check=True)
    r = _run(out, "--base", "main", "--skip-preflight")
    assert r.returncode == 0, r.stderr
    return r.stdout


def test_a_plan_of_states_and_events_without_a_table_gets_the_note(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    text = _plan_bundle(out, "Each Event moves the order State; a stale grant must expire.\n")
    plans = text.split("## Plan(s) under review", 1)[1].split("## Diff under review", 1)[0]
    assert f"*(note: {TRANSITIONS_NOTE} — the plan speaks of state, event, expire" in plans


@pytest.mark.parametrize("body", [
    "Each event moves the state.\n\n## Transitions\n\n| State | Event | Result |\n",
    "Render the widget in blue.\n",
    "Rename the event handler.\n\n```\nstate transition replay\n```\n",  # fenced: a quotation
], ids=["with-table", "unrelated", "fenced"])
def test_no_transitions_note_with_a_table_or_without_the_vocabulary(render, tmp_path, body):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    assert TRANSITIONS_NOTE not in _plan_bundle(out, body)


def test_a_project_word_from_review_local_counts(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    body = "The saga emits an event per step.\n"
    assert TRANSITIONS_NOTE not in _plan_bundle(out, body)
    out2 = render(tmp_path / "local", {"project_name": "d", "modules": {}})
    text = _plan_bundle(out2, body, local="# Local\n\ntransitions-vocabulary: Saga, not a word!\n")
    assert f"{TRANSITIONS_NOTE} — the plan speaks of event, saga " in text


def _bundle_module(out: Path, name: str):
    """make_review_bundle loaded from the rendered tree, its siblings importable."""
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(out / "scripts/process"))
    spec = importlib.util.spec_from_file_location(name, out / "scripts/process/make_review_bundle.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_transitions_heading_has_one_owner(render, tmp_path):
    """v2.77 D1: the bundle's note and plan-structure read one rule for a `## Transitions`
    heading — the review gate's, never a copy in the bundle."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    try:
        mod = _bundle_module(out, "bundle_transitions")
        rule = mod._review_gate.TRANSITIONS_HEADING
        assert rule.search("x\n### Transitions (order)\n") and not rule.search("# Transitions\n")
        # up to three spaces in an ATX heading is still one; four is indented code
        assert rule.search("x\n   ## Transitions\n") and not rule.search("x\n    ## Transitions\n")
        assert not hasattr(mod, "_TRANSITIONS_HEADING")
        src = (out / "scripts/process/make_review_bundle.py").read_text()
        assert "_review_gate.TRANSITIONS_HEADING" in src and "Transitions\\b" not in src
    finally:
        sys.path.remove(str(out / "scripts/process"))


# --- v2.77 G1: the report names its round in its header --------------------------------

def _block(work: str, rnd: int) -> str:
    return (f"REVIEW work={work} tier=2 reviewer=r model=m independence=bundle,non-implementing "
            f"verdict=block round={rnd}\n")


def _round_note(text: str) -> str | None:
    m = re.search(r"Put the header line `round: (\d+)`", text)
    return m.group(1) if m else None


def test_the_bundle_asks_for_the_round_attest_will_write(render, tmp_path):
    """#293 AC-5: findings are counted per round only when the report says its round; the
    bundle computes it as attest numbers the REVIEW line (`attest.round_problems`)."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    text = _bundle(out, "--base", "main").stdout
    grammar = text.split("## Required output grammar", 1)[1]
    assert _round_note(grammar) == "1" and "header block" in grammar
    journal = out / ".process-work/journal"
    journal.mkdir(parents=True, exist_ok=True)
    # the slug and the issue are one work, and an uncommitted block counts, as in attest
    (journal / "2026-07-10.md").write_text(_block("widget", 1) + _block("9", 2))
    assert _round_note(_bundle(out, "--base", "main").stdout) == "3"
    # a plan review counts its `-plan` rounds apart
    plan = _bundle(out, "--base", "main", "--plan", "widget", "--plan-review").stdout
    assert _round_note(plan) == "1" and "put the header line `phase: plan`" in plan


def test_no_round_header_when_the_work_cannot_be_determined(render, tmp_path):
    """Without a plan there is no work to count; ids of the bundle that count differently
    (a plan review's ids count apart, literally) name no one round — the header is left out."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    _git(out, "rm", "-q", "-r", ".process-work/plans", check=True)
    _git(out, "commit", "-q", "-m", "no plan", check=True)
    text = _bundle(out, "--base", "main").stdout
    assert _round_note(text) is None and "round: <n>" not in text
    out2 = render(tmp_path / "split", {"project_name": "d", "modules": {}})
    _seed_repo(out2)
    journal = out2 / ".process-work/journal"
    journal.mkdir(parents=True, exist_ok=True)
    (journal / "2026-07-10.md").write_text(_block("9-plan", 1))  # widget-plan still counts 1
    assert _round_note(_bundle(out2, "--base", "main", "--plan", "widget", "--plan-review").stdout) is None


def _lines(n: int, word: str = "x") -> str:
    return "".join(f"{word}_{i} = {i}\n" for i in range(n))


FIX_PASS = "**FIX-PASS WARNING:**"


def test_a_large_fix_pass_is_warned_on_the_delta_the_bundle_shows(render, tmp_path):
    """#297 AC-3: downstream, a fix pass of ten or more findings was followed by a
    fix-induced blocker in 86 % of rounds. The warning counts the delta the bundle shows:
    tests, `.process-work/`, CHANGELOG and what a merge of main brings stay out."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    reviewed = _git(out, "rev-parse", "HEAD").stdout.strip()
    (out / "tests").mkdir(exist_ok=True)
    (out / "tests/test_widget.py").write_text(_lines(900, "t"))
    (out / ".process-work/journal").mkdir(parents=True, exist_ok=True)
    (out / ".process-work/journal/2026-07-10.md").write_text(_lines(400, "j"))
    (out / "CHANGELOG.md").write_text(_lines(400, "c"))
    (out / "widget.py").write_text(_lines(300, "w"))  # 300 added + 2 deleted: 302 lines
    _git(out, "add", "-A", check=True)
    _git(out, "commit", "-q", "-m", "fix: widget", check=True)
    # main moves on; merging it brings 1,000 lines the fix pass did not write
    _git(out, "checkout", "-q", "main", check=True)
    (out / "vendor.py").write_text(_lines(1000, "v"))
    _git(out, "add", "-A", check=True)
    _git(out, "commit", "-q", "-m", "feat: vendor", check=True)
    _git(out, "checkout", "-q", "feat", check=True)
    _git(out, "merge", "-q", "--no-ff", "-m", "merge main", "main", check=True)
    text = _bundle(out, "--base", "main", "--since", reviewed).stdout
    warning = next(ln for ln in text.splitlines() if ln.startswith(FIX_PASS))
    assert "302 lines" in warning and "sibling paths" in warning, warning
    r = _run(out, "--base", "main", "--since", reviewed, "--skip-preflight")
    assert "make_review_bundle: FIX-PASS WARNING:" in r.stderr


def test_a_small_fix_pass_or_a_first_round_gets_no_warning(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    reviewed = _git(out, "rev-parse", "HEAD").stdout.strip()
    (out / "widget.py").write_text(_lines(298, "w"))  # 298 + 2 = 300: at the limit, not above
    (out / "tests").mkdir(exist_ok=True)
    (out / "tests/test_widget.py").write_text(_lines(900, "t"))
    _git(out, "add", "-A", check=True)
    _git(out, "commit", "-q", "-m", "fix: widget", check=True)
    assert FIX_PASS not in _bundle(out, "--base", "main", "--since", reviewed).stdout
    (out / "widget.py").write_text(_lines(900, "w"))
    _git(out, "commit", "-q", "-am", "feat: more", check=True)
    assert FIX_PASS not in _bundle(out, "--base", "main").stdout  # a full round is no fix pass


def test_a_fix_pass_counts_a_move_once_and_leaves_lock_files_and_fragments_out(render, tmp_path):
    """Refute v2.77 F: a pure move is no change of twice its size, and what the SIZE WARNING
    leaves out (lock files) plus `changelog.d/` fragments are no production lines either."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    (out / "big.py").write_text(_lines(400, "b"))
    _git(out, "add", "-A", check=True)
    _git(out, "commit", "-q", "-m", "feat: big", check=True)
    reviewed = _git(out, "rev-parse", "HEAD").stdout.strip()
    _git(out, "mv", "big.py", "moved.py", check=True)
    (out / "uv.lock").write_text(_lines(2000, "u"))
    (out / "web").mkdir()
    (out / "web/package-lock.json").write_text(_lines(2000, "l"))
    (out / "changelog.d").mkdir()
    (out / "changelog.d/297.md").write_text(_lines(400, "c"))
    _git(out, "add", "-A", check=True)
    _git(out, "commit", "-q", "-m", "fix: move and lock", check=True)
    assert FIX_PASS not in _bundle(out, "--base", "main", "--since", reviewed).stdout
    # the count still sees what the pass writes into the product, beside a move
    (out / "extra.py").write_text(_lines(301, "e"))
    _git(out, "add", "-A", check=True)
    _git(out, "commit", "-q", "-m", "fix: extra", check=True)
    text = _bundle(out, "--base", "main", "--since", reviewed).stdout
    warning = next(ln for ln in text.splitlines() if ln.startswith(FIX_PASS))
    assert "301 lines" in warning, warning


def test_the_round_header_says_a_second_lens_writes_the_blocked_round(render, tmp_path):
    """Refute v2.77 G: a bundle cannot know it serves a second lens of a round that already
    blocked — it computes the next round, and the grammar says that lens writes its own."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    journal = out / ".process-work/journal"
    journal.mkdir(parents=True, exist_ok=True)
    (journal / "2026-07-10.md").write_text(_block("9", 1))
    text = _bundle(out, "--base", "main").stdout
    assert _round_note(text) == "2"
    flat = " ".join(text.split("## Required output grammar", 1)[1].split())
    assert ("A second lens of a round that already blocked writes that round in `round:`, "
            "as it passes `attest.py --round <that round>`") in flat


def test_a_measured_regression_scores_100_and_class_is_asked_of_blockers(render, tmp_path):
    """#297 AC-4 and #297 AC-6: the bundle tells the scorer a measured old/new difference
    is not its to lower, and the grammar makes `class=` mandatory for blockers and majors."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    flat = " ".join(_bundle(out, "--base", "main").stdout.split())
    assert "A measured old/new difference scores 100: the scorer may refute the measurement, " \
           "never lower the score." in flat
    assert "`class`: required on every `blocker` and `major`" in flat


def test_the_report_header_reads_the_round(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    try:
        gate = _bundle_module(out, "bundle_round_header")._review_gate
        head = gate.report_header("review: widget\nwork: #9\nround: 3\n\nround: 4\n")
        assert head["round"] == ["3"] and head["work"] == ["#9"]
        assert "round" not in gate.report_header("review: widget\n\nround: 2\n")
    finally:
        sys.path.remove(str(out / "scripts/process"))



def test_the_bundle_carries_the_anchors_of_the_touched_folders(render, tmp_path, tmp_path_factory):
    """#253: a reviewer without tools sees only the bundle; a monorepo keeps its stack
    rules in nested anchors — the touched folders' anchors ride along, others do not."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    (out / "backend").mkdir()
    (out / "backend/CLAUDE.md").write_text("# backend rules\nLayering is directed.\n")
    (out / "web").mkdir()
    (out / "web/AGENTS.md").write_text("# web rules\nTokens only.\n")
    _seed_repo(out)
    plain = _bundle(out, "--base", "main").stdout
    assert "Stack anchor" not in plain
    (out / "backend/app.py").write_text("X = 1\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "backend change")
    r = _bundle(out, "--base", "main").stdout
    assert "## Stack anchor `backend/CLAUDE.md`" in r and "Layering is directed." in r
    assert "web/AGENTS.md" not in r and "Tokens only." not in r
    # AGENTS.md is an anchor too; a link out of the repository is none (refute v2.75 r3)
    outside = tmp_path_factory.mktemp("outside") / "secret.md"
    outside.write_text("TOP-SECRET\n")
    (out / "lib").mkdir()
    (out / "lib/CLAUDE.md").symlink_to(outside)
    (out / "web/page.ts").write_text("x\n")
    (out / "lib/a.py").write_text("x\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "web and lib change")
    r = _bundle(out, "--base", "main").stdout
    assert "## Stack anchor `web/AGENTS.md`" in r and "Tokens only." in r
    assert "TOP-SECRET" not in r and "Stack anchor `lib/CLAUDE.md`" not in r


def test_plan_filter_by_issue_finds_a_plan_without_the_number_in_its_name(render, tmp_path):
    """#207 6c: `--plan 77` matched file names only; a plan declaring `issue: #77` under
    another name was reported as due and then refused."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    plans = out / ".process-work/plans"
    (plans / "2026-10-19-widget-polish.md").write_text("# Plan\n\nissue: #77\ntier: 2\n\n## Decisions\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "plan for #77")
    for flt in ("77", "#77"):
        r = _bundle(out, "--base", "main", "--plan", flt).stdout
        assert "2026-10-19-widget-polish.md" in r, flt
    r = _run(out, "--base", "main", "--plan", "78", "--skip-preflight")
    assert r.returncode != 0 and "matches no plan" in (r.stdout + r.stderr)
    # read as the gate reads work ids: a fenced example and an archived plan of the
    # reopened issue are not this issue's plans (refute v2.75 r3)
    (plans / "2026-10-01-template-docs.md").write_text("# Plan\n\nissue: #5\ntier: 3\n\n```\nissue: #77\n```\n")
    (plans / "archive").mkdir(exist_ok=True)
    (plans / "archive/2026-03-01-first-try.md").write_text("# Plan\n\nissue: #77\ntier: 3\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "other plans")
    r = _bundle(out, "--base", "main", "--plan", "77").stdout
    bundled = [ln for ln in r.splitlines() if ln.startswith("### ")]
    assert any("widget-polish" in ln for ln in bundled), bundled
    assert not any("template-docs" in ln or "first-try" in ln for ln in bundled), bundled


# --- #281: checklist sections scoped by the path classes a diff touches ----------

SECTION_MAP = {"classes": {"code": ["*.py", "scripts/**"], "ui": ["frontend/**"],
                           "records": [".process-work/**"]},
               "sections": {"Surfaces": ["ui"], "Security": ["code", "ui"]}}


def _seed_with_map(out: Path, data) -> None:
    (out / "docs/process/review-sections.local.json").write_text(json.dumps(data))
    _seed_repo(out)


def _checklist_part(text: str) -> str:
    return text.split("## What a review checks", 1)[1].split("## This project's review dimensions", 1)[0]


def test_a_section_no_touched_class_reaches_is_left_out_and_named(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_with_map(out, SECTION_MAP)
    part = _checklist_part(_run(out, "--skip-preflight", "--base", "main").stdout)
    assert "## Surfaces" not in part and "## Security" in part and "## Correctness" in part, part[:400]
    assert "omitted for this diff" in part and "Surfaces — the UI acceptance floor" in part


def test_a_path_no_class_knows_keeps_every_section(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_with_map(out, SECTION_MAP)
    (out / "notes.txt").write_text("x\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "notes")
    part = _checklist_part(_run(out, "--skip-preflight", "--base", "main").stdout)
    assert "## Surfaces" in part and "notes.txt is in no path class" in part, part[-400:]


def test_without_a_map_or_with_a_bad_one_every_section_stays(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    part = _checklist_part(_run(out, "--skip-preflight", "--base", "main").stdout)
    assert "## Surfaces" in part and "omitted" not in part
    out2 = render(tmp_path / "bad", {"project_name": "d", "modules": {}})
    _seed_with_map(out2, {"classes": {"code": ["*.py"]}, "sections": {"Surfaces": ["nope"]}})
    part = _checklist_part(_run(out2, "--skip-preflight", "--base", "main").stdout)
    assert "## Surfaces" in part and "every section kept" in part


def test_an_empty_path_list_keeps_every_section(render, tmp_path):
    """Refute of #281: an empty diff matched no class, so every mapped section was left out."""
    import importlib.util
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    sys.path.insert(0, str(out / "scripts/process"))
    try:
        spec = importlib.util.spec_from_file_location("bundle_scope", out / "scripts/process/make_review_bundle.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        sys.path.remove(str(out / "scripts/process"))
    text = "# Checklist\n\n## Surfaces\n\nui\n\n## Security\n\nsec\n"
    assert mod._scoped_checklist(text, [], SECTION_MAP) == (text, "")


def test_a_branch_cannot_scope_its_own_review(render, tmp_path):
    """The map is read at the base: a branch adding one leaves out nothing."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    (out / "docs/process/review-sections.local.json").write_text(json.dumps(SECTION_MAP))
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "map")
    part = _checklist_part(_run(out, "--skip-preflight", "--base", "main").stdout)
    assert "## Surfaces" in part and "omitted" not in part
