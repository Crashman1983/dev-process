# Plan: Selbstlernender Entwicklungsprozess (Steward + Prozess-Maintainer)

Datum: 2026-10-12 · Release: v2.67 (Vorschlag) · Tier: 3 (Gate-Code: `dispatch.py`, `train.py`; neues Prozess-Skript `optimize.py`)

## Anlass

Der Owner hat ein Konzept vorgelegt: Kenni bekommt einen selbständig lernenden
Entwicklungsprozess mit zwei dauerhaften Verantwortlichen, dem Steward (Kenni)
und dem dev-process-Agenten (dieses Repository). Gemeinsamer Regelkreis:
Beobachten → Ursache → Verbesserung → unabhängig prüfen → begrenzt einsetzen →
Wirkung bewerten → übernehmen oder zurückrollen. Auftrag: Konzept reviewen und
umsetzen, mit der Randbedingung, dass es auch in anderen Repositories
ausgerollt werden kann.

## Review des Konzepts

### Was trägt

- **Untergrenzen statt Punktzahl.** Sicherheit, Korrektheit und Akzeptanz sind
  Boden, Zeit/Tokens/Betreuung werden darüber optimiert. Das passt zur
  Cockpit-Regel „kein Wert ist ein Ziel“ (`telemetry.md`, Goodhart).
- **Vorab festgelegte Kriterien** („ein Experiment darf seine Freigabekriterien
  nicht nachträglich erleichtern“) sind der wichtigste Satz des Konzepts.
- **Generik-Grenze mit vier Kategorien** (Kern, Modul, Projektkonfiguration,
  Projekt) und das Recht, eine Verallgemeinerung abzulehnen. Das ist Regel 4
  (ein Eigentümer) auf Repository-Ebene.
- **Graph abgeleitet, mit Herkunft und Unsicherheit; fehlende Kante beweist
  keine Unabhängigkeit; keine Graph-Datenbank.** Richtig dimensioniert.
- **Aufwand der Selbstoptimierung zählt mit**, „unentschieden“ ist ein
  zulässiges Ergebnis, kleine Stichproben beweisen keine Sicherheit.

### Befunde und was daraus in der Umsetzung folgt

- **R1 Neutralität.** Das Konzept spricht von Kenni und „Du“. Was ins Template
  geht, sagt „Projekt“ und „Owner“; Testsuite (`test_core_docs.KENNI`) erzwingt
  das. Das Kenni-Mandat selbst gehört in das Kenni-Repository, nicht hierher.
  → Template liefert Vertrag, Werkzeug und ein *Beispiel*-Mandat.
- **R2 „Dauerhafte Verantwortliche“ sind Sessions.** Steward und
  dev-process-Agent sind Rollen, die neu starten. Dauerhaft ist nur, was in
  Dateien steht. Das Konzept verlangt das (Abschnitt 7, letzter Satz), nennt
  aber keinen Ort. → Ein Optimierungsauftrag ist eine Datei
  `.process-work/optimizations/OPT-NNNN-<slug>.md` im Projekt, mit
  Zustandslog; das Upstream-Issue wird verlinkt.
- **R3 Ein Verantwortlicher vs. zwei Entscheidungen.** Abschnitt 7 verlangt
  einen eindeutigen Verantwortlichen der Gesamtbewertung, Schritt 7 verteilt die
  Entscheidung auf zwei. → Zwei getrennte Entscheidungen mit je einem Eigentümer:
  die Pilotentscheidung im Projekt-Record (`responsible:`, i. d. R. Steward),
  die generische Aufnahme im Upstream-Issue/Release (Maintainer). Der Record
  verlinkt beide. So bleibt jede Entscheidung eindeutig.
- **R4 „Begrenzt einsetzen“ ist technisch offen.** Prozessdateien gelten
  repo-weit. Ohne Schalter gibt es weder einen auf eine Aufgabenklasse
  begrenzten Pilot noch einen sofortigen Stopp. → Experiment-Flag, an den
  Record-Zustand gebunden: `optimize.py active <flag> --issue/--tier/--class`
  ist nur wahr, solange genau ein Record mit diesem Flag `piloting` ist, seine
  eingefrorenen Kriterien unverändert sind, `until` nicht überschritten ist
  und die Auswahl passt. Stopp = Zustandswechsel. Ein manipulierter Record
  schaltet sein Experiment ab (fail closed).
- **R5 Pilot unveröffentlichter Prozessänderungen.** Das Konzept sagt nicht,
  wie Kenni eine dev-process-Änderung erprobt, bevor sie generisch übernommen
  ist. → Der Mechanismus wird hinter einem Flag im regulären Release
  ausgeliefert, standardmäßig aus. Andere Projekte merken nichts (Generik
  gesichert), das Projekt pilotiert per Record. Kein Fork, kein Sonder-Ref.
  `releases.md` beschreibt das.
- **R6 Messbarkeit.** Mehrere Ziele sind heute nicht messbar:
  - Durchlaufzeit Planung → Deploy: Start (Dispatch-Logs) und Merge
    (`done`-Report) sind da; der Deploy ist keinem Branch zuzuordnen, weil
    `phases.jsonl` nur die Anzahl der Passagiere schreibt. → Der Zug schreibt
    künftig `branches` und `ended`.
  - Arbeits- vs. Wartezeit: aus Dispatch-Logs und Reports ableitbar
    (Phase läuft = Arbeit; zwischen Phasenende und nächstem Start, `blocked` =
    Warten). → neue KPI-Familie `flow`.
  - Tokens: nur `output_tokens`. Cache-Anteile brauchen die Harness-Felder.
    → Der eine Transkript-Leser in `dispatch.py` liest zusätzlich Input- und
    Cache-Felder; fehlen sie, heißt es „nicht gemessen“.
  - Betreuungsaufwand: „aktive Zeit“ ist nicht messbar. → Proxy: Owner-
    `DECISION`-Zeilen der Issue und Bypass-Einträge im Merge-Route-Ledger;
    ehrlich als Proxy markiert.
  - Wiederherstellungszeit: es gibt keine Incident-Records. → bleibt „nicht
    gemessen“, offen benannt.
  - Folgefehler: nur der CFR-Proxy. → Commit-Trailer `Regression-of: #N`
    verknüpft eine Reparatur mit ihrem Ursprungsissue; `flow` zählt ihn im
    Nachbeobachtungsfenster.
  - Prozessversion je Issue: aus `.copier-answers.yml` am Merge-Commit
    ableitbar, keine neue Instrumentierung.
- **R7 Statistik.** Ein Pilot auf einer Aufgabenklasse liefert kleine n;
  Vorher/Nachher wird von Modell- und Aufgabenmix-Wechseln überlagert.
  → Mindest-n und Mindesteffekt gehören in die vorab eingefrorenen Kriterien;
  unter Mindest-n ist das Ergebnis „unentschieden“. Für gleichzeitige
  Vergleiche gibt es die Auswahl `parity=odd|even` (Issue-Nummer), also eine
  deterministische Kontrollgruppe im selben Zeitraum.
- **R8 Budget und automatischer Schutz.** Ein Token-Budget ist nur so gut wie
  die Token-Messung. → Deterministisch automatisch ist nur die Laufzeitgrenze
  (`until`: danach ist das Flag aus). Budget- und Qualitätsverletzungen meldet
  `optimize.py status`; stoppen tut der Steward. Ehrlich so benannt.
- **R9 Gate oder Beobachtung.** Neue Regeln starten hier als Beobachtung
  (REFUTE-Warnung v2.32.0), und der Lean-Pass hat Gates auf das gekürzt, was
  nachweislich trägt. Ein 13. Gate für einen Mechanismus ohne einen einzigen
  echten Record wäre spekulativ. → Kein neues Gate. Die Kernregel wird am
  Verwendungspunkt durchgesetzt: `active` schaltet ab, `move`/`decide`
  verweigern. `optimize.py check` läuft beim Steward-Housekeeping und kann als
  lokales Gate eingetragen werden. Ob es ein Kern-Gate wird, entscheidet sich
  nach Paket D.
- **R10 Graph.** Die Auswirkungssicht (Vertrag → Implementierung →
  Verbraucher) ist sprachspezifisch. Generisch ableitbar sind Pläne, Issues,
  Testkarte (`testing.local.json`), Co-Change aus git und Review-Nachweise.
  Sprachspezifische Analyse ist eine Projektanbindung. → `graph.py` im
  `telemetry`-Modul (read-only Cockpit über bestehende Spuren), kein neues
  Modul: ein Modul kostet Verdrahtung in zehn Dateien, und der
  Wiederverwendungsbedarf ist noch nicht belegt (Konzept, Abschnitt 6, letzter
  Punkt). Projektquellen kommen über `docs/process/graph.local.json` als
  Kommandos, die Kanten als JSON-Zeilen liefern.
- **R11 Selbstbewertung.** Der dev-process-Agent entwirft, implementiert und
  „verantwortet die Analyse“ seines Experiments. Das ist Selbstabnahme.
  → Der Record nennt `implementer:`. Vor dem Pilot braucht er eine
  `REVIEWED`-Zeile von jemand anderem als dem Implementierer; die
  Entscheidung ist die Übergangszeile im Log, und auch sie darf nicht vom
  Implementierer stammen. Das Werkzeug prüft beides.
- **R12 Rückbau fehlt im Pflichtfeld-Katalog.** Abschnitt 9 verlangt einen
  sicheren Rückbauweg, die Tabelle in Abschnitt 7 hat kein Feld dafür.
  → `## Rollback` ist Pflicht vor dem Pilot.
- **R13 Überlagerte Experimente.** „Ein Experiment pro Mechanismus“ reicht
  nicht, wenn zwei Experimente dieselben Issues treffen. → `check` meldet zwei
  laufende Records mit gleichem Mechanismus oder gleichem Flag als Fehler.
- **R14 Steward-Kosten.** Die Analyse darf den Steward nicht teurer machen als
  sie spart. → Der Improvement-Loop läuft im täglichen Housekeeping, nicht pro
  Tick; der Steward meldet nur Ereignisse.
- **R15 Maintainer-Doku existiert nicht.** Das Repository hat keine
  Maintainer-Dokumentation. → `MAINTAINING.md` im Repository-Wurzelverzeichnis;
  copier rendert nur `template/`, die Rolle wird also nicht ausgeliefert.

## Entscheidungen

- **D1 Vertrag als Kern-Doku.** `docs/process/optimization.md`: Regelkreis,
  Ziele und ihre Messung, Rollen, Platzierung, Record-Format, Zustände,
  Entscheidungsrechte, Messregeln, Abschlussbedingung. Neutral formuliert.
- **D2 Record-Format.** Kopf mit Schlüsselzeilen (`state`, `responsible`,
  `implementer`, `mechanism`, `placement`, `flag`, `select`, `until`,
  `budget-tokens`, `budget-hours`, `issues`, `upstream`, `supersedes`),
  Abschnitte Observation, Hypothesis, Placement, Trial, Limits, Criteria,
  Generality, Rollback, Result, Decision, Log. Log-Zeilen:
  `- <date> <who>: <state> — because …`, `- REVIEWED …`, `- FROZEN …`.
  Die Entscheidung ist die Übergangszeile in einen Endzustand.
- **D3 Zustände.** proposed → designed → piloting → (stopped →) evaluating →
  adopted | rejected | rolled-back | superseded; proposed/designed → rejected.
- **D4 Einfrieren.** Der Übergang nach `piloting` schreibt
  `FROZEN … terms=<sha256-12>` über Trial, Limits, Criteria und die
  Kopfzeilen `select`, `until`, `budget-*`, `flag`, `mechanism`. Danach ist
  jede Abweichung ein Fehler. Mit git-Historie vergleicht `check` zusätzlich
  mit dem Stand des Commits, der die FROZEN-Zeile einführte; ein
  mitgeändertes Hash hilft dann nicht.
- **D5 Mandat.** `docs/process/optimization.local.json` im Projekt
  (Beispiel: `optimization.example.json`). Ohne Mandat kein Pilot,
  Analyse bleibt erlaubt. Das Werkzeug erzwingt `max_pilot_days`, das
  Vorhandensein eines Budgets und wer übernehmen darf (`steward_may`).
  Nur der Owner ändert das Mandat (Konvention, im Vertrag benannt; die Datei
  ist reviewpflichtig wie jede Prozessdatei).
- **D6 Telemetrie.** `process_kpis.py flow [--issue N] [--json]`:
  Zeitstrahl je Issue mit `measured|estimated|missing` je Feld; Zusammenfassung
  Median/P90, Arbeit und Warten getrennt. `dispatch.issue_token_usage` liest
  Output-, Input- und Cache-Tokens. Der Zug schreibt `branches` und `ended`.
- **D7 Graph.** `graph.py build|context|missed` im telemetry-Modul, read-only.
  Kanten tragen `source`, `at` (Commit) und `certainty`
  (`declared|derived|inferred`). `missed` vergleicht, was ein Branch geändert
  hat, mit dem, was sein Plan nannte, und meldet übersehene Beziehungen.
- **D8 Rollen.** Steward-Kommando bekommt den Abschnitt „Improvement loop“;
  AGENTS.md und Copilot verweisen auf den Vertrag. Die Maintainer-Rolle steht
  in `MAINTAINING.md`.
- **D9 Nicht in diesem Release.** Paket D (erstes Experiment in Kenni) und E
  sind Betrieb, kein Code dieses Repositories. Das Kenni-Mandat schreibt der
  Kenni-Steward mit dem Owner. Incident-Records für die Wiederherstellungszeit
  bleiben offen.

## Aufgaben

1. Vertrag, Beispielmandat, `optimize.py` (new, move, review, check, status,
   active, list) mit Tests: Zustandsfolge, Pflichtfelder je Zustand,
   Einfrieren und Manipulation (auch per git), Selbstfreigabe verweigert,
   Mandatsgrenzen, Flag-Auswahl inklusive Parität und Ablauf, Überlagerung.
2. Steward, Adapter-Verweise, `start-here`-Router, `releases.md` (Pilot und
   Rückbau), `commits.md` (`Regression-of:`), `MAINTAINING.md`.
3. `flow`, Token-Leser, Zug-Phasen, `graph.py` mit Tests.
4. CHANGELOG, unabhängiger Refute und Review, PR.

## Unabhängige Durchsetzung

Die bestehenden Gates bleiben die harte Grenze; nichts hier lockert sie.
`optimize.py` ist kein Gate (R9) und fällt in jedem Zweifel auf „inaktiv“.
Die Änderungen an `dispatch.py` (zusätzlicher Leser) und `train.py`
(zusätzliche Felder in einer Telemetriezeile) ändern keine Entscheidung eines
Gates.

## Refute und Review Runde 1 — Änderungen

Ergebnis: block. Ein unabhängiger Prüfer, nicht der Implementierer, fand 1 BLOCKER, 5 MAJOR und 8 MINOR. Gemeinsame Ursache: `optimize.py` setzte seine Regeln nur beim Schreiben durch `move` durch. `check` und `active` verglichen kaum mehr als ein Hash über eine lockere Markdown-Lesart.

- **F1 (BLOCKER) Doppelte Überschrift:** Eine zweite `## Criteria`, auch in einem Codeblock, trug die „echten“ Bedingungen. → Ein strenger Parser liest nur, was ein Leser sieht. Kommentare und Codeblöcke werden entfernt; eine doppelte Überschrift oder ein doppeltes Kopffeld ist ein Fehler, und der Record ist dann aus.
- **F2 Umbenennung:** `--follow --reverse` folgt keiner Umbenennung. → `versions()` liest `--follow --name-status -z` und kennt so den Pfad je Commit.
- **F3 Vorbereitetes FROZEN:** Die Historienprüfung ließ sich an eine versteckte FROZEN-Zeile in einem früheren Commit hängen. → Gezählt werden nur FROZEN-Zeilen im Log. *Jede* committete Fassung mit FROZEN muss die heutigen Bedingungen tragen.
- **F4 Handgeschriebener Start:** `max_pilot_days`, Startrecht und „nicht der Implementierer“ prüfte nur `move`. → `problems()` leitet alle Regeln aus dem Log neu ab: wer startete, wann eingefroren wurde, und `until` gemessen vom FROZEN-Datum. Ein nachträglich verkleinertes Mandat bindet auch laufende Versuche.
- **F5 Selbstfreigabe:** Namen wurden exakt verglichen, und `implementer` war optional. → `norm()` ignoriert Groß- und Kleinschreibung sowie Leerraum. Ab `designed` ist ein echter `implementer` Pflicht.
- **F6 Flow-Zuordnung:** Der `done`-Report des Zugs trägt das kleinste `#N` aus den Commits. Ein `Regression-of: #12` legte so die Reparatur unter #12 ab. → `flow` ordnet nur über eigene Worker-Reports und den Branch-Namen zu, nie über `done`. Der Zug ignoriert `Regression-of:`-Zeilen bei der Suche nach Issue-Referenzen.
- **F7 Stopp verweigerbar:** → `stopped` und `evaluating` werden nie verweigert. `rolled-back` bleibt auch bei kaputtem Record oder Mandat offen.
- **F8 Versteckte REVIEWED-Zeilen:** → durch den Parser aus F1 erledigt.
- **F9 Block nach Pass:** → Ein Block auf den eingefrorenen Bedingungen steht und wird durch einen Pass nicht überstimmt.
- **F10 `active` ignorierte Konflikte:** → `active` und `move` beachten `_conflicts`, also doppelte Nummern und zwei Versuche auf einem Mechanismus oder Flag. Der Konflikt wird an jedem beteiligten Record genannt.
- **F11 Flow-Kleinigkeiten:**
  - Ein neu dispatchter Phasenlauf wird als Vereinigung von Intervallen gezählt.
  - Bei einem wiederverwendeten Branch-Namen zählt der erste Merge nach Beginn, markiert als `estimated`.
  - Kaputte Zeilen in `phases.jsonl` werden übersprungen.
  - Ein Transkript ohne Usage-Felder gilt als `missing`.
- **F12 Doku-Behauptungen:**
  - Bypass-Zählung als nicht gemessen benannt.
  - Keine `DECIDED`-Zeile; die Entscheidung ist die Übergangszeile.
  - Tokens nur aus dispatchten Sitzungen.
  - Test-Kanten nur bei `context`.
  - Dotfile-Pfade erkannt.
- **F13 Tests:**
  - Je ein Regressionstest zu F1–F11.
  - Zwei Mutanten getötet: Rechteprüfung beim Start und in Endzuständen.
  - Ein Zeitzonentest unter `America/New_York` tötet den Mutanten „naiv als UTC“.
  - `optimization.md` steht in der Neutralitätsprüfung der Kern-Doku.
- **F14 `graph.local.json` überdimensioniert:** Bleibt. Das Konzept verlangt austauschbare Projektanbindungen und nennt „Projektanbindungen sind getrennt“ als Abnahmekriterium von Paket C. Ohne diese Schnittstelle müsste projektspezifische Analyse in den Kern. Der Code dafür umfasst rund 40 Zeilen ohne neue Abhängigkeit.
