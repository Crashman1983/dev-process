# Plan: Wissensanker — erzeugte Bestandslisten, Leser-Schritt im Plan, knowledge-gap-Befunde (v2.70)

Datum: 2026-10-13 · Status: **Entwurf, zur Planprüfung** · Issue: #223 ·
Tier: 3 (neuer Prüfcode, Änderung am FINDING-Parser) · Baut auf: v2.69

## 1. Anlass

Der Owner fragte, ob Kenni ohne Code aus seinen Unterlagen nachgebaut werden
könnte und ob eine lebende Ist-Spezifikation die Entwicklung verbessern würde.
Zwei Erhebungen und eine Refutation führten zu diesem Mittelweg.

- **Ursachen blockierender Review-Befunde** (rund 200 Befunde eines
  Projekts seit September): Implementierungsfehler ~47 %, Test- oder
  Evidenzlücke ~14 %, fehlendes Wissen über Bestehendes ~10–16 %, unklare
  Anforderung ~11 %, Prozess ~9 %, Umgebung ~3 %. Nur 8–12 % der
  Block-Berichte bestanden ausschließlich aus Wissenslücken.
- **Refutation beider Optionen.** Eine volle Ist-Spezifikation ist durch die
  Belege nicht gedeckt: Die fehlenden Fakten lagen auf Code-Ebene (Leser
  eines Dateiformats, ein Frontend-Timeout, eine Testumgebungs-Variable),
  Prosa driftet, und LLM-Verhalten lässt sich aus Prosa nicht neu erzeugen.
  Ein reiner Katalog hätte die Beispiele ebenfalls kaum verhindert: Einer
  Job-Liste fehlte die Spalte „läuft in welchem Prozess“, und ein Fakt stand
  schon in der Architektur-Doku und wurde nicht gelesen.

Die Fehler entstanden beim **Lesen** (vorhandenes Wissen wurde nicht
gefunden) und bei **unbekannten Lesern** (niemand suchte, wer ein Format,
eine Konstante oder ein Timeout noch verwendet). Dort setzt der Plan an.

## 2. Entscheidungen

- DECISION 2026-10-13 owner: Mittelweg statt voller Ist-Spezifikation — because
  die Belege tragen nur Anker für vorhandenes Wissen, keine Prosa-Spezifikation.
- DECISION 2026-10-13 owner: #221 bleibt unter seinem Messprotokoll (fünf
  Läufe); sein Text kommt erst nach der Auswertung ins Template — because das
  Protokoll ist die Bedingung des Owners.
- DECISION 2026-10-13 steward: Der Bestands-Check ist kein Kern-Gate, sondern
  ein mitgelieferter Check, den das Projekt in `gates.local.json`
  registriert — because ein neuer Knoten im Schatten beginnen soll
  (`gate_modes.py weaken --to shadow --observe`), und Kern-Gates lassen sich
  nicht abschwächen.

## 3. Umfang

**Drin:**

1. Erzeugte Bestandslisten mit Abweichungsprüfung.
2. Mechanischer Auslöser: Bestandszeilen zu den Dateien eines Plans.
3. `## Consumers` als fester Ort der Leser-/Schreiber-Suche im Plan.
4. `cause=` an FINDING-Zeilen, Auswertung in `process_kpis.py rounds`.

**Bewusst draußen:** Prosa zum LLM-Verhalten, Regeltabellen, Screen-Karte,
NFR-Katalog, Archivierung der Änderungs-Specs, Nachbau-Probe, der Text aus
#221.

## 4. Design

### 4.1 Erzeugte Bestandslisten (`inventory.py`, `check_inventory.py`)

**Konfiguration** `docs/process/inventories.local.json` (Projektdaten, das
Template schreibt sie nie; eigener kleiner Leser wie `testing_config.py`):

```json
{
  "inventories": {
    "env":  {"command": ["uv", "run", "scripts/inventory_env.py"], "timeout": 120},
    "jobs": {"command": ["python3", "scripts/inventory_jobs.py"]}
  }
}
```

- Name: `[a-z0-9-]+`. `command`: argv, keine Shell. `timeout`: Sekunden,
  Standard 120.
- Fehlt die Datei: nichts konfiguriert, beide Werkzeuge enden mit 0 und
  sagen das. Kaputt (unlesbar, falsche Typen, unbekannte Schlüssel): Fehler
  mit Ort, nie ein stiller Standard.

**Extraktor-Vertrag.** Der Befehl läuft im Repo-Wurzelverzeichnis und gibt
auf stdout je Zeile ein JSON-Objekt aus:

- `id` (nicht leerer String, eindeutig), `source` (`pfad:zeile`, Pfad
  relativ zum Repo), beliebige weitere Felder mit String-, Zahl-, Bool- oder
  Null-Werten.
- Exit ≠ 0, Zeitüberschreitung, eine Zeile ohne gültiges JSON, ohne `id`
  oder `source`, ein doppeltes `id` oder ein verschachtelter Wert: Fehler,
  nie ein halbes Ergebnis.

**Ausgabe** `docs/inventory/<name>.md`, deterministisch:

- Kopf: Titel, Hinweis „erzeugt von `inventory.py update <name>`, nicht von
  Hand ändern“, der Befehl.
- Eine Markdown-Tabelle, Zeilen nach `id` sortiert, Spalten: `id`, dann die
  übrigen Felder in der Reihenfolge ihres ersten Auftretens, `source` zuletzt,
  dann `note`. `|` und Zeilenumbrüche in Werten werden maskiert.
- Notizen: optional in `docs/inventory/<name>.notes.json` als
  `{"<id>": "<text>"}`, von Hand gepflegt. `update` übernimmt sie in die
  Spalte `note`; Notizen zu verschwundenen Zeilen nennt es als „verwaist“
  und lässt sie in der Datei, bis jemand sie löscht.

**Befehle** (`scripts/process/inventory.py`):

- `update [NAME…]` — Extraktoren laufen lassen, Ausgaben schreiben.
- `check [NAME…]` — dasselbe ohne Schreiben; jede Abweichung ist ein Fehler
  mit dem Befehl, der sie behebt. Dasselbe tut `check_inventory.py .` als
  Gate-Einstiegspunkt.
- `for-paths PATH…` und `for-plan PLAN` — siehe 4.2.
- `list` — konfigurierte Listen mit Zeilenzahl.

**Als Gate.** Das Projekt registriert
`{"inventory": {"module": null, "command": ["scripts/process/check_inventory.py", "."]}}`
in `docs/process/gates.local.json` und beobachtet ihn zuerst im Schatten.
Der Gate-Runner protokolliert ihn wie jedes Gate; `nodes` wiegt ihn.

**Ein Owner je Tatsache.** Wo eine Liste vorhandene Prosa ersetzt (etwa eine
Job-Aufzählung in der Architektur-Doku), wird die Prosa zum Verweis; das
steht in der Moduldoku als Pflicht des Projekts.

### 4.2 Mechanischer Auslöser

`inventory.py for-plan PLAN` liest die Pfade, die der Plan in Backticks nennt
(`plan_drift.named_paths`, ein Owner), und gibt jede Bestandszeile aus, deren
`source`-Pfad darunter ist oder unter einem genannten Verzeichnis liegt:
`<liste>  <id>  <pfad:zeile>  <note>`. `for-paths` tut dasselbe für
angegebene Pfade.

Die Zeilen werden **nicht** neu erzeugt, sondern aus den committeten
`docs/inventory/*.md` gelesen — billig, offline, ohne Extraktor-Lauf. Ist
eine Liste veraltet, meldet das der Check, nicht der Auslöser.

`/plan` (und `workflow.md`, Plan): Nach dem Festlegen der Dateien läuft
`for-plan`; jede gelistete Zeile, die ein Task berührt, steht mit `pfad:zeile`
im Task. Keine Pflicht, wenn das Projekt keine Listen hat.

### 4.3 `## Consumers`

Die Regel existiert schon zur Hälfte: `review-checklist.md`, Completeness,
„Plan decides“ verlangt bei Umbenennen, Entfernen, Verschieben oder einer
geänderten Version, einem Pfad oder einer Konstante jeden Leser, „found by a
search the plan quotes“. Erweitert wird:

- **Umfang:** zusätzlich Dateiformate und Ledger-Zeilen, Standardwerte und
  Timeouts (auch über Prozess- und Client-Grenzen), Umgebungsvariablen,
  Annahmen darüber, in welchem Prozess etwas läuft.
- **Ort:** ein Abschnitt `## Consumers` im Plan — je geändertem Element der
  Suchbefehl, die Treffer (`pfad:zeile`) und der Task, der jeden Treffer
  anpasst. Er ersetzt keine Tasks; er belegt die Suche.
- **Owner:** die Checklisten-Zeile; `/plan` und `workflow.md` verweisen
  darauf. Die Planprüfung fragt nach dem Abschnitt (`refute.md`, Plan-Brief).
- **Kein Gate** in v2.70: Ob ein Plan ein Format ändert, kann kein Programm
  sicher erkennen. Gemessen wird über `cause=knowledge-gap` (4.4).

### 4.4 `cause=` an FINDING-Zeilen

- Neuer optionaler Schlüssel in `check_issues.py` (`FINDING_KEYS`),
  Werte: `knowledge-gap | requirement | implementation | test-gap |
  process | environment`. Ein anderer Wert ist ein Formfehler wie bei
  `origin=`; ohne `cause=` bleibt die Zeile gültig.
- Prüfer-Briefe (`verification-independence.md`, „What each round judges“,
  und `refute.md`) bitten um `cause=` bei Blockern; `knowledge-gap` heißt:
  Der Autor kannte etwas Bestehendes nicht, das es schon gab.
- Bei einem `knowledge-gap`-Befund trägt der Fix die fehlende Tatsache an
  ihrem Anker nach (Bestands-Notiz, Registry-Story, ADR, Architektur-Doku)
  — `/execute`, Fix-Runde.
- `process_kpis.py rounds` zählt Blocker zusätzlich nach `cause`
  (ungekennzeichnet = `-`). Die Wochen-Anleitung nennt die Zahl als Eingabe.

## 5. Aufgaben

1. `[mechanical]` `template/scripts/process/inventory_config.py` (Leser der
   Konfiguration) mit Tests: fehlend, gültig, jeder Formfehler.
2. `[design]` `template/scripts/process/inventory.py`: `update`, `check`,
   `list`, `for-paths`, `for-plan`; Rendern mit Maskierung und stabiler
   Reihenfolge; Notizen-Sidecar. Urteil: Spaltenreihenfolge und Maskierung
   so, dass ein zweiter Lauf bytegleich ist.
3. `[mechanical]` `template/scripts/process/check_inventory.py` (Gate-Einstieg,
   ruft `inventory.check`, Exit 0/1).
4. `[mechanical]` `tests/test_inventory.py`: fehlende Konfiguration, Update
   und Check bytegleich, Abweichung rot mit Befehl, jeder kaputte
   Extraktor-Fall rot (Exit, Timeout, kein JSON, ohne id/source, doppeltes
   id, verschachtelter Wert), Notizen behalten und verwaiste gemeldet,
   `for-plan` und `for-paths` mit Datei- und Verzeichnistreffer, Registrierung
   als lokales Gate im echten Gate-Runner (rot bei Abweichung, im Schatten
   nicht blockierend).
5. `[mechanical]` `check_issues.py.jinja`: `cause` in `FINDING_KEYS`,
   `FINDING_CAUSES`, Validierung; Test für gültige, ungültige und fehlende
   `cause`.
6. `[mechanical]` `process_kpis.py` `rounds`: Zählung nach `cause`; Test.
7. `[mechanical]` Doku: neue Moduldoku `docs/process/inventories.md` (Vertrag,
   Gate-Registrierung, Schattenstart, Prosa-zu-Verweis), `/plan`,
   `workflow.md`, `review-checklist.md` (Consumers), `refute.md`
   (Plan-Brief), `verification-independence.md` (`cause=`), `/execute`
   (Fix-Runde), `improvement-weekly.md` (Eingabe), Copilot- und
   AGENTS-Verweise, wo `/plan` gespiegelt ist; CHANGELOG.

## 6. Unabhängige Durchsetzung

- Der Bestands-Check ist hart, sobald registriert und auf `block`: Er
  vergleicht Bytes, keine Prosa.
- `cause=` prüft der FINDING-Parser.
- `## Consumers` und die Übernahme der Bestandszeilen in Tasks bleiben
  Urteil der Planprüfung. Ob das trägt, zeigt die `knowledge-gap`-Zahl.

## 7. Risiken und Gegenmaßnahmen

- **Extraktoren sind Projektcode, der im Gate läuft.** Wie `testing.local.json`
  unter Review; argv ohne Shell; Zeitlimit.
- **Langsamer Gate-Lauf.** Zeitlimit je Liste; `nodes` zeigt die Kosten; im
  Schatten zuerst.
- **Ritual.** Kein Projekt muss Listen führen; ohne Konfiguration ändert
  sich nichts. `## Consumers` nur, wenn sich ein Format, eine Konstante, ein
  Standardwert, ein Timeout, ein Layout, ein Ledger oder eine Variable ändert.
- **Doppelte Wahrheit.** Prosa, die eine Liste dupliziert, wird zum Verweis.

## 8. Messung und Rückbau

- **Erfolg:** In einem Pilotprojekt sinkt der Anteil `cause=knowledge-gap`
  an den Blockern über acht Wochen gegenüber den ersten vier Wochen mit
  Kennzeichnung. Die Auswertung macht der Steward im Wochentakt, als
  Verbesserungs-Record mit eingefrorenen Kriterien.
- **Kosten:** `nodes` (Laufzeit des Bestands-Checks), `flow`/`losses`
  (Planphase).
- **Rückbau:** Check aus `gates.local.json` nehmen; `cause=` bleibt
  optional und harmlos.

## 9. Was diese Version für Projekte heißt

Reines Update ohne Projektschritt (`releases.md`): Ohne
`inventories.local.json` läuft nichts Neues; `cause=` ist optional. Wer die
Listen nutzen will, schreibt Extraktoren und registriert den Check.
