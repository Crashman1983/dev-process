"""#182: a gate killed by the runner's timeout says which phase was slow.

Downstream the review gate ran 936 s, was killed at 600 s and stood in the red
ledger as `review <day>`: indistinguishable from a review finding, and the
merge train held for hours on it."""
import datetime
import json
import subprocess
import sys
from pathlib import Path

_SLOW_GATE = """import sys, time
def mark(name, kind):
    print(f"gate-phase: {name} {kind} {time.monotonic():.3f}", file=sys.stderr, flush=True)
mark("records", "start")
time.sleep(0.2)
mark("records", "done")
mark("stale_review", "start")
time.sleep(60)
"""


def _project(render, tmp_path: Path) -> Path:
    out = render(tmp_path / "p", {"project_name": "d", "modules": {}})
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=out, check=True)
    return out


def _run_with_timeout(out: Path, seconds: int) -> subprocess.CompletedProcess[str]:
    """The rendered runner with a short GATE_TIMEOUT_S: the real 600 s is not a test."""
    runner = out / "scripts/process/gate_runner.py"
    code = ("import importlib.util, sys\n"
            "sys.dont_write_bytecode = True\n"
            f"spec = importlib.util.spec_from_file_location('gr', {str(runner)!r})\n"
            "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)\n"
            f"m.GATE_TIMEOUT_S = {seconds}\n"
            "sys.exit(m.main())\n")
    return subprocess.run([sys.executable, "-c", code], cwd=out, capture_output=True, text=True)


def test_a_killed_gate_names_its_slow_phase_in_output_and_red_ledger(render, tmp_path):
    out = _project(render, tmp_path)
    (out / "scripts/slow_gate.py").write_text(_SLOW_GATE, encoding="utf-8")
    (out / "docs/process/gates.local.json").write_text(
        json.dumps({"slow": {"module": None, "command": ["scripts/slow_gate.py"]}}), encoding="utf-8")

    r = _run_with_timeout(out, 3)

    assert r.returncode == 1
    assert "killed during phase `stale_review`" in r.stderr, r.stderr
    assert "longest finished phase `records`" in r.stderr
    assert "the gate reached no verdict" in r.stdout  # the FAILED gates line
    today = datetime.date.today().isoformat()
    line = next(ln for ln in (out / ".git/process-red-ledger").read_text().splitlines()
                if ln.startswith("slow "))
    assert line.startswith(f"slow {today} exceeded 3s: killed during phase `stale_review`"), line


def test_the_red_ledger_still_reads_its_two_field_lines(render, tmp_path):
    out = _project(render, tmp_path)
    spec_code = ("import importlib.util, sys\nsys.dont_write_bytecode = True\n"
                 f"spec = importlib.util.spec_from_file_location('gr', {str(out / 'scripts/process/gate_runner.py')!r})\n"
                 "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)\n"
                 "from pathlib import Path\n"
                 "p = Path(sys.argv[1])\n"
                 "p.write_text('review 2026-09-01\\nslow 2026-09-02 exceeded 600s: killed during phase `x`\\n')\n"
                 "print(m._read_red(p))\n")
    r = subprocess.run([sys.executable, "-c", spec_code, str(tmp_path / "ledger")],
                       capture_output=True, text=True)
    assert r.stdout.strip() == "{'review': '2026-09-01', 'slow': '2026-09-02'}", r.stdout + r.stderr


def test_phase_marks_stay_out_of_a_normal_run(render, tmp_path):
    out = _project(render, tmp_path)
    r = subprocess.run([sys.executable, str(out / "scripts/process/gate_runner.py")],
                       cwd=out, capture_output=True, text=True)
    assert "== running review ==" in r.stdout
    assert "gate-phase:" not in r.stdout + r.stderr
    direct = subprocess.run([sys.executable, str(out / "scripts/process/check_review.py"), "."],
                            cwd=out, capture_output=True, text=True)
    assert "gate-phase: records start" in direct.stderr  # the gate itself reports them


def test_tower_train_and_digest_show_the_reason_and_the_right_age(render, tmp_path):
    # the ledger has three readers besides the runner's own; a third field
    # must not turn the date into "red since <date> <reason>" with age 0
    out = _project(render, tmp_path)
    old = (datetime.date.today() - datetime.timedelta(days=5)).isoformat()
    (out / ".git/process-red-ledger").write_text(
        f"review {old} exceeded 600s: killed during phase `stale_review` (600 s in)\n", encoding="utf-8")
    tower = subprocess.run([sys.executable, str(out / "scripts/process/tower.py"), "--json"],
                           cwd=out, capture_output=True, text=True)
    gates = json.loads(tower.stdout)["gates"]
    assert gates == [{"gate": "review", "since": old, "age_days": 5,
                      "reason": "exceeded 600s: killed during phase `stale_review` (600 s in)"}], gates
    digest = subprocess.run([sys.executable, str(out / "scripts/process/human_digest.py")],
                            cwd=out, capture_output=True, text=True)
    assert f"**review** red since {old} (5 day(s)) (exceeded 600s: killed during phase `stale_review`" \
        in digest.stdout, digest.stdout + digest.stderr
