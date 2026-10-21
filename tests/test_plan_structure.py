"""plan-structure gate (core, #278): an active Tier 2+ plan's structure is read when
it is written — EARS criteria with one `shall`, a planned test per criterion once
execution starts, the project's required sections, registered story ids, and no
open task at the merge. Only plans the branch adds are bound."""
import json
import os
import subprocess
import sys

PLANS = ".process-work/plans"
GOOD = ("# Plan\n\ntier: 2\nissue: #7\n\n## Decisions\n\n"
        "- AC-1: When the user saves, the editor shall keep the cursor.\n"
        "- AC-1: `tests/test_editor.py::test_cursor_kept`\n")


def _run(root, *, merge=False):
    env = {k: v for k, v in os.environ.items() if k not in ("PROCESS_PUSH_TARGETS", "PRE_COMMIT_REMOTE_BRANCH")}
    if merge:
        env["PROCESS_PUSH_TARGETS"] = "refs/heads/main"
    return subprocess.run([sys.executable, str(root / "scripts/process/check_plan_structure.py"), "."],
                          cwd=root, capture_output=True, text=True, env=env)


def _repo(out, data=None):
    """main with the render (and the project data, read at main), a feature branch with
    one commit: the range plans are new in."""
    if data is not None:
        (out / "docs/process/plan-structure.local.json").write_text(json.dumps(data))
    _git(out, "init", "-q", "-b", "main")
    _git(out, "add", "-A")
    _git(out, "commit", "-qm", "base")
    _git(out, "checkout", "-qb", "feature")
    _git(out, "commit", "-q", "--allow-empty", "-m", "start")
    return out


def _plan(root, body, name="2026-10-21-7-editor.md"):
    p = root / PLANS / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


def _git(root, *args):
    subprocess.run(["git", "-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t",
                    "-c", "commit.gpgsign=false", *args], check=True, capture_output=True)


def test_clean_render_and_a_good_plan_pass(render, tmp_path):
    out = _repo(render(tmp_path, {"project_name": "demo"}))
    assert _run(out).returncode == 0
    _plan(out, GOOD)
    r = _run(out, merge=True)
    assert r.returncode == 0 and "plan-structure: OK" in r.stdout, r.stdout


def test_a_criterion_needs_exactly_one_shall(render, tmp_path):
    out = _repo(render(tmp_path, {"project_name": "demo"}))
    _plan(out, GOOD.replace("shall keep the cursor", "shall keep the cursor and shall scroll"))
    r = _run(out)
    assert r.returncode == 1 and ":8: AC-1 has 2 ×" in r.stdout, r.stdout
    _plan(out, GOOD.replace("shall keep", "keeps"))
    assert "AC-1 has 0 ×" in _run(out).stdout


def test_a_project_names_its_own_shall_words(render, tmp_path):
    out = _repo(render(tmp_path, {"project_name": "demo"}), {"shall_words": ["soll"]})
    _plan(out, GOOD.replace("the editor shall keep", "der Editor soll behalten"))
    assert _run(out).returncode == 0


def test_an_id_twice_as_a_criterion_fails(render, tmp_path):
    out = _repo(render(tmp_path, {"project_name": "demo"}))
    _plan(out, GOOD + "- AC-1: When the user quits, the editor shall save.\n")
    r = _run(out)
    assert r.returncode == 1 and "AC-1 is named twice" in r.stdout, r.stdout


def test_the_planned_test_is_owed_once_execution_starts(render, tmp_path):
    out = _repo(render(tmp_path, {"project_name": "demo"}))
    body = GOOD.replace("- AC-1: `tests/test_editor.py::test_cursor_kept`\n", "")
    _plan(out, body)
    assert _run(out).returncode == 0  # planning: not yet
    _plan(out, body + "\n- [x] T1 cursor\n")
    r = _run(out)
    assert r.returncode == 1 and "AC-1 names no planned test" in r.stdout, r.stdout
    for proof in ("- AC-1: struck — the editor is gone\n", "- AC-1: manual: checked on the device\n"):
        _plan(out, body + "\n- [x] T1 cursor\n" + proof)
        assert _run(out).returncode == 0, proof


def test_an_open_task_blocks_only_the_merge(render, tmp_path):
    out = _repo(render(tmp_path, {"project_name": "demo"}))
    _plan(out, GOOD + "\n- [ ] T2 docs\n")
    assert _run(out).returncode == 0
    r = _run(out, merge=True)
    assert r.returncode == 1 and "open task at the merge" in r.stdout, r.stdout
    for settled in ("- [ ] T2 docs — struck: done in T1\n", "- [ ] T2 docs — moved: #9\n"):
        _plan(out, GOOD + "\n" + settled)
        assert _run(out, merge=True).returncode == 0, settled


def test_a_required_section_is_project_data(render, tmp_path):
    out = _repo(render(tmp_path, {"project_name": "demo"}), {"sections": ["Anchor Delta"]})
    _plan(out, GOOD)
    r = _run(out)
    assert r.returncode == 1 and "no `## Anchor Delta` section" in r.stdout, r.stdout
    _plan(out, GOOD + "\n## Anchor Delta\n\nNone.\n")
    assert _run(out).returncode == 0


def test_a_story_must_be_in_the_registry(render, tmp_path):
    out = _repo(render(tmp_path, {"project_name": "demo"}),
                {"story_id": r"ED-US-\d+", "registry": "docs/registry/*.json"})
    (out / "docs/registry").mkdir(parents=True)
    (out / "docs/registry/editor.json").write_text('{"stories": [{"id": "ED-US-1"}]}')
    _plan(out, GOOD + "\nStories: ED-US-1, ED-US-2\n")
    r = _run(out)
    assert r.returncode == 1 and "story ED-US-2 is not in the registry" in r.stdout \
        and "ED-US-1 is not" not in r.stdout, r.stdout


def test_fenced_criteria_are_quotation(render, tmp_path):
    out = _repo(render(tmp_path, {"project_name": "demo"}))
    _plan(out, GOOD + "\n```\n- AC-2: When x, y shall a and shall b.\n```\n")
    assert _run(out).returncode == 0


def test_a_decision_on_an_assumption_is_a_note(render, tmp_path):
    out = _repo(render(tmp_path, {"project_name": "demo"}))
    _plan(out, GOOD + "- DECISION 2026-10-21 agent: cache it [assumption] reads are rare\n")
    r = _run(out)
    assert r.returncode == 0 and "rests on an `[assumption]`" in r.stdout, r.stdout


def test_a_plan_already_on_main_is_history(render, tmp_path):
    """Only plans this branch adds are bound: the gate is no retroactive duty."""
    out = render(tmp_path, {"project_name": "demo"})
    _plan(out, GOOD.replace("shall keep", "keeps"))
    _git(out, "init", "-q", "-b", "main")
    _git(out, "add", "-A")
    _git(out, "commit", "-qm", "base")
    _git(out, "checkout", "-qb", "feature")
    assert _run(out).returncode == 0  # on main's tip: no range, nothing new
    _plan(out, GOOD.replace("shall keep", "keeps"), name="2026-10-22-8-new.md")
    _git(out, "add", "-A")
    _git(out, "commit", "-qm", "new plan")
    r = _run(out)
    assert r.returncode == 1 and "8-new.md" in r.stdout and "7-editor" not in r.stdout, r.stdout


def test_gate_runner_registers_plan_structure_as_core(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    r = subprocess.run([sys.executable, str(out / "scripts/process/gate_runner.py"), "--list"],
                       cwd=out, capture_output=True, text=True)
    assert "plan-structure" in r.stdout.splitlines(), r.stdout


def test_a_branch_cannot_lift_its_own_duty(render, tmp_path):
    """The data is read at the integration ref: a branch that drops a required section
    from the file still owes it."""
    out = _repo(render(tmp_path, {"project_name": "demo"}), {"sections": ["Anchor Delta"]})
    (out / "docs/process/plan-structure.local.json").write_text(json.dumps({"sections": []}))
    _plan(out, GOOD)
    assert "no `## Anchor Delta` section" in _run(out).stdout


def test_project_data_that_is_no_json_fails(render, tmp_path):
    """M3: a broken data file is a problem, not "no project rules"."""
    out = render(tmp_path, {"project_name": "demo"})
    (out / "docs/process/plan-structure.local.json").write_text("{not json")
    _repo(out)
    _plan(out, GOOD)
    r = _run(out)
    assert r.returncode == 1 and "is not valid JSON" in r.stdout, r.stdout


def test_project_data_git_cannot_read_fails_closed(render, tmp_path):
    """Refute of #278: a failed `git show` read as "no data" and lifted every section."""
    out = _repo(render(tmp_path, {"project_name": "demo"}), {"sections": ["Anchor Delta"]})
    blob = subprocess.run(["git", "-C", str(out), "rev-parse", "main:docs/process/plan-structure.local.json"],
                          capture_output=True, text=True, check=True).stdout.strip()
    (out / ".git/objects" / blob[:2] / blob[2:]).unlink()
    _plan(out, GOOD)
    r = _run(out)
    assert r.returncode == 1 and "cannot be read" in r.stdout, r.stdout


def test_a_replaced_fork_point_does_not_unbind_a_plan(render, tmp_path):
    """Refute of #278: `git replace` of main with a commit holding the plan made it read
    as already merged; the gate reads git as every gate does (no replace objects)."""
    out = _repo(render(tmp_path, {"project_name": "demo"}))
    _plan(out, GOOD.replace("shall keep", "keeps"))
    _git(out, "add", "-A")
    _git(out, "commit", "-qm", "plan")
    fake = subprocess.run(["git", "-C", str(out), "rev-parse", "HEAD"], capture_output=True, text=True,
                          check=True).stdout.strip()
    _git(out, "replace", "main", fake)
    r = _run(out)
    assert r.returncode == 1 and "AC-1 has 0" in r.stdout, r.stdout


def test_a_tier_one_plan_is_not_bound_and_a_stub_raised_to_tier_two_is(render, tmp_path):
    """M4 and refute of #278: below Tier 2 the gate reads nothing; a Tier 1 stub on main
    rewritten to Tier 2 here is written here, so it is bound."""
    out = render(tmp_path, {"project_name": "demo"})
    _plan(out, GOOD.replace("tier: 2", "tier: 1").replace("shall keep", "keeps"))
    _repo(out)
    assert _run(out).returncode == 0
    _plan(out, GOOD.replace("shall keep", "keeps"))
    r = _run(out)
    assert r.returncode == 1 and "AC-1 has 0" in r.stdout, r.stdout


def test_a_finding_names_the_files_own_line_behind_a_fence(render, tmp_path):
    """Refute of #278: line numbers were counted over the text with fences removed."""
    out = _repo(render(tmp_path, {"project_name": "demo"}))
    fence = "```\nexample one\nexample two\n```\n"
    _plan(out, GOOD.replace("## Decisions\n\n", "## Decisions\n\n" + fence).replace("shall keep", "keeps"))
    r = _run(out)
    assert ":12: AC-1 has 0" in r.stdout, r.stdout


def test_every_list_marker_opens_a_task_for_every_reader(render, tmp_path):
    """Refute of #278: `* [ ]` was open for plan-structure and closed for the review gate;
    one grammar, owned by check_review."""
    out = _repo(render(tmp_path, {"project_name": "demo"}))
    _plan(out, GOOD + "\n* [ ] T2 docs\n")
    r = _run(out, merge=True)
    assert r.returncode == 1 and "open task at the merge" in r.stdout, r.stdout
    sys.path.insert(0, str(out / "scripts/process"))
    try:
        import importlib
        sys.modules.pop("check_review", None)
        cr = importlib.import_module("check_review")
        assert cr.UNCHECKED.search("* [ ] T2 docs\n")
    finally:
        sys.path.remove(str(out / "scripts/process"))
        sys.modules.pop("check_review", None)
