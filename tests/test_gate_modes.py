"""v2.68 P2: a gate's mode comes from the change record alone; weakening needs an
owner line and never touches a core or protected gate; the sentinel only ever
restores, and a restored gate stays locked until triaged
(docs/analysis/2026-10-12-closed-loop-plan.md, §6)."""
import json
import os
import subprocess
import sys
from pathlib import Path

_PASS = "import sys; sys.exit(0)\n"
_FAIL = "import sys; print('nope'); sys.exit(1)\n"


def _project(render, tmp_path: Path) -> Path:
    out = render(tmp_path / "p", {"project_name": "d", "modules": {"telemetry": True}})

    def git(*a):
        subprocess.run(["git", *a], cwd=out, check=True, capture_output=True)
    git("init", "-q", "-b", "main")
    git("config", "user.email", "t@t")
    git("config", "user.name", "t")
    for name, code in (("ok", _PASS), ("bad", _FAIL)):
        (out / f"scripts/{name}_gate.py").write_text(code, encoding="utf-8")
    (out / "docs/process/gates.local.json").write_text(json.dumps({
        "ok": {"module": None, "command": ["scripts/ok_gate.py"]},
        "bad": {"module": None, "command": ["scripts/bad_gate.py"]},
    }), encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "init")
    return out


def _env() -> dict:
    return {k: v for k, v in os.environ.items() if k not in ("CI", "PRE_COMMIT_TO_REF")}


def _modes(out: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(out / "scripts/process/gate_modes.py"), *args],
                          cwd=out, capture_output=True, text=True, env=_env())


def _gates(out: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(out / "scripts/process/gate_runner.py")],
                          cwd=out, capture_output=True, text=True, env=_env())


def _commit(out: Path, msg: str = "change") -> None:
    subprocess.run(["git", "add", "-A"], cwd=out, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", msg], cwd=out, check=True, capture_output=True)


def _events(out: Path) -> list[dict]:
    return [json.loads(ln) for ln in (out / ".git/process-gate-events.jsonl").read_text().splitlines()]


def test_a_shadow_gate_runs_and_records_but_does_not_block(render, tmp_path):
    out = _project(render, tmp_path)
    assert _gates(out).returncode == 1  # `bad` blocks by default
    r = _modes(out, "weaken", "bad", "--to", "shadow", "--decision", "owner 2026-10-12: watch it first")
    assert r.returncode == 0, r.stderr
    _commit(out, "shadow bad")
    g = _gates(out)
    assert g.returncode == 0, g.stdout + g.stderr
    assert "bad failed in shadow mode" in g.stderr
    last = [e for e in _events(out) if e["gate"] == "bad"][-1]
    assert last["mode"] == "shadow" and last["outcome"] == "fail"


def test_weakening_needs_an_owner_line_and_never_touches_a_core_gate(render, tmp_path):
    out = _project(render, tmp_path)
    r = _modes(out, "weaken", "bad", "--to", "off", "--decision", "steward: it is slow")
    assert r.returncode == 1 and "owner decision" in r.stderr
    r = _modes(out, "weaken", "review", "--to", "off", "--decision", "owner: trust me")
    assert r.returncode == 1 and "core gate" in r.stderr
    r = _modes(out, "weaken", "bad", "--to", "sampled", "--rate", "1.5", "--decision", "owner: x")
    assert r.returncode == 1 and "rate" in r.stderr
    (out / "docs/process/optimization.local.json").write_text(
        json.dumps({"guardrails": {"protected": ["bad"]}}), encoding="utf-8")
    r = _modes(out, "weaken", "bad", "--to", "off", "--decision", "owner: x")
    assert r.returncode == 1 and "protected" in r.stderr
    assert not (out / ".process-work/gate-changes.jsonl").exists()


def test_a_hand_written_record_that_breaks_a_rule_leaves_the_gate_blocking(render, tmp_path):
    out = _project(render, tmp_path)
    (out / ".process-work").mkdir(exist_ok=True)
    (out / ".process-work/gate-changes.jsonl").write_text(
        json.dumps({"gate": "review", "action": "weaken", "to": "off", "decision": "owner: x"}) + "\n"
        + json.dumps({"gate": "bad", "action": "weaken", "to": "off", "decision": "agent: x"}) + "\n"
        + "garbage\n", encoding="utf-8")
    _commit(out)
    g = _gates(out)
    assert g.returncode == 1 and "bad" in g.stdout.split("FAILED gates:")[-1]
    assert "a core gate cannot be weakened" in g.stdout and "owner decision" in g.stdout
    assert _modes(out, "check").returncode == 1


def test_off_skips_and_sampled_runs_on_a_stable_share_of_commits(render, tmp_path):
    out = _project(render, tmp_path)
    _modes(out, "weaken", "ok", "--to", "off", "--decision", "owner: replaced by X")
    _modes(out, "weaken", "bad", "--to", "sampled", "--rate", "0.5", "--decision", "owner: sample it")
    _commit(out, "modes")
    seen = set()
    for i in range(8):
        (out / f"f{i}.txt").write_text(str(i), encoding="utf-8")
        _commit(out, f"c{i}")
        assert _gates(out).returncode == 0
        seen |= {e["outcome"] for e in _events(out) if e["gate"] == "bad"}
    assert {e["outcome"] for e in _events(out) if e["gate"] == "ok"} == {"off"}
    assert seen == {"fail", "unsampled"}  # some commits sampled, some not
    # the same commit always gets the same answer
    import importlib.util
    spec = importlib.util.spec_from_file_location("gm", out / "scripts/process/gate_modes.py")
    gm = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gm)
    assert gm.sampled_in("bad", "abc", 0.5) == gm.sampled_in("bad", "abc", 0.5)
    assert gm.sampled_in("bad", None, 0.01) is True


def test_the_sentinel_restores_a_sampled_gate_that_failed_and_locks_it(render, tmp_path):
    out = _project(render, tmp_path)
    _modes(out, "weaken", "bad", "--to", "shadow", "--decision", "owner: try")
    _commit(out, "shadow")
    _gates(out)  # bad fails in shadow on a clean tree
    r = _modes(out, "sentinel")
    assert r.returncode == 0 and "restored bad" in r.stdout
    _commit(out, "restored")
    assert _gates(out).returncode == 1  # blocking again
    # locked: no new weakening until a triage is recorded
    r = _modes(out, "weaken", "bad", "--to", "shadow", "--decision", "owner: again")
    assert r.returncode == 1 and "locked" in r.stderr
    assert _modes(out, "unlock", "bad", "--triage", "flaky fixture, fixed in abc").returncode == 0
    assert _modes(out, "weaken", "bad", "--to", "shadow", "--decision", "owner: again").returncode == 0
    # the sentinel looks only at runs since the latest weakening
    assert "nothing to restore" in _modes(out, "sentinel", "--dry-run").stdout


def test_a_breached_guardrail_rolls_back_every_active_weakening_newest_first(render, tmp_path):
    out = _project(render, tmp_path)
    (out / "docs/process/optimization.local.json").write_text(json.dumps({"guardrails": {
        "limits": [{"name": "escapes", "metric": "regressions", "max": 0, "window_days": 30}]}}),
        encoding="utf-8")
    _modes(out, "weaken", "ok", "--to", "off", "--decision", "owner: one")
    _modes(out, "weaken", "bad", "--to", "off", "--decision", "owner: two", "--guardrail", "escapes")
    _commit(out, "two weakenings")
    assert "nothing to restore" in _modes(out, "sentinel").stdout  # no regression yet
    (out / "fix.txt").write_text("x", encoding="utf-8")
    _commit(out, "fix: crash\n\nRegression-of: #12")
    r = _modes(out, "sentinel")
    restored = [ln for ln in r.stdout.splitlines() if ln.startswith("gate-modes: restored")]
    assert [ln.split()[2] for ln in restored] == ["bad", "ok"]  # newest first
    assert all("guardrail escapes" in ln for ln in restored)
    rows = [json.loads(ln) for ln in (out / ".process-work/gate-changes.jsonl").read_text().splitlines()]
    assert all(r["lock"] for r in rows if r["action"] == "restore")
    assert "every gate blocks" not in _modes(out, "status").stdout


def test_a_branch_cannot_weaken_a_gate_for_its_own_push(render, tmp_path):
    out = _project(render, tmp_path)
    subprocess.run(["git", "checkout", "-qb", "sneaky"], cwd=out, check=True)
    _modes(out, "weaken", "bad", "--to", "off", "--decision", "owner: (written by the branch)")
    _commit(out, "weaken on the branch")
    g = _gates(out)
    assert g.returncode == 1 and "takes effect once" in g.stdout
    # once the record is on main, it counts
    subprocess.run(["git", "checkout", "-q", "main"], cwd=out, check=True)
    subprocess.run(["git", "merge", "-q", "--ff-only", "sneaky"], cwd=out, check=True)
    assert _gates(out).returncode == 0
    # a restore counts at once, even before it is committed
    _modes(out, "restore", "bad", "--reason", "back to block")
    assert _gates(out).returncode == 1
