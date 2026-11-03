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


@pytest.mark.parametrize("core", ["review", "kernel", "decision-records"])
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


def _committed(out: Path) -> None:
    for args in (["config", "user.email", "t@t"], ["config", "user.name", "t"],
                 ["config", "commit.gpgsign", "false"], ["add", "-A"], ["commit", "-qm", "base"],
                 ["checkout", "-qb", "feature"]):
        subprocess.run(["git", *args], cwd=out, check=True, capture_output=True)


def _change(out: Path, rel: str) -> None:
    p = out / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=out, check=True)
    subprocess.run(["git", "-c", "commit.gpgsign=false", "commit", "-qm", "change"], cwd=out, check=True)


def test_a_path_triggered_gate_runs_only_when_a_path_in_flight_matches(render, tmp_path):
    """#206: a backend lint gate need not run for a docs-only push."""
    out = _project(render, tmp_path, {"lint": {"module": None, "command": ["scripts/lint.py"],
                                               "paths": ["backend/**"]}})
    _gate(out, "scripts/lint.py", 1, "lint: FAIL")
    _committed(out)
    _change(out, "docs/note.md")
    r = _run(out)
    assert r.returncode == 0 and "lint: no path in flight matches" in r.stdout, r.stdout + r.stderr
    _change(out, "backend/app/x.py")
    r = _run(out)
    assert r.returncode == 1 and "lint: FAIL" in r.stdout, r.stdout + r.stderr


def test_a_path_triggered_gate_runs_when_git_cannot_name_the_paths(render, tmp_path):
    """No integration base: the paths in flight are unknown, so the gate runs (fail closed)."""
    out = _project(render, tmp_path, {"lint": {"module": None, "command": ["scripts/lint.py"],
                                               "paths": ["backend/**"]}})
    _gate(out, "scripts/lint.py", 1, "lint: FAIL")
    _committed(out)
    subprocess.run(["git", "branch", "-D", "main"], cwd=out, check=True, capture_output=True)
    r = _run(out)
    assert r.returncode == 1 and "lint: FAIL" in r.stdout, r.stdout + r.stderr


def test_an_exec_gate_runs_its_argv_as_given(render, tmp_path):
    out = _project(render, tmp_path, {"make-lint": {"module": None, "exec": [
        sys.executable, "-c", "import sys; print('exec ran', sys.argv[1:]); sys.exit(1)", "a b"]}})
    r = _run(out)
    assert "exec ran ['a b']" in r.stdout and "FAILED gates: make-lint" in r.stdout, r.stdout + r.stderr


@pytest.mark.parametrize("bad", [
    {"x": {"module": None, "command": ["a.py"], "exec": ["make"]}},  # both
    {"x": {"module": None}},                                          # neither
    {"x": {"module": None, "exec": "make lint"}},                     # not an argv
    {"x": {"module": None, "exec": ["make"], "paths": []}},           # empty trigger
    {"x": {"module": None, "exec": ["make"], "paths": "backend/"}},
    {"x": {"module": None, "exec": ["make"], "when": ["x"]}},         # unknown key
    {"x": {"module": None, "exec": ["make"], "areas": []}},           # empty areas
    {"x": {"module": None, "exec": ["make"], "areas": "ui"}},
], ids=["both", "neither", "exec-string", "paths-empty", "paths-string", "unknown-key",
        "areas-empty", "areas-string"])
def test_a_malformed_exec_or_paths_entry_is_a_hard_failure(render, tmp_path, bad):
    out = _project(render, tmp_path, bad)
    r = _run(out)
    assert r.returncode == 1 and "gates.local.json" in r.stderr, r.stdout + r.stderr
    if "areas" in bad["x"]:  # the new key's own rule, not "unknown key"
        assert "'areas' must be a non-empty list of area names" in r.stderr, r.stderr


def test_a_file_moved_out_of_the_trigger_paths_still_runs_the_gate(render, tmp_path):
    """Review F10: git names only the new side of a rename unless asked for both."""
    out = _project(render, tmp_path, {"lint": {"module": None, "command": ["scripts/lint.py"],
                                               "paths": ["backend/**"]}})
    _gate(out, "scripts/lint.py", 1, "lint: FAIL")
    (out / "backend").mkdir()
    (out / "backend/x.py").write_text("a = 1\nb = 2\nc = 3\n", encoding="utf-8")
    _committed(out)
    subprocess.run(["git", "mv", "backend/x.py", "docs/x.py"], cwd=out, check=True)
    subprocess.run(["git", "-c", "commit.gpgsign=false", "commit", "-qm", "move"], cwd=out, check=True)
    r = _run(out)
    assert r.returncode == 1 and "lint: FAIL" in r.stdout, r.stdout + r.stderr


# --- #369: areas — local gates by the content of a change -------------------

def _areas(out: Path, areas: dict) -> None:
    (out / "docs/process/testing.local.json").write_text(json.dumps({"areas": areas}),
                                                         encoding="utf-8")


def _ui_lint(render, tmp_path, areas=None):
    out = _project(render, tmp_path, {"ui-lint": {"module": None, "command": ["scripts/ui.py"],
                                                  "areas": ["ui"]}})
    _gate(out, "scripts/ui.py", 1, "ui-lint: FAIL")
    _areas(out, areas if areas is not None else {"ui": ["frontend/**"]})
    _committed(out)
    return out


def test_an_area_gate_runs_only_when_its_area_is_in_the_change(render, tmp_path):
    out = _ui_lint(render, tmp_path)
    _change(out, "backend/app.py")
    r = _run(out)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "ui-lint: no path in flight matches areas ui" in r.stdout
    assert "1 skipped (not in this change: ui-lint)" in r.stdout
    events = [json.loads(ln) for ln in (out / ".git/process-gate-events.jsonl").read_text().splitlines()]
    skip = [e for e in events if e["gate"] == "ui-lint"][-1]
    assert skip["outcome"] == "skipped" and "areas ui" in skip["reason"]
    _change(out, "frontend/page.tsx")
    r = _run(out)
    assert r.returncode == 1 and "ui-lint: FAIL" in r.stdout, r.stdout + r.stderr


def test_an_area_named_nowhere_is_a_hard_failure(render, tmp_path):
    out = _ui_lint(render, tmp_path, areas={"ios": ["ios/**"]})
    _change(out, "backend/app.py")
    r = _run(out)
    assert r.returncode == 1 and "area 'ui' is in no" in r.stderr, r.stdout + r.stderr


def test_a_branch_introduces_an_area_and_its_gate_together(render, tmp_path):
    # the area exists only in the working tree: the gate runs and a note says why
    out = _project(render, tmp_path, None)
    _committed(out)
    (out / "docs/process/gates.local.json").write_text(json.dumps(
        {"ui-lint": {"module": None, "command": ["scripts/ui.py"], "areas": ["ui"]}}), encoding="utf-8")
    _gate(out, "scripts/ui.py", 0, "ui-lint: OK")
    _areas(out, {"ui": ["frontend/**"]})
    _change(out, "backend/app.py")
    r = _run(out)
    assert "not on the integration branch yet" in r.stdout, r.stdout + r.stderr
    assert "== running ui-lint ==" in r.stdout and r.returncode == 0


def test_a_branch_cannot_narrow_an_area_to_skip_its_gate(render, tmp_path):
    out = _ui_lint(render, tmp_path)
    _areas(out, {"ui": ["nothing/**"]})  # the branch's own narrowing
    _change(out, "frontend/page.tsx")
    r = _run(out)
    assert r.returncode == 1 and "ui-lint: FAIL" in r.stdout, r.stdout + r.stderr


def test_an_empty_area_is_a_statement_not_an_error(render, tmp_path):
    out = _ui_lint(render, tmp_path, areas={"ui": []})
    _change(out, "frontend/page.tsx")
    r = _run(out)
    assert r.returncode == 0 and "ui-lint: no path in flight matches" in r.stdout, r.stdout + r.stderr


def test_an_area_gate_runs_when_git_cannot_name_the_paths(render, tmp_path):
    out = _ui_lint(render, tmp_path)
    subprocess.run(["git", "branch", "-D", "main"], cwd=out, check=True, capture_output=True)
    r = _run(out)
    assert r.returncode == 1 and "ui-lint: FAIL" in r.stdout, r.stdout + r.stderr


def test_without_skips_the_summary_keeps_its_wording(render, tmp_path):
    out = _project(render, tmp_path, {"ok": {"module": None, "command": ["scripts/ok.py"]}})
    _gate(out, "scripts/ok.py", 0, "ok: OK")
    r = _run(out)
    assert r.returncode == 0 and "active gate(s) passed" in r.stdout and "all " in r.stdout, r.stdout


def test_an_unreadable_testing_config_fails_the_area_gate_with_its_cause_and_goes_on(render, tmp_path):
    out = _ui_lint(render, tmp_path, areas={})  # the integration branch knows no area yet
    (out / "docs/process/testing.local.json").write_text(
        json.dumps({"areas": {"ui": ["frontend/**"]}, "stacks": 5}), encoding="utf-8")
    _change(out, "backend/app.py")
    r = _run(out)
    assert r.returncode == 1 and "cannot be read here" in r.stderr and "stacks" in r.stderr, r.stderr
    assert "FAILED gates: ui-lint" in r.stdout, r.stdout  # the run finished: summary printed


def test_an_unreadable_branch_config_runs_a_gate_whose_area_it_may_have_widened(render, tmp_path):
    out = _ui_lint(render, tmp_path)  # the integration branch: ui = frontend/**
    (out / "docs/process/testing.local.json").write_text(
        json.dumps({"areas": {"ui": ["frontend/**", "web/**"]}, "stacks": 5}), encoding="utf-8")
    _change(out, "web/page.tsx")
    r = _run(out)
    assert "== running ui-lint ==" in r.stdout and "cannot be read" in r.stdout, r.stdout + r.stderr
