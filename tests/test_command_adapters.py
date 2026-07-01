import subprocess
import sys

KENNI = ["Kenni", "KenniNext", "Seb", "Signal", "SvelteKit", "user_id=1", "surface:ios"]
# structural Kenni anchors that must never leak into a neutral command pointer
# (each has zero legitimate use in a thin harness-agnostic command file)
KENNI_STRUCTURAL = ["PRD.md", "ARCHITECTURE.md", "api-contract.md", "make test", "make dev-context"]

COMMANDS = ["brainstorm", "plan", "execute", "review", "quick", "debug", "commit", "prime"]


def _run_gate(out):
    script = out / "scripts/process/check_doc_drift.py"
    return subprocess.run(
        [sys.executable, str(script), str(out)], capture_output=True, text=True
    )


# --- enforcement hook: doc_drift must actually scan the command directories ---
# A positive (clean-tree) test proves nothing about scan scope — it is green
# whether or not the dir is scanned. Only a planted-broken-ref test per new
# SCAN_DIR proves the wiring; a typo in one SCAN_DIRS entry would silently scan
# nothing and every positive test would still pass.


def test_doc_drift_scans_claude_commands(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {"doc_drift_gate": True}})
    cmds = out / ".claude/commands"
    cmds.mkdir(parents=True, exist_ok=True)
    (cmds / "broken.md").write_text("See `docs/process/does-not-exist.md`.")
    r = _run_gate(out)
    assert r.returncode == 1
    assert "does-not-exist.md" in (r.stdout + r.stderr)


def test_doc_drift_scans_copilot_prompts(render, tmp_path):
    out = render(
        tmp_path,
        {"project_name": "d", "modules": {"doc_drift_gate": True}, "harnesses": {"copilot": True}},
    )
    prompts = out / ".github/prompts"
    prompts.mkdir(parents=True, exist_ok=True)
    (prompts / "broken.prompt.md").write_text("See `docs/process/does-not-exist.md`.")
    r = _run_gate(out)
    assert r.returncode == 1
    assert "does-not-exist.md" in (r.stdout + r.stderr)


# --- ship-set behaviour ---


def test_claude_commands_always_ship(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})  # every module + harness off
    for name in COMMANDS:
        assert (out / ".claude/commands" / f"{name}.md").is_file(), name


def test_shipped_commands_drift_clean(render, tmp_path):
    # render everything; every real slash-ref in every shipped command file
    # (and the AGENTS.md section) must resolve, so the gate exits 0.
    out = render(
        tmp_path,
        {
            "project_name": "d",
            "modules": {"doc_drift_gate": True},
            "harnesses": {"copilot": True, "agents_md": True},
        },
    )
    r = _run_gate(out)
    assert r.returncode == 0, r.stdout + r.stderr


def test_copilot_prompts_gated(render, tmp_path):
    off = render(tmp_path / "off", {"project_name": "d"})
    assert not (off / ".github/prompts").exists()
    on = render(tmp_path / "on", {"project_name": "d", "harnesses": {"copilot": True}})
    for name in COMMANDS:
        assert (on / ".github/prompts" / f"{name}.prompt.md").is_file(), name
