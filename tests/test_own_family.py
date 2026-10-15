"""#241 (downstream Kenni #2612): `review_evidence.own_family_from_tier` — from that tier
on, only a pass by the project's own (ranked) family clears a plan and proves its code
current; another family's pass stays valid but clears nothing alone. Read at the base."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

CLAUDE, CODEX = "claude-opus-5", "gpt-6-sol"


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t", *args],
                          capture_output=True, text=True, check=True).stdout.strip()


class Repo:
    """main (with the project's policy) → feature: plan + code (`alt`), more code (`neu`)."""

    def __init__(self, render, tmp_path: Path, *, own_from: int | None = 3, tier: int = 3,
                 claim: str = " (#77)") -> None:
        self.root = out = render(tmp_path / "r", {"project_name": "demo"})
        _git(out, "init", "-q", "-b", "main")
        if own_from is not None:
            self.policy({"review_evidence": {"own_family_from_tier": own_from}})
        _git(out, "add", "-A")
        _git(out, "commit", "-q", "-m", "base")
        self.base = _git(out, "rev-parse", "HEAD")
        _git(out, "checkout", "-q", "-b", "feature")
        (out / ".process-work/plans").mkdir(parents=True, exist_ok=True)
        (out / ".process-work/plans/2026-10-15-77-widget.md").write_text(
            f"# Plan\n\ntier: {tier}\nissue: #77\n\n## Decisions\n", encoding="utf-8")
        (out / "widget.py").write_text("X = 1\n", encoding="utf-8")
        _git(out, "add", "-A")
        _git(out, "commit", "-q", "-m", f"feat: widget{claim}")
        self.alt = _git(out, "rev-parse", "HEAD")
        (out / "widget.py").write_text("X = 2\n", encoding="utf-8")
        _git(out, "commit", "-q", "-am", f"fix: widget{claim}")
        self.neu = _git(out, "rev-parse", "HEAD")

    def policy(self, data: dict) -> None:
        (self.root / "docs/process/model-policy.local.json").write_text(json.dumps(data), encoding="utf-8")

    def passes(self, *pairs: tuple[str, str], tier: int = 3) -> None:
        folder = self.root / ".process-work/journal"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "2026-10-15.md").write_text("".join(
            f"REVIEW work=77 tier={tier} reviewer=r model={model} independence=bundle,non-implementing,cross-model "
            f"verdict=pass round=1 base={self.base} head={head}\n" for model, head in pairs), encoding="utf-8")

    def gate(self) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(self.root / "scripts/process/check_review.py"), "."],
                              cwd=self.root, capture_output=True, text=True,
                              env={**os.environ, "PROCESS_PUSH_TARGETS": "refs/heads/main"})


def test_another_family_alone_never_clears_from_the_tier(render, tmp_path):
    r = Repo(render, tmp_path)
    r.passes((CODEX, r.neu))
    out = r.gate()
    assert out.returncode == 1 and "cleared only by passes outside" in out.stdout, out.stdout


def test_an_own_family_pass_on_an_older_head_does_not_cover_the_code(render, tmp_path):
    """The other family's pass on the current head must not refresh an old own pass."""
    r = Repo(render, tmp_path)
    r.passes((CLAUDE, r.alt), (CODEX, r.neu))
    out = r.gate()
    assert out.returncode == 1, out.stdout
    r.passes((CLAUDE, r.neu), (CODEX, r.neu))
    out = r.gate()
    assert out.returncode == 0, out.stdout


def test_an_own_family_pass_alone_clears(render, tmp_path):
    r = Repo(render, tmp_path)
    r.passes((CLAUDE, r.neu))
    out = r.gate()
    assert out.returncode == 0, out.stdout


def test_an_unknown_model_is_no_own_family(render, tmp_path):
    r = Repo(render, tmp_path)
    r.passes(("gemini-x", r.neu))
    out = r.gate()
    assert out.returncode == 1 and "cleared only by passes outside" in out.stdout, out.stdout


@pytest.mark.parametrize("own_from,tier", [(None, 3), (4, 3), (3, 2)])
def test_without_the_rule_or_below_its_tier_nothing_changes(render, tmp_path, own_from, tier):
    r = Repo(render, tmp_path, own_from=own_from, tier=tier)
    r.passes((CODEX, r.neu), tier=tier)
    out = r.gate()
    assert out.returncode == 0, out.stdout


def test_a_branch_cannot_lift_the_rule_for_itself(render, tmp_path):
    r = Repo(render, tmp_path)
    r.policy({"review_evidence": {"own_family_from_tier": 4}})
    _git(r.root, "commit", "-q", "-am", "chore: lift the rule")
    r.passes((CODEX, _git(r.root, "rev-parse", "HEAD")))
    out = r.gate()
    assert out.returncode == 1 and "cleared only by passes outside" in out.stdout, out.stdout


def test_never_means_never_also_on_an_extended_scale(render, tmp_path):
    """Refute v2.74: with the default 4 a tier-4 plan fell under the rule and went red on update."""
    r = Repo(render, tmp_path, own_from=None, tier=4)
    r.passes((CODEX, r.neu))
    out = r.gate()
    assert out.returncode == 0, out.stdout


def test_a_plan_archived_in_this_push_still_needs_the_own_family(render, tmp_path):
    """Refute v2.74: `git mv` into the archive (no `(#77)` subject) skipped the rule."""
    r = Repo(render, tmp_path, claim="")
    _git(r.root, "mv", ".process-work/plans/2026-10-15-77-widget.md",
         ".process-work/plans/archive/2026-10-15-77-widget.md")
    _git(r.root, "commit", "-q", "-m", "chore: archive the plan")
    r.passes((CODEX, r.neu))
    out = r.gate()
    assert out.returncode == 1 and "cleared only by passes outside" in out.stdout, out.stdout


def test_an_ambiguous_fork_point_is_a_finding_not_a_crash(render, tmp_path):
    """Refute v2.74: the policy read raised GitReadError past the gate's own handling."""
    r = Repo(render, tmp_path)
    root = r.root
    _git(root, "checkout", "-q", "main")
    (root / "m.txt").write_text("m\n")
    _git(root, "add", "m.txt")
    _git(root, "commit", "-q", "-m", "main moves")
    _git(root, "merge", "-q", "--no-edit", "feature")  # main ← feature
    _git(root, "checkout", "-q", "feature")
    (root / "f.txt").write_text("f\n")
    _git(root, "add", "f.txt")
    _git(root, "commit", "-q", "-m", "feature moves")
    _git(root, "merge", "-q", "--no-edit", "main~1")  # feature ← old main: criss-cross
    out = r.gate()
    assert "Traceback" not in out.stderr + out.stdout, out.stderr
    assert out.returncode == 1, out.stdout


def _process_modules(root: Path):
    """train and check_review as the rendered project has them — loaded without
    bytecode and taken out of sys.modules again, so no other test sees them."""
    import importlib
    before, keep = set(sys.modules), sys.dont_write_bytecode
    sys.path.insert(0, str(root / "scripts/process"))
    sys.dont_write_bytecode = True
    try:
        for name in ("train", "check_review", "attest_evidence", "dispatch"):
            sys.modules.pop(name, None)
        return importlib.import_module("train"), importlib.import_module("check_review")
    finally:
        sys.path.remove(str(root / "scripts/process"))
        sys.dont_write_bytecode = keep
        for name in set(sys.modules) - before:
            del sys.modules[name]


def test_finish_asks_the_same_owner(render, tmp_path):
    """Code review v2.74: only the gate was tested; finish.py must refuse the same plan."""
    r = Repo(render, tmp_path)
    r.passes((CODEX, r.neu))
    out = subprocess.run([sys.executable, str(r.root / "scripts/process/finish.py"), "."],
                         cwd=r.root, capture_output=True, text=True)
    assert out.returncode != 0 and "cleared only by passes outside" in out.stdout + out.stderr, out.stdout
    r.passes((CLAUDE, r.neu), (CODEX, r.neu))
    out = subprocess.run([sys.executable, str(r.root / "scripts/process/finish.py"), "."],
                         cwd=r.root, capture_output=True, text=True)
    assert "cleared only by passes outside" not in out.stdout + out.stderr, out.stdout


def test_the_train_asks_the_same_owner(render, tmp_path):
    """Code review v2.74: the train neither boards nor archives what the gate refuses."""
    r = Repo(render, tmp_path)
    r.passes((CODEX, r.neu))
    train, review = _process_modules(r.root)
    journal = [p.read_text() for p in (r.root / ".process-work/journal").glob("*.md")]
    codex_only = review.review_passes(r.root, journal)
    assert not train._covers(r.root, codex_only, {"77"}, 3, "HEAD")
    archived, _issues = train._settle_plans(r.root, r.base, "feature", lambda _line: None)
    assert archived == [], archived
    r.passes((CLAUDE, r.neu))
    train, review = _process_modules(r.root)
    journal = [p.read_text() for p in (r.root / ".process-work/journal").glob("*.md")]
    assert train._covers(r.root, review.review_passes(r.root, journal), {"77"}, 3, "HEAD")


def test_archiving_onto_another_plans_file_still_needs_the_own_family(render, tmp_path):
    """Delta review v2.74: `git mv -f` onto a file name the base has skipped the archive arm."""
    r = Repo(render, tmp_path, claim="")
    _git(r.root, "checkout", "-q", "main")
    old = r.root / ".process-work/plans/archive/2026-01-01-old.md"
    old.parent.mkdir(parents=True, exist_ok=True)
    old.write_text("# Old\n\ntier: 1\nissue: #5\n", encoding="utf-8")
    _git(r.root, "add", "-A")
    _git(r.root, "commit", "-q", "-m", "an old archived plan")
    _git(r.root, "checkout", "-q", "feature")
    _git(r.root, "merge", "-q", "--no-edit", "main")
    _git(r.root, "mv", "-f", ".process-work/plans/2026-10-15-77-widget.md", ".process-work/plans/archive/2026-01-01-old.md")
    _git(r.root, "commit", "-q", "-m", "chore: archive")
    r.passes((CODEX, r.neu))
    out = r.gate()
    assert out.returncode == 1 and "cleared only by passes outside" in out.stdout, out.stdout


def test_renaming_inside_the_archive_reopens_nothing(render, tmp_path):
    """Delta review v2.74: an old codex-cleared archived plan, renamed, is no new merge."""
    r = Repo(render, tmp_path, claim="")
    _git(r.root, "checkout", "-q", "main")
    old = r.root / ".process-work/plans/archive/2026-01-01-55-old.md"
    old.parent.mkdir(parents=True, exist_ok=True)
    old.write_text("# Old\n\ntier: 3\nissue: #55\n", encoding="utf-8")
    _git(r.root, "add", "-A")
    _git(r.root, "commit", "-q", "-m", "an old archived plan")
    _git(r.root, "checkout", "-q", "feature")
    _git(r.root, "merge", "-q", "--no-edit", "main")
    _git(r.root, "mv", ".process-work/plans/archive/2026-01-01-55-old.md",
         ".process-work/plans/archive/2026-01-01-55-older.md")
    _git(r.root, "commit", "-q", "-m", "chore: rename")
    folder = r.root / ".process-work/journal"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "2026-10-15.md").write_text(
        f"REVIEW work=55 tier=3 reviewer=r model={CODEX} independence=bundle,non-implementing,cross-model "
        f"verdict=pass round=1\n"
        f"REVIEW work=77 tier=3 reviewer=r model={CLAUDE} independence=bundle,non-implementing,cross-model "
        f"verdict=pass round=1 base={r.base} head={_git(r.root, 'rev-parse', 'HEAD')}\n", encoding="utf-8")
    out = r.gate()
    assert "55-older.md" not in out.stdout, out.stdout
