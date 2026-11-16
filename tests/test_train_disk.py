"""v2.98 B1 (#425): a full disk is no red passenger on the train.

The train checks the disks it writes to (`process_git.disk_use`: the one under its worktrees,
the temp dir's) before every rebuild, before every judge and around every suite run. Over the
limit: `DiskFull`, nobody blamed, nothing merged (`red_path` "disk-full"). A red run that left
a disk over the limit is an abort (`disk-full <path> <use>%`), repeated without a wait for the
load and without a fresh base."""
import collections
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from test_train import (_OUTCOME_CMD, _aborting, _branch, _git, _load_train, _phases, _preboard_run,
                        _probe_gone, _repo, _shape, _subsets, _train)

_Usage = collections.namedtuple("usage", "total used free")
_HIGH_LOAD = (64.0, 64.0, 64.0)  # a wait for the load would run its whole budget


def _disk(monkeypatch, full, *, limit: str = "90"):
    """Every filesystem reads 95 % used while `full()` holds, else 10 % — the train's reader
    is `process_git.disk_use` (`shutil.disk_usage`, one module for every importer)."""
    monkeypatch.setenv("PROCESS_DISK_LIMIT_PCT", limit)

    def usage(_path):
        pct = 95 if full() else 10
        return _Usage(100 * 2**30, pct * 2**30, (100 - pct) * 2**30)
    monkeypatch.setattr(shutil, "disk_usage", usage)


def _blocked(out: Path) -> bool:
    reports = out / ".git/process-tower/reports.jsonl"
    return reports.exists() and '"blocked"' in reports.read_text()


# --- the three check points -----------------------------------------------------------------

@pytest.mark.parametrize("step", ["worktree", "merge", "commit"])
def test_enospc_while_building_halts_disk_full_never_a_conflict(render, tmp_path, monkeypatch, step):
    """A disk that fills while the tree is built (`worktree add`, a merge, its commit) is no
    conflict and no crash: `DiskFull`, and nobody is dropped."""
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    _repo(out)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    train = _load_train(out)
    full = [False]
    _disk(monkeypatch, lambda: full[0])
    real_git = train._git
    op = {"worktree": ("worktree", "add"), "merge": ("merge", "--no-ff"), "commit": ("commit", "-q")}[step]

    def git(root, *args, **kw):
        if args[:2] == op:
            full[0] = True
            r = subprocess.CompletedProcess(args, 128, "", "fatal: write error: No space left on device")
            if kw.get("check"):
                raise SystemExit("train: git failed:\nNo space left on device")
            return r
        return real_git(root, *args, **kw)
    monkeypatch.setattr(train, "_git", git)
    logged: list[str] = []
    with pytest.raises(train.DiskFull) as got:
        train.build_train(out, "main", ["alpha"], "x", logged.append)
    assert str(got.value).startswith("disk-full ") and str(got.value).endswith("95%"), got.value
    assert not any("conflict" in line or "dropped" in line for line in logged), logged


def test_a_merge_that_fails_on_a_free_disk_stays_a_conflict(render, tmp_path, monkeypatch):
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    _repo(out)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    train = _load_train(out)
    _disk(monkeypatch, lambda: False)
    real_git = train._git
    monkeypatch.setattr(train, "_git", lambda root, *a, **k: subprocess.CompletedProcess(a, 1, "", "CONFLICT")
                        if a[:2] == ("merge", "--no-ff") else real_git(root, *a, **k))
    logged: list[str] = []
    _wt, _br, merged, dropped = train.build_train(out, "main", ["alpha"], "x", logged.append)
    assert merged == [] and dropped == ["alpha"] and any("conflict: alpha dropped" in x for x in logged)


def test_a_full_disk_before_the_build_touches_no_worktree(render, tmp_path, monkeypatch):
    """Check point (a): after the old tree is gone, before `worktree add` — nothing is built."""
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    _repo(out)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    train = _load_train(out)
    _disk(monkeypatch, lambda: True)
    with pytest.raises(train.DiskFull) as got:
        train.build_train(out, "main", ["alpha"], "x", lambda line: None)
    # measured at the nearest directory that exists: `<root>-train` is not there yet
    assert str(got.value) == f"disk-full {out.parent} 95%", got.value
    assert not (out.parent / f"{out.name}-train").exists()
    assert "train/x" not in _git(out, "branch", "--list", "--format=%(refname:short)").stdout.split()


def test_enospc_in_a_merge_through_run_blames_nobody(render, tmp_path, monkeypatch, capsys):
    """Through `run()`: the round ends `disk-full`, result `environment`, no `blocked`, main and
    the branch untouched — not "blocked: merge conflict", not `aborted`."""
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    _repo(out)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    head = _git(out, "rev-parse", "main").stdout
    train = _load_train(out)
    full = [False]
    _disk(monkeypatch, lambda: full[0])
    real_git = train._git

    def git(root, *args, **kw):
        if args[:2] == ("merge", "--no-ff"):
            full[0] = True
            return subprocess.CompletedProcess(args, 128, "", "fatal: No space left on device")
        return real_git(root, *args, **kw)
    monkeypatch.setattr(train, "_git", git)
    rc = train.run(out, suite="true", deploy=None, push=False, min_candidates=1, max_wait_hours=0,
                   force=True, keep_branches=True, dry_run=False)
    err = capsys.readouterr().err
    assert rc == 1 and "nobody is blamed" in err and "disk-full" in err, err
    row = _phases(out)[-1]
    assert row["result"] == "environment" and [x["red_path"] for x in row["rounds"]] == ["disk-full"], row
    assert row["rounds"][0]["disk_full"].startswith("disk-full "), row
    assert not _blocked(out) and "conflict" not in err
    assert _git(out, "rev-parse", "main").stdout == head
    assert "alpha" in _git(out, "branch", "--list", "--format=%(refname:short)").stdout.split()


def test_a_gate_on_a_full_disk_is_disk_full_not_a_red_main(render, tmp_path, monkeypatch):
    """Check point (b): `judge` checks before the preflight and the gates — a gate that would
    fail on ENOSPC never runs, and the base is never read red."""
    _disk(monkeypatch, lambda: True)
    gates: list[int] = []

    def gate_seq():
        while True:
            gates.append(1)
            yield False
    r = _aborting(render, tmp_path, monkeypatch, via_run=True, gates=gate_seq(), sh=lambda sub, cmd, nth: "green")
    assert r.rc == 1 and r.written == [] and gates == [], (r.err, gates)
    assert r.phases["result"] == "environment" and [x["red_path"] for x in r.measure["rounds"]] == ["disk-full"]
    assert "main is red" not in r.err and "integration branch itself is red" not in r.err, r.err


def test_a_full_disk_before_the_gates_retry_halts(render, tmp_path, monkeypatch):
    """The gates were red on the first tree; the disk is full before their retry on the same
    tree: `DiskFull`, the retry never runs."""
    log = tmp_path / "t.log"
    _disk(monkeypatch, lambda: log.exists() and "retry of the same combined tree: gates" in log.read_text())
    gates: list[int] = []

    def gate_seq():
        while True:
            gates.append(1)
            yield len(gates) > 1
    r = _aborting(render, tmp_path, monkeypatch, n=1, gates=gate_seq(), sh=lambda sub, cmd, nth: "green")
    assert isinstance(r.raised, r.train.DiskFull) and r.written == [], r.err
    assert gates == [1] and r.calls == [], (gates, r.calls)  # neither the gates nor the suite ran again


def test_a_full_disk_before_the_failed_retry_halts(render, tmp_path, monkeypatch):
    """Check point (c) covers the `--retry` run in the same tree: `DiskFull` before it."""
    log = tmp_path / "t.log"
    _disk(monkeypatch, lambda: log.exists() and "retry of the same combined tree: failed" in log.read_text())
    r = _aborting(render, tmp_path, monkeypatch, n=1, retry="make retry", sh=lambda sub, cmd, nth: "red")
    assert isinstance(r.raised, r.train.DiskFull) and r.written == [], r.err
    assert [cmd for _s, cmd in r.calls] == ["s"], r.calls  # `make retry` never ran


def test_a_full_disk_in_a_bisect_probe_halts_and_reports_the_earlier_drop(render, tmp_path, monkeypatch):
    """Round 1 drops b1 for a real red; in round 2 the disk is full before the probe [b2]:
    `DiskFull`, nobody else blamed, and b1 still gets its report."""
    full = [False]
    _disk(monkeypatch, lambda: full[0])

    def on_build(subset):
        full[0] = subset == ["b2"]

    def sh(sub, cmd, nth):
        return "red" if "b1" in sub or sub == ("b2", "b3") else "green"
    r = _aborting(render, tmp_path, monkeypatch, n=3, via_run=True, on_build=on_build, sh=sh)
    assert r.rc == 1 and r.written == [("blocked", "b1")], (r.written, r.err)
    assert [x["red_path"] for x in r.measure["rounds"]] == ["dropped:b1", "disk-full"], r.measure
    assert r.phases["result"] == "environment" and r.phases["branches"] == []


@pytest.mark.parametrize("where", ["base", "once more"])
def test_a_full_disk_before_the_base_or_the_run_once_more_blames_nobody(render, tmp_path, monkeypatch, where):
    """A full disk before a run: before the base the search would ask, and before the run
    once more after a fresh green base (v2.95) — `DiskFull`, nobody blamed."""
    builds: list[list[str]] = []
    _disk(monkeypatch, lambda: bool(builds) and (builds[-1] == [] if where == "base" else len(builds) >= 4))
    if where == "base":
        sh = lambda sub, cmd, nth: "red"  # noqa: E731
    else:
        sh = lambda sub, cmd, nth: "abort" if sub else "green"  # noqa: E731
    r = _aborting(render, tmp_path, monkeypatch, n=1, on_build=builds.append, sh=sh)
    assert isinstance(r.raised, r.train.DiskFull) and r.written == [], (r.raised, r.err)
    if where == "base":
        assert _subsets(r) == [("b1",), ("b1",)]  # the first run and its retry, no base
    else:
        assert _subsets(r) == [("b1",), ("b1",), ()]  # aborted twice, the fresh base; not once more


def test_a_full_disk_in_the_preboard_halts_before_boarding(render, tmp_path, monkeypatch, capsys):
    """A `DiskFull` in the preboard (its candidate probe here) escapes `pre_board`: the train
    stops before boarding, the round it began ends `disk-full`, the probe tree is gone."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    train = _load_train(out)
    builds: list[int] = []
    real_build = train.build_train
    monkeypatch.setattr(train, "build_train", lambda *a, **k: builds.append(1) or real_build(*a, **k))
    _disk(monkeypatch, lambda: len(builds) >= 2)  # the base probe built and ran green, then full
    rc, built, writes = _preboard_run(train, out, monkeypatch, preboard="true")
    err = capsys.readouterr().err
    assert rc == 1 and writes == [] and "disk-full" in err, err
    assert [subset for subset, _wt in built] == [[], ["alpha"]], built  # never the train's own build
    row = _phases(out)[-1]
    assert row["result"] == "environment" and [x["red_path"] for x in row["rounds"]] == ["disk-full"], row
    assert "preboard_checks" in row and _probe_gone(out)


def test_a_host_over_the_limit_halts_the_real_train(render, tmp_path, monkeypatch):
    """End to end on the host's real disk, the limit at 0.001 %: every disk is over it — the
    train halts `disk-full` before its first build, with and without the preboard."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    head = _git(out, "rev-parse", "main").stdout
    monkeypatch.setenv("PROCESS_DISK_LIMIT_PCT", "0.001")
    for extra in ((), ("--preboard", "true")):
        r = _train(out, "run", "--force", "--suite", "true", *extra)
        assert r.returncode == 1 and "disk-full" in r.stderr and "nobody is blamed" in r.stderr, r.stderr
        row = _phases(out)[-1]
        assert row["result"] == "environment" and [x["red_path"] for x in row["rounds"]] == ["disk-full"], row
        assert ("preboard_checks" in row) == bool(extra)
    assert _git(out, "rev-parse", "main").stdout == head and not _blocked(out)
    branches = _git(out, "branch", "--list", "--format=%(refname:short)").stdout.split()
    assert "alpha" in branches and not [b for b in branches if b.startswith("train/")], branches
    assert not (out.parent / f"{out.name}-train").exists()


def _enospc_on(monkeypatch, *names: str) -> None:
    """`Path.open` raises ENOSPC for the train's files named `names` (`*.log`: every run log)."""
    import errno
    import fnmatch
    real_open = Path.open

    def opened(self, *a, **k):
        if self.parent.name == "process-train" and any(fnmatch.fnmatch(self.name, n) for n in names):
            raise OSError(errno.ENOSPC, "No space left on device", str(self))
        return real_open(self, *a, **k)
    monkeypatch.setattr(Path, "open", opened)


@pytest.mark.parametrize("lost", [("*.log",), ("*.log", "phases.jsonl")])
def test_a_disk_too_full_for_the_trains_own_log_still_halts_disk_full(render, tmp_path, monkeypatch, capsys,
                                                                       lost):
    """Refute v2.98 (BLOCKER): at 100 % the train's own log line (the departure record, the
    halt's line, `_record_phases`' line) raised ENOSPC before `DiskFull` — the round ended
    `aborted` and the `finally` raised again. Log and record writes are best effort: the run
    halts `disk-full`, says once that its log is lost, and a phases row it cannot write is
    said on stderr."""
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    _repo(out)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    train = _load_train(out)
    _disk(monkeypatch, lambda: True)
    _enospc_on(monkeypatch, *lost)
    rc = train.run(out, suite="true", deploy=None, push=False, min_candidates=1, max_wait_hours=0,
                   force=True, keep_branches=True, dry_run=False, suite_note="a deliberate exception")
    err = capsys.readouterr().err
    assert rc == 1 and "nobody is blamed" in err and "disk-full" in err, err
    assert err.count("cannot be written") == 1, err  # said once, not per line
    assert not list((out / ".git/process-train").glob("2*.log"))
    if "phases.jsonl" in lost:
        assert "phases row" in err and "not written" in err and not _phases(out), err
    else:
        row = _phases(out)[-1]
        assert row["result"] == "environment" and [x["red_path"] for x in row["rounds"]] == ["disk-full"], row


# --- after a red run: the disk tells an abort from a finding --------------------------------

def test_a_passenger_that_fills_the_disk_in_its_tree_is_found_without_a_wait(render, tmp_path, monkeypatch):
    """b2's tests fill the disk in its tree: the red run is an abort (`disk-full`), repeated at
    once (no wait for the load: under a high load the fake `_abort_sleep` would book its
    whole budget as `abort_wait`), the rebuild frees the disk,
    the repeat fills it again — red without a fresh base, and the search finds b2."""
    full = [False]
    _disk(monkeypatch, lambda: full[0])

    def on_build(subset):
        full[0] = False  # the old tree is removed: its residue goes with it

    def sh(sub, cmd, nth):
        if "b2" in sub:
            full[0] = True
            return "red"
        return "green"
    r = _aborting(render, tmp_path, monkeypatch, load=_HIGH_LOAD, on_build=on_build, sh=sh)
    assert r.rc is None and r.written == [], r.err  # the stub train/x: judging done
    assert _subsets(r)[:4] == [("b1", "b2"), ("b1", "b2"), (), ("b1",)], _subsets(r)
    assert _shape(r.measure)[0] == ("dropped:b2", {"first": 1, "retry_abort": 1, "base": 1, "probe": 1})
    aborts = r.measure["rounds"][0]["aborts"]
    assert [(a["reason"].split()[0], a["wait_s"], a["ended"]) for a in aborts] == \
        [("disk-full", 0.0, "disk-full"), ("disk-full", 0.0, None)], aborts
    assert not r.phases.get("abort_wait"), r.phases
    assert "flaky" not in r.log.lower()


def test_a_disk_filled_from_outside_with_a_dispatch_test_aboard_blames_nobody(render, tmp_path, monkeypatch):
    """r2 M1: the disk fills from outside during the run; a passenger's test calls dispatch,
    which refuses and appends `disk-full <path> <use>%` to the marker. The repeat finds the disk
    still full before it runs: `DiskFull`, nobody blamed, no wait for the load."""
    full = [False]
    _disk(monkeypatch, lambda: full[0])
    probe = ("import sys; from pathlib import Path; sys.path.insert(0, 'scripts/process'); import dispatch; "
             "sys.exit(0 if dispatch.disk_refusal(Path('.')) is None else 1)")
    dispatch_test = f"PROCESS_DISK_LIMIT_PCT=0.001 {sys.executable} -B -c \"{probe}\""

    def sh(sub, cmd, nth):
        if "b2" in sub:
            full[0] = True  # someone else's files: no rebuild frees them
            return dispatch_test
        return "green"
    r = _aborting(render, tmp_path, monkeypatch, load=_HIGH_LOAD, via_run=True, sh=sh)
    assert r.rc == 1 and r.written == [], (r.written, r.err)
    assert _subsets(r) == [("b1", "b2")], _subsets(r)
    rnd = r.measure["rounds"][0]
    assert rnd["red_path"] == "disk-full" and rnd["aborts"][0]["reason"].startswith("disk-full . "), rnd
    assert not r.phases.get("abort_wait"), r.phases


@pytest.mark.parametrize("pct", ["below", "filled-and-cleaned"])
def test_a_disk_never_seen_over_the_limit_leaves_the_red_path_as_it_was(render, tmp_path, monkeypatch, pct):
    """Under the limit — or a suite that fills the disk and cleans up again, so nothing is
    measured over it: the red run stays red, the search as before."""
    monkeypatch.setenv("PROCESS_DISK_LIMIT_PCT", "90")
    monkeypatch.setattr(shutil, "disk_usage", lambda p: _Usage(100, 89, 11))
    sh = (lambda sub, cmd, nth: "red" if "b2" in sub else "green") if pct == "below" else \
        (lambda sub, cmd, nth: f"head -c 1 /dev/zero > big.bin; rm -f big.bin; {_OUTCOME_CMD['red']}"
         if "b2" in sub else "green")
    r = _aborting(render, tmp_path, monkeypatch, sh=sh)
    assert r.rc is None and r.written == [], r.err
    assert _shape(r.measure) == [("dropped:b2", {"first": 1, "retry_full": 1, "base": 1, "probe": 1}),
                                 ("green", {"first": 1})], _shape(r.measure)
    assert "aborts" not in r.measure["rounds"][0]


def test_a_misconfigured_limit_is_a_note_never_a_halt(render, tmp_path, monkeypatch):
    _disk(monkeypatch, lambda: True, limit="abc")
    r = _aborting(render, tmp_path, monkeypatch, n=1, sh=lambda sub, cmd, nth: "green")
    assert r.raised is None and r.written == [], r.err
    assert [x["red_path"] for x in r.measure["rounds"]] == ["green"]
    assert "PROCESS_DISK_LIMIT_PCT='abc' is no percentage" in r.log and "note" in r.log, r.log
    assert r.err.count("PROCESS_DISK_LIMIT_PCT='abc'") == 1, r.err  # said once, not per check


def test_the_base_aborting_on_a_full_disk_twice_stays_suite_aborted(render, tmp_path, monkeypatch):
    """No passenger rides on the base: its disk-full abort twice is `suite-aborted`, as v2.95."""
    full = [False]
    _disk(monkeypatch, lambda: full[0])

    def on_build(subset):
        full[0] = False

    def sh(sub, cmd, nth):
        if not sub:
            full[0] = True
        return "red"
    r = _aborting(render, tmp_path, monkeypatch, n=1, on_build=on_build, sh=sh)
    assert isinstance(r.raised, r.train.SuiteAborted) and not isinstance(r.raised, r.train.DiskFull), r.raised
    assert r.written == [] and _subsets(r) == [("b1",), ("b1",), (), ()]
