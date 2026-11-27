---
name: "epic-slice"
description: "Mehrere zusammengehörige Issues eines Epics parallel bauen, je Issue schmal prüfen, lokal zusammenführen und als Scheibe landen. Nutzen, wenn ein Epic ab etwa vier zusammengehörigen Issues ansteht oder wenn eine Aufgabe einen selbst geschriebenen Ablauf über mehrere Arbeiter braucht (auffächern, prüfen, einsammeln). Nicht für ein einzelnes Issue und nicht für Tier-3-Arbeit."
---

# Epic-Scheibe

Du steuerst den Bau einer Scheibe: mehrere Issues eines Epics, parallel von
Arbeitern gebaut, von dir zusammengeführt. Den Ablauf schreibst du selbst als
kurzes Python-Skript gegen `scripts/flow.py`. Die Vorlagen unter `templates/`
sind Ausgangspunkte, die du für die Aufgabe änderst.

Der Prozess prüft hier das Ergebnis, nicht den Weg. Fest sind die Eingabe (das
Epic-Blatt) und die Ausgabe (ein zusammengeführter Stand, der seine Prüfungen
besteht und am Landen unabhängig geprüft wird). Alles dazwischen entscheidest du.

## Wann, wann nicht

Nutze das Vorgehen, wenn alle drei Punkte gelten:

- mindestens vier Issues, die dieselbe Fläche und dieselbe Referenz teilen;
- jedes Issue lässt sich auf eigene Dateien begrenzen;
- keines der Issues ist Tier 3.

Sonst gilt der normale Weg je Issue. Tier-3-Teile (Auth, Migration, API-Vertrag,
Persistenz, Scheduler) laufen immer regulär und vor der Scheibe, die auf ihnen
aufbaut. Sie stehen im Blatt unter `regular`.

## Schritt 1: das Epic-Blatt

Ohne Blatt startest du keinen Arbeiter. Format und Pflichtfelder stehen in
`reference/epic-sheet.md`; `load_sheet()` prüft sie und nennt alle Mängel auf
einmal. Das Blatt klärt vor dem Auffächern, was nachher nicht mehr billig zu
klären ist:

- **Referenz:** gegen welchen Stand gebaut und verglichen wird, und wie ein
  Arbeiter prüft, dass er ihn hat. Ein Tag reicht nur, wenn er der Stand ist,
  den der Owner am Gerät sieht.
- **Querschnittsverhalten mit Owner:** alles, was mehrere Issues berührt und
  keinem gehört (Kopfzeile, Scrollverhalten, Navigation, Fehlerzustände).
- **Gemeinsame Dateien:** Registry, Tokens, Routen, API-Vertrag, geteilte
  Komponenten. Die ändert nur der Integrationsowner.
- **Scheiben:** welche Issues zusammen landen, mit den Dateien je Issue.

Das Blatt wird einmal unabhängig geprüft, bevor gebaut wird. Es ersetzt für die
Tier-2-Issues der Scheibe das Plan-Review je Issue. Diese Abschwächung gilt nur,
wenn der Owner sie für das Projekt entschieden hat; steht die Entscheidung
nicht in den Projektregeln, frag ihn.

## Schritt 2: den Ablauf schreiben

Kopiere `templates/build_slice.py` und ändere es. Liegt die Kopie nicht mehr im
Skill-Ordner, setz `EPIC_SLICE_HOME` auf ihn, damit sie `flow.py` findet. Der
Lauf-Ordner mit Protokoll und Worktrees liegt außerhalb des Checkouts
(`default_run_dir()`: `$FLOW_ROOT/<epic>-<scheibe>`, sonst neben dem Repo); einen
Ordner im verfolgten Baum lehnt `Flow` ab. Bausteine:

| Baustein | Zweck |
|---|---|
| `flow.agent(prompt, label=, role=, cwd=, required=, state=)` | ein Arbeiter; liefert sein JSON-Ergebnis oder `None` |
| `flow.pipeline(items, stufe1, stufe2, …)` | je Element eine Kette, keines wartet auf die anderen |
| `flow.parallel([…])` | alle zugleich, wartet auf alle |
| `flow.worktree(label, base, branch=, bootstrap=)` | eigener Worktree und Zweig; `bootstrap` installiert einmal die Abhängigkeiten |
| `flow.unfinished(path, base)` | warum ein Arbeiterstand nicht übernehmbar ist (nicht committet, kein Commit) |
| `flow.ownership(branch, base, owns, shared)` | welche geänderten Dateien dem Arbeiter nicht gehören |
| `flow.recall(label)` | das letzte gültige Ergebnis unter einem Label, auch aus einem früheren Lauf |
| `flow.integrate(worktree, branches)` | lokal zusammenführen; Konflikte werden gemeldet, nicht gelöst |
| `flow.check(argv, cwd)` | ein Prüfbefehl auf dem zusammengeführten Stand |

Regeln für das Skript:

- **`pipeline` ist der Normalfall.** `parallel` nur, wenn du wirklich alle
  Ergebnisse zusammen brauchst (Dubletten entfernen, zusammenführen).
- **Jeder schreibende Arbeiter bekommt `flow.worktree`.** Lesende Arbeiter
  laufen im Repo.
- **Ein Arbeiter bekommt alles im Auftrag:** Referenz, eigene Dateien,
  verbotene Dateien, Tests, Ergebnisformat. Er kennt deinen Verlauf nicht.
- **Verlange ein Ergebnisformat mit Typen** über `required={"findings": "list"}`.
  Prosa wertest du nicht aus, und ein Text, wo eine Liste stehen soll, gilt als
  gescheitert.
- **Sag, woran ein Ergebnis hängt.** Ein Prüfer bekommt `state=flow.head(worktree)`.
  Ändert sich der Stand, läuft er beim nächsten Mal neu; ohne `state` käme sein
  altes Urteil aus dem Protokoll.
- **Nicht committete Arbeit zählt nicht.** Prüfe mit `flow.unfinished`, bevor du
  zusammenführst.
- **Rollen statt Modelle.** `role="build"`, `"check"`, `"plan"`; welcher Befehl
  und welches Modell dahinterstehen, sagt `workers.json` des Projekts. So kann
  dieselbe Scheibe mit Claude bauen und mit Codex prüfen.
- **Dynamisch heißt: du änderst das Skript zwischen den Wellen.** Fertige
  Aufrufe kommen beim nächsten Lauf aus dem Protokoll; nur Neues läuft.
- **Kein stilles Kürzen.** Begrenzt dein Skript etwas (nur die ersten n Funde,
  keine zweite Korrekturrunde), schreib es mit `flow.log` ins Protokoll.

Die Vorlagen `find_verify.py` (finden und widerlegen lassen) und
`judge_panel.py` (mehrere Entwürfe, dann Kritik) sind für Aufgaben, die keine
Scheibe sind.

## Schritt 3: zusammenführen

Der Lauf endet mit `slice-report.json`. Das ist deine Arbeitsliste als
Integrationsowner:

1. **`shared_requests`:** Änderungen an gemeinsamen Dateien, die die Arbeiter
   brauchen. Die trägst du selbst ein, einmal, im Scheibenzweig.
2. **`conflicts`:** Zweige, die sich nicht zusammenführen ließen. Du löst sie
   oder schickst das Issue in eine Korrekturrunde.
3. **`findings`:** Befunde der Prüfer je Issue. Sie sind Hinweise, kein Attest.
   Was ein Kriterium verfehlt, wird vor dem Landen behoben.
4. **`failed_issues`:** Issues ohne brauchbares Ergebnis. Sie landen nicht mit
   dieser Scheibe.
5. **`checks`:** die Prüfbefehle auf dem zusammengeführten Stand. Bei UI
   bedienst du danach die Oberfläche selbst, Desktop und Mobil.

Unterscheide in deiner Meldung „gebaut", „zusammengeführt und geprüft" und
„auf main".

## Schritt 4: landen

Landen ist nicht Teil des Laufs und geht den normalen Weg des Projekts:

- Der Scheibenzweig geht als eine Arbeit ins unabhängige Review und in den
  Merge-Zug. Die Bausteine pushen nicht und mergen nicht nach main.
- **Die Scheibe braucht einen Plan, den die Gates des Projekts annehmen.** Das
  Epic-Blatt ist dieser Plan nicht von selbst: Die Kriterien aller Issues der
  Scheibe mit ihren Testzeilen und die Pflichtabschnitte des Projekts gehören
  in einen Plan zur Scheibe, bevor der Zweig zum ersten Mal gepusht wird. Der
  Scheibenzweig heißt `<epic>-<scheibe>`, damit die Werkzeuge die Arbeit
  zuordnen können.
- Runden zählen je Arbeit. Eine Scheibe hat denselben Rundendeckel wie ein
  einzelnes Issue; auch deshalb bleibt sie klein.
- **Scheiben landen laufend, eine nach der anderen**, sobald sie stabil sind.
  Ein Review deckt immer den ganzen Zweig ab seinem Abzweig von main; ein
  Stapel ungelandeter Scheiben macht das letzte Review so groß wie das Epic.
- Die nächste Scheibe zweigt vom neuen main ab.
- Die volle Suite läuft am Zug. Lokal ausgewählte Tests ersetzen sie nicht.

## Leitplanken

Die Bausteine halten: Obergrenze für Arbeiter gleichzeitig (Standard 4) und je
Lauf-Ordner über alle Neustarts (40), Zeitgrenze je Arbeiter (30 Minuten), ein
Lauf je Ordner, Zusammenführen nur in einem Worktree dieses Laufs und nie auf
`main`/`master`. Bricht dein Skript ab, enden die Arbeiter mit.
Heb eine Grenze nur an, wenn die Aufgabe es verlangt, und schreib den Grund
ins Protokoll. Vier bis sechs parallele Issues kann ein Integrationsowner
aufnehmen; mehr Breite verschiebt die Arbeit nur ans Zusammenführen.

Was sie nicht halten: Ein Arbeiter ist eine eigene Sitzung mit eigenen Rechten.
Er startet mit einer Git-Einstellung, die `git push` zu den Remotes des Repos
scheitern lässt, und sein Auftrag verbietet Push und Merge. Das fängt Versehen,
keinen Vorsatz. Die Grenze, die hält, ist das Gate des Projekts am Gang nach main.

Ein Arbeiter aus deinem Lauf ist nie der Reviewer am Landen.
