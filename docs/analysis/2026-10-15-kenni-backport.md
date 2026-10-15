# Plan: Kenni-Rückport I

Datum: 2026-10-15 · Issues: #226, #234, #235, #221 (Anker), Teile von #232 · Tier: 3 (Gate-Code: `certificate.py`, `train.py`, `finish.py`, `test_select.py`, `testing_config.py`, `attest_evidence.py`, `train.py`-Meldung) · Release: reines Update

## Anlass

Der Owner hat am 2026-10-15 entschieden: Kennis Änderungen sollen so weit wie möglich zurück ins Template, damit Kenni dem Template nicht davonläuft.

Ein Render des Templates (v2.71.0) mit Kennis Antworten, verglichen mit Kennis `origin/main`, ergab 27 abweichende Template-Dateien. Sieben davon trägt Kenni in `.process-owned`:
- die fünf Dateien der `merge_scope`-Naht;
- `dispatch.py` und `tower.md` mit dem Codex-Harness.

Wer eigenen Gate-Code in Template-Dateien hat, macht jedes Template-Update zu Tier 3.

Die Einordnung jedes Hunks (Port, verallgemeinert, lokal, überholt) ist in der Session dokumentiert. Dieses Release bringt alles, was keine Owner-Entscheidung braucht.

## Entscheidungen

- **D1 `merge_scope`-Naht (#226), Port aus Kenni (#2587, #2603, #2604).**
  - **`testing_config`:** kennt den optionalen Schlüssel `merge_scope`, ein argv, dessen stdout die gewählten Stufen der Merge-Suite nennt.
  - **`certificate` als einziger Owner:**
    - `run_stages(root)` liest `<git-dir>/merge-suite/stages`.
    - `merge_evidence(root, suite, scope_argv, ran_stages=None)` liefert die Suite plus `scope=<sortierte Stufen>`. Ohne `merge_scope` ist es die Suite allein, also wie bisher. Ist der Scope unbekannt, liefert die Funktion None.
    - `run_evidence(root, suite, scope_argv)` ist der Schreiber. Der Scope kommt immer aus der `stages`-Datei des Laufs und wird nie neu berechnet. Fehlt die Datei bei konfiguriertem `merge_scope`, gibt es kein Zertifikat.
  - **Leser:** `test_select.run` nutzt `merge_evidence` über `merge_certificate_evidence`.
  - **Schreiber:**
    - `train._certify_merge` und `finish --tests` schreiben über `run_evidence`.
    - `train._suite_key` hasht dieselbe Evidenz. Ein grüner Lauf mit engerem Scope ist nie das Memo des vollen Laufs.
  - **#226-AC zur Abweichung:** Das Issue nannte `scope=unknown` als Evidenz. Gebaut wird Kennis strengere Form: Ein unbekannter Scope ergibt kein Zertifikat, und es wird keins gefunden.
- **D2 Stufen-Vertrag.**
  - `testing.md` beschreibt, was eine stufenweise Merge-Suite hinterlässt: `<git-dir>/merge-suite/stages` (Stufennamen, durch Leerzeichen getrennt) und je Stufe `<git-dir>/merge-suite/<stufe>.time` mit `t0 t1 exit`.
  - Wer keine Stufen hat, schreibt nichts, und alles bleibt wie bisher.
- **D3 Stufenzeiten (Kenni #2586).**
  - `train._collect_stage_times` sammelt die Marker nach Suite und Retry in `stages` der `phases.jsonl`-Zeile. Fehlt ein Marker, gilt die Stufe als `skipped`. Ein doppelt gesammelter Lauf zählt einmal.
  - `process_kpis.py train-phases` zeigt je Stufe den letzten Zug, Median, Maximum sowie die Zahl der übersprungenen und roten Läufe. Das deckt #232 AC-5 teilweise ab.
- **D4 Kleine Ports.**
  - Ein ungültiges `stale_minutes` wird gemeldet statt still verworfen. Owner ist `tower.resolve_stale_minutes`.
  - Design-Contract-Notizen kommen in `<surface>.notes.md` mit `merge=union` (Kenni #2588).
  - Der CI-Workflow erhält `concurrency`.
  - `rehydrate.py` bekommt `check=False` an zwei Stellen.
  - `.process-work/inbox.md` wird mit `merge=union` gemergt.
- **D5 Docs und Befehle (Kenni, verallgemeinert):**
  - `testing.md`:
    - zwei Lanes und begrenztes Push-Warten mit Exit 75 (ersetzt den veralteten Satz „one lock per host“);
    - Kosten der Push-Auswahl;
    - die Worker-Zahl gehört in den argv des Runners, nie in `addopts`;
    - die Quarantäne als Daten;
    - die Geräte-Matrix läuft nachts.
  - `train.md`: Der Gate-Runner startet über `gate_invoke`. Kann er nicht starten, ist das Exit 2 und kein „main ist rot“.
  - `journal-state-plans.md`: Die Inbox wird per Union-Merge zusammengeführt.
  - `commits.md`: Ohne CI-Adapter trägt keine Route einen gehosteten Job.
  - `improvement-weekly.md`, `news.md`: das Muster eines geplanten Laufs mit Sperre, Timeout und nur eigenen Branches (#235, Teil 3).
  - `/plan`: Kennis „Plan coherent work packets“ und „Every task carries its anchors“. Das ist der Text aus #221, und die Messung dort zeigt die Wirkung: Median 53 statt 183 Turns, 25 % statt 42 % Lesen und Suchen.
  - `/execute`: „Spend turns on edits, not on finding“, ohne Claude-Werkzeugnamen.
  - `/finish`: `--tests` mit genau dem String aus `merge_suite`. `--tests-passed` ist eine Behauptung und zertifiziert nichts.
  - `/steward`: Die Suite kommt standardmäßig aus `merge_suite`.
  - `/review`: Das Attest-Beispiel nennt `--with <report>`.
  - Quick (Befehl und `workflow.md`): eine beobachtbare Satz-Beschreibung, der Endzustand der Daten, und eskaliert wird bei einer Designwahl oder bei parallelen Subagenten.
- **D6 #234:** Gestrichene ACs. `~~AC-<id>~~` und `AC-<id>: struck — <Grund>` (auch `dropped`) nehmen eine AC aus der Testpflicht. Ohne Grund bleibt sie Pflicht.
- **D7 #235:**
  - Die Template-Beispiele für `codex exec` schließen stdin (`< /dev/null`) und begrenzen die Laufzeit (`timeout 1800`).
  - Die Zug-Meldung zu DECISION NEEDED zitiert die Zeile und nennt die Antwortform.
  - `/plan` und `/execute` sagen: Wer eine Frage beantwortet, setzt die Marke.
- **D8 Nicht in diesem Release:**
  - **Codex-Harness** (`dispatch.py`, `_dispatch_codex.py`, `tower.md`, `rehydrate --codex`): wartet auf die Owner-Entscheidung, ob ein Codex-Review beratend oder attestierbar ist.
  - **`/execute`-Regel** „Übergabe oder Kontext behalten“: wartet auf die Owner-Entscheidung, weil sie eine Template-Regel umkehrt.
  - **Später:**
    - die Pflicht-Deklaration im Design-Contract-Gate;
    - `due_measurements` mit lokalen Meilensteindaten;
    - `ci.github: manual`;
    - die Sprachwahl als Copier-Antwort;
    - Kennis lokale Stufenwahl (#232, braucht die gemessene Leser-Karte aus kenni#2607).
  - **Bleibt bei Kenni:**
    - `quick.md` als Spezialisierung;
    - Projektnotizen in Docs;
    - Codex-Modellmatrix;
    - abgeschaltete CI.

## Aufgaben

1. **Naht (D1, D2).** Port der fünf Dateien ohne Kenni-Kommentare, mit verallgemeinerten Docstrings (statt „`make test-merge`“ heißt es „die Merge-Suite“). Dazu `testing.md` „Stages“. Tests aus Kennis `test_merge_stage_selection_2587.py` und `test_merge_stage_residuals_2603.py`, soweit sie die Naht betreffen:
   - Evidenz mit Scope;
   - ein unbekannter Scope zertifiziert nie;
   - die Evidenz kommt aus der `stages`-Datei;
   - ein abweichender Scope ist kein Treffer;
   - Schreiber und Leser teilen einen Owner;
   - `_suite_key` enthält den Scope;
   - Zug und `finish` ohne `stages` schreiben kein Zertifikat;
   - der Config-Schlüssel.
2. **Stufenzeiten (D3).** Port mit Kennis `test_train_stage_times.py` und dem `train-phases`-Test.
3. **Kleine Ports (D4)** mit Tests: stale-Warnung, Notes-Sidecar, `.gitattributes`.
4. **Docs und Befehle (D5).** Dazu die Doc-Pins in `test_core_docs` und die Pins der Befehle.
5. **#234 (D6) und #235 (D7)** mit Tests.
6. **CHANGELOG und NEWS.** Für Kenni gilt: `.process-owned` verkleinern auf `dispatch.py` und `tower.md`; die Naht- und Stufenzeit-Tests werden zu Template-Tests; das lokale Drift-Paket bleibt.

## Unabhängige Durchsetzung

`check_review`, `merge_route` und `pre_push` bleiben, wie sie sind. Ohne `merge_scope` ist die Naht verhaltensgleich: Die Evidenz ist die Suite allein, der Hash bleibt gleich, und vorhandene Zertifikate und Memos gelten weiter. Mit `merge_scope` wird es strenger, weil ein unbekannter Scope kein Zertifikat ergibt.
