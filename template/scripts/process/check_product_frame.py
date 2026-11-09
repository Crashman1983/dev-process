#!/usr/bin/env python3
"""product-frame gate: keep PRODUCT.md honest — present, state-readable, and
free of dead references. Core and always on: the product frame is the
direction development is checked against, so its enforcement must not hinge
on an optional module.

Mechanical honesty only — prose quality (are the goals good? the non-goals
complete?) is judgment and belongs to the review gate (`review-checklist.md`,
Product frame). What this gate checks:

  - HARD: PRODUCT.md missing. It is a core artifact and ships with the
    template; deleting it removes the frame — absence is a violation, not
    pre-adoption.
  - HARD: no recognizable `status:` line, or a value outside
    `not-onboarded | onboarded` — the state axis must stay readable.
  - SOFT: `status: not-onboarded` — expected before the start-here onboarding
    dialogue has filled the frame; placeholders are allowed in this state.
  - HARD once onboarded: leftover placeholder lines. An onboarded frame still
    holding placeholders claims direction it does not have.
  - HARD: an `ADR-NNNN` reference that resolves to no decision record
    (docs/process/adr/ is core).
  - HARD when the feature registry exists: a story reference that resolves to
    no story — `STORY-NNNN` in the template's flat layout, the loose form of the
    project's `id_pattern` otherwise (`registry_config`), where a ref in that
    form the strict pattern refuses is a SOFT note. SOFT note when the registry
    is absent — not checkable, honest degradation.

Fenced code blocks are quotations, not claims — ignored for refs and
placeholders. Pure stdlib.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

FRAME = "PRODUCT.md"

# the decision-records gate (core, co-rendered) owns ADR file identity; the
# review gate owns fence stripping; registry_config (core) owns where the
# registry lives — import, don't copy (one owner per behavior)
sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling import
import registry_config  # noqa: E402
from check_decisions import ADR_DIR, adr_exists  # noqa: E402
from check_review import _unfenced as _strip_fences  # noqa: E402

STATUS = re.compile(r"^\s*(?:[-*+]\s+)?[*_]*status[*_]*:\s*(.+?)\s*$", re.MULTILINE)
STATES = {"not-onboarded", "onboarded"}
ADR_REF = re.compile(r"\bADR-(\d+)\b")
STORY_REF = re.compile(r"\bSTORY-(\d+)\b")  # any width; normalized like ADR refs
PLACEHOLDER = re.compile(r"^\s*>\s*_Placeholder", re.MULTILINE)
HEADING = re.compile(r"^##\s+(.*)$", re.MULTILINE)
HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)


def _unfenced(text: str) -> str:
    """Drop fenced code blocks (the review gate's length-aware stripper) and
    HTML comments — a quoted or commented example is not a claim. The seed
    itself uses an HTML comment for the status-flip instruction."""
    return _strip_fences(HTML_COMMENT.sub("", text))


def _story_ids(stories: list[registry_config.Story]) -> set[str]:
    """Registered story ids — resolved by the `id` field like the registry
    gate does, falling back to the filename stem, so a story living in a
    non-canonical filename still resolves."""
    return registry_config.story_ids(stories) | {s.path.stem for s in stories}


def _leftover_placeholders(text: str) -> list[str]:
    """Where placeholder lines survive: section headings when a heading
    encloses the hit, '(before the first section)' otherwise. Scans the WHOLE
    text — a placeholder above the first heading must not pass green."""
    out: list[str] = []
    heads = list(HEADING.finditer(text))
    first = heads[0].start() if heads else len(text)
    if PLACEHOLDER.search(text[:first]):
        out.append("(before the first section)")
    for i, m in enumerate(heads):
        start = m.end()
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        if PLACEHOLDER.search(text[start:end]):
            out.append(m.group(1).strip())
    return out


def check(root: Path) -> tuple[list[str], list[str]]:
    hard: list[str] = []
    soft: list[str] = []
    f = root / FRAME
    if not f.is_file():
        return ([f"{FRAME} missing — the product frame is a core artifact; "
                 f"restore it (the template ships a scaffold)"], [])
    try:
        text = _unfenced(f.read_text(encoding="utf-8"))
    except UnicodeDecodeError:
        return ([f"{FRAME}: not valid UTF-8"], [])

    m = STATUS.search(text)
    if not m:
        hard.append(f"{FRAME}: no 'status:' line — the frame's state is unreadable "
                    f"(want 'status: not-onboarded' or 'status: onboarded')")
    elif m.group(1) not in STATES:
        hard.append(f"{FRAME}: status {m.group(1)!r} is not one of "
                    f"{sorted(STATES)} (one bare value, no annotation)")
    elif m.group(1) == "not-onboarded":
        soft.append("product frame not onboarded yet — fill it in the start-here "
                    "onboarding dialogue and flip 'status:' to 'onboarded'")
    else:  # onboarded — placeholders now claim direction that is not there
        left = _leftover_placeholders(text)
        if left:
            hard.append(f"{FRAME}: status is 'onboarded' but "
                        f"{len(left)} place(s) still hold a placeholder: "
                        f"{', '.join(left)}")

    for ref in ADR_REF.finditer(text):
        if not adr_exists(root, ref.group(1)):
            hard.append(f"{FRAME}: ADR-{ref.group(1)} referenced but no "
                        f"{ADR_DIR}/adr-{ref.group(1)}-*.md exists")

    sh, ss = _story_findings(root, text)
    return hard + sh, soft + ss


def _story_findings(root: Path, text: str) -> tuple[list[str], list[str]]:
    """Story references against the registry. The flat template layout reads
    `STORY-N`, width-normalized like ADR refs; a project layout reads the loose
    form of its `id_pattern` — a ref in that form the strict pattern refuses is
    a note, never silence."""
    registry, cfg, why = _registry(root)
    if cfg is None or cfg.get("layout") != "capabilities":
        refs = sorted({s.group(1) for s in STORY_REF.finditer(text)})
        if refs and registry is None:
            return [], [f"STORY reference(s) in {FRAME} not checkable — {why}"]
        if not refs:
            return [], []
        ids = _story_ids(registry.stories)
        where = registry.path.relative_to(root).as_posix()
        # width-normalized like ADR refs: STORY-7 resolves to STORY-0007
        return [f"{FRAME}: STORY-{num} referenced but no such story is registered in {where}/"
                for num in refs if f"STORY-{num.zfill(4)}" not in ids and f"STORY-{num}" not in ids], []
    refs = sorted({m.group(0) for m in registry_config.story_ref_pattern(cfg).finditer(text)})
    if refs and registry is None:
        return [], [f"story reference(s) in {FRAME} not checkable — {why}"]
    hard: list[str] = []
    soft: list[str] = []
    ids = _story_ids(registry.stories) if refs else set()
    strict = registry_config.strict_id_pattern(cfg)
    for ref in refs:
        if ref in ids:
            continue
        if not strict.match(ref):
            soft.append(f"{FRAME}: {ref} looks like a story ref but does not match "
                        f"{cfg['id_pattern']} — not checked")
        else:
            hard.append(f"{FRAME}: {ref} referenced but no such story is registered in "
                        f"{registry.path.relative_to(root).as_posix()}/")
    return hard, soft


def _registry(root: Path) -> tuple[registry_config.Registry | None, dict | None, str]:
    """(the registry or None, the configuration or None, why the refs cannot be checked)."""
    if not registry_config.module_active(root):
        return None, None, "no feature registry (feature-registry off)"
    try:
        cfg = registry_config.config(root)
        registry = registry_config.load_registry(root, cfg)
        registry_config.story_ref_pattern(cfg)
    except (registry_config.ConfigError, KeyError, TypeError, AttributeError, re.error) as exc:
        return None, None, (f"the registry configuration is unusable ({exc}; "
                            f"the feature-registry gate says why)")
    if not registry.present:
        return None, cfg, f"no {cfg['root']}/"
    return registry, cfg, ""


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    if not root.is_dir():
        print(f"product-frame: FAILED:\n  - root {root} is not a directory")
        return 1
    hard, soft = check(root)
    for note in soft:
        print(f"product-frame: note: {note}")
    if hard:
        print("product-frame: FAILED:")
        for h in sorted(set(hard)):
            print(f"  - {h}")
        return 1
    print("product-frame: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
