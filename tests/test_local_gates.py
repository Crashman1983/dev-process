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


def _speckit_project(render, tmp_path: Path, local: object) -> Path:
    out = render(tmp_path / "p", {"project_name": "d", "modules": {"speckit": True}})
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=out, check=True)
    (out / "docs/process/gates.local.json").write_text(json.dumps(local), encoding="utf-8")
    return out


def test_replacing_a_module_gate_by_name_is_said_where_a_passing_hook_shows_it(render, tmp_path):
    """stderr: pre-commit hides a passing hook's stdout, and the replacement must be seen."""
    out = _speckit_project(render, tmp_path, {"speckit": {"module": "speckit",
                                                          "command": ["scripts/my_spec.py", "."]}})
    _gate(out, "scripts/my_spec.py", 0, "mine: OK")

    r = _run(out)

    assert r.returncode == 0 and "mine: OK" in r.stdout, r.stdout + r.stderr
    assert "gates.local.json replaces the template's speckit gate" in r.stderr


@pytest.mark.parametrize("core", ["review", "kernel", "fix-streak"])
def test_a_core_gate_cannot_be_replaced(render, tmp_path, core):
    """Refute F2: a branch's own gates.local.json replaced `review` with a script that
    exits 0 — and with it the standing block — and the push to main passed."""
    out = _project(render, tmp_path, {core: {"module": None, "command": ["scripts/ok.py"]}})
    _gate(out, "scripts/ok.py", 0, "ok")

    r = _run(out)

    assert r.returncode == 1 and f"{core} is a core gate" in r.stderr, r.stdout + r.stderr


def test_a_core_gate_cannot_be_moved_into_a_module(render, tmp_path):
    out = _project(render, tmp_path, {"review": {"module": "sbom", "command": ["scripts/ok.py"]}})

    r = _run(out, "--list")

    assert r.returncode == 1 and "review is a core gate" in r.stderr, r.stdout + r.stderr


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


def test_child_output_is_utf8_even_when_the_runners_locale_is_cp1252(render, tmp_path):
    import os
    out = _project(render, tmp_path, {'unicode': {'module': None,
                                                 'command': ['scripts/unicode_gate.py']}})
    _gate(out, 'scripts/unicode_gate.py', 0, 'unicode: €')
    result = subprocess.run(
        [sys.executable, str(out / 'scripts/process/gate_runner.py')], cwd=out,
        capture_output=True, text=True, encoding='cp1252',
        env={**os.environ, 'PYTHONIOENCODING': 'cp1252'})
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'unicode: €' in result.stdout
