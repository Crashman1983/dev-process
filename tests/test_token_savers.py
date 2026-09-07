"""v2.9.0: measure the context, fold old journals, update without re-porting
— three scripts that trade a few seconds of compute for agent tokens."""
import datetime as dt
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # _load() must not dirty the rendered tree

JOURNAL = ".process-work/journal"


def _py(root, script, *args):
    return subprocess.run([sys.executable, str(root / "scripts/process" / script),
                           *args, "."], cwd=root, capture_output=True, text=True)


def _git(root, *args):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                          check=True)


def _load(root: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, root / "scripts/process" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --- context cost -------------------------------------------------------------

def test_context_cost_is_opt_in_and_names_the_largest_files(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    plain = json.loads(_py(out, "process_context.py").stdout)
    assert "context_cost" not in plain  # the default JSON stays lean
    r = _py(out, "process_context.py", "--cost")
    assert r.returncode == 0, r.stdout + r.stderr
    cost = json.loads(r.stdout)["context_cost"]
    assert cost["anchor"]["files"] == 1 and cost["anchor"]["tokens"] > 100
    assert cost["process_docs"]["files"] > 10
    assert cost["session_start_estimate_tokens"] > cost["anchor"]["tokens"]
    assert cost["largest"] and "tokens" in cost["largest"][0]
    assert "chars / 4" in cost["unit"]


# --- journal compaction -------------------------------------------------------

def _shard(root, rel, *lines):
    p = root / JOURNAL / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def test_compact_folds_old_shards_keeps_records_and_gates_still_clear(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    old = (dt.date.today() - dt.timedelta(weeks=20)).isoformat()
    _shard(out, f"{old}.md", "# Day", "long reasoning " * 50,
           "- REVIEW work=42 tier=2 reviewer=fresh model=same "
           "independence=bundle,non-implementing verdict=pass round=1",
           "```", "REVIEW work=99 tier=2 reviewer=x model=y independence=bundle "
           "verdict=pass round=1", "```")
    _shard(out, f"feat-x/{old}.md", "GRADE work=42 checkpoint=plan criterion=c "
                                    "score=3 round=1 source=agent")
    recent = dt.date.today().isoformat()
    _shard(out, f"{recent}.md", "# Today", "fresh reasoning")
    adir = out / ".process-work/plans/archive"
    adir.mkdir(parents=True, exist_ok=True)
    (adir / "2026-05-01-widget.md").write_text("# Plan\n\ntier: 2\nissue: #42\n")
    dry = _py(out, "compact_journal.py")
    assert dry.returncode == 0 and "would save" in dry.stdout
    assert (out / JOURNAL / f"{old}.md").is_file()  # dry run touches nothing
    ap = _py(out, "compact_journal.py", "--apply")
    assert ap.returncode == 0, ap.stdout + ap.stderr
    assert not (out / JOURNAL / f"{old}.md").exists()
    assert not (out / JOURNAL / "feat-x").exists()  # emptied shard dir removed
    assert (out / JOURNAL / f"{recent}.md").is_file()  # recent shard untouched
    month = old[:7]
    archive = (out / JOURNAL / "archive" / f"{month}.md").read_text(encoding="utf-8")
    assert "REVIEW work=42" in archive and "GRADE work=42" in archive
    assert "work=99" not in archive  # fenced quotation dropped with the prose
    assert "long reasoning" not in archive
    # the gate still clears the archived plan from the folded record
    gate = subprocess.run([sys.executable, str(out / "scripts/process/check_review.py"), "."],
                          cwd=out, capture_output=True, text=True)
    assert gate.returncode == 0, gate.stdout
    # idempotent: nothing left to fold
    again = _py(out, "compact_journal.py")
    assert "nothing older" in again.stdout


def test_compact_leaves_undated_and_recent_shards(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    _shard(out, "notes.md", "undated")
    r = _py(out, "compact_journal.py", "--apply")
    assert r.returncode == 0 and "nothing older" in r.stdout
    assert (out / JOURNAL / "notes.md").is_file()


# --- template update with an owner list --------------------------------------

def test_owned_patterns_and_delta_writing(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    (out / ".process-owned").write_text(
        "# what this project owns\nscripts/process/check_review.py\n"
        ".claude/commands/*.md\n", encoding="utf-8")
    tu = _load(out, "template_update")
    owned = tu.owned_patterns(out)
    assert tu.is_owned("scripts/process/check_review.py", owned)
    assert tu.is_owned(".claude/commands/review.md", owned)
    assert not tu.is_owned("scripts/process/finish.py", owned)
    old, new = tmp_path / "old", tmp_path / "new"
    for d in (old, new):
        (d / "scripts/process").mkdir(parents=True)
        (d / "docs").mkdir()
        (d / "docs/other.md").write_text("same\n")
    (old / "scripts/process/check_review.py").write_text("a = 1\n")
    (new / "scripts/process/check_review.py").write_text("a = 2\n")
    delta_dir = out / ".process-work/template-delta/v9"
    changed = tu.write_deltas(old, new, owned, delta_dir, out)
    assert changed == ["scripts/process/check_review.py"]
    diff = (delta_dir / "scripts/process/check_review.py.diff").read_text()
    assert "-a = 1" in diff and "+a = 2" in diff
    assert not (delta_dir / "docs/other.md.diff").exists()


def test_answers_strip_underscore_keys_and_restore_owned(render, tmp_path):
    out = render(tmp_path, {"project_name": "d"})
    _git(out, "init", "-q", "-b", "main")
    _git(out, "config", "user.email", "t@example.com")
    _git(out, "config", "user.name", "Test")
    (out / ".copier-answers.yml").write_text(
        "_commit: v1.0.0\n_src_path: https://example.invalid/t.git\n"
        "project_name: d\nmodules: {speckit: true}\n", encoding="utf-8")
    (out / ".process-owned").write_text("scripts/process/finish.py\n")
    _git(out, "add", "-A")
    _git(out, "commit", "-q", "-m", "base")
    tu = _load(out, "template_update")
    src, commit, data = tu.answers(out)
    assert src == "https://example.invalid/t.git" and commit == "v1.0.0"
    assert "_commit" not in data and data["project_name"] == "d"
    assert "speckit: true" in data["modules"]  # re-asserted as --data on update
    # a template overwrite of an owned file is put back to HEAD
    (out / "scripts/process/finish.py").write_text("overwritten\n")
    restored = tu.restore_owned(out, tu.owned_patterns(out))
    assert restored == ["scripts/process/finish.py"]
    assert "overwritten" not in (out / "scripts/process/finish.py").read_text()
    r = _py(out, "template_update.py", "--dry-run")
    assert r.returncode == 0 and "1 owned pattern" in r.stdout
