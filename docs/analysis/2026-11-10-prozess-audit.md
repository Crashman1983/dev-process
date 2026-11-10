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

## 13. Radikalere Varianten (Auswahl des Owners: 1, 4, 5 und 2)

Anlass: Die Pakete aus Abschnitt 12 reparieren den Zug. Der Aufwand je Arbeitspaket entsteht woanders. Belege aus den eigenen Analysen:
- 47 % der Blocker ab Runde 2 stammen aus dem Fix der Vorrunde, 39 % sind Plan-Lücken, 0 % Rauschen (`docs/analysis/2026-10-21-v2.77.md:19-26`).
- Unter 200 Produktzeilen brauchen 10 % der Arbeiten drei oder mehr Runden, über 1.500 Zeilen 53 %; über mehrere Stacks 44 %, in einem 18 % (`docs/analysis/2026-10-28-v2.80.md:14-15`).
- Ein Fix-Durchgang über 300 Zeilen zog in zwei von drei Folgerunden einen neuen Blocker nach sich (`make_review_bundle.py:793-796`).

Die Zahlen, die für eine Entscheidung noch fehlen, sind beim Steward angefragt: Zeit je Arbeitspaket nach Phase, Runden mit und ohne Plan-Review, Durchrutscher je Tier, Größenverteilung, Aufwand der Template-Updates.

### Variante 1: Größe begrenzen

Heute: ein Hinweis in `/plan` ab etwa 500 Produktzeilen und eine Warnung im Bundle ab 30 Dateien oder 1.500 Zeilen (`make_review_bundle.py:591-592,929`). Beides blockiert nicht.

Vorschlag:
- Das Bundle für Runde 1 verweigert oberhalb der Grenze, statt zu warnen. Die Zahl misst es schon. Eine Ausnahme ist eine `DECISION`-Zeile des Owners im Plan mit Grund, wie bei `review-waived`.
- Die Grenze kommt aus den Zahlen des Projekts (`process_kpis.py size`), als Start 500 Produktzeilen und ein Stack.
- Keine neue Pflichtangabe im Plan. Eine geschätzte Größe ließe sich pro forma erfüllen; die gemessene nicht.

Preis: Jeder Schnitt zahlt den festen Prozess noch einmal (Plan-Review, Review, Attest, Merge). Die Variante lohnt sich deshalb erst richtig zusammen mit Variante 4. Risiko für die Qualität: keins; kleinere Arbeiten werden gründlicher gelesen.

Entscheidende Zahl: Anteil der Arbeiten über 500 Zeilen und ihr Anteil an allen Runden.

### Variante 2: Fix-Schleife umbauen

Heute: Jede blockierte Runde startet eine neue Fix-Sitzung und danach ein neues Review. Ab Runde 2 kommt eine `REPLAN`-Zeile dazu, nach Runde 3 entscheidet der Owner (`verification-independence.md:183-224`).

Vorschlag:
1. **Ein Block braucht einen ausführbaren Beleg.** Der Reviewer liefert je Blocker einen roten Test oder ein Skript, als Patch am Report, nicht als Commit auf dem Branch. Ohne Beleg ist der Befund ein Rest oder ein Folge-Issue. Ausnahme mit Begründung: Befunde, die sich nicht als Test fassen lassen, etwa eine fehlende Berechtigungsprüfung im Entwurf. Die Skala kennt das schon: Ein gemessener Unterschied alt/neu zählt 100.
2. **Der Fix-Durchgang ist begrenzt.** Er macht die gelieferten Tests grün und deckt die Geschwisterstellen ab. Über 300 Zeilen ist er kein Fix mehr, sondern ein Neubau mit neuem Plan-Review.
3. **Runde 2 ist eine Delta-Prüfung durch dieselbe Reviewer-Sitzung.** Sie prüft, ob die Tests grün sind und ob der Fix neue Wege öffnet. Befunde auf Code, der seit Runde 1 unverändert ist, werden in Runde 2 Folge-Issues, außer bei Datenverlust und Sicherheit.
4. **Nach Runde 2 entscheidet der Owner**, nicht erst nach Runde 3.

Risiko für die Qualität: mittel. Ein spät gefundener Fehler auf unverändertem Code wird mit Folge-Issue gemergt. Die Variante gehört als Versuch nach `optimization.md` gefahren, mit vorher festgelegten Kriterien: Runden je Arbeit, Anteil fix-induzierter Blocker, Durchrutscher innerhalb von sieben Tagen.

Entscheidende Zahl: Anteil der Blocks ab Runde 2 auf seit Runde 1 unveränderten Zeilen (`process_kpis.py rounds`).

### Variante 4: Nachweise aus dem Commit-Strom

Heute: Jede Runde endet mit einem Attest-Commit auf dem Branch, einem Push und einem vollen Gate-Lauf. In Kenni sind das 1.380 Commits in 90 Tagen, 10,7 % aller Commits (Zahl aus dem Kenni-Audit).

**4a, klein:** Ein Push, der gegenüber einem grün gestempelten Stand nur `.process-work/` ändert, fährt nur die Gates, die Journal und Plan lesen. Die Projekt-Gates laufen nicht. Das ist dieselbe Annahme, die der Hook heute für Tests macht („tree passed this push before — gates only“, `pre_push.py:236-237`), und damit keine schwächere Prüfung. Die Projekt-Gates sind in Kenni zwar pfadbegrenzt, aber gegen alle Pfade des Branches, nicht gegen das, was der Push ändert; deshalb laufen sie heute bei jedem Attest-Push mit.
- Wirkung, Obergrenze: 460 Attest-Commits im Monat mal rund 115 s sind etwa 15 Stunden Gate-Zeit bei 23 Stunden insgesamt. Tatsächlich weniger, weil mehrere Commits in einem Push fahren können.
- Aufwand: eine Änderung an Hook und Runner; Gate-Code, also Tier 3.

**4b, strukturell:** Der Attest landet nicht mehr als Commit auf dem Branch. Wo alle Worktrees ein Repository teilen, wie in Kenni, schreibt `attest.py` in eine eigene Referenz, gebunden an den geprüften Commit. Der Zug schreibt die Zeilen einer Arbeit beim Merge in das Journal auf main, im Merge-Commit. Die dauerhafte Akte auf main bleibt.
- Wirkung: ein Commit je Merge statt mehrerer je Runde; die Unterscheidung „Buchhaltung oder Code“ im Review-Gate wird einfacher.
- Grenze: Cloud-Umgebungen lehnen Pushes auf andere Referenzen ab (`tower.md:340-345`). Für entfernte Reviewer muss der Weg über den Branch bleiben. Damit gäbe es zwei Wege für denselben Nachweis im größten Gate (`check_review.py`, 3.691 Zeilen).
- Urteil: erst 4a, messen, dann über 4b entscheiden. 4b lohnt nur, wenn 4a den größten Teil nicht holt.

Risiko für die Qualität: gering bei beiden; die Bindung an den geprüften Commit bleibt.

### Variante 5: Prozess einfrieren

Heute: 74 Release-Tags seit Anfang Oktober. Jedes Update ist im Projekt ein Arbeitspaket.

Vorschlag:
- Bis zu einem festen Datum, etwa acht Wochen: keine neuen Regeln, Gates oder Pflichtzeilen. Erlaubt sind Fehlerkorrekturen, die Arbeit blockieren, und Änderungen, die Aufwand entfernen.
- Ein Release im Monat. Die Änderungen aus den Abschnitten 12 und 13 fahren gebündelt in einem Release statt in fünf.
- Jeder Wunsch nach einer neuen Regel wird in der Zeit als Issue gesammelt und am Ende gemeinsam bewertet, mit der Messung aus 9.5 und den Zahlen des Stewards.

Das ist eine Entscheidung des Owners in `MAINTAINING.md`, kein Code. Risiko für die Qualität: gering; eine Lücke, die in der Zeit auffällt, bleibt bis zum nächsten Release offen, sofern sie keine Arbeit blockiert.

Entscheidende Zahl: wie viele Arbeitspakete, Sitzungen und Review-Runden die Template-Updates in Kenni in 30 Tagen gekostet haben.

### Zusammenspiel und Reihenfolge

- 5 zuerst: Es kostet nichts und ändert den Plan aus Abschnitt 12 von fünf Releases auf eines.
- 1 und 4a in dieses eine Release, zusammen mit Release 1 und 2 aus Abschnitt 12. 1 erhöht die Zahl der Arbeiten, 4a senkt den festen Preis je Arbeit.
- 2 als Versuch in Kenni, sobald die Zahlen des Stewards vorliegen.
- 4b, Gate-Merker und Tier 0/1 im Zug bleiben zurückgestellt.

## 14. Eigene Zählung in Kenni (Stand `f0f03360ef`, 2026-11-10)

Der Owner hat der Audit-Sitzung Lesezugriff auf Kenni gegeben. Gezählt sind die `REVIEW`-Zeilen der Journale (1.173, davon 379 Plan-Reviews) und die `FINDING`-Zeilen der Review-Reports (4.714), Zeitraum im Wesentlichen 2026-10-01 bis 2026-11-10. Der Klon ist flach: Größen und Zeiten je Arbeit, die die Git-Historie brauchen, fehlen weiter.

**Code-Reviews je Tier**

| Tier | Arbeiten | Ø Blocks | mit ≥ 1 Block | mit ≥ 2 | mit ≥ 3 |
|---|---:|---:|---:|---:|---:|
| 1 | 24 | 0,12 | 12 % | 0 % | 0 % |
| 2 | 140 | 0,49 | 28 % | 7 % | 5 % |
| 3 | 163 | 1,37 | 53 % | 29 % | 14 % |

- 198 von 327 Arbeiten (61 %) gehen ohne Block durch. Die oberen 10 % der Arbeiten tragen 59 % aller Code-Blocks.
- Der Tier-3-Wert liegt über dem des Stewards (1,11), weil hier jede `block`-Zeile zählt.
- Verlauf: Im Oktober waren 51 % der neuen Arbeiten Tier 3 bei 0,84 Blocks im Mittel, im November bisher 33 % bei 0,77 (43 Arbeiten).

**Plan-Reviews**

| Tier | Pläne | Ø Blocks | mit ≥ 1 Block |
|---|---:|---:|---:|
| 2 | 87 | 0,32 | 6 % |
| 3 | 107 | 0,58 | 37 % |

Tier-2-Arbeiten seit 2026-10-10 mit Plan-Review: 79, im Mittel 0,44 Code-Blocks; ohne: 14, im Mittel 1,07. Die zweite Gruppe ist klein, und Arbeiten ohne Plan-Review können sich auch sonst unterscheiden. Die Zahl spricht für das Plan-Review, beweist es aber nicht.

**Befunde**

- 80 % aller Befunde sind `minor` oder `nit` (3.814 von 4.714). 1.412 davon tragen `action=fix`: Sie blockieren nicht, werden aber bearbeitet.
- Blocker und Major in Code-Reviews (577). Wo die Felder gesetzt sind:
  - Herkunft (321): 61 % aus dem ersten Entwurf, 26 % aus dem Fix der Vorrunde, 12 % spät gefunden.
  - Klasse (257): 86 % `testable`, also als Test fassbar.
  - Prüfbarkeit (435): bei 115 Befunden hätte nach Einschätzung des Reviewers ein Gate oder Test sie finden können.
- Blocker und Major in Plan-Reviews (288): 39 % `requirement`, 14 % `knowledge-gap`.
- Gut 40 % der Blocker und Majors tragen die Felder nicht; die Anteile gelten für die beschrifteten.

**Kenni ist strenger als das Template**

- `cross_model_from_tier` steht in Kenni auf 2 (Template: 3). 177 von 280 Tier-2-Review-Zeilen tragen `cross-model`. Jede Tier-2-Arbeit zahlt damit eine zweite Modellfamilie.
- 16 Einträge in `gates.local.json`, 17 Dateien `*.local.*` (Aufschlüsselung in Abschnitt 15), 195 `REVIEW-EXCEPTION`-Zeilen, 111 von 455 Plänen mit `spec-waived`.
- Kenni führt ein eigenes Tier-Dokument mit 2.833 Wörtern neben dem des Templates (908 Wörter).

**Was die Zahlen für die Varianten bedeuten**

- **Variante 2 (Blocks als Tests) ist gestützt:** 86 % der beschrifteten Blocker und Majors sind als Test fassbar.
- **Der Anteil fix-induzierter Blocker liegt hier bei 26 %**, nicht bei 47 % wie in der v2.77-Analyse. Jene zählte Blocker ab Runde 2; hier sind alle Runden gezählt.
- **Die Last ist stark konzentriert.** Eine Regel für die wenigen entgleisenden Arbeiten (früher Abbruch, Neuschnitt) trifft 59 % der Blocks, ohne die 61 % zu berühren, die glatt durchgehen.
- **Die Nebenlast der kleinen Befunde ist neu:** 1.412 bearbeitete `minor`- und `nit`-Befunde.
- **Warum eine Arbeit Tier 3 ist, lässt sich nicht auszählen.** Die Pläne tragen dafür kein Feld; `mutation:` steht bei der Hälfte auf `runtime`, bei einem Drittel fehlt es.

## 15. Größe, Zeit und Korrekturen aus Kennis Historie

Nachgeladen: 6.738 Commits seit 2026-09-25. Gezählt sind 314 Train-Merges zu 269 Issues; 200 davon lassen sich mit den Review-Zeilen verbinden. Produktzeilen sind geänderte Zeilen in Code unter `backend/`, `frontend-react/` und `ios/` ohne Tests; die Einordnung der Pfade ist meine und eine Näherung.

**Blocks nach Größe**

| Produktzeilen | Arbeiten | Ø Blocks | mit ≥ 1 Block | Anteil an allen Blocks |
|---|---:|---:|---:|---:|
| 0 | 74 (37 %) | 0,77 | 33 % | 28 % |
| unter 200 | 64 (32 %) | 0,31 | 17 % | 9 % |
| 200 bis 500 | 26 (13 %) | 0,88 | 34 % | 11 % |
| 500 bis 1.500 | 18 (9 %) | 2,06 | 55 % | 18 % |
| über 1.500 | 18 (9 %) | 3,56 | 100 % | 31 % |

- Arbeiten über 500 Produktzeilen sind 18 % der Arbeiten und tragen 49 % der Blocks.
- Bei Tier 3 unter 200 Zeilen: 0,06 Blocks im Mittel (18 Arbeiten). Bei Tier 3 über 1.500 Zeilen: 4,14 (14 Arbeiten). Die Größe erklärt die Runden besser als das Tier.
- Zwei Stacks: 3,11 Blocks im Mittel (19 Arbeiten); ein Stack: 0,77 (104).
- Arbeiten ohne Produktcode (Prozess, Doku, Specs, Tests, Design-Runden) sind 37 % der Arbeiten und tragen 28 % der Blocks.

**Zeit und Prozessanteil**

| Tier | Arbeiten | Durchlauf Median | p90 | Commits Median | davon nur Prozesspfade | Prozesszeilen je Produktzeile |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 16 | 2,6 h | 17,6 h | 5 | 64 % | 31,3 |
| 2 | 94 | 5,5 h | 57,6 h | 11,5 | 60 % | 4,2 |
| 3 | 90 | 7,9 h | 90,2 h | 20 | 57 % | 1,6 |

- Durchlauf vom ersten Commit bis zum letzten Merge. Ohne Block: Median 3,5 h. Mit einem Block: 11,9 h. Mit zwei oder mehr: 29,8 h.
- Über alle Train-Merges: 177.000 geänderte Produktzeilen, 320.000 Testzeilen, 310.000 Prozesszeilen.

**Korrekturen innerhalb von sieben Tagen**

Näherung: Ein Fix-Commit einer anderen Arbeit ändert innerhalb von sieben Tagen eine Produktdatei, die die Arbeit geändert hat. Das überzählt bei Dateien, die viele Arbeiten berühren.

- Tier 2: 31 von 52 (59 %). Tier 3: 39 von 57 (68 %).
- Arbeiten ohne Block: 57 %. Arbeiten mit mindestens einem Block: 73 %.

Die Näherung taugt nicht als Qualitätsmaß. Sie zeigt aber: Mehr Review-Runden gehen nicht mit weniger Folgekorrekturen einher. Größe steckt in beidem.

**Arbeiten ohne Produktcode, aufgeschlüsselt**

74 Arbeiten mit zusammen 57 Code-Blocks, eingeordnet nach dem Bereich mit den meisten geänderten Zeilen (Buchhaltung unter `.process-work/`, `specs/` und `news/` nicht mitgezählt):

| Überwiegend geändert | Arbeiten | Blocks | Ø Blocks | davon Tier 3 |
|---|---:|---:|---:|---:|
| Tests | 37 | 25 | 0,68 | 11 |
| Prozess-Maschinerie (`scripts/process/`, `docs/process/`, Hooks, CI, Befehle) | 21 | 22 | 1,05 | 15 |
| Design (`docs/design/`) | 5 | 7 | 1,40 | 1 |
| Sonstiges, Projekt-Werkzeug, Doku | 11 | 3 | 0,27 | 1 |

- Über alle 200 Arbeiten gerechnet überwiegt die Prozess-Maschinerie bei 22 Arbeiten (11 %) mit 26 Blocks (12 %). Die Vermutung, ein Viertel der Review-Last hänge am Prozess selbst, ist damit nicht gedeckt; es ist etwa ein Achtel.
- Diese Last ist stark konzentriert: Vier Template-Updates (#2393 mit 9 Blocks, #2416 mit 4, #2352 und #2720 mit je 2) tragen 17 der 22 Blocks. 15 der 21 Arbeiten sind Tier 3.
- Bei den reinen Test-Arbeiten trägt eine einzige (#2717) 9 der 25 Blocks.

**Kennis lokale Dateien und Gates**

- Von den 17 Dateien `*.local.*` sind 11 Konfiguration (JSON) und 6 Text. Alle sechs Texte sind erklärte Overlays mit `overlay-of:` und `extends:` auf Abschnitte der Template-Dokumente. Sie ergänzen und verschärfen; `review.local.md` sagt das ausdrücklich. Zusammen 5.325 Wörter, davon 3.398 in `review.local.md`.
- Daneben führt Kenni `docs/dev/process-risk-tiers.md` mit 2.833 Wörtern als eigenes Dokument, kein Overlay.
- Von den 16 Gates sind neun Produktprüfungen, die den Gate-Runner als Startpunkt nutzen (Lint für Backend und Web, OpenAPI- und Schema-Drift, Theme-Tokens, iOS-Guards, SBOM, Bild-Duplikate, ein Design-Board-Test). Zwei rufen Skripte des Templates auf (`inventory`, `baseline-duplicates`). Fünf sind eigene Prozessprüfungen (`owner-bypass`, `plan-branch-tests`, `kit-tokens`, `plan-retention`, `token-growth`), dazu ein eigenes `check_feature_registry.py`.

## 16. Was die späten Review-Runden finden

Gezählt aus den `REVIEW`-Zeilen (250 Issues mit Code-Reviews) und den `FINDING`-Zeilen der Review-Reports, die eine Rundennummer tragen (2.566 Befunde). Herkunft nach dem Feld `origin`: `draft` und `late` stammen aus dem ersten Entwurf, `fix` aus einer Reparaturrunde.

**Verteilung der Runden**

| Runde | Review-Läufe | Blocks |
|---|---:|---:|
| 1 | 386 | 120 |
| 2 | 152 | 52 |
| 3 | 72 | 32 |
| 4 und später | 104 | 53 |

23 von 250 Issues (9 %) liefen bis Runde 4 oder weiter. Sie tragen 148 von 257 Blocks (58 %). 22 der 23 endeten mit einem Pass; bei 9 gab es Owner-Ausnahmen.

**Blocker und Majors nach Runde und Herkunft** (nur Befunde mit gesetztem Feld)

| Runde | Blocker und Majors | aus Reparatur | aus dem ersten Entwurf |
|---|---:|---:|---:|
| 1 | 211 | 2 % | 98 % |
| 2 | 73 | 51 % | 49 % |
| 3 | 52 | 50 % | 50 % |
| 4 und später | 41 | 61 % | 39 % |

- Ab Runde 2 stammt etwa die Hälfte der schweren Befunde aus der Reparatur davor, ab Runde 4 sind es 61 %. Das bestätigt die v2.77-Analyse (47 % ab Runde 2).
- Die späten Runden sind kein Leerlauf: Runde 4 und später fanden 9 Blocker und 32 Majors, davon rund 13 echte Fehler aus dem ersten Entwurf.
- Von 337 Befunden ab Runde 4 sind 296 `minor` oder `nit`.
- Einschränkung: Die 41 schweren Befunde ab Runde 4 stammen aus 25 Reports zu 11 der 23 langen Issues; die übrigen Reports tragen keine Rundennummer oder keine Befundzeilen.

**Folgerung für einen frühen Halt**

- Ein Halt, der „mit Restpunkten mergen“ bedeutet, wäre riskant: Auch nach Runde 3 liegen echte Fehler im Entwurf.
- Ein Halt, der „nicht weiter reparieren, sondern neu schneiden“ bedeutet, ist gestützt: Die Mehrheit dessen, was späte Runden finden, hat die Reparatur erst erzeugt, und ein Neubau in kleineren Teilen erzeugt es nicht.
- Die Regel dafür gibt es schon (`REPLAN … rebuild` ab der zweiten blockierten Runde). Sie wird in Kenni an 13 % der geschuldeten Stellen geschrieben und hat keine Folge, wenn `increment` gewählt wird. Wirksam wäre: Nach dem zweiten Block ist `increment` nur noch mit Owner-Entscheidung möglich; der Normalfall ist der Neuschnitt.

## 17. Vorschlag: drei Maßnahmen gegen die entgleisenden Arbeiten

Der Owner ist mit allen drei Maßnahmen einverstanden, für Maßnahme 1 mit den Startwerten zehn Aufgaben sowie 300 und 500 Produktzeilen (Entscheidung vom 2026-11-10). Die Gegenprüfung durch die Optimierungs-Sitzung steht aus; umgesetzt ist nichts. Grundlage sind die Zählungen aus den Abschnitten 14 bis 16 und die folgende Verfeinerung.

**Wo die Grenze liegt**

Produktzeilen sind geänderte Codezeilen ohne Tests, gemessen am gemergten Diff. Sie stehen erst fest, wenn gebaut ist.

| Produktzeilen | Arbeiten | Ø Blocks | mit ≥ 1 Block |
|---|---:|---:|---:|
| 1 bis 99 | 49 | 0,20 | 14 % |
| 100 bis 199 | 15 | 0,67 | 26 % |
| 200 bis 299 | 12 | 0,50 | 8 % |
| 300 bis 499 | 14 | 1,21 | 57 % |
| 500 bis 799 | 10 | 2,30 | 60 % |
| 800 bis 1.499 | 8 | 1,75 | 50 % |
| ab 1.500 | 18 | 3,56 | 100 % |

Der Sprung liegt bei 300 Zeilen, nicht bei 500. Ab 300 Zeilen: 25 % der Arbeiten, 58 % der Blocks.

Vor dem Bau ist die Zahl der Aufgaben im Plan der beste Anzeiger. Sie hängt enger mit den Blocks zusammen (Rangkorrelation 0,46) als die Produktzeilen selbst (0,28):

| Aufgaben im Plan | Arbeiten | Ø Blocks | mit ≥ 2 Blocks | Produktzeilen, Median | Anteil an den Blocks |
|---|---:|---:|---:|---:|---:|
| bis 5 | 110 | 0,35 | 6 % | 23 | 19 % |
| 6 bis 10 | 53 | 1,26 | 24 % | 138 | 34 % |
| 11 bis 20 | 15 | 2,73 | 40 % | 950 | 20 % |
| über 20 | 11 | 4,55 | 63 % | 5.076 | 25 % |

Gezählt sind Checkbox-Zeilen in Plan und Aufgabenliste, über alle Phasen eines Issues summiert (189 Arbeiten mit auffindbarem Plan). Die Zahl der Akzeptanzkriterien und der im Plan genannten Dateien sagt deutlich weniger aus.

**Maßnahme 1: Größengrenze an zwei Stellen**

- Beim Plan: Ein Plan mit mehr als zehn Aufgaben oder mit Produktcode in mehr als einem Stack wird vor dem Plan-Review in gestapelte Pläne geschnitten. Das `plan-structure`-Gate zählt die Aufgaben; es liest die Pläne schon.
- Beim ersten Review-Bundle als Rückhalt: Es warnt ab 300 Produktzeilen und verweigert ab 500. So lässt sich die Plangrenze nicht durch größere Aufgaben umgehen.
- Ausnahme in beiden Fällen: eine begründete `DECISION`-Zeile des Owners im Plan.
- Welche Pfade Produktcode sind, kommt aus den Stacks in `testing.local.json`, ohne deren Testpfade.

**Maßnahme 2: Neuschnitt als Normalfall nach dem zweiten Block**

- Nach dem zweiten blockierten Code-Review einer Arbeit nimmt `attest.py` keine weitere Runde an, solange der Plan nicht `REPLAN … rebuild` trägt oder eine `DECISION` des Owners, die das Weiterreparieren erlaubt.
- `rebuild` heißt: Der offene Rest wird in kleinere Pläne geschnitten, jeder mit eigenem Plan-Review. Heute ist `increment` frei wählbar, und der Owner wird erst nach dem dritten Block gefragt.
- Kein Merge mit Restpunkten als Ausweg: Abschnitt 16 zeigt echte schwere Fehler auch in späten Runden.

**Maßnahme 3: Leichter Weg für kleine Arbeiten, auch bei Tier 3**

- Bedingung: höchstens fünf Aufgaben im Plan, ein Stack, und kein Pfad aus einer Risikokarte, die das Projekt festlegt (Zugriffsschutz, Migrationen, Gate-Code).
- Dann entfallen die Tier-3-Zusätze: eigener Refute-Lauf, zweite Modellfamilie, `analyze` und `converge`. Es bleiben Plan-Review und ein unabhängiges Review.
- Beleg: Tier-3-Arbeiten unter 200 Produktzeilen haben 0,06 Blocks im Mittel (18 Arbeiten). Was diese Zusätze dort verhindern, ist nicht gemessen. Deshalb als Versuch mit festen Kriterien: Blocks, Durchlaufzeit, Korrekturen innerhalb von sieben Tagen, mindestens 20 Arbeiten.
- Das Bundle prüft die Bedingung am Diff nach: Wächst die Arbeit über 200 Produktzeilen oder berührt sie die Risikokarte, gilt wieder der volle Weg.

**In Kenni, ohne Template-Änderung**

- `cross_model_from_tier` steht auf 2; das Template sieht 3 vor. Ob Tier 2 die zweite Modellfamilie braucht, ist eine Entscheidung des Owners in `model-policy.local.json`.

**Offen**

- Die Grenzen (zehn Aufgaben, 300 und 500 Zeilen, fünf Aufgaben für den leichten Weg) stammen aus sechs Wochen eines Projekts. Sie gehören als Projektwerte in die Konfiguration, mit diesen Zahlen als Voreinstellung.
- Jeder Schnitt zahlt den festen Prozess noch einmal. Ob das aufgeht, zeigt der Vergleich der Runden und der Durchlaufzeit vor und nach der Einführung.

## 18. Entscheidungen des Owners vom 2026-11-10

| Entscheidung | Inhalt | Umsetzung |
|---|---|---|
| Einfrieren | Vier Wochen, bis 2026-12-08: keine neuen Regeln, Gates oder Pflichtzeilen im Template. Erlaubt sind Korrekturen, die Arbeit blockieren, und Änderungen, die Aufwand entfernen. | Eintrag in `MAINTAINING.md` durch die Optimierungs-Sitzung; offen |
| Zweite Modellfamilie in Kenni | Zunächst: bei Tier 2 keine Pflicht mehr. Nach der Zählung in Abschnitt 19 vom Owner am selben Tag ersetzt durch die Richtung in Abschnitt 20: GPT als Standardweg und einziger Reviewer. Die Streichung ist zurückgezogen. | Steward ist informiert; nichts geändert |
| Drei Maßnahmen (Abschnitt 17) | Größengrenze mit den Startwerten zehn Aufgaben, 300 und 500 Produktzeilen; Neuschnitt nach dem zweiten Block; leichter Weg für kleine Arbeiten. | Gegenprüfung durch die Optimierungs-Sitzung steht aus; danach Freigabe der Umsetzung |

Die drei Maßnahmen fallen unter die Ausnahme des Einfrierens: 1 und 2 sind neue Grenzen, die Aufwand entfernen sollen; 3 nimmt Pflichten weg. Ob sie während der vier Wochen ausgeliefert werden oder am Ende gebündelt, ist mit der Freigabe zu entscheiden.

## 19. Was die zweite Modellfamilie bei Tier 2 fand

Gezählt aus den `FINDING`-Zeilen der Kenni-Review-Reports von Tier-2-Arbeiten, Feld `by=` (wer den Befund fand). Eigene Familie: Claude-Modelle. Zweite Familie: Codex und DeepSeek.

**Code-Reviews, Tier 2** (722 Befunde, 523 mit `by=`, aus 47 Arbeiten)

| Gefunden von | Blocker | Major | Minor | Nit |
|---|---:|---:|---:|---:|
| eigene Familie | 22 | 6 | 205 | 178 |
| zweite Familie | 12 | 26 | 59 | 15 |

- 38 von 66 schweren Befunden (58 %) stammen von der zweiten Familie. 34 davon tragen `action=fix`.
- Art: je 16 Testlücken und Implementierungsfehler, 3 fehlende Prozessnachweise, 3 sonstige.
- In 28 von 42 Reports mit einem schweren Befund hatte nur die zweite Familie einen.
- Verteilung: Die 38 Befunde liegen in 10 Arbeiten, 26 davon in dreien (#2717, #2702, #2712). In 7 Arbeiten fand nur die zweite Familie etwas Schweres, in 6 nur die eigene, in 3 beide.
- Die betroffenen Arbeiten sind nicht die großen: #2712 hat 177 Produktzeilen, #2718 164, #2723 128.
- Beispiele für Implementierungsfehler: #2718 (`ooxml.py` liest `show=" true "` als falsch und meldet eine sichtbare Folie als versteckt), #2723 (Zustandsfehler nach fehlgeschlagenem Abruf), #2821 (offener Dateideskriptor bei abgebrochenem Wächter).

**Plan-Reviews, Tier 2** (360 Befunde, 267 mit `by=`): 28 schwere Befunde von der zweiten Familie, 42 von der eigenen.

**Kosten**

Von 185 Tier-2-Review-Runden liefen 111 mit zweiter Familie. Blockiert wurden davon 39 %, von den 74 Runden ohne zweite Familie 28 %.

**Einordnung**

- Die zweite Familie ist bei Tier 2 nicht redundant. Sie fand in sechs Wochen in 7 von 47 ausgewerteten Arbeiten schwere Befunde, die die eigene Familie nicht meldete.
- Rund die Hälfte davon sind Testlücken: ein Akzeptanzkriterium ohne Test, der rot werden kann. Die andere Hälfte sind Fehler im Code.
- Grenzen der Zählung: 28 % der Befunde tragen kein `by=`. Wer zuerst liest, bekommt den Befund zugeschrieben; ob die eigene Familie ihn allein auch gefunden hätte, zeigt die Zählung nicht.
- Die Entscheidung des Owners vom 2026-11-10, die Pflicht bei Tier 2 zu streichen, wurde vor dieser Zählung getroffen.

## 20. GPT als einziger Reviewer: was die Journale dazu sagen

Richtung des Owners nach Abschnitt 19: `gpt-6.1-sol` soll Standardweg und einziger Reviewer sein können. Geprüft an den `REVIEW`-Zeilen aus Kenni.

**Dieselbe Runde, von beiden Familien in getrennten Zeilen beurteilt** (91 Runden, alle GPT-Modelle zusammen)

| | GPT blockiert | GPT lässt durch |
|---|---:|---:|
| Claude blockiert | 32 | 5 |
| Claude lässt durch | 31 | 23 |

- Von 68 Runden mit mindestens einem Block hätte GPT allein 63 blockiert (93 %), Claude allein 37 (54 %).
- Als einziger Reviewer verlöre GPT 5 Runden, die nur Claude blockierte. Claude allein verlöre 31.
- Die Auswahl ist nicht neutral: Getrennte Zeilen entstehen eher, wenn die Urteile auseinandergehen.

**Hielten die Blocks, die nur GPT setzte?**

Die 31 Runden „Claude lässt durch, GPT blockiert“ einzeln nachverfolgt: Gab es danach eine weitere Runde, und was änderte sich zwischen den geprüften Ständen?

| Was folgte | Runden |
|---|---:|
| Nächste Runde nach einer Änderung an Code, Tests oder Plan | 14 |
| Keine weitere Runde: Der Pass der eigenen Familie blieb stehen | 11 |
| Weitere Runde auf demselben Stand, ohne Änderung | 3 |
| Nächste Runde, nur Buchhaltung geändert | 1 |
| Stände nicht im Klon lesbar | 2 |

- Von 29 auswertbaren Runden führten 14 (48 %) zu einer echten Änderung, 15 (52 %) nicht.
- Eine Änderung nach dem Block beweist nicht, dass sie dem GPT-Befund galt. Ein stehen gebliebener Pass beweist nicht, dass GPT falsch lag; der Befund kann als Rest oder Folge-Issue angenommen worden sein.
- Die 91 gepaarten Runden stammen überwiegend aus August bis Oktober, mit älteren GPT-Modellen. Für `gpt-6.1-sol` sagen sie wenig.

Folge für den Vorschlag: Als einziger Reviewer hätte GPT niemanden neben sich, der die Hälfte seiner Blocks relativiert. Diese Rolle hat der Prozess schon: Vor einem Block bewertet ein frischer Prozess, der den Befund nicht geschrieben hat, jeden blockierenden Befund; unter Score 80 wird er ein Rest (`verification-independence.md`, „What blocks“). Mit GPT als Reviewer und einem Claude-Modell als Bewerter bliebe eine zweite Familie im Spiel, aber als kurzer Prüfschritt statt als zweites Review.

**Was offen ist**

- Zu `gpt-6.1-sol` selbst gibt es wenig: 8 Code-Review-Zeilen und 26 Plan-Review-Zeilen. Die Zahlen oben stammen überwiegend von `gpt-6-astra` und `gpt-6-sol`.
- Bei Tier 2 trugen 34 von 38 schweren Befunden der zweiten Familie `action=fix`; das passt nicht ganz zu den 48 % oben und betrifft einen späteren Zeitraum.
- Ein strengerer Reviewer bedeutet mehr blockierte Runden. Runden mit zweiter Familie wurden bei Tier 2 zu 39 % blockiert, ohne zu 28 %.
- Bei den Plan-Reviews von Tier 2 fand die eigene Familie mehr schwere Befunde (42 gegen 28).

**Was dafür geändert werden müsste**

- Im Template wenig: Der Voreinstellungswert `own_family_from_tier` ist 4 („nie“), und ein Codex-Review über den Dispatcher schreibt seit v2.73 eine vollständige `REVIEW`-Zeile. Ob `/review` und die Dispatch-Kette den Claude-Reviewer an weiteren Stellen voraussetzen, ist nicht geprüft.
- In Kenni: die Review-Zelle der Modell-Policy, `own_family_from_tier: 3` (heute klärt ab Tier 3 nur ein Pass der eigenen Familie) und Abschnitt 4 von `review.local.md`, der das Claude-Gate vorschreibt.
- Die Regel sollte „Reviewer aus der anderen Familie als der Implementierer“ lauten. Wo Claude baut, ist ein GPT-Review für sich schon familienübergreifend. Wo Codex baut, wäre GPT als Reviewer dieselbe Familie.
- Ein Rückfall auf den Claude-Reviewer, wenn das Codex-CLI nicht verfügbar ist, mit sichtbarem Vermerk.

**Vorschlag**

Als Versuch mit festen Kriterien, zuerst bei Tier 2: GPT als einziger Code-Reviewer für vier Wochen. Gemessen werden Blockquote, Runden je Arbeit, Durchlaufzeit und Korrekturen innerhalb von sieben Tagen, im Vergleich zu den Werten aus den Abschnitten 14 bis 16. Tier 3 folgt, wenn der Vorfall hinter `own_family_from_tier` benannt ist und nicht dagegen spricht.

## 21. Gegenprüfung der drei Maßnahmen und der Reviewer-Frage

Die Optimierungs-Sitzung hat die Abschnitte 14 bis 17 und 20 gegen das Template und Kennis Klon geprüft (zwei Kommentare im PR #407 vom 2026-11-10). Den ersten habe ich erst nach den Entscheidungen in Abschnitt 18 gelesen; die Zustimmung des Owners zu den drei Maßnahmen fiel also ohne diese Einwände. Stichproben habe ich nachgelesen: die Owner-Entscheidung vom 2026-11-02, Kennis Tier-Regel und die Aufgabenformen in Kennis Plänen.

**Was an meinen Zählungen nicht trägt**

- **Die Aufgabenzahl als Anzeiger ist schwächer als dargestellt.** Ich habe Checkbox-Zeilen gezählt und über alle Phasen eines Issues summiert. Von 166 Tier-2+-Plänen in Kenni tragen 61 Checkboxen; Pläne mit anderen Aufgabenformen zählten bei mir als null Aufgaben. Und mehr Phasen bedeuten von selbst mehr Pläne, mehr Reviews und mehr Blocks. Die Korrelation zeigt nicht, dass ein Schnitt hilft.
- **Produktzeilen aus dem gemergten Diff enthalten die Reparaturrunden.** Blocks treiben die Größe auch, nicht nur umgekehrt. Am ersten Review-Bundle ist eine Arbeit kleiner als in meiner Tabelle.
- **Der Sprung bei 300 Zeilen ruht auf 12 und 14 Arbeiten**, unter der Mindestzahl von 20, die das Template für ein Band verlangt.
- **Die 0,06 Blocks kleiner Tier-3-Arbeiten** sind gemessen, nachdem Refute und zweite Familie gelaufen waren. Was diese Zusätze verhindern, zeigt die Zahl nicht.

Der Hauptbefund bleibt: Die Blocks liegen bei wenigen Arbeiten, und Größe und Zahl der Stacks erklären sie besser als das Tier.

**Maßnahme 1 (Größengrenze): so nicht umsetzbar**

- `plan-structure` hat keine Grammatik für Aufgaben und öffnet `tasks.md` nicht. Eine Grenze je Plan braucht zuerst eine einheitliche Aufgabenform; für Kenni ist das eine Migration.
- „Ein Stack“ lässt sich am Plantext nicht entscheiden. Jede Vertragsänderung berührt in Kenni Backend und erzeugte Frontend-Typen.
- Gegen eine harte Verweigerung am Bundle steht die eigene Geschichte: v2.52 machte Verweigerungen nach getaner Arbeit zu Hinweisen, v2.77 strich die Verweigerung beim Execute-Start, und der Owner entschied für v2.80 „ohne neue Gates“.
- Das Bundle misst heute alle Zeilen, nicht Produktzeilen; die Schwellen lassen sich per Umgebungsvariable überschreiben; `attest.py` nimmt auch einen Bereich ohne Bundle an.
- Vorschlag der Optimierungs-Sitzung: erst die Aufgabenform, dann die Grenze je Plan. Am Bundle keine Verweigerung, sondern ein Pflichtnachweis oberhalb der Schwelle (`size-waived:` mit gebundener Owner-Entscheidung), mit einer einzigen Definition von Produktzeilen.

**Maßnahme 2 (Neuschnitt nach dem zweiten Block): richtig, aber an anderer Stelle**

- `attest.py` kennt die Zahl der Blocks, ist aber der falsche Ort: Eine Verweigerung dort wirft das Review der dritten Runde weg, nachdem es gelaufen ist. Der Halt gehört vor das Review, in das Bundle oder an den Dispatch-Start der dritten Runde.
- Die 13 % geschriebener REPLAN-Zeilen sind zum Teil ein Messfehler: Die Auswertung verbindet Arbeit und Runde über die exakte Zeichenkette, und Kenni schreibt REPLAN oft unter dem Slug statt der Issue-Nummer.
- Bestandene Teile gibt es nicht; ein Urteil bindet den ganzen Branch. Ein Neubau heißt neue Branches von main.
- Damit die Regel sich nicht pro forma erfüllen lässt: Ein `rebuild` zählt nur, wenn der Branch danach neue Plandateien mit eigenem Plan-Review trägt.

**Maßnahme 3 (leichter Weg für kleine Tier-3-Arbeiten): nur zum Teil haltbar**

- Refute und zweite Familie wurden wegen der Risikoklasse eingeführt, nicht wegen der Größe. Eine Änderung von 20 Zeilen kann einen zweiten Eigentümer einer Regel schaffen.
- Eine Risikokarte nach Pfaden deckt die Klasse nicht ab: Persistenz außerhalb von Migrationen, Sicherheitsfläche, Verträge über Repositories und Nebenläufigkeit lassen sich an Pfaden nicht erkennen.
- Ein Versuch bräuchte ein Mandat, das Kenni nicht hat, und 20 kleine Tier-3-Arbeiten kommen in 30 Tagen nicht zusammen.
- Haltbar ist: `analyze` und `converge` streichen. Dahinter steht kein Vorfall und keine Durchsetzung.
- Der größere Hebel liegt in Kenni: Die lokale Regel macht aus jedem einzelnen Ja auf eine Folgenfrage Tier 3 (`docs/dev/process-risk-tiers.md:85-87`).

**Konflikt mit zwei Owner-Entscheidungen**

- Am 2026-11-02 entschied der Owner, drei Wochen nur zu messen und keine neuen Pflichten einzuführen (`docs/analysis/2026-11-02-v2.81.md:20`); das läuft bis etwa 2026-11-23.
- Am 2026-11-10 entschied er das Einfrieren bis 2026-12-08.
- Die Maßnahmen 1 und 2 sind neue Pflichten. Meine Lesart in Abschnitt 18, sie fielen unter die Ausnahme, weil sie Aufwand entfernen sollen, teilt die Optimierungs-Sitzung nicht. Sie brauchen eine ausdrückliche Ausnahme des Owners oder warten bis nach dem Einfrieren.

**GPT als einziger Reviewer: die Regel dahinter**

- Hinter `own_family_from_tier` steht kein durchgerutschter Fehler. Es ist eine Owner-Entscheidung vom 2026-10-15 (Kenni #2612: „E1 übernehmen, Claude bleibt Pflicht ab Tier 3“), die einen Widerspruch zweier Regeln schloss.
- Laut Optimierungs-Sitzung nennt #241 eine ältere Zählung aus Kenni (#2617): In 176 Tier-3-Runden, die beide Familien prüften, blockierte in 101 von 103 abweichenden Runden nur Codex. Das habe ich nicht nachgelesen; es stützt Abschnitt 20 mit einer größeren Menge.
- Für einen Versuch bei Tier 2 muss im Template nichts geändert werden. In Kenni steht dem nur Abschnitt 4 von `review.local.md` entgegen, der das Claude-Gate vorschreibt.
- Für Tier 3 genügt später `own_family_from_tier: 4` in Kenni.

**Reihenfolge nach der Gegenprüfung**

1. In Kenni, als Owner-Entscheidungen ohne Template-Release: GPT als einziger Code-Reviewer bei Tier 2 mit einem Claude-Modell als Bewerter der Blocks; die Tier-Regel „ein Ja ergibt Tier 3“ überprüfen; `inert` und `red_ids` setzen; die REPLAN-Zählung berichtigen.
2. Template-Release 1 wie in Abschnitt 12, ergänzt um das Streichen von `analyze` und `converge`. Alles darin entfernt Aufwand oder korrigiert Text.
3. Template-Release 2: der rote Zugpfad (17, dann 16).
4. Maßnahme 2 in der berichtigten Form und Maßnahme 1 mit Aufgabenform und Pflichtnachweis: nach dem Einfrieren, oder früher mit ausdrücklicher Ausnahme des Owners.
5. Maßnahme 3 über `analyze` und `converge` hinaus: zurückgestellt.

## 22. Kennis Backend-Suite in der Cloud (Probelauf vom 2026-11-10)

Anlass: Der Owner prüft, die Testlast vom Server in die Cloud zu verlegen und die Suite selbst zu hinterfragen. Die Backend-Suite lief in einer Cloud-Sitzung auf einem frischen Klon (Stand `f0f03360ef`), `pytest tests/ -n 4 -m 'not network'`, ohne Coverage-Messung. Die Frontend-Stufe ist nicht gelaufen.

**Ergebnis**

| Lauf | Testfälle | rot | Dauer |
|---|---:|---:|---|
| Erster Lauf, Umgebung unverändert | 23.065 | 455 (2,0 %) | 44 min; die ersten 95 % in 19 min |
| Nachlauf der roten Dateien mit installiertem `bubblewrap` | 1.757 | 97 | 4 min |

- Rund 250 der 455 roten Tests meldeten „bwrap is not installed“. Nach `apt-get install bubblewrap` arbeitet die Sandbox im Cloud-Container, auch mit `--unshare-all`.
- Die 44 Minuten des ersten Laufs entstanden, weil Sandbox-Tests je 120 s auf ein fehlendes Werkzeug warteten; ein Test wurde vom Watchdog nach 300 s beendet.
- Von den verbleibenden 97 (0,4 % aller Testfälle) brauchen rund 58 das Dokument-Toolset (LibreOffice, pandoc, poppler). Dafür gibt es `scripts/bootstrap_document_toolset.py`; `docs/dev/claude-agent-document-toolset.md` nennt ein in der Cloud bereits geprüftes Image.
- Rund 35 betreffen Operator- und Zertifizierungstests. Dieselbe Doku nennt dafür zwei Grenzen der Cloud: Eine Kernel-Schnittstelle fehlt, und das mitgelieferte Claude-CLI hat dort kein angemeldetes Konto. Diese Tests bleiben auf dem Server.
- Einzelne Tests prüfen Lanes und Verzeichnisse des Hosts.

**Wohin die Zeit geht** (22.610 grüne Tests, zusammen 3.301 s Testzeit)

- Median je Test 18 ms; 21 Tests über 10 s, 388 über 1 s.
- Die 100 langsamsten Tests machen 22 % der Zeit aus, die 1.000 langsamsten 48 %. Die Zeit ist breit verteilt.
- Größte Bereiche: `services/documents` 16 %, `api/v1` 13 %, `services/claude_agent` 6 %, `services/learning` 5 %. `tests/scripts` zusammen 8 %.
- Ein Dutzend WebSocket-Tests braucht je 14,1 bis 14,2 s; das deutet auf eine feste Wartezeit.

**Was die Suite prüft** (Mustersuche in den Testdateien, Größenordnung)

- 58 % der Testfunktionen liegen in Dateien, die die Feature-Registry als Beleg nennt.
- Außerhalb davon: rund 890 Tests für Prozess-Skripte, rund 610 Text-Pins auf Doku und Pläne, rund 2.580 Tests in Dateien, die Quelltext durchsuchen statt ihn auszuführen. Die Gruppen überschneiden sich.

**Frontend-Stufe und Browser-Tests (Nachtrag)**

| Lauf | Ergebnis | Dauer |
|---|---|---|
| `npm ci` | 837 Pakete | 15 s |
| Frontend-Unit, Client (`vitest run`) | 7.556 Tests in 489 Dateien, alle grün | 268 s |
| Frontend-Unit, Server | 34 Tests, alle grün | 1 s |
| E2E-Backend starten (`make e2e-backend E2E_LANE=a`) | erreichbar | 15 s |
| Zwei Playwright-Specs, Projekt `desktop-1440` | 10 von 10 grün | 18 s |

- Die Frontend-Stufe der Merge-Suite läuft in der Cloud ohne jede Anpassung.
- Für Playwright sind zwei Dinge nötig. `E2E_LANE=a` muss in der Umgebung stehen; ohne die Variable bricht `make e2e-backend` an `scripts/e2e_lane.sh` ab. Und das Projekt nutzt Playwright 1.61, der vorinstallierte Chromium gehört zu einer anderen Version; der Probelauf lief über eine temporäre Konfiguration mit dem vorinstallierten Browser als `executablePath`. Für einen Dauerbetrieb gehört der passende Browser ins Setup-Skript.
- Gelaufen sind zwei von 166 Specs in einem von drei Projekten. Die ganze E2E-Suite ist nicht gemessen.

**Aufteilung in vier Teile (Nachtrag)**

Die Backend-Tests wurden nach gemessener Testzeit in vier überschneidungsfreie Teile geschnitten (`2026-11-10-kenni-suite/shard1.txt` bis `shard4.txt`) und nacheinander einzeln gefahren, jeder allein auf einer Maschine mit vier Prozessen, ohne Coverage:

| Teil | Dauer | Ergebnis |
|---|---:|---|
| 1 | 300 s | grün |
| 2 | 283 s | rot, bekannte Fälle |
| 3 | 303 s | rot, bekannte Fälle |
| 4 | 272 s | rot, bekannte Fälle |

- Die roten Fälle sind die aus dem Nachlauf bekannten: Dokument-Toolset, Operator- und Lane-Tests.
- Auf vier Maschinen parallel dauert der volle Backend-Lauf damit rund 5 Minuten zuzüglich Aufbau eines frischen Workers. Die Aufbauzeit und die Rückmeldung eines Workers sind nicht gemessen; der Start eigener Worker aus der Audit-Sitzung wurde von einer Sicherheitsprüfung angehalten.

**Folgerungen**

- Die Backend-Suite lässt sich in der Cloud fahren. Im Setup-Skript fehlen `bubblewrap` und das Dokument-Toolset; ein kleiner, benennbarer Rest braucht den Server.
- Bei breiter Zeitverteilung bringt es wenig, einzelne langsame Tests zu beschleunigen. Wirksam sind zwei Dinge: steuern, welche Tests bei welcher Änderung laufen, und die Suite auf mehrere Maschinen verteilen. Bei vier Maschinen wären aus 19 Minuten rechnerisch rund 5; gemessen ist das nicht.
- Ob Tests redundant sind, zeigt erst ein Lauf mit Coverage je Test.

## 23. Welche Tests eine Änderung wirklich berührt

Die Backend-Suite lief ein drittes Mal, jetzt mit Coverage je Test (`--cov-context=test`) und installierter Sandbox: 23,5 Minuten auf vier Prozessen in der Cloud. Die Auswertung verbindet jede Produktdatei mit den Tests, die mindestens eine ihrer Zeilen ausführen.

**Einzigartige Abdeckung**

- 23.001 Tests führen Produktcode aus und decken zusammen 70.178 Zeilen ab.
- 89 % dieser Tests decken keine Zeile ab, die nicht auch ein anderer Test abdeckt.
- Das ist kein Maß für Überflüssigkeit. Parametrisierte Fälle teilen sich ihre Zeilen von selbst, und zwei Tests können dieselbe Zeile mit verschiedenen Erwartungen prüfen. Für eine Streichliste taugt die Zahl nicht.
- 964 Tests führen gar keinen Produktcode aus (108 s); sie prüfen Skripte, Texte oder Konfiguration.

**Betroffene Tests je Änderung**

- Eine Produktdatei wird im Median von 0,5 % der Tests berührt, 454 von 519 Dateien von weniger als 5 %. Zehn Dateien berührt mehr als die Hälfte aller Tests, weil sie beim Start jedes Tests geladen werden (`core/db.py`, Registries).
- Durchgespielt an den 314 Train-Merges seit Ende September: 72 änderten weder Backend-Code noch Backend-Tests. Bei den übrigen 242 machen die Tests, die eine der geänderten Dateien ausführen, im Median 2 % der Suite-Zeit aus, im Mittel 17 %.
- 73 % dieser Merges brauchten weniger als ein Viertel der Suite-Zeit, 88 % weniger als die Hälfte, 4 % fast alles.

**Grenzen der Rechnung**

- Die Zuordnung stammt vom heutigen Stand. 113 geänderte Dateien gibt es heute nicht mehr oder gab es damals noch nicht; für sie fehlt die Zuordnung, das unterschätzt den Anteil.
- 72 Merges änderten auch Backend-Konfiguration oder Lockfiles und bräuchten den vollen Lauf.
- Coverage sieht nur ausgeführte Python-Zeilen. Abhängigkeiten über Datendateien, Prompts, Vorlagen oder das Datenbankschema erfasst sie nicht.
- Eine Zeile, die beim Import läuft, zählt als berührt, auch wenn der Test sie nicht prüft.

**Folgerung**

Die Frage „sind alle Tests nötig“ hat zwei Antworten. Streichen lässt sich aus den Daten nicht begründen. Auswählen schon: Bei den meisten Merges läuft die ganze Suite, obwohl nur ein kleiner Teil der Tests den geänderten Code überhaupt ausführt. Kenni wählt beim Push bereits nach Pfaden aus (`testing.local.json`) und führt für die Frontend-Stufe eine Leser-Karte; beim Merge läuft das Backend ganz. Eine Auswahl nach gemessener Abdeckung beim Merge, mit dem vollen Lauf als Rückhalt (nachts auf main und vor jedem Deploy), würde die Merge-Suite für die Mehrzahl der Züge auf Minuten bringen. Sie setzt voraus, dass die Zuordnung regelmäßig neu gemessen wird und dass jede Änderung an den zehn Kern-Dateien, an Konfiguration und an Datendateien den vollen Lauf auslöst.

## 24. Teststruktur für Kenni: Klassen, Regeln, erwartete Wirkung

Entscheidung des Owners vom 2026-11-10: zuerst die Tests strukturieren; ob ein Schattenbetrieb folgt, ist offen. Grundlage ist der Coverage-Lauf aus Abschnitt 23, jetzt auf der Ebene ganzer Testdateien ausgewertet, weil eine Auswahl in der Praxis Dateien startet.

**Die Klassen**

| Klasse | Umfang | Auslöser |
|---|---|---|
| Produkt-Tests mit eigener Abdeckung | 1.199 Testdateien, 85 % der Testzeit | eine Quelldatei geändert, die die Datei ausführt (Karte Quelldatei → Testdateien) |
| Pfadgebundene Tests | 235 Testdateien, 15 % der Testzeit (744 s) | ihr Gegenstand geändert |
| Kern-Dateien | 11 Quelldateien, die mehr als die Hälfte aller Testdateien beim Start lädt | Änderung erzwingt den vollen Lauf |
| Voller Lauf | alles | siehe Regeln |

- Pfadgebundene Tests führen außer den Kern-Dateien keinen Produktcode aus. Ihre Gegenstände sind laut Textsuche in den Testdateien vor allem `scripts/process` (110 Nennungen), `docs/process` (74), Pläne unter `.process-work/plans` (54), das `Makefile` (49), `docs/design` (39) und `frontend-react/src` (30).
- Bei 134 der 235 Dateien nennt die Testdatei ihren Gegenstand als Pfad; 101 brauchen eine Zuordnung von Hand.
- Die elf Kern-Dateien: `core/db.py`, `core/logging.py`, `api/v1/idempotency.py`, `api/v1/documents/_deps.py`, `services/tools/registry.py`, `services/push/push_service.py`, `services/claude_agent/late_calls.py`, `services/document_index/build_tasks.py`, `services/learning/task_registry.py`, `services/research/task_registry.py`, `services/ws/session_cleanup_tasks.py`.

**Die Regeln, wie durchgespielt**

1. Geänderte Quelldatei: ihre Testdateien aus der Karte.
2. Geänderte oder neue Testdatei: läuft selbst.
3. Pfadgebundene Testdatei: läuft, wenn einer ihrer Gegenstände geändert wurde.
4. Voller Lauf bei: Kern-Datei, Migration, Abhängigkeiten oder Testkonfiguration (`pyproject.toml`, `uv.lock`, `alembic.ini`), Test-Helfer und Fixtures, Nicht-Python-Datei unter `backend/src`, Quelldatei, die die Karte nicht kennt.
5. Die Auswahl gilt für die Vereinigung aller Änderungen eines Zugs.

**Wirkung an den 314 Train-Merges seit Ende September**

| Ergebnis | Merges | Anteil |
|---|---:|---:|
| Auswahl genügt | 220 | 70 % |
| Voller Lauf erzwungen | 94 | 29 % |

- Bei den 220 Merges mit Auswahl: Median 3 % der Suite-Zeit, drittes Viertel 7 %, neuntes Zehntel 25 %.
- Gründe für den vollen Lauf: Test-Helfer oder Fixture 36, Nicht-Python-Datei 20, Kern-Datei 12, Migration 10, Abhängigkeiten 8, unbekannte Quelldatei 8.
- Über alle Merges gemittelt läuft 36 % der Suite-Zeit.
- Jeder Merge startet einige pfadgebundene Tests, weil jeder Merge Pläne und Journale ändert, die diese Tests nennen.

**Grenzen**

- Die Rechnung ist je Merge gemacht, nicht je Zug; ein Zug mit mehreren Branches wählt mehr aus.
- Die Karte stammt vom heutigen Stand und ist auf ältere Merges angewandt.
- Der größte Posten bei den erzwungenen vollen Läufen sind Test-Helfer. Mit einer Zuordnung Helfer → Testdateien, die sie importieren, ließe er sich verkleinern; das ist nicht gerechnet.
- Was Coverage nicht sieht, deckt Regel 4 nur für Dateien unter `backend/src` und `backend/alembic` ab.

**Womit sich anfangen lässt, ohne die Merge-Grenze zu ändern**

Die Struktur ist schon dort nutzbar, wo das Template eine Auswahl heute erlaubt: beim Push eines Branches und in der inneren Schleife. Kenni wählt dort nach einer Pfadkarte von Hand (`testing.local.json`, `map` und `pins`). Drei Schritte, alle in Kenni:

1. Die Karte Quelldatei → Testdateien regelmäßig aus einem vollen Lauf mit Coverage je Test erzeugen und als Datei ablegen.
2. Die 235 pfadgebundenen Testdateien ihren Gegenständen zuordnen: 134 aus der Textsuche als Vorschlag, 101 von Hand. Das Template hat dafür `pins`.
3. Die Auswahl beim Branch-Push auf die gemessene Karte umstellen (`select`-Befehl des Stacks). Korrektur nach dem Plan des Stewards (#2954): In den Fällen der Regel 4 fährt der Push nicht die ganze Suite. Kenni überlässt das heute dem Zug (ADR-0086, #2289), und dabei bleibt es, solange jeder Merge voll läuft; ein voller Lauf am Push würde die Lane rund 20 Minuten belegen.

Der Merge fährt dabei unverändert die ganze Suite. Ob und wie die Auswahl später auch dort gilt, ist eine eigene Entscheidung.

## Anhang: Befunde außerhalb des Fokus

Nicht Gegenstand der Empfehlung, aber gesehen:
- `optimize.active()` hat im Template keinen Aufrufer; seit Einführung der Optimierungsschleife (v2.67/v2.68) nennt der CHANGELOG keine Prüfung, die aufgrund von Messwerten entfernt oder abgeschwächt wurde. Ob Projekte eigene Records haben, ist hier nicht sichtbar.
- `process_context.py --cost` führt die Prozess-Dokumente nur als Summe „available“; die Kosten je Phase weist es nicht aus (`process_context.py:255-281`).
