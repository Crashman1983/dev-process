"""plan-structure gate (core, #278): an active Tier 2+ plan's structure is read when
it is written — EARS criteria with one `shall`, a planned test per criterion once
execution starts, the project's required sections, registered story ids, and no
open task at the merge. Only plans the branch adds are bound."""
import json
import os
import shutil
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
    # cross-model review: the project's words add to `shall`, a bilingual plan is no false red
    _plan(out, GOOD + "- AC-2: When the user quits, the editor shall save.\n- AC-2: struck — later\n")
    assert _run(out).returncode == 0, _run(out).stdout


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
    _plan(out, body + "\n- [x] T1 cursor\n- AC-1: struck — the editor is gone\n")
    assert _run(out).returncode == 0
    # cross-model review: attest knows no `manual:` proof, so the plan gate offers none
    _plan(out, body + "\n- [x] T1 cursor\n- AC-1: manual: checked on the device\n")
    assert "AC-1 names no planned test" in _run(out).stdout


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


def test_a_registry_of_one_file_is_read(render, tmp_path):
    """Cross-model review: a `registry` without `*` walked a file as a folder and read no id."""
    out = _repo(render(tmp_path, {"project_name": "demo"}),
                {"story_id": r"ED-US-\d+", "registry": "docs/stories.json"})
    (out / "docs/stories.json").write_text('{"stories": [{"id": "ED-US-1"}]}')
    _plan(out, GOOD + "\nStories: ED-US-1\n")
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_a_plan_the_branch_archived_is_read_at_the_merge(render, tmp_path):
    """Cross-model review: /finish archives before the merge push, and only active plans
    were read — the open-task rule never fired on the normal route."""
    out = _repo(render(tmp_path, {"project_name": "demo"}))
    _plan(out, GOOD + "\n- [ ] T2 docs\n", name="archive/2026-10-21-7-editor.md")
    r = _run(out, merge=True)
    assert r.returncode == 1 and "archive/2026-10-21-7-editor.md" in r.stdout \
        and "open task at the merge" in r.stdout, r.stdout


def test_an_old_plan_finish_archives_stays_history(render, tmp_path):
    """Cross-model review, delta round: reading the archive bound an old plan as new once
    /finish moved it there — it is judged where it lived at the integration ref."""
    out = render(tmp_path, {"project_name": "demo"})
    _plan(out, GOOD.replace("shall keep", "keeps") + "\n- [ ] T2 docs\n")
    _repo(out)
    old = out / PLANS / "2026-10-21-7-editor.md"
    (out / PLANS / "archive").mkdir(parents=True, exist_ok=True)
    old.rename(out / PLANS / "archive" / old.name)
    r = _run(out, merge=True)
    assert r.returncode == 0, r.stdout


# --- #293 AC-1: a declared `## Transitions` section carries its table ---------------

TABLE = ("\n## Transitions\n\n"
         "| State | Event | Result | Test |\n"
         "|---|---|---|---|\n"
         "| draft | submit | in review | `tests/test_order.py::test_submit_starts_review` |\n"
         "| in review | approve | approved | `tests/test_order.py::test_decision_ends_review` |\n"
         "| in review | reject | draft | `tests/test_order.py::test_decision_ends_review` |\n"
         "| approved | submit | forbidden | struck — approval is final in this release |\n")
ROWS = TABLE.split("\n\n", 1)[1]  # the table alone


def test_a_valid_transitions_table_passes(render, tmp_path):
    """Rows of one equivalence class may name the same test; a struck row names its reason."""
    out = _repo(render(tmp_path, {"project_name": "demo"}))
    _plan(out, GOOD + TABLE + "\n- [x] T1 states\n")
    r = _run(out, merge=True)
    assert r.returncode == 0 and "plan-structure: OK" in r.stdout, r.stdout


def test_a_transitions_section_without_a_table_fails(render, tmp_path):
    out = _repo(render(tmp_path, {"project_name": "demo"}))
    _plan(out, GOOD + "\n## Transitions\n\nDraft goes to review on submit.\n\n## Next\n\n" + ROWS)
    r = _run(out)
    assert r.returncode == 1 and ":11: `## Transitions` has no table" in r.stdout, r.stdout


def test_a_transitions_table_without_a_test_column_fails(render, tmp_path):
    out = _repo(render(tmp_path, {"project_name": "demo"}))
    _plan(out, GOOD + "\n## Transitions\n\n| State | Event | Result |\n|---|---|---|\n| a | b | c |\n")
    r = _run(out)
    assert r.returncode == 1 and ":13: the transitions table has no `Test` column" in r.stdout, r.stdout
    _plan(out, GOOD + "\n## Transitions\n\n| State | Test |\n|---|---|\n| a | struck — later |\n")
    r = _run(out)
    assert r.returncode == 1 and ":13: the transitions table needs a `Test` column and at least two others" \
        in r.stdout, r.stdout


def test_a_transitions_row_with_an_empty_cell_fails(render, tmp_path):
    out = _repo(render(tmp_path, {"project_name": "demo"}))
    for row in ("| draft |  | review | struck — later |\n", "| draft | submit | … | struck — later |\n",
                "| draft | submit | review |\n"):
        _plan(out, GOOD + "\n## Transitions\n\n| State | Event | Result | Test |\n|---|---|---|---|\n" + row)
        r = _run(out)
        assert r.returncode == 1 and ":15: transitions row" in r.stdout, (row, r.stdout)


def test_the_test_cell_names_a_test_once_execution_starts(render, tmp_path):
    out = _repo(render(tmp_path, {"project_name": "demo"}))
    table = "\n## Transitions\n\n| State | Event | Result | Test |\n|---|---|---|---|\n| a | b | c | to do |\n"
    _plan(out, GOOD + table)
    assert _run(out).returncode == 0  # planning: the form only
    _plan(out, GOOD + table + "\n- [x] T1 states\n")
    r = _run(out)
    assert r.returncode == 1 and ":15: transitions row names no test" in r.stdout, r.stdout
    _plan(out, GOOD + table)
    assert "names no test" in _run(out, merge=True).stdout  # the merge push owes it too
    for placeholder in ("struck — <reason>", "struck — …", "struck"):
        _plan(out, GOOD + table.replace("to do", placeholder) + "\n- [x] T1 states\n")
        assert "names no test" in _run(out).stdout, placeholder


def test_a_deeper_transitions_heading_reads_its_own_section(render, tmp_path):
    """`### Transitions (…)` is the same rule; its section ends at the next heading of
    the same or a higher level, a deeper one stays inside."""
    out = _repo(render(tmp_path, {"project_name": "demo"}))
    _plan(out, GOOD + "\n### Transitions (order lifecycle)\n\n#### Rows\n\n" + ROWS + "\n### Next\n\nprose\n")
    r = _run(out)
    assert r.returncode == 0, r.stdout
    _plan(out, GOOD + "\n### Transitions (order lifecycle)\n\nprose\n\n## Next\n\n" + ROWS)
    assert "`### Transitions (order lifecycle)` has no table" in _run(out).stdout


def test_a_plan_without_transitions_and_a_fenced_table_are_untouched(render, tmp_path):
    out = _repo(render(tmp_path, {"project_name": "demo"}))
    _plan(out, GOOD + "\n```\n## Transitions\n\n| State | Event |\n|---|---|\n| a |  |\n```\n- [x] T1\n")
    r = _run(out)
    assert r.returncode == 0, r.stdout
    # a fenced table under a live heading is quotation: the section has none
    _plan(out, GOOD + "\n## Transitions\n\n```\n" + ROWS + "```\n")
    assert "`## Transitions` has no table" in _run(out).stdout


def test_the_copied_design_template_passes(render, tmp_path):
    """The template's example is what a plan copies: it must pass the gate it teaches,
    test cells included."""
    out = _repo(render(tmp_path, {"project_name": "demo"}))
    design = (out / "docs/process/design-template.md").read_text()
    section = "## Transitions" + design.split("## Transitions", 1)[1].split("\n## ", 1)[0]
    assert "| Test |" in section and "one test per row" in section
    assert "rows of one equivalence class may name the same test" in section
    _plan(out, GOOD + "\n" + section + "\n- [x] T1 states\n")
    r = _run(out, merge=True)
    assert r.returncode == 0, r.stdout
    # /plan asks for the section where state work is planned, with what goes beside it
    plan = " ".join((out / ".claude/commands/plan.md").read_text().split())
    for words in ("concurrency, a lifecycle, a state machine, a guard or a parser", "`## Transitions`",
                  "the invariant, its one owner", "every writer and reader of the state",
                  "rows of one equivalence class may name the same test"):
        assert words in plan, words


def _spec(root, body, tasks=None, name="001-orders"):
    d = root / "specs" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "plan.md").write_text(body, encoding="utf-8")
    if tasks is not None:
        (d / "tasks.md").write_text(tasks, encoding="utf-8")


SPEC_BAD = "# Plan\n\ntier: 2\nissue: #7\n\n## Transitions\n\n| State | Event | Result |\n|---|---|---|\n| a | b | c |\n"


def test_a_new_spec_kit_plan_is_bound_without_a_plan_folder(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    shutil.rmtree(out / PLANS)
    _repo(out)
    _spec(out, SPEC_BAD)
    r = _run(out)
    assert r.returncode == 1 and "specs/001-orders/plan.md:8: the transitions table has no `Test`" \
        in r.stdout, r.stdout
    # its ticks stand in tasks.md beside it
    good = SPEC_BAD.replace("| Result |\n|---|---|---|\n| a | b | c |",
                            "| Result | Test |\n|---|---|---|---|\n| a | b | c | to do |")
    _spec(out, good, tasks="- [ ] T1 states\n")
    assert _run(out).returncode == 0
    _spec(out, good, tasks="- [x] T1 states\n")
    assert "specs/001-orders/plan.md:10: transitions row names no test" in _run(out).stdout
    # below Tier 2 it is not bound; the plan folder's other rules stay off spec plans
    _spec(out, SPEC_BAD.replace("tier: 2", "tier: 1"))
    assert _run(out).returncode == 0
    _spec(out, "# Plan\n\ntier: 2\n\n- AC-1: When x, y keeps z.\n- [ ] T1 open\n")
    assert _run(out, merge=True).returncode == 0


def test_a_spec_kit_plan_at_the_ref_is_history(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    _spec(out, SPEC_BAD)
    _repo(out)
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_a_spec_kit_stub_raised_to_tier_two_is_bound(render, tmp_path):
    """The plan folder's rule holds for Spec Kit plans: below Tier 2 at the ref and
    raised here, the plan is the branch's to answer for."""
    out = render(tmp_path, {"project_name": "demo"})
    _spec(out, "# Plan\n\ntier: 1\n")
    _repo(out)
    _spec(out, SPEC_BAD)
    r = _run(out)
    assert r.returncode == 1 and "specs/001-orders/plan.md:8: the transitions table has no `Test`" \
        in r.stdout, r.stdout


def test_bundle_and_gate_read_one_transitions_heading(render, tmp_path):
    """One owner for the heading rule (check_review): the bundle's note and the gate
    agree on every heading form."""
    out = render(tmp_path, {"project_name": "demo"})
    names = ("check_review", "check_plan_structure", "make_review_bundle", "attest_evidence")
    sys.path.insert(0, str(out / "scripts/process"))
    try:
        import importlib
        for name in names:
            sys.modules.pop(name, None)
        cr = importlib.import_module("check_review")
        ps = importlib.import_module("check_plan_structure")
        mb = importlib.import_module("make_review_bundle")
        assert ps.TRANSITIONS_HEADING is cr.TRANSITIONS_HEADING
        words = "the state changes on each event"
        for heading in ("## Transitions", "### Transitions (lifecycle)", "#### Transitions",
                        "# Transitions", "## Transition table", "##Transitions", "## Transitions:",
                        "   ## Transitions", "    ## Transitions"):
            text = f"{words}\n\n{heading}\n\nprose\n"
            owned = bool(cr.TRANSITIONS_HEADING.search(text))
            assert (mb._transitions_note(text, mb.TRANSITION_VOCABULARY) is None) is owned, heading
            assert bool(ps.transitions_findings("p.md", text, need_tests=False)) is owned, heading
    finally:
        sys.path.remove(str(out / "scripts/process"))
        for name in names:
            sys.modules.pop(name, None)


# --- v2.77 refute round 1: what a reader sees is what the gate reads ------------------

HDR = "| State | Event | Result | Test |\n|---|---|---|---|\n"
ROW = "| draft | submit | in review | `tests/test_order.py::test_submit` |\n"
TICK = "\n- [x] T1 states\n"


def test_a_transitions_table_without_a_row_fails(render, tmp_path):
    """Header and delimiter alone state no transition: not even at the merge do they pass."""
    out = _repo(render(tmp_path, {"project_name": "demo"}))
    _plan(out, GOOD + "\n## Transitions\n\n" + HDR + TICK)
    r = _run(out, merge=True)
    assert r.returncode == 1 and ":13: the transitions table has no row" in r.stdout, r.stdout
    _plan(out, GOOD + "\n## Transitions\n\n" + HDR)
    assert ":13: the transitions table has no row" in _run(out).stdout


def test_an_html_comment_hides_a_section_and_its_table(render, tmp_path):
    """A commented-out section is no section; a table inside a comment is no table; a
    finding after a comment names the file's own line."""
    out = _repo(render(tmp_path, {"project_name": "demo"}))
    _plan(out, GOOD + "\n<!--\n## Transitions\n\n(no state work here)\n-->\n")
    r = _run(out)
    assert r.returncode == 0, r.stdout
    _plan(out, GOOD + "\n## Transitions\n\nDraft goes to review.\n\n<!--\n" + HDR + ROW + "-->\n")
    r = _run(out)
    assert r.returncode == 1 and ":11: `## Transitions` has no table" in r.stdout, r.stdout
    _plan(out, GOOD + "\n## Transitions <!-- states -->\n\nSee <!-- one\ncomment --> below.\n\n" + HDR
          + "| draft |  | in review | struck — later |\n")
    r = _run(out)
    assert r.returncode == 1 and ":18: transitions row leaves `Event` empty" in r.stdout, r.stdout


def test_an_inventory_table_beside_the_transitions_table_passes(render, tmp_path):
    """The writer and reader inventory /plan asks for beside the table needs no `Test`
    column; a section where no table has one fails."""
    out = _repo(render(tmp_path, {"project_name": "demo"}))
    inventory = "\n### Writers and readers\n\n| Role | Site |\n|---|---|\n| writer | src/a.py:10 |\n"
    _plan(out, GOOD + "\n## Transitions\n\n" + HDR + ROW + inventory + TICK)
    r = _run(out, merge=True)
    assert r.returncode == 0, r.stdout
    _plan(out, GOOD + "\n## Transitions\n\n| State | Event | Result |\n|---|---|---|\n| a | b | c |\n" + inventory)
    r = _run(out)
    assert r.returncode == 1 and ":13: the transitions table has no `Test` column" in r.stdout, r.stdout


def test_the_test_column_may_be_named_tests(render, tmp_path):
    out = _repo(render(tmp_path, {"project_name": "demo"}))
    for name in ("Tests", "Test(s)", "test(s)", "TEST", "**Tests**"):
        _plan(out, GOOD + f"\n## Transitions\n\n| State | Event | Result | {name} |\n|---|---|---|---|\n" + ROW + TICK)
        r = _run(out, merge=True)
        assert r.returncode == 0, (name, r.stdout)


def test_an_indented_heading_is_a_heading(render, tmp_path):
    """Up to three spaces in, `## Transitions` opens the section and `## Next` ends it;
    four spaces in, it is indented code."""
    out = _repo(render(tmp_path, {"project_name": "demo"}))
    _plan(out, GOOD + "\n   ## Transitions\n\nprose only\n")
    r = _run(out)
    assert r.returncode == 1 and ":11: `## Transitions` has no table" in r.stdout, r.stdout
    _plan(out, GOOD + "\n## Transitions\n\nprose only\n\n   ## Next\n\n" + HDR + ROW)
    assert ":11: `## Transitions` has no table" in _run(out).stdout
    _plan(out, GOOD + "\n    ## Transitions\n\nprose only\n")
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_a_setext_heading_ends_the_section(render, tmp_path):
    out = _repo(render(tmp_path, {"project_name": "demo"}))
    for underline in ("-----", "====="):
        _plan(out, GOOD + f"\n## Transitions\n\nprose only\n\nOther\n{underline}\n\n" + HDR + ROW)
        r = _run(out)
        assert r.returncode == 1 and ":11: `## Transitions` has no table" in r.stdout, (underline, r.stdout)
    # a deeper section ends at a setext level-2 heading too; a thematic break ends nothing
    _plan(out, GOOD + "\n### Transitions\n\nprose only\n\nOther\n---\n\n" + HDR + ROW)
    assert "`### Transitions` has no table" in _run(out).stdout
    _plan(out, GOOD + "\n## Transitions\n\nprose only\n\n---\n\n" + HDR + ROW + TICK)
    r = _run(out, merge=True)
    assert r.returncode == 0, r.stdout


def test_a_table_without_outer_pipes_is_a_table(render, tmp_path):
    out = _repo(render(tmp_path, {"project_name": "demo"}))
    _plan(out, GOOD + "\n## Transitions\n\nState | Event | Result | Test\n---|---|---|---\n"
          "draft | submit | review | `tests/x.py::test_submit`\n" + TICK)
    r = _run(out, merge=True)
    assert r.returncode == 0, r.stdout
    _plan(out, GOOD + "\n## Transitions\n\nState | Event | Result | Test\n:--- | --- | --- | ---\n"
          "draft |  | review | struck — later\n")
    r = _run(out)
    assert r.returncode == 1 and ":15: transitions row leaves `Event` empty" in r.stdout, r.stdout
