# SP1 Foundation — Design

**Status:** Entwurf zur Freigabe · **Datum:** 2026-07-01 · **Autor:** Maintainer + Claude
**Sub-Projekt:** SP1 (Foundation) von 3 — siehe [Dekomposition](#dekomposition)

---

## 1. Ziel & Kontext

Ein **portables, harness-agnostisches, modulares Muster** für einen stark
automatisierten KI-gestützten Entwicklungsprozess, das sich aus dem KenniNext-Projekt
destilliert und in beliebige neue oder bestehende Projekte einspielen lässt.

Zwei Einsatzmodi:
- **Greenfield** — leeres/neues Repo, Prozess von Anfang an.
- **Brownfield** — bestehende Sourcen, Prozess additiv nachrüsten.

Drei Harness-Ziele in SP1: **Claude Code** (Quelle), **GitHub Copilot**,
**AGENTS.md** (universeller Standard — deckt Codex, Gemini CLI, Aider u.a.).

**Auslieferung:** ein **copier-Template-Repo** als kanonisches Upstream.
`uvx copier` = quasi zero-install. Verifiziert für Greenfield + Brownfield +
Multi-Repo-Update (siehe §7).

### Leitprinzip

Der Prozess besteht aus **drei Schichten mit fundamental verschiedener Portabilität**:

| Schicht | Inhalt | Portabilität |
|---|---|---|
| **1 — Methodik-Kern** | Rules, Tiers, Zyklus, ADR, Journal, Commits (reines Markdown + git) | **voll portabel** |
| **2 — Harte Durchsetzung** | Gate-Skripte, `pre-commit`, CI — laufen **ohne Agent** | **voll portabel** |
| **3 — Aktive Automatisierung** | Slash-Commands, Skills, Subagents, Hooks, auto-ladende Anker | **harness-spezifisch, degradiert graceful** |

Der garantierte Anker ist **Schicht 2**: CI-Gates + git-Hooks erzwingen Disziplin,
egal welcher Agent (oder Mensch) den Code schrieb. Schicht 3 ist Bequemlichkeit
obendrauf — voll in Claude Code, reduziert in Copilot/AGENTS.md, aber der Prozess
**funktioniert überall**.

---

## 2. Nicht-Ziele (SP1) / YAGNI

Bewusst **außerhalb** von SP1, in eigene Sub-Projekte ausgelagert (§9):

- **SP2 — Brownfield-Architektur-Discovery + Verifikation.** Architektur-Interview
  (Layer, Interfaces, Invarianten, einzubindende Repos, externe Contracts) + Gate,
  das die checkbaren Claims gegen echten Code prüft. SP1 macht Brownfield nur
  **additiv** (Prozess-Dateien reinlegen ohne Clobber), *nicht* smart.
- **SP3 — Multi-Repo / Multi-Mensch.** Governance über N Repos, Cross-Repo-Contracts,
  Mensch+Agent-Koordination. Die *Upstream-Entscheidung* dafür wird in SP1 getroffen
  (copier als Governance-Hebel), der Rest folgt.

Ebenfalls YAGNI in SP1 (Advisor-Direktive „Reichhaltigkeit aus Modulen, nicht aus
CLI-Fläche"):
- Kein bespoke `add`/`remove`/`doctor`-CLI. „Modul nachrüsten" = Antwort in
  `.copier-answers.yml` ändern → `copier update`. `upgrade` fällt aus copier heraus.
- Keine schweren Kenni-Spezifika als Default — sie sind opt-in-Module (§4.3).

---

## 3. Dekomposition

```
Das Muster (Programm)
├─ SP1  Foundation                      ← DIESES SPEC
│      Kern + Adapter + copier-Init + additiver Brownfield-Drop-in
├─ SP2  Brownfield-Architektur-Discovery + Verifikation   ← nächstes Spec
│      Architektur-Fragebogen + Verifikations-Gate
└─ SP3  Multi-Repo / Multi-Mensch                          ← danach
       Upstream-Governance + Cross-Repo-Contracts + Koordination
```

Jedes Sub-Projekt durchläuft seinen eigenen `spec → plan → build`-Zyklus.
SP2/SP3 sind in SP1 nur als **Extension-Points** verankert (§9), nicht gebaut.

---

## 4. Architektur SP1

### 4.1 Repo-Layout (copier-Template)

```
dev-process/                        ← copier-Template-Repo = kanonisches Upstream
├─ README.md                        ← Front-Door: Mensch UND Agent
├─ BOOTSTRAP.md                     ← self-contained, harness-agnostischer Einstieg (Pull-Mode)
├─ copier.yml                       ← Fragen = Modul- + Harness-Auswahl + Projektvariablen
├─ docs/design/                     ← Design-Docs des Musters selbst (dieses Dokument)
└─ template/                        ← wird ins ZIEL-Repo gerendert
   ├─ .copier-answers.yml.jinja     ← DAS MANIFEST (SSOT: aktive Module/Harnesses/Version)
   ├─ docs/process/                 ← NEUTRALE SSOT (immer): Methodik in reinem Markdown
   │  ├─ mandatory-rules.md
   │  ├─ risk-tiers.md
   │  ├─ workflow.md
   │  ├─ commits.md
   │  ├─ journal-state-plans.md
   │  └─ adr/{README.md, template.md}
   ├─ {% if mod.contract_first %}…{% endif %}   ← opt-in-Module (konditional, §4.3)
   ├─ CLAUDE.md.jinja                            ← Adapter Claude Code (immer)
   ├─ {% if h.copilot %}.github/copilot-instructions.md{% endif %}.jinja
   ├─ {% if h.copilot %}.github/instructions/{% endif %} …
   ├─ {% if h.agents_md %}AGENTS.md{% endif %}.jinja
   ├─ {% if h.ci %}.github/workflows/process-gates.yml{% endif %}.jinja  ← manifest-aware CI
   └─ scripts/process/                           ← portable Gate-Skripte (bash + python)
```

### 4.2 Neutrale SSOT: `docs/process/`

Die Methodik lebt in **`docs/process/`** als reines Markdown — **nicht** in
`CLAUDE.md`. Das ist der Unterschied zu Kenni (wo `CLAUDE.md` die SSOT ist und
`AGENTS.md` darauf zeigt): eine tool-neutrale SSOT ist die Voraussetzung für
echte Harness-Agnostik. Alle Adapter (§4.4) sind **dünne Zeiger** auf diese SSOT.

Inhalt (destilliert + universalisiert aus Kenni, Kenni-Spezifika entfernt):

- **`mandatory-rules.md`** — verbindliche Regeln, generalisiert: Verifikation-vor-Behauptung,
  Plan-vor-Arbeit, Struktur-über-Additiv/ein-Owner-pro-Verhalten, Root-Cause-vor-Symptom,
  atomare Commits, Review-Gate-vor-Merge.
- **`risk-tiers.md`** — Tier-Matrix 0–4 + Routing (Tier 0 direkt · 1–2 quick · 3+
  plan→execute→review). Scope, nicht Diff-Größe, bestimmt den Tier.
- **`workflow.md`** — der Zyklus: brainstorm → plan → execute → review, plus
  quick/debug-Abkürzungen. Als Prozess-Prosa, harness-neutral.
- **`commits.md`** — Conventional + atomic Commits, Branching-Disziplin (kein direkter
  `main`, ff-only), `pre-commit`-Hook (git-nativ).
- **`journal-state-plans.md`** — Working-Memory-Konvention: Journal, branch-scoped State,
  Plans-Lifecycle.
- **`adr/`** — ADR-Pattern + Template + README-Index.

### 4.3 Modul-Katalog

**Core (immer installiert):** die `docs/process/`-Dateien aus §4.2 + Adapter + `pre-commit`.

**Opt-in-Module (je eine copier-Frage; jedes self-contained: Methodik-Fragment +
Gate-Skript + CI-Snippet + Adapter-Wissen + Templates):**

| Modul | Zweck | Herkunft (Kenni) |
|---|---|---|
| `doc-drift-gate` | verifiziert Anker-Claims (Pfade/Symbole/Referenzen) gegen echten Code | `check_doc_drift.py` |
| `contract-first` | Interface/API-Contract-SSOT + Drift-Gate | openapi-diff, `api-contract.md` |
| `feature-registry` | User-Story/Acceptance/Test-Traceability + Check | `check_feature_registry.py` |
| `parity-inventory` | Cross-Surface-Parity-SSOT | `feature-inventory.md` |
| `security-floor` | Security-Baseline-Gate | `check_security_floor.py` |
| `kpis` | Prozess-KPI-Sammlung + Grading (+ opt. Notify) | `process_kpis.py` |
| `audit` | Multi-Persona-Audit (Structure/UX/Security) + Synthese | `/audit`, `/audit-synthesis` |
| `e2e-discipline` | E2E-Konventionen + Waits-Lint | `check_e2e_waits.py` |

Beim Init werden nur gewählte Module gerendert (konditionaler Jinja-Dateiname → leer =
übersprungen, §7). Nachrüsten = Antwort umstellen + `copier update`. CI aktiviert das
zugehörige Gate automatisch, weil CI vom Manifest getriggert wird (§4.6).

### 4.4 Adapter (Harness-Schicht)

Jeder Adapter trägt **(a)** einen kompakten, **aus der SSOT gerenderten Digest** der
Always-on-Essentials (Mandatory Rules + Tier-Routing) und **(b)** einen Zeiger auf
`docs/process/` als Autorität. Der Digest ist nötig, weil Adapter-Dateien
*auto-geladen* werden, `docs/process/` aber nur on-demand gelesen wird.

| Harness | Dateien | Automatisierungsgrad |
|---|---|---|
| **Claude Code** (immer) | `CLAUDE.md` (Trunk-Digest + Zeiger); opt. `.claude/commands/` aus dem Zyklus, opt. Skills/Hooks/Subagents | **voll** |
| **Copilot** | `.github/copilot-instructions.md` (Digest, auto); `.github/instructions/*.instructions.md` (path-scoped via `applyTo`-Globs — Analogon zu nested Ankern); `.github/prompts/*.prompt.md` (Analogon zu Slash-Commands, VS Code, manuell) | **reduziert** (keine Skills/Subagents/Hooks) |
| **AGENTS.md** | `AGENTS.md` (Digest + Zeiger; von Codex/Gemini/Aider u.a. auto-gelesen) | **minimal** (eine Datei) |

**Drift-Schutz:** Alle Adapter werden von copier aus **denselben** Answers/Jinja-Partials
gerendert → bei Init/Update konsistent. Ist `doc-drift-gate` aktiv, verifiziert ein Check
zusätzlich, dass der Adapter-Digest zur SSOT passt.

**Ehrliche Degradation (Kernaussage):** Auto-triggernde Skills, Subagent-Fan-out,
Kontext-injizierende Hooks und auto-ladende nested Anker existieren **nur in Claude Code**.
Copilot bekommt Instructions + Prompt-Files, AGENTS.md-Harnesses eine einzige Datei.
Die **Garantie über alle** ist Schicht 2 (CI + git-Hooks). Der Prozess ist überall
befolgbar; die Bequemlichkeit variiert.

### 4.5 Manifest: `.copier-answers.yml`

copiers Answers-File **ist** das Manifest — SSOT für aktive Module, gewählte Harnesses
und die gepinnte Template-Version. Kein zweites Manifest-Format (ein Owner). Es steuert:
- welche Dateien beim Init/Update existieren (copier-Konditionale),
- welche Gates CI ausführt (§4.6),
- worauf `copier update` beim Ziehen einer neuen Prozess-Version aufsetzt (§7).

### 4.6 Manifest-aware CI: `process-gates`

Ein einziger CI-Job liest `.copier-answers.yml` und führt **nur die Gates der aktiven
Module** aus. Ergebnis: Durchsetzung skaliert automatisch mit — `contract-first`
nachrüsten ⇒ CI erzwingt ab sofort das Contract-Gate, ohne die Pipeline anzufassen.
Der Job ist harness-unabhängig (läuft in GitHub Actions, egal wer den Code schrieb).

### 4.7 `BOOTSTRAP.md` — der eigentliche Agnostik-Anker

Der abholende Agent hat beim ersten Kontakt **noch keinen Adapter**. Deshalb ist
`BOOTSTRAP.md` reine, von *jedem* Agent in *jedem* Harness befolgbare Prosa + ein
portables Kommando. Es ist self-contained (setzt nichts voraus) und beschreibt beide
Greenfield-Wege (§5). Das — nicht die Adapter-Vielfalt — ist der harness-agnostische Kern.

---

## 5. Onboarding-Flows

### 5.1 Greenfield

Zwei Wege, beide enden auf demselben `copier copy`, beide im README/`BOOTSTRAP.md`
beschrieben:

- **Pull-Mode** („LLM holt sich das Muster"): Man sagt dem Agenten im leeren Repo:
  *„Richte den Entwicklungsprozess aus `github.com/Crashman1983/dev-process` ein,
  folge dessen `BOOTSTRAP.md`."* Der Agent liest `BOOTSTRAP.md` und führt aus:
  ```
  uvx copier copy gh:Crashman1983/dev-process .
  ```
- **Copy-Mode** („reinkopieren + Init"): Mensch führt denselben Befehl selbst aus.

copier stellt die Modul-/Harness-Fragen (interaktiv oder via `--data`), rendert nur
die gewählten Teile, schreibt `.copier-answers.yml`. Fertig.

### 5.2 Brownfield (SP1: nur additiv)

Im bestehenden Repo:
```
uvx copier copy gh:Crashman1983/dev-process .
```
copier legt die Prozess-Dateien **additiv** an und **überschreibt Bestehendes nicht**
ungefragt (verifiziert, §7). Kollidiert eine Datei (z.B. vorhandene `AGENTS.md`),
markiert copier den Konflikt statt zu clobbern — manuell mergen.

**Grenze (bewusst):** SP1 fragt **nicht** nach Code-Ort, einzubindenden Repos oder
Architekturvorgaben und prüft **nichts** gegen echten Code. Das ist SP2. SP1 liefert
den Prozess-Rahmen; die Architektur-Erfassung ist der nächste Schritt.

---

## 6. Testing / Dogfooding

Das Meta-Tool gehorcht seinem eigenen Prozess (das `dev-process`-Repo nutzt SP1 auf sich selbst):

- **Render-Smoke:** `copier copy` in ein Temp-Verzeichnis für repräsentative
  Answer-Kombinationen (core-only; core+contract-first; alle Module; jede Harness-Teilmenge)
  → keine leeren Konditionale-Reste, valide YAML/CI, Skripte syntax-clean.
- **Idempotenz:** zweites `copier update` ohne Answer-Änderung ⇒ kein Diff.
- **Additiv-Garantie:** `copier copy` über ein Fixture-Repo mit vorbelegten Dateien
  ⇒ keine Fremd-Datei überschrieben (Konfliktmarker statt Clobber).
- **Gate-Aktivierung:** Manifest mit Modul X ⇒ `process-gates` führt Gate X aus;
  ohne X ⇒ führt es nicht aus.
- **Adapter-Konsistenz:** gerenderte Adapter-Digests sind über Harnesses inhaltsgleich
  zur SSOT.

CI des Musters selbst läuft diese Render-Matrix bei jedem Commit.

---

## 7. copier-Mechanik (verifiziert 2026-07-01)

- **Konditionale Modul-Inklusion** — Jinja-Dateiname, der zu leer rendert, wird
  übersprungen: `{% if use_precommit %}.pre-commit-config.yaml{% endif %}.jinja`.
  ([creating](https://copier.readthedocs.io/en/stable/creating/),
  [Issue #216](https://github.com/copier-org/copier/issues/216))
- **In bestehendes Repo anwenden** — „takes care of not overwriting existing files
  unless instructed to do so". ([docs](https://copier.readthedocs.io/en/stable/))
- **Update ohne lokale Edits zu zerstören** — Diff-Reapply mit Konfliktmarkern
  (inline/`.rej`), Antworten in `.copier-answers.yml`; das ist der Multi-Repo-Governance-Hebel
  für SP3. ([updating](https://copier.readthedocs.io/en/stable/updating/))

---

## 8. Ehrliche Grenzen (was SP1 NICHT tut)

- Keine smarte Brownfield-Architektur-Erfassung/-Verifikation (→ SP2).
- Keine Multi-Repo-Governance/Cross-Repo-Contracts (→ SP3; Upstream-Hebel steht aber).
- Keine Portierung der Claude-spezifischen aktiven Automatisierung auf andere Harnesses
  (technisch unmöglich — es gibt kein universelles Skill-/Hook-/Subagent-System).
  Andere Harnesses bekommen Instructions + (Copilot) Prompt-Files + CI-Enforcement.
- Kein automatischer semantischer Architektur-Konformitäts-Check (auch SP2 nur
  best-effort — siehe §9).

---

## 9. Extension-Points (SP2/SP3 — heute nur verankert)

### SP2 — Brownfield-Architektur-Discovery + Verifikation
- **Hook:** neues Modul `arch-onboarding` + Harness-Prompt/Skill „Architektur-Interview".
- **Zwei Artefakte:** (a) strukturierter **Fragebogen** (Layer, Interfaces, Invarianten,
  einzubindende Repos, externe Contracts); (b) **Verifikations-Gate**, das checkbare Claims
  prüft.
- **Ehrliche Decke:** Existenz/Ort (Pfade, Symbole, Interfaces vorhanden) ist mechanisch
  garantierbar; Architektur-*Konformität* („Domain importiert nie Infra") braucht
  sprach-spezifische Arch-Lints (import-linter / dependency-cruiser / ArchUnit) oder
  Agent-Urteil — **best-effort, nicht portabel garantiert**. Das Gate verdrahtet einen
  Arch-Linter, *falls* im Zielprojekt vorhanden; sonst Agent-Review.
- Produziert einen persistenten **Architektur-Anker** (analog `ARCHITECTURE.md` +
  Stack-Anker), der selbst vom `doc-drift-gate` überwacht wird.

### SP3 — Multi-Repo / Multi-Mensch
- **Hook:** `.copier-answers.yml`-Version-Pin + `copier update` als Governance (eine
  Prozess-Version, N Repos).
- **Koordination:** GitHub Issues/PRs/Org-Projects als inhärent multi-personen- +
  multi-repo-Substrat; Kennis `[BOTH]`-Issue-Muster + Claim/Heartbeat generalisieren
  auf **Menschen UND Agenten**.
- **Contracts:** Contract-SSOT wird cross-repo statt cross-subtree (baut auf
  `contract-first`-Modul auf).

---

## 10. Offene Entscheidungen (für /planning)

1. **Umfang der Regel-Universalisierung:** welche der 10 Kenni-Mandatory-Rules sind
   wirklich universell vs. Kenni-spezifisch? (Erster Cut: Rules 1/2/5/9/10 universell;
   3/4/6 an Module gebunden; 7/8 an Harness/Gates.)
2. **Digest-Rendering-Mechanik:** Jinja-Include-Partial vs. copier-Task-Hook, der den
   Digest aus der SSOT generiert.
3. **Skript-Sprache der Gates:** bash-only vs. python (ubiquitär, aber Dep). Vorschlag:
   python mit bash-Wrapper, `uv run` als Runner.
4. **Modul-Granularität:** `doc-drift-gate` core-nah machen (fast immer nützlich) oder
   strikt opt-in lassen?
5. **`.claude/commands/` im Adapter:** volle Slash-Command-Portierung des Zyklus oder
   nur ein Minimal-Set (prime/plan/execute/review)?

---

## Zusammenfassung

SP1 liefert einen **portablen Prozess-Rahmen** als copier-Template: neutrale
Markdown-SSOT (`docs/process/`) + CI-Enforcement + dünne Adapter für
Claude Code / Copilot / AGENTS.md, mit opt-in-Modulen für die schweren Gates.
Greenfield (pull + copy) und additiver Brownfield-Drop-in funktionieren sofort.
Die smarte Architektur-Erfassung (SP2) und Multi-Repo/Multi-Mensch (SP3) sind
sauber als Extension-Points verankert, aber nicht Teil von SP1.
