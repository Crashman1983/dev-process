# Kenni-Suite: Aufteilung und Auswerteskripte (2026-11-10)

Hilfsdateien zum Bericht `../2026-11-10-prozess-audit.md`, Abschnitte 22 und 23. Stand von Kenni: `f0f03360ef`.

- `shard1.txt` bis `shard4.txt`: die Backend-Tests in vier überschneidungsfreien Teilen, nach gemessener Testzeit ausgeglichen (je rund 1.240 s Testzeit mit Coverage). Jede Datei ist eine Liste von Pfaden relativ zu `backend/`, als Argumente für `pytest`.
- `shards.py`: erzeugt die Teile aus einer JUnit-Datei eines vollen Laufs.
- `cov.py`: wertet einen Lauf mit `--cov-context=test` aus (eindeutig abgedeckte Zeilen je Test).
- `impact.py`: spielt an den Train-Merges durch, welcher Anteil der Suite-Zeit die geänderten Dateien ausführt.

Die Skripte erwarten als Argument ein Verzeichnis mit `junit3.xml` und `.coverage` und den Kenni-Klon unter `/home/user/kenni`; sie sind Auswertungswerkzeuge einer einzelnen Sitzung, kein gepflegter Code.

Ein Teil läuft so, aus `backend/` heraus, mit eingerichteter Umgebung (`uv sync --group dev`, `bubblewrap` installiert):

    .venv/bin/python -m pytest $(cat shardN.txt) -n 4 -q -m 'not network' -p no:cacheprovider
