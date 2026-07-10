# dev-process

> **English:** A portable, harness-agnostic, modular foundation for a
> **machine-enforced**, AI-assisted development process — installable into new
> and existing repositories via `uvx copier copy gh:Crashman1983/dev-process .`.
> This README is German by choice; everything the template installs (process
> docs, adapters, commands) is English — start with
> [`BOOTSTRAP.md`](BOOTSTRAP.md). License: [Prosperity Public
> License 3.0.0](LICENSE.md) — free for noncommercial use; commercial use
> beyond a 30-day trial requires a license from the contributor.

Ein portables, harness-agnostisches, modulares Fundament für einen **maschinell
durchgesetzten**, KI-gestützten Entwicklungsprozess — einspielbar in **neue
(Greenfield)** wie **bestehende (Brownfield)** Projekte.

Ausgeliefert als [copier](https://copier.readthedocs.io)-Template. Adapter für
**Claude Code**, **GitHub Copilot** und **AGENTS.md** (Codex / Gemini CLI / Aider …).

> **Status:** `v1.35.0` — Sub-Projekte SP1–SP51 ausgeliefert (Kern + 13 opt-in
> Module, 4 Core-Gates, Profile für Solo/Team, DoR/DoD, Kernel-Integritäts-
> und Compaction-Schutz). Vollständige Historie: [`CHANGELOG.md`](CHANGELOG.md).
> **Überblick für Einsteiger:innen & Management** (wie es funktioniert, warum,
> welcher Mehrwert): [`docs/CAPABILITIES.md`](docs/CAPABILITIES.md).
> Setup: [`BOOTSTRAP.md`](BOOTSTRAP.md) · Systemumgebung:
> [`docs/SYSTEM-REQUIREMENTS.md`](docs/SYSTEM-REQUIREMENTS.md) · SBOM:
> [`docs/SBOM.md`](docs/SBOM.md) · Design: [`docs/design/`](docs/design/).

---

> **Herkunft:** Generalisiert aus *Kenni*, einem privaten Projekt, in dem
> dieser Prozess entwickelt und erprobt wurde. Verweise auf Kenni-Interna
> (Issue-Nummern, Spec-Abschnitte) in `docs/design/` und `docs/plans/` sind
> Projektgeschichte und öffentlich nicht auflösbar; alles, was das Template
> ausliefert, ist davon unabhängig und neutral.

## Die Idee in einem Absatz

Der Wert eines Entwicklungsprozesses steckt in drei Schichten, die üblicherweise
vermischt werden. Die **Methodik** (Regeln, Risiko-Tiers, Zyklus, ADRs, Journal)
ist reines Markdown + git und damit tool-unabhängig. Die **Durchsetzung**
(CI-Gates, git-Hooks) ist die eigentliche Garantie — sie hält auch dann, wenn
niemand hinsieht. Nur die **aktive Automatisierung** (Slash-Commands, Skills,
Subagents) ist harness-spezifisch und degradiert kontrolliert, wenn man das Tool
wechselt. `dev-process` legt die Methodik als neutrale SSOT (`docs/process/`) ab,
erzwingt sie über CI, und liefert dünne Adapter je Harness — die schweren
Bausteine sind zuschaltbare Module.

## Der Prozess — Eckpunkte

**Risiko-Tiers (0–3)** routen jede Aufgabe: der *Umfang* bestimmt den Tier, nicht
die Diff-Größe. Komponentenübergreifend, API/Contract, Auth oder Persistenz ⇒
Tier 2+ auch bei winzigem Diff; bloße User-Sichtbarkeit allein ist noch kein
Tier 2 (`risk-tiers.md` ist die SSOT). Ein `flow`-Label ist Boden, nie Decke.

**Neun bindende Regeln** (Reihenfolge = Priorität):

1. Verifikation vor Behauptung (Tool-Call oder Confidence-Tag).
2. Plan vor substanzieller Arbeit (Tier aus echtem Umfang ableiten).
3. Contract/Interface zuerst bei geteiltem Verhalten.
4. Ein Owner pro Verhalten — strukturell statt additiv (keine parallelen Efforts).
5. Tests beweisen Akzeptanz.
6. Root-Cause vor Symptom (max. 2 Symptom-Versuche).
7. Review-Gate vor Merge in den Main-Branch.
8. Atomare Commits, dokumentierte Ausnahmen.
9. Code wird zum Lesen geschrieben — intention-revealing, am Review-Gate geprüft.

**Zyklus:** Brainstorm → Plan → Execute → Review, plus Quick (kleine Änderungen)
und Debug. Methodik-Docs tragen die Tiefe: `testing.md` (Suite-Form: Pyramide,
Property-based, Regression-Pins, ehrliche Coverage-Decke), `releases.md`
(SemVer, Changelog, Tag-Ritual), `code-craft.md` (lesbarer Code); Tier-3-Designs
beantworten die Threat-Frage („Was könnte ein Angreifer damit?") schon im
Brainstorm. **ADRs** tragen zwei Achsen — `Status` (Proposed/Accepted/Superseded)
und `Intent` (keep/change-planned/tolerated), damit „so ist es" von „so soll es
werden" getrennt bleibt. **Journal, Branch-State und Pläne** halten das *Warum*
fest, das das git-log nicht zeigt. **`PRODUCT.md`** (Core) ist der Produktrahmen —
Purpose, Users, Goals, **Non-Goals**, Constraints, aktueller Scope —, im
Onboarding-Dialog befüllt und von Brainstorm/Plan/Review als Richtungs-Constraint
gelesen; ein immer aktives Gate hält ihn präsent und referenz-sauber.

**Durchsetzung:** ein manifest-bewusster `gate_runner` liest `.copier-answers.yml`
und fährt in CI nur die *aktiven* Module — als GitHub-Actions-Workflow und/oder
GitLab-CI-Job (`ci`-Frage; GitLab: includable Job-Datei plus dünner
Root-Shim, kollisionsfrei für Brownfield). git-Hooks sichern lokal ab.
**Ehrliche Degradation:** ohne GitHub *und* GitLab bleibt das `git-hooks`-Modul
die einzige Enforcement-Säule — und ohne dieses erzwingt nichts die Gates. Zuschaltbare
Module heute: `doc-drift-gate` (tote Pfad-Referenzen in Docs), `arch-onboarding`
(Architektur gegen echten Code), `feature-registry` (User-Story-/Akzeptanz-/
Test-Traceability), `github-issues` (EARS-Templates + Issue-Ref-Gate),
`contracts-drift` (Kopplung-als-Contract, Pin-Drift-Ratchet + best-effort-Konformität),
`git-hooks` (lokale pre-commit/pre-push/post-commit-Durchsetzung, an den gate_runner delegiert),
`contract-first` (geteiltes Capability-Interface im committeten Spec deklariert, bevor eine Surface darauf baut),
`parity` (Capability×Surface-Matrix, die jede bewusste Lücke an ein Tracking-Issue bindet — gegen stillen Capability-Verlust),
`security-floor` (der grep-bare Teil der Security-Invarianten als blockierendes Gate — verbotene Regex-Muster über git-getrackte Dateien)
`telemetry` (Effizienz-Messung: `GRADE`-Trace-Zeilen im Journal als Gate-gesichertes Format plus read-only KPI-Cockpit — Wirksamkeit, Konvergenz, Kalibrier-Suite, Tempo, Kosten, DORA-CFR; Messwerte mit Konfidenz + Maßnahme, Schwellen-Familien als erfüllt/nicht-erfüllt. Misst Trends, Verhältnisse und Catch/Escape-Ereignisse gegen die projekteigene Baseline — kein projektübergreifendes Benchmarking, Absolutwerte ohne eigene Baseline sind bedeutungslos)
`arch-docs` (stakeholder-gerichtete Architektur-Doku im arc42/C4-Zuschnitt: `ARCHITECTURE-OVERVIEW.md`-Scaffold mit Verify-Tags — Building-Blocks→arch-Block und Decisions→ADRs verlinkt statt dupliziert, Prosa ehrlich unverifiziert; Gate fängt nur tote ADR-Refs + verbliebene Platzhalter, nie „gute Prosa")
`sbom` (CycloneDX-SBOM mit attestierter Lizenz je Third-Party-Komponente + SPDX-Allow-List als blockierendes Gate — ehrlich degradierend: advisory ohne Policy/SBOM, hart bei fehlender/unerlaubter Lizenz)
und `github-master` (dreht die Wahrheitsrichtung: GitHub Issues als SSOT über einen committeten Snapshot — Sync mit Netz, Gate hermetisch offline; Board-Spalten-Konsistenz mitgeprüft).

**Harness-native Commands:** Der Zyklus (`brainstorm plan execute review quick
debug commit prime`) liegt als dünne Slash-Commands je aktivem Harness
(`.claude/commands/`, `.github/prompts/`, plus eine AGENTS.md-Sektion), die auf
die neutralen `docs/process/`-Phasen zeigen. Sie sind harness-Ergonomie, kein
Modul — und werden vom `doc-drift-gate` mitgeprüft, sodass ein toter
Command-Pointer die CI failt.

## Architektur als geprüfter Contract (SP2)

Die meisten Frameworks dokumentieren Architektur in Prosa, die verrottet.
`arch-onboarding` erfasst sie stattdessen als maschinen-prüfbaren Block in
`ARCHITECTURE.md` und verifiziert die Aussagen bei **jedem** CI-Lauf gegen echten
Code — ehrlich getrennt nach dem, was mechanisch garantierbar ist, und dem, was
nicht:

- **Hart (CI schlägt fehl):** `code_roots` und Layer-Pfade existieren, Interface-
  Symbole liegen in ihrer Datei, ein `rules[].adr`-Link löst auf eine ADR auf.
- **Best-effort:** Layering-Konformität fährt einen vorhandenen Arch-Linter
  (import-linter / dependency-cruiser) und schlägt bei Verstößen fehl; ohne Linter
  bleibt eine Manual-Review-Checkliste. Konformität wird nie *vorgetäuscht*.

## Mehrwert gegenüber Standard-Ansätzen

|  | Prosa-Playbook | Scaffolding (cookiecutter) | reines CI-Linting | **dev-process** |
|---|:---:|:---:|:---:|:---:|
| durchgesetzt, nicht nur dokumentiert | ✗ | ✗ | nur Stil | ✓ Gates + Hooks |
| nachträglich aktualisierbar | ✗ | ✗ (one-shot) | – | ✓ `copier update` |
| tool-/harness-unabhängig | – | – | – | ✓ Kernel byte-identisch |
| Architektur gegen echten Code geprüft | ✗ | ✗ | ✗ | ✓ arch-onboarding |
| Brownfield-additiv (überschreibt nichts) | ✗ | ✗ | – | ✓ |
| ehrliche Decke (hart vs. best-effort) | – | – | – | ✓ kein False-Green |

Kurz: Ein Playbook beschreibt, erzwingt aber nichts und altert; Scaffolding ist
ein einmaliger Abwurf ohne Update-Pfad; CI-Linting sichert Stil, nicht Prozess,
Architektur oder Entscheidungen. `dev-process` liefert die Methodik **mit** ihrer
Durchsetzung, harness-übergreifend und über `copier update` versionierbar.

Eine ausführliche, zielgruppengerechte Erklärung — *wie es funktioniert, warum,
welcher Mehrwert*, getrennt für Entwickler:innen und Management — steht in
[`docs/CAPABILITIES.md`](docs/CAPABILITIES.md).

## Sprachen & Ökonomie

**Artefakte englisch, Dialog in Nutzersprache.** Alle gerenderten Artefakte
(Prozessdoku, Adapter, Commands, ADRs, Journal, Commits) sind englisch — eine
Sprache zu pflegen, und die, auf die LLMs am zuverlässigsten reagieren. Eine
Kernel-Regel weist jeden Harness an, mit dem Nutzer in *dessen* Sprache zu
sprechen; die Artefaktsprache bleibt davon unberührt.

**Wann dieser Prozess nicht lohnt:** Für Wegwerf-Prototypen, Einmal-Skripte
und Single-Session-Arbeit ist der Overhead netto negativ — dort nichts (oder
nur das Minimalprofil) installieren. Der Prozess rechnet sich für alles
Mehrsession-, Multi-Agent- oder Contract/Persistenz/Auth-behaftete.

## Nutzung

**Greenfield oder Brownfield — derselbe Befehl:**

```bash
uvx copier copy gh:Crashman1983/dev-process .
```

copier fragt **Profil** (leitet den Modul-Default ab), **Module**, **Harnesses** und **CI-Adapter** ab und rendert nur
diese. Bestehende
Dateien werden **nicht** überschrieben (additiver Drop-in). Ein Modul später
nachrüsten oder eine neuere Prozess-Version ziehen:
`uvx copier update --defaults --data 'modules={…}'` mit dem vollständigen
Modul-Dictionary (Rezept: [`BOOTSTRAP.md`](BOOTSTRAP.md) — die Antwortdatei
`.copier-answers.yml` nicht von Hand editieren, sonst rendert `update` die
neuen Moduldateien nicht).

**Pull-Mode** (ein KI-Agent richtet es ein): dem Agenten im Zielrepo sagen
*„richte den Entwicklungsprozess aus diesem Repo ein, folge dessen `BOOTSTRAP.md`"* —
der Rest ist self-contained beschrieben, inklusive Headless-Rezept
(`--defaults --data … --skip …`) für Harnesses ohne Terminal-Prompts und
Pflicht-Verifikation über den `gate_runner`.

## Lizenz

[Prosperity Public License 3.0.0](LICENSE.md): Nutzung, Änderung und
Weitergabe sind für **nicht-kommerzielle Zwecke** frei (privat, Forschung,
Lehre, gemeinnützig, Behörden). **Kommerzielle Nutzung** — auch das
Einspielen des Prozesses in kommerzielle Projekte — ist auf eine
**30-Tage-Testphase** begrenzt (eine Testphase pro Firma); danach braucht
es eine Lizenz des Contributors (Anfrage per GitHub-Issue). Beiträge
zurück an das Projekt gelten laut Lizenz nicht als kommerzielle Nutzung,
wenn sie unter einer standardisierten offenen Lizenz (z. B. MIT/Apache-2.0)
eingereicht werden — genau so werden PRs angenommen.

## Historie

Die vollständige Sub-Projekt-Historie (Narrativ + Tabelle) ist nach
[`CHANGELOG.md`](CHANGELOG.md) ausgelagert.
