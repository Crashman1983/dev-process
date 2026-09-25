"""stale_review against the refutation of the ancestor fix (downstream #2144 r3/r4).

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
    _git(root, "checkout", "-q", "-b", "train", "main")
    _git(root, "merge", "-q", "--no-ff", "--no-edit", "feat")
    _git(root, "merge", "-q", "--no-ff", "--no-edit", "other")
    assert _stale(root, head) is None
    _git(root, "checkout", "-q", "feat")
    _commit(root, "a.py", "a = 3\n", "fix after the review")
    _git(root, "checkout", "-q", "-B", "train2", "main")
    _git(root, "merge", "-q", "--no-ff", "--no-edit", "feat")
    _git(root, "merge", "-q", "--no-ff", "--no-edit", "other")
    assert "a.py" in _stale(root, head) and "o.py" not in _stale(root, head)


def test_an_evil_train_merge_is_stale(repo):
    root, head = repo
    _git(root, "checkout", "-q", "-b", "train", "main")
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
    _git(root, "checkout", "-q", "-b", "train", "main")
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
    _git(root, "checkout", "-q", "-b", "train", "main")
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
