#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6,<7"]
# ///
"""Gate modes — the check graph's lifecycle, one record at a time.

A gate runs in one of four modes: `block` (the default: a failure stops the
push), `shadow` (runs and records, never blocks), `sampled` (runs on a share
of commits, never blocks) and `off`. The mode comes from one place only: the
append-only record `docs/process/gate-changes.local.jsonl`. Nothing else — not
`gates.local.json`, not an environment variable — weakens a gate.

  gate_modes.py status
  gate_modes.py weaken GATE --to shadow|sampled|off [--rate R] --decision "owner …"
                           [--guardrail NAME ...]
  gate_modes.py restore GATE --reason TEXT [--lock]
  gate_modes.py unlock GATE --triage TEXT
  gate_modes.py sentinel [--dry-run]
  gate_modes.py check

Rules (docs/process/optimization.md, "The process as a check graph"):

- Weakening needs an owner decision line (`--decision "owner …"`), every
  time, in this release. The line is text a session can write; what backs it
  is review: the record lives under `docs/process/`, which the review gate
  covers like any process configuration (never `.process-work/`, which it
  treats as bookkeeping). Core gates and the mandate's protected gates
  cannot be weakened at all.
- `--observe` (with `--to shadow`) is for a new gate that never blocked: the
  sentinel does not restore it on a failure, so its false alarms can be
  counted first. A weakened gate that used to block is never `--observe`.
- `restore` returns a gate to `block`; with `--lock` the gate cannot be
  weakened again until `unlock` records a triage.
- `sentinel` is deterministic and only ever restores: a `sampled` or `shadow`
  gate that failed on a clean commit goes back to `block` at once (pending
  triage), and a breached guardrail rolls back every still-active weakening
  that touches it, newest first, each locked. Newest first is containment,
  not a claim about the cause.

A record that does not parse, or a weakening that breaks a rule, is ignored
and named: the gate stays `block`. Never a gate itself; it never fails a
push by its own reading.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import subprocess
import sys
from pathlib import Path

CHANGES = "docs/process/gate-changes.local.jsonl"
MODES = ("block", "shadow", "sampled", "off")
WEAK = ("shadow", "sampled", "off")
MANDATE = "docs/process/optimization.local.json"
EVENTS = "process-gate-events.jsonl"


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="milliseconds")


def _when(value: object) -> _dt.datetime | None:
    """An aware timestamp, or None: a naive or unparseable one is no timestamp."""
    try:
        when = _dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return when if when.tzinfo else None


def base_ref(root: Path) -> str | None:
    """The integration branch a weakening must already be on — a remote's
    default branch, never a local one: at pre-push time a local `main` may be
    the very commit being pushed. None: no weakening is honoured."""
    for ref in ("refs/remotes/origin/HEAD", "refs/remotes/origin/main", "refs/remotes/origin/master"):
        r = subprocess.run(["git", "-C", str(root), "rev-parse", "--verify", "--quiet", ref],
                           capture_output=True, text=True)
        if r.returncode == 0:
            return ref
    r = subprocess.run(["git", "-C", str(root), "for-each-ref", "--format=%(refname)", "refs/remotes/*/HEAD"],
                       capture_output=True, text=True)
    heads = sorted(r.stdout.split()) if r.returncode == 0 else []
    return heads[0] if heads else None


def read_changes(root: Path, ref: str | None = None) -> tuple[list[dict], list[str]]:
    """(records in file order, problems) from the working tree, or as committed
    at `ref`. A line that is not a JSON object is a problem."""
    rows: list[dict] = []
    problems: list[str] = []
    if ref is None:
        try:
            text = (root / CHANGES).read_text(encoding="utf-8")
        except FileNotFoundError:
            return rows, problems
        except (OSError, ValueError) as exc:  # unreadable is not empty: say so
            return rows, [f"{CHANGES}: unreadable ({exc}) — ignored"]
    else:
        r = subprocess.run(["git", "-C", str(root), "show", f"{ref}:{CHANGES}"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode != 0:
            return rows, problems
        text = r.stdout
    for n, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            problems.append(f"{CHANGES}:{n}: not JSON — ignored")
            continue
        if not isinstance(row, dict) or not isinstance(row.get("gate"), str):
            problems.append(f"{CHANGES}:{n}: needs a 'gate' — ignored")
            continue
        row["_line"] = n
        rows.append(row)
    return rows, problems


def _mandate_guardrails(root: Path, ref: str | None = None) -> dict:
    """The mandate's `guardrails` mapping, from the working tree or as committed at `ref`."""
    try:
        if ref is None:
            text = (root / MANDATE).read_text(encoding="utf-8")
        else:
            r = subprocess.run(["git", "-C", str(root), "show", f"{ref}:{MANDATE}"],
                               capture_output=True, text=True, encoding="utf-8", errors="replace")
            text = r.stdout if r.returncode == 0 else ""
        data = json.loads(text) if text else {}
    except (OSError, ValueError):
        return {}
    g = data.get("guardrails") if isinstance(data, dict) else None
    return g if isinstance(g, dict) else {}


def protected_gates(root: Path, ref: str | None = None) -> set[str]:
    """`guardrails.protected` — gates no record may weaken. The union of the
    working tree's mandate and the integration branch's: a branch cannot
    un-protect a gate by editing its own copy."""
    names: set[str] = set()
    for where in (None, ref) if ref else (None,):
        listed = _mandate_guardrails(root, where).get("protected")
        if isinstance(listed, list):
            names |= {n for n in listed if isinstance(n, str)}
    return names


def guardrails(root: Path) -> tuple[list[dict], list[str]]:
    """The mandate's `guardrails.limits`: [{"name", "metric", "max", "window_days"}]."""
    limits = _mandate_guardrails(root).get("limits")
    if limits is None:
        return [], []
    out, problems = [], []
    for i, g in enumerate(limits if isinstance(limits, list) else [limits]):
        if (isinstance(g, dict) and isinstance(g.get("name"), str) and g.get("metric") in METRICS
                and isinstance(g.get("max"), int) and not isinstance(g.get("max"), bool)
                and isinstance(g.get("window_days", 30), int) and not isinstance(g.get("window_days"), bool)):
            out.append({"window_days": 30, **g})
        else:
            problems.append(f"{MANDATE}: guardrails.limits[{i}] needs name, metric "
                            f"({', '.join(METRICS)}), max and window_days — ignored")
    return out, problems


def effective(root: Path, core: set[str] = frozenset()) -> tuple[dict[str, dict], list[str]]:
    """{gate: {"mode", "rate", "since", "record", "guardrails", "locked"}} for every gate a
    record names, and the problems. Gates without records are `block`.

    A weakening counts only once it is on the integration branch: a branch
    cannot record its own "owner" line and push past a gate with it. A
    restore counts at once, from the working tree — stricter never waits."""
    ref = base_ref(root)
    protected = protected_gates(root, ref)
    tree_rows, problems = read_changes(root)
    tree, more = fold(tree_rows, core, protected)
    problems += more
    base_rows, base_problems = read_changes(root, ref) if ref else ([], [])
    base, more = fold(base_rows, core, protected)
    problems += [f"{ref}: {p}" for p in base_problems + more if p not in problems]
    state = {}
    for gate in sorted(set(base) | set(tree)):
        b, t = base.get(gate), tree.get(gate)
        if t is not None and t["mode"] == "block":
            state[gate] = t  # restored here: blocks now, whatever the base says
        elif b is not None:
            state[gate] = b
        elif t is not None:
            state[gate] = {**t, "mode": "block", "rate": None}
            problems.append(f"{gate}: weakened on this branch only — takes effect once "
                            f"{CHANGES} is merged to {ref or 'an integration branch'}")
    return state, problems


def fold(rows: list[dict], core: set[str], protected: set[str]) -> tuple[dict[str, dict], list[str]]:
    """Replay the records in order; a record that breaks a rule is named and skipped."""
    problems: list[str] = []
    state: dict[str, dict] = {}
    for row in rows:
        gate, action, where = row["gate"], row.get("action"), f"{CHANGES}:{row['_line']}"
        st = state.setdefault(gate, {"mode": "block", "rate": None, "since": None, "record": None,
                                     "guardrails": [], "locked": False})
        if action == "weaken":
            to, rate = row.get("to"), row.get("rate")
            decision = str(row.get("decision") or "")
            marks = row.get("guardrails", [])
            why = ("a core gate cannot be weakened" if gate in core else
                   "a protected gate (mandate) cannot be weakened" if gate in protected else
                   "locked since its last restore — unlock with a triage first" if st["locked"] else
                   f"'to' must be one of {', '.join(WEAK)}" if to not in WEAK else
                   "a sampled gate needs a rate in (0, 1]" if to == "sampled" and not (
                       isinstance(rate, (int, float)) and not isinstance(rate, bool) and 0 < rate <= 1) else
                   "weakening needs an owner decision ('decision': 'owner …')"
                   if not decision.strip().lower().startswith("owner") else
                   "a weakening needs a timezone-aware 'ts'" if _when(row.get("ts")) is None else
                   "'guardrails' must be a list of names" if not (
                       isinstance(marks, list) and all(isinstance(m, str) for m in marks)) else None)
            if why:
                problems.append(f"{where}: {gate}: {why} — the gate stays {st['mode']}")
                continue
            st.update(mode=to, rate=rate if to == "sampled" else None, since=row.get("ts"),
                      record=row.get("id"), guardrails=list(marks),
                      observe=to == "shadow" and row.get("observe") is True)
        elif action == "restore":
            st.update(mode="block", rate=None, since=row.get("ts"), record=row.get("id"),
                      guardrails=[], locked=bool(row.get("lock")))
        elif action == "unlock":
            if not str(row.get("triage") or "").strip():
                problems.append(f"{where}: {gate}: an unlock needs a triage — the gate stays locked")
                continue
            st["locked"] = False
        else:
            problems.append(f"{where}: {gate}: unknown action {action!r} — ignored")
    return state, problems


def sampled_in(gate: str, head: str | None, rate: float) -> bool:
    """Whether a `sampled` gate runs on this commit: a stable share by commit, so
    every host and every retry agrees. Without a commit it runs."""
    if not head:
        return True
    digest = hashlib.sha256(f"{gate}\0{head}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2 ** 64 < rate


# --- metrics a guardrail can watch ---------------------------------------------

def _regressions(root: Path, window_days: int) -> int | None:
    """Commits on the integration branch within the window that repair a
    regression (`Regression-of:` trailer, process_git owns the grammar).
    None when the branch cannot be read — unknown, never "no breach"."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from process_git import regression_refs  # noqa: PLC0415

    ref = base_ref(root)
    if ref is None:
        return None
    r = subprocess.run(["git", "-C", str(root), "log", ref,
                        f"--since={window_days}.days", "-z", "--format=%B"], capture_output=True)
    if r.returncode != 0:
        return None
    return sum(1 for body in r.stdout.decode("utf-8", "surrogateescape").split("\0")
               if regression_refs(body))


METRICS = {"regressions": _regressions}


def _common_dir(root: Path) -> Path | None:
    r = subprocess.run(["git", "-C", str(root), "rev-parse", "--git-common-dir"],
                       capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip():
        return None
    p = Path(r.stdout.strip())
    return p if p.is_absolute() else root / p


def _weak_failures(root: Path, gate: str, since: str | None) -> list[str]:
    """Commits a shadow or sampled run of `gate` failed on, on a clean tree, since `since`."""
    common = _common_dir(root)
    if common is None:
        return []
    start = _when(since)
    heads = []
    try:
        lines = (common / EVENTS).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in lines:
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        when = _when(ev.get("ts")) if isinstance(ev, dict) else None
        if when is None:
            continue
        if (ev.get("gate") == gate and ev.get("mode") in ("shadow", "sampled")
                and ev.get("outcome") in ("fail", "timeout") and ev.get("dirty") is False
                and (start is None or when >= start)):
            heads.append(str(ev.get("head")))
    return heads


# --- writing --------------------------------------------------------------------

def _id_number(record: object) -> int:
    text = str(record or "")
    return int(text[3:]) if text.startswith("GC-") and text[3:].isdigit() else -1


def _next_id(rows: list[dict]) -> str:
    nums = [int(r["id"][3:]) for r in rows
            if isinstance(r.get("id"), str) and r["id"].startswith("GC-") and r["id"][3:].isdigit()]
    return f"GC-{max(nums, default=0) + 1:04d}"


def append(root: Path, row: dict) -> dict:
    rows, _problems = read_changes(root)
    row = {"id": _next_id(rows), "ts": _now(), **row}
    path = root / CHANGES
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")
    return row


def _core(root: Path) -> set[str]:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import gate_runner  # noqa: PLC0415 — the one owner of which gates are core

    return {name for name, (key, _cmd) in gate_runner.GATES.items() if key is None}


def sentinel(root: Path, *, dry_run: bool = False) -> list[dict]:
    """Restore what the evidence says must block again. Returns the restores
    (written unless `dry_run`)."""
    state, _problems = effective(root, _core(root))
    restores: list[dict] = []
    weak = {g: st for g, st in state.items() if st["mode"] in WEAK}
    for gate, st in sorted(weak.items()):
        if st["mode"] in ("shadow", "sampled") and not st.get("observe"):
            try:
                heads = _weak_failures(root, gate, st["since"])
            except Exception as exc:  # noqa: BLE001 — the sentinel restores when it cannot see
                heads = [f"(its runs are unreadable: {exc})"]
            if heads:
                restores.append({"gate": gate, "action": "restore", "lock": True, "by": "sentinel",
                                 "of": st["record"],
                                 "reason": f"a {st['mode']} run failed on {heads[-1][:12]} — "
                                           f"blocking again until triaged"})
    limits, _gproblems = guardrails(root)
    known = {g["name"] for g in limits}
    for g in limits:
        value = METRICS[g["metric"]](root, g["window_days"])
        if value is None:
            print(f"gate-modes: guardrail {g['name']}: {g['metric']} unknown (no integration branch "
                  f"readable) — nothing restored on it", file=sys.stderr)
            continue
        if value <= g["max"]:
            continue
        # newest first by record number: containment, not attribution. A weakening that
        # names no known guardrail touches them all — a typo must not opt out
        touched = sorted(((_id_number(st["record"]), gate) for gate, st in weak.items()
                          if not set(st["guardrails"]) & known or g["name"] in st["guardrails"]),
                         reverse=True)
        for _record, gate in touched:
            if any(r["gate"] == gate for r in restores):
                continue
            restores.append({"gate": gate, "action": "restore", "lock": True, "by": "sentinel",
                             "of": weak[gate]["record"],
                             "reason": f"guardrail {g['name']}: {g['metric']} {value} > {g['max']} "
                                       f"in {g['window_days']} d"})
    if not dry_run:
        restores = [append(root, r) for r in restores]
    return restores


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="gate modes: the check graph's lifecycle")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    w = sub.add_parser("weaken")
    w.add_argument("gate")
    w.add_argument("--to", choices=WEAK, required=True)
    w.add_argument("--rate", type=float)
    w.add_argument("--decision", required=True)
    w.add_argument("--guardrail", action="append", default=[])
    w.add_argument("--observe", action="store_true",
                   help="a new gate that never blocked: the sentinel lets its failures stand")
    r = sub.add_parser("restore")
    r.add_argument("gate")
    r.add_argument("--reason", required=True)
    r.add_argument("--lock", action="store_true")
    u = sub.add_parser("unlock")
    u.add_argument("gate")
    u.add_argument("--triage", required=True)
    s = sub.add_parser("sentinel")
    s.add_argument("--dry-run", action="store_true")
    sub.add_parser("check")
    args = p.parse_args(argv)
    root = Path.cwd()

    if args.cmd == "weaken":
        proposal = {"gate": args.gate, "action": "weaken", "to": args.to, "rate": args.rate,
                    "decision": args.decision, "ts": _now(), "guardrails": args.guardrail,
                    "_line": 0}  # line 0: not yet written
        _state, problems = fold(read_changes(root)[0] + [proposal], _core(root),
                                protected_gates(root, base_ref(root)))
        mine = [pr for pr in problems if pr.startswith(f"{CHANGES}:0:")]
        if mine:
            print(f"gate-modes: refused — {mine[0].split(': ', 2)[2]}", file=sys.stderr)
            return 1
        unknown = sorted(set(args.guardrail) - {g["name"] for g in guardrails(root)[0]})
        if unknown:
            print(f"gate-modes: refused — no guardrail named {', '.join(unknown)} in the mandate",
                  file=sys.stderr)
            return 1
        row = append(root, {"gate": args.gate, "action": "weaken", "to": args.to,
                            **({"rate": args.rate} if args.to == "sampled" else {}),
                            "decision": args.decision, "guardrails": args.guardrail,
                            **({"observe": True} if args.observe else {})})
        if args.observe and args.to != "shadow":
            print("gate-modes: note: --observe only applies to --to shadow — ignored", file=sys.stderr)
        print(f"gate-modes: {row['id']} {args.gate} -> {args.to}"
              + (f" ({args.rate:.0%} of commits)" if args.to == "sampled" else "")
              + f" — commit {CHANGES}; `sentinel` restores it on a failure or a breached guardrail")
        return 0
    if args.cmd == "restore":
        row = append(root, {"gate": args.gate, "action": "restore", "reason": args.reason,
                            "lock": args.lock, "by": "manual"})
        print(f"gate-modes: {row['id']} {args.gate} -> block" + (" (locked until unlock)" if args.lock else ""))
        return 0
    if args.cmd == "unlock":
        row = append(root, {"gate": args.gate, "action": "unlock", "triage": args.triage})
        print(f"gate-modes: {row['id']} {args.gate} unlocked")
        return 0
    if args.cmd == "sentinel":
        done = sentinel(root, dry_run=args.dry_run)
        for r in done:
            print(f"gate-modes: {'would restore' if args.dry_run else 'restored'} {r['gate']} — {r['reason']}")
        if not done:
            print("gate-modes: sentinel — nothing to restore")
        return 0
    state, problems = effective(root, _core(root))
    for pr in problems:
        print(f"gate-modes: {pr}")
    if args.cmd == "check":
        return 1 if problems else 0
    if not state:
        print("gate-modes: every gate blocks (no change recorded)")
    for gate, st in sorted(state.items()):
        extra = (f" {st['rate']:.0%}" if st["rate"] else "") + (" locked" if st["locked"] else "")
        print(f"  {gate:<20} {st['mode']}{extra} since {st['since'] or '—'} ({st['record'] or '—'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
