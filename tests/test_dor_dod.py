def test_dor_dod_doc_present_and_binding(render, tmp_path):
    # the DoR/DoD checklist is a core process doc: present even with no modules
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    dod = out / "docs/process/definition-of-ready-and-done.md"
    assert dod.is_file()
    text = dod.read_text(encoding="utf-8")
    assert "Definition of Ready" in text and "Definition of Done" in text
    # binding + living
    assert "always evaluated" in text and "documented, justified deviation" in text
    assert "Amending these checklists" in text
    # per-work-item, explicitly distinguished from project onboarding
    assert "not" in text and "project-onboarding" in text.replace("project onboarding", "project-onboarding")


def test_dor_dod_wired_into_phases_and_rules(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    ref = "definition-of-ready-and-done.md"
    assert ref in (out / "docs/process/workflow.md").read_text(encoding="utf-8")
    assert ref in (out / "docs/process/mandatory-rules.md").read_text(encoding="utf-8")
    assert ref in (out / "docs/process/review-checklist.md").read_text(encoding="utf-8")


def test_start_here_disambiguates_onboarding_readiness(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    text = (out / "docs/process/start-here.md").read_text(encoding="utf-8")
    # the onboarding-readiness heading is disambiguated and points at the per-item doc
    assert "Definition of ready (project onboarding)" in text
    assert "definition-of-ready-and-done.md" in text


def test_ears_pattern_catalog_present(render, tmp_path):
    # SP53: all five EARS patterns named, unwanted-behaviour tied to the
    # negative cases R2 requires
    out = render(tmp_path, {"project_name": "d"})
    text = (out / "docs/process/definition-of-ready-and-done.md").read_text()
    for pat in ("Ubiquitous", "Event-driven", "State-driven",
                "Unwanted behaviour", "Optional feature"):
        assert pat in text, pat
    assert "While <state>" in text and "If <undesired condition>" in text
