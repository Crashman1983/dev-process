"""v2.98 B1 (#425): a full disk is no red passenger on the train.

The train checks the disks it writes to (`process_git.disk_use`: the one under its worktrees,
the temp dir's) before every rebuild, before every judge and around every suite run. Under the
floor (v2.103, #446: less than `PROCESS_DISK_FLOOR_GB`, 2 GiB, free): `DiskFull`, nobody
blamed, nothing merged (`red_path` "disk-full"); over the percentage limit with room: one
warning per disk and run, and the train goes on. A red run whose disk was under the floor after
it or at its lowest during it is an abort (`disk-full <path> <use>% <free> GiB free`), repeated
without a wait for the load and without a fresh base."""
import collections
import shutil
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from test_train import (_OUTCOME_CMD, _aborting, _branch, _git, _load_train, _phases, _preboard_run,
                        _probe_gone, _repo, _shape, _subsets, _train)

_Usage = collections.namedtuple("usage", "total used free")
_HIGH_LOAD = (64.0, 64.0, 64.0)  # a wait for the load would run its whole budget


GIB = 2**30
_FULL = "99% 1.0 GiB free"  # the tail of the halt line on a disk `_disk` reads full


def _disk(monkeypatch, full, *, limit: str = "90", floor: str = "2", room: int = 90):
    """Every filesystem reads 99 % used, 1 GiB free — under the 2 GiB floor — while `full()`
    holds, else `room` GiB free of 100 (90: 10 %; 5: over the 90 % limit with room) — the
    train's reader is `process_git.disk_use` (`shutil.disk_usage`, one module for every importer)."""
    monkeypatch.setenv("PROCESS_DISK_LIMIT_PCT", limit)
    monkeypatch.setenv("PROCESS_DISK_FLOOR_GB", floor)

    def usage(_path):
        free = 1 if full() else room
        return _Usage(100 * GIB, (100 - free) * GIB, free * GIB)
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
    assert str(got.value).startswith("disk-full ") and str(got.value).endswith(_FULL), got.value
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
    assert str(got.value) == f"disk-full {out.parent} {_FULL}", got.value
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


def test_the_halt_names_the_temp_dir_and_the_tree_and_what_to_clear(render, tmp_path, monkeypatch, capsys):
    """Refute v2.98: the halt said only `tidy.py --apply`, which frees no test basetemp. It
    names the train's tree and the temp dir on the full disk, and what to clear there."""
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    _repo(out)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    tmp = tmp_path / "tmp"
    tmp.mkdir()
    monkeypatch.setenv("TMPDIR", str(tmp))
    train = _load_train(out)
    _disk(monkeypatch, lambda: True)
    rc = train.run(out, suite="true", deploy=None, push=False, min_candidates=1, max_wait_hours=0,
                   force=True, keep_branches=True, dry_run=False)
    err = capsys.readouterr().err
    assert rc == 1 and "nobody is blamed" in err, err
    assert f"the train's tree {out.parent / (out.name + '-train')}" in err, err
    assert f"the temp dir {tmp}" in err and f"old test basetemps under {tmp} (pytest-of-*" in err, err
    assert "tidy.py --apply" in err, err


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


def test_a_full_disk_before_the_final_merge_merges_nothing(render, tmp_path, monkeypatch):
    """DeepSeek F1: the batch is green, then the disk is full before the push and the
    fast-forward — `DiskFull`, nothing merged, nobody blamed (not a crash in `merge --ff-only`)."""
    full = [False]
    _disk(monkeypatch, lambda: full[0])

    def sh(sub, cmd, nth):
        full[0] = True  # the green run leaves the disk full: a judge saw it free before
        return "green"
    r = _aborting(render, tmp_path, monkeypatch, n=1, via_run=True, sh=sh)
    assert r.rc == 1 and r.written == [], (r.rc, r.err)
    assert r.phases["result"] == "environment" and r.phases["branches"] == [], r.phases
    assert [x["red_path"] for x in r.measure["rounds"]] == ["disk-full"], r.measure
    assert "nobody is blamed" in r.err and "fast-forwarded" not in r.log, r.err


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


def test_a_full_disk_before_the_preboards_preflight_halts_disk_full(render, tmp_path, monkeypatch, capsys):
    """DeepSeek F4: `bad` is red twice on the preboard, the base green again; the disk fills
    before the confirming preflight (which fails on ENOSPC) — `disk-full`, not `environment`,
    and `bad` is not reported."""
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    _repo(out)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    _branch(out, "bad", {"src/BROKEN": "x\n"})
    train = _load_train(out)
    count = tmp_path / "preboard-runs"
    count.write_text("")

    def runs() -> int:
        return len(count.read_text().splitlines())
    # base, alpha, bad, bad once more, the base again: full after the fifth run
    _disk(monkeypatch, lambda: runs() >= 5)
    check = f"echo x >> {count}; test ! -e src/BROKEN"
    preflight = f"test $(wc -l < {count}) -lt 5"  # red on the full disk, as ENOSPC would be
    rc, _built, writes = _preboard_run(train, out, monkeypatch, preboard=check, preflight=preflight)
    err = capsys.readouterr().err
    assert rc == 1 and writes == [] and runs() == 5, (err, writes)
    row = _phases(out)[-1]
    assert row["result"] == "environment" and [x["red_path"] for x in row["rounds"]] == ["disk-full"], row
    assert "the preflight" not in err and "disk-full" in err, err


def test_a_host_under_the_floor_halts_the_real_train(render, tmp_path, monkeypatch):
    """End to end on the host's real disk, the floor at 10^9 GiB: every disk is under it — the
    train halts `disk-full` before its first build, with and without the preboard."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    head = _git(out, "rev-parse", "main").stdout
    monkeypatch.setenv("PROCESS_DISK_FLOOR_GB", "1000000000")
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


def test_a_host_over_the_limit_with_room_warns_and_the_real_train_merges(render, tmp_path, monkeypatch):
    """#446: end to end, the limit at 0.001 % and no floor — every disk is over the limit, none
    is short of room: one warning (the tree and the temp dir share a disk here) naming the
    use, the free GiB and what to clear, and the batch merges."""
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    _repo(out)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    _git(out, "checkout", "-q", "main")
    tmp = tmp_path / "tmp"
    tmp.mkdir()
    monkeypatch.setenv("TMPDIR", str(tmp))
    monkeypatch.setenv("PROCESS_DISK_LIMIT_PCT", "0.001")
    monkeypatch.setenv("PROCESS_DISK_FLOOR_GB", "0")
    r = _train(out, "run", "--force", "--suite", "true")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "src/a.py" in _git(out, "ls-tree", "-r", "--name-only", "main").stdout.split()
    warnings = [x for x in r.stderr.splitlines() if x.startswith("train: warning — ")]
    assert len(warnings) == 1, r.stderr
    assert "% full (limit 0.001%" in warnings[0] and "GiB free" in warnings[0], warnings
    assert "tidy.py --apply" in warnings[0] and f"the temp dir {tmp}" in warnings[0], warnings
    assert "disk-full" not in r.stderr, r.stderr


def test_over_the_limit_with_room_warns_once_per_disk_and_run(render, tmp_path, monkeypatch, capsys):
    """#446: 95 % used, 5 GiB free — every check point reads it over the limit: one warning per
    disk on stderr and in the train's log, per run (the memo starts empty each run), and both
    runs merge."""
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    _repo(out)
    tmp = tmp_path / "tmp"
    tmp.mkdir()
    monkeypatch.setenv("TMPDIR", str(tmp))
    train = _load_train(out)
    _disk(monkeypatch, lambda: False, room=5)
    for name in ("alpha", "beta"):
        _branch(out, name, {f"src/{name}.py": "x\n"})
        _git(out, "checkout", "-q", "main")
        rc = train.run(out, suite="true", deploy=None, push=False, min_candidates=1, max_wait_hours=0,
                       force=True, keep_branches=False, dry_run=False)
        err = capsys.readouterr().err
        assert rc == 0, err
        assert f"src/{name}.py" in _git(out, "ls-tree", "-r", "--name-only", "main").stdout.split()
        warnings = [x for x in err.splitlines() if x.startswith("train: warning — ")]
        assert len(warnings) == 1, err
        assert "is 95% full (limit 90%" in warnings[0] and "5.0 GiB free" in warnings[0], warnings
        assert "PROCESS_DISK_FLOOR_GB" in warnings[0] and "tidy.py --apply" in warnings[0], warnings
    log = "".join(f.read_text() for f in (out / ".git/process-train").glob("2*.log"))
    assert "warning — " in log and "is 95% full" in log, log


@pytest.mark.parametrize("var", ["TMPDIR", "TEMP", "TMP"])
def test_the_temp_dir_is_read_from_the_environment_not_from_tempfile(render, tmp_path, monkeypatch, var):
    """Refute v2.98: `tempfile.gettempdir()` falls back to another dir when $TMPDIR's disk is
    full (its test write fails) and caches the answer — the full disk was never checked. The
    train reads TMPDIR, TEMP, TMP as Python does, without writing there."""
    import tempfile
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    train = _load_train(out)
    full_tmp, free = tmp_path / "full-tmp", tmp_path / "free"
    full_tmp.mkdir()
    free.mkdir()
    for name in ("TMPDIR", "TEMP", "TMP"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv(var, str(full_tmp))
    monkeypatch.setattr(tempfile, "tempdir", str(free))  # what a fallback left in the cache
    monkeypatch.setenv("PROCESS_DISK_LIMIT_PCT", "90")
    monkeypatch.setenv("PROCESS_DISK_FLOOR_GB", "2")
    monkeypatch.setattr(shutil, "disk_usage", lambda p: _Usage(100 * GIB, 99 * GIB, GIB) if Path(p) == full_tmp
                        else _Usage(100 * GIB, 10 * GIB, 90 * GIB))
    assert train._disk_full(free, lambda line: None) == f"disk-full {full_tmp} {_FULL}"
    assert sorted(p.name for p in full_tmp.iterdir()) == []  # nothing written to test it


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


def test_one_disk_full_beside_a_load_abort_still_asks_the_fresh_base(render, tmp_path, monkeypatch):
    """Refute v2.98: a load abort, then a repeat that left the disk full, was red at once — one
    `disk-full` observation blamed b2 without a fresh base. Only a run and a repeat that both
    filled the disk skip it; here the fresh base runs, and b2 runs once more."""
    full = [False]
    _disk(monkeypatch, lambda: full[0])
    seen: list[int] = []

    def on_build(subset):
        full[0] = False

    def sh(sub, cmd, nth):
        if "b2" not in sub:
            return "green"
        seen.append(1)
        if len(seen) == 1:
            return "abort"  # the load: a marker line
        if len(seen) == 2:
            full[0] = True  # its repeat leaves the disk full
            return "red"
        return "green"
    r = _aborting(render, tmp_path, monkeypatch, on_build=on_build, sh=sh)
    assert r.rc is None and r.written == [], r.err
    assert _subsets(r)[:4] == [("b1", "b2"), ("b1", "b2"), (), ("b1", "b2")], _subsets(r)
    assert not str(r.measure["rounds"][0]["red_path"]).startswith("dropped:"), r.measure
    assert "the base runs fresh" in r.log, r.log


def test_a_passenger_that_fills_the_disk_twice_is_found_where_the_base_has_no_suite(render, tmp_path,
                                                                                       monkeypatch):
    """DeepSeek F2: the base has no suite (`undefined`); a probe with b1 fills the disk on its run
    and its repeat — red, b1 dropped, not `SuiteAborted` (the disk branch comes before the
    `undefined` base's)."""
    full = [False]
    _disk(monkeypatch, lambda: full[0])

    def on_build(subset):
        full[0] = False

    def sh(sub, cmd, nth):
        if not sub:
            return "undefined"
        if "b1" in sub:
            full[0] = True
            return "red"
        return "green"
    r = _aborting(render, tmp_path, monkeypatch, on_build=on_build, sh=sh)
    assert r.raised is None and r.written == [], (r.raised, r.err)
    assert [x["red_path"] for x in r.measure["rounds"]] == ["dropped:b1", "green"], r.measure
    assert ("b1",) in _subsets(r), _subsets(r)  # the probe ran, and was judged
    assert "the disk filled on the run and on its repeat with b1 aboard" in r.log, r.log


def test_a_disk_filled_from_outside_with_a_dispatch_test_aboard_blames_nobody(render, tmp_path, monkeypatch):
    """r2 M1: the disk fills from outside during the run; a passenger's test calls dispatch,
    which refuses (under its floor) and appends `disk-full <path> …` to the marker. The repeat finds the disk
    still full before it runs: `DiskFull`, nobody blamed, no wait for the load."""
    full = [False]
    _disk(monkeypatch, lambda: full[0])
    probe = ("import sys; from pathlib import Path; sys.path.insert(0, 'scripts/process'); import dispatch; "
             "sys.exit(0 if dispatch.disk_refusal(Path('.')) is None else 1)")
    dispatch_test = f"PROCESS_DISK_FLOOR_GB=1000000000 {sys.executable} -B -c \"{probe}\""

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


@pytest.mark.parametrize("pct", ["below", "over-with-room", "filled-and-cleaned"])
def test_a_disk_never_seen_under_the_floor_leaves_the_red_path_as_it_was(render, tmp_path, monkeypatch, pct):
    """Under the limit, over it with room (#446: a warning) — or a suite that fills the disk and
    cleans up again between two samples, so nothing is measured under the floor: the red run
    stays red, the search as before."""
    monkeypatch.setenv("PROCESS_DISK_LIMIT_PCT", "90")
    monkeypatch.setenv("PROCESS_DISK_FLOOR_GB", "2")
    free = 5 if pct == "over-with-room" else 11
    monkeypatch.setattr(shutil, "disk_usage", lambda p: _Usage(100 * GIB, (100 - free) * GIB, free * GIB))
    sh = (lambda sub, cmd, nth: "red" if "b2" in sub else "green") if pct != "filled-and-cleaned" else \
        (lambda sub, cmd, nth: f"head -c 1 /dev/zero > big.bin; rm -f big.bin; {_OUTCOME_CMD['red']}"
         if "b2" in sub else "green")
    r = _aborting(render, tmp_path, monkeypatch, sh=sh)
    assert r.rc is None and r.written == [], r.err
    assert _shape(r.measure) == [("dropped:b2", {"first": 1, "retry_full": 1, "base": 1, "probe": 1}),
                                 ("green", {"first": 1})], _shape(r.measure)
    assert "aborts" not in r.measure["rounds"][0]
    if pct == "over-with-room":
        assert "is 95% full" in r.err and r.err.count("train: warning — ") <= 2, r.err  # per disk


@pytest.mark.parametrize("var", ["limit", "floor"])
@pytest.mark.parametrize("full", [False, True])
def test_a_misconfigured_bound_is_a_note_and_the_default_holds(render, tmp_path, monkeypatch, full, var):
    """Refute v2.98: a misconfigured limit turned the train's check off. It is a note, said
    once, and the defaults hold (r2 N4: the floor alike): 90 GiB free runs, 1 GiB halts
    `disk-full`."""
    _disk(monkeypatch, lambda: full, **{var: "abc"})
    r = _aborting(render, tmp_path, monkeypatch, n=1, sh=lambda sub, cmd, nth: "green")
    assert r.written == [], r.err
    if full:
        assert isinstance(r.raised, r.train.DiskFull) and str(r.raised).endswith(_FULL), r.raised
    else:
        assert r.raised is None and [x["red_path"] for x in r.measure["rounds"]] == ["green"]
    env = {"limit": "PROCESS_DISK_LIMIT_PCT='abc' is no percentage",
           "floor": "PROCESS_DISK_FLOOR_GB='abc' is no number"}[var]
    assert env in r.log and "note" in r.log, r.log
    assert r.err.count(env) == 1, r.err  # said once, not per check
    assert "checked against the default 90% and 2 GiB free" in r.err, r.err


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


# --- during the run: the lowest free space it saw (r3 P2-1..P2-3) ----------------------------

def _suite_tree(render, tmp_path, monkeypatch):
    """A rendered repo, the train loaded, samples every 20 ms, the temp dir beside it."""
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    _repo(out)
    train = _load_train(out)
    monkeypatch.setattr(train, "DISK_SAMPLE_S", 0.02)
    tmp = tmp_path / "tmp"
    tmp.mkdir()
    monkeypatch.setenv("TMPDIR", str(tmp))
    return out, train


def _watching(train):
    """True only for a sample of the run's watch thread: the check before the run and the
    measurement after it read the disk free."""
    return threading.current_thread().name == train.DISK_WATCH_THREAD


@pytest.mark.parametrize("marker", [True, False])
def test_a_red_run_whose_disk_ran_low_during_it_is_an_abort(render, tmp_path, monkeypatch, marker):
    """The suite fills the disk under the floor and cleans up before it ends: after the run the
    disk is free again, but a sample during it saw 1 GiB — the run measured nothing: aborted,
    the reason `disk-full …`, so `abort_rule` takes its disk branch. Also without a marker:
    that run is a suite run too."""
    out, train = _suite_tree(render, tmp_path, monkeypatch)
    if not marker:
        monkeypatch.setattr(train, "_abort_marker", lambda root, stamp: None)
    flag = tmp_path / "low"
    samples: list[int] = []
    _disk(monkeypatch, lambda: (samples.append(1) if _watching(train) else None) or flag.exists())
    logged: list[str] = []
    state, reason = train._marked_sh(out, "x", out, f"touch {flag}; sleep 0.4; rm -f {flag}; exit 1",
                                     logged.append)
    assert (state, reason.split()[0]) == ("aborted", "disk-full") and reason.endswith(_FULL), (state, reason)
    assert len(samples) >= 3, samples  # sampled again and again, not once
    assert any("at its lowest during the run" in line for line in logged), logged
    assert train.DISK_WATCH_THREAD not in {t.name for t in threading.enumerate()}


@pytest.mark.parametrize("outcome, want", [("red", "aborted"), ("undefined", "aborted"), ("green", "green")])
def test_the_lowest_sample_decides_a_red_or_undefined_run_never_a_green_one(render, tmp_path, monkeypatch,
                                                                             outcome, want):
    out, train = _suite_tree(render, tmp_path, monkeypatch)
    _disk(monkeypatch, lambda: _watching(train))
    state, reason = train._marked_sh(out, "x", out, _OUTCOME_CMD[outcome], lambda line: None)
    assert state == want, (state, reason)
    assert reason == ("" if want == "green" else f"disk-full {out} {_FULL}"), reason


def test_a_red_run_that_only_quotes_enospc_stays_red(render, tmp_path, monkeypatch):
    """r2 M3: pytest prints source lines, and both suites hold the string — the output is no
    measurement. A red run on a disk with room that prints `No space left on device` is red."""
    out, train = _suite_tree(render, tmp_path, monkeypatch)
    _disk(monkeypatch, lambda: False)
    cmd = "echo 'E   OSError: [Errno 28] No space left on device'; echo 'ENOSPC'; exit 1"
    assert train._marked_sh(out, "x", out, cmd, lambda line: None) == ("red", "")


def test_a_run_past_its_timeout_stops_the_watch(render, tmp_path, monkeypatch):
    """The early return of a killed run ends the watch too (its `finally`); the watch kills nothing."""
    out, train = _suite_tree(render, tmp_path, monkeypatch)
    _disk(monkeypatch, lambda: False)
    watch = train._DiskWatch(train._disk_paths(out))
    assert train._sh(out, "sleep 5", lambda line: None, 0.3, disk_watch=watch) == "red"
    assert train.DISK_WATCH_THREAD not in {t.name for t in threading.enumerate()}
    assert watch.low_line() is None and watch.lowest, watch.lowest


def test_a_green_memo_that_cannot_be_written_leaves_no_temp_file(render, tmp_path, monkeypatch):
    """On a full disk the memo's write fails: its `<name>.<pid>.tmp` is removed, not left per run."""
    from pathlib import Path as _P

    from test_train import _load_train, _repo
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    _repo(out)
    train = _load_train(out)
    real = _P.write_text

    def full(self, *a, **k):
        if self.name.endswith(".tmp"):
            real(self, "", encoding="utf-8")  # the inode exists, the bytes do not fit
            raise OSError(28, "No space left on device")
        return real(self, *a, **k)

    monkeypatch.setattr(_P, "write_text", full)
    train._remember_green_suite(out, train._suite_key(out, "s"))
    monkeypatch.setattr(_P, "write_text", real)
    assert not list(train._train_dir(out).glob("*.tmp"))


def test_a_watch_thread_that_cannot_start_costs_the_watch_never_the_run(render, tmp_path, monkeypatch):
    """Review v2.103 (Nit): kann der Mess-Thread nicht starten, läuft die Suite trotzdem und
    wird entschieden wie ohne Messung."""
    out, train = _suite_tree(render, tmp_path, monkeypatch)
    _disk(monkeypatch, lambda: False)

    def refuse(self):
        raise RuntimeError("can't start new thread")
    monkeypatch.setattr(threading.Thread, "start", refuse)
    assert train._marked_sh(out, "x", out, "exit 1", lambda line: None) == ("red", "")
