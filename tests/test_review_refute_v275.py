"""Refute v2.75 round 1 on #250/#251: one CommonMark reading of fences, and a plan
leaving every arm's sight still owes its review. Each test was red before its fix."""

import os
import subprocess
import sys

import pytest

JOURNAL = ".process-work/journal"
ARCHIVE = ".process-work/plans/archive"
PLANS = ".process-work/plans"
CODEX = "gpt-6-sol"


def R(work="auth", tier="3", model="cross"):
    return (f"REVIEW work={work} tier={tier} reviewer=fresh model={model} "
            f"independence=bundle,non-implementing,cross-model verdict=pass round=1")


def run(root, merge=False):
    env = {**os.environ}
    if merge:
        env["PROCESS_PUSH_TARGETS"] = "refs/heads/main"
    r = subprocess.run([sys.executable, str(root / "scripts/process/check_review.py"), "."],
                       cwd=root, capture_output=True, text=True, env=env)
    return r


def write(root, rel, text):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t", *args],
                          capture_output=True, text=True, check=True).stdout.strip()


# ---------------- fence scenarios (no git) ----------------

def test_S_quoted_waiver_after_indented_nested_fence_stays_quoted(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    write(out, f"{ARCHIVE}/2026-07-10-widget.md",
          "# Plan\n\ntier: 3\n\n```md\n- step\n    ```bash\n    make\n    ```\n"
          "review-waived: quoted example, not a waiver\n```\n")
    r = run(out)
    assert r.returncode == 1 and "no clearing REVIEW" in r.stdout


def test_S3_quoted_review_after_indented_nested_fence_does_not_clear(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    write(out, f"{ARCHIVE}/2026-07-01-auth.md", "tier: 3\n")
    write(out, f"{JOURNAL}/2026-07-04.md",
          "```md\n1. x\n    ```text\n    y\n    ```\n" + R() + "\n```\n")
    r = run(out)
    assert r.returncode == 1 and "no clearing REVIEW" in r.stdout


def test_D_list_item_fence_in_journal_is_no_refusal(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    write(out, f"{ARCHIVE}/2026-07-01-auth.md", "tier: 3\n")
    write(out, f"{JOURNAL}/2026-07-04.md",
          R() + "\n\n- ran the suite:\n- ```bash\n  make test\n  ```\n\n" + R(work="other", tier="2") + "\n")
    r = run(out)
    assert r.returncode == 0


def test_M_unclosed_last_code_block_with_issue_field_is_no_refusal(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    write(out, f"{ARCHIVE}/2026-07-01-auth.md", "tier: 3\n")
    write(out, f"{JOURNAL}/2026-07-04.md",
          R() + "\n\nsketch:\n\n```python\n@dataclass\nclass Ticket:\n    issue: int\n")
    r = run(out)
    assert r.returncode == 0


def test_M2_unclosed_fence_in_design_doc_is_no_refusal(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    write(out, f"{PLANS}/design-widget.md",
          "# Design: widget\n\nexample header:\n\n```yaml\ntier: 2\nissue: '#5'\n")
    r = run(out)
    assert "design-widget.md: fence opened" not in r.stdout


def test_B_indented_code_block_is_no_fence(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    write(out, f"{ARCHIVE}/2026-07-01-auth.md", "tier: 3\n")
    write(out, f"{JOURNAL}/2026-07-04.md",
          R() + "\n\nliteral:\n\n    ```\n    x\n\n" + R(work="other", tier="2") + "\n")
    r = run(out)
    assert r.returncode == 0








# ---------------- deletion scenarios (git) ----------------

PLAN = "# Plan\n\ntier: 3\nissue: #77\n\n## Decisions\n"


def base_repo(render, tmp_path, *, body=PLAN, name="2026-09-07-widget.md", policy=None, extra=None):
    out = render(tmp_path, {"project_name": "demo"})
    git(out, "init", "-q", "-b", "main")
    if policy:
        import json
        (out / "docs/process/model-policy.local.json").write_text(json.dumps(policy), encoding="utf-8")
    write(out, f"{PLANS}/{name}", body)
    for rel, text in (extra or {}).items():
        write(out, rel, text)
    git(out, "add", "-A")
    git(out, "commit", "-q", "-m", "base")
    git(out, "checkout", "-q", "-b", "feature")
    write(out, "widget.py", "X = 1\n")
    git(out, "add", "-A")
    git(out, "commit", "-q", "-m", "feat: widget")
    return out


def commit(out, msg="chore: x"):
    git(out, "add", "-A")
    git(out, "commit", "-q", "-m", msg)


@pytest.mark.parametrize("dst", [
    f"{PLANS}/2026-09-07-widget.txt",
    f"{PLANS}/old/2026-09-07-widget.md",
    f"{ARCHIVE}/2026/2026-09-07-widget.md",
    f"{PLANS}/design-widget.md",
])
def test_DEL_rename_out_of_every_arm_is_refused(render, tmp_path, dst):
    out = base_repo(render, tmp_path)
    (out / dst).parent.mkdir(parents=True, exist_ok=True)
    git(out, "mv", f"{PLANS}/2026-09-07-widget.md", dst)
    commit(out)
    r = run(out, merge=True)
    assert r.returncode == 1


def test_DEL_heavily_edited_archive_move_with_waiver_is_no_deletion(render, tmp_path):
    out = base_repo(render, tmp_path)
    git(out, "rm", "-q", f"{PLANS}/2026-09-07-widget.md")
    write(out, f"{ARCHIVE}/2026-09-07-widget.md",
          "# Widget plan (closed)\n\ntier: 3\nissue: #77\n"
          "review-waived: spike thrown away, see #77\n\n## Decisions\n\n- dropped the widget\n"
          "- kept the old path\n\n## Outcome\n\nNothing shipped.\n")
    commit(out, "chore: archive the spike")
    r = run(out, merge=True)
    assert "deleted by this push" not in r.stdout


def test_DEL_design_doc_with_tier_line_deleted_is_no_finding(render, tmp_path):
    out = base_repo(render, tmp_path, name="design-widget.md",
                    body="# Design: widget\n\ntier: 3\nissue: #77\n\n## Intent\n")
    git(out, "rm", "-q", f"{PLANS}/design-widget.md")
    commit(out, "chore: drop the design")
    r = run(out, merge=True)
    assert "deleted by this push" not in r.stdout





def test_DEL_own_family_not_bypassed_by_deleting(render, tmp_path):
    out = base_repo(render, tmp_path, policy={"review_evidence": {"own_family_from_tier": 3}})
    write(out, "widget.py", "X = 2\n")
    commit(out, "fix: widget (#77)")
    head = git(out, "rev-parse", "HEAD")
    base = git(out, "merge-base", "main", "HEAD")
    write(out, f"{JOURNAL}/2026-10-15.md",
          f"REVIEW work=77 tier=3 reviewer=r model={CODEX} independence=bundle,non-implementing,cross-model "
          f"verdict=pass round=1 base={base} head={head}\n")
    commit(out, "docs: journal")
    # control: the plan kept active is refused for the own-family rule
    rc = run(out, merge=True)
    git(out, "rm", "-q", f"{PLANS}/2026-09-07-widget.md")
    commit(out, "chore: drop the plan")
    r = run(out, merge=True)
    assert rc.returncode == 1 and "outside" in rc.stdout
    assert r.returncode == 1





def test_DEL_detached_head(render, tmp_path):
    out = base_repo(render, tmp_path)
    git(out, "rm", "-q", f"{PLANS}/2026-09-07-widget.md")
    commit(out, "chore: drop")
    git(out, "checkout", "-q", "--detach")
    r = run(out, merge=True)
    assert r.returncode == 1 and "deleted by this push" in r.stdout


def test_DEL_spec_plan_deleted(render, tmp_path):
    out = base_repo(render, tmp_path, extra={"specs/001-x/plan.md": PLAN.replace("#77", "#78")})
    git(out, "rm", "-q", "-r", "specs/001-x")
    commit(out, "chore: drop spec")
    r = run(out, merge=True)
    assert "specs/001-x/plan.md: deleted by this push" in r.stdout


def test_DEL_tier1_plan_deleted_no_finding(render, tmp_path):
    out = base_repo(render, tmp_path, body=PLAN.replace("tier: 3", "tier: 1"))
    git(out, "rm", "-q", f"{PLANS}/2026-09-07-widget.md")
    commit(out, "chore: drop")
    r = run(out, merge=True)
    assert "deleted by this push" not in r.stdout


def test_DEL_partial_clone_offline_fails_closed(render, tmp_path):
    src = base_repo(render, tmp_path / "src")
    git(src, "rm", "-q", f"{PLANS}/2026-09-07-widget.md")
    commit(src, "chore: drop")
    git(src, "config", "uploadpack.allowFilter", "true")
    git(src, "config", "uploadpack.allowAnySHA1InWant", "true")
    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "-q", "--filter=blob:none", "--branch", "feature",
                    f"file://{src}", str(clone)], check=True)
    git(clone, "branch", "-q", "main", "origin/main")
    # the plan blob at the fork point was never fetched; the remote goes away
    git(clone, "remote", "set-url", "origin", f"file://{tmp_path}/gone")
    r = run(clone, merge=True)
    assert r.returncode == 1 and "git cannot read it at the fork point" in r.stdout, r.stdout


@pytest.mark.parametrize("opener,closer", [("~~~", "```"), ("````", "```")])
def test_a_fence_closes_only_on_its_own_character_and_length(render, tmp_path, opener, closer):
    # a REVIEW after the wrong closer is still quoted: the shard's fence never closes
    out = render(tmp_path, {"project_name": "demo"})
    write(out, f"{ARCHIVE}/2026-07-01-auth.md", "tier: 3\n")
    write(out, f"{JOURNAL}/2026-07-04.md", f"{opener}md\nexample\n{closer}\n" + R() + "\n")
    r = run(out)
    assert r.returncode == 1 and "fence opened on line 1 never closes — line 4" in r.stdout, r.stdout


@pytest.mark.parametrize("hidden", ["review-waived: spike", "issue: #77", "tier: 3", R()])
def test_an_unclosed_fence_hiding_any_declaration_is_hard(render, tmp_path, hidden):
    out = render(tmp_path, {"project_name": "demo"})
    write(out, f"{PLANS}/2026-09-07-widget.md", f"# Plan\n\ntier: 2\n\n```md\nexample\n{hidden}\n")
    r = run(out)
    assert r.returncode == 1 and "fence opened on line 5 never closes — line 7" in r.stdout, r.stdout


def test_an_unclosed_fence_in_a_spec_plan_hiding_a_marker_is_hard(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    write(out, "specs/001-x/plan.md", "# Plan\n\ntier: 2\n\n```\n[NEEDS CLARIFICATION: which?]\n")
    r = subprocess.run([sys.executable, str(out / "scripts/process/check_clarification.py"), "."],
                       cwd=out, capture_output=True, text=True)
    assert r.returncode == 1 and "fence opened on line 5 never closes" in r.stdout, r.stdout
