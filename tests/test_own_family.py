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

    def __init__(self, render, tmp_path: Path, *, own_from: int | None = 3, tier: int = 3) -> None:
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
        _git(out, "commit", "-q", "-m", "feat: widget (#77)")
        self.alt = _git(out, "rev-parse", "HEAD")
        (out / "widget.py").write_text("X = 2\n", encoding="utf-8")
        _git(out, "commit", "-q", "-am", "fix: widget (#77)")
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
    assert out.returncode == 1 and "cleared only by another model family" in out.stdout, out.stdout


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
    assert out.returncode == 1 and "cleared only by another model family" in out.stdout, out.stdout


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
    assert out.returncode == 1 and "cleared only by another model family" in out.stdout, out.stdout
