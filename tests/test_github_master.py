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
    assert not (out / "docs/process/modules/github-master.md").exists()


def test_artifacts_neutral(render, tmp_path):
    out = _render(render, tmp_path)
    for rel in ["docs/process/modules/github-master.md",
                "scripts/process/check_github_master.py",
                "scripts/process/gh_sync.py"]:
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


def test_malformed_snapshot_hard(render, tmp_path):
    out = _render(render, tmp_path)
    (out / ".process-work").mkdir(parents=True, exist_ok=True)
    (out / SNAP).write_text("{not json")
    r = _run(out)
    assert r.returncode == 1 and "invalid JSON" in r.stdout


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


def test_unknown_snapshot_key_hard(render, tmp_path):
    out = _render(render, tmp_path)
    _story(out, "STORY-0001")
    e = _entry("STORY-0001")
    e["bogus"] = 1
    _snapshot(out, e)
    r = _run(out)
    assert r.returncode == 1 and "unknown key" in r.stdout
