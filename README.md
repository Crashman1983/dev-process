# dev-process

Ein portables, harness-agnostisches, modulares Fundament für einen **maschinell
durchgesetzten**, KI-gestützten Entwicklungsprozess — einspielbar in **neue
(Greenfield)** wie **bestehende (Brownfield)** Projekte.

Ausgeliefert als [copier](https://copier.readthedocs.io)-Template. Adapter für
**Claude Code**, **GitHub Copilot** und **AGENTS.md** (Codex / Gemini CLI / Aider …).

> **Status:** SP1 (Foundation) + SP2 (Architektur-Onboarding) + SP3
> (feature-registry, github-issues, contracts-drift) + SP4 (git-hooks,
> contract-first, parity) ausgeliefert, Tag `v0.8.0`.
> Setup: [`BOOTSTRAP.md`](BOOTSTRAP.md) · Design: [`docs/design/`](docs/design/).

---

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

**Risiko-Tiers (0–4)** routen jede Aufgabe: der *Umfang* bestimmt den Tier, nicht
die Diff-Größe. User-sichtbar, komponentenübergreifend, API/Contract, Auth oder
Persistenz ⇒ Tier 3+ auch bei winzigem Diff. Ein `flow`-Label ist Boden, nie Decke.

**Acht bindende Regeln** (Reihenfolge = Priorität):

1. Verifikation vor Behauptung (Tool-Call oder Confidence-Tag).
2. Plan vor substanzieller Arbeit (Tier aus echtem Umfang ableiten).
3. Contract/Interface zuerst bei geteiltem Verhalten.
4. Ein Owner pro Verhalten — strukturell statt additiv (keine parallelen Efforts).
5. Tests beweisen Akzeptanz.
6. Root-Cause vor Symptom (max. 2 Symptom-Versuche).
7. Review-Gate vor Merge in den Main-Branch.
8. Atomare Commits, dokumentierte Ausnahmen.

**Zyklus:** Brainstorm → Plan → Execute → Review, plus Quick (kleine Änderungen)
und Debug. **ADRs** tragen zwei Achsen — `Status` (Proposed/Accepted/Superseded)
und `Intent` (keep/change-planned/tolerated), damit „so ist es" von „so soll es
werden" getrennt bleibt. **Journal, Branch-State und Pläne** halten das *Warum*
fest, das das git-log nicht zeigt.

**Durchsetzung:** ein manifest-bewusster `gate_runner` liest `.copier-answers.yml`
und fährt in CI nur die *aktiven* Module. git-Hooks sichern lokal ab. Zuschaltbare
Module heute: `doc-drift-gate` (tote Pfad-Referenzen in Docs), `arch-onboarding`
(Architektur gegen echten Code), `feature-registry` (User-Story-/Akzeptanz-/
Test-Traceability), `github-issues` (EARS-Templates + Issue-Ref-Gate) und
`contracts-drift` (Kopplung-als-Contract, Pin-Drift-Ratchet + best-effort-Konformität),
`git-hooks` (lokale pre-commit/pre-push/post-commit-Durchsetzung, an den gate_runner delegiert),
`contract-first` (geteiltes Capability-Interface im committeten Spec deklariert, bevor eine Surface darauf baut)
und `parity` (Capability×Surface-Matrix, die jede bewusste Lücke an ein Tracking-Issue bindet — gegen stillen Capability-Verlust).

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

## Nutzung

**Greenfield oder Brownfield — derselbe Befehl:**

```bash
uvx copier copy gh:Crashman1983/dev-process .
```

copier fragt **Module** und **Harnesses** ab und rendert nur diese. Bestehende
Dateien werden **nicht** überschrieben (additiver Drop-in). Ein Modul später
nachrüsten oder eine neuere Prozess-Version ziehen: Antwort in
`.copier-answers.yml` ändern → `uvx copier update`.

**Pull-Mode** (ein KI-Agent richtet es ein): dem Agenten im Zielrepo sagen
*„richte den Entwicklungsprozess aus diesem Repo ein, folge dessen `BOOTSTRAP.md`"* —
der Rest ist self-contained beschrieben.

## Roadmap

| Sub-Projekt | Inhalt | Status |
|---|---|---|
| **SP1** Foundation | Kern + Adapter + copier-Init + additiver Brownfield-Drop-in | ✅ ausgeliefert |
| **SP2** Architektur-Onboarding | Architektur-Interview + Verifikation gegen echten Code | ✅ ausgeliefert |
| **SP3** Prozess-Vervollständigung (Multi-Repo/-Mensch) | feature-registry · github-issues · contracts-drift | ✅ Slices 1–3 |
| **SP4** Prozess-Vervollständigung II | git-hooks (lokale Enforcement-Säule) · contract-first (Interface-declared-first-Gate) · parity (Capability×Surface-Matrix, Gap→Issue) | ✅ ausgeliefert |
