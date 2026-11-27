#!/usr/bin/env python3
"""flow — Bausteine für einen dynamischen Ablauf über mehrere Arbeiter.

Der steuernde Agent schreibt ein kurzes Python-Skript gegen diese Bausteine
und führt es aus. Ein Arbeiter ist ein Aufruf eines Harness ohne Dialog
(Claude, Codex, …); welcher Befehl hinter einer Rolle steht, sagt
``workers.json``. Die Bausteine kennen kein Harness.

    sheet = load_sheet("…/epic-3061.md")
    flow = Flow(".", default_run_dir(".", "3061-s1"), "workers.json")
    results = flow.pipeline(issues, build, check)      # je Issue eine Kette
    merged = flow.integrate(slice_worktree, branches)  # lokal, nie nach main

Was die Bausteine tun:

* Obergrenzen für Arbeiter gleichzeitig, Arbeiter je Lauf-Ordner (über alle
  Neustarts gezählt) und Zeit je Arbeiter.
* Lauf-Ordner und Worktrees liegen außerhalb des verfolgten Baums.
* Ein Ergebnis zählt nur als JSON-Datei mit den verlangten Schlüsseln und Typen.
* Jeder Aufruf steht im Protokoll (``journal.jsonl``); ein zweiter Lauf nimmt
  fertige Ergebnisse von dort, solange Auftrag und angegebener Stand gleich sind.
* Bricht das Steuerskript ab, werden die laufenden Arbeiter beendet.

Was sie nicht können: einen Arbeiter am Pushen hindern. Arbeiter starten mit
einer Git-Einstellung, die ``git push`` zu den bekannten Remotes ins Leere
laufen lässt, und ``integrate``/``check`` verweigern die naheliegenden Fälle.
Das fängt Versehen. Wer es umgehen will, kann es; die Grenze, die hält, ist
das Gate am Gang nach main.

Nur Standardbibliothek.
"""

from __future__ import annotations

import atexit
import concurrent.futures as cf
import contextlib
import hashlib
import json
import os
import re
import signal
import subprocess
import threading
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

PROTECTED = {"main", "master"}
TYPES = {"str": str, "list": list, "dict": dict, "bool": bool, "int": int}
PROTOCOL = """

--- Ergebnisprotokoll (bindend) ---
Schreibe dein Ergebnis als ein JSON-Objekt in die Datei {result_file}.
Pflichtschlüssel und Typen: {required}. Ohne diese Datei gilt dein Lauf als gescheitert.
Du arbeitest nur in deinem Arbeitsverzeichnis. Du pushst nicht, du mergst nicht,
du fasst main nicht an und du startest keine weiteren Agenten.
"""


class FlowError(RuntimeError):
    """Ein Baustein verweigert: falsche Eingabe oder eine Leitplanke greift."""


def _git(cwd: Path | str, *args: str, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    argv = ["git", "-C", str(cwd), *args]
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(argv, 124, "", f"git {args[0]}: Zeitgrenze {timeout}s")


# -- Muster ------------------------------------------------------------------------


def _static_prefix(pattern: str) -> str:
    return re.split(r"[*?]", pattern, maxsplit=1)[0]


def patterns_overlap(a: str, b: str) -> bool:
    """Vorsichtige Prüfung: überlappt, wenn ein fester Anfang den anderen enthält.

    Meldet lieber zu viel: ``src/a/*.tsx`` und ``src/a/*.css`` gelten als überlappend.
    """
    pa, pb = _static_prefix(a), _static_prefix(b)
    return pa.startswith(pb) or pb.startswith(pa)


def _pattern_re(pattern: str) -> re.Pattern[str]:
    if "*" not in pattern and "?" not in pattern:
        return re.compile(re.escape(pattern.rstrip("/")) + r"(/.*)?")
    body = re.escape(pattern).replace(r"\*", ".*").replace(r"\?", ".")
    return re.compile(body)


def matches(path: str, patterns: Iterable[str]) -> bool:
    """Nur ``*`` und ``?`` sind besonders; ``*`` überschreitet Verzeichnisgrenzen.

    Ein Muster ohne Platzhalter meint die Datei oder den ganzen Ordner dieses
    Namens. Eckige Klammern sind wörtlich (Ordner wie ``[id]`` bleiben treffbar).
    """
    return any(_pattern_re(p).fullmatch(path) for p in patterns)


# -- Epic-Blatt --------------------------------------------------------------------


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
        numbers = [i.get("issue") for i in issues]
        for num in sorted({n for n in numbers if numbers.count(n) > 1}, key=str):
            problems.append(f"Scheibe {sid}: #{num} steht mehrfach drin")
        for n, issue in enumerate(issues):
            num = issue.get("issue", "?")
            owns = issue.get("owns") or []
            tier = issue.get("tier")
            if not owns:
                problems.append(f"#{num}: owns fehlt — ohne eigene Dateien kein paralleler Bau")
            if isinstance(tier, bool) or not isinstance(tier, int):
                problems.append(f"#{num}: tier fehlt oder ist keine Zahl ({tier!r})")
            elif tier >= 3:
                problems.append(f"#{num}: Tier 3 gehört unter regular, nicht in eine Scheibe")
            for pat in owns:
                if not _static_prefix(pat).strip("/"):
                    problems.append(f"#{num}: {pat} beginnt nicht mit einem festen Ordner")
                    continue
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


def default_run_dir(repo: str | Path, slug: str) -> Path:
    """Lauf-Ordner außerhalb des Checkouts: ``$FLOW_ROOT/<slug>``, sonst neben dem Repo."""
    root = os.environ.get("FLOW_ROOT")
    top = Path(_git(repo, "rev-parse", "--show-toplevel").stdout.strip() or repo).resolve()
    return (Path(root) if root else top.parent / f"{top.name}-flow") / slug


def _check_types(data: Any, required: Mapping[str, str]) -> str | None:
    if not isinstance(data, dict):
        return "Ergebnis ist kein JSON-Objekt"
    wrong = []
    for key, kind in required.items():
        if key not in data:
            wrong.append(f"{key} fehlt")
        elif kind != "any" and (
            not isinstance(data[key], TYPES[kind])
            or (kind == "int" and isinstance(data[key], bool))
        ):
            wrong.append(f"{key} ist kein {kind}")
    return "; ".join(wrong) or None


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
        top = _git(repo, "rev-parse", "--show-toplevel").stdout.strip()
        if not top:
            raise FlowError(f"{repo} ist kein Git-Checkout")
        self.repo = Path(top).resolve()
        self.run_dir = Path(run_dir).resolve()
        inside = self.run_dir.is_relative_to(self.repo)
        if inside and _git(self.repo, "check-ignore", "-q", str(self.run_dir)).returncode != 0:
            raise FlowError(
                f"Lauf-Ordner {self.run_dir} liegt im verfolgten Baum. "
                "Nimm default_run_dir() oder einen ignorierten Ordner."
            )
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
        self._active: set[str] = set()
        self._closed = threading.Event()
        self._procs: set[subprocess.Popen[bytes]] = set()
        self._journal = self.run_dir / "journal.jsonl"
        self._done: dict[str, dict[str, Any]] = {}
        self._by_label: dict[str, dict[str, Any]] = {}
        self._started = 0
        if self._journal.exists():
            for line in self._journal.read_text(encoding="utf-8").splitlines():
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if entry.get("type") == "start":
                    self._started += 1
                elif entry.get("type") == "agent" and entry.get("ok"):
                    self._done[entry["key"]] = entry["result"]
                    self._by_label[entry["label"]] = entry["result"]
        self._take_lock()
        self._worker_env = self._no_push_env()
        atexit.register(self.close)
        if threading.current_thread() is threading.main_thread():
            for sig in (signal.SIGINT, signal.SIGTERM):
                signal.signal(sig, self._on_signal)

    # -- Lebenszyklus --------------------------------------------------------------

    def _take_lock(self) -> None:
        lock = self.run_dir / "lock"
        if lock.exists():
            try:
                pid = int(lock.read_text().strip())
                os.kill(pid, 0)
            except (ValueError, ProcessLookupError):
                pass
            except PermissionError:
                raise FlowError(f"{lock}: ein anderer Lauf hält diesen Ordner") from None
            else:
                raise FlowError(f"{lock}: Lauf {pid} arbeitet schon in diesem Ordner")
        lock.write_text(str(os.getpid()))

    def _no_push_env(self) -> dict[str, str]:
        env = dict(os.environ)
        remotes = _git(self.repo, "remote").stdout.split()
        start = int(env.get("GIT_CONFIG_COUNT", "0") or 0)
        for n, remote in enumerate(remotes, start=start):
            env[f"GIT_CONFIG_KEY_{n}"] = f"remote.{remote}.pushurl"
            env[f"GIT_CONFIG_VALUE_{n}"] = "/dev/null/flow-arbeiter-pushen-nicht"
        env["GIT_CONFIG_COUNT"] = str(start + len(remotes))
        return env

    def _on_signal(self, signum: int, _frame: object) -> None:
        self.close()
        raise SystemExit(128 + signum)

    def close(self) -> None:
        """Beendet laufende Arbeiter, startet keine neuen und gibt den Lauf-Ordner frei."""
        self._closed.set()
        with self._lock:
            procs = list(self._procs)
        for proc in procs:
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.killpg(proc.pid, signal.SIGKILL)
        lock = self.run_dir / "lock"
        with contextlib.suppress(OSError, ValueError):
            if int(lock.read_text().strip()) == os.getpid():
                lock.unlink()

    # -- Protokoll -----------------------------------------------------------------

    def _write(self, entry: dict[str, Any]) -> None:
        entry["at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        with self._lock, self._journal.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def log(self, message: str) -> None:
        print(f"[flow] {message}", flush=True)
        self._write({"type": "log", "message": message})

    def recall(self, label: str) -> dict[str, Any] | None:
        """Das letzte gültige Ergebnis unter diesem Label, auch aus einem früheren Lauf."""
        return self._by_label.get(label)

    # -- Arbeiter ------------------------------------------------------------------

    def agent(
        self,
        prompt: str,
        *,
        label: str,
        role: str = "build",
        cwd: str | Path | None = None,
        required: Sequence[str] | Mapping[str, str] = ("summary",),
        state: str = "",
    ) -> dict[str, Any] | None:
        """Startet einen Arbeiter und gibt sein JSON-Ergebnis zurück, sonst ``None``.

        ``required``: Namen oder ``{name: typ}`` mit ``str``, ``list``, ``dict``,
        ``bool``, ``int``, ``any``.
        ``state``: woran das Ergebnis hängt, etwa ``flow.head(worktree)`` für einen
        Prüfer. Ändert sich der Stand, läuft der Arbeiter beim nächsten Mal neu.
        ``None`` heißt: Zeit überschritten, kein Ergebnis, Schlüssel oder Typ falsch.
        Gescheiterte Aufrufe werden beim nächsten Lauf wiederholt, fertige nicht.
        """
        if role not in self.workers:
            raise FlowError(f"Rolle {role!r} steht nicht in workers.json ({sorted(self.workers)})")
        if not re.fullmatch(r"[A-Za-z0-9._-]+", label):
            raise FlowError(f"label {label!r}: nur Buchstaben, Ziffern, Punkt, Strich, Unterstrich")
        need = dict(required) if isinstance(required, Mapping) else dict.fromkeys(required, "any")
        unknown = [k for k, v in need.items() if v != "any" and v not in TYPES]
        if unknown:
            raise FlowError(f"required: unbekannter Typ für {unknown}")
        if self._closed.is_set():
            raise FlowError("Lauf ist beendet — es startet kein Arbeiter mehr")
        key = hashlib.sha256(f"{label}\0{role}\0{prompt}\0{state}".encode()).hexdigest()[:16]
        with self._lock:
            if key in self._done:
                cached = self._done[key]
            else:
                cached = None
                if label in self._active:
                    raise FlowError(f"label {label!r} läuft schon — Labels sind je Lauf eindeutig")
                if self._started >= self.max_agents:
                    raise FlowError(
                        f"Obergrenze erreicht: {self.max_agents} Arbeiter in diesem Lauf-Ordner. "
                        "Wer mehr braucht, entscheidet das bewusst über max_agents."
                    )
                self._started += 1
                self._active.add(label)
        if cached is not None:
            self.log(f"{label}: aus dem Protokoll übernommen")
            return cached
        try:
            return self._run_worker(prompt, label, role, cwd, need, key)
        finally:
            with self._lock:
                self._active.discard(label)

    def _run_worker(
        self,
        prompt: str,
        label: str,
        role: str,
        cwd: str | Path | None,
        need: dict[str, str],
        key: str,
    ) -> dict[str, Any] | None:
        self._write({"type": "start", "key": key, "label": label, "role": role})
        result_file = self.run_dir / "results" / f"{label}-{key}.json"
        result_file.unlink(missing_ok=True)
        spec = ", ".join(f"{k} ({v})" if v != "any" else k for k, v in need.items())
        fill = {
            "{prompt}": prompt + PROTOCOL.format(result_file=result_file, required=spec),
            "{result_file}": str(result_file),
            "{label}": label,
        }
        pattern = re.compile("|".join(re.escape(k) for k in fill))
        argv = [pattern.sub(lambda m: fill[m.group(0)], part) for part in self.workers[role]]
        started = time.monotonic()
        error = None
        rc: int | None = None
        with self._slots, (self.run_dir / "logs" / f"{label}-{key}.log").open("w") as log:
            try:
                if self._closed.is_set():
                    raise OSError("Lauf ist beendet")
                proc = subprocess.Popen(
                    argv,
                    cwd=str(cwd or self.repo),
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,
                    start_new_session=True,
                    env=self._worker_env,
                )
            except OSError as exc:
                proc = None
                error = f"Start gescheitert: {exc}"
            if proc is not None:
                with self._lock:
                    self._procs.add(proc)
                try:
                    rc = proc.wait(timeout=self.timeout_s)
                except subprocess.TimeoutExpired:
                    error = f"Zeitgrenze {self.timeout_s}s überschritten"
                finally:
                    with contextlib.suppress(ProcessLookupError, PermissionError):
                        os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait()
                    with self._lock:
                        self._procs.discard(proc)
        result: dict[str, Any] | None = None
        if error is None:
            try:
                data = json.loads(result_file.read_text(encoding="utf-8"))
            except FileNotFoundError:
                error = f"keine Ergebnisdatei (rc={rc})"
            except json.JSONDecodeError as exc:
                error = f"Ergebnisdatei kein JSON: {exc}"
            else:
                error = _check_types(data, need)
                if error is None:
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
            with self._lock:
                self._done[key] = result
                self._by_label[label] = result
            self.log(f"{label}: fertig nach {seconds}s")
        return result

    # -- Ablauf --------------------------------------------------------------------

    def parallel(self, thunks: Sequence[Callable[[], Any]]) -> list[Any]:
        """Alle zugleich, wartet auf alle. Ein gescheiterter Eintrag wird ``None``.

        Auch eine greifende Leitplanke (``FlowError``) beendet nur ihren Eintrag
        und steht im Protokoll; das Skript läuft weiter und kann berichten.
        """

        def safe(thunk: Callable[[], Any]) -> Any:
            try:
                return thunk()
            except Exception as exc:  # noqa: BLE001 - ein Eintrag darf den Lauf nicht kippen
                self.log(f"Eintrag gescheitert — {exc}")
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

    def git(self, *args: str, cwd: str | Path | None = None) -> subprocess.CompletedProcess[str]:
        """Ein Git-Befehl im Repo oder in ``cwd``. ``push`` wird verweigert."""
        if "push" in args:
            raise FlowError("flow.git verweigert push — Landen ist nicht Teil des Laufs")
        return _git(cwd or self.repo, *args)

    def head(self, path: str | Path) -> str:
        return _git(path, "rev-parse", "HEAD").stdout.strip()

    def worktree(
        self,
        label: str,
        base: str,
        *,
        branch: str | None = None,
        bootstrap: Sequence[Sequence[str]] = (),
    ) -> tuple[Path, str]:
        """Eigener Worktree auf eigenem Zweig ab ``base``.

        Ein vorhandener Worktree wird nur weiterbenutzt, wenn er auf dem
        erwarteten Zweig steht. ``bootstrap``: Befehle, die einmal nach dem
        Anlegen im Worktree laufen (Abhängigkeiten installieren).
        """
        path = self.run_dir / "worktrees" / label
        branch = branch or f"flow/{self.run_dir.name}/{label}"
        if branch in PROTECTED:
            raise FlowError(f"Worktree {label}: {branch} ist geschützt")
        if path.exists():
            current = _git(path, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
            if current != branch:
                raise FlowError(f"Worktree {label} steht auf {current!r}, erwartet {branch!r}")
            return path, branch
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            exists = _git(self.repo, "rev-parse", "--verify", "-q", f"refs/heads/{branch}")
            if exists.returncode == 0:
                done = _git(self.repo, "worktree", "add", str(path), branch)
            else:
                done = _git(self.repo, "worktree", "add", "-b", branch, str(path), base)
        if done.returncode != 0:
            raise FlowError(f"Worktree {label}: {done.stderr.strip()}")
        for argv in bootstrap:
            step = self.check(argv, path)
            if step["rc"] != 0:
                raise FlowError(f"Worktree {label}: {' '.join(argv)} scheitert\n{step['tail']}")
        return path, branch

    def unfinished(self, path: str | Path, base: str) -> list[str]:
        """Warum ein Arbeiterstand nicht zusammengeführt werden darf (leer = fertig)."""
        reasons = []
        dirty = _git(path, "status", "--porcelain").stdout.strip()
        if dirty:
            reasons.append(f"nicht committete Änderungen: {dirty.splitlines()[0]} …")
        count = _git(path, "rev-list", "--count", f"{base}..HEAD").stdout.strip()
        if count in ("", "0"):
            reasons.append(f"kein Commit über {base} hinaus")
        return reasons

    def changed_paths(self, branch: str, base: str) -> list[str]:
        done = _git(self.repo, "diff", "--name-only", "--no-renames", "-z", f"{base}...{branch}")
        if done.returncode != 0:
            raise FlowError(f"diff {base}...{branch}: {done.stderr.strip()}")
        return [p for p in done.stdout.split("\0") if p]

    def ownership(
        self, branch: str, base: str, owns: Sequence[str], shared: Sequence[str] = ()
    ) -> dict[str, list[str]]:
        """Welche geänderten Dateien gehören dem Arbeiter nicht?

        Umbenennungen zählen als Löschen und Anlegen, damit ein Verschieben aus
        einem fremden Ordner auffällt. ``shared``: gemeinsame Dateien — die ändert
        nur der Integrationsowner. ``foreign``: alles andere außerhalb von ``owns``.
        """
        outside = [p for p in self.changed_paths(branch, base) if not matches(p, owns)]
        return {
            "shared": [p for p in outside if matches(p, shared)],
            "foreign": [p for p in outside if not matches(p, shared)],
        }

    def integrate(self, target: str | Path, branches: Sequence[str]) -> dict[str, Any]:
        """Führt Zweige lokal im Worktree ``target`` zusammen.

        ``target`` muss ein Worktree dieses Laufs sein und auf einem eigenen
        Zweig stehen. Ein Konflikt wird abgebrochen und gemeldet; ihn löst der
        Integrationsowner.
        """
        where = Path(target).resolve()
        if not where.is_relative_to(self.run_dir / "worktrees"):
            raise FlowError(f"integrate verweigert: {where} ist kein Worktree dieses Laufs")
        head = _git(where, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        if head in PROTECTED or head in ("", "HEAD"):
            raise FlowError(f"integrate verweigert: {where} steht auf {head or 'keinem Zweig'}")
        merged: list[str] = []
        conflicts: dict[str, list[str]] = {}
        for branch in branches:
            done = _git(where, "merge", "--no-ff", "--no-edit", branch, timeout=600)
            if done.returncode == 0:
                merged.append(branch)
                continue
            listed = _git(where, "diff", "--name-only", "--diff-filter=U", "-z").stdout
            _git(where, "merge", "--abort")
            files = [p for p in listed.split("\0") if p]
            conflicts[branch] = files or [done.stderr.strip() or done.stdout.strip()]
        self._write({"type": "integrate", "target": head, "merged": merged, "conflicts": conflicts})
        return {"target": head, "merged": merged, "conflicts": conflicts}

    def check(self, argv: Sequence[str], cwd: str | Path, timeout_s: int = 1800) -> dict[str, Any]:
        """Ein Prüfbefehl (ausgewählte Tests, Build) auf dem zusammengeführten Stand."""
        argv = list(argv)
        if argv and Path(argv[0]).name == "git" and "push" in argv:
            raise FlowError("flow.check verweigert git push — Landen ist nicht Teil des Laufs")
        try:
            done = subprocess.run(
                argv, cwd=str(cwd), capture_output=True, text=True, timeout=timeout_s, check=False
            )
            rc, out = done.returncode, (done.stdout + done.stderr)
        except subprocess.TimeoutExpired:
            rc, out = 124, f"Zeitgrenze {timeout_s}s überschritten"
        except OSError as exc:
            rc, out = 127, str(exc)
        tail = "\n".join(out.splitlines()[-25:])
        self._write({"type": "check", "argv": argv, "rc": rc, "tail": tail})
        return {"argv": argv, "rc": rc, "tail": tail}
