"""news.py: user-readable change fragments under news/, rendered to NEWS.md.

A fragment's date is the day it reached the integration branch (first parents
of the remote's default branch), not the day it was written; a fragment not
yet there is "Unreleased" (docs/analysis/2026-10-13-knowledge-anchors-plan.md,
§4.5)."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


def _git(out: Path, *a: str, date: str | None = None) -> None:
    env = {k: v for k, v in os.environ.items() if k not in ("CI", "PRE_COMMIT_TO_REF")}
    if date:
        env["GIT_COMMITTER_DATE"] = env["GIT_AUTHOR_DATE"] = f"{date}T12:00:00+00:00"
    subprocess.run(["git", *a], cwd=out, check=True, capture_output=True, env=env)


def _commit(out: Path, msg: str, date: str) -> None:
    _git(out, "add", "-A")
    _git(out, "commit", "-qm", msg, date=date)


def _project(render, tmp_path: Path, *, remote: bool = True) -> Path:
    out = render(tmp_path / "p", {"project_name": "demo"})
    _git(out, "init", "-q", "-b", "main")
    _git(out, "config", "user.email", "t@t")
    _git(out, "config", "user.name", "t")
    _commit(out, "init", "2026-01-05")
    if remote:
        subprocess.run(["git", "init", "-q", "--bare", str(tmp_path / "origin.git")], check=True)
        _git(out, "remote", "add", "origin", str(tmp_path / "origin.git"))
        _git(out, "push", "-q", "-u", "origin", "main")
    return out


def _news(out: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(out / "scripts/process/news.py"), *args],
                          cwd=out, capture_output=True, text=True)


def _fragment(out: Path, slug: str, kind: str, text: str, issue: str | None = None) -> None:
    (out / "news").mkdir(exist_ok=True)
    head = f"type: {kind}\n" + (f"issue: #{issue}\n" if issue else "")
    (out / "news" / f"{slug}.md").write_text(f"{head}\n{text}\n", encoding="utf-8")


def _land(out: Path, date: str, msg: str = "land") -> None:
    """Commit on main at `date` and push: what is on origin/main is what the base says."""
    _commit(out, msg, date)
    _git(out, "push", "-q", "origin", "main")


def _render(out: Path) -> str:
    r = _news(out, "render")
    assert r.returncode == 0, r.stdout + r.stderr
    return (out / "NEWS.md").read_text(encoding="utf-8")


# --- new ----------------------------------------------------------------------

def test_new_writes_a_fragment_that_check_accepts(render, tmp_path):
    out = _project(render, tmp_path)
    r = _news(out, "new", "--type", "improved", "--slug", "faster-search", "--issue", "42",
              "Search answers in half the time.")
    assert r.returncode == 0, r.stdout + r.stderr
    assert (out / "news/faster-search.md").read_text(encoding="utf-8") == (
        "type: improved\nissue: #42\n\nSearch answers in half the time.\n")
    c = _news(out, "check")
    assert c.returncode == 0, c.stdout + c.stderr


def test_new_without_issue_has_no_issue_line(render, tmp_path):
    out = _project(render, tmp_path)
    assert _news(out, "new", "--type", "new", "--slug", "dark-mode", "A dark theme.").returncode == 0
    assert (out / "news/dark-mode.md").read_text(encoding="utf-8") == "type: new\n\nA dark theme.\n"


def test_new_refuses_an_existing_fragment(render, tmp_path):
    out = _project(render, tmp_path)
    _news(out, "new", "--type", "new", "--slug", "dark-mode", "A dark theme.")
    r = _news(out, "new", "--type", "fixed", "--slug", "dark-mode", "Something else.")
    assert r.returncode == 1
    assert "news/dark-mode.md exists already" in r.stderr
    assert "A dark theme." in (out / "news/dark-mode.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("args, fragment", [
    (["--slug", "Bad_Slug", "text"], "slug"),
    (["--slug", "../escape", "text"], "slug"),
    (["--slug", "ok", "   "], "no text"),
    (["--slug", "ok", "x" * 601], "601 characters"),
    (["--slug", "ok", "--issue", "abc", "text"], "--issue"),
])
def test_new_refuses_a_bad_request(render, tmp_path, args, fragment):
    out = _project(render, tmp_path)
    r = _news(out, "new", "--type", "new", *args)
    assert r.returncode == 1, r.stdout + r.stderr
    assert fragment in r.stderr
    assert not any((out / "news").glob("*")) if (out / "news").exists() else True


def test_new_accepts_exactly_600_characters(render, tmp_path):
    out = _project(render, tmp_path)
    assert _news(out, "new", "--type", "new", "--slug", "long", "x" * 600).returncode == 0


# --- check --------------------------------------------------------------------

@pytest.mark.parametrize("name, content, fragment", [
    ("no-header.md", "Just a sentence.\n", "first line must be `type:"),
    ("empty.md", "", "first line must be `type:"),
    ("bad-type.md", "type: shiny\n\nText.\n", "unknown type 'shiny'"),
    ("no-text.md", "type: new\nissue: #3\n\n\n", "no text"),
    ("too-long.md", "type: fixed\n\n" + "y" * 601 + "\n", "601 characters"),
    ("bad-issue.md", "type: new\nissue: 12\n\nText.\n", "`issue: #N`"),
    ("Bad_Name.md", "type: new\n\nText.\n", "<slug>.md"),
    ("notes.txt", "type: new\n\nText.\n", "<slug>.md"),
])
def test_check_names_each_malformed_fragment(render, tmp_path, name, content, fragment):
    out = _project(render, tmp_path)
    _fragment(out, "fine", "new", "A good one.")
    (out / "news" / name).write_text(content, encoding="utf-8")
    r = _news(out, "check")
    assert r.returncode == 1, r.stdout + r.stderr
    assert f"news/{name}: " in r.stdout and fragment in r.stdout
    assert "news/fine.md" not in r.stdout


def test_check_is_green_without_a_news_directory(render, tmp_path):
    out = _project(render, tmp_path)
    assert _news(out, "check").returncode == 0


def test_a_multiline_text_is_one_line_in_the_log(render, tmp_path):
    out = _project(render, tmp_path)
    (out / "news").mkdir()
    (out / "news/wrapped.md").write_text("type: new\n\nFirst sentence\nwraps here.  Second one.\n", encoding="utf-8")
    _land(out, "2026-10-02")
    assert "- 2026-10-02 — First sentence wraps here. Second one.\n" in _render(out)


# --- render -------------------------------------------------------------------

def test_render_groups_by_month_then_type_then_date_then_name(render, tmp_path):
    out = _project(render, tmp_path)
    for slug, kind, text, issue, day in [
        ("zeta-fix", "fixed", "Fixed Z.", None, "2026-09-03"),
        ("alpha-new", "new", "New A.", "7", "2026-09-10"),
        ("beta-new", "new", "New B.", None, "2026-09-10"),
        ("early-new", "new", "New early.", None, "2026-09-02"),
        ("oct-improved", "improved", "Better O.", "9", "2026-10-02"),
        ("oct-new", "new", "New O.", None, "2026-10-04"),
    ]:
        _fragment(out, slug, kind, text, issue)
        _land(out, day, slug)
    assert _render(out) == (
        "# News\n\n"
        "## 2026-10\n\n"
        "### New\n\n- 2026-10-04 — New O.\n\n"
        "### Improved\n\n- 2026-10-02 — Better O. (#9)\n\n"
        "## 2026-09\n\n"
        "### New\n\n- 2026-09-02 — New early.\n- 2026-09-10 — New A. (#7)\n- 2026-09-10 — New B.\n\n"
        "### Fixed\n\n- 2026-09-03 — Fixed Z.\n")


def test_render_is_deterministic_whatever_the_creation_order(render, tmp_path):
    first = _project(render, tmp_path / "one")
    second = _project(render, tmp_path / "two")
    rows = [("b-fix", "fixed", "Fix."), ("a-new", "new", "New."), ("c-imp", "improved", "Better.")]
    for slug, kind, text in rows:
        _fragment(first, slug, kind, text)
    for slug, kind, text in reversed(rows):
        _fragment(second, slug, kind, text)
    one = _render(first)
    assert _render(first) == one == _render(second)  # same bytes twice, and from another creation order


def test_a_fragment_not_yet_on_the_integration_branch_is_unreleased(render, tmp_path):
    out = _project(render, tmp_path)
    _fragment(out, "landed", "new", "Already shipped.")
    _land(out, "2026-10-02")
    _git(out, "switch", "-qc", "topic")
    _fragment(out, "in-flight", "fixed", "Not merged yet.")
    _commit(out, "work", "2026-10-05")
    assert _render(out) == (
        "# News\n\n"
        "## Unreleased\n\n### Fixed\n\n- Not merged yet.\n\n"
        "## 2026-10\n\n### New\n\n- 2026-10-02 — Already shipped.\n")


def test_a_fragment_from_a_long_lived_branch_takes_the_month_of_the_merge(render, tmp_path):
    out = _project(render, tmp_path)
    _git(out, "switch", "-qc", "long-lived")
    _fragment(out, "old-work", "improved", "Written in August.")
    _commit(out, "feature", "2026-08-20")
    _git(out, "switch", "-q", "main")
    (out / "other.txt").write_text("x\n", encoding="utf-8")
    _land(out, "2026-10-05", "main moves on")
    _git(out, "merge", "--no-ff", "-qm", "merge long-lived", "long-lived", date="2026-10-07")
    _git(out, "push", "-q", "origin", "main")
    text = _render(out)
    assert "## 2026-10" in text and "2026-10-07 — Written in August." in text
    assert "2026-08" not in text


def test_a_removed_and_readded_fragment_keeps_its_first_date(render, tmp_path):
    out = _project(render, tmp_path)
    _fragment(out, "again", "new", "Text.")
    _land(out, "2026-09-01")
    (out / "news/again.md").unlink()
    _land(out, "2026-09-15", "remove")
    _fragment(out, "again", "new", "Text.")
    _land(out, "2026-10-15", "re-add")
    assert "- 2026-09-01 — Text." in _render(out)


def test_without_an_integration_branch_everything_is_unreleased_and_says_so(render, tmp_path):
    out = _project(render, tmp_path, remote=False)
    _fragment(out, "solo", "new", "Local only.")
    _commit(out, "add", "2026-10-02")
    r = _news(out, "render")
    assert r.returncode == 0, r.stderr
    assert "no integration branch" in r.stderr
    assert (out / "NEWS.md").read_text(encoding="utf-8") == "# News\n\n## Unreleased\n\n### New\n\n- Local only.\n"


def test_render_aborts_on_a_malformed_fragment_naming_it_and_writes_nothing(render, tmp_path):
    out = _project(render, tmp_path)
    _fragment(out, "fine", "new", "Good.")
    (out / "news/broken.md").write_text("type: shiny\n\nText.\n", encoding="utf-8")
    r = _news(out, "render")
    assert r.returncode == 1
    assert "news/broken.md" in r.stderr
    assert not (out / "NEWS.md").exists()


def test_render_aborts_without_overwriting_an_existing_news_file(render, tmp_path):
    out = _project(render, tmp_path)
    (out / "NEWS.md").write_text("old\n", encoding="utf-8")
    _fragment(out, "bad", "new", "")
    assert _news(out, "render").returncode == 1
    assert (out / "NEWS.md").read_text(encoding="utf-8") == "old\n"


def test_an_empty_or_missing_news_directory_renders_a_valid_file(render, tmp_path):
    out = _project(render, tmp_path)
    assert _render(out) == "# News\n"  # no news/ at all
    (out / "news").mkdir()
    (out / "news/.gitkeep").write_text("", encoding="utf-8")
    assert _render(out) == "# News\n"


# --- configuration ---------------------------------------------------------------

def _config(out: Path, data) -> None:
    (out / "docs/process/news.local.json").write_text(
        data if isinstance(data, str) else json.dumps(data), encoding="utf-8")


def test_own_title_labels_and_unreleased_heading(render, tmp_path):
    out = _project(render, tmp_path)
    _config(out, {"title": "Neuigkeiten", "unreleased": "Unveröffentlicht",
                  "labels": {"new": "Neu", "improved": "Verbessert", "fixed": "Behoben"}})
    for slug, kind in (("a", "new"), ("b", "improved"), ("c", "fixed")):
        _fragment(out, slug, kind, f"Text {slug}.")
    _land(out, "2026-10-02")
    _git(out, "switch", "-qc", "topic")
    _fragment(out, "d", "new", "Noch offen.")
    assert _render(out) == (
        "# Neuigkeiten\n\n## Unveröffentlicht\n\n### Neu\n\n- Noch offen.\n\n"
        "## 2026-10\n\n### Neu\n\n- 2026-10-02 — Text a.\n\n"
        "### Verbessert\n\n- 2026-10-02 — Text b.\n\n### Behoben\n\n- 2026-10-02 — Text c.\n")
    shown = _news(out, "show").stdout
    assert shown.splitlines()[0] == "Unveröffentlicht  Neu  Noch offen."


def test_a_partial_config_keeps_the_other_defaults(render, tmp_path):
    out = _project(render, tmp_path)
    _config(out, {"labels": {"fixed": "Repaired"}})
    _fragment(out, "a", "fixed", "Done.")
    _land(out, "2026-10-02")
    assert _render(out).startswith("# News\n\n## 2026-10\n\n### Repaired\n")


@pytest.mark.parametrize("config", [
    "{not json", "[]", '{"title": ""}', '{"title": 3}', '{"labels": []}', '{"labels": {"new": 1}}',
    '{"labels": {"shiny": "x"}}', '{"unreleased": ""}', '{"titel": "typo"}',
])
def test_a_malformed_config_is_an_error_naming_the_file(render, tmp_path, config):
    out = _project(render, tmp_path)
    _config(out, config)
    for cmd in ("render", "show", "check"):
        r = _news(out, cmd)
        assert r.returncode == 1, (cmd, r.stdout, r.stderr)
        assert "docs/process/news.local.json" in r.stderr
    assert not (out / "NEWS.md").exists()


# --- show -----------------------------------------------------------------------

def test_show_lists_newest_first_and_since_filters_by_integration_date(render, tmp_path):
    out = _project(render, tmp_path)
    for slug, kind, text, day in [
        ("old", "new", "Old thing.", "2026-08-01"),
        ("mid-fix", "fixed", "Mid fix.", "2026-09-15"),
        ("mid-new", "new", "Mid new.", "2026-09-15"),
        ("recent", "improved", "Recent.", "2026-10-10"),
    ]:
        _fragment(out, slug, kind, text, "5" if slug == "recent" else None)
        _land(out, day, slug)
    _git(out, "switch", "-qc", "topic")
    _fragment(out, "pending", "fixed", "Pending.")
    assert _news(out, "show").stdout.splitlines() == [
        "Unreleased  Fixed  Pending.",
        "2026-10-10  Improved  Recent. (#5)",
        "2026-09-15  New  Mid new.",
        "2026-09-15  Fixed  Mid fix.",
        "2026-08-01  New  Old thing.",
    ]
    since = _news(out, "show", "--since", "2026-09-15").stdout.splitlines()
    assert since == ["Unreleased  Fixed  Pending.", "2026-10-10  Improved  Recent. (#5)",
                     "2026-09-15  New  Mid new.", "2026-09-15  Fixed  Mid fix."]
    assert _news(out, "show", "--since", "2026-10-11").stdout.splitlines() == ["Unreleased  Fixed  Pending."]


def test_show_uses_the_merge_date_for_a_long_lived_branch(render, tmp_path):
    out = _project(render, tmp_path)
    _git(out, "switch", "-qc", "long-lived")
    _fragment(out, "old-work", "new", "Written early.")
    _commit(out, "feature", "2026-08-20")
    _git(out, "switch", "-q", "main")
    _git(out, "merge", "--no-ff", "-qm", "merge", "long-lived", date="2026-10-07")
    _git(out, "push", "-q", "origin", "main")
    assert _news(out, "show", "--since", "2026-10-01").stdout.splitlines() == ["2026-10-07  New  Written early."]


def test_show_rejects_a_bad_date_and_a_malformed_fragment(render, tmp_path):
    out = _project(render, tmp_path)
    r = _news(out, "show", "--since", "yesterday")
    assert r.returncode == 1 and "--since" in r.stderr
    (out / "news").mkdir()
    (out / "news/broken.md").write_text("nothing\n", encoding="utf-8")
    r = _news(out, "show")
    assert r.returncode == 1 and "news/broken.md" in r.stderr


def test_show_without_news_prints_nothing(render, tmp_path):
    out = _project(render, tmp_path)
    r = _news(out, "show")
    assert r.returncode == 0 and r.stdout == ""
