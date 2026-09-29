"""Every process tool reads git path names NUL-separated (`-z`) through one owner.

Without `-z` git prints a name with a non-ASCII byte (or a newline, a tab, a
quote) in quotes with octal escapes. The quoted name matches no file: the train
read an archived Tier 2 plan under it, `git show` returned nothing, the tier
read 0 and the branch boarded without a review (downstream refutation). The
same pattern sat in the tower, the review bundle, dispatch, the digest and the
fix-streak note. And a name list git could not produce is no empty list: read
as "nothing in flight", a failing `git diff` made every plan somebody else's.
"""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

NAMES = ["größe", "new\nline"]


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True).stdout


def _repo(out: Path) -> None:
    _git(out, "init", "-q", "-b", "main")
    _git(out, "config", "user.email", "t@t")
    _git(out, "config", "user.name", "t")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "base")


def _write(out: Path, rel: str, text: str) -> None:
    p = out / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _commit(out: Path, msg: str) -> None:
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", msg)


def _load(out: Path, script: str):
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(out / "scripts/process"))
    spec = importlib.util.spec_from_file_location(f"{script}_names_under_test",
                                                  out / f"scripts/process/{script}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _train_plan(out: Path) -> dict:
    r = subprocess.run([sys.executable, str(out / "scripts/process/train.py"), "plan", "--json"],
                       cwd=out, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return {c["branch"]: c for c in json.loads(r.stdout)["candidates"]}


# --- train: an archived Tier 2 plan under a quoted name boards nothing unreviewed ---


@pytest.mark.parametrize("name", NAMES, ids=["umlaut", "newline"])
def test_train_does_not_board_a_tier2_plan_whose_name_git_quotes(render, tmp_path, name):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _git(out, "checkout", "-q", "-b", "1-thing")
    _write(out, "src/a.py", "a\n")
    _write(out, f".process-work/plans/archive/2026-09-20-{name}.md",
           "# Plan\n\ntier: 2\nissue: #1\n\n## Decisions\n")
    _commit(out, "feat: thing (#1)")
    _git(out, "checkout", "-q", "main")

    c = _train_plan(out)["1-thing"]

    assert not c["eligible"], c
    assert [p["tier"] for p in c["plans"]] == [2], c


def test_train_boards_a_reviewed_tier2_plan_with_a_non_ascii_name(render, tmp_path):
    """Twin: the real name is read, and its pass clears it."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _git(out, "checkout", "-q", "-b", "1-thing")
    _write(out, "src/a.py", "a\n")
    _write(out, ".process-work/plans/archive/2026-09-20-größe.md",
           "# Plan\n\ntier: 2\nissue: #1\n\n## Decisions\n")
    _write(out, ".process-work/journal/2026-09-20-größe.md",
           "REVIEW work=größe tier=2 reviewer=fresh model=cross "
           "independence=bundle,non-implementing verdict=pass round=1\n")
    _commit(out, "feat: thing (#1)")
    _git(out, "checkout", "-q", "main")

    c = _train_plan(out)["1-thing"]

    assert c["eligible"], c


def test_train_boards_nothing_when_git_cannot_list_a_branchs_files(render, tmp_path):
    """A name list git could not produce is no empty list."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _git(out, "checkout", "-q", "-b", "1-thing")
    _write(out, "src/a.py", "a\n")
    _write(out, ".process-work/plans/archive/2026-09-20-thing.md", "# Plan\n\ntier: 1\nissue: #1\n")
    _commit(out, "feat: thing (#1)")
    _git(out, "checkout", "-q", "main")
    train = _load(out, "train")
    real = train._paths

    def failing(root, *args):
        return None if args[:1] == ("diff",) else real(root, *args)

    train._paths = failing
    by = {c["branch"]: c for c in train.candidates(out, "main", "main")}

    assert not by["1-thing"]["eligible"], by
    assert any("git could not read" in r for r in by["1-thing"]["reasons"]), by


# --- tower, bundle, dispatch, digest, fix-streak: the real name, not the quoted one ---


@pytest.mark.parametrize("name", NAMES, ids=["umlaut", "newline"])
def test_tower_lists_an_active_plan_under_its_real_name(render, tmp_path, name):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    rel = f".process-work/plans/2026-09-20-{name}.md"
    _write(out, rel, "# Plan\n\ntier: 1\n")
    _commit(out, "docs: plan")

    assert rel in _load(out, "tower")._plan_paths_in_ref(out, "HEAD")


@pytest.mark.parametrize("name", NAMES, ids=["umlaut", "newline"])
def test_bundle_names_a_changed_image_under_its_real_name(render, tmp_path, name):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _git(out, "checkout", "-q", "-b", "1-thing")
    (out / f"shot-{name}.png").write_bytes(b"\x89PNG")
    _commit(out, "feat: shot")

    text = _load(out, "make_review_bundle")._ui_evidence(out, "main", [])

    assert f"- A shot-{name}.png" in text, text


@pytest.mark.parametrize("name", NAMES, ids=["umlaut", "newline"])
def test_dispatch_reads_a_branchs_own_plan_under_its_real_name(render, tmp_path, name):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _git(out, "checkout", "-q", "-b", "1-thing")
    rel = f".process-work/plans/2026-09-20-{name}.md"
    _write(out, rel, "# Plan\n\ntier: 2\nissue: #1\n")
    _commit(out, "docs: plan")
    _git(out, "update-ref", "refs/remotes/origin/1-thing", "HEAD")
    _git(out, "update-ref", "refs/remotes/origin/main", "main")

    _tip, plans = _load(out, "dispatch")._own_plans_on_origin(out, "1-thing", local=True)

    assert plans == [rel], plans


@pytest.mark.parametrize("name", NAMES, ids=["umlaut", "newline"])
def test_dispatch_commit_touches_names_the_real_file(render, tmp_path, name):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _write(out, f"src/{name}.py", "x\n")
    _commit(out, "feat: file")

    assert _load(out, "dispatch")._commit_touches(out, "HEAD") == [f"src/{name}.py"]


def test_digest_names_a_screenshot_under_its_real_path(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    shots = out / ".process-work/reviews/thing"
    shots.mkdir(parents=True)
    (shots / "größe.png").write_bytes(b"\x89PNG")
    _commit(out, "feat: shot")

    lines = _load(out, "human_digest").section_ui_evidence(out, 30)

    assert "- A .process-work/reviews/thing/größe.png" in lines, lines


def test_fix_streak_counts_a_non_ascii_file_under_its_real_name(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _git(out, "checkout", "-q", "-b", "7-thing")
    for subject in ("fix: a", "fix: b", "fix: c"):
        p = out / "größe.py"
        p.write_text(p.read_text() + "x\n" if p.exists() else "x\n")
        _commit(out, subject)

    r = subprocess.run([sys.executable, str(out / "scripts/process/check_fix_streak.py"), "."],
                       cwd=out, capture_output=True, text=True)

    assert r.returncode == 0, r.stderr
    assert "3 fix commits on größe.py" in r.stdout, r.stdout


# --- AC-5: a failing `git diff` is "cannot tell", never "nothing in flight" ---


def _feature_with_plan(render, tmp_path, tier: int) -> Path:
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _git(out, "checkout", "-q", "-b", "1-thing")
    _write(out, ".process-work/plans/2026-09-20-thing.md", f"# Plan\n\ntier: {tier}\nissue: none\n")
    _commit(out, "feat: plan")
    return out


def test_paths_in_flight_is_none_when_git_cannot_list_the_range(render, tmp_path):
    out = _feature_with_plan(render, tmp_path, 2)
    review = _load(out, "check_review")
    real = review._git_bytes
    review._git_bytes = lambda root, *a: None if "diff" in a else real(root, *a)

    assert review.paths_in_flight(out) is None
    assert review.merge_base(out) is not None  # the base resolves: only the diff failed


def test_paths_in_flight_without_a_base_stays_empty(render, tmp_path):
    """Twin: no base is the documented degrade, not a failure."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _git(out, "init", "-q", "-b", "feature")

    assert _load(out, "check_review").paths_in_flight(out) == set()


def test_finish_blocks_when_git_cannot_list_the_paths_in_flight(render, tmp_path):
    out = _feature_with_plan(render, tmp_path, 1)
    finish = _load(out, "finish")
    finish.paths_in_flight = lambda root: None

    blockers, _tail = finish.check(out)

    assert any("could not list the paths this push carries" in b for b in blockers), blockers


def test_review_gate_treats_every_active_plan_as_in_flight_when_git_fails(render, tmp_path, monkeypatch):
    """A Tier 3 plan the push may carry is no longer "somebody else's" because git failed."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _write(out, ".process-work/plans/2026-09-20-thing.md", "# Plan\n\ntier: 3\nissue: none\n")
    _commit(out, "docs: plan on main")
    _git(out, "checkout", "-q", "-b", "1-thing")
    _write(out, "src/a.py", "a\n")
    _commit(out, "feat: code")
    monkeypatch.chdir(out)
    monkeypatch.setenv("PROCESS_PUSH_TARGETS", "refs/heads/main")
    review = _load(out, "check_review")
    assert not any("2026-09-20-thing.md" in h and "no clearing REVIEW" in h
                   for h in review.check(out)[0])  # twin: not in flight, not this push's
    review.paths_in_flight = lambda root: None

    hard, soft = review.check(out)

    assert any("2026-09-20-thing.md" in h and "no clearing REVIEW" in h for h in hard), hard
    assert any("could not list the paths this push carries" in s for s in soft), soft


# --- template update and the KPI cockpit read names with -z too ---


def _update_repo(render, tmp_path) -> Path:
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    return out


def test_template_update_restores_an_owned_file_whose_name_git_quotes(render, tmp_path):
    out = _update_repo(render, tmp_path)
    _write(out, "docs/größe.md", "own\n")
    _write(out, ".process-owned", "docs/größe.md\n")
    _commit(out, "docs: owned")
    (out / "docs/größe.md").write_text("overwritten\n", encoding="utf-8")
    tu = _load(out, "template_update")

    assert tu.restore_owned(out, tu.owned_patterns(out)) == ["docs/größe.md"]
    assert (out / "docs/größe.md").read_text(encoding="utf-8") == "own\n"


def test_template_update_finds_conflict_markers_in_a_file_whose_name_git_quotes(render, tmp_path):
    out = _update_repo(render, tmp_path)
    _write(out, "docs/größe.md", "own\n")
    _commit(out, "docs: file")
    (out / "docs/größe.md").write_text("<<<<<<< ours\na\n=======\nb\n>>>>>>> theirs\n", encoding="utf-8")

    assert _load(out, "template_update").leftover_conflicts(out, []) == ["docs/größe.md"]


def test_kpi_cockpit_reads_a_non_ascii_file_under_its_real_name(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {"telemetry": True}})
    _repo(out)
    _write(out, "src/größe.py", "x\n")
    _commit(out, "fix: size")

    commits = _load(out, "process_kpis")._git_commits("main")

    assert commits[0]["subject"] == "fix: size"
    assert commits[0]["files"] == {"src/größe.py"}, commits[0]
