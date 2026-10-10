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
    for name in ("lane.py", "testing_config.py"):
        shutil.copy(PROC / name, root / "scripts/process" / name)
    assert cfg.lane_status(root, env) == []  # no test configuration: no lanes shown
    (root / "docs/process").mkdir(parents=True)
    (root / "docs/process/testing.local.json").write_text("{}")
    assert cfg.lane_status(root, env) == ["scoped: free", "full: free"]
    (root / "scripts/lane.py").write_text("print('scoped: held by pid 1 — own (b) since 09:00 (1 min)')\n")
    assert cfg.lane_status(root, env) == ["scoped: held by pid 1 — own (b) since 09:00 (1 min)"]
