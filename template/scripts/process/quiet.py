#!/usr/bin/env python3
"""Quiet ranges (#366) — one owner for "this change needs no test run".

A range is quiet when every path in it, on both sides of every rename, is
bookkeeping (`.process-work/`) or inert. A quiet range runs the gates and no
suite: on the merge push, and in `finish --apply` without `--tests`. The
certificate is not touched — it stays on the full tree.

A path is inert only when all four hold:

  1. its file type is media or prose (`INERT_SUFFIXES`) — never a build file,
     a script, a config or a lockfile; a list of excluded names stayed
     incomplete for three review rounds, a list of allowed types does not;
  2. the area `inert` in `testing.local.json` names it **as the integration
     branch has the file** — a branch never declares itself inert; no
     integration ref, an unreadable or broken file there: nothing is inert;
  3. it is not protected (`is_protected_path`): gate code, everything under
     `docs/process/`, `.claude/`, `.github/`, `.specify/`, the copier answers;
  4. it is no test input: no glob of a stack (`paths`, `tests`, pin subjects,
     map sources and targets) matches it and it lies under no pin target —
     in the working tree's configuration or the integration branch's.

  quiet.py [ROOT] [BASE..HEAD]

prints every path with its class and exits 0 only for a quiet range — the
entry for projects whose own pre-push hook decides about the suite. Without a
range it judges what the branch changes since its fork. Stdlib only.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_review import BOOKKEEPING, GitReadError, is_gate_path  # noqa: E402
from process_git import path_matches  # noqa: E402

import testing_config  # noqa: E402

INERT_SUFFIXES = frozenset({
    # images
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".avif", ".svg", ".ico", ".bmp", ".tif", ".tiff",
    ".heic",
    # audio and video
    ".mp3", ".wav", ".ogg", ".m4a", ".mp4", ".mov", ".webm",
    # documents and prose
    ".pdf", ".md", ".txt", ".rst", ".adoc",
})
PROTECTED_PATHS = ("docs/process/", ".claude/", ".github/", ".specify/")
PROTECTED_FILES = (".copier-answers.yml",)

BOOKKEEPING_CLASS = "bookkeeping"
INERT_CLASS = "inert"


def is_protected_path(rel: str) -> bool:
    """Never inert, whatever `inert` names: what runs, configures or reviews the process."""
    return is_gate_path(rel) or rel.startswith(PROTECTED_PATHS) or rel in PROTECTED_FILES


def inert_type(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    return "." in name and name[name.rindex("."):].lower() in INERT_SUFFIXES


def _under(rel: str, target: str) -> bool:
    target = target.rstrip("/")
    return bool(target) and (rel == target or rel.startswith(target + "/"))


def _fixed_prefix(template: str) -> str:
    """The leading segments of a map target before its first placeholder or wildcard."""
    out = []
    for seg in template.split("/"):
        if any(c in seg for c in "{*?["):
            break
        out.append(seg)
    return "/".join(out)


def test_input_of(cfg: dict, rel: str) -> str | None:
    """The stack whose tests may read `rel`, by the configuration alone."""
    for stack in cfg["stacks"]:
        globs = [*stack["paths"], *stack["tests"], *stack["pins"], *(m["from"] for m in stack["map"])]
        if any(rel == g or path_matches(g, rel) for g in globs):
            return stack["name"]
        if any(_under(rel, t) for targets in stack["pins"].values() for t in targets):
            return stack["name"]
        for entry in stack["map"]:
            for target in entry["to"]:
                if path_matches(target, rel) or _under(rel, _fixed_prefix(target)):
                    return stack["name"]
    return None


def _ref(root: Path, tip: str) -> tuple[str | None, str | None]:
    """(integration ref, why there is none)."""
    from check_review import integration_ref  # noqa: PLC0415

    try:
        ref = integration_ref(root, tip)
    except GitReadError as exc:
        return None, f"the integration branch cannot be read ({exc})"
    return (ref, None) if ref else (None, "no integration branch to read `inert` from")


def classify(root: Path, paths: set[str] | list[str], tip: str = "HEAD") -> dict[str, str]:
    """path → `bookkeeping`, `inert`, or why it is code. Every doubt is code."""
    paths = sorted(set(paths))
    out: dict[str, str] = {}
    candidates = []
    for rel in paths:
        if rel.startswith(BOOKKEEPING):
            out[rel] = BOOKKEEPING_CLASS
        elif not inert_type(rel):
            out[rel] = "code"
        else:
            candidates.append(rel)
    if not candidates:
        return out
    ref, why = _ref(root, tip)
    base = testing_config.config_at(root, ref) if ref else None
    tree = testing_config.config_at(root, None)
    if base is None and why is None:
        why = f"`{testing_config.CONFIG}` cannot be read on {ref}"
    if tree is None:
        why = why or f"`{testing_config.CONFIG}` cannot be read here"
    here = tree["areas"].get("inert", []) if tree else []
    for rel in candidates:
        named_here = any(path_matches(g, rel) for g in here)
        if why:
            # a reason only where this checkout names the path inert: elsewhere it is plain code
            out[rel] = f"code — {why}" if named_here else "code"
            continue
        if not any(path_matches(g, rel) for g in base["areas"].get("inert", [])):
            out[rel] = ("code — inert only on this branch, not yet on the integration branch"
                        if named_here else "code")
        elif is_protected_path(rel):
            out[rel] = "code — protected (process, gate or harness configuration)"
        elif (stack := test_input_of(tree, rel) or test_input_of(base, rel)):
            out[rel] = f"code — a test input of stack '{stack}'"
        else:
            out[rel] = INERT_CLASS
    return out


def is_quiet(classes: dict[str, str]) -> bool:
    """A classified range needs no test run: non-empty, every path bookkeeping or inert."""
    return bool(classes) and all(c in (BOOKKEEPING_CLASS, INERT_CLASS) for c in classes.values())


def quiet_paths(root: Path, paths: set[str] | list[str], tip: str = "HEAD") -> bool:
    return is_quiet(classify(root, paths, tip))


def report(classes: dict[str, str]) -> list[str]:
    """The lines a push or finish prints: the inert paths, and inert-looking ones that stay code."""
    inert = [p for p, c in classes.items() if c == INERT_CLASS]
    kept = [f"{p} ({c.removeprefix('code — ')})" for p, c in classes.items()
            if c.startswith("code — ")]
    lines = []
    if inert:
        lines.append(f"inert: {', '.join(inert)}")
    if kept:
        lines.append(f"not inert: {'; '.join(kept)}")
    return lines


def main(argv: list[str]) -> int:
    import test_select  # noqa: PLC0415

    rng = next((a for a in argv if ".." in a), None)
    rest = [a for a in argv if a != rng]
    root = Path(rest[0] if rest else ".").resolve()
    try:
        if rng:
            base, head = rng.split("..", 1)
            from check_review import paths_in_flight  # noqa: PLC0415

            paths = paths_in_flight(root, head or "HEAD", base=base, no_renames=True)
            if paths is None:
                print(f"quiet: git cannot list {rng} — not quiet")
                return 1
            tip = head or "HEAD"
        else:
            paths = test_select.changed_paths(root, None)
            tip = "HEAD"
    except test_select.Unjudgeable as exc:
        print(f"quiet: {exc} — not quiet")
        return 1
    classes = classify(root, paths, tip)
    for rel, c in classes.items():
        print(f"{c}\t{rel}")
    quiet = is_quiet(classes)
    print("quiet: the range needs no test run" if quiet else "quiet: not quiet — run the suite")
    return 0 if quiet else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
