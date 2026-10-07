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


def test_rounds_without_the_finding_reader_says_blockers_not_read(render, tmp_path):
    """Without check_issues the FINDING lines are not read — the column says so instead
    of reading as zero blockers (a missing input must not read as the OK state)."""
    out = _render(render, tmp_path)
    _journal(out, _review(9, 1, "block") + _review(9, 2, "block"))
    text = _rounds(out)
    row = next(ln for ln in text.splitlines() if ln.split()[:1] == ["9"])
    assert row.split()[1:4] == ["2", "open", "2"] and row.endswith("not read"), row
    assert "blockers: not read (FINDING lines are read by check_issues — the github-issues module)" in text


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
