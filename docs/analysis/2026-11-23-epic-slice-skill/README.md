# Entwurf: Skill „Epic-Scheibe"

Stand 2026-11-23, zweite Fassung nach einem unabhängigen Review. Ein Entwurf
zum Ausprobieren in Kenni, kein Teil des Templates. Er folgt aus der Frage, ob
sich das schnelle, parallele Bauen aus der KenniHybrid-Sitzung im Dev-Prozess
abbilden lässt, ohne an ein Harness gebunden zu sein.

## Was der Ordner enthält

| Datei | Inhalt |
|---|---|
| `epic-slice/SKILL.md` | die Anleitung für den steuernden Agenten |
| `epic-slice/reference/epic-sheet.md` | Format und Pflichtfelder des Epic-Blatts |
| `epic-slice/reference/workers.example.json` | Beispiel für die Zuordnung Rolle → Startbefehl |
| `epic-slice/scripts/flow.py` | die Bausteine: Arbeiter, Kette, Worktree, Besitzprüfung, Zusammenführen |
| `epic-slice/templates/build_slice.py` | Vorlage: Scheibe parallel bauen und zusammenführen |
| `epic-slice/templates/find_verify.py` | Vorlage: finden und widerlegen lassen |
| `epic-slice/templates/judge_panel.py` | Vorlage: mehrere Entwürfe, dann Kritik |

## Die Idee in drei Sätzen

Der steuernde Agent schreibt den Ablauf zur Laufzeit selbst, als kurzes
Python-Skript gegen wenige Bausteine; das macht ihn so beweglich wie einen
dynamischen Workflow. Ein Arbeiter ist ein Aufruf eines beliebigen Harness
ohne Dialog, und er liefert sein Ergebnis als JSON-Datei; deshalb hängt nichts
an Claude. Der Prozess hält nur Eingabe (Epic-Blatt) und Ausgabe
(zusammengeführter, geprüfter Stand) fest, und Landen geht den normalen Weg.

## Das Review und was daraus wurde

Ein Agent mit frischem Kontext hat die erste Fassung gelesen und gegen ein
Wegwerf-Repository ausgeführt. Er fand vier Blocker, sechs schwere und acht
mittlere Mängel. Derselben Modellfamilie; ein Review durch eine zweite Familie
steht aus.

Behoben und danach nachgespielt:

| Befund | Jetzt |
|---|---|
| Lauf-Ordner und Worktrees im verfolgten Baum | liegen außerhalb; ein Ordner im verfolgten Baum wird abgelehnt |
| Nicht committete Arbeit galt als zusammengeführt | `unfinished()` meldet es, das Issue landet unter `failed_issues` |
| Fortsetzen nahm ein altes Prüfurteil für neuen Code | `state=` bindet ein Ergebnis an den Stand; der Prüfer läuft neu |
| Fortsetzen verlor `shared_requests` | kommen über `recall()` aus dem Protokoll |
| Umbenennen umging die Besitzprüfung | Diff ohne Umbenennungserkennung |
| Abbruch ließ Arbeiter weiterlaufen | Arbeiter enden mit, wartende starten nicht mehr, ein Lauf je Ordner |
| Kopierte Vorlage fand `flow.py` nicht | `EPIC_SLICE_HOME` |
| Eine greifende Leitplanke kippte den Lauf ohne Bericht | beendet nur ihren Eintrag |
| Ergebnistypen ungeprüft | `required` mit Typen |
| Obergrenze galt je Prozess | zählt je Lauf-Ordner über Neustarts |
| Mustersprache mit Fallen | nur `*` und `?`, Ordner ohne Platzhalter, Klammern wörtlich |
| `tier` fehlend oder falsch getippt | Pflichtfeld, wird gemeldet statt abzustürzen |
| „Kein Push" nur als Text | Arbeiter starten mit ungültiger Push-Adresse; `check` und `git` verweigern `push`; der Text sagt, dass das nur Versehen fängt |

Im Entwurf beschrieben, aber nicht gelöst:

- **Die Scheibe braucht einen Plan, den Kennis Gates annehmen.** Das Blatt hat
  weder die Kriterien in fester Form noch die Pflichtabschnitte. Der Skill
  verlangt jetzt einen Plan je Scheibe vor dem ersten Push und benennt den
  Zweig `<epic>-<scheibe>`; wie dieser Plan aussieht und ob Kennis Werkzeuge
  den Zweignamen so zuordnen, ist nicht ausprobiert.
- **Der Rundendeckel zählt je Arbeit.** Vier bis fünf Issues teilen sich drei
  Runden. Das ist gewollt unverändert, begrenzt aber die Scheibengröße.
- **Merge-Commits im Scheibenzweig.** Kennis `finish` rebased; gelöste
  Konflikte müssten dabei neu gelöst werden. Nicht ausprobiert.
- **Ein Arbeiter, der sich aus seiner Prozessgruppe löst,** überlebt Zeitgrenze
  und Abbruch.

## Was geprüft ist

Mit einem Attrappen-Arbeiter in einem Wegwerf-Repository mit eigenem Remote:

- Sechs Issues parallel: vier werden zusammengeführt, eines ohne Commit und
  eines mit verschobener gemeinsamer Datei landen unter `failed_issues`.
- Der Push-Versuch eines Arbeiters scheitert; das Remote bleibt unverändert.
- Der Hauptcheckout bleibt sauber.
- Fortsetzen übernimmt fertige Ergebnisse und behält `shared_requests`; nach
  einem neuen Commit im Worktree läuft der Prüfer neu.
- Abbruch mit SIGINT: kein Arbeiter überlebt, die Sperre ist frei.
- `find_verify.py` und `judge_panel.py` laufen durch, auch mit einem
  scheiternden Arbeiter, falschem Typ und kaputtem JSON.
- Verweigert werden: Lauf-Ordner im Baum, zweiter Lauf im selben Ordner,
  `integrate` außerhalb der eigenen Worktrees, `git push` über `check` und `git`.
- `ruff check` und `ruff format --check` sind sauber.

## Was nicht geprüft ist

- **Kein Lauf mit einem echten Harness.** Ob Claude, Codex oder Copilot ohne
  Dialog zuverlässig die Ergebnisdatei schreiben, ist offen; ebenso, ob eine
  Sitzung in einem neuen Worktree eine Vertrauensabfrage stellt.
- **Die Befehle in `workers.example.json` sind Beispiele.** Die Schalter für
  Codex sind nicht nachgeschlagen; Kennis Regeln für hängende Codex-Läufe
  (`docs/dev/codex-cli-policy.md`) sind nicht eingearbeitet. Ein Eintrag für
  Copilot fehlt.
- **Kein Gate von Kenni wurde ausgeführt.** Die Aussagen zur Passung sind
  gelesen, nicht gelaufen.
- **Kein Test im Repository.** Die Prüfung lief aus dem Arbeitsordner der
  Sitzung; für das Template bräuchte es Tests in `tests/`.
- **Verbrauch und Last.** Jeder Arbeiter ist eine ganze Sitzung.

## Voraussetzungen vor einem Versuch in Kenni

1. **Plan je Scheibe:** eine Vorlage, die Kennis Planstruktur erfüllt und die
   Kriterien der Issues sammelt; ein Probe-Push zeigt, ob die Gates sie annehmen.
2. **Abhängigkeiten je Worktree:** `bootstrap` im Blatt mit Kennis Befehlen
   für Backend und Frontend. Ohne sie laufen weder Tests noch Build.
3. **Testlauf-Regel:** Kennis Sperre für parallele Testläufe lässt einen
   zweiten größeren Lauf warten und abbrechen. `max_parallel` und die Tests je
   Issue müssen dazu passen.
4. **Rechte der Arbeiter ohne Dialog:** committen und Tests starten ohne
   Rückfrage; für Codex entsprechend in dessen Sandbox. Arbeiter brauchen
   Zugriff auf die Issues.
5. **Geprüfte Startbefehle** in `workers.json`; je Harness ein einzelner
   Arbeiter als Rauchtest.
6. **Der Rechner:** Auf dem Gate-Host konkurrieren die Arbeiter mit dem Zug.
7. **Drei Entscheidungen des Owners:**
   - Das einmal geprüfte Blatt ersetzt für Tier-2-Issues einer Scheibe das
     Plan-Review je Issue.
   - Der Integrationsowner darf solche Läufe ohne Rückfrage starten.
   - Welches Modell baut und welches prüft.

Unverändert bleiben sollen der Rundendeckel je Arbeit und die Regel, dass ein
Review den ganzen Zweig ab seinem Abzweig von main deckt.

## Übernahme in Kenni

- Ordner `epic-slice/` nach `.agents/skills/epic-slice/` kopieren (dort liest
  Codex seine Skills) und für Claude nach `.claude/skills/` spiegeln; den
  Ordner gibt es dort noch nicht.
- `FLOW_ROOT` auf Kennis Worktree-Wurzel setzen.
- `workers.json` im Projekt anlegen.
- Eine Zeile in den Projektregeln, die das Vorgehen und seine Stelle benennt.
- Den ersten Versuch an einer Scheibe mit vier bis fünf kleinen UI-Issues
  fahren, einmal mit Claude als steuerndem Agenten und einmal mit Codex.

## Wohin es später gehört

Trägt das Muster, wandert `flow.py` nach dem Freeze (bis 2026-12-08) in das
Prozess-Werkzeug neben `dispatch.py`, das Arbeiter schon je Phase und Policy
startet. Der Skill bleibt als Handbuch.
