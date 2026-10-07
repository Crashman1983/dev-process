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

import os
import re
import shutil
import subprocess
import sys
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
_DEPENDENCIES = re.compile(r"^#\s*dependencies\s*=\s*\[(?P<items>[^\]]*)\]",
                           re.MULTILINE)


def declared_dependencies(path: Path) -> list[str]:
    """The dependencies a script declares in its PEP-723 block; [] without one.

    Deliberately textual: the declaration IS text in the script header, and a
    parser that had to import the script could fail on exactly the missing
    dependency it is meant to check. The block itself is the truth — there is
    no list of declaring scripts to keep in sync."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    block = _PEP723_BLOCK.search(text)
    if not block:
        return []
    deps = _DEPENDENCIES.search(block.group("body"))
    if not deps:
        return []
    return [item.strip().strip("\"'") for item in deps.group("items").split(",")
            if item.strip()]


def child_argv(root: Path, cmd: list[str]) -> list[str]:
    """argv for a child command of the shape `[interpreter, script, *args]`.

    A script with its own PEP-723 declaration runs through `uv run --script`;
    every other command is returned unchanged. Without `uv` on PATH the
    command also stays as given: that is the pre-existing behaviour — green on
    hosts with the dependency installed globally, the plain ImportError
    otherwise. Refusing here would disarm hosts on which the gates run today."""
    if len(cmd) < 2:
        return cmd
    script = root / cmd[1]
    if not declared_dependencies(script) or not shutil.which("uv"):
        return cmd
    return ["uv", "run", "--script", str(script), *cmd[2:]]


def gate_runner_argv(root: Path) -> list[str] | None:
    """argv that resolves the runner's PEP-723 declaration — or None.

    None means "not runnable", not "gates red". Callers report the two cases
    distinctly (`not_runnable_reason`), otherwise the reader hunts the failure
    in their branch instead of in the interpreter.

    Order: an interpreter that provably carries the dependency first —
    `find_spec` asks the running interpreter, exactly the one that would be
    handed on as `sys.executable`, and it needs no network or cache — then
    `uv`, which resolves the declaration itself."""
    runner = root / RUNNER_REL
    if not runner.is_file():
        return None
    if find_spec("yaml") is not None:
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
    """(core.hooksPath reaches the tracked hooks, a note). `.githooks`
    literally, or an absolute path that resolves to this checkout's
    `.githooks` or to the main checkout's (a linked worktree shares the
    main checkout's config) — the latter with a note when its files are
    not this worktree's tracked copy."""
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
        wired, note = _tracked_hooks_wiring(root, hooks_path)
        if note:
            soft.append(note)
        if not wired:
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
