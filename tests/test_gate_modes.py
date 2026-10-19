"""v2.68 P2: a gate's mode comes from the change record alone; weakening needs an
owner line, never touches a core or protected gate and counts only once it is
on the remote integration branch; the sentinel only ever restores, and a
restored gate stays locked until triaged
(docs/analysis/2026-10-12-closed-loop-plan.md, §6)."""
import json
import os
import subprocess
import sys
from pathlib import Path

_PASS = "import sys; sys.exit(0)\n"
_FAIL = "import sys; print('nope'); sys.exit(1)\n"


def _git(out: Path, *a: str) -> None:
    subprocess.run(["git", *a], cwd=out, check=True, capture_output=True)


def _project(render, tmp_path: Path, *, remote: bool = True) -> Path:
    out = render(tmp_path / "p", {"project_name": "d", "modules": {"telemetry": True}})
    _git(out, "init", "-q", "-b", "main")
    _git(out, "config", "user.email", "t@t")
    _git(out, "config", "user.name", "t")
    for name, code in (("ok", _PASS), ("bad", _FAIL)):
        (out / f"scripts/{name}_gate.py").write_text(code, encoding="utf-8")
    (out / "docs/process/gates.local.json").write_text(json.dumps({
        "ok": {"module": None, "command": ["scripts/ok_gate.py"]},
        "bad": {"module": None, "command": ["scripts/bad_gate.py"]},
    }), encoding="utf-8")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "init")
    if remote:
        subprocess.run(["git", "init", "-q", "--bare", str(tmp_path / "origin.git")], check=True)
        _git(out, "remote", "add", "origin", str(tmp_path / "origin.git"))
        _git(out, "push", "-q", "-u", "origin", "main")
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
    _git(out, "add", "-A")
    _git(out, "commit", "-qm", msg)


def _land(out: Path, msg: str = "land") -> None:
    """Commit and push main: what is on origin/main is what the base says."""
    _commit(out, msg)
    _git(out, "push", "-q", "origin", "main")


def _events(out: Path) -> list[dict]:
    return [json.loads(ln) for ln in (out / ".git/process-gate-events.jsonl").read_text().splitlines()]


def _changes(out: Path, *rows: dict) -> None:
    (out / ".process-work").mkdir(exist_ok=True)
    (out / "docs/process/gate-changes.local.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def test_a_shadow_gate_runs_and_records_but_does_not_block(render, tmp_path):
    out = _project(render, tmp_path)
    assert _gates(out).returncode == 1  # `bad` blocks by default
    r = _modes(out, "weaken", "bad", "--to", "shadow", "--decision", "owner 2026-10-12: watch it first")
    assert r.returncode == 0, r.stderr
    _land(out, "shadow bad")
    g = _gates(out)
    assert g.returncode == 0, g.stdout + g.stderr
    assert "bad failed in shadow mode" in g.stderr
    last = [e for e in _events(out) if e["gate"] == "bad"][-1]
    assert last["mode"] == "shadow" and last["outcome"] == "fail"
    # nodes counts the shadow failure as what it would have stopped, not as a block
    import importlib.util
    sys.path.insert(0, str(out / "scripts/process"))
    spec = importlib.util.spec_from_file_location("kpis_modes", out / "scripts/process/process_kpis.py")
    kpis = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(kpis)
    nd = {n["gate"]: n for n in kpis.nodes_table(out)["nodes"]}
    assert nd["bad"]["would_block"]["inputs"] == 1
    assert nd["bad"]["blocks"]["inputs"] == 1  # the first run, before the weakening, did block


def test_weakening_needs_an_owner_line_and_never_touches_a_core_gate(render, tmp_path):
    out = _project(render, tmp_path)
    r = _modes(out, "weaken", "bad", "--to", "off", "--decision", "steward: it is slow")
    assert r.returncode == 1 and "owner decision" in r.stderr
    r = _modes(out, "weaken", "review", "--to", "off", "--decision", "owner: trust me")
    assert r.returncode == 1 and "core gate" in r.stderr
    r = _modes(out, "weaken", "bad", "--to", "sampled", "--rate", "1.5", "--decision", "owner: x")
    assert r.returncode == 1 and "rate" in r.stderr
    r = _modes(out, "weaken", "bad", "--to", "off", "--decision", "owner: x", "--guardrail", "escape")
    assert r.returncode == 1 and "no guardrail named escape" in r.stderr  # a typo must not opt out
    (out / "docs/process/optimization.local.json").write_text(
        json.dumps({"guardrails": {"protected": ["bad"]}}), encoding="utf-8")
    r = _modes(out, "weaken", "bad", "--to", "off", "--decision", "owner: x")
    assert r.returncode == 1 and "protected" in r.stderr
    assert not (out / "docs/process/gate-changes.local.jsonl").exists()


def test_a_hand_written_record_that_breaks_a_rule_leaves_the_gate_blocking(render, tmp_path):
    out = _project(render, tmp_path)
    ts = "2026-10-12T10:00:00+00:00"
    _changes(out,
             {"gate": "review", "action": "weaken", "to": "off", "decision": "owner: x", "ts": ts},
             {"gate": "bad", "action": "weaken", "to": "off", "decision": "agent: x", "ts": ts},
             {"gate": "ok", "action": "weaken", "to": "shadow", "decision": "owner: x",
              "ts": "2026-10-12T10:00:00"},  # naive: no timestamp
             {"gate": "ok", "action": "weaken", "to": "shadow", "decision": "owner: x", "ts": ts,
              "guardrails": 3},
             {"gate": "bad", "action": "unlock"})
    with (out / "docs/process/gate-changes.local.jsonl").open("a") as fh:
        fh.write("garbage\n")
    _land(out)
    g = _gates(out)
    assert g.returncode == 1 and "bad" in g.stdout.split("FAILED gates:")[-1]
    for why in ("a core gate cannot be weakened", "owner decision", "timezone-aware",
                "'guardrails' must be a list", "an unlock needs a triage", "not JSON"):
        assert why in g.stdout, why
    assert _modes(out, "check").returncode == 1
    assert _modes(out, "sentinel").returncode == 0  # bad lines never stop the sentinel


def test_off_skips_and_sampled_runs_on_a_stable_share_of_commits(render, tmp_path):
    out = _project(render, tmp_path)
    _modes(out, "weaken", "ok", "--to", "off", "--decision", "owner: replaced by X")
    _modes(out, "weaken", "bad", "--to", "sampled", "--rate", "0.5", "--decision", "owner: sample it")
    _land(out, "modes")
    seen = set()
    # sampling follows the commit hash, which follows the clock: eight commits saw only one
    # outcome once in 128 runs (CI on v2.75.0) — commit on until both showed, 40 at most
    for i in range(40):
        (out / f"f{i}.txt").write_text(str(i), encoding="utf-8")
        _commit(out, f"c{i}")
        assert _gates(out).returncode == 0
        seen |= {e["outcome"] for e in _events(out) if e["gate"] == "bad"}
        if i >= 3 and seen == {"fail", "unsampled"}:
            break
    assert {e["outcome"] for e in _events(out) if e["gate"] == "ok"} == {"off"}
    assert seen == {"fail", "unsampled"}  # some commits sampled, some not
    import importlib.util
    spec = importlib.util.spec_from_file_location("gm", out / "scripts/process/gate_modes.py")
    gm = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gm)
    assert gm.sampled_in("bad", "abc", 0.5) == gm.sampled_in("bad", "abc", 0.5)
    assert gm.sampled_in("bad", None, 0.01) is True


def test_the_sentinel_restores_a_failed_weak_gate_at_once_and_locks_it(render, tmp_path):
    out = _project(render, tmp_path)
    _modes(out, "weaken", "bad", "--to", "shadow", "--decision", "owner: try")
    _land(out, "shadow")
    _gates(out)  # bad fails in shadow on a clean tree
    r = _modes(out, "sentinel")
    assert r.returncode == 0 and "restored bad" in r.stdout
    assert _gates(out).returncode == 1  # the restore counts here before it is committed
    _land(out, "restored")
    r = _modes(out, "weaken", "bad", "--to", "shadow", "--decision", "owner: again")
    assert r.returncode == 1 and "locked" in r.stderr
    assert _modes(out, "unlock", "bad", "--triage", "flaky fixture, fixed in abc").returncode == 0
    assert _modes(out, "weaken", "bad", "--to", "shadow", "--decision", "owner: again").returncode == 0
    _land(out, "again")
    # the old failure lies before the new weakening: nothing to restore
    assert "nothing to restore" in _modes(out, "sentinel", "--dry-run").stdout


def test_the_sentinel_ignores_dirty_runs(render, tmp_path):
    out = _project(render, tmp_path)
    _modes(out, "weaken", "bad", "--to", "shadow", "--decision", "owner: try")
    _land(out, "shadow")
    (out / "stray.txt").write_text("x", encoding="utf-8")
    _gates(out)  # fails, but on a tree no commit names
    assert {e["dirty"] for e in _events(out) if e["gate"] == "bad"} == {True}
    assert "nothing to restore" in _modes(out, "sentinel", "--dry-run").stdout


def test_a_breached_guardrail_rolls_back_every_active_weakening_newest_first(render, tmp_path):
    out = _project(render, tmp_path)
    (out / "docs/process/optimization.local.json").write_text(json.dumps({"guardrails": {
        "limits": [{"name": "escapes", "metric": "regressions", "max": 0, "window_days": 30}]}}),
        encoding="utf-8")
    _modes(out, "weaken", "ok", "--to", "off", "--decision", "owner: one")
    _modes(out, "weaken", "bad", "--to", "off", "--decision", "owner: two", "--guardrail", "escapes")
    _land(out, "two weakenings")
    assert "nothing to restore" in _modes(out, "sentinel").stdout  # no regression yet
    (out / "fix.txt").write_text("x", encoding="utf-8")
    _land(out, "fix: crash\n\nRegression-of: #12")
    r = _modes(out, "sentinel")
    restored = [ln for ln in r.stdout.splitlines() if ln.startswith("gate-modes: restored")]
    assert [ln.split()[2] for ln in restored] == ["bad", "ok"]  # newest first
    assert all("guardrail escapes" in ln for ln in restored)
    rows = [json.loads(ln) for ln in (out / "docs/process/gate-changes.local.jsonl").read_text().splitlines()]
    assert all(r["lock"] for r in rows if r["action"] == "restore")


def test_a_branch_cannot_weaken_a_gate_for_its_own_push(render, tmp_path):
    out = _project(render, tmp_path)
    _git(out, "checkout", "-qb", "sneaky")
    _modes(out, "weaken", "bad", "--to", "off", "--decision", "owner: (written by the branch)")
    _commit(out, "weaken on the branch")
    g = _gates(out)
    assert g.returncode == 1 and "takes effect once" in g.stdout
    # merged into local main but not yet pushed: still not on the base
    _git(out, "checkout", "-q", "main")
    _git(out, "merge", "-q", "--ff-only", "sneaky")
    assert _gates(out).returncode == 1
    _git(out, "push", "-q", "origin", "main")
    assert _gates(out).returncode == 0
    _modes(out, "restore", "bad", "--reason", "back to block")
    assert _gates(out).returncode == 1  # a restore counts at once, uncommitted


def test_without_a_remote_no_weakening_counts(render, tmp_path):
    out = _project(render, tmp_path, remote=False)
    _modes(out, "weaken", "bad", "--to", "off", "--decision", "owner: x")
    _commit(out, "weaken on main, no remote")
    g = _gates(out)
    assert g.returncode == 1 and "takes effect once" in g.stdout


def test_a_branch_cannot_unprotect_a_gate_in_its_own_mandate(render, tmp_path):
    out = _project(render, tmp_path)
    _modes(out, "weaken", "bad", "--to", "off", "--decision", "owner: for now")
    _land(out, "weaken")
    assert _gates(out).returncode == 0
    (out / "docs/process/optimization.local.json").write_text(
        json.dumps({"guardrails": {"protected": ["bad"]}}), encoding="utf-8")
    _land(out, "owner protects bad")
    assert _gates(out).returncode == 1
    _git(out, "checkout", "-qb", "unprotect")
    (out / "docs/process/optimization.local.json").write_text(json.dumps({}), encoding="utf-8")
    _commit(out, "drop the protection on the branch")
    assert _gates(out).returncode == 1  # the base's protection still holds


def test_a_broken_gate_modes_leaves_every_gate_blocking(render, tmp_path):
    out = _project(render, tmp_path)
    _modes(out, "weaken", "bad", "--to", "off", "--decision", "owner: x")
    _land(out, "weaken")
    (out / "scripts/process/gate_modes.py").write_text("this is not python\n", encoding="utf-8")
    g = _gates(out)
    assert g.returncode == 1 and "every gate blocks" in g.stdout


def test_an_unreadable_record_file_is_named_and_the_sentinel_survives(render, tmp_path):
    out = _project(render, tmp_path)
    (out / ".process-work").mkdir(exist_ok=True)
    (out / "docs/process/gate-changes.local.jsonl").write_bytes(b"\xff\xfe not utf-8\n")
    assert "unreadable" in _modes(out, "status").stdout
    assert _modes(out, "sentinel").returncode == 0
    assert _gates(out).returncode == 1


def test_the_record_lives_where_review_looks_not_in_bookkeeping(render, tmp_path):
    out = _project(render, tmp_path, remote=False)
    import importlib.util
    sys.path.insert(0, str(out / "scripts/process"))
    for name in ("gate_modes", "check_review"):
        spec = importlib.util.spec_from_file_location(f"{name}_rec", out / f"scripts/process/{name}.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        globals()[f"_{name}"] = mod
    assert not _gate_modes.CHANGES.startswith(_check_review.BOOKKEEPING)  # noqa: F821


def test_an_observed_new_gate_keeps_its_failures_and_weakened_gates_are_named(render, tmp_path):
    out = _project(render, tmp_path)
    r = _modes(out, "weaken", "bad", "--to", "shadow", "--observe", "--decision", "owner: new check, count it first")
    assert r.returncode == 0, r.stderr
    _land(out, "observe bad")
    g = _gates(out)
    assert g.returncode == 0
    assert "1 not blocking: bad shadow" in g.stdout and "not blocking by record" in g.stderr
    assert "nothing to restore" in _modes(out, "sentinel", "--dry-run").stdout
