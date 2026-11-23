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

Kopiere `templates/build_slice.py` in den Lauf-Ordner und ändere es. Bausteine:

| Baustein | Zweck |
|---|---|
| `flow.agent(prompt, label=, role=, cwd=, required=)` | ein Arbeiter; liefert sein JSON-Ergebnis oder `None` |
| `flow.pipeline(items, stufe1, stufe2, …)` | je Element eine Kette, keines wartet auf die anderen |
| `flow.parallel([…])` | alle zugleich, wartet auf alle |
| `flow.worktree(label, base)` | eigener Worktree und Zweig für einen schreibenden Arbeiter |
| `flow.ownership(branch, base, owns, shared)` | welche geänderten Dateien dem Arbeiter nicht gehören |
| `flow.integrate(worktree, branches)` | lokal zusammenführen; Konflikte werden gemeldet, nicht gelöst |
| `flow.check(argv, cwd)` | ein Prüfbefehl auf dem zusammengeführten Stand |

Regeln für das Skript:

- **`pipeline` ist der Normalfall.** `parallel` nur, wenn du wirklich alle
  Ergebnisse zusammen brauchst (Dubletten entfernen, zusammenführen).
- **Jeder schreibende Arbeiter bekommt `flow.worktree`.** Lesende Arbeiter
  laufen im Repo.
- **Ein Arbeiter bekommt alles im Auftrag:** Referenz, eigene Dateien,
  verbotene Dateien, Tests, Ergebnisformat. Er kennt deinen Verlauf nicht.
- **Verlange ein Ergebnisformat** über `required`. Prosa wertest du nicht aus.
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
- **Scheiben landen laufend, eine nach der anderen**, sobald sie stabil sind.
  Ein Review deckt immer den ganzen Zweig ab seinem Abzweig von main; ein
  Stapel ungelandeter Scheiben macht das letzte Review so groß wie das Epic.
- Die nächste Scheibe zweigt vom neuen main ab.
- Die volle Suite läuft am Zug. Lokal ausgewählte Tests ersetzen sie nicht.

## Leitplanken

Die Bausteine erzwingen: Obergrenze für Arbeiter gleichzeitig (Standard 4) und
je Lauf (40), Zeitgrenze je Arbeiter (30 Minuten), eigener Worktree je
schreibendem Arbeiter, keine Zusammenführung auf `main`/`master`, kein Push.
Heb eine Grenze nur an, wenn die Aufgabe es verlangt, und schreib den Grund
ins Protokoll. Vier bis sechs parallele Issues kann ein Integrationsowner
aufnehmen; mehr Breite verschiebt die Arbeit nur ans Zusammenführen.

Ein Arbeiter aus deinem Lauf ist nie der Reviewer am Landen.
