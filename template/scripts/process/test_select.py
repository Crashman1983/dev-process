#!/usr/bin/env python3
"""Which tests a change needs — from data, the same answer for every caller
(`docs/process/testing.md`, "One test path").

    test_select.py plan  [--base REF] [--class branch|merge] [--json]
    test_select.py run   [--base REF] [--class branch|merge] [--certify]
    test_select.py check

The data is `docs/process/testing.local.json` (`testing_config`): per stack
its path prefixes, a map from source paths to test targets with a fallback
chain (`{name}` = one segment, `**` = the rest; the first target that exists
and holds a test wins, a fallback is named), the test files that select
themselves, audit pins (subject → tests, deleted subjects included), the
runner (`{paths}` = the targets, relative to the stack's `cwd`), a `full`
command, and the rule for a changed path the map does not reach: `full`
(default) runs the stack's `full` command, `skip` names it and leaves it to
the train's full suite — the same rule for the hook, `--certify` and a manual
run (downstream: a helper no map reached ran the whole backend suite in a
"scoped" certification, then the train ran it again). A path in no stack
counts only for pins (docs, a README).

`run` takes one lane hold for all stacks (`lane.py`) and stops at the first
red stack; a certificate of the tree (`certificate.py`) skips it all — a
branch accepts `push` or `merge`, the merge class only `merge`. The merge
class without a certificate runs the configured `merge_suite`, else each
stack's `full`, on the `full` lane. `--certify` writes the `push`
certificate after green on a clean tree. A configured `preflight` checks the
environment once, under the hold, before the first test: red there runs no
test and is the host's failure, never a red test.

Exit: 0 green or nothing to run, 1 red, 2 cannot judge (no base, a broken
configuration, a selector that failed to answer, a red preflight), 75 the
lane stayed busy.
"""
from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

import certificate  # noqa: E402
import testing_config  # noqa: E402
from check_review import GitReadError, _git_bytes, integration_refs, merge_base, paths_in_flight  # noqa: E402
from process_git import git_environment, path_captures, path_matches  # noqa: E402

EX_TEMPFAIL = 75
EX_CANNOT_JUDGE = 2
SELECT_TIMEOUT_S = 600


class Unjudgeable(RuntimeError):
    """No answer that could be trusted: say why, run nothing (exit 2)."""


class NoForkPoint(Unjudgeable):
    """No integration ref to fork from at all — the one case a caller may
    bound the change otherwise (an ambiguous fork point is no such case)."""


def repo_root() -> Path:
    r = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    if r.returncode != 0:
        raise Unjudgeable("not inside a git repository")
    return Path(r.stdout.strip())


def _tracked(root: Path) -> set[str]:
    out = _git_bytes(root, "ls-files", "-z")
    if out is None:
        raise Unjudgeable("git cannot list the tracked files")
    return {p for p in out.decode("utf-8", "surrogateescape").split("\0") if p}


def changed_paths(root: Path, base: str | None) -> set[str]:
    """What the branch changes since its fork, renames as both sides. A tip an
    integration ref already contains changes nothing; no fork point
    otherwise is no answer."""
    if base is None:
        try:
            base = merge_base(root, "HEAD")
        except GitReadError as exc:
            raise Unjudgeable(str(exc)) from exc
        if base is None:
            if any(_git_bytes(root, "merge-base", "--is-ancestor", "HEAD", ref) is not None
                   for ref in integration_refs(root)
                   if _git_bytes(root, "rev-parse", "--verify", "-q", f"{ref}^{{commit}}") is not None):
                return set()
            raise NoForkPoint("no fork point from the integration branch — fetch it "
                              "(`git fetch origin <default branch>`)")
    paths = paths_in_flight(root, base=base, no_renames=True)
    if paths is None:
        raise Unjudgeable(f"git cannot list the changes since {base[:12]}")
    return paths


def _stack_of(stacks: list[dict], path: str) -> dict | None:
    return next((s for s in stacks if any(path_matches(p, path) for p in s["paths"])), None)


def _is_test(stack: dict, path: str) -> bool:
    return any(path_matches(t, path) for t in stack["tests"])


def _holds_test(stack: dict, target: str, tracked: set[str]) -> bool:
    if target in tracked:
        return _is_test(stack, target)
    prefix = target.rstrip("/") + "/"
    return any(p.startswith(prefix) and _is_test(stack, p) for p in tracked)


def _fill(template: str, caps: dict[str, str]) -> str:
    out = template
    for name, value in caps.items():
        out = out.replace("{" + name + "}", value)
    return out


def _pinned(stacks: list[dict], changed: set[str]) -> dict[str, set[str]]:
    """stack name → pinned targets. A subject ending in `/` is a prefix; any
    other is a path or glob. Deleted subjects count (the paths are both
    sides of every change)."""
    out: dict[str, set[str]] = {}
    for stack in stacks:
        for subject, targets in stack["pins"].items():
            if any(path_matches(subject, p) or p == subject for p in changed):
                out.setdefault(stack["name"], set()).update(targets)
    return out


def _local_select(root: Path, stack: dict, paths: list[str]) -> list[str]:
    """The stack's own selector (dependency-based selection, e.g. `vitest
    related`): the stack's paths NUL-separated on stdin, targets on stdout
    (NUL- or newline-separated). Failing to answer is no "nothing selected"."""
    data = "\0".join(paths).encode("utf-8", "surrogateescape")
    try:
        r = subprocess.run(stack["select"], cwd=root, input=data, capture_output=True,
                           timeout=SELECT_TIMEOUT_S, env=git_environment())
    except subprocess.TimeoutExpired as exc:
        raise Unjudgeable(f"stack {stack['name']}: the selector did not answer in "
                          f"{SELECT_TIMEOUT_S} s") from exc
    except OSError as exc:
        raise Unjudgeable(f"stack {stack['name']}: the selector cannot start ({exc})") from exc
    if r.returncode != 0:
        raise Unjudgeable(f"stack {stack['name']}: the selector failed ({r.returncode}): "
                          f"{r.stderr.decode(errors='replace').strip()[:300]}")
    text = r.stdout.decode("utf-8", "surrogateescape")
    return [t for t in text.replace("\0", "\n").splitlines() if t.strip()]


def plan(root: Path, cfg: dict, changed: set[str], klass: str) -> list[dict]:
    """Per stack: {name, action (run/skip/full/none), targets, fallbacks, unmapped, pins}."""
    tracked = _tracked(root)
    stacks = cfg["stacks"]
    pins = _pinned(stacks, changed)
    result = []
    for stack in stacks:
        mine = sorted(p for p in changed if _stack_of(stacks, p) is stack)
        targets: list[str] = []
        fallbacks: list[str] = []
        unmapped: list[str] = []
        for path in mine:
            if _is_test(stack, path):
                if path not in tracked:
                    continue  # a deleted test has nothing left to run
                targets.append(path)
                continue
            # a deleted source still maps: the tests that imported it must
            # show they no longer need it
            for entry in stack["map"]:
                caps = path_captures(entry["from"], path)
                if caps is None:
                    continue
                chain = [_fill(t, caps) for t in entry["to"]]
                found = next((t for t in chain if _holds_test(stack, t, tracked)), None)
                if found:
                    targets.append(found)
                    if found != chain[0]:
                        fallbacks.append(f"{path} → {found} (no tests in {chain[0]})")
                    break
            else:
                unmapped.append(path)
        if stack["select"] and mine:
            targets += _local_select(root, stack, mine)
        pinned = sorted(pins.get(stack["name"], set()))
        targets = _dedupe([*targets, *(t for t in pinned if t in tracked or
                                       any(p.startswith(t.rstrip("/") + "/") for p in tracked))])
        missing_pins = [t for t in pinned if t not in targets and not any(
            t.startswith(d.rstrip("/") + "/") for d in targets)]
        if klass == "merge":
            action = "full"
        elif unmapped and stack["unmapped"] == "full":
            action = "full"
        elif targets:
            action = "run"
        else:
            action = "none"
        result.append({"name": stack["name"], "action": action, "targets": targets,
                       "fallbacks": fallbacks, "unmapped": unmapped, "pins": pinned,
                       "missing_pins": missing_pins})
    return result


def _dedupe(targets: list[str]) -> list[str]:
    """Each target once; a file a selected directory holds is dropped."""
    uniq = sorted(set(targets))
    dirs = [t.rstrip("/") + "/" for t in uniq if not Path(t).suffix]
    return [t for t in uniq if not any(t != d.rstrip("/") and t.startswith(d) for d in dirs)]


def _argv(stack: dict, targets: list[str]) -> list[str]:
    cwd = stack["cwd"]
    rel = []
    for t in targets:
        r = t if cwd == "." else (t[len(cwd) + 1:] if t.startswith(cwd + "/") else str(
            Path(*([".."] * len(Path(cwd).parts))) / t))
        rel.append("./" + r if r.startswith("-") else r)
    out: list[str] = []
    for arg in stack["runner"]:
        out += rel if arg == "{paths}" else [arg]
    return out


def push_evidence(cfg: dict) -> str:
    """What a `push` certificate certifies: the stack configuration, serialised
    stably — a changed map or runner certifies nothing old."""
    return json.dumps(cfg["stacks"], sort_keys=True)


def _run(root: Path, argv: list[str], cwd: str, timeout: float, label: str) -> int:
    print(f"test_select: $ {shlex.join(argv)}   # {label}", flush=True)
    try:
        return subprocess.run(argv, cwd=root / cwd, timeout=timeout).returncode
    except subprocess.TimeoutExpired:
        print(f"test_select: {label} exceeded {int(timeout)} s — red", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"test_select: {label} cannot start ({exc}) — red", file=sys.stderr)
        return 1


def _preflight_problem(root: Path, cfg: dict) -> str | None:
    """Why the configured environment check failed, or None (green or none)."""
    argv, timeout = cfg["preflight"], cfg["preflight_timeout"]
    if not argv:
        return None
    print(f"test_select: $ {shlex.join(argv)}   # preflight", flush=True)
    try:
        rc = subprocess.run(argv, cwd=root, timeout=timeout, env=git_environment()).returncode
    except subprocess.TimeoutExpired:
        return f"the preflight did not finish in {timeout:g} s"
    except OSError as exc:
        return f"the preflight cannot start ({exc})"
    return f"the preflight exited {rc}" if rc else None


def _report(steps: list[dict]) -> None:
    for s in steps:
        for note in s["fallbacks"]:
            print(f"test_select: {s['name']}: fallback {note}")
        if s["unmapped"]:
            shown = ", ".join(s["unmapped"][:5]) + (" …" if len(s["unmapped"]) > 5 else "")
            what = "the stack's full command runs" if s["action"] == "full" else \
                "skipped here — the train's full suite runs them"
            print(f"test_select: {s['name']}: no map reaches {shown}; {what}")
        for pin in s["missing_pins"]:
            print(f"test_select: {s['name']}: pinned target {pin} does not exist (`test_select.py check`)")


def merge_certificate_evidence(root: Path, cfg: dict) -> str | None:
    """The evidence a merge certificate of this configuration must carry now."""
    return certificate.merge_evidence(root, cfg["merge_suite"], cfg.get("merge_scope"))


def run(root: Path, cfg: dict, changed: set[str], klass: str, *, certify: bool) -> int:
    import lane  # noqa: PLC0415 — fcntl only where tests run

    evidence = {"push": push_evidence(cfg)}
    wanted = merge_certificate_evidence(root, cfg) if cfg["merge_suite"] else None
    if wanted:  # an unknown scope names no evidence: no hit is possible
        evidence["merge"] = wanted
    kinds = ("merge",) if klass == "merge" else ("push", "merge")
    hit = certificate.find(root, kinds, evidence)
    if hit:
        print(f"test_select: {certificate.describe(hit)} — no tests run")
        return 0
    before = None
    if certify:
        problem = certificate.clean_tree_problem(root) or certificate.env_problem(cfg["certificate_env"])
        before = certificate.evidence_tree(root) if not problem else None
        if problem:
            print(f"test_select: no certificate will be written — {problem}")
    # a merge push runs its whole suite: no selection, no local selector
    steps = [] if klass == "merge" else plan(root, cfg, changed, klass)
    _report(steps)
    work: list[tuple[list[str], str, float, str]] = []
    if klass == "merge":
        if cfg["merge_suite"]:
            work.append((["sh", "-c", cfg["merge_suite"]], ".", max(s["timeout"] for s in cfg["stacks"])
                         if cfg["stacks"] else 3600.0, "merge_suite"))
        else:
            for stack in cfg["stacks"]:
                if stack["full"] is None:
                    print(f"test_select: stack {stack['name']} has no `full` command and there is no "
                          f"`merge_suite` — a merge push cannot be tested; configure one", file=sys.stderr)
                    return 2
                work.append((stack["full"], stack["cwd"], stack["timeout"], f"{stack['name']} full"))
    else:
        by_name = {s["name"]: s for s in cfg["stacks"]}
        for step in steps:
            stack = by_name[step["name"]]
            if step["action"] == "full":
                work.append((stack["full"], stack["cwd"], stack["timeout"], f"{stack['name']} full"))
            elif step["action"] == "run":
                work.append((_argv(stack, step["targets"]), stack["cwd"], stack["timeout"],
                             f"{stack['name']} selected"))
    if not work:
        print("test_select: nothing to test for this change")
        return _certify(root, cfg, certify, before)
    # a run under `make -n` proves nothing: make exits 0 having run no recipe, and the
    # push was accepted on it (#265). Other altering flags and variables (a `make X=1`
    # wrapper) still run the tests — they only deny the certificate, as before
    problem = certificate.noop_problem()
    if problem:
        print(f"test_select: environment — {problem}; no test ran — unset it and push again",
              file=sys.stderr)
        return EX_CANNOT_JUDGE
    name = "full" if klass == "merge" else "scoped"
    started = time.monotonic()
    try:
        settings = lane.config(root)
        hold = lane.hold(name, label=f"tests {klass}", settings=settings) \
            if testing_config.lane_script(root) == root / "scripts/process/lane.py" else _no_hold()
        with hold:
            problem = _preflight_problem(root, cfg)
            if problem:
                print(f"test_select: environment — {problem}; no test ran, nothing certified "
                      f"(fix the host, not the tests)", file=sys.stderr)
                return EX_CANNOT_JUDGE
            for argv, cwd, timeout, label in work:
                if _run(root, argv, cwd, timeout, label) != 0:
                    print(f"test_select: red — {label}", file=sys.stderr)
                    return 1
    except lane.LaneBusy as busy:
        print(lane.tempfail_message(busy, settings["lanes"][name]["wait"]), file=sys.stderr)
        return EX_TEMPFAIL
    print(f"test_select: green in {int(time.monotonic() - started)} s")
    return _certify(root, cfg, certify, before)


class _no_hold:
    """A project that still has its own `scripts/lane.py`: its commands hold
    their lanes themselves — the frame must not take the same lock first."""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _certify(root: Path, cfg: dict, certify: bool, before: str | None) -> int:
    if certify and before:
        ok, why = certificate.write(root, "push", push_evidence(cfg), before_tree=before,
                                    writer="test_select --certify", env_names=cfg["certificate_env"])
        print(f"test_select: {'push certificate written' if ok else 'no certificate — ' + why}")
    return 0


def check(root: Path, cfg: dict) -> list[str]:
    """Stale data: a pin target or subject, or a map target's fixed part, that
    no tracked path carries any more."""
    tracked = _tracked(root)
    findings = []

    def exists(path: str) -> bool:
        if path in tracked:
            return True
        prefix = path.rstrip("/") + "/"
        return any(p.startswith(prefix) for p in tracked)

    for stack in cfg["stacks"]:
        for subject, targets in stack["pins"].items():
            if not (exists(subject) or any(path_matches(subject, p) for p in tracked)):
                findings.append(f"{stack['name']}: pin subject {subject} names no tracked path")
            findings += [f"{stack['name']}: pin target {t} (for {subject}) does not exist"
                         for t in targets if not exists(t)]
        for i, entry in enumerate(stack["map"]):
            fixed = [t.split("{", 1)[0] for t in entry["to"]]
            if not any(exists(f.rstrip("/")) for f in fixed if f.strip("/")):
                findings.append(f"{stack['name']}: map[{i}] targets {', '.join(entry['to'])} "
                                f"reach no tracked path")
    return findings


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="test_select.py", description=(__doc__ or "").split("\n\n")[0])
    sub = p.add_subparsers(dest="command", required=True)
    for name in ("plan", "run"):
        sp = sub.add_parser(name)
        sp.add_argument("--base", default=None, help="the fork point (default: from the integration branch)")
        sp.add_argument("--class", dest="klass", choices=("branch", "merge"), default="branch")
        if name == "plan":
            sp.add_argument("--json", action="store_true")
        else:
            sp.add_argument("--certify", action="store_true", help="write the push certificate after green")
    sub.add_parser("check")
    args = p.parse_args(argv)
    try:
        root = repo_root()
        cfg = testing_config.load(root)
        if cfg is None:
            print("test_select: no test configuration (docs/process/testing.local.json) — nothing selected")
            return 0
        if args.command == "check":
            findings = check(root, cfg)
            for f in findings:
                print(f"test_select: stale — {f}", file=sys.stderr)
            return 1 if findings else 0
        changed = set() if args.klass == "merge" and args.command == "run" else changed_paths(root, args.base)
        if args.command == "plan":
            steps = plan(root, cfg, changed, args.klass)
            if args.json:
                print(json.dumps({"changed": sorted(changed), "stacks": steps}, indent=2))
            else:
                _report(steps)
                for s in steps:
                    print(f"{s['name']}: {s['action']}" + (f" — {' '.join(s['targets'])}" if s["targets"] else ""))
            return 0
        return run(root, cfg, changed, args.klass, certify=args.certify)
    except (testing_config.ConfigError, Unjudgeable) as exc:
        print(f"test_select: {exc} — nothing run", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
