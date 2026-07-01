from pathlib import Path

import copier
import pytest

SRC = Path(__file__).resolve().parent.parent  # repo root (holds copier.yml)


def _copy(dst: Path, data: dict) -> Path:
    full = {
        "harnesses": {"copilot": False, "agents_md": False},
        "modules": {"doc_drift_gate": False},
    }
    full.update(data)
    copier.run_copy(str(SRC), str(dst), data=full, defaults=True, unsafe=True, quiet=True)
    return dst


@pytest.fixture
def render():
    return _copy
