# Changelog — dev-process

Die vollständige Sub-Projekt-Historie, aus dem README hierher ausgelagert
(das README orientiert, dieses Dokument archiviert). Neue Releases nennen im
README nur die aktuelle Version und schreiben die Historie hier fort.

## Status-Narrativ (chronologisch)

SP1 (Foundation) + SP2 (Architektur-Onboarding) + SP3
(feature-registry, github-issues, contracts-drift) + SP4 (git-hooks,
contract-first, parity, security-floor) + Capstone (command-adapters,
`v1.0.0` — das volle Kenni-Command-Set, harness-nativ) + SP7 (ci-adapters:
GitLab CI + Install-Fallbacks) + SP8 (english-canon + ehrliche Ökonomie) +
SP9 (audit-fixes: False-Greens geschlossen, Failure-Modes sprechen) +
SP10 (telemetry: GRADE-Trace + KPI-Cockpit, Effizienz messbar) +
SP11 (Re-Audit + Public-Readiness) + SP12 (verification-independence:
Verifikation unabhängig, tier-gestaffelt) + SP13 (anchor-guidance) +
SP14 (junior-legibility: Review-Checkliste, Tier-Erkennung) +
SP15 (arch-docs: arc42/C4-lite Architektur-Doku-Modul) +
SP16 (review-breadth: Performance/Observability-Dimensionen) +
SP17 (parallel-friction: Journal-Sharding, Parallel-efforts-Doku) +
SP18 (decision-records: getyptes Decision Record + Core-Integritäts-Gate) +
SP19 (review-enforcement: Review-Unabhängigkeit als gegatete Attestierung) +
SP20 (issue-centricity: Issue-before-code für Tier 3+, geschärfte Claim-Disziplin) +
SP21 (dependency-sequencing: `blocked_by` + Zyklus-Gate + ready-order-Tool) +
SP22 (github-master: Issues als SSOT über hermetischen Snapshot-Gate + Sync) +
SP23 (sub-issues: `parent`-Dekomposition + Zyklus/Drift-Gate + Hierarchie-View) +
SP24 (project-board: hermetischer Spalten-Konsistenz-Gate + Board-Automation) +
SP25 (github-master honesty-pass: Freshness-Disclosure + ehrliche Doc-Fixes) +
SP26 (Rule-5-Konsolidierung: increment-vs-rewrite-Entscheidung + Gate-Refactor) +
SP27 (story-lifecycle-closure: done-braucht-Issue hart, DoR/DoD-View, Discovered-work-Inbox) +
SP28 (audit-hardening: sechs Persona-Audits über zwei Modelle — zwei Live-Bugs
gefixt, Konsens-Findings ausgeräumt, verifizierte Zweige regressionsgesichert) +
SP29 (tier-model: Skala von 0–4 auf zero-based **0–3** kollabiert — das unter
PR/Merge-Pflicht faktisch fiktive Tier 0 „direct commit" in Tier 1 gefaltet;
jede verbleibende Grenze trägt Gewicht; Gate-Schwellen + Anchor/Doku remapped) +
SP30 (decision-flow-wiring: Decision Records in die Phasen eingehängt —
Brainstorm liest sie als Constraints, Plan nennt seinen Decision-Kontext,
Execute stoppt bei entdeckter Grundsatzentscheidung, Review-Checkliste fragt
nach fehlendem/widersprochenem/still-obsoletem Record) +
SP31 (product-frame: `PRODUCT.md` als **Core**-Artefakt — Produktrahmen mit
Goals/Non-Goals/Constraints, im Init-Dialog erstellt, von allen Phasen als
Richtungs-Constraint gelesen, immer aktives Gate: fehlend hart,
not-onboarded ehrliche Note, Platzhalter-nach-Onboarding + tote Refs hart) +
SP32 (review-visibility: Audits/Reviews samt Prompt, Verdikt und Findings als
Report-Artefakt + GitHub-Issue — `FINDING`-Grammatik, `publish_review.sh` mit
Kampagnen-Bündelung unter Parent-Issue, hermetische Bindung: unpubliziert
ohne Waiver hart, Follow-up-Finding ohne Issue hart, gesplittete Kampagne hart;
entdeckte Arbeit in korrekter Form: `finding`-/`bug`-Templates mit EARS-AKs +
Origin-Sektion, Rückverlinkung + Kommentar am Ausgangsitem als Konvention) +
SP33 (gate-hardening aus 4-Session-Audit: 8 reproduzierte Gate-Defekte
geschlossen — Tier-Range-Validierung, Report-Header-Split auf jeder Ebene,
geteilte Fence/Bullet-Disziplin für REVIEW/GRADE, Decisions-Sektionsparser,
github-master fail-clean, Kampagnen-Ref-Normalisierung, Symbol-Wortgrenze,
code_roots-Skalar; `v1.20.1` Patch aus dem SP33-Review: Unicode-Ziffer-Crash
im Tier-Check, Header-Split auf jeden Überschriften-Stil, ehrliche Symbol-Grenze) +
SP34 (flow-closure: Plan-Archivierung als benannter Merge-Schritt,
Baseline-Commit-Bypass, tracker-lose Waiver für done-Story + Follow-up-Finding,
neutrale `kernel.md`, Reviewer-Grammatik im /review, Tier-1/2-Grenze geschärft +
Tier-0-1 als Self-Check-Band) + SP35 (economics/discoverability: Anchor listet
aktive Modul-Docs, /quick trägt eigene Schritte, /prime liest inbox,
Which-artifact-when-Router, Multi-Agent-SSOT-Ehrlichkeit, Mid-Size-Trap benannt)
ausgeliefert, `v1.21.0`.

SP36 (Backport-Batch 1 aus dem parallelen
law-aidev-Zweig, Issue #22: pre-push prüft die **gepushten Commits** statt des
Working Tree (Wegwerf-Worktree), neues opt-in **`sbom`**-Modul mit
CycloneDX-Lizenz-Attestierung, feature-registry-Advisory für unter-granulare
Akzeptanz) ausgeliefert, `v1.22.0`. SP37 (Backport-Batch 2, Issue #22:
read-only Koordinations-Dashboards `who_is_working.py` (Nebenläufigkeits-
Preflight) und `attention.py` (wo ein Mensch hinschauen sollte — inkl.
Issue-Hygiene) unter `github-issues`, Parallel-agents-Workflow-Abschnitt; die
label-mutierenden Lifecycle-Tools und `status:hold`/`awaiting-ack`-Overlays
bewusst ausgelassen) ausgeliefert, `v1.23.0`. SP38 (bindende **Definition of
Ready & Done** als Core-Doc `definition-of-ready-and-done.md` — pro Arbeitseinheit,
Enforcement an bestehende Mechanismen delegiert, lebende Checklisten; Namens-Kollision
mit der Projekt-Onboarding-Reife in `start-here.md` aufgelöst; in Brainstorm/Review,
Regel 7 und Review-Checkliste eingehängt; Konsolidierung von Backport-Patch 0013)
ausgeliefert, `v1.24.0`.

SP39 (4-Perspektiven-Funktionsaudit: sbom-Gate
gehärtet — SPDX-`OR`/`AND`-Auswertung, nur Root-Komponente exempt,
Multi-License-Konjunktion, exakte Coverage-Namen, kein doc-drift-Rotlauf beim
frischen Render; `attention` zählt nur existierende Tests; DoR/DoD- und
Tier-Routen-Kohärenz; `ARCHITECTURE-OVERVIEW.md` `.jinja`; BOOTSTRAP-
`github_master`-Key; interne Sprint-Refs aus Adopter-Code entfernt)
ausgeliefert, `v1.25.0`. SP40 (Kernel-Integrität als viertes **Core-Gate**
`check_kernel.py`: der immer-geladene Regel-Block muss in jedem vorhandenen
Anker byte-identisch zu `kernel.md` sein — eine still gelöschte/geänderte
Regel blockt den Merge; schließt die „Regeln vergessen weil ungegatet"-Lücke,
die ein abgeleiteter Prozess sichtbar machte) ausgeliefert, `v1.26.0`.
SP41 (Kernel überlebt Compaction: selbst-heilende Direktive *im* Kernel-Block
— bei Resume/Compaction Kernel+Regeln neu lesen, byte-identisch in allen vier
Kopien und damit vom Kernel-Gate unentfernbar; Phasen-Re-Hydration in
/execute, /review, /prime; ehrliche Grenze + Pro-Harness-Realität in
start-here dokumentiert — ein Gate sieht den Live-Kontext nicht) ausgeliefert,
`v1.27.0`. SP42 (Meta-Review „Reichweite vor Tiefe" für Solo-Devs/kleine
Teams: **Profile** statt 13 Modul-Booleans — eine `profile`-Frage
(minimal/solo/team/custom) leitet den Modul-Default ab, explizites `modules`
überschreibt weiter; dazu der **Härtungs-Ratchet** in start-here: Modul
einschalten, wenn sein Trigger eintritt — erste Persistenz → security_floor,
zweite Surface → parity usw.; Lockern ist eine dokumentierte
Prozessentscheidung) ausgeliefert, `v1.28.0`.

SP43 (Quick Wins „verlässlich + lesbar": `setup_branch_protection.sh` — der
eine Schritt, der aus „Gate läuft" „Gate blockt" macht, als idempotenter
Einzeiler (nicht-destruktiv, ehrliche Fehlermodi für Private-Repo/Free-Plan);
Actions-Job-Id von `gates` auf `process-gates` angeglichen, damit der
dokumentierte Required-Check-Kontext überhaupt erfüllbar ist; SP-Historie aus
dem README in dieses CHANGELOG ausgelagert) ausgeliefert, `v1.29.0`.

SP44 (Nachvollziehbarkeit als Werkzeug: `trace.py` — die ganze Geschichte
eines Arbeitsstücks in einem Kommando: Story, Issue (Snapshot offline zuerst,
dann `gh`, sonst nur Ref), aktive/archivierte Pläne, Commits, geparste
`REVIEW work=`-Attestierungen, Reports samt FINDINGs; read-only, Core,
unerreichbare Quellen werden benannt statt still übersprungen) ausgeliefert,
`v1.30.0`.

`v1.30.1` (Merge-Gate-Review über den v1.26–v1.30-Bogen, zwei unabhängige
Reviewer: Blocker im Branch-Protection-Skript geschlossen — bestehende Regel
wird nie mehr überschrieben (GET-404-Ambiguität); Kernel-Gate erzwingt exakt
einen Block und lehnt leeren Kanon ab; trace-Präzision (kein Bare-Number-Grep,
leere Query verweigert); Ratchet als einziger Owner mit allen 13 Modulen;
README/Update-Semantik-Kohärenz).

SP45 (Tiefe I — DoR als Gate: `gh_sync` leitet die Ready-Fakten aus dem
Live-Issue ab (typed/EARS/`## Deviations`-Body-Note als benannter Escape) und
legt sie als `dor`-Slot in den Snapshot; das hermetische github-master-Gate
failt hart, wenn eine in-progress-Story ein nicht-Ready-Issue ohne Deviation
verlinkt — proposed noch nicht gestartet, done Sache des Review-Gates; alter
Snapshot degradiert ehrlich zur Re-sync-Note) ausgeliefert, `v1.31.0`.

SP46 (Tiefe II — Architektur-Grenzen als Floor-Regeln: kein 14. Modul,
sondern der bestehende Owner — security-floor kann per `applies_to` gescopte
Regeln schon; neu: optionales `adr`-Feld je Regel (hängende Links hart),
Arch-Beispielregel, Moduldoc-Sektion mit ehrlicher Decke (Regex-Floor, kein
Architektur-Review), Ratchet-Trigger + arch-onboarding-Querverweis) + SP47
(Tiefe III — Review-Bundle als portables Reviewer-Interface:
`make_review_bundle.py` (Core) baut das eine self-contained Dokument — Kernel,
Checkliste, Produktrahmen, Pläne, Diff, REVIEW-Grammatik direkt aus
check_review importiert; FINDING-Tokens per Template-Test an check_issues gepinnt; Dispatch-Rezepte je Harness in
verification-independence, /review zeigt aufs Tool) ausgeliefert, `v1.32.0`.

`v1.32.1` (Arc-Review über den Tiefe-Bogen, zwei unabhängige Reviewer: vier
ausführbare Defekte im Bundle-Tool geschlossen — Fence-Korruption bei
Markdown-Diffs, Non-UTF-8-Crash, IndexError bei fehlendem Options-Wert,
Subdir-Aufruf verlor Root-Quellen; Grammatik-Claim ehrlich auf die
REVIEW-Hälfte begrenzt + FINDING-Tokens per Template-Test an check_issues
gepinnt; adr-Auflösung sieht rohe Regeln, Deviation nur als echte Überschrift,
dor-Slot mit exaktem Key-Set; Doku-Kohärenz: bedingter arch-onboarding-Verweis,
Hard-Path-Klausel in github-issues).

SP48 (Telemetry-Ehrlichkeit — die Individualität von Projekten als bindende
Decke dokumentiert: Zahlen gelten nur projektintern gegen die eigene Baseline
(Trends, Verhältnisse, Catch/Escape-Ereignisse als robusteste Klasse), kein
projektübergreifendes Benchmarking, Cockpit-Schwellen sind Startwerte zur
Rekalibrierung, Goodhart/Self-Grading-Vorbehalt; Moduldoc-Sektion „honest
ceiling" + Cockpit-Docstring + README, per Template-Test gepinnt)
ausgeliefert, `v1.33.0`.

## Sub-Projekt-Tabelle (SP1–SP24)

Die Tabelle wurde bis SP24 gepflegt; ab SP25 trägt das Narrativ oben die
Historie allein.

| Sub-Projekt | Inhalt | Status |
|---|---|---|
| **SP1** Foundation | Kern + Adapter + copier-Init + additiver Brownfield-Drop-in | ✅ ausgeliefert |
| **SP2** Architektur-Onboarding | Architektur-Interview + Verifikation gegen echten Code | ✅ ausgeliefert |
| **SP3** Prozess-Vervollständigung (Multi-Repo/-Mensch) | feature-registry · github-issues · contracts-drift | ✅ Slices 1–3 |
| **SP4** Prozess-Vervollständigung II | git-hooks (lokale Enforcement-Säule) · contract-first (Interface-declared-first-Gate) · parity (Capability×Surface-Matrix, Gap→Issue) · security-floor (Pattern-Floor über git-getrackte Dateien) | ✅ ausgeliefert |
| **Capstone** command-adapters | Harness-native Slash-Commands (Claude / Copilot / AGENTS.md), dünn auf `docs/process/` zeigend, vom doc-drift-gate mitgeprüft — schließt das „vollständig wie Kenni"-Programm bei `v1.0.0` | ✅ ausgeliefert |
| **SP7** ci-adapters | GitLab CI als zweiter Enforcement-Transport (`ci`-Namespace, includable Job + Root-Shim) · dokumentierte No-CI-Degradation · Install-Fallbacks ohne `uv` (pipx / venv+pip / lokaler Clone) | ✅ ausgeliefert |
| **SP8** english-canon | Alle Artefakte englisch (halbiert die Doku-Token je Session) · Kernel-Regel „Dialog in Nutzersprache" · „Wann lohnt es nicht"-Ehrlichkeit · Journal-Pflicht erst ab Tier 2 | ✅ ausgeliefert |
| **SP9** audit-fixes | Drei-Achsen-Audit: alle bestätigten False-Greens geschlossen (Manifest load-bearing, arch-Fence, unborn-main-Hook, hooksPath-Guard) · Failure-Modes mit Diagnose statt Traceback · doc-drift versteht dokument-relative Links · Doku-Drift bereinigt | ✅ ausgeliefert |
| **SP10** telemetry | Effizienz messbar (Audit-Finding, aus Kenni generalisiert): `GRADE`-Trace-Konvention im Journal · Gate lintet das Trace-Format (kein stiller Telemetrie-Verlust) · read-only KPI-Cockpit (`process_kpis.py`: effectiveness/convergence/suite/tempo/cost/cfr) · Grader-Kalibrier-Suite mit den drei Vertrauens-Schwellen (≥20/≥5 · 0 False-PASS · ≥90 % ≤2 Runden) | ✅ ausgeliefert |
| **SP11** reaudit + public | Adversariales Re-Audit der Telemetry-Slice: False-Greens geschlossen (Suite-Shape-Alignment in Gefahr-Richtung, Filter=Grammatik, Unicode-round, Typo-Root) · Failure-Modes sprechen statt Tracebacks · persönliche Daten aus dem Tree, englischer README-Einstieg, `uv.lock` committed, CI least-privilege | ✅ ausgeliefert |
| **SP12** verification-independence | Kontext-Unabhängigkeit der Verifikation als Kern-Methodik (die Lücke nach dem Telemetry-Slice): Produktion warm (Kohärenz), Verifikation unabhängig, tier-gestaffelt (0–1 Selbstcheck · 2 frischer Bundle-Review · 3 cross-model + adversarial-refute) · Review attestiert seine Unabhängigkeit, sonst zählt sie einen Tier schwächer | ✅ ausgeliefert |
| **SP13** anchor-guidance | Zwei portable Lücken geschlossen (aus dem Vergleich mit einem reifen Adopter): der „Anker trägt Pointer, nicht driftendes Detail"-Diskriminator ist jetzt in `start-here.md` ausgesprochen (*driftet es beim Refactor? → nicht in den Anker*), plus wie man Anker für große Multi-Stack-Repos skaliert (nested per-Subtree-Anker) — hält den dünnen Kernel dünn | ✅ ausgeliefert |
| **SP14** junior-legibility | Drei Lücken aus einer Junior-Simulation geschlossen: eine stack-neutrale `review-checklist.md` (was ein Review wirklich prüft — Vollständigkeit, Korrektheit, **Security** untrusted-input→sink, Design/ein-Owner, Tests), eine „Wie erkenne ich meinen Tier?"-Heuristik in `risk-tiers.md`, und ein ehrlicher „Muster-Floor, nicht deine Security-Review"-Satz im security-floor-Modul | ✅ ausgeliefert |
| **SP15** arch-docs | Neues opt-in Modul: stakeholder-gerichtete Architektur-Doku (arc42/C4-lite) als `ARCHITECTURE-OVERVIEW.md`-Scaffold — Kontext, Qualitätsziele, Runtime, Deployment, Risiken/Tech-Debt, Glossar; Building-Blocks→arch-Block und Decisions→ADRs *verlinkt* statt dupliziert (ein Owner); Gate prüft nur mechanisch Ehrliches (tote ADR-Refs hart, Platzhalter als Note), täuscht nie „dokumentiert" vor | ✅ ausgeliefert |
| **SP16** review-breadth | `review-checklist.md` aus der Web-Lastigkeit gelöst: zwei stack-neutrale Dimensionen ergänzt — **Performance & Effizienz** (N+1, unbounded Fan-out, heiße Pfade) und **Observability & Betreibbarkeit** (fail-fast statt stiller Degradation, deploy-abhängige Fragen konditional formuliert); untrusted-input→sink breiter gefasst | ✅ ausgeliefert |
| **SP17** parallel-friction | Reibung für parallele Agenten auf einem Repo reduziert: das eine geteilte Tages-Journal wird per Branch shardbar (`.process-work/journal/<branch-slug>/YYYY-MM-DD.md` — Gate und Cockpit lesen rekursiv, beide Layouts funktionieren); neue „## Parallel efforts"-Sektion nennt den Trade-off ehrlich (Ausführung parallel+sharded, Integration serialisiert durch ff-only, nie zwei Efforts auf einem Owner) | ✅ ausgeliefert |
| **SP18** decision-records | ADR zum getypten **Decision Record** generalisiert (`Type: architecture \| product \| process`) — signifikante Produkt-/Prozessentscheidungen haben endlich ein Zuhause; Intent bleibt *ein* Wert pro Record (Atomaritäts-Forcing-Function). Erstes **Core-Gate** (`check_decisions.py`, immer aktiv, da `adr/` Core ist): Listing-Drift + ungültige Enums + inkohärente Status×Intent-Paare (`Superseded`+`keep`) hart, unausgefüllte Menüs/fehlender Type soft. Rule 4 verankert „signifikante Entscheidung → Decision Record" + Patch-Count-Gate (dritter Patch default-falsch) | ✅ ausgeliefert |
| **SP19** review-enforcement | Review-Unabhängigkeit von Prosa zu gegatetem Artefakt: strukturierte `REVIEW`-Attestierung im Journal, zweites **Core-Gate** (`check_review.py`). **Arithmetik** hart — ein `pass` darf keinen Tier klären, den seine Independence-Flags nicht tragen (Selbst-Review/warm klärt kein Tier 2+; Tier 3 braucht `cross-model` oder ehrliches `single-family`). **Presence** hart — ein gemergter (archivierter) Tier-3+-Plan ohne klärende Attestierung fällt durch, außer benannte `review-waived:`-Ausnahme. Identität/Modell-Wahrheit bleibt attestiert (Gate sieht die Review-Runtime nicht) — ehrliche Grenze, kein False-Green | ✅ ausgeliefert |
| **SP20** issue-centricity | GitHub-Issues stärker in den Fluss gezogen: **Issue-before-code** als Gate im `github-issues`-Modul — ein *aktiver* Tier-3+-Plan ohne `issue:`-Link (oder benanntes `issue-waived:`) fällt durch. Spiegelbild zum Review-Gate: Issues bei aktiven Plänen (Start), Reviews bei archivierten (Ende), kein Overlap. Claim/Heartbeat-Disziplin geschärft (Claim-Felder + Kadenz) — bewusst *nicht* gegatet (Social/Wall-clock nicht maschinenprüfbar), ehrlich so benannt. Alles opt-in unter dem Modul (Portabilität) | ✅ ausgeliefert |
| **SP21** dependency-sequencing | Stories können Abhängigkeiten deklarieren (`blocked_by: [STORY-NNNN]`, Sequenzierung, nicht Dekomposition). Feature-registry-Gate (Owner erweitert, kein Parallel-Gate) prüft hart: dangling Ref, Selbst-Referenz, **Dependency-Zyklus** (DFS, mit Pfad); soft: `done`-Story mit unfertigem Blocker. Read-only `story_order.py` berechnet ready-to-start-Set + topologische Reihenfolge. „Blocked by #N"-Rendering ins Issue bleibt optionale Projektion (Registry = SSOT) | ✅ ausgeliefert |
| **SP22** github-master | Opt-in Adapter, der die Wahrheitsrichtung dreht: **GitHub Issues = SSOT**, Datei-Registry wird Spiegel — ohne Netz in CI. Zwei Schichten strikt getrennt: **Sync** (`gh_sync.py`, zieht Issues → committeter `.process-work/github-snapshot.json`, Netz) vs. **Gate** (`check_github_master.py`, hermetisch offline über den Snapshot). Harte Master-Invarianten: jede lebende Story hat Issue-Ref + Snapshot-Eintrag (beidseitig vollständig), Drift auf title/status↔state; `null`-Slots für blocked_by/parent/board (spätere Slices). Portabler registry-master-Default bleibt unangetastet | ✅ ausgeliefert |
| **SP23** sub-issues | Dekomposition: `parent: STORY-NNNN` (Baum, orthogonal zu `blocked_by`). Feature-registry-Gate erweitert (geteilte Zyklus-DFS, ein Owner): parent dangling/self/**Zyklus** hart; soft: parent-done-vor-Kind, wörtliche Child↔Parent-Dopplung. Epic-Test-Regel gelöst: ein Parent darf `done` ohne eigenen Test nur wenn **alle Kinder done** (Kinder-Tests decken ab), ein Leaf nie. github-master driftprüft `parent` (Sub-Issues = Master); `story_order.py` zeigt Epic→Kinder-Hierarchie. Anti-Dup ehrlich nur bei wörtlicher Gleichheit prüfbar | ✅ ausgeliefert |
| **SP24** project-board | GitHub Project Board (Backlog→Ready→In-progress→Review→Done) — **automatisiert *und* gegatet**, ohne Hermetik zu brechen: `gh_board.py` (Netz) füllt den `board_status`-Slot im Snapshot, der **Gate prüft offline** die Konsistenz Spalte↔Story-Status↔Issue-State (unbekannte Spalte / Widerspruch hart; `deprecated` exempt). Kartenbewegung (`--push`) ist ein expliziter Extension-Point (GitHub-Write, best-effort, nie Gate). Eine kanonische Mapping-Tabelle | ✅ ausgeliefert |
