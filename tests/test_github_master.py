"""github-master gate (lean pass): issues ARE the work log — the gate checks
the committed snapshot itself (well-formedness, DoR at rest, board vs
state/status), with no registry mirror to join against."""
import json
import subprocess
import sys

SNAP = ".process-work/github-snapshot.json"


def _render(render, tmp_path):
    return render(tmp_path, {"project_name": "d",
                             "modules": {"github_issues": True, "github_master": True}})


def _gate(out):
    return subprocess.run(
        [sys.executable, str(out / "scripts/process/check_github_master.py"), "."],
        cwd=out, capture_output=True, text=True)


def _snapshot(out, issues, **top):
    data = {"generated_by": "gh_sync", "generated_at": "2026-08-06T00:00:00Z",
            "issues": issues}
    data.update(top)
    f = out / SNAP
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _issue(num=42, **over):
    e = {"number": num, "title": "Widget", "state": "open",
         "status": "in-progress", "board_status": None,
         "dor": {"typed": True, "ears": True, "deviation": False}}
    e.update(over)
    return e


def test_no_snapshot_is_note_not_failure(render, tmp_path):
    out = _render(render, tmp_path)
    r = _gate(out)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "expected pre-sync" in r.stdout


def test_valid_snapshot_passes_with_freshness_note(render, tmp_path):
    out = _render(render, tmp_path)
    _snapshot(out, [_issue()])
    r = _gate(out)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "freshness is not gated" in r.stdout


def test_malformed_snapshot_fails_clean(render, tmp_path):
    out = _render(render, tmp_path)
    (out / SNAP).parent.mkdir(parents=True, exist_ok=True)
    (out / SNAP).write_text("{ nope", encoding="utf-8")
    r = _gate(out)
    assert r.returncode == 1
    assert "invalid JSON" in r.stdout
    assert "Traceback" not in r.stderr


def test_unknown_entry_key_is_hard(render, tmp_path):
    # the old registry-join keys (story, blocked_by, parent) are unknown now
    out = _render(render, tmp_path)
    _snapshot(out, [_issue(story="STORY-0001")])
    r = _gate(out)
    assert r.returncode == 1
    assert "unknown key" in r.stdout


def test_duplicate_number_is_hard(render, tmp_path):
    out = _render(render, tmp_path)
    _snapshot(out, [_issue(42), _issue(42)])
    r = _gate(out)
    assert r.returncode == 1
    assert "duplicate entry" in r.stdout


def test_in_progress_without_dor_readiness_fails(render, tmp_path):
    out = _render(render, tmp_path)
    _snapshot(out, [_issue(dor={"typed": False, "ears": True, "deviation": False})])
    r = _gate(out)
    assert r.returncode == 1
    assert "not Ready" in r.stdout and "type: label" in r.stdout


def test_dor_deviation_is_the_named_escape(render, tmp_path):
    out = _render(render, tmp_path)
    _snapshot(out, [_issue(dor={"typed": False, "ears": False, "deviation": True})])
    r = _gate(out)
    assert r.returncode == 0, r.stdout


def test_missing_dor_slot_degrades_to_note(render, tmp_path):
    out = _render(render, tmp_path)
    _snapshot(out, [_issue(dor=None)])
    r = _gate(out)
    assert r.returncode == 0, r.stdout
    assert "re-run gh_sync.py" in r.stdout


def test_done_issue_needs_no_dor(render, tmp_path):
    out = _render(render, tmp_path)
    _snapshot(out, [_issue(state="closed", status="done",
                           dor={"typed": False, "ears": False, "deviation": False})])
    r = _gate(out)
    assert r.returncode == 0, r.stdout


def test_board_done_column_requires_closed_issue(render, tmp_path):
    out = _render(render, tmp_path)
    _snapshot(out, [_issue(board_status="Done")])
    r = _gate(out)
    assert r.returncode == 1
    assert "implies a closed issue" in r.stdout


def test_board_column_vs_status_label(render, tmp_path):
    out = _render(render, tmp_path)
    _snapshot(out, [_issue(status="proposed", board_status="In-progress",
                           dor=None)])
    r = _gate(out)
    assert r.returncode == 1
    assert "implies status" in r.stdout


def test_unknown_board_column_is_hard(render, tmp_path):
    out = _render(render, tmp_path)
    _snapshot(out, [_issue(board_status="Parking lot")])
    r = _gate(out)
    assert r.returncode == 1
    assert "not a known column" in r.stdout


def test_null_board_slot_is_skipped(render, tmp_path):
    out = _render(render, tmp_path)
    _snapshot(out, [_issue(board_status=None)])
    r = _gate(out)
    assert r.returncode == 0, r.stdout


def test_bad_state_and_nonstring_slots_fail_clean(render, tmp_path):
    out = _render(render, tmp_path)
    _snapshot(out, [_issue(state="reopened", title=7)])
    r = _gate(out)
    assert r.returncode == 1
    assert "Traceback" not in r.stderr


def test_gh_sync_has_no_registry_join(render, tmp_path):
    # lean pass: the sync snapshots every issue, keyed by number — no
    # story materialization requirement, no orphan concept
    out = _render(render, tmp_path)
    src = (out / "scripts/process/gh_sync.py").read_text()
    assert "feature-registry" not in src
    assert "orphan" not in src
