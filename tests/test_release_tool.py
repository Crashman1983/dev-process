"""tools/release.py — the local release ritual in one run (#123)."""
import importlib.util
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def _load():
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("release_tool", REPO / "tools/release.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rel = _load()
CURRENT = re.search(r'^version = "(.+)"$', (REPO / "pyproject.toml").read_text(), re.M).group(1)


def test_every_place_the_repository_names_its_version_is_a_location():
    """A new location cannot be forgotten: the current version, anywhere in a tracked
    file outside the history and the generated SBOM, must be one of LOCATIONS.
    The overviews name the version they were last checked against — a review stamp,
    not a release location: bumped by the release, it would claim a check nobody did."""
    out = subprocess.run(["git", "grep", "-n", "-F", CURRENT, "--", ".",
                          ":!CHANGELOG.md", ":!CHANGELOG-DE.md", ":!docs/changelog-archive.md", ":!docs/changelog-archive-DE.md", ":!docs/sbom.cdx.json", ":!docs/SBOM.md", ":!tests/",
                          ":!docs/OVERVIEW.md", ":!docs/UEBERBLICK.md", ":!NEWS.md", ":!NEWS-DE.md", ":!docs/analysis/"],
                         cwd=REPO, capture_output=True, text=True).stdout
    files = {line.split(":", 1)[0] for line in out.splitlines()}
    assert files == {path for path, _ in rel.LOCATIONS}, files


def test_check_is_clean_at_the_current_version():
    assert rel.mismatches(REPO, CURRENT) == []


NEWS_999 = "# News\n\n## v9.9.9 — t\n\nWhat changes, in plain words.\n"


def _changelogs(root: Path, body: str = "body\n", sections: bool = False) -> None:
    """Both languages of the v9.9.9 entry (MAINTAINING.md: `## vX.Y.Z — <title> · <date>`)."""
    for name, marker in (("CHANGELOG.md", "Changed sections"), ("CHANGELOG-DE.md", "Geänderte Abschnitte")):
        tail = f"\n**{marker}.** `x.md` B, C (gone).\n" if sections else ""
        (root / name).write_text(f"## v9.9.9 — t · 2026-10-15\n\n{body}{tail}", encoding="utf-8")


def _copy(tmp_path: Path) -> Path:
    for path, _ in rel.LOCATIONS:
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REPO / path, tmp_path / path)
    for name in ("NEWS.md", "NEWS-DE.md"):
        (tmp_path / name).write_text(NEWS_999, encoding="utf-8")
    return tmp_path


def test_check_names_every_location_off_the_version(tmp_path):
    root = _copy(tmp_path)

    left = rel.mismatches(root, "9.9.9")

    assert [line.split(":", 1)[0] for line in left] == [path for path, _ in rel.LOCATIONS]


def test_bump_moves_every_location_and_nothing_else(tmp_path):
    root = _copy(tmp_path)
    before = {path: (root / path).read_text() for path, _ in rel.LOCATIONS}

    rel.bump(root, "9.9.9")

    assert rel.mismatches(root, "9.9.9") == []
    for path, text in before.items():
        after = (root / path).read_text()
        assert after.replace("9.9.9", CURRENT) == text, path


def test_release_refuses_without_a_changelog_entry(tmp_path):
    root = _copy(tmp_path)
    (root / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")

    with pytest.raises(SystemExit, match="no entry for v9.9.9"):
        rel.release(root, "v9.9.9")
    assert rel.mismatches(root, CURRENT) == []  # nothing bumped


@pytest.mark.parametrize("tag", ["2.38.0", "v2.38", "v2.38.0-rc1"])
def test_release_refuses_what_is_no_version(tmp_path, tag):
    with pytest.raises(SystemExit, match="no version"):
        rel.release(_copy(tmp_path), tag)


def test_a_failing_step_stops_before_the_commit(tmp_path, monkeypatch):
    root = _copy(tmp_path)
    _changelogs(root)
    calls = []

    def fake_run(argv, **kw):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 1 if "ruff" in argv else 0, stdout="", stderr="")

    monkeypatch.setattr(rel.subprocess, "run", fake_run)

    with pytest.raises(SystemExit, match="lint failed"):
        rel.release(root, "v9.9.9")
    assert not any("commit" in argv for argv in calls), calls


@pytest.mark.parametrize("xdist", [True, False])
def test_suite_runs_on_four_workers_only_with_xdist(tmp_path, monkeypatch, xdist):
    """serial the suite took ~5 min; loadfile because the render caches are per worker"""
    root = _copy(tmp_path)
    _changelogs(root)
    calls = []

    def fake_run(argv, **kw):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(rel.subprocess, "run", fake_run)
    monkeypatch.setattr(rel.importlib.util, "find_spec", lambda name: object() if xdist else None)
    rel.release(root, "v9.9.9")
    suite = next(argv for argv in calls if "pytest" in argv)
    assert (list(suite[-4:]) == ["-n", "4", "--dist", "loadfile"]) is xdist
    assert ("-n" in suite) is xdist


def test_cli_check_reports_ok_at_the_current_version():
    r = subprocess.run([sys.executable, str(REPO / "tools/release.py"), f"v{CURRENT}", "--check"],
                       capture_output=True, text=True)
    assert r.returncode == 0 and "release: OK" in r.stdout, r.stdout + r.stderr


# --- refute ---


def _git_repo(tmp_path: Path) -> Path:
    root = _copy(tmp_path)
    _changelogs(root)
    for args in (["init", "-q", "-b", "main"], ["config", "user.email", "t@t"],
                 ["config", "user.name", "t"], ["add", "-A"], ["commit", "-q", "-m", "base"]):
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)
    return root


def test_release_refuses_a_dirty_tree(tmp_path):
    """F6: a staged file rode along into the release commit."""
    root = _git_repo(tmp_path)
    (root / "WIP.txt").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "add", "WIP.txt"], cwd=root, check=True)

    with pytest.raises(SystemExit, match="not clean"):
        rel.release(root, "v9.9.9", suite=False)
    assert rel.mismatches(root, CURRENT) == []


def test_release_refuses_a_version_not_above_the_current_one(tmp_path):
    root = _git_repo(tmp_path)

    with pytest.raises(SystemExit, match="not above"):
        rel.release(root, "v0.0.1", suite=False)


def test_cli_refuses_an_unknown_flag():
    """F6: `--chek` ran a full release."""
    r = subprocess.run([sys.executable, str(REPO / "tools/release.py"), "v9.9.9", "--chek"],
                       capture_output=True, text=True)
    assert r.returncode == 2 and "unrecognized" in r.stderr, r.stderr


def test_check_reports_a_stale_sbom(monkeypatch):
    """F7: `--check` said OK while the SBOM still named the old version."""
    calls = []
    monkeypatch.setattr(rel.subprocess, "run",
                        lambda argv, **kw: calls.append(argv) or subprocess.CompletedProcess(argv, 1))

    assert "docs/sbom.cdx.json / docs/SBOM.md: stale (tools/gen_sbom.py --check)" in rel.check(REPO, f"v{CURRENT}")
    assert any("gen_sbom.py" in " ".join(map(str, a)) and "--check" in a for a in calls), calls


def test_a_rerun_after_a_failed_step_is_not_refused_as_a_downgrade(tmp_path, monkeypatch):
    """G2: the failed run left the files bumped; the version guard read the bump as current."""
    root = _git_repo(tmp_path)
    real = subprocess.run
    monkeypatch.setattr(rel.subprocess, "run", lambda argv, **kw: real(argv, **kw) if argv[0] == "git"
                        else subprocess.CompletedProcess(argv, 1 if "ruff" in argv else 0, stdout="", stderr=""))
    with pytest.raises(SystemExit, match="lint failed"):
        rel.release(root, "v9.9.9", suite=False)

    with pytest.raises(SystemExit, match="lint failed"):  # the same step fails again — no downgrade refusal
        rel.release(root, "v9.9.9", suite=False)


def test_the_remote_steps_wait_for_ci_on_main_before_the_tag(tmp_path, monkeypatch, capsys):
    """release-tag refuses a SHA without a green CI run on main; the steps must say so."""
    root = _git_repo(tmp_path)
    real = subprocess.run
    monkeypatch.setattr(rel.subprocess, "run", lambda argv, **kw: real(argv, **kw)
                        if argv[:2] == ["git", "-C"] else subprocess.CompletedProcess(argv, 0))
    rel.release(root, "v9.9.9")

    out = capsys.readouterr().out
    assert "wait for CI on main" in out
    assert out.index("wait for CI on main") < out.index("release-tag.yml"), out


def test_a_rename_is_named_by_its_new_path(tmp_path):
    """G5: porcelain -z puts the old name in its own field; it was read as a cut path."""
    root = _git_repo(tmp_path)
    subprocess.run(["git", "mv", "README.md", "README-OLD.md"], cwd=root, check=True)

    with pytest.raises(SystemExit) as refused:
        rel.release(root, "v9.9.9", suite=False)
    assert "README-OLD.md" in str(refused.value) and "DME.md" not in str(refused.value), refused.value


def test_release_refuses_without_a_plain_language_news_section(tmp_path):
    """#223: NEWS.md says in a few sentences what a release brings, for readers of no CHANGELOG."""
    root = _copy(tmp_path)
    _changelogs(root)
    (root / "NEWS.md").write_text("# News\n\n## v9.9.9 — t\n\n## v9.9.8 — older\n\nText.\n", encoding="utf-8")

    with pytest.raises(SystemExit, match="NEWS.md: no section for v9.9.9"):
        rel.release(root, "v9.9.9")  # a heading without sentences is no section
    assert rel.mismatches(root, CURRENT) == []  # nothing bumped


def test_check_names_a_missing_news_section(tmp_path, monkeypatch):
    root = _copy(tmp_path)
    _changelogs(root)
    (root / "NEWS.md").unlink()
    monkeypatch.setattr(rel.subprocess, "run", lambda argv, **kw: subprocess.CompletedProcess(argv, 0))

    assert any(line.startswith("NEWS.md: no section for v9.9.9") for line in rel.check(root, "v9.9.9"))


def test_the_news_reader_takes_one_section_and_stops_at_the_next():
    text = "# News\n\n## v2.0.0 — Big\n\nOne.\nTwo.\n\n## v1.9.0 — Small\n\nOld.\n"
    assert rel.news(text, "v2.0.0") == ("Big", "One.\nTwo.\n")
    assert rel.news(text, "v1.9.0") == ("Small", "Old.\n")
    assert rel.news(text, "v3.0.0") is None


def test_the_repository_news_has_a_section_for_the_current_version():
    for name in ("NEWS.md", "NEWS-DE.md"):
        assert rel.news((REPO / name).read_text(encoding="utf-8"), f"v{CURRENT}") is not None, name
    for name in ("CHANGELOG.md", "CHANGELOG-DE.md"):
        assert rel.notes((REPO / name).read_text(encoding="utf-8"), f"v{CURRENT}") is not None, name


@pytest.mark.parametrize("gone", ["CHANGELOG-DE.md", "NEWS-DE.md", "CHANGELOG.md", "NEWS.md"])
def test_a_release_needs_its_notes_in_both_languages(tmp_path, gone):
    """v2.74 (owner): the release notes exist in English and German; one missing refuses."""
    root = _copy(tmp_path)
    _changelogs(root)
    (root / gone).unlink()
    with pytest.raises(SystemExit, match=f"{gone}: no (entry|section) for v9.9.9"):
        rel.release(root, "v9.9.9")
    assert rel.mismatches(root, CURRENT) == []


def test_a_release_names_the_template_sections_it_changed(tmp_path):
    """v2.73 overlays: a project's overlay anchors to a template section; the release that
    changes or removes one says so before the update (template/docs/process/overlays.md)."""
    root = _git_repo(tmp_path)
    doc = root / "template/docs/process/x.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("# X\n\n## A\n\na\n\n## B\n\nb\n\n## C\n\nc\n", encoding="utf-8")
    gate = root / "template/scripts/process/check_overlays.py"
    gate.parent.mkdir(parents=True)
    for name in ("check_overlays.py", "markdown_read.py"):  # the gate and its reader (#443)
        shutil.copy(REPO / "template/scripts/process" / name, gate.parent / name)
    for args in (["add", "-A"], ["commit", "-q", "-m", "docs"], ["tag", f"v{CURRENT}"]):
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)
    doc.write_text("# X\n\n## A\n\na\n\n## B\n\nb, sharper\n\n## D\n\nnew\n", encoding="utf-8")

    assert rel.changed_sections(root) == ["template/docs/process/x.md: # X — changed",
                                          "template/docs/process/x.md: ## B — changed",
                                          "template/docs/process/x.md: ## C — gone"]
    with pytest.raises(SystemExit, match="naming them:\n  template/docs/process/x.md: # X"):
        rel.release(root, "v9.9.9", suite=False)
    _changelogs(root, sections=True)
    with pytest.raises(SystemExit, match="not clean"):  # past the section check: the next one speaks
        rel.release(root, "v9.9.9", suite=False)


def test_a_doc_that_became_a_template_keeps_its_sections(tmp_path):
    """v2.74: `start-here.md` → `start-here.md.jinja` is no section gone (plan review)."""
    root = _git_repo(tmp_path)
    doc = root / "template/docs/process/x.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("# X\n\n## A\n\na\n", encoding="utf-8")
    gate = root / "template/scripts/process/check_overlays.py"
    gate.parent.mkdir(parents=True)
    for name in ("check_overlays.py", "markdown_read.py"):  # the gate and its reader (#443)
        shutil.copy(REPO / "template/scripts/process" / name, gate.parent / name)
    for args in (["add", "-A"], ["commit", "-q", "-m", "docs"], ["tag", f"v{CURRENT}"]):
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)
    doc.rename(doc.with_name("x.md.jinja"))
    assert rel.changed_sections(root) == []


def test_changed_sections_reads_headings_through_the_gates_reader(tmp_path):
    """v2.102 (#443): the release loads `check_overlays` on its own (`_changes_reader`); the
    gate finds its reader beside it, in a fresh process too, and reads headings as rendered
    — a heading in an HTML comment opens no section."""
    root = _git_repo(tmp_path)
    doc = root / "template/docs/process/x.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("# X\n\n## A\n\na\n\n<!--\n## B\n-->\n\nb\n", encoding="utf-8")
    proc = root / "template/scripts/process"
    proc.mkdir(parents=True)
    for name in ("check_overlays.py", "markdown_read.py"):
        shutil.copy(REPO / "template/scripts/process" / name, proc / name)
    for args in (["add", "-A"], ["commit", "-q", "-m", "docs"], ["tag", f"v{CURRENT}"]):
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)
    doc.write_text("# X\n\n## A\n\na\n\n<!--\n## B\n-->\n\nb, sharper\n", encoding="utf-8")
    code = ("import importlib.util, sys; from pathlib import Path\n"
            "spec = importlib.util.spec_from_file_location('release_tool', sys.argv[1])\n"
            "mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)\n"
            "print(mod.changed_sections(Path(sys.argv[2])))\n")
    run = subprocess.run([sys.executable, "-B", "-c", code, str(REPO / "tools/release.py"), str(root)],
                         capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    assert run.stdout.strip() == str(["template/docs/process/x.md: # X — changed",
                                      "template/docs/process/x.md: ## A — changed"])


# --- v2.96 A4: every first-level item under What changes carries its mark ---

MARKED = "**What changes.**\n- [required] A fix.\n- [optional] A flag.\n"
UNMARKED = "**What changes.**\n- [required] A fix.\n- A point nobody graded.\n"


def _changelogs_de(root: Path, body: str) -> None:
    """Both languages, the German one under its own heading."""
    (root / "CHANGELOG.md").write_text(f"## v9.9.9 — t · 2026-11-14\n\n{body}", encoding="utf-8")
    (root / "CHANGELOG-DE.md").write_text("## v9.9.9 — t · 2026-11-14\n\n"
                                          + body.replace("**What changes.**", "**Was sich ändert.**"),
                                          encoding="utf-8")


def test_check_names_an_unmarked_item_of_a_new_entry(tmp_path, monkeypatch):
    root = _copy(tmp_path)
    _changelogs_de(root, UNMARKED)
    monkeypatch.setattr(rel.subprocess, "run", lambda argv, **kw: subprocess.CompletedProcess(argv, 0))

    left = rel.check(root, "v9.9.9")

    unmarked = [line for line in left if "without a mark" in line]
    assert [line.split(":", 1)[0] for line in unmarked] == ["CHANGELOG.md", "CHANGELOG-DE.md"], left
    assert all("A point nobody graded." in line for line in unmarked), unmarked


def test_check_passes_a_marked_entry_and_one_without_what_changes(tmp_path, monkeypatch):
    root = _copy(tmp_path)
    monkeypatch.setattr(rel.subprocess, "run", lambda argv, **kw: subprocess.CompletedProcess(argv, 0))
    for body in (MARKED, "body\n"):
        _changelogs_de(root, body)
        assert not [line for line in rel.check(root, "v9.9.9") if "without a mark" in line], body


def test_release_refuses_an_unmarked_item_before_anything_moves(tmp_path):
    root = _copy(tmp_path)
    _changelogs_de(root, UNMARKED)

    with pytest.raises(SystemExit, match=r"without a mark[\s\S]*A point nobody graded"):
        rel.release(root, "v9.9.9")
    assert rel.mismatches(root, CURRENT) == []  # nothing bumped


def test_a_released_entry_is_not_held_to_the_marks(tmp_path):
    """the entries up to the current version were written before the marks"""
    root = _copy(tmp_path)
    for name in ("CHANGELOG.md", "CHANGELOG-DE.md"):
        (root / name).write_text(f"## v{CURRENT} — t · 2026-11-11\n\n{UNMARKED}", encoding="utf-8")

    assert rel._marks_missing(root, f"v{CURRENT}") == []
    assert rel._marks_missing(root, "v9.9.9") == []  # no entry: _notes_missing speaks


def test_the_release_tools_read_the_entry_grammar_from_their_own_tree():
    """not from the `root` argument: a test root has no template (plan r3 m7)"""
    assert Path(rel.changelog.__file__) == REPO / "template/scripts/process/changelog.py"


# --- v2.102 M5: a release does not fill the disk, and a failed run loses no notes ---

GB = 2**30
VERSION_FILES = (*(path for path, _ in rel.LOCATIONS), "docs/sbom.cdx.json", "docs/SBOM.md")


@pytest.fixture(autouse=True)
def _room(monkeypatch, tmp_path_factory):
    """Every release test here runs with room to spare and its own temp dir — the host's
    free space is no input; the M5 tests below set what they measure."""
    monkeypatch.setenv("RELEASE_MIN_FREE_GB", "0")
    monkeypatch.setenv("PROCESS_DISK_LIMIT_PCT", "100")
    tmp = tmp_path_factory.mktemp("tmpdir")
    for name in ("TMPDIR", "TEMP", "TMP"):
        monkeypatch.setenv(name, str(tmp))
    return tmp


def _git_release_repo(tmp_path: Path) -> Path:
    """`_git_repo` with the SBOM the release regenerates, committed (`git add` names it)."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    root = _copy(tmp_path)
    _changelogs(root)
    (root / "docs").mkdir(exist_ok=True)
    (root / "docs/sbom.cdx.json").write_text('{"version": "old"}\n', encoding="utf-8")
    (root / "docs/SBOM.md").write_text("# SBOM old\n", encoding="utf-8")
    for args in (["init", "-q", "-b", "main"], ["config", "user.email", "t@t"],
                 ["config", "user.name", "t"], ["config", "commit.gpgsign", "false"],
                 ["add", "-A"], ["commit", "-q", "-m", "base"]):
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)
    return root


def _bytes(root: Path, rels=VERSION_FILES) -> dict[str, bytes | None]:
    return {r: (root / r).read_bytes() if (root / r).is_file() else None for r in rels}


def _faking(root: Path, monkeypatch, *, fail: str | None = None, interrupt: bool = False):
    """Real git; the SBOM writes both of its files, every other step passes — but `fail`
    (a word of the step's argv) exits 1, and with `interrupt` the suite is interrupted."""
    real, calls = subprocess.run, []

    def fake(argv, **kw):
        calls.append((list(argv), kw))
        if fail and fail in argv:
            return subprocess.CompletedProcess(argv, 1, stdout="", stderr="")
        if "pytest" in argv and interrupt:
            raise KeyboardInterrupt
        if argv[0] == "git":
            return real(argv, **kw)
        if any("gen_sbom" in str(a) for a in argv):
            (root / "docs/sbom.cdx.json").write_text('{"version": "9.9.9"}\n', encoding="utf-8")
            (root / "docs/SBOM.md").write_text("# SBOM 9.9.9\n", encoding="utf-8")
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
    monkeypatch.setattr(rel.subprocess, "run", fake)
    return calls


def test_too_little_room_refuses_before_the_bump(tmp_path, monkeypatch, _room):
    """r1 B2: the suite filled the disk mid-release. Below RELEASE_MIN_FREE_GB on the repo's
    or the temp dir's disk: no change, and what to clear (the train's hint)."""
    root = _git_release_repo(tmp_path)
    before = _bytes(root)
    monkeypatch.setenv("RELEASE_MIN_FREE_GB", "12")
    monkeypatch.setattr(rel.process_git, "disk_use",
                        lambda path, fallback=False: rel.process_git.DiskUse(50.0, None, 90.0, 3 * GB))
    calls = _faking(root, monkeypatch)

    with pytest.raises(SystemExit) as refused:
        rel.release(root, "v9.9.9")
    msg = str(refused.value)
    assert "needs 12 GB" in msg and "RELEASE_MIN_FREE_GB" in msg and "nothing changed" in msg, msg
    assert f"old test basetemps under {_room} (pytest-of-*" in msg, msg
    assert _bytes(root) == before
    assert not [argv for argv, _ in calls if argv[0] != "git"], calls  # no sbom, lint, suite


def test_a_disk_over_the_percent_limit_refuses_too(tmp_path, monkeypatch):
    """The train's limit holds here as well (PROCESS_DISK_LIMIT_PCT), however many GB are free."""
    root = _git_release_repo(tmp_path)
    before = _bytes(root)
    monkeypatch.setenv("PROCESS_DISK_LIMIT_PCT", "90")
    monkeypatch.setattr(rel.process_git, "disk_use",
                        lambda path, fallback=False: rel.process_git.DiskUse(95.0, None, 90.0, 500 * GB))
    _faking(root, monkeypatch)

    with pytest.raises(SystemExit, match=r"disk-full .* 95%"):
        rel.release(root, "v9.9.9")
    assert _bytes(root) == before


@pytest.mark.parametrize("use, free_gb, need, short", [
    (95.0, 500, "0", "at or over the 90% limit"),  # the percent check stays here (#446)
    (50.0, 3, "12", "needs 12 GB"),                # and the release's own floor
    (50.0, 1.5, "1", None),                        # the train's 2 GiB floor is no check of the release's
])
def test_release_keeps_its_percent_and_its_own_floor(tmp_path, monkeypatch, use, free_gb, need, short):
    """v2.103 (#446): the train warns at the percentage and halts below its floor; the release
    keeps both of its checks — `over_pct` and RELEASE_MIN_FREE_GB — and counts GiB as the
    train does (one constant)."""
    assert GB == rel.GB == rel.process_git.GIB
    monkeypatch.setenv("RELEASE_MIN_FREE_GB", need)
    monkeypatch.setattr(rel.process_git, "disk_use", lambda path, fallback=False:
                        rel.process_git.DiskUse(use, None, 90.0, int(free_gb * GB), 2.0))
    got = rel._disk_short(tmp_path)
    assert (got == []) if short is None else (len(got) == 2 and all(short in x for x in got)), got


def test_a_missing_tmpdir_does_not_crash(tmp_path, monkeypatch):
    """Unset, the platform default is read; set to a folder that is not there, the check
    measures its nearest existing parent and the suite's folder goes there."""
    root = _git_release_repo(tmp_path / "first")
    for name in ("TMPDIR", "TEMP", "TMP"):
        monkeypatch.delenv(name, raising=False)
    _faking(root, monkeypatch)
    rel.release(root, "v9.9.9", suite=False)

    root = _git_release_repo(tmp_path / "second")
    gone = tmp_path / "gone" / "deeper"
    monkeypatch.setenv("TMPDIR", str(gone))
    calls = _faking(root, monkeypatch)
    rel.release(root, "v9.9.9")
    suite = next(argv for argv, _ in calls if "pytest" in argv)
    basetemp = Path(next(a for a in suite if a.startswith("--basetemp=")).split("=", 1)[1])
    assert basetemp.parent.parent == tmp_path and not basetemp.parent.exists(), basetemp


def test_the_suite_runs_in_its_own_temp_folder_and_leaves_none(tmp_path, monkeypatch, _room):
    """r2 M4: `--basetemp` before the xdist arguments, and TMPDIR/TEMP/TMP of the suite in the
    same folder — pytest runs inside tests land there too; the folder is gone afterwards."""
    root = _git_release_repo(tmp_path)
    calls = _faking(root, monkeypatch)
    monkeypatch.setattr(rel.importlib.util, "find_spec", lambda name: object())
    rel.release(root, "v9.9.9")
    suite, kw = next((argv, kw) for argv, kw in calls if "pytest" in argv)
    assert suite[-4:] == ["-n", "4", "--dist", "loadfile"] and suite[-5].startswith("--basetemp="), suite
    folder = Path(suite[-5].split("=", 1)[1]).parent
    assert folder.parent == _room, folder
    assert {kw["env"][name] for name in ("TMPDIR", "TEMP", "TMP")} == {str(folder / "tmp")}, kw["env"]
    assert list(_room.iterdir()) == []


@pytest.mark.parametrize("how", ["pytest", "ruff", "interrupt"])
def test_a_failed_run_restores_the_version_files_and_keeps_the_notes(tmp_path, monkeypatch, _room, how):
    """r1 B2, r2 M6: a failed run left the files bumped; resetting every release file would
    have dropped the unsaved notes. Only what bump and gen_sbom write goes back, byte for
    byte — also on an interrupt — and no temp folder is left."""
    root = _git_release_repo(tmp_path)
    before = _bytes(root)
    notes = "## v9.9.9 — t · 2026-10-15\n\nbody, still being written\r\n"
    (root / "CHANGELOG.md").write_text(notes, encoding="utf-8", newline="")
    unsaved = (root / "CHANGELOG.md").read_bytes()
    calls = _faking(root, monkeypatch, fail=None if how == "interrupt" else how, interrupt=how == "interrupt")

    with pytest.raises(KeyboardInterrupt if how == "interrupt" else SystemExit):
        rel.release(root, "v9.9.9")
    assert _bytes(root) == before
    assert (root / "CHANGELOG.md").read_bytes() == unsaved
    assert list(_room.iterdir()) == []
    assert not any("commit" in argv or "add" in argv for argv, _ in calls)


def test_a_failed_restore_is_named(tmp_path, monkeypatch, capsys):
    root = _git_release_repo(tmp_path)
    _faking(root, monkeypatch, fail="ruff")
    real_write = Path.write_bytes

    def write_bytes(self, data):
        if self.name == "README-DE.md":
            raise OSError("read-only")
        return real_write(self, data)
    monkeypatch.setattr(Path, "write_bytes", write_bytes)

    with pytest.raises(SystemExit, match="lint failed"):
        rel.release(root, "v9.9.9")
    err = capsys.readouterr().err
    assert "not restored" in err and "README-DE.md" in err.split("not restored", 1)[1], err
    assert "pyproject.toml" not in err.split("not restored", 1)[1], err


def test_a_failed_commit_keeps_the_staged_release(tmp_path, monkeypatch):
    """r2 M6: past `git add` the run is tested and staged — nothing is reset, the message
    says only the commit is missing."""
    root = _git_release_repo(tmp_path)
    _faking(root, monkeypatch, fail="commit")

    with pytest.raises(SystemExit, match="tested and staged, only the commit is missing"):
        rel.release(root, "v9.9.9")
    assert rel.mismatches(root, "9.9.9") == []
    staged = subprocess.run(["git", "diff", "--cached", "--name-only"], cwd=root,
                            capture_output=True, text=True, check=True).stdout.split()
    assert set(VERSION_FILES) <= set(staged), staged


def test_the_free_space_default_is_the_one_maintaining_names():
    text = " ".join((REPO / "MAINTAINING.md").read_text(encoding="utf-8").split())
    assert f"`RELEASE_MIN_FREE_GB` frei sein (Vorgabe {rel.MIN_FREE_GB:g} GB" in text


def test_release_reads_the_disk_with_process_git_of_its_own_tree():
    """loaded by its path, not through the train and its imports (r2 M5)"""
    assert Path(rel.process_git.__file__) == REPO / "template/scripts/process/process_git.py"
    assert "train" not in vars(rel)
