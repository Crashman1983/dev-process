import subprocess
import sys


def test_module_off_absent(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    assert not (out / "scripts/process/check_doc_drift.py").exists()
    assert not (out / "docs/process/modules/doc-drift-gate.md").exists()


def test_module_on_present(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {"doc_drift_gate": True}})
    assert (out / "scripts/process/check_doc_drift.py").is_file()
    assert (out / "docs/process/modules/doc-drift-gate.md").is_file()


def test_gate_detects_broken_reference(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {"doc_drift_gate": True}})
    script = out / "scripts/process/check_doc_drift.py"
    # clean tree: gate passes
    assert subprocess.run([sys.executable, str(script), str(out)]).returncode == 0
    # inject a doc that references a non-existent file -> gate fails
    (out / "docs/process/broken.md").write_text("See [x](does/not/exist.py).")
    assert subprocess.run([sys.executable, str(script), str(out)]).returncode != 0


def test_gate_skips_runtime_process_work_paths(render, tmp_path):
    # .process-work/ files are runtime working memory, never shipped — a doc
    # referencing one literally (e.g. .process-work/inbox.md) must not be flagged
    out = render(tmp_path, {"project_name": "d", "modules": {"doc_drift_gate": True}})
    script = out / "scripts/process/check_doc_drift.py"
    (out / "docs/process/conv.md").write_text("Capture in `.process-work/inbox.md`.")
    assert subprocess.run([sys.executable, str(script), str(out)]).returncode == 0


def test_gate_skips_decision_records(render, tmp_path):
    # ADRs are point-in-time records owned by the decision-records gate; their
    # historical code refs must not read as drift
    out = render(tmp_path, {"project_name": "d", "modules": {"doc_drift_gate": True}})
    script = out / "scripts/process/check_doc_drift.py"
    (out / "docs/process/adr/adr-0002-old.md").write_text(
        "# ADR-0002: Old\n\nSee `code/that/was/deleted.py`.\n")
    assert subprocess.run([sys.executable, str(script), str(out)]).returncode == 0


def test_gate_notes_anchor_over_budget_without_failing(render, tmp_path):
    # anchors regrow silently — over the line budget the gate notes it for a
    # human but never fails (accretion is a judgment call, not a broken ref)
    out = render(tmp_path, {"project_name": "d", "modules": {"doc_drift_gate": True}})
    script = out / "scripts/process/check_doc_drift.py"
    claude = out / "CLAUDE.md"
    claude.write_text(claude.read_text() + "filler\n" * 300)
    r = subprocess.run([sys.executable, str(script), str(out)],
                       capture_output=True, text=True)
    assert r.returncode == 0
    assert "note:" in r.stdout and "budget" in r.stdout
    # and a raised budget silences the note
    import os
    env = dict(os.environ, ANCHOR_LINE_BUDGET="10000")
    r2 = subprocess.run([sys.executable, str(script), str(out)],
                        capture_output=True, text=True, env=env)
    assert r2.returncode == 0 and "note:" not in r2.stdout


def test_gate_runner_leaves_no_pycache(render, tmp_path):
    # the gates' sibling imports must not litter the adopter repo with
    # untracked __pycache__ (gate_runner sets PYTHONDONTWRITEBYTECODE)
    import subprocess
    import sys
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    r = subprocess.run([sys.executable, str(out / "scripts/process/gate_runner.py")],
                       cwd=out, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert not (out / "scripts/process/__pycache__").exists()


def test_gate_runner_note_ledger_prints_a_note_once(render, tmp_path):
    # v2.8.1: a note unchanged since the last run is not repeated (it would
    # cost tokens in every agent context) — the count is shown, --all-notes
    # restores everything; a NEW note prints immediately
    import subprocess
    import sys
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=out, check=True)
    runner = [sys.executable, str(out / "scripts/process/gate_runner.py")]
    first = subprocess.run(runner, cwd=out, capture_output=True, text=True)
    assert first.returncode == 0, first.stdout + first.stderr
    assert "review: note: no REVIEW attestations yet" in first.stdout
    second = subprocess.run(runner, cwd=out, capture_output=True, text=True)
    assert second.returncode == 0
    assert "no REVIEW attestations yet" not in second.stdout
    assert "known note(s) unchanged since the last run" in second.stdout
    third = subprocess.run(runner + ["--all-notes"], cwd=out,
                           capture_output=True, text=True)
    assert "no REVIEW attestations yet" in third.stdout
    # a new note appears at once
    d = out / ".process-work/plans"
    d.mkdir(parents=True, exist_ok=True)
    (d / "2026-09-07-wip.md").write_text("# WIP\n\ntier: 2\n")
    fourth = subprocess.run(runner, cwd=out, capture_output=True, text=True)
    assert "active Tier 2 plan(s)" in fourth.stdout
    assert not (out / "process-notes-ledger").exists()  # lives in .git/


def test_gate_runner_names_hand_edited_manifest_cause(render, tmp_path):
    # SP52: module enabled but script missing (the hand-edited-answers trap)
    # must name the likely cause, not just "can't open file"
    import subprocess
    import sys
    out = render(tmp_path, {"project_name": "d",
                            "modules": {"telemetry": True}})
    (out / "scripts/process/check_telemetry.py").unlink()
    r = subprocess.run([sys.executable, str(out / "scripts/process/gate_runner.py")],
                       cwd=out, capture_output=True, text=True)
    assert r.returncode == 1
    assert "hand" in r.stderr and "copier update" in r.stderr


def test_gate_runner_dates_a_chronic_red(render, tmp_path):
    # SP70: a gate red for days is wallpaper — the runner prints the age
    import datetime
    import subprocess
    import sys
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=out, check=True)
    (out / ".process-work/journal").mkdir(parents=True, exist_ok=True)
    (out / ".process-work/journal/x.md").write_text("REVIEW work=1 tier=9\n")  # malformed: red
    runner = [sys.executable, str(out / "scripts/process/gate_runner.py")]
    r1 = subprocess.run(runner, cwd=out, capture_output=True, text=True)
    assert r1.returncode == 1 and "red since" not in r1.stdout  # first day: no age yet
    ledger = out / ".git/process-red-ledger"
    old = (datetime.date.today() - datetime.timedelta(days=12)).isoformat()
    ledger.write_text(f"review {old}\n")
    r2 = subprocess.run(runner, cwd=out, capture_output=True, text=True)
    assert "review (red since" in r2.stdout and "12 day(s)" in r2.stdout
    assert "wallpaper" in r2.stdout
    (out / ".process-work/journal/x.md").unlink()
    r3 = subprocess.run(runner, cwd=out, capture_output=True, text=True)
    assert r3.returncode == 0 and ledger.read_text() == ""  # green: the clock stops
