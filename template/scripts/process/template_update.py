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

Pure stdlib plus the `copier` CLI on PATH (uvx copier works). The two extra
renders cost seconds; the manual port they replace cost an hour.

Usage: template_update.py [root] [--ref <tag-or-sha>] [--dry-run]
"""
from __future__ import annotations

import fnmatch
import difflib
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


def answers(root: Path) -> tuple[str | None, str | None, str]:
    """(src_path, commit, data-yaml-without-underscore-keys)."""
    text = (root / ANSWERS).read_text(encoding="utf-8")
    src = commit = None
    data_lines: list[str] = []
    for line in text.splitlines():
        if line.startswith("_src_path:"):
            src = line.split(":", 1)[1].strip()
        elif line.startswith("_commit:"):
            commit = line.split(":", 1)[1].strip()
        elif line.startswith("_"):
            continue
        else:
            data_lines.append(line)
    return src, commit, "\n".join(data_lines) + "\n"


def _copier(*args: str) -> subprocess.CompletedProcess:
    exe = shutil.which("copier")
    argv = [exe, *args] if exe else ["uvx", "copier", *args]
    return subprocess.run(argv, capture_output=True, text=True)


def render(src: str, ref: str, data_yaml: str, dst: Path) -> bool:
    with tempfile.NamedTemporaryFile("w", suffix=".yml", delete=False) as fh:
        fh.write(data_yaml)
        data_file = fh.name
    r = _copier("copy", "--trust", "--defaults", "-r", ref, "--data-file",
                data_file, "--quiet", src, str(dst))
    Path(data_file).unlink(missing_ok=True)
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
    src, old_ref, data_yaml = answers(root)
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
                  *(["-r", ref] if ref else []), str(root))
    if upd.returncode != 0:
        print(upd.stderr.strip(), file=sys.stderr)
        return 1
    _src, new_ref, _d = answers(root)
    new_ref = new_ref or ref or "HEAD"
    restored = restore_owned(root, owned)
    with tempfile.TemporaryDirectory() as tmp:
        old_dir, new_dir = Path(tmp) / "old", Path(tmp) / "new"
        if not (render(src, old_ref, data_yaml, old_dir) and
                render(src, new_ref, data_yaml, new_dir)):
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
