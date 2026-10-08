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


def _train():
    before = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(_SCRIPT.parent))  # train imports its siblings
    try:
        spec = importlib.util.spec_from_file_location("train_stale", _SCRIPT.parent / "train.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        sys.path.remove(str(_SCRIPT.parent))
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


def test_a_fenced_example_id_names_no_work(repo):
    root, _head = repo
    _commit(root, ".process-work/plans/2026-01-01-w.md", "# w\ntier: 2\n\n```\nissue: 77\n```\n", "plan")
    assert "77" not in _mod()._known_work(root)


def test_a_drop_inside_another_reviews_range_is_still_a_drop(repo):
    # work B's review covers a merge that resolved THIS work's reviewed line
    # to main's side: B saw the merge, it did not review the drop for w
    root, head = repo
    _git(root, "checkout", "-q", "main")
    _commit(root, "a.py", "a = 'main'\n", "main edits the same line")
    _git(root, "checkout", "-q", "feat")
    b_base = _git(root, "rev-parse", "HEAD")
    subprocess.run(["git", "merge", "-q", "--no-edit", "main"], cwd=root, capture_output=True)
    _git(root, "checkout", "--theirs", "a.py")
    _git(root, "commit", "-q", "-am", "merge main, resolved to main's side")
    b_head = _commit(root, "b.py", "b = 1\n", "work B")
    found = _mod().stale_review(root, [{"work": "w", "tier": "2", "head": head}], {"w"}, 2, set(),
                                ((b_base, b_head),))
    assert found is not None and "a.py" in found


def test_unreviewed_paths_never_reads_an_amended_head_as_covered(repo):
    root, head = repo
    _git(root, "commit", "-q", "--amend", "-m", "amended")
    assert _mod()._unreviewed_paths(root, head, "HEAD") is None


def test_taking_mains_side_of_a_file_this_work_never_changed_is_no_drop(repo):
    # refutation S4: a stacked branch merges main and takes main's version of
    # a file another branch edited — not this work's change
    root, head = repo
    _git(root, "checkout", "-q", "main")
    _commit(root, "x.py", "x = 0\n", "x on main")
    _git(root, "checkout", "-q", "feat")
    _git(root, "merge", "-q", "--no-edit", "main")
    b_base = _commit(root, "x.py", "x = 'b'\n", "B edits x")
    _git(root, "checkout", "-q", "main")
    _commit(root, "x.py", "x = 'main'\n", "main edits x")
    _git(root, "checkout", "-q", "feat")
    subprocess.run(["git", "merge", "-q", "--no-edit", "main"], cwd=root, capture_output=True)
    _git(root, "checkout", "--theirs", "x.py")
    _git(root, "commit", "-q", "-am", "take main's x")
    b_head = _git(root, "rev-parse", "HEAD")
    found = _mod().stale_review(root, [{"work": "w", "tier": "2", "head": head}], {"w"}, 2, set(),
                                ((head, b_head),))
    assert found is None, found
    assert b_base


# --- refutation of the narrowed drop check: renames, modes, the review's own range ---

_ROWS = [f"line{i} = {i}\n" for i in range(20)]


def _edit_line(i, value):
    out = _ROWS.copy()
    out[i] = f"line{i} = {value!r}\n"
    return "".join(out)


def _fresh(tmp_path):
    root = tmp_path / "r"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@t")
    _git(root, "config", "user.name", "t")
    return root


def _merge(root, *args):
    subprocess.run(["git", "merge", "--no-edit", *args], cwd=root, capture_output=True)


def _judged(root, head, base=None, covered=()):
    record = {"work": "w", "tier": "2", "head": head, **({"base": base} if base else {})}
    return _mod().stale_review(root, [record], {"w"}, 2, set(), covered)


def test_a_file_this_work_renamed_and_the_merge_turned_back_to_mains_old_one_is_a_drop(tmp_path):
    root = _fresh(tmp_path)
    _commit(root, "f.py", "".join(_ROWS), "base")
    _git(root, "checkout", "-q", "-b", "feat")
    _git(root, "mv", "f.py", "g.py")
    head = _commit(root, "g.py", _edit_line(0, "reviewed"), "reviewed: rename and edit")
    _git(root, "checkout", "-q", "main")
    _commit(root, "f.py", _edit_line(0, "main"), "main edits line 0")
    _git(root, "checkout", "-q", "feat")
    _merge(root, "main")
    (root / "g.py").write_text(_edit_line(0, "main"))
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "--no-edit")
    b_head = _commit(root, "b.py", "b = 1\n", "work B")
    found = _judged(root, head, covered=((head, b_head),))
    assert found is not None and "g.py" in found


@pytest.mark.parametrize("covered", [False, True])
def test_a_new_file_git_moved_into_a_renamed_directory_and_the_merge_deleted_is_a_drop(tmp_path, covered):
    root = _fresh(tmp_path)
    _commit(root, "d/a.py", "a = 0\n", "base")
    _git(root, "checkout", "-q", "-b", "feat")
    head = _commit(root, "d/new.py", "new = 'reviewed'\n", "reviewed: new file")
    _git(root, "checkout", "-q", "main")
    _git(root, "mv", "d", "e")
    _git(root, "commit", "-q", "-m", "main moves d/ to e/")
    _git(root, "checkout", "-q", "feat")
    _merge(root, "main")
    _git(root, "rm", "-q", "--cached", "--ignore-unmatch", "e/new.py", "d/new.py")
    for rel in ("e/new.py", "d/new.py"):
        (root / rel).unlink(missing_ok=True)
    _git(root, "commit", "-q", "--no-edit")
    b_head = _commit(root, "b.py", "b = 1\n", "work B")
    found = _judged(root, head, covered=((head, b_head),) if covered else ())
    assert found is not None and "d/new.py" in found


def test_a_merge_that_takes_the_executable_bit_back_is_a_drop(tmp_path):
    root = _fresh(tmp_path)
    _commit(root, "run.sh", "echo hi\n", "base")
    _git(root, "checkout", "-q", "-b", "feat")
    (root / "run.sh").chmod(0o755)
    _git(root, "add", "run.sh")
    _git(root, "commit", "-q", "-m", "reviewed: run.sh executable")
    head = _git(root, "rev-parse", "HEAD")
    _git(root, "checkout", "-q", "main")
    _commit(root, "m.py", "m = 1\n", "main moves on")
    _git(root, "checkout", "-q", "feat")
    _git(root, "merge", "-q", "--no-commit", "main")
    (root / "run.sh").chmod(0o644)
    _git(root, "add", "run.sh")
    _git(root, "commit", "-q", "--no-edit")
    b_head = _commit(root, "b.py", "b = 1\n", "work B")
    found = _judged(root, head, covered=((head, b_head),))
    assert found is not None and "run.sh" in found


def test_a_stacked_branch_taking_mains_squash_of_the_branch_below_is_no_drop(tmp_path):
    # this work's review starts at the branch below (base..head): that
    # branch's file is not this work's, even if merge-base says so
    root = _fresh(tmp_path)
    _commit(root, "f.py", "".join(_ROWS), "base")
    _git(root, "checkout", "-q", "-b", "b1")
    below = _commit(root, "f.py", _edit_line(0, "b1-draft"), "B1 draft")
    _git(root, "checkout", "-q", "-b", "b2")
    head = _commit(root, "g.py", "g = 'b2'\n", "B2 reviewed")
    _git(root, "checkout", "-q", "b1")
    _commit(root, "f.py", _edit_line(0, "b1-final"), "B1 review fix-up")
    _git(root, "checkout", "-q", "main")
    _git(root, "merge", "-q", "--squash", "b1")
    _git(root, "commit", "-q", "-m", "B1 (squash)")
    _git(root, "checkout", "-q", "b2")
    _merge(root, "main")
    _git(root, "checkout", "--theirs", "f.py")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "--no-edit")
    assert _judged(root, head, base=below) is None
    # the review that saw B1's change as well still owns it
    first = _git(root, "rev-list", "--max-parents=0", "HEAD")
    found = _judged(root, head, base=first)
    assert found is not None and "f.py" in found
    # the merge train's boarding judges by the same range
    assert _mod()._unreviewed_paths(root, head, "HEAD", ((below, head),)) == set()
    assert "f.py" in _mod()._unreviewed_paths(root, head, "HEAD", ((first, head),))
    train = _train()
    record = {"work": "w", "tier": "2", "head": head, "base": below}
    assert train._covers(root, [record], {"w"}, 2, "HEAD")
    assert not train._covers(root, [{**record, "base": first}], {"w"}, 2, "HEAD")


def test_an_unrelated_import_taking_its_own_file_is_no_drop_of_this_work(tmp_path):
    root = _fresh(tmp_path)
    base = _commit(root, "LICENSE", "ours\n", "base")
    _git(root, "checkout", "-q", "-b", "feat")
    head = _commit(root, "a.py", "a = 1\n", "reviewed")
    _git(root, "checkout", "-q", "--orphan", "vendor")
    _git(root, "rm", "-rfq", ".")
    _commit(root, "LICENSE", "theirs\n", "vendor root")
    _git(root, "checkout", "-q", "feat")
    _merge(root, "--allow-unrelated-histories", "vendor")
    _git(root, "checkout", "--theirs", "LICENSE")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "--no-edit")
    merged = _git(root, "rev-parse", "HEAD")
    assert _judged(root, head, base=base, covered=((head, merged),)) is None


# --- second refutation: every round's range, a base that proves nothing, modes apart, moved onto main's file ---

def _two_sided(root):
    """fork -> feat edits f.py line 0; main edits line 0 too (a conflict)."""
    fork = _commit(root, "f.py", "".join(_ROWS), "base")
    _git(root, "checkout", "-q", "-b", "feat")
    return fork


def _resolve_theirs(root, *paths):
    for p in paths:
        _git(root, "checkout", "--theirs", p)
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "--no-edit")


def test_a_delta_rounds_base_does_not_hide_a_drop_of_the_first_rounds_code(tmp_path):
    # round 1 reviewed fork..h1; round 2 is a delta review (make_review_bundle --since h1): base=h1
    root = _fresh(tmp_path)
    fork = _two_sided(root)
    h1 = _commit(root, "f.py", _edit_line(0, "reviewed"), "round 1")
    h2 = _commit(root, "b.py", "b = 1\n", "round 2")
    _git(root, "checkout", "-q", "main")
    _commit(root, "f.py", _edit_line(0, "main"), "main edits line 0")
    _git(root, "checkout", "-q", "feat")
    _merge(root, "main")
    _resolve_theirs(root, "f.py")
    r1 = {"work": "w", "tier": "2", "head": h1, "base": fork}
    r2 = {"work": "w", "tier": "2", "head": h2, "base": h1}
    found = _mod().stale_review(root, [r1, r2], {"w"}, 2, set(), ((fork, h1), (h1, h2)))
    assert found is not None and "f.py" in found, found


def test_the_train_judges_a_delta_round_like_the_gate(tmp_path):
    root = _fresh(tmp_path)
    fork = _two_sided(root)
    h1 = _commit(root, "f.py", _edit_line(0, "reviewed"), "round 1")
    h2 = _commit(root, "b.py", "b = 1\n", "round 2")
    _git(root, "checkout", "-q", "main")
    _commit(root, "f.py", _edit_line(0, "main"), "main edits line 0")
    _git(root, "checkout", "-q", "feat")
    _merge(root, "main")
    _resolve_theirs(root, "f.py")
    r1 = {"work": "w", "tier": "2", "head": h1, "base": fork}
    r2 = {"work": "w", "tier": "2", "head": h2, "base": h1}
    assert not _train()._covers(root, [r1, r2], {"w"}, 2, "HEAD")


def test_a_base_equal_to_head_proves_nothing(tmp_path):
    root = _fresh(tmp_path)
    _two_sided(root)
    head = _commit(root, "f.py", _edit_line(0, "reviewed"), "reviewed")
    _git(root, "checkout", "-q", "main")
    _commit(root, "f.py", _edit_line(0, "main"), "main edits line 0")
    _git(root, "checkout", "-q", "feat")
    _merge(root, "main")
    _resolve_theirs(root, "f.py")
    found = _judged(root, head, base=head)
    assert found is not None and "f.py" in found, found


def test_mains_content_under_the_reviewed_mode_is_a_drop(tmp_path):
    # work edits run.sh and makes it +x; main edits the same line. The merge takes
    # main's content with the +x git itself would keep: the reviewed edit is gone.
    root = _fresh(tmp_path)
    _commit(root, "run.sh", "".join(_ROWS), "base")
    _git(root, "checkout", "-q", "-b", "feat")
    (root / "run.sh").write_text(_edit_line(0, "reviewed"))
    (root / "run.sh").chmod(0o755)
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "reviewed")
    head = _git(root, "rev-parse", "HEAD")
    _git(root, "checkout", "-q", "main")
    _commit(root, "run.sh", _edit_line(0, "main"), "main")
    _git(root, "checkout", "-q", "feat")
    _merge(root, "main")
    (root / "run.sh").write_text(_edit_line(0, "main"))
    (root / "run.sh").chmod(0o755)
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "--no-edit")
    b_head = _commit(root, "b.py", "b = 1\n", "work B")
    found = _judged(root, head, covered=((head, b_head),))
    assert found is not None and "run.sh" in found, found


def test_a_file_git_moved_onto_mains_own_and_resolved_to_mains_is_a_drop(tmp_path):
    # work adds d/new.py; main moves d/ -> e/ and adds its own e/new.py. git moves the
    # work's file onto e/new.py (conflict); the merge takes main's. No covering review.
    root = _fresh(tmp_path)
    _commit(root, "d/a.py", "".join(_ROWS), "base")
    _git(root, "checkout", "-q", "-b", "feat")
    head = _commit(root, "d/new.py", "new = 'reviewed'\n" + "".join(_ROWS), "reviewed: new file")
    _git(root, "checkout", "-q", "main")
    _git(root, "mv", "d", "e")
    _commit(root, "e/new.py", "new = 'main'\n" + "".join(_ROWS), "main moves d/ to e/, adds its new.py")
    _git(root, "checkout", "-q", "feat")
    _merge(root, "main")
    (root / "e/new.py").write_text("new = 'main'\n" + "".join(_ROWS))
    _git(root, "rm", "-q", "--cached", "--ignore-unmatch", "d/new.py")
    (root / "d/new.py").unlink(missing_ok=True)
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "--no-edit")
    assert _git(root, "show", "HEAD:e/new.py").startswith("new = 'main'")
    found = _judged(root, head)
    assert found is not None and "new.py" in found, found


def test_the_reviewed_content_under_mains_mode_is_no_code_of_the_merge(tmp_path):
    # main edits the same line and makes the file +x; the merge keeps the reviewed
    # content with main's +x — exactly git's own mode merge. No new code.
    root = _fresh(tmp_path)
    _commit(root, "run.sh", "".join(_ROWS), "base")
    _git(root, "checkout", "-q", "-b", "feat")
    head = _commit(root, "run.sh", _edit_line(0, "reviewed"), "reviewed")
    _git(root, "checkout", "-q", "main")
    (root / "run.sh").write_text(_edit_line(0, "main"))
    (root / "run.sh").chmod(0o755)
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "main edits and +x")
    _git(root, "checkout", "-q", "feat")
    _merge(root, "main")
    (root / "run.sh").write_text(_edit_line(0, "reviewed"))
    (root / "run.sh").chmod(0o755)
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "--no-edit")
    assert _git(root, "ls-tree", "HEAD", "run.sh").startswith("100755")
    found = _judged(root, head)
    assert found is None, found


# --- third refutation: the mode apart from any content, every round owns its code ---

def _write(root, rel, text, mode=None, msg=None):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.is_symlink():
        p.unlink()
    p.write_text(text)
    if mode is not None:
        p.chmod(mode)
    _git(root, "add", "-A")
    if msg:
        _git(root, "commit", "-q", "-m", msg)
        return _git(root, "rev-parse", "HEAD")


def _finish(root):
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "--no-edit")
    return _git(root, "rev-parse", "HEAD")


def _covered_b(root, head):
    b_head = _commit(root, "b.py", "b = 1\n", "work B")
    return ((head, b_head),)


def test_a_dropped_mode_counts_when_main_changed_the_content(tmp_path):
    root = _fresh(tmp_path)
    _commit(root, "run.sh", "".join(_ROWS), "base")
    _git(root, "checkout", "-q", "-b", "feat")
    head = _write(root, "run.sh", "".join(_ROWS), 0o755, "reviewed: +x")
    _git(root, "checkout", "-q", "main")
    _write(root, "run.sh", _edit_line(10, "main"), 0o644, "main edits content")
    _git(root, "checkout", "-q", "feat")
    _merge(root, "--no-commit", "main")
    assert _git(root, "ls-files", "-s", "run.sh").startswith("100755")
    (root / "run.sh").chmod(0o644)
    _finish(root)
    found = _judged(root, head, covered=_covered_b(root, head))
    assert found is not None and "run.sh" in found, found


def test_a_dropped_mode_counts_under_gits_merged_content(tmp_path):
    root = _fresh(tmp_path)
    _commit(root, "run.sh", "".join(_ROWS), "base")
    _git(root, "checkout", "-q", "-b", "feat")
    head = _write(root, "run.sh", _edit_line(0, "reviewed"), 0o755, "reviewed")
    _git(root, "checkout", "-q", "main")
    _write(root, "run.sh", _edit_line(10, "main"), 0o644, "main")
    _git(root, "checkout", "-q", "feat")
    _merge(root, "--no-commit", "main")
    (root / "run.sh").chmod(0o644)
    _finish(root)
    found = _judged(root, head, covered=_covered_b(root, head))
    assert found is not None and "run.sh" in found, found


def test_a_dropped_mode_counts_through_this_works_rename(tmp_path):
    root = _fresh(tmp_path)
    _commit(root, "a.sh", "".join(_ROWS), "base")
    _git(root, "checkout", "-q", "-b", "feat")
    _git(root, "mv", "a.sh", "b.sh")
    head = _write(root, "b.sh", "".join(_ROWS), 0o755, "reviewed: rename, +x")
    _git(root, "checkout", "-q", "main")
    _write(root, "a.sh", _edit_line(10, "main"), 0o644, "main edits")
    _git(root, "checkout", "-q", "feat")
    _merge(root, "--no-commit", "main")
    assert _git(root, "ls-files", "-s", "b.sh").startswith("100755")
    (root / "b.sh").chmod(0o644)
    _finish(root)
    found = _judged(root, head, covered=((head, _commit(root, "z.py", "z\n", "B")),))
    assert found is not None and "b.sh" in found, found


def test_a_round_without_a_base_keeps_its_code_next_to_a_delta_round(tmp_path):
    # base names a commit ABOVE the reviewed change (ancestor of head) — only
    # a later record; the earlier round had no base at all
    root = _fresh(tmp_path)
    _two_sided(root)
    h1 = _commit(root, "f.py", _edit_line(0, "reviewed"), "round 1")
    h2 = _commit(root, "b.py", "b\n", "round 2")
    _git(root, "checkout", "-q", "main")
    _commit(root, "f.py", _edit_line(0, "main"), "main")
    _git(root, "checkout", "-q", "feat")
    _merge(root, "main")
    _resolve_theirs(root, "f.py")
    r1 = {"work": "w", "tier": "2", "head": h1}  # older record, no base
    r2 = {"work": "w", "tier": "2", "head": h2, "base": h1}
    found = _mod().stale_review(root, [r1, r2], {"w"}, 2, set(), ((h1, h2),))
    assert found is not None and "f.py" in found, found


def test_a_round_rebased_away_keeps_its_code_next_to_a_delta_round(tmp_path):
    root = _fresh(tmp_path)
    _two_sided(root)
    h1 = _commit(root, "f.py", _edit_line(0, "reviewed"), "round 1")
    h2 = _commit(root, "b.py", "b\n", "round 2")
    _git(root, "checkout", "-q", "main")
    _commit(root, "f.py", _edit_line(0, "main"), "main")
    _git(root, "checkout", "-q", "feat")
    _merge(root, "main")
    _resolve_theirs(root, "f.py")
    r1 = {"work": "w", "tier": "2", "head": "1" * 40, "base": "2" * 40}
    r2 = {"work": "w", "tier": "2", "head": h2, "base": h1}
    found = _mod().stale_review(root, [r1, r2], {"w"}, 2, set(), ((h1, h2),))
    assert found is not None and "f.py" in found, found


def test_the_train_and_the_gate_agree_on_a_dropped_mode(tmp_path):
    root = _fresh(tmp_path)
    _commit(root, "run.sh", "".join(_ROWS), "base")
    _git(root, "checkout", "-q", "-b", "feat")
    head = _write(root, "run.sh", "".join(_ROWS), 0o755, "reviewed: +x")
    _git(root, "checkout", "-q", "main")
    _write(root, "run.sh", _edit_line(10, "main"), 0o644, "main edits content")
    _git(root, "checkout", "-q", "feat")
    _merge(root, "--no-commit", "main")
    (root / "run.sh").chmod(0o644)
    _finish(root)
    rec = {"work": "w", "tier": "2", "head": head}
    gate = _mod().stale_review(root, [rec], {"w"}, 2, set(), ())
    train = _train()._covers(root, [rec], {"w"}, 2, "HEAD")
    assert (gate is None) == train, (gate, train)
    assert gate is not None


def test_work_bases_are_this_works_code_rounds_only():
    passes = [{"work": "w", "tier": "2", "head": "h", "base": "b1"},
              {"work": "w", "tier": "2", "head": "h2"},
              {"work": "w-plan", "tier": "2", "head": "h", "base": "bp"},
              {"work": "v", "tier": "2", "head": "h", "base": "bv"}]
    assert _mod().work_bases(passes, {"w"}) == (("b1", "h"), ("", "h2"))


# --- fourth refutation: a headless record proves nothing, a rename on both sides ---

def test_a_dropped_mode_counts_when_both_sides_renamed_the_file(tmp_path):
    # work renames a.sh->w.sh with +x; main renames a.sh->m.sh (rename/rename conflict)
    root = _fresh(tmp_path)
    _commit(root, "a.sh", "".join(_ROWS), "base")
    _git(root, "checkout", "-q", "-b", "feat")
    _git(root, "mv", "a.sh", "w.sh")
    head = _write(root, "w.sh", "".join(_ROWS), 0o755, "reviewed: rename +x")
    _git(root, "checkout", "-q", "main")
    _git(root, "mv", "a.sh", "m.sh")
    _git(root, "commit", "-q", "-m", "main rename")
    _git(root, "checkout", "-q", "feat")
    _merge(root, "main")
    # resolver keeps work's name but main's mode
    _git(root, "rm", "-q", "--cached", "--ignore-unmatch", "m.sh", "a.sh")
    for n in ("m.sh", "a.sh"):
        (root / n).unlink(missing_ok=True)
    (root / "w.sh").write_text("".join(_ROWS))
    (root / "w.sh").chmod(0o644)
    _finish(root)
    found = _judged(root, head, covered=_covered_b(root, head))
    assert found is not None and "w.sh" in found, found


def test_a_dropped_edit_counts_when_both_sides_renamed_the_file(tmp_path):
    # companion: same rename/rename, work also edited line 0; resolver keeps
    # w.sh (work's name) with the base text — the reviewed edit is gone
    root = _fresh(tmp_path)
    _commit(root, "a.sh", "".join(_ROWS), "base")
    _git(root, "checkout", "-q", "-b", "feat")
    _git(root, "mv", "a.sh", "w.sh")
    head = _write(root, "w.sh", _edit_line(0, "w"), None, "reviewed: rename + edit")
    _git(root, "checkout", "-q", "main")
    _git(root, "mv", "a.sh", "m.sh")
    _git(root, "commit", "-q", "-m", "main rename")
    _git(root, "checkout", "-q", "feat")
    _merge(root, "main")
    _git(root, "rm", "-q", "--cached", "--ignore-unmatch", "m.sh", "a.sh")
    for n in ("m.sh", "a.sh"):
        (root / n).unlink(missing_ok=True)
    (root / "w.sh").write_text("".join(_ROWS))
    _finish(root)
    found = _judged(root, head, covered=_covered_b(root, head))
    assert found is not None and "w.sh" in found, found


# --- fifth refutation: names-only conflicts, rename chains, headless records fail closed ---

def _rr(root, work_text, work_mode, main_text, main_mode=None, main_name="m.sh"):
    """a.sh at fork; feat renames a.sh->w.sh (work_text, work_mode); main renames a.sh->main_name."""
    _commit(root, "a.sh", "".join(_ROWS), "base")
    _git(root, "checkout", "-q", "-b", "feat")
    _git(root, "mv", "a.sh", "w.sh")
    head = _write(root, "w.sh", work_text, work_mode, "reviewed: rename")
    _git(root, "checkout", "-q", "main")
    _git(root, "mv", "a.sh", main_name)
    _write(root, main_name, main_text, main_mode, "main rename")
    _git(root, "checkout", "-q", "feat")
    _merge(root, "main")
    return head


def _keep_only(root, keep, text, mode=None, drop=("m.sh", "a.sh")):
    _git(root, "rm", "-q", "--cached", "--ignore-unmatch", *drop)
    for n in drop:
        (root / n).unlink(missing_ok=True)
    (root / keep).write_text(text)
    if mode is not None:
        (root / keep).chmod(mode)
    return _finish(root)


def test_a_rename_on_both_sides_keeping_gits_merged_content_is_no_drop(tmp_path):
    root = _fresh(tmp_path)
    head = _rr(root, "".join(_ROWS), None, _edit_line(10, "main"))
    _keep_only(root, "w.sh", _edit_line(10, "main"))
    assert _judged(root, head) is None


def test_a_rename_on_both_sides_keeping_mains_copy_of_the_reviewed_edit_is_no_drop(tmp_path):
    root = _fresh(tmp_path)
    both = _edit_line(0, "w").replace("line10 = 10", "line10 = 'main'")
    head = _rr(root, _edit_line(0, "w"), None, both)
    _keep_only(root, "w.sh", both)
    assert _judged(root, head) is None


def test_a_rename_chain_across_rounds_keeps_the_oldest_name(tmp_path):
    root = _fresh(tmp_path)
    fork = _commit(root, "a.sh", "".join(_ROWS), "base")
    _git(root, "checkout", "-q", "-b", "feat")
    _git(root, "mv", "a.sh", "b.sh")
    h1 = _write(root, "b.sh", _edit_line(0, "w"), None, "round 1")
    _git(root, "mv", "b.sh", "w.sh")
    _git(root, "commit", "-q", "-m", "round 2")
    h2 = _git(root, "rev-parse", "HEAD")
    _git(root, "checkout", "-q", "main")
    _commit(root, "a.sh", _edit_line(0, "main"), "main edits line 0")
    _git(root, "checkout", "-q", "feat")
    _merge(root, "main")
    _keep_only(root, "w.sh", _edit_line(0, "main"), drop=("a.sh", "b.sh"))
    r1 = {"work": "w", "tier": "2", "head": h1, "base": fork}
    r2 = {"work": "w", "tier": "2", "head": h2, "base": h1}
    found = _mod().stale_review(root, [r1, r2], {"w"}, 2, set(), _covered_b(root, h2))
    assert found is not None and "w.sh" in found, found


def test_a_headless_record_keeps_the_first_rounds_code_next_to_a_delta_round(tmp_path):
    root = _fresh(tmp_path)
    _two_sided(root)
    h1 = _commit(root, "f.py", _edit_line(0, "reviewed"), "round 1")
    h2 = _commit(root, "b.py", "b\n", "round 2")
    _git(root, "checkout", "-q", "main")
    _commit(root, "f.py", _edit_line(0, "main"), "main")
    _git(root, "checkout", "-q", "feat")
    _merge(root, "main")
    _resolve_theirs(root, "f.py")
    r1 = {"work": "w", "tier": "2"}  # legacy: no head, no base
    r2 = {"work": "w", "tier": "2", "head": h2, "base": h1}
    found = _mod().stale_review(root, [r1, r2], {"w"}, 2, set(), ())
    assert found is not None and "f.py" in found, found


# --- sixth refutation: a delete conflict leaves no markers ---

def test_keeping_mains_edit_of_a_file_this_work_deleted_is_a_drop(tmp_path):
    root = _fresh(tmp_path)
    _two_sided(root)
    _git(root, "rm", "-q", "f.py")
    _git(root, "commit", "-q", "-m", "reviewed: delete f.py")
    head = _git(root, "rev-parse", "HEAD")
    _git(root, "checkout", "-q", "main")
    _commit(root, "f.py", _edit_line(0, "main"), "main edits")
    _git(root, "checkout", "-q", "feat")
    _merge(root, "main")
    _git(root, "add", "f.py")  # keep main's edited file
    _finish(root)
    found = _judged(root, head, covered=_covered_b(root, head))
    assert found is not None and "f.py" in found, found


def test_keeping_mains_renamed_copy_of_a_file_this_work_deleted_is_a_drop(tmp_path):
    root = _fresh(tmp_path)
    _commit(root, "a.py", "".join(_ROWS), "base")
    _git(root, "checkout", "-q", "-b", "feat")
    _git(root, "rm", "-q", "a.py")
    head = _commit(root, "k.py", "k\n", "reviewed: delete a.py")
    _git(root, "checkout", "-q", "main")
    _git(root, "mv", "a.py", "b.py")
    _commit(root, "b.py", _edit_line(0, "main"), "main renames and edits")
    _git(root, "checkout", "-q", "feat")
    _merge(root, "main")
    _git(root, "add", "-A")
    _finish(root)
    assert _git(root, "cat-file", "-e", "HEAD:b.py") == ""
    found = _mod()._dropped_by_merge(root, _git(root, "rev-parse", "HEAD"), head)
    assert found == {"b.py"}, found


# --- #182: the git work does not grow with passes × merges -----------------

def _counted(root, heads, plans=1):
    """git subprocesses spawned by `plans` stale_review calls over the same
    history, every pass stale (a full evaluation)."""
    mod = _mod()
    calls = [0]
    real = mod.subprocess.run

    def run(cmd, *a, **k):
        if cmd and cmd[0] == "git":
            calls[0] += 1
        return real(cmd, *a, **k)

    mod.subprocess.run = run
    for _ in range(plans):
        why = mod.stale_review(root, [{"work": "w", "tier": "2", "head": h} for h in heads], {"w"}, 2, set())
        assert why and "late.py" in why, why
    return calls[0]


def _merged_history(tmp_path, merges, passes):
    root = tmp_path / f"m{merges}p{passes}"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@t")
    _git(root, "config", "user.name", "t")
    _commit(root, "a.py", "a = 0\n", "base")
    _git(root, "checkout", "-q", "-b", "feat")
    heads = [_commit(root, f"w{i}.py", f"w = {i}\n", f"round {i}") for i in range(passes)]
    for i in range(merges):
        _git(root, "checkout", "-q", "main")
        _commit(root, f"m{i}.py", f"m = {i}\n", f"main {i}")
        _git(root, "checkout", "-q", "feat")
        _git(root, "merge", "-q", "--no-edit", "main")
    _commit(root, "late.py", "x = 1\n", "unreviewed")
    return root, heads


def test_doubling_merges_and_passes_does_not_quadruple_the_git_work(tmp_path):
    # downstream: 132,211 git calls and a killed gate, because every pass
    # asked the same per-merge questions again (before the fix: x4.1 here)
    small = _counted(*_merged_history(tmp_path, 4, 2))
    large = _counted(*_merged_history(tmp_path, 8, 4))
    assert large < 3 * small, (small, large)


def test_a_second_plan_over_the_same_merges_reuses_the_answers(tmp_path):
    root, heads = _merged_history(tmp_path, 4, 2)
    one, two = _counted(root, heads), _counted(root, heads, plans=2)
    assert two - one < one * 2 // 3, (one, two)  # before the fix: the second plan cost as much as the first


def test_a_failed_git_read_is_asked_again_never_remembered(repo):
    # "git could not tell" must stay "stale, fail closed" on the next ask,
    # not become a cached answer
    root, head = repo
    mod = _mod()
    real = mod._git_bytes
    answers = iter([None])
    mod._git_bytes = lambda r, *a: next(answers, real(r, *a)) if a[:1] == ("rev-list",) else real(r, *a)
    assert mod._parents(root, head) is None
    assert mod._parents(root, head) == [_git(root, "rev-parse", "main")]
