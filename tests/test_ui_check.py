"""ui-check (#368, v2.84 C): a plan whose branch carries UI says how the UI was
considered; the gate checks that every axis is answered, never the answers. A
template gate in every project (`ALWAYS`), starting as `shadow --observe`
(`gate_modes.fold`), armed by `restore`."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

BLOCK = """ui-check:
- board: see Design Contract Trace
- viewports: 320, 1440
- themes: light, dark
- states: loading, empty, error, unknown
- navigation: in from the list, back to it with the selection kept
- interaction: keyboard and touch
- content extremes: an 80-char label
- accessibility: names, focus order
- rules: `docs/design/rules.md` — reused the row; no deviation
"""
TRACE = "## Design Contract Trace\n\n- C1 the list row\n"


def _env() -> dict:
    env = {k: v for k, v in os.environ.items()
           if k not in ("CI", "PRE_COMMIT_TO_REF") and not k.startswith(("PROCESS_", "GIT_"))}
    return {**env, "PYTHONDONTWRITEBYTECODE": "1", "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "commit.gpgsign", "GIT_CONFIG_VALUE_0": "false"}


def _git(out: Path, *a: str) -> str:
    return subprocess.run(["git", *a], cwd=out, check=True, capture_output=True, text=True,
                          env=_env()).stdout


def _write(out: Path, rel: str, text: str = "x\n") -> None:
    p = out / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _registry(**extra) -> str:
    return json.dumps({"surface": "web", "contract": "docs/design/web.md", "status": "draft",
                       "pin": "x", "id_prefixes": ["C"], "paths": ["web/**"], **extra})


@pytest.fixture
def project(render, tmp_path):
    """main on a bare origin with a `web` registry and `areas.ui`; `feature` checked out."""
    out = render(tmp_path / "p", {"project_name": "d", "modules": {"design_contracts": True,
                                                                  "speckit": True}})
    _write(out, "docs/process/design-contracts/web.json", _registry())
    _write(out, "docs/process/testing.local.json", json.dumps({"areas": {"ui": ["app/ui/**"]}}))
    _write(out, "docs/design/rules.md", "# rules\n")
    _write(out, "server/api.py")
    _git(out, "init", "-q", "-b", "main")
    _git(out, "config", "user.email", "t@t")
    _git(out, "config", "user.name", "t")
    _git(out, "add", "-A")
    _git(out, "commit", "-qm", "base")
    subprocess.run(["git", "init", "-q", "--bare", str(tmp_path / "origin.git")], check=True)
    _git(out, "remote", "add", "origin", str(tmp_path / "origin.git"))
    _git(out, "push", "-q", "-u", "origin", "main")
    _git(out, "checkout", "-q", "-b", "feature")
    return out


def _plan(out: Path, body: str, name: str = "2026-11-03-x.md", tier: int = 2) -> str:
    rel = f".process-work/plans/{name}"
    _write(out, rel, f"# Plan\n\ntier: {tier}\nissue: #1\n\n{body}\n")
    return rel


def _commit(out: Path, *paths: str) -> None:
    for rel in paths:
        _write(out, rel)
    _git(out, "add", "-A")
    _git(out, "commit", "-qm", "work")


def _check(out: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "scripts/process/check_ui.py", "."], cwd=out,
                          capture_output=True, text=True, env=_env())


def _modes(out: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "scripts/process/gate_modes.py", *args], cwd=out,
                          capture_output=True, text=True, env=_env())


# --- who owes the block ---------------------------------------------------------

def test_a_plan_declaring_a_contract_owes_the_block(project):
    out = project
    _plan(out, "design-contract: web\n\n" + TRACE)
    _commit(out)
    r = _check(out)
    assert r.returncode == 1 and "no `ui-check:` block — it declares web" in r.stdout, r.stdout
    _plan(out, "design-contract: web\n\n" + TRACE + "\n" + BLOCK)
    _commit(out)
    r = _check(out)
    assert r.returncode == 0, r.stdout


def test_ui_in_the_branch_makes_every_bound_plan_answer_or_opt_out(project):
    out = project
    rel = _plan(out, "design-contract: n/a — backend only")
    _commit(out, "app/ui/view.tsx")
    r = _check(out)
    assert r.returncode == 1 and "the branch changes UI paths" in r.stdout, r.stdout
    _plan(out, "design-contract: n/a — backend only\n\nui-check: n/a — carries the label rename only")
    _commit(out)
    assert _check(out).returncode == 0
    # a plan that declares a contract cannot opt out
    _plan(out, "design-contract: web\n\n" + TRACE + "\nui-check: n/a — not really")
    _commit(out)
    r = _check(out)
    assert r.returncode == 1 and "a contract's UI is never only carried along" in r.stdout, r.stdout
    assert rel


def test_a_backend_branch_owes_nothing(project):
    out = project
    _plan(out, "design-contract: n/a — backend only")
    _commit(out, "server/api.py")
    r = _check(out)
    assert r.returncode == 0 and "FAILED" not in r.stdout, r.stdout


@pytest.mark.parametrize("line, finding", [
    ("- viewports:", "`viewports` is empty"),
    ("- colours: red", "unknown ui-check axis `colours`"),
    ("- themes: again", "`themes` twice"),
    ("- viewports: inherited", "`viewports: inherited`, but no registry names a default"),
])
def test_each_axis_is_answered_once_and_known(project, line, finding):
    out = project
    block = BLOCK.replace("- viewports: 320, 1440\n", "") if "viewports" in line else BLOCK
    block = block.rstrip("\n") + "\n" + line + "\n"
    _plan(out, "design-contract: web\n\n" + TRACE + "\n" + block)
    _commit(out)
    r = _check(out)
    assert r.returncode == 1 and finding in r.stdout, r.stdout


def test_a_missing_axis_is_named(project):
    out = project
    _plan(out, "design-contract: web\n\n" + TRACE + "\n" + BLOCK.replace("- states: loading, empty, error, unknown\n", ""))
    _commit(out)
    r = _check(out)
    assert r.returncode == 1 and "ui-check has no `states` line" in r.stdout, r.stdout


def test_rules_name_an_existing_file_and_a_declared_source(project):
    out = project
    _plan(out, "design-contract: web\n\n" + TRACE + "\n" + BLOCK.replace("`docs/design/rules.md`", "`docs/nope.md`"))
    _commit(out)
    assert "`rules` names no existing file" in _check(out).stdout
    _plan(out, "design-contract: web\n\n" + TRACE + "\n" + BLOCK.replace(
        "- rules: `docs/design/rules.md` — reused the row; no deviation", "- rules: inherited"))
    _commit(out)
    assert "`rules` cannot be inherited" in _check(out).stdout
    # with rule_sources, rules must cite one of them, and n/a is a finding
    _write(out, "docs/design/ui-handwerk.md")
    _write(out, "docs/process/design-contracts/web.json",
           _registry(rule_sources=["docs/design/ui-handwerk.md"], defaults={"viewports": "320, 1440"}))
    _plan(out, "design-contract: web\n\n" + TRACE + "\n" + BLOCK)
    _commit(out)
    assert "cites none of the project's rule sources" in _check(out).stdout
    _plan(out, "design-contract: web\n\n" + TRACE + "\n" + BLOCK.replace(
        "- rules: `docs/design/rules.md` — reused the row; no deviation", "- rules: n/a — none apply"))
    _commit(out)
    assert "`rules: n/a`, but the project names its UI rules" in _check(out).stdout
    good = BLOCK.replace("`docs/design/rules.md`", "`docs/design/ui-handwerk.md`").replace(
        "- viewports: 320, 1440", "- viewports: inherited")
    _plan(out, "design-contract: web\n\n" + TRACE + "\n" + good)
    _commit(out)
    r = _check(out)
    assert r.returncode == 0, r.stdout


def test_a_block_in_a_fence_or_a_comment_counts_for_nothing(project):
    out = project
    for wrapped in (f"```\n{BLOCK}```\n", f"<!--\n{BLOCK}-->\n"):
        _plan(out, "design-contract: web\n\n" + TRACE + "\n" + wrapped)
        _commit(out)
        r = _check(out)
        assert r.returncode == 1 and "no `ui-check:` block" in r.stdout, (wrapped, r.stdout)


def test_ui_is_known_from_areas_or_registry_paths_and_nothing_declared_is_a_note(project):
    out = project
    _plan(out, "design-contract: n/a — backend only")
    _commit(out, "web/page.tsx")  # registry paths alone
    assert "the branch changes UI paths" in _check(out).stdout
    # nothing declared anywhere: a note, and no finding
    _git(out, "rm", "-q", "docs/process/design-contracts/web.json", "docs/process/testing.local.json")
    _git(out, "commit", "-qm", "undeclare")
    _git(out, "push", "-q", "origin", "HEAD:main")
    _plan(out, "design-contract: n/a — backend only", name="2026-11-04-next.md")
    _commit(out, "web/page.tsx")
    r = _check(out)
    assert r.returncode == 0 and "no UI paths declared" in r.stdout, r.stdout
    _write(out, "docs/process/testing.local.json", json.dumps({"areas": {"ui": []}}))
    _commit(out)
    r = _check(out)
    assert r.returncode == 0 and "no UI paths declared" not in r.stdout, r.stdout


def test_spec_kit_and_archived_plans_are_bound_old_ones_are_not(project):
    out = project
    _write(out, ".process-work/plans/2026-01-01-old.md", "# old\n\ntier: 2\nissue: #2\n\ndesign-contract: web\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-qm", "old plan")
    _git(out, "push", "-q", "origin", "HEAD:main")
    _git(out, "commit", "-q", "--allow-empty", "-m", "tip")
    assert _check(out).returncode == 0  # at the ref already: history
    _write(out, "specs/007-x/plan.md", "# Plan\n\ntier: 2\nissue: #3\n\ndesign-contract: web\n\n" + TRACE)
    _write(out, ".process-work/plans/archive/2026-11-02-y.md", "# y\n\ntier: 2\nissue: #4\n\ndesign-contract: web\n")
    _commit(out)
    r = _check(out)
    assert "specs/007-x/plan.md: no `ui-check:` block" in r.stdout, r.stdout
    assert "archive/2026-11-02-y.md: no `ui-check:` block" in r.stdout, r.stdout


def test_two_surfaces_need_two_blocks(project):
    out = project
    _write(out, "docs/process/design-contracts/ios.json", json.dumps(
        {"surface": "ios", "contract": "docs/design/ios.md", "status": "draft", "pin": "x",
         "id_prefixes": ["I"], "paths": ["ios/**"]}))
    _plan(out, "design-contract: web\ndesign-contract: ios\n\n" + TRACE + "\n" + BLOCK.replace("ui-check:", "ui-check web:"))
    _commit(out)
    r = _check(out)
    assert r.returncode == 1 and "declares ios but has no `ui-check ios:` block" in r.stdout, r.stdout


# --- mode: observing by default, armed by restore -----------------------------------

def test_ui_check_runs_without_a_module_key_and_observes_by_default(project):
    out = project
    r = subprocess.run([sys.executable, "scripts/process/gate_runner.py", "--list"], cwd=out,
                       capture_output=True, text=True, env=_env())
    assert "ui-check" in r.stdout.split(), r.stdout
    r = _modes(out, "status")
    assert "ui-check" in r.stdout and "shadow" in r.stdout and "template-default" in r.stdout, r.stdout


def test_a_project_gate_named_ui_check_keeps_its_mode(project):
    out = project
    _write(out, "scripts/own.py", "import sys; sys.exit(0)\n")
    _write(out, "docs/process/gates.local.json", json.dumps({"ui-check": {"module": None, "command": ["scripts/own.py"]}}))
    _commit(out)
    r = _modes(out, "status")
    assert "ui-check" not in r.stdout, r.stdout  # no record, no default: it blocks


def test_dropping_a_local_ui_check_needs_a_record(project):
    out = project
    _write(out, "scripts/own.py", "import sys; sys.exit(0)\n")
    _write(out, "docs/process/gates.local.json", json.dumps({"ui-check": {"module": None, "command": ["scripts/own.py"]}}))
    _commit(out)
    _git(out, "push", "-q", "origin", "HEAD:main")
    _write(out, "docs/process/gates.local.json", "{}")
    _commit(out)
    r = _modes(out, "check")
    assert r.returncode == 1 and "record the handover" in r.stdout, r.stdout
    assert _modes(out, "restore", "ui-check", "--reason", "keep it blocking").returncode == 0
    r = _modes(out, "check")
    assert r.returncode == 0 and "handover" not in r.stdout, r.stdout
    assert "ui-check" in _modes(out, "status").stdout and "block" in _modes(out, "status").stdout


def test_the_sentinel_leaves_observed_gates_alone_on_a_breached_guardrail(project):
    out = project
    _write(out, "scripts/bad.py", "import sys; sys.exit(1)\n")
    _write(out, "docs/process/gates.local.json", json.dumps({
        "bad": {"module": None, "command": ["scripts/bad.py"]},
        "new": {"module": None, "command": ["scripts/bad.py"]}}))
    _write(out, "docs/process/optimization.local.json", json.dumps({"guardrails": {
        "limits": [{"name": "escapes", "metric": "regressions", "max": 0, "window_days": 30}]}}))
    _commit(out)
    _modes(out, "weaken", "bad", "--to", "off", "--decision", "owner: one")
    _modes(out, "weaken", "new", "--to", "shadow", "--observe", "--decision", "owner: count it first")
    _git(out, "add", "-A")
    _git(out, "commit", "-qm", "fix: crash\n\nRegression-of: #12")
    _git(out, "push", "-q", "origin", "HEAD:main")
    r = _modes(out, "sentinel")
    restored = [ln.split()[2] for ln in r.stdout.splitlines() if ln.startswith("gate-modes: restored")]
    assert restored == ["bad"], r.stdout  # ui-check (template default) and `new` keep observing


def test_after_restore_a_finding_blocks(project):
    out = project
    _plan(out, "design-contract: web\n\n" + TRACE)
    _commit(out)
    r = subprocess.run([sys.executable, "scripts/process/gate_runner.py"], cwd=out,
                       capture_output=True, text=True, env=_env())
    assert "ui-check failed in shadow mode" in r.stderr and "restore ui-check` arms it" in r.stderr, r.stderr
    assert "ui-check" not in r.stdout.split("FAILED gates:")[-1] if "FAILED gates:" in r.stdout else True
    _modes(out, "restore", "ui-check", "--reason", "armed")
    r = subprocess.run([sys.executable, "scripts/process/gate_runner.py"], cwd=out,
                       capture_output=True, text=True, env=_env())
    assert r.returncode == 1 and "ui-check" in r.stdout.split("FAILED gates:")[-1], r.stdout


# --- visibility ------------------------------------------------------------------------

def test_the_bundle_and_digest_show_the_block_and_every_opt_out(project):
    out = project
    code = ("import sys; sys.path.insert(0, 'scripts/process'); import check_ui; from pathlib import Path; "
            "print('\\n'.join(check_ui.summary(Path('.'), {"
            "'a.md': open(sys.argv[1]).read(), 'b.md': open(sys.argv[2]).read()})))")
    a = _plan(out, "design-contract: web\n\n" + TRACE + "\n" + BLOCK, name="a.md")
    b = _plan(out, "ui-check: n/a — only the label", name="b.md")
    r = subprocess.run([sys.executable, "-c", code, a, b], cwd=out, capture_output=True, text=True, env=_env())
    assert "`a.md` ui-check: 9 axes, 0 n/a, 0 inherited; rules: `docs/design/rules.md`" in r.stdout, r.stdout + r.stderr
    assert "ui-check **n/a** — only the label" in r.stdout, r.stdout


# --- refute v2.84 ------------------------------------------------------------------

def test_wrapped_axis_lines_continue_the_axis(project):
    out = project
    wrapped = BLOCK.replace("- navigation: in from the list, back to it with the selection kept",
                            "- navigation: in from the list,\n  back to it with the selection kept: and\n  the filter")
    wrapped = wrapped.replace("- rules: `docs/design/rules.md` — reused the row; no deviation",
                              "- rules: `docs/design/rules.md:12` — reused the row;\n  no deviation")
    _plan(out, "design-contract: web\n\n" + TRACE + "\n" + wrapped)
    _commit(out)
    r = _check(out)
    assert r.returncode == 0, r.stdout


def test_a_header_then_a_blank_line_then_the_list_is_one_block(project):
    out = project
    _plan(out, "design-contract: web\n\n" + TRACE + "\n" + BLOCK.replace("ui-check:\n", "**ui-check:**\n\n"))
    _commit(out)
    assert _check(out).returncode == 0


def test_a_header_with_no_axes_is_named_at_its_own_line(project):
    out = project
    rel = _plan(out, "design-contract: web\n\n" + TRACE + "\nui-check:\n\nsome prose\n")
    _commit(out)
    r = _check(out)
    line = (out / rel).read_text().splitlines().index("ui-check:") + 1
    assert f"{rel}:{line}: `ui-check:` with no axis line" in r.stdout, r.stdout


def test_a_commented_skeleton_or_fenced_example_does_not_disturb_the_real_block(project):
    out = project
    for before in (f"<!--\n{BLOCK}-->\n\n", f"```\n{BLOCK}```\n\n", "<!-- inline --> note\n\n"):
        _plan(out, "design-contract: web\n\n" + TRACE + "\n" + before + BLOCK)
        _commit(out)
        r = _check(out)
        assert r.returncode == 0, (before, r.stdout)


def test_a_block_in_indented_code_counts_for_nothing(project):
    out = project
    indented = "\n".join("    " + ln for ln in BLOCK.splitlines())
    _plan(out, "design-contract: web\n\n" + TRACE + "\nAn example:\n\n" + indented + "\n")
    _commit(out)
    r = _check(out)
    assert "no `ui-check:` block" in r.stdout, r.stdout


@pytest.mark.parametrize("cite, ok", [
    ("`docs/design/rules.md:12`", True),
    ("`docs/design/rules.md#reuse`", True),
    ("[UI rules](docs/design/rules.md)", True),
    ("`/etc/hostname`", False),
    ("`../../../../../../etc/hostname`", False),
])
def test_rules_accept_the_usual_citations_and_nothing_outside_the_repository(project, cite, ok):
    out = project
    _plan(out, "design-contract: web\n\n" + TRACE + "\n" + BLOCK.replace("`docs/design/rules.md`", cite))
    _commit(out)
    r = _check(out)
    assert (r.returncode == 0) is ok, (cite, r.stdout)


def test_one_contract_answered_in_another_surfaces_block_is_a_finding(project):
    out = project
    _plan(out, "design-contract: web\n\n" + TRACE + "\n" + BLOCK.replace("ui-check:", "ui-check ios:"))
    _commit(out)
    r = _check(out)
    assert "declares web but has no `ui-check web:` block" in r.stdout, r.stdout


def test_observe_is_refused_for_a_gate_that_blocked(project):
    out = project
    # a template gate blocked from its first run
    r = _modes(out, "weaken", "design-contracts", "--to", "shadow",
               "--observe", "--decision", "owner: try")
    assert r.returncode == 1 and "never blocked" in r.stderr, r.stderr
    # ui-check, once restored, has blocked: observing again is refused
    assert _modes(out, "restore", "ui-check", "--reason", "armed").returncode == 0
    r = _modes(out, "weaken", "ui-check", "--to", "shadow", "--observe", "--decision", "owner: back")
    assert r.returncode == 1 and "never blocked" in r.stderr, r.stderr


def test_a_local_gate_main_added_after_the_fork_is_no_handover(project):
    out = project
    _git(out, "checkout", "-q", "-b", "later", "main")
    _write(out, "scripts/own.py", "import sys; sys.exit(0)\n")
    _write(out, "docs/process/gates.local.json", json.dumps({"ui-check": {"module": None, "command": ["scripts/own.py"]}}))
    _commit(out)
    _git(out, "push", "-q", "origin", "HEAD:main")
    _git(out, "checkout", "-q", "feature")
    r = _modes(out, "check")
    assert "handover" not in r.stdout, r.stdout


def test_a_local_gate_only_on_the_ref_keeps_the_default_off(project):
    out = project
    _write(out, "scripts/own.py", "import sys; sys.exit(0)\n")
    _write(out, "docs/process/gates.local.json", json.dumps({"ui-check": {"module": None, "command": ["scripts/own.py"]}}))
    _commit(out)
    _git(out, "push", "-q", "origin", "HEAD:main")
    _write(out, "docs/process/gates.local.json", "{}")
    _commit(out)
    assert "template-default" not in _modes(out, "status").stdout


def test_always_is_no_module_name(project):
    out = project
    code = ("import sys; sys.path.insert(0, 'scripts/process'); import gate_runner; "
            "print('always' in gate_runner.KNOWN_MODULES)")
    r = subprocess.run([sys.executable, "-c", code], cwd=out, capture_output=True, text=True, env=_env())
    assert r.stdout.strip() == "False", r.stdout + r.stderr


def test_the_bundle_keeps_the_d8_hint_beside_a_ui_check_opt_out(project):
    out = project
    (out / "docs/process/design-contracts/web.json").unlink()  # no contract: the bare D8 case
    rel = _plan(out, "ui-check: n/a — only the label")
    code = ("import sys; sys.path.insert(0, 'scripts/process'); import make_review_bundle as m; "
            "from pathlib import Path; print(m._ui_evidence(Path('.'), None, [Path(sys.argv[1])]))")
    r = subprocess.run([sys.executable, "-c", code, rel], cwd=out, capture_output=True, text=True, env=_env())
    assert "no screenshots" in r.stdout and "ui-check **n/a** — only the label" in r.stdout, r.stdout + r.stderr


def test_a_project_axis_with_a_hyphen_is_read(project):
    out = project
    _write(out, "docs/process/design-contracts/web.json", _registry(extra_axes=["dark-mode"]))
    _plan(out, "design-contract: web\n\n" + TRACE + "\n" + BLOCK.replace(
        "- themes: light, dark\n", "- themes: light, dark\n- dark-mode: contrast checked\n"))
    _commit(out)
    r = _check(out)
    assert r.returncode == 0, r.stdout
