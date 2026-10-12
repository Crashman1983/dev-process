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
    first = _designed(out, m)
    m.review(first, "reviewer", "pass", "ok", today=TODAY)
    assert m.move(out, first, "piloting", "steward", "go", today=TODAY) is None
    second = _designed(out, m)
    m.review(second, "reviewer", "pass", "ok", today=TODAY)
    assert "one experiment per mechanism" in m.move(out, second, "piloting", "steward", "go", today=TODAY)
    # written by hand anyway: both records are named, and the flag is off
    _hand_start(m, second, "steward")
    per, _ = m.check_all(out, history=False)
    assert all(any("one experiment per mechanism" in p for p in per[x.name]) for x in (first, second)), per
    assert m.active(out, "scoped-handover", issue=7, klass="mechanical", today=TODAY)[0] is None


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


# --- refute of v2.67.0 (independent review): every route to ease frozen terms --

def _hand_start(m, path: Path, who: str, edit=lambda text: text) -> None:
    """A start written by hand, self-consistent: state, log line, FROZEN on the new terms."""
    text = edit(path.read_text().replace("- state: designed", "- state: piloting"))
    terms = m.terms_hash(m.parse(text))
    path.write_text(text + f"- 2026-10-12 {who}: piloting — because by hand\n"
                           f"- FROZEN 2026-10-12 {who}: terms={terms}\n")


def _piloting(out, m):
    _mandate(out)
    path = _designed(out, m)
    m.review(path, "reviewer", "pass", "ok", today=TODAY)
    assert m.move(out, path, "piloting", "steward", "go", today=TODAY) is None
    return path


def _on(out, m):
    return m.active(out, "scoped-handover", issue=7, klass="mechanical", today=TODAY)[0]


def _probs(out, m, path, history=False) -> str:
    return " ".join(m.check_all(out, history=history)[0].get(path.name, []))


def test_a_second_heading_cannot_carry_the_real_terms(opt):
    out, m = opt
    path = _piloting(out, m)
    text = path.read_text()
    path.write_text(text.replace("## Rollback", "## Criteria\nMedian down by 1 %, n >= 1.\n\n## Rollback"))
    assert "## Criteria appears twice" in _probs(out, m, path)
    assert _on(out, m) is None
    path.write_text(text.replace("- issues:", "- until: 2099-01-01\n- issues:"))
    assert "header field until: appears twice" in _probs(out, m, path)


def test_hidden_text_counts_for_nothing(opt):
    out, m = opt
    _mandate(out)
    path = _designed(out, m)
    base = path.read_text()
    terms = m.terms_hash(m.parse(base))
    line = f"- REVIEWED 2026-10-12 alice: pass terms={terms} — ok\n"
    for hidden in (f"<!--\n{line}-->\n", f"```\n{line}```\n", f"- note:\n    ```\n    {line}    ```\n"):
        path.write_text(base + hidden)
        why = m.move(out, path, "piloting", "steward", "go", today=TODAY)
        assert why and "the Log holds plain" in why, why  # a Log with hidden parts is broken, not read around
    # a heading is a heading wherever it stands (fail closed), and the Log takes no comment
    path.write_text(base.replace("## Generality", "```\n## Criteria\nnothing\n```\n## Generality"))
    assert "## Criteria appears twice" in _probs(out, m, path)
    path.write_text(base + "<!-- note -->\n")
    assert "the Log holds plain" in _probs(out, m, path)


def test_the_implementer_is_named_and_compared_without_case(opt):
    out, m = opt
    _mandate(out)
    path = _designed(out, m)
    assert "someone else's" in m.review(path, "  Maintainer ", "pass", "ok", today=TODAY)
    path.write_text(path.read_text().replace("- implementer: maintainer",
                                             "- implementer: <who builds the change>"))
    assert "name the implementer first" in m.review(path, "reviewer", "pass", "ok", today=TODAY)
    assert "implementer: missing" in _probs(out, m, path)


def test_a_hand_written_start_must_keep_every_rule(opt):
    out, m = opt
    _mandate(out)
    path = _designed(out, m)
    m.review(path, "reviewer", "pass", "ok", today=TODAY)
    _hand_start(m, path, "MAINTAINER", lambda t: t.replace("until: 2026-11-01", "until: 2099-12-31"))
    probs = _probs(out, m, path)
    assert "implements this change and cannot start" in probs
    assert "beyond the mandate's max_pilot_days" in probs
    assert "no REVIEWED pass" in probs  # the review saw other terms
    assert _on(out, m) is None


def test_a_mandate_shrunk_after_the_start_binds_the_running_trial(opt):
    out, m = opt
    path = _piloting(out, m)
    assert _on(out, m) == path.name
    _mandate(out, {"max_pilot_days": 5, "steward_may": ["start"]})
    assert "max_pilot_days" in _probs(out, m, path)
    assert _on(out, m) is None


def test_a_block_is_not_outvoted_by_a_pass(opt):
    out, m = opt
    _mandate(out)
    path = _designed(out, m)
    m.review(path, "alice", "pass", "ok", today=TODAY)
    m.review(path, "bob", "block", "the minimum n is too small", today=TODAY)
    assert "REVIEWED block stands" in m.move(out, path, "piloting", "steward", "go", today=TODAY)


def test_history_survives_a_rename(opt):
    out, m = opt
    _repo(out)
    path = _piloting(out, m)
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "start trial")
    renamed = path.with_name("OPT-0001-renamed.md")
    _git(out, "mv", str(path), str(renamed))
    _git(out, "commit", "-q", "-m", "rename")
    text = renamed.read_text()
    old = m.parse(text)["frozen"][0]["terms"]
    eased = text.replace("down by 20 %", "down by 1 %")
    renamed.write_text(eased.replace(old, m.terms_hash(m.parse(eased))))
    _git(out, "commit", "-qam", "ease")
    assert "frozen in commit" in _probs(out, m, renamed, history=True)
    assert _on(out, m) is None


def test_a_freeze_prepared_in_an_earlier_commit_anchors_nothing(opt):
    out, m = opt
    _repo(out)
    _mandate(out)
    path = _designed(out, m)
    weak = path.read_text().replace("down by 20 %", "down by 1 %")
    weak_terms = m.terms_hash(m.parse(weak))
    path.write_text(weak.replace("## Hypothesis", f"<!--\n- FROZEN 2026-10-01 steward: terms={weak_terms}\n-->\n\n## Hypothesis"))
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "proposal")
    path.write_text(path.read_text().replace("down by 1 %", "down by 20 %"))
    m.review(path, "reviewer", "pass", "ok", today=TODAY)
    assert m.move(out, path, "piloting", "steward", "go", today=TODAY) is None
    _git(out, "commit", "-qam", "start")
    strong = m.parse(path.read_text())["frozen"][0]["terms"]
    path.write_text(path.read_text().replace("down by 20 %", "down by 1 %").replace(strong, weak_terms))
    assert "frozen in commit" in _probs(out, m, path, history=True)


def test_stopping_is_never_blocked(opt):
    out, m = opt
    path = _piloting(out, m)
    path.write_text(path.read_text().replace("down by 20 %", "down by 1 %"))  # tampered
    (out / "docs/process/optimization.local.json").write_text("{broken")
    assert m.move(out, path, "stopped", "anyone", "a stop condition fired", today=TODAY) is None
    assert m.move(out, path, "rolled-back", "steward", "undo", today=TODAY) is None  # default right


def test_a_hand_written_adoption_without_the_right_is_named(opt):
    out, m = opt
    path = _piloting(out, m)
    m.move(out, path, "evaluating", "steward", "done", today=TODAY)
    path.write_text(path.read_text().replace("- state: evaluating", "- state: adopted")
                    + "- 2026-10-20 steward: adopted — because by hand\n")
    assert "adopted by steward: adopted needs the owner" in _probs(out, m, path)
    path.write_text(path.read_text().replace("steward: adopted", "Maintainer: adopted"))
    assert "implements this change and cannot adopt" in _probs(out, m, path)


# --- refute round 2: the freeze is byte-exact, history is repo-wide -----------

HEADING_VARIANTS = ["## Criteria #", "Criteria\n--------", "   ## Criteria", "<h2>Criteria</h2>",
                    "Note `<!--`\n## Criteria\n`-->`", "```x```\n## Criteria"]


def test_any_change_above_result_breaks_the_freeze(opt):
    out, m = opt
    path = _piloting(out, m)
    text = path.read_text()
    for variant in HEADING_VARIANTS:
        path.write_text(text.replace("## Rollback", f"{variant}\nMedian down by 1 %, n >= 1.\n\n## Rollback"))
        assert "terms changed after they were frozen" in _probs(out, m, path), variant
        assert _on(out, m) is None, variant


def test_below_result_only_result_decision_and_log_are_headings(opt):
    out, m = opt
    path = _piloting(out, m)
    text = path.read_text()
    for variant in HEADING_VARIANTS[:4]:
        path.write_text(text.replace("## Decision", f"{variant}\nMedian down by 1 %.\n\n## Decision"))
        assert f"below {m.RESULT_LINE} only Result, Decision and Log are headings" in _probs(out, m, path), variant
        assert _on(out, m) is None, variant


def test_a_committed_block_cannot_be_erased_before_the_start(opt):
    out, m = opt
    _repo(out)
    _mandate(out)
    path = _designed(out, m)
    m.review(path, "carol", "block", "n too small", today=TODAY)
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "blocked")
    path.write_text("".join(line for line in path.read_text().splitlines(keepends=True)
                            if "REVIEWED" not in line))
    m.review(path, "alice", "pass", "fine", today=TODAY)
    why = m.move(out, path, "piloting", "steward", "go", today=TODAY)
    assert why and "REVIEWED block by carol" in why and "is gone" in why, why


def test_a_start_is_not_dated_ahead(opt):
    out, m = opt
    _mandate(out)
    path = _designed(out, m)
    m.review(path, "reviewer", "pass", "ok", today=TODAY)
    future = dt.date(2027, 6, 1)
    path.write_text(path.read_text().replace("until: 2026-11-01", "until: 2027-06-30"))
    m.review(path, "reviewer", "pass", "ok", today=TODAY)
    assert m.move(out, path, "piloting", "steward", "go", today=future) is None  # written as if on that day
    assert "lies in the future" in " ".join(m.check_all(out, history=False, today=TODAY)[0][path.name])
    assert _on(out, m) is None


def test_a_record_that_ran_cannot_vanish_or_be_renumbered(opt):
    out, m = opt
    _repo(out)
    path = _piloting(out, m)
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "start")
    # renumbered with a heavy edit in one commit: --follow would lose it, the number index does not
    eased = path.read_text().replace("down by 20 %", "down by 1 %") + ("padding\n" * 200).replace(
        "padding", "- 2026-10-12 steward: piloting — because pad")[:0]
    moved = path.with_name("OPT-0002-other.md")
    path.unlink()
    moved.write_text(eased.replace("# OPT-0001", "# OPT-0002"))
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "renumber")
    per, general = m.check_all(out)
    assert any("OPT-0001 ran" in g and "is gone" in g for g in general), general
    assert _on(out, m) is None
    assert m.new(out, "Next", "x", responsible="steward", implementer="", issues="", who="s",
                 because="b").name.startswith("OPT-0003")  # a used number is not reused


def test_a_record_added_in_a_merge_is_in_the_history(opt):
    out, m = opt
    _repo(out)
    _git(out, "checkout", "-q", "-b", "side")
    path = _piloting(out, m)
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "start on side")
    _git(out, "checkout", "-q", "main")
    _git(out, "commit", "-q", "--allow-empty", "-m", "main moves")
    _git(out, "merge", "-q", "--no-ff", "-m", "merge side", "side")
    eased = path.read_text()
    old = m.parse(eased)["frozen"][0]["terms"]
    eased = eased.replace("down by 20 %", "down by 1 %")
    path.write_text(eased.replace(old, m.terms_hash(eased)))
    _git(out, "commit", "-qam", "ease")
    assert "frozen in commit" in _probs(out, m, path, history=True)


def test_a_narrowed_mandate_binds_running_trials_not_finished_ones(opt):
    out, m = opt
    _mandate(out, {"max_pilot_days": 30, "steward_may": ["start", "adopt"]})
    path = _designed(out, m)
    m.review(path, "reviewer", "pass", "ok", today=TODAY)
    assert m.move(out, path, "piloting", "steward", "go", today=TODAY) is None
    assert m.move(out, path, "evaluating", "steward", "done", today=TODAY) is None
    assert m.move(out, path, "adopted", "steward", "criteria met", today=TODAY) is None
    _mandate(out, {"max_pilot_days": 5, "steward_may": []})
    assert _probs(out, m, path) == ""  # judged by the mandate it ran under
    # an evaluating trial stays decidable by the owner after the mandate shrank
    other = _designed(out, m)
    other.write_text(other.read_text().replace("mechanism: hand-over context", "mechanism: other")
                     .replace("flag: scoped-handover", "flag: other"))
    _mandate(out, {"max_pilot_days": 30, "steward_may": ["start"]})
    m.review(other, "reviewer", "pass", "ok", today=TODAY)
    assert m.move(out, other, "piloting", "steward", "go", today=TODAY) is None
    assert m.move(out, other, "evaluating", "steward", "done", today=TODAY) is None
    _mandate(out, {"max_pilot_days": 5, "steward_may": []})
    assert m.move(out, other, "adopted", "owner", "criteria met", today=TODAY) is None


def test_a_review_after_the_freeze_counts_for_nothing(opt):
    out, m = opt
    path = _piloting(out, m)
    text = path.read_text()
    rec = m.parse(text)
    terms = rec["frozen"][0]["terms"]
    path.write_text(text + f"- REVIEWED 2026-10-12 dave: block terms={terms} — late\n")
    assert _probs(out, m, path) == ""  # a late block does not count …
    no_review = "".join(line for line in text.splitlines(keepends=True) if "REVIEWED" not in line)
    path.write_text(no_review + f"- REVIEWED 2026-10-12 alice: pass terms={terms} — late\n")
    assert "before the freeze" in _probs(out, m, path)  # … and neither does a late pass
    assert m.active(out, "", issue=7)[0] is None
