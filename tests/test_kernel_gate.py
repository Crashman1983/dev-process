import importlib.util
import subprocess
import sys
from pathlib import Path


def _render(render, tmp_path, **data):
    d = {"project_name": "d"}
    d.update(data)
    return render(tmp_path, d)


def _load(out: Path):
    path = out / "scripts/process/check_kernel.py"
    spec = importlib.util.spec_from_file_location("check_kernel", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_gate_present_and_core(render, tmp_path):
    out = _render(render, tmp_path)
    assert (out / "scripts/process/check_kernel.py").is_file()
    # registered as a core gate (module key None), and first
    gr = (out / "scripts/process/gate_runner.py").read_text()
    assert '"kernel": (None,' in gr


def test_fresh_render_passes(render, tmp_path):
    # a freshly rendered project (CLAUDE.md carries the kernel) must pass
    out = _render(render, tmp_path)
    mod = _load(out)
    hard, soft = mod.check(out)
    assert hard == [], hard


def test_dropped_rule_fails(render, tmp_path):
    out = _render(render, tmp_path)
    mod = _load(out)
    anchor = out / "CLAUDE.md"
    text = anchor.read_text()
    # drop a line from inside the kernel block (a rule silently removed)
    block = mod._block(text)
    tampered = text.replace("6. Root cause before symptom.", "")
    assert tampered != text
    anchor.write_text(tampered)
    hard, _ = mod.check(out)
    assert any("drifted" in h and "CLAUDE.md" in h for h in hard), hard


def test_missing_block_fails(render, tmp_path):
    out = _render(render, tmp_path)
    mod = _load(out)
    anchor = out / "CLAUDE.md"
    # strip the whole kernel block out of the anchor
    import re
    stripped = re.sub(r"<!-- KERNEL:START -->.*?<!-- KERNEL:END -->", "X",
                      anchor.read_text(), flags=re.S)
    anchor.write_text(stripped)
    hard, _ = mod.check(out)
    assert any("block is missing" in h for h in hard), hard


def test_no_anchor_is_advisory(render, tmp_path):
    out = _render(render, tmp_path)
    mod = _load(out)
    (out / "CLAUDE.md").unlink()  # the only anchor on the default profile
    hard, soft = mod.check(out)
    assert hard == []
    assert any("no anchor carries the kernel" in s for s in soft)


def test_missing_kernel_doc_fails(render, tmp_path):
    out = _render(render, tmp_path)
    mod = _load(out)
    (out / "docs/process/kernel.md").unlink()
    hard, _ = mod.check(out)
    assert any("canonical kernel source is gone" in h for h in hard)


def test_kernel_carries_compaction_directive(render, tmp_path):
    # the self-restoring directive must live inside the kernel block so it rides
    # along with any surviving fragment and the gate's byte-identity keeps it.
    out = _render(render, tmp_path)
    mod = _load(out)
    canonical = mod._block((out / "docs/process/kernel.md").read_text())
    assert canonical is not None
    assert "resuming" in canonical and "compacted" in canonical
    assert "re-read" in canonical and "mandatory-rules.md" in canonical
    # the anchor block must equal the canonical doc block (the gate's invariant)
    assert mod._block((out / "CLAUDE.md").read_text()) == canonical


def test_all_adapters_render_gate_green(render, tmp_path):
    # with every anchor present, the gate runner passes on a fresh render
    out = render(tmp_path, {"project_name": "d",
                            "harnesses": {"copilot": True, "agents_md": True}})
    r = subprocess.run([sys.executable, str(out / "scripts/process/check_kernel.py"), str(out)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout
    assert "kernel: OK" in r.stdout
