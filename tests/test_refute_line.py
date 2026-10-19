"""refute_line: the plan's REFUTE line counted from the refuter's report (#124 AC-3)."""
import subprocess
import sys
from pathlib import Path

PLAN = ".process-work/plans/2026-10-19-widget.md"
REPORT = """# Refute

Long prose about each attack.

- SCENARIO 1 OWNER: HELD — one parser
- SCENARIO 2 FAIL-OPEN: CONFIRMED MAJOR NEW — a timeout reads as green
- **SCENARIO 3 EDGE CASES: CONFIRMED MINOR NEW** — CRLF
- SCENARIO 4 EVIDENCE: CONFIRMED BLOCKER PRE-EXISTING — no test goes red

```
SCENARIO 9 QUOTED: CONFIRMED BLOCKER NEW — an example, not a scenario
```

PATTERN: every finding reads a failed call as an empty answer — `_git` owns it
"""


def _setup(render, tmp_path, plan="# Plan\n\ntier: 3\nissue: #77\n") -> Path:
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    (out / PLAN).parent.mkdir(parents=True, exist_ok=True)
    (out / PLAN).write_text(plan, encoding="utf-8")
    (out / "report.md").write_text(REPORT, encoding="utf-8")
    return out


def _tool(out: Path, *args: str, report: str = "report.md") -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(out / "scripts/process/refute_line.py"), report,
                           "--plan", PLAN, *args], cwd=out, capture_output=True, text=True)


def test_counts_the_report_and_appends_the_line(render, tmp_path):
    out = _setup(render, tmp_path)
    r = _tool(out, "--summary", "MAJOR and MINOR fixed with tests; the BLOCKER is #80")
    assert r.returncode == 0, r.stdout + r.stderr
    line = ("REFUTE work=2026-10-19-widget round=1: 4 scenarios, 3 findings (1 blocker, 1 major, "
            "1 minor; 1 pre-existing) — MAJOR and MINOR fixed with tests; the BLOCKER is #80")
    assert (out / PLAN).read_text(encoding="utf-8") == f"# Plan\n\ntier: 3\nissue: #77\n\n{line}\n"


def test_the_line_is_one_the_review_bundle_counts(render, tmp_path):
    out = _setup(render, tmp_path)
    assert _tool(out, "--work", "77", "--summary", "all fixed").returncode == 0
    sys.path.insert(0, str(out / "scripts/process"))
    import importlib.util
    spec = importlib.util.spec_from_file_location("bundle_rl", out / "scripts/process/make_review_bundle.py")
    bundle = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bundle)
    assert bundle._unrefuted(out, {out / PLAN: (out / PLAN).read_text(encoding="utf-8")}) == []


def test_the_next_round_follows_the_last_and_a_taken_round_is_refused(render, tmp_path):
    out = _setup(render, tmp_path)
    assert _tool(out, "--summary", "fixed").returncode == 0
    r = _tool(out, "--summary", "the fix round's attack found nothing new")
    assert r.returncode == 0, r.stderr
    assert "REFUTE work=2026-10-19-widget round=2: 4 scenarios" in r.stdout
    r = _tool(out, "--round", "2", "--summary", "again")
    assert r.returncode == 1 and "round 2 is already recorded" in r.stderr


def test_a_report_without_findings_says_zero(render, tmp_path):
    out = _setup(render, tmp_path)
    (out / "report.md").write_text("SCENARIO OWNER: HELD\nPATTERN: no common cause\n", encoding="utf-8")
    r = _tool(out, "--summary", "nothing to fix", "--dry-run")
    assert r.returncode == 0, r.stderr
    assert "round=1: 1 scenarios, 0 findings — nothing to fix" in r.stdout
    assert "REFUTE" not in (out / PLAN).read_text(encoding="utf-8")  # dry run


def test_refuses_what_it_cannot_count(render, tmp_path):
    out = _setup(render, tmp_path)
    (out / "report.md").write_text(
        "SCENARIO A: CONFIRMED NEW — no severity\nSCENARIO B: HELD\nSCENARIO b: HELD\n", encoding="utf-8")
    r = _tool(out, "--work", "someone-else", "--summary", "<fixed / DECISION …>")
    assert r.returncode == 1
    for part in ("line 1: not `SCENARIO", "scenario 'b' reported twice", "no `PATTERN: …` line",
                 "work 'someone-else' binds no line to this plan", "does not read as a REFUTE record"):
        assert part in r.stderr, r.stderr
    assert "REFUTE" not in (out / PLAN).read_text(encoding="utf-8")


def test_a_report_of_prose_only_is_refused(render, tmp_path):
    out = _setup(render, tmp_path)
    (out / "report.md").write_text("All held, nothing found.\n", encoding="utf-8")
    r = _tool(out, "--summary", "fixed")
    assert r.returncode == 1 and "no SCENARIO line" in r.stderr


def test_markup_never_drops_a_scenario_out_of_the_count(render, tmp_path):
    # refute v2.75 r2: a numbered, checkbox, heading or quoted line was skipped silently
    out = _setup(render, tmp_path)
    (out / "report.md").write_text(
        "1. SCENARIO A: CONFIRMED BLOCKER NEW — x\n- [x] SCENARIO B: HELD\n### SCENARIO C: HELD\n"
        "> SCENARIO D: CONFIRMED MINOR NEW — y\n\n```\nSCENARIO E: HELD (a fenced template)\n```\n\n"
        "PATTERN: no common cause\n", encoding="utf-8")
    r = _tool(out, "--summary", "fixed", "--dry-run")
    assert r.returncode == 0, r.stderr
    assert "4 scenarios, 2 findings (1 blocker, 1 minor)" in r.stdout


def test_refuses_what_the_line_could_not_count_under(render, tmp_path):
    out = _setup(render, tmp_path, plan="# Plan\n\ntier: 3\nissue: acme/app#77\n")
    (out / "report.md").write_text("SCENARIO A: HELD for x; CONFIRMED MAJOR NEW for y\nPATTERN: none\n",
                                   encoding="utf-8")
    r = _tool(out, "--work", "acme/app#77", "--round", "-1", "--summary", "fixed")
    assert r.returncode == 1
    for part in ("line 1: not `SCENARIO", "binds no line to this plan", "rounds count from 1"):
        assert part in r.stderr, r.stderr
    (out / PLAN).write_text("# Plan\n\ntier: 3\n\n```md\nexample\n", encoding="utf-8")
    (out / "report.md").write_text("SCENARIO A: HELD\nPATTERN: none\n", encoding="utf-8")
    r = _tool(out, "--summary", "fixed")
    assert r.returncode == 1 and "open code fence" in r.stderr, r.stderr
