#!/usr/bin/env python3
"""The project's generated inventories — `docs/process/inventories.local.json`,
the one owner of what `inventory.py` and `check_inventory.py` read
(`docs/process/inventories.md`). Project data: the template never writes it.
Absent, nothing is configured. Present but malformed is an error that says
where, never a silent default: a renamed key would otherwise drop an inventory
from the check unnoticed.

    {"inventories": {"env": {"command": ["uv", "run", "scripts/inventory_env.py"],
                             "timeout": 120, "allow_empty": false}}}
"""
from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True

CONFIG = "docs/process/inventories.local.json"
DEFAULT_TIMEOUT = 120.0
# the check runs every extractor inside one gate run; the gate runner kills a
# gate after 600 s, so the extractors together must stay clearly below that
TIMEOUT_BUDGET = 540.0
NAME = re.compile(r"[a-z0-9-]+")
KEYS = ("command", "timeout", "allow_empty")


class ConfigError(ValueError):
    """`inventories.local.json` is unreadable or malformed — say where, run nothing."""


def _argv(value, where: str) -> list[str]:
    if not (isinstance(value, list) and value and all(isinstance(a, str) and a for a in value)):
        raise ConfigError(f"{where} must be a non-empty list of strings (an argv, no shell)")
    return list(value)


def _inventory(name: str, raw) -> dict:
    where = f"inventories.{name}"
    if not isinstance(raw, dict):
        raise ConfigError(f"{where} must be an object")
    unknown = sorted(set(raw) - set(KEYS))
    if unknown:
        raise ConfigError(f"{where}: unknown key(s): {', '.join(unknown)} (known: {', '.join(KEYS)})")
    if "command" not in raw:
        raise ConfigError(f"{where} needs `command`")
    timeout = raw.get("timeout", DEFAULT_TIMEOUT)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) \
            or not math.isfinite(timeout) or timeout <= 0:
        raise ConfigError(f"{where}.timeout must be finite seconds > 0")
    allow_empty = raw.get("allow_empty", False)
    if not isinstance(allow_empty, bool):
        raise ConfigError(f"{where}.allow_empty must be true or false")
    return {"command": _argv(raw["command"], f"{where}.command"), "timeout": float(timeout),
            "allow_empty": allow_empty}


def parse(data) -> dict[str, dict]:
    """The validated inventories, name → {command, timeout, allow_empty},
    sorted by name."""
    if not isinstance(data, dict):
        raise ConfigError("the configuration must be a JSON object")
    unknown = sorted(set(data) - {"inventories"})
    if unknown:
        raise ConfigError(f"unknown key(s): {', '.join(unknown)} (known: inventories)")
    raw = data.get("inventories")
    if not isinstance(raw, dict):
        raise ConfigError("inventories must be an object of inventory name → inventory")
    out: dict[str, dict] = {}
    for name in sorted(raw):
        if not NAME.fullmatch(name):
            raise ConfigError(f"inventories: {name!r} is no inventory name (a-z, 0-9 and -)")
        out[name] = _inventory(name, raw[name])
    total = sum(spec["timeout"] for spec in out.values())
    if total >= TIMEOUT_BUDGET:
        raise ConfigError(f"the timeouts add up to {total:g} s; they must stay below "
                          f"{TIMEOUT_BUDGET:g} s so the check finishes inside the gate's limit")
    return out


def load(root: Path) -> dict[str, dict] | None:
    """The inventories of the repository at `root`; None when it configures none.
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
