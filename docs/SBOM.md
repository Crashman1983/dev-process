# Software Bill of Materials

Stand: 2026-07-04

Diese SBOM beschreibt die Abhaengigkeiten des `dev-process`-Repositorys. Quelle
ist `pyproject.toml` fuer direkte Abhaengigkeiten und `uv.lock` fuer die
vollstaendig aufgeloesten Python-Pakete. Das Repository liefert keine
JavaScript-, Container- oder Systempaket-Lockfiles aus.

## Projekt

| Komponente | Version | Quelle |
|---|---:|---|
| `dev-process` | `1.6.0` | lokales Repository |

## Direkte Python-Abhaengigkeiten

Diese Pakete sind in `pyproject.toml` unter der Dependency-Gruppe `dev`
deklariert. Sie werden fuer Entwicklung, Tests und Template-Rendering im
Upstream-Repository benoetigt.

| Paket | Constraint | Zweck |
|---|---:|---|
| `copier` | `>=9.4` | Template-Rendering und Brownfield-/Greenfield-Kopien |
| `pytest` | `>=8` | automatisierte Tests |
| `ruff` | `>=0.6` | statische Python-Pruefung |
| `pyyaml` | `>=6` | YAML-Parsing fuer Manifest- und Gate-Skripte |

## Geloeste Python-Pakete

Diese Liste ist aus `uv.lock` abgeleitet. Alle Pakete stammen aus
`https://pypi.org/simple`, ausser der virtuellen Projektkomponente
`dev-process`.

| Paket | Version | Direkt | Abhaengigkeiten |
|---|---:|:---:|---|
| `annotated-types` | `0.7.0` | nein | - |
| `colorama` | `0.4.6` | nein | - |
| `copier` | `9.16.0` | ja | `colorama`, `dunamai`, `funcy`, `jinja2`, `jinja2-ansible-filters`, `packaging`, `pathspec`, `platformdirs`, `plumbum`, `pydantic`, `pygments`, `pyyaml`, `questionary` |
| `dunamai` | `1.26.1` | nein | `packaging` |
| `funcy` | `2.0` | nein | - |
| `iniconfig` | `2.3.0` | nein | - |
| `jinja2` | `3.1.6` | nein | `markupsafe` |
| `jinja2-ansible-filters` | `1.3.2` | nein | `jinja2`, `pyyaml` |
| `markupsafe` | `3.0.3` | nein | - |
| `packaging` | `26.2` | nein | - |
| `pathspec` | `1.1.1` | nein | - |
| `platformdirs` | `4.10.0` | nein | - |
| `pluggy` | `1.6.0` | nein | - |
| `plumbum` | `2.0.1` | nein | `typing-extensions` |
| `prompt-toolkit` | `3.0.52` | nein | `wcwidth` |
| `pydantic` | `2.13.4` | nein | `annotated-types`, `pydantic-core`, `typing-extensions`, `typing-inspection` |
| `pydantic-core` | `2.46.4` | nein | `typing-extensions` |
| `pygments` | `2.20.0` | nein | - |
| `pytest` | `9.1.1` | ja | `colorama`, `iniconfig`, `packaging`, `pluggy`, `pygments` |
| `pyyaml` | `6.0.3` | ja | - |
| `questionary` | `2.1.1` | nein | `prompt-toolkit` |
| `ruff` | `0.15.20` | ja | - |
| `typing-extensions` | `4.16.0` | nein | - |
| `typing-inspection` | `0.4.2` | nein | `typing-extensions` |
| `wcwidth` | `0.8.2` | nein | - |

## Optionale externe Werkzeuge

Diese Werkzeuge sind keine Python-Pakete des Repositorys, koennen aber von
bestimmten Modulen oder Workflows genutzt werden.

| Werkzeug | Wann relevant | Status |
|---|---|---|
| `git` | Template-Quelle klonen, Updates, lokale Hooks, Security-Floor-Dateiliste | erforderlich fuer normale Nutzung |
| `bash` | `git-hooks`-Installer und `new_issue.sh` | erforderlich, wenn diese Skripte genutzt werden |
| `gh` | best-effort Existenzpruefung im `github-issues`-Modul; Tempo-Familie des KPI-Cockpits im `telemetry`-Modul | optional |
| `import-linter` | best-effort Architektur-Layering in Python-Repos | optional, nur wenn Zielrepo es konfiguriert |
| `dependency-cruiser` | best-effort Architektur-Layering in JS/TS-Repos | optional, nur wenn Zielrepo es konfiguriert |

## Pflege

Wenn sich `pyproject.toml` oder `uv.lock` aendert, muss diese SBOM im selben
Change aktualisiert werden. Die SBOM ist absichtlich menschenlesbar; die
autoritativen Versions-Pins bleiben in `uv.lock`.
