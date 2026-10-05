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
