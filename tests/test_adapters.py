import re


def _kernel(text):
    m = re.search(r"<!-- KERNEL:START -->(.*?)<!-- KERNEL:END -->", text, re.S)
    return m.group(1).strip() if m else None


def test_claude_adapter_always_present(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    p = out / "CLAUDE.md"
    assert p.is_file()
    text = p.read_text()
    assert "docs/process/" in text                 # pointer to SSOT
    assert _kernel(text) is not None               # inlined kernel
    assert "demo" in text                          # project_name interpolated
    assert not re.search(r"{{|{%|{#", text)        # no jinja leak


def test_copilot_conditional(render, tmp_path):
    off = render(tmp_path / "off", {"project_name": "d"})
    assert not (off / ".github/copilot-instructions.md").exists()
    on = render(
        tmp_path / "on",
        {"project_name": "d", "harnesses": {"copilot": True, "agents_md": False}},
    )
    assert (on / ".github/copilot-instructions.md").is_file()
    assert (on / ".github/instructions/process.instructions.md").is_file()


def test_agents_md_conditional(render, tmp_path):
    on = render(
        tmp_path / "on",
        {"project_name": "d", "harnesses": {"copilot": False, "agents_md": True}},
    )
    assert (on / "AGENTS.md").is_file()


def test_kernel_identical_across_adapters(render, tmp_path):
    out = render(
        tmp_path,
        {"project_name": "d", "harnesses": {"copilot": True, "agents_md": True}},
    )
    blocks = [
        _kernel((out / f).read_text())
        for f in ["CLAUDE.md", ".github/copilot-instructions.md", "AGENTS.md"]
    ]
    assert blocks[0] and blocks.count(blocks[0]) == 3, "kernel must be byte-identical across adapters"


def test_adapters_point_to_start_here(render, tmp_path):
    out = render(
        tmp_path,
        {"project_name": "d", "harnesses": {"copilot": True, "agents_md": True}},
    )
    for rel in ["CLAUDE.md", ".github/copilot-instructions.md", "AGENTS.md"]:
        text = (out / rel).read_text()
        assert "docs/process/start-here.md" in text


def test_doc_drift_scans_copilot_instructions_file(render, tmp_path):
    # SP52: the one auto-applied Copilot file must not be a drift blind spot
    import subprocess
    import sys
    out = render(tmp_path, {"project_name": "d",
                            "harnesses": {"copilot": True, "agents_md": False},
                            "modules": {"doc_drift_gate": True}})
    f = out / ".github/instructions/process.instructions.md"
    assert f.is_file()
    f.write_text(f.read_text() + "\nSee `docs/process/nonexistent-file.md`.\n")
    r = subprocess.run(
        [sys.executable, str(out / "scripts/process/check_doc_drift.py"), str(out)],
        capture_output=True, text=True)
    assert r.returncode == 1, r.stdout
    assert "nonexistent-file.md" in r.stdout
