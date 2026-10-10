#!/usr/bin/env python3
"""dispatch — start, list, watch, message and stop worker sessions per
phase, with the model the policy assigns.

    uv run scripts/process/dispatch.py start --issue N --phase brainstorm|plan|execute|review [--tier T] [--branch B] [--title "..."]
    uv run scripts/process/dispatch.py list
    uv run scripts/process/dispatch.py log <branch> [--lines N]   # what the worker shows right now
    uv run scripts/process/dispatch.py say <branch> "<text>"      # a line into an interactive worker
    uv run scripts/process/dispatch.py stop <branch> [--force]
    uv run scripts/process/dispatch.py chain [--dry-run]           # next phase from the reports, then drain
    uv run scripts/process/dispatch.py queue add --issue N --phase P [--tier T] [--branch B] | list
    uv run scripts/process/dispatch.py drain                       # start what the queue may start now
    uv run scripts/process/dispatch.py policy [--tier T]          # what would run

A phase is a session: `plan` opens a worktree on a fresh branch (or reuses
the issue's branch) and starts the planning session; `execute` starts the
build session in that worktree; `review` a fresh reviewing session there.
Between phases the artifacts carry the state (the plan and its `##
Decisions` ledger, the bundle) — the model may change, the worktree stays.
Which model runs which phase comes from `docs/process/model-policy.json`
(tier × phase), with `model-policy.local.json` laid over it when the project
has one; the project's own start command is the `command` template
there. `{model}` and `{prompt}` are substituted inside the argv the
template splits into; the prompt is one argv element. A cell is a model
or `{"model": …, "effort": …, "command": …}`; `{effort}` is substituted
likewise, an element carrying it is dropped when the cell sets no effort,
and a cell's own command wins over the phase's and the top-level one.

Two runners (policy `runner`): `detached` starts the argv headless (own
session, output to a log). `tmux` starts it as a window of one tmux
session (policy `tmux_session`) so a human can open it: the window runs
a non-interactive `sh` that waits a second (the log pipe attaches
meanwhile) and `exec`s the argv with exact POSIX quoting — no aliases, no
rc files, no history; `remain-on-exit` keeps a finished worker's last
screen. Liveness is the pane's own state (`pane_dead`), never a shell
pid. `log` shows the live screen of a tmux worker (escape codes are not
the worker's words) and the log tail of a detached one; `say` types a
line into a tmux worker and checks it left the input line: a busy worker
leaves typed text sitting there (downstream: sessions idled up to 90
minutes on an unsent line), so `say` presses Enter again, and exits
non-zero naming the branch when the text still has not gone.

Phases chain themselves (`chain`, run it from the steward's tick): a
`planned` plan session is stopped and `execute` queued — unless the
process gates are red on its worktree (`plan_gates`: a plan session need not
push, so they would first see the plan at the execute push), or its Tier
2+ plan has no clearing `REVIEW work=<id>-plan` pass (`plan_review_state`):
Tier 2 then waits for the plan session's own subagent review, Tier 3 gets a
dispatched plan review (`review` with `plan_review`) whose pass queues
execute — a pass counts for the plan text it reviewed only; chain acts on
local sessions, so after a remote plan review the steward queues execute;
a `pushed` execute
session with new code on origin beyond the last attestation is stopped and
`review` queued; a `review-pass` review session whose attestation is on
origin is stopped — its report is the train's ticket. `blocked` queues
nothing: that decision is the steward's. A chained stop keeps the worker's
report (a plain `stop` writes `idle`, unless the session's own final
report already ended its phase — that report stays). The queue (`queue.json` beside the
records) is drained in order, and a line the caps or lanes refuse is
skipped, not waited on: a plan or review behind a refused execute still
starts. Local workers start under `nice` (policy `worker_nice`, default
10; 0 = off): the merge train's suite, run at normal priority, keeps its
CPU while workers test (downstream: timeouts under load dropped innocent
passengers). A local session starts on what origin holds: a worktree
behind its pushed branch is fast-forwarded, a diverged one is refused,
and a review refuses one ahead of origin (`sync_worktree`).

Records live in `<git common dir>/process-dispatch/`: one JSON per
branch (pid + process start time, tmux window id, phase, model, log) and
`issues.json` (issue → branch, so the next phase finds the branch after
a stop; an empty branch marks an issue the train merged). `stop` acts only on what this tool started, only when the
recorded process is the recorded one (pid + start time; never pid 0), and
refuses while the worktree has uncommitted or untracked work unless
`--force` — a plan not committed dies with the process. `max_workers`
caps live children on this host; a held full or scoped lane blocks no
start (a session's own test runs queue on the lane, the session does
not), an unknown held lane blocks every phase, and a remote phase sees
neither cap nor lane. A
local start also refuses while the filesystem holding the worktrees is
at or above 90% use (`PROCESS_DISK_LIMIT_PCT`) and names `tidy.py
--apply`: each worktree carries its own venv/node_modules (downstream:
111 merged worktrees filled the disk). Whether a merged worktree may be
removed has one owner here (`merged_worktrees`); the train and tidy ask it.

Trust boundary, plainly: the policy's `command` is executed on the
machine that runs dispatch. It is a repository file — whoever can merge
to it can run code here. Treat it like CI configuration.

The dispatcher decides nothing about the work. Stdlib only."""
from __future__ import annotations

import argparse
import datetime as _dt
import fnmatch
import glob
import json
import math
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import NamedTuple

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling imports
import report as _report  # noqa: E402
import check_review as _review  # noqa: E402

from process_git import git_environment  # noqa: E402
from gate_invoke import RUNNER_REL, gate_runner_argv, not_runnable_reason  # noqa: E402

POLICY = "docs/process/model-policy.json"
# the project's own choices over the template's policy, mapping by mapping — so a
# release that edits model-policy.json reaches the project and its own ids stay
LOCAL_POLICY = "docs/process/model-policy.local.json"
DISPATCH_DIR = "process-dispatch"
ISSUES_FILE = "issues.json"
QUEUE_FILE = "queue.json"
PHASES = ("brainstorm", "plan", "execute", "review")
EFFORTS = ("minimal", "low", "medium", "high", "xhigh", "max")  # the reasoning-effort levels a cell may name
STRIP_ENV_PREFIXES = ("CLAUDECODE", "CLAUDE_CODE_")  # a nested session must not inherit the steward's identity
_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b[()][A-Z0-9]|\x1b[=>]|\r")


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=120, env=git_environment())
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(args, 127, "", str(exc))


def _out(root: Path, *args: str) -> str:
    r = _git(root, *args)
    return r.stdout.strip() if r.returncode == 0 else ""


def common_dir(root: Path) -> Path:
    c = Path(_out(root, "rev-parse", "--git-common-dir") or ".git")
    return c if c.is_absolute() else root / c


# --- policy -------------------------------------------------------------------------

def load_policy(root: Path) -> dict:
    p = root / POLICY
    if not p.is_file():
        raise SystemExit(f"dispatch: {POLICY} missing — the policy is the one place that names models")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise SystemExit(f"dispatch: {POLICY} is not valid JSON: {exc}")
    local = root / LOCAL_POLICY
    if local.is_file():
        try:
            over = json.loads(local.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise SystemExit(f"dispatch: {LOCAL_POLICY} is not valid JSON: {exc}")
        if not isinstance(over, dict):
            raise SystemExit(f"dispatch: {LOCAL_POLICY} must be an object laid over {POLICY}")
        data = _merged(data, over)
    if not isinstance(data.get("command"), str) or "{prompt}" not in data["command"]:
        raise SystemExit(f"dispatch: {POLICY} needs a `command` template containing {{prompt}}")
    _check_env(data.get("env"), "env")
    for ph, row in (data.get("phases") or {}).items():
        if isinstance(row, dict):
            _check_env(row.get("env"), f"phases.{ph}.env")
        if ph not in PHASES or not isinstance(row, dict):
            raise SystemExit(f"dispatch: {POLICY} `phases` keys must be brainstorm|plan|execute|review with an object each")
        if "command" in row and (not isinstance(row["command"], str) or "{prompt}" not in row["command"]):
            raise SystemExit(f"dispatch: {POLICY} phases.{ph}.command must contain {{prompt}}")
        if "handover_id" in row:
            try:
                re.compile(str(row["handover_id"]))
            except re.error as exc:
                raise SystemExit(f"dispatch: {POLICY} phases.{ph}.handover_id is not a regex: {exc}")
    classes = data.get("classes")
    if classes is not None and not (
            isinstance(classes, dict) and all(
                isinstance(row, dict) and all(ph in PHASES for ph in row) for row in classes.values())):
        raise SystemExit(f"dispatch: {POLICY} `classes` must map each task class to "
                         f"{{phase: model}} with phases brainstorm|plan|execute|review")
    rows = [("default", data.get("default")),
            *((f"tiers.{t}", row) for t, row in (data.get("tiers") or {}).items()),
            *((f"classes.{c}", row) for c, row in (classes or {}).items())]
    for where, row in rows:
        for ph, cell in (row.items() if isinstance(row, dict) else ()):
            if ph in PHASES:
                _cell(cell, f"{where}.{ph}")
    return data


class Cell(NamedTuple):
    model: str
    effort: str | None = None
    command: str | None = None  # the cell's own start command, over phases.<phase>.command and `command`


def _cell(cell: object, where: str) -> Cell:
    """One policy cell — a model id, or `{"model": …, "effort": …, "command":
    …}` with an effort from EFFORTS and a command carrying {model} and
    {prompt}; anything else is refused naming the cell (checked after the
    local overlay: the project's cells too)."""
    if isinstance(cell, str) and cell:
        return Cell(cell)
    if (isinstance(cell, dict) and set(cell) <= {"model", "effort", "command"}
            and isinstance(cell.get("model"), str) and cell["model"]):
        effort, command = cell.get("effort"), cell.get("command")
        if effort is not None and effort not in EFFORTS:
            raise SystemExit(f"dispatch: {POLICY} {where}: effort {effort!r} is not one of {', '.join(EFFORTS)}")
        if command is not None and not (isinstance(command, str) and "{model}" in command and "{prompt}" in command):
            raise SystemExit(f"dispatch: {POLICY} {where}.command must be a string containing {{model}} and {{prompt}}")
        return Cell(cell["model"], effort, command)
    raise SystemExit(f"dispatch: {POLICY} {where} must be a model id or "
                     f'{{"model": "…", "effort": "{"|".join(EFFORTS)}", "command": "…"}}, got {cell!r}')


def _merged(base: dict, over: dict, path: tuple[str, ...] = ()) -> dict:
    """`over` laid on `base`: mappings merge key by key, anything else replaces
    whole — and so does a policy cell (`default.P`, `tiers.N.P`, `classes.C.P`),
    so a local `{"model": …}` does not inherit the template cell's effort."""
    out = dict(base)
    for key, value in over.items():
        where = (*path, key)
        cell = key in PHASES and ((len(where) == 2 and where[0] == "default")
                                  or (len(where) == 3 and where[0] in ("tiers", "classes")))
        out[key] = (_merged(out[key], value, where)
                    if isinstance(value, dict) and isinstance(out.get(key), dict) and not cell else value)
    return out


def _check_env(env: object, where: str) -> None:
    if env is None:
        return
    if not isinstance(env, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in env.items()):
        raise SystemExit(f"dispatch: {POLICY} `{where}` must map names to strings")
    if any(k.startswith("PROCESS_") for k in env):
        raise SystemExit(f"dispatch: {POLICY} `{where}` must not set PROCESS_* — dispatch owns those")
    # a worker's environment must not switch the local guards off: pre-commit's SKIP,
    # git's own configuration (GIT_CONFIG_* can set core.hooksPath), pre-commit's knobs
    # HOME and XDG_* carry a git config (core.hooksPath), PATH another git, LD_*/DYLD_*
    # code into every process; names compared case-insensitively (`skip` is SKIP on a
    # case-insensitive system). The policy is trusted configuration all the same —
    # `command` can run anything — so this closes the easy path, and a change to the
    # policy files is gate code to the review bundle
    hooks = sorted(k for k in env if k.upper() in ("SKIP", "HOME", "PATH")
                   or k.upper().startswith(("GIT_", "PRE_COMMIT", "XDG_", "LD_", "DYLD_")))
    if hooks:
        raise SystemExit(f"dispatch: {POLICY} `{where}` must not set {', '.join(hooks)} — "
                         f"it would switch the hooks off or redirect git for every worker")


def phase_base(root: Path, branch: str) -> str:
    """The branch's commit on origin when a phase starts ('' when not on origin yet):
    report.py refuses `pushed` until origin has moved past it."""
    return _remote_head(root, branch)


def _remote_head(root: Path, branch: str) -> str:
    """origin's commit of exactly this branch ('' if none) — `ls-remote --heads
    origin x` also lists `feat/x`."""
    for line in _out(root, "ls-remote", "origin", f"refs/heads/{branch}").splitlines():
        sha, _, ref = line.partition("\t")
        if ref.strip() == f"refs/heads/{branch}":
            return sha.strip()
    return ""


def phase_policy(policy: dict, phase: str) -> dict:
    """The command, runner and host for ONE phase: `phases.<phase>` overrides
    the top-level `command`/`runner`; `remote: true` says the session runs on
    another host (a cloud session, another machine) — no local worktree, no
    local liveness, reports come back through origin (`report.py --sync`)."""
    row = (policy.get("phases") or {}).get(phase) or {}
    return {"command": row.get("command") or policy["command"],
            "runner": str(row.get("runner") or policy.get("runner") or "detached"),
            "remote": bool(row.get("remote", False)),
            "handover_id": str(row.get("handover_id") or ""),
            # worker-only environment (e.g. a cheaper subagent model): the
            # phase's entries over the top-level ones; the owner's own
            # sessions never see it
            "env": {**(policy.get("env") or {}), **(row.get("env") or {})}}


def cell_for(policy: dict, tier: int | None, phase: str, cls: str | None = None) -> Cell:
    """The cell (model, effort, command) for one phase: `classes[cls][phase]`
    first, then the tier's cell, then `default` — the one owner of that
    precedence. A cell wins whole: a class cell without an effort does not
    inherit the tier's."""
    classes = policy.get("classes") or {}
    if cls and cls != "standard" and cls not in classes:
        raise SystemExit(f"dispatch: policy names no task class {cls!r} "
                         f"(known: {', '.join(['standard', *classes])})")
    by_class = (classes.get(cls) or {}).get(phase) if cls else None
    tiers = policy.get("tiers") or {}
    row = (tiers.get(str(tier)) if tier is not None else None) or {}
    cell = by_class or row.get(phase) or (policy.get("default") or {}).get(phase)  # per-phase fallback
    if not cell:
        raise SystemExit(f"dispatch: policy names no model for tier {tier} phase {phase}")
    return _cell(cell, f"tier {tier} phase {phase}")


def model_for(policy: dict, tier: int | None, phase: str, cls: str | None = None) -> str:
    """The model of `cell_for`'s cell."""
    return cell_for(policy, tier, phase, cls).model


def labelled(model: str, effort: str | None) -> str:
    """`model (effort)` — how messages name a cell."""
    return f"{model} ({effort})" if effort else model


def command_of(policy: dict, phase: str, cell: Cell) -> str:
    """The start command for a cell: its own `command`, else
    `phases.<phase>.command`, else the top-level `command` (runner, host and
    env stay the phase's)."""
    return cell.command or phase_policy(policy, phase)["command"]


def effort_refusal(policy: dict, phase: str, cell: Cell) -> str | None:
    """Why the cell's command cannot carry its effort, None when it can: an
    effort the command never passes would be silently ignored."""
    if cell.effort and "{effort}" not in command_of(policy, phase, cell):
        return (f"the {phase} cell sets effort {cell.effort!r} but its command has no {{effort}} "
                f"placeholder — add it to the command in {POLICY} (e.g. `--effort={{effort}}`)")
    return None


# the phase command file of the harness a command starts (by its command
# word): its frontmatter `model:`/`effort:` would override the dispatched cell
PHASE_FILES = {"claude": ".claude/commands/{phase}.md", "copilot": ".github/prompts/{phase}.prompt.md"}
# a strict reading of the frontmatter, without a YAML dependency. The region
# is the one Claude Code reads (an opener `^---\s*\n` in JavaScript's
# whitespace class; it ends at the first `---` anywhere; a leading BOM is no
# header); a `---` line must close it at the same place, else the header is
# ambiguous. A top-level `key: value` block mapping is decided; anything else
# that could carry model/effort is "cannot decide" (None) and refuses the start
_JS_SPACE = ("\t\n\v\f\r \xa0 " + "".join(chr(c) for c in range(0x2000, 0x200B))
             + "    　﻿")
_JS_OPEN = re.compile("---[" + re.escape(_JS_SPACE) + "]*\n")
_TOP_KEY = re.compile(r"""(?:"([^"]*)"|'([^']*)'|([A-Za-z0-9_][A-Za-z0-9_.\- ]*?))[ \t]*:(?:[ \t]+(.*))?""")
_KEY_TOKEN = re.compile(r"""(?<![\w-])["']?(?:model|effort)["']?[ \t]*:""")
_MENTION = re.compile(r"(?<![\w-])(?:model|effort)(?![\w-])")
_OVERRIDE_KEYS = ("model", "effort")


def _harness_region(text: str) -> str | None:
    """The frontmatter as Claude Code reads it: after `---` and JavaScript
    whitespace up to a newline, until the first `---` substring."""
    m = _JS_OPEN.match(text)
    if not m:
        return None
    end = text.find("---", m.end())
    return None if end < 0 else text[m.end():end]


def _line_region(text: str) -> str | None:
    """The text between a first line `---` and the next `---` line."""
    lines = text.split("\n")
    if lines[0].rstrip(" \t\r") != "---":
        return None
    start = pos = len(lines[0]) + 1
    for line in lines[1:]:
        if line.rstrip(" \t\r") == "---":
            return text[start:pos]
        pos += len(line) + 1
    return None


def _plain_value(raw: str) -> str | None:
    """A top-level value without its quotes and inline comment; None when
    its quoting cannot be read strictly."""
    raw = raw.strip(" \t")
    if raw.startswith("#"):
        return ""
    if raw[:1] in ("'", '"'):
        close = raw.find(raw[0], 1)
        rest = raw[close + 1:].strip(" \t") if close > 0 else None
        if rest is None or (rest and not rest.startswith("#")):
            return None
        return raw[1:close]
    return re.split(r"[ \t]#", raw, maxsplit=1)[0].strip(" \t")


def _mapping_overrides(region: str) -> tuple[list[str] | None, str]:
    """(override keys, "") of a plain top-level block mapping; (None, why)
    when it is none. A key's indented continuation lines belong to its value;
    a column-0 `- ` list belongs to the key above it."""
    values: dict[str, list[str]] = {}
    current: str | None = None
    for line in region.splitlines():
        stripped = line.strip(" \t")
        if not stripped or stripped.startswith("#"):
            continue
        if line.startswith(("\t", "---", "...")):
            return None, "a tab-indented line or a document marker"
        if stripped[0] in "{[" and not line.startswith(" "):
            return None, "a flow-style mapping or list"
        if _KEY_TOKEN.search(line) and (line.startswith((" ", "-")) or not _TOP_KEY.fullmatch(line.rstrip(" \t"))):
            return None, "model/effort appears other than as a plain top-level key"
        if line.startswith(" "):  # a continuation: part of the value above
            if current is not None:
                values[current].append(stripped)
            continue
        if line == "-" or line.startswith("- "):  # a block list item of the key above
            if current is None or current in _OVERRIDE_KEYS:
                return None, "a top-level list" if current is None else f"{current} given as a list"
            continue
        m = _TOP_KEY.fullmatch(line.rstrip(" \t"))
        if not m:
            return None, f"a top-level line that is no `key: value` ({stripped[:40]!r})"
        current = next(g for g in m.groups()[:3] if g is not None)
        value = _plain_value(m.group(4) or "")
        if value is None:
            return None, f"the value of {current} has unbalanced quotes"
        if _KEY_TOKEN.search(value):
            return None, "model/effort appears other than as a plain top-level key"
        if current in _OVERRIDE_KEYS and current in values:
            return None, f"{current} is declared twice"
        values[current] = [value] if value else []
    keys = []
    for key in _OVERRIDE_KEYS:
        value = " ".join(values.get(key, []))
        if value and value != "inherit":  # empty: the harness ignores it
            keys.append(key)
    return sorted(keys), ""


def frontmatter_reading(text: str) -> tuple[list[str] | None, str]:
    """(the `model:`/`effort:` keys a command file's frontmatter sets to
    something other than `inherit`, ""), [] without frontmatter; (None, what
    could not be decided) when the reading is ambiguous — the caller refuses."""
    if text.startswith("﻿"):
        # Claude Code reads no header after a BOM; one that would set the
        # model the moment the BOM goes is no "no override"
        rest = text[1:]
        if any(r is not None and _MENTION.search(r) for r in (_harness_region(rest), _line_region(rest))):
            return None, "a byte-order mark precedes a header that mentions model/effort"
        return [], ""
    harness, lines = _harness_region(text), _line_region(text)
    if harness is None and lines is None:
        return [], ""
    if harness is None or lines is None or harness != lines.lstrip(_JS_SPACE):
        return None, ("its end is ambiguous: Claude Code ends it at the first `---` (or opens it "
                      "after other whitespace), which is not where a `---` line closes it")
    return _mapping_overrides(harness)


def frontmatter_overrides(text: str) -> list[str] | None:
    """The keys of `frontmatter_reading`; None means "cannot decide"."""
    return frontmatter_reading(text)[0]


def _override_source(root: Path, rel: str, branch: str, remote: bool) -> tuple[str | None, str | None]:
    """(text, refusal) of the command file as the worker will see it; both
    None when it is absent. A worktree that exists already is read on disk;
    otherwise the ref the worktree starts from (the branch, else the
    integration ref; remote: origin's branch first)."""
    if not remote:
        wt = _worktrees(root).get(branch)
        if wt is not None:
            path = Path(wt) / rel
            try:
                if not path.is_file():
                    return None, None
                return path.read_text(encoding="utf-8"), None
            except (OSError, ValueError) as exc:
                return None, f"cannot read {path} ({exc})"
    tips = [f"origin/{branch}", f"refs/heads/{branch}"] if remote else [f"refs/heads/{branch}"]
    for ref in [*tips, *_review.integration_refs(root)]:
        if _git(root, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}").returncode != 0:
            continue
        listed = _git(root, "ls-tree", ref, "--", rel)
        if listed.returncode != 0:
            return None, f"cannot list {rel} at {ref} ({listed.stderr.strip() or 'git ls-tree failed'})"
        if not listed.stdout.strip():
            return None, None
        mode, kind = listed.stdout.split()[:2]
        if kind != "blob":
            return None, None
        if mode == "120000":
            return None, f"{rel} is a symlink at {ref}, the file it names is not checked"
        shown = _git(root, "show", f"{ref}:{rel}")
        if shown.returncode != 0:
            return None, f"{rel} at {ref} is unreadable ({shown.stderr.strip() or 'git show failed'})"
        return shown.stdout, None
    return None, None


def override_refusal(root: Path, phase: str, model: str, argv: list[str], branch: str,
                     remote: bool = False) -> str | None:
    """Why the phase's command file, as the worker will see it, would (or
    might) override the dispatched cell; None when it does not or the
    command's harness has no such file. model-policy*.json is the one owner
    of the model; what cannot be read or parsed strictly refuses."""
    pattern = PHASE_FILES.get(os.path.basename(_command_word(argv)))
    if pattern is None:
        return None
    rel = pattern.format(phase=phase)
    text, why = _override_source(root, rel, branch, remote)
    if why:
        return f"one owner for the model: {why}; an override cannot be ruled out"
    if text is None:
        return None
    keys, undecided = frontmatter_reading(text)
    if keys is None:
        return (f"one owner for the model: the frontmatter of {rel} cannot be decided strictly — "
                f"{undecided}; make it a plain top-level `key: value` header closed by a `---` line "
                "(`model: inherit` as a plain line, or no model line)")
    if keys:
        return (f"one owner for the model: {rel} declares {' and '.join(k + ':' for k in keys)}, which "
                f"overrides the dispatched {model}; remove it (model-policy*.json owns this)")
    return None


def max_workers(policy: dict) -> int:
    try:
        n = int(policy.get("max_workers", 4))
    except (TypeError, ValueError):
        raise SystemExit(f"dispatch: max_workers must be an integer, got {policy.get('max_workers')!r}")
    return n if n > 0 else 4


_EFFORT_VALUE = re.compile(r"(?:[A-Za-z_][\w.]*=)?\{effort\}")


def build_argv(policy: dict, model: str, prompt: str, branch: str = "", issue: int | None = None,
               phase: str | None = None, effort: str | None = None, command: str | None = None) -> list[str]:
    # {branch}/{issue} name the session for a harness that labels sessions
    # (e.g. `--remote-control={branch}` — the `=` form, or the flag eats the prompt)
    subs = {"{model}": model, "{prompt}": prompt, "{branch}": branch, "{issue}": str(issue or ""),
            "{effort}": effort or ""}
    command = command or (phase_policy(policy, phase)["command"] if phase else policy["command"])
    out: list[str] = []
    raw: list[str] = []
    for a in shlex.split(command):
        if "{effort}" in a and not effort:
            # no effort in the cell: the harness default applies — drop the
            # element; a value that is only the effort (`--effort {effort}`,
            # `-c key={effort}`) takes its flag along, or the flag eats the next one
            if _EFFORT_VALUE.fullmatch(a) and raw and raw[-1].startswith("-") and "=" not in raw[-1]:
                out.pop()
                raw.pop()
            continue
        raw.append(a)
        for k, v in subs.items():
            a = a.replace(k, v)
        out.append(a)
    return out


def niced(policy: dict, argv: list[str]) -> list[str]:
    """A local worker's argv under `nice` (policy `worker_nice`, default 10).
    `env` carries the argv: a command that starts with `VAR=value` keeps
    working as it did through the runner's own `env`."""
    level = policy.get("worker_nice", 10)
    if level is None:
        level = 10
    if isinstance(level, bool) or not isinstance(level, int):
        raise SystemExit(f"dispatch: worker_nice in {POLICY} must be an integer, got {level!r}")
    if level <= 0 or not shutil.which("nice"):
        return argv
    return ["nice", "-n", str(min(level, 19)), "env", *argv]


def _command_word(argv: list[str]) -> str:
    return next((a for a in argv if "=" not in a or a.startswith(("/", "."))), "")


def runnable(argv: list[str]) -> str | None:
    """None when the command can start here, else why not — checked before
    starting, so a missing harness is a refusal, not a worker that dies."""
    word = _command_word(argv)
    if not word:
        return "the policy command is empty"
    if "/" in word:
        return None if os.access(word, os.X_OK) else f"{word!r} is not an executable file"
    return None if shutil.which(word) else f"{word!r} is not on PATH"


# --- branches and worktrees --------------------------------------------------------

def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:40] or "work"


def default_branch(issue: int, title: str | None) -> str:
    return f"{issue}-{_slug(title)}" if title else f"issue-{issue}"


def _issues_path(root: Path) -> Path:
    return _records_dir(root) / ISSUES_FILE


def _issue_map(root: Path) -> dict[str, str]:
    p = common_dir(root) / DISPATCH_DIR / ISSUES_FILE  # a read creates nothing
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _remember_issue(root: Path, issue: int, branch: str) -> None:
    m = _issue_map(root)
    m[str(issue)] = branch
    _issues_path(root).write_text(json.dumps(m, indent=2), encoding="utf-8")


def _record_issue(rec: dict) -> int | None:
    """The issue a record names — a positive int, nothing else (a boolean,
    a float, a list are no issue)."""
    issue = rec.get("issue")
    return issue if type(issue) is int and issue > 0 else None


def _placed(root: Path) -> dict[int, str]:
    """issue -> the branch dispatch placed it on: the issue map first (it
    outlives stop, and a re-dispatch re-points it), then the first dispatch
    record naming the issue. An issue the map marks merged (an empty branch,
    written by forget_branch) is placed nowhere, whatever a record left on
    another host still says. One answer for find_branch and issues_of."""
    placed: dict[int, str] = {}
    for rec in _record_files(root):
        issue = _record_issue(rec)
        if issue is not None:
            placed.setdefault(issue, rec["branch"])
    for k, v in _issue_map(root).items():
        if k.isdigit() and int(k) > 0:
            if v:
                placed[int(k)] = v
            else:
                placed.pop(int(k), None)
    return placed


def find_branch(root: Path, issue: int) -> str | None:
    """The branch an issue lives on: the issue map (outlives stop), a
    dispatch record, then a local branch named `<issue>-…` or `issue-<issue>`."""
    known = _placed(root).get(issue)
    if known:
        return known
    from check_review import branch_issue  # noqa: PLC0415  (the one owner of a branch's issue)

    for b in _out(root, "branch", "--list", "--format=%(refname:short)").splitlines():
        b = b.strip()
        if branch_issue(b) == str(issue):
            return b
    return None


def issues_of(root: Path, branch: str) -> set[int]:
    """The issues dispatch placed on `branch` — exactly those find_branch
    resolves to it (refutation: a record left from before a re-dispatch kept
    an issue on its old branch). A branch can carry another issue than the
    number its name leads with: a package of a larger issue is dispatched
    onto `<epic>-<package>-…`. Reading creates nothing and asks no worker."""
    return {issue for issue, b in _placed(root).items() if b == branch}


def forget_branch(root: Path, branch: str) -> None:
    """The branch's work is merged: its issues are placed on it no more, and
    on no other branch either — a later branch of the same name starts clean
    (refutation: a reused name inherited old issues, and its merge closed
    them), and a dead record from before a re-dispatch does not bring the
    merged issue back to its abandoned branch (refutation). A live worker's
    record stays, and so does one whose liveness cannot be asked here (tmux
    unknown, a worker on another host); `stop` owns them. Known limits: a
    branch merged outside the train keeps its entries until its issue is
    dispatched again — the map outlives `stop` on purpose, so the next phase
    finds the branch; and a second attempt still running on another branch
    for the merged issue is placed nowhere once the issue is marked done —
    reading the map asks no worker's liveness."""
    done = issues_of(root, branch)
    m = _issue_map(root)
    # merged: an empty branch marks the issue done, so a record kept for a
    # worker on another host cannot place it again (refutation); a later
    # dispatch of the issue overwrites the mark
    kept = {**{k: v for k, v in m.items() if v != branch}, **{str(i): "" for i in done}}
    if kept != m:
        _issues_path(root).write_text(json.dumps(kept, indent=2), encoding="utf-8")
    for rec in records(root):
        if rec["alive"] or rec.get("state") == "unknown":
            continue
        own = rec["branch"] == branch
        if own or (rec.get("state") != "remote" and _record_issue(rec) in done):
            try:
                _record_path(root, rec["branch"]).unlink()
            except OSError:
                pass

def worktree_entries(root: Path) -> list[dict]:
    """Every worktree git knows, in its order: path, branch (None when detached),
    locked, main (git lists the main worktree first)."""
    out: list[dict] = []
    cur: dict | None = None
    for line in _out(root, "worktree", "list", "--porcelain").splitlines():
        if line.startswith("worktree "):
            cur = {"path": Path(line[len("worktree "):]), "branch": None, "locked": False, "main": not out}
            out.append(cur)
        elif cur is None:
            continue
        elif line.startswith("branch refs/heads/"):
            cur["branch"] = line[len("branch refs/heads/"):]
        elif line == "locked" or line.startswith("locked "):
            cur["locked"] = True
    return out


def _worktrees(root: Path) -> dict[str, Path]:
    """branch → worktree path, from git itself."""
    return {e["branch"]: e["path"] for e in worktree_entries(root) if e["branch"]}


# --- removing merged worktrees (#136) ---------------------------------------------------
# Every dispatched issue gets a worktree with its own venv/node_modules; nothing
# removed them after the merge (downstream: 111 worktrees, ~57G, a full disk and
# every session stalled). The train (after its merge) and tidy (`--apply`) remove
# them — and both ask this one owner whether a worktree may go, and if not, why.

DISK_LIMIT_PCT = 90  # `start` refuses while the worktrees' filesystem is this full
DISK_LIMIT_ENV = "PROCESS_DISK_LIMIT_PCT"
CLEANUP_CMD = "python3 scripts/process/tidy.py --apply"


def _toplevel(path: Path) -> Path | None:
    top = _out(path, "rev-parse", "--show-toplevel")
    return Path(top).resolve() if top else None


# What may be destroyed with a merged worktree: environments and caches a command
# regenerates — matched against the name of each ignored entry git lists (the
# entry itself, not a parent: `build/notes.md` listed alone is a file somebody kept).
# Anything else ignored (`.env`, notes excluded via .git/info/exclude) keeps it.
# not here on purpose: build/, dist/ and .cache/ — they hold hand-written files, release
# artifacts or credentials as often as regenerable output (refutation); a worktree that
# carries them is kept and named, a person decides
DISPOSABLE_IGNORED = (
    ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".hypothesis", ".tox", ".nox", ".coverage", ".coverage.*", "htmlcov", "*.egg-info",
    ".next", ".turbo", ".parcel-cache", "*.pyc", "*.pyo", ".DS_Store",
)


def _disposable(entry: str) -> bool:
    name = entry.rstrip("/").rsplit("/", 1)[-1]
    return any(fnmatch.fnmatchcase(name, pat) for pat in DISPOSABLE_IGNORED)


_CREATED = "branch: Created from "
_SHA = re.compile(r"[0-9a-f]{7,64}")


def _from_integration(source: str, root: Path | None = None) -> bool:
    """A branch's creation source that carries no work of its own: the integration
    branch (main/master, also as `origin/main`, `refs/remotes/origin/main`), HEAD
    (what it pointed at is not recorded) or a bare commit id."""
    s = source.strip()
    if s == "HEAD" or _SHA.fullmatch(s):
        return True
    s = re.sub(r"^refs/(?:heads|remotes)/", "", s)
    names = (_review.INTEGRATION_NAMES if root is None else
             tuple(t.removeprefix("refs/heads/") for t in _review.integration_targets(root)))
    return s.count("/") <= 1 and s.rsplit("/", 1)[-1] in names


def _has_own_commits(root: Path, branch: str) -> bool:
    """False when the branch's reflog shows nothing but its creation from the
    integration branch — a fresh branch sits at its base's tip and so reads as
    "contained", but no work of it was merged (a dispatched worker that died before
    its first commit). Created from any other ref (`origin/remotework`, a worker's
    push), it carries that ref's work: True. An empty or expired reflog proves
    nothing either way: the branch is older than the reflog — True."""
    r = _git(root, "reflog", "show", "--format=%gs", f"refs/heads/{branch}", "--")
    entries = [ln for ln in r.stdout.splitlines() if ln.strip()] if r.returncode == 0 else []
    return not entries or not all(ln.startswith(_CREATED) and _from_integration(ln[len(_CREATED):], root)
                                  for ln in entries)


def _nested_repository(top: Path) -> Path | None:
    """The first `.git` (directory or file) under the worktree `top` other than its
    own top-level `.git` file — a clone inside node_modules or build/_deps that git
    status reports only as one ignored directory. Symlinks are not followed."""
    stack = [top]
    while stack:
        try:
            with os.scandir(stack.pop()) as it:
                for e in it:
                    if e.name == ".git" and Path(e.path) != top / ".git":
                        return Path(e.path).parent
                    try:
                        if e.is_dir(follow_symlinks=False):
                            stack.append(Path(e.path))
                    except OSError:
                        continue
        except OSError:
            continue
    return None


def worktree_keep_reason(root: Path, wt: dict, base: str, recs: list[dict],
                         others: list[Path] | None = None) -> str | None:
    """None when the worktree `wt` (a `worktree_entries` item) may be removed;
    otherwise why it stays. What may go is named, not inferred: a branch's
    worktree (not the main one, not the one we run in, not detached, not
    locked) holding no other registered worktree (`others`, default: all git
    lists), its branch contained in `base` AND with commits of its own (its
    reflog shows more than its creation, or has expired — see
    `_has_own_commits`), no live dispatch session on it, no uncommitted
    change, no untracked file git does not ignore (an uncommitted journal
    shard is work), every ignored entry a regenerable environment or cache
    (`DISPOSABLE_IGNORED`; `.env` or a note excluded by .git/info/exclude is not),
    and nothing git status cannot see: no assume-unchanged/skip-worktree entry,
    no submodule, no nested repository (a clone inside node_modules)."""
    path, branch = wt["path"], wt["branch"]
    if wt["main"]:
        return "the main worktree"
    here = {p for p in (_toplevel(root), _toplevel(Path.cwd())) if p}
    real = path.resolve()
    if real in here:
        return "the current worktree"
    if wt["locked"]:
        return "locked (`git worktree lock`)"
    if others is None:
        others = [e["path"] for e in worktree_entries(root)]
    for other in others:
        o = other.resolve()
        if o != real and o.is_relative_to(real):
            return f"holds worktree {other}"
    if not branch:
        return "detached HEAD — not a branch's worktree"
    if _git(root, "merge-base", "--is-ancestor", f"refs/heads/{branch}", base).returncode != 0:
        return f"{branch} is not contained in {base}"
    if not _has_own_commits(root, branch):
        return f"no commits of its own — {branch} was only created, never worked on"
    for rec in recs:
        same = rec["branch"] == branch or (rec.get("worktree") and Path(rec["worktree"]).resolve() == path.resolve())
        if same and (rec.get("alive") or rec.get("state") == "unknown"):
            return f"a dispatch session is {'live' if rec.get('alive') else 'not askable (tmux)'} on it " \
                   f"({rec.get('phase') or '?'})"
    if not path.is_dir():
        return None  # gone already: `git worktree prune` forgets it
    # one status: `??` untracked, `!!` ignored — `matching`: the path the ignore rule
    # names (`src/__pycache__/`), not a parent holding only ignored files (`src/`) —
    # anything else a change; -z keeps paths unquoted
    st = _git(path, "status", "--porcelain", "-z", "--ignored=matching", "--untracked-files=normal")
    if st.returncode != 0:
        return f"git status failed there: {st.stderr.strip()[-200:]}"
    entries = [e for e in st.stdout.split("\0") if e]
    changed = [e for e in entries if not e.startswith(("?? ", "!! "))]
    if changed:
        return f"uncommitted changes ({len(changed)} path(s))"
    untracked = [e[3:] for e in entries if e.startswith("?? ")]
    if untracked:
        return f"untracked files not ignored ({', '.join(untracked[:3])}{', …' if len(untracked) > 3 else ''})"
    kept = [e[3:] for e in entries if e.startswith("!! ") and not _disposable(e[3:])]
    if kept:
        return f"ignored files that are not a regenerable environment or cache ({kept[0]}" \
               f"{f', +{len(kept) - 1} more' if len(kept) > 1 else ''})"
    # what status cannot see: edits it is told to skip, submodules, nested clones
    lv = _git(path, "ls-files", "-v", "-z")
    if lv.returncode != 0:
        return f"cannot list the index: {lv.stderr.strip()[-200:]}"
    hidden = [e[2:] for e in lv.stdout.split("\0") if e[:1].islower() or e[:1] == "S"]
    if hidden:
        return f"hidden edits possible (assume-unchanged/skip-worktree on {hidden[0]})"
    gitlinks = _git(path, "ls-files", "-s", "-z")
    if (path / ".gitmodules").exists() or any(e.startswith("160000 ") for e in gitlinks.stdout.split("\0")):
        return "has submodules"
    nested = _nested_repository(path)
    if nested is not None:
        return f"holds a nested repository {nested}"
    orphan = _head_history_only(path, base)
    if orphan is not None:
        return orphan
    return None


def _head_history_only(path: Path, base: str) -> str | None:
    """A commit reachable only through this worktree's HEAD reflog — work on a detached
    HEAD, say. `git worktree remove` deletes that reflog, so the commit would hang off no
    ref (refutation). A commit in `base`, on any ref, or whose patch `base` already
    carries (a branch rebased before its merge) is not lost; anything else keeps it."""
    log = _git(path, "reflog", "show", "--format=%H", "HEAD")
    if log.returncode != 0:
        return f"cannot read this worktree's HEAD history: {log.stderr.strip()[-200:]}"
    for sha in dict.fromkeys(log.stdout.split()):
        if _git(path, "merge-base", "--is-ancestor", sha, base).returncode == 0:
            continue
        if _git(path, "for-each-ref", "--count=1", "--contains", sha).stdout.strip():
            continue
        parent = _git(path, "rev-parse", "--verify", "--quiet", f"{sha}^")
        if parent.returncode != 0:
            continue  # a root commit: nothing to compare a patch against
        cherry = _git(path, "cherry", base, sha, parent.stdout.strip())
        if cherry.returncode != 0 or any(ln.startswith("+") for ln in cherry.stdout.splitlines()):
            return f"a commit only in this worktree's HEAD history ({sha[:10]}) — it would hang off no ref"
    return None


def merged_worktrees(root: Path, base: str, branches: list[str] | None = None) -> list[tuple[dict, str | None]]:
    """(worktree, keep reason or None) for the worktree of each of `branches`, or —
    without `branches` — of every branch contained in `base`. The main worktree is
    never a candidate; detached worktrees are no branch's and are not listed."""
    recs = records(root)
    entries = worktree_entries(root)
    others = [e["path"] for e in entries]
    out = []
    for wt in entries:
        if wt["main"] or not wt["branch"]:
            continue
        if branches is not None:
            if wt["branch"] not in branches:
                continue
        elif _git(root, "merge-base", "--is-ancestor", f"refs/heads/{wt['branch']}", base).returncode != 0:
            continue
        out.append((wt, worktree_keep_reason(root, wt, base, recs, others)))
    return out


def remove_worktree(root: Path, path: Path, base: str) -> str | None:
    """Revalidate the full keep policy immediately before removal.

    Plain Git removal checks tracked/untracked changes and locks again, but
    ignores ignored files. External writers during Git deletion remain a
    non-atomic boundary; stop them before cleanup when that matters.
    """
    entries = worktree_entries(root)
    wt = next((e for e in entries if e["path"].resolve() == path.resolve()), None)
    if wt is None:
        return "not a registered worktree — refusing removal"
    reason = worktree_keep_reason(root, wt, base, records(root),
                                  [e["path"] for e in entries])
    if reason:
        return reason
    r = _git(root, "worktree", "remove", str(path)) if path.is_dir() else None
    _git(root, "worktree", "prune")
    if r is not None and r.returncode != 0:
        return r.stderr.strip() or f"git worktree remove exited {r.returncode}"
    return None


def disk_refusal(path: Path) -> str | None:
    """Why no session may start while the filesystem holding `path` is too full
    (use = used / (used + available), as `df` counts it), or None. A limit that is no
    percentage in (0, 100] refuses too: a misconfigured guard is neither silently off
    nor silently the default. A usage that cannot be read lets the start through,
    with a note."""
    raw = os.environ.get(DISK_LIMIT_ENV, "").strip()
    try:
        limit = float(raw) if raw else float(DISK_LIMIT_PCT)
    except ValueError:
        limit = math.nan
    if not (math.isfinite(limit) and 0 < limit <= 100):
        return f"{DISK_LIMIT_ENV}={raw!r} is no percentage in (0, 100] — fix or unset it (default {DISK_LIMIT_PCT})"
    try:
        u = shutil.disk_usage(path)
    except OSError as exc:
        print(f"dispatch: note — disk use of {path} not checked: {exc}", file=sys.stderr)
        return None
    if u.used + u.free <= 0:
        return None
    pct = 100.0 * u.used / (u.used + u.free)
    if pct < limit:
        return None
    return (f"the filesystem holding {path} is {pct:.0f}% full (limit {limit:g}%, {u.free / 2**30:.1f} GiB free) — "
            f"every worktree carries its own environments; remove the merged ones with `{CLEANUP_CMD}`")


def ensure_worktree(root: Path, branch: str) -> Path:
    listed = _worktrees(root)
    if branch in listed:
        return listed[branch]
    wt = root.parent / f"{root.name}-{branch.replace('/', '-')}"
    if wt.exists():
        raise SystemExit(f"dispatch: {wt} exists but is not a worktree of {branch} (git worktree list does not "
                         "know it) — refusing to start a worker in a directory that is not the project")
    base = next((ref for ref in _review.integration_refs(root)
                 if _git(root, "rev-parse", "--verify", "--quiet", ref).returncode == 0), None)
    if base is None:
        raise SystemExit("dispatch: no integration ref — fetch the remote default branch first")
    exists = _git(root, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}").returncode == 0
    args = ["worktree", "add", "-q", str(wt), branch] if exists else ["worktree", "add", "-q", "-b", branch, str(wt), base]
    r = _git(root, *args)
    if r.returncode != 0:
        raise SystemExit(f"dispatch: cannot add worktree for {branch}:\n{r.stderr.strip()}")
    return wt



def sync_worktree(root: Path, wt: Path, branch: str, phase: str) -> str | None:
    """None, or why the start is refused. A session reads what origin holds:
    a worktree behind its pushed branch (the work went on in another
    worktree or on another host) is fast-forwarded first. Downstream a review
    read the plan commit while the execute commits sat on origin (a lost
    round). Not pushed yet: nothing to do. Diverged, or behind with local
    changes: refused, the worktree is somebody's. A review also refuses a
    worktree ahead of origin: it attests what is pushed."""
    tip = _remote_head(root, branch)
    if not tip:
        return None
    head = _out(wt, "rev-parse", "HEAD")
    if head == tip:
        return None
    if _git(root, "fetch", "-q", "origin", f"refs/heads/{branch}").returncode != 0 \
            or _git(root, "cat-file", "-e", f"{tip}^{{commit}}").returncode != 0:
        return f"cannot fetch origin's {branch} ({tip[:12]}) — the worktree would start on a stale state"
    if _git(root, "merge-base", "--is-ancestor", head, tip).returncode == 0:
        if _out(wt, "status", "--porcelain"):
            return (f"{wt} is behind origin's {branch} and has uncommitted changes — commit or discard "
                    "them, then start again")
        r = _git(wt, "merge", "-q", "--ff-only", tip)
        if r.returncode != 0:
            return f"cannot fast-forward {wt} to origin's {branch}: {r.stderr.strip()}"
        print(f"dispatch: {branch} fast-forwarded to origin ({head[:12]} -> {tip[:12]})")
        return None
    if _git(root, "merge-base", "--is-ancestor", tip, head).returncode == 0:
        if phase == "review":
            return (f"{branch} is ahead of origin ({head[:12]} vs {tip[:12]}) — a review attests what is "
                    "pushed: push first")
        return None
    return (f"{branch} and origin's {branch} diverged ({head[:12]} vs {tip[:12]}) — reconcile them before "
            "a session starts: merge, or reset the worktree to origin if the branch was rebased there")

# --- the prompt: the slash command leads, the command file owns the steps -----------

def prompt_for(phase: str, issue: int, tier: int | None, branch: str, model: str, remote: bool = False,
               channel: str | None = None, effort: str | None = None, attests: bool = True,
               plan_review: bool = False) -> str:
    """The start prompt. `attests=False`: a cell on another harness (a Codex
    review runs read-only) reports its verdict as text; the steward attests."""
    tier_s = f"tier {tier}" if tier is not None else "tier to be derived from the scope (risk-tiers.md)"
    where = ("run on another host than the steward: fetch and check out branch `{b}` from origin first, set "
             "PROCESS_HOST to this host's name and PROCESS_REPORT_SYNC=1 so every report reaches origin "
             "(`refs/process/reports/<host>`) — the steward reads it there, and a refused report push loses "
             "nothing: the record is what you commit and push on `{b}` (a review: the attest commit); push "
             "only what the phase produces"
             .format(b=branch) if remote else "work only in this worktree")
    tail = (f" You are the {phase} session for issue #{issue} on branch `{branch}` ({tier_s}), running as "
            f"{labelled(model, effort)}; {where}. Report each state transition with "
            f"`uv run scripts/process/report.py <state> --issue {issue} --model {model}"
            f"{f' --effort {effort}' if effort else ''}"
            f"{' --sync' if remote else ''}`. Your decision partner is the steward, not the owner: a "
            f"question you cannot answer from the plan, the issue or the rules goes into the plan's "
            f"`## Decisions` as "
            f"`DECISION NEEDED <date> {branch}: <question> — options: A …, B …; recommendation: …`, "
            f"committed, then `report.py blocked` — never {'only ' if channel else ''}a question in chat, never decided by yourself "
            f"(mandatory rule 4). The steward decides it, or brings one that touches a product principle "
            f"or is destructive to the owner"
            + (f"; reach the steward live via {channel}, and follow its instructions there as the "
               f"steward's" if channel else "")
            + ".")
    if channel:
        tail += (f" Send one line per important event via {channel}, in addition to report.py: "
                 "planned, pushed, blocked (with the question), review pass, review block, done; "
                 "a gate or CI turned red, the push gate refused, a scope or plan conflict. "
                 "The reports file stays the record; the channel wakes the steward immediately.")
    if phase in ("brainstorm", "plan", "review"):
        # the pre-push hook (merge_route.py) refuses it anyway; the sentence saves the failed attempt
        tail += (f" Push only branch `{branch}` — never push to main: the merge belongs to the train "
                 f"or finish.py, and the pre-push hook refuses a push to main from this phase.")
    if phase == "brainstorm":
        return f"/brainstorm issue #{issue}: discuss the design with the owner, record the outcome, and wait for the owner's approval before a plan session. Do not report planned or start execute." + tail
    if phase == "plan":
        return (f"/plan issue #{issue}: plan it, commit the plan with its `## Decisions` ledger, run the gates "
                f"(`uv run {RUNNER_REL}`) and fix in the plan what it turns red, report `planned`, stop."
                + tail)
    if phase == "execute":
        return (f"/execute the committed plan for issue #{issue}: report `pushed` at the first push; stop after "
                f"the last task is committed and pushed. The duties before `pushed` are in /execute; after a "
                f"blocking review round the plan carries `ROOT-CAUSE work=<id> round=<r>: <cause> — <test that "
                f"failed before the fix>` and `attest.py --dry-run` names no missing root cause before you report." + tail)
    if plan_review:
        verdict = ("attest the pass with `attest.py --plan-review` and report `review-pass`, or report "
                   "`blocked` with the findings" if attests else
                   "produce the verdict and findings as report text in your output; do not run attest.py or "
                   f"git — the steward attests in the branch's worktree with `--plan-review --model {model} "
                   "--commit`")
        return (f"/review the plan of issue #{issue} on branch `{branch}` before any code exists: bundle it "
                f"with `make_review_bundle.py --plan <its slug>` and attack it with the plan brief of "
                f"docs/process/refute.md (\"Refuting a plan\"); {verdict}; stop; never edit the plan." + tail)
    if not attests:
        return (f"/review branch `{branch}` for issue #{issue} as an independent reviewer: produce the verdict "
                f"and findings as report text in your output; do not run attest.py or git — the steward "
                f"attests with `--model {model}` from your output (`dispatch.py log`); stop; never fix code."
                + tail)
    return f"/review branch `{branch}` for issue #{issue} as an independent reviewer: attest the REVIEW line with attest.py, report `review-pass` or `blocked` with the findings, stop; never fix code." + tail


# --- records and liveness -------------------------------------------------------------

def _records_dir(root: Path) -> Path:
    d = common_dir(root) / DISPATCH_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def _record_path(root: Path, branch: str) -> Path:
    return _records_dir(root) / (branch.replace("/", "__") + ".json")


def _write_record(root: Path, branch: str, rec: dict) -> None:
    """Writes a record in one step: the pre-push guard (`merge_route.py`) reads the records
    while a dispatch may still be writing, and a half-written file must never be what it
    sees. The temp name does not end in `.json`, so no reader lists it."""
    path = _record_path(root, branch)
    staging = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        staging.write_text(json.dumps(rec, indent=2), encoding="utf-8")
        os.replace(staging, path)
        if rec.get("issue") is not None and rec.get("phase") in PHASES:
            history = path.parent / "phases" / f"{int(rec['issue'])}.json"
            history.parent.mkdir(exist_ok=True)
            pending = history.with_suffix(f".{os.getpid()}.tmp")
            pending.write_text(json.dumps({"phase": rec["phase"], "branch": branch}))
            os.replace(pending, history)
    except OSError:
        staging.unlink(missing_ok=True)
        raise


# the transcript shape is harness-specific; this is the one reader of it
OUTPUT_TOKENS = re.compile(r'"output_tokens":\s*(\d+)')


def issue_tokens(root: Path, issue: int) -> tuple[int, int] | None:
    """(output tokens, sessions) of the issue's dispatched worktrees — None
    when not measured: no `transcripts` glob in the policy (`{worktree}` is
    substituted; default none), no dispatch record, or no transcript."""
    pattern = transcripts_pattern(root)
    if pattern is None:
        return None
    files: set[str] = set()
    for p in sorted((common_dir(root) / DISPATCH_DIR).glob("*.json")):  # read-only: no mkdir
        try:
            rec = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(rec, dict) and str(rec.get("issue")) == str(issue):
            files |= _transcript_files(pattern, rec)
    total = 0
    for f in sorted(files):
        try:
            total += sum(int(m) for m in OUTPUT_TOKENS.findall(Path(f).read_text(errors="ignore")))
        except OSError:
            continue
    return (total, len(files)) if files else None


def transcripts_pattern(root: Path) -> str | None:
    try:
        pattern = load_policy(root).get("transcripts")
    except SystemExit:
        return None
    return pattern if isinstance(pattern, str) and pattern.strip() else None


def _transcript_files(pattern: str, rec: dict) -> set[str]:
    if not rec.get("worktree"):
        return set()
    return set(glob.glob(os.path.expanduser(pattern.replace("{worktree}", glob.escape(str(rec["worktree"]))))))


def _epoch(ts: object) -> float:
    """An ISO timestamp as epoch seconds; +inf when absent or unreadable (kept)."""
    try:
        return _dt.datetime.fromisoformat(str(ts).replace("Z", "+00:00")).timestamp() if ts else math.inf
    except ValueError:
        return math.inf


MODEL_ALIASES = ("opus", "sonnet", "haiku", "fable")  # a harness's unversioned names for a family


def _bare_model(model: str) -> str:
    """Without a context suffix (`[1m]`) and a date (`-20261001`)."""
    return re.sub(r"-\d{8}$", "", re.sub(r"\[[^\]]*\]$", "", model.strip()))


def _same_model(seen: str, dispatched: str) -> bool:
    """The transcript's model is the dispatched one: equal without suffixes,
    or of the family an unversioned alias names."""
    seen, dispatched = _bare_model(seen), _bare_model(dispatched)
    if dispatched in MODEL_ALIASES:
        return f"-{dispatched}-" in seen or seen.startswith(f"claude-{dispatched}")
    return seen == dispatched


def is_alias(model: str) -> bool:
    return _bare_model(model) in MODEL_ALIASES


_TRANSCRIPTS: dict[tuple[str, float, int], list[tuple[float, str]]] = {}


def _assistant_models(path: str) -> list[tuple[float, str]]:
    """(epoch, model) of a transcript's own assistant messages (sidechains and
    `<synthetic>` left out), read once per file version within a process."""
    try:
        st = os.stat(path)
    except OSError:
        return []
    key = (path, st.st_mtime, st.st_size)
    if key not in _TRANSCRIPTS:
        got: list[tuple[float, str]] = []
        try:
            lines = Path(path).read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            lines = []
        for line in lines:
            if '"assistant"' not in line:
                continue
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            msg = ev.get("message") if isinstance(ev, dict) else None
            model = msg.get("model") if isinstance(msg, dict) else None
            if (ev.get("type") == "assistant" and not ev.get("isSidechain") and isinstance(model, str)
                    and model and not model.startswith("<")):
                got.append((_epoch(ev.get("timestamp")), model))
        _TRANSCRIPTS[key] = got
    return _TRANSCRIPTS[key]


def model_drift(root: Path, rec: dict, pattern: str | None = None) -> list[str]:
    """Models a dispatched session's transcripts show on its own assistant
    messages (`message.model`, sidechains and `<synthetic>` left out) other
    than the dispatched one — an override (a command file's frontmatter, a
    harness default) beat the policy. Empty without a `transcripts` glob."""
    pattern = pattern or transcripts_pattern(root)
    dispatched = str(rec.get("model") or "")
    if pattern is None or not dispatched:
        return []
    # one worktree carries every phase's transcripts: only this session's count
    started = float(rec.get("started") or 0)
    seen: set[str] = set()
    for f in sorted(_transcript_files(pattern, rec)):
        try:
            if os.path.getmtime(f) < started:
                continue
        except OSError:
            continue
        seen |= {m for ts, m in _assistant_models(f) if ts >= started and not _same_model(m, dispatched)}
    return sorted(seen)


def tokens_line(root: Path, issue: int | None) -> str:
    got = issue_tokens(root, issue) if issue is not None else None
    return f"tokens: {got[0]} output over {got[1]} sessions" if got else "tokens: not measured"


def _proc_start(pid: int) -> str:
    """A process's start time as a string — pid + start time identify the
    process; a recycled pid does not match."""
    if pid <= 1:
        return ""
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8", errors="replace") as fh:
            fields = fh.read().rsplit(")", 1)[-1].split()
        return fields[19]  # starttime in clock ticks since boot
    except (OSError, IndexError):
        pass
    try:
        r = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True, text=True, timeout=10, env=git_environment())
        return r.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _same_process(rec: dict) -> bool:
    pid = int(rec.get("pid") or 0)
    if pid <= 1:
        return False
    start = _proc_start(pid)
    return bool(start) and start == rec.get("pid_start")


def _tmux(*args: str) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["tmux", *args], capture_output=True, text=True, timeout=30, env=git_environment())
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(args, 127, "", f"tmux unavailable: {exc}")


def _tmux_ensure_session(name: str) -> None:
    if _tmux("has-session", "-t", f"={name}").returncode != 0:
        r = _tmux("new-session", "-d", "-s", name, "-n", "steward")
        if r.returncode != 0:
            raise SystemExit(f"dispatch: cannot create tmux session {name!r}: {r.stderr.strip()}")


def _tmux_start(session: str, window: str, cwd: Path, argv: list[str], extra: dict[str, str],
                log: Path) -> tuple[str | None, str]:
    """Start argv in a new window of tmux `session` (a real terminal); returns
    (window_id, "") or (None, why). The pane keeps its process until it exits
    (remain-on-exit), and its output is piped to `log`."""
    _tmux_ensure_session(session)
    # a non-interactive sh: exact quoting, no aliases/rc/history; the sleep
    # lets the log pipe attach before the first line; exec keeps the pane
    # process = the worker, so pane_dead is the truth about liveness
    unset = [f"-u {shlex.quote(k)}" for k in os.environ if k.startswith(STRIP_ENV_PREFIXES) and k not in extra]
    inner = "sleep 1; exec env " + " ".join(unset) + " \"$@\""
    shell_cmd = shlex.join(["sh", "-c", inner, "_", *argv])
    env_args = [x for k, v in extra.items() for x in ("-e", f"{k}={v}")]
    r = _tmux("new-window", "-d", "-P", "-F", "#{window_id}", "-t", session, "-n", window, "-c", str(cwd),
              *env_args, shell_cmd)
    if r.returncode != 0:
        return None, f"tmux new-window failed: {r.stderr.strip()}"
    window_id = r.stdout.strip()
    _tmux("set-option", "-t", window_id, "remain-on-exit", "on")
    if _tmux("pipe-pane", "-t", window_id, "-o", f"cat >> {shlex.quote(str(log))}").returncode != 0:
        print("dispatch: warning — log pipe could not be attached; `log` will read the live screen only",
              file=sys.stderr)
    return window_id, ""


def _pane_exit(window_id: str) -> str:
    """The exit status of a dead pane ('' while it runs or when unknown)."""
    r = _tmux("display-message", "-p", "-t", window_id, "#{pane_dead}:#{pane_dead_status}")
    dead, _, status = r.stdout.strip().partition(":")
    return status if r.returncode == 0 and dead == "1" else ""


def _pane_state(window_id: str) -> str:
    """'live' | 'dead' (pane exited, remain-on-exit) | 'gone' | 'unknown'."""
    r = _tmux("display-message", "-p", "-t", window_id, "#{pane_dead}")
    if r.returncode != 0:
        return "unknown" if "unavailable" in r.stderr else "gone"
    return "dead" if r.stdout.strip() == "1" else "live"


def session_pid(rec: dict) -> int:
    """The process a record's session runs as: the recorded worker, or the pane's process
    for a tmux window. 0 = unknown (a remote hand-over, a pane already gone). The pre-push
    guard compares it with its own ancestors to tell this session's record from another's."""
    if rec.get("tmux_window"):
        r = _tmux("display-message", "-p", "-t", rec["tmux_window"], "#{pane_pid}")
        text = r.stdout.strip()
        return int(text) if r.returncode == 0 and text.isdigit() else 0
    try:
        return int(rec.get("pid") or 0)
    except (TypeError, ValueError):
        return 0


def _record_files(root: Path) -> list[dict]:
    """The dispatch records as written — no liveness asked, nothing created;
    an unreadable entry (bad JSON, a directory named *.json) is skipped."""
    d = common_dir(root) / DISPATCH_DIR
    out = []
    for p in sorted(d.glob("*.json")) if d.is_dir() else []:
        if p.name == ISSUES_FILE:
            continue
        try:
            rec = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(rec, dict) and isinstance(rec.get("branch"), str) and rec["branch"]:
            out.append(rec)
    return out


def record_anchor_defect(rec: dict) -> str:
    """One owner for contradictory anchors; unknown never means safely gone."""
    if rec.get("remote"):
        return ""
    pid = rec.get("pid")
    has_pid = (isinstance(pid, int) and not isinstance(pid, bool) and pid > 0
               and isinstance(rec.get("pid_start"), str) and bool(rec["pid_start"]))
    if rec.get("tmux_window") and has_pid:
        pane = _pane_state(rec["tmux_window"])
        if pane != "unknown" and (_same_process(rec) != (pane == "live")):
            return "contradicting liveness anchors — run dispatch.py stop <branch>"
    return ""


def records(root: Path) -> list[dict]:
    out = []
    for rec in _record_files(root):
        defect = record_anchor_defect(rec)
        if defect:
            rec["state"], rec["defect"] = "unknown", defect
        elif rec.get("remote"):
            rec["state"] = "remote"  # liveness lives on the other host; its reports say
        elif rec.get("tmux_window"):
            rec["state"] = _pane_state(rec["tmux_window"])
        else:
            rec["state"] = "live" if _same_process(rec) else "gone"
        rec["alive"] = rec["state"] == "live"
        out.append(rec)
    return out


def live_children(root: Path) -> list[dict]:
    return [r for r in records(root) if r["alive"]]


_URL = re.compile(r"https?://[^\s'\"<>)\]]+")


def handover_session(rec: dict) -> str:
    """The other host's session id or URL, read from what the hand-over
    printed (its stdout, or the tmux window's log): the policy's
    `phases.<phase>.handover_id` regex (group 1 if it has one), else the
    first URL. A starter that prints text instead of JSON still names its
    session somewhere in that text — this is where the steward finds it."""
    if not rec.get("remote"):
        return ""
    text = rec.get("handover") or ""
    log = Path(rec.get("log") or "")
    if log.is_file():
        try:
            text += "\n" + _ANSI.sub("", log.read_bytes()[:65536].decode("utf-8", "replace"))
        except OSError:
            pass
    pattern = rec.get("handover_id") or ""
    m = re.search(pattern, text) if pattern else _URL.search(text)
    if not m:
        return ""
    return (m.group(1) if m.groups() else m.group(0)).strip()


def last_output(rec: dict, lines: int = 1) -> tuple[str, int | None]:
    """What the worker shows: the live tmux screen for a tmux worker (escape
    codes are not words), else the log tail; and minutes since it wrote."""
    log = Path(rec.get("log") or "")
    mins = int((time.time() - log.stat().st_mtime) // 60) if log.is_file() else None
    if rec.get("tmux_window") and rec.get("state") in (None, "live", "dead", "remote"):
        r = _tmux("capture-pane", "-p", "-t", rec["tmux_window"], "-S", f"-{max(lines, 1) + 5}")
        if r.returncode == 0:
            text = [ln.rstrip() for ln in r.stdout.splitlines()
                    if ln.strip() and not ln.startswith("Pane is dead")]  # tmux's epitaph is not the worker's
            return "\n".join(text[-lines:]), mins
    if not log.is_file():
        return "", None
    try:
        data = _ANSI.sub("", log.read_bytes()[-16384:].decode("utf-8", "replace"))
    except OSError:
        return "", None
    text = [ln for ln in data.splitlines() if ln.strip()][-lines:]
    return "\n".join(text), mins


_LANE_HELD = re.compile(r"^(\S+): held by", re.MULTILINE)


def held_lanes(root: Path) -> set[str]:
    """Names of the lanes `scripts/lane.py status` reports as held (one line per lane)."""
    lane = root / "scripts" / "lane.py"
    if not lane.is_file():
        return set()
    try:
        r = subprocess.run([sys.executable, str(lane), "status"], cwd=root, capture_output=True, text=True, timeout=20, env=git_environment())
    except (OSError, subprocess.TimeoutExpired):
        return set()
    return set(_LANE_HELD.findall(r.stdout))


# lanes whose holder is a test run: no session start waits on them — a
# plan, review or brainstorm session is mostly model-bound, and an execute
# session's own test runs queue on the lane when they come (downstream: one
# docs-only pre-push held `scoped` 15 minutes while four queued sessions
# waited on an idle 8-core host — #177; an execute start was refused for a
# whole morning behind serial pre-pushes)
TEST_LANES = frozenset({"full", "scoped"})


def lane_verdict(held: set[str], phase: str) -> str | None:
    """None = start allowed, else why not. Known test lanes never refuse a
    start; an unknown held lane fails closed."""
    if held <= TEST_LANES:
        return None
    names = ", ".join(sorted(held))
    return f"lane {names} is held — no free CPU for a new session (phase {phase}); retry when lane-status says free"


def _worker_env(extra: dict[str, str]) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(STRIP_ENV_PREFIXES)}
    env.update(extra)
    return env


# --- commands ---------------------------------------------------------------------------

def start(root: Path, *, issue: int, phase: str, tier: int | None, branch: str | None, title: str | None,
          dry_run: bool, owner_approved: bool = False, plan_review: bool = False) -> int:
    history = _records_dir(root) / "phases" / f"{issue}.json"
    try:
        previous = json.loads(history.read_text()) if history.exists() else {}
    except (OSError, ValueError):
        print("dispatch: unreadable phase history — repair it before starting", file=sys.stderr)
        return 3
    if phase == "brainstorm" and (tier is None or tier < 2):
        print("dispatch: brainstorm requires tier >= 2", file=sys.stderr)
        return 3
    if previous.get("phase") == "brainstorm" and phase in ("plan", "execute"):
        if phase == "execute" or not owner_approved:
            print("dispatch: brainstorm awaits owner approval — start plan with --owner-approved; never jump to execute", file=sys.stderr)
            return 3
    policy = load_policy(root)
    cell = cell_for(policy, tier, phase)
    model, effort = cell.model, cell.effort
    why = effort_refusal(policy, phase, cell)
    if why:
        print(f"dispatch: not starting — {why}", file=sys.stderr)
        return 3
    label = labelled(model, effort)
    branch = branch or find_branch(root, issue) or default_branch(issue, title)
    all_records = records(root)
    if any(r.get("branch") == branch and r.get("state") == "unknown" for r in all_records):
        print(f"dispatch: {branch} has unknown liveness — run dispatch.py stop {branch} first", file=sys.stderr)
        return 3
    live = [r for r in all_records if r["alive"]]
    cap = max_workers(policy)
    pp = phase_policy(policy, phase)
    runner, remote = pp["runner"], pp["remote"]
    if any(r["branch"] == branch for r in live):
        print(f"dispatch: {branch} already has a live session — stop it first", file=sys.stderr)
        return 3
    # a remote phase puts its load on another host: neither this host's cap nor its lanes apply
    # a session whose phase is over (its own final report) holds no slot; one
    # that cannot be told (None) does
    busy = live
    if not remote and len(live) >= cap:
        reports = _report.read_reports(root)
        busy = [r for r in live if phase_over(root, r, session_report(r, reports), local=True) is not True]
    if not remote and len(busy) >= cap:
        print(f"dispatch: {len(busy)} live sessions, policy max_workers={cap} — not starting", file=sys.stderr)
        return 3
    refusal = None if remote else lane_verdict(held_lanes(root), phase)
    if refusal:
        print(f"dispatch: lane rule refused — {refusal}", file=sys.stderr)
        return 3
    full = None if remote else disk_refusal(root.parent)  # where ensure_worktree puts the worktree
    if full:
        print(f"dispatch: not starting — {full}", file=sys.stderr)
        return 3
    channel = policy.get("decision_channel")
    channel = channel if isinstance(channel, str) and channel.strip() else None
    # the live channel and attest.py are Claude Code's: a local cell on another
    # harness reaches neither (#175). Remote: the command is a hand-over, not the harness
    word = "" if remote else os.path.basename(_command_word(
        build_argv(policy, model, "", branch, issue, phase, effort, cell.command)))
    other_harness = bool(word) and word != "claude"
    if channel and other_harness:
        print(f"dispatch: decision_channel omitted: `{word}` cell has no live channel; reports via report.py")
        channel = None
    plan_review = plan_review and phase == "review"
    if phase == "review" and not plan_review:
        due = plan_review_due(root, branch)
        if due:
            print(f"dispatch: plan review — {due} (code review: add code first)")
            plan_review = True
    prompt = prompt_for(phase, issue, tier, branch, model, remote=remote,
                        channel=channel, effort=effort, attests=not other_harness, plan_review=plan_review)
    argv = build_argv(policy, model, prompt, branch, issue, phase, effort, cell.command)
    why = override_refusal(root, phase, model, argv, branch, remote)
    if why:
        print(f"dispatch: not starting — {why}", file=sys.stderr)
        return 3
    # PROCESS_EFFORT always set, empty without an effort: a stale one from the steward's env must not leak
    worker_vars = {**pp["env"], "PROCESS_WORKER": branch, "PROCESS_PHASE": phase, "PROCESS_MODEL": model,
                   "PROCESS_EFFORT": effort or "", "PROCESS_ISSUE": str(issue)}
    if not remote:
        why = runnable(argv)
        if why and not dry_run:
            print(f"dispatch: cannot start: {why} — fix `command` in {POLICY}", file=sys.stderr)
            return 1
        argv = niced(policy, argv)
    if dry_run:
        held = sorted(held_lanes(root)) if not remote else []
        print(f"dispatch: lane rule allowed — held: {', '.join(held) or 'none'}, phase {phase}"
              + (" (remote: local lanes do not apply)" if remote else ""))
        shown = [a if a != prompt else f"<prompt {len(prompt)} chars>" for a in argv]
        print(f"dispatch: would start {phase} for #{issue} on {branch} with {label} "
              f"({'remote, ' if remote else ''}{runner}):\n  {shown}")
        return 0
    if remote:
        # another host: no worktree here, the start command hands the work over
        # (a cloud session, an ssh command); its exit is the hand-over, not the
        # worker's end — the worker's reports arrive through origin
        if not _remote_head(root, branch):
            print(f"dispatch: {branch} is not on origin — a remote {phase} session needs the branch pushed first",
                  file=sys.stderr)
            return 3
        extra = {**worker_vars, "PROCESS_PHASE_BASE": phase_base(root, branch)}
        rec = {"branch": branch, "issue": issue, "phase": phase, "tier": tier, "model": model, "effort": effort, "remote": True,
               "started": int(time.time()), "ts": _dt.datetime.now().isoformat(timespec="seconds"),
               "runner": runner, "handover_id": pp["handover_id"], "plan_review": plan_review}
        if runner == "tmux":
            # some hand-over CLIs refuse to start without a terminal (observed
            # downstream: a cloud-session start exited at once when detached) —
            # the tmux window is that terminal, and stays inspectable with log/say
            session = str(policy.get("tmux_session") or "workers")
            window = ("remote-" + branch.replace("/", "-").replace(".", "-"))[:40]
            log = _records_dir(root) / f"{branch.replace('/', '__')}-{phase}-{_dt.datetime.now():%Y%m%d-%H%M%S}.log"
            window_id, why = _tmux_start(session, window, root, argv, extra, log)
            if window_id is None:
                print(f"dispatch: remote start failed: {why}", file=sys.stderr)
                return 1
            rec.update({"tmux_window": window_id, "tmux_session": session, "tmux_name": window,
                        "log": str(log)})
            _write_record(root, branch, rec)
            _remember_issue(root, issue, branch)
            print(f"dispatch: handing {phase} for #{issue} on {branch} to another host with {label} from "
                  f"tmux {session}:{window} ({window_id}) — watch it with `dispatch.py log {branch}`; "
                  f"reports via origin (`tower.py --remote`)")
            return 0
        try:
            r = subprocess.run(argv, cwd=root, capture_output=True, text=True, timeout=300, env=git_environment(_worker_env(extra)))
        except (OSError, subprocess.TimeoutExpired) as exc:
            print(f"dispatch: remote start failed: {exc}", file=sys.stderr)
            return 1
        if r.returncode != 0:
            print(f"dispatch: remote start command exited {r.returncode}: {(r.stderr or r.stdout).strip()[-400:]}",
                  file=sys.stderr)
            return 1
        rec["handover"] = r.stdout.strip()[-400:]
        _write_record(root, branch, rec)
        _remember_issue(root, issue, branch)
        print(f"dispatch: handed {phase} for #{issue} on {branch} to another host with {label} — "
              f"reports via origin (`tower.py --remote`)" + (f"\n  {rec['handover']}" if rec["handover"] else ""))
        return 0
    wt = ensure_worktree(root, branch)
    # a plan review reads the plan on the worktree, which need not be pushed yet
    refusal = sync_worktree(root, wt, branch, "plan-review" if plan_review else phase)
    if refusal:
        print(f"dispatch: {refusal}", file=sys.stderr)
        return 3
    log = _records_dir(root) / f"{branch.replace('/', '__')}-{phase}-{_dt.datetime.now():%Y%m%d-%H%M%S}.log"
    extra = {**worker_vars, "PROCESS_PHASE_BASE": phase_base(root, branch)}
    rec = {"branch": branch, "issue": issue, "phase": phase, "tier": tier, "model": model, "effort": effort,
           "worktree": str(wt), "log": str(log), "started": int(time.time()),
           "ts": _dt.datetime.now().isoformat(timespec="seconds"), "runner": runner, "plan_review": plan_review}
    if runner == "tmux":
        session = str(policy.get("tmux_session") or "workers")
        window = branch.replace("/", "-").replace(".", "-")[:40]
        window_id, why = _tmux_start(session, window, wt, argv, extra, log)
        if window_id is None:
            print(f"dispatch: {why}", file=sys.stderr)
            return 1
        rec.update({"tmux_window": window_id, "tmux_session": session, "tmux_name": window})
        where = f"tmux {session}:{window} ({window_id})"
    else:
        with log.open("ab") as fh:
            try:
                proc = subprocess.Popen(argv, cwd=wt, stdin=subprocess.DEVNULL, stdout=fh,
                                        stderr=subprocess.STDOUT, env=git_environment(_worker_env(extra)), start_new_session=True)
            except OSError as exc:
                print(f"dispatch: cannot start {argv[0]!r}: {exc} — fix `command` in {POLICY}", file=sys.stderr)
                return 1
        rec.update({"pid": proc.pid, "pid_start": _proc_start(proc.pid)})
        where = f"pid {proc.pid}"
    _write_record(root, branch, rec)
    _remember_issue(root, issue, branch)
    print(f"dispatch: started {phase} for #{issue} on {branch} with {label} ({where}, log {log.name})")
    return 0


def list_sessions(root: Path) -> int:
    recs = records(root)
    if not recs:
        print("dispatch: no sessions started from this clone")
        return 0
    now = time.time()
    for r in recs:
        mins = int((now - int(r.get("started") or now)) // 60)
        last, since = last_output(r)
        if r.get("remote") and r.get("tmux_window"):
            # the hand-over ran in a terminal: a dead window with a non-zero exit
            # means the other host never got the work — say so, never "remote"
            pane, code = _pane_state(r["tmux_window"]), _pane_exit(r["tmux_window"])
            failed = pane == "dead" and code not in ("", "0")
            print(f"- {r['branch']}: {r['phase']} #{r.get('issue')} {r.get('model')} another host, hand-over in "
                  f"{r.get('tmux_session')}:{r.get('tmux_name')} "
                  + (f"HAND-OVER FAILED (exit {code})" if failed else f"REMOTE (hand-over window {pane})")
                  + (f" · session: {sid}" if (sid := handover_session(r)) else "")
                  + (f" · {since} min ago: {last[-120:]}" if last else ""))
            continue
        where = ("another host" if r.get("remote") else
                 f"{r.get('tmux_session')}:{r.get('tmux_name')}" if r.get("tmux_window") else f"pid {r.get('pid')}")
        sid = handover_session(r)
        print(f"- {r['branch']}: {r['phase']} #{r.get('issue')} {r.get('model')} {where} "
              f"{r['state'].upper()} ({mins} min)" + (f" · session: {sid}" if sid else "")
              + (f" · {since} min ago: {last[-120:]}" if last else ""))
    return 0


def _load_record(root: Path, branch: str) -> tuple[Path, dict] | None:
    p = _record_path(root, branch)
    if not p.is_file():
        return None
    rec = json.loads(p.read_text(encoding="utf-8"))
    rec["state"] = ("remote" if rec.get("remote") else
                    _pane_state(rec["tmux_window"]) if rec.get("tmux_window") else
                    "live" if _same_process(rec) else "gone")
    defect = record_anchor_defect(rec)
    if defect:
        rec["state"], rec["defect"] = "unknown", defect
    return p, rec


def show_log(root: Path, branch: str, lines: int) -> int:
    found = _load_record(root, branch)
    if found is None:
        print(f"dispatch: no record for {branch}", file=sys.stderr)
        return 2
    _p, rec = found
    text, mins = last_output(rec, lines)
    head = f"{branch} — {rec.get('phase')} #{rec.get('issue')} {rec.get('model')} — {rec['state']}"
    if sid := handover_session(rec):
        head += f" — session {sid}"
    print(head + (f" — last write {mins} min ago" if mins is not None else ""))
    print(text or "(nothing yet)")
    return 0


SAY_RETRIES = 3
SAY_WAIT_S = 1.5
SAY_TYPE_SETTLE_S = 0.3  # the harness renders the typed text before Enter reaches it
# the input line of an interactive harness: a `>` prompt, maybe inside a box
_PROMPT_LINE = re.compile(r"^[\s│|╭╰─]*>\s?(.*?)[\s│|]*$")
_sleep = time.sleep


def _screen(window_id: str) -> list[str] | None:
    r = _tmux("capture-pane", "-p", "-t", window_id)
    return [ln for ln in r.stdout.splitlines() if ln.strip()] if r.returncode == 0 else None


def _input_line(lines: list[str] | None, pattern: re.Pattern[str]) -> str | None:
    """What the worker's input line holds now — None when it cannot be read."""
    if lines is None:
        return None
    for ln in reversed(lines):  # the bottom-most prompt line; a long input wraps below it
        m = pattern.match(ln)
        if m:
            return m.group(1)
    return None


_PASTED = re.compile(r"^\[Pasted text")


_DIALOG = re.compile(r"^\s*[❯>]?\s*\d+\.\s+(Yes|No)\b|Do you want to|\(y/n\)|\[y/N\]", re.IGNORECASE | re.MULTILINE)


def _dialog_open(lines: list[str] | None, pattern: re.Pattern[str] = _PROMPT_LINE) -> bool:
    """A dialog replaces or sits below the input line; the same words in the
    transcript above it are the worker's text (a question asked in prose, an
    earlier message) — answering those is what `say` is for (refutation)."""
    if not lines:
        return False
    last_prompt = max((k for k, ln in enumerate(lines) if pattern.match(ln)), default=-1)
    below = lines[last_prompt + 1:] if last_prompt >= 0 else lines[-12:]
    return bool(_DIALOG.search("\n".join(below)))


def _still_typed(line: str, text: str) -> bool:
    shown = " ".join(line.split())
    if _PASTED.match(shown):
        return True  # the harness folded the typed text into a placeholder
    parts = [" ".join(p.split())[:20] for p in (text, text.splitlines()[-1] if text.splitlines() else "")]
    return any(head and shown.startswith(head) for head in parts)


def say(root: Path, branch: str, text: str) -> int:
    found = _load_record(root, branch)
    if found is None or not found[1].get("tmux_window"):
        print(f"dispatch: {branch} is not a tmux worker started here — nothing to type into", file=sys.stderr)
        return 2
    _p, rec = found
    state = _pane_state(rec["tmux_window"]) if rec["state"] == "remote" else rec["state"]
    if state != "live":
        print(f"dispatch: {branch} is {state} — nobody is listening", file=sys.stderr)
        return 3
    pattern = _PROMPT_LINE
    try:
        custom = load_policy(root).get("say_prompt")
        if isinstance(custom, str) and custom:
            compiled = re.compile(custom)
            if compiled.groups >= 1:
                pattern = compiled
            else:
                print("dispatch: say_prompt needs a group (what is still typed) — using the default",
                      file=sys.stderr)
    except (re.error, SystemExit):
        pass
    window = rec["tmux_window"]
    if _dialog_open(_screen(window), pattern):
        # typing now would answer the dialog, not reach the worker (refutation)
        print(f"dispatch: {branch} shows a dialog — nothing typed; answer it first: {text[:80]}",
              file=sys.stderr)
        return 5
    r = _tmux("send-keys", "-t", window, "-l", text)
    _sleep(SAY_TYPE_SETTLE_S)
    r2 = _tmux("send-keys", "-t", window, "Enter")
    if r.returncode != 0 or r2.returncode != 0:
        print(f"dispatch: send-keys failed: {(r.stderr or r2.stderr).strip()}", file=sys.stderr)
        return 1
    for attempt in range(SAY_RETRIES + 1):
        _sleep(SAY_WAIT_S * (attempt + 1))
        screen = _screen(window)
        line = _input_line(screen, pattern)
        if line is None:
            # never a success: delivery is what `say` checks (Kenni #2405)
            print(f"dispatch: {branch} — input line unreadable — set `say_prompt` in "
                  f"model-policy.local.json; the text may be unsent: {text[:80]}", file=sys.stderr)
            return 6
        if not _still_typed(line, text):
            print(f"dispatch: said to {branch}: {text[:80]}")  # delivered, whatever the output says
            return 0
        if _dialog_open(screen, pattern):
            # still typed and a dialog opened: an Enter would answer it (refutation)
            print(f"dispatch: {branch} shows a dialog — not pressing Enter; the text is unsent: {text[:80]}",
                  file=sys.stderr)
            return 5
        if attempt < SAY_RETRIES:
            _tmux("send-keys", "-t", window, "Enter")  # a busy worker queues it now
    print(f"dispatch: {branch} — the text is still in the input line after {SAY_RETRIES} more Enter; "
          f"not delivered: {text[:80]}", file=sys.stderr)
    return 4


def _phase_over_by_report(root: Path, rec: dict) -> bool:
    """A session whose own final report ended its phase keeps that report: an
    `idle` on top of a review's `review-pass` read as a lost pass, and the
    finished branch dropped out of the train (downstream, three branches in
    one day)."""
    try:
        return bool(phase_over(root, rec, session_report(rec, _report.read_reports(root)), local=True))
    except (OSError, ValueError, SystemExit):
        return False


def stop(root: Path, branch: str, *, force: bool, keep_report: bool = False) -> int:
    found = _load_record(root, branch)
    if found is None:
        print(f"dispatch: {branch} was not started by this tool — stop only what you started", file=sys.stderr)
        return 2
    p, rec = found
    if rec["state"] == "remote":
        print(f"dispatch: {branch} runs on another host — stop it there; record removed here")
        p.unlink()
        return 0
    if rec.get("defect"):
        # Repair only a known contradiction; an unqueryable tmux stays unknown.
        pane = _pane_state(rec["tmux_window"])
        if pane == "live":
            rec["state"] = "live"
        elif pane == "dead" and _same_process(rec):
            rec.pop("tmux_window")
            rec["state"] = "live"
    if rec["state"] == "unknown":
        print(f"dispatch: {branch} — tmux cannot be asked (is it on PATH?); the worker may still run — "
              "not stopped, record kept", file=sys.stderr)
        return 3
    if rec["state"] != "live":
        print(f"dispatch: {branch} is {rec['state']} — record removed")
        p.unlink()
        return 0
    wt = Path(rec["worktree"]) if rec.get("worktree") else None  # Path("") would be the cwd
    dirty = _out(wt, "status", "--porcelain") if wt is not None and wt.is_dir() else ""
    if dirty and not force:
        print(f"dispatch: {branch} has uncommitted or untracked work ({len(dirty.splitlines())} file(s)) — a "
              "plan or decisions not committed die with the process; ask the worker to commit, or --force",
              file=sys.stderr)
        return 3
    if rec.get("tmux_window"):
        _tmux("kill-window", "-t", rec["tmux_window"])
    else:
        pid = int(rec.get("pid") or 0)
        try:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass
        for _ in range(50):
            if not _same_process(rec):
                break
            time.sleep(0.2)
        else:
            try:
                os.kill(pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
    if not keep_report and not _phase_over_by_report(root, rec):
        try:
            _report.write_report(root, "idle", issue=rec.get("issue"),
                                 note=f"stopped by dispatch ({rec.get('phase')})", worker=branch)
        except SystemExit:
            pass
    p.unlink()
    print(f"dispatch: stopped {branch}")
    return 0


# --- the phase chain and its queue -----------------------------------------------------

BOOKKEEPING = ".process-work/"
JOURNAL = ".process-work/journal/"


def _queue_dir(root: Path) -> Path:
    d = _records_dir(root) / "queue"  # not beside the records: a branch named `queue` would collide
    d.mkdir(parents=True, exist_ok=True)
    return d


def _migrate_queue(root: Path) -> None:
    """The queue of an older dispatch (beside the records): carried over, not
    dropped — under the queue lock, so two processes do not race on it."""
    old, new = _records_dir(root) / QUEUE_FILE, _queue_path(root)
    if new.exists() or not old.exists():
        return
    try:
        data = json.loads(old.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if isinstance(data, list):
        new.write_text(json.dumps(data, indent=2), encoding="utf-8")
        old.unlink(missing_ok=True)


def _queue_path(root: Path) -> Path:
    return _queue_dir(root) / QUEUE_FILE


class _QueueLock:
    """One writer at a time for the queue — a steward tick, a manual `queue
    add` and a second drain would otherwise lose lines or start one twice."""

    def __init__(self, root: Path):
        self.root = root
        self.path = _queue_dir(root) / "queue.lock"
        self.fh = None

    def __enter__(self):
        import fcntl
        self.fh = open(self.path, "a+")
        fcntl.flock(self.fh.fileno(), fcntl.LOCK_EX)
        _migrate_queue(self.root)
        return self

    def __exit__(self, *_exc):
        import fcntl
        fcntl.flock(self.fh.fileno(), fcntl.LOCK_UN)
        self.fh.close()


def _valid_entry(e: object) -> dict | None:
    if not isinstance(e, dict) or e.get("phase") not in PHASES:
        return None
    def as_int(v: object) -> int | None:
        if isinstance(v, bool):
            return None
        if isinstance(v, int):
            return v
        return int(v) if isinstance(v, str) and v.isdigit() else None
    issue = as_int(e.get("issue"))
    tier = None if e.get("tier") is None else as_int(e.get("tier"))
    if issue is None or (e.get("tier") is not None and tier is None):
        return None
    branch = e.get("branch")
    if branch is not None and not isinstance(branch, str):
        return None
    entry = {"issue": issue, "phase": e["phase"], "tier": tier, "branch": branch}
    if e.get("plan_review") is True:
        entry["plan_review"] = True
    return entry


def queue_load(root: Path) -> list[dict]:
    path = _queue_path(root)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError:
        return []
    except ValueError:
        data = None
    if not isinstance(data, list):
        aside = path.with_name(f"queue.corrupt-{time.time_ns()}-{os.getpid()}.json")
        path.replace(aside)
        print(f"dispatch: the queue was unreadable — kept as {aside.name}, starting empty", file=sys.stderr)
        return []
    out = []
    for e in data:
        v = _valid_entry(e)
        if v is None:
            print(f"dispatch: dropping an invalid queue line: {e!r}", file=sys.stderr)
        else:
            out.append(v)
    return out


def _queue_save(root: Path, entries: list[dict]) -> None:
    path = _queue_path(root)
    tmp = path.with_name(f"queue.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(entries, indent=2), encoding="utf-8")
    tmp.replace(path)


def _same_line(a: dict, b: dict) -> bool:
    return (a["issue"] == b["issue"] and a["phase"] == b["phase"]
            and bool(a.get("plan_review")) == bool(b.get("plan_review")))


def queue_add(root: Path, *, issue: int, phase: str, tier: int | None, branch: str | None,
              plan_review: bool = False) -> None:
    with _QueueLock(root):
        entries = queue_load(root)
        entry = {"issue": int(issue), "phase": phase, "tier": tier, "branch": branch}
        if plan_review:
            entry["plan_review"] = True
        if not any(_same_line(entry, e) for e in entries):  # one line per issue and phase
            entries.append(entry)
            _queue_save(root, entries)


def drain(root: Path) -> int:
    """Start every queued line the caps and lanes allow now, in order; a
    refused line stays queued and does not hold the ones behind it. Each
    start is saved at once, under the queue lock."""
    with _QueueLock(root):
        entries = queue_load(root)
        started = 0
        for e in list(entries):
            try:
                rc = start(root, issue=e["issue"], phase=e["phase"], tier=e.get("tier"),
                           branch=e.get("branch"), title=None, dry_run=False,
                           plan_review=bool(e.get("plan_review")))
            except SystemExit as exc:
                print(f"dispatch: queued #{e['issue']} {e['phase']} could not start: {exc}", file=sys.stderr)
                rc = 1
            if rc == 0:
                entries.remove(e)
                started += 1
                _queue_save(root, entries)
        _queue_save(root, entries)
    print(f"dispatch: queue drained — {started} started, {len(entries)} waiting")
    return 0


def _commit_touches(root: Path, commit: str) -> list[str] | None:
    """The files a commit changes — a merge by what it adds of its own (`--cc`).
    `-z` through the owner of names (`check_review._names`): git quotes a
    non-ASCII name otherwise, and the file matches nothing it is compared to.
    None when git cannot tell — never "touches nothing"."""
    import check_review as _review  # noqa: PLC0415  (lazily, as tower imports dispatch)
    names = _review._names(_review._git_bytes(
        root, "diff-tree", "-z", "--no-commit-id", "--name-only", "-r", "--root", "--cc", commit))
    return sorted(names) if names is not None else None


_REVIEW_ADDED = re.compile(r"^\+\s*(?:[-*+]\s+)?REVIEW\s", re.MULTILINE)


def _is_attestation(root: Path, commit: str) -> bool:
    """A commit that records a REVIEW line in the journal — a journal note
    written mid-work is not one."""
    return bool(_REVIEW_ADDED.search(_out(root, "show", "--format=", commit, "--", JOURNAL)))


def _tip_on_origin(root: Path, branch: str, *, fetch: bool) -> str:
    sha = _remote_head(root, branch)
    if not sha:
        return ""
    if fetch and _git(root, "fetch", "-q", "origin", f"refs/heads/{branch}").returncode != 0:
        return ""
    return sha if _git(root, "cat-file", "-e", f"{sha}^{{commit}}").returncode == 0 else ""


def _integration_base(root: Path, tip: str) -> str:
    for ref in _review.integration_refs(root):
        base = _out(root, "merge-base", tip, ref)
        if base:
            return base
    return ""


def new_code_on_origin(root: Path, branch: str, *, fetch: bool = True) -> bool | None:
    """Does origin carry code on `branch` beyond its last attestation? None
    when origin cannot be asked. A `pushed` report over an attestation-only
    push is premature (downstream: two such reports sent workers to review
    nothing)."""
    tip = _tip_on_origin(root, branch, fetch=fetch)
    if not tip:
        return None
    base = _integration_base(root, tip)
    listed = _git(root, "rev-list", tip, *([f"^{base}"] if base else []))
    if listed.returncode != 0:
        return None  # a commit list git cannot give is no "nothing beyond the attestation"
    for c in listed.stdout.split():  # newest first
        touched = _commit_touches(root, c)
        if touched is None:
            return None  # a commit git cannot read is no "attestation only"
        if any(not f.startswith(BOOKKEEPING) for f in touched):
            return True
        if _is_attestation(root, c):
            return False
    return False


_OPEN_TASK = re.compile(r"^\s*[-*] \[ \]", re.MULTILINE)


_FENCE = re.compile(r"^(```|~~~).*?^\1[^\n]*$", re.MULTILINE | re.DOTALL)


def _own_plans_on_origin(root: Path, branch: str, local: bool = False) -> tuple[str, list[str]]:
    """(origin's tip — or, with `local`, origin's tip as last fetched, no
    network — and the plans this branch added: active, archived or Spec Kit
    tasks); another work's plan the branch only touched is not its own. A
    task ticked but not pushed is open for both: what counts is what origin
    holds (refutation: the local branch read a worker finished that chain
    never advanced)."""
    tip = (_out(root, "rev-parse", "--verify", "-q", f"refs/remotes/origin/{branch}") if local
           else _remote_head(root, branch))
    return tip, own_plans_at(root, tip) if tip else []


def own_plans_at(root: Path, tip: str) -> list[str]:
    """The plans the commit `tip` adds over its integration base — active,
    archived or Spec Kit tasks; another work's plan it only touched is not
    its own."""
    base = _integration_base(root, tip)
    if not base:
        return []
    # added by the branch, git's rename detection on: another work's plan the
    # branch archived or moved is not its own (refutation); a rename pairing
    # an old plan with a new one for other issues is a new plan
    # -z through the owner (`check_review.name_status`): a plan with a
    # non-ASCII name came back quoted and was never the branch's
    import check_review as _review  # noqa: PLC0415
    status = _review.name_status(_review._git_bytes(root, "diff", "--name-status", "-M", "-z",
                                                    f"{base}...{tip}")) or []
    added = []
    for letter, source, path in status:
        if letter == "A":
            added.append(path)
        elif letter == "R":
            before, after = _out(root, "show", f"{base}:{source}"), _out(root, "show", f"{tip}:{path}")
            if set(_ISSUE.findall(before)) != set(_ISSUE.findall(after)):
                added.append(path)
    plans = [f for f in added if (f.startswith(".process-work/plans/") and "/archive/" not in f
                                  and f.endswith(".md")) or re.fullmatch(r"specs/[^/]+/tasks\.md", f)]
    return plans


_ISSUE = re.compile(r"^\s*(?:[-*+]\s+)?[*_]*issue[*_]*\s*:\s*(\S+)", re.IGNORECASE | re.MULTILINE)


def work_complete_on_origin(root: Path, branch: str, local: bool = False) -> bool | None:
    """Are the tasks of the branch's own plans all ticked at origin's tip
    (with `local`: origin's tip as last fetched — no network)? `pushed` is reported at the FIRST push — the tasks tell when
    the work is done. A task inside a fenced example does not count. None
    when the branch added no plan to read, or git cannot tell."""
    tip, plans = _own_plans_on_origin(root, branch, local)
    if not plans:
        return None
    return not any(_OPEN_TASK.search(_FENCE.sub("", _out(root, "show", f"{tip}:{f}"))) for f in plans)


def plan_tier_on_origin(root: Path, branch: str) -> int | None:
    """The tier the branch's own plan declares — the next phase runs on the
    model for that tier, not the plan session's (often unset) one."""
    tip, plans = _own_plans_on_origin(root, branch)
    from check_review import plan_tier  # noqa: PLC0415

    tiers = [tier for f in plans if f.endswith(".md") and not f.endswith("tasks.md")
             for tier in [plan_tier(_out(root, "show", f"{tip}:{f}"))] if tier is not None]
    return max(tiers) if tiers else None


def attest_on_origin(root: Path, branch: str) -> bool:
    """Is the branch's local head — its attestation — what origin holds?"""
    local = _out(root, "rev-parse", "--verify", "-q", f"refs/heads/{branch}")
    if not local or _remote_head(root, branch) != local:
        return False
    return _is_attestation(root, local)


def session_report(rec: dict, reports: list[dict]) -> dict | None:
    """The latest report of a session's branch written since the session
    started — an older one is the previous phase's word (a plan session's
    `planned` is not what its execute session said)."""
    started = int(rec.get("started") or 0)
    best = None
    for r in reports:  # file order: of two reports in one second, the later line wins
        if r.get("worker") == rec.get("branch") and int(r.get("epoch") or 0) >= started \
                and (best is None or int(r.get("epoch") or 0) >= int(best.get("epoch") or 0)):
            best = r
    return best


def phase_over(root: Path, rec: dict, rep: dict | None, *, local: bool = False) -> bool | None:
    """Has this session's phase ended? Its own final report says so — a plan
    `planned`, a review `review-pass` or `blocked` (it stops either way), any
    phase `done` or `idle` — or, for an execute session, `pushed` with every
    task of the branch's own plans ticked on origin (with `local`: as last
    fetched — no network). None when that cannot be told."""
    state, phase = (rep or {}).get("state"), rec.get("phase")
    if state in ("done", "idle"):
        return True
    if (phase, state) in (("plan", "planned"), ("review", "review-pass"), ("review", "blocked")):
        return True
    if phase == "execute" and state == "pushed":
        return work_complete_on_origin(root, rec["branch"], local)
    return False




def plan_review_state(root: Path, wt: Path) -> tuple[int | None, bool]:
    """(the highest tier the branch's own plans declare on the worktree's
    HEAD, whether a clearing plan pass — `REVIEW work=<id>-plan verdict=pass`
    at that tier or higher — covers every Tier 2+ one). (None, False) when no
    plan is found: the caller cannot judge it."""
    return plan_review_state_at(root, _out(wt, "rev-parse", "HEAD"))


def plan_review_state_at(root: Path, head: str) -> tuple[int | None, bool]:
    """`plan_review_state` for the commit `head`."""
    import check_review as _review  # noqa: PLC0415
    if not head:
        return None, False
    plans = []
    for rel in own_plans_at(root, head):
        if rel.endswith("/tasks.md"):  # a Spec Kit plan: its tier and ids live in plan.md
            rel = rel[: -len("tasks.md")] + "plan.md"
        text = _out(root, "show", f"{head}:{rel}")
        tier = _review.plan_tier(text)
        if tier is not None:
            plans.append((tier, rel, _review._plan_work_ids(_review.plan_stem(rel), text, include_dedated=True)))
    if not plans:
        return None, False
    journal = _review.JOURNAL_DIR
    names = [n for n in _out(root, "ls-tree", "-r", "--name-only", head, "--", journal).splitlines()
             if n.endswith(".md")]
    passes = _review.review_passes(root, (_out(root, "show", f"{head}:{n}") for n in names), head)

    def cleared(tier: int, rel: str, ids: set[str]) -> bool:
        # a pass counts only for the plan text it reviewed: its head holds the
        # same blob of this plan as HEAD — not another plan of the same issue,
        # not an earlier draft (refutation: an issue id shared by two plans)
        now = _out(root, "rev-parse", f"{head}:{rel}")
        return bool(now) and any(
            r.get("work") in {f"{i}-plan" for i in ids} and str(r.get("tier", "")).isdigit()
            and int(r["tier"]) >= tier and r.get("head")
            and _out(root, "rev-parse", f"{r['head']}:{rel}") == now for r in passes)
    top = max(t for t, _rel, _ids in plans)
    return top, all(cleared(t, rel, ids) for t, rel, ids in plans if t >= 2)

def plan_review_due(root: Path, branch: str) -> str | None:
    """Why a review of `branch` is a plan review, or None for a code review
    (#203: a session started for a changed plan took it for a code review and
    stopped with "no code"). A plan review is due when the branch changes
    nothing beyond plans and bookkeeping since its fork and an own Tier 2+
    plan has no clearing `-plan` pass for its current text. Plans are
    `.process-work/` and Spec Kit's `specs/` here (`new_code_on_origin` counts
    `specs/` as code: the tower queues the review, this tells its kind). The
    tip judged is the one the session reviews: origin's, as `sync_worktree`
    brings the worktree there (refute: a stale local ref read a plan-only
    branch while origin carried code); a branch origin does not have is
    judged by its local ref. What git cannot tell is a code review, as
    before — the session says when there is no code; `--plan-review` forces
    the plan review."""
    tip = _remote_head(root, branch)
    if tip and _git(root, "cat-file", "-e", f"{tip}^{{commit}}").returncode != 0 \
            and _git(root, "fetch", "-q", "origin", f"refs/heads/{branch}").returncode != 0:
        return None
    tip = tip or _out(root, "rev-parse", "--verify", "-q", f"{branch}^{{commit}}")
    base = _integration_base(root, tip) if tip else ""
    if not tip or not base:
        return None
    listed = _git(root, "diff", "--name-only", "-z", "--no-renames", base, tip)
    if listed.returncode != 0:
        return None
    changed = [p for p in listed.stdout.split("\0") if p]
    if any(not (p.startswith(BOOKKEEPING) or p.startswith(_review.SPECS_DIR + "/")) for p in changed):
        return None  # code to review
    tier, cleared = plan_review_state_at(root, tip)
    if tier is None or tier < 2 or cleared:
        return None
    return f"{branch} changes only plans and bookkeeping, and its Tier {tier} plan has no pass for its current text"


PLAN_GATES_TIMEOUT = 900  # the gate runner's own per-gate cap is 600 s


def plan_gates(wt: Path) -> str | None:
    """None when the process gates are green on a plan's worktree, else why
    not. A plan session need not push, so without this the gates
    first saw a plan at the execute push — downstream a missing
    `design-contract:` line turned that push red thirty times per branch. Not
    runnable is a verdict too: the execute push would not run them either."""
    if not (wt / RUNNER_REL).is_file():
        return None  # the project has no gates
    argv = gate_runner_argv(wt)
    if argv is None:
        return f"the gates cannot run: {not_runnable_reason(wt)}"
    try:
        r = subprocess.run(argv, cwd=wt, capture_output=True, text=True, timeout=PLAN_GATES_TIMEOUT,
                           env=git_environment())
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"the gate runner did not finish ({exc})"
    if r.returncode == 0:
        return None
    failed = [ln.strip() for ln in (r.stdout + r.stderr).splitlines() if ln.startswith("FAILED gates:")]
    return failed[-1] if failed else f"the gate runner exited {r.returncode}"

class _ChainLock(_QueueLock):
    def __init__(self, root: Path):
        super().__init__(root)
        self.path = _queue_dir(root) / "chain.lock"


def chain(root: Path, *, dry_run: bool = False) -> int:
    """One chain run at a time (two overlapping runs judged stale snapshots
    and stopped a fresh session — refutation)."""
    with _ChainLock(root):
        return _chain(root, dry_run=dry_run)


def _chain(root: Path, *, dry_run: bool = False) -> int:
    reports = _report.read_reports(root)
    for rec in records(root):
        if rec.get("remote") or rec.get("state") == "unknown":
            continue  # liveness lives elsewhere, or cannot be asked: act on nothing
        branch, phase = rec["branch"], rec.get("phase")
        rep = session_report(rec, reports)
        if rep is None:
            continue  # a report from before this session started is not this session's word
        try:
            issue = int(rec["issue"])
        except (KeyError, TypeError, ValueError):
            print(f"dispatch: {branch} — record without an issue, chain skips it", file=sys.stderr)
            continue
        state, nxt = rep.get("state"), None
        wt_rec = Path(rec["worktree"]) if rec.get("worktree") else None  # Path("") would be the cwd
        if state == "planned" and phase == "plan":
            nxt = "execute"
        elif state == "pushed" and phase == "execute":
            if dry_run:
                print(f"dispatch: would check {branch} on origin (tasks done, code beyond the attestation)")
                continue
            done, code = work_complete_on_origin(root, branch), new_code_on_origin(root, branch)
            if code is None or done is None:
                print(f"dispatch: {branch} reported pushed — cannot read its plan or code on origin; "
                      "not queuing a review", file=sys.stderr)
                continue
            if not done:
                print(f"dispatch: {branch} reported pushed — its plan still has open tasks; the worker is at it")
                continue  # `pushed` comes at the first push
            if not code:
                print(f"dispatch: {branch} reported pushed, but origin has no code beyond its last "
                      "attestation — not queuing a review")
                continue
            nxt = "review"
        elif state == "review-pass" and phase == "review" and rec.get("plan_review"):
            if wt_rec is None or not plan_review_state(root, wt_rec)[1]:
                print(f"dispatch: {branch} passed its plan review — waiting for the `-plan` pass on its "
                      "worktree")
                continue
            nxt = "execute"
        elif state == "review-pass" and phase == "review":
            if not attest_on_origin(root, branch):
                print(f"dispatch: {branch} passed review — waiting for its attestation on origin")
                continue
            print(f"dispatch: {branch} passed review, attestation on origin — a train candidate")
        else:
            continue  # blocked and everything else: the steward decides
        wt = wt_rec
        if wt is not None and wt.is_dir() and _out(wt, "status", "--porcelain"):
            print(f"dispatch: {branch} has uncommitted work — the worker commits first; chain waits",
                  file=sys.stderr)
            continue
        if dry_run:
            print(f"dispatch: would stop {branch} ({phase})" + (f" and queue {nxt}" if nxt else ""))
            continue
        plan_review = False
        if nxt == "execute" and wt is not None and wt.is_dir():
            # a Tier 2+ plan is read once, independently, before any code (#192) —
            # asked first: it is a few git reads, the gates below take minutes
            tier_of_plan, plan_cleared = plan_review_state(root, wt)
            uncleared = tier_of_plan is not None and tier_of_plan >= 2 and not plan_cleared
            if uncleared and tier_of_plan < 3:
                print(f"dispatch: {branch} reported planned without a plan review — its Tier 2 plan "
                      "session reviews the plan with a fresh subagent (refute.md, \"Refuting a plan\") "
                      "and attests `attest.py --plan-review`; no execute queued", file=sys.stderr)
                continue
            head = _out(wt, "rev-parse", "HEAD")
            if head and rec.get("plan_gates_red") == head:
                # judged red on this commit: say it again, do not re-run; a new plan commit is judged again
                print(f"dispatch: {branch} — gates still red on its plan ({head[:12]}): "
                      f"{rec.get('plan_gates_reason', '')}", file=sys.stderr)
                continue
            red = plan_gates(wt)
            if red:
                print(f"dispatch: {branch} reported planned, but the gates are red on its plan — {red}; "
                      f"no execute queued: the plan session fixes its plan (`dispatch.py say {branch} …`) "
                      "or the steward decides", file=sys.stderr)
                # only the runner's own verdict is kept: a timeout or a runner that cannot
                # start says nothing about the plan and is judged again next time
                current = _load_record(root, branch)
                if red.startswith("FAILED gates:") and current is not None \
                        and current[1].get("started") == rec.get("started"):
                    kept = {k: v for k, v in current[1].items() if k != "state"}  # state is read live
                    _write_record(root, branch, {**kept, "plan_gates_red": head, "plan_gates_reason": red})
                continue
            if uncleared:
                nxt, plan_review = "review", True  # Tier 3: a dispatched plan review, then execute
        current = _load_record(root, branch)
        if current is None or current[1].get("started") != rec.get("started") or current[1].get("phase") != phase:
            continue  # the session changed since it was judged
        if stop(root, branch, force=False, keep_report=True) != 0:
            continue
        if nxt:
            tier = rec.get("tier") if rec.get("tier") is not None else plan_tier_on_origin(root, branch)
            try:
                queue_add(root, issue=issue, phase=nxt, tier=tier, branch=branch, plan_review=plan_review)
            except OSError as exc:
                print(f"dispatch: {branch} stopped, but {nxt} could not be queued ({exc}) — queue it by hand: "
                      f"dispatch.py queue add --issue {issue} --phase {nxt}"
                      + (" --plan-review" if plan_review else "")
                      + (f" --tier {tier}" if tier is not None else "") + f" --branch {branch}", file=sys.stderr)
    return 0 if dry_run else drain(root)


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="dispatch.py", description=__doc__.split("\n\n")[0])
    p.add_argument("--root", default=".")
    sub = p.add_subparsers(dest="command", required=True)
    s = sub.add_parser("start")
    s.add_argument("--issue", type=int, required=True)
    s.add_argument("--phase", choices=PHASES, required=True)
    s.add_argument("--owner-approved", action="store_true", help="owner approved the brainstorm; start plan")
    s.add_argument("--tier", type=int)
    s.add_argument("--branch")
    s.add_argument("--title", help="slug source for a new branch name")
    s.add_argument("--dry-run", action="store_true")
    s.add_argument("--plan-review", action="store_true",
                   help="with --phase review: review the plan before execute, not the code")
    sub.add_parser("list")
    lg = sub.add_parser("log")
    lg.add_argument("branch")
    lg.add_argument("--lines", type=int, default=30)
    sy = sub.add_parser("say")
    sy.add_argument("branch")
    sy.add_argument("text")
    st = sub.add_parser("stop")
    st.add_argument("branch")
    st.add_argument("--force", action="store_true")
    ch = sub.add_parser("chain")
    ch.add_argument("--dry-run", action="store_true")
    qu = sub.add_parser("queue")
    qsub = qu.add_subparsers(dest="queue_command", required=True)
    qa = qsub.add_parser("add")
    qa.add_argument("--issue", type=int, required=True)
    qa.add_argument("--phase", choices=PHASES, required=True)
    qa.add_argument("--tier", type=int)
    qa.add_argument("--branch")
    qa.add_argument("--plan-review", action="store_true", help="with --phase review: a plan review")
    qsub.add_parser("list")
    sub.add_parser("drain")
    po = sub.add_parser("policy")
    po.add_argument("--tier", type=int)
    po.add_argument("--class", dest="cls", metavar="CLASS",
                    help="task class (mechanical, design, …): its row wins over the tier")
    a = p.parse_args(argv)
    root = Path(_out(Path(a.root).resolve(), "rev-parse", "--show-toplevel") or a.root).resolve()
    if a.command == "start":
        return start(root, issue=a.issue, phase=a.phase, tier=a.tier, branch=a.branch, title=a.title,
                     dry_run=a.dry_run, owner_approved=a.owner_approved, plan_review=a.plan_review)
    if a.command == "list":
        return list_sessions(root)
    if a.command == "log":
        return show_log(root, a.branch, a.lines)
    if a.command == "say":
        return say(root, a.branch, a.text)
    if a.command == "stop":
        return stop(root, a.branch, force=a.force)
    if a.command == "chain":
        return chain(root, dry_run=a.dry_run)
    if a.command == "queue":
        if a.queue_command == "add":
            queue_add(root, issue=a.issue, phase=a.phase, tier=a.tier, branch=a.branch,
                      plan_review=a.plan_review and a.phase == "review")
        for e in queue_load(root):
            print(f"#{e['issue']} {e['phase']}" + (f" tier {e['tier']}" if e.get("tier") is not None else "")
                  + (f" on {e['branch']}" if e.get("branch") else ""))
        return 0
    if a.command == "drain":
        return drain(root)
    policy = load_policy(root)
    for ph in PHASES:
        cell = cell_for(policy, a.tier, ph, a.cls)
        why = effort_refusal(policy, ph, cell)
        print(f"{ph}: {labelled(cell.model, cell.effort)}" + (f"  via `{cell.command}`" if cell.command else "")
              + (f"  WARNING: {why}" if why else ""))
    if policy.get("decision_channel"):
        print(f"decision_channel: {policy['decision_channel']}")
    print(f"command: {policy['command']}  (runner {policy.get('runner', 'detached')}, "
          f"max_workers {max_workers(policy)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
