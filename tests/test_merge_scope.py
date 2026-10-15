"""#226 (ported from Kenni #2587/#2603/#2604/#2586): the merge certificate names
the stages the merge suite ran — a narrower run never satisfies a fuller one, an
unknown scope certifies nothing — and the train records how long each stage took."""
import ast
import importlib
import json
import subprocess
import sys

import pytest

sys.dont_write_bytecode = True

SCOPE_ALL = [sys.executable, "-c", "print('test-frontend test-boundary')"]
SCOPE_BACKEND = [sys.executable, "-c", "print('test-boundary')"]
MODULES = ("certificate", "train", "test_select", "testing_config", "finish", "process_git",
           "check_review", "dispatch", "report", "gate_invoke", "lane", "merge_route", "tower")


@pytest.fixture
def process(render, tmp_path):
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


def _git(root, *args):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True).stdout


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q", "-b", "main")
    _git(r, "config", "user.email", "t@t")
    _git(r, "config", "user.name", "t")
    (r / "a.txt").write_text("x\n")
    _git(r, "add", "-A")
    _git(r, "commit", "-qm", "base")
    return r


def _stage_dir(repo):
    from pathlib import Path
    folder = Path(_git(repo, "rev-parse", "--absolute-git-dir").strip()) / "merge-suite"
    folder.mkdir(exist_ok=True)
    return folder


def _stages_file(repo, content):
    (_stage_dir(repo) / "stages").write_text(content + "\n")


# --- the evidence seam ----------------------------------------------------------------

def test_the_evidence_carries_the_scope_and_a_narrower_run_never_satisfies(process, repo):
    mod, _out = process
    certificate = mod("certificate")
    narrow = certificate.merge_evidence(repo, "make test-merge", SCOPE_BACKEND)
    full = certificate.merge_evidence(repo, "make test-merge", SCOPE_ALL)
    assert narrow == "make test-merge\nscope=test-boundary"
    assert full == "make test-merge\nscope=test-boundary test-frontend"
    # no merge_scope: the suite alone, as before the seam — existing certificates still match
    assert certificate.merge_evidence(repo, " make test-merge ", None) == "make test-merge"
    ok, why = certificate.write(repo, "merge", narrow, before_tree=certificate.evidence_tree(repo), writer="t")
    assert ok, why
    assert certificate.find(repo, ("merge",), {"merge": narrow}) is not None
    assert certificate.find(repo, ("merge",), {"merge": full}) is None


def test_an_unknown_scope_never_certifies(process, repo):
    mod, _out = process
    certificate, train = mod("certificate"), mod("train")
    for broken in (["false"], [sys.executable, "-c", "print('')"], ["no-such-command-226"]):
        assert certificate.merge_evidence(repo, "s", broken) is None
    assert certificate.merge_evidence(repo, "s", SCOPE_ALL, ran_stages=[]) is None
    _stages_file(repo, "")
    logged = []
    train._certify_merge(repo, "s", certificate.evidence_tree(repo), [], logged.append, SCOPE_ALL)
    assert any("scope of the run is unknown" in line for line in logged)
    assert certificate.find(repo, ("merge",), {"merge": "s"}) is None


def test_the_writer_takes_the_scope_from_the_run_never_recomputes(process, repo):
    mod, _out = process
    certificate, train = mod("certificate"), mod("train")
    _stages_file(repo, "test-boundary")
    train._certify_merge(repo, "s", certificate.evidence_tree(repo), [], lambda _m: None, SCOPE_ALL)
    assert certificate.find(repo, ("merge",), {"merge": "s\nscope=test-boundary"}) is not None
    assert certificate.find(repo, ("merge",), {"merge": "s\nscope=test-boundary test-frontend"}) is None


def test_a_configured_scope_without_its_stages_file_writes_no_certificate(process, repo):
    mod, _out = process
    certificate, train = mod("certificate"), mod("train")
    assert certificate.run_stages(repo) is None
    logged = []
    train._certify_merge(repo, "s", certificate.evidence_tree(repo), [], logged.append, SCOPE_ALL)
    assert any("scope of the run is unknown" in line for line in logged)
    for evidence in ("s", "s\nscope=test-boundary test-frontend"):
        assert certificate.find(repo, ("merge",), {"merge": evidence}) is None


def test_run_evidence_table(process, repo):
    mod, _out = process
    certificate = mod("certificate")
    assert certificate.run_evidence(repo, "s", None) == "s"
    assert certificate.run_evidence(repo, "s", SCOPE_ALL) is None  # no stages file
    _stages_file(repo, "")
    assert certificate.run_evidence(repo, "s", SCOPE_ALL) is None  # empty
    stages = _stage_dir(repo) / "stages"
    stages.unlink()
    stages.mkdir()  # a directory, not a file
    assert certificate.run_evidence(repo, "s", SCOPE_ALL) is None
    stages.rmdir()
    _stages_file(repo, "test-boundary")
    assert certificate.run_evidence(repo, "s", SCOPE_ALL) == "s\nscope=test-boundary"
    assert certificate.run_evidence(repo, "s", None) == "s"


def test_finish_without_the_stages_file_writes_no_certificate(process, repo, monkeypatch):
    mod, _out = process
    certificate, finish = mod("certificate"), mod("finish")
    (repo / "docs/process").mkdir(parents=True)
    (repo / "docs/process/testing.local.json").write_text(
        json.dumps({"merge_suite": "true", "merge_scope": SCOPE_ALL, "stacks": {}}))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "cfg")
    monkeypatch.setattr(finish, "ROOT", repo)
    monkeypatch.setattr(finish, "check", lambda _root: ([], []))
    monkeypatch.delenv("PROCESS_MERGE_ROUTE", raising=False)
    got = finish._certifiable_tree(repo, "true")
    assert got is not None and got[3] == SCOPE_ALL
    finish.apply(repo, tests="true", tests_passed=False)  # the push fails without a remote
    for evidence in ("true", "true\nscope=test-boundary test-frontend"):
        assert certificate.find(repo, ("merge",), {"merge": evidence}) is None


def test_writers_never_recompute_and_one_owner_spells_the_scope(process):
    mod, out = process

    def merge_evidence_calls(tree, inside):
        found = []
        for node in ast.iter_child_nodes(tree):
            here = inside or (isinstance(node, ast.FunctionDef) and node.name == "_suite_key")
            if isinstance(node, ast.Call):
                f = node.func
                if (f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")) == "merge_evidence" \
                        and not here:
                    found.append(node.lineno)
            found += merge_evidence_calls(node, here)
        return found

    for name in ("train.py", "finish.py"):
        tree = ast.parse((out / "scripts/process" / name).read_text())
        assert merge_evidence_calls(tree, False) == [], name
        assert "run_evidence" in {getattr(n.func, "attr", getattr(n.func, "id", ""))
                                  for n in ast.walk(tree) if isinstance(n, ast.Call)}, name
    spelled = [p.name for p in (out / "scripts/process").glob("*.py") if "\\nscope=" in p.read_text()]
    assert spelled == ["certificate.py"]


def test_a_scope_mismatch_is_a_miss(process, repo):
    mod, _out = process
    certificate, select, train = mod("certificate"), mod("test_select"), mod("train")
    cfg = {"merge_suite": "s", "merge_scope": SCOPE_ALL}
    assert select.merge_certificate_evidence(repo, cfg) == "s\nscope=test-boundary test-frontend"
    _stages_file(repo, "test-boundary")
    train._certify_merge(repo, "s", certificate.evidence_tree(repo), [], lambda _m: None, SCOPE_BACKEND)
    narrow = select.merge_certificate_evidence(repo, {**cfg, "merge_scope": SCOPE_BACKEND})
    assert certificate.find(repo, ("merge",), {"merge": narrow}) is not None
    assert certificate.find(repo, ("merge",), {"merge": select.merge_certificate_evidence(repo, cfg)}) is None


def test_the_suite_memo_includes_the_scope(process, repo):
    mod, _out = process
    train = mod("train")
    key_all = train._suite_key(repo, "s", SCOPE_ALL)
    key_narrow = train._suite_key(repo, "s", SCOPE_BACKEND)
    assert key_all and key_narrow and key_all != key_narrow
    assert train._suite_key(repo, "s", ["false"]) == ""  # an unknown scope: no memo
    # without a scope the key is the one the template wrote before the seam
    certificate = mod("certificate")
    tree = _git(repo, "rev-parse", "HEAD^{tree}").strip()
    assert train._suite_key(repo, "s") == f"{tree} {certificate.evidence_hash('s')}"


def test_the_config_accepts_merge_scope_as_argv(process):
    mod, _out = process
    config = mod("testing_config")
    base = {"merge_suite": "s", "stacks": {}}
    assert config.parse({**base, "merge_scope": ["python3", "x.py"]})["merge_scope"] == ["python3", "x.py"]
    assert config.parse(base)["merge_scope"] is None
    with pytest.raises(config.ConfigError):
        config.parse({**base, "merge_scope": "python3 x.py"})


# --- stage times -----------------------------------------------------------------------

def test_stage_times_green_red_and_skipped(process, repo):
    mod, _out = process
    train = mod("train")
    folder = _stage_dir(repo)
    (folder / "stages").write_text("test-frontend test-boundary test-x\n")
    (folder / "test-frontend.time").write_text("1000 1412 0\n")
    (folder / "test-boundary.time").write_text("1000 1100 1\n")
    stages, log = {}, []
    train._collect_stage_times(repo, stages, set(), log.append)
    assert stages["test-frontend"]["state"] == "green" and stages["test-frontend"]["seconds"] == 412
    assert stages["test-boundary"]["state"] == "red"
    assert stages["test-x"]["state"] == "skipped" and stages["test-x"]["runs"] == 0
    assert any(line.startswith("stage test-frontend: green 412 s") for line in log)


def test_stage_times_count_a_run_once_and_a_skip_never_overwrites(process, repo):
    mod, _out = process
    train = mod("train")
    folder = _stage_dir(repo)
    (folder / "stages").write_text("test-frontend\n")
    (folder / "test-frontend.time").write_text("1000 1412 0\n")
    stages, seen = {}, set()
    train._collect_stage_times(repo, stages, seen, lambda _l: None)
    train._collect_stage_times(repo, stages, seen, lambda _l: None)
    assert stages["test-frontend"]["runs"] == 1
    (folder / "test-frontend.time").unlink()  # the retry did not run the green stage again
    train._collect_stage_times(repo, stages, seen, lambda _l: None)
    assert stages["test-frontend"]["state"] == "green" and stages["test-frontend"]["seconds"] == 412


def test_stage_times_last_state_wins_and_seconds_add_up(process, repo):
    mod, _out = process
    train = mod("train")
    folder = _stage_dir(repo)
    (folder / "stages").write_text("test-boundary\n")
    stages, seen = {}, set()
    (folder / "test-boundary.time").write_text("1000 1100 1\n")
    train._collect_stage_times(repo, stages, seen, lambda _l: None)
    (folder / "test-boundary.time").write_text("1200 1500 0\n")
    train._collect_stage_times(repo, stages, seen, lambda _l: None)
    assert stages["test-boundary"] == {**stages["test-boundary"], "state": "green", "seconds": 400, "runs": 2}


def test_a_bad_marker_costs_a_kpi_never_the_train(process, repo):
    """Refute: a marker past the platform's time range raised after a green suite."""
    mod, _out = process
    train = mod("train")
    folder = _stage_dir(repo)
    (folder / "stages").write_text("a b\n")
    (folder / "a.time").write_text("99999999999999999 99999999999999999 0\n")
    (folder / "b.time").write_text("1500 1000 0\n")  # ends before it starts
    stages = {}
    train._collect_stage_times(repo, stages, set(), lambda _l: None)
    assert stages["a"]["state"] == stages["b"]["state"] == "skipped"


def test_undecodable_scope_output_is_an_unknown_scope(process, repo):
    mod, _out = process
    certificate = mod("certificate")
    garbage = [sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'\\xff\\xfe')"]
    assert certificate.merge_evidence(repo, "s", garbage) is None
    (_stage_dir(repo) / "stages").write_bytes(b"\xff\xfe\n")
    assert certificate.run_stages(repo) is None
    assert certificate.run_evidence(repo, "s", SCOPE_ALL) is None


def test_a_leftover_stages_file_certifies_nothing(process, repo, monkeypatch):
    """Plan review / refute: a wider `stages` an earlier run left certified a run that
    wrote none — the writers clear it before the suite starts."""
    mod, _out = process
    certificate, finish = mod("certificate"), mod("finish")
    folder = _stage_dir(repo)
    (folder / "x.time").write_text("1 2 0\n")
    _stages_file(repo, "test-boundary test-frontend")
    certificate.clear_run(repo)
    assert not (folder / "stages").exists() and not (folder / "x.time").exists()
    certificate.clear_run(repo)  # nothing there: nothing to do
    (repo / "docs/process").mkdir(parents=True)
    (repo / "docs/process/testing.local.json").write_text(
        json.dumps({"merge_suite": "true", "merge_scope": SCOPE_ALL, "stacks": {}}))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "cfg")
    _stages_file(repo, "test-boundary test-frontend")
    monkeypatch.setattr(finish, "ROOT", repo)
    monkeypatch.setattr(finish, "check", lambda _root: ([], []))
    monkeypatch.delenv("PROCESS_MERGE_ROUTE", raising=False)
    finish.apply(repo, tests="true", tests_passed=False)  # `true` writes no stages
    assert certificate.find(repo, ("merge",), {"merge": "true\nscope=test-boundary test-frontend"}) is None


def test_the_memo_names_the_scope_that_ran(process, repo, monkeypatch, tmp_path):
    """Plan review / refute: a run the suite narrowed was remembered as a green of the
    predicted, fuller scope."""
    mod, _out = process
    train = mod("train")
    remembered = []
    monkeypatch.setattr(train, "_remember_green_suite", lambda _root, key: remembered.append(key))
    monkeypatch.setattr(train, "_run_gates", lambda w, log: True)
    monkeypatch.setattr(train, "_cleanup", lambda *a: None)
    monkeypatch.setattr(train, "_write", lambda *a, **k: None)
    monkeypatch.setattr(train, "build_train", lambda root, base, subset, stamp, log:
                        (repo, "train/x", list(subset), []))
    for ran, kept in (("test-boundary", False), ("test-frontend test-boundary", True)):
        remembered.clear()
        monkeypatch.setattr(train, "_sh", lambda cwd, cmd, log, *a, ran=ran: _stages_file(repo, ran) or "green")
        p = {"base": "main", "candidates": [{"branch": "b1", "hours_waiting": 1}]}
        with pytest.raises(SystemExit):  # the stub train/x cannot be fast-forwarded; the judging is done
            train._run_batch(repo, "main", p, ["b1"], "x", tmp_path / "t.log", suite="s", deploy=None,
                             push=False, keep_branches=True, merge_scope=SCOPE_ALL)
        assert bool(remembered) is kept, (ran, remembered)


def test_without_a_stages_file_nothing_is_collected(process, repo):
    mod, _out = process
    stages = {}
    mod("train")._collect_stage_times(repo, stages, set(), lambda _l: None)
    assert stages == {}


def test_the_phases_line_carries_the_stages_and_kpis_read_them(process, repo, tmp_path, monkeypatch):
    mod, out = process
    train = mod("train")
    monkeypatch.setattr(train, "_train_dir", lambda root: tmp_path)
    stages = {"test-frontend": {"seconds": 412, "runs": 2, "state": "green", "start": None, "end": None},
              "test-boundary": {"seconds": 0, "runs": 0, "state": "skipped", "start": None, "end": None}}
    train._record_phases(tmp_path, "20261015-1000", {}, "green", [], lambda line: None, None, stages)
    train._record_phases(tmp_path, "20261015-0900", {}, "green", [], lambda line: None, None, None)
    rows = [json.loads(ln) for ln in (tmp_path / train.PHASES_FILE).read_text().splitlines()]
    assert rows[0]["stages"] == stages and rows[1]["stages"] == {}
    kpis = mod("process_kpis")
    lines = kpis._stage_lines([rows[1], rows[0]])
    assert any("stage test-frontend" in ln and "6.9 min green (2 runs)" in ln for ln in lines), lines
    assert any("stage test-boundary" in ln and ln.endswith("skipped") for ln in lines), lines
    assert kpis._stage_lines([rows[1]]) == ["  no stage times recorded yet"]
