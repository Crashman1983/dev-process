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
    assert r.returncode == 0 and "issue #7" in r.stdout and "tokens: not measured (not-configured)" in r.stdout, r.stdout + r.stderr
    (tmp_path / "t").mkdir()
    (tmp_path / "t" / "s.jsonl").write_text('{"output_tokens": 5}\n')
    (out / ".git/process-dispatch").mkdir()
    (out / ".git/process-dispatch/7-x.json").write_text(json.dumps({"issue": 7, "worktree": str(tmp_path)}))
    (out / "docs/process/model-policy.local.json").write_text(json.dumps({"transcripts": "{worktree}/t/*.jsonl"}))
    r = _kpis(out, "cost", "--issue", "7")
    assert "tokens: 5 output over 1 sessions" in r.stdout, r.stdout + r.stderr


def test_cost_reads_the_recorded_cost_lines_and_the_last_set_counts(render, tmp_path):
    """v2.94 E2: `cost` reads the COST lines `finish --apply` wrote next to its live output; with
    several sets for one work — a second branch of the issue, two shards folded into one archive
    month — the last counts (by the date in the file name, then by line)."""
    out = _render(render, tmp_path)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=out, check=True)
    for shard in ("archive", "issue-7", "issue-8"):
        (out / JOURNAL / shard).mkdir(parents=True, exist_ok=True)
    _journal(out, "# 2026-09\n\n## .process-work/journal/issue-7/2026-09-01.md\n\n"
                  "COST work=7 phase=plan wall_seconds=10 tokens=1\n"
                  "COST work=7 phase=execute wall_seconds=20 tokens=2\n"
                  "COST work=7 phase=plan wall_seconds=11 tokens=3\n"
                  "COST work=7 phase=execute wall_seconds=21 tokens=4\n", name="archive/2026-09.md")
    _journal(out, "# 2026-10-02\n\nREVIEW notes\n\n"
                  "COST work=7 phase=plan wall_seconds=100 tokens=- not-measured: not-configured\n"
                  "COST work=7 phase=execute wall_seconds=200 tokens=30 not-measured: partial: remote\n"
                  "COST work=8 phase=all wall_seconds=5 tokens=9\n", name="issue-7/2026-10-02.md")
    _journal(out, "COST work=8 phase=all wall_seconds=6 tokens=12\n", name="issue-8/2026-10-03.md")
    got = _flow_module(out).recorded_costs(out)
    assert got == {
        7: [{"phase": "plan", "wall_seconds": 100, "tokens": None, "reason": "not-configured"},
            {"phase": "execute", "wall_seconds": 200, "tokens": 30, "reason": "partial: remote"}],
        8: [{"phase": "all", "wall_seconds": 6, "tokens": 12, "reason": None}]}, got
    r = _kpis(out, "cost")
    assert r.returncode == 0, r.stderr
    assert "#7 execute wall 200 s, tokens 30 (not-measured: partial: remote)" in r.stdout, r.stdout
    assert "#8 all wall 6 s, tokens 12" in r.stdout and "wall 5 s" not in r.stdout
    r = _kpis(out, "cost", "--issue", "7")
    assert "tokens: not measured (not-configured)" in r.stdout  # the live line stays
    assert "#7 plan wall 100 s, tokens - (not-measured: not-configured)" in r.stdout and "#8" not in r.stdout
    r = _kpis(out, "cost", "--issue", "9")
    assert "no COST lines for #9" in r.stdout, r.stdout
    # within one file, a phase named twice starts the next set (two folded shards)
    (out / JOURNAL / "issue-7/2026-10-02.md").unlink()
    assert [(c["phase"], c["wall_seconds"]) for c in _flow_module(out).recorded_costs(out)[7]] == [
        ("plan", 11), ("execute", 21)]


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
    # no mandate: the limit of before, 40 %
    assert "over the limit (50 % > 40 % over 2 weeks)" in r.stdout, r.stdout


def _share_repo(out: Path) -> None:
    """Four commits on main, two of them process only (50 %)."""
    for args in (["init", "-q", "-b", "main"], ["config", "user.email", "t@t"], ["config", "user.name", "t"],
                 ["add", "-A"], ["commit", "-q", "-m", "base"]):
        subprocess.run(["git", *args], cwd=out, check=True, capture_output=True)
    for i, rel in enumerate([".process-work/journal/a.md", ".process-work/journal/a.md", "src/x.py"]):
        p = out / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f"{i}\n")
        subprocess.run(["git", "add", "-A"], cwd=out, check=True)
        subprocess.run(["git", "commit", "-q", "-m", f"c{i}"], cwd=out, check=True)


def test_share_judges_the_mandate_limit_over_the_mandate_weeks(render, tmp_path):
    """v2.97 B5 (#416): `share` reads `steering.process_share_max` and
    `process_share_window_weeks`; `--weeks` still wins over the mandate's weeks."""
    out = _render(render, tmp_path)
    _share_repo(out)
    r = _kpis(out, "share")  # no mandate: four weeks, as before
    assert r.returncode == 0, r.stdout + r.stderr
    assert "week -3:" in r.stdout and "week -4:" not in r.stdout, r.stdout
    assert "over the limit (50 % > 40 % over 4 weeks)" in r.stdout, r.stdout
    mandate = out / "docs/process/optimization.local.json"
    mandate.write_text(json.dumps({"steering": {"process_share_max": 0.6, "process_share_window_weeks": 3}}))
    r = subprocess.run([sys.executable, str(out / "scripts/process/process_kpis.py"), "share"],
                       cwd=out, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "week -2:" in r.stdout and "week -3:" not in r.stdout, r.stdout
    assert "within the limit (50 % ≤ 60 % over 3 weeks)" in r.stdout, r.stdout
    assert "over the limit" not in r.stdout
    mandate.write_text(json.dumps({"steering": {"process_share_max": 0.25, "process_share_window_weeks": 3}}))
    r = subprocess.run([sys.executable, str(out / "scripts/process/process_kpis.py"), "share", "--weeks", "1"],
                       cwd=out, capture_output=True, text=True)
    assert "week -1:" not in r.stdout, r.stdout  # --weeks wins
    assert "over the limit (50 % > 25 % over 1 week)" in r.stdout, r.stdout
    assert "25 %" in r.stdout.splitlines()[-1]  # the action names the limit it judged


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
    # each stamp carries the local offset of its own date, not today's: on a DST change between
    # the fixture's October dates and the day the suite runs, today's offset moved the merge an
    # hour past the deploy (failed from 2026-11-01 under TZ=America/New_York)
    from datetime import datetime as _dt
    (tower / "reports.jsonl").write_text("".join(
        json.dumps({"ts": _dt.fromisoformat(ts).astimezone().isoformat(), "host": "h", "worker": "12-faster", "branch": "12-faster",
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
    from datetime import datetime
    with (out / ".git/process-tower/reports.jsonl").open("a") as fh:
        # the offset of the stamp's own date (DST), as `_flow_repo` writes it
        fh.write(json.dumps({"ts": datetime.fromisoformat(ts).astimezone().isoformat(), "host": "h", "worker": worker, "branch": worker,
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


def test_losses_confidence_counts_issues_with_a_value_not_all_issues(render, tmp_path):
    """v2.81 D2 (#360): downstream `losses` printed "confidence: high (direct, n=93)" with no
    value for any of the 93 issues — the confidence came from the issue count."""
    out = _flow_repo(render, tmp_path)
    m = _flow_module(out)
    empty = {"value": None, "issues": 0, "missing": 93, "quality": "missing"}
    t = {"issues": 93, "occupancy": {**empty, "unit": "h"}, "delay": {**empty, "unit": "issue-h"},
         "tokens": dict(empty)}
    assert m.losses_confidence(t).startswith("confidence: not measured"), m.losses_confidence(t)
    some = {**t, "delay": {"value": 5.0, "unit": "issue-h", "issues": 30, "missing": 63, "quality": "measured"}}
    text = m.losses_confidence(some)
    assert "sample not representative" in text and "high" not in text, text


def test_session_tokens_count_a_message_once_not_once_per_content_block(render, tmp_path):
    """v2.81 D1 (#360): Claude Code writes one line per content block, each repeating the
    message's usage; `cost` summed every line, `dispatch` counted the message once."""
    import json
    out = _flow_repo(render, tmp_path)
    m = _flow_module(out)
    d = tmp_path / "t"
    d.mkdir()
    line = {"message": {"id": "msg_1", "model": "m", "usage": {"input_tokens": 5, "output_tokens": 40}},
            "requestId": "r1"}
    (d / "s.jsonl").write_text("\n".join(json.dumps(line) for _ in range(3)) + "\n")
    assert m.session_output_tokens(d) == {"s": 40}


def _issue(n, title, state="OPEN", labels=(), created="2026-01-05T10:00:00Z", closed=None, subs=(),
           subs_complete=True):
    return {"number": n, "title": title, "state": state, "createdAt": created, "closedAt": closed,
            "updatedAt": closed or created, "labels": list(labels), "sub_total": len(subs),
            "sub_done": sum(1 for c in subs if c["state"] == "CLOSED"), "subs": list(subs),
            "subs_complete": subs_complete}


def _fetch(issues, cut=None, seen=None):
    """An issue reader under the fetch contract: (issues, why, cut); `seen` records each call."""
    def fetch(_root, since, *, resolve_subs):
        if seen is not None:
            seen.append((since, resolve_subs))
        return issues, None, cut
    return fetch


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
    t = m.outcomes_table(out, days=3650, now=now, fetch=_fetch(issues))
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
    t = m.outcomes_table(out, days=3650, now=now, fetch=_fetch([epic]))
    assert t["epics"][0]["quality"] == "proxy" and t["epics"][0]["days_to_usable"] == 54.58
    assert t["bug_origin"]["coverage"] is None and t["bug_origin"]["blind_spot"] is False
    gone = m.outcomes_table(out, now=now, fetch=lambda _r, _s, **_k: (None, "gh is not installed", None))
    assert gone == {"available": False, "reason": "gh is not installed", "days": 90}
    # a duplicate or not-planned closure is no delivery; an epic grouped after its work is not negative
    dropped = dict(epic, stateReason="NOT_PLANNED")
    bug = _issue(200, "dup", "CLOSED", ["bug", "cause:unknown", "channel:operator", "priority:high"],
                 created="2026-12-01T00:00:00Z", closed="2026-12-01T01:00:00Z")
    bug["stateReason"] = "DUPLICATE"
    late = _issue(101, "[EPIC] grouped later", "CLOSED", created="2026-05-01T00:00:00Z",
                  closed="2026-04-01T00:00:00Z")
    t = m.outcomes_table(out, days=3650, now=now, fetch=_fetch([dropped, bug, late]))
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
                         fetch=_fetch(bugs))
    assert t["bug_origin"]["bugs"] == 1  # the default `bug`, not the letters b, u, g
    assert t["config"]["coverage_target"] == 0.8
    assert len(t["config_problems"]) == 4 and any("colour" in p for p in t["config_problems"])


_FAKE_GH = r'''
import json, pathlib, re, sys
scenario = json.loads(pathlib.Path(SCENARIO).read_text())
args = sys.argv[1:]
if args[0] == "repo":
    print("o/2048")
    sys.exit(0)
given = {}
for flag, kv in zip(args, args[1:]):
    if flag in ("-f", "-F"):
        k, _, v = kv.partition("=")
        given[k] = v
q = given.get("query", "")
rate = {"remaining": scenario.get("remaining", 5000)}
ALIAS = r'(\w+):repository\(owner:"([^"]*)",name:"([^"]*)"\)\{issue\(number:(\d+)\)'


def page(key):
    nodes, nxt = scenario["pages"].get(key, [[], None])
    return {"pageInfo": {"hasNextPage": nxt is not None, "endCursor": nxt}, "nodes": nodes}


code, errors = 0, []
if "issues(" in q:
    states = re.search(r"states:(\w+)", q).group(1)
    since = given.get("since")
    kind = "open" if states == "OPEN" else "closed" if since == scenario["since"] else "late"
    data = {"rateLimit": rate, "repository": {"issues": page(kind + ":" + given.get("after", ""))}}
elif "$number" in q:
    kind = "subs"
    data = {"rateLimit": rate, "repository": {"issue": {"subIssues": page(
        "subs:" + given["number"] + ":" + given.get("after", ""))}}}
elif "timelineItems" in q:
    kind = "timeline"
    data = {"rateLimit": rate}
    for alias, _o, _n, n in re.findall(ALIAS, q):
        data[alias] = {"issue": {"number": int(n), "timelineItems": {"nodes": scenario["timeline"].get(n, [])}}}
else:
    kind = "batch"
    data = {"rateLimit": rate}
    for alias, owner, name, n in re.findall(ALIAS, q):
        node = scenario["issues"].get(owner + "/" + name + "#" + n)
        if node is None:
            errors.append({"message": "Could not resolve to an Issue with the number of " + n})
        data[alias] = {"issue": node}
    code = 1 if errors else 0
with open(LOG, "a") as fh:
    fh.write(json.dumps({"kind": kind, "args": args, **given}) + "\n")
print(json.dumps({"data": data, **({"errors": errors} if errors else {})}))
sys.exit(code)
'''


def _fake_gh(tmp_path, monkeypatch, scenario: dict):
    """A `gh` on PATH that answers each list by `states`, `since` and `after`, the sub-issue
    follow-up by issue and cursor, a batch alias by alias (exit 1 with partial `data` when one
    is missing), and logs every call. Returns a reader of the calls since this setup."""
    import os
    fake = tmp_path / "fakebin"
    fake.mkdir(exist_ok=True)
    (tmp_path / "scenario.json").write_text(json.dumps(scenario))
    log = tmp_path / "gh-calls.jsonl"
    log.write_text("")
    (fake / "gh").write_text(f"#!{sys.executable}\nSCENARIO = {str(tmp_path / 'scenario.json')!r}\n"
                             f"LOG = {str(log)!r}\n" + _FAKE_GH)
    (fake / "gh").chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake}{os.pathsep}{os.environ['PATH']}")
    return lambda: [json.loads(line) for line in log.read_text().splitlines()]


def _node(n, title, state="OPEN", labels=(), created="2026-01-05T10:00:00Z", closed=None, updated=None,
          subs=(), subs_next=None, total=None):
    """One issue as GraphQL answers it in the light form: sub-issues as number and repository."""
    return {"number": n, "title": title, "state": state, "stateReason": "COMPLETED" if state == "CLOSED" else None,
            "createdAt": created, "closedAt": closed, "updatedAt": updated or closed or created,
            "labels": {"nodes": [{"name": lb} for lb in labels]},
            "subIssuesSummary": {"total": len(subs) if total is None else total, "completed": 0},
            "subIssues": {"nodes": [{"number": int(ref.split("#")[1]),
                                     "repository": {"nameWithOwner": ref.split("#")[0]}} for ref in subs],
                          "pageInfo": {"hasNextPage": subs_next is not None, "endCursor": subs_next}}}


_GH_SINCE_TEXT = "2026-12-01T00:00:00Z"


def _gh_since():
    from datetime import datetime, timezone
    return datetime(2026, 12, 1, tzinfo=timezone.utc)


def _gh_scenario(missing=()) -> dict:
    """Epic #700 on the second open page with 61 sub-issues: #1–#59 closed long before the window
    (batch-resolved, the acceptance issue #51 at position 51), #142 from the list, and x/y#5 on
    the epic's second sub-issue page. #140 changes between the lists, #141 closes between them."""
    subs = [f"o/2048#{n}" for n in range(1, 60)] + ["o/2048#142"]
    issues = {f"o/2048#{n}": _node(n, f"part {n}", "CLOSED", ["acceptance"] if n == 51 else (),
                                   closed="2025-06-01T00:00:00Z") for n in range(1, 60)}
    issues["x/y#5"] = _node(5, "elsewhere", "CLOSED", closed="2025-05-01T00:00:00Z")
    for key in missing:
        issues.pop(key)
    epic = _node(700, "[EPIC] product", created="2025-01-01T00:00:00Z", updated="2026-01-01T00:00:00Z",
                 subs=subs, subs_next="s1", total=61)
    return {"since": _GH_SINCE_TEXT, "issues": issues, "pages": {
        "closed:": [[_node(140, "old", "CLOSED", closed="2026-12-02T00:00:00Z")], "c1"],
        "closed:c1": [[_node(142, "part", "CLOSED", closed="2026-12-03T00:00:00Z")], None],
        "open:": [[_node(143, "new work")], "o1"],
        "open:o1": [[epic], None],
        "late:": [[_node(140, "new", "CLOSED", closed="2026-12-02T00:00:00Z", updated="2026-12-05T00:00:00Z"),
                   _node(141, "closed meanwhile", "CLOSED", closed="2026-12-04T00:00:00Z")], None],
        "subs:700:s1": [[{"number": 5, "repository": {"nameWithOwner": "x/y"}}], None]}}


def test_gh_issues_pages_both_lists_and_resolves_sub_issues_in_batches(render, tmp_path, monkeypatch):
    """#417: `outcomes` read the 100 most recently updated issues with 50 sub-issues each —
    Kenni's product epic (82 sub-issues) fell out of the window, its acceptance issue stood past
    position 50. Now: the closed issues of the window, then every open one, paged by creation;
    sub-issues as numbers, resolved against the list and in batches of 50."""
    from datetime import datetime, timezone
    out = _flow_repo(render, tmp_path)
    m = _flow_module(out)
    calls = _fake_gh(tmp_path, monkeypatch, _gh_scenario())
    issues, why, cut = m._gh_issues(out, _gh_since(), resolve_subs=True)
    assert why is None and cut is None
    by = {i["number"]: i for i in issues}
    assert set(by) == {700, 140, 141, 142, 143}  # #700 past the first page, #141 closed between the lists
    assert by[140]["title"] == "new"  # two copies: the newer updatedAt wins
    epic = by[700]
    assert epic["sub_total"] == 61 and epic["subs_complete"] is True and len(epic["subs"]) == 61
    assert epic["subs"][50]["number"] == 51 and epic["subs"][50]["labels"] == ["acceptance"]
    assert {(c["repository"], c["number"]) for c in epic["subs"]} >= {("x/y", 5), ("o/2048", 142)}
    got = calls()
    lists = [(c["kind"], c.get("after")) for c in got if c["kind"] in ("closed", "open", "late")]
    # the closed issues first, then the open ones; the first page sends no cursor
    assert lists == [("closed", None), ("closed", "c1"), ("open", None), ("open", "o1"), ("late", None)]
    closed, opened = got[0]["query"], got[2]["query"]
    assert "states:CLOSED" in closed and "filterBy:{since:$since}" in closed and "direction:ASC" in closed
    assert "states:OPEN" in opened and "filterBy" not in opened and "direction:DESC" in opened
    assert "field:CREATED_AT" in closed and "field:CREATED_AT" in opened  # a change moves no cursor
    assert "subIssues(first:100)" in closed and "stateReason" in closed
    assert all("rateLimit{remaining}" in c["query"] for c in got)
    assert "-f owner=o -f name=2048" in " ".join(got[0]["args"])  # -f: a numeric repo name stays a string
    assert [c["number"] for c in got if c["kind"] == "subs"] == ["700"]
    batches = [c["query"].count("repository(") for c in got if c["kind"] == "batch"]
    assert batches == [50, 10]  # #142 came with the list: not asked again
    # outcomes on top: the acceptance issue at position 51 decides usable
    (out / "docs/process/optimization.local.json").write_text(
        json.dumps({"outcomes": {"usable": "label:acceptance"}}), encoding="utf-8")
    t = m.outcomes_table(out, days=30, now=datetime(2026, 12, 31, tzinfo=timezone.utc))
    ep = {e["number"]: e for e in t["epics"]}
    assert ep[700]["quality"] == "proxy" and ep[700]["usable_at"] == datetime(2025, 6, 1, tzinfo=timezone.utc)
    assert t["complete"] is True and t["cut"] is None
    assert t["sample"] == "all open issues and those changed in the window"


def test_gh_issues_keeps_a_partial_batch_answer_and_the_epic_is_missing(render, tmp_path, monkeypatch):
    """`gh` exits 1 on a GraphQL error and still prints `data`: the entries there are resolved,
    only the missing one is not (moved or deleted) — and its epic is `missing`, never usable."""
    from datetime import datetime, timezone
    out = _flow_repo(render, tmp_path)
    m = _flow_module(out)
    _fake_gh(tmp_path, monkeypatch, _gh_scenario(missing=["o/2048#59"]))
    issues, why, cut = m._gh_issues(out, _gh_since(), resolve_subs=True)
    epic = next(i for i in issues if i["number"] == 700)
    assert why is None and cut is None
    assert 51 in [c["number"] for c in epic["subs"]] and 59 not in [c["number"] for c in epic["subs"]]
    assert epic["subs_complete"] is False
    (out / "docs/process/optimization.local.json").write_text(
        json.dumps({"outcomes": {"usable": "label:acceptance"}}), encoding="utf-8")
    t = m.outcomes_table(out, days=30, now=datetime(2026, 12, 31, tzinfo=timezone.utc))
    ep = {e["number"]: e for e in t["epics"]}
    assert ep[700]["quality"] == "missing" and ep[700]["usable_at"] is None and ep[700]["subs_complete"] is False
    assert t["epics_unread"] == 1 and t["o1_epic_usable"]["n"] == 0


def test_gh_issues_stops_at_the_rate_floor_or_the_page_limit(render, tmp_path, monkeypatch):
    """Every query asks `rateLimit{remaining}`; under RATE_FLOOR or at MAX_PAGES (pages, follow-ups
    and batches together) the run stops. A stop in the list is a `cut`; a stop while resolving
    leaves the list whole and the epic's sub-issues unread."""
    out = _flow_repo(render, tmp_path)
    m = _flow_module(out)
    assert (m.RATE_FLOOR, m.MAX_PAGES) == (500, 40)
    _fake_gh(tmp_path, monkeypatch, {**_gh_scenario(), "remaining": 400})
    issues, why, cut = m._gh_issues(out, _gh_since(), resolve_subs=True)
    assert why is None and [i["number"] for i in issues] == [140]
    assert cut["pages"] == 1 and "rate limit" in cut["reason"]
    _fake_gh(tmp_path, monkeypatch, _gh_scenario())
    monkeypatch.setattr(m, "MAX_PAGES", 3)
    issues, _why, cut = m._gh_issues(out, _gh_since(), resolve_subs=True)
    assert {i["number"] for i in issues} == {140, 142, 143} and cut["pages"] == 3 and "page limit" in cut["reason"]
    monkeypatch.setattr(m, "MAX_PAGES", 7)  # five list pages, the epic's second sub-issue page, one batch
    issues, _why, cut = m._gh_issues(out, _gh_since(), resolve_subs=True)
    epic = next(i for i in issues if i["number"] == 700)
    assert cut is None and epic["subs_complete"] is False and len(epic["subs"]) == 51
    # no sub-issues asked: nothing resolved, no follow-up, no batch
    calls = _fake_gh(tmp_path, monkeypatch, _gh_scenario())
    issues, _why, cut = m._gh_issues(out, _gh_since(), resolve_subs=False)
    epic = next(i for i in issues if i["number"] == 700)
    assert cut is None and epic["subs"] == [] and epic["subs_complete"] is False and epic["sub_total"] == 61
    assert {c["kind"] for c in calls()} == {"closed", "open", "late"}


def test_gh_issues_a_page_without_paging_facts_is_a_cut_not_the_end(render, tmp_path, monkeypatch):
    """A partial answer (exit 1 with `data`) can carry the list's nodes but no `pageInfo`: the list
    may go on, so it is a cut — never `complete` — named after that list."""
    out = _flow_repo(render, tmp_path)
    m = _flow_module(out)
    _fake_gh(tmp_path, monkeypatch, _gh_scenario())
    real = m._gh_graphql

    def no_page_info(gh, root, query, args):
        data, why = real(gh, root, query, args)
        issues = ((data or {}).get("repository") or {}).get("issues")
        if isinstance(issues, dict):
            issues.pop("pageInfo", None)
        return data, why

    monkeypatch.setattr(m, "_gh_graphql", no_page_info)
    issues, why, cut = m._gh_issues(out, _gh_since(), resolve_subs=False)
    assert why is None and cut is not None and cut["list"] == "closed" and "pageInfo" in cut["reason"]
    assert m._cut_text(cut).startswith("cut after 1 page(s) of the closed list")
    assert m._cut_text({"pages": 40, "reason": "page limit (40)", "list": "before late"}) \
        == "cut after 40 page(s), late list not read (page limit (40))"


def test_outcomes_a_sub_issue_of_another_repository_is_not_delivered_by_a_local_number(render, tmp_path):
    """#12 is delivered in this repository's flow; `other/repo#12`, still open, is not."""
    import json
    from datetime import datetime, timezone
    out = _flow_repo(render, tmp_path)
    m = _flow_module(out)
    foreign = {**_issue(12, "Acceptance run", labels=["acceptance"]), "repository": "other/repo"}
    epic = {**_issue(103, "[EPIC] Shared", subs=[foreign]), "repository": "own/repo"}
    (out / "docs/process/optimization.local.json").write_text(
        json.dumps({"outcomes": {"usable": "label:acceptance"}}), encoding="utf-8")
    t = m.outcomes_table(out, days=3650, now=datetime(2026, 12, 31, tzinfo=timezone.utc), fetch=_fetch([epic]))
    ep = {e["number"]: e for e in t["epics"]}
    assert ep[103]["usable_at"] is None and ep[103]["quality"] == "open"


def test_outcomes_asks_for_sub_issues_only_for_a_label_or_title_marker(render, tmp_path):
    from datetime import datetime, timedelta, timezone
    out = _flow_repo(render, tmp_path)
    m = _flow_module(out)
    now = datetime(2026, 12, 31, tzinfo=timezone.utc)
    seen: list = []
    m.outcomes_table(out, days=30, now=now, fetch=_fetch([], seen=seen))
    assert seen == [(now - timedelta(days=30), False)]  # epic-closed reads no sub-issue
    for marker in ("label:acceptance", "title:Abnahme"):
        (out / "docs/process/optimization.local.json").write_text(
            json.dumps({"outcomes": {"usable": marker}}), encoding="utf-8")
        m.outcomes_table(out, days=30, now=now, fetch=_fetch([], seen=seen))
        assert seen[-1] == (now - timedelta(days=30), True)


def test_outcomes_cut_list_is_incomplete_and_an_unread_epic_is_missing(render, tmp_path, capsys):
    """Two separate consequences (#417 r1 M3): a cut list makes the report incomplete and leaves
    every quality as it is; an epic whose sub-issues were not all read is `missing`, counted,
    never in `reached`."""
    from datetime import datetime, timezone
    out = _flow_repo(render, tmp_path)
    m = _flow_module(out)
    (out / "docs/process/optimization.local.json").write_text(
        json.dumps({"outcomes": {"usable": "label:acceptance"}}), encoding="utf-8")
    accept = _issue(12, "Acceptance run", "CLOSED", ["acceptance"], closed="2026-11-30T00:00:00Z")
    whole = _issue(100, "[EPIC] whole", subs=[accept])
    unread = _issue(101, "[EPIC] unread", subs=[accept], subs_complete=False)
    cut = {"pages": 40, "reason": "page limit (40)", "list": "open"}
    now = datetime(2026, 12, 31, tzinfo=timezone.utc)
    t = m.outcomes_table(out, days=3650, now=now, fetch=_fetch([whole, unread], cut=cut))
    ep = {e["number"]: e for e in t["epics"]}
    assert ep[100]["quality"] == "measured"  # the cut changes no quality
    assert ep[101]["quality"] == "missing" and ep[101]["usable_at"] is None
    assert t["o1_epic_usable"]["n"] == 1 and t["epics_unread"] == 1
    assert t["complete"] is False and t["cut"] == cut
    assert t["sample"] == "cut after 40 page(s) of the open list (page limit (40))"
    whole_t = m.outcomes_table(out, days=3650, now=now, fetch=_fetch([whole]))
    assert whole_t["complete"] is True and whole_t["cut"] is None and whole_t["epics_unread"] == 0
    m._gh_issues = _fetch([whole, unread], cut=cut)
    assert m.outcomes(out) == 0
    text = capsys.readouterr().out
    assert "list cut after 40 page(s) of the open list (page limit (40)) — epics not read do not appear" in text
    assert "1 epic(s) with sub-issues not all read: missing, never usable" in text


def test_outcomes_cli_text_names_the_blind_spot_or_says_unavailable(render, tmp_path, capsys):
    out = _flow_repo(render, tmp_path)
    m = _flow_module(out)
    m._gh_issues = lambda _r, _s, **_k: (None, "gh is not installed", None)
    assert m.outcomes(out) == 0
    assert "unavailable: gh is not installed — outcomes skipped (not zero)" in capsys.readouterr().out
    m._gh_issues = _fetch([_issue(202, "no origin", labels=["bug"], created="2099-01-01T00:00:00Z")])
    assert m.outcomes(out) == 0
    text = capsys.readouterr().out
    assert "1 bug(s), cause and channel on 0% (target 80%) — blind spot" in text


def _reports(out: Path, *rows) -> None:
    """Report lines (worker, issue, state, aware datetime) into this host's ledger."""
    d = out / ".git/process-tower"
    d.mkdir(parents=True, exist_ok=True)
    with (d / "reports.jsonl").open("a", encoding="utf-8") as fh:
        for worker, issue, state, when in rows:
            fh.write(json.dumps({"ts": when.isoformat(), "epoch": int(when.timestamp()), "host": "h",
                                 "worker": worker, "branch": worker, "issue": issue, "state": state,
                                 "note": "", "cwd": ""}) + "\n")


def _no_claims(_root, numbers, _label):
    return {}, None


def test_intake_without_gh_is_missing_and_keeps_the_tower_part(render, tmp_path):
    """#412: without `gh` the intake and the label part are `missing`, never zeros; the tower
    part is read and says it could not drop closed issues."""
    out = _merges_repo(render, tmp_path)
    m = _flow_module(out)
    _reports(out, ("w1", 12, "planned", _dt(20)))
    t = m.intake_table(out, weeks=2, now=_dt(31), fetch=lambda _r, _s, **_k: (None, "gh is not installed", None))
    assert len(t["intake"]) == 2
    for row in t["intake"]:
        for key in ("opened", "closed", "closed_not_planned", "open"):
            assert row[key] == {"value": None, "quality": "missing"}
    assert t["issues"] == {"read": False, "why": "gh is not installed", "complete": None, "cut": None}
    assert t["counts"]["label"] == {"value": None, "quality": "missing"}
    assert t["counts"]["tower"] == {"value": 1, "quality": "estimated"}
    [w] = t["in_progress"]
    assert w["issue"] == 12 and w["source"] == "tower" and w["open"] is None
    assert w["claimed"] == {"value": _dt(20), "quality": "estimated"} and w["claim_from"] == "tower"
    assert "a closed issue may count" in t["tower"]["note"]


def test_intake_counts_opened_closed_and_the_open_stock_week_by_week(render, tmp_path):
    out = _merges_repo(render, tmp_path)
    m = _flow_module(out)
    dup = _issue(3, "c", "CLOSED", created=_at(23), closed=_at(24))
    dup["stateReason"] = "DUPLICATE"
    issues = [_issue(1, "a", created=_at(16)), _issue(2, "b", "CLOSED", created=_at(17), closed=_at(23)),
              dup, _issue(4, "old")]
    seen: list = []
    t = m.intake_table(out, weeks=2, now=_dt(29), fetch=_fetch(issues, seen=seen), label_claims=_no_claims)
    from datetime import timedelta
    assert seen == [(_dt(29) - timedelta(days=14), False)]  # the window's start, no sub-issues
    w0, w1 = t["intake"]
    value = lambda row: tuple(row[k]["value"] for k in ("opened", "closed", "closed_not_planned", "open"))  # noqa: E731
    assert value(w1) == (2, 0, 0, 3)  # #1, #2 opened; at its end #1, #2 and #4 open
    assert value(w0) == (1, 2, 1, 2)  # #3 opened; #2 done and #3 a duplicate, counted apart
    assert w0["opened"]["quality"] == "measured" and t["issues"]["complete"] is True
    cut = {"pages": 40, "reason": "page limit (40)", "list": "open"}
    t = m.intake_table(out, weeks=2, now=_dt(29), fetch=_fetch(issues, cut=cut), label_claims=_no_claims)
    assert t["issues"]["complete"] is False and t["issues"]["cut"] == cut
    assert t["intake"][0]["opened"]["quality"] == "measured"


def test_intake_reads_in_progress_from_the_label_and_the_last_report_per_worker(render, tmp_path):
    """In progress: open issues with the label (`measured`) and the issue of each worker's last
    report that is not done or idle (`estimated`). A worker that moved on without `done` holds
    the old issue no longer; a closed issue does not count; the claim is the earlier of the
    label's last setting and the first report of the worker's current streak."""
    out = _merges_repo(render, tmp_path)
    m = _flow_module(out)
    _reports(out,
             ("w1", 5, "planned", _dt(10)), ("w1", 6, "planned", _dt(20)),  # moved on: #5 not held
             ("w2", 7, "pushed", _dt(21)),  # #7 is closed
             ("w3", 8, "done", _dt(22)),
             ("w4", 9, "planned", _dt(5)), ("w4", 11, "planned", _dt(8)),
             ("w4", 9, "blocked", _dt(15)), ("w4", 9, "planned", _dt(25)))  # the streak starts on the 15th
    issues = [_issue(5, "five"), _issue(6, "six", labels=["status:in-progress"]),
              _issue(7, "seven", "CLOSED", closed=_at(23)), _issue(8, "eight"), _issue(9, "nine"),
              _issue(10, "ten", labels=["status:in-progress"], created=_at(2)), _issue(11, "eleven")]
    asked: list = []

    def claims(_root, numbers, label):
        asked.append((sorted(numbers), label))
        return {6: _dt(28), 10: _dt(12)}, None
    t = m.intake_table(out, weeks=4, now=_dt(31), fetch=_fetch(issues), label_claims=claims)
    assert asked == [([6, 10], "status:in-progress")]
    got = {w["issue"]: w for w in t["in_progress"]}
    assert set(got) == {6, 9, 10}
    assert got[6]["source"] == "both" and got[6]["claimed"] == {"value": _dt(20), "quality": "estimated"}
    assert got[9]["source"] == "tower" and got[9]["claimed"]["value"] == _dt(15)
    assert got[9]["tower"]["state"] == "planned" and got[9]["tower"]["worker"] == "w4"
    assert got[10]["source"] == "label" and got[10]["claim_from"] == "label"
    assert got[10]["claimed"] == {"value": _dt(12), "quality": "measured"}
    assert got[10]["days"] == {"value": 19.0, "quality": "measured"}
    assert t["counts"]["label"] == {"value": 2, "quality": "measured"}
    assert t["counts"]["tower"] == {"value": 2, "quality": "estimated"}
    assert t["counts"]["total"] == {"value": 3, "quality": "estimated"}
    # another label is an argument, not a mandate key
    t = m.intake_table(out, weeks=4, now=_dt(31), fetch=_fetch(issues), label="doing", label_claims=claims)
    assert len(asked) == 1  # no issue carries it: no timeline asked
    assert {w["issue"] for w in t["in_progress"]} == {6, 9} and t["label"] == "doing"


def test_intake_takes_its_tower_part_from_the_one_in_progress_rule(render, tmp_path):
    """v2.97 B2: the tower part is `tower.in_progress` — `failed` holds nothing, `review-pass`
    holds, a dispatch record without a report holds, an issue silent for 14 days is dormant; the
    closed-issue filter and the `estimated` quality stay intake's."""
    out = _merges_repo(render, tmp_path)
    m = _flow_module(out)
    _reports(out, ("w1", 12, "failed", _dt(28)), ("w2", 13, "planned", _dt(10)),
             ("w3", 14, "review-pass", _dt(28)), ("w4", 16, "planned", _dt(28)))
    rec_dir = out / ".git/process-dispatch"
    rec_dir.mkdir(parents=True, exist_ok=True)
    (rec_dir / "15-x.json").write_text(json.dumps({"branch": "15-x", "issue": 15, "phase": "plan",
                                                   "started": int(_dt(29).timestamp())}))
    issues = [_issue(n, f"issue {n}") for n in (12, 13, 14, 15)] + [_issue(16, "x", "CLOSED", closed=_at(29))]
    t = m.intake_table(out, weeks=4, now=_dt(31), fetch=_fetch(issues), label_claims=_no_claims)
    got = {w["issue"]: w for w in t["in_progress"]}
    assert set(got) == {14, 15}
    assert got[15]["tower"]["worker"] == "15-x" and got[15]["claimed"] == {"value": _dt(29), "quality": "estimated"}
    assert t["counts"]["tower"] == {"value": 2, "quality": "estimated"}


def test_intake_label_claim_is_the_last_setting_after_the_last_removal(render, tmp_path, monkeypatch):
    from datetime import datetime, timezone
    out = _merges_repo(render, tmp_path)
    m = _flow_module(out)

    def ev(kind, label, day):
        return {"__typename": kind, "createdAt": f"2026-03-{day:02d}T09:00:00Z", "label": {"name": label}}
    calls = _fake_gh(tmp_path, monkeypatch, {"since": "", "pages": {}, "issues": {}, "timeline": {
        "10": [ev("LabeledEvent", "status:in-progress", 1), ev("UnlabeledEvent", "status:in-progress", 2),
               ev("LabeledEvent", "status:in-progress", 3), ev("LabeledEvent", "other", 4)],
        "11": [ev("LabeledEvent", "status:in-progress", 1), ev("UnlabeledEvent", "status:in-progress", 2)]}})
    got, why = m._gh_label_claims(out, [10, 11], "status:in-progress")
    assert why is None and got == {10: datetime(2026, 3, 3, 9, tzinfo=timezone.utc)}
    [call] = calls()
    assert "timelineItems(last:50,itemTypes:[LABELED_EVENT,UNLABELED_EVENT])" in call["query"]
    assert "rateLimit{remaining}" in call["query"]


def test_intake_counts_branch_and_landed_commits_apart(render, tmp_path):
    """#413: two numbers per issue in progress, never added into one: commits on its branches
    (`tower.issue_branch_commits`) and commits of its merge events (`merge_events` with
    `_own_issues`) — a `Refs #N` lands nothing for N, a finish range without an earlier bound is
    `missing`, a squash is no event and its branch keeps counting."""
    out = _merges_repo(render, tmp_path)
    m = _flow_module(out)
    _finish_merge(out, "40-first", [
        ("docs: plan first", {".process-work/plans/2026-03-02-first.md": _plan_text(40)}, _at(2)),
        ("feat: first (#40)", {"src/first.py": _lines(3)}, _at(2, 10))], ["2026-03-02-first.md"], _at(3))
    _train_merge(out, "20-feat", [("feat: one", {"src/one.py": _lines(2)}, _at(4)),
                                  ("feat: two", {"src/two.py": _lines(2)}, _at(4, 10))],
                 "train: merge 20-feat\n\nCloses #20\nRefs #21\nRefs #22", _at(5))
    _g(out, "checkout", "-q", "-b", "30-rebuilt", "main")
    _put(out, "feat: thirty a", {"src/thirty.py": "a\n"}, _at(6))
    _g(out, "checkout", "-q", "main")
    _put(out, "chore: main moves", {"src/main.py": "m\n"}, _at(7))
    _g(out, "checkout", "-q", "30-rebuilt")
    _g(out, "merge", "-q", "--no-ff", "-m", "Merge main", "main", when=_at(8))
    _put(out, "feat: thirty b", {"src/thirty.py": "b\n"}, _at(9))
    _g(out, "checkout", "-q", "-b", "31-squash", "main")
    _put(out, "feat: squash a", {"src/sq.py": "a\n"}, _at(10))
    _put(out, "feat: squash b", {"src/sq.py": "b\n"}, _at(11))
    _g(out, "checkout", "-q", "main")
    _g(out, "merge", "-q", "--squash", "31-squash")
    _put(out, "feat: squash (#31)", {}, _at(12))
    numbers = (20, 21, 22, 30, 31, 40)
    # the claim is the first report of the streak; the later one keeps the issue from going dormant
    _reports(out, *[(f"w{n}", n, "planned", _dt(1, 12)) for n in numbers],
             *[(f"w{n}", n, "planned", _dt(20)) for n in numbers])
    t = m.intake_table(out, weeks=4, now=_dt(31), fetch=_fetch([_issue(n, f"issue {n}") for n in numbers]),
                       label_claims=_no_claims)
    got = {w["issue"]: w for w in t["in_progress"]}

    def counts(n):
        return got[n]["branch_commits"]["value"], got[n]["landed_commits"]["value"]
    assert counts(20) == (0, 2)  # landed by the train; the branch holds nothing beyond main
    assert counts(21) == counts(22) == (0, 0)  # a Refs is no work of the issue
    assert counts(30) == (2, 0)  # neither main's commit nor the merge of main
    assert counts(31) == (2, 0)  # the squash is no event
    assert got[40]["landed_commits"]["value"] is None and got[40]["landed_commits"]["quality"] == "missing"
    assert got[20]["commits"] == {"value": 2, "quality": "estimated"}
    assert got[20]["branch_commits"]["quality"] == got[20]["landed_commits"]["quality"] == "estimated"
    assert got[40]["commits"]["quality"] == "missing"
    assert [w["issue"] for w in t["in_progress"]][:3] == [20, 30, 31]  # by the sum


def test_intake_cli_prints_rows_and_json_carries_quality_per_field(render, tmp_path, monkeypatch, capsys):
    import os
    import time
    from datetime import datetime, timezone
    out = _merges_repo(render, tmp_path)
    m = _flow_module(out)
    _reports(out, ("w1", 12, "planned", datetime.fromtimestamp(time.time() - 86400, tz=timezone.utc)))
    monkeypatch.setattr(m, "_gh_issues", _fetch([_issue(12, "twelve")]))
    monkeypatch.setattr(m, "_gh_label_claims", _no_claims)
    assert m.intake(out, weeks=2, as_json=True) == 0
    t = json.loads(capsys.readouterr().out)
    [w] = t["in_progress"]
    for key in ("claimed", "days", "branch_commits", "landed_commits", "commits"):
        assert {"value", "quality"} <= set(w[key]), key
    for row in t["intake"]:
        for key in ("opened", "closed", "closed_not_planned", "open"):
            assert set(row[key]) == {"value", "quality"}
    assert m.intake(out, weeks=2) == 0
    text = capsys.readouterr().out
    assert text.startswith("[intake]") and "#12" in text and "confidence:" in text
    assert "other hosts not read" in text  # no origin: the fetch of the published reports failed
    # registered on the command line; a gh that cannot name the repository leaves the tower part
    fake = tmp_path / "nogh"
    fake.mkdir()
    (fake / "gh").write_text(f"#!{sys.executable}\nimport sys\nsys.exit(1)\n")
    (fake / "gh").chmod(0o755)
    r = subprocess.run([sys.executable, str(out / "scripts/process/process_kpis.py"), "intake", "--weeks", "3",
                        "--label", "doing", "--json"], cwd=out, capture_output=True, text=True,
                       env={**os.environ, "PATH": f"{fake}{os.pathsep}{os.environ['PATH']}"})
    assert r.returncode == 0, r.stderr
    t = json.loads(r.stdout)
    assert t["label"] == "doing" and len(t["intake"]) == 3 and t["issues"]["read"] is False
    assert [w["issue"] for w in t["in_progress"]] == [12]


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


def _train_row(out: Path, branch: str, ended: str, deployed: bool = True) -> None:
    train = out / ".git/process-train"
    train.mkdir(exist_ok=True)
    with (train / "phases.jsonl").open("a") as fh:
        fh.write(json.dumps({"stamp": branch, "result": "green", "aboard": 1, "branches": [branch],
                             "deployed": deployed, "ended": ended}) + "\n")


def test_a_first_phase_merged_by_finish_opens_the_escape_window_at_its_merge(render, tmp_path):
    """#342 AC-1/AC-3: the first phase merged with `finish` (no train row), a later phase by
    the train. The host opened the window at the later phase's deploy and missed a fix in
    between; a clone, without train rows, opened it at the first merge. Both open it at the
    first merge now and count the same escape."""
    from datetime import datetime, timezone
    out = _merges_repo(render, tmp_path)
    _finish_merge(out, "9-one", [("feat: one (#9)", {"src/a.py": _lines(10),
                                                    ".process-work/plans/2026-03-02-one.md": _plan_text(9)},
                                  _at(2))], ["2026-03-02-one.md"], _at(3, 12))
    _train_merge(out, "9-two", [("fix: guard the edge (#9)\n\nRegression-of: #9", {"src/b.py": _lines(4)}, _at(5))],
                 "train: merge 9-two\n\nCloses #9", _at(6, 12))
    clone = _clone(out, tmp_path)
    (out / ".git/process-tower").mkdir()
    _report(out, "2026-03-03T12:05:00", "done", "9-one", 9)
    _report(out, "2026-03-06T12:05:00", "done", "9-two", 9)
    _train_row(out, "9-two", _at(6, 13))
    now = datetime(2026, 10, 1, tzinfo=timezone.utc)
    got = {}
    for root in (clone, out):
        it = _by_issue(_flow_module(root), root, now=now)[9]
        got[root] = it["escapes"]["value"]
        assert it["escapes"]["value"] == 1 and it["escapes"]["from"] == "merge", (root, it["escapes"])
    assert got[clone] == got[out]


def test_a_first_phase_with_its_own_deployed_train_row_opens_the_window_at_that_deploy(render, tmp_path):
    """#342 AC-2: where the first merge's own train row deployed, the window opens there, as
    before — a fix between that merge and its deploy is no escape, one after it is."""
    from datetime import datetime, timezone
    out = _merges_repo(render, tmp_path)
    _train_merge(out, "9-one", [("feat: one (#9)", {"src/a.py": _lines(10)}, _at(2))],
                 "train: merge 9-one\n\nRefs #9", _at(3, 12))
    _train_merge(out, "9-two", [("fix: early (#9)\n\nRegression-of: #9", {"src/b.py": _lines(4)}, _at(3, 18)),
                                ("fix: late (#9)\n\nRegression-of: #9", {"src/c.py": _lines(4)}, _at(5))],
                 "train: merge 9-two\n\nCloses #9", _at(6, 12))
    (out / ".git/process-tower").mkdir()
    _report(out, "2026-03-03T12:05:00", "done", "9-one", 9)
    _report(out, "2026-03-06T12:05:00", "done", "9-two", 9)
    _train_row(out, "9-one", _at(4))
    _train_row(out, "9-two", _at(6, 13))
    it = _by_issue(_flow_module(out), out, now=datetime(2026, 10, 1, tzinfo=timezone.utc))[9]
    assert it["escapes"]["value"] == 1 and it["escapes"]["from"] == "deploy", it["escapes"]


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


def test_plans_git_could_not_read_are_named_apart_from_merges_without_an_issue(render, tmp_path, monkeypatch):
    """Cross-model review: a train merge's branch-side plans (a shallow clone, a timeout) or a
    finish merge's archived plan that git cannot read made the merge one "without an issue" —
    the work fell out of the population under the wrong name. They count as not read."""
    out = _merges_repo(render, tmp_path)
    plan = {".process-work/plans/2026-03-02-long.md": _plan_text(15, extra="plan-stays-active: two phases\n")}
    _train_merge(out, "15-long", [("docs: plan long", plan, _at(2)),
                                  ("feat: long part one", {"src/l.py": _lines(6)}, _at(3))],
                 "train: merge 15-long", _at(4, 12))
    _finish_merge(out, "17-f", [("feat: f (#17)", {"src/f.py": _lines(2),
                                                 ".process-work/plans/2026-03-05-f.md": _plan_text(17)}, _at(5))],
                  ["2026-03-05-f.md"], _at(5, 12))
    m = _flow_module(out)
    import check_review
    monkeypatch.setattr(check_review, "own_plans", lambda *a, **k: None)
    real = m._git_out
    monkeypatch.setattr(m, "_git_out", lambda root, *args, **kw: None
                        if args[:1] == ("show",) and "/archive/" in args[1] else real(root, *args, **kw))
    p = m.size_table(out, *m._window(":"))["population"]
    assert (p["plans_unread"], p["unclaimed"]) == (2, 0), p
    assert "plans git could not read 2" in m._population_text(p)


def test_a_range_git_could_not_read_is_counted_unknown_not_zero(render, tmp_path, monkeypatch):
    out = _merges_repo(render, tmp_path)
    _train_merge(out, "18-a", [("feat: a (#18)", {"src/a.py": _lines(2)}, _at(2))],
                 "train: merge 18-a\n\nCloses #18", _at(2, 12))
    m = _flow_module(out)
    monkeypatch.setattr(m, "_rev_list", lambda *a, **k: None)
    p = m.size_table(out, *m._window(":"))["population"]
    assert p["unbounded"] == 1, p
    assert "ranges unknown 1" in m._population_text(p)


def test_the_escape_log_reads_the_whole_history_with_the_history_timeout(render, tmp_path, monkeypatch):
    """The whole-history read timed out at 30 s on a consumer clone (fixed for `_commit_table`
    in this release); the `Regression-of:` log reads the same history."""
    out = _merges_repo(render, tmp_path)
    m = _flow_module(out)
    seen = []
    real = m._git_out
    monkeypatch.setattr(m, "_git_out", lambda root, *a, **kw: seen.append(kw.get("timeout")) or real(root, *a, **kw))
    assert m._regressions(out, "main") is not None
    assert seen == [m._HISTORY_TIMEOUT]


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
    from datetime import datetime
    d = out / ".git/process-tower"
    d.mkdir(exist_ok=True)
    with (d / "reports.jsonl").open("a") as fh:
        fh.write(json.dumps({"ts": datetime.fromisoformat(ts).astimezone().isoformat(), "host": "h", "worker": worker, "branch": worker,
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


def _merged_main_repo(render, tmp_path) -> Path:
    """Kenni's shape (#360 M1): branch X forks after train merge 41; train merge 42 lands on
    main; X merges main in (no marker) and main is fast-forwarded onto X; train merge 43
    follows. Main's first-parent chain then runs through X, and 42 lies on the second side
    of X's merge of main."""
    out = _merges_repo(render, tmp_path)
    _train_merge(out, "41-a", [("feat: a (#41)", {"src/a.py": _lines(4)}, _at(2))],
                 "train: merge 41-a\n\nCloses #41", _at(2, 12))
    _g(out, "checkout", "-q", "-b", "x-carrier", "main")
    _put(out, "chore: carrier work", {"src/x.py": _lines(2)}, _at(3))
    _g(out, "checkout", "-q", "main")
    _train_merge(out, "42-b", [("feat: b (#42)", {"src/b.py": _lines(7)}, _at(3, 10))],
                 "train: merge 42-b\n\nCloses #42", _at(3, 12))
    _g(out, "checkout", "-q", "x-carrier")
    _g(out, "merge", "-q", "--no-ff", "-m", "chore: integrate main into the carrier", "main", when=_at(4))
    _g(out, "checkout", "-q", "main")
    _g(out, "merge", "-q", "--ff-only", "x-carrier")
    _train_merge(out, "43-c", [("feat: c (#43)", {"src/c.py": _lines(3)}, _at(5))],
                 "train: merge 43-c\n\nCloses #43", _at(5, 12))
    return out


def test_merge_events_reach_train_merges_behind_a_merge_of_main_into_a_branch(render, tmp_path):
    """#360 M1: downstream only 59 of 168 train merges lay on main's first-parent chain — two
    merges of main into a branch, with main fast-forwarded onto it, hid the rest, and every
    report counted a fraction of the work without saying so."""
    out = _merged_main_repo(render, tmp_path)
    m = _flow_module(out)
    got = m.merge_events(out)
    by = {i: e for e in got["events"] for i in e["issues"]}
    assert set(by) == {41, 42, 43}, sorted(by)
    assert by[42]["via"] and by[41]["via"] is None and by[43]["via"] is None
    # 43's strays and lines hold nothing of 42 (no second count of the side event's commits)
    assert by[43]["product_lines"] == 3 and by[43]["strays"] == 2  # the carrier commit and its merge of main
    assert by[43]["stray_product_lines"] == 2, by[43]
    assert [e["issues"] for e in got["events"]] == [[41], [42], [43]]  # topological, not by clock
    text = _cli(out, "baseline")
    assert "reached through a merge without marker 1" in text, text


def test_a_merge_of_main_into_a_branch_that_was_never_fast_forwarded_changes_nothing(render, tmp_path):
    out = _merges_repo(render, tmp_path)
    _train_merge(out, "41-a", [("feat: a (#41)", {"src/a.py": _lines(4)}, _at(2))],
                 "train: merge 41-a\n\nCloses #41", _at(2, 12))
    _g(out, "checkout", "-q", "-b", "x-side", "main")
    _g(out, "merge", "-q", "--no-ff", "-m", "chore: integrate main", "main", when=_at(3))
    _g(out, "checkout", "-q", "main")
    _train_merge(out, "43-c", [("feat: c (#43)", {"src/c.py": _lines(3)}, _at(5))],
                 "train: merge 43-c\n\nCloses #43", _at(5, 12))
    events = _flow_module(out).merge_events(out)["events"]
    assert [e["issues"] for e in events] == [[41], [43]] and not any(e["via"] for e in events)


def test_an_empty_value_names_why_it_is_empty(render, tmp_path):
    """#360 K4: empty token and escape columns gave no reason; an analysis read a project's
    missing configuration (no `transcripts` glob, no `Regression-of:` trailers) as a gap in the
    template. The reason now stands next to the dash, and a zero escape count without any
    trailer is named unmeasured, not zero."""
    out = _merges_repo(render, tmp_path)
    _train_merge(out, "41-a", [("feat: a (#41)", {"src/a.py": _lines(4)}, _at(2))],
                 "train: merge 41-a\n\nCloses #41", _at(2, 12))
    text = _cli(out, "baseline")
    assert "tokens — not-configured" in text, text
    assert "escapes — no Regression-of trailer since the window's start — unmeasured, not zero" in text, text
    losses = _cli(out, "losses", "--days", "3650")
    assert "not-configured" in losses or "no dispatched issue" in losses, losses


def test_baseline_names_the_outliers_share_and_the_revert_rate(render, tmp_path):
    """#360 B2/B3: medians hid that 7 % of the works carried 28 % of the code-review rounds
    downstream; and a revert is an escape no trailer has to name."""
    from datetime import datetime, timezone
    out = _merges_repo(render, tmp_path)
    for n, day, rounds in ((50, 2, 1), (51, 3, 1), (52, 4, 4)):
        _train_merge(out, f"{n}-w", [(f"feat: w{n} (#{n})", {f"src/w{n}.py": _lines(10 * (1 + n % 50))}, _at(day))],
                     f"train: merge {n}-w\n\nCloses #{n}", _at(day, 12))
    _journal(out, "".join(_review(n, r, "block") for n, last in ((52, 4),) for r in range(1, 4))
             + "".join(_review(n, last, "pass") for n, last in ((50, 1), (51, 1), (52, 4))))
    _put(out, 'Revert "feat: w51 (#51)"', {"src/w51.py": None}, _at(5))
    m = _flow_module(out)
    b = m.baseline_numbers(out, datetime(2026, 3, 1, tzinfo=timezone.utc), datetime(2026, 3, 9, tzinfo=timezone.utc),
                           commits=m._git_commits("main", root=out))
    o = b["outliers"]
    assert (o["works"], o["of"]) == (1, 3)
    assert o["share_rounds"] == round(4 / 6, 2), o  # 4 of the 1 + 1 + 4 rounds
    assert o["share_lines"] == round(30 / 60, 2), o  # w52: 30 of 10 + 20 + 30 lines
    assert b["reverts"] == {"commits": 1, "per_work": round(1 / 3, 2)}, b["reverts"]
    text = _cli(out, "baseline")
    assert "outliers (>= 4 code-review rounds)" in text and "reverts" in text and "proxy" in text
    assert "1 of 3 works carry 67 % of the rounds" in _cli(out, "works")


def _versions_repo(render, tmp_path, **mods):
    """Three template versions in the history — v2.70.0, v2.80.0 and a bare SHA (no release
    tag: unknown) — and a train merge reviewed at each: works 60, 61, 62."""
    out = _merges_repo(render, tmp_path, **mods)
    heads = {}
    for n, day, ver in ((60, 2, "v2.70.0"), (61, 3, "v2.80.0"), (62, 4, "3f2a9c1")):
        _put(out, f"chore: template {ver}", {".copier-answers.yml": f"_commit: {ver}\n_src_path: x\n"}, _at(day, 8))
        heads[n] = _g(out, "rev-parse", "HEAD")
        _train_merge(out, f"{n}-w", [(f"feat: w{n} (#{n})", {f"src/w{n}.py": _lines(3)}, _at(day, 10))],
                     f"train: merge {n}-w\n\nCloses #{n}", _at(day, 12))

    def rv(work, rnd, verdict, at=None):
        head = heads[at or work]
        return (f"REVIEW work={work} tier=2 reviewer=r model=m independence=bundle,non-implementing "
                f"verdict={verdict} round={rnd} base={head} head={head}\n")
    # 60's first round saw v2.70 (no duty yet), its later rounds the v2.80 head
    _journal(out, rv(60, 1, "block") + rv(60, 2, "block", at=61) + rv(60, 3, "pass", at=61)
             + rv(61, 1, "block") + rv(61, 2, "pass") + rv(62, 1, "block") + rv(62, 2, "pass")
             + "ROOT-CAUSE work=60 round=2: owner read twice — sites: none — a test\n"
             + "REPLAN work=60 round=2: rebuild — the owner moves\n"
             + "REPLAN 2026-10-23 issue-61 work=61 round=2 rebuild of the parser\n")
    return out


def test_rounds_count_compliance_with_owed_duties_and_coverage_apart(render, tmp_path):
    """#360 B1: how often the mandatory lines are written — only where they were owed (from the
    version that introduced them, at the head the review saw; an unknown version is never
    old), with variants named `unparsed`; optional fields are coverage, never a duty."""
    out = _versions_repo(render, tmp_path)
    c = _flow_module(out).compliance_table(out)
    rc = c["root_cause"]  # owed for every blocked code round from v2.77
    assert (rc["written"], rc["owed"], rc["not_owed"], rc["unknown"]) == (1, 2, 1, 1), rc
    rp = c["replan"]  # owed for every blocked round after the first, from v2.77
    assert (rp["written"], rp["owed"], rp["unparsed"]) == (1, 1, 1), rp
    assert c["rounds_after_rebuild"] == {"works": 1, "rounds": 1}
    text = _cli(out, "rounds")
    assert "compliance" in text and "coverage" in text and "ROOT-CAUSE 1/2" in text, text


def test_baseline_splits_works_by_the_version_their_review_saw(render, tmp_path):
    """#360 B4: before/after a mechanism, by the process version at the head of a work's first
    code review — never by merge date; an unparsed version is `unknown`."""
    out = _versions_repo(render, tmp_path)
    text = _cli(out, "baseline", "--split-version", "v2.75.0")
    assert "before v2.75.0: 1 works" in text and "from v2.75.0: 1 works" in text, text
    assert "unknown version: 1 works" in text, text


def test_a_plain_finish_range_keeps_its_net_lines(render, tmp_path):
    """v2.81 code review: summing per commit changed a finish range's lines even without any
    merge of main — a file written in one commit and rewritten in the next counted twice. A
    range with no event reached through a marker-less merge keeps the net diff."""
    out = _merges_repo(render, tmp_path)
    _train_merge(out, "41-a", [("feat: a (#41)", {"src/a.py": _lines(4)}, _at(2))],
                 "train: merge 41-a\n\nCloses #41", _at(2, 12))
    plan = {".process-work/plans/2026-03-03-f.md": _plan_text(44)}
    _finish_merge(out, "44-f", [("feat: f (#44)", {"src/f.py": _lines(5), **plan}, _at(3)),
                                ("fix: f again (#44)", {"src/f.py": _lines(5, "y")}, _at(3, 10))],
                  ["2026-03-03-f.md"], _at(3, 12))
    ev = {i: e for e in _flow_module(out).merge_events(out)["events"] for i in e["issues"]}[44]
    assert ev["product_lines"] == 5, ev  # the net change of src/f.py, not 5 + 10


def test_an_unrelated_root_in_a_stray_range_keeps_the_strays(render, tmp_path):
    """v2.81 code review: a subtree or vendor import brings a second root commit; treating any
    root as "no lower bound" dropped the strays and reported a measured 0."""
    out = _merges_repo(render, tmp_path)
    _train_merge(out, "41-a", [("feat: a (#41)", {"src/a.py": _lines(4)}, _at(2))],
                 "train: merge 41-a\n\nCloses #41", _at(2, 12))
    _g(out, "checkout", "-q", "--orphan", "vendor")
    _g(out, "rm", "-rfq", ".")
    _put(out, "vendor: import", {"vendor/lib.py": _lines(6)}, _at(3))
    _g(out, "checkout", "-q", "main")
    _g(out, "merge", "-q", "--allow-unrelated-histories", "-m", "chore: vendor lib", "vendor", when=_at(3, 10))
    _put(out, "chore: direct", {"src/d.py": _lines(2)}, _at(3, 11))
    _train_merge(out, "43-c", [("feat: c (#43)", {"src/c.py": _lines(3)}, _at(5))],
                 "train: merge 43-c\n\nCloses #43", _at(5, 12))
    ev = {i: e for e in _flow_module(out).merge_events(out)["events"] for i in e["issues"]}[43]
    assert ev["strays"] >= 2 and ev["stray_product_lines"] == 8, ev  # 6 vendored + 2 direct


def test_a_work_ends_at_its_latest_event_across_two_lines(render, tmp_path):
    """v2.81 code review: with phases on two integration lines (main and a carrier that later
    absorbs main), the topological order put the later phase first — the work ended before it
    started. The end is the latest event in time."""
    from datetime import datetime, timezone
    out = _merges_repo(render, tmp_path)
    _g(out, "checkout", "-q", "-b", "x-carrier", "main")
    _put(out, "chore: carrier", {"src/x.py": _lines(1)}, _at(2))
    _g(out, "checkout", "-q", "main")
    _train_merge(out, "70-a", [("feat: a (#70)", {"src/a.py": _lines(2)}, _at(3))],
                 "train: merge 70-a\n\nRefs #70", _at(3, 12))
    _g(out, "checkout", "-q", "x-carrier")
    _g(out, "checkout", "-q", "-b", "70-b", "x-carrier")
    _put(out, "feat: b (#70)", {"src/b.py": _lines(2)}, _at(6))
    _g(out, "checkout", "-q", "x-carrier")
    _g(out, "merge", "-q", "--no-ff", "-m", "train: merge 70-b\n\nCloses #70", "70-b", when=_at(6, 12))
    _g(out, "merge", "-q", "--no-ff", "-m", "chore: integrate main", "main", when=_at(7))
    _g(out, "checkout", "-q", "main")
    _g(out, "merge", "-q", "--ff-only", "x-carrier")
    w = _flow_module(out).merged_works(out)["works"][70]
    assert w["end"] == datetime(2026, 3, 6, 12, tzinfo=timezone.utc) and w["first"] <= w["end"], w


def test_a_version_split_prints_window_wide_numbers_once(render, tmp_path):
    """v2.81 code review: reverts, the change-failure proxy and the population are measures of
    the window, not of a group — printed under every half they read as each half's own."""
    out = _versions_repo(render, tmp_path)
    _put(out, 'Revert "feat: w61 (#61)"', {"src/w61.py": None}, _at(5))
    text = _cli(out, "baseline", "--split-version", "v2.75.0")
    assert text.count("reverts") == 1 and "window-wide, not split" in text, text
    assert "stacks not read" in text or "several stacks" in text, text  # the mix names the stacks


def test_a_version_split_reads_only_the_first_rounds_head(render, tmp_path):
    """v2.81 code review: a first round without a full head took a later round's head — a
    work that started before v2.78 was filed under a later version instead of unknown."""
    out = _versions_repo(render, tmp_path)
    m = _flow_module(out)
    head61 = _g(out, "rev-parse", "HEAD~1")  # any full sha of the v2.80 era
    _journal(out, "REVIEW work=63 tier=2 reviewer=r model=m independence=bundle,non-implementing "
                  "verdict=block round=1\n"
                  f"REVIEW work=63 tier=2 reviewer=r model=m independence=bundle,non-implementing "
                  f"verdict=pass round=2 base={head61} head={head61}\n", name="2026-07-03.md")
    groups = m.split_by_version(out, [{"issue": 63}], (2, 75, 0))
    assert [it["issue"] for it in groups["unknown"]] == [63], groups


def test_coverage_never_counts_a_dash_and_unread_reports_are_not_a_duty_count(render, tmp_path, monkeypatch):
    """v2.81 code review: `at=-` (no place) counted as carrying `at=`; with the reports not
    read, `kind=` on blockers read as a measured 0/0."""
    out = _versions_repo(render, tmp_path, github_issues=True)  # the FINDING reader
    m = _flow_module(out)
    rep = out / ".process-work/reviews/60-r2.md"
    rep.parent.mkdir(parents=True, exist_ok=True)
    rep.write_text("review: x\nwork: #60\nround: 2\npublish-waived: test\n\n## Findings\n"
                   "FINDING sev=major action=fix kind=implementation issue=- by=codex at=- no place\n")
    cov = m.compliance_table(out)["coverage"]
    assert cov["at"]["codex"] == [0, 1], cov
    monkeypatch.setattr(m, "_review_reports", lambda root, phase=None: "reports not read")
    c = m.compliance_table(out)
    assert c["kind_on_blockers"] == "reports not read" and c["coverage"] == "reports not read"


def test_losses_without_any_value_asks_to_measure(render, tmp_path, monkeypatch, capsys):
    """v2.81 code review: "not measured" sat beside the ready action, because no value read
    as an unknown count and the level came out medium."""
    out = _flow_repo(render, tmp_path)
    m = _flow_module(out)
    empty = {"value": None, "issues": 0, "missing": 93, "quality": "missing"}
    t = {"issues": 93, "days": 28, "occupancy": {**empty, "unit": "h"}, "delay": {**empty, "unit": "issue-h"},
         "tokens": dict(empty), "owner_effort": {"decisions": 0, "minutes": None, "quality": "proxy"},
         "proxies": {"regression_fixes": None, "regression_issues_observed": 0}}
    monkeypatch.setattr(m, "losses_table", lambda root, days=28: t)
    monkeypatch.setattr(m, "_reports_by_worker", lambda root: {})
    m.losses(out)
    printed = capsys.readouterr().out
    assert "confidence: not measured" in printed and "let more issues run through dispatch" in printed, printed
    assert "no worker reports (local or published)" in printed, printed  # #360 AC-5


def test_an_escape_after_the_window_is_not_called_unmeasured(render, tmp_path):
    """v2.81 code review: a `Regression-of:` fix after the window's end but inside the follow-up
    horizon is a measured escape; the reason scanned only the window and called it unmeasured."""
    out = _merges_repo(render, tmp_path)
    _train_merge(out, "41-a", [("feat: a (#41)", {"src/a.py": _lines(4)}, _at(2))],
                 "train: merge 41-a\n\nCloses #41", _at(2, 12))
    _put(out, "fix: a\n\nRegression-of: #41", {"src/a.py": _lines(4, "z")}, _at(6))
    text = _cli(out, "baseline", "--window", "2026-03-01:2026-03-05")
    assert "unmeasured, not zero" not in text, text


def test_a_carrier_merging_main_counts_no_line_twice(render, tmp_path):
    """v2.81 code review round 2: on a side line, a merge of main that brings no new event left
    the net diff in place, and the next event took 42's lines a second time as strays."""
    out = _merges_repo(render, tmp_path)
    _g(out, "checkout", "-q", "-b", "x-carrier", "main")
    _g(out, "checkout", "-q", "-b", "70-a", "x-carrier")
    _put(out, "feat: a (#70)", {"src/a.py": _lines(2)}, _at(2))
    _g(out, "checkout", "-q", "x-carrier")
    _g(out, "merge", "-q", "--no-ff", "-m", "train: merge 70-a\n\nCloses #70", "70-a", when=_at(2, 12))
    _g(out, "checkout", "-q", "main")
    _train_merge(out, "42-b", [("feat: b (#42)", {"src/b.py": _lines(7)}, _at(3))],
                 "train: merge 42-b\n\nCloses #42", _at(3, 12))
    _g(out, "checkout", "-q", "x-carrier")
    _g(out, "merge", "-q", "--no-ff", "-m", "chore: integrate main", "main", when=_at(4))
    _g(out, "checkout", "-q", "-b", "71-c", "x-carrier")
    _put(out, "feat: c (#71)", {"src/c.py": _lines(3)}, _at(5))
    _g(out, "checkout", "-q", "x-carrier")
    _g(out, "merge", "-q", "--no-ff", "-m", "train: merge 71-c\n\nCloses #71", "71-c", when=_at(5, 12))
    _g(out, "checkout", "-q", "main")
    _g(out, "merge", "-q", "--no-ff", "-m", "chore: take the carrier", "x-carrier", when=_at(6))
    by = {i: e for e in _flow_module(out).merge_events(out)["events"] for i in e["issues"]}
    assert set(by) == {42, 70, 71}
    assert by[71]["stray_product_lines"] == 0, by[71]  # 42's 7 lines are 42's


def test_split_json_keeps_window_wide_numbers_apart(render, tmp_path):
    """v2.81 code review round 2: the JSON of a split still carried the window's reverts and
    events under every half."""
    import json
    out = _versions_repo(render, tmp_path)
    got = json.loads(_cli(out, "baseline", "--split-version", "v2.75.0", "--json"))
    assert set(got) == {"window", "groups"} and set(got["groups"]) == {"before", "from", "unknown"}
    for g in got["groups"].values():
        assert "reverts" not in g and "change_failure_proxy" not in g and "stated_tokens_by_phase" not in g


def test_reverts_are_read_over_the_whole_window(render, tmp_path):
    """v2.81 code review round 2: reverts came from the last 300 commits `cfr` reads; an older
    revert in the window was a measured 0."""
    from datetime import datetime, timezone
    out = _merges_repo(render, tmp_path)
    _train_merge(out, "41-a", [("feat: a (#41)", {"src/a.py": _lines(4)}, _at(2))],
                 "train: merge 41-a\n\nCloses #41", _at(2, 12))
    _put(out, 'Revert "feat: a (#41)"', {"src/a.py": None}, _at(3))
    m = _flow_module(out)
    b = m.baseline_numbers(out, datetime(2026, 3, 1, tzinfo=timezone.utc),
                           datetime(2026, 3, 9, tzinfo=timezone.utc), commits=[])  # past the cap
    assert b["reverts"]["commits"] == 1, b["reverts"]


def test_kind_compliance_reads_code_reviews_only(render, tmp_path):
    """v2.81 code review round 2: plan-review blockers were judged against a code round's head."""
    out = _versions_repo(render, tmp_path, github_issues=True)
    m = _flow_module(out)
    rep = out / ".process-work/reviews/61-plan.md"
    rep.parent.mkdir(parents=True, exist_ok=True)
    rep.write_text("review: plan\nwork: #61\nphase: plan\nround: 1\npublish-waived: test\n\n## Findings\n"
                   "FINDING sev=blocker action=fix issue=- no kind here\n")
    k = m.compliance_table(out)["kind_on_blockers"]
    assert (k["owed"], k["written"]) == (0, 0), k


def test_a_plain_work_keeps_its_last_event_as_the_end_under_clock_skew(render, tmp_path):
    """v2.81 code review round 2: the end by time changed a plain history with a backdated
    later merge; on one line the order stands, as in v2.80."""
    out = _merges_repo(render, tmp_path)
    _train_merge(out, "80-a", [("feat: a (#80)", {"src/a.py": _lines(2)}, _at(5))],
                 "train: merge 80-a\n\nRefs #80", _at(5, 12))
    _train_merge(out, "80-b", [("feat: b (#80)", {"src/b.py": _lines(2)}, _at(3))],
                 "train: merge 80-b\n\nCloses #80", _at(3, 12))  # committed with an older clock
    w = _flow_module(out).merged_works(out)["works"][80]
    assert w["end"] == w["events"][-1]["when"], w


def test_coverage_counts_plan_review_findings_too(render, tmp_path):
    """v2.81 code review round 3: reading code reviews only for `kind=` compliance also dropped
    plan-review findings from coverage, which the doc promises over all blocker/major findings."""
    out = _versions_repo(render, tmp_path, github_issues=True)
    m = _flow_module(out)
    rep = out / ".process-work/reviews/61-plan.md"
    rep.parent.mkdir(parents=True, exist_ok=True)
    rep.write_text("review: plan\nwork: #61\nphase: plan\nround: 1\npublish-waived: test\n\n## Findings\n"
                   "FINDING sev=blocker action=fix issue=- by=codex origin=draft a plan gap\n")
    c = m.compliance_table(out)
    assert c["coverage"]["origin"]["codex"] == [1, 1], c["coverage"]
    assert c["kind_on_blockers"]["owed"] == 0  # still code reviews only


def test_an_empty_split_group_asks_for_no_token_reason(render, tmp_path):
    """v2.81 code review round 3: an empty group has no token median by construction; it must
    not call the tokens missing when the groups that have works measured them."""
    m = _flow_module(_merges_repo(render, tmp_path))
    measured = {"works": 3, "tokens_per_work": 1200.0}
    assert m._tokens_missing([measured, {"works": 0, "tokens_per_work": None}]) is False
    assert m._tokens_missing([measured, {"works": 2, "tokens_per_work": None}]) is True


def test_a_backdated_commit_after_a_revert_does_not_hide_it(render, tmp_path):
    """v2.81 code review round 3: `git log --since` stops at the first commit older than the
    date; a backdated commit on top of an in-window revert made the revert a measured 0."""
    from datetime import datetime, timezone
    out = _merges_repo(render, tmp_path)
    _train_merge(out, "41-a", [("feat: a (#41)", {"src/a.py": _lines(4)}, _at(2))],
                 "train: merge 41-a\n\nCloses #41", _at(2, 12))
    _put(out, 'Revert "feat: a (#41)"', {"src/a.py": None}, _at(3))
    _put(out, "chore: backdated", {"src/z.py": _lines(1)}, "2026-02-01T09:00:00+00:00")
    m = _flow_module(out)
    b = m.baseline_numbers(out, datetime(2026, 3, 1, tzinfo=timezone.utc),
                           datetime(2026, 3, 9, tzinfo=timezone.utc), commits=[])
    assert b["reverts"]["commits"] == 1, b["reverts"]


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


def test_size_bands_are_unknown_when_git_is_not_read(render, tmp_path, monkeypatch, capsys):
    """#346: with the git history unread the header said `git not read`, yet every band row
    printed 0 works — a failed git read is unknown, never zero."""
    out = _alpha_beta(render, tmp_path)
    m = _flow_module(out)
    real = m._git_out
    monkeypatch.setattr(m, "_git_out", lambda root, *args, **kw: None if args[:1] == ("log",)
                        else real(root, *args, **kw))
    m._EVENTS_READ.clear()
    t = m.size_table(out, *m._window(":"))
    assert t["population"]["why"], t["population"]
    assert all(c["works"] is None for c in t["buckets"].values()), t["buckets"]
    m.size(out)
    text = capsys.readouterr().out
    assert "git not read" in text, text
    rows = [line.split() for line in text.splitlines() if line.split()[:1] and line.split()[0] in m.SIZE_STEPS]
    assert len(rows) == 4 and all(r[1] == "unknown" for r in rows), text
    assert "n=0" not in text and "stacks: unknown" in text, text  # the stack spread too (code review)


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


# --- v2.94 E1: regression suspicion, computed from git blame at read time ------------------

def _alpha(out: Path) -> None:
    """#7 merged by the train: `src/a.py` with ten lines."""
    _train_merge(out, "7-alpha", [("feat: alpha (#7)", {"src/a.py": _lines(10, "a")}, _at(3))],
                 "train: merge 7-alpha\n\nCloses #7", _at(4, 12))


def _edit(text: str, *rows: int, tag: str = "fixed") -> str:
    lines = text.splitlines(keepends=True)
    for i in rows:
        lines[i] = f"{tag} {i}\n"
    return "".join(lines)


def _suspicion(out: Path, window: str = "2026-03-05:") -> dict:
    m = _flow_module(out)
    return m.regression_suspicion(out, *m._window(window))


def _shape(s: dict) -> tuple:
    return (s["evaluated"], [p["issue"] for p in s["suspected"]], sorted(o["why"] for o in s["open"]),
            s["repairs"], s["no_lines"])


def test_a_lockfile_or_changelog_fix_is_no_regression_suspicion(render, tmp_path):
    """Refute v2.94: E1 counts what a review counts as product (`_fix_pass_counted`) — a
    dependency bump in a lock file and a changelog line are no regression of the work that
    added them."""
    out = _merges_repo(render, tmp_path)
    _train_merge(out, "7-alpha", [("feat: alpha (#7)", {"src/a.py": _lines(10, "a"), "uv.lock": _lines(10, "l"),
                                                         "CHANGELOG.md": _lines(5, "c")}, _at(3))],
                 "train: merge 7-alpha\n\nCloses #7", _at(4, 12))
    _train_merge(out, "8-bump", [("fix: bump a dependency (#8)",
                                  {"uv.lock": _edit(_lines(10, "l"), 3),
                                   "CHANGELOG.md": _edit(_lines(5, "c"), 1)}, _at(5))],
                 "train: merge 8-bump\n\nCloses #8", _at(6, 12))
    s = _suspicion(out)
    assert s["suspected"] == [], s


def test_a_follow_up_branch_closing_the_same_issue_repairs_its_own_work(render, tmp_path):
    """Refute v2.94: a train event's own issues are its branch issue and the issues its message
    closes — a follow-up branch without a number that closes #7 repairs #7, never regresses it."""
    out = _merges_repo(render, tmp_path)
    _alpha(out)
    _train_merge(out, "alpha-followup", [("fix: alpha edge (#7)", {"src/a.py": _edit(_lines(10, "a"), 3)}, _at(5))],
                 "train: merge alpha-followup\n\nCloses #7", _at(6, 12))
    s = _suspicion(out)
    assert s["suspected"] == [] and s["repairs"] == 1, s


def test_a_fix_of_an_earlier_works_line_is_suspected_as_its_regression(render, tmp_path):
    """E1: a fix merged later changes a line #7's merge wrote — "suspected regression of #7",
    computed from `git blame` at the fix's parent; the `Regression-of:` trailer is counted
    apart, never folded in; nothing is written."""
    out = _merges_repo(render, tmp_path)
    _alpha(out)
    _train_merge(out, "8-fix", [("fix: guard alpha (#8)\n\nRegression-of: #7",
                                 {"src/a.py": _edit(_lines(10, "a"), 3)}, _at(5))],
                 "train: merge 8-fix\n\nCloses #8", _at(6, 12))
    head = _g(out, "rev-parse", "HEAD")
    s = _suspicion(out)
    assert _shape(s) == (1, [7], [], 0, 0), s
    assert s["trailers"] == 1
    fix = _g(out, "rev-parse", "8-fix")
    assert s["suspected"][0]["fix"] == fix and s["suspected"][0]["origin"] == _g(out, "rev-parse", "HEAD^1")
    text = _cli(out, "works", "--window", "2026-03-05:")
    assert _g(out, "rev-parse", "HEAD") == head and not _g(out, "status", "--porcelain")
    assert "regression suspicion" in text, text
    line = next(ln for ln in text.splitlines() if "fix commits evaluated" in ln)
    assert "fix commits evaluated 1" in line and "suspected 1" in line and "open 0" in line, line
    assert "Regression-of: trailers 1 (counted apart)" in line, line
    assert f"{fix[:12]} fix: guard alpha (#8) → #7" in text, text
    got = json.loads(_cli(out, "works", "--window", "2026-03-05:", "--json"))["regression_suspicion"]
    assert got["evaluated"] == 1 and got["suspected"][0]["issue"] == 7
    # without a window `works` would blame the whole history: no E1 at all
    assert "regression suspicion" not in _cli(out, "works")
    assert "regression_suspicion" not in json.loads(_cli(out, "works", "--json"))


def test_a_review_fix_inside_its_own_train_branch_is_no_suspicion(render, tmp_path):
    out = _merges_repo(render, tmp_path)
    _train_merge(out, "7-alpha", [("feat: alpha (#7)", {"src/a.py": _lines(10, "a")}, _at(3)),
                                  ("fix: review round 1 (#7)", {"src/a.py": _edit(_lines(10, "a"), 2)}, _at(3, 12))],
                 "train: merge 7-alpha\n\nCloses #7", _at(4, 12))
    assert _shape(_suspicion(out, "2026-03-04:")) == (1, [], [], 1, 0)


def test_a_review_fix_inside_a_finish_range_is_no_suspicion(render, tmp_path):
    """A fast-forward cannot tell the branch's commits apart: the range of the `finish` event
    is the work's own, and a fix of a line inside it repairs that work."""
    out = _merges_repo(render, tmp_path)
    _alpha(out)
    _finish_merge(out, "8-beta", [
        ("docs: plan beta", {".process-work/plans/2026-03-05-beta.md": _plan_text(8)}, _at(5)),
        ("feat: beta (#8)", {"src/b.py": _lines(6, "b")}, _at(6)),
        ("fix: review round 1 (#8)", {"src/b.py": _edit(_lines(6, "b"), 1)}, _at(7))],
        ["2026-03-05-beta.md"], _at(10, 12))
    assert _shape(_suspicion(out, "2026-03-09:")) == (1, [], [], 1, 0)


def test_a_fix_of_an_earlier_phase_of_the_same_issue_is_no_suspicion(render, tmp_path):
    out = _merges_repo(render, tmp_path)
    _train_merge(out, "9-one", [("feat: phase one (#9)", {"src/a.py": _lines(10, "a")}, _at(2))],
                 "train: merge 9-one\n\nRefs #9", _at(3, 12))
    _train_merge(out, "9-two", [("fix: phase one's edge (#9)", {"src/a.py": _edit(_lines(10, "a"), 4)}, _at(5))],
                 "train: merge 9-two\n\nCloses #9", _at(6, 12))
    assert _shape(_suspicion(out)) == (1, [], [], 1, 0)


def test_a_fix_whose_lines_go_back_to_two_merges_stays_open(render, tmp_path):
    out = _merges_repo(render, tmp_path)
    _alpha(out)
    _train_merge(out, "8-beta", [("feat: beta (#8)", {"src/b.py": _lines(6, "b")}, _at(4, 14))],
                 "train: merge 8-beta\n\nCloses #8", _at(4, 18))
    _train_merge(out, "10-fix", [("fix: both (#10)", {"src/a.py": _edit(_lines(10, "a"), 1),
                                                     "src/b.py": _edit(_lines(6, "b"), 1)}, _at(5))],
                 "train: merge 10-fix\n\nCloses #10", _at(6, 12))
    assert _shape(_suspicion(out)) == (1, [], ["several-origins"], 0, 0)


def test_an_origin_naming_no_issue_or_several_gives_no_suspicion(render, tmp_path):
    out = _merges_repo(render, tmp_path)
    _train_merge(out, "misc", [("feat: misc", {"src/m.py": _lines(5, "m")}, _at(2))],
                 "train: merge misc", _at(2, 12))
    _finish_merge(out, "11-pair", [
        ("docs: plans", {".process-work/plans/2026-03-03-one.md": _plan_text(11),
                         ".process-work/plans/2026-03-03-two.md": _plan_text(12)}, _at(3)),
        ("feat: one and two (#11)", {"src/p.py": _lines(5, "p")}, _at(3, 12))],
        ["2026-03-03-one.md", "2026-03-03-two.md"], _at(4, 12))
    _train_merge(out, "10-fix", [("fix: misc (#10)", {"src/m.py": _edit(_lines(5, "m"), 1)}, _at(5))],
                 "train: merge 10-fix\n\nCloses #10", _at(6, 12))
    _train_merge(out, "13-fix", [("fix: pair (#13)", {"src/p.py": _edit(_lines(5, "p"), 1)}, _at(7))],
                 "train: merge 13-fix\n\nCloses #13", _at(8, 12))
    assert _shape(_suspicion(out)) == (2, [], ["origin-issues", "origin-issues"], 0, 0)


def test_only_fix_commits_on_non_test_lines_are_judged(render, tmp_path):
    """A `feat:` that changes #7's line is no fix; `fixup!` and `fixture…` are no `fix` kind
    (`_commit_kind`); a fix that changes test lines only has nothing to blame."""
    out = _merges_repo(render, tmp_path)
    _train_merge(out, "7-alpha", [("feat: alpha (#7)", {"src/a.py": _lines(10, "a"),
                                                        "tests/test_a.py": _lines(4, "t")}, _at(3))],
                 "train: merge 7-alpha\n\nCloses #7", _at(4, 12))
    _train_merge(out, "10-misc", [
        ("feat: tweak alpha (#10)", {"src/a.py": _edit(_lines(10, "a"), 1)}, _at(5)),
        ("fixup! feat: tweak alpha", {"src/a.py": _edit(_lines(10, "a"), 1, 2)}, _at(5, 10)),
        ("fixture: alpha data (#10)", {"src/a.py": _edit(_lines(10, "a"), 1, 2, 3)}, _at(5, 11)),
        ("fix: the alpha test (#10)", {"tests/test_a.py": _edit(_lines(4, "t"), 1)}, _at(5, 12))],
        "train: merge 10-misc\n\nCloses #10", _at(6, 12))
    assert _shape(_suspicion(out)) == (1, [], [], 0, 1)


def test_an_origin_in_a_stray_or_mixed_range_stays_open(render, tmp_path):
    """Limit (r3): a `finish` range is mixed once a product commit names no issue — a
    suspicion into such a finish work stays open; so does one into a stray commit."""
    out = _merges_repo(render, tmp_path)
    _alpha(out)
    _put(out, "feat: straight onto main", {"src/s.py": _lines(5, "s")}, _at(4, 14))  # no marker
    _train_merge(out, "8-beta", [("feat: beta (#8)", {"src/c.py": _lines(3, "c")}, _at(4, 16))],
                 "train: merge 8-beta\n\nCloses #8", _at(4, 18))  # the stray lies in its range's strays
    _finish_merge(out, "9-gamma", [
        ("docs: plan gamma", {".process-work/plans/2026-03-05-gamma.md": _plan_text(9)}, _at(5)),
        ("feat: gamma", {"src/g.py": _lines(6, "g")}, _at(5, 12))],  # no issue in the subject
        ["2026-03-05-gamma.md"], _at(6, 12))
    m = _flow_module(out)
    gamma = next(e for e in m.merge_events(out)["events"] if e["issues"] == [9])
    assert gamma["mixed"] and gamma["bounded"]
    _train_merge(out, "10-fix", [("fix: stray (#10)", {"src/s.py": _edit(_lines(5, "s"), 1)}, _at(7))],
                 "train: merge 10-fix\n\nCloses #10", _at(8, 12))
    _train_merge(out, "11-fix", [("fix: gamma (#11)", {"src/g.py": _edit(_lines(6, "g"), 1)}, _at(9))],
                 "train: merge 11-fix\n\nCloses #11", _at(10, 12))
    assert _shape(_suspicion(out, "2026-03-07:")) == (2, [], ["mixed-origin", "no-event"], 0, 0)


def test_a_fix_in_a_mixed_event_stays_open(render, tmp_path):
    out = _merges_repo(render, tmp_path)
    _alpha(out)
    _train_merge(out, "10-fix", [("fix: guard alpha (#10)", {"src/a.py": _edit(_lines(10, "a"), 1)}, _at(5)),
                                 ("chore: another work's change (#99)", {"src/o.py": _lines(2)}, _at(5, 12))],
                 "train: merge 10-fix\n\nCloses #10", _at(6, 12))
    assert _shape(_suspicion(out)) == (1, [], ["mixed-fix"], 0, 0)


def test_a_blame_git_cannot_answer_stays_open(render, tmp_path, monkeypatch):
    """A timeout is no answer: open, never "no suspicion"."""
    out = _merges_repo(render, tmp_path)
    _alpha(out)
    _train_merge(out, "8-fix", [("fix: guard alpha (#8)", {"src/a.py": _edit(_lines(10, "a"), 3)}, _at(5))],
                 "train: merge 8-fix\n\nCloses #8", _at(6, 12))
    m = _flow_module(out)
    real = m._git_out
    monkeypatch.setattr(m, "_git_out", lambda root, *a, **kw: None if a[0] == "blame" else real(root, *a, **kw))
    s = m.regression_suspicion(out, *m._window("2026-03-05:"))
    assert _shape(s) == (1, [], ["git"], 0, 0), s


def test_works_sharing_only_a_refs_issue_do_not_hide_a_regression(render, tmp_path):
    """r3: own issues only — two works under one epic (`Refs #9`) are no phases of one work."""
    out = _merges_repo(render, tmp_path)
    _train_merge(out, "5-x", [("feat: x (#5)", {"src/a.py": _lines(10, "a")}, _at(2))],
                 "train: merge 5-x\n\nCloses #5\nRefs #9", _at(3, 12))
    _train_merge(out, "6-y", [("fix: x's edge (#6)", {"src/a.py": _edit(_lines(10, "a"), 5)}, _at(5))],
                 "train: merge 6-y\n\nCloses #6\nRefs #9", _at(6, 12))
    s = _suspicion(out)
    assert _shape(s) == (1, [5], [], 0, 0), s
    assert s["trailers"] == 0


def test_a_fix_that_renames_the_file_is_blamed_through_the_old_path(render, tmp_path):
    out = _merges_repo(render, tmp_path)
    _alpha(out)
    _train_merge(out, "10-mv", [("fix: move alpha (#10)", {"src/a.py": None,
                                                          "src/b.py": _edit(_lines(10, "a"), 6)}, _at(5))],
                 "train: merge 10-mv\n\nCloses #10", _at(6, 12))
    assert _shape(_suspicion(out)) == (1, [7], [], 0, 0)


# --- v2.94 E4: a finding's reviewer from its round's REVIEW line, at read time ----------------

def _families_repo(render, tmp_path) -> Path:
    """The policy's own family `alpha-` (ranked) and another, `beta-`; the plan `widget` of #9."""
    out = _merges_repo(render, tmp_path, github_issues=True)
    _put(out, "chore: model families", {"docs/process/model-policy.local.json": json.dumps(
        {"review_evidence": {"ranks": {"alpha-": 1}, "families": ["beta-"]}})}, _at(1, 1))
    plans = out / ".process-work/plans"
    plans.mkdir(parents=True, exist_ok=True)
    (plans / "2026-07-01-widget.md").write_text(_plan_text(9), encoding="utf-8")
    return out


def _review_line(work, rnd: int, model: str, head: str | None = None) -> str:
    art = f" base={'0' * 40} head={head}" if head else ""
    return (f"REVIEW work={work} tier=2 reviewer=r model={model} independence=bundle,non-implementing "
            f"verdict=block round={rnd}{art}\n")


def _rated(out: Path, name: str, work: str, rnd: int, findings: str, *, phase: str | None = None,
           head: str | None = None) -> None:
    reviews = out / ".process-work/reviews"
    reviews.mkdir(parents=True, exist_ok=True)
    (reviews / f"{name}.md").write_text(
        f"review: {name}\nwork: {work}\nround: {rnd}\npublish-waived: test\n"
        + (f"phase: {phase}\n" if phase else "") + (f"artifact: base={'0' * 40} head={head}\n" if head else "")
        + "\n## Findings\n" + findings, encoding="utf-8")


_BLOCKER = "FINDING sev=blocker action=fix issue=- origin=draft a gap\n"


def _line_families(out: Path) -> list:
    return sorted((fam or "-") for _w, _f, _r, fam in _flow_module(out)._attributed_findings(out))


def test_a_finding_without_by_takes_the_family_of_its_rounds_one_review_line(render, tmp_path):
    """E4: the REVIEW line names the model, the policy (`ranks`, `families`) its family — joined
    through the work's ids, so `work=widget` and `work: #9` are one work; never written."""
    out = _families_repo(render, tmp_path)
    _journal(out, _review_line("widget", 1, "beta-1") + _review_line(9, 2, "alpha-1"))
    _rated(out, "r1", "#9", 1, _BLOCKER)
    _rated(out, "r2", "widget", 2, _BLOCKER)
    before = {p: p.read_text() for p in (out / ".process-work").rglob("*.md")}
    assert _line_families(out) == ["alpha", "beta"]
    assert {p: p.read_text() for p in (out / ".process-work").rglob("*.md")} == before


def test_two_review_lines_of_one_round_or_model_same_attribute_nothing(render, tmp_path):
    out = _families_repo(render, tmp_path)
    _journal(out, _review_line(9, 1, "alpha-1") + _review_line("widget", 1, "beta-1")
             + _review_line(9, 2, "same") + _review_line(9, 3, "gamma-1"))
    for rnd in (1, 2, 3):
        _rated(out, f"r{rnd}", "#9", rnd, _BLOCKER)
    assert _line_families(out) == ["-", "-", "-"]
    # the report's head tells two lines of one round apart (the second lens' head is the first's attest)
    h1, h2 = "1" * 40, "2" * 40
    _journal(out, _review_line(9, 4, "alpha-1", h1) + _review_line(9, 4, "beta-1", h2), name="2026-07-03.md")
    _rated(out, "r4", "#9", 4, _BLOCKER, head=h2)
    assert _line_families(out) == ["-", "-", "-", "beta"]


def test_the_reports_own_by_wins_over_the_review_line(render, tmp_path):
    out = _families_repo(render, tmp_path)
    _journal(out, _review_line(9, 1, "alpha-1"))
    _rated(out, "r1", "#9", 1, "FINDING sev=blocker action=fix issue=- origin=draft by=codex a gap\n")
    assert _line_families(out) == ["-"]
    cov = _flow_module(out).compliance_table(out)["coverage"]
    assert cov["origin"] == {"codex": [1, 1]}, cov


def test_plan_reviews_join_only_plan_review_lines(render, tmp_path):
    out = _families_repo(render, tmp_path)
    _journal(out, _review_line("9-plan", 1, "beta-1") + _review_line(9, 1, "alpha-1"))
    _rated(out, "p1", "#9", 1, _BLOCKER, phase="plan")
    _rated(out, "c1", "#9", 1, _BLOCKER)
    m = _flow_module(out)
    assert [fam for *_x, fam in m._attributed_findings(out, "plan")] == ["beta"]
    assert [fam for *_x, fam in m._attributed_findings(out, "code")] == ["alpha"]


def test_rounds_and_coverage_keep_the_two_sources_apart(render, tmp_path):
    out = _families_repo(render, tmp_path)
    _journal(out, _review_line(9, 1, "alpha-1"))
    _rated(out, "r1", "#9", 1, _BLOCKER + "FINDING sev=blocker action=fix issue=- by=codex origin=fix another\n")
    text = _rounds(out)
    assert "blockers by reviewer: codex 1, - 1" in text, text
    assert "blockers without by=, by (review line): alpha 1" in text, text
    cov = _flow_module(out).compliance_table(out)["coverage"]
    assert cov["origin"] == {"codex": [1, 1], "alpha (review line)": [1, 1]}, cov
    assert "origin= alpha (review line) 1/1, codex 1/1" in text, text


def test_the_test_path_rule_has_one_owner(render, tmp_path):
    """E1 reads product paths as the review does: through `check_review._fix_pass_counted`,
    whose test rule is `check_review._is_test_path` (E3), with no copy of either of its own."""
    out = _render(render, tmp_path)
    m = _flow_module(out)
    source = (out / "scripts/process/process_kpis.py").read_text(encoding="utf-8")
    assert not hasattr(m, "_is_test_path") and not hasattr(m, "_TEST_NAME"), "a copy of the rule"
    assert "_review._fix_pass_counted(" in source
    bundle = (out / "scripts/process/make_review_bundle.py").read_text(encoding="utf-8")
    assert "def _is_test_path" not in bundle
