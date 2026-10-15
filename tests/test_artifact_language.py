"""#244 (E3): the language of written artifacts is a copier answer. `english` renders
as before; `conversation` keeps code, commits, issues and contract docs English and
the operator's prose in the conversation language — the same text in the kernel and
every anchor, so the kernel gate stays green."""
from __future__ import annotations

import subprocess
import sys

import pytest

ANCHORS = ["docs/process/kernel.md", "CLAUDE.md", "AGENTS.md", ".github/copilot-instructions.md"]
ALL = {"claude": True, "copilot": True, "agents_md": True}
ENGLISH = ("**Language:** converse with the user in the user's language; write all artifacts\n"
           "(docs, code, commits, ADRs, journal) in English.")
# downstream Kenni's ADR-0063 rule, byte for byte: its update then meets no kernel conflict
CONVERSATION = ("**Language:** converse with the user in the user's language. Write in English\n"
                "what an outside reader or a second toolchain has to read: code identifiers,\n"
                "commits, issues, and the shared contract docs. Prose the operator writes for\n"
                "themselves — ADRs, journal, plans, code comments, test titles — follows the\n"
                "conversation language.")


@pytest.mark.parametrize("answer,rule,other", [(None, ENGLISH, CONVERSATION),
                                               ("english", ENGLISH, CONVERSATION),
                                               ("conversation", CONVERSATION, ENGLISH)])
def test_the_kernel_and_every_anchor_carry_the_chosen_language_rule(render, tmp_path, answer, rule, other):
    data = {"project_name": "d", "harnesses": ALL}
    if answer:
        data["artifact_language"] = answer
    out = render(tmp_path, data)
    for rel in ANCHORS:
        text = (out / rel).read_text(encoding="utf-8")
        assert rule in text and other not in text, rel
    r = subprocess.run([sys.executable, str(out / "scripts/process/check_kernel.py"), str(out)],
                       capture_output=True, text=True)
    assert r.returncode == 0 and "kernel: OK" in r.stdout, r.stdout
    start = (out / "docs/process/start-here.md").read_text(encoding="utf-8")
    copilot = (out / ".github/instructions/process.instructions.md").read_text(encoding="utf-8")
    journal = (out / ".process-work/README.md").read_text(encoding="utf-8")
    if rule is ENGLISH:
        assert "write artifacts in English" in start and "write all artifacts in English" in copilot
        assert "dated, and in English" in journal
    else:
        assert "operator prose in the conversation language" in start
        assert "in the conversation language" in copilot and "in the conversation language" in journal
        assert "write all artifacts" not in start + copilot


def test_another_language_answer_is_refused(render, tmp_path):
    with pytest.raises(Exception):
        render(tmp_path, {"project_name": "d", "artifact_language": "german"})
