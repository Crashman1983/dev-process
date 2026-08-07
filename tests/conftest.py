import json
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


def _copy(src: Path, dst: Path, data: dict, **kwargs) -> Path:
    full = {
        "harnesses": {"claude": True, "copilot": False, "agents_md": False},
        "modules": {"speckit": False, "doc_drift_gate": False, "arch_onboarding": False, "feature_registry": False, "github_issues": False, "contracts": False, "git_hooks": False, "security_floor": False, "sbom": False, "telemetry": False, "arch_docs": False, "github_master": False},
        "ci": {"github": True},
    }
    # merge partial harnesses/modules dicts over the defaults — a test passing
    # {"copilot": True} keeps claude on, matching the old `| default(true)`
    # semantics that lived in the (Windows-hostile) template path names
    data = dict(data)
    for key in ("harnesses", "modules", "ci"):
        if key in data:
            full[key] = {**full[key], **data.pop(key)}
    full.update(data)
    copier.run_copy(str(src), str(dst), data=full, defaults=True, unsafe=True, quiet=True, **kwargs)
    return dst


@pytest.fixture(scope="session")
def _rendered(_template_src, tmp_path_factory):
    """Render each distinct answer set once per session and hand out copies.

    A render costs ~1.5s of fixed copier startup (parse copier.yml, build the
    Jinja environment, walk the template) no matter how small the result is,
    and the suite asks for one per test. Copying an already-rendered tree is
    ~13x cheaper, so the answers — not the test — decide when work happens.
    Every caller still gets its own writable tree; the cached one is never
    handed out.
    """
    root = tmp_path_factory.mktemp("rendered")
    store: dict[str, Path] = {}

    def _get(raw: bool, data: dict, kwargs: dict) -> Path:
        key = json.dumps([raw, data, kwargs], sort_keys=True, default=repr)
        if key not in store:
            src = root / f"r{len(store)}"
            if raw:
                copier.run_copy(str(_template_src), str(src), data=data,
                                defaults=True, unsafe=True, quiet=True, **kwargs)
            else:
                _copy(_template_src, src, data, **kwargs)
            store[key] = src
        return store[key]

    return _get


@pytest.fixture
def render(_rendered):
    def _f(dst: Path, data: dict, **kwargs) -> Path:
        shutil.copytree(_rendered(False, data, kwargs), dst, dirs_exist_ok=True)
        return dst

    return _f


@pytest.fixture
def render_raw(_rendered):
    """Render passing ONLY the given answers — unlike `render`, no full modules
    dict is injected, so profile-derived module defaults actually apply."""

    def _f(dst: Path, data: dict, **kwargs) -> Path:
        shutil.copytree(_rendered(True, data, kwargs), dst, dirs_exist_ok=True)
        return dst

    return _f


@pytest.fixture
def render_into(_template_src):
    # Not cached: this one renders *onto* an existing seed, so the result
    # depends on what is already there, not on the answers alone.
    def _f(dst: Path, seed: Path, data: dict, **kwargs) -> Path:
        shutil.copytree(seed, dst, dirs_exist_ok=True)
        return _copy(_template_src, dst, data, **kwargs)

    return _f
