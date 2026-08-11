# dev-process

> **English:** A **machine-enforced**, AI-assisted development process on a
> committed standard stack — GitHub + Spec Kit + pre-commit + a lean
> dev-process enforcement kernel — installable into new and existing
> repositories via `uvx copier copy gh:Crashman1983/dev-process .`.
> This README is German by choice; everything the template installs (process
> docs, adapters, commands) is English — start with
> [`BOOTSTRAP.md`](BOOTSTRAP.md). License: [Apache-2.0](LICENSE) —
> free for any use, commercial included. Two spec templates derive from
> GitHub Spec Kit (MIT, © GitHub, Inc.):
> [`THIRD-PARTY-NOTICES.md`](THIRD-PARTY-NOTICES.md).

Ein **maschinell durchgesetzter**, KI-gestützter Entwicklungsprozess auf einem
bewussten Standard-Stack: **GitHub** (Issues/Projects/Actions als Arbeits-Log
und CI), **[Spec Kit](https://github.com/github/spec-kit)** (der Weg zur
Spezifikation, gepinnt und vendored), **[pre-commit](https://pre-commit.com)**
(lokale Hooks) und ein schlanker **dev-process-Kernel** (Risiko-Tiers, Gates,
Review-Unabhängigkeit, Inventar, Telemetrie). Einspielbar in **neue
(Greenfield)** wie **bestehende (Brownfield)** Projekte; ausgeliefert als
[copier](https://copier.readthedocs.io)-Template. Der Command-Adapter wird bei
der Installation gewählt (`claude` | `copilot` | `agents_md`); die
Spezifikations-Skills deckt Spec Kits eigenes Integrations-System ab.

> **Produktrahmen-Entscheidung (2026-08-06):** Die frühere Identität
> „portabel, harness-agnostisch, 13 opt-in Module" wurde bewusst gegen den
> Standard-Stack getauscht (Lean-Pass SP56) — weniger Optionen, weniger
> Eigenbau, gleiche Garantien. Analyse und Design:
> [`docs/analysis/`](docs/analysis/) · [`docs/design/2026-08-06-speckit-hybrid-design.md`](docs/design/2026-08-06-speckit-hybrid-design.md).
> Exit-Szenario der Spec-Kit-Abhängigkeit: Pin einfrieren — der vendored
> Stand läuft ohne Netz und ohne CLI unbegrenzt weiter.

> **Status:** `v2.5.1` — Sub-Projekte SP1–SP61 (Standard-Setup
> statt Profile/Toggles, Spec Kit als Standard-Spezifikationsweg, 5 Core-Gates,
> DoR/DoD, Kernel-Integritäts- und Compaction-Schutz). Vollständige Historie: [`CHANGELOG.md`](CHANGELOG.md).
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
und fährt in CI nur die *aktiven* Module — als GitHub-Actions-Workflow
(`ci`-Frage). git-Hooks sichern lokal ab.
**Ehrliche Degradation:** ohne GitHub-CI bleibt das `git-hooks`-Modul
die einzige Enforcement-Säule — und ohne dieses erzwingt nichts die Gates. Das **Standard-Setup**
(Lean-Pass: eine Frage — `regulated` — statt 13 Toggles) umfasst:
`speckit` (Spec Kit als Tier-2+-Spezifikationsweg — Constitution-Pointer statt zweiter Wahrheit, EARS-/Test-Pflicht-Overrides, publish-and-prune-Merge-Ritual mit SC-Accounting),
`doc-drift-gate` (tote Pfad-Referenzen in Docs), `arch-onboarding`
(Architektur gegen echten Code), `feature-registry` (das **Feature-Inventar**: Capability → Akzeptanz → beweisender Test — das Arbeits-Log liegt in GitHub Issues),
`github-issues` (EARS-Templates + Issue-Ref-Gate),
`contracts` (Kopplung als geprüfter Contract: contract-first + Pin-Drift),
`git-hooks` (lokale Durchsetzung über das pre-commit-Framework),
`telemetry` (genau die drei Ziel-KPIs: Konvergenz, Kosten, DORA-CFR — `GRADE`-Trace gate-gesichert, Trends gegen die eigene Baseline),
`arch-docs` (arc42/C4-lite Doku-Scaffold mit ehrlichem Gate) und
`github-master` (GitHub Issues als Arbeits-Log-SSOT über einen committeten Snapshot — Sync mit Netz, Gate hermetisch offline; DoR-at-rest + Board-Konsistenz).
Das `regulated`-Paket ergänzt `security-floor` (verbotene Muster als Gate) und `sbom` (CycloneDX + Lizenz-Allow-List).

**Commands:** Der Zyklus (`brainstorm plan execute review quick debug commit
prime`) liegt als dünne Slash-Commands für den gewählten Harness; `brainstorm`
und `plan` zeigen auf den Spec-Kit-Pfad (`/speckit-specify → clarify → plan →
tasks`), der Rest auf die neutralen `docs/process/`-Phasen. Der
`doc-drift-gate` prüft die Pointer mit — ein toter Command-Pointer failt die
CI.

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

|  | Prosa-Playbook | Spec Kit allein | reines CI-Linting | **dev-process** |
|---|:---:|:---:|:---:|:---:|
| durchgesetzt, nicht nur dokumentiert | ✗ | ✗ (LLM-Selbstchecks) | nur Stil | ✓ Gates + Hooks |
| risiko-proportional (Tiers statt Ein-Pfad) | – | ✗ | – | ✓ |
| Spezifikationsweg nach Industriestandard | ✗ | ✓ | – | ✓ (Spec Kit integriert) |
| nachträglich aktualisierbar | ✗ | teils (0.x) | – | ✓ `copier update` + Pin |
| Architektur gegen echten Code geprüft | ✗ | ✗ | ✗ | ✓ arch-onboarding |
| Brownfield-additiv (überschreibt nichts) | ✗ | (✓) | – | ✓ |
| ehrliche Decke (hart vs. best-effort) | – | ✗ | – | ✓ kein False-Green |

Kurz: Ein Playbook beschreibt, erzwingt aber nichts und altert; Spec Kit
allein spezifiziert stark, erzwingt aber nichts und kennt keine Risiko-Tiers;
CI-Linting sichert Stil, nicht Prozess. `dev-process` kombiniert den
Standard-Spezifikationsweg mit deterministischer Durchsetzung — und bleibt
über `copier update` (Prozess) und den Version-Pin (Spec Kit) getrennt
aktualisierbar.

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

[Apache-2.0](LICENSE): Nutzung, Änderung und Weitergabe sind frei — auch
kommerziell, auch das Einspielen des Prozesses in kommerzielle Projekte.
Bedingungen: Lizenz- und Copyright-Hinweis mitführen, Änderungen an
lizenzierten Dateien kennzeichnen; die Lizenz enthält eine ausdrückliche
Patentklausel. Zwei Spezifikations-Templates sind von GitHub Spec Kit
abgeleitet (MIT, © GitHub, Inc.) — Details in
[`THIRD-PARTY-NOTICES.md`](THIRD-PARTY-NOTICES.md). Bis v2.1.0 stand das
Projekt unter der Prosperity Public License 3.0.0; der Wechsel zu Apache-2.0
öffnet den Kern bewusst (Open-Core: künftige kommerzielle Zusatzkomponenten
bleiben davon getrennt).

## Historie

Die vollständige Sub-Projekt-Historie (Narrativ + Tabelle) ist nach
[`CHANGELOG.md`](CHANGELOG.md) ausgelagert.
