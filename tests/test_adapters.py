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
