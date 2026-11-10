# Audit des Dev-Prozesses: Wiederholungen im Durchlauf

Datum: 2026-11-10 · Stand: v2.93.0 · Art: Analyse, kein Plan und kein Beschluss

Auftrag des Owners: Der Umfang des Prozesses ist in Ordnung, solange er korrekt ist und gebraucht wird. Störend ist, was er in der Anwendung kostet: dass ein Arbeitspaket mehrfach durch dieselbe Prüfung läuft. Dieser Bericht zählt diese Wiederholungen und nennt je Wiederholung, ob sie entfallen kann, ohne dass eine Prüfung schwächer wird.

Methode: Code und Regeln unter `template/` gelesen, nichts ausgeführt. Die Zählungen folgen aus den Aufrufstellen im Code. Laufzeiten in Sekunden sind hier nicht messbar; Abschnitt 5 nennt, welche Zahlen im Projekt zu ziehen sind. Was nicht geprüft ist, steht als Annahme da.

## 1. Ergebnis

Ein Tier-2-Paket, das ohne Beanstandung durchgeht, läuft achtmal lokal durch den vollen Gate-Runner und, wenn ein PR offen ist, dreimal in der CI. Jede weitere Review-Runde kostet drei lokale Läufe und zwei CI-Läufe mehr; bei drei Runden sind es 14 lokale. Auf vier Ständen läuft der Runner zwei- bis dreimal, ohne dass sich am geprüften Inhalt etwas geändert hat. Für Tests gibt es dagegen ein Zertifikat; sie werden je Stand einmal bezahlt.

Rund die Hälfte der lokalen Gate-Läufe kann entfallen, ohne dass eine Prüfung wegfällt: Derselbe Runner hat denselben Stand bereits grün gesehen.

Die Messung in Kenni (Abschnitt 9) zeigt einen größeren Posten: Rote Züge verbrauchen 37 % der Zug-Minuten, weil jede Bisect-Probe die ganze Suite fährt. Das steht in der Reihenfolge jetzt vorn.

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
| Suche nach Verbrauchern eines geänderten Werts | dreimal: Plan, Plan-Review, Code-Review (korrigiert: Execute vergleicht nur den Diff) | `refute.md:138-140`, `execute.md:13`, `review-checklist.md:64-67` | Ja, zwei davon: ein Skript führt die Befehle aus `## Consumers` am Kopf neu aus und zeigt die Differenz |
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
| 0 | `finish.py` | 3 bis 5 (korrigiert) | `finish`-Prüfung und Merge-Hook sehen denselben Commit | volle Merge-Suite, außer das Projekt hat den Pfad als `inert` eingetragen | 0 |
| 1 | `finish.py` | 3 bis 5 (korrigiert) | wie Tier 0 | Auswahl beim Push, danach volle Merge-Suite | 0 |
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

## 9. Messung in Kenni und der rote Zugpfad

Die Zahlen dieses Abschnitts hat die Kenni-Sitzung am 2026-11-10 gemessen (`train-phases --runs 50`, `nodes --json` über 30 Tage, Runden aus den `REVIEW`-Zeilen der Journale gezählt). Ich habe sie übernommen, nicht nachgezählt. Den Code des roten Pfads habe ich im Template gelesen.

### 9.1 Wo die Minuten liegen

| Größe | Wert |
|---|---|
| Ein grüner Zug, Median | Plan 337 s, Gates 115 s, Suite 1.837 s, Push 152 s, Deploy 45 s: rund 40 Minuten |
| Rote Züge | 18 von 50 (36 %), in der Gesamthistorie 55 von 167 (33 %) |
| Anteil roter Läufe an den Zug-Minuten | 1.196 von 3.190 (37 %), davon 971 Minuten Retry und Bisect |
| Längster Bisect, längster Retry | 107 Minuten, 50 Minuten |
| Wartezeit des ältesten Kandidaten | 7,9 Stunden bei einer Grenze von 4,0 |
| Gate-Laufzeit, 30 Tage, 31 Gates | 82.496 s, rund 23 Stunden |

Damit verschiebt sich die Reihenfolge. Die mehrfachen Gate-Läufe aus Abschnitt 2 kosten ein Tier-2-Paket rund 15 Minuten (acht Läufe zu etwa 115 s; Annahme: Ein Lauf im Push dauert so lange wie im Zug). Ein einziger roter Zug kostet alle Passagiere ein bis drei Stunden.

### 9.2 Warum ein roter Zug so lange dauert

Der Ablauf nach einem roten Lauf (`train.py:2172-2330`):

1. Ein Wiederholungslauf auf demselben Baum: nur das Fehlgeschlagene, wenn das Projekt `--retry` gesetzt hat, sonst die ganze Suite (`retry_plan`, `train.py:1690-1702`).
2. Ist er wieder rot: Prüfung der Basis, dann Bisect über Präfixe der Passagiere.
3. Jede Bisect-Probe baut den Baum neu und fährt die Gates und die **ganze** Suite (`attempt(aboard[:mid], kind="probe")`, `train.py:2289`). Das sind rund 33 Minuten je Probe und bei acht Passagieren drei Proben.
4. Der Verursacher wird abgesetzt. Der Rest ist eine neue Kombination: wieder Gates, ganze Suite und ein eigener Wiederholungslauf.

Der Zug kann die roten Tests seit v2.88 aus der `lastfailed`-Datei lesen und in die Messung schreiben (`red_tests`, `train.py:1571-1614`); er nutzt sie nicht, um den Verursacher zu finden. **Korrigiert (Abschnitt 11):** Das gilt nur, wenn das Projekt `red_ids` gesetzt hat. Kenni hat es nicht gesetzt.

Ein Timeout unter Last sieht für den Zug aus wie ein roter Test und führt, wenn er auch den Wiederholungslauf trifft, in den Bisect. **Korrigiert (Abschnitt 11):** Der Zug selbst gibt der Suite kein Zeitlimit; die Timeouts kommen aus der Suite (Wartezeit auf eine Lane mit Exit 75, Kennis Watchdog je Test) und enden als gewöhnlicher roter Exit.

### 9.3 Maßnahmen für den roten Pfad

| # | Maßnahme | Wirkung | Risiko für die Qualität |
|---|---|---|---|
| 15 | Bisect-Proben fahren nur die roten Tests statt der ganzen Suite. Sind die Test-IDs nicht lesbar oder zu viele, bleibt es bei der ganzen Suite. | Eine Probe sinkt von rund 33 Minuten auf wenige Minuten. | **Korrigiert (Abschnitt 11):** Nicht ohne Zusatzregel. Eine grüne Probe speist heute den Merge: Sie trägt den Baum in `green_here` ein und schreibt ein Merge-Zertifikat (`train.py:2018-2023`), und der Rest nach dem Absetzen fährt die Suite dann nicht mehr (`train.py:2088-2094`). Eine verengte Probe darf nichts davon schreiben. Der Vorschlag wurde als #378 schon in vier Plan-Runden blockiert. |
| 16 | Vor dem Bisect: Die roten Tests laufen einzeln auf Basis plus je einem Passagier, wie die Vorab-Prüfung aus v2.89. | Der Verursacher steht nach wenigen kurzen Läufen fest, wenn nur ein Passagier den Fehler bringt. | Wie 15. Ein Fehler, der nur in Kombination auftritt, geht weiter in den Bisect. |
| 17 | Ein Zeitlimit oder ein Abbruch durch Last ist kein Befund über einen Passagier. Der Zug wiederholt das Fehlgeschlagene dann ein zweites Mal, seriell oder nach gesunkener Last, bevor er sucht. | Der Fall von Zug 0519: Minuten statt knapp drei Stunden. | Gering. Ein echter Fehler bleibt beim zweiten Mal rot und geht in die Suche. Die Zahl der Wiederholungen ist begrenzt. |
| 18 | **Korrigiert (Abschnitt 11):** Kenni setzt `--retry`; sein Retry-Skript wiederholt ganze rote Stages statt einzelner Tests. Der Hebel ist die Körnung dieses Skripts. | Der erste Wiederholungslauf sinkt auf Minuten. | Keins; eine Änderung in Kenni, nicht im Template. |

Die Wartezeit von 7,9 Stunden folgt zum großen Teil aus dem roten Pfad: Züge fahren nacheinander, und ein roter Zug hält die Strecke bis zu drei Stunden. Die Maßnahmen 15 bis 18 sind deshalb auch die Maßnahmen gegen die Wartezeit. Offen ist ein zweiter Grund: Der Zug fährt nicht ab, solange auf dem Klon ein Gate rot ist oder eine volle Lane belegt ist (`departure`, `train.py:659-682`). Wie oft das die Abfahrt verhindert hat, steht nicht in der Messung.

### 9.4 Gate-Kosten

| Gate | Sekunden, 30 Tage | Blocks |
|---|---:|---:|
| `web-lint` | 23.027 | 3 |
| `review` | 15.431 | nicht genannt |
| `theme-tokens` | 5.849 | 0 |
| `backend-lint` | 5.106 | nicht genannt |
| `plan-structure` | 4.590 | nicht genannt |
| `inventory` | 3.464 | 0 |
| `openapi-drift` | 3.459 | 0 |

Fünf dieser Gates sind Prüfungen des Baums, die das Projekt selbst eingetragen hat (`web-lint`, `theme-tokens`, `backend-lint`, `inventory`, `openapi-drift`). Sie machen zusammen 40.905 s aus, die Hälfte der gesamten Gate-Zeit, und haben in 30 Tagen drei oder weniger Blocks gemeldet.

- Projekt-Gates können heute schon auf Pfade begrenzt werden (`paths` und `areas` in `gates.local.json`, `gate_runner.py.jinja:568-591`). Ein `web-lint`, der nur läuft, wenn ein Web-Pfad im Flug ist, braucht keine Änderung am Template. **Korrigiert (Abschnitt 12):** Laut Steward sind diese Gates in Kenni bereits pfadbegrenzt; die Kosten entstehen, wenn sie laufen.
- Ihr Ergebnis hängt nur vom Baum ab. Sie sind damit die ersten Kandidaten für den Gate-Merker (Maßnahme 1).
- Das `review`-Gate ist mit 19 % das teuerste Gate des Templates; das stützt Maßnahme 6.

Der Push im Zug dauert 152 s bei 115 s für die Gates. Das passt zu Abschnitt 2: Der Hook wiederholt die Gates, die der Zug gerade gefahren hat.

Auffällig ist auch der Schritt „Plan“ mit 337 s im Median. Der Steward ruft `train.py plan` bei jedem Tick auf (`steward.md:95`). Was darin die Zeit kostet, habe ich nicht untersucht.

### 9.5 Blockierte Review-Runden

| Tier | Arbeiten | Ø blockierte Runden | mit ≥ 1 Block | mit ≥ 2 Blocks | max |
|---|---:|---:|---:|---:|---:|
| 1 | 24 | 0,12 | 3 (13 %) | 0 | 1 |
| 2 | 140 | 0,49 | 39 (28 %) | 10 (7 %) | 9 |
| 3 | 163 | 1,11 | 87 (53 %) | 43 (26 %) | 9 |

Zwei Dinge fallen auf:
- Die Hälfte aller Arbeiten ist Tier 3 (163 von 327). `risk-tiers.md` sieht Tier 3 für Zugriffsschutz, Datenhaltung, Sicherheitsgrenzen und Verträge über mehrere Repositories vor und nennt ein unnötiges Tier 3 selbst den Engpass. Zu klären ist, aus welchem Grund diese 163 Arbeiten Tier 3 sind; die `tier:`-Zeile jedes Plans nennt ihn.
- Bei Tier 3 wird jede zweite Arbeit mindestens einmal blockiert. Jede blockierte Runde kostet zwei Sitzungen und drei Gate-Läufe. Welcher Anteil dieser Blocks hält, zeigt `process_kpis.py rounds`, sobald es durchgelaufen ist; dort steht auch der Anteil der Blocks auf Zeilen, die seit Runde 1 unverändert sind.

### 9.6 Reihenfolge nach der Messung

1. Roter Zugpfad: Maßnahmen 15 bis 18.
2. Gate-Zeit: Projekt-Gates auf Pfade begrenzen (Konfiguration in Kenni), dann der Gate-Merker (Maßnahmen 1, 2, 12, 14).
3. Tier-3-Anteil und blockierte Runden: erst die beiden Zählungen aus 9.5, dann die Maßnahmen 3, 9 und 10.
4. Tier 0/1 im Zug und die `inert`-Voreinstellung (Maßnahmen 11 und 13).

## 10. Abstimmung mit der Sitzung „Dev-Prozess Optimierung“

Vorschlag des Owners: Die Optimierungs-Sitzung plant und setzt um, die Audit-Sitzung liest Plan und Ergebnis gegen diesen Bericht. Vor einer Umsetzung bitte bewerten; ob und was umgesetzt wird, entscheidet der Owner.

Pakete:
- **A. Roter Zugpfad:** Maßnahmen 15 bis 18.
- **B. Gate-Läufe:** Maßnahmen 1, 2, 4, 12 und 14.
- **C. Texte und Tail:** Maßnahme 3 ohne den Lesezugriff, dazu der `finish`-Tail aus Abschnitt 8.
- **D. Tier 0/1:** Maßnahmen 11 und 13.

Fragen:
1. Welcher Befund ist falsch oder schon erledigt? Die Audit-Sitzung hat gelesen und nichts ausgeführt.
2. Zu A: Welcher Vorfall spricht dagegen, Bisect-Proben auf die roten Tests zu beschränken (Reihenfolgeabhängigkeit, Fehler nur in der ganzen Suite, Stages ohne pytest)? Reicht „schlimmstenfalls wird der Falsche abgesetzt, nie falsch gemergt“ als Sicherheitsargument?
3. Zu B: Welche Gates lesen Zustand außerhalb des Baums und dürfen nie aus dem Merker kommen?
4. Schnitt: ein Release je Paket, alles reine Updates? Was davon ist Migration?
5. Aufteilung: Plan-Review und Refute laufen wie in `MAINTAINING.md` in frischen Sitzungen. Die Audit-Sitzung prüft, ob der Plan die Befunde trifft und keine Prüfung schwächer wird. Passt das?

## 11. Korrekturen nach Gegenprüfung durch die Optimierungs-Sitzung

Die Optimierungs-Sitzung hat den Bericht am 2026-11-10 gegen v2.93.0 und gegen Kennis Checkout geprüft (Kommentar im PR #407). Die folgenden Punkte habe ich an den genannten Stellen nachgelesen und übernommen; die betroffenen Stellen oben sind als korrigiert markiert.

**Was ich falsch oder unvollständig hatte:**
- **Maßnahme 15 ist als #378 schon gescheitert.** Vier Plan-Runden haben den Teillauf blockiert; der Owner entschied am 2026-11-04 „Erst messen“ (`docs/analysis/2026-11-04-v2.88.md:8-10,231`). v2.88 lieferte nur die Messung. Das habe ich übersehen.
- **Mein Sicherheitsargument zu 15 hielt nicht.** Eine grüne Probe speist den Merge (`green_here`, Merge-Zertifikat). War der Verursacher der letzte Passagier, ist der Rest genau der zuletzt grün geprobte Baum, und seine Suite läuft nicht noch einmal. Mit Proben, die nur rote Tests fahren, würde so ein Baum gemergt, dessen ganze Suite nie grün war. Das war der Blocker in Runde 3 von #378.
- **Weitere Einwände gegen 15:** Bringt der Verursacher seinen roten Test selbst mit, kennen frühere Präfixe die ID nicht und werden fälschlich rot. Eine kleine Testmenge verteilt sich unter xdist anders. Die Merge-Suite ist eine Shell-Zeile ohne Vertrag für Test-IDs. Die `lastfailed`-Datei liegt im Worktree, den der Zug bei jedem Versuch neu baut.
- **Maßnahme 18** betrifft Kennis Retry-Skript, nicht das Template.
- **Lauf 8 ist keine reine Wiederholung.** Nur beim Merge-Push blockieren die Prüfungen, die am Merge hängen; Train und `finish` fahren die Gates ohne Push-Ziel, dort sind dieselben Befunde Hinweise (`check_review.py:1462-1476`). Lauf 8 entfällt erst, wenn Train und `finish` das Ziel übergeben.
- **`finish` zählt drei bis fünf Läufe für Tier 0/1**, weil `finish.py` und `finish.py --apply` beide prüfen (`finish.py:456`).
- **Die Verbraucher-Suche läuft dreimal**, nicht viermal.
- **Der Rebase-Text steht an drei Stellen**, nicht an einer: zweimal in `finish.py`, einmal in `releases.md`.
- **„Fünf von sechs Blocks sind Fehlalarme“ (Abschnitt 4) war zu weit geschlossen.** Die Messung betrifft Befunde, nicht Blocks; `/review` filtert blockierende Befunde bereits über einen Scorer.
- **Der veraltete Hook-Pfad (Abschnitt 8) kommt nicht aus dem Template.** `install_hooks.py` setzt `core.hooksPath` nicht; die Ursache ist ein im Projekt gesetzter absoluter Pfad.
- **Der Widerspruch zur Spec-Pflicht bei Tier 2 besteht nicht**; der Anhang ist bereinigt.

**Was der Gate-Merker (Maßnahme 1) zusätzlich braucht:**
- Der Schlüssel kann nicht der Baum-Hash des Testzertifikats sein: Der lässt `.process-work/` aus, das mehrere Gates lesen.
- Nie aus dem Merker: `review` (liest alle Refs und kann das Netz brauchen), `github-issues` (Netz) und Projekt-Gates, solange das Projekt nicht zustimmt.
- Gates, die am Fork-Punkt hängen (`plan-structure`, `ui-check`, `feature-registry`, `design-contracts`), nur mit HEAD und den Ref-SHAs im Schlüssel.
- Parallele Gates (Maßnahme 4) erhöhen die Last, und Last ist eine Ursache roter Züge. Also als Opt-in oder nach CPU-Zahl begrenzt.

**Neue Reihenfolge, abgestimmt:**
1. **C, Texte und Tail.** Reines Update, billig: alle drei Stellen des Rebase-Texts, die Archiv-Reihenfolge, der `finish`-Tail.
2. **A, roter Pfad, in dieser Folge:** erst 17 (Timeout und Lastabbruch sind kein Befund über einen Passagier), dann 16 auf der Vorab-Prüfung aus v2.89 aufgebaut. 15 nur, wenn Kenni `red_ids` setzt und die Messung genug geeignete Runden zeigt, und nur mit der Regel, dass eine verengte Probe nichts schreibt, was einen Merge stützt. Der Plan baut auf #378 auf.
3. **In Kenni, kein Template-Paket:** Körnung des Retry-Skripts; Projekt-Gates auf Pfade begrenzen; die beiden Zählungen aus 9.5 (warum 163 von 327 Arbeiten Tier 3 sind, welcher Anteil der Blocks hält).
4. **B, Gate-Merker**, mit dem Schlüssel und den Ausnahmen von oben. Reines Update, solange Projekt-Gates unverändert laufen.
5. **D, Tier 0/1.** Migration oder ein Schalter, der standardmäßig aus ist: Die Pfade, die Gate-Code kennzeichnen, sind fest verdrahtet und kennen projekteigene Gate-Skripte nicht; eine `inert`-Voreinstellung trifft Projekte, deren Tests Doku lesen.

## 12. Abgestimmtes Ergebnis (Stand 2026-11-10)

Abgestimmt mit der Optimierungs-Sitzung über den PR #407 und mit dem Steward von Kenni. Die Angaben des Stewards stammen aus seinem Checkout und sind hier nicht nachgeprüft. Umgesetzt ist nichts; die Entscheidung liegt beim Owner.

**Korrektur aus Kenni:** Die teuren Projekt-Gates (`web-lint`, `backend-lint`, `openapi-drift`, `theme-tokens`) sind dort bereits pfadbegrenzt. Die Empfehlung, sie zu begrenzen, entfällt. Ungebunden sind `review`, `plan-structure`, `design-contracts`, `inventory` und `feature-registry`; nur `inventory` ist ein Kandidat, und erst nach einer Analyse dessen, was es liest.

**Zentral im Template:**

| Release | Inhalt | Art |
|---|---|---|
| 1 | Rebase-Text an allen drei Stellen, Archiv-Reihenfolge, `finish`-Tail. Dazu die drei sicheren Teile aus dem Gate-Paket: Train und `finish` übergeben das Merge-Ziel an die Gates; kein Gate-Lauf für Plan-Review-Bundles; `finish --apply` verwendet das Prüfergebnis desselben Laufs wieder, wenn der Baum unverändert ist. | reines Update |
| 2 | Roter Pfad. Zuerst 17: Ein Abbruch durch Last oder Timeout ist kein Befund über einen Passagier. Das Signal ist eine Marker-Datei, deren Pfad der Zug der Suite vorgibt und vor jedem Lauf löscht; ein Exit-Code geht in `make` und unter xdist verloren. Danach 16: rote Tests je Passagier, aufgebaut auf der Vorab-Prüfung. | reines Update |
| 3 | Teillauf im Bisect (#378 wieder geöffnet), getrennt von Release 2. Erst nach der Messung mit `red_ids` aus Kenni. Abnahmekriterien sind die Blocker der vier Runden, dazu: Ein Baum, den nur eine verengte Probe grün sah, fährt vor jedem Merge die ganze Suite. | nach Messung |
| 4 | Der eigentliche Gate-Merker, erst nach einer Rechnung, was er je Lauf spart. Parallele Gates nur als Opt-in. | reines Update |
| 5 | Tier 0/1 im Zug als Schalter, der aus ist. Gate-Pfade aus `gates.local.json`; ein nicht auflösbarer Pfad gilt als Gate-Code. Keine `inert`-Voreinstellung im Template. | Schalter oder Migration |

Bedingungen für das Marker-Signal in Release 2, je mit Negativtest: Ein solcher Abbruch führt nie zu einem Merge und nie zu einer Schuldzuweisung; nach einer begrenzten Zahl von Wiederholungen endet die Runde mit „Umgebung“; ein Test, der auch ohne Marker rot ist, bleibt rot; der Zug liest den Marker nur an dem Pfad, den er selbst gesetzt hat.

**In Kenni (Steward):**

| Schritt | Inhalt | Art |
|---|---|---|
| a | `inert` für reine Doku-Pfade und `red_ids` in `testing.local.json` setzen. `red_ids` liefert nur Daten für Backend-Tests; die vitest-Stage bleibt ohne. | Konfiguration |
| b | Der Watchdog schreibt die Marker-Datei aus Release 2. Laut Steward der größte Hebel. | Tier 3, nach Release 2 |
| c | Körnung des Retry-Skripts. Es wiederholt mit Absicht ganze Stages (#2469), weil der Retry auch nachholen muss, was nicht lief. Erst nach den Daten aus a. | Tier 3 |
| d | Zählungen: warum 163 von 327 Arbeiten Tier 3 sind, welcher Anteil der Blocks hält. | Messung |

**Offen:** Wo die Marker-Datei liegt. Die Optimierungs-Sitzung schlägt einen Pfad im Worktree vor, den der Zug per Umgebungsvariable vorgibt; der Steward das git-dir. Das entscheidet der Plan für Release 2.

## Anhang: Befunde außerhalb des Fokus

Nicht Gegenstand der Empfehlung, aber gesehen:
- `optimize.active()` hat im Template keinen Aufrufer; seit Einführung der Optimierungsschleife (v2.67/v2.68) nennt der CHANGELOG keine Prüfung, die aufgrund von Messwerten entfernt oder abgeschwächt wurde. Ob Projekte eigene Records haben, ist hier nicht sichtbar.
- `process_context.py --cost` führt die Prozess-Dokumente nur als Summe „available“; die Kosten je Phase weist es nicht aus (`process_context.py:255-281`).
