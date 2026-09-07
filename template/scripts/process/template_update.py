#!/usr/bin/env python3
"""template_update: a `copier update` that respects what this project owns.

A downstream project that has lived with the template for a while owns some
of the rendered files outright — a gate it extended, a command it rewrote, a
checklist it sharpened. Every template release then conflicts on exactly
those files, and resolving them by hand costs an hour per release (measured
on the reference project: five scripts, one doc, one command). This tool
makes the owner list explicit and the port mechanical:

  1. `.process-owned` lists the repo-relative paths (globs allowed) this
     project owns. The template never overwrites them.
  2. `copier update` runs as usual for everything else.
  3. For every owned file the tool restores the committed version and writes
     the TEMPLATE's own delta (old release render -> new release render) to
     `.process-work/template-delta/<ref>/<path>.diff` — the exact change to
     port by hand, without the noise of the local divergence.
  4. Leftover conflict markers in non-owned files are listed.

Stdlib plus the `copier` CLI on PATH (uvx copier works; PyYAML, copier's
own dependency, is used when importable). The two extra
renders cost seconds; the manual port they replace cost an hour.

Usage: template_update.py [root] [--ref <tag-or-sha>] [--dry-run]
"""
from __future__ import annotations

import difflib
import fnmatch
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

OWNED_FILE = ".process-owned"
ANSWERS = ".copier-answers.yml"
DELTA_DIR = ".process-work/template-delta"
MARKER = re.compile(r"^(<<<<<<<|=======|>>>>>>>)", re.MULTILINE)


def owned_patterns(root: Path) -> list[str]:
    f = root / OWNED_FILE
    if not f.is_file():
        return []
    return [ln.strip() for ln in f.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")]


def is_owned(rel: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(rel, pat) or rel == pat for pat in patterns)


def answers(root: Path) -> tuple[str | None, str | None, dict[str, str]]:
    """(src_path, commit, {answer: yaml-flow-value}) — the recorded answers,
    re-asserted on every copier call. Copier recomputes `when: false`
    questions (the template's derived `modules`/`harnesses` mappings) from
    their default expression on update and ignores what the answers file
    recorded; only `--data` overrides that. So a project that switched a
    module off would get it back on every plain `copier update` (observed on
    the reference project: the disabled git-hooks module returned, with a
    conflicting anchor). Re-asserting the recorded answers as --data is what
    makes the recorded state actually win."""
    text = (root / ANSWERS).read_text(encoding="utf-8")
    src = commit = None
    data: dict[str, str] = {}
    try:
        import yaml  # copier's own dependency; present wherever copier runs
        loaded = yaml.safe_load(text) or {}
        for key, value in loaded.items():
            if key == "_src_path":
                src = str(value)
            elif key == "_commit":
                commit = str(value)
            elif not str(key).startswith("_"):
                dumped = yaml.safe_dump(value, default_flow_style=True,
                                        width=10 ** 6).strip()
                if dumped.endswith("..."):  # scalar document end marker
                    dumped = dumped[:-3].strip()
                data[str(key)] = dumped
    except ImportError:  # single-line entries only; multi-line values are skipped
        for line in text.splitlines():
            if line.startswith("_src_path:"):
                src = line.split(":", 1)[1].strip()
            elif line.startswith("_commit:"):
                commit = line.split(":", 1)[1].strip()
            elif line and not line.startswith(("_", " ", "#")) and ":" in line:
                key, value = line.split(":", 1)
                if value.strip():
                    data[key.strip()] = value.strip()
    return src, commit, data


def _data_args(data: dict[str, str]) -> list[str]:
    return [arg for key, value in data.items() for arg in ("--data", f"{key}={value}")]


def _copier(*args: str) -> subprocess.CompletedProcess:
    exe = shutil.which("copier")
    argv = [exe, *args] if exe else ["uvx", "copier", *args]
    return subprocess.run(argv, capture_output=True, text=True)


def render(src: str, ref: str, data: dict[str, str], dst: Path) -> bool:
    r = _copier("copy", "--trust", "--defaults", "-r", ref, *_data_args(data),
                "--quiet", src, str(dst))
    if r.returncode != 0:
        print(f"template-update: render of {ref} failed:\n{r.stderr.strip()}",
              file=sys.stderr)
        return False
    return True


def write_deltas(old: Path, new: Path, owned: list[str], out_dir: Path,
                 root: Path) -> list[str]:
    """One unified diff per owned file whose TEMPLATE render changed."""
    changed: list[str] = []
    for p in sorted(new.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(new).as_posix()
        if not is_owned(rel, owned):
            continue
        old_text = (old / rel).read_text(encoding="utf-8", errors="replace") \
            if (old / rel).is_file() else ""
        new_text = p.read_text(encoding="utf-8", errors="replace")
        if old_text == new_text:
            continue
        diff = difflib.unified_diff(old_text.splitlines(keepends=True),
                                    new_text.splitlines(keepends=True),
                                    fromfile=f"template-old/{rel}",
                                    tofile=f"template-new/{rel}")
        target = out_dir / f"{rel}.diff"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("".join(diff), encoding="utf-8")
        changed.append(rel)
    return changed


def restore_owned(root: Path, owned: list[str]) -> list[str]:
    """Put every owned tracked file back to HEAD; returns what was restored."""
    ls = subprocess.run(["git", "-C", str(root), "ls-files"], capture_output=True,
                        text=True)
    restored: list[str] = []
    for rel in ls.stdout.splitlines():
        if is_owned(rel, owned):
            subprocess.run(["git", "-C", str(root), "checkout", "HEAD", "--", rel],
                           capture_output=True)
            restored.append(rel)
    return restored


def leftover_conflicts(root: Path, owned: list[str]) -> list[str]:
    st = subprocess.run(["git", "-C", str(root), "status", "--porcelain"],
                        capture_output=True, text=True)
    hits: list[str] = []
    for line in st.stdout.splitlines():
        rel = line[3:].strip()
        p = root / rel
        if p.is_file() and not is_owned(rel, owned):
            try:
                if MARKER.search(p.read_text(encoding="utf-8", errors="replace")):
                    hits.append(rel)
            except OSError:
                pass
    return hits


def main() -> int:
    args = sys.argv[1:]
    ref: str | None = None
    if "--ref" in args:
        i = args.index("--ref")
        ref = args[i + 1]
        del args[i:i + 2]
    dry = "--dry-run" in args
    positional = [a for a in args if not a.startswith("--")]
    root = Path(positional[0] if positional else ".").resolve()
    owned = owned_patterns(root)
    src, old_ref, data = answers(root)
    if not src or not old_ref:
        print(f"template-update: {ANSWERS} lacks _src_path/_commit", file=sys.stderr)
        return 2
    if subprocess.run(["git", "-C", str(root), "status", "--porcelain"],
                      capture_output=True, text=True).stdout.strip():
        print("template-update: worktree not clean — commit or stash first",
              file=sys.stderr)
        return 2
    print(f"template-update: {len(owned)} owned pattern(s) from {OWNED_FILE}; "
          f"from {old_ref} to {ref or 'latest release'}")
    if dry:
        return 0
    upd = _copier("update", "--trust", "--defaults", "--conflict", "inline",
                  *_data_args(data), *(["-r", ref] if ref else []), str(root))
    if upd.returncode != 0:
        print(upd.stderr.strip(), file=sys.stderr)
        return 1
    _src, new_ref, _d = answers(root)
    new_ref = new_ref or ref or "HEAD"
    restored = restore_owned(root, owned)
    with tempfile.TemporaryDirectory() as tmp:
        old_dir, new_dir = Path(tmp) / "old", Path(tmp) / "new"
        if not (render(src, old_ref, data, old_dir) and
                render(src, new_ref, data, new_dir)):
            print("template-update: could not render both releases — owned files "
                  "were restored, but no delta was written; port by hand from "
                  "the template's CHANGELOG", file=sys.stderr)
            return 1
        out_dir = root / DELTA_DIR / new_ref
        changed = write_deltas(old_dir, new_dir, owned, out_dir, root)
    print(f"template-update: updated to {new_ref}; {len(restored)} owned file(s) "
          f"kept as committed")
    if changed:
        print(f"template-update: the template changed {len(changed)} owned file(s) "
              f"— port by hand from {DELTA_DIR}/{new_ref}/:")
        for rel in changed:
            print(f"  - {rel}")
    else:
        print("template-update: no owned file changed in the template")
    for rel in leftover_conflicts(root, owned):
        print(f"template-update: conflict markers left in {rel} — resolve before "
              f"committing")
    print(f"template-update: {DELTA_DIR}/ is working memory — delete it once "
          f"ported (it is not meant to be committed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
