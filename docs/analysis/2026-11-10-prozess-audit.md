# Audit des Dev-Prozesses: Wiederholungen im Durchlauf

Datum: 2026-11-10 · Stand: v2.93.0 · Art: Analyse, kein Plan und kein Beschluss

Auftrag des Owners: Der Umfang des Prozesses ist in Ordnung, solange er korrekt ist und gebraucht wird. Störend ist, was er in der Anwendung kostet: dass ein Arbeitspaket mehrfach durch dieselbe Prüfung läuft. Dieser Bericht zählt diese Wiederholungen und nennt je Wiederholung, ob sie entfallen kann, ohne dass eine Prüfung schwächer wird.

Methode: Code und Regeln unter `template/` gelesen, nichts ausgeführt. Die Zählungen folgen aus den Aufrufstellen im Code. Laufzeiten in Sekunden sind hier nicht messbar; Abschnitt 5 nennt, welche Zahlen im Projekt zu ziehen sind. Was nicht geprüft ist, steht als Annahme da.

## 1. Ergebnis

Ein Tier-2-Paket, das ohne Beanstandung durchgeht, läuft achtmal lokal durch den vollen Gate-Runner und, wenn ein PR offen ist, dreimal in der CI. Jede weitere Review-Runde kostet drei lokale Läufe und zwei CI-Läufe mehr; bei drei Runden sind es 14 lokale. Auf vier Ständen läuft der Runner zwei- bis dreimal, ohne dass sich am geprüften Inhalt etwas geändert hat. Für Tests gibt es dagegen ein Zertifikat; sie werden je Stand einmal bezahlt.

Rund die Hälfte der lokalen Gate-Läufe kann entfallen, ohne dass eine Prüfung wegfällt: Derselbe Runner hat denselben Stand bereits grün gesehen.

Tier 0 und 1 zahlen zwei bis vier Läufe und, ohne Projektkonfiguration, die volle Merge-Suite auch für eine einzelne Doku-Datei. Tier 3 liegt bei den Gates kaum über Tier 2; dort kosten die fünf Prüfläufe durch ein Modell (Abschnitt 7).

## 2. Gate-Läufe eines Tier-2-Pakets

Jeder Lauf startet alle aktiven Gates nacheinander, je Gate einen eigenen Interpreter: acht Kern-Gates und bis zu sieben Modul-Gates (`gate_runner.py.jinja:549,618`).

| # | Auslöser | Stand | Beleg |
|---|---|---|---|
| 1 | `/plan` nach dem Plan-Commit | Plan-Commit P | `plan.md.jinja:253` |
| 2 | Bundle für das Plan-Review („Preflight“) | P | `make_review_bundle.py:1350` |
| 3 | Dispatch-Kette vor dem Start von Execute | P | `dispatch.py:3378,3506` |
| 4 | Push des Branches | Kopf H | `pre_push.py:230-232` |
| 5 | Bundle für das Code-Review | H | `make_review_bundle.py:1350` |
| 6 | Push des Attest-Commits | H plus Journalzeile | `pre_push.py:229-237` |
| 7 | Train auf dem kombinierten Baum, oder `finish.py` | Merge-Baum M | `train.py:2082`, `finish.py:318` |
| 8 | Push-Hook beim Merge | M | `pre_push.py:225-232` |
| CI | PR nach Lauf 4 und nach Lauf 6, danach main | H, H plus Journalzeile, M | `process-gates.yml.jinja:11-14` |

Je weiterer Review-Runde: Push des Fixes, Bundle, Push des Attest-Commits, dazu zwei CI-Läufe.

Derselbe Stand, mehrfach geprüft:
- **P:** Läufe 1, 2 und 3. Der Plan-Reviewer liest laut Code-Kommentar keinen Code (`make_review_bundle.py:1341`), das Bundle fährt die Gates trotzdem.
- **H:** Läufe 4 und 5, dazu die CI.
- **H plus Journalzeile:** Lauf 6 und die CI. Der Hook erkennt den Stand und lässt die Tests weg („gates only“), die Gates laufen voll.
- **M:** Läufe 7 und 8, dazu die CI auf main. Der Train reicht das Merge-Ziel nicht an die Gates und stempelt nicht, deshalb wiederholt der Hook sie (`train.py:1115-1123`).

Der Push-Hook überspringt die Gates nur bei exakt demselben Commit und derselben Push-Klasse (`pre_push.py:220-225`). Bundle, `finish`, Train und Dispatch lesen diesen Stempel nicht.

Auch ein per Dispatch gestartetes Tier-1-Paket baut ein Bundle, attestiert und pusht (`dispatch.py:1249-1251`): vier Gate-Läufe für eine kleine Korrektur.

Was einen einzelnen Lauf teuer macht:
- Das `review`-Gate liest bei jedem Lauf die letzten 2.000 Commit-Nachrichten und alle archivierten Pläne (`check_review.py:2823-2827,3295`). Es hat schon einmal das Zeitlimit von 600 Sekunden gerissen (`check_review.py:3142-3146`).
- Das `github-issues`-Gate fragt bei jedem Lauf GitHub ab, mit bis zu 20 Sekunden Limit, und blockiert nie (`check_issues.py.jinja:9-12,667-669`).
- Die Gates laufen nacheinander, obwohl sie unabhängige Prozesse sind.

## 3. Weitere Wiederholungen im Durchlauf

| Was | Wie oft | Beleg | Kann entfallen? |
|---|---|---|---|
| Suche nach Verbrauchern eines geänderten Werts | viermal: Plan, Plan-Review, Execute, Code-Review | `refute.md:138-140`, `execute.md:13`, `review-checklist.md:64-67` | Ja, drei davon: ein Skript führt die Befehle aus `## Consumers` am Kopf neu aus und zeigt die Differenz |
| Zuordnung Kriterium → Test | dreimal von Hand: Plan, Review-Report, Registry | `journal-state-plans.md:75-80`, `review.md:53-63` | Ja, zwei davon: Bundle füllt aus dem Plan vor, Registry wird erzeugt |
| Eigentümer-Prüfung (Regel 4) bei Tier 3 | viermal: Plan-Review, Execute, Refute, Review | `refute.md:44,133`, `execute.md:24-26`, `review-checklist.md:208` | Teilweise; erst zählen, welche Stufe die Befunde bringt |
| Tier neu berechnen | zweimal: Plan-Review und Code-Review | `review-checklist.md:24,36` | Ja, wenn sich die berührten Pfade seit dem Plan nicht geändert haben |
| Refute-Szenarien | jedes zweimal: gegen die Änderung und gegen den Integrationsbranch | `refute.md:113` | Ja: nur bestätigte Szenarien gegenprüfen |
| Scorer-Subagent | einer je blockierendem Befund | `review.md:26-31` | Ja: einer je Runde |
| Tier-3-Prüfläufe | fünf: `analyze`, Plan-Review, Refute, Review, `converge` | `speckit.md:97-99` | Offen: `analyze` und `converge` überschneiden sich mit Plan-Review und Review; Einzelbefunde vorher zählen |
| Kaltstart je blockierter Runde | zwei neue Sitzungen, je mit vollem Lesepensum | `tower.md:309` | Als Versuch: Fix- und Delta-Runde setzen die Sitzung fort |
| Kernel neu lesen | bei jedem Phaseneintritt, obwohl er in der Startdatei steht und `rehydrate.py` ihn einspielt | `execute.md:19`, `review.md:12` | Ja, wo der Hook installiert ist |
| Steward-Tick | bis zu 48-mal am Tag der ganze Befehl und die volle Lage | `steward.md:44-52` | Ja: Tick-Karte mit `tower --section`, Tagespflichten getrennt |
| Stand der Arbeit melden | bis zu fünf Stellen, darunter Label, Claim und Heartbeat am Issue | `report.md:13-17`, `github-issues.md:116-127` | Ja: Du liest GitHub selten, und kein Skript liest Claim und Heartbeat |
| Review-Report als Issue | je Review ein Netzschritt und ein Rückschreib-Commit mit Push, der wieder durch die Gates geht | `github-issues.md:239-243` | Ja: als Opt-in |

## 4. Texte, die unnötige Runden auslösen

Eine Review-Runde ist die teuerste Wiederholung: zwei Sitzungen, drei Gate-Läufe, zwei CI-Läufe. Drei Stellen laden zu Runden ein, die der Code nicht verlangt:

- `finish.py:508-509` meldet nach einem Rebase „a rebase voids review-bundle digests; re-review if a bundle was built“. Die Digests gibt es seit v2.53 nicht mehr; ein sauberer Rebase hält das Review.
- Die Reihenfolge beim Archivieren des Plans: `workflow.md.jinja:53` archiviert vor dem Bundle und nennt jede spätere Änderung einen Grund für ein neues Bundle. `commits.md:77` und `attest.py:66-68` archivieren nach dem Pass. Der Code behandelt das Archivieren als Buchhaltung; der Text liest sich als neue Runde.
- Reviewer ohne Lesezugriff: `verification-independence.md:95-97` schreibt Werkzeuge aus vor. Dieselbe Datei misst ab `:128`, dass so etwa einer von sechs Befunden hält, mit Lesezugriff neun von zehn. Fünf von sechs Blocks sind dann Fehlalarme, und jeder kostet eine Runde.

Dazu kommt eine Staleness-Regel, die strenger ist als nötig: Jeder Pfad außerhalb der Buchhaltung, der nach dem geprüften Kopf geändert wird, macht das Review ungültig, auch ein Tippfehler in einer README (`check_review.py:2064-2069`). `quiet.py` kennt bereits eine enge Definition von „wirkungslos“ für die Testauswahl; das Review-Gate nutzt sie nicht.

## 5. Maßnahmen nach Wirkung auf die Durchlaufzeit

| # | Maßnahme | Wirkung | Risiko für die Qualität |
|---|---|---|---|
| 1 | Gate-Merker: Ein grüner Lauf wird je Gate mit seinem Eingabestand gemerkt. Bundle, Dispatch, `finish`, Train und Hook lesen ihn. Der Train übergibt das Merge-Ziel und stempelt. | Läufe 2, 3, 5 und 8 entfallen, je weiterer Runde einer von drei. Lauf 6 schrumpft auf die Gates, die Journal und Plan lesen. | Gering. Bedingung: Ein unsauberer Arbeitsbaum trifft nie, und Gates, die über den Baum hinaus lesen (Issue-Tracker, Rot-Liste, `train.py:1129-1131`), bleiben ohne Merker. Die CI bleibt ohne Merker. |
| 2 | Kein Gate-Lauf für Plan-Review-Bundles. | Lauf 2 entfällt auch ohne Merker. | Keins. |
| 3 | Die drei Texte aus Abschnitt 4 korrigieren; Reviewer mit Lesezugriff als Standard. | Vermiedene Review-Runden. | Keins bei den Texten. Beim Lesezugriff ändert sich die Bedeutung der Markierung `bundle`. |
| 4 | Gates im Runner parallel starten. | Die Dauer eines Laufs sinkt etwa auf die des langsamsten Gates. | Gering; die Ausgabe muss sortiert bleiben. |
| 5 | `github-issues` aus dem Push-Pfad in CI oder Digest verlegen. Review-Report als Issue wird Opt-in; Label, Claim und Heartbeat entfallen, wo Dispatch läuft. | Ein Netzzugriff je Gate-Lauf, ein Commit mit Push je Review. | Keins; das Gate blockiert heute nicht. |
| 6 | `review`-Gate begrenzen: archivierte Pläne nur im gepushten Bereich prüfen, der volle Durchgang bleibt auf main in der CI. | Kürzerer Lauf des teuersten Gates. | Mittel: Der Archiv-Zweig ist der Rückhalt für Merges auf dem Server (`check_review.py:1473-1476`). |
| 7 | Skript für die Verbraucher-Suche; Bundle füllt die Kriterien-Tabelle vor; ein Scorer je Runde; Refute einfach. | Weniger Reviewer-Zeit je Runde. | Gering. |
| 8 | Wirkungslose Pfade machen ein Review nicht ungültig. | Eine Runde je spätem Tippfehler. | Mittel; auf ungeschützte `.md`-Dateien begrenzen. |
| 9 | Fix- und Delta-Runden setzen die Sitzung fort. | Zwei Kaltstarts je blockierter Runde. | Mittel: Der Reviewer kann auf seiner ersten Sicht ankern. Deshalb als Versuch mit Messung. |
| 10 | Tier 3: `analyze` und `converge` in Plan-Review und Review aufgehen lassen. | Zwei Prüfläufe. | Erst nach Zählung der Befunde, die nur diese Läufe fanden. |

Die Maßnahmen 1 bis 5 und 7 entfernen nur Wiederholungen. 6 und 8 bis 10 ändern, was oder wie geprüft wird, und gehören vorher gemessen.

Zahlen, die im Projekt vor Maßnahme 1 und 4 zu ziehen sind: `process_kpis.py nodes --json`, je Gate die Zahl der Läufe je Eingabestand und `cost_s` (Median und p90); `process_kpis.py train-phases` für `gates` gegen `push`. Daraus folgt die tatsächliche Ersparnis in Minuten je Paket.

## 6. Was schon einmal bezahlt wird

- Tests: Auswahl, Lanes, Zertifikat und Stempel decken Wiederholungen ab (`docs/analysis/2026-10-10-one-test-path.md`).
- Ein sauberer Rebase und Buchhaltung unter `.process-work/` machen ein Review nicht ungültig.
- Runde 2 und später prüfen nur das Delta.
- Bei Tier 2 ist das Refute in das Review gefaltet.
- Das Pre-Commit-Framework wiederholt die Gates beim Push nicht (`--unless-frame-ran`).

## 7. Tier 0, Tier 1 und Tier 3

Gezählt sind wieder volle Läufe des Gate-Runners für ein Paket ohne Beanstandung.

| Tier | Weg | Lokale Gate-Läufe | Davon auf unverändertem Stand | Tests | LLM-Prüfläufe |
|---|---|---:|---|---|---:|
| 0 | `finish.py` | 2 bis 4 | `finish`-Prüfung und Merge-Hook sehen denselben Commit | volle Merge-Suite, außer das Projekt hat den Pfad als `inert` eingetragen | 0 |
| 1 | `finish.py` | 2 bis 4 | wie Tier 0 | Auswahl beim Push, danach volle Merge-Suite | 0 |
| 0/1 | Dispatch und Train | 4 | Bundle und Push; Train und Hook | Auswahl beim Push, Suite einmal je Train | 0, aber Bundle und `REVIEW`-Zeile mit `reviewer self` |
| 2 | Dispatch und Train | 8 | siehe Abschnitt 2 | wie oben | 2 |
| 3 | Dispatch und Train | 8 bis 10 | wie Tier 2 | wie oben | 5 |

**Tier 0 und 1 über `finish.py`.** Die Läufe: optional der Push des Branches, die Prüfung in `finish` (`finish.py:318`), nach einem Rebase noch einmal (`finish.py:510`), dann der Hook beim Push nach main. Ohne Rebase sehen `finish` und der Hook denselben Commit; der Stempel des Hooks gilt aber nur je Push-Klasse (`pre_push.py:220`), deshalb läuft alles erneut. Eine einzelne Doku-Datei zahlt außerdem die volle Merge-Suite: „wirkungslos“ ist ein Pfad nur, wenn das Projekt ihn im Bereich `inert` in `testing.local.json` nennt (`quiet.py:9-21`). Das Template bringt keine Voreinstellung mit.

**Tier 0 und 1 über den Train.** Der Train nimmt einen Branch nur mit archiviertem Plan oder mit einem `review-pass`-Report samt `REVIEW`-Zeile, die den Kopf deckt (`train.py:575-602`). Ein Tier-0-Branch ohne Plan wird abgewiesen mit „no archived plan on the branch and no review-pass report“. Der Dispatch-Auftrag für Tier 0/1 verlangt deshalb Bundle, `attest.py … --reviewer self` und Report (`dispatch.py:1249-1251`). Die Regeln sagen dagegen, Tier 0/1 brauche kein Review (`verification-independence.md:34-38`). Ein kleines Paket zahlt so die Attest-Zeremonie von Tier 2 und vier Gate-Läufe.

**Tier 3.** Die Gate-Läufe entsprechen Tier 2. Dazu kommen bis zu zwei Pushes für Buchhaltung, die je einen Lauf auslösen: die Attest-Zeile der eigens gestarteten Plan-Review-Sitzung und die `REFUTE`-Zeile im Plan. Annahme: Ob diese Zeilen getrennt gepusht werden, hängt von der Sitzung ab; im Code erzwingt es nichts. Jede Fix-Runde an Gate-Code wird neu refutet (`refute.md`, Tabelle „When“) und kostet damit eine Sitzung und einen Push mehr als bei Tier 2.

Teurer als die Gates sind bei Tier 3 die fünf Prüfläufe durch ein Modell: `/speckit-analyze`, Plan-Review auf einer zweiten Modellfamilie, Refute, Review, `/speckit-converge` (`speckit.md:85-100`). Das Review mit `cross-model` ist ein Lauf auf der zweiten Familie, kein zweites Review (`model-policy.json:49`).

Maßnahmen dazu, alle ohne schwächere Prüfung:

| # | Maßnahme | Wirkung |
|---|---|---|
| 11 | Der Train nimmt Tier 0/1 ohne Plan und ohne `REVIEW`-Zeile mit, wenn der Gate-Runner das Tier aus den Pfaden bestätigt (kein Gate-Code, keine geschützten Pfade). | Bundle, Attest und zwei Gate-Läufe je kleinem Paket entfallen; die Suite wird im Train geteilt. |
| 12 | Der Gate-Merker (Maßnahme 1) gilt auch zwischen `finish`-Prüfung und Merge-Hook. | Ein Lauf je Tier-0/1-Paket. |
| 13 | Eine Voreinstellung für `inert` im Template, zum Beispiel `docs/**` außerhalb von `docs/process/`. | Keine Merge-Suite für reine Doku. Die vier Bedingungen in `quiet.py` bleiben. |
| 14 | Buchhaltungszeilen (Plan-Review-Attest, `REFUTE`) fahren mit dem nächsten Push mit; ein Push, der nur `.process-work/` ändert, lässt nur die Gates laufen, die Journal und Plan lesen. | Ein bis zwei Läufe je Tier-3-Paket, einer je Review-Runde auf allen Tiers. |

## 8. Beobachtungen aus dem Kenni-Gesamtaudit vom 2026-11-10

Eine zweite Sitzung hat vier Beobachtungen aus dem Versuch gemeldet, eine einzelne Tier-0-Doku-Datei nach main zu bringen. Geprüft habe ich sie gegen den Template-Code, nicht in Kenni.

| Beobachtung | Im Template bestätigt? |
|---|---|
| `finish.py` listet 167 `publish_and_prune.py`-Schritte für fremde, längst gemergte Specs | Ja. Der Tail nennt jedes Spec-Verzeichnis im Baum, dessen Aufgaben alle abgehakt sind, unabhängig vom Branch (`finish.py:302-308`). Er sollte nur Specs des eigenen Bereichs nennen. |
| `train.py plan` nimmt einen Tier-0-Branch nicht mit | Ja, siehe oben (`train.py:602`). |
| Eine neue Markdown-Datei unter `docs/audit/` gilt nicht als ruhiger Bereich | Ja, sobald das Projekt den Pfad nicht als `inert` führt (`quiet.py:9-21`). |
| `core.hooksPath` der Worktrees zeigt auf einen veralteten Haupt-Checkout, dessen `pre-push` ein gelöschtes Skript aufruft; jeder Push scheitert | Nicht geprüft; das ist der Zustand eines Rechners. Offen ist, ob `install_hooks.py` den Pfad so setzt, dass alle Worktrees die Hooks eines Checkouts teilen. |

Die gemeldeten Anteile (44,5 % der Commits nur auf Prozesspfaden, 10,7 % `docs: attest …`) stammen aus Kenni und sind hier nicht nachgezählt. Die Attest-Commits passen zu Lauf 6 in Abschnitt 2: Jeder davon ist ein eigener Push mit vollem Gate-Lauf.

## Anhang: Befunde außerhalb des Fokus

Nicht Gegenstand der Empfehlung, aber gesehen:
- `optimize.active()` hat im Template keinen Aufrufer; seit Einführung der Optimierungsschleife (v2.67/v2.68) nennt der CHANGELOG keine Prüfung, die aufgrund von Messwerten entfernt oder abgeschwächt wurde. Ob Projekte eigene Records haben, ist hier nicht sichtbar.
- Widerspruch zur Spec-Pflicht bei Tier 2: nein laut Kernel und `risk-tiers.md`, ja laut `journal-state-plans.md:177-180` (hartes Gate, außer mit `spec-waived`).
- `process_context.py --cost` zählt die Befehlsdateien, aber keines der Dokumente, auf die eine Phase verweist (`process_context.py:255-281`).
