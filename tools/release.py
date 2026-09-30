#!/usr/bin/env python3
"""release — the local part of a template release in one run.

    python3 tools/release.py v2.38.0            bump, regenerate, check, commit
    python3 tools/release.py v2.38.0 --check    report what does not carry the version
    python3 tools/release.py v2.38.0 --no-suite skip the full suite (it ran already)

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


def _run(root: Path, what: str, *argv: str) -> None:
    print(f"release: {what}: {' '.join(argv)}", flush=True)
    if subprocess.run(argv, cwd=root).returncode != 0:
        raise SystemExit(f"release: {what} failed — nothing committed; fix it and run again")


def release(root: Path, tag: str, *, suite: bool = True) -> None:
    m = VERSION.match(tag)
    if not m:
        raise SystemExit(f"release: {tag!r} is no version (expected vX.Y.Z)")
    number = m.group(1)
    if notes((root / "CHANGELOG.md").read_text(encoding="utf-8"), tag) is None:
        raise SystemExit(f"release: CHANGELOG.md has no entry for {tag} — write it first "
                         f"(`**{tag} — <title>.**`); a release without notes is not published")
    bump(root, number)
    left = mismatches(root, number)
    if left:
        raise SystemExit("release: still not at the version:\n  " + "\n  ".join(left))
    _run(root, "sbom", sys.executable, "tools/gen_sbom.py")
    _run(root, "lint", "ruff", "check", ".")
    if suite:
        _run(root, "suite", sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider")
    shutil.rmtree(root / "template/scripts/process/__pycache__", ignore_errors=True)
    _run(root, "stage", "git", "add", "-A", "CHANGELOG.md", "pyproject.toml", "uv.lock",
         "README.md", "README-DE.md", "docs/sbom.cdx.json", "docs/SBOM.md")
    _run(root, "commit", "git", "commit", "-q", "-m", f"release: {tag}")
    print(f"""release: {tag} committed. Remote steps:
  1. push the branch, open the PR, merge it (rebase)
  2. release-tag.yml with tag={tag} and sha=<the merged SHA on main>
  3. once the tag exists: release-publish.yml with tag={tag}
  4. rebase the working branch onto origin/main""")


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    if len(args) != 1:
        print(__doc__.strip().splitlines()[2].strip(), file=sys.stderr)
        return 2
    tag = args[0]
    if "--check" in argv:
        m = VERSION.match(tag)
        if not m:
            print(f"release: {tag!r} is no version (expected vX.Y.Z)", file=sys.stderr)
            return 2
        left = mismatches(ROOT, m.group(1))
        if notes((ROOT / "CHANGELOG.md").read_text(encoding="utf-8"), tag) is None:
            left.append(f"CHANGELOG.md: no entry for {tag}")
        for line in left:
            print(f"release: {line}")
        print("release: OK" if not left else f"release: {len(left)} location(s) not at {tag}")
        return 1 if left else 0
    release(ROOT, tag, suite="--no-suite" not in argv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
