def test_render_produces_core_and_answers(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    assert (out / "docs/process/mandatory-rules.md").is_file()
    answers = (out / ".copier-answers.yml").read_text()
    assert "_src_path" in answers            # copier stamps provenance
    assert "harnesses" in answers            # our namespaces recorded


def test_subdirectory_scope_excludes_repo_meta(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    assert not (out / "copier.yml").exists()   # template-only via _subdirectory
    assert not (out / "tests").exists()
    assert not (out / "docs/design").exists()
