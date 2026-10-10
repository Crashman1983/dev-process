#!/usr/bin/env python3
"""The project's test configuration — `docs/process/testing.local.json`, the one
owner of what the selector, the lanes, the certificates and the train read
(`docs/process/testing.md`, "One test path"). Project data: the template never
writes it. Absent, there is no test configuration — the hook runs its gates and
no tests, nothing is guessed. Present but malformed is an error, never a
silent default (a typo in a map would otherwise skip tests unnoticed).
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.dont_write_bytecode = True

CONFIG = "docs/process/testing.local.json"
DEFAULT_LANES = {"scoped": {"wait": 300.0}, "full": {"wait": 3600.0, "nice": 10}}
UNMAPPED = ("full", "skip")
DEFAULT_TIMEOUT = 3600.0
DEFAULT_PREFLIGHT_TIMEOUT = 600.0


class ConfigError(ValueError):
    """`testing.local.json` is unreadable or malformed — say where, run nothing."""


def _argv(value, where: str, *, required: bool = True) -> list[str] | None:
    if value is None and not required:
        return None
    if not (isinstance(value, list) and value and all(isinstance(a, str) and a for a in value)):
        raise ConfigError(f"{where} must be a non-empty list of strings (an argv, no shell)")
    return list(value)


def _strings(value, where: str) -> list[str]:
    if not (isinstance(value, list) and all(isinstance(a, str) and a for a in value)):
        raise ConfigError(f"{where} must be a list of non-empty strings")
    return list(value)


def _lanes(raw) -> dict[str, dict]:
    if raw is None:
        return {k: dict(v) for k, v in DEFAULT_LANES.items()}
    if not isinstance(raw, dict) or not raw:
        raise ConfigError("lanes must be an object of lane name → {wait, nice}")
    lanes: dict[str, dict] = {}
    for name, spec in raw.items():
        if not (isinstance(name, str) and name.replace("-", "").replace("_", "").isalnum()):
            raise ConfigError(f"lanes: {name!r} is no lane name (letters, digits, - and _)")
        if not isinstance(spec, dict):
            raise ConfigError(f"lanes.{name} must be an object")
        wait = spec.get("wait", DEFAULT_LANES.get(name, {}).get("wait", 300.0))
        nice = spec.get("nice", 0)
        if isinstance(wait, bool) or not isinstance(wait, (int, float)) or wait < 0:
            raise ConfigError(f"lanes.{name}.wait must be seconds ≥ 0")
        if isinstance(nice, bool) or not isinstance(nice, int) or not 0 <= nice <= 19:
            raise ConfigError(f"lanes.{name}.nice must be an integer 0-19")
        lanes[name] = {"wait": float(wait), "nice": nice}
    return lanes


def _map(raw, where: str) -> list[dict]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ConfigError(f"{where} must be a list of {{from, to}} entries")
    out = []
    for i, entry in enumerate(raw):
        here = f"{where}[{i}]"
        if not (isinstance(entry, dict) and isinstance(entry.get("from"), str) and entry["from"]):
            raise ConfigError(f"{here} needs `from`: a path pattern")
        out.append({"from": entry["from"], "to": _strings(entry.get("to"), f"{here}.to")})
        if not out[-1]["to"]:
            raise ConfigError(f"{here}.to names no target")
    return out


def _pins(raw, where: str) -> dict[str, list[str]]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ConfigError(f"{where} must be an object of subject → [test targets]")
    if not all(raw):
        raise ConfigError(f"{where}: an empty subject")
    return {subject: _strings(targets, f"{where}.{subject}") for subject, targets in raw.items()}


def _stack(name: str, raw) -> dict:
    where = f"stacks.{name}"
    if not isinstance(raw, dict):
        raise ConfigError(f"{where} must be an object")
    unmapped = raw.get("unmapped", "full")
    if unmapped not in UNMAPPED:
        raise ConfigError(f"{where}.unmapped must be one of {', '.join(UNMAPPED)}")
    timeout = raw.get("timeout", DEFAULT_TIMEOUT)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
        raise ConfigError(f"{where}.timeout must be seconds > 0")
    cwd = raw.get("cwd", ".")
    if not isinstance(cwd, str) or Path(cwd).is_absolute() or ".." in Path(cwd).parts:
        raise ConfigError(f"{where}.cwd must be a path inside the repository")
    runner = _argv(raw.get("runner"), f"{where}.runner")
    if "{paths}" not in runner:
        raise ConfigError(f"{where}.runner needs the `{{paths}}` placeholder")
    stack = {
        "name": name,
        "paths": _strings(raw.get("paths"), f"{where}.paths"),
        "cwd": cwd.rstrip("/") or ".",
        "runner": runner,
        "full": _argv(raw.get("full"), f"{where}.full", required=False),
        "tests": _strings(raw.get("tests", []), f"{where}.tests"),
        "map": _map(raw.get("map"), f"{where}.map"),
        "pins": _pins(raw.get("pins"), f"{where}.pins"),
        "unmapped": unmapped,
        "select": _argv(raw.get("select"), f"{where}.select", required=False),
        "timeout": float(timeout),
    }
    if not stack["paths"]:
        raise ConfigError(f"{where}.paths names no path prefix")
    if unmapped == "full" and stack["full"] is None:
        raise ConfigError(f"{where}: unmapped=full needs a `full` command")
    return stack


def parse(data) -> dict:
    """The validated configuration from the decoded JSON."""
    if not isinstance(data, dict):
        raise ConfigError("the configuration must be a JSON object")
    known = {"lane_dir", "lanes", "certificate_env", "merge_suite", "preflight", "preflight_timeout",
             "stacks"}
    unknown = sorted(set(data) - known)
    if unknown:
        raise ConfigError(f"unknown key(s): {', '.join(unknown)} (known: {', '.join(sorted(known))})")
    lane_dir = data.get("lane_dir")
    if lane_dir is not None and not (isinstance(lane_dir, str) and lane_dir):
        raise ConfigError("lane_dir must be a path")
    suite = data.get("merge_suite")
    if suite is not None and not (isinstance(suite, str) and suite.strip()):
        raise ConfigError("merge_suite must be the train's suite command (a string, as --suite)")
    preflight_timeout = data.get("preflight_timeout", DEFAULT_PREFLIGHT_TIMEOUT)
    if isinstance(preflight_timeout, bool) or not isinstance(preflight_timeout, (int, float)) \
            or not math.isfinite(preflight_timeout) or preflight_timeout <= 0:
        raise ConfigError("preflight_timeout must be finite seconds > 0")
    if "preflight_timeout" in data and data.get("preflight") is None:
        raise ConfigError("preflight_timeout without a preflight times nothing")
    stacks_raw = data.get("stacks", {})
    if not isinstance(stacks_raw, dict):
        raise ConfigError("stacks must be an object of stack name → stack")
    return {
        "lane_dir": lane_dir,
        "lanes": _lanes(data.get("lanes")),
        "certificate_env": _strings(data.get("certificate_env", []), "certificate_env"),
        "merge_suite": suite.strip() if suite else None,
        # the environment check before any test runs: red is the host's, never a test's
        "preflight": _argv(data.get("preflight"), "preflight", required=False),
        "preflight_timeout": float(preflight_timeout),
        "stacks": [_stack(name, raw) for name, raw in stacks_raw.items()],
    }


def load(root: Path) -> dict | None:
    """The configuration of the repository at `root`; None when it has none.
    Raises ConfigError when the file exists but cannot be used."""
    path = root / CONFIG
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise ConfigError(f"{CONFIG}: {exc}") from exc
    try:
        return parse(data)
    except ConfigError as exc:
        raise ConfigError(f"{CONFIG}: {exc}") from exc


def lane_script(root: Path) -> Path | None:
    """The lane script whose `status` the tower, the train and dispatch read: a
    project's own `scripts/lane.py` while it still has one (its hooks use it),
    else the template's — once the project configures its tests."""
    own = root / "scripts" / "lane.py"
    if own.is_file():
        return own
    shipped = root / "scripts" / "process" / "lane.py"
    return shipped if shipped.is_file() and (root / CONFIG).is_file() else None


def lane_status(root: Path, env: dict | None = None) -> list[str]:
    """`lane.py status`, one line per lane (`<lane>: free` / `<lane>: held by …`);
    empty when the project has no lanes or the script cannot answer in 20 s."""
    import subprocess  # noqa: PLC0415

    script = lane_script(root)
    if script is None:
        return []
    try:
        r = subprocess.run([sys.executable, str(script), "status"], cwd=root,
                           capture_output=True, text=True, timeout=20, env=env)
    except (OSError, subprocess.TimeoutExpired):
        return []
    return [ln for ln in r.stdout.splitlines() if ln.strip()]
