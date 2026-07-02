from pathlib import Path

import copier.errors
import pytest

FIX = Path(__file__).parent / "fixtures/existing"


def test_existing_readme_not_clobbered(render_into, tmp_path):
    # README is not shipped by the template -> no collision -> user's file untouched
    out = render_into(tmp_path, FIX, {"project_name": "d"})
    assert "my existing project" in (out / "README.md").read_text()


def test_conflict_refuses_silent_clobber(render_into, tmp_path):
    # existing AGENTS.md + request the agents_md adapter -> content conflict.
    # copier must NOT silently overwrite: non-interactive it refuses (requires
    # explicit --overwrite / interactive consent). This is the non-destructive guarantee.
    with pytest.raises(copier.errors.InteractiveSessionError):
        render_into(
            tmp_path, FIX,
            {"project_name": "d", "harnesses": {"copilot": False, "agents_md": True}},
        )
    # the user's content survived the refused run
    assert "keep me" in (tmp_path / "AGENTS.md").read_text()


def test_skip_recipe_completes_headless(render_into, tmp_path):
    # the documented headless brownfield recipe (BOOTSTRAP.md): --skip on the
    # adapter files lets a non-interactive run complete instead of aborting
    # mid-render, and leaves the user's file untouched.
    out = render_into(
        tmp_path, FIX,
        {"project_name": "d", "harnesses": {"copilot": False, "agents_md": True}},
        skip_if_exists=["AGENTS.md"],
    )
    assert "keep me" in (out / "AGENTS.md").read_text()  # user's file survived
    # the run completed: process spine and gates landed
    assert (out / "docs/process/start-here.md").exists()
    assert (out / "scripts/process/gate_runner.py").exists()
    assert (out / "CLAUDE.md").exists()


def test_idempotent_second_copy(render_into, tmp_path):
    # identical content on re-run is not a conflict -> no changes, no error
    out = render_into(tmp_path, FIX, {"project_name": "d"})
    before = {p: p.read_bytes() for p in out.rglob("*") if p.is_file()}
    render_into(out, FIX, {"project_name": "d"})  # copy again in place
    after = {p: p.read_bytes() for p in out.rglob("*") if p.is_file()}
    assert before.keys() == after.keys()
    assert all(before[k] == after[k] for k in before)
