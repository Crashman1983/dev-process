# Changelog — dev-process

Was sich je Release geändert hat, warum und wozu es führt — neueste Version oben.
Jeder Eintrag hat dieselben Teile: **Warum** (das beobachtete Problem), **Was sich
ändert** (aus Sicht eines Projekts, das die Vorlage nutzt), **Wirkung**, **Update**
(Schritte für bestehende Projekte) und **Details** (der Plan mit den technischen
Einzelheiten, die Issues); ein kleines Fix-Release kann die Wirkung weglassen, und
ein Eintrag ohne Plan oder Issue hat keine Details-Zeile. In wenigen Sätzen je Version: [NEWS-DE.md](NEWS-DE.md).
English version: [CHANGELOG.md](CHANGELOG.md). Die Releases vor v2.28.2:
[docs/changelog-archive-DE.md](docs/changelog-archive-DE.md).

## v2.78.1 — Ein Pass stützt sich nur auf Belege, die ins Repository gelangen · 2026-10-25

**Warum.** `attest` las ROOT-CAUSE- und Skip-Zeilen aus jedem Journal-Shard im Arbeitsbaum, auch aus uncommitteten, während sein Commit nur den heutigen Shard und explizite `--with`-Pfade trug. Ein Beleg im uncommitteten Shard eines anderen Tages konnte so einen committeten Pass autorisieren, ohne je im Repository zu landen. Daneben akzeptierte `plan-structure` eine `## Transitions`-Tabelle, deren Trennzeile weniger Spalten nannte als der Kopf.

**Was sich ändert.**
- Der Owner der Belege zählt eine Journal-Zeile nur, wenn sie am geprüften Head committet ist oder in einer Datei liegt, die dieselbe Attestierung committet (heutiger Shard, `--with`). Nur die gezählten Belege dieser Arbeit — ihre ROOT-CAUSE und die Skip-Arten, die das Journal tragen darf — können einen Pass verweigern; fremde Arbeit und Arten, die nur aus dem Plan zählen, bleiben unsichtbar. Eine solche Zeile nur in einem anderen uncommitteten Shard wird mit Datei und Zeile verweigert, nie still gezählt.
- Belege im heutigen Shard landen wie bisher mit der REVIEW-Zeile im Commit; neben dem Beleg-Owner steht keine zweite Liste.
- `attest` liest jeden Record einmal und committet genau die geprüften Bytes — jeden Pfad einmal. Ein scheiterndes Index- oder Ref-Update endet mit Exit ≠ 0 und verliert nichts.
- Eine blockierende REVIEW-Zeile der Arbeit, die weder committet ist noch mit der Attestierung reist, wird mit Namen verweigert statt gezählt.
- Ein Record, der anders gestagt ist als im Arbeitsbaum und an HEAD, wird verweigert statt überschrieben; das fremde Staging bleibt.
- Während des Schreibens hält `attest` selbst die `index.lock` des Index; ein paralleles `git add` scheitert daran, statt überschrieben zu werden. Der heutige Shard wird über einen auf Identität und Inhalt geprüften Deskriptor angehängt. Ein Split-Index wird verweigert.
- Der Attest-Commit ruft wie bisher die Hooks von `git commit` (pre-commit, prepare-commit-msg, commit-msg) auf dem Index des Commits selbst; ein verweigernder Hook beendet den Commit, die Zeile bleibt geschrieben und gestagt. Ein Hook, der weitere Dateien in diesen Commit stagt, wird verweigert statt übernommen, und `post-commit` läuft dafür nicht.
- Ein Symlink oder Submodul, das als Record oder als Verzeichnis, unter dem Records liegen, committet ist, wird verweigert statt als leere Heimat gelesen.
- `attest --archive` verschiebt den Plan nicht mehr: Es verweigert, bevor es etwas liest, und nennt den Weg zum Archiv. Jede Art, eine Datei nach der Prüfung zu verschieben, konnte Bytes eines anderen Prozesses verlieren; das Gate erkennt einen Plan, den ein späterer `git mv`-Commit archiviert, an seinem Inhalt, wie nach `/finish`.
- `plan-structure` vergleicht die Zellenzahl von Kopf- und Trennzeile einer Tabelle (GFM) und meldet eine Abweichung als Befund.

**Update.** Keine Schritte für die Befehle der Vorlage. Ein Skript oder eine Gewohnheit, die `attest … --archive <plan>` aufruft, lässt die Option weg: erst attestieren (mit `--with <plan>`, wenn dem Plan Records angehängt sind), danach `git mv <plan> <Archivpfad> && git commit` — die Verweigerung nennt den Pfad.

**Geänderte Abschnitte.** `verification-independence.md` (Bind the verdict to the reviewed range)

Details: [Plan](docs/analysis/2026-10-24-v2.77.3.md) #308

## v2.78.0 — Ein Befund nennt seinen Ort; Blocks auf altem Code werden gezählt · 2026-10-24

**Warum.** Das Claude-Code-Team fand per git blame: 59 % des wiederholt markierten Codes lag schon seit Runde 1 vor (#311). Dieselbe Zahl wollten wir für unsere Review-Runden und konnten sie nicht erheben: In Kennis 571 Review-Berichten nannten nur 24 % der FINDING-Zeilen überhaupt eine Stelle `Datei:Zeile`, frei im Titel, und von 37 Blockern ab Runde 2 waren zwei messbar.

**Was sich ändert.**
- Eine FINDING-Zeile hat ein Ortsfeld, `at=<path>:<line>`, `<path>:<first>-<last>`, `<path>` oder `-` (kein einzelner Ort). Das Bericht-Gate des Moduls github-issues verlangt es bei jedem Blocker und Major, den ein Branch hinzufügt, wie `class=`; Befunde, die am Gabelpunkt standen, bleiben gültig, und wer einen alten Befund klassifiziert oder verortet, macht ihn nicht neu. Das Review-Bundle und das Codex-Ergebnisschema fragen danach; ein Codex-Lauf von vor dem Update wird mit `at=-` übergeben.
- `process_kpis.py rounds` und `baseline` zeigen Blocks auf altem Code (#311): die `sev=blocker`-Befunde von Code-Reviews ab Runde 2, deren Zeilen so stehen wie an einem Stand von Runde 1, als Anteil an den gemessenen, je Runde und je Arbeit, und was nicht messbar war, nach Grund. Verglichen wird der Inhalt der Bäume; ein Rebase zwischen den Runden ändert nichts, solange der Stand von Runde 1 existiert.

**Wirkung.** Ab dem ersten Review nach dem Update zeigt das Cockpit, wie viele späte Blocks auf Code liegen, den Runde 1 schon gesehen hat — das Maß für #310 (feste Befund-Kennungen, als Nächstes) und für jede Änderung an den Review-Runden.

**Update.**
1. Neue Blocker- und Major-Befunde eines Branches tragen `at=`; projekteigene Review-Prompts (Briefs für andere Reviewer) nehmen es in ihre FINDING-Vorgabe auf.
2. Berichte auf main bleiben gültig.

**Geänderte Abschnitte.** `verification-independence.md` (The review bundle — the portable interface to any reviewer), Modul `github-issues` (Review and audit visibility), Modul `telemetry` (The KPI cockpit), Befehl `/review`

Details: [Plan](docs/analysis/2026-10-24-v2.78.md) #311

## v2.77.2 — Ein pytest-Parameter mit Klammern behält die ganze ID · 2026-10-23

**Warum.** `red_evidence` schnitt den Parameteranhang einer pytest-ID am letzten `[` ab. Eine gültige ID wie `test_x[a[b]]` wurde als `test_x[a` gelesen, während `attest_evidence` `test_x` liest; ein gültiger Rot→Grün-Nachweis wurde auf dem pytest- und dem JUnit-Pfad verweigert.

**Was sich ändert.**
- `attest_evidence` besitzt die Testnamen-Normalisierung als öffentliche Funktion `attest_name`; `red_evidence` ruft sie auf beiden Pfaden und hat keine eigene `[`-Regel mehr.
- Ein Parameterwert darf Klammern, `]`, Kommas, Unicode oder leer sein; die Identität ist die Funktion, die attest auflöst.
- Die geschriebene Referenzform bleibt unverändert.

**Update.** Keine Schritte.

Details: [Plan](docs/analysis/2026-10-23-v2.77.2.md) #306

## v2.77.1 — Fixes aus der v2.77.0-Übernahme · 2026-10-23

**Warum.** v2.77.0 konnte einen Fix als belegt melden, obwohl kein einzelner Test von Rot auf Grün ging: Zwei JUnit-Fälle mit gleicher Datei und gleichem Namen, aber verschiedenen Klassen wurden zu einem verschmolzen, sodass ein rot-dann-übersprungener Fall neben einem immer grünen grün aussah. Daneben stürzte `process_kpis.py findings` an jeder FINDING-Zeile ab, das Review-Bundle nannte für eine zweite Linse auf einem blockierten Kopf die nächste Runde, und der Docstring des Plan-Gates beschrieb eine lockerere Transitions-Überschrift als das Gate erzwingt.

**Was sich ändert.**
- `red_evidence` hält JUnit-Fälle nach Datei, Klasse und Name getrennt und verweigert eine geschriebene Testreferenz, die das Gate wie einen anderen Fall des Laufs liest, oder — mit `--sites` — nicht als diesen Test; verschachtelte Python-Klassen behalten die ganze Kette. Die Referenzform für andere Sprachen bleibt unverändert.
- `process_kpis.py findings` endet mit Exit 0 und zählt verschiedene Arbeiten; das Bundle nennt die blockierte Runde, die `--round` bei attest annimmt; der Docstring nennt die Transitions-Regel ab Ebene 2.
- Die Regel der Linsen-Runde liegt jetzt in `attest.py`; Bundle und Codex-Übergabe teilen sie.

**Update.** Keine Schritte.

Details: [Plan](docs/analysis/2026-10-23-v2.77.1.md) #303

## v2.77.0 — Pläne entscheiden den Zustandsraum, Fix-Runden schließen die Klasse · 2026-10-22

**Warum.** In Kennis Review-Historie (510 Issues, 808 Runden) waren in den längsten Arbeiten 39 % der blockierenden Befunde Plan-Lücken und 35 % kamen aus dem Fix der Vorrunde; Review-Rauschen gab es keines. Fix-induzierte Fehler wuchsen mit der Größe des Fix-Durchgangs (6–9 Befunde: 46 % der Folgerunden blockierten erneut, ab 10: 86 %), und ein roter Test vorab senkte sie nicht (41 % gegen 40 %). Regel 4, „Inkrement oder Neubau“ ab dem zweiten Block, war Prosa; attest las ROOT-CAUSE nur im Plan, obwohl `red_evidence` es ins Journal schreibt; und eine Pflicht-Tatsache, die Git nicht bestimmen konnte, fiel bei allen außer zwei Tatsachen still weg.

**Was sich ändert.**
- Zwei Pflichtnachweise (#293, #297): Ab der zweiten blockierten Code-Runde einer Arbeit schuldet jeder weitere Block `REPLAN work=<id> round=<r>: increment|rebuild — <warum>` im Plan; jede blockierte Runde schuldet einen Klassentest — `ROOT-CAUSE … — sites: <Geschwisterstellen> — <pfad>::<test>` mit einem Test, der am Kopf steht (`red_evidence.py --sites` schreibt die Form), oder `sites: none — <Grund>` für eine Runde ohne Codefehler. Es zählen nur Runden und Records, die der Branch hinzufügt, inhaltlich gegen seinen Gabelpunkt verglichen; Ausweg ist ein begründetes `skipped replan|class-test`.
- attest verweigert jeden Pass, den eine nicht bestimmbare Tatsache offen ließe, und liest ROOT-CAUSE-Zeilen und die neuen Skips auch im Journal.
- `plan-structure` prüft die `## Transitions`-Tabelle eines Plans (auch in einem neuen Spec-Kit-Plan): Spalte `Test`, mindestens eine Zeile, jede Zelle gefüllt, und sobald Tests fällig sind je Zeile `<pfad>::<test>` oder `struck — <Grund>`.
- Das Report-Gate des github-issues-Moduls verlangt `class=` an jedem Blocker und Major, den ein Branch hinzufügt.
- Das Plan-Review bekommt den Schritt STATE SPACE und eine Kalibrierung (eine offene Fehlerklasse ist mindestens `major`); Execute bekommt „Fixing a review round“ (Geschwisterstellen, Differentialtest, Durchgänge über etwa 300 Zeilen oder sechs Befunde in Schritten, zuerst REPLAN); eine gemessene Alt/Neu-Differenz zählt als Score 100; der Fehlerkatalog bekommt „Decision after an await on a stale snapshot“; das Delta-Bundle warnt bei einem großen Fix-Durchgang.
- Berichte tragen `round:`; `process_kpis.py baseline` zählt Blocker nach Herkunft, Runden mit und ohne Plan-Review, zu fixende Befunde gegen fix-induzierte Blocker der Folgerunde und Skips je Art.

**Wirkung.** Ein zweiter Block lässt sich nicht mehr ohne die Neubau-Frage überflicken, ein Fix nennt die Klasse, die er schließt, und die Stellen, die er geprüft hat, und die Grundlinie zeigt, ob fix-induzierte Blocker und Fix-Runden sinken.

**Update.**
1. Laufende Arbeiten: Ein Pass nach zwei oder mehr blockierten Runden, die der Branch hinzugefügt hat, schuldet die REPLAN-Zeilen und die Klassentest-Ursachen — oder `skipped replan|class-test work=<id>: blocked before v2.77`; eigene neue Blocker- oder Major-Befunde ohne `class=` bekommen eines; ein laufender Plan mit `## Transitions` bekommt die Spalte `Test`.
2. Berichte auf main und schon gemergte Pläne bleiben gültig.

**Geänderte Abschnitte.** `design-template.md` (Sections), `failure-catalog.md` (Facts and state), `improvement-monthly.md` (What you review, What you produce), `journal-state-plans.md` (Review attestations), `mandatory-rules.md`, `refute.md` (Refuting a plan), `review-checklist.md` (Decisions — recorded, not embodied silently), `tower.md` (Dispatch and the model policy), `verification-independence.md` (The review bundle — the portable interface to any reviewer, Bind the verdict to the reviewed range, Enforcement), `workflow.md` (Execute, Review), Modul `github-issues` (Review and audit visibility), Modul `telemetry` (The KPI cockpit), Befehle `/execute`, `/plan`, `/review`

Details: [Plan](docs/analysis/2026-10-21-v2.77.md) #293 #297

## v2.76.1 — Ein dispatchter Codex-Bericht ist lesbar; das Kriterium eines anderen Issues ist keine Pflicht · 2026-10-21

**Warum.** Zwei Template-Fehler sind in Kenni angekommen. Der Codex-Dispatch schrieb den Titel des Berichts über den Header-Block. Der Header ist der Block bis zur ersten Leerzeile, also las das Report-Gate des github-issues-Moduls kein `review:` und lehnte den Push ab: zweimal an einem Tag (Kenni #2683, #2691), jedes Mal von Hand behoben. Auch `check_review.report_header` las aus so einem Bericht kein `work:`. Und attest zählte jede `AC-<id>` eines Plans als Kriterium der Arbeit, auch eine, die der Plan nur aus einem anderen Issue zitiert („bis zur AC-11-Messung (#2659)“). Dann verweigerte attest einen Pass für einen Test, den dieses Kriterium nie schuldete. Ein dritter kam aus Kenni #2338: Der Codex-Handoff attestierte die Issue-Nummer, und ein Issue mit mehreren Plänen ließ attest sie ablehnen, ohne Weg, den Plan zu nennen.

**Was sich ändert.**
- Der Codex-Dispatch schreibt zuerst den Header-Block, danach den Titel (#286).
- Ein Plan zitiert das Kriterium eines anderen Issues qualifiziert, `#2659/AC-11`: attest verlangt es nicht und nennt es in einem Hinweis (#287). Eine nackte `AC-<id>` bleibt ein eigenes Kriterium — Prosa unterscheidet kein Zitat von einem eigenen Kriterium mit Herkunftsangabe —, und ihre Ablehnung nennt jetzt die qualifizierte Form als Ausweg.
- Ein dispatchtes Codex-Review hält seine Arbeit fest: die Issue-Nummer, oder — wenn sie am geprüften Head mehrere Pläne benennt — den Slug des Plans, den es prüft. Der Handoff attestiert damit, und der Fallback-Hinweis nennt sie (#290).
- `verification-independence.md`: Ein lesender Reviewer über opencode braucht auch gesperrte Umleitungen, Pipes und Verkettungen — ein erlaubtes `git show*` ließ ein Review `git show … > <Datei>` schreiben.

**Update.** Ein Plan, der das Kriterium eines anderen Issues nennt, schreibt es `#<issue>/AC-<id>`; eine nackte ID bleibt Pflicht, und attest sagt das. Ein dispatchter Codex-Bericht von vor dem Update hat den Titel noch oben: Lehnt das Gate ihn ab, den Titel unter den Header-Block verschieben.

**Geänderte Abschnitte.** `journal-state-plans.md` (Plans), `verification-independence.md` (The review bundle — the portable interface to any reviewer)

Details: #286 #287 #290

## v2.76.0 — Deterministische Prüfungen vor dem Review, und das Maß ihrer Wirkung · 2026-10-21

**Warum.** Kennis Review-Historie (315 Berichte, 1.694 Befunde, dev-process #277 Schritt 0) zeigte: Von den 423 blockierenden oder schweren Befunden brauchten nur 85 das Urteil eines Lesers; den Rest hätte eine Regel oder ein Test gefangen. Sieben von zwanzig Befunden, bei denen eine Prüfung nie wirkte, waren Regeln, die nur eine Warnung druckten, sieben weitere standen nur als Prosa da. Ein Template-Update konnte sein eigenes Review nicht freigeben, ein Zug mit einem Update wurde abgelehnt, und ein Testlauf unter `MAKEFLAGS=-n` passierte den Push-Hook.

**Was sich ändert.**
- Pflichtnachweise (#282): Eine Tabelle, `review_evidence.required_records` in `model-policy.json`, sagt, was eine Arbeit schuldet — einen REFUTE für Gate-Code und ab Tier 3, eine ROOT-CAUSE-Zeile nach drei Fix-Commits auf einer Datei, das Wort des Owners (`DECISION <Datum> owner:`) hinter einer `review-waived:`-Zeile, wo immer der Plan liegt (aktiv, Archiv, Spec Kit), und schon bei `/finish`. attest verweigert ohne den Nachweis oder ein begründetes `skipped <kind> work=<id>: <Grund>` (das Wort des Owners lässt sich nicht überspringen); ein Projekt ergänzt Zeilen unter `required_records_extra`. Das Bundle liest seine Refute-Warnung aus derselben Tabelle.
- Neues Core-Gate `plan-structure` (#278): In einem Tier-2+-Plan, den der Branch neu anlegt — aktiv oder schon archiviert, oder hier von Tier 1 hochgestuft —, hat jedes `AC-<id>:`-Kriterium genau ein `shall`, eine nur einmal vergebene ID und — sobald eine Aufgabe abgehakt ist und beim Merge-Push — seinen geplanten Test (`AC-<id>: <pfad>::<test>` oder `struck — <Grund>`, die Grammatik, die attest annimmt); beim Merge-Push bleibt keine Aufgabe `- [ ]` ohne `struck:` oder `moved: #N`. Projektabschnitte, weitere `shall`-Wörter und eine Story-Registry kommen aus `plan-structure.local.json`, gelesen an der Integrations-Ref.
- Die Review-Checkliste lässt sich auf den Diff zuschneiden (#281): `review-sections.local.json` ordnet Abschnitte Pfadklassen zu; das Bundle lässt Abschnitte weg, die keine berührte Klasse erreicht, nennt sie und behält alle, wenn ein Pfad in keine Klasse fällt.
- FINDING-Zeilen tragen `class=mechanical|testable|judgment` und `rule=<Prüfung>` (#276); `process_kpis.py findings` zählt sie und nennt eine Prüfung, die sich über Arbeiten wiederholt. Der Codex-Reviewer schreibt beides.
- `process_kpis.py baseline` (#277): je gemergter Arbeit in einem oder zwei Datumsfenstern die Mediane von Tokens, Review- und Fix-Runden, Befunden und Durchlaufzeit, die je Phase angegebenen Tokens, durchgerutschte Arbeiten und der Change-Failure-Proxy. `testing.md` bekommt „Classes, not cases“; das github-issues-Modul liefert eine Vorlage für Prüfungsänderungen mit „Replaces“ und „Measure“.
- Dispatch (#270): `start` und `queue add` nehmen `--class`, die Klasse wandert durch die Kette; `report.py` kennt den Zustand `failed` (Absturz, Timeout — der Tower listet ihn hoch) und `--usage input=…,cached=…,output=…[,cost_usd=…]`, das `models` zeigt; ein `status_file` in der Policy-Zelle ist ein Lebenszeichen. `deepseek-` ist eine eigene Modellfamilie.
- `verification-independence.md` ergänzt einen Reviewer über opencode (ein OpenAI-kompatibles Modell wie DeepSeek): das Modell mit `reasoning` und `tool_call` deklariert, Lesezugriff aufs Repo und ein Brief mit `verified=` und einem Scope je Lens — gemessen am Cross-Model-Review dieses Releases hielten mit Lesezugriff neun von zehn Befunden, allein aus dem Diff einer von sechs.
- Fixes: Der eigene Review-Bericht eines Template-Updates zählt nicht mehr als ungesehenes Projekt-Delta (#272); das Gate beurteilt ein Template-Update im Zug auf seinem eigenen Branch (#271); ein Testlauf unter `MAKEFLAGS=-n` oder einer Variable aus `certificate_env` verweigert den Push, und ein grüner Stufen-Retry schreibt das Merge-Zertifikat (#265); ein Spec-Kit-Plan im Flug schuldet Präsenz und eigene Familie im Gate und in `finish.py` (#266); `due_measurements.py` nennt eine fehlende Meilensteindatei (#259).

**Wirkung.** Was eine Regel oder ein Test fangen kann, wird vor dem Review gefangen; Warnungen, denen niemand folgen musste, wurden Pflichten mit einem ausdrücklichen Ausweg, und die Grundlinie zeigt, ob weniger Fix-Runden und Tokens je Arbeit folgen — mit durchgerutschten Arbeiten als Wächter.

**Update.**
1. Für bestehende Pläne ist nichts nötig: `plan-structure` bindet nur Pläne, die ein Branch neu anlegt.
2. Strenger als bisher:
   - jeder Tier-3-Code-Review-Pass braucht eine REFUTE-Zeile der Arbeit oder `skipped refute work=<id>: <Grund>`;
   - drei Fix-Commits auf einer Datei brauchen eine ROOT-CAUSE-Zeile oder einen Skip;
   - ein `review-waived:`-Plan im Flug braucht `DECISION <Datum> owner: …`; `/finish` fragt es vor dem Archivieren ab;
   - die Kriterien eines neuen Tier-2+-Plans folgen der EARS-Zeilenform mit einem `shall` (ein Projekt, das in einer anderen Sprache schreibt, ergänzt sein Wort in `shall_words`);
   - ein Push unter `MAKEFLAGS=-n` oder einer `certificate_env`-Variable wird verweigert;
   - ein Spec-Kit-Plan im Flug blockiert `finish.py` ohne sein Review.
3. Optional:
   - `plan-structure.local.json` für Projektabschnitte und eine Story-Registry;
   - `review-sections.local.json`, um die Checkliste zuzuschneiden;
   - `class=`/`rule=` an Befunden;
   - `--usage` und `status_file` für Harnesses ohne Transkripte.

**Geänderte Abschnitte.** `journal-state-plans.md` (Plans, Review attestations), `mandatory-rules.md`, `refute.md` (What happens with the findings), `start-here.md` (The standard setup), `testing.md` (Classes, not cases — neu), `train.md` (The run), `tower.md` (The worker protocol), `verification-independence.md` (The review bundle — the portable interface to any reviewer), Modul `telemetry` (The KPI cockpit)

Details: [Plan](docs/analysis/2026-10-21-v2.76.md) #259 #265 #266 #270 #271 #272 #276 #277 #278 #281 #282

## v2.75.0 — Template-Updates überstehen ein wanderndes main, eine Lesart für Fences, Buchführung aus den Läufen · 2026-10-19

**Warum.** Kennis v2.74-Update brauchte nach jedem Zug, der main bewegte, sein Ack und sein volles Tier-3-Review neu, obwohl sich am Update nichts geändert hatte; die Retry-Meldung des Zugs nannte zudem den falschen Retry. Die drei Leser von Fence-Blöcken waren sich uneins, was einen Fence schließt, sodass ein zitiertes `REVIEW … verdict=pass` oder `review-waived:` als echt zählen konnte. REFUTE- und Red-Evidence-Zeilen wurden noch von Hand getippt, ein gelöschter Plan entging seinem Review, und die v2.74-Reviews hinterließen kleinere Reste in attest, finish, dem Designvertrags-Gate und dem Review-Bundle.

**Was sich ändert.**
- Template-Update: Ack und REVIEW des Updates gehen auf ein neues main über, wenn die alte Basis ein Vorfahr der neuen ist und die Commits dazwischen keinen Pfad des Updates berühren; das Gate nennt ein abgelaufenes Ack (`ack_expired`), und ein Update-REVIEW zählt nur, wenn sein Head die Antworten, die Owned-Liste und das Projekt-Delta des Updates gesehen hat.
- Die Retry-Meldung des Zugs sagt, was lief: grün unter dem Retry-Befehl, ein Gate-Flake oder das klassische FLAKY.
- Fences: ein Durchlauf (`check_review.fenced_lines`) für den REVIEW-Parser, den Deklarationsleser und das Klärungs-Gate. Sie lesen Fences wie bisher. Wo die Schließregel von CommonMark (sonst nichts auf der Zeile, also schließt ` ```python ` in einem ` ```md `-Beispiel nichts) eine Zeile eines Journal-Shards, Plans oder Spec-Dokuments anders lesen würde, ist das ein harter Befund — ein zitiertes REVIEW oder Waiver, das früher zählte, wird jetzt abgelehnt. Ein am Ende eines Plans oder Journal-Shards noch offener Fence, der `tier:`, `issue:`, `review-waived:`, eine REVIEW-Zeile, `DECISION NEEDED` oder einen Klärungsmarker verdeckt, ist ebenfalls ein harter Befund (im Archiv ein Hinweis).
- Ein Tier-2+-Plan, den ein Push löscht oder dorthin verschiebt, wo kein Zweig einen Plan liest (`notes.txt`, ein Unterordner, `archive/<dir>/`), schuldet weiter sein Review; die Dispatch-Kette stellt kein execute ein, solange ein Branch keinen eindeutigen Fork-Punkt hat.
- `refute_line.py` schreibt die REFUTE-Zeile aus dem Bericht des Refuters: Der Brief endet jetzt mit `SCENARIO`- und `PATTERN`-Zeilen, das Werkzeug zählt sie und nimmt die nächste Runde; die Zusammenfassung ist der einzige freie Text.
- `red_evidence.py --junit PATH` misst Rot-vorher/Grün-nachher für jeden Runner, der JUnit-XML schreibt (vitest, jest, XCTest); `PATH` ist eine nicht versionierte `.xml`-Datei, und der alte Baum leiht sich die installierten `node_modules`.
- `process_kpis.py models` zeigt den Anteil jedes Modells an den Tokens der dispatchten Sitzungen, Subagenten eingeschlossen.
- `finish.py --tests` ohne Befehl fährt die konfigurierte `merge_suite`; `--tests-passed` wird verweigert, solange eine gesetzt ist.
- attest: Die niedrigste Modellklasse reviewt keinen Plan, ein ungemessener Modell-Report wird mit Hinweis verweigert, und eine Basis ohne `review_evidence` übernimmt die strengeren Tier-Untergrenzen von HEAD.
- Designverträge: Ein flacher Klon datiert alte Pläne nicht mehr auf seine Grenze (ein Hinweis nennt `git fetch --unshallow`); der Status `legacy` registriert eine Norm von vor der Registry mit einem Hinweis.
- Das Review-Bundle trägt die `CLAUDE.md`/`AGENTS.md` der Ordner, die ein Diff berührt; `dispatch.py` nutzt den Fork-Punkt des Gates, und `--plan` findet einen Plan über das Issue, das er deklariert.
- `testing.md`: Ein Projekt, dessen `merge_scope` Stufen überspringt, plant einen vollen Lauf mit Alarm als Netz unter seiner Auswahl.
- Das Changelog-Archiv vor v2.28.2 ist jetzt ein Eintrag je Release, deutsch und englisch.

**Wirkung.** Ein Template-Update wird einmal quittiert und einmal reviewt, auch wenn dazwischen Züge mergen. Ein zitiertes Beispiel kann kein Review mehr freigeben oder erlassen, und ein kaputter Fence schaltet kein Gate mehr ab. REFUTE- und Red-Evidence-Einträge kommen aus den Läufen, und der Token-Bericht zeigt, ob mechanische Schritte wirklich beim kleineren Modell gelandet sind.

**Update.**
1. Nichts ist nötig.
2. Strenger als bisher: Eine Zeile wie ` ```python ` in einem Fence schließt ihn nicht mehr; ein offen gelassener Fence, der `tier:`, `issue:`, `review-waived:` oder eine REVIEW-Zeile verdeckt, ist jetzt hart — den Fence schließen. `finish.py --tests-passed` wird verweigert, wo `merge_suite` gesetzt ist (`--tests` nutzen). Einen Tier-2+-Plan ohne sein Review zu löschen, verweigert der Merge-Push.
3. Optional: Refute-Berichte in der `SCENARIO`/`PATTERN`-Form schreiben und mit `refute_line.py` anhängen; `--junit` für Suiten außer pytest; mit `merge_scope` den vollen Lauf planen (`testing.md`).

**Geänderte Abschnitte.** `commits.md` (Merging), `journal-state-plans.md` (Review attestations), `refute.md` (The brief, What happens with the findings), `releases.md` (Updating the process template), `review-checklist.md` (Extending this list), `risk-tiers.md` (Template updates), `testing.md` (Test economy — scoped inner loop, full merge boundary), `tower.md` (Dispatch and the model policy), `verification-independence.md` (The review bundle — the portable interface to any reviewer, Enforcement), Modul `design-contracts` (The registry entry, Hard vs. best-effort (no false-green), Declaring the contract), `/execute`, `/finish`, `/review`

Details: [Plan](docs/analysis/2026-10-15-v2.75.md) #124 #125 #207 #228 #229 #230 #232 #250 #251 #252 #253 #254 #255 #256 #257 #262 #263

## v2.74.2 — `make -k` zertifiziert wieder · 2026-10-16

**Warum.** v2.74.0 verweigerte Zertifikate unter MAKEFLAGS, die verändern, was läuft, und zählte `-k` dazu. Keep-going verdeckt aber nichts: make läuft nach einem Fehler die übrigen Ziele weiter und endet trotzdem mit einem Exit ungleich 0. Der eigene Rat des Templates fährt die Suite als `make -k test-merge`, und genau so tut es Kennis Merge-Suite. Zwei Züge sind gescheitert: Unter dem geerbten `MAKEFLAGS=k` wurden die Tests rot, die Zertifikate schreiben, und der Push auf main wurde verweigert.

**Was sich ändert.**
- `-k` und `--keep-going` sperren kein Zertifikat mehr.
- `-i`, `-n`, `-t`, `--eval` und abgekürzte Langoptionen sperren weiter.

**Update.** Nichts zu tun.

**Geänderte Abschnitte.** `testing.md` (Test economy — scoped inner loop, full merge boundary)

Details: #263

## v2.74.1 — Der Familienname aus /review gibt ab own_family_from_tier wieder frei · 2026-10-15

**Warum.** `/review` hält einen Pass mit `--model <family>` fest, zum Beispiel `claude`. Ab `own_family_from_tier` zählte v2.74.0 nur Modelle, deren Klasse die Ränge kennen (`claude-opus`). Ein Pass, der so festgehalten wurde, wie es dokumentiert ist, gab deshalb weder im Gate noch in `finish.py` noch im Zug frei. Kenni fand das im Review seines v2.74-Updates; dort hätte es laufende Tier-3-Pässe abgelehnt.

**Was sich ändert.**
- Ein bloßer Familienname zählt als eigene Familie, wenn eine gerankte Klasse zu ihm gehört (`claude` für `claude-*`). Der Name einer anderen Familie (`codex`, `gpt`), ein angefangenes Präfix (`claude-op`) und ein Nicht-Name (`opus`) zählen nicht.
- Der bloße Name bleibt ohne Klasse: Eine Plan-Review braucht weiter die konkrete Modell-ID.

**Update.** Nichts zu tun. Nur Projekte, die `own_family_from_tier` setzen, merken es.

**Geänderte Abschnitte.** `verification-independence.md` (Enforcement)

Details: #260

## v2.74.0 — Weniger Projektabweichung, Codex-Handoff repariert, lesbarer CHANGELOG · 2026-10-15

**Warum.** Kenni hielt nach v2.73 noch eine eigene Kernel-Fassung, zwei eigene Gate-Skripte im Template-Verzeichnis und mehrere Overlays nur dafür, dass dem Template eine Option fehlte. Der neue Codex-Handoff ließ einen fehlgeschlagenen Push liegen und prüfte den Katalog im falschen Verzeichnis. Der CHANGELOG war ein Commit-Protokoll ohne Gliederung.

**Was sich ändert.**
- Die Sprache der Artefakte ist eine Copier-Antwort: `artifact_language: english` (wie bisher) oder `conversation` (Code, Commits, Issues und Contract-Docs englisch, Prosa des Operators in der Gesprächssprache).
- `review_evidence.own_family_from_tier` lässt ab einem Tier nur Pässe der eigenen Modellfamilie freigeben; Gate, `finish.py` und Train fragen denselben Owner.
- Das Modul `design_contracts` kennt eine Opt-in-Pflicht: Mit `design-contract-declaration.local.json` erklärt jeder Tier-2+-Plan seinen Contract oder `n/a — <Grund>`.
- `due_measurements.py` meldet fällige Messmeilensteine aus `milestones.local.json`, bis ein Bericht `milestone: <id>` trägt.
- `/execute` verlangt für jede Übergabe verbotene Pfade, ACs und engen Prüfbefehl, zurück kommt Rot vor und Grün nach der Änderung; ein größeres Modell braucht einen benannten Grund.
- Weitere Korrekturen: Ein fehlgeschlagener Attest-Push wird wiederholt, der Codex-Katalog wird im Worktree gefragt, Testtitel dürfen Kommas tragen, FINDING-Zeilen nennen mit `by=` ihren Reviewer, und MAKEFLAGS, die verändern, was läuft (`-i`, `--eval`, Abkürzungen), zertifizieren nichts.

**Wirkung.** Ein Projekt drückt seine Eigenheiten über Antworten und lokale Dateien aus statt über eigene Fassungen von Template-Dateien; Updates laufen ohne Konflikte im Kernel und ohne eigene Gate-Skripte. Der CHANGELOG sagt je Release, warum es sich geändert hat und wozu es führt, auf Englisch und Deutsch.

**Update.**
1. Wer die Prosa in der Gesprächssprache schreibt, setzt vor dem Update `artifact_language: conversation` in `.copier-answers.yml`; eine handgepflegte Sprachzeile im Kernel entfällt dann.
2. Wer die neuen Optionen will: `own_family_from_tier` in `model-policy.local.json`, `milestones.local.json`, `design-contract-declaration.local.json`. Ohne sie ändert sich nichts.
3. Strenger als bisher: eine AC-Zeile mit Komma im Text, die keine zweite Referenz meint, ist jetzt eine Referenz; MAKEFLAGS mit unbekannter Langoption zertifiziert nichts.
4. Für Kenni: die Schritte stehen im Abschnitt Migration des [Plans](docs/analysis/2026-10-15-v2.74.md); das alte Gate `check_tier3_claude_pass.py` entfällt erst in einem Folge-Commit nach dem Merge.

**Geänderte Abschnitte.** `kernel.md` (Always-on kernel, nur bei `conversation`), `start-here.md` (Purpose, Dialogue rules, nur bei `conversation`), `improvement-weekly.md` (Inputs, Steps), `optimization.md` (The record), `tower.md` (Dispatch and the model policy), `train.md` (The run), `verification-independence.md` (Enforcement), Modul `github-issues` (Review and audit visibility), Modul `design-contracts`, `/execute` und sein Copilot-Prompt

Details: [Plan](docs/analysis/2026-10-15-v2.74.md) #231 #237 #239 #240 #241 #242 #243 #244 #245 #246 #247 #248

## v2.73.0 — Codex-Review attestiert, Overlays für Projektnotizen, manuelles CI · 2026-10-15

**Warum.** Kenni führte Codex-Worker, die Übergabe-Regel je Paket und den Verzicht auf gehostetes CI als eigene Fassungen; das Template nimmt sie auf, damit Kenni nicht davonläuft. Projektnotizen in Template-Docs hatten keine Prüfung, ob eine Template-Änderung sie bricht.

**Was sich ändert.**
- `--harness codex` für `start`, `queue add` und `policy` startet einen Codex-Worker unter Supervisor mit Zeitlimit; Voraussetzung ist eine eingeloggte Codex CLI.
- `dispatch.py handoff <branch>` prüft Belege, attestiert und pusht; fällt Codex aus, bleibt eine Spur, Ausweg: `--harness claude` oder `skipped cross-model`.
- `/plan` verlangt je größerem Paket `Execution: delegate | retain-context` mit Begründung; `report.py --execution` und `process_kpis.py execution` zeigen, ob Delegieren Review-Runden kostet.
- `ci.github: manual` rendert Workflows nur per `workflow_dispatch` und ohne Schutz-Skript; durchgesetzt wird im pre-push-Hook, erlaubt sind `true`, `false`, `manual`.
- Projektnotizen zu Template-Docs und -Befehlen stehen in `docs/process/<doc>.local.md` bzw. `docs/process/commands/<name>.local.md`, verankert mit `extends`/`replaces: "<Überschrift>" @<hash>`.
- Das Gate `overlays` wird rot, wenn sich ein verankerter Abschnitt ändert, bis er mit `--stamp` neu gestempelt ist; `template_update.py` nennt betroffene Overlays.

**Wirkung.** Codex wird vollwertiger Reviewer und hinterlässt eine Spur, wenn er ausfällt. Eigene Regeln brechen bei Template-Änderungen nicht mehr unbemerkt, kosten aber bei jeder Änderung eines verankerten Abschnitts eine Sichtung; Kenni braucht keinen Gate-Code mehr in `.process-owned`.

**Update.**
1. Wer `ci.github: manual` will, setzt die Antwort in `.copier-answers.yml` vor dem Update. Erlaubt sind `true`, `false` und `manual`; der String `"true"` wird verweigert.
2. Eigene Notizen in Template-Docs und -Befehlen nach dem Update in Overlays verschieben, verankern und mit `--stamp` stempeln. Der Kernel nimmt kein Overlay.
3. Für Kenni, vor dem Update: `ci: {github: manual}` setzen und `legacy_preflight` aus `scripts/process/_dispatch_codex.py` in eine eigene Datei außerhalb von `scripts/process/` verschieben — das Template ersetzt die Datei.
4. Für Kenni, danach: Codex-Werte nach `model-policy.codex.local.json`, eigene Regeln in Overlays, `.process-owned` leeren, die Tests zum beratenden Codex-Handoff anpassen oder streichen.

**Geänderte Abschnitte.** `commits.md` (Merging), `start-here.md` (The standard setup, Anchors: what goes where…, Definition of ready), `tower.md` (Dispatch and the model policy), `verification-independence.md` (The review bundle…), `workflow.md` (Plan), Module `arch-onboarding`, `doc-drift-gate`, `feature-registry`, `git-hooks` (Honest ceiling), `sbom` (The gate), alle Befehle und Copilot-Prompts (neue Overlay-Zeile unter dem Titel)

Details: [Plan](docs/analysis/2026-10-15-kenni-backport-2.md)

## v2.72.0 — Merge-Scope im Zertifikat, Stufenzeiten, gestrichene ACs · 2026-10-15

**Warum.** Kennis Änderungen sollen so weit wie möglich im Template liegen. Ein Render mit Kennis Antworten fand 27 abweichende Template-Dateien, sieben davon trug Kenni als eigenen Gate-Code in `.process-owned`; das machte jedes Template-Update dort zur Migration.

**Was sich ändert.**
- `testing.local.json` kennt `merge_scope`, ein argv, das die Stufen der `merge_suite` nennt; ein engerer Lauf zertifiziert nie einen volleren Push.
- Zug und `finish --tests` löschen vor der Suite alte Stufen- und Zeitdateien, und das Memo des Zugs gilt nur bei gleichem Scope.
- Eine gestufte Merge-Suite hinterlässt in `<git-dir>/merge-suite/` `stages` und je Stufe `<stufe>.time`; `process_kpis.py train-phases` zeigt je Stufe Median, Maximum und Übersprünge.
- `AC-<id>: struck — <Grund>` oder `dropped` nimmt eine eigene AC aus der Testpflicht; der Review-Bericht muss jede Streichung bestätigen, sonst verweigert attest.
- Kleinere Änderungen: ungültiges `stale_minutes` und falsche Policy-Form werden gemeldet, Design-Contract-Notizen und `.process-work/inbox.md` mergen mit `merge=union`, CI bricht ältere Läufe auf Branches ab, nie auf `main`.
- Docs und Befehle aus Kenni: zwei Test-Lanes mit begrenztem Push-Warten, kohärente Pakete in `/plan` (Median 53 statt 183 Turns), `/finish --tests` mit dem `merge_suite`-String.

**Wirkung.** Ein schmalerer Lauf kann keinen volleren Push mehr freigeben, und der Zug zeigt, welche Stufe Zeit kostet. Der erste Push nach dem Update läuft einmal neu, weil die Konfiguration jetzt `merge_scope` trägt.

**Update.** Keine Schritte. Optional für Kenni, in dieser Reihenfolge:
1. Update auf v2.72.0 mit den Einträgen in `.process-owned`.
2. `certificate.py`, `testing_config.py`, `test_select.py`, `train.py` und `finish.py` durch den neuen Render ersetzen.
3. Die fünf Zeilen aus `.process-owned` streichen.

Details: [Plan](docs/analysis/2026-10-15-kenni-backport.md) #226 #234 #235 #221

## v2.71.0 — Nachweise vor dem Pass: Cross-Model, Refute, ein Test je AC · 2026-10-14

**Warum.** Kenni mergte in einer Nacht sechs Tier-2-Branches mit Pass in Review-Runde 1; ein Audit fand danach sechs Major-Fehler, vier davon Tests, die nicht rot werden können. 4 von 4 Gate-Code-Branches ließen den Refute aus, und der Cross-Model-Lauf fehlte ohne Hinweis, denn beides hatte bisher nur gewarnt.

**Was sich ändert.**
- Ein Code-Review-Pass ab Tier 2 braucht einen Bericht (`--with`) mit einer Zeile `AC-<id>: <pfad>::<test>` je AC; `unproven` verweigert den Pass.
- Das Projekt deklariert seine Testdateien in `review_evidence` (`python_files`, `python_classes`, `test_files`); der Test muss wirklich laufen, nicht abgeschaltet.
- Berührt der Bereich Gate-Code, braucht ein Pass ab Tier 2 eine REFUTE-Zeile im eigenen Plan oder `skipped refute work=<id>: <Grund>`.
- Ab `review_evidence.cross_model_from_tier` (Standard 3) trägt der Pass `cross-model` oder `single-family` mit `skipped cross-model`.
- Ein Plan-Review-Pass ab Tier 2 nennt mit `--model` die Modell-ID, deren Rang nicht unter dem der Plan-Session liegt; Pläne tragen `plan-session model: <id>`.
- Jede Regel hat einen committeten Ausweg `skipped <art> work=<id>: <Grund>` (`cross-model`, `refute`, `plan-review`, `ac-trace`).

**Wirkung.** Ein Pass belegt, was er behauptet, und fehlende Nachweise sind zählbar statt still. Das kostet mehr Pflichtzeilen; eine von Hand geschriebene REVIEW-Zeile umgeht die Prüfung weiterhin, und ob ein Test seine AC prüft, beurteilt der Reviewer.

**Update.**
1. Tier-2+-Reviews: Bericht mit AC-Zeile je AC schreiben und mit `--with` attestieren; Plan-Reviews mit `--model`.
2. Pläne tragen `plan-session model: <id>`; ein Single-Family-Pass auf Tier 3 braucht `skipped cross-model work=<id>: <Grund>`.
3. Spec-Kit-Projekte geben Plan oder `spec.md` AC-IDs oder tragen `skipped ac-trace work=<id>: <Grund>` in den Plan, sonst wird jeder Tier-2+-Pass verweigert.
4. Für Kenni: die Schritte stehen im Abschnitt Migration des [Plans](docs/analysis/2026-10-14-review-evidence.md).

Details: [Plan](docs/analysis/2026-10-14-review-evidence.md) #225

## v2.70.0 — Erzeugte Bestandslisten, Leser-Suche im Plan, Neuigkeiten · 2026-10-13

**Warum.** Rund 200 blockierende Review-Befunde eines Projekts, nach Ursache sortiert, zeigten ~47 % Implementierungsfehler und 10–16 % fehlendes Wissen über Bestehendes. Die Wissenslücken entstanden beim Lesen von Code und bei unbekannten Lesern, nicht durch eine fehlende Gesamtspezifikation.

**Was sich ändert.**
- `inventory.py update` erzeugt Bestandslisten (Umgebungsvariablen, Jobs, Tabellen, Tools) nach `docs/inventory/<name>.md` aus Extraktoren in `docs/process/inventories.local.json`.
- `inventory.py check` vergleicht bytegenau und ist ohne Konfiguration inaktiv; das Projekt registriert den Check in `gates.local.json`.
- `inventory.py for-plan <plan>` nennt die Bestandszeilen der berührten Dateien, `/plan` übernimmt sie in die Tasks.
- Ein Plan, der eine Konstante, einen Standardwert, ein Timeout, ein Format oder eine Umgebungsvariable ändert, belegt in `## Consumers` die Suche nach Lesern und Schreibern.
- FINDING-Zeilen tragen optional `kind=` (`knowledge-gap`, `requirement`, `implementation`, `test-gap`, `process`, `environment`), und `process_kpis.py rounds` zählt Blocker danach.
- Jede nutzersichtbare Änderung bringt ein Fragment `news/<slug>.md` (`news.py new`); der Steward rendert wöchentlich `NEWS.md`, Titel und Bezeichnungen aus `news.local.json`.

**Wirkung.** Planer und Reviewer sehen Bestand und Leser, bevor sie etwas ändern, und Blocker lassen sich nach Ursache auswerten; Nicht-Techies lesen, was neu ist. Die Extraktoren muss jedes Projekt selbst schreiben.

**Update.** Keine Schritte.

Details: [Plan](docs/analysis/2026-10-13-knowledge-anchors-plan.md) #223

## v2.69.0 — Plan-Drift-Messung, Worktree-Probelauf, zwei Release-Arten · 2026-10-13

**Warum.** Ein Plan war über 1000 Commits alt, als sein Execute startete, und Migrationen, die Skripte löschen oder ersetzen, hatten keinen vorgeschriebenen Probelauf in einem frischen Worktree. Ein Test, der in einem eigenen Temp-Repo committete, traf beim Push das pushende Repo.

**Was sich ändert.**
- `dispatch.py start --phase execute` misst Plan-Drift; Mandat `plan_drift`: `mode` `shadow` (Standard, nur protokollieren), `warn` oder `block` (aufhebbar mit `--stale-plan-ok`).
- Ein migrierender Plan oder einer, der ein Gate-, Hook- oder Lane-Skript löscht oder ersetzt, trägt einen `## Fresh-worktree dry run` mit Exit-Codes aus einem frischen `git worktree`.
- Ein Release ist ein reines Update oder ein Migrations-Release mit eigenem Abschnitt `Migration` (`releases.md`).
- `tower.py --wait` weckt bei stillen Workern ohne Bericht und Commit seit der Schwelle (`--stale-minutes`, `PROCESS_STALE_MINUTES`, Policy `stale_minutes`, sonst 60), je Funkstille einmal.
- pre-push entfernt die git-Variablen des Repos (`GIT_DIR`, `GIT_INDEX_FILE`, …) aus den Kindprozessen von Gates, Testläufern und Merge-Suite.
- `DoD-deviation: …`-Zeilen eigener Pläne gehen in den Merge-Commit; `open AC-3 — …` oder `continues #42 — …` hält das Issue offen (`Refs #N`).

**Wirkung.** Veraltete Pläne fallen auf, bevor Arbeit darauf aufbaut, stille Worker wecken den Steward, und Tests können das pushende Repo nicht mehr verändern. Ein Issue schließt nicht vorzeitig, wenn der Plan eine Abweichung von der Definition of Done nennt.

**Update.** Keine Schritte. Plan-Drift läuft zunächst nur protokollierend; nach zwei bis vier Wochen zeigen `nodes` und `flow`, ob die Grenzen passen, dann entscheidet der Owner über `warn` oder `block`.

Details: #213 #214 #217 #218 #219 #220

## v2.68.0 — Prozess als Prüfgraph: Knotenmessung, Gate-Modi, Wochenschleife · 2026-10-13

**Warum.** Der Prozess soll mehr Output bei gleicher Qualität liefern und dafür Gates abschwächen oder entfernen können. Es fehlte die Messung, was ein Gate kostet und fängt, und ein sicherer Weg, es abzuschwächen.

**Was sich ändert.**
- Der Gate-Runner schreibt je Gate-Lauf eine Zeile (Ergebnis, Dauer, Commit, Modus) nach `process-gate-events.jsonl` im gemeinsamen git-Verzeichnis.
- `process_kpis.py nodes` zeigt je Gate Kosten, Blockaden und Flips, `losses` vier Verlustmaße, `outcomes` Epics und Bugs bis zum ausgelieferten Ergebnis.
- `gate_modes.py` setzt den Modus eines Gates (`block`, `shadow`, `sampled`, `off`) im Protokoll `docs/process/gate-changes.local.jsonl`; Abschwächen braucht eine Owner-Zeile, Kern-Gates sind ausgenommen.
- Der Steward ruft täglich `gate_modes.py sentinel` auf (Rückbau bei gerissener Leitplanke); `improvement-weekly.md` und `improvement-monthly.md` beschreiben die Schleifen.
- Token-Summen zählen eine API-Nachricht einmal statt je Zeile (vorher überhöht); `flow` endet am Deploy, sonst am Merge, und sagt welcher.
- Verhaltensänderung: `optimize.py` `active()` liefert eine `Activation` mit Wahrheitswert an/aus (in v2.67 war `if active(...)` immer wahr), und zwei laufende Versuche schalten sich gegenseitig ab.

**Wirkung.** Ein Projekt sieht je Gate, was es kostet und ob es etwas fängt, kann ein neues Gate im Schatten beobachten, bevor es blockiert, und bei gerissener Leitplanke automatisch zurückbauen. Preis: Jeder Gate-Lauf schreibt eine Zeile, und jede Abschwächung kostet eine Owner-Zeile.

**Update.** Keine Schritte. Optional: Bugs mit `cause:*` und `channel:*` labeln und für Epics im Mandat `outcomes.usable` setzen (etwa `label:acceptance`), damit `outcomes` die Abdeckung zeigt.

Details: [Plan](docs/analysis/2026-10-12-closed-loop-plan.md)

## v2.67.0 — Optimierungsvertrag mit eingefrorenen Kriterien und Flow-Messung · 2026-10-12

**Warum.** Der Owner wollte einen Prozess, der sich selbst verbessert: beobachten, Ursache finden, Verbesserung unabhängig prüfen, begrenzt einsetzen, Wirkung bewerten. Dafür fehlten ein Vertrag, der Kriterien vor dem Versuch festlegt, und eine Messung von der ersten Phase bis zum Deploy.

**Was sich ändert.**
- `docs/process/optimization.md` beschreibt den Regelkreis; `optimize.py` führt je Verbesserung einen Record unter `.process-work/optimizations/`.
- Vor `piloting` braucht es ein Mandat (`docs/process/optimization.local.json`), Budgets und eine unabhängige `REVIEWED`-Zeile; danach sind Kriterien, Grenzen, Laufzeit und Budget byte-genau eingefroren.
- Ein Mechanismus im Versuch fragt `optimize.py active <flag>` (Zweifel heißt aus); übernehmen darf der Owner, der Steward nur mit `adopt` im Mandat, nie der Implementierer.
- `process_kpis.py flow [--issue N]` verfolgt ein Issue bis Deploy oder Merge: Arbeits- und Wartezeit, Tokens, Owner-Entscheidungen und Folgefehler über den Commit-Trailer `Regression-of: #N`.
- `graph.py build|context|missed` leitet Kanten aus Plänen, Testkarte, git-Co-Change und REVIEW-Zeilen ab und empfiehlt nur, ohne je ein Gate einzuengen.
- Der Steward bekommt den Abschnitt „Improvement loop“ (täglich, nicht pro Tick).

**Wirkung.** Ein Projekt kann Prozessänderungen als begrenzten Versuch fahren, ohne dass jemand nachträglich die Kriterien lockert, und sieht, wo ein Issue Zeit und Tokens verliert. Ohne Mandat und Records ändert sich nichts.

**Update.** Keine Schritte.

Details: [Konzept und Review](docs/analysis/2026-10-12-self-improving-process.md)

## v2.66.0 — Eine Regel für eigene Pläne, Plan-Review fail-closed · 2026-10-12

**Warum.** Dispatch zählte nur hinzugefügte Pläne: Ein Branch, der den main-Plan seiner Issue änderte, ging ohne Plan-Review direkt nach execute. Dazu urteilte `plan_review_due` bei unerreichbarem origin oder nicht-UTF-8-Ausgabe von git falsch oder stürzte ab.

**Was sich ändert.**
- Eigen ist ein vom Branch hinzugefügter Plan oder ein Basisplan, der eine Issue des Branches deklariert; Dispatch und Zug nutzen dieselbe Regel.
- Ändert ein Branch den main-Plan einer Issue, für die er dispatcht wurde, startet eine Plan-Review, und ihr Pass gibt die Chain frei.
- Ein Paket für #72 auf `70-pkg-…` prüft den Plan seines Epics #70 nicht.
- Prompt und Wartemeldung der Plan-Review nennen die fälligen Pläne mit Pfad und verlangen einen Pass je Plan.
- Im Zweifel wählt dispatch die Code-Review: bei unerreichbarem origin, in einer Remote-Session, bei `--dry-run` und bei nicht-UTF-8-Ausgabe von git.
- Im Zug gilt ein Branch, der einen aktiven Plan löscht, nicht mehr als „unlesbar“, und ein umbenannter Plan zählt nur einmal.

**Wirkung.** Ein geänderter Plan geht nicht mehr an der Plan-Review vorbei, und unklare Lage führt in die sichere Richtung. Ein Branch, der einen main-Plan ändert, braucht dafür vorher einen `-plan`-Pass, und `start --phase review` wird für ihn zur Plan-Review.

**Update.** Keine Schritte.

Details: #207 #204 #201

## v2.65.0 — Umgebungs-Preflight vor jedem Testlauf · 2026-10-10

**Warum.** In Kenni kam ein kaputtes Worktree-venv an einem Tag dreimal als rote certify- und Operator-Tests an; in v2.64 hatte nur der Zug ein `--preflight`.

**Was sich ändert.**
- `testing.local.json` kennt `preflight` (argv ohne Shell) und `preflight_timeout` (Standard 600 s).
- Er läuft einmal vor dem ersten Testbefehl, im pre-push-Rahmen, bei `run --certify` und bei Läufen von Hand; ein Zertifikatstreffer braucht ihn nicht.
- Ist er rot, läuft kein Test, es entsteht kein Stempel und kein Zertifikat, und der Lauf endet mit Exit 2.
- Der Zug nimmt ihn als Standard für `--preflight` mit demselben Zeitlimit; ein hängender Preflight wird samt Prozessgruppe beendet, `--preflight ""` läuft ohne.
- Beim Push laufen die Prozess-Gates vor dem Preflight.

**Wirkung.** Ein kaputter Host zeigt sich als Umgebungsfehler statt als roter Test und verbraucht keine Testläufe.

**Update.** Keine Schritte.

Details: #209

## v2.64.0 — Ein Testpfad: Auswahl, Lanes und Zertifikate aus Daten · 2026-10-10

**Warum.** `testing.md` beschrieb vier Regeln für Testauswahl und Lanes, die jedes Projekt selbst bauen musste. Kenni baute `lane.py`, pre-push und Selektoren selbst, und `certify` ließ dort für eine Ein-Datei-Änderung die volle Suite laufen.

**Was sich ändert.**
- `docs/process/testing.local.json` beschreibt je Stack Runner, Test-Globs, Map, `select`, `merge_suite`, Lanes und `certificate_env`; fehlt sie, laufen nur Gates, ist sie kaputt, wird der Push verweigert.
- `test_select.py plan|run|check` ist die eine Auswahlregel für Hook, `certify` und Handlauf; `check` meldet veraltete Pins und Map-Ziele.
- `lane.py` hält die Lanes `scoped` und `full` für alle Stacks eines Pushs gemeinsam; bleibt die Lane belegt, läuft kein Test.
- Zertifikate `push` und `merge` gelten für einen unveränderten Baum; ein Merge-Push ohne Zertifikat führt `merge_suite` aus, sonst je Stack `full`.
- `pre_push.py` ist die eine Abfolge jedes Pushs; `PROCESS_SKIP=gates|tests` ist der geloggte Owner-Notausgang, `gates.local.json` kennt `exec` und `paths`.
- Der Train kennt `--preflight CMD` und schreibt nach grüner Suite das Merge-Zertifikat; `finish.py --tests CMD` mit `merge_suite` ebenso. **Vertragsänderung:** `--tests-passed` schreibt keins.

**Wirkung.** Ein Projekt liefert Daten statt eigener Skripte, eine Ein-Datei-Änderung wählt nur ihre Tests, und eine grüne Merge-Suite läuft im Push nicht noch einmal.

**Update.** Für Kenni:
1. `testing.local.json` mit den Stacks schreiben, `unmapped: "skip"` und `merge_suite` auf das Merge-Target setzen; `.githooks/pre-push` auf `exec uv run scripts/process/pre_push.py "$@"` reduzieren.
2. `finish --tests-passed` durch `finish --tests <merge_suite>` ersetzen, sonst läuft die Suite im Push.

**Geänderte Abschnitte.** `testing.md` („One test path“), `train.md`, `failure-catalog.md`, BOOTSTRAP

Details: #206

## v2.63.0 — Plan-Review wird erkannt, Codex-Block zählt erst ab Score 80 · 2026-10-10

**Warum.** In Kenni (#2480, #2483) wurde ein Plan nach seinem Plan-Pass geändert, die Review-Session startete ohne `--plan-review` und brach mit „kein Code“ ab. Außerdem verhinderte eine Projektregel den Plan-Pass, sobald Codex blockte, obwohl die unabhängige Bewertung bei 75 lag und nur ein Residuum offen war.

**Was sich ändert.**
- `dispatch.py start --phase review` startet ein Plan-Review selbst, wenn der Branch nur Pläne und Bookkeeping ändert und ein eigener Tier-2+-Plan keinen Pass für seinen aktuellen Text hat.
- Maßgeblich ist der Stand, den die Session prüft; kann git die Frage nicht beantworten, bleibt es ein Code-Review.
- `--plan-review` erzwingt das Plan-Review weiterhin und ist nötig, wenn ein Plan, der schon auf main liegt, auf dem Branch geändert wird (#204).
- Ein Block einer zweiten Modellfamilie zählt erst ab Score 80, wie bei Plan-Reviews (`verification-independence.md`).
- Ein `review.local.md` darf die Rundenzahl verschärfen, nicht die Schwelle.

**Wirkung.** Ein geänderter Plan wird als Plan geprüft statt als Code-Review abgebrochen, und ein Residuum unter der Schwelle verhindert den Plan-Pass nicht mehr.

**Update.** Für Kenni: die eigene Regel anpassen, die die Score-Schwelle verschärft.

Details: #203

## v2.62.1 — Gültige Runde mit gleicher Nummer löst die alte Zeile ab · 2026-10-10

**Warum.** `attest.py` zählt Runde = 1 + blockierende Runden, die Runde nach einem Pass behält also dessen Nummer; v2.62.0 verlangte für die ablösende Vollrunde aber eine höhere. In Kenni #2396 blieb deshalb eine alte formwidrige Delta-Zeile bestehen, und jeder Push blieb verweigert.

**Was sich ändert.** Eine Vollrunde löst die alte Zeile auch bei gleicher Nummer ab, sofern sie ein Pass ist und ihr Head vom alten abstammt.

**Update.** Keine Schritte.

Details: #199

## v2.62.0 — Vier Gate-Lücken aus dem Kenni-Betrieb geschlossen · 2026-10-10

**Warum.** Der Kenni-Steward meldete vier Lücken auf v2.61: hängende Branches nach dem Merge von main (#2240, #2396), ein vom Zug abgewiesener Branch mit aktivem Plan, ein durch `attest --with` stale gemachter Spec-Kit-Plan und `finish.py --tests` mit `shell=True`. Letzteres löste die Security-Scanner der Consumer aus.

**Was sich ändert.**
- Eine überholte REVIEW-Zeile blockiert nicht mehr, wenn eine gültige Vollrunde derselben Arbeit mit höherer Runde und abstammendem Head folgt; sie wird zur Notiz.
- Der Zug zählt den aktiven Plan eines Branches als dessen Arbeit, wenn der Branch ihn hinzufügt oder er eine Issue des Branches trägt.
- Ein Spec-Kit-Plan wird nicht mehr stale durch angehängte Records (REFUTE, ROOT-CAUSE, REVIEW, datierte DECISION), eine beantwortete `DECISION NEEDED` oder das Archivieren.
- `finish.py --tests` läuft ohne Shell: Führende Zuweisungen (`FOO=1 make test`) gelten als Umgebung, Shell-Operatoren werden vor dem ersten Schritt abgelehnt.

**Wirkung.** Branches hängen nach dem Merge nicht mehr fest, die eigene Attestierung entwertet kein Review mehr, und die Scanner schlagen nicht mehr an. Mehrere Teststufen gehören dafür in ein make-Target oder Skript.

**Update.**
1. `finish.py --tests` mit mehreren Stufen oder Shell-Operatoren: in ein make-Target oder Skript legen.
2. Für Kenni: Den Scanner für Merge-Commits im eigenen `.githooks/pre-commit` pflegt Kenni selbst; das Template liefert keinen.

Details: #199

## v2.61.0 — Tier wird nachgerechnet, geänderte Werte werden gesucht · 2026-10-09

**Warum.** In Kenni #2454 schrieb ein Tier-2-Plan den Redirect-Pfad um, an dem der einzige SSRF-Guard hing, ohne dass das Tier nachgerechnet wurde; in #2456 sahen Plan und Review bei einem Image-Tag nur die Paketliste, nicht Makefile, Tests und Doku, und der Zug lief rot. Außerdem startete `template_update.py --help` ein `copier update` im aktuellen Checkout, vermutlich die Ursache von Kenni #2463.

**Was sich ändert.**
- Ab Tier 2 nennt der Plan die berührte Grenze und ihren unabhängigen Guard (`file:line`); ist der geänderte Code die einzige Durchsetzung, gilt Tier 3.
- `review-checklist.md`, `/plan` und der Plan-Brief in `refute.md` stellen diese Frage; hält das Tier nicht, stoppt das Review und die Arbeit wird neu eingestuft.
- `/plan` inventarisiert geänderte Versionen, Pfade und Konstanten wie eine Umbenennung und zitiert die Suche; das Code-Review sucht den alten Wert selbst noch einmal.
- `template_update.py` liest Argumente mit argparse: `--help` ändert nichts, unbekannte Argumente und ein Verzeichnis ohne `.copier-answers.yml` werden vor copier abgelehnt.

**Wirkung.** Eine Änderung an der einzigen Durchsetzung eines Guards wird als Tier 3 geprüft, ein Wert, der an mehreren Stellen steht, wird vor dem Zug gefunden, und `--help` ist wieder harmlos.

**Update.** Keine Schritte.

Details: #197

## v2.60.0 — Mechanische Tasks laufen auf Haiku · 2026-10-09

**Warum.** Seit v2.58.0 schneidet `/plan` Tasks so, dass ein kleines Modell sie ohne eigene Entscheidung ausführen kann; die Klasse `mechanical` lief trotzdem auf Sonnet.

**Was sich ändert.** In `model-policy.json` zeigt `classes.mechanical.execute` jetzt auf `claude-haiku-5`; `[design]`-Tasks bleiben auf Opus, Review und Refute folgen weiter dem Tier.

**Wirkung.** `[mechanical]`-Tasks laufen mit dem Update auf dem kleineren Modell.

**Update.** Wer bei Sonnet bleiben will, setzt in `model-policy.local.json`: `{"classes": {"mechanical": {"execute": "claude-sonnet-5"}}}`.

## v2.59.1 — Der Zug testet einen schon grünen Baum nicht noch einmal · 2026-10-09

**Warum.** Im Kenni-Zug 20261009-0935 sah die Bisektion main+#2445 grün; nach dem Abwerfen von #2456 lief der Neubau, also derselbe Baum, noch einmal 25 min durch die Suite. Ein reiner Doku-Branch hielt die Lane so fast zwei Stunden.

**Was sich ändert.** `judge` überspringt die Suite für Bäume, die im selben Zug schon grün waren; die Gates laufen weiter.

**Update.** Keine Schritte.

## v2.59.0 — Der Zug wiederholt einen roten Lauf günstig · 2026-10-09

**Warum.** Der Zug baute einen roten kombinierten Baum bisher immer neu und ließ die ganze Suite noch einmal laufen, auch bei deterministischem Rot. In Kenni kostete das bei einem 25-minütigen `test-merge` einen zweiten 24-Minuten-Lauf vor dem Drop.

**Was sich ändert.**
- Rote Gates laufen noch einmal auf demselben Worktree, bei Grün danach die Suite; das Log nennt Entscheidung und Grund.
- Bei roter Suite führt `--retry` den Projektbefehl auf demselben Worktree aus; ohne `--retry` wird wie bisher neu gebaut.
- `--retry` wiederholt, was fehlschlug und was nicht lief, damit Stufen hinter der ersten roten nicht ungetestet gemergt werden.
- Hinterlässt der erste Lauf etwas, das git sieht, wird neu gebaut; die Suite-Ausgabe gehört daher in die gitignore.

**Wirkung.** Ein deterministisches Rot kostet nur noch den Wiederholungslauf der Fehlschläge, und der Schutz vor Flakes bleibt.

**Update.** Für Kenni:
1. Die Suite als `make -k test-merge` laufen lassen, damit jede Stufe einmal läuft.
2. `--retry "make test-merge-retry"` über `TRAIN_ARGS` oder das `train`-Target übergeben; je Stufe laufen nur die fehlgeschlagenen Tests.

Details: #193

## v2.58.0 — Ein Plan wird unabhängig geprüft, bevor Code entsteht · 2026-10-09

**Warum.** Zwischen Plan und execute las niemand den Plan unabhängig; der erste unabhängige Blick kam mit dem Code-Review. In Kenni #2454 deckte ein Tier-2-Plan alle acht ACs ab und hatte trotzdem zwei Lücken, die erst nach einer vollen Execute-Runde aufgefallen wären.

**Was sich ändert.**
- `review-checklist.md` beginnt jeden Abschnitt mit „Plan decides:“; der Plan entscheidet dort für die berührten Dimensionen, das Code-Review prüft den Code dagegen.
- Tier 2: Ein frischer Subagent prüft den Plan mit dem Plan-Brief in `refute.md`, der Planer attestiert mit `attest.py --plan-review --commit`.
- Tier 3: Eine eigene Plan-Review-Session mit zweiter Modellfamilie prüft den Plan.
- `dispatch.py chain` stellt execute erst ein, wenn jeder eigene Tier-2+-Plan einen bestandenen Plan-Review für seinen aktuellen Text trägt.
- `/plan` schneidet Tasks möglichst als `[mechanical]` (exakte Dateien, Contract, Test, Befehl); was ein Urteil braucht, wird `[design]`.
- Prüfungen, die `.process-work/` lesen, sind Gates statt Tests hinter dem Baum-Stempel.

**Wirkung.** Lücken im Plan fallen vor dem Code auf, und mehr Tasks laufen auf dem kleinsten Modell. Grenze: `chain` handelt nur auf lokalen Sessions, nach einem Plan-Review auf einem anderen Host stellt der Steward execute selbst ein.

**Update.** Für Kenni: Laufende Tier-2+-Pläne brauchen vor execute einen Plan-Pass; eine Arbeit, deren execute schon läuft, ist nicht betroffen. Die mechanische Zelle in Kennis `model-policy.json` kann auf ein kleineres Modell zeigen.

**Geänderte Abschnitte.** `/plan`, `/review`, `workflow.md` (Plan), DoR R3, `tower.md`, `refute.md`, Copilot-Prompts

Details: #192

## v2.57.1 — Gemeinsame Dateien halten geprüfte Branches nicht auf · 2026-10-08

**Warum.** Ein Kandidat stieg nicht in den Zug ein, wenn er eine Datei mit einem Branch an Bord teilte. In Kenni wartete so ein ganzer Zuglauf auf drei geprüfte Branches, nur wegen eines gemeinsamen Tests, Contract-Dokuments oder einer Registry-Datei.

**Was sich ändert.** Git führt den Batch in Einstiegsreihenfolge zusammen und die volle Suite läuft auf dem kombinierten Baum; nur bei echtem Konflikt fliegt der spätere Kandidat mit `blocked` raus und rebased.

**Wirkung.** Branches, die verschiedene Stellen derselben Datei ändern, fahren zusammen. Bekannte Grenze: Wird B nach einer Kollision mit C als Verursacher entfernt, verpasst C den Zug trotzdem; sicher kollidierende Kandidaten zählen bei `--min-candidates` mit.

**Update.** Keine Schritte.

## v2.57.0 — Zug und Sessions warten nicht mehr auf Pre-Pushes · 2026-10-08

**Warum.** Am 08.10. hielten in Kenni serielle Pre-Pushes die `scoped`-Lane den ganzen Vormittag. Ein execute-Start wurde stundenlang abgewiesen, und es fuhr nur ein Zug, während fünf Kandidaten mit bestandenem Review warteten.

**Was sich ändert.**
- Der Zug (`departure`) wartet nicht mehr auf eine belegte `scoped`-Lane, sondern fährt die Suite mit `nice` auf `full` neben den kurzen Läufen.
- Ein Session-Start, auch execute, wird bei belegter `full`- oder `scoped`-Lane nicht mehr abgewiesen; nur die Testläufe warten an der Lane.
- Die Gates laufen schon vor `planned` im Plan-Prompt und in `/plan`; `chain` startet bei rotem Plan-Worktree kein execute und nennt den Grund.
- Eine Session startet auf dem Stand von origin: zurückliegende Worktrees werden vorgespult, abweichende abgewiesen; ein Review weist einen Worktree vor origin ab.
- Nach einem roten Batch entfällt die Suite auf dem nackten main, wenn der Zug diesen Baum schon grün sah (`green-suites`), außer vor dem Beschuldigen eines Passagiers.

**Wirkung.** Der Zug fährt neben den Pre-Pushes, execute-Starts warten nicht mehr, und Planfehler fallen vor execute auf. In Kenni scheiterte der Push dreißigmal pro Branch an einer fehlenden `design-contract:`-Zeile.

**Update.** Keine Schritte. Für Kenni: lokale Schritte in `run_issue.sh` (`gate_runner`, Nachziehen auf origin) zurückbauen; der Zug fährt ohne `--force`.

Details: Kenni #2441, #2446

## v2.56.1 — Review-Bundle bricht das Issues-Gate nicht mehr · 2026-10-08

**Warum.** Das Issues-Gate las jede `.md` in `.process-work/reviews/` als Report, auch das gitignorte Review-Bundle (`*.bundle.md`), und der Push scheiterte, weil ihm der `review:`-Kopf fehlt. In Kenni passierte das zweimal an einem Tag.

**Was sich ändert.** Von git ignorierte Dateien zählen nicht mehr als Reports, und `testing.md` beschreibt, wie Testauswahl und Lane-Skript aussehen sollen.

**Update.** Keine Schritte. Für Kenni: Auswahl (`Makefile`) und `scripts/lane.py` bleiben Kennis Code, mit Test-Unterpaketen und einer Lane-Haltung pro Push; Haltezeit vorher und nachher in #184 festhalten.

Details: #186, #184

## v2.56.0 — Debug-Methode, Brainstorm in Runden, geprüfte Review-Blocks · 2026-10-08

**Warum.** Ein Vergleich ohne Bias mit Matt Pococks `skills` v1.3.1 und Claude Codes `code-review`-Plugin zeigte Methoden, die dem Prozess fehlten. Übernommen wurde nur das; keine neuen Gates, keine neuen Artefakte.

**Was sich ändert.**
- Debug folgt einer festen Reihenfolge (`workflow.md`): rote Schleife, reproduzieren, falsifizierbare Hypothesen, Regressionstest an der Naht, Commit mit bestätigter Hypothese.
- Brainstorm stellt Fragen gebündelt in Runden, je mit einer Empfehlung; mit Spec Kit hält `/speckit-clarify` die Antworten fest.
- Ein blockierender Befund nennt sein Fehlerszenario; ein Defekt, dessen Weg nicht durch die Änderung führt, ist vorbestehend und damit ein Issue statt eines Blocks.
- Ein frischer Prozess bewertet jeden Block (0/25/50/75/100); unter 80 wird er zum Rest-Befund, und was Linter, Typprüfer oder Tests fangen, blockiert nie.
- Jede Review-Linse berichtet in höchstens etwa 400 Wörtern, das Schwerste zuerst, und schließt mit „Merge danger“.
- `review-checklist.md` bekommt „Silent failures“, `testing.md` nennt tautologische und an Interna hängende Tests, `THIRD-PARTY-NOTICES.md` führt die übernommenen Quellen.

**Wirkung.** Debug-Sessions und Reviews folgen einer festen Methode; ein Block ist belegt statt vermutet, und schwache Befunde halten den Merge nicht auf.

**Update.** Keine Schritte. Für Kenni: Die Review-Session lässt jeden Block vor dem Attestieren von einem frischen Subagenten bewerten (günstiges Modell genügt); Kennis Refute-Panel kann schmaler werden (Steward-Brief, Punkt 2).

## v2.55.0 — Review-Gate prüft Inhalt statt Historie · 2026-10-08

**Warum.** Das Gate leitete aus der Commit-Historie ab, ob ein Review noch gilt, und ließ geprüfte Arbeiten nach einer Integration als ungeprüft dastehen; in Kenni lagen drei Arbeiten mit Registry-Änderung auf einem Branch. Zudem ging eine Konfliktauflösung auf die eigene Seite durch, auch wenn sie `main`s Änderung verwarf.

**Was sich ändert.**
- Eine Datei am gepushten Tip gilt als geprüft, wenn ihr Inhalt git's Merge aus Integrationszweig und geprüften Heads entspricht; kollidierende Pfade gelten nie als geprüft.
- Ein konfliktfreier Rebase oder Merge von `main` lässt ein Review mit Fork-Point-Basis gültig (#158), und sauber mergbare geprüfte Arbeiten gelten zusammen als geprüft.
- Strenger: Jede Konfliktauflösung braucht eine neue Runde, und ein Commit, der eine geprüfte Datei auf `main`s Stand zurücksetzt, ist ungeprüft.
- Jeder git-Fehler bedeutet „veraltet“ (fail closed); der schwächere `--cc`-Ersatz nach gescheitertem `merge-tree` entfällt.
- `/review` sagt jetzt: Rebase oder Merge von `main` vor Runde 1; eine spätere konfliktfreie Integration behält das Review.

**Wirkung.** Nur noch echte Konflikte kosten eine neue Review-Runde. Ein Urteil dauert median 0,05 s statt 25 s, und rund 400 Zeilen Gate-Code samt 28 Tests entfallen.

**Update.** Voraussetzung ist git 2.38 oder neuer (`merge-tree --write-tree`). Für Kenni: Branches mit Konfliktauflösung brauchen eine neue Runde, ein konfliktfreier Rebase nicht mehr.

Details: [Plan](docs/analysis/2026-10-07-review-gate-teardown.md) #158, Kenni #2439

## v2.54.2 — Review-Gate ohne Timeout auf großer Historie · 2026-10-08

**Warum.** In Kenni lief das Review-Gate 936 s und wurde vom Gate-Runner nach 600 s abgebrochen; der Zug stand mit vier fertigen Kandidaten stundenlang.

**Was sich ändert.** Die Stale-Prüfung fragt git jede Tatsache nur einmal pro Lauf, und ein abgebrochenes Gate nennt die laufende und die längste fertige Phase.

**Wirkung.** In Kenni sank der Lauf auf einem gepushten Bereich von 900 Commits von 172 s auf 92 s, die Stale-Prüfung von 39 s auf 7,5 s. Ein Timeout liest sich jetzt als Leistungsproblem mit benannter Phase statt als Urteil.

**Update.** Keine Schritte. Für Kenni: Den lokalen Patch aus #2436 an `check_review.py` und `gate_runner.py` mit dem Update fallen lassen (eigene Gate-Code-Änderungen wären sonst eine Tier-3-Migration).

Details: #182, Kenni #2436

## v2.54.1 — Commands und Prompts nennen Inventar- und REVIEW-Regel · 2026-10-07

**Warum.** Die Regel „ein Owner pro Akzeptanzkriterium“ stand nur in Modul-Doku und Review-Checkliste, das Review fand Verstöße erst eine Runde später. Der Copilot-Review-Prompt und `AGENTS.md` ließen die `REVIEW`-Zeile von Hand schreiben, ohne `base` und `head` aus dem Bundle.

**Was sich ändert.** `/execute` und der Copilot-Execute-Prompt nennen die Owner-Regel, und Copilot-Review-Prompt und `AGENTS.md` schreiben die `REVIEW`-Zeile mit `attest.py`.

**Update.** Keine Schritte.

## v2.54.0 — Zwei Gates weniger, ein Owner pro Akzeptanzkriterium · 2026-10-07

**Warum.** In Kenni standen in einem Monat 12 `GRADE`-Zeilen gegen 126 `REVIEW`-Zeilen, und was sie messen sollten, lesen `rounds` und `models` bereits aus den Review-Records. Das Gate `ac-text-drift` verglich den Text eines Kriteriums in Spec und Inventar, weil beide ihn trugen.

**Was sich ändert.**
- Das GRADE-Gate entfällt samt `process_kpis.py convergence` und Rework-Zählung in `cost`; `workflow.md`, die Tasks-Vorlage und `speckit.md` verlangen keine `GRADE`-Zeilen mehr.
- Das Modul `telemetry` bleibt als Cockpit, alte Zeilen bleiben als Historie, ein Manifest mit `telemetry: true` bleibt gültig.
- Der Text eines Akzeptanzkriteriums hat einen Ort: bis zum Merge Spec oder Issue, danach das Inventar; sonst steht nur die ID.
- Die liefernde Änderung schreibt den Inventareintrag aus den finalen `AC-n`-Zeilen als letzten Schritt vor dem Review-Bundle.
- `ac-text-drift` entfällt; ob Eintrag und Spec zusammenpassen, prüft das Review (neue Frage in `review-checklist.md`).

**Wirkung.** Zwei Gates weniger, und kein Text steht mehr an zwei Orten, die sich auseinanderentwickeln können.

**Update.** Keine Schritte. Für Kenni: `test_process_kpis_process.py` und `test_human_digest_process.py` erwarten `check_telemetry.py` und die `convergence`-Ausgabe und müssen angepasst werden; das eigene `ac-text-drift`-Skript in `gates.local.json` bleibt unberührt.

## v2.53.0 — Schlankeres Review-Gate: Digest und Ankerkette entfallen · 2026-10-07

**Warum.** `diff=<sha256>` war `sha256(git diff base head)`, also eine Funktion der beiden SHAs in der Zeile, und brauchte Nachrechnen, Integritäts-Ledger, Cache und Fetch-Stempel. Auch die Delta-Ankerkette bei Tier 3 brachte dem Gate mehr Code als Prüfwert.

**Was sich ändert.**
- Diff-Digest, Integritäts-Ledger und `PROCESS_REVIEW_INTEGRITY`/`--full` entfallen; `attest.py` schreibt nur `base` und `head` und prüft den Fork-Point.
- Delta-Bundles (`--since`) sind auf jedem Tier eine Lesehilfe, das Verdict bindet immer den ganzen Branch; `mode=delta` und die Tier-3-Ankerkette entfallen.
- Ein leeres Delta wird benannt, ein `--since` ohne Commit und ein älteres Delta-Bundle werden verweigert.
- Ein stehender Block wird am Tip gelesen; ein vom Bereich gelöschter Block-Eintrag steht nicht mehr.
- Altdaten bleiben gültig: Zeilen mit `diff=` und `mode=` werden gelesen, die Felder ignoriert, und jede Zeile mit `base`/`head` gilt als volle Runde.

**Wirkung.** `check_review.py` sinkt von 3.080 auf 2.683 Zeilen, mit Bundle, `attest` und Tests fallen rund 1.450 Zeilen weg. Der Prüfer sieht bei einem leeren Delta nicht mehr keinen Code und bürgt trotzdem für den Branch.

**Update.**
1. Ein Branch, der beim Update mitten in den Review-Runden steckt, braucht ein Review vom Fork-Point; gemergte Zeilen bleiben gültig.

Details: [Plan](docs/analysis/2026-10-07-review-gate-teardown.md)

## v2.52.0 — Weniger Prozess-Mechanik: nur echte Fehler blocken · 2026-10-07

**Warum.** Gemessen in Kenni fiel die Zahl abgeschlossener Arbeiten mit Review von 70 (26.08.–08.09.) auf 18 (23.09.–07.10.), der Anteil blockender Reviews stieg von 5 % auf 33 %. Am 07.10. blockierte sich der Prozess mindestens sechsmal selbst, etwa als `attest` zwei `pass` verweigerte, weil `round=6` statt `round=5` in der Zeile stand (Kenni #2396).

**Was sich ändert.**
- Template-Updates mit release-gleichem Gate-Code sind keine Tier-3-Migration mehr (eigene Änderungen bleiben Tier 3); `releases.md` empfiehlt Updates alle zwei bis vier Wochen.
- `attest.py` verweigert keine Buchhaltung mehr: Zu hohe `--round` und falsch nummerierte `ROOT-CAUSE`-Zeilen sind nur Hinweise, und `--with <Bericht>` committet Bericht und Planzeilen mit der REVIEW-Zeile.
- Nur ein Fehler, auf den jemand stößt, darf blocken; Formulierungen sind `nit`, und minor- oder nit-Funde ergeben ein `pass` mit Restpunkten.
- Ab dem zweiten Block am selben Element entscheidet die Fix-Session über Inkrement oder Umbau; nach dem dritten entscheidet der Owner einmal endgültig.
- Beantwortete oder durchgestrichene `DECISION NEEDED`-Zeilen halten den Zug nicht mehr an, und Plan-, Review- und Brainstorm-Sessions starten auch bei belegter `scoped`-Lane (#177).
- Ein Push nur mit Prozessdatensätzen fährt die Prozess-Gates ohne Suite; der Tower zeigt `balance` und meldet `process-heavy` über 40 % Prozessanteil.

**Wirkung.** Weniger Selbstblockaden durch Buchhaltung und Formulierungen, und ein Template-Update kostet keine Tier-3-Runden mehr (v2.51.1 brauchte drei). Cross-Model-Review bei Tier 3, Refute vor der ersten Runde und der Zug mit voller Suite bleiben.

**Update.** Keine Schritte. Für Kenni: `review.local.md` §11 schickt bisher jede Runde nach der zweiten zum Owner und sollte stattdessen die eine Owner-Entscheidung pro Deckel übernehmen.

Details: #177, Kenni #2396, #2397, #2416

## v2.51.1 — Strikter Override-Guard und Korrekturen für Worktrees · 2026-10-07

**Warum.** Der Guard gegen `model:`-/`effort:`-Overrides in Phase-Dateien musste das Frontmatter so lesen wie Claude Code selbst (#173/#174), und mehrere Fehler traten in Kenni in Worktrees, bei `say`, bei der Slot-Zählung und bei Spec-Plänen auf.

**Was sich ändert.** `dispatch` liest das Phase-Frontmatter strikt ohne PyYAML und verweigert uneindeutige Overrides; dazu kommen Korrekturen für Worktrees, `say`, Slot-Zählung und Spec-Pläne.

**Update.** Keine Schritte. Für Kenni: Die lokale Abweichung aus #2393 mit dem Update fallen lassen.

Details: #170, #173, #174, #175, Kenni #2399, #2405, #2411, #2412, #2414

## v2.51.0 — Effort pro Policy-Zelle, Tier-3-Review auf Opus xhigh · 2026-10-05

**Warum.** Eine Zelle in `model-policy.json` war nur ein Modellname, ohne Effort und ohne eigenen Startbefehl. Zudem setzte in Kenni ein `model:`-Override im Frontmatter einer Command-Datei Pläne wochenlang still auf ein anderes Modell (#2317, #2299).

**Was sich ändert.**
- Eine Zelle in `model-policy.json` ist ein Modellname oder `{"model": …, "effort": …, "command": …}`; `model-policy.local.json` ersetzt sie ganz.
- Effort-Stufen sind `minimal`, `low`, `medium`, `high`, `xhigh`, `max`.
- Der Startbefehl kennt `{effort}` und lässt sich pro Zelle setzen (Zelle > `phases.<phase>.command` > `command`), etwa um nur das Tier-3-Review auf Codex laufen zu lassen.
- Das Tier-3-Review läuft statt auf `claude-fable-5-1` auf `{"model": "claude-opus-5", "effort": "xhigh"}`, die Attestierung ist damit `single-family`.
- `dispatch start` verweigert, wenn die Command-Datei `model:` oder `effort:` im Frontmatter setzt (`inherit` ausgenommen); ein Template-Test hält alle Dateien frei davon.
- Worker bekommen `PROCESS_EFFORT`, Berichte weisen den Effort aus, und der Tower meldet mit `transcripts` in der Policy Modell-Drift.

**Wirkung.** Modell, Effort und Startbefehl sind pro Aufgabenklasse, Tier oder Phase wählbar, ein stiller Modell-Override ist nicht mehr möglich, und Modell-Drift wird sichtbar.

**Update.**
1. Projekte mit eigenem `command` in der lokalen Policy ergänzen `--effort={effort}` oder setzen die Tier-3-Review-Zelle lokal, sonst verweigert `dispatch start`.
2. Command-Dateien mit `model:` oder `effort:` im Frontmatter bereinigen.

Details: Kenni #2317, #2299, #2244, #2247

## v2.50.1 — Sichere Template-Quelle, Spec-Bereinigung ohne Datenverlust · 2026-10-05

**Warum.** `template_update` reichte eine ungeprüfte Quelle an Copier weiter (mit `GIT_ALLOW_PROTOCOL=ext` ausführbar), und die Spec-Bereinigung konnte Spec-Ordner löschen, auf die Code noch verweist (Kenni #2382). Ablehnungen des Prozesses sagten außerdem nicht, was zu tun ist.

**Was sich ändert.** `template_update` prüft die Quelle gegen die Allowlist, die Spec-Bereinigung löscht keine noch referenzierten Spec-Ordner mehr, und Ablehnungen nennen den Ausweg.

**Update.** Keine Schritte.

Details: #166, #167, #168, #169, Kenni #2382

## v2.50.0 — Gate prüft die Basis einer vollen Review-Runde · 2026-10-05

**Warum.** Seit v2.49.1 schreiben `attest.py` und das Bundle eine volle Runde nur gegen den Fork-Point, das Gate prüfte die Basis bestehender Einträge aber nicht (#160). Außerdem prüfte es das Template am Arbeitsbaum statt am committeten Stand (#161).

**Was sich ändert.**
- Ein `mode=full`-REVIEW-Eintrag zählt nur, wenn seine Basis der Fork-Point von Kopf und Integrationszweig ist; ein falscher Eintrag ist eine fehlerhafte Zeile.
- Ein lokal vorgespultes oder gefälschtes `main`/`master` umgeht die Prüfung nicht; ohne Integrations-Ref gibt es eine Meldung (beim Integrations-Push hart).
- Das Gate prüft das Template immer am committeten Stand; `template_verify --ack` arbeitet am Arbeitsbaum, und ein Ack zählt erst nach dem Commit.
- Auf macOS nennen Git-Befehle der Template-Prüfung den gemeinsamen Bare-Clone per `--git-dir`, `safe.bareRepository=explicit` blockiert sie nicht mehr.
- Das Bundle warnt beratend vor „Übergangstabelle fehlt“: Ein Plan nutzt Zustandsvokabular ohne Abschnitt `## Transitions`; eigene Wörter per `transitions-vocabulary: …` in `review.local.md`.
- Ein zweiter Hinweis, „Regression-Pin fehlt“, erscheint, wenn ein Delta-Bundle Code, aber keine Testdatei ändert.

**Wirkung.** Eine gefälschte Basis zählt nicht mehr als volle Runde; gegen Kennis Journal (1079 Einträge) entsteht auf main kein neuer harter Fehler. Die Wirkung der beiden Hinweise ist noch nicht gemessen.

**Update.** Keine Schritte. Gemergte Alt-Einträge werden nicht geprüft; Einträge außerhalb des gepushten Bereichs nennt eine einzige Sammelnotiz.

Details: #160, #161, #163

## v2.49.1 — Eine Merge-Basis oder keine, Template-Quelle abgesichert · 2026-10-05

**Warum.** Bei mehreren Merge-Basen wurde still eine gewählt (Kenni #2381), und eine Template-Quelle wie `--upload-pack=…` erreichte einen Git-Aufruf. Kenni hatte dazu in #2352 lokale Fixes gemacht, die jetzt auf den aktuellen Code übertragen sind.

**Was sich ändert.** Keine oder mehrere Merge-Basen sind jetzt ein Fehler, und die Template-Prüfung weist ungültige Pfade und nicht erlaubte Quellen ab.

**Update.** Keine Schritte. Für Kenni: Das lokale Delta aus #2352 mit dem Update ablösen (#2383).

Details: #160, #161, Kenni #2352, #2381, #2383

## v2.49.0 — Warten ohne Abfragen, Berichte aufräumen, Modell pro Klasse · 2026-10-05

**Warum.** Kenni hält 58 MB in 983 Berichtsdateien unter `.process-work/reviews/`, die das Gate bei jedem Lauf liest. `/steward` wartete über einen harness-eigenen Monitor auf neue Reports, und mechanische Teilaufgaben ließen sich nicht gezielt auf ein günstigeres Modell legen (#157).

**Was sich ändert.**
- `tower.py --wait` blockiert ohne Modell-Turns, bis ein Report mit einem der `--states` kommt, und gibt ihn als JSON aus; `/steward` nutzt es.
- `--json --section NAME` gibt nur die genannten Teile des Lagebilds aus.
- `tidy.py` entfernt nur Berichte abgeschlossener Arbeit (letztes Urteil `pass`), die älter als `--days`, nicht die neuesten und von keinem Plan oder Journal genannt sind.
- `tidy.py` löscht nur per `git rm` getrackte, mit HEAD inhaltsgleiche Berichte; ohne `--apply` listet es nur mit Größen.
- Nach der ID trägt eine Aufgabe ein Klassen-Token (`[mechanical]`, `[design]`, eigene aus `classes`), das vor Tier und Phase gilt; `dispatch.py policy --class C` nennt das Modell.
- Jeder Subagent-Aufruf nennt sein Modell, der Harness-Standard ist keine Wahl (`tower.md`); Review und Refute folgen weiter dem Tier.

**Wirkung.** Das Warten kostet keine Modell-Turns, Berichtsordner wachsen nicht unbegrenzt, und mechanische Teilaufgaben laufen auf dem günstigeren Modell. Die Wirkung der Klassen ist pro Klasse noch nicht messbar, die Token-Summe pro Issue aus v2.48 zeigt nur die Gesamtwirkung.

**Update.** Keine Schritte.

Details: #157

## v2.48.0 — Tier-3-Folgerunden als Delta, Verbrauch sichtbar · 2026-10-05

**Warum.** Ein Tier-3-Paket downstream brauchte 5 Runden mit je 3 Prüflinsen auf vollen Bundles von 10.400–13.100 Zeilen, weil Tier 3 kein Delta kannte (#155). Die Template-Prüfung klonte außerdem bei jedem Lauf neu (Kenni #2375).

**Was sich ändert.**
- Eine Tier-3-Folgerunde darf ein Delta-Bundle nutzen, wenn sie auf einer vollen Runde für genau diesen Stand oder einer lückenlosen Delta-Kette aufsetzt, sonst zählt es nie als Pass.
- Ein volles Bundle wird erzwungen, wenn das Delta Gate-Code, Vertragspfade, Entscheidungen oder das Tier ändert oder eine im Anker-Bericht nicht genannte Datei berührt.
- Eine Prüflinse läuft in der Folgerunde nur erneut, wenn sie offene Funde hat oder eine berührte Datei nennt.
- `/execute` prüft vor dem Push auch Host-Fähigkeiten, Zugangsdaten und Integrations-Fixtures aus dem Plan; was sich nicht prüfen lässt, ist `DECISION NEEDED`.
- Jeder Report trägt ein Modell; `/finish` nennt die Output-Tokens des Issues (Policy-Schlüssel `transcripts`) und schreibt den `done`-Report selbst, `process_kpis.py cost --issue N` zeigt sie auch.
- Die Template-Prüfung nutzt einen gefilterten Klon pro Prozess statt zwei `ls-remote` plus vollem Klon; offline scheitert sie weiter hart.

**Wirkung.** Tier-3-Folgerunden prüfen den Fix statt über 10.000 Zeilen, der Verbrauch pro Issue ist sichtbar, und die Template-Prüfung klont seltener. Die Wirkung ist noch nicht gemessen; Vergleich über `process_kpis.py rounds` und die neuen Token-Zahlen auf der nächsten Tier-3-Arbeit.

**Update.** Keine Schritte.

Details: #155, Kenni #2375

## v2.47.0 — Weniger Review-Runden: Fehlerkatalog und Fragen im Vorfeld · 2026-10-05

**Warum.** In Kenni standen 386 Review-Einträge in drei Wochen, 38 % davon Blocks, und Tier-3-Features brauchten 3–7 Runden. Ein zweites Projekt hatte 10 Blocker, 6 aus dem ersten Entwurf, 2 durch einen Fix und 2 spät gefunden.

**Was sich ändert.**
- `docs/process/failure-catalog.md` ist der eine Ort der Fehlerklassen: die sechs bisherigen aus `refute.md` plus elf neue, je mit Eingabeform, Test und Helfer.
- Die Bedrohungsfrage der Design-Vorlage gilt bei Tier 3 und bei Tier 2 mit hohem Risiko (Gate-Code, Datenverlust, Autorisierung, Migration, Nebenläufigkeit).
- Neu ist der Abschnitt „Transitions“ für Zustandsautomaten, mit Tests je Zeilenklasse und Negativtests (`/execute`); `/plan` inventarisiert bei geänderter Tatsachenberechnung jeden Leser.
- Runde 1 nennt alle Blocker; eine Folgerunde prüft Fix, offene Funde und die Fehlerklasse überall und verlangt bei geändertem Vertrag oder Risikoumfang ein volles Bundle.
- Bei Tier 2 beantwortet das Review die Fragen des Refuters selbst, ein eigener Refute-Lauf nur bei Datenverlust oder Nebenläufigkeit; ab Tier 3 und für Gate-Code bleibt er.
- `process_kpis.py rounds` zeigt je Arbeit Tier, Runden und Blocker nach Ursprung; FINDING-Zeilen haben das optionale Feld `origin=draft|fix|late`.

**Wirkung.** Fehlerklassen werden im Plan abgefragt statt in der dritten Runde gefunden, und Tier 2 spart den eigenen Refute-Lauf. Die Wirkung ist noch nicht gemessen; Vergleich über `rounds` auf den nächsten vergleichbaren Lieferungen.

**Update.** Keine Schritte.

## v2.46.0 — Session-Kontext auf die aktuelle Arbeit begrenzt · 2026-10-05

**Warum.** Beim Start las `process_context.py` alle Pläne und Specs ein, auch die fremden; im Referenzprojekt (43 aktive Pläne, 91 Spec-Ordner) war das der Großteil des Kontexts, nach einer Kompaktierung ebenso bei `rehydrate.py`.

**Was sich ändert.**
- `process_context.py` zeigt nur die aktuelle Arbeit vollständig (per `--issue N`, Branch-Name oder Issue im Branch), alle anderen Pläne und Specs als Index; ohne Zuordnung nur den Index mit Hinweis auf `--issue N`.
- `--all` liefert die bisherige Ausgabe; `--cost` misst weiter über alles und trennt `mandatory` von `available`.
- `rehydrate.py` zeigt nach der Kompaktierung ebenso nur die aktuelle Arbeit vollständig, der Rest steht als höchstens 10 Indexzeilen.
- `publish_and_prune --stage` verweigert Formen wie `GH-12`, statt die Issue zu raten.
- `tools/release.py` startet die volle Suite parallel, wenn pytest-xdist installiert ist (gemessen 465 s); sonst läuft sie seriell.
- doc-drift meldet einen Verweis auf eine fehlende optionale `*.local.*`-Datei nicht mehr als Drift.

**Wirkung.** Im Referenzprojekt sinkt `process_context` von 428.644 auf etwa 19.000 Zeichen (−96 %) und `rehydrate` von 84.359 auf 6.973 (−92 %). Nichts fällt still weg, der Rest bleibt im Index.

**Update.** Keine Schritte.

Details: #140

## v2.45.0 — Tag und Release nur nach grüner CI, weniger Doppelprüfungen · 2026-10-03

**Warum.** Tag und Release liefen ohne jede Suite und konnten CI umgehen. Zugleich prüfte der Prozess doppelt: Linux lief als `portable-smoke` neben dem Job `test`, und `fix-streak` wurde bei jedem Gate-Lauf neu berechnet.

**Was sich ändert.**
- `portable-smoke` läuft nur noch auf macOS und Windows; Linux deckt der Job `test` ab.
- Vor Tag und Release verlangt `tools/ci_evidence.py` einen erfolgreichen `push`-Lauf von `ci.yml` auf `main` für exakt den Ziel-Commit.
- `release-tag.yml` (auch bei `replace`) und `release-publish.yml` prüfen das und laufen nur noch von `main`.
- Eine nicht-hexadezimale `sha` bricht ab, statt still HEAD zu taggen.
- `fix-streak` ist kein Gate mehr; das Review-Bundle enthält den Hinweis einmal pro Runde als Abschnitt „Fix streak“, die Regeln 4 und 6 bleiben.
- `tools/release.py` behält den lokalen Lauf, `--no-suite` bleibt Opt-in, und die Remote-Schritte nennen das Warten auf CI auf `main`.

**Wirkung.** Tag und Release können CI nicht mehr umgehen. Der Wegfall des Linux-Smoke spart pro CI-Lauf etwa 16 s Runner-Zeit plus Einrichtung; verloren geht nur die `::error::`-Annotation für Linux-Fehler.

**Update.**
1. Ist `portable-smoke (ubuntu-latest)` ein Required Check, ihn aus der Branch-Protection nehmen.

## v2.44.1 — Ein Owner für Aufgaben-Zuschnitt und `[P]` · 2026-10-03

**Warum.** Die Doku widersprach sich: `/execute`, `workflow.md`, die Tasks-Vorlage und die Speckit-Moduldoku verlangten „ein atomarer Commit pro Task“, `/plan` und `commits.md` erlaubten zwei Commits.

**Was sich ändert.** Überall gilt: Eine Aufgabe ist fertig, wenn ihr Verhalten grün ist (ein oder zwei Commits), und `/plan` ist einziger Owner für `[P]`.

**Wirkung.** Der Commit-Widerspruch und die verstreuten `[P]`-Regeln sind weg; es gibt kein neues Gate und keine neue Phase.

**Update.** Keine Schritte.

## v2.44.0 — Fehler früher vermeiden, ohne neue Pflichtschritte · 2026-10-03

**Warum.** Vorhandene Prozessschritte widersprachen sich: `/execute` verbot, was „Check existing code first“ verlangte, die Tasks-Vorlage stand gegen `/plan`, `testing.md` gegen sich selbst, und die Speckit-Doku gegen ein Gate, das jede Begleitdatei hart scheitern ließ.

**Was sich ändert.**
- Spec Kit kennt eine Aufgabe pro Verhalten (Test, Rot, Umsetzung, Grün); Vorlage, Gate-Meldung, Doku und Constitution sagen dasselbe.
- Bestehende Pläne mit getrennten Test- und Umsetzungsaufgaben bestehen das Gate weiter, eine Story ohne Testbezug fällt weiter durch.
- Die Inventur bei Umbenennen, Entfernen und Verschieben gehört in die Aufgaben des Plans; `/execute` gleicht vor dem Push nur den Diff mit dem Plan ab.
- `/execute` liest vor dem Anlegen oder Ändern einer Regel, eines Parsers oder Helfers den bestehenden Owner samt Aufrufern und Tests.
- Das Clarification-Gate blockiert nur bei offenen Markern in `plan.md` und `tasks.md` und bei Lesefehlern; Marker in Begleitdateien wie `research.md` sind nur Hinweise mit Datei und Zeile.
- E2E nach Risiko statt Stückzahl: „One per feature — floor AND ceiling“ entfällt, geänderte kritische Verträge brauchen einen passenden Nachweis.

**Wirkung.** Fehler fallen im Plan statt kurz vor dem Push auf, Begleitdateien blockieren nicht mehr; es kommen keine Pflichtabschnitte, Gates oder Review-Runden hinzu. Die Einsparungen sind erwartet, nicht gemessen.

**Update.** Keine Schritte.

## v2.43.2 — Sichere automatische Template-Prüfung, geprüftes Aufräumen · 2026-10-02

**Warum.** Beim automatischen Rendern der Provenienz konnten lokal als vertrauenswürdig markierte Jinja-Erweiterungen vor dem Review laufen, und das Aufräumen von Worktrees konnte ignorierte Arbeit entfernen, die erst nach der ersten Freigabe entstanden war.

**Was sich ändert.** Das automatische Rendern überspringt Tasks und läuft ohne Trust, und vor dem Entfernen eines Worktrees wird die Keep-Policy mit frischen Records neu geprüft.

**Wirkung.** Lokal vertraute Erweiterungen laufen nicht mehr vor dem Review, und später entstandene ignorierte Arbeit bleibt erhalten. Externe Schreibzugriffe während der Prüfung und das Git-Löschen bleiben nicht atomar.

**Update.** Keine Schritte.

## v2.43.1 — Doku zu verifizierten Template-Updates aktualisiert · 2026-10-02

**Warum.** Übersichten und Review-Hinweise passten nicht mehr zum aktuellen Template.

**Was sich ändert.** Die englische und deutsche Übersicht (samt deutschem PDF) sowie die Review- und Tier-Hinweise beschreiben jetzt Owner-Bestätigung, Update-Provenienz, Review des Projekt-Deltas und Durchsetzungs-Migrationen.

**Wirkung.** Nur Doku, keine Änderung des Laufzeitverhaltens.

**Update.** Keine Schritte.

## v2.43.0 — Verifizierte Template-Updates, schnellere CI · 2026-10-02

**Warum.** Ein Template-Update hätte sonst samt freigegebener Template-Dateien erneut durch das Review gemusst, obwohl nur das Projekt-Delta neu ist. Die CI-Tests brauchten außerdem 322 Sekunden.

**Was sich ändert.**
- Beide gepinnten Template-Releases werden gegen die vertrauenswürdige Quelle neu gerendert und mit den Projektdateien verglichen; verlorene lokale Anpassungen bleiben Projekt-Delta.
- Ein reines, vom Owner bestätigtes Template-Update passiert ohne erneutes Review der Template-Dateien.
- Das Projekt-Delta braucht ein frisches, digest-gebundenes Tier-2-Review; Gate-Skripte, Helfer und Konfiguration bleiben Tier 3.
- Eigene und lokale Dateien, Hooks, Makefiles sowie geänderte oder gelöschte Tests bleiben im Projekt-Review; gefälschte Provenienz gibt keine Ausnahme.
- CI-Tests laufen mit zwei Workern, gruppiert nach Testdatei.
- Audit-Reste: `prime` liest Inbox-Inhalt in allen drei Harness-Adaptern, die Sprachprüfungen decken jedes Modul ab, der Gate-Workflow nennt seinen Required Check.

**Wirkung.** Der Review-Aufwand eines Updates beschränkt sich auf das Projekt-Delta; die CI-Laufzeit sinkt gemessen von 322 auf 183 Sekunden.

**Update.**
1. Baseline und Ziel als Release-Tags oder volle Git-SHAs eintragen; ungepinnte Angaben werden verweigert.
2. Die Update-Reihenfolge aus `docs/process/releases.md` befolgen, berechnetes Delta und Behavior Notes beilegen.
3. Die Owner-Bestätigung committen.

## v2.42.0 — Downstream-Fixes im Integrationsweg, Worker-Kanäle · 2026-10-02

**Warum.** Nach früheren Releases blieben im Referenzprojekt Restfehler in Integration und Review (#142). Unter Windows konnte außerdem die Ausgabekodierung der Gate-Subprozesse von der des Runners abweichen.

**Was sich ändert.**
- Integration und Review sind gehärtet: Integrationsbereiche scheitern geschlossen, die Review-Abdeckung wird gepoolt, Nicht-Fast-Forward-Pushes sind geschützt.
- Neu sind ein vom Owner freigegebener Übergang von Brainstorm zu Plan, die Diagnose widersprüchlicher oder toter Worker und additive projektlokale tower-Findings.
- `finish` arbeitet sicher über Worktrees und Archiv-Batches, und die Modell-Policy bestimmt die Phasenwahl.
- Der Push-Timeout des Zugs ist konfigurierbar (Standard 30 Minuten), damit lange Pre-Push-Gates möglich sind (#83).
- Worker-Kanal-Events und das Steward-Restart-Feedback sind dokumentiert (#139).
- Gate-Subprozesse geben UTF-8 aus.

**Wirkung.** Die Integration bricht bei unlesbarem Stand ab, statt zu raten, und lange Gates scheitern nicht mehr am Push-Timeout.

**Update.**
1. Bundle-Producer, Attestation-Writer und Review-Gate gemeinsam aktualisieren; neue Delta-Attestierungen tragen `mode=delta`, bestehende Full-Review-Records bleiben gültig.
2. Vor einem geschützten Push den Remote-Default-Branch fetchen; Nicht-Fast-Forward-Integrationspushes brauchen eine benannte Owner-Ausnahme.

Details: #142, #83, #139

## v2.41.0 — Gemergte Worktrees werden entfernt, nie Arbeit · 2026-10-01

**Warum.** Im Referenzprojekt blieben 111 Dispatch-Worktrees nach dem Merge stehen, jeder mit eigenem venv und `node_modules`, zusammen etwa 57 GB. Die Platte lief voll, und alle Sitzungen standen still.

**Was sich ändert.**
- Der Zug entfernt die Worktrees gemergter Branches nach dem erfolgreichen Push und nennt jeden behaltenen mit Grund.
- `tidy.py` listet gemergte Worktrees mit Größe, `tidy.py --apply` entfernt sie.
- Ein Worktree bleibt stehen, wenn er Arbeit tragen könnte, etwa durch uncommittete, unversionierte oder nicht regenerierbare ignorierte Dateien oder eine laufende Sitzung.
- `dispatch.py start` verweigert ab 90 % Plattenbelegung und nennt den Aufräumbefehl (`PROCESS_DISK_LIMIT_PCT`).

**Wirkung.** Die Platte läuft nicht mehr durch Altlasten voll, ohne dass ungesicherte Arbeit verloren geht.

**Update.** Keine Schritte.

Details: #136

## v2.40.1 — Hinweise nennen den Hook-Installer des Projekts · 2026-10-01

**Warum.** Das Referenzprojekt verwaltet seine Hooks in `.githooks/` ohne das git-hooks-Modul, doch Hook-Doktor und Doku schickten es zu `scripts/process/install_hooks.py`; `tower.md` riet außerdem noch zu `model-policy.json` in `.process-owned`, was seit v2.39.0 überholt ist.

**Was sich ändert.** Der Reparatur-Hinweis nennt den Installer des Projekts (`scripts/install_hooks.sh`, ein `make hooks`-Ziel, sonst `git config core.hooksPath .githooks`), und `tower.md` verweist auf `model-policy.local.json`.

**Update.** Keine Schritte.

Details: #134

## v2.40.0 — Letzte Projekt-Abweichungen geprüft ins Template übernommen · 2026-10-01

**Warum.** Nach dem Port auf v2.39.0 hatte das Referenzprojekt keine eigenen Dateien mehr, aber vier nicht-eigene Dateien trugen noch eigene Änderungen, die ein künftiges Update überschrieben hätte.

**Was sich ändert.**
- doc-drift prüft jetzt den Pfad in `` `pfad/datei.py::symbol` ``-Zeigern, sodass veraltete Zeiger auffallen.
- Der Owner-Digest nennt jede `<gate>-waived:`-Zeile, auch den Waiver eines projekteigenen Gates (`gates.local.json`).
- `check_architecture` und `check_issues` deklarieren PyYAML (PEP 723).
- Die Markierung `doc-drift-base` des Referenzprojekts wurde nicht übernommen, weil sie dort ungenutzt ist und im Review schon einmal als Umgehung entfernt wurde.

**Wirkung.** Das Referenzprojekt muss keine eigenen Änderungen an diesen Dateien mehr tragen. Die beiden Skripte laufen allein gestartet auch ohne installiertes PyYAML.

**Update.** Keine Schritte. Wer Symbol-Zeiger in geprüften Dokumenten hat, kann nach dem Update tote finden.

## v2.39.0 — Lokale Erweiterungspunkte und ein Wächter vor main · 2026-09-30

**Warum.** Im Referenzprojekt standen 14 Dateien in `.process-owned`, jede ein Handport bei jedem Release. Eine Inventur sortierte jede Abweichung ein.

**Was sich ändert.**
- `docs/process/gates.local.json` nimmt eigene Gates auf (`{name: {module, command}}`); ein Modul-Gate darf gleichnamig ersetzt werden, ein Kern-Gate nicht.
- `docs/process/model-policy.local.json` wird Mapping für Mapping über `model-policy.json` gelegt.
- `docs/process/review.local.md` trägt eigene Review-Dimensionen, die das Review nur schärfen, nie schwächen.
- Ein Push nach `main` braucht den Weg des Zugs oder von `finish.py` (`PROCESS_MERGE_ROUTE`) oder eine benannte, protokollierte Owner-Ausnahme.
- Ein `block` im gepushten Bereich hält den Merge-Push auf, bis ein späterer `pass` für dieselbe Arbeit vorliegt (Standing Block).
- `attest.py --archive` verschiebt mit dem `pass` den eigenen Plan ins Archiv, `--commit` macht daraus einen Commit nur dieser Pfade.

**Wirkung.** Das Template übernimmt die Upstream-Kandidaten und bietet für den Rest drei lokale Dateien; danach kann `.process-owned` leer sein. Ein Push nach `main` läuft nur noch über einen benannten Weg.

**Update.** Keine Schritte.

## v2.38.0 — Frühere Umbau-Frage, gemessene Belege, Release als Skript · 2026-09-30

**Warum.** Eine Retrospektive im Referenzprojekt zeigte: Ein Wächter brauchte vier Review-Runden, obwohl alle Befunde ab Runde 2 dieselbe Ursache hatten. Rot-Belege und ROOT-CAUSE-Zeilen wurden von Hand geschrieben, mit Fehlern, und das Release bestand aus einem Dutzend Handschritten.

**Was sich ändert.**
- Der Fix-Streak-Check meldet schon den zweiten `fix`-Commit auf derselben Datei und verlangt eine DECISION „Inkrement oder Umbau“ vor dem nächsten Flicken.
- Der Refuter schreibt nach den Befunden eine Zeile MUSTER mit der gemeinsamen Ursache und dem einen Owner, der alle schließt, oder „no common cause“.
- `red_evidence.py` fährt eine pytest-Auswahl gegen den alten Stand und den Arbeitsbaum; nur ein im Aufruf gescheiterter Test zählt als „rot vorher“.
- `red_evidence.py` schreibt den Journal-Block und mit `--cause` die ROOT-CAUSE-Zeile und verweigert, wenn kein Test vorher rot lief oder danach etwas rot ist.
- `tools/release.py` erledigt den lokalen Teil eines Template-Releases in einem Lauf; `--check` meldet jede Stelle, die nicht auf der Version steht.
- Bekannt, nicht umgesetzt: Die REFUTE-Zeile wird noch nicht aus dem Refute-Bericht erzeugt (#124).

**Wirkung.** Die Frage nach dem Umbau kommt nach dem zweiten statt nach dem vierten Treffer, Belege werden gemessen statt getippt, und ein Release ist ein Skriptaufruf.

**Update.** Keine Schritte.

Details: #124

## v2.37.0 — Pfadnamen mit `-z` gelesen, „unlesbar“ ist nicht „leer“ · 2026-09-29

**Warum.** Ohne `-z` setzt git Namen mit Umlaut, Zeilenumbruch oder Tab in Anführungszeichen, und der zitierte Name trifft keine Datei. Im Referenzprojekt las der Zug so einen archivierten Tier-2-Plan als Tier 0, und der Branch stieg ohne Review ein.

**Was sich ändert.**
- Alle Prozess-Werkzeuge (Zug, tower, Review-Bündel, `dispatch`, `template_update` u. a.) lesen Pfadnamen mit `-z`.
- `template_update` setzt eigene Dateien und sucht Konfliktmarker jetzt namenssicher; vorher überschrieb ein Update eigene Dateien mit Umlaut im Namen.
- Kann git eine Liste nicht liefern, gilt sie nicht mehr als leer.
- Dann zählt das Review-Gate jeden aktiven Plan mit, `finish` blockiert, und der Zug lässt den Branch nicht einsteigen.
- tower meldet einen Branch mit unlesbarer Dateiliste als `paths-unknown`, `dispatch` antwortet dann „nicht zu sagen“.
- Bekannt, nicht behoben: Einige Stellen lesen einen git-Fehler weiter als „keine Pläne“ oder Größe 0, entscheiden aber keinen Merge.

**Wirkung.** Kein Branch steigt mehr ohne Review ein, weil ein Plan unter einem Sonderzeichen-Namen unlesbar war. Ein Update überschreibt keine eigenen Dateien mit Umlaut im Namen mehr.

**Update.** Keine Schritte.

## v2.36.0 — Worker fragen den Steward, tower sieht unbeantwortete Fragen · 2026-09-29

**Warum.** Im Referenzprojekt stand die Frage eines Workers an den Owner sechs Stunden unbeantwortet im Chat. Außerdem setzt git Plannamen mit Umlaut in Anführungszeichen, wodurch `finish` einen Tier-2-Plan ohne Review als fertig meldete und das Review-Gate den Merge-Push eines Tier-3-Plans ohne Nachweis durchließ.

**Was sich ändert.**
- Der Steward ist der Entscheidungspartner; der Worker fragt den Owner nur bei Produktgrundsätzen oder destruktiven Schritten.
- Eine Frage kommt als `DECISION NEEDED` mit `blocked` in den Plan, nie in den Chat; den Live-Kanal nennt die Policy (`decision_channel`).
- `/execute` hat vor `pushed` vier neue Pflichten, darunter eine mit `attest.py --dry-run` geprüfte `ROOT-CAUSE`-Zeile nach einer blockierten Runde.
- tower meldet einen lebenden Worker, der seit 30 Minuten nichts ausgibt, als `waiting-for-input` (Frage geleitet) oder `question-unrouted`.
- tower liest Pfade NUL-getrennt und gibt Namen, die kein UTF-8 sind, maskiert aus.
- Bekannt, nicht behoben: Weitere Werkzeuge lesen Pfade noch ohne `-z` (Folgearbeit in v2.37.0), und ein Worker auf einem anderen Host zeigt hier keinen Bildschirm.

**Wirkung.** Fragen landen dort, wo sie jemand liest, und tower zeigt eine unbeantwortete sofort. Pläne mit Umlaut im Namen laufen nicht mehr am Review vorbei.

**Update.** Keine Schritte.

## v2.35.0 — Der Zug kennt die Issue eines Paket-Branches · 2026-09-29

**Warum.** Ein Branch, der nach einem größeren Issue benannt ist (`<epic>-<paket>-…`), aber unter dem Issue seines Pakets geprüft wurde, stieg nie in den Zug ein, weil sein Name nur die Nummer des Epics trägt.

**Was sich ändert.**
- Eine Stelle beantwortet „zu welcher Issue gehört der Branch“, und der Zug fragt sie beim Einsteigen, bei den Plänen und beim `Closes #N` des Merges.
- Eine im Worker-Bericht selbst gemeldete Issue zählt dabei nicht.
- Nach dem Merge entfernt der Zug die Einträge und toten Records der Issues des Branches; ein wiederverwendeter Branch-Name erbt keine alten Issues.
- Wer Issue-Map und Records liest, legt kein Verzeichnis an, fragt keinen Worker ab und überspringt kaputte Einträge.
- Bekannt, nicht behoben: Ein außerhalb des Zugs gemergter Branch behält seine Einträge, bis seine Issue neu vergeben wird.
- Bekannt, nicht behoben: Ein zweiter, noch laufender Versuch auf einem anderen Branch verliert seine Zuordnung, sobald die Issue gemergt ist.

**Wirkung.** Paket-Branches steigen in den Zug ein, und ihr Merge schließt die richtige Issue; vorher stieg ein solcher Branch ein, schloss aber nichts.

**Update.** Keine Schritte.

## v2.34.0 — Ein Refuter ab Tier 2: Owner-Check zuerst, dann Grenzfälle · 2026-09-28

**Warum.** Refute war nur für Gate-Code Pflicht, hat sich aber darüber hinaus bewährt: Beim Stale-Check fand jede Runde echte Fehler, etwa die Hälfte davon aus der vorherigen Fix-Runde. Die teuersten Blocker im Referenzprojekt kamen von einem zweiten Owner einer Regel.

**Was sich ändert.**
- Refute ist nach Tier gestaffelt: Tier 0 keiner, Tier 1 optional, Tier 2 ein Lauf vor der ersten Review-Runde (Fix-Runde: Regressionstests), Tier 3 und Gate-Code nach jeder Fix-Runde erneut.
- Der Refuter prüft in fester Reihenfolge Owner-Check, Fehler-als-Erfolg, Grenzfälle und Stichprobe des Belegs; vorbestehende Funde werden Issues.
- Ein zweiter Owner sperrt auf jedem Tier, außer eine `DECISION` im Plan nennt den Grund.
- Das Review-Bündel warnt, wenn ein Plan ab Tier 2 keine eigene REFUTE-Zeile trägt.
- Tier und Verzicht eines Plans liest nur noch ein Owner, für Bündel und Gate gleich.

**Wirkung.** Fehler fallen vor statt in der Fix-Runde auf, Doppel-Owner werden zuerst gesucht, Preis ist ein zusätzlicher Refute-Lauf bei Tier 2. Bekannt, nicht behoben: Die Delta-Verweigerung zählt Design-Dokumente und Pläne mit Review-Verzicht noch mit, und `dispatch` liest den Tier noch mit eigener Logik.

**Update.** Keine Schritte.

## v2.33.1 — Verwerfen im Stale-Check, auch im Bereich anderer Reviews · 2026-09-27

**Warum.** Ein Review im Referenzprojekt zeigte: Der Bereich `base..head` eines anderen Reviews entschuldigte mehr als den Inhalt, den dieses Review gesehen hat, sodass ein Merge dort geprüften Code unbemerkt verwerfen konnte.

**Was sich ändert.** Der Stale-Check prüft Merges im Bereich eines anderen Reviews wieder auf Verwerfen; fehlen Basis oder Kopf, zählt alles seit der Abzweigung.

**Wirkung.** Verworfener geprüfter Code fällt auch im Bereich eines anderen Reviews auf; fünf Grenzfälle bleiben offen und sind dokumentiert.

**Update.** Keine Schritte.

## v2.33.0 — Belege, Zug-Urteil und dispatch gehärtet · 2026-09-27

**Warum.** Fünf Prozess-Baustellen kamen aus Befunden des Referenzprojekts: Belegzeilen wurden uneinheitlich gelesen, Suite-Urteil und Stale-Check des Zugs hatten Lücken, ein Zug-Merge schloss die Arbeit nicht ab, und `dispatch` war schwach abgesichert.

**Was sich ändert.**
- Eine Stelle legt fest, wo REVIEW-, ROOT-CAUSE- und REFUTE-Zeilen stehen; Beispiele, Kommentare und Platzhalter zählen nicht.
- Ein roter make-Aufruf bleibt rot, und „nicht vorhanden“ gilt nur für die eigene Datei oder das eigene Ziel der Suite.
- Fehlt die Suite nur im kombinierten Baum, wird das dem Passagier angelastet, der sie entfernt hat.
- Ein Zug-Merge archiviert eigene fertige Pläne und schließt die Issues dieses Repositorys per `Closes #N`; `plan-stays-active:` hält einen Plan offen.
- Im Stale-Check gilt Code als geprüft, den ein anderes Code-Review in seinem Bereich `base..head` gesehen hat; Plan-Reviews decken keinen Code.
- `dispatch`: `say` prüft die Zustellung, `chain` schiebt Phasen aus Berichten weiter, die Warteschlange ist gesperrt und dedupliziert, Worker laufen unter `nice` (`worker_nice`).

**Wirkung.** attest, Bündel und Gate werten Belege einheitlich aus, und ein Zug-Merge hinterlässt keine fertigen Pläne und offenen Issues. Jeder Fund ist mit einem Test belegt, der gegen die Vorfassung fällt, oder als bekannte Grenze dokumentiert.

**Update.** Keine Schritte.

## v2.32.5 — Stale-Check urteilt nach einer gepinnten Tabelle · 2026-09-26

**Warum.** Nach der dritten Flickung am Stale-Check wurden im Referenzprojekt Züge täglich abgelehnt; jetzt sammelt der Check Fakten aus git und urteilt nach einer gepinnten Tabelle.

**Was sich ändert.** Der Stale-Check zählt bei sauberen Merges nur noch, was über git's eigenen Merge hinausgeht, und bleibt bei fehlenden Daten oder versteckten Änderungen fail-closed.

**Wirkung.** Saubere Merges lehnen den Zug nicht mehr ab, böse Auflösungen und verworfene Reviews rutschen nicht durch.

**Update.** Keine Schritte.

## v2.32.4 — REFUTE-Zeile als Beleg, genauere Suite-Erkennung · 2026-09-25

**Warum.** Ein Review des Refute-Ports im Referenzprojekt blockierte, und ein frischer Agent fand danach mit rund 165 Szenarien drei Majors.

**Was sich ändert.** Eine REFUTE-Zeile braucht `round=<n>:`, Inhalt und die work-id ihres Plans, und die Erkennung von „Suite nicht vorhanden“ im Zug ist enger gefasst.

**Wirkung.** Nur echte REFUTE-Belege zählen, und die Zeile eines gestapelten Plans deckt keinen anderen.

**Update.** Keine Schritte.

## v2.32.3 — Der Zug nimmt nur Branches mit Review am Kopf mit · 2026-09-25

**Warum.** Ein Branch, den ein Zug schon gemergt hatte, stand nach neuen Commits im nächsten Zug als einstiegsbereit da, weil der alte Bericht `done` und der alte REVIEW-Pass weiter galten.

**Was sich ändert.** Ein Branch steigt in den Zug nur ein, wenn sein REVIEW-Pass den Kopf des Branches abdeckt und dahinter kein ungeprüfter Code steht.

**Wirkung.** Neue Commits nach einem Zug-Merge kommen nicht ohne neues Review in den nächsten Zug.

**Update.** Keine Schritte.

## v2.32.2 — Refute der Restbefund-Fixes aus v2.31.6/7 · 2026-09-25

**Warum.** Ein frischer Agent prüfte die Fixes aus v2.31.6/7 mit 27 Szenarien, 8 fielen durch.

**Was sich ändert.** Stale-Check und Suite-Erkennung des Zugs sind für Umbenennungen, saubere Merges, fehlende Vorbedingungen und weitere make-Varianten korrigiert.

**Wirkung.** Fehlalarme bei sauberen Merges entfallen, und der Zug-Bericht bleibt vollständig.

**Update.** Keine Schritte.

## v2.32.1 — Die REFUTE-Warnung hält dem eigenen Refute stand · 2026-09-25

**Warum.** Die Regel aus v2.32.0 wurde gleich auf ihre eigene Umsetzung angewandt: Ein frischer Agent fand an der REFUTE-Warnung drei Majors und drei Minors.

**Was sich ändert.** Die REFUTE-Warnung erkennt jetzt auch wegbewegte Dateien, mehr Gate-Pfade (u. a. `Makefile`, `.github/workflows/`) und Nicht-ASCII-Namen und ignoriert Beispielzeilen.

**Wirkung.** Die Warnung lässt sich weder über Umbenennungen noch über Beispielzeilen umgehen.

**Update.** Keine Schritte.

## v2.32.0 — Refute vor dem ersten Review für Gate-Code · 2026-09-25

**Warum.** Gate-Änderungen brauchten im Referenzprojekt vier und mehr Review-Runden; ein Refute-Durchlauf fand in zwei Läufen mehr als drei Review-Runden zuvor.

**Was sich ändert.**
- Ändert ein Diff `scripts/process/`, `.githooks/` oder die Gate-Konfiguration, greift ihn ein frischer Agent an, bevor der Review ihn sieht.
- `docs/process/refute.md` (neu) beschreibt Zeitpunkt, Rolle, Auftrag zum Kopieren und Umgang mit Funden.
- Das Ergebnis steht als Zeile `REFUTE work=<id> round=<r>: …` im Plan.
- Das Review-Bündel warnt bei Gate-Code ohne REFUTE-Zeile, sperrt aber nicht.
- `review.md` und `verification-independence.md` verweisen auf die neue Regel.

**Wirkung.** Gate-Code wird vor dem Review angegriffen; jeder Fund wird ein Regressionstest oder eine DECISION. Die Warnung ist vorerst nur ein Hinweis.

**Update.** Keine Schritte.

## v2.31.7 — „Suite nicht vorhanden“ auch unter `make train` · 2026-09-25

**Warum.** v2.31.6 erkannte „Suite nicht vorhanden“ nur unter `make:`; unter `make train` meldet sich das make der Suite als `make[1]:`, und der Fall wäre wieder rot gewesen.

**Was sich ändert.** Es zählt jetzt die make-Ebene direkt unter der des Zugs; tiefere Ebenen bleiben rot.

**Update.** Keine Schritte.

## v2.31.6 — Vier Restbefunde im Zug, in tidy und im Stale-Check · 2026-09-25

**Warum.** Das Review zu v2.31.5 ließ vier Restbefunde offen.

**Was sich ändert.** Der Zug erkennt „Suite nicht vorhanden“ enger und wiederholt nach einem Abwurf Flakes, `tidy` übersteht unlesbare Dateien, und der Stale-Check erkennt verworfene Konfliktauflösungen.

**Wirkung.** Ein Fehler in einem Test sieht nicht mehr wie eine fehlende Suite aus, und ein verworfener Review rutscht nicht durch.

**Update.** Keine Schritte.

## v2.31.5 — `stale_review` prüft die Regel statt des Symptoms · 2026-09-25

**Warum.** Runde 3 des Reviews im Referenzprojekt zeigte: Nach `commit --amend` oder Rebase liegt der geprüfte Stand nicht mehr in der Vorgeschichte, und die Prüfung ließ das durch.

**Was sich ändert.** Der Stale-Check prüft die Regel statt des Symptoms: Ein geprüfter Stand außerhalb der Vorgeschichte ist ungültig, alles Ungeprüfte zählt, Git-Fehler führen zur Ablehnung.

**Wirkung.** Ein eingemergter Nebenbranch, ein Amend neben dem geprüften Stand und ein Merge mit `-s ours` fallen jetzt auf. Die Funde eines unabhängigen Refute-Agenten liegen als Regressionstests vor.

**Update.** Keine Schritte.

## v2.31.4 — Journal-Zeilen zweier Branches mergen ohne Konflikt · 2026-09-25

**Warum.** Im Referenzprojekt blockierten sich zwei geprüfte Branches im Zug über angehängte REVIEW-Zeilen in derselben Tagesdatei.

**Was sich ändert.** `.process-work/journal/.gitattributes` setzt `*.md merge=union`, sodass der Merge beide Zeilen behält; eine Root-`.gitattributes` des Projekts bleibt unberührt.

**Update.** Keine Schritte.

## v2.31.3 — Ein Prüfer-Set über alle Review-Runden · 2026-09-25

**Warum.** Ein neuer Prüfer in einer späteren Runde fand Altbefunde, und jeder davon wurde zu einer eigenen Runde.

**Was sich ändert.** `review.md` verlangt ein festes Prüfer-Set pro Arbeit und lässt Folgerunden nur den Fix und sein Umfeld prüfen; ältere Befunde werden eigene Issues.

**Update.** Keine Schritte.

## v2.31.2 — Konfliktauflösungen in Merge-Commits zählen als ungeprüft · 2026-09-25

**Warum.** Runde 2 des Reviews im Referenzprojekt: Der Fix aus v2.31.0 (`--no-merges`) übersah eine nach dem Review von Hand aufgelöste Konfliktstelle im Merge-Commit.

**Was sich ändert.** Der Stale-Check liest Merges über ihren kombinierten Diff (`--cc`): Eine Konfliktauflösung zählt als Code der Arbeit, ein sauberer Merge nicht.

**Update.** Keine Schritte.

## v2.31.1 — Rundenzähler zählt Runden statt Block-Zeilen · 2026-09-25

**Warum.** Das erste Review des Rundenzählers zeigte: Mehrere Prüfer-Linsen einer Runde wurden mehrfach gezählt.

**Was sich ändert.** `attest` zählt eindeutige blockierte Runden statt Block-Zeilen, und `--exception` schreibt die `REVIEW-EXCEPTION`-Zeile auch ohne greifende Regel.

**Wirkung.** Mehrere Linsen einer Runde zählen nicht mehr als mehrere Runden, und Ausnahmen bleiben immer zählbar.

**Update.** Keine Schritte.

## v2.31.0 — Zug unterscheidet Flake, fehlende Suite und fremde Passagiere · 2026-09-25

**Warum.** Befunde aus dem Referenzprojekt (Zug 31 und 34): Eine Bisektion über einen Flake beschuldigt einen Unbeteiligten, ein Passagier mit neuem Make-Ziel machte den Baum rot, und der Merge-Push lehnte jeden Zug mit mehreren Passagieren ab.

**Was sich ändert.**
- Ist der kombinierte Baum rot, läuft er ein zweites Mal; ist er dann grün, meldet der Zug FLAKY und merged.
- Fehlt die Suite auf einem Baum, ist dieser nicht vergleichbar statt rot: main gilt nicht als rot, kein Präfix wird beschuldigt.
- Jedes Rot-Urteil protokolliert die Systemlast, und ein abgelehnter Push nennt, ob origin oder der pre-push-Hook abgelehnt hat.
- Das Review-Gate zählt als „Code nach dem Review“ nur noch Nicht-Merge-Commits, die vom geprüften Stand abstammen.
- `tidy` führt Spec-Verzeichnisse, die der Pruner ablehnen würde, mit dem fehlenden Teil als Owner-Entscheidung auf; `--apply` übergibt sie nicht mehr.

**Wirkung.** Ein Flake blockiert den Zug nicht mehr, Mitpassagiere führen nicht mehr zur Ablehnung, und `tidy --apply` übergibt nichts, was der Pruner ablehnt.

**Update.** Keine Schritte.

## v2.30.0 — Weniger Review-Runden: zählen, erst die Ursache, dann der Fix · 2026-09-24

**Warum.** Die Analyse im Referenzprojekt ergab: Arbeiten mit drei oder mehr Runden stiegen von 11 % auf 23 %, vor allem durch Fixes, die den nächsten Blocker selbst erzeugten, und einen aufgeblähten Rundenzähler. Dazu kamen Arbeiten mit 3.000–5.500 Zeilen.

**Was sich ändert.**
- `attest` zählt die Runde selbst (1 plus erfasste Blocks) und lehnt eine abweichende Behauptung ab; Plan-Reviews zählen getrennt (`--plan-review`).
- Vor jeder Runde nach einem Block verlangt `attest` pro Block eine Zeile `ROOT-CAUSE work=<id> round=<r>: …` im Journal oder Plan.
- `--exception` hebt beide Regeln auf und schreibt eine zählbare `REVIEW-EXCEPTION`-Zeile.
- Das Review-Bündel warnt ab 30 Dateien oder 1.500 Zeilen (`PROCESS_REVIEW_MAX_FILES`/`_LINES`).
- Laut `review.md` übernimmt eine frische Sitzung den Fix, wenn dieselbe Stelle zweimal blockiert.

**Wirkung.** Eine Fix-Runde beginnt erst mit dokumentierter Ursache, der Zähler zeigt echte Runden, und zu große Arbeiten fallen früh auf.

**Update.** Keine Schritte.

## v2.29.0 — Nur die eigene Arbeit gibt einen Branch frei · 2026-09-24

**Warum.** Im Referenzprojekt stieg ein Template-Update-Branch in den Zug ein, während sein eigenes Review noch lief, weil er nur fremde, längst freigegebene Pläne archivierte.

**Was sich ändert.**
- Im Zug gibt ein archivierter Plan einen Branch nur frei, wenn es der eigene ist.
- Ein Branch, der `scripts/process/` oder `.githooks/` ändert, steigt unabhängig vom Tier nur mit einem REVIEW-Pass für die eigene Arbeit ein.
- Das Review-Bündel markiert ungültige Belege als VOID: identische Vorher/Nachher-Paare, identische Bilder und bekannte Leerzustände unter `docs/process/void-evidence/`.
- `model-policy.json` kennt `env` global und pro Phase (etwa `CLAUDE_CODE_SUBAGENT_MODEL`), gültig nur für Worker-Sitzungen.
- Der tmux-Runner entfernt Policy-Variablen nicht mehr zusammen mit den `CLAUDE_CODE_*`-Variablen des Stewards.
- `tower.md` nennt den attest-Commit auf dem Arbeitsbranch als Weg für ein Urteil aus der Cloud.

**Wirkung.** Aufräumen fremder Pläne gibt keinen Branch mehr frei, leere Belege gelten nicht, und Policy-Variablen erreichen die Worker.

**Update.** Keine Schritte.

## v2.28.2 — Die Merge-Suite ist die volle Suite jedes Stacks · 2026-09-24

**Warum.** Im Referenzprojekt fuhr der Zug nur die Backend-Suite; eine CSS-Änderung brach einen Frontend-Pin, und nichts vor dem Merge startete ihn.

**Was sich ändert.** `--suite` gilt jetzt als volle Suite jedes Stacks (`train.md`, `testing.md`), und `train.py run` ohne `--suite` warnt auf stderr, dass nur die Prozess-Gates laufen.

**Update.** Keine Schritte.
