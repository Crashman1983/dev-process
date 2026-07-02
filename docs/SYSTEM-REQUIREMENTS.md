# System Requirements

Stand: 2026-07-02

Dieses Dokument beschreibt, was auf einem System installiert sein muss, um
`dev-process` zu nutzen, im Upstream-Repository zu entwickeln oder die gerenderten
Prozess-Gates in Zielrepos auszufuehren.

## Template-Nutzung

Minimaler Weg fuer Greenfield- oder Brownfield-Projekte:

```bash
uvx copier copy gh:Crashman1983/dev-process .
```

| Voraussetzung | Version | Warum |
|---|---:|---|
| `uv` / `uvx` | aktuelle stabile Version | fuehrt `copier` isoliert aus |
| `git` | aktuelle stabile Version | holt das Template von GitHub und unterstuetzt `copier update` |
| Netzwerkzugriff auf GitHub und PyPI | - | Template- und Python-Paketauflösung |

Bei privaten Template-Repositories wird zusaetzlich ein Git-Credential-Setup
benoetigt, zum Beispiel `gh auth setup-git` oder ein anderer Git Credential
Helper. Fuer dieses oeffentliche Repository ist das nicht noetig.

## Entwicklung im `dev-process`-Repository

| Voraussetzung | Version | Warum |
|---|---:|---|
| Python | `>=3.11` | Projekt-Minimum aus `pyproject.toml`; Tests laufen in CI mit `uv` |
| `uv` | aktuelle stabile Version | synchronisiert die `dev`-Dependency-Gruppe aus `uv.lock` |
| `git` | aktuelle stabile Version | Versionskontrolle und Template-Tests |

Setup:

```bash
uv sync --group dev
uv run ruff check .
uv run pytest -v
```

Die direkten Python-Abhaengigkeiten stehen in `pyproject.toml`; die aufgeloesten
Versionen sind in `uv.lock` gepinnt und in `docs/SBOM.md` zusammengefasst.

## Gerenderte Zielrepos

Die installierten Prozessdateien sind weitgehend Markdown, Shell und Python. Je
nach aktivierten Modulen werden folgende Laufzeitwerkzeuge benoetigt.

| Voraussetzung | Version | Wann erforderlich |
|---|---:|---|
| Python | `>=3.11` empfohlen | alle Python-basierten Prozess-Gates |
| `PyYAML` | `>=6` | `gate_runner.py`, `arch-onboarding`, `parity` und alle Gates, die `.copier-answers.yml` lesen |
| `git` | aktuelle stabile Version | lokale Hooks, Security-Floor-Dateiliste, normale Projektarbeit |
| `bash` | POSIX-kompatible Shell plus Bash | `scripts/process/install-hooks.sh` und `scripts/process/new_issue.sh` |
| `gh` | aktuelle stabile Version | optional fuer best-effort GitHub-Issue-Existenzpruefung |
| Architekturlinter | projektabhaengig | optional fuer `arch-onboarding` best-effort Layering-Pruefungen |

Die von `dev-process` gerenderte GitHub-Actions-Workflow-Datei installiert
`pyyaml` explizit, bevor `python scripts/process/gate_runner.py` ausgefuehrt
wird. Lokal muss `python3` ebenfalls `PyYAML` finden, wenn die installierten
Git-Hooks direkt `python3 scripts/process/gate_runner.py` starten. Praktische
Optionen sind:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install 'PyYAML>=6'
PATH="$PWD/.venv/bin:$PATH" bash scripts/process/install-hooks.sh
```

oder eine projektweite Python-Umgebung, in der `PyYAML>=6` bereits installiert
ist.

## Modulbezogene Hinweise

| Modul | Zusaetzliche Umgebung |
|---|---|
| `doc-drift-gate` | Python-Stdlib reicht |
| `arch-onboarding` | `PyYAML`; optional `import-linter` oder `dependency-cruiser`, wenn das Zielrepo Layering maschinell pruefen will |
| `feature-registry` | Python-Stdlib reicht |
| `github-issues` | Python-Stdlib reicht; optional `gh` fuer best-effort Remote-Checks |
| `contracts-drift` | Python-Stdlib reicht; Contract-spezifische Verify-Kommandos koennen projektspezifische Tools brauchen |
| `git-hooks` | `git`, `bash`, Python mit `PyYAML` fuer die Hooks |
| `contract-first` | Python-Stdlib reicht |
| `parity` | `PyYAML` |
| `security-floor` | `git` und Python-Stdlib |

## CI

Die Upstream-CI verwendet Ubuntu, `astral-sh/setup-uv`, `uv sync --group dev`,
`uv run ruff check .` und `uv run pytest -v`.

Gerenderte Zielrepos erhalten einen separaten `process-gates`-Workflow mit
`actions/setup-python`, `pip install pyyaml` und
`python scripts/process/gate_runner.py`.
