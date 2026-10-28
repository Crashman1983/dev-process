import os
import json
import subprocess
import sys
from pathlib import Path

KENNI = ["Kenni", "KenniNext", "Seb", "Signal", "SvelteKit", "user_id=1", "surface:ios"]

JOURNAL = ".process-work/journal"

def _render(render, tmp_path, **mods):
    m = {"telemetry": True}
    m.update(mods)
    return render(tmp_path, {"project_name": "d", "modules": m})


def _kpis(out: Path, *args: str):
    return subprocess.run(
        [sys.executable, str(out / "scripts/process/process_kpis.py"), *args],
        capture_output=True, text=True,
    )


def _journal(out: Path, text: str, name: str = "2026-07-02.md"):
    d = out / JOURNAL
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(text, encoding="utf-8")


# --- module wiring -----------------------------------------------------------

def test_module_on_ships_cockpit_and_doc_without_a_gate(render, tmp_path):
    out = _render(render, tmp_path)
    assert not (out / "scripts/process/check_telemetry.py").exists()  # retired
    assert (out / "scripts/process/process_kpis.py").is_file()
    assert (out / "docs/process/modules/telemetry.md").is_file()


def test_module_off_ships_nothing(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    assert not (out / "scripts/process/process_kpis.py").exists()
    assert not (out / "docs/process/modules/telemetry.md").exists()
    # module OFF ships nothing — not even the seed dir (Finding-D discipline)
    assert not (out / "docs/process/telemetry").exists()


def test_doc_carries_honest_ceiling(render, tmp_path):
    # the honesty contract must not silently drop: numbers are within-project
    # trends/ratios/events, never cross-project benchmarks
    out = _render(render, tmp_path)
    doc = (out / "docs/process/modules/telemetry.md").read_text()
    assert "honest ceiling" in doc
    assert "Within-project only" in doc
    assert "Events are the robust class" in doc
    cockpit = (out / "scripts/process/process_kpis.py").read_text()
    assert "within-project only" in cockpit


def test_answers_records_telemetry(render, tmp_path):
    out = _render(render, tmp_path)
    assert "telemetry: true" in (out / ".copier-answers.yml").read_text()


def test_gate_runner_runs_no_telemetry_gate_and_accepts_the_module(render, tmp_path):
    out = _render(render, tmp_path)
    r = subprocess.run(
        [sys.executable, str(out / "scripts/process/gate_runner.py"), "--list"],
        cwd=out, capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    assert "telemetry" not in r.stdout
    r = subprocess.run([sys.executable, str(out / "scripts/process/gate_runner.py")],
                       cwd=out, capture_output=True, text=True)
    assert "unknown module" not in (r.stdout + r.stderr), r.stdout + r.stderr


def test_workflow_asks_for_no_grade_lines(render, tmp_path):
    on = _render(render, tmp_path / "on")
    assert "GRADE" not in (on / "docs/process/workflow.md").read_text()


# --- cockpit -----------------------------------------------------------------


def test_cost_per_issue_reads_the_policy_transcripts_or_says_not_measured(render, tmp_path):
    """Tokens per issue were never recorded downstream; the cockpit reads dispatch's count."""
    import json
    out = _render(render, tmp_path)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=out, check=True)
    r = _kpis(out, "cost", "--issue", "7")
    assert r.returncode == 0 and "issue #7" in r.stdout and "tokens: not measured" in r.stdout, r.stdout + r.stderr
    (tmp_path / "t").mkdir()
    (tmp_path / "t" / "s.jsonl").write_text('{"output_tokens": 5}\n')
    (out / ".git/process-dispatch").mkdir()
    (out / ".git/process-dispatch/7-x.json").write_text(json.dumps({"issue": 7, "worktree": str(tmp_path)}))
    (out / "docs/process/model-policy.local.json").write_text(json.dumps({"transcripts": "{worktree}/t/*.jsonl"}))
    r = _kpis(out, "cost", "--issue", "7")
    assert "tokens: 5 output over 1 sessions" in r.stdout, r.stdout + r.stderr


def test_models_reports_each_models_token_share_subagents_included(render, tmp_path):
    """#125 AC-3: did the mechanical steps move to the smaller model? Read
    from the dispatched sessions' transcripts, a subagent's messages count."""
    import json
    out = _render(render, tmp_path)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=out, check=True)
    def models():  # `models` reads the project it runs in
        return subprocess.run([sys.executable, str(out / "scripts/process/process_kpis.py"), "models"],
                              cwd=out, capture_output=True, text=True)

    r = models()
    assert r.returncode == 0 and "tokens by model" in r.stdout and "not measured" in r.stdout, r.stdout + r.stderr
    for issue in (7, 8):
        (tmp_path / f"w{issue}" / "t").mkdir(parents=True)
    big = '{"message": {"id": "%s", "model": "claude-big-1", "usage": {"input_tokens": 600, "output_tokens": 100}}, "requestId": "r"}\n'
    # one message, two content-block lines: counted once
    (tmp_path / "w7" / "t" / "main.jsonl").write_text(big % "m1" + big % "m1")
    (tmp_path / "w7" / "t" / "agent.jsonl").write_text(
        '{"isSidechain": true, "message": {"id": "m2", "model": "claude-small-1", '
        '"usage": {"input_tokens": 200, "output_tokens": 100}}, "requestId": "r"}\n')
    (tmp_path / "w8" / "t" / "codex.jsonl").write_text('{"info": {"last_token_usage": {"output_tokens": 0, "input_tokens": 100}}}\n')
    (out / ".git/process-dispatch").mkdir()
    for issue in (7, 8):
        (out / f".git/process-dispatch/{issue}-x.json").write_text(
            json.dumps({"issue": issue, "worktree": str(tmp_path / f"w{issue}")}))
    (out / "docs/process/model-policy.local.json").write_text(json.dumps({"transcripts": "{worktree}/t/*.jsonl"}))
    r = models()
    assert r.returncode == 0, r.stdout + r.stderr
    rows = {line.split()[0]: line.split()[1:] for line in r.stdout.splitlines()
            if line.strip().startswith(("claude-", "model not"))}
    assert rows["claude-big-1"] == ["700", "64%", "100", "50%"], r.stdout
    assert rows["claude-small-1"] == ["300", "27%", "100", "50%"], r.stdout
    # a harness that records no model per message is named, never dropped silently
    assert rows["model"] == ["not", "recorded", "100", "9%", "0", "0%"], r.stdout
    assert "partial" not in r.stdout
    # a message whose first line names no model is still its model's; an unreadable
    # transcript marks the shares partial (refute v2.75 r3)
    (tmp_path / "w8" / "t" / "codex.jsonl").write_text(
        '{"message": {"id": "m3", "usage": {"input_tokens": 0, "output_tokens": 50}}, "requestId": "q"}\n'
        '{"message": {"id": "m3", "model": "claude-small-1", "usage": {"input_tokens": 0, "output_tokens": 50}},'
        ' "requestId": "q"}\n')
    (tmp_path / "w8" / "t" / "broken.jsonl").mkdir()
    r = models()
    rows = {line.split()[0]: line.split()[1:] for line in r.stdout.splitlines()
            if line.strip().startswith(("claude-", "model not"))}
    assert rows["claude-small-1"][0] == "350" and "model" not in rows, r.stdout
    assert "partial: 1 transcript(s) could not be read" in r.stdout


def test_cfr_flags_code_overlap_only(render, tmp_path):
    out = _render(render, tmp_path)
    env_git = ["git", "-C", str(out)]

    def git(date: str, *args):
        subprocess.run([*env_git, *args], check=True, capture_output=True,
                       env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
                            "PATH": __import__("os").environ["PATH"],
                            "GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date})

    subprocess.run([*env_git, "init", "-b", "main"], check=True, capture_output=True)
    (out / "app.py").write_text("x = 1\n")
    git("2026-06-01T00:00:00", "add", "-A")
    git("2026-06-01T00:00:00", "commit", "-m", "feat: add app")
    (out / "app.py").write_text("x = 2\n")
    git("2026-06-03T00:00:00", "add", "-A")
    git("2026-06-03T00:00:00", "commit", "-m", "fix: correct app")
    (out / "notes.md").write_text("doc\n")
    git("2026-06-04T00:00:00", "add", "-A")
    # no code files: not a deployable change
    git("2026-06-04T00:00:00", "commit", "-m", "feat: doc-only change")
    r = _kpis(out, "cfr")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "100.0% (1/1 feat changes" in r.stdout
    assert "DORA bands" in r.stdout
    assert "trend" in r.stdout  # proxy: never a single-value action


def test_report_end_to_end(render, tmp_path):
    out = _render(render, tmp_path)
    _journal(out, "GRADE work=42 checkpoint=1 criterion=AC-1 round=1 verdict=satisfied "
                  "action=satisfied source=execute\n")  # an old line is history, read by nothing
    r = _kpis(out, "report")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "convergence" not in r.stdout
    assert "[cost]" in r.stdout
    assert "[cfr]" in r.stdout


def test_share_prints_process_against_product_week_by_week(render, tmp_path):
    out = _render(render, tmp_path)
    for args in (["init", "-q", "-b", "main"], ["config", "user.email", "t@t"], ["config", "user.name", "t"],
                 ["add", "-A"], ["commit", "-q", "-m", "base"]):
        subprocess.run(["git", *args], cwd=out, check=True, capture_output=True)
    for i, rel in enumerate([".process-work/journal/a.md", ".process-work/journal/a.md", "src/x.py"]):
        p = out / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f"{i}\n")
        subprocess.run(["git", "add", "-A"], cwd=out, check=True)
        subprocess.run(["git", "commit", "-q", "-m", f"c{i}"], cwd=out, check=True)
    r = subprocess.run([sys.executable, str(out / "scripts/process/process_kpis.py"), "share", "--weeks", "2"],
                       cwd=out, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "week -0:    4 commits — process only  50%" in r.stdout, r.stdout
    assert "week -1:    0 commits" in r.stdout and "confidence: low" in r.stdout


# --- hygiene -----------------------------------------------------------------

def test_neutral_no_kenni_terms(render, tmp_path):
    out = _render(render, tmp_path)
    for rel in [
        "scripts/process/process_kpis.py",
        "docs/process/modules/telemetry.md",
        "docs/process/workflow.md",
    ]:
        text = (out / rel).read_text()
        for k in KENNI:
            assert k not in text, f"{k} leaked in {rel}"


def test_docdrift_green_with_module_doc(render, tmp_path):
    out = render(tmp_path, {"project_name": "d",
                            "modules": {"doc_drift_gate": True, "telemetry": True}})
    r = subprocess.run(
        [sys.executable, str(out / "scripts/process/check_doc_drift.py"), str(out)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stdout


def test_cfr_outside_git_diagnostic(render, tmp_path):
    out = _render(render, tmp_path)  # rendered repo is not a git repo
    r = _kpis(out, "cfr")
    assert r.returncode == 0, r.stderr
    assert "cfr skipped" in r.stdout
    assert "Traceback" not in r.stderr


# --- SP62: fix clusters (rule 6 across sessions) ---------------------------

def test_clusters_names_the_shared_token(render, tmp_path):
    out = _render(render, tmp_path)
    env_git = ["git", "-C", str(out)]

    def git(date: str, *args):
        subprocess.run([*env_git, *args], check=True, capture_output=True,
                       env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
                            "PATH": __import__("os").environ["PATH"],
                            "GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date})

    subprocess.run([*env_git, "init", "-b", "main"], check=True, capture_output=True)
    subjects = [
        "feat: add scope model",
        "fix(chat): inherit the working scope on rollover",
        "fix(chat): resolve the first turn in its conversation scope",
        "fix(router): carry a stated scope into the daily cut",
        "fix(ui): align the button",
    ]
    for i, s in enumerate(subjects):
        (out / "app.py").write_text(f"x = {i}\n")
        git(f"2026-06-0{i + 1}T00:00:00", "add", "-A")
        git(f"2026-06-0{i + 1}T00:00:00", "commit", "-m", s)
    r = _kpis(out, "clusters")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "'scope': 3 fix commits" in r.stdout
    assert "invariant record" in r.stdout          # the escalation advice
    assert "'align'" not in r.stdout               # singletons are not clusters


def test_clusters_quiet_when_no_cluster(render, tmp_path):
    out = _render(render, tmp_path)
    env_git = ["git", "-C", str(out)]
    subprocess.run([*env_git, "init", "-b", "main"], check=True, capture_output=True)
    (out / "app.py").write_text("x = 1\n")
    subprocess.run([*env_git, "add", "-A"], check=True, capture_output=True,
                   env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
                        "PATH": __import__("os").environ["PATH"]})
    subprocess.run([*env_git, "commit", "-m", "fix: one lonely fix"], check=True,
                   capture_output=True,
                   env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
                        "PATH": __import__("os").environ["PATH"]})
    r = _kpis(out, "clusters")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "nothing to escalate" in r.stdout


def test_clusters_file_dimension_catches_synonyms(render, tmp_path):
    """Fixes wording the same behaviour differently share no token — the
    code-file dimension still clusters them (language-independent)."""
    out = _render(render, tmp_path)
    env_git = ["git", "-C", str(out)]

    def git(date: str, *args):
        subprocess.run([*env_git, *args], check=True, capture_output=True,
                       env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
                            "PATH": __import__("os").environ["PATH"],
                            "GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date})

    subprocess.run([*env_git, "init", "-b", "main"], check=True, capture_output=True)
    subjects = [  # zero shared salient tokens
        "fix(chat): inherit the parent value",
        "fix(chat): honour yesterday's setting on rollover",
        "fix(router): default correctly on an empty first message",
    ]
    for i, s in enumerate(subjects):
        (out / "scoping.py").write_text(f"x = {i}\n")
        git(f"2026-06-0{i + 1}T00:00:00", "add", "-A")
        git(f"2026-06-0{i + 1}T00:00:00", "commit", "-m", s)
    r = _kpis(out, "clusters")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "file 'scoping.py': 3 fix commits" in r.stdout
    assert "hot files" in r.stdout  # the honesty caveat rides along


def test_clusters_blind_without_conventional_commits(render, tmp_path):
    out = _render(render, tmp_path)
    env_git = ["git", "-C", str(out)]
    e = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
         "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
         "PATH": __import__("os").environ["PATH"]}
    subprocess.run([*env_git, "init", "-b", "main"], check=True, capture_output=True)
    (out / "app.py").write_text("x = 1\n")
    subprocess.run([*env_git, "add", "-A"], check=True, capture_output=True, env=e)
    subprocess.run([*env_git, "commit", "-m", "repaired the scope thing"],
                   check=True, capture_output=True, env=e)
    r = _kpis(out, "clusters")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "blind, not green" in r.stdout


# --- rounds: rounds to pass and blockers by origin ---------------------------

def _review(work, rnd, verdict, tier=2):
    return (f"REVIEW work={work} tier={tier} reviewer=r model=m "
            f"independence=bundle,non-implementing verdict={verdict} round={rnd}\n")


ROUNDS_JOURNAL = (_review(9, 1, "block") + _review(9, 2, "block") + _review(9, 3, "pass")
                  + _review("widget", 1, "pass", tier=3))
ROUNDS_REPORT = ("review: widget-fix\nwork: #9\npublish-waived: test\n\n## Findings\n"
                 "FINDING sev=blocker action=fix issue=- origin=draft owner read twice\n"
                 "FINDING sev=blocker action=fix issue=- origin=fix guard re-broken\n"
                 "FINDING sev=blocker action=fix issue=- origin=fix guard re-broken again\n"
                 "FINDING sev=blocker action=fix issue=- no origin given\n"
                 "FINDING sev=major action=fix issue=- origin=late not a blocker\n"
                 "FINDING sev=blocker action=fix issue=- origin=bogus refused, not counted\n"
                 "```\nFINDING sev=blocker action=fix issue=- origin=late quoted, not counted\n```\n")


def _rounds(out: Path):
    r = subprocess.run([sys.executable, str(out / "scripts/process/process_kpis.py"), "rounds"],
                       cwd=out, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout


def test_rounds_counts_rounds_to_pass_and_blockers_by_origin(render, tmp_path):
    """Tier-3 features took 3-7 rounds downstream and nobody could say whether the blockers
    came from the draft or from the fixes — `rounds` reads it from REVIEW and FINDING lines."""
    out = _render(render, tmp_path, github_issues=True)
    _journal(out, ROUNDS_JOURNAL)
    reviews = out / ".process-work/reviews"
    reviews.mkdir(parents=True)
    (reviews / "2026-07-05-widget-fix.md").write_text(ROUNDS_REPORT, encoding="utf-8")
    text = _rounds(out)
    row = next(ln for ln in text.splitlines() if ln.split()[:1] == ["9"])
    # tier 2, passed in round 3, two blocked rounds, four blockers: draft 1, fix 2, one unmarked
    assert row.split()[1:4] == ["2", "3", "2"], row
    assert row.endswith("4 (draft 1, fix 2, unmarked 1)"), row
    other = next(ln for ln in text.splitlines() if ln.split()[:1] == ["widget"])
    assert other.split()[1:5] == ["3", "1", "0", "0"], other
    assert "all blockers: 4 (draft 1, fix 2, unmarked 1)" in text
    assert "confidence: low" in text
    doc = (out / "docs/process/modules/telemetry.md").read_text()
    assert "| `rounds` |" in doc and "origin=draft" in doc


PLAN_ROUND_REPORT = ("review: widget-plan\nwork: #9\nphase: plan\npublish-waived: test\n\n## Findings\n"
                     "FINDING sev=blocker action=fix issue=- kind=knowledge-gap reinvents the note reader\n"
                     "FINDING sev=blocker action=fix issue=- kind=knowledge-gap second one\n"
                     "FINDING sev=blocker action=fix issue=- kind=requirement unclear AC\n"
                     "FINDING sev=blocker action=fix issue=- no kind on a plan blocker\n")
CODE_ROUND_REPORT = ("review: widget-code\nwork: #9\npublish-waived: test\n\n## Findings\n"
                     "FINDING sev=blocker action=fix issue=- kind=implementation off by one\n"
                     "FINDING sev=blocker action=fix issue=- kind=knowledge-gap used the old helper\n"
                     "FINDING sev=major action=fix issue=- kind=test-gap not a blocker\n")


def test_rounds_counts_blockers_by_kind_plan_reviews_apart_from_code_reviews(render, tmp_path):
    """The weekly question is whether blockers are knowledge gaps, and whether plan reviews
    catch them before code does: one plan report (`phase: plan`) and one code report."""
    out = _render(render, tmp_path, github_issues=True)
    _journal(out, ROUNDS_JOURNAL)
    reviews = out / ".process-work/reviews"
    reviews.mkdir(parents=True)
    (reviews / "2026-07-04-widget-plan.md").write_text(PLAN_ROUND_REPORT, encoding="utf-8")
    (reviews / "2026-07-05-widget-code.md").write_text(CODE_ROUND_REPORT, encoding="utf-8")
    text = _rounds(out)
    line = next(ln for ln in text.splitlines() if "blockers by kind" in ln)
    assert line.strip() == ("blockers by kind — plan reviews: knowledge-gap 2, requirement 1, - 1; "
                            "code reviews: implementation 1, knowledge-gap 1"), line
    # the origin split is unchanged: all six blockers, none carries origin=
    assert "all blockers: 6" in text
    # a report of a work item without REVIEW lines counts in neither total
    (reviews / "2026-07-06-stray.md").write_text(
        "work: 999\n\nFINDING sev=blocker action=fix issue=- gate=judgement kind=process stray\n",
        encoding="utf-8")
    assert next(ln for ln in _rounds(out).splitlines() if "blockers by kind" in ln) == line


def test_rounds_counts_blockers_by_reviewer(render, tmp_path):
    """#247: which reviewer raised the blockers — the second opinion's share, counted."""
    out = _render(render, tmp_path, github_issues=True)
    _journal(out, ROUNDS_JOURNAL)
    reviews = out / ".process-work/reviews"
    reviews.mkdir(parents=True)
    (reviews / "2026-07-05-widget-code.md").write_text(
        "review: widget-code\nwork: #9\npublish-waived: test\n\n## Findings\n"
        "FINDING sev=blocker action=fix issue=- by=codex guard read twice\n"
        "FINDING sev=blocker action=fix issue=- by=codex owner bypassed\n"
        "FINDING sev=blocker action=fix issue=- by=claude missing test\n"
        "FINDING sev=blocker action=fix issue=- unattributed\n"
        "FINDING sev=major action=fix issue=- by=claude not a blocker\n", encoding="utf-8")
    line = next(ln for ln in _rounds(out).splitlines() if "blockers by reviewer" in ln)
    assert line.strip() == "blockers by reviewer: claude 1, codex 2, - 1", line


def test_rounds_by_kind_without_any_kind_reads_zero(render, tmp_path):
    out = _render(render, tmp_path, github_issues=True)
    _journal(out, ROUNDS_JOURNAL)
    text = _rounds(out)
    assert "blockers by kind — plan reviews: 0; code reviews: 0" in text


def test_rounds_without_the_finding_reader_says_blockers_not_read(render, tmp_path):
    """Without check_issues the FINDING lines are not read — the column says so instead
    of reading as zero blockers (a missing input must not read as the OK state)."""
    out = _render(render, tmp_path)
    _journal(out, _review(9, 1, "block") + _review(9, 2, "block"))
    text = _rounds(out)
    row = next(ln for ln in text.splitlines() if ln.split()[:1] == ["9"])
    assert row.split()[1:4] == ["2", "open", "2"] and row.endswith("not read"), row
    assert "blockers: not read (FINDING lines are read by check_issues — the github-issues module)" in text
    assert "blockers by kind" not in text


def test_rounds_names_a_missing_dependency_of_an_installed_finding_reader(render, tmp_path, monkeypatch,
                                                                          capsys):
    """#169: check_issues installed but PyYAML missing read as "module not there"."""
    import importlib.util
    out = _render(render, tmp_path, github_issues=True)
    _journal(out, _review(9, 1, "block"))
    monkeypatch.setattr(sys, "path", list(sys.path))
    for name in ("check_issues", "check_review"):
        monkeypatch.delitem(sys.modules, name, raising=False)
    monkeypatch.setitem(sys.modules, "yaml", None)  # `import yaml` raises ModuleNotFoundError
    monkeypatch.setattr(sys, "dont_write_bytecode", True)
    spec = importlib.util.spec_from_file_location("kpis_169", out / "scripts/process/process_kpis.py")
    kpis = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(kpis)
    why = kpis._blockers_by_work(out)
    assert why == "check_issues needs yaml — run with it installed (e.g. uv run --with pyyaml …)", why
    assert kpis.rounds(out) == 0
    assert "blockers: not read (check_issues needs yaml" in capsys.readouterr().out
    head = (out / "scripts/process/process_kpis.py").read_text(encoding="utf-8").split('"""', 1)[0]
    assert "# /// script" in head and "pyyaml" in head


# --- flow: one issue from planning to deploy and follow-up (optimization.md) ----

def _flow_repo(render, tmp_path):
    import json
    out = _render(render, tmp_path)
    ans = out / ".copier-answers.yml"
    ans.write_text("_commit: v9.9.9\n" + ans.read_text())

    def git(*a, env=None):
        import os
        return subprocess.run(["git", *a], cwd=out, capture_output=True, text=True, check=True,
                              env={**os.environ, **(env or {})})
    git("init", "-q", "-b", "main")
    git("config", "user.email", "t@t")
    git("config", "user.name", "t")
    plans = out / ".process-work/plans/archive"
    plans.mkdir(parents=True, exist_ok=True)
    (plans / "2026-10-01-faster.md").write_text(
        "# Plan\n\nissue: #12\ntier: 2\n\n## Decisions\n\n"
        "- DECISION 2026-10-01 owner: keep the old API — because clients\n"
        "- DECISION 2026-10-01 steward: run it first — because ready\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "base", env={"GIT_COMMITTER_DATE": "2026-09-30T00:00:00+00:00",
                                         "GIT_AUTHOR_DATE": "2026-09-30T00:00:00+00:00"})
    # a later fix that names its origin, and one outside the follow-up window
    for day, body in (("2026-10-05", "fix: crash\n\nRegression-of: #12"),
                      ("2026-12-30", "fix: late\n\nRegression-of: #12")):
        (out / f"src-{day}.txt").write_text("x\n")
        git("add", "-A")
        git("commit", "-q", "-m", body, env={"GIT_COMMITTER_DATE": f"{day}T12:00:00+00:00",
                                             "GIT_AUTHOR_DATE": f"{day}T12:00:00+00:00"})
    common = out / ".git"
    d = common / "process-dispatch"
    d.mkdir()
    for phase, stamp in (("plan", "20261001-100000"), ("execute", "20261001-120000"),
                         ("review", "20261001-160000")):
        (d / f"12-faster-{phase}-{stamp}.log").write_text("")
    tower = common / "process-tower"
    tower.mkdir()
    reports = [("2026-10-01T11:00:00", "planned"), ("2026-10-01T15:00:00", "pushed"),
               ("2026-10-01T17:00:00", "review-pass"), ("2026-10-02T09:00:00", "done")]
    import time
    off = time.strftime("%z")
    (tower / "reports.jsonl").write_text("".join(
        json.dumps({"ts": ts + off, "host": "h", "worker": "12-faster", "branch": "12-faster",
                    "issue": 12, "state": st, "note": "", "cwd": ""}) + "\n" for ts, st in reports))
    train = common / "process-train"
    train.mkdir()
    import datetime as dt
    ended = dt.datetime(2026, 10, 2, 9, 30).astimezone().isoformat()
    (train / "phases.jsonl").write_text(json.dumps(
        {"stamp": "s", "result": "green", "aboard": 1, "branches": ["12-faster"], "deployed": True,
         "ended": ended}) + "\n")
    return out


def _flow_module(out):
    import importlib.util
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(out / "scripts/process"))
    spec = importlib.util.spec_from_file_location("kpis_flow_under_test", out / "scripts/process/process_kpis.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_flow_traces_one_issue_from_planning_to_deploy_and_follow_up(render, tmp_path):
    from datetime import datetime, timezone
    out = _flow_repo(render, tmp_path)
    m = _flow_module(out)
    [it] = m.flow_items(out, issue=12, now=datetime(2026, 12, 31, tzinfo=timezone.utc))
    assert it["start"]["quality"] == "measured" and it["deployed"]["quality"] == "measured"
    # 10:00 first phase → 09:30 next day deploy
    assert it["lead_s"] == {"value": 23.5 * 3600, "quality": "measured", "endpoint": "deploy"}
    # work: plan 1 h + execute 3 h + review 1 h; the rest waited
    assert it["work_s"]["value"] == 5 * 3600 and it["wait_s"]["value"] == 18.5 * 3600
    assert it["owner_decisions"]["value"] == 1  # the steward's line is no owner effort
    assert it["escapes"]["value"] == 1 and it["escapes"]["window_open"] is False  # the late fix is outside 30 d
    assert it["process_version"]["value"] == "v9.9.9"
    assert it["tokens"]["quality"] == "missing"  # no transcripts glob: never a zero


def test_flow_says_what_is_missing_instead_of_guessing(render, tmp_path):
    out = _flow_repo(render, tmp_path)
    (out / ".git/process-train/phases.jsonl").unlink()
    (out / ".git/process-tower/reports.jsonl").write_text("")
    m = _flow_module(out)
    [it] = m.flow_items(out, issue=12)
    assert it["merged"]["quality"] == "missing" and it["deployed"]["quality"] == "missing"
    assert it["lead_s"] == {"value": None, "quality": "missing", "endpoint": "merge"}
    # phases started, none reported an end: working time unknown, not zero
    assert it["work_s"] == {"value": None, "quality": "missing"}
    assert it["escapes"]["value"] is None


def test_flow_cli_prints_the_issue_and_the_honest_ceiling(render, tmp_path):
    out = _flow_repo(render, tmp_path)
    r = subprocess.run([sys.executable, str(out / "scripts/process/process_kpis.py"), "flow"],
                       cwd=out, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "#12: lead 23.5 h to deploy [measured] (work 5.0 h, wait 18.5 h)" in r.stdout, r.stdout
    assert "recovery time: not measured" in r.stdout and "confidence: low" in r.stdout
    j = subprocess.run([sys.executable, str(out / "scripts/process/process_kpis.py"), "flow", "--json",
                        "--issue", "12"], cwd=out, capture_output=True, text=True)
    import json
    assert json.loads(j.stdout)[0]["issue"] == 12


# --- refute of v2.67.0: attribution, overlap, malformed rows, time zones -------

def _report(out, ts, state, worker, issue):
    import json
    import time
    with (out / ".git/process-tower/reports.jsonl").open("a") as fh:
        fh.write(json.dumps({"ts": ts + time.strftime("%z"), "host": "h", "worker": worker, "branch": worker,
                             "issue": issue, "state": state, "note": "", "cwd": ""}) + "\n")


def test_flow_does_not_file_a_regression_fix_under_its_origin(render, tmp_path):
    from datetime import datetime, timezone
    out = _flow_repo(render, tmp_path)
    (out / ".git/process-dispatch/20-fix-execute-20261004-100000.log").write_text("")
    _report(out, "2026-10-04T11:00:00", "pushed", "20-fix", 20)
    _report(out, "2026-10-05T12:00:00", "done", "20-fix", 12)  # the train's refs[0] of `Regression-of: #12`
    m = _flow_module(out)
    items = {it["issue"]: it for it in m.flow_items(out, now=datetime(2026, 12, 31, tzinfo=timezone.utc))}
    assert items[12]["branches"] == ["12-faster"]
    assert items[12]["lead_s"]["value"] == 23.5 * 3600 and items[12]["escapes"]["value"] == 1
    assert items[20]["merged"]["quality"] == "measured"


def test_flow_counts_a_re_dispatched_phase_once(render, tmp_path):
    out = _flow_repo(render, tmp_path)
    (out / ".git/process-dispatch/12-faster-execute-20261001-130000.log").write_text("")
    [it] = _flow_module(out).flow_items(out, issue=12)
    assert it["work_s"]["value"] == 5 * 3600  # 12:00–15:00 and 13:00–15:00 are one interval


def test_flow_keeps_a_reused_branch_names_issues_apart(render, tmp_path):
    out = _flow_repo(render, tmp_path)
    _report(out, "2026-10-08T10:00:00", "planned", "12-faster", 30)
    _report(out, "2026-10-09T10:00:00", "done", "12-faster", 30)
    [it] = _flow_module(out).flow_items(out, issue=12)
    assert it["merged"]["value"].day == 2  # the first merge after the issue began
    assert it["lead_s"]["quality"] == "estimated"  # a shared name is an estimate, said so


def test_flow_survives_malformed_rows_and_empty_transcripts(render, tmp_path):
    import json
    out = _flow_repo(render, tmp_path)
    with (out / ".git/process-train/phases.jsonl").open("a") as fh:
        fh.write(json.dumps({"stamp": "x", "branches": 5, "ended": "nope"}) + "\n")
    m = _flow_module(out)
    [it] = m.flow_items(out, issue=12)
    assert it["deployed"]["quality"] == "measured"
    wt = tmp_path / "wt"
    (wt / "t").mkdir(parents=True)
    (wt / "t" / "a.jsonl").write_text('{"type": "user"}\n')
    (out / ".git/process-dispatch/12-faster.json").write_text(json.dumps({"issue": 12, "worktree": str(wt)}))
    (out / "docs/process/model-policy.local.json").write_text(json.dumps({"transcripts": "{worktree}/t/*.jsonl"}))
    [it] = m.flow_items(out, issue=12)
    assert it["tokens"]["quality"] == "missing"  # a transcript without usage is no measurement


def test_flow_reads_naive_dispatch_stamps_as_local_time(render, tmp_path, monkeypatch):
    import time
    monkeypatch.setenv("TZ", "America/New_York")
    time.tzset()
    try:
        out = _flow_repo(render, tmp_path)
        [it] = _flow_module(out).flow_items(out, issue=12)
        assert it["lead_s"]["value"] == 23.5 * 3600 and it["work_s"]["value"] == 5 * 3600
    finally:
        monkeypatch.delenv("TZ")
        time.tzset()


def test_flow_gives_a_reused_name_its_own_window_and_says_it_is_estimated(render, tmp_path):
    out = _flow_repo(render, tmp_path)
    _report(out, "2026-10-08T10:00:00", "planned", "12-faster", 30)
    _report(out, "2026-10-09T10:00:00", "done", "12-faster", 30)
    items = {it["issue"]: it for it in _flow_module(out).flow_items(out)}
    later = items[30]
    assert later["start"]["value"].day == 8 and later["merged"]["value"].day == 9
    assert {later[k]["quality"] for k in ("start", "merged")} == {"estimated"}
    assert later["deployed"]["quality"] != "measured"  # issue 12's deploy is not issue 30's


def test_flow_finds_an_issue_known_only_from_the_trains_merge(render, tmp_path):
    out = _flow_repo(render, tmp_path)
    _report(out, "2026-10-06T10:00:00", "done", "40-thing", None)
    items = {it["issue"]: it for it in _flow_module(out).flow_items(out)}
    assert items[40]["branches"] == ["40-thing"] and items[40]["merged"]["quality"] == "measured"


def test_one_grammar_for_the_regression_trailer(render, tmp_path):
    out = _render(render, tmp_path)
    sys.path.insert(0, str(out / "scripts/process"))
    import importlib.util
    spec = importlib.util.spec_from_file_location("pg_t", out / "scripts/process/process_git.py")
    pg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pg)
    assert pg.regression_refs("fix: x\n\nRegression-of: #12, acme/app#7\nregression-of:#3") == [12, 7, 3]
    assert pg.regression_refs("Regression-of: #12 (reported in #20)") == []  # not a trailer: counts nowhere
    # the train strips every trailer-key line, well-formed or not; only well-formed ones count as escapes
    assert pg.REGRESSION_LINE.sub("", "a #20\nRegression-of: #12.\n") == "a #20\n\n"


def test_flow_says_which_endpoint_and_how_complete_the_tokens_are(render, tmp_path):
    import json
    out = _flow_repo(render, tmp_path)
    rows = (out / ".git/process-train/phases.jsonl")
    row = json.loads(rows.read_text())
    row["deployed"] = False
    rows.write_text(json.dumps(row) + "\n")
    m = _flow_module(out)
    [it] = m.flow_items(out, issue=12)
    assert it["deployed"]["quality"] == "failed"
    assert it["lead_s"]["endpoint"] == "merge" and it["lead_s"]["quality"] == "estimated"
    assert it["escapes"]["from"] == "merge" and it["escapes"]["quality"] == "estimated"
    wt = tmp_path / "wt"
    (wt / "t").mkdir(parents=True)
    (wt / "t" / "a.jsonl").write_text('{"usage": {"input_tokens": 100, "output_tokens": 10}}\n')
    (wt / "t" / "b.jsonl").write_text('{"usage": {"output_tokens": 50}}\n')
    (out / ".git/process-dispatch/12-faster.json").write_text(json.dumps({"issue": 12, "worktree": str(wt)}))
    (out / "docs/process/model-policy.local.json").write_text(json.dumps({"transcripts": "{worktree}/t/*.jsonl"}))
    [it] = m.flow_items(out, issue=12)
    assert it["tokens"]["coverage"] == {"input_tokens": 1, "output_tokens": 2}
    assert it["tokens"]["quality"] == "estimated"  # input is a partial sum over two sessions
    # the same two calls in one transcript: the second call's input is still unknown
    # (refutation round 2, executed) — completeness is per usage event, not per file
    (wt / "t" / "b.jsonl").unlink()
    (wt / "t" / "a.jsonl").write_text('{"usage": {"input_tokens": 100, "output_tokens": 10}}\n'
                                      '{"usage": {"output_tokens": 50}}\n')
    [it] = m.flow_items(out, issue=12)
    assert it["tokens"]["value"] == {"input_tokens": 100, "output_tokens": 60}
    assert it["tokens"]["coverage"] == {"input_tokens": 1, "output_tokens": 2}
    assert it["tokens"]["events"] == 2 and it["tokens"]["sessions"] == 1
    assert it["tokens"]["quality"] == "estimated"
    # every call complete: measured; a non-JSON line with token fields covers nothing
    (wt / "t" / "a.jsonl").write_text('{"usage": {"input_tokens": 100, "output_tokens": 10}}\n'
                                      '{"usage": {"input_tokens": 7, "output_tokens": 50}}\n')
    [it] = m.flow_items(out, issue=12)
    assert it["tokens"]["quality"] == "measured"
    with (wt / "t" / "a.jsonl").open("a") as fh:
        fh.write('garbled "input_tokens": 3, "output_tokens": 4\n')
    [it] = m.flow_items(out, issue=12)
    assert it["tokens"]["value"] == {"input_tokens": 110, "output_tokens": 64}
    assert it["tokens"]["quality"] == "estimated"
    # Claude Code repeats a message's usage on each content-block line: one message counts once
    (wt / "t" / "a.jsonl").write_text(
        '{"message": {"id": "m1", "usage": {"input_tokens": 5, "output_tokens": 9}}, "requestId": "r1"}\n'
        '{"message": {"id": "m1", "usage": {"input_tokens": 5, "output_tokens": 9}}, "requestId": "r1"}\n'
        '{"message": {"id": "m2", "usage": {"input_tokens": 1, "output_tokens": 2}}, "requestId": "r2"}\n')
    [it] = m.flow_items(out, issue=12)
    assert it["tokens"]["value"] == {"input_tokens": 6, "output_tokens": 11} and it["tokens"]["events"] == 2
    # a streamed message's interim count is not its final one; a running total never adds up again
    (wt / "t" / "a.jsonl").write_text(
        '{"message": {"id": "m1", "usage": {"input_tokens": 5, "output_tokens": 1}}, "requestId": "r1"}\n'
        '{"message": {"id": "m1", "usage": {"input_tokens": 5, "output_tokens": 9}}, "requestId": "r1"}\n'
        '{"info": {"last_token_usage": {"input_tokens": 3, "output_tokens": 4}, '
        '"total_token_usage": {"input_tokens": 300, "output_tokens": 400}}}\n')
    [it] = m.flow_items(out, issue=12)
    assert it["tokens"]["value"] == {"input_tokens": 8, "output_tokens": 13}
    # only opaque lines: no field coverage at all is still not complete (refutation, round 3)
    (wt / "t" / "a.jsonl").write_text('garbled "input_tokens": 3, "output_tokens": 4\n')
    [it] = m.flow_items(out, issue=12)
    assert it["tokens"]["coverage"] == {} and it["tokens"]["unknown_sources"] == 1
    assert it["tokens"]["quality"] == "estimated"
    # a matched transcript that cannot be read leaves the readable total partial
    (wt / "t" / "a.jsonl").write_text('{"usage": {"input_tokens": 7, "output_tokens": 50}}\n')
    (wt / "t" / "b.jsonl").mkdir()  # matches the glob, cannot be read as a file
    [it] = m.flow_items(out, issue=12)
    assert it["tokens"]["sessions"] == 2 and it["tokens"]["unknown_sources"] == 1
    assert it["tokens"]["quality"] == "estimated"


def test_losses_keeps_four_measures_apart_and_never_fills_in(render, tmp_path):
    from datetime import datetime, timezone
    out = _flow_repo(render, tmp_path)
    m = _flow_module(out)
    now = datetime(2026, 12, 31, tzinfo=timezone.utc)
    t = m.losses_table(out, days=3650, now=now)
    assert t["issues"] == 1
    assert t["occupancy"] == {"value": 5.0, "unit": "h", "issues": 1, "missing": 0, "quality": "measured"}
    assert t["delay"]["value"] == 18.5 and t["delay"]["unit"] == "issue-h"
    assert t["owner_effort"] == {"decisions": 1, "minutes": None, "quality": "proxy"}
    assert t["tokens"] == {"value": None, "issues": 0, "missing": 1, "quality": "missing"}  # never a zero
    assert t["proxies"]["regression_fixes"] == 1
    assert "total" not in t and "sum" not in t  # the four are never added up
    # outside the window: nothing to report, not zeros
    assert m.losses_table(out, days=1, now=now)["issues"] == 0
    # an issue in flight (no phase reported an end) is missing, never zero hours
    (out / ".git/process-tower/reports.jsonl").write_text("")
    est = m.losses_table(out, days=3650, now=now)
    assert est["occupancy"] == {"value": None, "unit": "h", "issues": 0, "missing": 1, "quality": "missing"}
    assert est["delay"]["value"] is None and est["delay"]["missing"] == 1


def test_losses_cli_prints_each_measure_with_its_quality(render, tmp_path):
    out = _flow_repo(render, tmp_path)
    cli = [sys.executable, str(out / "scripts/process/process_kpis.py"), "losses", "--days", "3650"]
    r = subprocess.run(cli, cwd=out, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "four measures, never summed" in r.stdout
    assert "occupancy   5.0 h [measured" in r.stdout and "delay       18.5 issue-h" in r.stdout
    assert "tokens      not measured [missing" in r.stdout


def _issue(n, title, state="OPEN", labels=(), created="2026-01-05T10:00:00Z", closed=None, subs=()):
    return {"number": n, "title": title, "state": state, "createdAt": created, "closedAt": closed,
            "labels": list(labels), "sub_total": len(subs),
            "sub_done": sum(1 for c in subs if c["state"] == "CLOSED"), "subs": list(subs)}


def test_outcomes_measures_epics_to_usable_and_bug_origin_on_two_axes(render, tmp_path):
    import json
    from datetime import datetime, timezone
    out = _flow_repo(render, tmp_path)
    m = _flow_module(out)
    now = datetime(2026, 12, 31, tzinfo=timezone.utc)
    accept = _issue(12, "Acceptance run", "CLOSED", ["acceptance"], closed="2026-11-30T00:00:00Z")
    issues = [
        _issue(100, "[EPIC] Documents", subs=[accept, _issue(13, "part", "CLOSED", closed="2026-02-01T00:00:00Z")]),
        _issue(101, "Feature with children", subs=[_issue(14, "part")]),
        _issue(102, "[EPIC] Later", subs=[_issue(15, "Acceptance", labels=["acceptance"])]),
        _issue(200, "crash after #12", "CLOSED", ["bug", "cause:regression", "channel:operator", "priority:high"],
               created="2026-12-01T00:00:00Z", closed="2026-12-03T00:00:00Z"),
        _issue(201, "old flaw", labels=["bug", "cause:preexisting", "channel:agent"], created="2026-12-02T00:00:00Z"),
        _issue(202, "no origin", labels=["bug"], created="2026-12-02T00:00:00Z"),
    ]
    (out / "docs/process/optimization.local.json").write_text(
        json.dumps({"outcomes": {"usable": "label:acceptance"}}), encoding="utf-8")
    t = m.outcomes_table(out, days=3650, now=now, fetch=lambda _root: (issues, None))
    ep = {e["number"]: e for e in t["epics"]}
    assert set(ep) == {100, 101, 102}  # native sub-issues or the title prefix
    assert ep[100]["quality"] == "measured" and ep[100]["usable_at"] is not None  # #12 deployed in the flow
    assert ep[101]["quality"] == "missing"  # no acceptance sub-issue: the marker says nothing
    assert ep[102]["quality"] == "open" and ep[102]["usable_at"] is None
    assert t["o1_epic_usable"]["n"] == 1 and t["o1_epic_usable"]["quality"] == "measured"
    bo = t["bug_origin"]
    assert bo["bugs"] == 3 and bo["with_cause"] == 2 and bo["with_channel"] == 2
    assert bo["coverage"] == 0.67 and bo["blind_spot"] is True
    # the owner-reported regression counts in the regression share and in O2
    assert bo["regression_share"] == 0.5 and bo["quality"] == "estimated"
    assert t["o2_disruptive_fixed"] == {"median_days": 2.0, "n": 1, "quality": "proxy", "open": 0}


def test_outcomes_default_marker_is_a_proxy_and_no_gh_is_unavailable(render, tmp_path):
    from datetime import datetime, timezone
    out = _flow_repo(render, tmp_path)
    m = _flow_module(out)
    now = datetime(2026, 12, 31, tzinfo=timezone.utc)
    epic = _issue(100, "[EPIC] Done", "CLOSED", closed="2026-03-01T00:00:00Z")
    t = m.outcomes_table(out, days=3650, now=now, fetch=lambda _root: ([epic], None))
    assert t["epics"][0]["quality"] == "proxy" and t["epics"][0]["days_to_usable"] == 54.58
    assert t["bug_origin"]["coverage"] is None and t["bug_origin"]["blind_spot"] is False
    gone = m.outcomes_table(out, now=now, fetch=lambda _root: (None, "gh is not installed"))
    assert gone == {"available": False, "reason": "gh is not installed", "days": 90}
    # a duplicate or not-planned closure is no delivery; an epic grouped after its work is not negative
    dropped = dict(epic, stateReason="NOT_PLANNED")
    bug = _issue(200, "dup", "CLOSED", ["bug", "cause:unknown", "channel:operator", "priority:high"],
                 created="2026-12-01T00:00:00Z", closed="2026-12-01T01:00:00Z")
    bug["stateReason"] = "DUPLICATE"
    late = _issue(101, "[EPIC] grouped later", "CLOSED", created="2026-05-01T00:00:00Z",
                  closed="2026-04-01T00:00:00Z")
    t = m.outcomes_table(out, days=3650, now=now, fetch=lambda _root: ([dropped, bug, late], None))
    ep = {e["number"]: e for e in t["epics"]}
    assert ep[100]["usable_at"] is None and ep[100]["quality"] == "open"
    assert ep[101]["days_to_usable"] == 0.0
    assert t["o2_disruptive_fixed"]["n"] == 0 and t["o2_disruptive_fixed"]["open"] == 1


def test_outcomes_names_a_mistyped_mandate_instead_of_matching_letters(render, tmp_path):
    import json
    from datetime import datetime, timezone
    out = _flow_repo(render, tmp_path)
    m = _flow_module(out)
    (out / "docs/process/optimization.local.json").write_text(json.dumps({"outcomes": {
        "bug_labels": "bug", "epic_title_prefix": None, "coverage_target": "high", "colour": "red"}}))
    bugs = [_issue(1, "b", labels=["b"], created="2026-12-01T00:00:00Z"),
            _issue(2, "real", labels=["bug"], created="2026-12-01T00:00:00Z")]
    t = m.outcomes_table(out, days=3650, now=datetime(2026, 12, 31, tzinfo=timezone.utc),
                         fetch=lambda _root: (bugs, None))
    assert t["bug_origin"]["bugs"] == 1  # the default `bug`, not the letters b, u, g
    assert t["config"]["coverage_target"] == 0.8
    assert len(t["config_problems"]) == 4 and any("colour" in p for p in t["config_problems"])


def test_gh_issues_reads_the_graphql_answer_through_gh(render, tmp_path, monkeypatch):
    import json
    import os
    out = _flow_repo(render, tmp_path)
    m = _flow_module(out)
    fake = tmp_path / "fakebin"
    fake.mkdir()
    answer = {"data": {"repository": {"issues": {"nodes": [{
        "number": 7, "title": "[EPIC] x", "state": "CLOSED", "stateReason": "COMPLETED",
        "createdAt": "2026-01-01T00:00:00Z", "closedAt": "2026-02-01T00:00:00Z",
        "labels": {"nodes": [{"name": "type:epic"}]}, "subIssuesSummary": {"total": 1, "completed": 1},
        "subIssues": {"nodes": [{"number": 8, "title": "acc", "state": "CLOSED", "stateReason": None,
                                 "closedAt": "2026-01-20T00:00:00Z", "labels": {"nodes": []}}]}}]}}}}
    (tmp_path / "answer.json").write_text(json.dumps(answer))
    (fake / "gh").write_text(
        f"#!{sys.executable}\nimport sys, pathlib\n"
        f"pathlib.Path({str(tmp_path / 'args.txt')!r}).open('a').write(' '.join(sys.argv[1:]) + '\\n')\n"
        "if sys.argv[1] == 'repo': print('o/2048')\n"
        f"else: print(pathlib.Path({str(tmp_path / 'answer.json')!r}).read_text())\n")
    (fake / "gh").chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake}{os.pathsep}{os.environ['PATH']}")
    issues, why = m._gh_issues(out)
    assert why is None and issues[0]["number"] == 7 and issues[0]["sub_total"] == 1
    assert issues[0]["subs"][0]["number"] == 8 and issues[0]["labels"] == ["type:epic"]
    args = (tmp_path / "args.txt").read_text()
    assert "-f owner=o -f name=2048" in args  # -f: a numeric repo name stays a string
    assert "stateReason" in args


def test_outcomes_cli_text_names_the_blind_spot_or_says_unavailable(render, tmp_path, capsys):
    out = _flow_repo(render, tmp_path)
    m = _flow_module(out)
    m._gh_issues = lambda _root: (None, "gh is not installed")
    assert m.outcomes(out) == 0
    assert "unavailable: gh is not installed — outcomes skipped (not zero)" in capsys.readouterr().out
    m._gh_issues = lambda _root: ([_issue(202, "no origin", labels=["bug"], created="2099-01-01T00:00:00Z")], None)
    assert m.outcomes(out) == 0
    text = capsys.readouterr().out
    assert "1 bug(s), cause and channel on 0% (target 80%) — blind spot" in text


def test_flow_ends_at_the_merge_by_design_when_the_mandate_has_no_deploy(render, tmp_path):
    import json
    out = _flow_repo(render, tmp_path)
    (out / ".git/process-train/phases.jsonl").unlink()  # merged without the train
    m = _flow_module(out)
    [it] = m.flow_items(out, issue=12)
    before = it["lead_s"]["quality"]
    (out / "docs/process/optimization.local.json").write_text(json.dumps({"deploy": False}))
    [it] = m.flow_items(out, issue=12)
    assert it["deployed"]["quality"] == "not configured"
    if it["merged"]["value"] is not None:
        assert it["lead_s"]["endpoint"] == "merge"
        assert before == "estimated" and it["lead_s"]["quality"] == "measured"


def test_flow_carries_the_last_plan_drift_verdict_per_issue(render, tmp_path):
    import json
    out = _flow_repo(render, tmp_path)
    m = _flow_module(out)
    [it] = m.flow_items(out, issue=12)
    assert it["plan_drift"] == {"value": None, "quality": "missing"}
    rows = [{"ts": "2026-10-01T11:59:00+00:00", "gate": "plan-drift", "mode": "shadow", "outcome": "fail",
             "duration_s": 0.1, "issue": 12, "plans": [{"behind": 900, "touching": 40}, {"behind": 3, "touching": 1}]},
            {"ts": "2026-10-01T12:30:00+00:00", "gate": "plan-drift", "mode": "shadow", "outcome": "skipped",
             "duration_s": 0.1, "issue": 12, "plans": []},
            {"ts": "2026-10-01T12:40:00+00:00", "gate": "plan-drift", "mode": "shadow", "outcome": "pass",
             "duration_s": 0.1, "issue": 13, "plans": [{"behind": 1, "touching": 0}]}]
    (out / ".git/process-gate-events.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    [it] = m.flow_items(out, issue=12)
    assert it["plan_drift"] == {"value": {"behind": 900, "touching": 40, "outcome": "fail", "mode": "shadow"},
                                "quality": "measured"}  # a skipped run is no verdict


FINDINGS_REPORTS = {
    "a.md": ("review: a\nwork: #1\npublish-waived: test\n\n"
             "FINDING sev=blocker action=fix issue=- class=testable rule=mutation weak assert\n"
             "FINDING sev=minor action=fix issue=- class=judgment naming\n"
             "FINDING sev=major action=fix issue=- no class yet\n"),
    "b.md": ("review: b\nwork: #2\npublish-waived: test\n\n"
             "FINDING sev=major action=fix issue=- class=testable rule=mutation another weak assert\n"
             "FINDING sev=blocker action=fix issue=- class=judgment design call\n"),
}


def test_findings_counts_classes_and_names_a_repeating_check(render, tmp_path):
    """#276: what could have caught each finding, counted, and a check seen in two
    works named as the next gate to write."""
    out = _render(render, tmp_path, github_issues=True)
    reviews = out / ".process-work/reviews"
    reviews.mkdir(parents=True)
    for name, text in FINDINGS_REPORTS.items():
        (reviews / name).write_text(text, encoding="utf-8")
    r = subprocess.run([sys.executable, str(out / "scripts/process/process_kpis.py"), "findings", "--json"],
                       cwd=out, capture_output=True, text=True)
    got = json.loads(r.stdout)
    assert got["classes"] == {"testable": 2, "judgment": 2, "unclassed": 1}, got
    assert got["blocking"] == {"testable": 2, "judgment": 1, "unclassed": 1}, got
    assert got["repeating"] == {"testable:mutation": ["1", "2"]}, got
    assert got["judgment_share_of_blocking"] == 0.33, got
    text = subprocess.run([sys.executable, str(out / "scripts/process/process_kpis.py"), "findings"],
                          cwd=out, capture_output=True, text=True)
    assert text.returncode == 0, text.stdout + text.stderr
    assert "repeats in 2 works: testable:mutation" in text.stdout, text.stdout
    assert "n=2<20" in text.stdout, text.stdout


def test_findings_text_mode_exits_zero_and_counts_works(render, tmp_path):
    """#303: a report with a FINDING line must not crash the text mode — `findings`
    unpacks `_report_findings`' (work, fields, round) triples."""
    out = _render(render, tmp_path, github_issues=True)
    reviews = out / ".process-work/reviews"
    reviews.mkdir(parents=True)
    (reviews / "a.md").write_text(
        "review: a\nwork: #1\npublish-waived: test\n\n"
        "FINDING sev=blocker action=fix issue=- class=testable rule=mutation weak assert\n",
        encoding="utf-8")
    r = subprocess.run([sys.executable, str(out / "scripts/process/process_kpis.py"), "findings"],
                       cwd=out, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "Traceback" not in r.stderr, r.stderr
    assert "n=1<20" in r.stdout, r.stdout


def test_a_bad_finding_class_is_a_malformed_line(render, tmp_path):
    out = _render(render, tmp_path, github_issues=True)
    import importlib.util
    spec = importlib.util.spec_from_file_location("ci_gate_cls", out / "scripts/process/check_issues.py")
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    (fields, err, _), = gate.report_findings("FINDING sev=minor action=fix issue=- class=maybe rule=x title\n")
    assert fields is None and "class='maybe'" in err
    # refute of #276: an older report's title may start with the word — like `by=`, an
    # invalid value with no key after it begins the title
    for title in ("class=Foo leaks its lock", "rule=x+y is wrong"):
        (fields, err, _), = gate.report_findings(f"FINDING sev=minor action=fix issue=- {title}\n")
        assert err is None and fields["title"] == title, err
    (fields, err, _), = gate.report_findings("FINDING sev=minor action=fix issue=- class=mechanical "
                                             "rule=ruff:S110 swallowed\n")
    assert err is None and fields["rule"] == "ruff:S110" and fields["title"] == "swallowed"


def test_a_worker_states_its_usage_and_models_shows_it(render, tmp_path):
    """#270: a harness without transcripts the dispatch reader knows states its tokens
    with the report; `models` puts them beside rounds and blocks."""
    out = _render(render, tmp_path)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=out, check=True)
    rep = out / "scripts/process/report.py"
    env = {**os.environ, "PROCESS_PHASE": "execute", "PROCESS_MODEL": "deepseek-v4.1-flash"}
    r = subprocess.run([sys.executable, str(rep), "blocked", "--issue", "7", "--worker", "w7",
                        "--usage", "input=1000,cached=200,output=300,cost_usd=0.02"],
                       cwd=out, capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
    bad = subprocess.run([sys.executable, str(rep), "failed", "--issue", "7", "--usage", "output=-1"],
                         cwd=out, capture_output=True, text=True, env=env)
    assert bad.returncode == 2 and "--usage" in bad.stderr, bad.stderr
    # refute: float() took nan and inf, int() took `1_000` and non-ASCII digits
    for usage in ("input=1,output=1,cost_usd=nan", "input=1,output=1,cost_usd=inf", "input=1_000,output=1",
                  "input=\u0661\u0662,output=1", "input=+5,output=1", "output=1", "input=1"):
        bad = subprocess.run([sys.executable, str(rep), "failed", "--issue", "7", "--usage", usage],
                             cwd=out, capture_output=True, text=True, env=env)
        assert bad.returncode == 2 and "--usage" in bad.stderr, usage
    text = subprocess.run([sys.executable, str(out / "scripts/process/process_kpis.py"), "models"],
                          cwd=out, capture_output=True, text=True).stdout
    row = next(ln for ln in text.splitlines() if "deepseek-v4.1-flash" in ln)
    assert "1,500 (1)" in row and "$0.02" in row, text
    # cross-model review: a re-dispatch on another model dropped the first model's stated tokens
    later = {**env, "PROCESS_MODEL": "claude-opus-5"}
    subprocess.run([sys.executable, str(rep), "blocked", "--issue", "7", "--worker", "w7"],
                   cwd=out, capture_output=True, text=True, env=later, check=True)
    text = subprocess.run([sys.executable, str(out / "scripts/process/process_kpis.py"), "models"],
                          cwd=out, capture_output=True, text=True).stdout
    row = next(ln for ln in text.splitlines() if "deepseek-v4.1-flash" in ln)
    assert "1,500 (1)" in row, text


def _kpis_module(out):
    import importlib.util
    sys.path.insert(0, str(out / "scripts/process"))
    spec = importlib.util.spec_from_file_location("kpis_baseline", out / "scripts/process/process_kpis.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _finding(sev: str, action: str = "fix", origin: str | None = None) -> str:
    return (f"FINDING sev={sev} action={action} issue=- gate=judgement"
            + (f" origin={origin}" if origin else "") + f" {sev} {action}\n")


def _report_file(out: Path, name: str, work: str, findings: str, *, rnd: int | None = None,
                 phase: str | None = None) -> None:
    reviews = out / ".process-work/reviews"
    reviews.mkdir(parents=True, exist_ok=True)
    head = (f"review: {name}\nwork: {work}\npublish-waived: test\n"
            + (f"round: {rnd}\n" if rnd is not None else "") + (f"phase: {phase}\n" if phase else ""))
    (reviews / f"{name}.md").write_text(head + "\n## Findings\n" + findings, encoding="utf-8")


def test_baseline_counts_rounds_findings_and_skips_per_window(render, tmp_path, monkeypatch, capsys):
    """#293 AC-5: per window, only that window's works — blockers by origin from code
    reviews, rounds with and without a plan review, the fix pass's size against the next
    round's fix-induced blockers (the round from the `round:` header, else `-r<N>` closing
    the file name; reports of one round add up, unrounded ones are only counted), and skips."""
    out = _render(render, tmp_path, github_issues=True)
    archive = out / ".process-work/plans/archive"
    archive.mkdir(parents=True, exist_ok=True)
    (archive / "2026-10-05-gadget.md").write_text("# Plan\n\ntier: 2\nissue: #12\n")
    _journal(out, _review(9, 1, "block") + _review(9, 2, "block") + _review(9, 3, "pass")
             + _review("9-plan", 1, "pass") + _review("gadget", 1, "block") + _review("gadget", 2, "pass")
             + "skipped refute work=9: no gate code in the fix\n"
             + "skipped refute work=gadget: no gate code\n")
    # work 9 (window A): round 1 in two reports, 7 fixes in all → round 2 has two fix blockers
    _report_file(out, "2026-10-02-9-a", "#9", _finding("blocker") * 3 + _finding("major") * 2, rnd=1)
    _report_file(out, "2026-10-02-9-b", "#9", _finding("major") * 2 + _finding("minor", "accept"), rnd=1)
    _report_file(out, "2026-10-03-9-claude-r2", "#9",
                 _finding("blocker", origin="fix") * 2 + _finding("blocker", origin="late"))
    _report_file(out, "2026-10-04-9-r3", "#9", _finding("nit", "accept"))
    _report_file(out, "2026-10-04-9-late", "#9", _finding("blocker", origin="draft"))  # no round
    # a plan review counts for neither the origins nor the pairs
    _report_file(out, "2026-10-01-9-plan-r1", "#9", _finding("blocker", origin="fix") * 5, phase="plan")
    # work 12 (window B), named by its plan's slug: one fix, a clean next round
    _report_file(out, "2026-10-12-gadget-r1", "gadget", _finding("blocker", origin="draft"))
    _report_file(out, "2026-10-13-gadget-r2", "gadget", "")
    k = _kpis_module(out)
    item = {"issue": 9, "merged": {"value": "2026-10-05T12:00:00+00:00"}, "lead_s": {"value": 0},
            "tokens": {"value": {}}, "escapes": {"value": 0}}
    other = {**item, "issue": 12, "merged": {"value": "2026-10-15T12:00:00+00:00"}}
    a = k.baseline_numbers(out, *k._window("2026-10-01:2026-10-10"), items=[item, other], commits=[])
    assert a["blockers_by_origin"] == {"-": 3, "draft": 1, "fix": 2, "late": 1}, a
    pairs = a["fix_findings_vs_fix_blockers"]
    assert pairs["unrounded"] == 1
    assert pairs["buckets"]["6-9"] == {"rounds": 1, "with_fix_blocker": 1, "fix_blockers": 2}, pairs
    # round 2 (3 fixes) → round 3 without a fix blocker; round 3 has no next round
    assert pairs["buckets"]["3-5"] == {"rounds": 1, "with_fix_blocker": 0, "fix_blockers": 0}, pairs
    assert pairs["buckets"]["0-2"]["rounds"] == 0 and pairs["buckets"][">=10"]["rounds"] == 0
    assert (a["rounds_with_plan_review"], a["rounds_without_plan_review"]) == (3, None)
    assert a["skips_by_kind"] == {"refute": 1}
    b = k.baseline_numbers(out, *k._window("2026-10-10:"), items=[item, other], commits=[])
    assert b["blockers_by_origin"] == {"draft": 1}
    assert b["fix_findings_vs_fix_blockers"]["buckets"]["0-2"] == {"rounds": 1, "with_fix_blocker": 0,
                                                                   "fix_blockers": 0}
    assert (b["rounds_with_plan_review"], b["rounds_without_plan_review"]) == (None, 2)
    assert b["skips_by_kind"] == {"refute": 1}
    monkeypatch.setattr(k, "flow_items", lambda root: [item, other])
    assert k.baseline(out, [k._window("2026-10-01:2026-10-10")]) == 0
    text = capsys.readouterr().out
    assert "6-9 findings: 1/1 rounds, 2 blockers" in text and "unrounded reports 1" in text
    assert "skips by kind 2026-10-01–2026-10-10: refute 1" in text and "rounds_with_plan_review" in text


def test_baseline_without_the_finding_reader_says_not_read(render, tmp_path):
    out = _render(render, tmp_path)
    k = _kpis_module(out)
    item = {"issue": 9, "merged": {"value": "2026-10-05T12:00:00+00:00"}, "lead_s": {"value": 0},
            "tokens": {"value": {}}, "escapes": {"value": 0}}
    got = k.baseline_numbers(out, *k._window("2026-10-01:"), items=[item], commits=[])
    assert got["blockers_by_origin"] == got["fix_findings_vs_fix_blockers"] == "not read"


def test_a_report_round_comes_from_its_header_else_its_name(render, tmp_path):
    out = _render(render, tmp_path)
    k = _kpis_module(out)
    assert k._report_round("2026-10-02-9-r2-claude.md", {"round": ["4"]}) == 4
    assert k._report_round("2026-10-02-9-claude-r2.md", {}) == 2
    assert k._report_round("2026-10-02-9-r10.md", {}) == 10
    assert k._report_round("2026-10-02-r2d2.md", {}) is None  # no round part
    assert k._report_round("2026-10-02-9-r2.md", {"round": ["two"]}) is None  # a bad header is not read past
    assert k._report_round("2026-10-02-9-r2.md", {"round": ["1", "2"]}) is None


def test_only_a_round_marker_ending_the_name_is_a_round(render, tmp_path):
    """Refute v2.77 G: `-r<N>` inside a slug (`…-r2-migration-review`) is no round — only
    `-r<N>` closing the name is; the `round:` header wins over any name."""
    out = _render(render, tmp_path)
    k = _kpis_module(out)
    assert k._report_round("2026-10-21-r2-migration-review.md", {}) is None
    assert k._report_round("2026-10-21-9-r2-claude.md", {}) is None
    assert k._report_round("2026-10-21-foo-review-r1.md", {}) == 1
    assert k._report_round("2026-10-21-9-r1-r2.md", {}) == 2  # the closing marker
    assert k._report_round("2026-10-21-9-r٣.md", {}) is None  # ASCII digits only
    # named residual: a slug ending in a version reads as a round unless the header says otherwise
    assert k._report_round("2026-10-21-cache-v2-r3.md", {}) == 3
    assert k._report_round("2026-10-21-cache-v2-r3.md", {"round": ["1"]}) == 1


def test_baseline_takes_medians_per_merged_work_in_a_window(render, tmp_path):
    """#277: the numbers a verification change must move, per window."""
    out = _render(render, tmp_path, github_issues=True)
    _journal(out, "REVIEW work=9 tier=2 reviewer=r model=m independence=bundle,non-implementing "
                  "verdict=block round=1\n"
                  "REVIEW work=9 tier=2 reviewer=r model=m independence=bundle,non-implementing "
                  "verdict=pass round=2\n")
    k = _kpis_module(out)
    # `tokens.value` is the fields dict flow_items stores (cross-model review: median of dicts crashed)
    item = {"issue": 9, "merged": {"value": "2026-10-10T12:00:00+00:00"}, "lead_s": {"value": 7200},
            "tokens": {"value": {"input": 600, "output": 400}}, "escapes": {"value": 0}}
    lo, hi = k._window("2026-10-01:2026-10-20")
    got = k.baseline_numbers(out, lo, hi, items=[item], commits=[])
    assert (got["works"], got["rounds_per_work"], got["fix_rounds_per_work"], got["tokens_per_work"],
            got["lead_hours"]) == (1, 2, 1, 1000, 2.0), got
    # a REVIEW line naming its work by the plan's slug counts for the plan's issue
    archive = out / ".process-work/plans/archive"
    archive.mkdir(parents=True, exist_ok=True)
    (archive / "2026-10-05-12-gadget.md").write_text("# Plan\n\ntier: 2\nissue: #12\n")
    _journal(out, "REVIEW work=2026-10-05-12-gadget tier=2 reviewer=r model=m "
                  "independence=bundle,non-implementing verdict=block round=1\n"
                  "REVIEW work=2026-10-05-12-gadget tier=2 reviewer=r model=m "
                  "independence=bundle,non-implementing verdict=block round=2\n"
                  "REVIEW work=2026-10-05-12-gadget tier=2 reviewer=r model=m "
                  "independence=bundle,non-implementing verdict=pass round=3\n")
    slugged = {**item, "issue": 12}
    got = k.baseline_numbers(out, lo, hi, items=[slugged], commits=[])
    assert (got["rounds_per_work"], got["fix_rounds_per_work"]) == (3, 2), got
    lo, hi = k._window("2026-10-20:")
    assert k.baseline_numbers(out, lo, hi, items=[item], commits=[])["works"] == 0
    r = subprocess.run([sys.executable, str(out / "scripts/process/process_kpis.py"), "baseline",
                        "--window", "2026-10-01:2026-10-20", "--window", "2026-10-20:", "--json"],
                       cwd=out, capture_output=True, text=True)
    assert r.returncode == 0 and len(json.loads(r.stdout)) == 2, r.stdout + r.stderr


# --- #311: blocks on lines unchanged since round 1 ------------------------------------------

def _gitx(out: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(out), "-c", "user.email=t@t", "-c", "user.name=t",
                           "-c", "commit.gpgsign=false", *args], check=True, capture_output=True,
                          text=True).stdout.strip()


def _old_report(work: str, rnd: int, findings: str, head: str | None = None) -> str:
    art = f"artifact: base={'0' * 40} head={head}\n" if head else ""
    return f"review: r\nwork: {work}\nround: {rnd}\npublish-waived: test\n{art}\n## Findings\n{findings}"


def _old_repo(render, tmp_path):
    """Round 1 at h1; the fix changes a.py:5, deletes a.py:10, renames b.py → c.py and
    rewrites a binary file; round 2 at hr."""
    out = _render(render, tmp_path, github_issues=True)
    _gitx(out, "init", "-q", "-b", "main")
    (out / "src").mkdir()
    (out / "src/a.py").write_text("".join(f"line {i}\n" for i in range(1, 21)))
    (out / "src/b.py").write_text("".join(f"b {i}\n" for i in range(1, 11)))
    (out / "src/blob.bin").write_bytes(b"\0\1\2" * 10)
    _gitx(out, "add", "-A")
    _gitx(out, "commit", "-qm", "round 1")
    h1 = _gitx(out, "rev-parse", "HEAD")
    lines = [f"line {i}\n" for i in range(1, 21)]
    lines[4] = "line 5 fixed\n"
    del lines[9]
    (out / "src/a.py").write_text("".join(lines))
    _gitx(out, "mv", "src/b.py", "src/c.py")
    (out / "src/blob.bin").write_bytes(b"\0\3\4" * 10)
    _gitx(out, "add", "-A")
    _gitx(out, "commit", "-qm", "fix round 1")
    hr = _gitx(out, "rev-parse", "HEAD")
    return out, h1, hr


def _measure(out: Path) -> dict:
    sys.path.insert(0, str(out / "scripts/process"))
    try:
        for m in ("process_kpis", "check_review", "check_issues"):
            sys.modules.pop(m, None)
        import process_kpis  # noqa: PLC0415
        return process_kpis._blocks_since_round1(out)
    finally:
        sys.path.remove(str(out / "scripts/process"))
        for m in ("process_kpis", "check_review", "check_issues"):
            sys.modules.pop(m, None)


def _blocker(at: str | None, title: str) -> str:
    return f"FINDING sev=blocker action=fix issue=- class=judgment{f' at={at}' if at else ''} {title}\n"


def test_old_code_blocks_are_judged_by_the_tree_not_by_ancestry(render, tmp_path):
    """#311 AC-1/AC-3: a block of round 2 on a line round 1 saw is `unchanged`, one on a
    line the fix touched is `changed`; places git cannot measure are named, never counted."""
    out, h1, hr = _old_repo(render, tmp_path)
    _journal(out, f"REVIEW work=9 tier=2 reviewer=r model=m independence=bundle,non-implementing "
                  f"base={'0' * 40} head={h1} verdict=block round=1\n"
                  f"REVIEW work=9 tier=2 reviewer=r model=m independence=bundle,non-implementing "
                  f"base={'0' * 40} head={hr} verdict=block round=2\n")
    reviews = out / ".process-work/reviews"
    reviews.mkdir(parents=True)
    (reviews / "9-r1.md").write_text(_old_report("#9", 1, _blocker("src/a.py:15", "round one, not counted")))
    findings = "".join(_blocker(at, t) for at, t in (
        ("src/a.py:5", "changed line"), ("src/a.py:14", "unchanged line"), ("src/a.py:4-6", "range half changed"),
        ("src/a.py:13-15", "range unchanged"), ("src/a.py:9", "next to a deletion"), ("src/a.py:10", "after a deletion"),
        ("src/a.py:12", "past the deletion"), ("src/c.py:3", "renamed file"), ("src/blob.bin:1", "binary changed"),
        ("-", "no single place"), (None, "no place given"), ("src/a.py", "file only"),
        ("src/a.py:99", "past the end"), ("src/gone.py:1", "file not there"),
        (".process-work/plans/2026-01-01-x.md:3", "a plan line")))
    (reviews / "9-r2.md").write_text(_old_report("#9", 2, findings + "FINDING sev=major action=fix issue=- class=judgment at=src/a.py:5 a major, not counted\n", head=hr))
    got = _measure(out)
    # unchanged: a.py:14, 13-15, 12 (old 13), c.py:3; changed: a.py:5, 4-6, 9, 10, blob
    assert (got["unchanged"], got["changed"]) == (4, 5), got
    assert got["unmeasured"] == {"no-place": 1, "no-at": 1, "no-line": 1, "outside": 2, "not-code": 1}, got
    assert set(got["per_round"]) == {2} and got["per_work"]["9"]["unchanged"] == 4
    text = _rounds(out)
    assert "old-code blocks (rounds >= 2): 4/9 (44 %) unchanged since round 1; not measured: " \
           "no-at 1, no-place 1, no-line 1, not-code 1, outside 2" in text, text
    assert "    round 2: 4/9 (44 %)" in text


def test_old_code_survives_a_rebase_and_names_a_missing_commit(render, tmp_path):
    """Round 1's head off the branch's history (a rebase) still judges by content; a head
    the repository no longer has is `missing-commit`; with two round-1 heads one suffices."""
    out = _render(render, tmp_path, github_issues=True)
    _gitx(out, "init", "-q", "-b", "main")
    (out / "src").mkdir()
    (out / "src/a.py").write_text("".join(f"line {i}\n" for i in range(1, 21)))
    _gitx(out, "add", "-A")
    _gitx(out, "commit", "-qm", "base")
    _gitx(out, "checkout", "-qb", "work")
    (out / "src/new.py").write_text("x\n")
    _gitx(out, "add", "-A")
    _gitx(out, "commit", "-qm", "work")
    h1 = _gitx(out, "rev-parse", "HEAD")
    _gitx(out, "checkout", "-q", "main")
    (out / "README.x").write_text("main moved\n")
    _gitx(out, "add", "-A")
    _gitx(out, "commit", "-qm", "main moves")
    _gitx(out, "checkout", "-qB", "work2")
    (out / "src/new.py").write_text("x\n")
    lines = [f"line {i}\n" for i in range(1, 21)]
    lines[4] = "line 5 fixed\n"
    (out / "src/a.py").write_text("".join(lines))
    _gitx(out, "add", "-A")
    _gitx(out, "commit", "-qm", "rebased work and fix")
    hr = _gitx(out, "rev-parse", "HEAD")
    gone = "e" * 40
    _journal(out, "".join(f"REVIEW work=9 tier=2 reviewer=r model=m independence=bundle,non-implementing "
                          f"base={'0' * 40} head={h} verdict=block round={r}\n"
                          for h, r in ((gone, 1), (h1, 1), (hr, 2))))
    reviews = out / ".process-work/reviews"
    reviews.mkdir(parents=True)
    (reviews / "9-r2.md").write_text(_old_report("#9", 2, _blocker("src/a.py:14", "old") + _blocker("src/a.py:5", "new")))
    got = _measure(out)
    assert (got["unchanged"], got["changed"]) == (1, 1), got  # hr from the journal: one head in round 2
    _journal(out, "".join(f"REVIEW work=9 tier=2 reviewer=r model=m independence=bundle,non-implementing "
                          f"base={'0' * 40} head={h} verdict=block round={r}\n"
                          for h, r in ((gone, 1), (hr, 2))))
    assert _measure(out)["unmeasured"] == {"missing-commit": 2}


def test_old_code_joins_slug_and_issue_and_needs_one_head(render, tmp_path):
    """A report naming `#12` and REVIEW lines naming the plan's slug are one work; a round
    with two heads and no full-SHA `artifact:` head is `no-head`."""
    out, h1, hr = _old_repo(render, tmp_path)
    plans = out / ".process-work/plans"
    plans.mkdir(parents=True, exist_ok=True)
    (plans / "2026-01-02-gadget.md").write_text("# Plan\n\ntier: 2\nissue: #12\n")
    _journal(out, "".join(f"REVIEW work=gadget tier=2 reviewer=r model=m independence=bundle,non-implementing "
                          f"base={'0' * 40} head={h} verdict=block round={r}\n"
                          for h, r in ((h1, 1), (hr, 2))))
    reviews = out / ".process-work/reviews"
    reviews.mkdir(parents=True)
    (reviews / "12-r2.md").write_text(_old_report("#12", 2, _blocker("src/a.py:14", "old"), head=hr))
    assert _measure(out)["unchanged"] == 1
    # the other way round: the report names the slug, the REVIEW lines the issue
    _journal(out, "".join(f"REVIEW work=#12 tier=2 reviewer=r model=m independence=bundle,non-implementing "
                          f"base={'0' * 40} head={h} verdict=block round={r}\n" for h, r in ((h1, 1), (hr, 2))))
    (reviews / "12-r2.md").write_text(_old_report("gadget", 2, _blocker("src/a.py:14", "old")))
    assert _measure(out)["unchanged"] == 1  # head from the one REVIEW line of round 2
    # a named head that is no commit never falls back to the journal's one head
    (reviews / "12-r2.md").write_text(_old_report("gadget", 2, _blocker("src/a.py:14", "old"), head="HEAD"))
    assert _measure(out)["unmeasured"] == {"no-head": 1}
    # two heads in round 2 and none in the report: unknown
    _journal(out, "".join(f"REVIEW work=#12 tier=2 reviewer=r model=m independence=bundle,non-implementing "
                          f"base={'0' * 40} head={h} verdict=block round={r}\n"
                          for h, r in ((h1, 1), (hr, 2), ("f" * 40, 2))))
    (reviews / "12-r2.md").write_text(_old_report("gadget", 2, _blocker("src/a.py:14", "old")))
    assert _measure(out)["unmeasured"] == {"no-head": 1}


def test_old_code_reads_a_place_as_a_path_and_counts_an_unreadable_report(render, tmp_path):
    """`pages/[id].tsx` is that file, not a glob over `pages/i.tsx`, `pages/d.tsx`; a report
    that cannot be read is counted, never dropped (plan review, round 3)."""
    out = _render(render, tmp_path, github_issues=True)
    _gitx(out, "init", "-q", "-b", "main")
    (out / "pages").mkdir()
    (out / "pages/[id].tsx").write_text("".join(f"l {i}\n" for i in range(1, 6)))
    (out / "pages/i.tsx").write_text("".join(f"i {i}\n" for i in range(1, 6)))
    _gitx(out, "add", "-A")
    _gitx(out, "commit", "-qm", "round 1")
    h1 = _gitx(out, "rev-parse", "HEAD")
    (out / "pages/i.tsx").write_text("changed\n" * 5)
    _gitx(out, "commit", "-qam", "fix touches another file")
    hr = _gitx(out, "rev-parse", "HEAD")
    _journal(out, "".join(f"REVIEW work=9 tier=2 reviewer=r model=m independence=bundle,non-implementing "
                          f"base={'0' * 40} head={h} verdict=block round={r}\n" for h, r in ((h1, 1), (hr, 2))))
    reviews = out / ".process-work/reviews"
    reviews.mkdir(parents=True)
    (reviews / "9-r2.md").write_text(_old_report("#9", 2, _blocker("pages/[id].tsx:2", "dynamic route"), head=hr))
    got = _measure(out)
    assert (got["unchanged"], got["changed"]) == (1, 0), got
    (reviews / "broken.md").mkdir()  # a directory named like a report: it cannot be read
    assert _measure(out)["unmeasured"] == {"unreadable-report": 1}


def test_old_code_without_the_finding_reader_is_not_read(render, tmp_path):
    out = _render(render, tmp_path)
    _journal(out, _review(9, 1, "block"))
    assert "not_read" in _measure(out)
    assert "old-code blocks (rounds >= 2): not read" in _rounds(out)


def test_the_artifact_head_is_read_from_the_header_block_only(render, tmp_path):
    out = _render(render, tmp_path, github_issues=True)
    sys.path.insert(0, str(out / "scripts/process"))
    try:
        sys.modules.pop("check_review", None)
        import check_review  # noqa: PLC0415
        head = "a" * 40
        assert check_review.report_artifact(f"review: r\nartifact: REVIEW_ARTIFACT base={'0' * 40} head={head} diff=x\n\n# T\n") \
            == {"base": "0" * 40, "head": head, "diff": "x"}
        assert check_review.report_artifact(f"review: r\n\n## Prompt\nartifact: base=1 head={head}\n") == {}
        assert check_review.report_artifact("review: r\n\n") == {}
    finally:
        sys.path.remove(str(out / "scripts/process"))
        sys.modules.pop("check_review", None)
    doc = (out / "docs/process/modules/telemetry.md").read_text()
    assert "**old-code blocks** (#311)" in doc and "unreadable-report" in doc


def test_old_code_tells_a_git_failure_from_an_absent_file(render, tmp_path, monkeypatch):
    """A blob git cannot read, or git that cannot run, is `git-failed` — never `changed`
    or `missing-commit` (v2.78 refute, round 1); a directory or a line past the end by
    git's count (a form feed is no line break) is `outside`; a user's
    `diff.interHunkContext` merges no hunks over an unchanged line."""
    out, h1, hr = _old_repo(render, tmp_path)
    _journal(out, "".join(f"REVIEW work=9 tier=2 reviewer=r model=m independence=bundle,non-implementing "
                          f"base={'0' * 40} head={h} verdict=block round={r}\n" for h, r in ((h1, 1), (hr, 2))))
    reviews = out / ".process-work/reviews"
    reviews.mkdir(parents=True)
    report = reviews / "9-r2.md"
    report.write_text(_old_report("#9", 2, _blocker("src:2", "a directory") + _blocker("src/a.py:14", "old"), head=hr))
    assert _measure(out)["unmeasured"] == {"outside": 1}
    _gitx(out, "config", "diff.interHunkContext", "10")
    report.write_text(_old_report("#9", 2, _blocker("src/a.py:7", "between two hunks"), head=hr))
    assert _measure(out)["unchanged"] == 1  # a.py:5 changed, old 10 deleted: new 7 stands as it did
    _gitx(out, "config", "--unset", "diff.interHunkContext")
    monkeypatch.setenv("PATH", str(tmp_path / "no-git-here"))
    report.write_text(_old_report("#9", 2, _blocker("src/a.py:14", "old"), head=hr))
    assert _measure(out)["unmeasured"] == {"git-failed": 1}
    monkeypatch.undo()
    blob = _gitx(out, "rev-parse", f"{h1}:src/a.py")
    (out / ".git/objects" / blob[:2] / blob[2:]).unlink()
    assert _measure(out)["unmeasured"] == {"git-failed": 1}


def test_old_code_counts_lines_as_git_does(render, tmp_path):
    out = _render(render, tmp_path, github_issues=True)
    _gitx(out, "init", "-q", "-b", "main")
    (out / "src").mkdir()
    (out / "src/a.c").write_text("".join(f"x\f{i}\n" for i in range(1, 6)))
    _gitx(out, "add", "-A")
    _gitx(out, "commit", "-qm", "r1")
    h1 = _gitx(out, "rev-parse", "HEAD")
    _gitx(out, "commit", "-q", "--allow-empty", "-m", "r2")
    hr = _gitx(out, "rev-parse", "HEAD")
    _journal(out, "".join(f"REVIEW work=9 tier=2 reviewer=r model=m independence=bundle,non-implementing "
                          f"base={'0' * 40} head={h} verdict=block round={r}\n" for h, r in ((h1, 1), (hr, 2))))
    reviews = out / ".process-work/reviews"
    reviews.mkdir(parents=True)
    (reviews / "9-r2.md").write_text(_old_report("#9", 2, _blocker("src/a.c:8", "past the end") + _blocker("src/a.c:5", "last line"), head=hr))
    got = _measure(out)
    assert got["unmeasured"] == {"outside": 1} and got["unchanged"] == 1, got


def test_old_code_keeps_two_issues_of_one_plan_apart(render, tmp_path):
    """A plan declaring #12 and #13 joins neither issue's rounds to the other's (refute)."""
    out, h1, hr = _old_repo(render, tmp_path)
    plans = out / ".process-work/plans"
    plans.mkdir(parents=True, exist_ok=True)
    (plans / "2026-01-02-pair.md").write_text("# Plan\n\ntier: 2\nissue: #12\nissue: #13\n")
    _journal(out, "".join(f"REVIEW work={w} tier=2 reviewer=r model=m independence=bundle,non-implementing "
                          f"base={'0' * 40} head={h} verdict=block round={r}\n"
                          for w, h, r in (("12", h1, 1), ("12", hr, 2), ("13", hr, 1))))
    reviews = out / ".process-work/reviews"
    reviews.mkdir(parents=True)
    (reviews / "12-r2.md").write_text(_old_report("#12", 2, _blocker("src/a.py:5", "the fix changed it"), head=hr))
    got = _measure(out)
    assert (got["unchanged"], got["changed"]) == (0, 1), got


def test_old_code_in_a_window_leaves_unreadable_reports_out(render, tmp_path):
    """An unreadable report belongs to no known work: `rounds` counts it, a window does not."""
    out = _render(render, tmp_path, github_issues=True)
    _journal(out, _review(9, 1, "block"))
    reviews = out / ".process-work/reviews"
    reviews.mkdir(parents=True)
    (reviews / "broken.md").mkdir()
    sys.path.insert(0, str(out / "scripts/process"))
    try:
        for m in ("process_kpis", "check_review", "check_issues"):
            sys.modules.pop(m, None)
        import process_kpis  # noqa: PLC0415
        assert process_kpis._blocks_since_round1(out)["unmeasured"] == {"unreadable-report": 1}
        assert process_kpis._blocks_since_round1(out, {"9"})["unmeasured"] == {}
    finally:
        sys.path.remove(str(out / "scripts/process"))
        for m in ("process_kpis", "check_review", "check_issues"):
            sys.modules.pop(m, None)


def test_old_code_sees_a_changed_binary_in_any_locale(render, tmp_path, monkeypatch):
    """A changed binary is changed whatever language git speaks (cross-model review,
    round 2: a German git printed no "Binary files")."""
    out, h1, hr = _old_repo(render, tmp_path)
    _journal(out, "".join(f"REVIEW work=9 tier=2 reviewer=r model=m independence=bundle,non-implementing "
                          f"base={'0' * 40} head={h} verdict=block round={r}\n" for h, r in ((h1, 1), (hr, 2))))
    reviews = out / ".process-work/reviews"
    reviews.mkdir(parents=True)
    (reviews / "9-r2.md").write_text(_old_report("#9", 2, _blocker("src/blob.bin:1", "binary"), head=hr))
    (out / ".gitattributes").write_text("*.bin -diff\n")  # no hunk at all, in any language
    _gitx(out, "add", ".gitattributes")
    assert _measure(out)["changed"] == 1
    monkeypatch.setenv("LC_ALL", "de_DE.UTF-8")
    monkeypatch.setenv("LANGUAGE", "de")
    assert _measure(out)["changed"] == 1


def test_old_code_joins_a_slug_only_through_a_one_issue_plan(render, tmp_path):
    """A report naming the slug of a plan with two issues takes neither issue's heads; a
    window of #12 takes no report of #13 (cross-model review, round 2)."""
    out, h1, hr = _old_repo(render, tmp_path)
    plans = out / ".process-work/plans"
    plans.mkdir(parents=True, exist_ok=True)
    (plans / "2026-01-02-pair.md").write_text("# Plan\n\ntier: 2\nissue: #12\nissue: #13\n")
    _journal(out, "".join(f"REVIEW work={w} tier=2 reviewer=r model=m independence=bundle,non-implementing "
                          f"base={'0' * 40} head={h} verdict=block round={r}\n"
                          for w, h, r in (("12", h1, 1), ("12", hr, 2), ("13", hr, 1), ("13", hr, 2))))
    reviews = out / ".process-work/reviews"
    reviews.mkdir(parents=True)
    (reviews / "pair-r2.md").write_text(_old_report("pair", 2, _blocker("src/a.py:5", "changed by the fix"), head=hr))
    assert _measure(out)["unmeasured"] == {"no-round1": 1}
    (reviews / "pair-r2.md").unlink()
    (reviews / "13-r2.md").write_text(_old_report("#13", 2, _blocker("src/a.py:5", "of #13"), head=hr))
    sys.path.insert(0, str(out / "scripts/process"))
    try:
        for m in ("process_kpis", "check_review", "check_issues"):
            sys.modules.pop(m, None)
        import process_kpis  # noqa: PLC0415
        window = process_kpis._window_works([12], process_kpis._plans(out))
        assert "13" not in window
        assert process_kpis._blocks_since_round1(out, window)["unchanged"] == 0
    finally:
        sys.path.remove(str(out / "scripts/process"))
        for m in ("process_kpis", "check_review", "check_issues"):
            sys.modules.pop(m, None)


def test_old_code_survives_a_nul_in_a_place(render, tmp_path):
    out, h1, hr = _old_repo(render, tmp_path)
    _journal(out, "".join(f"REVIEW work=9 tier=2 reviewer=r model=m independence=bundle,non-implementing "
                          f"base={'0' * 40} head={h} verdict=block round={r}\n" for h, r in ((h1, 1), (hr, 2))))
    reviews = out / ".process-work/reviews"
    reviews.mkdir(parents=True)
    (reviews / "9-r2.md").write_text(_old_report("#9", 2, _blocker("src/a%00.py:1", "nul"), head=hr))
    assert _measure(out)["unmeasured"] == {"git-failed": 1}


# --- v2.80: merged works from git (#341), works (#314), rounds by number (#318), -------------
# --- escapes per tier (#320), process load and size ----------------------------------------

def _at(day: int, hour: int = 9) -> str:
    return f"2026-03-{day:02d}T{hour:02d}:00:00+00:00"


def _dt(day: int, hour: int = 9):
    from datetime import datetime, timezone
    return datetime(2026, 3, day, hour, tzinfo=timezone.utc)


def _g(out: Path, *args: str, when: str | None = None, author: str | None = None) -> str:
    env = dict(os.environ)
    if when:
        env.update(GIT_COMMITTER_DATE=when, GIT_AUTHOR_DATE=author or when)
    return subprocess.run(["git", "-C", str(out), "-c", "user.email=t@t", "-c", "user.name=t",
                           "-c", "commit.gpgsign=false", *args], check=True, capture_output=True,
                          text=True, env=env).stdout.strip()


def _put(out: Path, message: str, files: dict, when: str, author: str | None = None) -> None:
    """One commit: `files` written (None removes one), committed at `when` (author date `author`)."""
    for rel, text in files.items():
        if text is None:
            _g(out, "rm", "-q", rel)
            continue
        p = out / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    _g(out, "add", "-A")
    _g(out, "commit", "-q", "--allow-empty", "-m", message, when=when, author=author)


def _lines(n: int, tag: str = "x") -> str:
    return "".join(f"{tag} {i}\n" for i in range(n))


def _plan_text(issue: int, tier: int = 2, extra: str = "") -> str:
    return f"# Plan\n\nissue: #{issue}\ntier: {tier}\n{extra}\n## Decisions\n"


def _merges_repo(render, tmp_path, **mods) -> Path:
    """A project on git: the rendered tree as one onboarding commit, nothing merged yet."""
    out = _render(render, tmp_path, **mods)
    _g(out, "init", "-q", "-b", "main")
    _put(out, "chore: onboard the process", {}, _at(1, 0))
    return out


def _train_merge(out: Path, branch: str, commits: list, message: str, when: str) -> None:
    """A train merge: `branch` off main with `commits` [(message, files, date)], merged
    `--no-ff` with `message` (`train: merge <branch>`, then `Closes #N`/`Refs #N`)."""
    _g(out, "checkout", "-q", "-b", branch, "main")
    for msg, files, at in commits:
        _put(out, msg, files, at)
    _g(out, "checkout", "-q", "main")
    _g(out, "merge", "-q", "--no-ff", "-m", message, branch, when=when)


def _finish_merge(out: Path, branch: str, commits: list, plans: list, when: str) -> None:
    """A `finish` merge: the branch's commits rebased (author date kept, commit date `when`),
    its plans archived in `docs: archive plan(s) on merge — <names>`, main fast-forwarded."""
    _g(out, "checkout", "-q", "-b", branch, "main")
    for msg, files, at in commits:
        _put(out, msg, files, when, author=at)
    (out / ".process-work/plans/archive").mkdir(parents=True, exist_ok=True)
    for name in plans:
        _g(out, "mv", f".process-work/plans/{name}", f".process-work/plans/archive/{name}")
    _put(out, f"docs: archive plan(s) on merge — {', '.join(plans)}", {}, when)
    _g(out, "checkout", "-q", "main")
    _g(out, "merge", "-q", "--ff-only", branch)


def _clone(out: Path, tmp_path: Path) -> Path:
    """A fresh clone: no `.git/process-*` — no reports, no dispatch logs, no train rows."""
    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "-q", str(out), str(clone)], check=True, capture_output=True)
    assert not list((clone / ".git").glob("process-*"))
    return clone


def _cli(root: Path, *args: str) -> str:
    r = subprocess.run([sys.executable, str(root / "scripts/process/process_kpis.py"), *args],
                       cwd=root, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout


def _by_issue(m, root: Path, **kw) -> dict:
    return {it["issue"]: it for it in m.flow_items(root, **kw)}


def _alpha_beta(render, tmp_path, **mods) -> Path:
    """#7 merged by the train, #8 by `finish` (rebased: its commits' commit dates are the merge's)."""
    out = _merges_repo(render, tmp_path, **mods)
    _train_merge(out, "7-alpha", [
        ("docs: plan alpha", {".process-work/plans/2026-03-02-alpha.md": _plan_text(7)}, _at(2)),
        ("feat: alpha (#7)", {"src/alpha.py": _lines(10)}, _at(3))],
        "train: merge 7-alpha\n\nCloses #7", _at(4, 12))
    _finish_merge(out, "8-beta", [
        ("docs: plan beta", {".process-work/plans/2026-03-05-beta.md": _plan_text(8, 3)}, _at(5)),
        ("fix: beta (#8)", {"src/beta.py": _lines(5)}, _at(6))],
        ["2026-03-05-beta.md"], _at(10, 12))
    return out


def test_a_clone_counts_a_train_work_and_a_finish_work_from_git(render, tmp_path):
    """#341 AC-1/AC-3/AC-5: a fresh clone holds no host trace, and `baseline` said `works 0` —
    the merged works come from the integration branch: end from git, start from the earliest
    author time (it survives the rebase `finish` does), product lines over the range."""
    out = _alpha_beta(render, tmp_path)
    clone = _clone(out, tmp_path)
    assert json.loads(_cli(clone, "baseline", "--json"))[0]["works"] == 2
    items = _by_issue(_flow_module(clone), clone)
    alpha, beta = items[7], items[8]
    assert alpha["merged"] == {"value": _dt(4, 12), "quality": "measured"}
    assert alpha["start"] == {"value": _dt(2), "quality": "estimated"}
    assert alpha["product_lines"] == {"value": 10, "quality": "measured"}
    # the archive commit lies before rebase, suite and push: the end is an estimate
    assert beta["merged"] == {"value": _dt(10, 12), "quality": "estimated"}
    assert beta["start"] == {"value": _dt(5), "quality": "estimated"}  # not ≈ the end after the rebase
    assert beta["product_lines"] == {"value": 5, "quality": "measured"}
    text = _cli(clone, "baseline")
    assert "population: 2 merged works — git 2 (1 train, 1 finish merges), host reports only 0" in text, text
    assert "shallow clone" not in text
    # a shallow clone cuts the history at its boundary commit: the header says so
    shallow = tmp_path / "shallow"
    subprocess.run(["git", "clone", "-q", "--depth", "1", f"file://{out}", str(shallow)], check=True,
                   capture_output=True)
    assert "shallow clone" in _cli(shallow, "baseline")


def test_a_failed_history_read_is_not_read_in_every_report_of_the_run(render, tmp_path):
    """On a cold cache the whole-history `git log` ran past its timeout: `flow_items` saw no
    events and `baseline` printed `works 0` while its header, read a moment later, counted 64
    train merges (dry run on a consumer clone). One run, one answer: a failed read stays
    failed for the run and the header says git was not read, never `git 0`."""
    out = _alpha_beta(render, tmp_path)
    clone = _clone(out, tmp_path)
    m = _flow_module(clone)
    calls = {"n": 0}
    real = m._git_out

    def flaky(root, *args, **kw):
        if args and args[0] == "log" and "--name-only" in args:
            calls["n"] += 1
            if calls["n"] == 1:
                return None  # the first whole-history read fails, a later one would succeed
        return real(root, *args, **kw)

    m._git_out = flaky
    m._EVENTS_READ.clear()
    items = m.flow_items(clone)
    lo, hi = m._window("2026-01-01:2027-01-01")
    pop = m._population(clone, [it for it in items if it.get("source") in ("git", "both")], lo, hi, m._plans(clone),
                        m._review_rounds(clone))
    assert pop["why"], pop  # not read — and not a second, contradicting read
    assert "git not read" in m._population_text(pop)


def test_stacked_phases_are_one_work_and_a_fix_after_the_first_merge_escaped(render, tmp_path):
    """Two merges of one issue are one work (lines summed, start from the first); a fix under
    the same issue after the first merge is an escape — on the host and on a clone alike, and
    a work the host also reports counts once, at git's time."""
    from datetime import datetime, timezone
    out = _merges_repo(render, tmp_path)
    _train_merge(out, "9-one", [("feat: one (#9)", {"src/a.py": _lines(10)}, _at(2))],
                 "train: merge 9-one\n\nRefs #9", _at(3, 12))
    _train_merge(out, "9-two", [("fix: guard the edge (#9)\n\nRegression-of: #9", {"src/b.py": _lines(4)}, _at(5))],
                 "train: merge 9-two\n\nCloses #9", _at(6, 12))
    clone = _clone(out, tmp_path)
    (out / ".git/process-tower").mkdir()
    _report(out, "2026-03-03T12:05:00", "done", "9-one", 9)
    _report(out, "2026-03-06T12:05:00", "done", "9-two", 9)
    now = datetime(2026, 10, 1, tzinfo=timezone.utc)
    for root in (clone, out):
        items = [it for it in _flow_module(root).flow_items(root, now=now) if it["issue"] == 9]
        assert len(items) == 1, items
        [it] = items
        assert it["product_lines"]["value"] == 14 and it["start"]["value"] == _dt(2)
        assert it["merged"]["value"] == _dt(6, 12)  # git's time before the report's
        assert it["escapes"]["value"] == 1 and it["escapes"]["window_open"] is False, (root, it["escapes"])
    assert it["source"] == "both"


def test_a_merge_of_two_issues_is_two_works_and_one_event(render, tmp_path):
    from datetime import datetime, timezone
    out = _merges_repo(render, tmp_path)
    _train_merge(out, "10-pair", [("feat: pair", {"src/p.py": _lines(3)}, _at(2))],
                 "train: merge 10-pair\n\nCloses #10\nCloses #11", _at(3, 12))
    m = _flow_module(out)
    items = _by_issue(m, out)
    assert items[10]["product_lines"]["value"] == items[11]["product_lines"]["value"] == 3
    t = m.load_table(out, weeks=1, now=datetime(2026, 3, 7, tzinfo=timezone.utc))
    assert t["weeks"][0]["merges"] == 1


def test_a_merge_without_a_marker_or_claim_makes_the_next_range_mixed(render, tmp_path):
    """A planless run-up merged by hand falls into the next finish range, which is mixed: its
    lines and start are estimates, and counted. A commit straight onto main before a train
    merge is no part of the train's branch: it stays out of the merge's lines (a dry run on a
    consumer clone put 200 000 lines of unmarked history into one train merge) and is counted
    as a commit outside any merge range."""
    out = _merges_repo(render, tmp_path)
    _train_merge(out, "1-first", [("feat: first (#1)", {"src/one.py": _lines(2)}, _at(2))],
                 "train: merge 1-first\n\nCloses #1", _at(2, 12))
    _g(out, "checkout", "-q", "-b", "spike", "main")
    _put(out, "feat: spike", {"src/spike.py": _lines(7)}, _at(3))
    _g(out, "checkout", "-q", "main")
    _g(out, "merge", "-q", "--no-ff", "-m", "Merge branch 'spike'", "spike", when=_at(3, 12))
    _finish_merge(out, "12-gamma", [
        ("docs: plan gamma", {".process-work/plans/2026-03-04-gamma.md": _plan_text(12)}, _at(4)),
        ("feat: gamma (#12)", {"src/g.py": _lines(4)}, _at(5))], ["2026-03-04-gamma.md"], _at(6, 12))
    _put(out, "feat: straight onto main", {"src/direct.py": _lines(2)}, _at(7))
    _train_merge(out, "13-delta", [("feat: delta (#13)", {"src/d.py": _lines(1)}, _at(8))],
                 "train: merge 13-delta\n\nCloses #13", _at(8, 12))
    items = _by_issue(_flow_module(out), out)
    assert items[12]["product_lines"] == {"value": 11, "quality": "estimated"}
    assert items[12]["start"] == {"value": _dt(3), "quality": "estimated"}
    assert items[13]["product_lines"] == {"value": 1, "quality": "measured"}
    assert items[13]["start"] == {"value": _dt(8), "quality": "estimated"}
    assert items[1]["product_lines"] == {"value": 2, "quality": "measured"}
    text = _cli(out, "baseline")
    assert "mixed ranges 1" in text and "commits outside a merge range 1" in text, text


def test_the_first_finish_without_a_predecessor_has_unknown_lines_and_start(render, tmp_path):
    """Without a merge before it, the range would swallow the onboarding commit."""
    out = _merges_repo(render, tmp_path)
    _finish_merge(out, "14-first", [
        ("docs: plan first", {".process-work/plans/2026-03-02-first.md": _plan_text(14)}, _at(2)),
        ("feat: first (#14)", {"src/f.py": _lines(3)}, _at(3))], ["2026-03-02-first.md"], _at(4, 12))
    [it] = _flow_module(out).flow_items(out)
    assert it["issue"] == 14 and it["merged"]["quality"] == "estimated"
    assert it["product_lines"] == {"value": None, "quality": "missing"}
    assert it["start"] == {"value": None, "quality": "missing"}
    text = _cli(out, "works")
    row = next(ln for ln in text.splitlines() if ln.split()[:1] == ["#14"])
    assert " 0 " not in f" {row} " and "—" in row, row


def test_a_plan_that_stays_active_joins_its_first_train_merge_through_the_branch_plans(render, tmp_path):
    """A train merge of a plan with `plan-stays-active` names no `Closes`/`Refs`: its issue
    comes from the plans on its branch side (`merge^2`)."""
    out = _merges_repo(render, tmp_path)
    plan = {".process-work/plans/2026-03-02-long.md": _plan_text(15, extra="plan-stays-active: two phases\n")}
    _train_merge(out, "15-long", [("docs: plan long", plan, _at(2)),
                                  ("feat: long part one", {"src/l.py": _lines(6)}, _at(3))],
                 "train: merge 15-long", _at(4, 12))
    _train_merge(out, "15-long-two", [("feat: long part two (#15)", {"src/m.py": _lines(4)}, _at(5))],
                 "train: merge 15-long-two\n\nCloses #15", _at(6, 12))
    it = _by_issue(_flow_module(out), out)[15]
    assert it["product_lines"]["value"] == 10 and it["start"]["value"] == _dt(2)
    assert it["merged"]["value"] == _dt(6, 12) and len(it["events"]) == 2


def test_escapes_read_the_integration_ref_and_a_failing_log_is_unknown(render, tmp_path, monkeypatch):
    """A clone whose local main is behind origin/main still sees the escape (`integration_ref`);
    a `git log` that fails is unknown, never "no escapes"."""
    from datetime import datetime, timezone
    out = _merges_repo(render, tmp_path)
    _train_merge(out, "16-x", [("feat: x (#16)", {"src/x.py": _lines(3)}, _at(2))],
                 "train: merge 16-x\n\nCloses #16", _at(2, 12))
    _put(out, "fix: x again\n\nRegression-of: #16", {"src/x.py": _lines(4)}, _at(5))
    clone = _clone(out, tmp_path)
    _g(clone, "reset", "-q", "--hard", "HEAD~1")
    now = datetime(2026, 10, 1, tzinfo=timezone.utc)
    assert _by_issue(_flow_module(clone), clone, now=now)[16]["escapes"]["value"] == 1
    host = _flow_repo(render, tmp_path / "host")
    m = _flow_module(host)
    import tower
    monkeypatch.setattr(tower, "integration_ref", lambda root: "refs/heads/no-such-branch")
    [it] = m.flow_items(host, issue=12, now=now)
    assert it["escapes"]["value"] is None and it["escapes"]["quality"] == "missing"
    assert m._regressions(host, "refs/heads/no-such-branch") is None


def test_a_merge_without_an_issue_is_counted_and_regression_of_claims_nothing(render, tmp_path):
    out = _merges_repo(render, tmp_path)
    _train_merge(out, "misc", [("chore: tidy", {"src/t.py": _lines(1)}, _at(2))],
                 "train: merge misc\n\nRegression-of: #3", _at(2, 12))
    m = _flow_module(out)
    assert 3 not in _by_issue(m, out)
    assert m.merged_works(out)["unclaimed"] == 1
    assert "merges without an issue 1" in _cli(out, "baseline")


def _host_report(out: Path, ts: str, state: str, worker: str, issue: int, **extra) -> None:
    import time
    d = out / ".git/process-tower"
    d.mkdir(exist_ok=True)
    with (d / "reports.jsonl").open("a") as fh:
        fh.write(json.dumps({"ts": ts + time.strftime("%z"), "host": "h", "worker": worker, "branch": worker,
                             "issue": issue, "state": state, "note": "", "cwd": "", **extra}) + "\n")


def test_works_gives_one_row_per_work_and_medians_by_tier_and_kind(render, tmp_path):
    """#314: per work its tier, kind, plan and code rounds, lead, session time and sessions per
    model family where the host has them (`—` elsewhere, never 0), product lines; median and
    p90 by tier and by kind."""
    from datetime import datetime, timezone
    out = _alpha_beta(render, tmp_path)
    _journal(out, _review(7, 1, "block") + _review(7, 2, "pass") + _review("7-plan", 1, "pass")
             + _review(8, 1, "pass", tier=3))
    (out / ".git/process-dispatch").mkdir()
    (out / ".git/process-dispatch/7-alpha-execute-20260302-100000.log").write_text("")
    _host_report(out, "2026-03-02T13:00:00", "pushed", "7-alpha", 7, model="claude-opus-5", phase="execute")
    m = _flow_module(out)
    t = m.works_table(out, *m._window("2026-03-01:2026-04-01"))
    rows = {r["issue"]: r for r in t["rows"]}
    assert (rows[7]["tier"], rows[7]["kind"], rows[7]["plan_rounds"], rows[7]["code_rounds"]) == ("2", "change", 1, 2)
    assert rows[7]["work_h"] == 3.0 and rows[7]["sessions"] == {"claude": 1}
    assert rows[7]["product_lines"] == 10
    assert (rows[8]["tier"], rows[8]["kind"], rows[8]["plan_rounds"], rows[8]["code_rounds"]) == ("3", "fix", None, 1)
    assert rows[8]["work_h"] is None and rows[8]["sessions"] is None
    assert rows[8]["lead_h"] == round((datetime(2026, 3, 10, 12, tzinfo=timezone.utc)
                                       - datetime(2026, 3, 5, 9, tzinfo=timezone.utc)).total_seconds() / 3600, 1)
    assert t["by_tier"]["2"]["code_rounds"] == {"n": 1, "median": 2, "p90": 2}
    assert t["by_kind"]["fix"]["product_lines"] == {"n": 1, "median": 5, "p90": 5}
    text = _cli(out, "works", "--window", "2026-03-01:2026-04-01")
    row8 = next(ln for ln in text.splitlines() if ln.split()[:1] == ["#8"])
    assert row8.split()[1:3] == ["3", "fix"] and row8.count("—") >= 3, row8
    assert "claude 1" in next(ln for ln in text.splitlines() if ln.split()[:1] == ["#7"])
    assert "by tier" in text and "by kind" in text
    assert json.loads(_cli(out, "works", "--json"))["rows"]


def test_rounds_by_number_splits_code_and_plan_reviews(render, tmp_path):
    """#318: per round 1, 2, 3, ≥4 — blockers, works still blocked, blocks on lines unchanged
    since round 1 (plan reviews `n/a`) and the round's cost, `unknown` where none is recorded."""
    out = _render(render, tmp_path, github_issues=True)
    _g(out, "init", "-q", "-b", "main")
    _journal(out, _review(9, 1, "block") + _review(9, 2, "block") + _review(9, 3, "block")
             + _review(9, 4, "block") + _review(9, 5, "pass") + _review(10, 1, "pass")
             + _review("9-plan", 1, "block") + _review("9-plan", 2, "pass"))
    _report_file(out, "9-r1", "#9", _finding("blocker") * 2 + _finding("major"), rnd=1)
    _report_file(out, "9-r2", "#9", _finding("blocker"), rnd=2)
    _report_file(out, "9-r4", "#9", _finding("blocker") * 3, rnd=4)
    _report_file(out, "9-r5", "#9", _finding("blocker") * 5, rnd=5)
    _report_file(out, "9-plan-r1", "#9", _finding("blocker") * 4, rnd=1, phase="plan")
    _host_report(out, "2026-03-02T10:00:00", "blocked", "9-x", 9, phase="review", epoch=100,
                 usage={"input": 100, "cached": 0, "output": 50})
    m = _flow_module(out)
    t = m.rounds_by_number(out)
    code, plan = t["code"], t["plan"]
    assert code["1"]["blockers_median"] == 2 and code["1"]["blocked"] == (1, 2)
    assert code[">=4"]["blockers_median"] == 4 and code[">=4"]["blocked"] == (1, 2)
    assert code["3"]["blockers_median"] is None  # no report of round 3: not zero
    assert code["1"]["cost"] == {"median": 150, "known": 1, "unknown": 1}
    assert code["2"]["cost"] == {"median": None, "known": 0, "unknown": 1}
    assert plan["1"]["blockers_median"] == 4 and plan["1"]["blocked"] == (1, 1)
    assert plan["1"]["unchanged"] == "n/a" and plan["2"]["blocked"] == (0, 1)
    text = _rounds(out)
    assert "by round — code reviews over 2 works" in text and "by round — plan reviews over 1 works" in text
    row = next(ln for ln in text.splitlines() if ln.split()[:1] == ["1"])
    assert "unknown" in row and "1/2" in row, row
    # without the FINDING reader the blocker medians are not read, never zeros
    bare = _render(render, tmp_path / "bare")
    _journal(bare, _review(9, 1, "block") + _review(9, 2, "pass"))
    assert _flow_module(bare).rounds_by_number(bare)["code"]["1"]["blockers_median"] == "not read"


def test_baseline_gives_escapes_per_tier_over_closed_windows_and_marks_thin(render, tmp_path, monkeypatch,
                                                                            capsys):
    """#320: per tier the merged works, the escaped ones and their rate over closed windows
    (an open window counts beside, never in the denominator), median rounds and tokens; thin
    under ~20 works."""
    out = _render(render, tmp_path, github_issues=True)
    archive = out / ".process-work/plans/archive"
    archive.mkdir(parents=True, exist_ok=True)
    for n, tier in ((1, 2), (2, 2), (3, 2), (4, 3), (5, 3)):
        (archive / f"2026-03-0{n}-w{n}.md").write_text(_plan_text(n, tier))
    _journal(out, "".join(_review(n, 1, "pass") for n in (1, 2, 3))
             + "".join(_review(n, 1, "block") + _review(n, 2, "block") + _review(n, 3, "pass", tier=3)
                       for n in (4, 5)))

    def item(n, escapes, open_=False, tokens=None):
        return {"issue": n, "merged": {"value": "2026-03-05T12:00:00+00:00"}, "lead_s": {"value": 0},
                "tokens": {"value": tokens}, "escapes": {"value": escapes, "window_open": open_}}
    items = [item(1, 1), item(2, 0), item(3, 2, open_=True), item(4, 1, tokens={"output_tokens": 900}),
             item(5, 0, tokens={"output_tokens": 100})]
    k = _kpis_module(out)
    got = k.baseline_numbers(out, *k._window("2026-03-01:2026-04-01"), items=items, commits=[])
    two, three = got["by_tier"]["2"], got["by_tier"]["3"]
    assert (two["works"], two["escaped"], two["closed"], two["open"], two["rate"]) == (3, 1, 2, 1, 0.5)
    assert (three["works"], three["escaped"], three["closed"], three["rate"]) == (2, 1, 2, 0.5)
    assert (two["rounds"], three["rounds"]) == (1, 3)
    assert (two["tokens"], three["tokens"]) == (None, 500.0)
    assert two["thin"] and three["thin"]
    monkeypatch.setattr(k, "flow_items", lambda root: items)
    assert k.baseline(out, [k._window("2026-03-01:2026-04-01")]) == 0
    text = capsys.readouterr().out
    assert "tier 2: works 3, escaped 1/2 closed (50 %), open 1" in text and "thin" in text, text


def test_load_counts_process_against_product_lines_per_merge_event(render, tmp_path):
    from datetime import datetime, timezone
    out = _merges_repo(render, tmp_path)
    _train_merge(out, "20-docs", [("docs: plan only", {".process-work/plans/2026-03-02-d.md": _plan_text(20)},
                                   _at(2))], "train: merge 20-docs\n\nCloses #20", _at(2, 12))
    _train_merge(out, "21-both", [("feat: both (#21)", {"src/b.py": _lines(4),
                                                         ".process-work/plans/2026-03-03-b.md": _plan_text(21)},
                                   _at(3))], "train: merge 21-both\n\nCloses #21", _at(3, 12))
    m = _flow_module(out)
    t = m.load_table(out, weeks=2, now=datetime(2026, 3, 7, tzinfo=timezone.utc))
    w = t["weeks"][0]
    assert (w["merges"], w["without_product"], w["product_lines"]) == (2, 1, 4)
    assert w["process_lines"] == 2 * len(_plan_text(20).splitlines())
    assert w["process_files_median"] == 1
    assert t["weeks"][1]["merges"] == 0
    text = _cli(out, "load", "--weeks", "60")  # back to the merges of March
    assert "[load]" in text and "merges without a product file" in text and "proxy" in text


def test_load_counts_the_lines_committed_outside_any_merge_range(render, tmp_path):
    """Records committed straight onto the integration branch (a steward's journal, a review
    log) belong to no merge, yet they are process load — a dry run on a consumer clone showed a
    low merge ratio while most process lines lay outside the merges. `load` names them apart."""
    from datetime import datetime, timezone
    out = _merges_repo(render, tmp_path)
    _train_merge(out, "23-a", [("feat: a (#23)", {"src/a.py": _lines(2)}, _at(2))],
                 "train: merge 23-a\n\nCloses #23", _at(2, 12))
    _put(out, "docs: steward journal", {".process-work/journal/2026-03-03.md": _lines(9)}, _at(3))
    _put(out, "chore: straight onto main", {"src/s.py": _lines(3)}, _at(3, 10))
    _train_merge(out, "24-b", [("feat: b (#24)", {"src/b.py": _lines(1)}, _at(4))],
                 "train: merge 24-b\n\nCloses #24", _at(4, 12))
    m = _flow_module(out)
    w = m.load_table(out, weeks=1, now=datetime(2026, 3, 7, tzinfo=timezone.utc))["weeks"][0]
    assert (w["product_lines"], w["outside_process_lines"], w["outside_product_lines"]) == (3, 9, 3), w
    assert "outside merge ranges" in _cli(out, "load", "--weeks", "60")


def _size_repo(render, tmp_path) -> Path:
    """Four works, one per size step, with 1-4 review rounds; #31 spans two directories."""
    out = _merges_repo(render, tmp_path)
    for n, (day, files) in enumerate(((2, {"src/s.py": _lines(50)}),
                                      (3, {"src/m.py": _lines(150), "web/m.ts": _lines(150)}),
                                      (4, {"src/l.py": _lines(800)}),
                                      (5, {"README.md": _lines(2000)})), start=30):
        _train_merge(out, f"{n}-w", [(f"feat: w{n} (#{n})", files, _at(day))],
                     f"train: merge {n}-w\n\nCloses #{n}", _at(day, 12))
    passes = ((30, 1), (31, 2), (32, 3), (33, 4))
    _journal(out, "".join(_review(n, r, "block") for n, last in passes for r in range(1, last))
             + "".join(_review(n, last, "pass") for n, last in passes))
    return out


def test_size_gives_rounds_by_product_lines_and_by_stacks(render, tmp_path):
    out = _size_repo(render, tmp_path)
    m = _flow_module(out)
    t = m.size_table(out, *m._window(":"))
    b = t["buckets"]
    assert [b[k]["works"] for k in ("<200", "200-500", "500-1500", ">1500")] == [1, 1, 1, 1]
    assert (b["<200"]["rounds_median"], b[">1500"]["rounds_median"]) == (1, 4)
    assert b["500-1500"]["share_3plus"] == 1.0 and b["<200"]["share_3plus"] == 0.0
    assert b["<200"]["rounds_per_100_lines"] == 2.0  # 1 round over 50 lines
    assert b["200-500"]["process_per_product_line"] == 0.0
    assert t["stacks"] == "not read"  # no testing.local.json
    (out / "docs/process/testing.local.json").write_text("{")
    assert m.size_table(out, *m._window(":"))["stacks"] == "not read"
    (out / "docs/process/testing.local.json").write_text(json.dumps({"stacks": {
        "backend": {"paths": ["src/"], "runner": ["pytest", "{paths}"], "full": ["pytest"]},
        "frontend": {"paths": ["web/"], "runner": ["vitest", "{paths}"], "full": ["vitest"]}}}))
    got = m.size_table(out, *m._window(":"))
    s = got["stacks"]
    assert s["one stack"]["works"] == 2 and s["several stacks"]["works"] == 1 and s["no stack"]["works"] == 1
    assert s["several stacks"]["rounds_median"] == 2
    top = {f["file"]: f for f in got["top_files"]}
    assert top["src/m.py"]["works"] == 1 and top["src/m.py"]["co_files_median"] == 1
    text = _cli(out, "size")
    assert "[size]" in text and "several stacks" in text and "proxy" in text


def test_size_lists_code_files_as_hotspots_not_shared_documents(render, tmp_path):
    """A dry run on a consumer clone listed an inventory document, an API contract and a
    Makefile as the files most works touched — shared bookkeeping, not code that couples. The
    hotspot list and its "alongside" count read code files (the `_CODE_EXT` the change-failure
    proxy already owns)."""
    out = _merges_repo(render, tmp_path)
    _train_merge(out, "21-a", [("feat: a (#21)", {"src/a.py": _lines(3), "docs/inventory.md": _lines(1),
                                                  "Makefile": _lines(1)}, _at(2))],
                 "train: merge 21-a\n\nCloses #21", _at(2, 12))
    _train_merge(out, "22-b", [("feat: b (#22)", {"src/b.py": _lines(3), "docs/inventory.md": _lines(1, "y"),
                                                  "Makefile": _lines(1, "y")}, _at(3))],
                 "train: merge 22-b\n\nCloses #22", _at(3, 12))
    m = _flow_module(out)
    top = {f["file"]: f for f in m.size_table(out, *m._window(":"))["top_files"]}
    assert "docs/inventory.md" not in top and "Makefile" not in top, top
    assert top["src/a.py"]["works"] == 1 and top["src/a.py"]["co_files_median"] == 0


def test_size_counts_lines_on_vanished_files_and_follows_renames_forward(render, tmp_path):
    out = _merges_repo(render, tmp_path)
    _train_merge(out, "40-a", [("feat: a (#40)", {"src/gone.py": _lines(10), "src/old.py": _lines(30)}, _at(2))],
                 "train: merge 40-a\n\nCloses #40", _at(2, 12))
    _g(out, "checkout", "-q", "-b", "41-b", "main")
    _g(out, "mv", "src/old.py", "src/new.py")
    _put(out, "refactor: rename (#41)", {"src/gone.py": None}, _at(3))
    _g(out, "checkout", "-q", "main")
    _g(out, "merge", "-q", "--no-ff", "-m", "train: merge 41-b\n\nCloses #41", "41-b", when=_at(3, 12))
    m = _flow_module(out)
    # gone.py: 10 lines added, 10 deleted — vanished; old.py lives on as new.py
    assert m.size_table(out, *m._window(":"))["vanished"] == {"lines": 20, "of": 50, "share": 0.4}


def test_size_steps_do_not_share_a_boundary_and_unreviewed_rounds_are_unknown(render, tmp_path):
    """A cross-model review: 500 sat in "200-500" while "500-1500" reads as starting there;
    and a step whose works carry no REVIEW round printed rounds per 100 lines as `n/a` — the
    mark for a step without product lines — instead of unknown."""
    out = _merges_repo(render, tmp_path)
    _train_merge(out, "50-a", [("feat: a (#50)", {"src/a.py": _lines(50)}, _at(2))],
                 "train: merge 50-a\n\nCloses #50", _at(2, 12))
    m = _flow_module(out)
    assert [m._size_step(n) for n in (199, 200, 499, 500, 1500, 1501)] == [
        "<200", "200-500", "200-500", "500-1500", "500-1500", ">1500"]
    b = m.size_table(out, *m._window(":"))["buckets"]
    assert (b["<200"]["works"], b["<200"]["rounds_per_100_lines"]) == (1, None)
    assert b["200-500"]["rounds_per_100_lines"] == "n/a"


def test_size_follows_a_rename_of_a_file_first_merged_before_the_window(render, tmp_path):
    """A work's files sum over all its events; a file it added before the window and renamed
    inside it counted twice among the hotspots (old and new name)."""
    out = _merges_repo(render, tmp_path)
    _train_merge(out, "60-a", [("feat: a (#60)", {"src/old.py": _lines(30)}, _at(2))],
                 "train: merge 60-a\n\nRefs #60", _at(2, 12))
    _g(out, "checkout", "-q", "-b", "60-b", "main")
    _g(out, "mv", "src/old.py", "src/new.py")
    _put(out, "refactor: rename (#60)", {"src/c.py": _lines(2)}, _at(4))
    _g(out, "checkout", "-q", "main")
    _g(out, "merge", "-q", "--no-ff", "-m", "train: merge 60-b\n\nCloses #60", "60-b", when=_at(4, 12))
    m = _flow_module(out)
    top = {f["file"] for f in m.size_table(out, *m._window("2026-03-04:"))["top_files"]}
    assert top == {"src/new.py", "src/c.py"}, top


def test_load_does_not_count_merges_without_a_product_file_when_no_range_is_known(render, tmp_path):
    """Every merge of the week with an unknown range: the lines read `—`, and so must the
    count of merges without a product file — not a measured 0."""
    from datetime import datetime, timezone
    out = _merges_repo(render, tmp_path)
    _finish_merge(out, "70-a", [("feat: a (#70)", {"src/a.py": _lines(3),
                                                   ".process-work/plans/2026-03-02-a.md": _plan_text(70)}, _at(2))],
                  ["2026-03-02-a.md"], _at(2, 12))  # the first finish: no event before it
    m = _flow_module(out)
    w = m.load_table(out, weeks=1, now=datetime(2026, 3, 7, tzinfo=timezone.utc))["weeks"][0]
    assert (w["merges"], w["unknown"], w["without_product"]) == (1, 1, None), w


def test_report_runs_the_families_the_doc_names(render, tmp_path):
    import re
    out = _alpha_beta(render, tmp_path)
    text = _cli(out, "report")
    families = ["cost", "cfr", "clusters", "share", "flow", "losses", "nodes", "baseline", "works", "load", "size"]
    assert set(re.findall(r"^\[([a-z-]+)\]", text, re.MULTILINE)) == set(families), text
    doc = " ".join((out / "docs/process/modules/telemetry.md").read_text().split())
    listed = ", ".join(f"`{f}`" for f in families[:-1]) + f" and `{families[-1]}`"
    assert f"`report` runs {listed}" in doc
    for family in ("works", "load", "size"):
        assert f"| `{family}` |" in doc
