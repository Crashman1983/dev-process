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


def test_verification_independence_names_enforcement_gate(render, tmp_path):
    # SP19: the attestation is gated, not just prose. The doc must name the gate,
    # the arithmetic, and the presence check — and stay honest that identity is
    # attested, not machine-verified.
    out = render(tmp_path, {"project_name": "demo"})
    text = (out / "docs/process/verification-independence.md").read_text()
    assert "## Enforcement" in text
    assert "check_review.py" in text
    assert "REVIEW" in text and "single-family" in text
    assert "review-waived" in text
    assert "attested" in text  # identity truthfulness stays attested


def test_mandatory_rules_rule7_names_gated_attestation(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    text = (out / "docs/process/mandatory-rules.md").read_text()
    assert "REVIEW" in text and "attestation" in text
    assert "review-waived" in text


def test_journal_state_plans_documents_tier_field_and_review_record(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    text = (out / "docs/process/journal-state-plans.md").read_text()
    assert "tier: N" in text  # machine-readable plan tier field
    assert "## Review attestations" in text
    assert "REVIEW work=" in text
    assert "independence" in text


def test_mandatory_rules_names_decision_records_and_patch_count(render, tmp_path):
    # rule 4 must anchor the decision-record duty and the increment-vs-rewrite
    # call, otherwise significant non-feature decisions have no home and the
    # third-patch trap stays unguarded.
    out = render(tmp_path, {"project_name": "demo"})
    text = (out / "docs/process/mandatory-rules.md").read_text()
    assert "Decision Record" in text
    assert "product" in text and "process" in text  # decisions are typed, not just architecture
    assert "increment vs. rewrite" in text.lower() or "increment vs rewrite" in text.lower()
    assert "third patch" in text.lower()


def test_start_here_reads_decision_records_before_planning(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    text = (out / "docs/process/start-here.md").read_text()
    assert "Decision Records" in text
    assert "before planning" in text
    assert "the code that assumes it" in text  # new decision recorded before its code


def test_decision_record_template_has_type_axis_and_intent_atomicity(render, tmp_path):
    # the generalized decision record must carry the Type axis and state that
    # Intent is exactly one value per record (the atomicity forcing function).
    out = render(tmp_path, {"project_name": "demo"})
    text = (out / "docs/process/adr/template.md").read_text()
    assert "## Type" in text
    for t in ["architecture", "product", "process"]:
        assert t in text, t
    assert "one Intent per record" in text or "single value" in text
    assert "split it" in text


def test_decision_records_readme_generalized_and_token_kept(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    text = (out / "docs/process/adr/README.md").read_text()
    assert "Decision Records" in text
    assert "product" in text and "process" in text  # not architecture-only
    assert "ADR-NNNN" in text or "adr-NNNN" in text  # reference token preserved


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


def test_journal_state_plans_shards_journal_and_names_parallel_efforts(render, tmp_path):
    # the journal must be shardable per branch (the one shared-per-day working-memory
    # file otherwise conflicts under parallel efforts), and the serialized-integration
    # trade-off must be named so the rebase-and-re-gate cost is understood, not a surprise.
    out = render(tmp_path, {"project_name": "demo"})
    text = (out / "docs/process/journal-state-plans.md").read_text()
    assert ".process-work/journal/<branch-slug>/YYYY-MM-DD.md" in text  # per-branch shard
    assert "## Parallel efforts" in text
    assert "serialized" in text.lower()  # integration is serialized by design


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
