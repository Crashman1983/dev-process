# Analyse: dev-process vs. GitHub Spec Kit — lohnt sich ein Umstieg?

Datum: 2026-08-06 · Sprache bewusst Deutsch (Repo-Doku-Konvention wie
`README.md`/`CHANGELOG.md`; gerenderte Template-Artefakte bleiben englisch).

## 1. Fragestellung und Analysestrategie

**Frage:** Lohnt sich ein Umstieg von diesem Eigenbau (`dev-process`) auf
[GitHub Spec Kit](https://github.com/github/spec-kit), um einem anerkannten
Standard zu folgen, statt aufwändigen Eigenbau zu pflegen?

„Lohnt sich" ist nur relativ zu den Zielen beantwortbar, die der Eigenbau
verfolgt. Die Strategie hat deshalb fünf Schritte, jeder mit eigener
Beleglage:

1. **Artefakt-Analyse des Eigenbaus** — was `dev-process` *tatsächlich*
   liefert, belegt aus den Repo-Dateien selbst (nicht aus dem
   Selbstanspruch des README).
2. **Faktenrecherche Spec Kit** — Primärquellen (Repo, `spec-driven.md`,
   Releases, offizielle Doku, GitHub-API-Metriken, Stand 06.08.2026) getrennt
   von Sekundärquellen (Erfahrungsberichte, Hacker News, Blogs). Fakt und
   Meinung sind unten durchgängig als **[Fakt]** / **[Bericht]** markiert.
3. **Schichtenmodell als Vergleichsrahmen** — beide Ansätze werden auf die
   drei Schichten abgebildet, die das README dieses Repos selbst definiert
   (Methodik / Durchsetzung / aktive Automatisierung). Das verhindert den
   Kategorienfehler, ein Prompt-Toolkit mit einer Enforcement-Schicht zu
   vergleichen.
4. **Kriterienmatrix** — abgeleitet aus den erklärten Zielen des Eigenbaus
   (`README.md`, `docs/CAPABILITIES.md`) *plus* den Zielen der Ausgangsfrage
   (Standardisierung, Wartungsaufwand). Bewertung je Kriterium mit Beleg.
5. **Gap-Analyse in beide Richtungen + Empfehlung** — was ein Umstieg
   gewinnt, was er aufgibt, und welche dritte Option existiert.

## 2. Was die beiden Ansätze sind (Beleglage)

### 2.1 dev-process (dieses Repo)

Belegt aus dem Repo selbst (Stand `v1.37.0`, 131 Commits, SP1–SP54):

- **Methodik als neutrale SSOT:** ~1.300 Zeilen Prozess-Doku in
  `template/docs/process/` (9 bindende Regeln, Risiko-Tiers 0–3, Zyklus
  Brainstorm→Plan→Execute→Review, DoR/DoD, Review-Checkliste, Testing-,
  Release-, Commit-Konventionen, typisierte ADRs, Journal/Branch-State).
- **Maschinelle Durchsetzung:** manifest-bewusster `gate_runner`
  (`template/scripts/process/gate_runner.py.jinja`) für GitHub Actions und
  GitLab CI, lokale git-Hooks, 4 Core-Gates (u. a. Kernel-Integrität
  byte-identisch, `check_kernel.py`) und 13 zuschaltbare Module
  (doc-drift, arch-onboarding gegen echten Code, feature-registry mit
  Story→Akzeptanz→Test-Traceability, contracts-drift, security-floor, SBOM,
  parity, github-master mit Issues-als-SSOT, Telemetrie-KPIs …).
- **Deklarierte Ehrlichkeitsgrenze:** Gates unterscheiden hart vs.
  best-effort („kein False-Green", README „Mehrwert"-Tabelle).
- **Auslieferung:** copier-Template mit Update-Pfad (`copier update`),
  Brownfield-additiv (überschreibt nichts), Profile Solo/Team.
- **Harness-Adapter:** dünne Slash-Commands für Claude Code, Copilot,
  AGENTS.md — explizit „Ergonomie, kein Modul".
- **Absicherung des Eigenbaus selbst:** ~8.500 Zeilen Tests (`tests/`),
  Audit-Berichte (`.process-work/reviews/`), Design-Dokumente.
- **Kosten des Eigenbaus:** Ein-Personen-Projekt, 54 Sub-Projekte in ~7
  Wochen Historie; Prosperity-Lizenz (nicht-kommerziell frei) — d. h. kein
  Community-Ökosystem zu erwarten, Bus-Faktor 1.

### 2.2 GitHub Spec Kit

**[Fakt]** (Primärquellen; GitHub-API abgerufen 06.08.2026):

- MIT-lizenziertes Toolkit der `github`-Organisation für „Spec-Driven
  Development": Spezifikation als ausführbares, dauerhaftes Artefakt.
  Repo seit 21.08.2025; **125.495 Stars**, 11.211 Forks, letzter Push
  05.08.2026 — hochaktiv, aber weiterhin **Version 0.x** und im README als
  „Experimental Goals" gerahmt; kein kommerzielles GitHub-Produkt.
- **Workflow-Kommandos** `/speckit.constitution → specify → clarify → plan
  → tasks → (taskstoissues) → analyze → implement → converge`, plus
  `/speckit.checklist`. Artefakte je Feature-Branch:
  `specs/NNN-name/spec.md`, `plan.md`, `research.md`, `data-model.md`,
  `contracts/`, `tasks.md`; Projektprinzipien in
  `.specify/memory/constitution.md`.
- **30+ Agent-Integrationen** (Copilot, Claude Code, Gemini CLI, Cursor,
  Codex …), Installation via `specify-cli` (uv/PyPI).
- **2026-Entwicklung:** Extensions/Presets/Bundles (z. B. Jira,
  V-Modell-Traceability, Security-Review-Gates, Governance-Presets),
  Skills-basierte Integrationen (v0.16.0), `/speckit.converge` für
  Spec↔Code-Konvergenz, Brownfield-Guide (`docs/guides/evolving-specs.md`
  mit Flow-Forward / Living-Spec / Flow-Back).
- **Breaking Changes:** Kommando-Umbenennung `/specify` → `/speckit.*`,
  CLI-Flag-Wechsel `--ai` → `--integration` — ältere Anleitungen sind
  unbrauchbar.

**[Bericht]** (Sekundärquellen, gekennzeichnet):

- Kritik: „Reinvented Waterfall", Markdown-Flut, lange Laufzeiten, Overhead
  ohne belegten Qualitätsgewinn (Scott Logic, 26.11.2025); „illusion of
  work", ignoriert bestehende Projektstruktur, für Prototypen besser als
  für inkrementelle Arbeit (Discussion #1784); Spec-Drift als Dauerklage
  (HN); Brownfield als schwächste Seite (HN, Discussions #746/#1119/#2046);
  fehlende erzwungene Spec↔Code-Verifikation (DEV „missing 20%").
- Stärken: erzwingt Edge-Case-Denken vor dem Coden; Spec als dauerhafte
  Source of Truth; Agent- und Stack-Agnostik als Alleinstellungsmerkmal;
  gut für abgrenzbare Features und Greenfield (Ry Walker, arXiv 2606.04967,
  Visual Studio Magazine 12.05.2026).

Vollständige Quellenliste in Abschnitt 7.

## 3. Vergleichsrahmen: die drei Schichten

Das README dieses Repos trennt Methodik / Durchsetzung / aktive
Automatisierung. Darauf abgebildet:

| Schicht | dev-process | Spec Kit |
|---|---|---|
| **Methodik** (Regeln, Phasen, Artefakte) | 9 Regeln, Risiko-Tiers, DoR/DoD, ADRs, Journal — risiko-proportional | Constitution + SDD-Phasenmodell — **ein** Pfad für jedes Feature |
| **Durchsetzung** (hält, wenn niemand hinsieht) | CI-`gate_runner` + git-Hooks, deterministisch, merge-blockierend | Kern: keine. `analyze`/`checklist`/`converge` sind **LLM-Selbstprüfungen** im Agent-Lauf; „gate verdict workflow binding" (v0.15) und Security-Gates existieren als Presets/Extensions, nicht als deterministische CI-Garantie |
| **Aktive Automatisierung** (Commands, Skills) | 8 dünne Commands, 3 Harnesses | 10+ Kommandos, 30+ Integrationen, Extensions-Ökosystem |

Das ist der Kernbefund: **die beiden Werkzeuge haben ihren Schwerpunkt in
unterschiedlichen Schichten.** Spec Kit ist primär Schicht 1+3
(Spezifikations-Methodik plus reichhaltige Agent-Automatisierung),
dev-process ist primär Schicht 1+2 (Methodik plus maschinelle
Durchsetzung). Ein „Umstieg" ersetzt daher nicht Gleiches durch Gleiches,
sondern tauscht die Durchsetzungsschicht gegen ein größeres
Automatisierungs-Ökosystem.

## 4. Kriterienmatrix

Kriterien aus den erklärten Zielen des Eigenbaus plus den Zielen der Frage
(Standard, Wartungsaufwand). ✓✓ klar stärker · ✓ vorhanden · (✓) teilweise
· ✗ fehlt im Kern.

| Kriterium | dev-process | Spec Kit | Beleg |
|---|:---:|:---:|---|
| Maschinelle Durchsetzung (merge-blockierend, deterministisch) | ✓✓ | ✗ | `gate_runner`, Hooks vs. LLM-Selbstchecks; DEV „missing 20%" |
| Kein False-Green (ehrliche hart/best-effort-Trennung) | ✓✓ | ✗ | README-Tabelle, SP9/SP25-Honesty-Passes vs. keine Entsprechung |
| Risiko-proportionaler Aufwand (Tier 0 ≠ Tier 3) | ✓✓ | ✗ | `risk-tiers.md` vs. Ein-Pfad-Pipeline; Overhead-Kritik Scott Logic |
| Brownfield (additiv, überschreibt nichts) | ✓✓ | (✓) | copier-additiv + `test_brownfield.py` vs. Evolving-Specs-Guide, aber Praxis-Kritik als schwächste Seite |
| Spezifikations-Tiefe vor Implementierung | (✓) | ✓✓ | Brainstorm/Plan-Phase vs. spec/research/data-model/contracts-Kaskade + clarify |
| Anforderungs-Traceability | ✓ (Story→Test, gate-geprüft) | (✓) (Git/Issues, Extensions) | `feature-registry` vs. `taskstoissues`, V-Modell nur als Extension |
| Kontext über Sessions (Journal, State, Kernel-Schutz) | ✓✓ | (✓) | Journal/Branch-State/Compaction-Schutz vs. specs-Verzeichnisse |
| Messbarkeit der Wirkung | ✓ (Telemetrie-KPIs) | ✗ | `telemetry`-Modul vs. keine Entsprechung |
| Agent-/Harness-Abdeckung | (✓) 3 Adapter | ✓✓ 30+ | Integrationsliste Spec Kit |
| Ökosystem, Community, Schulungsmaterial | ✗ | ✓✓ | 125k Stars, MS-Learn-Training, Extensions-Katalog vs. Bus-Faktor 1 |
| „Anerkannter Standard" | ✗ | (✓) | De-facto-Standard für SDD-*Workflow*; aber 0.x, „experimental", Breaking Changes — kein Standard im Normsinn |
| API-/Update-Stabilität | ✓ (SemVer, `copier update`) | ✗ | v1.37.0 + Update-Pfad vs. 0.x, `--ai`→`--integration`, Command-Renames |
| Eigener Wartungsaufwand | ✗ (alles selbst) | ✓ (Community trägt) | 54 SPs, 8.500 Testzeilen Eigenpflege vs. fremdgepflegtes Toolkit |
| Lizenz / Weitergabe | ✗ (Prosperity, kommerziell lizenzpflichtig) | ✓✓ (MIT) | `LICENSE.md` vs. MIT |

## 5. Gap-Analyse in beide Richtungen

**Was ein Umstieg auf Spec Kit gewinnt:**

1. Fremdgepflegtes, hochaktives Toolkit statt Eigenpflege — der reale
   Kostenpunkt des Eigenbaus (54 Sub-Projekte, Testsuite, Audits) entfällt
   für die Automatisierungsschicht.
2. 30+ Agent-Integrationen statt 3 selbstgepflegter Adapter.
3. Reifere Spezifikationsphase: `specify → clarify → plan` mit
   `research.md`, `data-model.md`, `contracts/` ist tiefer als die
   Brainstorm/Plan-Prosa des Eigenbaus.
4. Ökosystem-Effekte: Schulungsmaterial (Microsoft Learn), Extensions
   (Jira, Compliance-Presets), Einstellbarkeit neuer Teammitglieder auf ein
   bekanntes Vokabular.
5. MIT-Lizenz ohne Nutzungsvorbehalt.

**Was ein Umstieg aufgibt (und Spec Kit im Kern nicht ersetzt):**

1. **Die gesamte Durchsetzungsschicht.** Merge-blockierende, deterministische
   Gates (Review-Attestierung, Kernel-Integrität, Traceability, Drift,
   Security-Floor, SBOM) haben in Spec Kit kein Äquivalent — genau die
   Lücke, die die Spec-Kit-Kritik selbst benennt (fehlende erzwungene
   Spec↔Code-Verifikation, Drift nur so gut wie die Git-Disziplin).
2. **Risiko-Proportionalität.** Spec Kit fährt für jedes Feature dieselbe
   Pipeline; der meistgenannte Kritikpunkt (Overhead, Markdown-Flut) ist die
   direkte Folge. Das Tier-Modell des Eigenbaus ist die Antwort auf genau
   dieses Problem.
3. **Brownfield-Stärke.** Der Eigenbau ist additiv per Design und getestet;
   bei Spec Kit ist Brownfield laut übereinstimmenden Berichten die
   schwächste Seite.
4. **Ehrlichkeits-Garantien** (kein False-Green), **Telemetrie**, typisierte
   ADRs, DoR/DoD-Bindung, Journal/Kontext-Schutz.
5. **Update-Stabilität:** SemVer + `copier update` gegen ein 0.x-Toolkit mit
   dokumentierten Breaking Changes.

**Einordnung des Standard-Arguments:** Spec Kit ist de-facto-Standard für
den *Spezifikations-Workflow* mit Coding-Agents — nicht für maschinell
durchgesetzte Prozess-Governance. Für das, was den Großteil des
Eigenbau-Aufwands ausmacht (Gates, Tests, Honesty-Passes, Module), gibt es
schlicht keinen anerkannten Standard, auf den man umsteigen könnte. Ein
Umstieg würde den Eigenbau-Aufwand also nicht durch einen Standard
ersetzen, sondern die Garantien aufgeben, die der Aufwand erkauft hat.

## 6. Empfehlung

**Kein Umstieg als Ersatz.** Spec Kit und dev-process beantworten
verschiedene Fragen: „Wie komme ich zu einer guten Spezifikation, bevor der
Agent codet?" vs. „Wie stelle ich sicher, dass Regeln auch dann gelten,
wenn niemand hinsieht?" Ein Wechsel tauscht die zweite Antwort gegen eine
bessere erste — das ist für die erklärten Ziele dieses Repos
(Durchsetzung, Brownfield, Risiko-Proportionalität, kein False-Green) ein
Netto-Verlust.

**Aber: die Automatisierungsschicht ist der legitime Prüfstein.** Die
Slash-Commands des Eigenbaus sind laut eigener Architektur „dünne
Ergonomie, kein Modul". Genau dort ist Spec Kit überlegen und genau dort
ist ein Hybrid technisch billig, weil beide Systeme additiv installieren:

- **Pilot-Vorschlag:** In einem Projekt Spec Kit als
  Spezifikations-Frontend für Tier-2/3-Arbeit erproben
  (`/speckit.specify → clarify → plan → tasks` erzeugt `specs/NNN-…/`),
  während Execute/Review/Merge weiter durch die dev-process-Gates laufen.
  Tier 0/1 bleibt beim Quick-Flow — das neutralisiert Spec Kits
  Overhead-Problem durch das Tier-Modell.
- **Zu klären im Pilot:** Doppel-Konventionen (Constitution vs.
  Kernel/PRODUCT.md — eine muss auf die andere verweisen, sonst zwei
  Wahrheiten), Aufnahme von `specs/` in den `doc-drift-gate`, und ob der
  Erkenntnisgewinn der tieferen Spec-Phase die zusätzlichen Artefakte
  rechtfertigt (Telemetrie-Modul liefert die Messbasis).
- **Unabhängig davon übernehmenswert:** einzelne Spec-Kit-Ideen als
  Anleihen — `clarify` als expliziter Schritt im Brainstorm,
  `checklist`-artige „unit tests for English" für Plan-Dokumente.

**Revisions-Trigger:** Die Empfehlung sollte neu bewertet werden, wenn
Spec Kit (a) 1.0 mit Stabilitätszusage erreicht, (b) deterministische,
CI-bindende Gates im Kern (nicht nur als Preset) ausliefert, oder (c) sich
ein Governance-Standard mit Enforcement-Schicht im Ökosystem etabliert.
Dann kippt das Wartungsargument real — heute tut es das nur für die
Schicht, die im Eigenbau ohnehin die dünnste ist.

## 7. Quellen

**Eigenbau (dieses Repo):** `README.md`, `docs/CAPABILITIES.md`,
`CHANGELOG.md`, `template/docs/process/` (kernel.md, mandatory-rules.md,
risk-tiers.md, definition-of-ready-and-done.md, workflow.md.jinja),
`template/scripts/process/gate_runner.py.jinja`, `tests/`
(u. a. `test_brownfield.py`, `test_english_canon.py`), `LICENSE.md`.

**Spec Kit, Primärquellen [Fakt]:**
Repo/README <https://github.com/github/spec-kit> ·
Methodik <https://github.com/github/spec-kit/blob/main/spec-driven.md> ·
Brownfield-Guide <https://github.com/github/spec-kit/blob/main/docs/guides/evolving-specs.md> ·
Integrationen <https://github.com/github/spec-kit/blob/main/docs/reference/integrations.md> ·
Releases <https://github.com/github/spec-kit/releases> ·
Docs-Site <https://github.github.io/spec-kit/> ·
Repo-Metriken via GitHub-API (06.08.2026) ·
Training <https://learn.microsoft.com/en-us/training/modules/spec-driven-development-github-spec-kit-enterprise-developers>.

**Spec Kit, Sekundärquellen [Bericht]:**
Scott Logic (26.11.2025) <https://blog.scottlogic.com/2025/11/26/putting-spec-kit-through-its-paces-radical-idea-or-reinvented-waterfall.html> ·
Discussions <https://github.com/github/spec-kit/discussions/1784>, /746, /1119, /2046 ·
HN <https://news.ycombinator.com/item?id=45154355>, <https://news.ycombinator.com/item?id=45306765> ·
DEV <https://dev.to/kotaroyamame/github-spec-kit-is-80-right-heres-the-missing-20-that-would-make-it-transformative-2bi6> ·
Ry Walker <https://rywalker.com/research/github-spec-kit> ·
arXiv <https://arxiv.org/pdf/2606.04967>, <https://arxiv.org/pdf/2605.01160> ·
Visual Studio Magazine (12.05.2026) <https://visualstudiomagazine.com/articles/2026/05/12/github-spec-kit-takes-off-as-antidote-to-piecemeal-vibe-coding.aspx> ·
MarkTechPost <https://www.marktechpost.com/2026/05/08/meet-github-spec-kit-an-open-source-toolkit-for-spec-driven-development-with-ai-coding-agents/> ·
EPAM-Brownfield-Guide <https://www.epam.com/insights/ai/blogs/using-spec-kit-for-brownfield-codebase> ·
OpenSpec-Vergleich <https://codemyspec.com/blog/openspec-vs-spec-kit>.

Einschränkung: Einige Sekundärquellen waren über den Netz-Proxy nur als
Such-Zusammenfassung erreichbar (403); sie sind durchgängig als
[Bericht] gekennzeichnet und tragen keine der Fakt-Aussagen.
