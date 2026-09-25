import json
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
    (tree / "Makefile").write_text("lint:\n\ttrue\n")  # every target of a chain is the suite's
    assert train._sh(tree, "make lint && make test", lambda _l: None) == "undefined"


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
