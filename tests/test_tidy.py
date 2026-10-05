"""SP68: residue has one owner — tidy.py reports it and removes the safe part."""
import datetime as dt
import subprocess
import sys

import pytest


def _git(root, *args):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True)


def _run(root, *args):
    return subprocess.run([sys.executable, str(root / "scripts/process/tidy.py"), *args, "."],
                          cwd=root, capture_output=True, text=True)


def _repo_with_residue(render, tmp_path):
    out = render(tmp_path / "work", {"project_name": "d", "modules": {"speckit": True}})
    bare = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    _git(out, "init", "-q", "-b", "main")
    _git(out, "config", "user.email", "t@t")
    _git(out, "config", "user.name", "t")
    old = (dt.date.today() - dt.timedelta(days=60)).isoformat()
    (out / ".process-work/plans").mkdir(parents=True, exist_ok=True)
    (out / ".process-work/plans" / f"{old}-abandoned.md").write_text("# Plan\n\ntier: 1\n")
    (out / ".process-work/plans/archive").mkdir(parents=True, exist_ok=True)
    (out / ".process-work/plans/archive" / f"{old}-done.md").write_text("# Plan\n\ntier: 1\n")
    (out / "specs/007-finished").mkdir(parents=True)
    (out / "specs/007-finished/tasks.md").write_text("- [x] T001 done\n")
    (out / "specs/007-finished/spec.md").write_text("# Spec\n\n- SC-001 it works\n")
    (out / "specs/007-finished/plan.md").write_text("# Plan\n\nissue: #7\nsc-evidenced: SC-001 test_x\n")
    # finished, but the pruner refuses these — owner decisions
    (out / "specs/009-noplan").mkdir(parents=True)
    (out / "specs/009-noplan/tasks.md").write_text("- [x] T001 done\n")
    (out / "specs/009-noplan/spec.md").write_text("# Spec\n")
    (out / "specs/010-sc").mkdir(parents=True)
    (out / "specs/010-sc/tasks.md").write_text("- [x] T001 done\n")
    (out / "specs/010-sc/spec.md").write_text("# Spec\n\n- SC-001 a\n- SC-002 b\n")
    (out / "specs/010-sc/plan.md").write_text("# Plan\n\nissue: #10\nsc-waived: SC-001 no\n")
    (out / "specs/008-open").mkdir(parents=True)
    (out / "specs/008-open/tasks.md").write_text("- [ ] T001 todo\n")
    (out / ".process-work/template-delta/v9").mkdir(parents=True)
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "base")
    _git(out, "remote", "add", "origin", str(bare))
    _git(out, "push", "-q", "-u", "origin", "main")
    _git(out, "checkout", "-q", "-b", "agent/merged-work")
    (out / "payload.txt").write_text("x\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "feat: merged later")
    _git(out, "push", "-q", "-u", "origin", "agent/merged-work")
    _git(out, "checkout", "-q", "main")
    _git(out, "merge", "-q", "--ff-only", "agent/merged-work")
    _git(out, "push", "-q", "origin", "main")
    _git(out, "checkout", "-q", "-b", "agent/still-open")
    (out / "wip.txt").write_text("y\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "wip")
    _git(out, "push", "-q", "-u", "origin", "agent/still-open")
    _git(out, "checkout", "-q", "main")
    return out, bare


def test_dry_run_reports_every_kind_of_residue(render, tmp_path):
    out, _bare = _repo_with_residue(render, tmp_path)
    r = _run(out)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "remote branches already merged into the default branch: 1" in r.stdout
    assert "agent/merged-work" in r.stdout and "still-open" not in r.stdout
    assert "fully ticked but not published/pruned: 1 (007-finished)" in r.stdout
    assert ("publish_and_prune would refuse: 2 (009-noplan: no plan.md; "
            "010-sc: unaccounted Success Criteria SC-002)") in r.stdout
    assert "active plans older than 30 days: 1" in r.stdout and "YOUR call" in r.stdout
    assert "archived plans older than 30 days: 1" in r.stdout
    assert "template-delta/ left over" in r.stdout
    assert "dry run" in r.stdout
    # nothing touched
    assert (out / ".process-work/template-delta").is_dir()


def test_apply_removes_the_safe_part_and_keeps_owner_decisions(render, tmp_path):
    out, bare = _repo_with_residue(render, tmp_path)
    r = _run(out, "--apply")
    assert r.returncode in (0, 1), r.stdout + r.stderr  # publish needs gh: reported, not fatal
    heads = subprocess.run(["git", "--git-dir", str(bare), "branch"], capture_output=True,
                           text=True).stdout
    assert "agent/merged-work" not in heads and "agent/still-open" in heads
    assert not (out / ".process-work/template-delta").exists()
    assert not list((out / ".process-work/plans/archive").glob("*-done.md"))
    assert list((out / ".process-work/plans").glob("*-abandoned.md"))  # owner's call, kept
    assert (out / "specs/008-open").is_dir()
    assert "publish_and_prune.py 009-noplan" not in r.stdout  # never handed to the pruner
    assert "publish_and_prune.py 007-finished" in r.stdout
    assert (out / "specs/009-noplan").is_dir() and (out / "specs/010-sc").is_dir()


@pytest.mark.parametrize("state", ["untracked", "modified"])
def test_apply_keeps_an_archived_plan_git_rm_refuses(render, tmp_path, state):
    """The archive pruner fell back to unlink when git rm refused — deleting the only copy."""
    out, _bare = _repo_with_residue(render, tmp_path)
    old = (dt.date.today() - dt.timedelta(days=60)).isoformat()
    plan = out / ".process-work/plans/archive" / f"{old}-{'loose' if state == 'untracked' else 'done'}.md"
    plan.write_text("# Plan\n\ntier: 1\n\nlocal notes only here\n")
    r = _run(out, "--apply")
    assert plan.read_text().endswith("local notes only here\n")
    assert f"tidy: kept .process-work/plans/archive/{plan.name} — git rm refused" in r.stdout, r.stdout
    assert r.returncode == 1


def test_keep_glob_protects_branches(render, tmp_path):
    out, _bare = _repo_with_residue(render, tmp_path)
    r = _run(out, "--keep", "agent/*")
    assert "remote branches already merged into the default branch: 0" in r.stdout


def _tidy(out):
    import importlib.util
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("tidy_under_test", out / "scripts/process/tidy.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_an_unreadable_plan_or_an_old_pruner_never_crashes_the_report(render, tmp_path, monkeypatch):
    # an unreadable plan or an older pruner must not crash the report
    from pathlib import Path
    out = render(tmp_path / "w", {"project_name": "d", "modules": {"speckit": True}})
    d = out / "specs/011-x"
    d.mkdir(parents=True)
    (d / "tasks.md").write_text("- [x] T001\n")
    (d / "spec.md").write_text("# Spec\n")
    (d / "plan.md").write_text("# Plan\n\nissue: #11\n")
    tidy = _tidy(out)
    real = Path.read_text

    def unreadable(self, *a, **k):
        if self.name == "plan.md":
            raise PermissionError(13, "Permission denied")
        return real(self, *a, **k)

    monkeypatch.setattr(Path, "read_text", unreadable)
    assert "unreadable" in tidy.spec_blocker(out, "011-x")
    monkeypatch.setattr(Path, "read_text", real)
    (out / "scripts/process/publish_and_prune.py").write_text("x = 1\n")  # an old pruner without the helpers
    assert tidy.spec_blocker(out, "011-x") is None


def test_a_pruner_that_exits_on_import_does_not_crash_the_report(render, tmp_path):
    out = render(tmp_path / "w", {"project_name": "d", "modules": {"speckit": True}})
    d = out / "specs/012-x"
    d.mkdir(parents=True)
    (d / "spec.md").write_text("# Spec\n")
    (d / "plan.md").write_text("# Plan\n\nissue: #12\n")
    (out / "scripts/process/publish_and_prune.py").write_text("import sys\nsys.exit(3)\n")
    assert _tidy(out).spec_blocker(out, "012-x") is None


def test_a_spec_dir_a_tracked_test_still_uses_is_listed_not_applied(render, tmp_path):
    """Kenni #2382: --apply pruned a spec directory whose probe a test imported."""
    out, _bare = _repo_with_residue(render, tmp_path)
    d = out / "specs/014-probe"
    (d / "probes").mkdir(parents=True)
    (d / "tasks.md").write_text("- [x] T001 done\n")
    (d / "spec.md").write_text("# Spec\n")
    (d / "plan.md").write_text("# Plan\n\nissue: #14\n")
    (d / "probes/egress.py").write_text("OK = True\n")
    (out / "tests").mkdir(exist_ok=True)
    (out / "tests/test_probe.py").write_text("import os\nP = 'specs/014-probe/probes/egress.py'\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "probe")
    r = _run(out)
    assert ("014-probe: still referenced: specs/014-probe/probes/egress.py by "
            "tests/test_probe.py:2") in r.stdout, r.stdout
    assert "fully ticked but not published/pruned: 1 (007-finished)" in r.stdout
    r = _run(out, "--apply")
    assert "publish_and_prune.py 014-probe" not in r.stdout
    assert (d / "probes/egress.py").is_file()


# --- #136: merged worktrees (each with its own venv/node_modules) are residue -----------

def _worktree_landscape(render, tmp_path):
    """A clone with origin and one worktree per case; every branch but `open` merged."""
    import importlib.util
    import json
    import os
    out = render(tmp_path / "work", {"project_name": "d", "modules": {}})
    bare = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    _git(out, "init", "-q", "-b", "main")
    _git(out, "config", "user.email", "t@t")
    _git(out, "config", "user.name", "t")
    (out / ".gitignore").write_text("venv/\nnode_modules/\n.env\nbuild/\n__pycache__/\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "base")
    _git(out, "remote", "add", "origin", str(bare))
    _git(out, "push", "-q", "-u", "origin", "main")
    wts = {}
    for name in ("clean", "cache", "untracked", "dirty", "locked", "live", "env", "excl", "outer", "open", "fresh",
                 "built"):
        wt = tmp_path / f"work-{name}"
        _git(out, "worktree", "add", "-q", "-b", name, str(wt), "main")
        wts[name] = wt
        if name == "fresh":
            continue  # dispatched, its worker died before the first commit: at main's tip, nothing merged
        (wt / f"{name}.txt").write_text(f"{name}\n")
        _git(wt, "add", "-A")
        _git(wt, "commit", "-q", "-m", f"feat: {name}")
        (wt / "venv").mkdir()
        (wt / "venv" / "big.bin").write_bytes(b"x" * 300_000)  # ignored: an environment, not work
        if name != "open":
            _git(out, "merge", "-q", "--no-ff", "-m", f"merge {name}", name)
    _git(out, "push", "-q", "origin", "main")
    # regenerable caches go with the tree; a secret or a note git ignores does not
    for rel in ("__pycache__/m.cpython-312.pyc", "node_modules/x/index.js", "src/__pycache__/n.pyc"):
        (wts["cache"] / rel).parent.mkdir(parents=True, exist_ok=True)
        (wts["cache"] / rel).write_text("regenerable\n")
    (wts["env"] / ".env").write_text("SECRET=1\n")
    # build/ holds hand-written files as often as output (refutation): not disposable
    (wts["built"] / "build").mkdir()
    (wts["built"] / "build/handwritten.txt").write_text("by hand\n")
    (out / ".git/info/exclude").write_text("notes.md\n**/.claude/worktrees/\n")
    (wts["excl"] / "notes.md").write_text("my notes\n")
    # a subagent's worktree inside a merged one: its own branch, unmerged, with uncommitted edits
    nested = wts["outer"] / ".claude/worktrees/agent-x"
    _git(out, "worktree", "add", "-q", "-b", "agent-x", str(nested), "main")
    (nested / "agent.txt").write_text("committed\n")
    _git(nested, "add", "-A")
    _git(nested, "commit", "-q", "-m", "agent work")
    (nested / "agent.txt").write_text("uncommitted edit\n")
    wts["nested"] = nested
    # an uncommitted journal shard is work, though the tracked files are clean
    shard = wts["untracked"] / ".process-work/journal/2026-10-01-untracked.md"
    shard.parent.mkdir(parents=True, exist_ok=True)
    shard.write_text("DECISION kept\n")
    (wts["dirty"] / "dirty.txt").write_text("changed\n")
    _git(out, "worktree", "lock", str(wts["locked"]))
    _git(out, "worktree", "add", "-q", "--detach", str(tmp_path / "work-detached"), "main")
    # a live dispatch session on `live`: this very test process is its worker
    spec = importlib.util.spec_from_file_location("dispatch_for_tidy", out / "scripts/process/dispatch.py")
    d = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(d)
    recs = out / ".git/process-dispatch"
    recs.mkdir(parents=True, exist_ok=True)
    (recs / "live.json").write_text(json.dumps({
        "branch": "live", "issue": 5, "phase": "execute", "worktree": str(wts["live"]),
        "pid": os.getpid(), "pid_start": d._proc_start(os.getpid())}))
    return out, wts


def test_merged_worktrees_are_listed_with_size_and_removed_only_when_nothing_is_lost(render, tmp_path):
    out, wts = _worktree_landscape(render, tmp_path)
    r = _run(out)
    assert r.returncode == 0, r.stderr
    assert "worktrees of merged branches: 2, " in r.stdout
    assert f"{wts['clean']} (" in r.stdout and "iB)" in r.stdout  # its size, venv included
    assert f"{wts['cache']} (" in r.stdout
    kept = {ln.split(" — ")[0].split("kept: ")[1]: ln for ln in r.stdout.splitlines() if "kept: " in ln}
    assert "untracked files not ignored" in kept[str(wts["untracked"])]
    assert "uncommitted changes" in kept[str(wts["dirty"])]
    assert "locked" in kept[str(wts["locked"])]
    assert "dispatch session is live" in kept[str(wts["live"])]
    assert "not a regenerable environment or cache (.env)" in kept[str(wts["env"])]
    assert "not a regenerable environment or cache (notes.md)" in kept[str(wts["excl"])]
    assert f"holds worktree {wts['nested']}" in kept[str(wts["outer"])]
    assert "no commits of its own" in kept[str(wts["fresh"])]
    assert "not a regenerable environment or cache (build" in kept[str(wts["built"])]
    assert str(wts["open"]) not in r.stdout and "work-detached" not in r.stdout  # not merged / no branch's
    assert wts["clean"].is_dir()  # a dry run removes nothing

    r = _run(out, "--apply")
    assert r.returncode == 0, r.stdout + r.stderr
    assert not wts["clean"].exists() and not wts["cache"].exists()
    listed = _git(out, "worktree", "list").stdout
    assert str(wts["clean"]) not in listed
    for name in ("untracked", "dirty", "locked", "live", "env", "excl", "outer", "nested", "open", "fresh", "built"):
        assert wts[name].is_dir() and str(wts[name]) in listed, name
    assert (wts["untracked"] / ".process-work/journal/2026-10-01-untracked.md").is_file()
    assert (wts["nested"] / "agent.txt").read_text() == "uncommitted edit\n"
    assert (wts["env"] / ".env").is_file() and (wts["excl"] / "notes.md").is_file()


def _dispatch_of(out):
    import importlib.util
    spec = importlib.util.spec_from_file_location("dispatch_for_tidy", out / "scripts/process/dispatch.py")
    d = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(d)
    return d


def test_what_git_status_cannot_see_keeps_the_worktree(render, tmp_path):
    out, wts = _worktree_landscape(render, tmp_path)
    for name in ("clone", "assumed", "skipped", "submod"):
        wt = tmp_path / f"work-{name}"
        _git(out, "worktree", "add", "-q", "-b", name, str(wt), "main")
        (wt / f"{name}.txt").write_text(f"{name}\n")
        _git(wt, "add", "-A")
        _git(wt, "commit", "-q", "-m", f"feat: {name}")
        wts[name] = wt
    # a fork cloned into node_modules: status shows only `!! node_modules/`
    fork = wts["clone"] / "node_modules/forked"
    fork.mkdir(parents=True)
    _git(fork, "init", "-q")
    (fork / "patch.js").write_text("uncommitted fork work\n")
    # edits status is told not to look at
    _git(wts["assumed"], "update-index", "--assume-unchanged", "assumed.txt")
    (wts["assumed"] / "assumed.txt").write_text("hidden edit\n")
    _git(wts["skipped"], "update-index", "--skip-worktree", "skipped.txt")
    (wts["skipped"] / "skipped.txt").write_text("hidden edit\n")
    # a submodule: `git worktree remove` refuses it on every run
    lib = tmp_path / "libsrc"
    _git(tmp_path, "init", "-q", "-b", "main", str(lib))
    (lib / "s.txt").write_text("s\n")
    _git(lib, "-c", "user.email=t@t", "-c", "user.name=t", "add", "-A")
    _git(lib, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "s")
    _git(wts["submod"], "-c", "protocol.file.allow=always", "submodule", "add", "-q", str(lib), "lib")
    _git(wts["submod"], "commit", "-q", "-m", "lib")
    # a branch taken over from a remote worker: created from its origin ref, no local commit
    other = tmp_path / "other"
    _git(tmp_path, "clone", "-q", "-b", "main", str(tmp_path / "origin.git"), str(other))
    _git(other, "switch", "-qc", "remotework")
    (other / "rw.txt").write_text("rw\n")
    _git(other, "add", "-A")
    _git(other, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "rw")
    _git(other, "push", "-q", "origin", "remotework")
    _git(out, "fetch", "-q", "origin")
    wts["remote"] = tmp_path / "work-remote"
    _git(out, "worktree", "add", "-q", str(wts["remote"]), "remotework")
    for name in ("clone", "assumed", "skipped", "submod", "remotework"):
        _git(out, "merge", "-q", "--no-ff", "-m", f"merge {name}", name)
    _git(out, "push", "-q", "origin", "main")

    r = _run(out)
    assert r.returncode == 0, r.stderr
    kept = {ln.split(" — ")[0].split("kept: ")[1]: ln for ln in r.stdout.splitlines() if "kept: " in ln}
    assert f"holds a nested repository {fork}" in kept[str(wts["clone"])]
    assert "hidden edits possible (assume-unchanged/skip-worktree on assumed.txt)" in kept[str(wts["assumed"])]
    assert "hidden edits possible (assume-unchanged/skip-worktree on skipped.txt)" in kept[str(wts["skipped"])]
    assert "has submodules" in kept[str(wts["submod"])]
    assert str(wts["remote"]) not in kept and f"{wts['remote']} (" in r.stdout  # its work is merged
    r = _run(out, "--apply")
    assert r.returncode == 0, r.stdout + r.stderr  # no removal that fails on every run
    assert (fork / "patch.js").is_file()
    assert (wts["assumed"] / "assumed.txt").read_text() == "hidden edit\n"
    assert (wts["skipped"] / "skipped.txt").read_text() == "hidden edit\n"
    assert wts["submod"].is_dir() and not wts["remote"].exists()


def test_only_a_branch_created_from_the_integration_branch_is_fresh(render, tmp_path):
    d = _dispatch_of(render(tmp_path / "w", {"project_name": "d", "modules": {}}))
    for src in ("main", "master", "origin/main", "refs/remotes/origin/main", "refs/heads/main", "HEAD", "1a2b3c4d"):
        assert d._from_integration(src), src
    for src in ("refs/remotes/origin/remotework", "origin/remotework", "feature", "release/main/x"):
        assert not d._from_integration(src), src


def test_the_worktree_tidy_runs_in_is_never_removed(render, tmp_path):
    out, wts = _worktree_landscape(render, tmp_path)
    here = wts["clean"]
    r = subprocess.run([sys.executable, str(out / "scripts/process/tidy.py"), "--apply", "."],
                       cwd=here, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert f"kept: {here} — the current worktree" in r.stdout
    assert here.is_dir() and not wts["cache"].exists()  # the others still go


def test_an_unaskable_session_or_an_unreadable_worktree_keeps_it(render, tmp_path):
    out, wts = _worktree_landscape(render, tmp_path)
    d = _dispatch_of(out)
    entry = next(e for e in d.worktree_entries(out) if e["branch"] == "clean")
    assert d.worktree_keep_reason(out, entry, "main", []) is None
    unknown = [{"branch": "clean", "alive": False, "state": "unknown", "phase": "execute"}]
    assert "not askable" in d.worktree_keep_reason(out, entry, "main", unknown)
    (wts["clean"] / ".git").write_text(f"gitdir: {tmp_path / 'nowhere'}\n")  # git cannot read it
    assert "git status failed" in d.worktree_keep_reason(out, entry, "main", [])
    assert (tmp_path / "work-detached").is_dir() and out.is_dir()


def test_a_commit_only_in_the_worktrees_head_history_keeps_it(render, tmp_path):
    """Refute round 3: a commit made on a detached HEAD in the worktree lives only in its
    HEAD reflog, which `git worktree remove` deletes — it would hang off no ref. A worktree
    whose old commits were rebased onto main (same patches) stays removable."""
    out, wts = _worktree_landscape(render, tmp_path)
    d = _dispatch_of(out)
    for name in ("detached-work", "rebased"):
        wt = tmp_path / f"work-{name}"
        _git(out, "worktree", "add", "-q", "-b", name, str(wt), "main")
        wts[name] = wt
    # detached work, then back on the branch, which is then merged
    dw = wts["detached-work"]
    (dw / "a.txt").write_text("a\n")
    _git(dw, "add", "-A")
    _git(dw, "commit", "-q", "-m", "feat: a")
    _git(dw, "switch", "-q", "--detach")
    (dw / "only-here.txt").write_text("precious\n")
    _git(dw, "add", "-A")
    _git(dw, "commit", "-q", "-m", "experiment")
    _git(dw, "switch", "-q", "detached-work")
    _git(out, "merge", "-q", "--no-ff", "-m", "merge detached-work", "detached-work")
    # rebased: a commit, main moves, the branch is rebased onto it, then merged
    rb = wts["rebased"]
    (rb / "r.txt").write_text("r\n")
    _git(rb, "add", "-A")
    _git(rb, "commit", "-q", "-m", "feat: r")
    (out / "m.txt").write_text("m\n")
    _git(out, "add", "m.txt")
    _git(out, "commit", "-q", "-m", "main moves")
    _git(rb, "rebase", "-q", "main")
    _git(out, "merge", "-q", "--ff-only", "rebased")
    verdicts = {str(w.get("path")): reason for w, reason in d.merged_worktrees(out, "main")}

    assert "only in this worktree's HEAD history" in (verdicts.get(str(dw)) or ""), verdicts
    assert verdicts.get(str(rb)) is None, verdicts


def test_tidy_apply_rechecks_ignored_work_created_after_report(render, tmp_path):
    import importlib.util
    out, wts = _worktree_landscape(render, tmp_path)
    d = _dispatch_of(out)
    spec = importlib.util.spec_from_file_location('tidy_revalidation', out / 'scripts/process/tidy.py')
    tidy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tidy)
    _, items = tidy.report(out, 30, with_remote=False, sizes=False)
    assert wts['clean'] in items['worktrees']
    items['worktrees'] = [wts['clean']]
    items['specs'] = []
    items['old_archive'] = []
    secret = wts['clean'] / '.env'
    secret.write_text('KEEP_THIS_SECRET\n')
    assert tidy.apply(out, items, 30) == 1
    assert secret.read_text() == 'KEEP_THIS_SECRET\n'
    assert d.worktree_entries(out)


def test_removal_rechecks_live_session_after_initial_clearance(render, tmp_path):
    import json
    import os
    out, wts = _worktree_landscape(render, tmp_path)
    d = _dispatch_of(out)
    entry = next(e for e in d.worktree_entries(out) if e['branch'] == 'clean')
    assert d.worktree_keep_reason(out, entry, 'main', []) is None
    (out / '.git/process-dispatch/clean.json').write_text(json.dumps({
        'branch': 'clean', 'issue': 50, 'phase': 'execute', 'worktree': str(wts['clean']),
        'pid': os.getpid(), 'pid_start': d._proc_start(os.getpid()),
    }))
    assert 'live' in d.remove_worktree(out, wts['clean'], 'main')
    assert wts['clean'].is_dir()


def test_removal_rechecks_branch_containment_in_supplied_base(render, tmp_path):
    out, wts = _worktree_landscape(render, tmp_path)
    d = _dispatch_of(out)
    entry = next(e for e in d.worktree_entries(out) if e['branch'] == 'clean')
    assert d.worktree_keep_reason(out, entry, 'main', []) is None
    (wts['clean'] / 'new-work.txt').write_text('new branch work\n')
    _git(wts['clean'], 'add', 'new-work.txt')
    _git(wts['clean'], 'commit', '-qm', 'new work after clearance')
    assert 'not contained' in d.remove_worktree(out, wts['clean'], 'main')
    assert (wts['clean'] / 'new-work.txt').read_text() == 'new branch work\n'


def _review_landscape(render, tmp_path):
    out = render(tmp_path / "rv", {"project_name": "d", "modules": {}})
    _git(out, "init", "-q", "-b", "main")
    _git(out, "config", "user.email", "t@t")
    _git(out, "config", "user.name", "t")
    old = (dt.date.today() - dt.timedelta(days=60)).isoformat()
    newer = (dt.date.today() - dt.timedelta(days=50)).isoformat()
    today = dt.date.today().isoformat()
    rv = out / ".process-work/reviews"
    (rv / "w1").mkdir(parents=True)
    (rv / "w1/after-login-desktop-light.png").write_bytes(b"\x89PNG" + b"0" * 2048)
    for n in (1, 2, 3, 4, 5):
        (rv / f"{old}-w{n}-round-1.md").write_text(f"# Review\nwork: #{n}\n\nfindings\n")
        (rv / f"{newer}-w{n}-round-2.md").write_text(f"# Review\nwork: #{n}\n\nfindings\n")
    (rv / f"{old}-w5-round-1.md").write_text("# Review\nwork: #5\ncampaign: sweep\n\nfindings\n")
    (rv / f"{today}-w6-round-1.md").write_text("# Review\nwork: #6\n\nfindings\n")
    (rv / f"{today}-w6-round-2.md").write_text("# Review\nwork: #6\n\nfindings\n")
    line = "REVIEW work=#{n} tier=2 reviewer=fresh model=cross independence=bundle verdict={v} round=2"
    (out / ".process-work/journal").mkdir(parents=True, exist_ok=True)
    (out / ".process-work/journal/reviews.md").write_text("\n".join(
        line.format(n=n, v="block" if n == 3 else "pass") for n in (1, 2, 3, 4, 5, 6)) + "\n")
    (out / ".process-work/plans/archive").mkdir(parents=True, exist_ok=True)
    (out / ".process-work/plans" / f"{today}-two.md").write_text("# Plan\n\ntier: 2\nissue: #2\n")
    (out / ".process-work/plans/archive" / f"{today}-four.md").write_text(
        f"# Plan\n\ntier: 2\nissue: #4\nsee .process-work/reviews/{old}-w4-round-1.md\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "base")
    return out, old


def test_old_review_reports_of_closed_work_are_listed_with_sizes(render, tmp_path):
    """Reports are tracked and read on every gate run; the dry run names only
    the residue — a closed work's superseded report — and shows the size split."""
    out, old = _review_landscape(render, tmp_path)
    r = _run(out, "--days", "30")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "review reports of closed work older than 30 days: 1 (" in r.stdout
    assert f"{old}-w1-round-1.md" in r.stdout
    assert "markdown," in r.stdout and "other (evidence, never removed)" in r.stdout
    assert (out / f".process-work/reviews/{old}-w1-round-1.md").is_file()


def test_apply_removes_only_superseded_reports_of_closed_work(render, tmp_path):
    """Kept: the newest report per work (the next delta reads it), open work
    (active plan or a block), a report a record names, campaign reports,
    evidence directories, and anything inside the window."""
    out, old = _review_landscape(render, tmp_path)
    r = _run(out, "--apply")
    assert r.returncode == 0, r.stdout + r.stderr
    rv = out / ".process-work/reviews"
    left = {p.name for p in rv.glob("*.md")}
    assert f"{old}-w1-round-1.md" not in left
    assert len(left) == 11  # 12 reports, one removed
    assert (rv / "w1/after-login-desktop-light.png").is_file()
    staged = _git(out, "diff", "--cached", "--name-only").stdout.split()
    assert staged == [f".process-work/reviews/{old}-w1-round-1.md"]


def _bare_reviews(tmp_path, reports, journal, plans):
    root = tmp_path / "r"
    for sub in ("reviews", "journal", "plans"):
        (root / ".process-work" / sub).mkdir(parents=True)
    for name, text in reports.items():
        (root / ".process-work/reviews" / name).write_text(text)
    (root / ".process-work/journal/j.md").write_text(journal)
    for name, text in plans.items():
        (root / ".process-work/plans" / name).write_text(text)
    _git(root.parent, "init", "-q", str(root))
    _git(root, "add", "-A")
    _git(root, "-c", "user.email=a@b", "-c", "user.name=a", "commit", "-qm", "x")
    return root


_TIDY = __import__("pathlib").Path(__file__).resolve().parents[1] / "template/scripts/process"
_LINE = ("REVIEW work={w} tier=2 reviewer=f model=x independence=bundle,non-implementing "
         "verdict={v} round={n}\n")


def _days_ago(n):
    return (dt.date.today() - dt.timedelta(days=n)).isoformat()


def _tidy_mod():
    sys.dont_write_bytecode = True
    if str(_TIDY) not in sys.path:
        sys.path.insert(0, str(_TIDY))
    import tidy
    return tidy


def test_a_closed_works_name_match_never_takes_an_open_works_only_report(tmp_path):
    """Refute: closed `login` reached `<date>-login-v2.md` by a whole-part name
    match while it is the only report of open #9 (plan login-v2) — the one the
    bundle's prior-report lookup picks. Ownership is decided per report."""
    tidy = _tidy_mod()
    root = _bare_reviews(tmp_path, {
        f"{_days_ago(90)}-login.md": "review: login\n\nx\n",
        f"{_days_ago(60)}-login-v2.md": "review: login-v2\n\nfindings\n",
        f"{_days_ago(40)}-login.md": "review: login\n\nx\n"},
        _LINE.format(w="login", v="pass", n=2) + _LINE.format(w="#9", v="block", n=1),
        {f"{_days_ago(70)}-login-v2.md": "# Plan\n\ntier: 2\nissue: #9\n"})
    assert tidy.old_review_reports(root, 30) == [f".process-work/reviews/{_days_ago(90)}-login.md"]


def test_a_work_named_in_an_active_plans_review_line_is_open(tmp_path):
    """A plan whose stem differs from its REVIEW work= id still holds that work open."""
    tidy = _tidy_mod()
    root = _bare_reviews(tmp_path, {
        f"{_days_ago(90)}-a.md": "work: other\n\nold\n",
        f"{_days_ago(80)}-b.md": "work: other\n\nnew\n"},
        _LINE.format(w="other", v="pass", n=2),
        {f"{_days_ago(70)}-plan-x.md": "# Plan\n\ntier: 2\n\n" + _LINE.format(w="other", v="pass", n=1)})
    assert tidy.old_review_reports(root, 30) == []


def _round2_case(tmp_path, case):
    old, mid, new = _days_ago(90), _days_ago(80), _days_ago(70)
    pair = {f"{old}-a.md": "work: #9\n\nold\n", f"{mid}-b.md": "work: #9\n\nnew\n"}
    if case == "headerless":  # a file name never decides a deletion
        return _bare_reviews(tmp_path, {f"{old}-login.md": "x\n", f"{mid}-login-v2.md": "findings\n",
                                        f"{_days_ago(40)}-login.md": "x\n"},
                             _LINE.format(w="login", v="pass", n=2), {})
    if case == "url-issue":  # the plan spells the issue as a URL: same number, open
        return _bare_reviews(tmp_path, pair, _LINE.format(w="#9", v="pass", n=2),
                             {f"{new}-p.md": "# P\n\nissue: https://github.com/o/r/issues/9\n"})
    if case == "spec-md-issue":  # the spec dir's issue lives in spec.md only
        root = _bare_reviews(tmp_path, pair, _LINE.format(w="#9", v="pass", n=2), {})
        (root / "specs/001-x").mkdir(parents=True)
        (root / "specs/001-x/plan.md").write_text("# plan\n")
        (root / "specs/001-x/spec.md").write_text("issue: #9\n")
        return root
    if case == "blocked":
        return _bare_reviews(tmp_path, pair, _LINE.format(w="#9", v="block", n=2), {})
    if case == "review-header-active-plan":
        return _bare_reviews(tmp_path, {f"{old}-a.md": "review: foo\n\nold\n", f"{mid}-b.md": "review: foo\n\nnew\n",
                                        f"{new}-c.md": "review: foo\n\nnewer\n"},
                             _LINE.format(w="foo", v="pass", n=2), {f"{_days_ago(10)}-foo.md": "# P\n"})
    if case == "two-works":
        return _bare_reviews(tmp_path, {f"{old}-a.md": "work: #9\nwork: #8\n\nold\n", f"{mid}-b.md": "work: #9\n\nnew\n"},
                             _LINE.format(w="#9", v="pass", n=2) + _LINE.format(w="#8", v="pass", n=2), {})
    raise AssertionError(case)


@pytest.mark.parametrize("case", ["headerless", "url-issue", "spec-md-issue", "blocked",
                                  "review-header-active-plan", "two-works"])
def test_open_unknown_or_ambiguous_work_keeps_every_report(tmp_path, case):
    """Refute round 2: heuristics dropped open work's reports. Fail-closed —
    only a single-work header of closed work (by issue number, any spelling;
    spec.md's issue included) makes a report removable."""
    tidy = _tidy_mod()
    assert tidy.old_review_reports(_round2_case(tmp_path, case), 30) == []


def test_a_name_with_spaces_is_removed_with_git_rm(tmp_path):
    """A closed work's superseded report is removed even with a space in its name."""
    tidy = _tidy_mod()
    rel = f".process-work/reviews/{_days_ago(90)}-a b.md"
    root = _bare_reviews(tmp_path, {f"{_days_ago(90)}-a b.md": "work: #1\n\nold\n",
                                    f"{_days_ago(80)}-b.md": "work: #1\n\nnew\n"},
                         _LINE.format(w="#1", v="pass", n=2), {})
    _lines, items = tidy.report(root, 30, with_remote=False, sizes=False)
    assert items["reviews"] == [rel] and tidy.apply(root, items, 30) == 0
    assert _git(root, "diff", "--cached", "--name-only").stdout.strip().strip('"') == rel


@pytest.mark.parametrize("how", ["staged-rename", "assume-unchanged"])
def test_a_report_git_cannot_give_back_is_kept(tmp_path, how):
    """A renamed (not in HEAD) or hidden-edited (assume-unchanged) report is
    compared by blob hash with HEAD, kept and named; apply exits 1."""
    tidy = _tidy_mod()
    old = _days_ago(90)
    root = _bare_reviews(tmp_path, {f"{old}-a.md": "work: #1\n\nold\n", f"{_days_ago(80)}-b.md": "work: #1\n\nnew\n"},
                         _LINE.format(w="#1", v="pass", n=2), {})
    rv = ".process-work/reviews"
    if how == "staged-rename":
        _git(root, "mv", f"{rv}/{old}-a.md", f"{rv}/{_days_ago(91)}-a.md")
        kept = f"{rv}/{_days_ago(91)}-a.md"
    else:
        _git(root, "update-index", "--assume-unchanged", f"{rv}/{old}-a.md")
        with (root / rv / f"{old}-a.md").open("a") as fh:
            fh.write("EDIT\n")
        kept = f"{rv}/{old}-a.md"
    _lines, items = tidy.report(root, 30, with_remote=False, sizes=False)
    assert items["reviews"] == [] and kept in items["reviews_skipped"]
    assert tidy.apply(root, items, 30) == 1 and (root / kept).is_file()


@pytest.mark.parametrize("plan", [
    "issue: #9,", "issue: [#9](https://github.com/o/r/issues/9)", "issue: #9.", "issue: **#9**",
    "issue: <#9>", "issue: none\n\nFollows up #9.", "issue: none\n\nSee https://github.com/o/r/issues/9 first.",
], ids=["comma", "md-link", "period", "bold", "angle", "mention", "url-mention"])
def test_a_decorated_or_mentioned_issue_keeps_the_work_open(tmp_path, plan):
    """Refute round 3: decorated `issue:` tokens yielded no key, so the active
    plan did not protect its work. Any `#N` / `issues/N` mention keeps it."""
    tidy = _tidy_mod()
    root = _bare_reviews(tmp_path, {f"{_days_ago(90)}-a.md": "work: #9\n\nold\n",
                                    f"{_days_ago(80)}-b.md": "work: #9\n\nnew\n"},
                         _LINE.format(w="#9", v="pass", n=2), {f"{_days_ago(5)}-p.md": f"# P\n\n{plan}\n"})
    assert tidy.old_review_reports(root, 30) == []


def test_a_slug_mentioned_in_an_active_plan_keeps_the_work_open(tmp_path):
    """A whole-token slug mention in an active plan is enough to keep (fail-closed)."""
    tidy = _tidy_mod()
    root = _bare_reviews(tmp_path, {f"{_days_ago(90)}-a.md": "review: foo\n\nold\n",
                                    f"{_days_ago(80)}-b.md": "review: foo\n\nnew\n"},
                         _LINE.format(w="foo", v="pass", n=2), {f"{_days_ago(5)}-p.md": "# P\n\nreworks foo again\n"})
    assert tidy.old_review_reports(root, 30) == []


def test_issues_of_another_repository_are_separate_works(tmp_path):
    """Grouping follows report_of: `other/repo#9` is not this repo's #9, so
    each is its own work's newest report and both stay."""
    tidy = _tidy_mod()
    root = _bare_reviews(tmp_path, {f"{_days_ago(90)}-a.md": "work: other/repo#9\n\nold\n",
                                    f"{_days_ago(80)}-b.md": "work: #9\n\nnew\n"},
                         _LINE.format(w="#9", v="pass", n=2) + _LINE.format(w="other/repo#9", v="pass", n=2), {})
    assert tidy.old_review_reports(root, 30) == []


def test_a_report_whose_file_name_reaches_open_work_is_kept(tmp_path):
    """`9-x.md` headed `review: foo` (foo closed) is what report_of's name rule
    finds for open #9 — removing it would take #9's prior report."""
    tidy = _tidy_mod()
    root = _bare_reviews(tmp_path, {f"{_days_ago(90)}-9-x.md": "review: foo\n\nold\n",
                                    f"{_days_ago(80)}-b.md": "review: foo\n\nnew\n"},
                         _LINE.format(w="foo", v="pass", n=2), {f"{_days_ago(5)}-bar.md": "# P\n\nissue: 9\n"})
    assert tidy.old_review_reports(root, 30) == []


def test_untracked_or_locally_changed_reports_are_never_deleted(tmp_path):
    """Refute: the `git rm` fallback unlinked an untracked report and one with
    local edits — the only copies. Both are kept, named, and apply exits 1."""
    tidy = _tidy_mod()
    old, mid, new = _days_ago(90), _days_ago(85), _days_ago(80)
    root = _bare_reviews(tmp_path, {f"{old}-w.md": "work: #1\n\nold\n", f"{new}-w-r2.md": "work: #1\n\nnew\n"},
                         _LINE.format(w="#1", v="pass", n=2), {})
    (root / f".process-work/reviews/{mid}-w-r1b.md").write_text("work: #1\n\nUNTRACKED notes\n")
    (root / f".process-work/reviews/{old}-w.md").write_text("work: #1\n\nold + LOCAL EDIT\n")
    _lines, items = tidy.report(root, 30, with_remote=False, sizes=False)
    assert items["reviews"] == []
    assert set(items["reviews_skipped"]) == {f".process-work/reviews/{old}-w.md",
                                             f".process-work/reviews/{mid}-w-r1b.md"}
    assert tidy.apply(root, items, 30) == 1
    assert "LOCAL EDIT" in (root / f".process-work/reviews/{old}-w.md").read_text()
    assert "UNTRACKED" in (root / f".process-work/reviews/{mid}-w-r1b.md").read_text()
