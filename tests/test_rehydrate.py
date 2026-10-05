"""rehydrate.py: the SessionStart hook that prints what /prime reads after a
compaction, and installs itself into .claude/settings.json without touching
the rest of the file."""
import json
import subprocess
import sys


def _run(out, *args):
    return subprocess.run([sys.executable, str(out / "scripts/process/rehydrate.py"), *args],
                          cwd=out, capture_output=True, text=True)


def _git(out, branch="feat-x"):
    subprocess.run(["git", "init", "-q", "-b", branch], cwd=out, check=True)


def test_hook_prints_kernel_rules_and_ledger_only(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    _git(out, "feat/12-panel")
    d = out / ".process-work/plans"
    d.mkdir(parents=True, exist_ok=True)
    (d / "2026-09-10-panel.md").write_text(
        "# Plan\n\ntier: 2\nissue: #12\n\n## Decisions\n"
        "- DECISION 2026-09-10 owner: variant B — because one owner\n"
        "- DECISION NEEDED 2026-09-11 panel: keep CSV? — options: A, B; recommendation: B\n")
    r = _run(out)
    assert r.returncode == 0, r.stderr
    text = r.stdout
    assert "## Always-on kernel" in text and "Load-bearing" in text
    assert "## Mandatory rules (full text)" in text and "Verify before asserting" in text
    assert "DECISION 2026-09-10 owner: variant B" in text
    assert "OPEN QUESTION (do not decide it yourself): DECISION NEEDED 2026-09-11 panel: keep CSV?" in text
    assert "feat/12-panel" in text
    assert "<!-- KERNEL:START -->" not in text  # the block, not the file around it
    assert len(text) < 12000  # every compaction pays for this
    # a plan that became a log (113 decisions downstream): only the latest ride along
    (d / "2026-09-11-log.md").write_text(
        "# L\n\ntier: 2\nissue: #12\n\n## Decisions\n" + "".join(f"- DECISION 2026-09-11 owner: d{i} — because\n" for i in range(40)))
    text = _run(out).stdout
    assert "28 earlier decisions in the plan" in text and "d39" in text and "d11" not in text


def test_hook_stays_bounded_with_forty_plans_and_specs(render, tmp_path):
    """every compaction re-rendered every plan and spec; downstream that grew with the repo"""
    out = render(tmp_path, {"project_name": "d", "modules": {"speckit": True}})
    _git(out, "feat/7-login")
    plans = out / ".process-work/plans"
    plans.mkdir(parents=True, exist_ok=True)
    ledger = "".join(f"- DECISION 2026-10-01 owner: choice {i} — because reason\n" for i in range(12))
    for i in range(1, 41):
        (plans / f"2026-10-01-p{i}.md").write_text(f"# P\n\ntier: 2\nissue: #{i}\n\n## Decisions\n{ledger}")
        s = out / "specs" / f"{i:03d}-s{i}"
        s.mkdir(parents=True)
        (s / "spec.md").write_text(f"# S\n\nissue: #{100 + i}\n")
        (s / "tasks.md").write_text("- [ ] T001 a\n")
    (plans / "2026-10-01-p7.md").write_text("# P\n\ntier: 2\nissue: #7\n\n## Decisions\n"
                                            "- DECISION 2026-10-01 owner: in-scope marker — because test\n")
    text = _run(out).stdout
    assert "DECISION 2026-10-01 owner: in-scope marker" in text  # the branch's own plan, in full
    assert "+69 more" in text  # the other 79 items: one capped line
    assert "choice 3" not in text  # no other plan's ledger
    assert len(text) < 13000  # unscoped, this fixture prints well over 40k


def test_install_is_idempotent_and_keeps_the_projects_settings(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    _git(out)
    s = out / ".claude/settings.json"
    s.parent.mkdir(parents=True, exist_ok=True)
    s.write_text(json.dumps({"permissions": {"allow": ["Read"]},
                             "hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "./setup.sh"}]}]}}))
    assert _run(out, "--check").returncode == 1
    r = _run(out, "--install")
    assert r.returncode == 0 and "added" in r.stdout
    data = json.loads(s.read_text())
    assert data["permissions"] == {"allow": ["Read"]}
    starts = data["hooks"]["SessionStart"]
    assert starts[0]["hooks"][0]["command"] == "./setup.sh"
    assert starts[1]["matcher"] == "compact|resume"
    assert "rehydrate.py" in starts[1]["hooks"][0]["command"]
    assert _run(out, "--check").returncode == 0
    r = _run(out, "--install")
    assert "already" in r.stdout and len(json.loads(s.read_text())["hooks"]["SessionStart"]) == 2
    # no settings file at all: one is created with just the hook
    s.unlink()
    assert _run(out, "--install").returncode == 0
    assert list(json.loads(s.read_text())) == ["hooks"]
