import shutil
import subprocess
import sys

import pytest

# Module-gated scripts are named `{% ... %}name.py{% endif %}` or `name.py.jinja`,
# so the template repo's own `ruff check .` never lints their *source*. But
# copier renders them to real `.py` files in every consumer project — where the
# process's own lint gate then runs. This test renders the full template and
# lints the rendered Python, so a lint defect in a module-gated script (an unused
# import, dead variable, …) cannot ship invisibly again.

ALL_MODULES = {
    "doc_drift_gate": True, "arch_onboarding": True, "feature_registry": True,
    "github_issues": True, "contracts_drift": True, "git_hooks": True,
    "contract_first": True, "parity": True, "security_floor": True,
    "telemetry": True, "arch_docs": True, "github_master": True,
}


@pytest.mark.skipif(shutil.which("ruff") is None, reason="ruff not on PATH")
def test_rendered_process_scripts_are_ruff_clean(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo", "modules": ALL_MODULES})
    scripts = out / "scripts" / "process"
    assert scripts.is_dir()
    py = sorted(str(p) for p in scripts.glob("*.py"))
    assert py, "no rendered process scripts to lint"
    r = subprocess.run(["ruff", "check", *py], capture_output=True, text=True)
    assert r.returncode == 0, f"ruff on rendered scripts:\n{r.stdout}\n{r.stderr}"


@pytest.mark.skipif(shutil.which("ruff") is None, reason="ruff not on PATH")
def test_rendered_process_scripts_are_valid_python(render, tmp_path):
    # a compile check even where ruff is absent-tolerant: every rendered script
    # must at least parse
    out = render(tmp_path, {"project_name": "demo", "modules": ALL_MODULES})
    for p in sorted((out / "scripts" / "process").glob("*.py")):
        r = subprocess.run([sys.executable, "-m", "py_compile", str(p)],
                           capture_output=True, text=True)
        assert r.returncode == 0, f"{p.name} does not compile:\n{r.stderr}"
