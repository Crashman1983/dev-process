# Plan: Umgebungs-Preflight vor jedem Testlauf

Datum: 2026-10-10 · Issue: #209 · Release: v2.65 · Tier: 3 (Gate-Code: Pre-Push, Train)

## Anlass

In v2.64 hat nur der Zug ein `--preflight`. Ein Branch-Push und `test_select.py run --certify`
starten Tests ohne Prüfung der Umgebung. In Kenni (#2521) kam ein kaputtes Worktree-venv an
einem Tag dreimal als rote certify- und Operator-Tests an. Das kostet Läufe, und der Fehler
sieht aus wie einer im Code. Owner-Entscheidung 2026-10-10: als v2.65 bauen.

## Entscheidungen

- **D1 Konfiguration.** `testing.local.json` bekommt `preflight` (argv, ohne Shell) und
  optional `preflight_timeout` (Sekunden, Default 600). Ein `preflight`, der keine nicht-leere
  argv-Liste ist, macht die Datei ungültig.
- **D2 Ein Eigentümer.** `test_select.run` führt den Preflight aus. Rahmen und `--certify`
  laufen über diese Funktion, also brauchen sie keinen eigenen Aufruf.
- **D3 Zeitpunkt.** Der Preflight läuft nach der Zertifikatsprüfung und nur, wenn Arbeit
  ansteht. Er läuft unter derselben Lane-Haltung, vor dem ersten Testbefehl, im Repo-Root,
  einmal pro Lauf. Ein Zertifikatstreffer oder „nichts zu testen“ braucht keine Umgebung.
- **D4 Rot ist Umgebung.** Exit ≠ 0, Startfehler oder Zeitüberschreitung: kein Test läuft,
  es gibt kein Zertifikat, und der Lauf endet mit Exit 2 („environment“). Der Rahmen gibt
  2 weiter, also wird kein Stempel geschrieben, und `hook_check` meldet das Verdikt. Die
  Meldung nennt den Preflight und seinen Exit, nicht „red“.
- **D5 Zug.** Ohne `--preflight` nimmt der Zug den konfigurierten (`shlex.join` der argv, weil
  der Zug Befehle als Shell-String führt). Ein expliziter `--preflight` gewinnt.

## Aufgaben

1. `testing_config`: Schema für `preflight` und `preflight_timeout`. Tests: gültig, leer,
   String statt Liste, negativer Timeout.
2. `test_select.run`: Preflight nach D2–D4. Tests: rot, also kein Test und Exit 2; grün, also
   Tests laufen; Zertifikatstreffer, also kein Preflight; nichts ausgewählt, also kein
   Preflight; `--certify` rot, also kein Zertifikat; Timeout.
3. `pre_push`: Ein E2E-Test zeigt, dass ein roter Preflight den Push verweigert, keinen Stempel
   schreibt und den Merge-Push genauso behandelt.
4. `train`: Default aus der Konfiguration. Ein Test zeigt, dass der Zug ohne `--preflight`
   bei rotem konfiguriertem Preflight mit `environment` abbricht.
5. Doku (`testing.md`, `train.md`, BOOTSTRAP), CHANGELOG v2.65.0, Refute und Review, Release.

## Unabhängige Durchsetzung

Die Garantien aus v2.64 (Route, Standing-Block, Zertifikatsregeln) bleiben unverändert. Der
Preflight kann einen Lauf nur verhindern, nie einen Test ersetzen.
