from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "docs/pilots/2026-07-19-governance-economics.md"


def test_governance_pilot_records_case_one_without_activation():
    text = PILOT.read_text(encoding="utf-8")

    assert "Status: 1/3 observed" in text
    for field in (
        "intent_mode",
        "semantic_impact",
        "mutation_class",
        "terminal_state",
        "claim_delta",
        "process_cost",
        "repeated_decision_question",
        "tool_stalls",
        "adopt | revise | reject",
    ):
        assert field in text
    assert "no template or gate effect" in text
