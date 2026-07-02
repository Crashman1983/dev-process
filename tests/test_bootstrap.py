from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_bootstrap_has_exact_copier_command():
    text = (ROOT / "BOOTSTRAP.md").read_text()
    assert "uvx copier copy gh:Crashman1983/dev-process ." in text


def test_readme_points_at_bootstrap():
    assert "BOOTSTRAP" in (ROOT / "README.md").read_text()


def test_bootstrap_points_to_rendered_start_here():
    text = (ROOT / "BOOTSTRAP.md").read_text()
    assert "docs/process/start-here.md" in text


def test_bootstrap_documents_headless_setup():
    # agent harnesses have no TTY for copier's prompts: BOOTSTRAP must carry a
    # complete non-interactive recipe (--defaults + --data + --skip) and forbid
    # the destructive --overwrite escape hatch.
    text = (ROOT / "BOOTSTRAP.md").read_text()
    assert "copier copy --defaults" in text
    assert "--data 'harnesses={" in text
    assert "--data 'modules={" in text
    assert "--skip 'CLAUDE.md' --skip 'AGENTS.md'" in text
    assert "KERNEL:START" in text  # merge recipe for skipped adapter files


def test_bootstrap_requires_post_install_verification():
    # mandatory rule 1 applied to the installer itself: claim "installed" only
    # after the gates ran green.
    text = (ROOT / "BOOTSTRAP.md").read_text()
    assert "python scripts/process/gate_runner.py" in text
    assert "git status --porcelain" in text


def test_retrofit_recipe_uses_update_data_not_answers_file_edit():
    # copier update reads .copier-answers.yml as the OLD state: after a hand
    # edit, old and new render are identical and the module files count as
    # intentional local deletions -> the module is never rendered. The only
    # working retrofit recipe is `copier update --data`.
    bootstrap = (ROOT / "BOOTSTRAP.md").read_text()
    readme = (ROOT / "README.md").read_text()
    assert "copier update --defaults" in bootstrap
    assert "--data 'modules={" in bootstrap
    assert "Do not hand-edit `.copier-answers.yml`" in bootstrap
    assert "copier update --defaults --data 'modules={…}'" in readme
    # the broken recipe must not resurface
    assert "(or edit" not in bootstrap
    assert ".copier-answers.yml` ändern" not in readme
