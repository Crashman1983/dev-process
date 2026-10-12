"""graph.py (telemetry module) — relations derived read-only, with source,
commit and certainty; recommendations, never verdicts (optimization.md)."""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

STACK = {
    "paths": ["src/"], "runner": [sys.executable, "-c", "pass", "{paths}"],
    "full": [sys.executable, "-c", "pass"], "tests": ["tests/test_*.py"],
    "map": [{"from": "src/*.py", "to": ["tests"]}],
    "unmapped": "skip",
    # never run by the graph: a read-only tool executes no project selector
    "select": [sys.executable, "-c", "import pathlib; pathlib.Path('SELECTED').write_text('x')"],
}


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True).stdout


def _write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _commit(root: Path, files: dict[str, str], msg: str) -> None:
    for rel, text in files.items():
        _write(root, rel, text)
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", msg)


def _load(out: Path):
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(out / "scripts/process"))
    spec = importlib.util.spec_from_file_location("graph_under_test", out / "scripts/process/graph.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _repo(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {"telemetry": True}})
    _write(out, "docs/process/testing.local.json", json.dumps({"stacks": {"app": STACK}}))
    _git(out, "init", "-q", "-b", "main")
    _git(out, "config", "user.email", "t@t")
    _git(out, "config", "user.name", "t")
    _commit(out, {"src/a.py": "0", "src/größe.py": "0", "src/c.py": "0", "src/data.py": "0",
                  "tests/test_a.py": "0", ".github/ci.yml": "0"}, "base")
    for i in range(3):  # a and größe change together; c alone
        _commit(out, {"src/a.py": f"{i + 1}", "src/größe.py": f"{i + 1}"}, f"feat: step {i}")
        _commit(out, {"src/c.py": f"{i + 1}"}, f"feat: c {i}")
    _commit(out, {".process-work/plans/2026-10-01-a.md":
                  "# Plan\n\nissue: #4\ntier: 2\n\nTouches ./src/a.py, `.github/ci.yml` and ...src/c.py.\n"}, "docs: plan")
    return out


def test_graph_ships_with_telemetry_only(render, tmp_path):
    on = render(tmp_path / "on", {"project_name": "d", "modules": {"telemetry": True}})
    off = render(tmp_path / "off", {"project_name": "d", "modules": {"telemetry": False}})
    assert (on / "scripts/process/graph.py").is_file()
    assert not (off / "scripts/process/graph.py").exists()
    assert "## The graph" in (on / "docs/process/modules/telemetry.md").read_text()


def test_every_edge_says_where_it_comes_from(render, tmp_path):
    out = _repo(render, tmp_path)
    g = _load(out).build(out)
    assert g["note"] == "a missing edge proves no independence"
    assert all({"source", "at", "certainty"} <= e.keys() for e in g["edges"])
    edges = {(e["from"], e["to"], e["certainty"]) for e in g["edges"]}
    plan = "plan:.process-work/plans/2026-10-01-a.md"
    assert ("issue:#4", plan, "declared") in edges
    assert (plan, "file:src/a.py", "declared") in edges and (plan, "file:src/c.py", "declared") in edges
    assert (plan, "file:.github/ci.yml", "declared") in edges  # a dotfile path is a path
    assert (plan, "file:src/data.py", "declared") not in edges  # `a.py` inside `data.py` names nothing
    co = [e for e in g["edges"] if e["kind"] == "changes-with"]
    assert [(e["from"], e["to"], e["support"]) for e in co] == [("file:src/a.py", "file:src/größe.py", 3)]
    assert co[0]["certainty"] == "inferred"


def test_context_recommends_partners_and_tests_without_running_a_selector(render, tmp_path):
    out = _repo(render, tmp_path)
    g = _load(out).context(out, ["src/a.py"])
    others = {e["other"]: e["certainty"] for e in g["paths"]["src/a.py"]}
    assert others["file:src/größe.py"] == "inferred"
    assert others["test:tests"] == "derived"
    assert others["plan:.process-work/plans/2026-10-01-a.md"] == "declared"
    assert not (out / "SELECTED").exists() and not (out / "src/SELECTED").exists()


def test_missed_names_what_a_branch_may_have_overlooked(render, tmp_path):
    out = _repo(render, tmp_path)
    _git(out, "checkout", "-q", "-b", "4-faster")
    _commit(out, {"src/a.py": "new"}, "feat: faster (#4)")
    g = _load(out).missed(out, "HEAD")
    why = {c["path"]: " ".join(c["why"]) for c in g["candidates"]}
    assert "inferred" in why["src/größe.py"] and "3 commits" in why["src/größe.py"]
    assert "plan of #4 (declared)" in why["src/c.py"]
    assert "src/a.py" not in why
    r = subprocess.run([sys.executable, str(out / "scripts/process/graph.py"), "missed"],
                       cwd=out, capture_output=True, text=True)
    assert r.returncode == 0 and "possibly not followed" in r.stdout and "not verdicts" in r.stdout, r.stdout


def test_project_sources_are_named_and_their_failures_shown(render, tmp_path):
    out = _repo(render, tmp_path)
    script = ("import json; print(json.dumps({'from': 'contract:users', 'to': 'file:src/a.py', "
              "'kind': 'implements', 'certainty': 'declared'})); print('garbage')")
    _write(out, "docs/process/graph.local.json", json.dumps({"sources": [
        {"name": "contracts", "exec": [sys.executable, "-c", script]},
        {"name": "broken", "exec": [sys.executable, "-c", "raise SystemExit(4)"]}]}))
    g = _load(out).build(out)
    mine = [e for e in g["edges"] if e["source"] == "contracts"]
    assert mine == [{"from": "contract:users", "to": "file:src/a.py", "kind": "implements",
                     "source": "contracts", "at": g["at"], "certainty": "declared"}]
    assert any("contracts: line 2 is not an edge" in p for p in g["problems"])
    assert any("broken: exited 4" in p and "missing, not absent" in p for p in g["problems"])
    _write(out, "docs/process/graph.local.json", "{nope")
    assert any("unreadable" in p for p in _load(out).build(out)["problems"])
