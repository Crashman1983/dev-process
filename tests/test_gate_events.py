"""v2.68 P1: every gate run is an observation, and `nodes` weighs a gate's
cost against its blocks without claiming more than the data shows
(docs/analysis/2026-10-12-closed-loop-plan.md, §5)."""
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

_PASS = "import sys; sys.exit(0)\n"
_FAIL = "import sys; print('nope'); sys.exit(1)\n"
_FLIP = ("import pathlib, sys\n"
         "p = pathlib.Path('.git/flip-count'); n = int(p.read_text()) if p.exists() else 0\n"
         "p.write_text(str(n + 1)); sys.exit(n % 2)\n")


def _project(render, tmp_path: Path) -> Path:
    out = render(tmp_path / "p", {"project_name": "d", "modules": {"telemetry": True}})

    def git(*a):
        subprocess.run(["git", *a], cwd=out, check=True, capture_output=True)
    git("init", "-q", "-b", "main")
    git("config", "user.email", "t@t")
    git("config", "user.name", "t")
    for name, code in (("ok", _PASS), ("bad", _FAIL), ("flip", _FLIP)):
        (out / f"scripts/{name}_gate.py").write_text(code, encoding="utf-8")
    (out / "docs/process/gates.local.json").write_text(json.dumps({
        "ok": {"module": None, "command": ["scripts/ok_gate.py"]},
        "bad": {"module": None, "command": ["scripts/bad_gate.py"]},
        "flip": {"module": None, "command": ["scripts/flip_gate.py"]},
    }), encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "init")
    return out


def _run(out: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k not in ("CI", "PRE_COMMIT_TO_REF")}
    return subprocess.run([sys.executable, str(out / "scripts/process/gate_runner.py"), *args],
                          cwd=out, capture_output=True, text=True, env=env)


def _events(out: Path) -> list[dict]:
    return [json.loads(ln) for ln in (out / ".git/process-gate-events.jsonl").read_text().splitlines()]


def _kpis(out: Path):
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(out / "scripts/process"))
    spec = importlib.util.spec_from_file_location("kpis_nodes_under_test", out / "scripts/process/process_kpis.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_each_gate_run_leaves_one_event_with_cost_outcome_and_input(render, tmp_path):
    out = _project(render, tmp_path)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=out, capture_output=True,
                          text=True, check=True).stdout.strip()
    r = _run(out)
    assert r.returncode == 1  # `bad` fails; the log changes no verdict
    ev = {e["gate"]: e for e in _events(out)}
    assert ev["ok"]["outcome"] == "pass" and ev["ok"]["rc"] == 0
    assert ev["bad"]["outcome"] == "fail" and ev["bad"]["rc"] == 1
    for e in ev.values():
        assert e["head"] == head and e["dirty"] is False and e["branch"] == "main"
        assert e["mode"] == "block" and e["ci"] is False
        assert e["duration_s"] >= 0 and e["ts"].endswith("+00:00")
    # the runner goes on after a failing gate: the verdicts on one commit sit side by side
    assert {"kernel", "ok", "bad", "flip"} <= set(ev)
    _run(out, "--warn")
    assert {e["mode"] for e in _events(out) if e["gate"] == "ok"} == {"block", "warn"}


def test_a_dirty_tree_is_recorded_as_such(render, tmp_path):
    out = _project(render, tmp_path)
    (out / "scripts/ok_gate.py").write_text(_PASS + "# edited\n", encoding="utf-8")
    _run(out)
    assert {e["dirty"] for e in _events(out)} == {True}


def test_an_unwritable_log_changes_no_verdict(render, tmp_path):
    out = _project(render, tmp_path)
    (out / ".git/process-gate-events.jsonl").mkdir()  # cannot be opened for append
    r = _run(out)
    assert r.returncode == 1 and "FAILED gates" in r.stdout and "bad" in r.stdout


def test_nodes_weighs_cost_against_blocks_and_keeps_inference_estimated(render, tmp_path):
    out = _project(render, tmp_path)
    _run(out)
    _run(out)  # same commit again: more runs, not more inputs
    (out / "README.md").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=out, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "two"], cwd=out, check=True, capture_output=True)
    _run(out)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=out, capture_output=True,
                          text=True, check=True).stdout.strip()
    (out / ".process-work").mkdir(exist_ok=True)
    (out / ".process-work/gate-triage.jsonl").write_text(
        json.dumps({"gate": "bad", "commit": head, "category": "confirmed-defect",
                    "class": "contract", "fix": "abc123"}) + "\n"
        + json.dumps({"gate": "bad", "commit": "f00", "category": "unknown"}) + "\n"
        + json.dumps({"gate": "bad", "commit": "f01", "category": "probably-fine"}) + "\n"
        + "not json\n", encoding="utf-8")
    table = _kpis(out).nodes_table(out)
    nd = {n["gate"]: n for n in table["nodes"]}
    assert nd["bad"]["runs"] == 3 and nd["bad"]["inputs"]["value"] == 2
    assert nd["bad"]["blocks"] == {"runs": 3, "inputs": 2, "quality": "measured"}
    # `flip` failed beside `bad` on its commits: no sole block can be claimed for either there
    assert nd["bad"]["sole_blocks"] == {"value": 1, "quality": "estimated"}  # the second commit only
    assert nd["flip"]["flips"]["value"] == 1  # passed and failed on the first commit
    assert nd["ok"]["blocks"]["inputs"] == 0 and nd["ok"]["cost_s"]["quality"] == "measured"
    assert nd["bad"]["triage"]["value"] == {"confirmed-defect": 1, "accepted-risk": 0,
                                            "infra-or-flake": 0, "unknown": 1}
    assert nd["bad"]["triage"]["of_blocked_inputs"] == 1  # f00 is no recorded block
    assert nd["ok"]["triage"]["quality"] == "missing"
    assert len(table["triage_problems"]) == 2  # a bad category and a non-JSON line are named


def test_sole_blocks_count_only_commits_no_other_gate_failed_on(render, tmp_path):
    out = _project(render, tmp_path)
    (out / "docs/process/gates.local.json").write_text(json.dumps({
        "ok": {"module": None, "command": ["scripts/ok_gate.py"]},
        "bad": {"module": None, "command": ["scripts/bad_gate.py"]},
    }), encoding="utf-8")
    subprocess.run(["git", "commit", "-qam", "two gates"], cwd=out, check=True, capture_output=True)
    _run(out)
    nd = {n["gate"]: n for n in _kpis(out).nodes_table(out)["nodes"]}
    assert nd["bad"]["sole_blocks"]["value"] == 1


def test_nodes_cli_prints_and_says_so_when_nothing_ran(render, tmp_path):
    out = _project(render, tmp_path)
    cli = [sys.executable, str(out / "scripts/process/process_kpis.py"), "nodes"]
    r = subprocess.run(cli, cwd=out, capture_output=True, text=True)
    assert r.returncode == 0 and "no gate run recorded yet" in r.stdout
    _run(out)
    r = subprocess.run(cli, cwd=out, capture_output=True, text=True)
    assert r.returncode == 0 and "bad" in r.stdout and "blocked 1 commits" in r.stdout
    r = subprocess.run([*cli, "--json"], cwd=out, capture_output=True, text=True)
    assert json.loads(r.stdout)["days"] == 30
