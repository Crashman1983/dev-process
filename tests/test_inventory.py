"""#223 part A: generated inventories with a drift check (`inventory.py`,
`check_inventory.py`, `inventory_config.py`) — the committed list stores
`source` without its line, the check compares bytes, and a plan finds the rows
of the files it names (docs/analysis/2026-10-13-knowledge-anchors-plan.md, 4.1/4.2)."""
import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

ENV_EXTRACTOR = '''import json, pathlib, re
for p in sorted(pathlib.Path("src").rglob("*.py")):
    for n, line in enumerate(p.read_text().splitlines(), 1):
        for m in re.finditer(r'getenv\\("([A-Z_]+)"(?:, "([^"]*)")?\\)', line):
            print(json.dumps({"id": m.group(1), "source": f"{p.as_posix()}:{n}",
                              "default": m.group(2)}))
'''
# prints a prepared file byte for byte: the contract cases write what they need
RAW_EXTRACTOR = 'import sys\nsys.stdout.buffer.write(open("inv/raw.out", "rb").read())\n'
SOURCES = {
    "src/app/config.py": 'import os\nDB = os.getenv("DB_URL", "sqlite://")\n',
    "src/app/worker.py": 'import os\n\nQ = os.getenv("QUEUE")\n',
    "src/other.py": 'import os\nF = os.getenv("OTHER_FLAG", "0")\n',
}
REFRESH = "uv run scripts/process/inventory.py update"


def _git(out: Path, *a: str) -> None:
    subprocess.run(["git", *a], cwd=out, check=True, capture_output=True)


def _write(out: Path, rel: str, text: str | bytes) -> None:
    p = out / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(text, bytes):
        p.write_bytes(text)
    else:
        p.write_text(text, encoding="utf-8")


def _config(out: Path, inventories: dict | None) -> None:
    path = out / "docs/process/inventories.local.json"
    if inventories is None:
        path.unlink(missing_ok=True)
    else:
        path.write_text(json.dumps({"inventories": inventories}), encoding="utf-8")


def _env_spec(**extra) -> dict:
    return {"command": [sys.executable, "scripts/inventory_env.py"], **extra}


def _raw_spec(**extra) -> dict:
    return {"command": [sys.executable, "scripts/inventory_raw.py"], **extra}


def _project(render, tmp_path: Path, inventories: dict | None = None, *, remote: bool = False) -> Path:
    out = render(tmp_path / "p", {"project_name": "d", "modules": {"telemetry": True}})
    _git(out, "init", "-q", "-b", "main")
    _git(out, "config", "user.email", "t@t")
    _git(out, "config", "user.name", "t")
    _git(out, "config", "commit.gpgsign", "false")
    for rel, text in SOURCES.items():
        _write(out, rel, text)
    _write(out, "scripts/inventory_env.py", ENV_EXTRACTOR)
    _write(out, "scripts/inventory_raw.py", RAW_EXTRACTOR)
    _config(out, {"env": _env_spec()} if inventories is None else inventories)
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "init")
    if remote:
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(tmp_path / "origin.git")],
                       check=True)
        _git(out, "remote", "add", "origin", str(tmp_path / "origin.git"))
        _git(out, "push", "-q", "-u", "origin", "main")
    return out


def _env() -> dict:
    return {k: v for k, v in os.environ.items() if k not in ("CI", "PRE_COMMIT_TO_REF")}


def _inv(out: Path, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(out / "scripts/process/inventory.py"), *args],
                          cwd=cwd or out, capture_output=True, text=True, env=_env(), timeout=120)


def _gate_entry(out: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(out / "scripts/process/check_inventory.py"), "."],
                          cwd=out, capture_output=True, text=True, env=_env(), timeout=120)


def _load(out: Path, name: str):
    sys.path.insert(0, str(out / "scripts/process"))
    spec = importlib.util.spec_from_file_location(f"{name}_under_test", out / f"scripts/process/{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _md(out: Path, name: str = "env") -> str:
    return (out / f"docs/inventory/{name}.md").read_text(encoding="utf-8")


# ------------------------------------------------------------------ configuration


def test_without_configuration_the_tool_is_green_and_the_gate_entry_red(render, tmp_path):
    out = _project(render, tmp_path)
    _config(out, None)

    for cmd in ("check", "update", "list"):
        r = _inv(out, cmd)
        assert r.returncode == 0 and "nothing configured" in r.stdout, r.stdout + r.stderr
    g = _gate_entry(out)
    assert g.returncode == 1, g.stdout
    assert "registered but no docs/process/inventories.local.json" in g.stdout


def test_a_valid_configuration_gets_its_defaults(render, tmp_path):
    out = _project(render, tmp_path)
    cfg = _load(out, "inventory_config")
    _config(out, {"jobs": {"command": ["python3", "j.py"]},
                  "env": {"command": ["uv", "run", "e.py"], "timeout": 30, "allow_empty": True}})

    conf = cfg.load(out)

    assert list(conf) == ["env", "jobs"]
    assert conf["jobs"] == {"command": ["python3", "j.py"], "timeout": 120.0, "allow_empty": False}
    assert conf["env"] == {"command": ["uv", "run", "e.py"], "timeout": 30.0, "allow_empty": True}
    assert cfg.parse({"inventories": {"a": {"command": ["x"], "timeout": 539}}})["a"]["timeout"] == 539


@pytest.mark.parametrize(("raw", "where"), [
    ("{not json", "inventories.local.json"),
    ("[]", "JSON object"),
    ('{"inventories": {}, "extra": 1}', "unknown key(s): extra"),
    ('{}', "inventories must be an object"),
    ('{"inventories": []}', "inventories must be an object"),
    ('{"inventories": {"Env": {"command": ["x"]}}}', "'Env' is no inventory name"),
    ('{"inventories": {"a_b": {"command": ["x"]}}}', "'a_b' is no inventory name"),
    ('{"inventories": {"a": ["x"]}}', "inventories.a must be an object"),
    ('{"inventories": {"a": {"command": ["x"], "shell": true}}}', "inventories.a: unknown key(s): shell"),
    ('{"inventories": {"a": {}}}', "inventories.a needs `command`"),
    ('{"inventories": {"a": {"command": "x y"}}}', "inventories.a.command must be a non-empty list"),
    ('{"inventories": {"a": {"command": []}}}', "inventories.a.command must be a non-empty list"),
    ('{"inventories": {"a": {"command": ["x", ""]}}}', "inventories.a.command must be a non-empty list"),
    ('{"inventories": {"a": {"command": ["x"], "timeout": 0}}}', "inventories.a.timeout"),
    ('{"inventories": {"a": {"command": ["x"], "timeout": true}}}', "inventories.a.timeout"),
    ('{"inventories": {"a": {"command": ["x"], "timeout": "60"}}}', "inventories.a.timeout"),
    ('{"inventories": {"a": {"command": ["x"], "timeout": Infinity}}}', "inventories.a.timeout"),
    ('{"inventories": {"a": {"command": ["x"], "allow_empty": "yes"}}}', "inventories.a.allow_empty"),
    ('{"inventories": {"a": {"command": ["x"], "timeout": 300}, "b": {"command": ["y"], "timeout": 240}}}',
     "add up to 540 s"),
    ('{"inventories": {"a": {"command": ["x"]}, "b": {"command": ["y"]}, "c": {"command": ["z"]},'
     ' "d": {"command": ["w"]}, "e": {"command": ["v"]}}}', "add up to 600 s"),
], ids=["unparseable", "not-object", "unknown-top", "no-inventories", "inventories-list", "upper-name",
        "underscore-name", "spec-list", "unknown-key", "no-command", "command-string", "command-empty",
        "command-blank-arg", "timeout-zero", "timeout-bool", "timeout-string", "timeout-inf",
        "allow-empty-string", "budget-exact", "budget-defaults"])
def test_a_malformed_configuration_is_an_error_with_its_place(render, tmp_path, raw, where):
    out = _project(render, tmp_path)
    (out / "docs/process/inventories.local.json").write_text(raw, encoding="utf-8")
    cfg = _load(out, "inventory_config")

    with pytest.raises(cfg.ConfigError) as exc:
        cfg.load(out)
    assert "docs/process/inventories.local.json" in str(exc.value) and where in str(exc.value)
    r = _inv(out, "check")
    assert r.returncode == 1 and where in r.stderr, r.stdout + r.stderr
    g = _gate_entry(out)
    assert g.returncode == 1 and where in g.stdout, g.stdout


# ------------------------------------------------------------------ update / check


def test_update_writes_a_list_that_check_finds_byte_identical(render, tmp_path):
    out = _project(render, tmp_path)

    r = _inv(out, "update")
    assert r.returncode == 0 and "env: wrote docs/inventory/env.md" in r.stdout, r.stdout + r.stderr
    text = _md(out)
    assert text.startswith("# Inventory: env\n")
    assert "Generated by `scripts/process/inventory.py update env` — do not edit by hand." in text
    assert "scripts/inventory_env.py" in text  # the command
    table = [ln for ln in text.splitlines() if ln.startswith("|")]
    assert table[0] == "| id | default | source | note |"
    assert table[2:] == ["| DB_URL | sqlite:// | src/app/config.py |  |",
                         "| OTHER_FLAG | 0 | src/other.py |  |",
                         "| QUEUE |  | src/app/worker.py |  |"]  # sorted by id, no :line
    c = _inv(out, "check")
    assert c.returncode == 0 and "inventory: OK" in c.stdout, c.stdout + c.stderr
    assert "unchanged" in _inv(out, "update").stdout
    g = _gate_entry(out)
    assert g.returncode == 0 and "inventory: OK" in g.stdout, g.stdout
    lst = _inv(out, "list")
    assert lst.stdout.strip() == "env  3 rows", lst.stdout


def test_the_same_rows_in_another_order_give_the_same_file(render, tmp_path):
    out = _project(render, tmp_path, {"raw": _raw_spec()})
    rows = [{"id": "b", "source": "x/b.py:4", "zeta": 1, "alpha": "A"},
            {"id": "a", "source": "x/a.py", "alpha": None, "flag": True},
            {"id": "c", "source": "./x/c.py:9", "zeta": 2.5}]
    _write(out, "inv/raw.out", "".join(json.dumps(r) + "\n" for r in rows))
    assert _inv(out, "update").returncode == 0
    first = (out / "docs/inventory/raw.md").read_bytes()

    shuffled = [dict(reversed(list(r.items()))) for r in reversed(rows)]
    _write(out, "inv/raw.out", "\n".join(json.dumps(r) for r in shuffled))  # no final newline either
    assert _inv(out, "update").returncode == 0

    assert (out / "docs/inventory/raw.md").read_bytes() == first
    table = [ln for ln in first.decode().splitlines() if ln.startswith("|")]
    assert table[0] == "| id | alpha | flag | zeta | source | note |"  # other fields alphabetical
    assert table[2:] == ["| a |  | true |  | x/a.py |  |",
                         "| b | A |  | 1 | x/b.py |  |",
                         "| c |  |  | 2.5 | x/c.py |  |"]


def test_rendering_and_reading_back_give_the_same_rows(render, tmp_path):
    out = _project(render, tmp_path, {"raw": _raw_spec()})
    inv = _load(out, "inventory")
    nasty = ["back\\slash", "pi|pe", "new\nline", "literal \\n and \\|", "  padded  ", "cr\r", "|", "\\", ""]
    rows = [{"id": f"r{i}|{v}", "source": f"src/{i}.py", "line": None, "fields": {"v": v, "w": i}}
            for i, v in enumerate(nasty)]
    notes = {rows[1]["id"]: "note | with\nbreak \\ too"}
    spec = _raw_spec()

    text = inv.render("raw", spec, rows, notes)

    cols, back = inv.parse_table(text)
    assert (cols, back) == inv.table(rows, notes)
    assert [r["v"] for r in sorted(back, key=lambda r: r["id"])] == [
        r["fields"]["v"] for r in sorted(rows, key=lambda r: r["id"])]
    assert all(ln.startswith("|") and ln.endswith("|") for ln in text.splitlines() if "|" in ln[:1])
    assert len([ln for ln in text.splitlines() if ln.startswith("|")]) == 2 + len(nasty)

    # the same through the extractor and the committed file
    _write(out, "inv/raw.out", "".join(json.dumps({"id": r["id"], "source": r["source"], **r["fields"]})
                                       + "\n" for r in rows))
    _write(out, "docs/inventory/raw.notes.json", json.dumps(notes))
    assert _inv(out, "update").returncode == 0
    assert inv.committed(out, "raw") == inv.table(rows, notes)[1]
    assert _inv(out, "check").returncode == 0


def test_a_shifted_line_number_keeps_the_check_green(render, tmp_path):
    out = _project(render, tmp_path)
    assert _inv(out, "update").returncode == 0
    _write(out, "src/app/config.py", "# a comment\n\n" + SOURCES["src/app/config.py"])

    r = _inv(out, "check")

    assert r.returncode == 0, r.stdout + r.stderr
    assert "env  DB_URL  src/app/config.py:4" in _inv(out, "for-paths", "src/app/config.py").stdout


def test_drift_is_red_and_names_the_command_that_fixes_it(render, tmp_path):
    out = _project(render, tmp_path)
    assert _inv(out, "update").returncode == 0
    _write(out, "src/new.py", 'import os\nT = os.getenv("TIMEOUT_S", "30")\n')

    r = _inv(out, "check")

    assert r.returncode == 1, r.stdout + r.stderr
    assert "docs/inventory/env.md differs from the code" in r.stderr
    assert f"`{REFRESH} env`" in r.stderr and "TIMEOUT_S" in r.stderr  # with the diff
    g = _gate_entry(out)
    assert g.returncode == 1 and f"{REFRESH} env" in g.stdout, g.stdout
    assert _inv(out, "update", "env").returncode == 0
    assert _inv(out, "check").returncode == 0


def test_a_hand_edit_of_the_list_is_drift(render, tmp_path):
    out = _project(render, tmp_path)
    assert _inv(out, "update").returncode == 0
    path = out / "docs/inventory/env.md"
    path.write_text(path.read_text().replace("sqlite://", "postgres://"), encoding="utf-8")

    assert _inv(out, "check").returncode == 1


# ------------------------------------------------------------------ the extractor contract

_BIG = "import sys\nsys.stdout.write('x' * (6 * 1024 * 1024))\n"
_EXIT = "import sys\nsys.stderr.write('boom: ' + 'e' * 5000 + ' tail-of-stderr')\nsys.exit(3)\n"


@pytest.mark.parametrize(("output", "script", "expect"), [
    (None, _EXIT, "exited 3"),
    ("not json\n", None, "output line 1 is no JSON"),
    ('["a"]\n', None, "is no JSON object"),
    ('{"source": "a.py"}\n', None, "`id` must be a non-empty string"),
    ('{"id": "", "source": "a.py"}\n', None, "`id` must be a non-empty string"),
    ('{"id": 7, "source": "a.py"}\n', None, "`id` must be a non-empty string"),
    ('{"id": "a"}\n', None, "no `source`"),
    ('{"id": "a", "source": "/etc/passwd"}\n', None, "must be a path inside the repository"),
    ('{"id": "a", "source": "../up.py"}\n', None, "must be a path inside the repository"),
    ('{"id": "a", "source": "a.py"}\n{"id": "a", "source": "b.py"}\n', None, "output line 2: duplicate id 'a'"),
    ('{"id": "a", "source": "a.py", "tags": ["x"]}\n', None, "field 'tags' is nested"),
    ('{"id": "a", "source": "a.py", "meta": {"k": 1}}\n', None, "field 'meta' is nested"),
    ('{"id": "a", "source": "a.py", "note": "hand"}\n', None, "`note` is reserved"),
    (b'{"id": "caf\xe9", "source": "a.py"}\n', None, "output is not UTF-8"),
    ("", None, "printed no rows"),
    ("\n  \n", None, "printed no rows"),
    (None, _BIG, "printed more than 5 MB"),
], ids=["exit", "no-json", "no-object", "no-id", "empty-id", "id-number", "no-source", "absolute-source",
        "parent-source", "duplicate-id", "nested-list", "nested-object", "note", "not-utf8", "empty",
        "blank-lines", "too-big"])
def test_a_broken_extractor_is_red_and_never_half_a_result(render, tmp_path, output, script, expect):
    out = _project(render, tmp_path, {"raw": _raw_spec()})
    _write(out, "inv/raw.out", '{"id": "ok", "source": "a.py"}\n')
    assert _inv(out, "update").returncode == 0
    before = _md(out, "raw")
    if script is not None:
        _write(out, "scripts/inventory_raw.py", script)
    else:
        _write(out, "inv/raw.out", output)

    c = _inv(out, "check")
    u = _inv(out, "update")

    assert c.returncode == 1 and expect in c.stderr, c.stdout + c.stderr
    assert f"{REFRESH} raw" in c.stderr
    assert u.returncode == 1 and expect in u.stderr, u.stdout + u.stderr
    assert _md(out, "raw") == before  # a failing extractor leaves the list as it was
    g = _gate_entry(out)
    assert g.returncode == 1 and expect in g.stdout, g.stdout
    if script == _EXIT:  # stderr is shown, shortened to its end
        assert "tail-of-stderr" in c.stderr and "…" in c.stderr and len(c.stderr) < 3500


def test_a_contract_error_shows_the_extractors_stderr(render, tmp_path):
    out = _project(render, tmp_path, {"raw": _raw_spec()})
    _write(out, "inv/raw.out", '{"id": "ok", "source": "a.py"}\n')
    assert _inv(out, "update").returncode == 0
    _write(out, "scripts/inventory_raw.py", "import sys\nsys.stderr.write('skipped models.py')\nprint('{')\n")

    r = _inv(out, "check")

    assert r.returncode == 1 and "is no JSON" in r.stderr and "skipped models.py" in r.stderr, r.stderr


def test_an_empty_list_passes_when_allowed(render, tmp_path):
    out = _project(render, tmp_path, {"raw": _raw_spec(allow_empty=True)})
    _write(out, "inv/raw.out", "")

    assert _inv(out, "update").returncode == 0
    assert _inv(out, "check").returncode == 0
    assert [ln for ln in _md(out, "raw").splitlines() if ln.startswith("|")][0] == "| id | source | note |"


def _alive(pid: int) -> bool:
    stat = Path(f"/proc/{pid}/stat")
    if stat.parent.parent.is_dir() and Path("/proc/self").exists():
        try:
            return stat.read_text().rsplit(")", 1)[1].split()[0] != "Z"  # a zombie is gone
        except (OSError, IndexError):
            return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


@pytest.mark.skipif(not hasattr(os, "killpg"), reason="process groups are POSIX")
def test_a_timeout_kills_the_extractors_whole_process_group(render, tmp_path):
    """`uv run` starts a grandchild: killing only the child leaves it holding the pipe."""
    out = _project(render, tmp_path, {"raw": _raw_spec(timeout=1)})
    _write(out, "inv/raw.out", '{"id": "ok", "source": "a.py"}\n')
    assert _inv(out, "update").returncode == 0
    _write(out, "scripts/inventory_raw.py",
           "import pathlib, subprocess, sys, time\n"
           "g = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])\n"
           "pathlib.Path('grandchild.pid').write_text(str(g.pid))\n"
           "print('{\"id\": \"a\", \"source\": \"a.py\"}', flush=True)\n"
           "time.sleep(120)\n")

    start = time.monotonic()
    r = _inv(out, "check")
    took = time.monotonic() - start

    assert r.returncode == 1 and "did not finish in 1 s — killed" in r.stderr, r.stdout + r.stderr
    assert took < 30
    pid = int((out / "grandchild.pid").read_text())
    deadline = time.monotonic() + 10
    while _alive(pid) and time.monotonic() < deadline:
        time.sleep(0.1)
    assert not _alive(pid)


# ------------------------------------------------------------------ files and notes


def test_a_configured_list_without_its_file_is_red(render, tmp_path):
    out = _project(render, tmp_path)

    r = _inv(out, "check")

    assert r.returncode == 1 and "docs/inventory/env.md is missing" in r.stderr, r.stderr
    assert f"`{REFRESH} env`" in r.stderr
    assert _gate_entry(out).returncode == 1


@pytest.mark.parametrize("orphan", ["old.md", "old.notes.json"])
def test_a_file_without_a_configured_list_is_red(render, tmp_path, orphan):
    out = _project(render, tmp_path)
    assert _inv(out, "update").returncode == 0
    _write(out, f"docs/inventory/{orphan}", "{}\n")

    r = _inv(out, "check")

    assert r.returncode == 1, r.stdout + r.stderr
    assert f"docs/inventory/{orphan} belongs to no configured inventory" in r.stderr
    assert "docs/process/inventories.local.json" in r.stderr
    g = _gate_entry(out)
    assert g.returncode == 1 and orphan in g.stdout
    assert _inv(out, "check", "env").returncode == 0  # a named check looks at its own list only


def test_notes_are_kept_and_orphaned_ones_reported(render, tmp_path):
    out = _project(render, tmp_path)
    notes = {"DB_URL": "rotate | yearly\nask ops", "GONE": "an old row"}
    _write(out, "docs/inventory/env.notes.json", json.dumps(notes))

    r = _inv(out, "update")

    assert r.returncode == 0, r.stdout + r.stderr
    assert "| DB_URL | sqlite:// | src/app/config.py | rotate \\| yearly\\nask ops |" in _md(out)
    assert "orphaned note(s) for GONE" in r.stdout
    assert json.loads((out / "docs/inventory/env.notes.json").read_text()) == notes  # left in place
    c = _inv(out, "check")
    assert c.returncode == 0 and "orphaned note(s) for GONE" in c.stdout, c.stdout + c.stderr
    # a changed note is drift: the list carries it
    _write(out, "docs/inventory/env.notes.json", json.dumps({"DB_URL": "other"}))
    assert _inv(out, "check").returncode == 1
    _write(out, "docs/inventory/env.notes.json", "[1]")
    bad = _inv(out, "check")
    assert bad.returncode == 1 and "env.notes.json must be an object" in bad.stderr


# ------------------------------------------------------------------ for-plan / for-paths


def _with_notes_and_lists(out: Path) -> None:
    _write(out, "docs/inventory/env.notes.json", json.dumps({"DB_URL": "rotated yearly"}))
    assert _inv(out, "update").returncode == 0
    # a list nobody configures any more: never read
    _write(out, "docs/inventory/old.md", "| id | source | note |\n| --- | --- | --- |\n"
                                         "| STALE | src/app/config.py |  |\n")


def test_for_paths_finds_rows_of_a_file_and_under_a_directory(render, tmp_path):
    out = _project(render, tmp_path)
    _with_notes_and_lists(out)

    f = _inv(out, "for-paths", "src/app/config.py")
    d = _inv(out, "for-paths", "src/app/")
    sub = _inv(out, "for-paths", "worker.py", cwd=out / "src/app")
    none = _inv(out, "for-paths", "docs/")

    assert f.returncode == 0 and f.stdout.splitlines() == ["env  DB_URL  src/app/config.py:2  rotated yearly"]
    assert d.stdout.splitlines() == ["env  DB_URL  src/app/config.py:2  rotated yearly",
                                     "env  QUEUE  src/app/worker.py:3"]
    assert sub.stdout.splitlines() == ["env  QUEUE  src/app/worker.py:3"]  # relative to where it runs
    assert none.returncode == 0 and "no row at or under the 1 path(s)" in none.stdout
    assert "STALE" not in f.stdout + d.stdout  # only configured lists


def test_for_plan_reads_the_paths_the_plan_names(render, tmp_path):
    out = _project(render, tmp_path)
    _with_notes_and_lists(out)
    _write(out, ".process-work/plans/2026-10-13-x.md",
            "# X\n\n1. Change `src/app/worker.py:3` and read `src/other.py::F`.\n"
            "2. src/app outside backticks and `make test` name nothing.\n")
    _write(out, ".process-work/plans/2026-10-13-dir.md", "# D\n\n1. Rework `src/app/`.\n")

    r = _inv(out, "for-plan", ".process-work/plans/2026-10-13-x.md")
    d = _inv(out, "for-plan", ".process-work/plans/2026-10-13-dir.md")

    assert r.returncode == 0, r.stderr
    assert r.stdout.splitlines() == ["env  OTHER_FLAG  src/other.py:2", "env  QUEUE  src/app/worker.py:3"]
    assert d.stdout.splitlines() == ["env  DB_URL  src/app/config.py:2  rotated yearly",
                                     "env  QUEUE  src/app/worker.py:3"]


def test_for_plan_falls_back_to_the_committed_list_when_the_extractor_fails(render, tmp_path):
    out = _project(render, tmp_path)
    _with_notes_and_lists(out)
    _write(out, "scripts/inventory_env.py", "import sys\nsys.stderr.write('db down')\nsys.exit(2)\n")
    _write(out, "plan.md", "Touch `src/app/config.py`.\n")

    r = _inv(out, "for-plan", "plan.md")

    assert r.returncode == 0, r.stderr  # a planning aid, not a gate
    assert r.stdout.splitlines() == ["env  DB_URL  src/app/config.py  rotated yearly"]
    assert "no line numbers, the extractor failed" in r.stderr and "exited 2" in r.stderr
    assert "db down" in r.stderr


# ------------------------------------------------------------------ as a local gate

_GATE = {"inventory": {"module": None, "command": ["scripts/process/check_inventory.py", "."]}}


def _gates(out: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(out / "scripts/process/gate_runner.py")],
                          cwd=out, capture_output=True, text=True, env=_env(), timeout=300)


def _registered(render, tmp_path: Path, *, remote: bool) -> Path:
    out = _project(render, tmp_path, remote=remote)
    assert _inv(out, "update").returncode == 0
    _write(out, "docs/process/gates.local.json", json.dumps(_GATE))
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "inventory gate")
    if remote:
        _git(out, "push", "-q", "origin", "main")
    return out


def test_the_registered_gate_runs_in_the_real_runner_and_blocks_drift(render, tmp_path):
    out = _registered(render, tmp_path, remote=False)

    green = _gates(out)
    assert green.returncode == 0, green.stdout + green.stderr
    assert "== running inventory ==" in green.stdout and "inventory: OK" in green.stdout

    _write(out, "src/new.py", 'import os\nT = os.getenv("TIMEOUT_S")\n')
    red = _gates(out)
    assert red.returncode == 1 and "FAILED gates: inventory" in red.stdout, red.stdout + red.stderr
    assert f"{REFRESH} env" in red.stdout


def test_in_shadow_the_registered_gate_records_drift_but_does_not_block(render, tmp_path):
    out = _registered(render, tmp_path, remote=True)
    w = subprocess.run([sys.executable, str(out / "scripts/process/gate_modes.py"), "weaken", "inventory",
                        "--to", "shadow", "--observe", "--decision", "owner: new check, count it first"],
                       cwd=out, capture_output=True, text=True, env=_env())
    assert w.returncode == 0, w.stderr
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "observe inventory")
    _git(out, "push", "-q", "origin", "main")  # a weakening counts once it is on the base
    _write(out, "src/new.py", 'import os\nT = os.getenv("TIMEOUT_S")\n')

    g = _gates(out)

    assert g.returncode == 0, g.stdout + g.stderr
    assert "inventory failed in shadow mode" in g.stderr
    events = [json.loads(ln) for ln in (out / ".git/process-gate-events.jsonl").read_text().splitlines()]
    last = [e for e in events if e["gate"] == "inventory"][-1]
    assert last["mode"] == "shadow" and last["outcome"] == "fail"
