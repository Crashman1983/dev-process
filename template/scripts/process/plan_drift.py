#!/usr/bin/env python3
"""Plan drift: how far the integration branch has moved since an issue's plan
was last written. A plan carries a picture of the code; an execute phase that
starts from a picture hundreds of commits old spends its first hour (and its
tokens) finding out what changed — or builds against code that is gone.

Measured per plan the issue declares (`issue: N`), at the branch's tip, else
at the base:

- behind   — commits on the base since the plan's last commit;
- touching — of those, the ones that change a file the plan names (a file
  path in backticks that exists at either end; a directory is too coarse);
- vanished — named files the base had where the plan forked from it and no
  longer has.

`dispatch.py start --phase execute` asks this before it starts a worker. The
check is a node of the check graph (docs/process/optimization.md): it writes
one `plan-drift` line to the gate event log and runs in the mode the mandate
gives it (`plan_drift` in docs/process/optimization.local.json):

- shadow (the default) — record only;
- warn  — record, tell the steward, and put a note in the worker's prompt;
- block — record and refuse to start until the plan is refreshed, or the
  steward passes `--stale-plan-ok`.

A plan is stale when `touching` exceeds `max_touching` or `behind` exceeds
`max_behind`. Both numbers are first guesses; the shadow events are there to
calibrate them before anyone turns the node up.

Usage: uv run scripts/process/plan_drift.py ISSUE [--branch B] [--json]
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling import
import check_review as _review  # noqa: E402
import gate_events  # noqa: E402

GATE = "plan-drift"
MODES = ("shadow", "warn", "block")
DEFAULTS = {"mode": "shadow", "max_touching": 10, "max_behind": 500}
# a path in backticks: no blanks, a slash or an extension, an optional
# `:line`, `:a-b` or `::symbol` suffix the plan adds for the reader
_NAMED = re.compile(r"`([^`\s]+?)(?::[\w.-]*)*`")
_MAX_NAMED = 200


def _git(root: Path, *args: str) -> str | None:
    try:
        proc = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return proc.stdout if proc.returncode == 0 else None


def settings(root: Path) -> tuple[dict, list[str]]:
    """The node's mode and limits from the mandate, defaults for anything
    missing; a malformed value is a problem and falls back to its default."""
    problems: list[str] = []
    try:
        import optimize  # noqa: PLC0415 — the mandate's one reader
        mandate, problem = optimize.load_mandate(root)
    except Exception as exc:  # noqa: BLE001
        mandate, problem = None, f"mandate unreadable ({exc})"
    if problem:
        problems.append(problem)
    raw = (mandate or {}).get("plan_drift", {})
    if not isinstance(raw, dict):
        problems.append("plan_drift must be a mapping — defaults apply")
        raw = {}
    out = dict(DEFAULTS)
    if raw.get("mode", out["mode"]) in MODES:
        out["mode"] = raw.get("mode", out["mode"])
    else:
        problems.append(f"plan_drift.mode must be one of {', '.join(MODES)} — shadow applies")
    for key in ("max_touching", "max_behind"):
        value = raw.get(key, out[key])
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            out[key] = value
        else:
            problems.append(f"plan_drift.{key} must be a non-negative integer — {out[key]} applies")
    return out, problems


def base_ref(root: Path) -> str | None:
    import gate_modes  # noqa: PLC0415 — the one answer to "which ref is the integration branch"
    return gate_modes.base_ref(root)


def _commit(root: Path, ref: str) -> str | None:
    out = _git(root, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
    return out.strip() if out else None


def tip_of(root: Path, branch: str | None) -> str | None:
    """The branch's commit here: the local branch, else origin's copy."""
    if not branch:
        return None
    return _commit(root, f"refs/heads/{branch}") or _commit(root, f"refs/remotes/origin/{branch}")


def named_paths(text: str) -> list[str]:
    seen: list[str] = []
    for m in _NAMED.finditer(text):
        tok = m.group(1)
        tok = (tok[2:] if tok.startswith("./") else tok).rstrip("/")
        if ("/" in tok or "." in tok) and "://" not in tok and tok not in seen:
            seen.append(tok)
        if len(seen) >= _MAX_NAMED:
            break
    return seen


def _tree(root: Path, ref: str) -> set[str] | None:
    """The files at `ref`."""
    out = _git(root, "ls-tree", "-r", "-z", "--name-only", ref)
    return None if out is None else {f for f in out.split("\0") if f}


def plans_for(root: Path, issue: int, ref: str) -> list[tuple[str, str]] | None:
    """(path, text) of the active plans at `ref` that declare `issue`."""
    texts = _review.record_texts(root, _review.PLAN_KINDS, ref=ref)
    if texts is None:
        return None
    return [(rel, text) for rel, text in texts if issue in _review.local_issue_numbers(text)]


def measure(root: Path, issue: int, branch: str | None = None, tip: str | None = None) -> dict:
    """One verdict for the issue: {"outcome": pass|fail|skipped|unknown,
    "reason", "plans": [...], "base", "tip"}. Limits come from the mandate.
    `tip` is the branch commit the caller resolved (dispatch: origin's for a
    remote phase); without it, or where it is not here, the local answer."""
    conf, problems = settings(root)
    base = base_ref(root)
    base_sha = _commit(root, base) if base else None
    tip = (_commit(root, tip) if tip else None) or tip_of(root, branch) or base_sha
    result: dict = {"outcome": "unknown", "reason": None, "plans": [], "base": base_sha, "tip": tip,
                    "mode": conf["mode"], "limits": {k: conf[k] for k in ("max_touching", "max_behind")},
                    "problems": problems}
    if not base_sha or not tip:
        result["reason"] = "no integration branch on a remote — drift cannot be told"
        return result
    plans = plans_for(root, issue, tip)
    if plans is None:
        result["reason"] = f"plans at {tip[:12]} unreadable"
        return result
    if not plans:
        result.update(outcome="skipped", reason=f"no active plan declares #{issue}")
        return result
    base_tree = _tree(root, base_sha)
    if base_tree is None:
        result["reason"] = "base tree unreadable"
        return result
    stale: list[str] = []
    for rel, text in plans:
        log = _git(root, "log", "-1", "--format=%H %cI", tip, "--", rel)
        if not log or not log.strip():
            result["reason"] = f"{rel}: no commit found"
            return result
        commit, _, when = log.strip().partition(" ")
        plan_tree = _tree(root, commit)
        if plan_tree is None:
            result["reason"] = f"{rel}: tree at {commit[:12]} unreadable"
            return result
        fork_out = _git(root, "merge-base", commit, base_sha)
        fork_tree = _tree(root, fork_out.split()[0]) if fork_out and fork_out.strip() else None
        if fork_tree is None:
            result["reason"] = f"{rel}: no common history with the base"
            return result
        named = [p for p in named_paths(text) if p in base_tree or p in plan_tree or p in fork_tree]
        # gone from the base since the fork — never a file the branch made itself
        vanished = [p for p in named if p in fork_tree and p not in base_tree]
        behind_out = _git(root, "rev-list", "--count", f"{commit}..{base_sha}")
        touching_out = (_git(root, "rev-list", "--count", f"{commit}..{base_sha}", "--", *named)
                        if named else "0")
        if behind_out is None or touching_out is None:
            result["reason"] = f"{rel}: history unreadable"
            return result
        behind, touching = int(behind_out.strip() or 0), int(touching_out.strip() or 0)
        result["plans"].append({"path": rel, "commit": commit, "written": when, "behind": behind,
                                "touching": touching, "named": len(named), "vanished": vanished[:20]})
        if touching > conf["max_touching"] or behind > conf["max_behind"]:
            stale.append(f"{rel} is {behind} commit(s) behind, {touching} touch its {len(named)} named path(s)"
                         + (f", {len(vanished)} of them gone" if vanished else ""))
    if stale:
        result.update(outcome="fail", reason="; ".join(stale))
    else:
        worst = max(result["plans"], key=lambda p: (p["touching"], p["behind"]))
        result.update(outcome="pass", reason=f"{worst['path']}: {worst['behind']} behind, "
                                             f"{worst['touching']} touching")
    return result


def _repeats(path: Path | None, issue: int, result: dict, override: bool) -> bool:
    """Whether the log's last plan-drift line for the issue already says this:
    a queued execute that block mode refuses is measured again on every
    drain, and a repeat is no new run to count."""
    if path is None:
        return False
    try:
        with path.open("rb") as fh:
            fh.seek(max(0, fh.seek(0, 2) - 200_000))
            lines = fh.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return False
    for line in reversed(lines):
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and row.get("gate") == GATE and row.get("issue") == issue:
            return (row.get("head"), row.get("base"), row.get("outcome"), row.get("mode"),
                    bool(row.get("override"))) == (result["tip"], result["base"], result["outcome"],
                                                   result["mode"], override)
    return False


def record(root: Path, issue: int, branch: str | None, result: dict, duration_s: float,
           *, override: bool = False) -> None:
    path = gate_events.events_path(root)
    if _repeats(path, issue, result, override):
        return
    # measured on committed refs: the input is the tip, never a working tree
    gate_events.append(path, {
        "gate": GATE, "mode": result["mode"], "outcome": result["outcome"], "rc": None,
        "duration_s": round(duration_s, 3), "reason": result["reason"],
        "head": result["tip"], "dirty": False, "pushed": None, "branch": branch, "ci": False,
        "issue": issue, "base": result["base"], "override": override or None,
        "plans": [{k: p[k] for k in ("path", "commit", "behind", "touching", "named")}
                  for p in result["plans"]]})


def prompt_note(result: dict) -> str:
    return ("Plan drift: " + result["reason"] + ". The code moved since the plan was written — "
            "before the first step, check the plan's named files against the current base; "
            "where they changed, update the plan (and say so in the report) instead of "
            "following it blind.")


def check_execute(root: Path, issue: int, branch: str, *, dry_run: bool, stale_plan_ok: bool,
                  tip: str | None = None) -> tuple[str | None, str | None]:
    """dispatch's question before an execute phase: (refusal, prompt note).
    The steward reads what it prints; nothing here may stop a start in shadow
    mode, and a check that cannot run blocks nothing."""
    started = time.monotonic()
    try:
        result = measure(root, issue, branch, tip)
    except Exception as exc:  # noqa: BLE001 — an observation, never a crash of dispatch
        print(f"dispatch: plan drift not measured ({exc})", file=sys.stderr)
        return None, None
    for problem in result["problems"]:
        print(f"dispatch: note: {problem}", file=sys.stderr)
    mode = result["mode"]
    stale = result["outcome"] == "fail"
    if not dry_run:
        record(root, issue, branch, result, time.monotonic() - started, override=stale and stale_plan_ok)
    if not stale or mode == "shadow":
        return None, None
    if mode == "block" and not stale_plan_ok:
        return (f"plan drift — {result['reason']}; refresh the plan (dispatch the plan phase) "
                f"or start with --stale-plan-ok"), None
    print(f"dispatch: plan drift — {result['reason']} (worker told to re-check)", file=sys.stderr)
    return None, prompt_note(result)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("issue", type=int)
    ap.add_argument("--branch")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    top = _git(Path.cwd(), "rev-parse", "--show-toplevel")
    root = Path(top.strip()) if top else Path.cwd()
    result = measure(root, args.issue, args.branch)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        for p in result["problems"]:
            print(f"note: {p}")
        print(f"#{args.issue}: {result['outcome']} ({result['mode']}) — {result['reason']}")
        for p in result["plans"]:
            print(f"  {p['path']}: written {p['written'][:10]} at {p['commit'][:12]}, {p['behind']} behind, "
                  f"{p['touching']} touching {p['named']} named path(s)"
                  + (f", gone: {', '.join(p['vanished'])}" if p["vanished"] else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
