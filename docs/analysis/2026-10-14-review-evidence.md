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
