# Plan (Entwurf, zur Refutation): Geschlossener Verbesserungskreislauf — v2.68

Datum: 2026-10-12 · Status: **Entwurf, nicht umgesetzt** · Baut auf: v2.67.0
(`docs/analysis/2026-10-12-self-improving-process.md`) · Tier: 3 (Gate-Code
betroffen: `dispatch.py`, `optimize.py`, `process_context.py`)

## Anlass

v2.67 liefert das Gerüst: Optimierungsvertrag, Records mit eingefrorenen
Bedingungen, Flags für begrenzte Piloten, Ende-zu-Ende-Messung (`flow`),
lesenden Graphen. Der Owner will **echte Selbstverbesserung**: Der Kreislauf
soll ohne ihn als Motor laufen. Eine Recherche zum Stand von Forschung und
Anthropic-Praxis (Quellen im Refute-Briefing
`docs/analysis/2026-10-12-refute-brief-codex.md`) bestätigt die Grundrichtung,
zeigt aber Lücken. Dieser Plan beschreibt die Antwort und wird **vor** der
Umsetzung von einer zweiten Modellfamilie (Codex Astra) widerlegt.

## Owner-Entscheidungen (2026-10-12)

- **DECISION 2026-10-12 owner:** dev-process-Releases, die ausschließlich einen
  neuen, standardmäßig *ausgeschalteten* Mechanismus hinter einem Flag
  bringen, dürfen ohne Einzelfreigabe erscheinen — nach Gates, voller Suite und
  unabhängigem Review. Alles, was Verhalten ändert (Flag standardmäßig an,
  Gates, Tiers, Verträge), bleibt beim Owner.
- **DECISION 2026-10-12 owner:** Der dev-process-Agent startet täglich per
  Routine, arbeitet aber nur, wenn ein offenes `optimization`-Issue wartet.
  Jeder Lauf zählt zum Optimierungsbudget.

## Diagnose: was am geschlossenen Kreislauf fehlt

| # | Lücke in v2.67 | Beleg |
|---|---|---|
| L1 | Kein Auslöser: Engpässe muss der Steward „bemerken“. | Loop-Spezifikation = Auslöser, Ziel, Prüfung, Abbruchregel, Gedächtnis; der Auslöser fehlt. |
| L2 | Kein Kanal zwischen Projekt und dev-process; der Record liegt im Projekt, der Maintainer arbeitet upstream. | Konzept §7; `MAINTAINING.md` beschreibt die Übergabe nur als Konvention. |
| L3 | Der dev-process-Agent läuft nie von selbst. | Er ist eine Sitzung, kein Prozess. |
| L4 | Bewertung ist Urteil statt Rechnung: Kriterien sind Freitext. | Anthropic: Selbstbewertung ist nachsichtig; Bewerter getrennt und kalibriert. |
| L5 | Nur Live-Piloten bewerten: eine Runde dauert Wochen. | Alle erfolgreichen selbstverbessernden Systeme iterieren gegen schnelle, wiederholbare Evals (DGM, SICA, Meta-/Self-Harness). |
| L6 | Records als Markdown mit Freeze per Parser: vier Refute-Runden fanden je einen neuen Rendering-Trick. | Anthropic: JSON wird seltener unangemessen überschrieben als Markdown. |
| L7 | Auswertung ohne Rauschmodell: Mindest-n pauschal, nur Mediane. | Anthropic: Infrastruktur allein verschiebt Agenten-Evals um bis zu 6 Punkte; Abstände < 3 Punkte skeptisch sehen. |
| L8 | Flags schalten nur Neues ein, nie Bestehendes ab. | Anthropic: Jede Harness-Komponente kodiert eine Annahme; mit neuen Modellen prüfen und entfernen. |
| L9 | Noch kein Mechanismus hinter einem Flag, den man pilotieren könnte. | Paket D des Konzepts. |

## Entscheidungen (zur Prüfung)

- **D1 Auslöser — Kandidaten-Detektor.** `process_kpis.py candidates [--json]`
  (telemetry-Modul) liest `flow`, `rounds`, `clusters` und meldet Kandidaten mit
  stabilem Signal-Schlüssel, Belegzahlen und Datenqualität: `wait-dominant`,
  `token-outliers`, `fix-cluster`, `review-rounds`, `escapes`. Schwellen sind
  dokumentierte, vorläufige Konstanten. `optimize.py propose` legt für jedes
  Signal ohne offenen Record einen `proposed`-Record an (nur Beobachtung).
- **D2 Kanal — Upstream-Issue.** `optimize.py hand-over OPT-n` legt im
  Prozess-Repository (aus `.copier-answers.yml` `_src_path`) ein Issue mit
  Label `optimization` an: Record-Verweis, Flow-Auszug, Projektgrenzen. Der
  dev-process-Agent antwortet mit einem strukturierten Entwurf;
  `optimize.py import-design OPT-n <datei|->` übernimmt nur die Abschnitte,
  die ihm gehören.
- **D3 Abschnittseigentum.** Projekt/Steward: Observation, Auswahl, Zeitraum,
  Budget, Entscheidung zum Projekteinsatz. dev-process-Agent (als
  `implementer`): Hypothesis, Placement, Trial-Design, Criteria, Generality,
  Rollback, Analyse. Dritter: `REVIEWED`. Übernahme nie durch den Implementierer.
- **D4 Taktgeber — Routine.** Eine Routine in dev-process startet täglich eine
  Sitzung mit dem Auftrag aus `docs/maintainer/optimization-routine.md`: offene
  `optimization`-Issues prüfen; keine → sofort beenden; sonst Ursache, Ort,
  Versuchsentwurf, Mechanismus hinter Flag, Offline-Eval (D6), Review, Release
  nach der Owner-Regel oben.
- **D5 Records als JSON.** `OPT-NNNN.json` trägt Zustand, eingefrorene
  Bedingungen (inkl. maschinenlesbarer Kriterien), Reviews, Log (append-only);
  der Freeze ist ein Hash über kanonisches JSON der Bedingungen.
  `OPT-NNNN.md` ist reine Erzählung, nicht eingefroren, nicht maschinell
  gelesen. Migration: v2.67-Records werden einmalig konvertiert (es gibt noch
  keine).
- **D6 Offline-Eval-Suite (schnelle Schleife).** Aus der Projekt-Historie
  entstehen eingefrorene Aufgaben: Repo-Commit + Task + Bewerter (Tests grün,
  Gates grün, Tokens, Runden-Proxy). Eine Variante läuft in isolierten
  Worktrees gegen *Train*- und *zurückgehaltene* Aufgaben, Baseline gegen
  Variante, mehrere Durchläufe je Aufgabe. Nur Varianten ohne Regression und
  mit Effekt über dem Rauschen gehen in den Live-Pilot. Capability-Aufgaben
  „graduieren“ später zu Regressionsaufgaben. Budget pro Eval-Lauf im Mandat.
- **D7 Rauschbewusste Auswertung.** Kriterien als Daten:
  `{"metric": "tokens_in", "direction": "down", "min_effect": 0.2, "min_n": …}`.
  `optimize.py evaluate` vergleicht Versuchs- und Kontrollgruppe *im selben
  Zeitraum* (Aktivierungsprotokoll: `active()` schreibt je Abfrage on /
  outside-select / off), Bootstrap-Konfidenzintervall statt nur Median,
  Mindest-n aus der Baseline-Streuung, Modell/Harness/Host als protokollierte
  Kontrollvariablen. Ergebnis `pass | fail | inconclusive`, geschrieben vom
  Skript. Der Steward darf nur bei `pass` übernehmen (sofern das Mandat es
  erlaubt); der Owner kann mit Begründung abweichen.
- **D8 Ablations-Flags.** Ein Experiment darf einen bestehenden Mechanismus
  probeweise *abschalten* (`mode: ablation`). So kann der Kreislauf
  vereinfachen.
- **D9 Erster Mechanismus: `scoped-handover`.** `process_context.py handover
  --issue N --task T` liefert das Paket für einen `[mechanical]`-Subagenten:
  Task-Zeile, genannte Dateien, `## Decisions`, zugehörige Tests (Testkarte,
  ggf. `graph.py context`). `/execute` nutzt es nur, wenn
  `optimize.py active scoped-handover --issue N --class mechanical` „an“ meldet;
  sonst unverändert.
- **D10 Release-Autonomie technisch.** `tools/release.py vX --autonomous`
  verweigert, solange nicht gilt: CHANGELOG-Eintrag trägt
  `Flag-aus-Release: <flag>`; jede verhaltensrelevante Template-Änderung ist
  durch dieses Flag geschützt (statischer Check + Suite ohne Mandat
  unverändert grün); unabhängiges Review attestiert.
- **D11 Graph neu eingeordnet.** `graph.py` bleibt Kontext-/Abhängigkeitsgraph
  (gestützt durch Code-Graph-Forschung). Der Orchestrierungsgraph (Phasen,
  Rollen, Modell je Phase) bleibt Konfiguration, die Experimente über Flags
  ändern. Keine Topologie-Optimierung (ADAS/AFlow-artig), bevor D6 existiert.

## Nicht in diesem Release

Automatische Topologie-Suche; Incident-Records für Wiederherstellungszeit;
Kern-Gate für `optimize.py check`.

## Offene Fragen an die Refutation

1. Ist die Offline-Suite (D6) aus Projekt-Historie überhaupt valide — Daten-
   leckage (das Modell kennt die Lösung aus dem Repo), Nicht-Determinismus,
   Kosten? Was wäre die minimale tragfähige Form?
2. Reicht eine Kontrollgruppe per Issue-Parität bei der Streuung realer Issues,
   oder braucht es Paarbildung / sequentielle Tests?
3. Ist die Release-Autonomie (D10) prüfbar „verhaltensneutral“, oder ist das
   eine Behauptung, die ein Agent erfüllen kann, ohne dass sie stimmt?
4. Welche Kennzahl kann der dev-process-Agent selbst beeinflussen (Goodhart,
   Reward-Hacking), und wie schließen wir das aus?
5. Ist der Kreislauf zu komplex für den Nutzen („simplest thing that works“)?
   Was würde man streichen?
