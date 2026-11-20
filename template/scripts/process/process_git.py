"""Environment for git readers: judge the objects the push actually carries."""
import math
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import NamedTuple

# `Regression-of: #N` (commits.md): a fix names the issue whose merged change
# it repairs. One grammar for both readers — the train must not take #N for
# an issue of the fix's branch, the telemetry flow counts it as an escape of
# #N. Only a well-formed trailer line counts: refs and commas, nothing else.
# One reader of "is this a release": a bare ref (`v1.2.3`, `1.2.3`) or the
# `_commit:` line of `.copier-answers.yml`. A SHA, `vX.Y.Z.postN…` or
# `vX.Y.Z-N-g<sha>` is no release — unknown, never an old version.
_RELEASE = r"v?(\d+)\.(\d+)\.(\d+)"
_RELEASE_REF = re.compile(rf"^{_RELEASE}$")
_RELEASE_LINE = re.compile(rf"^_commit:[ \t]*['\"]?{_RELEASE}['\"]?[ \t]*$", re.MULTILINE)


def release_of(ref: str | None) -> tuple[int, int, int] | None:
    """(major, minor, patch) when `ref` names a release, else None."""
    m = _RELEASE_REF.match((ref or "").strip())
    return (int(m[1]), int(m[2]), int(m[3])) if m else None


def answers_release(text: str) -> tuple[int, int, int] | None:
    """The release `.copier-answers.yml` text names in `_commit`, else None."""
    m = _RELEASE_LINE.search(text or "")
    return (int(m[1]), int(m[2]), int(m[3])) if m else None


_REF = r"(?:#\d+|[\w.-]+/[\w.-]+#\d+)"
REGRESSION_TRAILER = re.compile(rf"(?im)^[ \t]*Regression-of:[ \t]*({_REF}(?:[ \t]*,[ \t]*{_REF})*)[ \t]*$")


# any line that opens with the key: the train never takes what it names for an
# issue of the branch, well-formed or not (a near miss must not misfile the merge)
REGRESSION_LINE = re.compile(r"(?im)^[ \t]*Regression-of:.*$")


def regression_refs(body: str) -> list[int]:
    """The issue numbers a commit message's `Regression-of:` trailers name."""
    return [int(n) for m in REGRESSION_TRAILER.finditer(body) for n in re.findall(r"#(\d+)", m.group(1))]


# --- the disk (v2.98 B1): one reader for dispatch's start and the train -------------------
DISK_LIMIT_PCT = 90  # a filesystem this full refuses a start (dispatch) and halts the train
DISK_LIMIT_ENV = "PROCESS_DISK_LIMIT_PCT"
CLEANUP_CMD = "python3 scripts/process/tidy.py --apply"
# the abort-marker line of a full disk (train.md, "Red, undefined, aborted"): `disk-full <path> <use>%`
DISK_FULL = "disk-full"


class DiskUse(NamedTuple):
    """What `disk_use` read: the use in percent (None: not read), and why not (`problem`: a
    misconfigured limit — then `limit` is None — or a use that could not be read)."""
    use_pct: float | None
    problem: str | None
    limit: float | None = None
    free: int | None = None

    @property
    def full(self) -> bool:
        """At or over the limit. A problem is never full: a guard that cannot read is a note."""
        return self.use_pct is not None and self.limit is not None and self.use_pct >= self.limit


def disk_use(path: Path, *, fallback: bool = False) -> DiskUse:
    """The use of the filesystem holding `path` (used / (used + available), as `df` counts
    it) and the limit (`PROCESS_DISK_LIMIT_PCT`, default 90). A limit that is no percentage
    in (0, 100] is a problem, neither silently off nor silently the default: without
    `fallback` (dispatch refuses on it) `limit` is None and nothing is read; with it (the
    train, which must not stop checking) the use is read against the default, the problem
    still named."""
    raw = os.environ.get(DISK_LIMIT_ENV, "").strip()
    try:
        limit = float(raw) if raw else float(DISK_LIMIT_PCT)
    except ValueError:
        limit = math.nan
    misconfigured = None
    if not (math.isfinite(limit) and 0 < limit <= 100):
        misconfigured = (f"{DISK_LIMIT_ENV}={raw!r} is no percentage in (0, 100] — fix or unset it "
                         f"(default {DISK_LIMIT_PCT})")
        if not fallback:
            return DiskUse(None, misconfigured)
        limit = float(DISK_LIMIT_PCT)
    try:
        u = shutil.disk_usage(path)
    except OSError as exc:
        return DiskUse(None, f"disk use of {path} not checked: {exc}", limit)
    if u.used + u.free <= 0:
        return DiskUse(None, misconfigured, limit, u.free)
    return DiskUse(100.0 * u.used / (u.used + u.free), misconfigured, limit, u.free)


def disk_full_line(path: Path, use_pct: float) -> str:
    """`disk-full <path> <use>%`: the reason of a train that halts and the marker line of a
    refused start — one grammar, counted by its first two words (`train-phases`)."""
    return f"{DISK_FULL} {path} {use_pct:.0f}%"


def is_disk_full_line(line: str) -> bool:
    return line.split(maxsplit=1)[:1] == [DISK_FULL]


# the abort marker of the train's suite run (train.py, `docs/process/train.md`, "Red,
# undefined, aborted"): a writer inside the run marks it aborted, not red
SUITE_ABORT_ENV = "PROCESS_SUITE_ABORT"


def note_suite_abort(line: str) -> None:
    """Append `line` (its line breaks made spaces) to the train's abort marker, when
    `PROCESS_SUITE_ABORT` is set — the one writer, for lane.py (`lane-busy …`) and dispatch
    (`disk-full …`): one `os.write`, append only, never creating the file (a marker the
    train has removed stays gone), never blocking (a FIFO nobody reads). A failure to write
    changes nothing."""
    path = os.environ.get(SUITE_ABORT_ENV)
    if not path:
        return
    try:
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    except (OSError, ValueError):
        return
    try:
        os.write(fd, f"{' '.join(line.splitlines())}\n".encode("utf-8", "replace"))
    except OSError:
        pass
    finally:
        os.close(fd)


def git_environment(extra=None):
    return {**(os.environ if extra is None else extra), "GIT_NO_REPLACE_OBJECTS": "1"}


# `git rev-parse --local-env-vars` of git 2.43, for a git that cannot answer
LOCAL_ENV_VARS = ('GIT_ALTERNATE_OBJECT_DIRECTORIES', 'GIT_CONFIG', 'GIT_CONFIG_PARAMETERS',
                  'GIT_CONFIG_COUNT', 'GIT_OBJECT_DIRECTORY', 'GIT_DIR', 'GIT_WORK_TREE',
                  'GIT_IMPLICIT_WORK_TREE', 'GIT_GRAFT_FILE', 'GIT_INDEX_FILE', 'GIT_NO_REPLACE_OBJECTS',
                  'GIT_REPLACE_REF_BASE', 'GIT_PREFIX', 'GIT_SHALLOW_FILE', 'GIT_COMMON_DIR')


def local_env_vars() -> tuple[str, ...]:
    """The variables that bind a git process to one repository — git sets them
    for its hooks; a child that builds its own repo must not inherit them."""
    try:
        r = subprocess.run(['git', 'rev-parse', '--local-env-vars'], capture_output=True, text=True,
                           timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return LOCAL_ENV_VARS
    names = tuple(r.stdout.split())
    return names if r.returncode == 0 and names else LOCAL_ENV_VARS


# config handed down through the environment (`git -c`, `GIT_CONFIG_COUNT`):
# git keeps it for a child in another repository (prepare_other_repo_env), and
# containers inject credentials, URL rewrites and safe.directory this way
KEPT_CONFIG_VARS = ('GIT_CONFIG_PARAMETERS', 'GIT_CONFIG_COUNT')


def drop_local_env(*envs) -> None:
    """Removes git's repo-local variables from each environment in place: the
    one owner of what a hook's children must not see (#219). A child still
    finds the repo through its cwd. Config passed by environment stays, as
    git itself keeps it."""
    names = [n for n in local_env_vars() if n not in KEPT_CONFIG_VARS]
    for env in envs:
        for name in names:
            env.pop(name, None)


def git_ignored(root: Path, rels: list[str]) -> set[str] | None:
    """The subset of `rels` (paths relative to `root`) git ignores — the one owner of that
    question for the gates and the bundle (#421). None: git cannot tell (no git, no
    repository, an error, 60 s passed); each caller decides what that means for it."""
    if not rels:
        return set()
    try:
        r = subprocess.run(["git", "-C", str(root), "check-ignore", "-z", "--stdin"],
                           input="".join(f"{rel}\0" for rel in rels).encode(errors="surrogateescape"),
                           capture_output=True, timeout=60, check=False, env=git_environment())
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode > 1:  # 0: some ignored, 1: none, 128: no repository or an error
        return None
    return {rel for rel in r.stdout.decode(errors="surrogateescape").split("\0") if rel}


class GitReadError(RuntimeError):
    """A git read a gate cannot do without failed. `check_review` re-exports it: every
    gate catches it from there."""


class GitUnavailable(GitReadError, ValueError):
    """git cannot run here at all (#430): no git on PATH, a timeout, a repository git
    refuses (dubious ownership), a stale worktree `.git` file, a `GIT_DIR` that names
    nothing. Never "no base": read as one, every gate went green with a note. A
    ValueError too, as `fork_point` raised one before; a caller that tells ambiguity
    from this catches it first."""


def git_cannot_run(detail: str) -> GitUnavailable:
    """The one wording of #430: `git cannot run (<detail>)`."""
    return GitUnavailable(f"git cannot run ({detail})")


def start_failure(command: str, exc: BaseException) -> GitUnavailable:
    """GitUnavailable for `git <command>` that did not start (OSError) or timed out."""
    if isinstance(exc, subprocess.TimeoutExpired):
        return git_cannot_run(f"git {command} timed out after {exc.timeout:g}s")
    return git_cannot_run(f"git {command}: {type(exc).__name__}: {exc}")


# git's answer when it searched upward from the directory and found no repository: the
# one harmless failure (a rendered tree that is no clone). A path after "not a git
# repository:" (a stale `.git` file, a missing GIT_DIR) is a broken repository.
_SEARCHED_UP = ("not a git repository (or any of the parent directories)",
                "not a git repository (or any parent up to mount point")
_IN_REPO: set[str] = set()


def repo_probe(root: Path) -> bool:
    """Is `root` in a git repository git can read? The one probe of #430, asked by the
    gate runner at its entry and by the base search (`check_review`) before it reads.

    True: a repository — kept per root for the run. False: no repository, only when
    `root/.git` does not exist and git says it searched the parent directories (today's
    path: no range, a note). Anything else raises GitUnavailable, and is never kept: an
    OSError or a timeout, dubious ownership, a stale worktree `.git` file, `GIT_DIR` on
    a missing directory, an empty or broken `.git`."""
    key = os.path.abspath(root)
    if key in _IN_REPO:
        return True
    try:
        r = subprocess.run(["git", "-C", key, "rev-parse", "--git-dir"], capture_output=True,
                           timeout=60, env=git_environment({**os.environ, "LC_ALL": "C"}), check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise start_failure("rev-parse --git-dir", exc) from exc
    if r.returncode == 0:
        _IN_REPO.add(key)
        return True
    said = " ".join(r.stderr.decode(errors="replace").split())
    if not os.path.lexists(os.path.join(key, ".git")) and any(s in said for s in _SEARCHED_UP):
        return False
    raise git_cannot_run(said or f"git rev-parse --git-dir exit {r.returncode}")


class NoForkPoint(ValueError):
    """`base` and `tip` share no commit here (shallow clone, unrelated history)."""


def fork_point(root: Path, base: str, tip: str) -> str:
    """The one commit where `tip` forked from `base` — the one owner of that answer.

    Plain `git merge-base` silently picks one of several bases (a criss-cross
    merge); the pick decides the reviewed range and the template baseline, so
    exactly one is demanded. No base at all is named: a shallow clone or
    unrelated history, never an empty answer (ValueError either way). git that cannot
    run is GitUnavailable (#430), no ambiguity: the base search must not skip it."""
    try:
        r = subprocess.run(['git', '-C', str(root), 'merge-base', '--all', base, tip],
                           capture_output=True, timeout=60, env=git_environment())
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise start_failure(f'merge-base {base} {tip}', exc) from exc
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
