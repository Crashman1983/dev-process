"""optimize.py — the improvement record: states, frozen terms, decision rights,
bounded use (docs/process/optimization.md)."""
import datetime as dt
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

TODAY = dt.date(2026, 10, 12)

MANDATE = {"max_pilot_days": 30, "steward_may": ["start", "roll-back", "reject"]}

FILL = {
    "Observation": "Issues #3 and #5 re-read the whole plan on every hand-over (measured: 40k tokens each).",
    "Hypothesis": "Hand-overs carry the full plan; a scoped context cuts input tokens without more rounds.",
    "Placement": "core — the hand-over contract is a process mechanism every project shares.",
    "Trial": "Baseline: the last 20 mechanical tasks; process v2.67.0; in: mechanical tasks of odd issues.",
    "Limits": "Floors: no extra review round on median; stop when two trial issues need a rescue.",
    "Criteria": "Median input tokens per hand-over down by 20 %, n >= 8; below n the result is inconclusive.",
    "Generality": "Minimal render, claude/copilot/agents_md adapters; tests in the process repository.",
    "Rollback": "Stop: state stopped turns the flag off. No data changes; prompts revert with the flag.",
    "Result": "Median input tokens -27 % (n=9, measured); rounds unchanged; upkeep: one doc section.",
    "Decision": "Adopt for mechanical tasks; generic adoption is the maintainer's call upstream.",
}
HEADER = {
    "placement": "core",
    "flag": "scoped-handover",
    "select": "classes=mechanical parity=odd",
    "until": "2026-11-01",
    "budget-tokens": "2000000",
    "budget-hours": "12",
}


def _load(out: Path):
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(out / "scripts/process"))
    spec = importlib.util.spec_from_file_location("optimize_under_test", out / "scripts/process/optimize.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True).stdout


def _repo(out: Path) -> None:
    _git(out, "init", "-q", "-b", "main")
    _git(out, "config", "user.email", "t@t")
    _git(out, "config", "user.name", "t")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "base")


def _fill(path: Path, sections=FILL, header=HEADER) -> None:
    text = path.read_text(encoding="utf-8")
    for key, value in header.items():
        text = re.sub(rf"(?m)^- {re.escape(key)}: .*$", f"- {key}: {value}", text, count=1)
    for name, body in sections.items():
        text = re.sub(rf"(?ms)^## {name}\n<!--.*?-->", f"## {name}\n{body}", text, count=1)
    path.write_text(text, encoding="utf-8")


def _mandate(out: Path, data=MANDATE) -> None:
    (out / "docs/process/optimization.local.json").write_text(json.dumps(data), encoding="utf-8")


@pytest.fixture
def opt(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    return out, _load(out)


def _designed(out, m):
    path = m.new(out, "Scoped hand-over context", "hand-over context", responsible="steward",
                 implementer="maintainer", issues="#3, #5", who="steward", because="token outliers")
    _fill(path)
    assert m.move(out, path, "designed", "steward", "cause found", today=TODAY) is None
    return path


def test_core_ships_contract_tool_and_example(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    assert (out / "scripts/process/optimize.py").is_file()
    doc = (out / "docs/process/optimization.md").read_text()
    assert "does not ease its own criteria" in doc
    example = json.loads((out / "docs/process/optimization.example.json").read_text())
    assert example["max_pilot_days"] == 30
    assert not (out / "docs/process/optimization.local.json").exists()  # no mandate by default


def test_no_records_is_clean_and_nothing_is_active(opt):
    out, m = opt
    assert m.check_all(out) == ({}, [])
    assert m.active(out, "anything", issue=1)[0] is None
    r = subprocess.run([sys.executable, str(out / "scripts/process/optimize.py"), "--root", str(out), "check"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_a_record_runs_the_whole_loop(opt):
    out, m = opt
    path = _designed(out, m)
    # the implementer neither reviews nor starts its own change
    assert "someone else's" in m.review(path, "maintainer", "pass", "fine", today=TODAY)
    _mandate(out)
    assert "REVIEWED" in m.move(out, path, "piloting", "steward", "go", today=TODAY)
    assert m.review(path, "reviewer", "pass", "criteria measurable, rollback safe", today=TODAY) is None
    assert "implements this change" in m.move(out, path, "piloting", "maintainer", "go", today=TODAY)
    assert m.move(out, path, "piloting", "steward", "within mandate", today=TODAY) is None
    text = path.read_text()
    assert "- state: piloting" in text and "- FROZEN 2026-10-12 steward: terms=" in text
    # bounded use: odd mechanical work only, and only while the record runs
    on = m.active(out, "scoped-handover", issue=7, klass="mechanical", today=TODAY)
    assert on[0] == path.name, on
    assert m.active(out, "scoped-handover", issue=8, klass="mechanical", today=TODAY)[0] is None
    assert m.active(out, "scoped-handover", issue=7, klass="standard", today=TODAY)[0] is None
    assert m.active(out, "scoped-handover", issue=7, today=TODAY)[0] is None  # unanswerable → off
    assert m.check_all(out, history=False) == ({}, [])
    # stopping is anybody's and turns the flag off at once
    assert m.move(out, path, "stopped", "guard", "two rescues", today=TODAY) is None
    assert m.active(out, "scoped-handover", issue=7, klass="mechanical", today=TODAY)[0] is None
    assert m.move(out, path, "evaluating", "steward", "collect the result", today=TODAY) is None
    assert "needs the owner" in m.move(out, path, "adopted", "steward", "good", today=TODAY)
    assert "implements this change" in m.move(out, path, "adopted", "maintainer", "good", today=TODAY)
    assert m.move(out, path, "adopted", "owner", "criteria met", today=TODAY) is None
    assert m.check_all(out, history=False) == ({}, [])
    assert "is not a transition" in m.move(out, path, "piloting", "owner", "again", today=TODAY)


def test_designed_needs_its_sections_and_a_placement(opt):
    out, m = opt
    path = m.new(out, "Empty", "scheduling", responsible="steward", implementer="", issues="",
                 who="steward", because="seen")
    why = m.move(out, path, "designed", "steward", "go", today=TODAY)
    assert "## Observation" in why and "placement must be one of" in why
    assert "- state: proposed" in path.read_text()  # nothing written on a refusal


def test_a_pilot_needs_a_mandate_and_respects_its_limits(opt):
    out, m = opt
    path = _designed(out, m)
    assert m.review(path, "reviewer", "pass", "ok", today=TODAY) is None
    assert "no mandate" in m.move(out, path, "piloting", "steward", "go", today=TODAY)
    _mandate(out, {"max_pilot_days": 10, "steward_may": ["start"]})
    assert "max_pilot_days" in m.move(out, path, "piloting", "steward", "go", today=TODAY)
    _mandate(out, {"max_pilot_days": 30, "steward_may": []})
    assert "needs the owner" in m.move(out, path, "piloting", "steward", "go", today=TODAY)
    _mandate(out, {"max_pilot_days": 30, "steward_may": ["stop"]})
    assert "unknown right" in m.move(out, path, "piloting", "owner", "go", today=TODAY)


def test_a_pilot_needs_budgets_selection_and_until(opt):
    out, m = opt
    path = m.new(out, "No limits", "context", responsible="steward", implementer="maintainer",
                 issues="#1", who="steward", because="seen")
    _fill(path, header={"placement": "core", "flag": "x"})
    _mandate(out)
    assert m.move(out, path, "designed", "steward", "go", today=TODAY) is None
    assert m.review(path, "reviewer", "pass", "ok", today=TODAY) is None
    why = m.move(out, path, "piloting", "steward", "go", today=TODAY)
    for need in ("select:", "until:", "budget-tokens:", "budget-hours:"):
        assert need in why, why


def test_a_review_binds_to_the_terms_it_saw(opt):
    out, m = opt
    path = _designed(out, m)
    _mandate(out)
    assert m.review(path, "reviewer", "pass", "ok", today=TODAY) is None
    # the criteria were eased after the review: that review does not cover them
    path.write_text(path.read_text().replace("down by 20 %", "down by 1 %"))
    assert "REVIEWED" in m.move(out, path, "piloting", "steward", "go", today=TODAY)


def test_an_experiment_cannot_ease_its_own_criteria(opt):
    out, m = opt
    path = _designed(out, m)
    _mandate(out)
    m.review(path, "reviewer", "pass", "ok", today=TODAY)
    assert m.move(out, path, "piloting", "steward", "go", today=TODAY) is None
    path.write_text(path.read_text().replace("down by 20 %", "down by 1 %"))
    per, _ = m.check_all(out, history=False)
    assert "terms changed after they were frozen" in " ".join(per[path.name])
    assert m.active(out, "scoped-handover", issue=7, klass="mechanical", today=TODAY)[0] is None
    # a widened selection or a later until is an eased criterion too
    path.write_text(path.read_text().replace("down by 1 %", "down by 20 %")
                    .replace("until: 2026-11-01", "until: 2026-12-01"))
    assert "terms changed" in " ".join(m.check_all(out, history=False)[0][path.name])


def test_a_rewritten_frozen_hash_is_caught_by_history(opt):
    out, m = opt
    _repo(out)
    path = _designed(out, m)
    _mandate(out)
    m.review(path, "reviewer", "pass", "ok", today=TODAY)
    assert m.move(out, path, "piloting", "steward", "go", today=TODAY) is None
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "start trial")
    rec = m.parse(path.read_text())
    old = rec["frozen"][0]["terms"]
    eased = path.read_text().replace("down by 20 %", "down by 1 %")
    eased_hash = m.terms_hash(m.parse(eased))
    # the hash, the review and the criteria rewritten together: self-consistent text
    path.write_text(eased.replace(f"terms={old}", f"terms={eased_hash}"))
    assert m.check_all(out, history=False) == ({}, [])
    per, _ = m.check_all(out)
    assert "frozen in commit" in " ".join(per[path.name]), per
    assert m.active(out, "scoped-handover", issue=7, klass="mechanical", today=TODAY)[0] is None


def test_an_expired_trial_is_off_and_status_says_evaluate(opt):
    out, m = opt
    path = _designed(out, m)
    _mandate(out)
    m.review(path, "reviewer", "pass", "ok", today=TODAY)
    m.move(out, path, "piloting", "steward", "go", today=TODAY)
    late = dt.date(2026, 11, 2)
    assert "past until" in m.active(out, "scoped-handover", issue=7, klass="mechanical", today=late)[1]
    lines = m.status_lines(out, today=late)
    assert any("past until" in line and "evaluating" in line for line in lines), lines
    assert any("spent-tokens not recorded" in line for line in m.status_lines(out, today=TODAY))
    path.write_text(path.read_text().replace("- issues:", "- spent-tokens: 3000000\n- spent-hours: 2\n- issues:"))
    assert any("over budget-tokens" in line for line in m.status_lines(out, today=TODAY))
    assert m.check_all(out, history=False) == ({}, [])  # spent-* are not frozen terms


def test_two_trials_on_one_mechanism_confound(opt):
    out, m = opt
    _mandate(out)
    for _ in range(2):
        path = _designed(out, m)
        m.review(path, "reviewer", "pass", "ok", today=TODAY)
        assert m.move(out, path, "piloting", "steward", "go", today=TODAY) is None
    per, _ = m.check_all(out, history=False)
    assert any("one experiment per mechanism" in p for probs in per.values() for p in probs), per
    assert "ambiguous" in m.active(out, "scoped-handover", issue=7, klass="mechanical", today=TODAY)[1]


def test_a_rejected_trial_keeps_its_frozen_terms(opt):
    out, m = opt
    path = _designed(out, m)
    _mandate(out)
    m.review(path, "reviewer", "pass", "ok", today=TODAY)
    m.move(out, path, "piloting", "steward", "go", today=TODAY)
    m.move(out, path, "evaluating", "steward", "done", today=TODAY)
    assert m.move(out, path, "rejected", "steward", "no effect", today=TODAY) is None
    path.write_text(path.read_text().replace("down by 20 %", "down by 1 %"))
    assert "terms changed" in " ".join(m.check_all(out, history=False)[0][path.name])


def test_declining_a_proposal_is_anyones(opt):
    out, m = opt
    path = m.new(out, "Idea", "scheduling", responsible="steward", implementer="", issues="",
                 who="worker", because="seen")
    assert m.move(out, path, "rejected", "maintainer", "belongs in the project, not the core",
                  today=TODAY) is None
    assert m.check_all(out, history=False)[0] == {}


def test_hand_edited_state_must_match_the_log(opt):
    out, m = opt
    path = _designed(out, m)
    path.write_text(path.read_text().replace("- state: designed", "- state: adopted"))
    probs = " ".join(m.check_all(out, history=False)[0][path.name])
    assert "log's last transition is designed" in probs and "FROZEN" in probs


@pytest.mark.parametrize("value,expect", [
    ("all", {}),
    ("issues=#12,15 tiers=1", {"issues": {"12", "15"}, "tiers": {"1"}}),
    ("parity=even", {"parity": {"even"}}),
    ("", None), ("parity=sometimes", None), ("tiers=one", None), ("issues=1 issues=2", None),
    ("colour=red", None), ("issues=", None),
])
def test_select_grammar(opt, value, expect):
    _out, m = opt
    assert m.parse_select(value) == expect


def test_cli_moves_and_refuses(opt):
    out, m = opt
    script = [sys.executable, str(out / "scripts/process/optimize.py"), "--root", str(out)]
    r = subprocess.run([*script, "new", "--title", "Faster train", "--mechanism", "train scheduling"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    r = subprocess.run([*script, "move", "OPT-0001", "designed", "--who", "steward", "--because", "x"],
                       capture_output=True, text=True)
    assert r.returncode == 1 and "refused" in r.stderr
    r = subprocess.run([*script, "list"], capture_output=True, text=True)
    assert "OPT-0001  proposed" in r.stdout
    r = subprocess.run([*script, "active", "nothing", "--issue", "3"], capture_output=True, text=True)
    assert r.returncode == 1 and "off" in r.stdout
