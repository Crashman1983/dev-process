# Plan (Entwurf, zur Refutation): Der Prozess als Prüfgraph, den eine Schleife optimiert — v2.68/v2.69

Datum: 2026-10-12 · Status: **Entwurf, nicht umgesetzt** · Baut auf: v2.67
(`docs/analysis/2026-10-12-self-improving-process.md`) · Tier: 3 (Messung,
Aktivierung und Freigabe des Prozesses ändern sich selbst)

Revision 5. Vorgeschichte auf PR #216:

- Runde 1 und 2: Verdict `block` (zehn bzw. sieben Befunde).
- Neuausrichtung durch den Owner (§1). Revision 3 hatte jeden Befund mit
  zusätzlicher Regelung beantwortet und war zu schwer geworden. Revision 4
  setzte den Prüfmaßstab auf **Verhältnismäßigkeit** (§3).
- Runde 3 (verhältnismäßig): Verdict `revise`, kein Blocker. Der vereinfachte
  Ansatz und alle vier Lockerungen sind akzeptiert, fünf begrenzte Korrekturen
  verlangt.

Revision 5 arbeitet diese fünf ein. Wie jeder Befund beantwortet ist, steht in
§11.

## 1. Anforderung

- **Ziel:** mehr Output zu geringeren Kosten, **ohne Verlust von Qualität und
  Sicherheit**.
- **Mittel:** eine Schleife bzw. ein Graph, der den Entwicklungsprozess selbst
  anpasst. Gates dürfen wegfallen, sich ändern oder hinzukommen, je nachdem, was
  der Prozess braucht.
- **Ausgleich:** Verbesserung ist kein Selbstzweck. Prozessarbeit konkurriert
  mit Lieferarbeit.
- **Revidierbar und anpassungsfähig:** Signale, Regeln und Maßnahmen werden
  selbst überprüft, sind umkehrbar und passen sich an. Das leistet ein LLM, keine
  starre Formel.
- **Fehlende Signale schließt ein Regelkreis selbst.** Beispiel: Ob ein Bug ein
  Folgefehler oder neu entdeckt ist, soll erkannt, als Merkmal eingeführt und
  künftig ausgewertet werden (§12, A8).

## 2. Owner-Entscheidungen

- **DECISION 2026-10-12 owner:** Flag-aus-Releases von dev-process dürfen ohne
  Einzelfreigabe erscheinen (nach Gates, voller Suite, unabhängigem Review).
  Verhaltensänderungen bleiben beim Owner. Ausübbar erst mit der Inert-Grenze
  (P6, §13).
- **DECISION 2026-10-12 owner:** Der dev-process-Agent startet täglich, arbeitet
  aber nur bei offenen `optimization`-Issues. Jeder Lauf zählt zum Budget.
- **DECISION 2026-10-12 owner:** **Wert** heißt: Ein Feature ist *tatsächlich
  nutzbar* (Epic-Ebene), oder ein störender Fehler ist *schnell behoben*.
- **DECISION 2026-10-12 owner:** Ein projektseitiges Host-Skript darf
  aggregierte Betriebsdaten liefern, nur Zählwerte, keine Rohlogs.
- **DECISION 2026-10-12 owner:** Keine festen Modelle. Jede Schleife und jede
  Prüfung muss mit Claude oder Codex ausführbar sein.
- **DECISION 2026-10-12 owner:** Die Schleife darf Gates hinzufügen, ändern und
  entfernen. Qualität und Sicherheit sind Untergrenzen, kein Tauschgut.
- **DECISION 2026-10-12 owner:** Prüfmaßstab ist Verhältnismäßigkeit. Eine
  Kontrolle muss ihren Preis wert sein. Ein LLM-System braucht Freiraum beim
  Erkennen, Vorschlagen und Gestalten; strenge Grenzen gelten nur dort, wo ein
  Fehler teuer oder schwer umkehrbar ist.

## 3. Prüfmaßstab: wo Freiraum, wo Grenze

Die Refutation hat für jede Änderung den Nachweis einer Verbesserung verlangt.
Das ist der Maßstab einer Studie. Für dieses Ziel ist er falsch angesetzt, weil
die beiden Seiten der Rechnung verschieden sicher sind:

- **Die Bruttokosten sind direkt messbar.** Die Laufzeit eines Gates ist bei
  jedem Lauf bekannt und braucht keinen statistischen Nachweis. Die
  Nettoersparnis ist es nicht ganz: Liegt ein Gate nicht auf dem kritischen
  Pfad, spart sein Wegfall Rechenzeit, aber keine Durchlaufzeit; Stichprobe,
  Sichtung und Pflege kosten selbst etwas. Bruttokosten und beobachtete
  Nettokosten werden getrennt ausgewiesen, zugeordnete Tokens und verursachte
  Wartezeit als `estimated`.
- **Unsicher ist vor allem die Qualitätsseite.** Dort ist die Frage nicht „wird es
  besser?“, sondern „wird es nicht schlechter?“. Das beantwortet der Betrieb
  über Schattenläufe, Stichproben und schnellen Rückbau (§6), nicht über
  Studien.

Daraus folgt die Arbeitsteilung:

| Bereich | Maßstab |
|---|---|
| Erkennen, Diagnostizieren, Vorschlagen, Gestalten | **Freiraum.** Das LLM darf alles vorschlagen, auch neue Arten von Knoten, andere Reihenfolgen, andere Modelle je Phase. Keine Vorab-Bürokratie für Vorschläge. |
| Schrittweise Aktivierung einer Änderung | **Fester Lebenszyklus** (§6) mit wenigen, vorab im Record genannten Schwellen. Kein Signifikanznachweis. |
| Was als Qualität und Sicherheit gilt; geschützte Knoten; der Bewerter | **Harte Grenze** (§4, §9). Hier hatte die Refutation recht: Ein Optimierer auf Kosten findet sonst den Weg, seinen eigenen Maßstab zu senken. Die Einsparung zeigt sich sofort, der Verlust spät, selten und verrauscht. |

## 4. Leitplanken (Owner)

Der Owner legt im Mandat `docs/process/optimization.local.json` einen kleinen
Abschnitt `guardrails` fest:

- **Qualitäts- und Sicherheitskennzahlen mit Schwellen**, zum Beispiel:
  Folgefehler je Merge, vom Owner gemeldete störende Fehler, Rollbacks,
  Sicherheitsbefunde, rote Gates auf `main`. Für jede: Grundgesamtheit,
  Fenster, Schwelle.
- **Geschützte Knoten.** Knoten, die die Schleife nicht selbst abschwächen darf.
  Voreinstellung: Sicherheitsprüfungen, Secrets, Review-Unabhängigkeit,
  Abnahme, die Wächter selbst, der Bewerter. Geschützt ist die **wirksame
  Durchsetzung**, nicht nur der Name: Auch Abhängigkeitsauswahl, Routing,
  Reihenfolge und die Konfigurationshoheit dürfen einen geschützten Knoten
  nicht mittelbar umgehen. Projektspezifische Ergänzungen, etwa Prüfungen für
  destruktive Datenänderungen oder Migrationen, stehen in der
  Projektkonfiguration, damit dev-process generisch bleibt. Nicht jedes
  Kern-Gate ist automatisch geschützt (Format, Doku, Performance nicht).
- **Budget.** Absolute Agentenstunden und Owner-Minuten pro Woche für
  Prozessarbeit.
- **Rechte** des Stewards (§8).

Mehr regelt der Rahmen nicht. Alles andere ist Gestaltungsraum der Schleife.
Änderungen am Rahmen macht nur der Owner; `optimize.py check` lehnt Änderungen
ab, die nicht von ihm stammen (Entscheidungszeile mit `owner`).

## 5. Der Prozess als Graph

Jeder Schritt, der Arbeit prüft oder aufhält, ist ein **Knoten**: Gates im
Gate-Runner (Kern, Modul, projekteigen aus `gates.local.json`), Reviews und
Refutationen, Testauswahl, der Zug, Tier-Routing. Für jeden Knoten misst
`process_kpis.py nodes [--json]`:

| Maß | Quelle | Qualität |
|---|---|---|
| **Kosten:** Laufzeit, Tokens, verursachte Wartezeit | neues Gate-Ereignisprotokoll (§5.1), `flow`, Token-Abdeckung je Nutzungsereignis | measured |
| **Blockaden** (Rohzahl) | Gate-Ereignisse, REVIEW-Zeilen im Journal | measured |
| **Gesichtete Blockaden** (§5.2): bestätigter Defekt / akzeptiertes Risiko / Infrastruktur oder Flake / unbekannt | Sichtung einer Stichprobe | estimated, mit Stichprobengröße |
| **Eindeutige Fänge:** bestätigte Defekte, die kein anderer Knoten findet | vorhandene Urteile anderer Knoten auf demselben Stand, Wiederholung bekannter Fehlerfälle (§5.2) | estimated, mit Stichprobengröße |
| **Durchrutscher:** Folgefehler, deren Klasse der Knoten hätte fangen sollen | Bug-Herkunft (§10.3), LLM-Zuordnung an Stichprobe | estimated |

Knotendaten machen sichtbar, was ein Gate kostet und wie oft es anschlägt.
Wiederholte Läufe auf denselben Eingaben sind aber keine neuen
Fehlergelegenheiten. Für Entscheidungen zählen deshalb **verschiedene
zulässige Eingaben** (Kandidaten-Revisionen), nicht Läufe.

### 5.1 Gate-Ereignisprotokoll

Der Gate-Runner schreibt je Lauf und Gate eine Zeile nach
`.git/process-gate-events.jsonl`: Gate, Modus (§6), Commit, Branch bzw. Issue,
Ergebnis, Dauer, Grund. Das ergänzt die bestehende Rot-Ledger; es ist eine
Beobachtung, keine neue Pflicht.

### 5.2 Sichtung und Ersatznachweis

Ein folgender Fix-Commit beweist keinen Fang: Er kann einen anderen Fehler
beheben, und ein Waiver kann einen echten Defekt bewusst hinnehmen.
Stattdessen:

- **Sichtung.** Die Wochenschleife sichtet eine kleine Stichprobe von
  Blockaden und hält je Fall fest: Kategorie (bestätigter Defekt, akzeptiertes
  Risiko, Infrastruktur/Flake, unbekannt), Fehlerklasse, geprüfte Revision,
  Fix-Verweis. Ein Klassifikator ist nicht nötig. **Unbekannte Fälle
  begründen keinen Rückbau.**
- **Überlappung.** Der Gate-Runner läuft bereits nach einem Fehlschlag weiter
  und liefert die Urteile aller Gates auf demselben Kandidaten. Diese werden
  wiederverwendet. Zusätzliche Läufe gibt es nur für Ketten, die tatsächlich
  früh abbrechen (Reviews, Phasen).
- **Ersatznachweis.** Wer behauptet, Knoten B ersetze Knoten A, spielt die
  bekannten, von A gesichteten Fehlerfälle durch B. Gleichzeitiges
  Fehlschlagen beider auf derselben Revision reicht nicht, denn B kann einen
  anderen Fehler fangen.

## 6. Lebenszyklus einer Graph-Änderung

Jeder Knoten hat einen Modus in `gates.local.json` (für Reviews und Phasen in
der entsprechenden Konfiguration): `block`, `warn`, `shadow`, `sampled`, `off`.

| Änderung | Weg | Weiter, wenn |
|---|---|---|
| **Neuer Knoten** | Beobachtung (`shadow`, wahlweise `warn`) → `block`; eine Bewährungsstufe genügt | im Record genannte Mindestzahl verschiedener Eingaben; gesichtete Fänge und Fehlalarme im Rahmen; Kosten bekannt |
| **Ungeschützten, leicht umkehrbaren Knoten abschwächen** | `block` → `sampled` → dauerhaft `sampled` mit kleiner Reststichprobe; `off` nur mit Ersatznachweis (§5.2) oder ausdrücklichem Owner-Urteil | §6.1 |
| **Knoten ändern** | alt und neu parallel, das neue im `shadow` | Urteile stimmen überein oder das neue fängt mehr bei vertretbaren Kosten |
| **Routing, Reihenfolge, Modell je Phase** | über `active()`-Flags als begrenzter Versuch (v2.67) | Kosten direkt gemessen; Leitplanken halten |

### 6.1 Stichprobe abgeschwächter Knoten

- **Nur für ungeschützte, leicht umkehrbare Prüfungen.** Sicherheit,
  destruktive Änderungen und andere seltene, schwere Klassen werden nie mit
  „keine Fänge in der Stichprobe“ begründet abgeschwächt.
- **Startwerte** für etwa 100 Merges im Monat: 25–50 % Stichprobe über 4–6
  Wochen, verlängert, bis 30–50 verschiedene zulässige Eingaben vorliegen.
  Bei teuren Prüfungen ist eine kleinere Rate zulässig, mit entsprechend
  schwächerem Beleg. Das sind Beobachtungsvorgaben, keine Garantie, dass nichts
  durchrutscht.
- **Originale Eingaben.** Die Stichprobe prüft die ursprüngliche
  Kandidaten-Revision mit ihren Eingaben, die dafür aufbewahrt werden. Ein
  späteres, inzwischen repariertes `main` würde den verpassten Fang verbergen.
- **Sofortige Rückkehr.** Schlägt die Stichprobe unerwartet und handlungsrelevant
  an, kehrt der Knoten sofort auf `block` zurück, bis die Sichtung den Fall
  einordnet. Er wartet nicht auf einen Fix-Commit.

### 6.2 Rückbau bei Leitplankenbruch

- **Aktive Änderungen, nicht nur das Fenster.** Jede Abschwächung hat einen
  Record mit der vorherigen Konfiguration und den Leitplanken, die sie
  berührt. Reißt eine Leitplanke, nimmt der Wächter **alle noch aktiven**
  Änderungen zurück, die diese Leitplanke berühren, auch ältere, die jüngste
  zuerst, und stellt die aufgezeichnete vorherige Konfiguration her.
- **Eindämmung, keine Ursachenzuordnung.** Die Reihenfolge „jüngste zuerst“
  ist eine praktische Rückbauregel. Sie behauptet nicht, die Ursache gefunden
  zu haben.
- **Sperre.** Eine zurückgebaute Änderung ist für eine erneute Aktivierung
  gesperrt, bis sie gesichtet ist. So wendet die Wochenschleife dieselbe
  scheinbare Ersparnis nicht gleich wieder an.
- **Ein Abschwächen gleichzeitig je Leitplanke** bleibt als einfache Grenze.
- **Der Wächter hat Vorrang.** Deterministischer Rückbau gilt vor jedem
  LLM-Vorschlag.

### 6.3 Ausführungsvertrag

Nicht blockierend heißt nicht folgenlos: Ein Schattenbefehl kann trotzdem den
Kandidaten verändern, gemeinsamen Zustand schreiben oder eine Integration
aufrufen. Deshalb:

- **Frei** ist nur die Konfiguration bereits geprüfter, beobachtender Knoten:
  Modus, Stichprobenrate, Reihenfolge im Rahmen.
- **Neues ausführbares Verhalten**, etwa ein neuer Prüfbefehl, durchläuft die
  normale Code-Review des Projekts. Alternativ läuft eine neue Sonde gegen
  Wegwerf-Eingaben, mit eingeschränkten Rechten (keine Zugangsdaten, kein
  Netz, wo möglich) und einer Zeitgrenze. Ein Wegwerf-Arbeitsverzeichnis
  allein beschränkt weder Zugangsdaten noch externe Wirkungen.
- **Routing und Reihenfolge** dürfen geschützte Knoten nicht mittelbar
  umgehen (§4).

## 7. Schleifen

- **Wächter (deterministisch, immer an, eigenes kleines Budget):** Leitplanken,
  Stichproben abgeschwächter Knoten, automatischer Rückbau, Datenqualität. Sie
  entscheiden nur über Rückbau, nie über Abschwächung.
- **Wochenschleife (LLM):** liest Knotentabelle, Leitplanken, Wert- und
  Verlustmaße und schlägt Änderungen am Graphen vor, frei in der Form, mit
  Begründung und erwarteten Kosten. Sie startet Schritte des Lebenszyklus im
  Rahmen ihrer Rechte und meldet Produktsignale, wenn das Problem nicht im
  Prozess liegt. Sie sucht auch blinde Flecken (§10.4).
- **Monatsschleife (LLM, beratend):** prüft den Graphen als Ganzes, frühere
  Entscheidungen und ihre Wirkung, die Leitplanken selbst. Vorschläge zu
  Leitplanken und geschützten Knoten gehen an den Owner.

Aufträge harness-neutral unter `docs/process/`. Die Adapter (`.claude/commands/`,
`AGENTS.md`) verweisen nur darauf. Unabhängige Prüfsitzung: implementiert nicht
selbst, liest Belege an der exakten Revision ohne Schreibrecht, erbt keinen
Gesprächsverlauf. Modellfamilie und Rolle stehen im Log; wo die Tier-Regeln eine
andere Modellfamilie verlangen, gilt das weiter, sofern verfügbar.

## 8. Rechte

| Änderung | Steward | Owner |
|---|---|---|
| Vorschlag jeder Art | ✓ | — |
| Bereits geprüften Knoten in `shadow`/`warn` setzen | ✓ | — |
| Neuen ausführbaren Knoten einführen | über normale Code-Review oder als eingeschränkte Sonde (§6.3) | — |
| Neuer Knoten auf `block` | ✓ nach Lebenszyklus | sieht es im Bericht |
| Ungeschützten Knoten abschwächen (`block` → `sampled` → `off`) | **v2.68:** Owner bestätigt jeden Schritt mit einer Zeile. **v2.69:** Steward allein, sobald der Bewerter (§9) steht | ✓ |
| Geschützten Knoten abschwächen | Vorschlag mit Beleg | ✓ |
| Leitplanken, geschützte Knoten, Budget, Rechte | Vorschlag | ✓ |
| Rückbau | Wächter automatisch, Steward jederzeit | — |
| Globale Änderung im dev-process-Template | Vorschlag | Owner-Release (bzw. Flag-aus-Regel) |

## 9. Bewerter

Die Knotentabelle und die Leitplanken rechnet ein vertrauenswürdiger Bewerter:
der Basis-Stand des Prozesses, aufgelöst auf einen unveränderlichen Commit, in
eigenem Baum ausgeführt, mit seinen Abhängigkeiten. Eine Graph-Änderung ist
Gegenstand der Messung, nie Teil des Messcodes. Negativtest: Eine Änderung an
einem transitiven Leser (etwa `dispatch.issue_token_coverage`) ändert das Urteil
des Bewerters nicht. Bis v2.69 ersetzt die Owner-Bestätigung jedes
Abschwächens diese Grenze.

## 10. Wert, Verlust, Herkunft, blinde Flecken

### 10.1 Verlust: vier getrennte Maße

Belegung (Agentenstunden), Verzögerung (Issue-Stunden), Owner-Zeit, Tokens.
Nicht summiert, keine Doppelzählung, `missing` heißt unbekannt. Review-Runden,
Pfad-Anteile und Rauswürfe sind diagnostische Proxys.

### 10.2 Wert

- **O1 Epic nutzbar:** Epic = Issue mit nativen Sub-Issues (Fallback:
  Titelpräfix oder Label). Nutzbar = im Mandat festgelegter Abnahmenachweis,
  etwa geschlossenes Abnahme-Issue mit Deploy. Administrativer Abschluss ist
  ein schwächerer Proxy.
- **O2 Störender Fehler schnell behoben:** Bugs mit Kanal `operator` und dem
  Merkmal „störend“; Zeit bis zum ausgelieferten Fix.
- **O3 Betrieb (optional):** Zählwerte aus dem Host-Skript.
- Ohne Daten: `unavailable` mit Grund. Verschlechtert sich ein Wert und fehlen
  Prozessdaten, heißt der Befund „unbekannt“; die nächste Maßnahme schließt die
  Lücke.

### 10.3 Herkunft von Bugs: zwei Achsen

Ursache (`regression` mit `Regression-of: #N`, `preexisting`, `unknown`) und
Kanal (`operator`, `agent`, `monitor`, `other`), mit Zeitstempeln. Gesetzt wird,
wo es bekannt ist: der Agent bei Folgefehlern, die Steward-Sitzung bei
Owner-Meldungen. Abdeckung und Güte (geprüfte Stichprobe) sind getrennt; die
Folgefehlerquote gilt erst als gemessen, wenn beide reichen.

### 10.4 Blinde Flecken

Die Wochenschleife liest eine reproduzierbare Stichprobe neuer Issues, Commits
und Journalzeilen und sucht wiederkehrende Freitext-Muster, die eine Dimension
ohne Feld tragen. Ein Fund wird eine vorläufige Frage mit Beleg und benanntem
Abnehmer. „Keine neue Frage“ ist ein gültiges Ergebnis. Die Eskalation
(Hinweis → Pflichtfeld → weiche Notiz → Gate) ist selbst eine Graph-Änderung und
läuft durch denselben Lebenszyklus: Das Gate beginnt im `shadow`.

## 11. Antwort auf die Refutationsbefunde

### Was bleibt (die Refutation hatte recht)

| Befund | In Revision 4 und 5 |
|---|---|
| R1-1, R2-1: Schleife verschiebt ihren Maßstab | Leitplanken und geschützte Knoten nur durch den Owner (§4) |
| R1-1, R2-2: Bewerter nicht isoliert | §9; bis dahin Owner-Bestätigung jedes Abschwächens |
| R2-3: Verlustbuch mischt Maße | §10.1 vier getrennte Maße |
| R2-4: ein Herkunftsfeld reicht nicht | §10.3 zwei Achsen |
| R2-5, R1-5: Token- und Flow-Vollständigkeit | behoben (0557b2e, 92a3e49) |
| R1-2: Tupel-Wahrheitswert | behoben (0557b2e); autonome Releases erst mit P6 |
| R1-3: überlappende Versuche | behoben (0557b2e); ein Abschwächen je Leitplanke (§6) |
| R1-7: Übernahme geht verloren | der Modus steht in `gates.local.json` bzw. `adopted[]`; er bleibt, bis ihn jemand ändert |
| R2-7: Wächter dürfen nicht pausieren | §7 Wächter immer an, eigenes Budget, entscheiden nur über Rückbau |

### Runde 3 (verhältnismäßig, Verdict `revise`)

| # | Befund | In Revision 5 |
|---|---|---|
| 1 | Fix-Commit beweist keinen echten oder eindeutigen Fang | §5.2 Sichtung mit vier Kategorien; Unbekanntes begründet keinen Rückbau; Ersatznachweis durch Wiederholung bekannter Fehlerfälle; vorhandene Urteile des Gate-Runners statt Zusatzläufen |
| 2 | Nicht blockierend ist keine Rechtegrenze | §6.3 Ausführungsvertrag; §8 neue Befehle über Code-Review oder eingeschränkte Sonde |
| 3 | Null Fänge in 10 % Stichprobe reicht nicht zum Abschalten | §6.1 nur ungeschützt und umkehrbar; 25–50 % über 4–6 Wochen bis 30–50 verschiedene Eingaben; originale Eingaben; Reststichprobe statt `off` |
| 4 | Fenster-Rückbau braucht Records aktiver Änderungen und eine Sperre | §6.2 |
| 5 | Unbekannte Token-Quellen als gemessen gemeldet | **Behoben in d6567c9**; Tests für reine Opak-Zeilen und unlesbare Transkripte, Mutationsprüfung |

Antwort auf Frage 1 (Asymmetrie) in §3 eingearbeitet; Frage 5 (geschützte
Knoten: wirksame Durchsetzung, projektspezifische Ergänzungen) in §4; Frage 7
(nicht beide Bewährungsstufen erzwingen, keine Zusatzläufe, wo Urteile
vorliegen) in §5.2 und §6.

### Was bewusst anders gelöst wird (Verhältnismäßigkeit, in Runde 3 akzeptiert)

| Befund | Statt | Begründung |
|---|---|---|
| R1-4, R2-6: Stichprobengröße, Signifikanz | Einsparung direkt messen; Qualität über Lebenszyklus, Stichprobe, automatischen Rückbau | Die Kostenseite braucht keinen Nachweis. Die Qualitätsseite wird pro Prüfung beobachtet (viele Ereignisse), nicht pro Issue. Für seltene schwere Klassen bleiben geschützte Knoten. |
| R2-1: typisierte Parameter, Totband, Verweildauer für jede Regel | kleiner Owner-Rahmen; Freiraum im Rest | Der Formalismus kostete mehr, als er schützte. Die Schwellen des Lebenszyklus stehen im jeweiligen Record. |
| R2-7: Vorrangordnung, Hysterese für sechs Schleifen | zwei LLM-Schleifen plus Wächter | Weniger Schleifen, weniger Wechselwirkung; Wächter haben Vorrang, weil nur sie zurückbauen. |
| R1-6, P5: Offline-Benchmark | zurückgestellt | Für Gate-Änderungen liefert der Schattenbetrieb bessere Daten als nachgestellte historische Aufgaben. |

## 12. Abnahme (EARS)

- **A1** When a gate runs, the gate runner shall append gate, mode, commit,
  branch or issue, result, duration and reason to the gate event log.
- **A2** When `process_kpis.py nodes` runs, the system shall report per node its
  gross cost, raw blocks, triaged blocks by category and unique catches, each
  with the number of distinct inputs and data quality, and shall report
  triaged and unique figures as estimated with their sample size.
- **A3** When a node is in `shadow` or `sampled` mode, it shall run and record
  its verdict without blocking.
- **A4** When a `sampled` node records an actionable unexpected failure on the
  original candidate revision, the sentinel shall set the node back to `block`
  pending triage and record why.
- **A5** If a guardrail crosses its threshold, then the sentinel shall restore
  the recorded previous configuration of every still-active change that
  touches the guardrail, newest first, mark each as locked against
  reactivation until triaged, and report the breach to the owner.
- **A5b** When a node is weakened to `off`, the system shall refuse unless a
  replacement proof or an owner decision line is recorded. A triage category
  `unknown` shall not count as evidence for weakening.
- **A5c** When the steward introduces a new executable check, the system shall
  require it to come through code review or to run as a restricted probe
  against disposable inputs with a timeout.
- **A6** When the steward weakens a protected node or changes a guardrail,
  `optimize.py check` shall refuse the change unless an owner decision line
  covers it.
- **A7** While v2.68 is installed, every step that weakens a node shall need an
  owner decision line.
- **A8 (Herkunft, Beispiel des Owners)** When fewer than the target share of
  bugs carry cause and channel, the weekly loop shall record a blind spot and
  propose the field. When the owner reports a regression introduced by #N, the
  record shall carry cause `regression` and channel `operator` and count in
  both the regression share and O2. Once coverage and the audited sample meet
  target, `losses` shall report the regression share as measured.
- **A9** When `process_kpis.py losses` runs, the system shall report occupancy,
  delay, owner effort and tokens separately and never report `missing` as zero.
- **A10 (v2.69)** When a candidate changes a transitive measurement reader, the
  trusted evaluator's node table and guardrail verdicts shall not change.

## 13. Pakete

| Release | Paket | Inhalt |
|---|---|---|
| v2.68 | P1 Messen | Gate-Ereignisprotokoll; `nodes` mit Sichtung und Ersatznachweis; `losses` (vier Maße); `outcomes`; Herkunft auf zwei Achsen |
| v2.68 | P2 Modi und Wächter | `block/warn/shadow/sampled/off` je Knoten; Records aktiver Änderungen mit vorheriger Konfiguration; Leitplanken im Mandat; Wächter mit Rückbau und Sperre; Ausführungsvertrag; Owner-Bestätigung für jedes Abschwächen |
| v2.68 | P3 Schleifen | Aufträge wöchentlich und monatlich, harness-neutral; Berichtsformat |
| v2.69 | P4 Bewerter | vertrauenswürdiger Bewerter; danach darf der Steward ungeschützte Knoten selbst abschwächen |
| später | P5–P7 | Offline-Screen, Inert-Grenze für autonome Releases, Upstream-Kanal und Routine-Lease |

P1 liefert ab der ersten Woche eine Knotentabelle: Welche Gates kosten viel und
fangen wenig, welche fangen eindeutig? Das ist die erste konkrete
Optimierungsgrundlage, noch bevor die Schleife etwas verändert.

## 14. Offen an die nächste Prüfung

Runde 3 hat die Fragen von Revision 4 beantwortet. Offen bleibt, was erst die
Umsetzung zeigt:

1. Wie viel Sichtungsaufwand pro Woche fällt real an, und trägt er sich gegen
   die Ersparnis?
2. Welche Prüfungen eines Projekts sind tatsächlich leicht umkehrbar und
   damit für die Stichprobe geeignet?
