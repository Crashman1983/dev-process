import json
import subprocess
import sys
from pathlib import Path

REG = "docs/process/feature-registry"


def _render(render, tmp_path):
    return render(tmp_path, {"project_name": "d", "modules": {"feature_registry": True}})


def _run(out: Path):
    return subprocess.run(
        [sys.executable, str(out / "scripts/process/story_order.py"), str(out)],
        capture_output=True, text=True,
    )


def _story(out: Path, sid: str, status="proposed", blocked_by=None, parent=None):
    d = {"id": sid, "title": f"title {sid}", "story": "s",
         "acceptance": [{"id": "AC1", "text": "x"}], "tests": [], "status": status}
    if blocked_by is not None:
        d["blocked_by"] = blocked_by
    if parent is not None:
        d["parent"] = parent
    p = out / REG
    p.mkdir(parents=True, exist_ok=True)
    (p / f"{sid}.json").write_text(json.dumps(d), encoding="utf-8")


def test_hierarchy_shows_epic_and_children(render, tmp_path):
    out = _render(render, tmp_path)
    _story(out, "STORY-0001")  # epic
    _story(out, "STORY-0002", parent="STORY-0001")
    _story(out, "STORY-0003", parent="STORY-0001")
    r = _run(out)
    assert r.returncode == 0, r.stdout
    hier = r.stdout.split("Hierarchy")[1]
    assert "STORY-0001" in hier
    assert "STORY-0002" in hier and "STORY-0003" in hier


def test_tool_present_when_module_on(render, tmp_path):
    out = _render(render, tmp_path)
    assert (out / "scripts/process/story_order.py").is_file()


def test_tool_absent_when_module_off(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    assert not (out / "scripts/process/story_order.py").exists()


def test_ready_and_blocked_split(render, tmp_path):
    out = _render(render, tmp_path)
    _story(out, "STORY-0001", blocked_by=["STORY-0002"])
    _story(out, "STORY-0002")
    r = _run(out)
    assert r.returncode == 0, r.stdout
    # 0002 has no blockers -> ready; 0001 waits on 0002
    ready_line = r.stdout.split("Blocked:")[0]
    assert "STORY-0002" in ready_line
    assert "STORY-0001  waits on: STORY-0002" in r.stdout


def test_done_blocker_unblocks_dependent(render, tmp_path):
    out = _render(render, tmp_path)
    _story(out, "STORY-0001", blocked_by=["STORY-0002"])
    _story(out, "STORY-0002", status="done")
    r = _run(out)
    assert r.returncode == 0, r.stdout
    # 0002 done -> 0001 becomes ready, not blocked
    assert "STORY-0001  waits on" not in r.stdout
    ready_line = r.stdout.split("Blocked:")[0]
    assert "STORY-0001" in ready_line


def test_topological_order_respects_dependency(render, tmp_path):
    out = _render(render, tmp_path)
    _story(out, "STORY-0001", blocked_by=["STORY-0002"])
    _story(out, "STORY-0002", blocked_by=["STORY-0003"])
    _story(out, "STORY-0003")
    r = _run(out)
    assert r.returncode == 0, r.stdout
    order = r.stdout.split("Suggested order:")[1]
    i3 = order.index("STORY-0003")
    i2 = order.index("STORY-0002")
    i1 = order.index("STORY-0001")
    assert i3 < i2 < i1  # blockers come before dependents


def test_cycle_reported_not_ordered(render, tmp_path):
    out = _render(render, tmp_path)
    _story(out, "STORY-0001", blocked_by=["STORY-0002"])
    _story(out, "STORY-0002", blocked_by=["STORY-0001"])
    r = _run(out)
    assert r.returncode == 0, r.stdout  # a tool, never fails
    assert "cycle among" in r.stdout
