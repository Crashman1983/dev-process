"""SP62: the /finish tail checker — blocked without a clearing pass, ready
with one, and the printed tail carries the ritual order."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

JOURNAL = ".process-work/journal"
PLANS = ".process-work/plans"


def _run(root):
    return subprocess.run(
        [sys.executable, str(root / "scripts/process/finish.py"), "."],
        cwd=root, capture_output=True, text=True,
    )


def _git(root: Path, *args: str):
    return subprocess.run(["git", *args], cwd=root, capture_output=True,
                          text=True, check=True)


def _repo_on_feature(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    _git(out, "init", "-q", "-b", "main")
    _git(out, "config", "user.email", "t@example.com")
    _git(out, "config", "user.name", "Test")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "base")
    _git(out, "checkout", "-q", "-b", "feature")
    return out


def _active_plan(root, name, body):
    d = root / PLANS
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(body, encoding="utf-8")


def _journal(root, *lines, name="2026-07-04.md"):
    d = root / JOURNAL
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_blocked_on_main(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo"})
    _git(out, "init", "-q", "-b", "main")
    _git(out, "config", "user.email", "t@example.com")
    _git(out, "config", "user.name", "Test")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "base")
    r = _run(out)
    assert r.returncode == 1
    assert "no feature branch to finish" in r.stdout


def test_on_main_names_the_unmerged_branches_and_their_worktrees(render, tmp_path):
    out = render(tmp_path / "main", {"project_name": "demo"})
    _git(out, "init", "-q", "-b", "main")
    _git(out, "config", "user.email", "t@example.com")
    _git(out, "config", "user.name", "Test")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "base")
    r = _run(out)
    assert "no branch is left unmerged into main" in r.stdout, r.stdout
    wt = tmp_path / "wt-7"
    _git(out, "worktree", "add", "-q", "-b", "7-widget", str(wt), "main")
    (wt / "w.txt").write_text("w\n")
    _git(wt, "add", "-A")
    _git(wt, "commit", "-q", "-m", "feat: w")
    _git(out, "branch", "8-gizmo", "7-widget")
    _git(out, "branch", "merged-one", "main")  # merged: not offered
    r = _run(out)
    assert r.returncode == 1
    assert (f"check out the branch first: cd {wt.resolve()} (holds 7-widget) | "
            f"git checkout 8-gizmo") in r.stdout, r.stdout
    assert "merged-one" not in r.stdout


def test_blocked_without_clearing_pass(render, tmp_path):
    out = _repo_on_feature(render, tmp_path)
    _active_plan(out, "2026-07-04-widget.md", "# Plan\n\ntier: 2\nissue: none\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "feat: widget plan")
    r = _run(out)
    assert r.returncode == 1
    assert "no clearing REVIEW" in r.stdout and "/review before /finish" in r.stdout


@pytest.mark.parametrize("name", ["2026-07-04-größe.md", "2026-07-04-new\nline.md"])
def test_a_plan_whose_name_git_quotes_is_still_this_branchs(render, tmp_path, name):
    # without -z git prints such a name quoted; the plan read as another
    # work's and finished without its review (downstream refutation)
    out = _repo_on_feature(render, tmp_path)
    _active_plan(out, name, "# Plan\n\ntier: 2\nissue: none\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "feat: plan with a quoted name")
    r = _run(out)
    assert r.returncode == 1, r.stdout
    assert "no clearing REVIEW" in r.stdout


def test_ready_with_pass_prints_ordered_tail(render, tmp_path):
    out = _repo_on_feature(render, tmp_path)
    _active_plan(out, "2026-07-04-widget.md", "# Plan\n\ntier: 2\nissue: none\n")
    _journal(out, "REVIEW work=widget tier=2 reviewer=fresh model=same "
                  "independence=bundle,non-implementing verdict=pass round=1")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "feat: widget with pass")
    _git(out, "remote", "add", "origin", str(tmp_path / "origin.git"))  # the push tail (#330)
    r = _run(out)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "finish: ready" in r.stdout
    # ritual order: archive before merge, merge before branch delete
    ai = r.stdout.index("archive the plan")
    mi = r.stdout.index("merge:")
    di = r.stdout.index("--delete")
    assert ai < mi < di
    assert "worktree" in r.stdout
    # deleting the base of a stacked PR closes it on GitHub — the tail says so
    assert "retarget a PR stacked on it first" in r.stdout[di:].split("\n", 1)[0]


def test_blocked_on_dirty_worktree(render, tmp_path):
    out = _repo_on_feature(render, tmp_path)
    (out / "untracked.txt").write_text("wip\n", encoding="utf-8")
    r = _run(out)
    assert r.returncode == 1
    assert "worktree not clean" in r.stdout


# --- SP64: the speckit path's plans reach the presence question ------------

def _spec_dir(root, name, *, tier=2, ticked=True, issue="#42"):
    d = root / "specs" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "plan.md").write_text(f"# Plan\n\ntier: {tier}\nissue: {issue}\n",
                               encoding="utf-8")
    box = "x" if ticked else " "
    (d / "tasks.md").write_text(f"- [{box}] T001 do the thing\n",
                                encoding="utf-8")
    return d


def test_speckit_plan_without_pass_blocks(render, tmp_path):
    out = _repo_on_feature(render, tmp_path)
    _spec_dir(out, "009-widget", tier=3, ticked=True)
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "feat: widget spec work")
    r = _run(out)
    assert r.returncode == 1
    assert "specs/009-widget" in r.stdout and "/review before /finish" in r.stdout


def test_speckit_plan_with_pass_is_ready_and_prunes(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo",
                            "modules": {"speckit": True}})
    _git(out, "init", "-q", "-b", "main")
    _git(out, "config", "user.email", "t@example.com")
    _git(out, "config", "user.name", "Test")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "base")
    _git(out, "checkout", "-q", "-b", "feature")
    _spec_dir(out, "009-widget", tier=2, ticked=True, issue="#9")
    _journal(out, "REVIEW work=9 tier=2 reviewer=fresh model=same "
                  "independence=bundle,non-implementing verdict=pass round=1")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "feat: widget with pass")
    r = _run(out)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "publish_and_prune.py specs/009-widget" in r.stdout


def _speckit_main(render, tmp_path):
    """A speckit-rendered repository on `main`, nothing committed yet."""
    out = render(tmp_path, {"project_name": "demo", "modules": {"speckit": True}})
    _git(out, "init", "-q", "-b", "main")
    _git(out, "config", "user.email", "t@example.com")
    _git(out, "config", "user.name", "Test")
    return out


def test_a_foreign_finished_spec_is_not_in_this_branchs_tail(render, tmp_path):
    """v2.94 B1: the tail printed publish_and_prune for every fully ticked spec dir, also
    for one somebody else finished on main — the same own-spec rule as spec_plan_findings."""
    out = _speckit_main(render, tmp_path)
    _spec_dir(out, "005-old", tier=2, ticked=True, issue="#5")
    _journal(out, "REVIEW work=5 tier=2 reviewer=fresh model=same "
                  "independence=bundle,non-implementing verdict=pass round=1")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "base")
    _git(out, "checkout", "-q", "-b", "feature")
    _spec_dir(out, "009-widget", tier=2, ticked=True, issue="#9")
    _journal(out, "REVIEW work=9 tier=2 reviewer=fresh model=same "
                  "independence=bundle,non-implementing verdict=pass round=1", name="2026-07-05.md")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "feat: widget with pass")
    r = _run(out)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "publish_and_prune.py specs/009-widget" in r.stdout  # its own stays
    assert "specs/005-old" not in r.stdout, r.stdout
    assert "range unknown" not in r.stdout


def test_the_own_spec_rule_has_one_owner(render, tmp_path):
    """The tail and the gate's `spec_plan_findings` ask one helper whether a spec dir is
    this branch's (`check_review.own_spec`); finish keeps no copy of the rule."""
    out = render(tmp_path, {"project_name": "demo", "modules": {"speckit": True}})
    sys.path.insert(0, str(out / "scripts/process"))
    try:
        sys.modules.pop("check_review", None)
        import check_review
        assert check_review.own_spec("specs/009-w", {"specs/009-w/plan.md"})
        assert check_review.own_spec("specs/009-w/", {"specs/009-w/tasks.md"})
        assert not check_review.own_spec("specs/009-w", {"specs/009-widget/plan.md", "src/a.py"})
        assert check_review.own_spec("specs/009-w", None)  # an unknown range hides nothing
    finally:
        sys.path.remove(str(out / "scripts/process"))
        sys.modules.pop("check_review", None)
    finish = (out / "scripts/process/finish.py").read_text(encoding="utf-8")
    assert "def _own_spec" not in finish and "own_spec(" in finish
    review = (out / "scripts/process/check_review.py").read_text(encoding="utf-8")
    body = review.split("def spec_plan_findings", 1)[1].split("\ndef ", 1)[0]
    assert "own_spec(" in body and "startswith(spec_dir)" not in body


def test_without_a_fork_point_every_finished_spec_is_named_with_a_caution(render, tmp_path):
    """v2.94 B1: no fork point, no range — the own specs are never hidden, so every
    finished spec stays in the tail, marked."""
    out = render(tmp_path, {"project_name": "demo", "modules": {"speckit": True}})
    _git(out, "init", "-q", "-b", "feature")  # no integration branch at all: no fork point
    _git(out, "config", "user.email", "t@example.com")
    _git(out, "config", "user.name", "Test")
    _spec_dir(out, "005-old", tier=1, ticked=True, issue="#5")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "feat: a history without main")
    r = _run(out)
    assert r.returncode == 0, r.stdout + r.stderr
    line = next(ln for ln in r.stdout.splitlines() if "publish_and_prune.py specs/005-old" in ln)
    assert line.endswith("(range unknown — run only your own)"), line


def test_the_finish_command_starts_with_apply(render, tmp_path):
    """v2.94 B2: the separate preview run paid a full gate run of its own; `--apply` runs the
    same check, prints the same blockers and applies nothing when one blocks."""
    out = render(tmp_path, {"project_name": "demo"})
    doc = (out / ".claude/commands/finish.md").read_text()
    runs = [ln.strip() for ln in doc.splitlines() if ln.strip().startswith("uv run scripts/process/finish.py")]
    assert runs and all(" --apply" in ln for ln in runs), runs
    assert runs[0].startswith("uv run scripts/process/finish.py --apply --tests"), runs  # no train: straight on
    flat = " ".join(doc.split())
    assert "without `--apply` stays a read-only preview" in flat
    assert "stop after the archive step (`finish.py --apply` without `--tests`)" in flat  # the train route


def test_apply_prints_the_publish_line_of_each_own_finished_spec(render, tmp_path):
    """v2.94 B2: `--apply` names the publish_and_prune command per finished spec dir of the
    branch itself, not only the general by-hand text."""
    out = _speckit_main(render, tmp_path)
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "base")
    _git(out, "checkout", "-q", "-b", "feature")
    _spec_dir(out, "009-widget", tier=1, ticked=True, issue="#9")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "feat: widget")
    r = _run_args(out, "--apply")  # the train route stops before the merge and names it too
    assert r.returncode == 0 and "stopped before the merge" in r.stdout, r.stdout + r.stderr
    assert ("finish: after the merge $ python3 scripts/process/publish_and_prune.py "
            "specs/009-widget") in r.stdout, r.stdout
    r = _run_args(out, "--apply", "--tests", "true")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "merged feature into main locally" in r.stdout, r.stdout
    after = r.stdout.split("merged feature into main locally", 1)[1]
    assert "python3 scripts/process/publish_and_prune.py specs/009-widget" in after, r.stdout


def test_a_foreign_finished_spec_without_review_still_blocks(render, tmp_path):
    """Guard (v2.94, M4): `speckit_unreviewed` stays unfiltered — the only hard stop for a
    ticked Tier 2 spec without review that already sits on main."""
    out = _speckit_main(render, tmp_path)
    _spec_dir(out, "005-old", tier=2, ticked=True, issue="#5")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "base")
    _git(out, "checkout", "-q", "-b", "feature")
    (out / "payload.txt").write_text("mine\n", encoding="utf-8")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "feat: unrelated")
    r = _run(out)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "specs/005-old" in r.stdout and "its tasks are all ticked" in r.stdout, r.stdout


def test_speckit_plan_in_flight_without_review_blocks(render, tmp_path):
    """#266: a Spec Kit plan this branch carries owes its review at the merge, like an
    active plan — unticked tasks no longer let it through."""
    out = _repo_on_feature(render, tmp_path)
    _spec_dir(out, "009-widget", tier=3, ticked=False)
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "feat: widget in flight")
    r = _run(out)
    assert r.returncode == 1 and "specs/009-widget/plan.md" in r.stdout, r.stdout + r.stderr


def test_foreign_active_plan_does_not_block_this_branch(render, tmp_path):
    # SP65: a tier-3 decision paper committed on main by someone else is
    # neither this branch's review debt nor its archiving duty
    out = render(tmp_path, {"project_name": "demo"})
    _git(out, "init", "-q", "-b", "main")
    _git(out, "config", "user.email", "t@example.com")
    _git(out, "config", "user.name", "Test")
    _active_plan(out, "2026-09-01-foreign.md", "# Plan\n\ntier: 3\nissue: #5\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "base")
    _git(out, "checkout", "-q", "-b", "feature")
    (out / "payload.txt").write_text("mine\n", encoding="utf-8")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "feat: unrelated")
    r = _run(out)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "foreign" not in r.stdout
    # but a commit that CLAIMS the plan's issue pulls it in
    _git(out, "commit", "-q", "--allow-empty", "-m", "feat: do it (#5)")
    r = _run(out)
    assert r.returncode == 1
    assert "foreign" in r.stdout and "/review before /finish" in r.stdout


def test_not_runnable_gates_are_named_apart_from_red(render, tmp_path, monkeypatch):
    out = _repo_on_feature(render, tmp_path)
    (out / "scripts/process/gate_runner.py").unlink()
    r = _run(out)
    assert r.returncode == 1
    assert "NOT RUNNABLE (not red)" in r.stdout and "missing" in r.stdout


# --- v2.8.1: --apply executes the deterministic tail ------------------------

def _run_args(root, *args):
    return subprocess.run(
        [sys.executable, str(root / "scripts/process/finish.py"), *args, "."],
        cwd=root, capture_output=True, text=True,
    )


def _repo_with_origin(render, tmp_path):
    out = render(tmp_path / "work", {"project_name": "demo"})
    bare = tmp_path / "origin.git"
    _git(out, "init", "-q", "-b", "main")
    _git(out, "config", "user.email", "t@example.com")
    _git(out, "config", "user.name", "Test")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "base")
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    _git(out, "remote", "add", "origin", str(bare))
    _git(out, "push", "-q", "-u", "origin", "main")
    _git(out, "checkout", "-q", "-b", "feature")
    _active_plan(out, "2026-09-07-tiny.md", "# Plan\n\ntier: 1\n")
    (out / "payload.txt").write_text("done\n", encoding="utf-8")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "feat: tiny")
    _git(out, "push", "-q", "-u", "origin", "feature")
    return out, bare


def test_apply_archives_and_stops_before_the_merge(render, tmp_path):
    out, _bare = _repo_with_origin(render, tmp_path)
    r = _run_args(out, "--apply")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "stopped before the merge" in r.stdout
    assert (out / PLANS / "archive" / "2026-09-07-tiny.md").is_file()
    assert not (out / PLANS / "2026-09-07-tiny.md").exists()
    assert "archive plan(s) on merge" in _git(out, "log", "-1", "--format=%s").stdout
    assert _git(out, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == "feature"


def test_apply_with_asserted_suite_merges_pushes_and_deletes_branch(render, tmp_path):
    out, bare = _repo_with_origin(render, tmp_path)
    r = _run_args(out, "--apply", "--tests-passed")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "merged feature into main and pushed" in r.stdout
    assert _git(out, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == "main"
    remote_heads = subprocess.run(["git", "--git-dir", str(bare), "branch"],
                                  capture_output=True, text=True).stdout
    assert "feature" not in remote_heads and "main" in remote_heads
    remote_log = subprocess.run(["git", "--git-dir", str(bare), "log", "-1",
                                 "--format=%s", "main"],
                                capture_output=True, text=True).stdout
    assert "archive plan(s)" in remote_log


def test_finish_names_tokens_and_apply_writes_them_into_done(render, tmp_path):
    """No tokens per issue were recorded downstream; finish says the count or `not measured`
    and its `done` report carries the same line — no new form."""
    import json
    out, _bare = _repo_with_origin(render, tmp_path)
    r = _run(out)
    assert r.returncode == 0 and "finish: tokens: not measured (not-configured)" in r.stdout, r.stdout
    r = _run_args(out, "--apply", "--tests-passed")
    assert r.returncode == 0 and "finish: tokens: not measured (not-configured)" in r.stdout, r.stdout + r.stderr
    ledger = out / ".git/process-tower/reports.jsonl"
    done = [json.loads(line) for line in ledger.read_text().splitlines()]
    assert done[-1]["state"] == "done" and done[-1]["note"] == "tokens: not measured (not-configured)"
    assert done[-1]["worker"] == "feature"


def test_done_is_written_once_the_merge_is_pushed_even_if_the_branch_delete_fails(render, tmp_path):
    """Refute: `done` came only after the remote branch delete; a refused delete left a
    pushed merge without it."""
    import json
    out, bare = _repo_with_origin(render, tmp_path)
    hook = bare / "hooks/pre-receive"
    hook.write_text("#!/bin/sh\nwhile read old new ref; do\n"
                    "  [ \"$new\" = 0000000000000000000000000000000000000000 ] && exit 1\n"
                    "done\nexit 0\n")
    hook.chmod(0o755)
    r = _run_args(out, "--apply", "--tests-passed")
    assert r.returncode == 1 and "Traceback" not in r.stderr, r.stdout + r.stderr
    remote_log = subprocess.run(["git", "--git-dir", str(bare), "log", "-1", "--format=%s", "main"],
                                capture_output=True, text=True).stdout
    assert "archive plan(s)" in remote_log  # the merge is pushed
    done = [json.loads(line) for line in (out / ".git/process-tower/reports.jsonl").read_text().splitlines()]
    assert done[-1]["state"] == "done" and done[-1]["note"] == "tokens: not measured (not-configured)"


def test_a_failing_done_report_does_not_end_a_pushed_merge_in_a_traceback(render, tmp_path, monkeypatch):
    """A merged change must not end in a traceback over bookkeeping."""
    import importlib.util
    out = _repo_on_feature(render, tmp_path)
    sys.path.insert(0, str(out / "scripts/process"))
    spec = importlib.util.spec_from_file_location("finish_done", out / "scripts/process/finish.py")
    finish = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(finish)
    import report

    def boom(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(report, "write_report", boom)
    finish._done(out, "feature")  # no exception


def test_issue_tokens_sum_the_policy_transcripts_of_its_worktrees(render, tmp_path):
    """The count is read, never estimated: the policy's `transcripts` glob per dispatched worktree."""
    import importlib.util
    import json
    out = _repo_on_feature(render, tmp_path)
    sys.path.insert(0, str(out / "scripts/process"))
    spec = importlib.util.spec_from_file_location("finish_t", out / "scripts/process/finish.py")
    finish = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(finish)
    assert finish.usage(out, "7-widget") == (7, "tokens: not measured (not-configured)")
    wt = tmp_path / "wt [7]"  # glob characters in a worktree path are literal
    (wt / "t").mkdir(parents=True)
    (wt / "t" / "a.jsonl").write_text('{"usage": {"output_tokens": 40}}\n{"output_tokens": 2}\n')
    (wt / "t" / "b.jsonl").write_text('{"output_tokens": 100}\n')
    records = out / ".git/process-dispatch"
    records.mkdir(parents=True, exist_ok=True)
    (records / "7-widget.json").write_text(json.dumps({"issue": 7, "worktree": str(wt), "phase": "review"}))
    (records / "8-other.json").write_text(json.dumps({"issue": 8, "worktree": str(tmp_path), "phase": "plan"}))
    (out / "docs/process/model-policy.local.json").write_text(json.dumps({"transcripts": "{worktree}/t/*.jsonl"}))
    assert finish.usage(out, "7-widget") == (7, "tokens: 142 output over 2 sessions")
    assert finish.usage(out, "feature") == (None, "tokens: not measured (no-record)")
    # the same reader gives input and cache shares apart; a field the harness never
    # wrote stays absent (not measured), never a zero
    (wt / "t" / "a.jsonl").write_text('{"usage": {"input_tokens": 5, "cache_read_input_tokens": 900, '
                                      '"cache_creation": {"ephemeral_5m_input_tokens": 77}, '
                                      '"output_tokens": 40}}\n')
    import dispatch
    totals, sessions = dispatch.issue_token_usage(out, 7)
    assert sessions == 2
    assert totals == {"input_tokens": 5, "cache_read_input_tokens": 900, "output_tokens": 140}
    assert dispatch.issue_token_usage(out, 9) is None


def test_apply_red_suite_does_not_merge(render, tmp_path):
    out, _bare = _repo_with_origin(render, tmp_path)
    r = _run_args(out, "--apply", "--tests", "false")
    assert r.returncode == 1
    assert "full suite red" in r.stdout
    assert _git(out, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == "feature"


def test_rebase_texts_name_no_digest_and_no_re_review(render, tmp_path):
    """v2.94 A1: bundle digests are gone since v2.53, and a clean rebase keeps the review
    (the gate compares content) — finish must not send an agent into a new round for it."""
    out = render(tmp_path, {"project_name": "demo"})
    text = (out / "scripts/process/finish.py").read_text().lower()
    assert "digest" not in text
    assert "re-review" not in text


def test_apply_refuses_when_blocked(render, tmp_path):
    out = _repo_on_feature(render, tmp_path)
    _active_plan(out, "2026-07-04-widget.md", "# Plan\n\ntier: 2\nissue: none\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "feat: widget plan")
    r = _run_args(out, "--apply", "--tests-passed")
    assert r.returncode == 1 and "nothing applied" in r.stdout


def test_tail_names_the_full_suite_before_merge(render, tmp_path):
    out = _repo_on_feature(render, tmp_path)
    r = _run(out)
    assert r.returncode == 0, r.stdout + r.stderr
    fi = r.stdout.index("FULL test suite")
    mi = r.stdout.index("merge:")
    assert fi < mi  # the batch pays completeness before it merges


def _route_hooks(out: Path, seen: Path) -> None:
    """Hooks that log the route marker each git step sees; the pre-push one is the
    merge guard itself, fed the remote refs from stdin as a hook wrapper does."""
    hooks = out / ".git/hooks"
    for name in ("post-checkout", "post-merge"):
        (hooks / name).write_text(
            f'#!/bin/sh\necho "{name} ${{PROCESS_MERGE_ROUTE:-unset}}" >> "{seen}"\n')
        (hooks / name).chmod(0o755)
    (hooks / "pre-push").write_text(
        "#!/bin/sh\ntargets=''\n"
        "while read lref lsha rref rsha; do targets=\"$targets $rref\"; "
        f'echo "push $rref ${{PROCESS_MERGE_ROUTE:-unset}}" >> "{seen}"; done\n'
        f'exec "{sys.executable}" scripts/process/merge_route.py $targets\n')
    (hooks / "pre-push").chmod(0o755)


def test_apply_marks_only_its_own_push_to_main(render, tmp_path):
    # the pre-push guard (merge_route.py) refuses a push to main without a route;
    # finish names it for that one push and strips a marker it inherited
    out, bare = _repo_with_origin(render, tmp_path)
    seen = tmp_path / "seen.log"
    _route_hooks(out, seen)
    env = {k: v for k, v in os.environ.items() if not k.startswith(("PROCESS_", "SKIP"))}
    r = subprocess.run([sys.executable, str(out / "scripts/process/finish.py"), "--apply",
                        "--tests-passed", "."], cwd=out, capture_output=True, text=True,
                       env={**env, "PROCESS_MERGE_ROUTE": "inherited"})
    assert r.returncode == 0, r.stdout + r.stderr
    lines = seen.read_text().splitlines()
    assert "push refs/heads/main finish" in lines
    assert "push refs/heads/feature unset" in lines  # the branch deletion is no merge
    assert not [ln for ln in lines if ln.endswith("inherited")], lines
    assert "post-checkout unset" in lines and "post-merge unset" in lines
    # without finish, the same guard refuses a hand push to main
    _git(out, "commit", "-q", "--allow-empty", "-m", "by hand")
    hand = subprocess.run(["git", "push", "-q", "origin", "main"], cwd=out, capture_output=True,
                          text=True, env=env)
    assert hand.returncode != 0 and "merge_route" in hand.stderr


def _finish_module(out):
    import importlib.util
    sys.path.insert(0, str(out / "scripts/process"))
    spec = importlib.util.spec_from_file_location("finish_argv", out / "scripts/process/finish.py")
    finish = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(finish)
    return finish


def test_tests_run_without_a_shell(render, tmp_path):
    """#199: `--tests CMD` is argv, split once — no `shell=True` on argv text."""
    finish = _finish_module(_repo_on_feature(render, tmp_path))
    assert finish.tests_argv("make test") == (["make", "test"], {})
    assert finish.tests_argv("uv run pytest -k 'a or b|c'") == (["uv", "run", "pytest", "-k", "a or b|c"], {})
    assert finish.tests_argv("make test # note") == (["make", "test", "#", "note"], {})
    assert "shell=True" not in (Path(finish.__file__)).read_text()


@pytest.mark.parametrize("cmd", ["make a && make b", "make test | tee log", "make test > log",
                                 "make a; make b", "pytest 'unclosed", "   ", "CI=1", "A=1 B=2"])
def test_a_tests_command_that_needs_a_shell_is_refused(render, tmp_path, cmd):
    finish = _finish_module(_repo_on_feature(render, tmp_path))
    assert isinstance(finish.tests_argv(cmd), str)


def test_apply_refuses_a_shell_chain_before_merging(render, tmp_path):
    out, _bare = _repo_with_origin(render, tmp_path)
    r = _run_args(out, "--apply", "--tests", "true && true")
    assert r.returncode == 1 and "shell operator '&&'" in r.stdout, r.stdout


def test_tests_keep_an_env_prefix_and_refuse_a_newline(render, tmp_path):
    finish = _finish_module(_repo_on_feature(render, tmp_path))
    assert finish.tests_argv("FOO=1 make test") == (["make", "test"], {"FOO": "1"})
    assert "newline" in finish.tests_argv("make test\nmake deploy")
    assert "shell operator" in finish.tests_argv("make test # && make deploy")  # `#` hides nothing


@pytest.mark.parametrize("cmd", ["no-such-command-199", "FOO=1 no-such-command-199"])
def test_apply_with_a_missing_tests_command_does_not_merge(render, tmp_path, cmd):
    out, _bare = _repo_with_origin(render, tmp_path)
    r = _run_args(out, "--apply", "--tests", cmd)
    assert r.returncode == 1 and "cannot run" in r.stdout and "Traceback" not in r.stderr, (r.stdout, r.stderr)


def test_apply_with_an_assignment_alone_applies_nothing(render, tmp_path):
    """Refute #199: `CI=1` alone ran `env`, exit 0, and merged."""
    out, _bare = _repo_with_origin(render, tmp_path)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=out, capture_output=True, text=True).stdout
    r = _run_args(out, "--apply", "--tests", "CI=1")
    assert r.returncode == 1 and "names no command" in r.stdout and "nothing applied" in r.stdout, r.stdout
    assert subprocess.run(["git", "rev-parse", "HEAD"], cwd=out, capture_output=True, text=True).stdout == head


def test_apply_runs_the_tests_with_their_assignments(render, tmp_path):
    out, _bare = _repo_with_origin(render, tmp_path)
    check = f"FOO=199 {sys.executable} -c 'import os, sys; sys.exit(os.environ.get(\"FOO\") != \"199\")'"
    r = _run_args(out, "--apply", "--tests", check)
    assert r.returncode == 0 and "full suite red" not in r.stdout, r.stdout


def _merge_certificate(out: Path, evidence: str):
    import json
    code = ("import sys, json; sys.path.insert(0, 'scripts/process'); import certificate; "
            "from pathlib import Path; "
            f"print(json.dumps(certificate.find(Path('.'), ('merge',), {{'merge': {evidence!r}}})))")
    r = subprocess.run([sys.executable, "-c", code], cwd=out, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


@pytest.mark.parametrize("configured", [True, False])
def test_apply_with_the_merge_suite_certifies_the_merged_tree(render, tmp_path, configured):
    """#206: the push to main then runs no suite again; any other command certifies nothing."""
    import json
    out, _bare = _repo_with_origin(render, tmp_path)
    (out / "docs/process/testing.local.json").write_text(
        json.dumps({"merge_suite": "true" if configured else "make suite"}))
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "test config")
    r = _run_args(out, "--apply", "--tests", "true")
    assert r.returncode == 0, r.stdout + r.stderr
    hit = _merge_certificate(out, "true")
    if configured:
        assert "merge certificate written" in r.stdout and hit and hit["writer"] == "finish --tests"
    else:
        assert hit is None and "merge certificate" not in r.stdout


def test_tests_passed_is_refused_while_a_merge_suite_is_set(render, tmp_path):
    """#255: with a configured merge_suite the claim certifies nothing and the push would
    run the suite again — `--tests` is the route, so the claim is refused before anything
    is applied."""
    import json
    out, _bare = _repo_with_origin(render, tmp_path)
    (out / "docs/process/testing.local.json").write_text(json.dumps({"merge_suite": "true"}))
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "test config")
    head = _git(out, "rev-parse", "HEAD").stdout
    r = _run_args(out, "--apply", "--tests-passed")
    assert r.returncode == 2 and "--apply --tests" in r.stderr, r.stdout + r.stderr
    assert _git(out, "rev-parse", "HEAD").stdout == head
    assert _merge_certificate(out, "true") is None


def test_tests_passed_without_a_merge_suite_stays_a_claim(render, tmp_path):
    out, _bare = _repo_with_origin(render, tmp_path)
    r = _run_args(out, "--apply", "--tests-passed")
    assert r.returncode == 0, r.stdout + r.stderr
    assert _merge_certificate(out, "true") is None


def test_bare_tests_runs_the_merge_suite_and_certifies(render, tmp_path):
    """#255: `--tests` alone is the project's merge_suite."""
    import json
    out, _bare = _repo_with_origin(render, tmp_path)
    (out / "docs/process/testing.local.json").write_text(json.dumps({"merge_suite": "true"}))
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "test config")
    r = _run_args(out, "--apply", "--tests")
    assert r.returncode == 0, r.stdout + r.stderr
    hit = _merge_certificate(out, "true")
    assert hit and hit["writer"] == "finish --tests", r.stdout


def test_bare_tests_without_a_merge_suite_names_the_way_out(render, tmp_path):
    out, _bare = _repo_with_origin(render, tmp_path)
    r = _run_args(out, "--apply", "--tests")
    assert r.returncode == 2 and "--tests CMD" in r.stderr, r.stdout + r.stderr


def _finish(root, *args):
    """finish.py with exactly these arguments — no root appended."""
    return subprocess.run([sys.executable, str(root / "scripts/process/finish.py"), *args],
                          cwd=root, capture_output=True, text=True)


def test_tests_write_no_certificate_without_a_remote(render, tmp_path):
    """#330: the merge certificate serves the pre-push only, and a local merge pushes nothing."""
    import json
    out = _repo_without_remote(render, tmp_path)
    (out / "docs/process/testing.local.json").write_text(json.dumps({"merge_suite": "true"}))
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "test config")
    r = _run_args(out, "--apply", "--tests")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "merge certificate" not in r.stdout and _merge_certificate(out, "true") is None, r.stdout
    assert "locally (the repository has no remote)" in r.stdout


def test_bare_tests_is_read_in_every_argument_order(render, tmp_path):
    # refute v2.75 r2: only `--tests .` was tested; a bare `--tests`, `--tests --apply` and
    # `--tests ''` take other branches, and a bare name is a command even beside a folder
    import json
    out, _bare = _repo_with_origin(render, tmp_path)
    (out / "docs/process/testing.local.json").write_text(json.dumps({"merge_suite": "true"}))
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "test config")
    r = _finish(out, "--tests", "")
    assert r.returncode == 2 and "names no command" in r.stderr, r.stderr
    r = _finish(out, "--tests", "--apply")
    assert r.returncode == 0 and "merge certificate written" in r.stdout, r.stdout + r.stderr


def test_a_command_named_like_a_folder_is_the_command(render, tmp_path):
    import json
    out, _bare = _repo_with_origin(render, tmp_path)
    (out / "docs/process/testing.local.json").write_text(json.dumps({"merge_suite": "false"}))
    (out / "true").mkdir()
    (out / "true/.keep").write_text("")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "test config and a folder named true")
    r = _finish(out, "--apply", "--tests", "true")  # runs `true`, not the red merge_suite
    assert r.returncode == 0 and "full suite red" not in r.stdout, r.stdout + r.stderr


def test_a_broken_testing_file_is_named_not_mistaken_for_no_suite(render, tmp_path):
    out, _bare = _repo_with_origin(render, tmp_path)
    (out / "docs/process/testing.local.json").write_text('{"merge_suite": "true", "bogus": 1}')
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "broken test config")
    for flag in ("--tests", "--tests-passed"):
        r = _run_args(out, "--apply", flag)
        assert r.returncode == 2 and "testing.local.json cannot be read" in r.stderr, (flag, r.stderr)


def test_the_stop_names_the_route_the_merge_suite_takes(render, tmp_path):
    import json
    out, _bare = _repo_with_origin(render, tmp_path)
    (out / "docs/process/testing.local.json").write_text(json.dumps({"merge_suite": "true"}))
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "test config")
    r = _run_args(out, "--apply")
    assert r.returncode == 0 and "re-run with `--apply --tests`" in r.stdout, r.stdout
    assert "--tests-passed" not in r.stdout


# --- #330: finish in a repository without any remote --------------------------

def _repo_without_remote(render, tmp_path):
    """`_repo_with_origin` without the origin: a tier-1 plan and a payload on `feature`."""
    out = _repo_on_feature(render, tmp_path)
    _active_plan(out, "2026-09-07-tiny.md", "# Plan\n\ntier: 1\n")
    (out / "payload.txt").write_text("done\n", encoding="utf-8")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "feat: tiny")
    return out


def _main_checkout_with_feature_worktree(render, tmp_path):
    """main stays checked out in the main checkout; `feature` rides a worktree."""
    out = render(tmp_path / "main", {"project_name": "demo"})
    _git(out, "init", "-q", "-b", "main")
    _git(out, "config", "user.email", "t@example.com")
    _git(out, "config", "user.name", "Test")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "base")
    wt = tmp_path / "wt-feature"
    _git(out, "worktree", "add", "-q", "-b", "feature", str(wt), "main")
    return out, wt


def _common_dir(out: Path) -> Path:
    common = Path(_git(out, "rev-parse", "--git-common-dir").stdout.strip())
    return common if common.is_absolute() else out / common


def _failing_pre_push(out: Path, seen: Path) -> None:
    hook = _common_dir(out) / "hooks/pre-push"
    hook.write_text(f'#!/bin/sh\necho ran >> "{seen}"\nexit 1\n')
    hook.chmod(0o755)


def _reports(out: Path) -> list[dict]:
    import json
    ledger = _common_dir(out) / "process-tower/reports.jsonl"
    return [json.loads(line) for line in ledger.read_text().splitlines()] if ledger.is_file() else []


def _has_branch(out: Path, name: str) -> bool:
    return subprocess.run(["git", "rev-parse", "--verify", "-q", f"refs/heads/{name}"],
                          cwd=out, capture_output=True).returncode == 0


def test_apply_without_a_remote_merges_locally_and_deletes_the_branch(render, tmp_path):
    out = _repo_without_remote(render, tmp_path)
    seen = tmp_path / "pre-push.log"
    _failing_pre_push(out, seen)
    # a leftover tracking ref the gates never anchor on blocks nothing
    _git(out, "update-ref", "refs/remotes/old/feature", "HEAD")
    r = _run_args(out, "--apply", "--tests", "true")  # without a remote a claim is refused
    assert r.returncode == 0, r.stdout + r.stderr
    assert "merged feature into main locally (the repository has no remote)" in r.stdout, r.stdout
    assert _git(out, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == "main"
    assert "archive plan(s)" in _git(out, "log", "-1", "--format=%s", "main").stdout
    assert not _has_branch(out, "feature")  # the merged branch is deleted
    assert not seen.exists()  # nothing pushed: the pre-push never ran
    assert "merge certificate" not in r.stdout and _merge_certificate(out, "true") is None
    assert _reports(out)[-1]["state"] == "done"


def test_check_without_a_remote_prints_the_local_tail(render, tmp_path):
    out = _repo_without_remote(render, tmp_path)
    _git(out, "checkout", "-q", "main")
    (out / "other.txt").write_text("main moved\n", encoding="utf-8")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "feat: main moved")
    _git(out, "checkout", "-q", "feature")
    r = _run(out)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "git push" not in r.stdout and "git fetch" not in r.stdout, r.stdout
    assert "git rebase main" in r.stdout
    assert ("a rebase that applies cleanly keeps the review (the gate compares content); a conflict "
            "resolution needs a new round (`make_review_bundle.py --since <reviewed head>`)") in r.stdout
    assert "git checkout main && git merge --ff-only feature && git branch -d feature" in r.stdout


def test_a_local_main_ahead_of_the_branch_is_rebased_in(render, tmp_path):
    out = _repo_without_remote(render, tmp_path)
    _git(out, "checkout", "-q", "main")
    (out / "other.txt").write_text("main moved\n", encoding="utf-8")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "feat: main moved")
    moved = _git(out, "rev-parse", "HEAD").stdout.strip()
    _git(out, "checkout", "-q", "feature")
    r = _run_args(out, "--apply", "--tests", "true")
    assert r.returncode == 0, r.stdout + r.stderr
    assert ("finish: rebased — a clean rebase keeps the review; the gates below judge whether it "
            "still covers the tip") in r.stdout
    assert subprocess.run(["git", "merge-base", "--is-ancestor", moved, "main"], cwd=out).returncode == 0
    assert (out / "payload.txt").is_file() and (out / "other.txt").is_file()


@pytest.mark.parametrize("elsewhere", [False, True])
def test_a_red_merge_gate_stops_the_local_merge(render, tmp_path, elsewhere):
    """The gates run as the push to main would run them — here no push runs them."""
    if elsewhere:
        _main_checkout, out = _main_checkout_with_feature_worktree(render, tmp_path)
    else:
        out = _repo_on_feature(render, tmp_path)
    _active_plan(out, "2026-07-04-widget.md",
                 "# Plan\n\ntier: 2\nissue: none\n\n- [ ] T1 the task still open\n")
    _journal(out, "REVIEW work=widget tier=2 reviewer=fresh model=same "
                  "independence=bundle,non-implementing verdict=pass round=1")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "feat: widget with pass")
    main_before = _git(out, "rev-parse", "main").stdout
    head_before = _git(out, "rev-parse", "HEAD").stdout
    # v2.94 C1: check() runs the gates with the merge target — the open task blocks there,
    # before the archive commit, and the preview says so too
    # (check() names the last lines of the gate run: the red gate, not the finding)
    r = _run(out)
    assert r.returncode == 1 and "FAILED gates: plan-structure" in r.stdout, r.stdout + r.stderr
    r = _run_args(out, "--apply", "--tests", "true")
    assert r.returncode == 1, r.stdout + r.stderr
    assert "gate suite red" in r.stdout and "FAILED gates: plan-structure" in r.stdout, r.stdout
    assert "nothing applied" in r.stdout, r.stdout
    assert _git(out, "rev-parse", "HEAD").stdout == head_before  # no archive commit
    assert (out / PLANS / "2026-07-04-widget.md").is_file()
    assert _git(out, "rev-parse", "main").stdout == main_before  # nothing merged
    assert _git(out, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == "feature"
    assert not [e for e in _reports(out) if e["state"] == "done"]


def _counting_runner(finish, tmp_path, monkeypatch) -> Path:
    """Route finish's gate runs through a wrapper that logs each run's merge target and
    then runs the real runner; returns the log."""
    log = tmp_path / "gate-runs.log"
    wrapper = tmp_path / "count_gates.py"
    real = finish.gate_runner_argv(finish.ROOT)
    wrapper.write_text(
        "import os, subprocess, sys\n"
        f"with open({str(log)!r}, 'a') as f:\n"
        "    f.write(os.environ.get('PROCESS_PUSH_TARGETS', '-') + '\\n')\n"
        f"sys.exit(subprocess.call({real!r}))\n", encoding="utf-8")
    monkeypatch.setattr(finish, "gate_runner_argv", lambda root: [sys.executable, str(wrapper)])
    return log


def _apply_in_process(out, tmp_path, monkeypatch, *, tests):
    finish = _finish_module(out)
    monkeypatch.setattr(finish, "ROOT", out)
    log = _counting_runner(finish, tmp_path, monkeypatch)
    rc = finish.apply(out, tests=tests, tests_passed=False)
    runs = log.read_text().splitlines() if log.is_file() else []
    return rc, runs


def test_apply_reuses_a_green_check_on_the_same_head(render, tmp_path, monkeypatch, capsys):
    """v2.94 B3: without archive and rebase, check() and the local merge judge the same HEAD
    with the same target — the gates run once."""
    out = _repo_on_feature(render, tmp_path / "repo")
    (out / "payload.txt").write_text("done\n", encoding="utf-8")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "feat: payload")
    rc, runs = _apply_in_process(out, tmp_path, monkeypatch, tests="true")
    printed = capsys.readouterr().out
    assert rc == 0, printed
    assert "merged feature into main locally" in printed, printed
    assert runs == ["refs/heads/main"], runs


def test_apply_runs_the_gates_again_on_the_archive_commit(render, tmp_path, monkeypatch, capsys):
    """B3 guard: the archive commit is a new HEAD — the merge gates run there again."""
    out = _repo_without_remote(render, tmp_path / "repo")  # a Tier 1 plan to archive
    rc, runs = _apply_in_process(out, tmp_path, monkeypatch, tests="true")
    printed = capsys.readouterr().out
    assert rc == 0 and "archive plan(s)" in _git(out, "log", "-1", "--format=%s", "main").stdout, printed
    assert runs == ["refs/heads/main", "refs/heads/main"], runs


def test_apply_runs_the_gates_again_on_a_tree_dirtied_before_the_merge(render, tmp_path, monkeypatch,
                                                                      capsys):
    """B3 guard: green on a clean tree says nothing about a tree the suite left dirty."""
    out = _repo_on_feature(render, tmp_path / "repo")
    (out / "payload.txt").write_text("done\n", encoding="utf-8")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "feat: payload")
    rc, runs = _apply_in_process(out, tmp_path, monkeypatch, tests="touch left-by-the-suite.txt")
    printed = capsys.readouterr().out
    assert (out / "left-by-the-suite.txt").is_file()
    assert len(runs) == 2, (runs, printed)
    assert rc == 0, printed


def test_with_the_merge_target_low_tiers_and_the_train_archive_step_stay_green(render, tmp_path):
    """Guard (v2.94 C1): the merge target in check() hardens merge findings only — a Tier 0
    branch, a Tier 1 plan and the train route's archive step (`--apply` without `--tests`)
    stay green, with a remote and without one."""
    tier0 = _repo_on_feature(render, tmp_path / "t0")
    (tier0 / "payload.txt").write_text("done\n", encoding="utf-8")
    _git(tier0, "add", "-A")
    _git(tier0, "commit", "-q", "-m", "feat: payload")
    r = _run(tier0)
    assert r.returncode == 0 and "finish: ready" in r.stdout, r.stdout + r.stderr
    remote, _bare = _repo_with_origin(render, tmp_path / "t1")  # a Tier 1 plan, pushed
    local = _repo_without_remote(render, tmp_path / "t1-local")
    for out in (remote, local):
        r = _run(out)
        assert r.returncode == 0, r.stdout + r.stderr
        r = _run_args(out, "--apply")
        assert r.returncode == 0 and "stopped before the merge" in r.stdout, r.stdout + r.stderr
        assert "archive plan(s) on merge" in _git(out, "log", "-1", "--format=%s").stdout


def test_without_a_remote_the_checkout_holding_main_is_advanced(render, tmp_path):
    main_checkout, wt = _main_checkout_with_feature_worktree(render, tmp_path)
    (wt / "payload.txt").write_text("done\n", encoding="utf-8")
    _git(wt, "add", "-A")
    _git(wt, "commit", "-q", "-m", "feat: payload")
    r = _run_args(wt, "--apply", "--tests", "true")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "locally (the repository has no remote)" in r.stdout
    assert _git(main_checkout, "rev-parse", "HEAD").stdout == _git(wt, "rev-parse", "HEAD").stdout
    assert (main_checkout / "payload.txt").is_file()  # files and ref moved together
    assert _git(wt, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == "feature"  # kept
    assert "git branch -d feature" in r.stdout, r.stdout
    assert _reports(wt)[-1]["state"] == "done"


def test_a_refused_fast_forward_in_the_checkout_holding_main_merges_nothing(render, tmp_path):
    main_checkout, wt = _main_checkout_with_feature_worktree(render, tmp_path)
    (wt / "payload.txt").write_text("done\n", encoding="utf-8")
    _git(wt, "add", "-A")
    _git(wt, "commit", "-q", "-m", "feat: payload")
    (main_checkout / "payload.txt").write_text("in the way\n", encoding="utf-8")  # untracked there
    main_before = _git(main_checkout, "rev-parse", "HEAD").stdout
    r = _run_args(wt, "--apply", "--tests", "true")
    assert r.returncode == 1, r.stdout + r.stderr
    assert _git(main_checkout, "rev-parse", "HEAD").stdout == main_before
    assert "merged feature" not in r.stdout
    assert not [e for e in _reports(wt) if e["state"] == "done"]


def test_a_stale_tracking_ref_without_a_remote_is_refused(render, tmp_path):
    """Without a remote a left-over `origin/main` would anchor the gates on a stale base."""
    out = _repo_without_remote(render, tmp_path)
    _git(out, "update-ref", "refs/remotes/origin/main", "main")
    main_before = _git(out, "rev-parse", "main").stdout
    r = _run(out)
    assert r.returncode == 1 and "git branch -r -d origin/main" in r.stdout, r.stdout
    r = _run_args(out, "--apply", "--tests-passed")
    assert r.returncode == 1 and "nothing applied" in r.stdout, r.stdout
    assert "git branch -r -d origin/main" in r.stdout
    assert _git(out, "rev-parse", "main").stdout == main_before
    assert _git(out, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == "feature"


def test_a_refused_push_with_a_remote_keeps_the_branch(render, tmp_path):
    out, bare = _repo_with_origin(render, tmp_path)
    hook = bare / "hooks/pre-receive"
    hook.write_text("#!/bin/sh\nwhile read old new ref; do\n"
                    "  [ \"$ref\" = refs/heads/main ] && exit 1\n"
                    "done\nexit 0\n")
    hook.chmod(0o755)
    r = _run_args(out, "--apply", "--tests-passed")
    assert r.returncode == 1, r.stdout + r.stderr
    assert _has_branch(out, "feature")
    assert "no remote" not in r.stdout


def test_a_repository_with_another_remote_stays_on_the_push_path(render, tmp_path):
    """Only `upstream`: no silent local merge — the push to origin fails as today."""
    out = _repo_without_remote(render, tmp_path)
    bare = tmp_path / "upstream.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    _git(out, "remote", "add", "upstream", str(bare))
    r = _run_args(out, "--apply", "--tests-passed")
    assert r.returncode == 1, r.stdout + r.stderr
    assert "no remote" not in r.stdout
    assert _has_branch(out, "feature")


def test_tests_passed_without_a_remote_is_refused_before_anything_merges(render, tmp_path):
    """Fix round 1: without a remote no pre-push runs the suite, so the claim is never checked
    — a stack whose full suite is red merged on `--tests-passed`. `--tests <command>` runs it."""
    out = _repo_without_remote(render, tmp_path)
    (out / "suite.sh").write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")  # the red full suite
    (out / "suite.sh").chmod(0o755)
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "test: a red suite")
    head, main_before = _git(out, "rev-parse", "HEAD").stdout, _git(out, "rev-parse", "main").stdout
    r = _run_args(out, "--apply", "--tests-passed")
    assert r.returncode == 1, r.stdout + r.stderr
    assert "without a remote no pre-push runs the suite: pass --tests <command>" in r.stdout, r.stdout
    assert "nothing applied" in r.stdout
    assert _git(out, "rev-parse", "HEAD").stdout == head  # not even the archive commit
    assert _git(out, "rev-parse", "main").stdout == main_before
    assert _git(out, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == "feature"
    assert not [e for e in _reports(out) if e["state"] == "done"]
    r = _run_args(out, "--apply", "--tests", "./suite.sh")
    assert r.returncode == 1 and "full suite red — not merging" in r.stdout, r.stdout + r.stderr
    assert _git(out, "rev-parse", "main").stdout == main_before


def test_an_unreadable_tracking_ref_list_without_a_remote_is_a_blocker(render, tmp_path):
    """Fix round 1: a failing `git for-each-ref` read as "no tracking refs" — never "none"."""
    import shutil
    out = _repo_without_remote(render, tmp_path / "work")
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "git").write_text(
        "#!/bin/sh\ncase \"$*\" in *for-each-ref*refs/remotes/*) "
        "echo 'fatal: bad ref store' >&2; exit 128;; esac\n"
        f'exec "{shutil.which("git")}" "$@"\n', encoding="utf-8")
    (bindir / "git").chmod(0o755)
    env = {**os.environ, "PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}"}
    main_before = _git(out, "rev-parse", "main").stdout
    for args in ((), ("--apply", "--tests", "true")):
        r = subprocess.run([sys.executable, str(out / "scripts/process/finish.py"), *args, "."],
                           cwd=out, capture_output=True, text=True, env=env)
        assert r.returncode == 1, (args, r.stdout + r.stderr)
        assert "could not list remote-tracking refs" in r.stdout, (args, r.stdout)
    assert _git(out, "rev-parse", "main").stdout == main_before


# --- v2.94 E2: the cost commit before the archive commit ---------------------------------

COST_SUBJECT = "docs: record cost — #7"


def _phase_record(out: Path, issue: int, branch: str, t0: int) -> None:
    """The phase history dispatch writes: one window, a plan start and an execute start."""
    import json
    phases = _common_dir(out) / "process-dispatch/phases"
    phases.mkdir(parents=True, exist_ok=True)
    (phases / f"{issue}.json").write_text(json.dumps({"phase": "execute", "branch": branch, "branches": {
        branch: {"windows": [[t0, None]], "worktrees": [], "remote": False,
                 "starts": [["plan", t0], ["execute", t0 + 100]]}}}))


def _costed_repo(render, tmp_path, *, branch="7-widget", telemetry=True, record=True, plan=True):
    """A Tier 1 plan and a payload on a numbered branch, its phase history written."""
    import time
    out = render(tmp_path, {"project_name": "demo", "modules": {"telemetry": telemetry}})
    _git(out, "init", "-q", "-b", "main")
    _git(out, "config", "user.email", "t@example.com")
    _git(out, "config", "user.name", "Test")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "base")
    _git(out, "checkout", "-q", "-b", branch)
    if plan:
        _active_plan(out, "2026-09-07-tiny.md", "# Plan\n\ntier: 1\n")
    (out / "payload.txt").write_text("done\n", encoding="utf-8")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "feat: tiny")
    if record:
        _phase_record(out, 7, branch, int(time.time()) - 1000)
    return out


def _journal_costs(out: Path) -> list[str]:
    return [ln for f in sorted((out / JOURNAL).rglob("*.md"))
            for ln in f.read_text(encoding="utf-8").splitlines() if ln.startswith("COST ")]


def _subjects(out: Path, rev: str = "HEAD") -> list[str]:
    return _git(out, "log", "--format=%s", rev).stdout.splitlines()


def _modules(out: Path, *names: str):
    """Import the rendered repo's own modules, freshly; the caller pops them."""
    import importlib
    shared = ("attest", "attest_evidence", "check_review", "check_fix_streak", "dispatch", "report",
              "process_git", "required_records", "process_kpis", "tower")
    for name in shared:
        sys.modules.pop(name, None)
    sys.path.insert(0, str(out / "scripts/process"))
    return [importlib.import_module(n) for n in names], shared


def _drop_modules(out: Path, shared) -> None:
    sys.path.remove(str(out / "scripts/process"))
    for name in shared:
        sys.modules.pop(name, None)


def _cost_hook(out: Path, refuse: str) -> Path:
    """A commit-msg hook that refuses a commit whose message carries `refuse`."""
    hook = _common_dir(out) / "hooks/commit-msg"
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text(f'#!/bin/sh\ngrep -q "{refuse}" "$1" && exit 1\nexit 0\n')
    hook.chmod(0o755)
    return hook


def test_apply_writes_the_cost_commit_right_before_a_pure_archive_commit(render, tmp_path):
    """One COST line per phase, wall time from the phase history, `not-measured` where no
    transcripts are configured — never a 0; the archive commit stays the last and pure."""
    import datetime as dt
    import re
    out = _costed_repo(render, tmp_path)
    r = _run_args(out, "--apply")
    assert r.returncode == 0 and "stopped before the merge" in r.stdout, r.stdout + r.stderr
    subjects = _subjects(out)
    assert subjects[:3] == ["docs: archive plan(s) on merge — 2026-09-07-tiny.md", COST_SUBJECT,
                            "feat: tiny"], subjects
    shard = f".process-work/journal/issue-7/{dt.date.today().isoformat()}.md"
    assert _git(out, "show", "--format=", "--name-only", "HEAD~1").stdout.split() == [shard]
    lines = (out / shard).read_text(encoding="utf-8").split("\n")
    costs = [ln for ln in lines if ln.startswith("COST ")]
    assert costs[0] == "COST work=7 phase=plan wall_seconds=100 tokens=- not-measured: not-configured", costs
    assert re.fullmatch(r"COST work=7 phase=execute wall_seconds=\d{3,} tokens=- not-measured: "
                        r"not-configured", costs[1]), costs
    assert len(costs) == 2 and "tokens=0" not in "\n".join(costs)
    (attest,), shared = _modules(out, "attest")
    try:
        head, cost_commit, payload = (_git(out, "rev-parse", f"HEAD~{n}").stdout.strip() for n in range(3))
        assert attest._archive_only(out, cost_commit, head)
        assert attest._cost_only(out, payload, cost_commit)
    finally:
        _drop_modules(out, shared)


def test_a_second_apply_after_an_abort_writes_no_second_cost_commit(render, tmp_path):
    """Idempotent by content: an abort between the cost commit and the archive commit leaves
    the COST lines in the branch's range, and the next `--apply` writes none again."""
    out = _costed_repo(render, tmp_path)
    hook = _cost_hook(out, "archive plan")
    r = _run_args(out, "--apply")
    assert r.returncode == 1 and "archive commit failed" in r.stderr, r.stdout + r.stderr
    assert _subjects(out)[:2] == [COST_SUBJECT, "feat: tiny"]
    hook.unlink()
    r = _run_args(out, "--apply")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "already recorded" in r.stdout, r.stdout
    subjects = _subjects(out)
    assert subjects[:2] == ["docs: archive plan(s) on merge — 2026-09-07-tiny.md", COST_SUBJECT], subjects
    assert subjects.count(COST_SUBJECT) == 1


def test_a_quoted_cost_line_in_the_journal_does_not_count_as_recorded(render, tmp_path):
    """v2.94 code review: a COST line inside a fenced block is a quotation, as for every record
    reader — it neither suppresses the real cost commit nor counts as a measurement."""
    import datetime as dt
    out = _costed_repo(render, tmp_path)
    shard = out / f".process-work/journal/issue-7/{dt.date.today().isoformat()}.md"
    shard.parent.mkdir(parents=True, exist_ok=True)
    shard.write_text("# notes\n\n```\nCOST work=7 phase=plan wall_seconds=1 tokens=1\n```\n",
                     encoding="utf-8")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "docs: journal note")
    r = _run_args(out, "--apply")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "already recorded" not in r.stdout, r.stdout
    assert COST_SUBJECT in _subjects(out), _subjects(out)
    (kpis,), shared = _modules(out, "process_kpis")
    try:
        phases = [c["phase"] for c in kpis.recorded_costs(out)[7]]
        assert phases == ["plan", "execute"], phases  # the real set, not the quoted line
        assert all(c["wall_seconds"] != 1 for c in kpis.recorded_costs(out)[7])
    finally:
        _drop_modules(out, shared)


@pytest.mark.parametrize("case", ["no-record", "no-issue", "no-telemetry", "no-plan"])
def test_no_cost_commit_without_a_phase_record_an_issue_the_module_or_an_archive(render, tmp_path, case):
    """No dispatch chain, no issue in the branch name, no telemetry module, or no plan to
    archive (the cost commit rides only the run that writes the archive commit): no line."""
    out = _costed_repo(render, tmp_path, record=case != "no-record",
                       branch="feature" if case == "no-issue" else "7-widget",
                       telemetry=case != "no-telemetry", plan=case != "no-plan")
    r = _run_args(out, "--apply")
    assert r.returncode == 0, r.stdout + r.stderr
    assert COST_SUBJECT not in _subjects(out) and "record cost" not in r.stdout
    assert not _journal_costs(out)


def test_the_docs_name_the_cost_commit_its_place_and_when_there_is_none(render, tmp_path):
    out = render(tmp_path, {"project_name": "demo", "harnesses": {"claude": True},
                            "modules": {"telemetry": True}})
    for rel in (".claude/commands/finish.md", "docs/process/commits.md",
                "docs/process/journal-state-plans.md", "docs/process/modules/telemetry.md"):
        text = " ".join((out / rel).read_text(encoding="utf-8").split())
        assert "docs: record cost — #<issue>" in text, rel
        at = text.index("docs: record cost")
        assert "before" in text[at - 300:at + 300] and "archive commit" in text, rel  # its place
        assert "including waits" in text or "waits included" in text, rel
        assert "without a dispatch record or" in text and "issue in its branch name" in text, rel


def test_a_failing_cost_commit_does_not_stop_the_merge_and_the_archive_stays_pure(render, tmp_path):
    """The cost commit is refused: the journal shard is restored before `git mv`, nothing of it
    rides into the archive commit, and the merge goes on."""
    out = _costed_repo(render, tmp_path)
    _cost_hook(out, "record cost")
    r = _run_args(out, "--apply", "--tests", "true")  # no remote: the local merge
    assert r.returncode == 0, r.stdout + r.stderr
    assert "cost commit failed" in r.stderr, r.stderr
    assert "merged 7-widget into main locally" in r.stdout, r.stdout
    assert _subjects(out, "main")[:2] == ["docs: archive plan(s) on merge — 2026-09-07-tiny.md", "feat: tiny"]
    assert not _journal_costs(out)
    assert _git(out, "status", "--porcelain").stdout == ""
    (attest,), shared = _modules(out, "attest")
    try:
        assert attest._archive_only(out, "main~1", "main")
    finally:
        _drop_modules(out, shared)


def test_merge_events_count_the_cost_commit_in_its_own_finish_event(render, tmp_path):
    """The cost commit lies before the archive commit that ends a `finish` event: it is one of
    that event's own commits and process lines, and none of the next event's."""
    out = render(tmp_path, {"project_name": "demo", "modules": {"telemetry": True}})
    _git(out, "init", "-q", "-b", "main")
    _git(out, "config", "user.email", "t@example.com")
    _git(out, "config", "user.name", "Test")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "base")
    _git(out, "checkout", "-q", "-b", "prep")
    (out / "prep.txt").write_text("prep\n", encoding="utf-8")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "feat: prep")
    _git(out, "checkout", "-q", "main")
    _git(out, "merge", "-q", "--no-ff", "-m", "train: merge prep", "prep")  # an event below: a bound
    for issue, branch in ((7, "7-widget"), (8, "8-gizmo")):
        _git(out, "checkout", "-q", "-b", branch)
        _active_plan(out, f"2026-09-0{issue}-{branch}.md", f"# Plan\n\ntier: 1\nissue: #{issue}\n")
        (out / f"{branch}.txt").write_text("done\n", encoding="utf-8")
        _git(out, "add", "-A")
        _git(out, "commit", "-q", "-m", f"feat: {branch} (#{issue})")
        if issue == 7:
            _phase_record(out, 7, branch, 1_800_000_000)
        r = _run_args(out, "--apply", "--tests", "true")
        assert r.returncode == 0, r.stdout + r.stderr
    cost = next(s for s, subj in (ln.split(" ", 1) for ln in
                                 _git(out, "log", "--format=%H %s", "main").stdout.splitlines())
                if subj == COST_SUBJECT)
    (kpis,), shared = _modules(out, "process_kpis")
    try:
        events = kpis.merge_events(out, "main")["events"]
    finally:
        _drop_modules(out, shared)
    assert [e["kind"] for e in events] == ["train", "finish", "finish"], events
    seven, eight = events[1], events[2]
    assert seven["issues"] == [7] and eight["issues"] == [8]
    assert cost in seven["commits"] and cost not in eight["commits"]
    shard = next(f for f in seven["process_files"] if f.startswith(JOURNAL + "/issue-7/"))
    # the archived plan's four lines and the two COST lines; the next event carries only its plan
    assert (seven["process_lines"], eight["process_lines"]) == (4 + 2, 4), (seven, eight)
    assert shard not in eight["process_files"]
    assert not seven["mixed"]


# --- v2.97 B7: `finish --tests` holds the lane `full` ---------------------------------------

def _lane_config(out: Path, *, full_wait: float = 60, own_script: bool = False) -> None:
    import json
    (out / "docs/process/testing.local.json").write_text(json.dumps(
        {"lanes": {"scoped": {"wait": 5}, "full": {"wait": full_wait}}}))
    if own_script:
        (out / "scripts/lane.py").write_text("print('scoped: free')\nprint('full: free')\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "lanes")
    _git(out, "push", "-q", "origin", "HEAD")


def _hold_full(out: Path, seconds: float, label: str = "other-holder"):
    """A process outside finish that holds `full` for `seconds`."""
    import time
    code = f"import time; time.sleep({seconds!r})"
    lanes = Path(os.environ["PROCESS_LANE_DIR"])
    holder = subprocess.Popen([sys.executable, str(out / "scripts/process/lane.py"), "run", "--lane", "full",
                               "--label", label, "--no-nice", "--", sys.executable, "-c", code], cwd=out,
                              env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    for _ in range(200):
        if (lanes / "test-lane-full.status").exists():
            return holder
        time.sleep(0.05)
    holder.kill()
    raise AssertionError("the holder never took the lane")


def _suite_script(tmp_path: Path) -> tuple[str, Path]:
    """A `--tests` command that writes when it started, what `lane.py status` says while it
    runs, and the exit of `lane.py run --lane full --wait 0` inside it — a project's suite
    that queues on the lane itself."""
    seen = tmp_path / "seen"
    script = tmp_path / "suite.py"
    script.write_text(
        "import subprocess, sys, time\n"
        "started = time.time()\n"
        "status = subprocess.run([sys.executable, 'scripts/process/lane.py', 'status'],\n"
        "                        capture_output=True, text=True).stdout\n"
        "nested = subprocess.run([sys.executable, 'scripts/process/lane.py', 'run', '--lane', 'full',\n"
        "                         '--wait', '0', '--', sys.executable, '-c', 'pass']).returncode\n"
        f"open({str(seen)!r}, 'w').write(f'{{started!r}}\\n{{nested}}\\n{{status}}')\n"
        "sys.exit(nested)\n")
    return f"{sys.executable} {script}", seen


def test_finish_tests_holds_full_and_the_suites_own_lane_call_runs_through(render, tmp_path):
    """B7: the suite runs under `full`, held by finish; `lane.py run --lane full` inside it
    passes through (`PROCESS_LANE_HELD`), it does not wait for its own parent."""
    out, bare = _repo_with_origin(render, tmp_path)
    _lane_config(out)
    cmd, seen = _suite_script(tmp_path)
    r = _run_args(out, "--apply", "--tests", cmd)
    assert r.returncode == 0, r.stdout + r.stderr
    _started, nested, status = seen.read_text().split("\n", 2)
    assert nested == "0", status
    assert "full: held by" in status and "finish --tests" in status, status
    assert "payload.txt" in subprocess.run(["git", "ls-tree", "-r", "--name-only", "main"], cwd=bare,
                                           capture_output=True, text=True, check=True).stdout
    assert "full: free" in subprocess.run([sys.executable, str(out / "scripts/process/lane.py"), "status"],
                                          cwd=out, capture_output=True, text=True).stdout


def test_two_finish_runs_serialise_on_full(render, tmp_path):
    """B7: a second heavy run on the host waits for the first to let go of `full`."""
    import time
    out, _bare = _repo_with_origin(render, tmp_path)
    _lane_config(out)
    cmd, seen = _suite_script(tmp_path)
    holder = _hold_full(out, 120.0)
    said = tmp_path / "finish.err"
    with said.open("w") as err:
        finish = subprocess.Popen([sys.executable, str(out / "scripts/process/finish.py"), "--apply", "--tests",
                                   cmd, "."], cwd=out, stdout=subprocess.DEVNULL, stderr=err, text=True)
    try:
        # until finish queues on the lane — or, holding none, has run its suite and ended
        while finish.poll() is None and "waiting" not in said.read_text():
            time.sleep(0.05)
    finally:
        holder.kill()
        holder.wait()
    released = time.time()
    assert finish.wait(timeout=120) == 0, said.read_text()
    started = float(seen.read_text().split("\n", 1)[0])
    assert started >= released, (started, released)


def test_finish_on_a_held_full_lane_exits_75_and_merges_nothing(render, tmp_path):
    """B7: past the lane's wait budget, exit 75 naming the holder; the suite never ran,
    origin's main is where it was, the branch stays."""
    out, bare = _repo_with_origin(render, tmp_path)
    _lane_config(out, full_wait=1)
    main_before = _git(bare, "rev-parse", "main").stdout
    cmd, seen = _suite_script(tmp_path)
    holder = _hold_full(out, 30.0)
    try:
        r = _run_args(out, "--apply", "--tests", cmd)
    finally:
        holder.kill()
        holder.wait()
    assert r.returncode == 75, r.stdout + r.stderr
    said = r.stdout + r.stderr
    assert "other-holder" in said and "nothing merged" in said, said
    assert not seen.exists()
    assert _git(bare, "rev-parse", "main").stdout == main_before
    assert _git(bare, "rev-parse", "--verify", "feature").returncode == 0


def test_finish_with_the_projects_own_lane_script_holds_nothing(render, tmp_path):
    """B7: a project that kept its own `scripts/lane.py` holds its lanes itself — finish
    takes no lock first, as `test_select.run`: a held template lane does not stop it."""
    out, _bare = _repo_with_origin(render, tmp_path)
    _lane_config(out, full_wait=1, own_script=True)
    holder = _hold_full(out, 30.0)
    try:
        r = _run_args(out, "--apply", "--tests", "true")
    finally:
        holder.kill()
        holder.wait()
    assert r.returncode == 0, r.stdout + r.stderr
    assert "merged feature into main" in r.stdout, r.stdout
