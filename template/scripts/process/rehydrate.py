#!/usr/bin/env python3
"""rehydrate — what /prime reads, printed by a hook after every compaction.

    python3 scripts/process/rehydrate.py              # print the context (a SessionStart hook)
    python3 scripts/process/rehydrate.py --install    # add the hook to .claude/settings.json (idempotent)
    python3 scripts/process/rehydrate.py --check      # exit 1 when the hook is missing

The rules say "after a compaction re-read the kernel, the mandatory rules
and the plan's Decisions ledger" — but a sentence that has to survive the
compaction it warns about is not a mechanism. This is one: Claude Code runs
`SessionStart` hooks after a compaction (`source: compact`) and after a
resume, and feeds their stdout to the session as context. The hook prints
exactly what /prime reads and nothing more (every compaction pays for it):
the kernel block, the mandatory rules, and the branch's working memory
(`process_context.py`: active plans with tier, issue, DECISION ledger,
open DECISION NEEDED questions, the next unchecked task).

`--install` merges one hook entry into `.claude/settings.json` (matcher
`compact|resume`) without touching anything else there; the file stays
the project's. Stdlib only."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

KERNEL = "docs/process/kernel.md"
RULES = "docs/process/mandatory-rules.md"
SETTINGS = ".claude/settings.json"
HOOK_CMD = "python3 scripts/process/rehydrate.py"
MATCHER = "compact|resume"
START, END = "<!-- KERNEL:START -->", "<!-- KERNEL:END -->"
MAX_DECISIONS = 12  # the latest ones; older decisions are in the plan, which the session reads on demand


def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def kernel_block(root: Path) -> str:
    text = _read(root / KERNEL)
    if START in text and END in text:
        return text.split(START, 1)[1].split(END, 1)[0].strip()
    return text.strip()


def context(root: Path) -> dict:
    ctx_py = root / "scripts/process/process_context.py"
    if not ctx_py.is_file():
        return {}
    try:
        r = subprocess.run([sys.executable, str(ctx_py), str(root)], capture_output=True, text=True, timeout=30)
        return json.loads(r.stdout) if r.returncode == 0 else {}
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return {}


def render(root: Path) -> str:
    out = ["# Rehydrated process context (SessionStart hook — the compaction dropped this; it binds every turn)",
           "", kernel_block(root), "", "## Mandatory rules (full text)", "", _read(root / RULES).strip(), ""]
    ctx = context(root)
    if ctx:
        out.append(f"## Working memory of branch `{ctx.get('branch')}`")
        for p in ctx.get("active_plans", []):
            out.append(f"- plan `{p['file']}` tier {p.get('tier')} issue {p.get('issue')}")
            decisions = p.get("decisions", [])
            if len(decisions) > MAX_DECISIONS:  # a plan with 113 decisions is a log; every compaction pays
                out.append(f"  - ({len(decisions) - MAX_DECISIONS} earlier decisions in the plan — read it "
                           "before touching what they decided)")
            for d in decisions[-MAX_DECISIONS:]:
                out.append(f"  - DECISION {d}")
            for q in p.get("open_questions", []):
                out.append(f"  - OPEN QUESTION (do not decide it yourself): DECISION NEEDED {q}")
        for f in ctx.get("spec_features", []):
            nxt = f.get("next_task")
            out.append(f"- spec `{f['dir']}`: {f.get('tasks_done')} done, {f.get('tasks_open')} open"
                       + (f" — next: {nxt}" if nxt else ""))
        for key in ("state_file", "latest_journal"):
            if ctx.get(key):
                out.append(f"- {key.replace('_', ' ')}: `{ctx[key]}` (read it before the next tool call)")
        if ctx.get("inbox_items"):
            out.append(f"- inbox: {ctx['inbox_items']} item(s)")
    return "\n".join(out).rstrip() + "\n"


def _hook_entry() -> dict:
    return {"matcher": MATCHER, "hooks": [{"type": "command", "command": HOOK_CMD, "timeout": 30,
                                           "statusMessage": "Rehydrating process context..."}]}


def _has_hook(settings: dict) -> bool:
    for entry in settings.get("hooks", {}).get("SessionStart", []):
        for h in entry.get("hooks", []):
            if HOOK_CMD in str(h.get("command", "")):
                return True
    return False


def install(root: Path) -> int:
    p = root / SETTINGS
    settings: dict = {}
    raw = _read(p) if p.is_file() else ""
    if p.is_file():
        try:
            settings = json.loads(raw)
        except ValueError:
            print(f"rehydrate: {SETTINGS} is not valid JSON — fix it, then --install again", file=sys.stderr)
            return 1
    if _has_hook(settings):
        print(f"rehydrate: hook already in {SETTINGS}")
        return 0
    settings.setdefault("hooks", {}).setdefault("SessionStart", []).append(_hook_entry())
    p.parent.mkdir(parents=True, exist_ok=True)
    # keep the file's own escaping so the diff is the hook and nothing else
    p.write_text(json.dumps(settings, indent=2, ensure_ascii="\\u" in raw) + "\n", encoding="utf-8")
    print(f"rehydrate: SessionStart hook ({MATCHER}) added to {SETTINGS}")
    return 0


def check(root: Path) -> int:
    p = root / SETTINGS
    try:
        settings = json.loads(_read(p)) if p.is_file() else {}
    except ValueError:
        settings = {}
    if _has_hook(settings):
        print(f"rehydrate: SessionStart hook (compact|resume) installed in {SETTINGS}")
        return 0
    print(f"rehydrate: no SessionStart hook in {SETTINGS} — run `python3 scripts/process/rehydrate.py --install`",
          file=sys.stderr)
    return 1


def main(argv: list[str]) -> int:
    root = Path.cwd()
    top = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    if top.returncode == 0 and top.stdout.strip():
        root = Path(top.stdout.strip())
    if "--install" in argv:
        return install(root)
    if "--check" in argv:
        return check(root)
    sys.stdout.write(render(root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
