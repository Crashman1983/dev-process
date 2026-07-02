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
