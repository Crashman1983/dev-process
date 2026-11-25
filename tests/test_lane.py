"""lane.py (#206): one bounded queue per host, shared with a project's own lane script."""
import importlib.util
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

PROC = Path(__file__).resolve().parents[1] / "template/scripts/process"
LANE = PROC / "lane.py"


def _load():
    before = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(PROC))
    try:
        spec = importlib.util.spec_from_file_location("lane_t", LANE)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        sys.path.remove(str(PROC))
        sys.dont_write_bytecode = before
    return mod


def _settings(tmp_path, **lanes):
    return {"dir": tmp_path / "lanes",
            "lanes": lanes or {"scoped": {"wait": 300.0, "nice": 0}, "full": {"wait": 3600.0, "nice": 10}}}


def _env(tmp_path):
    return {**os.environ, "PROCESS_LANE_DIR": str(tmp_path / "lanes"), "PYTHONDONTWRITEBYTECODE": "1",
            "HOME": str(tmp_path)}


def _holder(tmp_path, seconds=30):
    """A second process holding `scoped` until killed."""
    proc = subprocess.Popen([sys.executable, str(LANE), "run", "--lane", "scoped", "--label", "holder", "--",
                             sys.executable, "-c", f"import time; time.sleep({seconds})"],
                            cwd=tmp_path, env=_env(tmp_path))
    status = tmp_path / "lanes/test-lane-scoped.status"
    for _ in range(100):
        if status.exists():
            return proc
        time.sleep(0.05)
    proc.kill()
    raise AssertionError("holder never took the lane")


def test_a_lane_is_exclusive_across_processes_and_bounded(tmp_path, monkeypatch):
    mod = _load()
    monkeypatch.setenv("PROCESS_LANE_DIR", str(tmp_path / "lanes"))
    proc = _holder(tmp_path)
    try:
        with pytest.raises(mod.LaneBusy, match="scoped: held by pid .* — holder"):
            with mod.hold("scoped", wait=0.3, settings=_settings(tmp_path), quiet=True):
                pass
        r = subprocess.run([sys.executable, str(LANE), "wait", "--lane", "scoped", "--wait", "0.2", "--quiet"],
                           cwd=tmp_path, env=_env(tmp_path), capture_output=True, text=True)
        assert r.returncode == 75 and "nothing ran" in r.stderr, r.stderr
    finally:
        proc.kill()
        proc.wait()


def test_status_line_and_record_match_the_projects_own_lane_script(tmp_path):
    """Kenni's lane.py and this one share files and record keys: one lock per lane on a host."""
    proc = _holder(tmp_path)
    try:
        record = json.loads((tmp_path / "lanes/test-lane-scoped.status").read_text())
        assert set(record) == {"lane", "label", "pid", "started", "cwd", "branch"}
        r = subprocess.run([sys.executable, str(LANE), "status"], cwd=tmp_path, env=_env(tmp_path),
                           capture_output=True, text=True)
        lines = r.stdout.splitlines()
        assert lines[0].startswith("scoped: held by pid ") and "— holder" in lines[0], lines
        assert lines[1] == "full: free", lines
    finally:
        proc.kill()
        proc.wait()


def test_a_killed_holder_frees_the_lane(tmp_path):
    mod = _load()
    proc = _holder(tmp_path)
    proc.send_signal(signal.SIGKILL)
    proc.wait()
    with mod.hold("scoped", wait=5, settings=_settings(tmp_path), quiet=True):
        assert "held by" in mod.describe(tmp_path / "lanes", "scoped")
    assert mod.describe(tmp_path / "lanes", "scoped") == "scoped: free"


def test_a_hold_inside_a_hold_of_the_same_lane_passes_through(tmp_path):
    mod = _load()
    s = _settings(tmp_path)
    with mod.hold("scoped", wait=1, settings=s, quiet=True):
        with mod.hold("scoped", wait=0, settings=s, quiet=True):  # would be LaneBusy without the mark
            pass
        # a child process inherits the mark: a hook run under the lane does not wait for itself
        r = subprocess.run([sys.executable, str(LANE), "run", "--lane", "scoped", "--wait", "0", "--", "true"],
                           cwd=tmp_path, env={**_env(tmp_path)}, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        with mod.hold("full", wait=0, settings=s, quiet=True):  # another lane: its own lock, taken
            assert (tmp_path / "lanes/test-lane-full.status").exists()
    assert "PROCESS_LANE_HELD" not in os.environ


def test_without_fcntl_a_lane_runs_unqueued_and_says_so(tmp_path, monkeypatch, capsys):
    mod = _load()
    monkeypatch.setattr(mod, "_fcntl", lambda: None)
    with mod.hold("scoped", wait=0, settings=_settings(tmp_path)):
        pass
    assert "runs unqueued" in capsys.readouterr().err


def test_a_lane_with_nice_lowers_its_command(tmp_path):
    mod = _load()
    s = _settings(tmp_path)
    assert mod.niced(s, "full", ["make", "test"])[:3] == ["nice", "-n", "10"]
    assert mod.niced(s, "scoped", ["make", "test"]) == ["make", "test"]


def test_the_lane_dir_follows_env_then_config_then_state_dir(tmp_path, monkeypatch):
    mod = _load()
    root = tmp_path / "repo"
    (root / "docs/process").mkdir(parents=True)
    monkeypatch.delenv("PROCESS_LANE_DIR", raising=False)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    assert mod.config(root)["dir"] == tmp_path / "state/process-lanes"
    (root / "docs/process/testing.local.json").write_text(json.dumps({"lane_dir": str(tmp_path / "cfg")}))
    assert mod.config(root)["dir"] == tmp_path / "cfg"
    monkeypatch.setenv("PROCESS_LANE_DIR", str(tmp_path / "env"))
    assert mod.config(root)["dir"] == tmp_path / "env"


def test_a_relative_lane_dir_is_anchored_at_the_project_root(tmp_path, monkeypatch):
    """#448 (r3 P4-1): `lane_dir` relative to the root, as testing_config reads it — never to
    the cwd, or a give-up in a worktree names another directory than the train's."""
    mod = _load()
    root = tmp_path / "repo"
    (root / "docs/process").mkdir(parents=True)
    (root / "docs/process/testing.local.json").write_text(json.dumps({"lane_dir": "state/lanes"}))
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.delenv("PROCESS_LANE_DIR", raising=False)
    monkeypatch.chdir(elsewhere)
    assert mod.config(root)["dir"] == root / "state/lanes"


def test_a_malformed_configuration_queues_nothing(tmp_path):
    root = tmp_path / "repo"
    (root / "docs/process").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    (root / "docs/process/testing.local.json").write_text('{"lanes": {"scoped": {"wait": -1}}}')
    r = subprocess.run([sys.executable, str(LANE), "status"], cwd=root, env=_env(tmp_path),
                       capture_output=True, text=True)
    assert r.returncode == 2 and "lanes.scoped.wait" in r.stderr, r.stderr


def _load_config():
    before = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(PROC))
    try:
        spec = importlib.util.spec_from_file_location("testing_config_t", PROC / "testing_config.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        sys.path.remove(str(PROC))
        sys.dont_write_bytecode = before
    return mod


def test_lane_readers_use_the_projects_own_script_then_the_template_one(tmp_path):
    """The tower, the train and dispatch read one source of lane lines."""
    import shutil
    cfg = _load_config()
    root = tmp_path / "repo"
    (root / "scripts/process").mkdir(parents=True)
    env = {**os.environ, "PROCESS_LANE_DIR": str(tmp_path / "lanes"), "PYTHONDONTWRITEBYTECODE": "1"}
    for name in ("lane.py", "testing_config.py", "process_git.py"):  # what lane.py imports
        shutil.copy(PROC / name, root / "scripts/process" / name)
    assert cfg.lane_status(root, env) == []  # no test configuration: no lanes shown
    (root / "docs/process").mkdir(parents=True)
    (root / "docs/process/testing.local.json").write_text("{}")
    assert cfg.lane_status(root, env) == ["scoped: free", "full: free"]
    (root / "scripts/lane.py").write_text("print('scoped: held by pid 1 — own (b) since 09:00 (1 min)')\n")
    assert cfg.lane_status(root, env) == ["scoped: held by pid 1 — own (b) since 09:00 (1 min)"]


def _encoded(where: Path) -> str:
    import urllib.parse
    return urllib.parse.quote(str(where.resolve()), safe="/")


def test_a_caught_lane_busy_writes_no_line_and_a_real_give_up_writes_its_dir(tmp_path, monkeypatch):
    """#448: `hold` raises LaneBusy and writes nothing — a caller that takes another lane gave
    nothing up. `give_up` writes `lane-busy <lane> dir=<resolved, percent-encoded> <holder>`
    inside the train's run only; `lane.py run` and `wait` call it on their own give-up."""
    mod = _load()
    marker = tmp_path / "marker"
    marker.write_text("")
    lanes = tmp_path / "lanes"
    monkeypatch.setenv("PROCESS_LANE_DIR", str(lanes))
    monkeypatch.setenv("PROCESS_SUITE_ABORT", str(marker))
    proc = _holder(tmp_path)
    try:
        with pytest.raises(mod.LaneBusy) as busy:
            with mod.hold("scoped", wait=0, settings=_settings(tmp_path), quiet=True):
                pass
        assert marker.read_text() == ""  # caught: no line (today `lane-busy scoped held by …`)
        mod.give_up("scoped", str(busy.value), settings=_settings(tmp_path))
        (line,) = marker.read_text().splitlines()
        assert line.startswith(f"lane-busy scoped dir={_encoded(lanes)} held by pid ") \
            and "— holder" in line, line
        # without the variable nothing is written
        monkeypatch.delenv("PROCESS_SUITE_ABORT")
        mod.give_up("scoped", str(busy.value), settings=_settings(tmp_path))
        assert len(marker.read_text().splitlines()) == 1
        # the command lines keep their exit 75 — and write the line with dir=
        for argv in (["wait", "--lane", "scoped", "--wait", "0", "--quiet"],
                     ["run", "--lane", "scoped", "--wait", "0", "--", "true"]):
            r = subprocess.run([sys.executable, str(LANE), *argv], cwd=tmp_path,
                               env={**_env(tmp_path), "PROCESS_SUITE_ABORT": str(marker)},
                               capture_output=True, text=True)
            assert r.returncode == 75, r.stderr
            assert marker.read_text().splitlines()[-1].startswith(
                f"lane-busy scoped dir={_encoded(lanes)} held by pid "), marker.read_text()
        assert len(marker.read_text().splitlines()) == 3
        # a missing path is never created, a path that is a directory is no error: exit 75 either way
        for where in (tmp_path / "missing", tmp_path):
            r = subprocess.run([sys.executable, str(LANE), "run", "--lane", "scoped", "--wait", "0", "--", "true"],
                               cwd=tmp_path, env={**_env(tmp_path), "PROCESS_SUITE_ABORT": str(where)},
                               capture_output=True, text=True)
            assert r.returncode == 75, (where, r.stderr)
        assert not (tmp_path / "missing").exists()
    finally:
        proc.kill()
        proc.wait()


def test_a_child_that_exits_75_under_lane_run_writes_no_line(tmp_path):
    """#448: `cmd_run` writes only on its own LaneBusy; its command's exit 75 is the command's."""
    marker = tmp_path / "marker"
    marker.write_text("")
    r = subprocess.run([sys.executable, str(LANE), "run", "--lane", "scoped", "--wait", "0", "--",
                        sys.executable, "-c", "raise SystemExit(75)"], cwd=tmp_path,
                       env={**_env(tmp_path), "PROCESS_SUITE_ABORT": str(marker)}, capture_output=True, text=True)
    assert r.returncode == 75 and marker.read_text() == "", (r.stderr, marker.read_text())


def test_a_give_up_percent_encodes_a_lane_dir_with_a_space(tmp_path, monkeypatch):
    """#448 (r3 P4-3): a space in the path would split the line — it is encoded, and the
    first two words stay `lane-busy <lane>` (train.md counts series by them)."""
    mod = _load()
    marker = tmp_path / "marker"
    marker.write_text("")
    monkeypatch.setenv("PROCESS_SUITE_ABORT", str(marker))
    where = tmp_path / "my lanes%x"
    mod.give_up("full", "full: held by pid 1 — x", where=where)
    line = marker.read_text().rstrip("\n")
    assert line == f"lane-busy full dir={_encoded(where)} held by pid 1 — x", line
    assert " " not in line.split()[2] and "%20" in line.split()[2] and "%25x" in line.split()[2]


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="no FIFOs on this platform")
def test_a_marker_that_is_a_fifo_never_blocks_the_exit_75(tmp_path):
    """Refute: the marker path names a FIFO nobody reads — the open must not block, and the
    busy lane still exits 75 at once."""
    fifo = tmp_path / "fifo"
    os.mkfifo(fifo)
    proc = _holder(tmp_path)
    try:
        started = time.monotonic()
        r = subprocess.run([sys.executable, str(LANE), "wait", "--lane", "scoped", "--wait", "0", "--quiet"],
                           cwd=tmp_path, env={**_env(tmp_path), "PROCESS_SUITE_ABORT": str(fifo)},
                           capture_output=True, text=True, timeout=20)
        assert r.returncode == 75 and time.monotonic() - started < 15, r.stderr
    finally:
        proc.kill()
        proc.wait()


def test_the_marker_line_carries_no_line_break_of_the_holder(tmp_path, monkeypatch):
    mod = _load()
    marker = tmp_path / "marker"
    marker.write_text("")
    monkeypatch.setenv("PROCESS_SUITE_ABORT", str(marker))
    mod.give_up("full", "held by pid 1 — a\nlabel\r\nwith breaks", where=tmp_path)
    assert marker.read_text() == f"lane-busy full dir={_encoded(tmp_path)} held by pid 1 — a label with breaks\n"
