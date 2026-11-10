# Kenni-Suite: Aufteilung in vier Teile (2026-11-10)

Hilfsdateien zum Bericht `../2026-11-10-prozess-audit.md`, Abschnitte 22 und 23. Stand von Kenni: `f0f03360ef`.

- `shard1.txt` bis `shard4.txt`: die Backend-Tests in vier überschneidungsfreien Teilen, nach gemessener Testzeit ausgeglichen (je rund 1.240 s Testzeit mit Coverage). Jede Datei ist eine Liste von Pfaden relativ zu `backend/`, als Argumente für `pytest`.
Die Auswerteskripte der Sitzung (Aufteilung, Coverage je Test, betroffene Tests je Merge) liegen nicht im Repository; sie genügen dem Linter nicht und waren Einmalwerkzeuge. Ihr Vorgehen beschreibt der Bericht.

Ein Teil läuft so, aus `backend/` heraus, mit eingerichteter Umgebung (`uv sync --group dev`, `bubblewrap` installiert):

    .venv/bin/python -m pytest $(cat shardN.txt) -n 4 -q -m 'not network' -p no:cacheprovider
