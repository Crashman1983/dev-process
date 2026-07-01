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
