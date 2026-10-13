# Plan: Wissensanker — erzeugte Bestandslisten, Leser-Schritt im Plan, knowledge-gap-Befunde (v2.70)

Datum: 2026-10-13 · Status: **Revision 3, nach zwei Planprüfungen (je revise, kein Blocker)** · Issue: #223 ·
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

- DECISION 2026-10-13 steward: Die committete Liste speichert `source` ohne
  Zeilennummer — because Zeilennummern bei jeder Änderung darüber das Gate rot
  färben und parallele Branches im Zug kollidieren lassen (Planprüfung, Befund 3).
  `for-plan` liefert die Zeile live.
- DECISION 2026-10-13 steward: Der FINDING-Schlüssel heißt `kind=`, nicht
  `cause=` — because es gibt schon die Label-Achse `cause:*` für Bug-Herkunft
  mit anderem Vokabular (Planprüfung, Befund 8).

- DECISION 2026-10-13 owner: Ein Änderungsprotokoll „für Nicht-Techies“ für
  dev-process und für Projekte (Kenni) kommt in diese Version — because
  heute steht nirgends lesbar, was neu oder besser ist (Kenni hat kein
  Changelog, dev-process nur ein sehr technisches).

## 3. Umfang

**Drin:**

1. Erzeugte Bestandslisten mit Abweichungsprüfung.
2. Mechanischer Auslöser: Bestandszeilen zu den Dateien eines Plans.
3. `## Consumers` als fester Ort der Leser-/Schreiber-Suche im Plan.
4. `kind=` an FINDING-Zeilen, Auswertung in `process_kpis.py rounds`, getrennt nach Plan- und Code-Review.

5. Ein verständliches Änderungsprotokoll: Fragmente je Änderung im Projekt,
   daraus erzeugtes `NEWS.md`; für dev-process selbst ein `NEWS.md` je Release.

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
  Standard 120. `allow_empty`: bool, Standard false. Die Summe aller
  `timeout` muss unter 540 s liegen, damit der Check im Gate-Zeitlimit von
  600 s bleibt.
- Fehlt die Datei: `inventory.py` sagt „nichts konfiguriert“ und endet mit 0.
  `check_inventory.py` (der Gate-Einstieg) endet dann mit 1: Wer den Check
  registriert hat, hat Listen erwartet — ein umbenannte Konfiguration darf
  nicht still grün werden. Kaputt (unlesbar, falsche Typen, unbekannte
  Schlüssel, Zeitlimit-Summe zu hoch): Fehler mit Ort, nie ein stiller
  Standard.

**Extraktor-Vertrag.** Der Befehl läuft im Repo-Wurzelverzeichnis und gibt
auf stdout je Zeile ein JSON-Objekt aus:

- `id` (nicht leerer String, eindeutig), `source` (`pfad` oder
  `pfad:zeile`, Pfad relativ zum Repo), beliebige weitere Felder mit String-,
  Zahl-, Bool- oder Null-Werten. `note` ist reserviert.
- Fehler, nie ein halbes Ergebnis: Exit ≠ 0, Zeitüberschreitung (die ganze
  Prozessgruppe wird beendet, denn `uv run` startet ein Enkelkind; Muster wie
  in `train.py`), Ausgabe über 5 MB, Ausgabe, die nicht striktes UTF-8 ist,
  eine Zeile ohne gültiges JSON, ohne `id` oder `source`, ein doppeltes `id`,
  ein verschachtelter Wert, ein Feld `note`, null Zeilen ohne `allow_empty`.
  Die Fehlermeldung zeigt stderr des Extraktors (gekürzt).

**Ausgabe** `docs/inventory/<name>.md`, deterministisch:

- Kopf: Titel, Hinweis „erzeugt von `inventory.py update <name>`, nicht von
  Hand ändern“, der Befehl.
- Eine Markdown-Tabelle, Zeilen nach `id` sortiert. Spalten: `id`, dann die
  übrigen Felder **alphabetisch**, dann `source`, dann `note` — unabhängig
  von der Reihenfolge der Extraktor-Ausgabe. Fehlende Felder sind leer.
- `source` wird ohne `:zeile` gespeichert.
- Maskierung umkehrbar: `\` → `\\`, `|` → `\|`, Zeilenumbruch → `\n`. Ein Test
  sichert, dass Rendern und erneutes Lesen dieselben Zeilen ergeben.
- Notizen: optional in `docs/inventory/<name>.notes.json` als
  `{"<id>": "<text>"}`, von Hand gepflegt. `update` übernimmt sie in die
  Spalte `note`; Notizen zu verschwundenen Zeilen nennt es als „verwaist“
  und lässt sie in der Datei, bis jemand sie löscht.

**Befehle** (`scripts/process/inventory.py`):

- `update [NAME…]` — Extraktoren laufen lassen, Ausgaben schreiben.
- `check [NAME…]` — dasselbe ohne Schreiben; jede Abweichung ist ein Fehler
  mit dem Befehl, der sie behebt. Ebenfalls Fehler: eine konfigurierte Liste
  ohne `.md`, eine `.md` oder `.notes.json` unter `docs/inventory/` ohne
  konfigurierte Liste. Dasselbe tut `check_inventory.py .` als
  Gate-Einstiegspunkt.
- `for-paths PATH…` und `for-plan PLAN` — siehe 4.2.
- `list` — konfigurierte Listen mit Zeilenzahl.

**Als Gate.** Das Projekt registriert
`{"inventory": {"module": null, "command": ["scripts/process/check_inventory.py", "."]}}`
in `docs/process/gates.local.json` und beobachtet ihn zuerst im Schatten.
Der Gate-Runner protokolliert ihn wie jedes Gate; `nodes` wiegt ihn.
Reihenfolge, weil eine Abschwächung erst auf dem Integrationsbranch gilt
(`gate_modes.py`): entweder Listen grün erzeugen und dann registrieren, oder
erst die Schatten-Zeile (`weaken --to shadow --observe`, Owner-Zeile) mergen
und danach registrieren. Ein lokales Gate mit `module: null` zählt nicht als
Kern-Gate (`gate_modes._core` liest nur die festen `GATES`) und lässt sich
deshalb abschwächen.

**Ein Owner je Tatsache.** Wo eine Liste vorhandene Prosa ersetzt (etwa eine
Job-Aufzählung in der Architektur-Doku), wird die Prosa zum Verweis; das
steht in der Moduldoku als Pflicht des Projekts.

### 4.2 Mechanischer Auslöser

`inventory.py for-plan PLAN` liest die Pfade, die der Plan in Backticks nennt
(`plan_drift.named_paths`, ein Owner), und gibt jede Bestandszeile aus, deren
`source`-Pfad darunter ist oder unter einem genannten Verzeichnis liegt:
`<liste>  <id>  <pfad:zeile>  <note>`. `for-paths` tut dasselbe für
angegebene Pfade.

Gelesen werden nur **konfigurierte** Listen. Die Zeilennummer kommt aus einem
Live-Lauf des Extraktors; scheitert er, nennt `for-plan` den Pfad ohne Zeile
und sagt warum — es ist eine Planungshilfe, kein Gate.

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
- **Auslöser, eine Liste:** ein geändertes Dateiformat oder eine
  Ledger-Zeile, eine Konstante, ein Standardwert, ein Timeout (auch über
  Prozess- und Client-Grenzen), ein Dateilayout, eine Umgebungsvariable, eine
  Annahme darüber, in welchem Prozess etwas läuft.
- **Ort:** ein Abschnitt `## Consumers` im Plan, der **nur** den Suchbefehl
  und seine Treffer (`pfad:zeile`) je Element enthält. Was angepasst wird,
  bleibt in den Tasks — die bestehende Regel „kein zweites Inventar“ gilt
  weiter. `workflow.md` (Plan) und `/plan` (die Sätze „not into a separate
  table“ und „does not build a second one“) werden so umformuliert, dass
  beides zusammenpasst.
- **Owner:** die Checklisten-Zeile; `/plan` und `workflow.md` verweisen
  darauf. Die Planprüfung fragt nach dem Abschnitt (`refute.md`, Plan-Brief).
  Der Copilot-Prompt `plan.prompt.md` spiegelt diese Regeln nicht und bleibt
  unverändert.
- **Kein Gate** in v2.70: Ob ein Plan ein Format ändert, kann kein Programm
  sicher erkennen. Gemessen wird über `kind=knowledge-gap` (4.4).

### 4.4 `kind=` an FINDING-Zeilen

- Neuer optionaler Schlüssel in `check_issues.py` (`FINDING_KEYS`),
  Werte: `knowledge-gap | requirement | implementation | test-gap |
  process | environment`. Ein anderer Wert ist ein Formfehler wie bei
  `origin=`; ohne `kind=` bleibt die Zeile gültig. Wie alle Schlüssel steht
  er vor dem Titel.
- Überall, wo die FINDING-Schlüssel aufgezählt sind, kommt `kind=` dazu:
  das Format im Review-Bundle (`make_review_bundle.py`, das sieht der Prüfer),
  `docs/process/modules/github-issues.md` und `telemetry.md`. Die Doku trennt
  `kind=` (was für ein Befund) ausdrücklich von den Labels `cause:*` (woher
  ein Bug kam).
- Prüfer-Briefe (`verification-independence.md`, „What each round judges“,
  und `refute.md`) bitten um `kind=` bei Blockern; `knowledge-gap` heißt:
  Der Autor kannte etwas Bestehendes nicht, das es schon gab.
- Bei einem `knowledge-gap`-Befund trägt der Fix die fehlende Tatsache an
  ihrem Anker nach (Bestands-Notiz, Registry-Story, ADR, Architektur-Doku)
  — `/execute`, Fix-Runde.
- `process_kpis.py rounds`: `_blockers_by_work` bekommt einen Parameter
  `key` (Standard `origin`), damit es ein Leser bleibt. Die Ausgabe erhält
  eine Zeile „blockers by kind“, getrennt nach Plan- und Code-Review,
  ungekennzeichnet als `-`; `--json` liefert dieselben Zahlen.
- **Woran ein Plan-Review-Bericht erkennbar ist:** Der Suffix `-plan` steht
  nur in den REVIEW-Zeilen des Journals, nicht im Bericht. Deshalb bittet
  `make_review_bundle.py --plan` den Prüfer um eine Kopfzeile `phase: plan`;
  `check_review.report_header` (der eine Leser der Berichtskopfzeilen) liest
  `phase` mit. Ein Bericht ohne `phase: plan` zählt als Code-Review; ältere
  Plan-Reviews ohne die Zeile werden so falsch einsortiert, was die
  Auswertung ab Einführung nicht stört. Die
  Wochen-Anleitung nennt sie als Eingabe.

### 4.5 Verständliches Änderungsprotokoll (`news.py`)

**Ziel:** In wenigen Sätzen je Änderung lesbar, was neu, besser oder behoben
ist — ohne Dateinamen und Fachbegriffe, für den Owner und spätere Leser.

**Projekte (Template):**

- **Fragment je Änderung**, im selben Branch wie die Änderung:
  `news/<slug>.md` mit erster Zeile `type: new | improved | fixed`
  (nicht `kind:`, um keinen zweiten Wortschatz unter dem Namen von FINDING
  `kind=` einzuführen), optional `issue: #N`, dann ein bis drei Sätze in
  Alltagssprache. Fragmente bleiben liegen; `render` baut jedes Mal alles neu.
- **Datum:** nicht im Dateinamen, sondern das Datum, an dem das Fragment auf
  dem Integrationsbranch hinzukam (`git log --diff-filter=A` dort); ein noch
  nicht gemergtes Fragment trägt „unreleased“. So landet ein langlebiger
  Branch im richtigen Monat, und `show --since` verpasst nichts.
  Fragmente statt einer gemeinsamen Datei, weil parallele Branches sonst im
  Zug an derselben Stelle kollidieren; außerdem funktioniert das für jeden
  Merge-Weg (Zug und `finish.py`, der ff-only merget und keinen eigenen
  Commit schreibt).
- **Wann:** Jede Änderung, die ein Nutzer bemerkt (Funktion, Verhalten,
  Oberfläche, behobener Fehler), bringt ein Fragment mit. Innere Arbeit
  (Refactoring, Prozess, Tests) nicht. Der Plan nennt es als Task; im
  Kurzverfahren (Tier 1) schreibt es der Commit mit.
- **`scripts/process/news.py`:**
  - `new --kind K --slug S "Text"` legt ein Fragment an;
  - `check` prüft die Form aller Fragmente (Kopfzeile, Art, nicht leer,
    höchstens 600 Zeichen) — als Hinweis, kein Gate;
  - `render` schreibt `NEWS.md`: nach Monat gruppiert, neueste zuerst,
    innerhalb des Monats nach Art (neu, besser, behoben), dann nach Datum
    und Dateiname; je Eintrag Datum und Text; deterministisch. Ein
    fehlerhaftes Fragment bricht `render` mit Dateiname ab, statt still
    übersprungen zu werden;
  - `show [--since DATUM]` druckt die Einträge für Digest und Wochenbericht.
  - Überschriften und Art-Bezeichnungen kommen aus
    `docs/process/news.local.json` (`title`, `labels`), Standard englisch;
    ein deutsches Projekt setzt „Neuigkeiten“, „Neu“, „Verbessert“,
    „Behoben“.
- **Wer rendert:** Der Steward im Wochentakt (ein Schreiber, keine
  Konflikte), über denselben Merge-Weg wie sein Wochenbericht: Branch, dann
  `finish.py` oder Zug — kein direkter Commit auf den Integrationsbranch.
  `improvement-weekly.md` und die Steward-Anleitung nennen den Schritt. `human_digest.py` zeigt einen
  Abschnitt „New and improved“ aus `news.py show --since` der letzten Tage.
- **Review:** Die Checkliste fragt bei nutzersichtbaren Änderungen nach dem
  Fragment und ob es ohne Fachwissen verständlich ist.

**dev-process selbst:**

- `NEWS.md` im Wurzelverzeichnis, deutsch, je Release drei bis sechs Sätze:
  Was ändert sich für ein Projekt, das die Vorlage nutzt, und was bringt es.
  Rückwirkend für v2.60 bis v2.69, damit der Anfang lesbar ist.
- `tools/release.py` verlangt neben dem CHANGELOG-Eintrag einen
  `NEWS.md`-Abschnitt `## vX.Y.Z — <Titel>` für die Version, in `check()` und
  in `release()`. Der Leser dafür liegt in `tools/release_notes.py` (ein
  Owner neben dem CHANGELOG-Leser). `NEWS.md` kommt in `RELEASE_FILES`, sonst
  verweigert das Release wegen eines unsauberen Baums; `tests/test_release_tool.py`
  nimmt `NEWS.md` von der Prüfung auf fremde Versionsnennungen aus. Die
  README verlinkt `NEWS.md` als ersten Einstieg „Was ist neu“.

## 5. Aufgaben

1. `[mechanical]` `template/scripts/process/inventory_config.py` (Leser der
   Konfiguration, Muster `testing_config.py`) mit Tests: fehlend, gültig,
   jeder Formfehler, Zeitlimit-Summe ≥ 540 s.
2. `[mechanical]` `template/scripts/process/inventory.py`: `update`, `check`,
   `list`, `for-paths`, `for-plan` nach 4.1/4.2 — Spaltenreihenfolge,
   Maskierung, `source` ohne Zeile, Notizen-Sidecar, verwaiste Dateien,
   begrenzter Lauf mit Prozessgruppe sind dort entschieden.
3. `[mechanical]` `template/scripts/process/check_inventory.py` (Gate-Einstieg:
   ohne Konfiguration rot, sonst `inventory.check`, Exit 0/1).
4. `[mechanical]` `tests/test_inventory.py`: fehlende Konfiguration
   (Werkzeug grün, Gate-Einstieg rot), Update und Check bytegleich, dieselben
   Zeilen in anderer Reihenfolge ergeben dieselbe Datei, Rendern und Lesen
   ergibt dieselben Zeilen (`\`, `|`, Zeilenumbruch), eine verschobene
   Zeilennummer lässt den Check grün, Abweichung rot mit Befehl, jeder kaputte
   Extraktor-Fall rot (Exit, Timeout mit Enkelprozess, kein JSON, ohne
   id/source, doppeltes id, verschachtelter Wert, `note`, nicht-UTF-8, leer
   ohne `allow_empty`, zu groß), fehlende und verwaiste Dateien rot, Notizen
   behalten und verwaiste gemeldet, `for-plan` und `for-paths` mit Datei- und
   Verzeichnistreffer und nur konfigurierten Listen, Registrierung als lokales
   Gate im echten Gate-Runner (rot bei Abweichung; im Schatten nicht
   blockierend, mit Basis-Ref-Fixture wie in `test_gate_modes.py`).
5. `[mechanical]` `check_issues.py.jinja`: `kind` in `FINDING_KEYS`,
   `FINDING_KINDS`, Validierung; Test für gültige, ungültige und fehlende
   `kind`.
6. `[mechanical]` `process_kpis.py` `rounds`: `_blockers_by_work(root, key=…)`,
   Zeile „blockers by kind“ getrennt nach Plan- (`phase: plan`) und
   Code-Review, `--json`; Test mit je einem Plan- und Code-Review-Bericht.
7. `[mechanical]` `make_review_bundle.py`: `kind=` im FINDING-Format, mit
   `--plan` zusätzlich die Bitte um `phase: plan`; `check_review._REPORT_KEY`
   nimmt `phase` auf. Tests in `tests/test_review_bundle.py` (Bundle nennt
   `kind=`, Plan-Bundle nennt `phase: plan`) und für `report_header`.
8. `[mechanical]` Doku: neue Moduldoku `docs/process/inventories.md` (Vertrag,
   Gate-Registrierung, Reihenfolge beim Schattenstart, Prosa-zu-Verweis),
   `/plan` und `workflow.md` (Auslöser, `## Consumers`, die zwei Sätze zum
   zweiten Inventar), `review-checklist.md` (Consumers), `refute.md`
   (Plan-Brief), `verification-independence.md` (`kind=`), `/execute`
   (Fix-Runde), `improvement-weekly.md` (Eingabe), `modules/github-issues.md`
   und `modules/telemetry.md` (`kind=`, Abgrenzung zu `cause:*`); CHANGELOG.

9. `[mechanical]` `template/scripts/process/news.py` (`new`, `check`,
   `render`, `show`, Konfiguration `news.local.json`) mit
   `tests/test_news.py`: Fragment anlegen, Formfehler gemeldet, `render`
   bricht bei kaputtem Fragment mit Dateiname ab, Rendern deterministisch und
   nach Monat/Art/Datum/Name geordnet, Datum aus dem Integrationsbranch
   (älteres Fragment auf langem Branch landet im Merge-Monat), „unreleased“
   vor dem Merge, eigene Bezeichnungen, `show --since`, leeres `news/` ergibt
   eine leere, gültige Datei.
10. `[mechanical]` `human_digest.py`: Abschnitt „New and improved“; Test.
11. `[mechanical]` Doku: `docs/process/news.md` (Zweck, Fragmentform, wann,
    wer rendert), `/plan` und `workflow.md` (Task für nutzersichtbare
    Änderungen), Kurzverfahren, `review-checklist.md`, Steward-Anleitung und
    `improvement-weekly.md` (wöchentliches Rendern), AGENTS-Abschnitt.
12. `[mechanical]` dev-process: `NEWS.md` mit Abschnitten v2.60–v2.70,
    Leser in `tools/release_notes.py`, Prüfung in `release.py` `check()` und
    `release()`, `NEWS.md` in `RELEASE_FILES`, Ausnahme in
    `tests/test_release_tool.py`; Tests: fehlender Abschnitt verweigert,
    vorhandener besteht; README/README-DE verlinken `NEWS.md`.

## 6. Unabhängige Durchsetzung

- Der Bestands-Check ist hart, sobald registriert und auf `block`: Er
  vergleicht Bytes, keine Prosa.
- `kind=` prüft der FINDING-Parser.
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

- **Erfolg:** In einem Pilotprojekt sinkt der Anteil `kind=knowledge-gap`
  an den Blockern **im Code-Review** über acht Wochen gegenüber den ersten
  vier Wochen mit Kennzeichnung. Plan-Review-Befunde zählen getrennt: Wenn
  `## Consumers` wirkt, verschieben sich Wissenslücken ins Plan-Review, wo sie
  billiger sind. Die Auswertung macht der Steward im Wochentakt, als
  Verbesserungs-Record mit eingefrorenen Kriterien.
- **Kosten:** `nodes` (Laufzeit des Bestands-Checks), `flow`/`losses`
  (Planphase).
- **Rückbau:** Check aus `gates.local.json` nehmen; `kind=` bleibt
  optional und harmlos.

## 9. Was diese Version für Projekte heißt

Reines Update ohne Projektschritt (`releases.md`): Ohne
`inventories.local.json` läuft nichts Neues; `kind=` ist optional. Wer die
Listen nutzen will, schreibt Extraktoren und registriert den Check.
