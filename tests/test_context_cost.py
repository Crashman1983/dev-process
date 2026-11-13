"""v2.96 A3 (#414 AC-1): `process_context.py --cost` misst die Ankerlast je
Harness — Zeilen je Gruppe, ein eigener Block `entry_load` (Harness-Anker,
verschachtelte Anker, Overlays) und mit `--trend` dieselben Summen an jedem
Release-Wechsel von `.copier-answers.yml`."""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True


def _cost(root: Path, *args: str) -> dict:
    r = subprocess.run([sys.executable, str(root / "scripts/process/process_context.py"), ".",
                        "--cost", *args], cwd=root, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return json.loads(r.stdout)["context_cost"]


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True)


def _repo(root: Path) -> None:
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "Test")


def _commit(root: Path, msg: str) -> None:
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", msg)


def _answers(root: Path, commit: str, extra: str = "") -> None:
    (root / ".copier-answers.yml").write_text(
        f"_commit: {commit}\n_src_path: https://example.invalid/t.git\n{extra}", encoding="utf-8")


def test_every_group_carries_lines_and_the_old_keys_stay(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    cost = _cost(out)
    for block in ("mandatory", "available"):
        for name, group in cost[block].items():
            assert {"files", "tokens", "lines"} <= set(group), (block, name)
    anchor = cost["mandatory"]["anchor"]
    text = (out / "CLAUDE.md").read_text(encoding="utf-8")
    assert anchor["lines"] == len(text.splitlines()) and anchor["tokens"] == len(text) // 4
    assert {"session_start_estimate_tokens", "largest", "unit"} <= set(cost)


def test_entry_load_names_subtree_anchor_and_command_overlay(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    _repo(out)
    _commit(out, "base")
    before = _cost(out)
    (out / "backend").mkdir()
    (out / "backend/CLAUDE.md").write_text("# Backend\n\nregel eins\nregel zwei\n", encoding="utf-8")
    (out / "ios/app").mkdir(parents=True)
    (out / "ios/app/AGENTS.md").write_text("# iOS\n", encoding="utf-8")
    (out / "scratch").mkdir()
    (out / "scratch/CLAUDE.md").write_text("# untracked\n", encoding="utf-8")
    cmds = out / "docs/process/commands"
    cmds.mkdir(parents=True)
    (cmds / "plan.local.md").write_text("overlay-of: .claude/commands/plan.md\n\nmehr\n", encoding="utf-8")
    (out / "docs/process/testing.local.md").write_text("overlay-of: docs/process/testing.md\n" + "x\n" * 40,
                                                      encoding="utf-8")
    _git(out, "add", "backend/CLAUDE.md", "ios/app/AGENTS.md")
    cost = _cost(out)
    load = cost["entry_load"]
    claude = load["harnesses"]["claude"]
    assert claude["files"] == 1 and claude["tokens"] == cost["mandatory"]["anchor"]["tokens"]
    assert claude["lines"] == cost["mandatory"]["anchor"]["lines"]
    assert "copilot" not in load["harnesses"] and "agents_md" not in load["harnesses"]
    sub = load["subtree_anchors"]
    assert [p["file"] for p in sub["paths"]] == ["backend/CLAUDE.md", "ios/app/AGENTS.md"]
    assert sub["files"] == 2 and sub["lines"] == 5  # untracked scratch/ and the root stay out
    overlays = load["overlays"]
    plan = overlays["commands"]["by_command"]["plan"]
    assert plan["file"] == "docs/process/commands/plan.local.md" and plan["lines"] == 3
    assert overlays["commands"]["files"] == 1 and overlays["commands"]["lines"] == 3
    docs = overlays["docs"]
    assert docs["files"] == 1 and docs["lines"] == 41  # command overlays are not doc overlays
    assert docs["largest"][0]["file"] == "docs/process/testing.local.md"
    # a block of its own: what /prime estimates does not move
    assert cost["session_start_estimate_tokens"] == before["session_start_estimate_tokens"]
    assert before["entry_load"]["subtree_anchors"]["paths"] == []


def test_doc_overlays_list_the_five_largest(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    for i in range(7):
        (out / f"docs/process/o{i}.local.md").write_text("y\n" * (i + 1), encoding="utf-8")
    docs = _cost(out)["entry_load"]["overlays"]["docs"]
    assert docs["files"] == 7 and docs["lines"] == sum(range(1, 8))
    assert [d["file"] for d in docs["largest"]] == [f"docs/process/o{i}.local.md" for i in (6, 5, 4, 3, 2)]


def test_entry_load_per_present_harness(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "harnesses": {"copilot": True, "agents_md": True}})
    load = _cost(out)["entry_load"]["harnesses"]
    assert set(load) == {"claude", "copilot", "agents_md"}
    assert load["copilot"]["files"] == 2 and load["agents_md"]["files"] == 1
    assert all(h["tokens"] > 0 and h["lines"] > 0 for h in load.values())


def test_subtree_anchors_missing_without_git(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    sub = _cost(out)["entry_load"]["subtree_anchors"]
    assert sub["missing"] and sub["tokens"] is None and sub["paths"] == []


def test_trend_sums_at_each_release_switch(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    _repo(out)
    _answers(out, "v2.90.0")
    _commit(out, "update to v2.90.0")
    _answers(out, "v2.90.0", "project_name: d\n")  # answers file changes, release does not
    _commit(out, "answer only")
    with (out / "CLAUDE.md").open("a", encoding="utf-8") as f:
        f.write("neue zeile\n" * 10)
    (out / "backend").mkdir()
    (out / "backend/CLAUDE.md").write_text("# Backend\n", encoding="utf-8")
    _answers(out, "v2.91.0", "project_name: d\n")
    _commit(out, "update to v2.91.0")
    _answers(out, "v2.91.0-3-gabc1234", "project_name: d\n")  # no release: no point
    _commit(out, "update to a dev ref")
    cost = _cost(out, "--trend")
    assert "trend" not in _cost(out)  # opt-in
    trend = cost["trend"]
    assert trend["quality"] == "measured"
    points = trend["value"]
    assert [p["release"] for p in points] == ["v2.90.0", "v2.91.0"]
    old, new = (p["entry_load"] for p in points)
    assert new["harnesses"]["claude"]["lines"] == old["harnesses"]["claude"]["lines"] + 10
    assert old["subtree_anchors"]["files"] == 0 and new["subtree_anchors"]["files"] == 1
    assert {"anchor", "kernel", "mandatory_rules", "commands"} <= set(points[-1]["mandatory"])
    # the newest point measures the same tree the working copy holds
    now = cost["entry_load"]["harnesses"]["claude"]
    assert new["harnesses"]["claude"] == {k: now[k] for k in ("files", "tokens", "lines")}
    assert points[-1]["mandatory"]["commands"]["tokens"] == cost["mandatory"]["commands"]["tokens"]
    assert all(len(p["commit"]) >= 7 and p["date"] for p in points)


def test_trend_keeps_the_last_twelve(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    _repo(out)
    for minor in range(14):
        _answers(out, f"v2.{minor}.0")
        _commit(out, f"update to v2.{minor}.0")
    points = _cost(out, "--trend")["trend"]["value"]
    assert len(points) == 12 and points[0]["release"] == "v2.2.0" and points[-1]["release"] == "v2.13.0"


def test_trend_missing_without_git_or_release_commits(render, tmp_path):
    out = render(tmp_path / "a", {"project_name": "d"})
    trend = _cost(out, "--trend")["trend"]
    assert trend["quality"] == "missing" and trend["value"] is None and trend["why"]
    other = render(tmp_path / "b", {"project_name": "d"})
    _repo(other)
    _answers(other, "4f1c2ab")  # a SHA is no release
    _commit(other, "base")
    trend = _cost(other, "--trend")["trend"]
    assert trend["quality"] == "missing" and "release" in trend["why"]


def test_release_parser_has_one_owner(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {"telemetry": True}})
    spec = importlib.util.spec_from_file_location("process_git", out / "scripts/process/process_git.py")
    pg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pg)
    assert pg.release_of("v2.95.0") == (2, 95, 0) == pg.release_of("2.95.0")
    assert pg.release_of("v2.95.0.post1") is None and pg.release_of("v2.95.0-3-gabc") is None
    assert pg.release_of(None) is None and pg.release_of("HEAD") is None
    assert pg.answers_release("_src_path: x\n_commit: 'v2.9.1'\n") == (2, 9, 1)
    assert pg.answers_release("_commit: v2.9.1.post2.dev0+gabc\n") is None
    kpis = (out / "scripts/process/process_kpis.py").read_text(encoding="utf-8")
    assert "from process_git import answers_release" in kpis and "_RELEASE_TAG" not in kpis
