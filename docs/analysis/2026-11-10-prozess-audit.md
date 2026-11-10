# Audit des Dev-Prozesses: Effizienz ohne Qualitätsverlust

Datum: 2026-11-10 · Stand: v2.93.0 · Art: Analyse, kein Plan und kein Beschluss

Auftrag des Owners: unnötige, doppelte und unangemessen aufwändige Arbeitsschritte finden, Verbesserungspotenziale nennen. Ziel ist mehr Tempo bei gleicher Qualität des Outputs.

Methode: Die Regeln, Befehle und Skripte unter `template/` wurden gelesen, nichts ausgeführt. Die Zahlen zur Historie stammen aus `git log` dieses Repositories. Zahlen zum Referenzprojekt stammen aus den Plänen und dem CHANGELOG dieses Repositories, nicht aus eigener Messung. Wortzahlen sind `wc -w` auf den ungerenderten Vorlagen (rund ±5 %). Was nicht geprüft ist, steht als Annahme da.

## 1. Befund in einem Absatz

Der Prozess hat keinen einzelnen überflüssigen Schritt, der alles erklärt. Er ist durch Anlagerung teuer geworden: Seit dem Abbau zu v2.0.0 (2026-08-06) kamen im Template 57.164 Zeilen dazu und 15.166 gingen weg. Die Abbauliste von damals wollte die Review-Maschinerie und die Telemetrie eindampfen; beide sind heute rund sechsmal so groß. Im Referenzprojekt stieg der Anteil reiner Prozess-Commits in acht Wochen von 25–39 % auf 60–68 %, je Merge im Median 8 Prozessdateien auf 1 Produktdatei (`docs/analysis/2026-10-28-v2.80.md`). Die Antwort darauf waren vier neue Messfamilien und Hinweise, kein Abbau. Die größten Hebel liegen in vier Bereichen: mehrfach laufende Gates, kalte Sitzungen mit großem Lesepensum, mehrfach geführte Buchhaltung und eine Selbstoptimierung, die bisher nichts entfernt hat.

| Stand | Doku im Template (Wörter) | Skripte (Zeilen) | Tests (Zeilen) |
|---|---:|---:|---:|
| v2.0.0, 2026-08-06 | 24.123 | 5.006 | 7.009 |
| v2.38.0, 2026-09-30 | 39.590 | 13.147 | 14.480 |
| v2.69.0, 2026-10-13 | 58.622 | 23.858 | 26.438 |
| v2.93.0, 2026-11-09 | 82.881 | 40.971 | 48.715 |

## 2. Doppelte Arbeit

### 2.1 Die Gates laufen je Branch sieben- bis neunmal, mindestens dreimal auf identischem Stand

Tests werden einmal bezahlt; Zertifikat und Stempel decken ihre Wiederholungen ab. Für die Gates gibt es nichts Vergleichbares. Ein Tier-2-Branch durchläuft den vollen Gate-Runner an diesen Stellen:

| Stelle | Stand | Beleg |
|---|---|---|
| Push des Branches | Kopf H | `pre_push.py:230-240` |
| CI auf dem PR | H | `process-gates.yml.jinja:11-14` |
| Bau des Review-Bundles („Preflight“) | H | `make_review_bundle.py:1350` |
| Push des Attest-Commits | H + Buchhaltung | `pre_push.py:229` |
| CI auf dem PR, zweiter Lauf | wie oben | |
| `finish.py`, nach Rebase erneut | | `finish.py:318-322,510` |
| Train auf dem kombinierten Baum | Merge-Baum M | `train.py:2082,2230` |
| Push-Hook beim Merge | M | `pre_push.py:225-232` |
| CI auf main | M | `process-gates.yml.jinja:12-13` |

Dazu kommt: Der Runner startet die Gates nacheinander, je Gate einen eigenen Interpreter (`gate_runner.py.jinja:549,618`). Das `review`-Gate liest bei jedem Lauf die letzten 2.000 Commit-Nachrichten und alle archivierten Pläne (`check_review.py:2823-2827,3295`); der Bundle-Code nennt den Preflight selbst „takes minutes“ (`make_review_bundle.py:1341`). Die Planphase lässt die Gates vor `planned` laufen, die Dispatch-Kette danach auf demselben HEAD noch einmal (`dispatch.py:1249-1251,3375`).

Empfehlung:
- Ein Gate-Merker analog zum Testzertifikat. Gates, die nur den Baum lesen (`kernel`, `decision-records`, `product-frame`, `overlays`, `doc-drift`, `arch`, `sbom`, `feature-registry`), werden über den Baum-Hash gemerkt; die übrigen über HEAD und Push-Ziel. Bundle-Preflight, `finish` und Train lesen den Merker. CI bleibt ohne Merker, als unabhängige Instanz.
- Der Train lässt seine Gates mit dem Merge-Ziel laufen und stempelt, damit der Hook danach ein Treffer ist.
- Gates im Runner parallel starten. Sie sind unabhängige Subprozesse; die Ausgabe muss sortiert bleiben.
- Das Qualitätsrisiko ist gering, solange ein unsauberer Arbeitsbaum nie trifft. Vorher messen: `process_kpis.py nodes --json`, Läufe je Gate und Eingabestand mal `cost_s`.

### 2.2 Dieselbe Tatsache wird drei- bis fünfmal geschrieben

| Tatsache | Kopien |
|---|---|
| Stand der Arbeit | `report.py`-Zeile, Status-Label und Claim-/Heartbeat-Kommentare am Issue, Plan-Checkboxen, Kanal-Einzeiler, Dispatch-Record |
| Review-Urteil | `REVIEW`-Zeile im Journal, Report-Datei, Kopie als GitHub-Issue (hart geprüft), `report.py review-pass` |
| Akzeptanzkriterium → Test | Plan (`AC-id: path::test`), Review-Report je Kriterium, Registry-Story, `sc-evidenced:` |
| Was sich geändert hat | Commit, News-Fragment, wöchentliches `NEWS.md` als eigener Branch durch den Train, Digest |
| Modell | `--model` an jedem Report, `plan-session model:` im Plan, `REVIEW model=` |

Mehreres davon liest kein Skript: Claim- und Heartbeat-Kommentare (die Ansichten dazu wurden im August gestrichen, die Pflicht blieb), der Inhalt der State-Datei, die Journal-Prosa außerhalb der `REVIEW`- und `ROOT-CAUSE`-Zeilen.

Empfehlung:
- Eine Tabelle Kriterium → Test im Plan. `attest.py` prüft sie am Kopf, das Bundle füllt sie vor, der Review-Report nennt nur Abweichungen, der Registry-Eintrag wird daraus erzeugt. Die Reviewer-Frage „würde der Test rot, wenn man das Verhalten entfernt?“ bleibt.
- Wo Dispatch läuft, entfallen Claim, Heartbeat und Status-Labels; der Train schließt Issues ohnehin über `Closes #N`.
- Die Veröffentlichung der Review-Reports als Issue wird Opt-in. Das spart je Review einen Netzschritt und einen Rückschreib-Commit.
- Die letzten beiden Punkte hängen an einer Frage an dich: Liest du Labels und Report-Issues auf GitHub?

### 2.3 Dieselbe Regel steht an bis zu acht Stellen

Die REPLAN-Regel steht in acht Dateien, das Verbraucher-Inventar in sieben Abschnitten, „was blockiert“ in vier, die Plan-Review-Prozedur in fünf. Die Folge sind Widersprüche, die Runden kosten:

- Braucht Tier 2 eine Spec? Nein laut Kernel, `workflow.md` und `risk-tiers.md`. Ja laut `/brainstorm`, `speckit.md` und `journal-state-plans.md:177-180` (hartes Gate, außer mit `spec-waived`).
- Wann wird der Plan archiviert? Vor dem Bundle (`workflow.md.jinja:53`) oder nach dem Pass (`commits.md:77`, `attest.py:66-68`).
- `finish.py:508-509` meldet nach einem Rebase noch „a rebase voids review-bundle digests; re-review if a bundle was built“. Die Digests gibt es seit v2.53 nicht mehr, ein sauberer Rebase hält das Review. Der Text lädt zu einer unnötigen Review-Runde ein, der teuersten Einheit im Prozess.
- Tier-2-Report: „encouraged“ (`verification-independence.md:327`) gegen „Every Tier 2+ review writes“ (`review.md:46`).
- Reviewer nur mit Bundle oder mit Lesezugriff? `verification-independence.md:95-97` schreibt Werkzeuge aus vor; dieselbe Datei misst ab `:128`, dass ohne Lesezugriff etwa einer von sechs Befunden hält, mit Lesezugriff neun von zehn.

Empfehlung: ein Eigentümer je Regel (das ist Regel 4, auf die Doku angewendet); Befehle tragen nur den Imperativ und den Verweis. Die drei falschen Texte oben sind sofort korrigierbar, ohne Risiko.

### 2.4 Dieselbe Prüfung durch mehrere Instanzen

- Die Suche nach Verbrauchern läuft viermal: Der Plan zitiert sie, der Plan-Reviewer führt sie aus, Execute vergleicht, der Code-Reviewer führt sie erneut aus. Ein Skript, das die Befehle aus `## Consumers` am Kopf neu ausführt und die Differenz zeigt, ersetzt drei davon.
- Tier 3 stapelt fünf LLM-Prüfungen: `/speckit-analyze`, Plan-Review, Refute, Code-Review, `/speckit-converge`. `analyze` und Plan-Review lesen dieselben Artefakte; `converge` deckt sich mit dem Abschnitt Completeness der Checkliste. Annahme: Die Überschneidung der Befunde ist nicht gemessen. Vor einer Zusammenlegung zählen, wie viele Befunde der letzten Tier-3-Arbeiten nur `analyze` oder nur `converge` fand.
- Der Refuter führt jedes Szenario zweimal aus, gegen die Änderung und gegen den Integrationsbranch (`refute.md:113`). Es genügt, bestätigte Szenarien gegenzuprüfen.
- Je blockierendem Befund startet ein eigener Scorer-Subagent (`review.md:26-31`); einer je Runde reicht.

## 3. Unangemessen aufwändig

### 3.1 Kalte Sitzungen mit großem Lesepensum

Tier 2 braucht mindestens drei kalte Sitzungen plus Subagenten, Tier 3 sechs bis sieben. Jede blockierte Runde kostet zwei weitere. Eine Review-Sitzung wird auf Kernel, Regeln, Workflow, Risikostufen, Checkliste und `verification-independence.md` verwiesen: rund 11.000 Wörter bei engem Lesen, rund 26.000, wenn sie die Dateien ganz liest. Jede Claude-Sitzung lädt vorab rund 6.700 Wörter (`CLAUDE.md.jinja:38-41`). Alle Befehle sagen „re-read the kernel“, obwohl der Kernel in der Startdatei steht und `rehydrate.py` ihn nach jeder Kürzung einspielt. `process_context.py --cost` misst das nicht: Es zählt die Befehlsdateien, aber keine der Phasen-Dokumente (`process_context.py:255-281`).

Ein erheblicher Teil dieser Texte ist für den Agenten nicht handlungsleitend: Interna der Gates (`verification-independence.md:243-297`, rund 600 Wörter, deren Inhalt in einen Satz passt), Hinweise auf abgeschaffte Funktionen und 45–55 Absätze, die je einen Vorfall nacherzählen.

Empfehlung:
- Je Phase eine Karte mit höchstens rund 1.500 Wörtern: was zu tun ist, in welcher Reihenfolge, mit welchem Befehl. Gate-Interna und Vorfallsgeschichte wandern in eine Referenz, die nur bei Bedarf gelesen wird.
- Fix-Runden setzen die Execute-Sitzung fort, Delta-Runden die Reviewer-Sitzung. Die Unabhängigkeit bleibt, denn der Reviewer hat weiterhin nicht implementiert. Kalt bleiben Refute und die erste Tier-3-Runde.
- Risiko: Ein fortgesetzter Reviewer ankert auf seiner ersten Sicht. Das gehört als Versuch nach `optimization.md` gemessen: Blocker je Runde, Anteil spät gefundener Befunde, Durchrutscher, mindestens 20 Arbeiten.

### 3.2 Tier 2 zahlt die volle Spec-Stufe

`risk-tiers.md` nennt als Tier-2-Beispiel eine Zehn-Zeilen-Weiterleitung. Im Standardset kostet sie Spec, Plan, Aufgaben und zwei Reviews. Die eigene Messung zeigt, dass kleine Arbeiten selten entgleisen: unter 200 Produktzeilen brauchen 10 % drei oder mehr Runden, über 1.500 Zeilen 53 %.

Empfehlung: Für kleine Tier-2-Arbeit in einem Stack sind Akzeptanzkriterien im Plan der Normalweg, wie es DoR R2 bereits sagt, statt einer Ausnahme mit `spec-waived`. Der Preis ist ein kürzeres Einflussfenster des Owners vor dem Bau. Entscheidungsgrundlage: `process_kpis.py size`, Runden und Durchrutscher für Tier 2 mit und ohne Spec.

### 3.3 Der Steward-Tick

`/loop 30m /steward` lädt bis zu 48-mal am Tag einen Befehl von 2.162 Wörtern, von dem etwa die Hälfte tägliche, wöchentliche und monatliche Pflichten beschreibt, dazu die volle Lage. Eine Tick-Karte mit `tower --section` und eine getrennte Tagesdatei sparen das meiste davon.

### 3.4 Die Pflege dieses Repositories

- 74 Release-Tags seit Anfang Oktober (61 im Oktober, 13 bis zum 9. November), zuletzt sechs an einem Tag (2026-11-04, v2.86 bis v2.91). Jedes Release ist ein eigener Durchlauf aus Plan, Plan-Review, Umsetzung, Review, zweisprachigem CHANGELOG und zweisprachigen NEWS. Projekte aktualisieren laut `OVERVIEW.md` alle zwei bis vier Wochen. Ein wöchentlicher Release-Zug mit gebündeltem CHANGELOG spart den Fixaufwand je Release, ohne dass ein Projekt später beliefert wird.
- Die letzten 13 Releases brauchten zusammen 26 Plan-Review-Runden, v2.93 allein fünf (gezählt an den Commit-Betreffs „plan review“). Die Befunde dort sind überwiegend Randfälle der Gate-Semantik. Das ist dieselbe Dynamik, die im Projekt die Runden treibt: Jede neue harte Regel braucht Ausnahmen, und jede Ausnahme ist wieder Gate-Code auf Tier 3.
- `MAINTAINING.md` verlangt für jeden Satz Regeltext Plan-Review und Review. Für Text, der eine Pflicht abschwächt oder entfernt, ist das begründet. Für eine reine Kürzung ohne Bedeutungsänderung macht es Abbau so teuer wie Aufbau; damit kann die Doku praktisch nur wachsen.

## 4. Unnötig oder ohne belegten Nutzen

### 4.1 Die Selbstoptimierung hat bisher nichts entfernt

Rund 6.700 Zeilen (`optimize.py`, `gate_modes.py`, `process_kpis.py`, `graph.py`, `plan_drift.py`, `due_measurements.py`, `human_digest.py`), dazu tägliche Sentinel-Läufe, eine wöchentliche und eine monatliche Sitzung.

- Alle Streichungen von Prüfungen im CHANGELOG liegen vor der Einführung der Schleife (v2.67/v2.68) und waren Entscheidungen von Hand. In den 26 Releases danach steht keine Abschwächung und keine Entfernung aufgrund von Messwerten.
- `optimize.active()`, die Abfrage für Versuche hinter einem Flag, hat im Template keinen Aufrufer.
- Das Cockpit meldete bis v2.80 auf jedem Klon `works 0`; die Kenni-Analyse lief von Hand.
- Die Untergrenzen des Beispiel-Mandats nehmen Gates, Tiers, Review-Unabhängigkeit und DoD von Versuchen aus. Das sind die teuren Teile. Die Schleife kann damit fast nur hinzufügen.
- Eine Prüfung wird erst nach acht triagierten Wochen Kandidat. Bei drei bis fünf Triage-Zeilen je Woche ist das kaum erreichbar.

Nicht geprüft: Die Projekte können eigene Records und Abschwächungen haben; dieses Repository enthält keine.

Empfehlung: Die Schleife ruht, bis es einen Versuch gibt. Sentinel und `optimize check` laufen nur, wenn ein Record im Pilot oder eine Gate-Änderung existiert; die wöchentliche Sitzung geht in der monatlichen auf. Der erste echte Versuch ist 3.1 (warme Fix- und Delta-Runden). Wenn die wöchentlichen Reports im Projekt in den letzten vier Wochen eine Entscheidung ausgelöst haben, spricht das dagegen; das lässt sich dort zählen.

### 4.2 Mechanismen für einen Vorfall oder einen seltenen Fall

Zu prüfen gegen dein tatsächliches Setup, zusammen etwa 500–800 Zeilen plus Tests:
- Mehr-Host-Betrieb (`refs/process/reports/<host>`, `--remote`, Übergabe), dessen Ref-Push Cloud-Umgebungen laut `tower.md:345` ablehnen.
- Eingabe in eine tmux-Oberfläche (`dispatch.py:2543-2706`), obwohl der Standard-Runner `detached` ist.
- Nachbau der Whitespace-Klasse von Claude Code, um `model:` in einer Befehlsdatei abzulehnen (`dispatch.py:416-600`).
- Nachbau der pytest-Sammlung per AST (`attest_evidence.py:1279-1412`), wo `red_evidence.py` dasselbe durch Ausführen zeigt.
- MAKEFLAGS-Parser (`certificate.py:157-232`), Queue-Migration (`dispatch.py:2808-2821`).
- Die Zweige ohne Spec Kit in `/plan` und `/brainstorm`, deren Streichung die Abbauliste (#11) schon beschlossen hat, während `start-here.md` sagt, es gebe keinen Modulschalter.

### 4.3 Pflichten, die sich pro forma erfüllen lassen

`ui-check: n/a — <Grund>`, `ROOT-CAUSE … sites: none — <Grund>`, `REPLAN`, `Execution: delegate | retain-context` je Paket, `plan-session model:`. Im Referenzprojekt tragen laut `docs/analysis/2026-11-02-v2.81.md` nur 13 % der geschuldeten Stellen ein REPLAN und 60 % ein ROOT-CAUSE. Eine Pflicht, die so oft fehlt und trotzdem nicht blockiert, kostet Lesezeit und liefert keine verlässlichen Daten. Jede davon gehört entweder mechanisch abgeleitet (Modell und Ausführungsart aus den Dispatch-Logs) oder gestrichen.

## 5. Reihenfolge

| # | Maßnahme | Ersparnis | Qualitätsrisiko |
|---|---|---|---|
| 1 | Falsche Texte korrigieren: Rebase-Hinweis in `finish.py`, Archiv-Reihenfolge, Spec-Pflicht Tier 2, Report-Pflicht | vermiedene Review-Runden | keins |
| 2 | Gate-Merker, Train stempelt, Gates parallel, kein Preflight für Plan-Bundles | 4–6 von 7–9 Gate-Läufen je Branch | gering |
| 3 | Eine Tabelle Kriterium → Test; Verbraucher-Suche als Skript | drei Abschriften und drei Suchläufe je Arbeit | gering |
| 4 | Phasenkarten, ein Eigentümer je Regel, `--cost` korrigieren | geschätzt 40–50 % der Wörter je Phaseneintritt | mittel: eine Regel wird übersehen |
| 5 | Reviewer mit Lesezugriff als Standard | weniger Fehlblocks und Scorer-Läufe | gering, bereits gemessen |
| 6 | Warme Fix- und Delta-Runden als Versuch | zwei Kaltstarts je blockierter Runde | mittel, deshalb als Versuch |
| 7 | Tier 2 klein ohne Spec-Stufe | eine Phase auf dem häufigsten geprüften Tier | mittel, Owner-Entscheidung |
| 8 | Selbstoptimierung ruhen lassen, Steward-Tick teilen | tägliche und wöchentliche Sitzungen | gering |
| 9 | Wöchentlicher Release-Zug; Kürzungen ohne Bedeutungsänderung mit leichtem Weg | Fixaufwand je Release | gering |
| 10 | Tier 3: `analyze`/`converge` zusammenlegen, Refute einfach | zwei LLM-Läufe | erst nach Zählung der Einzelbefunde |
| 11 | Selten genutzte Mechanismen streichen (4.2), Pro-forma-Pflichten ableiten oder streichen (4.3) | Pflegeaufwand, kürzere Doku | je nach Setup |

Die Punkte 1 bis 3 und 5 senken keine Prüfung ab und brauchen keine Owner-Entscheidung über Qualitätsuntergrenzen. Die Punkte 6, 7 und 10 ändern, wie geprüft wird, und gehören vor der Umsetzung gemessen.

## 6. Was bleibt, wie es ist

- Testpfad mit Auswahl, Lanes und Zertifikat (`docs/analysis/2026-10-10-one-test-path.md`).
- Inhaltsbasierte Review-Bindung: Ein sauberer Rebase hält das Review, Buchhaltung unter `.process-work/` macht es nicht ungültig.
- Delta-Bundles, das in das Review gefaltete Tier-2-Refute, der Tier-1-Weg.
- Provenienzprüfung für reine Template-Updates.
- Die Kürzung von `process_context` und `rehydrate`.
