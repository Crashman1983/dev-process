import re

CORE = [
    "start-here.md",
    "mandatory-rules.md",
    "risk-tiers.md",
    "workflow.md",
    "commits.md",
    "code-craft.md",
    "verification-independence.md",
    "review-checklist.md",
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


def test_start_here_names_anchor_discriminator(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    text = (out / "docs/process/start-here.md").read_text()
    assert "## Anchors" in text
    assert "drift" in text and "refactor" in text  # the discriminator, reword-robust
    assert "per subtree" in text or "per-area anchors" in text  # scaling note


def test_review_checklist_covers_security_sink(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    text = (out / "docs/process/review-checklist.md").read_text()
    assert "## Security" in text
    assert "redirect" in text and "sink" in text  # the untrusted-input-to-sink class
    assert "one owner" in text.lower()  # design/one-owner question
    assert "## Performance" in text and "N+1" in text  # performance dimension
    assert "## Observability" in text and "fail fast" in text  # ops dimension


def test_risk_tiers_recognition_questions(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    text = (out / "docs/process/risk-tiers.md").read_text()
    assert "Recognizing your tier" in text
    assert "persistence" in text and "untrusted" in text


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


def test_start_here_guides_greenfield_and_brownfield(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    text = (out / "docs/process/start-here.md").read_text()
    for required in [
        "## First run",
        "## LLM-guided onboarding",
        "## Greenfield start",
        "## Brownfield start",
        "Question",
        "Question compass",
        "do not invent",
        "ARCHITECTURE.md",
        "docs/process/feature-registry/",
        "scripts/process/gate_runner.py",
        ".process-work/",
    ]:
        assert required in text, required


def test_start_here_stack_compass_covers_layers_and_proposal_mode(render, tmp_path):
    # the tech dialogue must decompose the stack into the concrete layers and
    # instruct the LLM to propose confirmed options where the user has no
    # preference — otherwise proposals depend on the model's temperament, not
    # on the process.
    out = render(tmp_path, {"project_name": "demo"})
    text = (out / "docs/process/start-here.md").read_text()
    for required in [
        # the stack layers
        "Frontend", "Backend", "Storage", "API/communication", "Deployment",
        # proposal mode: derive options, name trade-offs, confirm
        "proposal mode", "trade-offs", "recommendation",
        # the API answer feeds the module heuristic
        "contract-first", "contracts-drift",
        # confirmed fundamentals land in the existing decision mechanics
        "ADR",
    ]:
        assert required in text, required


def test_commits_doc_names_isolation_invariant_and_both_merge_routes(render, tmp_path):
    # branches are the default and hosted PR/MR merging is a first-class route;
    # a worktree is one isolation option, not a mandate — otherwise the doc is
    # unfollowable in environments with protected branches or fresh clones.
    out = render(tmp_path, {"project_name": "demo"})
    text = " ".join((out / "docs/process/commits.md").read_text().split())
    assert "feature branch" in text.lower()
    assert "worktree" in text.lower()             # still named as an option...
    assert "one isolation technique" in text      # ...but explicitly not a mandate
    assert "--ff-only" in text                    # local route
    assert "pull/merge request" in text           # hosted route
    assert "process-gates" in text                # CI job is part of the hosted gate
    assert "one logical change per PR" in text    # squash-merge adaptation


def test_adr_template_has_intent_axis(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    text = (out / "docs/process/adr/template.md").read_text()
    assert "## Intent" in text
    for v in ["keep", "change-planned", "tolerated"]:
        assert v in text, v
