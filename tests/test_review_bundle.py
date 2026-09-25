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
    assert (
        "REVIEW independence=… model=… reviewer=… "
        "round=… tier=… verdict=… work=…"
    ) in t
    assert "attest.py" in t  # the digest is computed by the writer, never typed
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
    # a filter matching nothing says so instead of silently bundling all
    r2 = _run(out, "--base", "main", "--plan", "nope")
    assert "no active plan matches" in r2.stdout


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
    # one formula: the gate's canonical three-dot diff (`since` is an
    # ancestor of HEAD, so it carries exactly the delta)
    import importlib.util
    spec = importlib.util.spec_from_file_location("check_review", out / "scripts/process/check_review.py")
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    assert artifact["base"] == previous
    assert artifact["diff"] == gate.artifact_digest(out, previous, "HEAD")
    findings = text.split("## Findings from the previous round", 1)[1].split("## Diff under review", 1)[0]
    assert "FINDING prior finding" in findings
    assert "stranger" not in findings  # the reports are in the diff, not in the findings
    assert "REVIEW_SCOPE mode=delta" in text
    assert "Full branch surface:" in text


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
    assert "Tier 3 reviews require a full diff" in (r.stdout + r.stderr)


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


def test_product_code_needs_no_refute(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    assert "REFUTE WARNING" not in _run(out, "--base", "main").stdout


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
        assert "REFUTE WARNING" not in _run(out, "--base", "main").stdout, line


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
    assert "REFUTE WARNING" not in _run(out, "--base", "main").stdout
    _gate_commit(out, "scripts/process/g.py", "x = 2\n", "fix round")
    r = _run(out, "--base", "main", "--since", reviewed)
    assert r.returncode == 0, r.stderr
    assert "**REFUTE WARNING:** this delta changes gate code" in r.stdout and "REFUTE WARNING" in r.stderr
    plan.write_text(plan.read_text() + "REFUTE work=9 round=2: 6 scenarios, 0 findings\n")
    _git(out, "commit", "-q", "-am", "docs: refute of the fix")
    assert "REFUTE WARNING" not in _run(out, "--base", "main", "--since", reviewed).stdout
    # a delta without gate code needs none
    (out / "widget.py").write_text("def widget():\n    return 43\n")
    _git(out, "commit", "-q", "-am", "product fix")
    head = _git(out, "rev-parse", "HEAD~1").stdout.strip()
    assert "REFUTE WARNING" not in _run(out, "--base", "main", "--since", head).stdout


def test_a_comment_across_two_fences_does_not_hide_a_real_line(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    _gate_commit(out, "scripts/process/g.py")
    plan = out / ".process-work/plans/2026-07-09-widget.md"
    plan.write_text(plan.read_text() + "\n```\n<!--\n```\n\nREFUTE work=9 round=1: 4 scenarios, 0 findings\n"
                    "\n```\n-->\n```\n")
    _git(out, "commit", "-q", "-am", "plan")
    assert "REFUTE WARNING" not in _run(out, "--base", "main").stdout


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
    assert "REFUTE WARNING" not in _run(out, "--base", "main", "--since", reviewed).stdout


def test_a_delta_without_a_base_still_checks_refute(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _seed_repo(out)
    reviewed = _git(out, "rev-parse", "HEAD").stdout.strip()
    _gate_commit(out, "scripts/process/g.py", "x = 2\n", "fix round")
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
