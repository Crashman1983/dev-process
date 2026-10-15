"""due_measurements: measurement milestones read from the project's
milestones.local.json, due once their date passed without a record carrying
`milestone: <id>`. The due table is a pure function; the file and the CLI run
on a rendered tree, because that is where a project meets them."""
import importlib.util
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "template" / "scripts" / "process" / "due_measurements.py"

PLAN_DRIFT = "plan-drift-2026-10-27"
KNOWLEDGE_GAP = "knowledge-gap-2026-11-10"
MILESTONES = {"milestones": [
    # listed out of date order on purpose: the output sorts, the file need not
    {"id": KNOWLEDGE_GAP, "due": "2026-11-10",
     "command": "uv run scripts/process/process_kpis.py rounds",
     "record_hint": "knowledge-gap share as an improvement record"},
    {"id": PLAN_DRIFT, "due": "2026-10-27",
     "command": "uv run scripts/process/process_kpis.py nodes",
     "record_hint": "thresholds as a proposal to the owner"},
]}


def _module():
    sys.path.insert(0, str(SCRIPT.parent))  # the sibling `optimize` import
    spec = importlib.util.spec_from_file_location("due_measurements_t", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # the dataclass looks its module up by name
    spec.loader.exec_module(mod)
    return mod


dm = _module()


def _ids(milestones) -> list[str]:
    return [m.id for m in milestones]


def _write_milestones(root: Path, data) -> Path:
    path = root / "docs" / "process" / "milestones.local.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
    return path


def _record(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _run(root: Path, *args: str, script: Path | None = None) -> subprocess.CompletedProcess:
    script = script or root / "scripts" / "process" / "due_measurements.py"
    return subprocess.run([sys.executable, str(script), *args], capture_output=True,
                          text=True, cwd=root, check=False)


@pytest.fixture
def project(render, tmp_path):
    return render(tmp_path / "p", {"project_name": "d"})


# --- the pure due table ---------------------------------------------------
@pytest.fixture
def listed(tmp_path):
    _write_milestones(tmp_path, MILESTONES)
    return dm.load_milestones(tmp_path)


@pytest.mark.parametrize(("today", "recorded", "expected"), [
    (date(2026, 10, 26), set(), []),
    (date(2026, 10, 27), set(), [PLAN_DRIFT]),
    (date(2026, 11, 10), set(), [PLAN_DRIFT, KNOWLEDGE_GAP]),
    (date(2026, 11, 10), {PLAN_DRIFT}, [KNOWLEDGE_GAP]),
    (date(2026, 11, 10), {PLAN_DRIFT, KNOWLEDGE_GAP}, []),
    (date(2026, 11, 10), {"wrong-id"}, [PLAN_DRIFT, KNOWLEDGE_GAP]),
])
def test_due_table(listed, today, recorded, expected):
    assert _ids(dm.due(today, recorded, listed)) == expected


def test_due_is_sorted_by_date_not_file_order(listed):
    assert _ids(listed) == [KNOWLEDGE_GAP, PLAN_DRIFT]
    assert _ids(dm.due(date(2027, 1, 1), set(), listed)) == [PLAN_DRIFT, KNOWLEDGE_GAP]


def test_due_takes_the_list_it_is_given():
    m = dm.Milestone("x", date(2026, 1, 1), "cmd", "hint")
    assert dm.due(date(2026, 1, 1), set(), (m,)) == [m]
    assert dm.due(date(2026, 1, 1), set(), ()) == []


# --- records ----------------------------------------------------------------
def test_recorded_ids_reads_milestone_lines_from_both_record_kinds(tmp_path):
    _record(tmp_path, ".process-work/optimizations/OPT-0001-plan.md",
            f"# OPT-0001\n\n## Result\n\nmilestone: {PLAN_DRIFT}\n")
    _record(tmp_path, ".process-work/improvement/2026-W46.md", f"milestone: {KNOWLEDGE_GAP}\n")
    _record(tmp_path, ".process-work/improvement/note.txt", "milestone: ignored-txt\n")
    _record(tmp_path, ".process-work/optimizations/notes.md", "milestone: ignored-not-opt\n")
    _record(tmp_path, ".process-work/improvement/prose.md",
            "the milestone: in-prose is no line of its own\n")

    assert dm.recorded_ids(tmp_path) == {PLAN_DRIFT, KNOWLEDGE_GAP}


def test_recorded_ids_without_directories_is_empty(tmp_path):
    assert dm.recorded_ids(tmp_path) == set()


# --- the milestone file -------------------------------------------------------
def test_no_milestone_file_is_silent_exit_0(project):
    assert not (project / "docs/process/milestones.local.json").exists()
    done = _run(project, "--today", "2030-01-01")
    assert (done.returncode, done.stdout, done.stderr) == (0, "", "")


@pytest.mark.parametrize(("content", "names"), [
    ("{not json", "not readable as JSON"),
    ([], '{"milestones": [...]}'),
    ({"milestones": {}}, '{"milestones": [...]}'),
    ({"milestones": ["x"]}, "milestones[0]: not an object"),
    ({"milestones": [{"id": "a", "due": "2026-10-27", "command": "c"}]},
     "milestones[0] (id 'a'): 'record_hint' must be a non-empty string"),
    ({"milestones": [{"id": "", "due": "2026-10-27", "command": "c", "record_hint": "h"}]},
     "milestones[0]: 'id' must be a non-empty string"),
    ({"milestones": [{"id": "a", "due": 20261027, "command": "c", "record_hint": "h"}]},
     "'due' must be a non-empty string"),
    ({"milestones": [{"id": "a", "due": "2026-13-01", "command": "c", "record_hint": "h"}]},
     "milestones[0] (id 'a'): due '2026-13-01' is not a YYYY-MM-DD date"),
    ({"milestones": [{"id": "a", "due": "20261027", "command": "c", "record_hint": "h"}]},
     "due '20261027' is not a YYYY-MM-DD date"),
    ({"milestones": [
        {"id": "a", "due": "2026-10-27", "command": "c", "record_hint": "h"},
        {"id": "a", "due": "2026-11-10", "command": "c", "record_hint": "h"}]},
     "milestones[1] (id 'a'): id appears twice"),
])
def test_malformed_milestone_file_exits_2_naming_file_and_entry(project, content, names):
    """A broken list must never read as "nothing due" — not even on a date
    before every milestone, where an empty list and a due list look alike."""
    _write_milestones(project, content)
    done = _run(project, "--today", "2000-01-01")
    assert done.returncode == 2, done.stdout
    assert done.stdout == ""
    assert "docs/process/milestones.local.json" in done.stderr
    assert names in done.stderr


def test_load_milestones_raises_on_malformed_file(tmp_path):
    _write_milestones(tmp_path, "{not json")
    with pytest.raises(dm.MilestoneFileError, match="milestones.local.json"):
        dm.load_milestones(tmp_path)


# --- the CLI on a rendered project ----------------------------------------------
def test_cli_reports_due_milestones(project):
    _write_milestones(project, MILESTONES)
    done = _run(project, "--today", "2026-11-10")
    assert done.returncode == 0, done.stderr
    assert done.stdout.splitlines() == [
        f"DUE {PLAN_DRIFT} (since 2026-10-27): uv run scripts/process/process_kpis.py nodes"
        " → thresholds as a proposal to the owner",
        f"DUE {KNOWLEDGE_GAP} (since 2026-11-10): uv run scripts/process/process_kpis.py rounds"
        " → knowledge-gap share as an improvement record",
    ]


def test_cli_before_any_date_is_silent(project):
    _write_milestones(project, MILESTONES)
    done = _run(project, "--today", "2026-10-26")
    assert (done.returncode, done.stdout) == (0, "")


def test_cli_milestone_answered_by_improvement_report(project):
    _write_milestones(project, MILESTONES)
    _record(project, ".process-work/improvement/2026-W45.md",
            f"# Improvement 2026-W45\n- Action: none\nmilestone: {PLAN_DRIFT}\n")
    done = _run(project, "--today", "2026-11-10")
    assert done.returncode == 0, done.stderr
    assert _due_ids(done.stdout) == [KNOWLEDGE_GAP]


def test_cli_milestone_answered_by_opt_record(project):
    _write_milestones(project, MILESTONES)
    _record(project, ".process-work/optimizations/OPT-0003-gap.md",
            f"# OPT-0003\nstate: evaluating\n\n## Result\n\nmilestone: {KNOWLEDGE_GAP}\n")
    done = _run(project, "--today", "2026-11-10")
    assert done.returncode == 0, done.stderr
    assert _due_ids(done.stdout) == [PLAN_DRIFT]


def test_cli_reads_only_the_given_root(project, tmp_path):
    """The rendered project lists the milestones and holds no record; a
    separate root holds both — `--root` answers for that root alone."""
    _write_milestones(project, MILESTONES)
    other = tmp_path / "other"
    _write_milestones(other, MILESTONES)
    _record(other, ".process-work/optimizations/OPT-1.md", f"milestone: {PLAN_DRIFT}\n")

    done = _run(project, "--root", str(other), "--today", "2026-10-27")
    assert (done.returncode, done.stdout) == (0, "")
    assert _due_ids(_run(project, "--today", "2026-10-27").stdout) == [PLAN_DRIFT]


def test_cli_default_root_is_two_levels_above_the_script(project, tmp_path):
    _write_milestones(project, MILESTONES)
    elsewhere = tmp_path / "cwd"
    elsewhere.mkdir()
    done = subprocess.run(
        [sys.executable, str(project / "scripts/process/due_measurements.py"), "--today", "2026-10-27"],
        capture_output=True, text=True, cwd=elsewhere, check=False)
    assert done.returncode == 0, done.stderr
    assert _due_ids(done.stdout) == [PLAN_DRIFT]


@pytest.mark.parametrize("bad", ["no-date", "2026-02-30", "20261027"])
def test_cli_invalid_today_exits_2(project, bad):
    _write_milestones(project, MILESTONES)
    done = _run(project, "--today", bad)
    assert done.returncode == 2
    assert done.stdout == ""
    assert bad in done.stderr


def _due_ids(stdout: str) -> list[str]:
    return [line.split()[1] for line in stdout.splitlines()]
