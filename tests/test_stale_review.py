"""stale_review against the refutation of the ancestor fix.

Each scenario is one way unreviewed code reached a push while the review
still counted — or one way a fellow merge-train passenger must NOT count.
"""
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "template/scripts/process/check_review.py"


def _mod():
    # loaded straight from the template tree: no __pycache__ may land there,
    # it would be rendered into every project
    before = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec = importlib.util.spec_from_file_location("check_review_stale", _SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        sys.dont_write_bytecode = before
    return mod


def _git(root, *args):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True).stdout.strip()


def _commit(root, rel, text, msg):
    (root / rel).parent.mkdir(parents=True, exist_ok=True)
    (root / rel).write_text(text)
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", msg)
    return _git(root, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "r"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@t")
    _git(root, "config", "user.name", "t")
    _commit(root, "a.py", "a = 0\n", "base")
    _git(root, "checkout", "-q", "-b", "feat")
    head = _commit(root, "a.py", "a = 1\n", "reviewed work")
    return root, head


def _stale(root, head):
    return _mod().stale_review(root, [{"work": "w", "tier": "2", "head": head}], {"w"}, 2, set())


def test_holds_on_the_reviewed_head_and_after_bookkeeping(repo):
    root, head = repo
    assert _stale(root, head) is None
    _commit(root, ".process-work/journal/d.md", "REVIEW …\n", "attest")
    assert _stale(root, head) is None


def test_a_later_commit_is_stale(repo):
    root, head = repo
    _commit(root, "b.py", "b = 1\n", "after")
    assert "code changed after the reviewed head (b.py)" in _stale(root, head)


def test_an_unreviewed_side_branch_merged_in_is_stale(repo):
    root, head = repo
    _git(root, "checkout", "-q", "-b", "fix", "main")
    _commit(root, "evil.py", "x = 1\n", "unreviewed")
    _git(root, "checkout", "-q", "feat")
    _git(root, "merge", "-q", "--no-edit", "fix")
    assert "evil.py" in _stale(root, head)


def test_an_amend_merged_back_next_to_the_reviewed_head_is_stale(repo):
    root, head = repo
    _git(root, "checkout", "-q", "-b", "laundered", "main")
    _commit(root, "a.py", "a = 99\n", "the amended version")
    _git(root, "merge", "-q", "--no-edit", "-X", "ours", head)
    assert "a.py" in _stale(root, head)


def test_an_ours_merge_that_discards_the_review_is_stale(repo):
    root, head = repo
    _git(root, "checkout", "-q", "-b", "alt", "main")
    _commit(root, "a.py", "a = 42\n", "alt")
    _git(root, "merge", "-q", "--no-edit", "-s", "ours", head)
    assert "a.py" in _stale(root, head)


def test_amend_and_rebase_are_stale(repo):
    root, head = repo
    (root / "a.py").write_text("a = 2\n")
    _git(root, "commit", "-q", "-a", "--amend", "--no-edit")
    assert "is not in the history" in _stale(root, head)


def test_main_merged_in_cleanly_is_not_this_works_code(repo):
    root, head = repo
    _git(root, "checkout", "-q", "main")
    _commit(root, "m.py", "m = 1\n", "main moves on")
    _git(root, "checkout", "-q", "feat")
    _git(root, "merge", "-q", "--no-edit", "main")
    assert _stale(root, head) is None


def test_fellow_train_passengers_do_not_count_but_a_fix_does(repo):
    root, head = repo
    _git(root, "checkout", "-q", "-b", "other", "main")
    _commit(root, "o.py", "o = 1\n", "other passenger (tier 1, no review)")
    _git(root, "checkout", "-q", "-b", "train/a", "main")
    _git(root, "merge", "-q", "--no-ff", "--no-edit", "feat")
    _git(root, "merge", "-q", "--no-ff", "--no-edit", "other")
    assert _stale(root, head) is None
    _git(root, "checkout", "-q", "feat")
    _commit(root, "a.py", "a = 3\n", "fix after the review")
    _git(root, "checkout", "-q", "-B", "train/b", "main")
    _git(root, "merge", "-q", "--no-ff", "--no-edit", "feat")
    _git(root, "merge", "-q", "--no-ff", "--no-edit", "other")
    assert "a.py" in _stale(root, head) and "o.py" not in _stale(root, head)


def test_an_evil_train_merge_is_stale(repo):
    root, head = repo
    _git(root, "checkout", "-q", "-b", "train/a", "main")
    _git(root, "merge", "-q", "--no-ff", "--no-commit", "feat")
    (root / "a.py").write_text("a = 666\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "--no-edit")
    assert "a.py" in _stale(root, head)


def test_git_failure_fails_closed(repo, monkeypatch):
    root, head = repo
    mod = _mod()
    real = mod._git_bytes

    def broken(r, *args):
        return None if args and args[0] in ("log", "rev-list") else real(r, *args)

    monkeypatch.setattr(mod, "_git_bytes", broken)
    found = mod.stale_review(root, [{"work": "w", "tier": "2", "head": head}], {"w"}, 2, set())
    assert found is not None and "cannot determine" in found


def test_a_headless_pass_does_not_override_a_stale_one(repo):
    root, head = repo
    _commit(root, "b.py", "b = 1\n", "after")
    passes = [{"work": "w", "tier": "2"}, {"work": "w", "tier": "2", "head": head}]
    assert "b.py" in _mod().stale_review(root, passes, {"w"}, 2, set())


def test_evil_content_in_a_fellow_passengers_train_merge_is_stale(repo):
    root, head = repo
    _git(root, "checkout", "-q", "-b", "other", "main")
    _commit(root, "o.py", "o = 1\n", "other passenger")
    _git(root, "checkout", "-q", "-b", "train/a", "main")
    _git(root, "merge", "-q", "--no-ff", "--no-commit", "other")
    (root / "evil.py").write_text("u = 1\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "--no-edit")
    _git(root, "merge", "-q", "--no-ff", "--no-edit", "feat")
    assert "evil.py" in _stale(root, head)


def test_a_crafted_chain_merge_with_an_evil_tree_is_stale(repo):
    root, head = repo
    _git(root, "checkout", "-q", "main")
    _commit(root, "m.py", "m = 1\n", "main moves on")  # main~1 exists now
    _git(root, "checkout", "-q", "-b", "train/a", "main")
    (root / "evil.py").write_text("u = 1\n")
    _git(root, "add", "evil.py")
    tree = _git(root, "write-tree")
    m1 = _git(root, "commit-tree", tree, "-p", "main", "-p", "main~1", "-m", "step")
    _git(root, "reset", "-q", "--hard", m1)
    _git(root, "merge", "-q", "--no-ff", "--no-edit", "feat")
    assert "evil.py" in _stale(root, head)


def test_pushing_local_main_without_a_remote_ref_is_checked(repo):
    root, head = repo
    _git(root, "checkout", "-q", "main")
    _git(root, "merge", "-q", "--ff-only", "feat")
    _commit(root, "a.py", "a = 5\n", "unreviewed on main")
    assert "a.py" in _stale(root, head)


def test_a_conflict_resolved_to_the_other_side_is_stale(repo):
    # the result equals main's version, so the
    # combined diff is empty although the reviewed change was thrown away
    root, head = repo
    _git(root, "checkout", "-q", "main")
    _commit(root, "a.py", "a = 'main'\n", "main edits the same line")
    _git(root, "checkout", "-q", "feat")
    subprocess.run(["git", "merge", "--no-edit", "main"], cwd=root, capture_output=True)
    _git(root, "checkout", "--theirs", "a.py")
    _git(root, "add", "a.py")
    _git(root, "commit", "-q", "--no-edit")
    assert "a.py" in _stale(root, head)


def test_a_rename_on_main_resolved_to_mains_side_is_stale(tmp_path):
    # main renames and edits the file; git sees the rename, the content
    # conflicts, the resolution takes main's side — the reviewed edit is gone
    root = tmp_path / "r3"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@t")
    _git(root, "config", "user.name", "t")
    lines = [f"line{i} = {i}\n" for i in range(20)]
    _commit(root, "f.py", "".join(lines), "base")
    _git(root, "checkout", "-q", "-b", "feat")
    mine = lines.copy()
    mine[0] = "line0 = 'reviewed'\n"
    head = _commit(root, "f.py", "".join(mine), "reviewed work")
    _git(root, "checkout", "-q", "main")
    _git(root, "mv", "f.py", "g.py")
    theirs = lines.copy()
    theirs[0] = "line0 = 'main'\n"
    (root / "g.py").write_text("".join(theirs))
    _git(root, "commit", "-q", "-am", "main renames and edits")
    _git(root, "checkout", "-q", "feat")
    subprocess.run(["git", "merge", "--no-edit", "main"], cwd=root, capture_output=True)
    _git(root, "checkout", "--theirs", "g.py")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "--no-edit")
    assert _stale(root, head) is not None


def test_main_already_carrying_the_reviewed_change_merges_clean(tmp_path):
    # a squash/cherry-pick of the reviewed change landed on main, then a later
    # edit further down the same file; the branch merges main cleanly —
    # nothing was thrown away
    root = tmp_path / "r2"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@t")
    _git(root, "config", "user.name", "t")
    lines = [f"line{i} = {i}\n" for i in range(20)]
    _commit(root, "f.py", "".join(lines), "base")
    _git(root, "checkout", "-q", "-b", "feat")
    reviewed = lines.copy()
    reviewed[0] = "line0 = 'reviewed'\n"
    head = _commit(root, "f.py", "".join(reviewed), "reviewed work")
    _git(root, "checkout", "-q", "main")
    _commit(root, "f.py", "".join(reviewed), "the reviewed change, squashed")
    later = reviewed.copy()
    later[19] = "line19 = 'later'\n"
    _commit(root, "f.py", "".join(later), "a later edit")
    _git(root, "checkout", "-q", "feat")
    _git(root, "merge", "-q", "--no-edit", "main")
    assert _stale(root, head) is None


def test_a_work_branch_of_merges_only_is_no_train(repo):
    # the work branch holds only merges: the reviewed sub-branch and, after
    # the review, a side branch — the chain looks like a train's, but it is
    # not the train's staging branch, so the side branch's code is unreviewed
    root, head = repo
    _git(root, "checkout", "-q", "-b", "side", "main")
    _commit(root, "s.py", "s = 1\n", "side work, never reviewed")
    _git(root, "checkout", "-q", "-b", "work", "main")
    _git(root, "merge", "-q", "--no-ff", "--no-edit", "feat")
    _git(root, "merge", "-q", "--no-ff", "--no-edit", "side")
    assert "s.py" in _stale(root, head)


def test_a_headless_pass_does_not_clear_once_a_pass_records_a_head(repo):
    root, head = repo
    _commit(root, "b.py", "b = 1\n", "after")
    passes = [{"work": "w", "tier": "2"}, {"work": "w", "tier": "1", "head": head}]
    found = _mod().stale_review(root, passes, {"w"}, 2, set())
    assert found is not None and "records the reviewed head" in found


def test_local_main_ahead_of_origin_is_the_base(repo):
    # a train merged another passenger into local main and has not pushed yet;
    # the work then merged local main — measured against the stale origin/main
    # the passenger's code read as this work's unreviewed code
    root, head = repo
    _git(root, "update-ref", "refs/remotes/origin/main", "main")
    _git(root, "checkout", "-q", "-b", "other", "main")
    _commit(root, "o.py", "o = 1\n", "other passenger")
    _git(root, "checkout", "-q", "main")
    _git(root, "merge", "-q", "--no-ff", "--no-edit", "other")
    _git(root, "checkout", "-q", "feat")
    _git(root, "merge", "-q", "--no-edit", "main")
    assert _stale(root, head) is None


# --- clean merges of hunks from both sides, fellow passengers, decide() table ---

_LINES = "".join(f"l{i} = {i}\n" for i in range(12))


@pytest.fixture
def shared(tmp_path):
    """A reviewed branch and main each change a different hunk of one file
    after the review (a shared inventory file, downstream)."""
    root = tmp_path / "s"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@t")
    _git(root, "config", "user.name", "t")
    _commit(root, "inv.md", _LINES, "base")
    _git(root, "checkout", "-q", "-b", "feat")
    head = _commit(root, "inv.md", _LINES.replace("l0 = 0", "l0 = 'feat'"), "reviewed work")
    _git(root, "checkout", "-q", "main")
    _commit(root, "inv.md", _LINES.replace("l11 = 11", "l11 = 'main'"), "main edits another hunk")
    return root, head


def test_a_clean_merge_of_hunks_from_both_sides_is_not_late_code(shared):
    root, head = shared
    _git(root, "checkout", "-q", "feat")
    _git(root, "merge", "-q", "--no-edit", "main")
    assert _stale(root, head) is None


def test_a_train_with_a_passenger_on_a_file_main_changed_blames_nobody(shared):
    # two passengers; one touches the file main changed since its review
    root, head = shared
    _git(root, "checkout", "-q", "-b", "other", "main")
    other_head = _commit(root, "o.py", "o = 1\n", "other passenger")
    _git(root, "checkout", "-q", "-b", "train/a", "main")
    _git(root, "merge", "-q", "--no-ff", "--no-edit", "feat")
    _git(root, "merge", "-q", "--no-ff", "--no-edit", "other")
    assert _stale(root, head) is None
    assert _stale(root, other_head) is None


def test_a_hunk_of_its_own_in_a_clean_merge_is_still_late_code(shared):
    root, head = shared
    _git(root, "checkout", "-q", "feat")
    _git(root, "merge", "-q", "--no-commit", "main")
    text = (root / "inv.md").read_text().replace("l5 = 5", "l5 = 'evil'")
    (root / "inv.md").write_text(text)
    _git(root, "commit", "-q", "-am", "merge main")
    assert "inv.md" in _stale(root, head)


def test_a_fellow_passengers_evil_merge_is_named_as_such_not_as_this_works_code(repo):
    root, head = repo
    _git(root, "checkout", "-q", "-b", "other", "main")
    _commit(root, "o.py", "o = 1\n", "other passenger")
    _git(root, "checkout", "-q", "-b", "train/a", "main")
    _git(root, "merge", "-q", "--no-ff", "--no-edit", "feat")
    _git(root, "merge", "-q", "--no-ff", "--no-commit", "other")
    (root / "evil.py").write_text("u = 1\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "--no-edit")
    found = _stale(root, head)
    assert "evil.py" in found and "of another passenger" in found
    assert "code changed after the reviewed head" not in found


def test_a_merge_dropping_a_reviewed_change_to_a_non_ascii_file_is_stale(tmp_path):
    root = tmp_path / "u"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@t")
    _git(root, "config", "user.name", "t")
    _commit(root, "prüfung.py", "p = 0\n", "base")
    _git(root, "checkout", "-q", "-b", "feat")
    head = _commit(root, "prüfung.py", "p = 1\n", "reviewed work")
    _git(root, "checkout", "-q", "main")
    _commit(root, "prüfung.py", "p = 'main'\n", "main edits the same line")
    _git(root, "checkout", "-q", "feat")
    subprocess.run(["git", "merge", "-q", "--no-edit", "main"], cwd=root, capture_output=True)
    _git(root, "checkout", "--theirs", "prüfung.py")
    _git(root, "commit", "-q", "-am", "resolved to main's side")
    found = _stale(root, head)
    assert found is not None and "prüfung.py" in found


def test_a_head_missing_from_a_shallow_clone_is_stale(repo, tmp_path):
    root, head = repo
    _commit(root, "b.py", "b = 1\n", "after")
    clone = tmp_path / "shallow"
    subprocess.run(["git", "clone", "-q", "--depth", "1", "--branch", "feat", f"file://{root}", str(clone)],
                   check=True, capture_output=True)
    found = _stale(clone, head)
    assert found is not None and "shallow clone" in found


_H = "a" * 40


@pytest.mark.parametrize("case,facts,verdict,words", [
    ("reviewed head in history, nothing after", {}, "fresh", ""),
    ("amend", {"in_history": False}, "stale", "not in the history"),
    ("rebase", {"in_history": False}, "stale", "not in the history"),
    ("clean main merge", {}, "fresh", ""),
    ("clean merge of hunks from both sides", {}, "fresh", ""),
    ("conflict resolution", {"late": frozenset({"a.py"})}, "stale", "code changed after"),
    ("resolution to the other side", {"dropped": frozenset({"a.py"})}, "stale", "threw the reviewed change away"),
    ("-s ours", {"dropped": frozenset({"a.py"})}, "stale", "threw the reviewed change away"),
    ("train --no-ff staging", {}, "fresh", ""),
    ("fellow passenger's evil merge", {"fellow": (("b" * 40, frozenset({"e.py"})),)}, "stale", "another passenger"),
    ("later code commit", {"late": frozenset({"b.py"})}, "stale", "code changed after"),
    ("git error", {"git_error": True}, "stale", "git did not answer"),
    ("shallow clone", {"shallow_missing": True}, "stale", "shallow clone"),
    # precedence: the first fact that decides names the reason
    ("git error beats everything", {"git_error": True, "in_history": False, "late": frozenset({"x"})},
     "stale", "git did not answer"),
    ("not in history beats late", {"in_history": False, "late": frozenset({"x"})}, "stale", "not in the history"),
    ("a drop beats late", {"dropped": frozenset({"d"}), "late": frozenset({"x"})}, "stale", "threw"),
    ("own code beats a fellow's", {"late": frozenset({"x"}), "fellow": (("b" * 40, frozenset({"e"})),)},
     "stale", "code changed after"),
])
def test_decide_table(case, facts, verdict, words):
    mod = _mod()
    got, reason = mod.decide(mod.History(**facts), _H)
    assert got == verdict and words in reason, case


# --- refute of the decide() table ---


def _raw(root, name: bytes, text: bytes):
    import os
    with open(os.path.join(os.fsencode(str(root)), name), "wb") as f:
        f.write(text)


def test_a_non_utf8_name_cannot_take_any_resolution(tmp_path):
    name = b"lat\xe9.py"
    for resolution in (b"x=1\nevil()\n", None):  # an evil resolution, and a drop to main's side
        root = tmp_path / ("r1" if resolution else "r2")
        root.mkdir()
        _git(root, "init", "-q", "-b", "main")
        _git(root, "config", "user.email", "t@t")
        _git(root, "config", "user.name", "t")
        _raw(root, name, b"x=0\n")
        _git(root, "add", "-A")
        _git(root, "commit", "-q", "-m", "base")
        _git(root, "checkout", "-q", "-b", "feat")
        _raw(root, name, b"x=1\n")
        _git(root, "commit", "-q", "-am", "reviewed")
        head = _git(root, "rev-parse", "HEAD")
        _git(root, "checkout", "-q", "main")
        _raw(root, name, b"x=2\n")
        _git(root, "commit", "-q", "-am", "main")
        _git(root, "checkout", "-q", "feat")
        subprocess.run(["git", "merge", "-q", "--no-edit", "main"], cwd=root, capture_output=True)
        _raw(root, name, resolution or b"x=2\n")
        _git(root, "commit", "-q", "-am", "merge")
        assert _stale(root, head) is not None, resolution


def test_a_file_named_only_whitespace_is_code(repo):
    root, head = repo
    for name in ("\t", " "):
        (root / name).write_text("evil\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "late")
    assert _stale(root, head) is not None


def test_a_submodule_bump_hidden_by_ignore_all_is_late_code(repo):
    root, head = repo
    sha = _git(root, "rev-parse", "HEAD")
    (root / ".gitmodules").write_text('[submodule "lib"]\n\tpath = vendor/lib\n\turl = ./x\n\tignore = all\n')
    _git(root, "add", ".gitmodules")
    _git(root, "update-index", "--add", "--cacheinfo", f"160000,{sha},vendor/lib")
    _git(root, "commit", "-q", "-m", "add submodule")
    head = _git(root, "rev-parse", "HEAD")
    _git(root, "update-index", "--cacheinfo", f"160000,{_git(root, 'rev-parse', 'main')},vendor/lib")
    _git(root, "commit", "-q", "-m", "bump")
    found = _stale(root, head)
    assert found is not None and "vendor/lib" in found


def test_a_root_commit_merged_in_counts_whatever_log_showroot_says(repo):
    root, head = repo
    _git(root, "config", "log.showRoot", "false")
    _git(root, "checkout", "-q", "--orphan", "stray")
    _git(root, "rm", "-rq", "--cached", ".")
    (root / "stray.py").write_text("s = 1\n")
    _git(root, "add", "stray.py")
    _git(root, "commit", "-q", "-m", "unrelated root")
    _git(root, "checkout", "-q", "-f", "feat")
    _git(root, "merge", "-q", "--no-edit", "--allow-unrelated-histories", "stray")
    found = _stale(root, head)
    assert found is not None and "stray.py" in found


def test_a_commit_made_on_local_main_by_mistake_is_not_integrated(repo):
    # the remote is the authority: a local main only counts beyond it for merges
    root, head = repo
    _git(root, "checkout", "-q", "main")
    _git(root, "update-ref", "refs/remotes/origin/main", "main")
    _git(root, "merge", "-q", "--ff-only", "feat")
    _commit(root, "u.py", "u = 1\n", "unreviewed, on local main by mistake")
    _git(root, "checkout", "-q", "-b", "feat2")
    _commit(root, ".process-work/journal/j.md", "REVIEW …\n", "attest")
    found = _stale(root, head)
    assert found is not None and "u.py" in found


def test_a_local_master_pointed_at_unreviewed_work_hides_nothing(repo):
    root, head = repo
    _git(root, "update-ref", "refs/remotes/origin/main", "main")
    unreviewed = _commit(root, "u.py", "u = 1\n", "unreviewed")
    _git(root, "branch", "master", unreviewed)
    _commit(root, ".process-work/journal/j.md", "REVIEW …\n", "attest")
    found = _stale(root, head)
    assert found is not None and "u.py" in found


def test_a_plan_of_merged_work_is_residue_not_a_blame(repo):
    # the plan sits on main and its reviewed head is in main: later changes are not its code
    root, head = repo
    plan = ".process-work/plans/2026-01-01-w.md"
    _commit(root, plan, "# w\ntier: 2\n", "plan")
    _git(root, "checkout", "-q", "main")
    _git(root, "merge", "-q", "--no-ff", "--no-edit", "feat")
    _git(root, "checkout", "-q", "-b", "later")
    _commit(root, "a.py", "a = 9\n", "later, separately reviewed work")
    passes = [{"work": "w", "tier": "2", "head": head}]
    mod = _mod()
    assert mod.merged_work(root, plan, passes, {"w"}, 2)
    _git(root, "checkout", "-q", "-b", "unmerged", head)
    assert not mod.merged_work(root, ".process-work/plans/none.md", passes, {"w"}, 2)


def test_another_review_covers_its_range_not_the_history_below_its_base(repo):
    # work A reviewed at `head`, then an unreviewed commit; work B stacked on
    # top and reviewed from there: B's review saw B's range only
    root, head = repo
    below = _commit(root, "a.py", "a = 2\n", "unreviewed A code")
    b_head = _commit(root, "b.py", "b = 1\n", "work B, reviewed")
    mod = _mod()
    reviewed = ((below, b_head),)
    found = mod.stale_review(root, [{"work": "w", "tier": "2", "head": head}], {"w"}, 2, set(), reviewed)
    assert found is not None and "a.py" in found and "b.py" not in found
    # a review whose range starts below the unreviewed commit covers it
    assert mod.stale_review(root, [{"work": "w", "tier": "2", "head": head}], {"w"}, 2, set(),
                            ((head, b_head),)) is None


def test_a_plan_review_or_a_pass_of_no_plan_covers_no_code(repo, tmp_path):
    root, head = repo
    late = _commit(root, "a.py", "a = 2\n", "unreviewed")
    mod = _mod()
    passes = [{"work": "w", "tier": "2", "head": head},
              {"work": "w-plan", "tier": "2", "base": head, "head": late},
              {"work": "ghost", "tier": "2", "base": head, "head": late}]
    known = {"w"}
    reviewed = mod._reviewed_heads(passes, 2, known)
    assert reviewed == ()
    assert "a.py" in mod.stale_review(root, passes, {"w"}, 2, set(), reviewed)
