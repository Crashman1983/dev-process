# System Requirements

Stand: 2026-09-24 (v2.23.0)

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
Versionen sind in `uv.lock` gepinnt; `docs/SBOM.md` und `docs/sbom.cdx.json`
erzeugt `python3 tools/gen_sbom.py` daraus (ein Test prüft, dass sie aktuell sind).

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
uvx pre-commit install --hook-type pre-commit --hook-type pre-push
uv run scripts/process/new_issue.py feature
```

Die lokalen Hooks verwaltet das Standard-Framework `pre-commit`
(https://pre-commit.com); die Gate-Logik laeuft danach ueber `uv` in Python.

## Parallele Agenten (optional)

Wer mehrere Agenten gleichzeitig arbeiten lässt (Tower, Steward, Dispatch,
Merge Train; `docs/process/tower.md` und `docs/process/train.md` im
gerenderten Repo), braucht zusätzlich:

| Voraussetzung | Wann erforderlich |
|---|---|
| Python `>=3.11` auf `PATH` | die Koordinationsskripte (`tower.py`, `dispatch.py`, `train.py`, `report.py`, `rehydrate.py`) laufen mit der Stdlib |
| die CLI der Harness | `dispatch.py` startet Sitzungen mit dem Befehl aus `docs/process/model-policy.json`, im Standard `claude` (Claude Code) |
| `tmux` | nur für `"runner": "tmux"`: jeder Worker wird ein sichtbares, ansprechbares Fenster |
| Push-Zugriff auf `origin` | nur für Phasen auf einem anderen Host (`"remote": true`) und für Meldungen mit `report.py --sync` |

## Modulbezogene Hinweise

Das Standard-Setup rendert alle Module außer `security-floor` und `sbom`;
diese beiden kommen mit `regulated=true` dazu.

| Modul | Zusaetzliche Umgebung |
|---|---|
| `speckit` | die gepinnte Spec-Kit-CLI für das Setup (Rezept im gerenderten `docs/process/modules/speckit.md`); das Gate selbst braucht nur die Python-Stdlib |
| `doc-drift-gate` | Python-Stdlib reicht |
| `arch-onboarding` | `PyYAML`; optional `import-linter` oder `dependency-cruiser`, wenn das Zielrepo Layering maschinell pruefen will |
| `feature-registry` | Python-Stdlib reicht |
| `github-issues` | `PyYAML` (liest `.copier-answers.yml`); optional `gh` fuer best-effort Remote-Checks |
| `contracts` | Python-Stdlib reicht; Contract-spezifische Verify-Kommandos koennen projektspezifische Tools brauchen |
| `git-hooks` | keine zusaetzlichen Werkzeuge ausser dem Core-Vertrag |
| `telemetry` | Python-Stdlib fuer Gate und Cockpit-Kern; optional `gh` (Tempo-Familie) und `git` (CFR-Familie) |
| `arch-docs` | Python-Stdlib reicht |
| `github-master` | Gate: Python-Stdlib (hermetisch, offline); Sync/Board-Tools: `gh` (authentifiziert, Board zusaetzlich `project`-Scope) |
| `design-contracts` | Python-Stdlib reicht; die Referenz-Boards erzeugt das Projekt mit eigenen Werkzeugen |
| `security-floor` | `git` und Python-Stdlib |
| `sbom` | `git` und Python-Stdlib; SBOM-Erzeugung braucht einen CycloneDX-Generator im Build (z. B. Maven-Plugin, `@cyclonedx/cyclonedx-npm`, `syft`) |

## CI

Die Upstream-CI verwendet Ubuntu fuer die Vollsuite und eine portable
Smoke-Matrix auf Linux, macOS und Windows.

Gerenderte Zielrepos erhalten mit `ci.github` (Default) einen
`process-gates`-Job: ein Actions-Workflow mit `astral-sh/setup-uv` und
`uv run scripts/process/gate_runner.py`. `scripts/process/setup_branch_protection.sh`
hinterlegt ihn als Required Status Check.

Ist `ci.github` aus, erzwingt remote nichts die Gates — dann ist das
`git-hooks`-Modul die einzige Enforcement-Saeule.
