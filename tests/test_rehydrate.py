"""rehydrate.py: the SessionStart hook that prints what /prime reads after a
compaction, and installs itself into .claude/settings.json without touching
the rest of the file."""
import json
import subprocess
import sys


def _run(out, *args):
    return subprocess.run([sys.executable, str(out / "scripts/process/rehydrate.py"), *args],
                          cwd=out, capture_output=True, text=True)


def _git(out):
    subprocess.run(["git", "init", "-q", "-b", "feat-x"], cwd=out, check=True)


def test_hook_prints_kernel_rules_and_ledger_only(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    _git(out)
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
    assert "feat-x" in text
    assert "<!-- KERNEL:START -->" not in text  # the block, not the file around it
    assert len(text) < 12000  # every compaction pays for this


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
