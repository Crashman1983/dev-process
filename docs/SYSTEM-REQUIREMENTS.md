# System Requirements

Stand: 2026-07-10

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
| `uv` / `uvx` | aktuelle stabile Version | fuehrt `copier` isoliert aus; Fallbacks ohne `uv`: `pipx run copier` oder venv + `pip install 'copier>=9.4'` (Rezepte: `BOOTSTRAP.md`) |
| `git` | aktuelle stabile Version | holt das Template von GitHub und unterstuetzt `copier update`; loest `gh:` nicht auf, geht auch ein lokaler Clone als Template-Quelle |
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

Der Core-Runtime-Vertrag ist auf Linux, macOS und Windows gleich: `git` und
`uv`. Ein system Python, eine systemweite PyYAML-Installation oder Bash ist
nicht erforderlich. `uv` liest die PEP-723-Metadaten des Gate-Runners und
stellt Laufzeit und Abhaengigkeiten isoliert bereit.

| Voraussetzung | Version | Wann erforderlich |
|---|---:|---|
| `uv` | aktuelle stabile Version | startet Gates und portable Helfer samt isolierter Python-Abhaengigkeiten |
| `git` | aktuelle stabile Version | lokale Hooks, Security-Floor-Dateiliste, normale Projektarbeit |
| `gh` | aktuelle stabile Version | optional fuer best-effort GitHub-Issue-Existenzpruefung und die Tempo-Familie des KPI-Cockpits (`telemetry`) |
| Architekturlinter | projektabhaengig | optional fuer `arch-onboarding` best-effort Layering-Pruefungen |

Die plattformneutralen Befehle sind:

```bash
uv run scripts/process/gate_runner.py
uv run scripts/process/install_hooks.py
uv run scripts/process/new_issue.py feature
```

Git startet die kleinen POSIX-Hook-Launcher selbst; Git for Windows liefert
diese Hook-Umgebung mit. Die eigentliche Hook-Logik laeuft danach ueber `uv` in
Python.

## Modulbezogene Hinweise

| Modul | Zusaetzliche Umgebung |
|---|---|
| `doc-drift-gate` | Python-Stdlib reicht |
| `arch-onboarding` | `PyYAML`; optional `import-linter` oder `dependency-cruiser`, wenn das Zielrepo Layering maschinell pruefen will |
| `feature-registry` | Python-Stdlib reicht |
| `github-issues` | `PyYAML` (liest `.copier-answers.yml`); optional `gh` fuer best-effort Remote-Checks |
| `contracts-drift` | Python-Stdlib reicht; Contract-spezifische Verify-Kommandos koennen projektspezifische Tools brauchen |
| `git-hooks` | keine zusaetzlichen Werkzeuge ausser dem Core-Vertrag |
| `contract-first` | Python-Stdlib reicht |
| `parity` | `PyYAML` |
| `security-floor` | `git` und Python-Stdlib |
| `sbom` | `git` und Python-Stdlib; SBOM-Erzeugung braucht einen CycloneDX-Generator im Build (z. B. Maven-Plugin, `@cyclonedx/cyclonedx-npm`, `syft`) |
| `telemetry` | Python-Stdlib fuer Gate und Cockpit-Kern; optional `gh` (Tempo-Familie) und `git` (CFR-Familie) |
| `arch_docs` | Python-Stdlib reicht |
| `github-master` | Gate: Python-Stdlib (hermetisch, offline); Sync/Board-Tools: `gh` (authentifiziert, Board zusaetzlich `project`-Scope) |

## CI

Die Upstream-CI verwendet Ubuntu fuer die Vollsuite und eine portable
Smoke-Matrix auf Linux, macOS und Windows.

Gerenderte Zielrepos erhalten je nach `ci`-Antwort einen `process-gates`-Job:

- **GitHub** (`ci.github`, Default): Actions-Workflow mit
  `astral-sh/setup-uv` und `uv run scripts/process/gate_runner.py`.
- **GitLab** (`ci.gitlab`): includable Job-Datei
  `.gitlab/ci/process-gates.gitlab-ci.yml` (offizielles `uv`-Image, gleiches
  Kommando) plus duenner Root-Shim `.gitlab-ci.yml` mit einer
  `include:`-Zeile.

Sind beide aus, erzwingt remote nichts die Gates — dann ist das
`git-hooks`-Modul die einzige Enforcement-Saeule.
