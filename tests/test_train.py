import json
import os
import subprocess
import sys

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
            archive: bool = True) -> None:
    _git(out, "checkout", "-q", "-b", name, "main")
    for rel, text in files.items():
        p = out / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
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
    _branch(out, "gamma", {"src/a.py": "conflict\n", "src/g.py": "g\n"})       # overlaps alpha
    _branch(out, "delta", {"src/d.py": "d\n"}, archive=False, reviewed=False)  # not finished
    _branch(out, "tiny", {"README.md": "tiny\n"}, tier=1, reviewed=False)      # tier 1 needs no pass
    r = _train(out, "plan", "--json")
    assert r.returncode == 0, r.stderr
    p = json.loads(r.stdout)
    by = {c["branch"]: c for c in p["candidates"]}
    assert by["alpha"]["eligible"] and "REVIEW pass" in by["alpha"]["by"]
    assert not by["beta"]["eligible"] and "without a REVIEW pass covering the branch head" in by["beta"]["reasons"][0]
    assert not by["gamma"]["eligible"] and "overlaps" in by["gamma"]["reasons"][0]
    assert not by["delta"]["eligible"] and "run /finish first" in by["delta"]["reasons"][0]
    assert by["tiny"]["eligible"]
    assert p["ready"] is False and "waiting for 3" in p["why"]  # 2 aboard, fresh
    text = _train(out, "plan").stdout
    assert "✓ alpha" in text and "· beta" in text and "hold" in text
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
    _git(out, "checkout", "-q", "asked")
    a.write_text(a.read_text().replace("DECISION NEEDED 2026-09-21 asked: drop", "DECISION 2026-09-21 owner: drop"))
    _git(out, "commit", "-q", "-am", "answered")
    _git(out, "checkout", "-q", "main")
    by = {c["branch"]: c for c in json.loads(_train(out, "plan", "--json").stdout)["candidates"]}
    assert by["asked"]["eligible"]


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
    # forked (two candidates on one file never board together — overlap rule)
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
    monkeypatch.setattr(train, "build_train", lambda root, base, subset, stamp, log: (wt, "train/x", list(subset), []))
    monkeypatch.setattr(train, "_run_gates", lambda w, log: True)
    monkeypatch.setattr(train, "_sh", lambda cwd, cmd, log: next(states))
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
]
_SUITE_TABLE = [r if len(r) == 8 else (*r, None) for r in _SUITE_TABLE]


@pytest.mark.parametrize("case,cmd,rc,output,level,state,words,present", _SUITE_TABLE,
                         ids=[r[0] for r in _SUITE_TABLE])
def test_suite_decide_table(render, tmp_path, case, cmd, rc, output, level, state, words, present):
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    train = _load_train(out)
    exists = None if present is None else present.__contains__
    got, reason = train.decide(train.read_facts(cmd, rc, output, level, exists))
    assert (got, words in reason) == (state, True), (case, got, reason)


def test_every_row_of_decide_has_a_table_case(render, tmp_path):
    # a row added to decide() without a case in the table fails here
    import inspect
    import re
    out = render(tmp_path / "repo", {"project_name": "d", "modules": {}})
    train = _load_train(out)
    reasons = re.findall(r'return "\w+", f?"([^"{]+)', inspect.getsource(train.decide))
    reached = {train.decide(train.read_facts(c, rc, o, lv, None if p is None else p.__contains__))[1]
               for _n, c, rc, o, lv, _s, _w, p in _SUITE_TABLE}
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
    monkeypatch.setattr(train, "build_train", lambda root, base, subset, stamp, log: (wt, "train/x", list(subset), []))
    monkeypatch.setattr(train, "_run_gates", lambda w, log: True)
    monkeypatch.setattr(train, "_sh", lambda cwd, cmd, log: next(states))
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
    written = []
    monkeypatch.setattr(train, "build_train", lambda root, base, subset, stamp, log: (wt, "train/x", list(subset), []))
    monkeypatch.setattr(train, "_run_gates", lambda w, log: True)
    monkeypatch.setattr(train, "_sh", lambda cwd, cmd, log: next(states))
    monkeypatch.setattr(train, "_git", lambda *a, **k: SimpleNamespace(returncode=0, stdout="", stderr=""))
    monkeypatch.setattr(train, "_out", lambda *a, **k: "")
    monkeypatch.setattr(train, "_cleanup", lambda *a: None)
    monkeypatch.setattr(train, "_write", lambda root, state, note, worker: written.append((state, worker)))
    p = {"base": "origin/main", "candidates": [{"branch": "b1", "hours_waiting": 2}, {"branch": "b2", "hours_waiting": 1}]}
    rc = train._run_batch(out, "main", p, ["b1", "b2"], "x", tmp_path / "t.log", suite="s", deploy=None,
                          push=False, keep_branches=True)
    assert rc == 1 and ("blocked", "b1") in written


def _head_pass(out, work, head):
    return (f"REVIEW work={work} tier=2 reviewer=fresh model=cross independence=bundle,non-implementing "
            f"verdict=pass round=1 base={'0' * 40} head={head} diff={'0' * 64}\n")


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
    wt, merged, dropped, _msgs = _settle(out, ["41-b", "40-a"], "t6")
    try:
        assert merged == ["41-b", "40-a"] and not dropped
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


def _report(out, worker, issue=None, state="review-pass"):
    extra = ["--issue", str(issue)] if issue is not None else []
    subprocess.run([sys.executable, str(out / "scripts/process/report.py"), state, "--worker", worker, *extra],
                   cwd=out, check=True, capture_output=True)


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


def test_an_issue_on_another_branch_opens_no_pass(render, tmp_path):
    out = render(tmp_path, {"project_name": "d", "modules": {}})
    _repo(out)
    _package_branch(out, "70-p2-slice", "72")
    _report(out, "70-p2-slice")
    _dispatched(out, 72, "someone-else")
    _dispatched(out, 73, "70-p2-slice")
    assert not _candidate(out, "70-p2-slice")["eligible"]


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

