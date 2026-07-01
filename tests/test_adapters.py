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
