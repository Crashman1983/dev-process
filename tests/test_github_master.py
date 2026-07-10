import json
import subprocess
import sys
from pathlib import Path

REG = "docs/process/feature-registry"
SNAP = ".process-work/github-snapshot.json"


def _render(render, tmp_path, **mods):
    m = {"github_master": True, "feature_registry": True, "github_issues": True}
    m.update(mods)
    return render(tmp_path, {"project_name": "d", "modules": m})


def _run(out: Path):
    return subprocess.run(
        [sys.executable, str(out / "scripts/process/check_github_master.py"), str(out)],
        capture_output=True, text=True,
    )


def _story(out: Path, sid, status="in-progress", issue="#7", blocked_by=None, title="t"):
    d = {"id": sid, "title": title, "story": "As a x, when y, the system shall z.",
         "acceptance": [{"id": "AC1", "text": "x"}], "tests": [], "status": status}
    if issue is not None:
        d["issue"] = issue
    if blocked_by is not None:
        d["blocked_by"] = blocked_by
    p = out / REG
    p.mkdir(parents=True, exist_ok=True)
    (p / f"{sid}.json").write_text(json.dumps(d), encoding="utf-8")


def _entry(sid, number=7, title="t", state="open", status="in-progress",
           blocked_by=None):
    return {"number": number, "story": sid, "title": title, "state": state,
            "status": status, "blocked_by": blocked_by or [],
            "parent": None, "board_status": None}


def _snapshot(out: Path, *entries):
    d = out / ".process-work"
    d.mkdir(parents=True, exist_ok=True)
    (d / "github-snapshot.json").write_text(
        json.dumps({"generated_by": "test", "issues": list(entries)}), encoding="utf-8")


def _list(out: Path):
    return subprocess.run(
        [sys.executable, str(out / "scripts/process/gate_runner.py"), "--list"],
        cwd=out, capture_output=True, text=True,
    )


KENNI = ["Kenni", "KenniNext", "Seb", "Signal", "SvelteKit", "user_id=1"]


def test_artifacts_present_when_on(render, tmp_path):
    out = _render(render, tmp_path)
    assert (out / "scripts/process/check_github_master.py").is_file()
    assert (out / "scripts/process/gh_sync.py").is_file()
    assert (out / "docs/process/modules/github-master.md").is_file()


def test_artifacts_absent_when_off(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    assert not (out / "scripts/process/check_github_master.py").exists()
    assert not (out / "scripts/process/gh_sync.py").exists()
    assert not (out / "scripts/process/gh_board.py").exists()
    assert not (out / "docs/process/modules/github-master.md").exists()


def test_artifacts_neutral(render, tmp_path):
    out = _render(render, tmp_path)
    for rel in ["docs/process/modules/github-master.md",
                "scripts/process/check_github_master.py",
                "scripts/process/gh_sync.py",
                "scripts/process/gh_board.py"]:
        text = (out / rel).read_text()
        for k in KENNI:
            assert k not in text, f"{k} leaked in {rel}"


def test_gate_listed_when_on(render, tmp_path):
    out = _render(render, tmp_path)
    r = _list(out)
    assert r.returncode == 0, r.stderr
    assert "github-master" in r.stdout


def test_gate_omitted_when_off(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    r = _list(out)
    assert r.returncode == 0, r.stderr
    assert "github-master" not in r.stdout


def test_no_snapshot_is_soft(render, tmp_path):
    out = _render(render, tmp_path)
    _story(out, "STORY-0001")
    r = _run(out)
    assert r.returncode == 0, r.stdout
    assert "pre-sync" in r.stdout


def test_clean_case_ok(render, tmp_path):
    out = _render(render, tmp_path)
    _story(out, "STORY-0001", status="in-progress", title="Alpha")
    _snapshot(out, _entry("STORY-0001", title="Alpha", state="open"))
    r = _run(out)
    assert r.returncode == 0, r.stdout
    assert "github-master: OK" in r.stdout


def test_freshness_note_always_present(render, tmp_path):
    # the stale-passes-green caveat is surfaced every run, where the reader sees it
    out = _render(render, tmp_path)
    _story(out, "STORY-0001", status="in-progress", title="Alpha")
    _snapshot(out, _entry("STORY-0001", title="Alpha", state="open"))
    r = _run(out)
    assert r.returncode == 0, r.stdout
    assert "freshness is not gated" in r.stdout


def test_generated_at_allowed_and_shown(render, tmp_path):
    out = _render(render, tmp_path)
    _story(out, "STORY-0001", status="in-progress", title="Alpha")
    d = out / ".process-work"
    d.mkdir(parents=True, exist_ok=True)
    (d / "github-snapshot.json").write_text(json.dumps({
        "generated_by": "test", "generated_at": "2026-07-04T12:00:00Z",
        "issues": [_entry("STORY-0001", title="Alpha", state="open")]}))
    r = _run(out)
    assert r.returncode == 0, r.stdout  # generated_at is NOT an unknown top-level key
    assert "2026-07-04T12:00:00Z" in r.stdout


def test_malformed_snapshot_hard(render, tmp_path):
    out = _render(render, tmp_path)
    (out / ".process-work").mkdir(parents=True, exist_ok=True)
    (out / SNAP).write_text("{not json")
    r = _run(out)
    assert r.returncode == 1 and "invalid JSON" in r.stdout


def test_non_utf8_snapshot_hard(render, tmp_path):
    # a hand-corrupted committed snapshot must fail clean on the read, never
    # traceback (audit coverage: the UnicodeDecodeError branch had no test)
    out = _render(render, tmp_path)
    _story(out, "STORY-0001")
    (out / ".process-work").mkdir(parents=True, exist_ok=True)
    (out / SNAP).write_bytes(b'{"issues": []}\n\xff\xfe')
    r = _run(out)
    assert r.returncode == 1 and "not valid UTF-8" in r.stdout
    assert "Traceback" not in r.stdout and "Traceback" not in r.stderr


def test_snapshot_not_object_hard(render, tmp_path):
    # top-level must be an object with an 'issues' list
    out = _render(render, tmp_path)
    _story(out, "STORY-0001")
    (out / ".process-work").mkdir(parents=True, exist_ok=True)
    (out / SNAP).write_text(json.dumps([{"story": "STORY-0001"}]))  # a bare list
    r = _run(out)
    assert r.returncode == 1 and "object with an 'issues' list" in r.stdout


def test_entry_not_object_hard(render, tmp_path):
    # a non-dict issues[] element must fail clean, not traceback on .get()
    out = _render(render, tmp_path)
    _story(out, "STORY-0001")
    (out / ".process-work").mkdir(parents=True, exist_ok=True)
    (out / SNAP).write_text(json.dumps(
        {"generated_by": "t", "issues": ["not-an-object"]}))
    r = _run(out)
    assert r.returncode == 1 and "must be an object" in r.stdout
    assert "Traceback" not in r.stdout and "Traceback" not in r.stderr


def test_entry_missing_story_hard(render, tmp_path):
    # an entry without a 'story' join key cannot be matched to the registry
    out = _render(render, tmp_path)
    _story(out, "STORY-0001")
    e = _entry("STORY-0001")
    del e["story"]
    _snapshot(out, e)
    r = _run(out)
    assert r.returncode == 1 and "missing 'story'" in r.stdout


def test_entry_bad_state_hard(render, tmp_path):
    # 'state' is GitHub open/closed — any other value is a corrupt snapshot
    out = _render(render, tmp_path)
    _story(out, "STORY-0001")
    e = _entry("STORY-0001", state="merged")  # not open/closed
    _snapshot(out, e)
    r = _run(out)
    assert r.returncode == 1 and "'state' must be 'open' or 'closed'" in r.stdout


def test_entry_nonstring_title_fails_clean(render, tmp_path):
    # a hand-edited numeric title must fail clean before the drift compare
    out = _render(render, tmp_path)
    _story(out, "STORY-0001")
    e = _entry("STORY-0001")
    e["title"] = 42
    _snapshot(out, e)
    r = _run(out)
    assert r.returncode == 1 and "'title' must be a string or null" in r.stdout
    assert "Traceback" not in r.stdout and "Traceback" not in r.stderr


def test_missing_issue_invariant_hard(render, tmp_path):
    out = _render(render, tmp_path)
    _story(out, "STORY-0001", issue=None)  # no issue ref
    _snapshot(out, _entry("STORY-0001"))
    r = _run(out)
    assert r.returncode == 1 and "requires every live story to trace to an issue" in r.stdout


def test_deprecated_without_issue_ok(render, tmp_path):
    out = _render(render, tmp_path)
    _story(out, "STORY-0001", status="deprecated", issue=None)
    _snapshot(out)  # empty snapshot; deprecated is exempt
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_story_without_snapshot_entry_hard(render, tmp_path):
    out = _render(render, tmp_path)
    _story(out, "STORY-0001")
    _snapshot(out)  # no entry for it
    r = _run(out)
    assert r.returncode == 1 and "no snapshot entry" in r.stdout


def test_snapshot_without_story_hard(render, tmp_path):
    out = _render(render, tmp_path)
    _snapshot(out, _entry("STORY-0099"))  # pulled but not materialized
    r = _run(out)
    assert r.returncode == 1 and "no registry story exists" in r.stdout


def test_title_drift_hard(render, tmp_path):
    out = _render(render, tmp_path)
    _story(out, "STORY-0001", title="Local title")
    _snapshot(out, _entry("STORY-0001", title="GitHub title"))
    r = _run(out)
    assert r.returncode == 1 and "title drifts" in r.stdout


def test_status_state_mismatch_hard(render, tmp_path):
    out = _render(render, tmp_path)
    _story(out, "STORY-0001", status="done")  # done -> issue must be closed
    _snapshot(out, _entry("STORY-0001", state="open"))
    r = _run(out)
    assert r.returncode == 1 and "implies issue closed" in r.stdout


def test_status_done_closed_ok(render, tmp_path):
    out = _render(render, tmp_path)
    _story(out, "STORY-0001", status="done", title="t")
    _snapshot(out, _entry("STORY-0001", state="closed", status="done"))
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_blocked_by_drift_hard(render, tmp_path):
    out = _render(render, tmp_path)
    _story(out, "STORY-0001", blocked_by=["STORY-0002"])
    _snapshot(out, _entry("STORY-0001", blocked_by=[]))
    r = _run(out)
    assert r.returncode == 1 and "blocked_by drifts" in r.stdout


def test_status_drift_same_state_hard(render, tmp_path):
    # proposed vs in-progress both map to 'open' — the direct status compare
    # must still catch the divergence (F2)
    out = _render(render, tmp_path)
    _story(out, "STORY-0001", status="proposed")
    _snapshot(out, _entry("STORY-0001", state="open", status="in-progress"))
    r = _run(out)
    assert r.returncode == 1 and "status drifts" in r.stdout


def test_malformed_blocked_by_type_fails_clean(render, tmp_path):
    # a hand-edited snapshot with a non-list blocked_by must fail clean, not
    # traceback (F1)
    out = _render(render, tmp_path)
    _story(out, "STORY-0001")
    e = _entry("STORY-0001")
    e["blocked_by"] = 5
    _snapshot(out, e)
    r = _run(out)
    assert r.returncode == 1
    assert "blocked_by" in r.stdout and "must be a list" in r.stdout
    assert "Traceback" not in r.stdout and "Traceback" not in r.stderr


def test_duplicate_snapshot_entry_hard(render, tmp_path):
    # a duplicate story entry must not silently mask a divergent one (F3)
    out = _render(render, tmp_path)
    _story(out, "STORY-0001", title="Right")
    _snapshot(out,
              _entry("STORY-0001", number=8, title="WRONG", state="closed", status="done"),
              _entry("STORY-0001", number=7, title="Right"))
    r = _run(out)
    assert r.returncode == 1 and "duplicate entry" in r.stdout


def test_unknown_top_level_key_hard(render, tmp_path):
    # top-level strictness symmetric with per-entry strictness (F4)
    out = _render(render, tmp_path)
    _story(out, "STORY-0001")
    d = out / ".process-work"
    d.mkdir(parents=True, exist_ok=True)
    (d / "github-snapshot.json").write_text(json.dumps(
        {"generated_by": "t", "bogus": 1, "issues": [_entry("STORY-0001")]}))
    r = _run(out)
    assert r.returncode == 1 and "unknown top-level key" in r.stdout


def test_status_vocabulary_agrees_across_gates(render, tmp_path):
    # audit (both architects): check_github_master.STATUS_STATE.get(status) fails
    # OPEN on an unknown status — a status added to check_feature_registry.STATUSES
    # but not to STATUS_STATE would silently stop being drift-checked. The gates
    # cannot import each other (module isolation), so a cross-gate test is the guard.
    import importlib.util

    def _load(name, path):
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    out = render(tmp_path, {"project_name": "d",
                            "modules": {"feature_registry": True, "github_master": True}})
    fr = _load("cfr_x", out / "scripts/process/check_feature_registry.py")
    gm = _load("cgm_x", out / "scripts/process/check_github_master.py")
    missing = fr.STATUSES - set(gm.STATUS_STATE)
    assert not missing, (f"status-vocab drift: {missing} in feature-registry STATUSES "
                         f"but not github-master STATUS_STATE — its drift check would "
                         f"silently fail open on those statuses")
    # every board column must imply a real registry status
    assert set(gm.BOARD_STATUS.values()) <= fr.STATUSES


def _board(entry, col):
    entry = dict(entry)
    entry["board_status"] = col
    return entry


def test_board_unknown_column_hard(render, tmp_path):
    out = _render(render, tmp_path)
    _story(out, "STORY-0001", status="in-progress")
    _snapshot(out, _board(_entry("STORY-0001", status="in-progress"), "Frozen"))
    r = _run(out)
    assert r.returncode == 1 and "not a known" in r.stdout


def test_board_column_status_mismatch_hard(render, tmp_path):
    out = _render(render, tmp_path)
    _story(out, "STORY-0001", status="in-progress")
    # card in Done while the story is in-progress
    _snapshot(out, _board(_entry("STORY-0001", status="in-progress"), "Done"))
    r = _run(out)
    assert r.returncode == 1 and "implies status 'done'" in r.stdout


def test_board_backlog_proposed_ok(render, tmp_path):
    out = _render(render, tmp_path)
    _story(out, "STORY-0001", status="proposed")
    _snapshot(out, _board(_entry("STORY-0001", status="proposed"), "Backlog"))
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_board_review_maps_to_in_progress_ok(render, tmp_path):
    out = _render(render, tmp_path)
    _story(out, "STORY-0001", status="in-progress")
    _snapshot(out, _board(_entry("STORY-0001", status="in-progress"), "Review"))
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_board_done_consistent_ok(render, tmp_path):
    out = _render(render, tmp_path)
    _story(out, "STORY-0001", status="done")
    _snapshot(out, _board(_entry("STORY-0001", state="closed", status="done"), "Done"))
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_board_deprecated_exempt(render, tmp_path):
    out = _render(render, tmp_path)
    _story(out, "STORY-0001", status="deprecated")
    e = _board(_entry("STORY-0001", state="closed", status="deprecated"), "Done")
    _snapshot(out, e)
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_board_non_string_fails_clean(render, tmp_path):
    # a hand-edited numeric board_status must fail clean (unknown column), never
    # traceback on .lower()
    out = _render(render, tmp_path)
    _story(out, "STORY-0001", status="in-progress")
    e = _entry("STORY-0001", status="in-progress")
    e["board_status"] = 42
    _snapshot(out, e)
    r = _run(out)
    assert r.returncode == 1 and "not a known" in r.stdout
    assert "Traceback" not in r.stdout and "Traceback" not in r.stderr


def test_board_tool_present_when_on(render, tmp_path):
    out = _render(render, tmp_path)
    assert (out / "scripts/process/gh_board.py").is_file()


def test_parent_drift_hard(render, tmp_path):
    out = _render(render, tmp_path)
    _story(out, "STORY-0001", title="t")
    # story has no parent; snapshot (GitHub sub-issue) says STORY-0002 -> drift
    e = _entry("STORY-0001")
    e["parent"] = "STORY-0002"
    _snapshot(out, e)
    r = _run(out)
    assert r.returncode == 1 and "parent drifts" in r.stdout


def test_unknown_snapshot_key_hard(render, tmp_path):
    out = _render(render, tmp_path)
    _story(out, "STORY-0001")
    e = _entry("STORY-0001")
    e["bogus"] = 1
    _snapshot(out, e)
    r = _run(out)
    assert r.returncode == 1 and "unknown key" in r.stdout


def test_mixed_type_blocked_by_fails_clean(render, tmp_path):
    # audit: sorted([1, "STORY-0002"]) raised an uncaught TypeError (traceback)
    out = _render(render, tmp_path)
    _story(out, "STORY-0001", blocked_by=["STORY-0002"])
    e = _entry("STORY-0001")
    e["blocked_by"] = [1, "STORY-0002"]
    _snapshot(out, e)
    r = _run(out)
    assert r.returncode == 1
    assert "non-string element" in r.stdout
    assert "Traceback" not in r.stdout and "Traceback" not in r.stderr


# --- Definition of Ready, enforced (dor slot) --------------------------------

def _dor(typed=True, ears=True, deviation=False):
    return {"typed": typed, "ears": ears, "deviation": deviation}


def test_in_progress_not_ready_hard(render, tmp_path):
    out = _render(render, tmp_path)
    _story(out, "STORY-0001", status="in-progress")
    _snapshot(out, {**_entry("STORY-0001"), "dor": _dor(typed=False)})
    r = _run(out)
    assert r.returncode == 1
    flat = " ".join(r.stdout.split())
    assert "not Ready" in flat and "type: label (R1)" in flat


def test_in_progress_no_ears_hard(render, tmp_path):
    out = _render(render, tmp_path)
    _story(out, "STORY-0001", status="in-progress")
    _snapshot(out, {**_entry("STORY-0001"), "dor": _dor(ears=False)})
    r = _run(out)
    assert r.returncode == 1
    assert "EARS acceptance (R2)" in r.stdout.replace("\n", " ")


def test_deviation_is_the_named_escape(render, tmp_path):
    out = _render(render, tmp_path)
    _story(out, "STORY-0001", status="in-progress")
    _snapshot(out, {**_entry("STORY-0001"),
                    "dor": _dor(typed=False, ears=False, deviation=True)})
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_ready_issue_passes(render, tmp_path):
    out = _render(render, tmp_path)
    _story(out, "STORY-0001", status="in-progress")
    _snapshot(out, {**_entry("STORY-0001"), "dor": _dor()})
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_proposed_not_gated_by_dor(render, tmp_path):
    # DoR gates STARTING; a proposed story with an unready issue is fine
    out = _render(render, tmp_path)
    _story(out, "STORY-0001", status="proposed")
    _snapshot(out, {**_entry("STORY-0001", status="proposed"),
                    "dor": _dor(typed=False, ears=False)})
    r = _run(out)
    assert r.returncode == 0, r.stdout


def test_missing_dor_slot_is_soft(render, tmp_path):
    # a snapshot predating the dor slot degrades to a note, never a fake fail
    out = _render(render, tmp_path)
    _story(out, "STORY-0001", status="in-progress")
    _snapshot(out, _entry("STORY-0001"))  # no dor key at all
    r = _run(out)
    assert r.returncode == 0, r.stdout
    assert "predates the dor slot" in r.stdout.replace("\n", " ")


def test_malformed_dor_fails_clean(render, tmp_path):
    out = _render(render, tmp_path)
    _story(out, "STORY-0001", status="in-progress")
    _snapshot(out, {**_entry("STORY-0001"), "dor": {"typed": "yes"}})
    r = _run(out)
    assert r.returncode == 1
    assert "boolean typed/ears/deviation" in r.stdout.replace("\n", " ")
    assert "Traceback" not in r.stdout + r.stderr


def test_gh_sync_dor_facts(render, tmp_path):
    # the pure helper that derives DoR facts at sync time
    import importlib.util
    out = _render(render, tmp_path)
    spec = importlib.util.spec_from_file_location("ghs", out / "scripts/process/gh_sync.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    f = mod._dor_facts
    assert f([{"name": "type:feature"}], "t", "When x, the system shall y.") == \
        {"typed": True, "ears": True, "deviation": False}
    # uppercase SHALL and the German heading both count
    assert f([{"name": "type:bug"}], "t", "The system SHALL x")["ears"] is True
    assert f([{"name": "type:bug"}], "t", "## Akzeptanzkriterien (EARS)")["ears"] is True
    # epic is EARS-exempt (label or title)
    assert f([{"name": "type:epic"}], "t", "scope only")["ears"] is True
    assert f([], "EPIC: big", "scope only")["ears"] is True
    # untyped, prose-only -> not ready
    assert f([], "t", "some prose") == {"typed": False, "ears": False, "deviation": False}
    # the named escape: a Deviations heading in the body
    assert f([], "t", "## Deviations\nspike, no EARS yet")["deviation"] is True
    assert f([], "t", "we deviate informally")["deviation"] is False


def test_dor_extra_key_fails_clean(render, tmp_path):
    # a typoed fourth key must not vanish silently — exact key set enforced
    out = _render(render, tmp_path)
    _story(out, "STORY-0001", status="in-progress")
    _snapshot(out, {**_entry("STORY-0001"), "dor": {**_dor(), "bogus": True}})
    r = _run(out)
    assert r.returncode == 1
    assert "boolean typed/ears/deviation" in " ".join(r.stdout.split())
