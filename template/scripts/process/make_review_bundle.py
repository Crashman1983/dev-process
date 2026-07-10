#!/usr/bin/env python3
"""make_review_bundle: assemble the read-only bundle an independent reviewer
consumes — the process's portable interface to ANY reviewing model.

Verification independence (verification-independence.md) says a Tier 2+ review
runs in a fresh process over a read-only bundle, not in the producing context —
and a Tier 3 review preferably on another model family. What makes that
portable is the *artifact*: one self-contained markdown document any model can
take as its whole input. This tool assembles it:

  1. the reviewer preamble (role, independence expectations, read-only rule);
  2. the kernel block (the binding rules, from docs/process/kernel.md);
  3. the review checklist (what a review actually checks);
  4. the product frame (PRODUCT.md — direction to judge the change against);
  5. the active plan(s) under review;
  6. the diff (BASE...HEAD, three-dot: what the branch adds);
  7. the exact output grammar the gates parse (REVIEW / FINDING lines) —
     imported from check_review.py, so the bundle can never drift from the gate.

Sources that cannot be read are named in place, never silently skipped.

Usage:
    make_review_bundle.py [--base REF] [-o FILE]

--base defaults to the first of origin/main, main, origin/master, master that
git can resolve. Output goes to stdout unless -o is given. Read-only; never a
gate, never in CI. Stdlib only.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# the gate owns the grammar; importing it keeps the bundle's instructions
# byte-honest with what check_review.py will actually parse
import check_review as _review_gate

KERNEL_DOC = "docs/process/kernel.md"
CHECKLIST = "docs/process/review-checklist.md"
PRODUCT = "PRODUCT.md"
PLANS = ".process-work/plans"
DEFAULT_BASES = ("origin/main", "main", "origin/master", "master")


def _read(root: Path, rel: str) -> str | None:
    p = root / rel
    try:
        return p.read_text(encoding="utf-8") if p.is_file() else None
    except (UnicodeDecodeError, OSError):
        return None


def _kernel_block(root: Path) -> str | None:
    text = _read(root, KERNEL_DOC)
    if text is None:
        return None
    start, end = "<!-- KERNEL:START -->", "<!-- KERNEL:END -->"
    if start in text and end in text:
        return text.split(start, 1)[1].split(end, 1)[0].strip()
    return None


def _git(root: Path, *args: str) -> str | None:
    try:
        r = subprocess.run(["git", "-C", str(root), *args],
                           capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout if r.returncode == 0 else None


def _resolve_base(root: Path, base: str | None) -> str | None:
    candidates = (base,) if base else DEFAULT_BASES
    for c in candidates:
        if c and _git(root, "rev-parse", "--verify", "--quiet", f"{c}^{{commit}}") is not None:
            return c
    return None


def _active_plans(root: Path) -> list[Path]:
    d = root / PLANS
    if not d.is_dir():
        return []
    return sorted(p for p in d.glob("*.md"))  # archive/ is finished work


def _grammar_section() -> str:
    fields = " ".join(f"{k}=…" for k in sorted(_review_gate.REQUIRED))
    return f"""Record your verdict EXACTLY in this grammar — the gates parse it verbatim,
free-form prose is invisible to them:

    REVIEW {fields}

- `verdict`: one of {sorted(_review_gate.VERDICTS)}.
- `independence`: comma-joined tokens from {sorted(_review_gate.INDEP_TOKENS)} —
  attest honestly what you are: reading this bundle in a fresh context is
  `bundle,non-implementing`; add `cross-model` only if you are a different
  model family than the implementer, else declare `single-family`.
- `tier`/`round`: integers; `work`: the issue number or plan slug under review.

For each finding, one line:

    FINDING sev=<blocker|major|minor|nit> action=<fix|accept|follow-up> issue=<ref|-> <title>

Judge against the checklist and the rules above; cite file:line evidence; a
`pass` with unfixed blockers is a false green — verdict `block` instead."""


def build(root: Path, base: str | None) -> str:
    out: list[str] = []
    add = out.append

    add("# Review bundle — read-only\n")
    add("You are an INDEPENDENT reviewer. This bundle is your complete input: "
        "do not consult the implementing agent's context, do not edit anything, "
        "and do not trust claims you can check in the diff. Your deliverable is "
        "a verdict plus findings in the exact grammar at the end.\n")

    kernel = _kernel_block(root)
    add("## The binding rules (kernel)\n")
    add(kernel + "\n" if kernel else "*(unavailable: docs/process/kernel.md has no readable kernel block)*\n")

    checklist = _read(root, CHECKLIST)
    add("## What a review checks\n")
    add(checklist + "\n" if checklist else "*(unavailable: docs/process/review-checklist.md missing)*\n")

    product = _read(root, PRODUCT)
    add("## Product frame (judge direction against this)\n")
    add(product + "\n" if product else "*(unavailable: PRODUCT.md missing)*\n")

    add("## Plan(s) under review\n")
    plans = _active_plans(root)
    if plans:
        for p in plans:
            add(f"### {p.name}\n")
            body = _read(root, str(p.relative_to(root)))
            add((body or "*(unreadable)*") + "\n")
    else:
        add("*(no active plan in .process-work/plans — review the diff against "
            "the checklist and rules alone, and say so in your verdict)*\n")

    resolved = _resolve_base(root, base)
    add("## Diff under review\n")
    if resolved is None:
        add("*(unavailable: no usable base ref — pass --base explicitly; "
            "git may be absent or the repo unborn)*\n")
    else:
        diff = _git(root, "diff", f"{resolved}...HEAD")
        if diff is None:
            add(f"*(unavailable: `git diff {resolved}...HEAD` failed)*\n")
        elif not diff.strip():
            add(f"*(empty: HEAD adds nothing over {resolved})*\n")
        else:
            lines = diff.count("\n")
            add(f"Base: `{resolved}` (three-dot: what the branch adds). "
                f"{lines} diff lines.\n")
            if lines > 4000:
                add("*(large diff — consider a per-area pass; nothing was truncated)*\n")
            add("```diff\n" + diff + ("\n" if not diff.endswith("\n") else "") + "```\n")

    add("## Required output grammar\n")
    add(_grammar_section() + "\n")
    return "\n".join(out)


def main(argv: list[str]) -> int:
    base = None
    out_file = None
    if "--base" in argv:
        base = argv[argv.index("--base") + 1]
    if "-o" in argv:
        out_file = argv[argv.index("-o") + 1]
    text = build(Path.cwd(), base)
    if out_file:
        Path(out_file).write_text(text, encoding="utf-8")
        print(f"review bundle written to {out_file}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
