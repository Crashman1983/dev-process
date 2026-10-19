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


def test_D_a_fence_inside_a_list_item_is_reported_never_silent(render, tmp_path):
    # lists are not modelled (v2.75 review rounds 2-4): the item's indented closer opens a
    # fence that never closes — a loud finding, never a REVIEW read the wrong way
    out = render(tmp_path, {"project_name": "demo"})
    write(out, f"{ARCHIVE}/2026-07-01-auth.md", "tier: 3\n")
    write(out, f"{JOURNAL}/2026-07-04.md",
          R() + "\n\n- ran the suite:\n- ```bash\n  make test\n  ```\n\n" + R(work="other", tier="2") + "\n")
    r = run(out)
    assert r.returncode == 1 and "fence opened on line 6 never closes" in r.stdout, r.stdout


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


def test_B_a_fence_in_an_indented_code_block_is_reported_never_silent(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    write(out, f"{ARCHIVE}/2026-07-01-auth.md", "tier: 3\n")
    write(out, f"{JOURNAL}/2026-07-04.md",
          R() + "\n\nliteral:\n\n    ```\n    x\n\n" + R(work="other", tier="2") + "\n")
    r = run(out)
    assert r.returncode == 1 and "fence opened on line 5 never closes" in r.stdout, r.stdout








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


def test_a_quoted_record_in_a_list_items_fence_stays_quoted(render, tmp_path):
    # review v2.75 r1: a fence four columns in on a list item's continuation line is the
    # item's code — read as prose, a quoted REVIEW cleared and a quoted waiver waived
    out = render(tmp_path, {"project_name": "demo"})
    write(out, f"{ARCHIVE}/2026-07-01-auth.md",
          "# Plan\n\ntier: 3\n\n- Example of a record (quoted):\n\n    ```\n"
          "    review-waived: example only\n    tier: 1\n    ```\n")
    write(out, f"{JOURNAL}/2026-07-04.md", "- Example (quoted):\n\n    ```\n    " + R() + "\n    ```\n")
    r = run(out)
    assert r.returncode == 1 and "no clearing REVIEW" in r.stdout, r.stdout


def test_git_failing_to_list_deleted_plans_is_a_finding(render, tmp_path):
    # review v2.75 r1: the fail-closed branch had no test
    out = base_repo(render, tmp_path)
    probe = ("import sys; sys.dont_write_bytecode = True; sys.path.insert(0, 'scripts/process'); "
             "import check_review as c; c.plans_deleted = lambda *a: None; "
             "hard, _soft = c.check(c.Path('.')); print('\\n'.join(hard))")
    r = subprocess.run([sys.executable, "-c", probe], cwd=out, capture_output=True, text=True,
                       env={**os.environ, "PROCESS_PUSH_TARGETS": "refs/heads/main"})
    assert "git cannot list the plans this push deletes" in r.stdout, r.stdout + r.stderr


def test_a_marker_in_a_nested_lists_outer_item_is_read(render, tmp_path):
    # review v2.75 r2: a list-tracking scan dropped to column 0 after a nested item and
    # read the outer item's paragraph as code — an open question passed silently
    out = render(tmp_path, {"project_name": "demo"})
    write(out, f"{PLANS}/2026-10-19-store.md",
          "# Plan\n\ntier: 2\n\n1. Decide storage\n   - option A: postgres\n\n"
          "    Which one? [NEEDS CLARIFICATION: postgres or sqlite]\n")
    r = subprocess.run([sys.executable, str(out / "scripts/process/check_clarification.py"), "."],
                       cwd=out, capture_output=True, text=True)
    assert r.returncode == 1 and "2026-10-19-store.md:8" in r.stdout, r.stdout


def test_a_record_in_a_nested_lists_outer_item_counts(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    write(out, f"{ARCHIVE}/2026-07-01-auth.md", "tier: 3\n")
    write(out, f"{JOURNAL}/2026-07-04.md", "1. Merged auth\n   - follow-ups filed\n\n    " + R() + "\n")
    r = run(out)
    assert r.returncode == 0, r.stdout


def test_a_wrapped_list_item_keeps_its_next_paragraph_prose(render, tmp_path):
    # review v2.75 r3: an unindented wrapped line counted as top-level prose, and the item's
    # next indented paragraph read as code — its open question passed silently
    out = render(tmp_path, {"project_name": "demo"})
    write(out, f"{PLANS}/2026-10-19-store.md",
          "# Plan\n\ntier: 2\n\n1. Decide storage between postgres and sqlite, depending\n"
          "on where it deploys.\n\n    Which one? [NEEDS CLARIFICATION: postgres or sqlite]\n")
    r = subprocess.run([sys.executable, str(out / "scripts/process/check_clarification.py"), "."],
                       cwd=out, capture_output=True, text=True)
    assert r.returncode == 1 and "2026-10-19-store.md:8" in r.stdout, r.stdout


def test_an_unclosed_fence_hiding_a_decision_needed_is_hard(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    write(out, f"{PLANS}/2026-10-19-store.md",
          "# Plan\n\ntier: 2\n\n```bash\nmake test\n\nDECISION NEEDED 2026-10-19 seb: postgres or sqlite?\n")
    r = run(out)
    assert r.returncode == 1 and "fence opened on line 5 never closes — line 8" in r.stdout, r.stdout


def test_a_wrapped_line_starting_with_an_issue_ref_keeps_the_item_prose(render, tmp_path):
    # review v2.75 r4: `#250 …` read as a heading started top-level prose and hid the marker
    out = render(tmp_path, {"project_name": "demo"})
    write(out, f"{PLANS}/2026-10-19-store.md",
          "# Plan\n\ntier: 2\n\n1. Decide storage between postgres and sqlite, background in\n"
          "#250 and the deploy notes.\n\n    Which one? [NEEDS CLARIFICATION: postgres or sqlite]\n")
    r = subprocess.run([sys.executable, str(out / "scripts/process/check_clarification.py"), "."],
                       cwd=out, capture_output=True, text=True)
    assert r.returncode == 1 and "2026-10-19-store.md:8" in r.stdout, r.stdout


def test_a_list_marker_fence_hides_no_marker_and_clears_nothing(render, tmp_path):
    # review v2.75 r4: a fence right after a list marker is no fence here (as in v2.74.2)
    out = render(tmp_path, {"project_name": "demo"})
    write(out, f"{PLANS}/2026-10-19-store.md",
          "# Plan\n\ntier: 2\n\n- ```text\n[NEEDS CLARIFICATION: postgres or sqlite]\n  ```\n")
    r = subprocess.run([sys.executable, str(out / "scripts/process/check_clarification.py"), "."],
                       cwd=out, capture_output=True, text=True)
    assert r.returncode == 1 and "2026-10-19-store.md:6" in r.stdout, r.stdout
    write(out, f"{ARCHIVE}/2026-07-01-auth.md", "tier: 3\n")
    write(out, f"{JOURNAL}/2026-07-04.md", "- Ran:\n- ```bash\nmake test\n```\n\n" + R() + "\n")
    r = run(out)
    assert r.returncode == 1 and "no clearing REVIEW" in r.stdout, r.stdout
