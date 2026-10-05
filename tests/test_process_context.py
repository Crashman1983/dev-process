"""process_context.py (core): deterministic session orientation — one JSON
call instead of exploratory reads (the token-lean pass)."""
import json
import subprocess
import sys


def _run(out, *args):
    r = subprocess.run(
        [sys.executable, str(out / "scripts/process/process_context.py"), ".", *args],
        cwd=out, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return json.loads(r.stdout)


def _git(out, branch="feat-x"):
    subprocess.run(["git", "init", "-q", "-b", branch], cwd=out, check=True)


def test_core_tool_renders_always(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    assert (out / "scripts/process/process_context.py").is_file()


def test_empty_project_yields_clean_json(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    ctx = _run(out)
    assert ctx["active_plans"] == []
    assert ctx["spec_features"] == []
    assert ctx["inbox_items"] == 0


def test_context_names_next_task_and_markers(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {"speckit": True}})
    _git(out)
    d = out / "specs/001-widget"
    d.mkdir(parents=True)
    (d / "plan.md").write_text("# Plan\n\ntier: 2\nissue: #7\n")
    (d / "spec.md").write_text("# Spec\n\n[NEEDS CLARIFICATION: auth?]\n")
    (d / "tasks.md").write_text(
        "# Tasks\n\n- [x] T001 Test widget in tests/test_widget.py\n"
        "- [ ] T002 Implement widget in src/widget.py\n"
        "- [ ] T003 Docs\n")
    ctx = _run(out, "--all")
    feat = ctx["spec_features"][0]
    assert feat["tier"] == 2 and feat["issue"] == "#7"
    assert feat["tasks_done"] == 1 and feat["tasks_open"] == 2
    assert feat["next_task"].startswith("T002")
    assert feat["unresolved_markers"] == 1
    assert ctx["branch"] == "feat-x"


def test_context_reads_active_plans_and_inbox(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    p = out / ".process-work/plans"
    p.mkdir(parents=True, exist_ok=True)
    (p / "2026-08-06-thing.md").write_text("# Plan\n\ntier: 3\nissue: #9\n")
    (out / ".process-work/inbox.md").write_text("- fix the flaky test\n- docs\n")
    ctx = _run(out, "--issue", "9")
    assert ctx["active_plans"][0]["tier"] == 3
    assert ctx["inbox_items"] == 2


def test_prime_and_execute_point_to_context_tool(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    prime = (out / ".claude/commands/prime.md").read_text()
    execute = (out / ".claude/commands/execute.md").read_text()
    assert "process_context.py" in prime
    assert "never the whole journal" in prime  # the prime diet
    assert "process_context.py" in execute
    assert "checkbox" in execute  # progress-in-the-artifact
    assert "--issue N" in prime and "--issue N" in execute  # the scope, when known


def test_context_prints_the_decisions_ledger(render, tmp_path):
    # SP69: what a compaction summary drops, the plan keeps and prime re-reads
    out = render(tmp_path, {"project_name": "d"})
    d = out / ".process-work/plans"
    d.mkdir(parents=True, exist_ok=True)
    (d / "2026-09-10-panel.md").write_text(
        "# Plan\n\ntier: 2\n\n## Decisions\n"
        "- DECISION 2026-09-10 owner: variant B, not A — because one export owner\n"
        "- DECISION 2026-09-10 agent: skip CSV in this slice — because deferred\n"
        "- DECISION NEEDED 2026-09-11 panel: keep the legacy export? — options: A, B; recommendation: B\n")
    (d / "2026-09-10-bare.md").write_text("# Plan\n\ntier: 2\n")
    ctx = _run(out, "--all")
    plans = {p["file"]: p for p in ctx["active_plans"]}
    panel = plans[".process-work/plans/2026-09-10-panel.md"]
    assert panel["decisions_section"] is True
    assert panel["decisions"] == [
        "2026-09-10 owner: variant B, not A — because one export owner",
        "2026-09-10 agent: skip CSV in this slice — because deferred"]
    # an open question is not a decision — and a re-hydrated session must see it
    assert panel["open_questions"] == ["2026-09-11 panel: keep the legacy export? — options: A, B; recommendation: B"]
    bare = plans[".process-work/plans/2026-09-10-bare.md"]
    assert bare["decisions_section"] is False and bare["decisions"] == [] and bare["open_questions"] == []


# --- scoping: the current work in full, everything else as an index ----------

def _two_plans(out):
    d = out / ".process-work/plans"
    d.mkdir(parents=True, exist_ok=True)
    (d / "2026-10-01-login.md").write_text(
        "# Plan\n\ntier: 2\nissue: #7\n\n- DECISION 2026-10-01 owner: x — because y\n")
    (d / "2026-10-02-export.md").write_text(
        "# Plan\n\ntier: 3\nissue: https://github.com/o/r/issues/9\n\n- [ ] step\n")


def test_branch_scopes_the_plans_and_indexes_the_rest(render, tmp_path):
    """downstream printed 428k chars of every plan and spec; a session needs its own"""
    out = render(tmp_path, {"project_name": "d"})
    _git(out, "feat/7-login")
    _two_plans(out)
    ctx = _run(out)
    assert ctx["scope"] == {"issue": 7, "source": "branch"}
    assert [p["file"] for p in ctx["active_plans"]] == [".process-work/plans/2026-10-01-login.md"]
    assert ctx["active_plans"][0]["decisions"]  # in scope: full detail
    assert ctx["other_plans"] == [{"file": ".process-work/plans/2026-10-02-export.md",
                                   "issue": 9, "tier": 3, "tasks_open": 1}]


def test_issue_flag_beats_the_branch(render, tmp_path):
    """an explicit issue is what the agent knows; the branch is a guess"""
    out = render(tmp_path, {"project_name": "d"})
    _git(out, "feat/7-login")
    _two_plans(out)
    ctx = _run(out, "--issue", "9")
    assert ctx["scope"] == {"issue": 9, "source": "--issue"}
    assert [p["issue"] for p in ctx["active_plans"]] == ["https://github.com/o/r/issues/9"]
    assert [p["issue"] for p in ctx["other_plans"]] == [7]


def test_main_without_issue_prints_indexes_only(render, tmp_path):
    """nothing in scope is not nothing at all: every item stays in the index"""
    out = render(tmp_path, {"project_name": "d"})
    _git(out, "main")
    _two_plans(out)
    ctx = _run(out)
    assert ctx["scope"] == {"issue": None, "source": "none"}
    assert ctx["active_plans"] == [] and len(ctx["other_plans"]) == 2
    assert "--issue N" in ctx["hint"]


def _spec(out, name, spec="", plan="", tasks=""):
    d = out / "specs" / name
    d.mkdir(parents=True)
    for f, text in (("spec.md", spec), ("plan.md", plan), ("tasks.md", tasks)):
        if text:
            (d / f).write_text(text)


def test_spec_dir_scoped_by_spec_issue_and_by_branch_named_dir(render, tmp_path):
    """spec.md's issue: decides (issue-before-spec); a spec branch is named after its dir"""
    out = render(tmp_path, {"project_name": "d", "modules": {"speckit": True}})
    _git(out, "feat/7-login")
    _spec(out, "002-login", spec="# S\n\nissue: o/r#7\n", plan="# P\n\nissue: #99\n")
    _spec(out, "003-chat", spec="# S\n\nissue: #12\n")
    ctx = _run(out)
    assert [f["dir"] for f in ctx["spec_features"]] == ["specs/002-login"]
    assert ctx["other_specs"] == [{"dir": "specs/003-chat", "issue": 12, "tier": None, "tasks_open": 0}]
    # branch named after the dir: `003` is not issue 3, the dir's spec names the issue
    subprocess.run(["git", "symbolic-ref", "HEAD", "refs/heads/003-chat"], cwd=out, check=True)
    (out / ".process-work/plans").mkdir(parents=True, exist_ok=True)
    (out / ".process-work/plans/2026-10-03-chat.md").write_text("# P\n\ntier: 2\nissue: #12\n")
    ctx = _run(out)
    assert ctx["scope"] == {"issue": 12, "source": "branch"}
    assert [f["dir"] for f in ctx["spec_features"]] == ["specs/003-chat"]
    assert [p["file"] for p in ctx["active_plans"]] == [".process-work/plans/2026-10-03-chat.md"]


def test_index_marks_finished_unpruned_specs_done(render, tmp_path):
    """a finished spec dir nobody pruned must stay visible, not look like work"""
    out = render(tmp_path, {"project_name": "d", "modules": {"speckit": True}})
    _git(out, "main")
    _spec(out, "001-old", spec="# S\n\nissue: #1\n", tasks="- [x] T001 a\n")
    _spec(out, "002-new", spec="# S\n\nissue: #2\n", tasks="- [x] T001 a\n- [ ] T002 b\n")
    specs = {s["dir"]: s for s in _run(out)["other_specs"]}
    assert specs["specs/001-old"]["done"] is True
    assert "done" not in specs["specs/002-new"]


def test_all_prints_the_unscoped_shape(render, tmp_path):
    """--all is the escape hatch: every item in full, no index lists"""
    out = render(tmp_path, {"project_name": "d", "modules": {"speckit": True}})
    _git(out, "main")
    _two_plans(out)
    _spec(out, "001-x", spec="# S\n\nissue: #1\n")
    ctx = _run(out, "--all")
    assert len(ctx["active_plans"]) == 2 and len(ctx["spec_features"]) == 1
    assert not {"scope", "other_plans", "other_specs", "hint"} & set(ctx)


def test_cost_is_measured_over_everything_regardless_of_scope(render, tmp_path):
    """the cost report must not shrink because the printed view did"""
    out = render(tmp_path, {"project_name": "d"})
    _git(out, "feat/7-login")
    _two_plans(out)
    scoped = _run(out, "--cost")["context_cost"]
    assert scoped == _run(out, "--all", "--cost")["context_cost"]
    assert scoped["available"]["active_plans"]["files"] == 2


def test_help_names_the_scope_flags(render, tmp_path):
    """the ad-hoc parse took `--issue 7` for a root path"""
    out = render(tmp_path, {"project_name": "d"})
    r = subprocess.run([sys.executable, str(out / "scripts/process/process_context.py"), "--help"],
                       cwd=out, capture_output=True, text=True)
    assert r.returncode == 0 and "--issue" in r.stdout and "--all" in r.stdout
