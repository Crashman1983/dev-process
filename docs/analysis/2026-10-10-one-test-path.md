# Plan: Ein Testpfad — Lane, Baum-Zertifikat, Selektor aus Daten, Hook-Rahmen

Datum: 2026-10-10 · Issue: #206 · Release: v2.64.0 · Tier: 3 (Gate-Code: Pre-Push, Train, Gate-Runner)
Status: Entwurf, vor dem Plan-Review

## Anlass

`testing.md` schreibt die Testökonomie vor (nächstes Testpaket, Lane einmal halten,
Stempel-Cache, eine Vollsuite pro Batch), das Template liefert dafür keinen Code.
Kenni hat ihn nachgebaut (Bestandsaufnahme des Stewards, 2026-10-10): `scripts/lane.py`,
`test-changed-branch`, `certify` mit Push- und Merge-Zertifikat,
`select_audit_pins.py`, `push_selection.sh`, ein Pre-Push mit 609 Zeilen. Dieser
zweite Pfad ist von der Regel abgewichen. Eine scoped-Zertifizierung startete die
volle Backend-Suite, weil ein Testhelfer auf keine Karte passte. Ein Push hält die
Lane bis zu dreimal. Owner-Entscheidung: Das Template liefert den Mechanismus in
einem Release, danach schrumpft Kenni auf Daten und Konfiguration.

## Entscheidungen

- **D1 Eine Konfigurationsdatei.** `docs/process/testing.local.json` (Projektdaten,
  vom Template nie überschrieben) trägt Lanes, Stacks, Karten, Pins, Runner und
  Unmapped-Regel. Fehlt sie, verhalten sich Hook und Train wie bisher:
  Merge-Route, Standing-Block und Prozess-Gates laufen, Tests nicht. Ein Projekt
  ohne Testkonfiguration bekommt keinen geratenen Testlauf.
- **D2 Python, stdlib.** Alle neuen Werkzeuge sind stdlib-Python wie die übrigen
  Prozess-Skripte. Kein Bash-Rahmen.
- **D3 Ein Eigentümer je Frage.**
  - Lane-Sperre: `lane.py`.
  - Auswahl: `test_select.py`.
  - Zertifikat: `certificate.py`.
  - Push-Ablauf: `pre_push.py`.
  - Ref-Zeilen, Merge-Route und Bypass-Ledger: `merge_route.py`. `pre_push.py` ruft dessen Funktionen auf und kopiert sie nicht.
  - Merge-Basis: `check_review` / `process_git`.
- **D4 Lane-Ort.** `PROCESS_LANE_DIR`, sonst `$XDG_STATE_HOME/process-lanes`, sonst
  `~/.local/state/process-lanes`. Die Lanes gelten pro Host über alle Klone, wie
  bei Kenni (`~/.kenni-next`). Ein Projekt setzt `lane_dir` in der Config, um
  seinen bisherigen Ort zu behalten.
- **D5 Zertifikat-Ort und -Schlüssel.**
  - Ort: `<git-common-dir>/process-certificates/<kind>/<tree>-<cmd>`. Er gilt für alle Worktrees eines Klons, der Train-Worktree eingeschlossen. Über Klone hinweg wird nicht geteilt; ein zweiter Klon zertifiziert selbst.
  - `kind` ist `push` oder `merge`, `tree` ist `HEAD^{tree}`.
  - `cmd` sind die ersten 16 Zeichen von sha256 über die Beschreibung der Evidenz: für `push` die Stack-Konfiguration, für `merge` den Suite-Befehl.
- **D6 Unmapped-Regel.** Je Stack gilt `"unmapped": "skip"` (Default) oder `"full"`.
  - Bei `skip` läuft auf einem Branch-Push und in `certify` nichts für unzugeordnete Pfade. Sie werden genannt, und die Vollsuite des Zugs holt sie nach.
  - Bei `full` läuft der `full`-Befehl des Stacks.
  - Für den Merge-Push (Klasse `merge`) gilt die Regel nicht. Dort gilt das Merge-Zertifikat des Zugs. Fehlt es, läuft je Stack der `full`-Befehl, und ohne `full` wird der Push verweigert.
  - Die Regel gilt für jeden Aufrufer gleich, denn alle rufen `test_select.py`. Das schließt den Kenni-Vorfall.
- **D7 Eine Lane-Haltung pro Push.** `test_select.py run` nimmt die Lane einmal (In-Prozess über
  `lane.hold()`) und führt darunter alle Stacks aus. Es stoppt beim ersten Roten.
- **D8 Hook-Rahmen statt Framework-Kette.**
  - `pre_push.py` ist der eine Pre-Push-Einstieg.
  - `install_hooks.py` schreibt den Guard, der die Ref-Zeilen per stdin an `pre_push.py` gibt.
  - Im pre-commit-Framework ersetzt `pre-push-frame --hook-check` die Einträge `merge-route` und `process-gates`. Es prüft nur, dass der Rahmen lief, denn das Framework gibt keine Ref-Zeilen weiter.
  - Ein Projekt ohne `git_hooks`-Modul (Kenni) ruft `pre_push.py` aus seinem eigenen Hook auf: `exec uv run scripts/process/pre_push.py "$@"`.
- **D9 Lokale Schritte sind Gates.**
  - `gates.local.json`-Einträge bekommen `paths` (Globs). Ein solcher Eintrag läuft nur, wenn ein geänderter Pfad passt. Ist die Pfadmenge unbekannt, weil keine Basis da ist, läuft er immer (fail closed).
  - Neben `command` (Repo-Skript über `sys.executable`) gibt es `exec` (argv wie angegeben, z. B. `["make", "backend-lint"]`).
  - Einen weiteren Seam gibt es nicht.
- **D10 Bypass.**
  - `PROCESS_SKIP=<phase>[,<phase>]` überspringt im Rahmen `gates` und/oder `tests`. Merge-Route und Standing-Block lassen sich nicht überspringen.
  - Jeder Skip landet im Ledger von `merge_route` und wird aus einer dispatchten Session heraus abgelehnt. Das gilt wie heute für `SKIP=process-gates`.
  - Ein Skip schreibt keinen Stempel und kein Zertifikat.
- **D11 Stempel-Cache.**
  - Schlüssel: `sha <HEAD> <class> <scope>` und `tree <tree ohne .process-work/> <class> <scope>`, abgelegt in `git rev-parse --git-path process-push-ok`.
  - Ein SHA-Treffer beendet den Push grün.
  - Ein Tree-Treffer lässt nur die Prozess-Gates laufen (Buchhaltungs-Commit auf grünem Baum).
  - `scope` ist `process-only`, wenn der Push nur `.process-work/` ändert, sonst `code`. Bei `process-only` laufen keine Tests.
- **D12 Train.**
  - `--preflight CMD` läuft im Train-Worktree vor den Gates. Rot heißt Umgebungsfehler: Abbruch, niemand wird beschuldigt, kein Retry, keine Bisektion, der Lauf ist kein roter Zug.
  - Bei grüner Suite schreibt der Train das `merge`-Zertifikat für den Baum des Zugs.
  - Er protokolliert die Phasenzeiten (`lane_wait`, `preflight`, `gates`, `suite`, `retry`, `bisect`, `push`, `deploy`) als Logzeile und als JSON-Zeile in `process-train/phases.jsonl`.
- **D13 Zertifikat schreiben nur auf sauberem Baum.** Vorher und nachher gilt:
  - kein getrackter Diff und keine untracked, nicht ignorierte Datei (`git status --porcelain`, ohne `-uno`);
  - der Baum ist unverändert;
  - `MAKEFLAGS` trägt keine Zuweisung (`=`);
  - keine Variable aus `certificate_env` der Config ist gesetzt.

  Sonst wird nichts geschrieben, mit genanntem Grund. Damit sind die beiden Lücken aus Kenni #2474 im Template von Anfang an zu.

## Schnittstellen

### `docs/process/testing.local.json`

```json
{
  "lane_dir": "~/.kenni-next",
  "lanes": {"scoped": {"wait": 300}, "full": {"wait": 3600, "nice": 10}},
  "certificate_env": ["PYTEST_ADDOPTS"],
  "stacks": {
    "backend": {
      "paths": ["backend/"],
      "cwd": "backend",
      "runner": ["uv", "run", "pytest", "-q", "{paths}"],
      "full": ["uv", "run", "pytest", "-q"],
      "tests": ["backend/tests/**/test_*.py"],
      "map": [
        {"from": "backend/src/app/{pkg}/{sub}/**", "to": ["backend/tests/{pkg}/{sub}", "backend/tests/{pkg}"]}
      ],
      "pins": {"backend/src/app/api/": ["backend/tests/audit/test_errors.py"], "Makefile": ["backend/tests/scripts/"]},
      "unmapped": "skip",
      "select": null
    }
  }
}
```

- `paths`: die Präfixe, die zu diesem Stack gehören. Ein geänderter Pfad gehört zum
  ersten Stack, dessen Präfix passt. `pins` dürfen stackfremde Subjekte nennen, etwa
  `Makefile`.
- `map`: Muster mit `{name}` (genau ein Segment) und `**` (Rest). Die `to`-Liste ist die
  Rückfallkette. Es gilt das erste Ziel, das existiert und einen Test enthält, also eine
  Datei, die auf `tests` passt. Eine Datei, die selbst auf `tests` passt, wählt sich selbst.
- `runner`: argv. `{paths}` wird durch die gewählten Ziele ersetzt, relativ zu `cwd`.
  Leere Auswahl heißt: kein Lauf.
- `select`: optional ein argv eines lokalen Selektors (z. B. vitest related). Er bekommt
  die geänderten Pfade des Stacks auf stdin und gibt Ziele auf stdout aus. Exit ≠ 0 ist
  rot, nicht „nichts gewählt“.

### `scripts/process/lane.py`

- CLI:
  - `run [--lane NAME] [--wait S] [--label T] [--no-nice] -- CMD…`
  - `wait [--lane] [--wait] [--quiet]`
  - `status`, eine Zeile je konfigurierter Lane im Format `<name>: free` oder `<name>: held by pid <p> — <label> (<branch>) since HH:MM (<n> min)`
- Exit 75 bei erschöpftem Budget.
- API: `hold(lane, wait, label)` als Kontextmanager. Er wirft `LaneBusy` bei erschöpftem Budget.
- Sperre über `fcntl.flock` auf `<dir>/test-lane-<name>.lock`, Status als JSON daneben,
  atomar geschrieben.
- Lane-Namen und Budgets aus der Config, Default `scoped` und `full`.
- `train.py`, `tower.py` und `dispatch.py` lesen `scripts/process/lane.py status`.
  Rückfall auf `scripts/lane.py`, falls das Projekt noch ein eigenes hat. Die Ausgabe
  bleibt im heutigen Format, Leser ändern sich nicht.

### `scripts/process/test_select.py`

- `plan [--base REF] [--class branch|merge] [--json]`: je Stack die gewählten Ziele,
  die Rückfälle (genannt), die unzugeordneten Pfade und die Aktion
  (`run`/`skip`/`full`/`certified`).
- `run [--base REF] [--class …] [--lane scoped] [--certify]`:
  - Ein Zertifikat für den Baum überspringt alles: `push` auf Branch, `merge` bei Klasse `merge`.
  - Sonst laufen alle Stacks unter einer Lane-Haltung.
  - `--certify` schreibt nach Grün das `push`-Zertifikat (D13). Das ersetzt Kennis `certify`.
- `check`: Jedes `to`-Ziel muss existieren (Ziele einer Rückfallkette dürfen fehlen, wenn ein späteres existiert), ebenso jeder Pin und jedes Pin-Subjekt. Läuft als Gate `test-map`, sobald die Config da ist.
- Basis: `check_review.merge_base` / `process_git.fork_point`. Ohne Basis wird
  verweigert (Exit 2), nie ein Rückfall auf `HEAD~1`.
- Geänderte Pfade über `diff --name-only -z --no-renames base...HEAD`. Gelöschte Pfade zählen für Pins, für die Karte nicht.

### `scripts/process/certificate.py`

- `key(root, kind, evidence) -> str`, `has(root, kind, evidence) -> bool`.
- `write(root, kind, evidence, before_tree) -> (ok, why)` prüft D13 und schreibt.
- Die neuesten 200 je `kind` bleiben, ältere werden gelöscht.

### `scripts/process/pre_push.py`

Phasen in fester Reihenfolge:
1. Ref-Zeilen von stdin parsen (`merge_route`).
2. Merge-Route (`merge_route`), bei Push auf main.
3. Standing-Block (`check_review.standing_block_findings`), bei Push auf main.
4. Baum-Identität: Jeder gepushte Branch-SHA hat den Baum von HEAD, sonst Abbruch. Begründung: Der Hook prüft HEAD, ein anderer Baum bliebe ungeprüft.
5. Klasse (`merge`, wenn Ziel main/master, sonst `branch`) und Scope bestimmen; Stempel-Cache prüfen.
6. Prozess-Gates (`gate_runner`, mit Pfad-Triggern).
7. `test_select.run` mit Klasse und Lane `scoped`, nicht bei `process-only`.
8. Stempel schreiben.

Exit-Codes:
- 0 heißt grün.
- 1 heißt rot.
- 75 heißt Lane belegt, „kein Gate-Fehler“.
- 2 heißt nicht beurteilbar (keine Basis, Config defekt); der Push wird verweigert.

## Tasks

`[mechanical]` = ohne eigene Entscheidung ausführbar; `[design]` = mit benanntem Urteil.

1. `[mechanical]` `lane.py`
   - Kennis Fassung portieren: Config, `hold()`, Lane-Ort D4, `nice` je Lane, Signalweitergabe.
   - Tests: Sperre exklusiv zwischen zwei Prozessen; Budget → 75; Status-Format; ein toter Halter gibt frei; `hold()` wirft `LaneBusy`.
2. `[mechanical]` `train.py`, `tower.py` und `dispatch.py` lesen die neue Lane-Datei, mit Rückfall auf `scripts/lane.py`. Bestehende Tests bleiben grün, ein neuer deckt den Rückfall ab.
3. `[design: Mustersyntax, Rückfallkette]` `test_select.py plan/check`
   - Tests:
     - Kartenrückfall `{pkg}/{sub}` → `{pkg}`;
     - der Kenni-Vorfall: ein Testhelfer ohne Karte → `skip` mit Nennung, Klasse `merge` → `full`;
     - Pins, auch für gelöschte Subjekte;
     - Testdateien wählen sich selbst;
     - Stack-Zuordnung;
     - `check` meldet ein veraltetes Ziel und einen veralteten Pin;
     - keine Basis → Exit 2;
     - `select`-Fehler → rot.
4. `[mechanical]` `certificate.py`
   - Tests:
     - Schlüssel ändert sich mit dem Befehl;
     - untracked Datei, getrackter Diff, geänderter Baum, `MAKEFLAGS=X=1` und gesetzte `certificate_env`-Variable verhindern je das Schreiben;
     - Rotation auf 200.
5. `[design: Ein-Lane-Haltung über Stacks, Abbruch beim ersten Roten]` `test_select.py run/--certify`
   - Tests:
     - zwei Stacks unter einer Haltung: ein zweiter Prozess bekommt die Lane erst nach dem letzten Stack;
     - Zertifikat überspringt;
     - `--certify` schreibt nur bei Grün;
     - Lane belegt → 75.
6. `[design: Phasengrenzen, Bypass]` `pre_push.py`
   - Tests je Phase:
     - Baum-Identität verweigert;
     - SHA-Stempel → grün ohne Tests;
     - Tree-Stempel → nur Gates;
     - `process-only` → keine Tests;
     - `PROCESS_SKIP=tests` → Ledger-Zeile, kein Stempel, in dispatchter Session verweigert;
     - Merge-Push mit Merge-Zertifikat → keine Tests;
     - ohne Zertifikat → `full`;
     - Exit 75 durchgereicht;
     - ohne Config → nur Merge-Route, Standing-Block, Gates.
7. `[mechanical]` `install_hooks.py`: Der Guard ruft `pre_push.py`. In `.pre-commit-config.yaml` ersetzt `pre-push-frame --hook-check` die Einträge `merge-route` und `process-gates`. Bestehende Hook-Tests werden angepasst, die Garantie bleibt: Ein Push auf main ohne Guard wird verweigert.
8. `[design: Glob-Semantik wie test_select]` `gate_runner`
   - `paths` und `exec` in `gates.local.json`; Schema-Fehler bleibt hart.
   - Tests: Gate läuft bei passendem Pfad, sonst nicht; ohne Basis läuft es; `exec` mit argv.
9. `[design: was Umgebungsfehler heißt]` `train.py`
   - `--preflight`, Merge-Zertifikat nach grüner Suite, Phasenzeiten und `phases.jsonl`.
   - Tests:
     - Preflight rot → kein Blame, keine Bisektion, Train endet mit „environment“;
     - grüne Suite → Zertifikat vorhanden;
     - rote Suite → keines;
     - Phasen-Datei mit allen gelaufenen Phasen.
10. `[mechanical]` `process_kpis.py train-phases`: Median und Maximum je Phase über die letzten N Läufe.
11. `[mechanical]` Doku:
    - `testing.md` ersetzt die vier Projektregeln durch den gelieferten Mechanismus.
    - `train.md`: Preflight, Zertifikat, Phasen.
    - `failure-catalog.md`: Ressourcenleck, feste Wartezeit im Teardown.
    - `BOOTSTRAP.md`: `testing.local.json`.
    - CHANGELOG mit Migrationshinweis für Kenni.

## Plan decides (review-checklist)

- **Grenzen und Frist:**
  - Lane-Wartezeit aus der Config, Default 300 s für `scoped` und 3600 s für `full`.
  - Selektor-Befehl mit 600 s Timeout, Ablauf heißt rot.
  - `pre_push.py` hat keine Gesamtfrist. Die Tests laufen so lange wie heute, die Lane begrenzt das Warten.
- **Fehler- und Rückgabeform:** Exit-Codes wie oben. Jede Verweigerung nennt ihren Grund in einer Zeile.
- **Untrusted Input:** `testing.local.json` und `gates.local.json` sind Projektdaten vom Operator. Sie werden schema-geprüft, und ein Fehler ist hart. argv wird ohne Shell ausgeführt.
- **Spec-Risiken:**
  - Falscher Skip lässt einen roten Test bis zum Zug durch. Gegenmaßnahme: Der Zug läuft immer voll, und der Skip wird genannt.
  - Zertifikat ohne Evidenz. Gegenmaßnahme: D13, plus Tests je Bedingung.
  - Deadlock zwischen den Lanes `scoped` und `full`. Gegenmaßnahme: verschiedene Locks, keine Verschachtelung derselben Lane.
  - Kenni-Migration bricht den Hook. Gegenmaßnahme: Kennis Hook ruft `pre_push.py` erst nach dem Update, Rückfallpfad ist der alte Hook.
- **Zitierte Signaturen:** am Code prüfen. `merge_route` muss Parser und Ledger als Funktionen exportieren, `check_review.standing_block_findings` und `merge_base` existieren. Abweichungen im Plan-Review benennen.

## Anchor Delta

`testing.md`, `train.md`, `failure-catalog.md` und `BOOTSTRAP.md` ändern sich. CHANGELOG mit Migration.

## Nicht Teil

- Kennis Launcher, E2E-Ports und Datenverzeichnisse.
- Der vitest-related-Selektor bleibt Kennis `select`-Befehl.
- Keine Gate-Abschaltung, keine künstlichen Zertifikate, keine erhöhten Ressourcenlimits.
