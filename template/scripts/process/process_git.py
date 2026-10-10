"""Environment for git readers: judge the objects the push actually carries."""
import os
import subprocess
from pathlib import Path


def git_environment(extra=None):
    return {**(os.environ if extra is None else extra), "GIT_NO_REPLACE_OBJECTS": "1"}


class NoForkPoint(ValueError):
    """`base` and `tip` share no commit here (shallow clone, unrelated history)."""


def fork_point(root: Path, base: str, tip: str) -> str:
    """The one commit where `tip` forked from `base` — the one owner of that answer.

    Plain `git merge-base` silently picks one of several bases (a criss-cross
    merge); the pick decides the reviewed range and the template baseline, so
    exactly one is demanded. No base at all is named: a shallow clone or
    unrelated history, never an empty answer (ValueError either way)."""
    try:
        r = subprocess.run(['git', '-C', str(root), 'merge-base', '--all', base, tip],
                           capture_output=True, timeout=60, env=git_environment())
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError(f'git merge-base {base} {tip} failed ({type(exc).__name__})') from exc
    bases = r.stdout.decode(errors='replace').split()
    if r.returncode == 1 and not bases and not r.stderr.strip():
        raise NoForkPoint(f'no common ancestor of {base} and {tip} (shallow clone or '
                          'unrelated history); fetch the full history')
    if r.returncode:
        raise ValueError(r.stderr.decode(errors='replace').strip()
                         or f'git merge-base {base} {tip} failed ({r.returncode})')
    if len(bases) != 1:
        raise ValueError(f'{len(bases)} merge bases of {base} and {tip} ({", ".join(bases)}); '
                         'the fork point is ambiguous — rebase onto the integration branch')
    return bases[0]


def commit_of(root: Path, ref: str) -> str:
    """The commit `ref` names (`^0` peels a tag), '' when it names none."""
    r = subprocess.run(["git", "-C", str(root), "rev-parse", "--verify", "-q", ref + "^0"],
                       capture_output=True, text=True, env=git_environment())
    return r.stdout.strip() if r.returncode == 0 else ""


def pushed_commit_problem(root: Path, pushed: str) -> str | None:
    """Why a check of this checkout says nothing about the pushed commit, or
    None. The gates and the tests read the working tree, so the pushed commit
    must be HEAD (observed downstream: a shared checkout stood on another
    agent's branch while main was pushed, and the hook passed a tree it never
    saw). The gate runner and the pre-push frame ask here."""
    commit = commit_of(root, pushed) or pushed
    head = commit_of(root, "HEAD")
    if head and commit != head:
        return (f"the push carries {commit[:10]} but this checkout is at {head[:10]} — the "
                f"checks would read a tree that is not being pushed; push from the checkout "
                f"of that commit (its worktree)")
    return None


def path_captures(pattern: str, path: str) -> dict[str, str] | None:
    """`pattern` against a repo-relative posix `path`, segment by segment — the
    one glob of the process (test maps, pins, gate triggers): `*` and `{name}`
    match within one segment (`{name}` captures it), `**` any number of
    segments (a trailing `**` at least one), a trailing `/` everything below. Case-sensitive on every
    platform (`fnmatch.fnmatch` folds case on Windows). Captures, or None."""
    from fnmatch import fnmatchcase  # noqa: PLC0415

    if pattern.endswith("/"):
        pattern += "**"
    pat, parts = pattern.split("/"), path.split("/")

    def match(i: int, j: int, caps: dict[str, str]) -> dict[str, str] | None:
        if i == len(pat):
            return caps if j == len(parts) else None
        seg = pat[i]
        if seg == "**":
            # a trailing `**` is everything *inside* (gitignore's `dir/**`): at
            # least one segment; inside a pattern it may stand for none
            first = j + 1 if i == len(pat) - 1 else j
            for k in range(first, len(parts) + 1):
                found = match(i + 1, k, caps)
                if found is not None:
                    return found
            return None
        if j == len(parts):
            return None
        if len(seg) > 2 and seg[0] == "{" and seg[-1] == "}" and seg[1:-1].isidentifier():
            name = seg[1:-1]
            if name in caps and caps[name] != parts[j]:
                return None
            return match(i + 1, j + 1, {**caps, name: parts[j]})
        if not fnmatchcase(parts[j], seg):
            return None
        return match(i + 1, j + 1, caps)

    return match(0, 0, {})


def path_matches(pattern: str, path: str) -> bool:
    return path_captures(pattern, path) is not None
