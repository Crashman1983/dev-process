# Entwurf: Skill „Epic-Scheibe"

Stand 2026-11-23. Ein Entwurf zum Ausprobieren in Kenni, kein Teil des
Templates. Er folgt aus der Frage, ob sich das schnelle, parallele Bauen aus
der KenniHybrid-Sitzung im Dev-Prozess abbilden lässt, ohne an ein Harness
gebunden zu sein.

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

## Was geprüft ist und was nicht

Geprüft, mit einem Attrappen-Arbeiter in einem Wegwerf-Repository:

- Das Blatt wird abgelehnt bei fehlender Referenz, überlappenden Dateien und
  einem Tier-3-Issue; alle Mängel kommen in einer Meldung.
- Drei Issues bauen parallel in eigenen Worktrees und werden zusammengeführt.
- Ein Arbeiter, der eine gemeinsame Datei ändert, bekommt eine Korrekturrunde;
  sein Wunsch landet als `shared_requests` im Bericht.
- Ein zweiter Lauf nimmt alle fertigen Ergebnisse aus dem Protokoll.
- Zeitgrenze, Obergrenze je Lauf, fehlende Pflichtschlüssel und ein Konflikt
  beim Zusammenführen verhalten sich wie beschrieben; `integrate` verweigert
  einen Worktree auf `main`.
- `ruff check` und `ruff format --check` sind sauber.

Nicht geprüft:

- **Kein Lauf mit einem echten Harness.** Ob Claude und Codex ohne Dialog
  zuverlässig die Ergebnisdatei schreiben, ist offen.
- **Die Befehle in `workers.example.json` sind Beispiele.** Die Schalter für
  Codex habe ich nicht nachgeschlagen; Kenni hat für hängende Codex-Läufe
  eigene Regeln (`docs/dev/codex-cli-policy.md`), die hier noch fehlen.
- **`find_verify.py` und `judge_panel.py` sind nur auf Lint geprüft**, nicht
  durchgespielt.
- **Kein Test im Repository.** Die Prüfung oben lief aus dem Arbeitsordner
  der Sitzung; für das Template bräuchte es Tests in `tests/`.
- **Verbrauch.** Jeder Arbeiter ist eine ganze Sitzung und liest seinen
  Kontext neu ein.

## Was vor einem Versuch in Kenni zu entscheiden ist

1. **Die eine Abschwächung:** Für Tier-2-Issues einer Scheibe ersetzt das
   einmal geprüfte Epic-Blatt das Plan-Review je Issue. Das entscheidet der
   Owner.
2. **Die Erlaubnis:** Im Epic-Vorgehen darf der Integrationsowner solche
   Läufe starten, ohne jedes Mal zu fragen.
3. **Die Zuordnung der Rollen:** welches Modell baut, welches prüft
   (`workers.json` im Projekt).

Unverändert bleiben sollen der Rundendeckel je Arbeit und die Regel, dass ein
Review den ganzen Zweig ab seinem Abzweig von main deckt. Der Skill arbeitet
mit beiden, indem Scheiben klein bleiben und laufend landen.

## Übernahme in Kenni

- Ordner `epic-slice/` nach `.agents/skills/epic-slice/` kopieren (dort liest
  Codex seine Skills) und für Claude verlinken oder nach `.claude/skills/`
  spiegeln.
- `workers.json` im Projekt anlegen.
- Eine Zeile in den Projektregeln, die das Vorgehen und seine Stelle benennt.
- Den ersten Versuch an einer Scheibe mit vier bis fünf kleinen UI-Issues
  fahren, einmal mit Claude als steuerndem Agenten und einmal mit Codex.

## Wohin es später gehört

Trägt das Muster, wandert `flow.py` nach dem Freeze (bis 2026-12-08) in das
Prozess-Werkzeug neben `dispatch.py`, das Arbeiter schon je Phase und Policy
startet. Der Skill bleibt als Handbuch.
