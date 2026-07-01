import hashlib
import json
import subprocess
import sys
from pathlib import Path

KENNI = ["Kenni", "KenniNext", "Seb", "Signal", "SvelteKit", "user_id=1", "surface:ios"]


def _render(render, tmp_path, **mods):
    m = {"git_hooks": True}
    m.update(mods)
    return render(tmp_path, {"project_name": "d", "modules": m})


def _runner(out: Path, *args):
    return subprocess.run(
        [sys.executable, str(out / "scripts/process/gate_runner.py"), *args],
        cwd=out, capture_output=True, text=True,
    )


def _failing_contract(out: Path):
    """Enable a hard-failing active gate: a contracts-drift pin/artifact mismatch."""
    (out / "contracts").mkdir(parents=True, exist_ok=True)
    (out / "contracts/api.json").write_bytes(b"NEW-bytes-edited")
    reg = out / "docs/process/contracts"
    reg.mkdir(parents=True, exist_ok=True)
    (reg / "orders-api.json").write_text(json.dumps({
        "id": "orders-api", "kind": "rest",
        "artifact": "contracts/api.json",
        "pin": "sha256:" + hashlib.sha256(b"OLD-bytes").hexdigest(),
    }))


def test_warn_mode_reports_but_exits_zero(render, tmp_path):
    out = _render(render, tmp_path, contracts_drift=True)
    _failing_contract(out)
    r = _runner(out, "--warn")
    assert r.returncode == 0, r.stdout
    assert "not blocking" in r.stdout
    assert "contracts-drift" in r.stdout


def test_without_warn_hard_fails(render, tmp_path):
    out = _render(render, tmp_path, contracts_drift=True)
    _failing_contract(out)
    r = _runner(out)
    assert r.returncode == 1
    assert "FAILED gates" in r.stdout


def test_list_unaffected(render, tmp_path):
    out = _render(render, tmp_path, contracts_drift=True)
    r = _runner(out, "--list")
    assert r.returncode == 0, r.stderr
    assert "contracts-drift" in r.stdout
    assert "not blocking" not in r.stdout


def test_answers_records_git_hooks(render, tmp_path):
    out = _render(render, tmp_path)
    assert "git_hooks: true" in (out / ".copier-answers.yml").read_text()
