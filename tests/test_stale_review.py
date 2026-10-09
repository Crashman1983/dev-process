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


def test_an_amend_with_new_content_is_stale(repo):
    root, head = repo
    (root / "a.py").write_text("a = 2\n")
    _git(root, "commit", "-q", "-a", "--amend", "--no-edit")
    assert "code changed after the reviewed head (a.py)" in _stale(root, head)


def _with_base(root, head):
    fork = _git(root, "merge-base", head, "main")
    return _mod().stale_review(root, [{"work": "w", "tier": "2", "head": head, "base": fork}], {"w"}, 2, set())


def test_a_rebase_or_amend_that_changes_no_content_keeps_the_review(repo):
    # #158: the review binds what was reviewed, not where it sat — for a
    # review whose base is the fork point, so it saw everything it adds
    root, head = repo
    _git(root, "commit", "-q", "--amend", "-m", "reworded")
    assert _with_base(root, head) is None
    assert "a.py" in _stale(root, head)  # without a base the review's reach is unknown
    _git(root, "checkout", "-q", "main")
    _commit(root, "m.py", "m = 1\n", "main moves on")
    _git(root, "checkout", "-q", "feat")
    _git(root, "rebase", "-q", "main")
    assert _with_base(root, head) is None
    (root / "a.py").write_text("a = 3\n")
    _git(root, "commit", "-q", "-a", "--amend", "--no-edit")
    assert "a.py" in _with_base(root, head)


def test_a_slice_review_rebased_away_vouches_for_its_slice_only(repo):
    # refutation of step B: a record whose base was not the fork point saw
    # only base..head; once the head left the history, the content rule must
    # not take the commit below the base as reviewed
    root, head = repo
    below = _git(root, "rev-parse", "HEAD")
    _commit(root, "u.py", "u = 'unreviewed'\n", "below the slice")
    sliced = _commit(root, "s.py", "s = 1\n", "the reviewed slice")
    _git(root, "checkout", "-q", "main")
    _commit(root, "m.py", "m = 1\n", "main moves on")
    _git(root, "checkout", "-q", "feat")
    _git(root, "rebase", "-q", "main")
    record = {"work": "w", "tier": "2", "head": sliced, "base": _git(root, "rev-parse", f"{sliced}~1")}
    found = _mod().stale_review(root, [record], {"w"}, 2, set())
    assert found is not None and "u.py" in found and "s.py" not in found, found
    assert below


def test_a_head_that_is_in_no_history_here_covers_nothing(repo):
    root, _head = repo
    assert "is not in this repository" in _stale(root, "b" * 40)


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
        return None if "ls-tree" in args or "diff" in args else real(r, *args)

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


def test_a_conflict_resolved_to_mains_side_is_stale(repo):
    # every resolution is unreviewed — main's side included: taking main's
    # version of a reviewed file is a revert nobody reviewed (refutation of
    # step B, which first let such drops pass)
    root, head = repo
    _git(root, "checkout", "-q", "main")
    _commit(root, "a.py", "a = 'main'\n", "main edits the same line")
    _git(root, "checkout", "-q", "feat")
    subprocess.run(["git", "merge", "--no-edit", "main"], cwd=root, capture_output=True)
    _git(root, "checkout", "--theirs", "a.py")
    _git(root, "add", "a.py")
    _git(root, "commit", "-q", "--no-edit")
    assert "a.py" in _stale(root, head)


def test_a_later_commit_setting_a_reviewed_file_back_to_mains_version_is_stale(repo):
    # refutation of step B: the reviewed route stays, its guard is reverted —
    # each file matched some reviewed state, the combination nobody reviewed
    root, head = repo
    _git(root, "checkout", "-q", "main", "--", "a.py")
    _git(root, "commit", "-q", "-m", "revert the guard")
    assert "a.py" in _stale(root, head)


@pytest.mark.parametrize("kind", ["modify-delete", "file-to-symlink"])
def test_a_conflict_without_markers_resolved_to_this_side_is_stale(repo, kind):
    # refutation of step B: git writes this branch's side where no marker fits;
    # keeping it silently undoes main's change
    root, head = repo
    _git(root, "checkout", "-q", "main")
    if kind == "modify-delete":
        _git(root, "rm", "-q", "a.py")
        _git(root, "commit", "-q", "-m", "main deletes a.py")
    else:
        (root / "a.py").unlink()
        (root / "a.py").symlink_to("elsewhere.py")
        _git(root, "add", "-A")
        _git(root, "commit", "-q", "-m", "main turns a.py into a symlink")
    _git(root, "checkout", "-q", "feat")
    subprocess.run(["git", "merge", "--no-edit", "main"], cwd=root, capture_output=True)
    _git(root, "checkout", "-q", head, "--", "a.py")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "--no-edit")
    assert "a.py" in _stale(root, head)


def test_a_conflict_resolved_to_this_side_throws_mains_change_away(repo):
    root, head = repo
    _git(root, "checkout", "-q", "main")
    _commit(root, "a.py", "a = 'main'\n", "main edits the same line")
    _git(root, "checkout", "-q", "feat")
    subprocess.run(["git", "merge", "--no-edit", "main"], cwd=root, capture_output=True)
    _git(root, "checkout", "--ours", "a.py")
    _git(root, "add", "a.py")
    _git(root, "commit", "-q", "--no-edit")
    assert "a.py" in _stale(root, head)


def test_a_merge_of_main_that_quietly_keeps_the_heads_file_is_stale(repo):
    # shadow run of step B: the tip equals the reviewed head here, but main's
    # fix is gone — the head alone is no reviewed state once main moved
    root, head = repo
    _git(root, "checkout", "-q", "main")
    _commit(root, "m.py", "m = 1  # main's fix\n", "main's fix")
    _git(root, "checkout", "-q", "feat")
    _git(root, "merge", "-q", "-s", "ours", "--no-edit", "main")
    assert "m.py" in _stale(root, head)


def test_a_failed_git_merge_is_stale_never_a_weaker_answer(repo):
    # Kenni #2439: a merge-tree timeout read a revert merge as fresh
    root, head = repo
    _git(root, "checkout", "-q", "main")
    _commit(root, "m.py", "m = 1\n", "main's fix")
    _git(root, "checkout", "-q", "feat")
    _git(root, "merge", "-q", "-s", "ours", "--no-edit", "main")
    mod = _mod()
    passes = [{"work": "w", "tier": "2", "head": head}]
    real = mod._auto_merge_uncached
    calls = []

    def flaky(*a):  # git's own merge fails once (a timeout, a failed fork), then works
        calls.append(a)
        return None if len(calls) == 1 else real(*a)

    mod._auto_merge_uncached = flaky
    assert "cannot determine" in mod.stale_review(root, passes, {"w"}, 2, set())
    assert "m.py" in mod.stale_review(root, passes, {"w"}, 2, set())


def _works_on_one_branch(root, reviewed_also=True):
    """Three works on one branch, each editing its own hunk of one shared file
    (Kenni: three works merged together, each editing the feature registry)."""
    _commit(root, "inv.md", _LINES, "base")
    _git(root, "checkout", "-q", "-b", "w1", "main")
    h1 = _commit(root, "inv.md", _LINES.replace("l0 = 0", "l0 = 'w1'"), "w1 reviewed")
    _git(root, "checkout", "-q", "-b", "w2", "main")
    h2 = _commit(root, "inv.md", _LINES.replace("l5 = 5", "l5 = 'w2'"), "w2 reviewed")
    _git(root, "checkout", "-q", "-b", "w3", "main")
    h3 = _commit(root, "inv.md", _LINES.replace("l10 = 10", "l10 = 'w3'"), "w3 reviewed")
    _git(root, "merge", "-q", "--no-edit", "w1", "w2")
    return h1, h2, h3


def test_several_reviewed_works_merged_cleanly_on_one_branch_are_a_reviewed_state(tmp_path):
    root = tmp_path / "r"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@t")
    _git(root, "config", "user.name", "t")
    h1, h2, h3 = _works_on_one_branch(root)
    passes = [{"work": f"w{i}", "tier": "2", "head": h, "base": _git(root, "rev-parse", "main")}
              for i, h in enumerate((h1, h2, h3), 1)]
    others = tuple((r["base"], r["head"]) for r in passes)
    mod = _mod()
    for r in passes:
        assert mod.stale_review(root, passes, {r["work"]}, 2, set(), others) is None, r["work"]
    # without the other works' reviews, their hunks are code nobody reviewed
    assert "inv.md" in mod.stale_review(root, passes, {"w3"}, 2, set(), ())


def test_another_review_counts_only_where_the_tip_contains_its_head(repo):
    root, head = repo
    _git(root, "checkout", "-q", "-b", "elsewhere", "main")
    other = _commit(root, "b.py", "b = 1\n", "reviewed elsewhere, never merged here")
    _git(root, "checkout", "-q", "feat")
    _commit(root, "b.py", "b = 1\n", "the same content, committed here unreviewed")
    found = _mod().stale_review(root, [{"work": "w", "tier": "2", "head": head}], {"w"}, 2, set(),
                                ((_git(root, "rev-parse", "main"), other),))
    assert "b.py" in found




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



def test_two_passengers_on_hunks_of_one_file_are_both_reviewed(shared):
    # the train boards two reviewed works on one file (no overlap rule since
    # v2.57.1); git merges their hunks cleanly — neither reads as late code
    root, head = shared
    _git(root, "checkout", "-q", "-b", "other", "main")
    other_head = _commit(root, "inv.md", (root / "inv.md").read_text().replace("l6 = 6", "l6 = 'other'"),
                         "other passenger, another hunk of the same file")
    _git(root, "checkout", "-q", "-b", "train/b", "main")
    _git(root, "merge", "-q", "--no-ff", "--no-edit", "feat")
    _git(root, "merge", "-q", "--no-ff", "--no-edit", "other")
    text = (root / "inv.md").read_text()
    assert "l0 = 'feat'" in text and "l6 = 'other'" in text
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
    ("head in no history here", {"in_history": False}, "stale", "not in this repository"),
    ("clean main merge", {}, "fresh", ""),
    ("clean merge of hunks from both sides", {}, "fresh", ""),
    ("conflict resolution", {"late": frozenset({"a.py"})}, "stale", "code changed after"),
    ("train --no-ff staging", {}, "fresh", ""),
    ("fellow passenger's evil merge", {"fellow": (("b" * 40, frozenset({"e.py"})),)}, "stale", "another passenger"),
    ("later code commit", {"late": frozenset({"b.py"})}, "stale", "code changed after"),
    ("git error", {"git_error": True}, "stale", "git did not answer"),
    ("shallow clone", {"shallow_missing": True}, "stale", "shallow clone"),
    # precedence: the first fact that decides names the reason
    ("git error beats everything", {"git_error": True, "in_history": False, "late": frozenset({"x"})},
     "stale", "git did not answer"),
    ("not in this repository beats late", {"in_history": False, "late": frozenset({"x"})}, "stale",
     "not in this repository"),
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
    for resolution in (b"x=1\nevil()\n", b"x=1\n"):  # an evil resolution, and one to this side
        root = tmp_path / ("evil" if b"evil" in resolution else "ours")
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




def test_unreviewed_paths_reads_content_not_history(repo):
    root, head = repo
    _git(root, "commit", "-q", "--amend", "-m", "amended, nothing else")
    fork = _git(root, "merge-base", head, "main")
    assert _mod()._unreviewed_paths(root, head, "HEAD", (), fork) == set()
    assert _mod()._unreviewed_paths(root, "b" * 40, "HEAD") is None  # a head in no history here


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















def test_the_reviewed_content_under_mains_mode_still_throws_mains_line_away(tmp_path):
    # main edits the same line and makes the file +x; the merge keeps the
    # reviewed content with main's +x — main's edit of that line is gone
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
    assert found is not None and "run.sh" in found, found


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


















# --- fourth refutation: a headless record proves nothing, a rename on both sides ---





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


def test_a_rename_on_both_sides_keeping_only_this_name_throws_mains_rename_away(tmp_path):
    root = _fresh(tmp_path)
    head = _rr(root, "".join(_ROWS), None, _edit_line(10, "main"))
    _keep_only(root, "w.sh", _edit_line(10, "main"))
    assert "m.sh" in _judged(root, head)


def test_a_rename_on_both_sides_keeping_both_edits_under_this_name_is_still_a_resolution(tmp_path):
    root = _fresh(tmp_path)
    both = _edit_line(0, "w").replace("line10 = 10", "line10 = 'main'")
    head = _rr(root, _edit_line(0, "w"), None, both)
    _keep_only(root, "w.sh", both)
    assert "m.sh" in _judged(root, head)






# --- sixth refutation: a delete conflict leaves no markers ---





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








def test_a_later_round_that_reviewed_the_merge_of_main_covers_its_resolution(repo):
    # Kenni shadow run: round 1's head conflicts with main; round 2 reviewed the
    # merge of main and its resolution — the merge is reviewed content
    root, head = repo
    _git(root, "checkout", "-q", "main")
    _commit(root, "a.py", "a = 'main'\n", "main edits the same line")
    main = _git(root, "rev-parse", "HEAD")
    _git(root, "checkout", "-q", "feat")
    subprocess.run(["git", "merge", "--no-edit", "main"], cwd=root, capture_output=True)
    (root / "a.py").write_text("a = 1  # and 'main'\n")
    _git(root, "add", "a.py")
    _git(root, "commit", "-q", "--no-edit")
    second = _git(root, "rev-parse", "HEAD")
    passes = [{"work": "w", "tier": "2", "head": head}, {"work": "w", "tier": "2", "head": second, "base": main}]
    assert _mod().stale_review(root, passes[:1], {"w"}, 2, set()) is not None  # round 1 alone: the resolution is unreviewed
    assert _mod().stale_review(root, passes[:1], {"w"}, 2, set(), ((main, second),)) is None


def test_every_train_carrier_of_the_work_is_judged(repo):
    # refutation of step B: two staging merges carry the reviewed head — the
    # older one with an unreviewed commit on top; judging only the newest hid it
    root, head = repo
    _git(root, "checkout", "-q", "-b", "stacked", head)
    other = _commit(root, "c.py", "c = 1\n", "stacked work, reviewed on its own")
    _git(root, "checkout", "-q", "feat")
    _commit(root, "b.py", "b = 'unreviewed'\n", "after the review")
    _git(root, "checkout", "-q", "-b", "train/a", "main")
    _git(root, "merge", "-q", "--no-ff", "--no-edit", "feat")
    _git(root, "merge", "-q", "--no-ff", "--no-edit", "stacked")
    fork = _git(root, "merge-base", head, "main")
    found = _mod().stale_review(root, [{"work": "w", "tier": "2", "head": head}], {"w"}, 2, set(),
                                ((fork, other),))
    assert found is not None and "b.py" in found, found


def test_a_review_based_on_reviewed_content_counts_whole(tmp_path):
    # Kenni shadow run: work B started from work A's attest commit, so its
    # recorded base lies above main; that base is A's reviewed content plus
    # bookkeeping, so B counts whole and A, B and C merge into a reviewed state
    root = tmp_path / "r"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@t")
    _git(root, "config", "user.name", "t")
    fork = _commit(root, "inv.md", _LINES, "base")
    _git(root, "checkout", "-q", "-b", "a")
    h_a = _commit(root, "inv.md", _LINES.replace("l0 = 0", "l0 = 'a'"), "A reviewed")
    attest_a = _commit(root, ".process-work/journal/a.md", "REVIEW …\n", "attest A")
    h_b = _commit(root, "inv.md", _LINES.replace("l0 = 0", "l0 = 'a'").replace("l5 = 5", "l5 = 'b'"), "B reviewed")
    _git(root, "checkout", "-q", "-b", "c", "main")
    h_c = _commit(root, "inv.md", _LINES.replace("l10 = 10", "l10 = 'c'"), "C reviewed")
    _git(root, "merge", "-q", "--no-edit", "a")
    reviewed = ((fork, h_a), (attest_a, h_b), (fork, h_c))
    mod = _mod()
    assert mod.stale_review(root, [{"work": "c", "tier": "2", "head": h_c, "base": fork}], {"c"}, 2, set(),
                            reviewed) is None
    # a base with unreviewed code below it stays a slice
    _git(root, "checkout", "-q", "-b", "d", attest_a)
    _commit(root, "u.py", "u = 'unreviewed'\n", "below the slice")
    below = _git(root, "rev-parse", "HEAD")
    h_d = _commit(root, "d.py", "d = 1\n", "D reviewed from there")
    _git(root, "checkout", "-q", "c")
    _git(root, "merge", "-q", "--no-edit", "d")
    found = mod.stale_review(root, [{"work": "c", "tier": "2", "head": h_c, "base": fork}], {"c"}, 2, set(),
                             reviewed + ((below, h_d),))
    assert found is not None and "u.py" in found and "d.py" not in found, found


# --- #199: a Spec Kit plan's records ride the attestation commit ---

_SPEC = "specs/7-widget/plan.md"
_PLAN_TEXT = "# Widget\n\ntier: 2\n\n## Decisions\n\nDECISION NEEDED 2026-10-01 seb: which store?\n\n## Tasks\n\n- build it\n"


@pytest.fixture
def spec_repo(repo):
    root, _head = repo
    head = _commit(root, _SPEC, _PLAN_TEXT, "plan and work")
    return root, head


def _late(root, head):
    return _mod()._unreviewed_paths(root, head, "HEAD")


@pytest.mark.parametrize("added", [
    "REFUTE work=7-widget round=1: 14 scenarios, 2 findings — fixed\n",
    "- DECISION 2026-10-02: Ein Finding bleibt, weil es nur lokal wirkt.\n",
    "ROOT-CAUSE work=7-widget round=2: der Cache las den alten Stand\n\n"
    "REVIEW work=7-widget tier=2 reviewer=fresh model=cross independence=bundle verdict=pass round=1\n",
])
def test_record_lines_appended_to_a_spec_plan_keep_its_review(spec_repo, added):
    root, head = spec_repo
    _commit(root, _SPEC, _PLAN_TEXT + "\n" + added, "attest")
    assert _late(root, head) == set()


def test_an_answered_decision_needed_keeps_the_review(spec_repo):
    root, head = spec_repo
    answered = _PLAN_TEXT.replace("DECISION NEEDED 2026-10-01 seb: which store?",
                                  "DECISION 2026-10-02: SQLite, weil schon da.")
    _commit(root, _SPEC, answered, "attest")
    assert _late(root, head) == set()


@pytest.mark.parametrize("change", [
    lambda t: t + "\n- one more task\n",                                     # prose added
    lambda t: t.replace("- build it", "- build it twice"),                   # a line edited
    lambda t: t.replace("- build it\n", ""),                                 # a line deleted
    lambda t: t.replace("DECISION NEEDED 2026-10-01 seb: which store?\n", ""),  # a question dropped
    lambda t: t + "\n```\nREFUTE work=7-widget round=1: fenced\n```\n",      # a fenced record
    lambda t: t + "\n    REFUTE work=7-widget round=1: indented\n",          # an indented one
])
def test_plan_content_after_the_review_stays_late(spec_repo, change):
    root, head = spec_repo
    _commit(root, _SPEC, change(_PLAN_TEXT), "late plan change")
    assert _late(root, head) == {_SPEC}


def test_a_spec_plan_archived_with_records_keeps_its_review(spec_repo):
    root, head = spec_repo
    (root / ".process-work/plans/archive").mkdir(parents=True)
    _git(root, "mv", _SPEC, ".process-work/plans/archive/7-widget.md")
    _commit(root, ".process-work/plans/archive/7-widget.md",
            _PLAN_TEXT + "\nREFUTE work=7-widget round=1: 3 scenarios, no findings\n", "attest --archive")
    assert _late(root, head) == set()


def test_a_spec_plan_archived_with_new_content_stays_late(spec_repo):
    root, head = spec_repo
    (root / ".process-work/plans/archive").mkdir(parents=True)
    _git(root, "mv", _SPEC, ".process-work/plans/archive/7-widget.md")
    _commit(root, ".process-work/plans/archive/7-widget.md", _PLAN_TEXT + "\n- a new task\n", "archive")
    assert _late(root, head) == {_SPEC}


def test_a_spec_plan_deleted_without_archive_stays_late(spec_repo):
    root, head = spec_repo
    _git(root, "rm", "-q", _SPEC)
    _git(root, "commit", "-q", "-m", "drop the plan")
    assert _late(root, head) == {_SPEC}
