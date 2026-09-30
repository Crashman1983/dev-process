#!/usr/bin/env python3
"""release — the local part of a template release in one run.

    python3 tools/release.py vX.Y.Z             bump, regenerate, check, commit
    python3 tools/release.py vX.Y.Z --check     report what does not carry the version
    python3 tools/release.py vX.Y.Z --no-suite  skip the full suite (it ran already)

The ritual was a dozen hand steps, and a missed one showed late: a README
still naming the old version, a tag on a SHA without its CHANGELOG entry. The
steps, in order, stopping at the first failure:

1. the CHANGELOG has an entry for the version (`release_notes.notes`, the
   same reader the publish workflow uses — no entry, no release);
2. every version location carries it (`LOCATIONS`);
3. the SBOM is regenerated (`tools/gen_sbom.py`);
4. `ruff check .` and the full suite pass;
5. the template's `__pycache__` is gone;
6. one commit `release: <version>`.

The remote part (PR, merge, tag on the merged SHA, publish) is printed at the
end: it needs the host's GitHub access, which this script does not assume.
Stdlib only.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from release_notes import notes  # noqa: E402

VERSION = re.compile(r"^v(\d+\.\d+\.\d+)$")

# (file, pattern with one group around the version) — every place a release
# names its version. tests/test_release_tool.py fails when the repository
# carries the current version anywhere else, so a new location cannot be
# forgotten here.
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
RELEASE_FILES = ("CHANGELOG.md", *(rel for rel, _ in LOCATIONS), "docs/sbom.cdx.json", "docs/SBOM.md")


def _current(root: Path) -> tuple[int, ...]:
    """The released version: the committed one — a failed run leaves the files bumped, and
    read from them the rerun it asks for was refused as "not above" (refute of #123)."""
    shown = subprocess.run(["git", "-C", str(root), "show", f"HEAD:{LOCATIONS[0][0]}"],
                           capture_output=True, text=True)
    text = shown.stdout if shown.returncode == 0 else (root / LOCATIONS[0][0]).read_text(encoding="utf-8")
    found = LOCATIONS[0][1].findall(text)
    return tuple(int(x) for x in found[0].split(".")) if found else (0,)


def check(root: Path, tag: str) -> list[str]:
    """What is not at `tag` yet: the locations, the CHANGELOG entry and the SBOM (its own
    `--check`; the SBOM names the version too, and `--check` said OK while it was stale)."""
    m = VERSION.match(tag)
    if not m:
        return [f"{tag!r} is no version (expected vX.Y.Z)"]
    left = mismatches(root, m.group(1))
    if notes((root / "CHANGELOG.md").read_text(encoding="utf-8"), tag) is None:
        left.append(f"CHANGELOG.md: no entry for {tag}")
    sbom = subprocess.run([sys.executable, "tools/gen_sbom.py", "--check"], cwd=root, capture_output=True)
    if sbom.returncode != 0:
        left.append("docs/sbom.cdx.json / docs/SBOM.md: stale (tools/gen_sbom.py --check)")
    return left


def _run(root: Path, what: str, *argv: str) -> None:
    print(f"release: {what}: {' '.join(argv)}", flush=True)
    if subprocess.run(argv, cwd=root).returncode != 0:
        raise SystemExit(f"release: {what} failed — nothing committed; fix it and run again")


def release(root: Path, tag: str, *, suite: bool = True) -> None:
    m = VERSION.match(tag)
    if not m:
        raise SystemExit(f"release: {tag!r} is no version (expected vX.Y.Z)")
    number = m.group(1)
    if tuple(int(x) for x in number.split(".")) <= _current(root):
        raise SystemExit(f"release: {tag} is not above the current version "
                         f"{'.'.join(map(str, _current(root)))}")
    if notes((root / "CHANGELOG.md").read_text(encoding="utf-8"), tag) is None:
        raise SystemExit(f"release: CHANGELOG.md has no entry for {tag} — write it first "
                         f"(`**{tag} — <title>.**`); a release without notes is not published")
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
    bump(root, number)
    left = mismatches(root, number)
    if left:
        raise SystemExit("release: still not at the version:\n  " + "\n  ".join(left))
    _run(root, "sbom", sys.executable, "tools/gen_sbom.py")
    _run(root, "lint", "ruff", "check", ".")
    if suite:
        _run(root, "suite", sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider")
    shutil.rmtree(root / "template/scripts/process/__pycache__", ignore_errors=True)
    _run(root, "stage", "git", "add", "-A", *RELEASE_FILES)
    _run(root, "commit", "git", "commit", "-q", "-m", f"release: {tag}")
    print(f"""release: {tag} committed. Remote steps:
  1. push the branch, open the PR, merge it (rebase)
  2. release-tag.yml with tag={tag} and sha=<the merged SHA on main>
  3. once the tag exists: release-publish.yml with tag={tag}
  4. rebase the working branch onto origin/main""")


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
