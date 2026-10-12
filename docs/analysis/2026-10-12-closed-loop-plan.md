# Plan (Entwurf, zur Refutation): Verbesserungsregelkreis mit Ausgleich — v2.68

Datum: 2026-10-12 · Status: **Entwurf, nicht umgesetzt** · Baut auf: v2.67.0
(`docs/analysis/2026-10-12-self-improving-process.md`) · Tier: 3 (Messung,
Aktivierung und Freigabe des Prozesses ändern sich selbst)

Revision 2. Sie ersetzt den Entwurf D1–D11 nach zwei Eingaben:

1. Codex-Refutation auf PR #216, Verdict `block`, zehn Befunde.
2. Präzisierte Owner-Anforderung (unten).

Die Antwort auf jeden Codex-Befund steht in §9.

## 1. Anforderung

Der Owner will einen Mechanismus, der **kontinuierlich** Verbesserungspotenzial
erkennt und bearbeitet. Verbesserung ist kein Selbstzweck. Der Mechanismus
balanciert zwischen Verbesserung des Entwicklungsprozesses und Verbesserung der
Software bzw. ihrer Auslieferung, und dieser Ausgleich wird dauerhaft
etabliert. Dazu gilt:

- **Alles ist revidierbar.** Signale, Ausgleichsregeln und Maßnahmen werden selbst
  überprüft und sind umkehrbar. Sie passen sich an veränderte Rahmenbedingungen
  an. Die Anpassung leistet ein LLM, keine starre Formel.
- **Mehr Schleifen stabilisieren, bis zu einem Grad.** Weitere Regelkreise sind
  erwünscht, soweit sie das System stabilisieren. Die Grenze muss das System
  selbst ziehen.
- **Fehlende Signale schließt ein Regelkreis selbst.** Beispiel: Es gibt kein
  Merkmal, ob ein Bug ein Folgefehler oder neu entdeckt ist. Das soll in einem
  Regelkreis auffallen und dazu führen, dass das Merkmal eingeführt und künftig
  ausgewertet wird. Dieses Beispiel ist Abnahmekriterium (§10, A6).

## 2. Owner-Entscheidungen

- **DECISION 2026-10-12 owner:** dev-process-Releases, die ausschließlich einen
  neuen, standardmäßig *ausgeschalteten* Mechanismus hinter einem Flag
  bringen, dürfen ohne Einzelfreigabe erscheinen — nach Gates, voller Suite und
  unabhängigem Review. Alles, was Verhalten ändert, bleibt beim Owner. Umsetzung
  siehe §9 Befund 2: Die Entscheidung wird erst ausübbar, wenn die
  Inert-Grenze (P6) steht.
- **DECISION 2026-10-12 owner:** Der dev-process-Agent startet täglich per
  Routine, arbeitet aber nur, wenn ein offenes `optimization`-Issue wartet.
  Jeder Lauf zählt zum Optimierungsbudget.
- **DECISION 2026-10-12 owner:** **Wert** heißt: Ein neues Feature ist
  *tatsächlich nutzbar*, oder ein störender Fehler ist *schnell behoben*.
  Features stecken oft hinter Epics. Der Wert wird deshalb auf Epic-Ebene
  gemessen, nicht pro Einzel-Issue.
- **DECISION 2026-10-12 owner:** Ein projektseitiges Host-Skript, das
  aggregierte Betriebsdaten liefert, ist zulässig. Es liefert nur Zählwerte je
  Ereignisklasse, keine Rohlogs.
- **DECISION 2026-10-12 owner:** Der Plan schreibt keine festen Modelle vor.
  Jede Schleife und jede Prüfung muss mit Claude oder Codex ausführbar sein
  (§6.7).

## 3. Grundgedanke

Der Kreislauf startet beim **Messen von Verlust und Wert**, nicht bei einem
Mechanismus. Welcher Mechanismus zuerst gebaut wird, entscheiden die Daten des
Projekts. Darum entfällt `scoped-handover` als vorab gewählter erster
Mechanismus (Codex Befund 10).

Das System hat drei Schichten:

| Schicht | Takt | Wer | Darf ändern |
|---|---|---|---|
| Messung | laufend, deterministisch | Skripte | nichts (nur lesen und berechnen) |
| Arbeitsschleife | wöchentlich | Steward-Sitzung (LLM) | Hebel wählen, Experiment vorschlagen bzw. stoppen; innerhalb der Regeln |
| Meta-Schleife | monatlich | frische LLM-Sitzung, bei Rahmenänderung zusätzlich eine unabhängige Prüfsitzung (§6.7) | Regeln, Signale und Schleifen vorschlagen; Anwendung nach Rechte-Tabelle §7 |

Die Schichten sind getrennt, weil eine Schleife ihren eigenen Maßstab nicht
während der Messung verschieben darf (Codex Befund 1).

## 4. Messung

### 4.1 Verlustbuch — `process_kpis.py losses [--since] [--json]`

Das Verlustbuch rechnet Kapazitätsverluste in eine gemeinsame Währung um:
**Stunden**. Agentenzeit und Owner-Zeit werden getrennt ausgewiesen, weil eine
Owner-Minute knapper ist als eine Agenten-Minute.

| Klasse | Quelle (vorhandener Owner) | Datenqualität |
|---|---|---|
| Warten (Gate, Zug, Review-Warteschlange) | `train-phases`, `flow` | measured / estimated |
| Nacharbeit (Review-Runden ab Runde 2) | `rounds`, Journal-REVIEW-Zeilen | measured |
| Folgefehler (Regression-Fixes) | `Regression-of`-Trailer, Herkunftsmerkmal (§6.4) | measured, sobald Abdeckung erreicht |
| Abbrüche (Zug-Rauswurf, verworfene Branches) | `train.py phases.jsonl`, Reports | measured |
| Tokens | `issue_token_coverage` | measured / estimated mit Abdeckung |
| Owner-Eingriffe | DECISION-Zeilen, Eskalationen | count; Minuten estimated |

Jede Zeile trägt Belegzahl und Datenqualität. Bei Qualität `missing` wird nie
null angenommen. Die Zuordnung zum Issue läuft über Branch bzw. Worker und
nutzt die v2.67-Fallbacks der Reports. Das Verlustbuch erweitert
`process_kpis.py`; ein zweiter Leser entsteht nicht (Codex Befund 5).

### 4.2 Wertsignale — `process_kpis.py outcomes [--json]`

- **O1 Epic nutzbar.** Ein Epic ist ein Issue mit nativen Sub-Issues.
  Als Fallback dient ein konfigurierbarer Titelpräfix oder ein Label, denn
  Projekte sind dort nicht einheitlich. „Nutzbar“ ist konfigurierbar, und zwar
  als `epic-closed` oder als `acceptance:<label|titelmuster>`. Viele Epics
  haben ein eigenes Abnahme-Issue, dann ist dessen Abschluss der Zeitpunkt.
  Kennzahlen:
  - Durchsatz geschlossener Sub-Issues pro Woche je Epic;
  - Zeit vom Epic-Start bis „nutzbar“;
  - Alter offener Epics.
- **O2 Störender Fehler schnell behoben.** Erfasst werden Bugs mit Herkunft
  `operator` (§6.4). Gemessen wird die Zeit von der Meldung bis zum
  ausgelieferten Fix. Endpunkt ist Deploy, falls konfiguriert, sonst Merge.
  Die Kennzeichnung übernimmt die v2.68-Logik von `flow`.
- **O3 Betrieb (optional).** Ein projektseitiges Host-Skript schreibt
  `.process-work/ops/YYYY-MM-DD.json` (Schema im Template): Zählwerte je
  Ereignisklasse, Deploy- und Rollback-Ereignisse, Health-Ausfälle. Das
  Template liefert Schema und Leser, das Skript gehört dem Projekt.
- **Anteil.** `share` gibt es schon. Daraus wird der Prozessanteil an der
  gesamten Lieferarbeit berechnet.

### 4.3 Maßstab bleibt fest

Metrikdefinitionen, Evaluator-Code und Grundgesamtheiten sind versioniert. Ein
Experiment bindet sich an eine Version (§8.2). Eine geänderte Signaldefinition
läuft **eine Periode parallel** zur alten. Beide Werte erscheinen im Bericht,
erst danach gilt die neue.

## 5. Ausgleichsregeln

Die Regeln sind **Daten** im Register (§6.1). Jede Regel hat eine Prognose,
ein Prüfdatum und eine Historie. Die Startwerte sind Vorschläge, die die
Meta-Schleife überprüft:

- **R1 Budget.** Optimierungskapazität = clamp(5 %, 20 %, k × Prozessverlustanteil) der
  Agentenkapazität, Start k = 0,5. Owner-Zeit für Optimierung ist eigens
  begrenzt (Start: 30 min/Woche).
- **R2 Rückzahlung.** Ein Experiment startet nur, wenn es seine Kosten
  voraussichtlich innerhalb von **≤ 4 Wochen** zurückzahlt. Kosten sind
  Entwurf, Evaluation, Review, Release und Betrieb. Die Rückzahlung bemisst
  sich an eingesparten Verluststunden.
- **R3 WIP 1.** Höchstens ein Live-Versuch pro Projekt. Das ist in v2.68 schon
  durchgesetzt (`_conflicts`).
- **R4 Produktvorrang.** Verschlechtern sich O1 oder O2 zwei Perioden lang und
  erklärt der Prozessverlust das nicht, fällt das Budget auf das Minimum. Die
  Arbeitsschleife meldet das dann als Produktsignal, nicht als
  Prozessproblem.
- **R5 Untergrenzen.** Qualität, Sicherheit, Review-Unabhängigkeit und Abnahme
  sind nicht verrechenbar. Kein Effizienzgewinn wiegt eine Verletzung auf. Ist
  eine Untergrenze nicht prüfbar, findet keine Übernahme statt.
- **R6 Verfall.** Jede Regel hat ein `review_by`. Eine abgelaufene Regel fällt
  auf den konservativen Startwert zurück und erscheint im Bericht.

**Vertrauensmaß.** Für jede Regeländerung und jedes Experiment wird
festgehalten, wie Prognose und Ist zueinander standen (Trefferquote je
Akteur). Liegt die Quote über einer Schwelle, darf der Steward mehr allein
entscheiden. Liegt sie darunter, entscheidet er weniger allein. Das geschieht
nur innerhalb der Grenzen, die der Owner setzt.

## 6. Register und Schleifen

### 6.1 Register — `docs/process/improvement.local.json`

Eine Datei mit vier Abschnitten:

| Abschnitt | Inhalt |
|---|---|
| `signals` | Definition und Version |
| `rules` | Ausgleichsregeln |
| `loops` | Schleifen-Register |
| `questions` | Fragen-Register |

Jeder Eintrag trägt `id`, `version`, `prognosis`, `review_by` und `owner`.

Geändert wird nur über `optimize.py register set|revert|check`. Der Befehl
validiert streng: doppelte Schlüssel werden abgelehnt, ungültige Zahlen
ebenfalls. Jede Änderung hängt eine Zeile an
`.process-work/optimizations/register.log.jsonl` an: alt, neu, Begründung,
Prognose, Akteur. `revert <id>` stellt die Vorversion wieder her. Eine
Umkehrung kostet so einen Befehl. Die Datei ist in `.copier-answers`-
Updates projekteigen, wie das Mandat.

### 6.2 Arbeitsschleife (wöchentlich)

- **Auslöser:** Routine bzw. Steward-Sitzung, Auftrag
  `docs/process/improvement-weekly.md`.
- **Ziel:** größter Hebel nach Verlustbuch × R2.
- **Prüfung:** die Prognose des Vorwochen-Hebels gegen das Ist.
- **Abbruchregel:** kein Hebel über R2 → Bericht „kein Eingriff“, fertig.
- **Gedächtnis:** `.process-work/improvement/YYYY-Www.md` und das Register-Log.

Ergebnis ist eine von drei Möglichkeiten:

1. Ein Experimentvorschlag (`optimize.py new`).
2. Der Stopp eines laufenden Versuchs.
3. „Kein Eingriff“.

Auch ein Produktsignal nach R4 ist möglich. Das ist dann ein Issue für die
Lieferarbeit, kein Prozess-Experiment.

### 6.3 Meta-Schleife (monatlich)

Auftrag: `docs/process/improvement-monthly.md`. Die Schleife prüft:

- **Signale:** Trägt jedes Signal noch? Gibt es Abdeckung, Streuung,
  Manipulierbarkeit?
- **Regeln:** Wie stehen Prognose und Ist zueinander, gilt das Prüfdatum noch?
- **Maßnahmen:** Hält eine übernommene Maßnahme noch, wenn sich Modell,
  Harness oder Projektphase geändert haben? Gegebenenfalls schlägt die
  Schleife eine Ablation vor.
- **Schleifen-Register:** siehe §6.6.

Sie schreibt Vorschläge als Register-Änderungen mit Prognose. Die Anwendung
regelt §7. Ändert ein Vorschlag den **Rahmen**, prüft ihn vor der Anwendung
eine unabhängige Prüfsitzung (§6.7). Rahmen sind:

- die Spannen in R1;
- die Untergrenzen R5;
- die Evaluator-Version;
- die Rechte-Tabelle.

### 6.4 Folgefehler-Schleife und Herkunftsmerkmal

Herkunft eines Bugs, ein Wert pro Issue:

- `origin:regression` (zusätzlich `Regression-of: #N`, den es seit v2.67 gibt);
- `origin:discovered` (vorhandener Fehler, neu gefunden);
- `origin:operator` (vom Owner im Betrieb bemerkt).

Gesetzt wird die Herkunft dort, wo sie bekannt ist:

- Ein Agent, der einen Folgefehler anlegt, setzt `regression`.
- Die Steward-Sitzung setzt `operator`, wenn der Owner einen Fehler im Chat
  meldet.

Das GitHub-Konto des Autors trennt die Fälle nicht, wenn alle Issues über
dasselbe Konto entstehen. Kennzahl: Folgefehler je gemergtem Issue, getrennt
nach Tier, plus die Zeit bis zur Entdeckung. Ein fehlender Trailer zählt nicht
als null Defekte. Stichproben gleichen ab (Codex Befund 5).

### 6.5 Blinde-Flecken-Schleife

Das ist die Antwort auf „fehlende Signale schließt ein Regelkreis selbst“. Das
Fragen-Register hält fest, welche Frage jede Schleife beantwortet braucht und
welches Feld sie liefert. Beispiel: „Anteil Folgefehler?“ ← `origin:*`.

- **Abdeckung messen.** `optimize.py register check` berechnet je Frage, wie
  viele der relevanten Elemente das Feld tragen. Elemente sind neue Bugs der
  Periode. Liegt die Abdeckung unter dem Ziel, ist das ein blinder Fleck.
- **Unbekannte Fragen finden.** Die Arbeitsschleife liest eine Stichprobe
  neuer Issues, Commits und Journalzeilen (LLM). Sie sucht nach
  wiederkehrenden Freitext-Mustern, die eine Dimension tragen, für die es kein
  Feld gibt. Beispiele sind „follow-up of #N“, „after deploy of #N“ und
  „review residuals“. Fund → neue Frage mit Feldvorschlag und Prognose, wofür
  die Antwort gebraucht wird.
- **Label-Hygiene.** Zwei Label-Familien für dieselbe Dimension werden
  gemeldet, ebenso Pflichtfelder, die in der Praxis fehlen.
- **Eskalationsleiter.** Jede Stufe folgt erst, wenn die Abdeckung zwei
  Perioden unter Ziel lag:
  1. Hinweis im Issue-Template bzw. Steward-Auftrag;
  2. Pflichtfeld im Issue-Helfer des Projekts;
  3. weiche Notiz in `check_issues.py`;
  4. hartes Gate. Stufe 4 entscheidet der Owner.
- **Rückbau.** Wertet keine Schleife ein Feld drei Perioden lang aus, schlägt
  die Schleife vor, es zu entfernen.

### 6.6 Kostenschleife und Sättigung

- **Kosten.** Gezählt werden die Kosten der Verbesserungsmaschine selbst:
  Routine-Läufe, Evaluationen, Reviews, Owner-Minuten. Sie laufen in das
  R1-Budget ein, wobei Läufe ohne Arbeit mitzählen. Ist das Budget erschöpft,
  laufen Routinen bis zur nächsten Periode nur noch als billiger Vorab-Check.
- **Sättigung.** Jede Schleife im Register hat ein Gesundheitsmaß:
  - Entscheidungen pro Periode;
  - Prognose-Trefferquote;
  - Kosten.

  Drei Perioden ohne Entscheidung → die Schleife pausiert (die Meta-Schleife
  schlägt es vor). Eine neue Schleife entsteht nur, wenn ein Verlust oder eine
  Frage im Register nachweislich unabgedeckt ist. Die Obergrenze für aktive
  Schleifen ist eine Regel (Start: 6). So zieht das System die Grenze „bis zu
  einem gewissen Grad“ selbst und belegt sie.

Startbestand im Schleifen-Register:

1. Arbeitsschleife
2. Meta-Schleife
3. Folgefehler-Schleife
4. Blinde-Flecken-Schleife
5. Kostenschleife
6. Ergebnisschleife (O1/O2 → R4)

### 6.7 Wer die Schleifen ausführt

Der Plan legt kein Modell fest. Jede Schleife muss mit jedem unterstützten
Harness laufen, mindestens mit Claude Code und Codex.

- **Aufträge harness-neutral.** Die Aufträge liegen als harness-neutrale
  Dokumente unter `docs/process/`: `improvement-weekly.md`,
  `improvement-monthly.md` und der Prüfauftrag. Die Harness-Adapter
  (`.claude/commands/`, `AGENTS.md`) verweisen nur darauf, wie bei den
  übrigen Prozessbefehlen. Ergebnisse sind Dateien und Register-Befehle, keine
  harness-spezifischen Werkzeuge.
- **Unabhängigkeit über die Sitzung.** Eine unabhängige Prüfsitzung ist eine
  andere Sitzung als die vorschlagende, ohne deren Gesprächsverlauf. Sie
  bekommt nur Register, Berichte und Belege. Welches Modell und welcher
  Harness prüfen, ist Projektkonfiguration im Mandat (`reviewers`), nicht Teil
  des Prozesses. Eine andere Modellfamilie als der Vorschlagende ist empfohlen,
  wo verfügbar, aber nicht vorgeschrieben.
- **Akteur im Log.** Das Register-Log hält Harness und Modell jedes Akteurs
  fest. So kann die Meta-Schleife Prognose-Trefferquoten je Ausführer
  vergleichen, wenn das Projekt mehrere nutzt.

## 7. Rechte

| Änderung | Steward allein | Owner |
|---|---|---|
| Experiment vorschlagen, stoppen | ✓ | — |
| Übernahme nach `pass` | nur wenn `steward_may` es erlaubt und der Evaluator gebunden ist (§8.2) | sonst |
| Signal oder Regel innerhalb der Rahmen-Spannen | ✓, mit Prognose und `review_by`; umkehrbar | sieht es im Monatsbericht |
| Feld/Label Eskalationsstufe 1–3 | ✓ | — |
| Rahmen (Spannen, R5, Evaluator, diese Tabelle), Stufe 4, Gates, Tiers | — | ✓, nach unabhängiger Prüfsitzung (§6.7) |
| Ablation geschützter Kontrollen (Sicherheit, Tier, Review-Unabhängigkeit, Abnahme) | — | nie per Optimierungsmandat |

## 8. Experimente (Korrekturen am v2.67-Lebenszyklus)

### 8.1 Evidenz, die ein Projekt liefern kann

Live-A/B-Tests für kleine Effekte sind auf Projektebene nicht erreichbar. Bei
einem Variationskoeffizienten von 1 braucht ein 20-%-Effekt rund 390 Issues
pro Arm (Codex Befund 4). Deshalb:

- **Primär Ereignisraten mit vielen Fällen**, etwa der Anteil der
  Reviews, die in Runde 1 blockieren. Ein solcher Anteil reagiert innerhalb
  von Wochen, weil jedes Issue eine Beobachtung liefert.
- **Gepaarter Offline-Screen** für Mechanismen, die Agentenverhalten ändern:
  - 8–12 Aufgaben einer Klasse;
  - Prä-Fix-Snapshot, exportiert ohne künftige Git-Objekte, Pläne und
    Erinnerungen;
  - private Abnahmetests außerhalb des Schreibzugriffs;
  - Nachweis fail-before/pass-after mit dem historischen Patch;
  - 2–3 Durchläufe, zufällige Reihenfolge.

  Der Screen dient dem Aussortieren, er beweist nichts (Codex Befund 6).
- **Eine geplante Endauswertung**, keine wiederholten Blicke.
  `inconclusive` ist ein gültiges Ergebnis und behält die Baseline.

### 8.2 Evaluator-Bindung

Die Kriterien stehen als strikt geparster ```` ```json ````-Block in
`## Criteria`, eingefroren mit dem Rest. Sie enthalten:

- primäre Metrik, Richtung, Schwelle;
- Untergrenzen;
- Grundgesamtheit;
- Evaluator-Version (dev-process-Tag);
- Datensatz-Hash.

`optimize.py evaluate` schreibt das Ergebnis mit Bindung: Candidate-/Base-SHA,
Terms-Hash, Evaluator-Version, Manifest der Rohläufe. `move … adopted` prüft
die Bindung und rechnet neu. Ein beschreibbares `pass`-Feld genügt nicht.
Kandidaten dürfen Messpfade nicht verändern: `process_kpis.py`, `optimize.py`,
`check_*`, Testauswahl und deren Tests. Die Pfadliste wird aus dem
**Basis-Tag** geladen, nicht aus der Kandidaten-Revision. Eine
JSON-Record-Migration (früher D5) wird zurückgestellt. Sie beseitigt das
Manipulationsrisiko nicht und kostet eine Migration.

### 8.3 Zuteilung

Die Paritätsauswahl wird ersetzt. Die Zuteilung nimmt einen Hash aus
Issue-Nummer und einem Salz, das beim Freeze festgelegt wird, geblockt nach
Tier. Für jedes Issue wird die Zuteilung **einmal vor Arbeitsbeginn**
persistiert, getrennt von der tatsächlichen Exposition (Abbruch, Fehler,
Abweichung). Ausgewertet werden alle zugeteilten Issues. Nicht zulässige
Issues sind keine Kontrollen.

### 8.4 Übernahme bleibt erhalten

`adopted` trägt einen Eintrag in `optimization.local.json → adopted[]` ein
(`flag`, `record`, `terms_hash`). Für solche Flags meldet `active()` „on
(adopted OPT-n)“. Der Pilot-Sinn von `active()` bleibt davon getrennt.
Rückbau heißt: Eintrag entfernen und den Record nach `rolled-back` setzen.
Ein Test prüft das Verhalten **nach** der Übernahme (Codex Befund 7). Eine
globale Default-Änderung im Template bleibt eine Owner-Entscheidung.

## 9. Antwort auf die Codex-Befunde

| # | Befund | Antwort |
|---|---|---|
| 1 | Experiment kann den Maßstab ändern | §8.2 Bindung und geschützte Messpfade aus dem Basis-Tag; §7 verbietet Ablation geschützter Kontrollen; R5: nicht prüfbare Untergrenze → keine Übernahme |
| 2 | „Flag aus, verhaltensneutral“ nicht definiert | Tupel-Wahrheitswert behoben (`Activation`, 0557b2e). Autonome Releases erst nach P6: Inert-Grenze (allowlisted, lazy geladene Payload-Pfade), Policy aus dem Vortag, Negativtests (Tupel-Mutant, Import vor Guard, kein/abgelaufenes Mandat, Telemetrie aus). Die Einrichtung der Grenze ist selbst ein Owner-Release |
| 3 | Parität ist keine Zufallszuteilung; Überlappung | Überlappung behoben (ein Live-Versuch pro Projekt, 0557b2e); §8.3 Zuteilung |
| 4 | Pass-Regel, n, wiederholte Blicke | §8.1: Ereignisraten, eine Endauswertung, `inconclusive` legitim, keine Multimetrik-Suche |
| 5 | `flow` meldet Unvollständiges als gemessen | Behoben in 0557b2e: Token-Abdeckung je Feld, `endpoint` deploy/merge, `deployed=false` → failed, Escape-Fenster ab Deploy. Defekte per Stichprobe abgleichen (§6.4) |
| 6 | Worktrees isolieren nicht | §8.1: Export ohne künftige Objekte, private Tests, fail-before/pass-after; nur Screening |
| 7 | Übernahme geht verloren | §8.4 |
| 8 | Upstream-Kanal unzuverlässig, Exportgrenze | P7, nachrangig: konfiguriertes Ziel statt `_src_path`; Umschlag mit Allowlist nur aggregierter Zahlen; Idempotenzschlüssel `OPT-id + terms_hash`; vor dem Senden nach Marker suchen; Import nur als Daten, mit Compare-and-Swap auf die Revision |
| 9 | Routine ohne Budget/Lease | P7: Vorab-Check ohne LLM, Lease mit Ablauf, Versuchszähler, Grabsteine für abgelehnte Signale (erneut nur bei neuer Evidenz), Kosten in §6.6 |
| 10 | Handover-Paket unterspezifiziert | `scoped-handover` ist nicht mehr gesetzt. Kommt es aus den Daten, gilt Codex' Paketschema als Eingangsbedingung |

Gestrichen bzw. zurückgestellt (Codex Frage 5):

- Fünf-Signal-Autodetektor (ersetzt durch Verlustbuch und wöchentliches LLM);
- sequentielle und Multimetrik-Statistik;
- universeller Neutralitätsprüfer;
- Benchmark-Fabrik;
- JSON-Records;
- Topologiesuche.

## 10. Abnahme (EARS)

- **A1** When `process_kpis.py losses` runs, the system shall report each loss
  class in hours with evidence count and data quality, and shall never report
  a `missing` class as zero.
- **A2** When `process_kpis.py outcomes` runs on a repository with native
  sub-issues, the system shall report per epic the closed-sub-issue rate, the
  time to the configured usable marker, and the age of open epics.
- **A3** When a register entry changes, the system shall append old value, new
  value, reason, prognosis and actor to the register log, and `revert` shall
  restore the previous version.
- **A4** When an entry's `review_by` passes, the system shall fall back to the
  conservative default and list it in the next report.
- **A5** When a signal definition changes, the system shall report the old and
  new values side by side for one period before the new one applies.
- **A6 (Herkunft, Beispiel des Owners)**
  - When fewer than the target share of new bugs in a period carry an origin
    field, the weekly loop shall record a blind spot in the question register
    and propose the issue-template field.
  - While coverage stays below target for two periods, the monthly loop shall
    propose the next escalation step.
  - Once coverage reaches target, `losses` shall report the regression share
    with quality `measured`.
- **A7** When the weekly loop finds a recurring free-text pattern that encodes
  a dimension no field carries, it shall add a question with a field proposal
  and prognosis.
- **A8** When a loop records no decision for three periods, the monthly loop
  shall propose pausing it. The system shall reject a new loop that names no
  uncovered loss or question.
- **A9** When an experiment is adopted, `active()` shall report it on outside
  any pilot window. When the adoption is rolled back, `active()` shall report
  it off.
- **A10** When `move … adopted` runs, the system shall recompute the result
  from the bound evaluator version and raw-run manifest, and shall refuse if a
  candidate changed a protected measurement path.
- **A11** If O1 or O2 worsens for two periods without a matching process loss,
  then the system shall set the optimization budget to its minimum and report
  a product signal.
- **A12** When the improvement machinery's own cost exceeds the R1 budget, the
  routines shall run only their cheap preflight until the next period.

## 11. Pakete und Reihenfolge

Die Reihenfolge folgt dem schnellen Nutzen. P1 bis P3 liefern ab der ersten
Woche Erkenntnisse, ohne dass ein Experiment läuft.

| Paket | Inhalt | Nutzen ab |
|---|---|---|
| P1 | `losses`, `outcomes`, Ops-Schema (nur lesend) | Woche 1 |
| P2 | Register + `optimize.py register`, Startbestand Schleifen, Regeln, Fragen; Herkunftsmerkmal als erste Frage | Woche 1 |
| P3 | Aufträge wöchentlich und monatlich, Berichtsformat | Woche 2 |
| P4 | Lebenszyklus: §8.2–8.4 | vor dem ersten Live-Versuch |
| P5 | Offline-Screen (minimal, §8.1) | wenn ein Mechanismus Agentenverhalten ändert |
| P6 | Inert-Grenze für autonome Flag-aus-Releases | danach |
| P7 | Upstream-Kanal und Routine-Lease | wenn P1–P4 zwei bis vier Wochen gelaufen sind |

v2.68 enthält P1–P4. P5–P7 folgen als eigene Releases, sobald die Daten den
Bedarf zeigen.

## 12. Offen

**An die Refutation (nur der neue Teil, §4–§8):**

1. **Selbstreferenz.** Kann die Meta-Schleife über Regeländerungen innerhalb
   der Spannen ihren eigenen Maßstab verschieben? Ein Beispiel wäre, R4 so
   anzupassen, dass Produktsignale nie greifen. Reichen die Rahmen-Spannen und
   der Prognose-Ist-Abgleich?
2. **Goodhart im Verlustbuch.** Lassen sich Verluststunden durch
   Umklassifizieren oder Issue-Splitting senken, ohne dass die Lieferung
   besser wird? Bindet O1 auf Epic-Ebene das ausreichend?
3. **Freitext-Muster.** Ist die LLM-Suche nach Freitext-Mustern (A7) als
   Entdecker blinder Flecken tragfähig, oder erzeugt sie Rauschen und Feldflut?
   Reicht der Rückbau nach drei Perioden?
4. **Sättigung.** Sind „drei leere Perioden“ und eine feste Obergrenze ein
   sinnvoller Sättigungsmechanismus? Oder braucht es ein Maß dafür, ob eine
   Schleife stabilisiert?
5. **Schwankung.** Ist die Budgetformel R1 robust gegen schwankende Daten in
   kleinen Projekten, oder braucht sie Glättung bzw. Hysterese?
