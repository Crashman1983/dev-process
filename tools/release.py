#!/usr/bin/env python3
"""release — the local part of a template release in one run.

    python3 tools/release.py vX.Y.Z             bump, regenerate, check, commit
    python3 tools/release.py vX.Y.Z --check     report what does not carry the version
    python3 tools/release.py vX.Y.Z --no-suite  skip the full suite (it ran already)

The ritual was a dozen hand steps, and a missed one showed late: a README
still naming the old version, a tag on a SHA without its CHANGELOG entry. The
steps, in order, stopping at the first failure:

1. both languages of the release notes have their section for the version:
   CHANGELOG.md and CHANGELOG-DE.md an entry (`release_notes.notes`, the same
   reader the publish workflow uses — no entry, no release), NEWS.md and
   NEWS-DE.md a plain-language section (`release_notes.news`). The entry names
   the template sections it changed or removed (**Changed sections.** /
   **Geänderte Abschnitte.**) when there are any — a project's overlays anchor
   to them (`changed_sections`, against the last release's tag); every
   first-level item under **What changes.** / **Was sich ändert.** starts with
   its mark, `[required]`, `[recommended]` or `[optional]` (`_marks_missing`;
   the grammar is the core `changelog.py`, read from this tool's tree);
2. the repository's and the temp dir's disk have room: RELEASE_MIN_FREE_GB free
   (MAINTAINING.md) and under the train's PROCESS_DISK_LIMIT_PCT — else it stops
   here, nothing changed;
3. every version location carries it (`LOCATIONS`);
4. the SBOM is regenerated (`tools/gen_sbom.py`);
5. `ruff check .` and the full suite pass, the suite in its own temp folder
   (`--basetemp` and its children's TMPDIR), removed afterwards;
6. the template's `__pycache__` is gone;
7. one commit `release: <version>`.

A step that fails before `git add` puts back what 3 and 4 wrote (`BUMPED`, byte for
byte, and names a file it could not); the release notes are never touched. A failed
commit keeps the tested, staged tree.

The suite runs by default: it tests the bumped tree with the new SBOM before the
commit — skipped, a broken release commit can reach main, and the version is then
refused as "not above". `--no-suite` only when it just ran on this tree. With
pytest-xdist installed it runs on four workers with `--dist loadfile` (the render
caches are per worker, so a file's tests stay on one; docs/maintenance-2026-10-02.md,
Laufzeiten); without it, serially.

The remote part (PR, merge, wait for CI on main to be green for the merged SHA,
tag it, publish) is printed at the end: it needs the host's GitHub access, which
this script does not assume. release-tag.yml refuses a SHA without a green CI
run on main, release-publish.yml re-checks the tag's commit (tools/ci_evidence.py).
Stdlib only.
"""
from __future__ import annotations

import argparse
import contextlib
import importlib.util
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from release_notes import changelog, news, notes  # noqa: E402


def _load_process_git():
    """The disk readers of this tool's tree (`template/scripts/process/process_git.py`, stdlib),
    loaded by path — not through `train` and its imports, and without a `__pycache__`."""
    spec = importlib.util.spec_from_file_location(
        "release_process_git", ROOT / "template/scripts/process/process_git.py")
    mod = importlib.util.module_from_spec(spec)
    keep, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.dont_write_bytecode = keep
    return mod


process_git = _load_process_git()

VERSION = re.compile(r"^v(\d+\.\d+\.\d+)$")

# (file, pattern with one group around the version) — every place a release
# names its version. tests/test_release_tool.py fails when the repository
# carries the current version anywhere else, so a new location cannot be
# forgotten here. Not here on purpose: docs/OVERVIEW.md and docs/UEBERBLICK.md
# name the version they were last checked against — a release does not re-check them.
LOCATIONS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("pyproject.toml", re.compile(r'^version = "(\d+\.\d+\.\d+)"$', re.MULTILINE)),
    ("uv.lock", re.compile(r'^name = "dev-process"\nversion = "(\d+\.\d+\.\d+)"$', re.MULTILINE)),
    ("README.md", re.compile(r"^> \*\*Status:\*\* `v(\d+\.\d+\.\d+)`", re.MULTILINE)),
    ("README-DE.md", re.compile(r"^> \*\*Status:\*\* `v(\d+\.\d+\.\d+)`", re.MULTILINE)),
)


def mismatches(root: Path, number: str) -> list[str]:
    """Every location that does not carry `number`, with what it carries instead."""
    out = []
    for rel, pattern in LOCATIONS:
        path = root / rel
        found = pattern.findall(path.read_text(encoding="utf-8")) if path.is_file() else []
        if len(found) != 1:
            out.append(f"{rel}: {len(found)} version line(s) found, expected 1")
        elif found[0] != number:
            out.append(f"{rel}: carries {found[0]}")
    return out


def bump(root: Path, number: str) -> None:
    for rel, pattern in LOCATIONS:
        path = root / rel
        text = path.read_text(encoding="utf-8")
        m = pattern.search(text)
        if m is None:
            raise SystemExit(f"release: {rel} has no version line — update LOCATIONS")
        path.write_text(text[:m.start(1)] + number + text[m.end(1):], encoding="utf-8")


# what the release commit carries: a tree dirty anywhere else would ride along
# both languages of the release notes (README.md / README-DE.md convention): the
# CHANGELOG (what changed, why, what it leads to) and NEWS (a few plain sentences)
CHANGELOGS = ("CHANGELOG.md", "CHANGELOG-DE.md")
NEWS_FILES = ("NEWS.md", "NEWS-DE.md")
SBOM_FILES = ("docs/sbom.cdx.json", "docs/SBOM.md")
# what `bump` and `tools/gen_sbom.py` write — and all a failed run puts back. Never the
# release notes: they are written by hand before the run, often not yet saved in git (r1 B2).
BUMPED = (*(rel for rel, _ in LOCATIONS), *SBOM_FILES)
RELEASE_FILES = (*CHANGELOGS, *NEWS_FILES, *BUMPED)


def _current(root: Path) -> tuple[int, ...]:
    """The released version: the committed one. A run that fails before `git add` puts the
    bumped files back, but one whose commit failed leaves them bumped and staged (and a
    restore can fail) — read from them, the rerun it asks for was refused as "not above"
    (refute of #123)."""
    shown = subprocess.run(["git", "-C", str(root), "show", f"HEAD:{LOCATIONS[0][0]}"],
                           capture_output=True, text=True)
    text = shown.stdout if shown.returncode == 0 and shown.stdout else (root / LOCATIONS[0][0]).read_text(encoding="utf-8")
    found = LOCATIONS[0][1].findall(text)
    return tuple(int(x) for x in found[0].split(".")) if found else (0,)


def _above_current(root: Path, tag: str) -> bool:
    """Is `tag` a version above the released one — a release still to be made?"""
    m = VERSION.match(tag)
    return bool(m) and tuple(int(x) for x in m.group(1).split(".")) > _current(root)


def _notes_missing(root: Path, tag: str) -> list[str]:
    """Every release-notes file without its section for `tag`, with what it needs."""
    missing = []
    for rel in CHANGELOGS:
        path = root / rel
        if not path.is_file() or notes(path.read_text(encoding="utf-8"), tag) is None:
            missing.append(f"{rel}: no entry for {tag} (`## {tag} — <title> · <date>`, MAINTAINING.md)")
    for rel in NEWS_FILES:
        path = root / rel
        if not path.is_file() or news(path.read_text(encoding="utf-8"), tag) is None:
            missing.append(f"{rel}: no section for {tag} (`## {tag} — <title>` and a few plain sentences)")
    return missing


# what a project's overlay can anchor to (template/docs/process/overlays.md): the
# template's process docs and commands; a release that changes or removes one of
# their sections names it in its CHANGELOG entry, under this marker
ANCHORABLE = ("template/docs/process/", "template/{% if harnesses.claude %}.claude{% endif %}/commands/",
              "template/.github/{% if harnesses.copilot %}prompts{% endif %}/")
SECTIONS_MARKER = "Geänderte Abschnitte"
SECTIONS_MARKERS = {"CHANGELOG.md": "Changed sections", "CHANGELOG-DE.md": SECTIONS_MARKER}


def _changes_reader(root: Path):
    spec = importlib.util.spec_from_file_location(
        "release_check_overlays", root / "template/scripts/process/check_overlays.py")
    mod = importlib.util.module_from_spec(spec)
    keep, sys.dont_write_bytecode = sys.dont_write_bytecode, True  # no __pycache__ in the template
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.dont_write_bytecode = keep
    return mod.section_changes


def changed_sections(root: Path) -> list[str] | None:
    """`path: heading — changed|gone` for every section of an anchorable doc that
    differs from the last release (the tag of the committed version); None when that
    tag is not here (`git fetch --tags`). New sections are no break for an overlay."""
    base = "v" + ".".join(map(str, _current(root)))
    listed = subprocess.run(["git", "-C", str(root), "ls-tree", "-r", "--name-only", base, "--", *ANCHORABLE],
                            capture_output=True, text=True)
    if listed.returncode != 0:
        return None
    section_changes, out = None, []
    for rel in sorted((listed.stdout or "").splitlines()):
        if not rel.endswith((".md", ".md.jinja")) or rel.endswith(".local.md"):
            continue
        old = subprocess.run(["git", "-C", str(root), "show", f"{base}:{rel}"], capture_output=True, text=True)
        if old.returncode != 0:
            continue
        section_changes = section_changes or _changes_reader(root)
        path = root / rel
        if not path.is_file() and (root / f"{rel}.jinja").is_file():  # became a template: not gone
            path = root / f"{rel}.jinja"
        now = path.read_text(encoding="utf-8") if path.is_file() else ""
        out += [f"{rel}: {heading} — {kind}" for heading, kind in section_changes(old.stdout, now).items()]
    return out


def _sections_unnamed(root: Path, tag: str) -> list[str]:
    """The changed sections, when the CHANGELOG entry of a new release does not name
    them yet (the released version itself has nothing to compare against)."""
    if not _above_current(root, tag):
        return []
    found = changed_sections(root)
    if not found:
        return []
    for rel, marker in SECTIONS_MARKERS.items():
        path = root / rel
        entry = "\n".join(notes(path.read_text(encoding="utf-8"), tag) or ()) if path.is_file() else ""
        if marker.lower() not in entry.lower():
            return found
    return []


def _marks_missing(root: Path, tag: str) -> list[str]:
    """Every first-level item under **What changes.** / **Was sich ändert.** of a new
    release's entry that carries no mark. The released entries were written before the
    marks; an entry without that part has no item; no entry at all is _notes_missing's."""
    if not _above_current(root, tag):
        return []
    out = []
    for rel in CHANGELOGS:
        path = root / rel
        found = notes(path.read_text(encoding="utf-8"), tag) if path.is_file() else None
        out += [f"{rel}: {tag} item without a mark ([required]/[recommended]/[optional]) — {line}"
                for mark, line in changelog.marks(found[1] if found else "") if mark is None]
    return out


def check(root: Path, tag: str) -> list[str]:
    """What is not at `tag` yet: the locations, the CHANGELOG entry and the SBOM (its own
    `--check`; the SBOM names the version too, and `--check` said OK while it was stale)."""
    m = VERSION.match(tag)
    if not m:
        return [f"{tag!r} is no version (expected vX.Y.Z)"]
    left = mismatches(root, m.group(1))
    left += _notes_missing(root, tag)
    left += _marks_missing(root, tag)
    left += [f"CHANGELOG: `Changed sections` / `{SECTIONS_MARKER}` not named — {s}"
             for s in _sections_unnamed(root, tag)]
    sbom = subprocess.run([sys.executable, "tools/gen_sbom.py", "--check"], cwd=root, capture_output=True)
    if sbom.returncode != 0:
        left.append("docs/sbom.cdx.json / docs/SBOM.md: stale (tools/gen_sbom.py --check)")
    return left


def _run(root: Path, what: str, *argv: str, env: dict[str, str] | None = None,
         failed: str = "nothing committed; fix it and run again") -> None:
    print(f"release: {what}: {' '.join(argv)}", flush=True)
    if subprocess.run(argv, cwd=root, env=env).returncode != 0:
        raise SystemExit(f"release: {what} failed — {failed}")


# --- the disk (v2.102 M5) ------------------------------------------------------------------
# A release ran its suite on a disk with too little room: the suite filled it, the run
# failed late, and the bumped files stayed. Before the bump the disks it writes to — the
# repository's and the temp dir's — need RELEASE_MIN_FREE_GB free and stay under the
# train's percentage limit (`process_git.disk_use`, PROCESS_DISK_LIMIT_PCT).
MIN_FREE_ENV = "RELEASE_MIN_FREE_GB"
MIN_FREE_GB = 18.0  # a measured run's peak (14.7 GB, MAINTAINING.md) and room to grow
GB = 2**30  # as `df -h` counts


def _min_free_gb() -> float:
    raw = os.environ.get(MIN_FREE_ENV, "").strip()
    try:
        need = float(raw) if raw else MIN_FREE_GB
    except ValueError:
        need = math.nan
    if not (math.isfinite(need) and need >= 0):
        raise SystemExit(f"release: {MIN_FREE_ENV}={raw!r} is no number of GB — fix or unset it "
                         f"(default {MIN_FREE_GB:g}); nothing changed")
    return need


def _disk_short(root: Path) -> list[str]:
    """Every disk the release writes to that is over the limit or has less than
    RELEASE_MIN_FREE_GB free, measured at the nearest folder that exists (a `TMPDIR` nobody
    made is no crash). A use that cannot be read is a note, as in the train."""
    need, short = _min_free_gb(), []
    for what, path in (("the repository", root), ("the temp dir", process_git.temp_root())):
        at = process_git.nearest_dir(Path(path))
        use = process_git.disk_use(at, fallback=True)
        if use.problem:
            print(f"release: note — {use.problem}", file=sys.stderr, flush=True)
        if use.full and use.use_pct is not None:
            short.append(f"{what}: {process_git.disk_full_line(at, use.use_pct)} — at or over the "
                         f"{use.limit:g}% limit ({process_git.DISK_LIMIT_ENV})")
        elif use.free is not None and use.free < need * GB:
            short.append(f"{what} {at}: {use.free / GB:.1f} GB free, a release needs {need:g} GB "
                         f"({MIN_FREE_ENV})")
    return short


def _suite_folder() -> Path:
    """The suite's own temp folder, where the space was measured: `--basetemp` and the
    children's TMPDIR inside it, removed after the run."""
    base = process_git.nearest_dir(process_git.temp_root())
    try:
        return Path(tempfile.mkdtemp(prefix="release-suite-", dir=base))
    except OSError as exc:
        raise SystemExit(f"release: no temp folder for the suite under {base}: {exc} — "
                         "set TMPDIR to a writable folder; nothing changed") from None


def _snapshot(root: Path) -> dict[str, bytes | None]:
    """The bytes of what the run will write (`BUMPED`); None for a file that is not there."""
    return {rel: (root / rel).read_bytes() if (root / rel).is_file() else None for rel in BUMPED}


def _restore(root: Path, saved: dict[str, bytes | None]) -> None:
    """Put `saved` back where the run changed it, then compare the bytes: every file that
    is not as before is named — the rerun needs them as they were."""
    def now(path: Path) -> bytes | None | OSError:
        try:
            return path.read_bytes() if path.is_file() else None
        except OSError as exc:
            return exc

    for rel, data in saved.items():
        path = root / rel
        if now(path) != data:
            with contextlib.suppress(OSError):  # one failed write does not stop the others
                path.unlink() if data is None else path.write_bytes(data)
    left = [rel for rel, data in saved.items() if now(root / rel) != data]
    if left:
        print("release: not restored to their state before the run — put them back by hand: "
              + ", ".join(left), file=sys.stderr, flush=True)
    else:
        print("release: the version and SBOM files are as before the run", file=sys.stderr, flush=True)


def _parallel() -> list[str]:
    """xdist arguments when it is installed: four workers, not auto (a release
    must not take the whole host), files kept whole (per-worker render caches)."""
    return ["-n", "4", "--dist", "loadfile"] if importlib.util.find_spec("xdist") else []


def release(root: Path, tag: str, *, suite: bool = True) -> None:
    m = VERSION.match(tag)
    if not m:
        raise SystemExit(f"release: {tag!r} is no version (expected vX.Y.Z)")
    number = m.group(1)
    if tuple(int(x) for x in number.split(".")) <= _current(root):
        raise SystemExit(f"release: {tag} is not above the current version "
                         f"{'.'.join(map(str, _current(root)))}")
    missing = _notes_missing(root, tag)
    if missing:
        raise SystemExit("release: write the release notes first — a release without them is not "
                         "published:\n  " + "\n  ".join(missing))
    unmarked = _marks_missing(root, tag)
    if unmarked:
        raise SystemExit("release: every first-level item under `What changes` / `Was sich ändert` starts "
                         "with its mark — `[required]` (security, a broken contract, data loss, a defect "
                         "that blocks work), `[recommended]` or `[optional]` (MAINTAINING.md):\n  "
                         + "\n  ".join(unmarked))
    if changed_sections(root) is None:
        print("release: the last release's tag is not here — `git fetch --tags` to list the changed "
              "sections overlays may anchor to", flush=True)
    unnamed = _sections_unnamed(root, tag)
    if unnamed:
        raise SystemExit(f"release: the {tag} entry does not name the template sections it changed — "
                         f"projects re-check their overlays against them (docs/process/overlays.md). Add "
                         f"a line `**Changed sections.** …` (CHANGELOG.md) and `**{SECTIONS_MARKER}.** …` "
                         f"(CHANGELOG-DE.md) naming them:\n  " + "\n  ".join(unnamed))
    status = subprocess.run(["git", "-C", str(root), "status", "--porcelain", "-z"],
                            capture_output=True, text=True)
    if status.returncode != 0:
        raise SystemExit("release: git cannot tell whether the tree is clean — not releasing")
    others, entries = [], iter(status.stdout.split("\0"))
    for entry in entries:
        if len(entry) > 3 and entry[3:] not in RELEASE_FILES:
            others.append(entry[3:])
        if {"R", "C"} & set(entry[:2]):
            next(entries, None)  # the old name of a rename or copy, in its own field
    if others:
        raise SystemExit("release: the tree is not clean outside the release's own files — "
                         "commit or stash first: " + ", ".join(sorted(others)[:5]))
    short = _disk_short(root)
    if short:
        tmp = process_git.temp_root()
        raise SystemExit("release: too little room for the suite — nothing changed:\n  " + "\n  ".join(short)
                         + f"\nclear there: old test basetemps under {tmp} (pytest-of-*, other runs' "
                         "leftovers), merged worktrees and their environments")
    saved = _snapshot(root)
    folder = _suite_folder() if suite else None
    staged = False
    try:
        bump(root, number)
        left = mismatches(root, number)
        if left:
            raise SystemExit("release: still not at the version:\n  " + "\n  ".join(left))
        _run(root, "sbom", sys.executable, "tools/gen_sbom.py")
        _run(root, "lint", "ruff", "check", ".")
        if folder is not None:
            (folder / "tmp").mkdir()
            env = {**os.environ, **dict.fromkeys(("TMPDIR", "TEMP", "TMP"), str(folder / "tmp"))}
            _run(root, "suite", sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                 f"--basetemp={folder / 'basetemp'}", *_parallel(), env=env)
        shutil.rmtree(root / "template/scripts/process/__pycache__", ignore_errors=True)
        _run(root, "stage", "git", "add", "-A", *RELEASE_FILES)
        staged = True
        _run(root, "commit", "git", "commit", "-q", "-m", f"release: {tag}",
             failed=f"tested and staged, only the commit is missing: git commit -m 'release: {tag}'")
    finally:
        if folder is not None:
            shutil.rmtree(folder, ignore_errors=True)
        if not staged:  # failed before `git add` — SystemExit, KeyboardInterrupt, anything
            _restore(root, saved)
    print(f"""release: {tag} committed. Remote steps:
  1. push the branch, open the PR, merge it (rebase)
  2. wait for CI on main to be green for the merged SHA (release-tag refuses otherwise)
  3. release-tag.yml with tag={tag} and sha=<the merged SHA on main>
  4. once the tag exists: release-publish.yml with tag={tag} (re-checks the tag's commit)
  5. rebase the working branch onto origin/main""")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="release.py", description="the local part of a template release")
    ap.add_argument("tag", help="vX.Y.Z")
    ap.add_argument("--check", action="store_true", help="report what is not at the version, change nothing")
    ap.add_argument("--no-suite", action="store_true", help="skip the full suite (it ran already)")
    args = ap.parse_args(argv)  # an unknown flag (`--chek`) stops here, before anything runs
    if args.check:
        left = check(ROOT, args.tag)
        for line in left:
            print(f"release: {line}")
        print("release: OK" if not left else f"release: {len(left)} item(s) not at {args.tag}")
        return 1 if left else 0
    release(ROOT, args.tag, suite=not args.no_suite)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
