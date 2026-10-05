import subprocess
import sys
from pathlib import Path

KENNI = ["Kenni", "KenniNext", "Seb", "Signal", "SvelteKit", "user_id=1", "surface:ios"]

JOURNAL = ".process-work/journal"

VALID_LINES = (
    "GRADE work=42 checkpoint=1 criterion=AC-1 round=1 verdict=satisfied "
    "action=satisfied source=execute\n"
    "GRADE work=42 checkpoint=final criterion=AC-2 round=1 verdict=partial "
    "action=fixed source=review\n"
)


def _render(render, tmp_path, **mods):
    m = {"telemetry": True}
    m.update(mods)
    return render(tmp_path, {"project_name": "d", "modules": m})


def _gate(out: Path, root: Path | None = None):
    return subprocess.run(
        [sys.executable, str(out / "scripts/process/check_telemetry.py"),
         str(root if root is not None else out)],
        capture_output=True, text=True,
    )


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

def test_module_on_ships_gate_cockpit_doc_seed(render, tmp_path):
    out = _render(render, tmp_path)
    assert (out / "scripts/process/check_telemetry.py").is_file()
    assert (out / "scripts/process/process_kpis.py").is_file()
    assert (out / "docs/process/modules/telemetry.md").is_file()


def test_module_off_ships_nothing(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    assert not (out / "scripts/process/check_telemetry.py").exists()
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


def test_gate_runner_lists_telemetry(render, tmp_path):
    out = _render(render, tmp_path)
    r = subprocess.run(
        [sys.executable, str(out / "scripts/process/gate_runner.py"), "--list"],
        cwd=out, capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    assert "telemetry" in r.stdout


def test_workflow_mentions_grade_only_with_module(render, tmp_path):
    on = _render(render, tmp_path / "on")
    off = render(tmp_path / "off", {"project_name": "d"})
    assert "GRADE" in (on / "docs/process/workflow.md").read_text()
    assert "GRADE" not in (off / "docs/process/workflow.md").read_text()


# --- gate: GRADE lint --------------------------------------------------------

def test_no_grade_lines_soft_note(render, tmp_path):
    out = _render(render, tmp_path)
    r = _gate(out)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "no GRADE lines yet" in r.stdout
    assert "telemetry: OK" in r.stdout


def test_valid_lines_pass(render, tmp_path):
    out = _render(render, tmp_path)
    _journal(out, "prose before\n" + VALID_LINES + "prose after\n")
    r = _gate(out)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "2 GRADE line(s) parseable" in r.stdout


def test_malformed_line_fails_with_location(render, tmp_path):
    out = _render(render, tmp_path)
    # checkpoint= empty: the exact silent-loss shape the gate exists for
    _journal(out, "GRADE work=42 checkpoint= criterion=AC-1 round=1 "
                  "verdict=satisfied action=satisfied source=execute\n")
    r = _gate(out)
    assert r.returncode == 1
    assert "2026-07-02.md:1" in r.stdout
    assert "grammar" in r.stdout


def test_out_of_enum_values_fail(render, tmp_path):
    out = _render(render, tmp_path)
    bad = [
        ("verdict=maybe", "verdict=maybe not in"),
        ("action=ignored", "action=ignored not in"),
        ("source=nightly", "source=nightly not in"),
    ]
    for repl, expect in bad:
        line = ("GRADE work=1 checkpoint=1 criterion=A round=1 "
                "verdict=satisfied action=satisfied source=execute")
        key = repl.split("=", 1)[0]
        import re
        line = re.sub(rf"{key}=\S+", repl, line)
        _journal(out, line + "\n")
        r = _gate(out)
        assert r.returncode == 1, line
        assert expect in r.stdout, r.stdout


def test_non_numeric_round_fails(render, tmp_path):
    out = _render(render, tmp_path)
    _journal(out, "GRADE work=1 checkpoint=1 criterion=A round=one "
                  "verdict=satisfied action=satisfied source=execute\n")
    r = _gate(out)
    assert r.returncode == 1
    assert "round=one" in r.stdout


def test_prose_mentioning_grade_ignored(render, tmp_path):
    out = _render(render, tmp_path)
    _journal(out, "The GRADE trace grew today.\n"
                  "GRADE lines are appended per criterion.\n")
    r = _gate(out)
    assert r.returncode == 0, r.stdout


def test_prose_starting_with_grade_and_later_equals_ignored(render, tmp_path):
    # regression (audit): a prose line beginning 'GRADE ' with a '=' in a LATER
    # word (not the first token) must NOT be linted — its first token is a bare
    # word, so it is prose, not a GRADE line. Previously it hard-failed.
    out = _render(render, tmp_path)
    _journal(out, "GRADE totals for Q3 revenue=120k are in the report.\n")
    r = _gate(out)
    assert r.returncode == 0, r.stdout


def test_grade_with_typoed_first_key_still_linted(render, tmp_path):
    # the tightened predicate must NOT let a genuine-but-malformed GRADE line
    # slip: 'GRADE wrok=…' has a key=value first token, so it reaches the grammar
    # check and fails there.
    out = _render(render, tmp_path)
    _journal(out, "GRADE wrok=42 checkpoint=final criterion=AC-1 round=1 "
                  "verdict=satisfied action=satisfied source=review\n")
    r = _gate(out)
    assert r.returncode == 1
    assert "does not match the GRADE grammar" in r.stdout


def test_out_of_scope_verdict_is_valid(render, tmp_path):
    # audit coverage: out_of_scope is a first-class verdict driving the suite's
    # "0 false-pass in the danger direction" logic — assert the grammar accepts it
    out = _render(render, tmp_path)
    _journal(out, "GRADE work=1 checkpoint=1 criterion=A round=1 "
                  "verdict=out_of_scope action=disputed source=review\n")
    r = _gate(out)
    assert r.returncode == 0, r.stdout


def test_non_utf8_journal_fails(render, tmp_path):
    out = _render(render, tmp_path)
    d = out / JOURNAL
    d.mkdir(parents=True, exist_ok=True)
    (d / "2026-07-02.md").write_bytes(b"\xff\xfe not utf8")
    r = _gate(out)
    assert r.returncode == 1
    assert "UTF-8" in r.stdout




def test_convergence_classification(render, tmp_path):
    out = _render(render, tmp_path)
    _journal(out, (
        # converged in 2 rounds
        "GRADE work=1 checkpoint=1 criterion=A round=1 verdict=partial action=fixed source=execute\n"
        "GRADE work=1 checkpoint=1 criterion=A round=2 verdict=satisfied action=satisfied source=execute\n"
        # thrash: converged but took 3 rounds
        "GRADE work=1 checkpoint=1 criterion=B round=1 verdict=partial action=fixed source=execute\n"
        "GRADE work=1 checkpoint=1 criterion=B round=2 verdict=partial action=fixed source=execute\n"
        "GRADE work=1 checkpoint=1 criterion=B round=3 verdict=satisfied action=satisfied source=execute\n"
        # unresolved
        "GRADE work=1 checkpoint=1 criterion=C round=2 verdict=not_satisfied action=surfaced source=execute\n"
        # first-try: not convergence data
        "GRADE work=1 checkpoint=1 criterion=D round=1 verdict=satisfied action=satisfied source=execute\n"
    ))
    r = _kpis(out, "convergence")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "1/3 kickback episodes" in r.stdout
    assert "thrash=1" in r.stdout
    assert "unresolved=1" in r.stdout
    assert "first_try=1" in r.stdout




def test_cost_counts_rework(render, tmp_path):
    out = _render(render, tmp_path)
    _journal(out, (
        "GRADE work=1 checkpoint=1 criterion=A round=1 verdict=partial action=fixed source=execute\n"
        "GRADE work=1 checkpoint=1 criterion=A round=2 verdict=satisfied action=satisfied source=execute\n"
    ))
    r = _kpis(out, "cost")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "rework episodes (kickback round>1 -> fixed): 1" in r.stdout



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
    _journal(out, VALID_LINES)
    r = _kpis(out, "report")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "[convergence]" in r.stdout
    assert "[cost]" in r.stdout
    assert "[cfr]" in r.stdout


# --- hygiene -----------------------------------------------------------------

def test_neutral_no_kenni_terms(render, tmp_path):
    out = _render(render, tmp_path)
    for rel in [
        "scripts/process/check_telemetry.py",
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


# --- audit round 2 (adversarial findings) --------------------------------

def test_tab_after_grade_reaches_grammar_check(render, tmp_path):
    # F2: filter derived from the grammar — GRADE\t… must not slip past the
    # gate while the cockpit ingests it
    out = _render(render, tmp_path)
    _journal(out, "GRADE\twork=1 checkpoint=1 criterion=A round=1 "
                  "verdict=bogus action=satisfied source=execute\n")
    r = _gate(out)
    assert r.returncode == 1
    assert "verdict=bogus" in r.stdout


def test_unicode_round_fails_gate_and_cockpit_survives(render, tmp_path):
    # F3: "²" is isdigit() but int() raises — gate must fail it, and the
    # cockpit must not crash even when fed such a journal directly
    out = _render(render, tmp_path)
    _journal(out, "GRADE work=1 checkpoint=1 criterion=A round=² "
                  "verdict=satisfied action=satisfied source=execute\n")
    r = _gate(out)
    assert r.returncode == 1
    assert "round=" in r.stdout
    j = out / JOURNAL / "2026-07-02.md"
    for cmd in (["convergence", str(j)], ["cost", str(j)]):
        rc = _kpis(out, *cmd)
        assert rc.returncode == 0, rc.stderr
        assert "Traceback" not in rc.stderr




def test_nonexistent_root_fails(render, tmp_path):
    # F6: a typo'd root must not report green forever
    out = _render(render, tmp_path)
    r = _gate(out, root=out / "does-not-exist")
    assert r.returncode == 1
    assert "not a directory" in r.stdout


def test_fenced_grade_examples_are_quotations(render, tmp_path):
    # F8: fenced blocks are invisible to gate and cockpit
    out = _render(render, tmp_path)
    _journal(out, "```\nGRADE work=1 checkpoint= criterion=broken round=x "
                  "verdict=nope action=nope source=nope\n```\n")
    r = _gate(out)
    assert r.returncode == 0, r.stdout
    assert "no GRADE lines yet" in r.stdout
    r = _kpis(out, "convergence")
    assert r.returncode == 0, r.stderr




def test_cfr_outside_git_diagnostic(render, tmp_path):
    out = _render(render, tmp_path)  # rendered repo is not a git repo
    r = _kpis(out, "cfr")
    assert r.returncode == 0, r.stderr
    assert "cfr skipped" in r.stdout
    assert "Traceback" not in r.stderr


def test_non_utf8_journal_does_not_crash_cockpit(render, tmp_path):
    out = _render(render, tmp_path)
    d = out / JOURNAL
    d.mkdir(parents=True, exist_ok=True)
    (d / "2026-07-02.md").write_bytes(b"\xff\xfe garbage")
    r = _kpis(out, "convergence")
    assert r.returncode == 0, r.stderr
    assert "Traceback" not in r.stderr



def test_grade_lines_in_sharded_journal_are_read(render, tmp_path):
    # SP17: journals may be sharded per branch — the gate and cockpit read
    # .process-work/journal/**/*.md recursively, so a GRADE line in a per-branch
    # shard must be counted, not lost.
    out = _render(render, tmp_path)
    d = out / JOURNAL / "feat-x-branch"
    d.mkdir(parents=True, exist_ok=True)
    (d / "2026-07-02.md").write_text(
        "GRADE work=9 checkpoint=final criterion=AC-1 round=1 verdict=satisfied "
        "action=satisfied source=execute\n", encoding="utf-8")
    r = _gate(out)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "1 GRADE line(s) parseable" in r.stdout


def test_bulleted_grade_line_is_linted(render, tmp_path):
    # audit: '- GRADE ...' silently vanished from both the gate and cockpit
    out = render(tmp_path, {"project_name": "demo", "modules": {"telemetry": True}})
    d = out / ".process-work" / "journal"
    d.mkdir(parents=True, exist_ok=True)
    (d / "2026-07-05.md").write_text(
        "- GRADE work=x checkpoint=1 criterion=A round=1 verdict=satisfied "
        "action=bogus source=review\n", encoding="utf-8")
    r = subprocess.run([sys.executable, str(out / "scripts/process/check_telemetry.py"), str(out)],
                       capture_output=True, text=True)
    assert r.returncode == 1  # the bulleted line is seen and its bad action linted


def test_tilde_fenced_grade_ignored(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo", "modules": {"telemetry": True}})
    d = out / ".process-work" / "journal"
    d.mkdir(parents=True, exist_ok=True)
    (d / "2026-07-05.md").write_text(
        "~~~\nGRADE work=x checkpoint=1 criterion=A round=1 verdict=satisfied "
        "action=bogus source=review\n~~~\n", encoding="utf-8")
    r = subprocess.run([sys.executable, str(out / "scripts/process/check_telemetry.py"), str(out)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout  # quotation, not telemetry


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
    assert "blockers: not read" in text
