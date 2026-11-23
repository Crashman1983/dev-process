#!/usr/bin/env python3
"""flow — Bausteine für einen dynamischen Ablauf über mehrere Arbeiter.

Der steuernde Agent schreibt ein kurzes Python-Skript gegen diese Bausteine
und führt es aus. Ein Arbeiter ist ein Aufruf eines Harness ohne Dialog
(Claude, Codex, …); welcher Befehl hinter einer Rolle steht, sagt
``workers.json``. Die Bausteine kennen kein Harness.

    sheet = load_sheet("…/epic-3061.md")
    flow = Flow(repo=".", run_dir=".process-work/flow/3061-s1", workers="workers.json")
    results = flow.pipeline(issues, build, check)      # je Issue eine Kette
    merged = flow.integrate(slice_worktree, branches)  # lokal, nie nach main

Was die Bausteine erzwingen (und ein Skript nicht abschalten soll):

* Obergrenzen für Arbeiter gleichzeitig, Arbeiter je Lauf und Zeit je Arbeiter.
* Jeder schreibende Arbeiter bekommt einen eigenen Worktree auf eigenem Zweig.
* Es gibt keinen Baustein, der pusht. ``integrate`` verweigert ``main``/``master``.
* Ein Ergebnis zählt nur als JSON-Datei mit den verlangten Schlüsseln.
* Jeder Aufruf steht im Protokoll (``journal.jsonl``); ein zweiter Lauf mit
  demselben Skript nimmt fertige Ergebnisse von dort und fährt nur den Rest.

Nur Standardbibliothek. Die Grenze, die wirklich hält, bleibt das Gate am
Gang nach main — diese Datei kann ein Agent ändern.
"""

from __future__ import annotations

import concurrent.futures as cf
import fnmatch
import hashlib
import json
import os
import re
import signal
import subprocess
import threading
import time
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import Any

PROTECTED = {"main", "master"}
PROTOCOL = """

--- Ergebnisprotokoll (bindend) ---
Schreibe dein Ergebnis als ein JSON-Objekt in die Datei {result_file}.
Pflichtschlüssel: {required}. Ohne diese Datei gilt dein Lauf als gescheitert.
Du arbeitest nur in deinem Arbeitsverzeichnis. Du pushst nicht, du mergst nicht,
du fasst main nicht an und du startest keine weiteren Agenten.
"""


class FlowError(RuntimeError):
    """Ein Baustein verweigert: falsche Eingabe oder eine Leitplanke greift."""


def _git(cwd: Path | str, *args: str, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _static_prefix(pattern: str) -> str:
    return re.split(r"[*?\[]", pattern, maxsplit=1)[0]


def patterns_overlap(a: str, b: str) -> bool:
    """Grobe Prüfung: zwei Muster überlappen, wenn ein fester Anfang den anderen enthält."""
    pa, pb = _static_prefix(a), _static_prefix(b)
    return pa.startswith(pb) or pb.startswith(pa)


def matches(path: str, patterns: Iterable[str]) -> bool:
    """``*`` überschreitet Verzeichnisgrenzen (fnmatch), ``dir/*`` meint also den ganzen Baum."""
    return any(fnmatch.fnmatch(path, p) for p in patterns)


def load_sheet(path: str | Path) -> dict[str, Any]:
    """Liest das Epic-Blatt (Markdown mit einem ``json``-Block) und prüft es.

    Alle Mängel kommen in einer Meldung, damit das Blatt in einem Zug repariert wird.
    """
    text = Path(path).read_text(encoding="utf-8")
    sheet = None
    for block in re.findall(r"```json\n(.*?)\n```", text, flags=re.DOTALL):
        try:
            data = json.loads(block)
        except json.JSONDecodeError as exc:
            raise FlowError(f"{path}: json-Block nicht lesbar: {exc}") from exc
        if isinstance(data, dict) and "epic" in data:
            sheet = data
            break
    if sheet is None:
        raise FlowError(f'{path}: kein json-Block mit dem Schlüssel "epic" gefunden')

    problems: list[str] = []
    ref = sheet.get("reference") or {}
    if not ref.get("build"):
        problems.append("reference.build fehlt: gegen welchen Stand wird gebaut und verglichen?")
    if not ref.get("check"):
        problems.append("reference.check fehlt: wie prüft ein Arbeiter, dass er die Referenz hat?")
    if not sheet.get("integration_owner"):
        problems.append("integration_owner fehlt")
    for item in sheet.get("cross_cutting") or []:
        if not item.get("behavior") or not item.get("owner"):
            problems.append(f"cross_cutting ohne behavior oder owner: {item}")
    shared = list(sheet.get("shared_paths") or [])
    if not sheet.get("slices"):
        problems.append("slices fehlt oder ist leer")
    for sl in sheet.get("slices") or []:
        sid = sl.get("id", "?")
        if not sl.get("base"):
            problems.append(f"Scheibe {sid}: base fehlt")
        issues = sl.get("issues") or []
        if not issues:
            problems.append(f"Scheibe {sid}: keine Issues")
        for n, issue in enumerate(issues):
            num = issue.get("issue", "?")
            owns = issue.get("owns") or []
            if not owns:
                problems.append(f"#{num}: owns fehlt — ohne eigene Dateien kein paralleler Bau")
            if issue.get("tier", 2) >= 3:
                problems.append(f"#{num}: Tier 3 gehört unter regular, nicht in eine Scheibe")
            for pat in owns:
                for sp in shared:
                    if patterns_overlap(pat, sp):
                        problems.append(f"#{num}: {pat} überlappt die gemeinsame Datei {sp}")
                for other in issues[n + 1 :]:
                    for op in other.get("owns") or []:
                        if patterns_overlap(pat, op):
                            problems.append(
                                f"#{num}: {pat} überlappt {op} von #{other.get('issue', '?')}"
                            )
    if problems:
        raise FlowError(f"{path}: Epic-Blatt unvollständig:\n- " + "\n- ".join(problems))
    return sheet


class Flow:
    """Ein Lauf: Arbeiter starten, Ergebnisse einsammeln, Protokoll führen."""

    def __init__(
        self,
        repo: str | Path,
        run_dir: str | Path,
        workers: str | Path | dict[str, list[str]],
        *,
        max_parallel: int = 4,
        max_agents: int = 40,
        timeout_s: int = 1800,
    ) -> None:
        self.repo = Path(repo).resolve()
        self.run_dir = Path(run_dir).resolve()
        (self.run_dir / "results").mkdir(parents=True, exist_ok=True)
        (self.run_dir / "logs").mkdir(exist_ok=True)
        if isinstance(workers, dict):
            self.workers = workers
        else:
            self.workers = json.loads(Path(workers).read_text(encoding="utf-8"))
        self.max_agents = max_agents
        self.timeout_s = timeout_s
        self._slots = threading.Semaphore(max_parallel)
        self._pool_size = max(max_parallel * 4, 8)
        self._lock = threading.Lock()
        self._started = 0
        self._journal = self.run_dir / "journal.jsonl"
        self._done: dict[str, dict[str, Any]] = {}
        if self._journal.exists():
            for line in self._journal.read_text(encoding="utf-8").splitlines():
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if entry.get("type") == "agent" and entry.get("ok"):
                    self._done[entry["key"]] = entry["result"]

    # -- Protokoll -----------------------------------------------------------------

    def _write(self, entry: dict[str, Any]) -> None:
        entry["at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        with self._lock, self._journal.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def log(self, message: str) -> None:
        print(f"[flow] {message}", flush=True)
        self._write({"type": "log", "message": message})

    # -- Arbeiter ------------------------------------------------------------------

    def agent(
        self,
        prompt: str,
        *,
        label: str,
        role: str = "build",
        cwd: str | Path | None = None,
        required: Sequence[str] = ("summary",),
    ) -> dict[str, Any] | None:
        """Startet einen Arbeiter und gibt sein JSON-Ergebnis zurück, sonst ``None``.

        ``None`` heißt: Zeit überschritten, kein Ergebnis oder Pflichtschlüssel fehlen.
        Gescheiterte Aufrufe werden beim nächsten Lauf wiederholt, fertige nicht.
        """
        if role not in self.workers:
            raise FlowError(f"Rolle {role!r} steht nicht in workers.json ({sorted(self.workers)})")
        if not re.fullmatch(r"[A-Za-z0-9._-]+", label):
            raise FlowError(f"label {label!r}: nur Buchstaben, Ziffern, Punkt, Strich, Unterstrich")
        key = hashlib.sha256(f"{label}\0{role}\0{prompt}".encode()).hexdigest()[:16]
        if key in self._done:
            self.log(f"{label}: aus dem Protokoll übernommen")
            return self._done[key]
        with self._lock:
            if self._started >= self.max_agents:
                raise FlowError(
                    f"Obergrenze erreicht: {self.max_agents} Arbeiter in diesem Lauf. "
                    "Wer mehr braucht, entscheidet das bewusst über max_agents."
                )
            self._started += 1
        result_file = self.run_dir / "results" / f"{label}.json"
        result_file.unlink(missing_ok=True)
        full = prompt + PROTOCOL.format(result_file=result_file, required=", ".join(required))
        fill = {"{prompt}": full, "{result_file}": str(result_file), "{label}": label}
        argv = []
        for part in self.workers[role]:
            for placeholder, value in fill.items():
                part = part.replace(placeholder, value)
            argv.append(part)
        started = time.monotonic()
        error = None
        rc: int | None = None
        with self._slots, (self.run_dir / "logs" / f"{label}.log").open("w") as log:
            try:
                proc = subprocess.Popen(
                    argv,
                    cwd=str(cwd or self.repo),
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,
                    start_new_session=True,
                )
            except OSError as exc:
                proc = None
                error = f"Start gescheitert: {exc}"
            if proc is not None:
                try:
                    rc = proc.wait(timeout=self.timeout_s)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait()
                    error = f"Zeitgrenze {self.timeout_s}s überschritten"
        result: dict[str, Any] | None = None
        if error is None:
            try:
                data = json.loads(result_file.read_text(encoding="utf-8"))
            except FileNotFoundError:
                error = f"keine Ergebnisdatei (rc={rc})"
            except json.JSONDecodeError as exc:
                error = f"Ergebnisdatei kein JSON: {exc}"
            else:
                missing = [k for k in required if not isinstance(data, dict) or k not in data]
                if missing:
                    error = f"Pflichtschlüssel fehlen: {missing}"
                else:
                    result = data
        seconds = round(time.monotonic() - started, 1)
        self._write(
            {
                "type": "agent",
                "key": key,
                "label": label,
                "role": role,
                "ok": result is not None,
                "error": error,
                "seconds": seconds,
                "result": result,
            }
        )
        if result is None:
            self.log(f"{label}: gescheitert — {error}")
        else:
            self._done[key] = result
            self.log(f"{label}: fertig nach {seconds}s")
        return result

    # -- Ablauf --------------------------------------------------------------------

    def parallel(self, thunks: Sequence[Callable[[], Any]]) -> list[Any]:
        """Alle zugleich, wartet auf alle. Ein gescheiterter Eintrag wird ``None``."""

        def safe(thunk: Callable[[], Any]) -> Any:
            try:
                return thunk()
            except FlowError:
                raise
            except Exception as exc:  # noqa: BLE001 - ein Eintrag darf den Lauf nicht kippen
                self.log(f"parallel: Eintrag gescheitert — {exc!r}")
                return None

        with cf.ThreadPoolExecutor(max_workers=self._pool_size) as pool:
            return list(pool.map(safe, thunks))

    def pipeline(self, items: Sequence[Any], *stages: Callable[[Any, Any, int], Any]) -> list[Any]:
        """Jedes Element durchläuft alle Stufen für sich; keines wartet auf die anderen.

        Jede Stufe bekommt ``(vorheriges_ergebnis, element, index)``. Liefert eine
        Stufe ``None`` oder wirft sie, endet die Kette dieses Elements mit ``None``.
        """

        def chain(index: int) -> Any:
            value: Any = items[index]
            for stage in stages:
                value = stage(value, items[index], index)
                if value is None:
                    return None
            return value

        return self.parallel([lambda i=i: chain(i) for i in range(len(items))])

    # -- Git -----------------------------------------------------------------------

    def worktree(self, label: str, base: str) -> tuple[Path, str]:
        """Eigener Worktree auf eigenem Zweig ab ``base``; ein vorhandener wird weiterbenutzt."""
        path = self.run_dir / "worktrees" / label
        branch = f"flow/{self.run_dir.name}/{label}"
        if path.exists():
            return path, branch
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            done = _git(self.repo, "worktree", "add", "-b", branch, str(path), base)
        if done.returncode != 0:
            raise FlowError(f"Worktree {label}: {done.stderr.strip()}")
        return path, branch

    def changed_paths(self, branch: str, base: str) -> list[str]:
        done = _git(self.repo, "diff", "--name-only", f"{base}...{branch}")
        if done.returncode != 0:
            raise FlowError(f"diff {base}...{branch}: {done.stderr.strip()}")
        return [line for line in done.stdout.splitlines() if line]

    def ownership(
        self, branch: str, base: str, owns: Sequence[str], shared: Sequence[str] = ()
    ) -> dict[str, list[str]]:
        """Welche geänderten Dateien gehören dem Arbeiter nicht?

        ``shared``: gemeinsame Dateien — die ändert nur der Integrationsowner.
        ``foreign``: alles andere außerhalb von ``owns``.
        """
        outside = [p for p in self.changed_paths(branch, base) if not matches(p, owns)]
        return {
            "shared": [p for p in outside if matches(p, shared)],
            "foreign": [p for p in outside if not matches(p, shared)],
        }

    def integrate(self, target: str | Path, branches: Sequence[str]) -> dict[str, Any]:
        """Führt Zweige lokal im Worktree ``target`` zusammen. Nie auf main, nie ein Push.

        Ein Konflikt wird abgebrochen und gemeldet; ihn löst der Integrationsowner.
        """
        head = _git(target, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        if head in PROTECTED or not head:
            raise FlowError(f"integrate verweigert: {target} steht auf {head or 'keinem Zweig'}")
        merged: list[str] = []
        conflicts: dict[str, list[str]] = {}
        for branch in branches:
            done = _git(target, "merge", "--no-ff", "--no-edit", branch, timeout=600)
            if done.returncode == 0:
                merged.append(branch)
                continue
            files = _git(target, "diff", "--name-only", "--diff-filter=U").stdout.split()
            _git(target, "merge", "--abort")
            conflicts[branch] = files or [done.stderr.strip() or done.stdout.strip()]
        self._write({"type": "integrate", "target": head, "merged": merged, "conflicts": conflicts})
        return {"target": head, "merged": merged, "conflicts": conflicts}

    def check(self, argv: Sequence[str], cwd: str | Path, timeout_s: int = 1800) -> dict[str, Any]:
        """Ein Prüfbefehl (ausgewählte Tests, Build) auf dem zusammengeführten Stand."""
        try:
            done = subprocess.run(
                list(argv),
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=timeout_s,
                check=False,
            )
            rc, out = done.returncode, (done.stdout + done.stderr)
        except subprocess.TimeoutExpired:
            rc, out = 124, f"Zeitgrenze {timeout_s}s überschritten"
        except OSError as exc:
            rc, out = 127, str(exc)
        tail = "\n".join(out.splitlines()[-25:])
        self._write({"type": "check", "argv": list(argv), "rc": rc, "tail": tail})
        return {"argv": list(argv), "rc": rc, "tail": tail}
