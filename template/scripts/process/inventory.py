#!/usr/bin/env python3
"""Generated inventories — lists of what exists (environment variables, jobs,
file formats), written from the code by the project's own extractors and
checked for drift (`docs/process/inventories.md`). They are anchors for
existing knowledge: a plan that touches a file finds the rows that live there.

  inventory.py update [NAME ...]   run the extractors, write docs/inventory/<name>.md
  inventory.py check [NAME ...]    the same without writing; any difference is an error
  inventory.py list                the configured inventories with their row counts
  inventory.py for-paths PATH ...  the rows whose source lies at or under a path
  inventory.py for-plan PLAN       the same for the paths a plan names in backticks

Configuration: `docs/process/inventories.local.json` (`inventory_config.py`).

Extractor contract: the command runs in the repository root and prints one
JSON object per line — `id` (a non-empty string, unique), `source` (`path` or
`path:line`, relative to the repository) and any further fields with string,
number, boolean or null values. `note` is reserved for the notes sidecar.
Anything else is an error, never half a result.

The committed list stores `source` without the line: a line number would turn
the check red on every edit above it. `for-plan` and `for-paths` take the line
from a live run.
"""
from __future__ import annotations

import argparse
import contextlib
import difflib
import json
import math
import os
import re
import shlex
import signal
import subprocess
import sys
import threading
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling import
import inventory_config  # noqa: E402

OUT_DIR = "docs/inventory"
MAX_OUTPUT = 5 * 1024 * 1024
_STDERR_KEEP = 64 * 1024
_STDERR_SHOW = 2000
_LINE = re.compile(r"^(.*):(\d+)$")
_SCALAR = (str, int, float, bool, type(None))


class InventoryError(Exception):
    """An extractor broke its contract, or a committed list cannot be read."""


def refresh(name: str) -> str:
    return f"uv run scripts/process/inventory.py update {name}"


def md_path(root: Path, name: str) -> Path:
    return root / OUT_DIR / f"{name}.md"


def notes_path(root: Path, name: str) -> Path:
    return root / OUT_DIR / f"{name}.notes.json"


# ---------------------------------------------------------------- extractor


def _drain(stream, keep: bytearray) -> None:
    for chunk in iter(lambda: stream.read(8192), b""):
        keep.extend(chunk)
        if len(keep) > _STDERR_KEEP:
            del keep[:len(keep) - _STDERR_KEEP]


def _stderr_tail(raw: bytes) -> str:
    text = raw.decode("utf-8", "replace").strip()
    if not text:
        return ""
    if len(text) > _STDERR_SHOW:
        text = "…" + text[-_STDERR_SHOW:]
    return "\n  stderr: " + text.replace("\n", "\n  | ")


def run_extractor(root: Path, spec: dict) -> tuple[bytes, bytes]:
    """The extractor's stdout and (the end of) its stderr. Raises InventoryError on a nonzero exit, a
    timeout (the whole process group is killed: `uv run` starts a grandchild
    that would otherwise keep running and hold the pipe) or too much output."""
    argv, timeout = spec["command"], spec["timeout"]
    try:
        proc = subprocess.Popen(argv, cwd=root, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, start_new_session=True)
    except OSError as exc:
        raise InventoryError(f"`{shlex.join(argv)}` cannot start: {exc}") from exc
    assert proc.stdout is not None and proc.stderr is not None
    err = bytearray()
    reader = threading.Thread(target=_drain, args=(proc.stderr, err), daemon=True)
    reader.start()
    why: list[str] = []

    def _kill(reason: str) -> None:
        if not why:
            why.append(reason)
        with contextlib.suppress(OSError):
            if hasattr(os, "killpg"):
                os.killpg(proc.pid, signal.SIGKILL)
            else:
                proc.kill()

    timer = threading.Timer(timeout, _kill, args=(f"did not finish in {timeout:g} s — killed",))
    timer.start()
    out = bytearray()
    try:
        for chunk in iter(lambda: proc.stdout.read(65536), b""):
            out.extend(chunk)
            if len(out) > MAX_OUTPUT:
                _kill(f"printed more than {MAX_OUTPUT // (1024 * 1024)} MB — killed")
                break
        rc = proc.wait()
    finally:
        timer.cancel()
        proc.stdout.close()
    reader.join(timeout=5)
    proc.stderr.close()
    if why:
        raise InventoryError(f"`{shlex.join(argv)}` {why[0]}{_stderr_tail(bytes(err))}")
    if rc != 0:
        raise InventoryError(f"`{shlex.join(argv)}` exited {rc}{_stderr_tail(bytes(err))}")
    return bytes(out), bytes(err)


def _source(value, where: str) -> tuple[str, int | None]:
    if not (isinstance(value, str) and value.strip()):
        raise InventoryError(f"{where}: `source` must be a non-empty path")
    m = _LINE.match(value)
    path, line = (m.group(1), int(m.group(2))) if m else (value, None)
    path = path[2:] if path.startswith("./") else path
    if not path or Path(path).is_absolute() or path.startswith("/") or ".." in Path(path).parts:
        raise InventoryError(f"{where}: `source` {value!r} must be a path inside the repository")
    return path, line


def parse_output(raw: bytes, *, allow_empty: bool) -> list[dict]:
    """The extractor's rows: {"id", "source" (no line), "line", "fields"}.
    Raises InventoryError for anything outside the contract."""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InventoryError(f"output is not UTF-8 (byte {exc.start})") from exc
    rows: list[dict] = []
    seen: set[str] = set()
    for n, line in enumerate(text.split("\n"), 1):
        if not line.strip():
            continue
        where = f"output line {n}"
        try:
            obj = json.loads(line)
        except ValueError as exc:
            raise InventoryError(f"{where} is no JSON: {exc}") from exc
        if not isinstance(obj, dict):
            raise InventoryError(f"{where} is no JSON object")
        if "note" in obj:
            raise InventoryError(f"{where}: `note` is reserved for {OUT_DIR}/<name>.notes.json")
        ident = obj.get("id")
        if not (isinstance(ident, str) and ident):
            raise InventoryError(f"{where}: `id` must be a non-empty string")
        if ident in seen:
            raise InventoryError(f"{where}: duplicate id {ident!r}")
        seen.add(ident)
        if "source" not in obj:
            raise InventoryError(f"{where}: no `source`")
        path, lineno = _source(obj["source"], where)
        fields = {}
        for key, value in obj.items():
            if key in ("id", "source"):
                continue
            if not key:
                raise InventoryError(f"{where}: an empty field name")
            if not isinstance(value, _SCALAR):
                raise InventoryError(f"{where}: field {key!r} is nested — only strings, numbers, "
                                     "booleans and null")
            if isinstance(value, float) and not math.isfinite(value):
                raise InventoryError(f"{where}: field {key!r} is no finite number")
            fields[key] = value
        rows.append({"id": ident, "source": path, "line": lineno, "fields": fields})
    if not rows and not allow_empty:
        raise InventoryError("printed no rows (set `allow_empty` if an empty list is right)")
    return rows


def extract(root: Path, spec: dict) -> list[dict]:
    raw, err = run_extractor(root, spec)
    try:
        return parse_output(raw, allow_empty=spec["allow_empty"])
    except InventoryError as exc:
        raise InventoryError(f"`{shlex.join(spec['command'])}`: {exc}{_stderr_tail(err)}") from exc


# ---------------------------------------------------------------- notes


def load_notes(root: Path, name: str) -> dict[str, str]:
    path = notes_path(root, name)
    if not path.exists():
        return {}
    rel = path.relative_to(root).as_posix()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise InventoryError(f"{rel}: {exc}") from exc
    if not (isinstance(data, dict) and all(isinstance(v, str) for v in data.values())):
        raise InventoryError(f"{rel} must be an object of id → note text")
    return data


# ---------------------------------------------------------------- render / parse


def escape(text: str) -> str:
    return (text.replace("\\", "\\\\").replace("|", "\\|")
            .replace("\n", "\\n").replace("\r", "\\r"))


_UNESCAPE = {"\\": "\\", "|": "|", "n": "\n", "r": "\r"}


def _cells(line: str) -> list[str]:
    """The unescaped cells of one table line `| a | b |`."""
    cells, cur, i = [], [], 0
    while i < len(line):
        ch = line[i]
        if ch == "\\":
            nxt = line[i + 1] if i + 1 < len(line) else ""
            if nxt not in _UNESCAPE:
                raise InventoryError(f"unknown escape `\\{nxt}` in {line!r}")
            cur.append(_UNESCAPE[nxt])
            i += 2
            continue
        if ch == "|":
            cells.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
        i += 1
    cells.append("".join(cur))
    if len(cells) < 3 or cells[0] or cells[-1]:
        raise InventoryError(f"no table row: {line!r}")
    out = []
    for cell in cells[1:-1]:
        if len(cell) < 2 or cell[0] != " " or cell[-1] != " ":
            raise InventoryError(f"malformed cell {cell!r} in {line!r}")
        out.append(cell[1:-1])
    return out


def _cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return json.dumps(value)
    return value


def columns(rows: list[dict]) -> list[str]:
    fields = sorted({key for row in rows for key in row["fields"]})
    return ["id", *fields, "source", "note"]


def table(rows: list[dict], notes: dict[str, str]) -> tuple[list[str], list[dict[str, str]]]:
    """The columns and the cell text of each row, sorted by id."""
    cols = columns(rows)
    out = []
    for row in sorted(rows, key=lambda r: r["id"]):
        cells = {"id": row["id"], "source": row["source"], "note": notes.get(row["id"], "")}
        for col in cols[1:-2]:
            cells[col] = _cell(row["fields"].get(col))
        out.append({col: cells[col] for col in cols})
    return cols, out


def render(name: str, spec: dict, rows: list[dict], notes: dict[str, str]) -> str:
    cols, cells = table(rows, notes)
    lines = [
        f"# Inventory: {name}",
        "",
        f"Generated by `scripts/process/inventory.py update {name}` — do not edit by hand.",
        f"Command: `{shlex.join(spec['command'])}`. "
        f"Notes: `{OUT_DIR}/{name}.notes.json`.",
        "",
        "| " + " | ".join(escape(c) for c in cols) + " |",
        "|" + "|".join(" --- " for _ in cols) + "|",
    ]
    lines += ["| " + " | ".join(escape(row[c]) for c in cols) + " |" for row in cells]
    return "\n".join(lines) + "\n"


def parse_table(text: str) -> tuple[list[str], list[dict[str, str]]]:
    """Read a rendered list back: its columns and the cell text of each row."""
    lines = [ln for ln in text.split("\n") if ln.startswith("|")]
    if len(lines) < 2:
        raise InventoryError("no table")
    cols = _cells(lines[0])
    rows = []
    for line in lines[2:]:
        cells = _cells(line)
        if len(cells) != len(cols):
            raise InventoryError(f"row has {len(cells)} cells, header {len(cols)}: {line!r}")
        rows.append(dict(zip(cols, cells, strict=True)))
    return cols, rows


def committed(root: Path, name: str) -> list[dict[str, str]] | None:
    path = md_path(root, name)
    if not path.is_file():
        return None
    try:
        cols, rows = parse_table(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        raise InventoryError(f"{OUT_DIR}/{name}.md: {exc}") from exc
    except InventoryError as exc:
        raise InventoryError(f"{OUT_DIR}/{name}.md: {exc}") from exc
    if not {"id", "source", "note"} <= set(cols):
        raise InventoryError(f"{OUT_DIR}/{name}.md: the table lacks id, source or note")
    return rows


# ---------------------------------------------------------------- commands


def _select(conf: dict, names: list[str]) -> dict:
    unknown = [n for n in names if n not in conf]
    if unknown:
        raise InventoryError(f"not configured: {', '.join(unknown)} "
                             f"(configured: {', '.join(conf) or 'none'})")
    return {n: conf[n] for n in names} if names else conf


def _orphan_notes(rows: list[dict], notes: dict[str, str]) -> list[str]:
    ids = {r["id"] for r in rows}
    return sorted(i for i in notes if i not in ids)


def generate(root: Path, name: str, spec: dict) -> tuple[str, list[str]]:
    """The list's text and its orphaned note ids."""
    try:
        rows = extract(root, spec)
        notes = load_notes(root, name)
    except InventoryError as exc:
        raise InventoryError(f"{name}: {exc}") from exc
    return render(name, spec, rows, notes), _orphan_notes(rows, notes)


def update(root: Path, conf: dict, names: list[str] | None = None) -> tuple[list[str], list[str]]:
    """Write the lists; (errors, messages). A failing extractor leaves its file as it was."""
    errors, said = [], []
    for name, spec in _select(conf, names or []).items():
        try:
            text, orphans = generate(root, name, spec)
        except InventoryError as exc:
            errors.append(str(exc))
            continue
        path = md_path(root, name)
        old = path.read_bytes() if path.is_file() else None
        if old == text.encode("utf-8"):
            said.append(f"{name}: unchanged")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(text.encode("utf-8"))
            said.append(f"{name}: wrote {OUT_DIR}/{name}.md")
        if orphans:
            said.append(f"{name}: orphaned note(s) for {', '.join(orphans)} — rows gone; delete them "
                        f"from {OUT_DIR}/{name}.notes.json when they are no longer wanted")
    return errors, said


def _unconfigured(root: Path, conf: dict) -> list[str]:
    folder = root / OUT_DIR
    if not folder.is_dir():
        return []
    out = []
    for path in sorted(folder.iterdir()):
        if not path.is_file():
            continue
        for suffix in (".notes.json", ".md"):
            if path.name.endswith(suffix):
                if path.name[:-len(suffix)] not in conf:
                    out.append(f"{OUT_DIR}/{path.name} belongs to no configured inventory — add it "
                               f"to {inventory_config.CONFIG} or delete the file")
                break
    return out


def _diff(old: str, new: str) -> str:
    lines = list(difflib.unified_diff(old.splitlines(), new.splitlines(), "committed", "generated",
                                      lineterm="", n=0))
    shown = lines[2:22]
    more = len(lines) - 2 - len(shown)
    return "\n    " + "\n    ".join(shown) + (f"\n    … {more} more" if more > 0 else "")


def check(root: Path, conf: dict, names: list[str] | None = None) -> tuple[list[str], list[str]]:
    """(errors, notes): every list regenerated and compared byte for byte."""
    errors, said = [], []
    selected = _select(conf, names or [])
    for name, spec in selected.items():
        path = md_path(root, name)
        if not path.is_file():
            errors.append(f"{name}: {OUT_DIR}/{name}.md is missing — run `{refresh(name)}`")
            continue
        try:
            text, orphans = generate(root, name, spec)
        except InventoryError as exc:
            errors.append(f"{exc}\n  fix the extractor, then run `{refresh(name)}`")
            continue
        old = path.read_bytes()
        if old != text.encode("utf-8"):
            errors.append(f"{name}: {OUT_DIR}/{name}.md differs from the code — run "
                          f"`{refresh(name)}`{_diff(old.decode('utf-8', 'replace'), text)}")
        if orphans:
            said.append(f"{name}: orphaned note(s) for {', '.join(orphans)}")
    if not names:
        errors += _unconfigured(root, conf)
    return errors, said


def _norm(path: str) -> str:
    path = path.replace("\\", "/")
    path = path[2:] if path.startswith("./") else path
    return path.rstrip("/")


def _under(source: str, paths: list[str]) -> bool:
    return any(p in ("", ".") or source == p or source.startswith(p + "/") for p in paths)


def rows_for(root: Path, conf: dict, paths: list[str]) -> tuple[list[str], list[str]]:
    """(output lines, reasons): `<inventory>  <id>  <path:line>  <note>` for every
    row at or under one of `paths`. Lines come from a live run; where it fails,
    the committed list stands in, without lines, and the reason is said."""
    wanted = [_norm(p) for p in paths]
    out, reasons = [], []
    for name, spec in conf.items():
        try:
            notes = load_notes(root, name)
        except InventoryError as exc:
            reasons.append(f"{name}: notes unreadable — {exc}")
            notes = {}
        try:
            live = extract(root, spec)
        except InventoryError as exc:
            try:
                rows = committed(root, name)
            except InventoryError as bad:
                rows, exc = None, f"{exc}; {bad}"
            if rows is None:
                reasons.append(f"{name}: extractor failed and no readable {OUT_DIR}/{name}.md — {exc}")
                continue
            hits = [r for r in rows if _under(r["source"], wanted)]
            if hits:
                reasons.append(f"{name}: no line numbers, the extractor failed — {exc}")
            for r in sorted(hits, key=lambda r: r["id"]):
                out.append(_line(name, r["id"], r["source"], r["note"]))
            continue
        for r in sorted(live, key=lambda r: r["id"]):
            if _under(r["source"], wanted):
                where = r["source"] if r["line"] is None else f"{r['source']}:{r['line']}"
                out.append(_line(name, r["id"], where, notes.get(r["id"], "")))
    return out, reasons


def _line(name: str, ident: str, where: str, note: str) -> str:
    return "  ".join([name, escape(ident), escape(where), escape(note)]).rstrip()


def repo_root() -> Path:
    try:
        proc = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True,
                              timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise InventoryError(f"git cannot name the repository: {exc}") from exc
    if proc.returncode != 0 or not proc.stdout.strip():
        raise InventoryError("not inside a git repository")
    return Path(proc.stdout.strip()).resolve()


def _from_cwd(root: Path, path: str) -> str:
    """A path given on the command line, relative to the repository root."""
    try:
        return (Path.cwd() / path).resolve().relative_to(root).as_posix()
    except ValueError:
        return path


def _plan_paths(plan: str) -> list[str]:
    import plan_drift  # noqa: PLC0415 — the one reader of a plan's named paths

    path = Path(plan)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise InventoryError(f"{plan}: {exc}") from exc
    return plan_drift.named_paths(text)


def _print_many(lines: list[str], stream=None) -> None:
    for line in lines:
        print(line, file=stream or sys.stdout)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Generated inventories: update, check and look up.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for cmd in ("update", "check"):
        sub.add_parser(cmd).add_argument("names", nargs="*", metavar="NAME")
    sub.add_parser("list")
    sub.add_parser("for-paths").add_argument("paths", nargs="+", metavar="PATH")
    sub.add_parser("for-plan").add_argument("plan", metavar="PLAN")
    a = ap.parse_args(argv)
    try:
        root = repo_root()
        conf = inventory_config.load(root)
    except (InventoryError, inventory_config.ConfigError) as exc:
        print(f"inventory: {exc}", file=sys.stderr)
        return 1
    if conf is None:
        print(f"inventory: nothing configured ({inventory_config.CONFIG} is absent)")
        return 0
    try:
        if a.cmd in ("update", "check"):
            errors, said = (update if a.cmd == "update" else check)(root, conf, a.names)
            _print_many([f"inventory: {s}" for s in said])
            if errors:
                _print_many([f"inventory: FAILED: {e}" for e in errors], sys.stderr)
                return 1
            if a.cmd == "check":
                print("inventory: OK")
            return 0
        if a.cmd == "list":
            for name in conf:
                rows = committed(root, name)
                print(f"{name}  {'not generated' if rows is None else f'{len(rows)} rows'}")
            return 0
        paths = _plan_paths(a.plan) if a.cmd == "for-plan" else [_from_cwd(root, p) for p in a.paths]
        lines, reasons = rows_for(root, conf, paths)
        _print_many([f"inventory: {r}" for r in reasons], sys.stderr)
        if lines:
            _print_many(lines)
        else:
            print(f"inventory: no row at or under the {len(paths)} path(s)")
        return 0
    except InventoryError as exc:
        print(f"inventory: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
