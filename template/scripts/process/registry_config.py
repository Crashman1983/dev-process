#!/usr/bin/env python3
"""The feature registry's configuration and loader — the one owner of where the
registry lives, how it is laid out and what a story id looks like
(`docs/process/modules/feature-registry.md`, Configuration).

Core and always rendered, because four gates read the registry and two of them
run without the feature-registry module: the registry gate, `check_product_frame`,
`check_issues` and `check_plan_structure`. Without the module (its gate
`scripts/process/check_feature_registry.py` is rendered only with it) the loader
answers "no registry" and the core gates behave as without a registry.

Configuration: the template's `docs/process/feature-registry.json`, with the
project's `docs/process/feature-registry.local.json` laid over it — mappings
merge key by key, everything else (lists included) replaces whole. Both are read
from the working tree, like `gates.local.json`, and are gate configuration
(`check_review.GATE_FILES`). The core gates only read the configuration; whether
it is valid is the registry gate's judgment (`problems`). Stdlib only.
"""
from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

TEMPLATE = "docs/process/feature-registry.json"
LOCAL = "docs/process/feature-registry.local.json"
GATE = "scripts/process/check_feature_registry.py"
HEAD = "_capability.json"
EXAMPLE = ".example.json"
COMMENT = "_comment"

Reader = Callable[[str], "str | None"]


class ConfigError(ValueError):
    """The configuration cannot be read — say which file and why."""


def module_active(root: Path) -> bool:
    return (root / GATE).is_file()


def _merged(base: dict, over: dict) -> dict:
    """`over` laid on `base`: mappings merge key by key, anything else replaces whole."""
    out = dict(base)
    for key, value in over.items():
        out[key] = (_merged(out[key], value)
                    if isinstance(value, dict) and isinstance(out.get(key), dict) else value)
    return out


def _worktree_reader(root: Path) -> Reader:
    def read(rel: str) -> str | None:
        path = root / rel
        if not path.is_file():
            return None
        try:
            return path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise ConfigError(f"{rel}: cannot be read ({exc})") from exc
    return read


def _json_object(read: Reader, rel: str) -> dict | None:
    text = read(rel)
    if text is None:
        return None
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise ConfigError(f"{rel}: invalid JSON ({exc})") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{rel}: must be a JSON object")
    return data


def config(root: Path, read: Reader | None = None) -> dict:
    """The merged configuration. `read(rel)` returns a file's text or None when it is
    absent (default: the working tree); a caller reading at a ref passes its own.
    Raises ConfigError when the template file is missing or either file is unusable."""
    read = read or _worktree_reader(root)
    base = _json_object(read, TEMPLATE)
    if base is None:
        raise ConfigError(f"{TEMPLATE} missing — the template ships it; restore it "
                          f"(project choices go into {LOCAL})")
    local = _json_object(read, LOCAL)
    return _merged(base, local) if local else base


# --- validation: the registry gate's judgment, never the core gates' ---------

_ENUMS = {
    "layout": ("flat", "capabilities"),
    "story_surfaces": ("none", "optional", "required"),
    "story_tests": ("tests", "test_mapping"),
    "node_check": ("note", "hard"),
}
_STRINGS = ("root", "id_pattern")
_BOOLS = ("require_registry", "planned_refs", "strict_item_tests")
_STRING_LISTS = ("story_text_fields", "surfaces", "shared_proof_layers", "test_ref_roots",
                 "retired_fields", "extra_fields")
_ISSUES_KEYS = ("field", "required", "required_for")
_STATUS_KEYS = ("values", "deferred", "deferred_allows_empty_tests")
KEYS = (*_ENUMS, *_STRINGS, *_BOOLS, *_STRING_LISTS, "issues", "story_status")


def _unknown(data: dict, known: tuple[str, ...], where: str) -> list[str]:
    return [f"feature-registry config: unknown key `{where}{key}` (known: {', '.join(known)})"
            for key in sorted(set(data) - set(known) - {COMMENT})]


def _string_list(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(x, str) and x for x in value)


def problems(cfg: dict) -> list[str]:
    """Everything wrong with a merged configuration: unknown keys at any level
    (`_comment` excepted — a typo must not silently drop a rule), missing keys and
    values of the wrong shape."""
    out = _unknown(cfg, KEYS, "")
    where = "feature-registry config"
    for key in KEYS:
        if key not in cfg:
            out.append(f"{where}: `{key}` missing (the template file sets every key)")
    for key, allowed in _ENUMS.items():
        if key in cfg and cfg[key] not in allowed:
            out.append(f"{where}: `{key}` must be one of {', '.join(allowed)}, got {cfg[key]!r}")
    for key in _STRINGS:
        if key in cfg and not (isinstance(cfg[key], str) and cfg[key]):
            out.append(f"{where}: `{key}` must be a non-empty string")
    for key in _BOOLS:
        if key in cfg and not isinstance(cfg[key], bool):
            out.append(f"{where}: `{key}` must be true or false")
    for key in _STRING_LISTS:
        if key in cfg and not _string_list(cfg[key]):
            out.append(f"{where}: `{key}` must be a list of non-empty strings")
    root = cfg.get("root")
    if isinstance(root, str) and (Path(root).is_absolute() or ".." in Path(root).parts):
        out.append(f"{where}: `root` must be a path inside the repository")
    pattern = cfg.get("id_pattern")
    if isinstance(pattern, str) and pattern:
        if "{prefix}" in pattern and cfg.get("layout") != "capabilities":
            out.append(f"{where}: `id_pattern` uses {{prefix}}, which only the capabilities "
                       f"layout supplies (from each `{HEAD}`)")
        try:
            re.compile(pattern.replace("{prefix}", "[A-Z]+"))
        except re.error as exc:
            out.append(f"{where}: `id_pattern` is no regular expression ({exc})")
    if cfg.get("story_surfaces") in ("optional", "required") and not cfg.get("surfaces"):
        out.append(f"{where}: `story_surfaces` {cfg['story_surfaces']!r} needs `surfaces`, "
                   f"the project's declared surfaces")
    status = cfg.get("story_status")
    values: list = []
    if status is not None:
        if not isinstance(status, dict):
            out.append(f"{where}: `story_status` must be null or an object")
        else:
            out += _unknown(status, _STATUS_KEYS, "story_status.")
            values = status.get("values") if _string_list(status.get("values")) else []
            if not values:
                out.append(f"{where}: `story_status.values` must be a non-empty list of strings")
            deferred = status.get("deferred")
            if deferred is not None and deferred not in values:
                out.append(f"{where}: `story_status.deferred` must be null or one of `values`")
            if not isinstance(status.get("deferred_allows_empty_tests", False), bool):
                out.append(f"{where}: `story_status.deferred_allows_empty_tests` must be true or false")
    issues = cfg.get("issues")
    if "issues" in cfg and not isinstance(issues, dict):
        out.append(f"{where}: `issues` must be an object")
    elif isinstance(issues, dict):
        out += _unknown(issues, _ISSUES_KEYS, "issues.")
        if issues.get("field") not in ("issue", "issues"):
            out.append(f"{where}: `issues.field` must be \"issue\" or \"issues\"")
        if not isinstance(issues.get("required"), bool):
            out.append(f"{where}: `issues.required` must be true or false")
        required_for = issues.get("required_for")
        if required_for is not None and required_for not in values:
            out.append(f"{where}: `issues.required_for` must be null or one of "
                       f"`story_status.values`")
    return out


# --- the loader ----------------------------------------------------------------

@dataclass
class Story:
    path: Path
    data: object = None          # the parsed JSON; None when `error` is set
    error: str | None = None
    capability: Capability | None = None


@dataclass
class Capability:
    path: Path                   # the directory
    head: dict | None = None
    error: str | None = None     # the head is missing or unusable
    stories: list[Story] = field(default_factory=list)


@dataclass
class Registry:
    path: Path
    present: bool
    stories: list[Story] = field(default_factory=list)
    capabilities: list[Capability] = field(default_factory=list)
    stray: list[Path] = field(default_factory=list)  # JSON in the root of a capabilities layout


def _load(path: Path) -> tuple[object, str | None]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        return None, f"invalid JSON: {exc}"


def _entries(directory: Path, *, skip: str = "") -> list[Path]:
    return sorted(p for p in directory.glob("*.json")
                  if p.is_file() and not p.name.endswith(EXAMPLE) and p.name != skip)


def load_registry(root: Path, cfg: dict) -> Registry:
    """Every story file of the registry in `cfg`'s layout, parsed or with the reason it
    could not be; structure (heads, stray files) for the registry gate."""
    reg = Registry(root / cfg["root"], present=(root / cfg["root"]).is_dir())
    if not reg.present:
        return reg
    if cfg.get("layout") != "capabilities":
        for path in _entries(reg.path):
            data, error = _load(path)
            reg.stories.append(Story(path, data, error))
        return reg
    reg.stray = _entries(reg.path)
    for directory in sorted(p for p in reg.path.iterdir() if p.is_dir()):
        cap = Capability(directory)
        head = directory / HEAD
        if not head.is_file():
            cap.error = f"no {HEAD}"
        else:
            data, error = _load(head)
            if error or not isinstance(data, dict):
                cap.error = error or f"{HEAD} must be a JSON object"
            else:
                cap.head = data
        for path in _entries(directory, skip=HEAD):
            data, error = _load(path)
            story = Story(path, data, error, cap)
            cap.stories.append(story)
            reg.stories.append(story)
        reg.capabilities.append(cap)
    return reg


def load_stories(root: Path, cfg: dict | None = None) -> list[Story] | None:
    """The registry's stories; None when the module is off ("no registry").
    Raises ConfigError when the configuration cannot be read."""
    if not module_active(root):
        return None
    return load_registry(root, cfg if cfg is not None else config(root)).stories


def story_ids(stories: list[Story]) -> set[str]:
    return {s.data["id"] for s in stories
            if isinstance(s.data, dict) and isinstance(s.data.get("id"), str)}


def _pattern_body(cfg: dict) -> str:
    return cfg["id_pattern"].removeprefix("^").removesuffix("$")


def story_ref_pattern(cfg: dict) -> re.Pattern:
    """The loose form of a story reference in prose: `id_pattern` with any digit width
    and any prefix, between word boundaries — `^{prefix}-US-\\d{3}$` reads
    `\\b[A-Z]+-US-\\d+\\b`, so `DOC-US-0012` is one ref, never `DOC-US-001`."""
    loose = re.sub(r"\\d(?:\{\d+(?:,\d*)?\}|[+*])?", r"\\d+", _pattern_body(cfg))
    return re.compile(r"\b" + loose.replace("{prefix}", "[A-Z]+") + r"\b")


def strict_id_pattern(cfg: dict, prefix: str | None = None) -> re.Pattern:
    """`id_pattern` itself; `{prefix}` is the capability's prefix, or any when unknown."""
    fill = re.escape(prefix) if prefix else "[A-Z]+"
    return re.compile(cfg["id_pattern"].replace("{prefix}", fill))
