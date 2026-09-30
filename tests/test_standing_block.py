"""check_review's standing-block arm: a `block` stops the push to main,
whatever the tier.

Observed downstream: round 2 stood at `verdict=block`, a Tier 1 plan
declared the work, and the push to main went through — the gate collected
passes only, and every tier-keyed arm said "skip" below Tier 2. Pinned: the
latest verdict per work (highest round, an equal round goes to the block)
and the push → work join through three anchors: an issue claimed in the
commit range, a REVIEW record the range adds (or an `issue-<W>/` shard
folder), a `head=` in the range. The negative twins stand beside them:
foreign work does not block, a later pass clears the block, a feature
branch push gets a note only.
"""
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "template/scripts/process/check_review.py"


def _load():
    # loaded straight from the template tree: no __pycache__ may land there
    before = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec = importlib.util.spec_from_file_location("check_review_standing", _SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = before
    return module


mod = _load()

_INDEP = "independence=bundle,non-implementing,single-family"
SHARD = ".process-work/journal/2026-09-28.md"


def _line(work: str, verdict: str, round_: int, tier: int = 1) -> str:
    return (f"REVIEW work={work} tier={tier} reviewer=fresh-agent model=same "
            f"{_INDEP} verdict={verdict} round={round_}")


@pytest.fixture(autouse=True)
def merge_push(monkeypatch):
    """By default the push lands on main — only there is the verdict hard."""
    for var in (mod.PRE_COMMIT_TARGET_ENV, "PRE_COMMIT_TO_REF", "PRE_COMMIT_FROM_REF"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv(mod.PUSH_TARGETS_ENV, "refs/heads/main")


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True,
                          text=True).stdout.strip()


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "gate@example.invalid")
    _git(root, "config", "user.name", "Gate")
    (root / "README.md").write_text("base\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    return root


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _commit(root: Path, message: str) -> str:
    """A commit above the merge base — the range a push carries."""
    if _git(root, "rev-parse", "--abbrev-ref", "HEAD") == "main":
        _git(root, "checkout", "-q", "-b", "feature")
    code = root / "code.py"
    code.write_text((code.read_text(encoding="utf-8") if code.exists() else "") + "x = 1\n",
                    encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", message)
    return _git(root, "rev-parse", "HEAD")


def _on_main(root: Path, message: str) -> str:
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", message)
    return _git(root, "rev-parse", "HEAD")


def _blocked(findings: list[str], work: str) -> bool:
    return any("verdict=block" in f and f"work {work}" in f for f in findings)


def _cannot_tell(findings: list[str]) -> bool:
    return any("cannot determine the pushed range" in f for f in findings)


# --- the incident and its negative twins (through check) ------------------------------

def test_a_tier1_plan_with_a_block_stops_the_push_to_main(tmp_path):
    root = _repo(tmp_path)
    _write(root, ".process-work/plans/2026-09-28-2168-thing.md", "# Plan\n\nissue: #2168\ntier: 1\n")
    _write(root, SHARD, _line("2168", "block", 2) + "\n")
    _commit(root, "fix: something (#2168)")
    hard, _soft = mod.check(root)
    assert _blocked(hard, "2168") and any("round 2" in h for h in hard), hard


def test_a_block_without_any_plan_stops_it(tmp_path):
    root = _repo(tmp_path)
    _write(root, SHARD, _line("2168", "block", 1, tier=0) + "\n")
    _commit(root, "fix: something (#2168)")
    assert _blocked(mod.check(root)[0], "2168")


@pytest.mark.parametrize("lines,stands", [
    ([("block", 1), ("pass", 3)], False),   # a later pass clears it
    ([("pass", 2), ("block", 2)], True),    # parallel reviews of one round: fail closed
    ([("pass", 1), ("block", 2)], True),    # the order is the round, not the line
], ids=["later-pass", "equal-round", "later-block"])
def test_the_latest_round_decides(tmp_path, lines, stands):
    root = _repo(tmp_path)
    _write(root, SHARD, "".join(_line("2168", v, r) + "\n" for v, r in lines))
    _commit(root, "fix: something (#2168)")
    assert _blocked(mod.check(root)[0], "2168") is stands


def test_foreign_work_does_not_block(tmp_path):
    root = _repo(tmp_path)
    _write(root, ".process-work/journal/2026-09-20.md", _line("999", "block", 1) + "\n")
    _on_main(root, "docs: attest 999 round 1")
    _commit(root, "fix: something (#2168)")
    assert not _blocked(mod.check(root)[0], "999")


def test_a_touched_daily_shard_does_not_pull_foreign_blocks_in(tmp_path):
    root = _repo(tmp_path)
    _write(root, SHARD, _line("999", "block", 1) + "\n")
    _on_main(root, "docs: attest 999 round 1")
    _write(root, SHARD, _line("999", "block", 1) + "\n" + _line("2168", "pass", 1) + "\n")
    _commit(root, "fix: something (#2168)")
    assert not _blocked(mod.check(root)[0], "999")


def test_a_feature_branch_push_reports_the_block_as_a_note(tmp_path, monkeypatch):
    monkeypatch.setenv(mod.PUSH_TARGETS_ENV, "refs/heads/7-work")
    root = _repo(tmp_path)
    _write(root, SHARD, _line("2168", "block", 2) + "\n")
    _commit(root, "fix: something (#2168)")
    hard, soft = mod.check(root)
    assert not _blocked(hard, "2168"), hard
    assert any("verdict=block" in s and "note only" in s for s in soft), soft


# --- the anchors ----------------------------------------------------------------------

def test_an_issue_shard_folder_in_the_range_anchors_without_an_issue_ref(tmp_path):
    # the rebase case: no subject names the issue, but the `issue-<W>/` shard travels
    root = _repo(tmp_path)
    _write(root, ".process-work/journal/issue-2168/2026-09-28.md", _line("2168", "block", 2) + "\n")
    _commit(root, "docs: attest round 2")
    assert _blocked(mod.check(root)[0], "2168")


def test_a_review_line_added_in_the_range_anchors(tmp_path):
    root = _repo(tmp_path)
    _write(root, SHARD, _line("2168", "block", 2) + "\n")
    _commit(root, "docs: attest round 2")
    assert _blocked(mod.check(root)[0], "2168")


def test_a_head_in_the_range_anchors(tmp_path):
    root = _repo(tmp_path)
    base = _git(root, "rev-parse", "HEAD")
    head = _commit(root, "feat: work without issue ref")
    record = {"work": "2168", "verdict": "block", "round": "2", "head": head}
    assert mod.pushed_work_ids(root, [record], set(), tip="HEAD", base=base) == {"2168"}


def test_latest_verdicts_highest_round_and_block_on_a_tie():
    records = [
        {"work": "1", "round": "1", "verdict": "block"},
        {"work": "1", "round": "3", "verdict": "pass"},
        {"work": "2", "round": "2", "verdict": "pass"},
        {"work": "2", "round": "2", "verdict": "block"},
        {"work": "3", "round": "10", "verdict": "pass"},
        {"work": "3", "round": "9", "verdict": "block"},
    ]
    latest = mod.latest_verdicts(records)
    assert {w: r["verdict"] for w, r in latest.items()} == {"1": "pass", "2": "block", "3": "pass"}


# --- what is read is what the push carries: the committed state -----------------------

def test_an_uncommitted_pass_does_not_clear_the_block(tmp_path):
    root = _repo(tmp_path)
    _write(root, SHARD, _line("2168", "block", 1) + "\n")
    _commit(root, "fix: something (#2168)")
    _write(root, SHARD, _line("2168", "block", 1) + "\n" + _line("2168", "pass", 2) + "\n")
    assert _blocked(mod.check(root)[0], "2168")


def test_an_uncommitted_block_does_not_stop_the_push(tmp_path):
    root = _repo(tmp_path)
    _write(root, SHARD, _line("2168", "pass", 1) + "\n")
    _commit(root, "fix: something (#2168)")
    _write(root, SHARD, _line("2168", "pass", 1) + "\n" + _line("2168", "block", 2) + "\n")
    assert not _blocked(mod.check(root)[0], "2168")


@pytest.mark.parametrize("plan_issue,blocked", [(42, True), (43, False)],
                         ids=["own-plan", "foreign-plan"])
def test_a_tier1_plan_joins_a_work_slug_with_the_claimed_issue(tmp_path, plan_issue, blocked):
    # the line says work=my-feature, the commit says (#42): only the plan knows both
    root = _repo(tmp_path)
    _write(root, ".process-work/plans/2026-09-28-my-feature.md",
           f"# Plan\n\nissue: #{plan_issue}\ntier: 1\n")
    _write(root, SHARD, _line("my-feature", "block", 1) + "\n")
    _on_main(root, "docs: plan and attest")
    _commit(root, "fix: something (#42)")
    assert _blocked(mod.check(root)[0], "my-feature") is blocked


# --- no integration ref: no range — refuse instead of HEAD~1 --------------------------

@pytest.mark.parametrize("verdict,refused", [("block", True), ("pass", False)])
def test_missing_integration_refs_refuse_only_with_a_block_in_sight(tmp_path, verdict, refused):
    root = _repo(tmp_path)
    _write(root, SHARD, _line("42", verdict, 1) + "\n")
    _commit(root, "fix: something (#42)")
    _commit(root, "docs: follow-up")
    _git(root, "branch", "-D", "main")
    assert _cannot_tell(mod.check(root)[0]) is refused


# --- the pushed commit is checked, not HEAD -------------------------------------------

def test_the_pushed_sha_carries_the_block_wherever_head_stands(tmp_path):
    root = _repo(tmp_path)
    _write(root, SHARD, _line("42", "block", 1) + "\n")
    pushed = _commit(root, "fix: something (#42)")
    _git(root, "checkout", "-q", "main")
    _git(root, "checkout", "-q", "-b", "unrelated")
    (root / "other.txt").write_text("other\n", encoding="utf-8")
    _on_main(root, "chore: unrelated")
    assert not mod.standing_block_findings(root, "HEAD")
    assert _blocked(mod.standing_block_findings(root, pushed), "42")


def _run_cli(root: Path, *args: str):
    return subprocess.run([sys.executable, str(_SCRIPT), "--standing-block", *args], cwd=root,
                          capture_output=True, text=True)


def test_the_cli_stops_a_blocked_sha(tmp_path):
    root = _repo(tmp_path)
    _write(root, SHARD, _line("42", "block", 1) + "\n")
    blocked = _commit(root, "fix: something (#42)")
    r = _run_cli(root, blocked)
    assert r.returncode == 1 and "verdict=block" in r.stderr
    assert _run_cli(root, _git(root, "rev-parse", "main")).returncode == 0


# --- the range starts at the remote SHA of the ref line -------------------------------

def _advanced_local_main(tmp_path: Path, verdict: str = "block") -> tuple[Path, str, str]:
    """(root, tip, remote_sha): local main already stands on tip, no origin/main."""
    root = _repo(tmp_path)
    remote_sha = _git(root, "rev-parse", "main")
    _write(root, SHARD, _line("42", verdict, 1) + "\n")
    tip = _commit(root, "fix: something (#42)")
    _git(root, "checkout", "-q", "main")
    _git(root, "merge", "-q", "--ff-only", tip)
    return root, tip, remote_sha


def test_an_advanced_local_main_does_not_empty_the_range(tmp_path):
    root, tip, remote_sha = _advanced_local_main(tmp_path)
    assert _blocked(mod.standing_block_findings(root, tip, remote_sha=remote_sha), "42")


def test_the_cli_takes_the_remote_sha_as_its_second_part(tmp_path):
    root, tip, remote_sha = _advanced_local_main(tmp_path)
    r = _run_cli(root, f"{tip}:{remote_sha}")
    assert r.returncode == 1 and "verdict=block" in r.stderr, r.stderr


@pytest.mark.parametrize("origin", [None, "remote", "tip"])
@pytest.mark.parametrize("remote_sha", ["0" * 40, "ab" * 20, "", "  ", "zz" * 20, "abc"],
                         ids=["new-ref", "not-in-clone", "empty", "blank", "no-hex", "short"])
def test_an_unusable_remote_sha_refuses_whatever_origin_says(tmp_path, origin, remote_sha):
    # neither the local main nor origin/main stands in for the base the remote has
    root, tip, real = _advanced_local_main(tmp_path)
    if origin:
        _git(root, "update-ref", "refs/remotes/origin/main", real if origin == "remote" else tip)
    findings = mod.standing_block_findings(root, tip, remote_sha=remote_sha)
    assert _cannot_tell(findings), findings
    assert not any("verdict=block" in f for f in findings), findings


def test_an_unrelated_remote_history_refuses(tmp_path):
    root, tip, _real = _advanced_local_main(tmp_path)
    _git(root, "checkout", "-q", "--orphan", "foreign")
    _git(root, "rm", "-rqf", ".")
    (root / "other.txt").write_text("x\n", encoding="utf-8")
    unrelated = _on_main(root, "unrelated")
    assert _cannot_tell(mod.standing_block_findings(root, tip, remote_sha=unrelated))


def test_a_resolvable_remote_sha_stays_the_base(tmp_path):
    root, tip, remote_sha = _advanced_local_main(tmp_path)
    _git(root, "update-ref", "refs/remotes/origin/main", tip)
    assert _blocked(mod.standing_block_findings(root, tip, remote_sha=remote_sha), "42")


@pytest.mark.parametrize("remote_sha", ["zz" * 20, "0" * 40, "ab" * 20, ""])
def test_an_unusable_remote_sha_refuses_even_without_a_block(tmp_path, remote_sha):
    # the base is decided before the question "is there a block?"
    root, tip, _real = _advanced_local_main(tmp_path, verdict="pass")
    assert _cannot_tell(mod.standing_block_findings(root, tip, remote_sha=remote_sha))


def test_a_later_pass_clears_the_block_with_a_remote_sha_too(tmp_path):
    root = _repo(tmp_path)
    remote_sha = _git(root, "rev-parse", "main")
    _write(root, SHARD, _line("42", "block", 1) + "\n" + _line("42", "pass", 2) + "\n")
    tip = _commit(root, "fix: something (#42)")
    assert mod.standing_block_findings(root, tip, remote_sha=remote_sha) == []


# --- the anchor readers fail loudly; user config does not blind them ------------------

def _block_push(tmp_path: Path, verdict: str = "block") -> tuple[Path, str, str]:
    """The push carries work 42 ONLY through the REVIEW line its range adds."""
    root = _repo(tmp_path)
    remote_sha = _git(root, "rev-parse", "main")
    _write(root, SHARD, _line("42", verdict, 1) + "\n")
    tip = _commit(root, "docs: attest round 1")
    return root, tip, remote_sha


@pytest.mark.parametrize("subcommand", ["log", "diff", "rev-list", "ls-tree"])
def test_a_git_failure_reading_the_range_refuses(tmp_path, monkeypatch, subcommand):
    root, tip, remote_sha = _block_push(tmp_path)
    real = mod._git_bytes

    def failing(repo, *args):
        # ls-tree at the base only: the tip's records are read before the range
        if subcommand == "ls-tree" and (args[:1] != ("ls-tree",) or remote_sha not in args):
            return real(repo, *args)
        return None if subcommand in args and "merge-base" not in args else real(repo, *args)

    monkeypatch.setattr(mod, "_git_bytes", failing)
    findings = mod.standing_block_findings(root, tip, remote_sha=remote_sha)
    assert any("cannot read the pushed range" in f for f in findings), findings


def test_a_git_failure_without_a_standing_block_does_not_refuse(tmp_path, monkeypatch):
    root, tip, remote_sha = _block_push(tmp_path, verdict="pass")
    real = mod._git_bytes
    monkeypatch.setattr(mod, "_git_bytes",
                        lambda repo, *args: None if "log" in args else real(repo, *args))
    assert mod.standing_block_findings(root, tip, remote_sha=remote_sha) == []


@pytest.mark.parametrize("setting", [("diff.external", "true"), ("color.diff", "always"),
                                     ("color.ui", "always"), ("diff.interHunkContext", "3")])
def test_diff_configuration_does_not_open_the_guard(tmp_path, setting):
    root, tip, remote_sha = _block_push(tmp_path)
    _git(root, "config", *setting)
    assert _blocked(mod.standing_block_findings(root, tip, remote_sha=remote_sha), "42")


@pytest.mark.parametrize("attributes", ["*.md diff=blank\n", "*.md -diff\n"])
def test_diff_attributes_do_not_hide_a_new_block(tmp_path, attributes):
    root = _repo(tmp_path)
    remote_sha = _git(root, "rev-parse", "main")
    _git(root, "config", "diff.blank.textconv", "true")
    _write(root, ".gitattributes", attributes)
    _write(root, SHARD, _line("42", "block", 1) + "\n")
    tip = _commit(root, "docs: attest round 1")
    assert _blocked(mod.standing_block_findings(root, tip, remote_sha=remote_sha), "42")


@pytest.mark.parametrize("name", ["prüfen.md", "tab\tname.md"])
def test_a_block_in_a_shard_git_would_quote_stops_the_push(tmp_path, name):
    root = _repo(tmp_path)
    remote_sha = _git(root, "rev-parse", "main")
    _write(root, f".process-work/journal/{name}", _line("42", "block", 1) + "\n")
    tip = _commit(root, "docs: attest round 1")
    assert _blocked(mod.standing_block_findings(root, tip, remote_sha=remote_sha), "42")
    assert f".process-work/journal/{name}" in mod.paths_in_flight(
        root, tip, base=remote_sha, strict=True)


def test_a_malformed_review_line_at_the_tip_refuses(tmp_path):
    root = _repo(tmp_path)
    remote_sha = _git(root, "rev-parse", "main")
    _write(root, SHARD, _line("42", "block", 1).replace("round=1", "round=") + "\n")
    tip = _commit(root, "docs: attest round 1 (#42)")
    findings = mod.standing_block_findings(root, tip, remote_sha=remote_sha)
    assert any("malformed REVIEW line" in f and "2026-09-28.md:1" in f for f in findings), findings


def test_a_fenced_malformed_line_is_a_quotation(tmp_path):
    root = _repo(tmp_path)
    remote_sha = _git(root, "rev-parse", "main")
    _write(root, SHARD, "```\nREVIEW work=42 verdict=block round=\n```\n")
    tip = _commit(root, "docs: note (#42)")
    assert mod.standing_block_findings(root, tip, remote_sha=remote_sha) == []


# --- "added in the range" is record identity, not diff text ---------------------------

_LONG = "".join(f"line {n}: free text that lowers the similarity.\n" for n in range(40))


def _foreign_block_on_main(tmp_path: Path) -> tuple[Path, str]:
    """main carries a shard with the block of the foreign work 99; (root, remote_sha)."""
    root = _repo(tmp_path)
    _write(root, ".process-work/journal/2026-09-27.md", _line("99", "block", 1) + "\n")
    remote_sha = _on_main(root, "docs: attest 99 round 1")
    _git(root, "checkout", "-q", "-b", "feature")
    return root, remote_sha


OLD = ".process-work/journal/2026-09-27.md"
NEW = ".process-work/journal/2026-09-28.md"


@pytest.mark.parametrize("edit", ["rename", "rename-long", "rename-reuse", "chain", "move-line"])
def test_moving_a_foreign_block_does_not_pull_it_into_the_push(tmp_path, edit):
    root, remote_sha = _foreign_block_on_main(tmp_path)
    if edit == "move-line":
        (root / OLD).write_text("", encoding="utf-8")
        _write(root, NEW, _line("99", "block", 1) + "\n")
    else:
        _git(root, "mv", OLD, NEW)
    if edit == "rename-long":
        (root / NEW).write_text((root / NEW).read_text() + _LONG, encoding="utf-8")
    if edit == "rename-reuse":
        _write(root, OLD, "a new day, new text\n")
    if edit == "chain":
        _git(root, "commit", "-q", "-am", "docs: first move")
        _git(root, "mv", NEW, ".process-work/journal/2026-09-29.md")
        extended = root / ".process-work/journal/2026-09-29.md"
        extended.write_text(extended.read_text() + _LONG, encoding="utf-8")
    tip = _commit(root, "docs: move the shard")
    assert not _blocked(mod.standing_block_findings(root, tip, remote_sha=remote_sha), "99")


@pytest.mark.parametrize("rename", [False, True])
def test_an_own_new_line_counts_in_a_renamed_or_shared_shard(tmp_path, rename):
    root, remote_sha = _foreign_block_on_main(tmp_path)
    target = NEW if rename else OLD
    if rename:
        _git(root, "mv", OLD, NEW)
    shard = root / target
    shard.write_text(shard.read_text() + _LONG + _line("42", "block", 1) + "\n", encoding="utf-8")
    tip = _commit(root, "docs: attest round 1")
    findings = mod.standing_block_findings(root, tip, remote_sha=remote_sha)
    assert _blocked(findings, "42") and not _blocked(findings, "99"), findings


def test_unchanged_foreign_block_between_edited_neighbours_is_not_new(tmp_path):
    root = _repo(tmp_path)
    _write(root, OLD, f"head\nline a\n{_line('99', 'block', 1)}\nline b\nfoot\n")
    remote_sha = _on_main(root, "docs: attest 99 round 1")
    _git(root, "config", "diff.interHunkContext", "3")
    _git(root, "checkout", "-q", "-b", "feature")
    _write(root, OLD, f"head\nline a2\n{_line('99', 'block', 1)}\nline b2\nfoot\n")
    tip = _commit(root, "docs: edit the neighbours")
    assert not _blocked(mod.standing_block_findings(root, tip, remote_sha=remote_sha), "99")


@pytest.mark.parametrize("target", [OLD, NEW], ids=["same-shard", "second-shard"])
def test_a_duplicate_block_line_anchors_the_work(tmp_path, target):
    # no issue commit, no issue folder: the only anchor is the second, identical block line
    root, remote_sha = _foreign_block_on_main(tmp_path)
    shard = root / target
    before = shard.read_text(encoding="utf-8") if shard.exists() else ""
    _write(root, target, before + _line("99", "block", 1) + "\n")
    tip = _commit(root, "chore: code")
    assert _blocked(mod.standing_block_findings(root, tip, remote_sha=remote_sha), "99")


# --- the history of the range, not only its end state ---------------------------------

def test_a_base_block_the_range_deletes_still_stands(tmp_path):
    root = _repo(tmp_path)
    _write(root, OLD, _line("42", "block", 1) + "\n")
    remote_sha = _on_main(root, "docs: attest 42 round 1")
    _git(root, "checkout", "-q", "-b", "feature")
    (root / OLD).write_text("", encoding="utf-8")
    tip = _commit(root, "fix: something (#42)")
    assert _blocked(mod.standing_block_findings(root, tip, remote_sha=remote_sha), "42")


def test_a_block_brought_in_and_dropped_again_still_stands(tmp_path):
    root = _repo(tmp_path)
    remote_sha = _git(root, "rev-parse", "main")
    _write(root, SHARD, _line("42", "block", 1) + "\n")
    _commit(root, "docs: attest round 1")
    (root / SHARD).write_text("", encoding="utf-8")
    tip = _commit(root, "fix: something (#42)")
    assert _blocked(mod.standing_block_findings(root, tip, remote_sha=remote_sha), "42")


def test_a_deleted_block_with_a_higher_pass_is_cleared(tmp_path):
    root = _repo(tmp_path)
    _write(root, OLD, _line("42", "block", 1) + "\n")
    remote_sha = _on_main(root, "docs: attest 42 round 1")
    _git(root, "checkout", "-q", "-b", "feature")
    (root / OLD).write_text(_line("42", "pass", 2) + "\n", encoding="utf-8")
    tip = _commit(root, "fix: something (#42)")
    assert mod.standing_block_findings(root, tip, remote_sha=remote_sha) == []


def test_deleting_a_foreign_block_does_not_anchor_the_foreign_work(tmp_path):
    root, remote_sha = _foreign_block_on_main(tmp_path)
    (root / OLD).write_text("", encoding="utf-8")
    tip = _commit(root, "chore: tidy the journal")
    assert not _blocked(mod.standing_block_findings(root, tip, remote_sha=remote_sha), "99")


def test_a_reverted_pass_does_not_clear_the_block(tmp_path):
    root = _repo(tmp_path)
    remote_sha = _git(root, "rev-parse", "main")
    _write(root, SHARD, _line("42", "block", 1) + "\n")
    _commit(root, "feat: x (#42)")
    _write(root, SHARD, _line("42", "block", 1) + "\n" + _line("42", "pass", 2) + "\n")
    _commit(root, "docs: attest 42 round 2")
    _git(root, "revert", "--no-edit", "HEAD")
    tip = _git(root, "rev-parse", "HEAD")
    assert _blocked(mod.standing_block_findings(root, tip, remote_sha=remote_sha), "42")


def test_a_pass_main_holds_stays_mains_verdict(tmp_path):
    # the range deletes the pass line: main already judged, the work does not reopen
    root = _repo(tmp_path)
    _write(root, OLD, _line("42", "block", 1) + "\n" + _line("42", "pass", 2) + "\n")
    remote_sha = _on_main(root, "docs: history")
    _git(root, "checkout", "-q", "-b", "feature")
    _write(root, OLD, _line("42", "block", 1) + "\n")
    tip = _commit(root, "fix: follow-up (#42)")
    assert mod.standing_block_findings(root, tip, remote_sha=remote_sha) == []


def test_pruning_an_issue_folder_main_already_cleared_does_not_stop(tmp_path):
    root = _repo(tmp_path)
    _write(root, ".process-work/journal/issue-42/a.md",
           _line("42", "block", 1) + "\n" + _line("42", "pass", 2) + "\n")
    remote_sha = _on_main(root, "docs: history")
    _git(root, "checkout", "-q", "-b", "feature")
    _git(root, "rm", "-rq", ".process-work/journal/issue-42")
    tip = _commit(root, "chore: prune old journal")
    assert mod.standing_block_findings(root, tip, remote_sha=remote_sha) == []


def test_a_block_after_mains_pass_stands(tmp_path):
    root = _repo(tmp_path)
    shard = ".process-work/journal/issue-42/a.md"
    _write(root, shard, _line("42", "pass", 1) + "\n")
    remote_sha = _on_main(root, "docs: history")
    _git(root, "checkout", "-q", "-b", "feature")
    _write(root, shard, _line("42", "pass", 1) + "\n" + _line("42", "block", 2) + "\n")
    _commit(root, "docs: attest 42 round 2")
    _write(root, shard, _line("42", "pass", 1) + "\n")
    tip = _commit(root, "fix: drop the block (#42)")
    assert _blocked(mod.standing_block_findings(root, tip, remote_sha=remote_sha), "42")


def test_a_block_rewritten_to_pass_in_the_same_round_refuses(tmp_path):
    # indistinguishable from two parallel reviews of one round: count the round up
    root = _repo(tmp_path)
    remote_sha = _git(root, "rev-parse", "main")
    _write(root, SHARD, _line("42", "block", 1) + "\n")
    _commit(root, "feat: x (#42)")
    _write(root, SHARD, _line("42", "pass", 1) + "\n")
    tip = _commit(root, "docs: complete the review")
    assert _blocked(mod.standing_block_findings(root, tip, remote_sha=remote_sha), "42")


def test_a_parallel_block_a_merge_dropped_still_stands(tmp_path):
    root = _repo(tmp_path)
    remote_sha = _git(root, "rev-parse", "main")
    shard = ".process-work/journal/a.md"
    _write(root, shard, _line("42", "block", 1) + "\n")
    _commit(root, "feat: x (#42)")
    _git(root, "checkout", "-q", "-b", "rb")
    _write(root, shard, _line("42", "block", 1) + "\n" + _line("42", "block", 2) + "\n")
    _git(root, "commit", "-qam", "docs: review b round 2")
    _git(root, "checkout", "-q", "feature")
    _write(root, shard, _line("42", "block", 1) + "\n" + _line("42", "pass", 2) + "\n")
    _git(root, "commit", "-qam", "docs: review a round 2")
    subprocess.run(["git", "-C", str(root), "merge", "-q", "--no-edit", "rb"], capture_output=True)
    _git(root, "checkout", "-q", "--ours", shard)
    _git(root, "commit", "-qam", "merge")
    tip = _git(root, "rev-parse", "HEAD")
    assert _blocked(mod.standing_block_findings(root, tip, remote_sha=remote_sha), "42")


def test_mains_pass_does_not_clear_a_new_block_of_its_round(tmp_path):
    root = _repo(tmp_path)
    shard = ".process-work/journal/a.md"
    _write(root, shard, _line("42", "block", 1) + "\n" + _line("42", "pass", 2) + "\n")
    remote_sha = _on_main(root, "docs: history")
    _git(root, "checkout", "-q", "-b", "feature")
    _write(root, shard, _line("42", "block", 1) + "\n" + _line("42", "pass", 2) + "\n"
           + _line("42", "block", 2) + "\n")
    _commit(root, "fix: y (#42)")
    _write(root, shard, _line("42", "block", 1) + "\n" + _line("42", "pass", 2) + "\n")
    tip = _commit(root, "docs: drop")
    assert _blocked(mod.standing_block_findings(root, tip, remote_sha=remote_sha), "42")


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="needs symlinks")
@pytest.mark.parametrize("where", ["shard", "folder", "journal"])
def test_a_symlink_in_the_journal_refuses(tmp_path, where):
    # git hands a symlink's blob as the link text: the block behind it would not be read
    root = _repo(tmp_path)
    remote_sha = _git(root, "rev-parse", "main")
    _write(root, "notes/d/x.md", _line("42", "block", 1) + "\n")
    journal = root / ".process-work/journal"
    if where == "journal":
        journal.parent.mkdir(parents=True, exist_ok=True)
        journal.symlink_to("../notes/d")
    else:
        journal.mkdir(parents=True, exist_ok=True)
        if where == "folder":
            (journal / "d").symlink_to("../../notes/d")
        else:
            (journal / "2026-09-28.md").symlink_to("../../notes/d/x.md")
    tip = _commit(root, "feat: x (#42)")
    findings = mod.standing_block_findings(root, tip, remote_sha=remote_sha)
    assert any("symlink" in f for f in findings), findings
