import json
import os
import re
import subprocess
import sys
import time

import pytest
from pathlib import Path


def _git(root: Path, *args: str):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True)


def _train(out: Path, *args: str):
    return subprocess.run([sys.executable, str(out / "scripts/process/train.py"), *args],
                          cwd=out, capture_output=True, text=True)


def _repo(out: Path) -> None:
    _git(out, "init", "-q", "-b", "main")
    _git(out, "config", "user.email", "t@t")
    _git(out, "config", "user.name", "t")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "base")


def _branch(out: Path, name: str, files: dict[str, str], *, tier: int = 2, reviewed: bool = True,
            archive: bool = True, delete: tuple[str, ...] = (), start: str = "main") -> None:
    _git(out, "checkout", "-q", "-b", name, start)
    for rel, text in files.items():
        p = out / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    for rel in delete:
        (out / rel).unlink()
    if archive:
        a = out / ".process-work/plans/archive"
        a.mkdir(parents=True, exist_ok=True)
        (a / f"2026-09-20-{name}.md").write_text(f"# {name}\n\ntier: {tier}\nissue: #1\n\n## Decisions\n")
    if reviewed:
        j = out / ".process-work/journal"
        j.mkdir(parents=True, exist_ok=True)
        (j / f"2026-09-20-{name}.md").write_text(
            f"REVIEW work={name} tier={tier} reviewer=fresh model=cross "
            f"independence=bundle,non-implementing verdict=pass round=1\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", f"feat: {name}")
    _git(out, "checkout", "-q", "main")


def test_plan_boards_cleared_branches_and_explains_the_rest(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    _branch(out, "beta", {"src/b.py": "b\n"}, reviewed=False)                 # no pass
    _branch(out, "gamma", {"src/a.py": "conflict\n", "src/g.py": "g\n"})       # shares a file: boards too
    _branch(out, "delta", {"src/d.py": "d\n"}, archive=False, reviewed=False)  # not finished
    _branch(out, "tiny", {"README.md": "tiny\n"}, tier=1, reviewed=False)      # tier 1 needs no pass
    r = _train(out, "plan", "--json")
    assert r.returncode == 0, r.stderr
    p = json.loads(r.stdout)
    by = {c["branch"]: c for c in p["candidates"]}
    assert by["alpha"]["eligible"] and "REVIEW pass" in by["alpha"]["by"]
    assert not by["beta"]["eligible"] and "without a REVIEW pass covering the branch head" in by["beta"]["reasons"][0]
    assert by["gamma"]["eligible"]  # a shared file is git's to merge, not a reason to wait
    assert not by["delta"]["eligible"] and "run /finish first" in by["delta"]["reasons"][0]
    assert by["tiny"]["eligible"]
    assert p["ready"] is True  # alpha, gamma, tiny: 3 aboard
    text = _train(out, "plan").stdout
    assert "✓ alpha" in text and "· beta" in text and "READY" in text
    # a worker report is only the pointer: without a REVIEW pass it boards nothing
    subprocess.run([sys.executable, str(out / "scripts/process/report.py"), "review-pass", "--worker", "delta"],
                   cwd=out, check=True, capture_output=True)
    p2 = json.loads(_train(out, "plan", "--json").stdout)
    delta = next(c for c in p2["candidates"] if c["branch"] == "delta")
    assert not delta["eligible"] and "no REVIEW pass for its own work covers the branch head" in delta["reasons"][0]
    # with the pass on the branch, the report points at a real record
    _git(out, "checkout", "-q", "delta")
    j = out / ".process-work/journal"
    j.mkdir(parents=True, exist_ok=True)
    (j / "2026-09-20-delta.md").write_text(
        "REVIEW work=delta tier=2 reviewer=fresh model=cross independence=bundle,non-implementing verdict=pass round=1\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "attest delta")
    _git(out, "checkout", "-q", "main")
    p3 = json.loads(_train(out, "plan", "--json").stdout)
    delta = next(c for c in p3["candidates"] if c["branch"] == "delta")
    assert delta["eligible"] and "worker report review-pass" in delta["by"]
    # a `done` report never substitutes a missing pass on an archived plan
    subprocess.run([sys.executable, str(out / "scripts/process/report.py"), "done", "--worker", "beta"],
                   cwd=out, check=True, capture_output=True)
    p4 = json.loads(_train(out, "plan", "--json").stdout)
    beta = next(c for c in p4["candidates"] if c["branch"] == "beta")
    assert not beta["eligible"] and "covering the branch head" in beta["reasons"][0]
    assert p4["ready"] is True  # three aboard now


def test_open_question_keeps_a_branch_off_the_train(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _branch(out, "asked", {"src/q.py": "q\n"})
    _git(out, "checkout", "-q", "asked")
    a = out / ".process-work/plans/archive/2026-09-20-asked.md"
    a.write_text(a.read_text() + "- DECISION NEEDED 2026-09-21 asked: drop the flag? — options: A, B; recommendation: B\n")
    _git(out, "commit", "-q", "-am", "question")
    _git(out, "checkout", "-q", "main")
    by = {c["branch"]: c for c in json.loads(_train(out, "plan", "--json").stdout)["candidates"]}
    assert not by["asked"]["eligible"] and "open DECISION NEEDED" in by["asked"]["reasons"][0]
    # #235: the refusal quotes the line and names both answer forms
    reason = by["asked"]["reasons"][0]
    assert "drop the flag?" in reason and "`(answered <date>)`" in reason and "`DECISION <date> <who>: …`" in reason
    _git(out, "checkout", "-q", "asked")
    a.write_text(a.read_text().replace("DECISION NEEDED 2026-09-21 asked: drop", "DECISION 2026-09-21 owner: drop"))
    _git(out, "commit", "-q", "-am", "answered")
    _git(out, "checkout", "-q", "main")
    by = {c["branch"]: c for c in json.loads(_train(out, "plan", "--json").stdout)["candidates"]}
    assert by["asked"]["eligible"]


def test_who_or_why_in_parentheses_is_no_answer_marker(render, tmp_path):
    # refutation: `(decided by owner)` names who decides — the question is still open
    import importlib.util
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    spec = importlib.util.spec_from_file_location("cr", out / "scripts/process/check_review.py")
    cr = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cr)
    for still_open in ("DECISION NEEDED 2026-09-22 api (decided by owner): keep the export? — options: A, B",
                       "DECISION NEEDED 2026-09-22 api (entschieden durch Seb): Export behalten?",
                       "DECISION NEEDED 2026-09-22 api: (resolved vs. pending) which state wins?"):
        assert len(cr.open_questions(still_open + "\n")) == 1, still_open
    for answered in ("DECISION NEEDED 2026-09-22 api (answered): keep it?",
                     "DECISION NEEDED 2026-09-22 api (beantwortet, s. u.): behalten?",
                     "DECISION NEEDED 2026-09-22 api (answered 2026-09-23): keep it?"):
        assert cr.open_questions(answered + "\n") == [], answered


@pytest.mark.parametrize("marked", [    "DECISION NEEDED 2026-09-21 asked (beantwortet, s. u.): drop the flag? — options: A, B",
    "DECISION NEEDED (answered below) 2026-09-21 asked: drop the flag? — options: A, B",
    "DECISION NEEDED 2026-09-21 asked: (answered) drop the flag? — options: A, B",
    "~~DECISION NEEDED 2026-09-21 asked: drop the flag? — options: A, B~~",
])
def test_a_question_marked_answered_in_place_rides_the_train(render, tmp_path, marked):
    """Downstream: workers kept answered questions in place, marked `(beantwortet)`;
    behind the date the marker still read as open, and finished branches would
    have dropped out of the train over where a word stood."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _branch(out, "asked", {"src/q.py": "q\n"})
    _git(out, "checkout", "-q", "asked")
    a = out / ".process-work/plans/archive/2026-09-20-asked.md"
    a.write_text(a.read_text() + f"- {marked}\n- DECISION 2026-09-21 owner: drop it\n")
    _git(out, "commit", "-q", "-am", "answered in place")
    _git(out, "checkout", "-q", "main")
    by = {c["branch"]: c for c in json.loads(_train(out, "plan", "--json").stdout)["candidates"]}
    assert by["asked"]["eligible"], by["asked"]["reasons"]


def test_run_merges_the_batch_behind_one_suite_and_drops_the_offender(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    _branch(out, "beta", {"src/b.py": "b\n"})
    _branch(out, "bad", {"src/BROKEN": "x\n"})
    marker = out.parent / "deployed"
    # the suite fails only when the offender's file is present; count the runs
    suite = f"test ! -e src/BROKEN && echo run >> {out.parent}/suite.log"
    r = _train(out, "run", "--force", "--suite", suite, "--deploy", f"touch {marker}")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "dropping it and rebuilding" in r.stdout and "bad" in r.stdout
    assert "main →" in r.stdout and "alpha, beta" in r.stdout
    log = _git(out, "log", "--oneline", "main").stdout
    assert "train: merge alpha" in log and "train: merge beta" in log and "merge bad" not in log
    assert (out / "src/a.py").is_file() and (out / "src/b.py").is_file() and not (out / "src/BROKEN").exists()
    # green runs: the base check (nobody aboard), one bisection probe ([alpha]),
    # one for the surviving batch — never one per branch
    assert (out.parent / "suite.log").read_text().count("run") == 3
    assert marker.exists()
    # the offender search is filed under bisect, not under the suite
    row = [json.loads(line) for line in (out / ".git/process-train/phases.jsonl").read_text().splitlines()][-1]
    assert row["result"] == "green" and row["bisect"] > 0
    # what ties a deploy to its issues (process_kpis.py flow): who landed, deployed, when
    assert sorted(row["branches"]) == ["alpha", "beta"] and row["deployed"] is True and row["ended"]
    branches = _git(out, "branch", "--list", "--format=%(refname:short)").stdout.split()
    assert "alpha" not in branches and "beta" not in branches and "bad" in branches
    assert not [b for b in branches if b.startswith("train/")]
    reports = subprocess.run([sys.executable, str(out / "scripts/process/tower.py"), "--json"],
                             cwd=out, capture_output=True, text=True).stdout
    t = json.loads(reports)
    states = {x["worker"]: x["state"] for x in t["reports"]}
    assert states["alpha"] == "done" and states["beta"] == "done" and states["bad"] == "blocked"


def test_run_refuses_a_dirty_or_wrong_root(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    (out / "dirty.txt").write_text("x")
    r = _train(out, "run", "--force")
    assert r.returncode == 2 and "not clean" in r.stderr
    (out / "dirty.txt").unlink()
    _git(out, "checkout", "-q", "-b", "elsewhere")
    r = _train(out, "run", "--force")
    assert r.returncode == 2 and "run from the root worktree on main" in r.stderr


def test_run_holds_without_departure_and_dry_run_touches_nothing(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    r = _train(out, "run", "--suite", "true")
    assert r.returncode == 0 and "holding" in r.stdout
    head = _git(out, "rev-parse", "main").stdout
    r = _train(out, "run", "--force", "--dry-run", "--suite", "true")
    assert "dry run" in r.stdout and _git(out, "rev-parse", "main").stdout == head


def test_run_without_suite_says_the_batch_merges_untested(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    r = _train(out, "run", "--force", "--dry-run")
    assert "no --suite" in r.stderr
    r = _train(out, "run", "--force", "--dry-run", "--suite", "true")
    assert "no --suite" not in r.stderr

def _main_commit(out: Path, files: dict[str, str], msg: str) -> None:
    for rel, text in files.items():
        f = out / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text)
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", msg)


def test_archiving_other_works_cleared_plans_is_no_clearance(render, tmp_path):
    # a template-update branch archived older,
    # already cleared plans and boarded on them while its own review ran
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    plans = {f".process-work/plans/2026-09-1{i}-old-{i}.md": f"# old {i}\n\ntier: 2\nissue: #{i}\n" for i in (1, 2)}
    passes = "".join(f"REVIEW work=2026-09-1{i}-old-{i} tier=2 reviewer=fresh model=cross "
                     "independence=bundle,non-implementing verdict=pass round=1\n" for i in (1, 2))
    _main_commit(out, {**plans, ".process-work/journal/2026-09-19-old.md": passes}, "older work, cleared")
    _git(out, "checkout", "-q", "-b", "claude/process-v2.28.0")
    (out / ".process-work/plans/archive").mkdir(parents=True, exist_ok=True)
    for rel in plans:
        _git(out, "mv", rel, rel.replace("plans/", "plans/archive/"))
    _main_commit(out, {"scripts/process/new_gate.py": "x = 1\n"}, "update the process")
    _git(out, "checkout", "-q", "main")
    _git(out, "checkout", "-q", "-b", "tidy-plans")
    for rel in plans:
        _git(out, "mv", rel, rel.replace("plans/", "plans/archive/"))
    _main_commit(out, {"docs/x.md": "x\n"}, "archive only")
    _git(out, "checkout", "-q", "main")
    by = {c["branch"]: c for c in json.loads(_train(out, "plan", "--json").stdout)["candidates"]}
    upd = by["claude/process-v2.28.0"]
    assert not upd["eligible"] and upd["plans"] == [] and len(upd["housekeeping"]) == 2
    assert "gates' code (scripts/process/new_gate.py)" in upd["reasons"][0]
    tidy = by["tidy-plans"]
    assert not tidy["eligible"] and "of other work only" in tidy["reasons"][0]


def test_gate_code_boards_only_on_its_own_review_pass(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    # a Tier 1 plan needs no pass — unless the branch changes the gates' code
    _branch(out, "gatefix", {"scripts/process/g.py": "g\n"}, tier=1, reviewed=False)
    # the plan was written on main (by the steward); the branch archives it —
    # still its own, because the issue number names the branch
    _main_commit(out, {".process-work/plans/2026-09-20-login.md": "# login\n\ntier: 2\nissue: #42\n"}, "plan")
    _git(out, "checkout", "-q", "-b", "42-fix-login")
    _git(out, "mv", ".process-work/plans/2026-09-20-login.md", ".process-work/plans/archive/2026-09-20-login.md")
    _main_commit(out, {"src/login.py": "l\n", ".process-work/journal/2026-09-21-login.md":
                       "REVIEW work=42 tier=2 reviewer=fresh model=cross independence=bundle,non-implementing "
                       "verdict=pass round=1\n"}, "login")
    _git(out, "checkout", "-q", "main")
    by = {c["branch"]: c for c in json.loads(_train(out, "plan", "--json").stdout)["candidates"]}
    assert not by["gatefix"]["eligible"] and "without a REVIEW pass at tier 2 or higher" in by["gatefix"]["reasons"][0]
    assert by["42-fix-login"]["eligible"], by["42-fix-login"]
    _git(out, "checkout", "-q", "gatefix")
    _main_commit(out, {".process-work/journal/2026-09-21-gatefix.md":
                       "REVIEW work=gatefix tier=2 reviewer=fresh model=cross independence=bundle,non-implementing "
                       "verdict=pass round=1\n"}, "review")
    _git(out, "checkout", "-q", "main")
    by = {c["branch"]: c for c in json.loads(_train(out, "plan", "--json").stdout)["candidates"]}
    assert by["gatefix"]["eligible"], by["gatefix"]

def test_core_files_present(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    assert (out / "scripts/process/train.py").is_file()
    assert (out / ".claude/commands/steward.md").is_file()
    assert (out / "docs/process/train.md").is_file()


def test_rejected_push_leaves_local_main_untouched_and_keeps_the_train(render, tmp_path):
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    _repo(out)
    bare = tmp_path / "origin.git"
    _git(out, "clone", "-q", "--bare", str(out), str(bare))
    _git(out, "remote", "add", "origin", str(bare))
    _git(out, "fetch", "-q", "origin")
    _git(out, "branch", "-q", "--set-upstream-to=origin/main", "main")
    _branch(out, "alpha", {"src/a.py": "a\n"})
    _git(out, "push", "-q", "origin", "alpha")
    hook = bare / "hooks/pre-receive"
    hook.write_text("#!/bin/sh\nwhile read old new ref; do [ \"$ref\" = refs/heads/main ] && { echo 'protected'; exit 1; }; done; exit 0\n")
    hook.chmod(0o755)
    head = _git(out, "rev-parse", "main").stdout
    r = _train(out, "run", "--force", "--push", "--suite", "true")
    assert r.returncode == 1 and "origin rejected it" in r.stderr
    assert _git(out, "rev-parse", "main").stdout == head  # local main untouched
    branches = _git(out, "branch", "--list", "--format=%(refname:short)").stdout.split()
    assert "alpha" in branches and any(b.startswith("train/") for b in branches)
    assert not (out.parent / f"{out.name}-train").exists()
    assert not (out / ".git/process-train/worktree").exists()  # never under .git: tools skip that segment
    assert list((out / ".git/process-train").glob("*.log"))


def test_a_same_named_old_pass_on_main_does_not_clear_a_new_plan(render, tmp_path):
    # the review gate's uniqueness rule for de-dated slugs, mirrored: an old
    # archived `login` plan + its pass on main must not clear `2026-09-20-login`
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    a = out / ".process-work/plans/archive"
    a.mkdir(parents=True, exist_ok=True)
    (a / "2026-01-05-login.md").write_text("# old\n\ntier: 3\n")
    j = out / ".process-work/journal"
    j.mkdir(parents=True, exist_ok=True)
    (j / "2026-01-05.md").write_text("REVIEW work=login tier=3 reviewer=fresh model=cross "
                                     "independence=bundle,non-implementing verdict=pass round=1\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "history")
    _branch(out, "login", {"src/l.py": "l\n"}, tier=3, reviewed=False)
    p = json.loads(_train(out, "plan", "--json").stdout)
    c = next(c for c in p["candidates"] if c["branch"] == "login")
    assert not c["eligible"] and "without a REVIEW pass covering the branch head" in c["reasons"][0]


def test_fenced_tier_example_is_not_a_declaration(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _git(out, "checkout", "-q", "-b", "tricky", "main")
    a = out / ".process-work/plans/archive"
    a.mkdir(parents=True, exist_ok=True)
    (a / "2026-09-20-tricky.md").write_text("# P\n\n```\ntier: 1\n```\n\n- **Tier:** 3\nissue: #1\n")
    (out / "src.py").write_text("x\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "feat: tricky")
    _git(out, "checkout", "-q", "main")
    p = json.loads(_train(out, "plan", "--json").stdout)
    c = next(c for c in p["candidates"] if c["branch"] == "tricky")
    assert not c["eligible"] and c["plans"][0]["tier"] == 3


def test_a_red_base_blames_nobody(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    _branch(out, "beta", {"src/b.py": "b\n"})
    r = _train(out, "run", "--force", "--suite", "false")
    assert r.returncode == 1 and "integration branch itself is red" in r.stderr
    assert "dropping it" not in r.stdout
    branches = _git(out, "branch", "--list", "--format=%(refname:short)").stdout.split()
    assert "alpha" in branches and "beta" in branches and not any(b.startswith("train/") for b in branches)


_OPEN_TASK_PLAN = "# {name}\n\ntier: 2\nissue: none\n\n- [ ] T1 the task still open\n\n## Decisions\n"


def test_a_passenger_with_an_open_task_is_dropped_at_the_gates_not_at_the_push(render, tmp_path):
    # v2.94 C2: the train's gates run told where the merge goes — a merge-only
    # finding is red on the combined tree, the search drops its owner
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    _branch(out, "beta", {"src/b.py": "b\n", ".process-work/plans/archive/2026-09-20-beta.md":
                          _OPEN_TASK_PLAN.format(name="beta")}, archive=False)
    r = _train(out, "run", "--force", "--suite", "true")
    assert "beta was dropped as the offender" in r.stdout, r.stdout + r.stderr
    log = "".join(p.read_text() for p in (out / ".git/process-train").glob("*.log"))
    assert "open task at the merge" in log or "open task at the merge" in r.stdout, log
    files = _git(out, "ls-tree", "-r", "--name-only", "main").stdout.split()
    assert "src/a.py" in files and "src/b.py" not in files


def test_an_open_task_on_main_leaves_base_and_train_green(render, tmp_path):
    # the base runs without a target, the combined tree with one: a plan main
    # already carries is not this range's (`_bound`), so neither is red
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _main_commit(out, {".process-work/plans/2026-09-19-old.md": _OPEN_TASK_PLAN.format(name="old")},
                 "docs: an active plan")
    _branch(out, "alpha", {"src/a.py": "a\n"})
    r = _train(out, "run", "--force", "--suite", "true")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "src/a.py" in _git(out, "ls-tree", "-r", "--name-only", "main").stdout.split()


def test_a_train_of_contained_passengers_runs_its_gates_without_a_target(render, tmp_path, monkeypatch):
    # every passenger already in the base: the tree IS the base, and with a
    # target its active Tier 2 plan would read "no proper integration base"
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _main_commit(out, {".process-work/plans/2026-09-19-old.md": _OPEN_TASK_PLAN.format(name="old")},
                 "docs: an active plan")
    _git(out, "branch", "inside", "main")
    train = _load_train(out)
    seen: list = []
    real = train._run_gates

    def spy(wt, log, *a, **k):
        seen.append(a or tuple(k.values()))
        return real(wt, log, *a, **k)

    monkeypatch.setattr(train, "_run_gates", spy)
    monkeypatch.setattr(train, "_write", lambda *a, **k: None)
    base = _git(out, "rev-parse", "main").stdout.strip()
    p = {"base": "main", "base_sha": base, "candidates": [{"branch": "inside", "hours_waiting": 1}]}
    rc = train._run_batch(out, "main", p, ["inside"], "t9", tmp_path / "t.log", suite=None, deploy=None,
                          push=False, keep_branches=True)
    assert rc == 0, (tmp_path / "t.log").read_text()
    assert seen and all(not s or s == (None,) for s in seen), seen


def test_local_main_ahead_of_origin_refuses_to_depart(render, tmp_path):
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    _repo(out)
    bare = tmp_path / "origin.git"
    _git(out, "clone", "-q", "--bare", str(out), str(bare))
    _git(out, "remote", "add", "origin", str(bare))
    _git(out, "fetch", "-q", "origin")
    _branch(out, "alpha", {"src/a.py": "a\n"})
    (out / "local.txt").write_text("unpushed\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "local only")
    head = _git(out, "rev-parse", "main").stdout
    r = _train(out, "run", "--force", "--push", "--suite", "true")
    assert r.returncode == 2 and "carries commits that are not on origin/main" in r.stderr
    assert _git(out, "rev-parse", "main").stdout == head
    assert _git(bare, "rev-parse", "main").stdout != head


def test_conflicting_candidate_is_reported_blocked(render, tmp_path):
    # a conflict arises when main moved on the same file after the branch
    # forked, or two candidates aboard change the same lines
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _branch(out, "beta", {"shared.txt": "beta\n"})
    (out / "shared.txt").write_text("main moved\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "main: shared")
    r = _train(out, "run", "--force", "--suite", "true")
    assert r.returncode == 1, r.stdout + r.stderr
    assert "merge conflict with the batch" in r.stdout and "beta" in r.stdout
    t = json.loads(subprocess.run([sys.executable, str(out / "scripts/process/tower.py"), "--json"],
                                  cwd=out, capture_output=True, text=True).stdout)
    states = {x["worker"]: x["state"] for x in t["reports"]}
    assert states["beta"] == "blocked"
    branches = _git(out, "branch", "--list", "--format=%(refname:short)").stdout.split()
    assert "beta" in branches and not any(b.startswith("train/") for b in branches)


def test_a_train_written_conflict_blocked_does_not_hold(render, tmp_path):
    """Fix round 1: the train's own `blocked` describes a run — a conflict with a passenger
    that never landed would otherwise hold the branch for nothing. A steward's still holds,
    also under a later train-written one."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _branch(out, "beta", {"shared.txt": "beta\n"})
    (out / "shared.txt").write_text("main moved\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "main: shared")
    r = _train(out, "run", "--force", "--suite", "true")
    assert r.returncode == 1 and "merge conflict with the batch" in r.stdout, r.stdout + r.stderr
    c = _candidate(out, "beta")
    assert not any("latest report `blocked`" in why for why in c["reasons"]), c
    _report(out, "beta", None, "blocked", note="steward: wait for #12")
    _report(out, "beta", None, "blocked", note="dropped from train 20261027-1000: red with it aboard")
    c = _candidate(out, "beta")
    assert not c["eligible"], c
    assert any("latest report `blocked`" in why and "steward: wait for #12" in why for why in c["reasons"]), c


def test_a_train_written_blocked_does_not_shadow_a_review_pass(render, tmp_path):
    """Review round 2: the boarding arms read past the train's own `blocked` too — a branch
    that boarded on its `review-pass` boards again after a drop it did not cause."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _package_branch(out, "70-p1-slice", "71")
    _report(out, "70-p1-slice", issue=71)
    _dispatched(out, 71, "70-p1-slice")
    assert _candidate(out, "70-p1-slice")["eligible"]
    _report(out, "70-p1-slice", None, "blocked",
            note=f"{'dropped from train'} 20261027-1000: merge conflict — rebase onto main")
    c = _candidate(out, "70-p1-slice")
    assert c["eligible"] and "worker report review-pass" in c["by"], c


def test_a_flaky_suite_is_retried_on_the_same_tree_not_bisected(render, tmp_path):
    # two load-induced timeouts, then "base is red too"
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    _repo(out)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    _branch(out, "beta", {"src/b.py": "b\n"})
    marker = tmp_path / "ran-once"
    suite = f"if [ -f {marker} ]; then exit 0; else touch {marker}; exit 1; fi"
    r = _train(out, "run", "--force", "--suite", suite)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "FLAKY" in r.stderr and "dropping" not in r.stdout
    assert (out / "src/a.py").exists() and (out / "src/b.py").exists()


def test_a_suite_a_passenger_introduces_does_not_make_main_red(render, tmp_path):
    # `make test-merge` came with a passenger; the base
    # run said "No rule to make target" and the train called main red
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    _repo(out)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    _branch(out, "beta", {"Makefile": "test-merge:\n\texit 1\n"})
    r = _train(out, "run", "--force", "--suite", "make test-merge")
    assert "does not exist on the base" in r.stdout, r.stdout + r.stderr
    assert "fix main first" not in r.stderr
    assert "red with beta aboard" in r.stdout


def test_a_local_hook_refusal_names_the_hook_and_its_reasons(render, tmp_path):
    # the log said "branch protection?" while the local
    # pre-push review gate had refused, for a reason only a manual run showed
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    _repo(out)
    bare = tmp_path / "origin.git"
    _git(out, "clone", "-q", "--bare", str(out), str(bare))
    _git(out, "remote", "add", "origin", str(bare))
    _git(out, "fetch", "-q", "origin")
    _git(out, "branch", "-q", "--set-upstream-to=origin/main", "main")
    _branch(out, "alpha", {"src/a.py": "a\n"})
    hook = out / ".git/hooks/pre-push"
    hook.write_text("#!/bin/sh\necho 'review gate: code changed after the reviewed head' >&2\nexit 1\n")
    hook.chmod(0o755)
    r = _train(out, "run", "--force", "--push", "--suite", "true")
    assert r.returncode == 1
    assert "the local pre-push hook refused it" in r.stderr
    assert "code changed after the reviewed head" in r.stderr


def test_a_command_not_found_inside_a_red_suite_is_red_not_undefined(render, tmp_path):
    # a test that shells out prints it
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    _repo(out)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    r = _train(out, "run", "--force", "--suite", "echo 'sh: 1: frob: not found'; echo 'frob: command not found'; exit 1")
    assert "does not exist" not in r.stdout + r.stderr
    assert "fix main first" in r.stderr or "red with alpha aboard" in r.stdout, r.stdout + r.stderr


def _load_train(out):
    import importlib.util
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(out / "scripts/process"))
    spec = importlib.util.spec_from_file_location("train_under_test", out / "scripts/process/train.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_after_a_drop_the_rest_gets_its_own_flake_rerun(render, tmp_path, monkeypatch):
    # combined red, retry red, base green,
    # b1 dropped; the rest [b2] is red once, then green — a flake, not an offender
    from types import SimpleNamespace
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    train = _load_train(out)
    states = iter(["red", "red", "green", "red", "red", "green"])
    wt = tmp_path / "wt"
    wt.mkdir()
    monkeypatch.setattr(train, "build_train", lambda root, base, subset, stamp, log, **kw: (wt, "train/x", list(subset), []))
    monkeypatch.setattr(train, "_run_gates", lambda *a, **k: True)
    monkeypatch.setattr(train, "_sh", lambda cwd, cmd, log, **kw: next(states))
    monkeypatch.setattr(train, "_git", lambda *a, **k: SimpleNamespace(returncode=0, stdout="", stderr=""))
    monkeypatch.setattr(train, "_out", lambda *a, **k: "")
    monkeypatch.setattr(train, "_cleanup", lambda *a: None)
    monkeypatch.setattr(train, "_write", lambda *a, **k: None)
    p = {"base": "origin/main", "candidates": [{"branch": "b1", "hours_waiting": 2}, {"branch": "b2", "hours_waiting": 1}]}
    rc = train._run_batch(out, "main", p, ["b1", "b2"], "x", tmp_path / "t.log", suite="s", deploy=None,
                          push=False, keep_branches=True)
    assert rc == 0
    assert "flaky" in (tmp_path / "t.log").read_text()


def test_the_suites_own_make_is_recognised_at_any_makelevel(render, tmp_path, monkeypatch):
    # `make train` runs the train at MAKELEVEL 1: the suite's make prints
    # `make[1]:` — still undefined; a deeper make inside a test stays red
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    train = _load_train(out)
    log = lambda _l: None  # noqa: E731
    monkeypatch.delenv("MAKELEVEL", raising=False)
    assert train._sh(tmp_path, "make -f /dev/null missing-target", log) == "undefined"
    monkeypatch.setenv("MAKELEVEL", "1")
    assert train._sh(tmp_path, "make -f /dev/null missing-target", log) == "undefined"
    assert train._sh(tmp_path, "MAKELEVEL=2 make -f /dev/null missing-target", log) == "red"


@pytest.mark.parametrize("output,state", [
    # a prerequisite a passenger deleted is a red tree, not an undefined suite
    ("make: *** No rule to make target 'fixture.txt', needed by 'check'.  Stop.", "red"),
    ("make: *** No rule to make target `test-merge'.  Stop.", "undefined"),   # GNU make 3.81 quoting
    ("gmake: *** No rule to make target 'test-merge'.  Stop.", "undefined"),
    ("make: *** No rule to make target 'test-merge'.", "undefined"),          # make -k: no "Stop."
    # another name than the suite's target: a missing include or file
    ("make: *** No rule to make target 'mk/missing.mk'.  Stop.", "red"),
])
def test_the_undefined_line_reads_real_make_variants(render, tmp_path, monkeypatch, output, state):
    # a stand-in `make` on PATH prints the variant; the suite asks for test-merge
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    train = _load_train(out)
    monkeypatch.delenv("MAKELEVEL", raising=False)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ("make", "gmake"):
        fake = bin_dir / name
        fake.write_text("#!/bin/sh\nprintf '%s\\n' " + __import__("shlex").quote(output) + "\nexit 2\n")
        fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:{__import__('os').environ['PATH']}")
    assert train._sh(tmp_path, "make test-merge", lambda _l: None) == state
    assert train._sh(tmp_path, "gmake -j 4 -C . test-merge", lambda _l: None) == state
    # shell forms of the same call (refute of the fix: these lost their target)
    for cmd in ("(cd . && make test-merge)", "cd .&&make test-merge", "make test-merge;",
                "make test-merge 2>&1 | cat; exit 2"):
        assert train._sh(tmp_path, cmd, lambda _l: None) == state, cmd
    # a command that is not a make call names no target: never undefined on rc 2
    assert train._sh(tmp_path, "sh -c 'make test-merge'", lambda _l: None) == "red"


def test_a_missing_include_is_a_red_tree_not_an_undefined_suite(render, tmp_path, monkeypatch):
    # real make: the Makefile includes a file a passenger deleted
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    train = _load_train(out)
    monkeypatch.delenv("MAKELEVEL", raising=False)
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "Makefile").write_text("include mk/missing.mk\ntest:\n\ttrue\n")
    assert train._sh(tree, "make test", lambda _l: None) == "red"
    (tree / "Makefile").write_text("include test\nother:\n\ttrue\n")  # include named like the target
    assert train._sh(tree, "make test", lambda _l: None) == "red"
    (tree / "Makefile").write_text("other:\n\ttrue\n")
    assert train._sh(tree, "make test", lambda _l: None) == "undefined"
    # an earlier step echoing the words is not make's include line
    (tree / "Makefile").write_text("lint:\n\t@echo 'x: test-merge: No such file or directory'\n")
    assert train._sh(tree, "make lint && make test-merge", lambda _l: None) == "undefined"
    (tree / "Makefile").write_text("lint:\n\ttrue\n")  # every target of a chain is the suite's
    assert train._sh(tree, "make lint && make test", lambda _l: None) == "undefined"


# --- the suite verdict: read_facts + decide() table ---

_NO_RULE = "make: *** No rule to make target 'test-merge'.  Stop."
_SUITE_TABLE = [
    # (case, command, exit code, output, MAKELEVEL, state, words of the reason)
    ("green", "make test", 0, [], "0", "green", "exit 0"),
    ("recipe error on a defined target", "make test", 2,
     ["make: *** [Makefile:2: test] Error 1"], "0", "red", "defined target"),
    ("GNU make 3.81 recipe error", "make test", 2, ["make: *** [test] Error 1"], "0", "red", "defined target"),
    ("a red call, then a call without the target", "make test; make -C examples test", 2,
     ["make: *** [Makefile:2: test] Error 1", "make: Entering directory '/w/examples'",
      "make: *** No rule to make target 'test'.  Stop.", "make: Leaving directory '/w/examples'"],
     "0", "red", "defined target"),
    ("a call without the target, then a red call", "make -C examples test; make test", 2,
     ["make: *** No rule to make target 'test'.  Stop.", "make: *** [Makefile:2: test] Error 1"],
     "0", "red", "defined target"),
    ("make -k: a red target and an undefined one", "make -k lint test-merge", 2,
     ["make: *** [Makefile:2: lint] Error 1", "make: *** No rule to make target 'test-merge'.",
      "make: Target 'lint' not remade because of errors."], "0", "red", "defined target"),
    ("a recipe's tool not found", "make test", 2,
     ["/bin/sh: 1: frob: not found", "make: *** [Makefile:2: test] Error 127"], "0", "red", "defined target"),
    ("a red make call, then the suite's script not found", "make test; ./scripts/x.sh", 127,
     ["make: *** [Makefile:2: test] Error 1", "sh: 1: ./scripts/x.sh: not found"], "0", "red", "defined target"),
    ("missing prerequisite", "make check", 2,
     ["make: *** No rule to make target 'fixture.txt', needed by 'check'.  Stop."], "0", "red", "prerequisite"),
    ("missing prerequisite, then a call without the target", "make check; make test-merge", 2,
     ["make: *** No rule to make target 'fixture.txt', needed by 'check'.  Stop.", _NO_RULE],
     "0", "red", "prerequisite"),
    ("missing include", "make test", 2,
     ["Makefile:1: mk/missing.mk: No such file or directory",
      "make: *** No rule to make target 'mk/missing.mk'.  Stop."], "0", "red", "missing include"),
    ("include named like the target", "make test", 2,
     ["Makefile:1: test: No such file or directory", "make: *** No rule to make target 'test'.  Stop."],
     "0", "red", "missing include"),
    ("missing include in one call, no target in the next", "make -C sub lint; make test-merge", 2,
     ["Makefile:1: mk/missing.mk: No such file or directory",
      "make: *** No rule to make target 'mk/missing.mk'.  Stop.", _NO_RULE], "0", "red", "missing include"),
    ("an earlier step echoes make's include line", "make lint && make test-merge", 2,
     ["x: test-merge: No such file or directory", _NO_RULE], "0", "undefined", "names"),
    ("MAKELEVEL 0", "make test-merge", 2, [_NO_RULE], "0", "undefined", "names"),
    ("MAKELEVEL 1", "make test-merge", 2,
     ["make[1]: *** No rule to make target 'test-merge'.  Stop."], "1", "undefined", "names"),
    ("MAKELEVEL 2", "make test-merge", 2,
     ["make[2]: *** No rule to make target 'test-merge'.  Stop."], "2", "undefined", "names"),
    ("a deeper make's stop line", "make test-merge", 2,
     ["make[2]: *** No rule to make target 'test-merge'.  Stop."], "0", "red", "exit 2"),
    ("a bare make line under make train", "make test-merge", 2, [_NO_RULE], "1", "red", "exit 2"),
    ("GNU make 3.81 quoting", "make test-merge", 2,
     ["make: *** No rule to make target `test-merge'.  Stop."], "0", "undefined", "names"),
    ("gmake", "gmake -j 4 -C . test-merge", 2,
     ["gmake: *** No rule to make target 'test-merge'.  Stop."], "0", "undefined", "names"),
    ("make -k without Stop.", "make -k test-merge", 2,
     ["make: *** No rule to make target 'test-merge'."], "0", "undefined", "names"),
    ("no rule for another name", "make test-merge", 2,
     ["make: *** No rule to make target 'other'.  Stop."], "0", "red", "exit 2"),
    ("a chain: every target is the suite's", "make lint && make test", 2,
     ["make: *** No rule to make target 'test'.  Stop."], "0", "undefined", "names"),
    ("subshell", "(cd x && make test)", 2,
     ["make: *** No rule to make target 'test'.  Stop."], "0", "undefined", "names"),
    ("trailing ;", "make test;", 2, ["make: *** No rule to make target 'test'.  Stop."], "0", "undefined", "names"),
    ("no spaces around &&", "cd x&&make test", 2,
     ["make: *** No rule to make target 'test'.  Stop."], "0", "undefined", "names"),
    ("uv run make", "uv run make test", 2,
     ["make: *** No rule to make target 'test'.  Stop."], "0", "undefined", "names"),
    ("redirection and pipe", "make test-merge 2>&1 | cat; exit 2", 2, [_NO_RULE], "0", "undefined", "names"),
    ("sh -c is no make call the train reads", "sh -c 'make test'", 2,
     ["make: *** No rule to make target 'test'.  Stop."], "0", "red", "exit 2"),
    ("exit 1 with a stop line", "make test-merge || exit 1", 1, [_NO_RULE], "0", "red", "exit 1"),
    ("the suite's script not found (dash)", "./scripts/x.sh", 127,
     ["sh: 1: ./scripts/x.sh: not found"], "0", "undefined", "itself"),
    ("the suite's script not found (bash as sh)", "./scripts/x.sh", 127,
     ["sh: line 1: ./scripts/x.sh: No such file or directory"], "0", "undefined", "itself"),
    ("the suite's command not found", "pytest -q", 127,
     ["sh: line 1: pytest: command not found"], "0", "undefined", "itself"),
    ("the suite's script behind an assignment", "CI=1 ./scripts/x.sh", 127,
     ["sh: 1: ./scripts/x.sh: not found"], "0", "undefined", "itself"),
    ("the suite's script after a green make call", "make lint && ./scripts/x.sh", 127,
     ["sh: 1: ./scripts/x.sh: not found"], "0", "undefined", "itself"),
    ("a tool inside the suite not found", "./run.sh", 127, ["./run.sh: 2: frob: not found"], "0", "red", "inside"),
    ("a test prints sh's line for another word", "./run.sh", 127,
     ["sh: 1: frob: not found"], "0", "red", "inside"),
    ("the missing word is only an argument", "./run.sh ./scripts/x.sh", 127,
     ["sh: 1: ./scripts/x.sh: not found"], "0", "red", "inside"),
    ("exit 127 without a message", "./run.sh", 127, [], "0", "red", "inside"),
    # refute of the table: make's marker glued onto output without a newline
    ("recipe error glued onto a recipe's output", "make nonl; make -C examples test", 2,
     ["FAILED 3 testsmake: *** [Makefile:2: nonl] Error 1", "make: *** No rule to make target 'test'.  Stop."],
     "0", "red", "defined target"),
    ("recipe error glued onto -j progress dots", "make -j4 -k lint test ex", 2,
     ["make: *** No rule to make target 'ex'.", "..make: *** [Makefile:4: lint] Error 1"],
     "0", "red", "defined target"),
    ("-j: waiting for unfinished jobs", "make -j4 lint test ex", 2,
     ["make: *** No rule to make target 'ex'.  Stop.", "make: *** Waiting for unfinished jobs...."],
     "0", "red", "defined target"),
    # a command substitution does not split the command
    ("make -j$(nproc)", "make -j$(nproc) test-merge", 2, [_NO_RULE], "0", "undefined", "names"),
    ("make -j $(nproc)", "make -j $(nproc) test-merge", 2, [_NO_RULE], "0", "undefined", "names"),
    ("make -j`nproc`", "make -j`nproc` test-merge", 2, [_NO_RULE], "0", "undefined", "names"),
    # the suite's own file, asked of the tree (the last column: the files it has)
    ("the suite's script is in the tree but broken (CRLF)", "./scripts/ci.sh", 127,
     ["sh: 1: ./scripts/ci.sh: not found"], "0", "red", "inside", {"scripts/ci.sh"}),
    ("sh scripts/new.sh", "sh scripts/new.sh", 2,
     ["sh: 0: cannot open scripts/new.sh: No such file"], "0", "undefined", "own file", set()),
    ("bash scripts/new.sh", "bash scripts/new.sh", 127,
     ["bash: scripts/new.sh: No such file or directory"], "0", "undefined", "own file", set()),
    ("timeout 600 ./scripts/new.sh", "timeout 600 ./scripts/new.sh", 127,
     ["timeout: failed to run command './scripts/new.sh': No such file or directory"],
     "0", "undefined", "own file", set()),
    ("nice -n 5 ./scripts/new.sh", "nice -n 5 ./scripts/new.sh", 127, [], "0", "undefined", "own file", set()),
    ("env FOO=1 ./scripts/new.sh", "env FOO=1 ./scripts/new.sh", 127, [], "0", "undefined", "own file", set()),
    ("exec ./scripts/new.sh", "exec ./scripts/new.sh", 127,
     ["sh: 1: exec: ./scripts/new.sh: not found"], "0", "undefined", "own file", set()),
    ("command ./scripts/new.sh", "command ./scripts/new.sh", 127, [], "0", "undefined", "own file", set()),
    ("python3 scripts/new.py", "python3 scripts/new.py", 2, [], "0", "undefined", "own file", set()),
    ("uv run scripts/new.py", "uv run scripts/new.py", 2, [], "0", "undefined", "own file", set()),
    ("python -m: a missing path is the tool's argument", "python -m pytest tests/merge", 4, [],
     "0", "red", "exit 4", set()),
    ("sh -ec: a program text, no file", "sh -ec 'make test'", 2, [], "0", "red", "exit 2", set()),
    ("make -C a directory not on the tree", "make -C newdir test", 2,
     ["make: *** newdir: No such file or directory.  Stop."], "0", "undefined", "own file", set()),
    ("cd into a directory not on the tree", "cd newdir && make test", 2,
     ["sh: 1: cd: can't cd to newdir"], "0", "undefined", "own file", set()),
    ("make -f a makefile not on the tree", "make -f new.mk test", 2,
     ["make: new.mk: No such file or directory", "make: *** No rule to make target 'new.mk'.  Stop."],
     "0", "undefined", "own file", set()),
    ("make -C a directory on the tree", "make -C sub test", 2,
     ["make: *** No rule to make target 'other'.  Stop."], "0", "red", "exit 2", {"sub"}),
    ("an absent file behind a red first command", "./scripts/red.sh && ./scripts/new.sh", 1, [],
     "0", "red", "exit 1", {"scripts/red.sh"}),
    ("an absent first file behind ; is not the whole suite", "./scripts/new.sh; ./scripts/red.sh", 1, [],
     "0", "red", "exit 1", {"scripts/red.sh"}),
    ("a missing fallback after ||", "./scripts/red.sh || ./scripts/on-failure.sh", 127,
     ["sh: 1: ./scripts/on-failure.sh: not found"], "0", "red", "inside", {"scripts/red.sh"}),
    ("a missing command after ;", "./scripts/red.sh; ./scripts/x.sh", 127,
     ["sh: 1: ./scripts/x.sh: not found"], "0", "red", "inside", {"scripts/red.sh"}),
    # documented limits
    ("make stops at an undefined target before a red one", "make nope test", 2,
     ["make: *** No rule to make target 'nope'.  Stop."], "0", "undefined", "names"),
    ("output redirected away from the train", "make test > log 2>&1", 2, [], "0", "red", "exit 2"),
    ("a target spelled through the shell", "make test-$${X:-new}", 2,
     ["make: *** No rule to make target 'test-4242{X:-new}'.  Stop."], "0", "red", "exit 2"),
    # v2.95: the run marked itself aborted (`$PROCESS_SUITE_ABORT`, the last column: its lines),
    # or the suite refused to run (exit 75 at the top) — no finding about the tree
    ("a marker on a red run", "make test", 2, ["make: *** [Makefile:2: test] Error 1"], "0", "aborted",
     "a run aborted: watchdog tests/t.py::a 10 8.2", None, ("watchdog tests/t.py::a 10 8.2", "a second line")),
    ("a lane abort under make -k writes the marker", "make -k test", 2,
     ["make: *** [Makefile:2: test] Error 75"], "0", "aborted", "a run aborted: lane-busy full", None,
     ("lane-busy full held by pid 7",)),
    ("a marker beside a missing suite", "./scripts/x.sh", 127, ["sh: 1: ./scripts/x.sh: not found"], "0",
     "aborted", "a run aborted: nested-timeout", None, ("nested-timeout t::x 30",)),
    ("exit 0 wins over a marker", "make test", 0, [], "0", "green", "exit 0", None, ("watchdog t::x 10 9.0",)),
    ("exit 75 at the top", "./scripts/lanes.sh", 75, [], "0", "aborted",
     "a run aborted: exit 75 (EX_TEMPFAIL), the suite refused to run", None, ()),
    ("exit 75 under make without a marker", "make -k test", 2, ["make: *** [Makefile:2: test] Error 75"],
     "0", "red", "defined target", None, ()),
]
_SUITE_TABLE = [(*r, *(None, ())[len(r) - 7:]) for r in _SUITE_TABLE]


@pytest.mark.parametrize("case,cmd,rc,output,level,state,words,present,abort", _SUITE_TABLE,
                         ids=[r[0] for r in _SUITE_TABLE])
def test_suite_decide_table(render, tmp_path, case, cmd, rc, output, level, state, words, present, abort):
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    train = _load_train(out)
    exists = None if present is None else present.__contains__
    got, reason = train.decide(train.read_facts(cmd, rc, output, level, exists, abort=abort))
    assert (got, words in reason) == (state, True), (case, got, reason)


def test_every_row_of_decide_has_a_table_case(render, tmp_path):
    # a row added to decide() without a case in the table fails here
    import inspect
    import re
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    train = _load_train(out)
    reasons = re.findall(r'return "\w+", f?"([^"{]+)', inspect.getsource(train.decide))
    reached = {train.decide(train.read_facts(c, rc, o, lv, None if p is None else p.__contains__, abort=a))[1]
               for _n, c, rc, o, lv, _s, _w, p, a in _SUITE_TABLE}
    assert any(r.startswith("a run aborted") for r in reasons), reasons  # v2.95: the rows exist
    for r in reasons:
        assert any(x.startswith(r) for x in reached), r


def _real_make(monkeypatch, tmp_path):
    # real GNU make, untranslated, run as the train's suite at MAKELEVEL 0
    monkeypatch.setenv("PATH", f"/usr/local/bin:{__import__('os').environ['PATH']}")
    monkeypatch.setenv("LC_ALL", "C")
    monkeypatch.delenv("MAKELEVEL", raising=False)
    monkeypatch.delenv("MAKEFLAGS", raising=False)
    if __import__("shutil").which("make") is None:
        pytest.skip("no make")
    tree = tmp_path / "tree"
    tree.mkdir()
    return tree


def test_a_red_make_call_is_red_even_if_a_later_call_has_no_such_target(render, tmp_path, monkeypatch):
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    train = _load_train(out)
    tree = _real_make(monkeypatch, tmp_path)
    (tree / "Makefile").write_text("test:\n\texit 1\n")
    (tree / "examples").mkdir()
    (tree / "examples/Makefile").write_text("other:\n\ttrue\n")
    assert train._sh(tree, "make test; make -C examples test", lambda _l: None) == "red"
    assert train._sh(tree, "make -C examples test; make test", lambda _l: None) == "red"
    (tree / "Makefile").write_text("test:\n\ttrue\n")  # the first call green: the examples' target is missing
    assert train._sh(tree, "make test; make -C examples test", lambda _l: None) == "undefined"


def test_a_broken_make_call_is_red_even_if_a_later_call_has_no_such_target(render, tmp_path, monkeypatch):
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    train = _load_train(out)
    tree = _real_make(monkeypatch, tmp_path)
    (tree / "Makefile").write_text("check: fixture.txt\n\ttrue\n")  # a prerequisite a passenger deleted
    assert train._sh(tree, "make check; make test-merge", lambda _l: None) == "red"
    (tree / "sub").mkdir()
    (tree / "sub/Makefile").write_text("include mk/missing.mk\nlint:\n\ttrue\n")
    assert train._sh(tree, "make -C sub lint; make test-merge", lambda _l: None) == "red"


def test_exit_127_is_undefined_only_for_the_suites_own_command(render, tmp_path, monkeypatch):
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    train = _load_train(out)
    tree = _real_make(monkeypatch, tmp_path)
    # the script a passenger introduces is not on this tree: not comparable
    assert train._sh(tree, "./scripts/x.sh", lambda _l: None) == "undefined"
    # a tool missing inside the suite: red
    (tree / "run.sh").write_text("#!/bin/sh\nfrob-missing-tool\n")
    (tree / "run.sh").chmod(0o755)
    assert train._sh(tree, "./run.sh", lambda _l: None) == "red"
    assert train._sh(tree, "echo 'sh: 1: frob: not found'; exit 127", lambda _l: None) == "red"


def test_a_recipe_error_glued_onto_output_is_red(render, tmp_path, monkeypatch):
    # refute: a recipe without a final newline, or -j progress dots, run into
    # make's error line; a later "No rule" then excused the red tree
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    train = _load_train(out)
    tree = _real_make(monkeypatch, tmp_path)
    (tree / "Makefile").write_text(
        "nonl:\n\t@printf 'FAILED 3 tests'; exit 1\n"
        "lint:\n\t@sleep 0.3; exit 1\n"
        "dots:\n\t@for i in 1 2 3 4 5 6; do printf .; sleep 0.1; done\n")
    (tree / "examples").mkdir()
    (tree / "examples/Makefile").write_text("other:\n\ttrue\n")
    for cmd in ("make nonl; make -C examples test", "make -k nonl nope", "make -j4 -k lint dots nope",
                "make -j4 lint dots nope"):
        assert train._sh(tree, cmd, lambda _l: None) == "red", cmd


def test_a_flood_of_output_does_not_push_the_red_line_out(render, tmp_path, monkeypatch):
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    train = _load_train(out)
    tree = _real_make(monkeypatch, tmp_path)
    (tree / "Makefile").write_text("test:\n\texit 1\nflood:\n\t@for i in $$(seq 450); do echo \"x$$i: not found\"; done\n")
    assert train._sh(tree, "make test; make flood; make nope", lambda _l: None) == "red"


def test_a_missing_fallback_or_later_command_does_not_excuse_a_red_run(render, tmp_path, monkeypatch):
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    train = _load_train(out)
    tree = _real_make(monkeypatch, tmp_path)
    (tree / "scripts").mkdir()
    (tree / "scripts/red.sh").write_text("#!/bin/sh\nexit 1\n")
    (tree / "scripts/red.sh").chmod(0o755)
    assert train._sh(tree, "./scripts/red.sh || ./scripts/on-failure.sh", lambda _l: None) == "red"
    assert train._sh(tree, "./scripts/red.sh; ./scripts/next.sh", lambda _l: None) == "red"


def test_a_command_substitution_does_not_split_the_make_call(render, tmp_path, monkeypatch):
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    train = _load_train(out)
    tree = _real_make(monkeypatch, tmp_path)
    (tree / "Makefile").write_text("other:\n\ttrue\n")
    for cmd in ("make -j$(nproc) test-merge", "make -j $(nproc) test-merge", "make -j`nproc` test-merge"):
        assert train._sh(tree, cmd, lambda _l: None) == "undefined", cmd


def test_a_suite_file_a_passenger_introduces_is_undefined_behind_wrappers(render, tmp_path, monkeypatch):
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    train = _load_train(out)
    tree = _real_make(monkeypatch, tmp_path)
    (tree / "Makefile").write_text("other:\n\ttrue\n")
    for cmd in ("sh scripts/new.sh", "bash scripts/new.sh", "timeout 600 ./scripts/new.sh", "nice ./scripts/new.sh",
                "env FOO=1 ./scripts/new.sh", "exec ./scripts/new.sh", "command ./scripts/new.sh",
                f"{sys.executable} scripts/new.py", "make -C newdir test", "cd newdir && make test",
                "make -f new.mk test"):
        assert train._sh(tree, cmd, lambda _l: None) == "undefined", cmd
    # a tool's missing argument is no suite file: red
    assert train._sh(tree, f"{sys.executable} -m no_such_module_here tests/merge", lambda _l: None) == "red"


def test_a_broken_suite_script_in_the_tree_is_red_not_missing(render, tmp_path, monkeypatch):
    # CRLF line ends: dash says "not found" for a script that is there
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    train = _load_train(out)
    tree = _real_make(monkeypatch, tmp_path)
    (tree / "scripts").mkdir()
    (tree / "scripts/ci.sh").write_bytes(b"#!/bin/sh\r\nexit 0\r\n")
    (tree / "scripts/ci.sh").chmod(0o755)
    (tree / "scripts/py.sh").write_text("#!/nonexistent/interpreter\n")
    (tree / "scripts/py.sh").chmod(0o755)
    assert train._sh(tree, "./scripts/ci.sh", lambda _l: None) == "red"
    assert train._sh(tree, "./scripts/py.sh", lambda _l: None) == "red"


def test_output_the_terminal_cannot_encode_is_replaced_not_a_traceback(render, tmp_path, monkeypatch):
    import io
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    train = _load_train(out)
    stream = io.TextIOWrapper(io.BytesIO(), encoding="ascii")
    monkeypatch.setattr(sys, "stdout", stream)
    assert train._sh(tmp_path, "echo 'price: 5 €'", lambda _l: None) == "green"
    stream.flush()
    assert b"price: 5 ?" in stream.buffer.getvalue()


def test_a_suite_the_base_has_but_the_combined_tree_lost_is_red(render, tmp_path, monkeypatch):
    # combined undefined, base green: a passenger removed the suite — the
    # search blames the prefix that loses it ([b1] undefined), [b2] merges
    from types import SimpleNamespace
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    train = _load_train(out)
    states = iter(["undefined", "green", "undefined", "green"])
    wt = tmp_path / "wt"
    wt.mkdir()
    written = []
    monkeypatch.setattr(train, "build_train", lambda root, base, subset, stamp, log, **kw: (wt, "train/x", list(subset), []))
    monkeypatch.setattr(train, "_run_gates", lambda *a, **k: True)
    monkeypatch.setattr(train, "_sh", lambda cwd, cmd, log, **kw: next(states))
    monkeypatch.setattr(train, "_git", lambda *a, **k: SimpleNamespace(returncode=0, stdout="", stderr=""))
    monkeypatch.setattr(train, "_out", lambda *a, **k: "")
    monkeypatch.setattr(train, "_cleanup", lambda *a: None)
    monkeypatch.setattr(train, "_write", lambda root, state, note, worker: written.append((state, worker)))
    p = {"base": "origin/main", "candidates": [{"branch": "b1", "hours_waiting": 2}, {"branch": "b2", "hours_waiting": 1}]}
    rc = train._run_batch(out, "main", p, ["b1", "b2"], "x", tmp_path / "t.log", suite="s", deploy=None,
                          push=False, keep_branches=True)
    assert rc == 0 and ("blocked", "b1") in written and ("blocked", "b2") not in written


def test_a_passenger_that_deletes_the_suite_target_is_blamed(render, tmp_path, monkeypatch):
    monkeypatch.setenv("LC_ALL", "C")
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    _repo(out)
    (out / "ci.mk").write_text("check:\n\ttrue\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "ci")
    _branch(out, "alpha", {"src/a.py": "a\n"})
    _branch(out, "beta", {"ci.mk": "other:\n\ttrue\n"})
    r = _train(out, "run", "--force", "--suite", "make -f ci.mk check")
    assert "red with beta aboard" in r.stdout, r.stdout + r.stderr
    assert "fix --suite" not in r.stderr
    assert (out / "src/a.py").exists()


def test_an_offender_that_brought_the_suite_is_still_reported(render, tmp_path, monkeypatch):
    # combined red, retry red, base undefined; b1 (which brought the suite) is
    # dropped; the rest cannot run the suite — b1 must still get its report
    from types import SimpleNamespace
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    train = _load_train(out)
    states = iter(["red", "red", "undefined", "red", "undefined"])
    wt = tmp_path / "wt"
    wt.mkdir()
    written, builds = [], []

    def build(root, base, subset, stamp, log, **kw):
        builds.append((base, dict(kw["shas"])))
        return wt, "train/x", list(subset), []
    monkeypatch.setattr(train, "build_train", build)
    monkeypatch.setattr(train, "_run_gates", lambda *a, **k: True)
    monkeypatch.setattr(train, "_sh", lambda cwd, cmd, log, **kw: next(states))
    monkeypatch.setattr(train, "_git", lambda *a, **k: SimpleNamespace(returncode=0, stdout="", stderr=""))
    monkeypatch.setattr(train, "_out", lambda *a, **k: "")
    monkeypatch.setattr(train, "_cleanup", lambda *a: None)
    monkeypatch.setattr(train, "_write", lambda root, state, note, worker: written.append((state, worker)))
    p = _pinned({"base": "origin/main", "candidates": [{"branch": "b1", "hours_waiting": 2},
                                                       {"branch": "b2", "hours_waiting": 1}]})
    rc = train._run_batch(out, "main", p, ["b1", "b2"], "x", tmp_path / "t.log", suite="s", deploy=None,
                          push=False, keep_branches=True)
    assert rc == 1 and ("blocked", "b1") in written
    # every run — first, retry, base, probe, rebuild — on the pinned base and tips (#391)
    pinned = {"b1": f"{1:040x}", "b2": f"{2:040x}"}
    assert builds and all(base == "b" * 40 and shas == pinned for base, shas in builds), builds


def _head_pass(out, work, head, base=None):
    # a full round's base is the head's fork point from main (#160)
    base = base or _git(out, "merge-base", "main", head).stdout.strip()
    return (f"REVIEW work={work} tier=2 reviewer=fresh model=cross independence=bundle,non-implementing "
            f"verdict=pass round=1 base={base} head={head}\n")


def test_a_merged_branch_with_new_commits_does_not_board_on_its_done_report(render, tmp_path):
    # a train merged the branch at its reviewed head and wrote `done`; then the
    # branch got new, unreviewed commits — they must not ride the next train
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _git(out, "checkout", "-q", "-b", "42-work", "main")
    (out / "src").mkdir(exist_ok=True)
    (out / "src/w.py").write_text("w = 1\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "work")
    _git(out, "checkout", "-q", "main")
    _git(out, "merge", "-q", "--no-ff", "--no-edit", "42-work")  # the train's merge
    subprocess.run([sys.executable, str(out / "scripts/process/report.py"), "done", "--worker", "42-work"],
                   cwd=out, check=True, capture_output=True)
    _git(out, "checkout", "-q", "42-work")
    (out / "src/w.py").write_text("w = 2\n")  # new, unreviewed commit after the merge
    _git(out, "commit", "-q", "-am", "fix after merge")
    _git(out, "checkout", "-q", "main")
    by = {c["branch"]: c for c in json.loads(_train(out, "plan", "--json").stdout)["candidates"]}
    c = by["42-work"]
    assert not c["eligible"] and "report `done` boards nothing" in c["reasons"][0]


def test_a_pass_behind_which_the_branch_moved_does_not_clear_it(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _branch(out, "43-work", {"src/x.py": "x = 1\n"}, reviewed=False)
    head = _git(out, "rev-parse", "43-work").stdout.strip()
    _git(out, "checkout", "-q", "43-work")
    j = out / ".process-work/journal"
    j.mkdir(parents=True, exist_ok=True)
    (j / "2026-09-21-43.md").write_text(_head_pass(out, "43-work", head))
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "attest")  # bookkeeping after the head: still covered
    _git(out, "checkout", "-q", "main")
    by = {c["branch"]: c for c in json.loads(_train(out, "plan", "--json").stdout)["candidates"]}
    assert by["43-work"]["eligible"], by["43-work"]
    _git(out, "checkout", "-q", "43-work")
    (out / "src/x.py").write_text("x = 2\n")
    _git(out, "commit", "-q", "-am", "code after the review")
    _git(out, "checkout", "-q", "main")
    by = {c["branch"]: c for c in json.loads(_train(out, "plan", "--json").stdout)["candidates"]}
    assert not by["43-work"]["eligible"] and "covering the branch head" in by["43-work"]["reasons"][0]


@pytest.mark.parametrize("mid_branch", [True, False], ids=["mid-branch", "fork-point"])
def test_a_pass_from_mid_branch_does_not_board_it(render, tmp_path, mid_branch):
    # #160: a full round based mid-branch reviewed a slice; the train reads
    # passes for the branch it boards, so the slice clears nothing
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _branch(out, "44-work", {"src/y.py": "y = 1\n"}, reviewed=False)
    _git(out, "checkout", "-q", "44-work")
    first = _git(out, "rev-parse", "HEAD").stdout.strip()
    (out / "src/z.py").write_text("z = 1\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "more work")
    head = _git(out, "rev-parse", "HEAD").stdout.strip()
    j = out / ".process-work/journal"
    j.mkdir(parents=True, exist_ok=True)
    (j / "2026-09-21-44.md").write_text(_head_pass(out, "44-work", head, first if mid_branch else None))
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "attest")
    _git(out, "checkout", "-q", "main")
    by = {c["branch"]: c for c in json.loads(_train(out, "plan", "--json").stdout)["candidates"]}
    assert by["44-work"]["eligible"] is not mid_branch, by["44-work"]


def test_a_headless_pass_on_main_does_not_vouch_for_new_commits(render, tmp_path):
    # an older, headless pass merged to main was written for the earlier
    # commits; a review-pass report cannot carry new gate code on it
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _branch(out, "45-gate", {"scripts/process/g.py": "g = 1\n"}, archive=False)
    _git(out, "merge", "-q", "--no-ff", "--no-edit", "45-gate")
    _git(out, "checkout", "-q", "45-gate")
    (out / "scripts/process/g.py").write_text("g = 2\n")
    _git(out, "commit", "-q", "-am", "gate change after the merge")
    _git(out, "checkout", "-q", "main")
    subprocess.run([sys.executable, str(out / "scripts/process/report.py"), "review-pass", "--worker", "45-gate"],
                   cwd=out, check=True, capture_output=True)
    c = next(c for c in json.loads(_train(out, "plan", "--json").stdout)["candidates"] if c["branch"] == "45-gate")
    assert not c["eligible"] and "changes the gates' code" in c["reasons"][0], c


def test_a_headless_pass_does_not_count_once_the_work_has_a_head_pass(render, tmp_path):
    # the headless rule looks at every pass of the work, whatever its tier:
    # a tier-1 pass with a head outdates a headless tier-2 one
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _branch(out, "46-work", {"src/y.py": "y = 1\n"})
    head = _git(out, "rev-parse", "46-work").stdout.strip()
    _git(out, "checkout", "-q", "46-work")
    (out / "src/y.py").write_text("y = 2\n")
    j = out / ".process-work/journal/2026-09-22-46.md"
    j.write_text(_head_pass(out, "46-work", head).replace("tier=2", "tier=1"))
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "code after the review, tier-1 attest")
    _git(out, "checkout", "-q", "main")
    c = next(c for c in json.loads(_train(out, "plan", "--json").stdout)["candidates"] if c["branch"] == "46-work")
    assert not c["eligible"], c


# --- a merge finishes its work: plans archived, issues closed ---

def _active_plan_branch(out, name, *, issue, tier=2, reviewed=True, extra=""):
    _git(out, "checkout", "-q", "-b", name, "main")
    (out / "src").mkdir(exist_ok=True)
    (out / f"src/{name}.py").write_text("x = 1\n")
    plans = out / ".process-work/plans"
    plans.mkdir(parents=True, exist_ok=True)
    (plans / f"2026-09-20-{name}.md").write_text(f"# {name}\n\ntier: {tier}\nissue: #{issue}\n{extra}\n## Decisions\n")
    if reviewed:
        j = out / ".process-work/journal"
        j.mkdir(parents=True, exist_ok=True)
        (j / f"2026-09-20-{name}.md").write_text(
            f"REVIEW work={name} tier={tier} reviewer=fresh model=cross "
            f"independence=bundle,non-implementing verdict=pass round=1\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", f"feat: {name}")
    _git(out, "checkout", "-q", "main")


def test_a_train_merge_archives_the_cleared_plan_and_closes_its_issue(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _active_plan_branch(out, "7-done", issue=7)
    _active_plan_branch(out, "8-open", issue=8, reviewed=False)
    _active_plan_branch(out, "9-multi", issue=9, extra="plan-stays-active: second merge follows\n")
    train = _load_train(out)
    wt, _branch_name, merged, _dropped = train.build_train(out, "main", ["7-done", "8-open", "9-multi"], "t1",
                                                           lambda _m: None)
    try:
        assert merged == ["7-done", "8-open", "9-multi"]
        log = _git(wt, "log", "--format=%B%x00", "main..HEAD").stdout
        assert "Closes #7" in log and "#8" not in log and "#9" not in log
        assert (wt / ".process-work/plans/archive/2026-09-20-7-done.md").is_file()
        assert not (wt / ".process-work/plans/2026-09-20-7-done.md").exists()
        assert (wt / ".process-work/plans/2026-09-20-8-open.md").is_file()   # not cleared: stays active
        assert (wt / ".process-work/plans/2026-09-20-9-multi.md").is_file()  # says it stays
        # the chain stays merges only: the archive lives inside the merge commit
        assert _git(wt, "rev-list", "--first-parent", "--no-merges", "main..HEAD").stdout.strip() == ""
    finally:
        _git(out, "worktree", "remove", "--force", str(wt))


def test_a_train_merge_carries_dod_deviations_and_keeps_open_issues_open(render, tmp_path):
    # #217 AC-1/AC-2: rule 7 puts a DoD deviation in the merge-commit body —
    # the train writes that body, so the plan's lines ride along verbatim; a
    # line that leaves an AC open or the work continuing turns Closes into Refs
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _active_plan_branch(out, "50-gap", issue=50, extra=(
        "- DoD-deviation: D3 docs follow in the README pass — owner asked to split\n"
        "```\nDoD-deviation: an example in a fence — not a declaration\n```\n"))
    _active_plan_branch(out, "51-open", issue=51, extra=(
        "**DoD-deviation**: open AC-3 — the export waits for #60, then fixes #51\n"))
    _active_plan_branch(out, "52-more", issue=52, extra=(
        "DoD-deviation: continues #52 — the second merge adds the CLI\n"))
    _active_plan_branch(out, "53-named", issue=53, extra=(
        "DoD-deviation: open AC-2 of #54 — tracked on the sibling issue\n"))
    logged = []
    train = _load_train(out)
    wt, _b, merged, _d = train.build_train(out, "main", ["50-gap", "51-open", "52-more", "53-named"], "t9",
                                           logged.append)
    try:
        assert merged == ["50-gap", "51-open", "52-more", "53-named"]
        msgs = {m.strip().split("\n", 1)[0]: m.strip() for m in
                _git(wt, "log", "--first-parent", "--format=%B%x00", "main..HEAD").stdout.split("\x00") if m.strip()}
        assert msgs["train: merge 50-gap"] == (
            "train: merge 50-gap\n\n"
            "- DoD-deviation: D3 docs follow in the README pass — owner asked to split\n\n"
            "Closes #50")
        assert msgs["train: merge 51-open"] == (
            "train: merge 51-open\n\n**DoD-deviation**: open AC-3 — the export waits for #60, then fixes issue 51"
            "\n\nRefs #51")  # a closing keyword copied as is would close #51 on GitHub
        assert msgs["train: merge 52-more"].endswith("the second merge adds the CLI\n\nRefs #52")
        # the AC is open on #54, not on the plan's own issue: #53 closes
        assert msgs["train: merge 53-named"].endswith("sibling issue\n\nCloses #53")
        assert "Closes #51" not in "".join(msgs.values()) and "Closes #52" not in "".join(msgs.values())
        assert any("#51 stays open" in line for line in logged), logged
        assert any("#52 stays open" in line for line in logged), logged
    finally:
        _git(out, "worktree", "remove", "--force", str(wt))


def test_a_spec_plans_dod_deviation_rides_along_and_plan_shows_the_count(render, tmp_path):
    # #217 AC-1 (spec plan) and AC-3: `train.py plan` says how many lines ride
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _active_plan_branch(out, "55-dev", issue=55, extra="DoD-deviation: open AC-1 — a\nDoD-deviation: D8 — b\n")
    _git(out, "checkout", "-q", "-b", "56-spec", "main")
    spec = out / "specs/56-export/plan.md"
    spec.parent.mkdir(parents=True)
    spec.write_text("# export\n\ntier: 1\nissue: #56\n\nDoD-deviation: D7 evidence on the issue — no browser\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "feat: export spec")
    _git(out, "checkout", "-q", "main")
    shown = _train(out, "plan")
    assert shown.returncode == 0, shown.stderr
    line = {ln.split()[1]: ln for ln in shown.stdout.splitlines() if ln.startswith("  ")
            and ln.split()[1] in ("55-dev", "56-spec")}
    assert "2 DoD deviation(s), keeps #55 open" in line["55-dev"], shown.stdout
    assert "1 DoD deviation(s))" in line["56-spec"], shown.stdout
    train = _load_train(out)
    wt, _b, merged, _d = train.build_train(out, "main", ["56-spec"], "t10", lambda _m: None)
    try:
        assert merged == ["56-spec"]
        body = _git(wt, "log", "-1", "--format=%B").stdout
        assert body.startswith("train: merge 56-spec\n\nDoD-deviation: D7 evidence on the issue — no browser"), body
    finally:
        _git(out, "worktree", "remove", "--force", str(wt))


def test_a_train_merge_leaves_another_works_plan_alone(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    plans = out / ".process-work/plans"
    plans.mkdir(parents=True, exist_ok=True)
    (plans / "2026-09-01-older.md").write_text("# older\n\ntier: 1\nissue: #3\n\n## Decisions\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "an older plan on main")
    _git(out, "checkout", "-q", "-b", "10-touch", "main")
    (plans / "2026-09-01-older.md").write_text("# older\n\ntier: 1\nissue: #3\n\n## Decisions\n- a note\n")
    _git(out, "commit", "-q", "-am", "touch the older plan")
    _git(out, "checkout", "-q", "main")
    train = _load_train(out)
    wt, _b, merged, _d = train.build_train(out, "main", ["10-touch"], "t2", lambda _m: None)
    try:
        assert merged == ["10-touch"]
        assert (wt / ".process-work/plans/2026-09-01-older.md").is_file()
        assert "Closes" not in _git(wt, "log", "-1", "--format=%B").stdout
    finally:
        _git(out, "worktree", "remove", "--force", str(wt))


def _plan_on_main(out, name, body):
    plans = out / ".process-work/plans"
    plans.mkdir(parents=True, exist_ok=True)
    (plans / name).write_text(body)
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", f"plan {name} on main")


def _settle(out, branches, stamp):
    train = _load_train(out)
    wt, _b, merged, dropped = train.build_train(out, "main", branches, stamp, lambda _m: None)
    msgs = _git(wt, "log", "--format=%B%x00", "main..HEAD").stdout
    return wt, merged, dropped, msgs


def test_another_works_plan_renamed_or_named_like_the_branch_is_not_finished(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _plan_on_main(out, "2026-09-01-login.md", "# login\n\ntier: 1\nissue: #3\n\n- [ ] open\n")
    _git(out, "checkout", "-q", "-b", "12-login-typo", "main")  # names "login", issue 12
    _git(out, "mv", ".process-work/plans/2026-09-01-login.md", ".process-work/plans/2026-09-02-login.md")
    _git(out, "commit", "-q", "-m", "rename another work's plan")
    _git(out, "checkout", "-q", "main")
    wt, merged, _d, msgs = _settle(out, ["12-login-typo"], "t3")
    try:
        assert merged == ["12-login-typo"] and "Closes" not in msgs
        assert (wt / ".process-work/plans/2026-09-02-login.md").is_file()
    finally:
        _git(out, "worktree", "remove", "--force", str(wt))


def test_a_plan_without_tier_or_with_open_tasks_is_not_finished(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _active_plan_branch(out, "13-notier", issue=13, tier=1)
    _git(out, "checkout", "-q", "13-notier")
    p = out / ".process-work/plans/2026-09-20-13-notier.md"
    p.write_text(p.read_text().replace("tier: 1", "Risk tier 1"))
    _git(out, "commit", "-q", "-am", "no tier line")
    _git(out, "checkout", "-q", "main")
    _active_plan_branch(out, "14-open", issue=14, tier=1, extra="- [x] a\n- [ ] b\n")
    _active_plan_branch(out, "15-bold", issue=15, tier=1, extra="- **plan-stays-active**: part two follows\n")
    wt, merged, _d, msgs = _settle(out, ["13-notier", "14-open", "15-bold"], "t4")
    try:
        assert len(merged) == 3 and "Closes" not in msgs
    finally:
        _git(out, "worktree", "remove", "--force", str(wt))


def test_the_merge_commit_skips_the_pre_commit_hook(render, tmp_path, monkeypatch):
    # the old `git merge` auto-commit ran no pre-commit hook; the merge commit
    # after --no-commit must not either, or a broken hook install empties the
    # train (refutation). Git runs no hooks in this test environment, so the
    # call itself is pinned.
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _active_plan_branch(out, "16-a", issue=16)
    train = _load_train(out)
    calls = []
    real = train._git

    def spy(root, *args, **kw):
        calls.append(args)
        return real(root, *args, **kw)

    monkeypatch.setattr(train, "_git", spy)
    wt, _b, merged, _d = train.build_train(out, "main", ["16-a"], "t5", lambda _m: None)
    try:
        commits = [a for a in calls if a and a[0] == "commit"]
        assert merged == ["16-a"] and commits and all("--no-verify" in a for a in commits)
    finally:
        _git(out, "worktree", "remove", "--force", str(wt))


def test_a_stacked_passenger_already_contained_counts_as_merged(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _git(out, "checkout", "-q", "-b", "40-a", "main")
    (out / "a.txt").write_text("a\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "a")
    _git(out, "checkout", "-q", "-b", "41-b")
    (out / "b.txt").write_text("b\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "b")
    _git(out, "checkout", "-q", "main")
    # pinned (#391): 40-a moves on after boarding — its boarded SHA is in 41-b, the new one is not
    shas = {b: _git(out, "rev-parse", b).stdout.strip() for b in ("40-a", "41-b")}
    _move(out, "40-a", files={"late.txt": "late\n"})
    train = _load_train(out)
    wt, _b, merged, dropped = train.build_train(out, _git(out, "rev-parse", "main").stdout.strip(),
                                                ["41-b", "40-a"], "t6", lambda _m: None, shas=shas)
    try:
        assert merged == ["41-b", "40-a"] and not dropped
        assert not (wt / "late.txt").exists()
    finally:
        _git(out, "worktree", "remove", "--force", str(wt))


def test_interpreter_options_are_not_taken_for_the_suite_file(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    train = _load_train(out)
    import shlex
    cases = {"bash -eo pipefail scripts/t.sh": ["scripts/t.sh"], "bash -euxo pipefail scripts/t.sh": ["scripts/t.sh"],
             "node -r ts-node/register x.js": ["x.js"], "perl -I vendor/lib t.pl": ["t.pl"],
             "perl -e 'print 1'": [], "node -e 'x'": [], "bash -e scripts/t.sh": ["scripts/t.sh"],
             # final refute: options are the interpreter's own, attached values are values
             "python3 -I -m pytest": [], "python3 -I tests/run.py": ["tests/run.py"],
             "bash -r scripts/t.sh": ["scripts/t.sh"], "perl -X t/run.pl": ["t/run.pl"],
             "ruby -Itest test/all.rb": ["test/all.rb"], "ruby -rbundler/setup t.rb": ["t.rb"],
             "perl -MTest::More t/run.pl": ["t/run.pl"], "perl -Ilib/proto t/run.pl -v": ["t/run.pl"],
             "node --experimental-loader ./loader.mjs test/run.js": ["test/run.js"],
             "bash -O extglob s.sh": ["s.sh"], "bash --rcfile x s.sh": ["s.sh"]}
    for cmd, files in cases.items():
        assert train._entry_files(shlex.split(cmd)) == files, cmd


def test_another_repositorys_issue_is_not_closed_and_a_paired_new_plan_is_own(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _active_plan_branch(out, "17-ext", issue=7, tier=1)
    _git(out, "checkout", "-q", "17-ext")
    p = out / ".process-work/plans/2026-09-20-17-ext.md"
    p.write_text(p.read_text().replace("issue: #7", "issue: acme/lib#7"))
    _git(out, "commit", "-q", "-am", "the issue lives elsewhere")
    _git(out, "checkout", "-q", "main")
    body = "# plan\n\ntier: 1\nissue: #{n}\n\nsome shared words for a similar file\n" * 3
    _plan_on_main(out, "2026-09-01-old.md", body.format(n=20))
    _git(out, "checkout", "-q", "-b", "21-new", "main")
    _git(out, "rm", "-q", ".process-work/plans/2026-09-01-old.md")
    (out / ".process-work/plans/2026-09-21-new.md").write_text(body.format(n=22))
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "replace the old plan with a new one")
    _git(out, "checkout", "-q", "main")
    wt, merged, _d, msgs = _settle(out, ["17-ext", "21-new"], "t7")
    try:
        assert len(merged) == 2
        assert "Closes #7" not in msgs and "Closes #22" in msgs and "Closes #20" not in msgs
    finally:
        _git(out, "worktree", "remove", "--force", str(wt))


# --- a package branch of a larger issue: its issues are the ones dispatch placed on it ---

def _package_branch(out, name, work):
    """A branch named after the epic, attested under its package's issue —
    its plan not archived yet: it boards on its worker's review-pass report."""
    _git(out, "checkout", "-q", "-b", name, "main")
    (out / "src").mkdir(exist_ok=True)
    (out / "src/pkg.py").write_text("pkg = 1\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "feat: package")
    head = _git(out, "rev-parse", "HEAD").stdout.strip()
    j = out / ".process-work/journal"
    j.mkdir(parents=True, exist_ok=True)
    (j / f"2026-09-21-{name}.md").write_text(_head_pass(out, work, head))
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "attest")
    _git(out, "checkout", "-q", "main")


def _report(out, worker, issue=None, state="review-pass", *flags, note=""):
    extra = ["--issue", str(issue)] if issue is not None else []
    extra += ["--note", note] if note else []
    subprocess.run([sys.executable, str(out / "scripts/process/report.py"), state, "--worker", worker,
                    *extra, *flags], cwd=out, check=True, capture_output=True)


def _dispatched(out, issue, branch):
    """What `dispatch start --issue <issue> --branch <branch>` records."""
    subprocess.run([sys.executable, "-c", "import sys; from pathlib import Path; "
                    "sys.path.insert(0, 'scripts/process'); import dispatch; "
                    f"dispatch._remember_issue(Path('.'), {issue}, {branch!r})"],
                   cwd=out, check=True, capture_output=True, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})


def _candidate(out, name):
    return next(c for c in json.loads(_train(out, "plan", "--json").stdout)["candidates"] if c["branch"] == name)


def test_a_package_branch_boards_on_the_issue_dispatch_placed_on_it(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _package_branch(out, "70-p1-slice", "71")
    _report(out, "70-p1-slice")
    # the name carries the epic's number only: the package's pass is not its own
    c = _candidate(out, "70-p1-slice")
    assert not c["eligible"] and "no REVIEW pass for its own work" in c["reasons"][0], c
    # a worker's own claim is not the record: the report names the issue, dispatch did not
    _report(out, "70-p1-slice", issue=71)
    assert not _candidate(out, "70-p1-slice")["eligible"]
    _dispatched(out, 71, "70-p1-slice")
    c = _candidate(out, "70-p1-slice")
    assert c["eligible"] and "worker report review-pass" in c["by"], c


# --- a `blocked` report holds the branch (#326) ---

def test_a_blocked_report_keeps_a_cleared_branch_off_the_train(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    assert _candidate(out, "alpha")["eligible"]
    _report(out, "alpha", None, "blocked", note="steward: wait for #12")
    c = _candidate(out, "alpha")
    assert not c["eligible"], c
    held = [r for r in c["reasons"] if "latest report `blocked`" in r]
    assert held and "steward: wait for #12" in held[0] and "min ago" in held[0], c
    assert "`report.py pushed` after the fix, or `review-pass`, releases it" in held[0]
    assert c["by"] == "archived plan + REVIEW pass"  # the arms still run and say their part


@pytest.mark.parametrize("release", ["review-pass", "pushed"])
def test_a_later_pushed_or_review_pass_releases_a_blocked_branch(render, tmp_path, release):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    _report(out, "alpha", None, "blocked", note="steward: red on the steward's host")
    assert not _candidate(out, "alpha")["eligible"]
    # no origin here: `pushed` is recorded unverified — the hold reads the state
    _report(out, "alpha", None, release, *(["--force"] if release == "pushed" else []))
    c = _candidate(out, "alpha")
    assert c["eligible"] and not any("blocked" in r for r in c["reasons"]), c


@pytest.mark.parametrize("later", ["idle", "planned"])
def test_a_later_idle_or_planned_report_does_not_release_a_blocked_branch(render, tmp_path, later):
    # `dispatch stop` writes `idle`: stopping the session must not lift the hold
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    _report(out, "alpha", None, "blocked", note="steward hold")
    _report(out, "alpha", None, later)
    c = _candidate(out, "alpha")
    assert not c["eligible"] and any("latest report `blocked`" in r for r in c["reasons"]), c


def test_another_workers_blocked_report_does_not_hold_the_branch(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    _report(out, "beta", None, "blocked", note="not alpha's")
    c = _candidate(out, "alpha")
    assert c["eligible"] and not any("blocked" in r for r in c["reasons"]), c


def test_a_blocked_report_another_host_published_holds_the_branch(render, tmp_path):
    # the steward on another machine ran `report.py blocked --sync`: the train's
    # host sees it as the published ref `refs/process/reports/<host>`
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    line = json.dumps({"ts": "2026-10-27T10:00:00+0000", "epoch": int(time.time()), "host": "steward-elsewhere",
                       "worker": "alpha", "branch": "alpha", "issue": None, "state": "blocked",
                       "note": "held on the steward's host"})
    blob = subprocess.run(["git", "hash-object", "-w", "--stdin"], cwd=out, input=line + "\n",
                          capture_output=True, text=True, check=True).stdout.strip()
    _git(out, "update-ref", "refs/process/reports/steward-elsewhere", blob)
    c = _candidate(out, "alpha")
    assert not c["eligible"], c
    assert any("latest report `blocked`" in r and "held on the steward's host" in r for r in c["reasons"]), c


@pytest.mark.parametrize("record", [{"state": "blocked"},
                                    {"worker": "alpha", "state": "blocked", "epoch": "x"},
                                    {"worker": "", "state": "blocked", "epoch": 1},
                                    {"worker": "alpha", "state": "blocked", "epoch": True}])
def test_a_published_report_without_worker_or_numeric_epoch_is_skipped(render, tmp_path, record):
    """Fix round 1: another host's ref is data the train reads; a record without a worker
    or with a non-numeric epoch crashed `plan` — it is skipped like an unparsable line."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    blob = subprocess.run(["git", "hash-object", "-w", "--stdin"], cwd=out,
                          input=json.dumps(record) + "\n", capture_output=True, text=True,
                          check=True).stdout.strip()
    _git(out, "update-ref", "refs/process/reports/elsewhere", blob)
    r = _train(out, "plan", "--json")
    assert r.returncode == 0 and "Traceback" not in r.stderr, r.stderr
    c = next(c for c in json.loads(r.stdout)["candidates"] if c["branch"] == "alpha")
    assert c["eligible"] and not any("blocked" in why for why in c["reasons"]), c


def test_plan_without_origin_runs_and_notes_the_failed_report_fetch(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    r = _train(out, "plan", "--json")
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["candidates"][0]["eligible"]  # best effort: nothing held for it
    assert "could not fetch the published reports" in r.stderr, r.stderr


def _slug_branch(out, branch, plan, *, issue, work, files, on_main=False):
    """An active plan with `issue: #<issue>` and a REVIEW pass `work=<work>`;
    `on_main` puts the plan on main first, the branch only touches it."""
    plans = out / ".process-work/plans"
    plans.mkdir(parents=True, exist_ok=True)
    if on_main:
        (plans / plan).write_text(f"# p\n\ntier: 2\nissue: #{issue}\n\n## Decisions\n")
        _git(out, "add", "-A")
        _git(out, "commit", "-q", "-m", "plan on main")
    _git(out, "checkout", "-q", "-b", branch, "main")
    (plans / plan).write_text(f"# p\n\ntier: 2\nissue: #{issue}\n\n## Decisions\n- touched\n")
    for rel, text in files.items():
        (out / rel).parent.mkdir(parents=True, exist_ok=True)
        (out / rel).write_text(text)
    j = out / ".process-work/journal"
    j.mkdir(parents=True, exist_ok=True)
    (j / f"2026-10-01-{branch}.md").write_text(
        f"REVIEW work={work} tier=2 reviewer=fresh model=cross "
        f"independence=bundle,non-implementing verdict=pass round=1\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", f"feat: {branch}")
    _git(out, "checkout", "-q", "main")


@pytest.mark.parametrize("work", ["2260-work-expiry", "2026-10-01-2260-work-expiry"])
@pytest.mark.parametrize("gate_code", [False, True])
def test_an_active_plans_slug_or_stem_is_the_branchs_own_work(render, tmp_path, work, gate_code):
    """#199 (downstream): the train counted a plan's ids only once archived — an
    active plan with `work=<slug>` was refused, though attest accepted the id."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    files = {"src/expiry.py": "x = 1\n"}
    if gate_code:
        files["scripts/process/extra.py"] = "y = 1\n"
    _slug_branch(out, "issue-2260", "2026-10-01-2260-work-expiry.md", issue=2260, work=work, files=files)
    _report(out, "issue-2260")
    c = _candidate(out, "issue-2260")
    assert c["eligible"] and "worker report review-pass" in c["by"], c


def test_another_issues_active_plan_lends_the_branch_no_work_id(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _slug_branch(out, "issue-2260", "2026-10-01-2300-other.md", issue=2300, work="2300-other",
                 files={"src/expiry.py": "x = 1\n"}, on_main=True)
    _report(out, "issue-2260")
    c = _candidate(out, "issue-2260")
    assert not c["eligible"] and "no REVIEW pass for its own work" in " ".join(c["reasons"]), c


@pytest.mark.parametrize("where", [".process-work/plans", ".process-work/plans/archive"])
def test_a_shared_slug_does_not_board_but_the_stem_does(render, tmp_path, where):
    """The gate takes a slug among the active plans now, and in the archive once
    the merge archives the plan (refute #199: an archived namesake boarded)."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    a = out / where
    a.mkdir(parents=True, exist_ok=True)
    (a / "2026-01-01-2260-work-expiry.md").write_text("# old\n\ntier: 2\nissue: #1\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "another active plan with the same slug")
    _slug_branch(out, "issue-2260", "2026-10-01-2260-work-expiry.md", issue=2260, work="2260-work-expiry",
                 files={"src/expiry.py": "x = 1\n"})
    _report(out, "issue-2260")
    assert not _candidate(out, "issue-2260")["eligible"]
    j = out / ".process-work/journal/2026-10-02.md"
    _git(out, "checkout", "-q", "issue-2260")
    j.write_text("REVIEW work=2026-10-01-2260-work-expiry tier=2 reviewer=fresh model=cross "
                 "independence=bundle,non-implementing verdict=pass round=2\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "attest the stem")
    _git(out, "checkout", "-q", "main")
    assert _candidate(out, "issue-2260")["eligible"]


def test_an_issue_on_another_branch_opens_no_pass(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _package_branch(out, "70-p2-slice", "72")
    _report(out, "70-p2-slice")
    _dispatched(out, 72, "someone-else")
    _dispatched(out, 73, "70-p2-slice")
    assert not _candidate(out, "70-p2-slice")["eligible"]


def _spec_split_branch(out, branch, reviews):
    """#218 (downstream): one issue split into two stacked Spec Kit plans on
    one branch, each with its own code. `reviews` are (work, the plan whose
    commit the review saw up to) — full rounds from the fork point (#160),
    attested after the last plan."""
    _git(out, "checkout", "-q", "-b", branch, "main")
    heads = {}
    for slug, src in (("2334-a-split", "src/a.py"), ("2334-b-split", "src/b.py")):
        d = out / "specs" / slug
        d.mkdir(parents=True, exist_ok=True)
        (d / "plan.md").write_text(f"# {slug}\n\ntier: 2\nissue: #2334\n\n## Decisions\n")
        (out / src).parent.mkdir(exist_ok=True)
        (out / src).write_text("x = 1\n")
        _git(out, "add", "-A")
        _git(out, "commit", "-q", "-m", f"feat: {slug}")
        heads[slug] = _git(out, "rev-parse", "HEAD").stdout.strip()
    j = out / ".process-work/journal"
    j.mkdir(parents=True, exist_ok=True)
    (j / f"2026-10-12-{branch}.md").write_text("".join(
        _head_pass(out, work, heads[head]) for work, head in reviews))
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "attest")
    _git(out, "checkout", "-q", "main")


@pytest.mark.parametrize("reviews, missing", [
    ([("2334-a-split", "2334-a-split"), ("2334-b-split", "2334-b-split")], None),
    ([("2334-b-split", "2334-b-split")], "2334-a-split"),
    ([("2334-a-split", "2334-b-split")], "2334-b-split"),
], ids=["each-plan-reviewed", "b-review-saw-both", "a-review-saw-both"])
def test_each_spec_plan_of_a_split_issue_needs_its_own_review(render, tmp_path, reviews, missing):
    """#218: a Spec Kit plan's slug is the branch's own work id (AC-1), and each
    Tier 2+ spec plan needs a clearing REVIEW of its own — one plan's review does
    not clear the other, even where its range saw both (AC-2)."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _spec_split_branch(out, "issue-2334", reviews)
    _report(out, "issue-2334")
    c = _candidate(out, "issue-2334")
    if missing is None:
        assert c["eligible"] and "worker report review-pass" in c["by"], c["reasons"]
    else:
        assert not c["eligible"], c
        assert f"specs/{missing}/plan.md" in c["reasons"][0] and "its own" in c["reasons"][0], c


def _base_plan(out, stem, issue):
    p = out / ".process-work/plans"
    p.mkdir(parents=True, exist_ok=True)
    (p / f"{stem}.md").write_text(f"# {stem}\n\ntier: 2\nissue: #{issue}\n\n- [ ] do it\n\n## Decisions\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", f"plan {stem}")


def _package_on_base_plan(out, name, work, stem, *, archive=False):
    """The package's plan was written on main; the branch ticks (or archives)
    it and attests work=<package issue> at its head."""
    _git(out, "checkout", "-q", "-b", name, "main")
    (out / "src").mkdir(exist_ok=True)
    (out / f"src/{name}.py").write_text("x = 1\n")
    plan = out / f".process-work/plans/{stem}.md"
    plan.write_text(plan.read_text().replace("- [ ] do it", "- [x] do it"))
    _git(out, "add", "-A")
    if archive:
        (out / ".process-work/plans/archive").mkdir(parents=True, exist_ok=True)
        _git(out, "mv", str(plan), str(out / f".process-work/plans/archive/{stem}.md"))
    _git(out, "commit", "-q", "-m", "work")
    head = _git(out, "rev-parse", "HEAD").stdout.strip()
    j = out / ".process-work/journal"
    j.mkdir(parents=True, exist_ok=True)
    (j / f"2026-09-21-{name}.md").write_text(_head_pass(out, work, head))
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "attest")
    _git(out, "checkout", "-q", "main")


def _merge_messages(out, branch):
    train = _load_train(out)
    wt, _b, merged, _d = train.build_train(out, "main", [branch], "t1", lambda _m: None)
    try:
        assert merged == [branch]
        return (_git(wt, "log", "--format=%B%x00", "main..HEAD").stdout,
                sorted(p.name for p in (wt / ".process-work/plans").glob("*.md")))
    finally:
        _git(out, "worktree", "remove", "--force", str(wt))


@pytest.mark.parametrize("archive", [False, True])
def test_the_merge_closes_the_issue_the_branch_boarded_on(render, tmp_path, archive):
    # boarding, the branch's own plans and the issue its merge closes answer
    # one question — the train boarded on #71 and closed nothing (refutation)
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _base_plan(out, "2026-09-20-p1", 71)
    _package_on_base_plan(out, "70-p1-slice", "71", "2026-09-20-p1", archive=archive)
    _report(out, "70-p1-slice")
    _dispatched(out, 71, "70-p1-slice")
    c = _candidate(out, "70-p1-slice")
    assert c["eligible"] and not c.get("housekeeping"), c
    messages, active = _merge_messages(out, "70-p1-slice")
    assert "Closes #71" in messages and "#70" not in messages, messages
    assert "2026-09-20-p1.md" not in active


# --- second refutation: the map is find_branch's, merged branches are forgotten, reading has no side effects ---

def _dispatch_module(out):
    import importlib.util
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(out / "scripts/process"))
    spec = importlib.util.spec_from_file_location("dispatch_under_test", out / "scripts/process/dispatch.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _records_dir(out):
    d = out / ".git/process-dispatch"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _stale_record(out, branch, issue):
    """A dispatch record whose worker is gone and that nobody stopped."""
    (_records_dir(out) / f"{branch.replace('/', '__')}.json").write_text(json.dumps(
        {"branch": branch, "issue": issue, "phase": "execute", "pid": 999999999, "started": 1}))


def test_an_issue_re_dispatched_elsewhere_leaves_its_old_branch(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _package_branch(out, "70-p2-slice", "72")
    _report(out, "70-p2-slice")
    _stale_record(out, "70-p2-slice", 72)
    _dispatched(out, 72, "70-p2-new")
    d = _dispatch_module(out)
    assert d.find_branch(out, 72) == "70-p2-new" and 72 not in d.issues_of(out, "70-p2-slice")
    assert not _candidate(out, "70-p2-slice")["eligible"]


def test_a_merged_branch_is_forgotten_so_its_name_starts_clean(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _base_plan(out, "2026-09-20-p1", 71)
    _package_on_base_plan(out, "70-p1-slice", "71", "2026-09-20-p1")
    _report(out, "70-p1-slice")
    _dispatched(out, 71, "70-p1-slice")
    _stale_record(out, "70-p1-slice", 71)
    r = _train(out, "run", "--force", "--suite", "true")
    assert r.returncode == 0, r.stdout[-800:] + r.stderr[-800:]
    d = _dispatch_module(out)
    assert d.issues_of(out, "70-p1-slice") == set() and d.find_branch(out, 71) != "70-p1-slice"
    assert not (_records_dir(out) / "70-p1-slice.json").exists()


def test_reading_the_branch_issues_creates_nothing_and_skips_a_broken_record(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _package_branch(out, "70-p1-slice", "71")
    assert _train(out, "plan", "--json").returncode == 0
    assert not (out / ".git/process-dispatch").exists()
    (_records_dir(out) / "weird.json").mkdir()
    (_records_dir(out) / "bad.json").write_text("{not json")
    r = _train(out, "plan", "--json")
    assert r.returncode == 0, r.stderr[-600:]


# --- third refutation: the merged issue is done everywhere; bookkeeping never aborts a landed train ---

def test_a_merged_issue_does_not_return_to_its_abandoned_branch(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _base_plan(out, "2026-09-20-p1", 71)
    _package_on_base_plan(out, "70-p1-slice", "71", "2026-09-20-p1")
    _report(out, "70-p1-slice")
    _stale_record(out, "70-p1-old", 71)  # the first placement: its worker died, nobody stopped it
    _dispatched(out, 71, "70-p1-slice")
    r = _train(out, "run", "--force", "--suite", "true")
    assert r.returncode == 0, r.stdout[-800:] + r.stderr[-800:]
    d = _dispatch_module(out)
    assert d.find_branch(out, 71) is None and d.issues_of(out, "70-p1-old") == set()


def test_forgetting_keeps_a_live_or_unaskable_worker_and_ignores_a_boolean_issue(render, tmp_path, monkeypatch):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    d = _dispatch_module(out)
    _stale_record(out, "70-live", 71)
    _stale_record(out, "70-unknown", 71)
    (_records_dir(out) / "70-bool.json").write_text(json.dumps({"branch": "70-bool", "issue": True}))
    assert d.find_branch(out, 1) is None  # True is not issue 1
    _dispatched(out, 71, "70-slice")
    states = {"70-live": ("live", True), "70-unknown": ("unknown", False)}
    real = d.records

    def records(root):
        recs = real(root)
        for rec in recs:
            if rec["branch"] in states:
                rec["state"], rec["alive"] = states[rec["branch"]]
        return recs

    monkeypatch.setattr(d, "records", records)
    d.forget_branch(out, "70-slice")
    assert (_records_dir(out) / "70-live.json").is_file() and (_records_dir(out) / "70-unknown.json").is_file()


@pytest.mark.parametrize("error", ["OSError(28, 'No space left on device')", "ValueError('No space left: bad map')"])
def test_an_unwritable_issue_map_does_not_abort_a_landed_train(render, tmp_path, error):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    # the rendered dispatch of this scratch repo cannot write its map (a full
    # disk, a read-only .git): forgetting raises
    d = out / "scripts/process/dispatch.py"
    d.write_text(d.read_text() + "\n\ndef forget_branch(root, branch):\n"
                 f"    raise {error}\n")
    _git(out, "commit", "-q", "-am", "a dispatch whose map cannot be written")
    r = _train(out, "run", "--force", "--suite", "true")
    assert r.returncode == 0, r.stdout[-800:] + r.stderr[-800:]
    assert "train: merge alpha" in _git(out, "log", "--oneline", "main").stdout
    assert "could not forget it" in r.stderr and "No space left" in r.stderr
    assert "alpha" not in _git(out, "branch", "--list", "--format=%(refname:short)").stdout.split()


# --- fourth refutation: a malformed record, a remote worker ---

@pytest.mark.parametrize("issue", [[71], {"n": 71}, 71.0])
def test_a_malformed_record_neither_aborts_nor_is_taken_for_the_issue(render, tmp_path, issue):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _base_plan(out, "2026-09-20-p1", 71)
    _package_on_base_plan(out, "70-p1-slice", "71", "2026-09-20-p1")
    _report(out, "70-p1-slice")
    _dispatched(out, 71, "70-p1-slice")
    (_records_dir(out) / "zz-broken.json").write_text(json.dumps({"branch": "zz-broken", "issue": issue, "pid": 999999999}))
    r = _train(out, "run", "--force", "--suite", "true")
    assert r.returncode == 0, r.stdout[-800:] + r.stderr[-800:]
    assert (_records_dir(out) / "zz-broken.json").is_file()  # not this issue's record


def test_a_remote_worker_of_the_merged_issue_keeps_its_record(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _base_plan(out, "2026-09-20-p1", 71)
    _package_on_base_plan(out, "70-p1-slice", "71", "2026-09-20-p1")
    _report(out, "70-p1-slice")
    _dispatched(out, 71, "70-p1-slice")
    (_records_dir(out) / "70-p1-remote.json").write_text(
        json.dumps({"branch": "70-p1-remote", "issue": 71, "remote": True}))
    r = _train(out, "run", "--force", "--suite", "true")
    assert r.returncode == 0, r.stdout[-800:] + r.stderr[-800:]
    assert (_records_dir(out) / "70-p1-remote.json").is_file()


def test_a_kept_remote_record_does_not_bring_the_merged_issue_back(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _base_plan(out, "2026-09-20-p1", 71)
    _package_on_base_plan(out, "70-p1-slice", "71", "2026-09-20-p1")
    _report(out, "70-p1-slice")
    (_records_dir(out) / "70-p1-old.json").write_text(json.dumps({"branch": "70-p1-old", "issue": 71, "remote": True}))
    _dispatched(out, 71, "70-p1-slice")
    assert _train(out, "run", "--force", "--suite", "true").returncode == 0
    d = _dispatch_module(out)
    assert d.find_branch(out, 71) is None and d.issues_of(out, "70-p1-old") == set()
    assert (_records_dir(out) / "70-p1-old.json").is_file()  # the worker on the other host keeps its record
    # dispatched again, the issue lives on its new branch
    _dispatched(out, 71, "70-p1-again")
    assert d.find_branch(out, 71) == "70-p1-again"


def test_the_train_marks_only_its_own_push_to_main(render, tmp_path):
    # the pre-push guard (merge_route.py) refuses a push to main without a route; the
    # train names it for that one push and strips a marker it inherited from every
    # other git call (the branch deletion, the staging worktree's checkout)
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    _repo(out)
    bare = tmp_path / "origin.git"
    _git(out, "clone", "-q", "--bare", str(out), str(bare))
    _git(out, "remote", "add", "origin", str(bare))
    _git(out, "fetch", "-q", "origin")
    _git(out, "branch", "-q", "--set-upstream-to=origin/main", "main")
    _branch(out, "alpha", {"src/a.py": "a\n"})
    _git(out, "push", "-q", "origin", "alpha")
    seen = tmp_path / "seen.log"
    hooks = out / ".git/hooks"
    (hooks / "post-checkout").write_text(
        f'#!/bin/sh\necho "post-checkout ${{PROCESS_MERGE_ROUTE:-unset}}" >> "{seen}"\n')
    (hooks / "pre-push").write_text(
        "#!/bin/sh\ntargets=''\n"
        "while read lref lsha rref rsha; do targets=\"$targets $rref\"; "
        f'echo "push $rref ${{PROCESS_MERGE_ROUTE:-unset}}" >> "{seen}"; done\n'
        f'exec "{sys.executable}" scripts/process/merge_route.py $targets\n')
    for hook in ("post-checkout", "pre-push"):
        (hooks / hook).chmod(0o755)
    env = {k: v for k, v in os.environ.items() if not k.startswith(("PROCESS_", "SKIP"))}
    r = subprocess.run([sys.executable, str(out / "scripts/process/train.py"), "run", "--force",
                        "--push", "--suite", "true"], cwd=out, capture_output=True, text=True,
                       env={**env, "PROCESS_MERGE_ROUTE": "inherited"})
    assert r.returncode == 0, r.stdout[-800:] + r.stderr[-800:]
    lines = seen.read_text().splitlines()
    assert "push refs/heads/main train" in lines
    assert "push refs/heads/alpha unset" in lines  # the merged branch's deletion is no merge
    assert "post-checkout unset" in lines
    assert not [ln for ln in lines if ln.endswith("inherited")], lines


def test_a_pushed_train_removes_the_merged_worktrees_that_hold_no_work(render, tmp_path):
    # #136: a worktree per dispatched issue, each with its own venv, was never removed
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    (out / ".gitignore").write_text("venv/\n")
    _repo(out)
    bare = tmp_path / "origin.git"
    _git(out, "clone", "-q", "--bare", str(out), str(bare))
    _git(out, "remote", "add", "origin", str(bare))
    _git(out, "fetch", "-q", "origin")
    _git(out, "branch", "-q", "--set-upstream-to=origin/main", "main")
    wts = {}
    for name in ("alpha", "beta", "gamma"):
        _branch(out, name, {f"src/{name}.py": f"{name}\n"})
        wts[name] = tmp_path / f"repo-{name}"
        _git(out, "worktree", "add", "-q", str(wts[name]), name)
        (wts[name] / "venv").mkdir()
        (wts[name] / "venv/lib.bin").write_bytes(b"x" * 1000)  # ignored: removed with the tree
    shard = wts["beta"] / ".process-work/journal/2026-10-01-beta-notes.md"
    shard.write_text("DECISION not yet committed\n")  # untracked work: never removed automatically
    d = _dispatch_module(out)
    (_records_dir(out) / "gamma.json").write_text(json.dumps({
        "branch": "gamma", "issue": 9, "phase": "review", "worktree": str(wts["gamma"]),
        "pid": os.getpid(), "pid_start": d._proc_start(os.getpid())}))  # a live session on gamma
    r = _train(out, "run", "--force", "--push", "--suite", "true")
    assert r.returncode == 0, r.stdout[-800:] + r.stderr[-800:]
    assert "alpha, beta, gamma (pushed)" in r.stdout
    assert f"worktree {wts['alpha']} of alpha removed" in r.stdout
    assert not wts["alpha"].exists()
    assert f"worktree {wts['beta']} of beta kept — untracked files not ignored" in r.stdout
    assert shard.is_file()
    assert f"worktree {wts['gamma']} of gamma kept — a dispatch session is live" in r.stdout
    assert wts["gamma"].is_dir()
    listed = _git(out, "worktree", "list").stdout
    assert str(wts["alpha"]) not in listed and str(wts["beta"]) in listed
    branches = _git(out, "branch", "--list", "--format=%(refname:short)").stdout.split()
    assert "alpha" not in branches  # its worktree gone, the merged branch could be deleted too



@pytest.mark.parametrize("status,departs", [
    ("scoped: free\nfull: free", True),
    ("scoped: held by pid 1 — pre-push (issue-9) since 09:28 (15 min)\nfull: free", True),
    ("scoped: free\nfull: held by pid 1 — coverage-gate since 09:28 (5 min)", False),
    ("scoped: held by pid 1 — pre-push\nfull: held by pid 2 — test-boundary", False),
    ("gpu: held by pid 1 — render", False),
])
def test_a_held_scoped_lane_does_not_hold_the_train(render, tmp_path, status, departs):
    # the suite runs on `full`, niced beside the short runs; serial pre-pushes
    # on `scoped` starved the train downstream (one departure in a day)
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    (out / "scripts" / "lane.py").write_text(f"print({status!r})\n")
    train = _load_train(out)
    ready, why = train.departure([{"eligible": True, "hours_waiting": 0}], out,
                                 min_candidates=1, max_wait_hours=4)
    assert ready is departs, why
    if not departs:
        assert why.startswith("lane busy")


def _memo_batch(render, tmp_path, monkeypatch, *, seen, red):
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    _repo(out)
    train = _load_train(out)
    if seen:
        train._remember_green_suite(out, train._suite_key(out, "s"))
    runs, current, written = [], [], []
    # one tree per boarding prefix, as real merges give: [] main, [b1], [b1, b2]
    for name, files in (("one", {"a.txt": "a\n"}), ("both", {"a.txt": "a\n", "b.txt": "b\n"})):
        _git(out, "checkout", "-q", "-b", name, "main")
        for rel, text in files.items():
            (out / rel).write_text(text)
        _git(out, "add", "-A")
        _git(out, "commit", "-q", "-m", name)
    _git(out, "checkout", "-q", "main")

    def build(root, base, subset, stamp, log, **kw):
        current[:] = subset
        _git(out, "checkout", "-q", {0: "main", 1: "one", 2: "both"}[len(subset)])
        return out, "train/x", list(subset), []
    monkeypatch.setattr(train, "build_train", build)
    monkeypatch.setattr(train, "_run_gates", lambda *a, **k: True)
    monkeypatch.setattr(train, "_sh", lambda cwd, cmd, log, **kw: runs.append(list(current)) or
                        ("red" if red(current) else "green"))
    monkeypatch.setattr(train, "_cleanup", lambda *a: None)
    monkeypatch.setattr(train, "_write", lambda root, state, *a, **k: written.append(state))
    return out, train, runs, written


@pytest.mark.parametrize("seen", [True, False])
def test_the_bare_base_skips_a_suite_this_train_saw_green(render, tmp_path, monkeypatch, seen):
    # after a red batch the base is checked; it is the tree an earlier train
    # fast-forwarded to — its suite (~26 min downstream) need not run again
    out, train, runs, _w = _memo_batch(render, tmp_path, monkeypatch, seen=seen, red=lambda sub: "b2" in sub)
    p = {"base": "main", "candidates": [{"branch": "b1", "hours_waiting": 2}, {"branch": "b2", "hours_waiting": 1}]}
    with pytest.raises(SystemExit):  # the stub train/x cannot be fast-forwarded; the judging is done
        train._run_batch(out, "main", p, ["b1", "b2"], "x", tmp_path / "t.log", suite="s", deploy=None,
                         push=False, keep_branches=True)
    assert runs[-1] == ["b1"]  # b2 blamed, b1 green
    assert ([] in runs) is not seen  # the bare base ran only without the memo
    assert ("green on an earlier train" in (tmp_path / "t.log").read_text()) is seen


def test_a_remembered_base_runs_before_the_first_passenger_is_blamed(render, tmp_path, monkeypatch):
    # refutation: main turned red outside the tree (a host upgrade) — on the
    # memo alone the first passenger was blamed, then the next, and so on
    out, train, runs, written = _memo_batch(render, tmp_path, monkeypatch, seen=True, red=lambda sub: True)
    p = {"base": "main", "candidates": [{"branch": "b1", "hours_waiting": 1}]}
    rc = train._run_batch(out, "main", p, ["b1"], "x", tmp_path / "t.log", suite="s", deploy=None,
                          push=False, keep_branches=True)
    assert rc == 1 and runs[-1] == [] and "blocked" not in written


def test_two_reviewed_branches_on_one_file_ride_one_train(render, tmp_path):
    # the former overlap rule held the later one a whole train back; git
    # merges both cleanly and the gates read the merge of reviewed works
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    lines = [f"line {i}\n" for i in range(1, 10)]
    (out / "shared.txt").write_text("".join(lines))
    _repo(out)
    _branch(out, "alpha", {"shared.txt": "".join(["alpha\n", *lines[1:]])})
    _branch(out, "beta", {"shared.txt": "".join([*lines[:-1], "beta\n"])})
    p = json.loads(_train(out, "plan", "--json").stdout)
    assert all(c["eligible"] for c in p["candidates"]), p["candidates"]
    r = _train(out, "run", "--force", "--suite", "true", "--keep-branches")
    assert r.returncode == 0, r.stdout + r.stderr
    merged = (out / "shared.txt").read_text()
    assert merged.startswith("alpha\n") and merged.endswith("beta\n")


@pytest.mark.parametrize("red_in,retry,how", [
    ("gates", None, "gates"),          # a gate can read the network: re-run the gates only
    ("gates", "make retry", "gates"),
    ("suite", "make retry", "failed"),  # what failed and what did not run, same tree
    ("suite", None, "full"),            # no --retry: the whole suite on a rebuilt tree
])
def test_retry_plan_is_one_rule(render, tmp_path, red_in, retry, how):
    train = _load_train(render(tmp_path, {"project_name": "d", "modules": {}}))
    got, why = train.retry_plan(red_in, retry)
    assert got == how and why


def _retry_batch(render, tmp_path, monkeypatch, *, retry, sh):
    return _retry_batch_with(None, render, tmp_path, monkeypatch, retry=retry, sh=sh)


def _retry_batch_with(train, render, tmp_path, monkeypatch, *, retry, sh):
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    _repo(out)
    train = train or _load_train(out)
    builds, runs = [], []

    def build(root, base, subset, stamp, log, **kw):
        builds.append(list(subset))
        return out, "train/x", list(subset), []
    monkeypatch.setattr(train, "build_train", build)
    monkeypatch.setattr(train, "_run_gates", lambda *a, **k: True)
    monkeypatch.setattr(train, "_sh", lambda cwd, cmd, log, **kw: runs.append(cmd) or sh(cmd, len(runs)))
    monkeypatch.setattr(train, "_cleanup", lambda *a: None)
    monkeypatch.setattr(train, "_write", lambda *a, **k: None)
    p = {"base": "main", "candidates": [{"branch": "b1", "hours_waiting": 1}]}
    try:
        train._run_batch(out, "main", p, ["b1"], "x", tmp_path / "t.log", suite="suite", deploy=None,
                         push=False, keep_branches=True, retry=retry)
    except SystemExit:
        pass  # the stub train/x cannot be fast-forwarded; the judging is done
    return builds, runs, (tmp_path / "t.log").read_text()


def test_a_red_suite_retries_only_what_failed_on_the_same_tree(render, tmp_path, monkeypatch):
    # #193: the retry ran the whole 24-minute suite again on a deterministic red
    builds, runs, log = _retry_batch(render, tmp_path, monkeypatch, retry="make retry",
                                     sh=lambda cmd, n: "red" if n == 1 else "green")
    assert runs[:2] == ["suite", "make retry"] and builds[:1] == [["b1"]] and len(builds) == 1
    # #263: a green retry command is no proof of a flake on the identical suite
    assert "then green under the retry command `make retry`" in log and "failed —" in log
    assert "flaky suite, merging" not in log


def test_a_green_retry_certifies_the_tree_the_suite_started_from(render, tmp_path, monkeypatch):
    """#265: a green stage retry wrote no merge certificate, so the push to main ran
    the whole suite again on a tree that had passed every stage."""
    calls = []

    def certify(wt, suite, before, env, log, scope=None):
        calls.append((suite, before))
    monkeypatch.delenv("MAKEFLAGS", raising=False)
    out = render(tmp_path / "probe", {"project_name": "d", "modules": {}})
    train_mod = _load_train(out)
    monkeypatch.setattr(train_mod, "_certify_merge", certify)
    monkeypatch.setattr(train_mod.certificate, "evidence_tree", lambda wt: "tree-before")
    monkeypatch.setattr(train_mod.certificate, "clean_tree_problem", lambda wt: None)
    monkeypatch.setattr(train_mod, "_every_stage_green", lambda wt: True)
    builds, runs, log = _retry_batch_with(train_mod, render, tmp_path, monkeypatch, retry="make retry",
                                          sh=lambda cmd, n: "red" if n == 1 else "green")
    assert runs[:2] == ["suite", "make retry"]
    # the retry's green, certified for the tree the suite started from (refute: untested before)
    assert calls == [("suite", "tree-before")], calls


def test_a_retry_that_left_a_stage_unrun_certifies_nothing(render, tmp_path, monkeypatch):
    """Refute of #265: the suite stopped before stage c, the retry re-ran b; the
    certificate claimed scope a b c although c never ran."""
    calls = []
    monkeypatch.delenv("MAKEFLAGS", raising=False)
    out = render(tmp_path / "probe", {"project_name": "d", "modules": {}})
    train_mod = _load_train(out)
    monkeypatch.setattr(train_mod, "_certify_merge", lambda *a, **k: calls.append(a))
    monkeypatch.setattr(train_mod, "_every_stage_green", lambda wt: False)
    builds, runs, log = _retry_batch_with(train_mod, render, tmp_path, monkeypatch, retry="make retry",
                                          sh=lambda cmd, n: "red" if n == 1 else "green")
    assert runs[:2] == ["suite", "make retry"] and calls == [] and "no merge certificate" in log, log


def test_every_stage_green_reads_the_markers(render, tmp_path):
    """The retry certificate's precondition: every listed stage has a green marker."""
    train_mod = _load_train(render(tmp_path / "probe", {"project_name": "d", "modules": {}}))
    root = tmp_path / "r"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    folder = root / ".git/merge-suite"
    folder.mkdir()
    (folder / "stages").write_text("a b c\n")
    (folder / "a.time").write_text("1 2 0\n")
    (folder / "b.time").write_text("1 2 0\n")
    assert train_mod._every_stage_green(root) is False  # c never ran
    (folder / "c.time").write_text("1 2 1\n")
    assert train_mod._every_stage_green(root) is False  # c red
    (folder / "c.time").write_text("1 2 0\n")
    assert train_mod._every_stage_green(root) is True


def test_a_primary_suite_green_under_dry_run_makeflags_merges_nothing(render, tmp_path, monkeypatch):
    """Refute of #265: only the retry path refused `make -n`; the first suite's green merged."""
    monkeypatch.setenv("MAKEFLAGS", "-n")
    out = render(tmp_path / "probe", {"project_name": "d", "modules": {}})
    train_mod = _load_train(out)
    with pytest.raises(train_mod.EnvironmentRed, match="runs no recipe"):
        _retry_batch_with(train_mod, render, tmp_path, monkeypatch, retry=None, sh=lambda cmd, n: "green")


def test_a_retry_green_under_dry_run_makeflags_merges_nothing(render, tmp_path, monkeypatch):
    """#265 AC-3: under `MAKEFLAGS=-n` the retry exits 0 having run nothing."""
    monkeypatch.setenv("MAKEFLAGS", "-n")
    out = render(tmp_path / "probe", {"project_name": "d", "modules": {}})
    train_mod = _load_train(out)
    with pytest.raises(train_mod.EnvironmentRed, match="runs no recipe"):
        _retry_batch_with(train_mod, render, tmp_path, monkeypatch, retry="make retry",
                          sh=lambda cmd, n: "red" if n == 1 else "green")


def test_without_retry_the_whole_suite_runs_on_a_rebuilt_tree(render, tmp_path, monkeypatch):
    builds, runs, log = _retry_batch(render, tmp_path, monkeypatch, retry=None,
                                     sh=lambda cmd, n: "red" if n == 1 else "green")
    assert runs[:2] == ["suite", "suite"] and builds[:2] == [["b1"], ["b1"]]


def test_a_retry_command_missing_on_the_tree_falls_back_to_the_suite(render, tmp_path, monkeypatch):
    builds, runs, log = _retry_batch(render, tmp_path, monkeypatch, retry="make retry",
                                     sh=lambda cmd, n: {1: "red", 2: "undefined"}.get(n, "green"))
    assert runs[:3] == ["suite", "make retry", "suite"] and builds[:2] == [["b1"], ["b1"]]


def test_red_gates_rerun_the_gates_on_the_same_tree_then_the_suite(render, tmp_path, monkeypatch):
    # a gate that read the network red once is not worth a rebuilt tree
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    _repo(out)
    train = _load_train(out)
    builds, runs, gates = [], [], iter([False, True])
    monkeypatch.setattr(train, "build_train",
                        lambda root, base, subset, stamp, log, **kw: builds.append(1) or (out, "train/x", list(subset), []))
    monkeypatch.setattr(train, "_run_gates", lambda *a, **k: next(gates))
    monkeypatch.setattr(train, "_sh", lambda cwd, cmd, log, **kw: runs.append(cmd) or "green")
    monkeypatch.setattr(train, "_cleanup", lambda *a: None)
    monkeypatch.setattr(train, "_write", lambda *a, **k: None)
    p = {"base": "main", "candidates": [{"branch": "b1", "hours_waiting": 1}]}
    with pytest.raises(SystemExit):
        train._run_batch(out, "main", p, ["b1"], "x", tmp_path / "t.log", suite="suite", deploy=None,
                         push=False, keep_branches=True, retry="make retry")
    assert len(builds) == 1 and runs == ["suite"]
    assert "gates —" in (tmp_path / "t.log").read_text()



def test_a_run_that_wrote_into_the_tree_is_retried_on_a_rebuilt_one(render, tmp_path, monkeypatch):
    # refutation: run 1 generated a snapshot baseline it then found missing;
    # an in-place retry would pass on that file and merge a red tree
    def sh(cmd, n):
        if n == 1:
            (tmp_path / "repo" / "baseline.png").write_text("written by the run")
            return "red"
        return "green"
    builds, runs, log = _retry_batch(render, tmp_path, monkeypatch, retry="make retry", sh=sh)
    assert runs[:2] == ["suite", "suite"] and builds[:2] == [["b1"], ["b1"]]
    assert "changed the worktree" in log


def test_a_tree_this_train_saw_green_is_not_run_again_after_the_drop(render, tmp_path, monkeypatch):
    # downstream: the bisection probe main+#2445 went green, #2456 was dropped,
    # and the rebuild — the same tree — paid the 25-minute suite once more
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    _repo(out)
    for name, files in (("one", {"a.txt": "a\n"}), ("both", {"a.txt": "a\n", "b.txt": "b\n"})):
        _git(out, "checkout", "-q", "-b", name, "main")
        for rel, text in files.items():
            (out / rel).write_text(text)
        _git(out, "add", "-A")
        _git(out, "commit", "-q", "-m", name)
    _git(out, "checkout", "-q", "main")
    train = _load_train(out)
    runs, current = [], []

    def build(root, base, subset, stamp, log, **kw):
        current[:] = subset
        _git(out, "checkout", "-q", {0: "main", 1: "one", 2: "both"}[len(subset)])
        return out, "train/x", list(subset), []
    monkeypatch.setattr(train, "build_train", build)
    monkeypatch.setattr(train, "_run_gates", lambda *a, **k: True)
    monkeypatch.setattr(train, "_sh", lambda cwd, cmd, log, **kw: runs.append(list(current)) or
                        ("red" if "b2" in current else "green"))
    monkeypatch.setattr(train, "_cleanup", lambda *a: None)
    monkeypatch.setattr(train, "_write", lambda *a, **k: None)
    p = {"base": "main", "candidates": [{"branch": "b1", "hours_waiting": 2}, {"branch": "b2", "hours_waiting": 1}]}
    with pytest.raises(SystemExit):  # the stub train/x cannot be fast-forwarded; the judging is done
        train._run_batch(out, "main", p, ["b1", "b2"], "x", tmp_path / "t.log", suite="s", deploy=None,
                         push=False, keep_branches=True)
    # combined, its retry, the base, the probe [b1] — and no fifth run for the rebuilt [b1]
    assert runs == [["b1", "b2"], ["b1", "b2"], [], ["b1"]]
    assert "green earlier in this train" in (tmp_path / "t.log").read_text()


@pytest.mark.parametrize("namesake", ["main-after-fork", "other-car"])
def test_a_slug_another_plan_of_the_merged_tree_shares_does_not_board(render, tmp_path, namesake):
    """Review #199: unique at the branch tip is not enough — the merged tree
    decides whether the gate takes the slug after the merge archives the plan."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _slug_branch(out, "issue-2260", "2026-10-01-2260-work-expiry.md", issue=2260, work="2260-work-expiry",
                 files={"src/expiry.py": "x = 1\n"})
    if namesake == "main-after-fork":
        plans = out / ".process-work/plans"
        (plans / "2026-10-05-2260-work-expiry.md").write_text("# other\n\ntier: 2\nissue: #2300\n")
        _git(out, "add", "-A")
        _git(out, "commit", "-q", "-m", "a namesake on main")
    else:
        _slug_branch(out, "issue-2300", "2026-10-05-2260-work-expiry.md", issue=2300, work="x",
                     files={"src/other.py": "y = 1\n"})
    _report(out, "issue-2260")
    assert not _candidate(out, "issue-2260")["eligible"]


def test_a_stacked_branch_carrying_the_same_plan_does_not_double_count(render, tmp_path):
    """Refute #199: the same added plan on two stacked branches is one file after the merge."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _slug_branch(out, "issue-2260", "2026-10-01-2260-work-expiry.md", issue=2260, work="2260-work-expiry",
                 files={"src/expiry.py": "x = 1\n"})
    _git(out, "checkout", "-q", "-b", "issue-2260-part2", "issue-2260")
    (out / "src/part2.py").write_text("z = 1\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "part 2")
    _git(out, "checkout", "-q", "main")
    _report(out, "issue-2260")
    assert _candidate(out, "issue-2260")["eligible"]


def test_a_plan_the_branch_only_renamed_counts_once(render, tmp_path):
    """Refute #199: a renamed plan is one file after the merge, its slug still unique."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    plans = out / ".process-work/plans"
    plans.mkdir(parents=True, exist_ok=True)
    (plans / "2026-10-01-2260-work-expiry.md").write_text("# p\n\ntier: 2\nissue: #2260\n\n## Decisions\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "plan on main")
    _git(out, "checkout", "-q", "-b", "issue-2260", "main")
    _git(out, "mv", ".process-work/plans/2026-10-01-2260-work-expiry.md",
         ".process-work/plans/2026-10-08-2260-work-expiry.md")
    (out / "src").mkdir(exist_ok=True)
    (out / "src/expiry.py").write_text("x = 1\n")
    j = out / ".process-work/journal"
    j.mkdir(parents=True, exist_ok=True)
    (j / "2026-10-08-issue-2260.md").write_text(
        "REVIEW work=2260-work-expiry tier=2 reviewer=fresh model=cross "
        "independence=bundle,non-implementing verdict=pass round=1\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "rename and work")
    _git(out, "checkout", "-q", "main")
    _report(out, "issue-2260")
    assert _candidate(out, "issue-2260")["eligible"]


def test_another_cars_deletion_does_not_make_a_slug_unique(render, tmp_path):
    """Review #199: a car that deletes a namesake may not board — its deletion counts for nobody else."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    plans = out / ".process-work/plans"
    plans.mkdir(parents=True, exist_ok=True)
    (plans / "2026-09-01-2260-work-expiry.md").write_text("# old\n\ntier: 2\nissue: #2300\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "a namesake on main")
    _git(out, "checkout", "-q", "-b", "drop-old", "main")
    _git(out, "rm", "-q", ".process-work/plans/2026-09-01-2260-work-expiry.md")
    _git(out, "commit", "-q", "-m", "drop it, unreviewed")
    _git(out, "checkout", "-q", "main")
    _slug_branch(out, "issue-2260", "2026-10-01-2260-work-expiry.md", issue=2260, work="2260-work-expiry",
                 files={"src/expiry.py": "x = 1\n"})
    _report(out, "issue-2260")
    assert not _candidate(out, "issue-2260")["eligible"]


# --- #206: preflight, merge certificate, phase times ---------------------------------

def _find_merge_certificate(out: Path, evidence: str):
    code = ("import sys, json; sys.path.insert(0, 'scripts/process'); import certificate; "
            "from pathlib import Path; "
            f"print(json.dumps(certificate.find(Path('.'), ('merge',), {{'merge': {evidence!r}}})))")
    r = subprocess.run([sys.executable, "-c", code], cwd=out, capture_output=True, text=True,
                       env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def _phases(out: Path) -> list[dict]:
    f = out / ".git/process-train/phases.jsonl"
    return [json.loads(line) for line in f.read_text().splitlines()] if f.exists() else []


def test_a_red_preflight_stops_the_train_and_blames_nobody(render, tmp_path, tmp_path_factory):
    # the suite log lives outside the worker's shared directory: other train tests write there too
    logs = tmp_path_factory.mktemp("suite")
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    _branch(out, "beta", {"src/b.py": "b\n"})
    head = _git(out, "rev-parse", "main").stdout
    r = _train(out, "run", "--force", "--suite", f"echo run >> {logs}/suite.log",
               "--preflight", "exit 3")
    assert r.returncode == 1 and "preflight `exit 3` is red" in r.stderr and "nobody is blamed" in r.stderr, r.stderr
    assert "dropping" not in r.stdout and not (logs / "suite.log").exists()
    assert _git(out, "rev-parse", "main").stdout == head
    branches = _git(out, "branch", "--list", "--format=%(refname:short)").stdout.split()
    assert {"alpha", "beta"} <= set(branches) and not [b for b in branches if b.startswith("train/")]
    row = _phases(out)[-1]
    assert row["result"] == "environment" and row["suite"] == 0 and row["gates"] == 0


def test_a_green_preflight_and_suite_certify_the_train_tree_and_log_the_phases(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    r = _train(out, "run", "--force", "--suite", "true ", "--preflight", "sleep 0.3")
    assert r.returncode == 0, r.stdout + r.stderr
    hit = _find_merge_certificate(out, "true")
    assert hit and hit["writer"] == "train" and hit["head"] == _git(out, "rev-parse", "main").stdout.strip()
    row = _phases(out)[-1]
    # timed where it ran, nothing where it did not (no --push)
    assert row["result"] == "green" and row["aboard"] == 1 and row["preflight"] >= 0.3
    assert row["gates"] > 0 and row["push"] == 0 and row["bisect"] == 0
    logs = sorted((out / ".git/process-train").glob("*.log"))
    assert "phases (green):" in logs[-1].read_text() and "merge certificate written" in logs[-1].read_text()


def test_a_suite_that_writes_into_the_tree_certifies_nothing(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    r = _train(out, "run", "--force", "--suite", "touch generated.txt")
    assert r.returncode == 0, r.stdout + r.stderr
    assert _find_merge_certificate(out, "touch generated.txt") is None
    logs = sorted((out / ".git/process-train").glob("*.log"))
    text = logs[-1].read_text()
    assert "the run changed the worktree — no merge certificate" in text
    assert "not clean (generated.txt)" in text  # named, so it can be ignored or cleaned (downstream #2542)


def test_the_suite_defaults_to_the_configured_merge_suite(render, tmp_path, tmp_path_factory):
    logs = tmp_path_factory.mktemp("suite")
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    (out / "docs/process/testing.local.json").write_text(
        json.dumps({"merge_suite": f"echo run >> {logs}/suite.log"}))
    _repo(out)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    r = _train(out, "run", "--force")
    assert r.returncode == 0 and "no --suite" not in r.stderr, r.stdout + r.stderr
    assert "run" in (logs / "suite.log").read_text()


def test_a_broken_test_configuration_stops_the_train_before_it_departs(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    (out / "docs/process/testing.local.json").write_text("{not json")
    _repo(out)
    r = _train(out, "run", "--force")
    assert r.returncode == 2 and "testing.local.json" in r.stderr, r.stderr


def test_train_phases_reads_median_and_maximum_per_phase(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {"telemetry": True}})
    _repo(out)
    d = out / ".git/process-train"
    d.mkdir(parents=True)
    rows = [{"stamp": f"s{i}", "result": ("green", "red", "environment")[i], "aboard": 2,
             "suite": 100.0 * (i + 1), "gates": 10.0, "bisect": 0.0} for i in range(3)]
    (d / "phases.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows) + "torn line\n")
    r = subprocess.run([sys.executable, str(out / "scripts/process/process_kpis.py"), "train-phases"],
                       cwd=out, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "suite     median    200 s, max    300 s (in 3/3 runs)" in r.stdout, r.stdout
    assert "bisect" not in r.stdout and "1/3 runs ended red, 1 stopped by the preflight" in r.stdout


def _train_phases(render, tmp_path, rows: list, *args: str) -> str:
    out = render(tmp_path, {"project_name": "d", "modules": {"telemetry": True}})
    _repo(out)
    d = out / ".git/process-train"
    d.mkdir(parents=True)
    (d / "phases.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    r = subprocess.run([sys.executable, str(out / "scripts/process/process_kpis.py"), "train-phases", *args],
                       cwd=out, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout


def test_train_phases_takes_the_plan_median_over_rows_that_carry_it(render, tmp_path):
    """v2.91-Refute: Zeilen von vor v2.91 haben kein `plan`. Sie zählen nicht als 0 s,
    sonst stünde der Median der Planung nach einem Update lange bei fast null."""
    rows = [{"suite": 100.0} for _ in range(8)] + [{"plan": 30.0, "suite": 100.0} for _ in range(2)]
    out = _train_phases(render, tmp_path, rows)
    plan = next(line for line in out.splitlines() if line.strip().startswith("plan "))
    assert "median     30 s" in plan and "(in 2/2 runs)" in plan, plan
    suite = next(line for line in out.splitlines() if line.strip().startswith("suite "))
    assert "(in 10/10 runs)" in suite, suite


def _red(**sources) -> dict:
    """red_tests einer Runde, wie train.py es schreibt: jede genannte Stage ist rot, ihr Wert
    die Quelle (`ids`/`on_base` als Listen, `error`, `too_many`; None: keine Quelle)."""
    out = []
    for stage, v in sources.items():
        if v is None:
            continue
        if "too_many" in v:
            out.append({"stage": stage, "reason": "too_many", "n": v["too_many"]})
        elif "error" in v:
            out.append({"stage": stage, "reason": v["error"]})
        elif isinstance(v.get("on_base"), list) and len(v["on_base"]) == len(v["ids"]):
            out.append({"stage": stage, "ids": dict(zip(v["ids"], v["on_base"]))})
        else:
            out.append({"stage": stage, "ids": "torn"})
    return {"stages": list(sources), "sources": out}


def test_train_phases_counts_red_path_runs_per_kind_with_their_median_suite(render, tmp_path):
    """v2.88 M3: je Art die Zahl der Läufe und der Median der Suite-Sekunden je Lauf, im Fenster der Phasen."""
    run = lambda n, s: {"n": n, "build_gates_s": 5.0 * n, "suite_s": s}  # noqa: E731
    rows = [{"stamp": "old", "result": "red", "suite": 1.0,
             "rounds": [{"red_path": "flaky", "runs": {"first": run(1, 9999.0)}}]},  # außerhalb von --runs 2
            {"stamp": "a", "result": "green", "suite": 100.0,
             "rounds": [{"red_path": "flaky", "runs": {"first": run(1, 100.0), "retry_full": run(1, 300.0)}}]},
            {"stamp": "b", "result": "green", "suite": 100.0,
             "rounds": [{"red_path": "dropped:beta", "runs": {"first": run(1, 200.0), "base": run(2, 100.0),
                                                              "probe": run(1, 0.0)}},
                        {"red_path": "green", "runs": {"first": run(1, 300.0)}}]}]
    out = _train_phases(render, tmp_path, rows, "--runs", "2")
    assert "red path: 3 rounds in 2/2 trains" in out, out
    assert "runs first          3 runs, suite median    200 s per run" in out, out
    assert "runs retry_full     1 run,  suite median    300 s per run" in out, out
    assert "runs base           2 runs, suite median     50 s per run" in out, out
    assert "runs probe          1 run,  suite median      0 s per run" in out, out
    assert "9999" not in out and "retry_gates" not in out


def test_train_phases_classes_red_tests_apart_for_flake_and_offender_rounds(render, tmp_path):
    """v2.88 M3: fähig / nicht fähig / unbestimmt, getrennt nach dem red_path der Runde."""
    ok = {"ids": ["t.py::a", "t.py::b"], "on_base": [True, True]}
    rows = [{"stamp": "a", "result": "green", "rounds": [
        {"red_path": "flaky", "runs": {}, "red_tests": _red(unit=ok)},                                  # fähig
        {"red_path": "gate-flaky", "runs": {}, "red_tests": _red(unit={"ids": ["t.py::a"], "on_base": [False]})},  # nicht fähig, lesbar
        {"red_path": "flaky", "runs": {}, "red_tests": _red(unit={"ids": ["t.py::a"], "on_base": ["unknown"]})},  # unbestimmt, lesbar
        {"red_path": "flaky", "runs": {}, "red_tests": _red(unit={"error": "symlink"})},                # unbestimmt
    ]}, {"stamp": "b", "result": "red", "rounds": [
        {"red_path": "dropped:beta", "runs": {}, "red_tests": _red(unit=ok, e2e=ok)},                   # fähig
        {"red_path": "base-red", "runs": {}, "red_tests": _red(unit=ok, e2e=None)},                     # unbestimmt: Stage ohne Quelle
        {"red_path": "dropped:gamma", "runs": {}, "red_tests": _red(
            unit={"ids": ["t.py::a"], "on_base": [False]}, e2e=None)},                                  # nicht fähig
        {"red_path": "dropped:delta", "runs": {}, "red_tests": _red(unit={"ids": [], "on_base": []})},  # unbestimmt: leer
        {"red_path": "dropped:eps", "runs": {}, "red_tests": "gates-red"},                              # unbestimmt
        {"red_path": "green", "runs": {}},                                                              # ohne red_tests
    ]}]
    out = _train_phases(render, tmp_path, rows)
    assert ("red tests, flake rounds (flaky, gate-flaky): 4, ids readable 3"
            " — capable 1, not capable 1, undetermined 2") in out, out
    assert "red tests, offender rounds (dropped, base-red, none-survived): 5 — capable 1, not capable 1, undetermined 3" in out, out
    assert "confidence: low" in out and "upper bound" in out, out


def test_train_phases_counts_too_many_red_ids_as_undetermined(render, tmp_path):
    rows = [{"stamp": "a", "result": "red", "rounds": [
        {"red_path": "dropped:beta", "runs": {}, "red_tests": _red(unit={"too_many": 431})},
        {"red_path": "flaky", "runs": {}, "red_tests": _red(unit={"too_many": 250})}]}]
    out = _train_phases(render, tmp_path, rows)
    assert "offender rounds (dropped, base-red, none-survived): 1 — capable 0, not capable 0, undetermined 1" in out, out
    assert "flake rounds (flaky, gate-flaky): 1, ids readable 0 — capable 0, not capable 0, undetermined 1" in out, out


def test_train_phases_reads_rows_without_or_with_broken_rounds(render, tmp_path):
    """v2.88 M3: alte Zeilen ohne `rounds` und kaputte Einträge kosten nichts als ihre eigene Zählung."""
    old = [{"stamp": f"s{i}", "result": "green", "suite": 100.0} for i in range(2)]
    out = _train_phases(render, tmp_path, old)
    assert "suite     median    100 s, max    100 s (in 2/2 runs)" in out, out
    assert "no red-path rounds recorded yet" in out, out
    broken = old + [{"stamp": "x", "result": "red", "rounds": "torn"},
                    {"stamp": "y", "result": "red", "rounds": [
                        "torn", {"runs": {"first": {"n": "2", "suite_s": None}, "base": "x"}},
                        {"red_path": "dropped:b", "runs": [], "red_tests": {"stages": "unit", "sources": []}},
                        {"red_path": "flaky", "red_tests": _red(unit={"ids": ["a"], "on_base": "true"})},
                        {"red_path": "flaky", "red_tests": _red(unit={"ids": ["a", "b"], "on_base": [True]})}]}]
    out = _train_phases(render, tmp_path / "b", broken)
    assert "red path: 4 rounds in 1/4 trains" in out, out
    assert "offender rounds (dropped, base-red, none-survived): 1 — capable 0, not capable 0, undetermined 1" in out, out
    assert "flake rounds (flaky, gate-flaky): 2, ids readable 0 — capable 0, not capable 0, undetermined 2" in out, out


def test_the_configured_preflight_is_the_trains_default(render, tmp_path, tmp_path_factory):
    """#209: one environment check for push, certify and train."""
    logs = tmp_path_factory.mktemp("suite")
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    (out / "docs/process/testing.local.json").write_text(json.dumps(
        {"preflight": ["sh", "-c", "exit 6"], "merge_suite": f"echo run >> {logs}/suite.log"}))
    _repo(out)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    r = _train(out, "run", "--force")
    assert r.returncode == 1 and "preflight `sh -c 'exit 6'` is red" in r.stderr, r.stderr
    assert not (logs / "suite.log").exists()
    r = _train(out, "run", "--force", "--preflight", "true")  # an explicit one wins
    assert r.returncode == 0 and "run" in (logs / "suite.log").read_text(), r.stdout + r.stderr


def test_a_hung_preflight_is_killed_at_its_timeout_and_an_empty_one_runs_none(render, tmp_path, tmp_path_factory):
    """Review #209: the train honours preflight_timeout; `--preflight ""` switches it off for one run."""
    import time
    logs = tmp_path_factory.mktemp("suite")
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    (out / "docs/process/testing.local.json").write_text(json.dumps(
        {"preflight": ["sh", "-c", "sleep 30"], "preflight_timeout": 0.5,
         "merge_suite": f"echo run >> {logs}/suite.log"}))
    _repo(out)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    started = time.monotonic()
    r = _train(out, "run", "--force")
    assert r.returncode == 1 and "is red" in r.stderr and time.monotonic() - started < 25, r.stderr
    assert not (logs / "suite.log").exists()
    r = _train(out, "run", "--force", "--preflight", "")
    assert r.returncode == 0 and "run" in (logs / "suite.log").read_text(), r.stdout + r.stderr


# --- #201: false refusals on deleted plans and stacked renames -----------------------------

@pytest.mark.parametrize("how", ["delete", "rename"])
def test_a_branch_that_deletes_or_renames_an_active_plan_is_not_unreadable(render, tmp_path, how):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    plans = out / ".process-work/plans"
    plans.mkdir(parents=True, exist_ok=True)
    (plans / "2026-09-01-old.md").write_text("# old\n\ntier: 1\nissue: #9\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "an active plan on main")
    _slug_branch(out, "issue-2260", "2026-10-01-2260-work-expiry.md", issue=2260, work="2260-work-expiry",
                 files={"src/expiry.py": "x = 1\n"})
    _git(out, "checkout", "-q", "issue-2260")
    if how == "delete":
        _git(out, "rm", "-q", ".process-work/plans/2026-09-01-old.md")
    else:
        _git(out, "mv", ".process-work/plans/2026-09-01-old.md", ".process-work/plans/2026-09-02-old.md")
    _git(out, "commit", "-q", "-m", f"{how} the old plan")
    _git(out, "checkout", "-q", "main")
    c = _candidate(out, "issue-2260")
    assert not any("could not read" in r for r in c["reasons"]), c["reasons"]


def _stacked_rename(out):
    _slug_branch(out, "issue-2260", "2026-10-01-2260-work-expiry.md", issue=2260, work="2260-work-expiry",
                 files={"src/expiry.py": "x = 1\n"})
    _git(out, "checkout", "-q", "-b", "issue-2260-redate", "issue-2260")
    _git(out, "mv", ".process-work/plans/2026-10-01-2260-work-expiry.md",
         ".process-work/plans/2026-10-08-2260-work-expiry.md")
    (out / "src/part2.py").write_text("z = 1\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "re-date the plan")
    _git(out, "checkout", "-q", "main")
    _report(out, "issue-2260")


def test_a_stacked_rename_of_a_shared_plan_counts_one_plan(render, tmp_path):
    """#201: measured against the base, the re-dated plan is an add — both names
    counted, and both branches lost the slug, though the merged tree holds one plan."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _stacked_rename(out)
    assert _candidate(out, "issue-2260")["eligible"]


def test_a_genuine_namesake_on_a_third_car_still_counts(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _stacked_rename(out)
    _slug_branch(out, "issue-2300", "2026-10-05-2260-work-expiry.md", issue=2300, work="x",
                 files={"src/other.py": "y = 1\n"})
    assert not _candidate(out, "issue-2260")["eligible"]


def test_a_regression_trailer_names_no_issue_of_the_branch(render, tmp_path):
    """`Regression-of: #N` points at the origin of a defect: the train neither files
    the fix's `done` under #N nor asks to close it (process_kpis.py flow attributes by it)."""
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    _repo(out)
    bare = tmp_path / "origin.git"  # the train reads issue refs from origin/main..branch
    _git(out, "clone", "-q", "--bare", str(out), str(bare))
    _git(out, "remote", "add", "origin", str(bare))
    _git(out, "fetch", "-q", "origin")
    _branch(out, "20-fix", {"src/a.py": "a\n"})
    _git(out, "checkout", "-q", "20-fix")
    (out / "src/a.py").write_text("fixed\n")
    _git(out, "commit", "-qam", "fix: crash (#20)\n\nRegression-of: #12")
    _git(out, "checkout", "-q", "main")
    r = _train(out, "run", "--force")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "references issue(s) #20" in r.stdout and "#12" not in r.stdout, r.stdout
    t = json.loads(subprocess.run([sys.executable, str(out / "scripts/process/tower.py"), "--json"],
                                  cwd=out, capture_output=True, text=True).stdout)
    done = [x for x in t["reports"] if x["worker"] == "20-fix"]
    assert done and done[-1]["state"] == "done" and done[-1].get("issue") == 20, done


def test_a_tree_dirty_before_the_suite_names_its_files(render, tmp_path):
    """Code review v2.74 (downstream #2542): a gate that leaves a file keeps the run from
    its certificate — the log says which file, so it can be ignored or cleaned."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    (out / "scripts/litter.py").write_text("open('litter.txt', 'w').close()\nprint('litter: OK')\n")
    (out / "docs/process/gates.local.json").write_text(json.dumps(
        {"litter": {"module": None, "command": ["scripts/litter.py"]}}))
    _repo(out)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    r = _train(out, "run", "--force", "--suite", "true")
    assert r.returncode == 0, r.stdout + r.stderr
    text = sorted((out / ".git/process-train").glob("*.log"))[-1].read_text()
    assert "not clean (litter.txt) before the suite" in text, text[-2000:]


def test_a_retry_command_missing_on_the_tree_rebuilds_and_a_green_is_a_flake(render, tmp_path, monkeypatch):
    """#263: the fallback runs the same suite on a rebuilt identical tree — that IS a flake."""
    def sh(cmd, n):
        if cmd == "make retry":
            return "undefined"
        return "red" if n == 1 else "green"
    _builds, runs, log = _retry_batch(render, tmp_path, monkeypatch, retry="make retry", sh=sh)
    assert "make retry" in runs and runs.count("suite") >= 2
    assert "flaky suite, merging" in log and "green under the retry command" not in log


def test_red_gates_then_green_are_a_gate_flake_not_a_flaky_suite(render, tmp_path, monkeypatch):
    """#263: the suite never ran before the retry — a green is no word about the suite."""
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    _repo(out)
    train = _load_train(out)
    gates = iter([False, True, True, True])
    monkeypatch.setattr(train, "build_train", lambda root, base, subset, stamp, log, **kw: (out, "train/x", list(subset), []))
    monkeypatch.setattr(train, "_run_gates", lambda *a, **k: next(gates))
    monkeypatch.setattr(train, "_sh", lambda cwd, cmd, log, **kw: "green")
    monkeypatch.setattr(train, "_cleanup", lambda *a: None)
    monkeypatch.setattr(train, "_write", lambda *a, **k: None)
    p = {"base": "main", "candidates": [{"branch": "b1", "hours_waiting": 1}]}
    try:
        train._run_batch(out, "main", p, ["b1"], "x", tmp_path / "t.log", suite="suite", deploy=None,
                         push=False, keep_branches=True)
    except SystemExit:
        pass
    log = (tmp_path / "t.log").read_text()
    assert "gate flake" in log and "flaky suite" not in log, log


def test_every_stack_preflight_is_the_trains_too(render, tmp_path, tmp_path_factory):
    """#373: a merge runs every stack — a stack's own host check red, 3 included, is the environment."""
    logs = tmp_path_factory.mktemp("suite")
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    (out / "docs/process/testing.local.json").write_text(json.dumps(
        {"merge_suite": f"echo run >> {logs}/suite.log",
         "stacks": {"backend": {"paths": ["backend/"], "runner": ["true", "{paths}"], "unmapped": "skip",
                                "preflight": ["sh", "-c", "exit 3"]}}}))
    _repo(out)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    r = _train(out, "run", "--force")
    assert r.returncode == 1 and "exit 3" in r.stderr and "nobody is blamed" in r.stderr, r.stderr
    assert not (logs / "suite.log").exists()
    # `--preflight ""` replaces the global check only: the stacks' own still run
    r = _train(out, "run", "--force", "--preflight", "")
    assert r.returncode == 1 and "exit 3" in r.stderr, r.stderr
    assert not (logs / "suite.log").exists()


# --- #381: a --suite the hook would not match; #379: conflict hints in plan -----------------

def test_a_suite_the_hook_would_not_match_is_refused_before_boarding(render, tmp_path, tmp_path_factory):
    """#381: the push checks the merge certificate against merge_suite — a train run under
    another command certifies nothing the hook reads, and the push runs the suite again."""
    logs = tmp_path_factory.mktemp("suite")
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    config = out / "docs/process/testing.local.json"
    config.write_text(json.dumps({"merge_suite": f"echo run >> {logs}/suite.log"}))
    _repo(out)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    head = _git(out, "rev-parse", "main").stdout
    other = f"echo other >> {logs}/other.log"
    r = _train(out, "run", "--force", "--suite", other)
    assert r.returncode == 2, r.stdout + r.stderr
    # both commands, the reason and the one legitimate case for the flag
    assert other in r.stderr and f"echo run >> {logs}/suite.log" in r.stderr, r.stderr
    assert "never match" in r.stderr and "runs the suite again" in r.stderr, r.stderr
    assert "--suite-differs-ok" in r.stderr and "changes merge_suite itself" in r.stderr, r.stderr
    # refused before boarding: no departure, no staging branch, no log, main untouched
    assert "departing" not in r.stdout and not (logs / "other.log").exists()
    assert not [b for b in _git(out, "branch", "--list", "--format=%(refname:short)").stdout.split()
                if b.startswith("train/")]
    assert not list((out / ".git/process-train").glob("*.log"))
    assert _git(out, "rev-parse", "main").stdout == head
    # without merge_suite the command is the caller's, as before
    config.write_text(json.dumps({}))
    _git(out, "commit", "-q", "-am", "no merge_suite")
    r = _train(out, "run", "--force", "--suite", other)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "other" in (logs / "other.log").read_text()


def test_a_suite_equal_to_merge_suite_but_for_blanks_runs_merge_suite_itself(render, tmp_path):
    """#381: the rule of finish.py — equal after strip — and the run uses merge_suite, so the
    certificate's evidence is the hook's string exactly."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    (out / "docs/process/testing.local.json").write_text(json.dumps({"merge_suite": "true"}))
    _repo(out)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    r = _train(out, "run", "--force", "--suite", "  true ")
    assert r.returncode == 0, r.stdout + r.stderr
    hit = _find_merge_certificate(out, "true")
    assert hit and hit["writer"] == "train"
    text = sorted((out / ".git/process-train").glob("*.log"))[-1].read_text()
    assert "$ true → exit 0" in text and "$   true " not in text, text


def test_suite_differs_ok_runs_the_other_suite_and_logs_it(render, tmp_path, tmp_path_factory):
    """#381: a passenger that changes merge_suite itself needs the new command — deliberate, logged."""
    logs = tmp_path_factory.mktemp("suite")
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    (out / "docs/process/testing.local.json").write_text(json.dumps({"merge_suite": f"echo run >> {logs}/suite.log"}))
    _repo(out)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    other = f"echo other >> {logs}/other.log"
    r = _train(out, "run", "--force", "--suite", other, "--suite-differs-ok")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "other" in (logs / "other.log").read_text() and not (logs / "suite.log").exists()
    assert "--suite-differs-ok" in r.stderr, r.stderr
    text = sorted((out / ".git/process-train").glob("*.log"))[-1].read_text()
    assert "--suite-differs-ok" in text and other in text and f"echo run >> {logs}/suite.log" in text, text


def test_plan_names_conflicts_between_candidates_that_may_board(render, tmp_path):
    """#379: a pairwise conflict among the eligible candidates is a note in `plan` — text and JSON."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    _branch(out, "beta", {"src/a.py": "beta\n"}, reviewed=False)   # conflicts too, but may not board
    _branch(out, "gamma", {"src/a.py": "conflict\n", "src/g.py": "g\n"})
    _branch(out, "tiny", {"README.md": "tiny\n"}, tier=1, reviewed=False)
    r = _train(out, "plan", "--json")
    assert r.returncode == 0, r.stderr
    p = json.loads(r.stdout)
    assert p["conflicts"] == [{"branches": ["alpha", "gamma"], "paths": ["src/a.py"]}], p.get("conflicts")
    text = _train(out, "plan").stdout
    line = next((ln for ln in text.splitlines() if "conflict" in ln and "src/a.py" in ln), "")
    assert "alpha" in line and "gamma" in line and "beta" not in line, text


def test_conflict_hints_come_in_boarding_order(render, tmp_path, monkeypatch):
    """Refute v2.87: the run boards oldest first and drops the later of a pair —
    the hint names that one, not the alphabetically later."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    train = _load_train(out)
    monkeypatch.setattr(train._review, "_auto_merge", lambda root, a, b: ("tree", {"src/a.py"}))
    cands = [{"branch": "a", "eligible": True, "hours_waiting": 1},
             {"branch": "z", "eligible": True, "hours_waiting": 30},
             {"branch": "n", "eligible": False, "hours_waiting": 99}]
    assert train.conflict_hints(out, cands) == [{"branches": ["z", "a"], "paths": ["src/a.py"]}]
    text = train.render_plan({"base": "main", "ready": True, "why": "w", "candidates": [],
                              "conflicts": train.conflict_hints(out, cands)})
    assert "z × a conflict" in text and "drops a unless z" in text, text


def _pairs_repo(render, tmp_path):
    """Candidates for every kind of pair: a conflict (alpha × gamma), clean ones, an
    unrelated history (orphan) and a branch behind the base whose change conflicts
    with main only (old × side: their changes against the base share no path)."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    (out / "src").mkdir(exist_ok=True)
    (out / "src/f.py").write_text("0\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "f")
    _branch(out, "old", {"src/f.py": "old\n"})
    (out / "src/f.py").write_text("main\n")
    _git(out, "commit", "-q", "-am", "main moves on")
    _branch(out, "side", {"src/g.py": "g\n"})
    _branch(out, "alpha", {"src/a.py": "a\n"})
    _branch(out, "gamma", {"src/a.py": "gamma\n"})
    _git(out, "checkout", "-q", "--orphan", "orphan")
    _git(out, "rm", "-rfq", ".")
    (out / "src").mkdir(exist_ok=True)
    (out / "src/o.py").write_text("o\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "unrelated")
    _git(out, "checkout", "-q", "-f", "main")
    names = ("old", "side", "alpha", "gamma", "orphan")
    return out, {b: _git(out, "rev-parse", b).stdout.strip() for b in names}


# old is behind the base: it conflicts with every branch that carries main's f.py
_PAIR_HINTS = [{"branches": ["old", b], "paths": ["src/f.py"]} for b in ("side", "alpha", "gamma")] + [
    {"branches": ["alpha", "gamma"], "paths": ["src/a.py"]}]


def _merge_trees(review, monkeypatch, *, refuse_stdin=False) -> list[list[str]]:
    """Every `git merge-tree` `review` runs; `refuse_stdin`: a git before 2.40."""
    calls: list[list[str]] = []
    real = review.subprocess.run

    def run(cmd, *a, **k):
        if cmd and cmd[0] == "git" and "merge-tree" in cmd:
            calls.append(cmd)
            if refuse_stdin and "--stdin" in cmd:
                return subprocess.CompletedProcess(cmd, 129, b"", b"error: unknown option `stdin'\n")
        return real(cmd, *a, **k)

    monkeypatch.setattr(review.subprocess, "run", run)
    return calls


def test_one_merge_tree_answers_every_pair_as_its_own_merge(render, tmp_path, monkeypatch):
    """v2.91 (#398, M0: 12 % of `plan`): one `merge-tree --stdin` for all pairs, each
    answer the one git gives the pair alone — nothing skipped (plan review round 3)."""
    import itertools
    out, tips = _pairs_repo(render, tmp_path)
    review = _load_train(out)._review
    pairs = list(itertools.combinations(tips.values(), 2))
    alone = {pair: review._auto_merge_uncached(out, *pair) for pair in pairs}
    assert alone[(tips["old"], tips["side"])][1] == {"src/f.py"}
    assert alone[(tips["alpha"], tips["gamma"])][1] == {"src/a.py"}
    assert alone[(tips["alpha"], tips["orphan"])][1] == set() and alone[(tips["side"], tips["alpha"])][1] == set()
    review.clear_memo()
    calls = _merge_trees(review, monkeypatch)
    review._auto_merges(out, pairs)
    assert len(calls) == 1
    for pair in pairs:
        assert review._PURE[("auto", (str(out), pair))] == (alone[pair][0], frozenset(alone[pair][1])), pair
    assert all(review._auto_merge(out, *pair) == alone[pair] for pair in pairs) and len(calls) == 1


def test_conflict_hints_run_one_merge_tree_for_all_pairs(render, tmp_path, monkeypatch):
    out, tips = _pairs_repo(render, tmp_path)
    train = _load_train(out)
    train._review.clear_memo()
    calls = _merge_trees(train._review, monkeypatch)
    cands = [{"branch": b, "sha": sha, "eligible": True, "hours_waiting": 10 - i} for i, (b, sha) in enumerate(tips.items())]
    assert train.conflict_hints(out, cands) == _PAIR_HINTS
    assert len(calls) == 1


def test_a_git_without_merge_tree_stdin_merges_each_pair_alone(render, tmp_path, monkeypatch):
    """Guard: a git before 2.40 refuses `--stdin` — every pair alone, the same hints."""
    out, tips = _pairs_repo(render, tmp_path)
    train = _load_train(out)
    train._review.clear_memo()
    calls = _merge_trees(train._review, monkeypatch, refuse_stdin=True)
    cands = [{"branch": b, "sha": sha, "eligible": True, "hours_waiting": 10 - i} for i, (b, sha) in enumerate(tips.items())]
    assert train.conflict_hints(out, cands) == _PAIR_HINTS
    assert len([c for c in calls if "--stdin" not in c]) == 10


def test_a_batch_cut_short_by_an_unmergeable_line_fills_nothing(render, tmp_path, monkeypatch):
    """In batch mode git stops at a line it cannot merge (exit 1, the answers before it
    on stdout): only exit 0 with one answer per pair counts — else each pair alone."""
    out, tips = _pairs_repo(render, tmp_path)
    review = _load_train(out)._review
    review.clear_memo()
    calls = _merge_trees(review, monkeypatch)
    good, bad = (tips["alpha"], tips["gamma"]), (tips["alpha"], "1" * 40)
    review._auto_merges(out, [good, bad])
    assert len(calls) == 1 and not [k for k in review._PURE if k[0] == "auto"]
    assert review._auto_merge(out, *good)[1] == {"src/a.py"} and review._auto_merge(out, *bad) is None


def test_run_does_not_compute_the_conflict_hints(render, tmp_path, monkeypatch, capsys):
    """#379: the hint is the plan's output only — `run` calls plan() and must stay as fast."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    _branch(out, "gamma", {"src/a.py": "conflict\n"})
    train = _load_train(out)
    calls: list[int] = []
    monkeypatch.setattr(train, "conflict_hints", lambda root, cands: calls.append(1) or [])
    assert train.main(["run", "--force", "--dry-run", "--suite", "true", "--root", str(out)]) == 0
    assert calls == [] and "departing" in capsys.readouterr().out
    assert train.main(["plan", "--json", "--root", str(out)]) == 0
    assert calls == [1]


# --- v2.88 (#378): measure the red path — runs per kind and round, red tests read only --

LASTFAILED = ".pytest_cache/v/cache/lastfailed"


def _measured(render, tmp_path, monkeypatch, *, sh, n=2, gates=None, retry=None, red_ids=None,
              seen=False, conflicts=None):
    """b1 (and b2) judged on real trees — main, one = [b1], both = [b1, b2] — with a fake
    suite `sh(subset, cmd, nth)`. Returns the carrier, the `_sh` calls, the log and the rc
    (None: the stub train/x cannot be fast-forwarded — the judging is done)."""
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    with (out / ".gitignore").open("a") as fh:
        fh.write("\n.pytest_cache/\n")
    _repo(out)
    train = _load_train(out)
    if seen:
        train._remember_green_suite(out, train._suite_key(out, "s"))
    for name, files in (("one", {"a.txt": "a\n"}),
                        ("both", {"a.txt": "a\n", "tests/test_new.py": "def test_n():\n    pass\n"})):
        _git(out, "checkout", "-q", "-b", name, "main")
        for rel, text in files.items():
            (out / rel).parent.mkdir(parents=True, exist_ok=True)
            (out / rel).write_text(text)
        _git(out, "add", "-A")
        _git(out, "commit", "-q", "-m", name)
    _git(out, "checkout", "-q", "main")
    current, calls = [], []

    def build(root, base, subset, stamp, log, **kw):
        dropped = list((conflicts or (lambda s: []))(list(subset)))
        merged = [b for b in subset if b not in dropped]
        current[:] = merged
        _git(out, "checkout", "-q", {0: "main", 1: "one", 2: "both"}[len(merged)])
        return out, "train/x", merged, dropped

    def fake_sh(cwd, cmd, log, *a, **kw):
        calls.append((tuple(current), cmd))
        time.sleep(0.01)
        return sh(tuple(current), cmd, len(calls))
    monkeypatch.setattr(train, "build_train", build)
    gate = iter(gates) if gates is not None else None
    monkeypatch.setattr(train, "_run_gates", lambda *a, **k: next(gate, True) if gate else True)
    monkeypatch.setattr(train, "_sh", fake_sh)
    monkeypatch.setattr(train, "_cleanup", lambda *a: None)
    monkeypatch.setattr(train, "_write", lambda *a, **k: None)
    branches = ["b1", "b2"][:n]
    p = {"base": "main", "candidates": [{"branch": b, "hours_waiting": 2 - i} for i, b in enumerate(branches)]}
    measure: dict = {}
    try:
        rc = train._run_batch(out, "main", p, list(branches), "x", tmp_path / "t.log", suite="s", deploy=None,
                              push=False, keep_branches=True, retry=retry, measure=measure, red_ids=red_ids)
    except SystemExit:
        rc = None
    log = tmp_path / "t.log"
    return measure, calls, log.read_text() if log.exists() else "", rc


def _shape(measure: dict) -> list[tuple[str, dict[str, int]]]:
    return [(r["red_path"], {k: v["n"] for k, v in r["runs"].items()}) for r in measure["rounds"]]


def test_measure_a_gates_retry_and_its_suite_count_apart(render, tmp_path, monkeypatch):
    """M1: the gates retry runs no suite; the suite behind it is a `retry_full`. Gates red
    first: no red test can be read (`gates-red`)."""
    m, calls, _log, _rc = _measured(render, tmp_path, monkeypatch, n=1, gates=[False, True],
                                    sh=lambda sub, cmd, nth: "green",
                                    red_ids=[{"lastfailed": LASTFAILED, "rootdir": ".", "stage": None}])
    assert _shape(m) == [("gate-flaky", {"first": 1, "retry_gates": 1, "retry_full": 1})]
    runs = m["rounds"][0]["runs"]
    assert runs["first"]["suite_s"] == 0 and runs["retry_gates"]["suite_s"] == 0
    assert runs["retry_full"]["suite_s"] > 0 and m["rounds"][0]["red_tests"] == "gates-red"
    assert calls == [(("b1",), "s")]


@pytest.mark.parametrize("retry, answer, shape, path", [
    ("make retry", "green", {"first": 1, "retry_failed": 1}, "flaky"),
    ("make retry", "undefined", {"first": 1, "retry_failed": 1, "retry_full": 1}, "flaky"),
    (None, None, {"first": 1, "retry_full": 1}, "flaky")])
def test_measure_the_retry_kinds(render, tmp_path, monkeypatch, retry, answer, shape, path):
    """M1: `--retry` is `retry_failed`; its fallback to `undefined` rebuilds — one
    `retry_full`, not a second `retry_failed`."""
    def sh(sub, cmd, nth):
        if cmd == "make retry":
            return answer
        return "red" if nth == 1 else "green"
    m, _calls, _log, _rc = _measured(render, tmp_path, monkeypatch, n=1, retry=retry, sh=sh)
    assert _shape(m) == [(path, shape)]
    assert all(v["suite_s"] > 0 for v in m["rounds"][0]["runs"].values())
    assert "red_tests" not in m["rounds"][0]  # no red_ids: nothing read


def test_measure_the_base_in_the_undefined_path_and_none_survived(render, tmp_path, monkeypatch):
    m, _calls, _log, rc = _measured(render, tmp_path, monkeypatch, n=1,
                                    sh=lambda sub, cmd, nth: "undefined" if sub else "green")
    assert rc == 1 and _shape(m) == [("none-survived", {"first": 1, "base": 1})]


def test_measure_undefined_on_both(render, tmp_path, monkeypatch):
    m, _calls, _log, rc = _measured(render, tmp_path, monkeypatch, n=1, sh=lambda sub, cmd, nth: "undefined")
    assert rc == 1 and _shape(m) == [("undefined", {"first": 1, "base": 1})]


def test_measure_a_memo_hit_a_probe_and_the_round_after_the_drop(render, tmp_path, monkeypatch):
    """M1: the remembered base counts its build and gates, 0 s suite; the round after
    the drop is a round of its own."""
    m, calls, _log, _rc = _measured(render, tmp_path, monkeypatch, seen=True,
                                    sh=lambda sub, cmd, nth: "red" if "b2" in sub else "green")
    assert _shape(m) == [("dropped:b2", {"first": 1, "retry_full": 1, "base": 1, "probe": 1}),
                         ("green", {"first": 1})]
    base = m["rounds"][0]["runs"]["base"]
    assert base["suite_s"] == 0 and base["build_gates_s"] > 0
    # round 2: the probe saw this tree green — the first run ran no suite
    assert m["rounds"][1]["runs"]["first"]["suite_s"] == 0 and calls[-1] == (("b1",), "s")


def test_measure_the_real_base_run_behind_the_memo_and_a_red_base(render, tmp_path, monkeypatch):
    m, _calls, _log, rc = _measured(render, tmp_path, monkeypatch, n=1, seen=True,
                                    sh=lambda sub, cmd, nth: "red")
    assert rc == 1 and _shape(m) == [("base-red", {"first": 1, "retry_full": 1, "base": 2})]


def test_measure_a_probe_where_everybody_conflicts(render, tmp_path, monkeypatch):
    m, _calls, _log, _rc = _measured(render, tmp_path, monkeypatch,
                                     conflicts=lambda sub: sub if sub == ["b1"] else [],
                                     sh=lambda sub, cmd, nth: "red" if "b2" in sub else "green")
    assert _shape(m)[0] == ("dropped:b1", {"first": 1, "retry_full": 1, "base": 1, "probe": 1})
    assert m["rounds"][0]["runs"]["probe"]["suite_s"] == 0


def test_measure_a_first_run_where_everybody_conflicts(render, tmp_path, monkeypatch):
    m, calls, _log, rc = _measured(render, tmp_path, monkeypatch, conflicts=lambda sub: sub,
                                   sh=lambda sub, cmd, nth: "green")
    assert rc == 1 and calls == [] and _shape(m) == [("conflicts", {"first": 1})]


def test_measure_reaches_the_row_on_a_red_preflight(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    r = _train(out, "run", "--force", "--suite", "true", "--preflight", "exit 3")
    assert r.returncode == 1, r.stderr
    row = _phases(out)[-1]
    assert row["result"] == "environment"
    assert [(x["red_path"], sorted(x["runs"])) for x in row["rounds"]] == [("environment", ["first"])]


def test_measure_reaches_the_row_on_a_rejected_push(render, tmp_path):
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    _repo(out)
    bare = tmp_path / "origin.git"
    _git(out, "clone", "-q", "--bare", str(out), str(bare))
    _git(out, "remote", "add", "origin", str(bare))
    _git(out, "fetch", "-q", "origin")
    _git(out, "branch", "-q", "--set-upstream-to=origin/main", "main")
    _branch(out, "alpha", {"src/a.py": "a\n"})
    hook = out / ".git/hooks/pre-push"
    hook.write_text("#!/bin/sh\nexit 1\n")
    hook.chmod(0o755)
    r = _train(out, "run", "--force", "--push", "--suite", "true")
    assert r.returncode == 1, r.stderr
    row = _phases(out)[-1]
    assert [(x["red_path"], x["runs"]["first"]["n"]) for x in row["rounds"]] == [("push-rejected", 1)]
    # seconds are rounded in the row
    assert row["rounds"][0]["runs"]["first"]["suite_s"] == round(row["rounds"][0]["runs"]["first"]["suite_s"], 1)


def test_measure_reaches_the_row_when_the_run_aborts(render, tmp_path, monkeypatch):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    train = _load_train(out)

    def boom(*a, **k):
        raise RuntimeError("boom")
    monkeypatch.setattr(train, "_run_gates", lambda *a, **k: True)
    monkeypatch.setattr(train, "_sh", boom)
    with pytest.raises(RuntimeError):
        train.run(out, suite="s", deploy=None, push=False, min_candidates=1, max_wait_hours=0, force=True,
                  keep_branches=True, dry_run=False)
    row = _phases(out)[-1]
    assert row["result"] == "red"
    assert [(x["red_path"], x["runs"]["first"]["n"]) for x in row["rounds"]] == [("aborted", 1)]


def test_stage_markers_is_the_one_marker_reader(render, tmp_path):
    train_mod = _load_train(render(tmp_path / "probe", {"project_name": "d", "modules": {}}))
    root = tmp_path / "r"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    assert train_mod.stage_markers(root) is None  # no stages file: no stages
    folder = root / ".git/merge-suite"
    folder.mkdir()
    (folder / "stages").write_text("a b c\n")
    (folder / "a.time").write_text("1 2 0\n")
    (folder / "b.time").write_text("1 2 x\n")
    assert train_mod.stage_markers(root) == {"a": (1, 2, 0), "b": None, "c": None}


# M2: the red tests, read only from pytest's own cache

def _red_repo(tmp_path) -> Path:
    """main, and HEAD on `board` — the tree the train judged."""
    r = tmp_path / "red"
    files = {
        "backend/tests/test_a.py": "def test_one():\n    pass\n",
        "tests/test_b.py": "def test_x():\n    pass\n",
        "tests/test_e.py": "def test_y():\n    assert 1\n",
        "tests/test_f.py": "def test_x():\n    pass\n",
        "tests/test_g.py": "def test_p():\n    pass\n",
    }
    r.mkdir()
    _git(r, "init", "-q", "-b", "main")
    _git(r, "config", "user.email", "t@t")
    _git(r, "config", "user.name", "t")
    for rel, text in files.items():
        (r / rel).parent.mkdir(parents=True, exist_ok=True)
        (r / rel).write_text(text)
    _git(r, "add", "-A")
    _git(r, "commit", "-q", "-m", "base")
    _git(r, "checkout", "-q", "-b", "board")
    (r / "tests/test_b.py").write_text("def test_x():\n    assert 2\n\n\ndef test_new():\n    pass\n\n\n"
                                       "async def test_async_new():\n    pass\n\n\n"
                                       "class TestK:\n    def test_meth(self):\n        pass\n")
    (r / "tests/test_e.py").write_text("def test_y():\n    assert 2\n")
    (r / "tests/test_f.py").write_text("def test_x():\n    pass\n\n\ndef test_p(v):\n    pass\n")
    (r / "tests/test_c.py").write_text("def test_z():\n    pass\n")
    _git(r, "add", "-A")
    _git(r, "commit", "-q", "-m", "board")
    return r


def _lastfailed(root: Path, rel: str, ids) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({i: True for i in ids}))


def test_on_base_reads_each_id_by_file_and_def(render, tmp_path):
    train = _load_train(render(tmp_path / "probe", {"project_name": "d", "modules": {}}))
    r = _red_repo(tmp_path)
    _lastfailed(r, LASTFAILED, [
        "tests/test_b.py::test_new",              # new function in a changed file
        "tests/test_b.py::test_async_new",        # an async one
        "tests/test_b.py::TestK::test_meth",      # a new method
        "tests/test_e.py::test_y",                # changed file, no new def
        "tests/test_c.py::test_z",                # new file
        "tests/test_c.py",                        # a collection error: no `::`
        "tests/test_f.py::test_p[a::b]",          # the bracket goes first, then the first `::`
        "tests/test_g.py::test_p[x]",             # unchanged file
        "../outside.py::test_o",                  # outside the repository
        "tests/test_gone.py::test_m",             # on neither tree
    ])
    _lastfailed(r, "backend/" + LASTFAILED, ["tests/test_a.py::test_one"])
    got = train.red_tests(r, "main", [
        {"lastfailed": LASTFAILED, "rootdir": ".", "stage": None},
        {"lastfailed": "backend/" + LASTFAILED, "rootdir": "backend", "stage": None}], {})
    # a project without stages: the whole suite is the one stage `suite`, red
    assert got["stages"] == ["suite"]
    assert got["sources"][0]["ids"] == {
        "tests/test_b.py::test_new": False, "tests/test_b.py::test_async_new": False,
        "tests/test_b.py::TestK::test_meth": False, "tests/test_e.py::test_y": "unknown",
        "tests/test_c.py::test_z": False, "tests/test_c.py": "unknown",
        "tests/test_f.py::test_p[a::b]": False, "tests/test_g.py::test_p[x]": True,
        "../outside.py::test_o": "unknown", "tests/test_gone.py::test_m": "unknown"}
    # node ids are relative to the rootdir (plan review: `backend/` read `false` otherwise)
    assert got["sources"][1] == {"lastfailed": "backend/" + LASTFAILED, "rootdir": "backend", "stage": "suite",
                                 "ids": {"tests/test_a.py::test_one": True}}


def test_red_stages_come_from_the_markers_and_a_source_per_stage(render, tmp_path):
    train = _load_train(render(tmp_path / "probe", {"project_name": "d", "modules": {}}))
    r = _red_repo(tmp_path)
    folder = r / ".git/merge-suite"
    folder.mkdir()
    (folder / "stages").write_text("unit e2e\n")
    (folder / "unit.time").write_text("1 2 0\n")
    (folder / "e2e.time").write_text("1 2 1\n")
    _lastfailed(r, "e2e/lf", ["tests/test_g.py::test_p"])
    _lastfailed(r, "many/lf", [f"tests/test_g.py::test_{i}" for i in range(201)])
    got = train.red_tests(r, "main", [
        {"lastfailed": "unit/lf", "rootdir": ".", "stage": "unit"},
        {"lastfailed": "e2e/lf", "rootdir": ".", "stage": "e2e"},
        {"lastfailed": "many/lf", "rootdir": ".", "stage": "e2e"},
        {"lastfailed": "x/lf", "rootdir": ".", "stage": "lint"},
        {"lastfailed": "y/lf", "rootdir": ".", "stage": None}], {})
    assert got["stages"] == ["e2e"]
    reasons = [s.get("reason") for s in got["sources"]]
    assert reasons == ["stage not red", None, "too_many", "unknown stage", "unknown stage"]
    assert got["sources"][1]["ids"] == {"tests/test_g.py::test_p": True}
    assert got["sources"][2]["n"] == 201


def _broken(kind: str):
    def write(root: Path) -> None:
        p = root / LASTFAILED
        p.parent.mkdir(parents=True, exist_ok=True)
        if kind == "symlink":
            (root / ".pytest_cache/elsewhere.json").write_text('{"tests/test_new.py::test_n": true}')
            p.symlink_to(root / ".pytest_cache/elsewhere.json")
        elif kind == "large":
            p.write_text('{"tests/test_new.py::test_n": true}' + " " * (1 << 20))
        elif kind == "deep":
            p.write_text("[" * 100000)
        elif kind == "not-utf8":
            p.write_bytes(b'\xff\xfe{"a": true}')
        elif kind == "not-object":
            p.write_text('["tests/test_new.py::test_n"]')
        elif kind == "fine":
            p.write_text('{"tests/test_new.py::test_n": true}')
    return write


@pytest.mark.parametrize("kind, reason", [
    ("symlink", "not a regular file"), ("large", "larger than 1 MiB"), ("deep", "unreadable: RecursionError"),
    ("not-utf8", "not UTF-8"), ("not-object", "not a JSON object"), ("missing", "missing")])
def test_an_unreadable_lastfailed_costs_a_field_never_the_run(render, tmp_path, monkeypatch, kind, reason):
    """M2: whatever the file holds, the reader names a reason and the train runs the same
    `_sh` calls as without red_ids."""
    def run(red_ids, sub):
        root = tmp_path / sub / "repo"

        def sh(subset, cmd, nth):
            if nth == 1:
                _broken(kind)(root)
            return "red" if "b2" in subset else "green"
        return _measured(render, tmp_path / sub, monkeypatch, sh=sh, red_ids=red_ids)
    plain, plain_calls, _l, plain_rc = run(None, "plain")
    m, calls, _l, rc = run([{"lastfailed": LASTFAILED, "rootdir": ".", "stage": None}], "red")
    assert calls == plain_calls and rc == plain_rc and _shape(m) == _shape(plain)
    source = m["rounds"][0]["red_tests"]["sources"][0]
    # deep nesting: Python ≤3.13 raises RecursionError, 3.14's decoder a ValueError — a reason either way
    allowed = {reason, "not JSON"} if kind == "deep" else {reason}
    assert source.get("reason") in allowed and "ids" not in source, source


def test_the_red_ids_of_the_first_run_are_read_before_any_other_run(render, tmp_path, monkeypatch):
    root = tmp_path / "repo"

    def sh(subset, cmd, nth):
        _lastfailed(root, LASTFAILED, ["tests/test_new.py::test_n"] if nth == 1 else ["tests/test_other.py::t"])
        return "red" if "b2" in subset else "green"
    m, _calls, _log, _rc = _measured(render, tmp_path, monkeypatch, sh=sh,
                                     red_ids=[{"lastfailed": LASTFAILED, "rootdir": ".", "stage": None}])
    first, second = m["rounds"]
    # the board tree is the first run's: the new test file is not on the base
    assert first["red_tests"] == {"stages": ["suite"], "sources": [
        {"lastfailed": LASTFAILED, "rootdir": ".", "stage": "suite", "ids": {"tests/test_new.py::test_n": False}}]}
    assert second["red_path"] == "green" and "red_tests" not in second


def test_train_phases_reads_what_the_train_writes(render, tmp_path, monkeypatch):
    """v2.88: writer (M1/M2) and reader (M3) share one format — the round the train records
    is the round train-phases classes, without a hand-made fixture between them."""
    root = tmp_path / "w" / "repo"

    def sh(subset, cmd, nth):
        _lastfailed(root, LASTFAILED, ["tests/test_new.py::test_n"])
        return "red" if "b2" in subset else "green"
    m, _calls, _log, _rc = _measured(render, tmp_path / "w", monkeypatch, sh=sh,
                                     red_ids=[{"lastfailed": LASTFAILED, "rootdir": ".", "stage": None}])
    assert m["rounds"][0]["red_path"].startswith("dropped:"), m["rounds"]
    row = {"stamp": "a", "result": "green", "rounds": json.loads(json.dumps(m["rounds"]))}
    out = _train_phases(render, tmp_path / "r", [row])
    assert "offender rounds (dropped, base-red, none-survived): 1 — capable 0, not capable 1, undetermined 0" in out, out


def test_an_unchanged_file_that_does_not_define_the_test_is_unknown(render, tmp_path):
    """Refute v2.88: a test inherited from a mixin, or star-imported, is new elsewhere —
    the unchanged file that runs it is no proof it was on the base."""
    train = _load_train(render(tmp_path / "probe", {"project_name": "d", "modules": {}}))
    r = tmp_path / "inh"
    r.mkdir()
    _git(r, "init", "-q", "-b", "main")
    _git(r, "config", "user.email", "t@t")
    _git(r, "config", "user.name", "t")
    (r / "tests").mkdir()
    (r / "tests/cases.py").write_text("class Cases:\n    def test_old(self):\n        pass\n")
    (r / "tests/test_impl.py").write_text("from tests.cases import Cases\n\n\nclass TestImpl(Cases):\n    pass\n")
    _git(r, "add", "-A")
    _git(r, "commit", "-q", "-m", "base")
    _git(r, "checkout", "-q", "-b", "board")
    (r / "tests/cases.py").write_text("class Cases:\n    def test_old(self):\n        pass\n\n"
                                      "    def test_new_case(self):\n        pass\n")
    _git(r, "add", "-A")
    _git(r, "commit", "-q", "-m", "board")
    _lastfailed(r, LASTFAILED, ["tests/test_impl.py::TestImpl::test_new_case"])
    got = train.red_tests(r, "main", [{"lastfailed": LASTFAILED, "rootdir": ".", "stage": None}], {})
    assert got["sources"][0]["ids"] == {"tests/test_impl.py::TestImpl::test_new_case": "unknown"}, got


# --- v2.89 (#386): preboard — a check of seconds per candidate before it boards ----------

def _probe_gone(out: Path) -> bool:
    """Der Probebaum `<root>-train-preboard` und sein Branch `train/<stamp>-preboard` sind weg."""
    wt = out.parent / f"{out.name}-train-preboard"
    listed = _git(out, "worktree", "list", "--porcelain").stdout
    branches = _git(out, "branch", "--list", "--format=%(refname:short)").stdout.split()
    return not wt.exists() and str(wt) not in listed and not [b for b in branches if b.endswith("-preboard")]


def _checks(checked=0, dropped=(), unchecked=0, reason=None) -> dict:
    return {"checked": checked, "dropped": list(dropped), "unchecked": unchecked, "reason": reason}


def _preboard_run(train, out, monkeypatch, **kw):
    """`run()` im Prozess, mit Spionen auf `build_train` (Teilmenge, Worktree) und `_write`."""
    builds: list[tuple[list[str], object]] = []
    writes: list[tuple[str, str, str]] = []
    real_build, real_write = train.build_train, train._write

    def build(root, base, subset, stamp, log, **k):
        builds.append((list(subset), k.get("worktree")))
        return real_build(root, base, subset, stamp, log, **k)

    def write(root, state, note, worker):
        writes.append((state, note, worker))
        real_write(root, state, note, worker)
    monkeypatch.setattr(train, "build_train", build)
    monkeypatch.setattr(train, "_write", write)
    rc = train.run(out, suite="true", deploy=None, push=False, min_candidates=1, max_wait_hours=0, force=True,
                   keep_branches=True, dry_run=False, **kw)
    return rc, builds, writes


def test_preboard_red_on_a_broken_host_checks_nobody_and_the_preflight_stops_as_environment(render, tmp_path):
    """Host kaputt: der Check ist schon auf der Basis rot — niemand wird geprüft; der Preflight
    im ersten kombinierten Baum stoppt wie heute als `environment`."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    _branch(out, "beta", {"src/b.py": "b\n"})
    r = _train(out, "run", "--force", "--suite", "true", "--preboard", "exit 1", "--preflight", "exit 3")
    assert r.returncode == 1 and "preflight `exit 3` is red" in r.stderr, r.stdout + r.stderr
    assert "preboard on the base: red — not pre-checked" in r.stderr, r.stderr
    row = _phases(out)[-1]
    assert row["result"] == "environment" and isinstance(row["preboard"], float) and row["preboard"] >= 0
    assert [(x["red_path"], sorted(x["runs"])) for x in row["rounds"]] == [("environment", ["first"])]
    assert row["preboard_checks"] == _checks(unchecked=2, reason="preboard on the base: red")
    assert _probe_gone(out)


def test_preboard_red_on_the_base_blames_nobody_and_everybody_boards(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    _branch(out, "beta", {"src/b.py": "b\n"})
    r = _train(out, "run", "--force", "--suite", "true", "--preboard", "exit 1")
    assert r.returncode == 0 and "not pre-checked" in r.stderr, r.stdout + r.stderr
    row = _phases(out)[-1]
    assert row["result"] == "green" and sorted(row["branches"]) == ["alpha", "beta"]
    assert row["preboard_checks"] == _checks(unchecked=2, reason="preboard on the base: red")
    assert "preboard red" not in (out / ".git/process-train").joinpath(f"{row['stamp']}.log").read_text()


def test_preboard_judges_base_and_candidate_not_the_stale_tip(render, tmp_path):
    """Veraltete Spitze: auf der Spitze ist der Check rot, main hat es behoben — base+Kandidat ist grün."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    (out / "stale.txt").write_text("x\n")
    _repo(out)
    _branch(out, "fresh", {"src/f.py": "f\n"})
    _git(out, "rm", "-q", "stale.txt")
    _git(out, "commit", "-q", "-m", "main: drop stale.txt")
    r = _train(out, "run", "--force", "--suite", "true", "--preboard", "test ! -e stale.txt")
    assert r.returncode == 0, r.stdout + r.stderr
    row = _phases(out)[-1]
    assert row["branches"] == ["fresh"] and row["preboard_checks"] == _checks(checked=1)


def test_a_candidate_red_twice_on_the_preboard_is_blocked_and_never_built_into_the_train(
        render, tmp_path, monkeypatch, capsys):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    _branch(out, "bad", {"src/BROKEN": "x\n"})
    train = _load_train(out)
    rc, builds, writes = _preboard_run(train, out, monkeypatch, preboard="test ! -e src/BROKEN",
                                       preboard_timeout=60)
    err = capsys.readouterr().err
    assert rc == 0, err
    row = _phases(out)[-1]
    probe = out.parent / f"{out.name}-train-preboard"
    # the base, each candidate on base+it, the red one once more on a rebuilt tree, and the
    # base once more before anybody is reported (refute v2.89)
    assert sorted(s for s, w in builds if w == probe) == [[], [], ["alpha"], ["bad"], ["bad"]]
    trained = [s for s, w in builds if w is None]
    assert trained and all("bad" not in s for s in trained), builds
    assert writes == [("blocked", f"dropped from train {row['stamp']}: preboard red — test ! -e src/BROKEN", "bad")]
    assert "bad" in err and "preboard" in err
    assert row["result"] == "green" and row["branches"] == ["alpha"] and row["aboard"] == 2
    assert isinstance(row["preboard"], float) and row["preboard"] >= 0 and row["preboard_checks"] == _checks(checked=1, dropped=["bad"])
    assert _probe_gone(out)


def test_a_preboard_missing_everywhere_leaves_the_base_unjudged(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    r = _train(out, "run", "--force", "--suite", "true", "--preboard", "no-such-preboard-check-386")
    assert r.returncode == 0 and "preboard on the base: undefined — not pre-checked" in r.stderr, r.stderr
    row = _phases(out)[-1]
    assert row["branches"] == ["alpha"]
    assert row["preboard_checks"] == _checks(unchecked=1, reason="preboard on the base: undefined")


def test_a_candidate_that_deletes_the_preboard_script_is_unjudged_and_boards(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    (out / "check.sh").write_text("exit 0\n")
    _repo(out)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    _branch(out, "gone", {"src/g.py": "g\n"}, delete=("check.sh",))
    r = _train(out, "run", "--force", "--suite", "true", "--preboard", "sh check.sh")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "gone: not pre-checked — undefined" in r.stderr, r.stderr
    row = _phases(out)[-1]
    assert sorted(row["branches"]) == ["alpha", "gone"]
    assert row["preboard_checks"] == _checks(checked=1, unchecked=1, reason="gone: undefined")


def test_the_probe_tree_settles_plans_as_the_train_does(render, tmp_path):
    """Ein Besitzer für das Mergen: ein Plan, den `_settle_plans` archiviert, macht den Lint
    auf dem Probebaum nicht rot."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _active_plan_branch(out, "7-done", issue=7)
    train = _load_train(out)
    lines: list[str] = []
    kept, checks = train.pre_board(out, "main", ["7-done"], "t1",
                                   "test ! -e .process-work/plans/2026-09-20-7-done.md", 60, lines.append)
    assert kept == ["7-done"] and checks == _checks(checked=1), lines
    assert any("archived" in ln for ln in lines) and _probe_gone(out), lines


@pytest.mark.parametrize("residue", [False, True], ids=["red-then-green", "residue-of-the-first-run"])
def test_a_red_preboard_is_rerun_once_on_a_rebuilt_tree(render, tmp_path, tmp_path_factory, residue):
    """Rot, dann grün: er boardet. Der Retry läuft auf einem neu gebauten Baum — ein Check, der
    den Rückstand seines ersten Laufs ablehnt, ist dort grün."""
    count = tmp_path_factory.mktemp("preboard") / "n"
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    # calls: the base (n=0, green), alpha (n=1, red), alpha again (n=2, green)
    check = f'n=$(cat {count} 2>/dev/null || echo 0); echo $((n+1)) > {count}; [ "$n" != 1 ]'
    if residue:
        check = f"test ! -e residue || exit 1; touch residue; {check}"
    r = _train(out, "run", "--force", "--suite", "true", "--preboard", check)
    assert r.returncode == 0, r.stdout + r.stderr
    assert count.read_text().strip() == "3"
    row = _phases(out)[-1]
    assert row["branches"] == ["alpha"] and row["preboard_checks"] == _checks(checked=1)


def test_a_probe_tree_that_cannot_be_built_is_not_pre_checked_and_the_train_runs(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    # a file where the probe worktree goes: `worktree add` fails
    blocker = out.parent / f"{out.name}-train-preboard"
    blocker.write_text("not a worktree\n")
    r = _train(out, "run", "--force", "--suite", "true", "--preboard", "true")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "preboard on the base: not built — not pre-checked" in r.stderr, r.stderr
    row = _phases(out)[-1]
    assert row["branches"] == ["alpha"]
    assert row["preboard_checks"] == _checks(unchecked=1, reason="preboard on the base: not built")


def test_a_preboard_timeout_is_unjudged_while_the_preflight_timeout_stays_red(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    (out / "docs/process/testing.local.json").write_text(json.dumps(
        {"preboard": ["sh", "-c", "test ! -e slow.txt || sleep 30"], "preboard_timeout": 0.5}))
    _repo(out)
    _branch(out, "slow", {"slow.txt": "s\n"})
    started = time.monotonic()
    r = _train(out, "run", "--force", "--suite", "true")
    assert r.returncode == 0 and time.monotonic() - started < 25, r.stdout + r.stderr
    row = _phases(out)[-1]
    assert row["branches"] == ["slow"] and row["preboard_checks"] == _checks(unchecked=1, reason="slow: undefined")
    # `_sh`: red past its time by default (preflight, suite, deploy), undefined where asked
    train = _load_train(out)
    lines: list[str] = []
    assert train._sh(tmp_path, "sleep 5", lines.append, 0.3) == "red"
    assert train._sh(tmp_path, "sleep 5", lines.append, 0.3, timeout_state="undefined") == "undefined"
    assert lines == ["$ sleep 5 → killed after 0.3 s (red)", "$ sleep 5 → killed after 0.3 s (undefined)"]


def test_a_conflict_on_the_probe_merge_is_not_pre_checked_and_boards(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _branch(out, "beta", {"shared.txt": "beta\n"})
    (out / "shared.txt").write_text("main moved\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "main: shared")
    r = _train(out, "run", "--force", "--suite", "true", "--preboard", "true")
    # it boarded: the train's own build drops it as today
    assert r.returncode == 1 and "merge conflict with the batch" in r.stdout, r.stdout + r.stderr
    row = _phases(out)[-1]
    assert row["preboard_checks"] == _checks(unchecked=1, reason="beta: conflict")
    assert "preboard red" not in (out / ".git/process-train").joinpath(f"{row['stamp']}.log").read_text()
    assert _probe_gone(out)


def test_everybody_red_on_the_preboard_ends_without_a_train_build(render, tmp_path, monkeypatch, capsys):
    """Alle rot: rc 1, kein `build_train` des Zugs, die Zeile sagt `preboard` — und train-phases
    liest, was der Zug schreibt."""
    out = render(tmp_path / "w", {"project_name": "d", "modules": {}})
    _repo(out)
    _branch(out, "alpha", {"src/BROKEN": "a\n"})
    _branch(out, "beta", {"src/BROKEN": "b\n"})
    train = _load_train(out)
    rc, builds, writes = _preboard_run(train, out, monkeypatch, preboard="test ! -e src/BROKEN",
                                       preboard_timeout=60)
    assert rc == 1, capsys.readouterr().err
    assert [w for _s, w in builds if w is None] == []
    assert sorted(b for _s, _n, b in writes) == ["alpha", "beta"] and {s for s, _n, _b in writes} == {"blocked"}
    row = _phases(out)[-1]
    assert row["result"] == "preboard" and isinstance(row["preboard"], float) and row["preboard"] >= 0 and row["aboard"] == 2
    assert row["preboard_checks"] == _checks(dropped=sorted(row["preboard_checks"]["dropped"]))
    assert sorted(row["preboard_checks"]["dropped"]) == ["alpha", "beta"] and row["rounds"] == []
    assert _probe_gone(out)
    text = _train_phases(render, tmp_path / "r", [row])
    assert "preboard check: 0 checked, 2 dropped, 0 not pre-checked (in 1/1 runs)" in text, text
    assert "1 ended at the preboard check (every candidate dropped)" in text, text


def test_without_preboard_the_train_runs_as_before(render, tmp_path, monkeypatch):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    train = _load_train(out)
    calls: list[dict] = []
    real_sh = train._sh

    def sh(*a, **k):
        calls.append(k)
        return real_sh(*a, **k)
    monkeypatch.setattr(train, "_sh", sh)
    rc, builds, _writes = _preboard_run(train, out, monkeypatch)
    assert rc == 0
    assert calls and all("timeout_state" not in k for k in calls)
    assert builds and all(w is None for _s, w in builds)
    row = _phases(out)[-1]
    assert row["preboard"] == 0 and "preboard_checks" not in row
    text = (out / ".git/process-train").joinpath(f"{row['stamp']}.log").read_text()
    assert not [ln for ln in text.splitlines() if ln.split(" ", 1)[-1].startswith("preboard")], text


def test_dry_run_runs_no_preboard(render, tmp_path, tmp_path_factory):
    marker = tmp_path_factory.mktemp("preboard") / "ran"
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    r = _train(out, "run", "--force", "--dry-run", "--suite", "true", "--preboard", f"touch {marker}")
    assert r.returncode == 0 and "dry run" in r.stdout, r.stdout + r.stderr
    assert not marker.exists() and _probe_gone(out)


def test_the_configured_preboard_is_the_trains_default_and_an_empty_one_runs_none(render, tmp_path, tmp_path_factory):
    marker = tmp_path_factory.mktemp("preboard") / "ran"
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    (out / "docs/process/testing.local.json").write_text(json.dumps(
        {"preboard": ["sh", "-c", f"echo x >> {marker}"]}))
    _repo(out)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    r = _train(out, "run", "--force", "--suite", "true")
    assert r.returncode == 0, r.stdout + r.stderr
    assert marker.read_text().count("x") == 2  # the base and alpha
    _branch(out, "beta", {"src/b.py": "b\n"})
    r = _train(out, "run", "--force", "--suite", "true", "--preboard", "")
    assert r.returncode == 0, r.stdout + r.stderr
    assert marker.read_text().count("x") == 2 and "preboard_checks" not in _phases(out)[-1]


def test_the_probe_tree_is_gone_after_an_exception(render, tmp_path, monkeypatch):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    train = _load_train(out)
    probe = out.parent / f"{out.name}-train-preboard"
    seen: list[bool] = []

    def boom(cwd, cmd, log, *a, **k):
        seen.append(Path(cwd) == probe and probe.is_dir())
        raise RuntimeError("boom")
    monkeypatch.setattr(train, "_sh", boom)
    with pytest.raises(RuntimeError):
        _preboard_run(train, out, monkeypatch, preboard="true", preboard_timeout=60)
    assert seen == [True] and _probe_gone(out)
    assert _phases(out)[-1]["result"] == "red"


def test_train_phases_prints_the_preboard_time_and_counts(render, tmp_path):
    """AC-4: Sekunden aus `preboard`, Zahlen aus `preboard_checks`; `result: preboard` zählt
    getrennt von rot; kaputte Felder kosten nur ihre eigene Zählung."""
    rows = [{"stamp": "a", "result": "green", "preboard": 12.0,
             "preboard_checks": _checks(checked=2, dropped=["x"])},
            {"stamp": "b", "result": "preboard", "preboard": 8.0, "preboard_checks": _checks(dropped=["y", "z"])},
            {"stamp": "c", "result": "red", "preboard": 4.0,
             "preboard_checks": _checks(unchecked=3, reason="preboard on the base: red")},
            {"stamp": "d", "result": "green"},
            {"stamp": "e", "result": "green", "preboard_checks": "torn"},
            {"stamp": "f", "result": "green", "preboard_checks": {"checked": "2", "dropped": "x", "unchecked": None}}]
    out = _train_phases(render, tmp_path, rows)
    assert "preboard  median      2 s, max     12 s (in 3/6 runs)" in out, out
    assert ("preboard check: 2 checked, 3 dropped, 3 not pre-checked (in 4/6 runs; "
            "last reason: preboard on the base: red)") in out, out
    assert "1/6 runs ended red, 0 stopped by the preflight" in out, out
    assert "1 ended at the preboard check (every candidate dropped)" in out, out


def test_a_host_that_breaks_after_the_base_check_holds_nobody_back(render, tmp_path, tmp_path_factory):
    """Refute v2.89: the check is green on the base, then the host breaks (token,
    network, disk) — the base checked once more is red too, so nobody is reported."""
    count = tmp_path_factory.mktemp("c") / "n"
    out = render(tmp_path / "w", {"project_name": "d", "modules": {}})
    _repo(out)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    _branch(out, "beta", {"src/b.py": "b\n"})
    check = f'n=$(cat {count} 2>/dev/null || echo 0); echo $((n+1)) > {count}; [ "$n" = 0 ]'
    r = _train(out, "run", "--force", "--suite", "true", "--preboard", check)
    row = _phases(out)[-1]
    assert row["preboard_checks"]["dropped"] == [], row
    assert "turned red" in row["preboard_checks"]["reason"] and "did not board" not in r.stderr, r.stderr


def test_a_tool_missing_on_the_host_stops_as_environment_blaming_nobody(render, tmp_path):
    """Refute v2.89: the candidate's check needs a tool the host lacks; the base never
    used it — the preflight decides before anybody is reported blocked."""
    out = render(tmp_path / "w", {"project_name": "d", "modules": {}})
    (out / "check.sh").write_text("exit 0\n")
    _repo(out)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    _branch(out, "usestool", {"check.sh": "jqx-missing-386 --version\n"})
    r = _train(out, "run", "--force", "--suite", "true", "--preboard", "sh check.sh",
               "--preflight", "command -v jqx-missing-386")
    row = _phases(out)[-1]
    assert row["result"] == "environment", row
    assert "did not board" not in r.stderr, r.stderr
    # the stop reaches the row: an environment round and the counts (DeepSeek v2.89)
    assert [r["red_path"] for r in row["rounds"]] == ["environment"], row["rounds"]
    assert row["preboard_checks"]["dropped"] == ["usestool"] and "preflight_s" not in row["preboard_checks"], row


def test_a_killed_runs_probe_branch_is_removed(render, tmp_path):
    out = render(tmp_path / "w", {"project_name": "d", "modules": {}})
    _repo(out)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    wt = out.parent / f"{out.name}-train-preboard"
    _git(out, "worktree", "add", "-q", "-b", "train/20260101-0000-preboard", str(wt), "main")
    train = _load_train(out)
    kept, _checks = train.pre_board(out, "main", ["alpha"], "20261104-1200", "true", 60, lambda s: None)
    branches = _git(out, "branch", "--list", "--format=%(refname:short)").stdout.split()
    assert kept == ["alpha"] and not wt.exists()
    assert not [b for b in branches if b.endswith("-preboard")], branches



def test_a_dispatch_worktree_on_the_probe_path_is_left_alone(render, tmp_path):
    """Refute v2.89: dispatch names a branch `train-preboard`'s worktree like the probe —
    it is never removed; the check is skipped as not pre-checked."""
    out = render(tmp_path / "w", {"project_name": "d", "modules": {}})
    _repo(out)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    _git(out, "branch", "train-preboard", "main")
    wt = out.parent / f"{out.name}-train-preboard"
    _git(out, "worktree", "add", "-q", str(wt), "train-preboard")
    (wt / "wip.txt").write_text("uncommitted work\n")
    train = _load_train(out)
    kept, checks = train.pre_board(out, "main", ["alpha"], "20261104-1200", "true", 60, lambda s: None)
    assert (wt / "wip.txt").read_text() == "uncommitted work\n"
    assert kept == ["alpha"] and checks["unchecked"] == 1 and "train-preboard" in checks["reason"], checks


# --- v2.90 (#391, #335): the train keeps what it checked ----------------------------------

def _pinned(p: dict) -> dict:
    """Ein `_run_batch`-Plan, wie `plan()` ihn liefert: Basis und Spitzen beim Boarden
    festgehalten (#391) — die Fakes von `build_train` sehen sie in `shas`."""
    p["base_sha"] = "b" * 40
    for i, c in enumerate(p["candidates"]):
        c["sha"] = f"{i + 1:040x}"
    return p


def _move(out: Path, branch: str, files: dict[str, str] | None = None, delete: tuple[str, ...] = (),
          msg: str = "later") -> str:
    """Ein Commit auf `branch`, ohne ihn im Root auszuchecken — ein Worker in seinem
    Worktree während des Laufs; gibt den neuen SHA."""
    wt = out.parent / f"move-{branch.replace('/', '-')}-{time.monotonic_ns()}"
    _git(out, "worktree", "add", "-q", str(wt), branch)
    try:
        for rel, text in (files or {}).items():
            (wt / rel).parent.mkdir(parents=True, exist_ok=True)
            (wt / rel).write_text(text)
        for rel in delete:
            _git(wt, "rm", "-q", rel)
        _git(wt, "add", "-A")
        _git(wt, "commit", "-q", "-m", msg)
        return _git(wt, "rev-parse", "HEAD").stdout.strip()
    finally:
        _git(out, "worktree", "remove", "--force", str(wt))


def _run_in_process(train, out, **kw):
    args = dict(suite="true", deploy=None, push=False, min_candidates=1, max_wait_hours=0, force=True,
                keep_branches=False, dry_run=False)
    args.update(kw)
    return train.run(out, **args)


def _states_of(train, out: Path) -> list[tuple[str, str, str]]:
    return [(r["worker"], r["state"], r.get("note") or "") for r in train._report.read_reports(out)]


def test_a_fix_on_a_passenger_during_the_run_does_not_reach_the_probes(render, tmp_path, monkeypatch, capsys):
    """#391 (Kenni, Zug 20261104-0828): ein Fix kam im Lauf auf einen Passagier — die Proben
    enthielten ihn, der rote Baum nicht, und beschuldigt wurde ein Unbeteiligter. Proben und
    Neubau nehmen den festgehaltenen SHA: beschuldigt wird, wer den roten Baum rot machte."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _branch(out, "alpha", {"src/BROKEN": "x\n"})
    _branch(out, "beta", {"src/b.py": "b\n"})
    train = _load_train(out)
    suite = "test ! -e src/BROKEN"
    real_sh, moved = train._sh, []

    def sh(cwd, cmd, log, *a, **k):
        if cmd == suite and not moved:  # the first, red run: the fix lands on alpha meanwhile
            moved.append(_move(out, "alpha", delete=("src/BROKEN",), msg="fix: broken"))
        return real_sh(cwd, cmd, log, *a, **k)
    monkeypatch.setattr(train, "_sh", sh)
    rc = _run_in_process(train, out, suite=suite, retry=suite)
    said = capsys.readouterr()
    assert rc == 0, said.out + said.err
    assert "red with alpha aboard" in said.out and "red with beta aboard" not in said.out, said.out
    log = _git(out, "log", "--format=%s", "main").stdout
    assert "train: merge beta" in log and "merge alpha" not in log
    assert _git(out, "rev-parse", "alpha").stdout.strip() == moved[0]  # blamed: the branch stays
    assert ("alpha", "blocked", f"dropped from train {_phases(out)[-1]['stamp']}: red with it aboard") \
        in _states_of(train, out)


def test_a_fetch_that_moves_the_base_mid_run_moves_no_run(render, tmp_path, monkeypatch, capsys):
    """#391: jeder Lauf baut auf `base_sha` — ein `git fetch`, der `origin/main` im Lauf
    bewegt, macht weder den Neubau noch die Basisprobe rot."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    _branch(out, "bad", {"src/BAD": "x\n"})
    _git(out, "update-ref", "refs/remotes/origin/main", "main")
    _git(out, "checkout", "-q", "-b", "next-main", "main")
    (out / "src").mkdir(exist_ok=True)
    (out / "src/MAINBAD").write_text("x\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "main moves on, red")
    ahead = _git(out, "rev-parse", "HEAD").stdout.strip()
    _git(out, "checkout", "-q", "main")
    _git(out, "branch", "-q", "-D", "next-main")
    train = _load_train(out)
    suite = "test ! -e src/BAD && test ! -e src/MAINBAD"
    real_sh, fetched = train._sh, []

    def sh(cwd, cmd, log, *a, **k):
        if cmd == suite and not fetched:  # a fetch on the host while the first suite runs
            fetched.append(_git(out, "update-ref", "refs/remotes/origin/main", ahead))
        return real_sh(cwd, cmd, log, *a, **k)
    monkeypatch.setattr(train, "_sh", sh)
    rc = _run_in_process(train, out, suite=suite)
    said = capsys.readouterr()
    assert rc == 0 and "fix main first" not in said.err, said.out + said.err
    assert "red with bad aboard" in said.out
    assert (out / "src/a.py").is_file() and not (out / "src/MAINBAD").exists()


def test_a_commit_after_boarding_rides_no_train_and_its_branch_stays(render, tmp_path, monkeypatch, capsys):
    """#391: die Eignung galt zur Plan-Zeit, der Merge las zur Bau-Zeit — ein Commit danach,
    ohne Review, stieg mit ein. Jetzt fährt der geprüfte SHA; der bewegte Branch bleibt
    stehen, ohne `done` und ohne `forget_branch`."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    _branch(out, "beta", {"src/b.py": "b\n"})
    train = _load_train(out)
    real_plan, late = train.plan, []

    def plan(root, **kw):
        p = real_plan(root, **kw)
        late.append(_move(out, "alpha", files={"src/late.py": "unreviewed\n"}))
        return p
    monkeypatch.setattr(train, "plan", plan)
    import dispatch
    forgot: list[str] = []
    monkeypatch.setattr(dispatch, "forget_branch", lambda root, b: forgot.append(b))
    rc = _run_in_process(train, out)
    said = capsys.readouterr()
    assert rc == 0, said.out + said.err
    assert (out / "src/a.py").is_file() and (out / "src/b.py").is_file()
    assert not (out / "src/late.py").exists()  # the unreviewed commit stayed off main
    branches = _git(out, "branch", "--list", "--format=%(refname:short)").stdout.split()
    assert "alpha" in branches and "beta" not in branches
    assert _git(out, "rev-parse", "alpha").stdout.strip() == late[0]
    assert forgot == ["beta"]
    states = _states_of(train, out)
    assert ("beta", "done") in [(w, s) for w, s, _n in states]
    assert "alpha" not in [w for w, s, _n in states if s == "done"]
    stamp = _phases(out)[-1]["stamp"]
    text = (out / f".git/process-train/{stamp}.log").read_text()
    assert "alpha moved since boarding — merged at " in text and "need their own review and train" in text


def test_a_pinned_merge_reads_identity_by_name_and_content_by_sha(render, tmp_path):
    """Plan-Review Runde 1: der SHA nur für den Inhalt — ein Plan auf der Basis, der die Issue
    des Branches nennt, bleibt sein eigener: `Refs` statt `Closes`, der DoD-deviation-Hold wie
    bisher, gelesen am festgehaltenen SHA, nicht an der bewegten Spitze."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _plan_on_main(out, "2026-09-01-61-work.md", "# work\n\ntier: 1\nissue: #61\n\n## Decisions\n")
    _git(out, "checkout", "-q", "-b", "61-work", "main")
    plan = out / ".process-work/plans/2026-09-01-61-work.md"
    plan.write_text(plan.read_text() + "DoD-deviation: open AC-2 — the CLI follows\n")
    (out / "src").mkdir(exist_ok=True)
    (out / "src/w.py").write_text("w\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "feat: work")
    _git(out, "checkout", "-q", "main")
    sha = _git(out, "rev-parse", "61-work").stdout.strip()
    base_sha = _git(out, "rev-parse", "main").stdout.strip()
    # the tip moves on: the deviation is gone there — the pinned content still carries it
    _move(out, "61-work", files={".process-work/plans/2026-09-01-61-work.md":
                                 "# work\n\ntier: 1\nissue: #61\n\n## Decisions\n"})
    train = _load_train(out)
    logged: list[str] = []
    wt, _b, merged, _d = train.build_train(out, base_sha, ["61-work"], "t61", logged.append,
                                           shas={"61-work": sha})
    try:
        assert merged == ["61-work"]
        body = _git(wt, "log", "-1", "--format=%B").stdout
        assert "DoD-deviation: open AC-2 — the CLI follows" in body and "Refs #61" in body, body
        assert "Closes" not in body
        assert _git(wt, "rev-parse", "HEAD^2").stdout.strip() == sha
        assert any("#61 stays open" in line for line in logged), logged
    finally:
        _git(out, "worktree", "remove", "--force", str(wt))
    found = train._deviations(out, base_sha, "61-work", tip=sha)
    assert found is not None and found[1] == {61}


def test_after_the_push_done_names_the_issue_and_a_moved_origin_copy_stays(render, tmp_path, monkeypatch, capsys):
    """`log base..b` las nach dem Push nichts mehr (`origin/main` war vorgerückt): `done` nannte
    keine Issue. Jetzt `base_sha..sha`. Und die Kopie auf origin, auf die der Worker im Lauf
    gepusht hat, löscht der Zug nicht (`--force-with-lease`)."""
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    _repo(out)
    bare = tmp_path / "origin.git"
    _git(out, "clone", "-q", "--bare", str(out), str(bare))
    _git(out, "remote", "add", "origin", str(bare))
    _git(out, "fetch", "-q", "origin")
    _git(out, "branch", "-q", "--set-upstream-to=origin/main", "main")
    _branch(out, "62-feat", {"src/f.py": "f\n"})
    _git(out, "checkout", "-q", "62-feat")
    _git(out, "commit", "-q", "--amend", "-m", "feat: f\n\nRefs #62")
    _git(out, "checkout", "-q", "main")
    _git(out, "push", "-q", "origin", "62-feat")
    train = _load_train(out)
    real_plan, pushed = train.plan, []

    def plan(root, **kw):
        p = real_plan(root, **kw)
        _git(out, "branch", "-q", "copy-62", "62-feat")
        pushed.append(_move(out, "copy-62", files={"src/g.py": "g\n"}))
        _git(out, "push", "-q", "--force", "origin", "copy-62:62-feat")  # the worker, from elsewhere
        _git(out, "branch", "-q", "-D", "copy-62")
        return p
    monkeypatch.setattr(train, "plan", plan)
    rc = _run_in_process(train, out, push=True)
    said = capsys.readouterr()
    assert rc == 0, said.out + said.err
    done = [r for r in train._report.read_reports(out) if r["worker"] == "62-feat" and r["state"] == "done"]
    assert done and done[-1]["issue"] == 62 and "issues [62]" in done[-1]["note"], done
    branches = _git(out, "branch", "--list", "--format=%(refname:short)").stdout.split()
    assert "62-feat" not in branches  # the local copy is the one that boarded: merged, deleted
    assert _git(bare, "rev-parse", "refs/heads/62-feat").stdout.strip() == pushed[0]
    assert "62-feat" in said.err and "origin" in said.err


def _suite_reporting(out: Path, tmp: Path, *lines: str, first_rc: int = 0) -> str:
    """Eine Suite, die beim ersten Lauf Reports schreibt — ein Worker oder Steward während
    des Laufs — und `first_rc` gibt; danach grün."""
    mark = tmp / "reported"
    script = tmp / "suite-reporting.sh"
    report = f"{sys.executable} {out}/scripts/process/report.py"
    body = "\n".join(ln if ln.startswith("echo ") else f"{report} {ln} --root {out}" for ln in lines)
    script.write_text(f"if [ ! -e {mark} ]; then\ntouch {mark}\n{body}\nexit {first_rc}\nfi\nexit 0\n")
    return f"sh {script}"


def _held_run(out: Path, suite: str):
    r = _train(out, "run", "--force", "--suite", suite)
    row = _phases(out)[-1]
    log = (out / f".git/process-train/{row['stamp']}.log").read_text()
    return r, row, log


def test_a_blocked_report_written_during_the_run_drops_the_passenger(render, tmp_path):
    """#335: ein Hold, der im Lauf gesetzt wird, kam nicht mehr an. Vor dem Push wird neu
    gelesen: der Passagier steigt aus, der Rest fährt ohne ihn, `held` steht in der Zeile —
    und der Zug schreibt kein eigenes `blocked`."""
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    _repo(out)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    _branch(out, "beta", {"src/b.py": "b\n"})
    r, row, log = _held_run(out, _suite_reporting(out, tmp_path, "blocked --worker beta --note 'wait for #12'"))
    assert r.returncode == 0, r.stdout + r.stderr
    assert row["held"] == ["beta"] and row["branches"] == ["alpha"], row
    assert [x["red_path"] for x in row["rounds"]] == ["green", "green"], row["rounds"]
    assert "beta held during the run" in log
    assert "beta" in r.stderr and "held during the run" in r.stderr
    main = _git(out, "log", "--format=%s", "main").stdout
    assert "train: merge alpha" in main and "merge beta" not in main
    assert "beta" in _git(out, "branch", "--list", "--format=%(refname:short)").stdout.split()
    notes = [n for w, _s, n in _states_of(_load_train(out), out) if w == "beta"]
    assert notes == ["wait for #12"], notes  # the worker's own report counts, no train-written one


def test_a_blocked_released_again_during_the_run_still_drops(render, tmp_path):
    """Die Freigabe gilt der neuen Spitze, nicht der festgehaltenen."""
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    _repo(out)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    _branch(out, "beta", {"src/b.py": "b\n"})
    r, row, _log = _held_run(out, _suite_reporting(out, tmp_path, "blocked --worker beta --note fix",
                                                   "review-pass --worker beta"))
    assert r.returncode == 0, r.stdout + r.stderr
    assert row["held"] == ["beta"] and row["branches"] == ["alpha"], row


def test_a_blocked_with_another_hosts_old_clock_still_counts(render, tmp_path):
    """Kein Zeitfilter: ein `blocked`, dessen Epoche weit vor dem Boarden liegt (die Uhr eines
    anderen Hosts), ist neu, weil es beim Boarden nicht da war — auch hinter einem `pushed`."""
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    _repo(out)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    _branch(out, "beta", {"src/b.py": "b\n"})
    path = _load_train(out)._report.reports_path(out)
    now = int(time.time())
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"worker": "beta", "epoch": now, "state": "pushed", "note": "", "host": "h"}) + "\n")
        # the skewed host was read at boarding: its news counts, whatever its clock says
        # (a host first read during the run brings history, not news — refute v2.90)
        fh.write(json.dumps({"worker": "gamma", "epoch": now - 20 * 86400, "state": "idle", "note": "",
                             "host": "skewed"}) + "\n")
    old = json.dumps({"worker": "beta", "epoch": now - 10 * 86400, "state": "blocked",
                      "note": "steward: hold", "host": "skewed"})
    r, row, _log = _held_run(out, _suite_reporting(out, tmp_path, f"echo '{old}' >> {path}"))
    assert r.returncode == 0, r.stdout + r.stderr
    assert row["held"] == ["beta"] and row["branches"] == ["alpha"], row


def test_a_train_written_blocked_during_the_run_holds_nothing(render, tmp_path):
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    _repo(out)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    _branch(out, "beta", {"src/b.py": "b\n"})
    r, row, _log = _held_run(out, _suite_reporting(
        out, tmp_path, "blocked --worker beta --note 'dropped from train 20261104-0000: red with it aboard'"))
    assert r.returncode == 0, r.stdout + r.stderr
    assert row["held"] == [] and sorted(row["branches"]) == ["alpha", "beta"], row


def test_a_stacked_passenger_that_contains_a_held_one_is_held_too(render, tmp_path):
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    _repo(out)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    # Tier 1: a stack carries its base's archived plan twice, and a de-dated slug that is
    # not unique clears nothing (the review gate's rule) — beside the point here
    _branch(out, "beta", {"src/b.py": "b\n"}, tier=1, reviewed=False)
    _branch(out, "beta-more", {"src/c.py": "c\n"}, tier=1, reviewed=False, start="beta")
    by = {c["branch"]: c for c in json.loads(_train(out, "plan", "--json").stdout)["candidates"]}
    assert all(by[b]["eligible"] for b in ("alpha", "beta", "beta-more")), {b: c["reasons"] for b, c in by.items()}
    r, row, log = _held_run(out, _suite_reporting(out, tmp_path, "blocked --worker beta --note hold"))
    assert r.returncode == 0, r.stdout + r.stderr
    assert sorted(row["held"]) == ["beta", "beta-more"] and row["branches"] == ["alpha"], row
    assert "beta-more held during the run — it contains beta" in log


def test_the_round_before_the_hold_keeps_its_flaky(render, tmp_path):
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    _repo(out)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    _branch(out, "beta", {"src/b.py": "b\n"})
    r, row, _log = _held_run(out, _suite_reporting(out, tmp_path, "blocked --worker beta --note hold", first_rc=1))
    assert r.returncode == 0, r.stdout + r.stderr
    assert [x["red_path"] for x in row["rounds"]] == ["flaky", "green"], row["rounds"]
    assert row["held"] == ["beta"] and row["branches"] == ["alpha"]


def test_every_passenger_held_during_the_run_merges_nothing(render, tmp_path):
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    _repo(out)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    head = _git(out, "rev-parse", "main").stdout
    r, row, _log = _held_run(out, _suite_reporting(out, tmp_path, "blocked --worker alpha --note hold"))
    assert r.returncode == 1, r.stdout + r.stderr
    assert row["held"] == ["alpha"] and row["branches"] == [] and row["result"] == "red", row
    assert _git(out, "rev-parse", "main").stdout == head
    assert not [b for b in _git(out, "branch", "--list", "--format=%(refname:short)").stdout.split()
                if b.startswith("train/")]


# --- v2.91 (#398, #399): the train plans faster and says who stays behind, and why ---------

def test_the_plan_bench_builds_a_repo_and_reports_the_time(tmp_path):
    """M0: das Messwerkzeug baut das synthetische Repo und misst `plan` — geprüft wird das
    Werkzeug, nicht die Zahl (die Laufzeit des Runners schwankt)."""
    tool = Path(__file__).resolve().parents[1] / "tools/bench_train_plan.py"
    r = subprocess.run([sys.executable, str(tool), "--branches", "20", "--plans", "20", "--runs", "1",
                        "--workdir", str(tmp_path / "bench")], capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout + r.stderr
    result = json.loads(r.stdout)
    assert result["branches"] == 20 and result["ahead"] + result["merged"] == 20
    assert len(result["seconds"]) == 1 and result["median_seconds"] > 0
    assert result["candidates"] == result["ahead"] == result["eligible"], result
    again = subprocess.run([sys.executable, str(tool), "--branches", "20", "--workdir", str(tmp_path / "bench")],
                           capture_output=True, text=True, timeout=60)
    assert again.returncode == 2 and "not empty" in again.stderr, again.stderr  # DeepSeek v2.91: kein FileExistsError


def _git_calls(monkeypatch) -> list[list[str]]:
    """Jeder git-Aufruf des Prozesses, als argv hinter `git -C <root>` — gezählt, nicht verändert."""
    calls: list[list[str]] = []
    real = subprocess.run

    def spy(argv, *a, **k):
        if isinstance(argv, list) and argv[:1] == ["git"]:
            calls.append(argv[3:] if argv[1:2] == ["-C"] else argv[1:])
        return real(argv, *a, **k)

    monkeypatch.setattr(subprocess, "run", spy)
    return calls


def _merged_branches(out: Path, n: int) -> dict[str, str]:
    """`n` Branches ohne Vorsprung auf drei älteren main-Commits; main zieht danach weiter."""
    for i in range(3):
        _main_commit(out, {f"src/old{i}.py": f"{i}\n"}, f"old {i}")
    for i in range(n):
        _git(out, "branch", f"m{i:02}", f"main~{i % 3 + 1}")
    return {f"m{i:02}": _git(out, "rev-parse", f"m{i:02}").stdout.strip() for i in range(n)}


def test_merged_branches_are_sorted_out_before_any_diff(render, tmp_path, monkeypatch):
    """#398 AC-1/2 (S1): ein `for-each-ref --merged` sortiert die gemergten Branches aus —
    kein Diff nennt ihre Spitze, `plan` zählt sie in `no_lead`; ein Branch mit Vorsprung
    boardet wie bisher."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    merged = _merged_branches(out, 30)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    train = _load_train(out)
    calls = _git_calls(monkeypatch)
    p = train.plan(out, min_candidates=1, max_wait_hours=0)
    diffs = [c for c in calls if c[:1] == ["diff"]]
    assert diffs, "der Zähler sah keinen Diff"
    named = [c for c in diffs if any(sha in arg for sha in merged.values() for arg in c)]
    assert named == [], named[:3]
    assert p["no_lead"] == 30
    assert [c["branch"] for c in p["candidates"]] == ["alpha"] and p["candidates"][0]["eligible"]


def test_an_unreadable_plan_diff_of_a_merged_branch_blocks_nobody(render, tmp_path, monkeypatch):
    """S1, bewusste Urteilsänderung: der Plan-Diff eines gemergten Branches wird nicht mehr
    gelesen — unlesbar blockierte er bisher jeden Kandidaten (die globale `unreadable`-Liste)."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    merged = _merged_branches(out, 1)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    train = _load_train(out)
    real = train._git_bytes
    monkeypatch.setattr(train, "_git_bytes", lambda root, *a: None if a[0] == "diff" and any(
        merged["m00"] in x for x in a) else real(root, *a))
    alpha = next(c for c in train.candidates(out, "main", "main") if c["branch"] == "alpha")
    assert alpha["eligible"], alpha["reasons"]


def test_a_branch_moved_after_the_snapshot_takes_the_normal_way(render, tmp_path, monkeypatch):
    """S1 (Wächter): aussortiert wird nur, wessen gelistete SHA die des Snapshots ist — ein
    Branch, der nach dem Snapshot auf einen gemergten Commit zurückgesetzt wurde, wird am
    festgehaltenen SHA beurteilt (#391)."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _main_commit(out, {"src/old.py": "old\n"}, "old")
    _branch(out, "alpha", {"src/a.py": "a\n"})
    boarded = _git(out, "rev-parse", "alpha").stdout.strip()
    train = _load_train(out)
    real = train._snapshot

    def snapshot_then_move(root, base):
        taken = real(root, base)
        _git(out, "update-ref", "refs/heads/alpha", "main~1")  # now merged, after the snapshot
        return taken

    monkeypatch.setattr(train, "_snapshot", snapshot_then_move)
    alpha = next(c for c in train.candidates(out, "main", "main") if c["branch"] == "alpha")
    assert alpha["sha"] == boarded and alpha["ahead"] == 1 and alpha["eligible"], alpha


def test_the_dispatch_records_are_read_once_per_planning(render, tmp_path, monkeypatch):
    """#398 (S3): `candidates()` liest die Zuordnung der Dispatch-Records einmal und reicht sie
    an `dispatch.branch_issues` durch; ohne sie antwortet `branch_issues` wie bisher."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    for name in ("alpha", "beta", "gamma"):
        _branch(out, name, {f"src/{name}.py": "x\n"})
    _package_branch(out, "70-p1-slice", "71")
    _report(out, "70-p1-slice")
    _dispatched(out, 71, "70-p1-slice")
    train = _load_train(out)
    import dispatch  # the module train imports lazily
    real = dispatch._placed
    reads: list[int] = []
    monkeypatch.setattr(dispatch, "_placed", lambda root: reads.append(1) or real(root))
    by = {c["branch"]: c for c in train.candidates(out, "main", "main")}
    assert len(reads) == 1, len(reads)
    assert by["70-p1-slice"]["eligible"] and all(by[b]["eligible"] for b in ("alpha", "beta", "gamma")), by
    placed = real(out)
    for branch in ("70-p1-slice", "alpha"):
        assert dispatch.branch_issues(out, branch) == dispatch.branch_issues(out, branch, placed)
    assert dispatch.branch_issues(out, "70-p1-slice") == {"70", "71"}


def test_a_departing_run_logs_its_planning_time_as_the_plan_phase(render, tmp_path):
    """#398 AC-3 (S4): die Phase `plan` steht in der Zeile des abfahrenden Laufs, und
    `train-phases` zeigt sie."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    r = _train(out, "run", "--force", "--suite", "true")
    assert r.returncode == 0, r.stdout + r.stderr
    row = _phases(out)[-1]
    assert row["plan"] > 0, row
    text = _train_phases(render, tmp_path / "kpis", [{"stamp": "s", "result": "green", "plan": 12.0, "suite": 5.0}])
    assert "plan      median     12 s, max     12 s (in 1/1 runs)" in text, text


@pytest.mark.parametrize("args, said", [(("--min-candidates", "5"), "holding"), ((), "nothing to do")])
def test_a_holding_run_prints_its_planning_time_and_logs_no_phases(render, tmp_path, args, said):
    """S4: ein haltender Lauf und einer mit „nothing to do“ drucken ihre Planungszeit und
    schreiben keine Zeile in `phases.jsonl` — ein häufig abgefragtes `run` flutet nichts."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _branch(out, "alpha", {"src/a.py": "a\n"}, reviewed=said == "holding")
    r = _train(out, "run", "--suite", "true", *args)
    assert r.returncode == 0 and said in r.stdout, r.stdout + r.stderr
    assert re.search(r"planning took \d+\.\d s", r.stdout), r.stdout
    assert not (out / ".git/process-train/phases.jsonl").exists()


def _tip_merge_bases(calls: list[list[str]], out: Path, branches) -> list[list[str]]:
    """Die `merge-base`-Aufrufe zwischen zwei Kandidaten-Spitzen (nicht gegen die Basis)."""
    tips = {_git(out, "rev-parse", b).stdout.strip() for b in branches}
    return [c for c in calls if c[:1] == ["merge-base"] and len(c) == 3 and set(c[1:]) <= tips]


def test_candidates_that_share_no_commit_cost_no_merge_base(render, tmp_path, monkeypatch):
    """#398 (S5): drei Kandidaten mit neuen Plänen, keiner gestapelt — disjunkte Commit-Mengen
    jenseits der Basis sind kein Stapel, ohne `merge-base` zwischen den Spitzen."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    for name in ("alpha", "beta", "gamma"):
        _branch(out, name, {f"src/{name}.py": "x\n"})
    train = _load_train(out)
    calls = _git_calls(monkeypatch)
    cands = train.candidates(out, "main", "main")
    assert all(c["eligible"] for c in cands) and len(cands) == 3
    assert [c for c in calls if c[:1] == ["merge-base"]], "der Zähler sah kein merge-base"
    assert _tip_merge_bases(calls, out, ("alpha", "beta", "gamma")) == []


@pytest.mark.parametrize("rev_list", ["readable", "unreadable"])
def test_a_stacked_pair_costs_one_merge_base_and_stays_one_plan(render, tmp_path, monkeypatch, rev_list):
    """S5: ein gestapeltes Paar teilt Commits — ein `merge-base` je ungeordnetem Paar, und der
    umbenannte Plan bleibt ein Plan (#201). Ein unlesbares `rev-list` nimmt den bisherigen Weg."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _stacked_rename(out)
    train = _load_train(out)
    if rev_list == "unreadable":
        real = train._git_bytes
        monkeypatch.setattr(train, "_git_bytes", lambda root, *a: None if a[0] == "rev-list" else real(root, *a))
    calls = _git_calls(monkeypatch)
    by = {c["branch"]: c for c in train.candidates(out, "main", "main")}
    assert by["issue-2260"]["eligible"], by["issue-2260"]["reasons"]
    expected = 1 if rev_list == "readable" else 2
    assert len(_tip_merge_bases(calls, out, ("issue-2260", "issue-2260-redate"))) == expected


def test_a_stacked_pair_behind_the_base_is_judged_as_before(render, tmp_path):
    """S5 (Wächter): ein Stapel hinter der Basis — main zog nach dem Abzweig weiter — bleibt
    ein Plan."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _stacked_rename(out)
    _main_commit(out, {"src/later.py": "later\n"}, "main moves on")
    train = _load_train(out)
    by = {c["branch"]: c for c in train.candidates(out, "main", "main")}
    assert by["issue-2260"]["behind"] == 1 and by["issue-2260"]["eligible"], by["issue-2260"]["reasons"]


def test_a_recreated_plan_renamed_on_an_unstacked_branch_is_two_plans(render, tmp_path):
    """S5, bewusste Urteilsänderung (Plan-Review Runde 4): main merged X1 (löscht den Plan)
    und Y1; o = X1 + O1 legt ihn neu an, b = Y1 + B1 benennt ihn um. Bisher ein Plan (ihr
    `merge-base` ist B0, keiner der Forks) — die Commit-Mengen sind disjunkt: zwei Pläne,
    strenger, wie der Docstring es sagt."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    old, new = ".process-work/plans/2026-10-01-x.md", ".process-work/plans/2026-10-08-x.md"
    _main_commit(out, {old: "# x\n\ntier: 2\nissue: #5\n"}, "B0: the plan")
    _git(out, "checkout", "-q", "-b", "x")
    _git(out, "rm", "-q", old)
    _git(out, "commit", "-q", "-m", "X1: delete the plan")
    _git(out, "checkout", "-q", "-b", "y", "main")
    _main_commit(out, {"src/y.py": "y\n"}, "Y1")
    _git(out, "checkout", "-q", "main")
    _git(out, "merge", "-q", "--no-ff", "-m", "merge x", "x")
    _git(out, "merge", "-q", "--no-ff", "-m", "merge y", "y")
    _git(out, "checkout", "-q", "-b", "o", "x")
    _main_commit(out, {old: "# x again\n\ntier: 2\nissue: #6\n"}, "O1: the plan anew")
    _git(out, "checkout", "-q", "-b", "b", "y")
    _git(out, "mv", old, new)
    _git(out, "commit", "-q", "-m", "B1: rename the plan")
    _git(out, "checkout", "-q", "main")
    train = _load_train(out)
    base = _git(out, "rev-parse", "main").stdout.strip()
    tips = {b: _git(out, "rev-parse", b).stdout.strip() for b in ("o", "b")}
    new_by = {b: {rel for letter, _s, rel in train._review.name_status(train._git_bytes(
        out, "diff", "--name-status", "-M", "-z", f"{base}...{tips[b]}", "--", train.PLANS)) if letter != "D"}
        for b in ("o", "b")}
    assert new_by == {"o": {old}, "b": {new}}
    unreadable: list[str] = []
    assert train._stacked_renames(out, base, ["o", "b"], new_by, unreadable, tips) == {}
    assert unreadable == []


def _three_left_behind(out: Path) -> list[str]:
    """Drei Kandidaten, die nicht einsteigen, und ein gemergter Branch; die Gründe und die
    `no_lead`-Zeile, wie `plan` sie zeigt."""
    _branch(out, "beta", {"src/b.py": "b\n"}, reviewed=False)                  # no pass
    _branch(out, "delta", {"src/d.py": "d\n"}, archive=False, reviewed=False)  # not finished
    _branch(out, "omega", {"src/o.py": "o\n"})                                 # an open question
    _git(out, "checkout", "-q", "omega")
    a = out / ".process-work/plans/archive/2026-09-20-omega.md"
    a.write_text(a.read_text() + "- DECISION NEEDED 2026-09-21 omega: drop the flag? — options: A, B\n")
    _git(out, "commit", "-q", "-am", "question")
    _git(out, "checkout", "-q", "main")
    _git(out, "branch", "merged-one", "main")
    text = _train(out, "plan").stdout
    said = [line for line in text.splitlines() if line.startswith("      - ") or "without a lead" in line]
    assert len([line for line in said if line.startswith("      - ")]) >= 3, text
    assert any("1 branch" in line and "without a lead" in line for line in said), text
    return said


@pytest.mark.parametrize("exit_, args", [("nothing to do", ()), ("holding", ("--min-candidates", "5")),
                                         ("departing", ("--force",))])
def test_every_exit_says_who_stays_behind_and_why(render, tmp_path, exit_, args):
    """#399 AC-1/2 (R1): „nothing to do“ (der Fall aus #399), „holding“ und „departing“ drucken
    die Gründe jedes Kandidaten, der nicht einsteigt, wortgleich mit `plan`, und die
    `no_lead`-Zeile; ein abfahrender Lauf schreibt sie vor dem ersten Build ins Zug-Log."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    if exit_ != "nothing to do":
        _branch(out, "alpha", {"src/a.py": "a\n"})
    said = _three_left_behind(out)
    r = _train(out, "run", "--suite", "true", *args)
    assert r.returncode == 0 and exit_ in r.stdout, r.stdout + r.stderr
    printed = r.stdout.splitlines()
    assert all(line in printed for line in said), (said, r.stdout)
    train_dir = out / ".git/process-train"
    if exit_ == "departing":
        log = next(train_dir.glob("2*.log")).read_text()
        before_build = log[:log.index("merged alpha")]  # build_train's first line
        assert all(line in before_build for line in said), log
        assert not (train_dir / "last-hold.txt").exists()
    else:
        held = (train_dir / "last-hold.txt").read_text()
        assert exit_ in held.splitlines()[0] and re.match(r"\d{4}-\d\d-\d\dT", held), held
        assert all(line in held.splitlines() for line in said), held


def test_a_second_holding_run_overwrites_the_hold_log(render, tmp_path):
    """R1: `last-hold.txt` wird überschrieben, nicht angehängt — zwei Läufe hinterlassen den
    Stand des zweiten."""
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _branch(out, "alpha", {"src/a.py": "a\n"})
    _three_left_behind(out)
    for wanted in ("5", "6"):
        r = _train(out, "run", "--suite", "true", "--min-candidates", wanted)
        assert "holding" in r.stdout, r.stdout + r.stderr
    held = (out / ".git/process-train/last-hold.txt").read_text()
    assert "waiting for 6" in held and "waiting for 5" not in held, held
    assert held.count("holding") == 1, held


# --- v2.95: a load abort is no finding about a passenger ------------------------------------

_ABORT_LINE = "watchdog tests/test_x.py::test_slow 10 8.2"
_MARK = f"printf '%s\\n' '{_ABORT_LINE}' >> \"$PROCESS_SUITE_ABORT\""
# what the fake suite runs for each answer: a real command under the real `_sh`, so an abort is
# the line the command appends to `$PROCESS_SUITE_ABORT`, judged by `decide` — before v2.95 the
# variable is unset, the append fails and the run reads red
_OUTCOME_CMD = {
    "green": "true",
    "red": "exit 1",
    "undefined": "./scripts/not-on-this-tree.sh",
    "abort": f"{_MARK}; exit 1",
}


def _lastfailed_cmd(node_id: str) -> str:
    return ("mkdir -p .pytest_cache/v/cache && "
            f"printf '{{\"{node_id}\": true}}' > .pytest_cache/v/cache/lastfailed")


_TREES = (("one", {"a.txt": "a\n"}),
          ("both", {"a.txt": "a\n", "tests/test_new.py": "def test_n():\n    pass\n"}),
          ("three", {"a.txt": "a\n", "tests/test_new.py": "def test_n():\n    pass\n", "c.txt": "c\n"}))


def _aborting(render, tmp_path, monkeypatch, *, sh, n=2, retry=None, red_ids=None, seen=False, gates=None,
              load=(0.0, 0.0, 0.0), via_run=False):
    """b1..bn judged on real trees — main, one = [b1], both = [b1, b2], three — with a suite
    that answers `sh(subset, cmd, nth)`: green, red, undefined, abort or a command of its own,
    run by the real `_sh`. The load is `load` on the host's CPUs; the wait's clock and sleep
    are fake. `via_run`: through `run()`, with `plan` answering the candidates. Returns a
    namespace: the rounds, the `_sh` calls, the log, rc, the EnvironmentRed raised, the
    `blocked` reports, the phases and what went to stderr."""
    import io
    from types import SimpleNamespace
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    with (out / ".gitignore").open("a") as fh:
        fh.write("\n.pytest_cache/\n")
    _repo(out)
    train = _load_train(out)
    if seen:
        train._remember_green_suite(out, train._suite_key(out, "s"))
    for name, files in _TREES:
        _git(out, "checkout", "-q", "-b", name, "main")
        for rel, text in files.items():
            (out / rel).parent.mkdir(parents=True, exist_ok=True)
            (out / rel).write_text(text)
        _git(out, "add", "-A")
        _git(out, "commit", "-q", "-m", name)
    _git(out, "checkout", "-q", "main")
    current, calls, written = [], [], []
    real_sh = train._sh

    def build(root, base, subset, stamp, log, **kw):
        current[:] = subset
        _git(out, "checkout", "-q", ("main", "one", "both", "three")[len(subset)])
        return out, "train/x", list(subset), []

    def fake_sh(cwd, cmd, log, *a, **kw):
        calls.append((tuple(current), cmd))
        answer = sh(tuple(current), cmd, len(calls))
        return real_sh(cwd, _OUTCOME_CMD.get(answer, answer), log, *a, **kw)
    clock = [0.0]
    monkeypatch.setattr(train, "_abort_clock", lambda: clock[0])
    monkeypatch.setattr(train, "_abort_sleep", lambda s: clock.__setitem__(0, clock[0] + s))
    monkeypatch.setattr(train.os, "getloadavg", lambda: load, raising=False)
    monkeypatch.setattr(train, "build_train", build)
    gate = iter(gates) if gates is not None else None
    monkeypatch.setattr(train, "_run_gates", lambda *a, **k: next(gate, True) if gate else True)
    monkeypatch.setattr(train, "_sh", fake_sh)
    monkeypatch.setattr(train, "_cleanup", lambda *a: None)
    monkeypatch.setattr(train, "_write", lambda root, state, note, worker: written.append((state, worker)))
    branches = [f"b{i}" for i in range(1, n + 1)]
    p = {"base": "main", "ready": True, "why": "forced",
         "candidates": [{"branch": b, "hours_waiting": n - i, "eligible": True} for i, b in enumerate(branches)]}
    measure: dict = {}
    phases: dict = {}
    rc = raised = None
    err, old_err = io.StringIO(), sys.stderr
    sys.stderr = err
    try:
        if via_run:
            monkeypatch.setattr(train, "plan", lambda root, **kw: p)
            rc = train.run(out, suite="s", deploy=None, push=False, min_candidates=1, max_wait_hours=0,
                           force=True, keep_branches=True, dry_run=False, retry=retry, red_ids=red_ids)
        else:
            rc = train._run_batch(out, "main", p, list(branches), "x", tmp_path / "t.log", suite="s",
                                  deploy=None, push=False, keep_branches=True, retry=retry, measure=measure,
                                  red_ids=red_ids, phases=phases)
    except SystemExit:
        rc = None  # the stub train/x cannot be fast-forwarded: the judging is done
    except train.EnvironmentRed as exc:
        raised = exc
    finally:
        sys.stderr = old_err
    if via_run:
        row = _phases(out)[-1]
        measure, phases = {"rounds": row["rounds"]}, row
        logs = sorted((out / ".git/process-train").glob("2*.log"))
        log = logs[-1].read_text() if logs else ""
    else:
        log = (tmp_path / "t.log").read_text() if (tmp_path / "t.log").exists() else ""
    return SimpleNamespace(train=train, out=out, measure=measure, calls=calls, log=log, rc=rc, raised=raised,
                           written=written, phases=phases, err=err.getvalue())


def _subsets(r) -> list[tuple[str, ...]]:
    return [sub for sub, _cmd in r.calls]


def _round_aborts(r, i: int = 0) -> list[tuple[str, object]]:
    return [(a["reason"], a["ended"]) for a in r.measure["rounds"][i].get("aborts", [])]


def test_a_first_run_that_aborts_is_repeated_and_a_green_repeat_merges(render, tmp_path, monkeypatch):
    """Plan test 2: the first run aborted, its repeat green — merged, nobody blamed, the
    round ends green and keeps its abort."""
    r = _aborting(render, tmp_path, monkeypatch, n=1, sh=lambda sub, cmd, nth: "abort" if nth == 1 else "green")
    assert r.rc is None and r.raised is None and r.written == [], r.err
    assert _shape(r.measure) == [("green", {"first": 1, "retry_abort": 1})]
    assert _subsets(r) == [("b1",), ("b1",)]
    aborts = r.measure["rounds"][0]["aborts"]
    assert [(a["reason"], a["ended"], a["wait_s"]) for a in aborts] == [(_ABORT_LINE, "load", 0.0)]
    assert f"a run aborted: {_ABORT_LINE}" in r.log


def test_a_red_repeat_without_marker_takes_todays_path(render, tmp_path, monkeypatch):
    """Plan test 3: the repeat is red without a marker — the retry plan, the base, the search:
    the real offender b2 is dropped; the red tests are read from the rebuilt tree."""
    def sh(sub, cmd, nth):
        if nth == 1:  # the aborted run leaves a lastfailed of its own
            return f"{_lastfailed_cmd('tests/test_x.py::test_slow')}; {_MARK}; exit 1"
        if "b2" in sub:
            return f"{_lastfailed_cmd('tests/test_new.py::test_n')}; exit 1"
        return "green"
    red_ids = [{"lastfailed": LASTFAILED, "rootdir": ".", "stage": None}]
    r = _aborting(render, tmp_path, monkeypatch, sh=sh, red_ids=red_ids)
    assert r.rc is None and r.measure["rounds"][0]["red_path"] == "dropped:b2", r.err  # merged: the rest
    assert _shape(r.measure) == [("dropped:b2", {"first": 1, "retry_abort": 1, "retry_full": 1, "base": 1,
                                                 "probe": 1}), ("green", {"first": 1})]
    ids = r.measure["rounds"][0]["red_tests"]["sources"][0]["ids"]
    assert ids == {"tests/test_new.py::test_n": False}, ids  # the repeat's tree, not the aborted run's


@pytest.mark.parametrize("retry", [None, "make retry"])
def test_a_test_that_always_aborts_on_a_green_base_is_red_and_its_passenger_dropped(
        render, tmp_path, monkeypatch, retry):
    """Plan test 4: b2 brings a test that writes the marker on every run. The run, its repeat,
    a fresh green base, then the search — an "aborted is red" shortcut runs the retry plan
    instead. With --retry: the retry command never runs on the base's tree, no "flaky"."""
    red_ids = [{"lastfailed": LASTFAILED, "rootdir": ".", "stage": None}]
    r = _aborting(render, tmp_path, monkeypatch, retry=retry, red_ids=red_ids,
                  sh=lambda sub, cmd, nth: "abort" if "b2" in sub else "green")
    assert r.rc is None and r.measure["rounds"][0]["red_path"] == "dropped:b2", r.err  # merged: the rest
    # the run, its repeat, the fresh base, the run once more (refute: a load that ended between
    # the repeat and the base would blame an innocent), then the search
    assert _subsets(r)[:5] == [("b1", "b2"), ("b1", "b2"), (), ("b1", "b2"), ("b1",)]
    assert _shape(r.measure)[0] == ("dropped:b2", {"first": 1, "retry_abort": 2, "base": 1, "probe": 1})
    assert r.measure["rounds"][0]["red_tests"] == "suite-aborted"
    assert [cmd for _s, cmd in r.calls] == ["s"] * len(r.calls)  # never `make retry`
    assert "flaky" not in r.log.lower() and "FLAKY" not in r.err
    assert _round_aborts(r) == [(_ABORT_LINE, "load"), (_ABORT_LINE, "load"), (_ABORT_LINE, None)]


def test_a_load_that_aborts_everything_ends_suite_aborted_and_blames_nobody(render, tmp_path, monkeypatch):
    """Plan test 5: run, repeat, base and its repeat abort — `suite-aborted`, result
    `environment`, nobody blamed, nothing merged."""
    r = _aborting(render, tmp_path, monkeypatch, via_run=True, sh=lambda sub, cmd, nth: "abort")
    assert r.rc == 1 and r.written == [], r.err
    assert r.phases["result"] == "environment" and r.phases["branches"] == []
    assert _shape(r.measure) == [("suite-aborted", {"first": 1, "retry_abort": 2, "base": 1})]
    assert "nobody is blamed" in r.err and _ABORT_LINE in r.err, r.err


def test_run_ends_suite_aborted_and_reports_who_was_dropped_before(render, tmp_path, monkeypatch):
    """Plan test 15: `SuiteAborted` ends the round `suite-aborted` (not `environment`), and
    the passenger dropped for a real red in an earlier round gets its report."""
    r = _aborting(render, tmp_path, monkeypatch, via_run=True,
                  sh=lambda sub, cmd, nth: ("red" if "b1" in sub else "green") if nth <= 4 else "abort")
    assert r.rc == 1 and r.written == [("blocked", "b1")], (r.written, r.err)
    assert [x["red_path"] for x in r.measure["rounds"]] == ["dropped:b1", "suite-aborted"]
    assert r.phases["result"] == "environment"


def test_a_base_that_aborts_after_an_undefined_first_run_blames_nobody(render, tmp_path, monkeypatch):
    """Plan test 6: the first run undefined, the base aborts twice — suite-aborted."""
    r = _aborting(render, tmp_path, monkeypatch, n=1, sh=lambda sub, cmd, nth: "undefined" if sub else "abort")
    assert isinstance(r.raised, r.train.SuiteAborted) and r.written == [], r.err
    assert _subsets(r) == [("b1",), (), ()]


def test_a_base_that_aborts_before_the_search_blames_nobody(render, tmp_path, monkeypatch):
    r = _aborting(render, tmp_path, monkeypatch, n=1, sh=lambda sub, cmd, nth: "red" if sub else "abort")
    assert isinstance(r.raised, r.train.SuiteAborted) and r.written == [], r.err
    assert _shape(r.measure) == [(None, {"first": 1, "retry_full": 1, "base": 1, "retry_abort": 1})]


def test_the_guard_before_the_first_blame_repeats_without_the_memo(render, tmp_path, monkeypatch):
    """Plan test 6 (r3, M1b): the base came from the memo; the real base run before the first
    blame aborts — its repeat runs without the memo too, aborts, and nobody is blamed."""
    r = _aborting(render, tmp_path, monkeypatch, n=1, seen=True, sh=lambda sub, cmd, nth: "red" if sub else "abort")
    assert isinstance(r.raised, r.train.SuiteAborted) and r.written == [], (r.written, r.err)
    assert _subsets(r) == [("b1",), ("b1",), (), ()]


@pytest.mark.parametrize("repeat, blamed, runs", [
    ("green", "b2", [("b1", "b2"), ("b1", "b2"), (), ("b1",), ("b1",)]),
    ("red", "b1", [("b1", "b2"), ("b1", "b2"), (), ("b1",), ("b1",), ("b2",)]),
    # the repeat aborts too: a fresh base, green — the probe runs once more, green now (the
    # load passed): b1 is innocent, b2 the offender (refute); [b1] then merges on that green
    ("abort", "b2", [("b1", "b2"), ("b1", "b2"), (), ("b1",), ("b1",), (), ("b1",)]),
])
def test_a_probe_that_aborts_is_repeated(render, tmp_path, monkeypatch, repeat, blamed, runs):
    """Plan test 6: a probe aborts; its repeat green, red, or aborted on a green base."""
    r = _aborting(render, tmp_path, monkeypatch,
                  sh=lambda sub, cmd, nth: {1: "red", 2: "red", 3: "green", 4: "abort", 5: repeat}.get(nth, "green"))
    assert r.rc is None and r.measure["rounds"][0]["red_path"] == f"dropped:{blamed}", r.err
    assert _subsets(r) == runs


def test_a_probe_whose_passenger_hangs_every_time_is_still_found(render, tmp_path, monkeypatch):
    """A probe with b1 aborts on every run: its repeat, the fresh green base, the run once
    more — it aborts again, so it counts red and b1 is dropped."""
    r = _aborting(render, tmp_path, monkeypatch,
                  sh=lambda sub, cmd, nth: {1: "red", 2: "red"}.get(nth, "abort" if "b1" in sub else "green"))
    assert r.rc is None and [x["red_path"] for x in r.measure["rounds"]] == ["dropped:b1", "green"], r.err
    assert _subsets(r) == [("b1", "b2"), ("b1", "b2"), (), ("b1",), ("b1",), (), ("b1",), ("b2",)]
    assert _shape(r.measure)[0] == ("dropped:b1", {"first": 1, "retry_full": 1, "base": 2, "probe": 1,
                                                   "retry_abort": 2})


def test_a_lane_held_during_the_first_two_runs_drops_nobody(render, tmp_path, monkeypatch):
    """Refute: the lane is held during the first run and its repeat, no test is red anywhere.
    The fresh base is green, the run once more green too — merged, nobody dropped."""
    busy = "printf '%s\\n' 'lane-busy full held by pid 4242 — other (main) since 10:01 (3 min)' " \
           ">> \"$PROCESS_SUITE_ABORT\"; exit 2"
    r = _aborting(render, tmp_path, monkeypatch, sh=lambda sub, cmd, nth: busy if nth <= 2 else "green")
    assert r.rc is None and r.raised is None and r.written == [], (r.written, r.err)
    assert _shape(r.measure) == [("green", {"first": 1, "retry_abort": 2, "base": 1})]
    assert _subsets(r) == [("b1", "b2"), ("b1", "b2"), (), ("b1", "b2")]
    assert [a for a, _e in _round_aborts(r)] == [
        "lane-busy full held by pid 4242 — other (main) since 10:01 (3 min)"] * 2


def test_a_load_during_the_search_drops_only_the_real_offender(render, tmp_path, monkeypatch):
    """Refute: b2 is the real offender; the load aborts the probe [b1] and its repeat. The
    fresh base is green, the probe once more green — b2 is dropped, b1 and b3 merge."""
    r = _aborting(render, tmp_path, monkeypatch, n=3,
                  sh=lambda sub, cmd, nth: "abort" if nth in (5, 6) else ("red" if "b2" in sub else "green"))
    assert r.rc is None and r.raised is None, r.err
    assert [x["red_path"] for x in r.measure["rounds"]] == ["dropped:b2", "green"], r.err
    assert _subsets(r) == [("b1", "b2", "b3"), ("b1", "b2", "b3"), (), ("b1", "b2"), ("b1",), ("b1",), (),
                           ("b1",), ("b1", "b3")]


def test_the_fresh_base_and_its_repeat_skip_this_trains_green(render, tmp_path, monkeypatch):
    """Plan test 6 (r2, M3a; r3, M1a): the base ran green earlier in this train; a probe aborts
    twice — the base runs fresh, and so does its repeat; both abort: suite-aborted."""
    r = _aborting(render, tmp_path, monkeypatch,
                  sh=lambda sub, cmd, nth: {1: "red", 2: "red", 3: "green"}.get(nth, "abort"))
    assert isinstance(r.raised, r.train.SuiteAborted) and r.written == [], (r.written, r.err)
    assert _subsets(r) == [("b1", "b2"), ("b1", "b2"), (), ("b1",), ("b1",), (), ()]


def test_a_probe_that_aborts_on_a_red_fresh_base_ends_base_red(render, tmp_path, monkeypatch):
    """Plan test 6 (r2, M3b; r3, m4, n4): nobody blamed in this round, the passenger dropped
    in the round before is reported, and the message says the run aborted."""
    answers = {8: "abort", 9: "abort", 3: "green"}
    r = _aborting(render, tmp_path, monkeypatch, n=3, sh=lambda sub, cmd, nth: answers.get(nth, "red"))
    assert r.rc == 1 and r.raised is None and r.written == [("blocked", "b1")], (r.written, r.err)
    assert [x["red_path"] for x in r.measure["rounds"]] == ["dropped:b1", "base-red"]
    assert _subsets(r)[-3:] == [("b2",), ("b2",), ()]
    assert "aborted" in r.err and "fix main first" in r.err and "the combined tree is red" not in r.err, r.err


def test_an_abort_on_an_undefined_base_blames_nobody(render, tmp_path, monkeypatch):
    """Plan test 6 (r3, m2): a passenger brings the suite; a probe aborts twice — hang and
    load cannot be told apart: suite-aborted, no fresh base."""
    r = _aborting(render, tmp_path, monkeypatch,
                  sh=lambda sub, cmd, nth: "undefined" if not sub else ("abort" if sub == ("b1",) else "red"))
    assert isinstance(r.raised, r.train.SuiteAborted) and r.written == [], (r.written, r.err)
    assert _subsets(r) == [("b1", "b2"), ("b1", "b2"), (), ("b1",), ("b1",)]


def test_an_aborted_failed_retry_is_repeated_on_a_rebuilt_tree(render, tmp_path, monkeypatch):
    """Plan tests 6 and 11: `--retry` aborts; the repeat is the whole suite on a rebuilt tree,
    outside the `counted` block (no exception), and its green is a flake of the full suite."""
    r = _aborting(render, tmp_path, monkeypatch, n=1, retry="make retry",
                  sh=lambda sub, cmd, nth: {1: "red", 2: "abort"}.get(nth, "green"))
    assert r.rc is None and r.raised is None and r.written == [], r.err
    assert _shape(r.measure) == [("flaky", {"first": 1, "retry_failed": 1, "retry_abort": 1})]
    assert [cmd for _s, cmd in r.calls] == ["s", "make retry", "s"]
    assert "FLAKY" in r.err and "under the retry command" not in r.err, r.err


def test_an_aborted_suite_behind_a_gates_retry_is_repeated_and_stays_a_gate_flake(render, tmp_path, monkeypatch):
    """Plan test 6 (r3, n3): the gates red, then green; the suite behind them aborts; the
    repeat is green — the message speaks of a gate flake."""
    r = _aborting(render, tmp_path, monkeypatch, n=1, gates=[False],
                  sh=lambda sub, cmd, nth: "abort" if nth == 1 else "green")
    assert r.rc is None and r.raised is None and r.written == [], r.err
    assert _shape(r.measure) == [("gate-flaky", {"first": 1, "retry_gates": 1, "retry_full": 1, "retry_abort": 1})]
    assert "a gate flake" in r.err, r.err


def test_an_aborted_run_feeds_no_memo_certificate_or_stage_times(render, tmp_path, monkeypatch):
    """Plan test 10."""
    from types import SimpleNamespace
    seen = SimpleNamespace(memo=[], cert=[], stages=[])
    real_load = _load_train

    def load(out):
        train = real_load(out)
        monkeypatch.setattr(train, "_remember_green_suite", lambda *a: seen.memo.append(a))
        monkeypatch.setattr(train, "_certify_merge", lambda *a, **k: seen.cert.append(a))
        monkeypatch.setattr(train, "_collect_stage_times", lambda *a: seen.stages.append(a))
        return train
    monkeypatch.setitem(globals(), "_load_train", load)
    r = _aborting(render, tmp_path, monkeypatch, n=1, sh=lambda sub, cmd, nth: "abort")
    assert isinstance(r.raised, r.train.SuiteAborted)
    assert seen.memo == [] and seen.cert == [] and seen.stages == []
    assert len(r.calls) == 4 and "earlier in this train" not in r.log


def test_the_wait_for_the_load_is_bounded_and_recorded(render, tmp_path, monkeypatch):
    """Plan test 9: the load never falls below the CPUs — the wait ends at its bound, in the
    round's `aborts` and the `abort_wait` phase."""
    r = _aborting(render, tmp_path, monkeypatch, n=1, load=(1000.0, 1000.0, 1000.0),
                  sh=lambda sub, cmd, nth: "abort" if nth == 1 else "green")
    aborts = r.measure["rounds"][0]["aborts"]
    assert [(a["wait_s"], a["ended"]) for a in aborts] == [(600.0, "budget")], aborts
    assert r.phases["abort_wait"] == 600.0 and "abort_wait" in r.train.PHASES


def _fake_clock():
    now = [0.0]
    slept: list[float] = []

    def sleep(s):
        slept.append(s)
        now[0] += s
    return (lambda: now[0]), sleep, slept


def test_wait_for_load_ends_when_the_load_falls(render, tmp_path, monkeypatch):
    train = _load_train(render(tmp_path / "repo", {"project_name": "d", "modules": {}}))
    clock, sleep, slept = _fake_clock()
    loads = iter([9.0, 9.0, 1.0])
    monkeypatch.setattr(train.os, "getloadavg", lambda: (next(loads), 0.0, 0.0), raising=False)
    monkeypatch.setattr(train.os, "sched_getaffinity", lambda pid: {0, 1, 2, 3}, raising=False)
    lines: list[str] = []
    waited, ended = train.wait_for_load(lines.append, clock=clock, sleep=sleep)
    assert ended == "load" and waited == 2 * train.ABORT_POLL_S and slept == [train.ABORT_POLL_S] * 2
    assert train.ABORT_WAIT_S == 600 and train.ABORT_RETRIES == 1


@pytest.mark.parametrize("missing", ["getloadavg", "oserror", "cpus"])
def test_without_a_load_or_a_cpu_count_nothing_waits_and_the_log_says_so(render, tmp_path, monkeypatch, missing):
    train = _load_train(render(tmp_path / "repo", {"project_name": "d", "modules": {}}))
    clock, sleep, slept = _fake_clock()
    if missing == "getloadavg":
        monkeypatch.delattr(train.os, "getloadavg", raising=False)
    elif missing == "oserror":
        def broken():
            raise OSError("no load")
        monkeypatch.setattr(train.os, "getloadavg", broken, raising=False)
    else:
        monkeypatch.setattr(train.os, "getloadavg", lambda: (9.0, 0.0, 0.0), raising=False)
        monkeypatch.delattr(train.os, "sched_getaffinity", raising=False)
        monkeypatch.setattr(train.os, "cpu_count", lambda: None)
    lines: list[str] = []
    waited, ended = train.wait_for_load(lines.append, clock=clock, sleep=sleep)
    assert (waited, ended, slept) == (0.0, "unread", []) and lines and "no wait" in lines[0], lines
    assert train._load()  # the red verdict's load note never raises either


def _marker_dir(out: Path) -> Path:
    return out / ".git/process-train/suite-abort"


def test_marked_runs_read_only_their_own_path(render, tmp_path, monkeypatch):
    """Plan tests 8 and 16: a marker elsewhere is not read; the marker of run n-1 does not
    count for run n; a writer after the cleanup creates no file; exit 0 with a marker is green."""
    import importlib.util
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    _repo(out)
    train = _load_train(out)
    log = lambda _l: None  # noqa: E731
    elsewhere = tmp_path / "elsewhere"
    # beside its own path: another file in the folder, a fixed path
    cmd = f"printf 'x\\n' >> \"$PROCESS_SUITE_ABORT.other\"; printf 'x\\n' >> {elsewhere}; exit 1"
    assert train._marked_sh(out, "x", out, cmd, log) == ("red", "")
    # run n-1 leaves a late writer behind; run n stays red
    late = (f"P=\"$PROCESS_SUITE_ABORT\"; echo \"$P\" > {tmp_path / 'late-path'}; "
            "(sleep 0.3; printf 'late\\n' >> \"$P\") >/dev/null 2>&1 & exit 1")
    assert train._marked_sh(out, "x", out, late, log)[0] == "red"
    assert train._marked_sh(out, "x", out, "sleep 0.8; exit 1", log)[0] == "red"
    first = Path((tmp_path / "late-path").read_text().strip())
    # a writer that keeps the contract (append, no create) after the cleanup creates nothing
    assert train._marked_sh(out, "x", out, f"echo \"$PROCESS_SUITE_ABORT\" > {tmp_path / 'p'}; exit 1",
                            log)[0] == "red"
    gone = Path((tmp_path / "p").read_text().strip())
    spec = importlib.util.spec_from_file_location("lane_under_test", out / "scripts/process/lane.py")
    lane = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lane)
    monkeypatch.setenv("PROCESS_SUITE_ABORT", str(gone))
    lane._note_suite_abort("full", "held by pid 1")
    assert not gone.exists() and first.parent == gone.parent == _marker_dir(out)
    assert first != gone and first.name.startswith(f"x-{os.getpid()}.")
    # green wins: exit 0 with a marker
    assert train._marked_sh(out, "x", out, f"{_MARK}; exit 0", log) == ("green", "")
    train._clear_aborts(out, "x")
    assert list(_marker_dir(out).iterdir()) == []


def test_exit_75_is_an_abort_at_the_top_and_red_under_make_without_a_marker(render, tmp_path, monkeypatch):
    """Plan test 1, under real make."""
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    _repo(out)
    train = _load_train(out)
    tree = _real_make(monkeypatch, tmp_path)
    (tree / "Makefile").write_text(
        "test:\n\texit 75\nmarked:\n\tprintf 'lane-busy full x\\n' >> \"$$PROCESS_SUITE_ABORT\"; exit 75\n")
    log = lambda _l: None  # noqa: E731
    assert train._sh(tree, "exit 75", log) == "aborted"
    assert train._sh(tree, "make -k test", log) == "red"
    assert train._marked_sh(out, "x", tree, "make -k test", log) == ("red", "")
    assert train._marked_sh(out, "x", tree, "make -k marked", log) == ("aborted", "lane-busy full x")


def test_the_suite_variable_reaches_the_suite_and_nothing_else(render, tmp_path, monkeypatch, capsys):
    """Plan test 8: gates, preflight, deploy and the push hook never see PROCESS_SUITE_ABORT,
    even when the parent carries it; the suite sees its own path; afterwards the folder is empty."""
    monkeypatch.setenv("PROCESS_SUITE_ABORT", str(tmp_path / "parents"))
    rec = tmp_path / "rec"
    rec.mkdir()
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    _repo(out)
    bare = tmp_path / "origin.git"
    _git(out, "clone", "-q", "--bare", str(out), str(bare))
    _git(out, "remote", "add", "origin", str(bare))
    _git(out, "fetch", "-q", "origin")
    _git(out, "branch", "-q", "--set-upstream-to=origin/main", "main")
    _branch(out, "alpha", {"src/a.py": "a\n"})
    hook = out / ".git/hooks/pre-push"
    hook.write_text(f"#!/bin/sh\necho \"${{PROCESS_SUITE_ABORT-unset}}\" > {rec}/hook\n")
    hook.chmod(0o755)
    train = _load_train(out)  # after the variable is set: `_GIT_ENV` is built at import

    def record(name):
        return f"echo \"${{PROCESS_SUITE_ABORT-unset}}\" > {rec}/{name}"
    monkeypatch.setattr(train, "gate_runner_argv", lambda wt: ["sh", "-c", record("gates")])
    rc = _run_in_process(train, out, suite=record("suite"), preflight=record("preflight"),
                         deploy=record("deploy"), push=True, keep_branches=True)
    said = capsys.readouterr()
    assert rc == 0, said.out + said.err
    for name in ("gates", "preflight", "deploy", "hook"):
        assert (rec / name).read_text().strip() == "unset", name
    suite = Path((rec / "suite").read_text().strip())
    assert suite.parent == _marker_dir(out) and suite.name.startswith(f"{_phases(out)[-1]['stamp']}-")
    assert list(_marker_dir(out).iterdir()) == []


def test_a_preboard_probe_a_held_lane_stops_under_make_boards_unchecked(render, tmp_path):
    """Plan test 7: a held lane under `make -k` writes the marker; the probe is not checked,
    boards and is never dropped."""
    lanes = tmp_path / "lanes"
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    (out / "Makefile").write_text(
        "pre:\n\tif [ -e src/lane.txt ]; then " + sys.executable
        + " scripts/process/lane.py run --lane scoped --wait 0 -- true; fi\n")
    _repo(out)
    _branch(out, "alpha", {"src/lane.txt": "x\n"})
    env = {**os.environ, "PROCESS_LANE_DIR": str(lanes), "PYTHONDONTWRITEBYTECODE": "1", "LC_ALL": "C"}
    for name in ("MAKELEVEL", "MAKEFLAGS", "PROCESS_SUITE_ABORT"):
        env.pop(name, None)
    holder = subprocess.Popen([sys.executable, str(out / "scripts/process/lane.py"), "run", "--lane", "scoped",
                               "--label", "holder", "--", sys.executable, "-c", "import time; time.sleep(60)"],
                              cwd=out, env=env)
    try:
        for _ in range(100):
            if (lanes / "test-lane-scoped.status").exists():
                break
            time.sleep(0.05)
        r = subprocess.run([sys.executable, str(out / "scripts/process/train.py"), "run", "--force", "--suite",
                            "true", "--preboard", "make -k pre"], cwd=out, env=env, capture_output=True, text=True)
    finally:
        holder.kill()
        holder.wait()
    assert r.returncode == 0, r.stdout + r.stderr
    row = _phases(out)[-1]
    checks = row["preboard_checks"]
    assert row["branches"] == ["alpha"] and checks["dropped"] == [] and checks["unchecked"] == 1, checks
    assert "alpha: aborted" in checks["reason"], checks
    assert "held back" not in (out / ".git/process-train").joinpath(f"{row['stamp']}.log").read_text()
    assert list(_marker_dir(out).iterdir()) == []


# --- v2.95: train-phases tells a suite abort from the preflight -----------------------------

def test_train_phases_tells_a_suite_abort_from_the_preflight(render, tmp_path):
    """Plan test 13: `suite-aborted` apart from the preflight, `retry_abort` its own kind, and
    the first marker line with the count of trains in a row that ended on it."""
    def run(n, s):
        return {"n": n, "build_gates_s": 1.0, "suite_s": s}

    def aborted(line):
        return {"result": "environment", "abort_wait": 30.0, "rounds": [
            {"red_path": "suite-aborted", "runs": {"first": run(1, 10.0), "retry_abort": run(2, 20.0)},
             "aborts": [{"reason": "watchdog t::a 10 9.0", "wait_s": 30.0, "ended": "budget"},
                        {"reason": line, "wait_s": 0.0, "ended": None}]}]}
    rows = [aborted("lane-busy full held by pid 1"),
            {"result": "environment", "rounds": [{"red_path": "environment", "runs": {"first": run(1, 0.0)}}]},
            aborted("lane-busy full held by pid 2"), aborted("lane-busy full held by pid 2"),
            {"result": "green", "rounds": [{"red_path": "green", "runs": {"first": run(1, 5.0)}, "aborts": [
                {"reason": "watchdog t::a 10 9.0", "wait_s": 1.0, "ended": "load"}]}]},
            aborted("lane-busy full held by pid 2")]
    out = _train_phases(render, tmp_path, rows)
    assert ("0/6 runs ended red, 1 stopped by the preflight (the host, not a passenger), "
            "4 suite aborted, nobody blamed") in out, out
    assert "runs retry_abort    8 runs, suite median     10 s per run" in out, out
    assert "abort_wait median" in out, out
    assert 'suite aborted on "lane-busy full held by pid 2" — 1 train in a row' in out, out
    rows.append(aborted("lane-busy full held by pid 2"))
    out = _train_phases(render, tmp_path / "b", rows)
    assert 'suite aborted on "lane-busy full held by pid 2" — 2 trains in a row' in out, out
