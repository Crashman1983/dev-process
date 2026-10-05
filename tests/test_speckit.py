"""speckit module (standard, default-on): Spec Kit as the Tier 2+
specification path — rendered overrides, constitution pointer with gate
guard, deterministic test-task floor, clarification on specs/, publish-and-
prune merge ritual."""
import subprocess
import sys

import pytest

CONST = ".specify/memory/constitution.md"
OVR = ".specify/templates/overrides"


def _render(render, tmp_path, on=True):
    return render(tmp_path, {"project_name": "d", "modules": {"speckit": on}})


def _gate(out):
    return subprocess.run(
        [sys.executable, str(out / "scripts/process/check_speckit.py"), "."],
        cwd=out, capture_output=True, text=True)


def _clar(out):
    return subprocess.run(
        [sys.executable, str(out / "scripts/process/check_clarification.py"), "."],
        cwd=out, capture_output=True, text=True)


def test_module_renders_overrides_and_pointer(render, tmp_path):
    out = _render(render, tmp_path)
    spec_ovr = (out / OVR / "spec-template.md").read_text()
    tasks_ovr = (out / OVR / "tasks-template.md").read_text()
    const = (out / CONST).read_text()
    # EARS + DoR twins in the spec override (one acceptance grammar)
    assert "EARS" in spec_ovr and "shall" in spec_ovr
    assert "invalidation/cleanup" in spec_ovr
    assert "Success Criteria" in spec_ovr and "SC-001" in spec_ovr
    # the upstream "tests optional" stance is inverted
    assert "Tests are MANDATORY" in tasks_ovr
    assert "Checkpoint" in tasks_ovr
    # constitution is a pointer, never authored principles
    assert "DEV-PROCESS-CONSTITUTION-POINTER" in const
    assert "mandatory-rules.md" in const
    assert "Do NOT run `/speckit-constitution`" in const


def test_module_off_renders_nothing(render, tmp_path):
    out = _render(render, tmp_path, on=False)
    assert not (out / ".specify").exists()
    assert not (out / "scripts/process/check_speckit.py").exists()
    assert not (out / "scripts/process/publish_and_prune.py").exists()


def test_gate_soft_before_init_is_impossible_here(render, tmp_path):
    # the module renders .specify/ itself (pointer + overrides), so the gate
    # always has the pointer to verify on a fresh render — and passes
    out = _render(render, tmp_path)
    r = _gate(out)
    assert r.returncode == 0, r.stdout + r.stderr


def test_gate_fails_when_pointer_replaced(render, tmp_path):
    # someone ran /speckit-constitution: generated principles replace the
    # pointer — a second truth beside the gated one
    out = _render(render, tmp_path)
    (out / CONST).write_text("# My Constitution\n\n## Principles\nI. Be nice.\n")
    r = _gate(out)
    assert r.returncode == 1
    assert "pointer marker missing" in r.stdout


def test_gate_fails_story_phase_without_test_task(render, tmp_path):
    out = _render(render, tmp_path)
    d = out / "specs/001-widget"
    d.mkdir(parents=True)
    (d / "tasks.md").write_text(
        "# Tasks\n\n## Phase 3: User Story 1 — widget (P1)\n\n"
        "- [ ] T001 [US1] Implement widget in src/widget.py\n")
    r = _gate(out)
    assert r.returncode == 1
    assert "no task that references a test" in r.stdout and "rule 5" in r.stdout
    # the message teaches /plan's grain, not a separate test task
    assert "one task per behaviour" in r.stdout and "red → green" in r.stdout


def test_gate_passes_combined_behaviour_task(render, tmp_path):
    # /plan's grain: one task = one behaviour, test AND implementation —
    # the test reference inside the combined task satisfies the floor
    out = _render(render, tmp_path)
    d = out / "specs/001-widget"
    d.mkdir(parents=True)
    (d / "tasks.md").write_text(
        "# Tasks\n\n## Phase 3: User Story 1 — widget (P1)\n\n"
        "- [ ] T001 [US1] AC-1 widget saves: test in tests/test_widget.py "
        "(red) → implement in src/widget.py (green)\n"
        "\n## Phase 4: User Story 2 — export (P2)\n\n"
        "- [ ] T002 [US2] AC-3 export csv: implement in src/export.py\n")
    r = _gate(out)
    # US1 (combined, with test) passes; US2 (no test reference) still fails
    assert r.returncode == 1
    assert "User Story 2" in r.stdout and "User Story 1" not in r.stdout
    (d / "tasks.md").write_text(
        "# Tasks\n\n## Phase 3: User Story 1 — widget (P1)\n\n"
        "- [ ] T001 [US1] AC-1 widget saves: test in tests/test_widget.py "
        "(red) → implement in src/widget.py (green)\n")
    r = _gate(out)
    assert r.returncode == 0, r.stdout


def test_tasks_template_teaches_one_task_per_behaviour(render, tmp_path):
    out = _render(render, tmp_path)
    tasks_ovr = (out / OVR / "tasks-template.md").read_text()
    assert "One task = one behaviour, test AND implementation" in tasks_ovr
    assert "(red) → implement in src/… (green)" in tasks_ovr
    assert "Test: failing test(s)" not in tasks_ovr  # the split example is gone
    # one example asserts a refusal path, with its test and files named
    assert ("test `test_expired_invite_is_refused` in tests/test_invites.py asserts the error"
            in tasks_ovr)
    assert "One atomic commit per task" not in tasks_ovr  # test + impl may be two commits (/plan)
    plan = (out / ".claude/commands/plan.md").read_text()
    assert "one task = one behaviour, test AND implementation" in plan  # same rule, one source



def test_parallel_marker_has_one_owner_with_both_examples(render, tmp_path):
    out = _render(render, tmp_path)
    plan = " ".join((out / ".claude/commands/plan.md").read_text().split())
    assert "Disjoint files are necessary, not sufficient." in plan
    assert "the file format is still open — no `[P]`" in plan  # unsettled contract
    assert "no shared port — `[P]`" in plan  # fixed contract, conflict-free resources
    execute = (out / ".claude/commands/execute.md").read_text()
    tasks_ovr = (out / OVR / "tasks-template.md").read_text()
    for consumer in (execute, tasks_ovr):
        assert "(different files, no dependencies)" not in consumer
        assert "disjoint files and a fixed shared contract" in " ".join(consumer.split())
    # the non-speckit plan command carries the task grain and the [P] pointer too
    plain = " ".join((_render(render, tmp_path / "off", on=False)
                      / ".claude/commands/plan.md").read_text().split())
    assert "One task = one behaviour" in plain
    assert "disjoint files and a fixed shared contract" in plain

def test_gate_passes_story_phase_with_test_task(render, tmp_path):
    # an existing split-style tasks.md (test task, then implement task) stays
    # compatible — the floor is the test reference, not the shape
    out = _render(render, tmp_path)
    d = out / "specs/001-widget"
    d.mkdir(parents=True)
    (d / "tasks.md").write_text(
        "# Tasks\n\n## Phase 3: User Story 1 — widget (P1)\n\n"
        "- [ ] T001 [US1] Test: failing test for AC-1 in tests/test_widget.py\n"
        "- [ ] T002 [US1] Implement widget in src/widget.py\n"
        "\n## Final phase: Polish\n\n- [ ] T003 Update docs\n")
    r = _gate(out)
    assert r.returncode == 0, r.stdout
    # unchecked tasks are the deterministic completeness signal (converge diet)
    assert "unchecked task(s)" in r.stdout


def test_clarification_marker_in_spec_is_note_in_plan_is_hard(render, tmp_path):
    out = _render(render, tmp_path)
    d = out / "specs/001-widget"
    d.mkdir(parents=True)
    (d / "spec.md").write_text("# Spec\n\n[NEEDS CLARIFICATION: which auth?]\n")
    r = _clar(out)
    assert r.returncode == 0, r.stdout
    assert "speckit-clarify" in r.stdout  # visible note
    (d / "plan.md").write_text("# Plan\n\n[NEEDS CLARIFICATION: which auth?]\n")
    r = _clar(out)
    assert r.returncode == 1
    assert "unclarified spec" in r.stdout


def test_commands_repointed_when_module_on(render, tmp_path):
    out = _render(render, tmp_path)
    brainstorm = (out / ".claude/commands/brainstorm.md").read_text()
    plan = (out / ".claude/commands/plan.md").read_text()
    assert "speckit-specify" in brainstorm and "speckit-clarify" in brainstorm
    assert "tier first" in brainstorm  # kernel duty travels into the wrapper
    assert "speckit-plan" in plan and "speckit-tasks" in plan
    assert "tier: N" in plan and "issue: <ref>" in plan
    # replacement, not parallel operation: the old design-template path is gone
    assert "design-template.md" not in brainstorm


def test_commands_keep_fallback_when_module_off(render, tmp_path):
    out = _render(render, tmp_path, on=False)
    brainstorm = (out / ".claude/commands/brainstorm.md").read_text()
    assert "design-template.md" in brainstorm
    assert "speckit" not in brainstorm


def test_module_doc_pins_version_and_exit_scenario(render, tmp_path):
    out = _render(render, tmp_path)
    doc = (out / "docs/process/modules/speckit.md").read_text()
    assert "specify-cli==" in doc  # pinned, vendored dependency
    assert "speckit-implement" in doc  # excluded skills named
    assert "Exit scenario" in doc and "freeze the pin" in doc
    assert "Tier 3" in doc  # analyze/converge reserved for Tier 3 (token economy)
    assert "publish_and_prune.py" in doc
    assert "feature.json" in doc  # gitignored per-checkout state


def test_publish_and_prune_refuses_without_issue_or_sc_accounting(render, tmp_path):
    out = _render(render, tmp_path)
    d = out / "specs/001-widget"
    d.mkdir(parents=True)
    (d / "spec.md").write_text("# Spec\n\n- SC-001: users finish in 2 min\n")
    (d / "plan.md").write_text("# Plan\n\ntier: 2\n")
    r = subprocess.run(
        [sys.executable, str(out / "scripts/process/publish_and_prune.py"), "001-widget"],
        cwd=out, capture_output=True, text=True)
    assert r.returncode == 1
    assert "no issue: ref" in r.stderr
    assert (d / "spec.md").is_file()  # nothing pruned on refusal
    (d / "plan.md").write_text("# Plan\n\ntier: 2\nissue: #7\n")
    r = subprocess.run(
        [sys.executable, str(out / "scripts/process/publish_and_prune.py"), "001-widget"],
        cwd=out, capture_output=True, text=True)
    assert r.returncode == 1
    assert "SC-001" in r.stderr  # unaccounted SC blocks the prune
    assert (d / "spec.md").is_file()


def test_gate_runner_lists_speckit(render, tmp_path):
    out = _render(render, tmp_path)
    r = subprocess.run(
        [sys.executable, str(out / "scripts/process/gate_runner.py"), "--list"],
        cwd=out, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "speckit" in r.stdout.splitlines()


def test_workflow_phases_point_to_speckit(render, tmp_path):
    out = _render(render, tmp_path)
    text = (out / "docs/process/workflow.md").read_text()
    assert "speckit-specify" in text and "speckit-tasks" in text
    out2 = _render(render, tmp_path / "off", on=False)
    assert "speckit" not in (out2 / "docs/process/workflow.md").read_text()


# --- spec-before-plan: active Tier 2+ plans point at their spec or say why not ---

def _plan(out, name, body):
    d = out / ".process-work/plans"
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(body, encoding="utf-8")


def test_gate_fails_tier2_plan_without_spec_ref(render, tmp_path):
    out = _render(render, tmp_path)
    _plan(out, "2026-08-07-thing.md", "# Plan\n\ntier: 2\nissue: #1\n\nSteps.\n")
    r = _gate(out)
    assert r.returncode == 1
    assert "spec-waived" in r.stdout and "specs/" in r.stdout


def test_gate_passes_plan_with_spec_ref_or_waiver(render, tmp_path):
    out = _render(render, tmp_path)
    _plan(out, "2026-08-07-a.md", "tier: 2\n\nBuilt from specs/001-widget/.\n")
    _plan(out, "2026-08-07-b.md", "tier: 3\nspec-waived: hotfix, no feature scope\n")
    r = _gate(out)
    assert r.returncode == 0, r.stdout


def test_gate_ignores_tier1_designs_and_fenced_quotes(render, tmp_path):
    out = _render(render, tmp_path)
    _plan(out, "2026-08-07-small.md", "tier: 1\n")
    _plan(out, "design-2026-08-07-idea.md", "tier: 3\n")
    _plan(out, "2026-08-07-doc.md", "```\ntier: 2\n```\nNo declaration here.\n")
    r = _gate(out)
    assert r.returncode == 0, r.stdout


def test_stage_publish_needs_issue_ref_and_prunes_nothing(render, tmp_path):
    out = _render(render, tmp_path)
    d = out / "specs/003-widget"
    d.mkdir(parents=True)
    (d / "spec.md").write_text("# Feature\n\nStories.\n")
    r = subprocess.run(
        [sys.executable, str(out / "scripts/process/publish_and_prune.py"),
         "--stage", "003-widget"], cwd=out, capture_output=True, text=True)
    assert r.returncode == 1
    assert "issue-before-spec" in r.stderr
    assert (d / "spec.md").is_file()  # --stage never prunes, even on failure


# --- v2.9.3: publish goes REST when GraphQL throttles; deny-list before posting

def _fake_gh(tmp_path, *, comment_fails=True):
    """A gh stub: `issue comment` fails (GraphQL secondary limit), `api`
    succeeds and logs; `api …/comments` returns the marker so the verify
    step passes. Every call is appended to gh.log."""
    binpath = tmp_path / "bin"
    binpath.mkdir(exist_ok=True)
    log = tmp_path / "gh.log"
    script = binpath / "gh"
    script.write_text(f"""#!/bin/sh
echo "$@" >> {log}
case "$1 $2" in
  "issue comment") {"echo 'GraphQL: secondary rate limit' >&2; exit 1" if comment_fails else "exit 0"} ;;
  "api --paginate") echo '[{{"body": "<!-- publish_and_prune -->"}}]'; exit 0 ;;
  "api "*) exit 0 ;;
  *) exit 0 ;;
esac
""")
    script.chmod(0o755)
    return binpath, log


def test_publish_falls_back_to_rest_when_graphql_throttles(render, tmp_path):
    import os
    out = _render(render, tmp_path)
    d = out / "specs/004-widget"
    d.mkdir(parents=True)
    (d / "spec.md").write_text("# Feature\n\nissue: #12\n")
    binpath, log = _fake_gh(tmp_path)
    env = {**os.environ, "PATH": f"{binpath}:{os.environ['PATH']}"}
    r = subprocess.run([sys.executable, str(out / "scripts/process/publish_and_prune.py"),
                        "--stage", "004-widget"], cwd=out, capture_output=True,
                       text=True, env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "retrying via REST" in r.stderr
    calls = log.read_text()
    assert "api repos/{owner}/{repo}/issues/12/comments -f body=" in calls


def test_publish_refuses_on_denylist_hit(render, tmp_path):
    import os
    out = _render(render, tmp_path)
    (out / ".publish-denylist").write_text("# client slugs from the UI-test stubs\nacme-[a-z]+\n")
    d = out / "specs/005-widget"
    d.mkdir(parents=True)
    (d / "spec.md").write_text("# Feature\n\nissue: #12\n\nsee client acme-berlin\n")
    binpath, log = _fake_gh(tmp_path, comment_fails=False)
    env = {**os.environ, "PATH": f"{binpath}:{os.environ['PATH']}"}
    r = subprocess.run([sys.executable, str(out / "scripts/process/publish_and_prune.py"),
                        "--stage", "005-widget"], cwd=out, capture_output=True,
                       text=True, env=env)
    assert r.returncode == 1
    assert "REFUSED" in r.stderr and "line 5" in r.stderr and "acme-" in r.stderr
    assert not log.exists()  # nothing was posted


# --- Kenni #2382: the prune never deletes what tracked code still uses, nor uncommitted work

def _probe_repo(render, tmp_path, test_body):
    import os
    out = _render(render, tmp_path)
    d = out / "specs/013-probe"
    (d / "probes").mkdir(parents=True)
    (d / "spec.md").write_text("# Spec\n")
    (d / "plan.md").write_text("# Plan\n\nissue: #13\n")
    (d / "tasks.md").write_text("- [x] T001 done\n")
    (d / "probes/egress_probe.py").write_text("OK = True\n")
    (out / "tests").mkdir(exist_ok=True)
    (out / "tests/test_x.py").write_text(test_body)
    for args in (("init", "-q", "-b", "main"), ("config", "user.email", "t@t"),
                 ("config", "user.name", "t"), ("add", "-A"), ("commit", "-q", "-m", "base")):
        subprocess.run(["git", *args], cwd=out, check=True, capture_output=True)
    binpath, log = _fake_gh(tmp_path, comment_fails=False)
    env = {**os.environ, "PATH": f"{binpath}:{os.environ['PATH']}"}
    prune = [sys.executable, str(out / "scripts/process/publish_and_prune.py"), "013-probe"]
    return out, d, log, lambda: subprocess.run(prune, cwd=out, capture_output=True,
                                               text=True, env=env)


IMPORTS_PROBE = ("import sys\nfrom pathlib import Path\n"
                 "sys.path.insert(0, str(Path(__file__).parents[1] / 'specs/013-probe/probes'))\n"
                 "import egress_probe\n")


def test_prune_refuses_a_spec_dir_whose_probe_a_tracked_test_imports(render, tmp_path):
    out, d, log, prune = _probe_repo(render, tmp_path, IMPORTS_PROBE)
    r = prune()
    assert r.returncode == 1, r.stdout + r.stderr
    assert "tests/test_x.py:3" in r.stderr and "specs/013-probe/probes/" in r.stderr
    assert (d / "probes/egress_probe.py").is_file() and not log.exists()


@pytest.mark.parametrize("line", ["p = 'specs/013-probe/probes/egress_probe.py'\n",
                                  "from probes.egress_probe import OK\n"])
def test_prune_names_a_file_reference_by_path_or_module(render, tmp_path, line):
    out, d, log, prune = _probe_repo(render, tmp_path, "import os\n" + line)
    r = prune()
    assert r.returncode == 1
    assert "specs/013-probe/probes/egress_probe.py (referenced at tests/test_x.py:2)" in r.stderr
    assert d.is_dir()


def test_prune_of_an_unreferenced_spec_dir_works_as_before(render, tmp_path):
    out, d, log, prune = _probe_repo(render, tmp_path, "def test_x():\n    assert True\n")
    r = prune()
    assert r.returncode == 0, r.stdout + r.stderr
    assert not d.exists() and "pruned specs/013-probe/" in r.stdout


@pytest.mark.parametrize("dirty", ["untracked", "modified"])
def test_prune_refuses_uncommitted_content_and_deletes_nothing(render, tmp_path, dirty):
    out, d, log, prune = _probe_repo(render, tmp_path, "def test_x():\n    assert True\n")
    target = d / ("probes/notes.txt" if dirty == "untracked" else "probes/egress_probe.py")
    target.write_text("work in progress\n")
    r = prune()
    assert r.returncode == 1
    assert "uncommitted or untracked" in r.stderr and "nothing pruned" in r.stderr
    assert target.read_text() == "work in progress\n" and (d / "spec.md").is_file()
    assert not log.exists()
