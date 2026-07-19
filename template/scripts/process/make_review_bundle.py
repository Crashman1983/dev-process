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
  7. the output grammar: the REVIEW line imported from check_review.py (the
     gate that parses it — that half cannot drift), plus the FINDING line whose
     owner is the github-issues module's report gate (journal-state-plans.md);
     a template test pins the FINDING tokens to that gate's enums.

Sources that cannot be read are named in place, never silently skipped.

Usage:
    make_review_bundle.py [--base REF] [--plan SLUG] [-o FILE]

--plan narrows the bundled plans to filenames containing SLUG — for parallel
efforts, so the reviewer sees the one plan under review, not all of them.

--base defaults to the first of origin/main, main, origin/master, master that
git can resolve. Output goes to stdout unless -o is given. The repo root is
resolved via git (works from a subdirectory); read-only; never a gate, never in
CI. Stdlib only.
"""
from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from pathlib import Path

# check_review.py owns the REVIEW grammar; check_kernel.py owns kernel-block
# extraction — importing both keeps this tool byte-honest with the gates
sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling import
import check_kernel as _kernel_gate  # noqa: E402
import check_review as _review_gate  # noqa: E402

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
    text = _read(root, _kernel_gate.KERNEL_DOC)
    if text is None:
        return None
    # >1 START marker is ambiguous (the kernel gate hard-fails it) — refusing
    # here beats silently bundling whichever block happens to come first
    if text.count(_kernel_gate._START) > 1:
        return None
    return _kernel_gate._block(text)


def _git(root: Path, *args: str) -> str | None:
    try:
        # errors="replace": a non-UTF-8 tracked text file must degrade to
        # replacement chars in the diff, not crash the whole bundle
        r = subprocess.run(["git", "-C", str(root), *args],
                           capture_output=True, text=True, timeout=60,
                           encoding="utf-8", errors="replace")
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout if r.returncode == 0 else None


def _git_bytes(root: Path, *args: str) -> bytes | None:
    """Raw Git stdout for artifact hashing; decoding must not change bytes."""
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout if result.returncode == 0 else None


def _repo_root(cwd: Path) -> Path:
    """The git toplevel when available — running from a subdirectory must not
    silently lose the root-level plan/kernel/PRODUCT sources."""
    top = _git(cwd, "rev-parse", "--show-toplevel")
    return Path(top.strip()) if top and top.strip() else cwd


def _resolve_base(root: Path, base: str | None) -> str | None:
    candidates = (base,) if base else DEFAULT_BASES
    for c in candidates:
        if c and _git(root, "rev-parse", "--verify", "--quiet", f"{c}^{{commit}}") is not None:
            return c
    return None


def _active_plans(root: Path, plan_filter: str | None) -> list[Path]:
    d = root / PLANS
    if not d.is_dir():
        return []
    plans = sorted(p for p in d.glob("*.md"))  # archive/ is finished work
    if plan_filter:
        # parallel efforts: 8 active plans would bury the reviewer in 7
        # irrelevant ones — --plan narrows to the effort under review
        plans = [p for p in plans if plan_filter in p.name]
    return plans


def _review_artifact(root: Path, base_ref: str) -> tuple[str, str, str, bytes] | None:
    """Resolved endpoints, SHA-256, and exact bytes of the reviewed diff."""
    base = _git(root, "merge-base", base_ref, "HEAD")
    head = _git(root, "rev-parse", "HEAD")
    if not base or not head:
        return None
    base_sha = base.strip()
    head_sha = head.strip()
    diff = _git_bytes(root, "diff", "--binary", f"{base_sha}...{head_sha}")
    if diff is None:
        return None
    return base_sha, head_sha, hashlib.sha256(diff).hexdigest(), diff


def _grammar_section() -> str:
    # REVIEW fields/enums come from the gate that parses them (import above).
    # The FINDING line's owner is check_issues.py (github-issues module — not
    # importable here, it renders conditionally); its sev/action tokens are
    # duplicated below and pinned to that gate's enums by a template test.
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


def build(root: Path, base: str | None, plan_filter: str | None = None) -> str:
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
    plans = _active_plans(root, plan_filter)
    if plans:
        for p in plans:
            add(f"### {p.name}\n")
            body = _read(root, str(p.relative_to(root)))
            add((body or "*(unreadable)*") + "\n")
    elif plan_filter:
        add(f"*(no active plan matches --plan {plan_filter!r} — check the "
            f"filter, or drop it to bundle every active plan)*\n")
    else:
        add("*(no active plan in .process-work/plans — review the diff against "
            "the checklist and rules alone, and say so in your verdict)*\n")

    resolved = _resolve_base(root, base)
    add("## Diff under review\n")
    if resolved is None:
        add("*(unavailable: no usable base ref — pass --base explicitly; "
            "git may be absent or the repo unborn)*\n")
    else:
        artifact = _review_artifact(root, resolved)
        if artifact is None:
            add(f"*(unavailable: `git diff {resolved}...HEAD` failed)*\n")
        else:
            base_sha, head_sha, digest, diff_bytes = artifact
            add(f"REVIEW_ARTIFACT base={base_sha} head={head_sha} diff={digest}\n")
            diff = diff_bytes.decode("utf-8", errors="replace")
            if not diff.strip():
                add(f"*(empty: HEAD adds nothing over {resolved})*\n")
            else:
                lines = diff.count("\n")
                add(f"Base: `{resolved}` resolved to `{base_sha}` "
                    "(three-dot: what the branch adds). "
                    f"{lines} diff lines.\n")
                if lines > 4000:
                    add("*(large diff — consider a per-area pass; nothing was truncated)*\n")
                status = _git(root, "status", "--porcelain")
                if status and status.strip():
                    add("*(working tree dirty — uncommitted changes are NOT in this "
                        "diff; only committed work is under review)*\n")
                # a diff of a markdown file carries its own ``` runs, which would
                # close a plain fence early and corrupt everything after it — fence
                # with more backticks than the longest run inside (min 4)
                longest = max((len(m) for m in re.findall(r"`+", diff)), default=0)
                fence = "`" * max(4, longest + 1)
                add(f"{fence}diff\n" + diff + ("\n" if not diff.endswith("\n") else "") + fence + "\n")

    add("## Required output grammar\n")
    add(_grammar_section() + "\n")
    return "\n".join(out)


USAGE = "usage: make_review_bundle.py [--base REF] [--plan SLUG] [-o FILE]"


def _opt(argv: list[str], flag: str) -> str | None:
    if flag not in argv:
        return None
    i = argv.index(flag)
    if i + 1 >= len(argv):
        raise SystemExit(f"{USAGE} — {flag} needs a value")
    return argv[i + 1]


def main(argv: list[str]) -> int:
    base = _opt(argv, "--base")
    out_file = _opt(argv, "-o")
    plan_filter = _opt(argv, "--plan")
    # an unknown flag must be a hard error, not silently ignored — a typo'd
    # --base would hand the reviewer a bundle diffed against the wrong ref
    known = {"--base", "-o", "--plan"}
    consumed = {i for f in known if f in argv
                for i in (argv.index(f), argv.index(f) + 1)}
    extra = [a for i, a in enumerate(argv) if i not in consumed]
    if extra:
        raise SystemExit(f"{USAGE} — unknown argument(s): {' '.join(extra)}")
    text = build(_repo_root(Path.cwd()), base, plan_filter)
    if out_file:
        Path(out_file).write_text(text, encoding="utf-8")
        print(f"review bundle written to {out_file}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
