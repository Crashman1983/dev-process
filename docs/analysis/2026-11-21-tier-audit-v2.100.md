# Prozessaudit aller vier Tiers · 21. November 2026

**Entscheidungsvorlage für v2.101.** Die größten konkreten Kürzungsmöglichkeiten sind die manuelle Vorarbeit für Kennis Governance-Quick-Pfad, wiederholte Begründungen im Plan und doppelte Übertragung bereits vorhandener Reviewbelege. Bei Zustandsänderungen über mehrere Komponenten verschiebt sich die Prüfung der entscheidenden Annahme nach vorne. Bei einer plattformabhängigen Bedienhandlung bleibt die Prüfung am wirklichen Client wertvoll.

Untersucht sind die fachlich unterschiedlichen Schritte des v2.100.0-Workflows, die optionalen Pfade und die registrierten Gates. Shell-Unterbefehle, jede einzelne Testfunktion und alle möglichen Kombinationen der optionalen Module bilden keine separaten Prozessschritte. Vergleichsbasis ist Kenni auf b95197152 vom 20. November mit installiertem v2.98.0, Spec Kit, lokalen Overlays und manuellem GitHub-CI-Modus. „Kenni-Regel“ bezeichnet dokumentiertes Soll. Ein Issue-Verweis bezeichnet eine beobachtete Ausführung. Einsparungen sind Vorschläge, soweit keine bereits vorhandene Abkürzung ausdrücklich genannt ist. [Template](https://github.com/Crashman1983/dev-process/tree/v2.100.0) · [Kenni-Konfiguration](https://github.com/Crashman1983/kenni/blob/b95197152596fb31ab358f9c794b88e9e0409c87/.copier-answers.yml)

## Mit welchem Gewicht ist welche Aussage belegt?

November-Journaldateien am untersuchten Stand, ausgewertet mit Kennis eigenem Review-Leser. Eine Kennung zählt einmal je Phase, nach höchstem angegebenem Tier. Angegeben sind Arbeitskennungen mit mindestens einem Block / alle beobachteten Kennungen. Ein fehlender Journalnachweis erlaubt keinen Rückschluss auf die Anzahl direkt gelandeter Änderungen.

| Tier | Plan | Code | Konsequenz |
|---|---:|---:|---|
| 0 | 0/0 | 0/0 | Aufwand am Prozess und Diff untersuchen. Aus dem Journal lässt sich kein Zeitgewinn schätzen. |
| 1 | 0/0 | 0/2 | Kleine Stichprobe. #3053 dokumentiert Selbstprüfung, Bundle und 36 grüne Pin-Tests; Gate-Konfiguration war berührt. Kein Musterfall für einen gewöhnlichen Tippfehler. |
| 2 | 7/42 | 17/50 | Ein zusätzlicher Prüfdurchgang bei jeder Arbeit träfe viele Arbeiten ohne dokumentierten Block. Frühe Prüfung nach konkreter Unsicherheit auswählen. |
| 3 | 15/23 | 12/23 | Unabhängige Prüfung findet häufig einen Block. In #2822 hätte ein Fehler im Fix die letzte verifizierte Indexgeneration löschen können. |

Bei 32 gemergten Branches mit zuordenbarem explizitem Review-Pass betrug der Median vom letzten Pass bis Merge 1 h 31 min, sieben lagen bei mindestens acht Stunden. Das ist Kalenderzeit; Host-Wartezeit, Testlauf und Zugplanung sind darin gemeinsam enthalten. Auch 60 % reine Prozess-Commits über vier Wochen sind eine Pfadklassifikation. Keine der beiden Zahlen ist ein Budget für streichbare Prüfungen. [Reproduktion der Journalbasis](2026-11-21-v2.101-plan.md) · [#3053](https://github.com/Crashman1983/kenni/blob/b95197152596fb31ab358f9c794b88e9e0409c87/.process-work/journal/issue-3053/2026-11-20.md) · [#2822](https://github.com/Crashman1983/kenni/blob/b95197152596fb31ab358f9c794b88e9e0409c87/.process-work/reviews/2026-11-03-2822-d1-r2.md)

## Matrix für die Arbeit im Repository

Die vier Zahlen in der Spalte **Route 0/1/2/3** bezeichnen die Tiers in dieser Reihenfolge. **J** bedeutet regulärer Schritt, **B** bedingt durch Inhalt, Phase, Projektregel oder Betriebsart, **–** entfällt im normalen Pfad. Die genaue Ausprägung steht in der Zeile. Sobald der Umfang die Tiergrenze überschreitet, gilt die höhere Route. DoR und DoD werden an ihrem Übergang beurteilt; begründete Abweichungen bleiben dort nachvollziehbar. Die Matrix ersetzt keine lokale Freigabe zur Absenkung eines Gates.

### A · Start, Einstufung und Bereitschaft

| Schritt | Route 0/1/2/3 | Kenni und Entscheidung |
|---|---|---|
| Prozess installieren, Brownfield einrichten, Projektprofil und Harness wählen | B/B/B/B | Einmal pro Einrichtung bzw. Update. Kenni hat bereits lokale Hooks/Prozessintegration und manuelles CI. Bootstrap aus dem Tagesablauf heraushalten; nach Update die tatsächliche Durchsetzung prüfen. |
| Sitzung starten, Kontext laden, nach Unterbrechung wiederherstellen | B/B/B/B | Kernel und betroffene lokale Overlays verfügbar machen. Quick verweist auf zwei Kernfragen. Volle Workflow- und Stack-Dokumentation erst öffnen, wenn Änderung oder Unklarheit sie braucht. |
| Issue, Typ, Produktziel, Story/Epic, Abhängigkeiten identifizieren (R1, R3, R4) | B/B/J/J | Bestehendes Kenni-Issue und Links verwenden. Ein Issue pro geänderter Plattform bringt bei identischem Ziel keinen Mehrwert. Getrennte Zuständigkeit, Liefertermine oder Hardware-Wartezeiten können Sub-Issues rechtfertigen. |
| Claim, Branch, Worktree, WIP und Überschneidungen | B/B/B/B | Im parallelen Betrieb bestehende Tower-Daten nutzen, auch gemeinsame Story- und Vertragsdateien ansehen. #2848 bezahlte nach grünem Review eine zusätzliche Runde für eine Registry-Konfliktauflösung. Nur die Integration der kollidierenden Arbeiten ordnen. |
| Tier, Mutationsklasse und Reviewtarif bestimmen | J/J/J/J | Kenni trennt Risiko von runtime, governance-only und mechanical-docs. Der Tarif tempo/qualitaet betrifft die Prüftiefe. Einstufung einmal am Change begründen und bei Scope-Erweiterung neu beurteilen. Tier-3-Designpflichten für rein optischen Feinschliff zu kopieren wäre unnötig. |
| Governance-only-Vorprüfung für bereits gefällte Entscheidungen | B/B/B/B | Kenni fordert zwölf Angaben. Soll-Branch, Soll-Basis und Allowlist aus dem Auftrag beziehen; Ist-Worktree, Ist-Branch, Merge-Basis, fremde Dateien und Diff automatisch dagegen prüfen. Ziel, Entscheidungsowner, Claim-Delta und Abschlussziel sind menschliche Entscheidungen. Ein bloßes Kopieren des Ist-Branchs in das Soll-Feld zerstörte den Schutz. Rein redaktionelle Änderungen haben einen eigenen Pfad. |
| Quick statt eigener Planakte | B/J/–/– | T0 ohne Verhaltensänderung direkt, T0 mit isoliertem Verhalten und T1 per Quick. Ein beobachtbarer Satz, Dateien, Risiko und ggf. Endzustand genügen. Für Quick keine reguläre Spec, keine separate Plansitzung. Lokale Governance-Ausnahme behält das abgeleitete Tier. |
| Debug, Reproduktion, wiederkehrende Fehlerklasse | B/B/B/B | Bei Defekt erst kleinster reproduzierbarer Fehler. Bei wiederholten Fixes Historie und Ursache hinzunehmen. Das volle Debug-Verfahren bei einer eindeutigen Textkorrektur weglassen. Bei wiederholter Änderung am gleichen Verhalten schützt ein Invarianten-Test vor einem weiteren Einzelfix. |

Quellen: [Template-Workflow](https://github.com/Crashman1983/dev-process/blob/v2.100.0/template/docs/process/workflow.md.jinja) · [Kenni-Tiermatrix und Mutationsklassen](https://github.com/Crashman1983/kenni/blob/b95197152596fb31ab358f9c794b88e9e0409c87/docs/dev/process-risk-tiers.md) · [Kenni-Quick](https://github.com/Crashman1983/kenni/blob/b95197152596fb31ab358f9c794b88e9e0409c87/docs/process/commands/quick.local.md) · [Konflikt #2848](https://github.com/Crashman1983/kenni/blob/b95197152596fb31ab358f9c794b88e9e0409c87/.process-work/reviews/2026-11-07-2848-r3.md)

### B · Brainstorming, Spezifikation und Planning

| Schritt | Route 0/1/2/3 | Kenni und Entscheidung |
|---|---|---|
| Brainstorm und Entscheidung des Owners | –/–/B/J | T2 bei offener Produktentscheidung, T3 vorgelagertes Design; Kenni nutzt vollständiges Brainstorming nach Bedarf. In #2322 änderte „falsche Instanz zulassen oder abbrechen?“ den gesamten Lösungsweg. Diesen Fall einmal entscheiden. Bereits gebilligte Entscheidungen referenzieren. |
| Wegwerf-Spike | –/–/B/B | Nur wenn die Entscheidung über Machbarkeit oder gemeinsamen Vertrag ohne Experiment offenbleibt. Den Versuch als eigene Arbeit mit Endbedingung schneiden. Kein produktiver Prototyp als Nebenprodukt des Plans. |
| Spec Kit Specify, Akzeptanz und betroffene Surfaces (R2) | –/–/J/J | Kenni hat Spec Kit aktiviert. Eine fachliche Story mit stabilen AC-IDs; Erfolg, relevante Negativ-, Grenz-, Berechtigungs- und Aufräumfälle an derselben Stelle. Web/Apple können dasselbe Verhalten mit verschiedenen Renderern erfüllen. |
| Clarify | –/–/B/B | Offene Marker vor dem Plan auflösen. Stehen Ergebnis und Randfälle fest, genügt der vorhandene Prüfpfad. Keine zweite Fragerunde für bereits beantwortete Fragen. |
| UI-Bestand, Wiederverwendung, Designvertrag und ggf. Designrunde (R5) | B/B/B/B | Vor UI-Arbeit bestehende Komponenten, Norm und Referenz prüfen. Eigene Konzeptboards und unabhängiges Design-GO nur, wenn der Designgegenstand es verlangt. Ein bestehendes akzeptiertes Muster referenzieren. Ein Konflikt mehrerer ID-Familien im selben Plan ist ein Template-Fehler. Gate und Review-Bundle gemeinsam korrigieren. |
| Architekturentscheidung, Produktanker, Threat-/Fehleranalyse | B/B/B/J | Bestehende ADR nutzen, neue bedeutende Entscheidung vor dem sie voraussetzenden Code dokumentieren. Vertiefte Bedrohungsanalyse bei den definierten T2-Risiken und T3. Kennis Einzelbetreiber-Kontext gehört in die lokale Bewertung; v2.100 erlaubt die enge Härtungsausnahme nur bis Tier 2 und mit konkreten Belegen. Abweichende lokale Aussagen beim Update abgleichen. |
| Plan, betroffene Verbraucher, Zustandsregel und Übergänge | –/–/J/J | In #2980 hätte eine vorhandene Swift-Klasse die vorgeschlagene Annahme bereits widerlegt. Im Plan genügt Lesen oder ein vorhandener Befehl. Neue Parser, Adapter und dauerhafte Tests beginnen in Execute. Bei #2333-d war die Zustandsordnung entscheidend; bei Zustandsänderungen beibehalten. |
| Tasks, Testverweise, parallele Pakete, Modellwahl | –/–/J/J | Gemeinsam festgelegten Vertrag und disjunkte Dateien voraussetzen. Test und Implementierung desselben Verhaltens als ein Paket. Kennis leichtes Modell für mechanische Pakete nutzen, wenn der Übergabeaufwand kleiner als der Arbeitsgewinn ist. Lokales Overlay nennt die bisherige Größenfaustregel. |
| Optionale Spec-Kit-Analyse und Checklist | –/–/B/B | In v2.100 bereits auf Abruf. Bei konkretem Widerspruch zwischen Artefakten nützlich. Ein routinemäßiger zusätzlicher LLM-Durchgang wäre doppelte Planprüfung. |
| Plan-Bundle und unabhängiges Plan-Review | –/–/J/J | T2 frischer Prüfkontext, T3 zweite Familie gemäß Policy. Plan-Bundle vermeidet bereits den vollen Code-Preflight. Reviewer prüfen Entscheidung und Belege. Ein fertiger Produktnachweis als Vorbedingung würde die Planung zur Implementierung machen. |
| Plan-Block, Überarbeitung, erneute Freigabe | –/–/B/B | Bei #2322 waren zwei Records teilweise derselbe Durchgang; bei #2980 änderte sich der Plan tatsächlich. Urteile je beauftragtem Durchgang und identischem Bereich zusammen zurückgeben, offene Blocks erhalten. Erst am realen Dispatcher prüfen, ob doppelte **Aufträge** entstehen. Die Rundennummer allein beweist das nicht. |

Quellen: [DoR/DoD](https://github.com/Crashman1983/dev-process/blob/v2.100.0/template/docs/process/definition-of-ready-and-done.md) · [#2322](https://github.com/Crashman1983/kenni/blob/b95197152596fb31ab358f9c794b88e9e0409c87/.process-work/journal/issue-2322/2026-11-03.md) · [#2980](https://github.com/Crashman1983/kenni/blob/b95197152596fb31ab358f9c794b88e9e0409c87/.process-work/reviews/2980-plan-r7.md) · [Kenni-Planoverlay](https://github.com/Crashman1983/kenni/blob/b95197152596fb31ab358f9c794b88e9e0409c87/docs/process/commands/plan.local.md) · [Gemeinsamer Designvertrag](https://github.com/Crashman1983/kenni/blob/b95197152596fb31ab358f9c794b88e9e0409c87/docs/design/kenni-v52-contract.md)

### C · Umsetzung und Belege

| Schritt | Route 0/1/2/3 | Kenni und Entscheidung |
|---|---|---|
| Execute, erste vertikale Funktion, Aufgabenstatus | J/J/J/J | Quick editiert direkt, T2+ anhand der Tasks. Bei gemeinsamem Verhalten zuerst die riskante Verbindung zweier Komponenten beweisen; danach unabhängige Anbindungen parallel bauen. Keine eigene Issue und keinen zusätzlichen Statusbericht pro Checkbox. |
| Gezielter Test, rot/grün und Regression | B/J/J/J | T0 mechanisch mit Diffprüfung; T1 gezielter Test, Kenni je nach Subtyp mit test-fast bzw. Lint/Typcheck. T2+ Test je relevantem Verhalten. In #2822 war der „gesperrte“ Scope im Test tatsächlich offen. Vor der Übergabe den Zustand wirklich herstellen. Keine flächendeckende Mutationskampagne. |
| Delegation und Executor-Diffprüfung | –/–/B/B | Bestehenden Kontext bei eng gekoppelten Schritten behalten. Kennis Executor prüft den Diff delegierter Pakete. Kein weiterer Vollreview nach jedem kleinen Paket; der unabhängige Branch-Review folgt später. |
| Vertrags-, Integrations- und E2E-Belege (D1) | B/B/B/B | Für den veränderten kritischen Vertrag den günstigsten Test mit echter Wirkung wählen. Beleg des gemeinsamen Owners wiederverwenden. Browserklick oder nativen Tap prüfen, wenn die Anbindung eigenes Verhalten besitzt. Vorhandene E2E nur mit gleichwertigem Ersatz konsolidieren. |
| Visuelle Abnahme, Accessibility, Vorher/Nachher (D7/D8) | B/B/B/B | Bei UI-Story betroffene Zustände, Viewports und Themes belegen; Vorher-Zustand vor dem Edit sichern. #3019 zeigt die Grenze einer DOM-Assertion, wenn die sichtbare Marke im Screenshot verdeckt ist. Für reines Backend keine Bildproduktion. D8-Abweichung nach DoD begründen. |
| Registry- und Story-Nachweis | B/B/B/B | Akzeptanz einmal pflegen, Nachweis je betroffener Surface bzw. ausdrücklich gemeinsamem Owner. Belegpfade in Bericht übernehmen statt neu tippen. Prüfer entscheidet weiterhin, ob der Test tatsächlich das Kriterium belegt. |
| ADR, betroffene Doku, News und Abweichungen (D3–D5) | B/B/B/B | Nur tatsächliche Doku-/Vertragsänderung und nutzerrelevantes News-Fragment. Architekturentscheidung einmal in der ADR verankern. Plan, Report und News erfüllen verschiedene Zwecke; textgleiche Wiederholung ersetzen durch Verweis. |
| Commit, lokale Selektion, Push, Zertifikat, Gates (D2/D5) | J/J/J/J | Relevante Checks am richtigen Baum ausführen. Bereits grüne Belege nur mit gültigem Umfang und Kontext wiederverwenden. Kennis Execute-Overlay verlagert breite Läufe ans Paketende und nutzt Lanes. Bei belegter Lane keinen zusätzlichen Retry-Loop starten. |
| Spec-Kit Converge | –/–/B/B | Nur bei vermuteter semantischer Abweichung zwischen abgehakten Tasks und Produkt. Der obligatorische Abschluss-Review deckt den regulären Fall ab. |
| Backup, Rollback-Probe, Laufzeit-/Migrationsvorbereitung | –/–/B/B | Bei hohem, schwer rückgängig zu machendem Schaden in Kenni ausdrücklich erforderlich, soweit anwendbar. Aufwand gezielt auf Produktionszustand und Rückweg verwenden. Rein visuelle Arbeiten brauchen keine Datenwiederherstellungsprobe. |

Quellen: [Testregeln](https://github.com/Crashman1983/dev-process/blob/v2.100.0/template/docs/process/testing.md) · [Kenni-Execute](https://github.com/Crashman1983/kenni/blob/b95197152596fb31ab358f9c794b88e9e0409c87/docs/process/commands/execute.local.md) · [#3019](https://github.com/Crashman1983/kenni/blob/b95197152596fb31ab358f9c794b88e9e0409c87/.process-work/reviews/3019-r1.md) · [Kenni-Quellenanzeige](https://github.com/Crashman1983/kenni/blob/b95197152596fb31ab358f9c794b88e9e0409c87/specs/1987-source-disclosure/plan.md#L35-L54)

### D · Reviews, Fixes und Abschluss

| Schritt | Route 0/1/2/3 | Kenni und Entscheidung |
|---|---|---|
| Light Pass/Selbstprüfung | B/J/–/– | Bei Quick die zwei relevanten Fragen und betroffene Tests. Kennis #3053 belegt eine Selbstprüfung. Ein eigener externer Reviewer gehört bei regulärem T0/1 bereits nicht zum Standard. |
| Mergefähigkeit prüfen, Plan finalisieren, Code-Bundle erstellen | B/B/J/J | Für reguläre T2+-Reviews bekannten Konflikt früh auflösen. Frischer Reviewer erhält Diff, Plan, bestehende Belege. Bei zwei parallel betroffenen Registry-Dateieinträgen Tower nutzen, bevor der zweite Finalreview startet. Bei T0/1 Bundle nur im tatsächlich zutreffenden Sonderpfad. |
| Unabhängiger Code-Review / zweite Modellfamilie | –/–/J/J | T2 frischer nicht implementierender Prozess. T3 zweite Familie nach Policy und Verfügbarkeit. Kenni nennt Schwelle 3; Gate-Code bringt zusätzliche Pflichten. Pflichturteile eindeutig demselben Stand zuordnen. Ein zusätzlicher dritter Prüfer für sämtliche T2-Änderungen ist unbegründet. |
| Adversarial Refute | –/B/B/J | T1 optional; T2 normalerweise im Reviewbrief, separater Lauf bei den definierten Datenverlust-/Nebenläufigkeitsfällen; Gate-Code gesondert behandeln. T3 vor Runde 1. Ein Fix an Gate-Code verlangt erneuten Refute dieses Fixes. Bei normalen Folgefixes genügen Regression und Delta nach der geltenden Regel. |
| Kandidaten verifizieren, gewichten, entscheiden | –/–/B/B | Kenni verwendet in aufwendigen Fällen frische Bewerter. Bei #3000 wurden mehrere Major-Kandidaten unter die Blockschwelle eingestuft. Einmal reproduzierbare Messung pro Ursache an alle Prüfer geben. Eigene Prüfer für kosmetische Feststellungen kosten mehr, ohne die Merge-Entscheidung zu ändern. |
| Story-Trace, Felder, Tests, Architektur, Sicherheit, Vollständigkeit und Nutzerwirkung im Report | B/B/J/J | Kenni §11 fordert zusätzliche Reportteile. v2.100 bringt Feature-Satz und Feldverfolgung bereits zentral mit. Überschneidende lokale Vorgaben beim Update zusammenführen. Feldtabelle nur bei tatsächlich transportierten Feldern. Bestehende AC-/Testzuordnungen als Ausgangspunkt einlesen; der Reviewer ergänzt Urteil und Abweichung. |
| Minor/Nit, Follow-up und Rest | B/B/B/B | Kenni lässt Minor/Nit ohne eigene Runde stehen. Ein Issue pro gemeinsamer Ursache nur nach lokalen Kriterien. Bereits vorhandene Regel für alte Befunde mit Roadmap-Zeile: diese Ansicht aus den akzeptierten Befunden ableiten, falls die dauerhafte Rückverfolgbarkeit nachgewiesen ist. |
| Block, Ursachenklärung, Fix, Rot/Grün-Beleg | B/B/B/B | Formale Blockschleife vorrangig T2+. Alle Befunde einer Runde gemeinsam zurückgeben; Geschwisterstellen der Ursache erfassen. Bei #3000 führten zwei symptomatische Fixes zu weiteren Blocks. Ein laufender Test unter realen Eingabebedingungen hätte diese Annahme früher geklärt. |
| REPLAN, Rebuild, Owner-Eskalation, Tarif | –/–/B/B | Vorgesehene Eskalation nach wiederholtem Block nutzen. Ein grundlegender Neuaufbau braucht neue Planprüfung. Kennis tempo-Pfad für UI-Politur begrenzt Runden bereits; qualitaet behandelt Daten-, Vertrauens- und Zustandsrisiken tiefer. Bei einem echten offenen Block Scope oder Lösung entscheiden. |
| Delta-Review, erneuter Vollreview, Attest und Journal | B/B/J/J | Bestehendes Delta verwenden, sofern Grundlage und fixierter Umfang passen. Bei sauberer Integration die bestehenden Regeln für fortgeltende Freigaben nutzen. Echte Konfliktauflösung erneut prüfen. Bericht und Attest nach Möglichkeit im vorgesehenen kombinierten Commit ablegen. Kein Selbstattest als Ersatz für T2+. |
| Einzelintegration über Finish oder gemeinsamer Train | B/B/B/B | Einen passenden Integrationsweg wählen. Kennis Train bündelt Suite und Deploy. Die sieben langen Pass→Merge-Fälle mit Hostdaten prüfen: Warteschlange, Aufnahme und Laufzeit unterscheiden, bevor man Takt oder Batchgröße ändert. Kürzerer Takt kann mehr volle Läufe auslösen. |
| Train-Halt, roter Lauf, Wiederanlauf | B/B/B/B | Gehaltener Branch bleibt angehalten. Infrastrukturabbruch und reproduzierbarer Produktfehler unterschiedlich behandeln. Eine falsche Zuordnung setzt gesunde Arbeit zurück; vorhandene Maßnahmen aus v2.95–98 nutzen. |
| Deploy, Migration, Smoke, Produktionsfreigabe | B/B/B/B | Kenni führt Migrationen von Hand aus. Automatischer Zug-Deploy gibt keine Datenmigration frei. Plattform-Build und ggf. Freigabe sind eigene Endpunkte. Ein Mac-/iPhone-Nachweis lässt sich nur durch einen geeigneten Build-/Testweg belegen. |
| Plan archivieren, Issue schließen, Nachweise erhalten (D6) | B/B/J/J | T0/1 nur vorhandene Artefakte. Kenni schließt beim Landen auf main. Status aus Finish/Train ableiten und bei Wiederholung idempotent halten. Kein zweiter manueller Abschluss nach demselben Ereignis. |
| Produktrelease, Versionsnotizen, SBOM, Template-Update | B/B/B/B | Produkt- und Template-Release sind eigene Anlässe. Reines Template-Update über Herkunftsnachweis prüfen; lokale Deltas und verschobene Durchsetzung gesondert behandeln. #3044 brauchte Nachweis für eine echte lokale Abweichung. V2.100 übernimmt den betreffenden Report-Helfer. |
| Nachlauf: Stichprobe, Regressionen, Wochen-/Monatsbericht, Verbesserung | B/B/B/B | Vorhandene Telemetrie lesen, Kosten gegen gefundene Defekte prüfen. Arbeitszeiten benötigen Hostdaten. Monatsentscheidung zu teuren Gates mit triagierten Treffern und exklusivem Nutzen treffen. Für Routineänderungen entfällt eine separate Retrospektive. |

Quellen: [Unabhängigkeit und Integration](https://github.com/Crashman1983/dev-process/blob/v2.100.0/template/docs/process/verification-independence.md) · [Refute je Tier](https://github.com/Crashman1983/dev-process/blob/v2.100.0/template/docs/process/refute.md) · [Kenni-Reviewoverlay](https://github.com/Crashman1983/kenni/blob/b95197152596fb31ab358f9c794b88e9e0409c87/docs/process/review.local.md) · [#3000](https://github.com/Crashman1983/kenni/blob/b95197152596fb31ab358f9c794b88e9e0409c87/.process-work/reviews/3000-r3.md) · [#3044](https://github.com/Crashman1983/kenni/blob/b95197152596fb31ab358f9c794b88e9e0409c87/.process-work/reviews/3044-r1.md)

## Einzelprüfung der Gates

Der v2.100-Runner enthält 15 Einträge. Sieben sind Kernprüfungen, sieben hängen an Modulen, UI-Check ist inhaltsabhängig und startet standardmäßig beobachtend. Kennis Antworten aktivieren alle sieben hier genannten Module; der Modus jedes tatsächlichen Laufs ist gesondert zu betrachten. Seine lokale Gate-Datei definiert zusätzlich 16 benannte Einträge. Zehn davon haben Pfadfilter, sechs weder Pfad- noch Bereichsfilter. Das ist eine Auswahl für die Kostenanalyse, kein Nachweis für sechs teure Läufe. Bei unbekanntem Diff behält der Runner seinen sicheren Rückfall. [Runner v2.100](https://github.com/Crashman1983/dev-process/blob/v2.100.0/template/scripts/process/gate_runner.py.jinja) · [Lokale Gate-Definitionen](https://github.com/Crashman1983/kenni/blob/b95197152596fb31ab358f9c794b88e9e0409c87/docs/process/gates.local.json)

| Template-Gate | Urteil für Kenni und wichtiger Qualitätsverlust bei falscher Kürzung |
|---|---|
| kernel | Behalten. Drift zentraler Regeln beträfe jeden Worker. Manuelles Bestätigen derselben Kernelversion bei jedem Task ist ein Kürzungskandidat. |
| decision-records | Behalten. Verweise auf bestehende Entscheidung genügen; eine zweite ADR zum gleichen Entschluss erzeugt konkurrierende Aussagen. |
| review | Behalten. Identität, Unabhängigkeit und freigegebener Bereich sind der Schutz vor falschem Grün. Automatische Erstellung des Nachweises nutzen. |
| clarification | Behalten. Eindeutige Produktauswahl vor Planning; geklärte Fragen werden nicht erneut diskutiert. |
| plan-structure | Behalten. Mechanische Tabellenform und Anker hier prüfen, im unabhängigen Review die inhaltliche Richtigkeit. |
| product-frame | Behalten. Bei produktneutraler Arbeit vorhandenen Kurzpfad nutzen. Vollständiges Neulesen der Produktstrategie pro Fix entfällt. |
| overlays | Behalten. Kennis lokale Tarif- und Stackregeln hängen daran. Beim Update identische lokale Wiederholungen freigegebener Template-Regeln entfernen, projektspezifische Zusätze bewahren. |
| speckit | Behalten. Aktive Spezifikation und Taskkonsistenz sichern. Die optionalen LLM-Befehle davon getrennt halten. |
| doc-drift-gate | Behalten. Automatisch auflösbare Referenzen maschinell prüfen. Reviewer prüfen, ob die Aussage noch stimmt. |
| arch-onboarding | Einrichtung und bestehende Architekturbelege nutzen. Neue Architekturaufnahme nur bei geänderter Struktur oder Onboarding. |
| feature-registry | Behalten. Prüft Schema, Belege und stabile IDs. Der Projektchecker ergänzt Kenni-Regeln. Der dokumentierte Wrapper ruft beide auf; unmittelbar nach identischem grünem Runner-Lauf kann dieser dritte Aufruf entfallen. |
| github-issues | Issue-Zuordnung und Berichtspflichten behalten. Zustandswechsel und Merge-Verweis aus dem vorhandenen Ereignis ableiten. |
| sbom | Abhängigkeitsbelege behalten. Überschneidung mit sbom-freshness anhand tatsächlicher Eingaben und Outputs prüfen; sie prüfen verschiedene Pflichten. |
| design-contracts | Zuordnung mehrerer Verträge pro Plan korrigieren. Fehlende oder ungültige ID weiterhin erkennen. |
| ui-check | Beobachtungsmodus und Befunde auswerten, bevor eine neue blockierende Pflicht erwogen wird. Visuellen Review auf verbleibende Nutzerwirkung konzentrieren. |

| Kenni-Gate | Urteil |
|---|---|
| owner-bypass | Ohne Pfadfilter. Historisch drei Fehler durch eine zweite schwächere Implementierung. Behalten; erst mit vollständiger Karte der Leser über engeres Auslösen entscheiden. |
| plan-branch-tests | Bereits selektiv für Planpfade. Zweiten manuellen Syntaxcheck sparen; Gültigkeit des referenzierten Tests bleibt Prüffrage. |
| kit-tokens | Ohne Pfadfilter. Bereits ein realer Drift durch entfernte Produktionstokens (#2093). Filter müsste Produktion, importierende Kits und Gatekonfiguration umfassen. Gute erste Untersuchung bei gemessener Laufzeit. |
| backend-lint | Pfadselektiv. Identischen Lintlauf im unveränderten zertifizierten Kontext wiederverwenden. |
| web-lint | Pfadselektiv einschließlich Toolchain. Selektion bewahren; keine zusätzliche Lint-Sitzung je Unteraufgabe. |
| sbom-freshness | Web-Abhängigkeitsdateien und Generator sind Trigger. Ausgabe gegen Projekt-SBOM prüfen. Nur bei belegter Gleichwertigkeit redundant. |
| openapi-drift | Prüft den API-Vertrag. Ein gemeinsam konsumiertes Schema ist ein günstiger früher Beleg. Bei Vertragsänderung ausführen. |
| theme-tokens | Pfadselektiv. Maschinenprüfbare Tokenregeln hier prüfen. Manuelle Sichtabnahme für Kontrast und tatsächliche Darstellung bleibt wertvoll. |
| ios-guards | Pfadselektiv. Ein grüner statischer Guard sagt wenig über den realen Tap im nativen Client. |
| schema-drift | Prüft OpenAPI gegen abgeleiteten TS-Stand. Zusammen mit openapi-drift bilden sie zwei Kanten der Kette Backend → Schema → Client; eine Ausführung kann Resultate teilen, beide Beziehungen brauchen Nachweis. |
| baseline-duplicates | Bereits auf Baselines ausgelöst. Entwicklungsbilder außerhalb der offiziellen Referenzen nicht zusätzlich vergleichen. |
| plan-retention | Ohne Pfadfilter. Zuerst die Eingaben klären: Welche Planverschiebungen, Löschungen und Konfigurationsdateien wertet er aus? Erst dann Pfadselektion testen, insbesondere Verschieben und Löschen. |
| inventory | Ohne Pfadfilter. Produktdateien können indirekt eine Inventaränderung verlangen. Nur anhand kompletter Leserkarte enger auslösen. |
| token-growth | Ohne Pfadfilter. Prüft Wachstum von Design-Token-/View-Deklarationen. Kandidat für Selektion auf bekannte Quellen plus Regeln und Baseline. Mögliche Fehler durch neu angelegte Quellpfade testen. |
| board-round2 | Bereits auf ein konkretes Board begrenzt. Beim Ablösen einer Referenz prüfen, ob es noch aktive Verbraucher gibt; aktuelle Norm schützt historische Designentscheidungen. |
| registry-project | Ohne Pfadfilter, an Modul gekoppelt. Enthält lokale Regeln. Den gemeinsamen Wrapper als CLI behalten; nach einem gleichwertigen erfolgreichen Lauf das Ergebnis wiederverwenden. |

Quellen: [Registry-Wrapper](https://github.com/Crashman1983/kenni/blob/b95197152596fb31ab358f9c794b88e9e0409c87/scripts/check_feature_registry.py) · [Konkreter Token-Drift](https://github.com/Crashman1983/kenni/blob/b95197152596fb31ab358f9c794b88e9e0409c87/scripts/check_kit_tokens.py) · [Owner-Bypass](https://github.com/Crashman1983/kenni/blob/b95197152596fb31ab358f9c794b88e9e0409c87/scripts/check_owner_bypass.py)

## Umsetzungsentscheidung

| Reihenfolge | Ort und Änderung | Abnahme vor Übernahme |
|---|---|---|
| 1 | Template v2.101: Planannahmen mit genau der billigsten entscheidenden Gegenprobe am Bestand prüfen. Mehrere Urteile zum selben beauftragten Stand zusammen zurückgeben. | #2980 mit realer Swift-Deklaration; #2322 mit zwei unabhängigen Urteilen. Bleibt ein Block offen, bleibt die Arbeit blockiert. Keine zweite Aufgabe allein wegen der Anzahl der Records. |
| 2 | Template v2.101: Multi-Surface-Plan in Gate und Review-Bundle korrekt auflösen. | Web E1 und iOS E7 bestehen zusammen. Eine unbekannte oder falsch zugeordnete ID bleibt rot. Ein-Vertrags-Pläne funktionieren unverändert. |
| 3 | Kenni-Overlay: Governance-Quick vereinfachen und Dopplung im Reviewbericht bereinigen. | Eigener Sollwert für Branch/Basis bleibt erhalten. Fremder Worktree und geänderter ausführbarer Pfad stoppen weiterhin. Ein realer Story-Nachweis wird einmal erfasst und an beiden Stellen aufgelöst. |
| 4 | Kenni-Betrieb: 7 lange Pass→Merge-Fälle mit Hostereignissen zerlegen. Ungefilterte Gates nach Laufzeit, Häufigkeit, exklusiven Funden und geprüften Eingaben sortieren. | Erst bei gemessener Ursache Batchgröße, Aufnahmefrequenz oder Gate-Selektion ändern. Qualitätsvergleich über abgeschlossene Regressionsfenster, Gesamtlaufzeit einschließlich zusätzlicher Züge. |

Für T0/T1 ist die wirksamste direkte Änderung lokal. Für T2/T3 ist die reproduzierte Template-Korrektur sofort abnahmefähig. Eine generelle Abschaffung unabhängiger Reviews oder verpflichtender Surface-Abnahmen lässt sich mit dieser Datenlage nicht begründen. Aktive Modellzeit, genaue Gatekosten und Kenni-Produktlaufzeiten auf dem Host wurden für dieses Audit nicht neu gemessen.
