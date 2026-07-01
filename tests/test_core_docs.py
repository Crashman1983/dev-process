import re

CORE = [
    "mandatory-rules.md",
    "risk-tiers.md",
    "workflow.md",
    "commits.md",
    "code-craft.md",
    "journal-state-plans.md",
    "adr/README.md",
    "adr/template.md",
]
KENNI = ["KenniNext", "Kenni", "user_id=1", "Seb", "Signal", "SvelteKit"]


def test_core_docs_present_and_clean(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    for rel in CORE:
        p = out / "docs/process" / rel
        assert p.is_file(), rel
        text = p.read_text()
        assert not re.search(r"{{|{%|{#", text), f"jinja leak in {rel}"
        for k in KENNI:
            assert k not in text, f"kenni-specific '{k}' leaked in {rel}"


def test_mandatory_rules_required_headings(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    text = (out / "docs/process/mandatory-rules.md").read_text()
    for h in [
        "Verification before assertion",
        "Plan before substantive work",
        "One owner per behavior",
        "Root cause before symptom",
        "Atomic commits",
        "Code is written to be read",
    ]:
        assert h in text, h


def test_risk_tiers_matrix(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    text = (out / "docs/process/risk-tiers.md").read_text()
    for t in ["Tier 0", "Tier 1", "Tier 2", "Tier 3", "Tier 4"]:
        assert t in text, t


def test_adr_template_has_intent_axis(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    text = (out / "docs/process/adr/template.md").read_text()
    assert "## Intent" in text
    for v in ["keep", "change-planned", "tolerated"]:
        assert v in text, v
