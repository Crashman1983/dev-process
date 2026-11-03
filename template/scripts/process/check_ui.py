#!/usr/bin/env python3
"""ui-check gate (#368): a plan whose branch carries UI says how the UI was
considered — not judged. Judging the design is the owner's and the reviewer's,
against the board; this gate only makes sure the questions were answered.

Who owes the block. A Tier 2+ plan the branch adds (`check_plan_structure._bound`:
`.process-work/plans/` with its archive, and `specs/*/plan.md`) owes it when

  - it declares a design contract (`design-contract: <surface>`, not `n/a`), or
  - the branch diff (both sides of every rename) touches UI: the area `ui` in
    `testing.local.json` (the integration branch's and this checkout's, the
    union) and the `paths` of every design-contract registry.

A plan that only carries UI along — a backend plan beside a UI plan, a label in
a backend change — writes `ui-check: n/a — <reason>`. A plan that declares a
contract cannot. Every such line is shown in the review bundle and the digest:
whether the UI is really only carried along is the reviewer's call.

The block, one line per axis, in a plan section of its own or anywhere:

    ui-check:                 (or `ui-check <surface>:` — one per declared surface)
    - board: …                (may say `see Design Contract Trace`)
    - viewports: …
    - themes: …
    - states: …
    - navigation: …           (the way in and the way back)
    - interaction: …
    - content extremes: …
    - accessibility: …
    - rules: …                (the rule files checked against, the reuse decision —
                               used, variant, new with a reason — and every
                               deviation with its reason)

plus a registry's `extra_axes`. A value is coverage or a reference, `n/a — <reason>`,
or `inherited` where the surface's registry names a default for that axis (never
for `rules`). `rules` names at least one existing repository path; where a
registry lists `rule_sources`, at least one of those, and `n/a` is a finding
there. Fenced blocks and HTML comments are quotations — a commented skeleton in
a template counts for nothing.

Nothing declared as UI (no `areas.ui`, no registry `paths`) is a note while a
bound plan is on the branch; `"ui": []` says the repository has none. The gate
starts observing (`gate_modes`: `OBSERVE_FIRST`); `gate_modes.py restore
ui-check` arms it. Python stdlib only.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_review import (  # noqa: E402
    GitReadError,
    fenced_lines,
    integration_ref,
    plan_tier,
)
from process_git import path_matches  # noqa: E402

import testing_config  # noqa: E402

PLANS_ACTIVE = ".process-work/plans"
SPECS_DIR = "specs"
REGISTRY_DIR = "docs/process/design-contracts"
AXES = ("board", "viewports", "themes", "states", "navigation", "interaction",
        "content extremes", "accessibility", "rules")
_HEADER = re.compile(r"^[ \t]*(?:[-*+][ \t]+)?[*_]*ui-check(?:[ \t]+`?(?P<surface>[\w.-]+)`?)?[*_]*"
                     r"[ \t]*:[ \t]*(?P<rest>.*?)[ \t]*$", re.IGNORECASE)
_AXIS = re.compile(r"^[ \t]*(?:[-*+][ \t]+)?[*_]*(?P<axis>[a-z][a-z0-9 _-]*?)[*_]*[ \t]*:[ \t]*(?P<value>.*?)[ \t]*$",
                   re.IGNORECASE)
_NA = re.compile(r"^n/?a\b[\s—–:-]*(.*)$", re.IGNORECASE)
_TOKEN = re.compile(r"`([^`]+)`|(\S+)")


# --- what the project declares --------------------------------------------------

def registries(root: Path) -> list[dict]:
    """The design-contract registries as plain data (`surface`, `paths`, `defaults`,
    `extra_axes`, `rule_sources`); the design-contracts gate owns their validity."""
    d = root / REGISTRY_DIR
    out = []
    if not d.is_dir():
        return out
    for p in sorted(d.glob("*.json")):
        if p.name.endswith(".example.json"):
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError):
            continue
        if isinstance(data, dict):
            out.append({"surface": str(data.get("surface") or p.stem).lower(),
                        "paths": _strs(data.get("paths")),
                        "defaults": data.get("defaults") if isinstance(data.get("defaults"), dict) else {},
                        "extra_axes": [a.lower() for a in _strs(data.get("extra_axes"))],
                        "rule_sources": _strs(data.get("rule_sources"))})
    return out


def _strs(value) -> list[str]:
    return [v for v in value if isinstance(v, str) and v.strip()] if isinstance(value, list) else []


def ui_globs(root: Path, ref: str | None, regs: list[dict]) -> tuple[list[str], bool]:
    """(the globs that are UI, whether anything was declared at all)."""
    globs: list[str] = []
    declared = False
    for where in (None, ref) if ref else (None,):
        cfg = testing_config.config_at(root, where)
        if cfg is not None and "ui" in cfg["areas"]:
            declared = True
            globs += cfg["areas"]["ui"]
    for reg in regs:
        if reg["paths"]:
            declared = True
            globs += reg["paths"]
    return sorted(set(globs)), declared


# --- the plans --------------------------------------------------------------------

def bound_plans(root: Path, ref: str) -> dict[str, str]:
    """rel → text of the Tier 2+ plans this branch answers for."""
    from check_plan_structure import _bound  # noqa: PLC0415 — one owner of binding

    pdir = root / PLANS_ACTIVE
    found: list[Path] = []
    if pdir.is_dir():
        found += [p for p in sorted(pdir.glob("*.md")) if not p.name.startswith("design-")]
        if (pdir / "archive").is_dir():
            found += sorted((pdir / "archive").glob("*.md"))
    if (root / SPECS_DIR).is_dir():
        found += sorted((root / SPECS_DIR).glob("*/plan.md"))
    out: dict[str, str] = {}
    for p in found:
        rel = p.relative_to(root).as_posix()
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if (plan_tier(text) or 0) >= 2 and _bound(root, ref, rel):
            out[rel] = text
    return out


def _readable(text: str) -> str:
    """What a reader sees, line for line with the file: fenced lines (the review
    gate's fence walk) and HTML comments blank, everything else as written."""
    kept = dict(fenced_lines(text)[0])
    out: list[str] = []
    in_comment = False
    for i in range(1, len(text.splitlines()) + 1):
        line, rest, pos = kept.get(i, ""), "", 0
        while pos < len(line):
            if in_comment:
                end = line.find("-->", pos)
                if end < 0:
                    break
                in_comment, pos = False, end + 3
            else:
                start = line.find("<!--", pos)
                if start < 0:
                    rest += line[pos:]
                    break
                rest += line[pos:start]
                in_comment, pos = True, start + 4
        out.append(rest if rest.strip() else "")
    return "\n".join(out)


def declared_contracts(text: str, regs: list[dict]) -> list[str]:
    """The registered surfaces the plan's `design-contract:` lines declare (not `n/a`)."""
    try:
        from check_design_contracts import declarations, declared_surface  # noqa: PLC0415
    except ImportError:
        return []
    known = {r["surface"] for r in regs}
    out = []
    for value in declarations(text):
        if _NA.match(value):
            continue
        surface = declared_surface(value)
        if surface in known and surface not in out:
            out.append(surface)
    return out


def parse_blocks(text: str) -> tuple[dict[str, tuple[int, list[tuple[int, str, str]]]],
                                     list[tuple[int, str]]]:
    """({surface or "": (header line, [(line, axis, value)])}, [(line, n/a reason)]) from the readable
    text. A header indented four spaces or more is code, not a header. Blank lines may
    follow the header; an indented line without a list marker continues the axis above."""
    blocks: dict[str, tuple[int, list[tuple[int, str, str]]]] = {}
    opt_outs: list[tuple[int, str]] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        m = _HEADER.match(lines[i])
        if not m or _indent(lines[i]) >= 4:
            i += 1
            continue
        surface = (m.group("surface") or "").lower()
        rest = m.group("rest").strip().strip("*_").strip()
        if rest:
            na = _NA.match(rest)
            if na is not None:
                opt_outs.append((i + 1, na.group(1).strip()))
            i += 1
            continue
        # a second block for the same surface continues the first: its axes count, twice is a finding
        entries = blocks.setdefault(surface, (i + 1, []))[1]
        start = len(entries)
        j = i + 1
        while j < len(lines) and not lines[j].strip() and len(entries) == start:
            j += 1  # `**ui-check:**`, a blank line, then the list
        while j < len(lines) and lines[j].strip():
            line = lines[j]
            a = _AXIS.match(line)
            marker = re.match(r"^[ \t]*[-*+][ \t]", line) is not None
            if len(entries) > start and _indent(line) > 0 and not marker:
                n, axis, value = entries[-1]
                entries[-1] = (n, axis, f"{value} {line.strip()}".strip())
            elif a and (marker or _indent(line) < 4):
                entries.append((j + 1, a.group("axis").strip().lower(),
                                a.group("value").strip().strip("*_").strip()))
            else:
                break
            j += 1
        i = j
    return blocks, opt_outs


def _indent(line: str) -> int:
    """Columns of leading whitespace; a tab reaches the next multiple of four (CommonMark)."""
    col = 0
    for ch in line:
        if ch == " ":
            col += 1
        elif ch == "\t":
            col += 4 - col % 4
        else:
            break
    return col


_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")


def _cited_paths(root: Path, value: str) -> list[str]:
    """The repository files a `rules` value cites: `path`, `path:12`, `path#anchor`,
    `[text](path)`. Never outside the repository."""
    out = []
    top = root.resolve()
    tokens = [m.group(1) for m in _LINK.finditer(value)]
    tokens += [(m.group(1) or m.group(2) or "") for m in _TOKEN.finditer(_LINK.sub(" ", value))]
    for token in tokens:
        token = token.strip(".,;:()[]\"'")
        token = re.sub(r"#.*$", "", token)
        token = re.sub(r":\d+(?:-\d+)?$", "", token)
        if not token or token.startswith(("http://", "https://", "/")):
            continue
        target = (root / token).resolve()
        if top in target.parents and target.is_file() and token not in out:
            out.append(token)
    return out


def block_findings(root: Path, rel: str, header: int, entries: list[tuple[int, str, str]],
                   reg: dict | None, regs: list[dict]) -> list[str]:
    extra = reg["extra_axes"] if reg else sorted({a for r in regs for a in r["extra_axes"]})
    defaults = {k.lower() for k in (reg["defaults"] if reg else
                                   {k for r in regs for k in r["defaults"]})}
    sources = reg["rule_sources"] if reg else sorted({s for r in regs for s in r["rule_sources"]})
    wanted = [*AXES, *[a for a in extra if a not in AXES]]
    out: list[str] = []
    if not entries:
        return [f"{rel}:{header}: `ui-check:` with no axis line under it — one line per axis "
                f"({', '.join(wanted)})"]
    seen: dict[str, int] = {}
    for line, axis, value in entries:
        where = f"{rel}:{line}"
        if axis not in wanted:
            out.append(f"{where}: unknown ui-check axis `{axis}` — the axes are {', '.join(wanted)}")
            continue
        if axis in seen:
            out.append(f"{where}: `{axis}` twice (first at line {seen[axis]})")
            continue
        seen[axis] = line
        na = _NA.match(value)
        if not value:
            out.append(f"{where}: `{axis}` is empty — say what is covered, point to it, "
                       f"or `n/a — <reason>`")
        elif value.lower() == "inherited":
            if axis == "rules":
                out.append(f"{where}: `rules` cannot be inherited — name the rule files this work "
                           f"was checked against")
            elif axis not in defaults:
                out.append(f"{where}: `{axis}: inherited`, but no registry names a default for it")
        elif na is not None:
            if not re.search(r"\w", na.group(1)):
                out.append(f"{where}: `{axis}: n/a` without a reason")
            elif axis == "rules" and sources:
                out.append(f"{where}: `rules: n/a`, but the project names its UI rules "
                           f"({', '.join(sources)}) — say which were checked")
        elif axis == "rules":
            cited = _cited_paths(root, value)
            if not cited:
                out.append(f"{where}: `rules` names no existing file — the rule files this work "
                           f"was checked against, the reuse decision and every deviation")
            elif sources and not set(cited) & set(sources):
                out.append(f"{where}: `rules` cites none of the project's rule sources "
                           f"({', '.join(sources)})")
    for axis in wanted:
        if axis not in seen:
            out.append(f"{rel}:{header}: ui-check has no `{axis}` line")
    return out


# --- the gate -----------------------------------------------------------------------

def _branch_paths(root: Path) -> set[str] | None:
    import test_select  # noqa: PLC0415

    try:
        return test_select.changed_paths(root, None)
    except test_select.Unjudgeable:
        return None


def check(root: Path) -> tuple[list[str], list[str]]:
    hard: list[str] = []
    soft: list[str] = []
    try:
        ref = integration_ref(root)
    except GitReadError as exc:
        return [f"cannot read the integration ref: {exc}"], soft
    if ref is None:
        return hard, ["no branch range against an integration ref — no plan is checked"]
    plans = bound_plans(root, ref)
    if not plans:
        return hard, soft
    regs = registries(root)
    globs, declared = ui_globs(root, ref, regs)
    if not declared:
        soft.append("no UI paths declared (`areas.ui` in testing.local.json, or a design "
                    "contract's `paths`) — the gate cannot tell UI work; `\"ui\": []` says there is none")
    changed = _branch_paths(root)
    if changed is None:
        branch_ui = True
        soft.append("the branch's change cannot be listed — every bound plan is held to the block")
    else:
        branch_ui = any(path_matches(g, p) for p in changed for g in globs)
    by_surface = {r["surface"]: r for r in regs}
    for rel, raw in sorted(plans.items()):
        text = _readable(raw)
        contracts = declared_contracts(text, regs)
        blocks, opt_outs = parse_blocks(text)
        if opt_outs and not blocks:
            line, reason = opt_outs[0]
            if contracts:
                hard.append(f"{rel}:{line}: `ui-check: n/a`, but the plan declares "
                            f"{', '.join(contracts)} — a contract's UI is never only carried along")
            elif not re.search(r"\w", reason):
                hard.append(f"{rel}:{line}: `ui-check: n/a` without a reason")
            continue
        if not (contracts or branch_ui or blocks):
            continue
        if not blocks:
            why = (f"it declares {', '.join(contracts)}" if contracts else
                   "the branch changes UI paths")
            hard.append(f"{rel}: no `ui-check:` block — {why}; answer each axis ({', '.join(AXES)}), "
                        f"or `ui-check: n/a — <reason>` if this plan only carries UI along")
            continue
        for surface in contracts:
            # one contract may answer in an unnamed block; several each need their own
            if surface not in blocks and not (len(contracts) == 1 and "" in blocks):
                hard.append(f"{rel}: declares {surface} but has no `ui-check {surface}:` block — "
                            f"one block per surface")
        for surface, (header, entries) in blocks.items():
            reg = by_surface.get(surface) or (by_surface.get(contracts[0]) if len(contracts) == 1 else None)
            hard += block_findings(root, rel, header, entries, reg, regs)
    return hard, soft


def summary(root: Path, texts: dict[str, str]) -> list[str]:
    """For the review bundle and the digest: each plan's block with its counts, and
    every `ui-check: n/a` line with its reason — what the reviewer has to judge."""
    out: list[str] = []
    for rel, raw in sorted(texts.items()):
        blocks, opt_outs = parse_blocks(_readable(raw))
        for line, reason in opt_outs:
            out.append(f"- `{rel}:{line}` ui-check **n/a** — {reason or '(no reason)'}: is its UI "
                       f"really only carried along?")
        for surface, (_header, entries) in blocks.items():
            na = sum(1 for _l, _a, v in entries if _NA.match(v))
            inherited = sum(1 for _l, _a, v in entries if v.lower() == "inherited")
            rules = next((v for _l, a, v in entries if a == "rules"), "")
            out.append(f"- `{rel}` ui-check{' ' + surface if surface else ''}: {len(entries)} axes, "
                       f"{na} n/a, {inherited} inherited; rules: {rules or '(none)'}")
    return out


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    hard, soft = check(root)
    for note in soft:
        print(f"ui-check: note: {note}")
    if hard:
        print("ui-check: FAILED:")
        for h in hard:
            print(f"  - {h}")
        return 1
    print("ui-check: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
