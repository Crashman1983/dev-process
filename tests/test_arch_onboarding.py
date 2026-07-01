import os
import subprocess
import sys
from pathlib import Path


def _render(render, tmp_path, **mods):
    m = {"arch_onboarding": True}
    m.update(mods)
    return render(tmp_path, {"project_name": "d", "modules": m})


def _run(out: Path, extra_path: str | None = None):
    env = dict(os.environ)
    if extra_path:
        env["PATH"] = f"{extra_path}{os.pathsep}" + env["PATH"]
    return subprocess.run(
        [sys.executable, str(out / "scripts/process/check_architecture.py"), str(out)],
        capture_output=True, text=True, env=env,
    )


def _write_arch(out: Path, block: str, fence: str = "arch"):
    (out / "ARCHITECTURE.md").write_text(
        f"# Architecture\n\nnarrative\n\n```{fence}\n{block}\n```\n"
    )


def test_module_files_present_when_on(render, tmp_path):
    out = _render(render, tmp_path)
    assert (out / "scripts/process/check_architecture.py").is_file()
    assert (out / "docs/process/modules/arch-onboarding.md").is_file()
    assert (out / "ARCHITECTURE.md").is_file()


def test_module_files_absent_when_off(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    assert not (out / "scripts/process/check_architecture.py").exists()
    assert not (out / "docs/process/modules/arch-onboarding.md").exists()
    assert not (out / "ARCHITECTURE.md").exists()


def test_seed_is_inert(render, tmp_path):
    out = _render(render, tmp_path)  # ships ARCHITECTURE.md with ```arch-example
    r = _run(out)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "not onboarded" in r.stdout


def test_no_architecture_md(render, tmp_path):
    out = _render(render, tmp_path)
    (out / "ARCHITECTURE.md").unlink()
    r = _run(out)
    assert r.returncode == 0
    assert "not onboarded" in r.stdout


def test_no_arch_block(render, tmp_path):
    out = _render(render, tmp_path)
    (out / "ARCHITECTURE.md").write_text("# Architecture\n\njust prose, no block\n")
    r = _run(out)
    assert r.returncode == 0
    assert "not onboarded" in r.stdout


CLEAN_BLOCK = """\
code_roots: [src]
layers:
  domain: {path: src/domain}
  infra:  {path: src/infra}
interfaces:
  - {name: OrderPort, path: src/domain/ports.py}
"""


def _seed_code(out: Path):
    (out / "src/domain").mkdir(parents=True, exist_ok=True)
    (out / "src/infra").mkdir(parents=True, exist_ok=True)
    (out / "src/domain/ports.py").write_text("class OrderPort:\n    ...\n")


def test_existence_pass(render, tmp_path):
    out = _render(render, tmp_path)
    _seed_code(out)
    _write_arch(out, CLEAN_BLOCK)
    r = _run(out)
    assert r.returncode == 0, r.stdout
    assert "OK" in r.stdout


def test_layer_path_missing(render, tmp_path):
    out = _render(render, tmp_path)
    _seed_code(out)
    (out / "src/infra").rmdir()
    _write_arch(out, CLEAN_BLOCK)
    r = _run(out)
    assert r.returncode == 1
    assert "infra" in r.stdout


def test_interface_symbol_missing(render, tmp_path):
    out = _render(render, tmp_path)
    _seed_code(out)
    (out / "src/domain/ports.py").write_text("class Something:\n    ...\n")
    _write_arch(out, CLEAN_BLOCK)
    r = _run(out)
    assert r.returncode == 1
    assert "OrderPort" in r.stdout


def test_rule_unknown_layer(render, tmp_path):
    out = _render(render, tmp_path)
    _seed_code(out)
    block = CLEAN_BLOCK + "rules:\n  - {forbid: domain -> nope}\n"
    _write_arch(out, block)
    r = _run(out)
    assert r.returncode == 1
    assert "nope" in r.stdout


def test_forward_compat_unknown_key_ignored(render, tmp_path):
    out = _render(render, tmp_path)
    _seed_code(out)
    block = CLEAN_BLOCK + "external:\n  repos: [{name: billing, url: 'gh:o/billing'}]\n"
    _write_arch(out, block)
    r = _run(out)
    assert r.returncode == 0, r.stdout
