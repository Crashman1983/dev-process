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

`--dry-run` changes nothing. From a clone of the template source it names the
`[required]` items of every release between the installed one and the target
(`changelog.py`) and the overlays whose anchored section the template changed
(`check_overlays.section_changes`) — the work an update brings, before it runs.
It names the last update, and with the mandate's `steering.kit_update_cadence_days`
whether the next is due: due now when a `[required]` change is pending, else by
the cadence.

Stdlib plus the `copier` CLI on PATH (uvx copier works; PyYAML, copier's
own dependency, is used when importable). The two extra
renders cost seconds; the manual port they replace cost an hour.

Usage: template_update.py [root] [--ref <tag-or-sha>] [--dry-run] | --verify …  (--help)
"""
from __future__ import annotations

import datetime as _dt
import difflib
import fnmatch
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True

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


def _migrate(loaded: dict) -> None:
    """Carry an older manifest across template changes that re-asserting it
    verbatim would undo.

    v2.27.0 retired the `regulated` question; `sbom` joined the standard set.
    Before, `sbom` was derived from `regulated` — `sbom: false` next to
    `regulated: false` was the default, not an opt-out, and re-asserting it
    would keep a standard install one gate short."""
    if "regulated" in loaded:
        regulated = loaded.pop("regulated")
        mods = loaded.get("modules")
        if isinstance(mods, dict) and regulated is False and mods.get("sbom") is False:
            mods["sbom"] = True


def answers(root: Path, *, migrate: bool = True) -> tuple[str | None, str | None, dict[str, str]]:
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
        if migrate:
            _migrate(loaded)
        for key, value in loaded.items():
            if key == "_src_path":
                src = str(value)
            elif key == "_commit":
                commit = str(value)
            elif not str(key).startswith("_"):
                if value is None:
                    continue
                if isinstance(value, str):
                    # copier takes --data for a str question literally: a YAML
                    # dump would wrap it in quotes, and every update would add
                    # another layer ('' ->  -> ...)
                    data[str(key)] = value
                    continue
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
                value = value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
                    value = value[1:-1]  # a quoted scalar: pass its content, not the quotes
                if value or line.rstrip().endswith(("''", '""')):
                    data[key.strip()] = value
    return src, commit, data


# The template sources a render or clone may name. `_src_path` is read from
# the project's answers file: a value like `--upload-pack=<cmd>` would reach
# git or Copier as an option, and `ext::<cmd>` runs a transport helper. Every
# accepted form starts with a word character (or is an absolute path; the
# path of the scp form may start with `~` or `/`, never `-`), `::`
# is refused anywhere, and the argv puts `--` before it besides.
_REMOTE_SOURCE = re.compile(
    r"(?:gh:\w[\w.-]*/\w[\w.-]*"
    r"|(?:https|ssh)://\w[\w.@:~-]*(?:/[\w.~%+-]+)*/?"
    r"|\w[\w.-]*@\w[\w.-]*:[\w~/][\w.~%+/-]*)\Z")  # scp form: `:~/r`, `:/abs` too


def template_source(src: str) -> str:
    """`src` when it is a supported template source; ValueError otherwise."""
    # a local path is absolute (an unreachable one is reported as offline, by
    # name): a relative one would resolve against wherever the gate runs
    if "::" not in src and (_REMOTE_SOURCE.match(src) or Path(src).is_absolute()):
        return src
    raise ValueError(f"unsupported template source {src!r}: expected gh:<owner>/<repo>, "
                     "https://, ssh://, git@<host>:<path> or an absolute local path")


def _data_args(data: dict[str, str]) -> list[str]:
    return [arg for key, value in data.items() for arg in ("--data", f"{key}={value}")]


def _copier(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    exe = shutil.which("copier")
    if exe:
        argv = [exe, *args]
    elif shutil.which("uvx"):
        argv = ["uvx", "copier", *args]
    else:
        # named, not a FileNotFoundError traceback: no render, no exemption
        raise ValueError("copier required: install copier or uv (uvx)")
    return subprocess.run(argv, capture_output=True, text=True, timeout=120, env=env)


def render(src: str, ref: str, data: dict[str, str], dst: Path, *, trusted: bool = True) -> bool:
    # Explicit updates retain operator-approved tasks/extensions. Automatic
    # provenance must neither run tasks nor inherit local Copier trust/defaults.
    try:
        template_source(src)
    except ValueError as exc:
        print(f"template-update: {exc}", file=sys.stderr)
        return False
    with tempfile.TemporaryDirectory(prefix="copier-settings-") as temp:
        settings = Path(temp) / "settings.yml"
        settings.write_text("{}\n", encoding="utf-8")
        env = None
        flags = ["--trust"] if trusted else ["--skip-tasks"]
        if not trusted:
            from process_git import git_environment
            env = git_environment()
            env["COPIER_SETTINGS_PATH"] = str(settings)
        r = _copier("copy", *flags, "--defaults", "-r", ref, *_data_args(data),
                    "--quiet", "--", src, str(dst), env=env)
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
    # -z: a quoted non-ASCII name matched no owned pattern and was not restored,
    # so the update overwrote a file the project owns
    ls = subprocess.run(["git", "-C", str(root), "ls-files", "-z"], capture_output=True)
    restored: list[str] = []
    for rel in (n for n in ls.stdout.decode(errors="surrogateescape").split("\0") if n):
        if is_owned(rel, owned):
            subprocess.run(["git", "-C", str(root), "checkout", "HEAD", "--", rel],
                           capture_output=True)
            restored.append(rel)
    return restored


def leftover_conflicts(root: Path, owned: list[str]) -> list[str]:
    # -z: a quoted name named no file, and its conflict markers went unseen.
    # Entries are "XY path"; a rename or copy is followed by its old name.
    st = subprocess.run(["git", "-C", str(root), "status", "--porcelain", "-z"],
                        capture_output=True)
    entries = iter(st.stdout.decode(errors="surrogateescape").split("\0"))
    hits: list[str] = []
    for entry in entries:
        if len(entry) < 4:
            continue
        rel = entry[3:]
        if {"R", "C"} & set(entry[:2]):
            next(entries, None)  # the old name (a rename in either column)
        p = root / rel
        if p.is_file() and not is_owned(rel, owned):
            try:
                if MARKER.search(p.read_text(encoding="utf-8", errors="replace")):
                    hits.append(rel)
            except OSError:
                pass
    return hits


# a template path names its rendered file once `{% if … %}name{% endif %}` reads `name`
# and `.jinja` is gone — how an overlay's `overlay-of:` path finds its source file
_JINJA_IF = re.compile(r"\{%-?\s*if\b[^%]*%\}(.*?)\{%-?\s*endif\s*-?%\}")
_SUBDIRECTORY = re.compile(r"^_subdirectory:[ \t]*['\"]?([^'\"\s#]+)", re.MULTILINE)
MARKED_SINCE = (2, 96, 0)  # the release notes carry their marks from this release on


def rendered_path(source_rel: str) -> str:
    return _JINJA_IF.sub(r"\1", source_rel).removesuffix(".jinja")


def _bare_read(clone: Path, *args: str) -> bytes:
    from process_git import git_environment  # noqa: PLC0415
    from template_verify import _bare  # noqa: PLC0415
    r = subprocess.run([*_bare(clone), *args], capture_output=True, timeout=120, env=git_environment())
    if r.returncode:
        raise ValueError(r.stderr.decode(errors="replace").strip() or f"git {args[0]} failed")
    return r.stdout


def _blob(clone: Path, sha: str, rel: str) -> str | None:
    """The file at `sha`, None when it is not there; the blob-less clone fetches just it."""
    try:
        return _bare_read(clone, "cat-file", "blob", f"{sha}:{rel}").decode("utf-8", errors="replace")
    except ValueError:
        return None


def _source_files(clone: Path, sha: str) -> dict[str, str]:
    """Rendered path -> template source path at `sha`, below copier's `_subdirectory`."""
    config = _blob(clone, sha, "copier.yml") or _blob(clone, sha, "copier.yaml") or ""
    sub = _SUBDIRECTORY.search(config)
    prefix = sub.group(1).strip("/") + "/" if sub else ""
    out: dict[str, str] = {}
    for rel in _bare_read(clone, "ls-tree", "-r", "-z", "--name-only", sha).decode(
            errors="surrogateescape").split("\0"):
        if rel.startswith(prefix):
            out.setdefault(rendered_path(rel[len(prefix):]), rel)
    return out


def _latest_release(clone: Path) -> str | None:
    from process_git import release_of  # noqa: PLC0415
    tags = _bare_read(clone, "for-each-ref", "--format=%(refname:short)", "refs/tags").decode().split()
    released = [(release_of(t), t) for t in tags if t.startswith("v") and release_of(t)]
    return max(released)[1] if released else None


def _notes_lines(text: str, installed: tuple[int, int, int],
                 target: tuple[int, int, int]) -> tuple[list[str], bool | None]:
    """The lines for every release above `installed` up to `target`, and whether a
    `[required]` item is among them: True, False, or None when an unmarked item may be one."""
    from changelog import entries, marks  # noqa: PLC0415
    from process_git import release_of  # noqa: PLC0415
    lines = []
    required, unknown = False, False
    for version, title, body in entries(text):
        number = release_of(version)
        if number is None or not installed < number <= target:
            continue
        found = marks(body)
        graded = [m for m, _ in found if m]
        if not graded:
            before = " (before v2.96)" if number < MARKED_SINCE else ""
            lines.append(f"  {version} — {title}: not marked{before}")
            unknown = unknown or bool(found) or number < MARKED_SINCE
            continue
        counts = ", ".join(f"{graded.count(m)} {m}" for m in ("required", "recommended", "optional"))
        unmarked = len(found) - len(graded)
        unknown = unknown or bool(unmarked)
        lines.append(f"  {version} — {title}: {counts}" + (f", {unmarked} not marked" if unmarked else ""))
        required = required or "required" in graded
        lines += [f"    [required] {line}" for m, line in found if m == "required"]
    return lines, (True if required else None if unknown else False)


def _overlay_lines(root: Path, clone: Path, old_sha: str, new_sha: str) -> list[str]:
    """`overlay: section — changed|gone` for every anchored section the template changed
    between the two releases; only the overlays' own template files are fetched."""
    from check_overlays import anchored, section_changes  # noqa: PLC0415
    found = anchored(root)
    if not found:
        return []
    old_files, new_files = _source_files(clone, old_sha), _source_files(clone, new_sha)
    lines = []
    for overlay, target, headings in found:
        old_text = _blob(clone, old_sha, old_files[target]) if target in old_files else None
        if old_text is None:
            continue  # no template file at the installed release: nothing it built on moved
        new_text = _blob(clone, new_sha, new_files[target]) if target in new_files else None
        changes = section_changes(old_text, new_text or "")
        lines += [f"  {overlay}: {h} — {changes[h]}" for h in headings if h in changes]
    return lines


def release_report(root: Path, src: str, installed: str, ref: str | None) -> tuple[list[str], bool | None]:
    """What `--dry-run` says past its first line, read from a clone of the template
    source: the `[required]` items of every release above the installed one up to the
    target (`--ref`, else the highest `vN.N.N` tag) and the overlays whose anchored
    section changed; with it whether a `[required]` item is pending (None: the notes
    were not read). Never raises: unreadable is one line, and the dry run stays 0."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from process_git import release_of  # noqa: PLC0415
    import template_verify as tv  # noqa: PLC0415
    for name in (installed, ref):
        if name is not None and release_of(name) is None:
            return [f"template-update: release notes unreadable: {name} is no release"], None
    lines: list[str] = []
    required: bool | None = None
    try:
        clone = tv._clone(src, ref or "the latest release")
        target = ref or _latest_release(clone)
        if target is None:
            return ["template-update: release notes unreadable: the template source has no release tag"], None
        new_sha = tv._release(src, target)
        notes = _blob(clone, new_sha, "CHANGELOG.md")
        if notes is None:
            lines.append(f"template-update: release notes unreadable: no CHANGELOG.md at {target}")
        else:
            found, required = _notes_lines(notes, release_of(installed), release_of(target))
            lines.append(f"template-update: release notes from {installed} to {target}"
                         + (f" (CHANGELOG.md at {target}):" if found else ": no release in between"))
            lines += found
        changed = _overlay_lines(root, clone, tv._release(src, installed), new_sha)
        if changed:
            lines.append(f"template-update: overlays to re-check — the template changed the section "
                         f"between {installed} and {target}:")
            lines += changed
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        what = "overlays" if lines else "release notes and overlays"
        reason = str(exc).removesuffix(" — verification fails closed")  # template_verify's wording
        lines.append(f"template-update: {what} unreadable: {reason}")
    return lines, required


def last_update(root: Path) -> _dt.date | None:
    """The date of the last commit that changed `_commit` in the answers file: the last
    update (or the install). None when git names none."""
    r = subprocess.run(["git", "-C", str(root), "log", "-1", "--format=%cs", "-G", r"^_commit:",
                        "--", ANSWERS], capture_output=True, text=True)
    try:
        return _dt.date.fromisoformat(r.stdout.strip()) if r.returncode == 0 else None
    except ValueError:
        return None


def update_cadence(root: Path) -> tuple[int | None, str | None]:
    """(days, problem): `steering.kit_update_cadence_days` from the mandate; no key, no
    cadence. A wrong type is named and ignored, never guessed."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from optimize import load_mandate  # noqa: PLC0415 — stdlib-only sibling
    mandate, _problem = load_mandate(root)
    steering = (mandate or {}).get("steering")
    if not isinstance(steering, dict) or "kit_update_cadence_days" not in steering:
        return None, None
    days = steering["kit_update_cadence_days"]
    if isinstance(days, int) and not isinstance(days, bool) and days >= 1:
        return days, None
    return None, "steering.kit_update_cadence_days must be a positive integer — ignored"


def cadence_lines(root: Path, required: bool | None, today: _dt.date | None = None) -> list[str]:
    """The last update and, with the mandate's cadence, whether the next is due: a pending
    `[required]` change makes it due now; otherwise the cadence decides, and the update
    waits for the date only when the notes said no `[required]` change is pending."""
    last = last_update(root)
    lines = [f"template-update: last update {last.isoformat() if last else 'unknown'} "
             f"(the last commit that changed _commit in {ANSWERS})"]
    days, problem = update_cadence(root)
    if problem:
        return [*lines, f"template-update: {problem}"]
    if days is None:
        return lines
    head = f"template-update: cadence {days} days"
    if required:
        return [*lines, f"{head} — due now: a [required] change is pending"]
    if last is None:
        return [*lines, f"{head} — due: no last update to count from"]
    due = last + _dt.timedelta(days=days)
    if (today or _dt.date.today()) >= due:
        return [*lines, f"{head} — due (since {due.isoformat()})"]
    if required is None:
        return [*lines, f"{head} — defer until {due.isoformat()}; a [required] change may be pending "
                        "— the release notes did not say"]
    return [*lines, f"{head} — defer until {due.isoformat()}: no required change pending"]


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if "--verify" in args:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from template_verify import main as verify_main
        return verify_main([a for a in args if a != "--verify"])
    # argparse, so `--help` prints and an unknown argument is refused: hand-read
    # arguments let `--help` fall through to an update of the current checkout
    # (downstream: copier output landed in a foreign checkout)
    import argparse  # noqa: PLC0415
    ap = argparse.ArgumentParser(prog="template_update.py",
                                 description=__doc__.split("\n\n")[0].split(": ", 1)[-1])
    ap.add_argument("root", nargs="?", default=".", help="the project to update (default: the current directory)")
    ap.add_argument("--ref", help="the release tag or commit to update to (default: the latest release)")
    ap.add_argument("--dry-run", action="store_true", help="check and report the required items, the overlays to re-check and whether an update "
                         "is due; change nothing")
    ns = ap.parse_args(args)
    ref: str | None = ns.ref
    dry = ns.dry_run
    root = Path(ns.root).resolve()
    if not (root / ANSWERS).is_file():
        print(f"template-update: {root} has no {ANSWERS} — not a project rendered from this template; "
              "pass its root", file=sys.stderr)
        return 2
    owned = owned_patterns(root)
    src, old_ref, data = answers(root)
    if not src or not old_ref:
        print(f"template-update: {ANSWERS} lacks _src_path/_commit", file=sys.stderr)
        return 2
    try:  # the answers file is project data: an option or helper form never reaches copier
        template_source(src)
    except ValueError as exc:
        print(f"template-update: {exc}", file=sys.stderr)
        return 2
    if subprocess.run(["git", "-C", str(root), "status", "--porcelain"],
                      capture_output=True, text=True).stdout.strip():
        print("template-update: worktree not clean — commit or stash first",
              file=sys.stderr)
        return 2
    print(f"template-update: {len(owned)} owned pattern(s) from {OWNED_FILE}; "
          f"from {old_ref} to {ref or 'latest release'}")
    if ref is None and (".post" in old_ref or re.search(r"-\d+-g[0-9a-f]+$", old_ref)):
        # installed from a commit past the last tag: the latest release is older,
        # and copier refuses a downgrade — say so before anything runs
        print(f"template-update: {old_ref} is a commit past the last release; the "
              f"latest release would be a downgrade — pass --ref HEAD (or a newer tag)",
              file=sys.stderr)
        return 2
    if dry:
        lines, required = release_report(root, src, old_ref, ref)
        for line in lines + cadence_lines(root, required):
            print(line)
        return 0
    try:
        upd = _copier("update", "--trust", "--defaults", "--conflict", "inline",
                      *_data_args(data), *(["-r", ref] if ref else []), "--", str(root))
    except ValueError as exc:
        print(f"template-update: {exc}", file=sys.stderr)
        return 2
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
    # the project's overlays against the template it now has: a changed or removed
    # section an overlay builds on is a possible breaking change (docs/process/overlays.md)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from check_overlays import check as overlay_problems  # noqa: PLC0415
    for problem in overlay_problems(root):
        print(f"template-update: re-check an overlay — {problem}")
    print(f"template-update: {DELTA_DIR}/ is working memory — delete it once "
          f"ported (it is not meant to be committed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
