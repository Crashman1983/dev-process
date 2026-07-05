# Artifacts are English; dialogue follows the user (design: sp8-english-canon).
# One language to maintain, half the doc tokens per prime, and the canon LLMs
# handle best — while a kernel rule keeps the user-facing dialogue in the
# user's language.

LANGUAGE_RULE = "converse with the user in the user's language"

ALL_ON = {
    "project_name": "demo",
    "harnesses": {"copilot": True, "agents_md": True},
    "modules": {
        "doc_drift_gate": True, "arch_onboarding": True, "feature_registry": True,
        "github_issues": True, "contracts_drift": True, "git_hooks": True,
        "contract_first": True, "parity": True, "security_floor": True,
    },
    "ci": {"github": True, "gitlab": True},
}


def test_rendered_repo_carries_no_german_blocks(render, tmp_path):
    # full render, every harness and module on: no bilingual block marker may
    # survive anywhere — a single leftover doubles that doc's tokens forever.
    out = render(tmp_path, ALL_ON)
    offenders = [
        p for p in out.rglob("*")
        if p.is_file() and p.suffix in {".md", ".yml", ".json", ".py", ".sh"}
        and "**Deutsch:**" in p.read_text(errors="ignore")
    ]
    assert not offenders, offenders


def test_kernel_carries_dialogue_language_rule(render, tmp_path):
    # the language split (English artifacts, user-language dialogue) is an
    # always-on kernel property, present in every adapter.
    out = render(tmp_path, ALL_ON)
    for rel in ["CLAUDE.md", "AGENTS.md", ".github/copilot-instructions.md"]:
        text = (out / rel).read_text()
        kernel = text.split("<!-- KERNEL:START -->")[1].split("<!-- KERNEL:END -->")[0]
        assert LANGUAGE_RULE in kernel, rel
        assert "in English" in kernel, rel


def test_start_here_states_when_not_worth_it(render, tmp_path):
    # honest economics: the process names the case where it is a net loss
    # instead of implying universal value.
    out = render(tmp_path, {"project_name": "d"})
    text = (out / "docs/process/start-here.md").read_text()
    assert "not worth it" in text
    assert "throwaway prototypes" in text


def test_journal_duty_scales_with_tier(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    text = (out / "docs/process/journal-state-plans.md").read_text()
    assert "Tier 1 upward" in text
    assert "Tier 0 changes need none" in text
