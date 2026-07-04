import json
import subprocess
import sys
from pathlib import Path

KENNI = ["Kenni", "KenniNext", "Seb", "Signal", "SvelteKit", "user_id=1", "surface:ios"]

JOURNAL = ".process-work/journal"
CALIB = "docs/process/telemetry/calibration"

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


def _case(out: Path, name: str, data):
    d = out / CALIB
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(json.dumps(data), encoding="utf-8")


# --- module wiring -----------------------------------------------------------

def test_module_on_ships_gate_cockpit_doc_seed(render, tmp_path):
    out = _render(render, tmp_path)
    assert (out / "scripts/process/check_telemetry.py").is_file()
    assert (out / "scripts/process/process_kpis.py").is_file()
    assert (out / "docs/process/modules/telemetry.md").is_file()
    assert (out / CALIB / "case.example.json").is_file()


def test_module_off_ships_nothing(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    assert not (out / "scripts/process/check_telemetry.py").exists()
    assert not (out / "scripts/process/process_kpis.py").exists()
    assert not (out / "docs/process/modules/telemetry.md").exists()
    # module OFF ships nothing — not even the seed dir (Finding-D discipline)
    assert not (out / "docs/process/telemetry").exists()


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


def test_non_utf8_journal_fails(render, tmp_path):
    out = _render(render, tmp_path)
    d = out / JOURNAL
    d.mkdir(parents=True, exist_ok=True)
    (d / "2026-07-02.md").write_bytes(b"\xff\xfe not utf8")
    r = _gate(out)
    assert r.returncode == 1
    assert "UTF-8" in r.stdout


def test_calibration_case_validation(render, tmp_path):
    out = _render(render, tmp_path)
    # invalid JSON
    d = out / CALIB
    d.mkdir(parents=True, exist_ok=True)
    (d / "bad.json").write_text("{ not json", encoding="utf-8")
    r = _gate(out)
    assert r.returncode == 1
    assert "invalid JSON" in r.stdout
    (d / "bad.json").unlink()

    # id != stem
    _case(out, "one.json", {"id": "two", "ground_truth": {"A": "not_satisfied"}})
    r = _gate(out)
    assert r.returncode == 1
    assert "filename stem" in r.stdout
    (d / "one.json").unlink()

    # missing ground_truth
    _case(out, "one.json", {"id": "one"})
    r = _gate(out)
    assert r.returncode == 1
    assert "ground_truth" in r.stdout

    # out-of-enum verdict in grader_verdict
    _case(out, "one.json", {"id": "one", "ground_truth": {"A": "not_satisfied"},
                            "grader_verdict": {"A": "maybe"}})
    r = _gate(out)
    assert r.returncode == 1
    assert "grader_verdict" in r.stdout

    # valid case passes
    _case(out, "one.json", {"id": "one", "danger_direction": True,
                            "ground_truth": {"A": "not_satisfied"},
                            "grader_verdict": None})
    r = _gate(out)
    assert r.returncode == 0, r.stdout


def test_example_seed_ignored_even_when_broken(render, tmp_path):
    out = _render(render, tmp_path)
    (out / CALIB / "broken.example.json").write_text("{ not json", encoding="utf-8")
    r = _gate(out)
    assert r.returncode == 0, r.stdout


# --- cockpit -----------------------------------------------------------------

def test_effectiveness_buckets_and_thin_action(render, tmp_path):
    out = _render(render, tmp_path)
    _journal(out, (
        # catch: kicked back, then fixed
        "GRADE work=1 checkpoint=1 criterion=A round=1 verdict=partial action=fixed source=execute\n"
        "GRADE work=1 checkpoint=1 criterion=A round=2 verdict=satisfied action=satisfied source=execute\n"
        # false alarm: disputed
        "GRADE work=1 checkpoint=1 criterion=B round=1 verdict=not_satisfied action=disputed source=execute\n"
        # surfaced
        "GRADE work=1 checkpoint=1 criterion=C round=2 verdict=not_satisfied action=surfaced source=review\n"
        # idle: first-try satisfied
        "GRADE work=1 checkpoint=1 criterion=D round=1 verdict=satisfied action=satisfied source=execute\n"
    ))
    r = _kpis(out, "effectiveness")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "catch=1" in r.stdout
    assert "false_alarm=1" in r.stdout
    assert "idle=1" in r.stdout
    assert "surfaced=1" in r.stdout
    assert "confidence: low" in r.stdout
    assert "collect" in r.stdout  # thin-n action, never a trim verdict


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


def test_suite_counts_only_graded_and_flags_false_pass(render, tmp_path):
    out = _render(render, tmp_path)
    # ungraded: a fixture, not evidence
    _case(out, "pending.json", {"id": "pending", "danger_direction": True,
                                "ground_truth": {"A": "not_satisfied"},
                                "grader_verdict": None})
    # graded danger case where the grader said "fine": false-pass
    _case(out, "slipped.json", {"id": "slipped", "danger_direction": True,
                                "ground_truth": {"A": "not_satisfied"},
                                "grader_verdict": {"A": "satisfied"}})
    r = _kpis(out, "suite")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "2 cases (2 danger-direction, 1 graded, 1 not yet graded)" in r.stdout
    assert "threshold 1" in r.stdout and "NOT MET" in r.stdout
    assert "FAIL (1)" in r.stdout
    assert "false-pass: slipped.json:A" in r.stdout


def test_suite_zero_graded_is_vacuous_not_pass(render, tmp_path):
    out = _render(render, tmp_path)
    _case(out, "pending.json", {"id": "pending", "danger_direction": True,
                                "ground_truth": {"A": "not_satisfied"},
                                "grader_verdict": None})
    r = _kpis(out, "suite")
    assert r.returncode == 0
    assert "N/A" in r.stdout  # 0 false-pass over 0 graded proves nothing


def test_cost_counts_rework(render, tmp_path):
    out = _render(render, tmp_path)
    _journal(out, (
        "GRADE work=1 checkpoint=1 criterion=A round=1 verdict=partial action=fixed source=execute\n"
        "GRADE work=1 checkpoint=1 criterion=A round=2 verdict=satisfied action=satisfied source=execute\n"
    ))
    r = _kpis(out, "cost")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "rework episodes (kickback round>1 -> fixed): 1" in r.stdout


def test_tempo_reads_issues_json_and_skips_without_tracker(render, tmp_path):
    out = _render(render, tmp_path)
    issues = [
        {"number": 1, "createdAt": "2026-06-01T00:00:00Z", "closedAt": "2026-06-03T00:00:00Z"},
        {"number": 2, "createdAt": "2026-06-01T00:00:00Z", "closedAt": "2026-06-11T00:00:00Z"},
    ]
    f = tmp_path / "issues.json"
    f.write_text(json.dumps(issues), encoding="utf-8")
    r = _kpis(out, "tempo", "--issues-json", str(f))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "p50" in r.stdout and "p90" in r.stdout
    # n=2 is thin: the confidence gate must allow only the measuring action,
    # never the calibrated-threshold verdict
    assert "confidence: low" in r.stdout
    assert "no single-value action" in r.stdout
    # live path must degrade honestly (no gh auth/repo in the test env)
    r2 = _kpis(out, "tempo")
    assert r2.returncode == 0, r2.stdout + r2.stderr


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
    assert "[effectiveness]" in r.stdout
    assert "[friction]" in r.stdout
    assert "not instrumented" in r.stdout  # friction stays honestly gated


# --- hygiene -----------------------------------------------------------------

def test_neutral_no_kenni_terms(render, tmp_path):
    out = _render(render, tmp_path)
    for rel in [
        "scripts/process/check_telemetry.py",
        "scripts/process/process_kpis.py",
        "docs/process/modules/telemetry.md",
        f"{CALIB}/case.example.json",
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


def test_directory_entries_do_not_traceback(render, tmp_path):
    # F4: a directory named *.md / *.json is skipped, not a raw IsADirectoryError
    out = _render(render, tmp_path)
    (out / JOURNAL / "x.md").mkdir(parents=True)
    (out / CALIB / "y.json").mkdir(parents=True)
    r = _gate(out)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "Traceback" not in r.stderr


def test_shape_mismatch_hard_fails_gate(render, tmp_path):
    # F1: a grader_verdict whose kind or key set differs from ground_truth
    # yields zero comparisons — the gate must fail it
    out = _render(render, tmp_path)
    _case(out, "mix.json", {"id": "mix", "danger_direction": True,
                            "ground_truth": "not_satisfied",
                            "grader_verdict": {"AC-1": "satisfied"}})
    r = _gate(out)
    assert r.returncode == 1
    assert "shape" in r.stdout
    _case(out, "mix.json", {"id": "mix", "danger_direction": True,
                            "ground_truth": {"AC-1": "not_satisfied"},
                            "grader_verdict": {"AC-2": "satisfied"}})
    r = _gate(out)
    assert r.returncode == 1
    assert "criteria" in r.stdout


def test_suite_unmatched_danger_never_reads_pass(render, tmp_path):
    # F1 belt-and-suspenders: even standalone, the cockpit must not print
    # threshold 2 PASS while a danger-direction entry went uncompared
    out = _render(render, tmp_path)
    d = tmp_path / "cases"
    d.mkdir()
    (d / "mix.json").write_text(json.dumps(
        {"id": "mix", "danger_direction": True,
         "ground_truth": {"AC-1": "not_satisfied"},
         "grader_verdict": {"AC-2": "satisfied"}}), encoding="utf-8")
    r = _kpis(out, "suite", str(d))
    assert r.returncode == 0, r.stderr
    assert "NOT EVALUABLE" in r.stdout
    assert "threshold 2 (0 false-pass in danger direction): PASS" not in r.stdout


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
    r = _kpis(out, "effectiveness")
    assert "no GRADE lines found" in r.stdout


def test_suite_non_object_case_skipped(render, tmp_path):
    # F5: gate speaks about it; the standalone cockpit skips, never crashes
    out = _render(render, tmp_path)
    d = tmp_path / "cases"
    d.mkdir()
    (d / "list.json").write_text("[]", encoding="utf-8")
    r = _kpis(out, "suite", str(d))
    assert r.returncode == 0, r.stderr
    assert "skipping non-object" in r.stdout


def test_tempo_malformed_issues_json_diagnostic(render, tmp_path):
    out = _render(render, tmp_path)
    f = tmp_path / "bad.json"
    f.write_text("{ not json", encoding="utf-8")
    r = _kpis(out, "tempo", "--issues-json", str(f))
    assert r.returncode == 0, r.stderr
    assert "tempo skipped" in r.stdout
    f.write_text('{"a": 1}', encoding="utf-8")
    r = _kpis(out, "tempo", "--issues-json", str(f))
    assert r.returncode == 0
    assert "not a JSON list" in r.stdout


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
    r = _kpis(out, "effectiveness")
    assert r.returncode == 0, r.stderr
    assert "Traceback" not in r.stderr


def test_source_attribution_ignores_file_order(render, tmp_path):
    # F7: the episode belongs to the highest round's source, not file order
    out = _render(render, tmp_path)
    _journal(out, (
        "GRADE work=1 checkpoint=1 criterion=A round=2 verdict=satisfied action=fixed source=review\n"
        "GRADE work=1 checkpoint=1 criterion=A round=1 verdict=partial action=fixed source=execute\n"
    ))
    r = _kpis(out, "effectiveness")
    assert "source=review: catch=1" in r.stdout


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
    r2 = _kpis(out, "effectiveness")
    assert "source=execute: catch=0" in r2.stdout and "idle=1" in r2.stdout
