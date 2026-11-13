#!/usr/bin/env python3
"""process_context: deterministic session orientation — one read-only call
instead of exploratory ls/grep/journal-archaeology at session start.

Prints a single JSON object with everything an agent needs to resume:
branch, state file, active plan(s) with their tier:/issue: lines, the active
spec directory with the NEXT unchecked task, unresolved clarification-marker
counts, and the untriaged inbox size. The token saving is the point: /prime
and /execute call this instead of exploring, which is also what makes small
models robust in those phases (no orientation guesswork).

Scoped by default: only the current work's plans and spec dirs carry full
detail (`active_plans`, `spec_features`); every other one is a one-line entry
in `other_plans` / `other_specs`, so nothing is dropped and a repo with forty
plans does not print forty ledgers. The current work is `--issue N`, else the
branch: a spec dir named like the branch leaf (speckit.md, Branching), else
the issue the branch name leads with (check_review.branch_issue). `scope`
says which. `--all` prints every item in full (the unscoped shape).

    process_context.py [root] [--issue N | --all] [--cost] [--trend]

Read-only, never a gate, pure stdlib. Borrowed pattern: Spec Kit's
check-prerequisites --json (deterministic context bootstrap).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_review import OPEN_TASK, branch_issue, declared_issue_numbers, open_questions, plan_tier, spec_dir_issue  # noqa: E402
from process_git import answers_release  # noqa: E402  (the release grammar's owner)

PLANS = ".process-work/plans"
STATE = ".process-work/state"
INBOX = ".process-work/inbox.md"
SPECS = "specs"

ISSUE = re.compile(r"^\s*(?:[-*+]\s+)?issue\s*:\s*(\S+)", re.IGNORECASE | re.MULTILINE)
UNCHECKED = OPEN_TASK  # the gates' grammar; findall yields the task text
CHECKED = re.compile(r"^[ \t]*[-*+][ \t]+\[[xX]\][ \t]", re.MULTILINE)
MARKER = re.compile(r"\[NEEDS CLARIFICATION", re.IGNORECASE)
# the decisions ledger (journal-state-plans.md, Plans): one line per decision
# made in dialogue — `- DECISION 2026-09-10 owner: what — because why`. It is
# surfaced here so every re-hydration (/prime, /execute, /review) sees what a
# compaction summary would have dropped.
DECISION = re.compile(r"^\s*(?:[-*+]\s+)?DECISION\s+(\d{4}-\d{2}-\d{2})\s+([^:]+):\s*(.+?)\s*$",
                      re.MULTILINE)
DECISIONS_HEADING = re.compile(r"^#{2,4}\s+Decisions\b", re.IGNORECASE | re.MULTILINE)
# a question still open — `DECISION NEEDED <date> <who>: …` — is not a
# decision; a re-hydrated session must see that it is waiting, not act as
# if the plan were settled (check_review.open_questions owns the line)


# a task line's class (a class the policy defines; unmarked: standard) picks the
# model a spawn names — docs/process/tower.md, "Model by task class". Read only
# from the bracket tokens after the task id, like `[P]` and `[US1]`, never from
# the description
TASK_TOKENS = re.compile(r"^(?:[A-Za-z]*\d[\w.]*\s+)?((?:\[[^\]\s]+\]\s*)+)")
DEFAULT_CLASSES = ("mechanical", "design")


def _policy(root: Path) -> dict | None:
    """The resolved model policy, or None — orientation never fails on it."""
    try:
        import dispatch as _dispatch  # noqa: E402  (sibling; one owner for the policy)
        return _dispatch.load_policy(root)
    except (Exception, SystemExit):  # noqa: BLE001
        return None


def _next_task(text: str, tier: int | None, policy: dict | None) -> dict:
    """The first unchecked task with its class and, when the policy loads, its
    execute model (dispatch.model_for)."""
    unchecked = UNCHECKED.findall(text)
    if not unchecked:
        return {"next_task": None}
    line = unchecked[0].strip()
    known = tuple((policy or {}).get("classes") or DEFAULT_CLASSES)
    m = TASK_TOKENS.match(line)
    tokens = re.findall(r"\[([^\]\s]+)\]", m.group(1)) if m else []
    entry = {"next_task": line,
             "next_task_class": next((t for t in tokens if t in known), "standard")}
    if policy is not None:
        try:
            import dispatch as _dispatch  # noqa: E402
            entry["next_task_model"] = _dispatch.model_for(policy, tier, "execute", entry["next_task_class"])
        except (Exception, SystemExit):  # noqa: BLE001
            pass
    return entry


def _branch(root: Path) -> str | None:
    r = subprocess.run(["git", "-C", str(root), "symbolic-ref", "--short", "HEAD"],
                       capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _plan_info(p: Path) -> dict:
    text = _read(p)
    tier = plan_tier(text)
    issue = ISSUE.search(text)
    return {"file": str(p), "tier": tier,
            "issue": issue.group(1) if issue else None,
            "decisions": [f"{d} {who}: {what}" for d, who, what in DECISION.findall(text)],
            "open_questions": [f"{m.group(1)} {m.group(2) or 'worker'}: {m.group(3)}" for m in open_questions(text)],
            "decisions_section": bool(DECISIONS_HEADING.search(text))}


def _args(argv: list[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="process_context.py", description=(
        "Session orientation as one JSON object, scoped to the current work "
        "(--issue N, else the branch); every other plan and spec dir is a one-line index entry."))
    ap.add_argument("root", nargs="?", default=".", help="repository root (default: .)")
    scope = ap.add_mutually_exclusive_group()
    scope.add_argument("--issue", type=int, metavar="N", help="scope to issue N (beats the branch)")
    scope.add_argument("--all", action="store_true", help="every plan and spec dir in full detail")
    ap.add_argument("--cost", action="store_true",
                    help="add context_cost: approx tokens and lines a session reads (always over "
                         "everything), with entry_load: each harness's anchors, nested anchors, overlays")
    ap.add_argument("--trend", action="store_true",
                    help="with --cost (implied): the same sums at each commit that switches "
                         f"{ANSWERS} to a release tag (the last {TREND_POINTS})")
    return ap.parse_args(argv)


def _scope(issue: int | None, branch: str | None,
           spec_issues: dict[str, int | None]) -> tuple[dict, str | None]:
    """(scope, the spec dir named like the branch leaf). A spec branch is
    named after its dir (`003-chat`), so that match comes before the
    leading-number read, which would take `003` for issue 3."""
    if issue is not None:
        return {"issue": issue, "source": "--issue"}, None
    leaf = (branch or "").rsplit("/", 1)[-1]
    if leaf in spec_issues:
        return {"issue": spec_issues[leaf], "source": "branch"}, leaf
    number = branch_issue(branch) if branch else None
    if number is not None:
        return {"issue": int(number), "source": "branch"}, None
    return {"issue": None, "source": "none"}, None


def main(argv: list[str] | None = None) -> int:
    args = _args(sys.argv[1:] if argv is None else argv)
    root = Path(args.root).resolve()
    branch = _branch(root)
    out: dict = {"branch": branch}

    slug = (branch or "").replace("/", "-")
    state = root / STATE / f"{slug}.md"
    out["state_file"] = str(state.relative_to(root)) if state.is_file() else None

    journal_shard = root / ".process-work/journal" / slug
    shard_files = sorted(journal_shard.glob("*.md")) if journal_shard.is_dir() else []
    flat = sorted((root / ".process-work/journal").glob("*.md")) \
        if (root / ".process-work/journal").is_dir() else []
    latest = (shard_files or flat)
    out["latest_journal"] = str(latest[-1].relative_to(root)) if latest else None

    # collect everything first: --cost measures the whole set, the scope only
    # decides what is printed in full
    policy = _policy(root)
    pdir = root / PLANS
    plans = []  # (detail, declared issue numbers, open checkboxes)
    for p in (sorted(pdir.glob("*.md")) if pdir.is_dir() else []):
        if p.name.startswith("design-"):
            continue
        text = _read(p)
        info = _plan_info(p)
        plans.append(({**info, "file": str(p.relative_to(root)),
                       **_next_task(text, info["tier"], policy)},
                      declared_issue_numbers(text), len(UNCHECKED.findall(text))))
    out["active_plans"] = [d for d, _nums, _open in plans]

    features = []
    spec_issues: dict[str, int | None] = {}
    sdir = root / SPECS
    if sdir.is_dir():
        for fdir in sorted(d for d in sdir.iterdir() if d.is_dir()):
            tasks = _read(fdir / "tasks.md")
            unchecked = UNCHECKED.findall(tasks)
            plan = ({k: v for k, v in _plan_info(fdir / "plan.md").items()
                     if k != "file"} if (fdir / "plan.md").is_file() else {})
            info = {
                "dir": str(fdir.relative_to(root)),
                **plan,
                "tasks_done": len(CHECKED.findall(tasks)),
                "tasks_open": len(unchecked),
                **_next_task(tasks, plan.get("tier"), policy),
                "unresolved_markers": sum(
                    len(MARKER.findall(_read(f))) for f in fdir.glob("*.md")),
            }
            features.append(info)
            spec_issues[fdir.name] = spec_dir_issue(fdir)
    out["spec_features"] = features

    inbox = root / INBOX
    out["inbox_items"] = sum(
        1 for line in _read(inbox).splitlines() if line.strip().startswith(("-", "*"))
    ) if inbox.is_file() else 0

    if args.cost or args.trend:
        out["context_cost"] = context_cost(root, out, trend=args.trend)

    if not args.all:
        out["scope"], spec_dir = _scope(args.issue, branch, spec_issues)
        n = out["scope"]["issue"]
        mine = [n is not None and n in nums for _d, nums, _open in plans]
        out["active_plans"] = [d for (d, _nums, _open), m in zip(plans, mine) if m]
        out["other_plans"] = [{"file": d["file"], "issue": nums[0] if nums else None,
                               "tier": d["tier"], "tasks_open": opened}
                              for (d, nums, opened), m in zip(plans, mine) if not m]
        names = [Path(f["dir"]).name for f in features]
        mine = [name == spec_dir or (n is not None and spec_issues[name] == n) for name in names]
        out["spec_features"] = [f for f, m in zip(features, mine) if m]
        # a finished spec dir nobody pruned stays visible, marked
        out["other_specs"] = [{"dir": f["dir"], "issue": spec_issues[name], "tier": f.get("tier"),
                               "tasks_open": f["tasks_open"],
                               **({"done": True} if f["tasks_done"] and not f["tasks_open"] else {})}
                              for f, name, m in zip(features, names, mine) if not m]
        if n is None and spec_dir is None:
            out["hint"] = ("no current work in scope (main or an issue-less branch) — "
                           "pass --issue N for one item's detail, --all for every item")

    print(json.dumps(out, indent=2))
    return 0


# --- context cost: what a session reads, in approximate tokens ------------
# Measure before cutting. "Which doc is too long" is guesswork until the
# sizes are on the table; this puts them there. The estimate is chars/4 — a
# rough average for English prose and code in current tokenizers — so the
# numbers compare against each other, not against a bill.
CHARS_PER_TOKEN = 4
ANCHORS = ("CLAUDE.md", "AGENTS.md", ".github/copilot-instructions.md")
COMMAND_DIRS = (".claude/commands", ".github/prompts")
KERNEL = "docs/process/kernel.md"
RULES = "docs/process/mandatory-rules.md"
# entry load: what each harness reads before the first prompt. The kernel is
# a copy inside the anchor, so the anchor files are the whole of it.
HARNESS_ANCHORS = {"claude": ("CLAUDE.md",), "agents_md": ("AGENTS.md",),
                   "copilot": (".github/copilot-instructions.md",
                               ".github/instructions/process.instructions.md")}
SUBTREE_ANCHOR_NAMES = ("CLAUDE.md", "AGENTS.md")  # a harness loads these on top in a subtree
OVERLAY_DOCS = "docs/process"
COMMAND_OVERLAYS = "docs/process/commands"  # overlays.md, "Where an overlay lives"
LOCAL = ".local.md"
ANSWERS = ".copier-answers.yml"
TREND_POINTS = 12


def _size(texts: list[str]) -> dict:
    return {"files": len(texts),
            "tokens": sum(len(t) for t in texts) // CHARS_PER_TOKEN,
            "lines": sum(len(t.splitlines()) for t in texts)}


def _tokens(paths: list[Path]) -> dict:
    return _size([_read(p) for p in paths if p.is_file()])


def _mandatory_files(tree: set[str]) -> dict[str, list[str]]:
    """The groups every session loads, as relative paths present in `tree` —
    one owner for the working copy and for a commit (--trend)."""
    return {"anchor": [a for a in ANCHORS if a in tree],
            "kernel": [KERNEL] if KERNEL in tree else [],
            "mandatory_rules": [RULES] if RULES in tree else [],
            "commands": sorted(p for p in tree
                               if p.rpartition("/")[0] in COMMAND_DIRS and p.endswith(".md"))}


def _entry_files(tree: set[str]) -> dict:
    """entry_load's groups over the relative paths in `tree`: the anchors of
    each harness present, the nested anchors (never the root ones), the
    command overlays and the doc overlays (command overlays apart)."""
    return {"harnesses": {h: [f for f in fs if f in tree] for h, fs in HARNESS_ANCHORS.items()
                          if any(f in tree for f in fs)},
            "subtree_anchors": sorted(p for p in tree if "/" in p
                                      and p.rpartition("/")[2] in SUBTREE_ANCHOR_NAMES),
            "command_overlays": sorted(p for p in tree if p.endswith(LOCAL)
                                       and p.rpartition("/")[0] == COMMAND_OVERLAYS),
            "doc_overlays": sorted(p for p in tree if p.endswith(LOCAL)
                                   and p.startswith(OVERLAY_DOCS + "/")
                                   and p.rpartition("/")[0] != COMMAND_OVERLAYS)}


def _entry_paths(files: dict) -> list[str]:
    return [p for k, v in files.items()
            for ps in (v.values() if k == "harnesses" else (v,)) for p in ps]


def _worktree(root: Path) -> tuple[set[str], str | None]:
    """The relative paths the groups read in the working copy, and why the
    nested anchors are unknown (None when `git ls-files` answered). Nested
    anchors come from the index, so a vendored or scratch tree stays out."""
    fixed = {*ANCHORS, *(f for fs in HARNESS_ANCHORS.values() for f in fs), KERNEL, RULES}
    tree = {f for f in fixed if (root / f).is_file()}
    for d in COMMAND_DIRS:
        if (root / d).is_dir():
            tree |= {f"{d}/{p.name}" for p in (root / d).glob("*.md") if p.is_file()}
    if (root / OVERLAY_DOCS).is_dir():
        tree |= {p.relative_to(root).as_posix() for p in (root / OVERLAY_DOCS).rglob("*" + LOCAL)
                 if p.is_file()}
    r = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--",
                        *(f":(glob)**/{n}" for n in SUBTREE_ANCHOR_NAMES)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return tree, (r.stderr.strip().splitlines() or ["git ls-files failed"])[0]
    return tree | {p for p in r.stdout.split("\0") if p and (root / p).is_file()}, None


def _entry_load(files: dict, read: Callable[[str], str], *, detail: bool) -> dict:
    """Sizes of entry_load's groups; `detail` adds the paths, the overlay of
    each command and the five largest doc overlays (the trend keeps sums)."""
    texts = {p: read(p) for p in _entry_paths(files)}

    def size(paths: list[str]) -> dict:
        return _size([texts[p] for p in paths])

    def each(p: str) -> dict:
        one = size([p])
        return {"file": p, "tokens": one["tokens"], "lines": one["lines"]}

    load: dict = {"harnesses": {h: size(fs) for h, fs in files["harnesses"].items()},
                  "subtree_anchors": size(files["subtree_anchors"]),
                  "overlays": {"commands": size(files["command_overlays"]),
                               "docs": size(files["doc_overlays"])}}
    if detail:
        load["subtree_anchors"]["paths"] = [each(p) for p in files["subtree_anchors"]]
        load["overlays"]["commands"]["by_command"] = {
            p.rpartition("/")[2][:-len(LOCAL)]: each(p) for p in files["command_overlays"]}
        load["overlays"]["docs"]["largest"] = [
            each(p) for p in sorted(files["doc_overlays"], key=lambda p: (-len(texts[p]), p))[:5]]
    return load


def context_cost(root: Path, ctx: dict, *, trend: bool = False) -> dict:
    """Token sizes over the UNSCOPED context (every plan and spec dir), split
    into what every session loads (`mandatory`) and what it reads on demand
    (`available`); `entry_load` stands apart from both, so the session
    estimate stays what it was."""
    pdocs = root / "docs/process"
    tree, why = _worktree(root)
    mandatory: dict[str, list[Path]] = {k: [root / p for p in v]
                                        for k, v in _mandatory_files(tree).items()}
    jdir = root / ".process-work/journal"
    available: dict[str, list[Path]] = {
        "process_docs": [p for p in sorted(pdocs.rglob("*.md"))
                         if p not in (*mandatory["kernel"], *mandatory["mandatory_rules"])]
        if pdocs.is_dir() else [],
        "product_frame": [root / "PRODUCT.md"],
        "active_plans": [root / p["file"] for p in ctx.get("active_plans", [])],
        "state_and_latest_journal": [root / f for f in
                                     (ctx.get("state_file"), ctx.get("latest_journal")) if f],
        "all_journal_shards": sorted(jdir.rglob("*.md")) if jdir.is_dir() else [],
        "spec_dirs": [p for f in ctx.get("spec_features", [])
                      for p in sorted((root / f["dir"]).glob("*.md"))]}
    report: dict = {"mandatory": {k: _tokens(v) for k, v in mandatory.items()},
                    "available": {k: _tokens(v) for k, v in available.items()}}
    # what /prime actually loads: the mandatory set + the branch's own working
    # memory — the process docs are read on demand, the journal never whole
    session = sum(g["tokens"] for g in report["mandatory"].values()) + sum(
        report["available"][k]["tokens"] for k in
        ("product_frame", "active_plans", "state_and_latest_journal"))
    report["session_start_estimate_tokens"] = session
    load = _entry_load(_entry_files(tree), lambda p: _read(root / p), detail=True)
    if why is not None:
        load["subtree_anchors"] = {"files": None, "tokens": None, "lines": None,
                                   "paths": [], "missing": why}
    report["entry_load"] = load
    groups = {**mandatory, **available}
    everything = sorted({p for ps in groups.values() for p in ps if p.is_file()},
                        key=lambda p: -len(_read(p)))
    report["largest"] = [{"file": str(p.relative_to(root)),
                          "tokens": len(_read(p)) // CHARS_PER_TOKEN}
                         for p in everything[:10]]
    if trend:
        report["trend"] = cost_trend(root)
    report["unit"] = f"approx tokens = chars / {CHARS_PER_TOKEN}"
    return report


# --- trend: the same sums at each release the project updated to ----------

def _blobs(root: Path, specs: list[str]) -> list[str | None]:
    """The text of each `git cat-file` spec (a blob id or `<rev>:./<path>`),
    None where it is missing — one batch call, not one `git show` per file."""
    if not specs:
        return []
    r = subprocess.run(["git", "-C", str(root), "cat-file", "--batch"],
                       input="".join(f"{s}\n" for s in specs).encode(), capture_output=True)
    data, pos, got = r.stdout, 0, []
    for _spec in specs:
        nl = data.find(b"\n", pos)
        if nl < 0:
            got.append(None)
            continue
        head = data[pos:nl].split()
        pos = nl + 1
        if len(head) != 3 or not head[2].isdigit():
            got.append(None)  # `<spec> missing`
            continue
        size = int(head[2])
        got.append(data[pos:pos + size].decode("utf-8", "replace"))
        pos += size + 1
    return got


def _release_switches(root: Path) -> tuple[list[tuple[str, str, str]] | None, str | None]:
    """(commit, date, release) for each commit whose `.copier-answers.yml`
    moves to a release tag, oldest first — or (None, why) without git. A
    commit that changes other answers, or moves to a SHA or dev ref, is none."""
    r = subprocess.run(["git", "-C", str(root), "log", "--format=%H %cs", "--", ANSWERS],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return None, (r.stderr.strip().splitlines() or ["git log failed"])[0]
    commits = [line.split()[:2] for line in reversed(r.stdout.splitlines()) if line.strip()]
    texts = _blobs(root, [f"{sha}:./{ANSWERS}" for sha, _date in commits])
    switches, before = [], None
    for (sha, date), text in zip(commits, texts):
        release = answers_release(text) if text is not None else None
        if release is not None and release != before:
            switches.append((sha, date, "v{}.{}.{}".format(*release)))
        before = release
    return switches, None


def _tree_blobs(root: Path, sha: str) -> dict[str, str]:
    """path -> blob id at `sha`, relative to `root` like the working copy."""
    r = subprocess.run(["git", "-C", str(root), "ls-tree", "-r", "-z", sha],
                       capture_output=True, text=True)
    blobs = {}
    for entry in r.stdout.split("\0"):
        meta, _tab, path = entry.partition("\t")
        parts = meta.split()
        if len(parts) == 3 and parts[1] == "blob":
            blobs[path] = parts[2]
    return blobs


def cost_trend(root: Path) -> dict:
    """`mandatory` and `entry_load` sums at the last TREND_POINTS commits that
    switch `.copier-answers.yml` to a release tag, read from each commit's
    tree, never from the working copy."""
    switches, why = _release_switches(root)
    if switches is None:
        return {"value": None, "quality": "missing", "why": why}
    if not switches:
        return {"value": None, "quality": "missing",
                "why": f"no commit switches {ANSWERS} to a release tag"}
    points = []
    for sha, date, release in switches[-TREND_POINTS:]:
        blobs = _tree_blobs(root, sha)
        must, entry = _mandatory_files(set(blobs)), _entry_files(set(blobs))
        paths = sorted({*(p for ps in must.values() for p in ps), *_entry_paths(entry)})
        texts = dict(zip(paths, _blobs(root, [blobs[p] for p in paths])))

        def read(p: str, texts: dict[str, str | None] = texts) -> str:
            return texts.get(p) or ""
        points.append({"commit": sha[:12], "date": date, "release": release,
                       "mandatory": {k: _size([read(p) for p in v]) for k, v in must.items()},
                       "entry_load": _entry_load(entry, read, detail=False)})
    return {"value": points, "quality": "measured"}


if __name__ == "__main__":
    raise SystemExit(main())
