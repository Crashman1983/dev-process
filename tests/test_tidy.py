"""SP68: residue has one owner — tidy.py reports it and removes the safe part."""
import datetime as dt
import subprocess
import sys


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
    for name in ("clean", "cache", "untracked", "dirty", "locked", "live", "env", "excl", "outer", "open", "fresh"):
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
    for rel in ("__pycache__/m.cpython-312.pyc", "build/out.bin", "node_modules/x/index.js", "src/__pycache__/n.pyc"):
        (wts["cache"] / rel).parent.mkdir(parents=True, exist_ok=True)
        (wts["cache"] / rel).write_text("regenerable\n")
    (wts["env"] / ".env").write_text("SECRET=1\n")
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
    assert str(wts["open"]) not in r.stdout and "work-detached" not in r.stdout  # not merged / no branch's
    assert wts["clean"].is_dir()  # a dry run removes nothing

    r = _run(out, "--apply")
    assert r.returncode == 0, r.stdout + r.stderr
    assert not wts["clean"].exists() and not wts["cache"].exists()
    listed = _git(out, "worktree", "list").stdout
    assert str(wts["clean"]) not in listed
    for name in ("untracked", "dirty", "locked", "live", "env", "excl", "outer", "nested", "open", "fresh"):
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
