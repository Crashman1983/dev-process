import shutil
from pathlib import Path

import copier
import pytest

REPO = Path(__file__).resolve().parent.parent  # holds copier.yml + template/


@pytest.fixture(scope="session")
def _template_src(tmp_path_factory):
    # Render from a git-free snapshot of the template so copier copies the
    # working tree directly: deterministic and inclusive of files added since
    # the last release tag. Rendering straight from the git repo would pin to
    # that tag, hiding any template file committed (or still uncommitted)
    # after it — which would make every new module untestable.
    snap = tmp_path_factory.mktemp("template-src")
    shutil.copy2(REPO / "copier.yml", snap / "copier.yml")
    shutil.copytree(REPO / "template", snap / "template")
    return snap


def _copy(src: Path, dst: Path, data: dict) -> Path:
    full = {
        "harnesses": {"copilot": False, "agents_md": False},
        "modules": {"doc_drift_gate": False, "arch_onboarding": False, "feature_registry": False, "github_issues": False, "contracts_drift": False},
    }
    full.update(data)
    copier.run_copy(str(src), str(dst), data=full, defaults=True, unsafe=True, quiet=True)
    return dst


@pytest.fixture
def render(_template_src):
    def _f(dst: Path, data: dict) -> Path:
        return _copy(_template_src, dst, data)

    return _f


@pytest.fixture
def render_into(_template_src):
    def _f(dst: Path, seed: Path, data: dict) -> Path:
        shutil.copytree(seed, dst, dirs_exist_ok=True)
        return _copy(_template_src, dst, data)

    return _f
