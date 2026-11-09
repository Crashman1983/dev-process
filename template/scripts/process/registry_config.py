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

The registry at a commit (`load_registry_at`, v2.93): the gates that compare a
branch with its fork point read the base through the same layout logic as the
working tree (`_build`, one owner), from `git ls-tree` and one batched blob read.
`check_review` is imported late, inside those readers only: this module stays a
leaf the core gates import without a cycle.
"""
from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import NamedTuple

TEMPLATE = "docs/process/feature-registry.json"
LOCAL = "docs/process/feature-registry.local.json"
GATE = "scripts/process/check_feature_registry.py"
HEAD = "_capability.json"
EXAMPLE = ".example.json"
COMMENT = "_comment"
# an acceptance item's id (#404): addressable as `<story id>#<item id>`
ITEM_ID = re.compile(r"^AC[1-9]\d*$")

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
_BOOLS = ("require_registry", "planned_refs", "strict_item_tests", "stable_ids")
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


def _place_problems(cfg: dict) -> list[str]:
    """What is wrong with `root` and `id_pattern` once they are non-empty strings — the
    rules a base's configuration is held to as well (`load_registry_at`)."""
    out = []
    where = "feature-registry config"
    root = cfg.get("root")
    if isinstance(root, str) and (not root.strip() or Path(root).is_absolute() or ".." in Path(root).parts):
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
    return out


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
    out += _place_problems(cfg)
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
    cfg: dict = field(default_factory=dict)  # the configuration it was laid out by


def _parsed(text: str) -> tuple[object, str | None]:
    try:
        return json.loads(text), None
    except ValueError as exc:
        return None, f"invalid JSON: {exc}"


def _load(path: Path) -> tuple[object, str | None]:
    try:
        return _parsed(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        return None, f"invalid JSON: {exc}"


@dataclass
class _Listing:
    """What a lister saw of a registry directory: whether it is there, its subdirectories,
    the `*.json` names per directory ("" is the root itself) and how to parse one file
    (path relative to the registry directory). Working tree and commit each have a lister;
    `_build` alone knows the layout."""
    present: bool
    dirs: list[str] = field(default_factory=list)
    files: dict[str, list[str]] = field(default_factory=dict)
    load: Callable[[str], tuple[object, str | None]] = lambda _rel: (None, "not listed")


def _worktree_listing(path: Path) -> _Listing:
    if not path.is_dir():
        return _Listing(False)
    dirs = sorted(p.name for p in path.iterdir() if p.is_dir())
    files = {d: sorted(p.name for p in (path / d).glob("*.json") if p.is_file()) for d in ("", *dirs)}
    return _Listing(True, dirs, files, lambda rel: _load(path / rel))


def _review_module() -> ModuleType:
    """`check_review`, imported late: this module stays a leaf of the core gates."""
    import check_review  # noqa: PLC0415

    return check_review


def _plain_blobs(root: Path, rev: str, rel: str) -> dict[str, str]:
    """{path: blob id} of every entry at or under `rel` at `rev` (`ls-tree -z`). A symlink
    or a submodule anywhere there raises GitReadError, like the journal reader
    (`check_review._journal_blobs`): the file a link points at would not be read."""
    review = _review_module()
    out = review._git_read(root, "ls-tree", "-r", "-z", rev, "--", rel, strict=True)
    blobs: dict[str, str] = {}
    for raw in (out or b"").split(b"\0"):
        meta, tab, name = raw.partition(b"\t")
        parts = meta.split()
        path = name.decode("utf-8", errors="surrogateescape")
        if not tab or len(parts) != 3 or not (path == rel or path.startswith(rel + "/")):
            continue
        if parts[0] not in (b"100644", b"100755"):
            raise review.GitReadError(f"{path} at {rev[:12]} is a symlink or submodule "
                                      f"(mode {parts[0].decode()}) — not a plain file")
        blobs[path] = parts[2].decode()
    return blobs


def _rev_reader(root: Path, rev: str) -> Reader:
    """A `Reader` for `config` at `rev`: a file's text, None when absent; GitReadError for
    a symlink, a submodule, a failed read or a blob that is no UTF-8."""
    review = _review_module()

    def read(rel: str) -> str | None:
        sha = _plain_blobs(root, rev, rel).get(rel)
        return None if sha is None else review._blob_texts(root, [sha], strict=True)[sha]
    return read


def _rev_listing(root: Path, rev: str, rel_root: str) -> _Listing:
    """The registry directory `rel_root` at `rev`, its blobs read in ONE batch, strict."""
    rel_root = Path(rel_root).as_posix()  # `./x` and `x/` name `x`, as in the working tree
    blobs = _plain_blobs(root, rev, rel_root)
    if not blobs:
        return _Listing(False)
    if rel_root in blobs:
        raise _review_module().GitReadError(f"{rel_root} at {rev[:12]} is a file, not a directory")
    files: dict[str, list[str]] = {"": []}
    shas: dict[str, str] = {}
    for path, sha in blobs.items():
        parts = path[len(rel_root) + 1:].split("/")
        if len(parts) >= 2:
            files.setdefault(parts[0], [])
        if len(parts) <= 2 and parts[-1].endswith(".json"):
            files["" if len(parts) == 1 else parts[0]].append(parts[-1])
            shas["/".join(parts)] = sha
    texts = _review_module()._blob_texts(root, sorted(set(shas.values())), strict=True)
    return _Listing(True, sorted(d for d in files if d), {d: sorted(n) for d, n in files.items()},
                    lambda rel: _parsed(texts[shas[rel]]))


def _build(root: Path, cfg: dict, listing: _Listing) -> Registry:
    """The registry in `cfg`'s layout from what a lister saw — the one owner of the layout."""
    reg = Registry(root / cfg["root"], present=listing.present, cfg=cfg)
    if not reg.present:
        return reg

    def entries(directory: str, *, skip: str = "") -> list[str]:
        return [n for n in listing.files.get(directory, []) if not n.endswith(EXAMPLE) and n != skip]

    if cfg.get("layout") != "capabilities":
        for name in entries(""):
            data, error = listing.load(name)
            reg.stories.append(Story(reg.path / name, data, error))
        return reg
    reg.stray = [reg.path / name for name in entries("")]
    for directory in listing.dirs:
        cap = Capability(reg.path / directory)
        if HEAD not in listing.files.get(directory, []):
            cap.error = f"no {HEAD}"
        else:
            data, error = listing.load(f"{directory}/{HEAD}")
            if error or not isinstance(data, dict):
                cap.error = error or f"{HEAD} must be a JSON object"
            else:
                cap.head = data
        for name in entries(directory, skip=HEAD):
            data, error = listing.load(f"{directory}/{name}")
            story = Story(cap.path / name, data, error, cap)
            cap.stories.append(story)
            reg.stories.append(story)
        reg.capabilities.append(cap)
    return reg


def load_registry(root: Path, cfg: dict) -> Registry:
    """Every story file of the registry in `cfg`'s layout, parsed or with the reason it
    could not be; structure (heads, stray files) for the registry gate."""
    return _build(root, cfg, _worktree_listing(root / cfg["root"]))


# the configuration keys a base's registry is read by; the rest is today's rule set
BASE_KEYS = ("root", "layout", "id_pattern", "stable_ids")
NO_BASE = "no base registry"


def _base_config(cfg: dict) -> tuple[dict | None, str]:
    """(the base keys of a base's merged configuration, or None with the reason). Only
    they are held to a rule: `root`, `layout` and `id_pattern` must say where and how the
    registry lies; `stable_ids` is taken as it stands (the registry gate judges it)."""
    if not (isinstance(cfg.get("root"), str) and cfg["root"].strip()):
        return None, "`root` is no non-empty string"
    if cfg.get("layout") not in _ENUMS["layout"]:
        return None, f"`layout` {cfg.get('layout')!r} is none of {', '.join(_ENUMS['layout'])}"
    if not (isinstance(cfg.get("id_pattern"), str) and cfg["id_pattern"]):
        return None, "`id_pattern` is no non-empty string"
    bad = _place_problems(cfg)
    if bad:
        return None, "; ".join(p.removeprefix("feature-registry config: ") for p in bad)
    return {key: cfg[key] for key in BASE_KEYS if key in cfg}, ""


def load_registry_at(root: Path, rev: str) -> tuple[Registry | None, list[str]]:
    """The registry as it stands at the commit `rev` — the base a branch is compared with
    (v2.93 I4.2). Read leniently: it never raises on a bad base. Returns (the registry,
    []) or (None, notes), the notes saying why there is no base registry — each starts
    with `NO_BASE`:

    - the configuration is not at `rev` (a project from before the registry
      configuration), cannot be read (a git failure, a symlink or submodule, a blob that
      is no UTF-8, invalid JSON) or is invalid in `root`, `layout` or `id_pattern`;
    - the registry directory is not at `rev`, or cannot be read the same ways.

    Only `BASE_KEYS` of the base's configuration count, never today's full rule set:
    the registry's `cfg` holds just them (`stable_ids` as found, maybe not a boolean).
    The stories are laid out by `_build`, as in the working tree; a story file that does
    not parse is a `Story` with its `error`, as there."""
    review = _review_module()
    at = f"at {rev[:12]}"
    read = _rev_reader(root, rev)
    try:
        if read(TEMPLATE) is None:
            return None, [f"{NO_BASE}: {TEMPLATE} is not {at} (a project from before the "
                          f"registry configuration) — item ids are not compared with a base"]
        merged = config(root, read)
    except (review.GitReadError, ConfigError) as exc:
        return None, [f"{NO_BASE}: the configuration {at} cannot be read ({exc}) — item ids "
                      f"are not compared with a base"]
    cfg, why = _base_config(merged)
    if cfg is None:
        return None, [f"{NO_BASE}: the configuration {at} is unusable ({why}) — item ids are "
                      f"not compared with a base"]
    try:
        listing = _rev_listing(root, rev, cfg["root"])
    except review.GitReadError as exc:
        return None, [f"{NO_BASE}: {cfg['root']} {at} cannot be read ({exc}) — item ids are "
                      f"not compared with a base"]
    if not listing.present:
        return None, [f"{NO_BASE}: {cfg['root']} is not {at} — item ids are not compared "
                      f"with a base"]
    return _build(root, cfg, listing), []


def item_ids(data: object) -> tuple[set[str], set[str]]:
    """(the ids of a story's acceptance items, its retired ids) — conforming `AC<n>` ids
    only, from a parsed story of either load (`Story.data`); empty for anything else."""
    if not isinstance(data, dict):
        return set(), set()

    def ids(value: object) -> set[str]:
        return {e["id"] for e in value if isinstance(e, dict) and isinstance(e.get("id"), str)
                and ITEM_ID.match(e["id"])} if isinstance(value, list) else set()
    return ids(data.get("acceptance")), ids(data.get("retired"))


def paired_stories(reg: Registry, base: Registry) -> list[tuple[Story, Story]]:
    """(story today, the same story at the base) for every story in both (v2.93 I4.2).
    A story is found by its `id`; one whose id the base does not hold is looked up by its
    path there — a renamed story in the flat layout stays compared — unless the base's
    story at that path carries an id that still stands today (it moved, and is found by
    id). In the capabilities layout the file name is the id: a renamed story there is a
    deleted one plus a new one."""
    def sid(story: Story) -> str | None:
        return story.data.get("id") if isinstance(story.data, dict) and isinstance(
            story.data.get("id"), str) else None

    by_id: dict[str, Story] = {}
    for story in base.stories:
        if sid(story) is not None:
            by_id.setdefault(sid(story), story)
    by_path = {story.path: story for story in base.stories}
    today = {sid(story) for story in reg.stories} - {None}
    pairs = []
    for story in reg.stories:
        if sid(story) is None:
            continue
        found = by_id.get(sid(story))
        if found is None:
            at_path = by_path.get(story.path)
            if at_path is not None and isinstance(at_path.data, dict) and sid(at_path) not in today:
                found = at_path
        if found is not None and isinstance(found.data, dict):
            pairs.append((story, found))
    return pairs


# --- surfaces: one owner of how a story and an item resolve them (v2.93) -------

class Problem(NamedTuple):
    """A finding of the surface resolution, for the registry gate to report under its own
    label: `hard` fails, otherwise it is a note. The resolution itself reports nothing."""
    hard: bool
    text: str


def _non_empty_strings(value: object) -> bool:
    return isinstance(value, list) and bool(value) and all(isinstance(s, str) and s for s in value)


def story_surfaces(cfg: dict, data: dict) -> tuple[list[str], list[Problem]]:
    """(the story's surfaces, what is wrong with its `surfaces` field). The surfaces are
    its own, or — when it has none (or `story_surfaces` is "none") — the project's."""
    mode = cfg["story_surfaces"]
    found: list[Problem] = []
    own = data.get("surfaces") if mode != "none" else None
    if mode != "none":
        if "surfaces" not in data:
            if mode == "required":
                found.append(Problem(True, "missing 'surfaces'"))
        elif not _non_empty_strings(own):
            found.append(Problem(True, "'surfaces' must be a non-empty list of strings"))
        else:
            unknown = sorted(set(own) - set(cfg["surfaces"]))
            if unknown:
                found.append(Problem(True, f"unknown surface(s) {unknown} — declared: {cfg['surfaces']}"))
    if isinstance(own, list) and own and all(isinstance(s, str) for s in own):
        return own, found
    return list(cfg["surfaces"]), found


def item_surfaces(cfg: dict, item: dict, of_story: list[str]) -> tuple[list[str], list[Problem]]:
    """(the item's surfaces, what is wrong with its `surfaces` field), in the rule order of
    #404 AC-3/AC-3a; [] is the one implicit surface (none on the item, the story or in the
    configuration). `of_story` is `story_surfaces`' answer."""
    if "surfaces" not in item:
        return of_story, []
    if not cfg["surfaces"]:
        return [], [Problem(False, f"item 'surfaces' without project surfaces — declare "
                                   f"`surfaces` in {LOCAL}; not checked")]
    surfaces = item["surfaces"]
    if not _non_empty_strings(surfaces):
        return of_story, [Problem(True, "'surfaces' must be a non-empty list of strings")]
    outside = sorted(set(surfaces) - set(of_story))
    found = [Problem(True, f"surfaces {outside} outside the story's surfaces {of_story}")] if outside else []
    return list(dict.fromkeys(surfaces)), found


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
