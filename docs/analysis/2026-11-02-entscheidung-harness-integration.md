# Entscheidungsvorlage: Harness-Integration und Telemetrie — was gehört ins Template?

Datum: 2026-11-02 · Bezug: #358 (Issue), #359 (Plan Telemetrie an einer Stelle), #357 (KPI-Analyse), #356 (Schritt-KPIs der anderen Sitzung)

Stand: Vorlage für den Owner. Die Umsetzung bereitet die Hauptsitzung „dev-process optimierung“ vor.

## Anlass

Der Owner will die gesamte Prozess-Telemetrie an einer Stelle haben, auswerten und darauf reagieren. Dazu kommen drei Wünsche:

- quasi beliebige Abfolgen von Modellen (cross-model), auch über opencode, konfigurierbar in einer lokalen Policy
- Betrieb mit einem, zwei oder drei verfügbaren Harnessen
- sehen können, was ein vergebener Job in Codex oder opencode tut, über Cloud-, Server- und Desktop-Hosts hinweg

Der erste Entwurf (Option A, unten) hätte das alles ins Template gebaut. Der Owner hat die Sorge geäußert, dass sich das Template damit vom Grundgedanken entfernt: Harness installieren und den Prozess nutzen.

## Befunde, auf die sich die Vorlage stützt

Alle Befunde sind am 2026-11-01/02 erhoben, mit Fundort:

- **Das Cockpit misst in Kenni falsch** (#357 Abschnitt 10, #358):
  - Die Population geht über Fuchs-Merges verloren: hinter `0ffca6aab` liegen 1.430 Commits und 87 Train-Merges, die das Cockpit nicht sieht.
  - `losses` meldet `confidence: high (n=93)` bei 0 befüllten Werten.
  - 79 statt 139 Blocker-Zeilen gelesen.
- **Tokens fehlen strukturell:**
  - Codex wird ohne `--json` aufgerufen, Tokens kommen nie an.
  - Claude liefert Tokens nur über den optionalen `transcripts`-Pfad, in Kenni nicht gesetzt.
  - opencode läuft in Kenni an `dispatch.py` vorbei (`kenni-tooling`, ADR-0088).
- **opencode v2.2.5** (`@opencode/cli`), lokal getestet über Melious mit `deepseek-v4.1-flash`:
  - `--variant` wird abgelehnt; der Effort steht als `-m provider/model#variant` im Modellnamen. Eine unbekannte Variante übernimmt opencode ohne Warnung.
  - Ein offenes stdin lässt den Lauf hängen.
  - `--format json` liefert je `step_finish` die Kosten (`cost`) und die Tokens (`tokens{input,output,reasoning,cache}`).
  - Rechte stehen als geordnete Liste `permissions[]`. Ohne eigene Konfiguration ist alles erlaubt außer `.env`. Die Konfiguration „alles verbieten, dann `read`/`grep`/`glob` erlauben“ hielt im Test: kein Schreibwerkzeug, Datei unverändert.
  - `"reasoning": true` in der Modelldefinition (empfohlen in `verification-independence.md:103-105`) verwirft v2 als „unsupported legacy setting“.
- **Codex 0.166.0:**
  - `codex app-server` bietet `turn/steer`, `turn/interrupt` und `thread/tokenUsage/updated`. Die CLI markiert ihn als „[experimental]“.
  - `exec --json` gibt es, das Template nutzt es nicht.
- **Größe heute:** `dispatch.py` hat 3.115 Zeilen, `_dispatch_codex.py` 849. Option A hätte für Phase 0–2 geschätzt 3.000–4.000 Produkt- und ebenso viele Testzeilen bedeutet, über 6–8 Releases, mehrere davon Tier 3.

## Optionen

| | A: alles im Template | B: Kern und Vertrag im Template, Integration als Tooling | **B+ (Empfehlung)** |
|---|---|---|---|
| Treiber (Codex app-server, opencode-Server), Abfolgen, Panels, Hosts, Live-Ansicht | Template | Tooling | Tooling |
| Telemetrie-Vertrag über `report.py` | Template | Template | Template, **mit Version und Schema, Herkunftsfeld und Pflicht-KPI Abdeckung** |
| Phasenzeiten | aus dem Treiber | aus Reports | **soweit möglich aus Git** (Plan-, Attest-, Merge-Commits), Reports ergänzen |
| Automatische Meldung | Treiber | Hook oder Anweisung | Claude-Hook als Referenz, sonst Anweisung; Selbstauskunft wird als solche markiert |
| `dispatch.py` | ausbauen | einfrieren | **stabile Fassade** mit Standard-Backend (eingefroren) und Weiterreichen an ein externes Backend |
| Codex-Selbstattestierung (`handoff`) | bleibt | bleibt | geht ins Tooling, das `attest.py` aufruft |
| Aufwand im Template | 6–8 Releases, Tier 3 | 2–3 kleine Releases | 2–3 kleine Releases (Tier 2) |

## Zweitmeinungen

Über Melious mit derselben Frage gestellt (Text: siehe Anhang). Beide Modelle stammen aus anderen Familien als Claude.

- **`deepseek-v4.1-flash`:**
  - Option B ist richtig, aber als „B+“.
  - Ein Vertrag plus „bitte melden“ erzeugt einen Bias durch fehlende Daten: Abbrüche melden nicht. Daher Abdeckung als Pflicht-KPI.
  - Die Herkunft muss stimmen: Tokens und Attestierungen schreibt der Läufer oder ein Hook, nie das Modell selbst.
  - `dispatch.py` einfrieren und als veraltet markieren, später abtrennen. Die Codex-Selbstattestierung herauslösen.
  - Der Vertrag braucht Version, Schema und Contract-Tests.
- **`glm-5.3`:**
  - Option B ist die einzig saubere Trennung von Regeln und Ausführung.
  - Phasenzeiten aus eigenen Daten wie Git ableiten; Tokens nur „best effort“.
  - Fehlende Telemetrie soll Konsequenzen haben (als `FINDING`).
  - `dispatch.py` auf einen dünnen Referenz-Treiber verkleinern.
  - Codex-Selbstattestierung ins Tooling.
  - Fixtures gegen Versionswechsel der CLIs festhalten.

**Bewertung dieser Sitzung:**

- **Übernommen:** Herkunftsfeld, Abdeckung als Pflicht-KPI, Phasenzeiten aus Git, Vertrag mit Version, Fixtures, Codex-`handoff` ins Tooling.
- **Nicht übernommen:**
  - Fehlende Telemetrie als Gate- oder FINDING-Konsequenz. Das würde neue Prozesslast bringen (Regel-Budget, `optimization.md`). Gegenvorschlag: Abdeckung als DoD-Punkt im Review mit begründeter Abweichung. Das entscheidet der Owner (E3).
  - `dispatch.py` auf einen Referenz-Treiber umbauen. Das wäre selbst ein großer Umbau. Als Referenz für den Vertrag dient der Claude-Hook.
- **Schon vorhanden:** „Cross-model fail-closed“ (DeepSeek). `attest_evidence` verlangt ab `cross_model_from_tier` `cross-model` oder einen festgehaltenen Skip.

## Steward und Backend

Heute steuert der Steward alles über `dispatch.py`: `policy`, `start`, `log`, `say`, `stop`. Lagebild und Weckruf kommen aus `tower.py --json/--wait/--remote` (`.claude/commands/steward.md`, „Channel“, „Loop“).

Künftig gilt:

1. **`dispatch.py` bleibt die Fassade.** Die Verben und die Phasenkette (nach `planned` das Plan-Review, nach dem Pass Execute, nach dem Review der Train) bleiben Kern; das ist Prozesslogik. Der Steward-Befehl ändert sich nicht.
2. **Das Backend ist wählbar.**
   - **Standard:** der heutige einfache Weg. Je Policy-Zelle ein CLI (detached oder tmux), mit `log`, `say` und `stop`. Eingefroren: Fehlerkorrekturen ja, neue Läufer nein.
   - **Extern:** In der Policy steht `"backend": "<befehl>"`. `dispatch.py` reicht `start`, `log`, `say` und `stop` als kleine JSON-Aufrufe weiter. Das externe Backend muss über `report.py` melden (Vertrag).
3. **Der Tower bleibt unverändert.** Er liest Reports, Git und Pläne. Jedes vertragstreue Backend erscheint dort.
4. **Ohne Orchestrierung** öffnet der Owner seine Sitzungen selbst. Der Steward liest den Tower und gibt Entscheidungen über Plan-Zeilen weiter; das ist der heutige Weg ohne Kanal, nur über Reports. Die KPIs kommen dann aus Git und dem Hook.

Für Kenni heißt das: `kenni-tooling` (opencode) wird das externe Backend des Kenni-Stewards. Damit erscheinen die opencode-Läufe in `tower`, `log` und den KPIs.

## Was im Template umzusetzen wäre (B+)

| Paket | Inhalt | Tier | Grobe Größe |
|---|---|---|---|
| **T1** = #359 Phase A | Fuchs-Merges, Konfidenz nach befüllten Werten, Ein-Leser-Tokens (D1), Berichte ohne `work:`, Fehlgründe | 2 | wie in #359 geplant |
| **T2** Telemetrie-Vertrag | `report.py` mit Schema-Version: Zustände `started`/Ende, Phasen inkl. `plan-review`/`fix`, `model`, `runner`, `host`, `usage` (Tokens inkl. `reasoning`, `cost`), `source: hook\|runner\|self\|git`. Validierung beim Schreiben und Lesen. Abdeckung je Phase, Läufer und Herkunft als Pflichtzeile in `flow`/`works`/`losses`. Phasenzeiten aus Git, wo die Commits sie tragen | 2 | ~300–500 Zeilen + Tests |
| **T3** Claude-Hook | Adapter liefert einen Hook am Sitzungsende: `report.py` mit Tokens aus dem Transkript, `source: hook`. `AGENTS.md`/Copilot: zwei Sätze Anweisung, `source: self` | 2 | klein |
| **T4** Backend-Fassade | `"backend"` in der Policy, Weiterreichen von `start`/`log`/`say`/`stop` (JSON-Vertrag), Doku in `tower.md`/`steward.md`; Standard-Backend eingefroren | 2 | ~200–300 Zeilen + Tests |
| **T5** Doku-Korrekturen | opencode-v2-Abschnitt in `verification-independence.md`: `#variant`, stdin schließen, `permissions[]`-Format, `reasoning` entfernen. Codex-Hinweis auf `--json` | 1 | Doku |
| **T6** Codex-`handoff` | als veraltet markieren; Weg ins Tooling beschreiben (ruft `attest.py`) | 2–3 | klein, Migrationshinweis |

Neue KPIs (aus #357 fortgeschrieben). Sie werden gemessen, sobald ein Backend oder Hook sie liefert, sonst stehen sie als `missing: <grund>` da:

- angeforderter gegen tatsächlichen Läufer und Modell
- Ausweichquote
- herabgestufte Unabhängigkeit
- Ertrag je Reviewer-Familie, Linse und Panel (#316)
- Kosten in Geld
- Reasoning-Tokens
- Treiber-Fehlerquote
- Eingriffe je Arbeit
- „Effort eingehalten“
- **Abdeckung je Herkunft**

## Was ins Tooling geht (nicht Teil dieses Repos)

- Treiber für Codex `app-server` und den opencode-v2-Server (HTTP mit Ereignisstrom), jeweils mit Einmal-Aufruf als Rückfall.
- Live-Ansicht `log --follow`, Eingreifen über `send`/`interrupt`.
- Läufer-Profile, Vorzugslisten, `rounds`/`panel`, Verfügbarkeit (Version, Anmeldung, Modelle und Varianten).
- Hosts (Cloud, Server, Desktop), gemeinsame Warteschlange, Cloud-Treiber.
- Die Mitschnitte als Fixtures. Ein erster opencode-v2-Mitschnitt liegt unter `docs/analysis/fixtures/2026-11-02-opencode-v2.2.5-run.jsonl` (v2.2.5, `--format json`, read-only-Rechte, Melious `deepseek-v4.1-flash`).

## Entscheidungen für den Owner

- **E1:** Option A, B oder **B+**?
- **E2:** Eigenes Tooling-Repo (allgemein, z. B. `dev-process-tooling`), oder zunächst `kenni-tooling` als Backend und erst bei einem zweiten Projekt verallgemeinern? Empfehlung: zunächst `kenni-tooling`, Regel „im mehr als einem Einsatz belegt“ (`MAINTAINING.md`).
- **E3:** Abdeckung der Telemetrie als DoD-Punkt im Review (Empfehlung), als Gate oder FINDING (GLM), oder nur als Anzeige?
- **E4:** `dispatch.py`: Fassade plus eingefrorenes Standard-Backend (Empfehlung) oder später ganz abtrennen (DeepSeek)? Abtrennen erst, wenn das Tooling ein zweites Projekt trägt.
- **E5:** Codex-Selbstattestierung: ins Tooling verschieben (Empfehlung, beide Zweitmeinungen) oder im Template belassen?

## Reihenfolge für die Hauptsitzung

1. T1 (#359 Phase A) als nächstes Release; unabhängig von E1–E5.
2. Nach E1/E3: T2 und T3 als ein Release.
3. Nach E4: T4. T5 kann jederzeit als Doku-Release kommen.
4. T6 nach E5.
5. Kenni, Projektarbeit für den Steward und „Weiterentwicklung“:
   - `transcripts` setzen
   - `optimization.local.json` anlegen
   - `gate-triage.jsonl` beginnen
   - `Regression-of:` durchsetzen
   - opencode auf v2 heben (Rechte ins `permissions[]`-Format)
   - `kenni-tooling` meldet über `report.py` und wird nach T4 Backend
6. Nicht im Template: das Verhindern von Fuchs-Merges (Merge-Guard, Tier 3) bekommt ein eigenes Issue.

## Anhang: die gestellte Frage

> Architekturfrage zu einem Entwicklungsprozess-Template: Ausgangslage (Methodik harness-neutral, Cockpit liest Artefakte; `dispatch.py` ~3.100 Zeilen, `_dispatch_codex.py` ~850; Referenzprojekt hat Läufer ausgelagert; Tokens und Phasenzeiten fehlen). Option A (Phasen 0–3 im Template, 3.000–4.000 Zeilen, 6–8 Releases). Option B (Kern und Telemetrie-Vertrag im Template, Hooks oder Anweisung, `dispatch.py` nur gepflegt, Integration als Tooling, das `attest.py` aufruft). Fragen: richtige Grenze? Reicht Vertrag plus Hooks für belastbare KPIs? Cross-Model ohne Abfolge-Automatik? `dispatch.py` einfrieren, abtrennen oder verkleinern? Fehlende Risiken?

## Nachtrag 2026-11-02: KPI-Lücken gegen gängige Raster

Frage des Owners: Sind alle qualitativen und quantitativen KPIs der Softwareentwicklung in allen Schritten identifiziert? Antwort: nein. Der KPI-Satz deckt den Prozessfluss ab. Gegen DORA, SPACE/DevEx, Code-Gesundheit, Betrieb und Sicherheit fehlen ganze Bereiche. Ziel ist nicht „volle Telemetrie“, sondern keine blinde Entscheidung.

| Bereich | Fehlende KPI | Wofür entscheidend | Stand im Template | Aufwand |
|---|---|---|---|---|
| Betrieb (DORA) | Wiederherstellungszeit, Vorfälle je Deploy | Gegen-KPI zu allen Geschwindigkeits-KPIs | nicht gemessen (`optimization.md:24`); kein Vorfallsformat | M: Format `incident` + Leser |
| Betrieb | Fehler in Produktion (Sentry, Logs, SLOs) | Nachfehler ohne `Regression-of:` | fehlt; Kenni hat 2 Trailer | Projekt: Anbindung; Template: Leser-Schnittstelle |
| DORA | Deploy-Häufigkeit | Batchgröße, Takt des Zugs | Daten in `phases.jsonl`, keine Ausgabe | S |
| Nacharbeit | Revert-Quote, Fix-Commits je Arbeit nach dem Merge | versteckte Nachfehler | `clusters`/`cfr` nur Proxy, Reverts nicht gezählt | S (Git) |
| Review-Genauigkeit | Fehlalarme (verworfen oder widerlegt) und Übersehenes (Stichprobe bestandener Runden) | findet mehr Review mehr oder nur Lärm? | #316 teilweise; Stichprobe nur vorgeschlagen | M |
| Testqualität | Mutation-Score der geänderten Zeilen, Flaky-Quote, Suite-Dauer | fangen Tests Fehler oder laufen sie nur? | Mutation in `testing.md`/Review-Bundle, nicht gemessen; Flakes #317 | M |
| Code-Gesundheit | Trend von Komplexität und statischen Warnungen auf berührten Dateien, Churn-Hotspots | Gegen-KPI zu „schneller umsetzen“ | `size` zeigt meistberührte Dateien, keine Komplexität | M; Werkzeuge je Stack beim Projekt |
| Sicherheit | offene Schwachstellen in Abhängigkeiten, ihr Alter, Zeit bis zum Fix | Qualitätsuntergrenze | `sbom`-Modul ohne Schwachstellenprüfung | M |
| Anforderungen | Scope-Abweichung (tatsächlicher Diff gegen die im Plan genannten Dateien), nachträglich geänderte Akzeptanzkriterien | Planqualität jenseits von REPLAN | Execute vergleicht, schreibt nichts auf; `graph.py missed` | S–M |
| Prozess-Disziplin | Befolgungsquote der Pflichtzeilen (Kenni: REPLAN 13 %, ROOT-CAUSE 60 %, `origin=` 60 %, `at=` 25 %) | wirkt eine Regel oder ist sie nur Last? (Regel-Budget) | ermittelt, keine Familie im Cockpit | S |
| Agenten-spezifisch | Autonomie-Quote (ohne Eingriff), Kontext-Kompaktierungen und Neueinlesen, Werkzeugfehler | wo Agenten an Kontext oder Werkzeugen scheitern | fehlt; `rehydrate.py` wird nicht gezählt | S–M (Backend/Hook) |
| Mensch (SPACE) | Owner-Wartezeit (#319); Owner-Puls: eine Frage pro Woche („Wie belastend war der Prozess?“, 1–5) | einzige qualitative Stimme, Gegen-KPI zur Prozesslast | #319 offen, Puls fehlt | S (eine Zeile in `improvement-weekly.md`) |
| Wert | tatsächliche Nutzung gelieferter Funktionen | wird das Richtige gebaut? | `outcomes` misst „nutzbar“, nicht „genutzt“ | Projekt |

**Kandidaten für T2 (Telemetrie-Vertrag).** Ohne diese vier kann eine Optimierung Tempo gewinnen, während die Qualität unbemerkt sinkt:

1. Wiederherstellung und Vorfälle: Format und Leser
2. Review-Genauigkeit: Fehlalarme aus den Befund-Ausgängen, Übersehenes aus einer Stichprobe
3. Testqualität: Mutation-Score und Flakes, mit #317
4. Befolgungsquoten der Pflichtzeilen

Code-Gesundheit, Sicherheit, Produktionsfehler und Nutzung bekommen im Template nur einen Platz im Vertrag und einen Leser. Die Werkzeuge stellt das Projekt.

Grenzen: Die größte Lücke ist heute nicht eine fehlende KPI, sondern Daten, die vorhandene KPIs nie erreichen (Population, Tokens, Trailer, Triage). Jede neue KPI muss automatisch entstehen oder ihre Abdeckung ausweisen. Zahlen gelten nur innerhalb eines Projekts, und keine Zahl ist ein Ziel (`telemetry.md`, „honest ceiling“).
