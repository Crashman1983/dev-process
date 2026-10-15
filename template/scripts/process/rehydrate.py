#!/usr/bin/env python3
"""rehydrate — what /prime reads, printed by a hook after every compaction.

    python3 scripts/process/rehydrate.py              # print the context (a SessionStart hook)
    python3 scripts/process/rehydrate.py --install    # add the hook to .claude/settings.json (idempotent)
    python3 scripts/process/rehydrate.py --check      # exit 1 when the hook is missing
    python3 scripts/process/rehydrate.py --codex      # the same for a Codex session: SessionStart JSON
    python3 scripts/process/rehydrate.py --codex --install|--check   # its local .codex/hooks.json

The rules say "after a compaction re-read the kernel, the mandatory rules
and the plan's Decisions ledger" — but a sentence that has to survive the
compaction it warns about is not a mechanism. This is one: Claude Code runs
`SessionStart` hooks after a compaction (`source: compact`) and after a
resume, and feeds their stdout to the session as context. The hook prints
exactly what /prime reads and nothing more (every compaction pays for it):
the kernel block, the mandatory rules, and the branch's working memory
(`process_context.py`, scoped to the branch: its plans with tier, issue,
DECISION ledger, open DECISION NEEDED questions, the next unchecked task;
every other plan and spec dir as one capped index line).

`--install` merges one hook entry into `.claude/settings.json` (matcher
`compact|resume`) without touching anything else there; the file stays
the project's. `--codex` gives a Codex session the same context as Codex's
SessionStart JSON — the kernel, the rules, the Codex policy, `AGENTS.md` or
`CLAUDE.md` and the policy's `context_sources` — whole or not at all: a
missing source stops the session visibly, never a partial context. Its hook
lives in the local, ignored `.codex/hooks.json` (add `.codex/` to the
project's `.gitignore`). Stdlib only."""
from __future__ import annotations

import json
import os
import shlex
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
MAX_INDEX = 10  # other work, one line; the full index is a process_context.py call away
CODEX_SETTINGS = ".codex/hooks.json"
CODEX_MATCHER = "^(startup|resume|clear|compact)$"
CODEX_CONTEXT_MAX_BYTES = 128_000
CODEX_POLICY = "docs/process/model-policy.codex.json"
CODEX_LOCAL_POLICY = "docs/process/model-policy.codex.local.json"


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
        r = subprocess.run([sys.executable, str(ctx_py), str(root)], capture_output=True, text=True, timeout=30,
                           check=False)
        return json.loads(r.stdout) if r.returncode == 0 else {}
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return {}


def _overlay_pairs(root: Path) -> list[tuple[str, str]]:
    """(template file, overlay) for each project overlay — the gate's own reading
    (`check_overlays`), so the session and the gate never disagree on what is one."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        import check_overlays as co  # noqa: PLC0415
    except ImportError:
        return []
    out = []
    for p in co.overlays(root):
        m = co.HEAD.search(co.unfenced(_read(p)).lstrip("\ufeff"))
        out.append((os.path.normpath(m.group("path")) if m else "(unparsed overlay-of)",
                    p.relative_to(root).as_posix()))
    return out


def _inline_overlays(root: Path, docs: tuple[str, ...]) -> list[str]:
    """The overlays of docs whose full text is in the context (the rules): a pointer
    beside a full template rule would lose to it — the overlay goes in whole."""
    return [f"## Project overlay `{ov}` (of `{doc}` — it binds in this project)\n\n{_read(root / ov).strip()}"
            for doc, ov in _overlay_pairs(root) if doc in docs]


def render(root: Path) -> str:
    out = ["# Rehydrated process context (SessionStart hook — the compaction dropped this; it binds every turn)",
           "", kernel_block(root), "", "## Mandatory rules (full text)", "", _read(root / RULES).strip(), ""]
    inline = _inline_overlays(root, (RULES,))  # the kernel takes no overlay (check_overlays.UNOVERLAYABLE)
    out += [*inline, ""] if inline else []
    pairs = _overlay_pairs(root)
    if pairs:
        out += ["## Project overlays — read each with its template file (docs/process/overlays.md)", "",
                *(f"- `{doc}` → `{ov}`" for doc, ov in pairs), ""]
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
        def ref(n: int | None) -> str:
            return f"#{n}" if n is not None else "no issue"
        others = [f"`{p['file']}` {ref(p['issue'])}" for p in ctx.get("other_plans", [])] + [
            f"`{s['dir']}` {ref(s['issue'])}" + (" done" if s.get("done") else "")
            for s in ctx.get("other_specs", [])]
        if others:
            head = ("not this branch's work" if ctx.get("scope", {}).get("source") != "none"
                    else "no issue in scope")
            more = f" … +{len(others) - MAX_INDEX} more" if len(others) > MAX_INDEX else ""
            out.append(f"- other plans/specs ({head}; `process_context.py --issue N` for one): "
                       + ", ".join(others[:MAX_INDEX]) + more)
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


def codex_sources(root: Path) -> list[str]:
    """What a Codex session must read: the kernel, the rules, the Codex policy and its
    local file when there is one, the harness anchor that exists, and the policies'
    `context_sources`. A malformed policy or a source outside the repository raises —
    the session then stops instead of starting on part of the context."""
    sources = [KERNEL, RULES, CODEX_POLICY]
    if (root / CODEX_LOCAL_POLICY).exists():
        sources.append(CODEX_LOCAL_POLICY)
    sources += [a for a in ("AGENTS.md", "CLAUDE.md") if (root / a).is_file()]  # each anchor the project has
    # the overlays of what the context carries in full go in whole beside it
    sources += [ov for doc, ov in _overlay_pairs(root) if doc in sources and ov not in sources]
    for name in (CODEX_POLICY, CODEX_LOCAL_POLICY):
        if not (root / name).exists():
            continue
        data = json.loads((root / name).read_text(encoding="utf-8"))
        extra = data.get("context_sources", []) if isinstance(data, dict) else None
        if not isinstance(extra, list) or not all(isinstance(s, str) and s for s in extra):
            raise ValueError(f"{name}: `context_sources` must be a list of repository paths")
        for s in extra:
            if Path(s).is_absolute() or ".." in Path(s).parts:
                raise ValueError(f"{name}: context source {s!r} is outside the repository")
            if s not in sources:
                sources.append(s)
    return sources


def codex_output(root: Path) -> dict:
    """The whole context, or a visible stop — never part of it."""
    try:
        sections = []
        for source in codex_sources(root):
            content = (root / source).read_text(encoding="utf-8")
            if not content.strip():
                raise ValueError(f"{source} is empty")
            if source.endswith(".json") and not isinstance(json.loads(content), dict):
                raise ValueError(f"{source} must be a JSON object")
            sections.append(f"## Source: {source}\n\n{content}")
        sections.append(render(root))
        text = "# Codex session context\n\n" + "\n\n".join(sections)
        if len(text.encode("utf-8")) > CODEX_CONTEXT_MAX_BYTES:
            raise ValueError(f"the context exceeds {CODEX_CONTEXT_MAX_BYTES} bytes")
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        reason = f"the process context was not loaded: {exc}"
        return {"continue": False, "stopReason": reason, "systemMessage": reason}
    return {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}


def codex_hook_entry() -> dict:
    # the absolute script path lives only in the local, ignored hook file; the
    # session's cwd stays its own, so the same renderer reads each clone's root
    command = f"{shlex.quote(sys.executable)} {shlex.quote(str(Path(__file__).resolve()))} --codex"
    return {"matcher": CODEX_MATCHER, "hooks": [{
        "type": "command", "command": command, "timeout": 45, "statusMessage": "Loading the process context",
        "additionalContextLimit": 0}]}  # the script bounds the size itself


def _exclude_codex(root: Path) -> None:
    """`.codex/` holds a host-local hook: keep it out of `git status` via the clone's
    own exclude file (an untracked file would read as a dirty worktree to dispatch)."""
    r = subprocess.run(["git", "rev-parse", "--git-path", "info/exclude"], cwd=root, capture_output=True,
                       text=True, check=False)
    if r.returncode != 0:
        return
    exclude = (root / r.stdout.strip()) if not Path(r.stdout.strip()).is_absolute() else Path(r.stdout.strip())
    try:
        lines = exclude.read_text(encoding="utf-8").splitlines() if exclude.exists() else []
        if "/.codex/" not in lines:
            exclude.parent.mkdir(parents=True, exist_ok=True)
            exclude.write_text("\n".join([*lines, "/.codex/"]) + "\n", encoding="utf-8")
    except OSError:
        pass  # a missed exclude costs a dirty status line, never the hook


def codex_config(root: Path, *, installing: bool) -> int:
    """Install or check the hook's definition — never its runtime approval (`/hooks`)."""
    path = root / CODEX_SETTINGS
    try:
        config = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        if not isinstance(config, dict):
            raise TypeError("expected a JSON object")
        hooks = config.setdefault("hooks", {})
        if not isinstance(hooks, dict):
            raise TypeError("hooks must be an object")
        groups = hooks.setdefault("SessionStart", [])
        if not isinstance(groups, list):
            raise TypeError("SessionStart must be an array")
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        print(f"rehydrate: {CODEX_SETTINGS}: {exc}", file=sys.stderr)
        return 1
    entry = codex_hook_entry()
    if entry in groups:
        print(f"rehydrate: the Codex SessionStart hook is in {CODEX_SETTINGS}; approve it in /hooks")
        return 0
    if not installing:
        print("rehydrate: the Codex SessionStart hook is missing or changed — run "
              "`python3 scripts/process/rehydrate.py --codex --install`", file=sys.stderr)
        return 1
    # from another checkout: replace only our own handler, never another event or handler
    for index, group in enumerate(groups):
        handlers = group.get("hooks", []) if isinstance(group, dict) else []
        if not isinstance(handlers, list) or len(handlers) != 1 or not isinstance(handlers[0], dict):
            continue
        try:
            args = shlex.split(handlers[0].get("command", ""))
        except (ValueError, TypeError):
            continue
        if len(args) == 3 and Path(args[1]).name == "rehydrate.py" and args[2] == "--codex":
            groups[index] = entry
            break
    else:
        groups.append(entry)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    _exclude_codex(root)
    print(f"rehydrate: Codex SessionStart hook added to {CODEX_SETTINGS}; review and approve it in /hooks")
    return 0


def main(argv: list[str]) -> int:
    root = Path.cwd()
    top = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=False)
    if top.returncode == 0 and top.stdout.strip():
        root = Path(top.stdout.strip())
    if "--codex" in argv:
        if "--install" in argv or "--check" in argv:
            return codex_config(root, installing="--install" in argv)
        sys.stdout.write(json.dumps(codex_output(root), ensure_ascii=False) + "\n")
        return 0
    if "--install" in argv:
        return install(root)
    if "--check" in argv:
        return check(root)
    sys.stdout.write(render(root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
