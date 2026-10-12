# Plan (Entwurf, zur Refutation): Verbesserungsregelkreis mit Ausgleich — v2.68/v2.69

Datum: 2026-10-12 · Status: **Entwurf, nicht umgesetzt** · Baut auf: v2.67
(`docs/analysis/2026-10-12-self-improving-process.md`) · Tier: 3 (Messung,
Aktivierung und Freigabe des Prozesses ändern sich selbst)

Revision 3. Sie folgt auf zwei Refutationsrunden auf PR #216, beide mit
Verdict `block`:

- Runde 1: zehn Befunde zum Entwurf D1–D11.
- Runde 2: sieben Befunde zu Revision 2.

Revision 3 zieht zwei Konsequenzen:

1. **Weniger bauen.** v2.68 liefert nur, was ab Woche 1 nutzt und keine
   Autorität verschiebt. Die Grenze für Live-Übernahmen folgt in v2.69.
2. **Ein äußerer Rahmen gehört dem Owner.** Er legt fest, was als Erfolg
   gilt. Die Schleifen dürfen nur benannte, typisierte Parameter verstellen.

Wie jeder Befund beantwortet ist, steht in §10.

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
  ausgewertet wird. Dieses Beispiel ist Abnahmekriterium (§11, A6).

## 2. Owner-Entscheidungen

- **DECISION 2026-10-12 owner:** dev-process-Releases, die ausschließlich einen
  neuen, standardmäßig *ausgeschalteten* Mechanismus hinter einem Flag
  bringen, dürfen ohne Einzelfreigabe erscheinen — nach Gates, voller Suite und
  unabhängigem Review. Alles, was Verhalten ändert, bleibt beim Owner. Ausübbar
  erst mit der Inert-Grenze (P6, §12).
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
  (§7.4).

## 3. Grundgedanke

Der Kreislauf startet beim **Messen von Verlust und Wert**, nicht bei einem
Mechanismus. Welcher Mechanismus zuerst gebaut wird, entscheiden die Daten des
Projekts.

Vier Ebenen mit getrennter Autorität:

| Ebene | Wer | Darf |
|---|---|---|
| Äußerer Rahmen (§4) | Owner | Bedeutung von Erfolg, Grundgesamtheiten, Untergrenzen, Höchstrechte, absolute Budgets festlegen |
| Messung (§5) | deterministische Skripte, Wächter | beobachten und berechnen, nie entscheiden |
| Arbeitsschleife (§7.1) | wöchentliche Steward-Sitzung | eine priorisierte Maßnahme vorschlagen; typisierte Parameter im Rahmen verstellen |
| Meta-Schleife (§7.2) | monatliche Sitzung | nur beraten: Vorschläge zu Signalen, Regeln, Schleifen; Anwendung nach §8 |

Eine Ebene darf den Maßstab der darüberliegenden nicht verschieben. Diese
Grenze wird mechanisch geprüft und hängt nicht am guten Willen einer Sitzung
(R2-Befund 1).

## 4. Äußerer Rahmen (Owner)

Der Rahmen steht in einem eigenen Abschnitt `framework` des Mandats
`docs/process/optimization.local.json`. Er enthält:

- **Geschützte Bedeutungen.** Definition von O1 und O2 (§5.2), Richtung jeder
  Kennzahl, das Merkmal „störend“, das Merkmal „nutzbar“.
- **Grundgesamtheiten.** Für jede Frage und jede Kennzahl ist festgelegt,
  welche Elemente zählen (z. B. „Bugs mit Kanal `operator`“, nicht „alle
  neuen Bugs“).
- **Abdeckungs- und Prüfregeln.** Zielwerte für Abdeckung und Größe der
  Prüfstichprobe für die Klassifikationsgüte.
- **Untergrenzen.** Qualität, Sicherheit, Review-Unabhängigkeit, Abnahme. Sie
  sind nicht verrechenbar.
- **Höchstrechte** des Stewards und **absolute Budgets**: Agentenstunden und
  Owner-Minuten pro Woche für Optimierung.
- **`tunable`.** Die abschließende Liste der Parameter, die Schleifen
  verstellen dürfen, jeweils mit Typ, Spanne, größter Schrittweite und
  Mindestverweildauer.

Der Owner revidiert den Rahmen ausdrücklich. Die Schleifen können ihn nicht
mit ihren Parameterrechten ändern. `optimize.py register check` vergleicht
jede Änderung mit diesem Rahmen, egal ob sie über `set`, `revert`, Ablauf oder
eine direkte Dateibearbeitung entsteht. Eine Änderung ohne Log-Eintrag ist ein
Fehler. Jede Änderung ist an eine Register-Revision und ein Wirksamkeitsdatum
gebunden.

## 5. Messung

### 5.1 Verlustbuch — `process_kpis.py losses [--since] [--json]`

Das Verlustbuch führt **vier getrennte Maße**. Es rechnet sie nicht in eine
gemeinsame Währung um (R2-Befund 3):

| Maß | Einheit | Quelle | Bedeutung |
|---|---|---|---|
| Belegung | Agentenstunden | `flow` `work_s` | Kapazität, die tatsächlich verbraucht wurde |
| Verzögerung | Issue-Stunden | `flow` `wait_s`, `train-phases` | Wartezeit je Issue; zwanzig Issues, die eine Stunde auf dieselbe Störung warten, sind 20 Issue-Stunden Verzögerung, aber keine 20 Agentenstunden |
| Owner-Zeit | Owner-Minuten (geschätzt) und Zahl der Eingriffe | DECISION-Zeilen, Eskalationen | knappste Ressource |
| Tokens | Tokens je Feld | `issue_token_coverage` (Vollständigkeit je Nutzungsereignis) | Rechenkosten |

Dazu kommen **diagnostische Proxys** ohne Stundenwert:

- Review-Runden (`rounds`);
- Pfad-Anteile (`share`);
- Zug-Rauswürfe;
- Folgefehler-Zählung.

Proxys zeigen, wo man nachsehen sollte. Sie gehen in keine Budgetformel ein.

Dafür gelten feste Regeln:

- **Keine Doppelzählung.** Belegung entsteht nur aus `work_s`. Nacharbeit
  und Folgefehler sind Aufschlüsselungen dieser Belegung, kein Zusatz.
- **Unvollständig bleibt unvollständig.** Fehlende Beobachtungen bleiben
  sichtbar (`missing`, `estimated`, Abdeckung). `missing` heißt unbekannt,
  nie null, und auch die Entscheidungswege behandeln es so (§7.3).
- **Modellierte Werte sind geschätzt.** Eine Stundenumrechnung, etwa
  Owner-Minuten je Eingriff, trägt immer die Qualität `estimated` und nennt
  ihre Annahme.

### 5.2 Wertsignale — `process_kpis.py outcomes [--json]`

- **O1 Epic nutzbar.**
  - Ein Epic ist ein Issue mit nativen Sub-Issues. Als Fallback dient ein
    konfigurierter Titelpräfix oder ein Label.
  - **Nutzbar** heißt: Der im Rahmen festgelegte Abnahmenachweis liegt vor,
    zum Beispiel ein geschlossenes Abnahme-Issue mit ausgeliefertem
    Deploy-Nachweis.
  - Ein administrativ geschlossenes Epic gilt nur als schwächerer Proxy und
    wird so gekennzeichnet.
  - Kennzahl: Zeit vom Epic-Start bis „nutzbar“.
  - Diagnostisch, ohne Wertung: Durchsatz der Sub-Issues und Alter offener
    Epics. Beides steigt oder fällt auch durch Aufteilen und bloßes Warten.
  - „O1 verschlechtert sich“ ist im Rahmen definiert, und zwar über die
    Zeit bis „nutzbar“ abgeschlossener Epics. Das Alter offener Epics zählt
    dafür nicht.
- **O2 Störender Fehler schnell behoben.**
  - Gezählt werden Bugs mit Kanal `operator` (§6), die das Merkmal „störend“
    des Rahmens tragen, etwa ein Prioritätslabel.
  - Gemessen wird die Zeit von der Meldung bis zum ausgelieferten Fix.
    Endpunkt ist Deploy, falls konfiguriert, sonst Merge, gekennzeichnet nach
    der `flow`-Logik.
- **O3 Betrieb (optional).** Schema für `.process-work/ops/YYYY-MM-DD.json`
  aus dem projekteigenen Host-Skript; nur Zählwerte.
- **Nicht verfügbar.** Ein Projekt ohne Epics, ohne Betriebsdaten oder ohne
  Kanalfeld bekommt `unavailable` mit Grund, nie eine Null.

### 5.3 Wächter

Wächter sind billige deterministische Prüfungen. Sie laufen **unabhängig von
jedem Optimierungsbudget**, unter einer kleinen reservierten Überwachungszulage
im Rahmen. Sie prüfen:

- **Untergrenzen:** Gates rot, Rollback, Abnahme verletzt.
- **Stopp-Bedingungen** laufender Versuche.
- **Folgefehler:** neue Folgefehler zu übernommenen Maßnahmen.
- **Abdeckung:** Einbruch der Abdeckung eines Fragenfelds.
- **Datenqualität:** Kennzahl kippt nach `missing`.

Ein Wächter entscheidet nichts. Schlägt er an, weckt er die zuständige
Schleife (§7.3).

## 6. Herkunft von Bugs: zwei Achsen

Ein einzelnes Herkunftsfeld kann einen vom Owner gemeldeten Folgefehler nicht
abbilden (R2-Befund 4). Deshalb gibt es zwei Achsen:

| Achse | Werte | Zweck |
|---|---|---|
| Ursache | `regression` (mit `Regression-of: #N`, eingeführt durch), `preexisting`, `unknown` | Folgefehlerquote |
| Kanal | `operator`, `agent`, `monitor`, `other` | O2, Entdeckungswege |

Dazu gehören:

- **Zeitstempel und Konfidenz.** Erfasst werden Melde- und Entdeckungszeitpunkt
  sowie die Konfidenz der Klassifikation.
- **Unbekannt ist zulässig.** Eine spätere Korrektur auf Basis neuer Belege
  hängt sich an und überschreibt die Historie nicht.
- **Gesetzt wird dort, wo es bekannt ist.**
  - Der Agent, der einen Folgefehler anlegt, setzt `regression`/`agent`.
  - Die Steward-Sitzung setzt bei einer Owner-Meldung `operator` und eine
    Ursache, falls sie bekannt ist, sonst `unknown`.

  Wenn alle Issues über dasselbe Konto entstehen, trennt das Autor-Konto die
  Fälle nicht.
- **Abdeckung und Güte getrennt.**
  - Abdeckung ist der Anteil der Elemente mit Feld.
  - Güte wird an einer geprüften Stichprobe gemessen, die eine unabhängige
    Sitzung gegen Commits und Belege klassifiziert.
  - Die Folgefehlerquote bekommt die Qualität `measured` erst, wenn beide
    Ziele des Rahmens erfüllt sind und das Beobachtungsfenster reif ist.
  - Ein fehlender Trailer zählt nie als null Defekte.

## 7. Schleifen

### 7.1 Arbeitsschleife (wöchentlich)

- **Auslöser:** Routine bzw. Steward-Sitzung, Auftrag
  `docs/process/improvement-weekly.md`.
- **Eingang:** Verlustbuch, Wertsignale, Wächterbefunde, Fragen-Register.
- **Ergebnis:** genau **eine priorisierte Maßnahme** mit Begründung, Prognose
  und Kosten im absoluten Budget, oder „kein Eingriff“.
  - Eine Maßnahme kann ein Experimentvorschlag, ein Produktsignal (ein Issue
    für die Lieferarbeit) oder eine Frage für das Fragen-Register sein.
- **Grenzen:** Die Schleife verstellt nur Parameter aus `tunable`.
- **Gedächtnis:** `.process-work/improvement/YYYY-Www.md`, Register-Log.

**Blinde Flecken finden.** Die Arbeitsschleife bildet dazu Hypothesen, in
engen Grenzen (R2-Frage 3):

- **Stichprobe:** reproduzierbar, aus neuen Issues, Commits und Journalzeilen,
  mit Negativbeispielen.
- **Abgleich:** gegen vorhandene Fragen.
- **Beleg und Abnehmer:** Ein Vorschlag braucht beides — Belege und eine
  benannte Entscheidung, die die Antwort braucht.
- **Vorläufige Frage:** Ein Fund wird zunächst eine vorläufige Frage, noch
  kein Pflichtfeld.
- **„Keine neue Frage“** ist ein zulässiges Ergebnis.

Die Eskalation geht vom Hinweis über das Pflichtfeld im Issue-Helfer und die
weiche Notiz bis zum Gate. In v2.68 wird jede Stufe **vorgeschlagen und
manuell angewendet**: Stufen 1–2 vom Steward, ab Stufe 3 vom Owner. Eine
automatische Eskalation ist zurückgestellt.

### 7.2 Meta-Schleife (monatlich, beratend)

Auftrag: `docs/process/improvement-monthly.md`. Die Schleife prüft:

- **Signale:** Abdeckung, Güte, Streuung, Manipulierbarkeit.
- **Regeln:** Prognose gegen Ist.
- **Maßnahmen:** ob eine übernommene Maßnahme unter neuem Modell, Harness oder
  Projektstand noch trägt; gegebenenfalls ein Ablationsvorschlag.
- **Schleifen:** Nutzen und Kosten.

Sie schreibt **Vorschläge**, keine Änderungen. Angewendet wird nach §8.

**Prognose-Trefferquoten sind beratend.** Sie erweitern keine Rechte
(R2-Frage 7). Voraussetzung für eine spätere Kopplung an Rechte:

- vorregistrierte, quantifizierte Prognosen;
- vollständige Zählung der aufgelösten und unaufgelösten Prognosen;
- Kalibrierung *und* Nutzen.

### 7.3 Steuerung: Vorrang, Totband, Verweildauer, Wiederanlauf

Die Steuerung folgt aus R2-Befund 7 und R2-Frage 5.

- **Ein Schreiber.** Budgets und Parameter schreibt nur
  `optimize.py register`. Es gilt eine feste Vorrangordnung:
  1. Sicherheit und Stopp;
  2. Pflichtbeobachtung (Wächter);
  3. budgetierte Optimierung.
- **Unbekannt ist kein Produktproblem.** Verschlechtern sich O1 oder O2, ohne
  dass ein *gemessener* Prozessverlust das erklärt, aber Messdaten fehlen, so
  lautet der Befund „unbekannt“. Die nächste Maßnahme ist dann, die Lücke zu
  schließen, nicht das Prozessbudget zu kürzen.
- **Totband, Mindestbeobachtungen, Schrittgrenzen, Verweildauer.** Ein
  Parameter ändert sich nur:
  - mit einer Mindestzahl Beobachtungen;
  - wenn der Effekt außerhalb eines Totbands liegt;
  - höchstens um die größte Schrittweite;
  - frühestens nach seiner Mindestverweildauer.

  Eine Gegenrichtung innerhalb der Verweildauer ist unzulässig.
- **Verfall** (`review_by` erreicht) ist eine versionierte Entscheidung. Er
  setzt auf den Rahmen-Startwert zurück und erweitert nie die aktuelle
  Autorität.
- **Pausieren statt abschalten.** Teure Analyse kann pausieren, Wächter laufen
  weiter. Jede pausierte Schleife hat eine **ereignisbasierte
  Wiederanlaufbedingung**, zum Beispiel: neuer Folgefehler → Folgefehler-Analyse
  läuft wieder an.
- **Rückbau nach Nutzen.** Eine Schleife wird nach geprüfter Abdeckung, Nutzen
  und Kosten zurückgebaut, nicht nach der Zahl ihrer Eingriffe.
- **Tests mit Störungen.** Wiedergegebene oder synthetische Störungen prüfen,
  ob ein Ereignis übersehen wird, wie schnell die Reaktion kommt und ob die
  Steuerung schwingt. Live-Streuung allein ist in kleinen Projekten schwache
  Evidenz.

### 7.4 Wer die Schleifen ausführt

Der Plan legt kein Modell fest. Jede Schleife muss mit jedem unterstützten
Harness laufen, mindestens mit Claude Code und Codex.

- **Harness-neutrale Aufträge.** Die Aufträge liegen unter `docs/process/`.
  Die Harness-Adapter (`.claude/commands/`, `AGENTS.md`) verweisen nur darauf.
  Ergebnisse sind Dateien und Register-Befehle.
- **Unabhängige Prüfsitzung.** Sie ist mehr als eine frische Sitzung
  (R2-Frage 8):
  - Sie implementiert nicht selbst.
  - Sie liest Belege nur an der exakten Revision, ohne Schreibrecht.
  - Sie hat die geltenden Regeln.
  - Sie erbt keinen Gesprächsverlauf.
  - Ihre Prüfungen sind reproduzierbar.
  - Sie hat eigene Autorität.
- **Protokoll und Modellfamilie.** Modellfamilie, Rolle und Herkunft jedes
  Akteurs stehen im Log. Wo die Tier-Regeln eine Prüfung durch eine andere
  Modellfamilie verlangen, gilt das weiter, sofern verfügbar. Sonst wird die
  Einschränkung ausdrücklich vermerkt. §7.4 ersetzt die Tier-Regeln nicht.

### 7.5 Schleifen-Register und Sättigung

Startbestand in v2.68: **zwei geplante Schleifen** (wöchentlich, monatlich)
plus Wächter. Folgefehler, Abdeckung, Kosten und Ergebnis sind Abschnitte des
Wochenberichts, keine eigenen Taktgeber.

Eine weitere Schleife mit eigenem Takt entsteht nur, wenn zwei Bedingungen
erfüllt sind:

1. Ein Verlust oder eine Frage ist nachweislich unabgedeckt.
2. Der Wochenbericht kann sie nicht abdecken.

Die Obergrenze aktiver Schleifen ist ein Rahmenwert. Gemessen wird
Stabilisierung, nicht Aktivität:

- übersehene Ereignisse in Störungstests;
- Reaktionszeit;
- Richtungswechsel von Parametern;
- Kosten.

## 8. Rechte

| Änderung | Steward allein | Owner |
|---|---|---|
| Maßnahme vorschlagen, laufenden Versuch stoppen | ✓ | — |
| Parameter aus `tunable` im Rahmen (Typ, Spanne, Schritt, Verweildauer) | ✓, mit Prognose; umkehrbar | sieht es im Monatsbericht |
| Bedeutung, Grundgesamtheit, Nenner, Abdeckungs- und Prüfregel, Untergrenze, Recht, Budget | — | ✓, nach unabhängiger Prüfsitzung (§7.4) |
| Neues Signal nach der Parallelperiode übernehmen | — | ✓ (die Parallelperiode ist Beobachtung, keine Freigabe) |
| Feld-Eskalation Stufe 1–2 | ✓ | — |
| Feld-Eskalation Stufe 3–4, Gates, Tiers | — | ✓ |
| Übernahme eines Experiments | **v2.68: nur Owner.** Erst ab v2.69 mit vertrauenswürdigem Bewerter (§9.2) delegierbar über `steward_may` | ✓ |
| Ablation geschützter Kontrollen (Sicherheit, Tier, Review-Unabhängigkeit, Abnahme) | — | nie per Optimierungsmandat |

Die delegierte Übernahme aus v2.67 wird in v2.68 also eingeschränkt. Das ist
eine Verhaltensänderung und deshalb Teil des Owner-Releases.

## 9. Experimente (v2.69, Voraussetzung jeder delegierten Übernahme)

### 9.1 Evidenz, die ein kleines Projekt liefern kann

Ereignisraten lösen das Stichprobenproblem nicht. Jedes Issue bleibt eine
unabhängige Beobachtung. Der Vergleich von 50 % mit 40 % braucht rund 388
Issues pro Arm (R2-Befund 6). Daraus folgt:

- **Vorab festgelegt** werden:
  - Schätzgröße (Estimand), absoluter bzw. relativer Effekt;
  - Analyseeinheit und Umgang mit Clustern;
  - Stichprobenbudget;
  - Fehlwert- und Reiferegeln;
  - eine maschinell prüfbare Regel für `pass | fail | inconclusive`.
- **Untergrenzen bleiben getrennt.** Weniger Fänge in Runde 1 sind kein Beleg
  für bessere Qualität. Die Abnahme- und Folgefehler-Untergrenzen werden
  eigens geprüft.
- **Ehrliche Kennzeichnung.** Reicht das Budget nicht für den Nachweis, heißt
  das Ergebnis `inconclusive`. Eine Übernahme ist dann höchstens ein
  **umkehrbarer Versuch** mit der Kennzeichnung „diagnostische Evidenz, kein
  nachgewiesener Effekt“. Wächter überwachen ihn weiter, Rückbau-Auslöser
  sind festgelegt.
- **Gepaarter Offline-Screen** (P5) bleibt ein Aussortier-Instrument.

### 9.2 Vertrauenswürdiger Bewerter

Bewertet wird von einem **getrennt aufgelösten Bewerter-Commit** aus (R2-Befund 2):

- **Basis.** Das ist der Basis-Tag, aufgelöst auf die unveränderliche
  Commit-ID.
- **Eigener Baum.** Der Bewerter läuft in einem eigenen exportierten Baum,
  mit vollständigem Code-, Import- und Abhängigkeitsabschluss und
  eingefrorener Messkonfiguration.
- **Kandidat ist nur Gegenstand.** Kandidaten-Code ist nie Import oder
  ausführbare Eingabe des Bewerters.
- **Bindung.** Das Ergebnis ist gebunden an Bewerter-Commit, Candidate-/Base-SHA,
  Terms-Hash, Zuteilungsmanifest und Rohdaten-Manifest.
- **Zwei Zeitpunkte.** Die vorab erklärte Erhebungs- und Kohortenspezifikation
  steht im Freeze. Der Datensatz-Hash entsteht erst bei der Auswertung.
- **Pfadliste nur zusätzlich.** Die Liste geschützter Pfade bleibt als
  Ergänzung, sie ersetzt die Grenze nicht.
- **Negativtest.** Ein Kandidat ändert einen transitiven Leser, etwa
  `dispatch.issue_token_coverage`. Das vertrauenswürdige Urteil darf sich
  dadurch nicht ändern.

### 9.3 Zuteilung

- **Vorab festgelegt.** Zulässigkeit und Zuteilung werden vor der Auswahl der
  Arbeit persistiert, je Issue einmal.
- **Zufälliges Salz.** Die unabhängige Prüfsitzung erzeugt das Salz zufällig
  beim `REVIEWED`-Eintrag. So kann der Vorschlagende kein Salz suchen, das zu
  bekannten Issue-Nummern passt.
- **Geblockt nach Tier.**
- **Zuteilung und Exposition getrennt.** Abbruch, Fehler und Abweichung werden
  erfasst. Ausgewertet wird alles Zugeteilte.
- **Protokoll.** Modell- und Umgebungswechsel sowie Wechselwirkungen werden
  protokolliert.

### 9.4 Übernahme bleibt erhalten

`adopted` trägt atomar einen Eintrag in `optimization.local.json → adopted[]`
ein (`flag`, `record`, `terms_hash`, `release`). `active()` meldet „on
(adopted OPT-n)“, der Pilot-Sinn bleibt getrennt.

Weitere Regeln:

- **Rückbau:** Eintrag entfernen und den Record nach `rolled-back` setzen.
- **Kompatibilität:** Ein Release, das die Maßnahme nicht kennt, meldet sie
  als `unknown`, nicht als `on`.
- **Test:** Er prüft das Verhalten nach der Übernahme.

## 10. Antwort auf die Refutationsbefunde

### Runde 2

| # | Befund | Antwort |
|---|---|---|
| 1 | Änderungen im Rahmen verschieben, was als Erfolg oder blinder Fleck gilt | §4 äußerer Rahmen mit geschützten Bedeutungen, Grundgesamtheiten, Prüfregeln; nur `tunable` verstellbar; Prüfung auch bei Ablauf und direkter Bearbeitung; neues Signal braucht Owner-Entscheidung; Trefferquoten nur beratend (§7.2) |
| 2 | Pfadliste isoliert den Bewerter nicht | §9.2 getrennter Bewerter-Baum am unveränderlichen Commit, Kandidat nie importiert, Negativtest mit transitivem Leser |
| 3 | Verlustbuch mischt Verzögerung, Belegung, Zählwerte, Tokens | §5.1 vier getrennte Maße, Proxys nur diagnostisch, keine Doppelzählung; adaptives Budget R1 zurückgestellt, absolutes Owner-Budget (§4) |
| 4 | Ein Herkunftsfeld bildet Owner-gemeldete Folgefehler nicht ab | §6 zwei Achsen, `unknown`, Konfidenz, Abdeckung und Güte getrennt; A6 um zwei Fälle erweitert |
| 5 | Token-Abdeckung je Datei statt je Aufruf | **Behoben in 92a3e49:** Vollständigkeit je Nutzungsereignis; nicht-JSON-Zeilen decken nichts ab; Testfall aus der Refutation plus Mutationsprüfung |
| 6 | Ereignisraten lösen das Stichprobenproblem nicht | §9.1 vorab festgelegte Schätzgröße und Regel, `inconclusive` ehrlich, umkehrbarer Versuch statt Nachweis; delegierte Übernahme erst v2.69 |
| 7 | Rückbau stiller Schleifen und gemeinsames Budget legen die Erholung lahm | §5.3 Wächter mit reservierter Zulage; §7.3 ein Schreiber, Vorrang, „unbekannt“ statt Produktproblem, Totband, Verweildauer, Wiederanlauf, Rückbau nach Nutzen |

### Runde 1 (Stand nach Runde 2)

| # | Befund | Stand |
|---|---|---|
| 1 | Experiment ändert den Maßstab | §4, §9.2 |
| 2 | Flag-aus-Neutralität | Tupel-Wahrheitswert behoben (0557b2e); autonome Releases erst mit P6 |
| 3 | Zuteilung, Überlappung | Überlappung behoben (0557b2e); §9.3 |
| 4 | Pass-Regel, n | §9.1 |
| 5 | `flow`-Vollständigkeit | behoben (0557b2e, 92a3e49) |
| 6 | Offline-Isolation | P5, Richtung bestätigt |
| 7 | Übernahme geht verloren | §9.4 (v2.69) |
| 8 | Upstream-Kanal | P7 |
| 9 | Routine-Budget, Lease | P7; Wächter-Zulage §5.3 |
| 10 | Handover-Paket | kein vorab gewählter Mechanismus mehr |

## 11. Abnahme (EARS)

- **A1** When `process_kpis.py losses` runs, the system shall report occupancy
  (agent hours), delay (issue hours), owner effort and tokens as separate
  measures with evidence count and data quality. It shall never sum them,
  never count a breakdown twice, and never report `missing` as zero.
- **A2** When `process_kpis.py outcomes` runs, the system shall report per epic
  the time to the framework's usable marker, mark administrative closure as a
  weaker proxy, and report `unavailable` with a reason where the project has
  no epics, no channel field or no operations data.
- **A3** When a register entry changes through `set`, `revert`, expiry or a
  direct file edit, `optimize.py register check` shall refuse it unless the
  parameter is listed in `tunable` and the change respects type, range, step,
  dwell and a log entry bound to a register revision.
- **A4** When a change touches a meaning, population, denominator, coverage or
  audit rule, floor, right or budget, the system shall require an owner
  decision recorded after an independent review session.
- **A5** When a signal definition changes, the system shall report the old and
  new values side by side for one period. The new definition shall apply only
  after an owner decision.
- **A6 (Herkunft, Beispiel des Owners)**
  - When fewer than the framework's target share of bugs in the population
    carry the cause and channel fields, the weekly loop shall record a blind
    spot and propose the issue-template field.
  - When the owner reports a regression introduced by #N, the record shall
    carry cause `regression` with `Regression-of: #N` and channel `operator`,
    and it shall count in both the regression share and O2.
  - While every bug carries the fields but the audited sample's agreement is
    below target, the regression share shall stay `estimated`.
  - Once coverage, audited agreement and window maturity all meet target,
    `losses` shall report the regression share as `measured`.
- **A7** When the weekly loop finds a recurring free-text pattern, it shall
  propose a provisional question only with evidence, a named decision consumer
  and a duplicate check. "No new question" shall be a valid result.
- **A8** While a loop is paused, its sentinel shall keep running. When the
  sentinel's event fires, the loop shall resume.
- **A9** If O1 or O2 worsens while process data are `missing`, then the system
  shall report "unknown" and propose closing the gap, and shall not lower the
  optimization budget.
- **A10** When a parameter changes, the system shall refuse a reverse change
  within its dwell period and any change below the deadband or above the step
  limit.
- **A11** While v2.68 is installed, `optimize.py move … adopted` shall require
  an owner decision whatever `steward_may` says.
- **A12 (v2.69)** When a candidate changes a transitive measurement reader,
  the trusted evaluator's verdict shall not change.
- **A13 (v2.69)** When an experiment is adopted, `active()` shall report it on
  outside any pilot window. A release that does not know the measure shall
  report it unknown. A rollback shall report it off.

## 12. Pakete und Reihenfolge

| Release | Paket | Inhalt | Nutzen |
|---|---|---|---|
| v2.68 | P1 | `losses` (vier Maße, Proxys), `outcomes`, Ops-Schema; Zwei-Achsen-Herkunft (Vertrag, Template-Hinweis, Leser) | Woche 1 |
| v2.68 | P2 | äußerer Rahmen im Mandat, `tunable`, `optimize.py register set/revert/check`, Log, Wächter | Woche 1 |
| v2.68 | P3 | Aufträge wöchentlich (eine Maßnahme, absolutes Budget) und monatlich (beratend); Berichtsformat; Übernahme nur durch den Owner | Woche 2 |
| v2.69 | P4 | vertrauenswürdiger Bewerter, Zuteilung, dauerhafte Aktivierung, vorab festgelegte Auswertungsregel | vor der ersten delegierten Übernahme |
| später | P5–P7 | Offline-Screen, Inert-Grenze für autonome Flag-aus-Releases, Upstream-Kanal und Routine-Lease | wenn die Daten den Bedarf zeigen |

Zurückgestellt:

- adaptives Budget R1 (erst mit gemessenem Abrechnungsvertrag);
- an Trefferquoten gekoppelte Rechte;
- automatische Feld-Eskalation;
- Schleifen mit eigenem Takt über die zwei geplanten hinaus;
- JSON-Records;
- Topologiesuche.

## 13. Offen an die nächste Refutation

1. Ist der äußere Rahmen (§4) klein genug, damit der Owner ihn pflegt, und
   vollständig genug, um R2-Befund 1 zu schließen?
2. Reicht die Prüfung „Änderung ohne Log-Eintrag ist ein Fehler“ gegen direkte
   Dateibearbeitung, oder braucht es eine Signatur bzw. eine Gate-Prüfung beim
   Push?
3. Sind vier getrennte Maße ohne gemeinsame Währung noch entscheidbar für
   „größter Hebel“, oder braucht die Arbeitsschleife eine explizite,
   owner-gesetzte Gewichtung im Rahmen?
