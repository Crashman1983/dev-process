# Telemetrie an einer Stelle — erst richtig messen, dann sammeln, dann reagieren

Datum: 2026-11-02 · Issue: #358 · Analyse: PR #357 (`docs/analysis/2026-11-01-kpi-je-schritt-unabhaengig.md`, Abschnitte 1, 8, 10)

Stand: Fassung 1, vor dem Plan-Review.

Die Arbeit ist in drei gestapelte Phasen geteilt, damit die Schnittgröße klein bleibt (`plan.md`, R1 aus v2.80). Jede Phase hat ein eigenes Tier und ein eigenes Release:

| Phase | Inhalt | Tier | Release |
|---|---|---|---|
| A Messung richtig | M1, D2, D1, Befund-Join, Gründe statt Leerwerte | 2 (nur Leser) | v2.81, reines Update |
| B Eine Ablage | Host-Spuren über `refs/process/<art>/<host>` | 3 (Schreiber im Gate-Runner und Train) | v2.82 |
| C Reagieren | Schnappschuss `report --json`, Wochenlauf, Issues je Aktion | 2 | v2.83 |

Nur Phase A ist hier ausplanungsreif. B und C sind Skizzen und bekommen vor ihrer Umsetzung einen eigenen Plan-Abschnitt und ein eigenes Plan-Review.

## Anlass

Der Owner will die gesamte Prozess-Telemetrie an einer Stelle haben, auswerten und darauf reagieren. Ein Lauf von Kennis `process_kpis.py` (v2.80.0) auf Kenni `main` @ `6acc64314` zeigt, dass die Zahlen dafür noch nicht taugen:

- **M1 — Population falsch.** Kenni hat `main` in Feature-Branches gemergt und `main` danach auf sie vorgespult (`0ffca6aab chore(ios): integrate main into the completion carrier`, `b4dbb12a7 chore: integrate main for joint Apple release` u. a.). `merge_events` (`process_kpis.py:1914-1950`) läuft über `rev-list --first-parent` und folgt damit der Branch-Historie. Die Train-Merges auf der zweiten Seite fehlen: hinter `0ffca6aab` liegen 1.430 Commits und 87 Train-Merges. Für 10.10.–02.11. meldet `baseline` deshalb nur 58 Arbeiten, dazu 2.345 Commits „outside a merge range“. `load` zeigt zwei Wochen mit 0 Merges, während `share` für dieselben Wochen 1.044 und 785 Commits zählt.
- **D2 — falsche Konfidenz.** `losses` druckt `confidence: high (direct, n=93)`, obwohl Belegung, Verzögerung und Tokens bei 0 von 93 Issues befüllt sind (`process_kpis.py:2357-2359`, `confidence(n)` mit `n = t["issues"]`).
- **D1 — Tokens doppelt gezählt** (aus #356). `session_output_tokens` (`process_kpis.py:138-150`) summiert jeden Treffer von `OUTPUT_TOKENS`. `dispatch._transcript_usage` (`dispatch.py:1354`) zählt dagegen je Nachricht einmal.
- **Befund-Join.** `rounds` liest 79 Blocker; im Repository stehen 139 `sev=blocker`-Zeilen in 92 Berichten, 28 davon ohne `work:`-Kopf. Wie viel der Differenz das erklärt, ist offen `[assumption]`.
- **Leerwerte ohne Grund.** `—`/`missing` sagt nicht, ob der Wert fehlt, weil `transcripts` nicht gesetzt ist, weil der Host-Log auf diesem Checkout nicht liegt oder weil kein Trailer existiert. #356 hat daraus „fehlt in Kenni“ gelesen.

## Begriffe

- **Marker-Merge:** ein Train-Merge (`train: merge <branch>`, zwei Eltern) oder ein `finish`-Archiv-Commit. Beide Muster sind unverändert (`_TRAIN_MERGE`, `_FINISH_ARCHIVE`).
- **Fuchs-Merge:** ein Commit mit zwei Eltern auf der First-Parent-Kette, der kein Marker-Merge ist und dessen zweite Seite (`M^1..M^2`) mindestens einen Marker-Merge enthält. In ihm wurde der Integrationsbranch in einen Branch gemergt, auf den danach vorgespult wurde. Die eigentliche Historie des Integrationsbranches liegt auf der zweiten Seite.
- **Gefüllt:** ein Wert, der weder `None` noch `missing` ist. Eine 0 aus einer gelesenen Quelle zählt als gefüllt.
- **Fehlgrund:** einer aus der festen Menge `not-configured:<key>`, `no-host-log:<file>`, `no-trailer`, `git-failed`, `not-read:<module>`, `shallow`. Ein Wert hat höchstens einen.

## Aufgaben — Phase A (Tier 2)

- [ ] **A1 Fuchs-Merges** (`merge_events`). Für jeden Fuchs-Merge auf der First-Parent-Kette die zweite Seite mit `rev-list --first-parent M^2 ^M^1` nach Marker-Merges absuchen, rekursiv für Fuchs-Merges auf dieser Seite. Die Ereignisse dort zählen wie Ereignisse der Kette. Die Ereignisliste wird nach Commit-Zeit des Markers sortiert, und jedes `prev` (die Untergrenze eines `finish`-Bereichs) kommt aus dieser sortierten Liste. Ein Ereignis, das auf beiden Seiten erreichbar ist, zählt einmal (Schlüssel: SHA). Die `population`-Zeile nennt „fox merges N (events behind them M)“. Eine Arbeit, die nur über einen Fuchs-Merge gefunden wurde, behält ihre Qualität; ihr `finish`-Bereich wird `estimated`, denn die Vorspul-Grenze ist unscharf.
- [ ] **A2 Konfidenz nach gefüllten Werten.** `confidence()` bekommt `n` je Familie als Zahl der Items **mit Wert**. Betroffen sind `losses` (je Maß das Minimum über die gedruckten Maße, oder je Zeile), `flow`, `works` und `baseline`. Bei `n_filled = 0` lautet die Aktion „collect data first — <Fehlgrund>“. Die Aufrufer listet die Konsumentensuche (unten).
- [ ] **A3 Ein Transkript-Leser.** `cost` und `session_output_tokens` lesen über `dispatch._transcript_usage`. `OUTPUT_TOKENS` bleibt der Owner des Musters, die Summe ohne Deduplizierung entfällt. `finish.py`, das „die gleiche Zeile“ druckt (`telemetry.md`, `cost`), liest danach denselben Wert.
- [ ] **A4 Berichte ohne `work:`.** `_review_reports` und der Join in `rounds`/`findings` zählen sie als eigene Gruppe „(no work: header)“ mit Anzahl. Heute erscheint die Gruppe in `findings` und in der Old-Code-Zeile von `rounds`, aber nicht in den Blocker-Summen. Kein Bericht fällt still heraus; der Zähler steht im Kopf von `rounds`.
- [ ] **A5 Fehlgründe.** Ein Helfer `_missing(reason)` und eine Spalte bzw. ein Suffix `[missing: <grund>]` überall, wo heute `—`/`not measured` ohne Grund steht. Die Gründe kommen aus den Quellen, die schon gelesen werden:
  - `transcripts` fehlt in der Policy
  - `process-dispatch/`, `phases.jsonl` oder der Gate-Log fehlt im Common-Dir
  - kein `Regression-of:` im Fenster
  - `check_issues` nicht importierbar
  - flacher Klon
- [ ] **A6 Doku.** `telemetry.md`: Fuchs-Merges in „Merged works come from git“, Konfidenz nach gefüllten Werten im Kopfabschnitt, Fehlgründe als Liste. Keine neue Familie.

### Konsumenten

- `grep -n "confidence(" process_kpis.py` → jede Familie mit Konfidenz; jede bekommt `n_filled`.
- `grep -rn "merge_events\|merged_works" template/scripts tests` → `flow_items`, `baseline_numbers`, `works_table`, `load_table`, `size_table` und ihre Tests. Alle lesen die Ereignisliste und ändern sich nicht in der Form.
- `grep -rn "session_output_tokens\|OUTPUT_TOKENS" template/scripts` → `cost`, `finish.py`, `dispatch.py`.

### Tests (je rot gegen v2.80.1)

`tests/test_telemetry.py`, Helfer für Train-Merges und `finish`-Archiv-Commits aus v2.80 wiederverwenden:

- **Fuchs-Historie:** `main` mit zwei Train-Merges, dann ein Branch, der `main` mergt, und ein Vorspulen von `main` auf ihn, danach ein weiterer Train-Merge. Erwartet: alle drei Train-Merges als Ereignisse, `population` nennt 1 Fuchs-Merge. Heute: 1 Ereignis.
- **Verschachtelter Fuchs:** ein Fuchs-Merge auf der zweiten Seite eines Fuchs-Merges.
- **Ereignis doppelt erreichbar:** zählt einmal.
- **`finish` hinter einem Fuchs:** Bereich `estimated`, Zeilen nicht 0.
- **`losses` mit 93 Items und 0 Werten:** Konfidenz `low`, Aktion nennt den Fehlgrund. Heute: `high`.
- **Transkript mit drei Inhaltsblöcken einer Nachricht** (gleiche `id`, gleiche Usage): `cost` zählt einmal. Heute: dreimal.
- **Bericht ohne `work:` mit einem Blocker:** `rounds` nennt ihn in der Gruppe und im Kopf.
- **Je Fehlgrund ein Fall:** Policy ohne `transcripts`; Common-Dir ohne `phases.jsonl`; Fenster ohne Trailer; flacher Klon.

Generik-Nachweis nach `MAINTAINING.md`: Minimalprojekt (ohne `telemetry` rendert nichts davon), Standardset, Update-Test.

## Skizze — Phase B (Tier 3, eigener Plan-Abschnitt vor Umsetzung)

- `report.py --sync` ist das Vorbild: Es veröffentlicht die Datei dieses Hosts als Blob unter `refs/process/reports/<host>`. Das gleiche Muster soll es für `process-dispatch` (eine Zeile je Phasenstart statt nur Dateinamen), `process-train/phases.jsonl` und `process-gate-events.jsonl` geben. Dafür braucht es einen gemeinsamen Helfer (Owner: `report.py` oder ein neues `process_sync.py`).
- `process_kpis.py` liest lokal **und** aus den Refs aller Hosts, wie `tower.py --remote`.
- Tier 3, weil `gate_events.py` und `train.py` Schreiber im Gate- bzw. Merge-Pfad sind: Refute vor Runde 1, Cross-Model-Review. Das Schreiben darf nie ein Urteil ändern („loses an observation, never a verdict“ bleibt). Ein verlorener Sync wird gezählt (D3 aus #356, niedrige Priorität).
- Offene Frage an den Owner vor Phase B: Soll ein Projekt mit fremdem Runner (Kenni: opencode über `kenni-tooling`) über `report.py` melden und keine Dispatch-Logs schreiben? Dann reicht für Phasenstarts ein `report.py started`-Zustand, und das Logformat bleibt intern.

## Skizze — Phase C (Tier 2)

- `process_kpis.py report --json` schreibt einen Schnappschuss mit allen Familien, je Wert mit Qualität und Fehlgrund.
- Der wöchentliche Steward-Lauf (`improvement-weekly.md`) läuft dort, wo die Daten liegen, und committet den Schnappschuss als `.process-work/kpis/<YYYY>-W<ww>.json`. Das ist ein Commit je Woche, die Prozesslast bleibt klein.
- Je Aktion mit Konfidenz `medium` oder höher eröffnet bzw. aktualisiert der Lauf genau ein Issue, Schlüssel ist Familie + Aktion. Bei `low` entsteht kein Issue, nur die Zeile im Schnappschuss.
- Monatlich bleibt der CI-Lauf (`process-kpis.yml`). Mit Phase B sieht er dieselbe Population wie der Host.

## Nicht in diesem Plan

- **Vorspulen auf einen Branch verhindern, der `main` hineingemergt hat.** `finish.py:563-628` prüft nur `merge-base --is-ancestor`, und das erfüllt ein solcher Branch. Eine Prüfung „alter `main` liegt auf der First-Parent-Kette des Branches“ gehört in den Merge-Guard. Das ist Gate-Code (Tier 3) und bekommt ein eigenes Issue. A1 macht die Messung davon unabhängig.
- **Kenni-Konfiguration:** `transcripts`, `optimization.local.json`, `gate-triage.jsonl`, `Regression-of:`.
- **opencode-Runner in `kenni-tooling`.**
- #316 (Review-Ertrag), #317 (Test- und CI-Verschwendung), #319 (Owner-Wartezeit) bleiben eigene Issues. Phase A schafft die Grundlage, auf der sie messbar werden.

## Unabhängige Durchsetzung

- Plan-Review in frischer Sitzung, bevor A umgesetzt wird.
- Code-Review von A als Tier 2: frische Sitzung auf dem Bundle; eine zweite Familie, wo verfügbar.
- Tests rot gegen v2.80.1 und grün danach, belegt im Review-Bundle.
- Release nach Owner-Freigabe (`tools/release.py`).

## Tier

- Phase A: Tier 2. `process_kpis.py` liest nur; kein Gate, kein Format- und kein Vertragswechsel. Die Ausgabe ändert sich additiv (neue Kopfzeile, `[missing: …]`-Suffix).
- Phase B: Tier 3.
- Phase C: Tier 2.

## Decisions

- DECISION 2026-11-02 owner: Issue mit Plan anlegen. Owner-Wort: „issue mit plan“, auf das Angebot „Issues zu Punkt 1 … oder gleich einen Plan für die drei Schritte“.
- DECISION 2026-11-02 agent: Drei Phasen statt eines Releases, Phase A zuerst. Ohne richtige Population ist jede Zentralisierung eine zentrale Ablage falscher Zahlen. Die Phasen haben verschiedene Tiers, und B berührt Gate-Code.
- DECISION 2026-11-02 agent: Fuchs-Merges werden im Leser behandelt, nicht nur verboten. Die Historie in Kenni bleibt, wie sie ist, und andere Projekte können denselben Weg schon gegangen sein.
- DECISION 2026-11-02 agent: Keine neue Registry neben dem Cockpit (siehe #356, #357 Abschnitt 6). Der Schnappschuss in C ist Ausgabe, keine Definition.
