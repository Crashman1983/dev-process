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


def test_the_bare_family_name_review_records_is_the_own_family(render, tmp_path):
    """`/review` records `--model <family>`: `claude` is the family of the ranked `claude-*`
    classes and clears; a bare name of another family, or a non-name, does not."""
    r = Repo(render, tmp_path)
    r.passes(("claude", r.neu))
    out = r.gate()
    assert out.returncode == 0, out.stdout
    for other in ("codex", "gpt", "opus", "claude-op"):
        r.passes((other, r.neu))
        out = r.gate()
        assert out.returncode == 1 and "cleared only by passes outside" in out.stdout, (other, out.stdout)


def test_a_bare_family_name_stays_classless_for_a_plan_review(render, tmp_path):
    """Counting as the own family ranks nothing: a plan review by `claude` is still refused
    as an unknown class (attest), so the bare name cannot pass a smaller model off."""
    out = render(tmp_path / "r", {"project_name": "demo"})
    probe = ("import sys; sys.dont_write_bytecode = True; sys.path.insert(0, 'scripts/process'); "
             "from attest_evidence import model_class; "
             "print(model_class('claude', {'claude-haiku': 0, 'claude-opus': 2}, ['gpt-']))")
    got = subprocess.run([sys.executable, "-c", probe], cwd=out, capture_output=True, text=True)
    assert got.stdout.strip() == "None", got.stdout + got.stderr


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


def test_an_archived_plan_rewritten_under_a_rename_needs_the_own_family(render, tmp_path):
    """Delta round 3: an old archived plan renamed onto new work (git: R073) skipped the rule."""
    r = Repo(render, tmp_path, claim="")
    _git(r.root, "checkout", "-q", "main")
    old = r.root / ".process-work/plans/archive/2026-01-01-55-old.md"
    old.parent.mkdir(parents=True, exist_ok=True)
    old.write_text("# Plan\n\ntier: 3\nissue: #55\n\n## Decisions\n\nOld text that stays.\n", encoding="utf-8")
    _git(r.root, "add", "-A")
    _git(r.root, "commit", "-q", "-m", "an old archived plan")
    _git(r.root, "checkout", "-q", "feature")
    _git(r.root, "merge", "-q", "--no-edit", "main")
    _git(r.root, "rm", "-q", ".process-work/plans/2026-10-15-77-widget.md")
    _git(r.root, "mv", ".process-work/plans/archive/2026-01-01-55-old.md",
         ".process-work/plans/archive/2026-10-15-77-widget.md")
    moved = r.root / ".process-work/plans/archive/2026-10-15-77-widget.md"
    moved.write_text(moved.read_text().replace("#55", "#77"), encoding="utf-8")
    _git(r.root, "commit", "-qam", "chore: archive")
    r.passes((CODEX, r.neu))
    out = r.gate()
    assert out.returncode == 1 and "cleared only by passes outside" in out.stdout, out.stdout


def test_a_typo_fix_in_an_old_archived_plan_reopens_nothing(render, tmp_path):
    """Delta round 4: a link or wording sweep through the archive must not need a new review."""
    r = Repo(render, tmp_path, claim="")
    _git(r.root, "checkout", "-q", "main")
    old = r.root / ".process-work/plans/archive/2026-01-01-55-old.md"
    old.parent.mkdir(parents=True, exist_ok=True)
    old.write_text("# Plan\n\ntier: 3\nissue: #55\n\nteh text\n", encoding="utf-8")
    _git(r.root, "add", "-A")
    _git(r.root, "commit", "-q", "-m", "an old archived plan")
    _git(r.root, "checkout", "-q", "feature")
    _git(r.root, "merge", "-q", "--no-edit", "main")
    old.write_text(old.read_text().replace("teh", "the"), encoding="utf-8")
    _git(r.root, "commit", "-qam", "docs: typo")
    folder = r.root / ".process-work/journal"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "2026-10-15.md").write_text(
        f"REVIEW work=55 tier=3 reviewer=r model={CODEX} independence=bundle,non-implementing,cross-model "
        f"verdict=pass round=1\n"
        f"REVIEW work=77 tier=3 reviewer=r model={CLAUDE} independence=bundle,non-implementing,cross-model "
        f"verdict=pass round=1 base={r.base} head={_git(r.root, 'rev-parse', 'HEAD')}\n", encoding="utf-8")
    out = r.gate()
    assert "55-old.md" not in out.stdout, out.stdout


def test_a_rename_that_reorders_lines_is_no_pure_rename(render, tmp_path):
    """Delta round 4: git reports R100 for reordered lines; only an equal blob keeps the base path."""
    r = Repo(render, tmp_path, claim="")
    _git(r.root, "checkout", "-q", "main")
    old = r.root / ".process-work/plans/archive/2026-01-01-55-old.md"
    old.parent.mkdir(parents=True, exist_ok=True)
    old.write_text("# Plan\n\ntier: 3\nissue: #55\n\n```\nissue: #77\n```\n", encoding="utf-8")
    _git(r.root, "add", "-A")
    _git(r.root, "commit", "-q", "-m", "an old archived plan")
    _git(r.root, "checkout", "-q", "feature")
    _git(r.root, "merge", "-q", "--no-edit", "main")
    _git(r.root, "rm", "-q", ".process-work/plans/2026-10-15-77-widget.md")
    _git(r.root, "mv", ".process-work/plans/archive/2026-01-01-55-old.md",
         ".process-work/plans/archive/2026-10-15-77-widget.md")
    moved = r.root / ".process-work/plans/archive/2026-10-15-77-widget.md"
    moved.write_text("# Plan\n\ntier: 3\nissue: #77\n\n```\nissue: #55\n```\n", encoding="utf-8")
    _git(r.root, "commit", "-qam", "chore: archive")
    r.passes((CODEX, r.neu))
    out = r.gate()
    assert out.returncode == 1 and "cleared only by passes outside" in out.stdout, out.stdout


def _spec_plan_repo(render, tmp_path: Path) -> Repo:
    """A Tier 3 Spec Kit plan on the feature branch, no commit claiming its issue (#266)."""
    r = Repo(render, tmp_path, claim="")
    (r.root / ".process-work/plans/2026-10-15-77-widget.md").unlink()
    spec = r.root / "specs/77-widget"
    spec.mkdir(parents=True)
    (spec / "plan.md").write_text("# Plan\n\ntier: 3\nissue: #77\n\n## Decisions\n", encoding="utf-8")
    _git(r.root, "add", "-A")
    _git(r.root, "commit", "-q", "-m", "spec: widget plan")
    r.neu = _git(r.root, "rev-parse", "HEAD")
    return r


def test_an_in_flight_spec_plan_cleared_by_another_family_alone_fails(render, tmp_path):
    """#266: only the issue-anchored arm asked for the own family; a spec plan with no
    claiming commit passed on a Codex pass alone."""
    r = _spec_plan_repo(render, tmp_path)
    r.passes((CODEX, r.neu))
    out = r.gate()
    assert out.returncode == 1 and "specs/77-widget/plan.md" in out.stdout \
        and "cleared only by passes outside" in out.stdout, out.stdout
    r.passes((CLAUDE, r.neu))
    assert r.gate().returncode == 0, r.gate().stdout


def test_an_in_flight_spec_plan_without_any_review_fails(render, tmp_path):
    r = _spec_plan_repo(render, tmp_path)
    out = r.gate()
    assert out.returncode == 1 and "specs/77-widget/plan.md" in out.stdout, out.stdout


def test_finish_asks_the_same_owner_for_a_spec_plan(render, tmp_path):
    r = _spec_plan_repo(render, tmp_path)
    r.passes((CODEX, r.neu))
    _git(r.root, "add", "-A")
    _git(r.root, "commit", "-q", "-m", "journal")
    out = subprocess.run([sys.executable, str(r.root / "scripts/process/finish.py")], cwd=r.root,
                         capture_output=True, text=True)
    assert out.returncode == 1 and "cleared only by passes outside" in out.stdout, out.stdout


def test_a_waiver_without_the_owners_word_fails_at_the_merge(render, tmp_path):
    """#282: `review-waived:` took any text; the owner's decision now stands behind it."""
    r = Repo(render, tmp_path, tier=2)
    plan = r.root / ".process-work/plans/2026-10-15-77-widget.md"
    plan.write_text(plan.read_text() + "review-waived: trivial rename, tracked #77\n", encoding="utf-8")
    _git(r.root, "commit", "-qam", "waive")
    out = r.gate()
    assert out.returncode == 1 and "without the owner's word" in out.stdout, out.stdout
    plan.write_text(plan.read_text() + "- DECISION 2026-10-21 owner: rename only, no review\n",
                    encoding="utf-8")
    _git(r.root, "commit", "-qam", "owner decides")
    out = r.gate()
    assert "without the owner's word" not in out.stdout, out.stdout


def test_an_unreadable_policy_keeps_the_waivers_owner_duty(render, tmp_path):
    """Refute of #282: the gate read an unreadable policy as `{}` — no table, no duty."""
    r = Repo(render, tmp_path, own_from=None, tier=2)
    _git(r.root, "checkout", "-q", "main")
    (r.root / "docs/process/model-policy.local.json").write_text("{not json", encoding="utf-8")
    _git(r.root, "add", "-A")
    _git(r.root, "commit", "-q", "-m", "broken policy")
    _git(r.root, "checkout", "-q", "feature")
    _git(r.root, "merge", "-q", "--no-edit", "main")
    plan = r.root / ".process-work/plans/2026-10-15-77-widget.md"
    plan.write_text(plan.read_text() + "review-waived: trivial rename, tracked #77\n", encoding="utf-8")
    _git(r.root, "commit", "-qam", "waive")
    out = r.gate()
    assert out.returncode == 1 and "without the owner's word" in out.stdout, out.stdout


def test_finish_names_a_done_spec_plan_once(render, tmp_path):
    """Refute of #266 (M6): the in-flight arm and the ticked-tasks arm both judge a spec
    plan; finish names it once."""
    r = _spec_plan_repo(render, tmp_path)
    (r.root / "specs/77-widget/tasks.md").write_text("- [x] T1 widget\n", encoding="utf-8")
    _git(r.root, "add", "-A")
    _git(r.root, "commit", "-q", "-m", "tasks done")
    out = subprocess.run([sys.executable, str(r.root / "scripts/process/finish.py")], cwd=r.root,
                         capture_output=True, text=True)
    named = [ln for ln in out.stdout.splitlines() if "specs/77-widget" in ln]
    assert out.returncode == 1 and len(named) == 1, out.stdout


def _load_gate(root):
    import importlib
    sys.path.insert(0, str(root / "scripts/process"))
    try:
        for name in ("check_review", "attest_evidence", "dispatch", "required_records"):
            sys.modules.pop(name, None)
        return importlib.import_module("check_review")
    finally:
        sys.path.remove(str(root / "scripts/process"))


def test_an_unknown_range_carries_every_spec_plan(render, tmp_path, monkeypatch):
    """Refute of #266 (M2): the gate handed `spec_plan_findings` the active plans as its
    stand-in for an unknown range, so spec plans were never in flight there."""
    r = Repo(render, tmp_path, claim="")
    _git(r.root, "checkout", "-q", "main")
    spec = r.root / "specs/80-other"
    spec.mkdir(parents=True)
    (spec / "plan.md").write_text("# Plan\n\ntier: 3\nissue: #80\n\n## Decisions\n", encoding="utf-8")
    _git(r.root, "add", "-A")
    _git(r.root, "commit", "-q", "-m", "spec on main")
    _git(r.root, "checkout", "-q", "feature")
    _git(r.root, "merge", "-q", "--no-edit", "main")
    cr = _load_gate(r.root)
    owed = "specs/80-other/plan.md: tier 3 plan has no clearing REVIEW"
    try:
        assert not any(owed in f for f in cr.spec_plan_findings(r.root, [], {"widget.py"}))
        assert any(owed in f for f in cr.spec_plan_findings(r.root, [], None))
        monkeypatch.setattr(cr, "paths_in_flight", lambda *a, **k: None)
        monkeypatch.chdir(r.root)
        hard, soft = cr.check(r.root)
        assert any(owed in f for f in hard + soft), (hard, soft)
    finally:
        for name in ("check_review", "attest_evidence", "dispatch", "required_records"):
            sys.modules.pop(name, None)


def test_a_waiver_in_the_archive_or_a_spec_plan_owes_the_owners_word(render, tmp_path):
    """Refute of #282: the owner's word was asked only of an active plan's waiver; one
    written straight into the archive or into a Spec Kit plan passed."""
    r = Repo(render, tmp_path, tier=3)
    plan = r.root / ".process-work/plans/2026-10-15-77-widget.md"
    archive = r.root / ".process-work/plans/archive"
    archive.mkdir(parents=True, exist_ok=True)
    plan.rename(archive / plan.name)
    (archive / plan.name).write_text((archive / plan.name).read_text() + "review-waived: nah #77\n")
    spec = r.root / "specs/78-gadget"
    spec.mkdir(parents=True)
    (spec / "plan.md").write_text("# Plan\n\ntier: 3\nissue: #78\n\nreview-waived: nah\n", encoding="utf-8")
    _git(r.root, "add", "-A")
    _git(r.root, "commit", "-q", "-m", "waive both")
    out = r.gate()
    named = [ln for ln in out.stdout.splitlines() if "without the owner's word" in ln]
    assert out.returncode == 1 and any("archive/" in ln for ln in named) \
        and any("specs/78-gadget" in ln for ln in named), out.stdout
