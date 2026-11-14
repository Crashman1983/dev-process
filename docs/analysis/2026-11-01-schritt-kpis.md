# Schritt-KPIs des Entwicklungsprozesses — Transparenz und Messbarkeit

## Anlass

Der Prozess soll sich anhand realer Ergebnisse verbessern lassen. Dafür braucht ein
optimierender Agent für jeden Schritt eine Kennzahl für Fehlerfreiheit (Qualität) und
für Geschwindigkeit, dazu Kosten und eine Gegenkontrolle. Dieses Dokument legt diese
Kennzahlen fest, sagt für jede, ob der Prozess sie heute erfasst, und nennt die Lücken
und Messfehler, die vor einer Optimierung zu schließen sind.

Grundlage: die Schrittinventur (17 Schritte, Owner-Skripte und Datensätze) und ein Audit
der Messinfrastruktur in `kenni` (Prozessversion v2.80.1). Die Inventur ist für die
Aussagen zu Owner und Datensätzen verlässlich, soweit die genannten Stellen gegengeprüft
wurden; Stichproben: Gate-Ereignisschreiber, Tokenzählung, Konfidenzangabe.

## Ergebnis in Zahlen

Die maschinenlesbare Fassung ist `docs/analysis/step-kpis.json`; `tests/test_step_kpis.py`
prüft ihre Konsistenz (Vollständigkeit, Statuswerte, Pfade im Template, Begründung jeder Lücke).

- 17 Schritte, 48 KPIs: 22 Qualität, 15 Geschwindigkeit, 9 Kosten, 2 Gegenkontrolle.
- Status im Code: 21 `measured`, 3 `estimated`, 6 `proxy`, 18 `missing`.
- In `kenni` vorliegende Datensätze: 10 KPIs haben Daten, 29 nicht, 8 sind ungeprüft, 1 entfällt.

Die Journal-Datensätze für Review, Refute, Root-Cause und Entscheidungen sind in `kenni`
vorhanden und tragen die meisten Qualitätswerte. Dispatch-, Zug-, Gate- und Deploy-Daten
fehlen dort ganz: Die Gate-Ereignisse liegen nicht vor, es gibt kein Dispatch-
und kein Zug-Verzeichnis, und `kenni` hat keine Deploy-Stufe.

## Die Schritte

| Schritt | Owner | Qualität | Tempo / Kosten | Lage |
|---|---|---|---|---|
| S1 Tier-Routing | `risk-tiers.md` | Tier-Korrekturquote (missing) | Routing-Dauer (missing) | keine Erfassung |
| S2 Spec und Klärung | `check_clarification.py` | Klärungsblocks je Spec (measured) | Spec-Dauer (missing) | kenni ohne Gate-Log |
| S3 Plan | `check_plan_structure.py`, `plan_drift.py` | Strukturfehler, Planveraltung (measured) | Planungsdauer (missing) | kenni ohne Gate-Log |
| S4 Plan-Review | `attest.py` | Blockrate, Runden bis Pass (measured) | Tokens je Review (missing) | Journal vorhanden |
| S5 Refute | `refute_line.py` | befundwirksame Befunde (proxy) | Refute-Runden (measured) | Journal vorhanden |
| S6 Dispatch | `dispatch.py` | Modell außerhalb Policy (proxy) | Phasendauer (measured), Tokens und Queue-Wartezeit (missing) | kein Dispatch-Verzeichnis |
| S7 Umsetzung, Fix-Runden | `red_evidence.py` | blockierte Runden (proxy), Root-Cause-Blöcke (measured) | Tokens je Fix-Runde (missing) | Journal vorhanden |
| S8 Gate-Runner | `gate_runner.py` | Blockrate, Fehlalarmquote (measured, estimated) | Laufzeit, Sekunden je Push (measured) | kein Ereignis-Log |
| S9 Pre-Push und Merge-Schutz | `pre_push.py` | Override-Quote (proxy) | Prüfdauer (missing) | Override-Log ungeprüft |
| S10 Review-Urteil | `check_review.py` | Blockrate (measured) | Review-Dauer (missing), Owner-Entscheidungen (proxy) | Journal vorhanden |
| S11 Finish | `finish.py` | Testfehler beim Finish (missing) | Dauer (missing) | ungeprüft |
| S12 Merge-Zug | `train.py` | Rotquote, Flake-Quote (measured) | Phasenzeit, Lead-Time (measured) | kein Zug-Verzeichnis |
| S13 Worker-Berichte | `report.py` | Anteil failed/blocked (measured), Phasen ohne Endbericht (estimated) | Berichtsverzug (missing) | Verzeichnis leer |
| S14 Deploy, Nachfehler | `train.py` | Nachfehler 30 Tage (proxy), Deploy-Fehlerquote (missing) | Merge bis Deploy (measured) | 2 Trailer, keine Deploy-Stufe |
| S15 Housekeeping | `tidy.py` | Wiederherstellungen (missing) | offene Worktrees (missing) | ungeprüft |
| S16 Optimierungsschleife | `optimize.py` | zurückgenommene Entscheidungen (measured) | Befund bis Entscheidung (measured), Aufwandsanteil (estimated) | kein Record |
| S17 Messung selbst | `process_kpis.py` | verlorene Gate-Ereignisse (missing), Messabdeckung (measured) | Cockpit-Laufzeit (missing) | — |

Die vollständige Liste mit Definition, Einheit, Richtung und Lücke steht in der JSON-Datei.

## Ziele, die aus den KPIs gelesen werden

- **Durchlaufzeit je Issue:** S12.s2 und S14.s1; `flow` liefert Teilwerte, der Startzeitpunkt ist geschätzt.
- **Tokens je Issue:** S4.c1, S6.c1, S7.c1; heute nicht berechenbar, Blocker ist I1.
- **Nachfehler:** S14.q1 und S10.q1, nur zusammen lesbar.
- **Owner-Aufwand:** S10.c1, zählt Entscheidungen, nicht Minuten.

## Messfehler im Cockpit

Sie stehen vor jeder Optimierung, weil sie Zahlen falsch oder zu sicher erscheinen lassen.

- **D1 — Token-Zählung doppelt gelesen.** `process_kpis.py` (`cost`, `session_output_tokens`)
  summiert jeden Treffer des Musters ohne Deduplizierung. Claude Code schreibt je
  Inhaltsblock eine Zeile mit derselben Usage; `dispatch.py` (`_transcript_usage`) zählt
  eine Nachricht einmal. Gelesen, nicht reproduziert.
- **D2 — Konfidenz der Verlust-Überschrift.** `process_kpis.py:2357` leitet die Konfidenz
  aus der Zahl der Issues ab, nicht aus den befüllten Werten. In `kenni` steht
  „hohe Konfidenz (n=28)“, während Tokens, Belegung und Verzögerung bei 0 von 28 liegen.
- **D3 — verschluckte Gate-Ereignisse.** `gate_events.py:46-47` fängt jede Ausnahme ab.
  Verlorene Ereignisse sind unsichtbar; die Gate-KPIs wirken vollständiger, als sie sind.
- **D4 — Gesamtbericht lückenhaft.** Der Kopf von `report` lässt `models`, `rounds`,
  `outcomes` und `train-phases` aus; `cost` erhält kein Transkript-Verzeichnis.
  Vom Audit gelesen, nicht gegengeprüft.

## Instrumentierung nach Priorität

| Nr. | Prio | Was | Deckt |
|---|---|---|---|
| I1 | 1 | Phasen-Report übergibt die Sitzungs-Usage (Ausgabe- und Cache-Tokens) aus dem bestehenden Transkript-Leser | S4.c1, S6.c1, S7.c1 |
| I2 | 1 | `cost` nutzt den Leser von `dispatch.py` statt eigener Summe — behebt D1 | S6.c1 |
| I3 | 1 | Gate-Ereignisse nicht still verwerfen; Fehler zählen und im Cockpit zeigen — behebt D3 | S2.q1, S3.q1, S3.q2, S8.q1, S17.q1 |
| I4 | 2 | Tier als Feld im Plan-Kopf; Anhebungen als Zeile mit Grund | S1.q1 |
| I5 | 2 | Zeitstempel für Planbeginn und Reviewstart; REVIEW-Zeilen mit Zeitstempel (Vertragsänderung) | S3.s1, S10.s1 |
| I6 | 2 | Phasenstart und -ende als ein Datensatz mit Dauer; Berichtsverzug messen | S6.s1, S13.g1, S13.s1 |
| I7 | 2 | `PROCESS_SKIP` und `SKIP=process-gates` protokollieren wie Owner-Overrides | S9.q1 |
| I8 | 3 | Deploy-Ereignisse; in `kenni` ohne Wirkung, weil es keine Deploy-Stufe gibt | S14.q2, S14.s1 |

I1 bis I3 sind klein und ändern keine Verträge. I5 ändert das REVIEW-Zeilenformat und
braucht einen Migrationshinweis im CHANGELOG. I3 und I7 berühren Gate-Code und sind Tier 3.

## Regeln für den optimierenden Agenten

1. Eine Optimierung braucht ihre Gegen-KPI aus derselben Zeile der Registry
   (Tempo gegen Nachfehler, Tokens gegen Blockrate). Eine Kosten-KPI allein entscheidet nichts.
2. Entscheidungen stützen sich auf `measured` und `estimated`. `proxy` ist ein Hinweis,
   kein Beleg. `missing` heißt: zuerst das Backlog, nicht raten.
3. Mit wenigen Beobachtungen ist das Ergebnis unentschieden. Nie Prozente aus einem
   Dutzend Fällen ableiten; die Anzahl zuerst nennen.
4. Messwerte aus Transkripten nur über den Leser von `dispatch.py` lesen, bis D1 behoben ist.
5. Die Zahlen gelten nur innerhalb eines Projekts (Vergleich über Zeit, nicht über Projekte).

## Was nicht gemacht wurde

- Keine Änderung am Code: kein Cockpit-Unterbefehl `steps`, keine Instrumentierung, keine
  Korrektur von D1 bis D4. Das sind I1 bis I8 und ein eigener Plan.
- Die Registry liegt in `docs/analysis/`, nicht im Template. Damit ist sie noch nicht in
  Projekten sichtbar; eine Übernahme ins Template braucht Release und Migrationshinweis.
- Die Befunde sind nicht unabhängig geprüft (kein Review-Gate, keine frische Sitzung). Die
  Registry-Tests prüfen Form und Verweise, nicht die Messwerte.
- D1 bis D4 sind nicht reproduziert bzw. nicht gegengeprüft (Stand der Prüfung je Befund im Feld `evidence` der JSON).

## Entscheidungen

- Ablage in `docs/analysis/` als maschinenlesbare Registry plus Analysedokument; Begründung:
  Die Schritt-KPIs sind die Grundlage der Optimierung, noch kein Teil des ausgelieferten
  Prozesses. Die Übernahme ins Template ist eine eigene Entscheidung.
- Status ist getrennt nach Code und Projektdaten geführt, damit ein „measured“ nicht als
  „vorhanden“ gelesen wird.
- Gegenkontrollen sind eigene KPIs (Dimension `guard`) statt Teil einer Summe.

## Offene Fragen an den Owner

1. Sollen I1 bis I3 als Issues angelegt und zuerst umgesetzt werden?
2. Soll die Registry ins Template übernommen werden (mit Cockpit-Unterbefehl `steps`
   und Release)?
