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
