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
