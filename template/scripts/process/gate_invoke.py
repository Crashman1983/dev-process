#!/usr/bin/env python3
"""How a gate gets launched — decided in one place instead of at every call.

Two launch-path failures were observed in production, both silent:

1. **A declaring script started with the wrong interpreter.** `gate_runner.py`
   declares its dependency (PyYAML) as PEP-723 script metadata. Only
   `uv run` resolves that declaration; an arbitrary interpreter does not carry
   it. A caller that launched the runner with `sys.executable` therefore
   succeeded on one host and failed to start on the next — and reported the
   failed start as a gate finding, sending the reader to look for a defect in
   their own branch instead of in the interpreter. The same happened one level
   down: the runner launched its children with `sys.executable`, the
   interpreter of its own ephemeral environment, in which only ITS declaration
   is resolved.

2. **Hook registrations that never ran.** With `core.hooksPath` set, git reads
   hooks from that directory and ignores `.git/hooks` — every pre-commit
   framework registration is inert, and nothing says so. Measured downstream:
   25 days without a single local gate run, discovered by accident.

Both are the same failure class: a check that is *missing* being reported as
*passed*. The rule this module enforces: a missing check is a blocker, never a
skip, and "not runnable" is reported distinctly from "red".

Pure stdlib, so the helper cannot inherit the dependency problem it solves.
"""
from __future__ import annotations

import functools
import os
import re
import shutil
import subprocess
import sys
from importlib import metadata
from importlib.util import find_spec, module_from_spec, spec_from_file_location
from pathlib import Path

RUNNER_REL = "scripts/process/gate_runner.py"
PRE_COMMIT_CONFIG = ".pre-commit-config.yaml"
GITHOOKS_DIR = ".githooks"
INSTALL_HOOKS_REL = "scripts/process/install_hooks.py"
# a project's own installer for tracked hooks, where it has one
PROJECT_INSTALLERS = ("scripts/install_hooks.sh", "scripts/install-hooks.sh")
_MAKE_HOOKS = re.compile(r"^hooks\s*:", re.MULTILINE)


def _tracked_hooks_installer(root: Path) -> str:
    """How THIS project points git at its tracked hooks: its own installer script, a
    `make hooks` target, or the plain git line — never an installer it does not have
    (downstream refute: a project with its own .githooks was told to run
    install_hooks.py, which only the git-hooks module ships)."""
    for rel in PROJECT_INSTALLERS:
        if (root / rel).is_file():
            return f"`bash {rel}`"
    makefile = root / "Makefile"
    try:
        if makefile.is_file() and _MAKE_HOOKS.search(makefile.read_text(encoding="utf-8")):
            return "`make hooks`"
    except (OSError, UnicodeDecodeError):
        pass
    return f"`git config core.hooksPath {GITHOOKS_DIR}`"


def _framework_install(root: Path) -> str:
    """pre-commit's install line, plus the merge guard where the module ships it."""
    line = "uvx pre-commit install --hook-type pre-commit --hook-type pre-push"
    if (root / INSTALL_HOOKS_REL).is_file():
        line += f" && python3 {INSTALL_HOOKS_REL}"
    return f"`{line}`"

# The PEP-723 block: `# /// script` … `# ///`, every line a comment.
_PEP723_BLOCK = re.compile(r"^# /// script\s*$(?P<body>.*?)^# ///\s*$",
                           re.MULTILINE | re.DOTALL)
INVALID = "invalid"  # a PEP-723 block uv would refuse
_QUOTED = re.compile(r'"([^"]*)"|\'([^\']*)\'')
_REQUIRES_PYTHON = re.compile(r"^#\s*requires-python\s*=\s*[\"']([^\"']*)[\"']", re.MULTILINE)
_DEPENDENCIES = re.compile(r"^#\s*dependencies\s*=\s*\[(?P<items>[^\]]*)\]",
                           re.MULTILINE | re.DOTALL)


def _pep723(path: Path) -> dict:
    """The PEP-723 block as a mapping; {} without one. Deliberately read as
    text, never by importing the script: an import could fail on exactly the
    missing dependency it is meant to check. `tomllib` (3.11+) parses it; an
    older interpreter falls back to the quoted strings of `dependencies`."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, ValueError):  # unreadable or not UTF-8: no declaration read
        return {}
    blocks = _PEP723_BLOCK.findall(text)
    block = _PEP723_BLOCK.search(text)
    if not block:
        return {}
    lines = block.group("body").strip("\n").splitlines()
    # uv's own rule: one block, every line `#` or `# …` — anything else uv
    # refuses, so it is never trusted for a direct start here either
    if len(blocks) > 1 or not all(ln == "#" or ln.startswith("# ") for ln in lines):
        return {INVALID: True}
    body = "\n".join(ln[2:] for ln in lines)
    try:
        import tomllib  # noqa: PLC0415 — stdlib from 3.11 only
    except ImportError:
        deps = _DEPENDENCIES.search(block.group("body"))
        found = [a or b for a, b in _QUOTED.findall(deps.group("items"))] if deps else []
        data: dict = {"dependencies": found}
        python = _REQUIRES_PYTHON.search(block.group("body"))
        if python:
            data["requires-python"] = python.group(1)
        return data
    try:
        data = tomllib.loads(body)
    except tomllib.TOMLDecodeError:
        return {INVALID: True}
    deps = data.get("dependencies", [])
    python = data.get("requires-python")
    if (not isinstance(deps, list) or not all(isinstance(d, str) for d in deps)
            or (python is not None and not isinstance(python, str))):
        return {INVALID: True}
    return data


def declared_dependencies(path: Path) -> list[str]:
    """The dependencies a script declares in its PEP-723 block; [] without one.
    Each entry is one requirement: `"pyyaml>=6,<7"` carries its own comma.
    The block itself is the truth — there is no list of declaring scripts to
    keep in sync."""
    deps = _pep723(path).get("dependencies", [])
    return [d for d in deps if isinstance(d, str) and d.strip()] if isinstance(deps, list) else []


def declared_python(path: Path) -> str | None:
    """The `requires-python` of a script's PEP-723 block, if it names one."""
    value = _pep723(path).get("requires-python")
    return value if isinstance(value, str) else None


_REQUIREMENT = re.compile(r"^\s*(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)\s*(?P<spec>[^\[;]*)$")
_CLAUSE = re.compile(r"^\s*(?P<op>>=|<=|==|!=|>|<)\s*(?P<version>[0-9]+(?:\.[0-9]+)*)\s*$")
_RELEASE = re.compile(r"^[0-9]+(?:\.[0-9]+)*$")


def _release(version: str) -> tuple[int, ...] | None:
    """A plain release version (`6.0.3`) as numbers; None for anything else —
    pre/post/dev releases, epochs, local labels — which this reader does not
    judge."""
    if not _RELEASE.match(version):
        return None
    try:
        return tuple(int(p) for p in version.split("."))
    except ValueError:
        return None


def _meets(have: tuple[int, ...], spec: str) -> bool:
    """Every clause of a specifier list holds, compared zero-padded
    (`6.0` == `6.0.0`); an operator outside >=, >, <=, <, ==, != (`~=`,
    `===`, wildcards) is unreadable and fails."""
    for clause in filter(None, (c.strip() for c in spec.split(","))):
        m = _CLAUSE.match(clause)
        if not m:
            return False
        try:
            want = tuple(int(p) for p in m.group("version").split("."))
        except ValueError:  # beyond int conversion limits: unreadable
            return False
        width = max(len(have), len(want))
        a, b = have + (0,) * (width - len(have)), want + (0,) * (width - len(want))
        if not {">=": a >= b, "<=": a <= b, "==": a == b, "!=": a != b,
                ">": a > b, "<": a < b}[m.group("op")]:
            return False
    return True


@functools.lru_cache(maxsize=1)
def _distribution_modules() -> dict:
    """packages_distributions(), read once per process: it scans every
    installed distribution, and a push asks for it once per gate."""
    return metadata.packages_distributions()


def _module_found(dist: str) -> bool:
    """At least one top-level module of the distribution can be found — a
    leftover dist-info without its package is not "installed"."""
    try:
        mapping = _distribution_modules()
    except Exception:  # noqa: BLE001 — unreadable metadata proves nothing
        return False
    wanted = re.sub(r"[-_.]+", "-", dist).lower()
    modules = sorted(mod for mod, dists in mapping.items()
                     if any(re.sub(r"[-_.]+", "-", d).lower() == wanted for d in dists))
    for mod in modules:
        try:
            if find_spec(mod) is not None:
                return True
        except (ImportError, ValueError):
            continue
    return False


def _satisfied(requirement: str) -> bool:
    """True only when THIS interpreter provably provides the requirement:
    installed, a plain release version every clause accepts, and a module
    that can be found. Extras, markers and whatever else this small reader
    cannot judge count as not provided — uv then decides, as before."""
    m = _REQUIREMENT.match(requirement)
    if not m:
        return False
    try:
        have = _release(metadata.version(m.group("name")))
    except Exception:  # noqa: BLE001 — not installed or broken metadata
        return False
    return have is not None and _meets(have, m.group("spec")) and _module_found(m.group("name"))


def _python_ok(requires: str | None) -> bool:
    if requires is None:
        return True
    return _meets(tuple(sys.version_info[:3]), requires)


def provides(script: Path) -> bool:
    """This interpreter provably carries the script's PEP-723 declaration:
    requires-python and every requirement (`_satisfied`)."""
    if _pep723(script).get(INVALID):
        return False
    return _python_ok(declared_python(script)) and all(
        _satisfied(d) for d in declared_dependencies(script))


def child_argv(root: Path, cmd: list[str]) -> list[str]:
    """argv for a child command of the shape `[interpreter, script, *args]`.

    A script with its own PEP-723 declaration runs through `uv run --script` —
    unless the interpreter it was given is this one and provably provides the
    child's own declaration — requires-python, every distribution in an
    accepted version, a findable module (the incident in point 1 above was a
    child started in an interpreter that lacked ITS declaration). Then it runs as given, with
    no package index needed: a sandbox that reaches GitHub but not PyPI ran
    no gate at all before (#365). Every other command is returned unchanged.
    Without `uv` on PATH the command also stays as given: that is the
    pre-existing behaviour — green on hosts with the dependency installed
    globally, the plain ImportError otherwise. Refusing here would disarm
    hosts on which the gates run today."""
    if len(cmd) < 2:
        return cmd
    script = root / cmd[1]
    # any PEP-723 block counts: one that names only requires-python is a
    # declaration too, and uv honours it
    if not _pep723(script) or not shutil.which("uv"):
        return cmd
    # compared as given, not resolved: a venv's python is a symlink to the base
    # interpreter but carries other packages
    if cmd[0] == sys.executable and provides(script):
        return cmd
    return ["uv", "run", "--script", str(script), *cmd[2:]]


# uv's own failure carries one of these; a gate's `error:` line alone does not
_UV_ERROR = re.compile(r"^\s*(?:×|Caused by:)", re.MULTILINE)
_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_IMPORT_FAILED = re.compile(r"^(?:ModuleNotFoundError|ImportError): ", re.MULTILINE)


def uv_launch_failure(argv: list[str], rc: int, stdout: str, stderr: str) -> str | None:
    """The diagnosis when a declaring gate most likely never ran its check: a
    non-zero exit, nothing on stdout, and either uv's own failure form on
    stderr (`×`, `Caused by:`; colour codes ignored) for a launch through
    `uv run`, or — for a direct start that `provides()` vouched for — an
    import failure. A script without a declaration, a gate's own `error:`
    line, any output and any other traceback are the gate's own red and left
    alone. The outcome never changes — this only names the likely cause."""
    if rc == 0 or stdout.strip():
        return None
    script = next((Path(a) for a in argv[1:] if a.endswith(".py")), None)
    declared = declared_dependencies(script) if script else []
    if not declared:  # a script without a declaration has no launch to blame
        return None
    deps = ", ".join(declared)
    plain = _ANSI.sub("", stderr)
    if argv[:2] == ["uv", "run"] and _UV_ERROR.search(plain):
        return (f"launched through `uv run` to provide {deps}; uv's error above "
                f"and no output: most likely uv failed before the script ran — a "
                f"launch problem, not a gate finding. Without access to the "
                f"package index, Python >= 3.11 with {deps} runs the gates "
                f"(docs/SYSTEM-REQUIREMENTS.md)")
    if argv[:1] == [sys.executable] and provides(script) and _IMPORT_FAILED.search(plain):
        return (f"started with this interpreter, whose metadata lists {deps}, but "
                f"an import failed (above) and there is no output: possibly an "
                f"installation in part — check the traceback; if it names a "
                f"module of {deps} or of their dependencies, repair or remove it "
                f"and uv provides the declaration")
    return None


def gate_runner_argv(root: Path) -> list[str] | None:
    """argv that resolves the runner's PEP-723 declaration — or None.

    None means "not runnable", not "gates red". Callers report the two cases
    distinctly (`not_runnable_reason`), otherwise the reader hunts the failure
    in their branch instead of in the interpreter.

    Order: an interpreter that provably carries the declaration first —
    `provides` asks the running interpreter, exactly the one that would be
    handed on as `sys.executable`, and it needs no network or cache — then
    `uv`, which resolves the declaration itself."""
    runner = root / RUNNER_REL
    if not runner.is_file():
        return None
    if provides(runner):
        return [sys.executable, str(runner)]
    if shutil.which("uv"):
        return ["uv", "run", str(runner)]
    return None


def not_runnable_reason(root: Path) -> str:
    """The one-line diagnosis for a `gate_runner_argv` of None."""
    runner = root / RUNNER_REL
    if not runner.is_file():
        return f"{RUNNER_REL} is missing from this checkout"
    deps = ", ".join(declared_dependencies(runner)) or "its declared dependencies"
    return (f"neither `uv` on PATH nor an interpreter carrying {deps} — "
            f"install uv (https://docs.astral.sh/uv/) or `pip install "
            f"{deps}`; this is a launch problem, not a gate finding")


def _git(root: Path, *args: str) -> str | None:
    try:
        proc = subprocess.run(["git", "-C", str(root), *args],
                              capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return proc.stdout.strip() if proc.returncode == 0 else None


def _framework_only(root: Path) -> tuple[bool, bool]:
    """(pre-commit's pre-push hook is installed, True) — for a clone without the
    git-hooks module's merge guard, which then has nothing to check."""
    hooks_dir = _git(root, "rev-parse", "--git-path", "hooks")
    if not hooks_dir:
        return False, True
    hook = Path(hooks_dir) if Path(hooks_dir).is_absolute() else root / hooks_dir
    try:
        text = (hook / "pre-push").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False, True
    return "pre-commit" in text, True


def _hook_files(d: Path) -> dict[str, bytes]:
    try:
        return {p.name: p.read_bytes() for p in d.iterdir() if p.is_file()}
    except OSError:
        return {}


def _tracked_hooks_wiring(root: Path, hooks_path: str | None) -> tuple[bool, str | None]:
    """(core.hooksPath reaches the tracked hooks, a message). `.githooks`
    literally, or an absolute path that resolves to this checkout's
    `.githooks` or to the main checkout's (a linked worktree shares the
    main checkout's config). The latter only while that directory holds
    every tracked hook, executable — else the message says what is missing
    (hard) — and with a note (soft) when its files differ from this
    worktree's tracked copy."""
    if not hooks_path:
        return False, None
    if hooks_path == GITHOOKS_DIR:
        return True, None
    if not Path(hooks_path).is_absolute():
        return False, None
    target = Path(hooks_path).resolve()
    tracked = root / GITHOOKS_DIR
    if target == tracked.resolve():
        return True, None
    common = _git(root, "rev-parse", "--git-common-dir")
    if not common:
        return False, None
    common_dir = Path(common) if Path(common).is_absolute() else root / common
    main = common_dir.resolve().parent / GITHOOKS_DIR
    if target != main.resolve():
        return False, None
    # git runs what sits there: a missing or partial directory runs no hook
    names = sorted(p.name for p in tracked.iterdir() if p.is_file())
    missing = [n for n in names if not ((main / n).is_file() and os.access(main / n, os.X_OK))]
    if missing:
        return False, (f"core.hooksPath={hooks_path} is the main checkout's {GITHOOKS_DIR}/, but it "
                       f"lacks (or cannot execute) {', '.join(missing)} — git runs no such hook for "
                       f"pushes from here. {_tracked_hooks_installer(root)} in the main checkout")
    if _hook_files(main) != _hook_files(tracked):
        return True, (f"core.hooksPath={hooks_path} is the main checkout's {GITHOOKS_DIR}/, "
                      f"whose hooks differ from this worktree's tracked copy — the main "
                      f"checkout's version runs for pushes from here")
    return True, None


def hook_wiring_findings(root: Path) -> tuple[list[str], list[str]]:
    """(hard, soft) about whether the registered local hooks can run at all.

    Only meaningful where the git-hooks module rendered a pre-commit config;
    without one there is nothing registered and nothing to report. Hard: the
    config exists while `core.hooksPath` points git elsewhere — every
    registration is inert and reports nothing (one hook manager, never two).
    Soft: the config exists and this clone never installed it — the gates
    run in CI, but nothing runs locally before a push."""
    hard: list[str] = []
    soft: list[str] = []
    if _git(root, "rev-parse", "--is-inside-work-tree") != "true":
        return hard, soft
    if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"):
        # a CI checkout never installs local hooks and needs none: the job IS
        # the enforcement there — reporting it as broken wiring would red CI
        return hard, soft
    hooks_path = _git(root, "config", "--get", "core.hooksPath")
    # the other manager: a tracked hooks directory that git only reads when
    # core.hooksPath points at it. Unset, git runs whatever stale copy sits in
    # .git/hooks — observed downstream: a June copy of pre-push ran for months
    # while the tracked one evolved, and a leaked GIT_DIR from a test then
    # flipped the real repo to core.bare=true through it.
    tracked = root / GITHOOKS_DIR
    if tracked.is_dir() and any(p.is_file() for p in tracked.iterdir()):
        wired, message = _tracked_hooks_wiring(root, hooks_path)
        if wired and message:
            soft.append(message)
        elif message:
            hard.append(message)
        elif not wired:
            hard.append(
                f"{GITHOOKS_DIR}/ holds tracked hooks but core.hooksPath is "
                f"{hooks_path or 'unset'} — git never reads them; whatever sits "
                f"in .git/hooks runs instead (a stale copy, or nothing). "
                f"{_tracked_hooks_installer(root)} in this clone")
    if not (root / PRE_COMMIT_CONFIG).is_file():
        return hard, soft
    if hooks_path:
        hard.append(
            f"core.hooksPath={hooks_path} is set while {PRE_COMMIT_CONFIG} "
            f"registers hooks — git ignores .git/hooks, so every pre-commit "
            f"registration is inert and no local gate has run at push. One "
            f"hook manager: `git config --unset core.hooksPath` and reinstall "
            f"({_framework_install(root)}), or move the registrations into {hooks_path} and "
            f"drop the config")
        return hard, soft
    # one owner for "is the framework's hook there, and the merge guard before it"
    # read from this checkout by path: no git-hooks module (a project's own
    # pre-commit config) ships no guard, and then none is expected
    installer = Path(__file__).resolve().parent / "install_hooks.py"
    guard_state = _framework_only
    if installer.is_file():
        spec = spec_from_file_location("install_hooks_doctor", installer)
        if spec is not None and spec.loader is not None:
            module = module_from_spec(spec)
            spec.loader.exec_module(module)
            guard_state = module.guard_state
    installed, guarded = guard_state(root)
    if not installed:
        soft.append(
            f"{PRE_COMMIT_CONFIG} registers a pre-push gate but this clone "
            f"never installed it — {_framework_install(root)}; "
            f"until then no gate runs locally before a push (CI remains the "
            f"authority)")
    elif not guarded:
        # pre-commit hands its hooks only the first ref line with something to
        # push, and none at all for a published commit pushed onto main: without
        # the guard reading git's lines the merge route is not checked. A note:
        # `merge_route --hook-check` refuses the push to main the guard did not
        # see, and a hard finding here refused every branch push too (refutation)
        soft.append(
            f"pre-commit's pre-push hook is installed without the merge guard — "
            f"`python3 {INSTALL_HOOKS_REL}` (after `pre-commit install`); until "
            f"then a push to main is refused")
    return hard, soft
