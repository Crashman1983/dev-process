# Plan: Dispatch- und Train-Robustheit

Datum: 2026-10-12 · Issues: #207, #204, #201 · Release: v2.66 · Tier: 3 (Gate-Code: dispatch, train)

## Anlass

Drei offene Lücken im Gate-Code, vom Owner am 2026-10-12 als ein Release freigegeben:

- **#207** stammt aus Kennis Review zu v2.63. `plan_review_due` scheitert offen oder stürzt ab, und vier Mutanten überleben die Tests.
- **#204:** Zwei Regeln entscheiden, welche Pläne einem Branch gehören. `dispatch.own_plans_at` zählt nur hinzugefügte Pläne, `train._own_plans` zählt auch einen Basis-Plan mit einer Issue des Branches. Ein Branch, der einen Plan auf main ändert, bekam deshalb keine Plan-Review.
- **#201:** Der Zug lehnt zweimal fälschlich ab. Ein Branch, der einen aktiven Plan löscht, gilt als „unlesbar“. Ein gestapelter Branch, der einen geteilten Plan umbenennt, zählt den Slug doppelt.

## Entscheidungen

- **D1 Ein Eigentümer für „eigene Pläne“ (#204).** `check_review.own_plans(root, base, tip, issues)` liefert `(Pfad, entfenzter Text)` oder None, wenn git es nicht sagen kann. Die Regel ist die des Zugs:
  - Ein Plan zählt, wenn der Branch ihn hinzufügt.
  - Ein umbenannter Plan zählt, wenn sich seine Issues ändern.
  - Ein Plan, der schon auf der Basis liegt, zählt, wenn er eine der Issues des Branches deklariert.
  - Gelöschte Pläne zählen nie.
  - Erfasst werden aktive Pläne, archivierte Pläne und Spec-Kit-Verzeichnisse. Die Identität eines Spec-Kit-Plans ist sein Verzeichnis, gelesen über `plan.md`.

  `train._own_plans` und `dispatch.own_plans_at` rufen diese Funktion auf und filtern danach nur noch nach ihrem Bereich. Der Zug nimmt `.process-work/plans/`. Dispatch nimmt aktive Pläne und Spec-Kit-Verzeichnisse.
- **D2 Ein Eigentümer für „Issues eines Branches“.** `dispatch.branch_issues(root, branch)` ersetzt `train._branch_issues`. Er liefert die führende Zahl des Namens und `issues_of`. Den Issue-Parser eines Plans (`_local_issues`) besitzt künftig `check_review` als `plan_issue_numbers`.
- **D3 Fail-closed in `plan_review_due` (#207).**
  1. `dispatch._git` fängt `UnicodeDecodeError` ab und liefert ihn als git-Fehler zurück. Damit stürzt `start` nicht mehr ab, und `plan_review_due` liefert None (Code-Review).
  2. Schlägt `ls-remote` fehl, liefert `plan_review_due` None, statt „Branch fehlt“ anzunehmen. Dafür gibt es `_remote_head_or_none`.
  3. Mit `remote=True` wird nur der Stand auf origin beurteilt, nie ein lokaler Vorsprung.
  4. Mit `fetch=False`, wie in `--dry-run`, wird nichts geholt. Fehlt das Objekt, ist das Ergebnis None.
  5. Die Integrationsbasis ist die jüngste Merge-Basis aller Integrationsrefs. Ein veraltetes `origin/main` neben einem frischen `main` verschiebt sie nicht mehr.
  6. Ein Plan mit `review-waived:` ist keine fällige Plan-Review.
- **D4 Zug (#201).**
  1. Die Liste der aktiven Pläne für offene Fragen läuft mit `--diff-filter=d`, sodass ein gelöschter Plan nicht mehr gelesen wird.
  2. Die Eindeutigkeit von Slugs zählt Identitäten statt Pfaden. Benennt ein Kandidat einen Plan um, den ein anderer Kandidat hinzufügt (gemessen ab ihrer gemeinsamen Merge-Basis), sind beide Pfade ein Plan. Jeder seiner Slugs zählt dann einmal.
- **D5 Nicht in diesem Release.** `make_review_bundle --plan <issue>` sucht nur per Teilstring im Dateinamen (#207, Punkt 6, dritter Teil). Das bleibt in #207 als Rest.

## Aufgaben

1. `check_review.own_plans` und `plan_issue_numbers`, dazu `dispatch.branch_issues`. Train und Dispatch rufen sie auf. Tests:
   - Ein Basis-Plan mit Branch-Issue zählt, in Dispatch wie im Zug.
   - Ein Basis-Plan ohne Branch-Issue zählt nicht.
   - Ein Spec-Kit-Plan wird über `plan.md` erkannt.
   - Ein Branch ändert einen Plan auf main mit seiner Issue, dann startet `plan_review_due` eine Plan-Review.
2. `plan_review_due` nach D3. Tests für:
   - Nicht-UTF-8-Pfad, kein Absturz und None;
   - fehlgeschlagenes `ls-remote`, Ergebnis None;
   - `remote`, nur origin;
   - `--dry-run`, kein Fetch und kein FETCH_HEAD;
   - veraltetes `origin/main`;
   - Waiver.

   Außerdem ein Test für jeden überlebenden Mutanten:
   - Fetch-Fehler ignoriert;
   - `not base` beziehungsweise Diff-Returncode ignoriert;
   - `--no-renames` entfernt;
   - `phase == "review"`-Guard entfernt.
3. Zug nach D4. Tests:
   - gelöschter aktiver Plan, keine „unlesbar“-Ablehnung;
   - gestapelte Umbenennung, Slug eindeutig, Board über den Slug.
4. CHANGELOG, Refute und Review, Release.

## Unabhängige Durchsetzung

Die Review- und Merge-Gates (`check_review`, `merge_route`) bleiben die harte Grenze. D1 erweitert nur die Erkennung einer fälligen Plan-Review und die Zählung von Work-IDs. D3 wählt in jedem Zweifelsfall den sicheren Ausgang: Code-Review, und die Session sagt, wenn kein Code da ist. D4 hebt zwei Fehlablehnungen auf, ohne eine Prüfung wegzunehmen.

## Plan-Review Runde 1 — Änderungen

Ergebnis: „go with changes“, 4 MAJOR und 5 MINOR. Wo diese Punkte den Entscheidungen oben widersprechen, gelten sie.

- **P1 Herkunft (MAJOR-1).** `own_plans` liefert zu jedem Plan, ob der Branch ihn hinzugefügt hat. Dispatch zählt Basis-Pläne nur dort, wo eine Plan-Review erkannt oder ihr Pass geprüft wird (`plan_review_state_at` mit Branch, `plan_review_due`). Abschluss (`work_complete_on_origin`) und Tier der nächsten Phase (`plan_tier_on_origin`) fragen weiter nur hinzugefügte Pläne. Sonst würde ein Epic-Plan, den ein Paket abhakt, den `pushed`-Schritt des Pakets blockieren.
- **P2 Spec Kit (MAJOR-2).** Die Spec-Kit-Identität bleibt, wie sie ist: Dispatch erkennt `tasks.md`, und Tier und IDs kommen aus `plan.md`. Die Vereinheitlichung über das Verzeichnis kommt zu D5 (Rest in #207).
- **P3 Dekodierung (MAJOR-3).** `dispatch._git` dekodiert UTF-8 mit `surrogateescape`. Es stürzt nie ab und liefert keine leere Antwort, die ein Aufrufer als „nichts da“ lesen würde. `plan_review_due` liefert None, sobald ein geänderter Pfad nicht als UTF-8 lesbar ist.
- **P4 Branch durchreichen (MAJOR-4).** `plan_review_state(root, wt, branch)` und `plan_review_state_at(root, head, branch)` bekommen den Branch. Die Chain ruft beide mit dem Branch auf.
- **P5 Integrationsbasis (MINOR-5).** D3.5 ist zurückgestellt. Eine dritte Regel für den Fork-Punkt neben der des Gates ist schlechter als die bekannte Lücke. Die Lücke steht nicht in den EARS-Kriterien von #207, und die sichere Richtung bleibt: Ein veraltetes `origin/main` führt zu einer Code-Review.
- **P6 Parser (MINOR-6).** Der Parser heißt `check_review.local_issue_numbers`. Die Umbenennungsprüfung in Dispatch vergleicht jetzt lokale Issue-Nummern statt roher `issue:`-Tokens.
- **P7 Callback (MINOR-7).** `own_plans` behält den `read`-Callback. Der Zug liest damit den gemergten Baum und meldet unlesbare Pläne.
- **P8 Prompt (MINOR-9).** Der Prompt einer Plan-Review nennt die fälligen Pläne mit Pfad. Ein Epic-Plan, den ein Paket ändert, ist nicht der Plan der Paket-Issue.
- **P9 Zug (zu D4.2).** Gruppiert werden nur Umbenennungen (R) zwischen den neuen Pfaden zweier Kandidaten, nie die eigenen Namen der Basis oder des Archivs. Ein Diff, den git nicht liefert, gilt als unlesbar. Ein Umschreiben unter 50 % Ähnlichkeit bleibt zwei Pläne, also fail closed. Ein Negativtest prüft, dass ein echter Namensvetter auf einem dritten Kandidaten weiter zählt.

## Refute Runde 1 — Änderungen

Ergebnis: Block. Der Lauf fand einen BLOCKER, einen MAJOR und zwei MINOR, alle behoben.

- **R1 Rückfallregel (BLOCKER).** Ein Paket-Branch eines Epics, der den Epic-Plan auf main abhakt, zählte diesen als eigenen Plan. Die Chain wartete daraufhin für immer auf einen Epic-Pass, den die Plan-Review des Pakets nie liefert. Jetzt gilt in Dispatch: Ein Branch, der einen eigenen Plan hinzufügt, wird nach diesem beurteilt. Nur ein Branch ohne eigenen Plan wird nach den main-Plänen seiner Issues beurteilt, die er ändert. Damit bleibt der Fall aus #204 gedeckt.
- **R2 Verdrahtung (MAJOR).** Die Verdrahtung hat jetzt Tests:
  - Die Chain reicht den Branch beim Pass-Check weiter.
  - Die Chain reicht den Branch auch beim Schritt planned→execute weiter.
  - `start` übergibt die Plan-Pfade an den Prompt, auch bei `--plan-review` und in der Chain.
  - `start` reicht `remote` weiter.
- **R3 Fällige Pläne (MINOR).** Prompt und Wartemeldung nennen nur Pläne ab Tier 2 ohne Pass (`uncleared_plans`), nicht jeden eigenen Plan.
- **R4 Kosten (MINOR).** `_stacked_renames` überspringt Kandidatenpaare, die über der Basis keinen gemeinsamen Commit haben.

## Refute Runde 2 — Änderungen

Ergebnis: pass mit einem MAJOR. Der MAJOR und zwei MINOR sind behoben.

- **R5 Unterscheidung nach dispatchter Issue (MAJOR).** Die Rückfallregel aus R1 ließ einen Fall durch: Ein Branch fügt einen Delta-Plan hinzu und ändert dabei den Tier-3-Plan derselben Issue auf main. Dieser Plan bekam dann keine Plan-Review, was #204 widerspricht. Neue Regel: Basis-Pläne zählen für die Issues, für die der Branch dispatcht wurde (`review_issues`). Ohne Dispatch-Eintrag zählt die führende Zahl des Branch-Namens. Ein Paket, das für #72 dispatcht wurde, liest den Epic-Plan von #70 nicht. Ein Branch für #70 liest den main-Plan von #70, ob er einen eigenen Plan hinzufügt oder nicht.
- **R6 Remote (MINOR).** Eine erzwungene oder verkettete Plan-Review einer Remote-Session nennt die Pläne nach dem Stand auf origin.
- **R7 Mehrere Pläne (NIT).** Der Prompt verlangt einen Pass je Plan. Die Wartemeldung der Chain nennt die offenen Pläne, und ein Test prüft das.
