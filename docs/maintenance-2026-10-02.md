# Wartung: Issue-Abgleich, Laufzeiten und Template-Updates

Stand: 2. Oktober 2026. Ausgangspunkt ist Commit `2fbfc7a` auf `main`.
Die Prüfungen verwenden dieses Repository und lokale Testprojekte.

## Issue-Abgleich

| Issue | Ergebnis | Nachweis / Rest |
| --- | --- | --- |
| #45 | Erledigt und geschlossen | `finish.py` nutzt `gate_runner_argv`; nicht startbare Gates werden als `NOT RUNNABLE` benannt, Fehlerausgaben enthalten auch stderr. `test_gate_invoke.py`, `test_finish.py`. |
| #132 | Erledigt und geschlossen | Reviews decken ihre eigenen `base..head`-Bereiche ab. Der neue vollständige A→B→C-Test in `test_downstream_residuals.py` prüft überlappende Dateien, einen späten unreviewten Commit und einen manipulierten Digest. |
| #15 / SP33 | Akzeptanzkriterien erfüllt; Sprachfixture vervollständigt | Tier-Range, REVIEW/GRADE-Bullets und Tilde-Fences, Report-Header, leere ADR-Abschnitte, Kampagnen-Refs und skalare `code_roots` haben Regressionstests. Die früheren github-master/Capability-Contract-Pfade wurden inzwischen entfernt. Die Sprachprüfung aktiviert nun auch speckit, sbom und telemetry. |
| #16 / SP34 | Akzeptanzkriterien erfüllt | Archivierung hat einen Platz vor Review/Integration; Hooks werden nach dem Baseline-Commit installiert; Story-/Report-Waiver existieren; neutraler Kernel, exakte Bundle-Grammatik, Tier-1-Self-Check und Versionswarnung sind vorhanden. Der CI-Job erhält zusätzlich einen expliziten Namen. |
| #17 / SP35 | Akzeptanzkriterien erfüllt, letzte Inbox-Lücke behoben | Aktive Modul-Pointer, Quick-Leseschnitt, Routingtabelle, SSOT-Kollisionen und Mid-Size-Floor sind dokumentiert und getestet. Prime liest bei gefüllter Inbox jetzt deren Inhalt in allen drei Harness-Adaptern. |
| #18 | Gate-Breaker-Bericht durch SP33 abgearbeitet | Siehe #15 und die entsprechenden Gate-Regressionen. |
| #19 | Weiter offen | Die großen Kohärenzbefunde sind behoben. Ein echter Rest bleibt: Existenz und Zuordnung von Tier-3-Reports werden noch nicht vollständig mit REVIEW-Einträgen abgeglichen. Dieser Bericht bleibt der konkrete Tracker dafür. |
| #20 | Cold-Start-Bericht abgearbeitet | SP34 plus bestehende Artefakt-Routingtabelle; ADR-Dokumentation verlangt einen Datensatz je wesentlicher Entscheidung. |
| #21 | Economics-Bericht durch SP35 und Messung abgearbeitet | Verbindliche Lektüre ist geroutet; Inbox wird gelesen; Kollisionsrisiken und Core-Gate-Floor sind benannt. Die verbleibende feste Interpreter-Last ist unten gemessen. |
| #14 | Kampagnen-Parent bleibt offen | #19 enthält weiterhin einen offenen Befund. |

Die Abschlussreferenzen im PR schließen #15, #16, #17, #18, #20 und #21 beim
Merge. Ein offener Befund wird nicht durch Schließen des Kampagnen-Parents verdeckt.

## Laufzeiten (#140)

Gemessen in dieser Cloud-Umgebung mit Python 3.12 und einem CPU-Limit von vier
Kernen. Die Testsuite wird mit `--dist loadfile` verteilt: Jeder Test einer
Datei bleibt beim selben Worker. Render-Caches bleiben pro Worker isoliert.

- Ausgangssuite: **1.367 bestanden, 322,45 Sekunden**, ein Prozess.
- Vier Worker: **1.389 bestanden, 100,74 Sekunden** (rund 69 % weniger
  Laufzeit trotz 22 zusätzlicher Tests). Ein grüner Lauf je Konfiguration,
  keine statistische Langzeitmessung.
- Zwei Worker: **1.389 bestanden, 183,34 Sekunden** (rund 43 % weniger
  Laufzeit als seriell). Anschließend kam ein zusätzlicher Ownership-Regressionstest
  hinzu; die Vollsuite danach besteht mit **1.390 Tests in 100,45 Sekunden**
  bei vier Workern.
- Anschließender Changelog-Format-Fix: **28 Verifikations-/Update-Regressionen
  bestanden**; die aktuelle Testsammlung umfasst 1.391 Fälle.
- CI verwendet zwei Worker. Der portable Linux/macOS/Windows-Smoke bleibt
  seriell; für dessen kleine Testmenge lohnt sich der zusätzliche Startaufwand nicht.
- Die frühen parallelen Läufe zeigten Cache-Dateien aus einem CLI-Import und
  einen Fehler im neuen Train-Testaufruf. Sie gelten nicht als grüne Leistungsnachweise.

Reproduktion:

```sh
uv run --frozen pytest --durations=30 --junitxml=/tmp/serial.xml
uv run --frozen pytest -n 2 --dist loadfile --durations=30 --junitxml=/tmp/parallel.xml
uv run --frozen python tools/benchmark_gates.py --runs 5
```

Fünf Wiederholungen je frisch gerendertem Profil, ohne Projekthistorie:

| Prüfung | Median | Einzelwerte in Sekunden |
| --- | ---: | --- |
| Minimalprofil, alle Gates | 0,3307 s | 0,3197 / 0,3320 / 0,3236 / 0,3314 / 0,3307 |
| Standardprofil, alle Gates | 0,8205 s | 1,3591 / 0,8363 / 0,8067 / 0,8205 / 0,7969 |
| Minimalprofil, Review-Gate | 0,0848 s | 0,0848 / 0,0810 / 0,0857 / 0,0861 / 0,0837 |
| Standardprofil, Review-Gate | 0,0814 s | 0,0812 / 0,0831 / 0,0789 / 0,0814 / 0,0824 |

Der Grundaufwand rechtfertigt hier keinen Umbau aller Gates in einen gemeinsamen
Interpreter. Ein großer History-/Tracker-Effekt lässt sich aus diesen leeren
Testprojekten nicht ableiten. #140 bleibt für vier Wochen reale Phase-/Token-KPIs
und Messungen an großen Projekt-Historien offen. Eine aktuelle Pipeline läuft
bereits nur einmal pro PR-Push; ein zweiter Trigger wurde nicht hinzugefügt.
Der Release-Tool-Schalter `--no-suite` existiert bereits; die Änderung überspringt
keine Suite automatisch auf Basis einer unbestätigten alten Prüfung.

## Verifizierte Template-Updates (#137)

`template_verify.py` liest die Quelle aus dem Integrations-Baseline-Commit,
löst Release-Tags auf Git-SHAs auf und rendert beide Releases erneut mit den
jeweiligen Antworten. Für eine Ausnahme müssen alte und neue Projektdatei
jeweils zum Render passen. Inhalte, Ausführungsrechte und Symlink-Ziele zählen.
Auch eine Pin-Änderung ohne angewendete Template-Änderung wird als Projektdelta erkannt.

Lokale/owned Dateien, Hooks, Makefiles und Tests bleiben Projektdelta. Ein
manuell bearbeitetes Template oder eine verlorene lokale Anpassung benötigt
Review. Ein gespeicherter Report kann keine Ausnahme gewähren: Gate, Finish
und Train berechnen die Evidenz neu; nur unveränderliche Git-Objekte werden
innerhalb eines Aufrufs zwischengespeichert.

Ein reines, bestätigtes Update braucht Gates und Projekttests, keinen REVIEW.
Projektdelta braucht ein frisches, digestgebundenes Tier-2-Review; Änderungen
an Gate-Skripten, Helfern oder Konfiguration bleiben konservativ Tier 3.
Die Verhaltenshinweise sind der berechnete Changelog-Diff der beiden Release-SHAs;
das funktioniert auch mit den fett gesetzten Versionsabschnitten dieses Templates.
Der Owner/Steward bestätigt die ausgegebenen Release-Verhaltenshinweise mit
einem an Baseline und Release-SHA gebundenen Acknowledgment. Diese Bestätigung
ist eine attestierte Entscheidung; Dateiprovenienz wird weiterhin berechnet.

Die Regressionen prüfen reine Updates, Einzeländerungen, verlorene Anpassungen,
Deleted Tests, Template-Deletion, Rechte/Symlinks, fehlende Antworten oder
Render, HEAD-Pins, geänderte Quellen, andere Antwort-Metadaten, gefälschte
Reports, Review-Frische, Tier-3-Migrationen sowie Finish und Train.
