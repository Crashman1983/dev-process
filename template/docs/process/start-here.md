# Start Here / Einstieg

## Zweck / Purpose

**Deutsch:** Dieses Repository hat den Entwicklungsprozess installiert. Das ist
erst die Prozess-Baseline, nicht automatisch ein fachlich eingerichtetes
Projekt. Die Einrichtung soll von einem LLM begleitet werden: Das LLM fragt
schrittweise nach, dokumentiert die Antworten und legt erst dann die passenden
Projektartefakte an.

**English:** This repository has the development process installed. That is the
process baseline, not an automatically onboarded product project. Setup is meant
to be guided by an LLM: the LLM asks step by step, documents the answers, and
only then creates the project-specific artifacts.

## Erste Ausfuehrung / First run

**Deutsch:**

1. Pruefe, dass die Prozessdateien vorhanden sind: `CLAUDE.md`,
   `docs/process/`, `.copier-answers.yml` und
   `scripts/process/gate_runner.py`.
2. Initialisiere Git, falls das Repository neu ist.
3. Installiere lokale Hooks, wenn das Modul `git-hooks` aktiv ist:
   `bash scripts/process/install-hooks.sh`.
4. Fuehre die Gates aus: `python scripts/process/gate_runner.py`.
5. Lies `docs/process/mandatory-rules.md` und
   `docs/process/risk-tiers.md`.
6. Lege vor Produktarbeit einen Prozess-Baseline-Commit an.

**English:**

1. Confirm that the process files exist: `CLAUDE.md`, `docs/process/`,
   `.copier-answers.yml`, and `scripts/process/gate_runner.py`.
2. Initialize Git if this is a new repository.
3. Install local hooks if the `git-hooks` module is active:
   `bash scripts/process/install-hooks.sh`.
4. Run the gates: `python scripts/process/gate_runner.py`.
5. Read `docs/process/mandatory-rules.md` and
   `docs/process/risk-tiers.md`.
6. Create a process-baseline commit before product work starts.

**Deutsch:** Gruene Gates bedeuten in dieser Phase: "Der Prozess ist
installiert." Sie bedeuten noch nicht, dass Architektur, Anforderungen,
Contracts, Parity oder Security-Regeln fachlich eingerichtet sind.

**English:** Green gates at this stage mean: "the process is installed." They
do not yet mean that architecture, requirements, contracts, parity, or security
rules have been onboarded as project facts.

## LLM-gefuehrtes Onboarding / LLM-guided onboarding

**Deutsch:** Das LLM fuehrt die Einrichtung wie ein Brainstorming. Es fragt
immer nur wenige Punkte auf einmal ab, fasst die Antworten zusammen, nennt
Annahmen explizit und schreibt erst dann Dateien.

**English:** The LLM guides setup like a brainstorming session. It asks only a
few questions at a time, summarizes the answers, labels assumptions explicitly,
and writes files only after the answers are clear.

### Startfragen / Starting questions

**Deutsch:**

1. Frage: Ist das Projekt Greenfield oder Brownfield?
2. Frage: Was ist das Ziel des Projekts in einem Absatz?
3. Frage: Wer nutzt das Projekt und was ist der erste nutzbare Erfolg?
4. Frage: Welche Technologie-/Stack-Vorgaben gibt es?
5. Frage: Welche Risiken sind schon bekannt: Auth, Persistenz, externe
   Schnittstellen, Security, mehrere Oberflaechen?

**English:**

1. Question: Is this project Greenfield or Brownfield?
2. Question: What is the project goal in one paragraph?
3. Question: Who uses the project and what is the first useful outcome?
4. Question: Which technology or stack constraints exist?
5. Question: Which risks are already known: auth, persistence, external
   interfaces, security, multiple surfaces?

### Fragekompass / Question compass

**Deutsch:** Nutze diese Kategorien als Kompass, nicht als Formular. Stelle nur
Fragen, die fuer den aktuellen Modus relevant sind. Wenn eine Antwort unbekannt
ist, als offene Frage oder Annahme dokumentieren; nicht erfinden.

- Zweck: Welches Problem loest das Projekt, und woran erkennt man Nutzen?
- Nutzer: Wer nutzt das System, und welche Rolle hat Prioritaet?
- Erster Slice: Was ist der kleinste nutzbare End-to-End-Erfolg?
- Stack — pro Ebene erfragen; offene Ebenen laufen durch den Vorschlagsmodus
  (siehe Dialogregeln):
  - Frontend: Welche Technologie traegt jede Oberflaeche (Framework,
    Rendering, Build), oder ist das Projekt bewusst ohne Frontend?
  - Backend: Welche Sprache, welches Framework und welche Laufzeit sind
    gesetzt oder bevorzugt?
  - Storage: Welche Art von Persistenz (relational, dokumentenorientiert,
    Dateien, keine), welches konkrete System, und wie laufen Migrationen?
  - API/Kommunikation: Wie sprechen eigene Komponenten und Oberflaechen
    miteinander (REST, GraphQL, gRPC, Events, Queues), und wie wird das
    versioniert? Die Antwort informiert die Modulwahl (`contract-first`,
    `contracts-drift`, `parity`).
  - Deployment: Welche Laufzeitumgebung und Deployment-Ziele sind gesetzt?
- Codebasis: Gibt es vorhandenen Code, Tests, CI, Docs oder Datenmodelle?
- Architektur: Welche Code-Wurzeln, Layer, Schnittstellen und Grenzen sind
  tatsaechlich vorhanden oder geplant?
- Daten/Auth/Security: Gibt es Persistenz, personenbezogene Daten,
  Berechtigungen, Secrets oder verbotene Muster?
- Integrationen: Welche APIs, Events, Dateien, Jobs oder externen Systeme sind
  beteiligt?
- Oberflaechen: Gibt es Web, Mobile, CLI, API-only oder mehrere Zieloberflaechen?
- Qualitaet: Welche Tests, Gates, Performance- oder Betriebsanforderungen sind
  von Anfang an wichtig?
- Organisation: Gibt es Issues, Labels, Release-Regeln, Review-Pflichten oder
  mehrere Agenten/Menschen?

**English:** Use these categories as a compass, not as a form. Ask only the
questions relevant to the current mode. If an answer is unknown, document it as
an open question or assumption; do not invent it.

- Purpose: Which problem does the project solve, and how is value recognized?
- Users: Who uses the system, and which role has priority?
- First slice: What is the smallest useful end-to-end outcome?
- Stack — ask per layer; open layers go through proposal mode (see dialogue
  rules):
  - Frontend: Which technology carries each surface (framework, rendering,
    build), or is the project deliberately frontend-free?
  - Backend: Which language, framework, and runtime are fixed or preferred?
  - Storage: What kind of persistence (relational, document, files, none),
    which concrete system, and how do migrations run?
  - API/communication: How do the project's own components and surfaces talk
    to each other (REST, GraphQL, gRPC, events, queues), and how is that
    versioned? The answer informs the module choice (`contract-first`,
    `contracts-drift`, `parity`).
  - Deployment: Which runtime environment and deployment targets are set?
- Codebase: Is there existing code, tests, CI, docs, or data model?
- Architecture: Which code roots, layers, interfaces, and boundaries actually
  exist or are planned?
- Data/Auth/Security: Is there persistence, personal data, authorization,
  secrets, or forbidden patterns?
- Integrations: Which APIs, events, files, jobs, or external systems are
  involved?
- Surfaces: Is this web, mobile, CLI, API-only, or multiple target surfaces?
- Quality: Which tests, gates, performance, or operations requirements matter
  from the beginning?
- Organization: Are there issues, labels, release rules, review duties, or
  multiple agents/humans?

### Dialogregeln / Dialogue rules

**Deutsch:**

- Immer den Modus nennen: Greenfield oder Brownfield.
- Maximal drei Fragen auf einmal stellen.
- Nach jeder Antwort kurz zusammenfassen, was verstanden wurde.
- Annahmen markieren und bestaetigen lassen, bevor Dateien geschrieben werden.
- Vorschlagsmodus: Fehlt fuer eine Stack-Ebene eine Vorgabe, leite 1-3
  Optionen aus Ziel, erstem Slice und Rahmenbedingungen ab, nenne die
  Trade-offs, markiere eine Empfehlung und lasse sie bestaetigen. Vorschlaege
  sind immer klar als Vorschlag gekennzeichnet — Fakten werden weiterhin nie
  erfunden.
- Keine echten Architektur-, Story-, Contract-, Parity- oder Security-Artefakte
  schreiben, solange die Fakten nicht belastbar sind.
- Am Ende die naechsten drei konkreten Schritte nennen.

**English:**

- Always name the mode: Greenfield or Brownfield.
- Ask at most three questions at a time.
- After each answer, briefly summarize what was understood.
- Mark assumptions and get confirmation before writing files.
- Proposal mode: if a stack layer has no given preference, derive 1-3 options
  from the goal, the first slice, and the known constraints, name the
  trade-offs, mark one recommendation, and get it confirmed. Proposals are
  always clearly labeled as proposals — facts are still never invented.
- Do not write real architecture, story, contract, parity, or security artifacts
  until the facts are defensible.
- End with the next three concrete steps.

### Ergebnis des Dialogs / Dialogue output

**Deutsch:** Nach dem Dialog haelt das LLM mindestens fest:

- Greenfield oder Brownfield;
- Projektziel und erster nutzbarer Slice;
- initialer Stack je Ebene (Frontend, Backend, Storage, API/Kommunikation,
  Deployment) und Source-Layout — jede Ebene ist entschieden,
  vorgeschlagen-und-bestaetigt oder eine dokumentierte offene Frage;
- ob `ARCHITECTURE.md` schon einen echten `arch`-Block bekommen kann;
- ob echte Eintraege unter docs/process/feature-registry/ benoetigt werden;
- ob Contracts, Parity oder Security-Floor jetzt echte Artefakte brauchen oder
  bewusst noch inert bleiben.

**English:** After the dialogue, the LLM records at least:

- Greenfield or Brownfield;
- project goal and first useful slice;
- initial stack per layer (frontend, backend, storage, API/communication,
  deployment) and source layout — each layer decided,
  proposed-and-confirmed, or a documented open question;
- whether `ARCHITECTURE.md` can already receive a real `arch` block;
- whether real entries under docs/process/feature-registry/ are needed;
- whether contracts, parity, or security floor need real artifacts now or stay
  intentionally inert.

## Greenfield-Start / Greenfield start

**Deutsch:** Nutze diesen Pfad, wenn noch kein Produktcode existiert.

1. Dokumentiere Produktziel, Nutzer und ersten Slice in `.process-work/`.
2. Klaere den Stack je Ebene (Frontend, Backend, Storage, API/Kommunikation,
   Deployment); fehlt eine Vorgabe, nutze den Vorschlagsmodus. Waehle das
   bestaetigte Ergebnis und das Source-Layout so klein, dass die erste
   Architektur wahr beschrieben werden kann, und halte grundlegende
   Stack-Entscheidungen als ADR fest.
3. Erzeuge erst dann Quellverzeichnisse und Interface-Dateien.
4. Ersetze den inert markierten `arch-example` in `ARCHITECTURE.md` nur durch
   einen echten `arch`-Block, wenn die referenzierten Pfade existieren.
5. Wenn `feature-registry` aktiv ist, kopiere den Seed unter
   docs/process/feature-registry/ und entferne `.example` aus dem Dateinamen,
   sobald die erste echte User Story bekannt ist.
6. Wenn `security-floor` aktiv ist, kopiere die Datei
   security-floor.example.json zu einer Policy-Datei namens
   security-floor.json, sobald reale verbotene Muster bekannt sind.
7. Lasse optionale Beispiele fuer `parity`, `contract-first` und
   `contracts-drift` inert, bis echte Capabilities, Schnittstellen oder externe
   Contracts existieren.
8. Starte neue Arbeit ueber das Tier-Routing: Tier 1-2 nutzt Quick; Tier 3+
   nutzt Brainstorm -> Plan -> Execute -> Review.

**English:** Use this path when no product code exists yet.

1. Document product goal, users, and first slice in `.process-work/`.
2. Settle the stack per layer (frontend, backend, storage, API/communication,
   deployment); where no preference is given, use proposal mode. Choose the
   confirmed result and the source layout small enough that the first
   architecture can be described truthfully, and record fundamental stack
   decisions as ADRs.
3. Create source directories and interface files only then.
4. Replace the inert `arch-example` in `ARCHITECTURE.md` with a real `arch`
   block only when the referenced paths exist.
5. If `feature-registry` is active, copy the seed under
   docs/process/feature-registry/ and remove `.example` from the filename once
   the first real user story is known.
6. If `security-floor` is active, copy the file security-floor.example.json to
   a policy file named
   security-floor.json once real forbidden patterns are known.
7. Keep optional examples for `parity`, `contract-first`, and
   `contracts-drift` inert until real capabilities, interfaces, or external
   contracts exist.
8. Start new work through tier routing: Tier 1-2 uses Quick; Tier 3+ uses
   Brainstorm -> Plan -> Execute -> Review.

## Brownfield-Start / Brownfield start

**Deutsch:** Nutze diesen Pfad, wenn bereits Produktcode existiert.

1. Schreibe das Projekt nicht um, nur um zum Prozess zu passen.
2. Inventarisiere zuerst echte Code-Wurzeln, Tests, Architekturgrenzen,
   Features, externe Contracts, Security-Invarianten und Oberflaechen.
3. Befuelle `ARCHITECTURE.md` aus dem echten Code. Wenn eine Regel nur
   angestrebt ist, dokumentiere sie in einem ADR als `change-planned` oder
   `tolerated`, nicht als bereits erfuellt.
4. Lege Registry-Eintraege nur fuer Fakten an, die du belegen kannst: echte
   Stories, echte Tests, echte Contracts, echte Parity-Luecken, echte
   Security-Regeln.
5. Fuehre nach jedem Onboarding-Slice `python scripts/process/gate_runner.py`
   aus.
6. Committe das Onboarding in kleinen Schritten: Architektur-Baseline,
   Feature-Registry, Contracts, Parity, Security-Floor.
7. Starte Produktarbeit erst, wenn die relevante Baseline fuer diesen Bereich
   vorhanden ist.

**English:** Use this path when product code already exists.

1. Do not rewrite the project just to fit the process.
2. Inventory real code roots, tests, architecture boundaries, features,
   external contracts, security invariants, and surfaces first.
3. Fill `ARCHITECTURE.md` from real code. If a rule is only aspirational,
   document it in an ADR as `change-planned` or `tolerated`, not as already
   satisfied.
4. Create registry entries only for facts you can defend: real stories, real
   tests, real contracts, real parity gaps, real security rules.
5. Run `python scripts/process/gate_runner.py` after each onboarding slice.
6. Commit onboarding in small steps: architecture baseline, feature registry,
   contracts, parity, security floor.
7. Start product work only after the relevant baseline for that area exists.

## Definition von bereit / Definition of ready

**Deutsch:** Das Projekt ist bereit fuer normale prozessgefuehrte Entwicklung,
wenn:

- die Prozess-Baseline committet ist;
- Greenfield oder Brownfield in `.process-work/` festgehalten ist;
- `ARCHITECTURE.md` entweder ehrlich "noch nicht onboarded" ist oder einen
  echten `arch`-Block mit existierenden Pfaden enthaelt;
- jedes aktive optionale Modul entweder bewusst inert bleibt oder mindestens
  ein echtes Projektartefakt hat;
- `scripts/process/gate_runner.py` laeuft und alle Hinweise als bekannter
  Onboarding-Stand verstanden sind.

**English:** The project is ready for normal process-driven development when:

- the process baseline is committed;
- Greenfield or Brownfield is recorded in `.process-work/`;
- `ARCHITECTURE.md` either honestly remains "not onboarded yet" or contains a
  real `arch` block with existing paths;
- each active optional module either intentionally stays inert or has at least
  one real project artifact;
- `scripts/process/gate_runner.py` runs and all notes are understood as known
  onboarding state.
