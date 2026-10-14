# Plan: Nachweise vor dem Pass (Review-Tiefe)

Datum: 2026-10-14 · Issue: #225 · Tier: 3 (Gate-Code: `attest.py`, neues `attest_evidence.py`) · Release: Migrations-Release

## Anlass

Kenni hat in einer Nacht sechs Tier-2-Branches gemergt, alle mit einem Pass in Review-Runde 1. Ein Kalibrierungs-Audit fand danach sechs Major-Fehler, die das Review übersehen hatte. Vier davon sind Tests, die nicht rot werden können oder echten Zustand anfassen. Dazu kamen zwei Lücken, die heute nur warnen:

- **Gate-Code-Refute:** Er fehlte auf 4 von 4 Gate-Code-Branches. Das Bundle warnt nur („observed before it gates“).
- **Cross-Model-Lauf:** Kenni verlangt ihn ab Tier 2 lokal. Er wurde ohne Hinweis übersprungen, und nichts lehnte das ab.

Die Kenni-Vorschläge aus #225:

- **A:** Der Codex-Lauf bekommt bei Gate-Code den Refute-Auftrag.
- **B:** `attest.py` verweigert, wo heute nur gewarnt wird.
- **C:** Der Review-Bericht bekommt eine Testzeile je AC.
- **D1:** Kein kleineres Modell für die Plan-Review als in der Plan-Session.
- **D2:** Codex für Gate-Code-Pläne.
- **E1:** Plan-Zeilen stehen vor dem Attest im Head.

Kenni hat alles lokal in kenni#2602 gebaut: `attest_evidence_local.py` plus ein Haken in `attest.py`, nach drei Refute-Runden. Der Owner hat den Template-Port am 2026-10-14 freigegeben. Weil `attest.py` dem Template gehört, macht dieser Port Kennis Patch überflüssig.

## Entscheidungen

- **D-Owner.** Ein neues Kernmodul `template/scripts/process/attest_evidence.py` ist der einzige Owner der Nachweisregeln. Es hat zwei Teile:
  - `gather()` liest jeden Nachweis am Git-Objekt `head` der attestierten Zeile: den Plan der Arbeit, REFUTE- und Skip-Zeilen, Testfunktionen und den Diff `base..head`. Der Arbeitsbaum zählt nur bei E1.
  - `decide(Evidence) -> list[str]` ist eine reine Entscheidungstabelle und bekommt einen Tabellentest.

  `attest.py::main` ruft `evidence_problems(...)` genau einmal auf, nach `build_line`, weil erst dann Base und Head feststehen. Mit `--exception` landen die Funde in den `overrides` der `REVIEW-EXCEPTION`, wie die Rundenregeln. Grammatik und Pfadregeln bleiben bei ihren Ownern:
  - `check_review.REFUTE_LINE`, `is_gate_path`, `readable`, `record_texts(ref=…)`, `_plan_work_ids`, `work_key`;
  - `report.reports_path`;
  - `dispatch.load_policy`.
- **D-Konfig.** `model-policy.json` bekommt `review_evidence`, das wie bisher über `model-policy.local.json` überlagert wird:
  - `cross_model_from_tier`: Template-Standard 3, Kenni setzt 2.
  - `ranks`: Präfix der Modell-ID → Rang, Standard `claude-haiku` 0, `claude-sonnet` 1, `claude-opus` 2, `claude-fable` 3.
  - `families`: Präfixe weiterer Familien ohne Rang, Standard `gpt-`.

  Gelesen wird über `dispatch.load_policy`, den einen Leser mit Overlay. Eine unlesbare Policy führt zu einer Verweigerung mit Hinweis (fail closed). Ein Modell, dessen ID zu keinem Präfix passt, gilt als unbekannt.
- **D-Skip.** Ein Verzicht steht als Zeile `skipped <kind> work=<id>: <Grund>`. Die erlaubten Arten:
  - `cross-model`, mit der älteren Schreibweise `codex-review`, die Kenni schon nutzt;
  - `refute`;
  - `plan-review`;
  - `ac-trace`.

  Die Zeile braucht denselben Zeilenanfang wie Record-Zeilen. Der Grund darf nicht leer und kein Platzhalter sein (`<…>`, `TODO`, `…`). Eine Zeile zählt nur mit der nackten Arbeits-ID. Eine ID mit Repo-Präfix (`owner/repo#N`) zählt nicht. Gelesen werden die Zeilen am Head aus allen Record-Dateien. Jeder Verzicht bleibt per `grep` zählbar.
- **B1 Cross-Model (Code-Review).** Ein `pass` ab `cross_model_from_tier` braucht das Token `cross-model`. Alternativ genügt `single-family` zusammen mit einer `skipped cross-model`-Zeile der Arbeit. Bei Template-Standard 3 ist das eine Verhaltensänderung: Ein Single-Family-Pass auf Tier 3 braucht jetzt einen Grund. Plan-Reviews regeln D1 und D2.
- **B2 Gate-Code-Refute (Code-Review, Tier ≥ 2).** Berührt `base..head` Gate-Code nach `is_gate_path`, braucht der Pass eine REFUTE-Zeile der Arbeit am Head oder `skipped refute`. Kann git den Diff nicht liefern, wird verweigert.
- **A Ein Lauf.** Auf Tier 2 mit `cross-model` zählt auch eine REFUTE-Zeile im `--with`-Bericht dieses Attests. Damit liefert der Cross-Model-Lauf, der den Refute-Auftrag abarbeitet, beide Zeilen. Ab Tier 3 bleibt der getrennte Refute vor Runde 1 (Tabelle in `refute.md`), und nur eine Zeile am Head zählt. `refute.md`, `/review` und `verification-independence.md` sagen das.
- **C Testzeile je AC (Code-Review, Tier ≥ 2).**
  - **Soll-Liste:** alle Zeilen `AC-<n>:` des Plans am Head. Erkannt werden auch `AC<n>:` und `AC <n>:`, mit Liste, Checkbox, Überschrift oder Fettdruck davor.
  - **Ist-Liste:** die Zeilen `AC-<n>: <pfad>::<test>` in den `--with`-Berichten.
  - **Verweigert wird bei:**
    - einem Pass ohne Bericht;
    - einer fehlenden AC;
    - `unproven` an beliebiger Stelle der Zeile;
    - einem Beleg ohne `pfad::name`;
    - einem Test, der am Head fehlt oder abgeschaltet ist.
  - **Python-Prüfung (AST am Head):**
    - Gilt für `test_*` auf Modulebene oder `Klasse::test_*`.
    - Das Modul darf kein `pytestmark` mit skip/xfail tragen, auch keines in annotierter Form.
    - Ein `skip` auf Modulebene darf nicht aufgerufen werden, auch nicht als `importorskip`.
    - Der Test darf keinen Dekorator haben, dessen Ausdruck skip, skipif oder xfail nennt oder einen Namen, den das Modul an so einen Ausdruck bindet. Das deckt Aliase ab.
    - Im Körper darf kein `pytest.skip` oder `pytest.xfail` stehen.
    - Bei doppelter `def` zählt die letzte.
  - **Andere Sprachen:** Die Datei existiert am Head, und der Name steht wörtlich darin. Verweigert wird, wenn eine Zeile mit dem Namen auch `skip`, `xit`, `xtest`, `xdescribe` oder `todo` als Wort trägt.
  - **Plan ohne AC-Zeile:** wird verweigert, außer es gibt `skipped ac-trace`. Das betrifft etwa einen Spec-Kit-Plan, dessen ACs in `spec.md` stehen.
  - Ob der genannte Test die AC wirklich prüft, entscheidet der Reviewer. Das ist ein Rest, den kein Gate abdeckt.
- **D1 Modellklasse der Plan-Review (Tier ≥ 2).**
  - **Rangvergleich:** Ein `--plan-review`-Pass braucht ein `--model`, das zu `ranks` oder `families` passt. Ist es eine geranke Klasse, darf sein Rang nicht unter dem der Plan-Session liegen. Eine andere Familie ist nie kleiner.
  - **Modell der Plan-Session:** Es kommt aus dem neuesten `planned`-Report des Issues (`report.py`). Ohne Report gilt die Zeile `plan-session model: <id>` im Plan am Head, die `/plan` schreibt. Ein Report ohne gemessenes Modell ist nicht prüfbar.
  - **Verweigert wird:** wenn das Modell unbekannt, kleiner oder nicht prüfbar ist, außer es gibt `skipped plan-review work=<id>-plan`.
  - **Abweichung von Kenni:** Kenni lässt die Plan-Zeile für Slug-Arbeiten nicht gelten. Das Template lässt sie gelten, weil eine interaktive Tier-2-Planung vor ihrer Plan-Review keinen `planned`-Report hat. Der Rest ist benannt: Die Zeile ist eine Selbstangabe.
  - `/plan`: „a cheap model is enough“ für die Tier-2-Plan-Review fällt weg. Stattdessen gilt: nicht kleiner als die Plan-Session, und `--model` nennt die konkrete ID.
- **D2 Gate-Code-Pläne (Plan-Review, Tier ≥ 2).** Nennt der Plantext einen Gate-Pfad, braucht der Plan-Review-Pass `cross-model` oder `single-family` mit `skipped cross-model work=<id>-plan`. Pfade werden vor `is_gate_path` normalisiert: `./`, `/` und `\` werden behandelt, `scripts/process/` gilt als Teilpfad.
- **E1 Plan-Zeilen vor dem Attest (jeder Pass ab Tier 2).** Die Plan-Datei der Arbeit muss am Head gleich Arbeitsbaum und Index sein. Sonst wird verweigert, und die Meldung nennt die Reihenfolge: erst die Plan-Zeilen committen, dann Bundle und Attest am neuen Head.
  - Fehlt der Plan der Arbeit am Head, wird verweigert, ebenso wenn er nicht eindeutig ist.
  - Ein Block bleibt frei. `--with <plan>` bei einem Block ist weiter erlaubt, bei einem Pass greift E1.
- **Nicht in diesem Release.**
  - **Push-Gate:** Die Prüfung läuft nicht in `check_review`, sondern nur beim Schreiben. Im Push-Gate würde sie alte Tier-2-Zeilen rückwirkend rot machen und einen zweiten Owner schaffen. Der Rest ist benannt: Eine von Hand geschriebene REVIEW-Zeile umgeht die Prüfung. Folge-Issue.
  - **Fix-Runden:** Ein neuer Refute nach einer Fix-Runde mit Gate-Code bleibt eine Warnung des Bundles (`_unrefuted`).
  - **Selbstangabe:** Das Token `cross-model` bleibt eine Selbstangabe, wie bisher.

## Aufgaben

1. `attest_evidence.py` mit `Evidence`, `gather` und `decide`. Dazu `tests/test_attest_evidence.py`:
   - einen Tabellentest für `decide`, eine Zeile je Regel und Ausnahme, jede rot vor ihrer Regel;
   - Integrationstests in einem Scratch-Repo für Head-Bindung, Diff-Fehler, AST-Regeln und Aliase, Plan-Zeile und Report;
   - Tests für E1 im Arbeitsbaum und im Index.
2. `attest.py`: Der Aufruf kommt nach `build_line`, die Exception nimmt die Evidenz-Funde auf. `--with` und der Docstring sagen, dass Plan-Zeilen vor einem Pass im Head stehen. Bestehende Tests rufen `attest.py` mit Tier ≥ 2 und `pass` auf. Sie bekommen einen Helfer, der die Nachweise liefert, und werden nicht abgeschwächt.
3. `model-policy.json` erhält `review_evidence` samt Kommentar. Ein Test prüft, dass jedes Modell der Template-Policy einen Rang hat.
4. Doku:
   - `refute.md`: Tabelle und Absatz zur Bundle-Warnung, dazu `skipped refute` statt „say so in the plan“;
   - `verification-independence.md`: Cross-Model-Schwelle, `single-family` mit Grund;
   - `/review`: Testzeile je AC, Bericht bei jedem Pass ab Tier 2, A;
   - `/plan`: D1, D2 und `plan-session model:`;
   - `review-checklist.md`: eine AC-Zeile je AC, sonst ist die AC unbewiesen;
   - `design-template.md`: `plan-session model:`;
   - der Text der REFUTE-Warnung in `make_review_bundle.py`.
5. CHANGELOG mit Abschnitt `Migration` und NEWS. Refute, Review, Release.

## Migration (für das Release)

- **Kenni:**
  - `scripts/process/attest_evidence_local.py` und seine Tests entfernen. Der Haken in `attest.py` kommt mit dem Update.
  - In `model-policy.local.json` den Wert `review_evidence.cross_model_from_tier: 2` setzen.
  - Kennis eigene Rang- und GPT-Liste prüfen.
  - `skipped codex-review`-Zeilen gelten weiter.
- **Alle Projekte:**
  - Tier-2+-Reviews schreiben einen Bericht mit einer AC-Zeile je AC.
  - Plan-Reviews nennen mit `--model` die konkrete ID.
  - Pläne tragen `plan-session model:`.
  - Ein Single-Family-Pass auf Tier 3 braucht `skipped cross-model`.

## Unabhängige Durchsetzung

Das Push- und Merge-Gate (`check_review`) bleibt unverändert die harte Grenze für Grammatik, Runden und Abdeckung. Die neuen Regeln verweigern nur beim Schreiben, und jeder Zweifel endet in einer Verweigerung mit genannter Ausnahmezeile. Keine bestehende Prüfung wird gelockert.

## Plan-Review Runde 1 — Änderungen

Ergebnis: Block mit drei BLOCKERn, drei MAJORs und vier MINORs. Wo diese Punkte den Entscheidungen oben widersprechen, gelten sie.

- **P1 E1 folgt `records_only` (BLOCKER).** `check_review.records_only` lässt Record-Zeilen, die nach der letzten Planzeile angehängt sind, mit dem Attest-Commit mitfahren (#199). E1 verweigert deshalb nur, wenn der Plan im Arbeitsbaum oder im Index mehr als angehängte Records gegenüber dem Head enthält. Die Meldung sagt: Records ans Ende, alles andere vorher committen. Angehängte Records (REFUTE, Skip) zählen für B2 und für die Skips mit, wie für das Gate. Kennis Fall #2407 war eine Zeile mitten im Plan.
- **P2 Bindung an die Arbeit, nicht an `--work` (BLOCKER).** `attest.py` gibt die Work-IDs von `round_ids` mit: Slug, Datumsslug, Issue des einen Plans. Der Plan wird über diese IDs gefunden. Bei mehreren Plänen wird auf den Plan eingeengt, dessen Stem zu den IDs gehört. Sonst nennt die Meldung `--work <slug>`. REFUTE- und Skip-Zeilen binden an jede dieser IDs. Ausgenommen bleibt eine ID mit Repo-Präfix. Eine Plan-Review bindet Skips an `<id>-plan`. Nach einem `--archive` (späte Linse) wird der archivierte Plan gefunden.
- **P3 AC-Zeilen im Bundle und in den Dispatch-Prompts (BLOCKER).** Der Grammatikabschnitt des Code-Review-Bundles (`make_review_bundle`) verlangt eine AC-Zeile je Kriterium. Die Prompts für Reviewer, die nicht attestieren (`dispatch.py`), verlangen sie ebenfalls. Tests pinnen beides. `/review`: Jeder Tier-2+-Review schreibt einen Bericht.
- **P4 D2-Erkennung (MAJOR).** Ein Gate-Pfad im Plantext zählt nicht, wenn er als `pfad:zeile` zitiert oder als Befehl aufgerufen wird (`run`, `python`, `python3` direkt davor). Normalisiert werden nur Plan-Tokens. Diff-Pfade gehen unverändert an `is_gate_path`, eine zweite Pfadregel gibt es nicht. Skip-Zeilen werden Records: Ihre Grammatik besitzt `check_review` (`SKIP_LINE`), und `_record_line` kennt sie. Damit stellt eine angehängte Skip-Zeile die Plan-Review nicht neu fällig. `/plan` sagt, wohin sie gehört.
- **P5 D1-Reihenfolge (MAJOR).** Ein Paar aus verschiedenen Familien besteht immer, in beiden Richtungen, und wird vor der Session-Suche geprüft. Ranks vergleichen nur geranke Klassen. Ein `planned`-Report ohne gemessenes Modell fällt auf die Plan-Zeile zurück. Die Issues einer Slug-Arbeit kommen aus der `issue:`-Zeile ihres Plans. Reports werden über `report.read_reports` gelesen.
- **P6 AC-Grammatik (MAJOR).** Eine AC-ID ist `AC-<id>` mit `[\w.]+` wie im Zug (`train._HOLDS`) oder `AC<Ziffer…>`. Ein Punkt am Ende gehört nicht zur ID.
  - **Soll-Liste:** jede AC-ID, die der Plan am Head nennt, denn die Checkliste verlangt im Plan je AC die Task und den Test. Bei einem Spec-Kit-Plan kommen die IDs aus `spec.md` desselben Verzeichnisses dazu.
  - **`unproven`:** wird nur außerhalb der genannten `pfad::name` erkannt.
- **P7 Policy (MINOR).** Die Policy wird nur für einen Pass ab Tier 2 geladen, lazy, typgeprüft, am Base. Ein Fehler wird zur Verweigerung, nicht zu einem Absturz.
- **P8** Die Diff-Pfade nutzen allein `is_gate_path` (MINOR).
- **P9 A (MINOR).** Eine REFUTE-Zeile zählt nur aus einem Bericht unter `.process-work/reviews/`. Die Bundle-Warnung `_unrefuted` bleibt, wie sie ist. Ein Rest ist benannt: Die Fix-Runden-Regel sieht diese Zeile nicht.
- **P10 Tests und Ränder (MINOR).**
  - Ein Pass ohne Range wird verweigert.
  - Der Test-Helfer committet echte Nachweise vor dem Head: AC im Plan, eine echte Testfunktion und einen Bericht. Er nutzt keine Skip-Zeilen und keine Exception.
  - Plan-Review-Tests nennen konkrete Modelle und `plan-session model:`.
- **P11 Doku (NIT).**
  - `review.md`, `journal-state-plans.md`, `testing.md` und der `_comment` der Policy werden angepasst. Der `_comment` warnt jetzt: Ein kleineres Subagent-Modell wird als Plan-Reviewer verweigert.
  - `plan-session model:` kommt in beide Zweige von `plan.md.jinja`, nicht in `design-template.md`.
  - `attest.py`: Die Exception wird nach `build_line` gebaut.
- **Prozess.** Code entstand vor dem Plan-Pass. Er wird nach diesen Änderungen umgebaut, und Runde 2 prüft den revidierten Plan.

## Plan-Review Runde 2 — Änderungen

Ergebnis: Block. N1 ist ein BLOCKER, N2 und N4 sind MAJOR, N3 ist MINOR, dazu ein NIT. Alles ist behoben.

- **R1 AC-ID mit Ziffer (N1).** Eine AC-ID ist `AC-?` plus höchstens drei Buchstaben, eine Ziffer und den Rest, also `AC-1`, `AC-2.1`, `AC-B1` oder `AC1`. `AC-Zeile`, `AC-<id>` und `AC-N` sind Prosa. Die Bericht-Zeilen lesen dieselbe ID.
- **R2 Lesebreite wie der Owner (N2, N5).** REFUTE- und Skip-Zeilen werden nur aus dem gefundenen Plan gelesen, wie `make_review_bundle._unrefuted`. Sie binden über die IDs dieses Plans als String, ohne `work_key`. Ein zweiter Plan derselben Issue, das Archiv und das Journal leihen nichts.
- **R3 Nur, was mitfährt (N3).** Angehängte Records zählen nur, wenn der Plan in `--with` steht.
- **R4 DoD-Abweichung (N4).** Hält eine Zeile `DoD-deviation: open AC-<id>` (`train.DOD_DEVIATION` und `_HOLDS`) eine AC offen, fällt diese aus der Soll-Liste.
- **P3 erledigt.** Grammatik im Code-Review-Bundle und Prompt für den nicht attestierenden Reviewer sind umgesetzt, gepinnt in `test_review_bundle` und `test_dispatch`.

## Plan-Review Runde 3

Ergebnis: pass, mit drei MINOR- bzw. NIT-Resten. Alle sind behoben oder benannt.

- **M1:** Eine AC-ID in einem Code-Span (Backticks) im Plan ist ein Beispiel und keine AC. Sie zählt nicht zur Soll-Liste.
- **M2:** Die Schreibweise `AC 1` mit Leerzeichen vor einer Ziffer wird wieder erkannt.
- **M3 (Rest, benannt):** Eine Zeile `DoD-deviation: open AC-<id>` nimmt die AC aus der Testpflicht. Sie bleibt sichtbar, weil der Zug `Refs` statt `Closes` schreibt, wird aber nicht mit den Skip-Zeilen gezählt.
- **Doku:** Skip-Zeilen gehören in den Plan, vor dem Bundle committet oder angehängt und mit `--with` mitgefahren. `/plan` und `/review` sagen das.

## Refute Runde 1 — Änderungen

Ergebnis: Block mit zwei Funden ab 80 und fünf weiteren. Die Ursache der ersten drei ist dieselbe: Ob ein Test läuft, wurde an Wörtern im Quelltext abgelesen statt an dem, was der Testläufer sammelt.

- **F1/F2/F3 Umbau des Test-Prüfers.** `test_status` urteilt jetzt wie pytest.
  - **Testmodul:** `test_*.py` oder `*_test.py`, ohne `__test__ = False`.
  - **Klasse:** `Test*` ohne `__init__`, oder eine TestCase-Unterklasse.
  - **Funktion:** beginnt mit `test`. Die letzte Bindung des Namens zählt, und das muss die `def` sein, keine spätere Neubindung.
  - **Skip-Erkennung:** Namen werden über Importe und Modulzuweisungen aufgelöst (`_Names`). Als Abschaltung zählen `pytest.mark.skip/skipif/xfail`, `unittest.skip*/expectedFailure` sowie Aliase dieser Marken. Im Körper zählen `pytest.skip/xfail/importorskip`, `self.skipTest` und `raise SkipTest`. Daten wie `'--skip'` und Aufrufe wie `R().skip()` zählen nicht.
  - **Andere Sprachen:** Die Datei muss eine Testdatei sein (`tests/` oder `spec/` im Pfad, `test`/`spec` im Namen). Eine deklarierende Zeile (`it(`, `test(`, `func`, `fn`, `@Test`, `#[test]`) muss den Namen tragen. Eine Skip-Marke auf ihr oder der Zeile darüber zählt (`.skip`, `xit`, `@Disabled`, `#[ignore]`).
  - **Rest:** Sammelregeln eines Läufers, die über diese hinausgehen, sind nicht modelliert.
- **F4 Dispatch.** `_plan_states.cleared` erkennt einen Plan als gleich, wenn derselbe Blob vorliegt oder `records_only` gilt. Eine angehängte Skip- oder REFUTE-Zeile macht die Plan-Review nicht neu fällig. Test in `test_dispatch`.
- **F5 Backticks.** Ausgenommen ist nur ein Code-Span, der wie eine Beispielzeile aussieht (er enthält `::` oder `<`). Eine AC-ID allein in Backticks zählt.
- **F6 (Rest, benannt).** Ein Gate-Pfad im Plan, der als `pfad:zeile` zitiert ist, oder ein nackter Dateiname zählt nicht als Gate-Code-Plan. B2 fängt den Diff im Code-Review.
- **F7.** Eine Überschrift oder Prosazeile einer AC im Bericht ist kein Beleg. Es genügt, wenn eine Zeile der AC einen Test nennt.
- **Regeln ohne roten Test** haben jetzt Tests:
  - ACs aus `spec.md`;
  - der Rückfall eines ungemessenen Reports auf die Plan-Zeile;
  - die Einengung zweier Pläne über den Slug.

  Den `ImportFrom`-Zweig ersetzt `_Names`, mit Tabellenzeilen dazu.
- REFUTE-Zusammenfassung: 7 Funde, 2 blockierend. Daten mit „skip“ führten zu Fehlablehnungen, und eine Nicht-Testdatei konnte eine AC belegen. `self.skipTest` wurde übersehen. Eine angehängte Skip-Zeile machte die Plan-Review in Dispatch neu fällig. Vier Regeln hatten keinen roten Test.

## Refute Runde 2 — Änderungen

Ergebnis: Block mit einem BLOCKER. Alle Fixes aus Runde 1 halten. Es ist der zweite Block am selben Element, dem Test-Prüfer, deshalb ein Umbau statt eines weiteren Flickens. Die gemeinsame Ursache der Funde 1, 4 und 5: Welche Datei ein Test ist, wurde aus festen Namensmustern geraten, statt aus der Konfiguration des Projekts gelesen.

- **Umbau: Das Projekt deklariert seine Testdateien.** `review_evidence` erhält drei Schlüssel:
  - `python_files`: pytests Vorgabe `test_*.py`, `*_test.py`;
  - `python_classes`: Vorgabe `Test`;
  - `test_files`: fnmatch auf den Repo-Pfad, wobei `*` auch Ordner überspannt. Die breiten Vorgaben decken `*Tests/*`, `*Tests.*`, `*.spec.*`, `*_test.*` und `tests/` ab.

  Kennis Xcode-Ziele (`*Tests.swift`, `*UITests/Sources/*`) sind damit gedeckt. Ein Projekt ergänzt sein eigenes Layout, etwa Rust-Tests in `src/*.rs`. Eine Text- oder Datendatei (`.md`, `.json`, …) ist nie ein Test.
- **Andere Sprachen:**
  - Der Name muss als ganzes String-Literal oder ganzer Bezeichner auf einer deklarierenden Zeile stehen, nie als Teilstring.
  - Eine Skip-Marke zählt auf der Zeile davor, auf der Zeile selbst und im Körper bis zur nächsten Deklaration. Erkannt werden `t.Skip`, `XCTSkip`, `this.skip(`, `.skip` und `xit`.
- **Python:**
  - Ein autouse-Fixture oder `setUp`/`setup_*` des Moduls oder der Klasse, das skippt, schaltet ab.
  - Sind alle Fälle eines `parametrize` per `pytest.param(marks=skip)` abgeschaltet, zählt der Test als abgeschaltet.
  - Geerbte Testmethoden aus Basisklassen desselben Moduls werden gefunden.
  - `python_files` und `python_classes` kommen aus der Policy.
- **Dispatch:** Eine angehängte DECISION öffnet die Plan-Review wieder, denn sie bindet den Executor. REFUTE- und Skip-Zeilen öffnen sie nicht. Test in `test_dispatch`.
- **Rest (benannt):** Ein Skip-Alias, der aus einem eigenen Hilfsmodul importiert wird, ist nicht aufgelöst. Sammelregeln eines Läufers jenseits der deklarierten Muster sind nicht modelliert.
- REFUTE-Zusammenfassung: 5 Funde, einer blockierend. Xcode-Ziele vom Typ `*Tests.swift` galten als keine Testdatei (116 Dateien bei Kenni). Eine angehängte DECISION gab eine Planänderung in Dispatch frei. Autouse-, setUp- und param-Skips, Prosa, Teilstrings und Go-`t.Skip` gingen durch.

## Refute Runde 3

Ergebnis: pass mit Resten, kein Fund ab 80. Alle Fixes aus Runde 2 halten. Gegen Kennis Dateiliste geprüft:

- Swift: 117 von 117 UI- und Snapshot-Tests werden angenommen, 150 von 150 übrige.
- Frontend-Spec- und Testdateien: 611 von 611 werden angenommen.
- Backend: Abgelehnt werden nur Hilfsmodule.

Die Funde 1 bis 4 und 5a waren günstig zu beheben, das ist geschehen:

- **`XCTSkipIf`/`XCTSkipUnless`** werden erkannt. Kennis Perf-Test, der standardmäßig skippt, belegt keine AC mehr.
- **Setup:** Ein `setUp*`, `beforeEach`/`beforeAll` oder `TestMain` der Datei, das skippt, schaltet ihre Tests ab.
- **Kommentarzeilen** zählen weder als Deklaration noch als Körper. Ein Kommentar beendet die Körpersuche also nicht mehr.
- **Testform des Läufers:**
  - JS-artig `it(`/`test(` mit dem Namen als Titel;
  - `func/fun/fn/def test…` (XCTest, Go `Test…`);
  - eine Funktion unter `@Test`, `#[test]` oder `[Test]`/`[Fact]`.

  Eine Hilfsfunktion in einer Testdatei belegt nichts.
- **Zeilen über dem Test:** Nur Attributzeilen direkt darüber zählen zum Test, nicht der vorige Test (`it.todo`).
- **Reste (benannt):**
  - eine Basisklasse aus einem anderen Modul;
  - ein Skip-Alias aus einem eigenen Hilfsmodul;
  - Setup-Bereiche pro Klasse in anderen Sprachen (geprüft wird pro Datei);
  - Freitext hinter angehängten REFUTE- oder Skip-Zeilen, der unreviewt beim Executor ankommt. Executoren lesen REFUTE- und Skip-Zeilen nicht als Auftrag, nur DECISION-Zeilen binden.

REFUTE-Zusammenfassung: 6 Funde, keiner blockierend. `XCTSkipUnless` und `XCTSkipIf` fehlten, Swift-Setup-Skips, Kommentare und Hilfsfunktionen gingen durch, ein `it.todo` darüber und eine fremde Basisklasse führten zu Fehlablehnungen. Die Fixes aus Runde 2 und die Kenni-Probe bestehen.
