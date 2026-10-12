# Plan (Entwurf, zur Refutation): Der Prozess als Prüfgraph, den eine Schleife optimiert — v2.68/v2.69

Datum: 2026-10-12 · Status: **Entwurf, nicht umgesetzt** · Baut auf: v2.67
(`docs/analysis/2026-10-12-self-improving-process.md`) · Tier: 3 (Messung,
Aktivierung und Freigabe des Prozesses ändern sich selbst)

Revision 4. Ausgangspunkt sind zwei Refutationsrunden auf PR #216, beide mit
Verdict `block` (Runde 1: zehn Befunde, Runde 2: sieben) und eine Neuausrichtung
durch den Owner (§1). Revision 3 hatte jeden Befund mit zusätzlicher Regelung
beantwortet und war dadurch zu schwer geworden. Revision 4 hält die
Sicherheitsgrenzen der Refutation und setzt den Prüfmaßstab neu auf
**Verhältnismäßigkeit** (§3). Wie jeder Befund beantwortet ist, steht in §11.

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

- **Die Einsparung ist direkt messbar.** Laufzeit, Tokens und Wartezeit eines
  Gates sind bei jedem Lauf exakt bekannt. Sie brauchen keinen statistischen
  Nachweis.
- **Unsicher ist nur die Qualitätsseite.** Dort ist die Frage nicht „wird es
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
  Abnahme, die Wächter selbst, der Bewerter. Der Owner kann die Liste ändern.
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
| **Blockaden** | Gate-Ereignisse, REVIEW-Zeilen im Journal | measured |
| **Echte Fänge:** Blockade, auf die ein Fix-Commit auf dem Branch folgte (statt Waiver oder Override) | Gate-Ereignisse + Branch-Historie | measured / estimated |
| **Eindeutige Fänge:** echte Fänge, die kein anderer Knoten findet | Überlappungsstichprobe (§5.2) | estimated, mit Stichprobengröße |
| **Fehlalarme:** Blockade, die per Waiver oder ohne Code-Änderung aufgehoben wurde | Gate-Ereignisse, Waiver | measured |
| **Durchrutscher:** Folgefehler, deren Klasse der Knoten hätte fangen sollen | Bug-Herkunft (§10.3), LLM-Zuordnung an Stichprobe | estimated |

Jede Prüfung ist eine Beobachtung. Ein Projekt mit hundert Merges im Monat
liefert pro Gate Hunderte Ereignisse. Das Stichprobenproblem der Refutation
betrifft Vergleiche auf Issue-Ebene, nicht diese Knotendaten.

### 5.1 Gate-Ereignisprotokoll

Der Gate-Runner schreibt je Lauf und Gate eine Zeile nach
`.git/process-gate-events.jsonl`: Gate, Modus (§6), Commit, Branch bzw. Issue,
Ergebnis, Dauer, Grund. Das ergänzt die bestehende Rot-Ledger; es ist eine
Beobachtung, keine neue Pflicht.

### 5.2 Überlappungsstichprobe

Blockiert ein Knoten, laufen die nachgelagerten Knoten normalerweise nicht.
Auf einer Zufallsstichprobe der Blockaden laufen sie trotzdem, nicht
blockierend, und protokollieren ihr Urteil. Daraus ergibt sich, welche Fänge
eindeutig sind und welche ein anderer Knoten ohnehin gemacht hätte.

## 6. Lebenszyklus einer Graph-Änderung

Jeder Knoten hat einen Modus in `gates.local.json` (für Reviews und Phasen in
der entsprechenden Konfiguration): `block`, `warn`, `shadow`, `sampled`, `off`.

| Änderung | Weg | Weiter, wenn |
|---|---|---|
| **Neuer Knoten** | `shadow` → `warn` → `block` | im Record genannte Mindestzahl Läufe; Fänge und Fehlalarme im Rahmen; Kosten bekannt |
| **Knoten abschwächen** | `block` → `sampled` (läuft nachträglich auf z. B. 10 % der Merges, nicht blockierend) → nach einer Bewährungszeit `off` oder dauerhaft `sampled` | Stichprobe findet keinen echten Fang; Leitplanken halten |
| **Knoten ändern** | alt und neu parallel, das neue im `shadow` | Urteile stimmen überein oder das neue fängt mehr bei vertretbaren Kosten |
| **Routing, Reihenfolge, Modell je Phase** | über `active()`-Flags als begrenzter Versuch (v2.67) | Kosten direkt gemessen; Leitplanken halten |

Dazu gelten wenige feste Regeln:

- **Automatischer Rückbau.** Findet die Stichprobe eines abgeschwächten Knotens
  einen echten Fang, kehrt er sofort auf `block` zurück. Reißt eine Leitplanke,
  werden die Änderungen im betroffenen Fenster in umgekehrter Reihenfolge
  zurückgenommen, die jüngste zuerst. Das schreibt ein Wächter, kein LLM.
- **Ein Abschwächen gleichzeitig je Leitplanke.** So bleibt zuordenbar, welche
  Änderung eine Leitplanke bewegt.
- **Freiraum beim Hinzufügen.** `shadow` und `warn` kosten nur Laufzeit und
  ändern keine Entscheidung. Die Schleife darf sie im Budget frei setzen.
- **Ehrliche Kennzeichnung.** Eine Bewährungszeit ohne Fang ist kein Beweis,
  dass nichts durchrutscht, sondern ein beobachteter Wert mit seiner
  Stichprobengröße. Für seltene, schwere Fehlerklassen reicht das nicht; dafür
  gibt es die geschützten Knoten.

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
| Neuer Knoten in `shadow`/`warn` | ✓ | — |
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

| Befund | In Revision 4 |
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

### Was bewusst anders gelöst wird (Verhältnismäßigkeit)

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
  cost, blocks, true catches, false alarms and unique catches, each with
  evidence count and data quality, and shall report unique catches as
  estimated with their sample size.
- **A3** When a node is in `shadow` or `sampled` mode, it shall run and record
  its verdict without blocking.
- **A4** When a `sampled` node records a true catch, the sentinel shall set the
  node back to `block` and record why.
- **A5** If a guardrail crosses its threshold, then the sentinel shall roll back
  the node changes in its window, newest first, and report the breach to the
  owner.
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
| v2.68 | P1 Messen | Gate-Ereignisprotokoll; `nodes`; Überlappungsstichprobe; `losses` (vier Maße); `outcomes`; Herkunft auf zwei Achsen |
| v2.68 | P2 Modi und Wächter | `block/warn/shadow/sampled/off` je Knoten; Leitplanken im Mandat; Wächter mit automatischem Rückbau; Owner-Bestätigung für jedes Abschwächen |
| v2.68 | P3 Schleifen | Aufträge wöchentlich und monatlich, harness-neutral; Berichtsformat |
| v2.69 | P4 Bewerter | vertrauenswürdiger Bewerter; danach darf der Steward ungeschützte Knoten selbst abschwächen |
| später | P5–P7 | Offline-Screen, Inert-Grenze für autonome Releases, Upstream-Kanal und Routine-Lease |

P1 liefert ab der ersten Woche eine Knotentabelle: Welche Gates kosten viel und
fangen wenig, welche fangen eindeutig? Das ist die erste konkrete
Optimierungsgrundlage, noch bevor die Schleife etwas verändert.

## 14. Offen an die nächste Prüfung

1. Ist „echter Fang = Blockade mit folgendem Fix-Commit“ ein tragfähiges Maß,
   oder lässt es sich durch triviale Fix-Commits aufblähen?
2. Reicht die Überlappungsstichprobe, um eindeutige Fänge zu schätzen, wenn
   nachgelagerte Knoten auf einem blockierten Stand anders reagieren als auf
   einem korrigierten?
3. Ist eine Stichprobe von 10 % für abgeschwächte Knoten genug, und wie lang
   muss die Bewährungszeit mindestens sein?
4. Sind die voreingestellten geschützten Knoten richtig gewählt — zu viele
   (Optimierung blockiert) oder zu wenige?
