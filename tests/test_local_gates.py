"""Project gates without owning the runner (#130, P1): `docs/process/gates.local.json`
adds gates to the template's list, or replaces one by name. A downstream project kept
gate_runner.py in `.process-owned` only for three gates of its own; every template
release then needed a hand port."""
import json
import subprocess
import sys
from pathlib import Path

import pytest


def _project(render, tmp_path: Path, local: object | None) -> Path:
    out = render(tmp_path / "p", {"project_name": "d", "modules": {}})
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=out, check=True)
    if local is not None:
        text = local if isinstance(local, str) else json.dumps(local)
        (out / "docs/process/gates.local.json").write_text(text, encoding="utf-8")
    return out


def _gate(out: Path, rel: str, rc: int, say: str) -> None:
    p = out / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"import sys\nprint({say!r})\nsys.exit({rc})\n", encoding="utf-8")


def _run(out: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(out / "scripts/process/gate_runner.py"), *args],
                          cwd=out, capture_output=True, text=True)


def test_a_local_gate_runs_and_its_failure_fails_the_run(render, tmp_path):
    out = _project(render, tmp_path, {"owner-bypass": {"module": None,
                                                       "command": ["scripts/check_owner_bypass.py", "."]}})
    _gate(out, "scripts/check_owner_bypass.py", 1, "owner-bypass: FAIL x")

    r = _run(out)

    assert "== running owner-bypass ==" in r.stdout and "owner-bypass: FAIL x" in r.stdout
    assert r.returncode == 1 and "FAILED gates: owner-bypass" in r.stdout, r.stdout + r.stderr


def test_a_local_gate_is_listed(render, tmp_path):
    out = _project(render, tmp_path, {"kit-tokens": {"module": None, "command": ["scripts/k.py"]}})

    assert "kit-tokens" in _run(out, "--list").stdout.split()


def test_a_local_gate_of_an_inactive_module_does_not_run(render, tmp_path):
    out = _project(render, tmp_path, {"x": {"module": "speckit", "command": ["scripts/x.py"]}})

    assert "x" not in _run(out, "--list").stdout.split()


def test_replacing_a_template_gate_by_name_is_said(render, tmp_path):
    out = _project(render, tmp_path, {"fix-streak": {"module": None,
                                                     "command": ["scripts/my_streak.py", "."]}})
    _gate(out, "scripts/my_streak.py", 0, "mine: OK")

    r = _run(out)

    assert r.returncode == 0 and "mine: OK" in r.stdout, r.stdout + r.stderr
    assert "gates.local.json replaces the template's fix-streak gate" in r.stdout


@pytest.mark.parametrize("bad", [
    "{not json",
    [],
    {"x": {"command": ["a.py"]}},                      # no module key
    {"x": {"module": "nope", "command": ["a.py"]}},     # unknown module
    {"x": {"module": None, "command": []}},             # empty command
    {"x": {"module": None, "command": "a.py"}},         # not a list
    {"x": {"module": None, "command": ["/abs/a.py"]}},  # outside the repository
    {"x": {"module": None, "command": ["../a.py"]}},
], ids=["unparseable", "not-a-mapping", "no-module", "unknown-module", "empty",
        "string", "absolute", "parent"])
def test_a_malformed_local_file_is_a_hard_failure(render, tmp_path, bad):
    """Load-bearing like the manifest: a broken file must not read as 'no local gates'."""
    out = _project(render, tmp_path, bad)

    r = _run(out)

    assert r.returncode == 1 and "gates.local.json" in r.stderr, r.stdout + r.stderr


def test_without_a_local_file_nothing_changes(render, tmp_path):
    out = _project(render, tmp_path, None)

    r = _run(out)

    assert r.returncode == 0 and "gates.local.json" not in r.stdout + r.stderr, r.stdout + r.stderr
