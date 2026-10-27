"""Kenni backport II (E1): Codex workers under dispatch — the variant, the catalog
check before every start, the supervisor's receipts, and a Codex review that
`handoff` verifies and attests in one step (ported from Kenni #2357, whose
harness kept Codex reviews advisory; the owner decided they attest)."""
import argparse
import importlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.dont_write_bytecode = True

MODULES = ("dispatch", "_dispatch_codex", "attest", "attest_evidence", "check_review", "report", "process_git",
           "tower", "lane", "gate_invoke", "merge_route", "check_fix_streak", "plan_drift")
PLAN = ("# Plan\n\nissue: #7\ntier: 2\nplan-session model: claude-opus-5\n\n## Decisions\n\n"
        "## Acceptance criteria\n\n- AC-1: When x, the widget shall answer 42.\n")
TEST = "from widget import widget\n\ndef test_widget():\n    assert widget() == 42\n"


def _git(root, *args):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture
def mods(render, tmp_path):
    out = render(tmp_path / "t", {"project_name": "d", "modules": {"telemetry": True}})
    path = str(out / "scripts/process")
    sys.path.insert(0, path)
    for name in MODULES:
        sys.modules.pop(name, None)
    try:
        yield (lambda name: importlib.import_module(name)), out
    finally:
        sys.path.remove(path)
        for name in MODULES:
            sys.modules.pop(name, None)


def fake_codex(where: Path, mode: str = "ok", result: dict | None = None, models=("gpt-6-sol",)) -> Path:
    """A `codex` on PATH: `app-server --stdio` answers the catalog, `exec` writes
    `result` to its `-o` path (a review) and exits 0."""
    where.mkdir(parents=True, exist_ok=True)
    binary = where / "codex"
    rows = [{"id": m, "model": m, "supportedReasoningEfforts": [{"reasoningEffort": "medium"}]} for m in models]
    binary.write_text(f"#!{sys.executable}\n" + f"""import json, pathlib, sys, time
MODE, RESULT, ROWS = {mode!r}, {json.dumps(json.dumps(result))}, {rows!r}
if len(sys.argv) > 1 and sys.argv[1] == 'exec':
    assert sys.stdin.read() == ''
    if '-o' in sys.argv and json.loads(RESULT) is not None:
        pathlib.Path(sys.argv[sys.argv.index('-o') + 1]).write_text(RESULT)
    print('reviewer stdout', flush=True)
    raise SystemExit(0)
for line in sys.stdin:
    r = json.loads(line)
    if 'id' not in r:
        continue
    m = r['method']
    if MODE == 'timeout':
        time.sleep(10)
    if MODE == 'eof':
        break
    if m == 'initialize':
        out = {{}}
    elif m == 'config/read':
        # project configuration lives in the asked directory (`.codex/config.toml`)
        here = pathlib.Path(r['params'].get('cwd') or '.') / '.codex/config.toml'
        custom = MODE == 'custom' or (here.exists() and 'model_provider' in here.read_text())
        out = {{'config': {{'model_provider': 'custom' if custom else None}}}}
        if MODE in ('base_url', 'catalog', 'profile'):
            out['config'][{{'base_url': 'openai_base_url', 'catalog': 'model_catalog_json', 'profile': 'profile'}}[MODE]] = 'x'
    elif m == 'account/read':
        out = {{'account': None if MODE == 'auth' else {{'type': 'chatgpt'}}}}
    elif m == 'model/list':
        if r['params'].get('cursor'):
            out = {{'data': ROWS, 'nextCursor': None}}
        else:
            out = {{'data': [{{'id': 'other', 'model': 'other'}}], 'nextCursor': 'page2'}}
    if MODE == 'error':
        print(json.dumps({{'id': r['id'], 'error': {{'message': 'failed'}}}}), flush=True)
    else:
        print(json.dumps({{'id': r['id'], 'result': out}}), flush=True)
""")
    binary.chmod(0o755)
    return binary


def _variant(out: Path, binary: Path, model: str = "gpt-6-sol") -> None:
    p = out / "docs/process/model-policy.codex.json"
    v = json.loads(p.read_text())
    for row in [v["default"], *v["tiers"].values(), *v["classes"].values()]:
        for ph in row:
            row[ph] = model
    v["command"] = f"{binary} exec --model {{model}} --sandbox workspace-write {{prompt}}"
    v["phases"]["review"]["command"] = f"{binary} exec --model {{model}} --sandbox read-only {{prompt}}"
    p.write_text(json.dumps(v))


# --- the variant -----------------------------------------------------------------------

def test_the_variant_is_whole_and_never_takes_the_claude_overlay(mods):
    mod, out = mods
    d = mod("dispatch")
    (out / d.LOCAL_POLICY).write_text(json.dumps({"env": {"CLAUDE_CODE_SUBAGENT_MODEL": "sonnet"}}))
    v = d.load_policy(out, harness="codex")
    assert v["runner"] == "detached" and not v.get("env") and not v.get("decision_channel")
    assert d.model_for(v, 3, "review") == "gpt-6-astra"
    assert d.load_policy(out, harness="claude") == d.load_policy(out)
    # the project's values live in its own local file, laid over the variant
    (out / d.CODEX_LOCAL_POLICY).write_text(json.dumps({"tiers": {"3": {"review": "gpt-6-sol"}},
                                                        "context_sources": ["AGENTS.md"]}))
    v = d.load_policy(out, harness="codex")
    assert d.model_for(v, 3, "review") == "gpt-6-sol" and v["context_sources"] == ["AGENTS.md"]


@pytest.mark.parametrize("bad", ["unknown", "missing", "malformed", "incomplete", "tmux", "claude-env", "timeout"])
def test_an_unknown_or_incomplete_variant_is_refused(mods, bad):
    mod, out = mods
    d = mod("dispatch")
    p = out / d.CODEX_POLICY
    v = json.loads(p.read_text())
    if bad == "missing":
        p.unlink()
    elif bad == "malformed":
        p.write_text("[]")
    elif bad == "incomplete":
        del v["tiers"]["2"]["brainstorm"]
    elif bad == "tmux":
        v["runner"] = "tmux"
    elif bad == "claude-env":
        v["env"] = {"CLAUDE_CODE_X": "1"}
    elif bad == "timeout":
        v["review_timeout_minutes"] = 0
    if bad not in ("missing", "malformed"):
        p.write_text(json.dumps(v))
    with pytest.raises(SystemExit):
        d.load_policy(out, harness="unknown" if bad == "unknown" else "codex")


def test_the_variant_files_are_gate_files(mods):
    mod, _out = mods
    cr = mod("check_review")
    assert cr.is_gate_path("docs/process/model-policy.codex.json")
    assert cr.is_gate_path("docs/process/model-policy.codex.local.json")


def test_the_harness_travels_through_queue_and_drain(mods, monkeypatch):
    mod, out = mods
    d = mod("dispatch")
    base = {"issue": 7, "phase": "execute", "tier": 3, "branch": "7-x"}
    assert d._valid_entry({**base, "harness": "codex"}) == {**base, "harness": "codex"}
    assert d._valid_entry({**base, "harness": "other"}) is None
    calls = []
    monkeypatch.setattr(d, "start", lambda *a, **kw: calls.append(kw) or 0)
    d.queue_add(out, issue=7, phase="execute", tier=3, branch="7-x", harness="codex")
    assert d.queue_load(out)[0]["harness"] == "codex"
    assert d.drain(out) == 0 and calls[0]["harness"] == "codex" and d.queue_load(out) == []


def test_policy_prints_every_phase_of_the_variant(mods, capsys):
    mod, out = mods
    d = mod("dispatch")
    assert d.main(["--root", str(out), "policy", "--harness", "codex", "--tier", "3"]) == 0
    text = capsys.readouterr().out
    assert all(f"{ph}:" in text for ph in d.PHASES) and "gpt-6-astra" in text


# --- the catalog check -----------------------------------------------------------------

def test_the_catalog_check_pages_to_the_exact_model(mods, tmp_path):
    mod, _out = mods
    got = mod("_dispatch_codex").probe(str(fake_codex(tmp_path / "bin")), tmp_path, os.environ.copy(),
                                       "gpt-6-sol", "medium")
    assert got["model"] == "gpt-6-sol" and got["provider"] == "openai"


@pytest.mark.parametrize("mode, model, effort", [
    ("ok", "missing", None), ("auth", "gpt-6-sol", None), ("custom", "gpt-6-sol", None),
    ("base_url", "gpt-6-sol", None), ("catalog", "gpt-6-sol", None), ("profile", "gpt-6-sol", None),
    ("eof", "gpt-6-sol", None), ("error", "gpt-6-sol", None), ("timeout", "gpt-6-sol", None),
    ("ok", "gpt-6-sol", "high")])
def test_every_catalog_refusal_is_a_real_process_path(mods, tmp_path, mode, model, effort):
    mod, _out = mods
    with pytest.raises(ValueError):
        mod("_dispatch_codex").probe(str(fake_codex(tmp_path / "bin", mode)), tmp_path, os.environ.copy(),
                                     model, effort, timeout=0.5)


@pytest.mark.parametrize("argv", [
    ["codex", "exec", "--model", "m", "--sandbox", "workspace-write", "--json", "p"],
    ["codex", "exec", "--model", "m", "--sandbox", "read-only", "p"],
    ["wrapper", "exec", "--model", "m", "--sandbox", "workspace-write", "p"]])
def test_only_the_verified_cli_shape_runs(mods, argv):
    mod, _out = mods
    with pytest.raises(ValueError):
        mod("_dispatch_codex").executable(argv, "m", "execute", None, preview=True)


def _start_env(d, out, monkeypatch, tmp_path):
    monkeypatch.setattr(d, "_records_dir", lambda _: tmp_path / "records")
    (tmp_path / "records").mkdir(exist_ok=True)
    monkeypatch.setattr(d, "held_lanes", lambda _: set())
    monkeypatch.setattr(d, "disk_refusal", lambda _: None)
    monkeypatch.setattr(d, "override_refusal", lambda *a: None)


def test_a_refused_catalog_starts_nothing_and_records_the_way_out(mods, tmp_path, monkeypatch, capsys):
    mod, out = mods
    d, codex = mod("dispatch"), mod("_dispatch_codex")
    _variant(out, fake_codex(tmp_path / "bin", "auth"))
    _start_env(d, out, monkeypatch, tmp_path)
    wt = tmp_path / "wt"
    monkeypatch.setattr(d, "ensure_worktree", lambda *a: wt.mkdir(exist_ok=True) or wt)
    monkeypatch.setattr(d, "sync_worktree", lambda *a: None)
    monkeypatch.setattr(codex, "launch", lambda *a, **k: pytest.fail("a worker after a refused catalog"))
    rc = d.start(out, issue=7, phase="review", tier=2, branch="7-x", title=None, dry_run=False, harness="codex")
    err = capsys.readouterr().err
    assert rc == 3 and "no logged-in account" in err
    rows = (tmp_path / "records/codex" / codex.UNAVAILABLE).read_text().splitlines()
    row = json.loads(rows[-1])
    assert row["issue"] == 7 and row["phase"] == "review" and row["id"] in codex.unavailable_ids(tmp_path / "records")
    assert f"skipped cross-model work=7: codex unavailable {row['id']}" in err and "--harness claude" in err


def test_the_catalog_is_asked_in_the_worktree_the_worker_runs_in(mods, tmp_path, monkeypatch, capsys):
    """Downstream #240: Codex reads project configuration from its working directory —
    a provider only the worktree configures is refused, though the main checkout has none."""
    mod, out = mods
    d, codex = mod("dispatch"), mod("_dispatch_codex")
    _variant(out, fake_codex(tmp_path / "bin"))
    _start_env(d, out, monkeypatch, tmp_path)
    wt = tmp_path / "wt"
    (wt / ".codex").mkdir(parents=True)
    (wt / ".codex/config.toml").write_text('model_provider = "custom"\n')
    monkeypatch.setattr(d, "ensure_worktree", lambda *a: wt)
    monkeypatch.setattr(d, "sync_worktree", lambda *a: None)
    monkeypatch.setattr(codex, "launch", lambda *a, **k: pytest.fail("a worker the catalog check would refuse"))
    rc = d.start(out, issue=7, phase="review", tier=2, branch="7-x", title=None, dry_run=False, harness="codex")
    assert rc == 3 and "provider" in capsys.readouterr().err
    assert (tmp_path / "records/codex" / codex.UNAVAILABLE).exists()


def test_a_dry_run_is_unverified_and_asks_no_catalog(mods, tmp_path, monkeypatch, capsys):
    mod, out = mods
    d, codex = mod("dispatch"), mod("_dispatch_codex")
    _start_env(d, out, monkeypatch, tmp_path)
    monkeypatch.setattr(codex, "probe", lambda *a: pytest.fail("a dry run asked the catalog"))
    assert d.start(out, issue=7, phase="execute", tier=2, branch="7-x", title=None, dry_run=True,
                   harness="codex") == 0
    assert "UNVERIFIED" in capsys.readouterr().out


def test_a_codex_cell_gets_no_shell_form_block_and_ignores_the_key(mods, tmp_path, monkeypatch):
    # #323: the block is Claude's permission matching; Codex has its own sandbox
    mod, out = mods
    d = mod("dispatch")
    _start_env(d, out, monkeypatch, tmp_path)
    (out / d.CODEX_LOCAL_POLICY).write_text(json.dumps({"worker_shell_form": "OWN SHELL RULES"}))
    seen = []
    real = d.build_argv
    monkeypatch.setattr(d, "build_argv", lambda pol, model, prompt, *a, **k: seen.append(prompt)
                        or real(pol, model, prompt, *a, **k))
    for phase in ("plan", "execute", "review"):
        assert d.start(out, issue=7, phase=phase, tier=2, branch="7-x", title=None, dry_run=True,
                       harness="codex") == 0, phase
        assert d.SHELL_FORM not in seen[-1] and "OWN SHELL RULES" not in seen[-1], phase
    # the variant ignores the key: no type check refuses it there
    (out / d.CODEX_LOCAL_POLICY).write_text(json.dumps({"worker_shell_form": 7}))
    d.load_policy(out, harness="codex")


def test_a_model_attest_cannot_place_is_refused_before_the_run(mods, tmp_path, monkeypatch, capsys):
    mod, out = mods
    d = mod("dispatch")
    _variant(out, fake_codex(tmp_path / "bin"), model="o9-mystery")
    _start_env(d, out, monkeypatch, tmp_path)
    rc = d.start(out, issue=7, phase="review", tier=2, branch="7-x", title=None, dry_run=True, harness="codex")
    assert rc == 3 and "no class" in capsys.readouterr().err


# --- the supervisor ----------------------------------------------------------------------

def _wait(codex, d, rec, wanted=None):
    # a failed review runs twice (one retry); ~2.3 s unloaded — the full suite on four
    # workers stretched it past an earlier 15 s budget once (2026-10-15)
    until = time.monotonic() + 60
    while time.monotonic() < until:
        got = codex.outcome(rec, d._same_process(rec))
        if got in ("completed", "failed", "interrupted"):
            if wanted:
                assert got == wanted
            return got
        time.sleep(0.03)
    pytest.fail("no terminal receipt")


@pytest.mark.parametrize("code, expected", [(0, "completed"), (7, "failed")])
def test_the_supervisor_writes_the_real_exit(mods, tmp_path, code, expected):
    mod, _out = mods
    d, codex = mod("dispatch"), mod("_dispatch_codex")
    rec = codex.launch(tmp_path / "ev", [sys.executable, "-c", f"print('out');raise SystemExit({code})"], tmp_path,
                       os.environ.copy(), {"phase": "execute", "model": "m"}, deadline_s=60)
    codex.activate(rec)
    _wait(codex, d, rec, expected)
    assert "out" in (Path(rec["evidence"]) / "stdout.log").read_text()
    terminal = json.loads((Path(rec["evidence"]) / "terminal.json").read_text())
    assert terminal["exit_code"] == code
    terminal["invocation"] = "another"
    (Path(rec["evidence"]) / "terminal.json").write_text(json.dumps(terminal))
    assert codex.outcome(rec, False) == "unknown"


def test_the_deadline_interrupts_and_stop_reaps(mods, tmp_path):
    mod, _out = mods
    d, codex = mod("dispatch"), mod("_dispatch_codex")
    rec = codex.launch(tmp_path / "ev", [sys.executable, "-c", "import time;time.sleep(60)"], tmp_path,
                       os.environ.copy(), {"phase": "execute", "model": "m"}, deadline_s=1)
    codex.activate(rec)
    _wait(codex, d, rec, "interrupted")
    rec = codex.launch(tmp_path / "ev2", [sys.executable, "-c", "import time;time.sleep(60)"], tmp_path,
                       os.environ.copy(), {"phase": "execute", "model": "m"}, deadline_s=60)
    codex.activate(rec)
    until = time.monotonic() + 5
    while not (Path(rec["evidence"]) / "started.json").exists() and time.monotonic() < until:
        time.sleep(0.03)
    assert codex.stop_owned(rec, d._same_process) is True


def test_a_review_without_a_valid_result_runs_once_more_then_fails(mods, tmp_path):
    mod, _out = mods
    d, codex = mod("dispatch"), mod("_dispatch_codex")
    schema = tmp_path / "schema.json"
    schema.write_text(json.dumps(codex._schema(plan_review=False, gate=False)))
    counter = tmp_path / "runs"
    argv = [sys.executable, "-c", f"import pathlib;p=pathlib.Path({str(counter)!r});"
                                  "p.write_text(p.read_text()+'x' if p.exists() else 'x')"]
    rec = codex.launch(tmp_path / "ev", argv, tmp_path, os.environ.copy(),
                       {"phase": "review", "model": "m", "schema": str(schema), "result": str(tmp_path / "r.json")},
                       deadline_s=60)
    codex.activate(rec)
    _wait(codex, d, rec, "failed")
    assert counter.read_text() == "xx"


# --- handoff: verified, attested, pushed -------------------------------------------------

@pytest.fixture
def review_repo(render, tmp_path, monkeypatch):
    """A rendered project on branch 7-widget (plan, code, test) with a bare origin, an
    implementer report, and the Codex variant pointing at a fake CLI."""
    def build(result: dict, *, implementer="claude-opus-5", tier=2, gate=False, sibling=False):
        out = render(tmp_path / "r", {"project_name": "d", "modules": {"telemetry": True}})
        origin = tmp_path / "origin.git"
        subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
        _git(out, "init", "-q", "-b", "main")
        _git(out, "config", "user.email", "t@t")
        _git(out, "config", "user.name", "t")
        _git(out, "remote", "add", "origin", str(origin))
        _variant(out, fake_codex(tmp_path / "bin", result=result))
        if sibling:  # an earlier plan of the same issue, already on main
            (out / ".process-work/plans").mkdir(parents=True, exist_ok=True)
            (out / ".process-work/plans/2026-10-01-widget-part-1.md").write_text(PLAN)
        _git(out, "add", "-A")
        _git(out, "commit", "-q", "-m", "base")
        _git(out, "push", "-q", "origin", "main")
        _git(out, "checkout", "-q", "-b", "7-widget")
        (out / ".process-work/plans").mkdir(parents=True, exist_ok=True)
        (out / ".process-work/plans/2026-10-15-widget.md").write_text(PLAN.replace("tier: 2", f"tier: {tier}"))
        (out / "widget.py").write_text("def widget():\n    return 42\n")
        (out / "tests").mkdir(exist_ok=True)
        (out / "tests/test_widget.py").write_text(TEST)
        if gate:  # the diff touches gate code: the review must refute it
            (out / "scripts/process/extra_gate.py").write_text("X = 1\n")
        _git(out, "add", "-A")
        _git(out, "commit", "-q", "-m", "feat: widget")
        _git(out, "push", "-q", "origin", "7-widget")
        path = str(out / "scripts/process")
        sys.path.insert(0, path)
        for name in MODULES:
            sys.modules.pop(name, None)
        d = importlib.import_module("dispatch")
        codex = importlib.import_module("_dispatch_codex")
        monkeypatch.setattr(d, "ensure_worktree", lambda *a: out)
        monkeypatch.setattr(d, "sync_worktree", lambda *a: None)
        monkeypatch.setattr(d, "held_lanes", lambda _: set())
        monkeypatch.setattr(d, "disk_refusal", lambda _: None)
        monkeypatch.setattr(d, "override_refusal", lambda *a: None)
        monkeypatch.setattr(d, "plan_review_due_plans", lambda *a, **k: None)
        monkeypatch.setenv("PROCESS_PHASE", "execute")
        if implementer:
            d._report.write_report(out, "pushed", issue=7, note="", worker="7-widget", model=implementer)
        return out, d, codex
    yield build
    for name in MODULES:
        sys.modules.pop(name, None)
    sys.path[:] = [p for p in sys.path if not p.endswith("/r/scripts/process")]


PASS = {"verdict": "pass", "findings": [], "criteria": ["AC-1: tests/test_widget.py::test_widget"], "refute": []}


def _run_review(out, d, codex, tier=2):
    assert d.start(out, issue=7, phase="review", tier=tier, branch="7-widget", title=None, dry_run=False,
                   harness="codex") == 0
    rec = d._load_record(out, "7-widget")[1]
    _wait(codex, d, rec, "completed")
    return rec


def test_a_codex_review_is_verified_attested_and_pushed_in_one_step(review_repo):
    out, d, codex = review_repo(PASS)
    rec = _run_review(out, d, codex)
    assert rec["work"] == "7"  # one plan of the issue: the number stays the work (#290)
    assert d.handoff(out, "7-widget") == 0
    journal = "\n".join(p.read_text() for p in (out / ".process-work/journal").glob("**/*.md"))
    assert "REVIEW work=7 tier=2" in journal and "model=gpt-6-sol" in journal and "verdict=pass" in journal
    assert "cross-model" in journal  # the implementer is a Claude, the reviewer another family
    report = next((out / ".process-work/reviews").glob("*-7-codex-*.md")).read_text()
    assert "work: 7" in report and "publish-waived:" in report and "AC-1: tests/test_widget.py::test_widget" in report
    assert _git(out, "status", "--porcelain") == ""
    assert _git(out, "rev-parse", "HEAD") == _git(out, "ls-remote", "origin", "refs/heads/7-widget").split()[0]
    reports = [r for r in d._report.read_reports(out) if r.get("state") == "review-pass"]
    assert reports and reports[-1]["worker"] == "7-widget" and reports[-1]["model"] == "gpt-6-sol"
    # never attested twice
    lines = journal.count("REVIEW work=7")
    assert d.handoff(out, "7-widget") == 0
    again = "\n".join(p.read_text() for p in (out / ".process-work/journal").glob("**/*.md"))
    assert again.count("REVIEW work=7") == lines
    assert json.loads((Path(rec["evidence"]) / codex.HANDOFF).read_text())["state"] == "attested"


def test_the_written_report_opens_with_its_header_block(review_repo, render, tmp_path):
    """#286 (Kenni #2686): the title stood above the header block, so the report gate read
    no `review:` and refused the push, and `report_header` read no `work:`."""
    out, d, codex = review_repo(PASS)
    _run_review(out, d, codex)
    assert d.handoff(out, "7-widget") == 0
    text = next((out / ".process-work/reviews").glob("*-7-codex-*.md")).read_text()
    review = importlib.import_module("check_review")
    head = review.report_header(text)
    assert head.get("work") == ["7"] and head.get("review"), head
    # the github-issues report gate, as rendered with that module, reads the same file
    gated = render(tmp_path / "gated", {"project_name": "g", "modules": {"github_issues": True}})
    (gated / ".process-work/reviews").mkdir(parents=True, exist_ok=True)
    (gated / ".process-work/reviews/2026-10-21-7-codex-review.md").write_text(text)
    r = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, 'scripts/process'); "
                        "import check_issues as g; hard, _ = g._check_reports(__import__('pathlib').Path('.'), None); "
                        "print('\\n'.join(hard))"], cwd=gated, capture_output=True, text=True)
    assert r.returncode == 0 and "header" not in r.stdout, r.stdout + r.stderr


def test_the_report_header_names_the_round_attest_writes(review_repo):
    """#293 AC-5: findings are counted per round from the report's `round:` header — the
    handoff writes the round its own attest puts on the REVIEW line."""
    out, d, codex = review_repo(PASS)
    journal = out / ".process-work/journal/2026-10-16.md"
    journal.parent.mkdir(parents=True, exist_ok=True)
    journal.write_text("REVIEW work=7 tier=2 reviewer=r model=claude-opus-5 independence=bundle,non-implementing "
                       "verdict=block round=1\n"
                       # v2.77 asks a class test of a blocked round; this fixture's block had no defect
                       "skipped class-test work=7: a fixture round, no code defect\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "docs: attest 7 round 1")
    _git(out, "push", "-q", "origin", "7-widget")
    _run_review(out, d, codex)
    assert d.handoff(out, "7-widget") == 0
    text = next((out / ".process-work/reviews").glob("*-7-codex-*.md")).read_text()
    head = importlib.import_module("check_review").report_header(text)
    lines = "\n".join(p.read_text() for p in (out / ".process-work/journal").glob("**/*.md"))
    assert head.get("round") == ["2"] and "verdict=pass round=2" in lines, (head, lines)
    # the header block stays one block: `round:` sits before the first blank line
    assert "round: 2" in text.split("\n\n", 1)[0]


def test_a_second_lens_on_a_blocked_head_attests_that_round(review_repo):
    """A Codex lens of a round another lens already blocked on this head (its attest commit
    aside) is that round: one review round stays one blocked round, and owes no REPLAN and
    no class test of a round that never ran (v2.77 cross-model review)."""
    out, d, codex = review_repo(PASS)
    reviewed, base = _git(out, "rev-parse", "HEAD"), _git(out, "rev-parse", "main")
    journal = out / ".process-work/journal/2026-10-16.md"
    journal.parent.mkdir(parents=True, exist_ok=True)
    journal.write_text("REVIEW work=7 tier=2 reviewer=r model=claude-opus-5 independence=bundle,non-implementing "
                       f"base={base} head={reviewed} verdict=block round=1\n"
                       "skipped class-test work=7: a fixture round, no code defect\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "docs: attest 7 round 1, lens a")
    _git(out, "push", "-q", "origin", "7-widget")
    _run_review(out, d, codex)
    assert d.handoff(out, "7-widget") == 0
    text = next((out / ".process-work/reviews").glob("*-7-codex-*.md")).read_text()
    head = importlib.import_module("check_review").report_header(text)
    lines = "\n".join(p.read_text() for p in (out / ".process-work/journal").glob("**/*.md"))
    assert head.get("round") == ["1"] and "verdict=pass round=1" in lines, (head, lines)


def _blocked_lens(out, work: str) -> tuple[str, argparse.Namespace]:
    """Lens A blocked `work` on the current head: its attest commit adds the REVIEW line."""
    reviewed, base = _git(out, "rev-parse", "HEAD"), _git(out, "rev-parse", "main")
    journal = out / ".process-work/journal/2026-10-16.md"
    journal.parent.mkdir(parents=True, exist_ok=True)
    journal.write_text(f"REVIEW work={work} tier=2 reviewer=r model=claude-opus-5 "
                       "independence=bundle,non-implementing "
                       f"base={base} head={reviewed} verdict=block round=1\n")
    return reviewed, argparse.Namespace(work=work, round_=None)


def test_the_lens_round_has_one_owner(mods):
    """#303: the lens-round rule lives in attest, not in the Codex harness."""
    load, out = mods
    attest = load("attest")
    src = (out / "scripts/process/_dispatch_codex.py").read_text()
    assert "def _blocked_round_at" not in src and "def _attest_commit" not in src
    assert "attest.blocked_round_at(" in src
    assert callable(attest.blocked_round_at)
    assert "attest.blocked_round_at(" in (out / "scripts/process/make_review_bundle.py").read_text()


def test_only_attest_commits_keep_a_blocked_round(review_repo):
    import attest
    """Another lens of a blocked round is one whose head lies only attest commits above the
    blocked head — each adds a REVIEW line and changes nothing but reports, journal and
    records appended to a plan (`records_only`). A plan changed in its content, by a plan
    or a code fix, or a commit adding no REVIEW line, is a fix: the next round (v2.77
    cross-model review, rounds 2 and 3)."""
    out, _d, codex = review_repo(PASS)
    plan = out / ".process-work/plans/2026-10-15-widget.md"
    for work in ("7-plan", "7"):
        _git(out, "checkout", "-q", "-B", f"t-{work}", "7-widget")
        _reviewed, args = _blocked_lens(out, work)
        plan.write_text(plan.read_text() + "\nREFUTE work=7 round=1: 3 scenarios, none held\n")
        _git(out, "add", "-A")
        _git(out, "commit", "-q", "-m", f"docs: attest {work} round 1, lens a")
        assert attest.blocked_round_at(out, args, _git(out, "rev-parse", "HEAD")) == 1, work
        # the plan changed in its content: a fix, the next round
        plan.write_text(plan.read_text().replace("tier:", "Fixed.\n\ntier:", 1))
        _git(out, "commit", "-q", "-am", "plan: fix round 1")
        assert attest.blocked_round_at(out, args, _git(out, "rev-parse", "HEAD")) is None, work
    # an attest commit that archives the plan (`attest --archive`, a pass of another lens) moves it
    _git(out, "checkout", "-q", "-B", "t-archive", "7-widget")
    _reviewed, args = _blocked_lens(out, "7")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "docs: attest 7 round 1, lens a")
    (out / ".process-work/plans/archive").mkdir(parents=True, exist_ok=True)
    _git(out, "mv", ".process-work/plans/2026-10-15-widget.md", ".process-work/plans/archive/2026-10-15-widget.md")
    archived = out / ".process-work/plans/archive/2026-10-15-widget.md"
    archived.write_text(archived.read_text() + "\nREFUTE work=7 round=1: 2 scenarios, none held\n")
    journal = out / ".process-work/journal/2026-10-16.md"
    journal.write_text(journal.read_text() + journal.read_text().replace("verdict=block", "verdict=pass")
                       .replace("reviewer=r", "reviewer=s"))
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "docs: attest 7 round 1, lens b, archive")
    assert attest.blocked_round_at(out, args, _git(out, "rev-parse", "HEAD")) == 1
    # the move holds when git sees no rename: records that outweigh a short plan (v2.77 cross-model
    # review, round 5) — the archive rule pairs the deleted plan with its archived copy
    _git(out, "checkout", "-q", "-B", "t-archive-big", "7-widget")
    _reviewed, args = _blocked_lens(out, "7")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "docs: attest 7 round 1, lens a")
    _git(out, "mv", ".process-work/plans/2026-10-15-widget.md", ".process-work/plans/archive/2026-10-15-widget.md")
    archived.write_text(archived.read_text() + "".join(
        f"\nREFUTE work=7 round=1: scenario {n} of a long refute, none held\n" for n in range(80)))
    journal.write_text(journal.read_text() + journal.read_text().replace("verdict=block", "verdict=pass")
                       .replace("reviewer=r", "reviewer=s"))
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "docs: attest 7 round 1, lens b, archive")
    assert not any(k.startswith("R") for k in _git(out, "diff", "--name-status", "-M", "HEAD~1", "HEAD").split()[0::2])
    assert attest.blocked_round_at(out, args, _git(out, "rev-parse", "HEAD")) == 1
    # a lens line byte-identical to one already there (same model, same head) is still added (round 6)
    _git(out, "checkout", "-q", "-B", "t-twin", "7-widget")
    _reviewed, args = _blocked_lens(out, "7")
    journal.write_text(journal.read_text() + journal.read_text().replace("verdict=block", "verdict=pass"))
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "docs: attest 7 round 1, lenses a and b")
    journal.write_text(journal.read_text() + journal.read_text().splitlines()[-1] + "\n")
    _git(out, "commit", "-q", "-am", "docs: attest 7 round 1, lens c")
    assert attest.blocked_round_at(out, args, _git(out, "rev-parse", "HEAD")) == 1
    # a record appended without a REVIEW line (a decision answering the block) is no attest commit
    _git(out, "checkout", "-q", "-B", "t-decision", "7-widget")
    _reviewed, args = _blocked_lens(out, "7")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "docs: attest 7 round 1, lens a")
    plan.write_text(plan.read_text() + "\n- DECISION 2026-10-16 agent: the finding stays\n")
    _git(out, "commit", "-q", "-am", "plan: decide round 1")
    assert attest.blocked_round_at(out, args, _git(out, "rev-parse", "HEAD")) is None


def test_the_report_text_carries_no_round_it_was_not_given(mods):
    load, _out = mods
    codex = load("_dispatch_codex")
    rec = {"binding": {"base": "b", "head": "h", "diff_sha256": "x"}, "branch": "7-w", "model": "m",
           "invocation": "i", "result_sha256": "r", "issue": 7}
    result = {"verdict": "pass", "findings": [], "criteria": [], "refute": []}
    text = codex._report_text(rec, result, work="7", plan_review=True, refute_round=None, review_round=3)
    assert text.split("\n\n", 1)[0].splitlines()[1:4] == ["phase: plan", "work: 7", "round: 3"]
    assert "round:" not in codex._report_text(rec, result, work="7", plan_review=False, refute_round=None)


def test_a_refused_attest_leaves_the_worktree_clean_and_can_be_handed_off_again(review_repo):
    unproven = {**PASS, "criteria": []}  # no line for AC-1: attest refuses the pass
    out, d, codex = review_repo(unproven)
    rec = _run_review(out, d, codex)
    head = _git(out, "rev-parse", "HEAD")
    assert d.handoff(out, "7-widget") == 1
    assert _git(out, "status", "--porcelain") == "" and _git(out, "rev-parse", "HEAD") == head
    done = json.loads((Path(rec["evidence"]) / codex.HANDOFF).read_text())
    assert done["state"] == "refused" and "AC-1" in done["reasons"]
    assert [r for r in d._report.read_reports(out) if r.get("state") == "blocked"]
    # a record appended to the plan afterwards rides the next handoff
    plan = out / ".process-work/plans/2026-10-15-widget.md"
    plan.write_text(plan.read_text() + "\nskipped ac-trace work=7: the criterion is checked by hand\n")
    assert d.handoff(out, "7-widget") == 0
    assert "skipped ac-trace" in _git(out, "show", "HEAD:.process-work/plans/2026-10-15-widget.md")


def test_the_same_family_is_never_claimed_cross_model(review_repo):
    out, d, codex = review_repo(PASS, implementer="gpt-6-luna")
    _run_review(out, d, codex)
    assert d.handoff(out, "7-widget") == 0
    journal = "\n".join(p.read_text() for p in (out / ".process-work/journal").glob("**/*.md"))
    assert "single-family" in journal and "cross-model" not in journal
    # an unmeasured implementer is no other family either
    base = _git(out, "merge-base", "main", "HEAD")
    assert codex.independence(out, base, "gpt-6-sol", None) == "single-family"
    assert codex.independence(out, base, "gpt-6-sol", ["claude-sonnet-5"]) == "cross-model"
    assert codex.independence(out, base, "claude-opus-5", ["claude-sonnet-5"]) == "single-family"
    # every implementing model counts: one Codex push among Claude pushes is no other family
    assert codex.independence(out, base, "gpt-6-sol", ["claude-sonnet-5", "gpt-6-luna"]) == "single-family"


def test_a_tampered_or_stale_review_is_never_handed_off(review_repo):
    out, d, codex = review_repo(PASS)
    rec = _run_review(out, d, codex)
    Path(rec["result"]).write_text(json.dumps({**PASS, "verdict": "block", "findings": []}))
    assert d.handoff(out, "7-widget") == 3
    assert not list((out / ".process-work/reviews").glob("*-codex-*.md")) if (out / ".process-work/reviews").exists() else True
    assert "REVIEW work=7" not in "\n".join(p.read_text() for p in (out / ".process-work/journal").glob("**/*.md"))


def test_a_follow_up_without_an_issue_is_refused(review_repo):
    bad = {**PASS, "findings": [{"sev": "minor", "action": "follow-up", "kind": "implementation", "issue": "-",
                                 "class": "judgment", "rule": "-", "at": "-", "title": "later"}]}
    out, d, codex = review_repo(bad)
    _run_review(out, d, codex)
    assert d.handoff(out, "7-widget") == 3


# --- the tower's traces ------------------------------------------------------------------

def test_the_tower_names_an_unrecorded_skip_and_an_overridden_block(review_repo):
    out, d, codex = review_repo(PASS)
    tower = importlib.import_module("tower")
    plan = out / ".process-work/plans/2026-10-15-widget.md"
    plan.write_text(plan.read_text() + "\nskipped cross-model work=7: codex unavailable deadbeef0000 — no login\n")
    j = out / ".process-work/journal"
    j.mkdir(parents=True, exist_ok=True)
    head = _git(out, "rev-parse", "HEAD")
    base = _git(out, "merge-base", "main", "HEAD")
    (j / "2026-10-15.md").write_text(
        f"REVIEW work=7 tier=2 reviewer=codex model=gpt-6-sol independence=bundle,non-implementing,cross-model "
        f"verdict=block round=1 base={base} head={head}\n"
        f"REVIEW work=7 tier=2 reviewer=fresh model=claude-opus-5 independence=bundle,non-implementing,single-family "
        f"verdict=pass round=1 base={base} head={head}\n")
    kinds = {f["kind"]: f for f in tower.codex_findings(out, [{"path": str(out), "branch": "7-widget"}])}
    assert "deadbeef0000" in kinds["codex-skip-unmatched"]["what"]
    assert "gpt-" in kinds["codex-block-overridden"]["what"]
    row = codex.record_unavailable(d._records_dir(out), issue=7, phase="review", model="gpt-6-sol",
                                   branch="7-widget", reason="no login")
    plan.write_text(plan.read_text().replace("deadbeef0000", row))
    kinds = {f["kind"] for f in tower.codex_findings(out, [{"path": str(out), "branch": "7-widget"}])}
    assert "codex-skip-unmatched" not in kinds


# --- rehydrate --codex ---------------------------------------------------------------------

def test_rehydrate_gives_a_codex_session_the_whole_context_or_stops(render, tmp_path):
    out = render(tmp_path / "r", {"project_name": "d"})
    _git(out, "init", "-q", "-b", "main")
    run = [sys.executable, str(out / "scripts/process/rehydrate.py"), "--codex"]
    got = json.loads(subprocess.run(run, cwd=out, capture_output=True, text=True, check=True).stdout)
    text = got["hookSpecificOutput"]["additionalContext"]
    assert "## Source: docs/process/kernel.md" in text and "## Source: docs/process/model-policy.codex.json" in text
    (out / "docs/process/model-policy.codex.local.json").write_text(json.dumps({"context_sources": ["NOTES.md"]}))
    got = json.loads(subprocess.run(run, cwd=out, capture_output=True, text=True, check=True).stdout)
    assert got["continue"] is False and "NOTES.md" in got["stopReason"]  # a missing source: no partial context
    (out / "NOTES.md").write_text("project notes\n")
    got = json.loads(subprocess.run(run, cwd=out, capture_output=True, text=True, check=True).stdout)
    assert "project notes" in got["hookSpecificOutput"]["additionalContext"]
    check = subprocess.run([*run, "--check"], cwd=out, capture_output=True, text=True)
    assert check.returncode == 1
    assert subprocess.run([*run, "--install"], cwd=out, capture_output=True, text=True).returncode == 0
    assert subprocess.run([*run, "--check"], cwd=out, capture_output=True, text=True).returncode == 0
    hooks = json.loads((out / ".codex/hooks.json").read_text())["hooks"]["SessionStart"]
    assert len(hooks) == 1 and hooks[0]["hooks"][0]["command"].endswith("--codex")


# --- review findings of v2.73 (code review / refute) -----------------------------------

def test_a_harness_never_crosses_a_review_in_the_chain(mods, monkeypatch):
    """A Codex review's fix round on Codex, or a Codex execute reviewed by Codex, would leave
    the review single-family: the other side of a review takes the default harness."""
    mod, out = mods
    d = mod("dispatch")
    calls = []
    monkeypatch.setattr(d, "queue_add", lambda *a, **k: calls.append(k))
    monkeypatch.setattr(d, "drain", lambda *a: 0)
    monkeypatch.setattr(d, "stop", lambda *a, **k: 0)
    monkeypatch.setattr(d, "plan_review_state", lambda *a: (2, True))
    monkeypatch.setattr(d, "plan_gates", lambda *a: None)
    monkeypatch.setattr(d, "work_complete_on_origin", lambda *a: True)
    monkeypatch.setattr(d, "new_code_on_origin", lambda *a: True)
    monkeypatch.setattr(d, "_out", lambda *a: "")
    # a passed Codex plan review queues execute; a Codex execute queues its review; a Codex plan its execute
    for phase, report, plan_review, nxt, carried in (("review", "review-pass", True, "execute", None),
                                                     ("execute", "pushed", False, "review", None),
                                                     ("plan", "planned", False, "execute", "codex")):
        calls.clear()
        rec = {"branch": "7-x", "issue": 7, "phase": phase, "tier": 2, "harness": "codex", "worktree": str(out),
               "started": 1, "state": "gone", "plan_review": plan_review}
        monkeypatch.setattr(d, "records", lambda _r, rec=rec: [rec])
        monkeypatch.setattr(d, "_load_record", lambda *a, rec=rec: (out / "r", rec))
        monkeypatch.setattr(d, "session_report", lambda *a, s=report: {"state": s})
        assert d._chain(out) == 0
        assert [c.get("phase") for c in calls] == [nxt], (phase, calls)
        assert calls[0].get("harness") == carried, (phase, calls[0])


def test_an_issue_with_several_plans_is_attested_by_the_sessions_plan(review_repo, capsys):
    # the issue's number names two plans at head, and attest refuses it: the
    # review attests the plan it reviewed, by its slug (#290)
    out, d, codex = review_repo(PASS, sibling=True)
    rec = _run_review(out, d, codex)
    assert rec["work"] == "2026-10-15-widget"
    assert d.handoff(out, "7-widget") == 0
    journal = "\n".join(p.read_text() for p in (out / ".process-work/journal").glob("**/*.md"))
    assert "REVIEW work=2026-10-15-widget tier=2" in journal and "REVIEW work=7 " not in journal
    hint = codex.fallback_hint(7, "review", False, "r1", 2, rec["work"])
    assert "skipped cross-model work=2026-10-15-widget:" in hint
    assert "work=2026-10-15-widget-plan:" in codex.fallback_hint(7, "review", True, "r1", 2, rec["work"])


def test_a_failed_review_run_records_the_way_out(review_repo, capsys):
    out, d, codex = review_repo(None)  # the fake CLI writes no result: off schema
    assert d.start(out, issue=7, phase="review", tier=2, branch="7-widget", title=None, dry_run=False,
                   harness="codex") == 0
    rec = d._load_record(out, "7-widget")[1]
    _wait(codex, d, rec, "failed")
    assert d.handoff(out, "7-widget") == 3
    err = capsys.readouterr().err
    rows = [json.loads(x) for x in (d._records_dir(out) / "codex" / codex.UNAVAILABLE).read_text().splitlines()]
    assert rows[-1]["head"] == rec["binding"]["head"] and f"codex unavailable {rows[-1]['id']}" in err
    assert "--tier 2" in err


def test_a_failed_attest_commit_leaves_the_worktree_clean_and_rerunnable(review_repo):
    out, d, codex = review_repo(PASS)
    _run_review(out, d, codex)
    hooks = out / ".git/hooks"
    hooks.mkdir(exist_ok=True)
    hook = hooks / "pre-commit"
    hook.write_text("#!/bin/sh\nexit 1\n")
    hook.chmod(0o755)
    head = _git(out, "rev-parse", "HEAD")
    assert d.handoff(out, "7-widget") == 1
    assert _git(out, "status", "--porcelain") == "" and _git(out, "rev-parse", "HEAD") == head
    hook.unlink()
    assert d.handoff(out, "7-widget") == 0


def test_a_handoff_that_stopped_after_its_commit_finishes_without_a_second_line(review_repo):
    out, d, codex = review_repo(PASS)
    rec = _run_review(out, d, codex)
    assert d.handoff(out, "7-widget") == 0
    (Path(rec["evidence"]) / codex.HANDOFF).unlink()  # as if it crashed before its receipt
    journal = lambda: "\n".join(p.read_text() for p in (out / ".process-work/journal").glob("**/*.md"))  # noqa: E731
    lines = journal().count("REVIEW work=7")
    assert d.handoff(out, "7-widget") == 0
    assert journal().count("REVIEW work=7") == lines


def test_an_attested_handoff_whose_push_failed_pushes_again(review_repo):
    """Downstream #239: a failed push left `pushed=false` and every later handoff
    returned the old receipt — the attest commit never reached origin."""
    out, d, codex = review_repo(PASS)
    rec = _run_review(out, d, codex)
    hook = out / ".git/hooks/pre-push"
    hook.parent.mkdir(exist_ok=True)
    hook.write_text("#!/bin/sh\nexit 1\n")
    hook.chmod(0o755)
    assert d.handoff(out, "7-widget") == 1
    assert json.loads((Path(rec["evidence"]) / codex.HANDOFF).read_text())["pushed"] is False
    journal = lambda: "\n".join(p.read_text() for p in (out / ".process-work/journal").glob("**/*.md"))  # noqa: E731
    lines = journal().count("REVIEW work=7")
    hook.unlink()
    assert d.handoff(out, "7-widget") == 0
    assert _git(out, "ls-remote", "origin", "refs/heads/7-widget").split()[0] == _git(out, "rev-parse", "HEAD")
    assert journal().count("REVIEW work=7") == lines


def test_an_attested_handoff_never_pushes_commits_made_after_it(review_repo):
    out, d, codex = review_repo(PASS)
    rec = _run_review(out, d, codex)
    hook = out / ".git/hooks/pre-push"
    hook.parent.mkdir(exist_ok=True)
    hook.write_text("#!/bin/sh\nexit 1\n")
    hook.chmod(0o755)
    assert d.handoff(out, "7-widget") == 1
    hook.unlink()
    (out / "later.txt").write_text("x\n")
    _git(out, "add", "later.txt")
    _git(out, "commit", "-q", "-m", "later")
    remote = _git(out, "ls-remote", "origin", "refs/heads/7-widget").split()[0]
    assert d.handoff(out, "7-widget") == 1  # the old receipt: not pushed, and nothing pushed now
    assert _git(out, "ls-remote", "origin", "refs/heads/7-widget").split()[0] == remote
    assert json.loads((Path(rec["evidence"]) / codex.HANDOFF).read_text())["pushed"] is False


def test_an_amended_attest_commit_is_never_pushed_again(review_repo):
    """Refute v2.74: an attest commit amended with unreviewed code passed `_committed_attest`."""
    out, d, codex = review_repo(PASS)
    _run_review(out, d, codex)
    hook = out / ".git/hooks/pre-push"
    hook.parent.mkdir(exist_ok=True)
    hook.write_text("#!/bin/sh\nexit 1\n")
    hook.chmod(0o755)
    assert d.handoff(out, "7-widget") == 1
    hook.unlink()
    (out / "evil.py").write_text("X = 1\n")
    _git(out, "add", "evil.py")
    _git(out, "commit", "-q", "--amend", "--no-edit")
    remote = _git(out, "ls-remote", "origin", "refs/heads/7-widget").split()[0]
    assert d.handoff(out, "7-widget") == 1
    assert _git(out, "ls-remote", "origin", "refs/heads/7-widget").split()[0] == remote


@pytest.mark.parametrize("issue", ["none", "", "#x"])
def test_a_finding_names_an_issue_or_none(review_repo, issue):
    bad = {**PASS, "findings": [{"sev": "minor", "action": "accept", "kind": "implementation", "issue": issue,
                                 "title": "t"}]}
    out, d, codex = review_repo(bad)
    assert d.start(out, issue=7, phase="review", tier=2, branch="7-widget", title=None, dry_run=False,
                   harness="codex") == 0
    _wait(codex, d, d._load_record(out, "7-widget")[1], "failed")  # off its schema: the run failed
    assert d.handoff(out, "7-widget") == 3


def test_tier_2_gate_code_carries_the_reviewers_refute_in_its_report(review_repo):
    refuted = {**PASS, "refute": ["survives: a stale stamp cannot reach the gate"]}
    out, d, codex = review_repo(refuted, gate=True)
    rec = _run_review(out, d, codex)
    assert rec["gate_code"] is True
    assert json.loads(Path(rec["schema"]).read_text())["x-gate-code"] is True
    assert d.handoff(out, "7-widget") == 0
    report = next((out / ".process-work/reviews").glob("*-7-codex-*.md")).read_text()
    assert "REFUTE work=7 round=1: survives: a stale stamp cannot reach the gate" in report
    # a gate-code result without its refute is no usable review
    assert codex._validated(PASS, rec) is None


def test_a_codex_plan_review_attests_the_plan(review_repo):
    plan_pass = {"verdict": "pass", "findings": [], "criteria": [], "refute": []}
    out, d, codex = review_repo(plan_pass, implementer=None)
    d._report.write_report(out, "planned", issue=7, note="", worker="7-widget", model="claude-opus-5")
    assert d.start(out, issue=7, phase="review", tier=2, branch="7-widget", title=None, dry_run=False,
                   plan_review=True, harness="codex") == 0
    rec = d._load_record(out, "7-widget")[1]
    _wait(codex, d, rec, "completed")
    assert d.handoff(out, "7-widget") == 0
    report = next((out / ".process-work/reviews").glob("*-7-plan-codex-*.md")).read_text()
    assert "phase: plan" in report
    journal = "\n".join(p.read_text() for p in (out / ".process-work/journal").glob("**/*.md"))
    assert "REVIEW work=7-plan" in journal and "cross-model" in journal


def test_rehydrate_stops_on_a_malformed_or_escaping_codex_policy(render, tmp_path):
    out = render(tmp_path / "r", {"project_name": "d"})
    _git(out, "init", "-q", "-b", "main")
    run = [sys.executable, str(out / "scripts/process/rehydrate.py"), "--codex"]
    local = out / "docs/process/model-policy.codex.local.json"
    for bad in ('{"context_sources": ["NOTES.md"]', '{"context_sources": [7]}', "[]",
                '{"context_sources": ["/etc/hostname"]}', '{"context_sources": ["../x"]}'):
        local.write_text(bad)
        got = json.loads(subprocess.run(run, cwd=out, capture_output=True, text=True, check=True).stdout)
        assert got.get("continue") is False, bad
    local.unlink()
    assert subprocess.run([*run, "--install"], cwd=out, capture_output=True, text=True).returncode == 0
    assert "/.codex/" in (out / ".git/info/exclude").read_text()
    assert _git(out, "status", "--porcelain", "--", ".codex") == ""


def test_the_tower_survives_a_corrupt_trace_and_forgets_finished_work(review_repo):
    out, d, codex = review_repo(PASS)
    tower = importlib.import_module("tower")
    folder = d._records_dir(out) / "codex"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / codex.UNAVAILABLE).write_text("[" * 200000 + "]" * 200000 + "\n")
    assert isinstance(codex.unavailable_ids(d._records_dir(out)), set)
    j = out / ".process-work/journal"
    j.mkdir(parents=True, exist_ok=True)
    head, base = _git(out, "rev-parse", "HEAD"), _git(out, "merge-base", "main", "HEAD")
    (j / "2026-10-15.md").write_text(
        f"REVIEW work=99 tier=2 reviewer=codex model=gpt-6-sol independence=bundle,non-implementing,cross-model "
        f"verdict=block round=1 base={base} head={head}\n"
        f"REVIEW work=99 tier=2 reviewer=fresh model=claude-opus-5 independence=bundle,non-implementing,single-family "
        f"verdict=pass round=1 base={base} head={head}\n")
    kinds = {f["kind"] for f in tower.codex_findings(out, [{"path": str(out), "branch": "7-widget"}])}
    assert "codex-block-overridden" not in kinds  # work 99 has no active plan: history, not a finding


def test_ci_true_renders_no_manual_wording(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {"telemetry": True}})
    for name in ("process-gates.yml", "owner-digest.yml", "process-kpis.yml"):
        assert "ci.github: manual" not in (out / ".github/workflows" / name).read_text(), name


# --- refute round 2 ------------------------------------------------------------------------

def test_a_foreign_or_uncommitted_review_line_finishes_nothing(review_repo):
    out, d, codex = review_repo(None)  # the run fails: no result
    assert d.start(out, issue=7, phase="review", tier=2, branch="7-widget", title=None, dry_run=False,
                   harness="codex") == 0
    rec = d._load_record(out, "7-widget")[1]
    _wait(codex, d, rec, "failed")
    j = out / ".process-work/journal"
    j.mkdir(parents=True, exist_ok=True)
    (j / "2026-10-14.md").write_text(f"REVIEW work=7 tier=2 reviewer=fresh model=gpt-6-sol "
                                     f"independence=bundle,non-implementing,cross-model verdict=pass round=1 "
                                     f"base={rec['binding']['base']} head={rec['binding']['head']}\n")
    assert d.handoff(out, "7-widget") == 3
    assert not [r for r in d._report.read_reports(out) if r.get("state") == "review-pass"]


def test_a_review_without_receipt_is_no_way_out(review_repo, capsys):
    block = {"verdict": "block", "findings": [{"sev": "major", "action": "fix", "kind": "implementation",
                                               "issue": "-", "class": "testable", "rule": "mutation",
                                               "at": "src/widget.py:3", "title": "wrong"}], "criteria": [], "refute": []}
    out, d, codex = review_repo(block)
    rec = _run_review(out, d, codex)
    (Path(rec["evidence"]) / "terminal.json").unlink()
    assert d.handoff(out, "7-widget") == 3
    err = capsys.readouterr().err
    assert "receipts are unknown" in err and "codex unavailable" not in err
    assert not (d._records_dir(out) / "codex" / codex.UNAVAILABLE).exists()


def test_a_codex_finding_names_its_reviewer(review_repo):
    """#247: the handoff's findings carry `by=codex`, so a later count can tell them apart."""
    block = {"verdict": "block", "findings": [{"sev": "major", "action": "fix", "kind": "implementation",
                                               "issue": "-", "class": "testable", "rule": "mutation",
                                               "at": "src/widget.py:3", "title": "wrong"}],
             "criteria": ["AC-1: tests/test_widget.py::test_widget"], "refute": []}
    out, d, codex = review_repo(block)
    _run_review(out, d, codex)
    d.handoff(out, "7-widget")
    report = next((out / ".process-work/reviews").glob("*-7-codex-*.md")).read_text()
    assert "FINDING sev=major action=fix kind=implementation issue=- by=codex class=testable rule=mutation at=src/widget.py:3 wrong" \
        in report


def test_the_implementer_flag_never_overrides_a_measured_model(review_repo):
    out, d, codex = review_repo(PASS, implementer="gpt-6-luna")
    d._report.write_report(out, "pushed", issue=7, note="", worker="7-widget", model=None)  # not measured
    _run_review(out, d, codex)
    assert d.handoff(out, "7-widget", implementer="claude-opus-5") == 0
    journal = "\n".join(p.read_text() for p in (out / ".process-work/journal").glob("**/*.md"))
    assert "single-family" in journal and "cross-model" not in journal


# --- code review round 2: a red test for every round-1 fix ---------------------------------

def test_the_families_are_read_at_the_base_not_the_reviewed_branch(review_repo):
    """F1: a branch that draws its own family lines does not make its review cross-model."""
    out, d, codex = review_repo(PASS, implementer="gpt-6-luna")
    policy = out / "docs/process/model-policy.json"
    data = json.loads(policy.read_text())
    data["review_evidence"]["families"] = [*data["review_evidence"]["families"], "gpt-6-luna"]
    policy.write_text(json.dumps(data))
    _git(out, "commit", "-qam", "chore: luna is its own family")
    base, head = _git(out, "merge-base", "main", "HEAD"), _git(out, "rev-parse", "HEAD")
    assert codex.independence(out, head, "gpt-6-sol", ["gpt-6-luna"]) == "cross-model"  # the branch's own lines
    assert codex.independence(out, base, "gpt-6-sol", ["gpt-6-luna"]) == "single-family"


def test_the_implementer_flag_is_refused_when_every_model_is_measured(review_repo, capsys):
    """F2: `--implementer` stands in only for what no report measured."""
    out, d, codex = review_repo(PASS, implementer="gpt-6-luna")
    _run_review(out, d, codex)
    assert d.handoff(out, "7-widget", implementer="claude-opus-5") == 3
    assert "measured every implementing model" in capsys.readouterr().err
    assert "REVIEW work=7" not in "\n".join(p.read_text() for p in (out / ".process-work/journal").glob("**/*.md"))


def test_a_codex_session_reads_every_anchor_and_the_local_policy(render, tmp_path):
    """F3: AGENTS.md and CLAUDE.md both bind a Codex session; so do the project's Codex values."""
    out = render(tmp_path / "r", {"project_name": "d"})
    _git(out, "init", "-q", "-b", "main")
    (out / "AGENTS.md").write_text("agents anchor marker\n")
    (out / "CLAUDE.md").write_text("claude anchor marker\n")
    (out / "docs/process/model-policy.codex.local.json").write_text(json.dumps({"stale_minutes": 30}))
    run = [sys.executable, str(out / "scripts/process/rehydrate.py"), "--codex"]
    text = json.loads(subprocess.run(run, cwd=out, capture_output=True, text=True, check=True).stdout)[
        "hookSpecificOutput"]["additionalContext"]
    assert "agents anchor marker" in text and "claude anchor marker" in text
    assert "## Source: docs/process/model-policy.codex.local.json" in text


def test_a_codex_trace_that_cannot_be_read_costs_a_finding_not_the_table(review_repo, monkeypatch):
    """F4: any error in the Codex traces is a finding; the tower table still renders."""
    out, d, codex = review_repo(PASS)
    tower = importlib.import_module("tower")

    def broken(*_a):
        raise RuntimeError("trace unreadable")

    monkeypatch.setattr(tower, "codex_findings", broken)
    table = tower.build(out)
    assert any(f["kind"] == "local-findings-error" and "trace unreadable" in f["because"] for f in table["findings"])


def test_only_a_tracked_plan_with_appended_records_rides_a_review(review_repo):
    """F5: an untracked plan or a plan whose text changed is content, not a record."""
    out, d, codex = review_repo(PASS)
    plan = out / ".process-work/plans/2026-10-15-widget.md"
    committed = plan.read_text()
    plan.write_text(committed + "\nskipped ac-trace work=7: checked by hand\n")
    assert codex._records_appended(out, ".process-work/plans/2026-10-15-widget.md")
    plan.write_text(committed.replace("answer 42", "answer 43"))
    assert not codex._records_appended(out, ".process-work/plans/2026-10-15-widget.md")
    with pytest.raises(ValueError, match="clean worktree"):
        codex.binding(out, out / "no-bundle")
    plan.write_text(committed)
    (out / ".process-work/plans/2026-10-16-other.md").write_text(PLAN)
    assert not codex._records_appended(out, ".process-work/plans/2026-10-16-other.md")
    with pytest.raises(ValueError, match="clean worktree"):
        codex.binding(out, out / "no-bundle")


def test_a_refused_handoff_leaves_no_folder_it_made(review_repo):
    """F7: git status hides an empty folder; the handoff removes the ones it created."""
    unproven = {**PASS, "criteria": []}
    out, d, codex = review_repo(unproven)
    reviews = out / ".process-work/reviews"
    if reviews.exists():
        _git(out, "rm", "-rq", ".process-work/reviews")
        _git(out, "commit", "-qm", "chore: no reviews yet")
        _git(out, "push", "-q", "origin", "7-widget")
    _run_review(out, d, codex)
    assert d.handoff(out, "7-widget") == 1
    assert not reviews.exists()


@pytest.mark.parametrize("title", ["a\rb", "a b", "a\x0bb", "a\nb"])
def test_a_finding_renders_as_one_report_line(review_repo, title):
    """F8: every line separator splitlines knows would forge a second report line."""
    out, d, codex = review_repo(PASS)
    rec = _run_review(out, d, codex)
    bad = {**PASS, "findings": [{"sev": "minor", "action": "accept", "kind": "implementation", "issue": "-",
                                 "title": title}]}
    assert codex._validated(bad, rec) is None
    assert codex._validated({**PASS, "criteria": [f"AC-1: {title}"]}, rec) is None


def test_a_result_off_its_schema_at_handoff_is_the_way_out(review_repo, monkeypatch, capsys):
    """CR2: a completed run whose result the handoff cannot use records the way out."""
    out, d, codex = review_repo(PASS)
    _run_review(out, d, codex)
    monkeypatch.setattr(codex, "_validated", lambda *_a: None)
    assert d.handoff(out, "7-widget") == 3
    assert "codex unavailable" in capsys.readouterr().err
    assert (d._records_dir(out) / "codex" / codex.UNAVAILABLE).is_file()


def test_a_bad_codex_policy_names_its_own_file(mods):
    mod, out = mods
    d = mod("dispatch")
    (out / "docs/process/model-policy.codex.local.json").write_text(json.dumps({"stale_minutes": 0}))
    with pytest.raises(SystemExit, match="model-policy.codex.json"):
        d.load_policy(out, "codex")


def test_a_handoff_reads_the_families_at_the_base(review_repo):
    """F1 through the call site (delta review round 3): the branch under review adds its
    implementer as a family of its own; the attested review stays single-family."""
    out, d, codex = review_repo(PASS, implementer="gpt-6-luna")
    policy = out / "docs/process/model-policy.json"
    data = json.loads(policy.read_text())
    data["review_evidence"]["families"] = [*data["review_evidence"]["families"], "gpt-6-luna"]
    policy.write_text(json.dumps(data))
    _git(out, "commit", "-qam", "chore: luna is its own family")
    _git(out, "push", "-q", "origin", "7-widget")
    _run_review(out, d, codex)
    assert d.handoff(out, "7-widget") == 0
    journal = "\n".join(p.read_text() for p in (out / ".process-work/journal").glob("**/*.md"))
    assert "single-family" in journal and "cross-model" not in journal
