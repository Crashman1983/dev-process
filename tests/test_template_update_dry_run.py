"""template_update.py --dry-run names what a project must do (v2.96 A5, #415 AC-2): the
`[required]` items of every release between the installed one and the target, and the
overlays whose anchored template section changed — read from a clone of the template
source, before anything is written."""
import datetime
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "template/scripts/process/template_update.py"
CLAUDE_DIR = "{% if harnesses.claude %}.claude{% endif %}"

TESTING_OLD = "# Testing\n\n## Stages\n\nold stages\n\n## Lanes\n\nlanes\n\n## Retired\n\nsoon gone\n"
TESTING_NEW = "# Testing\n\n## Stages\n\nnew stages\n\n## Lanes\n\nlanes\n"
PLAN_OLD = "# Plan\n\n## Steps\n\n{% if modules.speckit %}spec{% endif %} old steps\n"
PLAN_NEW = "# Plan\n\n## Steps\n\n{% if modules.speckit %}spec{% endif %} new steps\n"

CHANGELOG_OLD = "# Changelog\n\n**v2.93.0 — Oldest.** Initial.\n"
CHANGELOG_NEW = """# Changelog

## v2.96.0 — Marks · 2026-11-14

**What changes.**
- [required] Fix the gate that blocks every push.
  - a detail
- [recommended] Better output.
- [optional] A new flag.

## v2.95.0 — Plain · 2026-11-11

**What changes.**
- Something.

**v2.94.0 — Bold.** Old form.
- Punkt

**v2.93.0 — Oldest.** Initial.
"""


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout.strip()


def write(root: Path, rel: str, body: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")


def init(root: Path) -> None:
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.name", "Test")
    git(root, "config", "user.email", "t@example.com")


def commit(root: Path) -> None:
    git(root, "add", "-A")
    git(root, "commit", "-qm", "fixture")


@pytest.fixture
def repos(tmp_path):
    """A template source tagged v2.93.0 and v2.96.0, and a project installed at v2.93.0
    with a doc overlay and a command overlay."""
    source, project = tmp_path / "source", tmp_path / "project"
    init(source)
    write(source, "copier.yml", "_subdirectory: template\nproject_name:\n  default: demo\n")
    write(source, "template/docs/process/testing.md", TESTING_OLD)
    write(source, f"template/{CLAUDE_DIR}/commands/plan.md.jinja", PLAN_OLD)
    write(source, "CHANGELOG.md", CHANGELOG_OLD)
    commit(source)
    git(source, "tag", "v2.93.0")
    write(source, "template/docs/process/testing.md", TESTING_NEW)
    write(source, f"template/{CLAUDE_DIR}/commands/plan.md.jinja", PLAN_NEW)
    write(source, "CHANGELOG.md", CHANGELOG_NEW)
    commit(source)
    git(source, "tag", "v2.96.0")
    init(project)
    write(project, ".copier-answers.yml", f"_commit: v2.93.0\n_src_path: {source}\nproject_name: demo\n")
    write(project, "docs/process/testing.local.md",
          'overlay-of: docs/process/testing.md\nextends: "## Stages" @new\nextends: "## Lanes" @new\n'
          'replaces: "## Retired" @new\n\n## Ours\n\nnotes\n')
    write(project, "docs/process/commands/plan.local.md",
          'overlay-of: .claude/commands/plan.md\nextends: "## Steps" @new\n\n## Ours\n\nnotes\n')
    write(project, "docs/process/notes.local.md", "# Just notes, no overlay\n")
    commit(project)
    return source, project


def dry(project: Path, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    return subprocess.run([sys.executable, str(SCRIPT), str(project), "--dry-run", *args],
                          capture_output=True, text=True, env=env, timeout=300)


def test_dry_run_names_the_required_items_and_the_overlays_to_re_check(repos):
    _, project = repos
    r = dry(project)
    out = r.stdout
    assert r.returncode == 0, r.stdout + r.stderr
    assert "v2.93.0 to v2.96.0" in out, out
    assert "[required] Fix the gate that blocks every push." in out
    assert "a detail" not in out and "Better output." not in out  # only required items are spelled out
    marks = next(ln for ln in out.splitlines() if "v2.96.0 — Marks" in ln)
    assert "1 required" in marks and "1 recommended" in marks and "1 optional" in marks, marks
    for version in ("v2.95.0 — Plain", "v2.94.0 — Bold"):
        line = next(ln for ln in out.splitlines() if version in ln)
        assert "not marked (before v2.96)" in line, line
    assert "v2.93.0 — Oldest" not in out  # the installed release is no change
    assert "docs/process/testing.local.md: ## Stages — changed" in out
    assert "docs/process/testing.local.md: ## Retired — gone" in out
    assert "## Lanes" not in out  # an unchanged anchored section needs no re-check
    assert "docs/process/commands/plan.local.md: ## Steps — changed" in out  # .md.jinja behind {% if %}
    assert "notes.local.md" not in out
    assert git(project, "status", "--porcelain") == ""  # nothing written


def test_an_explicit_target_bounds_the_range(repos):
    source, project = repos
    write(source, "CHANGELOG.md", "# Changelog\n\n## v2.97.0 — Later · 2026-11-20\n\n**What changes.**\n"
                                  "- [required] Not yet asked for.\n\n" + CHANGELOG_NEW.split("\n", 2)[2])
    commit(source)
    git(source, "tag", "v2.97.0")
    r = dry(project, "--ref", "v2.96.0")
    assert r.returncode == 0, r.stderr
    assert "Fix the gate" in r.stdout and "Not yet asked for." not in r.stdout
    r = dry(project)  # the default target is the highest release tag
    assert "Not yet asked for." in r.stdout and "v2.93.0 to v2.97.0" in r.stdout


def test_a_target_unmarked_entry_above_v2_96_is_not_marked_without_the_excuse(repos):
    source, project = repos
    write(source, "CHANGELOG.md", "# Changelog\n\n## v2.97.0 — Bare · 2026-11-20\n\nNo parts.\n\n"
          + CHANGELOG_NEW.split("\n", 2)[2])
    commit(source)
    git(source, "tag", "v2.97.0")
    line = next(ln for ln in dry(project).stdout.splitlines() if "v2.97.0 — Bare" in ln)
    assert line.rstrip().endswith("not marked"), line


def test_an_installed_post_release_is_no_release(repos):
    _, project = repos
    answers = project / ".copier-answers.yml"
    answers.write_text(answers.read_text().replace("v2.93.0", "v2.93.0.post1"))
    commit(project)
    r = dry(project, "--ref", "v2.96.0")
    assert r.returncode == 0, r.stderr
    assert "release notes unreadable: v2.93.0.post1 is no release" in r.stdout, r.stdout
    assert "[required]" not in r.stdout and "re-check" not in r.stdout
    r = dry(project)  # without --ref the old guard speaks, as before
    assert r.returncode == 2 and "commit past the last release" in r.stderr


def test_a_target_that_is_no_release_is_said_so(repos):
    _, project = repos
    r = dry(project, "--ref", "HEAD")
    assert r.returncode == 0 and "release notes unreadable: HEAD is no release" in r.stdout, r.stdout


def test_offline_is_one_line_and_exit_zero(repos):
    source, project = repos
    source.rename(source.with_name("gone"))
    r = dry(project)
    assert r.returncode == 0, r.stderr
    said = [ln for ln in r.stdout.splitlines() if "unreadable" in ln or "re-check" in ln or "[required]" in ln]
    assert len(said) == 1 and "unreachable" in said[0] and "fails closed" not in said[0], r.stdout


# --- v2.97 B6 (#415 AC-3/4): the last update and the cadence -----------------------------

CHANGELOG_LATER = ("# Changelog\n\n## v2.97.0 — Later · 2026-11-20\n\n**What changes.**\n"
                   "- [recommended] Nicer output.\n- [optional] Another flag.\n\n"
                   + CHANGELOG_NEW.split("\n", 2)[2])
TODAY = datetime.date.today()
NOW = datetime.datetime.now()


def commit_at(root: Path, when: datetime.datetime) -> None:
    git(root, "add", "-A")
    stamp = when.strftime("%Y-%m-%dT%H:%M:%S")
    env = dict(os.environ, GIT_AUTHOR_DATE=stamp, GIT_COMMITTER_DATE=stamp)
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=root, check=True, capture_output=True, env=env)


def mandate(project: Path, steering: dict | None) -> None:
    write(project, "docs/process/optimization.local.json",
          json.dumps({} if steering is None else {"steering": steering}))
    commit(project)


def install(project: Path, version: str, when: datetime.datetime) -> None:
    answers = project / ".copier-answers.yml"
    answers.write_text(re.sub(r"_commit: \S+", f"_commit: {version}", answers.read_text()))
    commit_at(project, when)


def later_release(source: Path) -> None:
    """v2.97.0 above v2.96.0, nothing `[required]` in it."""
    write(source, "CHANGELOG.md", CHANGELOG_LATER)
    commit(source)
    git(source, "tag", "v2.97.0")


def cadence_line(out: str) -> str:
    return next(ln for ln in out.splitlines() if "cadence" in ln)


def test_the_dry_run_names_the_last_update_and_no_cadence_without_one(repos):
    _, project = repos
    install(project, "v2.94.0", NOW - datetime.timedelta(days=40))
    install(project, "v2.93.0", NOW - datetime.timedelta(days=10))  # the last change of _commit
    answers = project / ".copier-answers.yml"
    answers.write_text(answers.read_text().replace("project_name: demo", "project_name: other"))
    commit(project)  # another answer changed today: no update
    r = dry(project)
    assert r.returncode == 0, r.stderr
    last = (TODAY - datetime.timedelta(days=10)).isoformat()
    assert f"template-update: last update {last}" in r.stdout, r.stdout
    assert "cadence" not in r.stdout and "defer" not in r.stdout and "due" not in r.stdout
    mandate(project, None)  # a mandate without the key: still no cadence
    assert "cadence" not in dry(project).stdout


def test_a_pending_required_change_is_due_now_whatever_the_cadence(repos):
    _, project = repos
    mandate(project, {"kit_update_cadence_days": 14})
    r = dry(project)  # installed today; v2.96.0 carries a [required] item
    assert r.returncode == 0, r.stderr
    line = cadence_line(r.stdout)
    assert "due now" in line and "[required]" in line, line


def test_without_a_required_change_the_cadence_defers_until_due(repos):
    source, project = repos
    later_release(source)
    install(project, "v2.96.0", NOW - datetime.timedelta(days=3))
    mandate(project, {"kit_update_cadence_days": 14})
    r = dry(project)
    assert r.returncode == 0, r.stderr
    assert "v2.96.0 to v2.97.0" in r.stdout and "[required]" not in r.stdout, r.stdout
    until = (TODAY - datetime.timedelta(days=3) + datetime.timedelta(days=14)).isoformat()
    line = cadence_line(r.stdout)
    assert f"defer until {until}: no required change pending" in line, line
    assert "due" not in line


def test_past_the_cadence_the_update_is_due(repos):
    source, project = repos
    later_release(source)
    install(project, "v2.96.0", NOW - datetime.timedelta(days=20))
    mandate(project, {"kit_update_cadence_days": 14})
    r = dry(project)
    line = cadence_line(r.stdout)
    assert "— due" in line and "due now" not in line and "defer" not in line, line
    assert f"last update {(TODAY - datetime.timedelta(days=20)).isoformat()}" in r.stdout, r.stdout


def test_a_wrong_cadence_is_named_and_judges_nothing(repos):
    _, project = repos
    for bad in ("14", True, 0, 2.5):
        mandate(project, {"kit_update_cadence_days": bad})
        r = dry(project)
        assert r.returncode == 0, r.stderr
        assert "kit_update_cadence_days must be a positive integer — ignored" in r.stdout, (bad, r.stdout)
        assert "due" not in r.stdout and "defer" not in r.stdout, bad


def test_unreadable_notes_never_say_no_required_change(repos):
    source, project = repos
    install(project, "v2.94.0", NOW - datetime.timedelta(days=3))
    mandate(project, {"kit_update_cadence_days": 14})
    source.rename(source.with_name("gone"))
    r = dry(project)
    assert r.returncode == 0, r.stderr
    line = cadence_line(r.stdout)
    assert "defer until" in line and "no required change pending" not in line, line
    assert "may be pending" in line, line
